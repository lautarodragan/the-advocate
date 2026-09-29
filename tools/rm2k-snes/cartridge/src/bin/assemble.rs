//! `rm2k-snes-assemble`: builds a ROM from the runtime and a directory of
//! generated data.
//!
//!     rm2k-snes-assemble runtime/main.s -I build/game -o build/game/game.sfc \
//!         --symbols build/game/game.sfc.sym
//!
//! It packs the generated files into banks —rewriting them in place—, writes
//! the memory map next to them, runs `ca65` and `ld65`, writes the header
//! checksum and, with `--symbols`, the symbol table. See the library.

use std::path::PathBuf;
use std::process::ExitCode;

use cartridge::assemble::{self, Failure};
use cartridge::banks;
use clap::{Arg, ArgAction, Command};
use rm2k_project::suite;
use serde_json::json;

fn command() -> Command {
    Command::new("rm2k-snes-assemble")
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
                .help("print, as JSON, the numbers of the memory map —the bank size, the banks, the stack—, and build nothing"),
        )
}

fn main() -> ExitCode {
    let matches = command().get_matches();
    if matches.get_flag("memory_map") {
        let map = json!({
            "bank_size": banks::BANK_SIZE,
            "banks": banks::BANKS,
            "reserved_banks": banks::RESERVED_BANKS,
            "first_bank": banks::FIRST_BANK,
            "stack": banks::STACK,
        });
        println!("{map}");
        return ExitCode::SUCCESS;
    }
    let Some(source) = matches.get_one::<String>("source").map(PathBuf::from) else {
        eprintln!("rm2k-snes-assemble: missing SOURCE");
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
    match assemble::assemble(&source, &include, &rom, table.as_deref(), &suite::root()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(Failure::Message(message)) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
        Err(Failure::Tool(code)) => ExitCode::from(u8::try_from(code).unwrap_or(1)),
    }
}
