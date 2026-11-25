//! The screens, which are `rm2k-snes-screens`: what goes into its requests.
//!
//! **The screens are drawn by the stage** —the message window and its
//! font, the title's menu, the save slots and the pause menu, the text
//! screens with their windows, End Game—, which reads the game from the
//! dump itself and the System, the faces and the title from the game's
//! folder. What the converter tells it is what the cartridge decided and
//! the stage does not know: which actors, which items, how many slots,
//! where each layout puts BG1.

use crate::compiler::LINES;
use crate::fail::{Result, Stop};
use crate::font::FontChoice;
use crate::game::Game;
use crate::stage;
use crate::systems::Switched;
use rm2k_project::windows::color_text;
use rm2k_snes_mapdata::{cgram, vram};
use rm2k_snes_screens::answer::{Face, FacesAnswer, WindowAnswer, WindowMerge};
use rm2k_snes_screens::request;
use rm2k_snes_screens::stage::Place;
use serde_json::Value;
use std::collections::BTreeMap;
use std::ffi::OsString;

/// The screens' four stages; their `layout` is constants, a plain call.
const SCREENS_BOXES: stage::Stage = stage::Stage {
    binary: "rm2k-snes-screens",
    command: "boxes",
};
const SCREENS_FACES: stage::Stage = stage::Stage {
    binary: "rm2k-snes-screens",
    command: "faces",
};
const SCREENS_WINDOW: stage::Stage = stage::Stage {
    binary: "rm2k-snes-screens",
    command: "window",
};
const SCREENS_CONVERT: stage::Stage = stage::Stage {
    binary: "rm2k-snes-screens",
    command: "convert",
};

/// Where the game is and how its screens are drawn, twice from the same
/// values: as the flags the binary took, which the cache key reads, and as
/// the [`Place`] the stage is called with. Built once so the two cannot
/// say different things.
fn game_place(game: &Game) -> (Vec<OsString>, Place) {
    let mut flags: Vec<OsString> = vec![
        "--data".into(),
        game.dump.clone().into_os_string(),
        "--game-dir".into(),
        game.game_dir.clone().into_os_string(),
    ];
    let mut place = Place {
        data: game.dump.clone(),
        game_dir: game.game_dir.clone(),
        ..Place::default()
    };
    if let Some(rtp) = &game.rtp_dir {
        flags.extend(["--rtp-dir".into(), rtp.clone().into_os_string()]);
        place.rtp_dir = Some(rtp.clone());
    }
    if let Some(system) = &game.system {
        flags.extend(["--system".into(), system.into()]);
        place.system = Some(system.clone());
    }
    // The System the cartridge starts with: every screen is drawn with it,
    // and the message window of the others it switches to is asked for
    // apart —see `window_colors`—. A gradient goes as the one colour it is
    // drawn with until the runtime draws it.
    if let Some(background) = game.window_background(&game.starting_system()) {
        let background = color_text(background.flat());
        flags.extend(["--window-background".into(), background.clone().into()]);
        place.window_background = Some(background);
    }
    // And the box's ink, in a cartridge whose boxes type a colour: one entry
    // of the window's palette, in every screen that counts it.
    if game.text_ink {
        flags.push("--text-ink".into());
        place.text_ink = true;
    }
    (flags, place)
}

/// `request` as the stage's cache key reads it: the JSON the binary would
/// have been handed.
fn in_key(request: &impl serde::Serialize) -> Value {
    serde_json::to_value(request).expect("a request is JSON")
}

/// Every text box of the game the port rebuilds for the console's window,
/// with the boxes that go in its place: `[{"from": lines, "to": boxes}]`,
/// only those that change. The window's lines are `width` pixels of
/// `font`.
pub fn boxes(
    game: &Game,
    font: &FontChoice,
    width: usize,
    lines: u32,
) -> Result<Vec<rm2k_snes_screens::boxes::Reflowed>> {
    let font = font.request();
    let request = request::Boxes {
        map_files: game.forks.map_files(),
        line: request::Line {
            font: Some(font.font),
            letter_spacing: font.letter_spacing,
            exfont: font.exfont,
            width,
            ..request::Line::default()
        },
        lines: lines as usize,
    };
    let written = stage::call(
        SCREENS_BOXES,
        &in_key(&request),
        &["--data".into(), game.dump.clone().into_os_string()],
        || rm2k_snes_screens::stage::boxes(&game.dump, &request),
    )?;
    stage::typed(&written, "boxes.json")
}

