//! The battle animations drawn over the map: which ones the cartridge
//! carries, the box the ROM draws them in, and their frames as they end up
//! in VRAM.
//!
//! **The drawing is `rm2k-snes-images animations`'**: RM2k's part —which
//! cells each frame has, cut from the sheet, zoomed, faded, and where they
//! go in the animation's box— and the port's after it: toning each cell
//! with the console's tint, stacking them, shrinking the whole into the box
//! and bringing its colours down. What is here is which animations, the
//! box, and their bytes.
//!
//! The budget, which is where the box comes from: a 32x32 object reads
//! four tiles from four consecutive rows of the name grid, so **a row of
//! blocks is 64 tiles and four objects**, which in two by two are 64x64
//! pixels. That box is **the same for the whole ROM**: the box not
//! depending on the map is what lets every map share the frames already
//! converted in the cartridge. The animation is shrunk whole until it fits
//! in it, keeping its proportions. What is lost is declared in
//! `divergences/the-shrunk-battle-animation.md` in the book.

use crate::bytecode;
use crate::fail::Result;
use crate::game::{Command, Game};
use crate::images;
use rm2k_snes_events::codes::SHOW_BATTLE_ANIMATION;
use rm2k_snes_bytecode::events::OP_ANIMATION;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// The box, and the 32x32 objects it is drawn with. Measured against A
/// Blurred Line: an assumption of the engine, not a fact of the game.
pub const BOX: i64 = 64;
pub const OBJ: i64 = 32;
pub const OBJ_SIDE: i64 = OBJ / 8;
/// Tiles per row of the OAM name grid.
pub const GRID: i64 = 16;
pub const OBJECTS: i64 = (BOX / OBJ) * (BOX / OBJ);
/// One row of blocks: the four objects.
pub const TILES: i64 = 4 * GRID;
pub const COLORS: i64 = 15;
/// `character_height` of `BattleAnimationMap::DrawSingle`.
pub const CHARACTER_HEIGHT: i64 = 24;
pub const SCREEN: (i64, i64) = (256, 224);
/// `Animation::Position`, which shifts the animation from the target.
pub const POS_TOP: i32 = 0;
pub const POS_BOTTOM: i32 = 2;
/// `Animation::Scope_screen`.
pub const SCOPE_SCREEN: i32 = 1;
/// The alpha from which a pixel is drawn: half, rounding up.
pub const ALPHA_MIN: i64 = 128;

/// An animation converted.
#[derive(Debug, Clone)]
pub struct Info {
    /// Its frames: each a 64x64 grid of palette indices.
    pub frames: Vec<Value>,
    pub palette: Vec<Value>,
    pub anchor: (i64, i64),
    pub size: (i64, i64),
    pub rm_box: (i64, i64),
    pub scope: i32,
    pub position: i32,
}

/// The animations converted so far, by number: None for one with nothing
/// to draw.
pub struct Animations {
    cache: BTreeMap<i32, Option<Info>>,
    search_dirs: Vec<PathBuf>,
    dump: PathBuf,
}

fn pair(v: &Value) -> (i64, i64) {
    (v[0].as_i64().unwrap_or(0), v[1].as_i64().unwrap_or(0))
}

impl Animations {
    pub fn new(search_dirs: &[PathBuf], dump: &Path) -> Animations {
        Animations { cache: BTreeMap::new(), search_dirs: search_dirs.to_vec(), dump: dump.to_path_buf() }
    }

    /// The path of an animation's `Battle` sheet, or None if it has none or
    /// it is not there.
    fn sheet_file(&self, anim: &crate::game::Animation) -> Option<PathBuf> {
        if anim.sheet.is_empty() {
            return None;
        }
        let folder = if anim.large { "Battle2" } else { "Battle" };
        crate::resources::find(&self.search_dirs, folder, &anim.sheet, &[".png", ".bmp"])
    }

    /// The animations `numbers` converted. The ones not converted yet are
    /// converted with a single call to the stage.
    pub fn by_numbers(&mut self, game: &Game, numbers: &[i32]) -> Result<BTreeMap<i32, Option<Info>>> {
        let new: BTreeSet<i32> = numbers.iter().copied().filter(|n| !self.cache.contains_key(n)).collect();
        let mut wanted = Vec::new();
        for number in new {
            let anim = game.db.animations.get(&number);
            match anim.and_then(|a| self.sheet_file(a).map(|s| (a, s))) {
                None => {
                    self.cache.insert(number, None);
                }
                Some((anim, sheet)) => wanted.push((number, anim.clone(), sheet)),
            }
        }
        let answers = images::animations(
            BOX,
            COLORS,
            ALPHA_MIN,
            &wanted.iter().map(|(n, _, s)| (*n, s.clone())).collect::<Vec<_>>(),
            &self.dump,
        )?;
        for ((number, anim, _), a) in wanted.into_iter().zip(answers) {
            let info = (!a.is_null()).then(|| Info {
                frames: a["frames"].as_array().cloned().unwrap_or_default(),
                palette: a["palette"].as_array().cloned().unwrap_or_default(),
                anchor: pair(&a["anchor"]),
                size: pair(&a["size"]),
                rm_box: pair(&a["rm_box"]),
                scope: anim.scope,
                position: anim.position,
            });
            self.cache.insert(number, info);
        }
        Ok(numbers.iter().map(|n| (*n, self.cache[n].clone())).collect())
    }

