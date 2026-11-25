//! The whole `.inc`: the header of constants, the maps —see [`record`]—,
//! the message window and its font, the picture, the battle animations,
//! the title and the full screens, the slots screen and the pause menu,
//! the item, equipment and shop screens, the battle and its tables, the
//! troops and their pages, the battle scene, and the tables the console
//! reads from bank 0.

use crate::asm::{block, unplaced, Inc};
use crate::cgram::{cgram_reserved, PRIORITY_ABOVE, WINDOW_PALETTE};
use crate::engine::*;
use crate::fail::{Bad, Result};
use crate::json::{ints, list, text};
use crate::objects::{LAYER_ABOVE, LAYER_SAME, OBJ_COLORS, OBJ_PRIORITY, OBJ_PRIORITY_ABOVE};
use crate::record::{
    self, ACTOR_BYTES, ACTOR_COLORS, ANIM_FAM_STRIDE, ANIM_STRIDE, EV_MAX, EV_STRIDE, FAMILIES,
    FLASH_MAX, MAP_STRIDE, NPC_MAX, NPC_STILL, NPC_STRIDE, PAGE_BYTES, PARALLEL_MAX, ROUTE_EV_MAX,
    TURN_NONE, TWIN_STRIDE,
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
use rm2k_snes_battle::encounters;
use rm2k_snes_battle::rules;
use rm2k_snes_events::answer::BattleAudio;
use rm2k_snes_screens::answer::{Answer, OtherSystem, SystemWindow};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};

mod custom_menu;
mod debug_screen;
mod header;
mod skills_screen;
use header::header;

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

/// The battle's commands, in the order the console puts them —the screen
/// geometry's `BA_COMMANDS`—, by the name [`BATTLE_TERMS`] gives the 2000
/// term of each.
/// `lcf::rpg::Item::Type`'s armors, the first and the last: shield, armor,
/// helmet and accessory.
const ITEM_SHIELD: i32 = 2;
const ITEM_ACCESSORY: i32 = 5;
/// The bit of `item_use` that says an armor spares its wearer a terrain's
/// damage —`no_terrain_damage`—. The others are 1 usable on the map, 4 opens
/// the actor choice and 8 a two-handed weapon.
const ITEM_USE_NO_TERRAIN_DAMAGE: i64 = 0x10;

const BA_COMMAND_TERMS: [&str; 5] = ["attack", "skill", "defend", "use", "escape"];

/// The terms of the lines a skill writes on each target under its using
/// ones, since 2026-10-20 —see `ba_result` in the runtime's battle.s—: the
/// failure, by the skill's `failure_message`, and what moved,
/// `<target> <points> <n><hp_recovery>` and `<target> <attack>
/// <n><parameter_increase>`. A medicine's recovery line writes the points
/// with these too: `GetHpSpRecoveredMessage` asks for `health_points` and
/// `spirit_points`, not the short ones the party's window writes —they
/// differ in The Book of Three, `H` and `HP`—. They go after every other
/// text, so the ones before keep their numbers, and **in this order**: the
/// console adds `failure_message` to `fail_a`'s number and what moved to
/// `hp_points`'.
pub const RESULT_TERMS: [(&str, &str); 12] = [
    ("fail_a", "skill_failure_a"),
    ("fail_b", "skill_failure_b"),
    ("fail_c", "skill_failure_c"),
    ("dodge", "dodge"),
    ("up", "parameter_increase"),
    ("down", "parameter_decrease"),
    ("hp_points", "health_points"),
    ("sp_points", "spirit_points"),
    ("atk", "attack"),
    ("def", "defense"),
    ("spi", "spirit"),
    ("agi", "agility"),
];

/// A term of the database, by liblcf's name: `Terms` serializes each field
/// by that name. In the resolved view, or a term the game left at its
/// default would be left out and read as no term.
fn term(db: &Db, name: &str) -> Result<String> {
    let terms = ditto::lcf::as_resolved(|| serde_json::to_value(&db.terms))
        .expect("the terms are strings, and strings go into JSON");
    terms
        .get(name)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| Bad::usage(format!("there is no term {name:?}")))
}

/// The terms of [`BATTLE_TERMS`] that RPG Maker 2003's battle never
/// writes, with the plain English that stands in for each in a 2003 game
/// whose project does not give them. Its battle tells a hit by a number
/// that floats over the target and asks for these only with the 2000
/// battle —easyrpg's `Game_BattleAlgorithm::*::GetStartMessage` and
/// `Scene_Battle_Rpg2k3`—, so whatever a 2003 database holds in them its
/// author never saw: Zounds' are the editor's Japanese defaults, read as
/// Windows-1252, and the console wrote `Kazar 3'I?_???[?W…` until
/// 2026-10-19. The console fights with the 2000 battle, which writes them.
/// Each goes after a name, as `<who><attacking>`, `<target>
/// <n><actor_damaged>`, `<who> <item><use_item>`, `<target> HP
/// <n><hp_recovery>`, `<target><skill_failure_a>` and `<target> Attack
/// <n><parameter_increase>` —see `ba_message` in the runtime's battle.s—.
pub const UNSHOWN_IN_2003: [(&str, &str); 15] = [
    ("attacking", " attacks!"),
    ("defending", " defends."),
    ("actor_critical", " A critical hit!"),
    ("enemy_damaged", " HP lost."),
    ("enemy_undamaged", " takes no damage."),
    ("actor_damaged", " HP lost."),
    ("actor_undamaged", " takes no damage."),
    ("use_item", " used."),
    ("hp_recovery", " recovered."),
    ("skill_failure_a", " is not affected."),
    ("skill_failure_b", " is not affected."),
    ("skill_failure_c", " is not affected."),
    ("dodge", " dodges the attack."),
    ("parameter_increase", " up."),
    ("parameter_decrease", " down."),
];

/// A battle term as the battle writes it: the project's `[battle.terms]`
/// if it gives it, the English stand-in of [`UNSHOWN_IN_2003`] if the game
/// is 2003's and its battle never wrote it, and the database's otherwise.
fn battle_term(given: &BTreeMap<String, String>, db: &Db, name: &str) -> Result<String> {
    if let Some(given) = given.get(name) {
        return Ok(given.clone());
    }
    if db.is_2003 {
        if let Some((_, stand_in)) = UNSHOWN_IN_2003.iter().find(|(n, _)| *n == name) {
            return Ok(stand_in.to_string());
        }
    }
    term(db, name)
}

/// The battle terms that come from the battle's model and not from
/// [`battle_term`]: the commands, trimmed and, in a 2003 game, from its
/// battle commands —see `actor_command_txt`—, and the victory, split. The
/// skill and item commands joined them on 2026-10-20: until then a project
/// could give `command_skill` and `command_item`, and no project did.
const FROM_THE_MODEL: [&str; 6] = ["attack", "defend", "escape", "victory", "use", "skill"];

