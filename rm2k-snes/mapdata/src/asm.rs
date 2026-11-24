//! The two primitives the `.inc` is written with: a data block with its
//! placement declaration, and a symbolic 24-bit pointer; and [`Inc`], the
//! writer the emission puts its tables through.

use std::fmt::{Display, Write};

/// The `.inc` as the emission writes it: its text, and the tables and
/// blocks it carries, each a whole line or lines.
pub struct Inc {
    text: String,
}

impl Inc {
    /// An `.inc` that starts with `text`.
    pub fn new(text: String) -> Inc {
        Inc { text }
    }

    pub fn into_text(self) -> String {
        self.text
    }

    pub fn push_str(&mut self, text: &str) {
        self.text.push_str(text);
    }

    pub fn push(&mut self, c: char) {
        self.text.push(c);
    }

    /// `text` and the end of its line.
    pub fn line(&mut self, text: &str) {
        self.text.push_str(text);
        self.text.push('\n');
    }

    /// A [`block`].
    pub fn block(&mut self, label: impl AsRef<str>, data: &[u8]) {
        self.line(&block(label.as_ref(), data));
    }

    /// A [`msu_block`].
    pub fn msu_block(&mut self, label: impl AsRef<str>, data: &[u8], msu: bool) {
        self.line(&msu_block(label.as_ref(), data, msu));
    }

    /// A [`msu_only_block`].
    pub fn msu_only_block(&mut self, label: impl AsRef<str>, data: &[u8]) {
        self.line(&msu_only_block(label.as_ref(), data));
    }

    /// A table of bytes on one line, declared with its `.block`: what the
    /// tables the console indexes look like. With nothing in it, one `$FF`,
    /// so the label still has a byte under it.
    pub fn bytes<T: Display>(
        &mut self,
        label: impl AsRef<str>,
        values: impl IntoIterator<Item = T>,
    ) {
        self.table(label.as_ref(), ".byte", 1, "$FF", values, true);
    }

    /// The same with `.word`, and one `0` when there is nothing.
    pub fn words<T: Display>(
        &mut self,
        label: impl AsRef<str>,
        values: impl IntoIterator<Item = T>,
    ) {
        self.table(label.as_ref(), ".word", 2, "0", values, true);
    }

    /// [`bytes`](Self::bytes) without its `.block`, for what goes to
    /// `TABLES`: see [`unplaced`].
    pub fn bytes_unplaced<T: Display>(
        &mut self,
        label: impl AsRef<str>,
        values: impl IntoIterator<Item = T>,
    ) {
        self.table(label.as_ref(), ".byte", 1, "$FF", values, false);
    }

    /// [`words`](Self::words) without its `.block`.
    pub fn words_unplaced<T: Display>(
        &mut self,
        label: impl AsRef<str>,
        values: impl IntoIterator<Item = T>,
    ) {
        self.table(label.as_ref(), ".word", 2, "0", values, false);
    }

    /// The two lines of a 24-bit pointer to `target`, for a table of
    /// pointers whose entries the caller writes one by one.
    pub fn far(&mut self, target: &str) {
        let _ = writeln!(
            self.text,
            "    .word .loword({target})\n    .byte ^{target}"
        );
    }

    fn table<T: Display>(
        &mut self,
        label: &str,
        directive: &str,
        width: usize,
        empty: &str,
        values: impl IntoIterator<Item = T>,
        declare: bool,
    ) {
        let values: Vec<String> = values.into_iter().map(|v| v.to_string()).collect();
        if declare {
            let _ = writeln!(self.text, ".block {}", width * values.len().max(1));
        }
        let joined = if values.is_empty() {
            empty.to_string()
        } else {
            values.join(", ")
        };
        let _ = writeln!(self.text, "{label}:\n    {directive} {joined}");
    }
}

/// A data block with its placement declaration, sixteen bytes a line.
///
/// Each block is declared before emitting it: almost all are uploaded by
/// DMA, and a DMA that crosses a bank reads garbage from the middle onward.
/// The same holds for a table walked with `[ptr], y` or with
/// `lda f:table, x`: it has to stay whole on one side, and its pointers
/// being symbolic is not enough. Split, the console reads the second half
/// from `$0000` of the next bank, which is not where the packing put it
/// unless the two banks continue each other —and in LoROM, where this
/// first bit, was the WRAM mirror—. It is
/// an error that appears or disappears when a byte is added anywhere else
/// in the cartridge.
pub fn block(label: &str, data: &[u8]) -> String {
    placed(label, data, Some(format!(".block {}", data.len())))
}

/// [`block`], and with `msu` marked as a piece that may travel in the
/// `.msu` of a cartridge that needs the MSU-1: see `pack_with_msu` in
/// `rm2k-snes-cartridge`. **Only for what the ROM reads through something
/// that knows how to read the `.msu`** —an LZ2 stream, which only
/// `lz2_decompress` reads; or a block that is only uploaded by a DMA that
/// goes through `msu_dma0`—, and at a moment when a seek, which costs
/// Mednafen one or two frames, can wait: when a map or a battle loads, not
/// on every frame.
pub fn msu_block(label: &str, data: &[u8], msu: bool) -> String {
    let text = block(label, data);
    if msu {
        format!(".msu\n{text}")
    } else {
        text
    }
}

/// [`block`] for a piece that travels **only** in the `.msu`, in any
/// cartridge: the packing sends it there always, and its label becomes bank
/// `MSU_SPILL_BANK` and its unit —see `pack_with_msu` in
/// `rm2k-snes-cartridge`—. Only for what the ROM reads after it checked
/// that the MSU-1 and this build's `.msu` are there, and goes without
/// otherwise: the debug screen's.
pub fn msu_only_block(label: &str, data: &[u8]) -> String {
    format!(".msu_only\n{}", block(label, data))
}

