//! A page's commands as the bytecode the ROM runs, or nothing if the ROM
//! cannot run all of them.
//!
//! **A page is emitted only if all its commands can be run.** One this
//! compiler does not model leaves the whole page out, and the event does
//! nothing: running half a script would leave the game in a state that
//! does not exist, and a capture taken there would defend it as good.
//!
//! Every operand is resolved here —an RM2k event id to its index in the
//! map's table, a map to its index in the cartridge, a variable to its
//! slot, a text to its offset— so the ROM never looks at the game again.

use crate::codes::*;
use crate::fail::{Bad, Result, Step, Stop};
use crate::game::{Command, Game, Sound};
use crate::messages::Messages;
use crate::opcodes::*;
use crate::pages::MapEvents;
use crate::registry::{Backdrop, Graphics, Package, Picture, Songs, Troops};
use crate::route;
use std::collections::{BTreeMap, BTreeSet, HashMap};

// --- the engine's numbers ------------------------------------------------------

/// RM2k measures waits in tenths of a second, and the ROM in frames.
pub const FRAMES_PER_TENTH: i64 = 6;
/// `DEFAULT_FPS`, which is what the timer counts with.
pub const FRAMES_PER_SECOND: i64 = 60;
/// `Game_Party::SetTimer` stores `seconds * 60 + 59`, not `seconds * 60`.
/// The extra 59 are what makes the first second show whole: without them
/// the timer would show the requested value for a single frame.
const TIMER_EXTRA_FRAMES: i64 = 59;
/// An absurd range of switches is not unrolled: better not to run the page
/// than to emit thousands of opcodes for one line.
const MAX_RANGE: i64 = 64;
/// How many switches the ROM's bitmap holds: `SWITCH_BYTES` is 128, that is
/// 0 to 1023. A branch on a higher one would write out of bounds, so it does
/// not compile.
/// Measured against the game this was built with: an assumption of the
/// engine, not a fact of the format.
const SWITCH_MAX: i64 = 1024;
/// The inventory: one byte per item of the database in far RAM, `FAR_ITEMS`,
/// indexed by the RM2k number. It was measured against the game this was
/// built with —its 450 items plus 0, which is not used—: an assumption of
/// the engine. See the `ChangeItems` arm.
pub const ITEMS_N: i64 = 451;
/// The equipment slots of an actor: weapon, shield, armor, helmet and
/// accessory.
const EQUIPMENT_SLOTS: i64 = 5;
/// How many graphics fit in a map's table: the operand is a byte.
const GRAPHICS_MAX: usize = 0xFF;
/// The variable slot is a byte, and far RAM has room for 256: see
/// `VAR_REFRESH` for why it stopped being seven bits.
pub const VAR_SLOT_MAX: usize = 0xFF;
/// How many frames a `MovePicture` can last to fit in `OP_PICTURE_MOVE`'s
/// byte. The two of the "1 year earlier" page —see `compile_picture`— last
/// 210 and 120.
const PICTURE_FRAMES_MAX: i64 = 255;
/// How deep a `CallEvent` nests. It is not an abstract precaution: a common
/// event can call itself —the body in place would be infinite— and two can
/// call each other. In the game this was measured on the longest chain that
/// compiles is one.
const CALL_MAX: usize = 4;

// ControlSwitches: the first parameter says where the ids come from and the
// last what to do with them (liblcf, ControlSwitches::Operation).
const SWITCH_SINGLE: i64 = 0;
const SWITCH_RANGE: i64 = 1;
const SWITCH_ON: i64 = 0;
const SWITCH_TOGGLE: i64 = 2;
// ControlVars: the operations, where the operand comes from, and the "other"
// ones and a character's coordinates.
//
// The operations that compile: set, add, subtract. Multiply, divide and
// modulo are not used by any page of the game.
const VAR_SET: i64 = 0;
const VAR_ADD: i64 = 1;
const VAR_SUBTRACT: i64 = 2;
// And where the operand comes from, with the RM2k number: a constant, another
// variable, a random number between a and b, or "other", which here are the
// gold and the seconds the timer has left. The random one requires b - a to be
// less than 256: the ROM divides with the hardware's eight-bit divider.
pub const VAR_CONSTANT: i64 = 0;
pub const VAR_VARIABLE: i64 = 1;
const VAR_RANDOM: i64 = 3;
// And kind 6: **a character's coordinates**. The sub-operands are those of
// easyrpg-player's `ControlVariables::Event` —the `op` of
// `game_interpreter_control_variables.cpp`—: 0 the map id, 1 x, 2 y, 3 where
// it faces, 4 and 5 the screen coordinates and 6 the event id. They are not
// from memory, which is the house rule.
//
// Of the 829 times the game uses it, **827 ask for x or y** and the other two
// for the screen x and y; nobody asks for the map id, the facing or the event
// id. So the ROM does 1 and 2, and the rest does not compile:
//
// * **0** in RM2k returns 0 for an event —an RPG_RT defect easyrpg copies—, so
//   doing it would be copying a defect nobody uses;
// * **3** returns 8, 6, 2 or 4 —the numeric keypad— and not 0..3;
// * **4** and **5** are screen pixels, and ours is 256x224 against RM2k's
//   320x240: the number the variable would end up with is not the original
//   game's. They are two occurrences in the whole game, and accepting them
//   would unlock **one** more page —measured, 5135 against 5136—: it is not
//   worth making up a coordinate that is not the one there for one page.
pub const VAR_CHARACTER: i64 = 6;
// And kind 5, an actor's data, of which the ROM does 2 to 5: the HP, the SP
// and their maximums. See `actor_stat` in tools/runtime/level.s.
const VAR_ACTOR: i64 = 5;
const ACTOR_STAT_HP: i64 = 2;
const ACTOR_STAT_SP_MAX: i64 = 5;
const VAR_OTHER: i64 = 7;
const OTHER_GOLD: i64 = 0;
const OTHER_TIMER: i64 = 1;
const CHARACTER_X: i64 = 1;
const CHARACTER_Y: i64 = 2;
const CMP_EQUAL: i64 = 0;
const CMP_NOT_EQUAL: i64 = 5;
/// The top bit of the **flags byte** of every opcode that writes a variable
/// —the operation in OP_VAR, the flags in OP_KEY, the mode in OP_TERRAIN and
/// in OP_LOCATION—: whether this write asks for the page refresh.
///
/// It is `Game_Map::SetNeedRefreshForVarChange`, which does **not** mark the
/// refresh for any write: it asks the `map_cache`, which has the list of the
/// variables some page condition of the loaded map looks at. Here that
/// question does not need to be run: who looks at what is static per map and
/// a page's bytecode is compiled **for its map**, so the converter answers it
/// —`refresh`— and on the console what is left is a `bpl`.
///
/// Without this the port ran at **30 frames per second in half of Lashe
/// City**: maps 8, 20, 23, 26, 28 and 32 have a parallel page that writes
/// four variables per frame —the hero's coordinates against an event's— and
/// each write asked for the whole refresh, which on map 8 is 68 events and
/// 106 pages and **does not fit in a frame**. None of those four variables is
/// looked at by any page condition, neither there nor on any other map of the
/// game.
///
/// **Until 2026-09-27 the bit went in the slot**, which that way fit in seven
/// bits: 128 variables. The game names 127, and `MemorizeLocation` and
/// `RecallToLocation` add nine more —127 to 129 of the droid tutorial and
/// `DisplayNameMenu`, 158 to 160 and 169 to 171 of the opening menus—, so the
/// bit moved to the flags byte, which in the three opcodes had the top one
/// free, and the slot was left at eight bits: 256, which is what far RAM
/// reserves between `FAR_VARIABLES` and `FAR_ITEMS`.
pub const VAR_REFRESH: i64 = 0x80;
// TimerOperation. The parameters are (operation, where the seconds come from,
// seconds, visible, in battle): liblcf, TimerOperation::Operation.
const TIMER_SET: i64 = 0;
const TIMER_START: i64 = 1;
const TIMER_STOP: i64 = 2;
/// The other value takes the seconds from a variable.
const TIMER_FIXED_SECONDS: i64 = 0;
/// The timer's fourth operation: the seconds from a variable. RM2k's three
/// are 0, 1 and 2.
const TIMER_SET_VAR: i64 = 3;
// ConditionalBranch: the kinds, and the actor's questions.
pub const COND_SWITCH: i64 = 0;
pub const COND_VARIABLE: i64 = 1;
const COND_GOLD: i64 = 3;
const COND_ITEM: i64 = 4;
pub const COND_ACTOR: i64 = 5;
const COND_ACTOR_IN_PARTY: i64 = 0;
pub const COND_ACTOR_SKILL: i64 = 4;
pub const COND_ACTOR_EQUIPMENT: i64 = 5;
// The route targets. 10002 to 10004 are the vehicles —boat, ship, airship—,
// which do not exist here.
pub const ROUTE_HERO: i64 = 10001;
/// "This event", the page's owner.
pub const ROUTE_THIS_EVENT: i64 = 10005;
// ChangePartyMembers: the first parameter says whether it adds or removes, the
// second where the actor's id comes from, and the third the id. From liblcf
// and `Game_Interpreter::CommandChangePartyMember` in easyrpg-player.
const PARTY_ADD: i64 = 0;
const PARTY_REMOVE: i64 = 1;
pub const PARTY_FIXED_ID: i64 = 0;
// ChangeEventLocation: `p[1]` 0 is the written cell, 1 reads it from
// variables, and there is no third: `CommandChangeEventLocation` has two
// branches and nothing else.
const PLACE_CONSTANT: i64 = 0;
const PLACE_BY_VARIABLE: i64 = 1;
// OP_LOCATION: recalling, and the refresh bits of the three writes —the map,
// x and y—.
const PLACE_JUMP: u8 = 0x01;
const PLACE_REFRESHES: [u8; 3] = [0x80, 0x40, 0x20];
// PanScreen. Of its four operations the game uses two —112 `pan` and 21
// `reset`, and not one `lock` or `unlock`— so those are the ones that
// compile.
const PAN_SHIFT: i64 = 2;
const PAN_RETURN: i64 = 3;
/// The camera's units inside RM2k: `SCREEN_TILE_SIZE`, that is 1/16 of a
/// pixel, with a 16-pixel cell worth 256. Keeping them is not a whim: speed
/// 2 moves the camera **half a pixel per frame**, and in whole pixels that
/// cannot be counted.
const PAN_UNIT: i64 = 256;
// KeyInputProc's flags: see the command's arm.
/// Bit 0 on purpose: `key_value` reads it with an `lsr`.
const KEY_WAIT: i64 = 0x01;
const KEY_DIRS: i64 = 0x02;
const KEY_DECISION: i64 = 0x04;
const KEY_CANCEL: i64 = 0x08;
const KEY_START: i64 = 0x10;
// The three permissions, and their bit in `FAR_ACCESS`. The bits mean
// "forbidden" so that the reset's zero is "everything allowed", which is how
// RM2k starts. $80 is the menu request —`menu_calling`— and it is not a
// permission.
//
// The operand is the bit and not the permission's number, and that is from the
// third round: the ROM got it with an `inc a` on the number, which gives $01
// and $02 for the first two and **$03 for the third**, that is forbidding the
// other two things at once. With the bit set by the converter the opcode has
// no math to do and accepts whatever permissions are needed.
const ACCESS_BIT: [u8; 3] = [0x01, 0x02, 0x04];
// ChangeScreenTransitions: `[which, transition]`. See the command's arm.
const TRANSITION_ERASE: i64 = 0;
const TRANSITION_SHOW: i64 = 1;
const RM2K_TRANSITION_MOSAIC: i64 = 17;
/// The cut and "none", which erasing compiles to the cut.
const RM2K_CUT_TRANSITIONS: [i64; 2] = [19, 20];
// What the bytecode carries: what the ROM does, and not the RM2k number.
const TRANSITION_FADE: u8 = 0;
const TRANSITION_MOSAIC: u8 = 1;
const TRANSITION_CUT: u8 = 2;
// ShowBattleAnimation: the kinds of entry of its timeline. See
// `compile_animation`.
const ANIM_SOUND: u8 = 0;
const ANIM_SCREEN_FLASH: u8 = 1;
const ANIM_FLASH: u8 = 2;
/// Ten, which is how long RM2k's lasts, and **even** on purpose: the screen
/// flash works in two phases according to the parity of what it has left
/// —see `flash_tick`—, and a `FlashScreen` of the game always lasts tenths
/// times six. With eleven the first phase was the even one, a path no page
/// takes and that therefore tests nothing: the `animacion` case showed it.
const ANIM_FLASH_FRAMES: u8 = 10;
/// "This animation is not drawn", and it is used by the ones RM2k repeats
/// three by three to cover the screen —`global`—, which are not done.
const ANIM_NO_DRAWING: u8 = 0xFF;
/// "Screen" scope: goes to the center, no target.
const ANIM_TARGET_SCREEN: u8 = 0xFF;
// EnemyEncounter. Where the backdrop comes from, parameter [2] of
// `CommandEnemyEncounter`: 0 the local one —the map's, or that of the terrain
// the hero stands on: it is `Game_Map::SetupBattle`—, 1 the one the command
// names and 2 that of a given terrain, which is RM2k3's.
const BATTLE_BACKDROP_OF_PLACE: i64 = 0;
const BATTLE_BACKDROP_OF_COMMAND: i64 = 1;
/// The escape parameter: 0 cannot, 1 cuts the battle. Only 1 is asked about.
const BATTLE_ESCAPE_CUTS: i64 = 1;
const BATTLE_DEFEAT_GAME_OVER: i64 = 0;
/// The destination that means "this does not continue: this is a Game
/// Over". It goes in the defeat's place when the `EnemyEncounter` carries
/// `defeat_mode` 0, which in RM2k is `Scene_Gameover`. It is an impossible
/// destination —all three are absolute within the page and none in the game
/// reaches 64 KB— so no new opcode or extra byte per battle is needed. The
/// ROM looks at it in `op_battle`.
const BATTLE_LOSE: usize = 0xFFFF;
/// The three handlers, in the order their destinations go in the opcode.
const BATTLE_HANDLERS: [i32; 3] = [VICTORY_HANDLER, ESCAPE_HANDLER, DEFEAT_HANDLER];
/// RM2k shows four options at most, and `GetChoices(4)` discards the ones
/// with a higher index. The ROM's window has four lines, so the cap is the
/// same on both sides.
const CHOICE_MAX: i64 = 4;
// The cursor, and what is put in front of the options that do not have it so
// the text does not shift from line to line.
const CHOICE_CURSOR: &str = ">";
const CHOICE_INDENT: &str = " ";
// Where the two destinations go inside `OP_CELL_TEST` —see events.toml—, and
// the top two bits of each write, over the variable's offset: y instead of
// x, and the refresh. See `cell_test` in tools/runtime/interpreter_cells.s.
const CELL_DEST_A: usize = 10;
const CELL_DEST_B: usize = 16;
const CELL_Y: i64 = 0x4000;
const CELL_REFRESH: i64 = 0x8000;
// Encounters: RM2k's table as (minimum ratio, pmod exponent), and the rate
// every step adds —the terrain's, 100 in the game this was measured on—.
//
// Everything here comes from easyrpg-player —`Game_Player::UpdateEncounterSteps`,
// `Game_Map::GetEncountersAt` and `Game_Map::PrepareEncounter`— and not from
// intuition, which in this repo has already cost three times.
//
// **Where the data lives**: not in the `.lmu` but in the tree, `RPG_RT.lmt`.
// Each node —map or *area*— carries `encounters` (a list of troops),
// `encounter_steps` (25 by default, 0 = off) and `area_rect`. An area is a
// type 2 node: it has no `.lmu`, hangs from a map and covers a rectangle of
// it.
//
// **How it triggers**, step by step of the hero and only those from the pad
// —a forced route leaves through `IsMoveRouteOverwritten` before `IncSteps`,
// so it does not count—:
//
//     accumulated += encounter_rate of the terrain it stands on
//     ratio = accumulated / encounter_steps         (integer)
//     while ratio >= TABLE[idx + 1][0]: idx++       (idx never goes down)
//     p = (1 / encounter_steps) * pmod * (rate / 100)
//     if it hits, accumulated = 0 and idx = 0, and an encounter is pending
//
// The pending one is collected on the next frame, with the hero already
// standing: the map's troops plus those of each area covering its cell are
// gathered and one is chosen at random. If there is none —the hero is outside
// all areas— nothing happens, which is what `PrepareEncounter` does when it
// returns `false`.
//
// **Two simplifications, both measured over the whole game** and enforced by
// `rom/pruebas/herramientas/test_encuentros.py`, which is what keeps them
// from becoming a lie the day someone touches the data:
//
// * **the terrain changes nothing**: the eleven terrain tags the 53 maps with
//   encounters step on have `encounter_rate` 100, so the accumulated goes up
//   by 100 always and the `rate / 100` factor is 1;
// * **no troop filters by terrain**: the 129 the encounters name have an
//   empty `terrain_set`, and in RM2k empty means "on all of them".
//
// With that the model stays entirely in integers, which is what the console
// can do without floating point: see `enc_step_thresholds`.
//
// It is `UpdateEncounterSteps`' table: easyrpg's eight `pmod`s are powers of
// two —1/16, 1/8, 1/4, 1/2, 2, 4, 8, 16— so here they go as shifts and the
// math needs no floats. The ninth row there is `{INT_MAX, 16.0}`, that is a
// cap that is never reached: the `while` does not go past the last of these.
const ENC_TABLE: [(i64, i64); 8] = [
    (0, -4),
    (20, -3),
    (40, -2),
    (60, -1),
    (100, 1),
    (140, 2),
    (160, 3),
    (180, 4),
];
/// The `encounter_rate` the accumulated goes up by: the terrain's, which in
/// the game this was measured on is 100 on the 53 maps with encounters. See
/// above.
const ENC_RATE: i64 = 100;
// --- the battle's audio -----------------------------------------------------
//
// All from the LDB, nothing made up: the battle song, the victory one and the
// effects `Game_System::GetSystemSE` hands out. Who sounds at what moment
// comes from easyrpg-player and **not from memory**, which is this repo's
// rule:
//
//   battle_music      `Scene_Battle`, on construction
//   battle_end_music  `Scene_Battle_Rpg2k`, on winning (BGM_Victory)
//   dodge_se          `AlgorithmBase::GetFailureSe`: the hit that misses
//   enemy_attack_se   `Normal::GetStartSe` with the enemy as source
//   enemy_damaged_se  the hit's `eMessage` sub-state, enemy target
//   actor_damaged_se  same, party target
//   enemy_death_se    `ProcessBattleActionDeath`
//   escape_se         `Scene_Battle_Rpg2k`, when the party escapes
//
// In the game this was measured on `battle_se` —the battle-start one— is
// "(OFF)", so nothing is registered for it: a name that does not resolve to
// any file still goes into the tables but would take up an entry that is
// forever silent.
//
// **This is registered inside the compilation** —`battle_audio`, when
// compiling the `EnemyEncounter`— and not in the converter: the `Songs`
// indices are carried by the bytecode of each `PlayBGM` and each `PlaySound`,
// so everyone who compiles pages has to number the same way, and a song noted
// from outside would shift all the ones after it.
/// The battle's effects. The order is the contract with the ROM: the
/// converter emits `BA_SE_<n>` with the index each one got from `Songs`, in
/// this order.
pub const BATTLE_AUDIO_SE: [&str; 7] = [
    "dodge_se",
    "enemy_attack_se",
    "enemy_damaged_se",
    "actor_damaged_se",
    "enemy_death_se",
    "escape_se",
    // The one from 2026-09-13, when the battle started letting items be
    // used: easyrpg's `Item::GetStartSe`, which is the LDB's `item_se`.
    "item_se",
];
/// A name RM2k uses to say "nothing": neither the song nor the effect exist.
const AUDIO_OFF: [&str; 2] = ["", "(OFF)"];

/// Commands accepted while doing nothing, because doing nothing does not
/// show. It is the same criterion as the doors', and it has to be applied
/// with the same distrust: if the command changes something we do draw, it
/// does not go here.
///
/// `MessageOptions` is where and how the message window is drawn, which
/// without messages is drawn nowhere.
const IGNORABLE: [i32; 1] = [MESSAGE_OPTIONS];
/// And this is something else, and the difference matters. The ones above
/// do nothing because there is nothing to do. The ones here **do** do
/// something and the ROM does not do it; they are accepted anyway because
/// what they leave undone does not appear on the screen being compared, and
/// in exchange they let pages run that would otherwise be left out whole.
///
/// It is a debt, not an equivalence, and that is why it is in a separate
/// list with its own name: whoever adds something here has to be able to
/// say what breaks. Each one's is in its arm of [`compile_command`].
///
/// `CallEvent` **is no longer here**: since 2026-09-12 it is compiled in
/// place, see `compile_call`. What is left of that is that a call whose
/// target does not compile is skipped just like before, and that is decided
/// in there and not in this list: the command itself is no longer a whole
/// debt. Neither is `PlayBGM`, which is done since the songs have a
/// registry: see its arm.
pub const ACCEPTED_UNDONE: [i32; 5] = [
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
    CHANGE_SYSTEM_BGM,
    CHANGE_HERO_TITLE,
];

/// What cuts an exit `PlayBGM` before the jump: branches, choices, battles,
/// calls and loops —with them, what follows is no longer a single line—, and
/// the jumps whose destination is not always known —`RecallToLocation` and
/// `PlayMemorizedBGM`—, which are taken as not leaving. The effects too, but
/// those show in `Songs::requested`, which also counts an animation's.
const CUT_THE_EXIT: [i32; 21] = [
    COND_BRANCH,
    COND_ELSE,
    COND_END,
    SHOW_CHOICE,
    SHOW_CHOICE_OPTION,
    SHOW_CHOICE_END,
    ENEMY_ENCOUNTER,
    END_BATTLE,
    CALL_EVENT,
    SHOW_INN,
    INN_STAY,
    INN_NO_STAY,
    INN_END,
    RECALL_TO_LOCATION,
    PLAY_MEMORIZED_BGM,
    VICTORY_HANDLER,
    ESCAPE_HANDLER,
    DEFEAT_HANDLER,
    LABEL,
    JUMP_TO_LABEL,
    LOOP,
];
/// And `BreakLoop`, `EndLoop` and `EndEventProcessing`.
const CUT_THE_EXIT_TOO: [i32; 3] = [BREAK_LOOP, END_LOOP, END_EVENT_PROCESSING];

// --- what the compiler knows before compiling anything -------------------------

/// The indices of the whole game, built once before compiling anything:
/// see [`crate::indices`].
#[derive(Debug, Clone, Default)]
pub struct Indices {
    /// RM2k variable to its slot in the ROM.
    pub variables: BTreeMap<i32, usize>,
    /// (actor, skill) to its bit in `FAR_SKILL`.
    pub skills: BTreeMap<(i32, i32), usize>,
    /// The switch that turns on each equipment common event, and its number.
    pub party_common_events: BTreeMap<i32, i32>,
}

