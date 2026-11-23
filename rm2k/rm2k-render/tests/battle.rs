//! What a battle is drawn with, over a sheet, a monster and a backdrop
//! generated inside the test —the same pictures as the ChipSets of
//! `common`—, which need no game and no RTP.
//!
//! The inputs touch what can differ: an indexed picture, and an RGBA one
//! with half-transparent pixels; cells zoomed up and down, to one pixel,
//! faded, fully faded, with a transparency out of 0..100, invalid, and
//! missing from the sheet; a large animation; and hues positive, negative,
//! and past a full turn.
//!
//! **The path it guards**: those edges, which a game's animations and
//! battlers may not have. What a real battle looks like is A Blurred Line's
//! goldens'. What is checked is where each cell lands and how big, its
//! tone, the animation's box, a hue that turns whole, and an opaque
//! backdrop. The zoom itself is tested in `picture.rs`.

mod common;

use common::{indexed_chipset, rgba_chipset};
use ditto::schema::Animation;
use rm2k_render::battle::{backdrop, battler};
use rm2k_render::battle_animation::{bounds, frames};
use rm2k_render::{picture, Picture};
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

/// Each frame's cells as `(x, y, side)`.
fn drawn(animation: &Animation, sheet: &Picture) -> Vec<Vec<Cell>> {
    frames(animation, sheet)
        .1
        .iter()
        .map(|f| f.iter().map(|p| (p.x, p.y, p.picture.width)).collect())
        .collect()
}

/// A drawn cell: where it lands and its side.
type Cell = (i64, i64, usize);

#[test]
fn the_box_holds_every_valid_cell() {
    assert_eq!(bounds(&small()), Some((-113, -56, 219, 192)));
    assert_eq!(bounds(&large()), Some((-64, -83, 145, 147)));
    let empty: Animation = serde_json::from_value(serde_json::json!({"frames": [
        {"cells": [with(cell(0, 0, 0), "valid", 0)]}, {"cells": []}
    ]}))
    .unwrap();
    assert_eq!(bounds(&empty), None);
}

#[test]
fn the_cells_land_where_they_are_put_and_as_big() {
    let dir = scratch("cells");
    let [(_, indexed), (_, rgba)] = pictures(&dir);
    let indexed = picture::read_rm2k(&indexed).unwrap();
    let rgba = picture::read_rm2k(&rgba).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    // The same on both sheets: where a cell goes is the animation's, not
    // its pixels'.
    let small_cells: [&[Cell]; 3] = [
        &[(65, 8, 96), (107, 0, 72), (0, 3, 127)],
        &[(27, 0, 192), (116, 59, 1), (82, 41, 48), (67, 11, 95)],
        &[],
    ];
    for sheet in [&indexed, &rgba] {
        assert_eq!(drawn(&small(), sheet), small_cells);
        assert_eq!(drawn(&large(), sheet), [[(26, 45, 76), (5, 0, 140)]]);
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

/// A battler's hue goes round: a full turn is two, back an eighth is
/// seven eighths on, and any turn changes a picture with colour. A turn of
/// 0 is the picture as it is; a full one is not quite, because the colour
/// goes through easyrpg's integer HSL and back.
#[test]
fn a_battler_s_hue_goes_round() {
    let dir = scratch("battlers");
    for (which, path) in pictures(&dir) {
        let at = |hue| battler(&path, hue).unwrap();
        let still = at(0);
        assert!(
            still == picture::read_rm2k(&path).unwrap(),
            "{which}: no turn"
        );
        assert!(at(360) == at(720), "{which}: one turn and two");
        assert!(at(-45) == at(315), "{which}: back an eighth");
        assert!(at(17) != still, "{which}: a turn that changes nothing");
        assert!(at(180) != at(17), "{which}: two turns the same");
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_backdrop_is_opaque() {
    let dir = scratch("backdrops");
    for (which, path) in pictures(&dir) {
        let drawn = backdrop(&path).unwrap();
        assert!(
            drawn.rgba.chunks_exact(4).all(|p| p[3] == 255),
            "{which}: not opaque"
        );
    }
    std::fs::remove_dir_all(&dir).unwrap();
}
