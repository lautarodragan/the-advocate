//! A cartridge's screens, whole: what the conversion asks for once per
//! cartridge, and what it answers.

use crate::borders::{self, compact_shop, compact_target, Borders};
use crate::cells::Color;
use crate::checks::{items_border_first, Vram};
use crate::end_game;
use crate::fail::{Bad, Result};
use crate::game::{Game, ITEM_MEDICINE};
use crate::items;
use crate::layout::{self, *};
use crate::message_window;
use crate::slots;
use crate::texts::{self, item_text, split_description};
use crate::title;
use serde_json::{json, Map, Value};
use voodoo::pack::Indices;

/// What the cartridge decided that the screens depend on.
#[derive(Debug, Clone, Default)]
pub struct Request {
    /// How many save slots there are.
    pub slots: usize,
    /// The actors that can be in the party: their faces go in the bank,
    /// and their names have to fit in what it leaves free.
    pub actors: Vec<i32>,
    /// The items the cartridge knows, in its order: their names and
    /// descriptions go as text.
    pub items: Vec<i32>,
    /// Whether the cartridge has a title screen.
    pub title: bool,
    /// Where what follows the message window starts in colour memory.
    pub cgram_reserved: usize,
    pub vram: Vram,
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

pub fn tiles_json(tiles: &[Indices]) -> Value {
    json!(tiles)
}

pub fn colors_json(colors: &[Color]) -> Value {
    json!(colors)
}

fn borders_json(b: &Borders) -> Value {
    json!({"tiles": tiles_json(&b.tiles), "colors": colors_json(&b.colors), "maps": b.maps})
}

fn glyphs_json(glyphs: &std::collections::BTreeMap<char, Vec<u16>>) -> Value {
    Value::Object(
        glyphs
            .iter()
            .map(|(c, w)| (c.to_string(), json!(w)))
            .collect::<Map<_, _>>(),
    )
}

/// The pairs of tiles a strip takes: as many columns as its letters reach,
/// from one pixel into its first cell. It is `tl_strip`'s count.
fn strip_tiles(game: &Game, stored: &str, cells: usize) -> usize {
    let text = texts::strip_text(&game.font, stored, cells);
    let width = SCR_TEXT_X + game.font.width(&text);
    if text.is_empty() {
        0
    } else {
        2 * width.div_ceil(crate::cells::CELL)
    }
}

/// That the names the menu, the actor choice and the slot screen compose fit
/// in what their bank leaves free: from its first even tile after `tiles`
/// up to its tilemap. The most a screen can ask for is counted: the menu
/// with the four longest names and the actor choice's longest medicine over
/// it, or a save in every slot with the longest leader.
///
/// Until 2026-10-03 the names went one letter per cell, from glyphs in the
/// bank: what cost was the letters, once. Composed, each name shown takes
/// tiles of its own.
fn strips_fit(game: &Game, request: &Request, medicines: &[(i32, String)], tiles: usize) -> Result<String> {
    let free = SLOT_TILES_MAX.saturating_sub(tiles.div_ceil(2) * 2);
    let mut names: Vec<usize> = Vec::new();
    let mut leaders = 0;
    for &actor in &request.actors {
        let stored = texts::name_text(game, actor, MENU_NAME_COLS)?;
        names.push(strip_tiles(game, &stored, MENU_NAME_COLS));
        leaders = leaders.max(strip_tiles(game, &stored, NAME_COLS));
    }
    names.sort_unstable_by(|a, b| b.cmp(a));
    let party: usize = names.iter().take(MENU_PARTY_ROWS).sum();
    let medicine = medicines
        .iter()
        .map(|(_, name)| {
            texts::name_in_lines(&game.font, name, TARGET_NAME_WIDTH, 2)
                .iter()
                .map(|line| strip_tiles(game, line, TARGET_NAME_WIDTH))
                .sum::<usize>()
        })
        .max()
        .unwrap_or(0);
    let need = (party + medicine).max(request.slots * leaders);
    if need > free {
        return Err(Bad::answer(format!(
            "the menu's bank has {tiles} tiles and leaves {free} free up to its tilemap, and the \
             composed names can ask for {need}: {party} the party's, {medicine} a medicine's and \
             {} the slot screen's",
            request.slots * leaders
        )));
    }
    Ok(format!(
        "  menu bank: {tiles} tiles of {SLOT_TILES_MAX}; the composed names ask for {need} of the {free} left"
    ))
}

/// Everything the conversion needs from the screens, and what it has to
/// say about them, in order.
pub fn convert(game: &Game, request: &Request) -> Result<Value> {
    let skin = game.skin()?;
    let mut says: Vec<String> = Vec::new();

    let window = message_window::convert(&skin, request.cgram_reserved)?;
    let font = message_window::font_bytes(&game.font)?;
    let prerender = message_window::font_prerender(&font, &window.color, window.shadow);

    let mut medicines = Vec::new();
    for &n in &request.items {
        if game.item(n)?.r#type.to_i32() == ITEM_MEDICINE {
            medicines.push((n, game.item_name(n)?));
        }
    }
    let slots = slots::slots_screen(game, &skin, request.slots, &request.actors)?;
    says.push(strips_fit(game, request, &medicines, slots.tiles.len())?);
    if !slots.lent.is_empty() {
        let names: Vec<String> = {
            let mut lent = slots.lent.clone();
            lent.sort();
            lent.iter().map(|a| game.actor_name(*a)).collect::<Result<_>>()?
        };
        says.push(format!(
            "  faces without a palette of their own, drawn with another's: {}",
            names.join(", ")
        ));
    }
    let target_screens = [borders::target_layer(game, &skin)?, borders::menu_bar_layer(&skin)];
    let target = borders::borders(&target_screens, 0, TARGET_CGRAM, TARGET_CGRAM + TARGET_COLORS_MAX)?;
    request.vram.target(target.tiles.len())?;
    let inks = items::text_inks(&skin, &game.font)?;
    // The item and equipment windows share tiles and colours, and go at the
    // end of the bank: the text has what is below them. Counted first, then
    // numbered from where they land.
    let border_screens = || [borders::item_layers(&skin), borders::equipment_layers(&skin)];
    let counted = borders::borders(&border_screens(), 0, ITEM_BORDER_CGRAM, 256)?;
    let first = items_border_first(counted.tiles.len());
    let items_border = borders::borders(&border_screens(), first, ITEM_BORDER_CGRAM, 256)?;
    request.vram.items_border(items_border.tiles.len(), 0)?;
    // The shop's, with their own tiles and colours.
    let shop_border = borders::borders(&borders::shop_layers(&skin), 0, ITEM_BORDER_CGRAM, TARGET_CGRAM)?;
    request.vram.shop(shop_border.tiles.len())?;
    // End Game's tiles go where the slot screen's do, so what is checked is
    // the same.
    let end = end_game::convert(game, &skin)?;
    request.vram.slots(end.tiles.len())?;
    request.vram.slots(slots.tiles.len())?;
    let title = if request.title { Some(title::menu(game, &skin)?) } else { None };

