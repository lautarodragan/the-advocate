//! The screens as a stage of a converter: what each of the commands it
//! calls answers, as the files they make, by name. The converter calls
//! these as functions —`convert`, `boxes`, `faces` and `window`—, and the
//! binary is a `main` over `window` and `layout`, which the tests ask, that
//! reads the request and writes the files into `--out`.
//!
//! **They read nothing but the place and the request they are given**: the
//! converter keeps their answers in its cache under the key of the flags
//! the binary took —which [`Place`] holds— and the request, and a function
//! that read anything else would hand back a stale answer.
//!
//! **And each starts and ends with no letters carried**: [`convert`] carries
//! the Latin-1 the text screens write in a `thread_local!` —see
//! `texts::carry_letters`—, which a process threw away when it ended. In
//! the converter one thread calls one stage after another, and the letters
//! one cartridge's `convert` carried would still be there for the next
//! call: see [`Fresh`].

use crate::answer;
use crate::fail::{Bad, Result};
use crate::request;
use crate::{boxes as box_table, convert as screens, faces as face_sets};
use crate::{message_window, texts, Game};
use rm2k_snes_text::font::Font;
use rm2k_snes_text::refit::Measure;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// The game a command draws, as the binary's flags give it: the dump, the
/// game's folder, the RTP, and the three ways a cartridge draws it other
/// than the database says. See the binary's `--help` for each.
#[derive(Debug, Clone, Default)]
pub struct Place {
    pub data: PathBuf,
    pub game_dir: PathBuf,
    pub rtp_dir: Option<PathBuf>,
    pub system: Option<String>,
    pub window_background: Option<String>,
    pub text_ink: bool,
}

impl Place {
    /// The game, with its RTP.
    pub fn game(&self) -> Result<Game> {
        let mut game = Game::from_dump(&self.data, &self.game_dir)?;
        game.rtp_dir = self.rtp_dir.clone();
        game.text_ink = self.text_ink;
        if let Some(system) = &self.system {
            game.use_system(system);
        }
        if let Some(background) = &self.window_background {
            game.use_window_background(background)?;
        }
        Ok(game)
    }
}

/// The letters carried, emptied when a stage starts and again when it
/// ends, however it ends: a stage answers the same on a thread that called
/// others before it as in a process of its own, and leaves nothing for the
/// next.
struct Fresh;

impl Fresh {
    fn start() -> Fresh {
        texts::carry_letters(&[]);
        Fresh
    }
}

impl Drop for Fresh {
    fn drop(&mut self) {
        texts::carry_letters(&[]);
    }
}

/// `answer` as the file `name`, as every JSON of this crate is written:
/// on one line, with no newline after it.
fn one(name: &str, answer: &impl serde::Serialize) -> Files {
    let text = serde_json::to_string(answer).expect("an answer is JSON");
    Files::from([(name.to_string(), text.into_bytes())])
}

/// The game, drawing with `font` —see [`request::TextFont`]—.
///
/// And with the Latin-1 letters the message boxes draw, `letters`, and the
/// ones only the text screens write, `screen_letters`, carried —see
/// `texts::carry_letters`—: every text a screen writes keeps them from
/// here on, until the stage ends.
pub fn game_with_font(
    place: &Place,
    font: &request::TextFont,
    letters: &[char],
    screen_letters: &[char],
) -> Result<Game> {
    let mut game = place.game()?;
    game.use_font(&font.font, font.letter_spacing, font.exfont.as_deref())?;
    let letters = texts::screen_letters(&game, letters, screen_letters)?;
    texts::carry_letters(&letters.screens);
    Ok(game)
}

/// `convert`: every screen a cartridge carries, as `screens.json`.
pub fn convert(place: &Place, request: &request::Convert) -> Result<Files> {
    let _fresh = Fresh::start();
    let game = game_with_font(
        place,
        &request.font,
        &request.letters,
        &request.screen_letters,
    )?;
    let answer = screens::convert(&game, &request.read()?)?;
    Ok(one("screens.json", &answer))
}

/// How a request's window measures a line: see [`request::Line`].
pub fn measure_of(line: &request::Line) -> Result<Measure> {
    if let Some(advances) = &line.advances {
        let mut advances = advances.clone();
        let mut half = 0;
        for &(letter, advance) in &line.letters {
            // An icon's half: they all move the line the same.
            if rm2k_snes_text::exfont::is_half(letter) {
                half = advance;
                continue;
            }
            let at = (letter as u32).saturating_sub(32) as usize;
            if advances.len() <= at {
                advances.resize(at + 1, 0);
            }
            advances[at] = advance;
        }
        return Ok(Measure::from_advances(advances, line.width).with_icons(half));
    }
    if let Some(name) = &line.font {
        let font = Font::named(name, rm2k_snes_text::font::MINCHO)
            .and_then(|f| f.with_spacing(line.letter_spacing))
            .and_then(|f| f.with_exfont_of(line.exfont.as_deref()))
            .map_err(Bad::answer)?;
        Ok(Measure::new(&font, line.width))
    } else {
        Ok(Measure::columns(line.columns))
    }
}

/// `boxes`: every message box of the game in `data` reflowed for the
/// console's window, as `boxes.json`.
pub fn boxes(data: &Path, request: &request::Boxes) -> Result<Files> {
    let _fresh = Fresh::start();
    let files: Vec<PathBuf> = request.map_files.values().cloned().collect();
    let table = box_table::table(data, &files, &measure_of(&request.line)?, request.lines)?;
    Ok(one("boxes.json", &table))
}

