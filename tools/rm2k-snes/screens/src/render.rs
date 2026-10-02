//! A screen as the console has to show it, for whoever compares a capture
//! against it.
//!
//! **It is built with the same blocks the cartridge uploads**, not by
//! drawing the text again: the tiles, the palettes and the cells of
//! [`crate::convert`], put where the cartridge puts them. Drawing it here
//! with the font and there with the tiles would leave out exactly the step
//! that can go wrong —cutting, deduplicating, the palettes—.
//!
//! What a screen shows depends on the game's state —the party, the gold,
//! the inventory, where the cursor is—, which comes in the request. The
//! rules that decide what is written —what can be equipped, what can be
//! bought— are RM2k's, and are here in the shape the cartridge runs them.

use crate::borders;
use crate::cells::{self, Color, CELL, COLS, HEIGHT, WIDTH};
use crate::end_game;
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::items;
use crate::layout::*;
use crate::slots::{self, MenuBlocks};
use crate::texts::{self, item_text, split_description};
use rm2k_render::picture::Picture;
use std::collections::{BTreeMap, BTreeSet};
use voodoo::pack::Indices;

/// A screen being painted as the cartridge paints it.
struct Painter<'a> {
    out: Picture,
    tiles: &'a [Indices],
    palettes: &'a [Vec<Color>],
}

impl<'a> Painter<'a> {
    fn new(tiles: &'a [Indices], palettes: &'a [Vec<Color>]) -> Self {
        Painter {
            out: Picture::filled(WIDTH, HEIGHT, [0, 0, 0, 255]),
            tiles,
            palettes,
        }
    }

    fn set(&mut self, x: usize, y: usize, color: Color) {
        let at = (y * WIDTH + x) * 4;
        self.out.rgba[at..at + 3].copy_from_slice(&[color[0] << 3, color[1] << 3, color[2] << 3]);
    }

    /// A block of cells, `cols` wide, from cell `(col0, row0)`: the tile and
    /// palette of each tilemap word, index 0 transparent.
    fn paste(&mut self, cells: &[u16], row0: usize, col0: usize, cols: usize) {
        for (i, &word) in cells.iter().enumerate() {
            let tx = (col0 + i % cols) * CELL;
            let ty = (row0 + i / cols) * CELL;
            let cell = self.tiles[(word & 0x3FF) as usize];
            let palette = &self.palettes[((word >> 10) & 7) as usize];
            for (y, line) in cell.iter().enumerate() {
                if ty + y >= HEIGHT {
                    break;
                }
                for (x, &value) in line.iter().enumerate() {
                    if value != 0 && tx + x < WIDTH {
                        self.set(tx + x, ty + y, palette[value as usize]);
                    }
                }
            }
        }
    }

    /// An 8x8 tile at any pixel, like a sprite, with the word's palette.
    fn sprite(&mut self, word: u16, x: i64, y: i64) {
        let cell = self.tiles[(word & 0x3FF) as usize];
        let palette = &self.palettes[((word >> 10) & 7) as usize];
        for (dy, line) in cell.iter().enumerate() {
            for (dx, &value) in line.iter().enumerate() {
                let (px, py) = (x + dx as i64, y + dy as i64);
                if value != 0 && (0..WIDTH as i64).contains(&px) && (0..HEIGHT as i64).contains(&py) {
                    self.set(px as usize, py as usize, palette[value as usize]);
                }
            }
        }
    }

    /// Pastes `picture` through its alpha: the windows behind the text.
    fn under(&mut self, picture: &Picture) {
        cells::paste(&mut self.out, picture, 0, 0);
    }

    fn picture(mut self) -> Picture {
        for p in self.out.rgba.chunks_exact_mut(4) {
            p[3] = 255;
        }
        self.out
    }
}

