//! Two questions about a map that a whole conversion answers without
//! saying: which events can be baked and why that is safe, and how the
//! object palettes are split with a given number of them. They exist for
//! whoever checks those decisions against a real game —its tests—, which
//! have no other way to see them: nothing on screen shows a passability, or
//! a palette nobody else shares.

use crate::baking::{self, bakeable};
use crate::events::{collect_npcs, events, UPPER_BASE};
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::map::MapRequest;
use crate::moves::moves;
use crate::sheets::Drawer;
use rm2k_render::picture;
use rm2k_rules::chipset::passability_table;
use rm2k_rules::charset::{OFFSET_X, OFFSET_Y};
use rm2k_rules::passability::cell;
use crate::sprites::extras::timer_colors;
use crate::sprites::npc::map_poses;
use crate::sprites::split::{drawable_npcs, Ask};
use serde_json::{json, Value};

/// The alpha of the 16x16 pixels of upper tile `index`, as the event's sheet
/// has it standing on its cell.
fn alphas(drawer: &mut Drawer, chipset: &str, index: i32) -> Result<Option<Vec<u8>>> {
    let name = crate::events::tile_name(chipset, index);
    Ok(drawer.draw(&name)?.map(|sheet| {
        let (x, y) = (-OFFSET_X as i64, -OFFSET_Y as i64);
        (0..16)
            .flat_map(|dy| (0..16).map(move |dx| (dx, dy)))
            .map(|(dx, dy)| sheet.get(x + dx, y + dy)[3])
            .collect()
    }))
}

/// Which events of the map can be baked: for each, its cell and tile, the
/// passage bits its row imposed, and what the map's table says of the cell
/// once the tile is in it; and the alpha of the empty tile and of each
/// baked one.
pub fn bakeable_report(game: &Game, request: &MapRequest) -> Result<Value> {
    let raw = game.map(request.map)?;
    let chipset = game.chipset(raw.chipset_id)?;
    let flags = passability_table(&chipset.passable_data_lower, &chipset.passable_data_upper);
    let events = events(&raw.events, &request.names, request.test_event);
    let npcs = collect_npcs(&events, &chipset.chipset_name, &flags);
    let lower: Vec<i32> = raw.lower_layer.iter().map(|&t| t as i32).collect();
    let upper: Vec<i32> = raw.upper_layer.iter().map(|&t| t as i32).collect();
    let mut drawer = Drawer::new(game, &request.dither);
    let map = baking::Map {
        width: raw.width as usize,
        lower: &lower,
        upper: &upper,
        flags: &flags,
        chipset: &chipset.chipset_name,
    };
    let baked = bakeable(&mut drawer, &map, &events, &npcs)?;
    let mut rows = Vec::new();
    for (event, (at, tile)) in &baked {
        let imposed = npcs.iter().find(|n| n.event == *event).and_then(|n| n.tile_pass);
        rows.push(json!({
            "event": event, "cell": at, "tile": tile, "imposed": imposed,
            "after": cell(&flags, lower[*at], *tile),
            "alphas": alphas(&mut drawer, &chipset.chipset_name, tile - UPPER_BASE)?,
        }));
    }
    Ok(json!({
        "baked": rows,
        "tile_zero": alphas(&mut drawer, &chipset.chipset_name, 0)?,
    }))
}

/// How the object palettes are split with `palettes` of them, and which
/// events are drawn.
pub fn split_report(game: &Game, request: &MapRequest, palettes: usize) -> Result<Value> {
    let raw = game.map(request.map)?;
    let chipset = game.chipset(raw.chipset_id)?;
    let flags = passability_table(&chipset.passable_data_lower, &chipset.passable_data_upper);
    let events = events(&raw.events, &request.names, request.test_event);
    let npcs = collect_npcs(&events, &chipset.chipset_name, &flags);
    let actors = game.actors()?;
    let leaders: Vec<(String, i32)> = request
        .leaders
        .iter()
        .map(|a| actors.get(a).cloned().ok_or_else(|| Bad::answer(format!("actor {a} is not in the database"))))
        .collect::<Result<_>>()?;
    let who = moves(&request.pages, &events, &npcs, &chipset.chipset_name, &request.also_walk, crate::moves::Animate::ALL);
    let poses = map_poses(
        &leaders,
        &npcs,
        &who.movable,
        &who.turning,
        &request.route_graphics,
        &who.animates_still,
    );
    let mut drawer = Drawer::new(game, &request.dither);
    let mut names: Vec<String> = leaders.iter().map(|k| k.0.clone()).collect();
    names.extend(npcs.iter().flat_map(|n| n.keys()).map(|k| k.0));
    names.extend(request.route_graphics.iter().map(|k| k.0.clone()));
    for name in &names {
        drawer.draw(name)?;
    }
    let timer = match &request.timer {
        Some(path) => timer_colors(&rm2k_render::system::timer(&picture::read_rm2k(path)?)),
        None => Vec::new(),
    };
    let sheets = drawer.sheets().clone();
    let d = drawable_npcs(
        &Ask {
            sheets: &sheets,
            leaders: &leaders,
            cap: palettes,
            route_graphics: &request.route_graphics,
            hero_graphics: &request.hero_graphics,
            timer_colors: &timer,
            only_here: &request.singles,
            poses: &poses,
            weights: &request.weights,
        },
        npcs,
    )
    .map_err(|b| Bad::answer(b.0))?;
    let s = &d.split;
    Ok(json!({
        "npcs": d.npcs.iter().map(|n| json!({"event": n.event, "charset": n.charset, "index": n.index})).collect::<Vec<_>>(),
        "discarded": d.discarded.iter().map(|(e, c)| json!([e, c])).collect::<Vec<_>>(),
        "palettes": s.palettes,
        "palette_of": s.palette_of.iter().map(|(k, n)| json!([k.0, k.1, n])).collect::<Vec<_>>(),
        "leader_owned": s.leader_owned,
        "shared_leaders": s.shared_leaders.iter().map(|k| json!([k.0, k.1])).collect::<Vec<_>>(),
        "lent": s.lent.iter().map(|k| json!([k.0, k.1])).collect::<Vec<_>>(),
        "notes": d.notes,
    }))
}
