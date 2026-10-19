//! The pictures, which are `rm2k-snes-images`: what goes into its requests.
//!
//! **The pixels are the stage's**: scaling, the console's tint, stacking an
//! animation's cells, bringing the colours down and handing back indices
//! and palette —see its README—. What the converter says is which
//! pictures, found in the game's folder or the RTP, and the sizes the
//! cartridge decided, which travel in the request so they are written in
//! one place.

use crate::fail::Result;
use crate::pictures::{HEIGHT, RM_HEIGHT, RM_WIDTH, WIDTH};
use crate::stage;
use serde_json::{json, Value};
use std::ffi::OsString;
use std::path::{Path, PathBuf};

const BINARY: &str = "rm2k-snes-images";
const PROJECT: &str = "images";

fn answer(command: &str, request: &Value, flags: &[OsString]) -> Result<Value> {
    let written = stage::run(BINARY, PROJECT, command, request, flags)?;
    stage::json(&written, &format!("{command}.json"))
}

fn file(path: &Path) -> String {
    rm2k_project::absolute(path).to_string_lossy().to_string()
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
) -> Result<Value> {
    answer(
        "fullscreen",
        &json!({"file": file(path), "width": width, "height": height, "cell": cell,
                "first_color": first_color, "cap": cap}),
        &[],
    )
}

/// The picture of a `ShowPicture` centred at `(cx, cy)` of RM2k's screen,
/// at `zoom` percent and with the map or with the screen.
#[allow(clippy::too_many_arguments)]
pub fn picture(
    path: &Path,
    use_transparent_color: bool,
    top_trans: i64,
    cx: i64,
    cy: i64,
    colors: i64,
    zoom: i64,
    map_fixed: bool,
    for_console: bool,
) -> Result<Value> {
    let mut request = json!({
        "file": file(path), "use_transparent_color": use_transparent_color,
        "top_trans": top_trans, "x": cx, "y": cy,
        "rm_screen": [RM_WIDTH, RM_HEIGHT], "screen": [WIDTH, HEIGHT], "colors": colors,
    });
    // Only when they say something, so the request of a plain picture is
    // the one it always was.
    if zoom != 100 {
        request["zoom"] = json!(zoom);
    }
    if map_fixed {
        request["map_fixed"] = json!(true);
    }
    if for_console {
        request["for_console"] = json!(true);
    }
    answer("picture", &request, &[])
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
) -> Result<Option<Value>> {
    let mut request = json!({
        "file": file(path), "use_transparent_color": use_transparent_color,
        "x": cx, "y": cy, "rm_screen": [RM_WIDTH, RM_HEIGHT], "screen": [WIDTH, HEIGHT],
        "zoom": zoom, "palettes": palettes, "first_palette": first_palette,
        "tiles": tiles, "rows": rows,
    });
    // Only when there is one, so a scaled picture's request is the one it
    // always was.
    if let Some((x, y)) = crop {
        request["crop"] = json!([x, y]);
    }
    if for_console {
        request["for_console"] = json!(true);
    }
    // The same for the texture, which only a picture that zooms asks for.
    if mode7 {
        request["mode7"] = json!({
            "tiles": crate::pictures::M7_TILES,
            "layer_tiles": crate::pictures::M7_LAYER_TILES,
            "layer_rows": crate::pictures::M7_LAYER_ROWS,
        });
    }
    let a = answer("background", &request, &[])?;
    Ok((!a.is_null()).then_some(a))
}

/// Each of `wanted` —`(path, quality, light)`— as the stage answers it.
pub fn backdrops(scene: &Value, wanted: &[(PathBuf, bool, bool)]) -> Result<Vec<Value>> {
    if wanted.is_empty() {
        return Ok(Vec::new());
    }
    let a = answer(
        "backdrops",
        &json!({
            "scene": scene,
            "backdrops": wanted.iter().map(|(p, q, l)| json!({"file": file(p), "quality": q, "light": l}))
                .collect::<Vec<_>>(),
        }),
        &[],
    )?;
    Ok(a.as_array().cloned().unwrap_or_default())
}

/// Each of `wanted` —`(path, hue)`— as the stage answers it.
pub fn battlers(scene: &Value, wanted: &[(PathBuf, i64)]) -> Result<Vec<Value>> {
    if wanted.is_empty() {
        return Ok(Vec::new());
    }
    let a = answer(
        "battlers",
        &json!({
            "scene": scene,
            "battlers": wanted.iter().map(|(p, hue)| json!({"file": file(p), "hue": hue}))
                .collect::<Vec<_>>(),
        }),
        &[],
    )?;
    Ok(a.as_array().cloned().unwrap_or_default())
}

/// Each of `wanted` —`(number, sheet)`— as the stage answers it, or null
/// if nothing of it is drawn. The animation itself is read from the dump.
pub fn animations(
    side: i64,
    colors: i64,
    alpha_min: i64,
    wanted: &[(i32, PathBuf)],
    dump: &Path,
) -> Result<Vec<Value>> {
    if wanted.is_empty() {
        return Ok(Vec::new());
    }
    let a = answer(
        "animations",
        &json!({
            "side": side, "colors": colors, "alpha_min": alpha_min,
            "animations": wanted.iter().map(|(n, s)| json!({"number": n, "sheet": file(s)}))
                .collect::<Vec<_>>(),
        }),
        &["--data".into(), dump.as_os_str().to_owned()],
    )?;
    Ok(a.as_array().cloned().unwrap_or_default())
}
