//! What the cartridge does with less than RM2k, in one list next to the
//! ROM: `degradations.json`.
//!
//! **Complete by construction**: each entry is noted where the loss
//! happens —the event compiler's arms, Wally's notes, the ChipSet
//! animation's fit, the converter's own decisions— and this only gathers
//! and sorts them. A page left out whole is not here: that is the culprits
//! report, `rm2k-snes-events culprits`. Nor are the colours the converter
//! merged, which are the patches' (`rm2k-snes-patches`).
//!
//! Each entry says where, as precisely as whoever lost it knows: a map's
//! event page with its cell and the command's index; a common event or a
//! troop's page; a whole map; or the whole cartridge. And `kind`, a stable
//! slug to count by, and `text`, what is lost. A loss inside a common event
//! pasted into a page carries `via`, the pasted bodies with the command
//! each was at.

//!
//! An entry is the event compiler's [`Entry`], whose place is the richest
//! of the stages': the others' are a map or the cartridge, a kind and a
//! text, which the converter puts into one with [`Degradations::map`] and
//! [`Degradations::cartridge`].

use rm2k_snes_events::answer::Compiled;
use rm2k_snes_events::losses::{CommonRun, Entry, Where, LETTER_PLAIN};
use serde_json::json;
use std::collections::BTreeMap;
use std::path::Path;

/// The file, in the cartridge's directory.
pub const FILE: &str = "degradations.json";

#[derive(Debug, Default)]
pub struct Degradations {
    losses: Vec<Entry>,
    commons: BTreeMap<i32, CommonRun>,
}

impl Degradations {
    /// The event compiler's: every page of the cartridge's.
    pub fn add_compiler_answer(&mut self, answer: &Compiled) {
        let d = &answer.degradations;
        self.losses.extend(d.losses.iter().cloned());
        self.commons.extend(d.commons.clone());
    }

    /// Takes out what was not lost after all: what `done` says the
    /// conversion did on its own.
    pub fn forget(&mut self, done: impl Fn(&Entry) -> bool) {
        self.losses.retain(|l| !done(l));
    }

    /// A loss of a whole map, or of some of its events by RM2k id.
    pub fn map(&mut self, map: i64, kind: &str, text: &str, events: &[i64]) {
        self.losses.push(Entry {
            place: Where {
                map: Some(map),
                ..Where::default()
            },
            events: events.to_vec(),
            ..entry(kind, text)
        });
    }

    /// A loss of one map event, with its cell.
    pub fn event(&mut self, map: i64, event: i64, at: (i64, i64), kind: &str, text: &str) {
        self.losses.push(Entry {
            place: Where {
                map: Some(map),
                event: Some(event),
                page: Some(None),
                x: Some(at.0),
                y: Some(at.1),
                ..Where::default()
            },
            ..entry(kind, text)
        });
    }

    /// A loss of a whole troop, not of one of its pages.
    pub fn troop(&mut self, troop: i64, kind: &str, text: &str) {
        self.losses.push(Entry {
            place: Where {
                troop: Some(troop),
                page: Some(None),
                ..Where::default()
            },
            ..entry(kind, text)
        });
    }

    /// A loss of the whole cartridge: a screen, the window, the battle.
    pub fn cartridge(&mut self, kind: &str, text: &str) {
        self.losses.push(entry(kind, text));
    }

    /// The losses, sorted: the maps' by map, event, page and command —so a
    /// map's are together, and its whole-map ones first—, then the common
    /// events', the troops', and the cartridge's.
    fn sorted(&self) -> Vec<Entry> {
        let key = |l: &Entry| {
            let p = &l.place;
            let group = if p.map.is_some() {
                0
            } else if p.common.is_some() {
                1
            } else if p.troop.is_some() {
                2
            } else {
                3
            };
            let first = p.map.or(p.common).or(p.troop).unwrap_or(-1);
            let event = p.event.unwrap_or(-1);
            let page = p.page.flatten().unwrap_or(-1);
            let command = p.command.flatten().unwrap_or(-1);
            (group, first, event, page, command, l.kind.clone())
        };
        let mut out = self.losses.clone();
        out.sort_by_key(key);
        out
    }

    /// How many of each kind.
    pub fn counts(&self) -> BTreeMap<String, usize> {
        let mut out = BTreeMap::new();
        for l in &self.losses {
            *out.entry(l.kind.clone()).or_insert(0) += 1;
        }
        out
    }

