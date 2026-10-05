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
use rm2k_snes_mapdata::{cgram, vram};
use serde_json::{json, Value};
use std::ffi::OsString;

const BINARY: &str = "rm2k-snes-screens";
const PROJECT: &str = "screens";

fn game_flags(game: &Game) -> Vec<OsString> {
    vec![
        "--data".into(),
        game.dump.clone().into_os_string(),
        "--game-dir".into(),
        game.game_dir.clone().into_os_string(),
    ]
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

/// The colour-memory entries the message window takes after the backdrop,
/// counted from the game's System. **The only place they come from**: the
/// screens get them as `cgram_reserved`, each map's `wally` and the
/// emission as `window_colors`, and the background of every map starts
/// after them.
pub fn window_colors(game: &Game) -> Result<u32> {
    let written = stage::run(BINARY, PROJECT, "window", &json!({}), &game_flags(game))?;
    let answer = stage::json(&written, "window.json")?;
    answer["colors"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or_else(|| Stop::new(format!("the screens' window answer has no colour count: {answer}")))
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
) -> Result<Value> {
    let _ = LINES;
    let bg1_banks: Vec<Value> = vram::LAYOUTS
        .iter()
        .map(|l| {
            json!([
                l.name,
                l.tiles.base,
                l.tiles.base + l.tiles.count * (rm2k_snes_mapdata::snes::BYTES_PER_TILE as u32 / 2)
            ])
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
        "vram": {
            "slot_vram": vram::SLOT_VRAM,
            "slot_map": vram::SLOT_MAP,
            // Each layout's BG1 bank, which is what `load_map` restores on
            // coming back from a screen: the screens have to fall inside.
            "bg1_banks": bg1_banks,
        },
    });
    // The custom menus, their variables' slots and the bodies they run.
    for key in ["menus", "variables", "before_bodies"] {
        request[key] = menus[key].clone();
    }
    let written = stage::run(BINARY, PROJECT, "convert", &request, &game_flags(game))?;
    stage::json(&written, "screens.json")
}
