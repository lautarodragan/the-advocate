//! The pictures of `ShowPicture`: which ones each map carries, and how.
//!
//! **The small ones go in OAM objects**, after the map's characters in its
//! sprite bank: the picture is put up and taken down without touching
//! anything underneath, which is also what RM2k does, at the price of
//! fifteen colours —a sprite palette— and the per-line object budget. The
//! map has to have room for them, and `wally` says whether it did; the one
//! that did not is accepted without being done. The console keeps up to
//! [`SLOTS`] at a time, one per RM2k picture number of the map; they share
//! sprite palettes when their colours fit together, and their tiles when
//! they are the same, and a sparse block goes as 8x8 objects.
//!
//! **The big ones go in BG1, in mode 1, while they are shown**, with the
//! map hidden: a picture that goes with the screen and does not fit the
//! objects, or one that goes with the map and covers the whole screen.
//! What fits is what it draws over its transparent colour, not its file:
//! a file of the whole screen with a silhouette in it is a small one (see
//! `sparse`).
//! They are the cartridge's, not each map's: the same picture on two maps
//! is one layer.
//!
//! **RM2k's screen is 320x240 and the console's 256x224**, so a picture
//! that goes with the screen is scaled; one that goes with the map is not,
//! since the map is not. **RM2k's position is the centre of the image**:
//! the console computes the corner when it shows it.
//!
//! **Unless the game asks for it to be cropped** —`[graphics]
//! cropped_pictures` of the project—: a picture that is a capture of
//! RM2k's screen showing the map, which scaled no longer matches the map
//! the console shows, gets the console's window of it instead, from the
//! pixel the game says. Which window that is depends on where the camera
//! is when it is shown, and only the game knows that. Such a picture is
//! always a big one: it covers the screen.
//!
//! The pixels are `rm2k-snes-images`'.

use crate::fail::{Result, Stop};
use crate::game::GameMap;
use crate::images;
use rm2k_project::Project;
use rm2k_snes_events::codes::{CHANGE_PBG, MOVE_PICTURE, SHOW_PICTURE, TINT_SCREEN};
use rm2k_snes_events::registry::PictureKey;
use rm2k_snes_mapdata::request::PictureImage;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::{Path, PathBuf};

/// RM2k's screen and the console's.
pub const RM_WIDTH: i64 = 320;
pub const RM_HEIGHT: i64 = 240;
pub const WIDTH: i64 = 256;
pub const HEIGHT: i64 = 224;
/// This port's large object, and the 8x8 tiles it measures on a side; and
/// how many tiles a row of the OAM name grid has.
pub const OBJ: i64 = 32;
pub const OBJ_SIDE: i64 = OBJ / 8;
pub const GRID: i64 = 16;
/// A row of blocks of the name grid: four objects side by side.
pub const BLOCK_ROW: i64 = 4 * GRID;
/// The fifteen of a sprite palette: index 0 is not drawn.
pub const COLORS: i64 = 15;
/// How many pictures the console keeps at a time, one per number: `PIC_SLOTS`
/// in the runtime's `far_ram.s`. Until 2026-10-16 it was two, one palette
/// each; how many go in is now what the palettes and the tiles allow.
pub const SLOTS: usize = 16;
/// The biggest picture the plane of objects takes: half the 512 tiles the
/// PPU names, so a map's characters keep the other half.
pub const WIDTH_MAX: i64 = 256;
pub const HEIGHT_MAX: i64 = 128;
/// The big ones' layer: the seven background palettes above the message
/// window's, the 1024 tiles a tilemap entry names, and a 32x64 tilemap.
/// `BIG_*` in the runtime's `big_picture.s` says the same.
pub const BIG_PALETTES: i64 = 7;
pub const BIG_FIRST_PALETTE: i64 = 1;
pub const BIG_TILES: i64 = 1024;
pub const BIG_ROWS: i64 = 64;
/// How many the cartridge's table of them holds: `OP_BIG_SHOW` names one
/// with a byte, and $FF is the runtime's `PIC_NONE`.
pub const BIG_IMAGES: usize = 255;
/// A big one that a `MovePicture` zooms is also carried as a mode 7
/// texture, whose map names 256 tiles. While it is still it is shown in
/// mode 1 as the others, but from VRAM's upper half —mode 7 owns the lower
/// one, and its texture goes up there meanwhile—: its tiles from word
/// $4000 to its tilemap, one screen of 32x32 at $7C00. So it takes the 960
/// tiles in between and 32 rows; one that takes more is not zoomed, and
/// fades as before. `BIG_HYBRID_*` in the runtime's `big_picture.s`.
pub const M7_TILES: i64 = 256;
pub const M7_LAYER_TILES: i64 = 960;
pub const M7_LAYER_ROWS: i64 = 32;

/// `zoom` percent of `side`, rounded and never under one.
pub fn zoomed(side: i64, zoom: i64) -> i64 {
    std::cmp::max(1, (side * zoom + 50).div_euclid(100))
}

/// The pictures the console does not scale, by name in lowercase —RM2k
/// finds a file without minding its case—: the ones the game crops, each
/// with the pixel the console's screen is cut from, and the ones drawn for
/// the console.
#[derive(Debug, Clone, Default)]
pub struct Cropped {
    crops: HashMap<String, (i64, i64)>,
    for_console: BTreeSet<String>,
}

impl Cropped {
    /// `[graphics] cropped_pictures`: a table of `name = [x, y]`; and
    /// `[graphics] console_pictures`, a list of names, if it is there.
    pub fn read(project: &Project) -> Result<Cropped> {
        let keys = ["graphics", "cropped_pictures"];
        let mut out = HashMap::new();
        for (name, at) in project.table(&keys)? {
            let pair = at
                .as_array()
                .filter(|a| a.len() == 2)
                .and_then(|a| Some((a[0].as_integer()?, a[1].as_integer()?)));
            let Some(pair) = pair else {
                return Err(project
                    .wrong_type(&["graphics", "cropped_pictures", name], "[x, y]", at)
                    .into());
            };
            out.insert(name.to_lowercase(), pair);
        }
        // **A picture drawn for the console** is a port's own —see
        // `patches/manual/Picture/`—, whose pixels already are the console's:
        // scaled to four fifths, text drawn pixel by pixel loses its
        // strokes. It is shown at its size, with its centre where RM2k's
        // lands: see `show_picture` in `rm2k-snes-images`.
        let for_console = match project.value(&["graphics", "console_pictures"]) {
            Err(_) => BTreeSet::new(),
            Ok(_) => project
                .strings(&["graphics", "console_pictures"])?
                .into_iter()
                .map(|n| n.to_lowercase())
                .collect(),
        };
        Ok(Cropped {
            crops: out,
            for_console,
        })
    }

    /// Where the console's screen is cut from `name`, if it is cropped.
    pub fn of(&self, name: &str) -> Option<(i64, i64)> {
        self.crops.get(&name.to_lowercase()).copied()
    }

    /// Whether `name` was drawn for the console, and is not scaled.
    pub fn for_console(&self, name: &str) -> bool {
        self.for_console.contains(&name.to_lowercase())
    }
}

/// The file of the picture `name`, or None if the game does not have it.
/// Without regard to case, as RPG_RT finds it.
pub fn path_of(game_dir: &Path, name: &str) -> Option<PathBuf> {
    crate::resources::find(&[game_dir], "Picture", name, &[".png"])
        .map(|p| rm2k_project::absolute(&p))
}

/// A PNG's width and height, from its header.
pub fn png_size(path: &Path) -> Result<(i64, i64)> {
    let file = std::fs::File::open(path).map_err(|e| crate::fail::io(path, e))?;
    let decoder = png::Decoder::new(file);
    let reader = decoder
        .read_info()
        .map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
    let info = reader.info();
    Ok((info.width as i64, info.height as i64))
}

fn int(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

/// A picture as the scan answers it —its [`PictureKey`], whose fields read
/// through this one—, and what the converter learns of it on the map that
/// shows it: `path` and `with_map` for a part, `behind_map`,
/// `screen_on_map`. It goes on in the tables, to the compiler and the
/// emission, as the key's fields and then these, only when they say
/// something.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Key {
    #[serde(flatten)]
    pub key: PictureKey,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(default, skip_serializing_if = "is_false")]
    pub with_map: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub behind_map: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub screen_on_map: bool,
}

impl From<PictureKey> for Key {
    fn from(key: PictureKey) -> Key {
        Key {
            key,
            ..Key::default()
        }
    }
}

impl std::ops::Deref for Key {
    type Target = PictureKey;
    fn deref(&self) -> &PictureKey {
        &self.key
    }
}

