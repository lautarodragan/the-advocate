//! The tables against the ones they replace.
//!
//! Until 2026-09-29 these tables were written by the converter in Python
//! (`battle_tables.py`, with the curves of `experience.py`). It was deleted
//! once both gave the same bytes on every cartridge of a whole game; what is
//! left of it is here: the SHA-256 of the text it wrote for a game built
//! inside this file, which needs no real game.
//!
//! The game is built to touch every edge: actors whose curve hits the
//! experience cap, whose levels are out of range —initial 0, initial past
//! the final, final 0 and past 50—, with parameters shorter than 50 levels,
//! missing or negative; two actors with the same experience curve, which
//! share its row; a party with an actor the game does not have and one
//! twice; and a party with nobody. For the encounters: maps with their own
//! troops, with areas, with both, with steps 0 and 1, a map the tree does
//! not have, an area without troops, an area inside an area, a node the
//! request adds, and the steps a test cartridge forces.
//!
//! **If one of these changes, a byte of the cartridge changed.** The
//! hashes are not to be regenerated to make a test pass: the Python that
//! produced them is gone, and with it the only independent answer.

use rm2k_snes_battle::{Game, Request, Tables};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

const CURVES: [&str; 6] = ["maxhp", "maxsp", "attack", "defense", "spirit", "agility"];

fn params(actor: i64, length: i64) -> Value {
    let mut curves = serde_json::Map::new();
    for (j, curve) in CURVES.iter().enumerate() {
        let j = j as i64;
        let values: Vec<i64> = (0..length)
            .map(|i| {
                ((i + 1) * (j + 2) * 13 + actor * 7) % 1500 - if (i + j) % 7 == 0 { 200 } else { 0 }
            })
            .collect();
        curves.insert(curve.to_string(), json!(values));
    }
    Value::Object(curves)
}

/// id, exp_base, exp_inflation, exp_correction, initial_level,
/// final_level, and how many levels of parameters.
const ACTORS: [(i64, i64, i64, i64, i64, i64, i64); 7] = [
    (1, 33, 29, 0, 1, 50, 50),
    (2, 10, 50, -3, 0, 20, 20),
    (3, 33, 29, 0, 5, 50, 50),
    (5, 25, 30, 0, 3, 0, 0),
    (7, 50, 10, 40, 60, 99, 50),
    (8, 1, 0, 0, 2, 2, 2),
    (12, 10, 50, -3, 20, 20, 7),
];

fn actor(
    &(id, base, inflation, correction, initial, last, length): &(i64, i64, i64, i64, i64, i64, i64),
) -> Value {
    json!({"id": id, "name": format!("A{id}"), "parameters": params(id, length),
           "initial_level": initial, "final_level": last,
           "exp_base": base, "exp_inflation": inflation,
           "exp_correction": correction})
}

fn node(id: i64, kind: i64, parent: i64, steps: i64, troops: &[i64], rect: [i64; 4]) -> Value {
    // With their ids out of order, as a dump could hold them: the reader
    // sorts by id.
    let encounters: Vec<Value> = troops
        .iter()
        .enumerate()
        .rev()
        .map(|(k, t)| json!({"id": k + 1, "troop_id": t}))
        .collect();
    json!({"id": id, "name": format!("M{id}"), "type": kind, "parent_map": parent,
           "encounter_steps": steps, "encounters": encounters,
           "area_rect": {"l": rect[0], "t": rect[1], "r": rect[2], "b": rect[3]}})
}

const NONE: [i64; 4] = [0, 0, 0, 0];

fn tree() -> Vec<Value> {
    vec![
        node(0, 0, 0, 25, &[], NONE),
        node(1, 1, 0, 25, &[3, 1, 4], NONE),
        node(2, 1, 0, 30, &[], NONE),
        node(3, 1, 0, 0, &[2], NONE),
        node(4, 1, 0, 85, &[9, 9], NONE),
        node(5, 1, 0, 1, &[1], NONE),
        node(6, 1, 0, 25, &[], NONE),
        node(10, 2, 2, 25, &[5, 6], [2, 3, 10, 8]),
        node(11, 2, 2, 25, &[], [0, 0, 4, 4]),
        node(12, 2, 10, 25, &[7], [3, 3, 5, 5]),
        node(13, 2, 4, 25, &[8], [5, 5, 20, 20]),
        node(14, 2, 4, 25, &[2, 3], [0, 10, 40, 30]),
    ]
}

