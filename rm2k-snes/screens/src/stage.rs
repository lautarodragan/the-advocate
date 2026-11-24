//! The screens as a stage of a converter: what each of the commands it
//! calls answers, as the files the binary writes into `--out`, by name. The
//! converter calls these as functions —`convert`, `boxes`, `faces`, `window`
//! and `layout`—, and the binary is a `main` over them that reads the
//! request and writes the files.
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

use crate::fail::{Bad, Result};
use crate::request::Json;
use crate::{boxes as box_table, convert as screens, faces as face_sets};
use crate::{layout as geometry, message_window, texts, Game};
use rm2k_snes_text::font::Font;
use rm2k_snes_text::refit::Measure;
use serde_json::Value;
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

/// `request` as the screens read a request, named for their messages:
/// the converter's has no file. Each command has a door that takes the
/// [`Json`] instead, `<command>_of`, which the binary goes through so its
/// complaints keep the request file's name.
fn json(request: &Value) -> Json {
    Json {
        data: request.clone(),
        whose: "the request".to_string(),
    }
}

/// `answer` as the file `name`, as every JSON of this crate is written:
/// on one line, with no newline after it.
fn one(name: &str, answer: &Value) -> Files {
    Files::from([(name.to_string(), answer.to_string().into_bytes())])
}

/// The game, drawing with the font the request names: `font`, which is the
/// project file's `[text] font` —`rm2k`, one the engine carries, or the
/// path of a sheet—, spaced by its `letter_spacing`, and with the icons of
/// the ExFont when the request names its sheet, `exfont`.
///
/// And with the Latin-1 letters the text screens write, `screen_letters`,
/// carried —see `texts::carry_letters`—: every text a screen writes keeps
/// them from here on, until the stage ends.
pub fn game_with_font(place: &Place, json: &Json) -> Result<Game> {
    let mut game = place.game()?;
    game.use_font(
        &json.text("font")?,
        json.number_or("letter_spacing", 0)?,
        json.exfont()?.as_deref(),
    )?;
    let letters = texts::screen_letters(
        &game,
        &json.letters("letters")?,
        &json.letters("screen_letters")?,
    )?;
    texts::carry_letters(&letters.screens);
    Ok(game)
}

/// `convert`: every screen a cartridge carries, as `screens.json`.
pub fn convert(place: &Place, request: &Value) -> Result<Files> {
    convert_of(place, &json(request))
}

/// [`convert`], asked a request already read.
pub fn convert_of(place: &Place, json: &Json) -> Result<Files> {
    let _fresh = Fresh::start();
    let game = game_with_font(place, json)?;
    let answer = screens::convert(&game, &json.convert()?)?;
    Ok(one("screens.json", &answer))
}

/// How a request's window measures a line: `font` —the project file's
/// `[text] font`, spaced by `letter_spacing`— and `width` in pixels; or
/// `advances`, each glyph's from the space on, and `width`, which is the
/// window the converter hands the event compiler, with its `letters`, the
/// Latin-1 the font draws, each with its advance; or, without either,
/// `columns` characters of RM2k's fixed-width font, which is how it was
/// asked until 2026-10-03.
pub fn measure_of(json: &Json) -> Result<Measure> {
    if json.data.get("advances").is_some_and(|f| !f.is_null()) {
        let mut advances: Vec<u8> = json
            .numbers("advances")?
            .into_iter()
            .map(|a| a as u8)
            .collect();
        let mut half = 0;
        for pair in json
            .data
            .get("letters")
            .and_then(|l| l.as_array())
            .into_iter()
            .flatten()
        {
            let letter = pair
                .get(0)
                .and_then(|l| l.as_str())
                .and_then(|l| l.chars().next());
            let advance = pair.get(1).and_then(|a| a.as_u64());
            let (Some(letter), Some(advance)) = (letter, advance) else {
                return Err(Bad::answer(format!(
                    "a window's `letters` are pairs of a letter and its advance: {pair}"
                )));
            };
            // An icon's half: they all move the line the same.
            if rm2k_snes_text::exfont::is_half(letter) {
                half = advance as u8;
                continue;
            }
            let at = (letter as u32).saturating_sub(32) as usize;
            if advances.len() <= at {
                advances.resize(at + 1, 0);
            }
            advances[at] = advance as u8;
        }
        return Ok(Measure::from_advances(advances, json.index_or("width", 0)?).with_icons(half));
    }
    if json.data.get("font").is_some_and(|f| !f.is_null()) {
        let spacing = json.number_or("letter_spacing", 0)?;
        let exfont = json.exfont()?;
        let font = Font::named(&json.text("font")?, rm2k_snes_text::font::MINCHO)
            .and_then(|f| f.with_spacing(spacing))
            .and_then(|f| f.with_exfont_of(exfont.as_deref()))
            .map_err(Bad::answer)?;
        Ok(Measure::new(&font, json.index_or("width", 0)?))
    } else {
        Ok(Measure::columns(json.index_or("columns", 0)?))
    }
}

