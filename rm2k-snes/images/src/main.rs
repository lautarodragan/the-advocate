//! A game's pictures from the command line: a request in, the pictures as
//! the console carries them out, in a JSON.
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
    /// A picture that fills the screen at 8 bits a pixel: unique tiles, a
    /// palette and a tilemap
    #[command(
        after_help = "The request: {\"file\", \"width\", \"height\", \"cell\", \
        \"first_color\", \"cap\"}. The answer: {\"tiles\": [8x8 CGRAM indices], \
        \"palette\": [[r, g, b] at five bits], \"tilemap\": [tile per cell, row by row]}."
    )]
    Fullscreen(Plain),
    /// The picture of a ShowPicture: where it lands and its colours
    #[command(
        after_help = "The request: {\"file\", \"use_transparent_color\", \"top_trans\", \
        \"x\", \"y\" (its centre on RM2k's screen), \"rm_screen\": [w, h], \"screen\": [w, h], \
        \"colors\", \"zoom\" (percent, 100 by default), \"map_fixed\" (false by default: \
        with the map it is not scaled to the console's screen)}. The answer: {\"x\", \"y\" \
        (its corner; with the map, relative to its centre), \"width\", \"height\", \"palette\", \
        \"indices\": rows of palette indices plus one, 0 where it is transparent}."
    )]
    Picture(Plain),
    /// The picture of a ShowPicture too big for the sprites, as a 4bpp layer
    #[command(
        after_help = "The request: {\"file\", \"use_transparent_color\", \"x\", \"y\" (its \
        centre on RM2k's screen), \"rm_screen\", \"screen\", \"zoom\" (100 by default), \
        \"crop\": [x, y] (absent by default: the pixel of the picture the screen is cut \
        from, unscaled, instead of scaling it), \"palettes\", \"first_palette\", \"tiles\" (the most distinct tiles, the blank one \
        included), \"rows\" (the most rows of cells), \"mode7\": {\"tiles\", \"layer_tiles\", \
        \"layer_rows\"} (absent by default: the layer as a mode 7 texture too, if it takes no more \
        than those)}. The answer, null if not even cut to the screen do its tiles fit: {\"top\" (where the canvas \
        starts, from the top of the screen), \"rows\", \"columns\", \"wider\" (whether it goes \
        past the screen's sides), \"tile_count\", \"tiles\" \
        (4bpp, hex), \"tilemap\" (an entry per cell, row by row), \"palettes\" (sixteen \
        colours each, from first_palette on), and if asked and the layer leaves room for \
        it, \"mode7\": {\"tile_count\", \"tiles\" (a byte a pixel, hex, tile 0 blank), \"map\" \
        (a tile per cell, row by row), \"distinct\" (the tiles before grouping them), \"center\" \
        (where on the screen a zoom shrinks it towards)}}."
    )]
    Background(Plain),
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
        Command::Fullscreen(args) => asked(args, "fullscreen", stage::fullscreen),
        Command::Picture(args) => asked(args, "picture", stage::picture),
        Command::Background(args) => asked(args, "background", stage::background),
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