fn is_false(b: &bool) -> bool {
    !b
}

/// A key's centre, in the widths the converter computes with.
fn wide((x, y): (i32, i32)) -> (i64, i64) {
    (x.into(), y.into())
}

/// The keys a scan answered, in `pictures`, as the converter keeps them.
pub fn keys(pictures: &[PictureKey]) -> Vec<Key> {
    pictures.iter().cloned().map(Key::from).collect()
}

/// A key as it goes on in a table, to have more fields put after its own.
fn entry_of(key: &Key) -> Map<String, Value> {
    match serde_json::to_value(key) {
        Ok(Value::Object(entry)) => entry,
        _ => unreachable!("a key is an object"),
    }
}

/// A picture converted, as the stage answers it plus half its size in
/// RM2k's pixels.
struct Converted {
    x: i64,
    y: i64,
    width: i64,
    height: i64,
    half: (i64, i64),
    palette: Vec<[u8; 3]>,
    indices: Vec<Vec<i64>>,
}

fn convert(path: &Path, key: &Key, for_console: bool) -> Result<Converted> {
    let (width, height) = png_size(path)?;
    let zoom = i64::from(key.zoom);
    let (zw, zh) = (zoomed(width, zoom), zoomed(height, zoom));
    // One drawn for the console is placed by the size RM2k would scale to
    // it: see `Screens::rm_size` in `rm2k-snes-images`, the same arithmetic.
    let (rw, rh) = if for_console {
        (
            (zw * RM_WIDTH).div_euclid(WIDTH),
            (zh * RM_HEIGHT).div_euclid(HEIGHT),
        )
    } else {
        (zw, zh)
    };
    // Placed by variables, or with the map: converted with its corner on
    // the grid, which is where the size comes out exact.
    let (cx, cy) = key
        .at
        .map(wide)
        .unwrap_or((zw.div_euclid(2), zh.div_euclid(2)));
    let a = images::picture(
        path,
        key.transparent_color,
        0,
        cx,
        cy,
        COLORS,
        zoom,
        goes_with_map(key),
        for_console,
    )?;
    let row = |r: Vec<usize>| r.into_iter().map(|v| v as i64).collect();
    Ok(Converted {
        x: a.x,
        y: a.y,
        width: a.width as i64,
        height: a.height as i64,
        half: (rw.div_euclid(2), rh.div_euclid(2)),
        palette: a.palette,
        indices: a.indices.into_iter().map(row).collect(),
    })
}

/// Whether the picture of `key` goes with the map: by its `ShowPicture`, or
/// because it is the part of a drawing the map carries the rest of —see
/// [`crate::map_pictures::Parts`]—, or because RM2k shows it where its map
/// is —see [`screen_on_map`]—, both of which the compiler is told too.
fn goes_with_map(key: &Key) -> bool {
    key.map_fixed || key.with_map || key.screen_on_map
}

/// The file of `key`'s picture: the part's, or the game's by its name.
///
/// A key `with_map` shows only its own part of one of several drawings
/// under a number: see [`crate::map_pictures::Parts`]. Such a part is never
/// a big one —it is what the drawings do not share, a lit option—, and its
/// file is not the game's.
fn file_of(game_dir: &Path, key: &Key) -> Option<PathBuf> {
    match &key.path {
        Some(path) => Some(PathBuf::from(path)),
        None => path_of(game_dir, &key.name),
    }
}

/// Whether a part fits the plane of objects: what it draws within the
/// reach of an object's place from the picture's corner, a byte. The part
/// is the whole drawing's size, mostly transparent, so its corner stays
/// the drawing's.
fn part_fits(info: &Converted) -> bool {
    let mut any = false;
    for (y, row) in info.indices.iter().enumerate() {
        for (x, &i) in row.iter().enumerate() {
            if i != 0 {
                if x as i64 >= WIDTH_MAX || y as i64 >= OBJECTS_HEIGHT_MAX {
                    return false;
                }
                any = true;
            }
        }
    }
    any && !info.palette.is_empty()
}

/// Whether the picture fits the plane of objects.
/// How tall a picture the objects take when it is not a big one —placed by
/// variables, or going with the map without covering the screen—: an
/// object's place in the picture is a byte, `picture_data`'s dy. What it
/// costs is the tiles of what it draws, which `wally` weighs against the
/// map's VRAM: a sparse block goes as 8x8 objects, an empty one as none.
/// Until 2026-10-20 it was [`HEIGHT_MAX`], from when every block was a
/// whole 32x32 object; Zounds' skill list on map 190, two lines of text at
/// the top of a 167x227 picture placed by variables, was left out by it.
pub const OBJECTS_HEIGHT_MAX: i64 = 256;

fn fits(info: &Converted) -> bool {
    0 < info.width
        && info.width <= WIDTH_MAX
        && 0 < info.height
        && info.height <= OBJECTS_HEIGHT_MAX
        && !info.palette.is_empty()
}

/// The first tile of object `block` of the pictures, from their base. A
/// 32x32 object reads four tiles from four consecutive rows of the name
/// grid, which is sixteen wide: a row of blocks fits four objects.
pub fn block_tile(block: i64) -> i64 {
    (block / 4) * (4 * GRID) + (block % 4) * OBJ_SIDE
}

/// The picture's size on the console's screen, as the plane of objects
/// would draw it: at its zoom, scaled unless it goes with the map or was
/// drawn for the console.
fn on_console(path: &Path, key: &Key, for_console: bool) -> Result<(i64, i64)> {
    let (width, height) = png_size(path)?;
    let (w, h) = (
        zoomed(width, i64::from(key.zoom)),
        zoomed(height, i64::from(key.zoom)),
    );
    if goes_with_map(key) || for_console {
        return Ok((w, h));
    }
    let (cx, cy) = key
        .at
        .map(wide)
        .unwrap_or((w.div_euclid(2), h.div_euclid(2)));
    let (x0, y0) = (cx - w.div_euclid(2), cy - h.div_euclid(2));
    Ok((
        ((x0 + w) * WIDTH).div_euclid(RM_WIDTH) - (x0 * WIDTH).div_euclid(RM_WIDTH),
        ((y0 + h) * HEIGHT).div_euclid(RM_HEIGHT) - (y0 * HEIGHT).div_euclid(RM_HEIGHT),
    ))
}

/// Whether the picture goes in the background layer: too big for the
/// objects, and either with the screen or covering it whole; or cropped,
/// which is the screen.
fn is_big(path: &Path, key: &Key, cropped: &Cropped) -> Result<bool> {
    if key.by_variable || key.with_map {
        return Ok(false);
    }
    let name = key.name.as_str();
    if cropped.of(name).is_some() {
        return Ok(true);
    }
    let (w, h) = on_console(path, key, cropped.for_console(name))?;
    if w <= WIDTH_MAX && h <= HEIGHT_MAX {
        return Ok(false);
    }
    if sparse(path, key, cropped.for_console(name))? {
        return Ok(false);
    }
    Ok(!key.map_fixed || (w >= WIDTH && h >= HEIGHT))
}

/// Whether the picture at `path`, shown as `key` says, is a small one by
/// what it draws and not by its file: see [`sparse`]. For
/// [`crate::map_pictures`], which says what a picture it does not take
/// loses, and one of these hides nothing.
pub fn draws_little(path: &Path, key: &Key) -> Result<bool> {
    let (w, h) = on_console(path, key, false)?;
    Ok((w > WIDTH_MAX || h > HEIGHT_MAX) && sparse(path, key, false)?)
}

/// How many objects a picture bigger than [`HEIGHT_MAX`] may be cut into
/// and still be a small one: see [`sparse`]. An eighth of the 128 the
/// console has for everything. Desert Nightmare's game over, `GO_Text`, is
/// eight lines of text of 45 objects each, and is shown on forty maps: as
/// small ones they took 35 KB of `picture_data`'s 64, and the maps' sprite
/// tiles, for what RM2k shows over a screen faded to black anyway.
pub const SPARSE_OBJECTS: usize = 16;

