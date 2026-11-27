//! The music's one job a person or a recipe runs on its own:
//! `volume-ceilings`, each song's headroom measured in the built ROM.
//!
//! What a cartridge's music is the converter asks the library for, as a
//! function —`stage::cartridge`—, and what a game's tests read of it the
//! build leaves beside the ROM. Until 2026-11-27 this binary also answered
//! the tests' questions —`compile`, `keys`, `decode`, `msu-index`,
//! `msu-sign`, `wav`, `find-song`, `pitch` and `constants`—, which went
//! when nothing called them any more.

use clap::Command;
use std::io::Write as _;
use std::process::ExitCode;

/// The subcommands written with clap's builder, like the flags of the
/// machine they take —`arguments` in `rm2k-project`—.
mod commands {
    pub mod volume_ceilings;
}

fn main() -> ExitCode {
    let matches = Command::new("rm2k-snes-audio")
        .about(
            "An rm2k-snes game's music: what is measured of it in the built ROM. The music \
             itself is compiled by the converter, which calls this crate as a library",
        )
        .version(env!("CARGO_PKG_VERSION"))
        .subcommand_required(true)
        .arg_required_else_help(true)
        .subcommand(commands::volume_ceilings::command())
        .get_matches();
    let done = match matches.subcommand() {
        Some(("volume-ceilings", sub)) => commands::volume_ceilings::run(sub),
        _ => unreachable!("clap requires a subcommand, and there is one"),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            let _ = std::io::stdout().flush();
            eprintln!("rm2k-snes-audio volume-ceilings: {bad}");
            ExitCode::FAILURE
        }
    }
}
