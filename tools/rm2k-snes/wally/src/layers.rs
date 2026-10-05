//! A map's two background layers: drawn by `rm2k-render`, converted by
//! [`crate::background`], and written for the caller; and the map as
//! blocks of 16x16, which are made of what the two layers were converted to.

use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::request::LayersRequest;
use ditto::schema::Chipset;
use rm2k_render::{picture, Atlas, Layers, Map};
use rm2k_rules::chipset::{passability_table, terrain_of};
use crate::background::blocks::{self, Blocks};
use crate::background::{Converted, Merge, Run};
use serde_json::{json, Value};
use std::path::Path;

/// The file what the caller needs to know is written to.
pub const ANSWER_FILE: &str = "layers.json";
/// The background's tiles.
pub const BACKGROUND_TILES: &str = "background.bin";
/// The layer above's tiles and its colour-memory words.
pub const ABOVE_TILES: &str = "above.bin";
pub const ABOVE_CGRAM: &str = "above-cgram.bin";
/// The panorama's tiles, if the map shows it.
pub const PANORAMA_TILES: &str = "panorama.bin";
/// The block table, and each block's passability and terrain.
pub const BLOCK_TABLE: &str = "blocks.bin";
pub const BLOCK_PASSABILITY: &str = "block-passability.bin";
pub const BLOCK_TERRAIN: &str = "block-terrain.bin";

/// The file drawing `d` of a family's run is written to.
pub fn run_file(run: &Run, d: usize) -> String {
    format!("run-{}-{d}.bin", run.family.name())
}

/// A map as it is drawn: the dump's, or the project's file, with the baked
/// cells painted into its upper layer; its ChipSet entry; and, if the
/// cartridge shows its panorama, the stretch of it the console can show.
pub struct Drawn {
    pub map: Map,
    pub chipset: Chipset,
    pub layers: Layers,
    pub panorama: Option<Panorama>,
}

/// The stretch of a panorama the console can show, and how it moves: what
/// the map says of it, as RM2k reads it —`Game_Map::Parallax`—.
#[derive(Clone, Debug)]
pub struct Panorama {
    pub name: String,
    /// The whole picture's size; the stretch is `picture`.
    pub size: (usize, usize),
    pub picture: picture::Picture,
    /// Whether it loops on each axis, and by how much a frame it moves on
    /// its own: RM2k's speed, 0 if it does not.
    pub looped: (bool, bool),
    pub auto: (i32, i32),
}

/// The RM2k screen, and the console's, in pixels; and where each puts the
/// hero's cell, from the screen's corner. RM2k's is
/// `Game_Player::GetDefaultPanX`: half the screen in cells, rounded up, less
/// one. The console's is `follow_camera`'s: the cell's centre on the
/// screen's.
const RM2K_SCREEN: (usize, usize) = (320, 240);
const RM2K_HERO: (usize, usize) = (9 * 16, 7 * 16);
const CONSOLE_SCREEN: (usize, usize) = (256, 224);
const CONSOLE_HERO: (usize, usize) = (128 - 8, 112 - 8);

/// How far into the panorama the console can look along one axis: all of
/// it if it loops, and if it does not, as far as `Game_Map::Parallax`
/// takes it with RM2k's camera, plus how far the console's camera, which
/// shows less, is from that one. That is the whole map walked a pixel at a
/// time. A `PanScreen` can take the camera further, and that is not
/// counted.
pub fn reach(map: usize, (rm2k, rm2k_hero): (usize, usize), (console, console_hero): (usize, usize), pano: usize, looped: bool) -> usize {
    if looped {
        return pano;
    }
    let camera = |h: usize, screen: usize, hero: usize| -> usize {
        h.saturating_sub(hero).min(map.saturating_sub(screen))
    };
    let tiles = map / 16;
    let per_screen = rm2k.div_ceil(16);
    let mut far = 0;
    for h in 0..map {
        let rc = camera(h, rm2k, rm2k_hero);
        let oc = camera(h, console, console_hero);
        let off = if tiles > per_screen && pano > rm2k {
            let w = (tiles - per_screen) * 16;
            w.min(pano - rm2k) * rc / w
        } else {
            0
        };
        far = far.max(off + oc - rc + console);
    }
    far.next_multiple_of(8).min(pano)
}