    let target_compact = compact_target(&target.maps)?;
    let shop_compact = compact_shop(&shop_border.maps)?;

    // What the cartridge composes as text: each actor's three strips, each
    // medicine's name in two lines, each item's name and description, the
    // equipment screen's terms and the shop's messages.
    let n_actors = request.actors.iter().copied().max().map_or(0, |m| m + 1).max(0);
    let actor_texts: Vec<Value> = (0..n_actors)
        .map(|a| {
            Ok(json!([
                texts::name_text(game, a, MENU_NAME_COLS)?,
                texts::level_text(game, a, None),
                texts::max_text(game, a, None)
            ]))
        })
        .collect::<Result<_>>()?;
    let mut item_texts = Vec::new();
    for &n in &request.items {
        let item = game.item(n)?;
        let mut lines = vec![item_text(&game.item_name(n)?, ITEM_NAME_WIDTH)];
        lines.extend(split_description(&game.font, &game.item_description(n)?));
        item_texts.push(json!({
            "number": n,
            "texts": lines,
            "usable": texts::item_usable(item),
            "needs_actor": texts::item_needs_actor(item),
        }));
    }
    let medicine_names: Vec<Value> = medicines
        .iter()
        .map(|(n, name)| json!({"number": n, "lines": texts::name_in_lines(&game.font, name, TARGET_NAME_WIDTH, 2)}))
        .collect();
    let params: Vec<String> = ["attack", "defense", "spirit", "agility"]
        .iter()
        .map(|t| Ok(game.term(t)?.chars().take(EQ_PARAM_VALUE - 1).collect()))
        .collect::<Result<_>>()?;
    let equipment: Vec<String> = ["weapon", "shield", "armor", "helmet", "accessory"]
        .iter()
        .map(|t| Ok(game.term(t)?.chars().take(EQ_SLOT_TERM_WIDTH).collect()))
        .collect::<Result<_>>()?;
    let mut shop = Vec::new();
    for set in 0..TI_TERM_SETS {
        let mut messages = Vec::new();
        for (k, term) in TI_TERMS.iter().enumerate() {
            let text = game.term(&format!("{term}{}", set + 1))?;
            let lines = split_description(&game.font, &text);
            // Outside the main screen, the message goes in a one-line
            // window.
            if !lines[1].is_empty() && k >= 2 {
                return Err(Bad::answer(format!(
                    "the shop message {text:?}, of set {set}, takes two lines and its window has one"
                )));
            }
            messages.push(lines);
        }
        shop.push(messages);
    }

