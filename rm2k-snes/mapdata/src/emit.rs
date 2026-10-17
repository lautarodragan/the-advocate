//! The whole `.inc`: the header of constants, the maps —see [`record`]—,
//! the message window and its font, the picture, the battle animations,
//! the title and the full screens, the slots screen and the pause menu,
//! the item, equipment and shop screens, the battle and its tables, the
//! troops and their pages, the battle scene, and the tables the console
//! reads from bank 0.
//!
//! What it writes is what the converter's Python wrote until 2026-10-01,
//! character by character: the long blocks of constants keep their
//! templates as they were —see [`crate::pyfmt`]— so that nobody has to
//! read them twice to know they say the same.

use crate::asm::{block, msu_block, unplaced};
use crate::cgram::{cgram_reserved, PRIORITY_ABOVE, WINDOW_PALETTE};
use crate::engine::*;
use crate::fail::{Bad, Result};
use crate::json::{
    at, bytes_at, colors, int, int_at, ints, ints_at, list, list_at, text, text_at, tiles,
};
use crate::objects::{LAYER_SAME, OBJ_COLORS, OBJ_PRIORITY, OBJ_PRIORITY_ABOVE};
use crate::pyf;
use crate::pyfmt::{format, Arg};
use crate::record::{
    self, ACTOR_BYTES, ACTOR_COLORS, ANIM_FAM_STRIDE, ANIM_STRIDE, EV_MAX, EV_STRIDE, FAMILIES,
    FLASH_MAX, MAP_STRIDE, NPC_MAX, NPC_STILL, NPC_STRIDE, PAGE_BYTES, PARALLEL_MAX, ROUTE_EV_MAX, TWIN_STRIDE,
    ROUTE_GFX_MAX, TURN_NONE,
};
use crate::request::{Emit, MessageFace, MsuData};
use crate::snes::{
    cgram_bytes, cgram_word, entry, pack_tile, words_le, Color, BYTES_PER_TILE, COLORS_PER_PALETTE,
};
use crate::vram::{
    MAP_LAYOUT, SLOTS, SLOT_MAP, SLOT_TEXT_LEVEL, SLOT_TEXT_WIDTH, SLOT_VRAM, VRAM_ABOVE_MAP,
    WINDOW_BASES,
};
use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::rules;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};

mod custom_menu;
mod header;
mod skills_screen;
use header::HEADER;

/// What [`emit`] makes.
pub struct Emitted {
    /// The `.inc`.
    pub text: String,
    /// What it says while it writes, in order.
    pub notes: Vec<String>,
    /// What was shared and compressed.
    pub report: Vec<String>,
    /// Per map, how many frames the console takes to decompress it.
    pub frames: Vec<f64>,
    /// Per map, what the console decompresses, uncompressed.
    pub raw: Vec<crate::materials::RawBlocks>,
}

/// The LDB terms the battle screen uses, in the order the console indexes
/// them, by the name the `.inc` gives them and liblcf's.
pub const BATTLE_TERMS: [(&str, &str); 29] = [
    ("attack", "command_attack"),
    ("defend", "command_defend"),
    ("escape", "battle_escape"),
    ("hp", "hp_short"),
    ("attacks", "attacking"),
    ("defends", "defending"),
    ("critical", "actor_critical"),
    ("damage_enemy", "enemy_damaged"),
    ("no_damage_enemy", "enemy_undamaged"),
    ("damage_actor", "actor_damaged"),
    ("no_damage_actor", "actor_undamaged"),
    ("victory", "victory"),
    ("defeat", "defeat"),
    ("fled", "escape_success"),
    ("no_fled", "escape_failure"),
    ("use", "command_item"),
    ("skill", "command_skill"),
    ("uses", "use_item"),
    ("recovered", "hp_recovery"),
    ("exp_received", "exp_received"),
    ("level", "level"),
    ("level_up", "level_up"),
    ("learned", "skill_learned"),
    ("gold_a", "gold_recieved_a"),
    ("currency", "gold"),
    ("gold_b", "gold_recieved_b"),
    ("obtained", "item_recieved"),
    ("sp", "sp_short"),
    ("normal", "normal_status"),
];

/// A term of the database, by liblcf's name.
fn term(db: &Db, name: &str) -> Result<String> {
    let t = &db.terms;
    Ok(match name {
        "command_attack" => &t.command_attack,
        "command_defend" => &t.command_defend,
        "battle_escape" => &t.battle_escape,
        "hp_short" => &t.hp_short,
        "attacking" => &t.attacking,
        "defending" => &t.defending,
        "actor_critical" => &t.actor_critical,
        "enemy_damaged" => &t.enemy_damaged,
        "enemy_undamaged" => &t.enemy_undamaged,
        "actor_damaged" => &t.actor_damaged,
        "actor_undamaged" => &t.actor_undamaged,
        "victory" => &t.victory,
        "defeat" => &t.defeat,
        "escape_success" => &t.escape_success,
        "escape_failure" => &t.escape_failure,
        "command_item" => &t.command_item,
        "command_skill" => &t.command_skill,
        "use_item" => &t.use_item,
        "hp_recovery" => &t.hp_recovery,
        "exp_received" => &t.exp_received,
        "level" => &t.level,
        "level_up" => &t.level_up,
        "skill_learned" => &t.skill_learned,
        "gold_recieved_a" => &t.gold_recieved_a,
        "gold" => &t.gold,
        "gold_recieved_b" => &t.gold_recieved_b,
        "item_recieved" => &t.item_recieved,
        "sp_short" => &t.sp_short,
        "normal_status" => &t.normal_status,
        "lvl_short" => &t.lvl_short,
        _ => return Err(Bad::usage(format!("there is no term {name:?}"))),
    }
    .clone())
}

/// The geometry the screens and the battle screen were drawn with, by
/// name.
struct Geometry<'a>(&'a Value);

impl Geometry<'_> {
    fn n(&self, name: &str) -> i64 {
        self.0
            .get(name)
            .and_then(Value::as_i64)
            .unwrap_or_else(|| panic!("the geometry has no {name}"))
    }

    fn v(&self, name: &str) -> &Value {
        self.0
            .get(name)
            .unwrap_or_else(|| panic!("the geometry has no {name}"))
    }
}

/// The text block of the text screens, which the console names by index.
struct Texts {
    data: Vec<u8>,
    offsets: Vec<(usize, usize)>,
    first: usize,
    count: usize,
}

/// A name or a term of the database with each letter the font lacks as its
/// plain ASCII stand-in —an actor's `Unamë` as `Uname`, see
/// `rm2k_snes_text::plain`—, where [`Texts::add`] would write a `?`.
fn plain(text: &str) -> String {
    rm2k_snes_text::plain::plain_text(text).0
}

impl Texts {
    /// What the text screens' font can write: the characters it has, a `?`
    /// for the others, cut to `width` —`item_text` in the screens stage—.
    /// What comes from the screens stage has its plain letters stood in
    /// already; what comes from the database goes through [`plain`] first.
    fn add(&mut self, text: &str) -> i64 {
        let fitted: String = text
            .chars()
            .map(|c| {
                let n = c as usize;
                if (self.first..self.first + self.count).contains(&n) {
                    c
                } else {
                    '?'
                }
            })
            .take(255)
            .collect();
        self.offsets.push((self.data.len(), fitted.len()));
        self.data.extend_from_slice(fitted.as_bytes());
        self.offsets.len() as i64 - 1
    }
}

fn line(out: &mut String, text: &str) {
    out.push_str(text);
    out.push('\n');
}

/// `label:` and a `.byte` line, or `$FF` when there is nothing: what the
/// tables of bank 0 look like. With `declare`, its `.block` in front.
fn bytes_asm(out: &mut String, label: &str, values: &[String], declare: bool) {
    if declare {
        out.push_str(&format!(".block {}\n", values.len().max(1)));
    }
    let joined = if values.is_empty() {
        "$FF".to_string()
    } else {
        values.join(", ")
    };
    out.push_str(&format!("{label}:\n    .byte {joined}\n"));
}

/// The same with `.word`, and `0` when there is nothing.
fn words_asm(out: &mut String, label: &str, values: &[String], declare: bool) {
    if declare {
        out.push_str(&format!(".block {}\n", (2 * values.len()).max(2)));
    }
    let joined = if values.is_empty() {
        "0".to_string()
    } else {
        values.join(", ")
    };
    out.push_str(&format!("{label}:\n    .word {joined}\n"));
}

fn decimal<T: ToString>(values: impl IntoIterator<Item = T>) -> Vec<String> {
    values.into_iter().map(|v| v.to_string()).collect()
}

fn hex2(values: impl IntoIterator<Item = i64>) -> Vec<String> {
    values.into_iter().map(|v| format!("${v:02X}")).collect()
}

fn hex4(values: impl IntoIterator<Item = i64>) -> Vec<String> {
    values.into_iter().map(|v| format!("${v:04X}")).collect()
}

/// Cells of a 4bpp tilemap as words: the index already carries its palette.
fn cell_words(cells: &[i64], priority: u32) -> Vec<u8> {
    words_le(
        cells
            .iter()
            .map(|&c| entry(c as u32, false, false, priority)),
    )
}

/// Tiles in the PPU's format.
fn packed(cells: &[Vec<Vec<u8>>], planes: usize) -> Vec<u8> {
    cells.iter().flat_map(|c| pack_tile(c, planes)).collect()
}

/// Palettes of sixteen, padded with black.
fn palettes_cgram(palettes: &[Vec<Color>]) -> Vec<u8> {
    let mut all = Vec::new();
    for palette in palettes {
        all.extend_from_slice(palette);
        all.extend(std::iter::repeat_n(
            [0, 0, 0],
            MENU_CGRAM.saturating_sub(palette.len()),
        ));
    }
    cgram_bytes(&all)
}

/// The CRC-32 of zlib, which signs the save format.
fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for &b in data {
        crc ^= u32::from(b);
        for _ in 0..8 {
            crc = if crc & 1 != 0 {
                (crc >> 1) ^ 0xEDB8_8320
            } else {
                crc >> 1
            };
        }
    }
    !crc
}

