//! The converter's command line: its flags, the test cases split at each
//! `--case`, and the ROM's maps in table order.

use crate::fail::{Result, Stop};
use crate::game::Command;
use clap::{value_parser, Arg, ArgAction};
use rm2k_project::environment;
use std::path::PathBuf;

/// The machine values the converter takes, and passes on.
pub const MACHINE: &[&str] = &["game_dir", "rtp_dir", "soundfont", "cache"];

const ABOUT: &str = "Converts an rm2k-snes game into the data a Super Nintendo cartridge carries.

It reads the command line, asks the game what it needs to know, has each map
converted and hands everything to the emission, calling each stage of the
conversion —each one a program on the PATH— in order.

With a test page, which is the list of RM2k commands from a JSON file; several
in one cartridge, each one after a `--case`, and the cartridge flags before
the first:

    rm2k-snes-convert -o … --map-id 6 \\
        --test-commands pan.json --case --test-commands pan-vuelve.json";

fn command() -> clap::Command {
    let mut c = clap::Command::new("rm2k-snes-convert")
        .about(ABOUT)
        .version(env!("CARGO_PKG_VERSION"))
        .arg(
            Arg::new("map_id")
                .long("map-id")
                .value_parser(value_parser!(i32))
                .help(
                    "the boot map, which goes first in the table. Mandatory and with no \
                     default: it belongs to the game, and its project file declares it",
                ),
        )
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the game's directory, where its rm2k-snes.toml is. Without this, it is \
                       looked for from the current directory upwards"),
        );
    for arg in environment::arguments(MACHINE) {
        c = c.arg(arg);
    }
    c.arg(Arg::new("output").short('o').long("output").value_name("PATH").help(
        "where the .inc goes; everything else the conversion writes goes next to it. \
         Without this, inc/mapdata.inc in the project's build",
    ))
    .arg(Arg::new("msu").long("msu").value_name("PATH").help(
        "where to write the .msu with the data the MSU-1 serves to the ROM: next to the \
         .sfc and with its name, so the emulator finds it. Without this, datos.msu next \
         to --output",
    ))
    .arg(
        Arg::new("text_padding")
            .long("text-padding")
            .value_parser(value_parser!(i64))
            .default_value("0")
            .help(
                "dead texts after the item ones, so that the battle's indices go past 255 \
                 without building a twenty-nine-map cartridge. It doesn't change a pixel",
            ),
    )
    .arg(Arg::new("no_title").long("no-title").action(ArgAction::SetTrue).help(
        "without the game's title screen and its start and load menu: the ROM boots \
         straight into the map. The title screen would add frames to the boot, and the \
         suite's cases compare frames counted from reset",
    ))
    .arg(Arg::new("title_4bpp").long("title-4bpp").action(ArgAction::SetTrue).help(
        "the title screen at four bits per pixel, in mode 1, even if it fits at eight: \
         the path a title too big for the VRAM takes, for a game whose title fits",
    ))
    .arg(
        Arg::new("measure_headroom")
            .long("measure-headroom")
            .value_name("HEADROOM")
            .value_parser(value_parser!(f64))
            .help(
                "the same headroom for every song, instead of the volume ceiling table: it is \
                 what `rm2k-snes-volume-ceilings` builds the ROM where it measures each song's \
                 peak with",
            ),
    )
    .arg(Arg::new("msu_everything").long("msu-everything").action(ArgAction::SetTrue).help(
        "every piece that may travel in the .msu travels there, even if the ROM has room, \
         and the ROM needs the MSU-1: for the tests, so that the path the ROM reads them by \
         runs in a game that fits. Without this, the project's `[rom] msu` decides",
    ))
    .arg(Arg::new("enemy_hp").long("enemy-hp").action(ArgAction::SetTrue).help(
        "the battle shows the enemies' HP, which RM2k never shows: for debugging",
    ))
    .arg(Arg::new("no_speed_keys").long("no-speed-keys").action(ArgAction::SetTrue).help(
        "L and R do not change the hero's speed. They are a port addition, not RM2k's",
    ))
    .arg(Arg::new("no_timer").long("no-timer").action(ArgAction::SetTrue).help(
        "the timer digits only in the maps where a case that uses them runs, and not in \
         the ones the game's timer can reach",
    ))
    .arg(
        Arg::new("test_graphic")
            .long("test-graphic")
            .num_args(2)
            .value_names(["CHARSET", "INDEX"])
            .action(ArgAction::Append)
            .help(
                "puts this graphic in the sprite bank of the maps where some case runs, so \
                 that the test page can change someone's graphic. It can be repeated",
            ),
    )
    .arg(
        Arg::new("test_encounters")
            .long("test-encounters")
            .value_name("STEPS")
            .value_parser(value_parser!(i64))
            .help(
                "every how many steps there is a random encounter, for every map of the \
                 cartridge; 0 turns them off. Without this the game tree's value applies",
            ),
    )
    .arg(
        Arg::new("test_events_max")
            .long("test-events-max")
            .value_name("EVENTS")
            .value_parser(value_parser!(usize))
            .help(
                "how many events a map keeps, as if the console's RAM held that many: what a \
                 test lowers to reach the twins and the events left out with the maps of a \
                 game that fits. Only the converter's choice moves; the RAM is the same",
            ),
    )
    .arg(Arg::new("hero_above").long("hero-above").action(ArgAction::SetTrue).help(
        "the hero at object priority 2, above the layer that should cover it",
    ))
    .arg(
        Arg::new("party")
            .long("party")
            .value_name("ACTOR")
            .num_args(1..)
            .value_parser(value_parser!(i32))
            .help(
                "the party it starts with, by actor ids. The hero's graphic is the first \
                 one's. By default, the database's",
            ),
    )
    .arg(Arg::new("test_commands").long("test-commands").value_name("FILE").help(
        "this case's test page, as the command list of an RM2k page in Ditto's JSON. It \
         is compiled with the context of the map where it runs: that of its Teleport if \
         it starts with one, and otherwise the boot map's",
    ))
    .arg(
        Arg::new("maps")
            .long("maps")
            .value_name("ID")
            .num_args(1..)
            .value_parser(value_parser!(i32))
            .help("other maps to put in the same ROM. The one from --map-id goes first"),
    )
    .arg(
        Arg::new("start_index")
            .long("start-index")
            .value_name("N")
            .value_parser(value_parser!(i64))
            .default_value("0")
            .help("which table index the ROM boots at"),
    )
}

