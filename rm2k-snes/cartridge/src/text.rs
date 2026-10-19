//! Reading assembler text the way the rest of the suite reads it.
//!
//! The converter that writes the data files is still Python, and the packing
//! rewrites them in place: the lines have to be cut, and put back together,
//! exactly as Python's `splitlines`, `split` and `strip` would, or the files
//! stop coming out byte for byte the same.

/// The lines of `text` without their endings, cutting where Python's
/// `str.splitlines` cuts: `\n`, `\r`, `\r\n` and the rarer separators.
pub fn split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        let breaks = matches!(
            c,
            '\n' | '\r'
                | '\x0b'
                | '\x0c'
                | '\x1c'
                | '\x1d'
                | '\x1e'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if !breaks {
            continue;
        }
        lines.push(&text[start..i]);
        start = i + c.len_utf8();
        if c == '\r' {
            if let Some(&(j, '\n')) = chars.peek() {
                chars.next();
                start = j + 1;
            }
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

/// What comes before the first `;`, trimmed: the directive of a line, with
/// its comment dropped.
pub fn code(line: &str) -> &str {
    line.split(';').next().unwrap_or("").trim()
}

/// The first word, and the rest with its leading blanks removed if there is
/// any: Python's `str.split(None, 1)` over a trimmed string.
pub fn first_word(text: &str) -> (&str, Option<&str>) {
    let text = text.trim_start();
    match text.find(char::is_whitespace) {
        None => (text, None),
        Some(end) => {
            let rest = text[end..].trim_start();
            (
                &text[..end],
                if rest.is_empty() { None } else { Some(rest) },
            )
        }
    }
}

/// Whether `text` starts with an identifier: an ASCII letter or `_`, then
/// letters, digits and `_`. Returns where the identifier ends.
pub fn identifier(text: &str) -> Option<usize> {
    let mut chars = text.char_indices();
    match chars.next() {
        Some((_, c)) if c.is_ascii_alphabetic() || c == '_' => {}
        _ => return None,
    }
    for (i, c) in chars {
        if !(c.is_alphanumeric() || c == '_') {
            return Some(i);
        }
    }
    Some(text.len())
}

/// `NAME = …`: a constant, which stays where it was written.
pub fn is_constant(directive: &str) -> bool {
    identifier(directive).is_some_and(|end| directive[end..].trim_start().starts_with('='))
}

/// `name:` at the start of the line: a label.
pub fn is_label(directive: &str) -> bool {
    identifier(directive).is_some_and(|end| directive[end..].starts_with(':'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lines_are_cut_like_python() {
        assert_eq!(split_lines("a\nb\r\nc\rd"), ["a", "b", "c", "d"]);
        assert_eq!(split_lines("a\n"), ["a"]);
        assert_eq!(split_lines("a\n\nb"), ["a", "", "b"]);
        assert!(split_lines("").is_empty());
        assert_eq!(split_lines("x\x0cy"), ["x", "y"]);
    }

    #[test]
    fn the_first_word_and_the_rest() {
        assert_eq!(first_word("  .byte  1, 2 "), (".byte", Some("1, 2 ")));
        assert_eq!(first_word(".byte   "), (".byte", None));
        assert_eq!(first_word(""), ("", None));
    }

    #[test]
    fn constants_and_labels() {
        assert!(is_constant("CONSTANT = 7"));
        assert!(is_constant("X=1"));
        assert!(!is_constant("label: .byte 1"));
        assert!(is_label("label:"));
        assert!(is_label("_a1:"));
        assert!(!is_label("1a:"));
        assert!(!is_label("a :"));
    }
}
