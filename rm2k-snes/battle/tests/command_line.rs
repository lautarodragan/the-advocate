//! The binary as a caller sees it: what it writes, and with which exit
//! code when it says no or the call is wrong.

use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-battle-cli-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("dump").join("db")).unwrap();
    dir
}

fn write(path: &Path, value: &Value) {
    std::fs::write(path, serde_json::to_string(value).unwrap()).unwrap();
}

fn curves() -> Value {
    json!({"maxhp": [10, 20], "maxsp": [], "attack": [], "defense": [1],
           "spirit": [2], "agility": [3]})
}

/// A game of `actors` actors, numbered from 1, and a map with one troop.
fn game(dir: &Path, actors: i64) {
    let actors: Vec<Value> = (1..=actors)
        .map(|id| {
            json!({"id": id, "parameters": curves(), "initial_level": 1,
                   "final_level": 10, "exp_base": 20, "exp_inflation": 30,
                   "exp_correction": 0})
        })
        .collect();
    // What makes the directory a Ditto dump, and which view it is.
    write(&dir.join("dump/ditto.json"), &json!({"ditto": 2, "view": "resolved"}));
    write(&dir.join("dump/db/actors.json"), &Value::Array(actors));
    write(
        &dir.join("dump/maps.json"),
        &json!({"maps": [{"id": 1, "type": 1, "parent_map": 0, "encounter_steps": 30,
                          "encounters": [{"id": 1, "troop_id": 6}],
                          "area_rect": {"l": 0, "t": 0, "r": 0, "b": 0}}]}),
    );
}

fn request(dir: &Path, party: &[i64]) {
    write(
        &dir.join("request.json"),
        &json!({"party": party, "maps": [{"id": 1, "width": 20, "height": 15}],
                "encounter_steps": null, "tree_nodes": []}),
    );
}

fn run(dir: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_rm2k-snes-battle"))
        .arg("tables")
        .args(["--data", dir.join("dump").to_str().unwrap()])
        .args(["--request", dir.join("request.json").to_str().unwrap()])
        .args(["--out", dir.join("out").to_str().unwrap()])
        .output()
        .unwrap()
}

#[test]
fn tables_writes_the_two_pieces_and_the_answer() {
    let dir = scratch("tables");
    game(&dir, 3);
    request(&dir, &[2]);
    let out = run(&dir);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let experience = std::fs::read_to_string(dir.join("out/experience.inc")).unwrap();
    assert!(experience.starts_with(".segment \"RODATA\"\nEXP_K = 1\n"));
    // Actors 0 to 3; only 2 has a slot.
    assert!(experience.contains("actor_exp_k:\n    .byte 255, 255, 0, 255\n"));
    let encounters = std::fs::read_to_string(dir.join("out/encounters.inc")).unwrap();
    assert!(encounters.starts_with(".block 2\nenc_map:\n    .word 0\n"));
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(dir.join("out/battle.json")).unwrap())
            .unwrap();
    assert_eq!(
        answer,
        json!({"experience": {"slots": [2]},
               "encounters": {"per_map": [0], "records": 1, "zones": 1, "troops": [6]}})
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_party_too_big_for_the_save_is_a_no() {
    // 129 slots are 516 bytes, and the save has 512.
    let dir = scratch("too-big");
    game(&dir, 129);
    request(&dir, &(1..=129).collect::<Vec<_>>());
    let out = run(&dir);
    assert_eq!(out.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("129 actors with experience don't fit"),
        "{stderr}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_missing_request_is_a_bad_call() {
    let dir = scratch("missing");
    game(&dir, 1);
    let out = run(&dir);
    assert_eq!(out.status.code(), Some(2));
    std::fs::remove_dir_all(&dir).unwrap();
}

/// A field the dump leaves out holds the format's default, as Ditto reads
/// it; one that cannot be what the format says is a no, and the message
/// says which file.
#[test]
fn a_broken_dump_is_a_no_that_says_where() {
    let dir = scratch("broken");
    game(&dir, 1);
    write(&dir.join("dump/db/actors.json"), &json!([{"id": 1, "parameters": "none"}]));
    request(&dir, &[1]);
    let out = run(&dir);
    assert_eq!(out.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(stderr.contains("actors.json"), "{stderr}");
    std::fs::remove_dir_all(&dir).unwrap();
}