/// Whether a picture bigger than [`HEIGHT_MAX`] draws, over its transparent
/// colour, so little that it is cut into no more than [`SPARSE_OBJECTS`]
/// —its empty blocks are no objects, see [`Bank::cut`]—: then the objects
/// take it as a small one, placed where its file puts what it draws, and it
/// is seen over the map as in RM2k. As a big one it hid the map and showed
/// its few pixels over black: Desert Nightmare's roof scene, map 28, drops
/// its monster in four files of RM2k's whole screen, each a 14x19
/// silhouette, and the screen went black for six seconds. What it costs is
/// the tiles of what it draws, which `wally` weighs against the map's as
/// with any small one; and on a map without room for them it is left out
/// as any small one, its commands accepted without being done, and the map
/// is seen: a few pixels are not worth hiding it for —Desert Nightmare's
/// map 28 has none to spare, and loses the monster—.
///
/// The file says it first, cheaply —[`crate::map_pictures::drawn`], twice
/// the limit at its zoom, before the console's scale—, so that a photograph
/// is not converted for it; the conversion says it exactly.
fn sparse(path: &Path, key: &Key, for_console: bool) -> Result<bool> {
    if !key.transparent_color {
        return Ok(false);
    }
    let (dw, dh) = crate::map_pictures::drawn(path)?;
    let (dw, dh) = (
        zoomed(dw as i64, i64::from(key.zoom)),
        zoomed(dh as i64, i64::from(key.zoom)),
    );
    if dw == 0 || dw > 2 * WIDTH_MAX || dh > 2 * HEIGHT_MAX {
        return Ok(false);
    }
    let info = convert(path, key, for_console)?;
    // What it draws within an object's reach from its corner: one that goes
    // with the map is not scaled, and its file is wider than the objects
    // take —Desert Nightmare's warehouse, map 21, drops a 6x7 shadow at the
    // 204th pixel of a 320x240 file—.
    if !part_fits(&info) {
        return Ok(false);
    }
    Ok(sparse_info(&info))
}

/// Whether the objects take a picture that is not a big one: a part, or
/// one small by what it draws —[`sparse`]—, by what it draws; the rest, by
/// their size.
fn takes(info: &Converted, key: &Key) -> bool {
    fits(info) || part_fits(info) && (key.with_map || sparse_info(info))
}

/// [`sparse`]'s count, on the picture converted.
fn sparse_info(info: &Converted) -> bool {
    let objects = Bank::default().cut(info).len();
    0 < objects && objects <= SPARSE_OBJECTS
}

