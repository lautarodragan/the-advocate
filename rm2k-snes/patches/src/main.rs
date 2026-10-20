//! `rm2k-snes-patches`: what the converter decided to lose, written down,
//! versioned and checked. See the library for what a patch is.
//!
//!     rm2k-snes-patches --request decisions.json BUILD
//!                                  the converter: one build's patches
//!     rm2k-snes-patches BUILD      the playable ROM's, to the project
//!     rm2k-snes-patches --check [BUILD…]
//!                                  fail if what is versioned is stale
//!
//! A BUILD is a cartridge's build directory, or a directory with cartridges
//! inside. Exit code 1 when the answer is no, 2 when the call is wrong.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use cartridge::cartridges::Cartridges;
use clap::{Arg, ArgAction, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::{relative, Project};
use rm2k_snes_patches::{check, copy, has_patches, versioned, write, Kind, Request, PLAYABLE};

const FROM_ENVIRONMENT: &[&str] = &["test_cartridges"];

fn command() -> Command {
    Command::new("rm2k-snes-patches")
        .about("What the converter decides to lose when taking the game to the SNES: written, versioned and checked")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where advocate.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(FROM_ENVIRONMENT))
        .arg(
            Arg::new("builds")
                .value_name("BUILDS")
                .num_args(0..)
                .help("the directories of the built cartridges. Without --check it has to be the playable ROM's and nothing else: what is versioned is what `release` decides. With --check and none given, those of all the cartridges `rm2k-snes-cartridges --list` gives"),
        )
        .arg(
            Arg::new("check")
                .long("check")
                .action(ArgAction::SetTrue)
                .help("do not write: fail if what is versioned is stale"),
        )
        .arg(
            Arg::new("request")
                .long("request")
                .value_name("FILE")
                .conflicts_with("check")
                .help("what the converter decided for one build, as JSON: write its patches into the one build directory given, next to its ROM. This is how the converter leaves them"),
        )
}

fn run() -> Result<(), String> {
    let matches = command().get_matches();
    let given: Vec<String> = matches
        .get_many::<String>("builds")
        .map(|b| b.cloned().collect())
        .unwrap_or_default();

    // The converter's call needs no project: it only writes into the build
    // what it was handed.
    if let Some(request) = matches.get_one::<String>("request") {
        let [build] = given.as_slice() else {
            return Err(format!(
                "--request writes one build's patches: pass its directory, and not {}",
                given.len()
            ));
        };
        let text = std::fs::read_to_string(request).map_err(|e| format!("{request}: {e}"))?;
        let request: Request =
            serde_json::from_str(&text).map_err(|e| format!("{request}: {e}"))?;
        for w in write(Path::new(build), &request)? {
            println!(
                "patches of {} {} -> {} ({} B)",
                w.files,
                w.kind.plural(),
                w.kind.in_build(),
                w.bytes
            );
        }
        return Ok(());
    }

    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let auto = project.auto_patches()?;
    // The maps that only exist for the suite: the project file declares them,
    // and the cartridge builder puts them into the cartridges.
    let tests: BTreeSet<i64> = project.ints(&["maps", "test"])?.into_iter().collect();
    let check_only = matches.get_flag("check");
    let listed: Vec<String> = if given.is_empty() && check_only {
        // Where each cartridge is built is said by the one that builds them.
        let environment = Environment::from_matches(&matches, FROM_ENVIRONMENT);
        let cartridges = Cartridges::load(project.clone(), environment)?;
        cartridges
            .names()
            .iter()
            .map(|name| cartridges.directory(name).map(|d| d.display().to_string()))
            .collect::<Result<_, _>>()?
    } else {
        given
    };
    let mut builds: Vec<PathBuf> = Vec::new();
    for build in &listed {
        let build = PathBuf::from(build);
        if has_patches(&build) {
            builds.push(build);
            continue;
        }
        let mut inside: Vec<String> = std::fs::read_dir(&build)
            .map_err(|e| format!("{}: {e}", build.display()))?
            .filter_map(|e| e.ok()?.file_name().into_string().ok())
            .collect();
        inside.sort();
        builds.extend(
            inside
                .into_iter()
                .map(|n| build.join(n))
                .filter(|b| has_patches(b)),
        );
    }
    if builds.is_empty() {
        return Err(format!(
            "found no built cartridge with patches inside: {}",
            listed.join(", ")
        ));
    }
    let here = std::env::current_dir().map_err(|e| format!("the current directory: {e}"))?;

    if check_only {
        let checked = check(&auto, &builds, &tests, &here)?;
        for complaint in &checked.complaints {
            eprintln!("  {complaint}");
        }
        if !checked.complaints.is_empty() {
            return Err(format!(
                "{} patch(es) do not match what the converter decides",
                checked.complaints.len()
            ));
        }
        for kind in Kind::ALL {
            println!(
                "the game's {} patch(es) of {} match what {} cartridge(s) decided",
                versioned(&auto, kind)?.len(),
                kind.plural(),
                builds.len()
            );
            if let Some(mine) = checked.own.get(&kind) {
                // It is not a complaint: they are situations the playable ROM
                // does not have, so the test cartridge decided on its own and
                // that is not versioned. It is printed because it says how
                // much the suite resembles the game.
                let keys: Vec<String> = mine.keys().map(|k| k.to_string()).collect();
                println!(
                    "  and {} that only exist for the suite, which decide on their own: {}",
                    mine.len(),
                    keys.join(", ")
                );
            }
        }
        return Ok(());
    }

    let [build] = builds.as_slice() else {
        return Err(format!(
            "what is versioned is what **one** ROM decides, the playable one: pass \
             the build directory of `{PLAYABLE}` and not {} cartridges",
            builds.len()
        ));
    };
    for kind in Kind::ALL {
        let (count, bytes, removed) = copy(&auto, build, kind, &tests)?;
        for path in removed {
            println!(
                "  {}: the game no longer carries it, removing it",
                relative(&path, &here).display()
            );
        }
        println!(
            "{count} patch(es) in {}, {bytes} B",
            relative(auto.join(kind.directory()), &here).display()
        );
    }
    Ok(())
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
