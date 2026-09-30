//! An RPG Maker 2000 game's maps, as a Super Nintendo cartridge carries
//! them.
//!
//! It is one stage of a converter —see "One stage of a converter" in
//! `rm2k-snes/battle/README.md`—: it reads the game from a Ditto dump
//! ([`game`]), gets what the cartridge decided in a request ([`request`]),
//! and writes what it made into a directory. Today it makes a map's two
//! background layers ([`layers`]); the rest of the map comes here as it
//! moves.
//!
//! The work is two libraries' that do not know each other:
//! `rm2k-snes-map-background` takes the lower half of colour memory and
//! the background layers. What needs both halves at once is this crate's.

pub mod fail;
pub mod game;
pub mod layers;
pub mod request;

pub use fail::{Bad, Result};
pub use game::Game;
pub use request::LayersRequest;
