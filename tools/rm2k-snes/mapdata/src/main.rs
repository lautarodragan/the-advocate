//! The cartridge's data `.inc` from the command line: a request in, what
//! it made out, in a directory.
//!
//! Where anything is is the caller's to say: nothing here has a default
//! path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_mapdata::fail::{Bad, Result};
use rm2k_snes_mapdata::materials::{self, RawBlocks, COMPRESSED_KINDS};
use rm2k_snes_mapdata::{cgram, hex, vram};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// "It does not fit" is this tool answering no; "that flag makes no sense"
/// is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-mapdata",
    about = "The data .inc of a Super Nintendo cartridge converted from an RPG Maker 2000 game",
    after_help = "Each subcommand writes <subcommand>.json into --out. Exit codes: 1 the \
                  answer is no (something does not fit), 2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// The VRAM layouts, the constants of the cartridge's memory, and which
    /// layout each map gets
    #[command(
        after_help = "The request: {\"maps\": [[background tiles, sprite tiles, upper tiles]]}. \
        The answer: {\"layouts\": [{\"name\", \"sprites\", \"tiles\", \"map\", \"above\", \
        \"window\", \"window_map\": [base in words, tiles]}], \"window\": [w, h], \
        \"map_layout\", \"above_map\", \"window_bases\", \"slots\", \"slot_vram\", \
        \"slot_map\", \"slot_text_width\", \"slot_text_level\", \"cgram_reserved\", \
        \"maps\": [{\"layout\": its name} or {\"refused\": why}]}. The layouts are checked \
        against the hardware on every call."
    )]
    Vram(Plain),
    /// The blocks the console decompresses, as LZ2 streams, each part once
    #[command(
        after_help = "The request: {\"maps\": [{\"id\", \"map_tiles\", \"above_tiles\", \
        \"sprite_tiles\", \"anim_tiles\", \"map_cells\": hex}]}. The answer: {\"maps\": \
        [{the same classes: the stream, in hex, its parts' streams stuck together; \
        \"frames\": how many frames the console takes to decompress the map}]}. The answer is \
        no if a stream does not fit in its place in WRAM."
    )]
    Compress(Plain),
}

#[derive(ClapArgs)]
struct Plain {
    /// What to answer for, in JSON
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

fn read(path: &Path) -> Result<Value> {
    let whose = path.display();
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
    serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))
}

fn write(out: &Path, name: &str, answer: &Value) -> Result<()> {
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    let path = out.join(format!("{name}.json"));
    std::fs::write(&path, answer.to_string())
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn number(value: &Value, what: &str) -> Result<u32> {
    value
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or_else(|| Bad::answer(format!("{what} is not a number: {value}")))
}

fn do_vram(args: &Plain) -> Result<()> {
    vram::check_splits()?;
    let request = read(&args.request)?;
    let piece = |p: vram::Piece| json!([p.base, p.count]);
    let layouts: Vec<Value> = vram::LAYOUTS
        .iter()
        .map(|l| {
            let mut entry = json!({"name": l.name});
            for (name, p) in l.pieces() {
                entry[name] = piece(p);
            }
            entry
        })
        .collect();
    let mut maps = Vec::new();
    for counts in request["maps"].as_array().map(Vec::as_slice).unwrap_or(&[]) {
        let n = |k: usize| number(&counts[k], "a map's tile count");
        maps.push(match vram::vram_layout(n(0)?, n(1)?, n(2)?) {
            Ok(layout) => json!({"layout": layout.name}),
            Err(refused) => json!({"refused": refused.message()}),
        });
    }
    write(
        &args.out,
        "vram",
        &json!({
            "layouts": layouts,
            "window": [vram::WINDOW_W, vram::WINDOW_H],
            "map_layout": vram::MAP_LAYOUT,
            "above_map": vram::VRAM_ABOVE_MAP,
            "window_bases": vram::WINDOW_BASES,
            "slots": vram::SLOTS,
            "slot_vram": vram::SLOT_VRAM,
            "slot_map": vram::SLOT_MAP,
            "slot_text_width": vram::SLOT_TEXT_WIDTH,
            "slot_text_level": vram::SLOT_TEXT_LEVEL,
            "cgram_reserved": cgram::CGRAM_RESERVED,
            "maps": maps,
        }),
    )
}

fn do_compress(args: &Plain) -> Result<()> {
    let request = read(&args.request)?;
    let mut maps: Vec<(i64, RawBlocks)> = Vec::new();
    for m in request["maps"].as_array().map(Vec::as_slice).unwrap_or(&[]) {
        let id = m["id"].as_i64().ok_or_else(|| Bad::answer("a map without an id"))?;
        let mut blocks = RawBlocks::new();
        for kind in COMPRESSED_KINDS {
            let text = m[kind].as_str().unwrap_or("");
            blocks.insert(kind.to_string(), hex::decode(text)?);
        }
        maps.push((id, blocks));
    }
    let refs: Vec<(i64, &RawBlocks)> = maps.iter().map(|(id, b)| (*id, b)).collect();
    let compressed = materials::compress_blocks(&refs)?;
    let answer: Vec<Value> = maps
        .iter()
        .map(|(_, blocks)| {
            let mut entry = json!({"frames": materials::decompress_frames(blocks, &compressed)});
            for kind in COMPRESSED_KINDS {
                entry[kind] = json!(hex::encode(&materials::stream_of(
                    kind,
                    &blocks[kind],
                    &compressed
                )));
            }
            entry
        })
        .collect();
    write(&args.out, "compress", &json!({"maps": answer}))
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Vram(args) => do_vram(args),
        Command::Compress(args) => do_compress(args),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-snes-mapdata: {}", bad.message());
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
