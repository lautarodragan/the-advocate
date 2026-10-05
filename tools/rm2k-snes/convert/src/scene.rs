//! The battle scene: the backdrop and the monsters, composited on the
//! console. The cartridge carries **each backdrop once and each battler
//! once**, and the console composites them when the battle starts —see
//! `scene_upload` in the runtime's `battle_scene.s`—. Here is which ones
//! the cartridge carries, who asks for each, and their bytes; how a
//! backdrop or a battler is drawn and brought down is
//! `rm2k-snes-images`'; how the scene is written for the ROM,
//! `rm2k-snes-mapdata`'s `scene.rs`.
//!
//! ## The geometry
//!
//! RM2k's battle backdrop is 320x160 at the top of a 320x240 screen. The
//! console's screen is 256x224, so the backdrop goes in scaled to **80%**:
//! 256x128, the top seven text lines. The battlers go at the same 80%, so
//! the troop positions —the centre of each battler, in 320x240— map by
//! multiplying by the same. What is not RM2k's is **the clipping**: a tall
//! battler goes past the scene's 128 pixels, so its corner is clamped
//! inside.
//!
//! ## The budget
//!
//! * **512 tiles at 8bpp**, the whole 32x16 grid without deduplicating: a
//!   photo does not repeat.
//! * **The colours**: the backdrop carries 96, CGRAM entries 32 to 127, and
//!   each battler **fifteen plus transparent**, in the top eight palettes:
//!   the troop's first distinct battler on palette 8, and so on. That they
//!   are fifteen is an artistic decision, written per battler in the
//!   project's automatic patches.
//!
//! ## Which backdrops there are, and which ones the cartridge carries
//!
//! **The game's backdrops** are all the ones a battle can ask for —those
//! named by the `EnemyEncounter`s and the `ChangeBattleBG`s, those of the
//! map tree and those of the terrains—, each with a **number**, its place in
//! that list sorted by name: a fixed place in the `.msu`, which carries
//! **all** of them in quality. **The ROM carries, in the light fallback,
//! all the ones the cartridge's battles can ask for**: sixteen colours at
//! half resolution, 128x64 at 4bpp, which the ROM doubles. **The
//! replacement** is left for what the ROM cannot know at conversion time: a
//! troop that fights with the "local" backdrop on a map without random
//! encounters, where any terrain of the map is possible. The flat backdrop
//! —zeros, black— is for the battle that has none.

use crate::bytecode;
use crate::fail::{Result, Stop};
use crate::game::{Command, Database, Game};
use crate::images;
use crate::maps::MapInfo;
use crate::resources;
use crate::settings::Settings;
use crate::text::{hex, repr};
use rm2k_snes_events::codes::{CHANGE_BATTLE_BG, ENEMY_ENCOUNTER};
use rm2k_snes_bytecode::events::{OP_ANIMATION, OP_BATTLE};
use rm2k_snes_mapdata::snes::{cgram_word, pack_tile};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// The scene, in screen pixels: the top seven text lines.
pub const WIDTH: i64 = 256;
pub const HEIGHT: i64 = 128;
/// RM2k's backdrop is 320 wide: 256/320 is the 80%.
pub const SCALE_NUM: i64 = WIDTH;
pub const SCALE_DEN: i64 = 320;
/// The backdrop's colours, and from which CGRAM entry they go.
pub const COLORS: i64 = 96;
pub const CGRAM_BASE: i64 = 32;
/// The light fallback: sixteen colours, at 4bpp, at half resolution.
/// `CGRAM_BASE` has to start a palette of sixteen so planes 4 to 7 are the
/// same on all its pixels.
pub const FALLBACK_COLORS: i64 = 16;
pub const FALLBACK_PLANES: usize = 4;
pub const FALLBACK_SCALE: i64 = 2;
pub const FALLBACK_WIDTH: i64 = WIDTH / FALLBACK_SCALE;
pub const FALLBACK_HEIGHT: i64 = HEIGHT / FALLBACK_SCALE;
/// The battlers' first palette, and how many colours each has.
pub const BATTLER_PALETTE: i64 = 8;
pub const BATTLER_COLORS: i64 = 15;
/// The alpha from which a pixel of a shrunk battler is its: half.
pub const ALPHA_MIN: i64 = 128;
pub const CELL: i64 = 8;
pub const TILES_X: i64 = WIDTH / CELL;
pub const TILES_Y: i64 = HEIGHT / CELL;
pub const TILES: i64 = TILES_X * TILES_Y;
/// Where it lives in VRAM, in words.
pub const VRAM_MAP: i64 = 0x3800;
pub const VRAM_TILES: i64 = 0x4000;
/// Where the battle's text pairs end: from there to the scene's tilemap go
/// the windows' tiles —see `battle.rs` in `rm2k-snes-screens`—.
pub const TEXT_PAIRS_END: i64 = 0x2000;
/// How many planes the cartridge stores per row of a battler: the mask
/// and the four of its drawing. The ROM sets the other four by palette.
pub const BATTLER_PLANES: usize = 5;

