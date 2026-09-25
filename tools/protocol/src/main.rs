//! Generate both ends of a bytecode from its declaration.
//!
//! A bytecode has two sides that must agree byte for byte: whatever emits the
//! bytes, and whatever reads them. This takes one declaration of the opcodes
//! and writes the constants for each side, so the numbers have one owner and a
//! change is a diff on both ends at once.
//!
//! Where the files go is not this tool's business: the caller passes the
//! paths. That is what keeps it independent of whatever project uses it.

mod declaration;
mod emit;

use clap::Parser;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// What the two exit codes mean, and why they are not the same.
///
/// `--check` failing is a normal answer —something is out of date and has to
/// be regenerated—, while a broken declaration or an unwritable path is the
/// caller getting it wrong. A build script wants to tell those apart.
const STALE: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "protocol",
    about = "Generate a bytecode's constants for both of its sides",
    after_help = "Both outputs are optional: pass the ones you need.\n\
                  Exit codes: 1 something is out of date, 2 bad usage.",
    version
)]
struct Args {
    /// The .toml declaring the opcodes
    declaration: PathBuf,

    /// Write a Python module here
    #[arg(long, value_name = "PATH")]
    python: Option<PathBuf>,

    /// Write 65816 assembler equates here
    #[arg(long, value_name = "PATH")]
    asm: Option<PathBuf>,

    /// Also put a jump table in the assembler output: a macro with one
    /// `.addr` per opcode, in number order, each naming the opcode in lower
    /// case. The numbers have to run from 0 with no gaps.
    #[arg(long, requires = "asm")]
    jump_table: bool,

    /// Write nothing; exit 1 if an output is out of date
    #[arg(long)]
    check: bool,
}

fn run(args: &Args) -> Result<u8, String> {
    if args.python.is_none() && args.asm.is_none() {
        return Err("nothing to write: pass --python, --asm, or both".into());
    }

    let declaration = declaration::load(&args.declaration).map_err(|e| e.to_string())?;

    // Only the declaration's file name: with the path, the generated text
    // would depend on how the caller spelled it, and `--check` would call a
    // file stale for having been generated from an equivalent path.
    let source = Path::new(&args.declaration)
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .ok_or_else(|| format!("{}: not a file", args.declaration.display()))?;

    let mut wanted: Vec<(&PathBuf, String)> = Vec::new();
    if let Some(p) = &args.python {
        wanted.push((p, emit::python(&declaration, &source)));
    }
    if let Some(p) = &args.asm {
        let text = emit::asm(&declaration, &source, args.jump_table)
            .map_err(|e| format!("{}: {e}", args.declaration.display()))?;
        wanted.push((p, text));
    }

    let mut stale = Vec::new();
    for (path, text) in &wanted {
        let current = std::fs::read_to_string(path).ok();
        if current.as_deref() == Some(text.as_str()) {
            continue;
        }
        if args.check {
            stale.push(path.display().to_string());
            continue;
        }
        if let Some(dir) = path.parent() {
            if !dir.as_os_str().is_empty() {
                std::fs::create_dir_all(dir)
                    .map_err(|e| format!("{}: {e}", dir.display()))?;
            }
        }
        std::fs::write(path, text).map_err(|e| format!("{}: {e}", path.display()))?;
        println!("wrote {}", path.display());
    }

    if !stale.is_empty() {
        eprintln!("out of date: {}", stale.join(", "));
        eprintln!("run the same command without --check");
        return Ok(STALE);
    }
    if args.check {
        println!(
            "{} {} opcodes, {} file(s) up to date",
            declaration.opcodes.len(),
            declaration.name,
            wanted.len()
        );
    }
    Ok(0)
}

fn main() -> ExitCode {
    let args = Args::parse();
    match run(&args) {
        Ok(code) => ExitCode::from(code),
        Err(message) => {
            eprintln!("error: {message}");
            ExitCode::from(MISUSE)
        }
    }
}
