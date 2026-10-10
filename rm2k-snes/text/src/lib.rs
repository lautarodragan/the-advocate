//! Text on an rm2k-snes console's screens: the letters, a line of them
//! drawn over an RPG Maker 2000 game's System, and a message box reflowed
//! for a window narrower than RM2k's.
//!
//! * [`font`]: a font as a sheet drawn by hand —the engine carries one, of
//!   variable width; a game may bring its own— or easyrpg-player's two 6x12
//!   ones, RM2k's, and which of those the game's `font_id` asks for.
//! * [`line`]: a line of text in one of the System's colours, with its
//!   shadow, as RM2k's `Font::Render` draws it.
//! * [`refit`]: a `ShowMessage` box spread over as many boxes of `rows`
//!   lines measured in pixels as it needs, with its speaker and its escape
//!   tail.
//!
//! It knows nothing about menus, nor about which screen a line lands on:
//! whoever draws a screen decides that.
//!
//! The tests make their boxes and their System inside the test, and compare
//! against the hashes of what the Python that did this until 2026-09-30
//! gave for the same input: they need no game.

pub mod cells;
pub mod font;
mod glyphs;
pub mod line;
pub mod refit;
