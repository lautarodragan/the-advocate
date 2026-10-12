//! A cartridge's screens, whole: what the conversion asks for once per
//! cartridge, and what it answers.

use crate::borders::{self, compact_shop, compact_target, Borders};
use crate::cells::Color;
use crate::checks::{items_border_first, Vram, TEXT_POOL_PAIRS};
use crate::render;
use crate::end_game;
use crate::fit;
use crate::fail::{Bad, Result};
use crate::game::Game;
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
    /// The custom menus the project declares, by name, each its file as
    /// JSON, in the order the cartridge numbers them; and what the
    /// cartridge decided they need —see `custom_menu`—.
    pub menus: Vec<(String, Value)>,
    pub menu_context: crate::custom_menu::Context,
    /// The glyph rows the message window's text takes an entry each for,
    /// the same in every System the cartridge switches between, or None if
    /// it never switches: see `message_window::TextRows`. The `window`
    /// subcommand answers it.
    pub text_rows: Option<message_window::TextRows>,
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

/// The tiles a bank's names can take, counted from its first even tile
/// after `tiles` up to its tilemap.
fn free_after(tiles: usize) -> usize {
    SLOT_TILES_MAX.saturating_sub(tiles.div_ceil(2) * 2)
}

/// What the names the menu, the actor choice and the slot screen compose
/// ask for at most: the menu with the four longest names and the actor
/// choice's longest medicine over it, and a save in every slot with the
/// longest leader. `(party, medicine, slots)`.
///
/// Until 2026-10-03 the names went one letter per cell, from glyphs in the
/// bank: what cost was the letters, once. Composed, each name shown takes
/// tiles of its own.
fn strips_asked(game: &Game, request: &Request, medicines: &[(i32, String)]) -> Result<(usize, usize, usize)> {
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
    Ok((party, medicine, request.slots * leaders))
}

/// Whether the names fit in what `bank` leaves free: the menu's after the
/// tiles it shows, the slot screen's after all of them.
fn strips_fit(asked: (usize, usize, usize), bank: &slots::Slots) -> bool {
    let (party, medicine, slots) = asked;
    party + medicine <= free_after(bank.menu_tiles) && slots <= free_after(bank.tiles.len())
}

/// The slot screen and the menu's bank, in the order that leaves room for
/// their composed names: as they are drawn, and if that does not, with the
/// slot screen's text last —see [`slots::Order`]—. What the error says is
/// what is missing in the second.
fn slots_with_room(
    game: &Game,
    skin: &crate::game::Skin,
    request: &Request,
    medicines: &[(i32, String)],
    custom: &[String],
) -> Result<(slots::Slots, String)> {
    let asked = strips_asked(game, request, medicines)?;
    let (party, medicine, slot_names) = asked;
    let mut bank =
        slots::slots_screen_with(game, skin, request.slots, &request.actors, slots::Order::Drawn, custom)?;
    let mut order = "";
    if !strips_fit(asked, &bank) {
        bank =
            slots::slots_screen_with(game, skin, request.slots, &request.actors, slots::Order::MenuFirst, custom)?;
        order = ", the slot screen's text last";
    }
    let tiles = bank.tiles.len();
    let menu_free = free_after(bank.menu_tiles);
    let slot_free = free_after(tiles);
    if !strips_fit(asked, &bank) {
        return Err(Bad::answer(format!(
            "the menu's bank has no room for the composed names, even with the slot screen's text \
             last: the menu shows {} tiles and leaves {menu_free} free up to its tilemap, and its \
             names can ask for {}: {party} the party's and {medicine} a medicine's; the slot \
             screen shows {tiles} and leaves {slot_free}, and its leaders can ask for {slot_names}",
            bank.menu_tiles,
            party + medicine,
        )));
    }
    Ok((
        bank,
        format!(
            "  menu bank: {tiles} tiles of {SLOT_TILES_MAX}{order}; the composed names ask for \
             {} of the {menu_free} the menu leaves and {slot_names} of the {slot_free} the slot \
             screen does",
            party + medicine
        ),
    ))
}

/// What a place leaves out of the names it writes in counted cells: for
/// each name it cuts, the name, the pixels it takes and what shows. The
/// console cuts what does not fit and says nothing, so it is the converter
/// that names them. A warning and not an error, as with the other things a
/// cartridge carries less of than the game: the screen still works.
///
/// Since 2026-10-03: with `[text] letter_spacing` above 0 every name grows,
/// and which ones stop fitting depends on the knob.
pub fn cut_names(font: &rm2k_snes_text::font::Font, place: &str, room: &str, cut: &[(String, String)]) -> Option<String> {
    if cut.is_empty() {
        return None;
    }
    let names: Vec<String> = cut
        .iter()
        .map(|(full, shown)| format!("{full:?} {} px, shows {shown:?}", font.width(full)))
        .collect();
    Some(format!(
        "  WARNING, {} {place} don't fit in {room} and are cut: {}",
        cut.len(),
        names.join("; ")
    ))
}