/// What goes in the backdrop tables instead of a number: the flat one, and
/// "the one of the place", which the ROM resolves with the map and the
/// terrain when the battle starts.
pub const FLAT_BACKDROP: i64 = 0xFF;
pub const PLACE_BACKDROP: i64 = 0xFE;

/// `EnemyEncounter`'s third parameter: where the backdrop comes from.
const BACKDROP_OF_PLACE: i32 = 0;
const BACKDROP_OF_COMMAND: i32 = 1;

/// The sizes the stage draws with.
pub fn scene_settings() -> Value {
    json!({"width": WIDTH, "height": HEIGHT, "colors": COLORS, "cgram_base": CGRAM_BASE,
           "light_scale": FALLBACK_SCALE, "light_colors": FALLBACK_COLORS,
           "scale": [SCALE_NUM, SCALE_DEN], "battler_colors": BATTLER_COLORS, "alpha_min": ALPHA_MIN})
}

/// An RM2k length in scene pixels.
pub fn scale(value: i64) -> i64 {
    std::cmp::max(1, (value * SCALE_NUM + SCALE_DEN / 2).div_euclid(SCALE_DEN))
}

/// The file of a backdrop or a battler: the game's, or else the RTP's, as
/// RM2k looks it up; None if neither has it.
///
/// Until 2026-10-05 the battlers did not look in the RTP —it was left for
/// later "so as not to change which ones get in without looking at it"—, and
/// an enemy whose picture is the RTP's (its `Troll`, its `Hog`) went into
/// the battle with no picture at all, without a word in the log.
fn find_file(game: &Game, rtp: &Path, folder: &str, name: &str) -> Option<PathBuf> {
    let places = [game.game_dir.clone(), rtp.to_path_buf()];
    resources::find(&places, folder, name, &[".png", ".bmp", ".xyz"]).map(rm2k_project::absolute)
}

/// The battle backdrop of an `EnemyEncounter`: the name it carries, the
/// place's (None), or "" if none.
fn encounter_backdrop(cmd: &Command) -> Option<Option<String>> {
    let p = &cmd.parameters;
    match p.get(2) {
        Some(&BACKDROP_OF_COMMAND) => Some(Some(cmd.string.clone())),
        Some(&BACKDROP_OF_PLACE) => Some(None),
        _ => Some(Some(String::new())),
    }
}

fn command_backdrops<'a>(commands: impl IntoIterator<Item = &'a Command>, names: &mut BTreeSet<String>) {
    for cmd in commands {
        if cmd.code == ENEMY_ENCOUNTER {
            if let Some(Some(name)) = encounter_backdrop(cmd) {
                if !name.is_empty() {
                    names.insert(name);
                }
            }
        } else if cmd.code == CHANGE_BATTLE_BG && !cmd.string.is_empty() {
            names.insert(cmd.string.clone());
        }
    }
}

/// The battle backdrops some command of the game names: the
/// `EnemyEncounter`s and `ChangeBattleBG`s of every map of the game, of the
/// common events and of the troops' pages, whether they compile or not.
pub fn named_backdrops(game: &Game) -> Result<BTreeSet<String>> {
    let ids = game.game_map_ids()?;
    let found: Vec<Result<BTreeSet<String>>> = std::thread::scope(|scope| {
        let workers = std::thread::available_parallelism().map_or(1, |n| n.get()).min(ids.len()).max(1);
        let handles: Vec<_> = (0..workers)
            .map(|w| {
                let ids = &ids;
                scope.spawn(move || {
                    let mut names = BTreeSet::new();
                    for id in ids.iter().skip(w).step_by(workers) {
                        let map = game.map(*id)?;
                        command_backdrops(map.all_commands(), &mut names);
                    }
                    Ok(names)
                })
            })
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });
    let mut names = BTreeSet::new();
    for part in found {
        names.extend(part?);
    }
    for commands in game.db.common_events.values() {
        command_backdrops(commands, &mut names);
    }
    for troop in game.db.troops.values() {
        for page in &troop.pages {
            command_backdrops(page, &mut names);
        }
    }
    Ok(names)
}

/// The game's backdrops, in the order that gives them their number: sorted
/// by name ignoring case, which is how RM2k looks them up, each named as
/// the game writes it the first time. A name that is neither in the game
/// nor in the RTP is left out: in RM2k that battle has no backdrop.
pub fn game_backdrops(game: &Game, rtp: &Path, named: &BTreeSet<String>) -> Vec<String> {
    let mut every: BTreeSet<String> = named.clone();
    every.extend(game.tree.named_backgrounds());
    every.extend(game.db.terrain_backdrops.values().filter(|n| !n.is_empty()).cloned());
    let mut by_key: BTreeMap<String, String> = BTreeMap::new();
    for name in &every {
        by_key.entry(name.to_lowercase()).or_insert_with(|| name.clone());
    }
    let mut out = Vec::new();
    for name in by_key.values() {
        if resources::find(&[&game.game_dir, &rtp.to_path_buf()], "Backdrop", name, &[".png", ".bmp", ".xyz"]).is_none() {
            println!("  backdrop {} is neither in the game nor in the RTP", repr(name));
            continue;
        }
        out.push(name.clone());
    }
    out
}

