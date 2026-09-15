//! A 65816 assembler that also lays out the cartridge image, with no separate
//! linker.
//!
//! It does the job of an assembler and a linker together for one fixed memory
//! map: LoROM, a handful of named segments, and a header with its checksum.
//! There is no object file in between, which is what lets a label carry its
//! full 24-bit address from the moment it is placed.
//!
//! It is not a complete 65816 assembler. It covers the subset the sources it
//! is pointed at actually use and fails loudly at anything else, which for a
//! tool like this is the right behaviour: an error is far better than an image
//! that is subtly different.

mod assembler;
mod expr;
mod layout;
mod opcodes;

use clap::Parser;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// What the two exit codes mean, and why they are not the same.
///
/// A source that does not assemble is a normal answer —something in the
/// program has to be fixed— while an unreadable source or an unwritable output
/// is the caller getting it wrong. A build script wants to tell those apart.
const FAILED: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "w65",
    about = "Assemble 65816 sources into a LoROM cartridge image",
    after_help = "The -I directories are searched before the source's own, which is what \
                  lets one build use a generated include of its own without touching the \
                  one in the tree.\n\
                  Exit codes: 1 the source did not assemble, 2 bad usage.",
    version
)]
struct Args {
    /// The top-level source to assemble
    source: Option<PathBuf>,

    /// Where to write the cartridge image
    #[arg(short, long, value_name = "PATH")]
    output: Option<PathBuf>,

    /// Look here for .include files, before the source's own directory. May be
    /// repeated
    #[arg(short = 'I', long = "include", value_name = "DIR")]
    include: Vec<PathBuf>,

    /// Write the symbol table here, one `name value` per line
    #[arg(long, value_name = "PATH")]
    symbols: Option<PathBuf>,

    /// Leave the header checksum alone, for comparing against an assembler
    /// that does not write one
    #[arg(long)]
    no_checksum: bool,

    /// Print the instruction table and exit, without assembling anything
    #[arg(long)]
    list_opcodes: bool,
}

enum Failure {
    /// The source is wrong.
    Source(String),
    /// The call is wrong.
    Usage(String),
}

fn run(args: &Args) -> Result<(), Failure> {
    if args.list_opcodes {
        print!("{}", opcodes::table());
        return Ok(());
    }

    // `source` and `output` are required to assemble but not to list, which is
    // why clap does not enforce them: a required argument that one mode does
    // not want cannot be expressed there. The cost is these two messages, and
    // they say the same thing clap would have said.
    let source = args
        .source
        .as_ref()
        .ok_or_else(|| Failure::Usage("a source to assemble is required".into()))?;
    let output = args
        .output
        .as_ref()
        .ok_or_else(|| Failure::Usage("--output <PATH> is required".into()))?;

    // Read the source here rather than letting the assembler trip over it, so
    // that "you pointed me at nothing" and "your program is wrong" do not come
    // out with the same exit code.
    if !source.is_file() {
        return Err(Failure::Usage(format!("{}: not a file I can read", source.display())));
    }

    let mut assembler = assembler::Assembler::new(!args.no_checksum, &args.include);
    let rom = assembler
        .assemble(source)
        .map_err(|error| Failure::Source(error.to_string()))?;

    write(output, &rom).map_err(Failure::Usage)?;
    println!("{} -> {} ({} bytes)", source.display(), output.display(), rom.len());

    if let Some(path) = &args.symbols {
        let mut table: Vec<(&String, i64)> = assembler
            .symbols()
            .iter()
            .filter_map(|(name, value)| value.map(|v| (name, v)))
            .collect();
        table.sort();
        let mut text = String::new();
        for (name, value) in table {
            text.push_str(&format!("{name} {value}\n"));
        }
        write(path, text.as_bytes()).map_err(Failure::Usage)?;
    }
    Ok(())
}

fn write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(directory) = path.parent() {
        if !directory.as_os_str().is_empty() {
            std::fs::create_dir_all(directory)
                .map_err(|e| format!("{}: {e}", directory.display()))?;
        }
    }
    std::fs::write(path, bytes).map_err(|e| format!("{}: {e}", path.display()))
}

fn main() -> ExitCode {
    let args = Args::parse();
    match run(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(Failure::Source(message)) => {
            eprintln!("w65: {message}");
            ExitCode::from(FAILED)
        }
        Err(Failure::Usage(message)) => {
            eprintln!("error: {message}");
            ExitCode::from(MISUSE)
        }
    }
}