impl Indices {
    pub fn variable_slot(&self, number: i64) -> Step<u8> {
        let slot = *i32::try_from(number)
            .ok()
            .and_then(|n| self.variables.get(&n))
            .ok_or(Stop::Cannot)?;
        if slot > VAR_SLOT_MAX {
            return Err(Stop::Cannot);
        }
        Ok(slot as u8)
    }

    fn skill_slot(&self, actor: i64, skill: i64) -> Step<i64> {
        match (i32::try_from(actor), i32::try_from(skill)) {
            (Ok(a), Ok(s)) => self
                .skills
                .get(&(a, s))
                .map(|&v| v as i64)
                .ok_or(Stop::Cannot),
            _ => Err(Stop::Cannot),
        }
    }
}

/// The decisions of the game's project file about its sound effects: which
/// ones play with another sample on some map, which ones the routes and the
/// troops leave out of their package. **The game's decisions by ear**, in
/// its project file —`[sound_effects]`— with the reason for each.
#[derive(Debug, Clone, Default)]
pub struct SoundSettings {
    /// (name in RM2k, map id) and the sample that plays there instead. Each
    /// one is one more sound effect, but not one more directory entry: it
    /// shares a place with those of the other packages. From
    /// `[sound_effects] per_map`.
    pub per_map: Vec<(String, i64, String)>,
    /// Per map, the effects that forced move routes ask for —move command
    /// 35, see `ROUTE_SOUND`— and that **do not fit** in their map's audio
    /// package: None is all of them. From `[sound_effects]
    /// route_effects_left_out`.
    pub route_left_out: Vec<(i64, Option<BTreeSet<String>>)>,
    /// The troop pages' effects that **do** go into the battle's package.
    /// From `[sound_effects] troop_effects_in_package`.
    pub troop_in_package: BTreeSet<String>,
}

/// Everything a page is compiled with. What is `None` is something this
/// compilation does not have, and the commands that need it do not compile
/// —or are accepted without being done, each as its comment says—.
pub struct Ctx<'a> {
    pub game: &'a Game,
    pub indices: &'a Indices,
    pub sound: &'a SoundSettings,
    /// An RM2k map id to its index in the cartridge; None if it did not get
    /// in: a teleport to one of those makes the page not runnable, which is
    /// more honest than jumping anywhere.
    pub map_index: &'a dyn Fn(i64) -> Option<usize>,
    /// The ROM's text block. Without it the text boxes do not compile, and
    /// it is not a matter of taste: the window takes 8 KB of VRAM and a
    /// palette, so a ROM that does not carry it has nowhere to draw them.
    pub messages: Option<&'a mut Messages>,
    pub songs: Option<&'a mut Songs>,
    pub graphics: Option<&'a mut Graphics>,
    pub picture: Option<&'a Picture>,
    /// The troops the cartridge is going to have to carry. **It does not
    /// change the bytecode** —the troop number emitted is RM2k's— so a ROM
    /// without a registry compiles exactly the same; the only thing lost is
    /// knowing which tables have to be emitted.
    pub troops: Option<&'a mut Troops>,
}

// --- bytes ---------------------------------------------------------------------

/// A value that has to be a byte. One that is not stops the conversion,
/// which is what the converter always did with it.
fn byte(v: i64) -> Step<u8> {
    u8::try_from(v).map_err(|_| Stop::Fatal(Bad::answer(format!("{v} does not fit in a byte"))))
}

/// A word, little-endian: `v & 0xFF` and `v >> 8`, and the second has to fit.
fn word(v: i64) -> Step<[u8; 2]> {
    Ok([(v & 0xFF) as u8, byte(v >> 8)?])
}

fn usize_word(v: usize) -> Step<[u8; 2]> {
    word(v as i64)
}

fn cannot<T>() -> Step<T> {
    Err(Stop::Cannot)
}

// --- the page ------------------------------------------------------------------

/// Where a branch still has its destination blank: the piece, and for a
/// piece with two destinations —`OP_CELL_TEST`— where in it.
#[derive(Debug, Clone, Copy)]
enum Open {
    End(usize),
    At(usize, usize),
}

fn with_dest(piece: &[u8], dest: usize) -> Step<Vec<u8>> {
    let mut out = piece[..piece.len() - 2].to_vec();
    out.extend(usize_word(dest)?);
    Ok(out)
}

fn patch(pieces: &mut [Vec<u8>], open: Open, dest: usize) -> Step<()> {
    match open {
        Open::End(i) => pieces[i] = with_dest(&pieces[i], dest)?,
        Open::At(i, at) => {
            let w = usize_word(dest)?;
            pieces[i][at] = w[0];
            pieces[i][at + 1] = w[1];
        }
    }
    Ok(())
}

struct Choice {
    at: usize,
    n: usize,
    cancel: i64,
    frames: Vec<usize>,
    destinations: Vec<Option<usize>>,
    seen: usize,
    exits: Vec<usize>,
}

struct Battle {
    at: usize,
    troop: i64,
    destinations: [Option<usize>; 3],
    game_over: bool,
    seen: usize,
    exits: Vec<usize>,
}

/// What the page's last `PlayBGM` is doing, command by command: see
/// [`follow_exit`].
#[derive(Default)]
struct Exit {
    pending: Option<usize>,
    noted: Vec<(usize, bool)>,
    jumps: Vec<(usize, Option<usize>)>,
}

/// The commands, one at a time, except a text box, which is its
/// `ShowMessage` with the `ShowMessage_2`s that follow: one window, one
/// wait. Returns the position of each and the extra lines.
///
/// RM2k emits a `ShowMessage` with the first line and a `ShowMessage_2` for
/// each of the following lines of the same box: they are a single command
/// —one window, one wait for the player— and whoever counts them separately
/// measures nonsense. It already happened: counting them apart, the text
/// boxes seemed to unlock three pages instead of fifty-five.
///
/// A loose `ShowMessage_2` is returned alone and does not compile, which is
/// right: it would be a line with no window to put it in. It is part of the
/// filter and not of the emitter: counting the commands separately is what
/// made that measurement come out wrong.
fn group_boxes(commands: &[Command]) -> Vec<(usize, Vec<String>)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < commands.len() {
        let mut j = i + 1;
        if commands[i].code == SHOW_MESSAGE {
            while j < commands.len() && commands[j].code == SHOW_MESSAGE_2 {
                j += 1;
            }
        }
        out.push((
            i,
            commands[i + 1..j]
                .iter()
                .map(|c| c.string.clone())
                .collect(),
        ));
        i = j;
    }
    out
}

/// A page's commands as bytes, or None if it cannot be done.
///
/// `map_events` is the map's `MapEvents`, already pointed at the page's
/// owner. Without it a forced route can only be on the hero: there is
/// nothing to translate the RM2k id to the table's index with.
///
/// `base` and `depth` are for what is compiled in place —a `CallEvent`, an
/// equipment common event—: the called event's body is emitted in the place
/// of the call. `base` is where this piece starts inside the outer page,
/// because the branches' destinations are absolute; `depth` is the nesting,
/// which is capped. A piece in place **carries no `OP_DONE`**: in RM2k the
/// called event's `END` returns to the caller, it does not end the page.
pub fn compile_page(
    ctx: &mut Ctx,
    commands: &[Command],
    map_events: Option<MapEvents>,
    base: usize,
    depth: usize,
) -> Result<Option<Vec<u8>>> {
    let mark = ctx.messages.as_ref().map(|m| m.mark());
    match page(ctx, commands, map_events, base, depth) {
        Ok(code) => Ok(Some(code)),
        Err(Stop::Cannot) => {
            if let (Some(m), Some(mark)) = (ctx.messages.as_deref_mut(), mark) {
                m.rewind(mark);
            }
            Ok(None)
        }
        Err(Stop::Fatal(bad)) => Err(bad),
    }
}

fn page(
    ctx: &mut Ctx,
    commands: &[Command],
    mut map_events: Option<MapEvents>,
    base: usize,
    depth: usize,
) -> Step<Vec<u8>> {
    // The branches are emitted with the destination blank and patched when
    // closing them, which is the only way: until what is inside is compiled
    // it is not known how much it takes. The stack carries the nesting, so
    // there is no need to look at the indentation as `SkipToNextConditional`
    // does —it walks the list of commands, here the blocks already come
    // properly nested—.
    let mut pieces: Vec<Vec<u8>> = Vec::new();
    // See `base`: the branches' destinations are absolute within the outer
    // page.
    let mut length = base;
    let mut stack: Vec<Open> = Vec::new();
    // A `ShowChoice`'s options and whether an `EnemyEncounter` has its
    // handlers are looked ahead, which is what RM2k does —`GetChoices`—: in
    // the loop the commands come one at a time and already grouped.
    //
    // An `EnemyEncounter` comes **without a handler block** when the battle
    // has no branch to write, which is exactly what happens with
    // `defeat_mode` 0: losing is the Game Over screen and not a branch of the
    // page. They are the game's 15 pages that did not compile before
    // 2026-09-13 —among them the Rat Tracks boss—, and all 15 are like this:
    // without this, accepting the Game Over left them falling into "an
    // unclosed battle".
    let options_of: HashMap<usize, Vec<(i64, String)>> = commands
        .iter()
        .enumerate()
        .filter(|(_, c)| c.code == SHOW_CHOICE)
        .map(|(i, _)| (i, choice_options(commands, i)))
        .collect();
    let no_block: BTreeSet<usize> = commands
        .iter()
        .enumerate()
        .filter(|(i, c)| {
            c.code == ENEMY_ENCOUNTER
                && (i + 1 >= commands.len() || !BATTLE_HANDLERS.contains(&commands[i + 1].code))
        })
        .map(|(i, _)| i)
        .collect();
    // The four of "is it on the cell?", which go in a single opcode —see
    // `fadable_cells`—: each command's role —0 and 1 the writes, 2 and 3 the
    // branches— and the pattern's first command; and each pattern's fused
    // piece by its first command, when it is emitted.
    let mut cell_role: HashMap<usize, (usize, usize)> = HashMap::new();
    for i in fadable_cells(commands) {
        for n in 0..4 {
            cell_role.insert(i + n, (n, i));
        }
    }
    let mut cell_piece: HashMap<usize, usize> = HashMap::new();
    let mut choices: Vec<Choice> = Vec::new();
    let mut battles: Vec<Battle> = Vec::new();
    // The pending `PlayBGM`, what was noted and the jumps: see `follow_exit`.
    let mut exit = Exit::default();
    // The last thing the page put in each variable, if it was a constant:
    // see `recalled_destination`.
    let mut constants: HashMap<i64, i64> = HashMap::new();
    let mut faded: Vec<u8> = Vec::new();

    for (i, extra) in group_boxes(commands) {
        let cmd = &commands[i];
        let requested = ctx.songs.as_ref().map_or(0, |s| s.requested);
        let mut role = cell_role.get(&i).copied();
        if let Some((0, _)) = role {
            // It is built here and not before because the refresh depends on
            // `map_events`, which changes after a `Teleport`.
            let loose = &commands[i..i + 4];
            let writes = [
                compile_command(ctx, &loose[0], &[], map_events.as_ref())?,
                compile_command(ctx, &loose[1], &[], map_events.as_ref())?,
            ];
            let branches = [branch_bytes(ctx, &loose[2])?, branch_bytes(ctx, &loose[3])?];
            match cell_test_piece(&writes, &branches)? {
                None => {
                    for n in 0..4 {
                        cell_role.remove(&(i + n));
                    }
                    role = None;
                }
                Some(piece) => {
                    faded = piece;
                    cell_piece.insert(i, pieces.len());
                }
            }
        }
        let piece: Vec<u8>;
        if let Some((n, first)) = role {
            piece = if n == 0 { faded.clone() } else { vec![] };
            if n < 2 {
                note_constant(cmd, &mut constants);
            } else {
                stack.push(Open::At(
                    cell_piece[&first],
                    if n == 2 { CELL_DEST_A } else { CELL_DEST_B },
                ));
            }
        } else if cmd.code == ENEMY_ENCOUNTER {
            // `EnemyEncounter` and its three handlers. It is the sibling of
            // `OP_CHOICE`: the command opens a screen that blocks, and **the
            // outcome chooses where the page continues**, so the opcode
            // carries the three destinations and the converter patches them
            // when closing the block, same as a choice's options.
            //
            // The troop number goes **as RM2k's** and not as an index of
            // ours, on purpose: which ones go in the cartridge is decided by
            // the converter looking at all the pages, and if the bytecode
            // carried the index, the same number would mean another troop
            // depending on which maps each ROM carries. With the RM2k number
            // inside, a page's bytecode is always the same; the ROM resolves
            // it by looking it up in `troop_id`, and a troop that is not
            // there is a battle that does not happen and goes out through
            // the victory branch.
            //
            // The destinations are **absolute within the page**, like
            // `OP_IF`'s. A handler the page does not have points to the end
            // of the block, that is to the `EndBattle`, which is what RM2k
            // does when the sub-index has no branch.
            //
            // OP_BATTLE: troop (word), victory (word), escape (word), defeat
            // (word)
            let troop = encounter_troop(cmd)?;
            if let Some(troops) = ctx.troops.as_deref_mut() {
                troops.request(troop as i32, encounter_backdrop(cmd));
            }
            // The song and effects the battle plays, noted in the battle's
            // package: see `battle_audio`.
            battle_audio(ctx);
            let losing_is_game_over = cmd.p(4) == Some(BATTLE_DEFEAT_GAME_OVER);
            if no_block.contains(&i) {
                // No handlers: the battle closes right here. Winning and
                // escaping continue with the command below —which is what
                // RM2k does when there are no branches— and losing goes to
                // `BATTLE_LOSE`, that is to the Game Over.
                //
                // **Escaping points to victory and not elsewhere**, and it is
                // a declared approximation: the 24 battles of this form carry
                // `escape_mode` 0 —escape forbidden—, so there the exit does
                // not exist; here the battle lets you escape anyway, because
                // the permission does not travel in the opcode:
                // `ChangeEscapeAccess` is stored —see `CHANGE_ESCAPE_ACCESS`—
                // but the battle does not read it.
                let next_at = length + 9;
                let lose = if losing_is_game_over {
                    BATTLE_LOSE
                } else {
                    next_at
                };
                let mut p = vec![OP_BATTLE];
                p.extend(word(troop)?);
                p.extend(usize_word(next_at)?);
                p.extend(usize_word(next_at)?);
                p.extend(usize_word(lose)?);
                piece = p;
            } else {
                battles.push(Battle {
                    at: pieces.len(),
                    troop,
                    destinations: [None; 3],
                    game_over: losing_is_game_over,
                    seen: 0,
                    exits: vec![],
                });
                // The room, filled in at the `EndBattle`.
                piece = vec![0; 9];
            }
        } else if BATTLE_HANDLERS.contains(&cmd.code) {
            let Some(current) = battles.last_mut() else {
                return cannot();
            };
            let n = BATTLE_HANDLERS.iter().position(|&h| h == cmd.code).unwrap();
            // The previous handler's body ends here and is taken out of the
            // block with a jump to the end, patched when closing it. It is
            // the same `ShowChoiceOption` does, and for the same reason: that
            // way there is no need to look at the indentation.
            piece = if current.seen == 0 {
                vec![]
            } else {
                vec![OP_GOTO, 0, 0]
            };
            if !piece.is_empty() {
                current.exits.push(pieces.len());
            }
            current.seen += 1;
            if current.destinations[n].is_some() {
                return cannot();
            }
            current.destinations[n] = Some(length + piece.len());
        } else if cmd.code == END_BATTLE {
            let Some(current) = battles.pop() else {
                return cannot();
            };
            let mut table = vec![OP_BATTLE];
            table.extend(word(current.troop)?);
            for (n, dest) in current.destinations.iter().enumerate() {
                // The handler the page does not have falls at the end of the
                // block, which is what RM2k does with a sub-index without a
                // branch: `SetSubcommandIndex` and carry on. **Except the
                // defeat with `defeat_mode` 0**, which there is not a missing
                // branch but the Game Over: see `BATTLE_LOSE`.
                let d = match dest {
                    None if n == 2 && current.game_over => BATTLE_LOSE,
                    None => length,
                    Some(d) => *d,
                };
                table.extend(usize_word(d)?);
            }
            pieces[current.at] = table;
            for out in current.exits {
                pieces[out] = with_dest(&pieces[out], length)?;
            }
            piece = vec![];
        } else if cmd.code == SHOW_CHOICE {
            if ctx.messages.is_none() {
                return cannot();
            }
            let options = &options_of[&i];
            if options.is_empty() {
                return cannot();
            }
            if options.iter().enumerate().any(|(k, (n, _))| *n != k as i64) {
                return cannot();
            }
            let cancel = cmd.p(0).unwrap_or(0);
            if cancel > options.len() as i64 {
                // `cancel_type` 5 with four options is the "cancel branch", a
                // fifth one that is not in the list. Nobody uses it in the
                // game and doing it blindly would be making things up.
                return cannot();
            }
            // OP_CHOICE: how many options (byte), what cancel does (byte),
            // and then one entry per option: the text box (word) and the
            // destination (word). It is `ShowChoice`.
            //
            // **One text box per option, not a single one.** The boxes carry
            // the same lines and differ in where the cursor is, so moving the
            // cursor is recomposing the window with another offset and not
            // drawing anything new. It costs a few dozen bytes per choice and
            // saves a sprite tile, a palette and all the code to draw it: on
            // the console there is nowhere to put a cursor that is not a
            // sprite, and this map's sprites are already spread among the
            // characters.
            //
            // The destination is absolute within the page, like OP_IF's, and
            // each option's body ends in an OP_GOTO to the end of the choice.
            let frames = choice_boxes(options, ctx.messages.as_deref_mut().unwrap())?;
            choices.push(Choice {
                at: pieces.len(),
                n: options.len(),
                cancel,
                frames,
                destinations: vec![None; options.len()],
                seen: 0,
                exits: vec![],
            });
            // The table's room, filled in at the `ShowChoiceEnd`.
            piece = vec![0; 3 + 4 * options.len()];
        } else if cmd.code == SHOW_CHOICE_OPTION {
            let Some(current) = choices.last_mut() else {
                return cannot();
            };
            let n = cmd.p(0).unwrap_or(0);
            if !(0 <= n && n < current.n as i64) {
                return cannot();
            }
            // The previous option's body ends here: it is taken out of the
            // choice with a jump to the end, patched when closing it. Emitting
            // it here and not at the body's `END` is what keeps this from
            // depending on looking at the indentation.
            piece = if current.seen == 0 {
                vec![]
            } else {
                vec![OP_GOTO, 0, 0]
            };
            if !piece.is_empty() {
                current.exits.push(pieces.len());
            }
            current.seen += 1;
            current.destinations[n as usize] = Some(length + piece.len());
        } else if cmd.code == SHOW_CHOICE_END {
            let Some(current) = choices.pop() else {
                return cannot();
            };
            if current.destinations.iter().any(|d| d.is_none()) {
                return cannot();
            }
            let mut table = vec![OP_CHOICE, byte(current.n as i64)?, byte(current.cancel)?];
            for (frame, dest) in current.frames.iter().zip(&current.destinations) {
                table.extend(usize_word(*frame)?);
                table.extend(usize_word(dest.unwrap())?);
            }
            pieces[current.at] = table;
            for out in current.exits {
                pieces[out] = with_dest(&pieces[out], length)?;
            }
            piece = vec![];
        } else if cmd.code == COND_BRANCH {
            // OP_IF: kind (byte), operand (word), polarity (byte),
            // destination (word): `ConditionalBranch` with a switch
            // condition. If it is not met, the cursor jumps to the
            // destination, which is the `else` or the `end` of that same
            // branch. The polarity is RM2k's reversed and on purpose: there
            // `parameters[2] == 0` means "has to be on", so here 0 is "on"
            // and 1 is "off", same as the data.
            //
            // The destination is **absolute** within the page, not relative:
            // the ROM's cursor is a 16-bit index into the same array, so
            // assigning it is the whole jump.
            stack.push(Open::End(pieces.len()));
            piece = branch_bytes(ctx, cmd)?;
        } else if cmd.code == COND_ELSE {
            let Some(open) = stack.pop() else {
                return cannot();
            };
            // OP_GOTO: destination (word): the unconditional jump emitted
            // where the `else` was, so the branch above skips the one below.
            piece = vec![OP_GOTO, 0, 0];
            // The `if`'s destination is **after** this jump, which is where
            // the branch below starts; the jump's is resolved at the `end`,
            // with the piece left open in its place.
            patch(&mut pieces, open, length + 3)?;
            stack.push(Open::End(pieces.len()));
        } else if cmd.code == COND_END {
            let Some(open) = stack.pop() else {
                return cannot();
            };
            patch(&mut pieces, open, length)?;
            piece = vec![];
        } else if cmd.code == SHOW_INN {
            piece = compile_inn(ctx, cmd, length)?;
        } else if cmd.code == CONTROL_SWITCHES
            && cmd.parameters.len() >= 4
            && cmd.p(3) == Some(SWITCH_TOGGLE)
        {
            piece = compile_toggle(cmd, length)?;
        } else if matches!(cmd.code, INN_STAY | INN_NO_STAY | INN_END) {
            // The inn's three branches. None of the game's 18 pages uses them
            // —measured on 2026-09-20—, and doing them requires exactly what
            // `compile_inn` does not have: a place to put the body of
            // "stayed" inside a choice that is already built.
            return cannot();
        } else if cmd.code == CALL_EVENT {
            piece = compile_call(ctx, cmd, length, depth, map_events.as_ref())?;
        } else {
            let mut p = compile_command(ctx, cmd, &extra, map_events.as_ref())?;
            // A jump to another map: the page keeps running there. See
            // `MapEvents::after_jump`.
            if cmd.code == TELEPORT {
                if let Some(me) = &map_events {
                    if cmd.p(0) != Some(me.map_id as i64) {
                        map_events = Some(me.after_jump());
                    }
                }
            }
            if cmd.code == RECALL_TO_LOCATION {
                let dest = recalled_destination(ctx, cmd, &constants);
                if let Some(me) = &map_events {
                    if dest != Some(me.map_id as i64) {
                        map_events = Some(me.after_jump());
                    }
                }
            }
            note_constant(cmd, &mut constants);
            // An equipment common event whose switch this turns on: its body
            // goes right here, as if a `CallEvent` followed it. In RM2k it
            // would run on the next frame; see `party_common_events` in
            // [`crate::indices`].
            for number in common_events_turned_on(ctx, cmd) {
                let body = ctx
                    .game
                    .common_events
                    .get(&number)
                    .map(|c| c.commands.clone())
                    .unwrap_or_default();
                let at = length + p.len();
                let code = compile_page(ctx, &body, map_events.clone(), at, depth + 1)?;
                p.extend(code.unwrap_or_default());
            }
            piece = p;
        }
        if ctx.songs.is_some() {
            let played = ctx.songs.as_ref().unwrap().requested != requested;
            follow_exit(ctx, cmd, &mut exit, played);
        }
        length += piece.len();
        pieces.push(piece);
    }
    if !stack.is_empty() || !choices.is_empty() || !battles.is_empty() {
        return cannot();
    }
    // What was noted from the `PlayBGM`s counts only if the page compiles:
    // one that does not, does not run, and says nothing about how the map is
    // left.
    if let Some(song) = exit.pending {
        exit.noted.push((song, false));
    }
    if let Some(songs) = ctx.songs.as_deref_mut() {
        for (song, is_exit) in exit.noted {
            songs.note_exit(song, is_exit);
        }
        for (dest, song) in exit.jumps {
            songs.jump(dest, song);
        }
    }
    let mut code: Vec<u8> = pieces.concat();
    // The `OP_DONE` belongs to the page and not to the piece: a body in place
    // carrying it would end the caller's page instead of returning control
    // to it. See `base`.
    if depth == 0 {
        code.push(OP_DONE);
    }
    Ok(code)
}