/// `boxes`: every message box of the game in `data` reflowed for the
/// console's window, as `boxes.json`.
pub fn boxes(data: &Path, request: &Value) -> Result<Files> {
    boxes_of(data, &json(request))
}

/// [`boxes`], asked a request already read.
pub fn boxes_of(data: &Path, json: &Json) -> Result<Files> {
    let _fresh = Fresh::start();
    let table = box_table::table(
        data,
        &json.files("map_files")?,
        &measure_of(json)?,
        json.index_or("lines", 0)?,
    )?;
    Ok(one("boxes.json", &table))
}

/// `faces`: the faces the message window shows, as `faces.json`.
pub fn faces(place: &Place, request: &Value) -> Result<Files> {
    faces_of(place, &json(request))
}

/// [`faces`], asked a request already read.
pub fn faces_of(place: &Place, json: &Json) -> Result<Files> {
    let _fresh = Fresh::start();
    let game = place.game()?;
    let drawn = face_sets::draw(&game, &face_sets::requested(&json.data, &json.whose)?)?;
    Ok(one("faces.json", &face_sets::answer(&drawn)))
}

/// `window`: how many colour-memory entries the message window takes, as
/// `window.json`; with the request's `systems`, each one's window too.
pub fn window(place: &Place, request: &Value) -> Result<Files> {
    window_of(place, &json(request))
}

/// [`window`], asked a request already read.
pub fn window_of(place: &Place, json: &Json) -> Result<Files> {
    let _fresh = Fresh::start();
    let game = place.game()?;
    let skin = game.skin()?;
    let others = json.systems()?;
    let merges_json = |merges: &[adeleine::Merge]| -> Vec<Value> {
        merges
            .iter()
            .map(|m| serde_json::json!([m.victim, m.target, m.pixels]))
            .collect()
    };
    if others.is_empty() {
        let (brought, merges) = message_window::reduction(&skin)?;
        let answer = serde_json::json!({
            "colors": message_window::colors(&skin)?, "brought": brought, "merges": merges_json(&merges),
            "system": game.system.system_name,
        });
        return Ok(one("window.json", &answer));
    }
    // Each other System is the same game drawn with it, over its own
    // background or none: the starting one's does not carry over.
    let mut skins = Vec::new();
    for other in &others {
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
        systems.push(serde_json::json!({
            "system": name,
            "window": screens::window_json(&window, &gold, &message_window::inks(s, &window, &game.font)),
            "brought": brought,
            "merges": merges_json(&merges),
            "colors": colors,
            "frame_fused": window.frame_fused,
            "mixed_text_rows": message_window::mixed_text_rows(s),
        }));
    }
    let (brought, merges) = message_window::reduction_with(&skin, Some(&rows))?;
    let answer = serde_json::json!({
        "colors": colors, "brought": brought, "merges": merges_json(&merges),
        "system": game.system.system_name,
        "text_rows": rows,
        "systems": systems,
    });
    Ok(one("window.json", &answer))
}

/// `layout`: the geometry the screens are drawn with, by name, as
/// `layout.json`; constants, which no game changes.
pub fn layout() -> Files {
    one("layout.json", &geometry::publish())
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
        convert(&place, &request).unwrap();
        assert_eq!(texts::carried_letters(), Vec::<char>::new());
        assert_eq!(texts::item_text("é", 4), "e");

        let stages: [(&str, &dyn Fn() -> Result<Files>); 3] = [
            ("faces", &|| {
                faces(&place, &serde_json::json!({"faces": []}))
            }),
            ("window", &|| window(&place, &serde_json::json!({}))),
            ("boxes", &|| {
                boxes(&place.data, &serde_json::json!({"columns": 38, "lines": 4}))
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
