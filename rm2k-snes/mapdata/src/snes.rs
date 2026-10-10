//! The formats of the console's PPU: a tile, a CGRAM colour and a tilemap
//! cell, as bytes or words ready for it.

/// An 8bpp tile: 8 bit planes of 8 rows.
pub const BYTES_PER_TILE: usize = 64;
/// What each 4bpp palette takes in CGRAM.
pub const COLORS_PER_PALETTE: usize = 16;

/// A colour at five bits a channel.
pub type Color = [u8; 3];

/// A tile in the PPU's format: bitplanes, not pixels.
///
/// Each plane holds one bit of each pixel, one row per byte, with the
/// leftmost pixel in the highest bit. Planes come in pairs, sixteen bytes a
/// pair: 0 and 1 first, then 2 and 3, and so on. That is why a 4bpp tile is
/// exactly the first half of an 8bpp one.
pub fn pack_tile(indices: &[Vec<u8>], planes: usize) -> Vec<u8> {
    let mut data = vec![0u8; planes * 8];
    for (y, row) in indices.iter().enumerate() {
        for (x, &value) in row.iter().enumerate() {
            let bit = 1u8 << (7 - x);
            for plane in 0..planes {
                if (value >> plane) & 1 != 0 {
                    data[(plane / 2) * 16 + y * 2 + (plane % 2)] |= bit;
                }
            }
        }
    }
    data
}

/// A CGRAM word: `0BBBBBGG GGGRRRRR`.
pub fn cgram_word(color: Color) -> u16 {
    let [red, green, blue] = color;
    (u16::from(blue) << 10) | (u16::from(green) << 5) | u16::from(red)
}

/// A tilemap cell: `vhopppcc cccccccc`.
///
/// The palette bits are not set here: at 8 bits a pixel the index already
/// reaches all of CGRAM and the PPU ignores them, and a 4bpp cell that
/// carries one already has it in `tile`.
pub fn entry(tile: u32, horizontal: bool, vertical: bool, priority: u32) -> u32 {
    tile | (priority << 13) | (u32::from(horizontal) << 14) | (u32::from(vertical) << 15)
}

/// Little-endian words, as bytes.
pub fn words_le<I: IntoIterator<Item = u32>>(words: I) -> Vec<u8> {
    let mut out = Vec::new();
    for w in words {
        out.push((w & 0xFF) as u8);
        out.push(((w >> 8) & 0xFF) as u8);
    }
    out
}

/// Colours as CGRAM words, as bytes.
pub fn cgram_bytes<'a, I: IntoIterator<Item = &'a Color>>(colors: I) -> Vec<u8> {
    words_le(colors.into_iter().map(|&c| u32::from(cgram_word(c))))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_tile_goes_in_planes_by_pairs() {
        let mut cell = vec![vec![0u8; 8]; 8];
        cell[0][0] = 0b0000_0101;
        cell[7][7] = 0b1000_0000;
        let tile = pack_tile(&cell, 8);
        assert_eq!(tile[0], 0x80, "plane 0, row 0");
        assert_eq!(tile[16], 0x80, "plane 2, row 0");
        assert_eq!(tile[48 + 14 + 1], 0x01, "plane 7, row 7");
        assert_eq!(pack_tile(&cell, 4), tile[..32]);
    }

    #[test]
    fn the_cgram_word_puts_blue_on_top() {
        assert_eq!(cgram_word([31, 0, 0]), 0x001F);
        assert_eq!(cgram_word([0, 0, 31]), 0x7C00);
    }

    #[test]
    fn a_cell_carries_priority_and_flips_above_its_tile() {
        assert_eq!(entry(5, false, false, 1), 0x2005);
        assert_eq!(entry(5, true, true, 0), 0xC005);
    }
}
