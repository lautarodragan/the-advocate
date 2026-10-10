//! What this crate answers for a small game, pinned: the game in
//! `tests/game/` —indexed PNGs with gradients and noise, a battler and an
//! animation sheet with their colour key, and three animations in the
//! dump's shape—, each piece converted as the stage does it and compared,
//! as canonical JSON, against a sha256.
//!
//! Until 2026-10-02 the hashes were what the Python this replaced answered,
//! and the scaling was a copy of Pillow's to the bit. Since then it is the
//! `image` crate's, which rounds differently, and the hashes are what the
//! crate answered that day: **a regression check, not an independent
//! answer**. If one changes, a pixel or a palette changed; whether it is
//! the right one is for the game's screenshots to say.
//!
//! The animations cover zoom, translucency, tones with and without
//! saturation, an invalid cell, an empty frame, a cell the sheet does not
//! have, and one with no cell at all.

use ditto::schema::Animation;
use rm2k_render::{battle, picture, show_picture as rm2k_picture};
use rm2k_snes_images::request::{
    animation_answer, backdrop_answer, battler_answer, fullscreen_answer, light_answer,
    picture_answer,
};
use rm2k_snes_images::{animation, fullscreen, scene, show_picture};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

#[rustfmt::skip]
const ANSWERS: &[(&str, &str)] = &[
    ("fullscreen-0-256", "d6105484a678a8de22f0ba02265284fe760581f43555fba1751ef4c78745b9ed"),
    ("fullscreen-16-200", "b50aaf2bafef1b8d854e7610d312f3482839709a3fe59a6fb5c81a260222f0ba"),
    ("picture-100-175", "999e751796914d4346c3bf2b6864109084f45200736f3cb442f809055e819551"),
    ("picture-160-120", "04a005f9ab724de2acb474c8a0ad03e7e5044d21a7731206bc5515f968a25065"),
    ("backdrop-quality", "b5167f454e0b3284148987e160ea3ec50586d4802e716425e9a190baabaff3c7"),
    ("backdrop-light", "65757b8db67f09329fe37ad003af3820b5e5d9aa5633b5b39cf4f619386d0e8d"),
    ("battler-0", "b759310b7fdb2c78ce5a2dabd0747b6fcf122a909e6fc045ccb5c66b22696daf"),
    ("battler-120", "d9ae7cdc459fd3dcd3cca1c41ba3dfe3dc94494f62e3fd49bcc813d208f7d3ed"),
    ("animation-1", "9558e636bfc353695d0071b85e8b0f3de0ba28fd8fb339e68bfe8df33c891696"),
    ("animation-2", "0feddecc76599e9e5b2ed2d4e91ccd7650cff9bf53a49e63e8cbd133c70dfa7e"),
    ("animation-3", "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"),
];

fn game(parts: &[&str]) -> PathBuf {
    let mut p = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("game");
    for part in parts {
        p = p.join(part);
    }
    p
}

/// JSON with every object's keys sorted and no spaces: what Python's
/// `json.dumps(sort_keys=True, separators=(",", ":"))` writes, whatever
/// order `serde_json` keeps its keys in.
fn canonical(v: &Value) -> String {
    match v {
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            let inner: Vec<String> = keys
                .iter()
                .map(|k| format!("{}:{}", Value::String((*k).clone()), canonical(&map[*k])))
                .collect();
            format!("{{{}}}", inner.join(","))
        }
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(canonical).collect::<Vec<_>>().join(",")
        ),
        other => other.to_string(),
    }
}

fn check(name: &str, answer: &Value) {
    let expected = ANSWERS.iter().find(|(k, _)| *k == name).expect(name).1;
    let got = format!("{:x}", Sha256::digest(canonical(answer).as_bytes()));
    assert_eq!(got, expected, "{name}");
}

const SCENE: scene::Geometry = scene::Geometry {
    width: 256,
    height: 128,
    colors: 96,
    cgram_base: 32,
    light_scale: 2,
    light_colors: 16,
    scale: (256, 320),
    battler_colors: 15,
    alpha_min: 128,
};

#[test]
fn full_screens() {
    let title = picture::read_unkeyed(&game(&["Title", "title.png"])).unwrap();
    for (first, cap) in [(0, 256), (16, 200)] {
        let screen = fullscreen::convert(&title, 256, 224, 8, first, cap);
        check(
            &format!("fullscreen-{first}-{cap}"),
            &fullscreen_answer(&screen),
        );
    }
}

#[test]
fn pictures() {
    let file = game(&["Picture", "picture.png"]);
    let (plain, keyed) = (
        picture::read_unkeyed(&file).unwrap(),
        picture::read_rm2k(&file).unwrap(),
    );
    let screens = show_picture::Screens {
        rm: (320, 240),
        console: (256, 224),
    };
    for (cx, cy, key, trans) in [(100, 175, false, 0), (160, 120, true, 30)] {
        let drawn = rm2k_picture::picture(&plain, &keyed, key, trans);
        let converted = show_picture::convert(&drawn, cx, cy, screens, 15).unwrap();
        check(&format!("picture-{cx}-{cy}"), &picture_answer(&converted));
    }
}

#[test]
fn backdrops() {
    let drawn = battle::backdrop(&game(&["Backdrop", "backdrop.png"])).unwrap();
    check(
        "backdrop-quality",
        &backdrop_answer(&scene::backdrop(&drawn, &SCENE)),
    );
    check(
        "backdrop-light",
        &light_answer(&scene::light_backdrop(&drawn, &SCENE).unwrap()),
    );
}

#[test]
fn battlers() {
    for hue in [0, 120] {
        let drawn = battle::battler(&game(&["Monster", "battler.png"]), hue).unwrap();
        check(
            &format!("battler-{hue}"),
            &battler_answer(&scene::battler(&drawn, &SCENE).unwrap()),
        );
    }
}

#[test]
fn animations() {
    let text = std::fs::read_to_string(game(&["animations.json"])).unwrap();
    let animations: Vec<Animation> = serde_json::from_str(&text).unwrap();
    let sheet = picture::read_rm2k(&game(&["Battle", "sheet.png"])).unwrap();
    let g = animation::Geometry {
        side: 64,
        colors: 15,
        alpha_min: 128,
    };
    for a in &animations {
        let answer =
            animation::convert(a, &sheet, &g).map_or(Value::Null, |c| animation_answer(&c));
        check(&format!("animation-{}", a.id), &answer);
    }
}
