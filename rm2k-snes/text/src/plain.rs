//! The letters a font does not have, as the plain ASCII ones that stand in
//! for them: `é` as `e`, `ñ` as `n`, `¿` as `?`, `ß` as `ss`, `…` as `...`.
//!
//! RM2k's font has Latin-1 —and RPG_RT draws Windows-1252's few extras,
//! the curly quotes and the ellipsis—, and the console's fonts are printable
//! ASCII. A box with such a letter used to leave its whole page out, which
//! is most of what the games in Spanish and German lose of their talk; now
//! the letter is shown as its plain neighbour, and whoever stands one in
//! says so —the event compiler notes it in `degradations.json`—.
//!
//! The table is what a reader would write by hand without the key: the
//! accent off, a ligature as its two letters, an inverted mark as the mark.
//! A character without an entry has no plain stand-in, and stays as it is:
//! what to do with it is the caller's.

/// The plain ASCII that stands in for `c`, or `None` when `c` is already
/// printable ASCII or has no stand-in.
pub fn plain(c: char) -> Option<&'static str> {
    Some(match c {
        'À' | 'Á' | 'Â' | 'Ã' | 'Ä' | 'Å' => "A",
        'Æ' => "AE",
        'Ç' => "C",
        'È' | 'É' | 'Ê' | 'Ë' => "E",
        'Ì' | 'Í' | 'Î' | 'Ï' => "I",
        'Ð' => "D",
        'Ñ' => "N",
        'Ò' | 'Ó' | 'Ô' | 'Õ' | 'Ö' | 'Ø' => "O",
        'Ù' | 'Ú' | 'Û' | 'Ü' => "U",
        'Ý' | 'Ÿ' => "Y",
        'Þ' => "Th",
        'ß' => "ss",
        'à' | 'á' | 'â' | 'ã' | 'ä' | 'å' => "a",
        'æ' => "ae",
        'ç' => "c",
        'è' | 'é' | 'ê' | 'ë' => "e",
        'ì' | 'í' | 'î' | 'ï' => "i",
        'ð' => "d",
        'ñ' => "n",
        'ò' | 'ó' | 'ô' | 'õ' | 'ö' | 'ø' => "o",
        'ù' | 'ú' | 'û' | 'ü' => "u",
        'ý' | 'ÿ' => "y",
        'þ' => "th",
        'Œ' => "OE",
        'œ' => "oe",
        'Š' => "S",
        'š' => "s",
        'Ž' => "Z",
        'ž' => "z",
        '¡' => "!",
        '¿' => "?",
        '«' => "<<",
        '»' => ">>",
        '‹' => "<",
        '›' => ">",
        '‘' | '’' | '‚' | '´' => "'",
        '“' | '”' | '„' | '¨' => "\"",
        '–' | '—' | '¬' | '¯' | '\u{ad}' => "-",
        '…' => "...",
        '·' | '•' => "*",
        '°' | 'º' => "o",
        'ª' => "a",
        '×' => "x",
        '÷' => "/",
        '±' => "+-",
        '¹' => "1",
        '²' => "2",
        '³' => "3",
        '¼' => "1/4",
        '½' => "1/2",
        '¾' => "3/4",
        '©' => "(c)",
        '®' => "(R)",
        '™' => "TM",
        '§' => "S",
        '¶' => "P",
        'µ' => "u",
        '¢' => "c",
        '£' => "L",
        '¥' => "Y",
        '€' => "E",
        '¦' => "|",
        '¸' => ",",
        'ˆ' => "^",
        '˜' => "~",
        '†' | '‡' => "+",
        '‰' => "%",
        '\u{a0}' => " ",
        _ => return None,
    })
}

/// `text` with every letter that has a stand-in replaced by it, and the
/// letters replaced, in order and once each.
pub fn plain_text(text: &str) -> (String, Vec<char>) {
    let mut out = String::with_capacity(text.len());
    let mut replaced = Vec::new();
    for c in text.chars() {
        match plain(c) {
            Some(p) => {
                out.push_str(p);
                if !replaced.contains(&c) {
                    replaced.push(c);
                }
            }
            None => out.push(c),
        }
    }
    (out, replaced)
}

/// What standing in `letters` loses, said for a build's report: each
/// letter and the ASCII drawn for it.
pub fn plain_loss(letters: &[char]) -> String {
    let each: Vec<String> = letters
        .iter()
        .map(|&c| format!("{c} as {}", plain(c).unwrap_or("?")))
        .collect();
    format!("letters the font does not have are shown plain: {}", each.join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_letter_without_its_accent_and_a_ligature_as_its_two() {
        assert_eq!(
            plain_text("¿Qué pasó, señor Unamë? ¡Weiß…!"),
            (
                "?Que paso, senor Uname? !Weiss...!".to_string(),
                vec!['¿', 'é', 'ó', 'ñ', 'ë', '¡', 'ß', '…']
            )
        );
    }

    #[test]
    fn ascii_and_what_has_no_stand_in_stay() {
        assert_eq!(plain('e'), None);
        assert_eq!(plain('ア'), None);
        assert_eq!(plain_text("aアb"), ("aアb".to_string(), vec![]));
    }

    /// Every stand-in is printable ASCII, which is what the console's fonts
    /// have: one that is not would trade a letter for another the font
    /// lacks.
    #[test]
    fn every_stand_in_is_printable_ascii() {
        for c in '\u{80}'..='\u{2200}' {
            if let Some(p) = plain(c) {
                assert!(p.bytes().all(|b| (32..127).contains(&b)), "{c:?} as {p:?}");
            }
        }
    }

    /// The reflow measures a letter as what will be drawn for it, so a box
    /// with `…` is not cut short once it becomes three periods.
    #[test]
    fn a_stand_in_is_measured_as_what_is_drawn() {
        let m = crate::refit::Measure::columns(39);
        assert_eq!(m.of("é"), m.of("e"));
        assert_eq!(m.of("Weiß…"), m.of("Weiss..."));
    }

    #[test]
    fn the_loss_says_each_letter_and_what_is_drawn() {
        assert_eq!(
            plain_loss(&['é', 'ß']),
            "letters the font does not have are shown plain: é as e, ß as ss"
        );
    }
}
