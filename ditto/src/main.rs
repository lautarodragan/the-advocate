//! Ditto: `.ldb`/`.lmu`/`.lmt` ⇄ JSON.

use ditto::file;
use std::path::Path;
use std::process::ExitCode;

fn usage() -> ExitCode {
    eprintln!(
        "usage:\n  \
         ditto read  <file.lmu|.ldb|.lmt> [out.json]\n  \
         ditto write <file.json> [out.lmu]\n\n\
         With no output file, it writes to standard output."
    );
    ExitCode::from(2)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 2 {
        return usage();
    }
    let input = Path::new(&args[1]);
    let output = args.get(2).map(Path::new);
    let r = match args[0].as_str() {
        "read" => read(input, output),
        "write" => write(input, output),
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
