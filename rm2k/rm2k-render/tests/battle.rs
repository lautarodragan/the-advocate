//! What a battle is drawn with, against the drawings it replaces.
//!
//! Until `battle-animation` and `battle` existed, the same pictures were
//! drawn by the Python of a converter. It was deleted once the two gave the
//! same pixels on every animation, battler and backdrop of a whole game;
//! what is left of it is here: the SHA-256 of what it drew for a sheet, a
//! monster and a backdrop generated inside the test —the same pictures as
//! the ChipSets of `common`—, which need no game and no RTP.
//!
//! The inputs touch what can differ: an indexed picture, and an RGBA one
//! with half-transparent pixels; cells zoomed up and down, to one pixel,
//! faded, fully faded, with a transparency out of 0..100, invalid, and
//! missing from the sheet; a large animation; and hues positive, negative,
//! and past a full turn.
//!
//! **A zoomed cell is checked by where it lands and its size, not by its
//! pixels.** Since 2026-10-02 the zoom is the `image` crate's bilinear and
//! no longer a copy of Pillow's, so the Python's hashes of those cells no
//! longer apply; the zoom itself is tested in `picture.rs`.
//!
//! **If one of these changes, a pixel changed.** The hashes are not to be
//! regenerated to make a test pass: the Python that produced them is gone,
//! and with it the only independent answer.

mod common;

use common::{indexed_chipset, rgba_chipset, sha};
use ditto::schema::Animation;
use rm2k_render::battle::{backdrop, battler};
use rm2k_render::battle_animation::{bounds, frames};
use rm2k_render::{picture, Picture};
use sha2::{Digest, Sha256};
use std::path::PathBuf;

