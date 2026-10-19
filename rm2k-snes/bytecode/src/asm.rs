//! The 65816 side: a bytecode as `ca65` equates.
//!
//! `rm2k-snes-assemble` writes these next to a cartridge's other generated
//! files every time it builds one —[`FILES`] says which and under what
//! name—, so the runtime has no number written down and no generated file
//! that can go stale. Nothing here knows what an opcode means: it is the
//! shape of the text, and the sizes are not in it, because the 65816 side
//! walks an instruction with its own code.

use crate::{events, music, Bytecode};

/// The files the runtime includes, the bytecode each one carries and
/// whether it also carries the dispatch table.
///
/// Only the events one has a table: `run_code` dispatches on it. The music
/// stream's reader goes by families of eight opcodes instead, and would not
/// use one.
pub const FILES: [(&str, &Bytecode, bool); 2] = [
    ("event_opcodes.inc", &events::BYTECODE, true),
    ("music_opcodes.inc", &music::BYTECODE, false),
];

/// The five header lines every file carries.
fn header(name: &str) -> Vec<String> {
    vec![
        format!("; The {name} opcodes: their numbers and their layout."),
        ";".into(),
        "; Written by rm2k-snes-assemble, at every build, from the declaration".into(),
        "; in the rm2k-snes-bytecode crate. **Do not edit:** change the".into(),
        "; declaration, and the next build writes it again.".into(),
    ]
}

/// The equates, and with `jump_table` a macro that lays down one `.addr` per
/// opcode in the order of their numbers, for an indirect `jmp (table, x)`.
///
/// The handler of `OP_SWITCH` is `op_switch`: the opcode's name in lower
/// case. That is a rule and not a field on purpose. A field would be a
/// second name to keep in step with the first, and the declaration would
/// start saying something about the reader's code; the rule says only how
/// to spell one name the declaration already has. A handler that does not
/// exist does not assemble, which is the check.
///
/// A macro and not the table itself because the equates are included where
/// the reader wants its constants, and the table has to land where the
/// reader puts its code: which segment, next to which dispatch, is the
/// reader's business.
///
/// The table needs the numbers to run from 0 with no gaps, and stops here
/// if they do not —see [`Bytecode::check_dispatch`]—. A declaration that
/// wants a table checks that in a `const`, so it does not get this far.
pub fn asm(bytecode: &Bytecode, jump_table: bool) -> String {
    let mut out = header(bytecode.name);
    out.push(String::new());
    for o in bytecode.opcodes {
        out.push(format!("{:<16} = ${:02X}", o.name, o.code));
    }
    out.push(String::new());
    if jump_table {
        bytecode.check_dispatch();
        let mut ordered: Vec<_> = bytecode.opcodes.iter().collect();
        ordered.sort_by_key(|o| o.code);
        let prefix = bytecode.name.to_uppercase();
        out.push("; How many opcodes there are: every number below this one is declared,".into());
        out.push("; so an opcode at or above it is not one, and must not index the table.".into());
        out.push(format!("{prefix}_OPCODE_COUNT = ${:02X}", ordered.len()));
        out.push(String::new());
        out.push(
            "; One `.addr` per opcode, in the order of their numbers, to expand where a".into(),
        );
        out.push(
            "; `jmp (table, x)` reads it with X = opcode * 2. Each opcode's handler is".into(),
        );
        out.push("; named after it, in lower case, and a missing one does not assemble.".into());
        out.push(format!(".macro {prefix}_HANDLERS"));
        for o in &ordered {
            out.push(format!(
                "    .addr {:<20} ; ${:02X}",
                o.name.to_lowercase(),
                o.code
            ));
        }
        out.push(".endmacro".into());
        out.push(String::new());
    }
    out.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Arg, Opcode, Repeated, Type};

    const fn arg(name: &'static str, kind: Type, count: bool) -> Arg {
        Arg {
            name,
            kind,
            signed: false,
            count,
        }
    }

    const ITEMS: &[Arg] = &[arg("y", Type::Word, false)];

    const SAMPLE: &[Opcode] = &[
        Opcode {
            name: "OP_NONE",
            code: 0x00,
            args: &[],
            repeated: None,
        },
        Opcode {
            name: "OP_ONE",
            code: 0x01,
            args: &[arg("x", Type::Word, false)],
            repeated: None,
        },
        Opcode {
            name: "OP_MANY",
            code: 0x02,
            args: &[arg("n", Type::Byte, true)],
            repeated: Some(Repeated {
                name: "items",
                args: ITEMS,
            }),
        },
    ];

    const REVERSED: &[Opcode] = &[SAMPLE[2], SAMPLE[1], SAMPLE[0]];
    const GAPPED: &[Opcode] = &[SAMPLE[0], SAMPLE[2]];

    fn sample() -> Bytecode {
        Bytecode {
            name: "test",
            opcodes: SAMPLE,
        }
    }

    /// An invisible trailing space would show up as a diff of the `.dbg` on
    /// every build that writes it with a different version.
    #[test]
    fn no_line_ends_in_whitespace() {
        for (_, bytecode, table) in FILES {
            let text = asm(bytecode, table);
            for (n, line) in text.lines().enumerate() {
                assert_eq!(line, line.trim_end(), "line {} of {}", n + 1, bytecode.name);
            }
            assert!(text.ends_with('\n'), "no trailing newline");
        }
    }

    #[test]
    fn the_equates_are_the_names_and_the_numbers_and_nothing_else() {
        let out = asm(&sample(), false);
        assert!(out.starts_with("; The test opcodes"), "{out}");
        assert!(out.contains("\nOP_MANY          = $02\n"), "{out}");
        assert!(!out.contains(".macro"), "{out}");
        assert!(!out.contains("COUNT"), "{out}");
    }

    /// Entry k of the table is the handler of opcode k, whatever order the
    /// declaration lists them in: that is the whole contract of the table.
    #[test]
    fn the_jump_table_follows_the_numbers_and_lowercases_the_names() {
        let out = asm(
            &Bytecode {
                name: "test",
                opcodes: REVERSED,
            },
            true,
        );
        let handlers: Vec<&str> = out
            .lines()
            .filter_map(|l| l.trim_start().strip_prefix(".addr "))
            .map(|l| l.split_whitespace().next().unwrap())
            .collect();
        assert_eq!(handlers, ["op_none", "op_one", "op_many"], "{out}");
        assert!(out.contains("TEST_OPCODE_COUNT = $03"), "{out}");
        assert!(out.contains(".macro TEST_HANDLERS"), "{out}");
        assert!(out.trim_end().ends_with(".endmacro"), "{out}");
    }

    #[test]
    #[should_panic(expected = "nothing takes 0x01")]
    fn a_jump_table_with_a_gap_is_refused() {
        asm(
            &Bytecode {
                name: "test",
                opcodes: GAPPED,
            },
            true,
        );
    }

    /// Without the table, the same declaration is fine: a stream with an end
    /// marker at 0xFF is a normal declaration and a pointless table.
    #[test]
    fn without_the_table_a_gap_is_fine() {
        asm(
            &Bytecode {
                name: "test",
                opcodes: GAPPED,
            },
            false,
        );
    }
}
