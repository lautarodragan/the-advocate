//! Ditto: `.ldb`/`.lmu`/`.lmt` ⇄ JSON, one file at a time or a whole game.

use ditto::{describe, dump, file};
use std::path::Path;
use std::process::ExitCode;

fn usage() -> ExitCode {
    eprintln!(
        "usage:\n  \
         ditto read   <file.lmu|.ldb|.lmt> [out.json]\n  \
         ditto write  <file.json> [out.lmu]\n  \
         ditto unpack <game dir> <exact dir> <resolved dir>\n  \
         ditto pack   <exact dir> <game dir>\n  \
         ditto schema [out.json]\n\n\
         read/write do one file, and with no output file they write to standard\n\
         output. unpack writes a whole game as a tree of JSON, in its two views\n\
         and in one run: the exact dump, which is what pack reads back, and the\n\
         resolved view, where every field is written and every enum is a number,\n\
         which is the one to read without knowing the format. See README.md.\n\
         schema writes out the format's own tables —every field's default and\n\
         the enums—, which is what reading the exact dump takes."
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
        // `unpack` takes the two output directories and not one: the exact
        // dump and the resolved view are written together on purpose, so that
        // there is no way to end up with one of each run. See `dump`.
        "unpack" => match (output, args.get(3).map(Path::new)) {
            (Some(exact), Some(resolved)) => tree_unpack(input, exact, resolved),
            _ => return usage(),
        },
        "pack" => match output {
            Some(out) => tree_pack(input, out),
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

fn tree_unpack(
    game: &Path,
    exact: &Path,
    resolved: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let files = dump::unpack(game, exact, resolved)?;
    said(&files, exact);
    said(&files, resolved);
    Ok(())
}

fn tree_pack(dump_dir: &Path, out: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let files = dump::pack(dump_dir, out)?;
    said(&files, out);
    Ok(())
}

/// Says how many files went into a directory and what they weigh, because the
/// whole point of `unpack` and `pack` is that what comes out is a directory
/// and not something one can look at on the terminal.
fn said(files: &[std::path::PathBuf], dir: &Path) {
    let mine: Vec<&std::path::PathBuf> = files.iter().filter(|p| p.starts_with(dir)).collect();
    let bytes: u64 = mine
        .iter()
        .filter_map(|p| std::fs::metadata(p).ok().map(|m| m.len()))
        .sum();
    eprintln!("{} files, {bytes} bytes, in {}", mine.len(), dir.display());
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
