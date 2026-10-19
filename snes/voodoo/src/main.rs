//! Tiles from the command line: an indexed picture in, tiles and a tilemap
//! and colour memory out.
//!
//! Where the files go is the caller's business: nothing here has a default
//! path or a directory it knows about. What it does have opinions about is
//! saying no clearly — a picture that breaks the format gets told which cell
//! and why, because the thing a caller does next is fix that cell.

use clap::{Args as ClapArgs, Parser, Subcommand};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use voodoo::convert::{Options, COLORS_PER_PALETTE};
use voodoo::fail::{Bad, Result};
use voodoo::grid::{Picture, CELL, ENTRIES};
use voodoo::{color, image, pack};

/// What the two exit codes mean, and why they are not the same.
///
/// "This cell draws with two palettes" is this tool working correctly and
/// answering no; "that file is not a PNG" is the call being wrong. A build
/// script wants to tell those apart without reading the message.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "voodoo",
    about = "Cut an indexed picture into 8x8 tiles and pack them, with the tilemap and \
             colour memory, the way a planar PPU reads them",
    after_help = "Exit codes: 1 the answer is no (the picture breaks the format, it needs \
                  too many tiles), 2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// An indexed picture into tiles, a tilemap and colour memory
    Convert(Convert),
    /// Tiles, colour memory and tilemap back into an indexed picture
    Render(Render),
}

#[derive(ClapArgs)]
#[command(after_help = "The picture is an 8-bit indexed PNG whose indices are \
                        colour-memory entries: at 4bpp, index >> 4 is the palette and \
                        index & 15 the colour inside it, and every cell has to draw with \
                        one palette. Choosing the palettes is not this tool's job.\n\
                        Mirrored cells are not new tiles: a tilemap entry carries an x \
                        and a y flip, so the four orientations are tried against the \
                        tiles already placed.\n\
                        A cell that differs from the picture in some frame of an \
                        animation gets tiles of its own, in one contiguous run per \
                        animation after the still ones: stepping it is overwriting the \
                        run with the next frame's data. All the pictures carry colour \
                        memory, and they have to agree on every entry some of them \
                        draw with.")]
struct Convert {
    /// The indexed PNG to convert
    input: PathBuf,

    /// Where to write the tile data
    #[arg(short, long, value_name = "PATH")]
    output: PathBuf,

    /// Where to write colour memory: all 256 entries, as little-endian words
    #[arg(long, value_name = "PATH")]
    palette: Option<PathBuf>,

    /// Where to write the tilemap, one little-endian entry per cell
    #[arg(long, value_name = "PATH")]
    tilemap: Option<PathBuf>,

    /// Bits per pixel
    #[arg(long, value_name = "N", default_value_t = 4, value_parser = depth)]
    bpp: usize,

    /// Set the priority bit on every tilemap entry that draws something
    #[arg(long)]
    priority: bool,

    /// Refuse a picture needing more distinct tiles than this
    #[arg(long, value_name = "N", default_value_t = 1024)]
    max_tiles: usize,

    /// Do not keep tile 0 for the empty cell
    #[arg(long)]
    no_blank_tile: bool,

    /// An animation: its frames other than the picture itself, comma
    /// separated. Repeat for each animation.
    #[arg(long, value_name = "PNG,PNG...")]
    animation: Vec<String>,

    /// Where to write an animation's run as every frame draws it, the picture
    /// first. One per --animation, in the same order.
    #[arg(long, value_name = "PATH")]
    animation_out: Vec<PathBuf>,

    /// Print what happened as JSON instead of prose
    #[arg(long)]
    json: bool,
}

#[derive(ClapArgs)]
#[command(
    after_help = "The inverse of `convert`: the same indices come back, with \
                        colour memory as the palette."
)]
struct Render {
    /// The tile data
    tiles: PathBuf,

    /// Colour memory, as little-endian words
    #[arg(long, value_name = "PATH")]
    palette: PathBuf,

    /// The tilemap, one little-endian entry per cell
    #[arg(long, value_name = "PATH")]
    tilemap: PathBuf,

    /// How many cells wide the tilemap is
    #[arg(long, value_name = "N")]
    columns: usize,

    /// Where to write the PNG
    #[arg(short, long, value_name = "PATH")]
    output: PathBuf,

    /// Bits per pixel the tiles were packed at
    #[arg(long, value_name = "N", default_value_t = 4, value_parser = depth)]
    bpp: usize,
}

/// What fraction of the cells did not need a tile of their own, as a
/// percentage. Nothing to report about a picture with no cells.
fn reuse(tiles: usize, cells: usize) -> usize {
    match cells {
        0 => 0,
        _ => 100 - tiles * 100 / cells,
    }
}

/// 4 or 8, and nothing else: those are the two planar depths this writes.
fn depth(text: &str) -> std::result::Result<usize, String> {
    match text {
        "4" => Ok(4),
        "8" => Ok(8),
        other => Err(format!("{other}: the planar depths are 4 and 8")),
    }
}