/// The names the menu, the actor choice, the slot screen and the
/// equipment screen write in counted cells, and which of them are cut.
fn names_in_cells(game: &Game, request: &Request, medicines: &[(i32, String)]) -> Result<Vec<String>> {
    let font = &game.font;
    let mut says = Vec::new();
    let mut actor_names = Vec::new();
    for &actor in &request.actors {
        actor_names.push(item_text(&game.actor_name(actor)?, usize::MAX));
    }
    for (place, cells) in [("actor names in the menu", MENU_NAME_COLS), ("leader names in the slot screen", NAME_COLS)] {
        let cut: Vec<(String, String)> = actor_names
            .iter()
            .map(|name| (name.clone(), texts::strip_text(font, &texts::ljust(name, cells), cells)))
            .filter(|(name, shown)| shown != name.trim_end())
            .collect();
        says.extend(cut_names(font, place, &format!("{cells} cells ({} px)", 8 * cells), &cut));
    }
    let cut: Vec<(String, String)> = medicines
        .iter()
        .filter_map(|(_, name)| {
            let lines = texts::name_in_lines(font, name, TARGET_NAME_WIDTH, 2);
            let shown: Vec<&str> = lines.iter().map(|l| l.trim_end()).filter(|l| !l.is_empty()).collect();
            let shown = shown.join(" / ");
            // A word may go on in the next line: what counts is that every
            // letter shows.
            let letters = |t: &str| t.chars().filter(|c| !c.is_whitespace()).collect::<String>();
            (letters(&lines.concat()) != letters(&item_text(name, usize::MAX))).then(|| (name.clone(), shown))
        })
        .collect();
    says.extend(cut_names(
        font,
        "medicine names in the actor choice",
        &format!("two lines of {TARGET_NAME_WIDTH} cells"),
        &cut,
    ));
    let mut cut = Vec::new();
    for &n in &request.items {
        let kind = game.item(n)?.r#type.to_i32();
        // RM2k's weapon, shield, armor, helmet and accessory: what an
        // equipment slot shows.
        if !(1..=5).contains(&kind) {
            continue;
        }
        let name = item_text(&game.item_name(n)?, usize::MAX);
        let shown = texts::fit_cells(font, &item_text(&name, ITEM_NAME_WIDTH), EQ_SLOT_NAME_WIDTH);
        if shown != name {
            cut.push((name, shown));
        }
    }
    says.extend(cut_names(
        font,
        "equipment names in the equipment screen",
        &format!("{EQ_SLOT_NAME_WIDTH} cells ({} px)", 8 * EQ_SLOT_NAME_WIDTH),
        &cut,
    ));
    Ok(says)
}

/// What the shop's busiest lists ask of the text layer's pool of pairs of
/// tiles —see `rm2k_snes_text::cells`—: buying and selling, with the
/// widest names of the items the cartridge knows in every row, the widest
/// description over them, and every count and the gold at their widest.
/// An upper bound: a shop sells a few, and a party owns what it owns.
fn shop_pairs(game: &Game, skin: &crate::game::Skin, request: &Request) -> Result<usize> {
    let font = &game.font;
    let mut by_name: Vec<(usize, i32)> = Vec::new();
    let mut widest_description = (0, None);
    for &n in &request.items {
        let name = item_text(&game.item_name(n)?, ITEM_NAME_WIDTH);
        by_name.push((font.width(&name), n));
        let description: usize =
            split_description(font, &game.item_description(n)?).iter().map(|l| font.width(l)).sum();
        widest_description = widest_description.max((description, Some(n)));
    }
    by_name.sort_by(|a, b| b.cmp(a));
    let mut most = 0;
    for (mode, rows) in [(TI_BUY, TI_LIST_ROWS_BUY), (TI_SELL, TI_LIST_ROWS_SALE)] {
        let mut list: Vec<i32> = widest_description.1.into_iter().collect();
        list.extend(by_name.iter().map(|(_, n)| *n).filter(|n| Some(*n) != widest_description.1));
        list.truncate(rows);
        for term_set in 0..TI_TERM_SETS {
            let shop = render::Shop {
                kind: 0,
                term_set,
                sells: list.clone(),
                gold: 999_999,
                inventory: list.iter().map(|&n| (n, 99)).collect(),
                party_equipment: Vec::new(),
                mode,
                chosen: 0,
                top: 0,
                count: 99,
                regreeting: false,
                known: None,
            };
            most = most.max(render::shop_text(game, skin, &shop)?.0.pairs(font));
        }
    }
    Ok(most)
}

