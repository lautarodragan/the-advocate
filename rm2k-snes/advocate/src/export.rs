//! `advocate export`: the way back of `import`, an exact dump written as
//! RPG Maker's own files —`RPG_RT.ldb`, `RPG_RT.lmt` and one `.lmu` per
//! map—, which is what RPG Maker 2000 and EasyRPG open. Ditto's `pack`.
//!
//! A port never needs it: its game is somebody else's and stays as it came.
//! It is for a game whose source is the dump, written by hand, like the
//! test game's `src/`: `export` makes its RM2k files, and `import` of them
//! gives the converter its dump and proves the way back, as for a port.
//!
//! Until 2026-11-27 it was `ditto pack`; taro's, that day: Ditto's binary
//! goes, and the library stays. The name is from `import`'s, the usual pair.

use std::path::Path;

use clap::{Arg, ArgMatches, Command};

pub fn command() -> Command {
    Command::new("export")
        .about("Writes an exact dump back as RPG Maker's .ldb, .lmt and .lmu files")
        .arg(
            Arg::new("exact").value_name("EXACT").required(true).help(
                "the exact dump: what `import` leaves in build/exact/, or one written by hand",
            ),
        )
        .arg(
            Arg::new("game")
                .value_name("GAME")
                .required(true)
                .help("the directory the files are written into; what else is in it stays"),
        )
}

pub fn run(matches: &ArgMatches) -> Result<(), String> {
    let exact = Path::new(matches.get_one::<String>("exact").expect("required"));
    let game = Path::new(matches.get_one::<String>("game").expect("required"));
    let written = ditto::dump::pack(exact, game).map_err(|e| e.to_string())?;
    eprintln!("{} files in {}", written.len(), game.display());
    Ok(())
}