/// A text composed one letter per cell with the menu bank's glyphs, as
/// the cartridge writes it.
fn paste_text(p: &mut Painter, menu: &MenuBlocks, text: &str, row: usize, col: usize) -> Result<()> {
    for (n, letter) in text.chars().enumerate() {
        let glyph = menu
            .glyphs
            .get(&letter)
            .ok_or_else(|| Bad::answer(format!("the menu's bank has no {letter:?}")))?;
        p.paste(glyph, row, col + n, 1);
    }
    Ok(())
}

/// The party's state a screen shows.
#[derive(Debug, Clone, Default)]
pub struct Party {
    /// The actors in order.
    pub members: Vec<i32>,
    /// The ones the cartridge knows —who can join the party—, which decide
    /// the tile bank; without them, the members.
    pub actors: Option<Vec<i32>>,
    /// Each actor's current HP; without it, full.
    pub hp: BTreeMap<i32, i64>,
    /// Each actor's level and experience; without them, the starting ones.
    pub levels: BTreeMap<i32, i64>,
    pub exps: BTreeMap<i32, i64>,
}

impl Party {
    fn known(&self) -> Vec<i32> {
        let set: BTreeSet<i32> = self.actors.clone().unwrap_or_else(|| self.members.clone()).into_iter().collect();
        set.into_iter().collect()
    }
}

/// A row of the party panel: the fixed block, the face and the three
/// strips that depend on the actor, and the current HP. It is what the
/// cartridge's `menu_party_paint` does, in the same order, and that is why
/// the menu and the actor choice share it.
fn actor_row(
    p: &mut Painter,
    game: &Game,
    slots: &slots::Slots,
    row: usize,
    actor: i32,
    party: &Party,
    levels: bool,
) -> Result<()> {
    let menu = &slots.menu;
    let row0 = row * MENU_ACTOR_ROWS;
    p.paste(&menu.row, row0, MENU_ACTOR_COL, MENU_ACTOR_COLS);
    if let Some(face) = slots.faces.get(&actor) {
        p.paste(face, row0, MENU_ACTOR_COL, FACE_CELLS);
    }
    paste_text(p, menu, &texts::name_text(game, actor, MENU_NAME_COLS)?, row0 + MENU_NAME_ROW, MENU_NAME_COL)?;
    let level = if levels { party.levels.get(&actor).copied() } else { None };
    paste_text(p, menu, &texts::level_text(game, actor, level), row0 + MENU_LEVEL_ROW, MENU_LEVEL_COL)?;
    paste_text(p, menu, &texts::max_text(game, actor, level), row0 + MENU_HP_ROW, MENU_MAX_COL)?;
    let hp = match party.hp.get(&actor) {
        Some(&hp) => hp,
        None => texts::max_hp(&game.actors[&actor], None),
    };
    let digits = texts::digits_of(hp, MENU_HP_DIGITS as u32);
    paste_text(p, menu, &digits, row0 + MENU_HP_ROW, MENU_HP_COL + MENU_HP_DIGITS - digits.len())
}