// --- following an exit song ------------------------------------------------------

/// Follows, command by command, whether the page's last `PlayBGM` is an
/// exit one —see `exit_songs` in the converter's `Songs`—: it is if what
/// comes up to a `Teleport` to another map plays no effect (`played_sound`),
/// turns on no other song and does not branch. What was noted is passed to
/// the registry only if the page compiles.
///
/// A jump to the same map also cuts it: it reloads the package with the
/// song playing, which is the inheritance case and not the leaving one.
///
/// And it notes each jump to another map with the song it carries if it is
/// an exit one, or None: see `Songs::jump`.
fn follow_exit(ctx: &mut Ctx, cmd: &Command, exit: &mut Exit, played_sound: bool) {
    let songs = ctx.songs.as_deref_mut().unwrap();
    let current = songs.current;
    let here = |dest: Option<usize>| match (current, dest) {
        (Some(Package::Map(c)), Some(d)) => c == d,
        (None, None) => true,
        _ => false,
    };
    if cmd.code == TELEPORT && current.is_some() {
        let dest = (ctx.map_index)(cmd.p(0).unwrap_or(0));
        if let Some(d) = dest {
            if !here(Some(d)) {
                exit.jumps.push((d, exit.pending));
            }
        }
    }
    if cmd.code == PLAY_BGM && !cmd.string.is_empty() {
        if let Some(p) = exit.pending {
            exit.noted.push((p, false));
        }
        exit.pending = songs.song(&cmd.string);
        return;
    }
    let Some(pending) = exit.pending else { return };
    if cmd.code == TELEPORT {
        let is_exit = !here((ctx.map_index)(cmd.p(0).unwrap_or(0)));
        exit.noted.push((pending, is_exit));
        exit.pending = None;
    } else if played_sound
        || CUT_THE_EXIT.contains(&cmd.code)
        || CUT_THE_EXIT_TOO.contains(&cmd.code)
    {
        exit.noted.push((pending, false));
        exit.pending = None;
    }
}

/// The RM2k id of the map a `RecallToLocation` jumps to, if the page set it
/// with a constant before —the breaking floors load 61 or 60 into the
/// variable, and jump right away—, or None.
///
/// What is known is noted as the map's destination in the song registry,
/// same as a `Teleport`: it is where it comes from which song may be playing
/// on arrival. What is not known —the way back from a tutorial, which jumps
/// to whatever another page remembered— is not noted, and it is the only
/// thing the audio does not see: the song that arrives that way has to be in
/// the destination's package by another path. In the game it is the droid
/// tutorial going back to 48 with the song it left there with.
fn recalled_destination(
    ctx: &mut Ctx,
    cmd: &Command,
    constants: &HashMap<i64, i64>,
) -> Option<i64> {
    let dest = cmd.p(0).and_then(|v| constants.get(&v).copied());
    if let (Some(d), Some(songs)) = (dest, ctx.songs.as_deref_mut()) {
        if let Some(index) = (ctx.map_index)(d) {
            songs.dest(index);
            if songs.current != Some(Package::Map(index)) {
                songs.jump(index, None);
            }
        }
    }
    dest
}

/// Keeps the last constant the page put in each variable, and forgets the
/// variable if it wrote it some other way. It does not look at branches: it
/// is for `recalled_destination`, which only uses it to note an audio
/// destination.
fn note_constant(cmd: &Command, constants: &mut HashMap<i64, i64>) {
    let p = &cmd.parameters;
    let v = |i: usize| p[i] as i64;
    if cmd.code == CONTROL_VARS && p.len() >= 7 {
        let (first, last) = if v(0) == 0 {
            (v(1), v(1))
        } else {
            (v(1), v(2))
        };
        for number in first..=last {
            constants.remove(&number);
        }
        if v(0) == 0 && v(3) == VAR_SET && v(4) == VAR_CONSTANT {
            constants.insert(v(1), v(5));
        }
    } else if matches!(
        cmd.code,
        MEMORIZE_LOCATION | KEY_INPUT_PROC | STORE_TERRAIN_ID
    ) && !p.is_empty()
    {
        let written: &[i32] = match cmd.code {
            MEMORIZE_LOCATION => &p[..p.len().min(3)],
            STORE_TERRAIN_ID => &p[p.len().min(3)..p.len().min(4)],
            _ => &p[..1],
        };
        for &number in written {
            constants.remove(&(number as i64));
        }
    }
}

/// The equipment common events —see `party_common_events` in
/// [`crate::indices`]— whose switch this command turns on.
fn common_events_turned_on(ctx: &Ctx, cmd: &Command) -> Vec<i32> {
    let p = &cmd.parameters;
    if cmd.code != CONTROL_SWITCHES
        || p.len() < 4
        || p[3] as i64 != SWITCH_ON
        || !(p[0] as i64 == SWITCH_SINGLE || p[0] as i64 == SWITCH_RANGE)
    {
        return vec![];
    }
    ctx.indices
        .party_common_events
        .iter()
        .filter(|(&switch, _)| p[1] <= switch && switch <= p[2])
        .map(|(_, &number)| number)
        .collect()
}

// --- the commands that are built from several opcodes ----------------------------

/// `CallEvent`, compiled **in place**: the called event's body goes in the
/// place of the call.
///
/// In RM2k this is `Push<ExecutionType::Call>`, that is a stack of
/// interpreters. Here none is needed, and that is the decision: the called
/// one runs whole before the caller continues, so pasting its bytecode in
/// the middle gives exactly the same. What a real stack would cost —a cursor
/// and a page per level in bank 0's RAM, which is full— buys no observable
/// difference: **no call in the game is recursive**, and the only price of
/// pasting is the size, measured below.
///
/// And it comes without touching the ROM: it runs the same bytecode as
/// always.
///
/// **If the called one does not compile, the call is skipped**, which is
/// what the port has always done with this command. It is declared debt and
/// not equivalence, and requiring it to compile would cost 183 pages that
/// run today: measured, only 6 of the 189 pages that compile and call have
/// all their targets compilable.
fn compile_call(
    ctx: &mut Ctx,
    cmd: &Command,
    length: usize,
    depth: usize,
    map_events: Option<&MapEvents>,
) -> Step<Vec<u8>> {
    let p = &cmd.parameters;
    if p.len() < 2 || depth >= CALL_MAX {
        return Ok(vec![]);
    }
    if p[0] == 0 && ctx.game.patches.counters.contains_key(&p[1]) {
        return compile_counter(ctx, p[1]);
    }
    let (body, context) = if p[0] == 0 {
        // A common event, by number. The game's are cut almost all of them
        // at `ControlVars` and at the original's own menus.
        (
            ctx.game
                .common_events
                .get(&p[1])
                .map(|c| c.commands.clone()),
            map_events.cloned(),
        )
    } else if p[0] == 1 && p.len() >= 3 && map_events.is_some() {
        // A map event, by id and **page number**, which in RM2k starts at
        // one: it is `CommandCallEvent`'s `page->ID`.
        //
        // "This event" inside the called one is **the called one**, not the
        // caller: `Push` passes it `event->GetId()`. Without this a
        // Hover-Tram route would move the Tram Officer.
        let me = map_events.unwrap();
        let Some(pages) = me.pages(p[1]) else {
            return Ok(vec![]);
        };
        if !(1 <= p[2] && p[2] as usize <= pages.len()) {
            return Ok(vec![]);
        }
        (
            Some(pages[p[2] as usize - 1].clone()),
            Some(me.for_event(p[1])),
        )
    } else {
        // By variable —type 2— it is not resolved at compile time and never
        // will be: the number comes from the save. It is skipped, as before.
        return Ok(vec![]);
    };
    let Some(body) = body else { return Ok(vec![]) };
    if body.is_empty() {
        return Ok(vec![]);
    }
    Ok(compile_page(ctx, &body, context, length, depth + 1)?.unwrap_or_default())
}

/// `ControlSwitches` that toggles: no opcode of its own, one branch per
/// switch with what the interpreter already does —like the inn, it is built
/// here because the destinations are absolute within the page and the one
/// that carries `length` is the page's loop—. For each switch, with the
/// offsets relative to its piece:
///
/// ```text
///  0  OP_IF       on, and if not, to 14
///  7  OP_SWITCH   turn it off
/// 11  OP_GOTO     to 18
/// 14  OP_SWITCH   turn it on
/// 18  the next one
/// ```
///
/// It is 18 bytes per switch against the 4 of an opcode that flipped the
/// bit, and the game toggles a single one, 286, twelve times in Eisen's
/// story (89 ev4 and 93 ev4 p2): it does not justify code in the ROM.
fn compile_toggle(cmd: &Command, length: usize) -> Step<Vec<u8>> {
    let p = |i: usize| cmd.parameters[i] as i64;
    if p(0) != SWITCH_SINGLE && p(0) != SWITCH_RANGE {
        return cannot();
    }
    let (first, last) = (p(1), p(2));
    if last < first || last - first >= MAX_RANGE {
        return cannot();
    }
    let mut out = Vec::new();
    for number in first..=last {
        let here = length + out.len();
        let (turn_on, end) = (here + 14, here + 18);
        let n = word(number)?;
        out.push(OP_IF);
        out.push(COND_SWITCH as u8);
        out.extend(n);
        out.push(0);
        out.extend(usize_word(turn_on)?);
        out.extend([OP_SWITCH, n[0], n[1], 0]);
        out.push(OP_GOTO);
        out.extend(usize_word(end)?);
        out.extend([OP_SWITCH, n[0], n[1], 1]);
    }
    Ok(out)
}

/// `ShowInn`, expanded into commands the ROM already knows how to do. The
/// game has 18 pages with one and none uses the branches —measured on
/// 2026-09-20—, so the command is compiled alone.
///
/// The inn is not a new opcode: it is the greeting with its choice, a branch
/// on gold, the charge and the heal, which are five things the interpreter
/// already did. It is built here and not in `compile_command` because the
/// destinations of the choice and of the branch are offsets **absolute
/// within the page**, and that is known by the page's loop, which is the one
/// that carries `length`.
///
/// What comes out, with the offsets relative to the start of the block:
///
/// ```text
///  0  OP_MESSAGE  the greeting, two lines
///  3  OP_CHOICE   "Yes" and "No"; cancel is "No"
/// 14  OP_IF       gold >= price, and if not, to the end
/// 21  OP_GOLD     it is charged
/// 26  OP_HEAL     the whole party to the maximum
/// 30  the end, which is where "No" and "cannot afford it" land
/// ```
///
/// The greeting is `CommandShowInn`'s (easyrpg
/// `game_interpreter_map.cpp:449-560`): `"{greeting_1} {price}{gold}
/// {greeting_2}"` on the first line —hence the two spaces, because the
/// game's `greeting_2` starts with one— and `greeting_3` on the second. The
/// terms are from the LDB: see `Game::inn_terms`.
///
/// **Three declared debts**, and all three are about what is seen and not
/// about what happens:
///
/// * there is no gold window next to the greeting;
/// * "Yes" is not grayed out when it cannot be afforded, so it can be
///   chosen; choosing it amounts to "No", which is what the gold branch
///   does. In RM2k the cursor does not let it be selected;
/// * there is no fade to black nor inn music: it charges and heals on the
///   spot. That is `Scene_Map::CallInn`.
///
/// **A free inn is just the heal**: with the price at zero `CommandShowInn`
/// shows nothing and goes straight to
/// `ContinuationShowInnStart(indent, 0, 0)`, which stays, charges zero and
/// rests. They are 6 of the game's 18 pages, those of maps 39, 59, 77 and
/// 111 —the rooms where the script lets you sleep—.
fn compile_inn(ctx: &mut Ctx, cmd: &Command, length: usize) -> Step<Vec<u8>> {
    if cmd.parameters.len() < 2 {
        return cannot();
    }
    let (kind, price) = (cmd.p(0).unwrap(), cmd.p(1).unwrap());
    if price == 0 {
        return Ok(vec![OP_HEAL, 0, 0, 0]);
    }
    let Some(messages) = ctx.messages.as_deref_mut() else {
        return cannot();
    };
    if !(kind == 0 || kind == 1) {
        return cannot();
    }
    if price > 0xFFFF {
        // The cap is the gold branch's operand, which goes in a word; the
        // game's most expensive is 100.
        return cannot();
    }
    let t = &ctx.game.inn_terms[kind as usize];
    let greeting = format!("{} {}{} {}", t[0], price, ctx.game.gold_term, t[1]);
    let at = messages.add(&[greeting, t[2].clone()])?;
    let frames = choice_boxes(&[(0, t[3].clone()), (1, t[4].clone())], messages)?;
    let end = length + 30;
    let mut out = vec![OP_MESSAGE];
    out.extend(usize_word(at)?);
    // Cancel is the second option: there the default `choice_cancel_type` is
    // 5 and `inn_stay` is `choice_result == 0`, that is cancelling is not
    // staying.
    out.extend([OP_CHOICE, 2, 2]);
    out.extend(usize_word(frames[0])?);
    out.extend(usize_word(length + 14)?);
    out.extend(usize_word(frames[1])?);
    out.extend(usize_word(end)?);
    out.extend([OP_IF, COND_GOLD as u8]);
    out.extend(word(price)?);
    out.push(0);
    out.extend(usize_word(end)?);
    out.extend([
        OP_GOLD,
        1,
        (price & 0xFF) as u8,
        ((price >> 8) & 0xFF) as u8,
        0,
    ]);
    out.extend([OP_HEAL, 0, 0, 0]);
    Ok(out)
}

/// The options of the `ShowChoice` at `commands[i]`, as (index, text).
///
/// It is `Game_Interpreter::GetChoices`: it walks forward from the next
/// command, gathers the `ShowChoiceOption`s on its same indentation and
/// stops at the `ShowChoiceEnd`. The `10` that closes each option's body is
/// `END`, and there is no need to look at it: the jump to the end of the
/// choice is emitted in the next option, which is where it is known that
/// the previous one ended.
fn choice_options(commands: &[Command], i: usize) -> Vec<(i64, String)> {
    if i + 1 >= commands.len() {
        return vec![];
    }
    let level = commands[i + 1].indent;
    let mut out = Vec::new();
    for cmd in &commands[i + 1..] {
        if cmd.indent != level {
            continue;
        }
        if cmd.code == SHOW_CHOICE_END {
            break;
        }
        if cmd.code == SHOW_CHOICE_OPTION
            && !cmd.parameters.is_empty()
            && cmd.p(0).unwrap() < CHOICE_MAX
        {
            out.push((cmd.p(0).unwrap(), cmd.string.clone()));
        }
    }
    out
}

/// One box per option, with the cursor on its line: moving the cursor is
/// showing another box.
///
/// The boxes are the same except for the cursor. `Messages` deduplicates by
/// content, so the common lines are not stored twice: what is paid is one
/// small box per option.
fn choice_boxes(options: &[(i64, String)], messages: &mut Messages) -> Step<Vec<usize>> {
    let texts: Vec<&String> = options.iter().map(|(_, t)| t).collect();
    let mut out = Vec::new();
    for n in 0..texts.len() {
        let lines: Vec<String> = texts
            .iter()
            .enumerate()
            .map(|(k, t)| {
                format!(
                    "{} {}",
                    if k == n { CHOICE_CURSOR } else { CHOICE_INDENT },
                    t
                )
            })
            .collect();
        out.push(messages.add(&lines)?);
    }
    Ok(out)
}

// --- branches ----------------------------------------------------------------------

/// A `ConditionalBranch` of the kinds this knows, with the destination
/// blank: switch, variable, gold, item, and three of the actor's seven
/// questions. The polarity is RM2k's as is.
/// The long whys of these conditions are in `git show 1487129f^:tools/port/events.py`.
fn branch_bytes(ctx: &Ctx, cmd: &Command) -> Step<Vec<u8>> {
    let p = |i: usize| cmd.p(i);
    if cmd.parameters.len() < 3 {
        return cannot();
    }
    let kind = p(0).unwrap();
    let number = p(1).unwrap();
    if kind == COND_SWITCH {
        if !(0..SWITCH_MAX).contains(&number) {
            return cannot();
        }
    } else if kind == COND_GOLD {
        if !(0..=0xFFFF).contains(&number) {
            return cannot();
        }
    } else if kind == COND_ITEM {
        // The inventory **already exists** —`OP_ITEM` and `FAR_ITEMS`,
        // since 2026-09-10—: the item branch is `GetItemCount(id) > 0`,
        // exactly the same question as the page condition by item, which the
        // ROM already answers by reading `FAR_ITEMS`. Equipment does not
        // count, as in `conditions_ok`: `GetEquippedItemCount` asks for
        // equipment, which there is none.
        if !(0..ITEMS_N).contains(&number) {
            return cannot();
        }
    } else if kind == COND_ACTOR {
        if !(0..=0xFFFF).contains(&number) {
            return cannot();
        }
        let question = p(2).unwrap();
        if question == COND_ACTOR_IN_PARTY {
            // No polarity: the branch below is the `else`.
            let mut out = vec![OP_IF, COND_ACTOR as u8];
            out.extend(word(number)?);
            out.extend([0, 0, 0]);
            return Ok(out);
        }
        // The two actor questions that do not fit in `OP_IF`, since
        // 2026-09-13: "does it have this item equipped?" and "does it know
        // this skill?". They do not fit because they carry **two** operands
        // —the actor and the item or the skill— and `OP_IF` has a single
        // one; the actor fits in a byte because the LDB has 60 and
        // `ACTORS_N` counts them, and the data does not, because the items go
        // up to 450.
        //
        // It carries no polarity: RM2k gives none to these two —the branch
        // below is the `else`— same as to "is in the party". The destination
        // goes last, as in all of them, because it is what `with_dest`
        // patches when closing the branch.
        //
        // OP_IF_ACTOR: sub (byte), actor (byte), data (word), destination
        // (word)
        //
        // The skill: `actor->IsSkillLearned(p[3])`. Since 2026-09-21 it is
        // state: the bit of the (actor, skill) pair in `FAR_SKILL`, which
        // starts with what `rules.learned_skills` says from the LDB and which
        // `ChangeSkills` turns on and off. The operand that travels is the
        // pair's slot and not the skill; see `skills` in [`crate::indices`].
        //
        // The equipment: easyrpg's five `Get*Id()`s compared against `p[3]`:
        // weapon, shield, armor, helmet and accessory. This **is** real state
        // —`FAR_EQUIPMENT`, which the equipment screen writes and which
        // travels in the save— and it starts from the LDB's
        // `initial_equipment`. Asking about item 0 says yes as soon as there
        // is an empty slot, which is what RM2k does; no page of the game
        // does it.
        if question == COND_ACTOR_SKILL || question == COND_ACTOR_EQUIPMENT {
            if cmd.parameters.len() < 4 {
                return cannot();
            }
            if !(0..=0xFF).contains(&number) {
                return cannot();
            }
            if !ctx.game.actors.contains_key(&(number as i32)) {
                return cannot();
            }
            let mut operand = p(3).unwrap();
            if question == COND_ACTOR_SKILL {
                // The skill travels as its pair's slot: the bit the ROM
                // looks at.
                operand = ctx.indices.skill_slot(number, operand)?;
            }
            if !(0..=0xFFFF).contains(&operand) {
                return cannot();
            }
            let mut out = vec![OP_IF_ACTOR, question as u8, number as u8];
            out.extend(word(operand)?);
            out.extend([0, 0]);
            return Ok(out);
        }
        return cannot();
    } else if kind == COND_VARIABLE {
        if cmd.parameters.len() < 5 {
            return cannot();
        }
        let slot = ctx.indices.variable_slot(number)?;
        let (operand_kind, value) = match p(2).unwrap() {
            0 => {
                let v = p(3).unwrap();
                if !(-0x8000..=0x7FFF).contains(&v) {
                    return cannot();
                }
                (VAR_CONSTANT, v)
            }
            1 => (
                VAR_VARIABLE,
                ctx.indices.variable_slot(p(3).unwrap())? as i64,
            ),
            _ => return cannot(),
        };
        let comparison = p(4).unwrap();
        if !(0..=CMP_NOT_EQUAL).contains(&comparison) {
            return cannot();
        }
        return Ok(vec![
            OP_IF_VAR,
            slot,
            operand_kind as u8,
            comparison as u8,
            (value & 0xFF) as u8,
            ((value >> 8) & 0xFF) as u8,
            0,
            0,
        ]);
    } else {
        return cannot();
    }
    let mut out = vec![OP_IF, byte(kind)?];
    out.extend(word(number)?);
    out.extend([if p(2).unwrap() != 0 { 1 } else { 0 }, 0, 0]);
    Ok(out)
}

/// Where each "is it on the cell?" pattern starts: two `ControlVars` that
/// put the x and the y of the same character in two variables, and two
/// nested `ConditionalBranch`es —the second is the first thing inside the
/// first— that compare one variable with another for equality.
/// `OP_CELL_TEST` does the four in one turn of the interpreter.
///
/// It is the pattern of the parallel pages that check whether two
/// characters touch: the forty of each lap of the race, the lights of map 11
/// and some two hundred more in the game. Fused, it runs in a single turn of
/// the interpreter instead of four, and it is what keeps the race at 60
/// frames: see `cell_test` in tools/runtime/interpreter_cells.s.
///
/// Only the shape is looked at here; whether the operands compile is said
/// by `cell_test_piece`, which is the one that emits.
fn fadable_cells(commands: &[Command]) -> Vec<usize> {
    let set_cell = |c: &Command| {
        let p = &c.parameters;
        c.code == CONTROL_VARS
            && p.len() >= 7
            && p[0] == 0
            && p[3] as i64 == VAR_SET
            && p[4] as i64 == VAR_CHARACTER
    };
    let equal_to_variable = |c: &Command| {
        let p = &c.parameters;
        c.code == COND_BRANCH
            && p.len() >= 5
            && p[0] as i64 == COND_VARIABLE
            && p[2] == 1
            && p[4] as i64 == CMP_EQUAL
    };
    let mut starts = Vec::new();
    let mut i = 0;
    while i + 3 < commands.len() {
        let (a, b, c, d) = (
            &commands[i],
            &commands[i + 1],
            &commands[i + 2],
            &commands[i + 3],
        );
        if set_cell(a)
            && set_cell(b)
            && a.parameters[5] == b.parameters[5]
            && equal_to_variable(c)
            && equal_to_variable(d)
            && a.indent == b.indent
            && b.indent == c.indent
            && d.indent == c.indent + 1
        {
            starts.push(i);
            i += 4;
        } else {
            i += 1;
        }
    }
    starts
}

