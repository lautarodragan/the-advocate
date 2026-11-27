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
use crate::cells::CELL;
use crate::fail::Result;
use crate::game::{Game, Skin};
use crate::layout::*;
use crate::texts::{self, item_text, split_description};
use rm2k_render::picture::Picture;
use rm2k_snes_text::font::{Font, FIGURE_BLANK};
use std::collections::{BTreeMap, BTreeSet};

/// A [`Grid`] run's colour from here up is System colour `variant -
/// SYSTEM_INK`, in a palette of its own: the skills screen's condition.
pub const SYSTEM_INK: usize = 100;

/// A text screen —items, equipment, shop— as the cartridge's text layer
/// composes it: each write a run of letters of the game's font from where
/// it starts, in a colour, on a line of two cell rows. See `text_layer.s` in
/// the runtime, which does the same: a write that starts at a cell goes from
/// x = 8 * column + `SCR_TEXT_X`, each letter moving it by its advance, and a
/// write at the same x of the same row replaces the one that was there.
#[derive(Debug, Clone, Default)]
pub struct Grid {
    /// `(row, x, text, colour)`, in the order they were written.
    pub runs: Vec<(usize, usize, String, usize)>,
}

impl Grid {
    fn run(&mut self, row: usize, x: usize, text: &str, variant: usize) {
        self.runs.retain(|r| !(r.0 == row && r.1 == x));
        self.runs.push((row, x, text.to_string(), variant));
    }

    pub fn write(&mut self, row: usize, col: usize, text: &str, variant: usize) {
        self.run(row, col * CELL + SCR_TEXT_X, text, variant);
    }

    /// In `width` places, right-aligned: the places a number does not reach
    /// are blanks as wide as a digit.
    pub fn write_number(
        &mut self,
        row: usize,
        col: usize,
        value: i64,
        width: usize,
        variant: usize,
    ) {
        let text: String = texts::right(value, width)
            .chars()
            .map(|c| if c == ' ' { FIGURE_BLANK } else { c })
            .collect();
        self.write(row, col, &text, variant);
    }

    /// Right-aligned so that its last letter ends with cell `last`: the
    /// shop's gold, prices and totals, which have no fixed number of places.
    pub fn write_right(
        &mut self,
        font: &Font,
        row: usize,
        last: usize,
        text: &str,
        variant: usize,
    ) {
        let x = (last + 1) * CELL + SCR_TEXT_X - 1 - font.width(text);
        self.run(row, x, text, variant);
    }

    /// The pairs of tiles the cartridge's text layer takes for these runs:
    /// see `rm2k_snes_text::cells`.
    pub fn pairs(&self, font: &Font) -> usize {
        let mut rows: BTreeMap<usize, Vec<(usize, String, usize)>> = BTreeMap::new();
        for (row, x, text, variant) in &self.runs {
            rows.entry(*row)
                .or_default()
                .push((*x, text.clone(), *variant));
        }
        rm2k_snes_text::cells::pairs(font, rows.values().map(Vec::as_slice))
    }

    fn description(&mut self, font: &Font, text: &str) {
        for (n, line) in split_description(font, text).iter().enumerate() {
            self.write(ITEM_DESC_Y / CELL + 2 * n, ITEM_DESC_COL, line, ITEM_WHITE);
        }
    }
}

