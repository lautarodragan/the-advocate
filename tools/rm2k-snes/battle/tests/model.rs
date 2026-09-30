//! The battle's model, its text screen and the battle played, against what
//! the Python they replace answered.
//!
//! Until 2026-09-30 the converter asked a model in Python for these, and
//! the tests that compare a console's battle played the battle with it. It
//! was deleted once both gave the same on every cartridge and on thousands
//! of random battles of a whole game; what is left of it is here: a small
//! game in `tests/game/dump`, built to touch the edges, and for each
//! request in `tests/game/` the SHA-256 of the answer the Python gave, or
//! `null` where it refused.
//!
//! The game has actors whose level is past their curves, below 1 and
//! above their cap, who learn a skill twice or one the database does not
//! have, with a weapon that costs SP and armor that does not charge it;
//! skills of every type and scope, a cost of 100, one that ignores defense
//! and ones that only touch parameters; medicines that revive, that only
//! work on the fallen, that only work outside battle; enemies that miss,
//! with a critical, with actions that are dropped for their condition,
//! their switches or their kind, ties in rating and ones that weigh zero;
//! and troops with hidden members, more members than a battle holds, and
//! pages on switches, turns, HP, a variable, with branches, an `else` and
//! a `ControlSwitches` the battle does not know.
//!
//! **If one of these changes, the battle changed.** The hashes are not to
//! be regenerated to make a test pass: the Python that produced them is
//! gone, and with it the only independent answer.

use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::model;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

fn game() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests").join("game")
}

fn read(name: &str) -> Value {
    let path = game().join(name);
    let text = std::fs::read_to_string(&path).unwrap();
    serde_json::from_str(&text).unwrap()
}

fn db() -> Db {
    Db::from_dump(&game().join("dump"), true).unwrap()
}

/// The answer with its keys sorted, compact: what the Python hashed. The
/// order does not depend on whether `serde_json` keeps insertion order,
/// which another crate of the workspace turns on.
fn sorted(v: &Value) -> Value {
    match v {
        Value::Object(o) => {
            let mut keys: Vec<&String> = o.keys().collect();
            keys.sort();
            let mut out = Map::new();
            for k in keys {
                out.insert(k.clone(), sorted(&o[k]));
            }
            Value::Object(out)
        }
        Value::Array(a) => Value::Array(a.iter().map(sorted).collect()),
        _ => v.clone(),
    }
}

fn sha256(v: &Value) -> String {
    let text = serde_json::to_string(&sorted(v)).unwrap();
    Sha256::digest(text.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn check(name: &str, answer: fn(&Db, &Value) -> rm2k_snes_battle::Result<Value>) -> usize {
    let db = db();
    let cases = read(name);
    let cases = cases.as_array().unwrap();
    let mut wrong = Vec::new();
    for (k, case) in cases.iter().enumerate() {
        let got = answer(&db, &case["request"]);
        let ok = match (&case["sha256"], &got) {
            (Value::Null, Err(_)) => true,
            (Value::String(expected), Ok(v)) => *expected == sha256(v),
            _ => false,
        };
        if !ok {
            wrong.push(format!(
                "case {k}: expected {}, got {}",
                case["sha256"],
                match got {
                    Ok(v) => sha256(&v),
                    Err(e) => format!("no: {e}"),
                }
            ));
        }
    }
    assert!(wrong.is_empty(), "{} of {} differ:\n{}", wrong.len(), cases.len(), wrong.join("\n"));
    cases.len()
}

#[test]
fn every_battle_plays_as_the_pythons() {
    let n = check("battles.json", model::simulate);
    assert!(n >= 400, "the battles are {n}");
}

#[test]
fn every_model_is_the_pythons() {
    let n = check("models.json", model::model);
    assert!(n >= 26, "the models are {n}");
}

#[test]
fn the_victory_lines_are_the_pythons() {
    let case = read("lines.json");
    let got = model::lines(&db(), &case["request"]).unwrap();
    assert_eq!(got, case["answer"]);
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