/// `OP_CELL_TEST` with both destinations blank, built from what the four
/// loose opcodes would be —so the checks and the refresh are the same—, or
/// None if they cannot be fused.
fn cell_test_piece(writes: &[Vec<u8>; 2], branches: &[Vec<u8>; 2]) -> Step<Option<Vec<u8>>> {
    for v in writes {
        if v.len() < 8
            || v[0] != OP_VAR
            || v[3] as i64 != VAR_CHARACTER
            || v[5] != 0
            || v[7] != 0
            || !(v[6] as i64 == CHARACTER_X || v[6] as i64 == CHARACTER_Y)
            || (v[2] as i64 & !VAR_REFRESH) != VAR_SET
        {
            return Ok(None);
        }
    }
    let (v1, v2) = (&writes[0], &writes[1]);
    if v1[4] != v2[4] {
        return Ok(None);
    }
    for r in branches {
        if r[0] != OP_IF_VAR || r[2] as i64 != VAR_VARIABLE || r[3] as i64 != CMP_EQUAL || r[5] != 0
        {
            return Ok(None);
        }
    }
    let (r1, r2) = (&branches[0], &branches[1]);
    let write = |v: &Vec<u8>| {
        (v[1] as i64 * 2)
            | if v[6] as i64 == CHARACTER_Y {
                CELL_Y
            } else {
                0
            }
            | if v[2] as i64 & VAR_REFRESH != 0 {
                CELL_REFRESH
            } else {
                0
            }
    };
    let words = [
        write(v1),
        write(v2),
        r1[1] as i64 * 2,
        r1[4] as i64 * 2,
        0,
        r2[1] as i64 * 2,
        r2[4] as i64 * 2,
        0,
    ];
    let mut piece = vec![OP_CELL_TEST, v1[4]];
    for w in words {
        piece.extend(word(w)?);
    }
    debug_assert_eq!(piece.len(), size_of(OP_CELL_TEST));
    Ok(Some(piece))
}

// --- the battle ------------------------------------------------------------------

/// The troop number of an `EnemyEncounter`, or it does not compile.
///
/// The indices come from easyrpg-player's
/// `Game_Interpreter_Map::CommandEnemyEncounter`, **not from memory**: `[0]`
/// says whether the troop comes from a variable, `[1]` is the troop, `[2]`
/// where the backdrop comes from, `[3]` what happens on escape, `[4]` what
/// happens on defeat and `[5]` whether the party strikes first. This only
/// does the case the game's 51 battles use —troop by constant— and stops on
/// the others, as always: better to emit nothing than to emit something the
/// ROM does differently.
///
/// What this does, and why the rest cuts the page:
///
/// * **the troop by constant**: reading it from a variable would require
///   resolving in the ROM which troop it is, and none of the game's 51
///   battles uses it;
/// * **escape forbidden or with a handler**, but not `escape_mode` 1, which
///   in RM2k cuts the whole page on escaping —`abort_on_escape`— and would
///   be a path with nothing exercising it;
/// * **defeat**, with a handler or without: `defeat_mode` 0 is RM2k's Game
///   Over screen, and since 2026-09-13 it is emitted as `BATTLE_LOSE` in
///   the defeat's destination. The ROM notes it before fighting and, if it
///   loses, shows the Game Over screen and from there goes back to boot
///   —that is to the title screen, with the saved game waiting in SRAM—:
///   see tools/runtime/game_over.s and what it still does not do in
///   `workflow/divergencias/lo-que-la-pantalla-de-game-over-no-modela.md`.
///   What is not done is what was done before 2026-09-13, which was not
///   compiling the page: it cost 15, among them the Rat Tracks boss.
///
/// The backdrop is not looked at here: `encounter_backdrop` gets it.
pub fn encounter_troop(cmd: &Command) -> Step<i64> {
    if cmd.parameters.len() < 6 {
        return cannot();
    }
    if cmd.p(0) != Some(0) {
        return cannot();
    }
    let troop = cmd.p(1).unwrap();
    if !(0 < troop && troop <= 0xFFFF) {
        return cannot();
    }
    if cmd.p(3) == Some(BATTLE_ESCAPE_CUTS) {
        return cannot();
    }
    Ok(troop)
}

/// The backdrop of an `EnemyEncounter`: the name it carries, the local one,
/// or none.
///
/// Parameter `[2]` of `CommandEnemyEncounter` says where the backdrop comes
/// from: 1 is "the one this command says", which is what 49 of the game's 51
/// battles do, with the name in the string —empty is no backdrop—; 0 is the
/// local one, `Game_Map::SetupBattle`, which is what the other two do (on
/// 105 and on 141), and the ROM resolves it when the battle starts: it is
/// not known when compiling, because it depends on where the hero is. 2 is
/// RM2k3's.
pub fn encounter_backdrop(cmd: &Command) -> Option<Backdrop> {
    match cmd.p(2) {
        Some(BATTLE_BACKDROP_OF_COMMAND) if !cmd.string.is_empty() => {
            Some(Backdrop::Named(cmd.string.clone()))
        }
        Some(BATTLE_BACKDROP_OF_PLACE) => Some(Backdrop::Place),
        _ => None,
    }
}

/// Notes what the battle plays —two songs and the system effects— in the
/// battle's package, and returns their indices: `$FF` or `$FFFF` the off
/// one.
///
/// It is called every time a page compiles an `EnemyEncounter`. What is
/// noted falls into the battle's package and not into that of the map that
/// has the battle, so the registry's current package has to be saved and
/// restored around it.
pub fn battle_audio(ctx: &mut Ctx) -> Option<Vec<(String, usize)>> {
    let game = ctx.game;
    let songs = ctx.songs.as_deref_mut()?;
    let previous = songs.current;
    songs.current = Some(Package::Battle);
    let mut out = Vec::new();
    for (name, song) in [
        ("battle_music", &game.battle_music),
        ("battle_end_music", &game.battle_end_music),
    ] {
        let k = if AUDIO_OFF.contains(&song.as_str()) {
            0xFF
        } else {
            songs.index(song)
        };
        out.push((name.to_string(), k));
    }
    for name in BATTLE_AUDIO_SE {
        let effect = game.system_se[name].clone();
        let k = if AUDIO_OFF.contains(&effect.0.as_str()) {
            0xFFFF
        } else {
            songs.sound(effect, true)
        };
        out.push((name.to_string(), k));
    }
    songs.current = previous;
    Some(out)
}

/// The actor operand of `OP_HEAL` and `OP_EQUIPMENT`, from RM2k's
/// `[type, id]`.
///
/// It is easyrpg's `GetActors` (`game_interpreter.cpp:1539`): 0 the party,
/// 1 a fixed actor, 2 the actor a variable says. The operand is the actor,
/// with 0 for "the whole party": the LDB has no actor 0, so it is not
/// mistaken for anyone.
///
/// Form 2 is not used by any `FullHeal` nor by any `ChangeHP` that adds
/// —measured on 2026-09-19 over the 328 maps and the common events—, nor by
/// any `ChangeEquipment` —on 2026-09-21—, so it does not compile instead of
/// being resolved in the ROM with nothing exercising it.
/// OP_ACTOR's `what`: the SP and not the HP, getting a fallen one up with 1,
/// the amount as a variable's slot, a loss that can kill, and subtracting.
/// The ROM reads them with the same numbers: `ACT_*` in
/// tools/runtime/level.s.
const ACT_SP: u8 = 0x01;
const ACT_REVIVE: u8 = 0x02;
const ACT_VARIABLE: u8 = 0x20;
const ACT_LETHAL: u8 = 0x40;
const ACT_SUBTRACT: u8 = 0x80;

/// OP_ENEMY's `what`: the SP and not the HP, and that a loss of HP can kill.
/// `ENEMY_*` in tools/runtime/battle_troop.s.
const ENEMY_SP: u8 = 0x01;
const ENEMY_LETHAL: u8 = 0x80;

/// RM2k's death state, `State::kDeathID`.
const DEATH_STATE: i64 = 1;

/// OP_ACTOR for `ChangeHP` and `ChangeSP`, which share their first five
/// parameters: [type, id, subtracts, amount by variable, amount]. `what`
/// brings what the caller already knows —the SP, lethal—.
fn actor_change(ctx: &Ctx, p: &[i32], mut what: u8) -> Step<Vec<u8>> {
    let q = |i: usize| -> i64 { p[i] as i64 };
    if q(2) != 0 {
        what |= ACT_SUBTRACT;
    }
    let amount = if q(3) != 0 {
        what |= ACT_VARIABLE;
        ctx.indices.variable_slot(q(4))? as i64
    } else if (0..=0x7FFF).contains(&q(4)) {
        q(4)
    } else {
        return cannot();
    };
    let mut out = vec![OP_ACTOR, target_actor(p)?, what];
    out.extend(word(amount)?);
    Ok(out)
}

fn target_actor(p: &[i32]) -> Step<u8> {
    if p[0] == 0 {
        return Ok(0);
    }
    if p[0] == 1 && 0 < p[1] && p[1] <= 0xFF {
        return Ok(p[1] as u8);
    }
    cannot()
}

/// A step's chance of an encounter: the formula's `1 / encounter_steps`, in
/// 1/65536.
///
/// A step's chance is `pmod / steps`, and `pmod` is a power of two: if the
/// quotient is precomputed here, on the console what is left is a shift and
/// a sixteen-bit comparison, with no division. **The truncation is part of
/// the contract**: both sides use this same number. The cartridge's comes
/// from `base` in `rm2k-snes-battle`, which does the same; this one is
/// `ChangeEncounterSteps`', and the converter's model —`enc_base` in
/// events.py— is the one the tests compare the ROM against.
///
/// Zero means off, which is what `encounter_steps` 0 means in RM2k. One
/// step saturates at `$FFFF`, which still fights on every step: see `base`
/// in `rm2k-snes-battle`, which has the arithmetic.
pub fn enc_base(steps: i64) -> i64 {
    if steps <= 0 {
        0
    } else {
        (0x10000 / steps).min(0xFFFF)
    }
}

/// At which step each row of `ENC_TABLE` is crossed, counting from zero.
///
/// There the comparison is `ratio >= row`, with `ratio = accumulated /
/// steps` integer and `accumulated = 100 * n`. Since the row is an integer,
///
/// ```text
/// accumulated / steps >= row   <=>   100 * n >= row * steps
/// ```
///
/// that is `n >= ceil(row * steps / 100)`, which is what is emitted: seven
/// bytes per map and not a single division on the console. The first row is
/// 0 and is not needed.
pub fn enc_step_thresholds(steps: i64) -> Vec<i64> {
    ENC_TABLE[1..]
        .iter()
        .map(|&(row, _)| -((-row * steps).div_euclid(ENC_RATE)))
        .collect()
}

// --- sound ---------------------------------------------------------------------------

/// The index of an effect asked for on the map being compiled —a
/// `PlaySound`'s or, with `from_route`, that of move command 35— with the
/// project's decisions applied: another sample on some map, left out of a
/// map's package, or in the battle's.
///
/// The ones that on some map sound with another sample —map 1's whole
/// thunder— carry another name for the same WAV, so the other maps keep
/// theirs. And the route ones of the `route_left_out` maps do not go into
/// the package: see there.
fn sound_index(ctx: &mut Ctx, sound: Sound, from_route: bool) -> usize {
    let (mut name, volume, tempo, balance) = sound;
    let songs = ctx.songs.as_deref_mut().unwrap();
    let current = songs.current;
    let map_index = ctx.map_index;
    let is_it = |map: i64| matches!(current, Some(Package::Map(c)) if map_index(map) == Some(c));
    let mut in_package = true;
    if current.is_some() {
        for (base, map, alias) in &ctx.sound.per_map {
            if name == *base && is_it(*map) {
                name = alias.clone();
                break;
            }
        }
        if from_route {
            in_package =
                !ctx.sound.route_left_out.iter().any(|(m, which)| {
                    is_it(*m) && which.as_ref().is_none_or(|w| w.contains(&name))
                });
        }
    }
    if current == Some(Package::Battle) {
        // A troop page's: see `troop_in_package`.
        in_package = ctx.sound.troop_in_package.contains(&name);
    }
    songs.sound((name, volume, tempo, balance), in_package)
}

// --- pictures --------------------------------------------------------------------------

/// Whether the parameters of a `ShowPicture` or a `MovePicture` fall within
/// what the console's picture knows how to do.
///
/// The indices come from easyrpg-player's `CommandShowPicture` and
/// `CommandMovePicture`, **not from memory**: the color and the saturation
/// go in 8..11 and the effect mode in 12, which is not what one would
/// guess.
fn picture_fits(p: &[i32]) -> bool {
    p.len() >= 14
        && p[1] == 0 // position by variable
        && p[4] == 0 // attached to the map
        && p[5] == 100 // the zoom
        && p[6] == 0 // translucent
        && p[11] == 100 // the saturation
        && p[12] == 0 // rotate or wave
        && p[8..12].iter().all(|&v| (0..=200).contains(&v))
}

/// The three `Picture` commands, or None if this picture does not fit.
///
/// `ShowPicture` (11110), `MovePicture` (11120) and `ErasePicture` (11130):
/// an image on top of everything, moved and erased. **Since 2026-09-12 one
/// is done**: the "One year previously" picture, and any other that fits the
/// same mold. See the converter's `Pictures` and
/// workflow/tasks/done/show-picture-phase-1.md. The ones that do not fit
/// —27 of the 34 the game has— are still accepted without being done, and
/// what follows applies to those.
///
/// In mode 3 both background layers are taken by the map, so an image on
/// top requires a video decision, not one more opcode. But there is a
/// shortcut the game allows and it is worth noting: **the cutscenes tint to
/// black before showing the picture**, that is the map is invisible while it
/// lasts and the image could borrow a whole layer instead of being
/// composited on top. That does not work for the game's custom systems,
/// which use them over the map, but it does for the pictures.
///
/// How much it unlocks, measured: +8 automatic pages, the three together.
/// The one that matters is the "1 year earlier" one, where the image is the
/// "One year previous" picture: accepting it, the player sees black where
/// the picture goes and the scene continues up to Talan's Pad.
///
/// The ROM carries **a single one** —see `Picture` in [`crate::registry`]—
/// and that is why the three opcodes do not say which: they say what to do
/// to it.
///
/// ```text
/// OP_PICTURE        r, g, b, sat (bytes, 100 neutral): puts it up with
///                   that tone.
/// OP_PICTURE_MOVE   the tone it goes to, and in how many frames (byte). It
///                   does not cut the frame: if the page waits, an OP_DELAY
///                   goes after it, as with `FlashScreen` and the shake.
/// OP_PICTURE_ERASE  takes it down.
/// ```
///
/// **The picture's fade is the tone and not the transparency**, which is
/// what had to be checked: the two `MovePicture`s of the "1 year earlier"
/// page leave `top_trans` at 0 and move (r, g, b) between 0 and 100 with the
/// saturation still at 100. So the image appears **black**, goes up to its
/// color and back to black; on the console that is tinting its fifteen CGRAM
/// entries, which is exactly the math the screen tint already did.
///
/// The parameter indices come from easyrpg-player's `CommandShowPicture` and
/// `CommandMovePicture`, **not from memory**: the two read fourteen and
/// sixteen, and the order is not the one one would guess.
pub fn compile_picture(cmd: &Command, picture: Option<&Picture>) -> Step<Option<Vec<u8>>> {
    let p = &cmd.parameters;
    let Some(picture) = picture else {
        return Ok(None);
    };
    if cmd.code == ERASE_PICTURE {
        if p.is_empty() || !picture.owns(p[0], None) {
            return Ok(None);
        }
        return Ok(Some(vec![OP_PICTURE_ERASE]));
    }
    if !picture_fits(p) {
        return Ok(None);
    }
    let tone = [p[8] as u8, p[9] as u8, p[10] as u8, p[11] as u8];
    if cmd.code == SHOW_PICTURE {
        // `use_transparent_color`: whether the PNG's index 0 is drawn or
        // not. The "1 year earlier" picture has it off, so it is an opaque
        // rectangle; making it transparent would require one palette color
        // less and knowing which was index 0 before reducing.
        if p[7] != 0 || !picture.shows(p[0], &cmd.string, p[2], p[3]) {
            return Ok(None);
        }
        let mut out = vec![OP_PICTURE];
        out.extend(tone);
        return Ok(Some(out));
    }
    // MovePicture: the same picture, in the same place, with another tone.
    // The duration comes in **tenths** —`data.time_left = duration *
    // DEFAULT_FPS / 10`—, which is what had to be looked up: the first one's
    // 35 are three and a half seconds, not half a second.
    if !picture.owns(p[0], Some((p[2], p[3]))) {
        return Ok(None);
    }
    let Some(&tenths) = p.get(14) else {
        return Err(Stop::Fatal(Bad::answer(
            "a MovePicture without its duration",
        )));
    };
    let frames = tenths as i64 * FRAMES_PER_TENTH;
    if !(0..=PICTURE_FRAMES_MAX).contains(&frames) {
        return Ok(None);
    }
    let mut out = vec![OP_PICTURE_MOVE];
    out.extend(tone);
    out.push(frames as u8);
    // `options.wait`: the page waits as long as it lasts, like `FlashScreen`.
    if p.len() > 15 && p[15] != 0 && frames != 0 {
        out.push(OP_DELAY);
        out.extend(word(frames)?);
    }
    Ok(Some(out))
}

// --- counters ----------------------------------------------------------------------------

/// RM2k's screen and the console's: a picture's position is given on the
/// first and drawn on the second.
const RM_SCREEN: (i64, i64) = (320, 240);
const CONSOLE_SCREEN: (i64, i64) = (256, 224);
/// What the ROM draws a counter's digits with: the timer's glyphs, eight by
/// sixteen, two side by side.
const COUNTER_GLYPH: (i64, i64) = (8, 16);

/// The digit a picture's image name is, if it is one: `"0"` to `"9"`.
fn digit_image(name: &str) -> Option<u8> {
    match name.as_bytes() {
        [d @ b'0'..=b'9'] => Some(d - b'0'),
        _ => None,
    }
}

/// Where a counter's number goes on the console's screen: the top-left
/// corner of its two glyphs.
///
/// It comes from the common event's own `ShowPicture`s of a digit, and the
/// declaration is checked against them: **two pictures**, the tens and the
/// ones, each always at the same place of the screen. The number is centered
/// on the midpoint of their two centers —RM2k's position is the center of
/// the image—, scaled from RM2k's screen to the console's like any picture.
/// It is not the images' own boxes: the glyphs are eight wide and the
/// images sixteen, and each glyph centered in its image would leave a gap
/// between the tens and the ones. The counter is a number, so it is drawn as
/// one.
fn counter_place(game: &Game, common: i32) -> Result<(u8, u8)> {
    let whose = format!("the counter of common event {common}");
    let Some(c) = game.common_events.get(&common) else {
        return Err(Bad::answer(format!("{whose}: there is no such common event")));
    };
    let mut places: BTreeMap<i32, (i64, i64)> = BTreeMap::new();
    for cmd in &c.commands {
        let p = &cmd.parameters;
        if cmd.code != SHOW_PICTURE || digit_image(&cmd.string).is_none() {
            continue;
        }
        if p.len() < 4 || p[1] != 0 {
            return Err(Bad::answer(format!(
                "{whose}: picture {} is placed by variable",
                p.first().copied().unwrap_or(0)
            )));
        }
        let here = (p[2] as i64, p[3] as i64);
        if *places.entry(p[0]).or_insert(here) != here {
            return Err(Bad::answer(format!(
                "{whose}: picture {} is shown in two places",
                p[0]
            )));
        }
    }
    if places.len() != 2 {
        return Err(Bad::answer(format!(
            "{whose}: it shows digits on {} pictures, and a counter is two, the tens and the ones",
            places.len()
        )));
    }
    let n = places.len() as i64;
    let cx = places.values().map(|p| p.0).sum::<i64>() / n;
    let cy = places.values().map(|p| p.1).sum::<i64>() / n;
    let x = cx * CONSOLE_SCREEN.0 / RM_SCREEN.0 - COUNTER_GLYPH.0;
    let y = cy * CONSOLE_SCREEN.1 / RM_SCREEN.1 - COUNTER_GLYPH.1 / 2;
    match (u8::try_from(x), u8::try_from(y)) {
        (Ok(x), Ok(y)) => Ok((x, y)),
        _ => Err(Bad::answer(format!("{whose}: it falls off the screen, at ({x}, {y})"))),
    }
}

/// The counter a `ShowPicture` belongs to, if it shows a digit on one of
/// the pictures of a declared counter: the common event's number.
fn counter_of_picture(game: &Game, cmd: &Command) -> Option<i32> {
    if cmd.code != SHOW_PICTURE || digit_image(&cmd.string).is_none() {
        return None;
    }
    let number = *cmd.parameters.first()?;
    game.patches.counters.keys().copied().find(|common| {
        game.common_events.get(common).is_some_and(|c| {
            c.commands.iter().any(|d| {
                d.code == SHOW_PICTURE
                    && digit_image(&d.string).is_some()
                    && d.parameters.first() == Some(&number)
            })
        })
    })
}

/// A counter: a common event the project declares as the display of a
/// variable —`counters` in the request—, as `OP_COUNTER`.
///
/// What such a common event does in RM2k is draw the variable's value with
/// two pictures whose images are digits, and to choose which image it
/// branches on every value: ten `ConditionalBranch` for the tens and ten for
/// the ones, the ones usually in a second common event. Pasted in place,
/// like every `CallEvent`, that chain costs its whole size **at each call**,
/// and the game that brought this calls its counter after every jump: 31
/// calls on one map. So the project says what the chain means, and the ROM
/// does it in one opcode: the value clamped to 0..99, the tens erased under
/// ten. What the declaration takes on trust is that the chain means that;
/// what it checks is where it draws, in [`counter_place`].
///
/// It is also what a `ShowPicture` of a digit on one of its pictures
/// compiles to, outside the common event: a page that sets the counter up
/// by hand —the variable just set, and the two pictures shown with the
/// digits of that value— **shows the counter**, the variable's value and not
/// the image's. It is the same only as long as the page shows the digits of
/// the value it just set, and that is also taken on trust.
///
/// The rest of the pictures' life is the ROM's: they go away when the map
/// changes, like every RM2k 2000 picture —`erase_on_map_change`—.
fn compile_counter(ctx: &Ctx, common: i32) -> Step<Vec<u8>> {
    let variable = ctx.game.patches.counters[&common];
    let slot = ctx.indices.variable_slot(variable as i64)?;
    let (x, y) = counter_place(ctx.game, common)?;
    Ok(vec![OP_COUNTER, slot, x, y])
}