/// The pause menu. `slots` are the save slots, `chosen` the command with
/// the cursor and `save_allowed` what `ChangeSaveAccess` left. With
/// `choosing`, the party row the bar is on while choosing whom a command
/// is for —`Scene_Menu::UpdateActorSelection`—; the command keeps its
/// cursor.
#[allow(clippy::too_many_arguments)]
pub fn menu(
    game: &Game,
    skin: &Skin,
    slots: usize,
    party: &Party,
    gold: i64,
    chosen: usize,
    save_allowed: bool,
    choosing: Option<usize>,
) -> Result<Picture> {
    let known = party.known();
    let bank = slots::slots_screen(game, skin, slots, &known, "")?;
    let menu = &bank.menu;
    let mut p = Painter::new(&bank.tiles, &bank.palettes);
    p.under(&borders::menu_bar(skin, choosing));
    for option in 0..MENU_OPTIONS {
        let done = MENU_DONE.contains(&option) && (option != MENU_SAVE || save_allowed);
        p.paste(
            &menu.options[option][if done { 0 } else { 1 }],
            (MENU_OPT_Y + option * MENU_OPT_STEP) / CELL,
            MENU_OPT_COL,
            MENU_OPT_COLS,
        );
    }
    p.paste(&menu.cursor, (MENU_OPT_Y + chosen * MENU_OPT_STEP) / CELL, MENU_CURSOR_COL, 1);
    let digits = texts::digits_of(gold, MENU_GOLD_DIGITS as u32);
    paste_text(&mut p, menu, &digits, MENU_GOLD_Y / CELL, MENU_CURRENCY_COL - digits.len())?;
    p.paste(&menu.currency, MENU_GOLD_Y / CELL, MENU_CURRENCY_COL, MENU_CURRENCY_COLS);
    let rows: Vec<(usize, i32)> = party
        .members
        .iter()
        .take(MENU_PARTY_ROWS)
        .copied()
        .enumerate()
        .filter(|(_, a)| known.contains(a))
        .collect();
    for &(row, actor) in &rows {
        actor_row(&mut p, game, &bank, row, actor, party, true)?;
    }
    // The experience goes on top of everything, like sprites over the
    // background: see `MENU_EXP_X`.
    for &(row, actor) in &rows {
        let text = texts::exp_text(
            game,
            actor,
            party.levels.get(&actor).copied(),
            party.exps.get(&actor).copied(),
        );
        let y = (row * MENU_ACTOR_ROWS * CELL + MENU_EXP_Y - GLYPH_DY) as i64;
        for (n, &word) in menu.exp_term.iter().enumerate() {
            p.sprite(
                word,
                (MENU_EXP_X + (n % MENU_EXP_TERM_CELLS) * CELL) as i64,
                y + ((n / MENU_EXP_TERM_CELLS) * CELL) as i64,
            );
        }
        for (n, letter) in text.chars().enumerate() {
            if letter == ' ' {
                continue;
            }
            let x = (MENU_EXP_X + MENU_EXP_NUM_DX + n * rm2k_snes_text::font::WIDTH - GLYPH_DX) as i64;
            let glyph = menu
                .glyphs
                .get(&letter)
                .ok_or_else(|| Bad::answer(format!("the menu's bank has no {letter:?}")))?;
            p.sprite(glyph[0], x, y);
            p.sprite(glyph[1], x, y + CELL as i64);
        }
    }
    Ok(p.picture())
}

/// The actor choice: the party panel, and `item`, the medicine being used,
/// with how many are left.
pub fn target(
    game: &Game,
    skin: &Skin,
    slots: usize,
    party: &Party,
    chosen: usize,
    item: i32,
    amount: i64,
) -> Result<Picture> {
    let known = party.known();
    let name = game.item_name(item)?;
    let bank = slots::slots_screen(game, skin, slots, &known, &name)?;
    let mut p = Painter::new(&bank.tiles, &bank.palettes);
    p.under(&borders::target_windows(game, skin, Some(chosen))?);
    for (row, actor) in party.members.iter().take(MENU_PARTY_ROWS).copied().enumerate() {
        if known.contains(&actor) {
            actor_row(&mut p, game, &bank, row, actor, party, false)?;
        }
    }
    for (n, line) in texts::name_in_lines(&name, TARGET_NAME_WIDTH, 2).iter().enumerate() {
        paste_text(&mut p, &bank.menu, line, TARGET_NAME_ROW + 2 * n, TARGET_NAME_COL)?;
    }
    paste_text(&mut p, &bank.menu, &format!("{:2}", amount.min(99)), TARGET_COUNT_ROW, TARGET_COUNT_COL)?;
    Ok(p.picture())
}