/// [`block`] aligned to `align` bytes instead of declared whole.
pub fn aligned(label: &str, data: &[u8], align: usize) -> String {
    placed(label, data, Some(format!(".align {align}")))
}

/// [`block`] without a declaration, for what goes to `TABLES`: that area
/// lives inside bank 0, so nothing that falls there can cross, and the
/// declaration would be a computation that always comes out zero.
pub fn unplaced(label: &str, data: &[u8]) -> String {
    placed(label, data, None)
}

fn placed(label: &str, data: &[u8], declaration: Option<String>) -> String {
    let mut out = String::new();
    if let Some(declaration) = declaration {
        out.push_str(&declaration);
        out.push('\n');
    }
    out.push_str(label);
    out.push(':');
    for line in data.chunks(16) {
        out.push_str("\n    .byte ");
        for (k, b) in line.iter().enumerate() {
            if k > 0 {
                out.push(',');
            }
            let _ = write!(out, "${b:02X}");
        }
    }
    out
}

/// The three bytes of a symbolic pointer, for `.byte`.
pub fn pointer(dest: &str) -> String {
    format!("<({dest}), >({dest}), ^({dest})")
}

/// The bytes of a table this crate wrote as `.byte` and `.word` lines, when
/// every operand is a number: decimal, `$hex`, or `<(n)`, `>(n)` and `^(n)`
/// of one. Labels, `.block` lines and comments are skipped. It is for a
/// table that is written once and goes either to the cartridge as text or,
/// with its pointers already resolved, compressed into WRAM —the page
/// table: see `page_bytes` in record.rs—, so both come out of the same
/// lines. The error is the first operand it cannot read: a symbol, which
/// only the linker can resolve, or a number out of range.
pub fn numeric_bytes(text: &str) -> std::result::Result<Vec<u8>, String> {
    fn number(s: &str) -> Option<i64> {
        match s.strip_prefix('$') {
            Some(hex) => i64::from_str_radix(hex, 16).ok(),
            None => s.parse().ok(),
        }
    }
    let mut out = Vec::new();
    for line in text.lines() {
        let code = line.split(';').next().unwrap_or("").trim();
        let (width, operands) = if let Some(rest) = code.strip_prefix(".byte") {
            (1, rest)
        } else if let Some(rest) = code.strip_prefix(".word") {
            (2, rest)
        } else {
            continue;
        };
        for operand in operands.split(',') {
            let operand = operand.trim();
            let inner = |prefix: &str| {
                operand
                    .strip_prefix(prefix)
                    .and_then(|r| r.strip_prefix('('))
                    .and_then(|r| r.strip_suffix(')'))
                    .and_then(number)
            };
            let value = if let Some(n) = inner("<") {
                n & 0xFF
            } else if let Some(n) = inner(">") {
                (n >> 8) & 0xFF
            } else if let Some(n) = inner("^") {
                (n >> 16) & 0xFF
            } else {
                number(operand).ok_or_else(|| operand.to_string())?
            };
            let top = if width == 1 { 0xFF } else { 0xFFFF };
            if !(0..=top).contains(&value) {
                return Err(operand.to_string());
            }
            out.extend_from_slice(&(value as u16).to_le_bytes()[..width]);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numeric_lines_assemble_and_a_symbol_is_refused() {
        let text = ".block 7\nt:\n    .word 300 ; a word\n    .byte $7F, 2\n    .byte \
                    <($7F8123), >($7F8123), ^($7F8123)";
        assert_eq!(
            numeric_bytes(text),
            Ok(vec![0x2C, 0x01, 0x7F, 2, 0x23, 0x81, 0x7F])
        );
        assert_eq!(
            numeric_bytes("    .byte <(code + 3)"),
            Err("<(code + 3)".to_string())
        );
        assert_eq!(numeric_bytes("    .byte 256"), Err("256".to_string()));
    }

    #[test]
    fn a_block_is_declared_and_cut_every_sixteen_bytes() {
        let data: Vec<u8> = (0..18).collect();
        assert_eq!(
            block("x", &data),
            ".block 18\nx:\n    .byte $00,$01,$02,$03,$04,$05,$06,$07,$08,$09,$0A,$0B,$0C,\
             $0D,$0E,$0F\n    .byte $10,$11"
        );
        assert_eq!(unplaced("y", &[0xAB]), "y:\n    .byte $AB");
        assert_eq!(aligned("z", &[], 256), ".align 256\nz:");
    }

    /// An empty table still has something under its label: `$FF` for
    /// bytes and `0` for words, which are in the ROM.
    #[test]
    fn a_table_is_declared_and_an_empty_one_has_a_filler() {
        let mut inc = Inc::new(String::new());
        inc.bytes("b", [1, 2]);
        inc.bytes("e", Vec::<i64>::new());
        inc.words("w", ["$0001"]);
        inc.words("z", Vec::<i64>::new());
        inc.words_unplaced("u", [7]);
        inc.far("t");
        assert_eq!(
            inc.into_text(),
            ".block 2\nb:\n    .byte 1, 2\n.block 1\ne:\n    .byte $FF\n\
             .block 2\nw:\n    .word $0001\n.block 2\nz:\n    .word 0\n\
             u:\n    .word 7\n    .word .loword(t)\n    .byte ^t\n"
        );
    }

    #[test]
    fn a_pointer_takes_its_three_bytes_from_the_label() {
        assert_eq!(pointer("pose_3"), "<(pose_3), >(pose_3), ^(pose_3)");
    }
}
