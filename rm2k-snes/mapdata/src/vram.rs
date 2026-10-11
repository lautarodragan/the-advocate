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
    /// Where a panorama goes, in the layouts made for one: see
    /// [`LAYOUT_PANORAMA_MODE3`] and [`LAYOUT_PANORAMA_MODE1`]. `None` in
    /// the others, which are the only ones [`vram_layout`] gives.
    pub panorama: Option<PanoramaPieces>,
}

/// What [`PanoramaPieces::count`] says of a painted map: no limit.
pub const PAINTED_ANY: u32 = 0xFFFF;

/// Where a layout puts a panorama.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PanoramaPieces {
    /// The mode the map goes in: 3, the panorama in BG2 at 4 bits, or 1,
    /// in BG3 at 2 bits.
    pub mode: u8,
    /// Its tiles: up to two stretches, numbered one after the other from
    /// the layer's base. The second has no tiles if there is one.
    pub tiles: [Piece; 2],
    /// Its 64x32 tilemap, which the console fills as a ring while it
    /// scrolls.
    pub map: u32,
}

impl PanoramaPieces {
    /// How many tiles it holds. A painted map's are any number: the
    /// cartridge carries them all and VRAM only the ones on screen.
    pub fn count(&self) -> u32 {
        if self.mode == 4 {
            return PAINTED_ANY;
        }
        self.tiles[0].count + self.tiles[1].count
    }

    /// Words a tile takes at its depth.
    pub fn tile_words(&self) -> u32 {
        if self.mode == 3 {
            16
        } else {
            8
        }
    }

    /// The tilemap's tile number for its `k`-th tile: the second stretch
    /// is numbered from where it lands, counted from the layer's base.
    pub fn number(&self, k: u32, base: u32) -> u32 {
        if k < self.tiles[0].count {
            (self.tiles[0].base - base) / self.tile_words() + k
        } else {
            (self.tiles[1].base - base) / self.tile_words() + k - self.tiles[0].count
        }
    }
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
    panorama: None,
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
    panorama: None,
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
    panorama: None,
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
    panorama: None,
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
    panorama: None,
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
    panorama: None,
};

/// A map that shows its panorama in mode 3: BG2 is the panorama, at 4
/// bits, and the map draws nothing above the hero. The panorama takes
/// what BG2 reaches around the window, which the window has to keep
/// —at BG2 index 256, from $5000 up, where a big picture does not step on
/// it—, and its tilemap is the upper layer's, at $7800, which the map
/// does not use: the console does not upload the upper layer's strips
/// there.
///
/// ```text
///   sprites     $0000  12 KB  384 4bpp tiles      OBJ base at 0
///   map         $1800   4 KB  the background's tilemap
///   tiles       $2000  16 KB  256 8bpp tiles
///   panorama    $4000   8 KB  256 4bpp tiles      <- the BG2 base
///   window      $5000   8 KB  256 tiles           <- indices 256..511
///   window_map  $6000   2 KB
///   panorama    $6400  10 KB  320 4bpp tiles      <- indices 576..895
///   (its tilemap at $7800)
/// ```
pub const LAYOUT_PANORAMA_MODE3: Layout = Layout {
    name: "VENTANA_PANORAMA",
    sprites: piece(0x0000, 384),
    map: piece(0x1800, 1),
    tiles: piece(0x2000, 256),
    // The upper layer is one blank tile: what `load_above` uploads before
    // the panorama.
    above: piece(0x4000, 1),
    window: piece(0x5000, 256),
    window_map: piece(0x6000, 1),
    panorama: Some(PanoramaPieces {
        mode: 3,
        tiles: [piece(0x4000, 256), piece(0x6400, 320)],
        map: VRAM_ABOVE_MAP,
    }),
};

/// A map that shows its panorama and draws something above the hero: mode
/// 1. BG1 is the map at 4 bits —its count here is in 64-byte units, like
/// the 8-bit ones', so 256 are 512 tiles—, BG2 the upper layer and the
/// window as in [`LAYOUT_WINDOW`], and BG3 the panorama at 2 bits.
///
/// ```text
///   sprites     $0000   8 KB  256 4bpp tiles      OBJ base at 0
///   map         $1000   4 KB
///   window_map  $1800   2 KB
///   tiles       $2000  16 KB  512 4bpp tiles
///   panorama    $4000  12 KB  768 2bpp tiles      <- the BG3 base
///   (its tilemap at $5800)
///   above       $6000   4 KB  128 tiles           <- the BG2 base
///   window      $6800   8 KB  256 tiles
///   (the upper tilemap at $7800)
/// ```
pub const LAYOUT_PANORAMA_MODE1: Layout = Layout {
    name: "VENTANA_PANORAMA_M1",
    sprites: piece(0x0000, 256),
    map: piece(0x1000, 1),
    window_map: piece(0x1800, 1),
    tiles: piece(0x2000, 256),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
    panorama: Some(PanoramaPieces {
        mode: 1,
        tiles: [piece(0x4000, 768), piece(0x5800, 0)],
        map: 0x5800,
    }),
};

