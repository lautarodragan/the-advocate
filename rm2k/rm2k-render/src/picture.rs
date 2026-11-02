//! An RGBA picture, the one way pixels are copied onto it, and PNG in and out.
//!
//! Every drawing here is the same operation: copy a rectangle **through its
//! own alpha**, so a transparent pixel leaves what was underneath. The blend
//! is written the way the drawings this replaces computed it —integer, with
//! the rounding of a division by 255 done as `((v + 128) >> 8 + v + 128) >> 8`—
//! because the point of this crate is that its pixels are those, not close to
//! those. With a ChipSet whose alpha is only 0 or 255, which is every indexed
//! one, the blend is a plain copy and the rounding never comes into it.

use crate::fail::{Bad, Result};
pub use image::imageops::FilterType;
use image::{imageops, Rgba32FImage};
use std::path::Path;

/// Four bytes a pixel, rows top to bottom, no padding.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Picture {
    pub width: usize,
    pub height: usize,
    pub rgba: Vec<u8>,
}

impl Picture {
    /// A picture of one colour.
    pub fn filled(width: usize, height: usize, color: [u8; 4]) -> Self {
        Picture {
            width,
            height,
            rgba: color.repeat(width * height),
        }
    }

    /// A fully transparent picture: transparent black, all four bytes zero.
    pub fn transparent(width: usize, height: usize) -> Self {
        Self::filled(width, height, [0; 4])
    }

    /// The pixel at `(x, y)`. **Outside the picture it is transparent
    /// black**, not an error: cropping past the edge gives that, and the
    /// drawings rely on it for a tile id past the end of the atlas.
    pub fn get(&self, x: i64, y: i64) -> [u8; 4] {
        if x < 0 || y < 0 || x >= self.width as i64 || y >= self.height as i64 {
            return [0; 4];
        }
        let at = (y as usize * self.width + x as usize) * 4;
        [
            self.rgba[at],
            self.rgba[at + 1],
            self.rgba[at + 2],
            self.rgba[at + 3],
        ]
    }

    /// The `w`x`h` rectangle at `(x, y)`, as is: what falls outside the
    /// picture comes out transparent black, as [`get`](Self::get) says.
    pub fn crop(&self, x: i64, y: i64, w: usize, h: usize) -> Picture {
        let mut rgba = Vec::with_capacity(w * h * 4);
        for dy in 0..h as i64 {
            for dx in 0..w as i64 {
                rgba.extend_from_slice(&self.get(x + dx, y + dy));
            }
        }
        Picture {
            width: w,
            height: h,
            rgba,
        }
    }

    /// The same picture mirrored left to right: a face `ChangeFaceGraphic`
    /// flips, which RM2k draws with `Bitmap::FlipBlit`.
    pub fn mirrored(&self) -> Picture {
        let mut rgba = Vec::with_capacity(self.rgba.len());
        for y in 0..self.height {
            let row = &self.rgba[y * self.width * 4..(y + 1) * self.width * 4];
            for pixel in row.chunks_exact(4).rev() {
                rgba.extend_from_slice(pixel);
            }
        }
        Picture {
            width: self.width,
            height: self.height,
            rgba,
        }
    }

    /// Copies `src` over this one from its top left corner, ignoring alpha:
    /// what does not fit is cut, and what `src` does not cover is left alone.
    pub fn paste(&mut self, src: &Picture) {
        let width = self.width.min(src.width);
        for y in 0..self.height.min(src.height) {
            let to = y * self.width * 4;
            let from = y * src.width * 4;
            self.rgba[to..to + width * 4].copy_from_slice(&src.rgba[from..from + width * 4]);
        }
    }

    /// Copies all of `src` to `(dx, dy)`, ignoring alpha, like
    /// [`paste`](Self::paste) at an offset: what does not fit is cut.
    pub fn put(&mut self, dx: usize, dy: usize, src: &Picture) {
        if dx >= self.width || dy >= self.height {
            return;
        }
        let width = src.width.min(self.width - dx);
        for y in 0..src.height.min(self.height - dy) {
            let to = ((dy + y) * self.width + dx) * 4;
            let from = y * src.width * 4;
            self.rgba[to..to + width * 4].copy_from_slice(&src.rgba[from..from + width * 4]);
        }
    }

