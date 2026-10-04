//! The System: the picture every window is drawn from —its background, its
//! frame and its cursor—, and the colours of the text and the timer's
//! digits.
//!
//! It is 160x80, and each piece has its place:
//!
//! ```text
//! (0, 0)    32x32  the background, stretched or tiled to the window
//! (32, 0)   32x32  the frame: 8x8 corners, and 16-pixel edges between them
//! (64, 0)   32x32  the cursor, first drawing: laid out like the frame, and
//!                  its 16x16 middle fills the inside
//! (96, 0)   32x32  the cursor, second drawing; it blinks between the two
//! (40, 8)   16x8   inside the frame's square, the arrow that says there
//!                  is more above
//! (40, 16)  16x8   and the one that says there is more below, which is
//!                  also the message's "press a key"
//! (16, 32)  16x16  the text's shadow colour
//! (32, 32)  88x16  the timer: the ten digits and the colon, 8x16 each
//! (0, 48)   16x16  text colour 0, and the other nineteen to its right and
//!                  below, ten per row
//! ```
//!
//! easyrpg's `Window::RefreshBackground`, `RefreshFrame` and
//! `RefreshCursor`, `Font::Render` and `Sprite_Timer`.

use ditto::schema::SystemStretch;

/// What the System measures.
pub const SYSTEM_WIDTH: i32 = 160;
pub const SYSTEM_HEIGHT: i32 = 80;

/// The background, the frame and the two cursor drawings are each a 32x32
/// square.
pub const PIECE: i32 = 32;
/// The background's square.
pub const BACKGROUND: (i32, i32) = (0, 0);
/// The frame's square.
pub const FRAME: (i32, i32) = (32, 0);
/// The cursor's two drawings: drawing `n` starts at `CURSOR[n]`.
pub const CURSOR: [(i32, i32); 2] = [(64, 0), (96, 0)];
/// A corner of the frame or of the cursor, and how thick their edges are.
pub const EDGE: i32 = 8;

/// The arrow pointing down, `ARROW_WIDTH` x `ARROW_HEIGHT`: a list that
/// goes on below, and a message waiting for a key —easyrpg's `Window::Draw`
/// draws it for `pause` too, at the bottom edge and centred—. The one
/// pointing up is the same size, right above it.
pub const ARROW_DOWN: (i32, i32) = (40, 16);
pub const ARROW_WIDTH: i32 = 16;
pub const ARROW_HEIGHT: i32 = 8;

/// A text colour, and the shadow's, is a 16x16 block and not a colour: a
/// letter takes, pixel by pixel, the block's pixel at the same place.
pub const COLOR_BLOCK: i32 = 16;
/// The shadow's block.
pub const SHADOW: (i32, i32) = (16, 32);
/// How many text colours there are.
pub const TEXT_COLORS: i32 = 20;

/// Where the block of text colour `number`, 0 to 19, starts.
pub fn text_color_origin(number: i32) -> (i32, i32) {
    (number % 10 * COLOR_BLOCK, number / 10 * COLOR_BLOCK + 48)
}

/// The timer: `TIMER_GLYPHS` glyphs of `TIMER_GLYPH_WIDTH` x
/// `TIMER_GLYPH_HEIGHT` in a row from `TIMER`, the digits 0 to 9 and then
/// the colon.
pub const TIMER: (i32, i32) = (32, 32);
pub const TIMER_GLYPHS: i32 = 11;
pub const TIMER_GLYPH_WIDTH: i32 = 8;
pub const TIMER_GLYPH_HEIGHT: i32 = 16;

/// How a window's background fills it: the database's `message_stretch`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Background {
    /// The square scaled to the window, which is the default.
    Stretched,
    /// The square repeated from the window's corner.
    Tiled,
}

/// What `message_stretch` says, or `None` for a value RM2k does not have:
/// the third one, `easyrpg_none`, is EasyRPG's own.
pub fn background(stretch: SystemStretch) -> Option<Background> {
    match stretch {
        SystemStretch::Stretch => Some(Background::Stretched),
        SystemStretch::Tiled => Some(Background::Tiled),
        _ => None,
    }
}
