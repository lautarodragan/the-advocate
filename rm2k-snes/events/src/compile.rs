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
use rm2k_snes_bytecode::events::*;
use crate::pages::MapEvents;
use crate::registry::{Backdrop, BigPicture, Graphics, Package, PictureKey, Pictures, Songs, Troops};
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
const EQUIPMENT_SLOTS: i64 = rm2k_rules::actor::EQUIPMENT_SLOTS as i64;
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
// id. So the ROM does 1, 2, 4 and 5, and the rest does not compile:
//
// * **0** in RM2k returns 0 for an event —an RPG_RT defect easyrpg copies—, so
//   doing it would be copying a defect nobody uses;
// * **3** returns 8, 6, 2 or 4 —the numeric keypad— and not 0..3.
//
// **4** and **5** are pixels of **RM2k's** 320x240 screen and not of the
// console's: the ROM works out where RM2k's display would be, the same one
// the pictures are placed on —`pic_on_map`—, so the number is the original
// game's and a `ShowPicture` by those variables lands on the character. They
// were left out until 2026-10-11, when the pictures still did not speak
// RM2k's screen; the two uses are map 207's smoke over its chimney.
pub const VAR_CHARACTER: i64 = 6;
// And kind 5, an actor's data, of which the ROM does 2 to 5: the HP, the SP
// and their maximums. See `actor_stat` in runtime/level.s.
const VAR_ACTOR: i64 = 5;
const ACTOR_STAT_HP: i64 = 2;
const ACTOR_STAT_SP_MAX: i64 = 5;
const VAR_OTHER: i64 = 7;
const OTHER_GOLD: i64 = 0;
const OTHER_TIMER: i64 = 1;
const CHARACTER_X: i64 = 1;
const CHARACTER_Y: i64 = 2;
const CHARACTER_SCREEN_X: i64 = 4;
const CHARACTER_SCREEN_Y: i64 = 5;
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
/// `OP_CHOICE`'s cancel byte when cancel picks past the options: the
/// table's last entry is cancel's alone, and the cursor does not reach it.
/// See `op_choice`.
const CANCEL_PAST: i64 = 0xFF;
/// The timer's seconds: `CommandConditionalBranch` case 2.
pub const COND_TIMER: i64 = 2;
const COND_GOLD: i64 = 3;
const COND_ITEM: i64 = 4;
pub const COND_ACTOR: i64 = 5;
const COND_FACING: i64 = 6;
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
/// The cut and "none", which both compile to the cut, erasing and showing.
const RM2K_CUT_TRANSITIONS: [i64; 2] = [19, 20];
// What the bytecode carries: what the ROM does, and not the RM2k number.
const TRANSITION_FADE: u8 = 0;
const TRANSITION_MOSAIC: u8 = 1;
const TRANSITION_CUT: u8 = 2;
/// `EraseScreen` and `ShowScreen` with -1: whatever the teleport's is when
/// the command runs. See their arm.
const TRANSITION_TELEPORTS: u8 = 0xFF;
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
/// The escape parameter: 0 cannot, 1 ends the event processing, 2 has its
/// handler. Only 1 is asked about: `abort_on_escape` in easyrpg's
/// `CommandEnemyEncounter`, whose continuation calls `EndEventProcessing`
/// instead of `SetSubcommandIndex`. Here escaping goes to an `OP_DONE` put
/// right after the battle for it, which ends the whole page —a battle inside
/// a `CallEvent` compiled in place ends the caller too, which is what
/// `EndEventProcessing` does to the whole interpreter—.
const BATTLE_ESCAPE_ENDS: i64 = 1;
const BATTLE_DEFEAT_GAME_OVER: i64 = 0;
/// The destination that means "this does not continue: this is a Game
/// Over". It goes in the defeat's place when the `EnemyEncounter` carries
/// `defeat_mode` 0, which in RM2k is `Scene_Gameover`. It is an impossible
/// destination —all three are absolute within the page and none in the game
/// reaches 64 KB— so no new opcode or extra byte per battle is needed. The
/// ROM looks at it in `op_battle`.
const BATTLE_LOSE: usize = 0xFFFF;
/// `escape_mode` 0: the battle cannot be escaped from, which is easyrpg's
/// `args.allow_escape = (escape_mode != 0)`.
const BATTLE_NO_ESCAPE_MODE: i64 = 0;
/// The destination that means "this battle cannot be escaped from": it goes
/// in the escape's place with `escape_mode` 0, where that destination is
/// never taken, and the ROM's `op_battle` reads it before fighting to leave
/// the Escape command out. Like `BATTLE_LOSE`, an impossible destination,
/// so no new opcode or extra byte per battle is needed. Since 2026-10-04.
const BATTLE_NO_ESCAPE: usize = 0xFFFE;
/// The three handlers, in the order their destinations go in the opcode.
const BATTLE_HANDLERS: [i32; 3] = [VICTORY_HANDLER, ESCAPE_HANDLER, DEFEAT_HANDLER];
/// RM2k shows four options at most, and `GetChoices(4)` discards the ones
/// with a higher index. The ROM's window has four lines, so the cap is the
/// same on both sides.
const CHOICE_MAX: i64 = 4;
/// The most digits an `InputNumber` asks for that the ROM takes: six, which
/// is RM2k 2000's editor's cap. The ROM writes the number into a sixteen-bit
/// variable, saturating —see `number_value` in runtime/number_input.s—,
/// and its line is a cursor column and a digit per digit: twelve letters.
const NUMBER_DIGITS_MAX: i64 = 6;
// Where the two destinations go inside `OP_CELL_TEST` —see its declaration
// in rm2k-snes-bytecode—, and
// the top two bits of each write, over the variable's offset: y instead of
// x, and the refresh. See `cell_test` in runtime/interpreter_cells.s.
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
/// Empty since 2026-10-04: `MessageOptions` was here, as "where and how the
/// message window is drawn, which without messages is drawn nowhere", and
/// that held for the page that had it but not for the ones after it —it is
/// state, and it lasts—. It is `OP_MESSAGE_OPTIONS` now.
const IGNORABLE: [i32; 0] = [];
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
pub const ACCEPTED_UNDONE: [i32; 7] = [
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
    CHANGE_SYSTEM_BGM,
    CHANGE_HERO_TITLE,
    // Debt: the System is not changed on the fly. The task to implement it is
    // `tasks/changesystemgraphics.md`.
    CHANGE_SYSTEM_GRAPHICS,
    // Debt: the face is not drawn; see its arm.
    CHANGE_FACE_GRAPHIC,
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
    /// Actor to the name `\N[n]` bakes into the text: see
    /// [`crate::indices::hero_names`].
    pub hero_names: BTreeMap<i32, String>,
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
    /// The pictures the map carries —or, in the scan, the ones being
    /// gathered—: see [`Pictures`].
    pub pictures: Option<&'a mut Pictures>,
    /// The troops the cartridge is going to have to carry. **It does not
    /// change the bytecode** —the troop number emitted is RM2k's— so a ROM
    /// without a registry compiles exactly the same; the only thing lost is
    /// knowing which tables have to be emitted.
    pub troops: Option<&'a mut Troops>,
    /// Set when compiling a **shared common event body** —see
    /// [`crate::commons`]—: each common event that has one, by number, and
    /// its index. A `CallEvent` there is an `OP_CALL` to the callee's body
    /// and not its body in place, and the page ends in `OP_RETURN` and not
    /// in `OP_DONE`. None is everything else, which pastes as always.
    pub commons: Option<&'a BTreeMap<i32, u8>>,
    /// Set when compiling a map's page that runs in the foreground: the
    /// shared bodies it may call instead of pasting —see `shares`—. Not a
    /// parallel page's: the ROM has one call stack, the foreground's.
    pub shared: Option<&'a BTreeMap<i32, u8>>,
}

impl Ctx<'_> {
    /// What ends the frame being compiled: the page, or the shared body back
    /// to whoever called it. It is RM2k's `END` of a frame, and also its
    /// `EndEventProcessing`, which ends **only** the frame it runs in
    /// —`Game_Interpreter::EndEventProcessing`, easyrpg—.
    fn end(&self) -> u8 {
        if self.commons.is_some() {
            OP_RETURN
        } else {
            OP_DONE
        }
    }
}

// --- bytes ---------------------------------------------------------------------

/// A value that has to be a byte. One that is not leaves the page out, like
/// any command the ROM cannot carry: until 2026-10-06 it stopped the whole
/// conversion, and a game with a switch past 255 in a route (Vampires Dawn's
/// 263) could not be built for one command.
fn byte(v: i64) -> Step<u8> {
    u8::try_from(v).map_err(|_| Stop::Cannot)
}

/// A word, little-endian: `v & 0xFF` and `v >> 8`, and the second has to fit.
fn word(v: i64) -> Step<[u8; 2]> {
    Ok([(v & 0xFF) as u8, byte(v >> 8)?])
}

fn usize_word(v: usize) -> Step<[u8; 2]> {
    word(v as i64)
}

/// `OP_MESSAGE_OPTIONS`'s bits above the position, which takes 0 and 1:
/// `MSG_BARE`, `MSG_DODGE` and `MSG_CONTINUE` in the runtime's `far_ram.s`.
const MESSAGE_BARE: u8 = 0x04;
const MESSAGE_DODGE: u8 = 0x08;
const MESSAGE_CONTINUE: u8 = 0x10;

fn cannot<T>() -> Step<T> {
    Err(Stop::Cannot)
}

