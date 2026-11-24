//! The pictures, which are `rm2k-snes-images`: what goes into its requests.
//!
//! **The pixels are the stage's**: scaling, the console's tint, stacking an
//! animation's cells, bringing the colours down and handing back indices
//! and palette —see its README—. What the converter says is which
//! pictures, found in the game's folder or the RTP, and the sizes the
//! cartridge decided, which travel in the request so they are written in
//! one place.

use crate::fail::{Result, Stop};
use crate::pictures::{HEIGHT, RM_HEIGHT, RM_WIDTH, WIDTH};
use crate::stage;
use rm2k_snes_images::request::{
    AnimationWanted, Animations, BackdropAnswer, BackdropWanted, Backdrops, Background,
    BattlerWanted, Battlers, Fullscreen, Layer, Mode7Room, Scene, ShowPicture,
};
use rm2k_snes_images::{animation, fullscreen, scene, show_picture, stage as the_stage};
use serde::de::DeserializeOwned;
use serde::Serialize;
use std::ffi::OsString;
use std::path::{Path, PathBuf};

/// The six commands the converter asks, each a function of the stage's
/// crate.
const FULLSCREEN: stage::Stage = images("fullscreen");
const PICTURE: stage::Stage = images("picture");
const BACKGROUND: stage::Stage = images("background");
const BACKDROPS: stage::Stage = images("backdrops");
const BATTLERS: stage::Stage = images("battlers");
const ANIMATIONS: stage::Stage = images("animations");

const fn images(command: &'static str) -> stage::Stage {
    stage::Stage {
        binary: "rm2k-snes-images",
        command,
    }
}

/// The stage `which` asked `request` —with `flags`, which the key reads and
/// `answer` must read nothing beyond—. Its answer goes into the cache
/// serialized, as `<command>.json`, and is read back from there whether it
/// was just made or found.
fn answer<R: Serialize, A: Serialize + DeserializeOwned>(
    which: stage::Stage,
    request: &R,
    flags: &[OsString],
    answer: impl FnOnce(&R) -> rm2k_snes_images::Result<A>,
) -> Result<A> {
    let name = format!("{}.json", which.command);
    let value = serde_json::to_value(request).expect("a request is JSON");
    let written = stage::call(which, &value, flags, || {
        answer(request).map(|a| {
            let json = serde_json::to_vec(&a).expect("an answer is JSON");
            stage::Files::from([(name.clone(), json)])
        })
    })?;
    serde_json::from_str(&stage::text(&written, &name)?)
        .map_err(|e| Stop::new(format!("{name}: {e}")))
}

fn file(path: &Path) -> PathBuf {
    rm2k_project::absolute(path)
}

/// A picture that fills the screen: the distinct 8x8 cells of CGRAM
/// indices —already shifted by `first_color`—, the colours at fifteen bits
/// and a tile per cell.
pub fn fullscreen(
    path: &Path,
    width: i64,
    height: i64,
    cell: i64,
    first_color: i64,
    cap: i64,
) -> Result<fullscreen::Screen> {
    let request = Fullscreen {
        file: file(path),
        width: width as usize,
        height: height as usize,
        cell: cell as usize,
        first_color: first_color as usize,
        cap: cap as usize,
    };
    answer(FULLSCREEN, &request, &[], the_stage::fullscreen)
}

/// The picture of a `ShowPicture` centred at `(cx, cy)` of RM2k's screen,
/// at `zoom` percent and with the map or with the screen.
#[allow(clippy::too_many_arguments)]
pub fn picture(
    path: &Path,
    use_transparent_color: bool,
    top_trans: i32,
    cx: i64,
    cy: i64,
    colors: i64,
    zoom: i64,
    map_fixed: bool,
    for_console: bool,
) -> Result<show_picture::Converted> {
    let request = ShowPicture {
        file: file(path),
        use_transparent_color,
        top_trans,
        x: cx,
        y: cy,
        rm_screen: (RM_WIDTH, RM_HEIGHT),
        screen: (WIDTH, HEIGHT),
        colors: colors as usize,
        zoom,
        map_fixed,
        for_console,
    };
    answer(PICTURE, &request, &[], the_stage::picture)
}