/// The slot screen: `full` says which slots have a save, `chosen` where
/// the cursor is, `mode` 0 for loading and 1 for saving, `parties` the
/// saved party of each full slot —the leader's name and up to
/// `FACES_MAX` faces— and `levels` the leader's level in each save.
#[allow(clippy::too_many_arguments)]
pub fn slot_screen(
    game: &Game,
    skin: &Skin,
    slots: usize,
    full: &[bool],
    chosen: usize,
    mode: usize,
    parties: &BTreeMap<usize, Vec<i32>>,
    levels: &BTreeMap<usize, i64>,
) -> Result<Picture> {
    let actors: Vec<i32> = parties.values().flatten().copied().collect::<BTreeSet<_>>().into_iter().collect();
    let bank = slots::slots_screen(game, skin, slots, &actors, "")?;
    let mut p = Painter::new(&bank.tiles, &bank.palettes);
    p.paste(&bank.headers[mode], HEADER_Y / CELL, 0, COLS);
    for number in 0..slots {
        let row0 = (SLOT_Y + number * SLOT_STEP) / CELL;
        let is_full = full.get(number).copied().unwrap_or(false) || parties.contains_key(&number);
        p.paste(
            &bank.rows[number][is_full as usize][(number == chosen) as usize],
            row0,
            0,
            COLS,
        );
        if !is_full {
            continue;
        }
        let party = parties.get(&number).cloned().unwrap_or_default();
        // The leader's name and level, composed with glyphs over the row, and
        // the faces, which are blocks.
        if let Some(&leader) = party.first() {
            if actors.contains(&leader) {
                paste_text(&mut p, &bank.menu, &texts::name_text(game, leader, NAME_COLS)?, row0 + NAME_ROW, NAME_COL)?;
                paste_text(
                    &mut p,
                    &bank.menu,
                    &texts::level_text(game, leader, levels.get(&number).copied()),
                    row0 + LEVEL_ROW,
                    LEVEL_COL,
                )?;
            }
        }
        for (place, actor) in party.iter().take(FACES_MAX).enumerate() {
            if let Some(face) = bank.faces.get(actor) {
                p.paste(face, row0, FACE_COL + place * FACE_STEP, FACE_CELLS);
            }
        }
    }
    Ok(p.picture())
}

/// The screen as a grid of cells, as the cartridge builds the text screens
/// —equipment, shop—: a letter and its variant per cell.
#[derive(Debug, Clone, Default)]
pub struct Grid {
    pub cells: BTreeMap<(usize, usize), (char, usize)>,
}

impl Grid {
    pub fn write(&mut self, row: usize, col: usize, text: &str, variant: usize) {
        for (n, c) in text.chars().enumerate() {
            if col + n < COLS {
                self.cells.insert((row, col + n), (c, variant));
            }
        }
    }

    /// Right-aligned, with leading spaces.
    pub fn write_number(&mut self, row: usize, col: usize, value: i64, width: usize, variant: usize) {
        self.write(row, col, &texts::right(value, width), variant);
    }

    fn description(&mut self, text: &str) {
        for (n, line) in split_description(text).iter().enumerate() {
            self.write(ITEM_DESC_Y / CELL + 2 * n, ITEM_DESC_COL, line, ITEM_WHITE);
        }
    }

    /// The grid over `windows`, with the text screens' font.
    pub fn render(&self, game: &Game, skin: &Skin, windows: &Picture) -> Result<Picture> {
        let font = items::items_screen(game, skin)?;
        let mut p = Painter::new(&font.tiles, &font.palettes);
        p.under(windows);
        for (&(row, col), &(c, variant)) in &self.cells {
            let glyph = font.glyphs[variant]
                .get(&c)
                .ok_or_else(|| Bad::answer(format!("variant {variant} of the font has no {c:?}")))?;
            p.paste(glyph, row, col, 1);
        }
        Ok(p.picture())
    }
}

