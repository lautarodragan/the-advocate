//! The pictures as a stage of a converter: what each of the six commands
//! answers, as the files the binary writes into `--out`, by name. The
//! converter calls the six as functions —`fullscreen`, `picture`,
//! `background`, `backdrops`, `battlers` and `animations`, each asked a
//! request already parsed—, and the binary is a `main` over the `_of`
//! functions, which take the request read from its file.
//!
//! **They read nothing but the request they are given, the pictures it
//! names and, for `animations`, the dump**: the converter keeps their
//! answers in its cache under the key of those, and a function that read
//! anything else would hand back a stale answer.

use crate::fail::{Bad, Result};
use crate::request::{self, Animations, Backdrops, Background, Battlers, Fullscreen, ShowPicture};
use crate::{animation, background, fullscreen, mode7, scene, show_picture};
use ditto::dump::Dump;
use ditto::schema::Animation;
use rm2k_render::{battle, picture, show_picture as rm2k_picture};
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// What the converter's requests are called in a complaint.
const WHOSE: &str = "the request";

/// `fullscreen`: a picture that fills the screen at 8 bits a pixel.
pub fn fullscreen(request: &Value) -> Result<Files> {
    fullscreen_of(&request::of(request, WHOSE)?)
}

/// `picture`: the picture of a `ShowPicture`, where it lands and its
/// colours.
pub fn picture(request: &Value) -> Result<Files> {
    picture_of(&request::of(request, WHOSE)?)
}

/// `background`: the picture of a `ShowPicture` too big for the sprites,
/// as a 4bpp layer, and as a mode 7 texture if asked for.
pub fn background(request: &Value) -> Result<Files> {
    background_of(&request::of(request, WHOSE)?)
}

/// `backdrops`: battle backdrops, in quality and in the light fallback.
pub fn backdrops(request: &Value) -> Result<Files> {
    backdrops_of(&request::of(request, WHOSE)?)
}

/// `battlers`: battlers, turned by their hue, at the scene's scale.
pub fn battlers(request: &Value) -> Result<Files> {
    battlers_of(&request::of(request, WHOSE)?)
}

/// `animations`: battle animations of the dump in `data`, in the box the
/// console draws them in.
pub fn animations(data: &Path, request: &Value) -> Result<Files> {
    animations_of(data, &request::of(request, WHOSE)?)
}

/// [`fullscreen`], of a request already read.
pub fn fullscreen_of(r: &Fullscreen) -> Result<Files> {
    let screen = fullscreen::convert(
        &picture::read_unkeyed(&r.file)?,
        r.width,
        r.height,
        r.cell,
        r.first_color,
        r.cap,
    );
    Ok(one("fullscreen", &request::fullscreen_answer(&screen)))
}

/// [`picture`], of a request already read.
pub fn picture_of(r: &ShowPicture) -> Result<Files> {
    let drawn = rm2k_picture::picture(
        &picture::read_unkeyed(&r.file)?,
        &picture::read_rm2k(&r.file)?,
        r.use_transparent_color,
        r.top_trans,
    );
    let screens = show_picture::Screens {
        rm: r.rm_screen,
        console: r.screen,
    };
    let shown = show_picture::Shown {
        zoom: r.zoom,
        map_fixed: r.map_fixed,
        for_console: r.for_console,
        ..show_picture::Shown::PLAIN
    };
    let converted = show_picture::convert_shown(&drawn, r.x, r.y, screens, r.colors, shown)?;
    Ok(one("picture", &request::picture_answer(&converted)))
}

