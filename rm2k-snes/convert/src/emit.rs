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
use wally::answer;

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
        draws: page.draws.clone(),
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
    let painted = m.panorama_way.as_deref() == Some("painted");
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

/// The objects as the emission takes them: what Wally answered, with the
/// bank's tiles and each character's poses, which its answer names as
/// files, as their bytes.
pub fn sprite(s: &answer::Sprite, tiles: Vec<u8>, banks: Vec<request::Bank>) -> request::Sprite {
    request::Sprite {
        tiles,
        palettes: s.palettes.clone(),
        place: s
            .place
            .iter()
            .map(|(slot, block, palette)| (slot.clone(), *block as u32, *palette as u32))
            .collect(),
        actors: s
            .actors
            .iter()
            .map(|(actor, palette, entry, colors)| {
                let colors = colors.iter().map(|&c| u32::from(c)).collect();
                (i64::from(*actor), *palette as i64, *entry, colors)
            })
            .collect(),
        timer: s
            .timer
            .map(|(tile, palette)| (tile as i64, Some(palette as i64))),
        timer_mask: s.timer_mask.into(),
        animated: s
            .animated
            .iter()
            .map(|(charset, index)| (charset.clone(), i64::from(*index)))
            .collect(),
        animated_palettes: s.animated_palettes.iter().map(|&p| p as i64).collect(),
        banks,
        route_gfx: s.route_gfx.clone(),
        rain: (s.rain.0 as i64, s.rain.1 as i64),
        sand: s.sand.map(|(t, p, e)| (t as i64, p as i64, e as i64)),
        turn_block: s.turn_block.map(|b| b as u32),
        image: (s.image.0 as i64, s.image.1 as i64),
        animation: s.animation,
        shared: s.shared.clone(),
        cache: s.cache.clone(),
    }
}

/// The panorama as the emission takes it: what Wally answered, with its
/// tiles and each other image's, which its answer names as files, as their
/// bytes —`tiles`, the map's first—.
fn panorama(p: &answer::Panorama, tiles: &[Vec<u8>]) -> request::Panorama {
    let pair = |(a, b): (usize, usize)| [a as i64, b as i64];
    request::Panorama {
        name: p.name.clone(),
        mode: p.mode,
        size: pair(p.size),
        stretch: pair(p.stretch),
        looped: [p.looped.0, p.looped.1],
        auto: [p.auto.0.into(), p.auto.1.into()],
        tiles: tiles[0].clone(),
        tilemap: p.tilemap.clone(),
        backdrop: p.backdrop,
        above_bg1: p.above_bg1,
        first: p.first,
        cgram: p.cgram.clone(),
        images: p
            .images
            .iter()
            .zip(&tiles[1..])
            .map(|(image, tiles)| request::PanoramaImage {
                name: image.name.clone(),
                size: pair(image.size),
                stretch: pair(image.stretch),
                tiles: tiles.clone(),
                tilemap: image.tilemap.clone(),
                backdrop: image.backdrop,
                first: image.first,
                cgram: image.cgram.clone(),
            })
            .collect(),
        none_first: p.none_first,
    }
}

/// A drawn event as the emission takes it: the part of Wally's row it
/// reads.
fn npc(row: &answer::Row) -> request::Npc {
    let n = &row.npc;
    request::Npc {
        event: n.event as i64,
        x: n.x.into(),
        y: n.y.into(),
        charset: n.charset.clone(),
        index: n.index.into(),
        pose: n.pose.into(),
        layer: n.layer.into(),
        speed: n.speed.into(),
        visible: n.visible,
        translucent: n.translucent,
        tile_pass: n.tile_pass.map(i64::from),
        posed: row.posed.map(|(p, g)| [p as i64, g as i64]),
    }
}

/// Events by their index, as the emission numbers them.
fn indices<'a>(events: impl IntoIterator<Item = &'a usize>) -> Vec<i64> {
    events.into_iter().map(|&e| e as i64).collect()
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
        panorama: m.panorama.as_ref().map(|p| panorama(p, &m.panorama_tiles)),
        cgram: m.cgram.clone(),
        above_tiles: m.above_tiles.clone(),
        above_cgram: m.above_cgram.clone(),
        above_first: m.above_first,
        runs: m.runs.clone(),
        cells: m.cells.clone(),
        blocks: m.blocks.clone(),
        block_pass: m.block_pass.clone(),
        block_terrain: m.block_terrain.clone(),
        terrain_outside: m.terrain_outside.into(),
        wrap: [wrap_x, wrap_y],
        sprite: Some(m.sprite.clone()),
        npcs: m.npcs.iter().map(npc).collect(),
        movable: indices(&m.movable),
        posed: m.posed_table.clone(),
        animates_still: indices(&m.animates_still),
        animates_with: m
            .animates_with
            .iter()
            .map(|&(e, whose)| [e as i64, whose as i64])
            .collect(),
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
        pictures: m
            .pictures
            .as_ref()
            .map(|(base, _table, images)| request::MapPictures {
                base: *base,
                images: images.clone(),
            }),
        // Not the converter's: the emission decides it, see
        // `layer_text::bake_all` in rm2k-snes-mapdata.
        layer_text: 0,
        // The ChipSets its pages swap in, each converted over its grid: see
        // `variants.rs`.
        variants: m
            .variants
            .iter()
            .map(crate::variants::Variant::request)
            .collect(),
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
