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
//!
//! And `[text] exfont`, **optional**: the ExFont, the icons a `$` and a
//! letter draw, as the path of a sheet —a PNG or a BMP, see
//! `rm2k_render::exfont`— relative to the project file, like a font's. The
//! stages are handed its absolute path, `exfont`, next to the font's name.
//! Without it, or with `false`, the cartridge carries no icon and drops
//! every code. Absent and `false` mean the same today; `false` stays
//! because it says on purpose that a game has no room for the glyphs —each
//! half of an icon a box draws is 1,248 bytes of the window's tables—,
//! which a default sheet of the engine's own, once there is one, would not
//! change.
//!
//! It is never looked for in the game's directory, and a game's executable
//! —where RPG_RT keeps its own— is not read: taro's, from 2026-11-02, so
//! that no port depends on the `.exe` a game brings. A port that wants
//! RPG_RT's icons commits the sheet extracted from it, next to its project
//! file.

use crate::fail::{Result, Stop};
use crate::settings::Settings;
use rm2k_snes_text::font::Font;
use serde_json::{json, Value};
use std::path::PathBuf;

/// The font, as the stages are told it, and its advances.
#[derive(Debug, Clone)]
pub struct FontChoice {
    /// The name, or the sheet's absolute path.
    pub spec: String,
    /// `[text] letter_spacing`, already in `font`; it goes to the stages
    /// that read the font themselves, next to `spec`.
    pub spacing: i64,
    /// `[text] exfont`, the sheet's absolute path: its icons are in
    /// `font`, and the stages read them from here.
    pub exfont: Option<PathBuf>,
    pub font: Font,
}

impl FontChoice {
    /// `[text] font` and `[text] exfont`, resolved and read: a font that
    /// cannot be read stops the conversion here, and not in the first stage
    /// that draws.
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
        let exfont = match settings.project.value(&["text", "exfont"]) {
            Err(_) => None,
            Ok(v) if v.as_bool() == Some(false) => None,
            Ok(v) => {
                let given = v.as_str().ok_or_else(|| {
                    Stop::new(
                        "[text] exfont is the path of a sheet, a PNG or a BMP, relative to \
                         the project file; or false",
                    )
                })?;
                let path = rm2k_project::absolute(settings.project.directory().join(given));
                if !path.is_file() {
                    return Err(Stop::new(format!(
                        "[text] exfont: there is no {}",
                        path.display()
                    )));
                }
                Some(path)
            }
        };
        let font = font
            .with_exfont_of(exfont.as_deref())
            .map_err(|e| Stop::new(format!("[text] exfont: {e}")))?;
        Ok(FontChoice {
            spec,
            spacing,
            exfont,
            font,
        })
    }

    /// What a request names the font with: `font`, `letter_spacing` and,
    /// when the project names one, `exfont`.
    pub fn request(&self) -> Value {
        let mut out = json!({"font": self.spec, "letter_spacing": self.spacing});
        if let Some(sheet) = &self.exfont {
            out["exfont"] = json!(sheet.to_string_lossy());
        }
        out
    }

    /// A message window as the event compiler takes it: `width` pixels a
    /// line, `lines` of them, the advances to measure a line with, and the
    /// Latin-1 letters the font draws with theirs —which of them the
    /// cartridge carries, the compiler decides—, and after them the halves
    /// of the ExFont's icons, if the project names one.
    pub fn window(&self, width: usize, lines: u32) -> Value {
        let mut letters: Vec<Value> = self
            .font
            .latin_letters()
            .iter()
            .map(|(c, a)| json!([c.to_string(), a]))
            .collect();
        if self.font.has_exfont() {
            for icon in 0..rm2k_snes_text::exfont::ICONS {
                for half in rm2k_snes_text::exfont::halves(icon) {
                    letters.push(json!([half.to_string(), self.font.advance(half)]));
                }
            }
        }
        json!({"width": width, "lines": lines, "advances": self.font.console_advances(), "letters": letters})
    }
}
