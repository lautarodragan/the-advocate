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

use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::path::Path;

/// The file, in the cartridge's directory.
pub const FILE: &str = "degradations.json";

#[derive(Debug, Default)]
pub struct Degradations {
    losses: Vec<Value>,
    commons: Map<String, Value>,
}

impl Degradations {
    /// The event compiler's: every page of the cartridge's.
    pub fn from_events(&mut self, answer: &Value) {
        let d = &answer["degradations"];
        self.losses
            .extend(d["losses"].as_array().cloned().unwrap_or_default());
        if let Some(commons) = d["commons"].as_object() {
            self.commons.extend(commons.clone());
        }
    }

    /// Takes out what was not lost after all: what `done` says the
    /// conversion did on its own.
    pub fn forget(&mut self, done: impl Fn(&Value) -> bool) {
        self.losses.retain(|l| !done(l));
    }

    /// A loss of a whole map, or of some of its events by RM2k id.
    pub fn map(&mut self, map: i64, kind: &str, text: &str, events: &[i64]) {
        let mut entry = json!({"map": map, "kind": kind, "text": text.trim()});
        if !events.is_empty() {
            entry["events"] = json!(events);
        }
        self.losses.push(entry);
    }

    /// A loss of one map event, with its cell.
    pub fn event(&mut self, map: i64, event: i64, at: (i64, i64), kind: &str, text: &str) {
        self.losses.push(json!({
            "map": map, "event": event, "page": null, "x": at.0, "y": at.1, "kind": kind, "text": text.trim(),
        }));
    }

    /// A loss of a whole troop, not of one of its pages.
    pub fn troop(&mut self, troop: i64, kind: &str, text: &str) {
        self.losses
            .push(json!({"troop": troop, "page": null, "kind": kind, "text": text.trim()}));
    }

    /// A loss of the whole cartridge: a screen, the window, the battle.
    pub fn cartridge(&mut self, kind: &str, text: &str) {
        self.losses.push(json!({"kind": kind, "text": text.trim()}));
    }

    /// The losses, sorted: the maps' by map, event, page and command —so a
    /// map's are together, and its whole-map ones first—, then the common
    /// events', the troops', and the cartridge's.
    fn sorted(&self) -> Vec<Value> {
        let int = |v: &Value, k: &str| v.get(k).and_then(Value::as_i64);
        let key = |v: &Value| {
            let group = if int(v, "map").is_some() {
                0
            } else if int(v, "common").is_some() {
                1
            } else if int(v, "troop").is_some() {
                2
            } else {
                3
            };
            let first = int(v, "map")
                .or(int(v, "common"))
                .or(int(v, "troop"))
                .unwrap_or(-1);
            let event = int(v, "event").unwrap_or(-1);
            let page = int(v, "page").unwrap_or(-1);
            let command = int(v, "command").unwrap_or(-1);
            let kind = v["kind"].as_str().unwrap_or("").to_string();
            (group, first, event, page, command, kind)
        };
        let mut out = self.losses.clone();
        out.sort_by_key(key);
        out
    }

    /// How many of each kind.
    pub fn counts(&self) -> BTreeMap<String, usize> {
        let mut out = BTreeMap::new();
        for l in &self.losses {
            *out.entry(l["kind"].as_str().unwrap_or("").to_string())
                .or_insert(0) += 1;
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
        for l in self.losses.iter().filter(|l| l["kind"] == "letter-plain") {
            commands += 1;
            let text = l["text"].as_str().unwrap_or("");
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_plain_letters_are_one_warning_with_every_letter_once() {
        let mut d = Degradations::default();
        assert_eq!(d.plain_warning(), None);
        let text = |t: &str| format!("letters the box does not draw are shown plain: {t}");
        d.losses.push(json!({"map": 8, "event": 3, "page": 1, "command": 0, "kind": "letter-plain", "text": text("é as e, ¿ as ?")}));
        d.losses.push(json!({"map": 8, "event": 3, "page": 1, "command": 2, "kind": "letter-plain", "text": text("é as e, ß as ss")}));
        assert_eq!(
            d.plain_warning().unwrap(),
            "  WARNING, letter-plain: 2 command(s) show letters their box does not draw as plain ASCII: é as e, ¿ as ?, ß as ss"
        );
    }

    #[test]
    fn the_maps_go_first_and_in_order_then_the_rest() {
        let mut d = Degradations::default();
        d.cartridge("title-menu-not-drawn", "x");
        d.losses
            .push(json!({"troop": 3, "page": 1, "command": 0, "kind": "b", "text": ""}));
        d.losses
            .push(json!({"common": 9, "command": 2, "kind": "a", "text": ""}));
        d.losses
            .push(json!({"map": 7, "event": 2, "page": 1, "command": 5, "kind": "a", "text": ""}));
        d.map(7, "rain-not-drawn", "y", &[]);
        d.losses
            .push(json!({"map": 3, "event": 9, "page": 2, "command": 0, "kind": "a", "text": ""}));
        let places: Vec<String> = d
            .sorted()
            .iter()
            .map(|v| format!("{}/{}/{}/{}", v["map"], v["event"], v["common"], v["troop"]))
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
