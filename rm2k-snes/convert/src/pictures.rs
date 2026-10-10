//! The pictures of `ShowPicture`: which ones each map carries, and how.
//!
//! **The small ones go in OAM objects**, after the map's characters in its
//! sprite bank: the picture is put up and taken down without touching
//! anything underneath, which is also what RM2k does, at the price of
//! fifteen colours —a sprite palette— and the per-line object budget. The
//! map has to have room for them, and `wally` says whether it did; the one
//! that did not is accepted without being done. The console keeps up to
//! [`SLOTS`] at a time, one per RM2k picture number, each with a palette.
//!
//! **The big ones go in BG1, in mode 1, while they are shown**, with the
//! map hidden: a picture that goes with the screen and does not fit the
//! objects, or one that goes with the map and covers the whole screen.
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
use crate::images;
use rm2k_project::Project;
use serde_json::{json, Map, Value};
use std::collections::HashMap;
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
/// How many pictures the console keeps at a time: `PIC_SLOTS` in the
/// runtime's `picture.s`.
pub const SLOTS: usize = 2;
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

/// The pictures the game crops instead of scaling, by name in lowercase
/// —RM2k finds a file without minding its case—, each with the pixel the
/// console's screen is cut from.
#[derive(Debug, Clone, Default)]
pub struct Cropped(HashMap<String, (i64, i64)>);

impl Cropped {
    /// `[graphics] cropped_pictures`: a table of `name = [x, y]`.
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
        Ok(Cropped(out))
    }

    /// Where the console's screen is cut from `name`, if it is cropped.
    pub fn of(&self, name: &str) -> Option<(i64, i64)> {
        self.0.get(&name.to_lowercase()).copied()
    }
}

/// The file of the picture `name`, or None if the game does not have it.
/// Without regard to case, as RPG_RT finds it.
pub fn path_of(game_dir: &Path, name: &str) -> Option<PathBuf> {
    crate::resources::find(&[game_dir], "Picture", name, &[".png"]).map(|p| rm2k_project::absolute(&p))
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

/// A picture converted, as the stage answers it plus half its size in
/// RM2k's pixels.
struct Converted {
    x: i64,
    y: i64,
    width: i64,
    height: i64,
    half: (i64, i64),
    palette: Value,
    indices: Vec<Vec<i64>>,
}

fn convert(path: &Path, key: &Value) -> Result<Converted> {
    let (width, height) = png_size(path)?;
    let zoom = int(&key["zoom"]);
    let (zw, zh) = (zoomed(width, zoom), zoomed(height, zoom));
    let (cx, cy) = match key["at"].as_array() {
        Some(at) => (int(&at[0]), int(&at[1])),
        // Placed by variables, or with the map: converted with its corner
        // on the grid, which is where the size comes out exact.
        None => (zw.div_euclid(2), zh.div_euclid(2)),
    };
    let a = images::picture(
        path,
        truthy(&key["transparent_color"]),
        0,
        cx,
        cy,
        COLORS,
        zoom,
        key["map_fixed"].as_bool().unwrap_or(false),
    )?;
    let indices = a["indices"]
        .as_array()
        .map(|rows| {
            rows.iter()
                .map(|r| r.as_array().map(|r| r.iter().map(int).collect()).unwrap_or_default())
                .collect()
        })
        .unwrap_or_default();
    Ok(Converted {
        x: int(&a["x"]),
        y: int(&a["y"]),
        width: int(&a["width"]),
        height: int(&a["height"]),
        half: (zw.div_euclid(2), zh.div_euclid(2)),
        palette: a["palette"].clone(),
        indices,
    })
}

fn truthy(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().unwrap_or(0.0) != 0.0,
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
        Value::Null => false,
    }
}

/// Whether the picture fits the plane of objects.
fn fits(info: &Converted) -> bool {
    0 < info.width
        && info.width <= WIDTH_MAX
        && 0 < info.height
        && info.height <= HEIGHT_MAX
        && info.palette.as_array().is_some_and(|p| !p.is_empty())
}

/// The picture cut into 32x32 objects, row by row, leaving out the ones
/// with nothing drawn: `(dx, dy, cells)`, with `cells` the sixteen 8x8
/// cells of the object. What falls outside the image is index 0.
fn objects(info: &Converted) -> Vec<(i64, i64, Vec<Vec<i64>>)> {
    let mut out = Vec::new();
    let mut oy = 0;
    while oy < info.height {
        let mut ox = 0;
        while ox < info.width {
            let mut cells = Vec::new();
            for ty in 0..OBJ_SIDE {
                for tx in 0..OBJ_SIDE {
                    let mut cell = Vec::with_capacity(64);
                    for py in 0..8 {
                        let y = oy + ty * 8 + py;
                        for px in 0..8 {
                            let x = ox + tx * 8 + px;
                            cell.push(if y < info.height && x < info.width {
                                info.indices[y as usize][x as usize]
                            } else {
                                0
                            });
                        }
                    }
                    cells.push(cell);
                }
            }
            if cells.iter().any(|c| c.iter().any(|&v| v != 0)) {
                out.push((ox, oy, cells));
            }
            ox += OBJ;
        }
        oy += OBJ;
    }
    out
}