    /// Copies the `w`x`h` rectangle of `src` at `(sx, sy)` to `(dx, dy)`,
    /// **through its alpha**. The destination's edges clip it: a rectangle
    /// partly outside draws its inside part.
    #[allow(clippy::too_many_arguments)]
    pub fn blit(&mut self, dx: i64, dy: i64, src: &Picture, sx: i64, sy: i64, w: i64, h: i64) {
        let left = 0.max(-dx);
        let top = 0.max(-dy);
        let right = w - 0.max(dx + w - self.width as i64);
        let bottom = h - 0.max(dy + h - self.height as i64);
        if left >= right || top >= bottom {
            return;
        }
        for y in top..bottom {
            for x in left..right {
                let pixel = src.get(sx + x, sy + y);
                let alpha = pixel[3] as u32;
                if alpha == 0 {
                    continue;
                }
                let at = ((dy + y) as usize * self.width + (dx + x) as usize) * 4;
                for (channel, value) in pixel.iter().enumerate() {
                    let under = self.rgba[at + channel] as u32;
                    self.rgba[at + channel] = blend(alpha, under, *value as u32);
                }
            }
        }
    }

    /// This picture resized to `width` x `height` with `filter`, by the
    /// `image` crate. The same size gives a copy.
    ///
    /// `imageops::resize` takes the alpha as already premultiplied and says
    /// so, so the colour is multiplied by it before and divided back after
    /// —in `f32`, so the trip does not round— and a transparent pixel does
    /// not bleed its colour into its neighbours. A pixel that ends fully
    /// transparent comes out transparent black.
    pub fn resized(&self, width: usize, height: usize, filter: FilterType) -> Picture {
        if (width, height) == (self.width, self.height) {
            return self.clone();
        }
        let premultiplied: Vec<f32> = self
            .rgba
            .chunks_exact(4)
            .flat_map(|p| {
                let a = p[3] as f32 / 255.0;
                [
                    p[0] as f32 / 255.0 * a,
                    p[1] as f32 / 255.0 * a,
                    p[2] as f32 / 255.0 * a,
                    a,
                ]
            })
            .collect();
        let source = Rgba32FImage::from_raw(self.width as u32, self.height as u32, premultiplied)
            .expect("four floats a pixel");
        let resized = imageops::resize(&source, width as u32, height as u32, filter);
        let byte = |v: f32| (v * 255.0).round().clamp(0.0, 255.0) as u8;
        let rgba = resized
            .pixels()
            .flat_map(|p| {
                let [r, g, b, a] = p.0;
                if byte(a) == 0 {
                    [0; 4]
                } else {
                    [byte(r / a), byte(g / a), byte(b / a), byte(a)]
                }
            })
            .collect();
        Picture {
            width,
            height,
            rgba,
        }
    }
}

/// `under` and `over` mixed by `alpha` out of 255, rounded the way the
/// drawings this replaces round it.
fn blend(alpha: u32, under: u32, over: u32) -> u8 {
    let tmp = under * (255 - alpha) + over * alpha + 128;
    (((tmp >> 8) + tmp) >> 8) as u8
}

