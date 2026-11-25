//! `stage::tables` as the converter calls it: the files it answers, and
//! what it says no with.

use rm2k_snes_battle::stage::{self, Files};
use rm2k_snes_battle::{Bad, Request};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-battle-stage-{name}-{}",
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
    write(
        &dir.join("dump/ditto.json"),
        &json!({"ditto": 2, "view": "resolved"}),
    );
    write(&dir.join("dump/db/actors.json"), &Value::Array(actors));
    write(
        &dir.join("dump/maps.json"),
        &json!({"maps": [{"id": 1, "type": 1, "parent_map": 0, "encounter_steps": 30,
                          "encounters": [{"id": 1, "troop_id": 6}],
                          "area_rect": {"l": 0, "t": 0, "r": 0, "b": 0}}]}),
    );
}

fn request(party: &[i64]) -> Request {
    serde_json::from_value(
        json!({"party": party, "maps": [{"id": 1, "width": 20, "height": 15}],
               "encounter_steps": null, "tree_nodes": []}),
    )
    .unwrap()
}

/// `stage::tables` on the game in `dir` for a cartridge of `party`.
fn run(dir: &Path, party: &[i64]) -> Result<Files, Bad> {
    stage::tables(&dir.join("dump"), &request(party))
}

fn text(files: &Files, name: &str) -> String {
    String::from_utf8(files[name].clone()).unwrap()
}

/// What it said no with; a yes or a bad call fails the test.
fn no(done: Result<Files, Bad>) -> String {
    match done {
        Err(Bad::Answer(why)) => why,
        Err(bad) => panic!("a bad call, not a no: {bad}"),
        Ok(_) => panic!("a yes"),
    }
}

#[test]
fn tables_answers_the_two_pieces_and_the_answer() {
    let dir = scratch("tables");
    game(&dir, 3);
    let files = run(&dir, &[2]).unwrap_or_else(|bad| panic!("{bad}"));
    let experience = text(&files, "experience.inc");
    assert!(experience.starts_with(".segment \"RODATA\"\nEXP_K = 1\n"));
    // Actors 0 to 3; only 2 has a slot.
    assert!(experience.contains("actor_exp_k:\n    .byte 255, 255, 0, 255\n"));
    let encounters = text(&files, "encounters.inc");
    assert!(encounters.starts_with(".block 2\nenc_map:\n    .word 0\n"));
    let answer: Value = serde_json::from_str(&text(&files, "battle.json")).unwrap();
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
    let why = no(run(&dir, &(1..=129).collect::<Vec<_>>()));
    assert!(
        why.contains("129 actors with experience don't fit"),
        "{why}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// A field the dump leaves out holds the format's default, as Ditto reads
/// it; one that cannot be what the format says is a no, and the message
/// says which file.
#[test]
fn a_broken_dump_is_a_no_that_says_where() {
    let dir = scratch("broken");
    game(&dir, 1);
    write(
        &dir.join("dump/db/actors.json"),
        &json!([{"id": 1, "parameters": "none"}]),
    );
    let why = no(run(&dir, &[1]));
    assert!(why.contains("actors.json"), "{why}");
    std::fs::remove_dir_all(&dir).unwrap();
}
