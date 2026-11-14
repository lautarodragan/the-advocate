//! A message without its background over the layer above: what the build
//! decides for it.
//!
//! On the lines a window without its background draws on, BG2 is the
//! window's own plane, and the console carries the map's layer above into
//! it —see `msg_layer_*` in the runtime's `message_layer.s`—: the cells
//! without letters take the layer's tilemap entries, and the cells with
//! letters are composed from the layer's pixels with the glyph over them.
//! The glyph comes from the composer's tables, which carry the window's
//! entries —the twelve rows' and the shadow's—, so a cell with letters
//! needs those entries to hold the text's colours in the palette it is
//! drawn with.
//!
//! **That palette is the text's, not the layer's**: a copy of the layer's
//! palette with the text's colours at the window's indices, in a BG palette
//! the map leaves free just under the layer's. The runtime builds it from
//! the layer's tinted colours and the window's untinted ones, so the tint
//! reaches the layer and not the letters, as in RM2k. Putting the text's
//! colours in the layer's own palette would have left, under a tint,
//! either the letters on the layer tinted or every pixel of the layer with
//! those colours untinted all over the map —ABL's memory, on maps 5 and 6,
//! goes under a sepia tone—.
//!
//! What this decides, per map:
//!
//! * **Which of the layer's colours sit at the text's indices.** If the
//!   palette has room, none: the layer's colours move off them, and the
//!   cells with letters show the layer exactly. If it does not, the
//!   layer's colours nearest the text's go there, and inside those cells
//!   they show as the text's: taro's rule, "the text keeps its exact
//!   colours and the nearest entries of the layer give way" (2026-10-19).
//!   It is a permutation of each palette, and of the pixels of the tiles
//!   drawn with it: outside the cells with letters nothing changes.
//! * **Which BG palettes the text's copies go in**: as many as the layer
//!   has, right under its own, if the background does not reach them.
//!   Otherwise none, and the map keeps the window's old look: the letters
//!   in the window's palette, over nothing.

use crate::request::{Emit, Map};
use crate::snes::COLORS_PER_PALETTE;

/// The BG palettes of the lower half of colour memory.
const BG_PALETTES: usize = 8;
/// A tile's bytes at four bits.
const TILE_BYTES: usize = 32;
/// Where a block's four cells of the layer above start: see
/// [`crate::materials::BLOCK_BYTES`].
const BLOCK_ABOVE: usize = 8;

/// The text's entries in the window's palette, with their colours: the
/// glyph's rows' and the shadow's, as the composer's tables index them.
pub struct Text {
    pub entries: Vec<(usize, u16)>,
}

impl Text {
    /// From the screens' answer: the window's `color`, `shadow` and `cgram`.
    pub fn of(screens: &serde_json::Value) -> Option<Text> {
        let window = screens.get("window")?;
        let cgram: Vec<u16> = window
            .get("cgram")?
            .as_array()?
            .iter()
            .map(|w| w.as_u64().unwrap_or(0) as u16)
            .collect();
        let mut indices: Vec<usize> = window
            .get("color")?
            .as_array()?
            .iter()
            .filter_map(|c| c.as_u64())
            .map(|c| c as usize)
            .collect();
        indices.push(window.get("shadow")?.as_u64()? as usize);
        indices.sort_unstable();
        indices.dedup();
        let entries = indices
            .into_iter()
            .filter(|&i| (1..COLORS_PER_PALETTE).contains(&i))
            .map(|i| (i, cgram.get(i).copied().unwrap_or(0)))
            .collect();
        Some(Text { entries })
    }

    /// The indices as a bit mask, the runtime's `LAYER_TEXT_ENTRIES`.
    pub fn mask(&self) -> u16 {
        self.entries.iter().fold(0, |m, (i, _)| m | 1 << i)
    }
}

/// The byte of `layer_texts` for a map whose layer keeps the text in its
/// own palettes: no copies.
pub const IN_PLACE: u8 = 0x80;

