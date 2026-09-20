//! Ditto: `.ldb`/`.lmu`/`.lmt` ⇄ JSON, one file at a time or a whole game.

use ditto::{describe, dump, file};
use std::path::Path;
use std::process::ExitCode;

fn usage() -> ExitCode {
    eprintln!(
        "usage:\n  \
         ditto read   <file.lmu|.ldb|.lmt> [out.json]\n  \
         ditto write  <file.json> [out.lmu]\n  \
         ditto unpack <game dir> <dump dir>\n  \
         ditto pack   <dump dir> <game dir>\n  \
         ditto schema [out.json]\n\n\
         read/write do one file, and with no output file they write to standard\n\
         output. unpack/pack do a whole game as a tree of JSON: see README.md.\n\
         schema writes out what a reader of that JSON needs and the JSON does\n\
         not carry: every field's default —absent means default— and the enum\n\
         tables the names in it come from."
    );
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    // `schema` reads nothing, so it is the one command that takes no input.
    if args.first().map(String::as_str) == Some("schema") {
        return match emit(describe::to_json().as_bytes(), args.get(1).map(Path::new)) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("ditto: {e}");
                ExitCode::FAILURE
            }
        };
    }
    if args.len() < 2 {
        return usage();
    }
    let input = Path::new(&args[1]);
    let output = args.get(2).map(Path::new);
    let r = match args[0].as_str() {
        "read" => read(input, output),
        "write" => write(input, output),
        "unpack" | "pack" => match output {
            Some(out) => tree(&args[0], input, out),
            None => return usage(),
        },
        _ => return usage(),
    };
    match r {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("ditto: {e}");
            ExitCode::FAILURE
        }
    }
}

fn read(input: &Path, output: Option<&Path>) -> Result<(), Box<dyn std::error::Error>> {
    let doc = file::read(&std::fs::read(input)?)?;
    emit(&serde_json::to_vec_pretty(&doc)?, output)
}

fn write(input: &Path, output: Option<&Path>) -> Result<(), Box<dyn std::error::Error>> {
    let doc: file::Document = serde_json::from_slice(&std::fs::read(input)?)?;
    emit(&file::write(&doc)?, output)
}

/// Says how many files it wrote, because the whole point of these two is that
/// what comes out is a directory and not something one can look at on the
/// terminal.
fn tree(command: &str, input: &Path, output: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let files = match command {
        "unpack" => dump::unpack(input, output)?,
        _ => dump::pack(input, output)?,
    };
    let bytes: u64 = files
        .iter()
        .filter_map(|p| std::fs::metadata(p).ok().map(|m| m.len()))
        .sum();
    eprintln!("{} files, {bytes} bytes, in {}", files.len(), output.display());
    Ok(())
}

fn emit(d: &[u8], output: Option<&Path>) -> Result<(), Box<dyn std::error::Error>> {
    match output {
        Some(p) => std::fs::write(p, d)?,
        None => {
            use std::io::Write;
            std::io::stdout().write_all(d)?;
        }
    }
    Ok(())
}