/// A battler, as the stage answered it.
#[derive(Debug, Clone)]
pub struct Battler {
    pub key: String,
    pub image: String,
    pub hue: i64,
    pub width: i64,
    pub height: i64,
    pub pixels: Vec<Vec<i64>>,
    pub rm_height: i64,
    pub palette: Value,
    pub colors: i64,
    pub merges: usize,
}

/// What a battler is called in the cartridge and in the patches: the image
/// and its hue, which is what makes it different from another with the
/// same image.
pub fn key(name: &str, hue: i64) -> String {
    if hue != 0 {
        format!("{name}-{hue}")
    } else {
        name.to_string()
    }
}

/// How many bytes a row of a plane is: eight pixels per byte.
pub fn columns(b: &Battler) -> i64 {
    (b.width + 7) / 8
}

/// A battler in the format `scene_set` reads: **plane by plane**, the mask
/// first and then the four planes of the drawing, and within each plane
/// row by row, each row **backwards** with a zero in front —`[0] [col n-1]
/// ... [col 0]`—, so a sixteen-bit read at column `k` brings `k` and
/// `k - 1`, the word to shift for a battler that does not fall on a tile
/// boundary; and a zero at the very end for the same reason.
pub fn battler_bytes(b: &Battler) -> Vec<u8> {
    let n = columns(b) as usize;
    let mut out = Vec::new();
    for plane in 0..BATTLER_PLANES {
        for row in &b.pixels {
            let mut bytes = vec![0u8; n];
            for (x, &value) in row.iter().enumerate() {
                let lit = if plane == 0 { value != 0 } else { (value >> (plane - 1)) & 1 != 0 };
                if lit {
                    bytes[x / 8] |= 0x80 >> (x % 8);
                }
            }
            out.push(0);
            out.extend(bytes.iter().rev());
        }
    }
    out.push(0);
    out
}

/// Where a battler's corner lands in the scene, already clamped inside:
/// the troop's position is its centre, on RM2k's 320x240 screen.
pub fn position(center: (i32, i32), b: &Battler) -> (i64, i64) {
    let (x, y) = (center.0 as i64, center.1 as i64);
    let px = (scale(x) - b.width.div_euclid(2)).max(0).min((WIDTH - b.width).max(0));
    let py = (scale(y) - b.height.div_euclid(2)).max(0).min((HEIGHT - b.height).max(0));
    (px, py)
}

/// The order a troop's enemies are placed in, the later covering:
/// `Sprite_Battler::ResetZ` —the battler's bottom edge in RM2k, and on an
/// equal edge the one with the lower place in the troop on top—.
pub fn drawing_order(centers: &[(i32, i32)], infos: &[Option<&Battler>]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..centers.len()).collect();
    order.sort_by_key(|&k| {
        let height = infos[k].map_or(0, |b| b.rm_height);
        (centers[k].1 as i64 + height.div_euclid(2), -(k as i64))
    });
    order
}

/// The 8x8 tiles of a grid, in the order the tilemap reads them: row by
/// row, without deduplicating.
fn tiles(indices: &Value) -> Vec<Vec<Vec<u8>>> {
    let rows: Vec<Vec<i64>> = indices
        .as_array()
        .map(|r| {
            r.iter()
                .map(|row| row.as_array().map(|row| row.iter().map(|v| v.as_i64().unwrap_or(0)).collect()).unwrap_or_default())
                .collect()
        })
        .unwrap_or_default();
    let mut out = Vec::new();
    let height = rows.len() / CELL as usize;
    let width = rows.first().map_or(0, Vec::len) / CELL as usize;
    for ty in 0..height {
        for tx in 0..width {
            out.push(
                (0..8)
                    .map(|y| (0..8).map(|x| rows[ty * 8 + y][tx * 8 + x] as u8).collect())
                    .collect(),
            );
        }
    }
    out
}

fn color(c: &Value) -> [u8; 3] {
    [c[0].as_u64().unwrap_or(0) as u8, c[1].as_u64().unwrap_or(0) as u8, c[2].as_u64().unwrap_or(0) as u8]
}

fn cgram(palette: &Value, count: i64) -> Vec<u8> {
    let mut colors: Vec<[u8; 3]> = palette.as_array().map(|p| p.iter().map(color).collect()).unwrap_or_default();
    while (colors.len() as i64) < count {
        colors.push([0, 0, 0]);
    }
    let mut out = Vec::new();
    for c in colors {
        out.extend_from_slice(&(cgram_word(c) as u16).to_le_bytes());
    }
    out
}