/// What the command line says.
#[derive(Debug, Clone)]
pub struct Options {
    pub map_id: i32,
    pub project: Option<PathBuf>,
    pub environment: environment::Environment,
    pub output: Option<PathBuf>,
    pub msu: Option<PathBuf>,
    pub text_padding: i64,
    pub no_title: bool,
    pub title_4bpp: bool,
    pub measure_headroom: Option<f64>,
    pub msu_everything: bool,
    pub enemy_hp: bool,
    pub no_speed_keys: bool,
    pub no_timer: bool,
    pub test_graphic: Option<Vec<(String, i32)>>,
    pub test_encounters: Option<i64>,
    pub test_events_max: Option<usize>,
    pub hero_above: bool,
    pub party: Option<Vec<i32>>,
    pub maps: Vec<i32>,
    pub start_index: i64,
    /// The test pages' files, case 0 first.
    pub case_files: Vec<String>,
}

/// The flags that describe a test case —what its page does— and not the
/// cartridge: the only ones that can go after a `--case`. Where a case runs
/// is not a flag: its `Teleport` says so, see [`case_map`].
const CASE_FLAGS: &[&str] = &["test_commands"];

pub fn parse(argv: Vec<String>) -> Result<Options> {
    let mut stretches: Vec<Vec<String>> = vec![Vec::new()];
    for token in argv {
        if token == "--case" {
            stretches.push(Vec::new());
        } else {
            stretches.last_mut().unwrap().push(token);
        }
    }
    let matches = command()
        .try_get_matches_from(std::iter::once("rm2k-snes-convert".to_string()).chain(stretches[0].clone()))
        .unwrap_or_else(|e| e.exit());
    let mut test_graphic = None;
    if let Some(occurrences) = matches.get_occurrences::<String>("test_graphic") {
        let mut graphics = Vec::new();
        for pair in occurrences {
            let pair: Vec<&String> = pair.collect();
            let index = pair[1]
                .parse::<i32>()
                .map_err(|_| Stop::usage(format!("--test-graphic: {} is not a number", pair[1])))?;
            graphics.push((pair[0].clone(), index));
        }
        test_graphic = Some(graphics);
    }
    let mut case_files = Vec::new();
    if let Some(file) = matches.get_one::<String>("test_commands") {
        case_files.push(file.clone());
    }
    for stretch in &stretches[1..] {
        let loose = command()
            .try_get_matches_from(std::iter::once("rm2k-snes-convert".to_string()).chain(stretch.clone()))
            .unwrap_or_else(|e| e.exit());
        for id in loose.ids() {
            let id = id.as_str();
            if CASE_FLAGS.contains(&id) {
                continue;
            }
            if loose.value_source(id) == Some(clap::parser::ValueSource::CommandLine) {
                return Err(Stop::usage(format!(
                    "--{} belongs to the cartridge and not to a case: it goes before the first --case",
                    id.replace('_', "-")
                )));
            }
        }
        match loose.get_one::<String>("test_commands") {
            Some(file) => case_files.push(file.clone()),
            None => return Err(Stop::usage("a --case with nothing for the test page to do")),
        }
    }
    let map_id = *matches
        .get_one::<i32>("map_id")
        .ok_or_else(|| Stop::usage("--map-id is missing, the boot map"))?;
    Ok(Options {
        map_id,
        project: matches.get_one::<String>("project").map(PathBuf::from),
        environment: environment::Environment::from_matches(&matches, MACHINE),
        output: matches.get_one::<String>("output").map(PathBuf::from),
        msu: matches.get_one::<String>("msu").map(PathBuf::from),
        text_padding: *matches.get_one::<i64>("text_padding").unwrap(),
        no_title: matches.get_flag("no_title"),
        title_4bpp: matches.get_flag("title_4bpp"),
        measure_headroom: matches.get_one::<f64>("measure_headroom").copied(),
        msu_everything: matches.get_flag("msu_everything"),
        enemy_hp: matches.get_flag("enemy_hp"),
        no_speed_keys: matches.get_flag("no_speed_keys"),
        no_timer: matches.get_flag("no_timer"),
        test_graphic,
        test_encounters: matches.get_one::<i64>("test_encounters").copied(),
        test_events_max: matches.get_one::<usize>("test_events_max").copied(),
        hero_above: matches.get_flag("hero_above"),
        party: matches.get_many::<i32>("party").map(|v| v.copied().collect()),
        maps: matches.get_many::<i32>("maps").map(|v| v.copied().collect()).unwrap_or_default(),
        start_index: *matches.get_one::<i64>("start_index").unwrap(),
        case_files,
    })
}

impl Options {
    /// The ROM's maps, in table order and without repeats. **The order is
    /// the contract**: a compiled teleport stores the index in this table,
    /// not the RM2k id.
    pub fn map_order(&self) -> Vec<i32> {
        let mut out = vec![self.map_id];
        out.extend(self.maps.iter().copied().filter(|&m| m != self.map_id));
        out
    }
}

/// The map where a case runs: that of its `Teleport`, if it starts with
/// one, and otherwise the map where the ROM boots. The page still lives in
/// event 0 of the boot map —that is where the ROM finds it and where it
/// runs first—, but what comes after the jump runs in the other map, so it
/// is compiled with that one's context.
pub fn case_map(file: &str, commands: &[Command], order: &[i32], initial: usize) -> Result<i32> {
    let Some(first) = commands.first() else {
        return Ok(order[initial]);
    };
    if first.code != rm2k_snes_events::codes::TELEPORT {
        return Ok(order[initial]);
    }
    let dest = first.parameters[0];
    if !order.contains(&dest) {
        crate::stop!(
            "{file}: the case jumps to map {dest}, which isn't in the cartridge (it carries {})",
            order.iter().map(|m| m.to_string()).collect::<Vec<_>>().join(" ")
        );
    }
    Ok(dest)
}
