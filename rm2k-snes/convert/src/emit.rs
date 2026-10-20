//! The emission, which is `rm2k-snes-mapdata emit`: what goes into its
//! request. It writes the whole `.inc` —the header of constants, the
//! tables of every map, the window and the font, the screens, the menus,
//! the battle, what the save game is signed with— from what every domain
//! of the conversion answered, which is what the request carries.

use crate::fail::Result;
use crate::maps::{MapInfo, PageRecord};
use crate::text::hex;
use serde_json::{json, Value};

/// A page as the emission takes it.
pub fn page_record(page: &PageRecord) -> Value {
    let own = page.own_route.as_ref().map(|own| {
        json!({
            "repeats": own["repeats"].as_bool().unwrap_or(false),
            "skippable": own["skippable"].as_bool().unwrap_or(false),
            "fixed_direction": own["fixed_direction"].as_bool().unwrap_or(false),
            "animation_continues": own["animation_continues"].as_bool().unwrap_or(false),
            "spin": own["spin"].as_bool().unwrap_or(false),
            "by_type": own["by_type"].as_bool().unwrap_or(false),
            "pattern": own["pattern"].as_i64().unwrap_or(1),
            "frequency": own["frequency"],
            "speed": own["speed"],
            "orders": own["commands"].as_array().map_or(0, Vec::len),
        })
    });
    json!({
        "event": page.event, "page": page.page,
        "trigger": page.trigger, "switch_a": page.switch_a,
        "switch_b": page.switch_b, "actor": page.actor,
        "layer": page.layer, "item": page.item,
        "has_code": page.has_code, "offset": page.offset,
        "route_offset": page.route_offset,
        "frequency": page.frequency, "speed": page.speed,
        "fixed_direction": page.fixed_direction,
        "fixed_graphic": page.fixed_graphic,
        "own_route": own,
        "draws": page.draws,
        "variable": page.variable,
        "graphic": page.graphic.as_ref().map(|(c, i, p)| json!([c, i, p])),
        "turns": page.turns,
        "pure": page.pure,
    })
}

/// What a map forbids, as the "forbidden" bits of the ROM's `FAR_ACCESS`:
/// save $01 and escape $04, the ones `ChangeSaveAccess` and
/// `ChangeEscapeAccess` set —`ACCESS_BIT` in the event compiler—, and
/// teleport $08, which no command sets yet. $02, the menu, is not the
/// map's.
pub fn access_bits(access: rm2k_rules::tree::Access) -> u8 {
    (if access.save { 0 } else { 0x01 })
        | (if access.escape { 0 } else { 0x04 })
        | (if access.teleport { 0 } else { 0x08 })
}

/// Which axes of the map loop on the console, `(x, y)`, and why an axis
/// RM2k loops does not, for `degradations.json`. An axis loops if the map
/// asks for it —`scroll_type`, where 1 is vertical and 2 horizontal— and:
///
/// * it is wider than the screen by a character on each side: 20 cells
///   across, 15 down. The runtime keeps a character's distance to the camera
///   inside one lap of the map, centred on the screen —`wrap_fold_x` in
///   `wrap.s`—, and a lap narrower than that would show it on both sides,
///   which takes the clones RM2k has and the console does not. Every map that
///   loops in the ports is at least that size;
/// * the map is not painted: a painted map's BG1 is uploaded by `painted.s`
///   from where the window is, and that does not know about laps. None of the
///   ports' is.
pub fn wrap_axes(m: &MapInfo) -> ((bool, bool), Vec<String>) {
    let asks_x = matches!(m.map.scroll_type, 2 | 3);
    let asks_y = matches!(m.map.scroll_type, 1 | 3);
    let painted = m.panorama_way.as_str() == Some("painted");
    let mut why = Vec::new();
    let mut fits = |asks: bool, size: i32, least: i32, axis: &str| {
        if !asks {
            return false;
        }
        if painted {
            why.push(format!(
                "it loops {axis} in RM2k, and a painted map does not loop on the console"
            ));
            return false;
        }
        if size < least {
            why.push(format!(
                "it loops {axis} in RM2k, and with {size} cells it is too small to loop on the \
                 console, which needs {least}"
            ));
            return false;
        }
        true
    };
    let x = fits(asks_x, m.map.width, 20, "across");
    let y = fits(asks_y, m.map.height, 15, "down");
    ((x, y), why)
}