/// A battle backdrop as the console reads it: `(tiles, colors)`, its 512
/// 8bpp tiles in tilemap order and its `COLORS` colours, padded with black.
pub fn backdrop_bytes(quality: &Value) -> (Vec<u8>, Vec<u8>) {
    let mut data = Vec::new();
    for cell in tiles(&quality["indices"]) {
        data.extend(pack_tile(&cell, 8));
    }
    (data, cgram(&quality["palette"], COLORS))
}

/// The light fallback of a backdrop, as the ROM carries it: its 4 KB of
/// 128x64 at 4bpp and its sixteen colours. **The bytes don't go in tile
/// order**, but in the one `scn_double` enlarges them in without doing any
/// arithmetic: each small tile becomes four large ones, filled two
/// neighbours of the same row at a time, large row by large row two at a
/// time, planes 0/1 before 2/3; and **each byte carries half a byte of two
/// planes**, so duplicated bit by bit it is already the two-plane word of
/// a row of a large tile. See `fallback_double` in the emission.
pub fn fallback_bytes(light: &Value) -> (Vec<u8>, Vec<u8>) {
    let smalls: Vec<Vec<u8>> = tiles(&light["small"])
        .into_iter()
        .map(|cell| {
            let shifted: Vec<Vec<u8>> =
                cell.iter().map(|row| row.iter().map(|v| (*v as i64 - CGRAM_BASE) as u8).collect()).collect();
            pack_tile(&shifted, FALLBACK_PLANES)
        })
        .collect();
    let columns = (FALLBACK_WIDTH / CELL) as usize;
    let mut out = Vec::new();
    for big_row in 0..TILES_Y as usize {
        let half = big_row % FALLBACK_SCALE as usize;
        for column in 0..columns {
            let small = &smalls[(big_row / FALLBACK_SCALE as usize) * columns + column];
            for pair in [0usize, 16] {
                for k in 0..4 {
                    let row = half * 4 + k;
                    let (p0, p1) = (small[pair + 2 * row], small[pair + 2 * row + 1]);
                    out.push((p0 & 0xF0) | (p1 >> 4));
                    out.push(((p0 & 0x0F) << 4) | (p1 & 0x0F));
                }
            }
        }
    }
    (out, cgram(&light["palette"], FALLBACK_COLORS))
}

/// A backdrop the ROM carries: its name, its number in the game, and its
/// light fallback as the stage answered it.
pub struct RomBackdrop {
    pub name: String,
    pub number: usize,
    pub light: Value,
}

/// The troops the compiled battles ask for, and the backdrop each one asks
/// for: a name, "" for none, or None for the place's.
pub struct Troops {
    pub ids: Vec<i32>,
    pub backdrops: BTreeMap<i32, Option<String>>,
}

/// Which backdrops and which battlers the cartridge carries, and who uses
/// each one.
pub struct Scene {
    pub game: Vec<String>,
    pub backdrops: Vec<RomBackdrop>,
    pub battlers: Vec<Battler>,
    pub battler_of: BTreeMap<i32, i64>,
    pub troop_backdrop: Vec<(i32, i64)>,
    pub map_backdrop: Vec<i64>,
    pub fallback_of: Vec<usize>,
    pub terrain_backdrop: Vec<i64>,
    /// The quality ones, for the `.msu`: every backdrop of the game.
    pub quality: Vec<(Vec<u8>, Vec<u8>)>,
}

