//! Against what the Python this replaced gave for the same pictures: the
//! small game in `tests/game/` —indexed PNGs with gradients and noise, a
//! battler and an animation sheet with their colour key, and three
//! animations in the dump's shape—, each piece converted as the stage
//! does it and compared, as canonical JSON, against the sha256 of what the
//! Python answered on 2026-09-30.
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
const PYTHON: &[(&str, &str)] = &[
    ("fullscreen-0-256", "1d504fb6ccb25a34b987d3a75ccdc919903548180cfd4b125d2b33d0e5eb19a5"),
    ("fullscreen-16-200", "6206fe1e7f2ecad9178e152be8324c7f21aedfb1ceb3da99f30a55e8b487342b"),
    ("picture-100-175", "64c5f73bd42dbee14b362b703354930634fd0f959302f3bc04d68e351ecbb9c9"),
    ("picture-160-120", "5a96c8c9e8d32f0105480c04ffbc084620085e16c41e866fe28151d8bb30cde1"),
    ("backdrop-quality", "785b5b912c60b2a0bba591b89ed09d14ee472e8faaebd30d20b3745e1de6e7ce"),
    ("backdrop-light", "702bf2503245ff79b50d0116393c0f08da81558b889ca7bb7d87a89fb1e028bd"),
    ("battler-0", "2d334ae45be66fbd550f6972fd2f1ac315464ca9d29ffe136033f6949f53ed43"),
    ("battler-120", "b49547e7592ed976655232c999632b84c34b8423e3f57cec4d84db04938d687a"),
    ("animation-1", "0017423419a3c1dd8dcfe7fd24a33158cad613478bf8168be60de532cadcb5bb"),
    ("animation-2", "1833c91b9d5b93e2b86a2ddcb83c0a14586f07e670062a81d12f394dce0fee3c"),
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
    let expected = PYTHON.iter().find(|(k, _)| *k == name).expect(name).1;
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
fn full_screens_are_the_pythons() {
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
fn pictures_are_the_pythons() {
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
fn backdrops_are_the_pythons() {
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
fn battlers_are_the_pythons() {
    for hue in [0, 120] {
        let drawn = battle::battler(&game(&["Monster", "battler.png"]), hue).unwrap();
        check(
            &format!("battler-{hue}"),
            &battler_answer(&scene::battler(&drawn, &SCENE).unwrap()),
        );
    }
}

#[test]
fn animations_are_the_pythons() {
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