// --- one command -------------------------------------------------------------------------

/// The size of an opcode that has a fixed one.
pub fn size_of(op: u8) -> usize {
    OPCODE_SIZE
        .iter()
        .find(|(o, _)| *o == op)
        .map(|(_, s)| *s)
        .unwrap()
}

/// How many bytes the instruction at `code[at]` takes, the variable-size
/// ones included.
pub fn instruction_size(code: &[u8], at: usize) -> usize {
    let op = code[at];
    match VARIABLE_SIZE.iter().find(|(o, ..)| *o == op) {
        Some(&(_, base, count, entry)) => base + entry * code[at + count] as usize,
        None => size_of(op),
    }
}

/// The offset of each instruction of already compiled code.
pub fn instructions(code: &[u8]) -> impl Iterator<Item = usize> + '_ {
    let mut at = 0;
    std::iter::from_fn(move || {
        (at < code.len()).then(|| {
            let here = at;
            at += instruction_size(code, here);
            here
        })
    })
}

/// The `VAR_REFRESH` bit for a write to variable `number`.
///
/// It is `SetNeedRefreshForVarChange` resolved at compile time: only the
/// variables some page condition of the map looks at ask for a refresh.
/// **Without the map it is always asked for**, and after leaving it too,
/// which is what the port did before this and the only honest thing when it
/// is not known who looks at what.
fn refresh(number: i64, map_events: Option<&MapEvents>) -> i64 {
    match map_events.and_then(|m| m.watched.as_ref()) {
        None => VAR_REFRESH,
        Some(w) => {
            if i32::try_from(number).is_ok_and(|n| w.contains(&n)) {
                VAR_REFRESH
            } else {
                0
            }
        }
    }
}

/// The target byte of a route, a flash, a placement: 0 the hero, and an
/// event its index plus one. Without the map there is no way to translate
/// the id, and a vehicle or an event that does not exist does not compile.
fn target_of(who: i64, map_events: Option<&MapEvents>) -> Step<u8> {
    if who == ROUTE_HERO {
        return Ok(0);
    }
    let Some(me) = map_events else {
        return cannot();
    };
    match me.route_target(who) {
        Some(t) => byte(t as i64),
        None => cannot(),
    }
}

