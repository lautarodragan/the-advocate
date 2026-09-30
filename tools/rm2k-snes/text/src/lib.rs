//! Text on an rm2k-snes console's screens: the letters, a line of them
//! drawn over an RPG Maker 2000 game's System, and a message box reflowed
//! for a window narrower than RM2k's.
//!
//! * [`font`]: easyrpg-player's two 6x12 fonts, and which one the game's
//!   `font_id` asks for.
//! * [`line`]: a line of text in one of the System's colours, with its
//!   shadow, as RM2k's `Font::Render` draws it.
//! * [`refit`]: a `ShowMessage` box spread over as many boxes of `columns`
//!   by `rows` as it needs, with its speaker and its escape tail.
//!
//! It knows nothing about menus, nor about which screen a line lands on:
//! whoever draws a screen decides that.

pub mod font;
mod glyphs;
pub mod line;
pub mod refit;
