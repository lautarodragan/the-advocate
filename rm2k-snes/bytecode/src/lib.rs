//! The two bytecodes an rm2k-snes cartridge reads, declared once.
//!
//! A bytecode has two sides that have to agree byte for byte: whatever emits
//! the bytes and whatever reads them. When each side writes the numbers down
//! for itself, they drift, and a bytecode whose two sides disagree **does not
//! fail** —it reads from the middle of the next instruction and carries on—.
//! So each opcode is declared here, once, with `bytecode!`:
//!
//! * [`events`]: the event bytecode, which `rm2k-snes-events` emits and the
//!   runtime's `run_code` interprets;
//! * [`music`]: the music stream, which `rm2k-snes-audio` writes and the
//!   runtime's `irq_music` reads.
//!
//! And [`level`], how loud, how fast and how gradually a song starts, which
//! `OP_BGM`, `OP_SYSTEM_BGM` and a map's own song carry in the same units.
//!
//! The Rust side takes the constants with a `use`, and the 65816 side gets
//! them from [`asm`]: `rm2k-snes-assemble` writes them next to the
//! cartridge's other generated files every time it builds one, so there is
//! no generated file to keep up to date. What each opcode *does* is
//! hand-written on both sides and stays hand-written.
//!
//! Everything that can be wrong about a declaration on its own —two opcodes
//! on one number, a repeated group nobody counts, a gap in the event
//! dispatch, a name both bytecodes use— **stops the compilation** of this
//! crate, with the opcode in the message: see [`Bytecode::check`].
//!
//! So the tests are those messages, the shape of the equates
//! `rm2k-snes-assemble` writes, and that the runtime uses only declared
//! opcodes and writes none by hand. They need no game.

pub mod asm;
pub mod level;
mod message;

/// How an argument is stored. Words and longs are little endian.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Type {
    Byte,
    Word,
    Long,
}

impl Type {
    pub const fn size(self) -> usize {
        match self {
            Type::Byte => 1,
            Type::Word => 2,
            Type::Long => 3,
        }
    }
}

/// One argument of an instruction, in the order it follows the opcode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Arg {
    pub name: &'static str,
    pub kind: Type,
    /// How to read it back; nothing writes it differently.
    pub signed: bool,
    /// It says how many entries of the opcode's [`Repeated`] group follow.
    pub count: bool,
}

/// The entries an opcode ends in, as many as its counting argument says.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Repeated {
    pub name: &'static str,
    pub args: &'static [Arg],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Opcode {
    pub name: &'static str,
    pub code: u8,
    pub args: &'static [Arg],
    pub repeated: Option<Repeated>,
}

const fn size_of(args: &[Arg]) -> usize {
    let mut size = 0;
    let mut i = 0;
    while i < args.len() {
        size += args[i].kind.size();
        i += 1;
    }
    size
}

impl Opcode {
    /// The opcode byte plus its arguments: the whole instruction, unless it
    /// ends in a repeated group.
    pub const fn fixed_size(&self) -> usize {
        1 + size_of(self.args)
    }

    /// How big one entry of the repeated group is; 0 without one.
    pub const fn entry_size(&self) -> usize {
        match self.repeated {
            Some(r) => size_of(r.args),
            None => 0,
        }
    }

    /// Where the argument holding how many entries follow starts, counting
    /// the opcode byte.
    pub const fn count_offset(&self) -> usize {
        let mut at = 1;
        let mut i = 0;
        while i < self.args.len() {
            if self.args[i].count {
                return at;
            }
            at += self.args[i].kind.size();
            i += 1;
        }
        at
    }
}

/// A bytecode: its name and its opcodes, in the order they are declared.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Bytecode {
    pub name: &'static str,
    pub opcodes: &'static [Opcode],
}

