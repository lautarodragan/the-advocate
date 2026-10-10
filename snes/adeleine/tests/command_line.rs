//! The executable: the request it reads, the answer it writes, and the exit
//! code that tells "no" from "wrong".

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("adeleine-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(name: &str, command: &str, request: &str) -> (Output, PathBuf) {
    let dir = scratch(name);
    let path = dir.join("request.json");
    fs::write(&path, request).unwrap();
    let out = dir.join("out");
    let output = Command::new(env!("CARGO_BIN_EXE_adeleine"))
        .args([command, "--request"])
        .arg(&path)
        .arg("--out")
        .arg(&out)
        .output()
        .unwrap();
    (output, out)
}

#[test]
fn merge_writes_the_mapping_in_the_order_given() {
    let (output, out) = run(
        "merge",
        "merge",
        r#"{"counts": [[2, 0, 0, 1], [0, 0, 0, 9], [31, 31, 31, 5]], "keep": 2}"#,
    );
    assert!(output.status.success(), "{output:?}");
    assert_eq!(
        fs::read_to_string(out.join("merge.json")).unwrap(),
        r#"{"mapping":[[0,0,0],[0,0,0],[31,31,31]],"merges":[[[2,0,0],[0,0,0],1]]}"#
    );
}

#[test]
fn pack_answers_null_when_it_does_not_fit() {
    let (output, out) = run(
        "pack",
        "pack",
        r#"{"tiles": [[[1, 1, 1], [2, 2, 2]], [[3, 3, 3]]], "palettes": 1, "per_palette": 2}"#,
    );
    assert!(output.status.success(), "{output:?}");
    assert_eq!(
        fs::read_to_string(out.join("pack.json")).unwrap(),
        r#"{"palettes":null}"#
    );
}

#[test]
fn reduce_writes_local_mappings_merges_and_palettes() {
    let (output, out) = run(
        "reduce",
        "reduce",
        r#"{"counts": [[1, 1, 1, 4], [2, 2, 2, 1], [3, 3, 3, 8]],
            "tiles": [[[1, 1, 1], [2, 2, 2]], [[3, 3, 3]]], "palettes": 1, "per_palette": 2}"#,
    );
    assert!(output.status.success(), "{output:?}");
    assert_eq!(
        fs::read_to_string(out.join("reduce.json")).unwrap(),
        r#"{"merges":[[0,[2,2,2],[1,1,1],1]],"palettes":[[[1,1,1],[3,3,3]]],"tiles":[{"mapping":[[1,1,1],[1,1,1]],"palette":0},{"mapping":[[3,3,3]],"palette":0}]}"#
    );
}

#[test]
fn not_reducible_is_a_no() {
    let (output, _) = run(
        "no",
        "reduce",
        r#"{"counts": [[1, 1, 1, 4]], "tiles": [[[1, 1, 1]]], "palettes": 0}"#,
    );
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(
        String::from_utf8_lossy(&output.stderr),
        "adeleine: The palette could not be reduced enough.\n"
    );
}

#[test]
fn a_bad_request_is_misuse() {
    let (output, _) = run("bad", "merge", r#"{"counts": [[1, 1, 1]], "keep": 1}"#);
    assert_eq!(output.status.code(), Some(2));
    let (output, _) = run("unknown", "merge", r#"{"counts": [], "keep": 1, "kep": 2}"#);
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("\"kep\""));
}
