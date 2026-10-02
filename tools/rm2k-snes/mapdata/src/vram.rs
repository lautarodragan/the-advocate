//! How the 64 KB of VRAM are laid out: the tilemap window, the six layouts
//! a map can get, the save slots screen, and the checks that every layout
//! respects the hardware and what the console assumes of it.
//!
//! The input is how many tiles each layer spends; the output, which layout
//! the map gets. The console chooses nothing: the layout travels in the
//! `.inc`. It is the converter's contract with the runtime, and the maps,
//! the screens and the emission read it from here: `rm2k-snes-mapdata vram`
//! publishes it.

use crate::fail::{Bad, Result};
use crate::snes::BYTES_PER_TILE;

// --- the tilemap window ------------------------------------------------------
// The PPU's tilemap does not go beyond 64x64 cells, and VRAM has to be shared
// with the tiles, so the window left for it is 64x32: 512x256 pixels against
// the 256x224 of the screen. A game's maps can be far bigger, so the whole
// map is never in VRAM: the console keeps redrawing the column and the row
// that come in while the camera moves, from a table of 16x16 blocks.
pub const WINDOW_W: u32 = 64;
pub const WINDOW_H: u32 = 32;
/// Two 32x32 screens side by side, which is 64x32.
pub const MAP_LAYOUT: u32 = 1;

/// Where a piece of a layout starts, in words, and how many tiles it holds
/// —one for the tilemaps, which hold a single map—.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Piece {
    pub base: u32,
    pub count: u32,
}

const fn piece(base: u32, count: u32) -> Piece {
    Piece { base, count }
}

/// A VRAM layout, by its pieces.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Layout {
    /// What the `.inc` and the runtime's comments call it.
    pub name: &'static str,
    /// The sprites' 4bpp tiles: the OBJ base.
    pub sprites: Piece,
    /// The background's 8bpp tiles: the BG1 base.
    pub tiles: Piece,
    /// The background's tilemap.
    pub map: Piece,
    /// The upper layer's 4bpp tiles: the BG2 base.
    pub above: Piece,
    /// The message window's tiles, behind the upper layer's in BG2.
    pub window: Piece,
    /// The message window's own 32x32 tilemap.
    pub window_map: Piece,
}