/// The item screen: `inventory` maps item number to how many there are,
/// `known` are the ones the cartridge knows —without it, the inventory's—,
/// `chosen` the cursor's position in the list and `top` the first visible.
pub fn item_screen(
    game: &Game,
    skin: &Skin,
    inventory: &BTreeMap<i32, i64>,
    chosen: usize,
    top: usize,
    known: Option<&[i32]>,
) -> Result<Picture> {
    let known: BTreeSet<i32> = match known {
        Some(k) => k.iter().copied().collect(),
        None => inventory.iter().filter(|(_, &n)| n > 0).map(|(i, _)| *i).collect(),
    };
    // The ones there are and that the cartridge knows, in number order like
    // `Game_Party`.
    let listed: Vec<i32> = known.into_iter().filter(|i| inventory.get(i).copied().unwrap_or(0) > 0).collect();
    let font = items::items_screen(game, skin)?;
    let mut p = Painter::new(&font.tiles, &font.palettes);
    p.under(&borders::item_windows(skin, if listed.is_empty() { None } else { Some(chosen - top) }));
    let write = |p: &mut Painter, text: &str, row0: usize, col0: usize, variant: usize| -> Result<()> {
        for (n, c) in text.chars().enumerate() {
            let glyph = font.glyphs[variant]
                .get(&c)
                .ok_or_else(|| Bad::answer(format!("variant {variant} of the font has no {c:?}")))?;
            p.paste(glyph, row0, col0 + n, 1);
        }
        Ok(())
    };
    if !listed.is_empty() {
        for (n, line) in split_description(&game.item_description(listed[chosen])?).iter().enumerate() {
            write(&mut p, line, ITEM_DESC_Y / CELL + 2 * n, ITEM_DESC_COL, ITEM_WHITE)?;
        }
    }
    for row in 0..ITEM_ROWS {
        let k = top + row;
        if k >= listed.len() {
            break;
        }
        let item = game.item(listed[k])?;
        let row0 = ITEM_LIST_Y / CELL + 2 * row;
        let variant = if texts::item_usable(item) { ITEM_WHITE } else { ITEM_GRAY };
        write(&mut p, &item_text(&game.item_name(listed[k])?, ITEM_NAME_WIDTH), row0, ITEM_NAME_COL, variant)?;
        let count = inventory[&listed[k]].min(99);
        write(&mut p, &format!(":{count:2}"), row0, ITEM_COLON_COL, variant)?;
    }
    Ok(p.picture())
}

/// What the actor can put in `slot`, in number order, and the 0 at the end
/// which is unequipping: only what the cartridge knows.
pub fn candidates(
    game: &Game,
    actor: i32,
    slot: usize,
    inventory: &BTreeMap<i32, i64>,
    known: Option<&BTreeSet<i32>>,
) -> Result<Vec<i32>> {
    let mut out = Vec::new();
    for (&i, &n) in inventory {
        if n <= 0 || known.is_some_and(|k| !k.contains(&i)) {
            continue;
        }
        let item = game.item(i)?;
        // The item type that goes in the slot: 1 weapon ... 5 accessory.
        let equippable = item.actor_set.get((actor - 1) as usize).copied().unwrap_or(true);
        if item.r#type.to_i32() == slot as i32 + 1 && equippable {
            out.push(i);
        }
    }
    out.push(0);
    Ok(out)
}

/// `Game_Actor::ChangeEquipment` ([`rm2k_rules::actor::change_equipment`])
/// with this game's items: an item it does not have is a no.
pub fn equip(game: &Game, equipment: &mut [i32], inventory: &mut BTreeMap<i32, i64>, slot: usize, item: i32) -> Result<()> {
    rm2k_rules::actor::change_equipment(equipment, inventory, slot, item, |i| {
        Ok(game.item(i)?.two_handed)
    })
}

/// `Window_EquipStatus::GetNewParameterColor`: the value that would result
/// goes white if it does not change, "goes up" if it goes up and gray if it
/// goes down.
fn new_value_color(now: i64, then: i64) -> usize {
    if then == now {
        ITEM_WHITE
    } else if then > now {
        ITEM_UP
    } else {
        ITEM_GRAY
    }
}

