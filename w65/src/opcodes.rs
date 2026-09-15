//! The instruction set, as a table of addressing mode to opcode byte.
//!
//! The modes are:
//!
//! ```text
//!   imp   implied, no operand             rts
//!   acc   on the accumulator              inc a
//!   imm   immediate, 1 or 2 bytes         lda #$8F
//!         depending on the current width
//!         of A or of X/Y
//!   imm8  immediate, always 1 byte        sep #$20
//!   dp    direct page, 1 byte             lda $12
//!   abs   absolute, 2 bytes               lda $2140
//!   long  absolute long, 3 bytes          lda f:$7E30A0
//!   dpil  indirect long through direct    lda [$12]
//!         page, 1 byte
//!   dpily indirect long indexed by Y      lda [$12],y
//!   dpi   indirect through direct page    lda ($12)
//!   dpiy  indirect indexed by Y           lda ($12),y
//!   rel   relative to the PC, 1 signed    bne label
//!         byte
//! ```
//!
//! The index is glued to the mode rather than kept apart because `[$12]` and
//! `[$12],y` are different opcodes. The indexed long is the one that walks a
//! table living outside the data bank.
//!
//! This is not a complete 65816. It covers what the sources it assembles
//! actually use and fails loudly at anything else, which for a tool like this
//! is the right behaviour: an error is better than a subtly different image.

pub type Modes = &'static [(&'static str, u8)];

static OPCODES: &[(&str, Modes)] = &[
    ("lda", &[("long", 0xAF), ("longx", 0xBF), ("dpx", 0xB5), ("absx", 0xBD), ("absy", 0xB9), ("imm", 0xA9), ("dp", 0xA5), ("abs", 0xAD), ("dpil", 0xA7), ("dpily", 0xB7), ("dpi", 0xB2), ("dpiy", 0xB1)]),
    ("sta", &[("long", 0x8F), ("longx", 0x9F), ("dpx", 0x95), ("absx", 0x9D), ("absy", 0x99), ("dp", 0x85), ("abs", 0x8D), ("dpil", 0x87), ("dpily", 0x97), ("dpi", 0x92), ("dpiy", 0x91)]),
    ("ldx", &[("dpy", 0xB6), ("absy", 0xBE), ("imm", 0xA2), ("dp", 0xA6), ("abs", 0xAE)]),
    ("stx", &[("dpy", 0x96), ("dp", 0x86), ("abs", 0x8E)]),
    ("ldy", &[("dpx", 0xB4), ("absx", 0xBC), ("imm", 0xA0), ("dp", 0xA4), ("abs", 0xAC)]),
    ("sty", &[("dpx", 0x94), ("dp", 0x84), ("abs", 0x8C)]),
    ("cmp", &[("long", 0xCF), ("longx", 0xDF), ("dpx", 0xD5), ("absx", 0xDD), ("absy", 0xD9), ("imm", 0xC9), ("dp", 0xC5), ("abs", 0xCD)]),
    ("cpx", &[("imm", 0xE0), ("dp", 0xE4), ("abs", 0xEC)]),
    ("cpy", &[("imm", 0xC0), ("dp", 0xC4), ("abs", 0xCC)]),
    ("inc", &[("dpx", 0xF6), ("absx", 0xFE), ("acc", 0x1A), ("dp", 0xE6), ("abs", 0xEE)]),
    ("dec", &[("dpx", 0xD6), ("absx", 0xDE), ("acc", 0x3A), ("dp", 0xC6), ("abs", 0xCE)]),
    ("stz", &[("dpx", 0x74), ("absx", 0x9E), ("dp", 0x64), ("abs", 0x9C)]),
    ("and", &[("dpil", 0x27), ("dpily", 0x37), ("long", 0x2F), ("longx", 0x3F), ("dpx", 0x35), ("absx", 0x3D), ("absy", 0x39), ("imm", 0x29), ("dp", 0x25), ("abs", 0x2D)]),
    ("ora", &[("dpil", 0x07), ("dpily", 0x17), ("long", 0x0F), ("longx", 0x1F), ("dpx", 0x15), ("absx", 0x1D), ("absy", 0x19), ("imm", 0x09), ("dp", 0x05), ("abs", 0x0D)]),
    ("eor", &[("long", 0x4F), ("longx", 0x5F), ("dpx", 0x55), ("absx", 0x5D), ("absy", 0x59), ("imm", 0x49), ("dp", 0x45), ("abs", 0x4D)]),
    ("adc", &[("long", 0x6F), ("longx", 0x7F), ("dpx", 0x75), ("absx", 0x7D), ("absy", 0x79), ("imm", 0x69), ("dp", 0x65), ("abs", 0x6D)]),
    ("sbc", &[("long", 0xEF), ("longx", 0xFF), ("dpx", 0xF5), ("absx", 0xFD), ("absy", 0xF9), ("imm", 0xE9), ("dp", 0xE5), ("abs", 0xED)]),
    ("bit", &[("imm", 0x89), ("dp", 0x24), ("abs", 0x2C)]),
    ("asl", &[("dpx", 0x16), ("absx", 0x1E), ("acc", 0x0A), ("dp", 0x06), ("abs", 0x0E)]),
    ("lsr", &[("dpx", 0x56), ("absx", 0x5E), ("acc", 0x4A), ("dp", 0x46), ("abs", 0x4E)]),
    ("rol", &[("dpx", 0x36), ("absx", 0x3E), ("acc", 0x2A), ("dp", 0x26), ("abs", 0x2E)]),
    ("ror", &[("dpx", 0x76), ("absx", 0x7E), ("acc", 0x6A), ("dp", 0x66), ("abs", 0x6E)]),
    ("jsr", &[("abs", 0x20)]),
    ("jmp", &[("abs", 0x4C)]),
    ("jml", &[("long", 0x5C)]),
    // `jsl` is the `jsr` that changes bank: it pushes the program bank as well
    // as the cursor, and returns with `rtl`. It is what a call into code that
    // does not fit in bank 0 needs.
    ("jsl", &[("long", 0x22)]),
    // `rep` and `sep` always take a one byte immediate, whatever width is in
    // force: their operand is the bits of the status register, not data.
    ("rep", &[("imm8", 0xC2)]),
    ("sep", &[("imm8", 0xE2)]),
];