/// What [`bake`] did to a map.
#[derive(Debug, PartialEq, Eq)]
pub enum Baked {
    /// The layer's palettes had room: the text's colours sit at their
    /// entries, which no pixel of the layer uses. Nothing changes.
    InPlace,
    /// The text's copies, under the layer's palettes; `gave` colours of
    /// the layer sit at the text's entries and show as the text's inside
    /// the cells with letters.
    Copies { gave: usize },
    /// No room for copies: `merged` colours of the layer were merged into
    /// their nearest to leave the text's entries to the text, in the
    /// layer's own palettes.
    Merged { merged: usize },
}

/// Every map of a cartridge that shows some message without its
/// background: each one's [`Map::layer_text`], and its palettes and tiles
/// arranged. What it says goes to the converter's log.
pub fn bake_all(request: &mut Emit) -> Vec<String> {
    let mut notes = Vec::new();
    if !request.transparent_messages {
        return notes;
    }
    let Some(text) = Text::of(&request.screens) else {
        return notes;
    };
    let reserved = crate::cgram::cgram_reserved(request.window_colors) as usize;
    for map in &mut request.maps {
        match bake(map, &text, reserved) {
            Ok(Some(Baked::Copies { gave })) if gave > 0 => notes.push(format!(
                "  map {}: under a message without its background, {gave} colour(s) of the \
                 layer above give way to the text's inside the cells with letters",
                map.id
            )),
            Ok(Some(Baked::Merged { merged })) => notes.push(format!(
                "  map {}: for a message without its background, the layer above merges {merged} \
                 colour(s) to leave the text's entries to the text: its palettes have no room \
                 for them and the map none for copies",
                map.id
            )),
            Ok(_) => {}
            Err(why) => notes.push(format!(
                "  map {}: a message without its background keeps the layer above off its \
                 letters: {why}",
                map.id
            )),
        }
    }
    notes
}