/// The actor's equipment: with `choosing`, the slot's list with the cursor
/// on `chosen` and the first visible one at `top`.
#[allow(clippy::too_many_arguments)]
pub fn equipment_screen(
    game: &Game,
    skin: &Skin,
    actor: i32,
    equipment: &[i32],
    inventory: &BTreeMap<i32, i64>,
    slot: usize,
    choosing: bool,
    chosen: usize,
    top: usize,
    known: Option<&BTreeSet<i32>>,
) -> Result<Picture> {
    let mut t = Grid::default();
    t.write(EQ_ACTOR_ROW, EQ_ACTOR_COL, &game.actor_name(actor)?, ITEM_WHITE);
    let choices = candidates(game, actor, slot, inventory, known)?;
    let bar = if choosing { EQUIPMENT_SLOTS + chosen - top } else { slot };
    let now = texts::equipped_params(game, actor, equipment);
    let mut then = None;
    if choosing {
        let mut trial = equipment.to_vec();
        let mut inv = inventory.clone();
        equip(game, &mut trial, &mut inv, slot, choices[chosen])?;
        then = Some(texts::equipped_params(game, actor, &trial));
        if choices[chosen] != 0 {
            t.description(&game.item_description(choices[chosen])?);
        }
    } else if equipment[slot] != 0 {
        t.description(&game.item_description(equipment[slot])?);
    }
    let params = ["attack", "defense", "spirit", "agility"];
    for (n, &(row, col)) in EQ_PARAMS.iter().enumerate() {
        let term: String = game.term(params[n])?.chars().take(EQ_PARAM_VALUE - 1).collect();
        t.write(row, col, &term, ITEM_RED);
        t.write_number(row, col + EQ_PARAM_VALUE, now[n], 3, ITEM_WHITE);
        if let Some(then) = &then {
            t.write(row, col + EQ_PARAM_ARROW, ">", ITEM_RED);
            t.write_number(row, col + EQ_PARAM_ARROW + 1, then[n], 3, new_value_color(now[n], then[n]));
        }
    }
    if !choosing {
        let slots = ["weapon", "shield", "armor", "helmet", "accessory"];
        for (r, name) in slots.iter().enumerate() {
            let row = EQ_SLOT_ROW0 + 2 * r;
            let term: String = game.term(name)?.chars().take(EQ_SLOT_TERM_WIDTH).collect();
            t.write(row, EQ_SLOT_TERM_COL, &term, ITEM_RED);
            if equipment[r] != 0 {
                t.write(row, EQ_SLOT_NAME_COL, &item_text(&game.item_name(equipment[r])?, EQ_SLOT_NAME_WIDTH), ITEM_WHITE);
            }
        }
    } else {
        for f in 0..EQ_LIST_ROWS {
            let k = top + f;
            if k >= choices.len() {
                break;
            }
            let row = EQ_LIST_ROW0 + 2 * f;
            if choices[k] != 0 {
                t.write(row, EQ_LIST_NAME_COL, &item_text(&game.item_name(choices[k])?, ITEM_NAME_WIDTH), ITEM_WHITE);
                let count = inventory[&choices[k]].min(99);
                t.write(row, ITEM_COLON_COL, &format!(":{count:2}"), ITEM_WHITE);
            }
        }
    }
    t.render(game, skin, &borders::equipment_windows(skin, Some(bar)))
}

/// What the shop is doing: its screen, and the state it shows.
#[derive(Debug, Clone, Default)]
pub struct Shop {
    /// `OpenShop`'s: 0 buys and sells, 1 only buys, 2 only sells.
    pub kind: usize,
    /// Which of the database's three message sets it speaks with.
    pub term_set: usize,
    /// What it sells.
    pub sells: Vec<i32>,
    pub gold: i64,
    pub inventory: BTreeMap<i32, i64>,
    /// Each party member's equipment.
    pub party_equipment: Vec<Vec<i32>>,
    /// Which screen: `TI_MAIN` to `TI_SOLD`.
    pub mode: usize,
    /// The cursor —of the main one or of the list—, the first visible one
    /// of the list, and the quantity being chosen.
    pub chosen: usize,
    pub top: usize,
    pub count: i64,
    pub regreeting: bool,
    /// The items the cartridge knows; without it, what it sells and what is
    /// owned.
    pub known: Option<BTreeSet<i32>>,
}