/// `faces`: the faces the message window shows, as `faces.json`.
pub fn faces(place: &Place, request: &request::Faces) -> Result<Files> {
    let _fresh = Fresh::start();
    let game = place.game()?;
    let drawn = face_sets::draw(&game, &request.faces)?;
    // Through a `Value`, as `window`'s: the binary's keys stay sorted.
    let answer = serde_json::to_value(face_sets::answer(&drawn)).expect("an answer is JSON");
    Ok(one("faces.json", &answer))
}

/// `window`: how many colour-memory entries the message window takes, as
/// `window.json`; with the request's `systems`, each one's window too.
pub fn window(place: &Place, request: &request::Window) -> Result<Files> {
    let _fresh = Fresh::start();
    let game = place.game()?;
    let skin = game.skin()?;
    let others = &request.systems;
    let merges_of = |merges: &[adeleine::Merge]| -> Vec<answer::WindowMerge> {
        merges
            .iter()
            .map(|m| (m.victim, m.target, m.pixels))
            .collect()
    };
    // Through a `Value`, so the binary writes its keys sorted, as it did
    // when this was `json!`; the converter's, which keeps the order they are
    // inserted in, writes them in the fields' order, which was the macro's.
    let written = |answer: &answer::WindowAnswer| {
        one(
            "window.json",
            &serde_json::to_value(answer).expect("an answer is JSON"),
        )
    };
    if others.is_empty() {
        let (brought, merges) = message_window::reduction(&skin)?;
        return Ok(written(&answer::WindowAnswer {
            colors: message_window::colors(&skin)?,
            brought,
            merges: merges_of(&merges),
            system: game.system.system_name.clone(),
            text_rows: None,
            systems: Vec::new(),
        }));
    }
    // Each other System is the same game drawn with it, over its own
    // background or none: the starting one's does not carry over.
    let mut skins = Vec::new();
    for other in others {
        let mut drawn = place.game()?;
        drawn.system_file = None;
        drawn.use_system(&other.system);
        drawn.window_background = None;
        if let Some(background) = &other.background {
            drawn.use_window_background(background)?;
        }
        if let Some(stretch) = other.stretch {
            drawn.system.message_stretch = ditto::schema::SystemStretch::from_i32(stretch);
        }
        skins.push((other.system.clone(), drawn.skin()?));
    }
    let mut each = vec![message_window::text_rows(&skin)?];
    for (_, s) in &skins {
        each.push(message_window::text_rows(s)?);
    }
    let rows = message_window::common_rows(&each);
    // The starting System's entries are the cartridge's, and the others fit
    // in them: see `message_window::convert_with`.
    let colors = message_window::colors_with(&skin, Some(&rows))?;
    let mut systems = Vec::new();
    for (name, s) in &skins {
        let (brought, merges) = message_window::reduction_capped(s, Some(&rows), colors)?;
        let window = message_window::convert_with(s, colors + 1, Some(&rows))?;
        let gold = message_window::gold(s, &window, &game.font, &game.term("gold")?)?;
        systems.push(answer::SwitchedWindow {
            other: answer::OtherSystem {
                system: name.clone(),
                window: screens::window_answer(
                    &window,
                    &gold,
                    &message_window::inks(s, &window, &game.font),
                ),
            },
            brought,
            merges: merges_of(&merges),
            colors,
            frame_fused: window.frame_fused,
            mixed_text_rows: message_window::mixed_text_rows(s),
        });
    }
    let (brought, merges) = message_window::reduction_with(&skin, Some(&rows))?;
    Ok(written(&answer::WindowAnswer {
        colors,
        brought,
        merges: merges_of(&merges),
        system: game.system.system_name.clone(),
        text_rows: Some(rows),
        systems,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn small_game() -> Place {
        let here = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game");
        Place {
            data: here.join("dump"),
            game_dir: here.join("pictures"),
            ..Place::default()
        }
    }

    /// A process got its letters fresh; a thread that called `convert`
    /// before, or anything that carried some, would hand them to the next
    /// stage. After any stage the text screens write `é` as its plain `e`
    /// again, as on a thread that never carried it.
    #[test]
    fn no_stage_leaves_letters_for_the_next() {
        let place = small_game();
        let request = serde_json::json!({
            "font": "low-variable", "slots": 4, "actors": [1], "items": [1], "title": false,
            "cgram_reserved": 9, "screen_letters": ["é"],
            "vram": {"slot_vram": 0x2000, "slot_map": 0x3C00,
                     "bg1_banks": [["WINDOW", 0x1000, 0x5000]]},
        });
        // Read as the binary reads a test's file: what it leaves out takes
        // the request's defaults.
        let request: request::Convert = serde_json::from_value(request).unwrap();
        convert(&place, &request).unwrap();
        assert_eq!(texts::carried_letters(), Vec::<char>::new());
        assert_eq!(texts::item_text("é", 4), "e");

        let stages: [(&str, &dyn Fn() -> Result<Files>); 3] = [
            ("faces", &|| faces(&place, &request::Faces::default())),
            ("window", &|| window(&place, &request::Window::default())),
            ("boxes", &|| {
                let line = request::Line {
                    columns: 38,
                    ..request::Line::default()
                };
                boxes(
                    &place.data,
                    &request::Boxes {
                        line,
                        lines: 4,
                        ..Default::default()
                    },
                )
            }),
        ];
        for (name, stage) in stages {
            texts::carry_letters(&['é']);
            stage().unwrap();
            assert_eq!(texts::carried_letters(), Vec::<char>::new(), "{name}");
            assert_eq!(texts::item_text("é", 4), "e", "{name}");
        }
    }
}