/// The faces the message window shows —`(FaceSet, index, mirrored)`, the
/// compiler's `faces` in `OP_FACE`'s order—, each as the cartridge stores
/// it, and `missing` for one whose FaceSet is neither the game's nor the
/// RTP's, drawn as the window's background alone. See `faces.rs` in
/// `rm2k-snes-screens`. The stage draws with the game's System and the
/// project's window background, like every screen.
pub fn faces(game: &Game, faces: &[(String, i64, bool)]) -> Result<Vec<Face>> {
    if faces.is_empty() {
        return Ok(Vec::new());
    }
    let request = request::Faces {
        faces: faces
            .iter()
            .map(|(f, i, m)| (f.clone(), *i as i32, *m))
            .collect(),
    };
    let (flags, place) = game_place(game);
    let written = stage::call(SCREENS_FACES, &in_key(&request), &flags, || {
        rm2k_snes_screens::stage::faces(&place, &request)
    })?;
    let answer: FacesAnswer = stage::typed(&written, "faces.json")?;
    if answer.faces.len() != faces.len() {
        crate::stop!(
            "the screens drew {} faces and {} were asked for",
            answer.faces.len(),
            faces.len()
        );
    }
    Ok(answer.faces)
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
pub fn window_colors(game: &Game, switched: &[Switched]) -> Result<(u32, WindowAnswer)> {
    let request = request::Window {
        systems: crate::systems::window_request(game, switched),
    };
    let (flags, place) = game_place(game);
    let written = stage::call(SCREENS_WINDOW, &in_key(&request), &flags, || {
        rm2k_snes_screens::stage::window(&place, &request)
    })?;
    let answer: WindowAnswer = stage::typed(&written, "window.json")?;
    let colors = u32::try_from(answer.colors).map_err(|_| {
        Stop::new(format!(
            "the screens' window answer counts {} colours",
            answer.colors
        ))
    })?;
    Ok((colors, answer))
}

/// What the message window lost, for the patches: the starting System's
/// and each other one's, those whose colours did not fit in one palette.
pub fn window_losses(answer: &WindowAnswer) -> Vec<rm2k_snes_patches::WindowDecision> {
    let rgb = |c: &[u8; 3]| c.map(i64::from);
    let decision = |system: &str, brought: usize, kept: usize, merges: &[WindowMerge]| {
        rm2k_snes_patches::WindowDecision {
            system: system.to_string(),
            colors: brought as i64,
            kept: kept as i64,
            merges: merges
                .iter()
                .map(|(victim, target, pixels)| {
                    rm2k_snes_patches::Merge::Global((rgb(victim), rgb(target), *pixels as i64))
                })
                .collect(),
        }
    };
    let starting = decision(
        &answer.system,
        answer.brought,
        answer.colors,
        &answer.merges,
    );
    let others = answer
        .systems
        .iter()
        .map(|o| decision(&o.other.system, o.brought, o.colors, &o.merges));
    std::iter::once(starting)
        .chain(others)
        .filter(|w| !w.merges.is_empty())
        .collect()
}

/// What of the screens' request the converter decides with the events
/// compiled: the custom menus, their variables' slots and the bodies they
/// run, the names `ChangeHeroName` gives and whether the cartridge carries
/// the debug screen. See [`request::Convert`].
pub struct Menus {
    pub menus: Vec<request::Menu>,
    pub variables: Vec<(i32, usize)>,
    pub before_bodies: BTreeMap<i32, u8>,
    pub names: Vec<(i32, String)>,
    pub debug: bool,
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
    menus: Menus,
    window_colors: u32,
    text_rows: Option<&Vec<Vec<usize>>>,
    letters: &[String],
    screen_letters: &[char],
) -> Result<rm2k_snes_screens::answer::Answer> {
    let _ = LINES;
    let bg1_banks = vram::LAYOUTS
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
            (l.name.to_string(), l.tiles.base as usize, end as usize)
        })
        .collect();
    // The Latin-1 letters the message boxes draw, as the event compiler
    // numbered them: their glyphs go after the console's 96.
    let letters = letters
        .iter()
        .map(|l| {
            let mut chars = l.chars();
            match (chars.next(), chars.next()) {
                (Some(c), None) => Ok(c),
                _ => Err(Stop::new(format!(
                    "the event compiler's letter {l:?} is not one letter"
                ))),
            }
        })
        .collect::<Result<_>>()?;
    let request = request::Convert {
        font: font.request(),
        slots: vram::SLOTS as usize,
        actors: members.to_vec(),
        items: items.to_vec(),
        title,
        // The message window goes in the lowest palette, and the background
        // starts after it: see `cgram.rs` in `rm2k-snes-mapdata`.
        cgram_reserved: cgram::cgram_reserved(window_colors) as usize,
        letters,
        // And the ones the converter found in the texts the text screens
        // compose at run time: those go after them, and the screens write
        // both. See `letters.rs`.
        screen_letters: screen_letters.to_vec(),
        vram: rm2k_snes_screens::checks::Vram {
            slot_vram: vram::SLOT_VRAM as usize,
            slot_map: vram::SLOT_MAP as usize,
            // Each layout's BG1 bank, which is what `load_map` restores on
            // coming back from a screen: the screens have to fall inside.
            bg1_banks,
        },
        // The text's entries, the same in every System: only a cartridge
        // that switches has them.
        text_rows: text_rows.cloned(),
        menus: menus.menus,
        variables: menus.variables,
        before_bodies: menus.before_bodies,
        names: menus.names,
        debug: menus.debug,
    };
    let (flags, place) = game_place(game);
    let written = stage::call(SCREENS_CONVERT, &in_key(&request), &flags, || {
        rm2k_snes_screens::stage::convert(&place, &request)
    })?;
    stage::typed(&written, "screens.json")
}