/// What the item screen's busiest list asks of the pool, as [`shop_pairs`]
/// does for the shop: the widest names in every row, every count at 99, and
/// the widest description over them. Its pool is what the item and
/// equipment windows leave below them —see `items_border_first`—, so a
/// System whose windows take many tiles leaves less.
pub fn item_pairs(game: &Game, skin: &crate::game::Skin, items: &[i32]) -> Result<usize> {
    let font = &game.font;
    let mut by_name: Vec<(usize, i32)> = Vec::new();
    let mut widest_description = (0, None);
    for &n in items {
        let name = item_text(&game.item_name(n)?, ITEM_NAME_WIDTH);
        by_name.push((font.width(&name), n));
        let description: usize =
            split_description(font, &game.item_description(n)?).iter().map(|l| font.width(l)).sum();
        widest_description = widest_description.max((description, Some(n)));
    }
    by_name.sort_by(|a, b| b.cmp(a));
    let mut list: Vec<i32> = widest_description.1.into_iter().collect();
    list.extend(by_name.iter().map(|(_, n)| *n).filter(|n| Some(*n) != widest_description.1));
    list.truncate(ITEM_ROWS);
    list.sort_unstable();
    let chosen = widest_description.1.and_then(|w| list.iter().position(|&n| n == w)).unwrap_or(0);
    let inventory = list.iter().map(|&n| (n, 99)).collect();
    Ok(render::item_screen_text(game, skin, &inventory, chosen, 0, Some(&list))?.0.pairs(font))
}

/// The message window as the emission takes it, without the font: what
/// changes from one System to another.
pub fn window_json(window: &message_window::Window) -> Value {
    json!({
        "tiles": hex(&window.tiles),
        "cgram": window.cgram,
        "cells": window.cells,
        "base": window.base,
        "background": hex(&window.background),
        "color": window.color,
        "shadow": window.shadow,
        "arrow": window.arrow,
        "bar": hex(&window.bar),
        "bar_bare": hex(&window.bar_bare),
    })
}

/// What a screen whose windows had to be redrawn says: see `fit`.
fn fused_windows(whose: &str, tiles: Option<(usize, usize)>) -> Option<String> {
    tiles.map(|(from, to)| {
        format!(
            "  WARNING, {whose} windows take {from} tiles as RM2k draws them and their bank holds {to}: \
             the cells that show the least were merged into their nearest, and they are drawn worse"
        )
    })
}

