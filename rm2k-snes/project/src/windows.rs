//! `[windows.background]`: what fills a window under its frame, by System.
//!
//! ```toml
//! [windows.background]
//! ablskin = "#000000"                               # one colour
//! Royal = ["#783f31", "#5a231f", "#421d2d"]         # a gradient, top to bottom
//! ```
//!
//! **Keyed by the System, not one value per game**, because a game changes
//! System while it plays (`ChangeSystemGraphics`) and each System has its own
//! background: whoever draws a window looks up the System that is current
//! then. The key is the System's name as RM2k names it —the database and the
//! command—, without its extension and without regard to case, as RPG_RT
//! finds the file on Windows; for a picture of the project's own in
//! `[graphics] system`, the stem of its file. A System with no entry keeps
//! its own background, stretched or tiled as the database says.
//!
//! A list is a vertical gradient: its stops evenly spread from each window's
//! first line to its last. No horizontal one: none of the games surveyed has
//! one, and the console can only change a colour between lines. Why the
//! setting exists, and what each game takes, is "The windows, made cheaper"
//! in the book's research.

use std::collections::BTreeMap;

use toml::Value;

use crate::{Error, Project};

/// A colour of the setting, 8 bits a channel as the file writes it.
pub type Rgb = [u8; 3];

/// One System's entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WindowBackground {
    /// `"#rrggbb"`.
    Color(Rgb),
    /// Two stops or more, top to bottom.
    Gradient(Vec<Rgb>),
}

impl WindowBackground {
    /// The stops, top to bottom: one for a colour.
    pub fn stops(&self) -> &[Rgb] {
        match self {
            WindowBackground::Color(c) => std::slice::from_ref(c),
            WindowBackground::Gradient(stops) => stops,
        }
    }

    /// The one colour a window is drawn with while there is no gradient to
    /// draw it with: the colour itself, or the gradient's average —the mean
    /// of the line its stops draw, so the two ends weigh half—, rounded to
    /// the nearest. The average and not the first stop: it is what the
    /// window looks like from afar, and a gradient's ends are usually its
    /// lightest and its darkest.
    pub fn flat(&self) -> Rgb {
        let stops = self.stops();
        if stops.len() == 1 {
            return stops[0];
        }
        let segments = (stops.len() - 1) as u32;
        let mut out = [0u8; 3];
        for (channel, o) in out.iter_mut().enumerate() {
            // Twice the sum of the segments' means, over twice the segments.
            let twice: u32 = stops
                .windows(2)
                .map(|w| w[0][channel] as u32 + w[1][channel] as u32)
                .sum();
            *o = ((twice + segments) / (2 * segments)) as u8;
        }
        out
    }
}

/// `"#rrggbb"` as a colour, or None.
pub fn parse_color(text: &str) -> Option<Rgb> {
    let hex = text.strip_prefix('#')?;
    if hex.len() != 6 || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let channel = |k: usize| u8::from_str_radix(&hex[k..k + 2], 16).ok();
    Some([channel(0)?, channel(2)?, channel(4)?])
}

/// A colour as the setting writes it, `"#rrggbb"` in lowercase.
pub fn color_text(c: Rgb) -> String {
    format!("#{:02x}{:02x}{:02x}", c[0], c[1], c[2])
}

const KEYS: [&str; 2] = ["windows", "background"];

impl Project {
    /// Every entry of `[windows.background]`, by the System's name as the
    /// file writes it; empty without the table. Fails on a value that is
    /// neither a colour nor a list of two colours or more, and on two names
    /// that are the same System —they differ only in case—.
    pub fn window_backgrounds(&self) -> Result<BTreeMap<String, WindowBackground>, Error> {
        let Ok(value) = self.value(&KEYS) else {
            return Ok(BTreeMap::new());
        };
        let table = value.as_table().ok_or_else(|| {
            Error(format!(
                "{}: windows.background is a table keyed by the System's name —`[windows.background]` \
                 and then `<System> = \"#rrggbb\"`—, and is {value}",
                self.file().display()
            ))
        })?;
        let mut out = BTreeMap::new();
        let mut seen: BTreeMap<String, &str> = BTreeMap::new();
        for (name, v) in table {
            if let Some(other) = seen.insert(name.to_lowercase(), name) {
                return Err(Error(format!(
                    "{}: windows.background names the same System twice, {other:?} and {name:?}: \
                     a System's name does not distinguish case",
                    self.file().display()
                )));
            }
            out.insert(name.clone(), self.window_background_value(name, v)?);
        }
        Ok(out)
    }

    /// The entry for System `system` —its name without extension—, or None
    /// if it has none: then its windows keep the System's own background.
    pub fn window_background(&self, system: &str) -> Result<Option<WindowBackground>, Error> {
        Ok(self
            .window_backgrounds()?
            .into_iter()
            .find(|(name, _)| name.to_lowercase() == system.to_lowercase())
            .map(|(_, v)| v))
    }

    fn window_background_value(&self, name: &str, v: &Value) -> Result<WindowBackground, Error> {
        let keys = ["windows", "background", name];
        let expected = "\"#rrggbb\" or a list of two of those or more, top to bottom";
        let color = |v: &Value| v.as_str().and_then(parse_color);
        if let Some(c) = color(v) {
            return Ok(WindowBackground::Color(c));
        }
        match v.as_array() {
            Some(list) if list.len() >= 2 => list
                .iter()
                .map(color)
                .collect::<Option<Vec<_>>>()
                .map(WindowBackground::Gradient)
                .ok_or_else(|| self.wrong_type(&keys, expected, v)),
            _ => Err(self.wrong_type(&keys, expected, v)),
        }
    }
}
