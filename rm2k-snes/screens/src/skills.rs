//! The skills screen: its windows on BG1 at 8bpp, what the cartridge needs
//! of each skill to write its list and its description, and the text a page
//! asks of the text layer.
//!
//! Where everything goes is `SK_*` in [`crate::layout`]; the runtime's
//! `skills_screen.s` writes with those numbers, and [`crate::render`] draws
//! the screen as the console has to show it.
//!
//! **The windows take the custom menus' VRAM**: tiles from `CM_BG1_VRAM`,
//! colours from [`CM_BORDER_CGRAM`], the tilemap at `SCENE_MAP` —see
//! `custom_menu.s`—. What the cartridge stores is the arrangement's whole
//! tilemap and each bar as **half a row**: the bar of a column stays in its
//! half of the screen, so painting it is two rows of sixteen words, and
//! taking it off is the same two from the arrangement.

use crate::borders::{self, Screen};
use crate::cells::{self, COLS};
use crate::custom_menu::{CM_BORDER_CGRAM, CM_BORDER_CGRAM_END};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use crate::render::Grid;
use crate::texts::{self, description_spans};
use rm2k_render::picture::Picture;
use serde_json::{json, Map, Value};

/// The most 8bpp tiles the windows take: from `CM_BG1_VRAM`, word $4000,
/// up to where the custom menus' portrait would go, $6000 —this screen has
/// no objects, but the runtime asserts the same bound for both—.
pub const SK_TILES_MAX: usize = (0x6000 - 0x4000) / 32;

/// The text pairs a screen of the custom menus' VRAM has: up to the BG1
/// tilemap at `SCENE_MAP`, word $3800, minus pair 0.
pub const SK_TEXT_PAIRS: usize = 0x3800 / 32 - 1;

/// The place `p` of a page —row `p / 2`, column `p % 2`— as its bar's
/// rectangle.
fn bar_rect(p: usize) -> Rect {
    let (x, width) = SK_BARS[p % SK_COLUMNS];
    (x, SK_LIST_ROW0 * cells::CELL + 2 * cells::CELL * (p / SK_COLUMNS), width, 2 * cells::CELL)
}

/// The three windows, with the bar on place `bar` of the page.
pub fn windows(skin: &Skin, bar: Option<usize>) -> Picture {
    let mut out = cells::layer();
    for &(x, y, w, h) in &SK_WINDOWS {
        cells::paste(&mut out, &skin.window(w, h), x as i64, y as i64);
    }
    if let Some(p) = bar {
        let (x, y, w, h) = bar_rect(p);
        cells::paste(&mut out, &skin.cursor(w, h), x as i64, y as i64);
    }
    skin.redraw(&mut out);
    out
}

/// The screen as `borders` cuts it: the windows, and a bar per place.
pub fn layers(skin: &Skin) -> Screen {
    Screen {
        background: windows(skin, None),
        bars: (0..SK_ROWS * SK_COLUMNS)
            .map(|p| (windows(skin, Some(p)), SK_LIST_ROW0 + 2 * (p / SK_COLUMNS), 2))
            .collect(),
    }
}

/// What the cartridge stores of the windows: the tiles, their colours, the
/// arrangement's tilemap, and per place its bar's half rows, the top row's
/// sixteen words and then the bottom's.
pub fn windows_json(skin: &Skin) -> Result<Value> {
    let made = borders::borders(&[layers(skin)], 0, CM_BORDER_CGRAM, CM_BORDER_CGRAM_END)?;
    if made.tiles.len() > SK_TILES_MAX {
        return Err(Bad::answer(format!(
            "the skills screen's windows take {} tiles and there is room for {SK_TILES_MAX}",
            made.tiles.len()
        )));
    }
    let (map, bars) = &made.maps[0];
    let mut halves: Vec<u16> = Vec::new();
    for (p, bar) in bars.iter().enumerate() {
        let col0 = SK_HALF_COLS * (p % SK_COLUMNS);
        let row0 = SK_LIST_ROW0 + 2 * (p / SK_COLUMNS);
        for (i, (&with, &without)) in bar.iter().zip(&map[row0 * COLS..(row0 + 2) * COLS]).enumerate() {
            let col = i % COLS;
            if with != without && !(col0..col0 + SK_HALF_COLS).contains(&col) {
                return Err(Bad::answer(format!(
                    "the skills screen's bar on place {p} reaches past its half of the screen, at cell {col}"
                )));
            }
        }
        for row in 0..2 {
            halves.extend(&bar[row * COLS + col0..row * COLS + col0 + SK_HALF_COLS]);
        }
    }
    Ok(json!({
        "tiles": crate::convert::tiles_json(&made.tiles),
        "colors": crate::convert::colors_json(&made.colors),
        "map": map,
        "bars": halves,
    }))
}

/// Per skill of the database, what the cartridge needs to write it on the
/// map: the description's two lines as `[start, letters]` slices of the
/// text the battle carries, and whether the map can use it
/// ([`rm2k_rules::skill::usable_on_the_map`]). By number, as text, for the
/// emission to pick the ones the cartridge carries.
pub fn per_skill(game: &Game) -> Result<Value> {
    let mut out = Map::new();
    for (&id, skill) in &game.skills {
        let [(s1, n1), (s2, n2)] = description_spans(&game.font, &game.skill_description(id)?);
        if s1 != 0 || s2 > 255 || n1 > 255 || n2 > 255 {
            return Err(Bad::answer(format!("skill {id}'s description does not fit in a byte per number")));
        }
        out.insert(
            id.to_string(),
            json!({
                "lines": [n1, s2, n2],
                "field": rm2k_rules::skill::usable_on_the_map(skill, &game.states),
            }),
        );
    }
    Ok(Value::Object(out))
}

