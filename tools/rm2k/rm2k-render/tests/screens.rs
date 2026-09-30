//! Faces, windows and pictures against the ones they replace.
//!
//! Until `face`, `system` and `picture` existed, the same pictures were
//! drawn by the Python of the converter. It was deleted once the two gave
//! the same pixels on every FaceSet, System and picture of a whole game and
//! of the RTP; what is left of it is here: the SHA-256 of what it drew for
//! pictures generated inside this file, which need no game and no RTP.
//!
//! The inputs touch what can differ: an indexed System —the colour key at
//! index 0— and an RGBA one with half-transparent pixels, where the
//! rounding of each blend shows; windows whose size is not a multiple of
//! the background's, where the stretch has to pick the same pixels, and
//! edges that do not repeat every 8 pixels; a FaceSet smaller than the
//! faces it is asked for.
//!
//! **If one of these changes, a pixel changed.** The hashes are not to be
//! regenerated to make a test pass: the Python that produced them is gone,
//! and with it the only independent answer.
//!
//! What the Python never drew —the tiled background, the cursor's second
//! drawing, a transparent colour or a transparency on a `ShowPicture`— is
//! checked here against what RM2k does, pixel by pixel.

mod common;

use common::sha;
use rm2k_render::picture::{self, Picture};
use rm2k_render::{face, show_picture, system};
use rm2k_rules::system::Background;
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir =
        std::env::temp_dir().join(format!("rm2k-render-screens-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// An indexed picture: a palette and every pixel from formulas.
fn indexed(
    path: &Path,
    width: usize,
    height: usize,
    palette: impl Fn(usize) -> [u8; 3],
    pixel: impl Fn(usize, usize) -> u8,
) {
    let mut encoder = png::Encoder::new(
        std::fs::File::create(path).unwrap(),
        width as u32,
        height as u32,
    );
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_palette((0..256).flat_map(&palette).collect::<Vec<u8>>());
    let pixels: Vec<u8> = (0..height)
        .flat_map(|y| (0..width).map(move |x| (x, y)))
        .map(|(x, y)| pixel(x, y))
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

/// An indexed System whose edges do not repeat every 8 pixels, with the
/// colour key scattered through it.
fn indexed_system(path: &Path) {
    indexed(
        path,
        160,
        80,
        |i| {
            [
                (i * 37 % 256) as u8,
                (i * 101 % 256) as u8,
                (i * 211 % 256) as u8,
            ]
        },
        |x, y| {
            if (x * 3 + y) % 7 == 0 {
                0
            } else {
                ((x * 7 + y * 13 + (x / 5) * (y / 3)) % 256) as u8
            }
        },
    );
}

/// An RGBA System with half-transparent pixels.
fn rgba_system(path: &Path) {
    const ALPHAS: [u8; 5] = [0, 255, 128, 37, 200];
    let mut rgba = Vec::with_capacity(160 * 80 * 4);
    for y in 0..80usize {
        for x in 0..160usize {
            rgba.extend_from_slice(&[
                (x * 3 % 256) as u8,
                (y * 5 % 256) as u8,
                ((x + y) % 256) as u8,
                ALPHAS[(x * y + x) % 5],
            ]);
        }
    }
    picture::write_png(
        path,
        &Picture {
            width: 160,
            height: 80,
            rgba,
        },
    )
    .unwrap();
}

/// An indexed FaceSet, or picture, of any size.
fn indexed_sheet(path: &Path, width: usize, height: usize) {
    indexed(
        path,
        width,
        height,
        |i| {
            [
                (i * 53 % 256) as u8,
                (i * 29 % 256) as u8,
                (i * 197 % 256) as u8,
            ]
        },
        |x, y| {
            if (x + y) % 4 == 0 {
                0
            } else {
                ((x * 11 + y * 5 + (x / 7) * (y / 4)) % 256) as u8
            }
        },
    );
}

fn systems(dir: &Path) -> [(&'static str, Picture); 2] {
    indexed_system(&dir.join("indexed.png"));
    rgba_system(&dir.join("rgba.png"));
    [
        (
            "indexed",
            picture::read_rm2k(&dir.join("indexed.png")).unwrap(),
        ),
        ("rgba", picture::read_rm2k(&dir.join("rgba.png")).unwrap()),
    ]
}

fn find<'a>(systems: &'a [(&str, Picture); 2], kind: &str) -> &'a Picture {
    &systems.iter().find(|(k, _)| *k == kind).unwrap().1
}

#[test]
fn windows_stretched_are_the_pythons() {
    let s = systems(&scratch("windows"));
    for (kind, w, h, hash) in [
        (
            "indexed",
            256,
            80,
            "9382802088f44fbdef998976bded8c72a1f77f1b14f2ef07938e64d67f4b7b21",
        ),
        (
            "indexed",
            80,
            48,
            "b1f6653cfc56eb88b1cd886a023b13578af765b881027c0d2df294fe4db09674",
        ),
        (
            "indexed",
            17,
            23,
            "5e94ee70d6810b46ef256c5228ef9ef8a3cfa6f7c4a57a15cae0c19f78e96df5",
        ),
        (
            "indexed",
            320,
            240,
            "9761702e0086747a9242f431823695145a8c562400b14915c295e26712b18fb3",
        ),
        (
            "indexed",
            16,
            16,
            "0428386d71fe49e4f403aa126552502ab353ca6d175ee0540fc56e805e57b618",
        ),
        (
            "indexed",
            100,
            16,
            "f3fe8375d2ee22ace4e19b704e73df9cf17ff6a3715f6e330386a93f94d43f6d",
        ),
        (
            "rgba",
            256,
            80,
            "0f20198126f0ce93a2d31080f2d3f2b4d52ee74a7c2944dc94e12964809a73a4",
        ),
        (
            "rgba",
            80,
            48,
            "84140ac18db8b5c5f87e39cd9b669c540996d970ce13142764febece56369c07",
        ),
        (
            "rgba",
            17,
            23,
            "48cb57e84abe1de285f0c361ababb7034f8384f505083f30b8f995c4caa2260e",
        ),
        (
            "rgba",
            320,
            240,
            "b76f0d5643b26d675af0b2516d048bc9cb14ffe3fa87df04f21716acdd93f50b",
        ),
        (
            "rgba",
            16,
            16,
            "e1201b8000d574e3ee9440fb546a02019edcc194911f917758d849a7a2882760",
        ),
        (
            "rgba",
            100,
            16,
            "a798e8804d184e75dfd3fbc85007a4c5c48aea7adabbb093307766ca6ccc0f8e",
        ),
    ] {
        let window = system::window(find(&s, kind), w, h, Background::Stretched);
        assert_eq!(sha(&window), hash, "{kind} window {w}x{h}");
    }
}

#[test]
fn cursors_are_the_pythons() {
    let s = systems(&scratch("cursors"));
    for (kind, w, h, hash) in [
        (
            "indexed",
            100,
            16,
            "6d4a642cd528de1c8d23f5804d51fa5d961b022ec91cf78730f9c533a83a2d41",
        ),
        (
            "indexed",
            57,
            33,
            "859c3b8c9a8f79360687df373cfe225caae732d4bcde81bd55328a38e04e0a48",
        ),
        (
            "indexed",
            16,
            16,
            "a525e01cd962210c3f15daf384ed3ff920159a812e7c61d1efa82db6a04bc6e6",
        ),
        (
            "indexed",
            240,
            32,
            "96200302e8a0d22978414fbb1ecd57595d2bd28c28972ef1b74fed08fbf7667d",
        ),
        (
            "rgba",
            100,
            16,
            "2be81122bc47de663b16e88ca844a3c1dc5bae42b3c8bbe3ad2a06776b778186",
        ),
        (
            "rgba",
            57,
            33,
            "fef0c09192204afaf543e7eb8e370011042463ea103af5f60fd9a43b16086b9f",
        ),
        (
            "rgba",
            16,
            16,
            "3c3d7253d8a2d4ec68d306f0e77b58fccf9ace2f3095193fd528104d95287f17",
        ),
        (
            "rgba",
            240,
            32,
            "532153086672f69ce9e8a2598955c7fa40f040d0ae6a5d923204114de2536a6b",
        ),
    ] {
        let cursor = system::cursor(find(&s, kind), w, h, 0);
        assert_eq!(sha(&cursor), hash, "{kind} cursor {w}x{h}");
    }
}

#[test]
fn blocks_are_the_pythons() {
    let s = systems(&scratch("blocks"));
    for (kind, color, hash) in [
        (
            "indexed",
            0,
            "3c3db104db99da9be07619b76195a0b23c2abc0604087967b98a954922f668ba",
        ),
        (
            "indexed",
            13,
            "1eca47b00ac01afd957cf74b4a3b0487475614f68518af9cc07824095712bde3",
        ),
        (
            "indexed",
            19,
            "c3845c376eb692fd894092b09363b0d40d4a3c330302fb368e1f6618463da211",
        ),
        (
            "rgba",
            0,
            "d4716bd7f06c7fee44862f4e531229d4b36ae6ed50447dbc191e1e5e0714264d",
        ),
        (
            "rgba",
            13,
            "39d18b74cbc1a51326ffddf3abe1f8b87f522de777fd3f168d992e7906b4e8d8",
        ),
        (
            "rgba",
            19,
            "3a757c8cae7f20bdadfaa94ba5ebab3d825ae80312a720e4e2beb62c7f2c301b",
        ),
    ] {
        let block = system::text_color(find(&s, kind), color);
        assert_eq!(sha(&block), hash, "{kind} text colour {color}");
    }
    for (kind, shadow, timer) in [
        (
            "indexed",
            "a5d5b7d137300cc30d2f51f0627d81fda886956f88bcc5d36215eb535873913f",
            "763269afba3bbbd6b6b038e615239d61f2046c22a33700303ace49ba616cb93f",
        ),
        (
            "rgba",
            "93a28a5a90aa53c5ea87734895af9c9e238bea904d49330be54ca99873d506e4",
            "377a5af171aa1a0234d3006e59f45776abf44ca6564781922680bbc52065e9da",
        ),
    ] {
        assert_eq!(
            sha(&system::shadow(find(&s, kind))),
            shadow,
            "{kind} shadow"
        );
        assert_eq!(sha(&system::timer(find(&s, kind))), timer, "{kind} timer");
    }
}

/// With `message_stretch` 1 the background is the 32x32 square repeated
/// from the window's corner, and the frame is the stretched window's.
#[test]
fn a_tiled_window_repeats_the_background() {
    let dir = scratch("tiled");
    indexed_system(&dir.join("indexed.png"));
    let system = picture::read_rm2k(&dir.join("indexed.png")).unwrap();
    let square = system.crop(0, 0, 32, 32);
    let (w, h) = (83, 57);
    let tiled = system::window(&system, w, h, Background::Tiled);
    let stretched = system::window(&system, w, h, Background::Stretched);
    let stretched_background = system::stretched(&square, w, h);
    let mut framed = 0;
    for y in 0..h as i64 {
        for x in 0..w as i64 {
            let border = x < 8 || y < 8 || x >= w as i64 - 8 || y >= h as i64 - 8;
            if !border {
                assert_eq!(tiled.get(x, y), square.get(x % 32, y % 32), "({x}, {y})");
            } else if stretched.get(x, y) != stretched_background.get(x, y) {
                // The frame drew here, and it is opaque: it is the same
                // frame over either background.
                assert_eq!(tiled.get(x, y), stretched.get(x, y), "({x}, {y})");
                framed += 1;
            } else if tiled.get(x, y) != square.get(x % 32, y % 32) {
                assert_eq!(tiled.get(x, y), stretched.get(x, y), "({x}, {y})");
            }
        }
    }
    assert!(framed > 0, "no pixel of the frame was checked");
}

/// The cursor's second drawing is laid out from the square at (96, 0) the
/// way the first is from the one at (64, 0).
#[test]
fn the_second_cursor_is_laid_out_like_the_first() {
    let s = systems(&scratch("second-cursor"));
    for (kind, system) in &s {
        let mut moved = system.clone();
        let square = system.crop(96, 0, 32, 32);
        moved.put(64, 0, &square);
        for (w, h) in [(100, 16), (57, 33), (16, 16)] {
            assert_eq!(
                system::cursor(system, w, h, 1),
                system::cursor(&moved, w, h, 0),
                "{kind} {w}x{h}"
            );
        }
    }
}

#[test]
fn faces_are_the_pythons() {
    let dir = scratch("faces");
    indexed_sheet(&dir.join("faceset.png"), 192, 192);
    indexed_sheet(&dir.join("faceset-small.png"), 100, 100);
    for (name, index, hash) in [
        (
            "faceset",
            0,
            "f618c1588690d01308eb733ea3fed7846c151f04374bbd9e85cf96ccc60b74a8",
        ),
        (
            "faceset",
            5,
            "4d7d031ebc3ed7d659d116fc7559549b8fb2818c1e579db8913426cfc2d83957",
        ),
        (
            "faceset",
            15,
            "fa4bf78dfad0cc9a7545bddf8ef0236bab859ee9be2804ba5eed2ac591ddf6b1",
        ),
        // A face partly outside the FaceSet, and one wholly outside: what
        // is not there comes out transparent.
        (
            "faceset-small",
            1,
            "ed1ff5590740bebd0c0962918dca896a0b01bcc6ad68f4dca0f49fd9c7975288",
        ),
        (
            "faceset-small",
            15,
            "2d07a41ae992770085117e9815300bfd0730745883e60b24aaad5e69dfc087ae",
        ),
    ] {
        let sheet = picture::read_rm2k(&dir.join(format!("{name}.png"))).unwrap();
        assert_eq!(sha(&face::face(&sheet, index)), hash, "{name} face {index}");
    }
}

/// The RGB of each pixel, which is all the Python kept of a picture.
fn rgb(picture: &Picture) -> Picture {
    let rgba = picture
        .rgba
        .chunks(4)
        .flat_map(|p| p[..3].to_vec())
        .collect();
    Picture {
        width: picture.width,
        height: picture.height,
        rgba,
    }
}

#[test]
fn pictures_are_the_pythons_and_rm2ks() {
    let dir = scratch("pictures");
    let path = dir.join("picture.png");
    indexed_sheet(&path, 64, 40);
    let plain = picture::read_unkeyed(&path).unwrap();
    let keyed = picture::read_rm2k(&path).unwrap();

    // Opaque and without its transparent colour, which is the one kind the
    // Python drew: every pixel opaque, with the colours of the file.
    let drawn = show_picture::picture(&plain, &keyed, false, 0);
    assert_eq!(
        sha(&rgb(&drawn)),
        "b1915b23e52704464b17313ccabea43e46b6a6b6cf3d22369c0440a0a0da92ac"
    );
    assert!(drawn.rgba.chunks(4).all(|p| p[3] == 255));

    // With the transparent colour: index 0 transparent, which is what the
    // Python did to any RM2k picture that was not a `ShowPicture`.
    let drawn = show_picture::picture(&plain, &keyed, true, 0);
    assert_eq!(
        sha(&drawn),
        "baeccda7ae6cb122c42865cd9fcceb7ba6118d0b8d935bacb258e2deb511e4c8"
    );

    // At a transparency, every pixel that is drawn is at its opacity, and
    // the colours do not change.
    for (top_trans, alpha) in [(50, 127), (100, 0), (1, 252)] {
        let drawn = show_picture::picture(&plain, &keyed, true, top_trans);
        for (p, k) in drawn.rgba.chunks(4).zip(keyed.rgba.chunks(4)) {
            assert_eq!(p[..3], k[..3]);
            assert_eq!(
                p[3],
                if k[3] == 0 { 0 } else { alpha },
                "top_trans {top_trans}"
            );
        }
    }
}
