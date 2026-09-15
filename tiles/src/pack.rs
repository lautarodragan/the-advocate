//! The bytes the PPU reads: bit planes, not two pixels to a byte.
//!
//! Every plane holds one bit of every pixel, one row per byte, leftmost pixel
//! in the high bit. Planes go in pairs and in blocks of sixteen bytes: 0 and 1
//! first, then 2 and 3, and so on. That layout is why a 4-bit tile is exactly
//! the first half of an 8-bit one, and why the same code does both with
//! nothing but a different plane count.

use crate::color::Rgb15;
use crate::fail::{Bad, Result};
use crate::grid::{Tile, CELL};

/// A cell as palette indices.
pub type Indices = [[u8; CELL]; CELL];

/// Bytes one tile takes at a given depth.
pub fn tile_bytes(planes: usize) -> usize {
    planes * CELL
}

/// A cell as indices into its palette.
///
/// Index 0 is the transparent one, so a palette of `n` colours occupies
/// indices `base..base + n`. `base` is where the palette starts in colour
/// memory: 1 for a 4-bit tile, whose indices are counted inside its own
/// sixteen, and whatever is reserved below it for an 8-bit tile, which
/// addresses colour memory directly.
pub fn to_indices(tile: &Tile, palette: &[Rgb15], base: u8) -> Result<Indices> {
    let mut out: Indices = [[0; CELL]; CELL];
    for (y, row) in tile.iter().enumerate() {
        for (x, pixel) in row.iter().enumerate() {
            out[y][x] = match pixel {
                None => 0,
                Some(color) => match palette.iter().position(|c| c == color) {
                    Some(i) => base + i as u8,
                    None => {
                        return Err(Bad::answer(format!(
                            "the colour {},{},{} at pixel {x},{y} is not in the \
                             palette this cell was assigned",
                            color.0, color.1, color.2
                        )))
                    }
                },
            };
        }
    }
    Ok(out)
}

/// The four orientations, for reusing a mirrored tile.
///
/// In the order the flags are usually written: as it is, mirrored across x,
/// mirrored across y, both.
pub fn flips(indices: &Indices) -> [(Indices, u8, u8); 4] {
    let mut horizontal = *indices;
    for row in horizontal.iter_mut() {
        row.reverse();
    }
    let mut vertical = *indices;
    vertical.reverse();
    let mut both = horizontal;
    both.reverse();
    [
        (*indices, 0, 0),
        (horizontal, 1, 0),
        (vertical, 0, 1),
        (both, 1, 1),
    ]
}

/// Indices into the planar bytes the PPU reads.
pub fn pack_tile(indices: &Indices, planes: usize) -> Vec<u8> {
    let mut data = vec![0u8; tile_bytes(planes)];
    for (y, row) in indices.iter().enumerate() {
        for (x, value) in row.iter().enumerate() {
            let bit = 1u8 << (7 - x);
            for plane in 0..planes {
                if (value >> plane) & 1 == 1 {
                    data[(plane / 2) * 16 + y * 2 + (plane % 2)] |= bit;
                }
            }
        }
    }
    data
}

/// The planar bytes back to indices, so what was written can be looked at.
pub fn unpack_tile(data: &[u8], planes: usize) -> Indices {
    let mut out: Indices = [[0; CELL]; CELL];
    for (y, row) in out.iter_mut().enumerate() {
        for (x, value) in row.iter_mut().enumerate() {
            let bit = 1u8 << (7 - x);
            for plane in 0..planes {
                let byte = data[(plane / 2) * 16 + y * 2 + (plane % 2)];
                if byte & bit != 0 {
                    *value |= 1 << plane;
                }
            }
        }
    }
    out
}

/// One tilemap cell: `vhop ppcc cccc cccc`.
///
/// The three palette bits are meaningful at 4 bits per pixel, where an index
/// is counted inside its own sixteen. At 8 bits an index reaches all of colour
/// memory on its own and the hardware ignores them, so a caller working at
/// that depth passes 0.
pub fn entry(tile: u16, horizontal: u8, vertical: u8, priority: u8, palette: u8) -> u16 {
    tile | ((palette as u16 & 0x07) << 10)
        | ((priority as u16 & 1) << 13)
        | ((horizontal as u16 & 1) << 14)
        | ((vertical as u16 & 1) << 15)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn indices(rows: [[u8; 8]; 8]) -> Indices {
        rows
    }

    #[test]
    fn a_4bpp_tile_is_the_first_half_of_the_8bpp_one() {
        let mut t = indices([[0; 8]; 8]);
        t[0][0] = 5;
        t[3][7] = 15;
        let four = pack_tile(&t, 4);
        let eight = pack_tile(&t, 8);
        assert_eq!(four.len(), 32);
        assert_eq!(eight.len(), 64);
        assert_eq!(&eight[..32], &four[..]);
    }

    #[test]
    fn the_leftmost_pixel_is_the_high_bit_of_plane_zero() {
        let mut t = indices([[0; 8]; 8]);
        t[0][0] = 1;
        assert_eq!(pack_tile(&t, 4)[0], 0b1000_0000);
        let mut t = indices([[0; 8]; 8]);
        t[0][7] = 1;
        assert_eq!(pack_tile(&t, 4)[0], 0b0000_0001);
    }

    #[test]
    fn planes_go_in_pairs_sixteen_bytes_apart() {
        let mut t = indices([[0; 8]; 8]);
        t[0][0] = 0b0100; // plane 2 only
        let packed = pack_tile(&t, 4);
        assert_eq!(packed[16], 0b1000_0000);
        assert_eq!(packed[0], 0);
    }

    #[test]
    fn packing_and_unpacking_are_inverses() {
        let mut t = indices([[0; 8]; 8]);
        for (y, row) in t.iter_mut().enumerate() {
            for (x, value) in row.iter_mut().enumerate() {
                *value = (y * 8 + x) as u8;
            }
        }
        assert_eq!(unpack_tile(&pack_tile(&t, 8), 8), t);
    }

    #[test]
    fn the_four_flips_are_the_four_orientations() {
        let mut t = indices([[0; 8]; 8]);
        t[0][0] = 1;
        let f = flips(&t);
        assert_eq!(f[0].0[0][0], 1);
        assert_eq!((f[1].0[0][7], f[1].1, f[1].2), (1, 1, 0));
        assert_eq!((f[2].0[7][0], f[2].1, f[2].2), (1, 0, 1));
        assert_eq!((f[3].0[7][7], f[3].1, f[3].2), (1, 1, 1));
    }

    #[test]
    fn a_tilemap_entry_puts_each_flag_where_the_hardware_looks() {
        assert_eq!(entry(0x3FF, 0, 0, 0, 0), 0x03FF);
        assert_eq!(entry(0, 1, 0, 0, 0), 0x4000);
        assert_eq!(entry(0, 0, 1, 0, 0), 0x8000);
        assert_eq!(entry(0, 0, 0, 1, 0), 0x2000);
        assert_eq!(entry(0, 0, 0, 0, 7), 0x1C00);
    }

    #[test]
    fn a_colour_outside_its_palette_says_which_pixel_and_which_colour() {
        let mut tile: Tile = [[None; 8]; 8];
        tile[2][3] = Some((9, 8, 7));
        let e = to_indices(&tile, &[(1, 1, 1)], 1).unwrap_err();
        assert!(e.message().contains("9,8,7"), "{e}");
        assert!(e.message().contains("pixel 3,2"), "{e}");
    }
}