fn open(path: &Path) -> Result<png::Reader<std::io::BufReader<std::fs::File>>> {
    let file =
        std::fs::File::open(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
    decoder.set_transformations(png::Transformations::IDENTITY);
    decoder
        .read_info()
        .map_err(|e| Bad::answer(format!("{}: not a PNG this can read: {e}", path.display())))
}

/// A ChipSet —or any RM2k picture— as RGBA, with its colour key applied.
///
/// **In an indexed picture, index 0 is the colour key**, whatever the file's
/// own transparency says: it is how RM2k draws them, and every ChipSet of
/// the game and of the RTP is indexed. The other kinds keep the transparency
/// the file declares, if any. A BMP, which RM2k takes in every folder, is
/// read here too, and is always indexed: see [`read_bmp`].
pub fn read_rm2k(path: &Path) -> Result<Picture> {
    read(path, true)
}

/// Like [`read_rm2k`], but with index 0 of an indexed picture as opaque as
/// the others: a `ShowPicture` without its transparent colour is drawn so.
pub fn read_unkeyed(path: &Path) -> Result<Picture> {
    read(path, false)
}

fn read(path: &Path, key: bool) -> Result<Picture> {
    if path
        .extension()
        .map(|e| e.eq_ignore_ascii_case("bmp"))
        .unwrap_or(false)
    {
        return read_bmp(path, key);
    }
    let mut reader = open(path)?;
    let mut buffer = vec![0; reader.output_buffer_size()];
    let frame = reader
        .next_frame(&mut buffer)
        .map_err(|e| Bad::answer(format!("{}: {e}", path.display())))?;
    let info = reader.info();
    let (width, height) = (frame.width as usize, frame.height as usize);
    let depth = frame.bit_depth as usize;
    let unsupported = || {
        Bad::answer(format!(
            "{}: {:?} at {} bits, and this reads indexed PNGs, or grey, RGB or RGBA at 8 bits",
            path.display(),
            frame.color_type,
            depth
        ))
    };
    let mut rgba = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        let line = &buffer[y * frame.line_size..(y + 1) * frame.line_size];
        for x in 0..width {
            let pixel = match (frame.color_type, depth) {
                (png::ColorType::Indexed, 1 | 2 | 4 | 8) => {
                    let per_byte = 8 / depth;
                    let byte = line[x / per_byte];
                    let shift = 8 - depth * (x % per_byte + 1);
                    let index = ((byte >> shift) as usize) & ((1 << depth) - 1);
                    let palette = info.palette.as_deref().unwrap_or(&[]);
                    let rgb = palette.get(index * 3..index * 3 + 3).unwrap_or(&[0, 0, 0]);
                    [
                        rgb[0],
                        rgb[1],
                        rgb[2],
                        if key && index == 0 { 0 } else { 255 },
                    ]
                }
                (png::ColorType::Grayscale, 8) => {
                    let g = line[x];
                    [g, g, g, keyed(info.trns.as_deref(), &[g])]
                }
                (png::ColorType::GrayscaleAlpha, 8) => {
                    let g = line[x * 2];
                    [g, g, g, line[x * 2 + 1]]
                }
                (png::ColorType::Rgb, 8) => {
                    let p = &line[x * 3..x * 3 + 3];
                    [p[0], p[1], p[2], keyed(info.trns.as_deref(), p)]
                }
                (png::ColorType::Rgba, 8) => {
                    let p = &line[x * 4..x * 4 + 4];
                    [p[0], p[1], p[2], p[3]]
                }
                _ => return Err(unsupported()),
            };
            rgba.extend_from_slice(&pixel);
        }
    }
    Ok(Picture {
        width,
        height,
        rgba,
    })
}