/// It is the other half of the scene: here **which ones**. A battle asks for
/// its backdrop in three ways: an `EnemyEncounter` that names it, a random
/// encounter in a map that inherits it from the tree, and the terrain the
/// hero stands on if the map names none —the ROM resolves that one—. A
/// battler goes in if some troop of the cartridge uses it, **once** even if
/// four use it, and it is the image with its hue.
pub fn rom_scene(
    game: &Game,
    settings: &Settings,
    rtp: &Path,
    troops: &Troops,
    maps: &[MapInfo],
    encounters: &Value,
) -> Result<Scene> {
    let named = named_backdrops(game)?;
    let names = game_backdrops(game, rtp, &named);
    let number_of: BTreeMap<String, usize> =
        names.iter().enumerate().map(|(k, n)| (n.to_lowercase(), k)).collect();
    if names.len() as i64 >= PLACE_BACKDROP {
        crate::stop!(
            "the game has {} battle backdrops and the number of one is a byte, with ${PLACE_BACKDROP:02X} and $FF reserved",
            names.len()
        );
    }
    let number = |name: Option<&str>| -> i64 {
        match name {
            None => PLACE_BACKDROP,
            Some("") => FLAT_BACKDROP,
            Some(n) => number_of.get(&n.to_lowercase()).map_or(FLAT_BACKDROP, |&k| k as i64),
        }
    };
    let mut troop_backdrop = Vec::new();
    for n in &troops.ids {
        let k = match troops.backdrops.get(n) {
            None => FLAT_BACKDROP,
            Some(None) => PLACE_BACKDROP,
            Some(Some(name)) if name.is_empty() => FLAT_BACKDROP,
            Some(Some(name)) => number(Some(name)),
        };
        // A dictionary by troop: a repeated one keeps its first place.
        match troop_backdrop.iter_mut().find(|(t, _)| t == n) {
            Some(entry) => entry.1 = k,
            None => troop_backdrop.push((*n, k)),
        }
    }
    // The map's, for random encounters and for the troops that fight with
    // the one of the place; only where some battle can look at it.
    let per_map: Vec<i64> = match encounters.get("per_map").and_then(Value::as_array) {
        Some(list) if !list.is_empty() => list.iter().map(|v| v.as_i64().unwrap_or(0xFF)).collect(),
        _ => vec![0xFF; maps.len()],
    };
    let place_ones = troop_backdrop.iter().any(|(_, k)| *k == PLACE_BACKDROP);
    let mut map_backdrop = Vec::new();
    for (map, record) in maps.iter().zip(&per_map) {
        if *record != 0xFF || place_ones {
            map_backdrop.push(number(game.tree.map_background(map.id).as_deref()));
        } else {
            map_backdrop.push(FLAT_BACKDROP);
        }
    }
    let terrains = &game.db.terrain_backdrops;
    let top = terrains.keys().max().copied().unwrap_or(0);
    let terrain_backdrop: Vec<i64> = (0..=top)
        .map(|t| match terrains.get(&t) {
            Some(n) if !n.is_empty() => number(Some(n)),
            _ => FLAT_BACKDROP,
        })
        .collect();
    let of_terrains = |map: &MapInfo| -> Vec<i64> {
        let set: BTreeSet<u8> = map.block_terrain.iter().copied().collect();
        set.into_iter()
            .map(|t| terrain_backdrop.get(t as usize).copied().unwrap_or(FLAT_BACKDROP))
            .collect()
    };
    let mut requested: Vec<i64> = troop_backdrop.iter().map(|(_, k)| *k).collect();
    requested.extend(&map_backdrop);
    let mut possible = Vec::new();
    for ((map, record), k) in maps.iter().zip(&per_map).zip(&map_backdrop) {
        if *k != PLACE_BACKDROP {
            continue;
        }
        if *record != 0xFF {
            requested.extend(of_terrains(map));
        } else {
            possible.extend(of_terrains(map));
        }
    }
    let mut theirs: Vec<i64> = Vec::new();
    for k in requested {
        if k < PLACE_BACKDROP && !theirs.contains(&k) {
            theirs.push(k);
        }
    }
    let replacement_name = settings.string(&["battle", "fallback_backdrop"])?;
    let replacement_number = *number_of
        .get(&replacement_name.to_lowercase())
        .ok_or_else(|| Stop::new(format!("the fallback backdrop {} is not one of the game's", repr(&replacement_name))))?
        as i64;
    if possible.iter().any(|k| *k < PLACE_BACKDROP && !theirs.contains(k)) && !theirs.contains(&replacement_number) {
        theirs.push(replacement_number);
    }
    let scene = scene_settings();
    let found = |list: &[String], quality: bool, light: bool| -> Result<Vec<(Option<Value>, Option<Value>)>> {
        let paths: Vec<Option<PathBuf>> = list.iter().map(|n| find_file(game, rtp, "Backdrop", n)).collect();
        let wanted: Vec<(PathBuf, bool, bool)> =
            paths.iter().flatten().map(|p| (p.clone(), quality, light)).collect();
        let mut answers = images::backdrops(&scene, &wanted)?.into_iter();
        Ok(paths
            .iter()
            .map(|p| match p {
                None => (None, None),
                Some(_) => {
                    let a = answers.next().unwrap_or(Value::Null);
                    let q = (!a["quality"].is_null()).then(|| a["quality"].clone());
                    let l = (!a["light"].is_null()).then(|| a["light"].clone());
                    (q, l)
                }
            })
            .collect())
    };
    let wanted: Vec<String> = theirs.iter().map(|&k| names[k as usize].clone()).collect();
    let lights = found(&wanted, false, true)?;
    let mut backdrops = Vec::new();
    for (k, (_q, light)) in theirs.iter().zip(lights) {
        backdrops.push(RomBackdrop {
            name: names[*k as usize].clone(),
            number: *k as usize,
            light: light.unwrap_or(Value::Null),
        });
    }
    let place: BTreeMap<i64, usize> = theirs.iter().enumerate().map(|(i, k)| (*k, i)).collect();
    let replacement = place.get(&replacement_number).copied().unwrap_or(0);
    let fallback_of = (0..names.len() as i64).map(|k| place.get(&k).copied().unwrap_or(replacement)).collect();
    // The quality ones, for the `.msu`: all of them, in the ROM or not.
    let quality = found(&names, true, false)?
        .into_iter()
        .map(|(q, _)| backdrop_bytes(&q.unwrap_or(Value::Null)))
        .collect();

    // Which enemies ask for which battler, in the order they are asked for;
    // then the battlers, with a single call to the stage.
    let db: &Database = &game.db;
    let enemies_max = rm2k_snes_mapdata::engine::ENEMIES_MAX;
    let mut asked: Vec<(String, i64)> = Vec::new();
    let mut first_asked: Vec<(i32, (String, i64))> = Vec::new();
    for number in &troops.ids {
        let Some(troop) = db.troops.get(number) else { continue };
        for enemy in troop.members.iter().take(enemies_max) {
            if first_asked.iter().any(|(e, _)| e == enemy) {
                continue;
            }
            let Some(e) = db.enemies.get(enemy) else { continue };
            let (name, hue) = (e.battler_name.clone(), e.battler_hue as i64);
            first_asked.push((*enemy, (name.clone(), hue)));
            if !name.is_empty() && !asked.contains(&(name.clone(), hue)) {
                asked.push((name, hue));
            }
        }
    }
    let paths: Vec<Option<PathBuf>> = asked.iter().map(|(n, _)| find_file(game, rtp, "Monster", n)).collect();
    for ((name, _), path) in asked.iter().zip(&paths) {
        if path.is_none() {
            println!("  battler {} is neither in the game nor in the RTP: its enemies fight with no picture", repr(name));
        }
    }
    let mut answers = images::battlers(
        &scene,
        &asked.iter().zip(&paths).filter_map(|((_, hue), p)| p.clone().map(|p| (p, *hue))).collect::<Vec<_>>(),
    )?
    .into_iter();
    let mut drawn: Vec<((String, i64), Option<Battler>)> = Vec::new();
    for ((name, hue), path) in asked.iter().zip(&paths) {
        let info = match path {
            None => None,
            Some(_) => {
                let a = answers.next().unwrap_or(Value::Null);
                Some(Battler {
                    key: key(name, *hue),
                    image: name.clone(),
                    hue: *hue,
                    width: a["width"].as_i64().unwrap_or(0),
                    height: a["height"].as_i64().unwrap_or(0),
                    pixels: a["pixels"]
                        .as_array()
                        .map(|rows| {
                            rows.iter()
                                .map(|r| r.as_array().map(|r| r.iter().map(|v| v.as_i64().unwrap_or(0)).collect()).unwrap_or_default())
                                .collect()
                        })
                        .unwrap_or_default(),
                    rm_height: a["rm_height"].as_i64().unwrap_or(0),
                    palette: a["palette"].clone(),
                    colors: a["colors"].as_i64().unwrap_or(0),
                    merges: a["merges"].as_array().map_or(0, Vec::len),
                })
            }
        };
        drawn.push(((name.clone(), *hue), info));
    }
    let mut battlers: Vec<Battler> = Vec::new();
    let mut battler_k: BTreeMap<String, i64> = BTreeMap::new();
    let mut battler_of = BTreeMap::new();
    for (enemy, (name, hue)) in &first_asked {
        let k = key(name, *hue);
        if !battler_k.contains_key(&k) {
            let info = if name.is_empty() {
                None
            } else {
                drawn.iter().find(|(a, _)| a.0 == *name && a.1 == *hue).and_then(|(_, i)| i.clone())
            };
            match info {
                None => {
                    battler_k.insert(k.clone(), 0xFF);
                }
                Some(info) => {
                    battler_k.insert(k.clone(), battlers.len() as i64);
                    battlers.push(info);
                }
            }
        }
        battler_of.insert(*enemy, battler_k[&k]);
    }
    Ok(Scene {
        game: names,
        backdrops,
        battlers,
        battler_of,
        troop_backdrop,
        map_backdrop,
        fallback_of,
        terrain_backdrop,
        quality,
    })
}