/// Reads the request's map and draws it.
pub fn draw(game: &Game, request: &LayersRequest) -> Result<Drawn> {
    let id = request.map;
    let map = game.map(id)?;
    let chipset = game.chipset(map.chipset_id)?;
    let mut upper = map.upper_layer.clone();
    for &(cell, tile) in &request.baked {
        let slot = upper.get_mut(cell).ok_or_else(|| {
            Bad::answer(format!(
                "map {id}: baked cell {cell} is past its {} cells",
                map.upper_layer.len()
            ))
        })?;
        *slot = tile;
    }
    let path = game
        .resource("ChipSet", &chipset.chipset_name)
        .ok_or_else(|| {
            Bad::answer(format!(
                "can't find the chipset of map {id}: {:?} is in none of the search directories",
                chipset.chipset_name
            ))
        })?;
    let atlas = Atlas::new(&picture::read_rm2k(&path)?);
    let size = |name: &str, v: i32| {
        usize::try_from(v).map_err(|_| Bad::answer(format!("map {id}: `{name}` is {v}")))
    };
    let drawn = Map {
        width: size("width", map.width)?,
        height: size("height", map.height)?,
        lower_layer: map.lower_layer.iter().map(|&t| t as i64).collect(),
        upper_layer: upper.iter().map(|&t| t as i64).collect(),
        passable_lower: chipset.passable_data_lower.clone(),
        passable_upper: chipset.passable_data_upper.clone(),
    };
    let panorama = match request.panorama {
        Some(_) if map.parallax_flag => {
            let name = map.parallax_name.clone();
            let path = game.resource("Panorama", &name).ok_or_else(|| {
                Bad::answer(format!(
                    "can't find the panorama of map {id}: {name:?} is in none of the search directories"
                ))
            })?;
            // Opaque: RM2k gives a panorama no colour key.
            let whole = picture::read_unkeyed(&path)?;
            let (mw, mh) = (drawn.width * 16, drawn.height * 16);
            let w = reach(mw, (RM2K_SCREEN.0, RM2K_HERO.0), (CONSOLE_SCREEN.0, CONSOLE_HERO.0), whole.width, map.parallax_loop_x);
            let h = reach(mh, (RM2K_SCREEN.1, RM2K_HERO.1), (CONSOLE_SCREEN.1, CONSOLE_HERO.1), whole.height, map.parallax_loop_y);
            Some(Panorama {
                name,
                size: (whole.width, whole.height),
                picture: whole.crop(0, 0, w, h),
                looped: (map.parallax_loop_x, map.parallax_loop_y),
                auto: (
                    if map.parallax_loop_x && map.parallax_auto_loop_x { map.parallax_sx } else { 0 },
                    if map.parallax_loop_y && map.parallax_auto_loop_y { map.parallax_sy } else { 0 },
                ),
            })
        }
        _ => None,
    };
    let layers = if panorama.is_some() {
        drawn.render_over_panorama(&atlas)?
    } else {
        drawn.render(&atlas)?
    };
    Ok(Drawn {
        map: drawn,
        chipset,
        layers,
        panorama,
    })
}

/// The two layers converted, with the panorama if the map shows it.
pub fn convert(drawn: &Drawn, request: &LayersRequest) -> Result<Converted> {
    let ask = match (&drawn.panorama, request.panorama) {
        (Some(p), Some(budget)) => Some(crate::background::PanoramaAsk {
            picture: &p.picture,
            tiles_mode3: budget.tiles_mode3,
            tiles_mode1: budget.tiles_mode1,
        }),
        _ => None,
    };
    if ask.is_some() && request.panorama.and_then(|b| b.mode) == Some(3) {
        // Mode 3 asked for: what goes above the hero is drawn behind him.
        let flat = flattened(&drawn.layers);
        return Ok(crate::background::convert_with(&flat, request.window_colors, ask.as_ref())?);
    }
    Ok(crate::background::convert_with(&drawn.layers, request.window_colors, ask.as_ref())?)
}

/// The layers with the upper one drawn over the lower one, in every drawing
/// of the animation, and nothing left above.
fn flattened(layers: &Layers) -> Layers {
    let over = |below: &picture::Picture| {
        let mut out = below.clone();
        for (px, up) in out.rgba.chunks_exact_mut(4).zip(layers.upper.rgba.chunks_exact(4)) {
            if up[3] != 0 {
                px.copy_from_slice(up);
            }
        }
        out
    };
    Layers {
        lower: over(&layers.lower),
        upper: picture::Picture::transparent(layers.upper.width, layers.upper.height),
        variants: layers
            .variants
            .iter()
            .map(|(f, gs)| (*f, gs.iter().map(over).collect()))
            .collect(),
    }
}

