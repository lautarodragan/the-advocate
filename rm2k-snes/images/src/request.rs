//! The requests each stage function takes, and the answers it gives that
//! are not a library type of their own.
//!
//! A request names the pictures —by path: finding a game's file, in its
//! folder or in the RTP, is the caller's— and carries the sizes the
//! cartridge decided. Until 2026-11-27 they were also read from a file, by
//! the crate's binary, which the tests ran; nothing does any more.

use crate::{animation, background, mode7, scene};
use adeleine::Color;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// `fullscreen`: one picture, the screen's size and the cell's, and the
/// palette: how many colours and from which CGRAM entry.
#[derive(Serialize, Deserialize)]
pub struct Fullscreen {
    pub file: PathBuf,
    pub width: usize,
    pub height: usize,
    pub cell: usize,
    pub first_color: usize,
    pub cap: usize,
}

/// `picture`: the file and what the `ShowPicture` says of it —its
/// transparent colour, its transparency, its centre on RM2k's screen—,
/// the two screens, and how many colours.
#[derive(Serialize, Deserialize)]
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
#[derive(Serialize, Deserialize)]
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
    /// A panorama to draw under it, from the corner of RM2k's screen: what
    /// RM2k shows through the picture's holes on a map of one screen. With
    /// it the layer is the two together, the screen's size. Absent, the
    /// holes draw nothing.
    #[serde(default)]
    pub under: Option<PathBuf>,
}

/// What the console grants a layer that is also a mode 7 texture: the tiles
/// the texture's map names, the blank one included, and how many tiles and
/// rows of cells the layer itself can take while the texture shares VRAM
/// with it.
#[derive(Serialize, Deserialize, Clone, Copy)]
pub struct Mode7Room {
    pub tiles: usize,
    pub layer_tiles: usize,
    pub layer_rows: usize,
}

fn hundred() -> i64 {
    100
}

/// The scene's geometry, as `scene::Geometry` names it.
#[derive(Serialize, Deserialize, Clone, Copy)]
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
#[derive(Serialize, Deserialize)]
pub struct Backdrops {
    pub scene: Scene,
    pub backdrops: Vec<BackdropWanted>,
}

#[derive(Serialize, Deserialize)]
pub struct BackdropWanted {
    pub file: PathBuf,
    #[serde(default)]
    pub quality: bool,
    #[serde(default)]
    pub light: bool,
}

/// `battlers`: each battler's file and its `battler_hue`.
#[derive(Serialize, Deserialize)]
pub struct Battlers {
    pub scene: Scene,
    pub battlers: Vec<BattlerWanted>,
}

#[derive(Serialize, Deserialize)]
pub struct BattlerWanted {
    pub file: PathBuf,
    #[serde(default)]
    pub hue: i32,
}

/// `animations`: the box, and each animation by its number in the dump
/// with the sheet its cells are cut from.
#[derive(Serialize, Deserialize)]
pub struct Animations {
    pub side: usize,
    pub colors: usize,
    pub alpha_min: u8,
    pub animations: Vec<AnimationWanted>,
}

#[derive(Serialize, Deserialize)]
pub struct AnimationWanted {
    pub number: i32,
    pub sheet: PathBuf,
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

/// What `background` answers: the layer, as [`background::Background`]
/// and [`mode7::Texture`] carry it to a cartridge.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Layer {
    pub top: i64,
    pub rows: usize,
    pub columns: usize,
    pub wider: bool,
    pub tile_count: usize,
    #[serde(with = "hex")]
    pub tiles: Vec<u8>,
    pub tilemap: Vec<u16>,
    pub palettes: Vec<Vec<Color>>,
    /// Only for a layer that was asked for one and leaves room for it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mode7: Option<LayerTexture>,
}

/// A layer's mode 7 texture, and where on the screen a zoom shrinks it
/// towards.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct LayerTexture {
    pub tile_count: usize,
    #[serde(with = "hex")]
    pub tiles: Vec<u8>,
    pub map: Vec<u8>,
    pub distinct: usize,
    pub center: (i64, i64),
}

impl Layer {
    pub fn of(b: background::Background, texture: Option<mode7::Texture>) -> Layer {
        Layer {
            mode7: texture.map(|t| LayerTexture {
                tile_count: t.tile_count,
                tiles: t.tiles,
                map: t.map,
                distinct: t.distinct,
                center: b.center,
            }),
            top: b.top,
            rows: b.rows,
            columns: b.columns,
            wider: b.wider,
            tile_count: b.tile_count,
            tiles: b.tiles,
            tilemap: b.tilemap,
            palettes: b.palettes,
        }
    }
}

/// Bytes as lowercase hex, which is how a cartridge's requests carry them.
mod hex {
    use serde::{de::Error, Deserialize, Deserializer, Serializer};

    pub fn serialize<S: Serializer>(bytes: &[u8], s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&bytes.iter().map(|v| format!("{v:02x}")).collect::<String>())
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<u8>, D::Error> {
        let text = String::deserialize(d)?;
        (0..text.len() / 2)
            .map(|i| {
                text.get(2 * i..2 * i + 2)
                    .and_then(|b| u8::from_str_radix(b, 16).ok())
            })
            .collect::<Option<_>>()
            .ok_or_else(|| D::Error::custom(format!("{text:?} is not hex")))
    }
}

/// What `backdrops` answers for each backdrop: the versions asked for.
#[derive(Serialize, Deserialize)]
pub struct BackdropAnswer {
    pub quality: Option<scene::Backdrop>,
    pub light: Option<scene::Light>,
}