/// A map as the emission takes it: see `Map` in its `request.rs`. `access`
/// is what it forbids, from [`access_bits`].
pub fn map_record(m: &MapInfo, access: u8) -> Value {
    json!({
        "id": m.id, "name": m.name,
        "access": access,
        "tilemap": [m.tilemap.0, m.tilemap.1],
        "size": [m.map.width, m.map.height], "start": [m.start.0, m.start.1],
        "layout": m.layout_name,
        "tiles": hex(&m.tile_data),
        "bpp": m.bpp,
        "panorama": m.panorama,
        "cgram": hex(&m.cgram),
        "above_tiles": hex(&m.above_tiles),
        "above_cgram": hex(&m.above_cgram), "above_first": m.above_first,
        "runs": m.runs,
        "cells": hex(&m.cells),
        "blocks": hex(&m.blocks),
        "block_pass": hex(&m.block_pass),
        "block_terrain": hex(&m.block_terrain),
        "terrain_outside": m.terrain_outside,
        "wrap": [wrap_axes(m).0 .0, wrap_axes(m).0 .1],
        "sprite": m.objects,
        "npcs": m.npcs, "movable": m.movable,
        "animates_still": m.animates_still,
        "animates_with": m.animates_with,
        "events": m.map.events.iter().map(|e| json!([e.x, e.y])).collect::<Vec<_>>(),
        // The cells that share another event's row, with that event's
        // index: see `trim::twins`.
        "twins": m.map.twins.iter().map(|&(x, y, owner)| {
            json!([x, y, m.map.events.iter().position(|e| e.id == owner)])
        }).collect::<Vec<_>>(),
        "pages": m.pages.iter().map(page_record).collect::<Vec<_>>(),
        "evcode": hex(&m.evcode),
        "changing": m.changing.iter().collect::<Vec<_>>(),
        "appearing": m.appearing.iter().collect::<Vec<_>>(),
        "turning": m.turning.iter().collect::<Vec<_>>(),
        // The `ShowPicture` pictures the map carries: where they start in
        // its sprite bank, and each one's half size, objects and colours.
        "pictures": m.pictures.as_ref().map(|(base, _table, images)| json!({"base": base, "images": images})),
    })
}

/// What the emission answered besides the `.inc`: what was shared and
/// compressed, and per map how many frames decompressing it takes.
pub struct Emitted {
    pub report: Vec<String>,
    pub frames: Vec<Value>,
    /// What the emission cut to fit —a ChipSet animation—, for the
    /// cartridge's degradations.
    pub losses: Vec<Value>,
}

/// Runs the emission and writes the `.inc` at `path`, with what the console
/// decompresses of each map, uncompressed, in `raw/` next to it.
pub fn emit(path: &std::path::Path, request: &Value, dump: &std::path::Path) -> Result<Emitted> {
    let directory = rm2k_project::absolute(path.parent().unwrap_or(std::path::Path::new(".")));
    let written = crate::stage::run(
        "rm2k-snes-mapdata",
        "mapdata",
        "emit",
        request,
        &[
            "--data".into(),
            dump.as_os_str().to_owned(),
            "--raw".into(),
            directory.join("raw").into_os_string(),
        ],
    )?;
    let text = crate::stage::text(&written, "mapdata.inc")?;
    std::fs::write(path, text).map_err(|e| crate::fail::io(path, e))?;
    let answer = crate::stage::json(&written, "mapdata.json")?;
    for note in answer["notes"].as_array().cloned().unwrap_or_default() {
        println!(
            "{}",
            note.as_str()
                .map_or_else(|| note.to_string(), str::to_string)
        );
    }
    Ok(Emitted {
        report: answer["report"]
            .as_array()
            .map(|r| {
                r.iter()
                    .map(|l| l.as_str().unwrap_or("").to_string())
                    .collect()
            })
            .unwrap_or_default(),
        frames: answer["frames"].as_array().cloned().unwrap_or_default(),
        losses: answer["losses"].as_array().cloned().unwrap_or_default(),
    })
}
