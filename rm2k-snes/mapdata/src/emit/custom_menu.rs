//! The custom menus: what `rm2k-snes-screens` answered of them, as the
//! runtime's `custom_menu.s` reads it. A cartridge without any still gets
//! the labels, empty, so the runtime assembles the same.

use crate::asm::block;
use crate::compress::compress_many;
use crate::fail::{Bad, Result};
use crate::json::{bytes, colors, ints, list, list_at, tiles};
use crate::snes::{cgram_bytes, pack_tile, words_le};
use serde_json::Value;

/// How many bytes a BG1 tilemap of the screen takes: 32 by 28 words.
const SCREEN_MAP_BYTES: usize = 32 * 28 * 2;

fn words(v: &Value) -> Result<Vec<u8>> {
    Ok(words_le(ints(v)?.into_iter().map(|w| w as u32)))
}

/// The section, after the pause menu's tables: `custom` is the screens
/// stage's `custom_menus`, null if the project declares none.
pub fn section(out: &mut String, custom: &Value) -> Result<()> {
    out.push_str("\n; --- the custom menus: see custom_menu.s ---\n");
    out.push_str(".segment \"RODATA\"\n");
    let empty = custom.is_null() || list_at(custom, "labels").map_or(true, |l| l.is_empty());
    if empty {
        if let Some(geometry) = custom.get("layout").and_then(Value::as_object) {
            for (name, value) in geometry {
                out.push_str(&format!("{name} = {}\n", value.as_i64().unwrap_or(0)));
            }
        }
        out.push_str(
            "CM_MENUS = 0\nCM_LAYOUTS = 0\nCM_BORDER_TILES = 0\nCM_BORDER_COLORS = 0\nCM_INKS_N = 0\n\
             CM_PORTRAITS = 0\n.block 1\ncmenu_data:\n    .byte 0\n",
        );
        for label in ["cm_layout_lo", "cm_layout_bk", "cm_portrait_lo", "cm_portrait_bk"] {
            out.push_str(&format!(".block 1\n{label}:\n    .byte 0\n"));
        }
        for label in ["cm_bars", "cm_border_tiles", "cm_border_cgram", "cm_inks_cgram", "cm_portrait_cgram"] {
            out.push_str(&format!(".block 1\n{label}:\n    .byte 0\n"));
        }
        return Ok(());
    }
    let get = |key: &str| {
        custom
            .get(key)
            .ok_or_else(|| Bad::answer(format!("the custom menus have no `{key}`")))
    };
    let blob = bytes(get("blob")?)?;
    let layouts = list_at(custom, "layouts")?;
    let border_tiles = tiles(get("tiles")?)?;
    let border_colors = colors(get("colors")?)?;
    let inks = list_at(custom, "inks")?;
    let portraits = list_at(custom, "portraits")?;
    let geometry = get("layout")?
        .as_object()
        .ok_or_else(|| Bad::answer("the custom menus' layout is not an object"))?;
    let mut equates = String::new();
    for (name, value) in geometry {
        let n = value
            .as_i64()
            .ok_or_else(|| Bad::answer(format!("the custom menus' {name} is not a number")))?;
        equates.push_str(&format!("{name} = {n}\n"));
    }
    out.push_str(&equates);
    out.push_str(&format!(
        "CM_MENUS = {}\nCM_LAYOUTS = {}\nCM_BORDER_TILES = {}\nCM_BORDER_COLORS = {}\nCM_INKS_N = {}\n\
         CM_PORTRAITS = {}\n",
        list_at(custom, "labels")?.len(),
        layouts.len(),
        border_tiles.len(),
        border_colors.len(),
        inks.len(),
        portraits.len()
    ));
    // The data the screen walks, in one block: it reads it with
    // `lda f:cmenu_data, x`, and its offsets are sixteen bits.
    out.push_str(&block("cmenu_data", &blob));
    out.push('\n');
    // Each arrangement of windows, a whole BG1 tilemap uploaded at once.
    for (k, layout) in layouts.iter().enumerate() {
        let data = words(layout)?;
        if data.len() != SCREEN_MAP_BYTES {
            return Err(Bad::answer(format!(
                "custom menu arrangement {k} is {} bytes and a tilemap {SCREEN_MAP_BYTES}",
                data.len()
            )));
        }
        out.push_str(&block(&format!("cm_layout_{k}"), &data));
        out.push('\n');
    }
    let names: Vec<String> = (0..layouts.len()).map(|k| format!("cm_layout_{k}")).collect();
    out.push_str(&format!(
        ".block {}\ncm_layout_lo:\n    .word {}\n",
        2 * names.len(),
        names.iter().map(|n| format!(".loword({n})")).collect::<Vec<_>>().join(", ")
    ));
    out.push_str(&format!(
        ".block {}\ncm_layout_bk:\n    .byte {}\n",
        names.len(),
        names.iter().map(|n| format!("^{n}")).collect::<Vec<_>>().join(", ")
    ));
    // The bar on each tab: its two cell rows of the subjects' tilemap.
    let mut bars = Vec::new();
    for bar in list_at(custom, "bars")? {
        bars.extend(words(bar)?);
    }
    out.push_str(&block("cm_bars", &bars.clone().into_iter().chain(std::iter::once(0)).collect::<Vec<_>>()));
    out.push('\n');
    let packed: Vec<u8> = border_tiles.iter().flat_map(|t| pack_tile(t, 8)).collect();
    out.push_str(&block("cm_border_tiles", &packed));
    out.push('\n');
    out.push_str(&block("cm_border_cgram", &cgram_bytes(&border_colors)));
    out.push('\n');
    let mut ink_colors = Vec::new();
    for ink in inks {
        ink_colors.extend(colors(ink)?);
    }
    out.push_str(&block(
        "cm_inks_cgram",
        &cgram_bytes(&ink_colors).into_iter().chain(std::iter::once(0)).collect::<Vec<_>>(),
    ));
    out.push('\n');
    // The portraits: their tiles in LZ2, which the screen decompresses
    // into WRAM and uploads a few rows per vblank, and their palettes.
    let mut raws = Vec::new();
    let mut palettes = Vec::new();
    for p in portraits {
        let t = tiles(p.get("tiles").ok_or_else(|| Bad::answer("a portrait has no tiles"))?)?;
        raws.push(t.iter().flat_map(|t| pack_tile(t, 4)).collect::<Vec<u8>>());
        palettes.extend(colors(p.get("palette").ok_or_else(|| Bad::answer("a portrait has no palette"))?)?);
    }
    let refs: Vec<&[u8]> = raws.iter().map(|r| r.as_slice()).collect();
    let streams = compress_many(&refs)?;
    for (k, s) in streams.iter().enumerate() {
        out.push_str(&block(&format!("cm_portrait_{k}"), s));
        out.push('\n');
    }
    let names: Vec<String> = (0..streams.len()).map(|k| format!("cm_portrait_{k}")).collect();
    let or_zero = |v: Vec<String>| if v.is_empty() { "0".to_string() } else { v.join(", ") };
    out.push_str(&format!(
        ".block {}\ncm_portrait_lo:\n    .word {}\n",
        (2 * names.len()).max(2),
        or_zero(names.iter().map(|n| format!(".loword({n})")).collect())
    ));
    out.push_str(&format!(
        ".block {}\ncm_portrait_bk:\n    .byte {}\n",
        names.len().max(1),
        or_zero(names.iter().map(|n| format!("^{n}")).collect())
    ));
    out.push_str(&block(
        "cm_portrait_cgram",
        &cgram_bytes(&palettes).into_iter().chain(std::iter::once(0)).collect::<Vec<_>>(),
    ));
    out.push('\n');
    let _ = list;
    Ok(())
}
