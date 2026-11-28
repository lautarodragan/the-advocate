//! The custom menus: what `rm2k-snes-screens` answered of them, as the
//! runtime's `custom_menu.s` reads it. A cartridge without any still gets
//! the labels, empty, so the runtime assembles the same.

use crate::asm::Inc;
use crate::compress::compress_many;
use crate::fail::{Bad, Result};
use crate::json::by_key;
use crate::snes::{cgram_bytes, pack_tile, words_le};
use rm2k_snes_screens::answer::CustomMenus;

/// How many bytes a BG1 tilemap of the screen takes: 32 by 28 words.
const SCREEN_MAP_BYTES: usize = 32 * 28 * 2;

fn words(v: &[u16]) -> Vec<u8> {
    words_le(v.iter().map(|&w| w.into()))
}

/// The section, after the pause menu's tables: `custom` is the screens
/// stage's `custom_menus`, with no labels if the project declares none.
pub fn section(out: &mut Inc, custom: &CustomMenus) -> Result<()> {
    out.push_str("\n; --- the custom menus: see custom_menu.s ---\n");
    out.push_str(".segment \"RODATA\"\n");
    let built = custom.built.as_ref().filter(|_| !custom.labels.is_empty());
    let Some(built) = built else {
        if let Some(geometry) = custom.layout.as_object() {
            for (name, value) in by_key(geometry) {
                out.push_str(&format!("{name} = {}\n", value.as_i64().unwrap_or(0)));
            }
        }
        out.push_str(
            "CM_MENUS = 0\nCM_LAYOUTS = 0\nCM_BORDER_TILES = 0\nCM_BORDER_COLORS = 0\nCM_INKS_N = 0\n\
             CM_PORTRAITS = 0\n.block 1\ncmenu_data:\n    .byte 0\n",
        );
        for label in [
            "cm_layout_lo",
            "cm_layout_bk",
            "cm_portrait_lo",
            "cm_portrait_bk",
        ] {
            out.push_str(&format!(".block 1\n{label}:\n    .byte 0\n"));
        }
        for label in [
            "cm_bars",
            "cm_border_tiles",
            "cm_border_cgram",
            "cm_inks_cgram",
            "cm_portrait_cgram",
        ] {
            out.push_str(&format!(".block 1\n{label}:\n    .byte 0\n"));
        }
        return Ok(());
    };
    let layouts = &built.layouts;
    let (border_tiles, border_colors) = (&built.tiles, &built.colors);
    let inks = &built.inks;
    let portraits = &built.portraits;
    let geometry = custom
        .layout
        .as_object()
        .ok_or_else(|| Bad::answer("the custom menus' layout is not an object"))?;
    let mut equates = String::new();
    for (name, value) in by_key(geometry) {
        let n = value
            .as_i64()
            .ok_or_else(|| Bad::answer(format!("the custom menus' {name} is not a number")))?;
        equates.push_str(&format!("{name} = {n}\n"));
    }
    out.push_str(&equates);
    out.push_str(&format!(
        "CM_MENUS = {}\nCM_LAYOUTS = {}\nCM_BORDER_TILES = {}\nCM_BORDER_COLORS = {}\nCM_INKS_N = {}\n\
         CM_PORTRAITS = {}\n",
        custom.labels.len(),
        layouts.len(),
        border_tiles.len(),
        border_colors.len(),
        inks.len(),
        portraits.len()
    ));
    // The data the screen walks, in one block: it reads it with
    // `lda f:cmenu_data, x`, and its offsets are sixteen bits.
    out.block("cmenu_data", &built.blob);
    // Each arrangement of windows, a whole BG1 tilemap uploaded at once.
    for (k, layout) in layouts.iter().enumerate() {
        let data = words(layout);
        if data.len() != SCREEN_MAP_BYTES {
            return Err(Bad::answer(format!(
                "custom menu arrangement {k} is {} bytes and a tilemap {SCREEN_MAP_BYTES}",
                data.len()
            )));
        }
        out.block(format!("cm_layout_{k}"), &data);
    }
    let names: Vec<String> = (0..layouts.len())
        .map(|k| format!("cm_layout_{k}"))
        .collect();
    out.words(
        "cm_layout_lo",
        names.iter().map(|n| format!(".loword({n})")),
    );
    out.bytes("cm_layout_bk", names.iter().map(|n| format!("^{n}")));
    // The bar on each tab: its two cell rows of the subjects' tilemap.
    let mut bars = Vec::new();
    for bar in &built.bars {
        bars.extend(words(bar));
    }
    out.block(
        "cm_bars",
        &bars
            .clone()
            .into_iter()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>(),
    );
    let packed: Vec<u8> = border_tiles.iter().flat_map(|t| pack_tile(t, 8)).collect();
    out.block("cm_border_tiles", &packed);
    out.block("cm_border_cgram", &cgram_bytes(border_colors));
    let ink_colors: Vec<_> = inks.iter().flatten().copied().collect();
    out.block(
        "cm_inks_cgram",
        &cgram_bytes(&ink_colors)
            .into_iter()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>(),
    );
    // The portraits: their tiles in LZ2, which the screen decompresses
    // into WRAM and uploads a few rows per vblank, and their palettes.
    let mut raws = Vec::new();
    let mut palettes = Vec::new();
    for p in portraits {
        raws.push(
            p.tiles
                .iter()
                .flat_map(|t| pack_tile(t, 4))
                .collect::<Vec<u8>>(),
        );
        palettes.extend(&p.palette);
    }
    let refs: Vec<&[u8]> = raws.iter().map(|r| r.as_slice()).collect();
    let streams = compress_many(&refs)?;
    for (k, s) in streams.iter().enumerate() {
        out.block(format!("cm_portrait_{k}"), s);
    }
    let names: Vec<String> = (0..streams.len())
        .map(|k| format!("cm_portrait_{k}"))
        .collect();
    out.words(
        "cm_portrait_lo",
        names.iter().map(|n| format!(".loword({n})")),
    );
    out.bytes(
        "cm_portrait_bk",
        super::or_zero(names.iter().map(|n| format!("^{n}")).collect()),
    );
    out.block(
        "cm_portrait_cgram",
        &cgram_bytes(&palettes)
            .into_iter()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>(),
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// The geometry's equates go in the order of their names, whatever
    /// order the screens inserted them in: in the converter, with
    /// `preserve_order`, that order reaches this crate —`cargo test
    /// --workspace` shows it—, where the crate's binary saw them sorted
    /// until 2026-11-27.
    #[test]
    fn the_geometry_goes_in_the_order_of_its_names() {
        let custom = CustomMenus {
            labels: Vec::new(),
            built: None,
            layout: json!({"CM_ZED": 2, "CM_ALPHA": 1}),
        };
        let mut out = Inc::new(String::new());
        section(&mut out, &custom).unwrap();
        let text = out.into_text();
        let alpha = text.find("CM_ALPHA = 1").unwrap();
        let zed = text.find("CM_ZED = 2").unwrap();
        assert!(alpha < zed, "{text}");
    }
}
