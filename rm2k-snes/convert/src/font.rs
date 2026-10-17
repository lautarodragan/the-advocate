//! The font the game's text is drawn with: the project file's `[text]
//! font`, and what the stages that measure a line need of it.
//!
//! It is a name —`rm2k`, RM2k's own six-pixel font, the one the game's
//! `font_id` picks; or one the engine carries, like `low-variable`— or the
//! path of a sheet of the game's own, relative to the project file: a sheet
//! is a PNG, and that is how the two are told apart. See
//! `rm2k_snes_text::font` for what a sheet is.
//!
//! And `[text] letter_spacing`, pixels added after every letter —see
//! `Font::with_spacing`—: **optional**, unlike the rest of the file,
//! because its absence has a meaning that is no other game's value, the
//! font as its sheet draws it.

use crate::fail::{Result, Stop};
use crate::settings::Settings;
use rm2k_snes_text::font::Font;
use serde_json::{json, Value};

/// The font, as the stages are told it, and its advances.
#[derive(Debug, Clone)]
pub struct FontChoice {
    /// The name, or the sheet's absolute path.
    pub spec: String,
    /// `[text] letter_spacing`, already in `font`; it goes to the stages
    /// that read the font themselves, next to `spec`.
    pub spacing: i64,
    pub font: Font,
}

impl FontChoice {
    /// `[text] font`, resolved and read: a font that cannot be read stops
    /// the conversion here, and not in the first stage that draws.
    pub fn of(settings: &Settings) -> Result<FontChoice> {
        let given = settings.string(&["text", "font"])?;
        let spec = if given.to_ascii_lowercase().ends_with(".png") {
            rm2k_project::absolute(settings.project.directory().join(&given))
                .to_string_lossy()
                .into_owned()
        } else {
            given
        };
        // `font_id` only matters to RM2k's, and only for the shape of the
        // letters, which no stage asks the converter for: the advances are
        // six either way.
        let font = Font::named(&spec, rm2k_snes_text::font::MINCHO)
            .map_err(|e| Stop::new(format!("[text] font: {e}")))?;
        let spacing = settings.project.int_or(&["text", "letter_spacing"], 0)?;
        let font = font
            .with_spacing(spacing)
            .map_err(|e| Stop::new(format!("[text] letter_spacing: {e}")))?;
        Ok(FontChoice { spec, spacing, font })
    }

    /// A message window as the event compiler takes it: `width` pixels a
    /// line, `lines` of them, the advances to measure a line with, and the
    /// Latin-1 letters the font draws with theirs —which of them the
    /// cartridge carries, the compiler decides—.
    pub fn window(&self, width: usize, lines: u32) -> Value {
        let letters: Vec<Value> = self.font.latin_letters().iter().map(|(c, a)| json!([c.to_string(), a])).collect();
        json!({"width": width, "lines": lines, "advances": self.font.console_advances(), "letters": letters})
    }
}
