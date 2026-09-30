//! The layers of a map, and what its events are drawn with, from the
//! command line: RM2k's data and pictures in, pictures out.
//!
//! Where the game and the RTP are is the caller's to say, with the same
//! flags the rest of the suite takes: nothing here has a default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_render::fail::{Bad, Result};
use rm2k_render::{battle, battle_animation, charset, picture, source, Atlas};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// "The map names a ChipSet nobody has" is this tool answering no; "that
/// flag makes no sense" is the call being wrong. A build script wants to
/// tell those apart without reading the message.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-render",
    about = "Draw an RPG Maker 2000 game's graphics the way RM2k draws them: the tile \
             layers of a map, the other drawings of its ChipSet animation, and what its \
             events are drawn with",
    after_help = "Exit codes: 1 the answer is no (the ChipSet is missing, the map is \
                  broken), 2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// A map's layers, as PNGs in a directory
    Layers(Layers),
    /// A ChipSet expanded into every tile it can draw, as one PNG
    Atlas(AtlasArgs),
    /// What events are drawn with, as CharSet sheets: CharSets, tiles of a
    /// ChipSet, and translucent ones over what is behind them
    Charset(CharsetArgs),
    /// A battle animation's cells, cut from its sheet and placed as RM2k
    /// places them, for the caller to tone and stack
    BattleAnimation(BattleAnimationArgs),
    /// A battle's backdrops and its enemies' pictures
    Battle(BattleArgs),
}

/// Where a ChipSet is looked for: a file, or a name in the game and the RTP.
#[derive(ClapArgs)]
struct Where {
    /// The ChipSet's picture, instead of looking it up by name
    #[arg(long, value_name = "PATH")]
    chipset_file: Option<PathBuf>,

    /// The original RM2k project: its ChipSet/ is where a ChipSet is looked
    /// for first
    #[arg(long, value_name = "DIRECTORY")]
    game_dir: Option<PathBuf>,

    /// The RTP the game was made with: where a ChipSet the game does not
    /// ship is looked for
    #[arg(long, value_name = "DIRECTORY")]
    rtp_dir: Option<PathBuf>,
}

#[derive(ClapArgs)]
#[command(
    after_help = "Writes lower.png, what is drawn behind the hero on opaque black, \
                        and upper.png, what is drawn in front of it on transparency. For \
                        each family the map uses, its other drawings behind the hero: \
                        water-1.png and water-2.png, animated-1.png to animated-3.png. A \
                        family the map does not use has no files, and old ones are \
                        removed.\n\
                        --map reads a Ditto dump, --data, as it is. A map somebody \
                        changed goes in a --request: a JSON with width, height, \
                        lower_layer, upper_layer, and chipset with chipset_name, \
                        passable_data_lower and passable_data_upper, named as in the \
                        dump."
)]
struct Layers {
    /// The map's number, read from the dump in --data
    #[arg(
        long,
        value_name = "N",
        conflicts_with = "request",
        required_unless_present = "request",
        requires = "data"
    )]
    map: Option<u32>,

    /// The map as a JSON request, instead of from the dump
    #[arg(long, value_name = "PATH")]
    request: Option<PathBuf>,

    /// The Ditto dump --map reads the map from: the directory with maps/
    /// and db/
    #[arg(long, value_name = "DIRECTORY", conflicts_with = "request")]
    data: Option<PathBuf>,

    #[command(flatten)]
    chipset: Where,

    /// The directory to write the pictures to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(
    after_help = "32 tiles by 45: the three waters in their three drawings, the \
                        water's depth edges, the animated tiles, the twelve terrains in \
                        their 50 combinations, and the 288 plain tiles, in the order the \
                        map's tile ids index them."
)]
struct AtlasArgs {
    /// The ChipSet's name, looked up in the game and the RTP
    #[arg(long, value_name = "NAME", required_unless_present = "chipset_file")]
    chipset: Option<String>,

    #[command(flatten)]
    place: Where,

    /// Where to write the PNG
    #[arg(short, long, value_name = "PATH")]
    output: PathBuf,
}