/// One command, as its opcodes. The ones built from several —branches,
/// choices, battles, the inn, calls— are the page's.
///
/// One opcode per command, with the operands already resolved: the ROM does
/// not look at the LCF again nor knows its numbers. **The numbers and
/// layouts are in `tools/snes/protocol/events.toml`**, not here: what each
/// arm says is what there is to know about each one that a declaration
/// cannot say.
pub fn compile_command(
    ctx: &mut Ctx,
    cmd: &Command,
    extra: &[String],
    map_events: Option<&MapEvents>,
) -> Step<Vec<u8>> {
    let p = &cmd.parameters;
    let n = p.len();
    let q = |i: usize| -> i64 { p[i] as i64 };
    if cmd.code == END || IGNORABLE.contains(&cmd.code) {
        return Ok(vec![]);
    }
    match cmd.code {
        PLAY_SOUND => {
            // PlaySound plays an effect: a door, a hit, Talan's Insta-Shave.
            // It sounds since 2026-09-11 (see OP_SOUND, below); until then it
            // was accepted without playing it, and it was the cheapest debt of
            // all the ones accepted undone: **it does not show**. The screen
            // being compared is exactly the same with and without sound.
            //
            // What made it costly was ARAM. The effects go in each map's
            // audio package, together with its songs —`package_load`, in
            // tools/runtime/audio_package.s—, with the same per-pack budget
            // as the music's samples:
            // `workflow/decisiones/un-solo-banco-de-muestras.md`. One that
            // does not fit in its pack does not sound.
            //
            // How much it unlocks, measured and not assumed: **+10
            // action-key pages and +6 automatic ones**. It is much less than
            // it seems: `PlaySound` is the command that cuts *first* in 349
            // pages, but almost all of them are also cut by something else:
            // the command that cuts first is not the only one that cuts, and
            // counting by it promises more than it unlocks.
            //
            // What it does unlock is concrete: the Insta-Shave on Talan's pad
            // plays four effects before its message, so without this that
            // branch does not run.
            //
            // **Since 2026-09-11 they sound**: `PlaySound` compiles to
            // OP_SOUND with the index of its entry in `Songs::sounds`, and the
            // ROM's table says with which sample, what pitch, what volume on
            // each side and how many frames. The samples go in ARAM next to
            // the music's bank, in what it leaves free: see `effects.rs` in
            // `rm2k-snes-audio`. They play on voice 7, which is stolen from
            // the music while they last. They cost no tick, as in RM2k.
            //
            // OP_SOUND: index (word)
            //
            // Without a song registry it is accepted and not done, as
            // before. An empty name is "(OFF)": it plays nothing.
            if ctx.songs.is_none() || cmd.string.is_empty() || n < 3 {
                return Ok(vec![]);
            }
            let k = sound_index(ctx, (cmd.string.clone(), p[0], p[1], p[2]), false);
            let mut out = vec![OP_SOUND];
            out.extend(usize_word(k)?);
            Ok(out)
        }
        WEATHER_EFFECTS => {
            // WeatherEffects turns the rain on or off. It is accepted without
            // drawing it, and the debt is one of the big ones, so it is
            // spelled out.
            //
            // **In mode 3 there is no layer left to put it on.** BG1 is the
            // map's eight bits and BG2 the upper layer plus the message
            // window; there is no third. Not with objects either: RM2k's rain
            // is up to 100 streaks of 6x24 spread across the whole screen,
            // and the console draws 34 sprite tiles per line —a 32x32 object
            // takes four—, so a rain that covers the screen blows the budget
            // on almost every line.
            //
            // And even if it fit: each drop has its own transparency —`alpha
            // = min((5 + power) * t, 255)` in `Weather::DrawParticles`— and
            // the console has a single color operation for the whole screen,
            // not one per object. The positions also come from a random
            // number generator that would have to be reproduced.
            //
            // What is lost, measured on an EasyRPG capture of the opening:
            // thin diagonal streaks 24 pixels tall, which between two
            // consecutive frames move 3.9% of the screen. They show mostly in
            // the dark areas.
            //
            // It is accepted because **it is the only thing blocking the
            // opening cutscene**. Without this the ROM does not start the
            // story; with it, it starts, without rain.
            //
            // **Since 2026-09-11 the rain is drawn**: see OP_WEATHER, which
            // carries the type and the power, and the rain's model next to
            // `WEATHER_RAIN` in the converter's events.py. Snow, fog and
            // sandstorm are still not drawn, and they turn the rain off.
            //
            // OP_WEATHER: type, power
            if n < 2 {
                return cannot();
            }
            Ok(vec![
                OP_WEATHER,
                (q(0) & 0xFF) as u8,
                q(1).clamp(0, 2) as u8,
            ])
        }
        OPEN_SHOP => {
            // The shop: `OpenShop`. Forty-three in the game, none with the
            // "bought"/"did not buy" branches. From the night of 2026-09-10
            // to the 11th it was accepted without opening anything, so that
            // the Lashe City Interiors vendors —EV0021 and EV0023— would
            // answer; since the 11th it opens the real shop.
            //
            // It compiles to OP_SHOP with the type —0 buys and sells, 1 only
            // buys, 2 only sells—, the message set and the list of what it
            // sells, by item number. It is variable-length, like OP_CHOICE.
            // Like saving, the screen opens inside the interpreter and costs
            // no tick: the map does not run while it is shown. The "bought"
            // and "did not buy" branches do not compile; none of the game's
            // 43 shops uses them.
            //
            // OP_SHOP: type, set, how many (bytes), and two bytes per item
            if n < 4 {
                return cannot();
            }
            if q(2) != 0 {
                return cannot();
            }
            let sells: Vec<i64> = p[4..]
                .iter()
                .map(|&i| i as i64)
                .filter(|&i| 0 < i && i < ITEMS_N)
                .collect();
            if sells.len() > 255 || !(0..=2).contains(&q(0)) || !(0..=2).contains(&q(1)) {
                return cannot();
            }
            let mut out = vec![OP_SHOP, q(0) as u8, q(1) as u8, sells.len() as u8];
            for i in sells {
                out.extend(word(i)?);
            }
            Ok(out)
        }
        FULL_HEAL => {
            // HP, SP and states. Until 2026-09-12 outside battle they never
            // went down —measured over the 328 maps: the 11 `ChangeHP`s add,
            // the 16 `ChangeCondition`s remove a state and the 54 `FullHeal`s
            // fill up— so the three commands compiled to nothing and it was
            // exact. **It stopped being so the next day**, with the battle:
            // HP and SP became state, in `FAR_HP` and `FAR_SP`, and a
            // `FullHeal` that does not heal leaves the party down. That
            // blocked the demo until 2026-09-19, because the battle on map 9
            // is lost by script and its defeat handler is precisely a
            // `FullHeal`.
            //
            // Today `FullHeal` and the `ChangeHP` that adds are both OP_HEAL,
            // and the amount tells them apart: at 0 it is this one. The one
            // that subtracts still does not compile.
            //
            // OP_HEAL: actor (byte), amount (word). Actor 0 is the whole
            // party and amount 0 is `FullHeal`, that is HP and SP to the
            // maximum.
            if n < 2 {
                return cannot();
            }
            Ok(vec![OP_HEAL, target_actor(p)?, 0, 0])
        }
        CHANGE_HP => {
            // [type, id, subtracts, amount by variable, amount, lethal]. The
            // one that adds shares OP_HEAL with `FullHeal`, with the amount
            // set: it is `Game_Battler::ChangeHp` (`game_battler.cpp:480`),
            // which does not touch the downed and caps at the maximum
            // —`SetHp`—. It does not touch SP.
            //
            // An amount of zero does nothing in RM2k, and here it is not
            // emitted: in OP_HEAL zero means `FullHeal`.
            //
            // The 11 that add outside battle are constants —seven of 1 to the
            // party, four of 300 and 999 to one actor—.
            //
            // **The rest is OP_ACTOR**, since 2026-09-30: the one that
            // subtracts —`Sacrifice` and `LifeForStrength` take 999 from
            // Talan in battle, lethal— and the one by a variable
            // —`ResetAfterBattles` gives Talan back the HP he had—. Without
            // `lethal` a loss leaves the actor at 1. In battle it lands on
            // the battle's HP: see `ba_sync_out` in
            // tools/runtime/battle_troop.s. What it does not do is
            // `CheckGameOver` on the map, which no page of the game needs.
            if n < 6 {
                return cannot();
            }
            if q(3) == 0 && q(2) == 0 {
                if !(0..=0xFFFF).contains(&q(4)) {
                    return cannot();
                }
                if q(4) == 0 {
                    return Ok(vec![]);
                }
                let mut out = vec![OP_HEAL, target_actor(p)?];
                out.extend(word(q(4))?);
                return Ok(out);
            }
            let mut what = 0;
            if q(5) != 0 {
                what |= ACT_LETHAL;
            }
            actor_change(ctx, p, what)
        }
        CHANGE_SP => {
            // `ChangeSP`: [type, id, subtracts, amount by variable, amount].
            // It is `SetSp(GetSp() + amount)`, between zero and the maximum.
            // The game's are `ResetAfterBattles`', which gives Talan back his
            // SP by a variable. OP_ACTOR with `ACT_SP`.
            if n < 5 {
                return cannot();
            }
            actor_change(ctx, p, ACT_SP)
        }
        CHANGE_SKILLS => {
            // [type, id, forgets, skill by variable, skill]. It is easyrpg's
            // `CommandChangeSkills`: `LearnSkill` or `UnlearnSkill` on each
            // actor of the target, without asking for the page refresh —it
            // does not ask for it there either— and without a message: the
            // "learned such a thing" is written by the page with a
            // `ShowMessage`.
            //
            // The game's 898 are all fixed actor and constant skill, so the
            // operand is directly the bit: see `skills` in
            // [`crate::indices`]. The party, the actor by variable and the
            // skill by variable do not compile.
            //
            // OP_SKILL: pair slot (word), learns (byte: 1 learns, 0 forgets)
            if n < 5 {
                return cannot();
            }
            if q(0) != 1 {
                return cannot();
            }
            if q(3) != 0 {
                return cannot();
            }
            let slot = ctx.indices.skill_slot(q(1), q(4))?;
            let mut out = vec![OP_SKILL];
            out.extend(word(slot)?);
            out.push(if q(2) != 0 { 0 } else { 1 });
            Ok(out)
        }
        CHANGE_EQUIPMENT => {
            // [type, id, operation, a, b]. Operation 1 is unequipping slot
            // `a` —0 to 4, weapon to accessory; 5 is everything— and it is
            // `Game_Actor::ChangeEquipment(slot, 0)`: the slot is left empty
            // and what it had goes back to the inventory, capped at
            // ITEM_MAX. It does not ask for the refresh either:
            // `CommandChangeEquipment` does not ask for it.
            //
            // The 35 the game runs outside battle all unequip a slot; the 560
            // that equip belong to the troops. When this was written the port
            // did not run troop pages; it does since 2026-09-21, but equipping
            // still does not compile. Unequipping everything does not either:
            // nobody uses it.
            if n < 4 {
                return cannot();
            }
            if q(2) != 1 {
                return cannot();
            }
            if !(0..EQUIPMENT_SLOTS).contains(&q(3)) {
                return cannot();
            }
            let actor = target_actor(p)?;
            if actor != 0 && !ctx.game.actors.contains_key(&(actor as i32)) {
                return cannot();
            }
            Ok(vec![OP_EQUIPMENT, actor, q(3) as u8])
        }
        // `CommandGameOver`: the Game Over screen and, on pressing, the
        // title. It is the same as losing a battle without a handler —see
        // `BATTLE_LOSE`—: tools/runtime/game_over.s.
        GAME_OVER => Ok(vec![OP_GAME_OVER]),
        // `ReturntoTitleScreen`: the same without the screen, that is going
        // back to boot, which in `release` is the title screen. The end of
        // the demo asks for it, in map 66's fork (`rom/parches/manual/`).
        // Until 2026-09-28 it shared the opcode with `GameOver`, when neither
        // of the two drew anything.
        RETURN_TO_TITLE => Ok(vec![OP_RETURN_TO_TITLE]),
        CHANGE_CONDITION => {
            // `ChangeCondition` that removes a state compiles to nothing, and
            // that is **not** debt: outside battle states do not exist —the
            // battle sets them up and throws them away— so there is nothing
            // to remove. The one that sets a state still does not compile.
            //
            // **Except death**, since 2026-09-30: an actor with no HP is one
            // with the death state, inside battle and out, and removing it
            // gets it up with 1 —the `SetHp(1)` of `RemoveStates`—. It is
            // OP_ACTOR with `ACT_REVIVE`, on the actor or the party. The
            // characters' systems use it in battle, `Sacrifice` and
            // `Inscribe`, always on the party.
            //
            // [type, id, removes, state]
            if n < 4 || q(2) != 1 {
                return cannot();
            }
            if q(3) == DEATH_STATE {
                return Ok(vec![OP_ACTOR, target_actor(p)?, ACT_REVIVE, 0, 0]);
            }
            Ok(vec![])
        }
        KEY_INPUT_PROC => {
            // `KeyInputProc`: variable slot (byte) and which keys it looks at
            // (byte).
            //
            // In RM2k it is `CommandKeyInputProc` plus the piece of
            // `Game_Interpreter::Update` that handles it while it waits, and
            // the value it stores comes from `CheckInput`: 1 down, 2 left, 3
            // right, 4 up, 5 the action key, 6 cancel. They are checked from
            // highest to lowest, which is what the comment "RPG processes
            // keys from highest variable value to lowest" says.
            //
            // The two forms are different programs and that is why they carry
            // a flag:
            //
            //   no wait      reads what is pressed **now** —`Input::IsPressed`—
            //                and the page continues on the same frame. It is
            //                the car's steering wheel.
            //   with wait    the page stops here until there is an **edge**
            //                —`IsTriggered`— of any of the requested keys.
            //
            // The waiting one is emitted **twice**, the first with
            // `KEY_START`: that one sets the variable to zero, eats whatever
            // edge there was and returns control without looking at anything.
            // It is RPG_RT's `Input::ResetTriggerKeys()`, which exists so the
            // command does not eat the same key that just closed a message
            // —and in the game the 23 waits come right after a `ShowMessage`,
            // so without it the sign would skip past—. Two opcodes and not a
            // state byte because the interpreter has nowhere to keep it: the
            // one that waits **rewinds its own cursor** and runs again frame
            // after frame, so it cannot tell the first turn from the others.
            //
            // [variable, wait, the four directions, the action one, cancel].
            // The game's 32 occurrences have the five and no more: with six or
            // more RM2k 1.50 goes on to look at each direction separately,
            // which is another program, so the length is required instead of
            // assumed.
            if n != 5 {
                return cannot();
            }
            let flags = (if q(1) != 0 { KEY_WAIT } else { 0 })
                | (if q(2) != 0 { KEY_DIRS } else { 0 })
                | (if q(3) != 0 { KEY_DECISION } else { 0 })
                | (if q(4) != 0 { KEY_CANCEL } else { 0 });
            if flags & (KEY_DIRS | KEY_DECISION | KEY_CANCEL) == 0 {
                // With no key asked for, the waiting form never comes out.
                return cannot();
            }
            if q(1) == 0 {
                // The form that does not wait: it reads what is pressed and
                // the page continues on the same frame. In the game there are
                // four pages, the steering wheel of the car chase
                // —`RaceController2` on maps 49, 51, 52 and 54—, which also
                // forces the hero's route on every frame.
                //
                // It was not accepted until 2026-09-27, first because of the
                // Python reference —which did not know that a forced route
                // rules over the pad— and then, when the reference went away,
                // because nobody had looked at it again. On accepting it two
                // things of the ROM that no compiled page exercised showed up:
                // that `op_key` looked at edges in this form too —see
                // `key_value` in the converter's events.py— and that a
                // `Teleport` from a parallel page was not handled with the
                // foreground idle —see the main loop—.
                // `test_recorrido_carrera_golden.py` enforces it.
                let slot = ctx.indices.variable_slot(q(0))?;
                return Ok(vec![
                    OP_KEY,
                    slot,
                    (flags | refresh(q(0), map_events)) as u8,
                ]);
            }
            // The one that waits goes twice: the first eats the edge that
            // closed the message before it.
            //
            // **The wait is done with all three: the D-pad, the action key
            // and cancel**, since 2026-09-13. Until that day only the action
            // one counted, and the written reason was the **harness**'s and
            // not the ROM's: the suite held a direction from boot and pressed
            // A on noted frames, so a D-pad edge in the middle of a scene
            // could not be produced by any case, and modeling it anyway would
            // have been writing a path nothing runs.
            //
            // That reason stopped holding with `rom/pruebas/arnes/recorrido.py`,
            // which plays the real game and can press any button on any
            // frame, and with `--tocar` of both halves of the suite, which
            // presses a direction on a noted frame the way A was already
            // pressed.
            //
            // What it unlocks, measured: the two pages of `(151, 1, 1, 1, 1)`
            // —the one that waits for all three— and, together with variable
            // 5's slot, the one of the stones minigame engine on map 11, which
            // is `(8, 1, 1, 0, 0)`: without this no stone can be thrown.
            let slot = ctx.indices.variable_slot(q(0))?;
            let flags = flags | refresh(q(0), map_events);
            Ok(vec![
                OP_KEY,
                slot,
                (flags | KEY_START) as u8,
                OP_KEY,
                slot,
                flags as u8,
            ])
        }
        CHANGE_SPRITE_ASSOCIATION => {
            // `ChangeSpriteAssociation`: changes the CharSet of an **actor**,
            // not an event. In RM2k it is `actor->SetSprite(...)` plus a
            // `ResetGraphic()` on `Game_Player`, so it shows right away if
            // that actor is leading and stays stored for when it leads.
            //
            // The parameters are [actor, index within the CharSet,
            // transparent] and the name goes in `string`. A fourth parameter
            // is the bitfield that says which of the three come from a
            // variable —`ValueOrVariableBitfield(com, 3, ...)`—: the game
            // does not use it in any of its 212 occurrences and it is
            // rejected here, as always.
            //
            // OP_ACTOR_SPRITE: actor (byte) and which graphic of the map's
            // table (byte). It is the same as move command 34 but on an
            // **actor**, and the two differences come from there:
            //
            // * **It survives the map change**, because in RM2k it belongs to
            //   the actor and not to `Game_Player`. That is why its index
            //   comes from the slots the graphics table of every map reserves
            //   for it —see `associations` in [`crate::indices`]— and not
            //   from the map's free numbering.
            // * **It is stored per actor and shows only if that actor
            //   leads.** The one that does not lead is not drawn, so the
            //   change stays waiting; the ROM resolves it in
            //   `pick_hero_graphic`, which is the only one that decides what
            //   the hero is drawn with.
            //
            // And one thing that **is not** done: if the graphic is not in
            // the map's sprite bank, the actor keeps its own from the LDB
            // instead of stopping being drawn. It is the difference with
            // command 34, which there hides the row, and it is chosen: here
            // the target is the hero, and an invisible hero on a map where
            // the CharSet did not fit is worse than a hero with the old
            // graphic.
            if n != 3 {
                // With four it is the bitfield of "this comes from a
                // variable", which the game never uses.
                return cannot();
            }
            if q(2) != 0 {
                // Transparent: the console does not fade a sprite without
                // color math.
                return cannot();
            }
            if !(0 < q(0) && q(0) < 256) {
                return cannot();
            }
            let Some(graphics) = ctx.graphics.as_deref_mut() else {
                return cannot();
            };
            let chosen = graphics.index(&cmd.string, p[1]);
            if chosen > GRAPHICS_MAX {
                return cannot();
            }
            Ok(vec![OP_ACTOR_SPRITE, q(0) as u8, chosen as u8])
        }
        CHANGE_SAVE_ACCESS | CHANGE_MENU_ACCESS | CHANGE_ESCAPE_ACCESS => {
            // `ChangeSaveAccess`, `ChangeMainMenuAccess` and
            // `ChangeEscapeAccess`, since there is a pause menu: **the bit**
            // of the permission —see `ACCESS_BIT`— and whether it stays
            // allowed. The ROM stores it in `FAR_ACCESS`. Saving from the save
            // point does not look at it, like `OpenSaveMenu` in RM2k.
            //
            // `ChangeEscapeAccess` is the permission to escape from a battle,
            // and it is stored without being read: the battle looks at the
            // escape, and that belongs to someone else. It is here anyway
            // because it is what unlocks the most for what a bit costs —**30
            // of the game's 39 pages with `EnemyEncounter` that do not compile
            // have it ahead**—, and because a command accepted without being
            // done would be a lie: RM2k stores it in `Game_System` and it
            // travels in the save, and here too.
            //
            // OP_ACCESS: the bit in FAR_ACCESS (byte), allowed (byte)
            if n == 0 {
                return cannot();
            }
            let which = match cmd.code {
                CHANGE_SAVE_ACCESS => 0,
                CHANGE_MENU_ACCESS => 1,
                _ => 2,
            };
            Ok(vec![
                OP_ACCESS,
                ACCESS_BIT[which],
                if q(0) != 0 { 1 } else { 0 },
            ])
        }
        CHANGE_SCREEN_TRANSITIONS => {
            // `ChangeScreenTransitions` (10690) changes the teleport's
            // transition from then on: `[which, transition]`, with which 0
            // the teleport's erase and 1 its show —2 to 5 are the battle's—
            // and the transition an index into `Game_System::GetTransition`'s
            // `fades` table. The game uses it in Boss Wick's hideout: zoom
            // (16) to go to the vidcasts, mosaic (17) inside, and fade (0) on
            // the way back. It is state that crosses the teleport, and in
            // RM2k it travels in the save; here it does not —see
            // `TRANSITION_ERASE` in tools/runtime/far_ram.s—.
            //
            // The ROM does two: **the mosaic**, with the PPU's MOSAIC register
            // tied to the brightness ramp —like the battle's,
            // `battle_fade.s`, and for the same reason: the map load has to
            // fall inside the black—, and **the fade**, which is what goes
            // for the ones the console does not do (the zoom is mode 7, and
            // the map is in mode 3): taro decided it on 2026-09-26. See
            // workflow/divergencias/las-transiciones-del-teletransporte.md.
            //
            // And **the cut** (19) for erasing: the screen to black in one
            // frame —`TransitionCutOut`, which `Transition::GetDefaultFrames`
            // makes last 1— and the new map loaded there; the way back is
            // whatever the show says. Eisen's story (95 ev55) asks for it and,
            // for "none" (20), 93 ev4: "none" compiles **to the cut**, and it
            // is a divergence. In RM2k erasing with "none" does not touch the
            // screen, so the fade back fades from the old map to the new one;
            // the console has nothing to blend two frames with, and loading
            // the map requires forced blanking: the closest thing is one
            // frame of black. See
            // workflow/divergencias/las-transiciones-del-teletransporte.md.
            //
            // The cut and "none" for **showing** do not compile: no ROM map
            // uses them, and with nobody running them they would be a path no
            // test walks. The battle's do not either: the ROM always uses the
            // database's.
            if n < 2 {
                return cannot();
            }
            let (which, rm2k) = (q(0), q(1));
            if which != TRANSITION_ERASE && which != TRANSITION_SHOW {
                // The battle's: the ROM always uses the database's.
                return cannot();
            }
            if which == TRANSITION_ERASE && RM2K_CUT_TRANSITIONS.contains(&rm2k) {
                return Ok(vec![OP_TRANSITION, which as u8, TRANSITION_CUT]);
            }
            if RM2K_CUT_TRANSITIONS.contains(&rm2k) {
                return cannot();
            }
            let kind = if rm2k == RM2K_TRANSITION_MOSAIC {
                TRANSITION_MOSAIC
            } else {
                TRANSITION_FADE
            };
            Ok(vec![OP_TRANSITION, which as u8, kind])
        }
        CHANGE_ITEMS => {
            // The inventory, since the night of 2026-09-10: one byte per LDB
            // item in far RAM —`FAR_ITEMS`, right after the variables—,
            // indexed by the RM2k number, and `ChangeItems` compiles to
            // OP_ITEM with the item and how much is added, signed. The count
            // stays in [0, ITEM_MAX], which is `Game_Party::AddItem` with
            // RM2k's cap. The game uses it 509 times, always with constant
            // item and quantity: the item by variable does not compile. With
            // this the page condition by item is evaluated for real
            // —`GetItemCount(id) > 0`, without equipment yet— and stops being
            // "never active". Changing an item asks for the page refresh.
            //
            // OP_ITEM: item (word), delta (signed byte)
            //
            // [add or remove, item by constant or variable, item, amount by
            // constant or variable, amount].
            if n < 5 {
                return cannot();
            }
            if q(1) != 0 || q(3) != 0 {
                return cannot();
            }
            if !(1..ITEMS_N).contains(&q(2)) {
                return cannot();
            }
            let delta = if q(0) != 0 { -q(4) } else { q(4) };
            if !(-128..=127).contains(&delta) {
                return cannot();
            }
            let mut out = vec![OP_ITEM];
            out.extend(word(q(2))?);
            out.push((delta & 0xFF) as u8);
            Ok(out)
        }
        CHANGE_GOLD => {
            // `OperateValue(operation, type, value)`: the operation is 0 add
            // and 1 subtract, and the type 0 constant and 1 "the value is in
            // a variable". Without variables, the latter cannot be done.
            //
            // OP_GOLD: sign (byte: 0 adds, 1 subtracts) and a 24-bit amount.
            // It goes in three bytes because RM2k's cap is 999999 and the
            // game uses the whole value: there is a command that gives
            // exactly that.
            //
            // RM2k's gold cap does not travel: the ROM clamps to [0,
            // GOLD_MAX] like `Game_Party::GainGold`, which clamps to
            // `MaxGoldValue()`. There is still nowhere to show it —the menu
            // does not exist— but there is who asks for it: the gold branch
            // of `ConditionalBranch`.
            if n < 3 {
                return cannot();
            }
            if q(1) != 0 {
                return cannot();
            }
            let amount = q(2);
            if !(0..=0xFFFFFF).contains(&amount) {
                return cannot();
            }
            Ok(vec![
                OP_GOLD,
                if q(0) != 0 { 1 } else { 0 },
                (amount & 0xFF) as u8,
                ((amount >> 8) & 0xFF) as u8,
                ((amount >> 16) & 0xFF) as u8,
            ])
        }
        PLAY_BGM => {
            // PlayBGM changes the song that plays, and it is no longer one of
            // the accepted undone: it is done. Each map uploads its audio
            // package to ARAM, with the songs its pages can turn on
            // —`package_load`, in tools/runtime/audio_package.s—, and each
            // sample's budget is that of its worst pack: see
            // `workflow/decisiones/un-solo-banco-de-muestras.md`.
            //
            // OP_BGM: the song's index in `Songs` (byte). The ROM plays the
            // ones it carried —the first `SONG_TOTAL`— and with any other it
            // does nothing. See `Songs`.
            //
            // Without a song registry it is accepted and not done, which is
            // what this repo did with PlayBGM from the start. With a registry
            // the index is emitted and the ROM plays the song if it got to
            // carry it.
            let Some(songs) = ctx.songs.as_deref_mut() else {
                return Ok(vec![]);
            };
            if cmd.string.is_empty() {
                return Ok(vec![]);
            }
            Ok(vec![OP_BGM, (songs.index(&cmd.string) & 0xFF) as u8])
        }
        PAN_SCREEN => {
            // Moving the camera without the hero: `CommandPanScreen`.
            // Locking and unlocking the camera are used by no page of the
            // game, so they do not compile: modeling them with nothing
            // exercising them is making up a difference. Moving and resetting
            // do, which are the 133 there are.
            //
            // OP_PAN: operation (byte: PAN_SHIFT or PAN_RETURN), how far the
            // destination moves in x and in y (a signed word each, in 1/16 of
            // a pixel), the step per frame (byte) and whether the page waits
            // (byte).
            //
            // The direction and the distance come resolved to a signed
            // offset, and the speed to its step: they are fixed computations
            // and the converter does them once. What **cannot** be resolved
            // here are the frames the page waits: they come from what the pan
            // has left when the command runs, and with one still in progress
            // that is not what this command asked for. See `GetPanWait` and
            // `CommandPanScreen`'s comment on the maximum.
            if n < 5 || !(q(0) == PAN_SHIFT || q(0) == PAN_RETURN) {
                return cannot();
            }
            if q(0) == PAN_SHIFT && !(0..=3).contains(&q(1)) {
                return cannot();
            }
            if !(0..=255).contains(&q(2)) {
                return cannot();
            }
            let (mut dx, mut dy) = if q(0) == PAN_RETURN {
                (0, 0)
            } else {
                // Which way the camera moves for each direction —up, right,
                // down, left—, in (dx, dy) per unit.
                [(0, -1), (1, 0), (0, 1), (-1, 0)][q(1) as usize]
            };
            dx *= q(2) * PAN_UNIT;
            dy *= q(2) * PAN_UNIT;
            if !((-0x8000..0x8000).contains(&dx) && (-0x8000..0x8000).contains(&dy)) {
                return cannot();
            }
            // How far the camera moves per frame, in 1/16 of a pixel. It is
            // `data()->pan_speed = 2 << speed` from `Game_Player::StartPan`,
            // with the speed clamped between 1 and 6 as `CommandPanScreen`
            // does. The game uses 2 to 6: from half a pixel per frame to
            // eight.
            let step = 2i64 << q(3).clamp(1, 6);
            Ok(vec![
                OP_PAN,
                q(0) as u8,
                (dx & 0xFF) as u8,
                ((dx >> 8) & 0xFF) as u8,
                (dy & 0xFF) as u8,
                ((dy >> 8) & 0xFF) as u8,
                byte(step)?,
                if q(4) != 0 { 1 } else { 0 },
            ])
        }
        FADE_OUT_BGM => {
            // Fading out the song that is playing, over so many milliseconds.
            // `Game_Interpreter::CommandFadeOutBGM` calls `BgmFade` and
            // returns **true** on the same frame: it does not block the page,
            // so it costs no frame and moves nothing of what is compared.
            //
            // OP_FADE_BGM: step (word): how much the song's volume goes down
            // per frame, in 1/65536 of whatever was playing.
            //
            // The step goes and not the milliseconds RM2k brings because the
            // 65816 does not divide without hardware and the math is always
            // the same: `ceil(65536 / frames)`. It is the same kind of number
            // as a teleport's map index —resolved by the converter so the ROM
            // does not look at it again—. The hardware divider is eight bits
            // —the 5000 ms of map 3's door are 300 frames and do not fit—.
            //
            // The level starts at 65535 and goes down by the step; it is
            // rounded up so the fade ends **within** the frames it asks for
            // and not one after.
            if n == 0 || q(0) < 0 {
                return cannot();
            }
            let frames = (q(0) * FRAMES_PER_SECOND / 1000).max(1);
            let step = (-((-0x10000i64).div_euclid(frames))).min(0xFFFF);
            let mut out = vec![OP_FADE_BGM];
            out.extend(word(step)?);
            Ok(out)
        }
        // Opening the save menu: the slot screen, which freezes the game while
        // it is shown and costs no tick.
        //
        // OP_SAVE: no operands: the save to the cartridge's SRAM. It is
        // `OpenSaveMenu`, but without a menu: there is a single slot and the
        // event overwrites it. What is saved is said by `save_table` in
        // tools/runtime/bank1.s, which is the only place where it is written.
        // It costs no frame: in RM2k the menu blocks, and here there is
        // nothing to look at.
        OPEN_SAVE_MENU => Ok(vec![OP_SAVE]),
        SHOW_PICTURE | MOVE_PICTURE | ERASE_PICTURE => {
            if let Some(common) = counter_of_picture(ctx.game, cmd) {
                return compile_counter(ctx, common);
            }
            // None is "this picture does not fit the model": it is accepted
            // without being done, which is what the three did until
            // 2026-09-12. Cutting the page would take away from the game the
            // eight that compile today because of it.
            Ok(compile_picture(cmd, ctx.picture)?.unwrap_or_default())
        }
        // `ChangeSystemBGM` (10660): changes the song the system uses for
        // fighting, for winning, for the inn. The game uses it **130 times on
        // 25 maps** and always in pairs —0 and 1, that is `battle_music` and
        // `battle_end_music`—: each zone has its battle music.
        //
        // It is accepted without being done, and the debt is concrete: **a
        // battle on those maps plays the LDB's song instead of the zone's**.
        // It is not "it does not sound": what sounds is the one
        // `battle_audio` brings from the database, which is the one the map's
        // audio package already carries, so nothing goes silent and nothing
        // asks for a sample that is not there. And it does not change a
        // pixel, so the suite measures the same with and without this.
        //
        // How much it unlocks, measured over the game's 5603 triggerable
        // pages: **+24**. Doing it for real is not this command but an audio
        // feature: the system song would become state that travels in the
        // save, and the songs those 130 occurrences name would have to fit in
        // their maps' audio packages. Today the worst package is 54945 of
        // 63831 B of ARAM; adding a battle song to twenty-five maps requires
        // room in those packages: see
        // workflow/decisiones/un-solo-banco-de-muestras.md.
        //
        // `ChangeHeroTitle` (10620): an actor's "title", which in RM2k is the
        // text the status screen shows under the name. Eight occurrences in
        // the whole game and **all on Talan**: "Fugitive", "Limping",
        // "Defender".
        //
        // It is accepted without being done because **this port does not show
        // the title anywhere**: the converter emits an actor's name and
        // starting equipment, and nothing else —there is no status screen—.
        // So doing it for real is not this command but that screen, and while
        // it does not exist the data would have nowhere to show. Storing it
        // anyway would be state that travels in the save without anyone
        // reading it.
        //
        // What it unlocks: **+5 pages**, and among them map 19's
        // `RunDirectorScene`, which is automatic. With it not compiling, the
        // director's scene did not start: taro reached the office on
        // 2026-09-13, the speech ran whole, the teleport back worked, and then
        // nothing else happened.
        CHANGE_SYSTEM_BGM | CHANGE_HERO_TITLE => Ok(vec![]),
        CHANGE_ENCOUNTER_STEPS => {
            // `ChangeEncounterSteps` (11740): every how many steps there is a
            // random encounter. Nineteen occurrences on nine maps, and
            // thirteen of them set it to **zero**, which in RM2k is turning
            // them off. Until 2026-09-27 it was left out because "there are no
            // random encounters"; there are since 2026-09-13 —see
            // `tools/runtime/encounters.s`— and Dalia's trip to Tasgarde asked
            // for it, the automatic `DaliaGoingToTasgarde` on map 66, which
            // turns them off before forcing the hero's route.
            //
            // The `1 / steps` and the rows' seven thresholds, computed here as
            // `rm2k-snes-battle` does for the map's registry, so a change of
            // steps changes the chance and the rows together, same as
            // `Encounters.set_steps` in the converter's model. It lasts until
            // the next map load: the ROM sets the map's again, which is what
            // RM2k does.
            if n == 0 {
                return cannot();
            }
            let steps = q(0).max(0);
            let thresholds = enc_step_thresholds(steps);
            if thresholds.iter().max().copied().unwrap_or(0) > 0xFF {
                return cannot();
            }
            let base = enc_base(steps);
            let mut out = vec![OP_ENCOUNTER_STEPS];
            out.extend(word(base)?);
            for t in thresholds {
                out.push(byte(t)?);
            }
            out.push(0xFF);
            Ok(out)
        }
        // `Comment` and its extra lines: the author's notes in the editor,
        // which RM2k skips when running the page. EasyRPG's `CommandComment`
        // only does something with the DynRPG and Destiny patches —comments
        // starting with `@` or `$`—, and none of the game's 23 starts like
        // that. It is not debt: in RM2k it does nothing either. Map 64's
        // farewell asked for it, whose only command that did not compile was
        // the "LYS" note the author left after the `Teleport` to the world.
        COMMENT | COMMENT_2 => Ok(vec![]),
        CONTROL_SWITCHES => {
            // OP_SWITCH: id (word), value (byte)
            if n < 4 || !(q(0) == SWITCH_SINGLE || q(0) == SWITCH_RANGE) {
                // By variable: it needs variables.
                return cannot();
            }
            if q(3) == SWITCH_TOGGLE {
                // `compile_toggle` builds it from the page's loop, which is
                // the one that knows `length`; here it would only arrive from
                // another path —the fused cells'—, which no toggle of the game
                // takes.
                return cannot();
            }
            let (first, last) = (q(1), q(2));
            if last < first || last - first >= MAX_RANGE {
                return cannot();
            }
            let value = if q(3) == SWITCH_ON { 1 } else { 0 };
            let mut out = Vec::new();
            for number in first..=last {
                out.push(OP_SWITCH);
                out.extend(word(number)?);
                out.push(value);
            }
            Ok(out)
        }
        TELEPORT => {
            // OP_TELEPORT: map (word), x (word), y (word). The map used to go
            // in a byte and that put a ceiling of 256 maps **on the format**:
            // the game has 328. Today it does not matter —the demos carry
            // 29— but it was a written ceiling, and removing it while it is
            // still cheap is cheaper than removing it the day a demo goes
            // over.
            if n < 3 {
                return cannot();
            }
            let Some(dest) = (ctx.map_index)(q(0)) else {
                // The map did not get into the ROM.
                return cannot();
            };
            if let Some(songs) = ctx.songs.as_deref_mut() {
                songs.dest(dest);
            }
            let mut out = vec![OP_TELEPORT];
            out.extend(usize_word(dest)?);
            out.extend(word(q(1))?);
            out.extend(word(q(2))?);
            Ok(out)
        }
        // The hero's location into three variables, and the jump to whatever
        // they say: the plant's breaking floors, and the way back from the
        // tutorials.
        //
        // OP_LOCATION: mode (byte), and the slots of the map, x and y (a byte
        // each). `MemorizeLocation` and `RecallToLocation` are the same
        // opcode because they are the same location read or written: bit 0
        // of the mode says which —`PLACE_JUMP`—, and when memorizing, which
        // is what writes the three variables, bits 7, 6 and 5 are the
        // VAR_REFRESH of each of those writes. **The map
        // in the variable is the RM2k id**, which is what any other page
        // reads and writes; the ROM translates it with `map_rm2k`. They
        // unlock 55 pages of Lashe City's milestone 3 —the plant's floors, 28
        // on 60 and 26 on 62, and the droid tutorial— and they are what holds
        // back the most pages in the whole game.
        MEMORIZE_LOCATION => {
            if n < 3 {
                return cannot();
            }
            let mut mode = 0u8;
            for (bit, &number) in PLACE_REFRESHES.iter().zip(&p[..3]) {
                if refresh(number as i64, map_events) != 0 {
                    mode |= bit;
                }
            }
            let mut out = vec![OP_LOCATION, mode];
            for &number in &p[..3] {
                out.push(ctx.indices.variable_slot(number as i64)?);
            }
            Ok(out)
        }
        RECALL_TO_LOCATION => {
            if n < 3 {
                return cannot();
            }
            let mut out = vec![OP_LOCATION, PLACE_JUMP];
            for &number in &p[..3] {
                out.push(ctx.indices.variable_slot(number as i64)?);
            }
            Ok(out)
        }
        MEMORIZE_BGM | PLAY_MEMORIZED_BGM => {
            // The song playing, noted down, and put back.
            //
            // OP_MEMORIZED_BGM: 0 remember the song that plays, 1 put it back.
            //
            // Without a song registry it is accepted and not done, like
            // `PlayBGM`.
            if ctx.songs.is_none() {
                return Ok(vec![]);
            }
            Ok(vec![
                OP_MEMORIZED_BGM,
                (cmd.code == PLAY_MEMORIZED_BGM) as u8,
            ])
        }
        CHANGE_PARTY_MEMBERS => {
            // OP_PARTY: operation (byte), actor (byte)
            if n < 3 || q(1) != PARTY_FIXED_ID {
                // The id comes from a variable.
                return cannot();
            }
            if !(q(0) == PARTY_ADD || q(0) == PARTY_REMOVE) || !(0..=255).contains(&q(2)) {
                return cannot();
            }
            Ok(vec![OP_PARTY, q(0) as u8, q(2) as u8])
        }
        // "Wait for the routes to finish". In RM2k it waits until **none** is
        // pending, neither the hero's nor any event's: it is
        // `Game_Map::IsAnyMovePending` in `Game_Interpreter::Update`, and not
        // a wait for the event that was just sent walking.
        //
        // OP_WAIT_ROUTES: no operands: the page does not continue until no
        // forced route is left running.
        PROCEED_WITH_MOVEMENT => Ok(vec![OP_WAIT_ROUTES]),
        // `HaltAllMovement`: all of the map's forced routes are abandoned at
        // once. It is `Game_Map::RemoveAllPendingMoves`, that is a
        // `CancelMoveRoute` on the hero and on each event, and what
        // cancelling means is written only once: it is **the same as what
        // happens when the route ends on its own** —whoever had a page route
        // of its own goes back to it, whoever did not stands still— and that
        // is why the ROM calls `resume_page`.
        //
        // What it **does not** touch, same as `CancelMoveRoute`: the step or
        // jump in progress are finished, and where each one faces stays where
        // the route left it.
        //
        // In the whole game there is **a single one** —map 11, the event that
        // rearranges the Lazer Teeth hideout when you are discovered— and
        // that is why it is worth it: without it that page does not compile
        // and the HQ cannot be played again after you get caught.
        //
        // OP_STOP_ROUTES: no operands
        HALT_ALL_MOVEMENT => Ok(vec![OP_STOP_ROUTES]),
        // `ChangePBG`, the parallax background. **It is accepted and
        // dropped**, which is the same the port already does with the whole
        // panorama: mode 3 has two background layers and both are taken —the
        // map and the upper layer with the window—, so there is nowhere to
        // draw it. See workflow/tasks/wishlist/panorama-del-mapa-2.md.
        //
        // It is dropped **when compiling**: it emits nothing and the ROM does
        // not find out, like move commands 26 and 27.
        //
        // It appears **only once in the whole game**: seven commands in a
        // single page, the Hover-Tram ride on map 13, where the afternoon
        // landscape runs behind and changes speed when starting and braking.
        // It is the only page that blocks that map, so the debt declared here
        // is exactly "the tram is ridden with no background landscape".
        CHANGE_PBG => Ok(vec![]),
        FLASH_SPRITE => {
            // A flash on a character: `Game_Character::Flash`. The parameters
            // are whom, r, g and b from 0 to 31, the power, how many **tenths
            // of a second** it lasts, and whether the page waits for it to
            // finish.
            //
            // The tenths are not a detail: `CommandFlashSprite` does
            // `event->Flash(r, g, b, p, tenths * DEFAULT_FPS / 10)` and, if it
            // waits, `SetupWait(tenths)`, which is the same wait as the Wait
            // command. So the time comes for free: it is an OP_DELAY after
            // it.
            //
            // OP_FLASH: target (byte), r, g, b, power (a byte each, 0 to 31)
            // and how many frames it lasts (byte)
            if n < 7 {
                return cannot();
            }
            // **A flash on an event that shares a palette is emitted
            // anyway.** On the console the flash is a CGRAM tint
            // —`paint_flash` uploads the whole row— so two events with the
            // same graphic flash together. Until 2026-09-13 that cut the
            // page, and the cut cost **51 pages**, measured, and one of them
            // is map 20's `EV0027`: the Bum cutscene that turns on the Rat
            // Tracks B2 event. Without it the player shows up invisible and
            // the game cannot continue.
            //
            // What is left is a declared divergence from RM2k, which flashes
            // the image of a single sprite, and it is in
            // `workflow/divergencias/destello-sobre-la-paleta-de-otro.md`.
            let target = target_of(q(0), map_events)?;
            if p[1..5].iter().any(|&v| !(0..=31).contains(&v)) {
                return cannot();
            }
            let frames = q(5) * FRAMES_PER_TENTH;
            if !(0 < frames && frames <= 255) {
                return cannot();
            }
            let mut out = vec![
                OP_FLASH,
                target,
                p[1] as u8,
                p[2] as u8,
                p[3] as u8,
                p[4] as u8,
                frames as u8,
            ];
            if q(6) != 0 {
                // Waiting is exactly the Wait command: `SetupWait(tenths)`,
                // that is the same tenths times FRAMES_PER_TENTH.
                out.push(OP_DELAY);
                out.extend(word(frames)?);
            }
            Ok(out)
        }
        CONTROL_VARS => {
            // RM2k's variables are **sixteen-bit signed** here: RM2k carries
            // them at 32 and caps them at ±999999, but none of the game's goes
            // past a few hundred —timer seconds, a random 0 to 100,
            // counters—. What does not fit in the word does not compile, which
            // is more honest than truncating. The bytecode talks in slots:
            // see `variables` in [`crate::indices`].
            //
            // OP_VAR: slot (byte), operation (byte), kind (byte), a (word),
            // b (word)
            //
            // `[how it is chosen, from, to, operation, operand kind, a, b]`.
            // One variable at a time and nothing else: ranges and indirect are
            // used by no page of the game.
            if n < 7 {
                return cannot();
            }
            if q(0) != 0 {
                return cannot();
            }
            let slot = ctx.indices.variable_slot(q(1))?;
            let refresh = refresh(q(1), map_events);
            if !matches!(q(3), VAR_SET | VAR_ADD | VAR_SUBTRACT) {
                return cannot();
            }
            let operand_kind = q(4);
            let (mut a, mut b) = (q(5), q(6));
            if operand_kind == VAR_CONSTANT {
                if !(-0x8000..=0x7FFF).contains(&a) {
                    return cannot();
                }
                b = 0;
            } else if operand_kind == VAR_VARIABLE {
                a = ctx.indices.variable_slot(a)? as i64;
                b = 0;
            } else if operand_kind == VAR_RANDOM {
                if !(0 <= a && a <= b && b <= 0x7FFF && b - a < 256) {
                    return cannot();
                }
            } else if operand_kind == VAR_OTHER {
                if !(a == OTHER_GOLD || a == OTHER_TIMER) {
                    return cannot();
                }
                b = 0;
            } else if operand_kind == VAR_ACTOR {
                // An actor's data: `a` the actor and `b` which one, with the
                // numbers of `ControlVariables::Actor`. The ROM does the HP,
                // the SP and their maximums, 2 to 5, which is what the game
                // asks for: the characters' systems read Talan's HP in
                // battle —where they are the battle's, see `ba_sync_out`—
                // and `ResetAfterBattles` the four. See `actor_stat` in
                // tools/runtime/level.s.
                if !(ACTOR_STAT_HP..=ACTOR_STAT_SP_MAX).contains(&b)
                    || !(1..=0xFF).contains(&a)
                    || !ctx.game.actors.contains_key(&(a as i32))
                {
                    return cannot();
                }
            } else if operand_kind == VAR_CHARACTER {
                // A character's cell. `a` becomes the same target byte
                // OP_ROUTE carries —0 the hero, the event's index plus one—
                // and not the RM2k id: the bytecode never sees an id again,
                // which is what `MapEvents` exists to guarantee. `b` is which
                // coordinate.
                if !(b == CHARACTER_X || b == CHARACTER_Y) {
                    return cannot();
                }
                // Not checked as a byte: it goes as a word.
                a = if a == ROUTE_HERO {
                    0
                } else {
                    let Some(me) = map_events else {
                        return cannot();
                    };
                    match me.route_target(a) {
                        Some(t) => t as i64,
                        None => return cannot(),
                    }
                };
            } else {
                return cannot();
            }
            Ok(vec![
                OP_VAR,
                slot,
                byte(q(3) | refresh)?,
                byte(operand_kind)?,
                (a & 0xFF) as u8,
                ((a >> 8) & 0xFF) as u8,
                (b & 0xFF) as u8,
                byte(b >> 8)?,
            ])
        }
        TIMER_OPERATION => {
            // The timer. The whole operation is done —set, start and stop— and
            // the seconds can come from a variable: it is the fourth
            // operation, `TIMER_SET_VAR`, with the slot in the operand.
            //
            // OP_TIMER: operation (byte), seconds (word), visible (byte). The
            // five bytes are fixed even though each operation uses two: that
            // way the interpreter skips it without looking at which one it is,
            // which is what the converter's `walk_code` does.
            if n < 5 {
                return cannot();
            }
            if q(0) == TIMER_SET {
                if q(1) != TIMER_FIXED_SECONDS {
                    let slot = ctx.indices.variable_slot(q(2))?;
                    return Ok(vec![OP_TIMER, TIMER_SET_VAR as u8, slot, 0, 0]);
                }
                // The ROM counts the frames in sixteen bits, so the cap is not
                // the operand's but the count's. It is eighteen minutes, and
                // the game's longest timer is ten.
                if !(0..=0xFFFF).contains(&(q(2) * FRAMES_PER_SECOND + TIMER_EXTRA_FRAMES)) {
                    return cannot();
                }
                let mut out = vec![OP_TIMER, TIMER_SET as u8];
                out.extend(word(q(2))?);
                out.push(0);
                return Ok(out);
            }
            if q(0) == TIMER_START || q(0) == TIMER_STOP {
                // The fifth parameter is "also in battle", and here there are
                // no battles: it is compiled anyway and ignored, like the rest
                // of what belongs to combat.
                return Ok(vec![
                    OP_TIMER,
                    q(0) as u8,
                    0,
                    0,
                    if q(3) != 0 { 1 } else { 0 },
                ]);
            }
            cannot()
        }
        MOVE_EVENT => compile_route(ctx, cmd, map_events),
        CHANGE_EVENT_LOCATION => {
            // Placing an event on a cell. It is `CommandChangeEventLocation`:
            // `MoveTo`, which sets the cell and leaves the step at zero, and
            // nothing else —only RM2k3 touches the direction, and the game is
            // RM2k—. The opening cutscene uses it six times to bring Core,
            // Manta and the droid into the scene.
            //
            // OP_PLACE: target (byte, as in OP_ROUTE: the event's index plus
            // one), x (word), y (word). Places the event on the cell and cuts
            // the step in progress; it does not touch its route nor where it
            // faces, which is what `MoveTo` does.
            if n < 4 || !(q(1) == PLACE_CONSTANT || q(1) == PLACE_BY_VARIABLE) {
                return cannot();
            }
            // Nobody moves the hero this way in the game —that is what
            // Teleport is for— and without the map there is no way to
            // translate the id.
            if q(0) == ROUTE_HERO {
                return cannot();
            }
            let Some(me) = map_events else {
                return cannot();
            };
            let Some(target) = me.route_target(q(0)) else {
                return cannot();
            };
            let target = byte(target as i64)?;
            if q(1) == PLACE_BY_VARIABLE {
                // `ChangeEventLocation` with the cell **in two variables**,
                // which is RM2k's other `PLACE_*`: same effects as `OP_PLACE`
                // —`MoveTo`, the cell changes right away and the step in
                // progress is cut— but the two numbers are read **when it
                // runs**: it is `CommandChangeEventLocation`'s
                // `Main_Data::game_variables->Get(x)`.
                //
                // It goes in its own opcode and not in a bit of `OP_PLACE`
                // because the operands are different: two one-byte slots
                // against two words. `OPCODE_SIZE` is a table, so an opcode
                // whose size depends on a bit cannot be walked by either the
                // converter or the ROM.
                //
                // What it unlocks is **one page**, measured over the whole
                // game, and there are 129 occurrences in 32 pages: the other
                // 31 are held back by something else anyway. That page is the
                // one that matters: the engine of the stones minigame on map
                // 11, which without this cannot place the stone where the
                // player is standing and therefore none can be thrown.
                //
                // OP_PLACE_VAR: target (byte, as in OP_PLACE), slot of x
                // (byte), slot of y (byte)
                return Ok(vec![
                    OP_PLACE_VAR,
                    target,
                    ctx.indices.variable_slot(q(2))?,
                    ctx.indices.variable_slot(q(3))?,
                ]);
            }
            if !((0..=0xFFFF).contains(&q(2)) && (0..=0xFFFF).contains(&q(3))) {
                return cannot();
            }
            let mut out = vec![OP_PLACE, target];
            out.extend(word(q(2))?);
            out.extend(word(q(3))?);
            Ok(out)
        }
        TILE_SUBSTITUTION => {
            // Changing one map tile for another, on every cell where it is:
            // `CommandTileSubstitution`. It is by **tile number** and not by
            // cell, and that is why in the ROM it is a small table that
            // translates blocks while drawing, and not a write to the grid
            // —which lives in ROM and cannot be written—. The converter
            // resolves which block goes to which: see `Substitutions`.
            //
            // `[upper layer?, old tile, new tile]`, with the tiles numbered
            // from the first of their layer, which is how `DoSubstitute`
            // numbers them; translated to the ROM's blocks by the caller, who
            // built them.
            if n < 3 {
                return cannot();
            }
            let Some(subs) = map_events.and_then(|m| m.substitutions.as_ref()) else {
                // Without the converter in between there are no blocks to
                // translate against. See `Substitutions` in blocks.py.
                return cannot();
            };
            let Some(pairs) = subs.pairs(q(0) != 0, q(1), q(2))? else {
                return cannot();
            };
            if pairs.is_empty() {
                // No cell of the map draws the old tile, so there is nothing
                // to change. In RM2k the substitution is still recorded, but
                // nobody looks at what it records: there is no cell that can
                // use it.
                return Ok(vec![]);
            }
            let mut out = vec![OP_TILE_SUB, byte(pairs.len() as i64)?];
            for (old, new) in pairs {
                out.extend(word(old)?);
                out.extend(word(new)?);
            }
            Ok(out)
        }
        STORE_TERRAIN_ID => {
            // A cell's terrain into a variable: `CommandStoreTerrainID`. The
            // terrain comes from the tile of the **lower** layer —"RPG_RT
            // always uses the terrain of the first lower tile"— so the upper
            // layer does not change it.
            //
            // `[mode, x, y, variable]`, with `ValueOrVariable`: in mode 0 the
            // cell comes written and in mode 1 the two numbers are variable
            // ids. Both are resolved **when it runs**, so both go in the same
            // opcode with the mode set: reading them here in mode 1 would
            // answer with what the variables were worth at compile time.
            if n < 4 || !(q(0) == 0 || q(0) == 1) {
                return cannot();
            }
            let dest = ctx.indices.variable_slot(q(3))?;
            let (x, y) = if q(0) != 0 {
                (
                    ctx.indices.variable_slot(q(1))? as i64,
                    ctx.indices.variable_slot(q(2))? as i64,
                )
            } else {
                if !((0..=0xFFFF).contains(&q(1)) && (0..=0xFFFF).contains(&q(2))) {
                    return cannot();
                }
                (q(1), q(2))
            };
            let mode = q(0) | refresh(q(3), map_events);
            let mut out = vec![OP_TERRAIN, byte(mode)?];
            out.extend(word(x)?);
            out.extend(word(y)?);
            out.push(dest);
            Ok(out)
        }
        SHOW_HIDDEN_MONSTER => {
            // `ShowHiddenMonster`, which only exists in battle: the troop
            // member in that place —from 0, in troop order— stops being
            // hidden. See `ba_show_hidden`.
            //
            // It only arrives from a troop page: see `TROOP_COMMANDS`. A place
            // the troop does not have does nothing in easyrpg —`GetEnemy`
            // gives null—, and the ROM checks it against `BA_KID`.
            if n < 1 || !(0..256).contains(&q(0)) {
                return cannot();
            }
            Ok(vec![OP_SHOW_ENEMY, q(0) as u8])
        }
        CHANGE_MONSTER_HP | CHANGE_MONSTER_MP => {
            // `ChangeMonsterHP` —[place, loses, from where, amount, lethal]—
            // and `ChangeMonsterMP` —the same without lethal—, which only
            // exist in battle: `Game_Interpreter_Battle`. The game's are all
            // a constant that is subtracted, on places 0 to 2; the percentage
            // and the variable do not compile.
            //
            // OP_ENEMY: place (byte), what (byte: `ENEMY_SP` for the SP, and
            // `ENEMY_LETHAL` on top), amount (signed word). See
            // `ba_enemy_change` in tools/runtime/battle_troop.s.
            let hp = cmd.code == CHANGE_MONSTER_HP;
            if n < if hp { 5 } else { 4 } {
                return cannot();
            }
            if !(0..256).contains(&q(0)) || q(2) != 0 || !(0..=0x7FFF).contains(&q(3)) {
                return cannot();
            }
            let amount = if q(1) != 0 { -q(3) } else { q(3) };
            let mut what = if hp { 0 } else { ENEMY_SP };
            if hp && q(4) != 0 {
                what |= ENEMY_LETHAL;
            }
            let mut out = vec![OP_ENEMY, q(0) as u8, what];
            out.extend((amount as i16).to_le_bytes());
            Ok(out)
        }
        SHAKE_SCREEN => {
            // `CommandShakeScreen`, in its RM2k form: power, speed, tenths and
            // whether it waits. The game's 29 are of that form. With zero
            // tenths it is `ShakeEnd` and never waits.
            //
            // OP_SHAKE: power (byte), speed (byte), frames (word):
            // `ShakeOnce`. With zero frames it is `ShakeEnd`: the screen goes
            // back to its place. The math is `shake_tick` in
            // tools/runtime/camera.s.
            if n < 4 || !(0..=9).contains(&q(0)) || !(0..=9).contains(&q(1)) {
                return cannot();
            }
            let frames = q(2) * FRAMES_PER_TENTH;
            if frames > 0xFFFF {
                return cannot();
            }
            let mut out = vec![OP_SHAKE, q(0) as u8, q(1) as u8];
            out.extend(word(frames)?);
            if frames != 0 && q(3) != 0 {
                out.push(OP_DELAY);
                out.extend(word(frames)?);
            }
            Ok(out)
        }
        SHOW_BATTLE_ANIMATION => compile_animation(ctx, cmd, map_events),
        FLASH_SCREEN => {
            // `CommandFlashScreen`, in its RM2k form: color, power, tenths and
            // whether it waits. The game's 62 are of that form, and none lasts
            // more than twenty tenths: the frames byte is enough, and the ROM
            // divides the level by what is left with the hardware's eight-bit
            // divider.
            //
            // OP_FLASH_SCREEN: r, g, b, power (a byte each, 0..31) and frames
            // (byte): `FlashOnce`, the whole-screen flash. The math is
            // `flash_tick` in tools/runtime/screen_flash.s.
            if n < 6 || p[..4].iter().any(|&v| !(0..=31).contains(&v)) {
                return cannot();
            }
            let frames = q(4) * FRAMES_PER_TENTH;
            if frames > 0xFF {
                return cannot();
            }
            let mut out = vec![
                OP_FLASH_SCREEN,
                p[0] as u8,
                p[1] as u8,
                p[2] as u8,
                p[3] as u8,
                byte(frames)?,
            ];
            if frames != 0 && q(5) != 0 {
                out.push(OP_DELAY);
                out.extend(word(frames)?);
            }
            Ok(out)
        }
        TRADE_EVENT_LOCATIONS => {
            // `CommandTradeEventLocations`: each one goes with `MoveTo` to the
            // other's cell. No page of the game uses it on the hero.
            //
            // OP_SWAP: two targets (a byte each, as in OP_PLACE): the two
            // events trade cells, each one with `MoveTo`.
            if n < 2 {
                return cannot();
            }
            let Some(me) = map_events else {
                return cannot();
            };
            let targets: Vec<Option<usize>> = p[..2]
                .iter()
                .map(|&who| me.route_target(who as i64))
                .collect();
            if targets.iter().any(|t| matches!(t, None | Some(0))) {
                // The hero, a vehicle or an event that does not exist.
                return cannot();
            }
            let mut out = vec![OP_SWAP];
            for t in targets {
                out.push(byte(t.unwrap() as i64)?);
            }
            Ok(out)
        }
        WAIT => {
            // OP_DELAY: frames (word): the cutscene waits six seconds, that is
            // 360, and they do not fit in a byte.
            if n < 1 {
                return cannot();
            }
            let frames = q(0) * FRAMES_PER_TENTH;
            if frames > 0xFFFF {
                return cannot();
            }
            let mut out = vec![OP_DELAY];
            out.extend(word(frames)?);
            Ok(out)
        }
        TINT_SCREEN => {
            // OP_TINT: r, g, b, sat (a byte each)
            //
            // The duration is discarded: the tint is applied at once. The
            // screen being compared is always settled, so the final value is
            // the one that matters; what is lost is the one-second gradient.
            if n < 4 {
                return cannot();
            }
            if p[..4].iter().any(|&v| !(0..=200).contains(&v)) {
                return cannot();
            }
            Ok(vec![
                OP_TINT, p[0] as u8, p[1] as u8, p[2] as u8, p[3] as u8,
            ])
        }
        SHOW_MESSAGE => {
            // OP_MESSAGE: offset (word) within the `messages` block: opens
            // that window and blocks the page until the player presses A.
            //
            // The operand is an offset and not a text, and that is what makes
            // it fit. An already composed message page is ~240 tiles at 4bpp,
            // that is 7.5 KB, and emitting one for every text box in the game
            // does not come close to fitting in a 256 KB cartridge: the 2895
            // boxes would be 21 MB. What is emitted is the text —one byte per
            // letter— and the 65816 composes it on the fly, with the font in
            // ROM, which is FF6's way out. The same 2895 boxes are 180 KB of
            // text, and a single map quite a lot less.
            //
            // Sixteen bits are enough because the block has to fit in a 32 KB
            // bank: `lda [msg_ptr], y` reads it with a pointer that increments
            // one byte at a time and does **not** carry into the bank byte, so
            // `bloque()` emits it with `.block`, which keeps it whole in one
            // bank. If some day it does not fit, what has to grow is the
            // pointer, not the operand.
            let Some(messages) = ctx.messages.as_deref_mut() else {
                // This ROM carries no window: nowhere to put it.
                return cannot();
            };
            let mut lines = vec![cmd.string.clone()];
            lines.extend_from_slice(extra);
            // `Messages::add` removes the escape tail, since every box goes
            // through it; anything that is not `\|` or `\^` still cuts the
            // page from there. See `escape_tail`.
            let at = messages.add(&lines)?;
            let mut out = vec![OP_MESSAGE];
            out.extend(usize_word(at)?);
            Ok(out)
        }
        _ => cannot(),
    }
}

