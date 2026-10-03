//! How a name is quoted in the `.inc`'s comments.
//!
//! The comments that head each map's record carry its name quoted the way
//! the converter always wrote them, which was Python's `repr`: single
//! quotes, unless the name has one and no double quote. The console's
//! tests read the map order from those lines, and the `.inc` has to come
//! out the same, so the quoting is the same.

/// `name` quoted as Python's `repr` quotes a string.
pub fn quoted(name: &str) -> String {
    let quote = if name.contains('\'') && !name.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(name.len() + 2);
    out.push(quote);
    for c in name.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if printable(c) => out.push(c),
            c if (c as u32) < 0x100 => out.push_str(&format!("\\x{:02x}", c as u32)),
            c if (c as u32) < 0x10000 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push_str(&format!("\\U{:08x}", c as u32)),
        }
    }
    out.push(quote);
    out
}

/// Python's `str.isprintable` for one character, as far as a game's names
/// go: the controls and the separators other than the space are not.
fn printable(c: char) -> bool {
    let n = c as u32;
    !(n < 0x20
        || (0x7F..0xA1).contains(&n)
        || n == 0xAD
        || matches!(n, 0x2000..=0x200F | 0x2028..=0x202F | 0x205F..=0x2064 | 0x3000 | 0xFEFF))
}

#[cfg(test)]
mod tests {
    use super::quoted;

    #[test]
    fn a_name_is_quoted_as_the_converter_always_did() {
        assert_eq!(quoted("Grove Town - 34,35"), "'Grove Town - 34,35'");
        assert_eq!(quoted("Miller's Cottage"), "\"Miller's Cottage\"");
        assert_eq!(quoted("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(quoted("back\\slash"), "'back\\\\slash'");
        assert_eq!(quoted("tab\there"), "'tab\\there'");
        assert_eq!(quoted("año"), "'año'");
        assert_eq!(quoted("nb\u{a0}sp"), "'nb\\xa0sp'");
    }
}
