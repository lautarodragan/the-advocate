//! The compiler against the one it replaces.
//!
//! Until 2026-09-29 the event compiler was the converter's Python
//! (`events.py`). It was deleted once both gave the same bytes on every page
//! of every cartridge of a whole game; what is left of it is here: a small
//! game in `tests/game/`, the two requests a caller would send for it
//! —`scan.json` and `compile.json`—, and in `python.json` the SHA-256 of each
//! part of what the Python answered for them, written in this crate's shape.
//! It needs no real game.
//!
//! The game is built to touch as many paths as it can: text boxes with
//! escape tails and one the project rebuilt; choices; the five kinds of
//! branch and the actor's three questions, nested; every `ControlVars` it
//! compiles and the fused "is it on the cell?"; forced routes on the hero
//! and on an event, with sounds, graphics, jumps and diagonals; a battle
//! with its handlers and one without, that loses to a Game Over; both inns;
//! a toggle; calls to a common event, to a map event, to one that does not
//! compile; the picture that took the place and one that did not; a
//! translucent page the project renamed; a page with a condition the ROM
//! cannot evaluate; an automatic page that compiles to nothing; a teleport
//! out of the cartridge; the sound effects decided per map; troop pages
//! with every trigger, one of them shared by two troops; and two test
//! pages, on two maps.
//!
//! **If one of these changes, a byte of a cartridge changed.** The hashes
//! are not to be regenerated to make a test pass: the Python that produced
//! them is gone, and with it the only independent answer.

use rm2k_snes_events::{compile, scan, Game, Request};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn read(name: &str) -> Value {
    let path = here().join(name);
    serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap()
}

/// A value with its objects' keys sorted, as Python's `json.dumps(...,
/// sort_keys=True, separators=(",", ":"), ensure_ascii=False)` writes it,
/// whatever order the map keeps.
fn canonical(v: &Value) -> String {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            let fields: Vec<String> = keys
                .iter()
                .map(|k| format!("{}:{}", Value::String((*k).clone()), canonical(&m[*k])))
                .collect();
            format!("{{{}}}", fields.join(","))
        }
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(canonical).collect::<Vec<_>>().join(",")
        ),
        other => other.to_string(),
    }
}

fn sha256(v: &Value) -> String {
    Sha256::digest(canonical(v).as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// The songs a package's jumps can carry are a set on the Python side: they
/// are compared sorted, with "whatever is playing" first.
fn sorted_jumps(answer: &mut Value) {
    let Some(jumps) = answer
        .pointer_mut("/songs/jumps")
        .and_then(Value::as_array_mut)
    else {
        return;
    };
    for package in jumps {
        for dest in package[1].as_array_mut().unwrap() {
            dest[1]
                .as_array_mut()
                .unwrap()
                .sort_by_key(|s| s.as_i64().unwrap_or(-1));
        }
    }
}

/// `route_targets` came into the page records after the Python was gone,
/// so it is not in its hashes: it is taken out here and has a test of its
/// own, `route_targets_are_the_routes_of_the_code`.
fn without_route_targets(answer: &mut Value) {
    let Some(maps) = answer.get_mut("maps").and_then(Value::as_array_mut) else {
        return;
    };
    for map in maps {
        for page in map["pages"].as_array_mut().into_iter().flatten() {
            page.as_object_mut().unwrap().remove("route_targets");
        }
    }
}

fn check(which: &str, answer: Value) {
    let mut answer = answer;
    sorted_jumps(&mut answer);
    without_route_targets(&mut answer);
    let expected = read("python.json");
    let expected = expected[which].as_object().unwrap();
    let got = answer.as_object().unwrap();
    let mut keys: Vec<&String> = got.keys().collect();
    keys.sort();
    assert_eq!(
        keys,
        expected.keys().collect::<Vec<_>>(),
        "the parts of the answer"
    );
    for (part, hash) in expected {
        assert_eq!(
            sha256(&got[part]),
            hash.as_str().unwrap(),
            "{which}: {part}"
        );
    }
}

/// Who each page sends walking. The answer was checked against the
/// converter's Python rule, `events.route_targets`, before it was deleted:
/// map 1's first page routes the hero and events 1 and 3 —the hero is not
/// an event and does not count—, and the test page on map 3, which the
/// request puts first, sends event 0.
#[test]
fn route_targets_are_the_routes_of_the_code() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let answer = scan(&game(&request), &request).unwrap();
    let mut routed = Vec::new();
    for map in answer["maps"].as_array().unwrap() {
        for page in map["pages"].as_array().unwrap() {
            let targets = page["route_targets"].as_array().unwrap();
            if page["code"].is_null() {
                assert!(targets.is_empty(), "a page without code routes nobody");
            }
            if !targets.is_empty() {
                routed.push((map["id"].clone(), page["event"].clone(), page["page"].clone(), targets.clone()));
            }
        }
    }
    let expected: Vec<(Value, Value, Value, Vec<Value>)> = vec![
        (1.into(), 1.into(), 0.into(), vec![1.into(), 3.into()]),
        (3.into(), 0.into(), 0.into(), vec![0.into()]),
    ];
    assert_eq!(routed, expected);
}

fn game(request: &Request) -> Game {
    Game::from_dump(&here().join("game"), request.patches.clone()).unwrap()
}

#[test]
fn the_scan_is_the_pythons() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    check("scan", scan(&game(&request), &request).unwrap());
}

#[test]
fn the_compilation_is_the_pythons() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    check("compile", compile(&game(&request), &request).unwrap());
}
