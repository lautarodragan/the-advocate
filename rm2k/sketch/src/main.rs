//! `rm2k-sketch <sketch.toml> <MapNNNN.tiles>`: a map sketched as text into
//! the `.tiles` of a Ditto dump. See `lib.rs` for what a sketch is.

use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let [sketch, tiles] = args.as_slice() else {
        eprintln!(
            "usage: rm2k-sketch <sketch.toml> <MapNNNN.tiles>\n\n\
             Draws a map's two tile layers from a grid of characters and a\n\
             legend of which tiles each one stands for, and writes them as\n\
             the .tiles that `ditto pack` reads beside the map's JSON."
        );
        return ExitCode::from(2);
    };
    let layers = match std::fs::read_to_string(sketch)
        .map_err(|e| e.to_string())
        .and_then(|text| rm2k_sketch::read(&text).map_err(|e| e.to_string()))
    {
        Ok(layers) => layers,
        Err(e) => {
            eprintln!("rm2k-sketch: {sketch}: {e}");
            return ExitCode::FAILURE;
        }
    };
    if let Err(e) = std::fs::write(tiles, layers.tiles()) {
        eprintln!("rm2k-sketch: {tiles}: {e}");
        return ExitCode::FAILURE;
    }
    ExitCode::SUCCESS
}
