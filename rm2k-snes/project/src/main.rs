//! `rm2k-snes-project`: a project as the tools resolve it, in JSON.
//!
//!     rm2k-snes-project [--project DIRECTORY]
//!
//! What it prints, and why it is asked and not read, is in `resolved.rs`.

use std::path::Path;
use std::process::ExitCode;

use clap::{Arg, Command};
use rm2k_project::{resolved, Error, Project};

fn command() -> Command {
    Command::new("rm2k-snes-project")
        .about("Prints a project as the tools resolve it, in JSON: its paths, the suite's own, and its settings")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where rm2k-snes.toml is. Without this, it is looked up from the current directory upwards"),
        )
}

fn run() -> Result<(), Error> {
    let matches = command().get_matches();
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let out = resolved(&project)?;
    println!("{}", serde_json::to_string_pretty(&out).expect("a JSON value always serializes"));
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("rm2k-snes-project: {error}");
            ExitCode::FAILURE
        }
    }
}