#[derive(ClapArgs)]
#[command(
    after_help = "The request is a JSON list with an entry per sheet, and sheet i is \
                        written as <i>.png, an RGBA PNG. An entry is {\"charset_file\": \
                        path}, the CharSet with its colour key, or {\"chipset_file\": \
                        path, \"tile\": n}, an event drawn with tile n (0 to 143) of the \
                        ChipSet's upper layer: a sheet with that tile in the twelve poses \
                        of character 0. Either can carry \"translucent\": {\"behind\": \
                        path, \"x\": x, \"y\": y}: every pose blended at RM2k's opacity \
                        for a translucent page over what that RGBA PNG has where the event \
                        stands on cell (x, y), and opaque. Relative paths are relative to \
                        the request."
)]
struct CharsetArgs {
    /// The sheets to draw, as a JSON request
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write the sheets to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(
    after_help = "The request is a JSON list with an entry per animation, {\"sheet_file\": \
                        path, \"animation\": {...}}, the animation named as in a Ditto dump: \
                        its `large` and its `frames`, each with its `cells`. For animation i \
                        it writes <i>.json, {\"box\": [x, y, width, height], \"frames\": \
                        [[{\"x\", \"y\", \"tone\"}, ...], ...]}: the box holds every valid \
                        cell of every frame, relative to the anchor, and is null if there \
                        are none. Each cell RM2k draws of frame f, cut from the sheet, \
                        zoomed and faded, is <i>-<f>-<k>.png, an RGBA PNG: toned by its \
                        tone —red, green, blue, gray— and stacked in order at (x, y) of the \
                        box, the cells are the frame. Relative paths are relative to the \
                        request."
)]
struct BattleAnimationArgs {
    /// The animations to draw, as a JSON request
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write the cells to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(
    after_help = "The request is a JSON list with an entry per picture, and picture i is \
                        written as <i>.png, an RGBA PNG. An entry is {\"backdrop_file\": \
                        path}, a battle backdrop, drawn opaque, or {\"monster_file\": path, \
                        \"hue\": degrees}, an enemy's picture with its colour key, turned by \
                        its battler_hue. Relative paths are relative to the request."
)]
struct BattleArgs {
    /// The pictures to draw, as a JSON request
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write the pictures to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

/// The ChipSet's picture: the file given, or the one the name finds.
fn chipset(place: &Where, name: Option<&str>) -> Result<picture::Picture> {
    if let Some(path) = &place.chipset_file {
        return picture::read_rm2k(path);
    }
    let name = name.ok_or_else(|| Bad::usage("no ChipSet: --chipset or --chipset-file"))?;
    let dirs: Vec<PathBuf> = [&place.game_dir, &place.rtp_dir]
        .into_iter()
        .flatten()
        .cloned()
        .collect();
    if dirs.is_empty() {
        return Err(Bad::usage(format!(
            "ChipSet {name:?} has to be looked up and there is nowhere to: pass --game-dir \
             and --rtp-dir, or --chipset-file"
        )));
    }
    let path = source::find_resource(&dirs, "ChipSet", name).ok_or_else(|| {
        Bad::answer(format!(
            "ChipSet {name:?} is in none of {}",
            dirs.iter()
                .map(|d| d.display().to_string())
                .collect::<Vec<_>>()
                .join(", ")
        ))
    })?;
    picture::read_rm2k(&path)
}

fn do_layers(args: &Layers) -> Result<()> {
    let found = match (&args.request, args.map) {
        (Some(path), _) => source::request(path)?,
        (None, Some(id)) => {
            let data = args.data.as_deref();
            source::dump(data.ok_or_else(|| Bad::usage("--map needs --data"))?, id)?
        }
        (None, None) => return Err(Bad::usage("no map: --map or --request")),
    };
    let atlas = Atlas::new(&chipset(&args.chipset, Some(&found.chipset_name))?);
    rm2k_render::write(&args.out, &found.map.render(&atlas)?)
}

fn do_atlas(args: &AtlasArgs) -> Result<()> {
    let atlas = Atlas::new(&chipset(&args.place, args.chipset.as_deref())?);
    if let Some(dir) = args.output.parent().filter(|d| !d.as_os_str().is_empty()) {
        std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
    }
    picture::write_png(Path::new(&args.output), &atlas.picture)
}

fn do_charset(args: &CharsetArgs) -> Result<()> {
    charset::write(&args.out, &charset::request(&args.request)?)
}

fn do_battle_animation(args: &BattleAnimationArgs) -> Result<()> {
    battle_animation::write(&args.out, &battle_animation::request(&args.request)?)
}

fn do_battle(args: &BattleArgs) -> Result<()> {
    battle::write(&args.out, &battle::request(&args.request)?)
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Layers(args) => do_layers(args),
        Command::Atlas(args) => do_atlas(args),
        Command::Charset(args) => do_charset(args),
        Command::BattleAnimation(args) => do_battle_animation(args),
        Command::Battle(args) => do_battle(args),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-render: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
