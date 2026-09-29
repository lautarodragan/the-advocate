//! The battle tables from the command line: a dump and a request in, the
//! pieces of the `.inc` and what goes with them out.
//!
//! Where the dump is is the caller's to say: nothing here has a default
//! path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_battle::{Bad, Game, Request, Result, Tables};
use std::path::PathBuf;
use std::process::ExitCode;

/// "The party does not fit in the save" is this tool answering no; "that
/// flag makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-battle",
    about = "An RPG Maker 2000 game's battle tables, for a Super Nintendo cartridge",
    after_help = "Exit codes: 1 the answer is no (it does not fit, the dump is broken), 2 bad \
                  usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Experience and level per actor, and each map's random encounters
    Tables(TablesArgs),
}

#[derive(ClapArgs)]
#[command(after_help = "Writes into --out:\n  \
    experience.inc  EXP_K, EXP_LEVEL_MAX and the experience and level tables, \
                    in RODATA\n  \
    encounters.inc  the encounter tables, in whatever segment it is included \
                    in\n  \
    battle.json     the experience slots; per map its encounter record or \
                    255; how many records and zones; and the troops the \
                    encounters name, which the cartridge has to carry\n\n\
    The request is a JSON with `party` (the actors that can fight), `maps` \
    (each with id, width and height, in the cartridge's order), \
    `encounter_steps` (null, or the steps every map gets) and `tree_nodes` \
    (nodes of maps.json, in the dump's shape, over the dump's).")]
struct TablesArgs {
    /// The Ditto dump the game is read from: the directory with maps.json
    /// and db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    /// What the cartridge decided: its party, its maps
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

fn tables(args: &TablesArgs) -> Result<()> {
    let mut game = Game::from_dump(&args.data)?;
    let request = Request::read(&args.request, &mut game)?;
    Tables::new(&game, &request)?.write(&args.out)
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Tables(args) => tables(args),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-snes-battle: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