impl Bytecode {
    /// The opcode numbered `code`, if it is declared.
    pub const fn opcode(&self, code: u8) -> Option<&'static Opcode> {
        let opcodes = self.opcodes;
        let mut i = 0;
        while i < opcodes.len() {
            if opcodes[i].code == code {
                return Some(&opcodes[i]);
            }
            i += 1;
        }
        None
    }

    /// How many bytes an instruction of `code` takes, if it is declared and
    /// does not end in a repeated group.
    pub const fn fixed_size(&self, code: u8) -> Option<usize> {
        match self.opcode(code) {
            Some(o) if o.repeated.is_none() => Some(o.fixed_size()),
            _ => None,
        }
    }

    /// How many bytes the instruction starting at `code[at]` takes, the
    /// variable-size ones included: `None` if its opcode is not declared or
    /// its count is past the end of `code`.
    pub fn size_at(&self, code: &[u8], at: usize) -> Option<usize> {
        let o = self.opcode(*code.get(at)?)?;
        if o.repeated.is_none() {
            return Some(o.fixed_size());
        }
        let count = *code.get(at + o.count_offset())? as usize;
        Some(o.fixed_size() + count * o.entry_size())
    }

    /// Stops with what is wrong if the declaration is not one: no opcodes,
    /// two on the same number, or a repeated group that is not counted by
    /// exactly one of the opcode's own arguments. Two opcodes with the same
    /// name do not get this far: they are two `const`s with the same name.
    ///
    /// `bytecode!` calls it in a `const`, so a broken declaration does not
    /// compile.
    pub const fn check(&self) {
        let opcodes = self.opcodes;
        if opcodes.is_empty() {
            message::Message::new()
                .push("the ")
                .push(self.name)
                .push(" bytecode does not declare a single opcode")
                .fail();
        }
        let mut i = 0;
        while i < opcodes.len() {
            let o = &opcodes[i];
            let mut j = 0;
            while j < i {
                if opcodes[j].code == o.code {
                    message::Message::new()
                        .push(o.name)
                        .push(" and ")
                        .push(opcodes[j].name)
                        .push(" both take ")
                        .hex(o.code)
                        .fail();
                }
                j += 1;
            }
            check_count(o);
            i += 1;
        }
    }

    /// Stops unless the opcodes are numbered from 0 with no gaps: what a jump
    /// table indexed by the opcode needs. A gap would be an entry that jumps
    /// anywhere, so it is refused and named instead of filled with a guess.
    pub const fn check_dispatch(&self) {
        self.check();
        // With no number repeated, no gaps is every number below the count.
        let count = self.opcodes.len();
        let mut largest = 0usize;
        let mut i = 0;
        while i < count {
            if self.opcodes[i].code as usize > largest {
                largest = self.opcodes[i].code as usize;
            }
            i += 1;
        }
        if largest < count {
            return;
        }
        let mut m = message::Message::new()
            .push("a jump table needs the ")
            .push(self.name)
            .push(" opcodes numbered from 0 with no gaps; nothing takes ");
        // A long list is noise: the first few say what is wrong.
        let mut missing = 0;
        let mut code = 0;
        while code < largest {
            if self.opcode(code as u8).is_none() {
                if missing < 8 {
                    if missing > 0 {
                        m = m.push(", ");
                    }
                    m = m.hex(code as u8);
                }
                missing += 1;
            }
            code += 1;
        }
        if missing > 8 {
            m = m.push(" and ").number(missing - 8).push(" more");
        }
        m.fail();
    }
}

/// An opcode with a repeated group has exactly one argument counting it, and
/// one without has none.
const fn check_count(o: &Opcode) {
    let mut counts = 0;
    let mut i = 0;
    while i < o.args.len() {
        if o.args[i].count {
            counts += 1;
        }
        i += 1;
    }
    let message = message::Message::new().push(o.name);
    match o.repeated {
        Some(r) => {
            let mut i = 0;
            while i < r.args.len() {
                if r.args[i].count {
                    message
                        .push(" counts its entries from inside the entries of ")
                        .push(r.name)
                        .fail();
                }
                i += 1;
            }
            if counts == 0 {
                message
                    .push(" declares `repeated ")
                    .push(r.name)
                    .push("` and no argument counts it")
                    .fail();
            }
            if counts > 1 {
                message
                    .push(" counts ")
                    .push(r.name)
                    .push(" more than once")
                    .fail();
            }
        }
        None => {
            if counts > 0 {
                message
                    .push(" has a `count` argument and nothing `repeated` to count")
                    .fail();
            }
        }
    }
}