/// A forced `MoveEvent` route: whom, the frequency, and the commands the
/// ROM walks, with the ones that drag something along resolved.
///
/// The parameters are (whom, frequency, a repeat bitmask, whether it is
/// skippable) and from there on the route's commands, with the codes of
/// liblcf's `rpg::MoveCommand::Code`: which ones the ROM walks is
/// [`route::known`].
///
/// How a forced route consumes time is a modeling decision both sides have
/// to share: turning is instantaneous —it goes to the next command on the
/// same frame—, waiting consumes a frame, and moving starts a one-cell step,
/// which the ROM walks at WALK_SPEED = 2 pixels per frame like any other
/// step. A blocked move is skipped, which is our decision and not RM2k's
/// —RM2k would retry forever, and a hung test tells nobody anything—.
///
/// OP_ROUTE: target (byte), frequency (byte), how many commands (byte), and
/// the commands. The target is 0 for the hero, and otherwise the event's
/// index in the map's table plus one.
///
/// **The index is not the RM2k id.** 39 maps of the game have gaps in the
/// event numbering, so a route aimed at id 8 would move whichever is eighth
/// in the list, which can be any other. The converter translates it, being
/// the only one that sees the map.
fn compile_route(ctx: &mut Ctx, cmd: &Command, map_events: Option<&MapEvents>) -> Step<Vec<u8>> {
    let p = &cmd.parameters;
    if p.len() < 4 {
        return cannot();
    }
    let target = target_of(p[0] as i64, map_events)?;
    if !(route::FREQUENCY_MIN..=route::FREQUENCY).contains(&p[1]) {
        // 1 does not fit in the ROM's wait byte.
        return cannot();
    }
    let commands = route::decode(&p[4..])?;
    let codes: Vec<i32> = commands.iter().map(|(c, _)| *c).collect();
    if route::min_frequency(p[1], &codes, p[2] != 0) < route::FREQUENCY_MIN {
        // Commands 30 and 31 would take it down to 1.
        return cannot();
    }
    let mut path: Vec<i64> = Vec::new();
    // Whether the cursor is between a `begin_jump` and its `end_jump`. Inside
    // a jump the commands are not run: `BeginMoveRouteJump` only **adds up**
    // the `move_*`s and the turns, and 9 there would have to ask about the
    // hero in the middle of the math. No route of the game does it —measured,
    // zero—, so it is rejected instead of letting the ROM walk it down a path
    // no test exercises.
    let mut in_jump = false;
    for (command, extras) in commands {
        if command == ROUTE_JUMP_START {
            in_jump = true;
        } else if command == ROUTE_JUMP_END {
            in_jump = false;
        } else if command == ROUTE_TOWARD_HERO && in_jump {
            return cannot();
        }
        if command == ROUTE_SOUND {
            // The sound inside the route: it plays when the route reaches that
            // step, since 2026-09-27. In a MoveEvent it goes with two bytes
            // after it, the effect's index in `Songs::sounds` —the same one
            // OP_SOUND carries—, so the effect goes into the map's audio
            // package like that of a `PlaySound`. It costs no frame:
            // `UpdateMoveRoute` does not touch its stop counter.
            //
            // It is still dropped in two places. **Inside a jump**, because
            // RM2k does not touch it there: `BeginMoveRouteJump` walks up to
            // the `end_jump` adding up the steps and runs nothing else. And
            // **in a page's own route**, which is a bare list of codes with
            // no room for the operand —see `route::own`—: a single one in the
            // game asks for it, that of event 40 on map 2.
            //
            // Without a song registry, or "(OFF)", it is dropped as before.
            if in_jump || ctx.songs.is_none() || AUDIO_OFF.contains(&extras[0].text()) {
                continue;
            }
            let sound = (
                extras[0].text().to_string(),
                extras[1].int() as i32,
                extras[2].int() as i32,
                extras[3].int() as i32,
            );
            let k = sound_index(ctx, sound, true) as i64;
            path.extend([command as i64, k & 0xFF, k >> 8]);
            continue;
        }
        if ROUTE_TRANSPARENCY.contains(&command) {
            // Raising and lowering the transparency by an eighth. They are
            // accepted and dropped, like the sound: the SNES does not fade a
            // sprite in steps without color math, and the game's eight routes
            // that use it —map 2's four screens, which fade while Manta
            // hacks— are a decorative fade inside a 78-command scene that did
            // not compile without this. They cost no frames: in
            // `UpdateMoveRoute` they go through the branch that does not touch
            // the stop counter.
            continue;
        }
        // Turning, waiting and moving. The `move_*`s came in on 2026-09-03,
        // and they are looked at *during* the walk and not only at the end:
        // `path` tests it, comparing four frames of a twelve-cell route with
        // waits in the middle. What goes in from `rpg::MoveCommand::Code` is
        // `route::known`, and moving toward the hero is in since 2026-09-12;
        // moving away from him, turning in place and the switches are still
        // out.
        if !route::known(command) {
            return cannot();
        }
        if (command == ROUTE_FACE_HERO || command == ROUTE_TOWARD_HERO) && target == 0 {
            // The hero facing or moving toward itself.
            return cannot();
        }
        if (command == ROUTE_LOCK_DIR || command == ROUTE_UNLOCK_DIR) && target == 0 {
            // Locking and unlocking the facing on **the hero**: accepted and
            // dropped, like the sound and the transparency. On events they
            // are done. Raising and lowering the speed were also dropped on
            // the hero, and they are done since 2026-09-10 —the Tram Officer
            // asks for it, and 170 routes in the game— and they stay: RM2k
            // restores the frequency when the route ends and not the speed,
            // so the pad walks afterwards at the speed the route left.
            //
            // Dropping them and not rejecting the whole page, which was the
            // first thing tried, is from 2026-09-06: **Talan's scene has a
            // hero route that starts with 28**, so the scene that motivated
            // that day's six points did not compile and the player could not
            // leave the Emitter Room corridor.
            continue;
        }
        if route::diagonal(command) && target == 0 {
            // And the hero diagonally: the ROM does not know how to do it and
            // none of the game's 26 routes with diagonals is the hero's.
            // Without this cut the ROM would go left —the mover of
            // `step_route` falls into `try_left` by elimination—.
            return cannot();
        }
        if command == ROUTE_CHANGE_GRAPHIC {
            // The only command with an operand: after 34 goes the graphic's
            // index in `Graphics`, which the converter resolves to the map's
            // sprite bank. Whoever walks an already compiled route has to
            // skip that byte: read as a command, a 30 or a 31 change the
            // route's frequency without anyone asking.
            //
            // **On the hero too**, since 2026-09-12. Its graphic comes from
            // the actor table, but the actor's twelve poses are written with
            // the same shape as an `npc_poses` entry, so the ROM changes the
            // pointer and that is it: see `graphic_hero` in
            // tools/runtime/hero_route.s. They are +29 pages of the game, and
            // among them the three of map 8's `EV0047`, which could not be
            // interacted with.
            let Some(graphics) = ctx.graphics.as_deref_mut() else {
                return cannot();
            };
            if extras.len() < 2 {
                return cannot();
            }
            let chosen = graphics.index(extras[0].text(), extras[1].int() as i32);
            if chosen > GRAPHICS_MAX {
                return cannot();
            }
            path.push(command as i64);
            path.push(chosen as i64);
            continue;
        }
        path.push(command as i64);
    }
    if path.len() > 255 {
        return cannot();
    }
    if path.is_empty() {
        // A route left without commands —only sound or transparency, like
        // those of map 2's screens— is not emitted: in RM2k
        // `UpdateMoveRoute` consumes it whole on the same frame and considers
        // it finished, so it neither costs frames nor leaves anything to wait
        // for in `ProceedWithMovement`.
        return Ok(vec![]);
    }
    let mut out = vec![OP_ROUTE, target, p[1] as u8, path.len() as u8];
    for v in path {
        out.push(byte(v)?);
    }
    Ok(out)
}