/// [`LAYOUT_PANORAMA_MODE3`] with panorama tiles traded for background
/// tiles, for the bigger maps: 384 of each 8-bit, and 320 of panorama. The
/// window keeps BG2's 256 to 511, so the window's tilemap goes after it.
///
/// ```text
///   sprites     $0000  12 KB  384 4bpp tiles      OBJ base at 0
///   map         $1800   4 KB  the background's tilemap
///   tiles       $2000  24 KB  384 8bpp tiles
///   panorama    $5000   8 KB  256 4bpp tiles      <- the BG2 base
///   window      $6000   8 KB  256 tiles           <- indices 256..511
///   window_map  $7000   2 KB
///   panorama    $7400   2 KB   64 4bpp tiles      <- indices 576..639
///   (its tilemap at $7800)
/// ```
pub const LAYOUT_PANORAMA_MODE3_BG: Layout = Layout {
    name: "VENTANA_PANORAMA_FONDO",
    sprites: piece(0x0000, 384),
    map: piece(0x1800, 1),
    tiles: piece(0x2000, 384),
    above: piece(0x5000, 1),
    window: piece(0x6000, 256),
    window_map: piece(0x7000, 1),
    panorama: Some(PanoramaPieces {
        mode: 3,
        tiles: [piece(0x5000, 256), piece(0x7400, 64)],
        map: VRAM_ABOVE_MAP,
    }),
};

/// The same with sprite tiles traded for panorama tiles: 256 sprites and
/// 384 of panorama, for a big map whose panorama does not hold in 320.
///
/// ```text
///   sprites     $0000   8 KB  256 4bpp tiles      OBJ base at 0
///   map         $1000   4 KB  the background's tilemap
///   window_map  $1800   2 KB
///   tiles       $2000  24 KB  384 8bpp tiles
///   panorama    $5000   8 KB  256 4bpp tiles      <- the BG2 base
///   window      $6000   8 KB  256 tiles           <- indices 256..511
///   panorama    $7000   4 KB  128 4bpp tiles      <- indices 512..639
///   (its tilemap at $7800)
/// ```
pub const LAYOUT_PANORAMA_MODE3_BG_SPRITE: Layout = Layout {
    name: "VENTANA_PANORAMA_FONDO_SPRITE",
    sprites: piece(0x0000, 256),
    map: piece(0x1000, 1),
    window_map: piece(0x1800, 1),
    tiles: piece(0x2000, 384),
    above: piece(0x5000, 1),
    window: piece(0x6000, 256),
    panorama: Some(PanoramaPieces {
        mode: 3,
        tiles: [piece(0x5000, 256), piece(0x7000, 128)],
        map: VRAM_ABOVE_MAP,
    }),
};

/// The ceiling of the background with a panorama in mode 3: 448 8-bit
/// tiles, which go past BG2's base. BG2's first 128 tiles are the
/// background's, and nothing in BG2 names them: the window is at 128, as in
/// [`LAYOUT_WINDOW`], and the panorama after it. That is why `load_above`
/// uploads nothing to BG2's base in a map whose panorama goes in mode 3.
///
/// ```text
///   sprites     $0000   8 KB  256 4bpp tiles      OBJ base at 0
///   map         $1000   4 KB  the background's tilemap
///   window_map  $1800   2 KB
///   tiles       $2000  28 KB  448 8bpp tiles      (BG2's base at $5000)
///   window      $5800   8 KB  256 tiles           <- indices 128..383
///   panorama    $6800   8 KB  256 4bpp tiles      <- indices 384..639
///   (its tilemap at $7800)
/// ```
pub const LAYOUT_PANORAMA_MODE3_BG_CEILING: Layout = Layout {
    name: "VENTANA_PANORAMA_FONDO_TECHO",
    sprites: piece(0x0000, 256),
    map: piece(0x1000, 1),
    window_map: piece(0x1800, 1),
    tiles: piece(0x2000, 448),
    above: piece(0x5000, 1),
    window: piece(0x5800, 256),
    panorama: Some(PanoramaPieces {
        mode: 3,
        tiles: [piece(0x6800, 256), piece(0x7800, 0)],
        map: VRAM_ABOVE_MAP,
    }),
};