/// One map: what it did, `Ok(None)` if it has no layer above to bake, or
/// `Err` with why it keeps the old look.
///
/// In this order: the text in the layer's own palettes if they have room
/// for it, which changes nothing; copies of them under them, if the
/// background leaves those palettes, which changes nothing outside the cells
/// with letters; and if neither, the layer's least visible colours merged
/// until its own palettes have the room. Never shared: an entry that is
/// the layer's and the text's at once would be tinted for both or for
/// neither —see the module—.
pub fn bake(map: &mut Map, text: &Text, reserved: usize) -> Result<Option<Baked>, String> {
    map.layer_text = 0;
    // A panorama in mode 3 is BG2 itself, and a painted map trades BG1
    // and BG2 on the window's lines: neither has a layer above there.
    if let Some(p) = &map.panorama {
        if p.mode != 1 {
            return Ok(None);
        }
    }
    let tiles = map.above_tiles.len() / TILE_BYTES;
    if tiles <= 1 {
        return Ok(None);
    }
    let palettes = map.above_cgram.len() / (2 * COLORS_PER_PALETTE);
    let first = map.above_first as usize;
    if palettes == 0 || first + palettes != BG_PALETTES {
        return Err(format!(
            "its layer's {palettes} palette(s) from {first} do not end at the last"
        ));
    }
    // The palette each tile is drawn with, from the blocks' cells of the
    // layer —a tile drawn with two would need both arrangements—, and how
    // many cells of the map draw each block, which is what a colour weighs.
    let mut palette_of: Vec<Option<usize>> = vec![None; tiles];
    let blocks: Vec<Vec<u8>> = map
        .blocks
        .chunks_exact(crate::materials::BLOCK_BYTES)
        .map(<[u8]>::to_vec)
        .collect();
    let mut uses = vec![0u64; blocks.len()];
    for cell in map.cells.chunks_exact(2) {
        let b = u16::from_le_bytes([cell[0], cell[1]]) as usize;
        if b < uses.len() {
            uses[b] += 1;
        }
    }
    let mut weight = vec![[0u64; COLORS_PER_PALETTE]; palettes];
    for (b, block) in blocks.iter().enumerate() {
        for cell in block[BLOCK_ABOVE..].chunks_exact(2) {
            let word = u16::from_le_bytes([cell[0], cell[1]]) as usize;
            let tile = word & 0x3FF;
            if tile == 0 || tile >= tiles {
                continue;
            }
            let pal = (word >> 10) & 7;
            if pal < first {
                return Err(format!("a cell of its layer is drawn with palette {pal}"));
            }
            match palette_of[tile] {
                Some(p) if p != pal - first => {
                    return Err(format!("its tile {tile} is drawn with two palettes"));
                }
                _ => palette_of[tile] = Some(pal - first),
            }
            let data = &map.above_tiles[tile * TILE_BYTES..(tile + 1) * TILE_BYTES];
            for y in 0..8 {
                for x in 0..8 {
                    weight[pal - first][pixel(data, x, y)] += uses[b].max(1);
                }
            }
        }
    }
    let room = COLORS_PER_PALETTE - 1 - text.entries.len();
    let fits = (0..palettes)
        .all(|p| used(map, &palette_of, p).iter().filter(|&&u| u).count() <= room);
    // The copies go right under the layer's palettes, where the background
    // may not reach.
    let background_end = reserved + map.cgram.len() / 2;
    let copies =
        first >= 2 * palettes && background_end <= (first - palettes) * COLORS_PER_PALETTE;
    let in_place = fits || !copies;
    let mut merged = 0;
    if !fits && !copies {
        for p in 0..palettes {
            merged += merge_down(map, &palette_of, p, &weight[p], room);
        }
    }
    let mut gave = 0;
    for p in 0..palettes {
        let used = used(map, &palette_of, p);
        let words = palette_words(map, p);
        let (to, n) = arrange(&used, &words, text);
        gave += n;
        for (t, tile) in map.above_tiles.chunks_exact_mut(TILE_BYTES).enumerate() {
            if palette_of[t] == Some(p) {
                remap(tile, &to);
            }
        }
        let mut moved = vec![0u16; COLORS_PER_PALETTE];
        for k in 0..COLORS_PER_PALETTE {
            moved[to[k]] = words[k];
        }
        // In place, the text's entries hold the text's colours: no pixel of
        // the layer uses them.
        if in_place {
            for &(i, word) in &text.entries {
                moved[i] = word;
            }
        }
        for (k, word) in moved.iter().enumerate() {
            let at = 2 * (p * COLORS_PER_PALETTE + k);
            map.above_cgram[at..at + 2].copy_from_slice(&word.to_le_bytes());
        }
    }
    if in_place {
        map.layer_text = IN_PLACE;
        Ok(Some(if fits { Baked::InPlace } else { Baked::Merged { merged } }))
    } else {
        map.layer_text = palettes as u8;
        Ok(Some(Baked::Copies { gave }))
    }
}

/// The entries palette `p` of the layer uses, 0 aside.
fn used(map: &Map, palette_of: &[Option<usize>], p: usize) -> [bool; COLORS_PER_PALETTE] {
    let mut used = [false; COLORS_PER_PALETTE];
    for (t, tile) in map.above_tiles.chunks_exact(TILE_BYTES).enumerate() {
        if palette_of[t] == Some(p) {
            for y in 0..8 {
                for x in 0..8 {
                    used[pixel(tile, x, y)] = true;
                }
            }
        }
    }
    used[0] = false;
    used
}

/// The sixteen words of palette `p` of the layer.
fn palette_words(map: &Map, p: usize) -> Vec<u16> {
    (0..COLORS_PER_PALETTE)
        .map(|k| {
            let at = 2 * (p * COLORS_PER_PALETTE + k);
            u16::from_le_bytes([map.above_cgram[at], map.above_cgram[at + 1]])
        })
        .collect()
}

