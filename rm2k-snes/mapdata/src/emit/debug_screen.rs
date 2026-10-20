//! The debug screen: what `rm2k-snes-screens` answered of it, as the
//! runtime's `debug_screen.s` reads it. A cartridge without it gets only
//! `DEBUG_SCREEN = 0`, an equate, so its ROM is the same byte for byte as
//! before the screen existed.

use crate::asm::block;
use crate::fail::{Bad, Result};
use crate::json::{bytes, colors, ints, list_at, tiles};
use crate::snes::{cgram_bytes, pack_tile, words_le};
use serde_json::Value;

/// How many bytes the windows' tilemap takes: 32 by 28 words.
const SCREEN_MAP_BYTES: usize = 32 * 28 * 2;
/// And a bar: two cell rows of it.
const BAR_BYTES: usize = 2 * 32 * 2;

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
    // The names, in one block read with `lda f:dbg_data, x`.
    out.push_str(&block("dbg_data", &bytes(get("blob")?)?));
    out.push('\n');
    let layout = words(get("layout")?)?;
    if layout.len() != SCREEN_MAP_BYTES {
        return Err(Bad::answer(format!(
            "the debug screen's tilemap is {} bytes and a tilemap {SCREEN_MAP_BYTES}",
            layout.len()
        )));
    }
    out.push_str(&block("dbg_layout", &layout));
    out.push('\n');
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
    out.push_str(&block("dbg_bars", &bars));
    out.push('\n');
    // At 2bpp: BG2's in mode 5, the 512-wide mode the screen runs in.
    let packed: Vec<u8> = border_tiles.iter().flat_map(|t| pack_tile(t, 2)).collect();
    out.push_str(&block("dbg_border_tiles", &packed));
    out.push('\n');
    out.push_str(&block("dbg_border_cgram", &cgram_bytes(&border_colors)));
    out.push('\n');
    Ok(())
}
