//! The screens, which are `rm2k-snes-screens`: what goes into its requests.
//!
//! **The screens are drawn by the stage** —the message window and its
//! font, the title's menu, the save slots and the pause menu, the text
//! screens with their windows, End Game—, which reads the game from the
//! dump itself and the System, the faces and the title from the game's
//! folder. What the converter tells it is what the cartridge decided and
//! the stage does not know: which actors, which items, how many slots,
//! where each layout puts BG1.

use crate::compiler::{self, LINES};
use crate::fail::{Result, Stop};
use crate::font::FontChoice;
use crate::game::Game;
use crate::stage;
use crate::systems::Switched;
use rm2k_project::windows::color_text;
use rm2k_snes_mapdata::{cgram, vram};
use serde_json::{json, Value};
use std::ffi::OsString;

const BINARY: &str = "rm2k-snes-screens";
const PROJECT: &str = "screens";

fn game_flags(game: &Game) -> Vec<OsString> {
    let mut flags: Vec<OsString> = vec![
        "--data".into(),
        game.dump.clone().into_os_string(),
        "--game-dir".into(),
        game.game_dir.clone().into_os_string(),
    ];
    if let Some(rtp) = &game.rtp_dir {
        flags.extend(["--rtp-dir".into(), rtp.clone().into_os_string()]);
    }
    if let Some(system) = &game.system {
        flags.extend(["--system".into(), system.into()]);
    }
    // The System the cartridge starts with: every screen is drawn with it,
    // and the message window of the others it switches to is asked for
    // apart —see `window_colors`—. A gradient goes as the one colour it is
    // drawn with until the runtime draws it.
    if let Some(background) = game.window_background(&game.starting_system()) {
        flags.extend([
            "--window-background".into(),
            color_text(background.flat()).into(),
        ]);
    }
    // And the box's ink, in a cartridge whose boxes type a colour: one entry
    // of the window's palette, in every screen that counts it.
    if game.text_ink {
        flags.push("--text-ink".into());
    }
    flags
}

/// Every text box of the game the port rebuilds for the console's window,
/// with the boxes that go in its place: `[{"from": lines, "to": boxes}]`,
/// only those that change. The window's lines are `width` pixels of
/// `font`.
pub fn boxes(game: &Game, font: &FontChoice, width: usize, lines: u32) -> Result<Value> {
    let request = json!({
        "map_files": compiler::map_files(game),
        "font": font.spec,
        "letter_spacing": font.spacing,
        "width": width,
        "lines": lines,
    });
    let written = stage::run(
        BINARY,
        PROJECT,
        "boxes",
        &request,
        &["--data".into(), game.dump.clone().into_os_string()],
    )?;
    stage::json(&written, "boxes.json")
}

/// The faces the message window shows —`(FaceSet, index, mirrored)`, the
/// compiler's `faces` in `OP_FACE`'s order—, each as the cartridge stores
/// it, `{"tiles": hex, "palette": words, "missing": bool}`: `missing` is
/// one whose FaceSet is neither the game's nor the RTP's, drawn as the
/// window's background alone. See `faces.rs` in `rm2k-snes-screens`. The
/// stage draws with the game's System and the project's window background,
/// like every screen.
pub fn faces(game: &Game, faces: &[(String, i64, bool)]) -> Result<Vec<Value>> {
    if faces.is_empty() {
        return Ok(Vec::new());
    }
    let request =
        json!({"faces": faces.iter().map(|(f, i, m)| json!([f, i, m])).collect::<Vec<_>>()});
    let written = stage::run(BINARY, PROJECT, "faces", &request, &game_flags(game))?;
    let answer = stage::json(&written, "faces.json")?;
    answer["faces"]
        .as_array()
        .cloned()
        .filter(|drawn| drawn.len() == faces.len())
        .ok_or_else(|| {
            Stop::new(format!(
                "the screens drew {} faces and {} were asked for",
                answer["faces"].as_array().map_or(0, Vec::len),
                faces.len()
            ))
        })
}