/// A page of the list as the text layer composes it: the description's
/// lines of skill `under`, the status line, and up to `SK_ROWS` rows of
/// `listed` from `top`. `grey` says per listed skill whether it goes in
/// grey.
#[allow(clippy::too_many_arguments)]
pub fn page_text(
    game: &Game,
    actor: i32,
    level: i64,
    hp: (i64, i64),
    sp: (i64, i64),
    listed: &[i32],
    grey: &[bool],
    under: Option<i32>,
    top: usize,
) -> Result<Grid> {
    let font = &game.font;
    let mut t = Grid::default();
    if let Some(k) = under {
        let text = game.skill_description(k)?;
        let letters: Vec<char> = text.chars().collect();
        for (n, (start, len)) in description_spans(font, &text).iter().enumerate() {
            let line: String = letters[*start..*start + *len].iter().collect();
            if !line.is_empty() {
                t.write(SK_HELP_ROW0 + 2 * n, SK_HELP_COL, &line, ITEM_WHITE);
            }
        }
    }
    let row = SK_STATUS_ROW;
    let name = texts::fit_cells(font, &texts::item_text(&game.actor_name(actor)?, usize::MAX), SK_NAME_WIDTH);
    t.write(row, SK_NAME_COL, &name, ITEM_WHITE);
    t.write(row, SK_LEVEL_COL, &game.term("lvl_short")?, ITEM_RED);
    t.write_number(row, SK_LEVEL_NUM_COL, level, LEVEL_DIGITS, ITEM_WHITE);
    t.write(row, SK_STATE_COL, &texts::fit_cells(font, &game.term("normal_status")?, SK_STATE_WIDTH), ITEM_WHITE);
    t.write(row, SK_HP_COL, &game.term("hp_short")?, ITEM_RED);
    t.write(row, SK_HP_NUM_COL, &capped_pair(hp), ITEM_WHITE);
    t.write(row, SK_SP_COL, &game.term("sp_short")?, ITEM_RED);
    t.write(row, SK_SP_NUM_COL, &capped_pair(sp), ITEM_WHITE);
    for (k, &skill) in listed.iter().enumerate().skip(SK_COLUMNS * top).take(SK_ROWS * SK_COLUMNS) {
        let p = k - SK_COLUMNS * top;
        let row = SK_LIST_ROW0 + 2 * (p / SK_COLUMNS);
        let col = SK_COLUMN_DX * (p % SK_COLUMNS);
        let variant = if grey[k] { ITEM_GRAY } else { ITEM_WHITE };
        let name = texts::fit_cells(font, &game.skill_name(skill)?, SK_NAME_CELLS);
        t.write(row, col + SK_NAME_DX, &name, variant);
        let cost: String = texts::right(game.skill(skill)?.sp_cost.into(), SK_COST_DIGITS)
            .chars()
            .map(|c| if c == ' ' { rm2k_snes_text::font::FIGURE_BLANK } else { c })
            .collect();
        t.write(row, col + SK_DASH_DX, &format!("-{cost}"), variant);
    }
    Ok(t)
}

/// The HP or the SP as the status line writes them, one run: the current
/// in three places, the slash and the maximum in three, each capped at 999
/// as the battle caps them —`ba_capped`—.
fn capped_pair((now, max): (i64, i64)) -> String {
    let places = |v: i64| -> String {
        texts::right(v.clamp(0, 999), 3)
            .chars()
            .map(|c| if c == ' ' { rm2k_snes_text::font::FIGURE_BLANK } else { c })
            .collect()
    };
    format!("{}/{}", places(now), places(max))
}

/// The most pairs a page can ask of the text layer: the widest
/// description of the database's skills that a list can show —normal or
/// switch, costing up to 99, `skill_usable` in `rm2k-snes-battle`—, the
/// status line with actor `actor`, and the sixteen widest names, all white.
/// A bound over the whole database, which no actor's page reaches: the
/// converter warns against [`SK_TEXT_PAIRS`] with it.
pub fn worst_page_pairs(game: &Game, actor: i32) -> Result<usize> {
    let listable: Vec<i32> = game
        .skills
        .values()
        .filter(|s| matches!(s.r#type.to_i32(), 0 | 3) && s.sp_cost <= 99)
        .map(|s| s.id)
        .collect();
    if listable.is_empty() {
        return Ok(0);
    }
    let mut names = Vec::new();
    let mut descs = Vec::new();
    for &k in &listable {
        names.push((game.font.width(&texts::fit_cells(&game.font, &game.skill_name(k)?, SK_NAME_CELLS)), k));
        descs.push((game.font.width(&game.skill_description(k)?), k));
    }
    names.sort_by(|a, b| b.cmp(a));
    let page: Vec<i32> = names.iter().map(|n| n.1).take(SK_ROWS * SK_COLUMNS).collect();
    let widest = descs.iter().max().map(|d| d.1);
    let grey = vec![false; page.len()];
    let t = page_text(game, actor, 99, (999, 999), (999, 999), &page, &grey, widest, 0)?;
    Ok(t.pairs(&game.font))
}

