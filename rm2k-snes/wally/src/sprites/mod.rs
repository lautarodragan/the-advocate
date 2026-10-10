//! An RPG Maker 2000 map's characters, as Super Nintendo objects.
//!
//! What a map's events and its hero are drawn with —CharSet sheets, already
//! drawn— goes to the upper half of colour memory and the object bank:
//!
//! * [`character`]: a character's colours at 15 bits over the poses it can
//!   show, its palette of fifteen, and its poses as 32x32 objects;
//! * [`npc`]: the events that are drawn, and which poses each graphic can
//!   end up showing;
//! * [`split`]: how the eight object palettes are split among the
//!   characters, and which events drawn with a tile fit;
//! * [`bank`]: the VRAM bank, one pose per slot, and the cartridge's bank
//!   of the twelve poses of whoever changes pose;
//! * [`share`]: the still ones that take turns in a slot because they are
//!   never on screen together;
//! * [`cache`]: the slots nobody owns, for a map that does not fit even
//!   with those turns;
//! * [`extras`]: the timer's digits, the raindrops, a picture and the
//!   battle animation's box, at the end of the bank.
//!
//! It knows nothing of the background layers, which get the lower half of
//! colour memory, and nothing of which game the map is from.

pub mod bank;
pub mod cache;
pub mod character;
pub mod extras;
pub mod fail;
pub mod npc;
pub mod share;
pub mod split;

pub use fail::{Bad, Result};
