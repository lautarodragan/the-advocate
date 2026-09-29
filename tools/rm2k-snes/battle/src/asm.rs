//! Tables as ca65 reads them.
//!
//! Every table goes with a `.block` in front, which tells the bank packer
//! how many bytes it needs whole on one side of a bank: they are read with
//! `lda f:table, x`, and a table split across a bank reads its second half
//! out of the next one.
//!
//! There are two layouts, and both are the ones the converter wrote before
//! these tables were Rust's: the experience ones break the list every
//! sixteen values, and the encounters' go on a single line. Changing either
//! changes the `.inc` and not the ROM; it is kept so that a cartridge can
//! be compared byte for byte, `.inc` included.

use std::fmt::Write;

fn join(values: &[i64]) -> String {
    values
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<_>>()
        .join(", ")
}

/// `directive` is `.byte`, `.word` or `.dword`, and `width` its bytes: the
/// table takes `width * len`, and never less than one value. Sixteen values
/// per line; an empty table is its label alone.
pub fn table(out: &mut String, label: &str, directive: &str, width: usize, values: &[i64]) {
    writeln!(out, ".block {}", width.max(width * values.len())).unwrap();
    writeln!(out, "{label}:").unwrap();
    for row in values.chunks(16) {
        writeln!(out, "    {directive} {}", join(row)).unwrap();
    }
}

/// A byte table on one line. An empty one gets a `$FF`, so the label still
/// has something under it.
pub fn bytes(out: &mut String, label: &str, values: &[i64]) {
    writeln!(out, ".block {}", values.len().max(1)).unwrap();
    let values = if values.is_empty() {
        "$FF".to_string()
    } else {
        join(values)
    };
    write!(out, "{label}:\n    .byte {values}\n").unwrap();
}

/// A word table on one line. An empty one gets a 0.
pub fn words(out: &mut String, label: &str, values: &[i64]) {
    writeln!(out, ".block {}", (2 * values.len()).max(2)).unwrap();
    let values = if values.is_empty() {
        "0".to_string()
    } else {
        join(values)
    };
    write!(out, "{label}:\n    .word {values}\n").unwrap();
}
