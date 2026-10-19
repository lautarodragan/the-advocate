//! The requests each subcommand reads, and the answers it writes.
//!
//! A request names the pictures —by path: finding a game's file, in its
//! folder or in the RTP, is the caller's— and carries the sizes the
//! cartridge decided. A relative path is relative to the request.

use crate::fail::{Bad, Result};
use crate::{animation, background, fullscreen, mode7, scene, show_picture};
use adeleine::Color;
use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

/// A request file, read into `T`, with its paths made absolute.
pub fn read<T: DeserializeOwned + Paths>(path: &Path) -> Result<T> {
    let whose = path.display();
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
    let mut request: T =
        serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
    let base = path.parent().unwrap_or(Path::new("."));
    request.resolve(base);
    Ok(request)
}

/// The paths of a request, which are made relative to its directory.
pub trait Paths {
    fn resolve(&mut self, base: &Path);
}

fn resolve(path: &mut PathBuf, base: &Path) {
    if path.is_relative() {
        *path = base.join(&*path);
    }
}

/// `fullscreen`: one picture, the screen's size and the cell's, and the
/// palette: how many colours and from which CGRAM entry.
#[derive(Deserialize)]
pub struct Fullscreen {
    pub file: PathBuf,
    pub width: usize,
    pub height: usize,
    pub cell: usize,
    pub first_color: usize,
    pub cap: usize,
}

impl Paths for Fullscreen {
    fn resolve(&mut self, base: &Path) {
        resolve(&mut self.file, base);
    }
}

/// `picture`: the file and what the `ShowPicture` says of it —its
/// transparent colour, its transparency, its centre on RM2k's screen—,
/// the two screens, and how many colours.
#[derive(Deserialize)]
pub struct ShowPicture {
    pub file: PathBuf,
    #[serde(default)]
    pub use_transparent_color: bool,
    #[serde(default)]
    pub top_trans: i32,
    pub x: i64,
    pub y: i64,
    pub rm_screen: (i64, i64),
    pub screen: (i64, i64),
    pub colors: usize,
    /// The zoom, in percent: 100 if it does not say.
    #[serde(default = "hundred")]
    pub zoom: i64,
    /// Whether the picture goes with the map: then it is not scaled to the
    /// console's screen, and its corner is relative to its centre.
    #[serde(default)]
    pub map_fixed: bool,
    /// Whether the picture was drawn for the console: then it is not
    /// scaled. See [`crate::show_picture`].
    #[serde(default)]
    pub for_console: bool,
}

/// `background`: the file and what the `ShowPicture` says of it, the two
/// screens, and the room the layer gets: how many palettes from which one,
/// how many tiles and how many rows of cells.
#[derive(Deserialize)]
pub struct Background {
    pub file: PathBuf,
    #[serde(default)]
    pub use_transparent_color: bool,
    pub x: i64,
    pub y: i64,
    pub rm_screen: (i64, i64),
    pub screen: (i64, i64),
    #[serde(default = "hundred")]
    pub zoom: i64,
    /// The pixel of the picture the console's screen is cut from, instead
    /// of scaling it; absent, it is scaled.
    #[serde(default)]
    pub crop: Option<(i64, i64)>,
    /// Whether the picture was drawn for the console: then it is not
    /// scaled. See [`crate::show_picture`].
    #[serde(default)]
    pub for_console: bool,
    pub palettes: usize,
    pub first_palette: usize,
    pub tiles: usize,
    pub rows: usize,
    /// The layer as a mode 7 texture too, if it fits this; absent, not.
    #[serde(default)]
    pub mode7: Option<Mode7Room>,
}

/// What the console grants a layer that is also a mode 7 texture: the tiles
/// the texture's map names, the blank one included, and how many tiles and
/// rows of cells the layer itself can take while the texture shares VRAM
/// with it.
#[derive(Deserialize, Clone, Copy)]
pub struct Mode7Room {
    pub tiles: usize,
    pub layer_tiles: usize,
    pub layer_rows: usize,
}

impl Paths for Background {
    fn resolve(&mut self, base: &Path) {
        resolve(&mut self.file, base);
    }
}

fn hundred() -> i64 {
    100
}

impl Paths for ShowPicture {
    fn resolve(&mut self, base: &Path) {
        resolve(&mut self.file, base);
    }
}

/// The scene's geometry, as `scene::Geometry` names it.
#[derive(Deserialize, Clone, Copy)]
pub struct Scene {
    pub width: usize,
    pub height: usize,
    pub colors: usize,
    pub cgram_base: usize,
    pub light_scale: usize,
    pub light_colors: usize,
    pub scale: (i64, i64),
    pub battler_colors: usize,
    pub alpha_min: u8,
}

