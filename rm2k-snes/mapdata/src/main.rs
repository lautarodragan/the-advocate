//! The cartridge's data `.inc` from the command line: a request in, what
//! it made out, in a directory.
//!
//! Where anything is is the caller's to say: nothing here has a default
//! path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_mapdata::fail::{Bad, Result};
use rm2k_snes_mapdata::materials::{self, RawBlocks, COMPRESSED_KINDS};
use rm2k_snes_mapdata::{animation, hex, record, request, vram};
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
        \"slot_map\", \"slot_text_width\", \"slot_text_level\", \
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
    /// What the cartridge carries per map: its record, its data blocks, its
    /// pages and its tables, and the poses of whoever changes pose
    #[command(
        after_help = "The request: {\"maps\": [a map as the conversion left it: see `Map` in \
        request.rs]}, in the order of the cartridge's table. It writes offsets.inc —the \
        record's fields—, maps.inc —the poses, the LZ2 caps and each map's blocks, in RODATA— \
        and tables.inc —the map table and the ChipSet animation's—, and maps.json: {\"notes\": \
        what it says, in order, \"report\": what was shared and compressed, \"frames\": per \
        map, how many frames decompressing it takes}. With --raw, what the console \
        decompresses of each map, uncompressed, into that directory."
    )]
    Maps(MapsArgs),
    /// One map's page table, alone
    #[command(
        after_help = "The request: {\"number\": the map's index in the cartridge, \"evcode\": \
        the label of its code block, \"pages\": [a page: see `Page` in request.rs], \
        \"changing\", \"appearing\", \"turning\": [events], \"animated\": [[CharSet, index]]}. \
        It writes pages.inc."
    )]
    Pages(Plain),
    /// The whole .inc of a cartridge
    #[command(
        after_help = "The request: what every domain of the conversion answered —see `Emit` in \
        request.rs—. The database's items, skills, enemies, actors and troops are read from \
        the dump in --data. It writes mapdata.inc and mapdata.json: {\"notes\": what it says, in \
        order, \"report\": what was shared and compressed, \"frames\": per map, how many frames \
        decompressing it takes}. With --raw, what the console decompresses of each map, \
        uncompressed, into that directory. The answer is no if something does not fit where \
        the console reads it."
    )]
    Emit(EmitArgs),
    /// The engine's numbers, by name: the ones the .inc hands the runtime
    #[command(
        after_help = "The request: {}. The answer: {\"NAME\": its value} for every number of \
        engine.rs, and for PARALLEL_MAX and ROUTE_EV_MAX, the caps a map's compiled pages are \
        checked against: a number, or a list of numbers."
    )]
    Engine(Plain),
}

#[derive(ClapArgs)]
struct EmitArgs {
    /// The Ditto dump the database is read from: the directory with db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    #[command(flatten)]
    maps: MapsArgs,
}

#[derive(ClapArgs)]
struct MapsArgs {
    #[command(flatten)]
    plain: Plain,

    /// Where to leave each map's blocks, uncompressed
    #[arg(long, value_name = "DIRECTORY")]
    raw: Option<PathBuf>,
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
            "maps": maps,
        }),
    )
}

fn do_compress(args: &Plain) -> Result<()> {
    let request = read(&args.request)?;
    let mut maps: Vec<(i64, RawBlocks)> = Vec::new();
    for m in request["maps"].as_array().map(Vec::as_slice).unwrap_or(&[]) {
        let id = m["id"]
            .as_i64()
            .ok_or_else(|| Bad::answer("a map without an id"))?;
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

fn write_text(out: &Path, name: &str, text: &str) -> Result<()> {
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    let path = out.join(name);
    std::fs::write(&path, text).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn do_maps(args: &MapsArgs) -> Result<()> {
    let mut request: request::Maps = request::read(&args.plain.request)?;
    let mut notes = animation::fit_all(&mut request.maps);
    let written = record::maps(&request.maps)?;
    notes.extend(written.notes);
    if let Some(raw) = &args.raw {
        materials::write_raw(raw, &written.raw)?;
    }
    let out = &args.plain.out;
    write_text(out, "offsets.inc", &written.offsets)?;
    write_text(out, "maps.inc", &written.maps)?;
    write_text(out, "tables.inc", &written.tables)?;
    write(
        out,
        "maps",
        &json!({"notes": notes, "report": written.report, "frames": written.frames}),
    )
}

#[derive(serde::Deserialize)]
struct PagesRequest {
    number: usize,
    evcode: String,
    pages: Vec<request::Page>,
    #[serde(default)]
    changing: Vec<i64>,
    #[serde(default)]
    appearing: Vec<i64>,
    #[serde(default)]
    turning: Vec<i64>,
    #[serde(default)]
    movable: Vec<i64>,
    #[serde(default)]
    animated: Vec<(String, i64)>,
    #[serde(default)]
    animated_palettes: Vec<i64>,
}

fn do_pages(args: &Plain) -> Result<()> {
    let r: PagesRequest = request::read(&args.request)?;
    let map = record::PageMap {
        pages: &r.pages,
        changing: &r.changing,
        appearing: &r.appearing,
        turning: &r.turning,
        movable: &r.movable,
        animated: &r.animated,
        animated_palettes: &r.animated_palettes,
    };
    write_text(
        &args.out,
        "pages.inc",
        &record::page_table(&map, r.number, &r.evcode),
    )
}

fn do_emit(args: &EmitArgs) -> Result<()> {
    let mut request: request::Emit = request::read(&args.maps.plain.request)?;
    // A ChipSet animation cut to fit is a loss, which the converter lists
    // with the cartridge's others.
    let cut = animation::fit_all_by_map(&mut request.maps);
    let losses: Vec<Value> = cut
        .iter()
        .map(
            |(map, text)| json!({"map": map, "kind": "chipset-animation-cut", "text": text.trim()}),
        )
        .collect();
    let mut notes: Vec<String> = cut.into_iter().map(|(_, note)| note).collect();
    let db = rm2k_snes_battle::db::Db::from_dump(&args.data, true)
        .map_err(|b| Bad::answer(b.message().to_string()))?;
    let emitted = rm2k_snes_mapdata::emit::emit(&request, &db)?;
    notes.extend(emitted.notes);
    if let Some(raw) = &args.maps.raw {
        materials::write_raw(raw, &emitted.raw)?;
    }
    let out = &args.maps.plain.out;
    write_text(out, "mapdata.inc", &emitted.text)?;
    write(
        out,
        "mapdata",
        &json!({"notes": notes, "report": emitted.report, "frames": emitted.frames, "losses": losses}),
    )
}

fn do_engine(args: &Plain) -> Result<()> {
    read(&args.request)?;
    let numbers: serde_json::Map<String, Value> = rm2k_snes_mapdata::engine::numbers()
        .into_iter()
        .map(|(name, value)| (name.to_string(), value))
        .collect();
    write(&args.out, "engine", &Value::Object(numbers))
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Vram(args) => do_vram(args),
        Command::Compress(args) => do_compress(args),
        Command::Maps(args) => do_maps(args),
        Command::Pages(args) => do_pages(args),
        Command::Emit(args) => do_emit(args),
        Command::Engine(args) => do_engine(args),
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
