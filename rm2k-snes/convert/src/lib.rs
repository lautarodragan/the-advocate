//! The converter: an rm2k-snes game into the data a Super Nintendo
//! cartridge carries.
//!
//! It is the conversion's orchestrator. Every domain is a stage of its own
//! —a library it is compiled with, called as a function, that reads the
//! game from the dump itself and answers a request: the maps (`wally`),
//! the event compiler, the screens,
//! the pictures, the battle, the emission, the patches, the music—, and
//! this asks each one, in order, what the cartridge needs, handing each
//! the decisions it cannot make and what the others answered. What it
//! decides itself is what joins them: which maps and test pages the
//! cartridge carries, who can lead the party, which items and actors it
//! needs, where the timer runs, which pictures, animations, backdrops and
//! battlers go in, and the checks the compiled pages have to pass.

//!
//! **A library, and the cartridges' builder calls it** —[`convert`]—, with
//! flags, which are what the project file writes for each cartridge: the
//! ones the binary `rm2k-snes-convert` took until 2026-11-27. Until
//! 2026-11-25 the builder ran that binary once per cartridge; what the
//! process gave on its own and a call
//! does not —its own stdout, which was the cartridge's `converter.log`, and
//! state that lived as long as one conversion— is now the conversion's: see
//! `rm2k_project::log` and [`stage`]'s cache.

mod animations;
mod bytecode;
mod chipsets;
mod common_pages;
mod common_pictures;
mod compiler;
pub mod convert;
mod degradations;
mod emit;
pub mod fail;
mod font;
mod fork;
mod fullscreen;
mod game;
mod images;
mod letters;
mod map_pictures;
mod maps;
mod msu_missing;
pub mod options;
mod pictures;
mod reach;
mod resources;
mod scan;
mod scene;
mod screens;
mod settings;
pub mod stage;
mod systems;
mod text;
mod trim;
mod variants;

use rm2k_project::log::Log;

/// One conversion, with `argv` —its flags, without a program's name—:
/// everything it says goes into `log` instead of stdout and stderr. What
/// it answers no to is the [`fail::Stop`] the caller prints last, as the
/// binary did until 2026-11-27 before exiting with its code.
pub fn convert(argv: Vec<String>, log: &Log) -> fail::Result<()> {
    log.during(|| options::parse(argv).and_then(convert::run))
}
