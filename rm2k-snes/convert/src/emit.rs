//! The emission, which is `rm2k-snes-mapdata emit`: what goes into its
//! request. It writes the whole `.inc` —the header of constants, the
//! tables of every map, the window and the font, the screens, the menus,
//! the battle, what the save game is signed with— from what every domain
//! of the conversion answered, which is what the request carries.

use crate::fail::{Result, Stop};
use crate::maps::{MapInfo, PageRecord};
use rm2k_snes_mapdata::request;
use serde::de::DeserializeOwned;
use serde_json::Value;

/// A piece of the request some stage answered as JSON, as the emission's
/// type: what the emission itself did when it read the request.
pub fn typed<T: DeserializeOwned>(value: &Value) -> Result<T> {
    serde_json::from_value(value.clone()).map_err(|e| {
        Stop::new(format!(
            "rm2k-snes-mapdata: the request: {e} in {}",
            short(value)
        ))
    })
}

fn short(value: &Value) -> String {
    let text = value.to_string();
    match text.char_indices().nth(60) {
        Some((at, _)) => format!("{}…", &text[..at]),
        None => text,
    }
}

/// A page as the emission takes it.
pub fn page_record(page: &PageRecord) -> Result<request::Page> {
    let own_route = page.own_route.as_ref().map(|own| request::OwnRoute {
        repeats: own.repeats,
        skippable: own.skippable,
        fixed_direction: own.fixed_direction,
        animation_continues: own.animation_continues,
        spin: own.spin,
        by_type: own.by_type,
        pattern: own.pattern.unwrap_or(1).into(),
        frequency: own.frequency.into(),
        speed: own.speed.into(),
        orders: own.commands.len(),
    });
    Ok(request::Page {
        event: page.event,
        page: page.page,
        trigger: page.trigger,
        switch_a: page.switch_a.into(),
        switch_b: page.switch_b.into(),
        actor: page.actor.into(),
        layer: page.layer.into(),
        item: page.item.into(),
        has_code: page.has_code,
        offset: page.offset,
        route_offset: page.route_offset,
        frequency: page.frequency.into(),
        speed: page.speed.into(),
        fixed_direction: page.fixed_direction,
        fixed_graphic: page.fixed_graphic,
        own_route,
        draws: page.draws.as_ref().map(typed).transpose()?,
        variable: page.variable,
        graphic: page.graphic.clone(),
        turns: page.turns,
        pure: page.pure,
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
pub fn map_record(m: &MapInfo, access: u8) -> Result<request::Map> {
    let ((wrap_x, wrap_y), _) = wrap_axes(m);
    let events = &m.map.events;
    Ok(request::Map {
        id: m.id.into(),
        name: m.name.clone(),
        access,
        tilemap: [m.tilemap.0 as i64, m.tilemap.1 as i64],
        size: [m.map.width.into(), m.map.height.into()],
        start: [m.start.0, m.start.1],
        layout: m.layout_name.clone(),
        tiles: m.tile_data.clone(),
        bpp: m.bpp as usize,
        panorama: m.panorama.as_ref().map(typed).transpose()?,
        cgram: m.cgram.clone(),
        above_tiles: m.above_tiles.clone(),
        above_cgram: m.above_cgram.clone(),
        above_first: m.above_first,
        runs: m.runs.iter().map(typed).collect::<Result<_>>()?,
        cells: m.cells.clone(),
        blocks: m.blocks.clone(),
        block_pass: m.block_pass.clone(),
        block_terrain: m.block_terrain.clone(),
        terrain_outside: m.terrain_outside.into(),
        wrap: [wrap_x, wrap_y],
        sprite: typed(&m.objects)?,
        npcs: typed(&m.npcs)?,
        movable: typed(&m.movable)?,
        posed: typed(&m.posed_table)?,
        animates_still: typed(&m.animates_still)?,
        animates_with: typed(&m.animates_with)?,
        events: events.iter().map(|e| [e.x.into(), e.y.into()]).collect(),
        // The cells that share another event's row, with that event's
        // index: see `trim::twins`.
        twins: m
            .map
            .twins
            .iter()
            .map(|&(x, y, owner)| {
                let index = events.iter().position(|e| e.id == owner).ok_or_else(|| {
                    Stop::new(format!(
                        "map {}: a twin of event {owner}, which it does not have",
                        m.id
                    ))
                })?;
                Ok([x.into(), y.into(), index as i64])
            })
            .collect::<Result<_>>()?,
        pages: m.pages.iter().map(page_record).collect::<Result<_>>()?,
        evcode: m.evcode.clone(),
        changing: m.changing.iter().copied().collect(),
        appearing: m.appearing.iter().copied().collect(),
        turning: m.turning.iter().copied().collect(),
        // The `ShowPicture` pictures the map carries: where they start in
        // its sprite bank, and each one's half size, objects and colours.
        pictures: match &m.pictures {
            None => None,
            Some((base, _table, images)) => Some(request::MapPictures {
                base: typed(base)?,
                images: images.iter().map(typed).collect::<Result<_>>()?,
            }),
        },
        // Not the converter's: the emission decides it, see
        // `layer_text::bake_all` in rm2k-snes-mapdata.
        layer_text: 0,
        // The ChipSets its pages swap in, each converted over its grid: see
        // `variants.rs`.
        variants: m
            .variants
            .iter()
            .map(crate::variants::Variant::request)
            .collect::<Result<_>>()?,
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

/// The emission, a function of `rm2k-snes-mapdata`.
const EMIT: crate::stage::Stage = crate::stage::Stage {
    binary: "rm2k-snes-mapdata",
    command: "emit",
};

/// Runs the emission and writes the `.inc` at `path`, with what the console
/// decompresses of each map, uncompressed, in `raw/` next to it.
pub fn emit(
    path: &std::path::Path,
    request: request::Emit,
    dump: &std::path::Path,
) -> Result<Emitted> {
    let directory = rm2k_project::absolute(path.parent().unwrap_or(std::path::Path::new(".")));
    // Not from the disk cache, which never kept it: it is asked once per
    // cartridge, and its request carries what every other stage answered,
    // so it changes whenever any of them does.
    let written =
        crate::stage::call_uncached(EMIT, || rm2k_snes_mapdata::stage::emit(dump, request))?;
    let raw = written
        .iter()
        .filter_map(|(name, bytes)| {
            let name = name.strip_prefix(rm2k_snes_mapdata::stage::RAW)?;
            Some((name.to_string(), bytes.clone()))
        })
        .collect();
    rm2k_snes_mapdata::materials::write_raw(&directory.join("raw"), &raw)
        .map_err(|bad| crate::fail::Stop::new(bad.to_string()))?;
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
