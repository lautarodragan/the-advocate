//! A game's pictures from the command line: a request in, the pictures as
//! the console carries them out, in a JSON.
//!
//! Where the pictures and the dump are is the caller's to say: nothing here
//! has a default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use ditto::dump::Dump;
use ditto::schema::Animation;
use rm2k_render::{battle, picture, show_picture as rm2k_picture};
use rm2k_snes_images::request::{self, Animations, Backdrops, Battlers, Fullscreen, ShowPicture};
use rm2k_snes_images::{animation, fullscreen, scene, show_picture, Bad, Result};
use serde_json::Value;
use std::collections::HashMap;
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

fn write(out: &Path, name: &str, answer: &Value) -> Result<()> {
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    let path = out.join(format!("{name}.json"));
    std::fs::write(&path, answer.to_string())
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn do_fullscreen(args: &Plain) -> Result<()> {
    let r: Fullscreen = request::read(&args.request)?;
    let screen = fullscreen::convert(
        &picture::read_unkeyed(&r.file)?,
        r.width,
        r.height,
        r.cell,
        r.first_color,
        r.cap,
    );
    write(
        &args.out,
        "fullscreen",
        &request::fullscreen_answer(&screen),
    )
}

fn do_picture(args: &Plain) -> Result<()> {
    let r: ShowPicture = request::read(&args.request)?;
    let drawn = rm2k_picture::picture(
        &picture::read_unkeyed(&r.file)?,
        &picture::read_rm2k(&r.file)?,
        r.use_transparent_color,
        r.top_trans,
    );
    let screens = show_picture::Screens {
        rm: r.rm_screen,
        console: r.screen,
    };
    let shown = show_picture::Shown {
        zoom: r.zoom,
        map_fixed: r.map_fixed,
        ..show_picture::Shown::PLAIN
    };
    let converted = show_picture::convert_shown(&drawn, r.x, r.y, screens, r.colors, shown)?;
    write(&args.out, "picture", &request::picture_answer(&converted))
}

fn do_backdrops(args: &Plain) -> Result<()> {
    let r: Backdrops = request::read(&args.request)?;
    let g: scene::Geometry = r.scene.into();
    let mut answer = Vec::with_capacity(r.backdrops.len());
    for wanted in &r.backdrops {
        let drawn = battle::backdrop(&wanted.file)?;
        let quality = wanted
            .quality
            .then(|| request::backdrop_answer(&scene::backdrop(&drawn, &g)));
        let light = match wanted.light {
            true => Some(request::light_answer(&scene::light_backdrop(&drawn, &g)?)),
            false => None,
        };
        answer.push(serde_json::json!({"quality": quality, "light": light}));
    }
    write(&args.out, "backdrops", &Value::Array(answer))
}

fn do_battlers(args: &Plain) -> Result<()> {
    let r: Battlers = request::read(&args.request)?;
    let g: scene::Geometry = r.scene.into();
    let answer = r
        .battlers
        .iter()
        .map(|b| {
            Ok(request::battler_answer(&scene::battler(
                &battle::battler(&b.file, b.hue)?,
                &g,
            )?))
        })
        .collect::<Result<Vec<_>>>()?;
    write(&args.out, "battlers", &Value::Array(answer))
}

fn do_animations(args: &WithDump) -> Result<()> {
    let r: Animations = request::read(&args.request)?;
    let g = animation::Geometry::from(&r);
    let dump = Dump::open(&args.data).map_err(|e| Bad::answer(e.0))?;
    let all: Vec<Animation> = dump.section("animations").map_err(|e| Bad::answer(e.0))?;
    let by_number: HashMap<i32, &Animation> = all.iter().map(|a| (a.id, a)).collect();
    let mut sheets: HashMap<PathBuf, rm2k_render::Picture> = HashMap::new();
    let mut answer = Vec::with_capacity(r.animations.len());
    for wanted in &r.animations {
        let anim = by_number.get(&wanted.number).ok_or_else(|| {
            Bad::answer(format!(
                "{}: the dump has no animation {}",
                args.data.display(),
                wanted.number
            ))
        })?;
        if !sheets.contains_key(&wanted.sheet) {
            sheets.insert(wanted.sheet.clone(), picture::read_rm2k(&wanted.sheet)?);
        }
        let converted = animation::convert(anim, &sheets[&wanted.sheet], &g);
        answer.push(converted.map_or(Value::Null, |c| request::animation_answer(&c)));
    }
    write(&args.out, "animations", &Value::Array(answer))
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Fullscreen(args) => do_fullscreen(args),
        Command::Picture(args) => do_picture(args),
        Command::Backdrops(args) => do_backdrops(args),
        Command::Battlers(args) => do_battlers(args),
        Command::Animations(args) => do_animations(args),
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
