//! Where the message window and the background meet in the lower half of
//! CGRAM, and the priorities that put each layer where RM2k draws it.

use crate::snes::Color;

/// The CGRAM entries the background **cannot** use, at the very bottom:
/// entry 0, the screen's backdrop colour, and the message window's
/// `window_colors`. The background goes at 8 bits a pixel and addresses
/// CGRAM directly, so it is enough for it to start after them: it is
/// contiguous from here up to where each map's upper layer starts. And the
/// tint, which starts at the background, leaves the window out without
/// anybody remembering it: RM2k tones the map and not the window.
///
/// `window_colors` is the game's, not the engine's: it comes out of the
/// System —its window, its arrow, its cursor and its text—, and
/// `rm2k-snes-screens window` counts it. Until 2026-10-04 it was a constant
/// here and one more in `wally`, eight and then thirteen, which is what
/// ABL's System takes.
pub fn cgram_reserved(window_colors: u32) -> u32 {
    1 + window_colors
}

/// The message window's palette: **0**, always. Its cells are emitted once
/// with the palette bits inside, so it is a single one for the whole
/// cartridge.
pub const WINDOW_PALETTE: u32 = 0;

/// The priority order of mode 3, from front to back, is
///
/// ```text
///     objects 3 / BG1 1 / objects 2 / BG2 1 / objects 1 / BG1 0 / objects 0
/// ```
///
/// which is exactly what is needed: the map in BG1 at priority 0, the hero
/// and the usual events as objects at 1, the upper layer in BG2 at 1, and
/// the events marked "above" as objects at 2. This is the BG2 cells'.
pub const PRIORITY_ABOVE: u32 = 1;

/// CGRAM colour 0, the backdrop: it shows where no layer draws. Black,
/// which is what RM2k draws where the map has nothing and beyond its edges,
/// and that shows: the screen shake reveals what is at the sides.
pub const BACKDROP: Color = [0, 0, 0];