/// The cartridge's maps: id, width, height. 7 is not in the tree, and 20
/// only in the request.
const MAPS: [(i64, i64, i64); 8] = [
    (4, 40, 30),
    (1, 20, 15),
    (7, 10, 10),
    (2, 30, 20),
    (3, 10, 10),
    (5, 8, 8),
    (6, 12, 12),
    (20, 16, 16),
];

const PARTY: [i64; 9] = [8, 3, 1, 4, 12, 3, 7, 5, 2];

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-battle-python-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("dump").join("db")).unwrap();
    dir
}

fn write(path: &Path, value: &Value) {
    std::fs::write(path, serde_json::to_string(value).unwrap()).unwrap();
}

/// The game and its request, written as a caller would, and read back.
fn tables(name: &str, party: &[i64], steps: Option<i64>) -> Tables {
    let dir = scratch(name);
    let dump = dir.join("dump");
    write(&dump.join("ditto.json"), &json!({"ditto": 2, "view": "resolved"}));
    write(
        &dump.join("db").join("actors.json"),
        &Value::Array(ACTORS.iter().map(actor).collect()),
    );
    write(&dump.join("maps.json"), &json!({"maps": tree()}));
    let maps: Vec<Value> = MAPS
        .iter()
        .map(|(id, w, h)| json!({"id": id, "width": w, "height": h}))
        .collect();
    write(
        &dir.join("request.json"),
        &json!({"party": party, "maps": maps, "encounter_steps": steps,
                "tree_nodes": [node(20, 1, 0, 40, &[11], NONE)]}),
    );
    let mut game = Game::from_dump(&dump).unwrap();
    let request = Request::read(&dir.join("request.json"), &mut game).unwrap();
    let tables = Tables::new(&game, &request).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    tables
}

fn sha256(text: &str) -> String {
    Sha256::digest(text.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

#[test]
fn the_experience_of_a_party_is_the_pythons() {
    let t = tables("party", &PARTY, None);
    assert_eq!(
        t.slots,
        [1, 2, 3, 3, 5, 7, 8, 12].map(Some).to_vec(),
        "the slots"
    );
    assert_eq!(
        sha256(&t.experience),
        "fabb6eec9249205508b2f92faa5f898d4e8c7b4e34839fdf430045b225c7ec5f"
    );
}

#[test]
fn a_party_of_nobody_still_has_one_slot() {
    let t = tables("nobody", &[], None);
    assert_eq!(t.slots, vec![None]);
    assert_eq!(
        sha256(&t.experience),
        "10ebff53b00bfcfb2709778253167df528b353ca6add8506b691063260a0563b"
    );
}

#[test]
fn the_encounters_of_the_game_are_the_pythons() {
    let t = tables("game", &PARTY, None);
    let e = &t.encounters;
    assert_eq!(e.per_map, [0, 1, 255, 2, 255, 3, 255, 4]);
    assert_eq!(e.troops, [9, 9, 8, 2, 3, 3, 1, 4, 5, 6, 1, 11]);
    assert_eq!((e.bases.len(), e.zones.len()), (5, 7));
    assert_eq!(
        sha256(&e.tables()),
        "8bec72779043d311c16dd8c8453f64adff00f058363e1f0f175834fc0c2be860"
    );
}

#[test]
fn the_steps_of_a_test_cartridge_are_the_pythons() {
    // Map 3 has troops and steps 0, which is off; forced to 3, it gets a
    // record.
    let t = tables("test", &PARTY, Some(3));
    let e = &t.encounters;
    assert_eq!(e.per_map, [0, 1, 255, 2, 3, 4, 255, 5]);
    assert_eq!(e.troops, [9, 9, 8, 2, 3, 3, 1, 4, 5, 6, 2, 1, 11]);
    assert_eq!((e.bases.len(), e.zones.len()), (6, 8));
    assert_eq!(
        sha256(&e.tables()),
        "696835ab49952e068c0cc17f5f76bb5c1ef57b6171c1289036f2b66ff0645067"
    );
}