/// `ShowBattleAnimation` on the map: its sounds and flashes as a timeline,
/// and the number the ROM draws it with.
///
/// `CommandShowBattleAnimation`, 11210: the battle animation is drawn over
/// the character, with its own graphics and its own sound. In the opening it
/// is the explosion with which CORE breaks map 2's security door; the page
/// that asks for it continues with a `FlashScreen`, which does show, and
/// with the message "CORE performs FURY PUNCH!". With the command cutting,
/// that page did not run and the game was left without the corridor to the
/// elevator.
///
/// The battle animations on the map, since 2026-09-11: their sounds and
/// their flashes, **without the drawing**. `ShowBattleAnimation` compiles to
/// OP_ANIMATION with the whole timeline inside: how many entries and, for
/// each one, eight bytes —the tick it fires at, counted from the command's,
/// the type and six of data—. It is what `BattleAnimation::Update` does with
/// the animation's `timings`: on the even frame `2 * (frame - 1)` the effect
/// plays and the flash of the screen or of the target event starts. There
/// is a single one at a time —`Game_Screen::ShowBattleAnimation` replaces
/// the previous one— and it advances once per frame **before** the flashes,
/// which is where `Game_Screen::Update` puts it. With "wait", the page waits
/// for as long as it lasts: two frames per animation frame. See
/// `battle_anim_tick` in tools/runtime/battle_animation.s.
///
/// The flash is not exactly RM2k's: there the power is `min((7 - (d + 1) /
/// 2) * power / 6, 31)` for ten frames, in steps; here it is a `FlashScreen`
/// or a `FlashSprite` that starts at the first and goes down linearly over
/// `ANIM_FLASH_FRAMES`. It is the same light and it lasts the same.
///
/// The **drawing**, since 2026-09-12. The opcode carries two more bytes: the
/// RM2k animation number as is —180 at most, so it fits in one— and what it
/// is drawn over. The number goes raw and not as an index of ours on
/// purpose: the ROM looks it up in `anim_battle`, a table by number, so
/// neither end has to carry a counter the other one guesses. See
/// `animation.py`.
///
/// OP_ANIMATION: number, what it is drawn over, n, and n entries of eight
/// bytes. The parameters are (animation, target, wait, global).
fn compile_animation(
    ctx: &mut Ctx,
    cmd: &Command,
    map_events: Option<&MapEvents>,
) -> Step<Vec<u8>> {
    let p = &cmd.parameters;
    if p.len() < 3 {
        return cannot();
    }
    let anim = ctx.game.animations.get(&p[0]);
    let (target, who) = if p[1] as i64 == ROUTE_HERO {
        (Some(0usize), None)
    } else if let Some(me) = map_events {
        let who = if p[1] as i64 == ROUTE_THIS_EVENT {
            me.owner
        } else {
            Some(p[1])
        };
        (me.route_target(p[1] as i64), who)
    } else {
        (None, None)
    };
    let (Some(anim), Some(target)) = (anim, target) else {
        // Without an animation or a target RM2k does nothing.
        return Ok(vec![]);
    };
    // The target's flash is a tint of its palette on the console, and two
    // events with the same graphic share it: see `FlashSprite`. Here the page
    // is not cut for that: that flash is not done. **The hero is never
    // flashed**: whom he shares a palette with depends on the party, which
    // the compiler does not see —the converter looks at it for the
    // `FlashSprite`s and cuts the whole ROM—, and an animation is not worth
    // that.
    let flashes = target != 0 && !map_events.unwrap().shares_graphic(who);
    let mut entries: Vec<[u8; 8]> = Vec::new();
    for t in &anim.timings {
        let tick = (t.frame as i64 - 1) * 2;
        if !(0..=255).contains(&tick) {
            continue;
        }
        let tick = tick as u8;
        let (name, volume, tempo, balance) = &t.se;
        if !name.is_empty() && name != "(OFF)" {
            if let Some(songs) = ctx.songs.as_deref_mut() {
                let k = songs.sound((name.clone(), *volume, *tempo, *balance), true);
                entries.push([
                    tick,
                    ANIM_SOUND,
                    (k & 0xFF) as u8,
                    byte((k >> 8) as i64)?,
                    0,
                    0,
                    0,
                    0,
                ]);
            }
        }
        let c = |v: i32| v.clamp(0, 31) as u8;
        let (r, g, b) = (c(t.rgb.0), c(t.rgb.1), c(t.rgb.2));
        let strength = (7 * t.power.max(0) as i64 / 6).min(31) as u8;
        if t.flash_scope == 2 {
            entries.push([
                tick,
                ANIM_SCREEN_FLASH,
                r,
                g,
                b,
                strength,
                ANIM_FLASH_FRAMES,
                0,
            ]);
        } else if t.flash_scope == 1 && flashes {
            entries.push([
                tick,
                ANIM_FLASH,
                target as u8,
                r,
                g,
                b,
                strength,
                ANIM_FLASH_FRAMES,
            ]);
        }
    }
    // Stable: the LDB's order.
    entries.sort_by_key(|e| e[0]);
    if entries.len() > 255 {
        return cannot();
    }
    // A `global` one —the one RM2k repeats three by three to cover the
    // screen— is accepted and not drawn: it is still heard and still
    // flashes, which is what it already did. None of the intro's eleven asks
    // for it.
    let number = if p[0] <= 255 && !(p.len() > 3 && p[3] != 0) {
        p[0] as i64
    } else {
        ANIM_NO_DRAWING as i64
    };
    // What it is drawn over: with "screen" scope —`Animation::Scope_screen`,
    // which is 1— RM2k draws it at the center and asks the target nothing;
    // with the other, over the target, which is the same byte the routes and
    // the flashes already use.
    let drawn_over = if anim.scope == 1 {
        ANIM_TARGET_SCREEN
    } else {
        byte(target as i64)?
    };
    let mut out = vec![OP_ANIMATION, byte(number)?, drawn_over, entries.len() as u8];
    for e in entries {
        out.extend(e);
    }
    let frames = 2 * anim.frames as i64;
    if p[2] != 0 && frames != 0 {
        out.push(OP_DELAY);
        out.extend(word(frames)?);
    }
    Ok(out)
}

/// Which commands of this page are accepted without being done, so the
/// converter can warn instead of the debt going silent.
///
/// The three `Picture` ones are debt only **if this page is not the one of
/// the picture the ROM does draw**: warning anyway would be the warning
/// nobody reads, which is how a real debt gets lost among the ones that no
/// longer are.
pub fn page_debts(
    game: &Game,
    commands: &[Command],
    picture: Option<&Picture>,
) -> Result<Vec<i32>> {
    let mut out = BTreeSet::new();
    for cmd in commands {
        if !ACCEPTED_UNDONE.contains(&cmd.code) {
            continue;
        }
        // A digit on a counter's picture is done: it shows the counter.
        if counter_of_picture(game, cmd).is_some() {
            continue;
        }
        if matches!(cmd.code, SHOW_PICTURE | MOVE_PICTURE | ERASE_PICTURE) {
            match compile_picture(cmd, picture) {
                Ok(Some(_)) => continue,
                Ok(None) => {}
                Err(Stop::Fatal(b)) => return Err(b),
                Err(Stop::Cannot) => {}
            }
        }
        out.insert(cmd.code);
    }
    Ok(out.into_iter().collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::CommonEvent;

    fn cmd(code: i32, parameters: &[i32], string: &str) -> Command {
        Command::new(code, 0, string, parameters.to_vec())
    }

    /// A page compiled with nothing but songs, in package 0.
    fn with_songs(
        commands: &[Command],
        songs: &mut Songs,
        map_index: &dyn Fn(i64) -> Option<usize>,
    ) -> Option<Vec<u8>> {
        let game = Game::default();
        let indices = Indices::default();
        let sound = SoundSettings::default();
        songs.current = Some(Package::Map(0));
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index,
            messages: None,
            songs: Some(songs),
            graphics: None,
            picture: None,
            troops: None,
        };
        compile_page(&mut ctx, commands, None, 0, 0).unwrap()
    }

    /// A game whose common event 9 shows variable 48 in two digit pictures,
    /// 2 and 3, the way the one this was built for does: the tens centered at
    /// (55, 30) and the ones at (70, 30).
    fn with_counter(declared: bool, pictures: &[(i32, i32, i32)]) -> Game {
        let mut game = Game::default();
        let mut commands = Vec::new();
        for &(number, x, y) in pictures {
            for d in ["0", "9"] {
                commands.push(cmd(
                    SHOW_PICTURE,
                    &[number, 0, x, y, 0, 100, 0, 1, 100, 100, 100, 100, 0, 0],
                    d,
                ));
            }
        }
        game.common_events.insert(
            9,
            CommonEvent {
                trigger: 5,
                switch_flag: false,
                switch_id: 1,
                commands,
            },
        );
        if declared {
            game.patches.counters.insert(9, 48);
        }
        game
    }

    fn compile_with(game: &Game, commands: &[Command]) -> Result<Option<Vec<u8>>> {
        let indices = Indices {
            variables: BTreeMap::from([(48, 5)]),
            ..Default::default()
        };
        let sound = SoundSettings::default();
        let mut ctx = Ctx {
            game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            picture: None,
            troops: None,
        };
        compile_page(&mut ctx, commands, None, 0, 0)
    }

    const FORTITUDE: [(i32, i32, i32); 2] = [(2, 55, 30), (3, 70, 30)];

    #[test]
    fn a_declared_counter_is_one_opcode_and_not_its_body() {
        // The middle of the two centers is (62, 30), which on the console is
        // (49, 28): the two glyphs, sixteen by sixteen, start eight to the
        // left and eight up.
        let game = with_counter(true, &FORTITUDE);
        let code = compile_with(&game, &[cmd(CALL_EVENT, &[0, 9, 0], "")]);
        assert_eq!(code.unwrap().unwrap(), [OP_COUNTER, 5, 41, 20, OP_DONE]);
    }

    #[test]
    fn a_digit_on_a_counters_picture_shows_the_counter() {
        let game = with_counter(true, &FORTITUDE);
        let show = |number: i32, name: &str| {
            cmd(
                SHOW_PICTURE,
                &[number, 0, 55, 30, 0, 100, 0, 1, 100, 100, 100, 100, 0, 0],
                name,
            )
        };
        let code = compile_with(&game, &[show(2, "9")]);
        assert_eq!(code.unwrap().unwrap(), [OP_COUNTER, 5, 41, 20, OP_DONE]);
        // Another image on it, or a digit on a picture that is not the
        // counter's, is still any picture: accepted without being done.
        for other in [show(2, "Fortitude"), show(1, "9")] {
            let code = compile_with(&game, &[other.clone()]);
            assert_eq!(code.unwrap().unwrap(), [OP_DONE]);
            assert_eq!(page_debts(&game, &[other], None).unwrap(), [SHOW_PICTURE]);
        }
        assert!(page_debts(&game, &[show(3, "4")], None).unwrap().is_empty());
    }

    #[test]
    fn an_undeclared_common_event_is_not_a_counter() {
        // Its body in place, and its pictures are any picture's.
        let game = with_counter(false, &FORTITUDE);
        let code = compile_with(&game, &[cmd(CALL_EVENT, &[0, 9, 0], "")]);
        assert_eq!(code.unwrap().unwrap(), [OP_DONE]);
    }

    #[test]
    fn a_counter_that_is_not_two_digits_in_fixed_places_stops() {
        let call = [cmd(CALL_EVENT, &[0, 9, 0], "")];
        for pictures in [
            vec![(2, 55, 30)],
            vec![(2, 55, 30), (3, 70, 30), (4, 85, 30)],
            vec![(2, 55, 30), (3, 70, 30), (3, 70, 40)],
        ] {
            let game = with_counter(true, &pictures);
            assert!(compile_with(&game, &call).is_err());
        }
    }

    #[test]
    fn a_destination_that_does_not_fit_a_byte_is_not_truncated() {
        // The game has 328 maps: 300 is one the old one-byte operand could
        // not name, and 300 & 0xFF is 44.
        let code = with_songs(
            &[cmd(TELEPORT, &[7, 12, 34], "")],
            &mut Songs::default(),
            &|_| Some(300),
        );
        assert_eq!(code.unwrap(), [OP_TELEPORT, 44, 1, 12, 0, 34, 0, OP_DONE]);
    }

    #[test]
    fn one_encounter_step_saturates_instead_of_not_compiling() {
        // `$10000 / 1` does not fit in the operand's word: it saturates, and
        // every threshold is the first step.
        let code = with_songs(
            &[cmd(CHANGE_ENCOUNTER_STEPS, &[1], "")],
            &mut Songs::default(),
            &|_| None,
        );
        assert_eq!(
            code.unwrap(),
            [OP_ENCOUNTER_STEPS, 0xFF, 0xFF, 1, 1, 1, 1, 2, 2, 2, 0xFF, OP_DONE]
        );
    }

    #[test]
    fn a_teleport_notes_the_song_it_carries() {
        // The jump right after a `PlayBGM` takes that song along, and the one
        // that is not, whatever is playing.
        let mut songs = Songs::default();
        let map_index = |m: i64| match m {
            20 => Some(1),
            30 => Some(2),
            _ => None,
        };
        let page = [
            cmd(TELEPORT, &[20, 1, 1], ""),
            cmd(PLAY_BGM, &[0, 100, 100, 50], "K"),
            cmd(TELEPORT, &[30, 1, 1], ""),
        ];
        assert!(with_songs(&page, &mut songs, &map_index).is_some());
        assert_eq!(
            songs.jumps,
            [(Package::Map(0), vec![(1, vec![None]), (2, vec![Some(0)])])]
        );
    }

    #[test]
    fn a_song_is_an_exit_one_only_if_every_playbgm_of_it_is() {
        // Only the first: an effect in the middle, a jump to the same map, no
        // jump, and a song that leaves in one page and not in another.
        let map_index = |m: i64| match m {
            3 => Some(0),
            4 => Some(1),
            _ => None,
        };
        let bgm = |name: &str| cmd(PLAY_BGM, &[0, 100, 100, 50], name);
        let wait = cmd(WAIT, &[10], "");
        let to_4 = cmd(TELEPORT, &[4, 9, 9], "");
        let to_3 = cmd(TELEPORT, &[3, 9, 9], "");
        let mut songs = Songs::default();
        for page in [
            vec![
                bgm("leaves"),
                wait.clone(),
                cmd(CONTROL_SWITCHES, &[0, 15, 15, 0], ""),
                to_4.clone(),
            ],
            vec![
                bgm("sounds"),
                cmd(PLAY_SOUND, &[100, 100, 50], "Thunder9"),
                to_4.clone(),
            ],
            vec![bgm("back"), wait.clone(), to_3],
            vec![bgm("stays"), wait.clone()],
            vec![bgm("twice"), to_4],
            vec![bgm("twice"), wait],
        ] {
            assert!(with_songs(&page, &mut songs, &map_index).is_some());
        }
        let exits: Vec<&str> = songs.exits[0]
            .1
            .iter()
            .filter(|(_, is_exit)| *is_exit)
            .map(|(s, _)| songs.names[*s].as_str())
            .collect();
        assert_eq!(exits, ["leaves"]);
    }

    #[test]
    fn a_free_inn_is_only_the_heal() {
        // With the price at zero `CommandShowInn` shows nothing and rests.
        let code = with_songs(
            &[cmd(SHOW_INN, &[0, 0, 0], "")],
            &mut Songs::default(),
            &|_| None,
        );
        assert_eq!(code.unwrap(), [OP_HEAL, 0, 0, 0, OP_DONE]);
    }

    #[test]
    fn what_the_characters_systems_do_to_the_party() {
        // The forms the troop pages use, each as the ROM reads it: see
        // `actor_change`, `actor_stat` and `ba_enemy_change`.
        let mut game = Game::default();
        game.actors.insert(14, vec![]);
        let one = |c: Command| compile_with(&game, &[c]).unwrap().unwrap();
        // `LifeForStrength`: 999 off Talan, lethal.
        assert_eq!(
            one(cmd(CHANGE_HP, &[1, 14, 1, 0, 999, 1], "")),
            [OP_ACTOR, 14, ACT_SUBTRACT | ACT_LETHAL, 0xE7, 0x03, OP_DONE]
        );
        // The one that adds a constant is still OP_HEAL.
        assert_eq!(
            one(cmd(CHANGE_HP, &[0, 0, 0, 0, 50, 0], "")),
            [OP_HEAL, 0, 50, 0, OP_DONE]
        );
        // By a variable: its slot, and 48 is the fifth.
        assert_eq!(
            one(cmd(CHANGE_SP, &[1, 14, 1, 1, 48], "")),
            [OP_ACTOR, 14, ACT_SP | ACT_SUBTRACT | ACT_VARIABLE, 5, 0, OP_DONE]
        );
        // Removing death gets the party up; another state, nothing.
        assert_eq!(
            one(cmd(CHANGE_CONDITION, &[0, 0, 1, 1], "")),
            [OP_ACTOR, 0, ACT_REVIVE, 0, 0, OP_DONE]
        );
        assert_eq!(one(cmd(CHANGE_CONDITION, &[0, 0, 1, 5], "")), [OP_DONE]);
        // Talan's HP into variable 48, asking for the refresh: without a map
        // there is no knowing that no page looks at it.
        assert_eq!(
            one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 5, 14, 2], "")),
            [OP_VAR, 5, 0x80, 5, 14, 0, 2, 0, OP_DONE]
        );
        // An enemy: 70 off the first, lethal; 40 SP off the second.
        assert_eq!(
            one(cmd(CHANGE_MONSTER_HP, &[0, 1, 0, 70, 1], "")),
            [OP_ENEMY, 0, ENEMY_LETHAL, 0xBA, 0xFF, OP_DONE]
        );
        assert_eq!(
            one(cmd(CHANGE_MONSTER_MP, &[1, 1, 0, 40], "")),
            [OP_ENEMY, 1, ENEMY_SP, 0xD8, 0xFF, OP_DONE]
        );
    }

    #[test]
    fn what_the_rom_cannot_do_to_the_party_does_not_compile() {
        let mut game = Game::default();
        game.actors.insert(14, vec![]);
        let fails = |c: Command| compile_with(&game, &[c]).unwrap().is_none();
        // An actor's level, and one the database does not have.
        assert!(fails(cmd(CONTROL_VARS, &[0, 48, 48, 0, 5, 14, 0], "")));
        assert!(fails(cmd(CONTROL_VARS, &[0, 48, 48, 0, 5, 15, 2], "")));
        // An enemy's HP by a percentage, and adding a state.
        assert!(fails(cmd(CHANGE_MONSTER_HP, &[0, 1, 2, 50, 1], "")));
        assert!(fails(cmd(CHANGE_CONDITION, &[0, 0, 0, 1], "")));
    }
}
