//! `rm2k-snes-space`: how much space each cartridge has left. It prints it
//! and does not write it down.
//!
//!     rm2k-snes-space                  every cartridge
//!     rm2k-snes-space release          only that one
//!     rm2k-snes-space DIR/game.sfc     a ROM built separately
//!     rm2k-snes-space --json …         the same, as JSON
//!
//! Everything comes from what the build left next to the ROM, so it neither
//! relinks nor assembles anything; a cartridge that is not up to date is
//! refused. See `space` in the library for what each number is.
//!
//! It takes the same machine flags as `rm2k-snes-cartridges`, because it
//! asks the same question: the fingerprint reads the original game
//! —`--game-dir`— and the RTP's and the SoundFont's paths. Only a built ROM
//! passed by its path needs none of them.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use cartridge::cartridges::{Cartridges, FROM_ENVIRONMENT};
use cartridge::space;
use clap::{Arg, ArgAction, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::{absolute, relative, suite, Project};
use serde_json::json;

fn command() -> Command {
    Command::new("rm2k-snes-space")
        .about("How much space each cartridge has left: it prints it and does not write it down")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where rm2k-snes.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(FROM_ENVIRONMENT))
        .arg(
            Arg::new("json")
                .long("json")
                .action(ArgAction::SetTrue)
                .help("print the numbers as JSON, one object per cartridge or ROM"),
        )
        .arg(
            Arg::new("which_ones")
                .value_name("CARTRIDGE")
                .num_args(0..)
                .help("a cartridge of the project or the path of a built ROM; with nothing, every cartridge"),
        )
}

fn run() -> Result<(), String> {
    let matches = command().get_matches();
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let environment = Environment::from_matches(&matches, FROM_ENVIRONMENT);
    let cartridges = Cartridges::load(project, environment)?;
    let which_ones: Vec<String> = match matches.get_many::<String>("which_ones") {
        Some(names) => names.cloned().collect(),
        None => cartridges.names(),
    };
    let mut inputs = None;
    let mut report = serde_json::Map::new();
    let mut first = true;
    for which in which_ones {
        let sfc: PathBuf = if cartridges.get(&which).is_some() {
            if inputs.is_none() {
                inputs = Some(cartridges.fingerprint()?);
            }
            if let Some(reason) = cartridges.stale(&which, inputs.as_ref().unwrap())? {
                return Err(format!(
                    "{which}: {reason}; rm2k-snes-cartridges builds it first"
                ));
            }
            cartridges.rom_of(&which)?
        } else if Path::new(&which).is_file() {
            absolute(&which)
        } else {
            return Err(format!(
                "'{which}' is neither a cartridge ({}) nor a built ROM",
                cartridges.names().join(", ")
            ));
        };
        let m = space::measure(&sfc, &suite::runtime())?;
        if matches.get_flag("json") {
            report.insert(
                which.clone(),
                json!({
                    "rom": sfc,
                    "banks": m.banks,
                    "used": m.used,
                    "slow": m.slow,
                    "free": m.free,
                    "free_fast": m.free_fast,
                    "free_halves": m.free_halves,
                    "gaps": m.gaps,
                    "largest_gap": m.largest_gap,
                    "bank0": m.bank0,
                    "bank1": m.bank1,
                    "bank_far2": m.bank_far2,
                    "bank_far3": m.bank_far3,
                    "bss": m.bss,
                    "far": m.far,
                    "switches": m.switches,
                    "zeropage": m.zeropage,
                    "texts": m.texts,
                    "texts_cap": m.texts_cap,
                }),
            );
            continue;
        }
        if !first {
            println!();
        }
        first = false;
        // A ROM built separately is named by its path; a cartridge, by its
        // name.
        let title = if Path::new(&which).is_file() {
            which.clone()
        } else {
            format!("{which}  ({})", relative(&sfc, suite::root()).display())
        };
        print!("{}", space::show(&title, &m));
    }
    if matches.get_flag("json") {
        println!("{}", serde_json::Value::Object(report));
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
