//! `rm2k-snes-cartridges`: the game's cartridges, the ones its project file
//! declares in `[cartridges]`.
//!
//!     rm2k-snes-cartridges                 builds whatever is not up to date
//!     rm2k-snes-cartridges release         only that one, with its MSU-1 tracks
//!     rm2k-snes-cartridges --list          which case goes in which cartridge
//!     rm2k-snes-cartridges --list --json   everything a test suite needs to know
//!     rm2k-snes-cartridges release --convert-into DIR -- --some-converter-flag
//!                                          a copy, somewhere else, with more flags
//!
//! A new cartridge is one more table in `[cartridges]`, and nothing here. No
//! test builds anything: they run against what this leaves.

use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::mpsc;

use cartridge::cartridges::{Cartridges, FROM_ENVIRONMENT, RELEASE};
use clap::{Arg, ArgAction, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::Project;

fn command() -> Command {
    Command::new("rm2k-snes-cartridges")
        .about("The game's cartridges, the ones its project file declares in [cartridges]")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where rm2k-snes.toml is. Without this, it is looked up from the current directory upwards"),
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

fn run() -> Result<(), String> {
    let matches = command().get_matches();
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let environment = Environment::from_matches(&matches, FROM_ENVIRONMENT);
    let cartridges = Cartridges::load(project, environment)?;
    let names: Vec<String> = matches
        .get_many::<String>("names")
        .map(|n| n.cloned().collect())
        .unwrap_or_default();
    for name in &names {
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
    let tracks = names.iter().any(|n| n == RELEASE) && !matches.get_flag("without_tracks");
    // The cartridges and the tracks are built at the same time, in threads:
    // each one writes in its own directory, and the heavy work runs in the
    // tools this runs. What they share is the disk cache, which writes aside
    // and renames. What is printed stays in the usual order.
    //
    // The tracks, **after `release`** and not alongside it: they are its
    // songs', which the converter leaves next to its ROM. Meanwhile the other
    // cartridges get built.
    std::thread::scope(|scope| {
        let (release_built, release_done) = mpsc::channel();
        let handles: Vec<_> = names
            .iter()
            .map(|name| {
                let cartridges = &cartridges;
                let inputs = &inputs;
                let sender = (name == RELEASE).then(|| release_built.clone());
                scope.spawn(move || {
                    let built = cartridges.build(name, inputs);
                    let Some(sender) = sender else {
                        return Outcome { built: Some(built), tracks: None };
                    };
                    // `release` says it is built before its tracks start.
                    let ok = built.is_ok();
                    let _ = sender.send(built);
                    Outcome {
                        built: None,
                        tracks: (ok && tracks).then(|| cartridges.msu_tracks()),
                    }
                })
            })
            .collect();
        drop(release_built);
        // The scope waits for the builds still running before it returns, so
        // a failure does not leave a converter half-way through a directory.
        for (name, handle) in names.iter().zip(handles) {
            if name == RELEASE {
                let built = release_done
                    .recv()
                    .unwrap_or_else(|_| Err(format!("{RELEASE}: the build did not finish")))?;
                println!("{name}: {}", if built { "built" } else { "up to date" });
            }
            let outcome = handle.join().expect("a build thread panicked");
            if let Some(built) = outcome.built {
                println!("{name}: {}", if built? { "built" } else { "up to date" });
            }
            if let Some(line) = outcome.tracks {
                println!("{}", line?);
            }
        }
        Ok(())
    })
}

/// What a build thread leaves: whether it built —`release` says that
/// through a channel instead, earlier— and the tracks' line.
struct Outcome {
    built: Option<Result<bool, String>>,
    tracks: Option<Result<String, String>>,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}
