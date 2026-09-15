//! Tiles from the command line: a picture in, tiles and palettes and a
//! tilemap out.
//!
//! Where the files go is the caller's business: nothing here has a default
//! path or a directory it knows about. What it does have opinions about is
//! saying no clearly — a picture that does not fit gets told which cell and by
//! how much, because the thing a caller does next is edit that cell.

use clap::{Args as ClapArgs, Parser, Subcommand};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use tiles::convert::{fits_per_palette, widest_cell, Options};
use tiles::fail::{Bad, Result};
use tiles::grid::{cut_tiles, tile_colors, Picture};
use tiles::palette::distinct_cells;
use tiles::{color, image, pack};

/// What the two exit codes mean, and why they are not the same.
///
/// "This cell has nineteen colours and fifteen fit" is this tool working
/// correctly and answering no; "that file is not a PNG" is the call being
/// wrong. A build script wants to tell those apart without reading the
/// message.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "tiles",
    about = "Cut a picture into 8x8 tiles, spread its colours over palettes, and pack \
             both the way a planar PPU reads them",
    after_help = "Exit codes: 1 the answer is no (it does not fit, it needs too many \
                  tiles), 2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// A picture into tiles, palettes and a tilemap
    Convert(Convert),
    /// What a picture would cost, without writing anything
    Inspect(Inspect),
    /// Tiles, palette and tilemap back into a picture, to look at what came out
    Render(Render),
}

#[derive(ClapArgs)]
#[command(after_help = "Mirrored cells are not new tiles: a tilemap entry carries an x \
                        and a y flip, so the four orientations are tried against the \
                        tiles already placed.\n\
                        At 4bpp the colours are spread over palettes so each cell uses \
                        only one; at 8bpp there is a single palette and an index reaches \
                        all of colour memory.\n\
                        Without --merge a picture that does not fit is refused rather \
                        than quietly made worse.")]
struct Convert {
    /// The PNG to convert
    input: PathBuf,

    /// Where to write the tile data
    #[arg(short, long, value_name = "PATH")]
    output: PathBuf,

    /// Where to write the palettes, as little-endian colour words
    #[arg(long, value_name = "PATH")]
    palette: Option<PathBuf>,

    /// Where to write the tilemap, one little-endian entry per cell
    #[arg(long, value_name = "PATH")]
    tilemap: Option<PathBuf>,

    /// Bits per pixel
    #[arg(long, value_name = "N", default_value_t = 4, value_parser = depth)]
    bpp: usize,

    /// At 4bpp, how many palettes may be used
    #[arg(long, value_name = "N", default_value_t = 8)]
    palettes: usize,

    /// At 8bpp, how many colours the palette may hold
    #[arg(long, value_name = "N", default_value_t = 255)]
    max_colors: usize,

    /// Which colour-memory entry each palette starts at; 0 is transparent
    #[arg(long, value_name = "N", default_value_t = 1)]
    base: u8,

    /// The palette number the tilemap's entries count from, at 4bpp
    #[arg(long, value_name = "N", default_value_t = 0)]
    first_palette: u8,

    /// Set the priority bit on every tilemap entry
    #[arg(long)]
    priority: bool,

    /// Give up the cheapest colours instead of refusing a picture that does
    /// not fit
    #[arg(long)]
    merge: bool,

    /// Refuse a picture needing more distinct tiles than this
    #[arg(long, value_name = "N", default_value_t = 1024)]
    max_tiles: usize,

    /// Do not keep tile 0 for the empty cell
    #[arg(long)]
    no_blank_tile: bool,

    /// Print what happened as JSON instead of prose
    #[arg(long)]
    json: bool,
}

#[derive(ClapArgs)]
struct Inspect {
    /// The PNG to look at
    input: PathBuf,

    /// The depth to answer for
    #[arg(long, value_name = "N", default_value_t = 4, value_parser = depth)]
    bpp: usize,

    /// At 4bpp, how many palettes to try to fit into
    #[arg(long, value_name = "N", default_value_t = 8)]
    palettes: usize,

    /// Print it as JSON
    #[arg(long)]
    json: bool,
}

#[derive(ClapArgs)]
#[command(after_help = "The inverse of `convert`, as far as the colours allow: what \
                        comes back is the 15-bit colour, not the original.")]
struct Render {
    /// The tile data
    tiles: PathBuf,

    /// The palettes, as little-endian colour words
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

    /// Which colour-memory entry each palette starts at
    #[arg(long, value_name = "N", default_value_t = 1)]
    base: u8,