/// That every term the project gives is one [`battle_term`] answers.
fn check_battle_terms(r: &Emit) -> Result<()> {
    let given = BATTLE_TERMS
        .iter()
        .filter(|(short, _)| !FROM_THE_MODEL.contains(short))
        .chain(RESULT_TERMS.iter());
    for name in r.battle_terms.keys() {
        if !given.clone().any(|(_, liblcf)| liblcf == name) {
            return Err(Bad::usage(format!(
                "[battle.terms] gives {name:?}, which is not a term the battle writes: \
                 they are {}",
                given
                    .clone()
                    .map(|(_, liblcf)| *liblcf)
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
    }
    Ok(())
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

/// Numbers the runtime does not name, written as equates for whoever reads
/// the cartridge's `.dbg` and `.sym` instead of asking a stage: a game's
/// tests, a debugger. An equate costs no ROM byte, and no `.ifdef` of the
/// runtime looks at these names. Each one is here because a test reads it,
/// by the name it has in its stage —`engine.rs`, the screens' and the
/// battle's geometry—; the ones the `.inc` already writes under their own
/// name are read from there. Until 2026-11-25 the tests asked the stages for
/// all of them: `rm2k-snes-mapdata engine`, `rm2k-snes-screens layout` and
/// `rm2k-snes-battle layout`.
fn for_readers(t: &Geometry, bs: &Geometry) -> String {
    let mut text = String::from(
        "; For the readers of the .dbg —a game's tests, a debugger—: numbers\n\
         ; the runtime does not name, which cost no ROM. See `for_readers`.\n",
    );
    let numbers = [
        // The text block's step, which `OP_MESSAGE` counts in.
        ("MESSAGES_STEP", MESSAGES_STEP as i64),
        // The item screen's geometry, in pixels and cells.
        ("ITEM_HELP_HEIGHT", t.n("ITEM_HELP_HEIGHT")),
        ("ITEM_LIST_Y", t.n("ITEM_LIST_Y")),
        ("ITEM_NAME_WIDTH", t.n("ITEM_NAME_WIDTH")),
        // The battle's message rows and column, in cells; the `.inc` writes
        // them as places in the text layer, `BA_MSG_POS1` and company.
        ("BA_MSG_ROW1", bs.n("BA_MSG_ROW1")),
        ("BA_PAGE_MSG_ROW0", bs.n("BA_PAGE_MSG_ROW0")),
        ("BA_PAGE_MSG_COL", bs.n("BA_PAGE_MSG_COL")),
        // The battle model's commands and outcomes, as its requests and
        // answers carry them: see `simulate.rs` in rm2k-snes-battle.
        ("COMMAND_ATTACK", bs.n("COMMAND_ATTACK")),
        ("COMMAND_DEFEND", bs.n("COMMAND_DEFEND")),
        ("COMMAND_ITEM", bs.n("COMMAND_ITEM")),
        ("COMMAND_SKILL", bs.n("COMMAND_SKILL")),
        ("VICTORY", bs.n("VICTORY")),
        ("DEFEAT", bs.n("DEFEAT")),
    ];
    for (name, value) in numbers {
        text.push_str(&format!("{name:<17} = {value}\n"));
    }
    text.push('\n');
    text
}

/// What the battle's model answered for the number `n`, or why not.
fn by_number<'a, T>(answered: &'a BTreeMap<i32, T>, n: i64, what: &str) -> Result<&'a T> {
    i32::try_from(n)
        .ok()
        .and_then(|n| answered.get(&n))
        .ok_or_else(|| Bad::answer(format!("the battle's model has nothing of {what} {n}")))
}

/// The text block of the text screens, which the console names by index.
struct Texts {
    data: Vec<u8>,
    offsets: Vec<(usize, usize)>,
    first: usize,
    count: usize,
    /// The glyphs past the console's the screens' tables carry: see
    /// [`ScreenGlyphs`].
    glyphs: ScreenGlyphs,
}

/// What the text screens draw past the console's 96 glyphs, as the screens
/// stage decided it: the ExFont icons, in their order —see `Inks` there—,
/// and the Latin-1 letters they reach, the font's from `letters_at` on —see
/// `texts::ScreenLetters` there—. A screen's byte is its glyph plus 32.
#[derive(Debug, Clone, Default)]
struct ScreenGlyphs {
    icons: Vec<usize>,
    letters: Vec<char>,
    letters_at: usize,
}

impl ScreenGlyphs {
    /// The screens stage's: its `text_inks`' icons and its `font`'s
    /// letters.
    fn of(screens: &Answer) -> ScreenGlyphs {
        ScreenGlyphs::new(
            screens.text_inks.icons.clone(),
            screens.font.screen_letters.clone(),
            screens.font.letters_at,
        )
    }

    /// The letters past `SCREEN_GLYPHS` are not carried: a screen's byte
    /// would not hold them. The screens stage already stops there; this is
    /// the emission's half of the same rule.
    fn new(icons: Vec<usize>, mut letters: Vec<char>, letters_at: usize) -> ScreenGlyphs {
        letters.truncate(rm2k_snes_text::font::SCREEN_GLYPHS.saturating_sub(letters_at));
        ScreenGlyphs {
            icons,
            letters,
            letters_at,
        }
    }

    /// `text` as the screens write it: its icons as halves, the letters
    /// they carry as they are, and every other letter as its plain
    /// stand-in —see `rm2k_snes_text::plain::screen_text`—.
    fn text(&self, text: &str) -> String {
        rm2k_snes_text::plain::screen_text(text, &self.letters)
    }

    /// A text's byte for a character of [`ScreenGlyphs::text`]'s, `None`
    /// for an icon's half the tables do not carry and anything else that is
    /// not the console's.
    fn byte(&self, c: char) -> Option<u8> {
        if let Some((icon, side)) = rm2k_snes_text::exfont::half_of(c) {
            let k = self.icons.iter().position(|&i| i == icon)?;
            return Some((ICON_CODE_FIRST + 2 * k + side) as u8);
        }
        if let Some(k) = self.letters.iter().position(|&l| l == c) {
            return Some((32 + self.letters_at + k) as u8);
        }
        (c == ' ' || c.is_ascii_graphic()).then_some(c as u8)
    }
}

/// A name or a term of the database as the text screens write it —an
/// actor's `Unamë`, as `Uname` where the cartridge carries no `ë`, see
/// [`ScreenGlyphs::text`]—, and without its ExFont icons, which the menu's
/// bank and a message box's names do not draw.
fn plain(glyphs: &ScreenGlyphs, text: &str) -> String {
    rm2k_snes_text::exfont::without_icons(&glyphs.text(text))
}

/// A text of the database's for the battle's lists and messages —a
/// skill's name, description and using messages, an enemy's name, a
/// condition's—: [`plain`]'s letters, but **with its ExFont icons**,
/// which [`Texts::add`] writes when the screens' tables carry them —
/// Zounds' `$LLátigo de Seda`, its icon and `Látigo de Seda`—, as
/// `item_text` does in the screens stage. Until 2026-11-22 these went to
/// [`Texts::add`] raw, and every accent was a `?`; and until the screens
/// drew Latin-1, the same day, each was its plain stand-in.
fn db_text(glyphs: &ScreenGlyphs, text: &str) -> String {
    glyphs.text(text)
}

/// A name on the actor choice's line on top, as the screens stage stored
/// it —`target_text`, its letters already the console's or the screens'
/// and its ExFont icons as halves—: its bytes, `width` of them. A half goes
/// as the text layer's byte for it, as [`Texts::add`] writes it: the menu's
/// bank, where the line is composed, carries the same glyphs as the
/// screens' tables. One whose icon they do not carry is dropped, and the
/// name padded again. Anything else is the stage's mistake, said here
/// rather than drawn as another letter.
fn target_name_bytes(name: &str, width: usize, glyphs: &ScreenGlyphs) -> Result<Vec<u8>> {
    let bad = || {
        Bad::answer(format!(
            "the actor choice's name {name:?} is not {width} letters of the console's"
        ))
    };
    if name.chars().count() != width {
        return Err(bad());
    }
    let mut out = Vec::with_capacity(width);
    for c in name.chars() {
        match glyphs.byte(c) {
            Some(b) => out.push(b),
            None if rm2k_snes_text::exfont::is_half(c) => {}
            None => return Err(bad()),
        }
    }
    out.resize(width, b' ');
    Ok(out)
}

/// A row of the actors' strips, `width` letters, as the text screens write
/// it: [`target_name_bytes`]'s rule, without the icons the strips never
/// carry, and padded with spaces.
fn strip_bytes(row: &str, width: usize, glyphs: &ScreenGlyphs) -> Result<Vec<u8>> {
    let mut out = Vec::with_capacity(width);
    for c in row.chars() {
        out.push(glyphs.byte(c).ok_or_else(|| {
            Bad::answer(format!(
                "the slot screen's row {row:?} has a letter the screens do not draw: {c:?}"
            ))
        })?);
    }
    if out.len() < width {
        out.resize(width, b' ');
    }
    Ok(out)
}

/// The byte the text layer reads as the first half of the first icon the
/// screens' tables carry: their glyph `ICON_GLYPH_FIRST` —past the console's
/// 96 and `TL_FIGURE`— plus 32, since a letter is its byte less 32.
const ICON_CODE_FIRST: usize = 32 + rm2k_snes_text::font::CONSOLE_GLYPHS + 1;

impl Texts {
    /// What the text screens' font can write: the characters it has, the
    /// letters and icons [`ScreenGlyphs`] carries, a `?` for the others,
    /// cut to `width` —`item_text` in the screens stage—. What comes from
    /// the screens stage has its letters stood in already; what comes from
    /// the database goes through [`plain`] first, or [`db_text`] where its
    /// icons are drawn.
    ///
    /// An ExFont icon —a code of the database's, or the halves the screens
    /// stage left— goes as its two halves' bytes, the text layer's glyph
    /// plus 32, if the screens' tables carry it, and is dropped if they do
    /// not: see `ICON_GLYPH_FIRST` in the screens stage. A letter goes as
    /// its glyph plus 32, past every icon.
    fn add(&mut self, text: &str) -> i64 {
        let fitted: Vec<u8> = rm2k_snes_text::exfont::with_icons(text)
            .chars()
            .filter_map(|c| {
                if rm2k_snes_text::exfont::is_half(c) || self.glyphs.letters.contains(&c) {
                    return self.glyphs.byte(c);
                }
                let n = c as usize;
                Some(if (self.first..self.first + self.count).contains(&n) {
                    n as u8
                } else {
                    b'?'
                })
            })
            .take(255)
            .collect();
        self.offsets.push((self.data.len(), fitted.len()));
        self.data.extend_from_slice(&fitted);
        self.offsets.len() as i64 - 1
    }

    /// A database text per id, through [`db_text`] and [`add`](Self::add),
    /// in the order of `ids` —which is the order they are numbered in, and
    /// the numbers are in the ROM—: each id's number.
    fn add_each<'t>(
        &mut self,
        ids: &[i64],
        text: impl Fn(i64) -> Result<&'t str>,
    ) -> Result<HashMap<i64, i64>> {
        let mut numbers = HashMap::new();
        for &id in ids {
            let shown = db_text(&self.glyphs, text(id)?);
            numbers.insert(id, self.add(&shown));
        }
        Ok(numbers)
    }
}

/// What a byte table that says 0 when there is nothing, and not the `$FF`
/// of [`Inc::bytes`], puts through it. Each of them always wrote its 0, and
/// those bytes are in the ROM.
fn or_zero(values: Vec<String>) -> Vec<String> {
    if values.is_empty() {
        vec!["0".to_string()]
    } else {
        values
    }
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
fn cell_words(cells: &[u16], priority: u32) -> Vec<u8> {
    words_le(
        cells
            .iter()
            .map(|&c| entry(c.into(), false, false, priority)),
    )
}

/// Tiles in the PPU's format.
fn packed<T: AsRef<[R]>, R: AsRef<[u8]>>(cells: &[T], planes: usize) -> Vec<u8> {
    cells
        .iter()
        .flat_map(|c| pack_tile(c.as_ref(), planes))
        .collect()
}

/// A tilemap's words, little-endian.
fn words(cells: &[u16]) -> Vec<u8> {
    words_le(cells.iter().map(|&w| w.into()))
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

/// A sprite palette: the transparent entry, then `colors`, cut or padded
/// with black to sixteen.
fn palette16(colors: &[Color]) -> Vec<u8> {
    let mut sixteen = vec![[0, 0, 0]];
    sixteen.extend_from_slice(colors);
    sixteen.resize(16, [0, 0, 0]);
    cgram_bytes(&sixteen)
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

/// How many bytes the ROM's switch table takes, a bit per switch from 0 to
/// `top`, the highest the game names. It lives in the cartridge's `SWITCHRAM`,
/// 256 bytes of far RAM, and a game past it is refused before this: see
/// `switch_top` in the event compiler.
pub fn switch_bytes(top: i64) -> Result<i64> {
    let bytes = top.max(0) / 8 + 1;
    if bytes > 256 {
        return Err(Bad::answer(format!(
            "switch {top} does not fit the ROM's switch table, 256 bytes"
        )));
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
    experience: &[Option<i64>],
    n_actors: i64,
    switch_bytes: i64,
) -> u32 {
    // A struct and not `json!`: its fields go in this order whether or not
    // serde_json preserves the order of an object's keys, which depends on
    // the features other crates of the build ask for.
    #[derive(serde::Serialize)]
    struct Shape<'a> {
        variables: &'a [(i64, i64)],
        items: usize,
        switches: i64,
        actors: i64,
        skills: &'a [(i64, i64, i64)],
        experience: &'a [Option<i64>],
    }
    let shape = Shape {
        variables,
        items: ITEMS_N,
        switches: switch_bytes,
        actors: n_actors,
        skills: pairs,
        experience,
    };
    let text = serde_json::to_string(&shape).expect("the shape is plain JSON");
    crc32(text.as_bytes()) & 0xFFFF
}

/// The sine the screen shake reads by index, in bank 0's neighbour.
fn sine_table() -> String {
    let mut out = vec![
        "; The sine at scale 127, for the screen shake: `shake_sine` in".to_string(),
        "; rm2k-snes-mapdata's engine.rs.".into(),
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
    check_battle_terms(r)?;
    let screens = &r.screens;
    let t = Geometry(&screens.layout);
    let model = &r.battle_model;
    let bs = Geometry(&model.layout);
    let slot_text_max = SLOT_TEXT_LEVEL as i64 + t.n("LEVEL_DIGITS");

    // Everything that goes per map, first: it is also where what each map
    // spends is checked against its VRAM layout.
    let per_map = record::maps_with(&r.maps, r.rom.msu != MsuData::Optional)?;

    let windows = normalized_windows(&screens.window.system, &r.window_systems)?;
    let window = &windows[0];
    let slots = &screens.slots;
    let title = r.title.as_ref();
    let title_menu = match title {
        Some(_) => Some(
            screens
                .title
                .as_ref()
                .ok_or_else(|| Bad::answer("the cartridge has a title and the screens no menu"))?,
        ),
        None => None,
    };
    let variables_n = r.variables.len().max(1);
    if variables_n > 256 {
        return Err(Bad::answer(format!(
            "{variables_n} variables don't fit in far RAM: FAR_ITEMS is 512 bytes from FAR_VARIABLES"
        )));
    }
    let faces: BTreeMap<i64, &Vec<u16>> = slots.faces.iter().map(|(&k, v)| (k.into(), v)).collect();
    let cell = CELL;
    let cols = COLS;
    // The RAM table of route graphics, as big as the map that asks for most:
    // see `route_gfx_buf` in runtime/far_ram.s. At least one entry, so the
    // `.res` is never empty.
    let route_gfx_max = r
        .maps
        .iter()
        .filter_map(|m| m.sprite.as_ref().map(|s| s.route_gfx.len()))
        .max()
        .unwrap_or(0)
        .max(1);

    // Where the slot screen's names go.
    let slot_names = slots.slot_names;
    let menu_counts = title_menu.map_or((0, 0), |menu| (menu.tiles.len(), menu.texts.len()));
    let mut out = Inc::new(format!(
        header!(),
        maps = r
            .maps
            .iter()
            .map(|m| format!("{} {}", m.id, m.name))
            .collect::<Vec<_>>()
            .join(", "),
        map_count = r.maps.len(),
        map_stride = MAP_STRIDE,
        map_initial = r.start,
        vram_above_map = VRAM_ABOVE_MAP,
        map_layout = MAP_LAYOUT,
        npc_stride = NPC_STRIDE,
        npc_max = NPC_MAX,
        npc_still = NPC_STILL,
        ev_stride = EV_STRIDE,
        ev_max = EV_MAX,
        twin_stride = TWIN_STRIDE,
        route_ev_max = ROUTE_EV_MAX,
        page_bytes = PAGE_BYTES,
        turn_none = TURN_NONE,
        route_gfx_max = route_gfx_max,
        header_lines = HEADER_LINES,
        header_autoclose = HEADER_AUTO_CLOSE,
        pause_frames = PAUSE_FRAMES,
        var_refresh = VAR_REFRESH,
        var_slot = VAR_SLOT_MAX,
        anim_entry = ANIM_ENTRY_BYTES,
        anim_sound = ANIM_SOUND,
        anim_flash = ANIM_SCREEN_FLASH,
        key_wait = KEY_WAIT,
        key_dirs = KEY_DIRS,
        key_decision = KEY_DECISION,
        key_cancel = KEY_CANCEL,
        key_starts = KEY_START,
        key_value_decision = KEY_VALUE_DECISION,
        key_value_cancel = KEY_VALUE_CANCEL,
        key_value_up = KEY_VALUE_DIR[0],
        key_value_right = KEY_VALUE_DIR[1],
        key_value_left = KEY_VALUE_DIR[3],
        key_value_down = KEY_VALUE_DIR[2],
        picture_obj_stride = OBJ_SIDE,
        picture_row_stride = (4 * GRID),
        rain_drops_max = RAIN_DROPS.iter().copied().max().unwrap_or(0),
        rain_drops_0 = RAIN_DROPS[0],
        rain_drops_1 = RAIN_DROPS[1],
        rain_drops_2 = RAIN_DROPS[2],
        rain_life = RAIN_LIFE,
        rain_born = RAIN_SPAWN,
        rain_seed = RAIN_SEED,
        weather_rain = WEATHER_RAIN,
        weather_sand = WEATHER_SAND,
        items_n = ITEMS_N,
        item_max = ITEM_MAX,
        variables_n = variables_n,
        var_add = VAR_ADD,
        var_variable = VAR_VARIABLE,
        var_random = VAR_RANDOM,
        var_other = VAR_OTHER,
        var_character = VAR_CHARACTER,
        character_x = CHARACTER_X,
        character_y = CHARACTER_Y,
        var_actor = VAR_ACTOR,
        cell_y = CELL_Y,
        cell_refresh = CELL_REFRESH,
        random_seed = RANDOM_SEED,
        enc_seed = ENC_SEED,
        timer_set_var = TIMER_SET_VAR,
        timer_slot = TIMER_SLOT,
        cond_timer = COND_TIMER,
        cond_gold = COND_GOLD,
        cond_item = COND_ITEM,
        cond_actor = COND_ACTOR,
        cond_actor_skill = COND_ACTOR_SKILL,
        cond_actor_equipment = COND_ACTOR_EQUIPMENT,
        cond_actor_hp = COND_ACTOR_HP,
        cond_actor_state = COND_ACTOR_STATE,
        gold_max = GOLD_MAX,
        pan_lock = PAN_LOCK,
        pan_unlock = PAN_UNLOCK,
        pan_run = PAN_SHIFT,
        pan_return = PAN_RETURN,
        timer_set = TIMER_SET,
        timer_start = TIMER_START,
        timer_x = TIMER_X,
        timer_y = TIMER_Y,
        timer_glyph_w = TIMER_GLYPH_W,
        timer_two_points = (TIMER_GLYPHS - 1),
        timer_frames = FRAMES_PER_SECOND,
        more_timer = TIMER_EXTRA_FRAMES,
        flash_max = FLASH_MAX,
        parallel_max = PARALLEL_MAX,
        trigger_auto = TRIGGER_AUTOSTART,
        trigger_action = TRIGGER_ACTION,
        trigger_touches_hero = TRIGGER_TOUCH_HERO,
        trigger_collision = TRIGGER_COLLISION,
        trigger_parallel = TRIGGER_PARALLEL,
        frames_per_cell = FRAMES_PER_CELL,
        route_frequency = ROUTE_FREQUENCY,
        route_wait = ROUTE_WAIT_FRAMES,
        jump_step = JUMP_STEP,
        tint_neutral = NEUTRAL_TINT,
        fade_load_tick = FADE_RAMP,
        fade_total = FADE_TOTAL,
        fade_ramp = FADE_RAMP,
        fade_load = FADE_RAMP,
        brightness_max = BRIGHTNESS_MAX,
        transition_mosaic = TRANSITION_MOSAIC,
        transition_cutoff = TRANSITION_CUT,
        light_r = LUMA_R,
        light_g = LUMA_G,
        light_b = LUMA_B,
        switch_bytes = switch_bytes(r.switch_top)?,
        party_max = PARTY_MAX,
        party_initial_n = r.party.len(),
        actor_bytes = ACTOR_BYTES,
        actor_colors = ACTOR_COLORS,
        obj_colors = OBJ_COLORS,
        hero_layer = LAYER_SAME,
        hero_priority = (if r.hero_above {
            OBJ_PRIORITY_ABOVE
        } else {
            OBJ_PRIORITY
        }),
        layer_above = LAYER_ABOVE,
        npc_priority = OBJ_PRIORITY,
        npc_priority_above = OBJ_PRIORITY_ABOVE,
        cgram_base = cgram_reserved(r.window_colors),
        window_cgadd = (WINDOW_PALETTE as usize * COLORS_PER_PALETTE),
        window_tiles = (window.tiles.len() / 32),
        window_rows_ = t.n("WINDOW_ROWS_INC"),
        text_window_cols = t.n("WINDOW_COLS_INC"),
        window_text_base = window.base,
        window_text_row = t.n("WINDOW_TEXT_ROW"),
        window_text_rows = t.n("WINDOW_TEXT_ROWS"),
        window_text_col = t.n("WINDOW_TEXT_COL"),
        window_text_cols = t.n("WINDOW_TEXT_COLS"),
        message_width = t.n("MESSAGE_WIDTH"),
        font_height = t.n("FONT_HEIGHT"),
        font_width = t.n("FONT_WIDTH"),
        font_shadow = window.shadow,
        font_pre_rows = t.n("FONT_PRE_ROWS"),
        font_pre_char = t.n("FONT_PRE_CHAR"),
        choice_indent = t.n("CHOICE_INDENT"),
        msg_face_row = t.n("MSG_FACE_ROW"),
        msg_face_col_left = t.n("MSG_FACE_COL_LEFT"),
        msg_face_col_right = t.n("MSG_FACE_COL_RIGHT"),
        msg_face_text_x = t.n("MSG_FACE_TEXT_X"),
        msg_face_right_x = t.n("MSG_FACE_RIGHT_X"),
        window_arrow_row = t.n("WINDOW_ARROW_ROW"),
        window_arrow_col = t.n("WINDOW_ARROW_COL"),
        window_arrow_cells = t.n("WINDOW_ARROW_CELLS"),
        anim_families = FAMILIES.len(),
        anim_stride = ANIM_STRIDE,
        anim_fam_stride = ANIM_FAM_STRIDE,
        water_frames = WATER_FRAMES_SLOW,
        water_drawings = FAMILIES[0].2,
        water_cycle_n = WATER_CYCLE,
        animated_frames = ANIMATED_FRAMES,
        animated_steps = ANIMATED_STEPS,
        bytes_per_tile = BYTES_PER_TILE,
        title_tiles = title.map_or(0, |full| full.tiles),
        title_bpp = title.map_or(8, |full| full.bpp),
        title_menu_cgram = MENU_CGRAM,
        title_menu_tiles = menu_counts.0,
        title_menu_n = menu_counts.1,
        slot_vram = SLOT_VRAM,
        slot_map = SLOT_MAP,
        sram_slots_n = slots.rows.len(),
        slot_tiles = slots.tiles.len(),
        slot_menu_tiles = slots.menu_tiles,
        slot_names_first = slot_names.0,
        slot_names_end = slot_names.1,
        slot_hdr_row = (t.n("HEADER_Y").div_euclid(cell)),
        slot_hdr_rows = t.n("HEADER_ROWS"),
        slot_hdr_cells = (t.n("HEADER_ROWS") * cols),
        slot_row0 = (t.n("SLOT_Y").div_euclid(cell)),
        slot_jump = (t.n("SLOT_STEP").div_euclid(cell)),
        slot_rows = t.n("SLOT_ROWS"),
        slot_cells = (t.n("SLOT_ROWS") * cols),
        slot_hdr_vram = (t.n("HEADER_Y").div_euclid(cell) * 32),
        slot_faces_max = t.n("FACES_MAX"),
        slot_face_cols = t.n("FACE_CELLS"),
        slot_face_rows = t.n("FACE_CELLS"),
        slot_name_cols = t.n("NAME_COLS"),
        slot_text_width = SLOT_TEXT_WIDTH,
        slot_text_level = SLOT_TEXT_LEVEL,
        slot_text_max = slot_text_max,
        slot_level_digits = t.n("LEVEL_DIGITS"),
        slot_level_ofs =
            ((t.n("LEVEL_ROW") - t.n("NAME_ROW")) * 32 + t.n("LEVEL_COL") - t.n("NAME_COL")),
        glyph_digit_0 = ((i64::from(b'0') - t.n("ITEM_FIRST_CHAR")) * 4),
        slot_actors_n = (faces
            .keys()
            .copied()
            .chain(r.actors.iter().copied())
            .max()
            .unwrap_or(-1)
            .max(-1)
            + 1),
        slot_cgram_n = (slots.palettes.len() * MENU_CGRAM),
        title_menu_cgram_again = MENU_CGRAM,
    ));

    out.push_str(&for_readers(&t, &bs));

    // Who the cartridge is.
    out.push_str(&format!(
        "; Who the ROM is, from the project file: the header title and\n\
         ; the signature with which the SRAM says a slot holds a save of\n\
         ; this game.\n\
         .define ROM_TITLE \"{:<21}\"\n\
         .define SRAM_MAGIC_TEXT \"{}\"\n\n",
        r.rom.title, r.rom.sram_signature
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
    out.push_str(&format!(
        "; Whether L and R change the hero's speed: see `hero_speed_keys.s`.\nHERO_SPEED_KEYS = {}\n\n",
        u8::from(r.speed_keys)
    ));
    out.push_str(&format!(
        "; Whether Select walks the hero through everything: see `phasing.s`.\nDEBUG_PHASING = {}\n\n",
        u8::from(r.phasing)
    ));
    // Only in a cartridge where some `Teleport` asks for a facing: one where
    // none does —every RM2k game's— gets the same `.inc` as before there was
    // one, and its runtime only the opcode's entry in the dispatch. See
    // `op_teleport_facing` in interpreter_teleport.s.
    if r.teleport_facing {
        out.push_str(
            "; Some Teleport asks for a facing: see `op_teleport_facing`.\n\
             TELEPORT_FACING = 1\n\n",
        );
    }
    // Only in a cartridge with some `ShowWindow`, RPG Maker 2000 PLUS's: one
    // without gets the same `.inc` as before there was one, and its runtime
    // only the two opcodes' entries in the dispatch. See show_window.s.
    if r.window_slots > 0 {
        out.push_str(&format!(
            "; The game's ShowWindows: a slot per window id. See show_window.s.\n\
             SHOW_WINDOW_SLOTS = {}\n\n",
            r.window_slots
        ));
    }
    // Only in a test cartridge that asks for it: the probe costs cycles in
    // every vblank, so the ROM that gets played does not carry it. See
    // `vblank_probe` in vblank.s.
    if r.vblank_probe {
        out.push_str(
            "; The vblank's last line, to RAM, for a test: see `vblank_probe`.\n\
             VBLANK_PROBE = 1\n\n",
        );
    }
    // The fade ramp, in bank 0: `fade_tick` reads it with `lda fade_ramp, x`.
    out.push_str(
        ".segment \"TABLES\"\n\
         ; The master brightness on each frame of the ramp, from\n\
         ; black to full. Going down it is read backwards.\n",
    );
    out.bytes_unplaced("fade_ramp", fade_ramp());
    out.push('\n');
    // The data goes in RODATA, which the linker spreads over the upper
    // banks; what stays in TABLES —bank 0— is what the console walks with a
    // bare `lda table, x`.
    out.push_str(".segment \"RODATA\"\n");
    out.push_str(&per_map.maps);

    let mut notes = per_map.notes.clone();
    window_section(&mut out, r, &windows, &t, screens)?;
    picture_section(&mut out, r, &mut notes)?;
    big_pictures_section(&mut out, r)?;
    animations_section(&mut out, r)?;
    title_section(&mut out, title_menu)?;
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
    custom_menu::section(&mut out, &screens.custom_menus)?;
    debug_screen::section(&mut out, screens.debug_screen.as_ref())?;
    skills_screen::section(&mut out, screens)?;
    out.push_str(&per_map.tables);
    timer_and_case(&mut out, r);
    Ok(Emitted {
        text: out.into_text(),
        notes,
        report: per_map.report,
        frames: per_map.frames,
        raw: per_map.raw,
    })
}

/// The cartridge's one font, colour-free, a table per phase, and the
/// colours each of its three writers puts in it —the message window, the
/// text screens and the slot bank—, as constants: the runtime's
/// `font_ink.inc` composes a letter with them as immediates. And where the
/// boxes' letters start in it. Until 2026-11-20 each writer had its own
/// table, already coloured: `font_pre`, `scr_pre` and `slot_pre`.
fn font_section(out: &mut Inc, screens: &Answer) -> Result<()> {
    let font = &screens.font;
    for (phase, data) in font.prerender.iter().enumerate() {
        out.block(format!("font_pre{phase}"), data);
    }
    out.push_str(&format!(
        "; The console's glyphs, and where a box's letter k is: glyph\n\
         ; FONT_LETTERS_AT + k of the font, past the screens' own.\n\
         FONT_CONSOLE_GLYPHS = {}\n\
         FONT_LETTERS_AT = {}\n",
        rm2k_snes_text::font::CONSOLE_GLYPHS,
        font.letters_at
    ));
    // And each letter the text screens carry, by its code point: the
    // glyph a screen's byte names, less 32. No byte of the ROM: a test
    // reads them from the symbols to decode what a screen wrote. The
    // halves of the boxes' icons among them are not letters, and the
    // screens write theirs with their own glyphs.
    let shown = ScreenGlyphs::of(screens);
    // How many the text screens reach, if any: with none, no name carries
    // a letter past the screens' icons, so `msg_name_letter` has nothing
    // to take back to the window's numbering, and without the symbol its
    // code is not assembled.
    if !shown.letters.is_empty() {
        out.push_str(&format!(
            "; The letters the text screens reach, from FONT_LETTERS_AT.\n\
             FONT_SCREEN_LETTERS = {}\n",
            shown.letters.len()
        ));
    }
    for (k, c) in shown.letters.iter().enumerate() {
        if rm2k_snes_text::exfont::is_half(*c) {
            continue;
        }
        out.push_str(&format!(
            "FONT_LETTER_{:04X} = {}\n",
            *c as u32,
            shown.letters_at + k
        ));
    }
    for (prefix, ink) in [
        ("MSG", &screens.window.font_ink),
        ("SCR", &screens.text_inks.font_ink),
        ("SLOT", &screens.slots.font_ink),
    ] {
        for (k, c) in ink.rows.iter().enumerate() {
            out.push_str(&format!("{prefix}_INK_{k} = {c}\n"));
        }
        out.push_str(&format!("{prefix}_INK_SHADOW = {}\n", ink.shadow));
    }
    out.push('\n');
    Ok(())
}

fn window_section(
    out: &mut Inc,
    r: &Emit,
    windows: &[SystemWindow],
    t: &Geometry,
    screens: &Answer,
) -> Result<()> {
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
    // How many wide variables the cartridge has: the event compiler lists
    // their high words' slots with the variable's number negated. Without
    // any, the runtime leaves out the code that compares them —see
    // `OP_IF_WIDE` in number_input.s—, which a cartridge tight in `FAR3`
    // has no room for.
    let wide = r.variables.iter().filter(|(v, _)| *v < 0).count();
    out.push_str(&format!("WIDE_VARIABLES = {wide}\n"));
    let one_line = windows.iter().all(|w| Backdrop::of(w, t).is_one_line());
    for (k, w) in windows.iter().enumerate() {
        window_pieces(out, r, w, t, &system_suffix(k), one_line)?;
    }
    if windows.len() > 1 {
        window_systems_table(out, windows.len());
    }
    let window = &screens.window;
    out.block("font_table", &window.font);
    // How far each letter moves the line, and how far it paints: the
    // composer adds the first and checks the second against the edge. The
    // message window's, with the letters its boxes draw; the text screens'
    // are `font_advance` and `font_reach`, further down.
    out.block("msg_font_advance", &window.advances);
    out.block("msg_font_reach", &window.reach);

    font_section(out, screens)?;
    out.block("messages", &r.messages);
    // How big it is and how big it can be, for the space a build measures: the operand
    // of `OP_MESSAGE` is sixteen bits, in steps of `MESSAGES_STEP`.
    out.push_str(&format!(
        "MESSAGES_BYTES = {}\nMESSAGES_CAP = {}\n",
        r.messages.len(),
        0x10000 * MESSAGES_STEP
    ));
    // The pairs its letters are written with, for `message_tick`.
    out.block("message_pairs", &r.message_pairs.table);
    out.push_str(&format!("MESSAGE_PAIR_FIRST = {}\n", r.message_pairs.first));
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
fn message_faces(out: &mut Inc, faces: &[MessageFace]) -> Result<()> {
    out.push_str(&format!(
        "; The faces of the message window: `MESSAGE_FACES` of `MESSAGE_FACE_BYTES`\n\
         ; each, and a long pointer to each one. See the runtime's message_face.s.\n\
         MESSAGE_FACES = {}\nMESSAGE_FACE_BYTES = {}\n",
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
        out.block(format!("message_face_{k}"), &data);
    }
    // The pointers, by hand: a word and a bank each, like `window_systems`.
    out.push_str(&format!(
        ".block {}\nmessage_face_ptr:\n",
        (faces.len() * 3).max(1)
    ));
    if faces.is_empty() {
        out.push_str("    .byte $FF\n");
    }
    for k in 0..faces.len() {
        out.far(&format!("message_face_{k}"));
    }
    out.push('\n');
    Ok(())
}

/// What goes after the labels of the `k`-th System's window pieces: nothing
/// for the System the cartridge starts with, `_k` for the `k`-th it
/// switches to.
fn system_suffix(k: usize) -> String {
    if k == 0 {
        String::new()
    } else {
        format!("_{k}")
    }
}

/// One System's message window: its tiles, its palette, its two planes of
/// cells for each window base, its arrow's cells, the text area's
/// background and the bar over it. `suffix`, its [`system_suffix`], goes
/// after every label.
fn window_pieces(
    out: &mut Inc,
    r: &Emit,
    window: &SystemWindow,
    t: &Geometry,
    suffix: &str,
    one_line: bool,
) -> Result<()> {
    let reserved = cgram_reserved(r.window_colors);
    out.block(format!("window_tiles{suffix}"), &window.tiles);
    // Only the `reserved` at the bottom: from there up it is the
    // background's.
    let words: Vec<u32> = window
        .cgram
        .iter()
        .take(reserved as usize)
        .map(|&w| w.into())
        .collect();
    out.block(format!("window_cgram{suffix}"), &words_le(words));
    // One layout of the cells per window base the VRAM layouts use, with
    // the upper layer's priority so it covers the hero and the events.
    //
    // Each one is two planes, one after the other, and the console stamps
    // both in the window's tilemap: the window as it is, and below it the
    // same window without its frame —`MessageOptions` without the
    // background—, where only the text cells remain and every other one is
    // cell 0, the BG2 tile that is blank in every map. Which one shows is
    // the scroll: see `msg_hdma_build` in the runtime.
    let text_base = window.base;
    for (base, label) in WINDOW_BASES
        .iter()
        .zip(["window_cells", "window_cells_256"])
    {
        let label = format!("{label}{suffix}");
        let mut framed = Vec::new();
        let mut bare = Vec::new();
        for row in &window.cells {
            for &c in row {
                let cell =
                    entry(base + c as u32, false, false, PRIORITY_ABOVE) | (WINDOW_PALETTE << 10);
                framed.push(cell);
                bare.push(if c >= text_base { cell } else { 0 });
            }
        }
        framed.extend(bare);
        out.block(&label, &words_le(framed));
    }
    // The cells of the arrow of a message waiting for a key, per window base
    // in the order of `window_cells`: with the frame, off and on, and
    // without it, off and on. Off is what the window has there —its frame,
    // or cell 0 without it—. The console writes one of the four on the
    // plane the window shows: see `msg_arrow` in the runtime.
    let arrow = &window.arrow;
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
    let under: &[usize] = window.cells.get(arrow_row).map_or(&[], Vec::as_slice);
    if under.len() < arrow_col + arrow_cells {
        return Err(Bad::answer(format!(
            "the window's arrow goes at row {arrow_row}, columns {arrow_col} to {}, and the \
             window has no cell there",
            arrow_col + arrow_cells - 1
        )));
    }
    let mut arrow_table = Vec::new();
    for base in WINDOW_BASES {
        let cell = |tile: usize| {
            entry(base + tile as u32, false, false, PRIORITY_ABOVE) | (WINDOW_PALETTE << 10)
        };
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
    out.block(
        format!("window_arrow_cells{suffix}"),
        &words_le(arrow_table),
    );
    // And the arrow over nothing as two objects' tiles, for a window
    // without its background in a map that has room for them: the same
    // tiles the window's cells name, in the window's palette, which the
    // console copies to a sprite palette. See `arrow_obj` in record.rs.
    //
    // A tile the window does not carry goes blank: the screens stage always
    // carries the arrow's, among `tiles` before `base`, and only a made-up
    // window —the tests' carry three tiles— names one past them.
    let tiles = &window.tiles;
    let mut arrow_obj = Vec::with_capacity(arrow_cells * 32);
    for &tile in &arrow[arrow_cells..] {
        let at = tile * 32;
        let mut bytes = tiles
            .get(at..)
            .unwrap_or_default()
            .iter()
            .take(32)
            .copied()
            .collect::<Vec<u8>>();
        bytes.resize(32, 0);
        arrow_obj.extend(bytes);
    }
    out.block(format!("window_arrow_obj{suffix}"), &arrow_obj);
    // And the gold window, which `ShowInn` opens next to its greeting, as
    // objects in the arrow's sprite palette: its 44 tiles, the fifteen words
    // of that palette from entry 1 —the window's own and the colours it
    // adds—, and the twelve entries a greyed option's glyph rows take. See
    // `gold` in rm2k-snes-screens' `message_window.rs`, and the runtime's
    // gold_window.s.
    let gold = &window.gold;
    {
        let mut gold_block = gold.tiles.clone();
        if gold_block.len() != GOLD_TILES * 32 {
            return Err(Bad::answer(format!(
                "the gold window has {} bytes of tiles, not {}",
                gold_block.len(),
                GOLD_TILES * 32
            )));
        }
        gold_block.extend(words_le(
            gold.cgram.iter().skip(1).take(15).map(|&w| u32::from(w)),
        ));
        let disabled = &window.disabled;
        if disabled.len() != 12 {
            return Err(Bad::answer(format!(
                "the window's disabled ink has {} rows, not twelve",
                disabled.len()
            )));
        }
        gold_block.extend(disabled);
        // And the text's twenty colours, which go with the grey: for each,
        // the word the box's ink entry takes and the entries of the glyph's
        // twelve rows with the ink and without it. See `inks` in
        // rm2k-snes-screens and the runtime's message_pace.s. Only in a
        // cartridge whose boxes type a colour, the one whose window keeps the
        // ink: the others never read them —`colour` in the runtime is 0
        // without an ink—, and half a kilobyte of nothing would only move
        // the rest of the packing.
        if window.ink > 0 {
            gold_block.extend(text_inks(window)?);
        }
        if suffix.is_empty() {
            out.push_str(&format!(
                "; The gold window: its size, where its number ends and its text's top,\n\
                 ; in pixels. See the runtime's gold_window.s.\n\
                 GOLD_WIDTH = {}\nGOLD_HEIGHT = {}\nGOLD_RIGHT = {}\nGOLD_TEXT_Y = {}\n\
                 ; The window's entry a box's ink takes, 0 if its boxes type no\n\
                 ; colour but 0. See the runtime's message_pace.s.\n\
                 TEXT_INK_ENTRY = {}\n",
                gold.width, gold.height, gold.right, gold.text_y, window.ink,
            ));
        }
        out.block(format!("window_gold{suffix}"), &gold_block);
    }
    // The text area's background, one line —two cell rows— after another,
    // which `prime_line` copies under each line before its letters. When
    // every line is the same —a window over one colour, `[windows.
    // background]`— only the first goes, and `prime_line` copies it under
    // all of them: a quarter of the bytes.
    let backdrop = Backdrop::of(window, t);
    let backdrop_lines = if one_line { 1 } else { backdrop.lines };
    if suffix.is_empty() {
        out.push_str(&format!("WINDOW_BACKDROP_LINES = {backdrop_lines}\n"));
    }
    out.block(
        format!("window_backdrop{suffix}"),
        if one_line {
            &backdrop.bytes[..backdrop.line]
        } else {
            &backdrop.bytes
        },
    );
    // And the same background with the System's cursor on each line, and
    // one line's with the cursor over nothing: a choice's highlighted
    // option is composed over these. See `prime_line` in the runtime.
    out.block(format!("window_bar{suffix}"), &window.bar);
    out.block(format!("window_bar_bare{suffix}"), &window.bar_bare);
    Ok(())
}

/// How many text colours a System has, and the bytes each takes in
/// `window_gold` after the grey: the ink's word and two sets of twelve
/// entries. `INK_COLOURS` and `INK_BYTES` in the runtime's message_pace.s.
pub const INK_COLOURS: usize = 20;
pub const INK_BYTES: usize = 2 + 12 + 12;

/// The window's `inks` as the cartridge carries them: see [`INK_BYTES`].
fn text_inks(window: &SystemWindow) -> Result<Vec<u8>> {
    let mut out = Vec::with_capacity(INK_COLOURS * INK_BYTES);
    let inks = &window.inks;
    if inks.len() != INK_COLOURS {
        return Err(Bad::answer(format!(
            "the window has {} text colours, not {INK_COLOURS}",
            inks.len()
        )));
    }
    for ink in inks {
        out.extend(words_le([u32::from(ink.word)]));
        for rows in [&ink.inked, &ink.plain] {
            if rows.len() != 12 {
                return Err(Bad::answer(format!(
                    "a text colour has {} rows, not twelve",
                    rows.len()
                )));
            }
            out.extend(rows);
        }
    }
    Ok(out)
}

/// A window's text area background, as `prime_line` reads it: one line
/// —two cell rows— after another.
struct Backdrop {
    bytes: Vec<u8>,
    /// The bytes of a line.
    line: usize,
    /// How many lines the text area has.
    lines: usize,
}

impl Backdrop {
    fn of(window: &SystemWindow, t: &Geometry) -> Backdrop {
        Backdrop {
            bytes: window.background.clone(),
            line: (t.n("WINDOW_TEXT_COLS") * 2 * 32) as usize,
            lines: (t.n("WINDOW_TEXT_ROWS") / 2) as usize,
        }
    }

    /// Whether every line is the same: a window over one colour,
    /// `[windows.background]`.
    fn is_one_line(&self) -> bool {
        let first = &self.bytes[..self.line.min(self.bytes.len())];
        self.bytes.len() == self.line * self.lines
            && self.bytes.chunks(self.line).all(|l| l == first)
    }
}

/// How many bytes a System's entry takes in `window_systems`: the ten
/// 24-bit pointers `window_select` copies to `WINDOW_NOW`, in the order of
/// `WS_TILES` and the rest in the runtime's `window_system.s`.
pub const WINDOW_SYSTEM_BYTES: usize = 30;

/// The gold window's tiles: 88x32 in 8x8 objects. `GOLD_OBJ_TILES` in
/// record.rs, which keeps room for them past a map's sprite bank.
const GOLD_TILES: usize = crate::record::GOLD_OBJ_TILES;

/// The table the runtime finds each System's window in: per System, in the
/// cartridge's order, a pointer to each of its pieces.
fn window_systems_table(out: &mut Inc, systems: usize) {
    let bytes = WINDOW_SYSTEM_BYTES;
    out.push_str(&format!(
        "; The message window of each System, for `window_select`.\n\
         WINDOW_SYSTEM_BYTES = {bytes}\n\
         .block {}\nwindow_systems:\n",
        systems * bytes
    ));
    for k in 0..systems {
        let suffix = system_suffix(k);
        for piece in [
            "window_tiles",
            "window_cgram",
            "window_cells",
            "window_cells_256",
            "window_arrow_cells",
            "window_backdrop",
            "window_bar",
            "window_bar_bare",
            "window_arrow_obj",
            "window_gold",
        ] {
            out.far(&format!("{piece}{suffix}"));
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
fn normalized_windows(window: &SystemWindow, others: &[OtherSystem]) -> Result<Vec<SystemWindow>> {
    if others.is_empty() {
        return Ok(vec![window.clone()]);
    }
    let mut all = vec![window.clone()];
    let mut base = window.base;
    for o in others {
        let w = &o.window;
        base = base.max(w.base);
        if (&w.color, w.shadow) != (&window.color, window.shadow) {
            return Err(Bad::answer(format!(
                "System {:?} gives the text other palette entries than the starting one: the \
                 font's tables are one for all of them",
                o.system
            )));
        }
        all.push(w.clone());
    }
    for w in &mut all {
        let own = w.base;
        w.tiles.resize(base * 32, 0);
        for c in w.cells.iter_mut().flatten() {
            if *c >= own {
                *c = *c - own + base;
            }
        }
        w.base = base;
    }
    Ok(all)
}

/// How many bytes a picture's entry takes in `picture_data`: see
/// [`picture_tables`].
pub const PICTURE_ENTRY: usize = 16;

/// The bit of an entry's palette byte that sends the picture behind what
/// its map draws above the hero: `PIC_BEHIND` in the runtime's
/// picture_far.s, which builds the object's attributes with it.
pub const PICTURE_BEHIND: u8 = 0x10;

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
///     byte  its sprite palette, counted from the top: 0 is palette 7;
///           and PICTURE_BEHIND if it goes at the characters' priority,
///           behind what the map draws above the hero —`behind_map`—
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
        data.extend(
            u16::try_from(p.base)
                .map_err(|_| whose(format!("pictures at tile {}", p.base)))?
                .to_le_bytes(),
        );
        data.push(n as u8);
        let entries = data.len();
        data.resize(entries + n * PICTURE_ENTRY, 0);
        // The first tile again at the end of each entry, so drawing needs
        // the entry alone.
        let base = i16::try_from(p.base)
            .map_err(|_| whose(format!("a picture's {}", p.base)))?
            .to_le_bytes();
        // Each palette's colours once, by its index.
        let mut colors_of = BTreeMap::new();
        for (i, image) in p.images.iter().enumerate() {
            let palette = u8::try_from(image.palette_index)
                .ok()
                .filter(|&p| p < 8)
                .ok_or_else(|| {
                    whose(format!(
                        "sprite palette {} from the top",
                        image.palette_index
                    ))
                })?;
            let entry = picture_entry(
                &mut data,
                image,
                &mut colors_of,
                palette | if image.behind_map { PICTURE_BEHIND } else { 0 },
                [base[0], base[1], 0, 0],
                &whose,
            )?;
            let at = entries + i * PICTURE_ENTRY;
            data[at..at + PICTURE_ENTRY].copy_from_slice(&entry);
        }
        starts.push(
            u16::try_from(start).map_err(|_| whose("the pictures' table passes 64 KB".into()))?,
        );
    }
    Ok((words_le(starts.iter().map(|&s| u32::from(s))), data))
}

/// One picture's objects and its palette's colours, added to `data`, and
/// its entry —see [`picture_tables`]—, whose offsets are indices of `data`.
/// `colors_of` says where each palette's colours already are, so the
/// pictures that share a palette point to it once. The palette byte and
/// the entry's last four bytes are each caller's: a map's picture and a
/// common one say different things there.
fn picture_entry(
    data: &mut Vec<u8>,
    image: &crate::request::PictureImage,
    colors_of: &mut BTreeMap<i64, usize>,
    palette: u8,
    tail: [u8; 4],
    whose: &dyn Fn(String) -> Bad,
) -> Result<[u8; PICTURE_ENTRY]> {
    let objects_at = data.len();
    for &[dx, dy, tile] in &image.objects {
        let byte = |v: i64| u8::try_from(v).map_err(|_| whose(format!("an object at {v}")));
        data.push(byte(dx)?);
        data.push(byte(dy)?);
        data.extend(
            u16::try_from(tile)
                .map_err(|_| whose(format!("an object's tile {tile}")))?
                .to_le_bytes(),
        );
    }
    let colors_at = match colors_of.get(&image.palette_index) {
        Some(&at) => at,
        None => {
            let at = data.len();
            data.extend(palette16(&image.palette));
            colors_of.insert(image.palette_index, at);
            at
        }
    };
    let half = |v: i64| -> Result<[u8; 2]> {
        Ok(i16::try_from(v)
            .map_err(|_| whose(format!("a picture's {v}")))?
            .to_le_bytes())
    };
    // The two offsets are unsigned, as the console reads them —an index of
    // `picture_data`—: the table reaches 64 KB, and Desert Nightmare's went
    // past 32 KB on 2026-11-21, when the pictures of RM2k's whole screen
    // that draw little became small ones.
    let offset = |v: usize| -> Result<[u8; 2]> {
        Ok(u16::try_from(v)
            .map_err(|_| whose("the pictures' table passes 64 KB".into()))?
            .to_le_bytes())
    };
    let mut entry = [0u8; PICTURE_ENTRY];
    entry[0..2].copy_from_slice(&half(image.half[0])?);
    entry[2..4].copy_from_slice(&half(image.half[1])?);
    entry[4] = u8::try_from(image.objects.len()).map_err(|_| whose("too many objects".into()))?;
    entry[5] = palette;
    entry[6..8].copy_from_slice(&offset(objects_at)?);
    entry[8..10].copy_from_slice(&offset(colors_at)?);
    entry[10..14].copy_from_slice(&tail);
    Ok(entry)
}

/// The common events' small pictures' entries, after the maps' in
/// `picture_data`: as a map's —see [`picture_tables`]—, with the base tile
/// at 0 and the palette counted from the set's first, since both are each
/// map's —see [`picture_common_section`]—, the set's index at byte 12 and $80, a
/// common one, at byte 13.
/// Answers where the first is, which the console finds as `PICTURE_COMMON`;
/// 0 without any.
pub fn common_entries(sets: &[crate::request::CommonSet], data: &mut Vec<u8>) -> Result<usize> {
    let count: usize = sets.iter().map(|s| s.images.len()).sum();
    if count == 0 {
        return Ok(0);
    }
    if count > 0x7F {
        return Err(Bad::answer(format!(
            "{count} common pictures, and an image's seven bits name 127"
        )));
    }
    let entries = data.len();
    data.resize(entries + count * PICTURE_ENTRY, 0);
    let mut at = entries;
    for (k, set) in sets.iter().enumerate() {
        let whose = |what: String| Bad::answer(format!("{}: {what}", set.name));
        let mut colors_of = BTreeMap::new();
        for image in &set.images {
            let palette = u8::try_from(image.palette_index)
                .ok()
                .filter(|&p| (p as usize) < set.palettes.max(1))
                .ok_or_else(|| whose(format!("palette {}", image.palette_index)))?;
            let entry = picture_entry(
                data,
                image,
                &mut colors_of,
                palette,
                [0, 0, k as u8, 0x80],
                &whose,
            )?;
            data[at..at + PICTURE_ENTRY].copy_from_slice(&entry);
            at += PICTURE_ENTRY;
        }
    }
    if data.len() > 0x10000 {
        return Err(Bad::answer(
            "the pictures' table with the common ones passes 64 KB",
        ));
    }
    Ok(entries)
}

/// How many sets of common pictures a map's mask names: see
/// [`picture_common_section`].
pub const COMMON_SETS: usize = 8;
/// The bytes of an entry of `picture_sets` and of `picture_common_maps`.
const COMMON_SET_ENTRY: usize = 8;
const COMMON_MAP_ENTRY: usize = 8;
/// A 4-bit tile.
const COMMON_TILE: usize = 32;

/// The common events' small pictures, as the console uploads them: see
/// `runtime/picture_common.s`.
///
/// ```text
///   picture_sets, an entry per set:
///     long  its tiles, raw, from its first
///     word  their bytes
///     byte  how many sprite palettes it takes
///     two bytes of nothing
///   picture_common_maps, an entry per map, in the order of `map_table`:
///     word  the tile of the bank the sets go at
///     word  its VRAM word
///     byte  the first sprite palette they take, counted from the top
///     byte  which sets fit there, a bit each from bit 0
///     two bytes of nothing
/// ```
///
/// A set fits on a map if its tiles fit past what the map's bank, the
/// message arrow and the gold window take, and its palettes under what its
/// pictures and the arrow take and over its characters': see
/// [`crate::record::common_room`]. Only one set is in VRAM at a time, so
/// each is judged alone. The log says on how many maps each one fits.
fn picture_common_section(out: &mut Inc, r: &Emit, notes: &mut Vec<String>) -> Result<()> {
    let sets = &r.common_pictures;
    out.push_str(&format!("PICTURE_SETS = {}\n", sets.len()));
    if sets.is_empty() {
        out.block("picture_sets", &[0]);
        out.block("picture_common_maps", &[0]);
        return Ok(());
    }
    if sets.len() > COMMON_SETS {
        return Err(Bad::answer(format!(
            "{} sets of common pictures, and a map's mask names {COMMON_SETS}",
            sets.len()
        )));
    }
    out.push_str(&format!(
        ".block {}\npicture_sets:\n",
        COMMON_SET_ENTRY * sets.len()
    ));
    for (k, set) in sets.iter().enumerate() {
        out.far(&format!("picture_set_tiles_{k}"));
        out.push_str(&format!(
            "    .word {}\n    .byte {}\n    .res 2\n",
            set.tiles * COMMON_TILE,
            set.palettes
        ));
    }
    out.push('\n');
    let mut maps = Vec::with_capacity(COMMON_MAP_ENTRY * r.maps.len());
    let mut fits = vec![0usize; sets.len()];
    for map in &r.maps {
        let room = crate::record::common_room(map)?;
        let layout = crate::record::layout_of(map)?;
        let mut mask = 0u8;
        for (k, set) in sets.iter().enumerate() {
            if set.tiles <= room.tiles && set.palettes <= room.palettes {
                mask |= 1 << k;
                fits[k] += 1;
            }
        }
        let vram = layout.sprites.base as usize + room.base * 16;
        maps.extend((room.base as u16).to_le_bytes());
        maps.extend(
            u16::try_from(vram)
                .map_err(|_| Bad::answer(format!("map {}: VRAM word {vram}", map.id)))?
                .to_le_bytes(),
        );
        maps.push(room.palette as u8);
        maps.push(mask);
        maps.extend([0, 0]);
    }
    out.block("picture_common_maps", &maps);
    for (k, set) in sets.iter().enumerate() {
        // One that fits no map is never uploaded: its tiles stay out.
        if fits[k] == 0 {
            out.block(format!("picture_set_tiles_{k}"), &[0]);
            notes.push(format!(
                "  {}: WARNING, their small pictures fit on none of the {} maps, and aren't shown",
                set.name,
                r.maps.len()
            ));
            continue;
        }
        let mut tiles = vec![0u8; set.tiles * COMMON_TILE];
        for (number, cell) in &set.cells {
            if cell.len() != 64 || *number >= set.tiles {
                return Err(Bad::answer(format!(
                    "{}: tile {number} of {} with {} pixels",
                    set.name,
                    set.tiles,
                    cell.len()
                )));
            }
            tiles[number * COMMON_TILE..(number + 1) * COMMON_TILE].copy_from_slice(&pack4(cell));
        }
        out.block(format!("picture_set_tiles_{k}"), &tiles);
        notes.push(format!(
            "  {}: their small pictures fit on {} of the {} maps",
            set.name,
            fits[k],
            r.maps.len()
        ));
    }
    Ok(())
}

/// An 8x8 cell of colour indices as the console's 4-bit tile: two planes
/// at a time, a row each two bytes.
fn pack4(cell: &[u8]) -> [u8; COMMON_TILE] {
    let mut out = [0u8; COMMON_TILE];
    for (i, &v) in cell.iter().enumerate() {
        let (y, x) = (i / 8, i % 8);
        let bit = 0x80 >> x;
        for plane in 0..4 {
            if (v >> plane) & 1 == 1 {
                out[(plane / 2) * 16 + y * 2 + plane % 2] |= bit;
            }
        }
    }
    out
}

fn picture_section(out: &mut Inc, r: &Emit, notes: &mut Vec<String>) -> Result<()> {
    out.push_str(
        "\n; --- the ShowPicture pictures: see `picture_tables` in rm2k-snes-mapdata ---\n",
    );
    out.push_str(&format!("PICTURE_ENTRY = {PICTURE_ENTRY}\n"));
    let (maps, mut data) = picture_tables(&r.maps)?;
    let common = common_entries(&r.common_pictures, &mut data)?;
    out.push_str(&format!("PICTURE_COMMON = {common}\n"));
    out.block("picture_maps", &maps);
    out.block("picture_data", &data);
    picture_common_section(out, r, notes)?;
    // The screen flash's products, `d * level // 31`, so the console does not
    // multiply and divide for each of its 96 entries every odd frame.
    let products: Vec<u8> = (0..32u32)
        .flat_map(|n| (0..32u32).map(move |d| (d * n / 31) as u8))
        .collect();
    out.block("prod31_table", &products);
    Ok(())
}

/// The big pictures' tilemap is 32x32 cells to a screen, two screens: side
/// by side when the picture is as tall as the screen —the second one holds
/// the mirrored edges a wave scrolls into view—, one under the other when
/// it is taller. `BG1SC`'s size bits for each.
const BIG_SCREEN: usize = 32;
const BIG_WIDE: u8 = 1;
const BIG_TALL: u8 = 2;
/// And in the same byte, bit 7: the layer keeps the map's small pictures
/// over it, its tiles past the sprite bank. `BIG_KEEPS` in
/// `runtime/big_picture.s`.
const BIG_KEEPS: u8 = 0x80;
/// The most tiles such a layer takes: from word $2000 to its tilemap.
const BIG_KEEP_TILES: usize = 512;
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
        return Err(Bad::answer(format!(
            "a big picture of {rows} rows: the tilemap holds 64"
        )));
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
///   byte  BG1SC's size bits, and BIG_KEEPS
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
fn big_pictures_section(out: &mut Inc, r: &Emit) -> Result<()> {
    out.push_str("\n; --- the big pictures: see `big_pictures_section` in rm2k-snes-mapdata ---\n");
    out.push_str(&format!(
        "BIG_PICTURES = {}\nBIG_ENTRY = {BIG_ENTRY}\n",
        r.big_pictures.len()
    ));
    if r.big_pictures.is_empty() {
        out.block("big_table", &[0]);
        return Ok(());
    }
    let mut raw: Vec<Vec<u8>> = Vec::new();
    let mut sizes = Vec::new();
    for big in &r.big_pictures {
        let (map, size) = big_tilemap(big.rows, &big.tilemap, big.wider)?;
        raw.push(map.iter().flat_map(|w| w.to_le_bytes()).collect());
        if big.keeps_objects && (big.tiles.len() / 32 > BIG_KEEP_TILES || big.mode7.is_some()) {
            return Err(Bad::answer(format!(
                "a big picture of {} tiles{} keeps the sprites: it takes at most {BIG_KEEP_TILES},                  and no texture",
                big.tiles.len() / 32,
                if big.mode7.is_some() { " with a texture" } else { "" }
            )));
        }
        sizes.push(size | if big.keeps_objects { BIG_KEEPS } else { 0 });
    }
    let refs: Vec<&[u8]> = raw.iter().map(Vec::as_slice).collect();
    let streams = crate::compress::compress_many(&refs)?;
    let shared = big_shared(&r.big_pictures);
    out.push_str(&format!(
        ".block {}\nbig_table:\n",
        BIG_ENTRY * r.big_pictures.len()
    ));
    for (k, big) in r.big_pictures.iter().enumerate() {
        let vofs = (-big.top - 1) as i16 as u16;
        let corner = ((big.center[1] - big.half[1]) * BIG_CONSOLE_HEIGHT).div_euclid(BIG_RM_HEIGHT);
        let j = shared[k];
        for piece in ["big_tiles", "big_map", "big_colors"] {
            out.far(&format!("{piece}_{j}"));
        }
        out.push_str(&format!(
            "    .word {}\n    .byte {}\n    .word {vofs}\n\
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
                out.far(&format!("big_m7_tiles_{k}"));
                out.far(&format!("big_m7_rows_{k}"));
                out.push_str(&format!(
                    "    .word {}\n    .word {rows}\n    .word {}\n    .word {}\n",
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
                let c = big
                    .palettes
                    .get(p)
                    .and_then(|p| p.get(i))
                    .copied()
                    .unwrap_or([0, 0, 0]);
                colors.extend(cgram_word(c).to_le_bytes());
            }
        }
        // The tiles go whole through `big_dma_vram`, and the tilemap is an
        // LZ2 stream: both may travel in the `.msu`, and a picture is shown
        // with the screen off. See `msu_block`.
        let msu = r.rom.msu != MsuData::Optional;
        if shared[k] == k {
            out.msu_block(format!("big_tiles_{k}"), &big.tiles, msu);
            out.msu_block(format!("big_map_{k}"), &streams[k], msu);
            out.block(format!("big_colors_{k}"), &colors);
        }
        if let Some(t) = &big.mode7 {
            let (tiles, rows) = big_mode7(big.rows, t)?;
            out.block(format!("big_m7_tiles_{k}"), &tiles);
            out.block(format!("big_m7_rows_{k}"), &rows);
        }
    }
    Ok(())
}

/// For each big picture, the one whose tiles, tilemap and colours its entry
/// points at: the first with the same three, itself if none before has
/// them. The same picture zoomed on one map and still on others is two
/// layers, one with a mode 7 texture and one without —see `number_big` in
/// rm2k-snes-convert—, and the cartridge carries what they share once.
pub fn big_shared(bigs: &[crate::request::BigLayer]) -> Vec<usize> {
    let same = |a: &crate::request::BigLayer, b: &crate::request::BigLayer| {
        a.tiles == b.tiles
            && a.tilemap == b.tilemap
            && a.rows == b.rows
            && a.wider == b.wider
            && a.palettes == b.palettes
    };
    (0..bigs.len())
        .map(|k| (0..k).find(|&j| same(&bigs[j], &bigs[k])).unwrap_or(k))
        .collect()
}

/// A row of mode 7's map: 128 tiles, of which a layer takes the first 32.
const BIG_M7_ROW: usize = 128;
/// The most tiles mode 7's map names, each a byte a pixel.
const BIG_M7_TILES: usize = 256;
const BIG_M7_TILE: usize = 64;

/// A big picture's mode 7 texture as the cartridge carries it: its tiles,
/// and its map's rows as VRAM's low bytes take them, padded to 128.
pub fn big_mode7(rows: usize, t: &crate::request::Mode7Texture) -> Result<(Vec<u8>, Vec<u8>)> {
    if !t.tiles.len().is_multiple_of(BIG_M7_TILE) || t.tiles.len() > BIG_M7_TILES * BIG_M7_TILE {
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

fn animations_section(out: &mut Inc, r: &Emit) -> Result<()> {
    let a = &r.animations;
    let mut list: Vec<&crate::request::BattleAnimation> = a.list.iter().collect();
    list.sort_by_key(|x| x.number);
    let cap = list.last().map_or(1, |x| x.number + 1);
    let mut lines: Vec<String> = vec![
        "\n; --- the drawing of the battle animations ---".into(),
        ";".into(),
        "; The box is a single one for the whole ROM and the reason is in".into(),
        "; rm2k-snes-convert's animations.rs: four 32x32 objects in one row of blocks".into(),
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

fn title_section(out: &mut Inc, menu: Option<&rm2k_snes_screens::answer::Title>) -> Result<()> {
    out.push_str("\n; --- the title screen ---\n");
    match menu {
        None => {
            out.block("title_menu_tiles", &[0]);
            out.block("title_menu_cells", &[0]);
        }
        Some(menu) => {
            // A 4-bit tile bank and one tilemap per selected option, one after
            // the other, first the ones without a save and then the ones with:
            // the console indexes them by multiplying.
            out.block("title_menu_tiles", &packed(&menu.tiles, 4));
            let mut plane = Vec::new();
            for tilemap in &menu.tilemaps {
                plane.extend(cell_words(tilemap, PRIORITY_ABOVE));
            }
            out.block("title_menu_cells", &plane);
        }
    }
    Ok(())
}

fn full_screens_section(out: &mut Inc, r: &Emit) -> Result<()> {
    out.push_str("\n; --- the full screens ---\n");
    out.push_str(&format!(
        "GAME_OVER_TILES = {}\n",
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
        out.block("screens_table", &[0]);
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
        out.far(label);
        out.push_str(&format!(
            "    .word {}, {}\n    .byte {}\n",
            data.tiles * data.bpp * 8,
            data.colors * 2,
            data.first_color
        ));
    }
    out.push('\n');
    for (_, label, data) in &rows {
        out.block(label, &data.stream);
    }
    Ok(())
}

/// What goes after the full screens: the slots screen, the menus and the
/// text screens, the equipment, the battle, the troops and the scene, and
/// the tables of bank 0.
struct Rest<'a> {
    r: &'a Emit,
    db: &'a Db,
    slots: &'a rm2k_snes_screens::answer::Slots,
    screens: &'a Answer,
    t: &'a Geometry<'a>,
    bs: &'a Geometry<'a>,
    model: &'a rm2k_snes_battle::model::Model,
    faces: &'a BTreeMap<i64, &'a Vec<u16>>,
}

impl Rest<'_> {
    fn write(&self, out: &mut Inc, _notes: &mut Vec<String>) -> Result<()> {
        let (r, db, slots, t) = (self.r, self.db, self.slots, self.t);
        let screens = self.screens;
        let cell = CELL;
        let cols = COLS;
        // --- the slots screen, in every cartridge: the save point opens it
        // from inside the game.
        out.push_str("\n; --- the slots screen ---\n");
        out.block("slot_tiles", &packed(&slots.tiles, 4));
        // Each cell block with its own label, named by a pointer table. The
        // bank of the slots and the menu goes with the priority bit set: the
        // actor choice turns on BG1, which at priority 0 would cover BG2.
        let mut slot_blocks: Vec<String> = Vec::new();
        for (mode, cells) in slots.headers.iter().enumerate() {
            let name = format!("slot_hdr_{mode}");
            out.block(&name, &cell_words(cells, 1));
            slot_blocks.push(name);
        }
        // Two per slot, empty and full: the cursor is the System's, on BG1
        // —`slot_bar_cells`, below—.
        for (number, row) in slots.rows.iter().enumerate() {
            for (full, cells) in row.iter().enumerate() {
                let name = format!("slot_{number}_{full}");
                out.block(&name, &cell_words(cells, 1));
                slot_blocks.push(name);
            }
        }
        // Per actor that can join the party, its face.
        let mut face_block: BTreeMap<i64, usize> = BTreeMap::new();
        for (actor, cells) in self.faces {
            let name = format!("slot_face_{actor}");
            out.block(&name, &cell_words(cells, 1));
            face_block.insert(*actor, slot_blocks.len());
            slot_blocks.push(name);
        }
        // The pause menu's: each command in its two variants, the coin, and
        // a party row's text.
        let menu = &slots.menu;
        let menu_option_block = slot_blocks.len();
        for (order, variants) in menu.options.iter().enumerate() {
            for (disabled, cells) in variants.iter().enumerate() {
                let name = format!("menu_option_{order}_{disabled}");
                out.block(&name, &cell_words(cells, 1));
                slot_blocks.push(name);
            }
        }
        let menu_currency_block = slot_blocks.len();
        out.block("menu_currency", &cell_words(&menu.currency, 1));
        slot_blocks.push("menu_currency".into());
        let menu_row_block = slot_blocks.len();
        out.block("menu_row", &cell_words(&menu.row, 1));
        slot_blocks.push("menu_row".into());

        // The text screens' inks: a palette per colour, all with the same
        // layout —the font's colours for it are `SCR_INK_*`, with the
        // window's—. Until 2026-10-03 this was a font bank, each letter in
        // two cells.
        let inks = &screens.text_inks;
        // How far each of the screens' glyphs moves the line and paints:
        // the console's, `TL_FIGURE`'s place and the icons' halves.
        out.block("font_advance", &inks.advances);
        out.block("font_reach", &inks.reach);
        let item_palettes = &inks.palettes;
        let up = t.n("ITEM_UP") as usize;
        out.block(
            "items_cgram",
            &palettes_cgram(&item_palettes[..up.min(item_palettes.len())]),
        );
        out.block(
            "item_cgram_uploads",
            &palettes_cgram(&item_palettes[up.min(item_palettes.len())..]),
        );
        // The windows of the item and equipment screens, on BG1.
        let border = &screens.items_border;
        let border_tiles = &border.tiles;
        let border_colors = &border.colors;
        let [(border_map, border_bars), (eq_map, eq_bars)] = &border.maps[..] else {
            return Err(Bad::answer(format!(
                "the item and equipment windows are {} screens, not two",
                border.maps.len()
            )));
        };
        let bars = |bars: &[Vec<u16>]| -> Vec<u8> { bars.iter().flat_map(|b| words(b)).collect() };
        out.block("items_border_tiles", &packed(border_tiles, 8));
        out.block("items_border_map", &words(border_map));
        out.block("items_border_bars", &bars(border_bars));
        out.block("eq_border_map", &words(eq_map));
        out.block("eq_border_bars", &bars(eq_bars));
        out.block("items_border_cgram", &cgram_bytes(border_colors));
        // The battle's windows, on BG1 at 8bpp in the cells the scene does
        // not take: see `battle.rs` in `rm2k-snes-screens`. Per layout its
        // band's rows, and per layout and set the bars, sixteen records of
        // six bytes —row, column, rows, columns, the first word in
        // `ba_win_patches`— with ten for set A, five for set B and one of
        // padding; a record of no rows is no bar.
        let bw = &screens.battle_windows;
        out.block("ba_win_tiles", &packed(&bw.tiles, 8));
        out.block("ba_win_cgram", &cgram_bytes(&bw.colors));
        let band: Vec<u8> = bw.band.iter().flat_map(|layout| words(layout)).collect();
        out.block("ba_win_band", &band);
        out.block("ba_win_help", &words(&bw.help));
        out.block("ba_win_patches", &words(&bw.patches));
        let mut records = Vec::new();
        for sets in &bw.bars {
            for (set, room) in [(0, 10), (1, 6)] {
                let no_bars = Vec::new();
                let bars = sets.get(set).unwrap_or(&no_bars);
                if bars.len() > room {
                    return Err(Bad::answer(format!(
                        "a battle layout has {} bars in a set of {room}",
                        bars.len()
                    )));
                }
                for k in 0..room {
                    match bars.get(k) {
                        Some(b) => {
                            records.extend([b[0] as u8, b[1] as u8, b[2] as u8, b[3] as u8]);
                            records.extend((b[4] as u16 * 2).to_le_bytes());
                        }
                        None => records.extend([0u8; 6]),
                    }
                }
            }
        }
        out.block("ba_win_bars", &records);
        out.push_str(&format!(
            "BA_WIN_TILES      = {}\nBA_WIN_FIRST      = {}\nBA_WIN_CGRAM      = {}\nBA_WIN_COLORS     = {}\n\
             BA_WIN_BAND_ROW   = {}\nBA_WIN_BAND_ROWS  = {}\nBA_WIN_HELP_ROWS  = {}\n",
            bw.tiles.len(),
            bw.first,
            bw.cgram,
            bw.colors.len(),
            bw.band_row,
            bw.band.first().map_or(0, Vec::len) / 32,
            bw.help.len() / 32
        ));
        // The shop windows, on BG1 with their own base.
        let shop = &screens.shop_border;
        let ti_tiles = &shop.tiles;
        let ti_colors = &shop.colors;
        out.block("ti_border_tiles", &packed(ti_tiles, 8));
        out.block("ti_border_cgram", &cgram_bytes(ti_colors));
        let rows_words: Vec<u8> = shop.compact.rows.iter().flat_map(|f| words(f)).collect();
        out.block("ti_border_rows", &rows_words);
        out.block("ti_border_patches", &words(&shop.compact.patches));
        let ti_map = t.n("TI_MAP");
        let mut stretches: Vec<i64> = Vec::new();
        let mut layer_stretches: Vec<i64> = Vec::new();
        for layer in &shop.compact.layers {
            layer_stretches.push(2 * stretches.len() as i64);
            for &(row, origin, how_many) in layer {
                let (row, origin, how_many) = (row as i64, origin as i64, how_many as i64);
                stretches.extend([ti_map + row * cols, origin * 2 * cols, how_many * 2 * cols]);
            }
            stretches.extend([0, 0, 0]);
        }
        out.block(
            "ti_stretches",
            &words_le(stretches.iter().map(|&w| w as u32)),
        );
        out.block(
            "ti_layer_stretches",
            &words_le(layer_stretches.iter().map(|&w| w as u32)),
        );
        let mut ti_bars = Vec::new();
        let mut base_bars = vec![0i64];
        for layer in &shop.compact.bars {
            for &(row, col, rows, width, origin) in layer {
                let (row, col, rows, width, origin) = (
                    row as i64,
                    col as i64,
                    rows as i64,
                    width as i64,
                    origin as i64,
                );
                ti_bars.extend([ti_map + row * cols + col, 2 * origin, 2 * width, rows]);
            }
            base_bars.push(base_bars[base_bars.len() - 1] + layer.len() as i64);
        }
        out.block("ti_bars", &words_le(ti_bars.iter().map(|&w| w as u32)));
        let base_bytes: Vec<u8> = base_bars[..base_bars.len() - 1]
            .iter()
            .map(|&b| b as u8)
            .collect();
        out.block("ti_bar_base", &base_bytes);
        let modes: Vec<u8> = ints(t.v("TI_LAYER_OF_MODE"))?
            .into_iter()
            .map(|b| b as u8)
            .collect();
        out.block("ti_layer_mode", &modes);
        out.push_str(&format!(
            "TI_BORDER_VRAM    = ${:04X}\nTI_BORDER_MAP     = ${:04X}\nTI_BORDER_TILES   = {}\n\
             TI_BORDER_COLORS  = {}\nTI_BORDER_UP      = {}\n",
            t.n("TI_VRAM"),
            ti_map,
            ti_tiles.len(),
            ti_colors.len(),
            shop.compact.top
        ));
        // The shop's party: each possible member's three front frames,
        // twelve 4bpp tiles each, behind a pointer per member; its palette in
        // colour and in grey, sixteen colours each with the transparent one
        // first; which member each actor is; and the System's sixteen arrows
        // with their palette. See `party.rs` in `rm2k-snes-screens`.
        out.push_str("\n; --- the shop's party: see shop_party.s ---\n");
        let party = &screens.shop_party;
        let mut party_k = Vec::new();
        let mut party_pointers = Vec::new();
        let mut party_cgram = Vec::new();
        let mut members: Vec<(i64, i64)> = Vec::new();
        // Two actors drawn with the same CharSet share it: in A Blurred Line
        // there are two Kershes and three with the same sheet's index.
        let mut stored: Vec<(Vec<u8>, Vec<u8>)> = Vec::new();
        for m in &party.members {
            let actor = i64::from(m.actor);
            let Some(drawn) = &m.drawn else {
                continue;
            };
            let frames: Vec<_> = drawn.frames.iter().flatten().collect();
            let bytes = packed(&frames, 4);
            let mut cgram = palette16(&drawn.colors);
            cgram.extend(palette16(&drawn.greys));
            if let Some(k) = stored.iter().position(|s| s.0 == bytes && s.1 == cgram) {
                members.push((actor, k as i64));
                continue;
            }
            let k = stored.len() as i64;
            let label = format!("ti_party_tiles_{k}");
            out.block(&label, &bytes);
            party_pointers.push(format!("    .byte {}", crate::asm::pointer(&label)));
            party_cgram.extend(&cgram);
            stored.push((bytes, cgram));
            members.push((actor, k));
        }
        if members.len() > 255 {
            return Err(Bad::answer(format!(
                "the shop's party has {} members with a CharSet and a byte names 255",
                members.len()
            )));
        }
        let n_party_actors = members.iter().map(|&(a, _)| a + 1).max().unwrap_or(1);
        for a in 0..n_party_actors {
            party_k.push(
                members
                    .iter()
                    .find(|&&(b, _)| b == a)
                    .map_or(0xFF, |&(_, k)| k as u8),
            );
        }
        out.block("ti_party_k", &party_k);
        out.line(&format!(
            ".block {}\nti_party_ptr:",
            3 * party_pointers.len().max(1)
        ));
        if party_pointers.is_empty() {
            out.line("    .byte 0, 0, 0");
        }
        for p in &party_pointers {
            out.line(p);
        }
        if party_cgram.is_empty() {
            party_cgram.push(0);
        }
        out.block("ti_party_cgram", &party_cgram);
        out.block("ti_arrow_tiles", &packed(&party.arrows, 4));
        out.block("ti_arrow_cgram", &palette16(&party.arrow_colors));
        let party_tile0 = party.tile0 as i64;
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
        out.block("ti_party_oam", &oam);
        out.push_str(&format!(
            "TI_PARTY_ACTORS   = {}\nTI_PARTY_TILE0    = {}\nTI_PARTY_VRAM     = ${:04X}\n\
             TI_ARROW_TILE0    = {}\nTI_ARROW_VRAM     = ${:04X}\nTI_PARTY_MEMBERS  = {}\n\
             TI_PARTY_X0       = {}\nTI_PARTY_Y0       = {}\nTI_PARTY_STEP     = {}\n\
             TI_ARROW_DX       = {}\nTI_ARROW_DY       = {}\nTI_PARTY_RATE     = {}\n\
             TI_FRAME_TILES    = {}\nTI_FRAME_COLS     = {}\nTI_ARROW_FRAMES   = {}\n\
             TI_ARROW_UP       = {}\nTI_ARROW_SAME     = {}\nTI_ARROW_DOWN     = {}\n\
             TI_ARROW_EQUIPPED = {}\nTI_LAYER_BUY      = {}\nTI_PARTY_ON       = {}\n",
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
            i64::from(party.on)
        ));
        out.push_str("; --- the shop's party ends ---\n");
        // The End Game screen, whole: the "Yes" palette first.
        let end = &screens.end_game;
        let end_tiles = &end.tiles;
        let end_rows = &end.rows;
        out.block("end_tiles", &packed(end_tiles, 4));
        out.block("end_map", &words(end_rows));
        out.block("end_cgram", &palettes_cgram(&end.palettes));
        let ramp: Vec<u8> = ints(t.v("END_RAMP"))?
            .into_iter()
            .map(|b| b as u8)
            .collect();
        out.block("end_ramp", &ramp);
        out.push_str(&format!(
            "END_TILES   = {}\nEND_ROW0    = {}\nEND_ROWS    = {}\nEND_ENTERS  = {}\nEND_NO      = {}\n\
             END_FRAMES = {}\nEND_STEP_SONG = {}\n",
            end_tiles.len(),
            end.row0,
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
            glyphs: ScreenGlyphs::of(screens),
        };
        let shown = texts.glyphs.clone();
        let textos = &screens.texts;
        for item in &textos.items {
            for text in &item.texts {
                texts.add(text);
            }
        }
        // Dead texts after the item ones and before the others, so the
        // battle's indices go past 255 in a small cartridge: an item's name is
        // named by `3k`, so they cannot go in front of the items.
        for _ in 0..r.text_padding {
            texts.offsets.push((0, 0));
        }
        let param_text: Vec<i64> = textos.params.iter().map(|t| texts.add(t)).collect();
        let slot_text: Vec<i64> = textos.equipment.iter().map(|t| texts.add(t)).collect();
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
            actor_text.insert(a, texts.add(&plain(&shown, name)));
        }
        // And each rename's, in the order `OP_CHANGE_NAME` counts them.
        let name_text: Vec<i64> = r
            .names
            .iter()
            .map(|(_, name)| texts.add(&plain(&shown, name)))
            .collect();
        let mut shop_text = None;
        for l in textos.shop.iter().flatten().flatten() {
            let k = texts.add(l);
            shop_text.get_or_insert(k);
        }
        let owned_text = texts.add(&textos.owned);
        let carried_text = texts.add(&textos.carried);
        let currency_text = texts.add(&textos.currency);
        // The battle's: the LDB's terms —the three commands already trimmed,
        // the victory split as the stage checked it fits— and the rest.
        let model = self.model;
        let mtexts = &model.texts;
        let victory = &mtexts.victory;
        let mut battle_text = None;
        // The commands' texts the cartridge already has, by what they say:
        // an actor's command that says the same points to it —see
        // `actor_command_txt` below—.
        let mut command_texts: HashMap<String, i64> = HashMap::new();
        for (name, liblcf) in BATTLE_TERMS {
            let value = match name {
                "attack" => mtexts.attack.clone(),
                "defend" => mtexts.defend.clone(),
                "escape" => mtexts.escape.clone(),
                "victory" => victory[0].clone(),
                _ => battle_term(&self.r.battle_terms, db, liblcf)?,
            };
            let value = plain(&shown, &value);
            let k = texts.add(&value);
            if BA_COMMAND_TERMS.contains(&name) {
                command_texts.entry(value).or_insert(k);
            }
            battle_text.get_or_insert(k);
        }
        let battle_text = battle_text.unwrap_or(0);
        let revived_text = texts.add(&db_text(&shown, &mtexts.revived));
        let dead_text = texts.add(&db_text(&shown, &mtexts.dead));
        let victory2_text = texts.add(&db_text(&shown, victory.get(1).map_or("", String::as_str)));
        let rom_enemies: Vec<i64> = model.enemies.iter().map(|&e| e.into()).collect();
        let enemy_text = texts.add_each(&rom_enemies, |e| {
            by_number(&mtexts.enemies, e, "enemy").map(String::as_str)
        })?;
        let actions = &model.actions;
        let rom_skills: Vec<i64> = model.skills.iter().map(|&h| h.into()).collect();
        let skill_text = texts.add_each(&rom_skills, |h| {
            Ok(&by_number(&mtexts.skills, h, "skill")?.name)
        })?;
        let skill_desc_text = texts.add_each(&rom_skills, |h| {
            Ok(&by_number(&mtexts.skills, h, "skill")?.description)
        })?;
        // An item's description whole, for the battle's help window, which
        // has one line: the item screens split it in two, `3k + 1` and `3k +
        // 2`. Only the items the battle offers; the others point to text 0.
        let item_battle = &model.item_battle;
        let item_list = &textos.items;
        if item_battle.len() != item_list.len() {
            return Err(Bad::answer(
                "the battle's items and the screens' are not the same list",
            ));
        }
        let mut item_desc_battle = Vec::new();
        for (item, &battle) in item_list.iter().zip(item_battle) {
            if battle {
                let whole: Vec<&str> = item.texts[1..]
                    .iter()
                    .map(String::as_str)
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
        let taught: Vec<i64> = model.taught.iter().map(|&h| h.into()).collect();
        let whole_skill_text = texts.add_each(&taught, |h| Ok(&skill(h)?.name))?;
        let skill_msg1_text = texts.add_each(&rom_skills, |h| Ok(&skill(h)?.using_message1))?;
        let skill_msg2_text = texts.add_each(&rom_skills, |h| Ok(&skill(h)?.using_message2))?;
        let mut skill_command_text = HashMap::new();
        for &a in &r.actors {
            let name = plain(
                &shown,
                by_number(&mtexts.skill_commands, a, "actor")?.as_str(),
            );
            let k = texts.add(&name);
            command_texts.entry(name).or_insert(k);
            skill_command_text.insert(a, k);
        }
        // The conditions' two battle messages, by LDB number —see
        // `battle_states.s`—: the one said while it lasts and the one said
        // when it goes. The empty ones, which are most, share one text.
        // **They are the last texts**, with the empty one first: the ones
        // before keep the numbers they had before 2026-10-12.
        let empty_text = texts.add("");
        let states_n = db.states.keys().max().map_or(1, |&m| m.max(0) as usize + 1);
        let mut state_affected_text = vec![empty_text; states_n];
        let mut state_recovery_text = vec![empty_text; states_n];
        // And since 2026-11-01 the three a skill's result says: given to an
        // actor, given to an enemy, and already held.
        let mut state_actor_text = vec![empty_text; states_n];
        let mut state_enemy_text = vec![empty_text; states_n];
        let mut state_already_text = vec![empty_text; states_n];
        for (&id, st) in &db.states {
            let Ok(k) = usize::try_from(id) else { continue };
            for (message, out) in [
                (&st.message_affected, &mut state_affected_text),
                (&st.message_recovery, &mut state_recovery_text),
                (&st.message_actor, &mut state_actor_text),
                (&st.message_enemy, &mut state_enemy_text),
                (&st.message_already, &mut state_already_text),
            ] {
                if !message.is_empty() {
                    out[k] = texts.add(&db_text(&shown, message));
                }
            }
        }
        // The skills screen's level term, since 2026-10-12: after the
        // conditions', for the same reason they go last.
        let level_text = texts.add(&db_text(&shown, &term(db, "lvl_short")?));
        out.push_str(&format!("SK_TXT_LEVEL = {level_text}\n"));
        // And the terms of a skill's result lines, since 2026-10-20: after
        // that, for the same reason, and one after the other —see
        // `RESULT_TERMS`—.
        for (name, liblcf) in RESULT_TERMS {
            let value = battle_term(&self.r.battle_terms, db, liblcf)?;
            let k = texts.add(&plain(&shown, &value));
            out.push_str(&format!("BA_TXT_{:<11}= {}\n", name.to_uppercase(), k));
        }
        // Each actor's commands, as the battle's model names them —a 2003
        // game's from its battle commands, see `command_names` in
        // `rm2k-snes-battle`'s rules—: the text the cartridge already has
        // when it says the same, so a 2000 game adds none, and otherwise a
        // new one, after every other for the same reason as the result
        // terms'.
        let mut command_text = HashMap::new();
        for &a in &r.actors {
            let mut row = Vec::new();
            for (slot, name) in by_number(&mtexts.commands, a, "actor")?.iter().enumerate() {
                let name = plain(&shown, name);
                // The skill command is the one `skill_commands` gave this
                // actor, its own text since before the other four.
                let own = skill_command_text
                    .get(&a)
                    .filter(|_| BA_COMMAND_TERMS[slot] == "skill");
                let k = match own.or_else(|| command_texts.get(&name)) {
                    Some(&k) => k,
                    None => {
                        let k = texts.add(&name);
                        command_texts.insert(name, k);
                        k
                    }
                };
                row.push(k);
            }
            command_text.insert(a, row);
        }
        let item_texts = if texts.data.is_empty() {
            vec![0]
        } else {
            texts.data.clone()
        };
        out.block("item_texts", &item_texts);
        if slot_blocks.len() > 255 {
            return Err(Bad::answer(format!(
                "the slots screen has {} blocks and the tables that name them are one byte",
                slot_blocks.len()
            )));
        }
        // The palette, padded to the sixteen the console uploads at once.
        out.block("slot_cgram", &palettes_cgram(&slots.palettes));

        // The tables that name the cell blocks: outside bank 0, read with
        // `lda f:slot_block_lo, x`, because they grow with every face.
        out.push_str("\n.segment \"RODATA\"\n");
        for (field, prefix) in [("lo", "<"), ("hi", ">"), ("bk", "^")] {
            out.bytes(
                format!("slot_block_{field}"),
                slot_blocks.iter().map(|e| format!("{prefix}{e}")),
            );
        }
        // Where each row goes in the tilemap: in bank 0.
        out.push_str("\n.segment \"TABLES\"\n");
        let row_of: Vec<i64> = (0..i64::from(SLOTS))
            .map(|n| {
                i64::from(SLOT_MAP) + (t.n("SLOT_Y") + n * t.n("SLOT_STEP")).div_euclid(cell) * 32
            })
            .collect();
        out.words_unplaced("slot_vram", &row_of);
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
        out.words_unplaced("slot_face_vram", face_vram);
        let name_vram: Vec<i64> = row_of
            .iter()
            .map(|r| r + t.n("NAME_ROW") * 32 + t.n("NAME_COL"))
            .collect();
        out.words_unplaced("slot_name_vram", name_vram);
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
        let face_blocks =
            (0..n_actors_slots).map(|a| face_block.get(&a).map_or(0xFF, |&b| b as i64));
        // By actor id: outside bank 0, read with `lda f:slot_face_block, x`,
        // because it grows with every actor.
        out.push_str(".segment \"RODATA\"\n");
        out.bytes("slot_face_block", face_blocks);
        out.push_str(".segment \"TABLES\"\n");
        // The pause menu: its blocks, and where each thing goes, in words.
        let vram_cell = |row: i64, col: i64| i64::from(SLOT_MAP) + row * 32 + col;
        // The custom menus' options go after RM2k's five, as commands 5 and
        // on, and the column has a row for each: see `menu_rows_build`.
        // And the debug screen's, after them: one more command, which the
        // screens stage drew after theirs.
        let custom_n =
            screens.custom_menus.labels.len() as i64 + i64::from(screens.debug_screen.is_some());
        let option_rows: Vec<i64> = (0..t.n("MENU_OPTIONS") + custom_n)
            .map(|n| (t.n("MENU_OPT_Y") + n * t.n("MENU_OPT_STEP")).div_euclid(cell))
            .collect();
        out.push_str(&format!(
            "MENU_OPTIONS      = {}\nMENU_EQUIPMENT    = {}\nMENU_SAVE         = {}\nMENU_END          = {}\n\
             MENU_BLK_OPTION   = {}\nMENU_BLK_CURRENCY = {}\nMENU_BLK_ROW      = {}\nMENU_OPT_COLS     = {}\n\
             MENU_CURRENCY_COLS = {}\nMENU_CURRENCY_VRAM = {}\nMENU_ACTOR_COLS   = {}\nMENU_ACTOR_ROWS   = {}\n\
             MENU_ROWS_PARTY   = {}\nMENU_ACTORS_N     = {}\nMENU_HP_DIGITS    = {}\nMENU_HP_OFS       = {}\n\
             MENU_FACE_CELLS   = {}\nMENU_NAME_COLS    = {}\nMENU_NAME_OFS = {}\nMENU_LEVEL_OFS    = {}\n\
             MENU_MAX_DIGITS   = {}\nMENU_MAX_OFS      = {}\n",
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
        out.bytes_unplaced(
            "menu_done",
            (0..t.n("MENU_OPTIONS") + custom_n)
                .map(|n| u8::from(done.contains(&n) || n >= t.n("MENU_OPTIONS"))),
        );
        out.words_unplaced(
            "menu_option_vram",
            option_rows
                .iter()
                .map(|&f| vram_cell(f, t.n("MENU_OPT_COL"))),
        );
        // Where a party row's first cell goes: the actor choice's four
        // rows, and after them, at `MENU_ROWS_PARTY`, the pause menu's
        // first row, where it paints each member's to keep it —see
        // `menu_list_paint`—.
        out.words_unplaced(
            "menu_row_vram",
            (0..t.n("MENU_PARTY_ROWS"))
                .map(|r| {
                    vram_cell(
                        t.n("TARGET_PARTY_ROW") + r * t.n("TARGET_ROW_CELLS"),
                        t.n("TARGET_ACTOR_COL"),
                    )
                })
                .chain([vram_cell(0, t.n("MENU_ACTOR_COL"))]),
        );
        // What the screen composes on the fly goes outside bank 0: it is read
        // with `lda f:`. The glyphs are indexed by character, and the ones
        // this cartridge does not use stay in the empty cell.
        out.push_str(".segment \"RODATA\"\n");
        // Where the command cursor and the slot cursor start on BG1, per
        // command and per slot: their rectangles on the first one, which
        // `alone` in `rm2k-snes-screens` cut, moved down by whole cells.
        let target = &screens.target;
        let compact = &target.compact;
        let bg1_cell = |row: i64, col: i64| t.n("TARGET_MAP") + row * 32 + col;
        let cmd_at = compact.menu_cmd_at;
        out.words(
            "menu_cursor_vram",
            (0..t.n("MENU_OPTIONS") + custom_n).map(|n| {
                bg1_cell(
                    cmd_at.0 as i64 + n * t.n("MENU_OPT_STEP").div_euclid(cell),
                    cmd_at.2 as i64,
                )
            }),
        );
        let slot_at = compact.slot_bar_at;
        out.words(
            "slot_bar_vram",
            (0..i64::from(SLOTS)).map(|n| {
                bg1_cell(
                    slot_at.0 as i64 + n * t.n("SLOT_STEP").div_euclid(cell),
                    slot_at.2 as i64,
                )
            }),
        );
        // A cell's word, in the palette `palette` counts.
        let cells = |cells: &[u16], palette: u32| {
            hex4(
                cells
                    .iter()
                    .map(|&c| i64::from(entry(c.into(), false, false, palette))),
            )
        };
        // Two cells a letter, the top and the bottom; the empty cell for the
        // letters the cartridge does not use.
        let first = t.n("ITEM_FIRST_CHAR");
        let chars = t.n("ITEM_CHARS");
        let mut glyph_cells = Vec::new();
        for n in first..first + chars {
            let letter = char::from_u32(n as u32).unwrap_or('?');
            glyph_cells.extend(match menu.glyphs.get(&letter) {
                Some(letter) => cells(letter, 1),
                None => cells(&[0, 0], 0),
            });
        }
        out.words("slot_glyph_cells", glyph_cells);
        out.words("menu_exp_finished", cells(&menu.exp_term, 0));
        // The SP term the same way: the actor choice's fourth line.
        out.words("menu_sp_finished", cells(&menu.sp_term, 0));
        // And the pause menu's arrows, which go in sprites in a palette of
        // their own: see `MENU_ARROW_Y`.
        out.words("menu_arrow_cells", cells(&menu.arrows, 0));
        let mut arrow_colors = menu.arrow_colors.clone();
        arrow_colors.resize(16, [0, 0, 0]);
        out.block("menu_arrow_cgram", &cgram_bytes(&arrow_colors));
        // The actor choice: its windows on BG1, a single tilemap and the bar
        // only where it changes; and each medicine's name in two lines.
        let obj_tiles = &target.tiles;
        let obj_colors = &target.colors;
        out.block("target_tiles", &packed(obj_tiles, 8));
        out.block("target_map", &words(&compact.map));
        out.block("target_bars", &bars(&compact.bars));
        out.block("menu_bar_cells", &words(&compact.menu_bar));
        let bar_at = compact.menu_bar_at;
        out.push_str(&format!(
            "MENU_BAR_ROW0 = {}\nMENU_BAR_ROWS = {}\nMENU_BAR_COL0 = {}\nMENU_BAR_COLS = {}\n",
            bar_at.0, bar_at.1, bar_at.2, bar_at.3
        ));
        // The pause menu's command cursor and the slot cursor, each on its
        // first row and over nothing, like the bar: see `alone` in
        // `rm2k-snes-screens`.
        for (cells, bar_at, name, prefix) in [
            (
                &compact.menu_cmd,
                compact.menu_cmd_at,
                "menu_cmd_cells",
                "MENU_CMD",
            ),
            (
                &compact.slot_bar,
                compact.slot_bar_at,
                "slot_bar_cells",
                "SLOT_BAR",
            ),
        ] {
            out.block(name, &words(cells));
            out.push_str(&format!(
                "{prefix}_ROW0 = {}\n{prefix}_ROWS = {}\n{prefix}_COL0 = {}\n{prefix}_COLS = {}\n",
                bar_at.0, bar_at.1, bar_at.2, bar_at.3
            ));
        }
        out.block("target_cgram", &cgram_bytes(obj_colors));
        // The same choice for a skill: the cost's term over the count's,
        // and the bar over the whole party as its distinct cell rows and,
        // per party size, which goes on each row. See
        // `compact_target_skill` in `rm2k-snes-screens`.
        let skill = &target.skill;
        let (term_at, all_at) = (skill.term_at, skill.all_at);
        out.block("target_term", &words(&skill.term));
        out.block("target_all_rows", &bars(&skill.all_rows));
        let all_index: Vec<u8> = skill.all.iter().flatten().copied().collect();
        out.block("target_all", &all_index);
        out.push_str(&format!(
            "TARGET_TERM_ROW0 = {}\nTARGET_TERM_ROWS = {}\nTARGET_TERM_COL0 = {}\nTARGET_TERM_COLS = {}\n\
             TARGET_ALL_ROW0 = {}\nTARGET_ALL_ROWS = {}\nTARGET_ALL_COL0 = {}\nTARGET_ALL_COLS = {}\n",
            term_at.0, term_at.1, term_at.2, term_at.3, all_at.0, all_at.1, all_at.2, all_at.3
        ));
        // Each medicine's name on the line on top, `TARGET_NAME_WIDTH`
        // letters, as the screens stage stored it: `target_text` there.
        let width = t.n("TARGET_NAME_WIDTH") as usize;
        let mut medicine_names: HashMap<i64, Vec<u8>> = HashMap::new();
        for m in &textos.medicines {
            medicine_names.insert(m.number.into(), target_name_bytes(&m.name, width, &shown)?);
        }
        let medicines: Vec<i64> = r
            .items
            .iter()
            .copied()
            .filter(|n| medicine_names.contains_key(n))
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
        out.block("target_name", &target_name);
        let mut names: Vec<u8> = medicines
            .iter()
            .flat_map(|n| medicine_names[n].iter().copied())
            .collect();
        if names.is_empty() {
            names.push(b' '); // a label over nothing would be no `.block`
        }
        out.block("target_names", &names);
        out.push_str(&format!(
            "TARGET_VRAM       = ${:04X}\nTARGET_MAP        = ${:04X}\nTARGET_TILES      = {}\n\
             TARGET_CGRAM      = {}\nTARGET_COLORS     = {}\nTARGET_NAME_WIDTH = {}\n\
             TARGET_NAME_VRAM = {}\nTARGET_COUNT_VRAM = {}\nTARGET_BAR_ROW0 = {}\n\
             TARGET_BAR_ROWS = {}\nTARGET_BAR_COL0 = {}\nTARGET_BAR_COLS = {}\n\
             TARGET_ROW_CELLS = {}\n",
            t.n("TARGET_VRAM"),
            t.n("TARGET_MAP"),
            obj_tiles.len(),
            t.n("TARGET_CGRAM"),
            obj_colors.len(),
            t.n("TARGET_NAME_WIDTH"),
            vram_cell(t.n("TARGET_NAME_ROW"), t.n("TARGET_NAME_COL")),
            vram_cell(t.n("TARGET_COUNT_ROW"), t.n("TARGET_COUNT_COL")),
            compact.row0,
            compact.rows,
            compact.col0,
            compact.cols,
            t.n("TARGET_ROW_CELLS")
        ));
        out.push_str(&format!(
            "MENU_EXP_X        = {}\nMENU_EXP_NUM_X    = {}\nMENU_EXP_Y        = {}\nMENU_EXP_STEP     = {}\n\
             MENU_EXP_DIGITS   = {}\nMENU_EXP_LETTERS  = {}\n",
            t.n("MENU_EXP_X"),
            t.n("MENU_EXP_X") + t.n("MENU_EXP_NUM_DX") - t.n("GLYPH_DX"),
            t.n("MENU_EXP_Y") - t.n("GLYPH_DY"),
            t.n("FONT_WIDTH"),
            t.n("MENU_EXP_DIGITS"),
            t.n("MENU_EXP_LETTERS")
        ));
        // The SP line, in cells on both screens: its letters, and on the
        // actor choice where its term goes, counted from a row's first
        // cell like the HP's —on the HP's line, see `TARGET_SP_COL`—. The
        // number follows the term: see `menu_sp_put`.
        out.push_str(&format!(
            "MENU_SP_LETTERS   = {}\nMENU_SP_TERM_CELLS = {}\nTARGET_SP_TERM_OFS = {}\n",
            t.n("MENU_SP_LETTERS"),
            t.n("MENU_SP_TERM_CELLS"),
            t.n("MENU_HP_ROW") * 32 + t.n("TARGET_SP_COL") - t.n("TARGET_ACTOR_COL")
        ));
        // The pause menu's list: three rows of nine cells from the first
        // row's cell, each actor painted there once; and the SP line in
        // cells, counted from the row's first cell like the HP's.
        out.push_str(&format!(
            "MENU_LIST_ROWS    = {}\nMENU_SHOWN        = {}\nMENU_LIST_HEIGHT  = {}\n\
             MENU_LIST_VRAM    = {}\nMENU_SP_TERM_OFS  = {}\nMENU_SP_NUM_OFS   = {}\n\
             MENU_ARROW_X      = {}\nMENU_ARROW_Y      = {}\n",
            t.n("MENU_LIST_ROWS"),
            t.n("MENU_SHOWN"),
            t.n("MENU_LIST_ROWS") * cell,
            i64::from(SLOT_MAP) + t.n("MENU_ACTOR_COL"),
            t.n("MENU_SP_ROW") * 32 + t.n("MENU_SP_X") / cell - t.n("MENU_ACTOR_COL"),
            t.n("MENU_SP_ROW") * 32 + t.n("MENU_HP_COL") - t.n("MENU_ACTOR_COL"),
            t.n("MENU_ARROW_X"),
            t.n("MENU_ARROW_Y")
        ));
        self.menu_states(out, t, &slots.states)?;
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
        let mut strip: Vec<u8> = Vec::new();
        for a in 0..n_actors_slots {
            let [name, level, max] = textos
                .actors
                .get(a as usize)
                .ok_or_else(|| Bad::answer(format!("the screens wrote no strips for actor {a}")))?;
            let row = format!("{name:<w$}{level}{max}", w = SLOT_TEXT_LEVEL as usize);
            strip.extend(strip_bytes(&row, SLOT_TEXT_WIDTH as usize, &shown)?);
        }
        // And after the actors' rows, one per rename, with its name alone:
        // the menu and the slot screen take it instead of the actor's own
        // when the actor carries it. See the runtime's `actor_names.s`.
        let renamed = &textos.renamed;
        if renamed.len() != r.names.len() {
            return Err(Bad::answer(format!(
                "the screens wrote {} renamed names and the request has {}",
                renamed.len(),
                r.names.len()
            )));
        }
        for (_, name) in renamed {
            strip.extend(strip_bytes(name, SLOT_TEXT_WIDTH as usize, &shown)?);
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
        out.words("name_actor", renamed_actors.iter().copied());
        out.bytes("slot_actor_text", or_zero(decimal(strip)));
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
                command_text,
                state_affected_text,
                state_recovery_text,
                state_actor_text,
                state_enemy_text,
                state_already_text,
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
    /// Per actor, its commands' texts, in `BA_COMMANDS`' order.
    command_text: HashMap<i64, Vec<i64>>,
    state_affected_text: Vec<i64>,
    state_recovery_text: Vec<i64>,
    state_actor_text: Vec<i64>,
    state_enemy_text: Vec<i64>,
    state_already_text: Vec<i64>,
    rom_enemies: Vec<i64>,
    rom_skills: Vec<i64>,
    actions: &'a BTreeMap<i32, Vec<(i64, Option<i32>, bool)>>,
    border_tiles: usize,
    border_colors: usize,
}

impl Rest<'_> {
    /// The party's conditions where the menu's rows and the skills screen
    /// say "Normal" —`menu_state_paint` and `sk_status`—, from the screens
    /// stage's `states`: by LDB number from 0, each name in ASCII padded to
    /// `STATE_NAME_W` letters —at least the cells it may take, so that
    /// `tl_strip` reads as many letters as fit— and its length, and its
    /// ink; per ink, the palette entry of each glyph row, the cells'
    /// palette and the colour the skills screen uploads.
    fn menu_states(
        &self,
        out: &mut Inc,
        t: &Geometry,
        states: &rm2k_snes_screens::answer::States,
    ) -> Result<()> {
        let names = &states.names;
        let cols = t.n("MENU_STATE_COLS") as usize;
        let width = names
            .iter()
            .map(|n| n.chars().count())
            .max()
            .unwrap_or(0)
            .max(cols);
        if width > 255 {
            return Err(Bad::answer("a condition's name does not fit in a byte"));
        }
        let mut padded: Vec<u8> = Vec::new();
        for name in names {
            padded.extend(format!("{name:<width$}").bytes());
        }
        let inks = &states.inks;
        let mut rows = Vec::new();
        let mut attr = Vec::new();
        let mut cgram = Vec::new();
        for ink in inks {
            rows.extend(&ink.rows);
            // And the shadow's entry in the ink's palette.
            rows.push(if ink.palette == 0 {
                states.shadow
            } else {
                states.gray_shadow
            });
            attr.push(i64::from(ink.palette) << 10);
            cgram.extend(ink.cgram.iter().map(|&w| i64::from(w)));
        }
        out.push_str(&format!(
            "; The party's conditions, where the rows say Normal.\n\
             MENU_STATE_OFS    = {}\nMENU_STATE_COLS   = {cols}\nSLOT_SHADOW       = {}\n\
             SLOT_GRAY_SHADOW  = {}\nSTATE_NAMES_N     = {}\nSTATE_NAME_W      = {width}\n\
             STATE_INKS_N      = {}\nSK_STATE_PALETTE  = {}\n",
            t.n("MENU_LEVEL_ROW") * 32 + t.n("MENU_STATE_COL") - t.n("MENU_ACTOR_COL"),
            states.shadow,
            states.gray_shadow,
            names.len(),
            inks.len(),
            t.n("SK_STATE_PALETTE"),
        ));
        out.bytes("state_names", padded.iter());
        out.bytes("state_name_n", names.iter().map(|n| n.chars().count()));
        out.bytes("state_ink", states.ink.iter());
        out.bytes("state_ink_rows", rows);
        out.words("state_ink_attr", hex4(attr));
        out.words("state_ink_cgram", hex4(cgram));
        out.push_str("; The end of the party's conditions.\n");
        Ok(())
    }
}

impl Rest<'_> {
    /// The conditions, one row per LDB number from 0 —which is nobody's—,
    /// outside bank 0: what `battle_states.s` does with them. Every one of
    /// the database's goes, and not only the ones the troop pages give: the
    /// tables are a byte a field, and the bytecode names them by number.
    fn states(&self, out: &mut Inc, x: &ItemTexts, n_actors: i64) -> Result<()> {
        let db = self.db;
        let n = x.state_affected_text.len();
        if n > 256 {
            return Err(Bad::answer(format!(
                "{} conditions do not fit in OP_MONSTER_STATE's byte",
                n - 1
            )));
        }
        let per = |f: &dyn Fn(&ditto::schema::State) -> i64| -> Vec<i64> {
            (0..n)
                .map(|k| {
                    db.states
                        .get(&(k as i32))
                        .map_or(0, |st| f(st).clamp(0, 255))
                })
                .collect()
        };
        out.push_str(&format!(
            "STATES_N = {n}
"
        ));
        out.bytes("state_priority", per(&|st| st.priority.into()));
        out.bytes("state_restrict", per(&|st| st.restriction.to_i32().into()));
        out.bytes("state_hold", per(&|st| st.hold_turn.into()));
        out.bytes("state_auto", per(&|st| st.auto_release_prob.into()));
        out.bytes("state_damage", per(&|st| st.release_by_damage.into()));
        out.bytes("state_hit", per(&|st| st.reduce_hit_ratio.into()));
        // Which parameters it halves, one bit each in the order of
        // `BA_ATK`, `BA_DEF`, `BA_SPI`, `BA_AGI`.
        out.bytes(
            "state_halves",
            per(&|st| {
                i64::from(st.affect_attack)
                    | i64::from(st.affect_defense) << 1
                    | i64::from(st.affect_spirit) << 2
                    | i64::from(st.affect_agility) << 3
            }),
        );
        // Whether the battle's end takes it away from an actor:
        // `State::RemoveAllBattle`, which keeps only the ones that persist
        // —`type` 1— and never wear off on their own —`auto_release_prob`
        // 0—.
        out.bytes(
            "state_end",
            per(&|st| i64::from(st.r#type.to_i32() != 1 || st.auto_release_prob > 0)),
        );
        // What it does to its holder on the map, `Game_Party::
        // ApplyStateDamage`: four words per condition —every how many of
        // the party's steps and how many HP, then the same for SP—, the
        // amount signed, negative a loss. Zero steps, zero amount or
        // `ChangeType_nothing` is nothing, and both come out 0.
        let map_change = |steps: i32, val: i32, kind: i32| -> [i64; 2] {
            if steps <= 0 || val <= 0 || kind == 2 {
                [0, 0]
            } else if kind == 0 {
                [steps.into(), -i64::from(val)]
            } else {
                [steps.into(), val.into()]
            }
        };
        let map: Vec<i64> = (0..n)
            .flat_map(|k| {
                db.states.get(&(k as i32)).map_or([0; 4], |st| {
                    let [hs, hv] = map_change(
                        st.hp_change_map_steps,
                        st.hp_change_map_val,
                        st.hp_change_type.to_i32(),
                    );
                    let [ss, sv] = map_change(
                        st.sp_change_map_steps,
                        st.sp_change_map_val,
                        st.sp_change_type.to_i32(),
                    );
                    [hs, hv, ss, sv]
                })
            })
            .map(|v| v & 0xFFFF)
            .collect();
        out.words("state_map", map);
        // And what it does each time its holder acts in battle,
        // `ApplyConditions`: four words per condition —the HP's
        // `hp_change_val` and `hp_change_max`, a percentage of the maximum,
        // and the same with SP—, both 0 with `ChangeType_nothing`; and per
        // condition whether each is a loss, bit 0 the HP's and bit 1 the
        // SP's.
        let turn_change = |kind: i32, val: i32, pct: i32| -> [i64; 2] {
            if kind == 2 {
                [0, 0]
            } else {
                [val.clamp(0, 0x7FFF).into(), pct.clamp(0, 100).into()]
            }
        };
        let turn: Vec<i64> = (0..n)
            .flat_map(|k| {
                db.states.get(&(k as i32)).map_or([0; 4], |st| {
                    let [hv, hp] = turn_change(
                        st.hp_change_type.to_i32(),
                        st.hp_change_val,
                        st.hp_change_max,
                    );
                    let [sv, sp] = turn_change(
                        st.sp_change_type.to_i32(),
                        st.sp_change_val,
                        st.sp_change_max,
                    );
                    [hv, hp, sv, sp]
                })
            })
            .collect();
        out.words("state_turn", turn);
        out.bytes(
            "state_turn_loss",
            per(&|st| {
                i64::from(st.hp_change_type.to_i32() == 0)
                    | i64::from(st.sp_change_type.to_i32() == 0) << 1
            }),
        );
        self.state_odds(out, x, n_actors)?;
        out.words("state_affected", x.state_affected_text.iter());
        out.words("state_recovery", x.state_recovery_text.iter());
        out.words("state_actor", x.state_actor_text.iter());
        out.words("state_enemy", x.state_enemy_text.iter());
        out.words("state_already", x.state_already_text.iter());
        Ok(())
    }
}

impl Rest<'_> {
    /// What a skill or a weapon gives, and the odds it takes hold:
    /// `battle_states.s`'s `ba_st_skill`, and `rm2k-snes-battle`'s
    /// `states` for the model.
    ///
    /// * `st_lists`: lists of conditions by number, each ended by a 0, the
    ///   first one empty. `skill_st_at` gives each skill the byte where its
    ///   `state_effects` start —0, none—, and `item_st_at` each item its
    ///   `state_set`'s: what an equipment gives or guards from, and what a
    ///   medicine removes.
    /// * `item_st_pct`: an armor's `100 - state_chance`, what it leaves of
    ///   the odds of what it lists; a weapon's `state_chance` with bit 7.
    /// * `st_used`: per condition, its column in the ranks —only the ones a
    ///   skill or a weapon gives have one—, or $FF.
    /// * `st_rate`: per column, its five rates, `A` to `E`.
    /// * `st_ranks`: rows of `ST_USED_N` ranks, one per actor —its own,
    ///   before its armor— and then one per enemy, in `enemy_*` order: the
    ///   enemy `k`'s row is `ACTORS_N + k`.
    fn state_odds(&self, out: &mut Inc, x: &ItemTexts, n_actors: i64) -> Result<()> {
        use rm2k_snes_battle::states as st;
        let (r, db) = (self.r, self.db);
        let mut lists: Vec<i64> = vec![0];
        let mut at_of: HashMap<Vec<i64>, i64> = HashMap::new();
        let mut used = BTreeSet::new();
        let mut place = |ids: Vec<i64>, lists: &mut Vec<i64>| -> i64 {
            if ids.is_empty() {
                return 0;
            }
            if let Some(&at) = at_of.get(&ids) {
                return at;
            }
            let at = lists.len() as i64;
            lists.extend(&ids);
            lists.push(0);
            at_of.insert(ids, at);
            at
        };
        let n_states = db.states.keys().max().copied().unwrap_or(0) as i64;
        let fits = |ids: &[i64]| -> Result<()> {
            match ids.iter().find(|&&id| id > n_states || id > 255) {
                Some(id) => Err(Bad::answer(format!(
                    "condition {id} is given, and the database has {n_states}"
                ))),
                None => Ok(()),
            }
        };
        let mut skill_at = Vec::new();
        for &h in &x.rom_skills {
            let ids = st::of_skill(&db.skill(h as i32).map_err(bad)?.state_effects);
            fits(&ids)?;
            if rm2k_snes_battle::db::targets_enemies(db.skill(h as i32).map_err(bad)?) {
                used.extend(ids.iter().copied());
            }
            skill_at.push(place(ids, &mut lists));
        }
        let mut item_at = Vec::new();
        let mut item_pct = Vec::new();
        for &n in &r.items {
            let it = db.item(n as i32).map_err(bad)?;
            let kind = it.r#type.to_i32();
            let weapon = kind == rm2k_snes_battle::db::ITEM_WEAPON;
            let armor = (2..=5).contains(&kind);
            // A medicine's are the ones it removes, without the dead one,
            // which is `MED_RAISES`: see `act_st_cure` in party_states.s.
            let medicine = kind == rm2k_snes_battle::db::ITEM_MEDICINE;
            let ids = if weapon || armor {
                st::of_skill(&it.state_set)
            } else if medicine {
                let mut ids = st::of_skill(&it.state_set);
                ids.retain(|&id| id != 1);
                ids
            } else {
                Vec::new()
            };
            fits(&ids)?;
            let chance = i64::from(it.state_chance).clamp(0, 100);
            if weapon {
                used.extend(ids.iter().copied());
                item_pct.push(chance | 0x80);
            } else {
                item_pct.push(100 - chance);
            }
            item_at.push(place(ids, &mut lists));
        }
        if lists.len() > 0x10000 {
            return Err(Bad::answer("the conditions' lists don't fit in a bank"));
        }
        let used: Vec<i64> = used.into_iter().filter(|&id| id >= 1).collect();
        if used.len() > 255 {
            return Err(Bad::answer(format!("{} conditions given", used.len())));
        }
        out.push_str(&format!("ST_USED_N = {}\n", used.len()));
        out.bytes("st_lists", lists);
        out.words("skill_st_at", skill_at);
        out.words("item_st_at", item_at);
        out.bytes("item_st_pct", item_pct);
        let states_n = x.state_affected_text.len() as i64;
        out.bytes(
            "st_used",
            (0..states_n).map(|id| {
                used.iter()
                    .position(|&u| u == id)
                    .map_or(0xFF, |k| k as i64)
            }),
        );
        let rates: Vec<i64> = used
            .iter()
            .flat_map(|&id| (0..5).map(move |rank| st::rate(db, id, rank).clamp(0, 100)))
            .collect();
        out.bytes("st_rate", rates);
        let mut ranks = Vec::new();
        for a in 0..n_actors {
            for &id in &used {
                ranks.push(match db.actors.get(&(a as i32)) {
                    Some(_) => st::actor_rank(db, a as i32, id).map_err(bad)?,
                    None => st::ACTOR_RANK,
                });
            }
        }
        for &e in &x.rom_enemies {
            for &id in &used {
                ranks.push(st::enemy_rank(db, e as i32, id).map_err(bad)?);
            }
        }
        if ranks.len() > 0x10000 {
            return Err(Bad::answer("the condition ranks don't fit in a bank"));
        }
        out.bytes("st_ranks", ranks);
        Ok(())
    }
}

fn bad(b: rm2k_snes_battle::Bad) -> Bad {
    Bad::answer(b.message().to_string())
}

impl Rest<'_> {
    fn items_and_battle(&self, out: &mut Inc, texts: &mut Texts, x: ItemTexts) -> Result<()> {
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
        out.push_str(&format!(
            "ITEMS_ROM         = {}\nITEMS_CGRAM_N     = {}\nITEM_ROWS         = {}\n\
             ITEM_CURSOR_COL   = {}\nITEM_NAME_COL     = {}\nITEM_DIGITS_COL   = {}\nITEM_LIST_POS     = {}\n\
             ITEM_FIRST_CHAR = {}\nSCR_TEXT_X        = {}\nSCR_TEXT_Y        = {}\n\
             ITEM_BORDER_VRAM  = ${:04X}\nITEM_BORDER_TILES = {}\n\
             ITEM_BORDER_MAP   = ${:04X}\nITEM_BORDER_CGRAM = {}\nITEM_BORDER_COLORS = {}\nITEM_BORDER_ROWS  = {}\n\
             ITEM_BORDER_LIST  = {}\nITEM_TEXT_MORE    = {}\n",
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
            i64::from(SLOT_VRAM) + self.screens.items_border_first as i64 * 32,
            x.border_tiles,
            t.n("ITEM_BORDER_MAP"),
            t.n("ITEM_BORDER_CGRAM"),
            x.border_colors,
            ROWS,
            t.n("ITEM_LIST_Y").div_euclid(cell),
            t.n("ITEM_MORE_PAIRS")
        ));
        // The item tables go outside bank 0, read with `lda f:item_k, x`:
        // they grow with every item the maps bring. `item_k` is a word per
        // RM2k number, $FFFF for one the cartridge does not carry: ABL's
        // whole game carries 264 items, and until 2026-10-15 it was a byte.
        out.push_str(".segment \"RODATA\"\n");
        out.words(
            "item_k",
            (0..ITEMS_N as i64).map(|n| k_of.get(&n).map_or(0xFFFF, |&k| k as i64)),
        );
        out.words("item_id", items.iter());
        // Whether it goes in white and does something on the map, whether
        // it opens the actor choice, and whether it is a two-handed weapon.
        // Whether using it spends it is `item_uses`'s, below.
        let flags: HashMap<i64, (bool, bool)> = self
            .screens
            .texts
            .items
            .iter()
            .map(|i| (i.number.into(), (i.usable, i.needs_actor)))
            .collect();
        let mut uses = Vec::new();
        for &n in items {
            let (usable, needs) = flags
                .get(&n)
                .copied()
                .ok_or_else(|| Bad::answer(format!("item {n} has no text")))?;
            let it = item(n)?;
            // And whether it spares its wearer a terrain's damage: only an
            // armor, which is what `PreventsTerrainDamage` walks —its
            // `ForEachEquipment<false, true>`—. See runtime/terrain_steps.s.
            let armor = (ITEM_SHIELD..=ITEM_ACCESSORY).contains(&it.r#type.to_i32());
            uses.push(
                i64::from(usable)
                    | if needs { 4 } else { 0 }
                    | if it.two_handed { 8 } else { 0 }
                    | if armor && it.no_terrain_damage {
                        ITEM_USE_NO_TERRAIN_DAMAGE
                    } else {
                        0
                    },
            );
        }
        out.bytes("item_use", uses);
        out.push_str(&format!(
            "ITEM_USE_NO_TERRAIN_DAMAGE = ${ITEM_USE_NO_TERRAIN_DAMAGE:02X}\n"
        ));
        // Each terrain's HP per step, by its id, signed: `damage` of the
        // database, which `terrain_step` takes from every actor as the
        // hero begins a step onto it. Id 0 is no terrain, and a hole in the
        // ids is a terrain that hurts nobody.
        let top = db.terrains.keys().copied().max().unwrap_or(0).max(0);
        let damage: Vec<i64> = (0..=top)
            .map(|id| {
                db.terrains
                    .get(&id)
                    .map_or(0, |t| i64::from(t.damage) & 0xFFFF)
            })
            .collect();
        out.push_str(&format!("TERRAINS_N = {}\n", damage.len()));
        out.words("terrain_damage", damage);
        // And what each adds to the steps to a battle: its `encounter_rate`,
        // which `encounter_step` adds to the accumulated rate, and the same
        // rate as the factor in 1/256 it multiplies the chance by —see
        // `factor` in `rm2k-snes-battle`—. A hole in the ids is worth 100,
        // liblcf's default.
        let rate: Vec<i64> = (0..=top)
            .map(|id| {
                db.terrains
                    .get(&id)
                    .map_or(100, |t| i64::from(t.encounter_rate).clamp(0, 0xFFFF))
            })
            .collect();
        let factor: Vec<i64> = rate.iter().map(|&r| encounters::factor(r)).collect();
        out.words("terrain_encounter_rate", rate);
        out.words("terrain_encounter_factor", factor);
        // And how much of a character standing on it is half hidden, its
        // `bush_depth`: 0 none, 1 a third, 2 half, 3 all. See `bush_oam` in
        // runtime/terrain_steps.s.
        let bush: Vec<i64> = (0..=top)
            .map(|id| {
                db.terrains
                    .get(&id)
                    .map_or(0, |t| i64::from(t.bush_depth.to_i32()).clamp(0, 3))
            })
            .collect();
        out.bytes("terrain_bush", bush);
        // The skill a special item casts from the items screen, by its RM2k
        // number, 0 for none: the battle stage's `item_map_skill`.
        let map_skills: Vec<i64> = self
            .model
            .item_map_skill
            .iter()
            .map(|&h| h.into())
            .collect();
        if map_skills.len() != items.len() {
            return Err(Bad::answer(
                "the battle's `item_map_skill` and the items are not the same list",
            ));
        }
        // A special item whose skill is a switch one goes down the switch
        // items' path on the map —the screens stage gives it no actor
        // choice—, so its switch is the skill's: `Scene_Item` turns on
        // `skill->switch_id` and spends the item, as for a switch item.
        let switch_of = |n: i64, h: i64| -> Result<i64> {
            let own = item(n)?.switch_id.into();
            Ok(match db.skills.get(&(h as i32)) {
                Some(s) if s.r#type == ditto::schema::SkillType::Switch => s.switch_id.into(),
                _ => own,
            })
        };
        out.words(
            "item_switch",
            items
                .iter()
                .zip(&map_skills)
                .map(|(&n, &h)| switch_of(n, h))
                .collect::<Result<Vec<_>>>()?,
        );
        // What each item does in a battle: whether it goes in the list
        // —the battle stage's rule— and how much it heals.
        let item_battle: Vec<i64> = self.model.item_battle.iter().map(|&b| b.into()).collect();
        out.bytes("item_battle", item_battle);
        // The skill a special item casts, as its place in the cartridge's
        // skill rows —`skill_*`—, or $FF for every other item: see
        // `ba_items_list` in battle_items.s. The model puts that skill in
        // `skills`.
        let rom_skills: Vec<i64> = self.model.skills.iter().map(|&h| h.into()).collect();
        let place_of = |h: i64, where_: &str| -> Result<i64> {
            if h == 0 {
                return Ok(0xFF);
            }
            Ok(rom_skills.iter().position(|&s| s == h).ok_or_else(|| {
                Bad::answer(format!(
                    "an item casts skill {h}{where_}, which the cartridge does not carry"
                ))
            })? as i64)
        };
        let item_skill = self
            .model
            .item_skill
            .iter()
            .map(|&h| place_of(h.into(), ""))
            .collect::<Result<Vec<_>>>()?;
        if item_skill.len() != items.len() {
            return Err(Bad::answer(
                "the battle's `item_skill` and the items are not the same list",
            ));
        }
        out.bytes("item_skill", item_skill);
        // And the one it casts from the items screen, the same way: see
        // `item_cast_use` in item_skills.s.
        let item_map_skill = map_skills
            .iter()
            .map(|&h| place_of(h, " on the map"))
            .collect::<Result<Vec<_>>>()?;
        out.bytes("item_map_skill", item_map_skill);
        out.words("ba_item_desc", x.item_desc_battle.iter().copied());
        let per_item = |f: &dyn Fn(&ditto::schema::Item) -> i64| -> Result<Vec<i64>> {
            items.iter().map(|&n| item(n).map(f)).collect()
        };
        out.bytes("item_heal_rate", per_item(&|i| i.recover_hp_rate.into())?);
        out.words(
            "item_heal_hp",
            per_item(&|i| i64::from(i.recover_hp).min(0xFFFF))?,
        );
        out.bytes(
            "item_heal_sp_rate",
            per_item(&|i| i.recover_sp_rate.into())?,
        );
        out.words(
            "item_heal_sp",
            per_item(&|i| i64::from(i.recover_sp).min(0xFFFF))?,
        );
        // The `MED_*` bits of the runtime. A material is only what it is
        // —the editor keeps the fields of the type it had before, and RM2k
        // reads none of them for one—.
        out.bytes(
            "item_medicine",
            per_item(&|i| {
                if i.r#type.to_i32() == rm2k_snes_battle::db::ITEM_MATERIAL {
                    return 8;
                }
                i64::from(i.ko_only)
                    | if i.state_set.first() == Some(&true) {
                        2
                    } else {
                        0
                    }
            })?,
        );
        // How many uses spend one of the item, `uses`, which the runtime
        // counts per item in `FAR_ITEM_USAGE` —`item_spend`—: The Book of
        // Three's bags of five shells. Zero is never spent, and so are the
        // normal items and the equipment, whatever their `uses` says:
        // `Game_Party::ConsumeItemUse` returns before looking at it for
        // them. The editor stops at 99, so it is a byte.
        out.bytes(
            "item_uses",
            per_item(&|i| {
                if i.r#type.to_i32() < rm2k_snes_battle::db::ITEM_MEDICINE {
                    0
                } else {
                    i64::from(i.uses).clamp(0, 255)
                }
            })?,
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
                up.push(if material {
                    i64::from(points) & 0xFFFF
                } else {
                    0
                });
            }
        }
        out.words("item_up", up);
        // The four text tables outside bank 0, like the ones above.
        for (field, prefix) in [("lo", "<"), ("hi", ">"), ("bk", "^")] {
            let entries = texts
                .offsets
                .iter()
                .map(|(ofs, _)| format!("{prefix}(item_texts + {ofs})"))
                .collect();
            out.bytes(format!("item_txt_{field}"), or_zero(entries));
        }
        out.bytes("item_txt_n", texts.offsets.iter().map(|(_, n)| *n));
        // --- the equipment: per item its type, what it adds and who can
        // equip it; per actor its parameters and initial equipment.
        let n_actors = db
            .actors
            .keys()
            .copied()
            .max()
            .map_or(0, |m| i64::from(m) + 1);
        let pos = |row: i64, col: i64| row * 64 + col * 2;
        out.bytes("item_type", per_item(&|i| i.r#type.to_i32().into())?);
        let mut points = Vec::new();
        for &n in items {
            points.extend(rules::points(item(n)?).map(|p| p & 0xFFFF));
        }
        out.words("item_points", points);
        out.bytes(
            "item_sp",
            per_item(&|i| {
                if i.r#type.to_i32() == rm2k_snes_battle::db::ITEM_WEAPON {
                    i.sp_cost.into()
                } else {
                    0
                }
            })?,
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
        out.bytes("item_actors", equippable);
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
        out.words("actor_params", params);
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
        out.bytes("item_crit_k", per_item(&|i| column(crit_bonus(i)))?);
        let row = |a: i64| owns.iter().position(|&o| o == own(a)).unwrap_or(0) * bonuses.len();
        out.words("actor_crit_row", (0..n_actors).map(|a| row(a) as i64));
        let mut table = Vec::new();
        for &o in &owns {
            for &b in &bonuses {
                table.push(rules::critical_percent(o, b).clamp(0, 255));
            }
        }
        out.bytes("crit_table", table);
        let mut initial = Vec::new();
        for a in 0..n_actors {
            match actor(a) {
                Some(x) => initial.extend(rules::initial_equipment(x).into_iter().map(i64::from)),
                None => initial.extend([0; EQUIPMENT_SLOTS]),
            }
        }
        out.words("equipment_initial", initial);
        out.push_str("\n.segment \"TABLES\"\n");
        out.words_unplaced(
            "actor_txt",
            hex4((0..n_actors).map(|a| x.actor_text.get(&a).copied().unwrap_or(0xFFFF))),
        );
        // And each rename's, which `actor_name_txt` takes instead when the
        // actor carries it: see the runtime's `actor_names.s`.
        out.words_unplaced("name_txt", hex4(x.name_text.iter().copied()));
        let eq_params: Vec<i64> = list(t.v("EQ_PARAMS"))?
            .iter()
            .map(|p| {
                let p = ints(p)?;
                Ok(pos(p[0], p[1]))
            })
            .collect::<Result<_>>()?;
        out.words_unplaced("eq_param_pos", eq_params);
        out.push_str(".segment \"RODATA\"\n");
        out.words("item_price", per_item(&|i| i.price.into())?);
        out.push_str(".segment \"TABLES\"\n");
        out.push_str(&format!(
            "TI_TEXT           = {}\nTI_TEXT_HAVE      = {}\nTI_TEXT_CARRIED   = {}\nTI_TEXT_CURRENCY  = {}\n\
             TI_SECOND         = {}\nTI_MAIN_MSG_POS = {}\nTI_MSG_POS        = {}\nTI_COMMAND_POS0   = {}\n\
             TI_GOLD_POS       = {}\nTI_HAVE_POS       = {}\nTI_HAVE_NUM       = {}\nTI_CARRIED_POS    = {}\n\
             TI_CARRIED_NUM    = {}\nTI_LIST_POS0      = {}\nTI_LIST_ROWS_BUY = {}\nTI_LIST_ROWS_SALE = {}\n\
             TI_NAME           = {}\nTI_PRICE          = {}\nTI_COUNT_POS      = {}\nTI_COUNT_X_POS    = {}\n\
             TI_COUNT_NUM_POS = {}\nTI_TOTAL_POS      = {}\nTI_RED            = {}\n",
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
        out.push_str(&format!(
            "ACTORS_N          = {}\nSLOTS_EQUIPMENT   = {}\nEQ_TEXT_PARAM     = {}\nEQ_TEXT_SLOT      = {}\n\
             EQ_ACTOR_POS      = {}\nEQ_BAR_ROW0       = {}\nEQ_BORDER_TEXT    = {}\nEQ_BORDER_TEXT_N  = {}\n\
             EQ_PARAM_VALUE    = {}\nEQ_PARAM_ARROW    = {}\nEQ_SLOT_POS0      = {}\nEQ_SLOT_TERM      = {}\n\
             EQ_SLOT_NAME      = {}\nEQ_SLOT_WIDTH     = {}\nEQ_LIST_POS0      = {}\nEQ_LIST_ROWS      = {}\n\
             EQ_LIST_NAME      = {}\nSCR_TWO_POINTS    = {}\nSCR_DESC_POS      = {}\n",
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
        out.words("actor_hpmax", hp);
        let sp: Vec<i64> = (0..n_actors)
            .map(|a| Ok(param(a, "maxsp")? & 0xFFFF))
            .collect::<Result<_>>()?;
        out.words("actor_spmax", sp);
        // And each actor's starting level, one byte: what a `ControlVars`
        // asking for the level of an actor who never fights —no `FAR_EXP`
        // slot— answers. See `actor_stat_other` in the runtime.
        let levels: Vec<i64> = (0..n_actors)
            .map(|a| actor(a).map_or(1, rules::level_of))
            .collect();
        out.bytes("actor_level", levels);
        // `rm2k-snes-battle` leaves the segment in RODATA.
        out.push_str(&r.battle_tables.experience);
        self.skills_and_troops(out, texts, x, n_actors)
    }

    fn skills_and_troops(
        &self,
        out: &mut Inc,
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
        let per_skill = |f: &dyn Fn(&ditto::schema::Skill) -> i64| -> Result<Vec<i64>> {
            rom_skills.iter().map(|&h| skill(h).map(f)).collect()
        };
        let from = |m: &HashMap<i64, i64>| rom_skills.iter().map(|h| m[h]).collect::<Vec<_>>();
        // --- the skills, one row per skill the cartridge carries, outside
        // bank 0 and declared: the battle reads them with `lda f:`.
        out.words("skill_id", rom_skills.iter());
        out.words("skill_txt", from(&x.skill_text));
        out.words("skill_desc", from(&x.skill_desc_text));
        out.words("skill_msg1", from(&x.skill_msg1_text));
        out.words("skill_msg2", from(&x.skill_msg2_text));
        out.words("skill_power", per_skill(&|s| s.power.into())?);
        out.words("skill_switch", per_skill(&|s| s.switch_id.into())?);
        out.bytes("skill_sp", per_skill(&|s| s.sp_cost.into())?);
        out.bytes("skill_type", per_skill(&|s| s.r#type.to_i32().into())?);
        // 1 if the battle lets it be chosen, 0 if its list carries it grey
        // for everyone: `usable_in_battle`, a switch skill for the map.
        out.bytes(
            "skill_in_battle",
            per_skill(&|s| rm2k_snes_battle::rules::usable_in_battle(s).into())?,
        );
        out.bytes("skill_phys", per_skill(&|s| s.physical_rate.into())?);
        out.bytes("skill_mag", per_skill(&|s| s.magical_rate.into())?);
        out.bytes("skill_var", per_skill(&|s| s.variance.into())?);
        out.bytes("skill_hit", per_skill(&|s| s.hit.into())?);
        // Which failure it says when it did nothing, 0 to 3: `skill_failure_a`
        // to `_c` and `dodge`, the order of `RESULT_TERMS`. Since 2026-10-20.
        out.bytes(
            "skill_fail",
            per_skill(&|s| s.failure_message.clamp(0, 3).into())?,
        );
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
        out.bytes("skill_affects", hex2(affects));
        // Whether it shifts its target's rank in the attributes it carries,
        // `affect_attr_defence`: see `ba_attr_shift` in battle_attributes.s.
        // Without an attribute it has nothing to shift.
        out.bytes(
            "skill_shifts",
            per_skill(&|s| {
                i64::from(s.affect_attr_defence && s.attribute_effects.iter().any(|&a| a))
            })?,
        );
        out.bytes("skill_scope", per_skill(&|s| s.scope.to_i32().into())?);
        // What the skills screen needs of each one, from the screens stage:
        // the description's two lines as slices of `skill_desc` —the first's
        // length, and where the second starts and its length— and whether
        // the map can use it. See `skills.rs` in `rm2k-snes-screens`.
        let of = |h: i64| {
            i32::try_from(h)
                .ok()
                .and_then(|h| self.screens.skills.get(&h))
                .ok_or_else(|| Bad::answer(format!("the screens have nothing of skill {h}")))
        };
        let mut lines: [Vec<i64>; 3] = Default::default();
        let mut field = Vec::new();
        // And the name the actor choice writes on its line on top, for the
        // ones the map can use: `TARGET_NAME_WIDTH` letters each, in
        // `skill_target_names`, and per skill where its name is there —$FF
        // for the others—. Its own copy, as a medicine's: see
        // `target_name` in the screens stage's `skills.rs`.
        let shown = ScreenGlyphs::of(self.screens);
        let mut target_index = Vec::new();
        let mut target_names: Vec<u8> = Vec::new();
        for &h in rom_skills {
            let row = of(h)?;
            for (v, &n) in lines.iter_mut().zip(&row.lines) {
                v.push(n as i64);
            }
            // Bit 0, the map can use it; bit 1, it raises the fallen, which
            // only a skill the map can use is asked.
            let on_map = row.field;
            field.push(i64::from(on_map) | i64::from(on_map && row.revives) << 1);
            if on_map {
                let width = self.t.n("TARGET_NAME_WIDTH") as usize;
                let k = target_names.len() / width;
                if k >= 0xFF {
                    return Err(Bad::answer(
                        "the skills the map can use don't fit in `skill_target_name`",
                    ));
                }
                target_index.push(k as i64);
                target_names.extend(target_name_bytes(&row.target_name, width, &shown)?);
            } else {
                target_index.push(0xFF);
            }
        }
        out.bytes("skill_line1_n", lines[0].iter());
        out.bytes("skill_line2_at", lines[1].iter());
        out.bytes("skill_line2_n", lines[2].iter());
        out.bytes("skill_on_map", field);
        out.bytes("skill_target_name", target_index);
        if target_names.is_empty() {
            target_names.push(b' '); // a label over nothing would be no `.block`
        }
        out.block("skill_target_names", &target_names);
        self.states(out, &x, n_actors)?;
        // The parallel common events, in the order of their numbers, which
        // is the order RM2k runs them in: see `compar_tick` in
        // `common_events.s`. One entry of `COMPAR_ENTRY` bytes each: the
        // switch's byte and its mask —$00 for one without a switch, which
        // runs always—, whether it is pure, and where its body starts.
        let parallel = &r.parallel_common;
        out.push_str(&format!("COMPAR_N = {}\n", parallel.len()));
        out.push_str(&format!(
            ".block {}\ncompar_table:\n",
            6 * parallel.len().max(1)
        ));
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
                "    .byte {byte}, ${mask:02X}, {}\n",
                u8::from(*pure)
            ));
            out.far(&format!("common_parallel_{n}"));
        }
        for (_, n, _, code) in parallel {
            out.block(format!("common_parallel_{n}"), &crate::hex::decode(code)?);
        }
        // The shared common event bodies, by index, and the automatic ones:
        // see `common_events.s`. A cartridge without them carries the
        // labels anyway, with a dummy entry, so the runtime assembles.
        let empty = crate::request::Commons {
            bodies: vec![],
            autostart: vec![],
            depth: Some(0),
            copies: Default::default(),
        };
        let commons = r.commons.as_ref().unwrap_or(&empty);
        let labels: Vec<String> = commons
            .bodies
            .iter()
            .map(|(n, _)| format!("common_body_{n}"))
            .collect();
        // A loop of calls has no deepest chain: the ROM's stack skips what
        // does not fit.
        out.push_str(&format!("COMMON_DEPTH = {}\n", commons.depth.unwrap_or(0)));
        out.words(
            "common_body_lo",
            labels.iter().map(|l| format!(".loword({l})")),
        );
        out.words("common_body_bank", labels.iter().map(|l| format!("^{l}")));
        out.push_str(&format!("COMAUTO_N = {}\n", commons.autostart.len()));
        out.words("comauto_byte", commons.autostart.iter().map(|a| a.0 >> 3));
        out.bytes(
            "comauto_mask",
            or_zero(hex2(commons.autostart.iter().map(|a| 1 << (a.0 & 7)))),
        );
        out.bytes(
            "comauto_body",
            or_zero(decimal(commons.autostart.iter().map(|a| a.1))),
        );
        // Which automatic ones have copies in the maps, and which maps carry
        // them, a bit per map index: see `switch_of` in `common_events.s`.
        let copied = commons.autostart.iter().map(|a| {
            u8::from(
                commons
                    .bodies
                    .get(a.1 as usize)
                    .is_some_and(|(n, _)| commons.copies.commons.contains(n)),
            )
        });
        out.bytes("comauto_copied", or_zero(decimal(copied)));
        let mut bitmap = vec![0u8; r.maps.len().div_ceil(8).max(1)];
        for &m in &commons.copies.maps {
            let m = usize::try_from(m)
                .ok()
                .filter(|&m| m < r.maps.len())
                .ok_or_else(|| {
                    Bad::answer(format!(
                        "a copy of a common event on map index {m}, past the cartridge's maps"
                    ))
                })?;
            bitmap[m / 8] |= 1 << (m % 8);
        }
        out.bytes("comcopy_maps", bitmap);
        for ((_, code), label) in commons.bodies.iter().zip(&labels) {
            out.block(label, &crate::hex::decode(code)?);
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
            save_signature(
                &variables,
                &pairs,
                &r.battle_tables.slots,
                n_actors,
                switch_bytes(r.switch_top)?
            )
        ));
        out.words("skill_pair_init", skill_pair_start);
        out.bytes("skill_pair_n", skill_pair_n);
        let actors: BTreeSet<i64> = r.actors.iter().copied().collect();
        out.bytes(
            "skill_pair_k",
            pairs.iter().map(|&(a, h, _)| {
                if actors.contains(&a) {
                    skill_place.get(&h).map_or(0xFF, |&k| k as i64)
                } else {
                    0xFF
                }
            }),
        );
        out.bytes("skill_initial", hex2(bits));
        // At which level the learning table teaches each pair, or 0.
        let pair_levels = &self.model.pair_levels;
        out.bytes("skill_pair_level", pair_levels.iter());
        // And the name the victory tells it by, or $FFFF.
        out.words(
            "skill_pair_learns_txt",
            hex4(pairs.iter().zip(pair_levels).map(|(&(a, h, _), &level)| {
                match x.whole_skill_text.get(&h) {
                    Some(&k) if actors.contains(&a) && level > 0 => k,
                    _ => 0xFFFF,
                }
            })),
        );
        // 254 and not 256: $FF is the attack and $FE "none left".
        if rom_skills.len() > 254 {
            return Err(Bad::answer(format!(
                "the cartridge's skills are {} and `skill_pair_k` is one byte",
                rom_skills.len()
            )));
        }
        // Five words per actor, its commands' texts —`ba_commands` in the
        // runtime's battle_skills.s—; `$FFFF` for an actor the cartridge
        // does not carry.
        out.words(
            "actor_command_txt",
            hex4((0..n_actors).flat_map(|a| match x.command_text.get(&a) {
                Some(row) => row.clone(),
                None => vec![0xFFFF; BA_COMMAND_TERMS.len()],
            })),
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
        out.words("troop_id", used.iter());
        let model_troops = &self.model.troops;
        let answered: Vec<i64> = model_troops.iter().map(|t| t.id.into()).collect();
        if answered != used {
            return Err(Bad::answer(format!(
                "the battle stage answered for troops {answered:?} and the cartridge carries {used:?}"
            )));
        }
        for (field, what) in [("exp", "experience"), ("gold", "gold")] {
            let values: Vec<i64> = model_troops
                .iter()
                .map(|t| if field == "exp" { t.exp } else { t.gold })
                .collect();
            for (n, v) in used.iter().zip(&values) {
                if *v > 0xFFFF {
                    return Err(Bad::answer(format!(
                        "troop {n} gives {v} {what} and the ROM adds it in sixteen bits"
                    )));
                }
            }
            out.words(format!("troop_{field}"), values);
        }
        out.words("troop_init", starts);
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
        out.bytes("troop_hidden", hex2(hidden));
        out.bytes("troop_n", counts);
        out.bytes("troop_member", members.iter());
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
    /// **The ones a skill can shift go first** —those a carried skill with
    /// `affect_attr_defence` carries, `ATTR_SHIFT_N` of them, still in
    /// database order among themselves—: the battle keeps a shift per
    /// combatant only for those, in `ba_attr_shifts`, and an attribute is
    /// one of them if its number is below `ATTR_SHIFT_N`. The order changes
    /// nothing else: of each kind the best rate counts, whatever the order.
    ///
    /// * `attr_rate`: a word per attribute and rank, `A` to `E`. A negative
    ///   rate counts for nothing in RM2k 2000, and goes as -1.
    /// * `attr_magic`: whether each one is magical.
    /// * `attr_sets`: rows of `ATTR_N` bytes, 1 where the set has the
    ///   attribute; row 0 is the empty set, and equal sets share a row.
    ///   `item_attr` and `skill_attr` give each item and skill its row, as
    ///   the byte where it starts.
    /// * `skill_weapon`: per skill, the row of the attributes it asks a
    ///   weapon for —its physical ones, unless it has
    ///   `affect_attr_defence`: `weapon_attributes_asked` in `rm2k-rules`, through
    ///   `rm2k-snes-battle`'s—;
    ///   row 0, the empty set, asks for nothing. `ba_weapons_allow` greys
    ///   it by them, in battle and in the menu.
    /// * `attr_ranks`: rows of `ATTR_N` ranks, one per actor —its own,
    ///   before its armor— and then one per enemy, in `enemy_*` order: the
    ///   enemy `k`'s row is `ACTORS_N + k`.
    fn attributes(&self, out: &mut Inc, x: &ItemTexts, n_actors: i64) -> Result<()> {
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
        let mut shifting = BTreeSet::new();
        for &h in &x.rom_skills {
            let s = db.skill(h as i32).map_err(bad)?;
            if s.affect_attr_defence {
                shifting.extend(
                    s.attribute_effects
                        .iter()
                        .enumerate()
                        .filter(|(_, &has)| has)
                        .map(|(k, _)| k),
                );
            }
        }
        let (first, rest): (Vec<usize>, Vec<usize>) =
            used.into_iter().partition(|k| shifting.contains(k));
        let n_shift = first.len();
        let used: Vec<usize> = first.into_iter().chain(rest).collect();
        let n = used.len();
        if n > 255 {
            return Err(Bad::answer(format!(
                "{n} attributes, and `ATTR_N` multiplies as a byte"
            )));
        }
        out.push_str(&format!("ATTR_N = {n}\nATTR_SHIFT_N = {n_shift}\n"));
        let attrs: Vec<&ditto::schema::Attribute> = db.attributes.values().collect();
        let mut rates = Vec::new();
        for &k in &used {
            for rank in 0..5 {
                let rate = at::rate_of(attrs[k], rank);
                if rate > 0x7FFF {
                    return Err(Bad::answer(format!(
                        "attribute {}: a rate of {rate}",
                        k + 1
                    )));
                }
                rates.push(rate.max(-1) & 0xFFFF);
            }
        }
        out.words("attr_rate", rates);
        out.bytes(
            "attr_magic",
            used.iter().map(|&k| i64::from(!at::physical(attrs[k]))),
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
        // A subset of the skill's own, so its attributes are all among
        // `used`.
        let weapon_rows: Vec<usize> = x
            .rom_skills
            .iter()
            .map(|&h| {
                let skill = db.skill(h as i32).map_err(bad)?;
                Ok(place(&rm2k_snes_battle::rules::weapon_attributes_asked(
                    db, skill,
                )))
            })
            .collect::<Result<_>>()?;
        if rows.len() > 0x10000 {
            return Err(Bad::answer("the attribute sets don't fit in a bank"));
        }
        out.bytes("attr_sets", rows);
        out.words("item_attr", item_rows);
        out.words("skill_attr", skill_rows);
        out.words("skill_weapon", weapon_rows);
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
        out.bytes("attr_ranks", ranks);
        Ok(())
    }

    fn troop_pages(&self, out: &mut Inc, used: &[i64]) -> Result<()> {
        // Per troop, where its pages start and how many there are; per page,
        // its trigger and where its code is inside `troop_code`. All in
        // RODATA, each table in its `.block`.
        let pt = self.r.troop_pages.as_ref();
        let per_troop: HashMap<i64, Vec<([i64; 13], usize)>> = pt
            .map(|pt| &pt.per_troop[..])
            .unwrap_or_default()
            .iter()
            .map(|(number, pages)| {
                let theirs = pages
                    .iter()
                    .map(|(trigger, offset, _)| (trigger.map(i64::from), *offset))
                    .collect();
                (i64::from(*number), theirs)
            })
            .collect();
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
        out.words("troop_page_init", page_start);
        out.bytes("troop_page_n", page_n);
        // A trigger: flags, switch_a, switch_b, slot, value, and the rest.
        out.bytes("tpage_flags", hex2(entries.iter().map(|(d, _)| d[0])));
        out.words("tpage_sw_a", entries.iter().map(|(d, _)| d[1]));
        out.words(
            "tpage_code",
            entries
                .iter()
                .map(|(_, ofs)| format!(".loword(troop_code + {ofs})")),
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
                entries.iter().map(|(d, _)| d[field] & 0xFFFF).collect()
            } else {
                Vec::new()
            };
            out.words(name, values);
        }
        // Without pages, no code, and the message block's one byte, its end.
        let (code, messages) = pt.map_or((&[][..], &[0][..]), |pt| {
            (&pt.code.0[..], &pt.messages.0[..])
        });
        out.block("troop_code", if code.is_empty() { &[0] } else { code });
        out.block("messages_troop", messages);
        Ok(())
    }

    fn enemies_and_scene(
        &self,
        out: &mut Inc,
        x: &ItemTexts,
        used: &[i64],
        n_actors: i64,
        bs: &Geometry,
    ) -> Result<()> {
        let (r, db) = (self.r, self.db);
        let enemy = |e: i64| db.enemy(e as i32).map_err(bad);
        let rom_enemies = &x.rom_enemies;
        let per_enemy = |f: &dyn Fn(&ditto::schema::Enemy) -> i64| -> Result<Vec<i64>> {
            rom_enemies.iter().map(|&e| enemy(e).map(f)).collect()
        };
        out.words("enemy_hp", per_enemy(&|e| e.max_hp.into())?);
        out.words("enemy_atk", per_enemy(&|e| e.attack.into())?);
        out.words("enemy_def", per_enemy(&|e| e.defense.into())?);
        out.words("enemy_agi", per_enemy(&|e| e.agility.into())?);
        out.words("enemy_spi", per_enemy(&|e| e.spirit.into())?);
        out.words("enemy_sp", per_enemy(&|e| e.max_sp.into())?);
        // `Game_Enemy::GetHitChance`: 70 if it misses, 90 if not.
        let hit = |e: &ditto::schema::Enemy| if e.miss { 70 } else { 90 };
        out.bytes("enemy_hit", per_enemy(&|e| hit(e))?);
        // The critical hit as a whole percentage: `1 / chance` times a
        // hundred, in floating point as RM2k —see `critical_percent`—.
        out.bytes(
            "enemy_crit",
            per_enemy(&|e| {
                rules::critical_percent(e.critical_hit.then_some(e.critical_hit_chance), 0)
                    .clamp(0, 255)
            })?,
        );
        out.words("enemy_txt", rom_enemies.iter().map(|e| x.enemy_text[e]));
        out.words("enemy_exp", per_enemy(&|e| e.exp.into())?);
        out.words("enemy_gold", per_enemy(&|e| e.gold.into())?);
        let known: BTreeSet<i64> = r.items.iter().copied().collect();
        for &e in rom_enemies {
            let drop = i64::from(enemy(e)?.drop_id);
            if drop != 0 && !known.contains(&drop) {
                return Err(Bad::answer(format!(
                    "enemy {e} drops item {drop} and the cartridge doesn't carry it"
                )));
            }
        }
        out.words("enemy_drop", per_enemy(&|e| e.drop_id.into())?);
        out.bytes("enemy_drop_pct", per_enemy(&|e| e.drop_prob.into())?);
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
            let theirs = by_number(x.actions, e, "enemy")?;
            eacc_n.push(theirs.len() as i64);
            for &(rating, skill, effective) in theirs {
                eacc_skill.push(match skill {
                    None => 0xFF,
                    Some(h) => *skill_place
                        .get(&h.into())
                        .ok_or_else(|| Bad::answer(format!("skill {h} is not the battle's")))?
                        as i64,
                });
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
        out.words("enemy_acc_init", eacc_start);
        out.bytes("enemy_acc_n", eacc_n);
        out.bytes("eacc_skill", eacc_skill);
        out.bytes("eacc_weight", eacc_weight);
        self.attributes(out, x, n_actors)?;
        // The battle scene: the backdrops and the battlers, in the order of
        // `troop_id`.
        out.push_str(&crate::scene::scenes_asm(
            &r.scene,
            used,
            r.rom.msu != MsuData::Optional,
        )?);
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
        out.push_str(&format!(
            "TROOPS_N          = {}\nBATTLE_SEED       = ${:04X}\nBA_TXT_BASE       = {}\n\
             TROOP_PAGE_MAX    = {}\nTPAGE_SWITCH_A    = ${:02X}\nTPAGE_SWITCH_B    = ${:02X}\nTPAGE_VARIABLE    = ${:02X}\n\
             TPAGE_TURN        = ${:02X}\nTPAGE_ENEMY       = ${:02X}\nTPAGE_ACTOR       = ${:02X}\n\
             TPAGE_WITH_HEADER = ${:02X}\nTPAGE_HEADER      = {}\n",
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
        let audio = r.battle_audio.as_ref();
        let song = |which: fn(&BattleAudio) -> usize| audio.map_or(0xFF, which);
        out.push_str(&format!(
            "BA_SONG           = ${:02X}\nBA_SONG_END       = ${:02X}\nBA_PACKAGE        = ${:04X}\n",
            song(|a| a.battle_music),
            song(|a| a.battle_end_music),
            if audio.is_some() {
                r.maps.len() as i64
            } else {
                0xFFFF
            }
        ));
        // And the levels the two songs start a game with —gains, step and
        // fade-in, as `OP_BGM` carries them—, which a `ChangeSystemBGM`
        // changes: see `bgm_level_reset` in runtime/bgm_level.s. A request
        // without them is the song as written.
        let levels: [(fn(&BattleAudio) -> [u8; 6], &str); 2] = [
            (|a| a.battle_music_level, "BA_SONG"),
            (|a| a.battle_end_music_level, "BA_SONG_END"),
        ];
        for (which, prefix) in levels {
            let level = audio.map_or([128, 128, 0, 1, 0, 0], which);
            let word = |i: usize| u16::from(level[i]) | u16::from(level[i + 1]) << 8;
            out.push_str(&format!(
                "{:<18}= ${:04X}\n{:<18}= ${:04X}\n{:<18}= ${:04X}\n",
                format!("{prefix}_GAINS"),
                word(0),
                format!("{prefix}_STEP"),
                word(2),
                format!("{prefix}_FADE"),
                word(4)
            ));
        }
        let effects: [(fn(&BattleAudio) -> usize, &str); 7] = [
            (|a| a.dodge_se, "BA_SE_MISS"),
            (|a| a.enemy_attack_se, "BA_SE_ATTACK"),
            (|a| a.enemy_damaged_se, "BA_SE_DAMAGE_ENEMY"),
            (|a| a.actor_damaged_se, "BA_SE_DAMAGE_ACTOR"),
            (|a| a.enemy_death_se, "BA_SE_DEATH"),
            (|a| a.escape_se, "BA_SE_FLEE"),
            (|a| a.item_se, "BA_SE_ITEM"),
        ];
        for (which, constant) in effects {
            out.push_str(&format!(
                "{:<18}= ${:04X}\n",
                constant,
                audio.map_or(0xFFFF, which)
            ));
        }
        out.push_str(&format!(
            "BA_TXT_VICTORY2   = {}\nBA_VIC_FINISHED_N = {}\n",
            x.victory2_text, x.victory_lines
        ));
        for (k, (name, _)) in BATTLE_TERMS.iter().enumerate() {
            out.push_str(&format!(
                "BA_TXT_{:<11}= BA_TXT_BASE + {}\n",
                name.to_uppercase(),
                k
            ));
        }
        out.push_str(&format!("BA_TXT_REVIVED    = {}\n", x.revived_text));
        out.push_str(&format!("BA_TXT_DEAD       = {}\n", x.dead_text));
        let commands = list(bs.v("BA_COMMANDS"))?;
        out.push_str(&format!("BA_COMMANDS_N     = {}\n", commands.len()));
        out.push_str(&format!(
            "BA_ITEM_POS0      = {}\nBA_ITEM_ROWS      = {}\nBA_ITEM_NAME_WIDTH = {}\nBA_ITEM_COUNT_DX  = {}\n",
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
        out.push_str(&format!(
            "SKILLS_N          = {}\nBA_SKILL_DESC_POS = {}\nBA_SKILL_POS0     = {}\nBA_SKILL_ROWS     = {}\n\
             BA_SKILL_COLUMNS  = {}\nBA_SKILL_COLUMN_DX = {}\nBA_SKILL_NAME_DX  = {}\nBA_SKILL_NAME_WIDTH = {}\n\
             BA_SKILL_DASH_DX  = {}\nBA_SKILL_COST_DX  = {}\nBA_SKILL_COST_DIGITS = {}\n",
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
        if commands.iter().map(text).collect::<Result<Vec<_>>>()? != BA_COMMAND_TERMS {
            return Err(Bad::answer(format!(
                "the battle's commands are {commands:?} and `actor_command_txt` has {BA_COMMAND_TERMS:?}"
            )));
        }
        let undone: BTreeSet<i64> = ints(bs.v("BA_COMMAND_UNDONE"))?.into_iter().collect();
        out.bytes(
            "ba_command_gray",
            (0..commands.len() as i64).map(|k| i64::from(undone.contains(&k))),
        );
        out.push_str(".segment \"TABLES\"\n");
        self.tail(out)
    }

    fn tail(&self, out: &mut Inc) -> Result<()> {
        let r = self.r;
        // `font_color` in bank 0: the console reads it with
        // `lda font_color, y`, which addresses the data bank.
        out.line(&unplaced("font_color", &self.screens.window.system.color));
        // And the entries the text takes, which a cell with letters over
        // the layer above finds in the text's copy of the layer's palette:
        // see `layer_text`.
        let mask = crate::layer_text::Text::of(self.screens).map_or(0, |t| t.mask());
        out.push_str(&format!("LAYER_TEXT_ENTRIES = ${mask:04X}\n\n"));
        // A game can start with the party empty, as RM2k allows: the label
        // stays, with no bytes —`.byte` with nothing after it does not
        // assemble—, and `boot` copies none.
        if r.party.is_empty() {
            out.push_str("party_initial:                ; the party starts empty\n\n");
        } else {
            out.bytes_unplaced("party_initial", &r.party);
            out.push('\n');
        }
        out.line(&sine_table());
        // How many frames a character stays still after a step and after a
        // turn, per route frequency: RM2k's stop counters. 0 does not
        // compile, nor 1 in a route; 1 is there for a page that walks by a
        // movement type, with its 256 frames after a step held at the
        // byte's 255 —see `route::own` in the compiler—.
        let per_frequency = |f: fn(u32) -> u32| {
            (0..=ROUTE_FREQUENCY).map(move |q| if q >= 1 { f(q).min(255) } else { 0 })
        };
        out.bytes_unplaced("route_after_step", per_frequency(wait_after_step));
        out.bytes_unplaced("route_after_turn", per_frequency(wait_after_turn));
        out.push('\n');
        Ok(())
    }
}

/// What used to be appended after the `.inc`: which entries of its palette
/// the timer's digits use, per map, and where the harness writes the case
/// number.
fn timer_and_case(out: &mut Inc, r: &Emit) {
    out.push_str("\n.segment \"RODATA\"\n");
    out.words(
        "timer_mask",
        hex4(
            r.maps
                .iter()
                .map(|m| m.sprite.as_ref().map_or(0, |s| s.timer_mask)),
        ),
    );
    // The sandstorm's grains, four bytes per map —first tile, palette and
    // first entry—, only in a cartridge that carries them: the runtime
    // assembles the sandstorm only if this table is there. See
    // `sandstorm.s`.
    if r.maps
        .iter()
        .any(|m| m.sprite.as_ref().is_some_and(|s| s.sand.is_some()))
    {
        let grains = r.maps.iter().flat_map(|m| {
            let (base, palette, first) =
                m.sprite.as_ref().and_then(|s| s.sand).unwrap_or((0, 0, 0));
            [base, palette | first << 8]
        });
        out.words("sand_table", hex4(grains));
    }
    // And what each map forbids, one byte per map: `map_access_enter`
    // writes it over the permissions when the map is entered.
    out.bytes(
        "map_access",
        or_zero(hex2(r.maps.iter().map(|m| i64::from(m.access)))),
    );
    if let Some(slot) = r.case_slot {
        out.push_str(&format!("\nCASE_SLOT = {slot}\n"));
    }
    if let Some(switch) = r.test_switch {
        out.push_str(&format!("\nTEST_SWITCH = {switch}\n"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A common picture's entry goes after the maps' in `picture_data`, as
    /// theirs, but with the base tile at 0, its palette counted from its
    /// set's first, and the set and $80 in bytes 12 and 13: the console adds
    /// the loaded map's base and palette, and tells it from a map's by the
    /// $80. See `runtime/picture_common.s`.
    #[test]
    fn a_common_picture_s_entry_says_its_set() {
        let image = |palette_index| crate::request::PictureImage {
            half: [4, 3],
            objects: vec![[0, 0, 0x8000], [8, 0, 0x8001]],
            palette: vec![[31, 0, 0]],
            palette_index,
            behind_map: false,
        };
        let set = |name: &str, images| crate::request::CommonSet {
            name: name.into(),
            tiles: 2,
            cells: vec![],
            palettes: 2,
            images,
        };
        let sets = [set("a", vec![image(0)]), set("b", vec![image(1), image(1)])];
        let mut data = vec![0u8; 5];
        let first = common_entries(&sets, &mut data).unwrap();
        assert_eq!(first, 5);
        let entry = |k: usize| &data[first + k * PICTURE_ENTRY..first + (k + 1) * PICTURE_ENTRY];
        assert_eq!(entry(0)[..6], [4, 0, 3, 0, 2, 0]);
        assert_eq!(entry(0)[10..14], [0, 0, 0, 0x80]);
        assert_eq!(entry(1)[5], 1);
        assert_eq!(entry(1)[10..14], [0, 0, 1, 0x80]);
        // The two of set b share their colours.
        assert_eq!(entry(1)[8..10], entry(2)[8..10]);
        // Each one's objects where the entry says.
        let objects = u16::from_le_bytes([entry(1)[6], entry(1)[7]]) as usize;
        assert_eq!(data[objects..objects + 8], [0, 0, 0, 0x80, 8, 0, 1, 0x80]);
    }

    /// The console's 4-bit tile: planes 0 and 1 a row at a time, then 2
    /// and 3, the leftmost pixel in bit 7.
    #[test]
    fn a_cell_packs_as_a_four_bit_tile() {
        let mut cell = vec![0u8; 64];
        cell[0] = 0xF;
        cell[9] = 0x5;
        let tile = pack4(&cell);
        assert_eq!(tile[0..4], [0x80, 0x80, 0x40, 0x00]);
        assert_eq!(tile[16..20], [0x80, 0x80, 0x40, 0x00]);
        assert!(tile[4..16].iter().chain(&tile[20..]).all(|&b| b == 0));
    }

    #[test]
    fn the_crc_is_zlib_s() {
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
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

    /// Every term the battle and the skills screen name is one of the
    /// database's, whether the game left it at its default or wrote its
    /// own; and a name that is no term is refused.
    #[test]
    fn every_term_the_tables_name_is_the_databases() {
        let names = BATTLE_TERMS
            .iter()
            .chain(RESULT_TERMS.iter())
            .map(|(_, liblcf)| *liblcf)
            .chain(["lvl_short"]);
        let mut db = Db::default();
        for name in names.clone() {
            term(&db, name).unwrap_or_else(|_| panic!("{name} at its default"));
        }
        db.terms.gold_recieved_a = "Found ".to_string();
        db.terms.lvl_short = "Nv".to_string();
        assert_eq!(term(&db, "gold_recieved_a").unwrap(), "Found ");
        assert_eq!(term(&db, "lvl_short").unwrap(), "Nv");
        assert!(term(&db, "gold_received_a").is_err());
        let dump =
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../battle/tests/game/dump");
        let game = Db::from_dump(&dump, true).unwrap();
        for name in names {
            term(&game, name).unwrap_or_else(|_| panic!("{name} in the test game"));
        }
    }

    /// Zounds' terms, which taro saw as `Kazar 3'I?_???[?W…` in every
    /// battle until 2026-10-19: what a 2003 database holds in the terms its
    /// battle never writes gives way to the project's, or to the stand-in.
    #[test]
    fn a_2003_games_unshown_battle_terms_are_not_its_databases() {
        let mut db = Db::default();
        // `の攻撃！` in Shift-JIS, read as Windows-1252.
        db.terms.attacking = "\u{201a}\u{cc}\u{8d}U\u{152}\u{201a}\u{81}I".to_string();
        db.terms.victory = "\u{a1}Victoria!".to_string();
        let none = BTreeMap::new();
        let mut given = BTreeMap::new();
        given.insert("attacking".to_string(), " ataca.".to_string());
        // A 2000 game: its own, whatever they are.
        assert_eq!(
            battle_term(&none, &db, "attacking").unwrap(),
            db.terms.attacking
        );
        db.is_2003 = true;
        assert_eq!(battle_term(&none, &db, "attacking").unwrap(), " attacks!");
        assert_eq!(battle_term(&given, &db, "attacking").unwrap(), " ataca.");
        // One its battle writes stays the database's.
        assert_eq!(
            battle_term(&none, &db, "victory").unwrap(),
            "\u{a1}Victoria!"
        );
        for (name, stand_in) in UNSHOWN_IN_2003 {
            assert!(
                BATTLE_TERMS
                    .iter()
                    .chain(RESULT_TERMS.iter())
                    .any(|(_, l)| *l == name),
                "{name}"
            );
            assert!(stand_in.chars().all(|c| (' '..='~').contains(&c)), "{name}");
        }
    }

    /// Zounds' skills, `L?tigo de Seda` in the battle until 2026-11-22: a
    /// database text keeps its icon and stands its accents in.
    #[test]
    fn a_database_text_stands_its_accents_in_and_keeps_its_icons() {
        let glyphs = ScreenGlyphs::new(
            vec![rm2k_snes_text::exfont::icon_of_letter('L').unwrap()],
            Vec::new(),
            99,
        );
        let mut texts = Texts {
            data: Vec::new(),
            offsets: Vec::new(),
            first: 32,
            count: 95,
            glyphs: glyphs.clone(),
        };
        let k = texts.add(&db_text(&glyphs, "$LL\u{e1}tigo de Seda"));
        let bytes = text_bytes(&texts, k);
        let icon = ICON_CODE_FIRST as u8;
        assert_eq!(bytes[..2], [icon, icon + 1]);
        assert_eq!(&bytes[2..], b"Latigo de Seda");
    }

    fn text_bytes(texts: &Texts, k: i64) -> Vec<u8> {
        let (at, len) = texts.offsets[k as usize];
        texts.data[at..at + len].to_vec()
    }

    /// A letter the screens carry is its glyph plus 32, after the icons'
    /// halves; a name loses its icon and keeps its letter. Zounds' `á` and
    /// Unamë's `ë` since 2026-11-22.
    #[test]
    fn a_letter_the_screens_carry_is_its_glyph() {
        let icon = rm2k_snes_text::exfont::icon_of_letter('L').unwrap();
        let glyphs = ScreenGlyphs::new(vec![icon], vec!['\u{eb}', '\u{e1}'], 99);
        let mut texts = Texts {
            data: Vec::new(),
            offsets: Vec::new(),
            first: 32,
            count: 95,
            glyphs: glyphs.clone(),
        };
        let k = texts.add(&db_text(&glyphs, "$LL\u{e1}tigo"));
        let bytes = text_bytes(&texts, k);
        assert_eq!(bytes[2..4], [b'L', 32 + 99 + 1]);
        let k = texts.add(&plain(&glyphs, "$LUnam\u{eb}"));
        assert_eq!(text_bytes(&texts, k), [b'U', b'n', b'a', b'm', 32 + 99]);
        // And one it does not carry is its stand-in.
        let k = texts.add(&plain(&glyphs, "Ni\u{f1}o"));
        assert_eq!(text_bytes(&texts, k), b"Nino");
    }

    /// A screen's byte is its glyph plus 32, so the screens reach glyph
    /// 223 and no further: a letter the font carries past it is shown on
    /// them as its plain stand-in, and nothing wraps around to a low byte.
    #[test]
    fn the_screens_stop_at_glyph_223() {
        let letters = vec!['\u{e1}', '\u{e9}', '\u{ed}', '\u{f3}', '\u{fa}'];
        let glyphs = ScreenGlyphs::new(Vec::new(), letters, 220);
        assert_eq!(glyphs.letters, ['\u{e1}', '\u{e9}', '\u{ed}', '\u{f3}']);
        let mut texts = Texts {
            data: Vec::new(),
            offsets: Vec::new(),
            first: 32,
            count: 95,
            glyphs: glyphs.clone(),
        };
        let k = texts.add(&db_text(&glyphs, "\u{f3}\u{fa}"));
        assert_eq!(text_bytes(&texts, k), [255, b'u']);
    }
}