static IMPLIED: &[(&str, u8)] = &[
    ("sei", 0x78), ("cli", 0x58), ("clc", 0x18), ("sec", 0x38), ("cld", 0xD8),
    ("xce", 0xFB), ("xba", 0xEB), ("nop", 0xEA),
    ("txs", 0x9A), ("tsx", 0xBA), ("txa", 0x8A), ("tax", 0xAA),
    ("tay", 0xA8), ("tya", 0x98), ("txy", 0x9B), ("tyx", 0xBB),
    ("inx", 0xE8), ("iny", 0xC8), ("dex", 0xCA), ("dey", 0x88),
    ("pha", 0x48), ("pla", 0x68), ("php", 0x08), ("plp", 0x28),
    ("phx", 0xDA), ("plx", 0xFA), ("phy", 0x5A), ("ply", 0x7A),
    ("phb", 0x8B), ("plb", 0xAB), ("phd", 0x0B), ("pld", 0x2B), ("phk", 0x4B),
    ("rts", 0x60), ("rtl", 0x6B), ("rti", 0x40),
];

static BRANCHES: &[(&str, u8)] = &[
    ("bpl", 0x10), ("bmi", 0x30), ("bvc", 0x50), ("bvs", 0x70),
    ("bcc", 0x90), ("bcs", 0xB0), ("bne", 0xD0), ("beq", 0xF0), ("bra", 0x80),
];

/// Which ones look at the width of X/Y, rather than of A, to decide whether
/// an immediate takes one byte or two.
static INDEX_WIDTH: &[&str] = &["ldx", "ldy", "cpx", "cpy"];

/// The whole instruction table, as lines of `kind mnemonic …`, for a caller
/// that wants to generate a source exercising every entry. Three kinds:
///
/// ```text
///   implied rts 60
///   branch  bne D0
///   modal   lda imm A9 dp A5 abs AD …
/// ```
///
/// It exists because a table nobody exercises is a trap set for whoever first
/// uses an entry, and the only honest way to exercise it is to read it from
/// the assembler itself rather than from a second copy that drifts.
pub fn table() -> String {
    let mut out = String::new();
    for (name, code) in IMPLIED {
        out.push_str(&format!("implied {name} {code:02X}\n"));
    }
    for (name, code) in BRANCHES {
        out.push_str(&format!("branch {name} {code:02X}\n"));
    }
    for (name, modes) in OPCODES {
        out.push_str(&format!("modal {name}"));
        for (mode, code) in modes.iter() {
            out.push_str(&format!(" {mode} {code:02X}"));
        }
        out.push('\n');
    }
    out
}