/// The cartridge's battle scene as `rm2k-snes-mapdata emit` takes it: what
/// `rom_scene` decided, with what a backdrop and a battler look like, where
/// each member stands and in which order the troop is drawn, already as
/// bytes and numbers.
pub fn request(scene: &Scene, troops: &[i32], db: &Database) -> Value {
    let mut geometry = Map::new();
    for (name, value) in [
        ("WIDTH", WIDTH),
        ("HEIGHT", HEIGHT),
        ("TILES", TILES),
        ("TILES_X", TILES_X),
        ("TILES_Y", TILES_Y),
        ("COLORS", COLORS),
        ("CGRAM_BASE", CGRAM_BASE),
        ("VRAM_TILES", VRAM_TILES),
        ("VRAM_MAP", VRAM_MAP),
        ("FALLBACK_COLORS", FALLBACK_COLORS),
        ("FALLBACK_PLANES", FALLBACK_PLANES as i64),
        ("FALLBACK_WIDTH", FALLBACK_WIDTH),
        ("FALLBACK_HEIGHT", FALLBACK_HEIGHT),
        ("FALLBACK_SCALE", FALLBACK_SCALE),
        ("BATTLER_PALETTE", BATTLER_PALETTE),
    ] {
        geometry.insert(name.into(), json!(value));
    }
    let backdrops: Vec<Value> = scene
        .backdrops
        .iter()
        .map(|b| {
            let (tiles, colors) = fallback_bytes(&b.light);
            json!({"tiles": hex(&tiles), "colors": hex(&colors)})
        })
        .collect();
    let enemies_max = rm2k_snes_mapdata::engine::ENEMIES_MAX;
    let mut placed = Vec::new();
    for number in troops {
        let Some(troop) = db.troops.get(number) else { continue };
        let theirs: Vec<(i32, (i32, i32))> =
            troop.members.iter().copied().zip(troop.positions.iter().copied()).take(enemies_max).collect();
        let mut members = Vec::new();
        let mut infos: Vec<Option<&Battler>> = Vec::new();
        for (enemy, center) in &theirs {
            let k = scene.battler_of.get(enemy).copied().unwrap_or(0xFF);
            let info = (k != 0xFF).then(|| &scene.battlers[k as usize]);
            infos.push(info);
            let (x, y) = info.map_or((0, 0), |b| position(*center, b));
            members.push(json!([k, x, y]));
        }
        let centers: Vec<(i32, i32)> = theirs.iter().map(|(_, c)| *c).collect();
        placed.push(json!([number, members, drawing_order(&centers, &infos)]));
    }
    json!({
        "geometry": geometry,
        "game": scene.game.len(),
        "troop_backdrop": scene.troop_backdrop.iter().map(|(n, k)| json!([n, k])).collect::<Vec<_>>(),
        "map_backdrop": scene.map_backdrop,
        "terrains": scene.terrain_backdrop,
        "fallback_of": scene.fallback_of,
        "backdrops": backdrops,
        "battlers": scene.battlers.iter().map(|b| json!({
            "columns": columns(b), "height": b.height, "palette": b.palette,
            "bytes": hex(&battler_bytes(b)),
        })).collect::<Vec<_>>(),
        "troops": placed,
    })
}