    /// The palette number the tilemap's entries count from, at 4bpp
    #[arg(long, value_name = "N", default_value_t = 0)]
    first_palette: u8,
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
        palettes: args.palettes,
        max_colors: args.max_colors,
        base: args.base,
        first_palette: args.first_palette,
        priority: u8::from(args.priority),
        merge: args.merge,
        max_tiles: args.max_tiles,
        blank_tile: !args.no_blank_tile,
    };
    let done = tiles::convert(&picture, &options)?;

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
             \"colors\": {}, \"colors_before\": {}, \"merged\": {}}}",
            args.output.display(),
            args.bpp,
            r.columns,
            r.rows,
            r.cells,
            r.tiles,
            done.tiles.len(),
            r.palettes,
            r.colors_used,
            r.colors_before,
            r.merged
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
            "  {} colours in {} palette(s) at {}bpp{}",
            r.colors_used,
            r.palettes,
            args.bpp,
            if r.merged == 0 {
                String::new()
            } else {
                format!(", {} of {} merged away", r.merged, r.colors_before)
            }
        );
    }
    Ok(())
}

fn do_inspect(args: &Inspect) -> Result<()> {
    let picture = image::read(&args.input)?;
    let grid = cut_tiles(&picture);
    let colors: std::collections::BTreeSet<_> =
        grid.cells().flat_map(tile_colors).collect();
    let widest = widest_cell(&grid);
    let per_palette = fits_per_palette(args.bpp);
    let sets: std::collections::BTreeSet<_> = grid
        .cells()
        .map(tile_colors)
        .filter(|s| !s.is_empty())
        .collect();
    let packs = if args.bpp == 4 {
        tiles::try_pack(&sets, args.palettes, per_palette).map(|g| g.len())
    } else {
        (colors.len() <= per_palette).then_some(1)
    };

    if args.json {
        println!(
            "{{\"input\": \"{}\", \"width\": {}, \"height\": {}, \"columns\": {}, \
             \"rows\": {}, \"cells\": {}, \"distinct_cells\": {}, \"colors\": {}, \
             \"widest_cell\": {}, \"fits\": {}, \"palettes_needed\": {}}}",
            args.input.display(),
            picture.width,
            picture.height,
            grid.columns,
            grid.height(),
            grid.columns * grid.height(),
            distinct_cells(&grid),
            colors.len(),
            widest,
            packs.is_some(),
            packs.map_or(-1, |n| n as i64)
        );
    } else {
        println!(
            "{}: {}x{} pixels, {}x{} cells, {} distinct",
            args.input.display(),
            picture.width,
            picture.height,
            grid.columns,
            grid.height(),
            distinct_cells(&grid)
        );
        println!(
            "  {} colours, the busiest cell uses {}",
            colors.len(),
            widest
        );
        match packs {
            Some(n) => println!("  fits at {}bpp in {} palette(s)", args.bpp, n),
            None => println!(
                "  does not fit at {}bpp in {} palette(s) of {}",
                args.bpp, args.palettes, per_palette
            ),
        }
    }
    if packs.is_none() {
        return Err(Bad::answer(String::new()));
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
    let colors: Vec<_> = palette_bytes
        .chunks_exact(2)
        .map(|c| color::from_cgram_word(u16::from_le_bytes([c[0], c[1]])))
        .collect();

    let bytes = args.bpp * 8;
    let rows_of_cells = entries.len() / args.columns;
    let mut rows = vec![vec![None; args.columns * 8]; rows_of_cells * 8];
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
        for y in 0..8 {
            for x in 0..8 {
                let sy = if cell & 0x8000 != 0 { 7 - y } else { y };
                let sx = if cell & 0x4000 != 0 { 7 - x } else { x };
                let mut value = indices[sy][sx] as usize;
                if args.bpp == 4 {
                    // A 4bpp palette file is whole palettes of sixteen, so the
                    // index already counts from the start of its own.
                    if value == 0 {
                        continue;
                    }
                    value += palette.saturating_sub(args.first_palette as usize) * 16;
                } else {
                    // An 8bpp palette file is the run that gets loaded at
                    // --base, so the entries below it are not in the file.
                    if value < args.base as usize {
                        continue;
                    }
                    value -= args.base as usize;
                }
                rows[cy * 8 + y][cx * 8 + x] = colors.get(value).copied();
            }
        }
    }
    let picture = Picture {
        width: args.columns * 8,
        height: rows_of_cells * 8,
        rows,
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
        Command::Inspect(a) => do_inspect(a),
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
