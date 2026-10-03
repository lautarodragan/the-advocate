//! How many cells a composed line puts ink on: what a console that
//! composes text into tiles of its own pays for it.
//!
//! The screens' text layer —`text_layer.s` in the runtime— gives each
//! column of a row that got ink a pair of tiles from a pool, and a row
//! that says what another one said takes that one's. So what a screen
//! asks of the pool is, per distinct row, the cells its runs put ink on.

use crate::font::Font;
use std::collections::BTreeSet;

/// A cell of eight pixels.
pub const CELL: usize = 8;

/// The cells a run of `text` from pixel `x` puts ink on —each letter's
/// ink and shadow, from where it starts—, added to `cells`.
pub fn ink(font: &Font, x: usize, text: &str, cells: &mut BTreeSet<usize>) {
    let mut x = x;
    for c in text.chars() {
        let reach = font.reach(c);
        if reach > 0 {
            cells.extend(x / CELL..=(x + reach - 1) / CELL);
        }
        x += font.advance(c);
    }
}

/// The pairs of tiles a screen asks of the pool: per distinct row —its
/// runs, `(x, text, colour)`—, the cells it puts ink on. Rows that say
/// the same share their tiles.
pub fn pairs<'a>(font: &Font, rows: impl IntoIterator<Item = &'a [(usize, String, usize)]>) -> usize {
    let mut seen: BTreeSet<Vec<(usize, String, usize)>> = BTreeSet::new();
    let mut total = 0;
    for row in rows {
        if row.is_empty() || !seen.insert(row.to_vec()) {
            continue;
        }
        let mut cells = BTreeSet::new();
        for (x, text, _) in row {
            ink(font, *x, text, &mut cells);
        }
        total += cells.len();
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_letter_takes_the_cells_its_ink_and_shadow_reach() {
        let font = Font::rm2k(crate::font::MINCHO);
        let mut cells = BTreeSet::new();
        ink(&font, 1, "A", &mut cells);
        assert_eq!(cells.into_iter().collect::<Vec<_>>(), vec![0]);
        let mut cells = BTreeSet::new();
        ink(&font, 6, "A", &mut cells);
        assert_eq!(cells.into_iter().collect::<Vec<_>>(), vec![0, 1]);
    }

    #[test]
    fn rows_that_say_the_same_share_their_pairs() {
        let font = Font::rm2k(crate::font::MINCHO);
        let row = vec![(1, "AB".to_string(), 0)];
        assert_eq!(pairs(&font, [row.as_slice(), row.as_slice()]), pairs(&font, [row.as_slice()]));
    }
}
