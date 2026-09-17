//! Reading an indexed PNG in, and writing one back out.
//!
//! Only PNG, and only indexed at eight bits: the index **is** the
//! colour-memory entry, so a picture that is not indexed has not had its
//! palettes chosen yet, and choosing them is not this tool's job. Eight bits
//! and not fewer because an index has to reach all 256 entries, and a 4-bit
//! file could only name the first sixteen.

use crate::color::{expand, quantize, Rgb15};
use crate::fail::{Bad, Result};
use crate::grid::{Picture, ENTRIES};
use std::path::Path;

/// Read an 8-bit indexed PNG: its indices, and its palette at 15 bits.
pub fn read(path: &Path) -> Result<Picture> {
    let file = std::fs::File::open(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
    decoder.set_transformations(png::Transformations::IDENTITY);
    let mut reader = decoder
        .read_info()
        .map_err(|e| Bad::usage(format!("{}: not a PNG this can read: {e}", path.display())))?;

    let info = reader.info();
    if info.color_type != png::ColorType::Indexed || info.bit_depth != png::BitDepth::Eight {
        return Err(Bad::usage(format!(
            "{}: {:?} at {:?} bits, and this reads indexed PNGs at 8 bits: their indices \
             are colour-memory entries, which is how the palettes arrive already chosen",
            path.display(),
            info.color_type,
            info.bit_depth as u8
        )));
    }
    let mut colors = vec![None; ENTRIES];
    if let Some(palette) = &info.palette {
        for (entry, rgb) in palette.chunks_exact(3).enumerate().take(ENTRIES) {
            colors[entry] = Some(quantize(rgb[0], rgb[1], rgb[2]));
        }
    }

    let mut buffer = vec![0; reader.output_buffer_size()];
    let frame = reader
        .next_frame(&mut buffer)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let width = frame.width as usize;
    let height = frame.height as usize;
    let mut pixels = Vec::with_capacity(width * height);
    for y in 0..height {
        let start = y * frame.line_size;
        pixels.extend_from_slice(&buffer[start..start + width]);
    }
    Ok(Picture {
        width,
        height,
        pixels,
        colors,
    })
}

/// Write an indexed PNG, with the 5-bit channels put back in the top five
/// bits of each byte, and entries the picture has no colour for as black.
pub fn write(path: &Path, picture: &Picture) -> Result<()> {
    let file = std::fs::File::create(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut encoder = png::Encoder::new(
        std::io::BufWriter::new(file),
        picture.width as u32,
        picture.height as u32,
    );
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    let mut palette = Vec::with_capacity(3 * ENTRIES);
    for color in &picture.colors {
        let (r, g, b) = expand(color.unwrap_or((0, 0, 0)));
        palette.extend_from_slice(&[r, g, b]);
    }
    encoder.set_palette(palette);
    let mut writer = encoder
        .write_header()
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    writer
        .write_image_data(&picture.pixels)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

/// The colour of an entry, for callers that build a picture in memory.
pub fn palette_of(colors: &[(usize, Rgb15)]) -> Vec<Option<Rgb15>> {
    let mut out = vec![None; ENTRIES];
    for &(entry, color) in colors {
        out[entry] = Some(color);
    }
    out
}
