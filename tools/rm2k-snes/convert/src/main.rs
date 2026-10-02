//! `rm2k-snes-convert`: an rm2k-snes game into the data a Super Nintendo
//! cartridge carries.
//!
//! It is the conversion's orchestrator. Every domain is a stage of its own
//! —a program on the PATH that reads the game from the dump itself and
//! answers a request: the maps (`wally`), the event compiler, the screens,
//! the pictures, the battle, the emission, the patches, the music—, and
//! this asks each one, in order, what the cartridge needs, handing each
//! the decisions it cannot make and what the others answered. What it
//! decides itself is what joins them: which maps and test pages the
//! cartridge carries, who can lead the party, which items and actors it
//! needs, where the timer runs, which pictures, animations, backdrops and
//! battlers go in, and the checks the compiled pages have to pass.

mod animations;
mod bytecode;
mod chipsets;
mod compiler;
mod convert;
mod emit;
mod fail;
mod fork;
mod fullscreen;
mod game;
mod images;
mod maps;
mod options;
mod pictures;
mod pyjson;
mod queries;
mod resources;
mod scan;
mod scene;
mod screens;
mod settings;
mod stage;
mod text;

use std::io::Write;
use std::process::ExitCode;

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    // A question a game's test asks goes by its word, first; anything else
    // is a conversion.
    let done = if argv.first().is_some_and(|a| queries::QUERIES.contains(&a.as_str())) {
        queries::run(argv)
    } else {
        options::parse(argv).and_then(convert::run)
    };
    let _ = std::io::stdout().flush();
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(stop) => {
            eprintln!("{}", stop.message);
            ExitCode::from(stop.code)
        }
    }
}
