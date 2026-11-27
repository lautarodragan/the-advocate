//! The pictures as a stage of a converter: what each of the six commands
//! answers. The converter calls the six as functions —`fullscreen`,
//! `picture`, `background`, `backdrops`, `battlers` and `animations`—.
//! Until 2026-11-27 a binary was a `main` over the last three, which a
//! game's tests asked; it went when they stopped.
//!
//! **They read nothing but the request they are given, the pictures it
//! names and, for `animations`, the dump**: the converter keeps their
//! answers in its cache under the key of those, and a function that read
//! anything else would hand back a stale answer.

use crate::fail::{Bad, Result};
use crate::request::{
    Animations, BackdropAnswer, Backdrops, Background, Battlers, Fullscreen, Layer, ShowPicture,
};
use crate::{animation, background, fullscreen, mode7, scene, show_picture};
use ditto::dump::Dump;
use ditto::schema::Animation;
use rm2k_render::{battle, picture, show_picture as rm2k_picture};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// `fullscreen`: a picture that fills the screen at 8 bits a pixel.
pub fn fullscreen(r: &Fullscreen) -> Result<fullscreen::Screen> {
    Ok(fullscreen::convert(
        &picture::read_unkeyed(&r.file)?,
        r.width,
        r.height,
        r.cell,
        r.first_color,
        r.cap,
    ))
}

/// `picture`: the picture of a `ShowPicture`, where it lands and its
/// colours.
pub fn picture(r: &ShowPicture) -> Result<show_picture::Converted> {
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
    show_picture::convert_shown(&drawn, r.x, r.y, screens, r.colors, shown)
}

/// `background`: the picture of a `ShowPicture` too big for the sprites,
/// as a 4bpp layer, and as a mode 7 texture if asked for; None if not even
/// cut to the screen do its tiles fit.
pub fn background(r: &Background) -> Result<Option<Layer>> {
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
    Ok(layer.map(|l| {
        // The texture, if asked for and the layer leaves room for it.
        let texture = match r.mode7 {
            Some(m) if l.tile_count <= m.layer_tiles && l.rows <= m.layer_rows => {
                Some(mode7::texture(&l.pixels, l.columns, &l.colors, m.tiles))
            }
            _ => None,
        };
        Layer::of(l, texture)
    }))
}

/// `backdrops`: battle backdrops, in quality and in the light fallback.
pub fn backdrops(r: &Backdrops) -> Result<Vec<BackdropAnswer>> {
    let g: scene::Geometry = r.scene.into();
    r.backdrops
        .iter()
        .map(|wanted| {
            let drawn = battle::backdrop(&wanted.file)?;
            Ok(BackdropAnswer {
                quality: wanted.quality.then(|| scene::backdrop(&drawn, &g)),
                light: match wanted.light {
                    true => Some(scene::light_backdrop(&drawn, &g)?),
                    false => None,
                },
            })
        })
        .collect()
}

/// `battlers`: battlers, turned by their hue, at the scene's scale.
pub fn battlers(r: &Battlers) -> Result<Vec<scene::Battler>> {
    let g: scene::Geometry = r.scene.into();
    r.battlers
        .iter()
        .map(|b| scene::battler(&battle::battler(&b.file, b.hue)?, &g))
        .collect()
}

/// `animations`: battle animations of the dump in `data`, in the box the
/// console draws them in; None for one of which nothing is drawn.
pub fn animations(data: &Path, r: &Animations) -> Result<Vec<Option<animation::Converted>>> {
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
        answer.push(animation::convert(anim, &sheets[&wanted.sheet], &g));
    }
    Ok(answer)
}