/// The colour-memory entries the message window takes after the backdrop,
/// counted from the game's System. **The only place they come from**: the
/// screens get them as `cgram_reserved`, each map's `wally` and the
/// emission as `window_colors`, and the background of every map starts
/// after them.
///
/// And the whole answer with it: a System with more colours than a palette
/// holds comes back reduced, and what it lost —`system`, `brought` and
/// `merges`— goes to the game's patches.
///
/// With the Systems the cartridge switches to, `switched`, the count is the
/// most any of them takes, the text takes the same entries in all of them
/// —`text_rows`, which [`convert`] takes back— and each one's window comes
/// in `systems`.
pub fn window_colors(game: &Game, switched: &[Switched]) -> Result<(u32, Value)> {
    let request = if switched.is_empty() {
        json!({})
    } else {
        json!({"systems": crate::systems::window_request(game, switched)})
    };
    let written = stage::run(BINARY, PROJECT, "window", &request, &game_flags(game))?;
    let answer = stage::json(&written, "window.json")?;
    let colors = answer["colors"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or_else(|| {
            Stop::new(format!(
                "the screens' window answer has no colour count: {answer}"
            ))
        })?;
    Ok((colors, answer))
}

/// The geometry the screens are drawn with, by the names the emission
/// writes it with.
pub fn layout() -> Result<Value> {
    let written = stage::run(BINARY, PROJECT, "layout", &json!({}), &[])?;
    stage::json(&written, "layout.json")
}

/// How many pixels a line of the message window takes: the screens'.
pub fn message_width() -> Result<usize> {
    let layout = layout()?;
    layout["MESSAGE_WIDTH"]
        .as_u64()
        .map(|w| w as usize)
        .ok_or_else(|| Stop::new("the screens' layout has no MESSAGE_WIDTH"))
}

/// What the cartridge carries of its screens, for `members` —the actors
/// that can join the party— and `items` —the ones the cartridge knows—,
/// with the title's menu if `title`. Returns the stage's answer as it came,
/// which is what `rm2k-snes-mapdata emit` takes.
pub fn convert(
    game: &Game,
    font: &FontChoice,
    members: &[i32],
    items: &[i32],
    title: bool,
    menus: &Value,
    window_colors: u32,
    text_rows: &Value,
    letters: &Value,
) -> Result<Value> {
    let _ = LINES;
    let bg1_banks: Vec<Value> = vram::LAYOUTS
        .iter()
        .map(|l| {
            let mut end =
                l.tiles.base + l.tiles.count * (rm2k_snes_mapdata::snes::BYTES_PER_TILE as u32 / 2);
            // A panorama's tiles right after BG1's come back with them: the
            // same `load_above` that the return to the map goes through
            // uploads them —see `pano_load` in the runtime—.
            if let Some(p) = &l.panorama {
                for t in p.tiles.iter().filter(|t| t.count > 0) {
                    if t.base == end {
                        end = t.base + t.count * p.tile_words();
                    }
                }
            }
            json!([l.name, l.tiles.base, end])
        })
        .collect();
    let mut request = json!({
        "font": font.spec,
        "letter_spacing": font.spacing,
        "slots": vram::SLOTS,
        "actors": members,
        "items": items,
        "title": title,
        // The message window goes in the lowest palette, and the background
        // starts after it: see `cgram.rs` in `rm2k-snes-mapdata`.
        "cgram_reserved": cgram::cgram_reserved(window_colors),
        // The Latin-1 letters the message boxes draw, as the event compiler
        // numbered them: their glyphs go after the console's 96.
        "letters": letters,
        "vram": {
            "slot_vram": vram::SLOT_VRAM,
            "slot_map": vram::SLOT_MAP,
            // Each layout's BG1 bank, which is what `load_map` restores on
            // coming back from a screen: the screens have to fall inside.
            "bg1_banks": bg1_banks,
        },
    });
    // The text's entries, the same in every System: only a cartridge that
    // switches has them, and the request of one that does not stays as it
    // was.
    if !text_rows.is_null() {
        request["text_rows"] = text_rows.clone();
    }
    // The custom menus, their variables' slots and the bodies they run; and
    // the names `ChangeHeroName` gives, which ride along in the same value.
    for key in ["menus", "variables", "before_bodies", "names"] {
        request[key] = menus[key].clone();
    }
    // And the debug screen, only when the cartridge carries it: a request
    // without it stays as it was.
    if menus["debug"].as_bool() == Some(true) {
        request["debug"] = json!(true);
    }
    let written = stage::run(BINARY, PROJECT, "convert", &request, &game_flags(game))?;
    stage::json(&written, "screens.json")
}