/// The picture of a `ShowPicture` too big for the sprites, as a 4bpp
/// layer, or None if not even cut to the screen do its tiles fit; with
/// `mode7`, as a mode 7 texture too, if the layer leaves room for one.
#[allow(clippy::too_many_arguments)]
pub fn background(
    path: &Path,
    use_transparent_color: bool,
    cx: i64,
    cy: i64,
    zoom: i64,
    crop: Option<(i64, i64)>,
    for_console: bool,
    palettes: i64,
    first_palette: i64,
    tiles: i64,
    rows: i64,
    mode7: bool,
    under: Option<&Path>,
) -> Result<Option<Layer>> {
    let request = Background {
        file: file(path),
        use_transparent_color,
        x: cx,
        y: cy,
        rm_screen: (RM_WIDTH, RM_HEIGHT),
        screen: (WIDTH, HEIGHT),
        zoom,
        crop,
        for_console,
        palettes: palettes as usize,
        first_palette: first_palette as usize,
        tiles: tiles as usize,
        rows: rows as usize,
        // The texture, which only a picture that zooms asks for.
        mode7: mode7.then_some(Mode7Room {
            tiles: crate::pictures::M7_TILES as usize,
            layer_tiles: crate::pictures::M7_LAYER_TILES as usize,
            layer_rows: crate::pictures::M7_LAYER_ROWS as usize,
        }),
        // And the panorama under it, for one shown with its holes over a
        // map's still panorama: see `pictures::still_over`.
        under: under.map(file),
    };
    answer(BACKGROUND, &request, &[], the_stage::background)
}

/// Each of `wanted` —`(path, quality, light)`— as the stage answers it.
pub fn backdrops(scene: &Scene, wanted: &[(PathBuf, bool, bool)]) -> Result<Vec<BackdropAnswer>> {
    if wanted.is_empty() {
        return Ok(Vec::new());
    }
    let request = Backdrops {
        scene: *scene,
        backdrops: wanted
            .iter()
            .map(|(p, quality, light)| BackdropWanted {
                file: file(p),
                quality: *quality,
                light: *light,
            })
            .collect(),
    };
    answer(BACKDROPS, &request, &[], the_stage::backdrops)
}

/// Each of `wanted` —`(path, hue)`— as the stage answers it.
pub fn battlers(scene: &Scene, wanted: &[(PathBuf, i64)]) -> Result<Vec<scene::Battler>> {
    if wanted.is_empty() {
        return Ok(Vec::new());
    }
    let request = Battlers {
        scene: *scene,
        battlers: wanted
            .iter()
            .map(|(p, hue)| BattlerWanted {
                file: file(p),
                hue: *hue as i32,
            })
            .collect(),
    };
    answer(BATTLERS, &request, &[], the_stage::battlers)
}

/// Each of `wanted` —`(number, sheet)`— as the stage answers it, or None
/// if nothing of it is drawn. The animation itself is read from the dump.
pub fn animations(
    side: i64,
    colors: i64,
    alpha_min: i64,
    wanted: &[(i32, PathBuf)],
    dump: &Path,
) -> Result<Vec<Option<animation::Converted>>> {
    if wanted.is_empty() {
        return Ok(Vec::new());
    }
    let request = Animations {
        side: side as usize,
        colors: colors as usize,
        alpha_min: alpha_min as u8,
        animations: wanted
            .iter()
            .map(|(number, s)| AnimationWanted {
                number: *number,
                sheet: file(s),
            })
            .collect(),
    };
    answer(
        ANIMATIONS,
        &request,
        &["--data".into(), dump.as_os_str().to_owned()],
        |r| the_stage::animations(dump, r),
    )
}
