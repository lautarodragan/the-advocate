//! `advocate`: builds an rm2k-snes game, the one whose `advocate.toml` is
//! found from the current directory upwards or named with `--project`.
//!
//!     advocate build                  every cartridge that is not up to date
//!     advocate build release          only that one, with its MSU-1 tracks
//!     advocate build --force          all of them, even the ones up to date
//!     advocate build --list           which case goes in which cartridge
//!     advocate build release --into DIR -- --some-converter-flag
//!                                     a copy, somewhere else, with more flags
//!
//! **One program, and it runs no other of ours**: the converter, its
//! stages, the bank packing, the assembler and the MSU-1 tracks are
//! libraries it calls. What it still runs is not ours: `ca65` and `ld65`,
//! and the tracks' synthesizer and encoder. See the book's decision "One
//! command, and no tool of ours runs another".
//!
//! **Every build leaves `build/advocate.json`**, also when nothing had to be
//! rebuilt and when a cartridge failed: everything a game's tests and
//! recipes need to know about the project, its cartridges and the machine
//! it was built with, so they read a file instead of running a tool. What
//! it holds, in `file.rs`.
//!
//! Until 2026-11-25 building was `rm2k-snes-cartridges`, which ran
//! `rm2k-snes-convert` per cartridge; and what is now the file the tests
//! asked `rm2k-snes-cartridges --list --json`, `space --json`, `assemble
//! --memory-map` and `--sources`, and `rm2k-snes-project`.

use std::process::ExitCode;

use clap::Command;

mod build;
mod file;
mod patches;

fn command() -> Command {
    Command::new("advocate")
        .about("Builds an rm2k-snes game from its advocate.toml")
        .subcommand_required(true)
        .arg_required_else_help(true)
        .subcommand(build::command())
}

fn main() -> ExitCode {
    let matches = command().get_matches();
    let done = match matches.subcommand() {
        Some(("build", sub)) => build::run(sub),
        _ => unreachable!("clap requires a subcommand"),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}