    let menu = &slots.menu;
    Ok(json!({
        "window": {
            "tiles": hex(&window.tiles),
            "cgram": window.cgram,
            "cells": window.cells,
            "base": window.base,
            "background": hex(&window.background),
            "color": window.color,
            "shadow": window.shadow,
            "font": hex(&font),
            "advances": game.font.console_advances(),
            "reach": message_window::font_reach(&game.font),
            "prerender": prerender.iter().map(|t| hex(t)).collect::<Vec<_>>(),
        },
        "title": title.map(|t| json!({
            "texts": t.texts,
            "tiles": tiles_json(&t.tiles),
            "palette": colors_json(&t.palette),
            "tilemaps": t.tilemaps,
        })),
        "slots": {
            "tiles": tiles_json(&slots.tiles),
            "palettes": slots.palettes,
            "headers": slots.headers,
            "rows": slots.rows,
            "faces": Value::Object(slots.faces.iter().map(|(a, c)| (a.to_string(), json!(c))).collect()),
            "menu": {
                "options": menu.options,
                "cursor": menu.cursor,
                "glyphs": glyphs_json(&menu.glyphs),
                "currency": menu.currency,
                "row": menu.row,
                "exp_term": menu.exp_term,
            },
            "prerender": slots.prerender.iter().map(|t| hex(t)).collect::<Vec<_>>(),
        },
        "text_inks": {
            "palettes": inks.palettes,
            "prerender": inks.prerender.iter().map(|t| hex(t)).collect::<Vec<_>>(),
        },
        "items_border": borders_json(&items_border),
        "items_border_first": first,
        "shop_border": {
            "tiles": tiles_json(&shop_border.tiles),
            "colors": colors_json(&shop_border.colors),
            "rows": shop_compact.rows,
            "top": shop_compact.top,
            "layers": shop_compact.layers,
            "patches": shop_compact.patches,
            "bars": shop_compact.bars,
        },
        "target": {
            "tiles": tiles_json(&target.tiles),
            "colors": colors_json(&target.colors),
            "map": target_compact.map,
            "bars": target_compact.bars,
            "row0": target_compact.row0,
            "rows": target_compact.rows,
            "col0": target_compact.col0,
            "cols": target_compact.cols,
            "menu_bar": target_compact.menu_bar,
            "menu_bar_at": [
                target_compact.menu_bar_at.0,
                target_compact.menu_bar_at.1,
                target_compact.menu_bar_at.2,
                target_compact.menu_bar_at.3
            ],
        },
        "end_game": {
            "tiles": tiles_json(&end.tiles),
            "rows": end.rows,
            "row0": end.row0,
            "palettes": end.palettes,
        },
        "texts": {
            "actors": actor_texts,
            "items": item_texts,
            "medicines": medicine_names,
            "params": params,
            "equipment": equipment,
            "shop": shop,
            "owned": game.term(TI_TERM_OWNED)?,
            "carried": game.term(TI_TERM_CARRIED)?,
            "currency": game.term("gold")?,
        },
        "layout": layout::publish(),
        "says": says,
    }))
}