    /// Writes the file into `dir` and says how much is in it.
    pub fn write(&self, dir: &Path) -> crate::fail::Result<()> {
        let counts = self.counts();
        let answer = json!({
            "about": "What this cartridge does with less than RM2k, each where it is. Pages left out whole \
                      are not here: see `rm2k-snes-events culprits`.",
            "counts": counts,
            "losses": self.sorted(),
            "commons": self.commons,
        });
        let path = dir.join(FILE);
        std::fs::write(&path, serde_json::to_string_pretty(&answer).unwrap() + "\n")
            .map_err(|e| crate::fail::io(&path, e))?;
        println!(
            "  degradations: {} in {} kind(s), in {FILE}",
            self.losses.len(),
            counts.len()
        );
        if let Some(line) = self.plain_warning() {
            println!("{line}");
        }
        Ok(())
    }

    /// The warning for the letters the text boxes show plain —see
    /// `rm2k_snes_text::plain`—, all of them in one line, or `None` if no
    /// box does. A warning and not only one more count, because it is the
    /// game's text that changes, which a player reads on every page.
    fn plain_warning(&self) -> Option<String> {
        let mut commands = 0;
        let mut letters: Vec<String> = Vec::new();
        for l in self.losses.iter().filter(|l| l.kind == LETTER_PLAIN) {
            commands += 1;
            let text = l.text.as_str();
            let each = text.split_once(": ").map_or("", |(_, e)| e);
            for one in each.split(", ").filter(|e| !e.is_empty()) {
                if !letters.iter().any(|x| x == one) {
                    letters.push(one.to_string());
                }
            }
        }
        (commands > 0).then(|| {
            format!(
                "  WARNING, letter-plain: {commands} command(s) show letters their box does not draw as plain ASCII: {}",
                letters.join(", ")
            )
        })
    }
}

/// An entry without a place: the whole cartridge's, or one a place is
/// put into.
fn entry(kind: &str, text: &str) -> Entry {
    Entry {
        kind: kind.to_string(),
        text: text.trim().to_string(),
        ..Entry::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A place by map, event, common event, page and command.
    fn at(
        map: Option<i64>,
        event: Option<i64>,
        common: Option<i64>,
        page: Option<i64>,
        command: Option<i64>,
    ) -> Where {
        Where {
            map,
            event,
            common,
            page: page.map(Some),
            command: command.map(Some),
            ..Where::default()
        }
    }

    #[test]
    fn the_plain_letters_are_one_warning_with_every_letter_once() {
        let mut d = Degradations::default();
        assert_eq!(d.plain_warning(), None);
        let text = |t: &str| format!("letters the box does not draw are shown plain: {t}");
        let plain = |command: i64, letters: &str| Entry {
            place: at(Some(8), Some(3), None, None, Some(command)),
            ..entry(LETTER_PLAIN, &text(letters))
        };
        d.losses.push(plain(0, "é as e, ¿ as ?"));
        d.losses.push(plain(2, "é as e, ß as ss"));
        assert_eq!(
            d.plain_warning().unwrap(),
            "  WARNING, letter-plain: 2 command(s) show letters their box does not draw as plain ASCII: é as e, ¿ as ?, ß as ss"
        );
    }

    #[test]
    fn the_maps_go_first_and_in_order_then_the_rest() {
        let mut d = Degradations::default();
        d.cartridge("title-menu-not-drawn", "x");
        let lost = |place: Where, kind: &str| Entry {
            place,
            ..entry(kind, "")
        };
        d.losses.push(lost(
            Where {
                troop: Some(3),
                ..at(None, None, None, Some(1), Some(0))
            },
            "b",
        ));
        d.losses
            .push(lost(at(None, None, Some(9), None, Some(2)), "a"));
        d.losses
            .push(lost(at(Some(7), Some(2), None, Some(1), Some(5)), "a"));
        d.map(7, "rain-not-drawn", "y", &[]);
        d.losses
            .push(lost(at(Some(3), Some(9), None, Some(2), Some(0)), "a"));
        let places: Vec<String> = d
            .sorted()
            .iter()
            .map(|v| {
                let p = &v.place;
                let n = |x: Option<i64>| x.map_or("null".to_string(), |x| x.to_string());
                format!("{}/{}/{}/{}", n(p.map), n(p.event), n(p.common), n(p.troop))
            })
            .collect();
        assert_eq!(
            places,
            [
                "3/9/null/null",
                "7/null/null/null",
                "7/2/null/null",
                "null/null/9/null",
                "null/null/null/3",
                "null/null/null/null"
            ]
        );
        assert_eq!(d.counts()["a"], 3);
    }
}
