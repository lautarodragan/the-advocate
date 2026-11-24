//! The battle's model over a small game built to touch the edges: every
//! request answers or is refused, and the refused ones are the ones that
//! must be.
//!
//! The game, in `tests/game/dump`, has actors whose level is past their
//! curves, below 1 and above their cap, who learn a skill twice or one the
//! database does not have, with a weapon that costs SP and armor that does
//! not charge it; skills of every type and scope, a cost of 100, one that
//! ignores defense and ones that only touch parameters; medicines that
//! revive, that only work on the fallen, that only work outside battle;
//! enemies that miss, with a critical, with actions that are dropped for
//! their condition, their switches or their kind, ties in rating and ones
//! that weigh zero; and troops with hidden members, more members than a
//! battle holds, and pages on switches, turns, HP, a variable, with
//! branches, an `else` and a `ControlSwitches` the battle does not know.
//! `battles.json` is four hundred battles played on it, with seeds, and
//! `models.json` twenty-six models asked of it.
//!
//! **The path it guards**: those edges. A Blurred Line's suite plays its
//! battles on the console and holds them against this model, which is
//! what checks what a battle gives; but only with that game's actors,
//! skills and troops, none of which reach most of these. What is checked
//! here is what does not depend on knowing the right numbers: that the
//! model gets through each one —no panic, no overflow in a debug build—,
//! and that it refuses exactly the orders RM2k does not allow, such as a
//! skill `usable_in_battle` says no to (cases 14, 106 and 107 of
//! `battles.json`).

use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::model;
use serde_json::Value;
use std::path::{Path, PathBuf};

fn game() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("game")
}

fn read(name: &str) -> Value {
    let path = game().join(name);
    let text = std::fs::read_to_string(&path).unwrap();
    serde_json::from_str(&text).unwrap()
}

fn check<T>(name: &str, answer: impl Fn(&Db, &Value) -> rm2k_snes_battle::Result<T>) -> usize {
    let db = Db::from_dump(&game().join("dump"), true).unwrap();
    let cases = read(name);
    let cases = cases.as_array().unwrap();
    let mut wrong = Vec::new();
    for (k, case) in cases.iter().enumerate() {
        let refused = case["refused"].as_bool().unwrap();
        match (refused, answer(&db, &case["request"])) {
            (true, Err(_)) | (false, Ok(_)) => {}
            (true, Ok(_)) => wrong.push(format!("case {k}: answered, and it must be refused")),
            (false, Err(e)) => wrong.push(format!("case {k}: refused: {e}")),
        }
    }
    assert!(
        wrong.is_empty(),
        "{} of {} differ:\n{}",
        wrong.len(),
        cases.len(),
        wrong.join("\n")
    );
    cases.len()
}

#[test]
fn every_battle_plays_or_is_refused_as_rm2k_would() {
    let n = check("battles.json", model::simulate);
    assert!(n >= 400, "the battles are {n}");
}

#[test]
fn every_model_answers_or_is_refused() {
    let n = check("models.json", |db, request| {
        model::model(db, &model::ModelRequest::of(request)?)
    });
    assert!(n >= 26, "the models are {n}");
}

#[test]
fn a_battle_without_a_troop_does_not_read_the_troops() {
    let request: Value = serde_json::from_str(r#"{"actors": [{"id": 1}], "steps": []}"#).unwrap();
    assert!(!model::needs_troops(&request));
    let db = Db::from_dump(&game().join("dump"), false).unwrap();
    assert!(db.troops.is_empty());
    let answer = model::simulate(&db, &request).unwrap();
    assert_eq!(answer["battle"]["actors"][0]["name"], "Actor1");
}