/// Everything the conversion needs from the screens, and what it has to
/// say about them, in order.
pub fn convert(game: &Game, request: &Request) -> Result<Value> {
    let skin = game.skin()?;
    let mut says: Vec<String> = Vec::new();

    let window = message_window::convert_with(&skin, request.cgram_reserved, request.text_rows.as_ref())?;
    if let Some(had) = window.frame_fused {
        says.push(format!(
            "  WARNING, the message window's frame and arrow took {had} tiles and the text area leaves \
             {}: the background seen through the frame was fused into bands, and it is drawn worse",
            message_window::FRAME_TILES_MAX
        ));
    }
    let font = message_window::font_bytes(&game.font)?;
    let prerender = message_window::font_prerender(&font, &window.color, window.shadow);

    // The items the actor choice opens for, whose names it writes: the
    // medicines, and since 2026-10-04 the materials.
    let mut medicines = Vec::new();
    for &n in &request.items {
        if texts::item_needs_actor(game.item(n)?) {
            medicines.push((n, game.item_name(n)?));
        }
    }
    let menus = crate::custom_menu::read_all(game, &request.menus)?;
    let labels: Vec<String> = menus.iter().map(|m| m.label.clone()).collect();
    for label in &labels {
        let taken = game.font.width(label);
        if taken > MENU_OPT_COLS * crate::cells::CELL {
            says.push(format!(
                "  WARNING, the custom menu option {label:?} takes {taken} px and the menu's column {}",
                MENU_OPT_COLS * crate::cells::CELL
            ));
        }
    }
    let (slots, said) = slots_with_room(game, &skin, request, &medicines, &labels)?;
    says.push(said);
    says.extend(names_in_cells(game, request, &medicines)?);
    let shop = shop_pairs(game, &skin, request)?;
    let warning = if shop > TEXT_POOL_PAIRS { "WARNING, " } else { "" };
    says.push(format!(
        "  {warning}shop text: its lists ask for {shop} pairs of tiles at most, of the {TEXT_POOL_PAIRS} of the pool"
    ));
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
    // Each screen with windows is drawn with the System `fit` gives it: the
    // game's, or with its windows redrawn if they do not fit their bank.
    let (fitted, fused) = fit::skin_for(game, &skin, fit::Screen::Target, 0)?;
    says.extend(fused_windows("the actor choice's", fused));
    let target_screens = [borders::target_layer(game, &fitted)?, borders::menu_bar_layer(&fitted)];
    let target = borders::borders(&target_screens, 0, TARGET_CGRAM, TARGET_CGRAM + TARGET_COLORS_MAX)?;
    request.vram.target(target.tiles.len())?;
    let inks = items::text_inks(&skin, &game.font)?;
    // The item and equipment windows share tiles and colours, and go at the
    // end of the bank: the text has what is below them. Counted first, then
    // numbered from where they land.
    let (fitted, fused) = fit::skin_for(game, &skin, fit::Screen::Items, item_pairs(game, &skin, &request.items)?)?;
    says.extend(fused_windows("the item and equipment", fused));
    let border_screens = || [borders::item_layers(&fitted), borders::equipment_layers(&fitted)];
    let counted = borders::borders(&border_screens(), 0, ITEM_BORDER_CGRAM, 256)?;
    let first = items_border_first(counted.tiles.len());
    let items_border = borders::borders(&border_screens(), first, ITEM_BORDER_CGRAM, 256)?;
    request.vram.items_border(items_border.tiles.len(), 0)?;
    let asked = item_pairs(game, &fitted, &request.items)?;
    let pool = first.saturating_sub(1);
    let warning = if asked > pool { "WARNING, " } else { "" };
    says.push(format!(
        "  {warning}item text: its list asks for {asked} pairs of tiles at most, of the {pool} the item and \
         equipment windows leave"
    ));
    // The shop's, with their own tiles and colours.
    let (fitted, fused) = fit::skin_for(game, &skin, fit::Screen::Shop, 0)?;
    says.extend(fused_windows("the shop's", fused));
    let shop_border = borders::borders(&borders::shop_layers(&fitted), 0, ITEM_BORDER_CGRAM, TARGET_CGRAM)?;
    request.vram.shop(shop_border.tiles.len())?;
    // End Game's tiles go where the slot screen's do, so what is checked is
    // the same.
    let end = end_game::convert(game, &skin)?;
    request.vram.slots(end.tiles.len())?;
    if end.merged > 0 {
        says.push(format!(
            "  WARNING, End Game's windows have more colours than its palette: {} were merged into the ones \
             most like them",
            end.merged
        ));
    }
    request.vram.slots(slots.tiles.len())?;
    let title = if request.title { Some(title::menu(game, &skin)?) } else { None };

    let (fitted, fused) = fit::skin_for(game, &skin, fit::Screen::Battle, 0)?;
    says.extend(fused_windows("the battle's", fused));
    let battle_windows = crate::battle::battle_windows(&fitted)?;
    says.push(format!(
        "  battle windows: {} tiles of {}, {} colours of {}, {} words of bars",
        battle_windows["tiles"].as_array().map_or(0, Vec::len),
        crate::battle::BATTLE_WINDOW_TILES_MAX,
        battle_windows["colors"].as_array().map_or(0, Vec::len),
        crate::battle::BATTLE_WINDOW_COLORS,
        battle_windows["patches"].as_array().map_or(0, Vec::len),
    ));
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

    let custom_menus = if menus.is_empty() {
        // The geometry goes anyway: the runtime assembles the same with or
        // without menus.
        json!({"labels": [], "layout": crate::custom_menu::publish()})
    } else {
        let built = crate::custom_menu::build(game, &skin, menus, &request.menu_context)?;
        says.extend(built.says.iter().cloned());
        crate::custom_menu::to_json(&built)
    };
    let menu = &slots.menu;
    let mut window_json = window_json(&window);
    window_json["font"] = json!(hex(&font));
    window_json["advances"] = json!(game.font.console_advances());
    window_json["reach"] = json!(message_window::font_reach(&game.font));
    window_json["prerender"] = json!(prerender.iter().map(|t| hex(t)).collect::<Vec<_>>());
    Ok(json!({
        "custom_menus": custom_menus,
        "window": window_json,
        "title": title.map(|t| json!({
            "texts": t.texts,
            "tiles": tiles_json(&t.tiles),
            "palette": colors_json(&t.palette),
            "tilemaps": t.tilemaps,
        })),
        "slots": {
            "tiles": tiles_json(&slots.tiles),
            "menu_tiles": slots.menu_tiles,
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
        "battle_windows": battle_windows,
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
