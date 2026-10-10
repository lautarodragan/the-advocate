//! The battle from the command line: a dump and a request in; the pieces
//! of the `.inc` and what goes with them, the battle's model, a battle
//! played or the victory's lines out.
//!
//! Where the dump is is the caller's to say: nothing here has a default
//! path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::model::{
    self, EXPERIENCE_FILE, LAYOUT_FILE, LINES_FILE, MODEL_FILE, SIMULATE_FILE,
};
use rm2k_snes_battle::{screen, Bad, Game, Request, Result, Tables};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// "The party does not fit in the save" is this tool answering no; "that
/// flag makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-battle",
    about = "An RPG Maker 2000 game's battle, for a Super Nintendo cartridge",
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
    /// What the rest of the conversion writes of the battle: its skills,
    /// actions, items, troops and texts, and its screen's geometry
    Model(StageArgs),
    /// A battle played turn by turn, for whoever compares a console's
    Simulate(StageArgs),
    /// The victory's lines, as the console builds them
    Lines(StageArgs),
    /// What a `ChangeExp` or a `ChangeLevel` leaves an actor with, and its
    /// level-up message
    Experience(StageArgs),
    /// The geometry of the battle's text screen
    Layout(LayoutArgs),
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

#[derive(ClapArgs)]
#[command(after_help = "Writes into --out one JSON, named after the subcommand: model.json, \
    simulate.json, lines.json or experience.json. The README says what each request and each answer hold.")]
struct StageArgs {
    /// The Ditto dump the game is read from: the directory with maps.json
    /// and db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    /// What is asked: see the README
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(after_help = "Writes layout.json into --out. The request is ignored: the geometry \
    does not depend on any game.")]
struct LayoutArgs {
    /// Ignored: it is there so that every subcommand is called the same way
    #[arg(long, value_name = "PATH")]
    request: Option<PathBuf>,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

fn write(dir: &Path, name: &str, answer: &Value) -> Result<()> {
    let io = |path: &Path, e: std::io::Error| Bad::usage(format!("{}: {e}", path.display()));
    std::fs::create_dir_all(dir).map_err(|e| io(dir, e))?;
    let path = dir.join(name);
    let text = serde_json::to_string_pretty(answer).unwrap() + "\n";
    std::fs::write(&path, text).map_err(|e| io(&path, e))
}

fn stage(args: &StageArgs, name: &str, answer: fn(&Db, &Value) -> Result<Value>) -> Result<()> {
    let request = model::read_request(&args.request)?;
    // The troops are most of a database: only a request that names one
    // reads them.
    let db = Db::from_dump(&args.data, model::needs_troops(&request))?;
    write(&args.out, name, &answer(&db, &request)?)
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
        Command::Model(args) => stage(args, MODEL_FILE, model::model),
        Command::Simulate(args) => stage(args, SIMULATE_FILE, model::simulate),
        Command::Lines(args) => stage(args, LINES_FILE, model::lines),
        Command::Experience(args) => stage(args, EXPERIENCE_FILE, model::experience),
        Command::Layout(args) => write(&args.out, LAYOUT_FILE, &screen::layout()),
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