/// Who asks for each animation and each battler of the cartridge, per
/// patch class: `{key: [origin, ...]}`, the origin being the map whose page
/// or random encounter asks for it, or "caso" if a test page does. It is
/// what lets `rm2k-snes-patches --check` know what is not the game's in the
/// ROM that is played. The bytecode is walked, so it counts what ended up
/// emitted.
pub fn patch_uses(maps: &[MapInfo], game: &Game) -> Result<Value> {
    #[derive(Clone, PartialEq, Eq, PartialOrd, Ord)]
    enum Origin {
        Map(i32),
        Case,
    }
    let mut animations: BTreeMap<i64, BTreeSet<Origin>> = BTreeMap::new();
    let mut troops: Vec<(i64, BTreeSet<Origin>)> = Vec::new();
    let add_troop = |n: i64, o: Origin, troops: &mut Vec<(i64, BTreeSet<Origin>)>| {
        match troops.iter_mut().find(|(t, _)| *t == n) {
            Some(entry) => {
                entry.1.insert(o);
            }
            None => troops.push((n, BTreeSet::from([o]))),
        }
    };
    let no_drawing = rm2k_snes_mapdata::engine::ANIM_NO_DRAWING as u8;
    for map in maps {
        for page in &map.pages {
            let origin = if page.test { Origin::Case } else { Origin::Map(map.id) };
            let code = &page.code;
            for i in bytecode::walk(code)? {
                if code[i] == OP_ANIMATION && bytecode::at(code, i + 1) != no_drawing {
                    animations.entry(bytecode::at(code, i + 1) as i64).or_default().insert(origin.clone());
                } else if code[i] == OP_BATTLE {
                    let n = bytecode::at(code, i + 1) as i64 | (bytecode::at(code, i + 2) as i64) << 8;
                    add_troop(n, origin.clone(), &mut troops);
                }
            }
        }
        for zone in game.tree.rules.encounter_zones(map.id, map.map.width as i64, map.map.height as i64) {
            for number in zone.troops {
                add_troop(number, Origin::Map(map.id), &mut troops);
            }
        }
    }
    let mut battlers: BTreeMap<String, BTreeSet<Origin>> = BTreeMap::new();
    let enemies_max = rm2k_snes_mapdata::engine::ENEMIES_MAX;
    for (number, origins) in &troops {
        let Some(troop) = game.db.troops.get(&(*number as i32)) else { continue };
        for enemy in troop.members.iter().take(enemies_max) {
            let Some(e) = game.db.enemies.get(enemy) else { continue };
            if !e.battler_name.is_empty() {
                battlers.entry(key(&e.battler_name, e.battler_hue as i64)).or_default().extend(origins.iter().cloned());
            }
        }
    }
    // The origins go sorted as text, so a map id and "caso" can share a
    // list; and the keys by the text of their `(key, origins)` pair, which
    // is the order the file always had.
    fn origins(set: &BTreeSet<Origin>) -> Value {
        let mut list: Vec<(String, Value)> = set
            .iter()
            .map(|o| match o {
                Origin::Map(m) => (m.to_string(), json!(m)),
                Origin::Case => ("caso".to_string(), json!("caso")),
            })
            .collect();
        list.sort_by(|a, b| a.0.cmp(&b.0));
        Value::Array(list.into_iter().map(|(_, v)| v).collect())
    }
    let mut anim: Vec<(String, String, Value)> = animations
        .iter()
        .map(|(k, v)| (format!("({k}, "), k.to_string(), origins(v)))
        .collect();
    anim.sort_by(|a, b| a.0.cmp(&b.0));
    let mut bat: Vec<(String, String, Value)> =
        battlers.iter().map(|(k, v)| (format!("({}, ", repr(k)), k.clone(), origins(v))).collect();
    bat.sort_by(|a, b| a.0.cmp(&b.0));
    let object = |list: Vec<(String, String, Value)>| {
        let mut m = Map::new();
        for (_, k, v) in list {
            m.insert(k, v);
        }
        Value::Object(m)
    };
    Ok(json!({"animacion": object(anim), "battler": object(bat)}))
}

