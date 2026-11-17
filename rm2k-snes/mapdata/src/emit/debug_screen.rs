//! The debug screen: what `rm2k-snes-screens` answered of it, as the
//! runtime's `debug_screen.s` reads it. A cartridge without it gets only
//! `DEBUG_SCREEN = 0`, an equate, so its ROM is the same byte for byte as
//! before the screen existed.
//!
//! **Its bulk travels only in the `.msu`**, since 2026-11-16 —taro's: the
//! screen is for testing, which they do with the `.msu`, and it is not
//! needed to enjoy the game—: the font, the names, the windows. Each goes
//! as a `.msu_only` piece, which the packing sends to the `.msu` in any
//! cartridge, and the ROM keeps the code, the geometry, the letters'
//! advances and reaches and a table of where each page of names is. Without
//! the MSU-1 the pause menu does not offer the screen: see `debug_screen.s`.

use crate::asm::{block, msu_only_block};
use crate::fail::{Bad, Result};
use crate::json::{bytes, colors, ints, list_at, tiles};
use crate::snes::{cgram_bytes, pack_tile, words_le};
use serde_json::Value;

/// How many bytes the windows' tilemap takes: 32 by 28 words.
const SCREEN_MAP_BYTES: usize = 32 * 28 * 2;
/// And a bar: two cell rows of it.
const BAR_BYTES: usize = 2 * 32 * 2;
/// A precomposed letter's bytes, in each phase: 13 rows of two columns'
/// mask and planes. The runtime's `FONT_PRE_CHAR`, of the game's font.
const FONT_PRE_CHAR: usize = 13 * 12;

fn words(v: &Value) -> Result<Vec<u8>> {
    Ok(words_le(ints(v)?.into_iter().map(|w| w as u32)))
}

/// The section: `debug` is the screens stage's `debug_screen`, null if the
/// cartridge does not carry it.
pub fn section(out: &mut String, debug: &Value) -> Result<()> {
    out.push_str("\n; --- the debug screen: see debug_screen.s ---\n");
    if debug.is_null() {
        out.push_str("DEBUG_SCREEN = 0\n");
        return Ok(());
    }
    let get = |key: &str| {
        debug
            .get(key)
            .ok_or_else(|| Bad::answer(format!("the debug screen has no `{key}`")))
    };
    out.push_str("DEBUG_SCREEN = 1\n");
    let geometry = get("geometry")?
        .as_object()
        .ok_or_else(|| Bad::answer("the debug screen's geometry is not an object"))?;
    for (name, value) in geometry {
        let n = value
            .as_i64()
            .ok_or_else(|| Bad::answer(format!("the debug screen's {name} is not a number")))?;
        out.push_str(&format!("{name} = {n}\n"));
    }
    let border_tiles = tiles(get("tiles")?)?;
    let border_colors = colors(get("colors")?)?;
    out.push_str(&format!(
        "DBG_BORDER_TILES = {}\nDBG_BORDER_COLORS = {}\n",
        border_tiles.len(),
        border_colors.len()
    ));
    out.push_str(".segment \"RODATA\"\n");
    // The names, a piece per page —its table and its strings—, which the
    // screen loads into WRAM when the page changes; and in the ROM, where
    // each one is: its unit in the `.msu`'s region.
    let pages = list_at(debug, "pages")?;
    let mut units = Vec::new();
    for (k, page) in pages.iter().enumerate() {
        out.push_str(&msu_only_block(&format!("dbg_page{k}"), &bytes(page)?));
        out.push('\n');
        units.push(format!(".loword(dbg_page{k})"));
    }
    out.push_str(&format!(".block {}\ndbg_pages:\n", 2 * units.len()));
    for line in units.chunks(8) {
        out.push_str(&format!("    .word {}\n", line.join(", ")));
    }
    let layout = words(get("layout")?)?;
    if layout.len() != SCREEN_MAP_BYTES {
        return Err(Bad::answer(format!(
            "the debug screen's tilemap is {} bytes and a tilemap {SCREEN_MAP_BYTES}",
            layout.len()
        )));
    }
    // The windows' tilemap and its bars, one piece the screen loads into WRAM
    // when it opens, the tilemap first: `DBG_FRAME_BYTES`.
    // The bars: the ranges' ten, then the list's, two cell rows each.
    let mut bars = Vec::new();
    for bar in list_at(debug, "bars")? {
        let data = words(bar)?;
        if data.len() != BAR_BYTES {
            return Err(Bad::answer(format!(
                "a debug screen bar is {} bytes and two cell rows {BAR_BYTES}",
                data.len()
            )));
        }
        bars.extend(data);
    }
    let frame: Vec<u8> = layout.iter().chain(&bars).copied().collect();
    out.push_str(&format!(
        "DBG_FRAME_BYTES = {}\nDBG_BARS_AT = {}\n",
        frame.len(),
        layout.len()
    ));
    out.push_str(&msu_only_block("dbg_frame", &frame));
    out.push('\n');
    // The windows' tiles —at 2bpp: BG2's in mode 5, the 512-wide mode the
    // screen runs in— and their colours behind them, one piece the screen
    // reads into WRAM and uploads when it opens.
    let mut border: Vec<u8> = border_tiles.iter().flat_map(|t| pack_tile(t, 2)).collect();
    border.extend(cgram_bytes(&border_colors));
    out.push_str(&msu_only_block("dbg_border", &border));
    out.push('\n');
    // Its font, which only the text layer's 512-wide mode reads: how far
    // each letter moves the line and how far it paints, and its glyphs
    // precomposed for the inks, a table per phase —what `font_advance`,
    // `font_reach` and `scr_pre0` to `scr_pre7` are of the game's font—.
    let font = get("font")?;
    let small = |name: &str| -> Result<Vec<u8>> {
        Ok(ints(&font[name])?.into_iter().map(|n| n as u8).collect())
    };
    out.push_str(&block("dbg_font_advance", &small("advances")?));
    out.push('\n');
    out.push_str(&block("dbg_font_reach", &small("reach")?));
    out.push('\n');
    let phases = list_at(font, "prerender")?;
    if phases.len() != 8 {
        return Err(Bad::answer(format!(
            "the debug screen's font has {} phases and a cell eight",
            phases.len()
        )));
    }
    // The precomposed glyphs, a piece per phase, which the screen reads a
    // letter at a time into its cache in WRAM: `DBG_GLYPHS` letters each.
    let mut glyphs = None;
    for (phase, data) in phases.iter().enumerate() {
        let data = bytes(data)?;
        if data.len() % FONT_PRE_CHAR != 0
            || glyphs.is_some_and(|g| g != data.len() / FONT_PRE_CHAR)
        {
            return Err(Bad::answer(format!(
                "the debug screen's phase {phase} is {} bytes, not a letter's {FONT_PRE_CHAR} \
                 times as many letters as the others",
                data.len()
            )));
        }
        glyphs = Some(data.len() / FONT_PRE_CHAR);
        out.push_str(&msu_only_block(&format!("dbg_pre{phase}"), &data));
        out.push('\n');
    }
    out.push_str(&format!("DBG_GLYPHS = {}\n", glyphs.unwrap_or(0)));
    Ok(())
}