/// The item screen's text, and its windows.
pub fn item_screen_text(
    game: &Game,
    skin: &Skin,
    inventory: &BTreeMap<i32, i64>,
    chosen: usize,
    top: usize,
    known: Option<&[i32]>,
) -> Result<(Grid, Picture)> {
    let known: BTreeSet<i32> = match known {
        Some(k) => k.iter().copied().collect(),
        None => inventory
            .iter()
            .filter(|(_, &n)| n > 0)
            .map(|(i, _)| *i)
            .collect(),
    };
    // The ones there are and that the cartridge knows, in number order like
    // `Game_Party`.
    let listed: Vec<i32> = known
        .into_iter()
        .filter(|i| inventory.get(i).copied().unwrap_or(0) > 0)
        .collect();
    let mut t = Grid::default();
    if !listed.is_empty() {
        t.description(&game.font, &game.item_description(listed[chosen])?);
    }
    for row in 0..ITEM_ROWS {
        let k = top + row;
        if k >= listed.len() {
            break;
        }
        let item = game.item(listed[k])?;
        let row0 = ITEM_LIST_Y / CELL + 2 * row;
        let variant = if texts::item_usable(item, texts::map_skill(game, item)) {
            ITEM_WHITE
        } else {
            ITEM_GRAY
        };
        t.write(
            row0,
            ITEM_NAME_COL,
            &item_text(&game.item_name(listed[k])?, ITEM_NAME_WIDTH),
            variant,
        );
        // The colon and the count are one write on the cartridge: the
        // number goes where the colon left it.
        let count = inventory[&listed[k]].min(99);
        let digits: String = format!("{count:2}")
            .chars()
            .map(|c| if c == ' ' { FIGURE_BLANK } else { c })
            .collect();
        t.write(row0, ITEM_COLON_COL, &format!(":{digits}"), variant);
    }
    Ok((
        t,
        borders::item_windows(
            skin,
            if listed.is_empty() {
                None
            } else {
                Some(chosen - top)
            },
        ),
    ))
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

/// The items the shop's list shows in its mode: what it sells, or what is
/// owned of what the cartridge knows.
fn shop_choices(shop: &Shop) -> Vec<i32> {
    let known: BTreeSet<i32> = shop.known.clone().unwrap_or_else(|| {
        shop.sells
            .iter()
            .chain(shop.inventory.keys())
            .copied()
            .collect()
    });
    if matches!(shop.mode, TI_BUY | TI_COUNT_BUY | TI_BOUGHT) {
        shop.sells
            .iter()
            .copied()
            .filter(|i| known.contains(i))
            .collect()
    } else {
        shop.inventory
            .iter()
            .filter(|(i, &n)| n > 0 && known.contains(i))
            .map(|(i, _)| *i)
            .collect()
    }
}

/// The shop's text in its mode, and its windows.
pub fn shop_text(game: &Game, skin: &Skin, shop: &Shop) -> Result<(Grid, Picture)> {
    let mut t = Grid::default();
    let term = |name: &str| game.term(&format!("{name}{}", shop.term_set + 1));
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
    let lines = split_description(&game.font, &term(message)?);
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
            t.write(
                row0 + 2 * n,
                TI_COMMAND_COL,
                &split_description(&game.font, &term(command)?)[0],
                ITEM_WHITE,
            );
        }
        let bar = shop.chosen + two as usize;
        return Ok((t, borders::shop_windows(skin, layer, Some(bar))));
    }
    t.write(TI_MSG_ROW, ITEM_DESC_COL, &lines[0], ITEM_WHITE);
    let buying = matches!(shop.mode, TI_BUY | TI_COUNT_BUY | TI_BOUGHT);
    let choices = shop_choices(shop);
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
        t.description(&game.font, &game.item_description(choices[shop.chosen])?);
    }
    let gold_term = game.term("gold")?;
    if layer == TI_LAYER_BUY {
        // The gold, and how many of the one the cursor marks the party owns
        // and has equipped.
        let digits = shop.gold.min(999_999).to_string();
        t.write_right(&game.font, TI_GOLD_ROW, TI_GOLD_COL, &digits, ITEM_WHITE);
        t.write(TI_GOLD_ROW, TI_GOLD_COL + 1, &gold_term, ITEM_RED);
        if !choices.is_empty() {
            let number = choices[shop.chosen];
            t.write(
                TI_OWNED_ROW,
                TI_STATUS_COL,
                &game.term(TI_TERM_OWNED)?,
                ITEM_RED,
            );
            t.write_number(
                TI_OWNED_ROW,
                TI_STATUS_NUM,
                shop.inventory.get(&number).copied().unwrap_or(0),
                2,
                ITEM_WHITE,
            );
            t.write(
                TI_CARRIED_ROW,
                TI_STATUS_COL,
                &game.term(TI_TERM_CARRIED)?,
                ITEM_RED,
            );
            let carried = shop
                .party_equipment
                .iter()
                .flatten()
                .filter(|&&i| i == number)
                .count() as i64;
            t.write_number(TI_CARRIED_ROW, TI_STATUS_NUM, carried, 2, ITEM_WHITE);
        }
    }
    if matches!(shop.mode, TI_COUNT_BUY | TI_COUNT_SALE) {
        let number = choices[shop.chosen];
        let mut price = game.item(number)?.price as i64;
        if shop.mode == TI_COUNT_SALE {
            price /= 2;
        }
        t.write(
            TI_COUNT_ROW,
            TI_LIST_COL,
            &item_text(&game.item_name(number)?, ITEM_NAME_WIDTH),
            ITEM_WHITE,
        );
        t.write(TI_COUNT_ROW, TI_COUNT_X_COL, "x", ITEM_WHITE);
        t.write_number(TI_COUNT_ROW, TI_COUNT_COL, shop.count, 2, ITEM_WHITE);
        let total = (price * shop.count).to_string();
        t.write_right(&game.font, TI_TOTAL_ROW, TI_GOLD_COL, &total, ITEM_WHITE);
        t.write(TI_TOTAL_ROW, TI_GOLD_COL + 1, &gold_term, ITEM_RED);
        return Ok((t, windows));
    }
    if matches!(shop.mode, TI_BOUGHT | TI_SOLD) {
        // The middle window, empty: RM2k.
        return Ok((t, windows));
    }
    let rows = if buying {
        TI_LIST_ROWS_BUY
    } else {
        TI_LIST_ROWS_SALE
    };
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
            if (item.price as i64) <= shop.gold && owned < 99 {
                ITEM_WHITE
            } else {
                ITEM_GRAY
            }
        } else if item.price > 0 {
            ITEM_WHITE
        } else {
            ITEM_GRAY
        };
        t.write(
            row,
            TI_LIST_COL,
            &item_text(&game.item_name(number)?, ITEM_NAME_WIDTH),
            variant,
        );
        if buying {
            let price = item.price.to_string();
            t.write_right(&game.font, row, TI_PRICE_COL, &price, variant);
        } else {
            let count = shop.inventory[&number].min(99);
            let digits: String = format!("{count:2}")
                .chars()
                .map(|c| if c == ' ' { FIGURE_BLANK } else { c })
                .collect();
            t.write(row, ITEM_COLON_COL, &format!(":{digits}"), variant);
        }
    }
    Ok((t, windows))
}
