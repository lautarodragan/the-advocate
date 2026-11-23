//! `rm2k-snes-cartridges assemble`: builds a ROM from the runtime and a
//! directory of generated data.
//!
//!     rm2k-snes-cartridges assemble runtime/main.s -I build/game \
//!         -o build/game/game.sfc --symbols build/game/game.sfc.sym
//!
//! It writes the bytecodes' equates next to the generated files, packs those
//! into banks —rewriting them in place—, writes the memory map next to
//! them, runs `ca65` and `ld65`, writes the header checksum and, with
//! `--symbols`, the symbol table. See the library.
//!
//! The cartridges' builder runs it as a process of its own, by its name on
//! the PATH, which is the binary the fingerprint hashes. Until 2026-11-23 it
//! was a command of its own, `rm2k-snes-assemble`.

use std::path::PathBuf;
use std::process::ExitCode;

use cartridge::assemble::{self, Failure};
use cartridge::banks;
use clap::{Arg, ArgAction, ArgMatches, Command};
use rm2k_project::{cache, environment, suite};
use serde_json::json;

pub fn command() -> Command {
    Command::new("assemble")
        .about("Builds the ROM: the bank packing, ca65 + ld65, the header checksum and the symbols")
        .arg(Arg::new("source").value_name("SOURCE").help("the runtime's main file"))
        .arg(
            Arg::new("include")
                .short('I')
                .value_name("DIR")
                .required_unless_present_any(["sources", "memory_map"])
                .help("where the generated .inc files are; the memory map is written there"),
        )
        .arg(
            Arg::new("rom")
                .short('o')
                .value_name("ROM")
                .required_unless_present_any(["sources", "memory_map"])
                .help("the ROM to write; its .o and .dbg go next to it"),
        )
        .arg(
            Arg::new("symbols")
                .long("symbols")
                .value_name("PATH")
                .help("also write the symbol table here: `name value`, one per line"),
        )
        .arg(
            Arg::new("sources")
                .long("sources")
                .action(ArgAction::SetTrue)
                .requires("source")
                .conflicts_with_all(["include", "rom", "memory_map"])
                .help("print the .s files SOURCE includes, in the order ca65 reads them, and build nothing"),
        )
        .arg(
            Arg::new("memory_map")
                .long("memory-map")
                .action(ArgAction::SetTrue)
                .conflicts_with_all(["include", "rom"])
                .help("print, as JSON, the numbers of the memory map —the bank size, the banks, the stack, the far RAM the linker hands out—, and build nothing"),
        )
        // Where `ca65`'s objects are kept, to assemble once what several
        // builds assemble the same: without it, or with `NO_CACHE=1`, it
        // always runs.
        .args(environment::arguments(&["cache"]))
}

pub fn run(matches: &ArgMatches) -> ExitCode {
    if matches.get_flag("memory_map") {
        let map = json!({
            "bank_size": banks::BANK_SIZE,
            "rom_size": banks::ROM_SIZE,
            "data_banks": banks::slots().len(),
            "stack": banks::STACK,
            "far_pool": {"start": banks::FAR_POOL_START, "size": banks::FAR_POOL_SIZE},
            "wram": banks::WRAM_AREAS
                .iter()
                .map(|a| json!({"area": a.name, "start": a.start, "size": a.size, "segments": a.segments}))
                .collect::<Vec<_>>(),
        });
        println!("{map}");
        return ExitCode::SUCCESS;
    }
    let Some(source) = matches.get_one::<String>("source").map(PathBuf::from) else {
        eprintln!("rm2k-snes-cartridges assemble: missing SOURCE");
        return ExitCode::from(2);
    };
    if matches.get_flag("sources") {
        return match assemble::sources(&source) {
            Ok(paths) => {
                for path in paths {
                    println!("{}", path.display());
                }
                ExitCode::SUCCESS
            }
            Err(message) => {
                eprintln!("{message}");
                ExitCode::FAILURE
            }
        };
    }
    let include = PathBuf::from(matches.get_one::<String>("include").unwrap());
    let rom = PathBuf::from(matches.get_one::<String>("rom").unwrap());
    let table = matches.get_one::<String>("symbols").map(PathBuf::from);
    let cache_dir = matches
        .get_one::<String>("cache")
        .filter(|_| !cache::disabled())
        .map(rm2k_project::absolute);
    let root = suite::root();
    match assemble::assemble(
        &source,
        &include,
        &rom,
        table.as_deref(),
        &root,
        cache_dir.as_deref(),
    ) {
        Ok(from_the_cache) => {
            if from_the_cache {
                println!("ca65: the object came from the cache");
            }
            ExitCode::SUCCESS
        }
        Err(Failure::Message(message)) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
        Err(Failure::Tool(code)) => ExitCode::from(u8::try_from(code).unwrap_or(1)),
    }
}
