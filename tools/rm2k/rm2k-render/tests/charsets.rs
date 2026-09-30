//! The CharSet sheets against the ones they replace.
//!
//! Until `charset` existed, the same sheets were drawn by the Python of the
//! converter. It was deleted once the two gave the same pixels on every
//! CharSet a whole game draws; what is left of it is here: the SHA-256 of
//! what it drew for CharSets, ChipSets and a background generated inside
//! this file, which need no game and no RTP.
//!
//! The inputs touch what can differ: an indexed CharSet —the colour key at
//! index 0— and an RGBA one with half-transparent pixels; tiles of an
//! indexed ChipSet and of a half-transparent one, whose two copies each
//! round; and translucent sheets on cells in the middle of the background
//! and against its edges, where what is behind is black.
//!
//! **If one of these changes, a pixel changed.** The hashes are not to be
//! regenerated to make a test pass: the Python that produced them is gone,
//! and with it the only independent answer.

mod common;

use common::{indexed_chipset, rgba_chipset, sha};
use rm2k_render::charset::{tile_sheet, translucent, SHEET_HEIGHT, SHEET_WIDTH};
use rm2k_render::{picture, Picture};
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-render-charsets-{}-{name}",
        std::process::id()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// An indexed CharSet: a quarter of it the colour key, the rest from a
/// formula.
fn indexed_charset(path: &Path) {
    let mut encoder = png::Encoder::new(
        std::fs::File::create(path).unwrap(),
        SHEET_WIDTH as u32,
        SHEET_HEIGHT as u32,
    );
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    let palette: Vec<u8> = (0..256usize)
        .flat_map(|i| {
            [
                (i * 53 % 256) as u8,
                (i * 29 % 256) as u8,
                (i * 197 % 256) as u8,
            ]
        })
        .collect();
    encoder.set_palette(palette);
    let pixels: Vec<u8> = (0..SHEET_HEIGHT)
        .flat_map(|y| {
            (0..SHEET_WIDTH).map(move |x| {
                if (x + y) % 4 == 0 {
                    0
                } else {
                    ((x * 11 + y * 5 + (x / 7) * (y / 4)) % 256) as u8
                }
            })
        })
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

/// An RGBA CharSet with half-transparent pixels.
fn rgba_charset(path: &Path) {
    const ALPHAS: [u8; 4] = [0, 255, 90, 255];
    let mut rgba = Vec::with_capacity(SHEET_WIDTH * SHEET_HEIGHT * 4);
    for y in 0..SHEET_HEIGHT {
        for x in 0..SHEET_WIDTH {
            rgba.extend_from_slice(&[
                (x * 5 % 256) as u8,
                (y * 3 % 256) as u8,
                ((x * y) % 256) as u8,
                ALPHAS[(x + 3 * y) % 4],
            ]);
        }
    }
    let picture = Picture {
        width: SHEET_WIDTH,
        height: SHEET_HEIGHT,
        rgba,
    };
    picture::write_png(path, &picture).unwrap();
}

/// What is behind: 6 cells by 5, opaque, as a map's lower layer is.
fn behind() -> Picture {
    let (width, height) = (96, 80);
    let rgba = (0..height)
        .flat_map(|y: usize| {
            (0..width).flat_map(move |x: usize| {
                [
                    (x * 9 % 256) as u8,
                    (y * 7 % 256) as u8,
                    ((x + 2 * y) % 256) as u8,
                    255,
                ]
            })
        })
        .collect();
    Picture {
        width,
        height,
        rgba,
    }
}

#[test]
fn the_sheets_are_what_the_python_drew() {
    let dir = scratch("python");
    let read = |name: &str, write: fn(&Path)| {
        let path = dir.join(name);
        write(&path);
        picture::read_rm2k(&path).unwrap()
    };
    let indexed = read("indexed-charset.png", indexed_charset);
    let rgba = read("rgba-charset.png", rgba_charset);
    let indexed_chip = read("indexed-chipset.png", indexed_chipset);
    let rgba_chip = read("rgba-chipset.png", rgba_chipset);
    let behind = behind();
    let rgba_tile = tile_sheet(&rgba_chip, 7);

    let got = [
        ("indexed CharSet", sha(&indexed)),
        ("RGBA CharSet", sha(&rgba)),
        ("indexed tile 0", sha(&tile_sheet(&indexed_chip, 0))),
        ("indexed tile 5", sha(&tile_sheet(&indexed_chip, 5))),
        ("indexed tile 143", sha(&tile_sheet(&indexed_chip, 143))),
        ("RGBA tile 7", sha(&rgba_tile)),
        ("RGBA tile 100", sha(&tile_sheet(&rgba_chip, 100))),
        (
            "indexed translucent at 0,0",
            sha(&translucent(&indexed, &behind, 0, 0)),
        ),
        (
            "indexed translucent at 3,2",
            sha(&translucent(&indexed, &behind, 3, 2)),
        ),
        (
            "indexed translucent at 5,4",
            sha(&translucent(&indexed, &behind, 5, 4)),
        ),
        (
            "RGBA translucent at 2,1",
            sha(&translucent(&rgba, &behind, 2, 1)),
        ),
        (
            "RGBA tile 7 translucent at 1,1",
            sha(&translucent(&rgba_tile, &behind, 1, 1)),
        ),
    ];
    let expected = [
        "a8dd7d43b0d908a742cdf30f0d4461acd219561d9c1717fc99733fe6803dc09b",
        "1ebc63b214609ddf2074640632fbb1c2302286de48514ab45a48701b0dace987",
        "79d00eafada08878e35e82fa0697c01bb256500b46aa9e1b993c250f7516c7c9",
        "4306edf8dc2b59e213754eee7c28eaa0432ddc74dc9783cb78c1ee6b0879f1ad",
        "91a2463b13dc6f2de94d70087ce9659957f2a5ddc51efd46462a82f1d2e0fb5c",
        "64a826ba391bf78fec364b697ba1b3a6e1afacc477cf21f6e336189bce6ae6fa",
        "f7a4ab7618cff90c718a291283c37ad169fc5083e4a307570f28b7648e839937",
        "2e3aa404750c22e4247e2e290c06c9cba151a16216d82212b3d404065f63afc5",
        "1ff2e7d247e1f6d31f8f8577f03ffa8157b4cf13897551990483f93131db025c",
        "4e2fd9c3dc301781d8bcdd54c25a553978d0285638effe1619f4a847f4b0da8f",
        "e9b7a83e83d2c31bf09becc02c15c594f8167eac713ffb606e20d3406efc7092",
        "829e734342eaf849b91a0f56a47960006ac10bb611d28c61aa1ed4b0187766d5",
    ];
    let wrong: Vec<String> = got
        .iter()
        .zip(expected)
        .filter(|((_, g), e)| g != e)
        .map(|((what, g), e)| format!("{what}: {g}, and the Python gave {e}"))
        .collect();
    std::fs::remove_dir_all(&dir).unwrap();
    assert!(wrong.is_empty(), "{}", wrong.join("\n"));
}
