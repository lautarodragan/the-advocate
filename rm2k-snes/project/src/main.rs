//! `rm2k-snes-project`: a project as the tools resolve it, in JSON.
//!
//!     rm2k-snes-project [--project DIRECTORY]
//!     rm2k-snes-project --game-dir GAME.zip --unpacked game_dir
//!     rm2k-snes-project --harness
//!
//! What it prints, and why it is asked and not read, is in `resolved.rs`.
//!
//! With `--unpacked`, only the directory a machine value is read from: the
//! same one if it is a directory, and its unpacked copy if it is a `.zip`
//! —see `Environment::unpack`—. It is for whoever reads the game or the RTP
//! and is not a tool of the suite: a game's tests, Ditto in its recipes.
//!
//! With `--harness`, only the directory of the tests' generic harness —see
//! `suite::harness`—, and with no project: it is what a game's tests put on
//! their import path before anything else, and the tests of several games
//! at once have no one project to name.

use std::path::Path;
use std::process::ExitCode;

use clap::{Arg, Command};
use rm2k_project::environment::{arguments, Environment, PACKABLE};
use rm2k_project::{resolved, Error, Project};

fn command() -> Command {
    Command::new("rm2k-snes-project")
        .about("Prints a project as the tools resolve it, in JSON: its paths, the suite's own, and its settings")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where advocate.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .arg(
            Arg::new("harness")
                .long("harness")
                .action(clap::ArgAction::SetTrue)
                .conflicts_with_all(["project", "unpacked"])
                .help("print only the directory of the tests' generic harness, the Python package rm2k_snes_harness, for the import path; it needs no project"),
        )
        .args(arguments(PACKABLE))
        .arg(
            Arg::new("unpacked")
                .long("unpacked")
                .value_name("NAME")
                .value_parser(PACKABLE.to_vec())
                .help("print only the directory that machine value is read from, unpacking it into the project's cache if it is a .zip"),
        )
}

fn run() -> Result<(), Error> {
    let matches = command().get_matches();
    if matches.get_flag("harness") {
        println!("{}", rm2k_project::suite::harness().display());
        return Ok(());
    }
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    if let Some(name) = matches.get_one::<String>("unpacked") {
        let mut environment = Environment::from_matches(&matches, PACKABLE);
        environment.unpack(&project)?;
        let directory = match name.as_str() {
            "game_dir" => environment.game()?,
            _ => environment.rtp()?,
        };
        println!("{}", directory.display());
        return Ok(());
    }
    let out = resolved(&project)?;
    println!(
        "{}",
        serde_json::to_string_pretty(&out).expect("a JSON value always serializes")
    );
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("rm2k-snes-project: {error}");
            ExitCode::FAILURE
        }
    }
}
