//! A BMP and the same drawing as a PNG read the same: RM2k takes both, in
//! every folder, and index 0 is the colour key in both.

use rm2k_render::picture;
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-render-bmp-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// Index 0 and index 1 are the same colour, so a key by colour and a key by
/// index come out different.
fn palette(colors: usize) -> Vec<[u8; 3]> {
    (0..colors)
        .map(|i| match i {
            0 | 1 => [10, 200, 30],
            _ => [
                (i * 53 % 256) as u8,
                (i * 29 % 256) as u8,
                (i * 197 % 256) as u8,
            ],
        })
        .collect()
}

fn pixel(x: usize, y: usize, colors: usize) -> u8 {
    ((x * 7 + y * 3 + x * y) % colors) as u8
}

fn png(path: &Path, width: usize, height: usize, colors: usize) {
    let mut encoder = png::Encoder::new(
        std::fs::File::create(path).unwrap(),
        width as u32,
        height as u32,
    );
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_palette(palette(colors).concat());
    let pixels: Vec<u8> = (0..height)
        .flat_map(|y| (0..width).map(move |x| pixel(x, y, colors)))
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

/// An uncompressed BMP with a BITMAPINFOHEADER, at `depth` bits, rows
/// bottom to top unless `top_down`, each padded to four bytes.
fn bmp(path: &Path, width: usize, height: usize, depth: usize, top_down: bool) {
    let colors = 1 << depth;
    let row = (width * depth).div_ceil(32) * 4;
    let mut rows = vec![0u8; row * height];
    for y in 0..height {
        let stored = if top_down { y } else { height - 1 - y };
        for x in 0..width {
            let index = pixel(x, y, colors);
            let bit = x * depth;
            rows[stored * row + bit / 8] |= index << (8 - depth - bit % 8);
        }
    }
    let table: Vec<u8> = palette(colors)
        .iter()
        .flat_map(|[r, g, b]| [*b, *g, *r, 0])
        .collect();
    let offset = 14 + 40 + table.len();
    let mut file = Vec::new();
    file.extend_from_slice(b"BM");
    file.extend_from_slice(&((offset + rows.len()) as u32).to_le_bytes());
    file.extend_from_slice(&[0; 4]);
    file.extend_from_slice(&(offset as u32).to_le_bytes());
    file.extend_from_slice(&40u32.to_le_bytes());
    file.extend_from_slice(&(width as i32).to_le_bytes());
    let h = if top_down {
        -(height as i32)
    } else {
        height as i32
    };
    file.extend_from_slice(&h.to_le_bytes());
    file.extend_from_slice(&1u16.to_le_bytes());
    file.extend_from_slice(&(depth as u16).to_le_bytes());
    file.extend_from_slice(&0u32.to_le_bytes());
    file.extend_from_slice(&(rows.len() as u32).to_le_bytes());
    file.extend_from_slice(&[0; 8]);
    file.extend_from_slice(&0u32.to_le_bytes());
    file.extend_from_slice(&0u32.to_le_bytes());
    file.extend_from_slice(&table);
    file.extend_from_slice(&rows);
    std::fs::write(path, file).unwrap();
}

#[test]
fn a_bmp_reads_as_the_same_drawing_in_png() {
    let dir = scratch("same");
    // Odd widths, so the rows carry padding and a half-used byte.
    for (depth, width, top_down) in [
        (8, 37, false),
        (4, 37, false),
        (1, 21, false),
        (8, 13, true),
    ] {
        let (height, colors) = (11, 1usize << depth);
        let name = format!("{depth}-{width}-{top_down}");
        let png_path = dir.join(format!("{name}.png"));
        let bmp_path = dir.join(format!("{name}.BMP"));
        png(&png_path, width, height, colors);
        bmp(&bmp_path, width, height, depth, top_down);
        let keyed = picture::read_rm2k(&bmp_path).unwrap();
        assert_eq!(
            keyed,
            picture::read_rm2k(&png_path).unwrap(),
            "{name}, keyed"
        );
        assert_eq!(
            picture::read_unkeyed(&bmp_path).unwrap(),
            picture::read_unkeyed(&png_path).unwrap(),
            "{name}, unkeyed"
        );
        // The key is the index, not the colour: index 1 has index 0's colour
        // and stays opaque.
        for (at, p) in keyed.rgba.chunks(4).enumerate() {
            let index = pixel(at % width, at / width, colors);
            assert_eq!(p[3], if index == 0 { 0 } else { 255 }, "{name}, pixel {at}");
        }
    }
}

#[test]
fn a_compressed_bmp_is_refused() {
    let dir = scratch("rle");
    let path = dir.join("rle.bmp");
    bmp(&path, 8, 2, 8, false);
    let mut bytes = std::fs::read(&path).unwrap();
    bytes[30] = 1; // BI_RLE8
    std::fs::write(&path, bytes).unwrap();
    let error = picture::read_rm2k(&path).unwrap_err();
    assert!(format!("{error:?}").contains("compress"), "{error:?}");
}