impl From<Scene> for scene::Geometry {
    fn from(s: Scene) -> Self {
        scene::Geometry {
            width: s.width,
            height: s.height,
            colors: s.colors,
            cgram_base: s.cgram_base,
            light_scale: s.light_scale,
            light_colors: s.light_colors,
            scale: s.scale,
            battler_colors: s.battler_colors,
            alpha_min: s.alpha_min,
        }
    }
}

/// `backdrops`: each backdrop's file, and which of its two versions are
/// wanted.
#[derive(Deserialize)]
pub struct Backdrops {
    pub scene: Scene,
    pub backdrops: Vec<BackdropWanted>,
}

#[derive(Deserialize)]
pub struct BackdropWanted {
    pub file: PathBuf,
    #[serde(default)]
    pub quality: bool,
    #[serde(default)]
    pub light: bool,
}

impl Paths for Backdrops {
    fn resolve(&mut self, base: &Path) {
        for b in &mut self.backdrops {
            resolve(&mut b.file, base);
        }
    }
}

/// `battlers`: each battler's file and its `battler_hue`.
#[derive(Deserialize)]
pub struct Battlers {
    pub scene: Scene,
    pub battlers: Vec<BattlerWanted>,
}

#[derive(Deserialize)]
pub struct BattlerWanted {
    pub file: PathBuf,
    #[serde(default)]
    pub hue: i32,
}

impl Paths for Battlers {
    fn resolve(&mut self, base: &Path) {
        for b in &mut self.battlers {
            resolve(&mut b.file, base);
        }
    }
}

/// `animations`: the box, and each animation by its number in the dump
/// with the sheet its cells are cut from.
#[derive(Deserialize)]
pub struct Animations {
    pub side: usize,
    pub colors: usize,
    pub alpha_min: u8,
    pub animations: Vec<AnimationWanted>,
}

#[derive(Deserialize)]
pub struct AnimationWanted {
    pub number: i32,
    pub sheet: PathBuf,
}

impl Paths for Animations {
    fn resolve(&mut self, base: &Path) {
        for a in &mut self.animations {
            resolve(&mut a.sheet, base);
        }
    }
}

impl From<&Animations> for animation::Geometry {
    fn from(a: &Animations) -> Self {
        animation::Geometry {
            side: a.side,
            colors: a.colors,
            alpha_min: a.alpha_min,
        }
    }
}

fn colors(palette: &[Color]) -> Value {
    json!(palette)
}

pub fn fullscreen_answer(s: &fullscreen::Screen) -> Value {
    json!({"tiles": s.tiles, "palette": colors(&s.palette), "tilemap": s.tilemap})
}

pub fn picture_answer(p: &show_picture::Converted) -> Value {
    json!({"x": p.x, "y": p.y, "width": p.width, "height": p.height,
           "palette": colors(&p.palette), "indices": p.indices})
}

pub fn background_answer(b: &background::Background, texture: Option<&mode7::Texture>) -> Value {
    let hex = |bytes: &[u8]| -> String { bytes.iter().map(|v| format!("{v:02x}")).collect() };
    let mut answer = json!({
        "top": b.top, "rows": b.rows, "columns": b.columns, "wider": b.wider,
        "tile_count": b.tile_count, "tiles": hex(&b.tiles), "tilemap": b.tilemap,
        "palettes": b.palettes.iter().map(|p| colors(p)).collect::<Vec<_>>(),
    });
    // Only for a layer that was asked for one, so the answer of every
    // other is the one it always was.
    if let Some(t) = texture {
        answer["mode7"] = json!({
            "tile_count": t.tile_count, "tiles": hex(&t.tiles), "map": t.map,
            "distinct": t.distinct, "center": [b.center.0, b.center.1],
        });
    }
    answer
}

pub fn backdrop_answer(b: &scene::Backdrop) -> Value {
    json!({"indices": b.indices, "palette": colors(&b.palette)})
}

pub fn light_answer(l: &scene::Light) -> Value {
    json!({"small": l.small, "indices": l.indices, "palette": colors(&l.palette)})
}

pub fn battler_answer(b: &scene::Battler) -> Value {
    json!({
        "width": b.width, "height": b.height, "pixels": b.pixels,
        "rm_height": b.rm_height, "palette": colors(&b.palette), "colors": b.colors,
        "merges": b.merges.iter().map(|m| json!([m.victim, m.target, m.pixels])).collect::<Vec<_>>(),
    })
}

pub fn animation_answer(a: &animation::Converted) -> Value {
    json!({"frames": a.frames, "palette": colors(&a.palette), "anchor": a.anchor,
           "size": a.size, "rm_box": a.rm_box})
}
