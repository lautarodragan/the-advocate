//! `stage::compile`, as the converter calls it: from the small game's dump
//! and a request to the answer, and a no when the request cannot be
//! compiled.

use rm2k_snes_events::{stage, Bad};
use serde_json::Value;
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn compile_json() -> Value {
    serde_json::from_str(&std::fs::read_to_string(here().join("compile.json")).unwrap()).unwrap()
}

/// What `stage::compile` answers to `request`, as JSON,
/// or what it said no with.
fn compile(request: &Value) -> Result<Value, Bad> {
    let asked = serde_json::from_value(request.clone()).unwrap();
    stage::compile(&here().join("game"), &asked).map(|answer| serde_json::to_value(answer).unwrap())
}

#[test]
fn it_answers_every_map_of_the_request() {
    let answer = compile(&compile_json()).unwrap_or_else(|bad| panic!("{bad}"));
    assert_eq!(answer["maps"].as_array().unwrap().len(), 3);
}

#[test]
fn a_text_the_font_does_not_have_is_a_no() {
    let mut request = compile_json();
    request["test_commands"] = serde_json::json!([
        {"code": 10110, "indent": 0, "string": "¡Olé! アー", "parameters": []}
    ]);
    // In a game page it stops only that page; a test page has to compile
    // whole. `¡` and `é` have a plain stand-in, the katakana do not.
    match compile(&request) {
        Err(Bad::Answer(e)) => assert!(e.contains("text box does not compile"), "{e}"),
        other => panic!("not a no: {other:?}"),
    }
}

/// The events of map 1's pages in the answer to `request`, by index.
fn page_events(request: &Value) -> Vec<u64> {
    let answer = compile(request).unwrap_or_else(|bad| panic!("{bad}"));
    let map = answer["maps"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["id"] == 1)
        .unwrap();
    map["pages"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| p["event"].as_u64().unwrap())
        .collect()
}

#[test]
fn a_dropped_event_is_not_in_the_map() {
    // Map 1's events are ids 1, 2, 4, 7, 8 and 9, after the test page's,
    // which is index 0: without 4, index 3, its pages are gone and the
    // ones after it are numbered one less.
    let mut request = compile_json();
    let whole = page_events(&request);
    assert!(whole.contains(&3), "{whole:?}");
    request["dropped_events"] = serde_json::json!({"1": [4]});
    let without = page_events(&request);
    let expected: Vec<u64> = whole
        .iter()
        .filter(|&&e| e != 3)
        .map(|&e| if e > 3 { e - 1 } else { e })
        .collect();
    assert_eq!(without, expected);
}