/// The slots a painted map keeps in VRAM: one per cell the screen can show
/// at once, and a row more. The screen is 256x224, so with the scroll
/// halfway through a cell it shows 33 columns and 29 rows; cell (x, y) goes
/// in slot `(y mod 30) + 30 * (x mod 33)`, so that no two cells on screen
/// share one and a column is one run. The row more is the one the console
/// uploads ahead, a few tiles a frame, because a row is 33 DMAs. See
/// `runtime/painted.s`.
pub const PAINTED_COLUMNS: u32 = 33;
pub const PAINTED_ROWS: u32 = 30;
pub const PAINTED_SLOTS: u32 = PAINTED_COLUMNS * PAINTED_ROWS;
/// The blank tile right after them, which the tilemap names where there is
/// no map: past its edges, or a map smaller than the screen.
pub const PAINTED_BLANK: u32 = PAINTED_SLOTS;

/// A painted map —see `Way::Painted` in Wally—: mode 1, and BG1 is the
/// whole map as a painting, its slots uploaded as they come into view. Its
/// "tiles" are the slots, counted in 64-byte units like the 8-bit ones', and
/// its tilemap is the map's moving window; BG2 is the layer above and the
/// window as in [`LAYOUT_WINDOW`].
///
/// ```text
///   sprites     $0000   8 KB  256 4bpp tiles      OBJ base at 0
///   tiles       $1000  32 KB  990 4bpp slots and the blank one   <- BG1
///   map         $5000   4 KB  the painting's 64x32 tilemap
///   window_map  $5800   2 KB
///   (free)      $5C00   2 KB
///   above       $6000   4 KB  128 tiles           <- the BG2 base
///   window      $6800   8 KB  256 tiles
///   (the upper tilemap at $7800)
/// ```
pub const LAYOUT_PAINTED: Layout = Layout {
    name: "VENTANA_PINTADA",
    sprites: piece(0x0000, 256),
    // Up to the tilemap, past the blank one: the screens that open over the
    // map write BG1 up to $4C00 —the actor choice— and count on the load to
    // put it back, which `paint_load` does.
    tiles: piece(0x1000, 512),
    map: piece(0x5000, 1),
    window_map: piece(0x5800, 1),
    above: piece(0x6000, 128),
    window: piece(0x6800, 256),
    panorama: Some(PanoramaPieces {
        mode: 4,
        tiles: [piece(0x1000, PAINTED_SLOTS), piece(0x1000, 0)],
        map: 0x5000,
    }),
};

/// In the order `vram_layout` tries them, and then the panorama's, which
/// it never gives: a map gets one of those only by showing its panorama,
/// and the first of its mode it fits in —[`panorama_layout`]—.
pub const LAYOUTS: [Layout; 12] = [
    LAYOUT_WINDOW,
    LAYOUT_WINDOW_BG,
    LAYOUT_WINDOW_SPRITE,
    LAYOUT_WINDOW_BOTH,
    LAYOUT_WINDOW_BG_CEILING,
    LAYOUT_WINDOW_ABOVE,
    LAYOUT_PANORAMA_MODE3,
    LAYOUT_PANORAMA_MODE1,
    LAYOUT_PANORAMA_MODE3_BG,
    LAYOUT_PANORAMA_MODE3_BG_SPRITE,
    LAYOUT_PANORAMA_MODE3_BG_CEILING,
    LAYOUT_PAINTED,
];

/// The layouts for a map that shows its panorama in `mode`, in the order
/// they are tried.
pub fn panorama_layouts(mode: u8) -> impl Iterator<Item = &'static Layout> {
    LAYOUTS.iter().filter(move |l| l.panorama.is_some_and(|p| p.mode == mode))
}

