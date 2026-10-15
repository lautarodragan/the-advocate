//! An rm2k-snes game's screens as a cartridge carries them: the message
//! window and its font, the title's menu, the save slots and the pause
//! menu, the text screens —items, equipment, shop, the actor choice— with
//! their windows, and End Game.
//!
//! It reads the game itself, from a Ditto dump and the game's folder; what
//! the cartridge decided —which actors, which items, how many slots, where
//! the maps' layouts put BG1— comes in a request. What comes out is data,
//! not code: tiles, tilemaps, palettes, the texts the cartridge composes,
//! and the geometry they were drawn with.
//!
//! * [`convert`]: everything a cartridge carries, in one answer.
//! * [`render`]: a screen as the console has to show it, built from the
//!   same blocks the cartridge uploads, for whoever compares against a
//!   capture.
//! * [`boxes`]: every message box of the game reflowed for the console's
//!   window.

pub mod battle;
pub mod borders;
pub mod boxes;
pub mod cells;
pub mod checks;
pub mod convert;
pub mod custom_menu;
pub mod end_game;
pub mod fail;
pub mod fit;
pub mod game;
pub mod items;
pub mod layout;
pub mod message_window;
pub mod party;
pub mod render;
pub mod request;
pub mod skills;
pub mod slots;
pub mod texts;
pub mod title;

pub use fail::{Bad, Result};
pub use game::Game;
