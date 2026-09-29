//! The declaration: what a TOML file is allowed to say, and what it means.
//!
//! Every error carries the file and the opcode it came from. That is not
//! politeness: this tool's whole job is to be the one place a number is
//! written, so the moment a declaration is wrong it has to say exactly where.

use serde::Deserialize;
use std::fmt;
use std::path::Path;

/// A problem in a declaration. `Display` is what the user reads.
#[derive(Debug)]
pub struct Bad(pub String);

impl fmt::Display for Bad {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Bad {}

pub type Result<T> = std::result::Result<T, Bad>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Type {
    Byte,
    Word,
    Long,
}

impl Type {
    pub fn size(self) -> u32 {
        match self {
            Type::Byte => 1,
            Type::Word => 2,
            Type::Long => 3,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Arg {
    pub name: String,
    #[serde(rename = "type")]
    pub kind: Type,
    /// Names the repeated group this argument says the length of.
    #[serde(default)]
    pub count: Option<String>,
    #[serde(default)]
    pub signed: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Repeated {
    pub name: String,
    pub args: Vec<Arg>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Opcode {
    pub name: String,
    pub code: u32,
    #[serde(default)]
    pub args: Vec<Arg>,
    #[serde(default)]
    pub repeated: Option<Repeated>,
}

impl Opcode {
    /// The opcode byte plus its arguments.
    pub fn fixed_size(&self) -> u32 {
        1 + self.args.iter().map(|a| a.kind.size()).sum::<u32>()
    }

    pub fn entry_size(&self) -> u32 {
        self.repeated
            .as_ref()
            .map_or(0, |r| r.args.iter().map(|a| a.kind.size()).sum())
    }

    /// Where the argument holding how many entries follow starts.
    pub fn count_offset(&self) -> u32 {
        let mut at = 1;
        for a in &self.args {
            if a.count.is_some() {
                return at;
            }
            at += a.kind.size();
        }
        at
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Declaration {
    pub name: String,
    #[serde(rename = "opcode")]
    pub opcodes: Vec<Opcode>,
}

impl Declaration {
    /// The opcodes in the order of their numbers, if those numbers are exactly
    /// 0, 1, 2… with nothing missing: what a jump table indexed by the opcode
    /// needs. A gap would be a slot that jumps anywhere, so it is refused and
    /// named instead of filled with a guess.
    pub fn in_code_order(&self) -> std::result::Result<Vec<&Opcode>, String> {
        let mut sorted: Vec<&Opcode> = self.opcodes.iter().collect();
        sorted.sort_by_key(|o| o.code);
        let missing: Vec<String> = (0..sorted.last().map_or(0, |o| o.code))
            .filter(|c| !sorted.iter().any(|o| o.code == *c))
            .map(|c| format!("0x{c:02X}"))
            .collect();
        if missing.is_empty() {
            Ok(sorted)
        } else {
            // A long list is noise: the first few say what is wrong.
            let shown = missing.iter().take(8).cloned().collect::<Vec<_>>().join(", ");
            let more = if missing.len() > 8 {
                format!(" and {} more", missing.len() - 8)
            } else {
                String::new()
            };
            Err(format!(
                "a jump table needs the {} opcodes numbered from 0 with no gaps; \
                 nothing takes {shown}{more}",
                self.name
            ))
        }
    }
}

pub fn load(path: &Path) -> Result<Declaration> {
    let shown = path.display();
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad(format!("{shown}: {e}")))?;
    let declaration: Declaration = toml::from_str(&text)
        .map_err(|e| Bad(format!("{shown}: {}", tidy(&e.to_string()))))?;

    if declaration.opcodes.is_empty() {
        return Err(Bad(format!("{shown}: not a single [[opcode]]")));
    }

    let mut seen: Vec<(u32, &str)> = Vec::new();
    for o in &declaration.opcodes {
        if let Some((_, other)) = seen.iter().find(|(c, _)| *c == o.code) {
            return Err(Bad(format!(
                "{shown}: {} and {other} both take 0x{:02X}",
                o.name, o.code
            )));
        }
        seen.push((o.code, &o.name));

        let counted: Vec<&String> =
            o.args.iter().filter_map(|a| a.count.as_ref()).collect();
        match (&o.repeated, counted.as_slice()) {
            (Some(r), [one]) if *one == &r.name => {}
            (Some(r), []) => {
                return Err(Bad(format!(
                    "{shown}: {} declares `repeated` {:?} and no argument counts it",
                    o.name, r.name
                )))
            }
            (Some(r), _) => {
                return Err(Bad(format!(
                    "{shown}: {} counts something other than its `repeated` {:?}",
                    o.name, r.name
                )))
            }
            (None, []) => {}
            (None, [one]) => {
                return Err(Bad(format!(
                    "{shown}: {} counts {one:?}, which is not declared",
                    o.name
                )))
            }
            (None, _) => {
                return Err(Bad(format!(
                    "{shown}: {} counts more than one group",
                    o.name
                )))
            }
        }
    }
    Ok(declaration)
}

/// Drops the source excerpt toml draws under the error —the `6 | args = ...`
/// lines— and keeps the prose. The first line says where and the last says
/// what, and the middle is noise next to the file name we add ourselves.
fn tidy(s: &str) -> String {
    s.lines()
        .map(str::trim_end)
        .filter(|l| !l.trim_start().starts_with('|'))
        .filter(|l| {
            // `6 | ...`: a line number, a bar, and the source.
            let rest = l.trim_start().trim_start_matches(|c: char| c.is_ascii_digit());
            !(rest.starts_with(" |") && rest.len() < l.trim_start().len())
        })
        .filter(|l| !l.is_empty())
        .collect::<Vec<_>>()
        .join("; ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    /// Writes a declaration to a temporary file and loads it.
    fn load_text(text: &str) -> Result<Declaration> {
        let path = std::env::temp_dir().join(format!(
            "protocol-test-{}-{:?}.toml",
            std::process::id(),
            std::thread::current().id()
        ));
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(text.as_bytes()).unwrap();
        let out = load(&path);
        let _ = std::fs::remove_file(&path);
        out
    }

    const ONE: &str = r#"
        name = "test"
        [[opcode]]
        name = "OP_A"
        code = 0x01
        args = [{ name = "x", type = "word" }]
    "#;

    #[test]
    fn a_declaration_loads_and_derives_its_sizes() {
        let d = load_text(ONE).unwrap();
        assert_eq!(d.name, "test");
        assert_eq!(d.opcodes[0].fixed_size(), 3);
    }

    /// The bug this whole tool exists for: two opcodes on the same number.
    /// It used to be found by a merge, days later.
    #[test]
    fn two_opcodes_cannot_share_a_number() {
        let e = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            [[opcode]]
            name = "OP_B"
            code = 0x01
        "#,
        )
        .unwrap_err();
        assert!(e.0.contains("OP_B and OP_A both take 0x01"), "{e}");
    }

    #[test]
    fn an_unknown_type_says_which_argument_and_what_is_allowed() {
        let e = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            args = [{ name = "x", type = "dword" }]
        "#,
        )
        .unwrap_err();
        assert!(e.0.contains("dword"), "{e}");
    }

    #[test]
    fn a_repeated_group_needs_something_counting_it() {
        let e = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            args = [{ name = "x", type = "byte" }]
            repeated = { name = "items", args = [{ name = "y", type = "byte" }] }
        "#,
        )
        .unwrap_err();
        assert!(e.0.contains("no argument counts it"), "{e}");
    }

    #[test]
    fn counting_a_group_that_is_not_declared_is_an_error() {
        let e = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            args = [{ name = "n", type = "byte", count = "items" }]
        "#,
        )
        .unwrap_err();
        assert!(e.0.contains("not declared"), "{e}");
    }

    /// A field nobody reads is a field somebody thought they had declared.
    #[test]
    fn a_misspelled_field_is_refused_instead_of_ignored() {
        let e = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            args = [{ name = "x", type = "byte", sgined = true }]
        "#,
        )
        .unwrap_err();
        assert!(e.0.contains("sgined"), "{e}");
    }

    #[test]
    fn a_declaration_with_no_opcodes_is_refused() {
        let e = load_text("name = \"test\"\nopcode = []\n").unwrap_err();
        assert!(e.0.contains("not a single"), "{e}");
    }

    /// Declared out of order is fine: the table follows the numbers.
    #[test]
    fn code_order_sorts_by_number_not_by_declaration() {
        let d = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_B"
            code = 0x01
            [[opcode]]
            name = "OP_A"
            code = 0x00
        "#,
        )
        .unwrap();
        let names: Vec<&str> =
            d.in_code_order().unwrap().iter().map(|o| o.name.as_str()).collect();
        assert_eq!(names, ["OP_A", "OP_B"]);
    }

    #[test]
    fn code_order_names_every_gap() {
        let d = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            [[opcode]]
            name = "OP_B"
            code = 0x04
        "#,
        )
        .unwrap();
        let e = d.in_code_order().unwrap_err();
        assert!(e.contains("nothing takes 0x00, 0x02, 0x03"), "{e}");
        assert!(e.contains("test opcodes"), "{e}");
    }