/// The first tile of object `block` of the pictures, from their base. A
/// 32x32 object reads four tiles from four consecutive rows of the name
/// grid, which is sixteen wide: a row of blocks fits four objects.
pub fn block_tile(block: i64) -> i64 {
    (block / 4) * (4 * GRID) + (block % 4) * OBJ_SIDE
}

/// The picture's size on the console's screen, as the plane of objects
/// would draw it: at its zoom, scaled unless it goes with the map.
fn on_console(path: &Path, key: &Value) -> Result<(i64, i64)> {
    let (width, height) = png_size(path)?;
    let zoom = int(&key["zoom"]);
    let (w, h) = (zoomed(width, zoom), zoomed(height, zoom));
    if truthy(&key["map_fixed"]) {
        return Ok((w, h));
    }
    let (cx, cy) = match key["at"].as_array() {
        None => (w.div_euclid(2), h.div_euclid(2)),
        Some(at) => (int(&at[0]), int(&at[1])),
    };
    let (x0, y0) = (cx - w.div_euclid(2), cy - h.div_euclid(2));
    Ok((
        ((x0 + w) * WIDTH).div_euclid(RM_WIDTH) - (x0 * WIDTH).div_euclid(RM_WIDTH),
        ((y0 + h) * HEIGHT).div_euclid(RM_HEIGHT) - (y0 * HEIGHT).div_euclid(RM_HEIGHT),
    ))
}

/// Whether the picture goes in the background layer: too big for the
/// objects, and either with the screen or covering it whole; or cropped,
/// which is the screen.
fn is_big(path: &Path, key: &Value, cropped: &Cropped) -> Result<bool> {
    if truthy(&key["by_variable"]) {
        return Ok(false);
    }
    if cropped.of(key["name"].as_str().unwrap_or("")).is_some() {
        return Ok(true);
    }
    let (w, h) = on_console(path, key)?;
    if w <= WIDTH_MAX && h <= HEIGHT_MAX {
        return Ok(false);
    }
    Ok(!truthy(&key["map_fixed"]) || (w >= WIDTH && h >= HEIGHT))
}

/// Where the layer is drawn from: the key's centre, or the screen's for
/// one that goes with the map, which covers it whole.
fn big_center(key: &Value) -> (i64, i64) {
    if truthy(&key["map_fixed"]) {
        return (RM_WIDTH / 2, RM_HEIGHT / 2);
    }
    let at = key["at"].as_array().cloned().unwrap_or_default();
    (at.first().map_or(0, int), at.get(1).map_or(0, int))
}

/// A big picture of a map: its key, and its layer as the stage answered
/// it with its half size and centre.
#[derive(Debug, Clone)]
pub struct Big {
    pub key: Value,
    pub layer: Value,
}

/// Whether a `MovePicture` of the map zooms the picture `key`: one under
/// its number that goes to another size than the one it was shown at.
/// `zooms` is what the scan wrote down, `[number, zoom]` per move.
fn moved_to_another_size(key: &Value, zooms: &[Value]) -> bool {
    zooms.iter().any(|z| int(&z[0]) == int(&key["number"]) && int(&z[1]) != int(&key["zoom"]))
}

/// The big pictures of `keys`. The ones that do not fit even cut to the
/// screen are left out, and their commands are accepted without being
/// done. The ones a move of the map zooms —`zooms`, as the scan wrote it
/// down— carry a mode 7 texture too, if they leave room for it.
pub fn big_for_map(
    game_dir: &Path,
    keys: &[Value],
    zooms: &[Value],
    map_id: i32,
    cropped: &Cropped,
) -> Result<Vec<Big>> {
    let mut out = Vec::new();
    for key in keys {
        let name = key["name"].as_str().unwrap_or("");
        let Some(path) = path_of(game_dir, name) else { continue };
        if !is_big(&path, key, cropped)? {
            continue;
        }
        let (cx, cy) = big_center(key);
        let zoom = int(&key["zoom"]);
        let layer = images::background(
            &path,
            truthy(&key["transparent_color"]),
            cx,
            cy,
            zoom,
            cropped.of(name),
            BIG_PALETTES,
            BIG_FIRST_PALETTE,
            BIG_TILES,
            BIG_ROWS,
            moved_to_another_size(key, zooms),
        )?;
        let Some(mut layer) = layer else {
            println!(
                "  map {map_id}: the picture {} doesn't fit the background layer even cut to the screen",
                crate::text::repr(name)
            );
            continue;
        };
        let (width, height) = png_size(&path)?;
        let object = layer.as_object_mut().ok_or_else(|| Stop::new("a layer is not an object"))?;
        object.insert(
            "half".into(),
            json!([zoomed(width, zoom).div_euclid(2), zoomed(height, zoom).div_euclid(2)]),
        );
        object.insert("center".into(), json!([cx, cy]));
        out.push(Big { key: key.clone(), layer });
    }
    Ok(out)
}

