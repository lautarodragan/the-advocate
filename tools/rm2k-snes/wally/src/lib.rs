//! An RPG Maker 2000 game's maps, as a Super Nintendo cartridge carries
//! them.
//!
//! It is one stage of a converter —see "One stage of a converter" in
//! `rm2k-snes/battle/README.md`—: it reads the game from a Ditto dump
//! ([`game`]), gets what the cartridge decided in a request ([`request`]),
//! and writes what it made into a directory. It makes a whole map ([`map`]):
//! its two background layers ([`layers`]), the events baked into them
//! ([`baking`]), its characters as objects, and its blocks.
//!
//! The work is two modules' that do not know each other: [`background`]
//! takes the lower half of colour memory and the background layers,
//! [`sprites`] the upper half and the objects —`tests/halves.rs` keeps
//! them apart—. What needs both halves at once —baking an event, which takes a
//! sprite into a layer— is this crate's, and so is reading the map's events
//! ([`events`]), who among them moves ([`moves`]), and drawing the sheets its characters are cut from
//! ([`sheets`]).

pub mod background;
pub mod baking;
pub mod events;
pub mod fail;
pub mod game;
pub mod inspect;
pub mod layers;
pub mod map;
pub mod moves;
pub mod request;
pub mod sheets;
pub mod sprites;
pub mod substitutions;

pub use fail::{Bad, Result};
pub use game::Game;
pub use request::LayersRequest;
