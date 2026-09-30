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
//! with half-transparent pixels, which is where premultiplying for the zoom
//! shows; cells zoomed up and down, to one pixel, faded, fully faded, with
//! a transparency out of 0..100, invalid, and missing from the sheet; a
//! large animation; and hues positive, negative, and past a full turn.
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

/// Each frame's cells as `(x, y, hash)`.
fn drawn(animation: &Animation, sheet: &Picture) -> Vec<Vec<(i64, i64, String)>> {
    frames(animation, sheet)
        .1
        .iter()
        .map(|f| f.iter().map(|p| (p.x, p.y, sha(&p.picture))).collect())
        .collect()
}

fn cells(listed: &[(i64, i64, &str)]) -> Vec<(i64, i64, String)> {
    listed
        .iter()
        .map(|(x, y, h)| (*x, *y, h.to_string()))
        .collect()
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
fn the_cells_are_what_the_python_drew() {
    let dir = scratch("cells");
    let [(_, indexed), (_, rgba)] = pictures(&dir);
    let indexed = picture::read_rm2k(&indexed).unwrap();
    let rgba = picture::read_rm2k(&rgba).unwrap();
    let small_indexed = vec![
        cells(&[
            (
                65,
                8,
                "4db7698078df9b7ca6ec96254da4d070439396bfbc6f0694d7eff280a20b8d81",
            ),
            (
                107,
                0,
                "1c11833d678a1ddb30dad5ea0ba30bbac57c3de29704fe77080d48e7880d13b4",
            ),
            (
                0,
                3,
                "5f374a24ed4100195c0bbab944033f9bd99f9f8cde27c3630a1d940d1f95f443",
            ),
        ]),
        cells(&[
            (
                27,
                0,
                "c80fd785181131e181e7e61b2e2df0ad998fbb6a3c818d0191b6b566decde69b",
            ),
            (
                116,
                59,
                "31791d517861bf0d8af3ebbd00568701b2871736955a05170d61e37253a5f3e8",
            ),
            (
                82,
                41,
                "2c3b75385f9f9be11ab4af3facb36360deefd8dba6b4a8ae7bc4d98c792fc3e1",
            ),
            (
                67,
                11,
                "4398d94d426c96e88d74a11c1a0e1b90bf6457e3c40e60f0e9f0ce0aa2c811b5",
            ),
        ]),
        vec![],
    ];
    let small_rgba = vec![
        cells(&[
            (
                65,
                8,
                "e4eb2a37aa6f7b644f3104f0758a31540dd2272d51ec076208548853bdeb6cb6",
            ),
            (
                107,
                0,
                "db036edb10bf2ba1466dda8645faae32a1e93abc9235ccffd56bfbe4fd0aaa15",
            ),
            (
                0,
                3,
                "e5c24458173fb59dd32df5b8274c254b2864866b2b0771c5a2a3dd9b8a1784e1",
            ),
        ]),
        cells(&[
            (
                27,
                0,
                "7fa95efe633729971f5991cbc28a1d129921b855b1e4384c7974d8d8e0bc2309",
            ),
            (
                116,
                59,
                "7aab1496358a4780acec547842af6851e7d4231b464a4a798c037e985d8d8eba",
            ),
            (
                82,
                41,
                "1db718c40626c405b3a05b0d5a8e053688ce3b6fb86537d9b1bb728902b76e8a",
            ),
            (
                67,
                11,
                "a16611e89df37bfdb65fe21dabeb0c1c39c337b5aae92e224739820c27ba709b",
            ),
        ]),
        vec![],
    ];
    let large_indexed = vec![cells(&[
        (
            26,
            45,
            "75b951b0d22fde203ffc70a2b3d7ef3a27030567fd8878aa4b45f378cf8f7d8d",
        ),
        (
            5,
            0,
            "cf813b0401a5be108769fad813a4c96dff09ecf4467321338b19587a9d0dce6e",
        ),
    ])];
    let large_rgba = vec![cells(&[
        (
            26,
            45,
            "bab1389217cc9186f9672283ee33c175a2959ccc414fe7ac6ad0793dd6660179",
        ),
        (
            5,
            0,
            "9f74040bef1654ac8c54ccc9cbac5f07f212655607cf56e508dd0ae4486daabd",
        ),
    ])];
    std::fs::remove_dir_all(&dir).unwrap();
    assert_eq!(drawn(&small(), &indexed), small_indexed);
    assert_eq!(drawn(&small(), &rgba), small_rgba);
    assert_eq!(drawn(&large(), &indexed), large_indexed);
    assert_eq!(drawn(&large(), &rgba), large_rgba);
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

// --- the executable -----------------------------------------------------------

fn run(
    subcommand: &str,
    dir: &std::path::Path,
    entries: serde_json::Value,
) -> std::process::Output {
    let path = dir.join("request.json");
    std::fs::write(&path, entries.to_string()).unwrap();
    std::process::Command::new(env!("CARGO_BIN_EXE_rm2k-render"))
        .args([
            subcommand,
            "--request",
            path.to_str().unwrap(),
            "--out",
            dir.join("out").to_str().unwrap(),
        ])
        .output()
        .unwrap()
}

fn listing(dir: &std::path::Path) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .unwrap()
        .map(|e| e.unwrap().file_name().into_string().unwrap())
        .collect();
    names.sort();
    names
}

#[test]
fn a_battle_animation_request_writes_its_box_and_its_cells() {
    let dir = scratch("cli-animation");
    pictures(&dir);
    std::fs::create_dir_all(dir.join("Battle")).unwrap();
    std::fs::rename(dir.join("indexed.png"), dir.join("Battle/Hit.png")).unwrap();
    // Paths relative to the request; the second animation has no valid
    // cell, and the first a cell the sheet does not have.
    let done = run(
        "battle-animation",
        &dir,
        serde_json::json!([
            {"sheet_file": "Battle/Hit.png", "animation": {"frames": [
                {"cells": [cell(1, 0, 0), with(cell(4, 10, 20), "zoom", 50), cell(12, 0, 0)]},
                {"cells": []},
            ]}},
            {"sheet_file": "Battle/Hit.png", "animation": {"frames": [
                {"cells": [with(cell(1, 0, 0), "valid", 0)]},
            ]}},
        ]),
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let out = dir.join("out");
    assert_eq!(
        listing(&out),
        ["0-0-0.png", "0-0-1.png", "0.json", "1.json"]
    );
    let listed: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("0.json")).unwrap()).unwrap();
    assert_eq!(
        listed,
        serde_json::json!({"box": [-48, -48, 96, 96], "frames": [
            [{"x": 0, "y": 0, "tone": [100, 100, 100, 100]},
             {"x": 34, "y": 44, "tone": [100, 100, 100, 100]}],
            [],
        ]})
    );
    // Cell 1 whole, as the sheet has it at (96, 0).
    let sheet = picture::read_rm2k(&dir.join("Battle/Hit.png")).unwrap();
    let first = picture::read_rgba(&out.join("0-0-0.png")).unwrap();
    assert_eq!((first.width, first.height), (96, 96));
    assert_eq!(first.get(5, 7), sheet.get(96 + 5, 7));
    let half = picture::read_rgba(&out.join("0-0-1.png")).unwrap();
    assert_eq!((half.width, half.height), (48, 48));
    let empty: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("1.json")).unwrap()).unwrap();
    assert_eq!(empty, serde_json::json!({"box": null, "frames": [[]]}));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_battle_request_draws_backdrops_and_battlers() {
    let dir = scratch("cli-battle");
    pictures(&dir);
    let done = run(
        "battle",
        &dir,
        serde_json::json!([
            {"backdrop_file": "indexed.png"},
            {"monster_file": "indexed.png"},
            {"monster_file": "rgba.png", "hue": 90},
        ]),
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let out = dir.join("out");
    assert_eq!(listing(&out), ["0.png", "1.png", "2.png"]);
    let read = |name: &str| picture::read_rgba(&out.join(name)).unwrap();
    assert_eq!(read("0.png"), backdrop(&dir.join("indexed.png")).unwrap());
    assert_eq!(read("1.png"), battler(&dir.join("indexed.png"), 0).unwrap());
    assert_eq!(read("2.png"), battler(&dir.join("rgba.png"), 90).unwrap());
    // Index 0 is a colour in a backdrop, and the colour key in a battler:
    // the indexed picture has it at (0, 0).
    assert_eq!(read("0.png").get(0, 0)[3], 255);
    assert_eq!(read("1.png").get(0, 0)[3], 0);
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_battle_entry_that_makes_no_sense_is_an_answer() {
    let dir = scratch("cli-bad");
    pictures(&dir);
    for (subcommand, entries, says) in [
        (
            "battle",
            serde_json::json!([{"backdrop_file": "indexed.png", "monster_file": "rgba.png"}]),
            "only one",
        ),
        (
            "battle",
            serde_json::json!([{"monster_file": "rgba.png", "hue": "red"}]),
            "`hue`",
        ),
        (
            "battle-animation",
            serde_json::json!([{"animation": {"frames": []}}]),
            "`sheet_file`",
        ),
        (
            "battle-animation",
            serde_json::json!([{"sheet_file": "indexed.png"}]),
            "no `animation`",
        ),
        (
            "battle-animation",
            serde_json::json!({"sheet_file": "indexed.png"}),
            "not a list",
        ),
    ] {
        let done = run(subcommand, &dir, entries);
        assert_eq!(done.status.code(), Some(1));
        assert!(
            String::from_utf8_lossy(&done.stderr).contains(says),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
    }
    // A picture that is not there is the call being wrong, as with
    // --chipset-file.
    let done = run(
        "battle",
        &dir,
        serde_json::json!([{"backdrop_file": "Nobody.png"}]),
    );
    assert_eq!(done.status.code(), Some(2));
    std::fs::remove_dir_all(&dir).unwrap();
}