/// A BMP as RM2k takes them: indexed, at 1, 4 or 8 bits, uncompressed, with
/// index 0 as the colour key as in an indexed PNG. Read by hand and not with
/// `image`, whose BMP decoder hands back colours and loses the index, and
/// with it the key: two entries of a palette can be the same colour. The
/// header is the old core one or any of the Windows ones, rows bottom to top
/// or, with a negative height, top to bottom, each padded to four bytes.
/// EasyRPG reads them the same way (`ImageBMP`), and refuses compressed ones
/// too.
fn read_bmp(path: &Path, key: bool) -> Result<Picture> {
    let data = std::fs::read(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let bad = |what: String| Bad::answer(format!("{}: {what}", path.display()));
    let short = || bad("cut short, not a BMP this can read".to_string());
    let u16_at = |at: usize| {
        data.get(at..at + 2)
            .map(|b| u16::from_le_bytes([b[0], b[1]]))
    };
    let u32_at = |at: usize| {
        data.get(at..at + 4)
            .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    };
    if !data.starts_with(b"BM") {
        return Err(bad("not a BMP".to_string()));
    }
    let bits = u32_at(10).ok_or_else(short)? as usize;
    let header = u32_at(14).ok_or_else(short)? as usize;
    // (width, height, depth, compression, colours, bytes a palette entry);
    // 12 bytes is the OS/2 core header, any other size a Windows one.
    let (width, height, depth, compression, colors, entry) = if header == 12 {
        let (w, h) = (u16_at(18).ok_or_else(short)?, u16_at(20).ok_or_else(short)?);
        let depth = u16_at(24).ok_or_else(short)? as usize;
        (w as i64, h as i16 as i64, depth, 0, 0, 3)
    } else {
        let w = u32_at(18).ok_or_else(short)? as i32 as i64;
        let h = u32_at(22).ok_or_else(short)? as i32 as i64;
        let depth = u16_at(28).ok_or_else(short)? as usize;
        let compression = u32_at(30).ok_or_else(short)?;
        let colors = u32_at(46).ok_or_else(short)? as usize;
        (w, h, depth, compression, colors, 4)
    };
    if !matches!(depth, 1 | 4 | 8) {
        return Err(bad(format!(
            "a BMP at {depth} bits, and RM2k's are indexed, at 8 bits or fewer"
        )));
    }
    if compression != 0 {
        return Err(bad(format!(
            "a compressed BMP (method {compression}), and this reads uncompressed ones only"
        )));
    }
    // 0 colours in the header means as many as the depth gives.
    let colors = if colors == 0 {
        1 << depth
    } else {
        colors.min(256)
    };
    let table = data
        .get(14 + header..14 + header + colors * entry)
        .ok_or_else(short)?;
    // Stored blue, green, red.
    let palette: Vec<[u8; 3]> = table.chunks(entry).map(|c| [c[2], c[1], c[0]]).collect();
    let top_down = height < 0;
    let (width, height) = (width.max(0) as usize, height.unsigned_abs() as usize);
    let row = (width * depth).div_ceil(32) * 4;
    let rows = data.get(bits..bits + row * height).ok_or_else(short)?;
    let mut rgba = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        let stored = if top_down { y } else { height - 1 - y };
        let line = &rows[stored * row..(stored + 1) * row];
        for x in 0..width {
            let bit = x * depth;
            let index = ((line[bit / 8] >> (8 - depth - bit % 8)) as usize) & ((1 << depth) - 1);
            let [r, g, b] = palette.get(index).copied().unwrap_or([0, 0, 0]);
            rgba.extend_from_slice(&[r, g, b, if key && index == 0 { 0 } else { 255 }]);
        }
    }
    Ok(Picture {
        width,
        height,
        rgba,
    })
}

/// The alpha of a grey or RGB pixel against the file's transparent colour,
/// which PNG writes as one 16-bit sample per channel.
fn keyed(trns: Option<&[u8]>, samples: &[u8]) -> u8 {
    match trns {
        Some(key) if key.len() == samples.len() * 2 => {
            let same = samples
                .iter()
                .enumerate()
                .all(|(i, s)| u16::from_be_bytes([key[i * 2], key[i * 2 + 1]]) == *s as u16);
            if same {
                0
            } else {
                255
            }
        }
        _ => 255,
    }
}

/// Reads back a PNG this crate wrote: RGBA at 8 bits and nothing else.
pub fn read_rgba(path: &Path) -> Result<Picture> {
    let mut reader = open(path)?;
    let mut buffer = vec![0; reader.output_buffer_size()];
    let frame = reader
        .next_frame(&mut buffer)
        .map_err(|e| Bad::answer(format!("{}: {e}", path.display())))?;
    if frame.color_type != png::ColorType::Rgba || frame.bit_depth != png::BitDepth::Eight {
        return Err(Bad::answer(format!(
            "{}: not an RGBA PNG at 8 bits",
            path.display()
        )));
    }
    buffer.truncate(frame.buffer_size());
    Ok(Picture {
        width: frame.width as usize,
        height: frame.height as usize,
        rgba: buffer,
    })
}

