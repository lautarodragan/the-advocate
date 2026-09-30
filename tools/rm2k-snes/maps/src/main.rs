//! A game's maps from the command line: a dump and a request in, what the
//! cartridge carries of a map out.
//!
//! Where the dump and the pictures are is the caller's to say: nothing here
//! has a default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_snes_maps::{layers, request, Bad, Game, LayersRequest, Result};
use std::path::PathBuf;
use std::process::ExitCode;

/// "The map's colours cannot be split" is this tool answering no; "that
/// flag makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-maps",
    about = "An RPG Maker 2000 game's maps, for a Super Nintendo cartridge",
    after_help = "Exit codes: 1 the answer is no (it does not fit, the dump is broken), 2 bad \
                  usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// A map's two background layers, in mode 3
    Layers(LayersArgs),
}

/// Where the game is: the dump, and where its pictures are.
#[derive(ClapArgs)]
struct Where {
    /// The Ditto dump the game is read from: the directory with maps/ and
    /// db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    /// A directory the pictures are looked up in —with ChipSet/, CharSet/
    /// inside—. Repeat it: the first one that has a picture wins
    #[arg(long = "search-dir", value_name = "DIRECTORY")]
    search_dirs: Vec<PathBuf>,

    /// What the cartridge decided about the map
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(after_help = "Writes into --out:\n  \
    background.bin      the layer behind the hero's tiles, at 8bpp\n  \
    above.bin           the layer in front of it's tiles, at 4bpp\n  \
    above-cgram.bin     that layer's palettes, from the first it takes\n  \
    run-<family>-<d>.bin  drawing d of each run of the ChipSet's animation\n  \
    <name>.png          what Adeleine decided, as indexed pictures whose \
                        indices are colour-memory entries: background, above, \
                        and each family's other drawings\n  \
    layers.json         the rest: the background's colour-memory words and \
                        tilemap, its colours, budget and merges, its runs; \
                        the layer above's tilemap, first palette and merges; \
                        and the pictures\n\n\
    The request is a JSON with `map` (its number), `map_files` and \
    `chipset_files` (the project's maps and ChipSets, by number, over the \
    dump's) and `baked` (cells of the upper layer painted over, as [cell, \
    tile id]).")]
struct LayersArgs {
    #[command(flatten)]
    place: Where,
}

fn game(place: &Where) -> Result<(Game, serde_json::Value, String)> {
    let (data, whose) = request::read(&place.request)?;
    let mut game = Game {
        data: place.data.clone(),
        search_dirs: place.search_dirs.clone(),
        ..Game::default()
    };
    request::patches(&data, &whose, &mut game)?;
    Ok((game, data, whose))
}

fn do_layers(args: &LayersArgs) -> Result<()> {
    let (game, data, whose) = game(&args.place)?;
    let request = LayersRequest::from_json(&data, &whose)?;
    layers::run(&game, &request, &args.place.out)
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Layers(args) => do_layers(args),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-snes-maps: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