/// A `PlayBGM`'s volume, tempo and balance as `OP_BGM` carries them: the
/// gain of each side in 128ths and the music frames per video frame in
/// 256ths. 100, 100 and 50 —the editor's defaults— are 128, 128 and 256: the
/// song as written.
///
/// * **The volume** is what easyrpg's MIDI path does, and the game's songs
///   are all MIDI: it scales each channel's CC7 —`AudioDecoderMidi::SetVolume`
///   sends `channel_volumes[i] * volume`—. The stream already went through
///   that CC7 squared —see `volume` in rm2k-snes-audio's sdsp.rs—, so a
///   volume of 50 is a quarter of the amplitude.
/// * **The balance** is easyrpg's curve for audio without MIDI messages
///   —`ApplyLogVolume`—: the opposite side drops 6 dB every 10 away from 50.
///   Its MIDI path moves each channel's pan instead, which the stream already
///   baked into each voice; scaling the sides is the cheap approximation, and
///   only one `PlayBGM` of the game asks for a balance other than 50.
/// * **The tempo** is the MIDI one: the song goes faster or slower and the
///   pitch stays —`AudioDecoderMidi` advances its clock by `pitch / 100`—.
///   It is clamped to the editor's range, 50 to 150, which also keeps
///   `irq_music` at two music frames at most per video frame; the game asks
///   for 50 to 110.
pub fn bgm_level(volume: i64, tempo: i64, balance: i64) -> (u8, u8, u16) {
    let gain = (volume.clamp(0, 100) as f64 / 100.0).powi(2);
    let balance = balance.clamp(0, 100);
    let drop = |away: i64| 0.5012f64.powf(away.max(0) as f64 / 10.0);
    let side = |g: f64| (128.0 * gain * g).round().clamp(0.0, 128.0) as u8;
    let step = (256.0 * tempo.clamp(50, 150) as f64 / 100.0).round() as u16;
    (side(drop(balance - 50)), side(drop(50 - balance)), step)
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
    /// Whether cancel picks past the options: see `SHOW_CHOICE`.
    past: bool,
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
    /// `escape_mode` 1: escaping ends the page. See `BATTLE_ESCAPE_ENDS`.
    escape_ends: bool,
    /// `escape_mode` 0: it cannot be escaped from. See `BATTLE_NO_ESCAPE`.
    no_escape: bool,
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

/// The commands that close a block: what follows a label for a jump into
/// that block to be the same in RM2k and here. See [`label_targets`].
const BLOCK_ENDS: [i32; 6] = [
    COND_END,
    SHOW_CHOICE_END,
    END_BATTLE,
    INN_END,
    END_LOOP,
    BATTLE_COND_END,
];

/// Where each `JumpToLabel` lands: the index of its `Label`, or None if the
/// page has none with its number. It is what `CommandJumpToLabel` does:
///
/// * **The first `Label` of the list with that number wins**, wherever it
///   is: before or after the jump, and at any indentation —the search
///   walks the whole list from the top and looks at nothing but the
///   number—. A second one with the same number is never reached.
/// * **A jump to a number with no `Label` does nothing**: the page goes on
///   with the next command.
/// * The list is the frame's: a `CallEvent`'s body looks only at its own
///   labels, which is what compiling it apart with `page` already does.
///
/// **Landing inside a block is where it stops being free.** RM2k keeps no
/// stack of open blocks, only a sub-index per indentation
/// (`subcommand_path`), and what follows the body decides: an `ElseBranch`,
/// a `ShowChoiceOption` or a battle handler **runs or skips its body by that
/// sub-index**, which is whatever the last block at that indentation left
/// in it —usually "none", but a branch that was false and had no `else`
/// leaves "else", and then the `else` would run too—. Here those are jumps
/// to the end of the block, always. So a jump compiles only if every block
/// the label is in and the jump is not, the label is in its **last** body:
/// after it comes the block's end, which does nothing in RM2k and nothing
/// here. The game's jumps into blocks —the 13 of common event 39, into the
/// `else` of a chain of branches— are all like that. Jumping **out** of a
/// block is free: the ROM keeps no state for the ones that compile, and
/// `Loop`, the one that might, does not compile.
fn label_targets(commands: &[Command]) -> Step<HashMap<usize, Option<usize>>> {
    let mut first: HashMap<i32, usize> = HashMap::new();
    for (i, c) in commands.iter().enumerate() {
        if c.code == LABEL {
            first
                .entry(c.parameters.first().copied().unwrap_or(0))
                .or_insert(i);
        }
    }
    let mut out = HashMap::new();
    for (i, c) in commands.iter().enumerate() {
        if c.code != JUMP_TO_LABEL {
            continue;
        }
        let Some(&t) = first.get(&c.parameters.first().copied().unwrap_or(0)) else {
            out.insert(i, None);
            continue;
        };
        // The bodies both are in: the indentations below the shallowest
        // command between them, inclusive. A command at indentation k in
        // between —an `else`, an option, another block— means that from k
        // on they are in different bodies.
        let shared = commands[i.min(t)..=i.max(t)]
            .iter()
            .map(|c| c.indent)
            .min()
            .unwrap_or(0);
        for k in shared..commands[t].indent {
            let after = commands[t + 1..].iter().find(|c| c.indent <= k);
            match after {
                Some(c) if c.indent == k && BLOCK_ENDS.contains(&c.code) => {}
                _ => return cannot(),
            }
        }
        out.insert(i, Some(t));
    }
    Ok(out)
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
    match judged_page(ctx, commands, map_events, base, depth) {
        Ok(code) => Ok(Some(code)),
        Err((Stop::Cannot, _)) => Ok(None),
        Err((Stop::Fatal(bad), _)) => Err(bad),
    }
}

/// Which command a page stopped at: its index in the page, or None if it
/// stopped at the page as a whole —a block left open, a `JumpToLabel` out of
/// its body—. It is the command being compiled when the "no" came, so a
/// command that is fine and closes a block whose opener was not is the one
/// named. What a `CallEvent` pastes is not looked into: a called body that
/// does not compile is skipped, it does not stop the page.
pub type Culprit = Option<usize>;

/// [`compile_page`], saying where it stopped when it stops: see [`Culprit`].
/// Only the culprit report asks; the code is the same.
pub fn judged_page(
    ctx: &mut Ctx,
    commands: &[Command],
    map_events: Option<MapEvents>,
    base: usize,
    depth: usize,
) -> std::result::Result<Vec<u8>, (Stop, Culprit)> {
    let mark = ctx.messages.as_ref().map(|m| m.mark());
    let mut at = None;
    match page(ctx, commands, map_events, base, depth, &mut at) {
        Ok(code) => {
            whole_instructions(&code).map_err(|bad| (Stop::Fatal(bad), None))?;
            Ok(code)
        }
        Err(Stop::Cannot) => {
            if let (Some(m), Some(mark)) = (ctx.messages.as_deref_mut(), mark) {
                m.rewind(mark);
            }
            Err((Stop::Cannot, at))
        }
        Err(fatal) => Err((fatal, at)),
    }
}

/// `at` is the command being compiled, for [`judged_page`]: set at the top
/// of each turn of the loop and cleared after it, so a "no" from anywhere
/// in between —however deep, through whichever `?`— names it.
fn page(
    ctx: &mut Ctx,
    commands: &[Command],
    mut map_events: Option<MapEvents>,
    base: usize,
    depth: usize,
    at: &mut Culprit,
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
    // Each `ShowMessage` an `InputNumber` follows, with the `InputNumber`:
    // they go in one window. See [`compile_number`].
    let numbers = number_inputs(commands);
    let input_after: HashMap<usize, usize> = numbers.iter().copied().collect();
    let joined: BTreeSet<usize> = numbers.iter().map(|&(_, j)| j).collect();
    let mut choices: Vec<Choice> = Vec::new();
    let mut battles: Vec<Battle> = Vec::new();
    // The pending `PlayBGM`, what was noted and the jumps: see `follow_exit`.
    let mut exit = Exit::default();
    // The last thing the page put in each variable, if it was a constant:
    // see `recalled_destination`.
    let mut constants: HashMap<i64, i64> = HashMap::new();
    let mut faded: Vec<u8> = Vec::new();
    // Where each `JumpToLabel` lands, where each `Label` was emitted, and the
    // jumps forward, patched at the end: see [`label_targets`].
    let targets = label_targets(commands)?;
    let mut label_at: HashMap<usize, usize> = HashMap::new();
    let mut forward: Vec<(usize, usize)> = Vec::new();

    for (i, extra) in group_boxes(commands) {
        *at = Some(i);
        let cmd = &commands[i];
        if joined.contains(&i) {
            // Its window is the message's, already emitted.
            continue;
        }
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
            let branches = [branch_bytes(ctx, &loose[2], map_events.as_ref())?, branch_bytes(ctx, &loose[3], map_events.as_ref())?];
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
            let escape_ends = cmd.p(3) == Some(BATTLE_ESCAPE_ENDS);
            let no_escape = cmd.p(3) == Some(BATTLE_NO_ESCAPE_MODE);
            if no_block.contains(&i) {
                // No handlers: the battle closes right here. Winning and
                // escaping continue with the command below —which is what
                // RM2k does when there are no branches— and losing goes to
                // `BATTLE_LOSE`, that is to the Game Over.
                //
                // With `escape_mode` 0 —escape forbidden— the escape's
                // destination says so, `BATTLE_NO_ESCAPE`, and the battle
                // leaves Escape out. Until 2026-10-04 it pointed to the
                // victory's and the battle let you escape anyway.
                //
                // With `escape_mode` 1 the `OP_DONE` that escaping goes to
                // follows the opcode, and the other two skip it.
                let done_at = length + 9;
                let next_at = done_at + usize::from(escape_ends);
                let escape = if no_escape {
                    BATTLE_NO_ESCAPE
                } else if escape_ends {
                    done_at
                } else {
                    next_at
                };
                let lose = if losing_is_game_over {
                    BATTLE_LOSE
                } else {
                    next_at
                };
                let mut p = vec![OP_BATTLE];
                p.extend(word(troop)?);
                p.extend(usize_word(next_at)?);
                p.extend(usize_word(escape)?);
                p.extend(usize_word(lose)?);
                if escape_ends {
                    p.push(ctx.end());
                }
                piece = p;
            } else {
                battles.push(Battle {
                    at: pieces.len(),
                    troop,
                    destinations: [None; 3],
                    game_over: losing_is_game_over,
                    escape_ends,
                    no_escape,
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
            // With `escape_mode` 1 the block ends in an `OP_DONE` for the
            // escape, behind a jump that the last handler's body falls into
            // and that skips it. The handlers' way out is past both.
            let ends = current.escape_ends && current.destinations[1].is_none();
            let end = if ends { length + 4 } else { length };
            let mut table = vec![OP_BATTLE];
            table.extend(word(current.troop)?);
            for (n, dest) in current.destinations.iter().enumerate() {
                // The handler the page does not have falls at the end of the
                // block, which is what RM2k does with a sub-index without a
                // branch: `SetSubcommandIndex` and carry on. **Except the
                // defeat with `defeat_mode` 0**, which there is not a missing
                // branch but the Game Over: see `BATTLE_LOSE`; and the escape
                // with `escape_mode` 1, which ends the page.
                let d = match dest {
                    None if n == 2 && current.game_over => BATTLE_LOSE,
                    None if n == 1 && current.no_escape => BATTLE_NO_ESCAPE,
                    None if n == 1 && ends => length + 3,
                    None => end,
                    Some(d) => *d,
                };
                table.extend(usize_word(d)?);
            }
            pieces[current.at] = table;
            for out in current.exits {
                pieces[out] = with_dest(&pieces[out], end)?;
            }
            piece = if ends {
                let mut p = vec![OP_GOTO];
                p.extend(usize_word(end)?);
                p.push(ctx.end());
                p
            } else {
                vec![]
            };
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
            let mut cancel = cmd.p(0).unwrap_or(0);
            // **Cancelling to an option that is not there runs none**:
            // `choice_result` is `cancel_type - 1`, no `ShowChoiceOption`
            // carries that index —`CommandOptionGeneric` skips them all— and
            // the page goes on after the `ShowChoiceEnd`. It is the shop of
            // map 348, which gives 4 to a choice of two. Here it is one more
            // entry in the table, after the options, whose destination is the
            // end of the choice; the cursor never reaches it, only cancel.
            // The length counts it —it is what walks the code past the
            // table— and the cancel byte is [`CANCEL_PAST`], which tells the
            // ROM that the last entry is cancel's alone.
            //
            // `cancel_type` 5 with four options is the "cancel branch", a
            // fifth `ShowChoiceOption` with index 4: that one still does not
            // compile, because the option's index is checked against the
            // list. Nobody uses it in the game.
            let past = cancel > options.len() as i64;
            if past {
                cancel = CANCEL_PAST;
            }
            // OP_CHOICE: how many options (byte), what cancel does (byte),
            // and then one entry per option: the text box (word) and the
            // destination (word). It is `ShowChoice`.
            //
            // **One text box per option**, and since 2026-10-04 all of them
            // the same one: see `choice_boxes`. Moving the cursor is
            // recomposing the window with the bar under another line.
            //
            // The destination is absolute within the page, like OP_IF's, and
            // each option's body ends in an OP_GOTO to the end of the choice.
            let frames = choice_boxes(options, ctx.messages.as_deref_mut().unwrap())?;
            choices.push(Choice {
                at: pieces.len(),
                n: options.len(),
                cancel,
                past,
                frames,
                destinations: vec![None; options.len()],
                seen: 0,
                exits: vec![],
            });
            // The table's room, filled in at the `ShowChoiceEnd`.
            piece = vec![0; 3 + 4 * (options.len() + past as usize)];
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
            let entries = current.n + current.past as usize;
            let mut table = vec![OP_CHOICE, byte(entries as i64)?, byte(current.cancel)?];
            for (frame, dest) in current.frames.iter().zip(&current.destinations) {
                table.extend(usize_word(*frame)?);
                table.extend(usize_word(dest.unwrap())?);
            }
            if current.past {
                // The box is the last option's, which is never drawn from
                // here: cancelling closes the window.
                table.extend(usize_word(*current.frames.last().unwrap())?);
                table.extend(usize_word(length)?);
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
            piece = branch_bytes(ctx, cmd, map_events.as_ref())?;
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
        } else if cmd.code == LABEL {
            label_at.insert(i, length);
            piece = vec![];
        } else if cmd.code == JUMP_TO_LABEL {
            // OP_GOTO to where the label was emitted, or nothing if the page
            // has no label with that number.
            piece = match targets[&i] {
                None => vec![],
                Some(t) => match label_at.get(&t) {
                    Some(&dest) => {
                        let mut p = vec![OP_GOTO];
                        p.extend(usize_word(dest)?);
                        p
                    }
                    None => {
                        forward.push((pieces.len(), t));
                        vec![OP_GOTO, 0, 0]
                    }
                },
            };
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
        } else if let Some(&j) = input_after.get(&i) {
            piece = compile_number(ctx, cmd, &extra, &commands[j])?;
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
                let common = map_events.as_ref().map(MapEvents::in_a_common);
                let code = compile_page(ctx, &body, common, at, depth + 1)?;
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
    *at = None;
    if !stack.is_empty() || !choices.is_empty() || !battles.is_empty() {
        return cannot();
    }
    for (at, t) in forward {
        patch(&mut pieces, Open::End(at), label_at[&t])?;
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
        code.push(ctx.end());
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
    // A troop page leaves no map: it has no `Teleport`, and its `PlayBGM`
    // plays in the battle and not on the way out of a map.
    if current == Some(Package::Battle) {
        return;
    }
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
    if p[0] == 0 && ctx.game.patches.menus.replaced.contains_key(&p[1]) {
        return Ok(crate::commons::menu_open(ctx.game, p[1]));
    }
    if let (0, Some(commons)) = (p[0], ctx.commons) {
        // Inside a shared body, a call to another: `OP_CALL` to its body, or
        // nothing if it has none, which is the same skip as a pasted call
        // whose body does not compile. See [`crate::commons`].
        return Ok(match commons.get(&p[1]) {
            Some(&index) => vec![OP_CALL, index],
            None => vec![],
        });
    }
    if let (0, Some(shared)) = (p[0], ctx.shared) {
        if let Some(&index) = shared.get(&p[1]) {
            if shares(ctx, p[1], shared, map_events)? {
                return Ok(vec![OP_CALL, index]);
            }
        }
    }
    let (body, context) = if p[0] == 0 {
        // A common event, by number. The game's are cut almost all of them
        // at `ControlVars` and at the original's own menus.
        (
            ctx.game
                .common_events
                .get(&p[1])
                .map(|c| c.commands.clone()),
            map_events.map(MapEvents::in_a_common),
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

/// Whether a page of this map can call common event `number`'s shared body
/// instead of pasting it: whether the body compiled **with this map** is
/// byte for byte the body compiled **without a map**, which is the one in
/// the cartridge. Both are compiled here, as shared bodies, with the page's
/// registries.
///
/// What a map changes in a body is what it resolves against the map: a
/// map's event —a route, a flash, "this event"—, a graphic of its sprite
/// bank, a picture it carries, an effect that sounds with another sample
/// there, a `TileSubstitution`. Without a map those do not compile, or
/// compile to something else, so the two differ and the page pastes as
/// always.
///
/// **Except the refresh**: a write to a variable asks for the page refresh
/// only if a page condition of the map looks at it —see [`refresh`]—, and
/// without a map it always asks. So the body with the map is compiled as if
/// the map did not know who looks at what, which is what is left in the
/// cartridge: a call asks for more refreshes than the pasted body did. It
/// costs nothing that shows from a page that runs in the foreground: the
/// refresh is a flag, and it runs once when the interpreter lets go, not
/// once per write —see `events_tick`—. From a parallel one, which runs every
/// frame, it was the thirty frames per second of Lashe City: those do not
/// call.
///
/// And what compiling it here leaves in the registries is what the pasted
/// body would leave: its effects noted in this map's package, so they sound
/// here; its troops asked for. Its texts are taken back: the body's go into
/// the block when it is compiled for the cartridge.
fn shares<'a>(
    ctx: &mut Ctx<'a>,
    number: i32,
    shared: &'a BTreeMap<i32, u8>,
    map_events: Option<&MapEvents>,
) -> Step<bool> {
    let Some(common) = ctx.game.common_events.get(&number) else {
        return Ok(false);
    };
    let commands = common.commands.clone();
    let mark = ctx.messages.as_ref().map(|m| m.mark());
    let mut here = map_events.cloned();
    if let Some(m) = here.as_mut() {
        m.watched = None;
        m.in_common = true;
    }
    let (commons, shared_before) = (ctx.commons, ctx.shared);
    ctx.commons = Some(shared);
    ctx.shared = None;
    let with_map = compile_page(ctx, &commands, here, 0, 0);
    // And as the cartridge's is compiled: no map's events, graphics or
    // pictures, and no package, which is where an effect's sample per map
    // comes from.
    let (graphics, pictures) = (ctx.graphics.take(), ctx.pictures.take());
    let package = ctx.songs.as_mut().and_then(|s| s.current.take());
    let without = compile_page(ctx, &commands, None, 0, 0);
    if let Some(songs) = ctx.songs.as_mut() {
        songs.current = package;
    }
    ctx.graphics = graphics;
    ctx.pictures = pictures;
    ctx.commons = commons;
    ctx.shared = shared_before;
    if let (Some(m), Some(mark)) = (ctx.messages.as_deref_mut(), mark) {
        m.rewind(mark);
    }
    let (with_map, without) = (with_map.map_err(Stop::Fatal)?, without.map_err(Stop::Fatal)?);
    Ok(with_map.is_some() && with_map == without)
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

/// The box of a choice's options, once per option: the table of
/// `OP_CHOICE` carries one per option.
///
/// They are the same box. Until 2026-10-04 each one carried a ">" on its
/// option's line and moving the cursor was showing another; since then the
/// cursor is the System's bar, which the console composes under the
/// option `pick_sel` points at —see `prime_line` in the runtime—, and it
/// also puts the options' text further in. `Messages` deduplicates by
/// content, so the box is stored once. The table keeps its shape so the
/// opcode does not change.
fn choice_boxes(options: &[(i64, String)], messages: &mut Messages) -> Step<Vec<usize>> {
    let lines: Vec<String> = options.iter().map(|(_, t)| t.clone()).collect();
    let at = messages.add(&lines)?;
    Ok(vec![at; options.len()])
}

/// Where a `ShowMessage` is followed by an `InputNumber` that goes in its
/// window, as (the message's position, the `InputNumber`'s).
///
/// It is `CommandShowMessage`: after gathering the `ShowMessage_2`s it looks
/// at the next command, and an `InputNumber` there goes into the same
/// message if the box leaves it a line —`pm.NumLines() < 4`—. Otherwise
/// the `InputNumber` is one on its own, a window with no text, which the
/// ROM does not do: the game's two are both after a message of two and
/// three lines.
fn number_inputs(commands: &[Command]) -> Vec<(usize, usize)> {
    let groups = group_boxes(commands);
    groups
        .windows(2)
        .filter(|w| {
            let (i, extra) = &w[0];
            commands[*i].code == SHOW_MESSAGE
                && commands[w[1].0].code == INPUT_NUMBER
                && 1 + extra.len() < 4
        })
        .map(|w| (w[0].0, w[1].0))
        .collect()
}

/// `ShowMessage` and the `InputNumber` that goes in its window, in one
/// opcode.
///
/// OP_NUMBER: the variable's slot (byte), how many digits (byte) and the
/// message's box (word). The box is the message's as it is, and the ROM
/// writes the digits' line below its lines, from RAM: what changes when the
/// player presses up or down is that line, and nothing of it is in the text
/// block. See `op_number` in runtime/number_input.s.
///
/// It is **one** opcode and not `OP_MESSAGE` and then another one because
/// in RM2k the message does not wait for A when a number follows it: the
/// digits appear when its text finishes, and A is what enters the number.
fn compile_number(
    ctx: &mut Ctx,
    cmd: &Command,
    extra: &[String],
    input: &Command,
) -> Step<Vec<u8>> {
    let (Some(digits), Some(variable)) = (input.p(0), input.p(1)) else {
        return cannot();
    };
    if !(1..=NUMBER_DIGITS_MAX).contains(&digits) {
        return cannot();
    }
    let slot = ctx.indices.variable_slot(variable)?;
    let Some(messages) = ctx.messages.as_deref_mut() else {
        return cannot();
    };
    let mut lines = vec![cmd.string.clone()];
    lines.extend_from_slice(extra);
    let at = messages.add(&lines)?;
    let mut out = vec![OP_NUMBER, slot, digits as u8];
    out.extend(usize_word(at)?);
    Ok(out)
}

// --- branches ----------------------------------------------------------------------

/// A `ConditionalBranch` of the kinds this knows, with the destination
/// blank: switch, variable, gold, item, and three of the actor's seven
/// questions. The polarity is RM2k's as is.
/// The long whys of these conditions are in `git show 1487129f^:tools/port/events.py`.
fn branch_bytes(ctx: &Ctx, cmd: &Command, map_events: Option<&MapEvents>) -> Step<Vec<u8>> {
    let p = |i: usize| cmd.p(i);
    if cmd.parameters.len() < 3 {
        return cannot();
    }
    let kind = p(0).unwrap();
    let number = p(1).unwrap();
    if kind == COND_FACING {
        // Which way a character faces, `CommandConditionalBranch` case 6:
        // the character is the hero, "this event" or an event of the map,
        // addressed as in a route. The direction is RM2k's facing —0 up, 1
        // right, 2 down, 3 left— and so is the ROM's. No polarity: the
        // branch below is the `else`.
        let direction = p(2).unwrap();
        if !(0..=3).contains(&direction) {
            return cannot();
        }
        let mut out = vec![OP_IF_FACING, target_of(number, map_events)?, direction as u8];
        out.extend([0, 0]);
        return Ok(out);
    }
    if kind == COND_SWITCH {
        if !(0..SWITCH_MAX).contains(&number) {
            return cannot();
        }
    } else if kind == COND_GOLD || kind == COND_TIMER {
        // The timer is the gold's question with another value: the seconds
        // left —`GetTimerSeconds`— against the operand, `>=` with polarity 0
        // and `<=` with anything else. `CommandConditionalBranch` case 2.
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
        // starts with what `learned_skills` of `rm2k-rules` says from the
        // LDB and which `ChangeSkills` turns on and off. The operand that
        // travels is the pair's slot and not the skill; see `skills` in
        // [`crate::indices`].
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
        let comparison = p(4).unwrap();
        let (operand_kind, value) = match p(2).unwrap() {
            0 => {
                let v = p(3).unwrap();
                // **Equal and not equal take up to 65534**, as the sixteen
                // bits of the variable: the ROM compares the words, and
                // there the sign does not matter. It is Drust Camp's door
                // (map 68, event 10), which asks for 35421 after an
                // `InputNumber`, and `OP_NUMBER` writes what was entered
                // that way —saturated at 65535, which is why that one is
                // left out: it would also be every number above it—. Any
                // other comparison with a constant like that would be
                // signed, and it does not compile.
                let as_word = matches!(comparison, CMP_EQUAL | CMP_NOT_EQUAL)
                    && (0x8000..=0xFFFE).contains(&v);
                if !(-0x8000..=0x7FFF).contains(&v) && !as_word {
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
/// frames: see `cell_test` in runtime/interpreter_cells.s.
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
///   see runtime/game_over.s and what it still does not do in
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
/// runtime/level.s.
const ACT_SP: u8 = 0x01;
const ACT_REVIVE: u8 = 0x02;
const ACT_EQUIP: u8 = 0x04;
/// With `ACT_EQUIP`, OP_ACTOR's amount is the item with its slot on top.
const EQUIP_SLOT_SHIFT: i64 = 13;
/// The item types that equip without the weapon's business: armor, helmet
/// and accessory, which are their slot plus one.
const EQUIP_ARMOR: i64 = 3;
const EQUIP_ACCESSORY: i64 = 5;
const ACT_VARIABLE: u8 = 0x20;
const ACT_LETHAL: u8 = 0x40;
const ACT_SUBTRACT: u8 = 0x80;

/// OP_GOLD's sign byte: subtracting, and the amount as a variable's slot.
/// `GOLD_*` in runtime/interpreter_gold_and_items.s.
const GOLD_SUBTRACTS: u8 = 0x01;
const GOLD_BY_VARIABLE: u8 = 0x02;

/// OP_EXP's `what`: levels and not experience, note the level-up message
/// for the OP_LEVEL_PAGE that follows, the amount as a variable's slot, and
/// subtracting. `EXP_*` in runtime/level.s.
const EXP_BY_LEVELS: u8 = 0x01;
const EXP_WITH_MESSAGE: u8 = 0x02;
const EXP_BY_VARIABLE: u8 = 0x20;
const EXP_SUBTRACTS: u8 = 0x80;

/// OP_ENEMY's `what`: the SP and not the HP, and that a loss of HP can kill.
/// `ENEMY_*` in runtime/battle_troop.s.
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

/// `OP_PICTURE`'s `mode`: the position is two variable slots.
pub const PICTURE_BY_VARIABLE: u8 = 0x01;
/// And the picture goes with the map.
pub const PICTURE_MAP_FIXED: u8 = 0x02;

/// Whether the parameters of a `ShowPicture` or a `MovePicture` fall within
/// what the console's pictures know how to do: no rotation nor waves, the
/// saturation neutral, a zoom that shrinks, and a tone the tint's tables
/// cover.
///
/// The indices come from easyrpg-player's `CommandShowPicture` and
/// `CommandMovePicture`, **not from memory**: the color and the saturation
/// go in 8..11 and the effect mode in 12, which is not what one would
/// guess. The position is by variable with `p[1]` at 1 —`ValueOrVariable`—
/// and goes with the map with `p[4]`.
fn picture_fits(p: &[i32]) -> bool {
    picture_shows(p, 1) && p[11] == 100 && p[12] == 0
}

/// RM2k's effect modes, `p[12]`, and the strongest a wave goes in the
/// editor.
const EFFECT_NONE: i32 = 0;
const EFFECT_WAVE: i32 = 2;
const WAVE_MAX: i32 = 10;

/// What the console shows at all, in one plane or the other: [`picture_fits`]
/// and, for the big ones in the background layer, any saturation —the
/// tint's tables already do it— and the wave effect, which is a scroll per
/// line. Rotating stays out. `zoom_min` is 1 but for a big picture's
/// `MovePicture`, which can shrink it to nothing: see
/// [`compile_big_picture`].
fn picture_shows(p: &[i32], zoom_min: i32) -> bool {
    p.len() >= 14
        && (0..=1).contains(&p[1]) // position by constant or by variable
        && (zoom_min..=100).contains(&p[5]) // the zoom, which only shrinks
        && (0..=100).contains(&p[6]) // the transparency
        && (0..=200).contains(&p[11]) // the saturation
        && (p[12] == EFFECT_NONE || (p[12] == EFFECT_WAVE && (0..=WAVE_MAX).contains(&p[13])))
        && p[8..11].iter().all(|&v| (0..=200).contains(&v))
}

/// What a `ShowPicture` shows, if the console can show it: see
/// [`PictureKey`]. It takes the saturation and the wave the background
/// layer does, so a big picture is gathered with them; a small one that
/// asks for them is gathered and then not done, which no picture of the
/// game is —the only ones with either are the big `GTest4` and
/// `ShipFlash`—.
pub fn picture_key(cmd: &Command) -> Option<PictureKey> {
    let p = &cmd.parameters;
    if cmd.code != SHOW_PICTURE || !picture_shows(p, 1) {
        return None;
    }
    let (by_variable, map_fixed) = (p[1] == 1, p[4] != 0);
    Some(PictureKey {
        number: p[0],
        name: cmd.string.clone(),
        zoom: p[5],
        transparent_color: p[7] != 0,
        map_fixed,
        by_variable,
        at: (!by_variable && !map_fixed).then_some((p[2], p[3])),
    })
}

/// The three `Picture` commands, or None if the map does not carry this
/// picture.
///
/// `ShowPicture` (11110), `MovePicture` (11120) and `ErasePicture` (11130):
/// an image on top of everything, moved and erased. Since 2026-09-12 one
/// was done, the "One year previously" picture; **since 2026-10-01, the
/// ones each map carries in its sprite bank** —see [`Pictures`]—, as many as
/// the console has slots for. What the caller did not put in is still
/// accepted without being done, and that is what the pictures too big for
/// the sprites are until they have a plane of their own.
///
/// ```text
/// OP_PICTURE        slot, image, mode, x, y, r, g, b, transparency: puts
///                   the image up in the slot, centred at (x, y) of RM2k's
///                   screen —or of two variables—, with that tone.
/// OP_PICTURE_MOVE   slot, and the tone and transparency it goes to in how
///                   many frames (byte). It does not cut the frame: if the
///                   page waits, an OP_DELAY goes after it, as with
///                   `FlashScreen` and the shake.
/// OP_PICTURE_ERASE  slot: takes it down.
/// ```
///
/// **A `MovePicture` does not move**: the console keeps the place a picture
/// was put in and changes its tone and its transparency, which is all the
/// game's moves on pictures that fit do —the fades of the signs, the shadow
/// that appears—. So one compiles only if a picture of the map under that
/// number stays where it is: placed by a constant at the move's place, or
/// going with the map, whose position RM2k 2000 does not move either
/// (`Picture::Move`, `ignore_position` with `IsLegacy`). Nor does it zoom:
/// the zoom has to be the one it was shown with.
///
/// **The picture's fade is the tone and not the transparency**: the two
/// `MovePicture`s of the "1 year earlier" page leave `top_trans` at 0 and
/// move (r, g, b) between 0 and 100. The image appears **black**, goes up to
/// its color and back to black; on the console that is tinting its fifteen
/// CGRAM entries, the math the screen tint already did.
pub fn compile_picture(
    cmd: &Command,
    pictures: Option<&Pictures>,
    indices: &Indices,
) -> Step<Option<Vec<u8>>> {
    let p = &cmd.parameters;
    let Some(pictures) = pictures else {
        return Ok(None);
    };
    if cmd.code == ERASE_PICTURE {
        // The number can name a picture in the sprites and a big one; which
        // is up is not known until it runs, so both are taken down —the one
        // that is not up costs a byte to read—.
        let small = p.first().and_then(|&n| pictures.numbered(n).next()).map(|&(_, s)| s);
        let big = p.first().is_some_and(|&n| pictures.numbered_big(n).next().is_some());
        let mut out = Vec::new();
        if let Some(slot) = small {
            out.extend([OP_PICTURE_ERASE, slot]);
        }
        if big {
            out.extend([OP_PICTURE_ERASE, PICTURE_BIG]);
        }
        return Ok((!out.is_empty()).then_some(out));
    }
    if let Some(out) = compile_big_picture(cmd, pictures)? {
        return Ok(Some(out));
    }
    if !picture_fits(p) {
        return Ok(None);
    }
    let tone = [p[8] as u8, p[9] as u8, p[10] as u8, p[6] as u8];
    if cmd.code == SHOW_PICTURE {
        let Some(key) = picture_key(cmd) else {
            return Ok(None);
        };
        let Some((image, slot)) = pictures.image(&key) else {
            return Ok(None);
        };
        let mut mode = 0;
        let (x, y) = if key.by_variable {
            mode |= PICTURE_BY_VARIABLE;
            // A variable without a slot is a picture this cartridge cannot
            // place: accepted without being done, like one it does not carry.
            match (
                indices.variable_slot(p[2] as i64),
                indices.variable_slot(p[3] as i64),
            ) {
                (Ok(sx), Ok(sy)) => (sx as i64, sy as i64),
                _ => return Ok(None),
            }
        } else {
            (p[2] as i64, p[3] as i64)
        };
        if key.map_fixed {
            mode |= PICTURE_MAP_FIXED;
        }
        let (Ok(x), Ok(y)) = (i16::try_from(x), i16::try_from(y)) else {
            return Ok(None);
        };
        let mut out = vec![OP_PICTURE, slot, image, mode];
        out.extend(x.to_le_bytes());
        out.extend(y.to_le_bytes());
        out.extend(tone);
        return Ok(Some(out));
    }
    // MovePicture: the same pictures, where they are and at their size,
    // with another tone and transparency. The duration comes in **tenths**
    // —`data.time_left = duration * DEFAULT_FPS / 10`—, which is what had to
    // be looked up: the first one's 35 are three and a half seconds, not half
    // a second.
    // Which one it moves is not known until it runs —the number can show
    // another picture by then—, so it is enough that one of them stays: the
    // one this page showed, almost always. If another one is up, it gets the
    // tone and stays where it is, where RM2k would have moved it too.
    let Some(slot) = pictures
        .numbered(p[0])
        .find(|(key, _)| {
            let stays = key.map_fixed || (p[1] == 0 && key.at == Some((p[2], p[3])));
            stays && key.zoom == p[5]
        })
        .map(|(_, s)| *s)
    else {
        return Ok(None);
    };
    let Some(&tenths) = p.get(14) else {
        return Err(Stop::Fatal(Bad::answer(
            "a MovePicture without its duration",
        )));
    };
    let frames = tenths as i64 * FRAMES_PER_TENTH;
    if !(0..=PICTURE_FRAMES_MAX).contains(&frames) {
        return Ok(None);
    }
    let mut out = vec![OP_PICTURE_MOVE, slot];
    out.extend(tone);
    out.push(frames as u8);
    // `options.wait`: the page waits as long as it lasts, like `FlashScreen`.
    if p.len() > 15 && p[15] != 0 && frames != 0 {
        out.push(OP_DELAY);
        out.extend(word(frames)?);
    }
    Ok(Some(out))
}

/// The largest size `OP_BIG_ZOOM` takes, in percent of the size shown: what
/// its byte holds.
const ZOOM_SIZE_MAX: i32 = 255;

/// The slot `OP_PICTURE_ERASE` names the big picture with: it has one
/// place, the background layer, and no sprite slot. Bit 7, which no slot
/// reaches.
pub const PICTURE_BIG: u8 = 0x80;

/// A big picture's `ShowPicture` or `MovePicture`, or None if the command
/// is not about one the map carries as a background layer: see
/// [`BigPicture`].
///
/// ```text
/// OP_BIG_SHOW  image, r, g, b, transparency, saturation, wave: puts the
///              image up, where the conversion drew it, with that tone.
/// OP_BIG_MOVE  r, g, b, transparency, frames, y (word), wave, saturation:
///              the tone, the transparency, the centre's y and the wave it
///              goes to in how many frames; the saturation at once. Like
///              OP_PICTURE_MOVE, it does not wait: an OP_DELAY goes after.
/// ```
///
/// **The place is the conversion's**: the picture is drawn into the layer
/// where its `ShowPicture` puts it, so the image does not move sideways.
/// What a `MovePicture` can do is **scroll it up or down** —the layer is
/// taller than the screen when the picture is—, which is what the
/// instructions of map 285 do: `y` is RM2k's centre, and the console
/// computes the corner from it as RM2k does, with half the size of the
/// picture that is up —which one is, it only knows when it runs—.
///
/// **A zoom is done in mode 7, if the cartridge carries the picture with a
/// texture for it** —one that a `MovePicture` of its map zooms: see
/// [`Pictures::zooms`]—, which is what the photos of maps 212 to 216 do:
/// they shrink from 100 to 0 in two seconds on a black screen. Every move
/// of such a picture is an `OP_BIG_ZOOM`, with the size it goes to in
/// percent of the one it was shown at: the size it has when the move runs
/// is not known here.
///
/// ```text
/// OP_BIG_ZOOM  OP_BIG_MOVE's operands, and the size: see OP_BIG_MOVE.
/// ```
///
/// **Without a texture a zoom that shrinks is a fade**: the console does not
/// scale a background without mode 7, so the picture fades to black in that
/// time instead: the transparency it goes to is what is left of its area,
/// `100 - (100 - t) × zoom / shown`. See
/// `divergencias/lo-que-las-imagenes-grandes-no-modelan.md`.
///
/// **The transparency darkens**: under a big picture there is only the
/// screen's backdrop, which is black, so a picture half transparent is a
/// picture at half its colour. That is exact on a black screen, which is
/// where the big pictures of the game are shown.
fn compile_big_picture(cmd: &Command, pictures: &Pictures) -> Step<Option<Vec<u8>>> {
    let p = &cmd.parameters;
    if !picture_shows(p, 0) {
        return Ok(None);
    }
    let wave = |p: &[i32]| if p[12] == EFFECT_WAVE { p[13] as u8 } else { 0 };
    let tone = [p[8] as u8, p[9] as u8, p[10] as u8];
    if cmd.code == SHOW_PICTURE {
        let Some(big) = picture_key(cmd).and_then(|key| pictures.big_of(&key).cloned()) else {
            return Ok(None);
        };
        let mut out = vec![OP_BIG_SHOW, big.image];
        out.extend(tone);
        out.extend([p[6] as u8, p[11] as u8, wave(p)]);
        return Ok(Some(out));
    }
    // MovePicture: one of the number's big pictures that stays where it is
    // sideways and does not grow. Which one is up is not known until it
    // runs, as with the small ones, and a big one shown under the number is
    // what the game's pages move.
    if p[1] != 0 {
        return Ok(None);
    }
    // One with a texture can also grow past the size it was shown at: the
    // matrix of mode 7 does both. Up to what the size's byte holds.
    let size = |b: &BigPicture| p[5] * 100 / b.key.zoom.max(1);
    let Some(big) = pictures
        .numbered_big(p[0])
        .find(|b| b.center.0 == p[2] && (p[5] <= b.key.zoom || (b.texture && size(b) <= ZOOM_SIZE_MAX)))
        .cloned()
    else {
        return Ok(None);
    };
    let Some(&tenths) = p.get(14) else {
        return Err(Stop::Fatal(Bad::answer("a MovePicture without its duration")));
    };
    let frames = tenths as i64 * FRAMES_PER_TENTH;
    if !(0..=PICTURE_FRAMES_MAX).contains(&frames) {
        return Ok(None);
    }
    let Ok(y) = i16::try_from(p[3]) else {
        return Ok(None);
    };
    let mut out = if big.texture {
        let mut out = vec![OP_BIG_ZOOM];
        out.extend(tone);
        out.extend([p[6] as u8, frames as u8]);
        out.extend(y.to_le_bytes());
        out.extend([wave(p), p[11] as u8, size(&big) as u8]);
        out
    } else {
        let transparency = 100 - (100 - p[6]) * p[5] / big.key.zoom;
        let mut out = vec![OP_BIG_MOVE];
        out.extend(tone);
        out.extend([transparency as u8, frames as u8]);
        out.extend(y.to_le_bytes());
        out.extend([wave(p), p[11] as u8]);
        out
    };
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
    BYTECODE.fixed_size(op).unwrap()
}

/// How many bytes the instruction at `code[at]` takes, the variable-size
/// ones included.
pub fn instruction_size(code: &[u8], at: usize) -> usize {
    BYTECODE.size_at(code, at).unwrap()
}

/// That walking `code` by the declared sizes lands exactly on its end.
///
/// What it catches is the emitter and the interpreter counting different
/// bytes for one opcode: each piece is written by hand, and the
/// interpreter advances by what `rm2k-snes-bytecode` declares. If they disagree
/// the ROM reads the bytecode shifted, and that is no error: it is a page
/// that does anything. So every page is checked as it comes out, the
/// game's included —until 2026-10-02 it was a test of the game's that
/// walked its 3000-odd pages in Python—, and a mismatch stops the
/// conversion, because it is a bug of this compiler and not of the page.
fn whole_instructions(code: &[u8]) -> Result<()> {
    let mut at = 0;
    while at < code.len() {
        match BYTECODE.size_at(code, at) {
            Some(size) => at += size,
            None => break,
        }
    }
    if at == code.len() {
        Ok(())
    } else {
        Err(Bad::answer(format!(
            "the compiler emitted a page that does not walk by the declared \
             sizes —it ends at {at} and is {} bytes long—; it starts {}",
            code.len(),
            code.iter().take(32).map(|b| format!("{b:02X}")).collect::<Vec<_>>().join(" ")
        )))
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

/// A text box's lines with each `\N[n]` —the name of actor `n`— written as
/// the actor's name in the database, when no `ChangeHeroName` in the game
/// changes it: see [`crate::indices::hero_names`]. Both cases of the `N`.
/// `\N[0]` (the leader), a renamed actor and a malformed one are left as they
/// are, so the escape still stops the page in `escape_tail`.
pub fn with_names(lines: &[String], indices: &Indices) -> Vec<String> {
    lines
        .iter()
        .map(|line| {
            let chars: Vec<char> = line.chars().collect();
            let mut text = String::new();
            let mut i = 0;
            while i < chars.len() {
                if chars[i] == '\\' && matches!(chars.get(i + 1), Some('N' | 'n')) && chars.get(i + 2) == Some(&'[') {
                    let digits: String = chars[i + 3..].iter().take_while(|c| c.is_ascii_digit()).collect();
                    let close = i + 3 + digits.len();
                    let name = digits.parse::<i32>().ok().and_then(|n| indices.hero_names.get(&n));
                    if let (Some(name), Some(']')) = (name, chars.get(close).copied()) {
                        text.push_str(name);
                        i = close + 1;
                        continue;
                    }
                }
                text.push(chars[i]);
                i += 1;
            }
            text
        })
        .collect()
}

/// A text box's lines with each `\V[n]` —the value of variable `n`— as the
/// mark `Messages` writes as the variable's slot: see
/// [`crate::messages::VARIABLE`]. The ROM writes the digits when the box
/// opens, which is what easyrpg's `PendingMessage::DefaultCommandInserter`
/// does when the `ShowMessage` runs: the value in decimal, with a minus sign
/// if it is negative and no padding.
///
/// Only the plain form, `\V[` digits `]` with either case of the `V`, which
/// is the only one the game uses —three boxes, all of the portable
/// console—. The nested one, `\V[\V[n]]`, and one without brackets are left
/// as they are, so the escape still stops the page in `escape_tail`. A
/// variable without a slot does not compile.
pub fn with_variables(lines: &[String], indices: &Indices) -> Step<Vec<String>> {
    let mut out = Vec::with_capacity(lines.len());
    for line in lines {
        let chars: Vec<char> = line.chars().collect();
        let mut text = String::new();
        let mut i = 0;
        while i < chars.len() {
            if chars[i] == '\\' && matches!(chars.get(i + 1), Some('V' | 'v')) && chars.get(i + 2) == Some(&'[') {
                let digits: String = chars[i + 3..].iter().take_while(|c| c.is_ascii_digit()).collect();
                let close = i + 3 + digits.len();
                if !digits.is_empty() && chars.get(close) == Some(&']') {
                    let number: i64 = digits.parse().map_err(|_| Stop::Cannot)?;
                    text.push(crate::messages::variable_mark(indices.variable_slot(number)?));
                    i = close + 1;
                    continue;
                }
            }
            text.push(chars[i]);
            i += 1;
        }
        out.push(text);
    }
    Ok(out)
}

/// One command, as its opcodes. The ones built from several —branches,
/// choices, battles, the inn, calls— are the page's.
///
/// One opcode per command, with the operands already resolved: the ROM does
/// not look at the LCF again nor knows its numbers. **The numbers and
/// layouts are in `rm2k-snes-bytecode`**, not here: what each
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
        MESSAGE_OPTIONS => {
            // `CommandMessageOptions`: without the frame, the position,
            // whether it moves out of the hero's way —easyrpg stores the
            // opposite, `SetMessagePositionFixed(p[2] == 0)`— and whether the
            // events go on moving. It is state of the game and not of the
            // page: it lasts until the next one, and travels in the save, as
            // `SaveSystem` does.
            if n < 4 || !(0..=2).contains(&q(1)) {
                return cannot();
            }
            let mut options = q(1) as u8;
            if q(0) != 0 {
                options |= MESSAGE_BARE;
            }
            if q(2) != 0 {
                options |= MESSAGE_DODGE;
            }
            if q(3) != 0 {
                options |= MESSAGE_CONTINUE;
            }
            Ok(vec![OP_MESSAGE_OPTIONS, options])
        }
        PLAY_SOUND => {
            // PlaySound plays an effect: a door, a hit, Talan's Insta-Shave.
            // It sounds since 2026-09-11 (see OP_SOUND, below); until then it
            // was accepted without playing it, and it was the cheapest debt of
            // all the ones accepted undone: **it does not show**. The screen
            // being compared is exactly the same with and without sound.
            //
            // What made it costly was ARAM. The effects go in each map's
            // audio package, together with its songs —`package_load`, in
            // runtime/audio_package.s—, with the same per-pack budget
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
            // runtime/battle_troop.s. What it does not do is
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
        CHANGE_EXP | CHANGE_LEVEL => {
            // [type, id, subtracts, amount by variable, amount, message]:
            // `CommandChangeExp` and `CommandChangeLevel`, which are
            // `ChangeExp(GetExp() + value)` and `ChangeLevel(GetLevel() +
            // value)` on each actor of the target. Both are OP_EXP, the
            // second with `EXP_BY_LEVELS`; the ROM's `exp_change` does both.
            //
            // The game uses neither —measured on 2026-10-04 over the maps,
            // the common events and the troops—: they came for the debug
            // map's doors, which leave each actor at the level of someone
            // who played up to there.
            //
            // With the message, OP_LEVEL_PAGE right behind: OP_EXP notes the
            // lines and that one shows them, a page at a time. Without
            // anyone going up there is no page, as in RM2k, where an empty
            // `PendingMessage` opens nothing.
            //
            // Like `ChangeHP`, the actor by a variable does not compile.
            if n < 6 {
                return cannot();
            }
            let mut what = 0;
            if cmd.code == CHANGE_LEVEL {
                what |= EXP_BY_LEVELS;
            }
            if q(2) != 0 {
                what |= EXP_SUBTRACTS;
            }
            let amount = if q(3) != 0 {
                what |= EXP_BY_VARIABLE;
                ctx.indices.variable_slot(q(4))? as i64
            } else if (0..=rm2k_rules::actor::EXP_MAX).contains(&q(4)) {
                q(4)
            } else {
                return cannot();
            };
            if q(5) != 0 {
                what |= EXP_WITH_MESSAGE;
            }
            let mut out = vec![OP_EXP, target_actor(p)?, what];
            out.extend([
                (amount & 0xFF) as u8,
                ((amount >> 8) & 0xFF) as u8,
                (amount >> 16) as u8,
            ]);
            if what & EXP_WITH_MESSAGE != 0 {
                out.push(OP_LEVEL_PAGE);
            }
            Ok(out)
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
            // that equip belong to the troops. Unequipping everything does
            // not compile: nobody uses it.
            //
            // **Equipping**, operation 0 with the item in `b`, compiles since
            // 2026-09-30, for `Play Radio`: it puts one of four accessories on
            // Emily in battle. It is OP_ACTOR with `ACT_EQUIP`, and the item's
            // slot goes on top of its number, because the ROM does not carry
            // every item's type. Only on one actor, only a constant, and only
            // armor, helmet or accessory: the weapon and the shield are where
            // `CommandChangeEquipment` does its two-handed business, and the
            // game does not equip either from an event. One the actor cannot
            // use does nothing in RM2k —`IsItemUsable`— and here it is not
            // emitted.
            if n < 4 {
                return cannot();
            }
            if q(2) == 0 {
                if n < 5 || q(0) != 1 || q(3) != 0 {
                    return cannot();
                }
                let actor = target_actor(p)?;
                let Some((kind, users)) = ctx.game.items.get(&(q(4) as i32)) else {
                    return cannot();
                };
                if !(EQUIP_ARMOR..=EQUIP_ACCESSORY).contains(&(*kind as i64))
                    || !(1..ITEMS_N).contains(&q(4))
                {
                    return cannot();
                }
                if !users.get(actor as usize - 1).copied().unwrap_or(false) {
                    return Ok(vec![]);
                }
                let slot = *kind as i64 - 1;
                let mut out = vec![OP_ACTOR, actor, ACT_EQUIP];
                out.extend(word(q(4) | slot << EQUIP_SLOT_SHIFT)?);
                return Ok(out);
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
        // `BATTLE_LOSE`—: runtime/game_over.s.
        GAME_OVER => Ok(vec![OP_GAME_OVER]),
        // `ReturntoTitleScreen`: the same without the screen, that is going
        // back to boot, which in `release` is the title screen. The end of
        // the demo asks for it, in map 66's fork (`rom/parches/manual/`).
        // Until 2026-09-28 it shared the opcode with `GameOver`, when neither
        // of the two drew anything.
        RETURN_TO_TITLE => Ok(vec![OP_RETURN_TO_TITLE]),
        PLAYER_VISIBILITY => {
            // `CommandPlayerVisibility`: `hidden = p[0] == 0`. The ROM keeps
            // one byte of it, which the save carries.
            if n < 1 {
                return cannot();
            }
            Ok(vec![OP_HERO_VISIBLE, if q(0) != 0 { 1 } else { 0 }])
        }
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
            let Some(chosen) = graphics.index_capped(&cmd.string, p[1]) else {
                return cannot();
            };
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
            // `TRANSITION_ERASE` in runtime/far_ram.s—.
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
            // And the cut for **showing**: the new map at full brightness on
            // the tick after the load —`TransitionCutIn`, one frame in RM2k—,
            // with no ramp back up. Sunset Over Imdahl asks for it in the same
            // page that opens the game (map 22, ev1), and while it did not
            // compile the whole page was left out: the screen stayed in the
            // black tint map 11 leaves it in. "None" (20) for showing goes to
            // the cut too: in RM2k it is zero frames instead of one, and the
            // console cannot tell the two apart. The battle's do not compile:
            // the ROM always uses the database's.
            if n < 2 {
                return cannot();
            }
            let (which, rm2k) = (q(0), q(1));
            if which != TRANSITION_ERASE && which != TRANSITION_SHOW {
                // The battle's: the ROM always uses the database's.
                return cannot();
            }
            if RM2K_CUT_TRANSITIONS.contains(&rm2k) {
                return Ok(vec![OP_TRANSITION, which as u8, TRANSITION_CUT]);
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
            // a variable".
            //
            // OP_GOLD: sign (byte: GOLD_SUBTRACTS, GOLD_BY_VARIABLE) and a
            // 24-bit amount, or the variable's slot in its low byte. It goes
            // in three bytes because RM2k's cap is 999999 and the game uses
            // the whole value: there is a command that gives exactly that.
            if n >= 3 && q(1) == 1 {
                let slot = ctx.indices.variable_slot(q(2))?;
                let sign = if q(0) != 0 { GOLD_SUBTRACTS } else { 0 };
                return Ok(vec![OP_GOLD, sign | GOLD_BY_VARIABLE, slot, 0, 0]);
            }
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
            // —`package_load`, in runtime/audio_package.s—, and each
            // sample's budget is that of its worst pack: see
            // `workflow/decisiones/un-solo-banco-de-muestras.md`.
            //
            // OP_BGM: the song's index in `Songs` (byte). The ROM plays the
            // ones it carried —the first `SONG_TOTAL`— and with any other it
            // does nothing. See `Songs`. After it, the volume, the balance
            // and the tempo, in the console's units: see [`bgm_level`].
            //
            // Without a song registry it is accepted and not done, which is
            // what this repo did with PlayBGM from the start. With a registry
            // the index is emitted and the ROM plays the song if it got to
            // carry it.
            //
            // A troop page's is done too, since the evening of 2026-09-30:
            // its song is noted in the battle's audio package, like the
            // battle theme, and also as a troop song, which the cartridge's
            // plan puts apart —see `troop_songs`—. It is `Play Radio`'s,
            // which puts on one of three songs.
            let Some(songs) = ctx.songs.as_deref_mut() else {
                return Ok(vec![]);
            };
            if cmd.string.is_empty() {
                return Ok(vec![]);
            }
            let index = songs.index(&cmd.string);
            if songs.current == Some(Package::Battle) && !songs.troop_songs.contains(&index) {
                songs.troop_songs.push(index);
            }
            let at = |i: usize, default: i64| cmd.parameters.get(i).map_or(default, |&v| v as i64);
            let (left, right, step) = bgm_level(at(1, 100), at(2, 100), at(3, 50));
            Ok(vec![OP_BGM, (index & 0xFF) as u8, left, right, step as u8, (step >> 8) as u8])
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
        // runtime/bank1.s, which is the only place where it is written.
        // It costs no frame: in RM2k the menu blocks, and here there is
        // nothing to look at.
        OPEN_SAVE_MENU => Ok(vec![OP_SAVE]),
        SHOW_PICTURE | MOVE_PICTURE | ERASE_PICTURE => {
            if let Some(common) = counter_of_picture(ctx.game, cmd) {
                return compile_counter(ctx, common);
            }
            // The scan gathers what the page shows and emits nothing: its
            // bytecode is for knowing who walks, and a picture moves nobody.
            if let Some(p) = ctx.pictures.as_deref_mut().filter(|p| p.gathering) {
                if let Some(key) = picture_key(cmd) {
                    p.gather(key);
                }
                if cmd.code == MOVE_PICTURE && picture_shows(&cmd.parameters, 0) {
                    p.gather_zoom(cmd.parameters[0], cmd.parameters[5]);
                }
                return Ok(Vec::new());
            }
            // None is "the map does not carry this picture": it is accepted
            // without being done, which is what the three did until
            // 2026-09-12. Cutting the page would take away from the game the
            // pages that compile today because of it.
            Ok(compile_picture(cmd, ctx.pictures.as_deref(), ctx.indices)?.unwrap_or_default())
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
        // `ChangeSystemGraphics` (10680): debt, accepted without doing anything
        // so the page that uses it is not left out whole; the task to
        // implement it is `tasks/changesystemgraphics.md`.
        CHANGE_SYSTEM_GRAPHICS => Ok(vec![]),
        ERASE_SCREEN | SHOW_SCREEN => {
            // `EraseScreen` (11010) and `ShowScreen` (11020): the screen to
            // black and left there until the show, with the game frozen while
            // each transition lasts —EasyRPG's `AsyncOp::MakeEraseScreen`—.
            // `[transition]`: -1 the teleport's —which the ROM resolves when
            // it runs, because `ChangeScreenTransitions` changes it on the
            // fly—, and otherwise an index into the same table as
            // `ChangeScreenTransitions`, and it goes the same way: the
            // mosaic (17) is the mosaic, the cut (19) and anything past it
            // —"none" in EasyRPG, which RPG_RT does as a pause and black when
            // erasing and as nothing when showing— are the cut, and the rest
            // is the fade, which is what taro decided for the ones the
            // console does not do. Desert Nightmare asks for the fade, El
            // Dorado for the teleport's, and Vampires Dawn for the mosaic
            // too.
            //
            // What the ROM does with them is in `teleport_transition.s`:
            // the teleport's fade cut in half, and a teleport with the screen
            // erased loads in the black without showing it, as
            // `Scene_Map::FinishPendingTeleport2` does. A troop page never
            // gets here: `TROOP_COMMANDS` does not have them, and in battle
            // EasyRPG ignores them too.
            if n < 1 {
                return cannot();
            }
            let rm2k = q(0);
            let kind = if rm2k < 0 {
                TRANSITION_TELEPORTS
            } else if rm2k >= RM2K_CUT_TRANSITIONS[0] {
                TRANSITION_CUT
            } else if rm2k == RM2K_TRANSITION_MOSAIC {
                TRANSITION_MOSAIC
            } else {
                TRANSITION_FADE
            };
            let op = if cmd.code == ERASE_SCREEN { OP_ERASE_SCREEN } else { OP_SHOW_SCREEN };
            Ok(vec![op, kind])
        }
        // `ChangeFaceGraphic` (10130): debt, the face is not drawn; see
        // `workflow/tasks/*/las-caras-y-las-esperas.md`.
        CHANGE_FACE_GRAPHIC => Ok(vec![]),
        CHANGE_ENCOUNTER_STEPS => {
            // `ChangeEncounterSteps` (11740): every how many steps there is a
            // random encounter. Nineteen occurrences on nine maps, and
            // thirteen of them set it to **zero**, which in RM2k is turning
            // them off. Until 2026-09-27 it was left out because "there are no
            // random encounters"; there are since 2026-09-13 —see
            // `runtime/encounters.s`— and Dalia's trip to Tasgarde asked
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
        // `EraseEvent` **after the page jumped to another map** does
        // nothing: the jump put 0 in the event id of every frame of the
        // interpreter's stack —`Game_Interpreter_Map::OnMapChange`— and
        // `CommandEraseEvent` with 0 returns without erasing anyone. It is the
        // one of map 311, the clearing in Tangle Forest, which teleports to
        // 312 and erases itself there. **And in a common event**, whose
        // frame has no event either —`GetThisEventId` is 0—: without a map
        // (a shared body) and pasted into a map's page alike.
        ERASE_EVENT if map_events.is_none_or(|m| m.jumped || m.in_common) => Ok(vec![]),
        // Before the jump, in the page of an event, it erases it until the
        // map is loaded again: see `op_erase_event` in the runtime. A jump to
        // **the same map** is not a jump here —map 150's, where Sern starts
        // the quarry's work— and the erase after it is the real one.
        ERASE_EVENT => {
            let target = map_events.and_then(|m| m.route_target(ROUTE_THIS_EVENT));
            match target {
                Some(t) => Ok(vec![OP_ERASE_EVENT, byte(t as i64)?]),
                None => cannot(),
            }
        }
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
        // `ChangePBG`, `Game_Map::Parallax::ChangeBG`: how the panorama
        // loops and scrolls on its own from now on. The picture stays the
        // map's: one that names another would need its tiles converted and
        // uploaded mid-map, and that is not done —the name is not even
        // read—. Wally converts the map's panorama big enough for every way
        // the map's own pages make it loop. In a map that does not show its
        // panorama the ROM does nothing. See `op_panorama` in `pano.s`.
        //
        // OP_PANORAMA: loops (byte: bit 0 across, bit 1 down), and what it
        // moves on its own each frame across and down (signed words, 1/32
        // px), which is RM2k's `scroll_amt` and 0 on an axis that does not
        // loop or scroll on its own.
        CHANGE_PBG => {
            if n < 6 {
                return cannot();
            }
            let step = |looped: bool, auto: bool, speed: i64| -> i16 {
                match (looped && auto, speed) {
                    (false, _) | (_, 0) => 0,
                    (_, s) if s < 0 => 1 << -s,
                    (_, s) => -(1i16 << s),
                }
            };
            let (lx, ly) = (q(0) != 0, q(1) != 0);
            if !(-8..=8).contains(&q(3)) || !(-8..=8).contains(&q(5)) {
                return cannot();
            }
            let mut out = vec![OP_PANORAMA, u8::from(lx) | (u8::from(ly) << 1)];
            out.extend(step(lx, q(2) != 0, q(3)).to_le_bytes());
            out.extend(step(ly, q(4) != 0, q(5)).to_le_bytes());
            Ok(out)
        }
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
                // Setting one past the word saturates at its edge: what does
                // that, common event 45 of the game this was built for, sets
                // six variables to 999999 as "no cell", and they are only
                // compared for equality against cells, which never reach the
                // ceiling. Adding or subtracting past it still does not
                // compile, because the ROM's sum wraps around. The divergence
                // is the book's `divergences/variables-saturate-at-16-bits.md`.
                if q(3) == VAR_SET {
                    a = a.clamp(-0x8000, 0x7FFF);
                }
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
                // runtime/level.s.
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
                if !matches!(b, CHARACTER_X | CHARACTER_Y | CHARACTER_SCREEN_X | CHARACTER_SCREEN_Y) {
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
                // translate against. See `substitutions.rs` in
                // `wally`, which builds them.
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
            // `ba_enemy_change` in runtime/battle_troop.s.
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
            // runtime/camera.s.
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
            // `flash_tick` in runtime/screen_flash.s.
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
            // The gradient is discarded: the tint is applied at once. The
            // screen being compared is always settled, so the final value is
            // the one that matters; what is lost is the one-second gradient.
            //
            // **The wait is not.** The parameters are (r, g, b, sat, tenths,
            // wait), and with the wait `CommandTintScreen` does
            // `SetupWait(tenths)`, the same wait as the Wait command: so it
            // is an OP_DELAY after it, as with `FlashSprite`. Until
            // 2026-10-05 it went with the gradient, and the page ran on in
            // the same frame. That is time a forced route of the hero walks:
            // Dr. Vago's `[28]` (map 81, event 6) runs during his fade to
            // black, and without it the next route replaced it unread. The
            // hero stayed at speed 3 for the rest of the game, and Dalia's
            // tank (map 66, event 14), whose route at 3 does not finish
            // before the page swaps the party, turned into Dalia on the
            // bridge. Measured in the RPG_RT, 2000 and 2015: at 4 it ends.
            if n < 4 {
                return cannot();
            }
            if p[..4].iter().any(|&v| !(0..=200).contains(&v)) {
                return cannot();
            }
            let mut out = vec![
                OP_TINT, p[0] as u8, p[1] as u8, p[2] as u8, p[3] as u8,
            ];
            if n >= 6 && q(5) != 0 {
                out.push(OP_DELAY);
                out.extend(word(q(4) * FRAMES_PER_TENTH)?);
            }
            Ok(out)
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
            // page from there —see `escape_tail`—, except `\V[n]`, which
            // comes off here.
            let lines = with_variables(&with_names(&lines, ctx.indices), ctx.indices)?;
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
        } else if [ROUTE_TOWARD_HERO, ROUTE_RANDOM, ROUTE_AWAY_HERO].contains(&command) && in_jump {
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
        // `route::known`, and moving toward the hero is in since 2026-09-12 and
        // moving away from him and the random step since 2026-10-06; turning
        // in place and the switches are still out.
        if !route::known(command) {
            return cannot();
        }
        if [ROUTE_FACE_HERO, ROUTE_TOWARD_HERO, ROUTE_RANDOM, ROUTE_AWAY_HERO, ROUTE_FACE_AWAY]
            .contains(&command)
            && target == 0
        {
            // The hero facing or moving toward itself, or at random: the
            // hero's walk is `hero_route.s`, which has none of these.
            return cannot();
        }
        // Locking and unlocking the facing —26 and 27— go to the hero too since
        // 2026-09-30, and stay locked after the route like the speed does:
        // the race car of maps 49 to 54 is the hero with a CharSet whose rows
        // are other cars, locked with a 26 that only map 64 releases. Until
        // then they were dropped on the hero, and each arrow drew another car.
        if route::diagonal(command) && target == 0 {
            // And the hero diagonally: the ROM does not know how to do it and
            // none of the game's 26 routes with diagonals is the hero's.
            // Without this cut the ROM would go left —the mover of
            // `try_toward` falls into `try_left` by elimination—.
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
            // runtime/hero_route.s. They are +29 pages of the game, and
            // among them the three of map 8's `EV0047`, which could not be
            // interacted with.
            let Some(graphics) = ctx.graphics.as_deref_mut() else {
                return cannot();
            };
            if extras.len() < 2 {
                return cannot();
            }
            // One that does not fit in the map's table is ignored: the route
            // goes on with the graphic it had, and the converter warns.
            let Some(chosen) = graphics.index_capped(extras[0].text(), extras[1].int() as i32)
            else {
                continue;
            };
            if target != 0 {
                graphics.on_events.insert((extras[0].text().to_string(), extras[1].int() as i32));
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
/// `battle_anim_tick` in runtime/battle_animation.s.
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
/// The three `Picture` ones are debt only **if the map does not carry the
/// picture**: warning anyway would be the warning nobody reads, which is how
/// a real debt gets lost among the ones that no longer are.
pub fn page_debts(
    game: &Game,
    indices: &Indices,
    commands: &[Command],
    pictures: Option<&Pictures>,
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
            match compile_picture(cmd, pictures, indices) {
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
    use crate::registry::BigPicture;

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
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
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

    #[test]
    fn change_system_graphics_is_accepted_without_emitting() {
        let game = Game::default();
        let out = compile_with(&game, &[cmd(CHANGE_SYSTEM_GRAPHICS, &[], "Blue")]);
        assert!(out.unwrap().is_some(), "the page was left out");
    }

    #[test]
    fn change_face_graphic_is_accepted_without_emitting() {
        let game = Game::default();
        let out = compile_with(&game, &[cmd(CHANGE_FACE_GRAPHIC, &[], "Jack")]);
        assert!(out.unwrap().is_some(), "the page was left out");
    }

    #[test]
    fn change_face_graphic_is_reported_as_debt() {
        let game = Game::default();
        let command = cmd(CHANGE_FACE_GRAPHIC, &[], "Jack");
        assert_eq!(
            page_debts(&game, &Indices::default(), &[command], None).unwrap(),
            [CHANGE_FACE_GRAPHIC]
        );
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
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
        };
        compile_page(&mut ctx, commands, None, 0, 0)
    }

    const TWO_DIGITS: [(i32, i32, i32); 2] = [(2, 55, 30), (3, 70, 30)];

    #[test]
    fn a_declared_counter_is_one_opcode_and_not_its_body() {
        // The middle of the two centers is (62, 30), which on the console is
        // (49, 28): the two glyphs, sixteen by sixteen, start eight to the
        // left and eight up.
        let game = with_counter(true, &TWO_DIGITS);
        let code = compile_with(&game, &[cmd(CALL_EVENT, &[0, 9, 0], "")]);
        assert_eq!(code.unwrap().unwrap(), [OP_COUNTER, 5, 41, 20, OP_DONE]);
    }

    #[test]
    fn a_digit_on_a_counters_picture_shows_the_counter() {
        let game = with_counter(true, &TWO_DIGITS);
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
        for other in [show(2, "Gauge"), show(1, "9")] {
            let code = compile_with(&game, &[other.clone()]);
            assert_eq!(code.unwrap().unwrap(), [OP_DONE]);
            assert_eq!(page_debts(&game, &Indices::default(), &[other], None).unwrap(), [SHOW_PICTURE]);
        }
        assert!(page_debts(&game, &Indices::default(), &[show(3, "4")], None).unwrap().is_empty());
    }

    #[test]
    fn an_undeclared_common_event_is_not_a_counter() {
        // Its body in place, and its pictures are any picture's.
        let game = with_counter(false, &TWO_DIGITS);
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

    /// A page compiled as map 5's, with a window, songs and the map
    /// table answering 1 for any other map.
    fn on_a_map(commands: &[Command]) -> Option<Vec<u8>> {
        on_a_map_with(&Indices::default(), commands)
    }

    /// The same, with these indices.
    fn on_a_map_with(indices: &Indices, commands: &[Command]) -> Option<Vec<u8>> {
        let map = crate::game::Map { id: 5, events: Vec::new() };
        on_this_map(&Game::default(), indices, &map, commands)
    }

    /// The same, on this map of this game.
    fn on_this_map(
        game: &Game,
        indices: &Indices,
        map: &crate::game::Map,
        commands: &[Command],
    ) -> Option<Vec<u8>> {
        use crate::messages::{Messages, Window};
        let sound = SoundSettings::default();
        let mut songs = Songs::default();
        songs.current = Some(Package::Map(0));
        let mut messages = Messages::new(1, Window::columns(39, 4));
        let mut ctx = Ctx {
            game,
            indices,
            sound: &sound,
            map_index: &|_| Some(1),
            messages: Some(&mut messages),
            songs: Some(&mut songs),
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
        };
        let me = MapEvents::new(map, None);
        compile_page(&mut ctx, commands, Some(me), 0, 0).unwrap()
    }

    /// The same page, on a map 5 whose only event is 1, **as that event's**:
    /// "this event" is somebody.
    fn as_the_only_event(commands: &[Command]) -> Option<Vec<u8>> {
        use crate::messages::{Messages, Window};
        let game = Game::default();
        let indices = Indices::default();
        let sound = SoundSettings::default();
        let mut songs = Songs::default();
        songs.current = Some(Package::Map(0));
        let mut messages = Messages::new(1, Window::columns(39, 4));
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| Some(1),
            messages: Some(&mut messages),
            songs: Some(&mut songs),
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
        };
        let map = watching(5, 123);
        let me = MapEvents::new(&map, None).for_event(1);
        compile_page(&mut ctx, commands, Some(me), 0, 0).unwrap()
    }

    #[test]
    fn erasing_the_event_after_a_jump_is_nothing() {
        // After the jump "this event" is 0 —`OnMapChange`— and
        // `CommandEraseEvent` does nothing; before it, it would erase, which
        // the ROM does not do.
        let erase = cmd(ERASE_EVENT, &[], "");
        let jump = cmd(TELEPORT, &[7, 1, 2], "");
        assert_eq!(
            on_a_map(&[jump.clone(), erase.clone()]).unwrap(),
            [OP_TELEPORT, 1, 0, 1, 0, 2, 0, OP_DONE]
        );
        // Before it, and as an event's own, it is no longer nothing: see the
        // next test.
        assert_ne!(as_the_only_event(&[erase, jump]), None);
    }

    #[test]
    fn erasing_and_showing_the_screen_carry_what_the_rom_does() {
        // -1 is the teleport's, resolved by the ROM when it runs; 17 the
        // mosaic; 19 and past it the cut; the rest, the fade. The same
        // table as `ChangeScreenTransitions`.
        for (rm2k, kind) in [(-1, 0xFF), (0, 0), (5, 0), (16, 0), (17, 1), (19, 2), (20, 2)] {
            assert_eq!(
                on_a_map(&[cmd(ERASE_SCREEN, &[rm2k], "")]).unwrap(),
                [OP_ERASE_SCREEN, kind, OP_DONE],
                "EraseScreen {rm2k}"
            );
            assert_eq!(
                on_a_map(&[cmd(SHOW_SCREEN, &[rm2k], "")]).unwrap(),
                [OP_SHOW_SCREEN, kind, OP_DONE],
                "ShowScreen {rm2k}"
            );
        }
        // They are no longer a debt: nothing to warn about.
        assert!(!ACCEPTED_UNDONE.contains(&ERASE_SCREEN));
        assert!(!ACCEPTED_UNDONE.contains(&SHOW_SCREEN));
    }

    #[test]
    fn erasing_the_event_is_erasing_this_events_row() {
        // `CommandEraseEvent` with 0 erases "this event" until the map is
        // loaded again. The target is the index plus one, as in `OP_ROUTE`:
        // event 1 is the first of the map's table.
        let erase = cmd(ERASE_EVENT, &[], "");
        assert_eq!(as_the_only_event(&[erase.clone()]).unwrap(), [OP_ERASE_EVENT, 1, OP_DONE]);
        // A page that is nobody's has no event to erase, and is cut.
        assert_eq!(on_a_map(&[erase]), None);
    }

    #[test]
    fn erasing_the_event_in_a_common_event_is_nothing() {
        // `GetThisEventId` is 0 in a common event and the command returns
        // without erasing anyone: the quarry's timer, which is a common
        // event with the command in it.
        let mut game = Game::default();
        let on = cmd(CONTROL_SWITCHES, &[0, 11, 11, 0], "");
        game.common_events.insert(2, common(5, None, vec![cmd(ERASE_EVENT, &[], ""), on]));
        game.common_events.insert(4, common(3, Some(30), vec![call(2)]));
        let s = shared(&game);
        assert_eq!(s.bodies[0].1, [OP_SWITCH, 11, 0, 1, OP_RETURN]);
    }

    #[test]
    fn the_timer_branch_is_the_golds_question_with_its_own_kind() {
        let code = on_a_map(&[
            cmd(COND_BRANCH, &[2, 30, 1, 0, 0, 0], ""),
            cmd(COND_END, &[], ""),
        ]);
        assert_eq!(code.unwrap(), [OP_IF, COND_TIMER as u8, 30, 0, 1, 7, 0, OP_DONE]);
    }

    #[test]
    fn a_route_walks_at_random_and_away_from_the_hero_on_events_only() {
        // MoveEvent: (target, frequency, repeat, skippable, commands...). The
        // map's only event is 1, and its route target is 1: index plus one.
        let map = watching(5, 1);
        let route = |who: i32, commands: &[i32]| {
            let mut p = vec![who, 8, 0, 1];
            p.extend(commands);
            on_this_map(&Game::default(), &Indices::default(), &map, &[cmd(MOVE_EVENT, &p, "")])
        };
        // 8 walks at random, 10 away from the hero and 22 turns away.
        assert_eq!(
            route(1, &[8, 10, 22]).unwrap(),
            [OP_ROUTE, 1, 8, 3, 8, 10, 22, OP_DONE]
        );
        // The hero has no random walk, and no "away from himself".
        for command in [8, 10, 22] {
            assert_eq!(route(10001, &[command]), None, "{command} on the hero");
        }
        // Inside a jump the commands only add up, and these would have to
        // ask the hero or the dice halfway through the sum.
        for command in [8, 10] {
            assert_eq!(route(1, &[24, command, 25]), None, "{command} in a jump");
        }
    }

    #[test]
    fn hiding_and_showing_the_hero_is_one_opcode() {
        // `PlayerVisibility`: parameter 0 is 0 to hide him —RM2k's
        // "transparent"— and 1 to show him.
        for (parameter, visible) in [(0, 0), (1, 1)] {
            let code = on_a_map(&[cmd(PLAYER_VISIBILITY, &[parameter], "")]);
            assert_eq!(code.unwrap(), [OP_HERO_VISIBLE, visible, OP_DONE]);
        }
    }

    #[test]
    fn the_direction_branch_asks_the_hero_or_an_event() {
        // `ConditionalBranch` case 6: (6, character, direction, ...). The
        // hero is target 0 and an event its index plus one, as in a route.
        let map = watching(5, 1);
        let ask = |who: i32| {
            on_this_map(
                &Game::default(),
                &Indices::default(),
                &map,
                &[cmd(COND_BRANCH, &[6, who, 2, 0, 0, 0], ""), cmd(COND_END, &[], "")],
            )
        };
        assert_eq!(ask(10001).unwrap(), [OP_IF_FACING, 0, 2, 5, 0, OP_DONE]);
        assert_eq!(ask(1).unwrap(), [OP_IF_FACING, 1, 2, 5, 0, OP_DONE]);
        // An event the map does not have does not compile.
        assert_eq!(ask(77), None);
    }

    #[test]
    fn cancelling_past_the_options_runs_none() {
        // Two options and `cancel_type` 4: three entries, the cancel byte
        // says the third is cancel's, and it jumps to the end of the choice.
        let mut choice = vec![cmd(SHOW_CHOICE, &[4], "A/B")];
        for (n, text) in ["A", "B"].iter().enumerate() {
            choice.push(Command::new(SHOW_CHOICE_OPTION, 0, text, vec![n as i32]));
            choice.push(Command::new(END, 1, "", vec![]));
        }
        choice.push(cmd(SHOW_CHOICE_END, &[], ""));
        let code = on_a_map(&choice).unwrap();
        assert_eq!(&code[..3], [OP_CHOICE, 3, 0xFF]);
        assert_eq!(instruction_size(&code, 0), 3 + 4 * 3);
        let entry = |k: usize| u16::from_le_bytes([code[3 + 4 * k + 2], code[3 + 4 * k + 3]]) as usize;
        let end = code.len() - 1;
        assert_eq!(entry(2), end, "cancel lands after the choice");
        assert!(entry(0) < entry(1) && entry(1) <= end);
        // A fifth option, the cancel branch, still does not compile.
        let mut branch = choice.clone();
        branch[0] = cmd(SHOW_CHOICE, &[5], "A/B");
        let at = branch.len() - 1;
        branch.insert(at, Command::new(SHOW_CHOICE_OPTION, 0, "", vec![4]));
        assert_eq!(on_a_map(&branch), None);
    }

    fn label(n: i32, indent: i32) -> Command {
        Command::new(LABEL, indent, "", vec![n])
    }

    fn jump(n: i32, indent: i32) -> Command {
        Command::new(JUMP_TO_LABEL, indent, "", vec![n])
    }

    /// Switch 1 on, at this indentation: two bytes of something that is
    /// not a jump.
    fn switch_on(indent: i32) -> Command {
        Command::new(CONTROL_SWITCHES, indent, "", vec![0, 1, 1, 0])
    }

    fn branch(code: i32, indent: i32) -> Command {
        let parameters = if code == COND_BRANCH {
            vec![0, 1, 0, 0, 0, 0]
        } else {
            vec![]
        };
        Command::new(code, indent, "", parameters)
    }

    /// Where each `OP_GOTO` of the code goes, in order.
    fn gotos(code: &[u8]) -> Vec<usize> {
        let mut out = vec![];
        let mut at = 0;
        while at < code.len() {
            if code[at] == OP_GOTO {
                out.push(u16::from_le_bytes([code[at + 1], code[at + 2]]) as usize);
            }
            at += instruction_size(code, at);
        }
        out
    }

    #[test]
    fn a_jump_forward_lands_on_its_label() {
        let code = on_a_map(&[jump(1, 0), switch_on(0), label(1, 0), switch_on(0)]).unwrap();
        let on = on_a_map(&[switch_on(0)]).unwrap().len() - 1;
        assert_eq!(code[0], OP_GOTO);
        assert_eq!(gotos(&code), [3 + on]);
        assert_eq!(code.len(), 3 + 2 * on + 1);
    }

    #[test]
    fn a_jump_back_lands_on_its_label() {
        let code = on_a_map(&[switch_on(0), label(1, 0), switch_on(0), jump(1, 0)]).unwrap();
        let on = on_a_map(&[switch_on(0)]).unwrap().len() - 1;
        assert_eq!(gotos(&code), [on]);
    }

    #[test]
    fn a_jump_out_of_a_branch_lands_past_its_end() {
        // From inside two branches to after them.
        let code = on_a_map(&[
            branch(COND_BRANCH, 0),
            branch(COND_BRANCH, 1),
            jump(1, 2),
            branch(COND_END, 1),
            branch(COND_END, 0),
            label(1, 0),
            switch_on(0),
        ])
        .unwrap();
        let end = code.len() - 1 - (on_a_map(&[switch_on(0)]).unwrap().len() - 1);
        assert_eq!(gotos(&code), [end]);
    }

    #[test]
    fn the_first_label_with_the_number_wins_wherever_it_is() {
        // Two labels 1, one before the jump and one after it, and one deeper:
        // RM2k searches from the top and looks only at the number.
        let code = on_a_map(&[
            switch_on(0),
            label(1, 0),
            jump(1, 0),
            label(1, 0),
            switch_on(0),
        ])
        .unwrap();
        let on = on_a_map(&[switch_on(0)]).unwrap().len() - 1;
        assert_eq!(gotos(&code), [on]);
    }

    #[test]
    fn a_jump_to_a_label_the_page_does_not_have_does_nothing() {
        let code = on_a_map(&[jump(7, 0), switch_on(0)]).unwrap();
        assert_eq!(code, on_a_map(&[switch_on(0)]).unwrap());
    }

    #[test]
    fn a_jump_into_the_last_body_of_a_block_compiles() {
        // Into the `else`: after the body comes the
        // `EndBranch`, which does nothing in RM2k either.
        let page = [
            jump(1, 0),
            branch(COND_BRANCH, 0),
            switch_on(1),
            branch(COND_ELSE, 0),
            label(1, 1),
            switch_on(1),
            branch(COND_END, 0),
        ];
        let code = on_a_map(&page).unwrap();
        // The jump, the branch, its body and the `else`'s jump: the label
        // is after them.
        let goto = gotos(&code);
        assert_eq!(goto.len(), 2);
        assert_eq!(
            goto[0],
            goto[1] - (on_a_map(&[switch_on(0)]).unwrap().len() - 1)
        );
        // And into a branch without `else`.
        let code = on_a_map(&[
            jump(1, 0),
            branch(COND_BRANCH, 0),
            label(1, 1),
            switch_on(1),
            branch(COND_END, 0),
        ]);
        assert!(code.is_some());
    }

    #[test]
    fn a_jump_into_a_body_that_is_not_the_last_does_not_compile() {
        // Into the true body of a branch with `else`: in RM2k, whether the
        // `else` runs after it depends on what the last branch at that
        // indentation left in the sub-index.
        assert_eq!(
            on_a_map(&[
                jump(1, 0),
                branch(COND_BRANCH, 0),
                label(1, 1),
                switch_on(1),
                branch(COND_ELSE, 0),
                switch_on(1),
                branch(COND_END, 0),
            ]),
            None
        );
        // From the `else` to the true body of the same branch, too.
        assert_eq!(
            on_a_map(&[
                branch(COND_BRANCH, 0),
                label(1, 1),
                switch_on(1),
                branch(COND_ELSE, 0),
                jump(1, 1),
                branch(COND_END, 0),
            ]),
            None
        );
        // And into a choice's first option.
        let mut choice = vec![jump(1, 0), cmd(SHOW_CHOICE, &[0], "A/B")];
        for (n, text) in ["A", "B"].iter().enumerate() {
            choice.push(Command::new(SHOW_CHOICE_OPTION, 0, text, vec![n as i32]));
            if n == 0 {
                choice.push(label(1, 1));
            }
            choice.push(Command::new(END, 1, "", vec![]));
        }
        choice.push(cmd(SHOW_CHOICE_END, &[], ""));
        assert_eq!(on_a_map(&choice), None);
        // Into the last one it does.
        let last = choice.iter().rposition(|c| c.code == SHOW_CHOICE_OPTION).unwrap();
        let first = choice.iter().position(|c| c.code == LABEL).unwrap();
        let moved = choice.remove(first);
        choice.insert(last, moved);
        assert!(on_a_map(&choice).is_some());
    }

    #[test]
    fn a_jump_inside_the_same_body_needs_nothing_else() {
        // Both inside the true body of a branch with `else`: the label is in
        // a body that is not the last, but the jump is in it too.
        let code = on_a_map(&[
            branch(COND_BRANCH, 0),
            label(1, 1),
            switch_on(1),
            jump(1, 1),
            branch(COND_ELSE, 0),
            branch(COND_END, 0),
        ])
        .unwrap();
        assert_eq!(gotos(&code)[0], 7);
    }

    /// Variable 143 in slot 3, as a door that asks for a number needs it.
    fn with_the_password() -> Indices {
        Indices {
            variables: BTreeMap::from([(143, 3)]),
            ..Default::default()
        }
    }

    #[test]
    fn a_number_goes_in_the_window_of_the_message_before_it() {
        // Two lines, and six digits into variable 143.
        let page = [
            cmd(SHOW_MESSAGE, &[], "VOICE"),
            cmd(SHOW_MESSAGE_2, &[], "What is the secret number?"),
            cmd(INPUT_NUMBER, &[6, 143], ""),
        ];
        let code = on_a_map_with(&with_the_password(), &page).unwrap();
        assert_eq!(code, [OP_NUMBER, 3, 6, 0, 0, OP_DONE]);
        assert_eq!(instruction_size(&code, 0), 5);
    }

    #[test]
    fn a_number_the_rom_cannot_show_does_not_compile() {
        let indices = with_the_password();
        let message = |lines: usize| -> Vec<Command> {
            (0..lines)
                .map(|k| cmd(if k == 0 { SHOW_MESSAGE } else { SHOW_MESSAGE_2 }, &[], "line"))
                .collect()
        };
        let input = |digits: i32| cmd(INPUT_NUMBER, &[digits, 143], "");
        // On its own: RM2k opens a window with no text, and the ROM does
        // not.
        assert_eq!(on_a_map_with(&indices, &[input(6)]), None);
        // After four lines it does not fit in the message's window, so it
        // is one on its own too.
        let mut four = message(4);
        four.push(input(4));
        assert_eq!(on_a_map_with(&indices, &four), None);
        let mut three = message(3);
        three.push(input(4));
        assert!(on_a_map_with(&indices, &three).is_some());
        // Seven digits are more than the ROM's line takes.
        let mut seven = message(1);
        seven.push(input(7));
        assert_eq!(on_a_map_with(&indices, &seven), None);
    }

    #[test]
    fn equal_takes_a_constant_as_the_variables_sixteen_bits() {
        let indices = with_the_password();
        let branch = |comparison: i32, value: i32| {
            on_a_map_with(
                &indices,
                &[
                    cmd(COND_BRANCH, &[1, 143, 0, value, comparison, 1], ""),
                    cmd(COND_END, &[], ""),
                ],
            )
        };
        let code = branch(CMP_EQUAL as i32, 35421).unwrap();
        assert_eq!(&code[..6], [OP_IF_VAR, 3, VAR_CONSTANT as u8, 0, 0x5D, 0x8A]);
        assert!(branch(CMP_NOT_EQUAL as i32, 35421).is_some());
        // Ordered, it would be signed; and 65535 is also everything an
        // `InputNumber` saturates to.
        assert_eq!(branch(1, 35421), None);
        assert_eq!(branch(CMP_EQUAL as i32, 65535), None);
        assert_eq!(branch(CMP_EQUAL as i32, 65536), None);
    }

    /// The three destinations of an `OP_BATTLE` at the start of `code`.
    fn battle_destinations(code: &[u8]) -> [usize; 3] {
        assert_eq!(code[0], OP_BATTLE);
        let at = |k: usize| u16::from_le_bytes([code[3 + 2 * k], code[4 + 2 * k]]) as usize;
        [at(0), at(1), at(2)]
    }

    #[test]
    fn escaping_with_escape_mode_1_ends_the_page() {
        // No handlers: escaping goes to the `OP_DONE` right after the
        // opcode, and winning to the command that follows it.
        let switch_on = cmd(CONTROL_SWITCHES, &[0, 7, 7, 0], "");
        let game = Game::default();
        let code = compile_with(&game, &[cmd(ENEMY_ENCOUNTER, &[0, 82, 1, 1, 0, 0], "bg"), switch_on.clone()])
            .unwrap()
            .unwrap();
        assert_eq!(code[9], OP_DONE);
        let [victory, escape, defeat] = battle_destinations(&code);
        assert_eq!((victory, escape, defeat), (10, 9, BATTLE_LOSE));
        // `escape_mode` 0 keeps its shape —nine bytes, and winning goes
        // on— and its escape says it cannot be taken.
        let code = compile_with(&game, &[cmd(ENEMY_ENCOUNTER, &[0, 82, 1, 0, 0, 0], "bg"), switch_on])
            .unwrap()
            .unwrap();
        assert_eq!(battle_destinations(&code), [9, BATTLE_NO_ESCAPE, BATTLE_LOSE]);
    }

    #[test]
    fn escaping_with_escape_mode_1_ends_the_page_also_with_handlers() {
        // `defeat_mode` 1 brings the victory and defeat handlers. The block
        // ends in a jump over an `OP_DONE`, which is where escaping goes;
        // the bodies leave past it.
        let game = Game::default();
        let page = [
            cmd(ENEMY_ENCOUNTER, &[0, 82, 1, 1, 1, 0], "bg"),
            Command::new(VICTORY_HANDLER, 0, "", vec![]),
            Command::new(CONTROL_SWITCHES, 1, "", vec![0, 7, 7, 0]),
            Command::new(END, 1, "", vec![]),
            Command::new(DEFEAT_HANDLER, 0, "", vec![]),
            Command::new(CONTROL_SWITCHES, 1, "", vec![0, 8, 8, 0]),
            Command::new(END, 1, "", vec![]),
            Command::new(END_BATTLE, 0, "", vec![]),
        ];
        let code = compile_with(&game, &page).unwrap().unwrap();
        let [victory, escape, defeat] = battle_destinations(&code);
        assert_eq!(code[escape], OP_DONE);
        assert_eq!(code[escape - 3], OP_GOTO);
        let past = escape + 1;
        assert_eq!(u16::from_le_bytes([code[escape - 2], code[escape - 1]]) as usize, past);
        assert_eq!(code[past], OP_DONE, "the page's own end");
        assert!(victory < defeat && defeat < escape);
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

    /// The volume, the balance and the tempo of a `PlayBGM`, in the units
    /// `OP_BGM` carries: the defaults leave the song as written, a volume of
    /// 50 is a quarter of the amplitude —the stream's CC7 is squared—, and
    /// the tempo is clamped to the editor's 50 to 150.
    #[test]
    fn a_play_bgms_level_in_the_consoles_units() {
        assert_eq!(bgm_level(100, 100, 50), (128, 128, 256));
        assert_eq!(bgm_level(50, 150, 50), (32, 32, 384));
        assert_eq!(bgm_level(40, 80, 50), (20, 20, 205));
        assert_eq!(bgm_level(0, 50, 50), (0, 0, 128));
        assert_eq!(bgm_level(100, 300, 50), (128, 128, 384));
        // the balance: the opposite side drops, 6 dB every 10
        assert_eq!(bgm_level(100, 100, 100), (4, 128, 256));
        assert_eq!(bgm_level(100, 100, 40), (128, 64, 256));
        let page = [cmd(PLAY_BGM, &[0, 50, 150, 50], "K")];
        let mut songs = Songs::default();
        assert_eq!(
            with_songs(&page, &mut songs, &|_| None),
            Some(vec![OP_BGM, 0, 32, 32, 0x80, 1, OP_DONE])
        );
    }

    /// A troop page's `PlayBGM` plays its song, which goes into the battle's
    /// package and also into `troop_songs`, for the plan to put apart; a
    /// map's goes only into its map's package.
    #[test]
    fn a_troop_pages_song_is_played_and_noted_as_a_troop_song() {
        let mut songs = Songs::default();
        let map_page = [cmd(PLAY_BGM, &[0, 100, 100, 50], "map")];
        assert_eq!(with_songs(&map_page, &mut songs, &|_| None), Some(vec![OP_BGM, 0, 128, 128, 0, 1, OP_DONE]));
        let game = Game::default();
        let indices = Indices::default();
        let sound = SoundSettings::default();
        songs.current = Some(Package::Battle);
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: Some(&mut songs),
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
        };
        let troop_page = [cmd(PLAY_BGM, &[0, 100, 100, 50], "radio")];
        let code = compile_page(&mut ctx, &troop_page, None, 0, 0).unwrap();
        assert_eq!(code, Some(vec![OP_BGM, 1, 128, 128, 0, 1, OP_DONE]));
        assert_eq!(songs.troop_songs, [1]);
        assert_eq!(songs.per_package[1].0, Package::Battle);
        assert_eq!(songs.per_package[1].1.songs, [1]);
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
    fn a_page_that_does_not_walk_by_the_declared_sizes_stops_the_conversion() {
        assert!(whole_instructions(&[OP_SWITCH, 1, 0, 1, OP_DONE]).is_ok());
        // A byte short, one too many that is not an opcode, and a choice
        // whose options run past the end.
        assert!(whole_instructions(&[OP_SWITCH, 1, 0]).is_err());
        assert!(whole_instructions(&[OP_DONE, 0xFF]).is_err());
        assert!(whole_instructions(&[OP_CHOICE, 2, 2, 0, 0, 0, 0, OP_DONE]).is_err());
    }

    fn word_at(code: &[u8], at: usize) -> usize {
        u16::from_le_bytes([code[at], code[at + 1]]) as usize
    }

    #[test]
    fn an_inn_with_a_price_is_its_greeting_a_choice_and_a_gold_branch() {
        // The whole block, byte by byte, which is the only thing that says
        // whether the choice's and the branch's destinations land where they
        // should. They are absolute within the page, so the block cannot be
        // read on its own: the message in front shifts it three bytes, and
        // those are the three an implementation that counted from zero would
        // get wrong. It is the shape of the inn that brought `ShowInn`, a
        // message and then the inn at 5.
        let mut game = Game::default();
        game.gold_term = "G".into();
        for terms in game.inn_terms.iter_mut() {
            *terms = ["Stay for".into(), "?".into(), "Rested.".into(), "Yes".into(), "No".into()];
        }
        let map = crate::game::Map { id: 5, events: Vec::new() };
        let code = on_this_map(
            &game,
            &Indices::default(),
            &map,
            &[cmd(SHOW_MESSAGE, &[], "Hi"), cmd(SHOW_INN, &[0, 5, 0], "")],
        )
        .unwrap();
        let (greeting, yes, no) = (word_at(&code, 4), word_at(&code, 9), word_at(&code, 13));
        // The two options are one box: the bar under the highlighted one is
        // the console's, see `choice_boxes`.
        assert!(0 < greeting && greeting < yes && yes == no, "{greeting} {yes} {no}");
        let w = |v: usize| [(v & 0xFF) as u8, (v >> 8) as u8];
        let mut expected = vec![OP_MESSAGE, 0, 0, OP_MESSAGE];
        expected.extend(w(greeting));
        expected.extend([OP_CHOICE, 2, 2]); // cancelling is "No"
        expected.extend(w(yes));
        expected.extend([17, 0]); // "Yes" goes to the branch
        expected.extend(w(no));
        expected.extend([33, 0]); // "No" to the end
        expected.extend([OP_IF, COND_GOLD as u8, 5, 0, 0, 33, 0]);
        expected.extend([OP_GOLD, 1, 5, 0, 0]);
        expected.extend([OP_HEAL, 0, 0, 0, OP_DONE]);
        assert_eq!(code, expected);
    }

    /// A map whose only event has a page that asks for variable `watched`.
    fn watching(id: i32, watched: i32) -> crate::game::Map {
        use crate::game::{Condition, Event, Page};
        let page = Page {
            trigger: 0,
            layer: 1,
            move_type: 0,
            move_frequency: 3,
            move_speed: 3,
            animation_type: 0,
            character_name: String::new(),
            character_index: 0,
            character_pattern: 1,
            commands: Vec::new(),
            route: Vec::new(),
            route_repeat: false,
            route_skippable: false,
            condition: Condition {
                variable: Some((watched, 8)),
                ..Default::default()
            },
        };
        crate::game::Map {
            id,
            events: vec![Event {
                id: 1,
                pages: vec![page],
                starting: None,
            }],
        }
    }

    /// The operation byte of the one `ControlVars` write to variable 123 in
    /// the page, compiled on `map`: the one that carries the refresh bit.
    fn writing_123(map: &crate::game::Map, before: &[Command]) -> i64 {
        let indices = Indices {
            variables: BTreeMap::from([(123, 7)]),
            ..Default::default()
        };
        let mut commands = before.to_vec();
        commands.push(cmd(CONTROL_VARS, &[0, 123, 123, 0, 0, 8, 0], ""));
        let code = on_this_map(&Game::default(), &indices, map, &commands).unwrap();
        let writes: Vec<i64> = instructions(&code)
            .filter(|&at| code[at] == OP_VAR)
            .map(|at| code[at + 2] as i64)
            .collect();
        assert_eq!(writes.len(), 1, "{code:?}");
        writes[0]
    }

    #[test]
    fn a_write_after_jumping_to_another_map_asks_for_the_refresh() {
        // A page that jumps to another map keeps running there, so what it
        // writes afterwards is looked at by the pages **of the destination**:
        // the write has to ask for the refresh, which is what is done when
        // it is not known who looks. It is the chest that did not show up
        // after a `Teleport` although its variable was already 8: the map
        // the page was on did not look at it.
        let quiet = crate::game::Map { id: 5, events: Vec::new() };
        let jump = cmd(TELEPORT, &[7, 4, 7], "");
        assert_ne!(writing_123(&quiet, &[jump]) & VAR_REFRESH, 0);
    }

    #[test]
    fn without_jumping_a_write_asks_for_the_refresh_if_the_map_looks() {
        // The control of the one above: on a map that does not look at 123,
        // writing it asks for nothing; on one that does, it asks. And a
        // jump **to the same** map does not change who looks.
        let quiet = crate::game::Map { id: 5, events: Vec::new() };
        assert_eq!(writing_123(&quiet, &[]) & VAR_REFRESH, 0);
        assert_ne!(writing_123(&watching(5, 123), &[]) & VAR_REFRESH, 0);
        let same = cmd(TELEPORT, &[5, 22, 12], "");
        assert_eq!(writing_123(&quiet, &[same]) & VAR_REFRESH, 0);
    }

    // "Is the hero on the cell of variables 34 and 35?", as RM2k's parallel
    // pages write it: the hero's y and x into 36 and 37, and two nested
    // branches comparing them with 34 and 35. It is the shape of the forty
    // cars of each lap of a race, aiming at the hero.
    fn on_the_cell(body: &[(i32, i32, &[i32])]) -> Vec<Command> {
        let at = |code: i32, indent: i32, p: &[i64]| {
            Command::new(code, indent, "", p.iter().map(|&v| v as i32).collect())
        };
        let mut commands = vec![
            at(CONTROL_VARS, 0, &[0, 36, 36, VAR_SET, VAR_CHARACTER, ROUTE_HERO, CHARACTER_Y]),
            at(CONTROL_VARS, 0, &[0, 37, 37, VAR_SET, VAR_CHARACTER, ROUTE_HERO, CHARACTER_X]),
            at(COND_BRANCH, 0, &[COND_VARIABLE, 36, 1, 34, CMP_EQUAL, 1]),
            at(COND_BRANCH, 1, &[COND_VARIABLE, 37, 1, 35, CMP_EQUAL, 1]),
        ];
        commands.extend(body.iter().map(|&(code, indent, p)| Command::new(code, indent, "", p.to_vec())));
        commands
    }

    const SWITCH_172: (i32, i32, &[i32]) = (CONTROL_SWITCHES, 2, &[0, 172, 172, 0]);

    /// Each variable's slot: (34, 3), (35, 4), (36, 5), (37, 6).
    fn on_the_cell_compiled(commands: &[Command]) -> Vec<u8> {
        let indices = Indices {
            variables: BTreeMap::from([(34, 3), (35, 4), (36, 5), (37, 6)]),
            ..Default::default()
        };
        on_a_map_with(&indices, commands).expect("the page does not compile")
    }

    fn opcodes_of(code: &[u8]) -> Vec<u8> {
        instructions(code).map(|at| code[at]).collect()
    }

    #[test]
    fn the_four_of_the_cell_go_in_one_opcode() {
        // The two writes and the two branches come out as a single
        // `OP_CELL_TEST`, with what they would carry loose: the target, the
        // four variables as offsets —the slot times two—, which coordinate
        // goes to each, and the two destinations, which without an `else`
        // are both the end of their branch.
        let code = on_the_cell_compiled(&on_the_cell(&[SWITCH_172, (COND_END, 1, &[]), (COND_END, 0, &[])]));
        assert_eq!(opcodes_of(&code), [OP_CELL_TEST, OP_SWITCH, OP_DONE]);
        let refresh = CELL_REFRESH as usize;
        assert_eq!(code[1], 0, "the target is the hero");
        assert_eq!(word_at(&code, 2) & !refresh, 5 * 2 | CELL_Y as usize);
        assert_eq!(word_at(&code, 4) & !refresh, 6 * 2);
        assert_eq!((word_at(&code, 6), word_at(&code, 8)), (5 * 2, 3 * 2));
        assert_eq!((word_at(&code, 12), word_at(&code, 14)), (6 * 2, 4 * 2));
        let end = code.len() - 1; // the OP_DONE
        assert_eq!(word_at(&code, CELL_DEST_A), end);
        assert_eq!(word_at(&code, CELL_DEST_B), end);
    }

    #[test]
    fn the_else_of_the_inner_branch_comes_from_its_destination() {
        // With an `else` in the inner branch, its destination is the body of
        // the `else` —after the `OP_GOTO` that takes the outer one out—, and
        // the outer one's is still its end. It is the same patch as a loose
        // branch's, on the opcode's second destination.
        let code = on_the_cell_compiled(&on_the_cell(&[
            SWITCH_172,
            (COND_ELSE, 1, &[]),
            (CONTROL_SWITCHES, 2, &[0, 173, 173, 0]),
            (COND_END, 1, &[]),
            (COND_END, 0, &[]),
        ]));
        let at: Vec<usize> = instructions(&code).collect();
        assert_eq!(opcodes_of(&code), [OP_CELL_TEST, OP_SWITCH, OP_GOTO, OP_SWITCH, OP_DONE]);
        let (goto, otherwise, end) = (at[2], at[3], at[4]);
        assert_eq!(word_at(&code, CELL_DEST_B), otherwise);
        assert_eq!(word_at(&code, goto + 1), end);
        assert_eq!(word_at(&code, CELL_DEST_A), end);
    }

    #[test]
    fn without_the_exact_shape_it_is_not_fused() {
        // A comparison that is not equality, or a branch that is not the
        // first thing inside the other, goes as before: four loose opcodes.
        let body: [(i32, i32, &[i32]); 3] = [SWITCH_172, (COND_END, 1, &[]), (COND_END, 0, &[])];
        let mut other = on_the_cell(&body);
        other[3].parameters[4] = 1; // >=
        let ops = opcodes_of(&on_the_cell_compiled(&other));
        assert_eq!(ops[..4], [OP_VAR, OP_VAR, OP_IF_VAR, OP_IF_VAR]);

        let mut beside = on_the_cell(&body);
        beside[3].indent = 0; // the second one, next to the other
        assert!(!opcodes_of(&on_the_cell_compiled(&beside)).contains(&OP_CELL_TEST));
    }

    #[test]
    fn change_exp_and_change_level_are_op_exp() {
        // See `exp_change` in runtime/level.s for what the ROM does
        // with each bit.
        let mut game = Game::default();
        game.actors.insert(14, vec![]);
        let one = |c: Command| compile_with(&game, &[c]).unwrap().unwrap();
        // 999999 experience to actor 14, in three bytes, without a message.
        assert_eq!(
            one(cmd(CHANGE_EXP, &[1, 14, 0, 0, 999_999, 0], "")),
            [OP_EXP, 14, 0, 0x3F, 0x42, 0x0F, OP_DONE]
        );
        // Two levels off the party, with the message: its pages right after.
        assert_eq!(
            one(cmd(CHANGE_LEVEL, &[0, 0, 1, 0, 2, 1], "")),
            [OP_EXP, 0, EXP_BY_LEVELS | EXP_SUBTRACTS | EXP_WITH_MESSAGE, 2, 0, 0, OP_LEVEL_PAGE, OP_DONE]
        );
        // By a variable: its slot, and 48 is the fifth.
        assert_eq!(
            one(cmd(CHANGE_LEVEL, &[1, 14, 0, 1, 48, 0], "")),
            [OP_EXP, 14, EXP_BY_LEVELS | EXP_BY_VARIABLE, 5, 0, 0, OP_DONE]
        );
        // The actor by a variable, and more than RM2k's cap, do not compile.
        assert_eq!(compile_with(&game, &[cmd(CHANGE_EXP, &[2, 3, 0, 0, 5, 0], "")]).unwrap(), None);
        assert_eq!(compile_with(&game, &[cmd(CHANGE_EXP, &[1, 14, 0, 0, 1_000_000, 0], "")]).unwrap(), None);
    }

    #[test]
    fn what_the_characters_systems_do_to_the_party() {
        // The forms the troop pages use, each as the ROM reads it: see
        // `actor_change`, `actor_stat` and `ba_enemy_change`.
        let mut game = Game::default();
        game.actors.insert(14, vec![]);
        let one = |c: Command| compile_with(&game, &[c]).unwrap().unwrap();
        // 999 off actor 14, lethal.
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
        // Actor 14's HP into variable 48, asking for the refresh: without a map
        // there is no knowing that no page looks at it.
        assert_eq!(
            one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 5, 14, 2], "")),
            [OP_VAR, 5, 0x80, 5, 14, 0, 2, 0, OP_DONE]
        );
        // Equipping an accessory: its slot, 4, on top of its number.
        let mut game = game.clone();
        let mut users = vec![false; 25];
        users[13] = true;
        game.items.insert(386, (5, users));
        game.items.insert(200, (1, vec![true; 25]));
        let equip = |game: &Game, item: i32| {
            compile_with(game, &[cmd(CHANGE_EQUIPMENT, &[1, 14, 0, 0, item], "")]).unwrap()
        };
        assert_eq!(
            equip(&game, 386).unwrap(),
            [OP_ACTOR, 14, ACT_EQUIP, 0x82, 0x81, OP_DONE]
        );
        // A weapon does not compile; one the actor cannot use does nothing.
        assert!(equip(&game, 200).is_none());
        game.items.insert(386, (5, vec![false; 25]));
        assert_eq!(equip(&game, 386).unwrap(), [OP_DONE]);
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

    /// A `ShowPicture` of `name` on `number`: centred at (cx, cy), with
    /// `mode` —RM2k's p[1], 1 by variables—, with the map if `map`, at
    /// `zoom`, transparency `trans`.
    fn picture(number: i32, name: &str, mode: i32, at: (i32, i32), map: bool, zoom: i32, trans: i32) -> Command {
        cmd(
            SHOW_PICTURE,
            &[number, mode, at.0, at.1, i32::from(map), zoom, trans, 1, 100, 90, 80, 100, 0, 0],
            name,
        )
    }

    fn moving(number: i32, at: (i32, i32), zoom: i32, trans: i32, tenths: i32, wait: bool) -> Command {
        cmd(
            MOVE_PICTURE,
            &[number, 0, at.0, at.1, 0, zoom, trans, 0, 0, 0, 0, 100, 0, 0, tenths, i32::from(wait)],
            "",
        )
    }

    /// `commands` compiled for a map that carries `table`.
    fn with_pictures(table: &[(PictureKey, u8)], indices: &Indices, commands: &[Command]) -> Vec<u8> {
        let game = Game::default();
        let sound = SoundSettings::default();
        let mut pictures = Pictures {
            table: table.to_vec(),
            big: Vec::new(),
            gathering: false,
            zooms: Vec::new(),
        };
        let mut ctx = Ctx {
            game: &game,
            indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            pictures: Some(&mut pictures),
            troops: None,
            commons: None,
            shared: None,
        };
        compile_page(&mut ctx, commands, None, 0, 0).unwrap().unwrap()
    }

    /// Where `judged_page` says a page stopped, compiled with nothing.
    fn stopped_at(commands: &[Command]) -> Option<Culprit> {
        let game = Game::default();
        let sound = SoundSettings::default();
        let indices = Indices::default();
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
        };
        match judged_page(&mut ctx, commands, None, 0, 0) {
            Ok(_) => None,
            Err((Stop::Cannot, at)) => Some(at),
            Err((Stop::Fatal(bad), _)) => panic!("{bad}"),
        }
    }

    #[test]
    fn a_page_that_does_not_compile_names_the_command_it_stopped_at() {
        let wait = cmd(WAIT, &[1], "");
        // `Loop` does not compile, two commands in.
        assert_eq!(stopped_at(&[wait.clone(), wait.clone(), cmd(LOOP, &[], ""), wait.clone()]), Some(Some(2)));
        // Inside a branch, it is the command and not the branch.
        let branch = Command::new(COND_BRANCH, 0, "", vec![0, 1, 0, 0, 0, 0]);
        let inside = Command::new(LOOP, 1, "", vec![]);
        let end = Command::new(COND_END, 0, "", vec![]);
        assert_eq!(stopped_at(&[branch.clone(), inside, end]), Some(Some(1)));
        // A branch left open stops at the page as a whole.
        assert_eq!(stopped_at(&[branch, wait.clone()]), Some(None));
        assert_eq!(stopped_at(&[wait]), None);
    }

    /// `commands` compiled for a map that carries `big` as a background
    /// layer, and nothing in its sprites.
    fn with_big(big: &[BigPicture], commands: &[Command]) -> Vec<u8> {
        let game = Game::default();
        let sound = SoundSettings::default();
        let indices = Indices::default();
        let mut pictures = Pictures {
            table: Vec::new(),
            big: big.to_vec(),
            gathering: false,
            zooms: Vec::new(),
        };
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            pictures: Some(&mut pictures),
            troops: None,
            commons: None,
            shared: None,
        };
        compile_page(&mut ctx, commands, None, 0, 0).unwrap().unwrap()
    }

    #[test]
    fn a_big_picture_goes_up_scrolls_fades_and_comes_down() {
        // A sheet of instructions: 300x299 centred at (160, 150), that
        // go up to 50 in four seconds; the console computes the corner.
        let show = cmd(
            SHOW_PICTURE,
            &[6, 0, 160, 150, 0, 100, 0, 0, 100, 100, 100, 100, 0, 0],
            "Billboard",
        );
        let big = BigPicture {
            key: picture_key(&show).unwrap(),
            image: 2,
            center: (160, 150),
            texture: false,
        };
        let up = cmd(
            MOVE_PICTURE,
            &[6, 0, 160, 50, 0, 100, 0, 0, 100, 100, 100, 100, 0, 0, 40, 1],
            "",
        );
        assert_eq!(
            with_big(std::slice::from_ref(&big), &[show, up, cmd(ERASE_PICTURE, &[6], "")]),
            [
                OP_BIG_SHOW, 2, 100, 100, 100, 0, 100, 0,
                OP_BIG_MOVE, 100, 100, 100, 0, 240, 50, 0, 0, 100,
                OP_DELAY, 240, 0,
                OP_PICTURE_ERASE, PICTURE_BIG,
                OP_DONE
            ]
        );
        // A photo: with the map, shrinking to nothing in two seconds, which
        // is fading to black; and a wave and a saturation.
        let photo = cmd(
            SHOW_PICTURE,
            &[20, 0, 160, 120, 1, 100, 0, 1, 100, 100, 100, 200, 2, 8],
            "Photo",
        );
        let big = BigPicture {
            key: picture_key(&photo).unwrap(),
            image: 0,
            center: (160, 120),
            texture: false,
        };
        let shrink = cmd(
            MOVE_PICTURE,
            &[20, 0, 160, 120, 0, 0, 0, 0, 100, 100, 100, 100, 2, 4, 20, 0],
            "",
        );
        assert_eq!(
            with_big(&[big], &[photo, shrink]),
            [
                OP_BIG_SHOW, 0, 100, 100, 100, 0, 200, 8,
                OP_BIG_MOVE, 100, 100, 100, 100, 120, 120, 0, 4, 100,
                OP_DONE
            ]
        );
    }

    #[test]
    fn a_big_picture_with_a_texture_zooms_instead_of_fading() {
        // The photo of map 212: shown at 100, shrinking to nothing in two
        // seconds with the page waiting; then back to half, and past the
        // size it was shown at, which only the texture can do.
        let photo = cmd(
            SHOW_PICTURE,
            &[20, 0, 160, 120, 1, 100, 0, 1, 100, 100, 100, 100, 0, 60],
            "Photo",
        );
        let big = BigPicture {
            key: picture_key(&photo).unwrap(),
            image: 3,
            center: (160, 120),
            texture: true,
        };
        let shrink = cmd(
            MOVE_PICTURE,
            &[20, 0, 160, 120, 0, 0, 0, 0, 100, 100, 100, 100, 0, 5497976, 20, 1],
            "",
        );
        let half = moving(20, (160, 120), 50, 0, 0, false);
        assert_eq!(
            with_big(std::slice::from_ref(&big), &[photo.clone(), shrink.clone(), half]),
            [
                OP_BIG_SHOW, 3, 100, 100, 100, 0, 100, 0,
                OP_BIG_ZOOM, 100, 100, 100, 0, 120, 120, 0, 0, 100, 0,
                OP_DELAY, 120, 0,
                OP_BIG_ZOOM, 0, 0, 0, 0, 0, 120, 0, 0, 100, 50,
                OP_DONE
            ]
        );
        // Shown at half, a move to 100 is twice its size; without a
        // texture it is not done.
        let small = cmd(
            SHOW_PICTURE,
            &[20, 0, 160, 120, 1, 50, 0, 1, 100, 100, 100, 100, 0, 0],
            "Photo",
        );
        let grown = moving(20, (160, 120), 100, 0, 10, false);
        let mut big = BigPicture { key: picture_key(&small).unwrap(), ..big };
        assert_eq!(
            with_big(std::slice::from_ref(&big), &[grown.clone()]),
            [OP_BIG_ZOOM, 0, 0, 0, 0, 60, 120, 0, 0, 100, 200, OP_DONE]
        );
        big.texture = false;
        assert_eq!(with_big(&[big], &[grown]), [OP_DONE]);
    }

    #[test]
    fn the_scan_writes_down_what_each_move_zooms_to() {
        let game = Game::default();
        let sound = SoundSettings::default();
        let indices = Indices::default();
        let mut pictures = Pictures::gathering();
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            pictures: Some(&mut pictures),
            troops: None,
            commons: None,
            shared: None,
        };
        let commands = [
            moving(20, (160, 120), 0, 0, 20, true),
            moving(20, (160, 120), 0, 50, 20, true),
            moving(3, (10, 10), 100, 0, 5, false),
        ];
        compile_page(&mut ctx, &commands, None, 0, 0).unwrap();
        assert_eq!(pictures.zooms, [(20, 0), (3, 100)]);
    }

    #[test]
    fn two_pictures_take_their_slots() {
        let a = picture(3, "Sign", 0, (100, 175), false, 100, 0);
        let b = picture(1, "Rec", 0, (250, 200), false, 50, 0);
        let table = [(picture_key(&a).unwrap(), 0), (picture_key(&b).unwrap(), 1)];
        let code = with_pictures(&table, &Indices::default(), &[a, b, cmd(ERASE_PICTURE, &[3], "")]);
        assert_eq!(
            code,
            [
                OP_PICTURE, 0, 0, 0, 100, 0, 175, 0, 100, 90, 80, 0,
                OP_PICTURE, 1, 1, 0, 250, 0, 200, 0, 100, 90, 80, 0,
                OP_PICTURE_ERASE, 0,
                OP_DONE
            ]
        );
    }

    #[test]
    fn a_picture_the_map_does_not_carry_is_accepted_undone() {
        let a = picture(3, "Sign", 0, (100, 175), false, 100, 0);
        let elsewhere = picture(3, "Sign", 0, (101, 175), false, 100, 0);
        let table = [(picture_key(&a).unwrap(), 0)];
        // The same file somewhere else is another picture: its pixels round
        // differently.
        let code = with_pictures(&table, &Indices::default(), &[elsewhere, cmd(ERASE_PICTURE, &[4], "")]);
        assert_eq!(code, [OP_DONE]);
    }

    #[test]
    fn by_variables_and_with_the_map() {
        let smoke = picture(8, "Smoke", 1, (153, 154), true, 35, 40);
        let key = picture_key(&smoke).unwrap();
        assert!(key.by_variable && key.map_fixed && key.at.is_none());
        let mut indices = Indices::default();
        indices.variables.insert(153, 7);
        indices.variables.insert(154, 9);
        let code = with_pictures(&[(key, 1)], &indices, &[smoke.clone()]);
        let mode = PICTURE_BY_VARIABLE | PICTURE_MAP_FIXED;
        assert_eq!(code, [OP_PICTURE, 1, 0, mode, 7, 0, 9, 0, 100, 90, 80, 40, OP_DONE]);
        // Without a slot for its variables it cannot be placed.
        let code = with_pictures(&[(picture_key(&smoke).unwrap(), 1)], &Indices::default(), &[smoke]);
        assert_eq!(code, [OP_DONE]);
    }

    #[test]
    fn a_move_changes_tone_and_transparency_and_waits() {
        let sign = picture(3, "Sign", 0, (100, 175), false, 100, 0);
        let table = [(picture_key(&sign).unwrap(), 0)];
        let code = with_pictures(&table, &Indices::default(), &[moving(3, (100, 175), 100, 50, 35, true)]);
        assert_eq!(code, [OP_PICTURE_MOVE, 0, 0, 0, 0, 50, 210, OP_DELAY, 210, 0, OP_DONE]);
        // Somewhere else, or at another zoom, it does not: the console does
        // not move pictures.
        for elsewhere in [moving(3, (120, 175), 100, 0, 10, false), moving(3, (100, 175), 50, 0, 10, false)] {
            assert_eq!(with_pictures(&table, &Indices::default(), &[elsewhere]), [OP_DONE]);
        }
        // Two pictures under one number: one of them staying is enough.
        let other = picture(3, "Other", 0, (10, 10), false, 100, 0);
        let both = [table[0].clone(), (picture_key(&other).unwrap(), 0)];
        let code = with_pictures(&both, &Indices::default(), &[moving(3, (10, 10), 100, 0, 1, false)]);
        assert_eq!(code, [OP_PICTURE_MOVE, 0, 0, 0, 0, 0, 6, OP_DONE]);
        // With the map, RM2k 2000 does not move it either, so the place does
        // not matter.
        let shadow = picture(17, "shadow", 0, (100, 115), true, 55, 100);
        let table = [(picture_key(&shadow).unwrap(), 1)];
        let code = with_pictures(&table, &Indices::default(), &[moving(17, (0, 0), 55, 50, 10, true)]);
        assert_eq!(code, [OP_PICTURE_MOVE, 1, 0, 0, 0, 50, 60, OP_DELAY, 60, 0, OP_DONE]);
    }

    #[test]
    fn rotating_or_enlarging_is_not_a_picture() {
        let mut spin = picture(1, "x", 0, (0, 0), false, 100, 0);
        spin.parameters[12] = 1;
        let mut big = picture(1, "x", 0, (0, 0), false, 150, 0);
        big.parameters[12] = 0;
        assert!(picture_key(&spin).is_none());
        assert!(picture_key(&big).is_none());
    }

    #[test]
    fn change_gold_by_a_variable_is_its_slot() {
        // Sern's forge and the bets: the amount is in a variable, and 48 is
        // the fifth slot. The same five bytes as a constant.
        let game = Game::default();
        let one = |c: Command| compile_with(&game, &[c]).unwrap();
        assert_eq!(
            one(cmd(CHANGE_GOLD, &[0, 1, 48], "")),
            Some(vec![OP_GOLD, GOLD_BY_VARIABLE, 5, 0, 0, OP_DONE])
        );
        assert_eq!(
            one(cmd(CHANGE_GOLD, &[1, 1, 48], "")),
            Some(vec![OP_GOLD, GOLD_SUBTRACTS | GOLD_BY_VARIABLE, 5, 0, 0, OP_DONE])
        );
    }

    #[test]
    fn a_characters_screen_position_is_class_six() {
        // Map 207's smoke: the screen x and y, 4 and 5, of RM2k's screen.
        // The ROM works them out: see `character_screen`.
        let game = Game::default();
        let one = |c: Command| compile_with(&game, &[c]).unwrap();
        assert_eq!(
            one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 6, 10001, 4], "")),
            Some(vec![OP_VAR, 5, 0x80, 6, 0, 0, 4, 0, OP_DONE])
        );
        assert_eq!(
            one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 6, 10001, 5], "")),
            Some(vec![OP_VAR, 5, 0x80, 6, 0, 0, 5, 0, OP_DONE])
        );
        // The facing and the map id still do not compile.
        assert_eq!(one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 6, 10001, 3], "")), None);
        assert_eq!(one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 6, 10001, 0], "")), None);
    }

    #[test]
    fn setting_a_variable_past_the_word_saturates() {
        // Common event 45 of the game this was built for sets six variables
        // to 999999 as "no cell": they land at the word's ceiling, and the
        // floor's mirror image too. Adding past the word still does not
        // compile: the ROM's sum wraps around.
        let game = Game::default();
        let one = |c: Command| compile_with(&game, &[c]).unwrap();
        assert_eq!(
            one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 0, 999_999, 0], "")),
            Some(vec![OP_VAR, 5, 0x80, 0, 0xFF, 0x7F, 0, 0, OP_DONE])
        );
        assert_eq!(
            one(cmd(CONTROL_VARS, &[0, 48, 48, 0, 0, -999_999, 0], "")),
            Some(vec![OP_VAR, 5, 0x80, 0, 0x00, 0x80, 0, 0, OP_DONE])
        );
        assert_eq!(one(cmd(CONTROL_VARS, &[0, 48, 48, 1, 0, 999_999, 0], "")), None);
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

    // --- `\V[n]` ---------------------------------------------------------------

    #[test]
    fn a_variables_value_goes_in_the_text_as_its_slot() {
        // A line like "The hero has \V[0173] coins to spend".
        // The value counts as one letter of the line, and its slot follows
        // the escape byte.
        let indices = Indices {
            variables: BTreeMap::from([(173, 7)]),
            ..Default::default()
        };
        let code = on_a_map_with(&indices, &[cmd(SHOW_MESSAGE, &[], "has \\V[0173] souls")]).unwrap();
        assert_eq!(code, [OP_MESSAGE, 0, 0, OP_DONE]);
        let mut messages = crate::messages::Messages::new(1, crate::messages::Window::columns(39, 4));
        let lines = with_variables(&["a\\v[173]b".to_string()], &indices).unwrap();
        let at = messages.add(&lines).ok().unwrap();
        // One line of three units: a, the value, b.
        assert_eq!(messages.data[at..], [1, 3, 65, crate::messages::VARIABLE, 7, 66]);
    }

    #[test]
    fn an_actors_name_is_baked_into_the_text_unless_it_can_change() {
        let indices = Indices {
            hero_names: BTreeMap::from([(2, "Kai".to_string())]),
            ..Default::default()
        };
        let out = with_names(&["Hi \\N[2]! \\n[2] \\N[0] \\N[3]".to_string()], &indices);
        assert_eq!(out, ["Hi Kai! Kai \\N[0] \\N[3]"]);
        // The page compiles with it, and not without.
        let mut messages = crate::messages::Messages::new(1, crate::messages::Window::columns(39, 4));
        assert!(messages.add(&with_names(&["\\N[2]".to_string()], &indices)).is_ok());
        assert!(messages.add(&["\\N[2]".to_string()]).is_err());
    }

    #[test]
    fn a_variable_the_rom_cannot_show_does_not_compile() {
        let indices = Indices {
            variables: BTreeMap::from([(173, 7)]),
            ..Default::default()
        };
        let fails = |text: &str| on_a_map_with(&indices, &[cmd(SHOW_MESSAGE, &[], text)]).is_none();
        // One without a slot, the nested one and one without brackets.
        assert!(fails("\\V[0174]"));
        assert!(fails("\\V[\\V[0173]]"));
        assert!(fails("\\V173"));
        assert!(!fails("\\V[173]"));
    }

    // --- the shared common event bodies -----------------------------------------

    fn common(trigger: i32, switch: Option<i32>, commands: Vec<Command>) -> CommonEvent {
        CommonEvent {
            trigger,
            switch_flag: switch.is_some(),
            switch_id: switch.unwrap_or(1),
            commands,
        }
    }

    fn call(number: i32) -> Command {
        cmd(CALL_EVENT, &[0, number, 0], "")
    }

    fn shared(game: &Game) -> crate::commons::Shared {
        use crate::messages::{Messages, Window};
        let indices = Indices::default();
        let sound = SoundSettings::default();
        let mut messages = Messages::new(1, Window::columns(39, 4));
        let mut songs = Songs::default();
        let mut troops = Troops::default();
        let setting = crate::commons::Setting {
            game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
        };
        let plan = crate::commons::plan(&setting, BTreeSet::new(), &messages, &songs).unwrap();
        crate::commons::compile(&setting, &plan, &mut messages, &mut songs, &mut troops).unwrap()
    }

    #[test]
    fn an_automatic_common_event_calls_the_others_by_index() {
        // 4 is automatic on switch 30 and calls 2 twice and 3, which does not
        // compile: 2 is compiled once, and the call to 3 is skipped, as a
        // pasted call whose body does not compile is. 5 is automatic without
        // a switch, which is not taken; 6 is called by nobody.
        let mut game = Game::default();
        let on = |s: i32| cmd(CONTROL_SWITCHES, &[0, s, s, 0], "");
        game.common_events.insert(2, common(5, None, vec![on(11)]));
        game.common_events.insert(3, common(5, None, vec![cmd(LOOP, &[], "")]));
        game.common_events.insert(4, common(3, Some(30), vec![call(2), call(3), call(2)]));
        game.common_events.insert(5, common(3, None, vec![on(12)]));
        game.common_events.insert(6, common(5, None, vec![on(13)]));
        let s = shared(&game);
        let numbers: Vec<i32> = s.bodies.iter().map(|(n, _)| *n).collect();
        assert_eq!(numbers, [2, 4]);
        assert_eq!(s.bodies[0].1, [OP_SWITCH, 11, 0, 1, OP_RETURN]);
        assert_eq!(s.bodies[1].1, [OP_CALL, 0, OP_CALL, 0, OP_RETURN]);
        assert_eq!(s.autostart, [(30, 1)]);
        assert_eq!(s.depth, Some(2));
    }

    #[test]
    fn a_common_event_a_custom_menu_replaces_opens_it_and_turns_off() {
        // 4, automatic on switch 30, is replaced by menu 1: its body is the
        // menu and its switch off, and 2, which it called, is not reached.
        // 6 runs before a page: its message goes, its variable stays, after
        // the other bodies.
        let mut game = Game::default();
        let on = |s: i32| cmd(CONTROL_SWITCHES, &[0, s, s, 0], "");
        game.common_events.insert(2, common(5, None, vec![on(11)]));
        game.common_events.insert(4, common(3, Some(30), vec![call(2)]));
        game.common_events.insert(
            6,
            common(5, None, vec![on(12), cmd(SHOW_MESSAGE, &[], "Counted.")]),
        );
        game.patches.menus.replaced.insert(4, 1);
        game.patches.menus.before.insert(6);
        let s = shared(&game);
        let numbers: Vec<i32> = s.bodies.iter().map(|(n, _)| *n).collect();
        assert_eq!(numbers, [4, 6]);
        assert_eq!(s.bodies[0].1, [OP_MENU_OPEN, 1, OP_SWITCH, 30, 0, 0, OP_RETURN]);
        assert_eq!(s.bodies[1].1, [OP_SWITCH, 12, 0, 1, OP_RETURN]);
        assert_eq!(s.menu_before, [(6, 1)]);
        assert_eq!(s.autostart, [(30, 0)]);
    }

    #[test]
    fn a_body_a_menu_runs_before_a_page_cannot_wait() {
        let mut game = Game::default();
        game.common_events.insert(6, common(5, None, vec![cmd(WAIT, &[10], "")]));
        game.patches.menus.before.insert(6);
        assert!(crate::commons::before_commands(&game, 6).is_err());
    }

    #[test]
    fn an_automatic_common_event_that_does_not_compile_has_no_body() {
        let mut game = Game::default();
        game.common_events.insert(2, common(5, None, vec![]));
        game.common_events.insert(4, common(3, Some(30), vec![call(2), cmd(LOOP, &[], "")]));
        let s = shared(&game);
        assert!(s.bodies.is_empty());
        assert!(s.autostart.is_empty());
    }

    #[test]
    fn escaping_a_battle_in_a_shared_body_ends_only_its_frame() {
        // `EndEventProcessing` ends the frame it runs in, not the caller's:
        // in a shared body the escape goes to an `OP_RETURN`.
        let mut game = Game::default();
        for name in BATTLE_AUDIO_SE {
            game.system_se.insert(name, ("(OFF)".to_string(), 100, 100, 50));
        }
        game.common_events.insert(
            4,
            common(3, Some(30), vec![cmd(ENEMY_ENCOUNTER, &[0, 7, 0, 1, 1, 0, 0], "")]),
        );
        let s = shared(&game);
        let body = &s.bodies[0].1;
        assert_eq!(body[0], OP_BATTLE);
        assert_eq!(body[9], OP_RETURN);
        assert_eq!(*body.last().unwrap(), OP_RETURN);
    }

    /// A page of map 5 that calls common events 2 and 3, compiled the way
    /// the cartridge's are: it may call the shared bodies of `shared`.
    fn calling(game: &Game, sound: &SoundSettings, shared: &BTreeMap<i32, u8>) -> Vec<u8> {
        use crate::game::Map;
        use crate::messages::{Messages, Window};
        let indices = Indices {
            variables: BTreeMap::from([(40, 0)]),
            ..Default::default()
        };
        let mut songs = Songs::default();
        songs.current = Some(Package::Map(0));
        let mut messages = Messages::new(1, Window::columns(39, 4));
        let mut ctx = Ctx {
            game,
            indices: &indices,
            sound,
            map_index: &|m| (m == 5).then_some(0),
            messages: Some(&mut messages),
            songs: Some(&mut songs),
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: Some(shared),
        };
        let map = Map { id: 5, events: Vec::new() };
        let me = MapEvents::new(&map, None);
        compile_page(&mut ctx, &[call(2), call(3)], Some(me), 0, 0).unwrap().unwrap()
    }

    #[test]
    fn a_page_calls_a_body_only_if_the_map_changes_nothing_in_it() {
        // 2 is the same with and without the map: it is called. 3 plays
        // an effect that on map 5 sounds with another sample, so compiled
        // with the map it is not the cartridge's body: it is pasted, with
        // the map's sample. A variable's refresh does not count: see `shares`.
        let mut game = Game::default();
        game.common_events.insert(
            2,
            common(5, None, vec![cmd(CONTROL_VARS, &[0, 40, 40, 0, 0, 1, 0], "")]),
        );
        game.common_events.insert(3, common(5, None, vec![cmd(PLAY_SOUND, &[100, 100, 50], "Thunder")]));
        let sound = SoundSettings {
            per_map: vec![("Thunder".into(), 5, "Thunder-5".into())],
            ..Default::default()
        };
        let shared = BTreeMap::from([(2, 0), (3, 1)]);
        let code = calling(&game, &sound, &shared);
        assert_eq!(&code[..2], [OP_CALL, 0]);
        assert_eq!(code[2], OP_SOUND);
        assert_eq!(*code.last().unwrap(), OP_DONE);
        // Without the per-map sample, 3 is the same everywhere too.
        let code = calling(&game, &SoundSettings::default(), &shared);
        assert_eq!(code, [OP_CALL, 0, OP_CALL, 1, OP_DONE]);
    }

    #[test]
    fn calls_that_loop_have_no_depth() {
        let mut game = Game::default();
        game.common_events.insert(2, common(5, None, vec![call(4)]));
        game.common_events.insert(4, common(3, Some(30), vec![call(2)]));
        let s = shared(&game);
        assert_eq!(s.bodies.len(), 2);
        assert_eq!(s.depth, None);
    }
}
