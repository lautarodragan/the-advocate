//! The binary as a caller sees it: what `culprits` writes, and with which
//! exit code it says no or the call is wrong. `scan` and `compile` are the
//! converter's, functions: `small_game.rs` and `compile_stage.rs`. Until
//! 2026-11-25 these looked at a `scan` subcommand.

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
fn culprits_writes_its_report() {
    let dir = scratch("answer");
    let out = dir.join("culprits");
    let done = run(
        "culprits",
        &here().join("game"),
        &here().join("scan.json"),
        &out,
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("culprits.json")).unwrap()).unwrap();
    assert!(
        answer["totals"]["maps"]["pages"].as_u64().unwrap() > 0,
        "{answer}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_request_that_is_not_there_is_a_wrong_call() {
    let dir = scratch("usage");
    let done = run(
        "culprits",
        &here().join("game"),
        &dir.join("nowhere.json"),
        &dir.join("out"),
    );
    assert_eq!(done.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&done.stderr).starts_with("rm2k-snes-events: "));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_dump_that_is_not_one_is_a_no() {
    let dir = scratch("dump");
    let done = run(
        "culprits",
        &dir,
        &here().join("scan.json"),
        &dir.join("out"),
    );
    assert_eq!(done.status.code(), Some(1));
    std::fs::remove_dir_all(&dir).unwrap();
}