/// Each cell's passability —both layers resolved, as the hero meets them—
/// and the map in blocks.
pub fn blocks(drawn: &Drawn, converted: &Converted) -> Result<(Vec<u8>, Blocks)> {
    let map = &drawn.map;
    let flags = passability_table(&map.passable_lower, &map.passable_upper);
    let lower: Vec<i32> = map.lower_layer.iter().map(|&t| t as i32).collect();
    let upper: Vec<i32> = map.upper_layer.iter().map(|&t| t as i32).collect();
    let passability: Vec<u8> = lower
        .iter()
        .zip(&upper)
        .map(|(&l, &u)| rm2k_rules::passability::cell(&flags, l, u))
        .collect();
    let terrain: Vec<i32> = lower.iter().map(|&l| terrain_of(&drawn.chipset, l)).collect();
    let made = blocks::blocks(
        &blocks::Map {
            width: map.width,
            height: map.height,
            lower: &lower,
            upper: &upper,
            passability: &passability,
            terrain: &terrain,
        },
        &converted.background.tilemap,
        &converted.above.tilemap,
    )?;
    Ok((passability, made))
}

fn write_file(dir: &Path, name: &str, bytes: &[u8]) -> Result<()> {
    std::fs::write(dir.join(name), bytes)
        .map_err(|e| Bad::usage(format!("{}: {e}", dir.join(name).display())))
}

/// Writes the conversion into `out`: the tiles, the runs and the block
/// table as binaries, what was decided as indexed PNGs, and the rest in
/// `layers.json`.
pub fn write(
    out: &Path,
    converted: &Converted,
    panorama: Option<&Panorama>,
    passability: &[u8],
    made: &Blocks,
) -> Result<()> {
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    let bg = &converted.background;
    let above = &converted.above;
    write_file(out, BACKGROUND_TILES, &bg.tiles)?;
    write_file(out, ABOVE_TILES, &above.tiles)?;
    write_file(out, ABOVE_CGRAM, &above.cgram)?;
    write_file(out, BLOCK_TABLE, &made.table)?;
    write_file(out, BLOCK_PASSABILITY, &made.passability)?;
    write_file(out, BLOCK_TERRAIN, &made.terrain)?;
    let mut runs = Vec::new();
    for run in &bg.runs {
        let mut files = Vec::new();
        for (d, drawing) in run.drawings.iter().enumerate() {
            let name = run_file(run, d);
            write_file(out, &name, drawing)?;
            files.push(name);
        }
        runs.push(json!({"family": run.family.name(), "base": run.base,
                         "tiles": run.tiles, "drawings": files}));
    }
    let mut pictures = Vec::new();
    for decided in &converted.pictures {
        let name = format!("{}.png", decided.name);
        voodoo::image::write(&out.join(&name), &decided.picture)
            .map_err(|e| Bad::usage(e.to_string()))?;
        pictures.push(json!({"name": decided.name, "file": name}));
    }
    let pano = match (&converted.panorama, panorama) {
        (Some(p), Some(source)) => {
            write_file(out, PANORAMA_TILES, &p.tiles)?;
            json!({
                "name": source.name,
                "mode": p.mode.number(),
                "size": [source.size.0, source.size.1],
                "stretch": [source.picture.width, source.picture.height],
                "loop": [source.looped.0, source.looped.1],
                "auto": [source.auto.0, source.auto.1],
                "tiles": p.tiles.len() / if p.mode.number() == 3 { 32 } else { 16 },
                "tilemap": p.tilemap,
                "first": p.first,
                "cgram": p.cgram,
                "backdrop": p.backdrop,
                "distinct": p.distinct,
                "colors": p.colors,
                "kept": p.kept,
                "merges": merges_json(&p.merges),
            })
        }
        _ => Value::Null,
    };
    let answer = json!({
        "panorama": pano,
        "background": {
            "bpp": bg.bpp,
            "tiles": bg.tiles.len() / 64,
            "cgram": bg.cgram,
            "tilemap": bg.tilemap,
            "colors": bg.colors,
            "used": bg.used,
            "budget": bg.budget,
            "merges": merges_json(&bg.merges),
            "cells": bg.cells,
            "runs": runs,
        },
        "above": {
            "tilemap": above.tilemap,
            "first": above.first,
            "merges": merges_json(&above.merges),
        },
        "pictures": pictures,
        "passability": passability,
        "blocks": {
            "cells": made.cells,
            "combos": made.combos.iter().map(|&((l, u), b)| json!([l, u, b])).collect::<Vec<_>>(),
        },
    });
    write_file(out, ANSWER_FILE, answer.to_string().as_bytes())
}

/// Each merge as `[victim, target, pixels]`, a colour as `[r, g, b]`.
fn merges_json(merges: &[Merge]) -> Vec<Value> {
    merges
        .iter()
        .map(|m| json!([m.victim, m.target, m.pixels]))
        .collect()
}

/// The whole `layers` command: the request's map, drawn and converted,
/// into `out`.
pub fn run(game: &Game, request: &LayersRequest, out: &Path) -> Result<()> {
    let drawn = draw(game, request)?;
    let converted = convert(&drawn, request)?;
    let (passability, made) = blocks(&drawn, &converted)?;
    write(out, &converted, drawn.panorama.as_ref(), &passability, &made)
}
