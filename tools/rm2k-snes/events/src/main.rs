//! The event compiler from the command line: a dump and a request in,
//! `events.json` out.
//!
//! Where the dump is is the caller's to say: nothing here has a default
//! path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_events::{compile, scan, write, Bad, Game, Request, Result};
use std::path::PathBuf;
use std::process::ExitCode;

/// "A text has a letter the font does not have" is this tool answering no;
/// "that flag makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-events",
    about = "An RPG Maker 2000 game's event pages, compiled for a Super Nintendo cartridge",
    after_help = "Exit codes: 1 the answer is no (it cannot be compiled, the dump is broken), 2 bad \
                  usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// The indices of the whole game, which pages of each map compile, and
    /// each map's pages compiled without songs: what the caller needs
    /// before it builds the maps
    Scan(Args),
    /// Every page of the cartridge, with the text block, the songs, the
    /// troops and the troops' pages
    Compile(Args),
}

#[derive(ClapArgs)]
#[command(
    after_help = "Writes events.json into --out. The request's fields are described in the \
                        crate's README."
)]
struct Args {
    /// The Ditto dump the game is read from: the directory with maps.json
    /// and db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    /// What the cartridge decided, and what the project changed on top of
    /// the dump
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

fn run(args: &Args, compiling: bool) -> Result<()> {
    let request = Request::read(&args.request)?;
    let game = Game::from_dump(&args.data, request.patches.clone())?;
    let answer = if compiling {
        compile(&game, &request)?
    } else {
        scan(&game, &request)?
    };
    write(&answer, &args.out)
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Scan(args) => run(args, false),
        Command::Compile(args) => run(args, true),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-snes-events: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
