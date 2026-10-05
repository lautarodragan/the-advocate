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
/// The block table, and each block's passability and terrain.
pub const BLOCK_TABLE: &str = "blocks.bin";
pub const BLOCK_PASSABILITY: &str = "block-passability.bin";
pub const BLOCK_TERRAIN: &str = "block-terrain.bin";

/// The file drawing `d` of a family's run is written to.
pub fn run_file(run: &Run, d: usize) -> String {
    format!("run-{}-{d}.bin", run.family.name())
}

/// A map as it is drawn: the dump's, or the project's file, with the baked
/// cells painted into its upper layer; and its ChipSet entry.
pub struct Drawn {
    pub map: Map,
    pub chipset: Chipset,
    pub layers: Layers,
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
    let layers = drawn.render(&atlas)?;
    Ok(Drawn {
        map: drawn,
        chipset,
        layers,
    })
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
pub fn write(out: &Path, converted: &Converted, passability: &[u8], made: &Blocks) -> Result<()> {
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
    let answer = json!({
        "background": {
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
    let converted = crate::background::convert(&drawn.layers, request.window_colors)?;
    let (passability, made) = blocks(&drawn, &converted)?;
    write(out, &converted, &passability, &made)
}