fn write(path: &Path, data: &[u8]) -> Result<()> {
    if let Some(dir) = path.parent() {
        if !dir.as_os_str().is_empty() {
            std::fs::create_dir_all(dir)
                .map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
        }
    }
    std::fs::write(path, data).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn read(path: &Path) -> Result<Vec<u8>> {
    std::fs::read(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn do_convert(args: &Convert) -> Result<()> {
    let picture = image::read(&args.input)?;
    let options = Options {
        bpp: args.bpp,
        priority: u8::from(args.priority),
        max_tiles: args.max_tiles,
        blank_tile: !args.no_blank_tile,
    };
    if !args.animation_out.is_empty() && args.animation_out.len() != args.animation.len() {
        return Err(Bad::usage(format!(
            "{} --animation-out for {} --animation: one each, in the same order",
            args.animation_out.len(),
            args.animation.len()
        )));
    }
    let mut animations = Vec::with_capacity(args.animation.len());
    for list in &args.animation {
        let frames = list
            .split(',')
            .map(|path| image::read(Path::new(path)))
            .collect::<Result<Vec<_>>>()?;
        animations.push(frames);
    }
    let done = voodoo::convert(&picture, &animations, &options)?;
    for (path, animation) in args.animation_out.iter().zip(&done.animations) {
        write(path, &animation.frames.concat())?;
    }

    write(&args.output, &done.tiles)?;
    if let Some(path) = &args.palette {
        write(path, &done.cgram)?;
    }
    if let Some(path) = &args.tilemap {
        let mut bytes = Vec::with_capacity(done.report.cells * 2);
        for row in &done.tilemap {
            for cell in row {
                bytes.extend_from_slice(&cell.to_le_bytes());
            }
        }
        write(path, &bytes)?;
    }

    let r = &done.report;
    if args.json {
        println!(
            "{{\"output\": \"{}\", \"bpp\": {}, \"columns\": {}, \"rows\": {}, \
             \"cells\": {}, \"tiles\": {}, \"tile_bytes\": {}, \"palettes\": {}, \
             \"colors\": {}, \"animations\": [{}]}}",
            args.output.display(),
            args.bpp,
            r.columns,
            r.rows,
            r.cells,
            r.tiles,
            done.tiles.len(),
            r.palettes,
            r.colors,
            done.animations
                .iter()
                .map(|a| format!(
                    "{{\"first\": {}, \"tiles\": {}, \"frames\": {}}}",
                    a.first,
                    a.count,
                    a.frames.len()
                ))
                .collect::<Vec<_>>()
                .join(", ")
        );
    } else {
        println!(
            "{}: {}x{} cells, {} distinct tiles ({}% reuse), {} bytes",
            args.input.display(),
            r.columns,
            r.rows,
            r.tiles,
            reuse(r.tiles, r.cells),
            done.tiles.len()
        );
        println!(
            "  {} colours in {} palette(s) at {}bpp",
            r.colors, r.palettes, args.bpp
        );
        for (n, a) in done.animations.iter().enumerate() {
            println!(
                "  animation {n}: {} tiles from {}, {} frames",
                a.count,
                a.first,
                a.frames.len()
            );
        }
    }
    Ok(())
}

fn do_render(args: &Render) -> Result<()> {
    let data = read(&args.tiles)?;
    let palette_bytes = read(&args.palette)?;
    let map_bytes = read(&args.tilemap)?;
    if map_bytes.len() % 2 != 0 {
        return Err(Bad::usage(format!(
            "{}: {} bytes, and a tilemap entry is two",
            args.tilemap.display(),
            map_bytes.len()
        )));
    }
    let entries: Vec<u16> = map_bytes
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    if args.columns == 0 || !entries.len().is_multiple_of(args.columns) {
        return Err(Bad::usage(format!(
            "{} entries do not divide into rows of {}",
            entries.len(),
            args.columns
        )));
    }
    let mut colors = vec![None; ENTRIES];
    for (slot, word) in colors.iter_mut().zip(palette_bytes.chunks_exact(2)) {
        *slot = Some(color::from_cgram_word(u16::from_le_bytes([
            word[0], word[1],
        ])));
    }

    let bytes = args.bpp * CELL;
    let rows_of_cells = entries.len() / args.columns;
    let width = args.columns * CELL;
    let mut pixels = vec![0u8; width * rows_of_cells * CELL];
    for (index, cell) in entries.iter().enumerate() {
        let (cx, cy) = (index % args.columns, index / args.columns);
        let number = (cell & 0x03FF) as usize;
        let palette = ((cell >> 10) & 0x07) as usize;
        if (number + 1) * bytes > data.len() {
            return Err(Bad::usage(format!(
                "the tilemap points at tile {number} and {} holds {}",
                args.tiles.display(),
                data.len() / bytes
            )));
        }
        let indices = pack::unpack_tile(&data[number * bytes..(number + 1) * bytes], args.bpp);
        for y in 0..CELL {
            for x in 0..CELL {
                let sy = if cell & 0x8000 != 0 { CELL - 1 - y } else { y };
                let sx = if cell & 0x4000 != 0 { CELL - 1 - x } else { x };
                let mut value = indices[sy][sx] as usize;
                if args.bpp == 4 {
                    // A 4-bit index counts inside its own sixteen.
                    value += palette * COLORS_PER_PALETTE;
                }
                pixels[(cy * CELL + y) * width + cx * CELL + x] = value as u8;
            }
        }
    }
    let picture = Picture {
        width,
        height: rows_of_cells * CELL,
        pixels,
        colors,
    };
    image::write(&args.output, &picture)?;
    println!(
        "wrote {} ({}x{})",
        args.output.display(),
        picture.width,
        picture.height
    );
    Ok(())
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let outcome = match &cli.command {
        Command::Convert(a) => do_convert(a),
        Command::Render(a) => do_render(a),
    };
    match outcome {
        Ok(()) => ExitCode::SUCCESS,
        Err(Bad::Answer(message)) => {
            if !message.is_empty() {
                eprintln!("error: {message}");
            }
            ExitCode::from(NO)
        }
        Err(Bad::Usage(message)) => {
            eprintln!("error: {message}");
            ExitCode::from(MISUSE)
        }
    }
}
