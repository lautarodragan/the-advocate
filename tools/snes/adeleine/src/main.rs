//! Adeleine from the command line: colours in a JSON request, what was
//! decided in a JSON answer.
//!
//! Where the files go is the caller's to say: nothing here has a default
//! path.

use adeleine::request::{self, merged_answer, packed_answer, reduced_answer};
use adeleine::{merge_least_visible, reduce_colors, try_pack, Bad, Result};
use clap::{Args as ClapArgs, Parser, Subcommand};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;

/// "It cannot be brought down that far" is this tool answering no; "that
/// request makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "adeleine",
    about = "Decide which colours a picture loses and how the ones left are grouped into \
             palettes",
    after_help = "Exit codes: 1 the answer is no (no amount of merging makes it fit), 2 bad \
                  usage.\n\n\
                  A colour is [r, g, b], and a colour with its pixels [r, g, b, pixels]. A \
                  tile is the list of colours it draws with. A palette holds 15 colours for \
                  the drawing, sixteen entries minus the transparent one, unless the request \
                  says otherwise in per_palette.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Merge the colours that show the least until only `keep` are left
    #[command(
        after_help = "The request: {\"counts\": [[r, g, b, pixels], ...], \"keep\": N}.\n\
        Writes merge.json: {\"mapping\": [...], \"merges\": [...]}. mapping is the colour each \
        one of counts became, in the order of counts; merges is each merge in the order it \
        was made, as [victim, target, pixels]."
    )]
    Merge(Files),
    /// Group the tiles' colours into palettes, merging nothing
    #[command(
        after_help = "The request: {\"tiles\": [[[r, g, b], ...], ...], \"palettes\": N}.\n\
        Writes pack.json: {\"palettes\": [[[r, g, b], ...], ...]}, each palette's colours in \
        order, or {\"palettes\": null} if the tiles do not fit in that many."
    )]
    Pack(Files),
    /// Merge the colours that show the least until the tiles fit in the palettes
    #[command(
        after_help = "The request: {\"counts\": [[r, g, b, pixels], ...], \"tiles\": \
        [[[r, g, b], ...], ...], \"palettes\": N}. counts are the pixels over the whole \
        picture, and tiles the colours of each distinct tile.\n\
        Writes reduce.json: {\"mapping\": [...], \"palettes\": [...], \"merges\": [...]}, as \
        merge and pack write them."
    )]
    Reduce(Files),
}

#[derive(ClapArgs)]
struct Files {
    /// The request, a JSON file
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write the answer into
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

fn read(files: &Files) -> Result<String> {
    fs::read_to_string(&files.request).map_err(|e| {
        Bad::usage(format!(
            "cannot read the request {}: {e}",
            files.request.display()
        ))
    })
}

fn write(files: &Files, name: &str, answer: &Value) -> Result<()> {
    fs::create_dir_all(&files.out)
        .and_then(|()| fs::write(files.out.join(name), answer.to_string()))
        .map_err(|e| Bad::usage(format!("cannot write into {}: {e}", files.out.display())))
}

fn run(command: &Command) -> Result<()> {
    match command {
        Command::Merge(files) => {
            let asked = request::merge_request(&read(files)?)?;
            let merged = merge_least_visible(&asked.counts, asked.keep)?;
            write(files, "merge.json", &merged_answer(&merged))
        }
        Command::Pack(files) => {
            let asked = request::pack_request(&read(files)?)?;
            let palettes = try_pack(&asked.tiles, asked.palettes, asked.per_palette);
            write(files, "pack.json", &packed_answer(palettes.as_deref()))
        }
        Command::Reduce(files) => {
            let asked = request::reduce_request(&read(files)?)?;
            let reduced = reduce_colors(
                &asked.counts,
                &asked.tiles,
                asked.palettes,
                asked.per_palette,
            )?;
            write(files, "reduce.json", &reduced_answer(&reduced))
        }
    }
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match run(&cli.command) {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("adeleine: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
