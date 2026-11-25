//! `rm2k-snes-cartridges`: the game's cartridges, the ones its project file
//! declares in `[cartridges]`.
//!
//!     rm2k-snes-cartridges                 builds whatever is not up to date
//!     rm2k-snes-cartridges release         only that one, with its MSU-1 tracks
//!     rm2k-snes-cartridges --force         all of them, even the ones up to date
//!     rm2k-snes-cartridges --list          which case goes in which cartridge
//!     rm2k-snes-cartridges --list --json   everything a test suite needs to know
//!     rm2k-snes-cartridges release --convert-into DIR -- --some-converter-flag
//!                                          a copy, somewhere else, with more flags
//!     rm2k-snes-cartridges space …         how much each one has left: `space`
//!     rm2k-snes-cartridges assemble …      one ROM from the runtime and the
//!                                          converter's files: `assemble`
//!
//! The subcommands go first, before any flag. They were commands of their
//! own until 2026-11-23, `rm2k-snes-space` and `rm2k-snes-assemble`: they
//! share this crate, so folding them took two commands off the PATH and
//! moved nothing between them.
//!
//! A new cartridge is one more table in `[cartridges]`, and nothing here. No
//! test builds anything: they run against what this leaves.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

mod assemble;
mod space;

use cartridge::cartridges::{Cartridges, FROM_ENVIRONMENT, RELEASE, SUBCOMMANDS};
use clap::{Arg, ArgAction, ArgMatches, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::Project;

fn command() -> Command {
    Command::new("rm2k-snes-cartridges")
        .about("The game's cartridges, the ones its project file declares in [cartridges]")
        // A cartridge called `space` or `assemble` would be taken for the
        // subcommand: `Cartridges::load` refuses one —see `SUBCOMMANDS`—.
        .subcommand(space::command())
        .subcommand(assemble::command())
        .args_conflicts_with_subcommands(true)
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where advocate.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(FROM_ENVIRONMENT))
        .arg(
            Arg::new("list")
                .long("list")
                .action(ArgAction::SetTrue)
                .help("which case goes in which cartridge, without building anything"),
        )
        .arg(
            Arg::new("json")
                .long("json")
                .action(ArgAction::SetTrue)
                .requires("list")
                .help("with --list: everything about the cartridges, as JSON —where each one is, what it carries, whether it is up to date—"),
        )
        .arg(
            Arg::new("convert_into")
                .long("convert-into")
                .value_name("DIR")
                .conflicts_with("list")
                .help("convert and assemble the one cartridge named into DIR, without a stamp and even if it is up to date; what follows `--` goes to the converter"),
        )
        .arg(
            Arg::new("force")
                .long("force")
                .action(ArgAction::SetTrue)
                .conflicts_with_all(["list", "convert_into"])
                .help("build them even if they are up to date: the RTP and the SoundFont go into the fingerprint by their path and not their content, so after changing one in place this is how the cartridges see it"),
        )
        .arg(
            Arg::new("without_tracks")
                .long("without-tracks")
                .action(ArgAction::SetTrue)
                .help("do not make the MSU-1 tracks of release"),
        )
        .arg(
            Arg::new("names")
                .value_name("CARTRIDGE")
                .num_args(0..)
                .help("only these; without names, all of them"),
        )
        .arg(
            Arg::new("extra")
                .value_name("CONVERTER_FLAGS")
                .num_args(0..)
                .last(true)
                .requires("convert_into")
                .help("with --convert-into: more flags for the converter"),
        )
}

fn run(matches: &ArgMatches) -> Result<(), String> {
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let environment = Environment::from_matches(matches, FROM_ENVIRONMENT);
    let cartridges = Cartridges::load(project, environment)?;
    let names: Vec<String> = matches
        .get_many::<String>("names")
        .map(|n| n.cloned().collect())
        .unwrap_or_default();
    for name in &names {
        if SUBCOMMANDS.contains(&name.as_str()) {
            return Err(format!(
                "`{name}` is a subcommand, and it goes first: rm2k-snes-cartridges {name} --project …"
            ));
        }
        if cartridges.get(name).is_none() {
            return Err(format!(
                "there is no cartridge '{name}': the ones there are {}",
                cartridges.names().join(", ")
            ));
        }
    }

    if matches.get_flag("list") {
        if matches.get_flag("json") {
            println!("{}", cartridges.describe()?);
            return Ok(());
        }
        for name in cartridges.names() {
            let cases = cartridges.cases(&name)?;
            println!("{name} ({}): {}", cases.len(), cases.join(" "));
        }
        return Ok(());
    }

    if let Some(dest) = matches.get_one::<String>("convert_into") {
        let [name] = names.as_slice() else {
            return Err("--convert-into takes exactly one cartridge".into());
        };
        let dest = rm2k_project::absolute(dest);
        let file = cartridges
            .rom_of(name)?
            .file_name()
            .map(PathBuf::from)
            .unwrap();
        let extra: Vec<String> = matches
            .get_many::<String>("extra")
            .map(|e| e.cloned().collect())
            .unwrap_or_default();
        return cartridges.convert(name, &dest, &dest.join(file), &extra);
    }

    let inputs = cartridges.fingerprint()?;
    let names = if names.is_empty() {
        cartridges.names()
    } else {
        names
    };
    let force = matches.get_flag("force");
    let tracks = names.iter().any(|n| n == RELEASE) && !matches.get_flag("without_tracks");
    cartridges.build_these(&names, &inputs, force, tracks)
}

fn main() -> ExitCode {
    let matches = command().get_matches();
    let done = match matches.subcommand() {
        Some(("assemble", sub)) => return assemble::run(sub),
        Some(("space", sub)) => space::run(sub),
        _ => run(&matches),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}