/// Palette `p` of the layer down to `room` colours: the least visible one
/// —its weight times how far it is from its nearest— into its nearest, one
/// at a time, in the pixels of the tiles drawn with it. Returns how many.
fn merge_down(
    map: &mut Map,
    palette_of: &[Option<usize>],
    p: usize,
    weight: &[u64; COLORS_PER_PALETTE],
    room: usize,
) -> usize {
    let words = palette_words(map, p);
    let used = used(map, palette_of, p);
    let mut weight = *weight;
    let mut live: Vec<usize> = (1..COLORS_PER_PALETTE).filter(|&k| used[k]).collect();
    let mut to: Vec<usize> = (0..COLORS_PER_PALETTE).collect();
    let mut merged = 0;
    while live.len() > room {
        let nearest = |k: usize, live: &[usize]| {
            live.iter()
                .copied()
                .filter(|&j| j != k)
                .min_by_key(|&j| distance(words[k], words[j]))
                .expect("two colours at least")
        };
        let (_, gone, into) = live
            .iter()
            .map(|&k| {
                let j = nearest(k, &live);
                (weight[k].max(1) * u64::from(distance(words[k], words[j]).max(1)), k, j)
            })
            .min()
            .expect("more colours than room");
        for t in to.iter_mut() {
            if *t == gone {
                *t = into;
            }
        }
        weight[into] += weight[gone];
        weight[gone] = 0;
        live.retain(|&k| k != gone);
        merged += 1;
    }
    if merged > 0 {
        for (t, tile) in map.above_tiles.chunks_exact_mut(TILE_BYTES).enumerate() {
            if palette_of[t] == Some(p) {
                remap(tile, &to);
            }
        }
    }
    merged
}

/// Where each entry of a palette goes: off the text's slots if there is
/// room, and otherwise the colours nearest the text's onto them. Returns
/// the mapping, which leaves every unused entry where it is when it can,
/// and how many colours landed on a text slot.
fn arrange(used: &[bool; COLORS_PER_PALETTE], words: &[u16], text: &Text) -> (Vec<usize>, usize) {
    let is_text = |k: usize| text.entries.iter().any(|&(i, _)| i == k);
    let colours: Vec<usize> = (1..COLORS_PER_PALETTE).filter(|&k| used[k]).collect();
    let free: Vec<usize> = (1..COLORS_PER_PALETTE).filter(|&k| !is_text(k)).collect();
    let over = colours.len().saturating_sub(free.len());
    // The `over` pairs of a text slot and a colour of the layer that are
    // nearest, one at a time: those colours go to those slots.
    let mut on_text: Vec<(usize, usize)> = Vec::new();
    let mut left_colours = colours.clone();
    let mut left_slots: Vec<(usize, u16)> = text.entries.clone();
    for _ in 0..over {
        let mut best: Option<(u32, usize, usize)> = None;
        for (ci, &k) in left_colours.iter().enumerate() {
            for (si, &(_, word)) in left_slots.iter().enumerate() {
                let d = distance(words[k], word);
                if best.is_none_or(|(bd, _, _)| d < bd) {
                    best = Some((d, ci, si));
                }
            }
        }
        let (_, ci, si) = best.expect("more colours than slots means some of each");
        on_text.push((left_colours.remove(ci), left_slots.remove(si).0));
    }
    let mut to: Vec<usize> = (0..COLORS_PER_PALETTE).collect();
    for &(k, slot) in &on_text {
        to[k] = slot;
    }
    // The rest of the colours: those already off a text slot stay, and
    // those on one move to a free slot nobody keeps.
    let mut taken = [false; COLORS_PER_PALETTE];
    taken[0] = true;
    for &(_, slot) in &on_text {
        taken[slot] = true;
    }
    for &k in &left_colours {
        if !is_text(k) {
            taken[k] = true;
        }
    }
    for &k in &left_colours {
        if is_text(k) {
            let slot = free
                .iter()
                .copied()
                .find(|&s| !taken[s])
                .expect("the colours fit in the free slots");
            taken[slot] = true;
            to[k] = slot;
        }
    }
    // The unused entries fill what is left, so `to` stays a permutation.
    let mut spare = (1..COLORS_PER_PALETTE).filter(|&s| !taken[s]);
    for k in 1..COLORS_PER_PALETTE {
        if !used[k] {
            to[k] = spare.next().expect("a permutation of fifteen");
        }
    }
    (to, on_text.len())
}

