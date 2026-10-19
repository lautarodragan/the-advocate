//! What a game's tests ask the converter, without converting anything: the
//! questions whose answer is the converter's —how it asks the event
//! compiler, who it decides can lead the party, what it hands `wally` about
//! a map—, so a test gets them from the one place that decides them and
//! not from a copy. Each one prints its answer as JSON.
//!
//!     rm2k-snes-convert scan [--maps M...] [--test-commands FILE...] [--extra-variable V...]
//!     rm2k-snes-convert compile [--maps M...] [--case MAP FILE...] [--encounter-troop T...]
//!     rm2k-snes-convert leaders --maps M... --party A...
//!     rm2k-snes-convert map-context --map M
//!     rm2k-snes-convert boxes
//!
//! Each takes `--project` and the machine's flags, as the conversion does.

use crate::compiler::Compiler;
use crate::fail::{Result, Stop};
use crate::game::{Command, Game};
use crate::settings::Settings;
use clap::{value_parser, Arg, ArgAction, ArgMatches};
use rm2k_project::{environment, Project};
use serde_json::json;
use std::collections::BTreeSet;
use std::path::PathBuf;

/// The questions, by the word that asks each.
pub const QUERIES: [&str; 5] = ["scan", "compile", "leaders", "map-context", "boxes"];

fn common(c: clap::Command) -> clap::Command {
    let mut c = c.arg(
        Arg::new("project")
            .long("project")
            .value_name("DIRECTORY")
            .help(
            "the game's directory, where its rm2k-snes.toml is; without this, it is looked for \
         from the current directory upwards",
        ),
    );
    for arg in environment::arguments(crate::options::MACHINE) {
        c = c.arg(arg);
    }
    c
}

fn maps_arg(required: bool) -> Arg {
    Arg::new("maps")
        .long("maps")
        .value_name("ID")
        .num_args(if required { 1.. } else { 0.. })
        .required(required)
        .value_parser(value_parser!(i32))
}

fn command() -> clap::Command {
    clap::Command::new("rm2k-snes-convert")
        .about("What a game's tests ask the converter, as JSON on standard output")
        .subcommand_required(true)
        .subcommand(
            common(clap::Command::new("scan"))
                .about(
                    "The event compiler's first answer, as the converter asks for it: the \
                     indices, and which pages compile. Without --maps, every map of the dump; \
                     with --maps and no number, none —the indices are the whole game's anyway—",
                )
                .arg(maps_arg(false))
                .arg(
                    Arg::new("test_commands")
                        .long("test-commands")
                        .value_name("FILE")
                        .action(ArgAction::Append),
                )
                .arg(
                    Arg::new("extra_variable")
                        .long("extra-variable")
                        .value_name("V")
                        .action(ArgAction::Append)
                        .value_parser(value_parser!(i32)),
                ),
        )
        .subcommand(
            common(clap::Command::new("compile"))
                .about(
                    "The event compiler's second answer for a cartridge of --maps built without \
                     converting them: each --case is a page compiled in a map, and each \
                     --encounter-troop a troop the cartridge carries",
                )
                .arg(maps_arg(false))
                .arg(
                    Arg::new("case")
                        .long("case")
                        .num_args(2)
                        .value_names(["MAP", "FILE"])
                        .action(ArgAction::Append),
                )
                .arg(
                    Arg::new("encounter_troop")
                        .long("encounter-troop")
                        .value_name("T")
                        .action(ArgAction::Append)
                        .value_parser(value_parser!(i32)),
                ),
        )
        .subcommand(
            common(clap::Command::new("leaders"))
                .about("The actors that can lead the party in a cartridge of these maps")
                .arg(maps_arg(true))
                .arg(
                    Arg::new("party")
                        .long("party")
                        .value_name("ACTOR")
                        .num_args(1..)
                        .required(true)
                        .value_parser(value_parser!(i32)),
                ),
        )
        .subcommand(
            common(clap::Command::new("map-context"))
                .about(
                    "What the converter hands `wally` about a map besides its decisions: the \
                     dump, the directories pictures are looked for in, the project's files and \
                     the names it gives the map's graphics",
                )
                .arg(
                    Arg::new("map")
                        .long("map")
                        .required(true)
                        .value_parser(value_parser!(i32)),
                ),
        )
        .subcommand(common(clap::Command::new("boxes")).about(
            "The text boxes the converter hands the event compiler, rebuilt for the \
                     window, and the window they were rebuilt for",
        ))
}

