//! A map whose ChipSet animation does not fit where the console keeps its
//! drawings: the tiles that cover the fewest cells of the map stand still.
//!
//! **It changes what is seen**, and it is here and not in `wally` because
//! the cap is this crate's —[`LZ2_CAP_ANIM`], the WRAM the runtime reserves
//! for the drawings— and because standing still needs nothing redrawn: each
//! family's tiles are a contiguous run at the end of the bank, drawing 0 is
//! what the bank already carries for them, and the console uploads the first
//! `tiles` of each drawing. So keeping the first `k` of a run and dropping
//! the rest from every drawing leaves the others on drawing 0, which is how
//! RM2k shows them before the clock moves.
//!
//! Which `k` per family is the one choice: the one that keeps the most cells
//! of the map moving —counted over the map's own cells, by the block table—,
//! within the cap. A run is cut and not reordered, so the tiles that stay
//! are the first ones Voodoo numbered, which are the first met row by row;
//! reordering them would move tile numbers in the block table. Ties go to
//! the one that keeps more bytes, and then to the first family.
//!
//! A map that fits is not touched: byte for byte the same.

use crate::materials::LZ2_CAP_ANIM;
use crate::record::FAMILIES;
use crate::request::Map;
use crate::snes::BYTES_PER_TILE;

/// What the cells of the map draw on the background, per tile of the
/// bank: four per block, as many times as cells show the block. Tiles only
/// a `TileSubstitution` brings count zero.
fn tile_uses(map: &Map, tiles: usize) -> Vec<u64> {
    const BLOCK_BYTES: usize = 16;
    let mut per_block: Vec<u64> = vec![0; map.blocks.len() / BLOCK_BYTES];
    for cell in map.cells.chunks_exact(2) {
        let block = u16::from_le_bytes([cell[0], cell[1]]) as usize;
        if let Some(n) = per_block.get_mut(block) {
            *n += 1;
        }
    }
    let mut uses = vec![0; tiles];
    for (block, &n) in per_block.iter().enumerate() {
        // The first four words are the background's: see `blocks.rs` in wally.
        for k in 0..4 {
            let at = block * BLOCK_BYTES + 2 * k;
            let tile = usize::from(u16::from_le_bytes([map.blocks[at], map.blocks[at + 1]]) & 0x3FF);
            if let Some(u) = uses.get_mut(tile) {
                *u += n;
            }
        }
    }
    uses
}

/// A family's run as the choice sees it: how many drawings it uploads, and
/// the cells its first `k` tiles cover, for every `k`.
pub struct Offer {
    pub drawings: usize,
    pub covered: Vec<u64>,
}

/// How many tiles of each run stay: the most cells moving within `budget`
/// tiles' worth of drawings, then the most of those, then the first family.
pub fn choose(offers: &[Offer], budget: usize) -> Vec<usize> {
    fn walk(offers: &[Offer], budget: usize) -> (u64, usize, Vec<usize>) {
        let Some((first, rest)) = offers.split_first() else {
            return (0, 0, Vec::new());
        };
        let most = (first.covered.len() - 1).min(budget / first.drawings.max(1));
        let mut best: Option<(u64, usize, Vec<usize>)> = None;
        for k in (0..=most).rev() {
            let spent = k * first.drawings;
            let (cells, kept, mut ks) = walk(rest, budget - spent);
            let here = (cells + first.covered[k], kept + spent);
            if best.as_ref().is_none_or(|(c, b, _)| here > (*c, *b)) {
                ks.insert(0, k);
                best = Some((here.0, here.1, ks));
            }
        }
        best.unwrap()
    }
    walk(offers, budget).2
}

/// [`fit`] for each map, and what each one lost, in order.
pub fn fit_all(maps: &mut [Map]) -> Vec<String> {
    maps.iter_mut().filter_map(fit).collect()
}

/// Cuts the map's runs until their drawings fit in WRAM, and says what it
/// lost; nothing, and nothing touched, if they already fit.
pub fn fit(map: &mut Map) -> Option<String> {
    let per_tile = BYTES_PER_TILE * map.bpp / 8;
    let bytes: usize = map.runs.iter().map(|r| r.drawings.iter().map(Vec::len).sum::<usize>()).sum();
    if bytes <= LZ2_CAP_ANIM {
        return None;
    }
    let uses = tile_uses(map, map.tiles.len() / per_tile);
    // In the order their drawings go: the same as `anim_bytes`.
    let order: Vec<usize> = FAMILIES
        .iter()
        .filter_map(|(_, family, _)| map.runs.iter().position(|r| r.family == *family))
        .collect();
    let offers: Vec<Offer> = order
        .iter()
        .map(|&i| {
            let run = &map.runs[i];
            let mut covered = vec![0];
            for t in 0..run.tiles as usize {
                let u = uses.get(run.base as usize + t).copied().unwrap_or(0);
                covered.push(covered[t] + u);
            }
            Offer { drawings: run.drawings.len(), covered }
        })
        .collect();
    let keep = choose(&offers, LZ2_CAP_ANIM / per_tile);
    let mut lost = Vec::new();
    for ((&i, offer), &k) in order.iter().zip(&offers).zip(&keep) {
        let run = &mut map.runs[i];
        let tiles = run.tiles as usize;
        if k == tiles {
            continue;
        }
        let all = offer.covered[tiles];
        lost.push(format!(
            "{} of its {tiles} {} tiles ({} of {all} cells)",
            tiles - k,
            run.family,
            all - offer.covered[k]
        ));
        run.tiles = k as i64;
        for drawing in &mut run.drawings {
            drawing.truncate(k * per_tile);
        }
    }
    Some(format!(
        "  map {}: WARNING, the ChipSet animation's drawings are {bytes} bytes and {LZ2_CAP_ANIM} \
         fit in WRAM: {} stand still on their first drawing",
        map.id,
        lost.join(" and ")
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn offer(drawings: usize, uses: &[u64]) -> Offer {
        let mut covered = vec![0];
        for u in uses {
            covered.push(covered.last().unwrap() + u);
        }
        Offer { drawings, covered }
    }

    #[test]
    fn what_fits_whole_stays_whole() {
        assert_eq!(choose(&[offer(3, &[1, 1]), offer(4, &[1])], 10), [2, 1]);
    }

    #[test]
    fn the_cells_that_move_decide_and_not_the_tiles() {
        // Two water tiles cost six, one animated tile four: with seven, the
        // animated one covers more of the map than both water ones.
        assert_eq!(choose(&[offer(3, &[2, 2]), offer(4, &[5])], 7), [1, 1]);
        assert_eq!(choose(&[offer(3, &[2, 2]), offer(4, &[5])], 6), [0, 1]);
        assert_eq!(choose(&[offer(3, &[2, 2]), offer(4, &[5])], 3), [1, 0]);
    }

    #[test]
    fn a_tie_keeps_more_drawings_and_then_the_first_family() {
        // Tiles that no cell shows still go if they fit.
        assert_eq!(choose(&[offer(3, &[0, 0]), offer(4, &[0])], 10), [2, 1]);
        assert_eq!(choose(&[offer(2, &[1]), offer(2, &[1])], 2), [1, 0]);
    }
}
