//! The runtime, `runtime/`, uses only declared opcodes and declares
//! none by hand.
//!
//! A `cmp #OP_X` against something nobody declares does not assemble...
//! today. But the day someone puts an equate back by hand, it would assemble
//! again reading a number written twice, which is what this crate leaves
//! behind. Both bytecodes together: to the ROM they are a single symbol
//! space.

use std::collections::BTreeSet;
use std::path::Path;

use rm2k_snes_bytecode::{events, music};

/// Every `.s` of the runtime, which is the reader of both bytecodes.
fn runtime() -> String {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../runtime");
    let mut text = String::new();
    let mut paths: Vec<_> = std::fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("{}: {e}", dir.display()))
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.extension().is_some_and(|e| e == "s"))
        .collect();
    paths.sort();
    for path in paths {
        text.push_str(&std::fs::read_to_string(&path).unwrap());
        text.push('\n');
    }
    text
}

/// The `OP_…` names in `text` that start right after `before` and are not
/// in a comment.
fn names_after(text: &str, before: &str) -> BTreeSet<String> {
    let mut found = BTreeSet::new();
    for line in text.lines() {
        let code = line.split(';').next().unwrap();
        let mut rest = code;
        while let Some(at) = rest.find(before) {
            rest = &rest[at + before.len()..];
            if !rest.starts_with("OP_") {
                continue;
            }
            let end = rest
                .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_'))
                .unwrap_or(rest.len());
            found.insert(rest[..end].to_string());
        }
    }
    found
}

#[test]
fn the_runtime_uses_only_declared_opcodes_and_declares_none() {
    let source = runtime();
    // Only the uses as an operand: bare names in comments do not count.
    let used = names_after(&source, "#");
    assert!(
        !used.is_empty(),
        "not a single use of an opcode in the runtime"
    );
    let declared: BTreeSet<String> = events::BYTECODE
        .opcodes
        .iter()
        .chain(music::BYTECODE.opcodes)
        .map(|o| o.name.to_string())
        .collect();
    let undeclared: Vec<_> = used.difference(&declared).collect();
    assert!(
        undeclared.is_empty(),
        "the runtime compares against {undeclared:?}, which is not declared in rm2k-snes-bytecode"
    );

    let by_hand: Vec<_> = source
        .lines()
        .map(|line| line.split(';').next().unwrap().trim_start())
        .filter(|code| {
            code.starts_with("OP_")
                && code
                    .split_once('=')
                    .is_some_and(|(name, _)| !name.trim().contains(char::is_whitespace))
        })
        .collect();
    assert!(
        by_hand.is_empty(),
        "the runtime declares an opcode by hand: {by_hand:?}; it goes in rm2k-snes-bytecode"
    );
}
