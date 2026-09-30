//! A text box's escape tail, against the copy `rm2k-snes-text` reflows
//! boxes for the window around: both answer what `escapes.json` says.
//! A change on one side only goes red on that side.

use rm2k_snes_events::messages::escape_tail;
use serde_json::{json, Value};

#[test]
fn the_tails_are_the_ones_the_python_cuts_too() {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/escapes.json");
    let data: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    let cases = data["cases"].as_array().unwrap();
    assert!(cases.len() > 10);
    for case in cases {
        let lines: Vec<String> = case["lines"]
            .as_array()
            .unwrap()
            .iter()
            .map(|l| l.as_str().unwrap().to_string())
            .collect();
        let got = match escape_tail(&lines) {
            Ok((lines, pauses, close)) => json!([lines, pauses, close]),
            Err(_) => Value::Null,
        };
        assert_eq!(got, case["answer"], "{lines:?}");
    }
}