fn ints(m: &ArgMatches, id: &str) -> Vec<i32> {
    m.get_many::<i32>(id)
        .map(|v| v.copied().collect())
        .unwrap_or_default()
}

fn commands_of(file: &str) -> Result<Vec<Command>> {
    crate::convert::handwritten_commands(std::path::Path::new(file))
}

pub fn run(argv: Vec<String>) -> Result<()> {
    let matches = command()
        .try_get_matches_from(std::iter::once("rm2k-snes-convert".to_string()).chain(argv))
        .unwrap_or_else(|e| e.exit());
    let (name, m) = matches.subcommand().expect("a subcommand is required");
    let project = Project::locate(m.get_one::<String>("project").map(PathBuf::from).as_deref())?;
    let settings = Settings { project: &project };
    let mut environment = environment::Environment::from_matches(m, crate::options::MACHINE);
    environment.unpack(&project)?;
    let game = Game::read(environment.game()?, &project)?;
    let answer = match name {
        "scan" => {
            let compiler = Compiler::new(&game, &settings)?;
            let maps = if m.value_source("maps") == Some(clap::parser::ValueSource::CommandLine) {
                ints(m, "maps")
            } else {
                game.dump_map_ids()?
            };
            let mut commands = Vec::new();
            for file in m.get_many::<String>("test_commands").into_iter().flatten() {
                commands.extend(commands_of(file)?);
            }
            let extra: BTreeSet<i32> = ints(m, "extra_variable").into_iter().collect();
            compiler.scan(&maps, &commands, &extra, None, &[])?
        }
        "compile" => {
            let compiler = Compiler::new(&game, &settings)?;
            let mut cases = Vec::new();
            if let Some(occurrences) = m.get_occurrences::<String>("case") {
                for pair in occurrences {
                    let pair: Vec<&String> = pair.collect();
                    let map: i32 = pair[0]
                        .parse()
                        .map_err(|_| Stop::usage(format!("--case: {} is not a map", pair[0])))?;
                    cases.push((map, commands_of(pair[1])?));
                }
            }
            compiler.loose(&ints(m, "maps"), &cases, &ints(m, "encounter_troop"))?
        }
        "leaders" => {
            let compiler = Compiler::new(&game, &settings)?;
            let maps = ints(m, "maps");
            let scan = compiler.scan(&maps, &[], &BTreeSet::new(), None, &[])?;
            let read: Vec<crate::game::GameMap> =
                maps.iter().map(|id| game.map(*id)).collect::<Result<_>>()?;
            let refs: Vec<&crate::game::GameMap> = read.iter().collect();
            let changes = crate::scan::party_changes(&refs, &scan)?;
            json!(crate::scan::possible_leaders(&changes, &ints(m, "party")))
        }
        "map-context" => {
            let id = *m.get_one::<i32>("map").unwrap();
            let search_dirs = crate::convert::search_dirs(&game, &project, environment.rtp()?)?;
            let map = game.map(id)?;
            json!({
                "data": game.dump.to_string_lossy(),
                "search_dirs": search_dirs.iter().map(|d| rm2k_project::absolute(d).to_string_lossy().to_string())
                    .collect::<Vec<_>>(),
                "map_files": crate::compiler::map_files(&game),
                "chipset_files": crate::compiler::chipset_files(&game),
                "names": crate::compiler::names([&map]).into_iter().map(|e| json!([e[1], e[2], e[3]]))
                    .collect::<Vec<_>>(),
            })
        }
        "boxes" => {
            let compiler = Compiler::new(&game, &settings)?;
            json!({"window": compiler.window(), "boxes": compiler.boxes()})
        }
        other => return Err(Stop::usage(format!("{other} is not a question"))),
    };
    println!(
        "{}",
        serde_json::to_string(&answer).expect("an answer is JSON")
    );
    Ok(())
}