/// The battler's numbers, for the log.
pub fn battler_report(b: &Battler) -> String {
    format!(
        "  battler {}: {}x{}, {} B, {} colors of {}",
        repr(&b.key),
        b.width,
        b.height,
        battler_bytes(b).len(),
        b.palette.as_array().map_or(0, Vec::len),
        b.colors
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn battler(width: i64, height: i64, pixels: Vec<Vec<i64>>) -> Battler {
        Battler {
            key: "b".into(),
            image: "b".into(),
            hue: 0,
            width,
            height,
            pixels,
            rm_height: height * 5 / 4,
            palette: json!([]),
            colors: 0,
            merges: 0,
        }
    }

    #[test]
    fn a_length_scales_to_four_fifths_rounding_and_never_to_zero() {
        assert_eq!(scale(320), 256);
        assert_eq!(scale(2), 2);
        assert_eq!(scale(0), 1);
    }

    #[test]
    fn a_battler_is_clamped_inside_the_scene() {
        let b = battler(64, 100, vec![]);
        assert_eq!(position((160, 80), &b), (96, 14));
        assert_eq!(position((0, 0), &b), (0, 0));
        assert_eq!(position((320, 240), &b), (WIDTH - 64, HEIGHT - 100));
    }

    #[test]
    fn the_lower_edge_goes_on_top_and_on_a_tie_the_lower_place() {
        let tall = battler(8, 40, vec![]);
        let short = battler(8, 8, vec![]);
        let order = drawing_order(&[(10, 100), (10, 100), (10, 90)], &[Some(&short), Some(&short), Some(&tall)]);
        assert_eq!(order, [1, 0, 2]);
    }

    #[test]
    fn a_battler_goes_plane_by_plane_each_row_backwards_after_a_zero() {
        // Nine pixels wide: two columns of a plane. Pixel 0 is color 1 and
        // pixel 8 is color 2.
        let mut row = vec![0i64; 9];
        row[0] = 1;
        row[8] = 2;
        let b = battler(9, 1, vec![row]);
        let bytes = battler_bytes(&b);
        assert_eq!(columns(&b), 2);
        assert_eq!(bytes.len(), BATTLER_PLANES * 3 + 1);
        // The mask: both lit.
        assert_eq!(&bytes[0..3], [0, 0x80, 0x80]);
        // Plane 0 of the drawing has pixel 0, plane 1 pixel 8.
        assert_eq!(&bytes[3..6], [0, 0x00, 0x80]);
        assert_eq!(&bytes[6..9], [0, 0x80, 0x00]);
        assert_eq!(*bytes.last().unwrap(), 0);
    }

    #[test]
    fn the_fallback_carries_half_a_byte_of_two_planes() {
        // A backdrop of one colour, the second of its palette: every pixel
        // is `CGRAM_BASE + 1`, which is plane 0 lit.
        let small = vec![vec![CGRAM_BASE + 1; FALLBACK_WIDTH as usize]; FALLBACK_HEIGHT as usize];
        let light = json!({"small": small, "palette": [[0, 0, 0], [31, 0, 0]]});
        let (tiles, colors) = fallback_bytes(&light);
        assert_eq!(tiles.len() as i64, TILES_Y * (FALLBACK_WIDTH / CELL) * 16);
        // Of each pair of planes, the first byte has plane 0's high nibble
        // over plane 1's, the second the low nibbles: 0xF0 and 0xF0.
        assert_eq!(&tiles[0..2], [0xF0, 0xF0]);
        // Planes 2 and 3 are empty.
        assert_eq!(&tiles[8..10], [0, 0]);
        assert_eq!(colors.len() as i64, FALLBACK_COLORS * 2);
        assert_eq!(&colors[2..4], [31, 0]);
    }

    #[test]
    fn a_battler_is_named_by_its_image_and_its_hue() {
        assert_eq!(key("Rat", 0), "Rat");
        assert_eq!(key("Rat", 120), "Rat-120");
    }
}
