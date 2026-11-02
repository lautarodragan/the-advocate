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
//! And the game's ExFont, the icons a `$` and a letter draw, which are not
//! the project's but the game's: they come from its `RPG_RT.exe`, or a
//! sheet of its own —see `rm2k_render::exfont::find`—, and the stages are
//! handed its path, `exfont`, next to the font's name. A game without one
//! drops the codes. `[text] exfont`, **optional**, names the file in the
//! game's directory for a game that runs with another executable —Zounds'
//! icons are in its `RPG_RT_a.exe`—.

use crate::fail::{Result, Stop};
use crate::settings::Settings;
use rm2k_snes_text::font::Font;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

/// The font, as the stages are told it, and its advances.
#[derive(Debug, Clone)]
pub struct FontChoice {
    /// The name, or the sheet's absolute path.
    pub spec: String,
    /// `[text] letter_spacing`, already in `font`; it goes to the stages
    /// that read the font themselves, next to `spec`.
    pub spacing: i64,
    /// The game's executable, when it carries an ExFont: its icons are in
    /// `font`, and the stages read them from here.
    pub exfont: Option<PathBuf>,
    pub font: Font,
}

impl FontChoice {
    /// `[text] font`, resolved and read: a font that cannot be read stops
    /// the conversion here, and not in the first stage that draws.
    pub fn of(settings: &Settings, game_dir: &Path) -> Result<FontChoice> {
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
        let named = match settings.project.value(&["text", "exfont"]) {
            Err(_) => None,
            Ok(v) => Some(
                v.as_str()
                    .ok_or_else(|| {
                        Stop::new("[text] exfont is the name of a file in the game's directory")
                    })?
                    .to_string(),
            ),
        };
        let file = rm2k_render::exfont::find(game_dir, named.as_deref());
        if let (Some(name), Some(path)) = (&named, &file) {
            if !path.is_file() {
                return Err(Stop::new(format!(
                    "[text] exfont: the game has no {name:?}"
                )));
            }
        }
        let font = font
            .with_exfont_of(file.as_deref())
            .map_err(|e| Stop::new(format!("the game's ExFont: {e}")))?;
        let exfont = file.filter(|_| font.has_exfont());
        Ok(FontChoice {
            spec,
            spacing,
            exfont,
            font,
        })
    }

    /// What a request names the font with: `font`, `letter_spacing` and,
    /// when the game has one, `exfont`.
    pub fn request(&self) -> Value {
        let mut out = json!({"font": self.spec, "letter_spacing": self.spacing});
        if let Some(exe) = &self.exfont {
            out["exfont"] = json!(exe.to_string_lossy());
        }
        out
    }

    /// A message window as the event compiler takes it: `width` pixels a
    /// line, `lines` of them, the advances to measure a line with, and the
    /// Latin-1 letters the font draws with theirs —which of them the
    /// cartridge carries, the compiler decides—, and after them the halves
    /// of the ExFont's icons, if the game has one.
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
