//! The binary as a caller sees it: what it writes, and with which exit
//! code when it says no or the call is wrong.

use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-events-cli-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(command: &str, data: &Path, request: &Path, out: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_rm2k-snes-events"))
        .arg(command)
        .args(["--data", data.to_str().unwrap()])
        .args(["--request", request.to_str().unwrap()])
        .args(["--out", out.to_str().unwrap()])
        .output()
        .unwrap()
}

#[test]
fn both_calls_write_their_answer() {
    let dir = scratch("answer");
    for (command, request) in [("scan", "scan.json"), ("compile", "compile.json")] {
        let out = dir.join(command);
        let done = run(command, &here().join("game"), &here().join(request), &out);
        assert!(
            done.status.success(),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
        let answer: Value =
            serde_json::from_str(&std::fs::read_to_string(out.join("events.json")).unwrap())
                .unwrap();
        assert_eq!(answer["maps"].as_array().unwrap().len(), 3);
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_request_that_is_not_there_is_a_wrong_call() {
    let dir = scratch("usage");
    let done = run(
        "scan",
        &here().join("game"),
        &dir.join("nowhere.json"),
        &dir.join("out"),
    );
    assert_eq!(done.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&done.stderr).starts_with("rm2k-snes-events: "));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_text_the_font_does_not_have_is_a_no() {
    let dir = scratch("font");
    let mut request: Value =
        serde_json::from_str(&std::fs::read_to_string(here().join("compile.json")).unwrap())
            .unwrap();
    request["test_commands"] = serde_json::json!([
        {"code": 10110, "indent": 0, "string": "¡Olé! アー", "parameters": []}
    ]);
    let path = dir.join("request.json");
    std::fs::write(&path, request.to_string()).unwrap();
    let done = run("compile", &here().join("game"), &path, &dir.join("out"));
    assert_eq!(done.status.code(), Some(1));
    // In a game page it stops only that page; a test page has to compile
    // whole. `¡` and `é` have a plain stand-in, the katakana do not.
    let e = String::from_utf8_lossy(&done.stderr);
    assert!(e.contains("text box does not compile"), "{e}");
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_dump_that_is_not_one_is_a_no() {
    let dir = scratch("dump");
    let done = run("scan", &dir, &here().join("scan.json"), &dir.join("out"));
    assert_eq!(done.status.code(), Some(1));
    std::fs::remove_dir_all(&dir).unwrap();
}

/// The events of map 1's pages in the answer to `request`, by index.
fn page_events(name: &str, request: &Value) -> Vec<u64> {
    let dir = scratch(name);
    let path = dir.join("request.json");
    std::fs::write(&path, request.to_string()).unwrap();
    let done = run("compile", &here().join("game"), &path, &dir.join("out"));
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let answer: Value = serde_json::from_str(
        &std::fs::read_to_string(dir.join("out").join("events.json")).unwrap(),
    )
    .unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
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
    let mut request: Value =
        serde_json::from_str(&std::fs::read_to_string(here().join("compile.json")).unwrap())
            .unwrap();
    let whole = page_events("whole", &request);
    assert!(whole.contains(&3), "{whole:?}");
    request["dropped_events"] = serde_json::json!({"1": [4]});
    let without = page_events("without", &request);
    let expected: Vec<u64> = whole
        .iter()
        .filter(|&&e| e != 3)
        .map(|&e| if e > 3 { e - 1 } else { e })
        .collect();
    assert_eq!(without, expected);
}