    /// Whether some page of a map can draw a battle animation. It is
    /// looked at on the raw commands and not on the compiled bytecode, and
    /// on purpose: the VRAM has to be reserved when converting the map and
    /// the pages are compiled afterwards. A superset: a page that in the
    /// end does not compile leaves the box reserved and unused, and it has
    /// to be so, because a bytecode that showed an animation the map did
    /// not reserve would write over a character's tiles. `commands` are the
    /// test pages' that run there.
    pub fn map_shows_animation<'a>(
        &mut self,
        game: &Game,
        map_commands: impl Iterator<Item = &'a Command>,
        commands: &'a [Command],
    ) -> Result<bool> {
        let mut numbers = BTreeSet::new();
        for cmd in commands.iter().chain(map_commands) {
            if cmd.code == SHOW_BATTLE_ANIMATION && cmd.parameters.len() >= 3 {
                numbers.insert(cmd.parameters[0]);
            }
        }
        let numbers: Vec<i32> = numbers.into_iter().collect();
        Ok(self.by_numbers(game, &numbers)?.values().any(Option::is_some))
    }
}

/// The battle animations the already emitted bytecode shows: their numbers.
/// The bytecode is walked and not the commands, which makes it the truth
/// and not a guess: what counts is what ended up emitted.
pub fn shown<'a>(codes: impl IntoIterator<Item = &'a [u8]>) -> Result<BTreeSet<i32>> {
    let no_drawing = rm2k_snes_mapdata::engine::ANIM_NO_DRAWING as u8;
    let mut numbers = BTreeSet::new();
    for code in codes {
        for i in bytecode::walk(code)? {
            if code[i] == OP_ANIMATION && bytecode::at(code, i + 1) != no_drawing {
                numbers.insert(bytecode::at(code, i + 1) as i32);
            }
        }
    }
    Ok(numbers)
}

/// The anchor as the ROM's table carries it: the vertical shift of
/// `Animation::Position` is baked into it, since it is fixed per animation.
/// With "screen" scope there is no shift: `DrawSingle` draws at the centre
/// without asking the target anything.
pub fn rom_anchor(info: &Info) -> (i64, i64) {
    let (ax, ay) = info.anchor;
    if info.scope == SCOPE_SCREEN {
        return (ax, ay);
    }
    let run = match info.position {
        POS_TOP => -(CHARACTER_HEIGHT / 2),
        POS_BOTTOM => CHARACTER_HEIGHT / 2,
        _ => 0,
    };
    (ax, ay + CHARACTER_HEIGHT / 2 - run)
}

/// A frame as it ends up in VRAM: the box's 64 4bpp tiles, in the order
/// OAM numbers them. The four objects fit in one row of blocks and object
/// `o` starts at `o * 4`; inside it, tile (tx, ty) is `ty` grid rows
/// further on. On screen the objects go two by two.
pub fn frame_bytes(frame: &Value) -> Vec<u8> {
    let mut data = vec![0u8; (TILES * 32) as usize];
    let pixel = |x: i64, y: i64| frame[y as usize][x as usize].as_u64().unwrap_or(0) as u8;
    for o in 0..OBJECTS {
        let start = (o % 4) * OBJ_SIDE;
        let (base_x, base_y) = ((o % 2) * OBJ, (o / 2) * OBJ);
        for ty in 0..OBJ_SIDE {
            for tx in 0..OBJ_SIDE {
                let cell: Vec<Vec<u8>> = (0..8)
                    .map(|py| (0..8).map(|px| pixel(base_x + tx * 8 + px, base_y + ty * 8 + py)).collect())
                    .collect();
                let tile = (start + ty * GRID + tx) as usize;
                data[tile * 32..(tile + 1) * 32]
                    .copy_from_slice(&rm2k_snes_mapdata::snes::pack_tile(&cell, 4));
            }
        }
    }
    data
}

/// The numbers that justify the layout, for the log and the patches.
pub struct Report {
    pub frames: usize,
    pub original: (i64, i64),
    pub size: (i64, i64),
    pub percent: i64,
    pub colors: usize,
    pub bytes: usize,
}

pub fn report(info: &Info) -> Report {
    Report {
        frames: info.frames.len(),
        original: info.rm_box,
        size: info.size,
        percent: (100 * info.size.0).div_euclid(info.rm_box.0),
        colors: info.palette.len(),
        bytes: info.frames.len() * (TILES * 32) as usize,
    }
}

/// The cartridge's battle animations as `rm2k-snes-mapdata emit` takes
/// them: the box, and per animation its frames as they end up in VRAM, its
/// anchor as the console's table carries it and its colours.
pub fn request(animations: &BTreeMap<i32, Info>) -> Value {
    json!({
        "box": BOX, "obj": OBJ, "objects": OBJECTS, "tiles": TILES,
        "screen": [SCREEN.0, SCREEN.1],
        "list": animations.iter().map(|(number, info)| {
            let (ax, ay) = rom_anchor(info);
            json!({
                "number": number,
                "frames": info.frames.iter().map(|f| crate::text::hex(&frame_bytes(f))).collect::<Vec<_>>(),
                "anchor": [ax, ay],
                "palette": info.palette,
            })
        }).collect::<Vec<_>>(),
    })
}