/// The picture as an RGBA PNG at 8 bits.
///
/// Fast compression: these are read once, by whoever asked for them, and
/// then thrown away, so the bytes saved by compressing harder are not worth
/// the time on a big map.
pub fn write_png(path: &Path, picture: &Picture) -> Result<()> {
    let file =
        std::fs::File::create(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut encoder = png::Encoder::new(
        std::io::BufWriter::new(file),
        picture.width as u32,
        picture.height as u32,
    );
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_compression(png::Compression::Fast);
    let failed = |e: png::EncodingError| Bad::usage(format!("{}: {e}", path.display()));
    let mut writer = encoder.write_header().map_err(failed)?;
    writer.write_image_data(&picture.rgba).map_err(failed)?;
    writer.finish().map_err(failed)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A picture of noise from a congruence, with fully transparent, fully
    /// opaque and translucent pixels.
    fn noise(width: usize, height: usize) -> Picture {
        let mut x: u64 = 12345;
        let rgba = (0..width * height * 4)
            .map(|i| {
                x = (x * 1103515245 + 12345) % (1 << 31);
                let b = (x >> 16) as u8;
                match (i % 4, b) {
                    (3, 0..=63) => 0,
                    (3, 192..) => 255,
                    _ => b,
                }
            })
            .collect();
        Picture {
            width,
            height,
            rgba,
        }
    }

    const FILTERS: [FilterType; 2] = [FilterType::Lanczos3, FilterType::Triangle];
    const SIZES: [(usize, usize); 4] = [(256, 224), (64, 49), (1, 1), (400, 300)];

    #[test]
    fn the_same_size_is_a_copy() {
        let picture = noise(37, 23);
        for filter in FILTERS {
            assert_eq!(picture.resized(37, 23, filter), picture);
        }
    }

    #[test]
    fn it_comes_out_at_the_size_asked() {
        let picture = noise(320, 240);
        for filter in FILTERS {
            for (w, h) in SIZES {
                let resized = picture.resized(w, h, filter);
                assert_eq!((resized.width, resized.height), (w, h));
                assert_eq!(resized.rgba.len(), w * h * 4);
            }
        }
    }

    #[test]
    fn a_flat_picture_stays_flat() {
        let picture = Picture::filled(320, 240, [9, 120, 250, 255]);
        for filter in FILTERS {
            for (w, h) in SIZES {
                assert_eq!(
                    picture.resized(w, h, filter),
                    Picture::filled(w, h, [9, 120, 250, 255])
                );
            }
        }
    }

    /// Opaque blue next to fully transparent red: premultiplied, the red
    /// weighs nothing, so not a pixel with any alpha gets any red.
    #[test]
    fn a_transparent_pixel_does_not_bleed() {
        let mut picture = Picture::filled(40, 40, [255, 0, 0, 0]);
        for y in 0..40 {
            for x in 0..20 {
                let at = (y * 40 + x) * 4;
                picture.rgba[at..at + 4].copy_from_slice(&[0, 0, 255, 255]);
            }
        }
        for filter in FILTERS {
            for (w, h) in [(25, 25), (64, 64), (7, 40)] {
                for p in picture.resized(w, h, filter).rgba.chunks_exact(4) {
                    assert!(p[0] == 0 && p[1] == 0, "{filter:?}: {p:?}");
                }
            }
        }
    }

    /// Bilinear weights are never negative, so no channel lands outside
    /// what the picture had.
    #[test]
    fn bilinear_stays_inside_the_pictures_range() {
        let picture = Picture {
            width: 3,
            height: 2,
            rgba: [
                [40, 90, 200, 255],
                [60, 80, 210, 255],
                [50, 100, 190, 255],
                [45, 85, 205, 255],
                [55, 95, 195, 255],
                [42, 99, 201, 255],
            ]
            .concat(),
        };
        for (w, h) in [(7, 5), (2, 1), (30, 20)] {
            for p in picture
                .resized(w, h, FilterType::Triangle)
                .rgba
                .chunks_exact(4)
            {
                assert!((40..=60).contains(&p[0]), "{p:?}");
                assert!((80..=100).contains(&p[1]), "{p:?}");
                assert!((190..=210).contains(&p[2]), "{p:?}");
                assert_eq!(p[3], 255);
            }
        }
    }
}