/// The layout of a map that shows its panorama in `mode`: the first that
/// holds its background, sprite, upper and panorama tiles.
pub fn panorama_layout(mode: u8, background: u32, sprites: u32, above: u32, panorama: u32) -> Result<&'static Layout> {
    panorama_layouts(mode)
        .find(|l| {
            background <= l.tiles.count
                && sprites <= l.sprites.count
                && above <= l.above.count.max(1)
                && l.panorama.is_some_and(|p| panorama <= p.count())
        })
        .ok_or_else(|| {
            Bad::answer(format!(
                "there is no layout for a panorama in mode {mode} that holds {background} background tiles, \
                 {sprites} sprite tiles, {above} upper tiles and {panorama} panorama tiles"
            ))
        })
}

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
        .filter(|l| l.panorama.is_none())
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
            // In the mode-3 panorama layout the upper layer is the
            // panorama's blank tile 0, and counted there.
            (
                "encima",
                if layout.panorama.is_some_and(|p| p.mode == 3) {
                    0
                } else {
                    layout.above.count * 16
                },
                0x1000,
            ),
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
        if let Some(p) = layout.panorama.filter(|p| p.mode == 4) {
            // A painted map: its slots are the tiles piece, and its tilemap
            // the map's; both are checked as any layout's. The slots and the
            // blank one have to fit in it, under BG1's ten bits.
            if p.tiles[0].base != layout.tiles.base
                || p.map != layout.map.base
                || (PAINTED_SLOTS + 1) * 16 > layout.tiles.count * (BYTES_PER_TILE as u32 / 2)
                || PAINTED_BLANK >= 1024
            {
                return Err(Bad::answer(format!(
                    "LAYOUT_{name}: the painting's slots are not its tiles and its tilemap the map's"
                )));
            }
        } else if let Some(p) = &layout.panorama {
            for piece in p.tiles.iter().filter(|t| t.count > 0) {
                stretches.push(("panorama", piece.base, piece.base + piece.count * p.tile_words()));
            }
            if p.map != VRAM_ABOVE_MAP {
                stretches.push(("panorama map", p.map, p.map + WINDOW_W * WINDOW_H));
            }
            // A panorama in mode 3 is BG2, and its tiles have to land where
            // BG2's ten bits reach; in mode 1 it is BG3's, from its base.
            let base = if p.mode == 3 { layout.above.base } else { p.tiles[0].base };
            let last = p.number(p.count() - 1, base);
            if base % 0x1000 != 0 || p.tiles[0].base < base || last >= 1024 {
                return Err(Bad::answer(format!(
                    "LAYOUT_{name}: the panorama's tiles go past what its layer reaches"
                )));
            }
        }
        for (piece, length, step) in pieces {
            let base = base_of(piece);
            if base % step != 0 {
                return Err(Bad::answer(format!(
                    "LAYOUT_{name}: {piece} at ${base:04X}, and its base goes in steps of ${step:X} \
                     words"
                )));
            }
            if length > 0 {
                stretches.push((piece, base, base + length));
            }
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
                    .filter(|l| l.panorama.is_none())
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
                "VENTANA_ENCIMA",
                "VENTANA_PANORAMA",
                "VENTANA_PANORAMA_M1",
                "VENTANA_PANORAMA_FONDO",
                "VENTANA_PANORAMA_FONDO_SPRITE",
                "VENTANA_PANORAMA_FONDO_TECHO",
                "VENTANA_PINTADA"
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

    /// The mode-3 panorama's second stretch is numbered from where it
    /// lands: after the window, which is BG2's 256 to 511, and its tilemap.
    #[test]
    fn the_panorama_tiles_are_numbered_from_where_they_land() {
        let p = LAYOUT_PANORAMA_MODE3.panorama.unwrap();
        assert_eq!(p.number(0, 0x4000), 0);
        assert_eq!(p.number(255, 0x4000), 255);
        assert_eq!(p.number(256, 0x4000), 576);
        assert_eq!(p.number(575, 0x4000), 895);
        assert_eq!(panorama_layout(1, 256, 256, 1, 768).unwrap().name, "VENTANA_PANORAMA_M1");
        assert_eq!(panorama_layout(3, 300, 300, 0, 500).unwrap_err().message().is_empty(), false);
        assert_eq!(panorama_layout(3, 300, 300, 0, 320).unwrap().name, "VENTANA_PANORAMA_FONDO");
        assert_eq!(panorama_layout(3, 300, 300, 0, 384).unwrap_err().message().is_empty(), false);
        assert_eq!(panorama_layout(3, 300, 200, 0, 384).unwrap().name, "VENTANA_PANORAMA_FONDO_SPRITE");
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