/// A JSON value as Python's `json.dumps` writes it: `, ` and `: `.
fn python_json(value: &Value) -> String {
    match value {
        Value::Array(items) => {
            format!(
                "[{}]",
                items.iter().map(python_json).collect::<Vec<_>>().join(", ")
            )
        }
        Value::Object(map) => format!(
            "{{{}}}",
            map.iter()
                .map(|(k, v)| format!("{}: {}", Value::String(k.clone()), python_json(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
        other => other.to_string(),
    }
}

/// How many bytes the ROM's switch table takes, a bit per switch from 0 to
/// `top`, the highest the game names. It lives in the cartridge's `SWITCHRAM`,
/// 256 bytes of far RAM, and a game past it is refused before this: see
/// `switch_top` in the event compiler.
pub fn switch_bytes(top: i64) -> Result<i64> {
    let bytes = top.max(0) / 8 + 1;
    if bytes > 256 {
        return Err(Bad::answer(format!("switch {top} does not fit the ROM's switch table, 256 bytes")));
    }
    Ok(bytes)
}

/// Sixteen bits that change when what each byte of the saved game means
/// changes —which variable goes in each slot, which actor each skill pair
/// and each experience slot belongs to—, so that the console rejects a save
/// from another build. It is the assignments and not the whole cartridge on
/// purpose: two builds whose save reads the same can share it.
fn save_signature(
    variables: &[(i64, i64)],
    pairs: &[(i64, i64, i64)],
    experience: &Value,
    n_actors: i64,
    switch_bytes: i64,
) -> u32 {
    let shape =
        format!(
        "{{\"variables\": {}, \"items\": {ITEMS_N}, \"switches\": {switch_bytes}, \"actores\": \
         {n_actors}, \"habilidades\": {}, \"experiencia\": {}}}",
        python_json(&Value::Array(
            variables.iter().map(|(v, s)| serde_json::json!([v, s])).collect()
        )),
        python_json(&Value::Array(
            pairs.iter().map(|(a, h, r)| serde_json::json!([a, h, r])).collect()
        )),
        python_json(experience)
    );
    crc32(shape.as_bytes()) & 0xFFFF
}

/// The sine the screen shake reads by index, in bank 0's neighbour.
fn sine_table() -> String {
    let mut out = vec![
        "; The sine at scale 127, for the screen shake: it is the same".to_string(),
        "; list `SENO_SACUDIDA` builds in events.py.".into(),
        ";".into(),
        "; It goes outside bank 0 —`lda f:sine_shake, x`, one read per".into(),
        "; shake frame— for the same reason as `item_k`: it is 256 bytes".into(),
        "; and the code's bank filled up.".into(),
        ".segment \"RODATA\"".into(),
        ".block 256".into(),
        "sine_shake:".into(),
    ];
    let values = shake_sine();
    for chunk in values.chunks(16) {
        out.push(format!(
            "    .byte {}",
            chunk
                .iter()
                .map(|v| format!("${:02X}", v & 0xFF))
                .collect::<Vec<_>>()
                .join(",")
        ));
    }
    // And back to bank 0: what follows is read with absolute indexed
    // addressing and has to stay there.
    out.push(".segment \"TABLES\"".into());
    out.join("\n") + "\n"
}

/// Everything the cartridge carries, as the `.inc` ca65 assembles with
/// the runtime.
pub fn emit(r: &Emit, db: &Db) -> Result<Emitted> {
    let screens = &r.screens;
    let t = Geometry(at(screens, "layout")?);
    let model = &r.battle_model;
    let bs = Geometry(at(model, "layout")?);
    let slot_text_max = SLOT_TEXT_LEVEL as i64 + t.n("LEVEL_DIGITS");

    // Everything that goes per map, first: it is also where what each map
    // spends is checked against its VRAM layout.
    let per_map = record::maps_with(&r.maps, r.rom.msu != MsuData::Optional)?;


    let windows = normalized_windows(at(screens, "window")?, &r.window_systems)?;
    let window = &windows[0];
    let slots = at(screens, "slots")?;
    let title = r.title.as_ref().map(|full| (full, at(screens, "title")));
    let title_menu = match &title {
        Some((_, menu)) => Some(
            menu.as_ref()
                .map_err(|e| Bad::answer(e.message().to_string()))?,
        ),
        None => None,
    };
    let variables_n = r.variables.len().max(1);
    if variables_n > 256 {
        return Err(Bad::answer(format!(
            "{variables_n} variables don't fit in far RAM: FAR_ITEMS is 512 bytes from FAR_VARIABLES"
        )));
    }
    let faces: BTreeMap<i64, &Value> = at(slots, "faces")?
        .as_object()
        .ok_or_else(|| Bad::answer("the slots' faces are not an object"))?
        .iter()
        .map(|(k, v)| {
            Ok((
                k.parse::<i64>()
                    .map_err(|_| Bad::answer(format!("face {k}")))?,
                v,
            ))
        })
        .collect::<Result<_>>()?;
    let cell = CELL;
    let cols = COLS;

    let mut args: Vec<Arg> = vec![
        r.maps
            .iter()
            .map(|m| format!("{} {}", m.id, m.name))
            .collect::<Vec<_>>()
            .join(", ")
            .into(),
        r.maps.len().into(),
        MAP_STRIDE.into(),
        r.start.into(),
        VRAM_ABOVE_MAP.into(),
        MAP_LAYOUT.into(),
        NPC_STRIDE.into(),
        NPC_MAX.into(),
        NPC_STILL.into(),
        EV_STRIDE.into(),
        EV_MAX.into(),
        TWIN_STRIDE.into(),
        ROUTE_EV_MAX.into(),
        PAGE_BYTES.into(),
        TURN_NONE.into(),
        ROUTE_GFX_MAX.into(),
        HEADER_LINES.into(),
        HEADER_AUTO_CLOSE.into(),
        PAUSE_FRAMES.into(),
        VAR_REFRESH.into(),
        VAR_SLOT_MAX.into(),
        ANIM_ENTRY_BYTES.into(),
        ANIM_SOUND.into(),
        ANIM_SCREEN_FLASH.into(),
        KEY_WAIT.into(),
        KEY_DIRS.into(),
        KEY_DECISION.into(),
        KEY_CANCEL.into(),
        KEY_START.into(),
        KEY_VALUE_DECISION.into(),
        KEY_VALUE_CANCEL.into(),
        KEY_VALUE_DIR[0].into(),
        KEY_VALUE_DIR[1].into(),
        KEY_VALUE_DIR[3].into(),
        KEY_VALUE_DIR[2].into(),
        OBJ_SIDE.into(),
        (4 * GRID).into(),
        RAIN_DROPS.iter().copied().max().unwrap_or(0).into(),
        RAIN_DROPS[0].into(),
        RAIN_DROPS[1].into(),
        RAIN_DROPS[2].into(),
        RAIN_LIFE.into(),
        RAIN_SPAWN.into(),
        RAIN_SEED.into(),
        WEATHER_RAIN.into(),
        ITEMS_N.into(),
        ITEM_MAX.into(),
        variables_n.into(),
        VAR_ADD.into(),
        VAR_VARIABLE.into(),
        VAR_RANDOM.into(),
        VAR_OTHER.into(),
        VAR_CHARACTER.into(),
        CHARACTER_X.into(),
        CHARACTER_Y.into(),
        VAR_ACTOR.into(),
        CELL_Y.into(),
        CELL_REFRESH.into(),
        RANDOM_SEED.into(),
        ENC_SEED.into(),
        TIMER_SET_VAR.into(),
        TIMER_SLOT.into(),
        COND_TIMER.into(),
        COND_GOLD.into(),
        COND_ITEM.into(),
        COND_ACTOR.into(),
        COND_ACTOR_SKILL.into(),
        COND_ACTOR_EQUIPMENT.into(),
        COND_ACTOR_HP.into(),
        GOLD_MAX.into(),
        PAN_LOCK.into(),
        PAN_UNLOCK.into(),
        PAN_SHIFT.into(),
        PAN_RETURN.into(),
        TIMER_SET.into(),
        TIMER_START.into(),
        TIMER_X.into(),
        TIMER_Y.into(),
        TIMER_GLYPH_W.into(),
        (TIMER_GLYPHS - 1).into(),
        FRAMES_PER_SECOND.into(),
        TIMER_EXTRA_FRAMES.into(),
        FLASH_MAX.into(),
        PARALLEL_MAX.into(),
        TRIGGER_AUTOSTART.into(),
        TRIGGER_ACTION.into(),
        TRIGGER_TOUCH_HERO.into(),
        TRIGGER_COLLISION.into(),
        TRIGGER_PARALLEL.into(),
        FRAMES_PER_CELL.into(),
        ROUTE_FREQUENCY.into(),
        ROUTE_WAIT_FRAMES.into(),
        JUMP_STEP.into(),
        NEUTRAL_TINT.into(),
        FADE_RAMP.into(),
        FADE_TOTAL.into(),
        FADE_RAMP.into(),
        FADE_RAMP.into(),
        BRIGHTNESS_MAX.into(),
        TRANSITION_MOSAIC.into(),
        TRANSITION_CUT.into(),
        LUMA_R.into(),
        LUMA_G.into(),
        LUMA_B.into(),
        switch_bytes(r.switch_top)?.into(),
        PARTY_MAX.into(),
        r.party.len().into(),
        ACTOR_BYTES.into(),
        ACTOR_COLORS.into(),
        OBJ_COLORS.into(),
        LAYER_SAME.into(),
        (if r.hero_above {
            OBJ_PRIORITY_ABOVE
        } else {
            OBJ_PRIORITY
        })
        .into(),
        cgram_reserved(r.window_colors).into(),
        (WINDOW_PALETTE as usize * COLORS_PER_PALETTE).into(),
        (bytes_at(window, "tiles")?.len() / 32).into(),
        t.n("WINDOW_ROWS_INC").into(),
        t.n("WINDOW_COLS_INC").into(),
        int_at(window, "base")?.into(),
        t.n("WINDOW_TEXT_ROW").into(),
        t.n("WINDOW_TEXT_ROWS").into(),
        t.n("WINDOW_TEXT_COL").into(),
        t.n("WINDOW_TEXT_COLS").into(),
        t.n("MESSAGE_WIDTH").into(),
        t.n("FONT_HEIGHT").into(),
        t.n("FONT_WIDTH").into(),
        int_at(window, "shadow")?.into(),
        t.n("FONT_PRE_ROWS").into(),
        t.n("FONT_PRE_CHAR").into(),
        t.n("CHOICE_INDENT").into(),
        t.n("MSG_FACE_ROW").into(),
        t.n("MSG_FACE_COL_LEFT").into(),
        t.n("MSG_FACE_COL_RIGHT").into(),
        t.n("MSG_FACE_TEXT_X").into(),
        t.n("MSG_FACE_RIGHT_X").into(),
        t.n("WINDOW_ARROW_ROW").into(),
        t.n("WINDOW_ARROW_COL").into(),
        t.n("WINDOW_ARROW_CELLS").into(),
        FAMILIES.len().into(),
        ANIM_STRIDE.into(),
        ANIM_FAM_STRIDE.into(),
        WATER_FRAMES_SLOW.into(),
        FAMILIES[0].2.into(),
        WATER_CYCLE.into(),
        ANIMATED_FRAMES.into(),
        ANIMATED_STEPS.into(),
        BYTES_PER_TILE.into(),
        title.as_ref().map_or(0, |(full, _)| full.tiles).into(),
        title.as_ref().map_or(8, |(full, _)| full.bpp).into(),
        MENU_CGRAM.into(),
    ];
    let menu_counts = match title_menu {
        None => (0, 0),
        Some(menu) => (
            list_at(menu, "tiles")?.len(),
            list_at(menu, "texts")?.len(),
        ),
    };
    args.extend([
        menu_counts.0.into(),
        menu_counts.1.into(),
        SLOT_VRAM.into(),
        SLOT_MAP.into(),
        list_at(slots, "rows")?.len().into(),
        list_at(slots, "tiles")?.len().into(),
        slots
            .get("menu_tiles")
            .and_then(Value::as_u64)
            .map_or(list_at(slots, "tiles")?.len(), |n| n as usize)
            .into(),
        (t.n("HEADER_Y").div_euclid(cell)).into(),
        t.n("HEADER_ROWS").into(),
        (t.n("HEADER_ROWS") * cols).into(),
        (t.n("SLOT_Y").div_euclid(cell)).into(),
        (t.n("SLOT_STEP").div_euclid(cell)).into(),
        t.n("SLOT_ROWS").into(),
        (t.n("SLOT_ROWS") * cols).into(),
        (t.n("HEADER_Y").div_euclid(cell) * 32).into(),
        t.n("FACES_MAX").into(),
        t.n("FACE_CELLS").into(),
        t.n("FACE_CELLS").into(),
        t.n("NAME_COLS").into(),
        SLOT_TEXT_WIDTH.into(),
        SLOT_TEXT_LEVEL.into(),
        slot_text_max.into(),
        t.n("LEVEL_DIGITS").into(),
        ((t.n("LEVEL_ROW") - t.n("NAME_ROW")) * 32 + t.n("LEVEL_COL") - t.n("NAME_COL")).into(),
        ((i64::from(b'0') - t.n("ITEM_FIRST_CHAR")) * 4).into(),
        (faces
            .keys()
            .copied()
            .chain(r.actors.iter().copied())
            .max()
            .unwrap_or(-1)
            .max(-1)
            + 1)
        .into(),
        (list_at(slots, "palettes")?.len() * MENU_CGRAM).into(),
        MENU_CGRAM.into(),
    ]);
    let mut out = format(HEADER, &args);

    // Who the cartridge is.
    out.push_str(&pyf!(
        "; Who the ROM is, from the project file: the header title and\n\
         ; the signature with which the SRAM says a slot holds a save of\n\
         ; this game.\n\
         .define ROM_TITLE \"%s\"\n\
         .define SRAM_MAGIC_TEXT \"%s\"\n\n",
        format!("{:<21}", r.rom.title),
        r.rom.sram_signature.clone()
    ));
    // Only in a cartridge that needs the MSU-1: one that does not gets the
    // same `.inc` as before there was a way to need it.
    if r.rom.msu != MsuData::Optional {
        out.push_str(
            "; This cartridge needs the MSU-1: what does not fit in the ROM\n\
             ; goes to the `.msu` —the bank packing decides it, see\n\
             ; `pack_with_msu` in rm2k-snes-cartridge—, and the ROM does not\n\
             ; start without it. See `msu_required` in msu1.s.\n\
             MSU_REQUIRED = 1\n",
        );
        if r.rom.msu == MsuData::Everything {
            out.push_str(
                "; And everything that may go goes, even if it fitted: a test\n\
                 ; cartridge, for the path to run.\n\
                 MSU_SPILL_EVERYTHING = 1\n",
            );
        }
        out.push('\n');
    }
    out.push_str(&per_map.offsets);
    out.push_str("\n\n");
    out.push_str(&pyf!(
        "; Whether L and R change the hero's speed: see `hero_speed_keys.s`.\nHERO_SPEED_KEYS = %d\n\n",
        r.speed_keys
    ));
    // The fade ramp, in bank 0: `fade_tick` reads it with `lda fade_ramp, x`.
    out.push_str(&pyf!(
        ".segment \"TABLES\"\n\
         ; The master brightness on each frame of the ramp, from\n\
         ; black to full. Going down it is read backwards.\n\
         fade_ramp:\n        .byte %s\n\n",
        decimal(fade_ramp()).join(",")
    ));
    // The data goes in RODATA, which the linker spreads over the upper
    // banks; what stays in TABLES —bank 0— is what the console walks with a
    // bare `lda table, x`.
    out.push_str(".segment \"RODATA\"\n");
    out.push_str(&per_map.maps);

    let mut notes = per_map.notes.clone();
    window_section(&mut out, r, &windows, &t)?;
    picture_section(&mut out, r)?;
    big_pictures_section(&mut out, r)?;
    animations_section(&mut out, r)?;
    title_section(&mut out, title_menu.copied())?;
    full_screens_section(&mut out, r)?;
    let rest = Rest {
        r,
        db,
        slots,
        screens,
        t: &t,
        bs: &bs,
        model,
        faces: &faces,
    };
    rest.write(&mut out, &mut notes)?;
    custom_menu::section(&mut out, screens.get("custom_menus").unwrap_or(&Value::Null))?;
    skills_screen::section(&mut out, screens)?;
    out.push_str(&per_map.tables);
    timer_and_case(&mut out, r);
    Ok(Emitted {
        text: out,
        notes,
        report: per_map.report,
        frames: per_map.frames,
        raw: per_map.raw,
    })
}

fn window_section(out: &mut String, r: &Emit, windows: &[Value], t: &Geometry) -> Result<()> {
    // The window is a single one for the whole cartridge, in palette 0. That
    // the background does not step on it comes from the split —it starts at
    // `reserved`— but it is checked anyway: no single map's comparison
    // would see it.
    let reserved = cgram_reserved(r.window_colors);
    for m in &r.maps {
        let used = (m.cgram.len() / 2) as i64;
        let above = m.above_first * COLORS_PER_PALETTE as i64;
        if used + i64::from(reserved) > above {
            return Err(Bad::answer(format!(
                "the background of map {} uses {used} CGRAM entries from {reserved} and steps \
                 on the upper layer, which starts at {above}",
                m.id
            )));
        }
    }
    out.push_str("\n; --- the message window ---\n");
    // One window per System the cartridge switches between, the starting
    // one's with the plain labels: see `normalized_windows`. The background
    // of the text area goes as one line only if it is one in all of them,
    // because `prime_line` reads them all the same way.
    // How many: the runtime reads the pieces through `window_systems` only
    // when there are more than one —see `window_system.s`—.
    out.push_str(&format!("WINDOW_SYSTEMS = {}\n", windows.len()));
    let one_line = windows.iter().map(|w| backdrop_is_one_line(w, t)).collect::<Result<Vec<bool>>>()?.iter().all(|&b| b);
    for (k, w) in windows.iter().enumerate() {
        let suffix = if k == 0 { String::new() } else { format!("_{k}") };
        window_pieces(out, r, w, t, &suffix, one_line)?;
    }
    if windows.len() > 1 {
        window_systems_table(out, windows.len());
    }
    let window = &windows[0];
    line(out, &block("font_table", &bytes_at(window, "font")?));
    // How far each letter moves the line, and how far it paints: the
    // composer adds the first and checks the second against the edge.
    let small = |name: &str| -> Result<Vec<u8>> {
        Ok(ints_at(window, name)?.into_iter().map(|n| n as u8).collect())
    };
    line(out, &block("font_advance", &small("advances")?));
    line(out, &block("font_reach", &small("reach")?));

    for (phase, data) in list_at(window, "prerender")?.iter().enumerate() {
        line(
            out,
            &block(&format!("font_pre{phase}"), &crate::json::bytes(data)?),
        );
    }
    line(out, &block("messages", &r.messages));
    // How big it is and how big it can be, for `rm2k-snes-space`: the operand
    // of `OP_MESSAGE` is sixteen bits, in steps of `MESSAGES_STEP`.
    out.push_str(&pyf!(
        "MESSAGES_BYTES = %d\nMESSAGES_CAP = %d\n",
        r.messages.len(),
        0x10000 * MESSAGES_STEP
    ));
    // The pairs its letters are written with, for `message_tick`.
    line(out, &block("message_pairs", &r.message_pairs.table));
    out.push_str(&pyf!("MESSAGE_PAIR_FIRST = %d\n", r.message_pairs.first));
    message_faces(out, &r.faces)?;
    Ok(())
}

/// The bytes one face of the message window takes in the cartridge: its 36
/// 4bpp tiles and its fifteen colour words. `FACE_BYTES` in the runtime's
/// `message_face.s`, which reads them.
pub const MESSAGE_FACE_BYTES: usize = 36 * 32 + 15 * 2;

/// The faces the message window shows, one block each —a block stays whole
/// in one bank, and all the faces together can be more than one—, and the
/// table of long pointers `OP_FACE` indexes, `message_face_ptr`. `faces.rs`
/// in `rm2k-snes-screens` says what each one holds.
fn message_faces(out: &mut String, faces: &[MessageFace]) -> Result<()> {
    out.push_str(&pyf!(
        "; The faces of the message window: `MESSAGE_FACES` of `MESSAGE_FACE_BYTES`\n\
         ; each, and a long pointer to each one. See the runtime's message_face.s.\n\
         MESSAGE_FACES = %d\nMESSAGE_FACE_BYTES = %d\n",
        faces.len(),
        MESSAGE_FACE_BYTES
    ));
    for (k, face) in faces.iter().enumerate() {
        if face.tiles.len() != 36 * 32 || face.palette.len() != 15 {
            return Err(Bad::answer(format!(
                "message face {k} has {} bytes of tiles and {} colours, not 1152 and 15",
                face.tiles.len(),
                face.palette.len()
            )));
        }
        let mut data = face.tiles.clone();
        data.extend(words_le(face.palette.iter().map(|&w| w as u32)));
        line(out, &block(&format!("message_face_{k}"), &data));
    }
    // The pointers, by hand: a word and a bank each, like `window_systems`.
    out.push_str(&format!(".block {}\nmessage_face_ptr:\n", (faces.len() * 3).max(1)));
    if faces.is_empty() {
        out.push_str("    .byte $FF\n");
    }
    for k in 0..faces.len() {
        out.push_str(&format!("    .word .loword(message_face_{k})\n    .byte ^message_face_{k}\n"));
    }
    out.push('\n');
    Ok(())
}

/// One System's message window: its tiles, its palette, its two planes of
/// cells for each window base, its arrow's cells, the text area's
/// background and the bar over it. `suffix` goes after every label: empty
/// for the System the cartridge starts with, `_k` for the `k`-th it
/// switches to.
fn window_pieces(out: &mut String, r: &Emit, window: &Value, t: &Geometry, suffix: &str, one_line: bool) -> Result<()> {
    let reserved = cgram_reserved(r.window_colors);
    line(out, &block(&format!("window_tiles{suffix}"), &bytes_at(window, "tiles")?));
    // Only the `reserved` at the bottom: from there up it is the
    // background's.
    let cgram = ints_at(window, "cgram")?;
    let words: Vec<u32> = cgram
        .iter()
        .take(reserved as usize)
        .map(|&w| w as u32)
        .collect();
    line(out, &block(&format!("window_cgram{suffix}"), &words_le(words)));
    // One layout of the cells per window base the VRAM layouts use, with
    // the upper layer's priority so it covers the hero and the events.
    //
    // Each one is two planes, one after the other, and the console stamps
    // both in the window's tilemap: the window as it is, and below it the
    // same window without its frame —`MessageOptions` without the
    // background—, where only the text cells remain and every other one is
    // cell 0, the BG2 tile that is blank in every map. Which one shows is
    // the scroll: see `msg_hdma_build` in the runtime.
    let text_base = int_at(window, "base")?;
    for (base, label) in WINDOW_BASES
        .iter()
        .zip(["window_cells", "window_cells_256"])
    {
        let label = format!("{label}{suffix}");
        let mut framed = Vec::new();
        let mut bare = Vec::new();
        for row in list_at(window, "cells")? {
            for c in ints(row)? {
                let cell =
                    entry(base + c as u32, false, false, PRIORITY_ABOVE) | (WINDOW_PALETTE << 10);
                framed.push(cell);
                bare.push(if c >= text_base { cell } else { 0 });
            }
        }
        framed.extend(bare);
        line(out, &block(&label, &words_le(framed)));
    }
    // The cells of the arrow of a message waiting for a key, per window base
    // in the order of `window_cells`: with the frame, off and on, and
    // without it, off and on. Off is what the window has there —its frame,
    // or cell 0 without it—. The console writes one of the four on the
    // plane the window shows: see `msg_arrow` in the runtime.
    let arrow = ints_at(window, "arrow")?;
    let arrow_row = t.n("WINDOW_ARROW_ROW") as usize;
    let arrow_col = t.n("WINDOW_ARROW_COL") as usize;
    let arrow_cells = t.n("WINDOW_ARROW_CELLS") as usize;
    if arrow.len() != 2 * arrow_cells {
        return Err(Bad::answer(format!(
            "the window's arrow has {} tiles and it takes {arrow_cells} cells, with the frame and \
             without it",
            arrow.len()
        )));
    }
    let window_rows = list_at(window, "cells")?;
    let under = match window_rows.get(arrow_row) {
        Some(row) => ints(row)?,
        None => vec![],
    };
    if under.len() < arrow_col + arrow_cells {
        return Err(Bad::answer(format!(
            "the window's arrow goes at row {arrow_row}, columns {arrow_col} to {}, and the \
             window has no cell there",
            arrow_col + arrow_cells - 1
        )));
    }
    let mut arrow_table = Vec::new();
    for base in WINDOW_BASES {
        let cell = |tile: i64| entry(base + tile as u32, false, false, PRIORITY_ABOVE) | (WINDOW_PALETTE << 10);
        for k in 0..arrow_cells {
            arrow_table.push(cell(under[arrow_col + k]));
        }
        for &tile in &arrow[..arrow_cells] {
            arrow_table.push(cell(tile));
        }
        arrow_table.extend(std::iter::repeat_n(0, arrow_cells));
        for &tile in &arrow[arrow_cells..] {
            arrow_table.push(cell(tile));
        }
    }
    line(out, &block(&format!("window_arrow_cells{suffix}"), &words_le(arrow_table)));
    // The text area's background, one line —two cell rows— after another,
    // which `prime_line` copies under each line before its letters. When
    // every line is the same —a window over one colour, `[windows.
    // background]`— only the first goes, and `prime_line` copies it under
    // all of them: a quarter of the bytes.
    let backdrop = bytes_at(window, "background")?;
    let line_bytes = (t.n("WINDOW_TEXT_COLS") * 2 * 32) as usize;
    let text_lines = (t.n("WINDOW_TEXT_ROWS") / 2) as usize;
    let lines: Vec<&[u8]> = backdrop.chunks(line_bytes).collect();
    let backdrop_lines = if one_line { 1 } else { text_lines };
    if suffix.is_empty() {
        out.push_str(&format!("WINDOW_BACKDROP_LINES = {backdrop_lines}\n"));
    }
    line(
        out,
        &block(&format!("window_backdrop{suffix}"), if one_line { lines[0] } else { &backdrop }),
    );
    // And the same background with the System's cursor on each line, and
    // one line's with the cursor over nothing: a choice's highlighted
    // option is composed over these. See `prime_line` in the runtime.
    line(out, &block(&format!("window_bar{suffix}"), &bytes_at(window, "bar")?));
    line(out, &block(&format!("window_bar_bare{suffix}"), &bytes_at(window, "bar_bare")?));
    Ok(())
}

/// Whether the text area's four lines have the same background: a window
/// over one colour, `[windows.background]`.
fn backdrop_is_one_line(window: &Value, t: &Geometry) -> Result<bool> {
    let backdrop = bytes_at(window, "background")?;
    let line_bytes = (t.n("WINDOW_TEXT_COLS") * 2 * 32) as usize;
    let text_lines = (t.n("WINDOW_TEXT_ROWS") / 2) as usize;
    let lines: Vec<&[u8]> = backdrop.chunks(line_bytes).collect();
    Ok(backdrop.len() == line_bytes * text_lines && lines.iter().all(|l| *l == lines[0]))
}

/// How many bytes a System's entry takes in `window_systems`: the eight
/// 24-bit pointers `window_select` copies to `WINDOW_NOW`, in the order of
/// `WS_TILES` and the rest in the runtime's `window_system.s`.
pub const WINDOW_SYSTEM_BYTES: usize = 24;

/// The table the runtime finds each System's window in: per System, in the
/// cartridge's order, a pointer to each of its pieces.
fn window_systems_table(out: &mut String, systems: usize) {
    out.push_str(&format!(
        "; The message window of each System, for `window_select`.\n\
         WINDOW_SYSTEM_BYTES = {WINDOW_SYSTEM_BYTES}\n\
         .block {}\nwindow_systems:\n",
        systems * WINDOW_SYSTEM_BYTES
    ));
    for k in 0..systems {
        let suffix = if k == 0 { String::new() } else { format!("_{k}") };
        for piece in [
            "window_tiles",
            "window_cgram",
            "window_cells",
            "window_cells_256",
            "window_arrow_cells",
            "window_backdrop",
            "window_bar",
            "window_bar_bare",
        ] {
            out.push_str(&format!("    .word .loword({piece}{suffix})\n    .byte ^{piece}{suffix}\n"));
        }
    }
    out.push('\n');
}

/// The starting System's window and those of the Systems the cartridge
/// switches to, all with the same tile numbers: the text area starts where
/// the largest frame ends —`WINDOW_TEXT_BASE` is one for the whole
/// cartridge— and a smaller frame is padded with blank tiles up to it. The
/// font's composed tables are the starting System's for all of them, so
/// each has to give the text the same entries: the screens stage laid them
/// out that way —see `text_rows` in `rm2k-snes-screens window`—, and this
/// checks it. With one System, its window as it came.
fn normalized_windows(window: &Value, others: &[Value]) -> Result<Vec<Value>> {
    if others.is_empty() {
        return Ok(vec![window.clone()]);
    }
    let mut all: Vec<Value> = vec![window.clone()];
    let mut base = int_at(window, "base")?;
    for o in others {
        let w = at(o, "window")?;
        base = base.max(int_at(w, "base")?);
        if (at(w, "color")?, at(w, "shadow")?) != (at(window, "color")?, at(window, "shadow")?) {
            return Err(Bad::answer(format!(
                "System {} gives the text other palette entries than the starting one: the \
                 font's tables are one for all of them",
                at(o, "system")?
            )));
        }
        all.push(w.clone());
    }
    for w in &mut all {
        let own = int_at(w, "base")?;
        let mut tiles = bytes_at(w, "tiles")?;
        tiles.resize(base as usize * 32, 0);
        let cells: Vec<Value> = list_at(w, "cells")?
            .iter()
            .map(|row| Ok(Value::from(ints(row)?.into_iter().map(|c| if c >= own { c - own + base } else { c }).collect::<Vec<i64>>())))
            .collect::<Result<_>>()?;
        w["tiles"] = Value::from(tiles.iter().map(|b| format!("{b:02x}")).collect::<String>());
        w["cells"] = Value::from(cells);
        w["base"] = Value::from(base);
    }
    Ok(all)
}

/// How many bytes a picture's entry takes in `picture_data`: see
/// [`picture_tables`].
pub const PICTURE_ENTRY: usize = 16;

/// The pictures each map carries, as the console reads them with
/// `lda f:picture_data, x`: `picture_maps` has a word per map, the offset of
/// its block in `picture_data`, or 0 if it carries none. A map's block is
///
/// ```text
///   word  the first tile of its sprite bank the pictures start at
///   byte  how many pictures
///   then PICTURE_ENTRY bytes per picture, in the bytecode's order:
///     word  half its width, in RM2k's pixels
///     word  half its height
///     byte  how many objects
///     byte  its sprite palette, counted from the top: 0 is palette 7
///     word  where its objects are: per object dx and dy from its corner,
///           and a word with its tile from the first one in the low nine
///           bits and bit 15 for an 8x8 object instead of a 32x32
///     word  where its sixteen colours are, entry 0 included: the
///           palette's, which the pictures that share it point to once
///     word  the first tile again, so drawing needs the entry alone
///     four bytes of nothing, so an entry is a shift away
/// ```
///
/// All in one `.block` each, so the offsets are sixteen bits and a colour
/// pointer never crosses a bank.
pub fn picture_tables(maps: &[crate::request::Map]) -> Result<(Vec<u8>, Vec<u8>)> {
    let mut data = vec![0u8];
    let mut starts = Vec::with_capacity(maps.len());
    for map in maps {
        let Some(p) = &map.pictures else {
            starts.push(0u16);
            continue;
        };
        let whose = |what: String| Bad::answer(format!("map {}: {what}", map.id));
        let start = data.len();
        let n = p.images.len();
        if n == 0 || n > 255 {
            return Err(whose(format!("{n} pictures")));
        }
        data.extend(u16::try_from(p.base).map_err(|_| whose(format!("pictures at tile {}", p.base)))?.to_le_bytes());
        data.push(n as u8);
        let entries = data.len();
        data.resize(entries + n * PICTURE_ENTRY, 0);
        // Each palette's colours once, by its index.
        let mut colors_of: std::collections::BTreeMap<i64, usize> = std::collections::BTreeMap::new();
        for (i, image) in p.images.iter().enumerate() {
            let objects_at = data.len() - start;
            for &[dx, dy, tile] in &image.objects {
                let byte = |v: i64| u8::try_from(v).map_err(|_| whose(format!("an object at {v}")));
                data.push(byte(dx)?);
                data.push(byte(dy)?);
                data.extend(u16::try_from(tile).map_err(|_| whose(format!("an object's tile {tile}")))?.to_le_bytes());
            }
            let colors_at = match colors_of.get(&image.palette_index) {
                Some(&at) => at,
                None => {
                    let at = data.len() - start;
                    let mut colors = vec![[0, 0, 0]];
                    colors.extend_from_slice(&image.palette);
                    colors.resize(16, [0, 0, 0]);
                    data.extend(cgram_bytes(&colors));
                    colors_of.insert(image.palette_index, at);
                    at
                }
            };
            let word = |v: i64| -> Result<[u8; 2]> {
                Ok(i16::try_from(v).map_err(|_| whose(format!("a picture's {v}")))?.to_le_bytes())
            };
            let palette = u8::try_from(image.palette_index)
                .ok()
                .filter(|&p| p < 8)
                .ok_or_else(|| whose(format!("sprite palette {} from the top", image.palette_index)))?;
            let at = entries + i * PICTURE_ENTRY;
            let mut entry = Vec::with_capacity(PICTURE_ENTRY);
            entry.extend(word(image.half[0])?);
            entry.extend(word(image.half[1])?);
            entry.push(u8::try_from(image.objects.len()).map_err(|_| whose("too many objects".into()))?);
            entry.push(palette);
            entry.extend(word((start + objects_at) as i64)?);
            entry.extend(word((start + colors_at) as i64)?);
            entry.extend(word(p.base)?);
            data[at..at + entry.len()].copy_from_slice(&entry);
        }
        starts.push(u16::try_from(start).map_err(|_| whose("the pictures' table passes 64 KB".into()))?);
    }
    Ok((words_le(starts.iter().map(|&s| u32::from(s))), data))
}

fn picture_section(out: &mut String, r: &Emit) -> Result<()> {
    out.push_str("\n; --- the ShowPicture pictures: see `picture_tables` in rm2k-snes-mapdata ---\n");
    out.push_str(&format!("PICTURE_ENTRY = {PICTURE_ENTRY}\n"));
    let (maps, data) = picture_tables(&r.maps)?;
    line(out, &block("picture_maps", &maps));
    line(out, &block("picture_data", &data));
    // The screen flash's products, `d * level // 31`, so the console does not
    // multiply and divide for each of its 96 entries every odd frame.
    let products: Vec<u8> = (0..32u32)
        .flat_map(|n| (0..32u32).map(move |d| (d * n / 31) as u8))
        .collect();
    line(out, &block("prod31_table", &products));
    Ok(())
}

/// The big pictures' tilemap is 32x32 cells to a screen, two screens: side
/// by side when the picture is as tall as the screen —the second one holds
/// the mirrored edges a wave scrolls into view—, one under the other when
/// it is taller. `BG1SC`'s size bits for each.
const BIG_SCREEN: usize = 32;
const BIG_WIDE: u8 = 1;
const BIG_TALL: u8 = 2;
/// How many columns of the edge the second screen mirrors on each side: the
/// strongest wave of the editor, 10, moves a line 32 of RM2k's pixels,
/// which is 25.6 of the console's.
const BIG_MIRRORED: usize = 4;
/// The palettes a big picture takes, always uploaded whole: the seven above
/// the window's: the same number as `BIG_PALETTES` in `runtime/big_picture.s`.
const BIG_PALETTES: usize = 7;
/// The bytes of an entry of `big_table`.
const BIG_ENTRY: usize = 32;
/// RM2k's screen and the console's, down: a picture's corner goes from one
/// to the other as `Screens::place` in rm2k-snes-images takes it.
const BIG_RM_HEIGHT: i64 = 240;
const BIG_CONSOLE_HEIGHT: i64 = 224;

/// A big picture's tilemap as VRAM holds it, and its `BG1SC` size bits.
///
/// As tall as the screen, the left screen is the picture and the right one
/// is what a wave brings into view past its sides: a line the wave moves
/// right shows the columns left of 0 —the right screen's last ones— and one
/// it moves left the ones right of 31. In RM2k that is the picture's own
/// pixels if it is `wider` than the screen —`GTest4`—, and nothing
/// otherwise —`ShipFlash`—. The console has no room for the first: it
/// carries the picture's edges mirrored, so the edge goes on the way it was
/// going instead of jumping to the other side, and with no tile of its own,
/// since a tile flipped is the same tile.
pub fn big_tilemap(rows: usize, cells: &[u16], wider: bool) -> Result<(Vec<u16>, u8)> {
    let flip = |e: u16| if e == 0 { 0 } else { e ^ 0x4000 };
    let at = |r: usize, c: usize| cells[r * BIG_SCREEN + c];
    if cells.len() != rows * BIG_SCREEN {
        return Err(Bad::answer(format!(
            "a big picture's tilemap has {} cells for {rows} rows of {BIG_SCREEN}",
            cells.len()
        )));
    }
    if rows > 2 * BIG_SCREEN {
        return Err(Bad::answer(format!("a big picture of {rows} rows: the tilemap holds 64")));
    }
    let mut map = vec![0u16; 2 * BIG_SCREEN * BIG_SCREEN];
    if rows > BIG_SCREEN {
        map[..cells.len()].copy_from_slice(cells);
        return Ok((map, BIG_TALL));
    }
    let side = BIG_SCREEN * BIG_SCREEN;
    for r in 0..rows {
        for c in 0..BIG_SCREEN {
            map[r * BIG_SCREEN + c] = at(r, c);
        }
        if !wider {
            continue;
        }
        for j in 0..BIG_MIRRORED {
            map[side + r * BIG_SCREEN + j] = flip(at(r, BIG_SCREEN - 1 - j));
            map[side + r * BIG_SCREEN + BIG_SCREEN - 1 - j] = flip(at(r, j));
        }
    }
    Ok((map, BIG_WIDE))
}

/// `big_table`, an entry of `BIG_ENTRY` bytes per big picture, and their
/// streams:
///
/// ```text
///   long  its tiles, raw
///   long  its tilemap, an LZ2 stream of 4 KB
///   long  its colours, BIG_PALETTES × 16 words, raw
///   word  the tiles' bytes
///   byte  BG1SC's size bits
///   word  BG1VOFS with the screen's top at the canvas's: the rows above
///         it, minus the line the PPU skips
///   word  half its height, in RM2k's pixels
///   word  its top on the console's screen, where it was drawn
///   long  its mode 7 texture's tiles, raw: 64 bytes each, the first blank
///   long  the rows of its map, raw: 128 bytes each, as many as the layer's
///   word  the texture's bytes, 0 if it has none
///   word  its map rows' bytes
///   word  the texture's point the zoom shrinks it towards: x
///   word  and y, the layer's row: the screen's, plus the rows above it
/// ```
///
/// The last six are a picture's that a `MovePicture` zooms —see
/// `big_picture.s`—, and zero for any other, as all were until then. The
/// texture goes raw for the same reason as the tiles: its map is mostly
/// zeros, but it goes up a piece per vblank, straight from the cartridge.
///
/// The last two are what `OP_BIG_MOVE` needs to scroll it: the corner it
/// goes to is computed by the console from the centre and the half height,
/// against where it was drawn.
///
/// **The tiles go raw**, and are sent to VRAM by DMA straight from the
/// cartridge. Decompressing them was most of the black frames a picture
/// costs —30 KB of LZ2, and the bytecode a page carries from another map,
/// which lives in the same buffer and had to be decompressed again after—,
/// and the montage of map 217 changes picture every six frames. They are
/// photos, which LZ2 hardly shrinks. The tilemap does go compressed: it is
/// mostly empty, and its 4 KB fit in the buffer below the carried bytecode.
///
/// See `big_picture.s` in the runtime.
fn big_pictures_section(out: &mut String, r: &Emit) -> Result<()> {
    out.push_str("\n; --- the big pictures: see `big_pictures_section` in rm2k-snes-mapdata ---\n");
    out.push_str(&format!(
        "BIG_PICTURES = {}\nBIG_ENTRY = {BIG_ENTRY}\n",
        r.big_pictures.len()
    ));
    if r.big_pictures.is_empty() {
        line(out, &block("big_table", &[0]));
        return Ok(());
    }
    let mut raw: Vec<Vec<u8>> = Vec::new();
    let mut sizes = Vec::new();
    for big in &r.big_pictures {
        let (map, size) = big_tilemap(big.rows, &big.tilemap, big.wider)?;
        raw.push(map.iter().flat_map(|w| w.to_le_bytes()).collect());
        sizes.push(size);
    }
    let refs: Vec<&[u8]> = raw.iter().map(Vec::as_slice).collect();
    let streams = crate::compress::compress_many(&refs)?;
    out.push_str(&format!(".block {}\nbig_table:\n", BIG_ENTRY * r.big_pictures.len()));
    for (k, big) in r.big_pictures.iter().enumerate() {
        let vofs = (-big.top - 1) as i16 as u16;
        let corner =
            ((big.center[1] - big.half[1]) * BIG_CONSOLE_HEIGHT).div_euclid(BIG_RM_HEIGHT);
        out.push_str(&format!(
            "    .word .loword(big_tiles_{k})\n    .byte ^big_tiles_{k}\n\
             \x20   .word .loword(big_map_{k})\n    .byte ^big_map_{k}\n\
             \x20   .word .loword(big_colors_{k})\n    .byte ^big_colors_{k}\n\
             \x20   .word {}\n    .byte {}\n    .word {vofs}\n\
             \x20   .word {}\n    .word {}\n",
            big.tiles.len(),
            sizes[k],
            big.half[1] as i16 as u16,
            corner as i16 as u16
        ));
        match &big.mode7 {
            None => out.push_str("    .res 14\n"),
            Some(t) => {
                let rows = big.rows * BIG_M7_ROW;
                out.push_str(&format!(
                    "    .word .loword(big_m7_tiles_{k})\n    .byte ^big_m7_tiles_{k}\n\
                     \x20   .word .loword(big_m7_rows_{k})\n    .byte ^big_m7_rows_{k}\n\
                     \x20   .word {}\n    .word {rows}\n    .word {}\n    .word {}\n",
                    t.tiles.len(),
                    t.center[0] as i16 as u16,
                    (t.center[1] - big.top) as i16 as u16,
                ));
            }
        }
    }
    out.push('\n');
    for (k, big) in r.big_pictures.iter().enumerate() {
        if big.palettes.len() > BIG_PALETTES {
            return Err(Bad::answer(format!(
                "big picture {k} has {} palettes and the layer takes {BIG_PALETTES}",
                big.palettes.len()
            )));
        }
        let mut colors = Vec::with_capacity(BIG_PALETTES * 32);
        for p in 0..BIG_PALETTES {
            for i in 0..16 {
                let c = big.palettes.get(p).and_then(|p| p.get(i)).copied().unwrap_or([0, 0, 0]);
                colors.extend(cgram_word(c).to_le_bytes());
            }
        }
        // The tiles go whole through `big_dma_vram`, and the tilemap is an
        // LZ2 stream: both may travel in the `.msu`, and a picture is shown
        // with the screen off. See `msu_block`.
        let msu = r.rom.msu != MsuData::Optional;
        line(out, &msu_block(&format!("big_tiles_{k}"), &big.tiles, msu));
        line(out, &msu_block(&format!("big_map_{k}"), &streams[k], msu));
        line(out, &block(&format!("big_colors_{k}"), &colors));
        if let Some(t) = &big.mode7 {
            let (tiles, rows) = big_mode7(big.rows, t)?;
            line(out, &block(&format!("big_m7_tiles_{k}"), &tiles));
            line(out, &block(&format!("big_m7_rows_{k}"), &rows));
        }
    }
    Ok(())
}

/// A row of mode 7's map: 128 tiles, of which a layer takes the first 32.
const BIG_M7_ROW: usize = 128;
/// The most tiles mode 7's map names, each a byte a pixel.
const BIG_M7_TILES: usize = 256;
const BIG_M7_TILE: usize = 64;

/// A big picture's mode 7 texture as the cartridge carries it: its tiles,
/// and its map's rows as VRAM's low bytes take them, padded to 128.
pub fn big_mode7(rows: usize, t: &crate::request::Mode7Texture) -> Result<(Vec<u8>, Vec<u8>)> {
    if t.tiles.len() % BIG_M7_TILE != 0 || t.tiles.len() > BIG_M7_TILES * BIG_M7_TILE {
        return Err(Bad::answer(format!(
            "a mode 7 texture of {} bytes: it holds {BIG_M7_TILES} tiles of {BIG_M7_TILE}",
            t.tiles.len()
        )));
    }
    if t.map.len() != rows * BIG_SCREEN {
        return Err(Bad::answer(format!(
            "a mode 7 texture's map has {} cells for {rows} rows of {BIG_SCREEN}",
            t.map.len()
        )));
    }
    let mut map = vec![0u8; rows * BIG_M7_ROW];
    for r in 0..rows {
        map[r * BIG_M7_ROW..r * BIG_M7_ROW + BIG_SCREEN]
            .copy_from_slice(&t.map[r * BIG_SCREEN..(r + 1) * BIG_SCREEN]);
    }
    Ok((t.tiles.clone(), map))
}

/// A battle animation's frame as the cartridge stores it: only the tiles
/// that are not all zero, each with its number in front, and `$FF`.
fn frame_without_gaps(data: &[u8], tiles: usize) -> Vec<u8> {
    let mut out = Vec::new();
    for tile in 0..tiles {
        let one = &data[tile * 32..(tile + 1) * 32];
        if one.iter().any(|&b| b != 0) {
            out.push(tile as u8);
            out.extend_from_slice(one);
        }
    }
    out.push(0xFF);
    out
}

fn animations_section(out: &mut String, r: &Emit) -> Result<()> {
    let a = &r.animations;
    let mut list: Vec<&crate::request::BattleAnimation> = a.list.iter().collect();
    list.sort_by_key(|x| x.number);
    let cap = list.last().map_or(1, |x| x.number + 1);
    let mut lines: Vec<String> = vec![
        "\n; --- the drawing of the battle animations ---".into(),
        ";".into(),
        "; The box is a single one for the whole ROM and the reason is in".into(),
        "; tools/port/animation.py: four 32x32 objects in one row of blocks".into(),
        "; of the name grid, which is the most that fits in the sprite VRAM".into(),
        "; map 2 has left free. What changes per map is where that row lands".into(),
        "; and with which palette, and that goes in `anim_battle_split`,".into(),
        "; one byte per map.".into(),
        format!("ANIM_B_BOX    = {}", a.side),
        format!("ANIM_B_OBJ    = {}", a.obj),
        format!("ANIM_B_OBJECTS = {}", a.objects),
        format!("ANIM_B_TILES  = {}", a.tiles),
        format!("ANIM_B_BYTES  = {}", a.tiles * 32),
        "ANIM_B_STRIDE = 8".into(),
        "; How high an animation number `anim_battle` reaches: the bytecode".into(),
        "; carries the RM2k number as is and a larger one isn't in the table,".into(),
        "; so the ROM compares it before reading it.".into(),
        format!("ANIM_B_MAX    = {cap}"),
        "; The center of the screen, which is where the ones with scope".into(),
        "; `Scope_screen` land: `DrawAt(screen_width / 2, screen_height / 2)`.".into(),
        format!("ANIM_B_CENTER_X = {}", a.screen[0] / 2),
        format!("ANIM_B_CENTER_Y = {}", a.screen[1] / 2),
        format!("ANIM_B_NO       = ${ANIM_NO_DRAWING:02X}"),
        format!("ANIM_B_SCREEN = ${ANIM_TARGET_SCREEN:02X}"),
    ];
    let slot_of: HashMap<i64, usize> = list
        .iter()
        .enumerate()
        .map(|(k, x)| (x.number, k))
        .collect();
    let numbered: Vec<u8> = (0..cap)
        .map(|n| slot_of.get(&n).map_or(0xFF, |&k| k as u8))
        .collect();
    lines.push(block("anim_battle", &numbered));
    let mut table = Vec::new();
    let mut first = 0usize;
    for x in &list {
        // The anchor with `Animation::Position`'s shift already in it.
        let [ax, ay] = x.anchor;
        table.extend_from_slice(&[
            x.frames.len() as u8,
            (ax & 0xFF) as u8,
            (ay & 0xFF) as u8,
            0,
            (first & 0xFF) as u8,
            (first >> 8) as u8,
            0,
            0,
        ]);
        first += x.frames.len();
    }
    lines.push(block("anim_battle_table", &table));
    let mut cgram = Vec::new();
    for x in &list {
        let mut colors = vec![[0u8, 0, 0]];
        colors.extend_from_slice(&x.palette);
        colors.resize(colors.len().max(COLORS_PER_PALETTE), [0, 0, 0]);
        cgram.extend(cgram_bytes(&colors));
    }
    lines.push(block("anim_battle_cgram", &cgram));
    // The pointers, declared with `.block` like the page table's: the
    // console reads it with a 24-bit pointer. Each frame is an LZ2 stream,
    // which `anim_frame_build` decompresses when the frame is due: one
    // frame at a time and not the whole animation, so that starting one
    // does not stop the map for frames while a big one decompresses.
    let mut pointers = vec![
        format!(".block {}", 4 * first),
        "anim_battle_frames:".to_string(),
    ];
    let mut frames: Vec<Vec<u8>> = Vec::new();
    for x in &list {
        for (k, frame) in x.frames.iter().enumerate() {
            pointers.push(format!("    .dword anim_battle_{}_{k}", x.number));
            frames.push(frame_without_gaps(frame, a.tiles as usize));
        }
    }
    lines.push(pointers.join("\n"));
    // Where they land: two places, one for the frame being built and one for
    // the previous one, whose tiles are erased first. The largest a frame
    // can be is every tile of the box with its number, and the `$FF`.
    lines.push(format!(
        "ANIM_B_FRAME_MAX = {}",
        (a.tiles as usize) * 33 + 1
    ));
    let refs: Vec<&[u8]> = frames.iter().map(Vec::as_slice).collect();
    let mut streams = crate::compress::compress_many(&refs)?.into_iter();
    for x in &list {
        for k in 0..x.frames.len() {
            let stream = streams.next().expect("one stream per frame");
            lines.push(block(&format!("anim_battle_{}_{k}", x.number), &stream));
        }
    }
    // Per map, where and with which palette it is drawn: bit 7 "drawn
    // here", the 64-tile block and the palette, three bits each.
    let split: Vec<u8> = r
        .maps
        .iter()
        .map(|m| {
            let (base, pal) = m
                .sprite
                .as_ref()
                .and_then(|s| s.animation.as_ref())
                .map_or((0, 0), |a| (a.base, a.palette));
            if base != 0 {
                (0x80 | ((base / 64) << 3) | pal) as u8
            } else {
                0
            }
        })
        .collect();
    lines.push(block("anim_battle_split", &split));
    out.push_str(&lines.join("\n"));
    out.push('\n');
    Ok(())
}

fn title_section(out: &mut String, menu: Option<&Value>) -> Result<()> {
    out.push_str("\n; --- the title screen ---\n");
    match menu {
        None => {
            line(out, &block("title_menu_tiles", &[0]));
            line(out, &block("title_menu_cells", &[0]));
        }
        Some(menu) => {
            // A 4-bit tile bank and one tilemap per selected option, one after
            // the other, first the ones without a save and then the ones with:
            // the console indexes them by multiplying.
            line(
                out,
                &block("title_menu_tiles", &packed(&tiles(at(menu, "tiles")?)?, 4)),
            );
            let mut plane = Vec::new();
            for tilemap in list_at(menu, "tilemaps")? {
                plane.extend(cell_words(&ints(tilemap)?, PRIORITY_ABOVE));
            }
            line(out, &block("title_menu_cells", &plane));
        }
    }
    Ok(())
}

fn full_screens_section(out: &mut String, r: &Emit) -> Result<()> {
    out.push_str("\n; --- the full screens ---\n");
    out.push_str(&pyf!(
        "GAME_OVER_TILES = %d\n",
        r.game_over.as_ref().map_or(0, |g| g.tiles)
    ));
    let mut rows = Vec::new();
    if let Some(g) = &r.game_over {
        rows.push(("GAME_OVER", "game_over_lz2", g));
    }
    if let Some(t) = &r.title {
        rows.push(("TITLE", "title_lz2", t));
    }
    // Its stream is not marked as one that may go to the `.msu`, like none
    // of these: it is what the ROM shows when there is no `.msu`.
    if let Some(m) = &r.msu_missing {
        rows.push(("MSU_MISSING", "msu_missing_lz2", m));
    }
    if rows.is_empty() {
        line(out, &block("screens_table", &[0]));
        return Ok(());
    }
    out.push_str(
        "; Each screen's row in `screens_table`: where its stream is,\n\
         ; how many bytes of tiles and colors it brings, and from which\n\
         ; CGRAM color they go. See `screen_upload`.\n\
         SCREEN_ROW = 8\n",
    );
    for (number, (name, _, _)) in rows.iter().enumerate() {
        out.push_str(&format!("SCREEN_{name} = {number}\n"));
    }
    out.push_str(&format!(".block {}\nscreens_table:\n", 8 * rows.len()));
    for (_, label, data) in &rows {
        out.push_str(&pyf!(
            "    .word .loword(%s)\n    .byte ^%s\n    .word %d, %d\n    .byte %d\n",
            *label,
            *label,
            data.tiles * data.bpp * 8,
            data.colors * 2,
            data.first_color
        ));
    }
    out.push('\n');
    for (_, label, data) in &rows {
        line(out, &block(label, &data.stream));
    }
    Ok(())
}

/// What goes after the full screens: the slots screen, the menus and the
/// text screens, the equipment, the battle, the troops and the scene, and
/// the tables of bank 0.
struct Rest<'a> {
    r: &'a Emit,
    db: &'a Db,
    slots: &'a Value,
    screens: &'a Value,
    t: &'a Geometry<'a>,
    bs: &'a Geometry<'a>,
    model: &'a Value,
    faces: &'a BTreeMap<i64, &'a Value>,
}

impl Rest<'_> {
    fn write(&self, out: &mut String, _notes: &mut Vec<String>) -> Result<()> {
        let (r, db, slots, t) = (self.r, self.db, self.slots, self.t);
        let screens = self.screens;
        let cell = CELL;
        let cols = COLS;
        // --- the slots screen, in every cartridge: the save point opens it
        // from inside the game.
        out.push_str("\n; --- the slots screen ---\n");
        line(
            out,
            &block("slot_tiles", &packed(&tiles(at(slots, "tiles")?)?, 4)),
        );
        // The font precomposed for the bank's text palette, a table per
        // phase: the names are composed with it —`tl_strip`—.
        for (phase, data) in list_at(slots, "prerender")?.iter().enumerate() {
            line(out, &block(&format!("slot_pre{phase}"), &crate::json::bytes(data)?));
        }
        // Each cell block with its own label, named by a pointer table. The
        // bank of the slots and the menu goes with the priority bit set: the
        // actor choice turns on BG1, which at priority 0 would cover BG2.
        let mut slot_blocks: Vec<String> = Vec::new();
        for (mode, cells) in list_at(slots, "headers")?.iter().enumerate() {
            let name = format!("slot_hdr_{mode}");
            line(out, &block(&name, &cell_words(&ints(cells)?, 1)));
            slot_blocks.push(name);
        }
        // Two per slot, empty and full: the cursor is the System's, on BG1
        // —`slot_bar_cells`, below—.
        for (number, row) in list_at(slots, "rows")?.iter().enumerate() {
            for full in 0..2 {
                let name = format!("slot_{number}_{full}");
                let cells = &list(row)?[full];
                line(out, &block(&name, &cell_words(&ints(cells)?, 1)));
                slot_blocks.push(name);
            }
        }
        // Per actor that can join the party, its face.
        let mut face_block: BTreeMap<i64, usize> = BTreeMap::new();
        for (actor, cells) in self.faces {
            let name = format!("slot_face_{actor}");
            line(out, &block(&name, &cell_words(&ints(cells)?, 1)));
            face_block.insert(*actor, slot_blocks.len());
            slot_blocks.push(name);
        }
        // The pause menu's: each command in its two variants, the coin, and
        // a party row's text.
        let menu = at(slots, "menu")?;
        let menu_option_block = slot_blocks.len();
        for (order, variants) in list_at(menu, "options")?.iter().enumerate() {
            for (disabled, cells) in list(variants)?.iter().enumerate() {
                let name = format!("menu_option_{order}_{disabled}");
                line(out, &block(&name, &cell_words(&ints(cells)?, 1)));
                slot_blocks.push(name);
            }
        }
        let menu_currency_block = slot_blocks.len();
        line(
            out,
            &block("menu_currency", &cell_words(&ints_at(menu, "currency")?, 1)),
        );
        slot_blocks.push("menu_currency".into());
        let menu_row_block = slot_blocks.len();
        line(
            out,
            &block("menu_row", &cell_words(&ints_at(menu, "row")?, 1)),
        );
        slot_blocks.push("menu_row".into());

        // The text screens' inks: a palette per colour, all with the same
        // layout, and the font precomposed for it, a table per phase —see
        // `text_layer.s`—. Until 2026-10-03 this was a font bank, each
        // letter in two cells.
        let inks = at(screens, "text_inks")?;
        for (phase, data) in list_at(inks, "prerender")?.iter().enumerate() {
            line(out, &block(&format!("scr_pre{phase}"), &crate::json::bytes(data)?));
        }
        let item_palettes: Vec<Vec<Color>> = list_at(inks, "palettes")?
            .iter()
            .map(colors)
            .collect::<Result<_>>()?;
        let up = t.n("ITEM_UP") as usize;
        line(
            out,
            &block(
                "items_cgram",
                &palettes_cgram(&item_palettes[..up.min(item_palettes.len())]),
            ),
        );
        line(
            out,
            &block(
                "item_cgram_uploads",
                &palettes_cgram(&item_palettes[up.min(item_palettes.len())..]),
            ),
        );
        // The windows of the item and equipment screens, on BG1.
        let border = at(screens, "items_border")?;
        let border_tiles = tiles(at(border, "tiles")?)?;
        let border_colors = colors(at(border, "colors")?)?;
        let maps = list_at(border, "maps")?;
        let (border_map, border_bars) = (&list(&maps[0])?[0], &list(&maps[0])?[1]);
        let (eq_map, eq_bars) = (&list(&maps[1])?[0], &list(&maps[1])?[1]);
        let words =
            |v: &Value| -> Result<Vec<u8>> { Ok(words_le(ints(v)?.into_iter().map(|w| w as u32))) };
        let bars = |v: &Value| -> Result<Vec<u8>> {
            let mut all = Vec::new();
            for bar in list(v)? {
                all.extend(words(bar)?);
            }
            Ok(all)
        };
        line(out, &block("items_border_tiles", &packed(&border_tiles, 8)));
        line(out, &block("items_border_map", &words(border_map)?));
        line(out, &block("items_border_bars", &bars(border_bars)?));
        line(out, &block("eq_border_map", &words(eq_map)?));
        line(out, &block("eq_border_bars", &bars(eq_bars)?));
        line(
            out,
            &block("items_border_cgram", &cgram_bytes(&border_colors)),
        );
        // The battle's windows, on BG1 at 8bpp in the cells the scene does
        // not take: see `battle.rs` in `rm2k-snes-screens`. Per layout its
        // band's rows, and per layout and set the bars, sixteen records of
        // six bytes —row, column, rows, columns, the first word in
        // `ba_win_patches`— with ten for set A, five for set B and one of
        // padding; a record of no rows is no bar.
        let bw = at(screens, "battle_windows")?;
        let bw_tiles = tiles(at(bw, "tiles")?)?;
        let bw_colors = colors(at(bw, "colors")?)?;
        line(out, &block("ba_win_tiles", &packed(&bw_tiles, 8)));
        line(out, &block("ba_win_cgram", &cgram_bytes(&bw_colors)));
        let mut band = Vec::new();
        for layout in list_at(bw, "band")? {
            band.extend(words(layout)?);
        }
        line(out, &block("ba_win_band", &band));
        line(out, &block("ba_win_help", &words(at(bw, "help")?)?));
        line(out, &block("ba_win_patches", &words(at(bw, "patches")?)?));
        let mut records = Vec::new();
        for sets in list_at(bw, "bars")? {
            let sets = list(sets)?;
            for (set, room) in [(0, 10), (1, 6)] {
                let bars = list(&sets[set])?;
                if bars.len() > room {
                    return Err(Bad::answer(format!("a battle layout has {} bars in a set of {room}", bars.len())));
                }
                for k in 0..room {
                    match bars.get(k) {
                        Some(b) => {
                            let b = ints(b)?;
                            records.extend([b[0] as u8, b[1] as u8, b[2] as u8, b[3] as u8]);
                            records.extend((b[4] as u16 * 2).to_le_bytes());
                        }
                        None => records.extend([0u8; 6]),
                    }
                }
            }
        }
        line(out, &block("ba_win_bars", &records));
        out.push_str(&pyf!(
            "BA_WIN_TILES      = %d\nBA_WIN_FIRST      = %d\nBA_WIN_CGRAM      = %d\nBA_WIN_COLORS     = %d\n\
             BA_WIN_BAND_ROW   = %d\nBA_WIN_BAND_ROWS  = %d\nBA_WIN_HELP_ROWS  = %d\n",
            bw_tiles.len(),
            int_at(bw, "first")?,
            int_at(bw, "cgram")?,
            bw_colors.len(),
            int_at(bw, "band_row")?,
            list(&list_at(bw, "band")?[0])?.len() / 32,
            list(at(bw, "help")?)?.len() / 32
        ));
        // The shop windows, on BG1 with their own base.
        let shop = at(screens, "shop_border")?;
        let ti_tiles = tiles(at(shop, "tiles")?)?;
        let ti_colors = colors(at(shop, "colors")?)?;
        line(out, &block("ti_border_tiles", &packed(&ti_tiles, 8)));
        line(out, &block("ti_border_cgram", &cgram_bytes(&ti_colors)));
        let mut rows_words = Vec::new();
        for f in list_at(shop, "rows")? {
            rows_words.extend(ints(f)?);
        }
        line(
            out,
            &block(
                "ti_border_rows",
                &words_le(rows_words.iter().map(|&w| w as u32)),
            ),
        );
        line(
            out,
            &block("ti_border_patches", &words(at(shop, "patches")?)?),
        );
        let ti_map = t.n("TI_MAP");
        let mut stretches: Vec<i64> = Vec::new();
        let mut layer_stretches: Vec<i64> = Vec::new();
        for layer in list_at(shop, "layers")? {
            layer_stretches.push(2 * stretches.len() as i64);
            for s in list(layer)? {
                let s = ints(s)?;
                let (row, origin, how_many) = (s[0], s[1], s[2]);
                stretches.extend([ti_map + row * cols, origin * 2 * cols, how_many * 2 * cols]);
            }
            stretches.extend([0, 0, 0]);
        }
        line(
            out,
            &block(
                "ti_stretches",
                &words_le(stretches.iter().map(|&w| w as u32)),
            ),
        );
        line(
            out,
            &block(
                "ti_layer_stretches",
                &words_le(layer_stretches.iter().map(|&w| w as u32)),
            ),
        );
        let mut ti_bars = Vec::new();
        let mut base_bars = vec![0i64];
        for layer in list_at(shop, "bars")? {
            let layer = list(layer)?;
            for b in layer {
                let b = ints(b)?;
                let (row, col, rows, width, origin) = (b[0], b[1], b[2], b[3], b[4]);
                ti_bars.extend([ti_map + row * cols + col, 2 * origin, 2 * width, rows]);
            }
            base_bars.push(base_bars[base_bars.len() - 1] + layer.len() as i64);
        }
        line(
            out,
            &block("ti_bars", &words_le(ti_bars.iter().map(|&w| w as u32))),
        );
        let base_bytes: Vec<u8> = base_bars[..base_bars.len() - 1]
            .iter()
            .map(|&b| b as u8)
            .collect();
        line(out, &block("ti_bar_base", &base_bytes));
        let modes: Vec<u8> = ints(t.v("TI_LAYER_OF_MODE"))?
            .into_iter()
            .map(|b| b as u8)
            .collect();
        line(out, &block("ti_layer_mode", &modes));
        out.push_str(&pyf!(
            "TI_BORDER_VRAM    = $%04X\nTI_BORDER_MAP     = $%04X\nTI_BORDER_TILES   = %d\n\
             TI_BORDER_COLORS  = %d\nTI_BORDER_UP      = %d\n",
            t.n("TI_VRAM"),
            ti_map,
            ti_tiles.len(),
            ti_colors.len(),
            int_at(shop, "top")?
        ));
        // The shop's party: each possible member's three front frames,
        // twelve 4bpp tiles each, behind a pointer per member; its palette in
        // colour and in grey, sixteen colours each with the transparent one
        // first; which member each actor is; and the System's sixteen arrows
        // with their palette. See `party.rs` in `rm2k-snes-screens`.
        out.push_str("\n; --- the shop's party: see shop_party.s ---\n");
        let party = at(screens, "shop_party")?;
        let mut party_k = Vec::new();
        let mut party_pointers = Vec::new();
        let mut party_cgram = Vec::new();
        let palette16 = |colors: &[Color]| {
            let mut sixteen = vec![[0u8; 3]];
            sixteen.extend_from_slice(colors);
            sixteen.resize(16, [0, 0, 0]);
            cgram_bytes(&sixteen)
        };
        let mut members: Vec<(i64, i64)> = Vec::new();
        // Two actors drawn with the same CharSet share it: in A Blurred Line
        // there are two Kershes and three with the same sheet's index.
        let mut stored: Vec<(Vec<u8>, Vec<u8>)> = Vec::new();
        for m in list_at(party, "members")? {
            let actor = int_at(m, "actor")?;
            if m.get("frames").is_none() {
                continue;
            }
            let mut frames = Vec::new();
            for f in list_at(m, "frames")? {
                frames.extend(tiles(f)?);
            }
            let bytes = packed(&frames, 4);
            let mut cgram = palette16(&colors(at(m, "colors")?)?);
            cgram.extend(palette16(&colors(at(m, "greys")?)?));
            if let Some(k) = stored.iter().position(|s| s.0 == bytes && s.1 == cgram) {
                members.push((actor, k as i64));
                continue;
            }
            let k = stored.len() as i64;
            let label = format!("ti_party_tiles_{k}");
            line(out, &block(&label, &bytes));
            party_pointers.push(format!("    .byte {}", crate::asm::pointer(&label)));
            party_cgram.extend(&cgram);
            stored.push((bytes, cgram));
            members.push((actor, k));
        }
        if members.len() > 255 {
            return Err(Bad::answer(format!("the shop's party has {} members with a CharSet and a byte names 255", members.len())));
        }
        let n_party_actors = members.iter().map(|&(a, _)| a + 1).max().unwrap_or(1);
        for a in 0..n_party_actors {
            party_k.push(members.iter().find(|&&(b, _)| b == a).map_or(0xFF, |&(_, k)| k as u8));
        }
        line(out, &block("ti_party_k", &party_k));
        line(out, &format!(".block {}\nti_party_ptr:", 3 * party_pointers.len().max(1)));
        if party_pointers.is_empty() {
            line(out, "    .byte 0, 0, 0");
        }
        for p in &party_pointers {
            line(out, p);
        }
        if party_cgram.is_empty() {
            party_cgram.push(0);
        }
        line(out, &block("ti_party_cgram", &party_cgram));
        let arrows = tiles(at(party, "arrows")?)?;
        line(out, &block("ti_arrow_tiles", &packed(&arrows, 4)));
        line(out, &block("ti_arrow_cgram", &palette16(&colors(at(party, "arrow_colors")?)?)));
        let party_tile0 = int_at(party, "tile0")?;
        // The whole OAM the shop opens with: each member's twelve objects,
        // three across by four down with palette `i` over every layer, the
        // four arrows and the rest below the screen, and the high table at
        // zero —x below 256, all small—. See `ti_party_open`.
        let mut oam = Vec::new();
        let hidden = |oam: &mut Vec<u8>| oam.extend([0, 224, 0, 0]);
        for i in 0..t.n("TI_PARTY_MEMBERS") {
            for j in 0..12 {
                oam.push((t.n("TI_PARTY_X0") + t.n("TI_PARTY_STEP") * i + 8 * (j % 3)) as u8);
                oam.push((t.n("TI_PARTY_Y0") + 8 * (j / 3)) as u8);
                oam.push((party_tile0 + 12 * i + j) as u8);
                oam.push((0x30 | (i << 1)) as u8);
            }
        }
        while oam.len() < 512 {
            hidden(&mut oam);
        }
        oam.resize(544, 0);
        line(out, &block("ti_party_oam", &oam));
        out.push_str(&pyf!(
            "TI_PARTY_ACTORS   = %d\nTI_PARTY_TILE0    = %d\nTI_PARTY_VRAM     = $%04X\n\
             TI_ARROW_TILE0    = %d\nTI_ARROW_VRAM     = $%04X\nTI_PARTY_MEMBERS  = %d\n\
             TI_PARTY_X0       = %d\nTI_PARTY_Y0       = %d\nTI_PARTY_STEP     = %d\n\
             TI_ARROW_DX       = %d\nTI_ARROW_DY       = %d\nTI_PARTY_RATE     = %d\n\
             TI_FRAME_TILES    = %d\nTI_FRAME_COLS     = %d\nTI_ARROW_FRAMES   = %d\n\
             TI_ARROW_UP       = %d\nTI_ARROW_SAME     = %d\nTI_ARROW_DOWN     = %d\n\
             TI_ARROW_EQUIPPED = %d\nTI_LAYER_BUY      = %d\nTI_PARTY_ON       = %d\n",
            n_party_actors,
            party_tile0,
            t.n("TI_VRAM") + party_tile0 * 16,
            party_tile0 + t.n("TI_PARTY_MEMBERS") * 12,
            t.n("TI_VRAM") + (party_tile0 + t.n("TI_PARTY_MEMBERS") * 12) * 16,
            t.n("TI_PARTY_MEMBERS"),
            t.n("TI_PARTY_X0"),
            t.n("TI_PARTY_Y0"),
            t.n("TI_PARTY_STEP"),
            t.n("TI_ARROW_DX"),
            t.n("TI_ARROW_DY"),
            t.n("TI_PARTY_RATE"),
            12,
            3,
            t.n("TI_ARROW_FRAMES"),
            t.n("TI_ARROW_UP"),
            t.n("TI_ARROW_SAME"),
            t.n("TI_ARROW_DOWN"),
            t.n("TI_ARROW_EQUIPPED"),
            t.n("TI_LAYER_BUY"),
            party.get("on").and_then(|v| v.as_bool()).unwrap_or(true) as i64
        ));
        out.push_str("; --- the shop's party ends ---\n");
        // The End Game screen, whole: the "Yes" palette first.
        let end = at(screens, "end_game")?;
        let end_tiles = tiles(at(end, "tiles")?)?;
        let end_rows = ints_at(end, "rows")?;
        let end_palettes: Vec<Vec<Color>> = list_at(end, "palettes")?
            .iter()
            .map(colors)
            .collect::<Result<_>>()?;
        line(out, &block("end_tiles", &packed(&end_tiles, 4)));
        line(
            out,
            &block("end_map", &words_le(end_rows.iter().map(|&w| w as u32))),
        );
        line(out, &block("end_cgram", &palettes_cgram(&end_palettes)));
        let ramp: Vec<u8> = ints(t.v("END_RAMP"))?
            .into_iter()
            .map(|b| b as u8)
            .collect();
        line(out, &block("end_ramp", &ramp));
        out.push_str(&pyf!(
            "END_TILES   = %d\nEND_ROW0    = %d\nEND_ROWS    = %d\nEND_ENTERS  = %d\nEND_NO      = %d\n\
             END_FRAMES = %d\nEND_STEP_SONG = %d\n",
            end_tiles.len(),
            int_at(end, "row0")?,
            (end_rows.len() as i64).div_euclid(cols),
            t.n("END_DEFAULT_CHOICE"),
            t.n("END_NO"),
            t.n("END_FADE_FRAMES"),
            fade_step(t.n("END_SONG_FADE_MS"))
        ));

        // The texts the text screens compose, by index.
        let mut texts = Texts {
            data: Vec::new(),
            offsets: Vec::new(),
            first: t.n("ITEM_FIRST_CHAR") as usize,
            count: t.n("ITEM_CHARS") as usize,
        };
        let textos = at(screens, "texts")?;
        for item in list_at(textos, "items")? {
            for text in list_at(item, "texts")? {
                texts.add(crate::json::text(text)?);
            }
        }
        // Dead texts after the item ones and before the others, so the
        // battle's indices go past 255 in a small cartridge: an item's name is
        // named by `3k`, so they cannot go in front of the items.
        for _ in 0..r.text_padding {
            texts.offsets.push((0, 0));
        }
        let param_text: Vec<i64> = list_at(textos, "params")?
            .iter()
            .map(|t| Ok(texts.add(text(t)?)))
            .collect::<Result<_>>()?;
        let slot_text: Vec<i64> = list_at(textos, "equipment")?
            .iter()
            .map(|t| Ok(texts.add(text(t)?)))
            .collect::<Result<_>>()?;
        let mut actor_text: HashMap<i64, i64> = HashMap::new();
        // The renamed actors too, who may never join: a message's `\N[n]`
        // writes the name from here. See the runtime's `actor_names.s`.
        for &a in r.actors.iter().chain(r.names.iter().map(|(a, _)| a)) {
            if actor_text.contains_key(&a) {
                continue;
            }
            let name = &db
                .actor(a as i32)
                .map_err(|b| Bad::answer(b.message().to_string()))?
                .name;
            actor_text.insert(a, texts.add(&plain(name)));
        }
        // And each rename's, in the order `OP_CHANGE_NAME` counts them.
        let name_text: Vec<i64> = r.names.iter().map(|(_, name)| texts.add(&plain(name))).collect();
        let mut shop_text = None;
        for messages in list_at(textos, "shop")? {
            for lines in list(messages)? {
                for l in list(lines)? {
                    let k = texts.add(text(l)?);
                    shop_text.get_or_insert(k);
                }
            }
        }
        let owned_text = texts.add(text_at(textos, "owned")?);
        let carried_text = texts.add(text_at(textos, "carried")?);
        let currency_text = texts.add(text_at(textos, "currency")?);
        // The battle's: the LDB's terms —the three commands already trimmed,
        // the victory split as the stage checked it fits— and the rest.
        let model = self.model;
        let mtexts = at(model, "texts")?;
        let victory: Vec<String> = list_at(mtexts, "victory")?
            .iter()
            .map(|v| Ok(text(v)?.to_string()))
            .collect::<Result<_>>()?;
        let mut battle_text = None;
        for (name, liblcf) in BATTLE_TERMS {
            let value = match name {
                "attack" | "defend" | "escape" => text_at(mtexts, name)?.to_string(),
                "victory" => victory[0].clone(),
                _ => term(db, liblcf)?,
            };
            let k = texts.add(&plain(&value));
            battle_text.get_or_insert(k);
        }
        let battle_text = battle_text.unwrap_or(0);
        let revived_text = texts.add(text_at(mtexts, "revived")?);
        let dead_text = texts.add(text_at(mtexts, "dead")?);
        let victory2_text = texts.add(victory.get(1).map_or("", String::as_str));
        let rom_enemies = ints_at(model, "enemies")?;
        let enemy_names = at(mtexts, "enemies")?;
        let mut enemy_text = HashMap::new();
        for &e in &rom_enemies {
            enemy_text.insert(e, texts.add(text_at(enemy_names, &e.to_string())?));
        }
        let actions = at(model, "actions")?;
        let rom_skills = ints_at(model, "skills")?;
        let skill_texts = at(mtexts, "skills")?;
        let mut skill_text = HashMap::new();
        for &h in &rom_skills {
            skill_text.insert(
                h,
                texts.add(text_at(at(skill_texts, &h.to_string())?, "name")?),
            );
        }
        let mut skill_desc_text = HashMap::new();
        for &h in &rom_skills {
            skill_desc_text.insert(
                h,
                texts.add(text_at(at(skill_texts, &h.to_string())?, "description")?),
            );
        }
        // An item's description whole, for the battle's help window, which
        // has one line: the item screens split it in two, `3k + 1` and `3k +
        // 2`. Only the items the battle offers; the others point to text 0.
        let item_battle = list_at(model, "item_battle")?;
        let item_list = list_at(textos, "items")?;
        if item_battle.len() != item_list.len() {
            return Err(Bad::answer("the battle's items and the screens' are not the same list"));
        }
        let mut item_desc_battle = Vec::new();
        for (item, battle) in item_list.iter().zip(item_battle) {
            if battle.as_bool().unwrap_or(false) {
                let lines = list_at(item, "texts")?;
                let whole: Vec<&str> = lines[1..]
                    .iter()
                    .map(text)
                    .collect::<Result<Vec<_>>>()?
                    .into_iter()
                    .filter(|l| !l.is_empty())
                    .collect();
                item_desc_battle.push(texts.add(&whole.join(" ")));
            } else {
                item_desc_battle.push(0);
            }
        }
        let skill = |h: i64| {
            db.skill(h as i32)
                .map_err(|b| Bad::answer(b.message().to_string()))
        };
        let taught = ints_at(model, "taught")?;
        let mut whole_skill_text = HashMap::new();
        for &h in &taught {
            whole_skill_text.insert(h, texts.add(&skill(h)?.name));
        }
        let mut skill_msg1_text = HashMap::new();
        for &h in &rom_skills {
            skill_msg1_text.insert(h, texts.add(&skill(h)?.using_message1));
        }
        let mut skill_msg2_text = HashMap::new();
        for &h in &rom_skills {
            skill_msg2_text.insert(h, texts.add(&skill(h)?.using_message2));
        }
        let commands = at(mtexts, "skill_commands")?;
        let mut skill_command_text = HashMap::new();
        for &a in &r.actors {
            skill_command_text.insert(a, texts.add(text_at(commands, &a.to_string())?));
        }
        // The conditions' two battle messages, by LDB number —see
        // `battle_states.s`—: the one said while it lasts and the one said
        // when it goes. The empty ones, which are most, share one text.
        // **They are the last texts**, with the empty one first: the ones
        // before keep the numbers they had before 2026-10-12, which is what
        // `tests/python.rs` holds.
        let empty_text = texts.add("");
        let states_n = db.states.keys().max().map_or(1, |&m| m.max(0) as usize + 1);
        let mut state_affected_text = vec![empty_text; states_n];
        let mut state_recovery_text = vec![empty_text; states_n];
        for (&id, st) in &db.states {
            let Ok(k) = usize::try_from(id) else { continue };
            for (message, out) in [
                (&st.message_affected, &mut state_affected_text),
                (&st.message_recovery, &mut state_recovery_text),
            ] {
                if !message.is_empty() {
                    out[k] = texts.add(message);
                }
            }
        }
        // The skills screen's level term, since 2026-10-12: after the
        // conditions', for the same reason they go last.
        let level_text = texts.add(&term(db, "lvl_short")?);
        out.push_str(&format!("SK_TXT_LEVEL = {level_text}\n"));
        let item_texts = if texts.data.is_empty() {
            vec![0]
        } else {
            texts.data.clone()
        };
        line(out, &block("item_texts", &item_texts));
        if slot_blocks.len() > 255 {
            return Err(Bad::answer(format!(
                "the slots screen has {} blocks and the tables that name them are one byte",
                slot_blocks.len()
            )));
        }
        // The palette, padded to the sixteen the console uploads at once.
        let slot_palettes: Vec<Vec<Color>> = list_at(slots, "palettes")?
            .iter()
            .map(colors)
            .collect::<Result<_>>()?;
        line(out, &block("slot_cgram", &palettes_cgram(&slot_palettes)));

        // The tables that name the cell blocks: outside bank 0, read with
        // `lda f:slot_block_lo, x`, because they grow with every face.
        out.push_str("\n.segment \"RODATA\"\n");
        for (field, prefix) in [("lo", "<"), ("hi", ">"), ("bk", "^")] {
            out.push_str(&format!(
                ".block {}\nslot_block_{field}:\n       .byte {}\n",
                slot_blocks.len(),
                slot_blocks
                    .iter()
                    .map(|e| format!("{prefix}{e}"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        // Where each row goes in the tilemap: in bank 0.
        out.push_str("\n.segment \"TABLES\"\n");
        let row_of: Vec<i64> = (0..i64::from(SLOTS))
            .map(|n| {
                i64::from(SLOT_MAP) + (t.n("SLOT_Y") + n * t.n("SLOT_STEP")).div_euclid(cell) * 32
            })
            .collect();
        out.push_str(&format!(
            "slot_vram:\n      .word {}\n",
            decimal(row_of.iter()).join(", ")
        ));
        let faces_max = t.n("FACES_MAX");
        let face_vram: Vec<i64> = (0..SLOTS as usize)
            .flat_map(|n| {
                let row = row_of[n];
                let (col, step) = (t.n("FACE_COL"), t.n("FACE_STEP"));
                (0..4).map(move |place| {
                    if place < faces_max {
                        row + col + place * step
                    } else {
                        0
                    }
                })
            })
            .collect();
        out.push_str(&format!(
            "slot_face_vram:\n      .word {}\n",
            decimal(face_vram).join(", ")
        ));
        let name_vram: Vec<i64> = row_of
            .iter()
            .map(|r| r + t.n("NAME_ROW") * 32 + t.n("NAME_COL"))
            .collect();
        out.push_str(&format!(
            "slot_name_vram:\n        .word {}\n",
            decimal(name_vram).join(", ")
        ));
        // A renamed actor that never joins has its row too: a message's
        // `\N[n]` and the slot screen look its name up there.
        let n_actors_slots = face_block
            .keys()
            .copied()
            .chain(r.actors.iter().copied())
            .chain(r.names.iter().map(|(a, _)| *a))
            .max()
            .unwrap_or(-1)
            .max(-1)
            + 1;
        let face_blocks: Vec<String> = (0..n_actors_slots)
            .map(|a| face_block.get(&a).map_or(0xFF, |&b| b as i64).to_string())
            .collect();
        // By actor id: outside bank 0, read with `lda f:slot_face_block, x`,
        // because it grows with every actor.
        out.push_str(".segment \"RODATA\"\n");
        bytes_asm(out, "slot_face_block", &face_blocks, true);
        out.push_str(".segment \"TABLES\"\n");
        // The pause menu: its blocks, and where each thing goes, in words.
        let vram_cell = |row: i64, col: i64| i64::from(SLOT_MAP) + row * 32 + col;
        // The custom menus' options go after RM2k's five, as commands 5 and
        // on, and the column has a row for each: see `menu_rows_build`.
        let custom = screens.get("custom_menus").filter(|c| !c.is_null());
        let custom_n = match custom {
            Some(c) => list_at(c, "labels")?.len() as i64,
            None => 0,
        };
        let option_rows: Vec<i64> = (0..t.n("MENU_OPTIONS") + custom_n)
            .map(|n| (t.n("MENU_OPT_Y") + n * t.n("MENU_OPT_STEP")).div_euclid(cell))
            .collect();
        out.push_str(&pyf!(
            "MENU_OPTIONS      = %d\nMENU_EQUIPMENT    = %d\nMENU_SAVE         = %d\nMENU_END          = %d\n\
             MENU_BLK_OPTION   = %d\nMENU_BLK_CURRENCY = %d\nMENU_BLK_ROW      = %d\nMENU_OPT_COLS     = %d\n\
             MENU_CURRENCY_COLS = %d\nMENU_CURRENCY_VRAM = %d\nMENU_ACTOR_COLS   = %d\nMENU_ACTOR_ROWS   = %d\n\
             MENU_ROWS_PARTY   = %d\nMENU_ACTORS_N     = %d\nMENU_HP_DIGITS    = %d\nMENU_HP_OFS       = %d\n\
             MENU_FACE_CELLS   = %d\nMENU_NAME_COLS    = %d\nMENU_NAME_OFS = %d\nMENU_LEVEL_OFS    = %d\n\
             MENU_MAX_DIGITS   = %d\nMENU_MAX_OFS      = %d\n",
            t.n("MENU_OPTIONS"),
            t.n("MENU_EQUIPMENT"),
            t.n("MENU_SAVE"),
            t.n("MENU_END"),
            menu_option_block,
            menu_currency_block,
            menu_row_block,
            t.n("MENU_OPT_COLS"),
            t.n("MENU_CURRENCY_COLS"),
            vram_cell(t.n("MENU_GOLD_Y").div_euclid(cell), t.n("MENU_CURRENCY_COL")),
            t.n("MENU_ACTOR_COLS"),
            t.n("MENU_ACTOR_ROWS"),
            t.n("MENU_PARTY_ROWS"),
            n_actors_slots,
            t.n("MENU_HP_DIGITS"),
            t.n("MENU_HP_ROW") * 32 + t.n("MENU_HP_COL") - t.n("MENU_ACTOR_COL"),
            t.n("FACE_CELLS"),
            t.n("MENU_NAME_COLS"),
            t.n("MENU_NAME_ROW") * 32 + t.n("MENU_NAME_COL") - t.n("MENU_ACTOR_COL"),
            t.n("MENU_LEVEL_ROW") * 32 + t.n("MENU_LEVEL_COL") - t.n("MENU_ACTOR_COL"),
            t.n("MENU_MAX_DIGITS"),
            t.n("MENU_HP_ROW") * 32 + t.n("MENU_MAX_COL") - t.n("MENU_ACTOR_COL")
        ));
        out.push_str(&format!(
            "MENU_CUSTOM = {custom_n}\nMENU_ROWS_MAX = {}\n",
            t.n("MENU_OPTIONS") + custom_n
        ));
        let done: BTreeSet<i64> = ints(t.v("MENU_DONE"))?.into_iter().collect();
        out.push_str(&format!(
            "menu_done:\n     .byte {}\n",
            (0..t.n("MENU_OPTIONS") + custom_n)
                .map(|n| if done.contains(&n) || n >= t.n("MENU_OPTIONS") { "1" } else { "0" })
                .collect::<Vec<_>>()
                .join(", ")
        ));
        out.push_str(&format!(
            "menu_option_vram:\n    .word {}\n",
            decimal(
                option_rows
                    .iter()
                    .map(|&f| vram_cell(f, t.n("MENU_OPT_COL")))
            )
            .join(", ")
        ));
        out.push_str(&format!(
            "menu_row_vram:\n     .word {}\n",
            decimal(
                (0..t.n("MENU_PARTY_ROWS"))
                    .map(|r| vram_cell(r * t.n("MENU_ACTOR_ROWS"), t.n("MENU_ACTOR_COL")))
            )
            .join(", ")
        ));
        // What the screen composes on the fly goes outside bank 0: it is read
        // with `lda f:`. The glyphs are indexed by character, and the ones
        // this cartridge does not use stay in the empty cell.
        out.push_str(".segment \"RODATA\"\n");
        // Where the command cursor and the slot cursor start on BG1, per
        // command and per slot: their rectangles on the first one, which
        // `alone` in `rm2k-snes-screens` cut, moved down by whole cells.
        let target = at(screens, "target")?;
        let bg1_cell = |row: i64, col: i64| t.n("TARGET_MAP") + row * 32 + col;
        let cmd_at = ints_at(target, "menu_cmd_at")?;
        let cmd_vram: Vec<String> = (0..t.n("MENU_OPTIONS") + custom_n)
            .map(|n| bg1_cell(cmd_at[0] + n * t.n("MENU_OPT_STEP").div_euclid(cell), cmd_at[2]).to_string())
            .collect();
        words_asm(out, "menu_cursor_vram", &cmd_vram, true);
        let slot_at = ints_at(target, "slot_bar_at")?;
        let slot_bar_vram: Vec<String> = (0..i64::from(SLOTS))
            .map(|n| bg1_cell(slot_at[0] + n * t.n("SLOT_STEP").div_euclid(cell), slot_at[2]).to_string())
            .collect();
        words_asm(out, "slot_bar_vram", &slot_bar_vram, true);
        let empty = format!(
            "${:04X}, ${:04X}",
            entry(0, false, false, 0),
            entry(0, false, false, 0)
        );
        let glyphs = at(menu, "glyphs")?;
        let first = t.n("ITEM_FIRST_CHAR");
        let chars = t.n("ITEM_CHARS");
        let mut glyph_cells = Vec::new();
        for n in first..first + chars {
            let letter = char::from_u32(n as u32).unwrap_or('?').to_string();
            glyph_cells.push(match glyphs.get(&letter) {
                Some(cells) => hex4(
                    ints(cells)?
                        .into_iter()
                        .map(|c| i64::from(entry(c as u32, false, false, 1))),
                )
                .join(", "),
                None => empty.clone(),
            });
        }
        out.push_str(&format!(
            ".block {}\nslot_glyph_cells:\n        .word {}\n",
            chars * 4,
            glyph_cells.join(", ")
        ));
        let exp_term = ints_at(menu, "exp_term")?;
        out.push_str(&format!(
            ".block {}\nmenu_exp_finished:\n    .word {}\n",
            2 * exp_term.len(),
            hex4(
                exp_term
                    .into_iter()
                    .map(|c| i64::from(entry(c as u32, false, false, 0)))
            )
            .join(", ")
        ));
        // The actor choice: its windows on BG1, a single tilemap and the bar
        // only where it changes; and each medicine's name in two lines.
        let target = at(screens, "target")?;
        let obj_tiles = tiles(at(target, "tiles")?)?;
        let obj_colors = colors(at(target, "colors")?)?;
        line(out, &block("target_tiles", &packed(&obj_tiles, 8)));
        line(out, &block("target_map", &words(at(target, "map")?)?));
        line(out, &block("target_bars", &bars(at(target, "bars")?)?));
        line(
            out,
            &block("menu_bar_cells", &words(at(target, "menu_bar")?)?),
        );
        let bar_at = ints_at(target, "menu_bar_at")?;
        out.push_str(&pyf!(
            "MENU_BAR_ROW0 = %d\nMENU_BAR_ROWS = %d\nMENU_BAR_COL0 = %d\nMENU_BAR_COLS = %d\n",
            bar_at[0],
            bar_at[1],
            bar_at[2],
            bar_at[3]
        ));
        // The pause menu's command cursor and the slot cursor, each on its
        // first row and over nothing, like the bar: see `alone` in
        // `rm2k-snes-screens`.
        for (cells, at_key, name, prefix) in [
            ("menu_cmd", "menu_cmd_at", "menu_cmd_cells", "MENU_CMD"),
            ("slot_bar", "slot_bar_at", "slot_bar_cells", "SLOT_BAR"),
        ] {
            line(out, &block(name, &words(at(target, cells)?)?));
            let bar_at = ints_at(target, at_key)?;
            out.push_str(&format!(
                "{prefix}_ROW0 = {}\n{prefix}_ROWS = {}\n{prefix}_COL0 = {}\n{prefix}_COLS = {}\n",
                bar_at[0], bar_at[1], bar_at[2], bar_at[3]
            ));
        }
        line(out, &block("target_cgram", &cgram_bytes(&obj_colors)));
        // The same choice for a skill: the cost's term over the count's,
        // and the bar over the whole party as its distinct cell rows and,
        // per party size, which goes on each row. See
        // `compact_target_skill` in `rm2k-snes-screens`.
        let skill = at(target, "skill")?;
        let term_at = ints_at(skill, "term_at")?;
        let all_at = ints_at(skill, "all_at")?;
        line(out, &block("target_term", &words(at(skill, "term")?)?));
        line(out, &block("target_all_rows", &bars(at(skill, "all_rows")?)?));
        let mut all_index = Vec::new();
        for which in list_at(skill, "all")? {
            all_index.extend(ints(which)?.into_iter().map(|k| k as u8));
        }
        line(out, &block("target_all", &all_index));
        out.push_str(&pyf!(
            "TARGET_TERM_ROW0 = %d\nTARGET_TERM_ROWS = %d\nTARGET_TERM_COL0 = %d\nTARGET_TERM_COLS = %d\n\
             TARGET_ALL_ROW0 = %d\nTARGET_ALL_ROWS = %d\nTARGET_ALL_COL0 = %d\nTARGET_ALL_COLS = %d\n",
            term_at[0],
            term_at[1],
            term_at[2],
            term_at[3],
            all_at[0],
            all_at[1],
            all_at[2],
            all_at[3]
        ));
        let mut medicine_lines: HashMap<i64, String> = HashMap::new();
        for m in list_at(textos, "medicines")? {
            let lines: Vec<String> = list_at(m, "lines")?
                .iter()
                .map(|l| Ok(text(l)?.to_string()))
                .collect::<Result<_>>()?;
            medicine_lines.insert(int_at(m, "number")?, lines.concat());
        }
        let medicines: Vec<i64> = r
            .items
            .iter()
            .copied()
            .filter(|n| medicine_lines.contains_key(n))
            .collect();
        if medicines.len() > 255 {
            return Err(Bad::answer(format!(
                "{} medicines don't fit in `target_name`",
                medicines.len()
            )));
        }
        let target_name: Vec<u8> = r
            .items
            .iter()
            .map(|n| {
                medicines
                    .iter()
                    .position(|m| m == n)
                    .map_or(0xFF, |k| k as u8)
            })
            .collect();
        line(out, &block("target_name", &target_name));
        let names: Vec<u8> = medicines
            .iter()
            .flat_map(|n| {
                medicine_lines[n]
                    .chars()
                    .map(|c| if c.is_ascii() { c as u8 } else { b'?' })
            })
            .collect();
        line(out, &block("target_names", &names));
        out.push_str(&pyf!(
            "TARGET_VRAM       = $%04X\nTARGET_MAP        = $%04X\nTARGET_TILES      = %d\n\
             TARGET_CGRAM      = %d\nTARGET_COLORS     = %d\nTARGET_NAME_WIDTH = %d\n\
             TARGET_NAME_VRAM = %d\nTARGET_COUNT_VRAM = %d\nTARGET_BAR_ROW0 = %d\n\
             TARGET_BAR_ROWS = %d\nTARGET_BAR_COL0 = %d\nTARGET_BAR_COLS = %d\n",
            t.n("TARGET_VRAM"),
            t.n("TARGET_MAP"),
            obj_tiles.len(),
            t.n("TARGET_CGRAM"),
            obj_colors.len(),
            t.n("TARGET_NAME_WIDTH"),
            vram_cell(t.n("TARGET_NAME_ROW"), t.n("TARGET_NAME_COL")),
            vram_cell(t.n("TARGET_COUNT_ROW"), t.n("TARGET_COUNT_COL")),
            int_at(target, "row0")?,
            int_at(target, "rows")?,
            int_at(target, "col0")?,
            int_at(target, "cols")?
        ));
        out.push_str(&pyf!(
            "MENU_EXP_X        = %d\nMENU_EXP_NUM_X    = %d\nMENU_EXP_Y        = %d\nMENU_EXP_STEP     = %d\n\
             MENU_EXP_DIGITS   = %d\nMENU_EXP_LETTERS  = %d\nMENU_ACTOR_HEIGHT = %d\n",
            t.n("MENU_EXP_X"),
            t.n("MENU_EXP_X") + t.n("MENU_EXP_NUM_DX") - t.n("GLYPH_DX"),
            t.n("MENU_EXP_Y") - t.n("GLYPH_DY"),
            t.n("FONT_WIDTH"),
            t.n("MENU_EXP_DIGITS"),
            t.n("MENU_EXP_LETTERS"),
            t.n("MENU_ACTOR_ROWS") * cell
        ));
        // Each actor's text, in ASCII: the name with trailing spaces, the
        // two digits of the level and max HP, in one row per actor.
        if (SLOT_TEXT_LEVEL as i64) < t.n("MENU_NAME_COLS")
            || SLOT_TEXT_LEVEL as i64 + t.n("LEVEL_DIGITS") + t.n("MENU_MAX_DIGITS")
                > SLOT_TEXT_WIDTH as i64
        {
            return Err(Bad::answer(format!(
                "the actor's three strips don't fit in the {SLOT_TEXT_WIDTH} bytes of its row"
            )));
        }
        let actor_strips = list_at(textos, "actors")?;
        let mut strip: Vec<u8> = Vec::new();
        for a in 0..n_actors_slots {
            let three = list(&actor_strips[a as usize])?;
            let row = format!(
                "{:<w$}{}{}",
                text(&three[0])?,
                text(&three[1])?,
                text(&three[2])?,
                w = SLOT_TEXT_LEVEL as usize
            );
            strip.extend(format!("{row:<w$}", w = SLOT_TEXT_WIDTH as usize).bytes());
        }
        // And after the actors' rows, one per rename, with its name alone:
        // the menu and the slot screen take it instead of the actor's own
        // when the actor carries it. See the runtime's `actor_names.s`.
        // Absent in a screens' answer from before 2026-10-15: none.
        let none = Vec::new();
        let renamed = match textos.get("renamed") {
            Some(v) => list(v)?,
            None => &none,
        };
        if renamed.len() != r.names.len() {
            return Err(Bad::answer(format!(
                "the screens wrote {} renamed names and the request has {}",
                renamed.len(),
                r.names.len()
            )));
        }
        for pair in renamed {
            let row = format!("{:<w$}", text(&list(pair)?[1])?, w = SLOT_TEXT_WIDTH as usize);
            strip.extend(row.bytes());
        }
        if n_actors_slots as usize + r.names.len() > 256 {
            return Err(Bad::answer(format!(
                "{} actors' rows and {} renames don't fit in the byte the runtime counts rows with",
                n_actors_slots,
                r.names.len()
            )));
        }
        let mut renamed_actors: Vec<i64> = Vec::new();
        for (a, _) in &r.names {
            if !renamed_actors.contains(a) {
                renamed_actors.push(*a);
            }
        }
        out.push_str(&format!(
            "; The actors some ChangeHeroName renames, in the order of their\n\
             ; first rename: each one's place is its byte of ACTOR_NAME. And the\n\
             ; row of slot_actor_text the first rename's name is in.\n\
             NAME_SLOTS = {}\nSLOT_TEXT_ROWS = {n_actors_slots}\n",
            renamed_actors.len()
        ));
        words_asm(out, "name_actor", &decimal(renamed_actors.iter().copied()), true);
        out.push_str(&format!(
            ".block {}\nslot_actor_text:\n        .byte {}\n",
            strip.len().max(1),
            if strip.is_empty() {
                "0".to_string()
            } else {
                decimal(strip.iter()).join(", ")
            }
        ));
        out.push_str(".segment \"TABLES\"\n");
        self.items_and_battle(
            out,
            &mut texts,
            ItemTexts {
                param_text,
                slot_text,
                actor_text,
                name_text,
                shop_text: shop_text.unwrap_or(0),
                owned_text,
                carried_text,
                currency_text,
                battle_text,
                revived_text,
                dead_text,
                victory2_text,
                victory_lines: victory.len(),
                enemy_text,
                skill_text,
                skill_desc_text,
                item_desc_battle,
                whole_skill_text,
                skill_msg1_text,
                skill_msg2_text,
                skill_command_text,
                state_affected_text,
                state_recovery_text,
                rom_enemies,
                rom_skills,
                actions,
                border_tiles: border_tiles.len(),
                border_colors: border_colors.len(),
            },
        )
    }
}

/// What the first half wrote that the second names.
struct ItemTexts<'a> {
    param_text: Vec<i64>,
    slot_text: Vec<i64>,
    actor_text: HashMap<i64, i64>,
    /// Each rename's text, in the order `OP_CHANGE_NAME` counts them.
    name_text: Vec<i64>,
    shop_text: i64,
    owned_text: i64,
    carried_text: i64,
    currency_text: i64,
    battle_text: i64,
    revived_text: i64,
    dead_text: i64,
    victory2_text: i64,
    victory_lines: usize,
    enemy_text: HashMap<i64, i64>,
    skill_text: HashMap<i64, i64>,
    skill_desc_text: HashMap<i64, i64>,
    item_desc_battle: Vec<i64>,
    whole_skill_text: HashMap<i64, i64>,
    skill_msg1_text: HashMap<i64, i64>,
    skill_msg2_text: HashMap<i64, i64>,
    skill_command_text: HashMap<i64, i64>,
    state_affected_text: Vec<i64>,
    state_recovery_text: Vec<i64>,
    rom_enemies: Vec<i64>,
    rom_skills: Vec<i64>,
    actions: &'a Value,
    border_tiles: usize,
    border_colors: usize,
}

impl Rest<'_> {
    /// The conditions, one row per LDB number from 0 —which is nobody's—,
    /// outside bank 0: what `battle_states.s` does with them. Every one of
    /// the database's goes, and not only the ones the troop pages give: the
    /// tables are a byte a field, and the bytecode names them by number.
    fn states(&self, out: &mut String, x: &ItemTexts) -> Result<()> {
        let db = self.db;
        let n = x.state_affected_text.len();
        if n > 256 {
            return Err(Bad::answer(format!(
                "{} conditions do not fit in OP_MONSTER_STATE's byte",
                n - 1
            )));
        }
        let per = |f: &dyn Fn(&ditto::schema::State) -> i64| -> Vec<String> {
            decimal((0..n).map(|k| {
                db.states
                    .get(&(k as i32))
                    .map_or(0, |st| f(st).clamp(0, 255))
            }))
        };
        out.push_str(&format!("STATES_N = {n}
"));
        bytes_asm(out, "state_priority", &per(&|st| st.priority.into()), true);
        bytes_asm(
            out,
            "state_restrict",
            &per(&|st| st.restriction.to_i32().into()),
            true,
        );
        bytes_asm(out, "state_hold", &per(&|st| st.hold_turn.into()), true);
        bytes_asm(out, "state_auto", &per(&|st| st.auto_release_prob.into()), true);
        bytes_asm(out, "state_damage", &per(&|st| st.release_by_damage.into()), true);
        bytes_asm(out, "state_hit", &per(&|st| st.reduce_hit_ratio.into()), true);
        // Which parameters it halves, one bit each in the order of
        // `BA_ATK`, `BA_DEF`, `BA_SPI`, `BA_AGI`.
        bytes_asm(
            out,
            "state_halves",
            &per(&|st| {
                i64::from(st.affect_attack)
                    | i64::from(st.affect_defense) << 1
                    | i64::from(st.affect_spirit) << 2
                    | i64::from(st.affect_agility) << 3
            }),
            true,
        );
        words_asm(out, "state_affected", &decimal(x.state_affected_text.iter()), true);
        words_asm(out, "state_recovery", &decimal(x.state_recovery_text.iter()), true);
        Ok(())
    }
}

fn bad(b: rm2k_snes_battle::Bad) -> Bad {
    Bad::answer(b.message().to_string())
}

impl Rest<'_> {
    fn items_and_battle(&self, out: &mut String, texts: &mut Texts, x: ItemTexts) -> Result<()> {
        let (r, db, t) = (self.r, self.db, self.t);
        let cell = CELL;
        let items = &r.items;
        // A `k` is a word, and the runtime indexes the tables with it in a
        // sixteen-bit X: the widest one, `item_up`, at `12k`. RM2k's editor
        // stops at 5000 items, below this.
        if items.len() * 12 > 0x10000 {
            return Err(Bad::answer(format!(
                "{} items: `item_up` is indexed by 12k in sixteen bits",
                items.len()
            )));
        }
        let item = |n: i64| db.item(n as i32).map_err(bad);
        let k_of: HashMap<i64, usize> = items.iter().enumerate().map(|(k, &n)| (n, k)).collect();
        out.push_str(&pyf!(
            "ITEMS_ROM         = %d\nITEMS_CGRAM_N     = %d\nITEM_ROWS         = %d\n\
             ITEM_CURSOR_COL   = %d\nITEM_NAME_COL     = %d\nITEM_DIGITS_COL   = %d\nITEM_LIST_POS     = %d\n\
             ITEM_FIRST_CHAR = %d\nSCR_TEXT_X        = %d\nSCR_TEXT_Y        = %d\n\
             ITEM_BORDER_VRAM  = $%04X\nITEM_BORDER_TILES = %d\n\
             ITEM_BORDER_MAP   = $%04X\nITEM_BORDER_CGRAM = %d\nITEM_BORDER_COLORS = %d\nITEM_BORDER_ROWS  = %d\n\
             ITEM_BORDER_LIST  = %d\n",
            items.len(),
            t.n("ITEM_UP") * MENU_CGRAM as i64,
            t.n("ITEM_ROWS"),
            t.n("ITEM_CURSOR_COL"),
            t.n("ITEM_NAME_COL"),
            t.n("ITEM_DIGITS_COL"),
            t.n("ITEM_LIST_Y").div_euclid(cell) * 64,
            t.n("ITEM_FIRST_CHAR"),
            t.n("SCR_TEXT_X"),
            t.n("SCR_TEXT_Y"),
            i64::from(SLOT_VRAM) + int_at(self.screens, "items_border_first")? * 32,
            x.border_tiles,
            t.n("ITEM_BORDER_MAP"),
            t.n("ITEM_BORDER_CGRAM"),
            x.border_colors,
            ROWS,
            t.n("ITEM_LIST_Y").div_euclid(cell)
        ));
        // The item tables go outside bank 0, read with `lda f:item_k, x`:
        // they grow with every item the maps bring. `item_k` is a word per
        // RM2k number, $FFFF for one the cartridge does not carry: ABL's
        // whole game carries 264 items, and until 2026-10-15 it was a byte.
        out.push_str(".segment \"RODATA\"\n");
        words_asm(
            out,
            "item_k",
            &decimal((0..ITEMS_N as i64).map(|n| k_of.get(&n).map_or(0xFFFF, |&k| k as i64))),
            true,
        );
        words_asm(out, "item_id", &decimal(items.iter()), true);
        // Whether it goes in white and does something on the map, whether
        // using it spends one, whether it opens the actor choice, and whether
        // it is a two-handed weapon.
        let textos = at(self.screens, "texts")?;
        let mut flags: HashMap<i64, (bool, bool)> = HashMap::new();
        for i in list_at(textos, "items")? {
            let usable = at(i, "usable")?.as_bool().unwrap_or(false);
            let needs = at(i, "needs_actor")?.as_bool().unwrap_or(false);
            flags.insert(int_at(i, "number")?, (usable, needs));
        }
        let mut uses = Vec::new();
        for &n in items {
            let (usable, needs) = flags
                .get(&n)
                .copied()
                .ok_or_else(|| Bad::answer(format!("item {n} has no text")))?;
            let it = item(n)?;
            uses.push(
                i64::from(usable)
                    | if usable && !needs && it.uses != 0 {
                        2
                    } else {
                        0
                    }
                    | if needs { 4 } else { 0 }
                    | if it.two_handed { 8 } else { 0 },
            );
        }
        bytes_asm(out, "item_use", &decimal(uses), true);
        words_asm(
            out,
            "item_switch",
            &decimal(
                items
                    .iter()
                    .map(|&n| item(n).map(|i| i.switch_id))
                    .collect::<Result<Vec<_>>>()?,
            ),
            true,
        );
        out.push_str(".segment \"TABLES\"\n");
        // What each item does in a battle: whether it goes in the list
        // —the battle stage's rule— and how much it heals.
        out.push_str(".segment \"RODATA\"\n");
        let item_battle: Vec<i64> = list_at(self.model, "item_battle")?
            .iter()
            .map(|v| i64::from(v.as_bool().unwrap_or(false)))
            .collect();
        bytes_asm(out, "item_battle", &decimal(item_battle), true);
        words_asm(out, "ba_item_desc", &decimal(x.item_desc_battle.iter().copied()), true);
        let per_item = |f: &dyn Fn(&ditto::schema::Item) -> i64| -> Result<Vec<String>> {
            Ok(decimal(
                items
                    .iter()
                    .map(|&n| item(n).map(f))
                    .collect::<Result<Vec<_>>>()?,
            ))
        };
        bytes_asm(
            out,
            "item_heal_rate",
            &per_item(&|i| i.recover_hp_rate.into())?,
            true,
        );
        words_asm(
            out,
            "item_heal_hp",
            &per_item(&|i| i64::from(i.recover_hp).min(0xFFFF))?,
            true,
        );
        bytes_asm(
            out,
            "item_heal_sp_rate",
            &per_item(&|i| i.recover_sp_rate.into())?,
            true,
        );
        words_asm(
            out,
            "item_heal_sp",
            &per_item(&|i| i64::from(i.recover_sp).min(0xFFFF))?,
            true,
        );
        // The `MED_*` bits of the runtime. A material is only what it is
        // —the editor keeps the fields of the type it had before, and RM2k
        // reads none of them for one—, and whether it has uses.
        bytes_asm(
            out,
            "item_medicine",
            &per_item(&|i| {
                let uses = if i.uses != 0 { 4 } else { 0 };
                if i.r#type.to_i32() == rm2k_snes_battle::db::ITEM_MATERIAL {
                    return 8 | uses;
                }
                i64::from(i.ko_only)
                    | if i.state_set.first() == Some(&true) {
                        2
                    } else {
                        0
                    }
                    | uses
            })?,
            true,
        );
        // What a material adds to an actor for good, six words per item in
        // the order of the runtime's `level_param`: maximum HP, maximum SP,
        // attack, defense, spirit and agility. Zero for every other type.
        let mut up = Vec::new();
        for &n in items {
            let it = item(n)?;
            let material = it.r#type.to_i32() == rm2k_snes_battle::db::ITEM_MATERIAL;
            for points in [
                it.max_hp_points,
                it.max_sp_points,
                it.atk_points2,
                it.def_points2,
                it.spi_points2,
                it.agi_points2,
            ] {
                up.push(if material { i64::from(points) & 0xFFFF } else { 0 });
            }
        }
        words_asm(out, "item_up", &decimal(up), true);
        out.push_str(".segment \"TABLES\"\n");
        // The four text tables outside bank 0.
        out.push_str(".segment \"RODATA\"\n");
        for (field, prefix) in [("lo", "<"), ("hi", ">"), ("bk", "^")] {
            out.push_str(&format!(".block {}\n", texts.offsets.len().max(1)));
            let entries: Vec<String> = texts
                .offsets
                .iter()
                .map(|(ofs, _)| format!("{prefix}(item_texts + {ofs})"))
                .collect();
            out.push_str(&format!(
                "item_txt_{field}:\n    .byte {}\n",
                if entries.is_empty() {
                    "0".to_string()
                } else {
                    entries.join(", ")
                }
            ));
        }
        bytes_asm(
            out,
            "item_txt_n",
            &decimal(texts.offsets.iter().map(|(_, n)| *n)),
            true,
        );
        // --- the equipment: per item its type, what it adds and who can
        // equip it; per actor its parameters and initial equipment.
        let n_actors = db
            .actors
            .keys()
            .copied()
            .max()
            .map_or(0, |m| i64::from(m) + 1);
        let pos = |row: i64, col: i64| row * 64 + col * 2;
        bytes_asm(
            out,
            "item_type",
            &per_item(&|i| i.r#type.to_i32().into())?,
            true,
        );
        let mut points = Vec::new();
        for &n in items {
            points.extend(rules::points(item(n)?).map(|p| p & 0xFFFF));
        }
        words_asm(out, "item_points", &decimal(points), true);
        bytes_asm(
            out,
            "item_sp",
            &per_item(&|i| {
                if i.r#type.to_i32() == rm2k_snes_battle::db::ITEM_WEAPON {
                    i.sp_cost.into()
                } else {
                    0
                }
            })?,
            true,
        );
        let mut equippable = Vec::new();
        for &n in items {
            let it = item(n)?;
            for byte in 0..8 {
                let mut bits = 0;
                for b in 0..8 {
                    let actor = 8 * byte + b + 1;
                    let can = it
                        .actor_set
                        .get(actor as usize - 1)
                        .copied()
                        .unwrap_or(true);
                    if actor < n_actors && can {
                        bits |= 1 << b;
                    }
                }
                equippable.push(bits);
            }
        }
        bytes_asm(out, "item_actors", &decimal(equippable), true);
        out.push_str(".segment \"RODATA\"\n");
        let actor = |a: i64| db.actors.get(&(a as i32));
        let param = |a: i64, which: &str| -> Result<i64> {
            match actor(a) {
                Some(x) => Ok(rules::param_of(x, which, None).map_err(bad)?),
                None => Ok(0),
            }
        };
        let mut params = Vec::new();
        for a in 0..n_actors {
            for which in ["attack", "defense", "spirit", "agility"] {
                params.push(param(a, which)? & 0xFFFF);
            }
        }
        words_asm(out, "actor_params", &decimal(params), true);
        // An actor's critical hit is its own `1 / critical_hit_chance` plus
        // its best weapon's bonus, added in floating point: see
        // `critical_percent` in `rm2k-snes-battle`. So the console does not
        // add them —it would get 4 where RM2k gets 3— but looks the result
        // up: each actor has a row of `crit_table`, one per different own
        // part, and each weapon a column, one per different bonus. The
        // columns go by bonus, lowest first and 0 for no weapon, so the
        // best of two weapons is the higher column. See `ba_crit_of`.
        let own = |a: i64| actor(a).and_then(rules::actor_critical_own);
        let mut owns: Vec<Option<i32>> = (0..n_actors).map(own).collect();
        owns.sort();
        owns.dedup();
        let crit_bonus = |i: &ditto::schema::Item| {
            if i.r#type.to_i32() == rm2k_snes_battle::db::ITEM_WEAPON {
                i.critical_hit
            } else {
                0
            }
        };
        let mut bonuses = vec![0];
        for &n in items {
            bonuses.push(crit_bonus(item(n)?));
        }
        bonuses.sort();
        bonuses.dedup();
        let column = |b: i32| bonuses.iter().position(|&x| x == b).unwrap_or(0) as i64;
        bytes_asm(out, "item_crit_k", &per_item(&|i| column(crit_bonus(i)))?, true);
        let row = |a: i64| owns.iter().position(|&o| o == own(a)).unwrap_or(0) * bonuses.len();
        words_asm(out, "actor_crit_row", &decimal((0..n_actors).map(|a| row(a) as i64)), true);
        let mut table = Vec::new();
        for &o in &owns {
            for &b in &bonuses {
                table.push(rules::critical_percent(o, b).clamp(0, 255));
            }
        }
        bytes_asm(out, "crit_table", &decimal(table), true);
        out.push_str(".segment \"TABLES\"\n");
        out.push_str("\n.segment \"RODATA\"\n");
        out.push_str(&format!(
            ".block {}\n",
            2 * n_actors as usize * EQUIPMENT_SLOTS
        ));
        let mut initial = Vec::new();
        for a in 0..n_actors {
            match actor(a) {
                Some(x) => initial.extend(rules::initial_equipment(x).into_iter().map(i64::from)),
                None => initial.extend([0; EQUIPMENT_SLOTS]),
            }
        }
        out.push_str(&format!(
            "equipment_initial:\n .word {}\n",
            decimal(initial).join(", ")
        ));
        out.push_str("\n.segment \"TABLES\"\n");
        words_asm(
            out,
            "actor_txt",
            &hex4((0..n_actors).map(|a| x.actor_text.get(&a).copied().unwrap_or(0xFFFF))),
            false,
        );
        // And each rename's, which `actor_name_txt` takes instead when the
        // actor carries it: see the runtime's `actor_names.s`.
        words_asm(out, "name_txt", &hex4(x.name_text.iter().copied()), false);
        let eq_params: Vec<i64> = list(t.v("EQ_PARAMS"))?
            .iter()
            .map(|p| {
                let p = ints(p)?;
                Ok(pos(p[0], p[1]))
            })
            .collect::<Result<_>>()?;
        words_asm(out, "eq_param_pos", &decimal(eq_params), false);
        out.push_str(".segment \"RODATA\"\n");
        words_asm(out, "item_price", &per_item(&|i| i.price.into())?, true);
        out.push_str(".segment \"TABLES\"\n");
        out.push_str(&pyf!(
            "TI_TEXT           = %d\nTI_TEXT_HAVE      = %d\nTI_TEXT_CARRIED   = %d\nTI_TEXT_CURRENCY  = %d\n\
             TI_SECOND         = %d\nTI_MAIN_MSG_POS = %d\nTI_MSG_POS        = %d\nTI_COMMAND_POS0   = %d\n\
             TI_GOLD_POS       = %d\nTI_HAVE_POS       = %d\nTI_HAVE_NUM       = %d\nTI_CARRIED_POS    = %d\n\
             TI_CARRIED_NUM    = %d\nTI_LIST_POS0      = %d\nTI_LIST_ROWS_BUY = %d\nTI_LIST_ROWS_SALE = %d\n\
             TI_NAME           = %d\nTI_PRICE          = %d\nTI_COUNT_POS      = %d\nTI_COUNT_X_POS    = %d\n\
             TI_COUNT_NUM_POS = %d\nTI_TOTAL_POS      = %d\nTI_RED            = %d\n",
            x.shop_text,
            x.owned_text,
            x.carried_text,
            x.currency_text,
            t.n("TI_SECOND"),
            pos(t.n("TI_MAIN_MSG_ROW"), t.n("ITEM_DESC_COL")),
            pos(t.n("TI_MSG_ROW"), t.n("ITEM_DESC_COL")),
            pos(t.n("TI_MAIN_MSG_ROW") + 2, t.n("TI_COMMAND_COL")),
            pos(t.n("TI_GOLD_ROW"), t.n("TI_GOLD_COL")),
            pos(t.n("TI_OWNED_ROW"), t.n("TI_STATUS_COL")),
            pos(t.n("TI_OWNED_ROW"), t.n("TI_STATUS_NUM")),
            pos(t.n("TI_CARRIED_ROW"), t.n("TI_STATUS_COL")),
            pos(t.n("TI_CARRIED_ROW"), t.n("TI_STATUS_NUM")),
            pos(t.n("TI_LIST_ROW0"), 0),
            t.n("TI_LIST_ROWS_BUY"),
            t.n("TI_LIST_ROWS_SALE"),
            t.n("TI_LIST_COL") * 2,
            t.n("TI_PRICE_COL") * 2,
            pos(t.n("TI_COUNT_ROW"), t.n("TI_LIST_COL")),
            pos(t.n("TI_COUNT_ROW"), t.n("TI_COUNT_X_COL")),
            pos(t.n("TI_COUNT_ROW"), t.n("TI_COUNT_COL")),
            pos(t.n("TI_TOTAL_ROW"), t.n("TI_GOLD_COL")),
            t.n("ITEM_RED")
        ));
        // `eq_bar` counts the slots' rows and the list's from the same one.
        if t.n("EQ_LIST_ROW0") != t.n("EQ_SLOT_ROW0") {
            return Err(Bad::answer(format!(
                "the equipment list starts at row {} and the slots at {}",
                t.n("EQ_LIST_ROW0"),
                t.n("EQ_SLOT_ROW0")
            )));
        }
        out.push_str(&pyf!(
            "ACTORS_N          = %d\nSLOTS_EQUIPMENT   = %d\nEQ_TEXT_PARAM     = %d\nEQ_TEXT_SLOT      = %d\n\
             EQ_ACTOR_POS      = %d\nEQ_BAR_ROW0       = %d\nEQ_BORDER_TEXT    = %d\nEQ_BORDER_TEXT_N  = %d\n\
             EQ_PARAM_VALUE    = %d\nEQ_PARAM_ARROW    = %d\nEQ_SLOT_POS0      = %d\nEQ_SLOT_TERM      = %d\n\
             EQ_SLOT_NAME      = %d\nEQ_SLOT_WIDTH     = %d\nEQ_LIST_POS0      = %d\nEQ_LIST_ROWS      = %d\n\
             EQ_LIST_NAME      = %d\nSCR_TWO_POINTS    = %d\nSCR_DESC_POS      = %d\n",
            n_actors,
            EQUIPMENT_SLOTS,
            x.param_text[0],
            x.slot_text[0],
            pos(t.n("EQ_ACTOR_ROW"), t.n("EQ_ACTOR_COL")),
            t.n("EQ_SLOT_ROW0"),
            t.n("EQ_SLOT_ROW0"),
            (EQUIPMENT_SLOTS as i64).max(t.n("EQ_LIST_ROWS")) * 2,
            t.n("EQ_PARAM_VALUE") * 2,
            t.n("EQ_PARAM_ARROW") * 2,
            pos(t.n("EQ_SLOT_ROW0"), 0),
            t.n("EQ_SLOT_TERM_COL") * 2,
            t.n("EQ_SLOT_NAME_COL") * 2,
            t.n("EQ_SLOT_NAME_WIDTH"),
            pos(t.n("EQ_LIST_ROW0"), 0),
            t.n("EQ_LIST_ROWS"),
            t.n("EQ_LIST_NAME_COL") * 2,
            t.n("ITEM_COLON_COL") * 2,
            pos(t.n("ITEM_DESC_Y").div_euclid(cell), t.n("ITEM_DESC_COL"))
        ));
        // --- the battle: each actor's max HP and SP at its level.
        out.push_str(".segment \"RODATA\"\n");
        let hp: Vec<i64> = (0..n_actors)
            .map(|a| Ok(param(a, "maxhp")? & 0xFFFF))
            .collect::<Result<_>>()?;
        words_asm(out, "actor_hpmax", &decimal(hp), true);
        let sp: Vec<i64> = (0..n_actors)
            .map(|a| Ok(param(a, "maxsp")? & 0xFFFF))
            .collect::<Result<_>>()?;
        words_asm(out, "actor_spmax", &decimal(sp), true);
        // And each actor's starting level, one byte: what a `ControlVars`
        // asking for the level of an actor who never fights —no `FAR_EXP`
        // slot— answers. See `actor_stat_other` in the runtime.
        let levels: Vec<i64> = (0..n_actors)
            .map(|a| actor(a).map_or(1, rules::level_of))
            .collect();
        bytes_asm(out, "actor_level", &decimal(levels), true);
        // `rm2k-snes-battle` leaves the segment in RODATA.
        out.push_str(&r.battle_tables.experience);
        self.skills_and_troops(out, texts, x, n_actors)
    }

    fn skills_and_troops(
        &self,
        out: &mut String,
        _texts: &mut Texts,
        x: ItemTexts,
        n_actors: i64,
    ) -> Result<()> {
        let (r, db, bs) = (self.r, self.db, self.bs);
        let rom_skills = &x.rom_skills;
        let skill = |h: i64| db.skill(h as i32).map_err(bad);
        let skill_place: HashMap<i64, usize> = rom_skills
            .iter()
            .enumerate()
            .map(|(k, &h)| (h, k))
            .collect();
        let per_skill = |f: &dyn Fn(&ditto::schema::Skill) -> i64| -> Result<Vec<String>> {
            Ok(decimal(
                rom_skills
                    .iter()
                    .map(|&h| skill(h).map(f))
                    .collect::<Result<Vec<_>>>()?,
            ))
        };
        let from = |m: &HashMap<i64, i64>| decimal(rom_skills.iter().map(|h| m[h]));
        // --- the skills, one row per skill the cartridge carries, outside
        // bank 0 and declared: the battle reads them with `lda f:`.
        words_asm(out, "skill_id", &decimal(rom_skills.iter()), true);
        words_asm(out, "skill_txt", &from(&x.skill_text), true);
        words_asm(out, "skill_desc", &from(&x.skill_desc_text), true);
        words_asm(out, "skill_msg1", &from(&x.skill_msg1_text), true);
        words_asm(out, "skill_msg2", &from(&x.skill_msg2_text), true);
        words_asm(out, "skill_power", &per_skill(&|s| s.power.into())?, true);
        words_asm(
            out,
            "skill_switch",
            &per_skill(&|s| s.switch_id.into())?,
            true,
        );
        bytes_asm(out, "skill_sp", &per_skill(&|s| s.sp_cost.into())?, true);
        bytes_asm(
            out,
            "skill_type",
            &per_skill(&|s| s.r#type.to_i32().into())?,
            true,
        );
        bytes_asm(
            out,
            "skill_phys",
            &per_skill(&|s| s.physical_rate.into())?,
            true,
        );
        bytes_asm(
            out,
            "skill_mag",
            &per_skill(&|s| s.magical_rate.into())?,
            true,
        );
        bytes_asm(out, "skill_var", &per_skill(&|s| s.variance.into())?, true);
        bytes_asm(out, "skill_hit", &per_skill(&|s| s.hit.into())?, true);
        // What it touches, one bit each in the order `Skill::vExecute` looks
        // at them; bit 6 whether it targets enemies, 7 whether it ignores
        // defense.
        let affects: Vec<i64> = rom_skills
            .iter()
            .map(|&h| {
                let s = skill(h)?;
                Ok(i64::from(s.affect_hp)
                    | i64::from(s.affect_sp) << 1
                    | i64::from(s.affect_attack) << 2
                    | i64::from(s.affect_defense) << 3
                    | i64::from(s.affect_spirit) << 4
                    | i64::from(s.affect_agility) << 5
                    | i64::from(rm2k_snes_battle::db::targets_enemies(s)) << 6
                    | i64::from(s.ignore_defense) << 7)
            })
            .collect::<Result<_>>()?;
        bytes_asm(out, "skill_affects", &hex2(affects), true);
        bytes_asm(
            out,
            "skill_scope",
            &per_skill(&|s| s.scope.to_i32().into())?,
            true,
        );
        // What the skills screen needs of each one, from the screens stage:
        // the description's two lines as slices of `skill_desc` —the first's
        // length, and where the second starts and its length— and whether
        // the map can use it. See `skills.rs` in `rm2k-snes-screens`.
        let on_map = at(self.screens, "skills")?;
        let of = |h: i64| at(on_map, &h.to_string());
        let mut lines: [Vec<i64>; 3] = Default::default();
        let mut field = Vec::new();
        let mut name_cut = Vec::new();
        for &h in rom_skills {
            let l = ints(at(of(h)?, "lines")?)?;
            for (k, v) in lines.iter_mut().enumerate() {
                v.push(l[k]);
            }
            // Bit 0, the map can use it; bit 1, it raises the fallen, which
            // only a skill the map can use is asked.
            let flag = |name: &str| -> Result<bool> { Ok(at(of(h)?, name)?.as_bool().unwrap_or(false)) };
            let on_map = flag("field")?;
            field.push(i64::from(on_map) | i64::from(on_map && flag("revives")?) << 1);
            name_cut.push(int_at(of(h)?, "name_cut")?);
        }
        bytes_asm(out, "skill_line1_n", &decimal(lines[0].iter()), true);
        bytes_asm(out, "skill_line2_at", &decimal(lines[1].iter()), true);
        bytes_asm(out, "skill_line2_n", &decimal(lines[2].iter()), true);
        bytes_asm(out, "skill_on_map", &decimal(field), true);
        bytes_asm(out, "skill_name_cut", &decimal(name_cut), true);
        self.states(out, &x)?;
        // The parallel common events, in the order of their numbers, which
        // is the order RM2k runs them in: see `compar_tick` in
        // `common_events.s`. One entry of `COMPAR_ENTRY` bytes each: the
        // switch's byte and its mask —$00 for one without a switch, which
        // runs always—, whether it is pure, and where its body starts.
        let parallel = &r.parallel_common;
        out.push_str(&format!("COMPAR_N = {}\n", parallel.len()));
        out.push_str(&format!(".block {}\ncompar_table:\n", 6 * parallel.len().max(1)));
        if parallel.is_empty() {
            out.push_str("    .byte 0, 0, 0, 0, 0, 0\n");
        }
        for (switch, n, pure, _) in parallel {
            let byte = switch >> 3;
            if byte > 255 {
                return Err(Bad::answer(format!(
                    "parallel common event {n}: switch {switch} does not fit the table's byte"
                )));
            }
            let mask = if *switch == 0 { 0 } else { 1 << (switch & 7) };
            out.push_str(&format!(
                "    .byte {byte}, ${mask:02X}, {}\n    .word .loword(common_parallel_{n})\n    .byte ^common_parallel_{n}\n",
                u8::from(*pure)
            ));
        }
        for (_, n, _, code) in parallel {
            line(out, &block(&format!("common_parallel_{n}"), &crate::hex::decode(code)?));
        }
        // The shared common event bodies, by index, and the automatic ones:
        // see `common_events.s`. A cartridge without them carries the
        // labels anyway, with a dummy entry, so the runtime assembles.
        let empty = crate::request::Commons {
            bodies: vec![],
            autostart: vec![],
            depth: Some(0),
        };
        let commons = r.commons.as_ref().unwrap_or(&empty);
        let labels: Vec<String> = commons
            .bodies
            .iter()
            .map(|(n, _)| format!("common_body_{n}"))
            .collect();
        let or_dummy = |v: Vec<String>, dummy: &str| {
            if v.is_empty() {
                vec![dummy.to_string()]
            } else {
                v
            }
        };
        // A loop of calls has no deepest chain: the ROM's stack skips what
        // does not fit.
        out.push_str(&format!("COMMON_DEPTH = {}\n", commons.depth.unwrap_or(0)));
        words_asm(
            out,
            "common_body_lo",
            &or_dummy(labels.iter().map(|l| format!(".loword({l})")).collect(), "0"),
            true,
        );
        words_asm(
            out,
            "common_body_bank",
            &or_dummy(labels.iter().map(|l| format!("^{l}")).collect(), "0"),
            true,
        );
        out.push_str(&format!("COMAUTO_N = {}\n", commons.autostart.len()));
        words_asm(
            out,
            "comauto_byte",
            &or_dummy(decimal(commons.autostart.iter().map(|a| a.0 >> 3)), "0"),
            true,
        );
        bytes_asm(
            out,
            "comauto_mask",
            &or_dummy(
                commons
                    .autostart
                    .iter()
                    .map(|a| format!("${:02X}", 1 << (a.0 & 7)))
                    .collect(),
                "0",
            ),
            true,
        );
        bytes_asm(
            out,
            "comauto_body",
            &or_dummy(decimal(commons.autostart.iter().map(|a| a.1)), "0"),
            true,
        );
        for ((_, code), label) in commons.bodies.iter().zip(&labels) {
            line(out, &block(label, &crate::hex::decode(code)?));
        }
        // What each actor knows: one bit per (actor, skill) pair, and per
        // actor where its pairs start and how many there are.
        let mut pairs: Vec<(i64, i64, i64)> = r.skill_pairs.clone();
        pairs.sort_by_key(|p| p.2);
        let mut skill_pair_start = Vec::new();
        let mut skill_pair_n = Vec::new();
        for a in 0..n_actors {
            let own: Vec<i64> = pairs.iter().filter(|p| p.0 == a).map(|p| p.2).collect();
            skill_pair_start.push(own.first().copied().unwrap_or(0));
            skill_pair_n.push(own.len() as i64);
            if !own.is_empty() && own != (own[0]..own[0] + own.len() as i64).collect::<Vec<_>>() {
                return Err(Bad::answer(format!(
                    "the skill pairs of actor {a} aren't contiguous"
                )));
            }
        }
        if skill_pair_n.iter().copied().max().unwrap_or(0) > 255 {
            return Err(Bad::answer(
                "an actor has more than 255 skill pairs and `skill_pair_n` is one byte",
            ));
        }
        let skill_bytes = pairs.len().div_ceil(8).max(1);
        let mut bits = vec![0i64; skill_bytes];
        for &(a, h, slot) in &pairs {
            if let Some(actor) = db.actors.get(&(a as i32)) {
                if rules::learned_skills(actor, None).contains(&(h as i32)) {
                    bits[(slot >> 3) as usize] |= 1 << (slot & 7);
                }
            }
        }
        out.push_str(&format!(
            "; How many bytes the skill bits take in `FAR_SKILL`.\nSKILL_BYTES = {skill_bytes}\n"
        ));
        let mut variables = r.variables.clone();
        variables.sort_by_key(|v| v.1);
        out.push_str(&format!(
            "; The signature of the save format: see `SRAM_SIGNATURE`.\nGAME_SIGNATURE = ${:04X}\n",
            save_signature(&variables, &pairs, &r.battle_tables.slots, n_actors, switch_bytes(r.switch_top)?)
        ));
        words_asm(out, "skill_pair_init", &decimal(skill_pair_start), true);
        bytes_asm(out, "skill_pair_n", &decimal(skill_pair_n), true);
        let actors: BTreeSet<i64> = r.actors.iter().copied().collect();
        bytes_asm(
            out,
            "skill_pair_k",
            &decimal(pairs.iter().map(|&(a, h, _)| {
                if actors.contains(&a) {
                    skill_place.get(&h).map_or(0xFF, |&k| k as i64)
                } else {
                    0xFF
                }
            })),
            true,
        );
        bytes_asm(out, "skill_initial", &hex2(bits), true);
        // At which level the learning table teaches each pair, or 0.
        let pair_levels = ints_at(self.model, "pair_levels")?;
        bytes_asm(out, "skill_pair_level", &decimal(pair_levels.iter()), true);
        // And the name the victory tells it by, or $FFFF.
        words_asm(
            out,
            "skill_pair_learns_txt",
            &hex4(pairs.iter().zip(&pair_levels).map(|(&(a, h, _), &level)| {
                match x.whole_skill_text.get(&h) {
                    Some(&k) if actors.contains(&a) && level > 0 => k,
                    _ => 0xFFFF,
                }
            })),
            true,
        );
        // 254 and not 256: $FF is the attack and $FE "none left".
        if rom_skills.len() > 254 {
            return Err(Bad::answer(format!(
                "the cartridge's skills are {} and `skill_pair_k` is one byte",
                rom_skills.len()
            )));
        }
        words_asm(
            out,
            "actor_skill_txt",
            &hex4((0..n_actors).map(|a| x.skill_command_text.get(&a).copied().unwrap_or(0xFFFF))),
            true,
        );
        // The troops some battle asks for, by their RM2k number, and their
        // members.
        let used: Vec<i64> = r
            .troops
            .iter()
            .copied()
            .filter(|n| db.troops.contains_key(&(*n as i32)))
            .collect();
        let place_of: HashMap<i64, usize> = x
            .rom_enemies
            .iter()
            .enumerate()
            .map(|(k, &e)| (e, k))
            .collect();
        let mut members = Vec::new();
        let mut starts = Vec::new();
        for &number in &used {
            starts.push(members.len() as i64);
            for m in db.members(number as i32).map_err(bad)? {
                members.push(*place_of.get(&i64::from(m.enemy_id)).ok_or_else(|| {
                    Bad::answer(format!("enemy {} is not the battle's", m.enemy_id))
                })? as i64);
            }
        }
        // A troop's place goes in a word —`BA_TROOP_K`, with $FFFF "the
        // cartridge does not carry it"—, and the ROM indexes the word
        // tables with twice it in sixteen bits: up to 32768. It was a byte
        // until 2026-10-11, when Vampires Dawn asked for 277. Where its
        // members start goes in a word of `troop_init`: they were a byte
        // until 2026-10-10, when its 234 troops took 470 members.
        if used.len() > 0x8000 || members.len() > 0x10000 {
            return Err(Bad::answer(format!(
                "the cartridge's troops don't fit: {} troops of 32768, {} members",
                used.len(),
                members.len()
            )));
        }
        words_asm(out, "troop_id", &decimal(used.iter()), true);
        let model_troops = list_at(self.model, "troops")?;
        let answered: Vec<i64> = model_troops
            .iter()
            .map(|t| int_at(t, "id"))
            .collect::<Result<_>>()?;
        if answered != used {
            return Err(Bad::answer(format!(
                "the battle stage answered for troops {answered:?} and the cartridge carries {used:?}"
            )));
        }
        let troop_exp: Vec<i64> = model_troops
            .iter()
            .map(|t| int_at(t, "exp"))
            .collect::<Result<_>>()?;
        for (n, exp) in used.iter().zip(&troop_exp) {
            if *exp > 0xFFFF {
                return Err(Bad::answer(format!(
                    "troop {n} gives {exp} experience and the ROM adds it in sixteen bits"
                )));
            }
        }
        words_asm(out, "troop_exp", &decimal(troop_exp.iter()), true);
        let troop_gold: Vec<i64> = model_troops
            .iter()
            .map(|t| int_at(t, "gold"))
            .collect::<Result<_>>()?;
        for (n, gold) in used.iter().zip(&troop_gold) {
            if *gold > 0xFFFF {
                return Err(Bad::answer(format!(
                    "troop {n} gives {gold} gold and the ROM adds it in sixteen bits"
                )));
            }
        }
        words_asm(out, "troop_gold", &decimal(troop_gold.iter()), true);
        words_asm(out, "troop_init", &decimal(starts), true);
        // Which members start hidden, one bit per place.
        let mut hidden = Vec::new();
        let mut counts = Vec::new();
        for &n in &used {
            let ms = db.members(n as i32).map_err(bad)?;
            hidden.push(
                ms.iter()
                    .enumerate()
                    .filter(|(_, m)| m.invisible)
                    .map(|(k, _)| 1i64 << k)
                    .sum::<i64>(),
            );
            counts.push(ms.len() as i64);
        }
        bytes_asm(out, "troop_hidden", &hex2(hidden), true);
        bytes_asm(out, "troop_n", &decimal(counts), true);
        bytes_asm(out, "troop_member", &decimal(members.iter()), true);
        self.troop_pages(out, &used)?;
        // The random encounters, which `rm2k-snes-battle` wrote; they open no
        // segment and land in this RODATA.
        out.push_str(&r.battle_tables.encounters);
        self.enemies_and_scene(out, &x, &used, n_actors, bs)
    }

    /// The attributes, for `battle_attributes.s`: see `attributes.rs` in
    /// `rm2k-snes-battle`, which is the model's and what each number here
    /// comes from. Outside bank 0 and declared, like the rest of the battle.
    ///
    /// Only the attributes something that hits can carry count —a carried
    /// skill's `attribute_effects`, a carried weapon's `attribute_set`—:
    /// one that only armor or an enemy's ranks name never multiplies
    /// anything. They are numbered again from 0 in database order, and
    /// `ATTR_N` says how many; at zero the routine returns at once.
    ///
    /// * `attr_rate`: a word per attribute and rank, `A` to `E`. A negative
    ///   rate counts for nothing in RM2k 2000, and goes as -1.
    /// * `attr_magic`: whether each one is magical.
    /// * `attr_sets`: rows of `ATTR_N` bytes, 1 where the set has the
    ///   attribute; row 0 is the empty set, and equal sets share a row.
    ///   `item_attr` and `skill_attr` give each item and skill its row, as
    ///   the byte where it starts.
    /// * `attr_ranks`: rows of `ATTR_N` ranks, one per actor —its own,
    ///   before its armor— and then one per enemy, in `enemy_*` order: the
    ///   enemy `k`'s row is `ACTORS_N + k`.
    fn attributes(&self, out: &mut String, x: &ItemTexts, n_actors: i64) -> Result<()> {
        use rm2k_snes_battle::attributes as at;
        let (r, db) = (self.r, self.db);
        let n_db = db.attributes.len();
        let skill_sets: Vec<Vec<bool>> = x
            .rom_skills
            .iter()
            .map(|&h| Ok(db.skill(h as i32).map_err(bad)?.attribute_effects.clone()))
            .collect::<Result<_>>()?;
        let mut item_sets = Vec::new();
        let mut hitting = skill_sets.clone();
        for &n in &r.items {
            let it = db.item(n as i32).map_err(bad)?;
            item_sets.push(it.attribute_set.clone());
            if it.r#type.to_i32() == rm2k_snes_battle::db::ITEM_WEAPON {
                hitting.push(it.attribute_set.clone());
            }
        }
        let mut used = BTreeSet::new();
        for set in &hitting {
            for (k, &has) in set.iter().enumerate() {
                if has {
                    // easyrpg stops the walk at an attribute the database
                    // lacks; no game does that, and the console does not.
                    if k >= n_db {
                        return Err(Bad::answer(format!(
                            "a skill or weapon carries attribute {}, and the database has {n_db}",
                            k + 1
                        )));
                    }
                    used.insert(k);
                }
            }
        }
        let used: Vec<usize> = used.into_iter().collect();
        let n = used.len();
        if n > 255 {
            return Err(Bad::answer(format!("{n} attributes, and `ATTR_N` multiplies as a byte")));
        }
        out.push_str(&format!("ATTR_N = {n}\n"));
        let attrs: Vec<&ditto::schema::Attribute> = db.attributes.values().collect();
        let mut rates = Vec::new();
        for &k in &used {
            for rank in 0..5 {
                let rate = at::rate_of(attrs[k], rank);
                if rate > 0x7FFF {
                    return Err(Bad::answer(format!("attribute {}: a rate of {rate}", k + 1)));
                }
                rates.push(rate.max(-1) & 0xFFFF);
            }
        }
        words_asm(out, "attr_rate", &decimal(rates), true);
        bytes_asm(
            out,
            "attr_magic",
            &decimal(used.iter().map(|&k| i64::from(!at::physical(attrs[k])))),
            true,
        );
        let mut rows: Vec<i64> = vec![0; n];
        let mut row_of: HashMap<Vec<i64>, usize> = HashMap::new();
        row_of.insert(vec![0; n], 0);
        let mut place = |set: &[bool]| -> usize {
            let row: Vec<i64> = used
                .iter()
                .map(|&k| i64::from(set.get(k).copied().unwrap_or(false)))
                .collect();
            if let Some(&at) = row_of.get(&row) {
                return at;
            }
            let at = rows.len();
            rows.extend(&row);
            row_of.insert(row, at);
            at
        };
        let item_rows: Vec<usize> = item_sets.iter().map(|s| place(s)).collect();
        let skill_rows: Vec<usize> = skill_sets.iter().map(|s| place(s)).collect();
        if rows.len() > 0x10000 {
            return Err(Bad::answer("the attribute sets don't fit in a bank"));
        }
        bytes_asm(out, "attr_sets", &decimal(rows), true);
        words_asm(out, "item_attr", &decimal(item_rows), true);
        words_asm(out, "skill_attr", &decimal(skill_rows), true);
        let mut ranks = Vec::new();
        for a in 0..n_actors {
            for &k in &used {
                ranks.push(match db.actors.get(&(a as i32)) {
                    Some(_) => at::actor_own_rank(db, a as i32, k).map_err(bad)?,
                    None => at::RANK_NEUTRAL,
                });
            }
        }
        for &e in &x.rom_enemies {
            for &k in &used {
                ranks.push(at::enemy_rank(db, e as i32, k).map_err(bad)?);
            }
        }
        if ranks.len() > 0x10000 {
            return Err(Bad::answer("the attribute ranks don't fit in a bank"));
        }
        bytes_asm(out, "attr_ranks", &decimal(ranks), true);
        Ok(())
    }

    fn troop_pages(&self, out: &mut String, used: &[i64]) -> Result<()> {
        // Per troop, where its pages start and how many there are; per page,
        // its trigger and where its code is inside `troop_code`. All in
        // RODATA, each table in its `.block`.
        let empty = serde_json::json!({"per_troop": [], "code": "", "messages": "00"});
        let pt = self.r.troop_pages.as_ref().unwrap_or(&empty);
        let mut per_troop: HashMap<i64, Vec<(Vec<i64>, i64)>> = HashMap::new();
        for entry in list_at(pt, "per_troop")? {
            let entry = list(entry)?;
            let number = int(&entry[0])?;
            let mut theirs = Vec::new();
            for page in list(&entry[1])? {
                let page = list(page)?;
                theirs.push((ints(&page[0])?, int(&page[1])?));
            }
            per_troop.insert(number, theirs);
        }
        let mut entries = Vec::new();
        let mut page_start = Vec::new();
        let mut page_n = Vec::new();
        for n in used {
            let theirs = per_troop.get(n).cloned().unwrap_or_default();
            page_start.push(entries.len() as i64);
            page_n.push(theirs.len() as i64);
            entries.extend(theirs);
        }
        if page_n.iter().copied().max().unwrap_or(0) > TROOP_PAGES_MAX as i64 {
            return Err(Bad::answer(format!(
                "a troop brings {} pages and the battle tracks {TROOP_PAGES_MAX}",
                page_n.iter().max().unwrap()
            )));
        }
        out.push_str(".segment \"RODATA\"\n");
        words_asm(out, "troop_page_init", &decimal(page_start), true);
        bytes_asm(out, "troop_page_n", &decimal(page_n), true);
        // A trigger: flags, switch_a, switch_b, slot, value, and the rest.
        bytes_asm(
            out,
            "tpage_flags",
            &hex2(entries.iter().map(|(d, _)| d[0])),
            true,
        );
        words_asm(
            out,
            "tpage_sw_a",
            &decimal(entries.iter().map(|(d, _)| d[1])),
            true,
        );
        words_asm(
            out,
            "tpage_code",
            &entries
                .iter()
                .map(|(_, ofs)| format!(".loword(troop_code + {ofs})"))
                .collect::<Vec<_>>(),
            true,
        );
        // `switch_b` and the variable only if some page uses them: with none
        // the console never reads them, so the label is enough.
        for (name, field, bit) in [
            ("tpage_sw_b", 2usize, TROOP_TRIGGER_SWITCH_B),
            ("tpage_var", 3, TROOP_TRIGGER_VARIABLE),
            ("tpage_value", 4, TROOP_TRIGGER_VARIABLE),
        ] {
            let uses_it = entries.iter().any(|(d, _)| d[0] & i64::from(bit) != 0);
            let values = if uses_it {
                decimal(entries.iter().map(|(d, _)| d[field] & 0xFFFF))
            } else {
                Vec::new()
            };
            words_asm(out, name, &values, true);
        }
        let code = crate::json::bytes_at(pt, "code")?;
        line(
            out,
            &block("troop_code", if code.is_empty() { &[0] } else { &code }),
        );
        line(
            out,
            &block("messages_troop", &crate::json::bytes_at(pt, "messages")?),
        );
        Ok(())
    }

    fn enemies_and_scene(
        &self,
        out: &mut String,
        x: &ItemTexts,
        used: &[i64],
        n_actors: i64,
        bs: &Geometry,
    ) -> Result<()> {
        let (r, db) = (self.r, self.db);
        let enemy = |e: i64| db.enemy(e as i32).map_err(bad);
        let rom_enemies = &x.rom_enemies;
        let per_enemy = |f: &dyn Fn(&ditto::schema::Enemy) -> i64| -> Result<Vec<String>> {
            Ok(decimal(
                rom_enemies
                    .iter()
                    .map(|&e| enemy(e).map(f))
                    .collect::<Result<Vec<_>>>()?,
            ))
        };
        words_asm(out, "enemy_hp", &per_enemy(&|e| e.max_hp.into())?, true);
        words_asm(out, "enemy_atk", &per_enemy(&|e| e.attack.into())?, true);
        words_asm(out, "enemy_def", &per_enemy(&|e| e.defense.into())?, true);
        words_asm(out, "enemy_agi", &per_enemy(&|e| e.agility.into())?, true);
        words_asm(out, "enemy_spi", &per_enemy(&|e| e.spirit.into())?, true);
        words_asm(out, "enemy_sp", &per_enemy(&|e| e.max_sp.into())?, true);
        // `Game_Enemy::GetHitChance`: 70 if it misses, 90 if not.
        let hit = |e: &ditto::schema::Enemy| if e.miss { 70 } else { 90 };
        bytes_asm(out, "enemy_hit", &per_enemy(&|e| hit(e))?, true);
        // The critical hit as a whole percentage: `1 / chance` times a
        // hundred, in floating point as RM2k —see `critical_percent`—.
        bytes_asm(
            out,
            "enemy_crit",
            &per_enemy(&|e| {
                rules::critical_percent(e.critical_hit.then_some(e.critical_hit_chance), 0)
                    .clamp(0, 255)
            })?,
            true,
        );
        words_asm(
            out,
            "enemy_txt",
            &decimal(rom_enemies.iter().map(|e| x.enemy_text[e])),
            true,
        );
        words_asm(out, "enemy_exp", &per_enemy(&|e| e.exp.into())?, true);
        words_asm(out, "enemy_gold", &per_enemy(&|e| e.gold.into())?, true);
        let known: BTreeSet<i64> = r.items.iter().copied().collect();
        for &e in rom_enemies {
            let drop = i64::from(enemy(e)?.drop_id);
            if drop != 0 && !known.contains(&drop) {
                return Err(Bad::answer(format!(
                    "enemy {e} drops item {drop} and the cartridge doesn't carry it"
                )));
            }
        }
        words_asm(out, "enemy_drop", &per_enemy(&|e| e.drop_id.into())?, true);
        bytes_asm(
            out,
            "enemy_drop_pct",
            &per_enemy(&|e| e.drop_prob.into())?,
            true,
        );
        // What each enemy can do on its turn: per action, the skill as a `k`
        // or $FF for the attack, and its rating with bit 7 if not effective.
        let skill_place: HashMap<i64, usize> = x
            .rom_skills
            .iter()
            .enumerate()
            .map(|(k, &h)| (h, k))
            .collect();
        let mut eacc_start = Vec::new();
        let mut eacc_skill = Vec::new();
        let mut eacc_weight = Vec::new();
        let mut eacc_n = Vec::new();
        for &e in rom_enemies {
            eacc_start.push(eacc_skill.len() as i64);
            let theirs = list_at(x.actions, &e.to_string())?;
            eacc_n.push(theirs.len() as i64);
            for a in theirs {
                let a = list(a)?;
                let rating = int(&a[0])?;
                eacc_skill.push(match a[1].as_i64() {
                    None => 0xFF,
                    Some(h) => *skill_place
                        .get(&h)
                        .ok_or_else(|| Bad::answer(format!("skill {h} is not the battle's")))?
                        as i64,
                });
                let effective = a[2].as_bool().unwrap_or(false);
                eacc_weight.push(rating | if effective { 0 } else { 0x80 });
            }
        }
        // Where each enemy's list starts goes in a word: it was a byte until
        // 2026-10-10, when Vampires Dawn's enemies took 344 actions.
        if eacc_skill.len() > 0x10000 {
            return Err(Bad::answer(format!(
                "the actions of the cartridge's enemies are {} and `enemy_acc_init` is a word",
                eacc_skill.len()
            )));
        }
        out.push_str(&format!("ACTIONS_MAX = {}\n", bs.n("ACTIONS_MAX")));
        words_asm(out, "enemy_acc_init", &decimal(eacc_start), true);
        bytes_asm(out, "enemy_acc_n", &decimal(eacc_n), true);
        bytes_asm(out, "eacc_skill", &decimal(eacc_skill), true);
        bytes_asm(out, "eacc_weight", &decimal(eacc_weight), true);
        self.attributes(out, x, n_actors)?;
        // The battle scene: the backdrops and the battlers, in the order of
        // `troop_id`.
        out.push_str(&crate::scene::scenes_asm(&r.scene, used, r.rom.msu != MsuData::Optional)?);
        out.push_str(".segment \"TABLES\"\n");
        // Two products that have to fit in sixteen bits: the healing's
        // `recover_hp_rate * hp_max`, and the hit's `(100 - hit) * agility`.
        for a in 0..n_actors {
            let hp = match db.actors.get(&(a as i32)) {
                Some(actor) => rules::param_of(actor, "maxhp", None).map_err(bad)?,
                None => 0,
            };
            if hp * 100 > 0xFFFF {
                return Err(Bad::answer(format!(
                    "actor {a} has {hp} HP and the ROM's healing computation is sized for 655"
                )));
            }
        }
        for &e in rom_enemies {
            if hit(enemy(e)?) < 70 {
                return Err(Bad::answer(format!(
                    "enemy {e} has a hit rate of {}, and the ROM's hit computation is sized for 70",
                    hit(enemy(e)?)
                )));
            }
        }
        let pos = |row: i64, col: i64| row * 64 + col * 2;
        // The battle's geometry, in the text layer's terms: a place is
        // row * 64 + column * 2, and a column offset is the column times two.
        // See `screen.rs` in `rm2k-snes-battle`.
        for (name, value) in [
            ("BA_ENEMY_POS0", pos(bs.n("BA_ENEMY_ROW0"), 0)),
            ("BA_TARGET_ROWS", bs.n("BA_TARGET_ROWS")),
            ("BA_ENEMY_NAME_DX", bs.n("BA_ENEMY_NAME_COL") * 2),
            ("BA_ENEMY_NAME_WIDTH", bs.n("BA_ENEMY_NAME_WIDTH")),
            ("BA_COMMAND_POS0", pos(bs.n("BA_COMMAND_ROW0"), 0)),
            ("BA_COMMAND_DX", bs.n("BA_COMMAND_COL") * 2),
            ("BA_COMMAND_CELLS", bs.n("BA_COMMAND_CELLS")),
            ("BA_PARTY_POS0", pos(bs.n("BA_PARTY_ROW0"), 0)),
            ("BA_NAME_DX", bs.n("BA_NAME_COL") * 2),
            ("BA_NAME_WIDTH", bs.n("BA_NAME_WIDTH")),
            ("BA_STATE_DX", bs.n("BA_STATE_COL") * 2),
            ("BA_STATE_WIDTH", bs.n("BA_STATE_WIDTH")),
            ("BA_HP_DX", bs.n("BA_HP_COL") * 2),
            ("BA_SP_DX", bs.n("BA_SP_COL") * 2),
            ("BA_MSG_POS1", pos(bs.n("BA_MSG_ROW1"), 0)),
            ("BA_MSG_POS2", pos(bs.n("BA_MSG_ROW2"), 0)),
            ("BA_MSG_LINES", bs.n("BA_MSG_LINES")),
            ("BA_MSG_DX", 2),
            ("BA_HELP_POS", pos(bs.n("BA_HELP_ROW"), bs.n("BA_HELP_COL"))),
            ("BA_LAYOUT_COMMAND", bs.n("BA_LAYOUT_COMMAND")),
            ("BA_LAYOUT_TARGET", bs.n("BA_LAYOUT_TARGET")),
            ("BA_LAYOUT_WIDE", bs.n("BA_LAYOUT_WIDE")),
            ("BA_BARS_MAX", bs.n("BA_BARS_MAX")),
            ("BA_HELP_SCENE_ROWS", bs.n("BA_HELP_SCENE_ROWS")),
            ("BA_HELP_WIDTH", bs.n("BA_HELP_WIDTH")),
            ("BA_PAGE_MSG_POS0", pos(bs.n("BA_PAGE_MSG_ROW0"), 0)),
            ("BA_PAGE_MSG_DX", bs.n("BA_PAGE_MSG_COL") * 2),
            ("BA_PAGE_MSG_WIDTH", bs.n("BA_PAGE_MSG_WIDTH")),
            ("BA_ROW_BYTES", 2 * 64),
            ("BA_HP_ENEMIES", i64::from(r.enemy_hp)),
        ] {
            out.push_str(&format!("{name:<17} = {value}\n"));
        }
        out.push_str(&pyf!(
            "TROOPS_N          = %d\nBATTLE_SEED       = $%04X\nBA_TXT_BASE       = %d\n\
             TROOP_PAGE_MAX    = %d\nTPAGE_SWITCH_A    = $%02X\nTPAGE_SWITCH_B    = $%02X\nTPAGE_VARIABLE    = $%02X\n\
             TPAGE_TURN        = $%02X\nTPAGE_ENEMY       = $%02X\nTPAGE_ACTOR       = $%02X\n\
             TPAGE_WITH_HEADER = $%02X\nTPAGE_HEADER      = %d\n",
            used.len(),
            bs.n("BATTLE_SEED"),
            x.battle_text,
            TROOP_PAGES_MAX,
            TROOP_TRIGGER_SWITCH_A,
            TROOP_TRIGGER_SWITCH_B,
            TROOP_TRIGGER_VARIABLE,
            TROOP_TRIGGER_TURN,
            TROOP_TRIGGER_ENEMY,
            TROOP_TRIGGER_ACTOR,
            TROOP_WITH_HEADER,
            TROOP_HEADER_BYTES
        ));
        // The battle's audio: the songs and the effects with the index they
        // got, $FF or $FFFF when the database has them off. The battle's
        // package goes after the maps', so its index is how many maps there
        // are.
        let audio = r
            .battle_audio
            .as_ref()
            .filter(|a| a.as_object().is_some_and(|o| !o.is_empty()));
        let get = |name: &str, missing: i64| -> i64 {
            audio
                .and_then(|a| a.get(name))
                .and_then(Value::as_i64)
                .unwrap_or(missing)
        };
        out.push_str(&pyf!(
            "BA_SONG           = $%02X\nBA_SONG_END       = $%02X\nBA_PACKAGE        = $%04X\n",
            get("battle_music", 0xFF),
            get("battle_end_music", 0xFF),
            if audio.is_some() {
                r.maps.len() as i64
            } else {
                0xFFFF
            }
        ));
        for (name, constant) in [
            ("dodge_se", "BA_SE_MISS"),
            ("enemy_attack_se", "BA_SE_ATTACK"),
            ("enemy_damaged_se", "BA_SE_DAMAGE_ENEMY"),
            ("actor_damaged_se", "BA_SE_DAMAGE_ACTOR"),
            ("enemy_death_se", "BA_SE_DEATH"),
            ("escape_se", "BA_SE_FLEE"),
            ("item_se", "BA_SE_ITEM"),
        ] {
            out.push_str(&pyf!("%-18s= $%04X\n", constant, get(name, 0xFFFF)));
        }
        out.push_str(&pyf!(
            "BA_TXT_VICTORY2   = %d\nBA_VIC_FINISHED_N = %d\n",
            x.victory2_text,
            x.victory_lines
        ));
        for (k, (name, _)) in BATTLE_TERMS.iter().enumerate() {
            out.push_str(&pyf!(
                "BA_TXT_%-11s= BA_TXT_BASE + %d\n",
                name.to_uppercase(),
                k
            ));
        }
        out.push_str(&format!("BA_TXT_REVIVED    = {}\n", x.revived_text));
        out.push_str(&format!("BA_TXT_DEAD       = {}\n", x.dead_text));
        let commands = list(bs.v("BA_COMMANDS"))?;
        out.push_str(&format!("BA_COMMANDS_N     = {}\n", commands.len()));
        out.push_str(&pyf!(
            "BA_ITEM_POS0      = %d\nBA_ITEM_ROWS      = %d\nBA_ITEM_NAME_WIDTH = %d\nBA_ITEM_COUNT_DX  = %d\n",
            pos(bs.n("BA_ITEM_ROW0"), 0),
            bs.n("BA_ITEM_ROWS"),
            bs.n("BA_ITEM_NAME_WIDTH"),
            bs.n("BA_ITEM_COUNT_COL") * 2
        ));
        out.push_str(&format!("BA_COMMAND_USE    = {}\n", bs.n("BA_COMMAND_USE")));
        out.push_str(&format!(
            "BA_COMMAND_ESCAPE = {}\n",
            bs.n("BA_COMMAND_ESCAPE")
        ));
        out.push_str(&format!(
            "BA_COMMAND_ATTACK = {}\n",
            bs.n("BA_COMMAND_ATTACK")
        ));
        out.push_str(&format!(
            "BA_COMMAND_DEFEND = {}\n",
            bs.n("BA_COMMAND_DEFEND")
        ));
        out.push_str(&format!("BA_COMMAND_SKILL= {}\n", bs.n("BA_COMMAND_SKILL")));
        out.push_str(&pyf!(
            "SKILLS_N          = %d\nBA_SKILL_DESC_POS = %d\nBA_SKILL_POS0     = %d\nBA_SKILL_ROWS     = %d\n\
             BA_SKILL_COLUMNS  = %d\nBA_SKILL_COLUMN_DX = %d\nBA_SKILL_NAME_DX  = %d\nBA_SKILL_NAME_WIDTH = %d\n\
             BA_SKILL_DASH_DX  = %d\nBA_SKILL_COST_DX  = %d\nBA_SKILL_COST_DIGITS = %d\n",
            x.rom_skills.len(),
            pos(bs.n("BA_SKILL_DESC_ROW"), bs.n("BA_SKILL_DESC_COL")),
            pos(bs.n("BA_SKILL_ROW0"), 0),
            bs.n("BA_SKILL_ROWS"),
            bs.n("BA_SKILL_COLUMNS"),
            bs.n("BA_SKILL_COLUMN_DX") * 2,
            bs.n("BA_SKILL_NAME_COL") * 2,
            bs.n("BA_SKILL_NAME_WIDTH"),
            bs.n("BA_SKILL_DASH_COL") * 2,
            bs.n("BA_SKILL_COST_COL") * 2,
            bs.n("BA_SKILL_COST_DIGITS")
        ));
        out.push_str(".segment \"RODATA\"\n");
        let mut txt = Vec::new();
        for c in commands {
            let name = text(c)?;
            let k = BATTLE_TERMS
                .iter()
                .position(|(n, _)| *n == name)
                .ok_or_else(|| Bad::answer(format!("the battle command {name:?} is not a term")))?;
            txt.push(x.battle_text + k as i64);
        }
        // Two bytes: a text index does not fit in one.
        words_asm(out, "ba_command_txt", &decimal(txt), true);
        let undone: BTreeSet<i64> = ints(bs.v("BA_COMMAND_UNDONE"))?.into_iter().collect();
        bytes_asm(
            out,
            "ba_command_gray",
            &decimal((0..commands.len() as i64).map(|k| i64::from(undone.contains(&k)))),
            true,
        );
        out.push_str(".segment \"TABLES\"\n");
        self.tail(out)
    }

    fn tail(&self, out: &mut String) -> Result<()> {
        let r = self.r;
        // `font_color` in bank 0: the console reads it with
        // `lda font_color, y`, which addresses the data bank.
        let colors: Vec<u8> = ints_at(at(self.screens, "window")?, "color")?
            .into_iter()
            .map(|c| c as u8)
            .collect();
        line(out, &unplaced("font_color", &colors));
        // A game can start with the party empty, as RM2k allows: the label
        // stays, with no bytes —`.byte` with nothing after it does not
        // assemble—, and `boot` copies none.
        if r.party.is_empty() {
            out.push_str("party_initial:                ; the party starts empty\n\n");
        } else {
            out.push_str(&format!(
                "party_initial:\n    .byte {}\n\n",
                decimal(r.party.iter()).join(",")
            ));
        }
        line(out, &sine_table());
        // How many frames a character stays still after a step and after a
        // turn, per route frequency: RM2k's stop counters. 0 does not
        // compile, nor 1 in a route; 1 is there for a page that walks by a
        // movement type, with its 256 frames after a step held at the
        // byte's 255 —see `route::own` in the compiler—.
        let per_frequency = |f: fn(u32) -> u32| {
            decimal((0..=ROUTE_FREQUENCY).map(|q| if q >= 1 { f(q).min(255) } else { 0 })).join(",")
        };
        out.push_str(&format!(
            "route_after_step:\n  .byte {}\n",
            per_frequency(wait_after_step)
        ));
        out.push_str(&format!(
            "route_after_turn:\n  .byte {}\n\n",
            per_frequency(wait_after_turn)
        ));
        Ok(())
    }
}

/// What used to be appended after the `.inc`: which entries of its palette
/// the timer's digits use, per map, and where the harness writes the case
/// number.
fn timer_and_case(out: &mut String, r: &Emit) {
    let masks: Vec<String> = r
        .maps
        .iter()
        .map(|m| format!("${:04X}", m.sprite.as_ref().map_or(0, |s| s.timer_mask)))
        .collect();
    out.push_str(&format!(
        "\n.segment \"RODATA\"\n.block {}\ntimer_mask:\n    .word {}\n",
        2 * masks.len(),
        masks.join(", ")
    ));
    // And what each map forbids, one byte per map: `map_access_enter`
    // writes it over the permissions when the map is entered.
    let access: Vec<String> = r.maps.iter().map(|m| format!("${:02X}", m.access)).collect();
    out.push_str(&format!(
        ".block {}\nmap_access:\n    .byte {}\n",
        access.len().max(1),
        if access.is_empty() { "0".to_string() } else { access.join(", ") }
    ));
    if let Some(slot) = r.case_slot {
        out.push_str(&format!("\nCASE_SLOT = {slot}\n"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_crc_is_zlib_s() {
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
    }

    #[test]
    fn json_is_written_as_python_writes_it() {
        let v = serde_json::json!([[1, 2], [3, null]]);
        assert_eq!(python_json(&v), "[[1, 2], [3, null]]");
        assert_eq!(python_json(&serde_json::json!([])), "[]");
    }

    /// The switch table is the game's: ABL names up to 1008, Vampires Dawn
    /// up to 1643; and 2047 is the last its 256 bytes hold.
    #[test]
    fn the_switch_table_is_the_games() {
        assert_eq!(switch_bytes(0).unwrap(), 1);
        assert_eq!(switch_bytes(1008).unwrap(), 127);
        assert_eq!(switch_bytes(1643).unwrap(), 206);
        assert_eq!(switch_bytes(2047).unwrap(), 256);
        assert!(switch_bytes(2048).is_err());
    }
}
