//! A game's battle pictures from the command line: a request in, the
//! pictures as the console carries them out, in a JSON. The three the
//! converter alone asks —`fullscreen`, `picture`, `background`— it calls
//! as functions, in `stage`; these are the ones the tests ask too.
//!
//! Where the pictures and the dump are is the caller's to say: nothing here
//! has a default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_images::request::{self, Paths};
use rm2k_snes_images::stage;
use rm2k_snes_images::{Bad, Result};
use serde::de::DeserializeOwned;
use serde::Serialize;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// "The picture cannot be read" is this tool answering no; "that flag
/// makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-images",
    about = "An RPG Maker 2000 game's pictures, brought to a Super Nintendo's screen and palettes",
    after_help = "Each subcommand writes <subcommand>.json into --out. Exit codes: 1 the \
                  answer is no (a picture cannot be read, the dump is broken), 2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Battle backdrops, in quality and in the light fallback
    #[command(
        after_help = "The request: {\"scene\": the geometry, \"backdrops\": [{\"file\", \
        \"quality\", \"light\"}]}; the geometry is {\"width\", \"height\", \"colors\", \
        \"cgram_base\", \"light_scale\", \"light_colors\", \"scale\": [num, den], \
        \"battler_colors\", \"alpha_min\"}. The answer: per backdrop, {\"quality\": \
        {\"indices\", \"palette\"} or null, \"light\": {\"small\", \"indices\", \"palette\"} or \
        null}."
    )]
    Backdrops(Plain),
    /// Battlers: an enemy's picture, turned by its hue, at the scene's scale
    #[command(
        after_help = "The request: {\"scene\": the geometry, as for backdrops, \
        \"battlers\": [{\"file\", \"hue\"}]}. The answer: per battler, {\"width\", \"height\", \
        \"pixels\": rows of 0 (not drawn) or palette index plus one, \"rm_height\", \
        \"palette\", \"colors\", \"merges\": [[from, to, pixels]]}."
    )]
    Battlers(Plain),
    /// Battle animations, in the box the console draws them in
    #[command(
        after_help = "The request: {\"side\", \"colors\", \"alpha_min\", \"animations\": \
        [{\"number\" (in the dump), \"sheet\"}]}. The answer: per animation, null if nothing \
        of it is drawn, or {\"frames\": per frame, rows of 0 or palette index plus one, \
        \"palette\", \"anchor\": [x, y], \"size\": [w, h], \"rm_box\": [w, h]}."
    )]
    Animations(WithDump),
}

#[derive(ClapArgs)]
struct Plain {
    /// What the cartridge decided, and which pictures
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
struct WithDump {
    /// The Ditto dump the animations are read from: the directory with db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

/// What a command answered, as `<command>.json` in `out`, which is created
/// if it is not there: on one line, with no newline after it, and its keys
/// sorted, which is how a `serde_json::Value` without `preserve_order`
/// keeps them.
fn write(out: &Path, command: &str, answer: &impl Serialize) -> Result<()> {
    let text = serde_json::to_value(answer)
        .map_err(|e| Bad::answer(e.to_string()))?
        .to_string();
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    let path = out.join(format!("{command}.json"));
    std::fs::write(&path, text).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

/// A command over its request file: read it, ask, write what it answered.
fn asked<T: DeserializeOwned + Paths, A: Serialize>(
    args: &Plain,
    command: &str,
    answer: fn(&T) -> Result<A>,
) -> Result<()> {
    write(&args.out, command, &answer(&request::read(&args.request)?)?)
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Backdrops(args) => asked(args, "backdrops", stage::backdrops),
        Command::Battlers(args) => asked(args, "battlers", stage::battlers),
        Command::Animations(args) => request::read(&args.request)
            .and_then(|r| stage::animations(&args.data, &r))
            .and_then(|answer| write(&args.out, "animations", &answer)),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-snes-images: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