/// Whether a layer carries a mode 7 texture.
fn textured(layer: &Value) -> bool {
    layer.get("mode7").is_some_and(|t| !t.is_null())
}

/// The cartridge's big pictures, numbered: the layers, in the order the
/// maps meet them, and each map's table —each key with its layer's number,
/// its centre and whether it has a texture—, which the event compiler
/// numbers against. The same picture drawn the same way on two maps, or
/// under two numbers, is one layer; and **it has a texture if any of them
/// zooms it**: the other maps show it still, in mode 1, as before, from
/// the other half of VRAM.
pub fn number_big(maps: &[&[Big]]) -> (Vec<Value>, Vec<Vec<Value>>) {
    let mut layers: Vec<Value> = Vec::new();
    let mut index: HashMap<String, usize> = HashMap::new();
    let mut numbers: Vec<Vec<usize>> = Vec::new();
    for bigs in maps {
        let mut map = Vec::new();
        for big in bigs.iter() {
            let ident = json!([big.key["name"], big.key["zoom"], big.key["transparent_color"], big.layer["center"]])
                .to_string();
            let number = *index.entry(ident).or_insert_with(|| {
                layers.push(big.layer.clone());
                layers.len() - 1
            });
            if textured(&big.layer) && !textured(&layers[number]) {
                layers[number] = big.layer.clone();
            }
            map.push(number);
        }
        numbers.push(map);
    }
    let mut tables = Vec::new();
    for (bigs, map) in maps.iter().zip(&numbers) {
        let mut table = Vec::new();
        for (big, &number) in bigs.iter().zip(map) {
            let mut entry: Map<String, Value> = big.key.as_object().cloned().unwrap_or_default();
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
    if !layers.is_empty() {
        println!("  the cartridge carries {} big picture(s) in the background layer", layers.len());
    }
    (layers, tables)
}

/// What a map carries of the pictures the scan says it can show: what
/// `wally` reserves in the sprite bank (every picture's objects, as cells
/// from the base, and how many slots), what the event compiler numbers
/// against (each picture that went in, with its slot) and what the
/// emission writes (each one's half size, its objects and its colours).
#[derive(Debug, Clone)]
pub struct ForMap {
    pub asked: Value,
    pub table: Vec<Value>,
    pub images: Vec<Value>,
}

/// A picture whose file is missing, that does not fit the plane, or whose
/// number is past the console's slots, is left out, and its commands are
/// accepted without being done.
pub fn for_map(game_dir: &Path, keys: &[Value], map_id: i32, cropped: &Cropped) -> Result<Option<ForMap>> {
    let mut slots: Vec<(i64, usize)> = Vec::new();
    let (mut table, mut images, mut cells, mut names) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    let mut block = 0i64;
    for key in keys {
        let number = int(&key["number"]);
        let name = key["name"].as_str().unwrap_or("");
        // The big ones are `big_for_map`'s, and take no slot.
        let path = path_of(game_dir, name);
        if let Some(path) = &path {
            if is_big(path, key, cropped)? {
                continue;
            }
        }
        if !slots.iter().any(|(n, _)| *n == number) {
            if slots.len() == SLOTS {
                println!(
                    "  map {map_id}: the picture {} (number {number}) doesn't go in: the console keeps {SLOTS} at a time",
                    crate::text::repr(name)
                );
                continue;
            }
            slots.push((number, slots.len()));
        }
        let Some(path) = path else { continue };
        let info = convert(&path, key)?;
        if !fits(&info) {
            println!(
                "  map {map_id}: the picture {} is {}x{} on the console: bigger than the plane of objects",
                crate::text::repr(name),
                info.width,
                info.height
            );
            continue;
        }
        if let Some(at) = key["at"].as_array() {
            // The corner the console computes from the centre and the half
            // size —`pic_show`— has to be the one the picture was converted
            // at: the same floor of four fifths and fourteen fifteenths.
            let (cx, cy) = (int(&at[0]), int(&at[1]));
            let (hw, hh) = info.half;
            let expected = (
                ((cx - hw) * WIDTH).div_euclid(RM_WIDTH),
                ((cy - hh) * HEIGHT).div_euclid(RM_HEIGHT),
            );
            if (info.x, info.y) != expected {
                crate::stop!("{key}: converted at ({}, {}) and the console puts it at {expected:?}", info.x, info.y);
            }
        }
        let cut = objects(&info);
        let first = block;
        for (_dx, _dy, object_cells) in &cut {
            let start = block_tile(block);
            for (k, cell) in object_cells.iter().enumerate() {
                let k = k as i64;
                let tile = start + (k / OBJ_SIDE) * GRID + k % OBJ_SIDE;
                cells.push(json!([tile, cell]));
            }
            block += 1;
        }
        let slot = slots.iter().find(|(n, _)| *n == number).map(|(_, s)| *s).unwrap();
        let mut entry: Map<String, Value> = key.as_object().cloned().unwrap_or_default();
        entry.insert("slot".into(), json!(slot));
        table.push(Value::Object(entry));
        images.push(json!({
            "half": [info.half.0, info.half.1],
            "first": first,
            "objects": cut.iter().map(|(dx, dy, _)| json!([dx, dy])).collect::<Vec<_>>(),
            "palette": info.palette,
        }));
        names.push(name.to_string());
    }
    if table.is_empty() {
        return Ok(None);
    }
    let max_slot = table.iter().map(|t| int(&t["slot"])).max().unwrap_or(0);
    let asked = json!({
        "name": names.join(", "),
        "objects": block,
        "tiles": -((-block).div_euclid(4)) * BLOCK_ROW,
        "cells": cells,
        "slots": max_slot + 1,
    });
    Ok(Some(ForMap { asked, table, images }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn project(graphics: &str) -> Project {
        Project::from_text(Path::new("/nowhere"), &format!("[graphics]\n{graphics}\n")).unwrap()
    }

    #[test]
    fn the_cropped_pictures_are_found_without_minding_case() {
        let cropped = Cropped::read(&project("cropped_pictures = { PhotoA = [8, 16] }")).unwrap();
        assert_eq!(cropped.of("photoa"), Some((8, 16)));
        assert_eq!(cropped.of("PHOTOA"), Some((8, 16)));
        assert_eq!(cropped.of("PhotoB"), None);
        assert!(Cropped::read(&project("cropped_pictures = {}")).unwrap().of("PhotoA").is_none());
    }

    #[test]
    fn a_crop_is_two_numbers_and_the_table_is_declared() {
        for bad in ["{ PhotoA = [8] }", "{ PhotoA = [8, \"16\"] }", "{ PhotoA = 8 }"] {
            let e = Cropped::read(&project(&format!("cropped_pictures = {bad}"))).unwrap_err();
            assert!(e.to_string().contains("graphics.cropped_pictures.PhotoA"), "{e}");
        }
        let e = Cropped::read(&project("opaque = []")).unwrap_err();
        assert!(e.to_string().contains("graphics.cropped_pictures"), "{e}");
    }

    #[test]
    fn a_layer_has_a_texture_if_any_map_zooms_it() {
        // The same photo on three maps: still on the first, zoomed on the
        // second; and another one, still, on the third.
        let key = |name: &str| json!({"name": name, "zoom": 100, "transparent_color": true, "number": 20});
        let layer = |texture: bool| {
            json!({"center": [160, 120], "tiles": "00", "mode7": if texture { json!({"map": []}) } else { Value::Null }})
        };
        let still = [Big { key: key("Photo"), layer: layer(false) }];
        let zoomed = [Big { key: key("Photo"), layer: layer(true) }];
        let other = [Big { key: key("Other"), layer: layer(false) }];
        let (layers, tables) = number_big(&[&still, &zoomed, &other]);
        assert_eq!(layers.len(), 2);
        assert!(textured(&layers[0]) && !textured(&layers[1]));
        assert_eq!(tables[0][0]["image"], 0);
        assert_eq!(tables[0][0]["texture"], true, "the map that shows it still too");
        assert_eq!(tables[1][0]["texture"], true);
        assert!(tables[2][0].get("texture").is_none(), "and nothing for one that does not zoom");
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

    #[test]
    fn the_objects_with_nothing_drawn_are_left_out() {
        // 40x8: the first object has a pixel, the second (from x = 32) too,
        // and nothing is below.
        let mut indices = vec![vec![0i64; 40]; 8];
        indices[0][0] = 1;
        indices[7][39] = 2;
        let info = Converted { x: 0, y: 0, width: 40, height: 8, half: (20, 4), palette: json!([[0, 0, 0]]), indices };
        let cut = objects(&info);
        assert_eq!(cut.iter().map(|(x, y, _)| (*x, *y)).collect::<Vec<_>>(), [(0, 0), (32, 0)]);
        // The second object's pixel is at (7, 7) of its first cell, and
        // what falls past the image is transparent.
        assert_eq!(cut[1].2[0][63], 2);
        assert!(cut[1].2[1].iter().all(|&v| v == 0));
        assert!(fits(&info));
    }
}