/// Whether some picture of `keys` is small: one [`for_map`] would cut for
/// the plane of objects, and not [`big_for_map`]'s. A copy of a common
/// event into a map exists for those —see [`crate::common_pages`]—: a big
/// one is the cartridge's, and the same with a map and without one.
pub fn any_small(game_dir: &Path, keys: &[Key], cropped: &Cropped) -> Result<bool> {
    for key in keys {
        let Some(path) = file_of(game_dir, key) else {
            continue;
        };
        if !is_big(&path, key, cropped)?
            && takes(&convert(&path, key, cropped.for_console(&key.name))?, key)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Where the layer is drawn from: the key's centre, or the screen's for
/// one that goes with the map, which covers it whole.
fn big_center(key: &Key) -> (i64, i64) {
    if key.map_fixed {
        return (RM_WIDTH / 2, RM_HEIGHT / 2);
    }
    key.at.map(wide).unwrap_or((0, 0))
}

/// A big picture of a map: its key, and its layer as the stage answered
/// it with its half size and centre.
#[derive(Debug, Clone)]
pub struct Big {
    pub key: Key,
    pub layer: Value,
}

/// Whether a `MovePicture` of the map zooms the picture `key`: one under
/// its number that goes to another size than the one it was shown at.
/// `zooms` is what the scan wrote down, `[number, zoom]` per move.
fn moved_to_another_size(key: &Key, zooms: &[Value]) -> bool {
    zooms
        .iter()
        .any(|z| int(&z[0]) == i64::from(key.number) && int(&z[1]) != i64::from(key.zoom))
}

/// The big pictures of `keys`. The ones that do not fit even cut to the
/// screen are left out, and their commands are accepted without being
/// done. The ones a move of the map zooms —`zooms`, as the scan wrote it
/// down— carry a mode 7 texture too, if they leave room for it. `whose` is
/// who shows them, for the log: "map 12", or "the common events".
///
/// With `small`, the ones it says of the rest too, which would go in the
/// sprites: see [`over_black`].
///
/// With `under`, a map's still panorama and the pictures [`still_over`]
/// it: those are drawn over the panorama, which fills their holes, and
/// their layer says so with `under`. See [`still_over`].
pub fn big_for_map(
    game_dir: &Path,
    keys: &[Key],
    zooms: &[Value],
    whose: &str,
    cropped: &Cropped,
    small: &dyn Fn(&Key) -> bool,
    under: Option<(&Path, &BTreeSet<(i64, String)>)>,
) -> Result<Vec<Big>> {
    let mut out = Vec::new();
    for key in keys {
        let name = key.name.as_str();
        let Some(path) = file_of(game_dir, key) else {
            continue;
        };
        if !is_big(&path, key, cropped)? && !small(key) {
            continue;
        }
        let (cx, cy) = big_center(key);
        let zoom = i64::from(key.zoom);
        // Only one with holes —a quarter of it or more, as a picture that
        // is part of a map, `map_pictures`—: over an opaque one the small
        // pictures under its number would come out in front of it.
        let panorama = match under {
            Some((panorama, still))
                if cropped.of(name).is_none()
                    && !cropped.for_console(name)
                    && zoom == 100
                    && !moved_to_another_size(key, zooms)
                    && shown_in(key, still)
                    && key.transparent_color
                    && crate::map_pictures::holes(&path)?
                        >= crate::map_pictures::OPAQUE_HOLES_MIN =>
            {
                Some(panorama)
            }
            _ => None,
        };
        let layer = images::background(
            &path,
            key.transparent_color,
            cx,
            cy,
            zoom,
            cropped.of(name),
            cropped.for_console(name),
            BIG_PALETTES,
            BIG_FIRST_PALETTE,
            BIG_TILES,
            BIG_ROWS,
            moved_to_another_size(key, zooms),
            panorama,
        )?;
        let Some(layer) = layer else {
            println!(
                "  {whose}: the picture {} doesn't fit the background layer even cut to the screen",
                crate::text::quoted(name)
            );
            continue;
        };
        let (mut width, mut height) = png_size(&path)?;
        // One drawn for the console, by the size RM2k would scale to it, as
        // in `convert`.
        if cropped.for_console(name) {
            (width, height) = (
                (width * RM_WIDTH).div_euclid(WIDTH),
                (height * RM_HEIGHT).div_euclid(HEIGHT),
            );
        }
        let mut layer = serde_json::to_value(layer).expect("a layer is JSON");
        let object = layer
            .as_object_mut()
            .ok_or_else(|| Stop::new("a layer is not an object"))?;
        object.insert(
            "half".into(),
            json!([
                zoomed(width, zoom).div_euclid(2),
                zoomed(height, zoom).div_euclid(2)
            ]),
        );
        object.insert("center".into(), json!([cx, cy]));
        if let Some(panorama) = panorama {
            println!(
                "  {whose}: the picture {} is drawn over the panorama {}, which shows through its holes",
                crate::text::quoted(name),
                crate::text::quoted(&panorama.file_stem().unwrap_or_default().to_string_lossy())
            );
            object.insert("under".into(), json!(panorama.to_string_lossy()));
        }
        out.push(Big {
            key: key.clone(),
            layer,
        });
    }
    Ok(out)
}

/// The pictures `map`'s pages show **over a black screen**, by number and
/// name in lowercase: a `ShowPicture` after a `TintScreen` to black in its
/// page —red, green and blue at 0—, with no other tint between them; placed
/// by a constant and with the screen, which is how the background layer
/// draws it.
///
/// Those can go in the background layer when the map has no room for them
/// in its sprites: the layer hides the map and its characters, which over
/// black are not seen anyway, and its transparency darkens, which over
/// black is exact. The Book of Three's ending does it: it tints map 69 and
/// map 72 black and shows its credits and its quotes there, centred, fading
/// in and out, and the maps' tiles leave no room for them in the sprites.
/// A tint before the page —the map entered black, another page's— is not
/// seen: the rule only takes what it can be sure of.
pub fn over_black(map: &GameMap) -> BTreeSet<(i64, String)> {
    let mut out = BTreeSet::new();
    for event in &map.events {
        for page in &event.pages {
            let mut black = false;
            for c in &page.commands {
                let p = &c.parameters;
                match c.code {
                    TINT_SCREEN if p.len() >= 3 => black = p[..3] == [0, 0, 0],
                    SHOW_PICTURE if black && p.len() >= 5 && p[1] == 0 && p[4] == 0 => {
                        out.insert((p[0] as i64, c.string.to_lowercase()));
                    }
                    _ => {}
                }
            }
        }
    }
    out
}

/// Whether the key, as the scan answers it, is one of `shown`'s, as
/// [`over_black`] and [`still_over`] answer them: placed by a constant and
/// with the screen.
pub fn shown_in(key: &Key, shown: &BTreeSet<(i64, String)>) -> bool {
    !key.by_variable
        && !key.map_fixed
        && shown.contains(&(i64::from(key.number), key.name.to_lowercase()))
}

/// The pictures `map`'s pages show by variables **with the screen where
/// RM2k shows its map**, by number and name in lowercase: on a map RM2k
/// never scrolls —its one screen or less, not looping—, the screen
/// pictures shown by the same two variables as one under the same number
/// that goes with the map. A name also shown by other variables with the
/// screen is not one of them.
///
/// The console scales a picture that goes with the screen, four fifths
/// across, and not one that goes with the map, so the two would land in
/// different places where RM2k puts them in the same one. Such a one goes
/// with the map: its image is not scaled, and the compiler gives its
/// `ShowPicture` `PICTURE_SCREEN` too, which lets it move as a screen
/// picture does. Desert Nightmare's dog, on map 11, runs as pictures with
/// the map by its event's screen place, and the hit one is shown at the
/// same variables with the screen and moved behind the warehouse's roof:
/// scaled, it landed sixteen pixels to the left, on the sand. Measured
/// over the eight games on 2026-11-23, it is the only one.
pub fn screen_on_map(map: &GameMap) -> BTreeSet<(i64, String)> {
    let one_screen =
        i64::from(map.width) * 16 <= RM_WIDTH && i64::from(map.height) * 16 <= RM_HEIGHT;
    if !one_screen || map.scroll_type != 0 {
        return BTreeSet::new();
    }
    let by_variable = || {
        map.events
            .iter()
            .flat_map(|e| &e.pages)
            .flat_map(|p| &p.commands)
            .filter(|c| c.code == SHOW_PICTURE && c.parameters.len() >= 5 && c.parameters[1] == 1)
    };
    let with_map: BTreeSet<(i32, i32, i32)> = by_variable()
        .filter(|c| c.parameters[4] != 0)
        .map(|c| (c.parameters[0], c.parameters[2], c.parameters[3]))
        .collect();
    let (mut same, mut other) = (BTreeSet::new(), BTreeSet::new());
    for c in by_variable().filter(|c| c.parameters[4] == 0) {
        let p = &c.parameters;
        let name = (i64::from(p[0]), c.string.to_lowercase());
        if with_map.contains(&(p[0], p[2], p[3])) {
            same.insert(name);
        } else {
            other.insert(name);
        }
    }
    &same - &other
}

/// Whether the key, as the scan answers it, is one of `on_map`'s, as
/// [`screen_on_map`] answers them: placed by variables and with the screen.
pub fn screen_on_map_in(key: &Key, on_map: &BTreeSet<(i64, String)>) -> bool {
    key.by_variable
        && !key.map_fixed
        && on_map.contains(&(i64::from(key.number), key.name.to_lowercase()))
}

/// The big pictures `map`'s pages show **still over its panorama**, by
/// number and name in lowercase, as [`over_black`] answers them: placed by a
/// constant and with the screen, at their size, opaque, untoned and without
/// an effect, and never moved —no `MovePicture` of their number on the
/// map—; and the map swaps no panorama with `ChangePBG`.
///
/// On a map of one screen —[`crate::game::Game::screen_panorama`]—, what
/// RM2k shows through such a picture's holes is that panorama, still, and
/// the console draws the two together as one layer, for a picture with a
/// quarter of itself transparent or more; an opaque one is left as it was. And since the layer
/// then covers the screen with what RM2k shows there, the map's small
/// pictures are drawn over it, which they could not be over the black:
/// Zounds' skill screen, map 190, frames its skill list with
/// `Zounds_SystemBox_Pic` —the panorama's own pixels, cut out to clip the
/// list when it scrolls— and puts its selectors and a face over them. See
/// `big_picture.s` in the runtime, and the layer's `keeps_objects` in
/// `crate::convert`.
pub fn still_over(map: &GameMap) -> BTreeSet<(i64, String)> {
    let commands: Vec<&crate::game::Command> = map.all_commands().collect();
    if commands.iter().any(|c| c.code == CHANGE_PBG) {
        return BTreeSet::new();
    }
    let moved: BTreeSet<i64> = commands
        .iter()
        .filter(|c| c.code == MOVE_PICTURE && !c.parameters.is_empty())
        .map(|c| c.parameters[0] as i64)
        .collect();
    let mut out = BTreeSet::new();
    let mut spoilt = BTreeSet::new();
    for c in &commands {
        let p = &c.parameters;
        if c.code != SHOW_PICTURE || p.len() < 13 {
            continue;
        }
        let key = (p[0] as i64, c.string.to_lowercase());
        // With the screen, by a constant, at 100 %, opaque, untoned —red,
        // green, blue and saturation at 100— and without an effect; and the
        // 2003 bottom's transparency, if there is one, at 0.
        let still = p[1] == 0
            && p[4] == 0
            && p[5] == 100
            && p[6] == 0
            && p[8..12] == [100, 100, 100, 100]
            && p[12] == 0
            && p.get(14).is_none_or(|&b| b == 0)
            && !moved.contains(&key.0);
        if still {
            out.insert(key);
        } else {
            spoilt.insert(key);
        }
    }
    out.retain(|k| !spoilt.contains(k));
    out
}

/// Whether a layer carries a mode 7 texture.
fn textured(layer: &Value) -> bool {
    layer.get("mode7").is_some_and(|t| !t.is_null())
}

/// The cartridge's big pictures, numbered: the layers, in the order the
/// maps meet them, and each map's table —each key with its layer's number,
/// its centre and whether it has a texture—, which the event compiler
/// numbers against. The same picture drawn the same way on two maps, or
/// under two numbers, is one layer; but **the one a map zooms, with its
/// texture, is another layer than the one the rest show still**. Shown
/// still, one with a texture goes in VRAM's upper half, over the message
/// window's tiles, and the window's layer is off: Desert Nightmare's black
/// screen, which map 151 zooms, hid every message over it on the other
/// maps —the thoughts after the bar, map 32—. Until 2026-11-23 the two
/// were one layer, with the texture. The emission shares the tiles, the
/// tilemap and the colours of two layers that have the same: see
/// `big_pictures_section` in rm2k-snes-mapdata.
pub fn number_big(maps: &[&[Big]]) -> (Vec<Value>, Vec<Vec<Value>>) {
    let mut layers: Vec<Value> = Vec::new();
    let mut index: HashMap<String, usize> = HashMap::new();
    let mut numbers: Vec<Vec<usize>> = Vec::new();
    for bigs in maps {
        let mut map = Vec::new();
        for big in bigs.iter() {
            let ident = json!([
                big.key.name,
                i64::from(big.key.zoom),
                big.key.transparent_color,
                big.layer["center"],
                big.layer.get("under"),
                textured(&big.layer)
            ])
            .to_string();
            let number = *index.entry(ident).or_insert_with(|| {
                layers.push(big.layer.clone());
                layers.len() - 1
            });
            map.push(number);
        }
        numbers.push(map);
    }
    let mut tables = Vec::new();
    for (bigs, map) in maps.iter().zip(&numbers) {
        let mut table = Vec::new();
        for (big, &number) in bigs.iter().zip(map) {
            let mut entry = entry_of(&big.key);
            entry.insert("plane".into(), json!("background"));
            entry.insert("image".into(), json!(number));
            entry.insert("center".into(), big.layer["center"].clone());
            if textured(&layers[number]) {
                entry.insert("texture".into(), json!(true));
            }
            table.push(Value::Object(entry));
        }
        tables.push(table);
    }
    (layers, tables)
}

/// The most tiles a layer can take and leave the sprite bank whole: its
/// tiles then go from VRAM word $2000 to its tilemap at $4000, past the
/// 512 object tiles the PPU names. `BIG_KEEP_*` in the runtime's
/// `big_picture.s`.
pub const BIG_KEEP_TILES: i64 = 512;

/// The layers drawn over a map's panorama —[`still_over`]— that leave the
/// map's small pictures up over them: the ones whose tiles leave the sprite
/// bank alone, `keeps_objects` in the layer. The runtime draws only the
/// pictures' objects while such a layer is up, not the characters, which
/// are the map's. The rest hide the small ones, as every big picture did
/// until 2026-10-20.
pub fn keep_objects(layers: &mut [Value]) {
    for layer in layers.iter_mut() {
        if layer.get("under").is_none() {
            continue;
        }
        let tiles = int(&layer["tile_count"]);
        if tiles <= BIG_KEEP_TILES {
            layer["keeps_objects"] = json!(true);
        } else {
            println!(
                "  a big picture over {} takes {tiles} tiles: past {BIG_KEEP_TILES} it would                  overwrite the sprite bank, and the small pictures are not shown over it",
                layer["under"].as_str().unwrap_or("")
            );
        }
    }
}

/// What the log says of [`number_big`]'s layers, once they are final.
pub fn say_big(layers: &[Value]) {
    if !layers.is_empty() {
        println!(
            "  the cartridge carries {} big picture(s) in the background layer",
            layers.len()
        );
        let kept = layers
            .iter()
            .filter(|l| l["keeps_objects"] == json!(true))
            .count();
        if kept > 0 {
            println!("  {kept} of them over a map's panorama, with the small pictures over them");
        }
    }
}

/// What a map carries of the pictures the scan says it can show: what
/// `wally` reserves in the sprite bank (every picture's tiles, as cells
/// from the base, and how many palettes), what the event compiler numbers
/// against (each picture that went in, with its slot) and what the
/// emission writes (each one's half size, its objects, its palette and its
/// colours).
#[derive(Debug, Clone)]
pub struct ForMap {
    /// The pictures' names, joined; how many objects they take; the tiles
    /// they reserve from the base, and each one's 64 colour indices from
    /// there; and how many palettes.
    pub name: String,
    pub objects: usize,
    pub tiles: i64,
    pub cells: Vec<(usize, Vec<u8>)>,
    pub palettes: usize,
    pub table: Vec<Value>,
    pub images: Vec<PictureImage>,
}

impl ForMap {
    /// What `wally` is asked to reserve for them: its request's `picture`.
    pub fn asked(&self) -> Value {
        json!({
            "name": self.name,
            "objects": self.objects,
            "tiles": self.tiles,
            "cells": self.cells,
            "palettes": self.palettes,
        })
    }
}

/// A 32x32 block with this many 8x8 cells drawn or fewer goes as that many
/// 8x8 objects instead of one 32x32: a 7x8 digit is one tile and not
/// sixteen. More cells than this and the tiles saved are not worth the
/// objects, of which the console has 128 for everything.
pub const SMALL_CELLS: usize = 4;
/// And a block whose drawn cells are this many or fewer **and fill no more
/// than two of its four rows of cells** goes as cells too —a frame's top
/// and bottom edge, a line of text—, unless they are two whole rows side
/// by side: a band as wide as the block, where one 32x32 costs the same
/// slivers and a quarter of the objects. A 32x32 object costs four of the
/// 34 slivers the console draws on a line on each of its 32 lines, even
/// where it draws nothing; the cells cost one each, and only on their own
/// eight. Zounds' skill screen, map 190, puts a selector's frame and two
/// lines of the skill list on the same lines as the face: as whole blocks
/// they were 38 slivers on 37 lines, and the PPU dropped the frame. Since
/// 2026-10-20.
pub const THIN_CELLS: usize = 8;
pub const THIN_ROWS: usize = 2;

/// Whether a block whose cells `drawn` —0 to 15, row by row— are drawn
/// goes as 8x8 objects: see [`SMALL_CELLS`] and [`THIN_CELLS`].
fn as_cells(drawn: &[usize]) -> bool {
    let side = OBJ_SIDE as usize;
    let mut rows: BTreeMap<usize, usize> = BTreeMap::new();
    for &k in drawn {
        *rows.entry(k / side).or_default() += 1;
    }
    let band = rows.len() == 2
        && rows.values().all(|&n| n == side)
        && rows
            .keys()
            .max()
            .zip(rows.keys().min())
            .is_some_and(|(a, b)| a - b == 1);
    drawn.len() <= SMALL_CELLS || (drawn.len() <= THIN_CELLS && rows.len() <= THIN_ROWS && !band)
}
/// In an object's tile word, the bit that says it is an 8x8 object: the
/// tile is the word's low nine bits, from the pictures' base. `PIC_SMALL`
/// in the runtime's `picture_far.s`.
pub const SMALL_BIT: i64 = 0x8000;

/// One converted picture of the map, before its tiles are placed.
struct Shown {
    entry: Map<String, Value>,
    name: String,
    info: Converted,
}

/// How far a colour of a picture may land from its own when it shares a
/// palette that has no room left for it: two steps of the console's 31 in
/// each channel. The blends a picture's scaling leaves at its edges are
/// what it catches —Zounds' ten digits, three colours each in the file,
/// come out with more between them than a palette holds—.
pub const NEAR: i64 = 2;

/// The pictures' palettes: each picture goes in the first one that takes
/// its colours —those it has, the ones that fit in what is left of fifteen,
/// and the rest within [`NEAR`] of one it has—, or in a new one. Its
/// colours are tried in the order the picture uses them most, so what is
/// approximated is the least used. Each palette is a sprite palette from
/// the top, so how many there are is what the map's characters have to
/// leave. Answers the palettes, with each picture's indices moved to its
/// own and its `palette` in its entry.
///
/// **A number the map tones** —`tinted`, as the scan wrote it down— shares
/// only with itself: the console tones a picture by toning its palette, and
/// a picture beside it in the same palette would take the tone too. Its
/// pictures are never up at the same time, since a number holds one.
fn share_palettes(shown: &mut [Shown], tinted: &[i64]) -> Vec<Vec<[u8; 3]>> {
    let mut palettes: Vec<Vec<[u8; 3]>> = Vec::new();
    // Whose each palette is: None for anyone's, or a toned number's.
    let mut owners: Vec<Option<i64>> = Vec::new();
    for s in shown.iter_mut() {
        let own = s.info.palette.clone();
        let number = s.entry.get("number").map_or(0, int);
        let owner = tinted.contains(&number).then_some(number);
        let found = palettes
            .iter()
            .enumerate()
            .filter(|&(at, _)| owners[at] == owner)
            .find_map(|(at, p)| fit(p, &own).map(|(t, a)| (at, t, a)));
        let (at, to, added) = match found {
            Some(found) => found,
            None => {
                palettes.push(Vec::new());
                owners.push(owner);
                let (to, added) = fit(&[], &own).unwrap_or_default();
                (palettes.len() - 1, to, added)
            }
        };
        palettes[at].extend(added);
        for row in s.info.indices.iter_mut() {
            for v in row.iter_mut() {
                *v = to.get(*v as usize).copied().unwrap_or(0);
            }
        }
        s.entry.insert("palette".into(), json!(at));
    }
    palettes
}

/// How far apart two colours are: the most any channel differs.
fn far(a: &[u8; 3], b: &[u8; 3]) -> i64 {
    a.iter()
        .zip(b)
        .map(|(&x, &y)| (i64::from(x) - i64::from(y)).abs())
        .max()
        .unwrap_or(i64::MAX)
}

/// Where the colours `own` go in `palette`: each one's index from one —0
/// is the transparent—, and the colours it adds; None if one is too far
/// from every colour of a palette without room.
fn fit(palette: &[[u8; 3]], own: &[[u8; 3]]) -> Option<(Vec<i64>, Vec<[u8; 3]>)> {
    let mut added: Vec<[u8; 3]> = Vec::new();
    let mut to = vec![0i64];
    for c in own {
        let all: Vec<&[u8; 3]> = palette.iter().chain(added.iter()).collect();
        if let Some(k) = all.iter().position(|p| *p == c) {
            to.push(k as i64 + 1);
        } else if all.len() < COLORS as usize {
            to.push(all.len() as i64 + 1);
            added.push(*c);
        } else {
            let (k, d) = all
                .iter()
                .enumerate()
                .map(|(k, p)| (k, far(p, c)))
                .min_by_key(|&(_, d)| d)?;
            if d > NEAR {
                return None;
            }
            to.push(k as i64 + 1);
        }
    }
    Some((to, added))
}

/// The 8x8 cell of `info` at (`x`, `y`), its 64 indices; past the image,
/// index 0.
fn cell_at(info: &Converted, x: i64, y: i64) -> Vec<i64> {
    let mut cell = Vec::with_capacity(64);
    for py in 0..8 {
        for px in 0..8 {
            let (x, y) = (x + px, y + py);
            cell.push(if y < info.height && x < info.width {
                info.indices[y as usize][x as usize]
            } else {
                0
            });
        }
    }
    cell
}

/// A piece of a picture: a 32x32 object, one of the map's distinct blocks
/// of sixteen cells, or an 8x8 one, one of its distinct cells.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Piece {
    Block(usize),
    Cell(usize),
}

/// The tiles of the map's pictures, each distinct block and cell once: the
/// same file shown under two numbers, or ten digits that share a zero, take
/// their tiles once.
#[derive(Default)]
struct Bank {
    blocks: Vec<Vec<Vec<i64>>>,
    cells: Vec<Vec<i64>>,
}

impl Bank {
    /// The picture cut into pieces, row by row of 32x32 blocks, leaving out
    /// what has nothing drawn: `(dx, dy, piece)`. A block with
    /// [`SMALL_CELLS`] cells drawn or fewer goes as those cells, and so does
    /// a thin one: see [`THIN_CELLS`].
    fn cut(&mut self, info: &Converted) -> Vec<(i64, i64, Piece)> {
        let mut out = Vec::new();
        let mut oy = 0;
        while oy < info.height {
            let mut ox = 0;
            while ox < info.width {
                let cells: Vec<Vec<i64>> = (0..OBJ_SIDE * OBJ_SIDE)
                    .map(|k| cell_at(info, ox + (k % OBJ_SIDE) * 8, oy + (k / OBJ_SIDE) * 8))
                    .collect();
                let drawn: Vec<usize> = (0..cells.len())
                    .filter(|&k| cells[k].iter().any(|&v| v != 0))
                    .collect();
                if !as_cells(&drawn) {
                    let at = self
                        .blocks
                        .iter()
                        .position(|b| *b == cells)
                        .unwrap_or_else(|| {
                            self.blocks.push(cells.clone());
                            self.blocks.len() - 1
                        });
                    out.push((ox, oy, Piece::Block(at)));
                } else {
                    for k in drawn {
                        let at = self
                            .cells
                            .iter()
                            .position(|c| *c == cells[k])
                            .unwrap_or_else(|| {
                                self.cells.push(cells[k].clone());
                                self.cells.len() - 1
                            });
                        let k = k as i64;
                        out.push((
                            ox + (k % OBJ_SIDE) * 8,
                            oy + (k / OBJ_SIDE) * 8,
                            Piece::Cell(at),
                        ));
                    }
                }
                ox += OBJ;
            }
            oy += OBJ;
        }
        out
    }

    /// Where each distinct cell goes, from the pictures' base: the blocks
    /// fill rows of the name grid four to a row, and the cells go first in
    /// what the last row of blocks leaves free to its right, then after it.
    fn cell_tiles(&self) -> Vec<i64> {
        let blocks = self.blocks.len() as i64;
        let mut free = Vec::new();
        if blocks % 4 != 0 {
            let row = blocks / 4;
            for gy in 0..OBJ_SIDE {
                for gx in (blocks % 4) * OBJ_SIDE..GRID {
                    free.push(row * BLOCK_ROW + gy * GRID + gx);
                }
            }
        }
        let after = -((-blocks).div_euclid(4)) * BLOCK_ROW;
        (0..self.cells.len() as i64)
            .map(|i| {
                free.get(i as usize)
                    .copied()
                    .unwrap_or(after + i - free.len() as i64)
            })
            .collect()
    }

    /// Every tile of the pictures as `[tile, cell]`, and how many tiles from
    /// the base they reserve.
    fn tiles(&self) -> (Vec<(usize, Vec<u8>)>, i64) {
        let mut out = Vec::new();
        let mut end = 0;
        // A cell's colour indices, which are a palette's: one byte each.
        let indices = |cell: &[i64]| cell.iter().map(|&i| i as u8).collect();
        for (b, cells) in self.blocks.iter().enumerate() {
            let start = block_tile(b as i64);
            for (k, cell) in cells.iter().enumerate() {
                let k = k as i64;
                let tile = start + (k / OBJ_SIDE) * GRID + k % OBJ_SIDE;
                out.push((tile as usize, indices(cell)));
                end = end.max(-((-(b as i64 + 1)).div_euclid(4)) * BLOCK_ROW);
            }
        }
        for (tile, cell) in self.cell_tiles().into_iter().zip(&self.cells) {
            out.push((tile as usize, indices(cell)));
            end = end.max(tile + 1);
        }
        (out, end)
    }

    /// A piece's tile word: its tile from the base, and [`SMALL_BIT`] for an
    /// 8x8 one.
    fn word(&self, piece: Piece, cell_tiles: &[i64]) -> i64 {
        match piece {
            Piece::Block(b) => block_tile(b as i64),
            Piece::Cell(c) => cell_tiles[c] | SMALL_BIT,
        }
    }
}

/// A picture whose file is missing, that does not fit the plane, or whose
/// number is past the console's slots, is left out, and its commands are
/// accepted without being done.
pub fn for_map(
    game_dir: &Path,
    keys: &[Key],
    tinted: &[i64],
    whose: &str,
    cropped: &Cropped,
) -> Result<Option<ForMap>> {
    let mut slots: Vec<i64> = Vec::new();
    let mut shown: Vec<Shown> = Vec::new();
    for key in keys {
        let number = i64::from(key.number);
        let name = key.name.as_str();
        // The big ones are `big_for_map`'s, and take no slot.
        let Some(path) = file_of(game_dir, key) else {
            continue;
        };
        if is_big(&path, key, cropped)? {
            continue;
        }
        let info = convert(&path, key, cropped.for_console(name))?;
        if !takes(&info, key) {
            println!(
                "  {whose}: the picture {} is {}x{} on the console: bigger than the plane of objects",
                crate::text::quoted(name),
                info.width,
                info.height
            );
            continue;
        }
        if !slots.contains(&number) {
            if slots.len() == SLOTS {
                println!(
                    "  {whose}: the picture {} (number {number}) doesn't go in: the console keeps {SLOTS} at a time",
                    crate::text::quoted(name)
                );
                continue;
            }
            slots.push(number);
        }
        if let Some((cx, cy)) = key.at.map(wide).filter(|_| !key.with_map) {
            // The corner the console computes from the centre and the half
            // size —`pic_show`— has to be the one the picture was converted
            // at: the same floor of four fifths and fourteen fifteenths.
            let (hw, hh) = info.half;
            let expected = (
                ((cx - hw) * WIDTH).div_euclid(RM_WIDTH),
                ((cy - hh) * HEIGHT).div_euclid(RM_HEIGHT),
            );
            if (info.x, info.y) != expected {
                crate::stop!(
                    "{}: converted at ({}, {}) and the console puts it at {expected:?}",
                    json!(key),
                    info.x,
                    info.y
                );
            }
        }
        shown.push(Shown {
            entry: entry_of(key),
            name: name.to_string(),
            info,
        });
    }
    if shown.is_empty() {
        return Ok(None);
    }
    // The highest number in slot 0: OAM puts the lowest index in front, and
    // RM2k the highest number.
    slots.sort_by(|a, b| b.cmp(a));
    for s in shown.iter_mut() {
        let number = int(&s.entry["number"]);
        let slot = slots.iter().position(|n| *n == number).unwrap();
        s.entry.insert("slot".into(), json!(slot));
    }
    let palettes = share_palettes(&mut shown, tinted);
    let mut bank = Bank::default();
    let cuts: Vec<Vec<(i64, i64, Piece)>> = shown.iter().map(|s| bank.cut(&s.info)).collect();
    let cell_tiles = bank.cell_tiles();
    let (cells, tiles) = bank.tiles();
    let mut images = Vec::new();
    let mut objects = 0;
    for (s, cut) in shown.iter().zip(&cuts) {
        let palette = int(&s.entry["palette"]);
        // `behind_map`: a picture under a lower number than one its map
        // draws opaque —`map_pictures`, which `maps.rs` marks— goes at the
        // characters' priority, behind the cells that one raised, as RM2k
        // shows a lower number under a higher one. Desert Nightmare's dog
        // runs behind a warehouse that way, on map 11: picture 1 under
        // picture 2, the warehouse's roof. What it loses is RM2k's "over
        // everything": it goes behind the ChipSet's layer above the hero
        // too, and the events above the hero go over it.
        images.push(PictureImage {
            half: [s.info.half.0, s.info.half.1],
            objects: cut
                .iter()
                .map(|&(dx, dy, piece)| [dx, dy, bank.word(piece, &cell_tiles)])
                .collect(),
            palette: palettes[palette as usize].clone(),
            palette_index: palette,
            behind_map: s.entry.get("behind_map") == Some(&json!(true)),
        });
        objects += cut.len();
    }
    let names: Vec<&str> = shown.iter().map(|s| s.name.as_str()).collect();
    let name = names.join(", ");
    let table = shown.into_iter().map(|s| Value::Object(s.entry)).collect();
    Ok(Some(ForMap {
        name,
        objects,
        tiles,
        cells,
        palettes: palettes.len(),
        table,
        images,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn project(graphics: &str) -> Project {
        Project::from_text(Path::new("/nowhere"), &format!("[graphics]\n{graphics}\n")).unwrap()
    }

    /// The Book of Three's map 72, shrunk: the screen tinted black, two
    /// quotes shown over it; then the tint back and one more, which is not
    /// over black; and in another page one by a variable after its own
    /// black tint, which the layer cannot place.
    #[test]
    fn the_pictures_over_black_are_the_ones_after_a_black_tint_in_their_page() {
        use crate::game::{Command, Event, Page};
        let c = |code: i32, string: &str, parameters: &[i32]| Command {
            code,
            indent: 0,
            string: string.to_string(),
            parameters: parameters.to_vec(),
        };
        let show = |name: &str, by_variable: i32| {
            c(
                SHOW_PICTURE,
                name,
                &[
                    20,
                    by_variable,
                    160,
                    120,
                    0,
                    100,
                    100,
                    1,
                    100,
                    100,
                    100,
                    100,
                    0,
                    0,
                ],
            )
        };
        let page = |commands: Vec<Command>| Page {
            id: 1,
            character_name: String::new(),
            dump_name: String::new(),
            character_index: 0,
            direction: 2,
            pattern: 1,
            layer: 0,
            animation_type: 0,
            translucent: false,
            trigger: 0,
            commands,
        };
        let black = c(TINT_SCREEN, "", &[0, 0, 0, 100, 50, 1]);
        let map = GameMap {
            id: 72,
            chipset_id: 1,
            width: 20,
            height: 15,
            scroll_type: 0,
            events: vec![Event {
                id: 4,
                x: 0,
                y: 0,
                pages: vec![
                    page(vec![
                        show("Before", 0),
                        black.clone(),
                        show("Quote1", 0),
                        show("quote2", 0),
                        c(TINT_SCREEN, "", &[100, 100, 100, 100, 50, 1]),
                        show("After", 0),
                    ]),
                    page(vec![black, show("Placed", 1)]),
                ],
            }],
            lower_layer: Vec::new(),
            upper_layer: Vec::new(),
            twins: Vec::new(),
        };
        let found = over_black(&map);
        assert_eq!(
            found,
            BTreeSet::from([(20, "quote1".to_string()), (20, "quote2".to_string())])
        );
        let key = Key::from(PictureKey {
            number: 20,
            name: "QUOTE1".into(),
            ..PictureKey::default()
        });
        assert!(shown_in(&key, &found));
    }

    /// Desert Nightmare's map 11, shrunk: the dog runs as picture 1 with the
    /// map by variables 14 and 15, and the hit one is shown by the same ones
    /// with the screen. Another number by other variables, or the map
    /// bigger than RM2k's screen, or looping, and it is not.
    #[test]
    fn a_screen_picture_by_the_variables_of_one_with_the_map_goes_with_it() {
        use crate::game::{Command, Event, Page};
        let show = |number: i32, name: &str, vars: (i32, i32), with_map: bool| Command {
            code: SHOW_PICTURE,
            indent: 0,
            string: name.to_string(),
            parameters: vec![
                number,
                1,
                vars.0,
                vars.1,
                i32::from(with_map),
                100,
                0,
                1,
                100,
                100,
                100,
                100,
                0,
                0,
            ],
        };
        let map = |width: i32, scroll_type: i32, commands: Vec<Command>| GameMap {
            id: 11,
            chipset_id: 1,
            width,
            height: 15,
            scroll_type,
            events: vec![Event {
                id: 80,
                x: 0,
                y: 0,
                pages: vec![Page {
                    id: 1,
                    character_name: String::new(),
                    dump_name: String::new(),
                    character_index: 0,
                    direction: 2,
                    pattern: 1,
                    layer: 0,
                    animation_type: 0,
                    translucent: false,
                    trigger: 3,
                    commands,
                }],
            }],
            lower_layer: Vec::new(),
            upper_layer: Vec::new(),
            twins: Vec::new(),
        };
        let dog = || {
            vec![
                show(1, "Hund_Animation1", (14, 15), true),
                show(1, "Hund_Animation4", (14, 15), false),
                show(3, "Selector", (14, 15), false),
                show(1, "Elsewhere", (16, 17), false),
            ]
        };
        let found = screen_on_map(&map(20, 0, dog()));
        assert_eq!(found, BTreeSet::from([(1, "hund_animation4".to_string())]));
        let key = Key::from(PictureKey {
            number: 1,
            name: "Hund_Animation4".into(),
            by_variable: true,
            ..PictureKey::default()
        });
        assert!(screen_on_map_in(&key, &found));
        assert!(screen_on_map(&map(21, 0, dog())).is_empty());
        assert!(screen_on_map(&map(20, 3, dog())).is_empty());
        // Shown by other variables too, it is not: it would land apart.
        let mut twice = dog();
        twice.push(show(1, "Hund_Animation4", (16, 17), false));
        assert!(screen_on_map(&map(20, 0, twice)).is_empty());
    }

    /// Zounds' map 190, shrunk: the frame shown once, still, over the
    /// panorama; a selector at half transparency; a picture moved; and one
    /// shown twice, the second time toned.
    #[test]
    fn the_pictures_still_over_a_panorama_are_shown_untouched_and_never_moved() {
        use crate::game::{Command, Event, Page};
        let c = |code: i32, string: &str, parameters: &[i32]| Command {
            code,
            indent: 0,
            string: string.to_string(),
            parameters: parameters.to_vec(),
        };
        // Number, by variable, place, with the map, zoom, transparency,
        // transparent colour, tone, effect, and 2003's tail: the bottom's
        // transparency at 14.
        let show = |number: i32, name: &str, transparency: i32, red: i32| {
            c(
                SHOW_PICTURE,
                name,
                &[
                    number,
                    0,
                    160,
                    120,
                    0,
                    100,
                    transparency,
                    1,
                    red,
                    100,
                    100,
                    100,
                    0,
                    0,
                    transparency,
                    68,
                ],
            )
        };
        let page = |commands: Vec<Command>| Page {
            id: 1,
            character_name: String::new(),
            dump_name: String::new(),
            character_index: 0,
            direction: 2,
            pattern: 1,
            layer: 0,
            animation_type: 0,
            translucent: false,
            trigger: 0,
            commands,
        };
        let map = |commands: Vec<Command>| GameMap {
            id: 190,
            chipset_id: 1,
            width: 20,
            height: 15,
            scroll_type: 0,
            events: vec![Event {
                id: 1,
                x: 0,
                y: 0,
                pages: vec![page(commands)],
            }],
            lower_layer: Vec::new(),
            upper_layer: Vec::new(),
            twins: Vec::new(),
        };
        let screen = map(vec![
            show(48, "Box", 0, 100),
            show(49, "Bright", 50, 100),
            show(30, "Moved", 0, 100),
            c(
                MOVE_PICTURE,
                "",
                &[30, 0, 0, 0, 100, 0, 100, 100, 100, 100, 0, 0, 10, 0],
            ),
            show(31, "Toned", 0, 100),
            show(31, "Toned", 0, 50),
        ]);
        assert_eq!(
            still_over(&screen),
            BTreeSet::from([(48, "box".to_string())])
        );
        // A map that swaps its panorama shows none of them over it.
        let swapped = map(vec![
            show(48, "Box", 0, 100),
            c(CHANGE_PBG, "Other", &[0, 0, 0, 0, 0, 0]),
        ]);
        assert!(still_over(&swapped).is_empty());
    }

    #[test]
    fn a_frame_s_edges_and_a_line_of_text_go_as_cells_and_a_band_whole() {
        // Cells are numbered row by row, four to a row.
        let row = |r: usize| -> Vec<usize> { (0..4).map(|c| 4 * r + c).collect() };
        // Four or fewer, as always.
        assert!(as_cells(&[0, 5, 10, 15]));
        // A frame's top and bottom edge: rows 0 and 3, eight cells.
        assert!(as_cells(&[row(0), row(3)].concat()));
        // A line of text over two rows, not all of them drawn.
        assert!(as_cells(&[1, 2, 3, 5, 6, 7]));
        // Two whole rows side by side: one 32x32 costs the same slivers.
        assert!(!as_cells(&[row(1), row(2)].concat()));
        // Three rows, or more than eight cells: a block.
        assert!(!as_cells(&[0, 4, 8, 12, 1]));
        assert!(!as_cells(&[row(0), row(3), vec![5]].concat()));
    }

    #[test]
    fn the_cropped_pictures_are_found_without_minding_case() {
        let cropped = Cropped::read(&project("cropped_pictures = { PhotoA = [8, 16] }")).unwrap();
        assert_eq!(cropped.of("photoa"), Some((8, 16)));
        assert_eq!(cropped.of("PHOTOA"), Some((8, 16)));
        assert_eq!(cropped.of("PhotoB"), None);
        assert!(Cropped::read(&project("cropped_pictures = {}"))
            .unwrap()
            .of("PhotoA")
            .is_none());
    }

    #[test]
    fn the_pictures_drawn_for_the_console_are_named_and_optional() {
        let p = project("cropped_pictures = {}\nconsole_pictures = [\"MenuA\"]");
        let cropped = Cropped::read(&p).unwrap();
        assert!(cropped.for_console("menua"));
        assert!(!cropped.for_console("MenuB"));
        // Without the list, none: the projects that predate it.
        let none = Cropped::read(&project("cropped_pictures = {}")).unwrap();
        assert!(!none.for_console("MenuA"));
    }

    #[test]
    fn a_crop_is_two_numbers_and_the_table_is_declared() {
        for bad in [
            "{ PhotoA = [8] }",
            "{ PhotoA = [8, \"16\"] }",
            "{ PhotoA = 8 }",
        ] {
            let e = Cropped::read(&project(&format!("cropped_pictures = {bad}"))).unwrap_err();
            assert!(
                e.to_string().contains("graphics.cropped_pictures.PhotoA"),
                "{e}"
            );
        }
        let e = Cropped::read(&project("opaque = []")).unwrap_err();
        assert!(e.to_string().contains("graphics.cropped_pictures"), "{e}");
    }

    #[test]
    fn a_layer_has_a_texture_only_on_the_maps_that_zoom_it() {
        // The same photo on three maps: still on the first, zoomed on the
        // second; and another one, still, on the third.
        let key = |name: &str| {
            Key::from(PictureKey {
                number: 20,
                name: name.into(),
                zoom: 100,
                transparent_color: true,
                ..PictureKey::default()
            })
        };
        let layer = |texture: bool| json!({"center": [160, 120], "tiles": "00", "mode7": if texture { json!({"map": []}) } else { Value::Null }});
        let still = [Big {
            key: key("Photo"),
            layer: layer(false),
        }];
        let zoomed = [Big {
            key: key("Photo"),
            layer: layer(true),
        }];
        let other = [Big {
            key: key("Other"),
            layer: layer(false),
        }];
        let (layers, tables) = number_big(&[&still, &zoomed, &other, &still]);
        assert_eq!(layers.len(), 3);
        assert!(!textured(&layers[0]) && textured(&layers[1]) && !textured(&layers[2]));
        // Desert Nightmare's black screen, which one map zooms: shown still
        // with the texture, it hid the window of every message over it.
        assert_eq!(tables[0][0]["image"], 0);
        assert!(
            tables[0][0].get("texture").is_none(),
            "the map that shows it still goes without the texture"
        );
        assert_eq!(tables[1][0]["image"], 1);
        assert_eq!(tables[1][0]["texture"], true);
        assert!(tables[2][0].get("texture").is_none());
        assert_eq!(
            tables[3][0]["image"], 0,
            "and the still one is a single layer"
        );
        // Which moves zoom: another size than the one shown, under its number.
        let zooms = [json!([20, 100]), json!([3, 0])];
        assert!(!moved_to_another_size(&key("Photo"), &zooms));
        assert!(moved_to_another_size(&key("Photo"), &[json!([20, 0])]));
    }

    #[test]
    fn a_zoom_rounds_and_never_gives_zero() {
        assert_eq!(zoomed(233, 100), 233);
        assert_eq!(zoomed(10, 55), 6);
        assert_eq!(zoomed(1, 10), 1);
    }

    #[test]
    fn a_row_of_blocks_fits_four_objects() {
        assert_eq!(block_tile(0), 0);
        assert_eq!(block_tile(1), 4);
        assert_eq!(block_tile(3), 12);
        assert_eq!(block_tile(4), 64);
        assert_eq!(block_tile(5), 68);
    }

    fn info(
        width: i64,
        height: i64,
        palette: Vec<[u8; 3]>,
        drawn: &[(usize, usize, i64)],
    ) -> Converted {
        let mut indices = vec![vec![0i64; width as usize]; height as usize];
        for &(x, y, v) in drawn {
            indices[y][x] = v;
        }
        Converted {
            x: 0,
            y: 0,
            width,
            height,
            half: (width / 2, height / 2),
            palette,
            indices,
        }
    }

    #[test]
    fn a_sparse_block_goes_as_cells_and_a_full_one_whole() {
        // 40x8: the first block has one cell drawn, the second (from x = 32)
        // one too; and a 32x32 with all sixteen.
        let sparse = info(40, 8, vec![[0, 0, 0], [8, 8, 8]], &[(0, 0, 1), (39, 7, 2)]);
        let full: Vec<(usize, usize, i64)> = (0..32)
            .flat_map(|y| (0..32).map(move |x| (x, y, 1)))
            .collect();
        let full = info(32, 32, vec![[0, 0, 0]], &full);
        let mut bank = Bank::default();
        let cut = bank.cut(&sparse);
        assert_eq!(cut, [(0, 0, Piece::Cell(0)), (32, 0, Piece::Cell(1))]);
        assert_eq!(bank.cut(&full), [(0, 0, Piece::Block(0))]);
        // The same picture again takes no tiles of its own.
        assert_eq!(bank.cut(&sparse), cut);
        assert_eq!((bank.blocks.len(), bank.cells.len()), (1, 2));
        // The two cells go right of the block, in its row of the grid; the
        // block reserves its whole row of blocks.
        assert_eq!(bank.cell_tiles(), [4, 5]);
        let (tiles, end) = bank.tiles();
        assert_eq!(tiles.len(), 16 + 2);
        assert_eq!(end, BLOCK_ROW);
        assert_eq!(bank.word(Piece::Cell(1), &bank.cell_tiles()), 5 | SMALL_BIT);
        assert_eq!(bank.word(Piece::Block(0), &bank.cell_tiles()), 0);
        // What falls past the image is transparent.
        assert_eq!(bank.cells[1][63], 2);
        assert!(fits(&sparse));
    }

    #[test]
    fn cells_without_blocks_start_at_the_base_and_four_blocks_leave_no_gap() {
        let mut bank = Bank {
            blocks: vec![Vec::new(); 4],
            cells: vec![Vec::new(); 2],
        };
        assert_eq!(bank.cell_tiles(), [BLOCK_ROW, BLOCK_ROW + 1]);
        bank.blocks.clear();
        assert_eq!(bank.cell_tiles(), [0, 1]);
    }

    #[test]
    fn pictures_whose_colours_fit_together_share_a_palette() {
        let shown = |palette: Vec<[u8; 3]>| Shown {
            entry: Map::new(),
            name: String::new(),
            info: info(8, 8, palette, &[(0, 0, 1), (1, 0, 2)]),
        };
        let fifteen = || (0..15).map(|k| [k, 0, 0]).collect::<Vec<_>>();
        let mut pictures = vec![
            shown(vec![[1, 1, 1], [2, 2, 2]]),
            shown(vec![[2, 2, 2], [3, 3, 3]]),
            shown(fifteen()),
        ];
        let palettes = share_palettes(&mut pictures, &[]);
        assert_eq!(palettes.len(), 2);
        assert_eq!(palettes[0], [[1, 1, 1], [2, 2, 2], [3, 3, 3]]);
        assert_eq!(pictures[1].entry["palette"], 0);
        assert_eq!(pictures[2].entry["palette"], 1);
        // The second one's indices are the shared palette's: its first
        // colour is the first one's second.
        assert_eq!(pictures[1].info.indices[0][..2], [2, 3]);
        // A full palette takes a colour within two steps of one it has.
        let mut near = fifteen();
        near[1] = [16, 2, 1];
        let mut pictures = vec![shown(fifteen()), shown(near)];
        assert_eq!(share_palettes(&mut pictures, &[]).len(), 1);
        assert_eq!(
            pictures[1].info.indices[0][..2],
            [1, 15],
            "[16, 2, 1] drawn as [14, 0, 0]"
        );
        let mut pictures = vec![shown(fifteen()), shown(vec![[0, 0, 0], [20, 20, 20]])];
        assert_eq!(
            share_palettes(&mut pictures, &[]).len(),
            2,
            "but not one three steps away or more"
        );
        // A toned number has its own, which its other pictures share.
        let numbered = |number: i64| {
            let mut s = shown(vec![[1, 1, 1]]);
            s.entry.insert("number".into(), json!(number));
            s
        };
        let mut pictures = vec![numbered(1), numbered(3), numbered(2), numbered(3)];
        assert_eq!(share_palettes(&mut pictures, &[3]).len(), 2);
        let palettes: Vec<Value> = pictures
            .iter()
            .map(|p| p.entry["palette"].clone())
            .collect();
        assert_eq!(palettes, [json!(0), json!(1), json!(0), json!(1)]);
    }
}
