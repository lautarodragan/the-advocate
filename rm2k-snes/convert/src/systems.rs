//! The Systems a cartridge carries a message window for: the one it starts
//! with and every one a `ChangeSystemGraphics` of its pages switches to.
//!
//! The screens stage draws one window per System, all with the text at the
//! same palette entries so the font's composed tables are one; the event
//! compiler turns each command into its System's index in this list; and
//! the runtime swaps the window when the command runs. Only the message
//! window follows the change: see `change_system` in the event compiler.

use crate::game::{Command, Game, GameMap};
use rm2k_project::windows::color_text;
use rm2k_snes_events::codes::CHANGE_SYSTEM_GRAPHICS;
use serde_json::{json, Value};
use std::path::PathBuf;

/// A System the cartridge switches to.
#[derive(Debug, Clone)]
pub struct Switched {
    /// As the first command that names it writes it.
    pub name: String,
    /// The stretch that command asks for, its first parameter: the window
    /// is drawn once, so a second command asking for another is not heard.
    pub stretch: Option<i32>,
}

/// The Systems other than the starting one that the pages of `maps`, the
/// common events, the troops and the test pages `tests` switch to, in the
/// order of their names without regard to case —it is the index the
/// compiler emits—; whether any command names a System at all, the
/// starting one included; and what the conversion has to say about them: a
/// name the game and the RTP have no picture for is left out, and the page
/// that asks for it with it.
pub fn switched(game: &Game, maps: &[&GameMap], tests: &[Command]) -> (Vec<Switched>, bool, Vec<String>) {
    let starting = game.starting_system().to_lowercase();
    let mut all: Vec<&Command> = Vec::new();
    for map in maps {
        all.extend(map.all_commands());
    }
    all.extend(game.db.common_events.values().flatten());
    all.extend(game.db.troops.values().flat_map(|t| t.pages.iter().flatten()));
    all.extend(tests);
    let mut out: Vec<Switched> = Vec::new();
    let mut says = Vec::new();
    let rtp: Vec<PathBuf> = game.rtp_dir.iter().cloned().collect();
    let mut any = false;
    for c in all.into_iter().filter(|c| c.code == CHANGE_SYSTEM_GRAPHICS) {
        any = true;
        let lower = c.string.to_lowercase();
        if lower == starting || out.iter().any(|s| s.name.to_lowercase() == lower) {
            continue;
        }
        let found = crate::resources::find(&[&game.game_dir], "System", &c.string, &[".png", ".bmp"]).is_some()
            || crate::resources::find(&rtp, "System", &c.string, &[".png", ".bmp"]).is_some();
        if !found {
            let line = format!(
                "  WARNING, a ChangeSystemGraphics asks for System {:?}, which neither the game nor the RTP has: \
                 the page that asks for it is left out",
                c.string
            );
            if !says.contains(&line) {
                says.push(line);
            }
            continue;
        }
        out.push(Switched { name: c.string.clone(), stretch: c.parameters.first().copied() });
    }
    out.sort_by_key(|s| s.name.to_lowercase());
    (out, any, says)
}

/// Every System's name in the cartridge's order, the starting one first:
/// what the compiler numbers them by. Empty if no command names one, which
/// is how the request of a game that never switches stays as it was; the
/// starting one alone if every command names it, and then each is an
/// `OP_CHANGE_SYSTEM` to 0, which changes nothing.
pub fn names(game: &Game, switched: &[Switched], any: bool) -> Vec<String> {
    if !any {
        return Vec::new();
    }
    let mut out = vec![game.starting_system()];
    out.extend(switched.iter().map(|s| s.name.clone()));
    out
}

/// The `systems` the screens' `window` subcommand takes: each with the
/// project's `[windows.background]` for it, if any.
pub fn window_request(game: &Game, switched: &[Switched]) -> Value {
    Value::Array(
        switched
            .iter()
            .map(|s| {
                json!({
                    "system": s.name,
                    "background": game.window_background(&s.name).map(|b| color_text(b.flat())),
                    "stretch": s.stretch,
                })
            })
            .collect(),
    )
}
