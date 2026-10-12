//! The skills screen: its windows, as `rm2k-snes-screens` answered them
//! —`skills.rs` there—, and its geometry, as the runtime's
//! `skills_screen.s` reads them. What it needs of each skill goes with the
//! battle's `skill_*` tables.

use crate::asm::block;
use crate::fail::{Bad, Result};
use crate::json::{colors, ints, tiles};
use crate::snes::{cgram_bytes, pack_tile, words_le};
use serde_json::Value;

/// How many bytes a BG1 tilemap of the screen takes: 32 by 28 words.
const SCREEN_MAP_BYTES: usize = 32 * 28 * 2;

/// The geometry the runtime writes with, from the screens stage's `layout`.
const GEOMETRY: [&str; 26] = [
    "SK_HELP_ROW0",
    "SK_HELP_COL",
    "SK_STATUS_ROW",
    "SK_NAME_COL",
    "SK_NAME_WIDTH",
    "SK_LEVEL_COL",
    "SK_LEVEL_NUM_COL",
    "SK_STATE_COL",
    "SK_STATE_WIDTH",
    "SK_HP_COL",
    "SK_HP_NUM_COL",
    "SK_SP_COL",
    "SK_SP_NUM_COL",
    "SK_LIST_ROW0",
    "SK_ROWS",
    "SK_COLUMNS",
    "SK_COLUMN_DX",
    "SK_NAME_DX",
    "SK_NAME_CELLS",
    "SK_DASH_DX",
    "SK_COST_DIGITS",
    "SK_HALF_COLS",
    "MENU_SKILL",
    "ITEM_WHITE",
    "ITEM_GRAY",
    "ITEM_RED",
];

fn words(v: &Value) -> Result<Vec<u8>> {
    Ok(words_le(ints(v)?.into_iter().map(|w| w as u32)))
}

/// The section: `screens` is the screens stage's whole answer.
pub fn section(out: &mut String, screens: &Value) -> Result<()> {
    out.push_str("\n; --- the skills screen: see skills_screen.s ---\n");
    let layout = screens
        .get("layout")
        .ok_or_else(|| Bad::answer("the screens have no `layout`"))?;
    for name in GEOMETRY {
        let n = layout
            .get(name)
            .and_then(Value::as_i64)
            .ok_or_else(|| Bad::answer(format!("the screens' layout has no {name}")))?;
        out.push_str(&format!("{name} = {n}\n"));
    }
    let sk = screens
        .get("skills_screen")
        .ok_or_else(|| Bad::answer("the screens have no `skills_screen`"))?;
    let get = |key: &str| sk.get(key).ok_or_else(|| Bad::answer(format!("the skills screen has no `{key}`")));
    let border_tiles = tiles(get("tiles")?)?;
    let border_colors = colors(get("colors")?)?;
    let map = words(get("map")?)?;
    if map.len() != SCREEN_MAP_BYTES {
        return Err(Bad::answer(format!(
            "the skills screen's tilemap is {} bytes and a tilemap {SCREEN_MAP_BYTES}",
            map.len()
        )));
    }
    let bars = words(get("bars")?)?;
    out.push_str(&format!(
        "SK_BORDER_TILES = {}\nSK_BORDER_COLORS = {}\n",
        border_tiles.len(),
        border_colors.len()
    ));
    out.push_str(".segment \"RODATA\"\n");
    // The arrangement, uploaded whole, and right after it in the same block
    // each place's bar, two half rows of sixteen words, the top one first:
    // one bank byte reads both (`SK_BARS_OFS` in the runtime).
    out.push_str(&block("sk_layout", &[map, bars].concat()));
    out.push('\n');
    let packed: Vec<u8> = border_tiles.iter().flat_map(|t| pack_tile(t, 8)).collect();
    out.push_str(&block("sk_border_tiles", &packed));
    out.push('\n');
    out.push_str(&block("sk_border_cgram", &cgram_bytes(&border_colors)));
    out.push('\n');
    Ok(())
}
