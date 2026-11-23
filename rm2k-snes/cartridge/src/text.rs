//! Reading the assembler text the packing rewrites: a line's directive, its
//! first word, constants and labels.

/// What comes before the first `;`, trimmed: the directive of a line, with
/// its comment dropped.
pub fn code(line: &str) -> &str {
    line.split(';').next().unwrap_or("").trim()
}

/// The first word, and the rest with its leading blanks removed if there is
/// any.
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