/// Stops if a name is in both bytecodes. The numbers may repeat —`OP_NOTE_V0`
/// and `OP_DONE` are both $00, in different streams—, but in the assembler
/// both are one symbol space: that is why the events' end is `OP_DONE` and not
/// `OP_END`, which was the music's.
pub const fn check_disjoint(a: &Bytecode, b: &Bytecode) {
    let mut i = 0;
    while i < a.opcodes.len() {
        let mut j = 0;
        while j < b.opcodes.len() {
            if message::same(a.opcodes[i].name, b.opcodes[j].name) {
                message::Message::new()
                    .push(a.opcodes[i].name)
                    .push(" is in the ")
                    .push(a.name)
                    .push(" bytecode and in the ")
                    .push(b.name)
                    .push(" one: in the ROM they are a single symbol")
                    .fail();
            }
            j += 1;
        }
        i += 1;
    }
}

/// Declares a bytecode, in the module it is invoked in: one `pub const` per
/// opcode with its number, and `BYTECODE`, the whole table, which is checked
/// while it compiles.
///
/// ```text
/// bytecode! {
///     "event";
///     /// What the opcode is, as a doc comment: it goes on the constant.
///     OP_SWITCH = 0x01 (id: word, value: byte);
///     OP_CHOICE = 0x14 (length: count byte, on_cancel: byte)
///         repeated options (window: word, destination: word);
/// }
/// ```
///
/// An instruction is its opcode byte followed by its arguments, in order.
/// The types are `byte` (1), `word` (2) and `long` (3); `signed` in front
/// says how to read it back and changes nothing about how it is written. An
/// opcode that ends in a variable number of entries declares them with
/// `repeated`, and the argument that holds how many follow is a `count`.
///
/// Those are the only two shapes there are. If a new opcode does not fit,
/// the answer is to change the opcode, not to grow this grammar: **the
/// moment a declaration can describe behaviour, it stopped being a
/// declaration and became a second compiler**. A type it does not know is
/// a token no rule expects, and does not compile.
macro_rules! bytecode {
    (
        $name:literal;
        $(
            $(#[$meta:meta])*
            $op:ident = $code:literal ( $($arg:ident : $($kind:ident)+),* $(,)? )
            $(repeated $group:ident ( $($entry:ident : $($entry_kind:ident)+),* $(,)? ))?
            ;
        )*
    ) => {
        $(
            $(#[$meta])*
            pub const $op: u8 = $code;
        )*

        /// Every opcode, in the order they are declared.
        pub const BYTECODE: $crate::Bytecode = $crate::Bytecode {
            name: $name,
            opcodes: &[$(
                $crate::Opcode {
                    name: stringify!($op),
                    code: $op,
                    args: &[$(bytecode!(@arg $arg $($kind)+)),*],
                    repeated: bytecode!(@repeated $($group ($($entry $($entry_kind)+),*))?),
                }
            ),*],
        };

        const _: () = BYTECODE.check();
    };

    (@repeated) => { None };
    (@repeated $group:ident ($($entry:ident $($kind:ident)+),*)) => {
        Some($crate::Repeated {
            name: stringify!($group),
            args: &[$(bytecode!(@arg $entry $($kind)+)),*],
        })
    };

    (@arg $name:ident $kind:ident) => { bytecode!(@arg $name false false $kind) };
    (@arg $name:ident signed $kind:ident) => { bytecode!(@arg $name true false $kind) };
    (@arg $name:ident count $kind:ident) => { bytecode!(@arg $name false true $kind) };
    (@arg $name:ident $signed:literal $count:literal $kind:ident) => {
        $crate::Arg {
            name: stringify!($name),
            kind: bytecode!(@type $kind),
            signed: $signed,
            count: $count,
        }
    };

    (@type byte) => { $crate::Type::Byte };
    (@type word) => { $crate::Type::Word };
    (@type long) => { $crate::Type::Long };
}

pub mod events;
pub mod music;

// Both land in the assembler's one symbol space.
const _: () = check_disjoint(&events::BYTECODE, &music::BYTECODE);

#[cfg(test)]
mod tests {
    use super::*;

    const fn arg(name: &'static str, kind: Type, count: bool) -> Arg {
        Arg {
            name,
            kind,
            signed: false,
            count,
        }
    }

    const fn op(name: &'static str, code: u8, args: &'static [Arg]) -> Opcode {
        Opcode {
            name,
            code,
            args,
            repeated: None,
        }
    }

    const ITEMS: Repeated = Repeated {
        name: "items",
        args: &[arg("x", Type::Word, false)],
    };

    /// A test's declaration lives as long as the test does; `Bytecode` wants
    /// it `'static`, as the macro's are.
    fn leak<T>(items: Vec<T>) -> &'static [T] {
        Vec::leak(items)
    }

    fn bytecode(name: &'static str, opcodes: Vec<Opcode>) -> Bytecode {
        Bytecode {
            name,
            opcodes: leak(opcodes),
        }
    }

    fn check(opcodes: Vec<Opcode>) {
        bytecode("test", opcodes).check();
    }

    #[test]
    fn the_declarations_are_checked_where_they_are_declared() {
        // They are, in a `const`; this is that the checks pass at all.
        events::BYTECODE.check_dispatch();
        music::BYTECODE.check();
        check_disjoint(&events::BYTECODE, &music::BYTECODE);
    }

    /// The bug the declaration exists for: two opcodes on the same number.
    /// It used to be found by a merge, days later.
    #[test]
    #[should_panic(expected = "OP_B and OP_A both take 0x01")]
    fn two_opcodes_cannot_share_a_number() {
        check(vec![op("OP_A", 0x01, &[]), op("OP_B", 0x01, &[])]);
    }

    #[test]
    #[should_panic(expected = "the test bytecode does not declare a single opcode")]
    fn a_bytecode_with_no_opcodes_is_refused() {
        check(vec![]);
    }

    #[test]
    #[should_panic(expected = "OP_A declares `repeated items` and no argument counts it")]
    fn a_repeated_group_needs_something_counting_it() {
        check(vec![Opcode {
            repeated: Some(ITEMS),
            ..op("OP_A", 0x01, leak(vec![arg("x", Type::Byte, false)]))
        }]);
    }

    #[test]
    #[should_panic(expected = "OP_A has a `count` argument and nothing `repeated` to count")]
    fn counting_a_group_that_is_not_declared_is_an_error() {
        check(vec![op(
            "OP_A",
            0x01,
            leak(vec![arg("n", Type::Byte, true)]),
        )]);
    }

    #[test]
    #[should_panic(expected = "OP_A counts items more than once")]
    fn a_group_is_counted_once() {
        check(vec![Opcode {
            repeated: Some(ITEMS),
            ..op(
                "OP_A",
                0x01,
                leak(vec![arg("n", Type::Byte, true), arg("m", Type::Byte, true)]),
            )
        }]);
    }

    #[test]
    #[should_panic(expected = "OP_A counts its entries from inside the entries of items")]
    fn the_count_is_not_inside_the_entries() {
        check(vec![Opcode {
            repeated: Some(Repeated {
                name: "items",
                args: leak(vec![arg("n", Type::Byte, true)]),
            }),
            ..op("OP_A", 0x01, leak(vec![arg("n", Type::Byte, true)]))
        }]);
    }

    #[test]
    #[should_panic(expected = "OP_X is in the a bytecode and in the b one")]
    fn the_two_bytecodes_share_no_name() {
        check_disjoint(
            &bytecode("a", vec![op("OP_X", 0x00, &[])]),
            &bytecode("b", vec![op("OP_Y", 0x00, &[]), op("OP_X", 0x01, &[])]),
        );
    }

    /// The numbers may repeat between bytecodes; only the names may not.
    #[test]
    fn the_two_bytecodes_may_share_a_number() {
        check_disjoint(
            &bytecode("a", vec![op("OP_X", 0x00, &[])]),
            &bytecode("b", vec![op("OP_Y", 0x00, &[])]),
        );
    }

    /// Declared out of order is fine: the dispatch follows the numbers.
    #[test]
    fn the_dispatch_needs_the_numbers_not_the_order() {
        bytecode("test", vec![op("OP_B", 0x01, &[]), op("OP_A", 0x00, &[])]).check_dispatch();
    }

    #[test]
    #[should_panic(
        expected = "a jump table needs the test opcodes numbered from 0 with no gaps; \
                               nothing takes 0x00, 0x02, 0x03"
    )]
    fn the_dispatch_names_every_gap() {
        bytecode("test", vec![op("OP_A", 0x01, &[]), op("OP_B", 0x04, &[])]).check_dispatch();
    }

    /// A stream with an end marker at 0xFF is a normal declaration; it just
    /// cannot be a jump table, and the message should not list 250 numbers.
    #[test]
    #[should_panic(expected = "0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08 and 246 more")]
    fn a_long_list_of_gaps_is_cut_short() {
        bytecode("test", vec![op("OP_A", 0x00, &[]), op("OP_END", 0xFF, &[])]).check_dispatch();
    }

    /// Where the count sits and how big an entry is are what a reader needs to
    /// walk past an instruction it does not care about.
    #[test]
    fn a_variable_sized_opcode_derives_where_its_count_is() {
        const ARGS: &[Arg] = &[
            arg("a", Type::Byte, false),
            arg("b", Type::Word, false),
            arg("n", Type::Byte, true),
        ];
        const OPS: &[Opcode] = &[Opcode {
            repeated: Some(ITEMS),
            ..op("OP_A", 0x01, ARGS)
        }];
        let b = Bytecode {
            name: "test",
            opcodes: OPS,
        };
        let o = b.opcode(0x01).unwrap();
        assert_eq!(o.fixed_size(), 5); // opcode + 1 + 2 + 1
        assert_eq!(o.count_offset(), 4); // after the opcode, the byte and the word
        assert_eq!(o.entry_size(), 2);
        assert_eq!(b.fixed_size(0x01), None, "it has no fixed size");
        assert_eq!(b.size_at(&[0x01, 0, 0, 0, 3], 0), Some(5 + 3 * 2));
        assert_eq!(
            b.size_at(&[0x01, 0, 0], 0),
            None,
            "the count is past the end"
        );
        assert_eq!(b.size_at(&[0x02], 0), None, "not declared");
    }

    /// What the macro builds from a declaration: the types, `signed` and
    /// `count` where they were written.
    #[test]
    fn the_macro_reads_the_declaration_as_written() {
        let pan = events::BYTECODE.opcode(events::OP_PAN).unwrap();
        assert_eq!(pan.name, "OP_PAN");
        let dx = pan.args.iter().find(|a| a.name == "dx").unwrap();
        assert_eq!((dx.kind, dx.signed, dx.count), (Type::Word, true, false));
        let choice = events::BYTECODE.opcode(events::OP_CHOICE).unwrap();
        assert_eq!(choice.repeated.unwrap().name, "options");
        assert!(choice.args[0].count);
        assert_eq!(choice.entry_size(), 4);
        let gold = events::BYTECODE.opcode(events::OP_GOLD).unwrap();
        assert_eq!(gold.fixed_size(), 1 + 1 + 3);
        assert_eq!(music::BYTECODE.fixed_size(music::OP_SET_PITCH_V3), Some(3));
    }
}