impl Layout {
    /// The pieces by the names the converter's Python knew them by.
    pub fn pieces(&self) -> [(&'static str, Piece); 6] {
        [
            ("sprites", self.sprites),
            ("tiles", self.tiles),
            ("map", self.map),
            ("above", self.above),
            ("window", self.window),
            ("window_map", self.window_map),
        ]
    }
}

// --- the layouts -------------------------------------------------------------
// The 64 KB cannot be split any way one likes: the base of the sprite tiles
// goes in steps of 16 KB, that of each background in steps of 8 KB and that
// of each tilemap in steps of 2 KB.
//
// Every map carries the message window, which needs 8 KB of its own tiles
// —the text is 240 tiles and there is no way to lower that, because a 6 px
// glyph does not align to 8-pixel cells and it is composed pixel by pixel—
// plus 2 KB of its own tilemap. What makes the tiles possible is that the
// upper layer and the window end up adjacent: BG2 has a single base and its
// tile indices are 10 bits, so the window is the upper layer's next bank.
//
// The upper layer gets 128 tiles in five of the six: measured over the maps
// of A Blurred Line, the median use is one tile.
//
// **New ones are added at the end**, never in the middle: `vram_layout`
// returns the first one that fits, so a new layout does not change any
// map's. The numbers each one was made for were measured against A Blurred
// Line; the reasons are in the runtime's comments and in the git log of
// the converter's Python `vram.py`, where they lived until 2026-10-01.

/// The usual one.
///
/// ```text
///   sprites     $0000  14 KB  448 4bpp tiles      OBJ base at 0
///   window_map  $1C00   2 KB  the window's 32x32 tilemap
///   tiles       $2000  28 KB  448 8bpp tiles
///   map         $5800   4 KB
///   above       $6000   4 KB  128 tiles           <- the BG2 base
///   window      $6800   8 KB  256 tiles           <- indices 128..383
///   (the upper tilemap at $7800)
/// ```
pub const LAYOUT_WINDOW: Layout = Layout {
    name: "VENTANA",
    sprites: piece(0x0000, 448),
    window_map: piece(0x1C00, 1),
    tiles: piece(0x2000, 448),
    map: piece(0x5800, 1),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
};

/// Sprite tiles traded for background tiles, for the maps that spend more
/// background: 480 instead of 448, with 256 sprite tiles.
pub const LAYOUT_WINDOW_BG: Layout = Layout {
    name: "VENTANA_FONDO",
    sprites: piece(0x0000, 256),
    tiles: piece(0x1000, 480),
    window_map: piece(0x4C00, 1),
    map: piece(0x5800, 1),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
};

/// The opposite: background tiles traded for sprite tiles. 512 is the
/// hardware's cap and not a choice: the OAM name field is nine bits, and
/// with `OBSEL`'s name select at zero both tables end up adjacent. The 2 KB
/// free at $5400 are the price of the alignment.
pub const LAYOUT_WINDOW_SPRITE: Layout = Layout {
    name: "VENTANA_SPRITE",
    sprites: piece(0x0000, 512),
    tiles: piece(0x2000, 384),
    window_map: piece(0x5000, 1),
    map: piece(0x5800, 1),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
};

/// The only one that **moves the background's tilemap**, down to the 2 KB
/// left between the sprites and the background. The tilemap moving is paid
/// for by `build_column` and `build_row`, which add `FAR_VRAM_MAP`, and by
/// `push_strips`, which masks eleven bits to step to the upper layer: that
/// is why both tilemap bases are multiples of 2048 words, and the map's
/// cannot be zero —`col_addr` at zero means "no column"—.
pub const LAYOUT_WINDOW_BOTH: Layout = Layout {
    name: "VENTANA_AMBOS",
    sprites: piece(0x0000, 384),
    map: piece(0x1800, 1),
    tiles: piece(0x2000, 480),
    window_map: piece(0x5C00, 1),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
};

/// The ceiling of the background with 256 sprite tiles: 544. That is
/// 34 KB, more than the LZ2 buffer, which is why a background goes in two
/// streams.
pub const LAYOUT_WINDOW_BG_CEILING: Layout = Layout {
    name: "VENTANA_FONDO_TECHO",
    sprites: piece(0x0000, 256),
    tiles: piece(0x1000, 544),
    window_map: piece(0x5400, 1),
    map: piece(0x5800, 1),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
};

/// The only one that **moves the BG2 base**, to give the upper layer 256
/// tiles. The window starts then at index 256 and not 128, and its cells
/// carry that index baked in: that is why there are two layouts of the
/// window's cells —see [`WINDOW_BASES`]—.
pub const LAYOUT_WINDOW_ABOVE: Layout = Layout {
    name: "VENTANA_ENCIMA",
    sprites: piece(0x0000, 384),
    map: piece(0x1800, 1),
    tiles: piece(0x2000, 384),
    above: piece(0x5000, 256),
    window: piece(0x6000, 256),
    window_map: piece(0x7000, 1),
};

/// In the order `vram_layout` tries them.
pub const LAYOUTS: [Layout; 6] = [
    LAYOUT_WINDOW,
    LAYOUT_WINDOW_BG,
    LAYOUT_WINDOW_SPRITE,
    LAYOUT_WINDOW_BOTH,
    LAYOUT_WINDOW_BG_CEILING,
    LAYOUT_WINDOW_ABOVE,
];

/// How many save slots the cartridge has. The same number is in the
/// runtime's `save_game.s` as `SRAM_SLOTS`, and the console checks it.
pub const SLOTS: u32 = 4;

/// Where the slots screen's tiles live, in words. It is opened with a map
/// loaded, and closing it has to restore what it overwrote: that is cheap
/// only if it overwrote the BG1 tile bank, which `load_map` uploads whole
/// again. These fall in the BG1 bank of every layout —the screens check it—.
pub const SLOT_VRAM: u32 = 0x2000;
/// And its tilemap.
pub const SLOT_MAP: u32 = 0x3C00;
/// The row of `slot_actor_text`: an actor's name, the two digits of the
/// level and max HP, one after the other. A power of two even if bytes are
/// left over, so that the actor's index comes out of five `asl`.
pub const SLOT_TEXT_WIDTH: u32 = 32;
/// The name fits in thirteen, and three are left over.
pub const SLOT_TEXT_LEVEL: u32 = 16;

/// The upper layer's tilemap is fixed: the background's is chosen by the
/// layout —see [`LAYOUT_WINDOW_BOTH`]—.
pub const VRAM_ABOVE_MAP: u32 = 0x7800;

/// The BG2 index of the window's first tile in a layout: where the
/// window's bank starts counted from the BG2 base.
pub fn window_base(layout: &Layout) -> u32 {
    (layout.window.base - layout.above.base) / 16
}

/// The bases the layouts use, in the order of their cells in the `.inc`:
/// the first one's is `window_cells` and the second's `window_cells_256`.
/// The console picks between the two by the distance between the window
/// and the BG2 base, so there cannot be a third without touching
/// `stamp_window`; [`check_splits`] enforces it.
pub const WINDOW_BASES: [u32; 2] = [
    (LAYOUT_WINDOW.window.base - LAYOUT_WINDOW.above.base) / 16,
    256,
];

/// Which VRAM layout a map gets, according to what it spends: the first
/// one where the three numbers fit.
pub fn vram_layout(tiles: u32, sprites: u32, above: u32) -> Result<&'static Layout> {
    LAYOUTS
        .iter()
        .find(|l| tiles <= l.tiles.count && sprites <= l.sprites.count && above <= l.above.count)
        .ok_or_else(|| {
            Bad::answer(format!(
                "this map can't carry a message window: it spends {tiles} background tiles, \
                 {sprites} sprite tiles and {above} upper tiles, and there is no layout that \
                 leaves 8 KB of tiles plus 2 KB of tilemap for the window"
            ))
        })
}