/// The squared distance between two colours of fifteen bits.
fn distance(a: u16, b: u16) -> u32 {
    let channel = |w: u16, s: u16| ((w >> s) & 31) as i32;
    [0, 5, 10]
        .iter()
        .map(|&s| {
            let d = channel(a, s) - channel(b, s);
            (d * d) as u32
        })
        .sum()
}

/// Pixel (x, y) of a 4bpp tile.
fn pixel(tile: &[u8], x: usize, y: usize) -> usize {
    let bit = 7 - x;
    let b = |at: usize| ((tile[at] >> bit) & 1) as usize;
    b(2 * y) | b(2 * y + 1) << 1 | b(16 + 2 * y) << 2 | b(17 + 2 * y) << 3
}

/// Every pixel of a 4bpp tile through `to`.
fn remap(tile: &mut [u8], to: &[usize]) {
    let mut out = [0u8; TILE_BYTES];
    for y in 0..8 {
        for x in 0..8 {
            let v = to[pixel(tile, x, y)];
            let bit = 7 - x;
            out[2 * y] |= ((v & 1) as u8) << bit;
            out[2 * y + 1] |= (((v >> 1) & 1) as u8) << bit;
            out[16 + 2 * y] |= (((v >> 2) & 1) as u8) << bit;
            out[17 + 2 * y] |= (((v >> 3) & 1) as u8) << bit;
        }
    }
    tile.copy_from_slice(&out);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text() -> Text {
        Text {
            entries: vec![(2, 0x0C63), (9, 0x739C), (10, 0x77BD), (11, 0x7BDE), (12, 0x7FFF)],
        }
    }

    #[test]
    fn a_palette_with_room_moves_off_the_text() {
        let mut used = [false; 16];
        for k in 1..=9 {
            used[k] = true;
        }
        let words: Vec<u16> = (0..16).map(|k| k as u16 * 0x0421).collect();
        let (to, n) = arrange(&used, &words, &text());
        assert_eq!(n, 0);
        for k in 1..=9 {
            assert!(![2, 9, 10, 11, 12].contains(&to[k]), "{k} went to {}", to[k]);
        }
        let mut seen = to.clone();
        seen.sort_unstable();
        assert_eq!(seen, (0..16).collect::<Vec<_>>());
    }

    #[test]
    fn a_full_palette_gives_its_nearest_to_the_text() {
        let used = {
            let mut u = [true; 16];
            u[0] = false;
            u
        };
        // Greys from dark to light: the lightest four go to the text's
        // whites and the one equal to the shadow to the shadow.
        let words: Vec<u16> = (0..16).map(|k| (2 * k as u16).min(31) * 0x0421).collect();
        let (to, n) = arrange(&used, &words, &text());
        assert_eq!(n, 5);
        let on: Vec<usize> = (1..16).filter(|&k| [2, 9, 10, 11, 12].contains(&to[k])).collect();
        assert_eq!(on.len(), 5);
        assert!(on.contains(&15) && on.contains(&14), "{on:?}");
        let mut seen = to.clone();
        seen.sort_unstable();
        assert_eq!(seen, (0..16).collect::<Vec<_>>());
    }

    #[test]
    fn remapping_keeps_the_picture() {
        let mut tile = [0u8; 32];
        for (i, b) in tile.iter_mut().enumerate() {
            *b = (i * 37 % 256) as u8;
        }
        let before: Vec<usize> = (0..64).map(|i| pixel(&tile, i % 8, i / 8)).collect();
        let to: Vec<usize> = (0..16).map(|k| (k * 7) % 16).collect();
        remap(&mut tile, &to);
        let after: Vec<usize> = (0..64).map(|i| pixel(&tile, i % 8, i / 8)).collect();
        for (b, a) in before.iter().zip(&after) {
            assert_eq!(to[*b], *a);
        }
    }
}
