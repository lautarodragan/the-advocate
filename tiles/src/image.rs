//! Reading a PNG in, and writing one back out.
//!
//! Only PNG, and deliberately: this reads one format well rather than six
//! badly, and a caller with something else has a converter already.

use crate::color::{quantize_pixel, Pixel, Rgb15};
use crate::fail::{Bad, Result};
use crate::grid::Picture;
use std::path::Path;

/// Read a PNG and quantise it to what the hardware can show.
///
/// Whatever the file's colour type, it arrives here as RGBA and leaves as
/// 15-bit colour with a hard transparent/opaque split, because that is what
/// every later decision has to be made on: two colours the display cannot tell
/// apart must not be counted as two.
pub fn read(path: &Path) -> Result<Picture> {
    let file = std::fs::File::open(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder
        .read_info()
        .map_err(|e| Bad::usage(format!("{}: not a PNG this can read: {e}", path.display())))?;

    let mut buffer = vec![0; reader.output_buffer_size()];
    let info = reader
        .next_frame(&mut buffer)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;

    let width = info.width as usize;
    let height = info.height as usize;
    let channels = match info.color_type {
        png::ColorType::Grayscale => 1,
        png::ColorType::GrayscaleAlpha => 2,
        png::ColorType::Rgb => 3,
        png::ColorType::Rgba => 4,
        png::ColorType::Indexed => {
            return Err(Bad::usage(format!(
                "{}: the palette could not be expanded",
                path.display()
            )))
        }
    };

    let mut rows = Vec::with_capacity(height);
    for y in 0..height {
        let start = y * info.line_size;
        let mut row = Vec::with_capacity(width);
        for x in 0..width {
            let p = &buffer[start + x * channels..start + (x + 1) * channels];
            let (r, g, b, a) = match channels {
                1 => (p[0], p[0], p[0], 255),
                2 => (p[0], p[0], p[0], p[1]),
                3 => (p[0], p[1], p[2], 255),
                _ => (p[0], p[1], p[2], p[3]),
            };
            row.push(quantize_pixel(r, g, b, a));
        }
        rows.push(row);
    }
    Ok(Picture {
        width,
        height,
        rows,
    })
}

/// Write a picture back out as an RGBA PNG, with the 5-bit channels put back
/// in the top five bits of each byte.
pub fn write(path: &Path, picture: &Picture) -> Result<()> {
    let file = std::fs::File::create(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut encoder = png::Encoder::new(
        std::io::BufWriter::new(file),
        picture.width as u32,
        picture.height as u32,
    );
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder
        .write_header()
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;

    let mut data = Vec::with_capacity(picture.width * picture.height * 4);
    for row in &picture.rows {
        for pixel in row {
            data.extend_from_slice(&rgba(*pixel));
        }
    }
    writer
        .write_image_data(&data)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

/// A 15-bit colour back to eight bits a channel. The five bits go to the top,
/// so 31 comes back as 248 and not as 31: the alternative would make every
/// picture that goes through here noticeably darker.
pub fn rgba(pixel: Pixel) -> [u8; 4] {
    match pixel {
        None => [0, 0, 0, 0],
        Some((r, g, b)) => [r << 3, g << 3, b << 3, 255],
    }
}

/// A picture made of nothing but the given rows, for callers building one.
pub fn picture_of(width: usize, rows: Vec<Vec<Pixel>>) -> Picture {
    Picture {
        height: rows.len(),
        width,
        rows,
    }
}

/// The colour a 15-bit value shows as, for a caller writing its own output.
pub fn shown(color: Rgb15) -> (u8, u8, u8) {
    (color.0 << 3, color.1 << 3, color.2 << 3)
}