/// That each layout respects the hardware and what the console assumes of
/// it. None of this depends on the map.
pub fn check_splits() -> Result<()> {
    for layout in &LAYOUTS {
        let name = layout.name;
        // In words: what each thing takes, and the step its base goes in.
        // The sprite and upper-layer tiles are 4bpp, 16 words.
        let pieces = [
            ("sprites", layout.sprites.count * 16, 0x2000),
            (
                "tiles",
                layout.tiles.count * (BYTES_PER_TILE as u32 / 2),
                0x1000,
            ),
            ("encima", layout.above.count * 16, 0x1000),
            ("ventana", layout.window.count * 16, 1),
            ("ventana_map", 32 * 32, 0x400),
            // 2048 and not 1024, which is what `BG1SC` asks for:
            // `push_strips` steps to the upper layer by masking eleven bits.
            ("mapa", WINDOW_W * WINDOW_H, 0x800),
        ];
        let base_of = |piece: &str| match piece {
            "sprites" => layout.sprites.base,
            "tiles" => layout.tiles.base,
            "encima" => layout.above.base,
            "ventana" => layout.window.base,
            "ventana_map" => layout.window_map.base,
            _ => layout.map.base,
        };
        let mut stretches = vec![(
            "upper map",
            VRAM_ABOVE_MAP,
            VRAM_ABOVE_MAP + WINDOW_W * WINDOW_H,
        )];
        for (piece, length, step) in pieces {
            let base = base_of(piece);
            if base % step != 0 {
                return Err(Bad::answer(format!(
                    "LAYOUT_{name}: {piece} at ${base:04X}, and its base goes in steps of ${step:X} \
                     words"
                )));
            }
            stretches.push((piece, base, base + length));
        }
        if layout.map.base == 0 {
            return Err(Bad::answer(format!(
                "LAYOUT_{name}: the tilemap at $0000, and `col_addr` at zero means there is no \
                 column"
            )));
        }
        let first = window_base(layout);
        if !WINDOW_BASES.contains(&first) {
            return Err(Bad::answer(format!(
                "LAYOUT_{name}: the window starts at BG2 tile {first}, and there are layouts for \
                 ({}, {}): see WINDOW_BASES",
                WINDOW_BASES[0], WINDOW_BASES[1]
            )));
        }
        // And the window has to land inside what BG2 reaches from its base:
        // the tilemap index is ten bits.
        if first + layout.window.count > 1024 {
            return Err(Bad::answer(format!(
                "LAYOUT_{name}: the window goes past BG2 index 1023"
            )));
        }
        stretches.sort_by_key(|s| s.1);
        for pair in stretches.windows(2) {
            let ((a, _, end), (b, start, _)) = (pair[0], pair[1]);
            if end > start {
                return Err(Bad::answer(format!(
                    "LAYOUT_{name}: {a} ends at ${end:04X} and {b} starts at ${start:04X}"
                )));
            }
        }
        let last = stretches[stretches.len() - 1];
        if last.2 > 0x8000 {
            return Err(Bad::answer(format!(
                "LAYOUT_{name}: {} goes past VRAM",
                last.0
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_layouts_respect_the_hardware() {
        check_splits().unwrap();
    }

    /// `vram_layout` returns the first that fits: that is what allows adding
    /// a layout at the end without moving any map.
    #[test]
    fn each_map_takes_the_first_layout_it_fits() {
        for background in (0..545).step_by(16) {
            for sprites in (0..513).step_by(16) {
                let fitting: Vec<&Layout> = LAYOUTS
                    .iter()
                    .filter(|l| background <= l.tiles.count && sprites <= l.sprites.count)
                    .collect();
                if let Some(first) = fitting.first() {
                    assert_eq!(vram_layout(background, sprites, 0).unwrap(), *first);
                }
            }
        }
    }

    #[test]
    fn a_new_layout_goes_at_the_end() {
        let names: Vec<&str> = LAYOUTS.iter().map(|l| l.name).collect();
        assert_eq!(
            names,
            [
                "VENTANA",
                "VENTANA_FONDO",
                "VENTANA_SPRITE",
                "VENTANA_AMBOS",
                "VENTANA_FONDO_TECHO",
                "VENTANA_ENCIMA"
            ]
        );
    }

    /// The maps each one was made for, measured on A Blurred Line.
    #[test]
    fn the_maps_that_asked_for_a_layout_get_it() {
        assert_eq!(vram_layout(476, 347, 0).unwrap(), &LAYOUT_WINDOW_BOTH);
        assert_ne!(LAYOUT_WINDOW_BOTH.map.base, LAYOUT_WINDOW.map.base);
        assert_eq!(vram_layout(527, 222, 0).unwrap(), &LAYOUT_WINDOW_BG_CEILING);
        assert_eq!(vram_layout(544, 256, 0).unwrap(), &LAYOUT_WINDOW_BG_CEILING);
        assert_eq!(vram_layout(329, 283, 157).unwrap(), &LAYOUT_WINDOW_ABOVE);
        assert_eq!(vram_layout(329, 283, 0).unwrap(), &LAYOUT_WINDOW);
    }

    #[test]
    fn the_window_bases_are_those_of_the_layouts() {
        let mut bases: Vec<u32> = LAYOUTS.iter().map(window_base).collect();
        bases.sort();
        bases.dedup();
        assert_eq!(bases, WINDOW_BASES);
    }

    #[test]
    fn a_map_that_fits_nowhere_is_refused() {
        assert_eq!(
            vram_layout(600, 0, 0).unwrap_err().message(),
            "this map can't carry a message window: it spends 600 background tiles, 0 sprite \
             tiles and 0 upper tiles, and there is no layout that leaves 8 KB of tiles plus 2 KB \
             of tilemap for the window"
        );
    }
}
