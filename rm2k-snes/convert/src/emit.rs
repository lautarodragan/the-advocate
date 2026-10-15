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
        "sprite": m.objects,
        "npcs": m.npcs, "movable": m.movable,
        "animates_still": m.animates_still,
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
        println!("{}", note.as_str().map_or_else(|| note.to_string(), str::to_string));
    }
    Ok(Emitted {
        report: answer["report"]
            .as_array()
            .map(|r| r.iter().map(|l| l.as_str().unwrap_or("").to_string()).collect())
            .unwrap_or_default(),
        frames: answer["frames"].as_array().cloned().unwrap_or_default(),
    })
}
