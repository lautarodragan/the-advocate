//! `rm2k-snes-convert`: an rm2k-snes game into the data a Super Nintendo
//! cartridge carries, and the questions a game's tests ask the converter.
//! What it does is the library's, `rm2k_snes_convert`: this only reads the
//! command line and says how it went.

use rm2k_snes_convert::{convert, options, queries};
use std::io::Write;
use std::process::ExitCode;

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    // A question a game's test asks goes by its word, first; anything else
    // is a conversion, onto this process's stdout.
    let done = if argv
        .first()
        .is_some_and(|a| queries::QUERIES.contains(&a.as_str()))
    {
        queries::run(argv)
    } else {
        options::parse(argv).and_then(convert::run)
    };
    let _ = std::io::stdout().flush();
    match done {
        Ok(()) => ExitCode::SUCCESS,
        // `--help`, which the flags' parser answers on stdout.
        Err(stop) if stop.code == 0 => {
            println!("{}", stop.message);
            ExitCode::SUCCESS
        }
        Err(stop) => {
            eprintln!("{}", stop.message);
            ExitCode::from(stop.code)
        }
    }
}