    /// A stream with an end marker at 0xFF is a normal declaration; it just
    /// cannot be a jump table, and the message should not list 250 numbers.
    #[test]
    fn a_long_list_of_gaps_is_cut_short() {
        let d = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x00
            [[opcode]]
            name = "OP_END"
            code = 0xFF
        "#,
        )
        .unwrap();
        let e = d.in_code_order().unwrap_err();
        assert!(e.contains("0x01, 0x02"), "{e}");
        assert!(e.contains("and 246 more"), "{e}");
    }

    #[test]
    fn a_missing_file_says_so_with_its_name() {
        let e = load(Path::new("no-such-declaration.toml")).unwrap_err();
        assert!(e.0.contains("no-such-declaration.toml"), "{e}");
    }

    /// Where the count sits and how big an entry is are what a reader needs to
    /// walk past an instruction it does not care about.
    #[test]
    fn a_variable_sized_opcode_derives_where_its_count_is() {
        let d = load_text(
            r#"
            name = "test"
            [[opcode]]
            name = "OP_A"
            code = 0x01
            args = [
              { name = "a", type = "byte" },
              { name = "b", type = "word" },
              { name = "n", type = "byte", count = "items" },
            ]
            repeated = { name = "items", args = [
              { name = "x", type = "word" },
            ] }
        "#,
        )
        .unwrap();
        let o = &d.opcodes[0];
        assert_eq!(o.fixed_size(), 5); // opcode + 1 + 2 + 1
        assert_eq!(o.count_offset(), 4); // after the opcode, the byte and the word
        assert_eq!(o.entry_size(), 2);
    }
}