/// The shop in its mode.
pub fn shop_screen(game: &Game, skin: &Skin, shop: &Shop) -> Result<Picture> {
    let mut t = Grid::default();
    let term = |name: &str| game.term(&format!("{name}{}", shop.term_set + 1));
    let known: BTreeSet<i32> = shop
        .known
        .clone()
        .unwrap_or_else(|| shop.sells.iter().chain(shop.inventory.keys()).copied().collect());
    let message = match shop.mode {
        TI_MAIN if shop.regreeting => "shop_regreeting",
        TI_MAIN => "shop_greeting",
        TI_BUY => "shop_buy_select",
        TI_COUNT_BUY => "shop_buy_number",
        TI_BOUGHT => "shop_purchased",
        TI_SELL => "shop_sell_select",
        TI_COUNT_SALE => "shop_sell_number",
        _ => "shop_sold",
    };
    let layer = TI_LAYER_OF_MODE[shop.mode];
    let lines = split_description(&term(message)?);
    if shop.mode == TI_MAIN {
        for (n, line) in lines.iter().enumerate() {
            t.write(TI_MAIN_MSG_ROW + 2 * n, ITEM_DESC_COL, line, ITEM_WHITE);
        }
        let two = !lines[1].is_empty();
        let row0 = TI_MAIN_MSG_ROW + if two { 4 } else { 2 };
        let commands: &[&str] = match shop.kind {
            0 => &["shop_buy", "shop_sell", "shop_leave"],
            1 => &["shop_buy"],
            _ => &["shop_sell"],
        };
        for (n, command) in commands.iter().enumerate() {
            // From the first line, like the cartridge, which stores them
            // split: a term with a leading space loses it.
            t.write(row0 + 2 * n, TI_COMMAND_COL, &split_description(&term(command)?)[0], ITEM_WHITE);
        }
        let bar = shop.chosen + two as usize;
        return t.render(game, skin, &borders::shop_windows(skin, layer, Some(bar)));
    }
    t.write(TI_MSG_ROW, ITEM_DESC_COL, &lines[0], ITEM_WHITE);
    let buying = matches!(shop.mode, TI_BUY | TI_COUNT_BUY | TI_BOUGHT);
    let choices: Vec<i32> = if buying {
        shop.sells.iter().copied().filter(|i| known.contains(i)).collect()
    } else {
        shop.inventory
            .iter()
            .filter(|(i, &n)| n > 0 && known.contains(i))
            .map(|(i, _)| *i)
            .collect()
    };
    let bar = if choices.is_empty() {
        None
    } else {
        match shop.mode {
            TI_BUY | TI_SELL => Some(shop.chosen - shop.top),
            TI_COUNT_BUY | TI_COUNT_SALE => Some(TI_LIST_ROWS_BUY),
            _ => None,
        }
    };
    let windows = borders::shop_windows(skin, layer, bar);
    if !choices.is_empty() {
        t.description(&game.item_description(choices[shop.chosen])?);
    }
    let gold_term = game.term("gold")?;
    if layer == TI_LAYER_BUY {
        // The gold, and how many of the one the cursor marks the party owns
        // and has equipped.
        let digits = shop.gold.min(999_999).to_string();
        t.write(TI_GOLD_ROW, TI_GOLD_COL + 1 - digits.len(), &digits, ITEM_WHITE);
        t.write(TI_GOLD_ROW, TI_GOLD_COL + 1, &gold_term, ITEM_RED);
        if !choices.is_empty() {
            let number = choices[shop.chosen];
            t.write(TI_OWNED_ROW, TI_STATUS_COL, &game.term(TI_TERM_OWNED)?, ITEM_RED);
            t.write_number(TI_OWNED_ROW, TI_STATUS_NUM, shop.inventory.get(&number).copied().unwrap_or(0), 2, ITEM_WHITE);
            t.write(TI_CARRIED_ROW, TI_STATUS_COL, &game.term(TI_TERM_CARRIED)?, ITEM_RED);
            let carried = shop.party_equipment.iter().flatten().filter(|&&i| i == number).count() as i64;
            t.write_number(TI_CARRIED_ROW, TI_STATUS_NUM, carried, 2, ITEM_WHITE);
        }
    }
    if matches!(shop.mode, TI_COUNT_BUY | TI_COUNT_SALE) {
        let number = choices[shop.chosen];
        let mut price = game.item(number)?.price as i64;
        if shop.mode == TI_COUNT_SALE {
            price /= 2;
        }
        t.write(TI_COUNT_ROW, TI_LIST_COL, &item_text(&game.item_name(number)?, ITEM_NAME_WIDTH), ITEM_WHITE);
        t.write(TI_COUNT_ROW, TI_COUNT_X_COL, "x", ITEM_WHITE);
        t.write_number(TI_COUNT_ROW, TI_COUNT_COL, shop.count, 2, ITEM_WHITE);
        let total = (price * shop.count).to_string();
        t.write(TI_TOTAL_ROW, TI_GOLD_COL + 1 - total.len(), &total, ITEM_WHITE);
        t.write(TI_TOTAL_ROW, TI_GOLD_COL + 1, &gold_term, ITEM_RED);
        return t.render(game, skin, &windows);
    }
    if matches!(shop.mode, TI_BOUGHT | TI_SOLD) {
        // The middle window, empty: RM2k.
        return t.render(game, skin, &windows);
    }
    let rows = if buying { TI_LIST_ROWS_BUY } else { TI_LIST_ROWS_SALE };
    for f in 0..rows {
        let k = shop.top + f;
        if k >= choices.len() {
            break;
        }
        let number = choices[k];
        let item = game.item(number)?;
        let row = TI_LIST_ROW0 + 2 * f;
        let variant = if buying {
            // `Window_ShopBuy::CheckEnable`: that there is enough and that
            // it does not have 99.
            let owned = shop.inventory.get(&number).copied().unwrap_or(0);
            if (item.price as i64) <= shop.gold && owned < 99 { ITEM_WHITE } else { ITEM_GRAY }
        } else if item.price > 0 {
            ITEM_WHITE
        } else {
            ITEM_GRAY
        };
        t.write(row, TI_LIST_COL, &item_text(&game.item_name(number)?, ITEM_NAME_WIDTH), variant);
        if buying {
            let price = item.price.to_string();
            t.write(row, TI_PRICE_COL + 1 - price.len(), &price, variant);
        } else {
            let count = shop.inventory[&number].min(99);
            t.write(row, ITEM_COLON_COL, &format!(":{count:2}"), variant);
        }
    }
    t.render(game, skin, &windows)
}

/// End Game with the cursor on `chosen`, rebuilt from what the cartridge
/// uploads and not from the drawing: the colour pairs go through the same
/// math as in the cartridge.
pub fn end_game_screen(game: &Game, skin: &Skin, chosen: usize) -> Result<Picture> {
    let end = end_game::convert(game, skin)?;
    let palette = &end.palettes[chosen];
    let mut out = Picture::filled(WIDTH, HEIGHT, [0, 0, 0, 255]);
    for (n, &word) in end.rows.iter().enumerate() {
        let mut cell = end.tiles[(word & 0x3FF) as usize];
        if word & 0x4000 != 0 {
            for line in cell.iter_mut() {
                line.reverse();
            }
        }
        if word & 0x8000 != 0 {
            cell.reverse();
        }
        let (row, col) = (end.row0 + n / COLS, n % COLS);
        for (y, line) in cell.iter().enumerate() {
            for (x, &value) in line.iter().enumerate() {
                let c = palette[value as usize];
                let at = ((row * CELL + y) * WIDTH + col * CELL + x) * 4;
                out.rgba[at..at + 3].copy_from_slice(&[c[0] << 3, c[1] << 3, c[2] << 3]);
            }
        }
    }
    Ok(out)
}
