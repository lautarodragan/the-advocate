//! The font of the text screens —items, equipment, shop, and the battle's
//! text—: each character in two cells, one above the other, in four
//! colours, so the cartridge writes any text two tilemap words per letter.

use crate::cells::{self, Bank, Color, Counts, BLACK};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use std::collections::BTreeMap;
use voodoo::pack::Indices;

/// The bank: the tiles, one palette per variant —white, gray, "goes up"
/// and red, see `ITEM_WHITE`— and per variant the two tilemap words of
/// each character it has. The "goes up" one has only `ITEM_UP_CHARS`. The
/// space is two blank cells: it is what the cursor erases with.
#[derive(Debug, Clone)]
pub struct ItemsFont {
    pub tiles: Vec<Indices>,
    pub palettes: Vec<Vec<Color>>,
    pub glyphs: Vec<BTreeMap<char, Vec<u16>>>,
}

pub fn items_screen(game: &Game, skin: &Skin) -> Result<ItemsFont> {
    let font = &game.font;
    let mut layers = Vec::new();
    for variant in [ITEM_WHITE, ITEM_GRAY, ITEM_UP, ITEM_RED] {
        for n in 0..ITEM_CHARS {
            let c = char::from_u32((ITEM_FIRST_CHAR + n) as u32).expect("ASCII");
            if variant == ITEM_UP && !ITEM_UP_CHARS.contains(c) {
                continue;
            }
            let mut image = cells::layer();
            skin.draw_line(&mut image, 1, 2, &c.to_string(), ITEM_COLORS[variant], font);
            layers.push((variant, c, image));
        }
    }
    let mut seen = vec![Counts::default(); 4];
    for (variant, _, image) in &layers {
        seen[*variant].add_picture(image);
    }
    let mut palettes = Vec::new();
    let mut indices = Vec::new();
    for counts in &seen {
        if counts.len() > 15 {
            return Err(Bad::answer(format!(
                "the text screens' font uses {} colours and 4bpp fits 15",
                counts.len()
            )));
        }
        let mut palette = vec![BLACK];
        palette.extend(counts.by_use());
        indices.push(cells::index_of(&palette));
        palettes.push(palette);
    }
    let mut bank = Bank::default();
    let mut glyphs = vec![BTreeMap::new(); 4];
    for (variant, c, image) in &layers {
        let words = cells::cell_block(image, 0, 2, &mut bank, &indices[*variant], 0, 1, *variant as u16)?;
        glyphs[*variant].insert(*c, words);
    }
    if bank.len() > ITEMS_TILES_MAX {
        return Err(Bad::answer(format!(
            "the text screens' font gathers {} tiles and its bank fits {ITEMS_TILES_MAX}",
            bank.len()
        )));
    }
    Ok(ItemsFont {
        tiles: bank.tiles,
        palettes,
        glyphs,
    })
}