/// [`background`], of a request already read.
pub fn background_of(r: &Background) -> Result<Files> {
    let drawn = rm2k_picture::picture(
        &picture::read_unkeyed(&r.file)?,
        &picture::read_rm2k(&r.file)?,
        r.use_transparent_color,
        0,
    );
    let (drawn, x, y) = match &r.under {
        None => (drawn, r.x, r.y),
        Some(under) => background::over_panorama(
            &drawn,
            &picture::read_unkeyed(under)?,
            r.x,
            r.y,
            r.rm_screen,
        ),
    };
    let screens = show_picture::Screens {
        rm: r.rm_screen,
        console: r.screen,
    };
    let room = background::Room {
        palettes: r.palettes,
        first_palette: r.first_palette,
        tiles: r.tiles,
        rows: r.rows,
    };
    let layer = background::convert(&drawn, x, y, screens, r.zoom, r.crop, r.for_console, room)?;
    // The texture, if asked for and the layer leaves room for it; if it
    // does not, the answer says so with a null.
    let texture = match (&layer, r.mode7) {
        (Some(l), Some(m)) if l.tile_count <= m.layer_tiles && l.rows <= m.layer_rows => {
            Some(mode7::texture(&l.pixels, l.columns, &l.colors, m.tiles))
        }
        _ => None,
    };
    let mut answer = layer.as_ref().map_or(Value::Null, |l| {
        request::background_answer(l, texture.as_ref())
    });
    if r.mode7.is_some() && texture.is_none() && !answer.is_null() {
        answer["mode7"] = Value::Null;
    }
    Ok(one("background", &answer))
}

/// [`backdrops`], of a request already read.
pub fn backdrops_of(r: &Backdrops) -> Result<Files> {
    let g: scene::Geometry = r.scene.into();
    let mut answer = Vec::with_capacity(r.backdrops.len());
    for wanted in &r.backdrops {
        let drawn = battle::backdrop(&wanted.file)?;
        let quality = wanted
            .quality
            .then(|| request::backdrop_answer(&scene::backdrop(&drawn, &g)));
        let light = match wanted.light {
            true => Some(request::light_answer(&scene::light_backdrop(&drawn, &g)?)),
            false => None,
        };
        answer.push(serde_json::json!({"quality": quality, "light": light}));
    }
    Ok(one("backdrops", &Value::Array(answer)))
}

/// [`battlers`], of a request already read.
pub fn battlers_of(r: &Battlers) -> Result<Files> {
    let g: scene::Geometry = r.scene.into();
    let answer = r
        .battlers
        .iter()
        .map(|b| {
            Ok(request::battler_answer(&scene::battler(
                &battle::battler(&b.file, b.hue)?,
                &g,
            )?))
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(one("battlers", &Value::Array(answer)))
}

/// [`animations`], of a request already read.
pub fn animations_of(data: &Path, r: &Animations) -> Result<Files> {
    let g = animation::Geometry::from(r);
    let dump = Dump::open(data).map_err(|e| Bad::answer(e.0))?;
    let all: Vec<Animation> = dump.section("animations").map_err(|e| Bad::answer(e.0))?;
    let by_number: HashMap<i32, &Animation> = all.iter().map(|a| (a.id, a)).collect();
    let mut sheets: HashMap<PathBuf, rm2k_render::Picture> = HashMap::new();
    let mut answer = Vec::with_capacity(r.animations.len());
    for wanted in &r.animations {
        let anim = by_number.get(&wanted.number).ok_or_else(|| {
            Bad::answer(format!(
                "{}: the dump has no animation {}",
                data.display(),
                wanted.number
            ))
        })?;
        if !sheets.contains_key(&wanted.sheet) {
            sheets.insert(wanted.sheet.clone(), picture::read_rm2k(&wanted.sheet)?);
        }
        let converted = animation::convert(anim, &sheets[&wanted.sheet], &g);
        answer.push(converted.map_or(Value::Null, |c| request::animation_answer(&c)));
    }
    Ok(one("animations", &Value::Array(answer)))
}

/// `answer` as the file `<command>.json`, as every answer of this crate is
/// written: on one line, with no newline after it.
fn one(command: &str, answer: &Value) -> Files {
    Files::from([(format!("{command}.json"), answer.to_string().into_bytes())])
}