pub fn modes_of(mnemonic: &str) -> Option<Modes> {
    OPCODES.iter().find(|(m, _)| *m == mnemonic).map(|(_, modes)| *modes)
}

pub fn code_of(modes: Modes, mode: &str) -> Option<u8> {
    modes.iter().find(|(m, _)| *m == mode).map(|(_, code)| *code)
}

pub fn has_mode(modes: Modes, mode: &str) -> bool {
    code_of(modes, mode).is_some()
}

pub fn implied(mnemonic: &str) -> Option<u8> {
    IMPLIED.iter().find(|(m, _)| *m == mnemonic).map(|(_, code)| *code)
}

pub fn branch(mnemonic: &str) -> Option<u8> {
    BRANCHES.iter().find(|(m, _)| *m == mnemonic).map(|(_, code)| *code)
}

pub fn uses_index_width(mnemonic: &str) -> bool {
    INDEX_WIDTH.contains(&mnemonic)
}

/// How many bytes the operand of a mode takes. `imm` is missing on purpose:
/// it depends on the width in force, which only the assembler knows.
pub fn operand_width(mode: &str) -> Option<u8> {
    Some(match mode {
        "imp" | "acc" => 0,
        "dp" | "dpx" | "dpy" | "dpil" | "dpily" | "dpi" | "dpiy" | "imm8" => 1,
        "abs" | "absx" | "absy" => 2,
        "long" | "longx" => 3,
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_mnemonic_that_does_not_exist_has_no_modes() {
        assert!(modes_of("frobnicate").is_none());
        assert!(modes_of("lda").is_some());
    }

    /// Nothing may be in two of the three tables: the assembler checks them in
    /// order, so an overlap would make one of them unreachable.
    #[test]
    fn no_mnemonic_appears_in_two_tables() {
        for (name, _) in IMPLIED {
            assert!(modes_of(name).is_none(), "{name} is both implied and modal");
            assert!(branch(name).is_none(), "{name} is both implied and a branch");
        }
        for (name, _) in BRANCHES {
            assert!(modes_of(name).is_none(), "{name} is both a branch and modal");
        }
    }

    /// The printed table is what `--list-opcodes` hands to whoever generates a
    /// source exercising every entry, so a mnemonic missing from it is an
    /// entry that silently stops being tested.
    #[test]
    fn the_printed_table_lists_every_mnemonic_once() {
        let text = table();
        let names: Vec<&str> = text
            .lines()
            .map(|line| line.split_whitespace().nth(1).expect("a kind and a name"))
            .collect();
        assert_eq!(names.len(), IMPLIED.len() + BRANCHES.len() + OPCODES.len());
        for name in &names {
            assert_eq!(names.iter().filter(|other| *other == name).count(), 1, "{name} twice");
        }
        for (name, modes) in OPCODES {
            let line = text
                .lines()
                .find(|line| line.starts_with(&format!("modal {name} ")))
                .unwrap_or_else(|| panic!("{name} is not in the printed table"));
            assert_eq!(line.split_whitespace().count(), 2 + modes.len() * 2);
        }
    }

    #[test]
    fn no_mnemonic_declares_the_same_mode_twice() {
        for (name, modes) in OPCODES {
            for (i, (mode, _)) in modes.iter().enumerate() {
                assert!(
                    !modes[..i].iter().any(|(other, _)| other == mode),
                    "{name} declares {mode} twice"
                );
            }
        }
    }

    /// Every mode named in the tables has to have a width, or the assembler
    /// would refuse an instruction it can encode.
    #[test]
    fn every_declared_mode_has_a_known_operand_width() {
        for (name, modes) in OPCODES {
            for (mode, _) in modes.iter() {
                assert!(
                    *mode == "imm" || operand_width(mode).is_some(),
                    "{name} uses {mode}, which has no width"
                );
            }
        }
    }
}
