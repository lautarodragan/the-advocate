//! `advocate import`: an RPG Maker game in its own format —its `.ldb`,
//! `.lmt` and every `.lmu`— into the project's, the dump in `[paths] data`
//! the converter reads. Pictures, music and sounds are not imported: the
//! build reads them from the untouched game.
//!
//! **It writes the two views of the dump, in one run** —Ditto's `unpack`—:
//! the resolved view into `data/`, what the converter and a game's tests
//! read, and the exact one into `build/exact/`, the binary's own shape and
//! the only one that writes back. **And it checks its own round trip**: the
//! exact dump packed again has to give back every `.ldb`, `.lmt` and `.lmu`
//! of the game byte for byte, or it fails saying which. It is what makes
//! `data/` the game and not an approximate reading of it.
//!
//! Until 2026-11-27 this was each game's `just dump` running `ditto unpack`
//! and `ditto pack`, with a Python script of the ports that took the RPG
//! Maker files out of the `.zip` and compared them; taro's, that day:
//! `advocate import` instead of `ditto`, which stays a library.

use std::path::{Path, PathBuf};

use clap::{Arg, ArgMatches, Command};
use rm2k_project::archive;
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::{absolute, Project};

/// The machine values it takes: the game, and the cache a `.zip` game is
/// unpacked into, the same one `build` unpacks it into.
const MACHINE: &[&str] = &["game_dir", "cache"];

pub fn command() -> Command {
    Command::new("import")
        .about("Imports the game's .ldb, .lmt and .lmu into the dump in [paths] data, and checks they come back byte for byte")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where advocate.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(MACHINE))
        .arg(
            Arg::new("data")
                .long("data")
                .value_name("DIR")
                .help("where the resolved view goes. Without this, the project's [paths] data"),
        )
        .arg(
            Arg::new("exact")
                .long("exact")
                .value_name("DIR")
                .help("where the exact dump goes, the one that writes back. Without this, exact/ in the project's build"),
        )
}

pub fn run(matches: &ArgMatches) -> Result<(), String> {
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let given = Environment::from_matches(matches, MACHINE);
    let game = matches
        .get_one::<String>("game_dir")
        .map(absolute)
        .ok_or("missing --game-dir: the original RM2k game, a directory or a .zip of one")?;
    // Not `Environment::unpack`, which also puts the port's own files in
    // front of the game's: what is imported is the game as its author left
    // it, and the port's files are the build's business.
    let game = if archive::is_zip(&game) {
        let hash = archive::content_hash(&game)?;
        archive::unpacked(&game, &hash, &given.cache(&project)?.join("zip"))?
    } else {
        game
    };
    let data = match matches.get_one::<String>("data") {
        Some(d) => absolute(d),
        None => project.data()?,
    };
    let exact = match matches.get_one::<String>("exact") {
        Some(d) => absolute(d),
        None => project.build().join("exact"),
    };
    let written = ditto::dump::unpack(&game, &exact, &data).map_err(|e| e.to_string())?;
    said(&written, &data);
    said(&written, &exact);
    // Beside the exact dump, so that one imported somewhere else to look at
    // it leaves nothing in the project.
    let again = PathBuf::from(format!("{}-again", exact.display()));
    ditto::dump::round_trip(&game, &exact, &again).map_err(|e| e.to_string())?;
    eprintln!("and the exact dump packs back to the game byte for byte");
    Ok(())
}

/// How many files went into a directory and what they weigh: what comes out
/// is a directory, not something to look at on the terminal.
fn said(files: &[PathBuf], dir: &Path) {
    let mine: Vec<&PathBuf> = files.iter().filter(|p| p.starts_with(dir)).collect();
    let bytes: u64 = mine
        .iter()
        .filter_map(|p| std::fs::metadata(p).ok().map(|m| m.len()))
        .sum();
    eprintln!("{} files, {bytes} bytes, in {}", mine.len(), dir.display());
}
