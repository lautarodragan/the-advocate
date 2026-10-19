//! The event compiler from the command line: a dump and a request in,
//! `events.json` out.
//!
//! Where the dump is is the caller's to say: nothing here has a default
//! path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_events::{compile, culprits, scan, write, Bad, Game, Request, Result};
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
    /// Which commands keep each page out: every map's page, every common
    /// event and every troop page, each chased to all its culprits. A
    /// report for people, not a stage of the conversion
    Culprits(CulpritArgs),
}

#[derive(ClapArgs)]
#[command(
    after_help = "Writes culprits.json into --out and prints, per kind of page, the commands that \
                  keep some page out: how many pages each one is all that keeps out (alone), and \
                  how many it keeps out along with something else. It takes the request `scan` \
                  takes."
)]
struct CulpritArgs {
    #[command(flatten)]
    args: Args,

    /// Every map of the game, and not only the request's; a teleport to any
    /// of them compiles
    #[arg(long)]
    every_map: bool,
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

fn run_culprits(c: &CulpritArgs) -> Result<()> {
    let args = &c.args;
    let mut request = Request::read(&args.request)?;
    let mut game = Game::from_dump(&args.data, request.patches.clone())?;
    // A request written by hand does not say which Systems the cartridge
    // carries a window for —the converter does, see `systems.rs` in
    // `rm2k-snes-convert`—: every one the game names, so a
    // `ChangeSystemGraphics` is not counted as what keeps its page out.
    if request.patches.systems.is_empty() {
        request.patches.systems = game.system_names()?;
        game.patches.systems = request.patches.systems.clone();
    }
    let judged = culprits::judge_game(&game, &request, c.every_map)?;
    let report = culprits::report(&judged);
    print!("{}", culprits::table(&report));
    let io =
        |path: &std::path::Path, e: std::io::Error| Bad::usage(format!("{}: {e}", path.display()));
    std::fs::create_dir_all(&args.out).map_err(|e| io(&args.out, e))?;
    let path = args.out.join(culprits::ANSWER_FILE);
    std::fs::write(&path, serde_json::to_string_pretty(&report).unwrap() + "\n")
        .map_err(|e| io(&path, e))
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Scan(args) => run(args, false),
        Command::Compile(args) => run(args, true),
        Command::Culprits(args) => run_culprits(args),
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
