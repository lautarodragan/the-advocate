//! A cartridge's plan and its `.msu`, against what the Python gave for them.
//!
//! Until 2026-09-30 the converter decided in Python which songs each map's
//! package carries, which one may be playing when it loads, and wrote the
//! `.msu`. It was deleted once the two gave the same bytes for three whole
//! cartridges of a real game; what is left of it is here: the SHA-256 of
//! what it wrote for the small game of `cartridge.json` —six maps, one
//! without pages, exit songs, separate ones, a jump that never happens, a
//! jump that carries what came in and one that carries its song; with and
//! without title, Game Over and battle— and of the `.msu` it built for two
//! backdrops and three packages' sound effects.
//!
//! **If one of these changes, what the cartridge carries changed.** The
//! hashes are not to be regenerated to make a test pass: the Python that
//! produced them is gone, and with it the only independent answer.

use rm2k_snes_audio::cartridge::{self, Cartridge, Songs};
use rm2k_snes_audio::msu::{Effects, PackageEffects, Version};
use rm2k_snes_audio::pyjson;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

const GAME: &str = include_str!("cartridge.json");

fn sha(data: &[u8]) -> String {
    Sha256::digest(data).iter().map(|b| format!("{b:02x}")).collect()
}

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len()).step_by(2).map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap()).collect()
}

fn cartridge(name: &str) -> Cartridge {
    let game: Value = serde_json::from_str(GAME).unwrap();
    let c = &game["cartridge"][name];
    let strings = |v: &Value| -> Vec<String> {
        v.as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect()
    };
    let text = |v: &Value| v.as_str().map(String::from);
    Cartridge {
        songs: Songs::from_json(&game["songs"]).unwrap(),
        maps: c["maps"].as_array().unwrap().iter().map(|m| m.as_i64().unwrap()).collect(),
        map_music: strings(&c["map_music"]),
        start: c["start"].as_u64().unwrap() as usize,
        title: text(&c["title"]),
        game_over: text(&c["game_over"]),
        apart: c["apart"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| (p[0].as_i64().unwrap(), strings(&p[1]).into_iter().collect::<HashSet<_>>()))
            .collect::<HashMap<_, _>>(),
        not_given: c["not_given"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| (p[0].as_i64().unwrap(), p[1].as_i64().unwrap()))
            .collect(),
        system_songs: strings(&c["system_songs"]),
        measuring_headroom: c["measuring_headroom"].as_f64(),
        decompress_frames: c["decompress_frames"].as_f64().unwrap(),
    }
}

#[test]
fn the_job_is_the_one_the_python_built() {
    for (name, expected) in [
        ("full", "fc543ffcdf37beecf8899e9097ec3dc21236ce3bbdb2402b0b172f4c10ea5e2d"),
        ("sparse", "5e35cf376546a9a28c7003116f82a49f2c7fae43ab9683f5b9ab5386e747f379"),
    ] {
        let plan = cartridge::plan(&cartridge(name)).unwrap();
        assert_eq!(sha(pyjson::to_string(&plan.job).as_bytes()), expected, "{name}");
    }
}

#[test]
fn the_msu_is_the_one_the_python_built() {
    let game: Value = serde_json::from_str(GAME).unwrap();
    let m = &game["msu"];
    let backdrops: Vec<(Vec<u8>, Vec<u8>)> = m["backdrops"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| (unhex(p[0].as_str().unwrap()), unhex(p[1].as_str().unwrap())))
        .collect();
    let indices =
        |v: &Value| -> Vec<usize> { v.as_array().unwrap().iter().map(|i| i.as_u64().unwrap() as usize).collect() };
    let quality = Effects {
        versions: m["versions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| Version { effect: String::new(), rate: 0, data: unhex(v.as_str().unwrap()) })
            .collect(),
        packages: m["packages"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| PackageEffects {
                name: p["name"].as_str().unwrap().into(),
                versions: indices(&p["versions"]),
                rows: indices(&p["rows"]),
                pitches: p["pitches"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|q| (q[0].as_u64().unwrap() as usize, q[1].as_i64().unwrap()))
                    .collect(),
            })
            .collect(),
        rates: Vec::new(),
    };
    let msu = cartridge::msu(&backdrops, &quality, b"TEST").unwrap();
    assert_eq!(sha(&msu.blob), "3abd8f1c1580d53a6b36d5751aa12d1a0d42769c593e9123089bf26430f771de");
    assert_eq!(sha(msu.inc.as_bytes()), "607f647d6a8ebd866f7a4663a4d621b1348ae1a3106b002b685916c4d5c3ade2");
    assert_eq!((msu.backdrops, msu.effects), (2, 3));
}
