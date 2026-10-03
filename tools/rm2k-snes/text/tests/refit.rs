//! The reflow's rules, one by one, for a window of 39 characters by four
//! lines. That a whole game's boxes fit is the game's to check.
//!
//! The boxes are invented, but each one keeps the shape —the length of every
//! word, the punctuation, the speaker— of a box of the game the reflow was
//! tuned on that showed the rule: until 2026-10-02 they were that game's
//! own lines.

use rm2k_snes_text::refit::{escape_tail, fits, is_speaker, refit};

const COLUMNS: usize = 39;
const LINES: usize = 4;

fn s(lines: &[&str]) -> Vec<String> {
    lines.iter().map(|l| l.to_string()).collect()
}

fn reflow(lines: &[&str]) -> Vec<Vec<String>> {
    refit(&s(lines), COLUMNS, LINES)
}

/// The words of the boxes, without each one's speaker if they have one.
fn words(boxes: &[Vec<String>], speaker: bool) -> Vec<String> {
    let from = usize::from(speaker);
    boxes
        .iter()
        .flat_map(|b| b[from.min(b.len())..].to_vec())
        .flat_map(|l| l.split_whitespace().map(str::to_string).collect::<Vec<_>>())
        .collect()
}

#[test]
fn a_box_that_fits_is_left_alone() {
    // Not even the spaces inside: they are the author's.
    let b = s(&["                  < Wave >"]);
    assert_eq!(refit(&b, COLUMNS, LINES), vec![b]);
}

#[test]
fn it_is_rebuilt_and_keeps_the_speaker() {
    let b = ["ODILE", "I have pressing business across the Harbour", "Front. No turning back."];
    let out = reflow(&b);
    assert_eq!(out.len(), 1);
    assert_eq!(out[0][0], "ODILE");
    assert!(out[0].iter().all(|t| t.chars().count() <= COLUMNS));
    assert_eq!(words(&out, true), words(&[s(&b)], true));
}

#[test]
fn what_does_not_fit_is_split_and_repeats_the_speaker() {
    // As a game does with consecutive boxes of the same character.
    let b = [
        "FLINT",
        "According to this, the North Harbor is connected",
        "to the Front by an electromagnetic Lock, which",
        "keeps the Harbor from drifting into waves.",
    ];
    let out = reflow(&b);
    assert_eq!(out.len(), 2);
    assert!(out.iter().all(|c| c[0] == "FLINT"));
    assert!(out.iter().all(|c| c.len() <= LINES));
    assert_eq!(words(&out, true), words(&[s(&b)], true));
}

#[test]
fn the_tail_goes_at_the_end_of_the_last_box() {
    let out = reflow(&[
        "VEGA",
        "Thank you, Flint. And maybe... after all this,",
        "you'll be able to show me the result of the",
        "equation none of my detectors... can.\\|\\^",
    ]);
    assert!(out.len() > 1);
    assert!(out.last().unwrap().last().unwrap().ends_with("can.\\|\\^"));
    assert!(!out[..out.len() - 1].iter().flatten().any(|t| t.contains('\\')));
}

/// A line that is not the last one and takes up less than this looks cut
/// off.
const SHORT: usize = 2 * COLUMNS / 3;

#[test]
fn no_line_breaks_too_early() {
    // Except the last one of each box, no line ends up shorter than
    // `SHORT`: all of these have a way of breaking that satisfies it. The
    // first two are the ones that looked worst —"Remember," and "Well,"
    // alone on their line, so that the ones below ended in a period—.
    let cases: [&[&str]; 8] = [
        &["?????", "Remember, my alias for this excursion is", "\"Odile.\" We should have the element of", "surprise."],
        &["PERCY", "Well, this question won't get any easier.", "I've got to pick up my coat and go!"],
        &["?????", "That cleaning robot has been deactivated.", "Its polish mode has been switched off."],
        &["PERCY", "...but the Cable-Boats don't always run on", "time, and I might get stuck waiting for one."],
        &["PERCY", "It's Cargo Shed 004 - right near my apartment.", "I'm not getting anywhere!"],
        &["PERCY", "Maybe there'll be another one along", "pretty soon... at least, I hope there will!"],
        &["MAVIS", "Do you think he's one of the Night Gulls?", "Maybe they found out about our spy..."],
        &["VEGA", "Thank you, Flint. And maybe... after all this,", "you'll be able to show me the result of the", "equation none of my detectors... can."],
    ];
    for b in cases {
        let out = reflow(b);
        for c in &out {
            assert_eq!(c[0], b[0]);
            let short: Vec<&String> = c[1..c.len() - 1].iter().filter(|t| t.chars().count() < SHORT).collect();
            assert!(short.is_empty(), "{c:?}");
        }
        assert_eq!(words(&out, true), words(&[s(b)], true));
    }
}

#[test]
fn a_line_of_whole_sentences_may_be_short() {
    // Breaking between two short sentences reads as the author's line
    // break, and it is not traded for filling the line.
    assert_eq!(
        reflow(&["ODILE", "Tide is running out. There's no turning back."]),
        vec![s(&["ODILE", "Tide is running out.", "There's no turning back."])]
    );
    assert_eq!(
        reflow(&["PERCY", "Six minutes... I'm not sure I can make it."]),
        vec![s(&["PERCY", "Six minutes...", "I'm not sure I can make it."])]
    );
}

#[test]
fn a_name_is_not_split_from_its_number() {
    let out = reflow(&[
        "PERCY",
        "I'd better not go back through Sector 33. The Night",
        "Gulls wouldn't be happy to see me...",
    ]);
    assert!(!out.iter().flatten().any(|t| t.ends_with("Sector")), "{out:?}");
}

#[test]
fn no_box_is_added_for_nothing() {
    // If the text fits in one box, it is not split in two to look better:
    // one more box is one more key press.
    let out = reflow(&[
        "PERCY",
        "Well... time to get away from the Office. Now I've",
        "got an entire world to hide in...",
    ]);
    assert_eq!(out.len(), 1);
}

#[test]
fn who_speaks() {
    for (line, speaks) in [
        ("ODILE", true),
        ("DOCK OFFICER", true),
        ("?????", true),
        ("WHAT?", false),
        ("NO!", false),
        ("Odile", false),
    ] {
        assert_eq!(is_speaker(line), speaks, "{line}");
    }
}

#[test]
fn what_is_reflowed_fits_and_does_not_change_again() {
    let b = [
        "FLINT",
        "I already told you. He didn't go this way. Twice. And I will tell you",
        "again if you ask me again, because that is the kind of person I am.",
    ];
    for c in reflow(&b) {
        assert!(fits(&c, COLUMNS, LINES).unwrap(), "{c:?}");
        assert_eq!(refit(&c, COLUMNS, LINES), vec![c.clone()]);
    }
}

/// The escape tail's cases, which the event compiler cuts boxes with too:
/// `tests/escapes.json`.
#[test]
fn the_escape_tail_is_the_compilers() {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/escapes.json");
    let data: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    for case in data["cases"].as_array().unwrap() {
        let lines: Vec<String> = serde_json::from_value(case["lines"].clone()).unwrap();
        let got = escape_tail(&lines).ok();
        match &case["answer"] {
            serde_json::Value::Null => assert!(got.is_none(), "{lines:?}"),
            answer => {
                let (untailed, pauses, close) = got.unwrap_or_else(|| panic!("{lines:?} does not compile"));
                let want: (Vec<String>, usize, bool) = serde_json::from_value(answer.clone()).unwrap();
                assert_eq!((untailed, pauses, close), want, "{lines:?}");
            }
        }
    }
}