fn scratch(name: &str) -> PathBuf {
    let dir =
        std::env::temp_dir().join(format!("rm2k-render-battle-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// The two pictures every case is drawn from: `indexed.png` and
/// `rgba.png`, 480x256. As a battle sheet that is two rows of five cells
/// of 96, or two by three of 128.
fn pictures(dir: &std::path::Path) -> [(&'static str, PathBuf); 2] {
    let indexed = dir.join("indexed.png");
    let rgba = dir.join("rgba.png");
    indexed_chipset(&indexed);
    rgba_chipset(&rgba);
    [("indexed", indexed), ("rgba", rgba)]
}

fn cell(cell_id: i32, x: i32, y: i32) -> serde_json::Value {
    serde_json::json!({"cell_id": cell_id, "x": x, "y": y})
}

fn with(mut cell: serde_json::Value, key: &str, value: i32) -> serde_json::Value {
    cell[key] = value.into();
    cell
}

/// A small animation: every kind of cell.
fn small() -> Animation {
    let toned = [
        ("zoom", 133),
        ("tone_red", 150),
        ("tone_green", 100),
        ("tone_blue", 80),
        ("tone_gray", 40),
    ]
    .iter()
    .fold(cell(3, -50, 10), |c, (k, v)| with(c, k, *v));
    serde_json::from_value(serde_json::json!({"frames": [
        {"cells": [
            cell(0, 0, 0),
            with(with(cell(7, 30, -20), "zoom", 75), "transparency", 37),
            toned,
            with(cell(1, 500, 500), "valid", 0),
            cell(12, 5, 5),
        ]},
        {"cells": [
            with(with(cell(9, 10, 40), "zoom", 200), "transparency", -5),
            with(cell(4, 3, 3), "zoom", 1),
            with(with(cell(2, -7, 9), "zoom", 50), "transparency", 150),
            with(with(cell(5, 1, 2), "zoom", 99), "transparency", 100),
        ]},
        {"cells": []},
    ]}))
    .unwrap()
}

/// A large one: cells of 128, and one the sheet has no room for.
fn large() -> Animation {
    serde_json::from_value(serde_json::json!({"large": true, "frames": [
        {"cells": [
            with(cell(2, 0, 0), "zoom", 60),
            with(with(cell(6, 11, -13), "zoom", 110), "transparency", 20),
            cell(3, 0, 0),
        ]},
    ]}))
    .unwrap()
}

/// Each frame's cells as `(x, y, side, hash)`.
fn drawn(animation: &Animation, sheet: &Picture) -> Vec<Vec<(i64, i64, usize, String)>> {
    frames(animation, sheet)
        .1
        .iter()
        .map(|f| {
            f.iter()
                .map(|p| (p.x, p.y, p.picture.width, sha(&p.picture)))
                .collect()
        })
        .collect()
}

/// A drawn cell: where it lands, its side, and —for one drawn at its own
/// size— the hash of what the Python drew. A zoomed one has no hash: the
/// zoom is the `image` crate's since 2026-10-02, not the Python's, and its
/// pixels are `Picture::resized`'s, tested there.
type Cell = (i64, i64, usize, Option<&'static str>);

fn check(drawn: Vec<Vec<(i64, i64, usize, String)>>, expected: &[&[Cell]]) {
    assert_eq!(drawn.len(), expected.len(), "frames");
    for (f, (got, want)) in drawn.iter().zip(expected).enumerate() {
        assert_eq!(got.len(), want.len(), "cells of frame {f}");
        for (c, ((x, y, side, hash), (wx, wy, wside, whash))) in got.iter().zip(*want).enumerate() {
            assert_eq!((x, y, side), (wx, wy, wside), "frame {f}, cell {c}");
            if let Some(whash) = whash {
                assert_eq!(hash, whash, "frame {f}, cell {c}");
            }
        }
    }
}

#[test]
fn the_boxes_are_what_the_python_measured() {
    assert_eq!(bounds(&small()), Some((-113, -56, 219, 192)));
    assert_eq!(bounds(&large()), Some((-64, -83, 145, 147)));
    let empty: Animation = serde_json::from_value(serde_json::json!({"frames": [
        {"cells": [with(cell(0, 0, 0), "valid", 0)]}, {"cells": []}
    ]}))
    .unwrap();
    assert_eq!(bounds(&empty), None);
}

#[test]
fn the_cells_land_where_the_python_put_them() {
    let dir = scratch("cells");
    let [(_, indexed), (_, rgba)] = pictures(&dir);
    let indexed = picture::read_rm2k(&indexed).unwrap();
    let rgba = picture::read_rm2k(&rgba).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    let zoomed_small: [&[Cell]; 2] = [
        &[(107, 0, 72, None), (0, 3, 127, None)],
        &[
            (27, 0, 192, None),
            (116, 59, 1, None),
            (82, 41, 48, None),
            (67, 11, 95, None),
        ],
    ];
    let small_indexed: [Cell; 1] = [(
        65,
        8,
        96,
        Some("4db7698078df9b7ca6ec96254da4d070439396bfbc6f0694d7eff280a20b8d81"),
    )];
    let small_rgba: [Cell; 1] = [(
        65,
        8,
        96,
        Some("e4eb2a37aa6f7b644f3104f0758a31540dd2272d51ec076208548853bdeb6cb6"),
    )];
    for (sheet, first) in [(&indexed, &small_indexed), (&rgba, &small_rgba)] {
        let frame_0: Vec<Cell> = first.iter().chain(zoomed_small[0]).copied().collect();
        check(drawn(&small(), sheet), &[&frame_0, zoomed_small[1], &[]]);
    }
    for sheet in [&indexed, &rgba] {
        check(
            drawn(&large(), sheet),
            &[&[(26, 45, 76, None), (5, 0, 140, None)]],
        );
    }
}

#[test]
fn a_cell_goes_out_with_its_tone() {
    let dir = scratch("tone");
    let [(_, indexed), _] = pictures(&dir);
    let sheet = picture::read_rm2k(&indexed).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    let (_, frames) = frames(&small(), &sheet);
    let tones: Vec<[i32; 4]> = frames[0].iter().map(|p| p.tone).collect();
    assert_eq!(
        tones,
        [
            [100, 100, 100, 100],
            [100, 100, 100, 100],
            [150, 100, 80, 40]
        ]
    );
}

#[test]
fn the_battlers_are_what_the_python_drew() {
    let dir = scratch("battlers");
    let expected = [
        (
            "indexed",
            0,
            "46d142a57ce5a4cbaf2f4d312c94915b584ccf74ef5f57bee9b2aabed735560a",
        ),
        (
            "indexed",
            17,
            "4e711b079be8bd6b70944ce3ef3deebc4790d90950c60ff127a64c3b124cfc1e",
        ),
        (
            "indexed",
            -45,
            "02845d573b62b1829303598cb36ffc33305efa064cefa644691f103579f999dd",
        ),
        (
            "indexed",
            180,
            "0df7af8f92d4120d8b4a43f362af896ab0053712a5fe8be2655188ea772b5468",
        ),
        (
            "indexed",
            360,
            "6aafc28a20f22458d74cb032aa4b3ec2f1ec52caf950fde56d39a8602640f817",
        ),
        (
            "indexed",
            720,
            "6aafc28a20f22458d74cb032aa4b3ec2f1ec52caf950fde56d39a8602640f817",
        ),
        (
            "rgba",
            0,
            "43f843d7d483a6b124aeb6b6481ee7ddbdf5fbe287aa1f2bb5233b5912d63f30",
        ),
        (
            "rgba",
            17,
            "89b99ca02a5152f9b8719cab0c6f521a81a524da2008ff7d0544d580c4d5f3d0",
        ),
        (
            "rgba",
            -45,
            "f58836d3207b3da4d9f728debc2a0320704d668381830b4a1e49415d13fac7a7",
        ),
        (
            "rgba",
            180,
            "a1adbdae3acb7cf7f36576898a51590a693bd64126d7c0077f925874c943b69e",
        ),
        (
            "rgba",
            360,
            "efc679126da1af203ae13538a07608913607d79d23b8921b5425400ba9ed4a25",
        ),
        (
            "rgba",
            720,
            "efc679126da1af203ae13538a07608913607d79d23b8921b5425400ba9ed4a25",
        ),
    ];
    let files = pictures(&dir);
    let wrong: Vec<String> = expected
        .iter()
        .filter_map(|(which, hue, e)| {
            let path = &files.iter().find(|(n, _)| n == which).unwrap().1;
            let got = sha(&battler(path, *hue).unwrap());
            (got != *e).then(|| format!("{which} at {hue}: {got}, and the Python gave {e}"))
        })
        .collect();
    std::fs::remove_dir_all(&dir).unwrap();
    assert!(wrong.is_empty(), "{}", wrong.join("\n"));
}

#[test]
fn the_backdrops_are_what_the_python_drew_and_opaque() {
    let dir = scratch("backdrops");
    let expected = [
        (
            "indexed",
            "852743bb64ffe609593aee8ff136d88a5aa1adee8a2146ae9d93cc5bf99749c7",
        ),
        (
            "rgba",
            "9a357ddd2845242263887beca3888799bebfb5c681736eb1faaf329efa05c2ed",
        ),
    ];
    let files = pictures(&dir);
    let mut wrong = Vec::new();
    for (which, e) in expected {
        let path = &files.iter().find(|(n, _)| *n == which).unwrap().1;
        let drawn = backdrop(path).unwrap();
        // The Python kept the colours only, and hashed those.
        let rgb: Vec<u8> = drawn
            .rgba
            .chunks_exact(4)
            .flat_map(|p| [p[0], p[1], p[2]])
            .collect();
        let got: String = Sha256::digest(&rgb)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        if got != e {
            wrong.push(format!("{which}: {got}, and the Python gave {e}"));
        }
        if drawn.rgba.chunks_exact(4).any(|p| p[3] != 255) {
            wrong.push(format!("{which}: not opaque"));
        }
    }
    std::fs::remove_dir_all(&dir).unwrap();
    assert!(wrong.is_empty(), "{}", wrong.join("\n"));
}
