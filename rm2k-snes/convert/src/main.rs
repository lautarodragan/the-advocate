//! `rm2k-snes-convert`: the questions a game's tests ask the converter, by
//! their word —see `queries`—. Converting is `advocate build`'s, which calls
//! the library; until 2026-11-25 anything that was not a question was a
//! conversion, onto this process's stdout.

use rm2k_snes_convert::queries;
use std::io::Write;
use std::process::ExitCode;

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let done = queries::run(argv);
    let _ = std::io::stdout().flush();
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(stop) => {
            eprintln!("{}", stop.message);
            ExitCode::from(stop.code)
        }
    }
}
