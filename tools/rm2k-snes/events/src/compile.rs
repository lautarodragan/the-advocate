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
/// `Game_Party::SetTimer` stores `seconds * 60 + 59`: the 59 are what makes
/// the first second show whole.
const TIMER_EXTRA_FRAMES: i64 = 59;
/// An absurd range of switches is not unrolled.
const MAX_RANGE: i64 = 64;
/// How many switches the ROM's bitmap holds: `SWITCH_BYTES` is 128.
/// Measured against the game this was built with: an assumption of the
/// engine, not a fact of the format.
const SWITCH_MAX: i64 = 1024;
/// RM2k's gold cap does not travel: the ROM clamps. The operand is 24 bits.
/// The inventory: one byte per item of the database in far RAM, `FAR_ITEMS`,
/// indexed by the RM2k number. It was measured against the game this was
/// built with —its 450 items plus 0—: an assumption of the engine.
pub const ITEMS_N: i64 = 451;
/// The equipment slots of an actor: weapon, shield, armor, helmet and
/// accessory.
const EQUIPMENT_SLOTS: i64 = 5;
/// How many graphics fit in a map's table: the operand is a byte.
const GRAPHICS_MAX: usize = 0xFF;
/// The variable slot is a byte, and far RAM has room for 256.
pub const VAR_SLOT_MAX: usize = 0xFF;
/// A picture's `MovePicture` has to fit in `OP_PICTURE_MOVE`'s byte.
const PICTURE_FRAMES_MAX: i64 = 255;
/// How deep a `CallEvent` nests: a common event can call itself.
const CALL_MAX: usize = 4;

// ControlSwitches.
const SWITCH_SINGLE: i64 = 0;
const SWITCH_RANGE: i64 = 1;
const SWITCH_ON: i64 = 0;
const SWITCH_TOGGLE: i64 = 2;
// ControlVars: the operations, where the operand comes from, and the "other"
// ones and a character's coordinates.
const VAR_SET: i64 = 0;
const VAR_ADD: i64 = 1;
const VAR_SUBTRACT: i64 = 2;
pub const VAR_CONSTANT: i64 = 0;
pub const VAR_VARIABLE: i64 = 1;
const VAR_RANDOM: i64 = 3;
pub const VAR_CHARACTER: i64 = 6;
const VAR_OTHER: i64 = 7;
const OTHER_GOLD: i64 = 0;
const OTHER_TIMER: i64 = 1;
const CHARACTER_X: i64 = 1;
const CHARACTER_Y: i64 = 2;
const CMP_EQUAL: i64 = 0;
const CMP_NOT_EQUAL: i64 = 5;
/// The top bit of the flags byte of every opcode that writes a variable:
/// whether the write asks for the page refresh.
pub const VAR_REFRESH: i64 = 0x80;
// TimerOperation.
const TIMER_SET: i64 = 0;
const TIMER_START: i64 = 1;
const TIMER_STOP: i64 = 2;
const TIMER_FIXED_SECONDS: i64 = 0;
/// The timer's fourth operation: the seconds from a variable.
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
// The route targets.
pub const ROUTE_HERO: i64 = 10001;
pub const ROUTE_THIS_EVENT: i64 = 10005;
// ChangePartyMembers.
const PARTY_ADD: i64 = 0;
const PARTY_REMOVE: i64 = 1;
pub const PARTY_FIXED_ID: i64 = 0;
// ChangeEventLocation.
const PLACE_CONSTANT: i64 = 0;
const PLACE_BY_VARIABLE: i64 = 1;
// OP_LOCATION: recalling, and the refresh bits of the three writes.
const PLACE_JUMP: u8 = 0x01;
const PLACE_REFRESHES: [u8; 3] = [0x80, 0x40, 0x20];
// PanScreen.
const PAN_SHIFT: i64 = 2;
const PAN_RETURN: i64 = 3;
/// The camera's unit inside RM2k: a 16-pixel cell is worth 256.
const PAN_UNIT: i64 = 256;
// KeyInputProc's flags.
const KEY_WAIT: i64 = 0x01;
const KEY_DIRS: i64 = 0x02;
const KEY_DECISION: i64 = 0x04;
const KEY_CANCEL: i64 = 0x08;
const KEY_START: i64 = 0x10;
// The three permissions, and their bit in `FAR_ACCESS`.
const ACCESS_BIT: [u8; 3] = [0x01, 0x02, 0x04];
// ChangeScreenTransitions.
const TRANSITION_ERASE: i64 = 0;
const TRANSITION_SHOW: i64 = 1;
const RM2K_TRANSITION_MOSAIC: i64 = 17;
/// The cut and "none", which erasing compiles to the cut.
const RM2K_CUT_TRANSITIONS: [i64; 2] = [19, 20];
const TRANSITION_FADE: u8 = 0;
const TRANSITION_MOSAIC: u8 = 1;
const TRANSITION_CUT: u8 = 2;
// ShowBattleAnimation.
const ANIM_SOUND: u8 = 0;
const ANIM_SCREEN_FLASH: u8 = 1;
const ANIM_FLASH: u8 = 2;
/// Ten, which is how long RM2k's lasts, and even: the screen flash works
/// in two phases by the parity of what it has left.
const ANIM_FLASH_FRAMES: u8 = 10;
const ANIM_NO_DRAWING: u8 = 0xFF;
const ANIM_TARGET_SCREEN: u8 = 0xFF;
// EnemyEncounter.
const BATTLE_BACKDROP_OF_PLACE: i64 = 0;
const BATTLE_BACKDROP_OF_COMMAND: i64 = 1;
const BATTLE_ESCAPE_CUTS: i64 = 1;
const BATTLE_DEFEAT_GAME_OVER: i64 = 0;
/// The destination that means "this is a Game Over": no page reaches 64 KB.
const BATTLE_LOSE: usize = 0xFFFF;
const BATTLE_HANDLERS: [i32; 3] = [VICTORY_HANDLER, ESCAPE_HANDLER, DEFEAT_HANDLER];
// ShowChoice.
const CHOICE_MAX: i64 = 4;
const CHOICE_CURSOR: &str = ">";
const CHOICE_INDENT: &str = " ";
// Where the two destinations go inside `OP_CELL_TEST`, and the top two bits
// of each write: y instead of x, and the refresh.
const CELL_DEST_A: usize = 10;
const CELL_DEST_B: usize = 16;
const CELL_Y: i64 = 0x4000;
const CELL_REFRESH: i64 = 0x8000;
// Encounters: RM2k's table as (minimum ratio, pmod exponent), and the rate
// every step adds —the terrain's, 100 in the game this was measured on—.
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
const ENC_RATE: i64 = 100;
/// The battle's audio: the order is the ROM's.
pub const BATTLE_AUDIO_SE: [&str; 7] = [
    "dodge_se",
    "enemy_attack_se",
    "enemy_damaged_se",
    "actor_damaged_se",
    "enemy_death_se",
    "escape_se",
    "item_se",
];
/// A name RM2k uses to say "nothing".
const AUDIO_OFF: [&str; 2] = ["", "(OFF)"];

/// The commands that are accepted doing nothing because there is nothing
/// to do: the message window's position, without a window to put.
const IGNORABLE: [i32; 1] = [MESSAGE_OPTIONS];
/// The ones accepted without being done, with the debt declared: what they
/// leave undone does not show on the screen being compared.
pub const ACCEPTED_UNDONE: [i32; 5] = [
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
    CHANGE_SYSTEM_BGM,
    CHANGE_HERO_TITLE,
];

/// What cuts an exit `PlayBGM` before the jump: branches, choices, battles,
/// calls, loops, and the jumps whose destination is not always known.
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

/// The decisions of the game's project file about its sound effects.
#[derive(Debug, Clone, Default)]
pub struct SoundSettings {
    /// (name in RM2k, map id) and the sample that plays there instead.
    pub per_map: Vec<(String, i64, String)>,
    /// Per map, the route effects that do not go into its package: None is
    /// all of them.
    pub route_left_out: Vec<(i64, Option<BTreeSet<String>>)>,
    /// The troop pages' effects that do go into the battle's package.
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
    /// in.
    pub map_index: &'a dyn Fn(i64) -> Option<usize>,
    pub messages: Option<&'a mut Messages>,
    pub songs: Option<&'a mut Songs>,
    pub graphics: Option<&'a mut Graphics>,
    pub picture: Option<&'a Picture>,
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
/// `base` and `depth` are for what is compiled in place —a `CallEvent`, an
/// equipment common event—: `base` is where this piece starts in the outer
/// page, because the branches' destinations are absolute; `depth` is the
/// nesting. A piece in place carries no `OP_DONE`: in RM2k the called one's
/// end returns to the caller.
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
    let mut pieces: Vec<Vec<u8>> = Vec::new();
    let mut length = base;
    let mut stack: Vec<Open> = Vec::new();
    // A `ShowChoice`'s options and whether an `EnemyEncounter` has its
    // handlers are looked ahead, which is what RM2k does: in the loop the
    // commands come one at a time.
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
    // The four of "is it on the cell?", which go in a single opcode: each
    // command's role —0 and 1 the writes, 2 and 3 the branches— and the
    // pattern's first command.
    let mut cell_role: HashMap<usize, (usize, usize)> = HashMap::new();
    for i in fadable_cells(commands) {
        for n in 0..4 {
            cell_role.insert(i + n, (n, i));
        }
    }
    let mut cell_piece: HashMap<usize, usize> = HashMap::new();
    let mut choices: Vec<Choice> = Vec::new();
    let mut battles: Vec<Battle> = Vec::new();
    let mut exit = Exit::default();
    // The last thing the page put in each variable, if it was a constant.
    let mut constants: HashMap<i64, i64> = HashMap::new();
    let mut faded: Vec<u8> = Vec::new();

    for (i, extra) in group_boxes(commands) {
        let cmd = &commands[i];
        let requested = ctx.songs.as_ref().map_or(0, |s| s.requested);
        let mut role = cell_role.get(&i).copied();
        if let Some((0, _)) = role {
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
            let troop = encounter_troop(cmd)?;
            if let Some(troops) = ctx.troops.as_deref_mut() {
                troops.request(troop as i32, encounter_backdrop(cmd));
            }
            battle_audio(ctx);
            let losing_is_game_over = cmd.p(4) == Some(BATTLE_DEFEAT_GAME_OVER);
            if no_block.contains(&i) {
                // No handlers: winning and escaping go on with the command
                // below, and losing goes to the Game Over.
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
                piece = vec![0; 9];
            }
        } else if BATTLE_HANDLERS.contains(&cmd.code) {
            let Some(current) = battles.last_mut() else {
                return cannot();
            };
            let n = BATTLE_HANDLERS.iter().position(|&h| h == cmd.code).unwrap();
            // The previous handler's body ends here, with a jump to the end.
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
                // block, except a defeat that is a Game Over.
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
                // The "cancel branch", a fifth one: nobody uses it.
                return cannot();
            }
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
            piece = vec![0; 3 + 4 * options.len()];
        } else if cmd.code == SHOW_CHOICE_OPTION {
            let Some(current) = choices.last_mut() else {
                return cannot();
            };
            let n = cmd.p(0).unwrap_or(0);
            if !(0 <= n && n < current.n as i64) {
                return cannot();
            }
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
            stack.push(Open::End(pieces.len()));
            piece = branch_bytes(ctx, cmd)?;
        } else if cmd.code == COND_ELSE {
            let Some(open) = stack.pop() else {
                return cannot();
            };
            piece = vec![OP_GOTO, 0, 0];
            // The `if`'s destination is after this jump.
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
            // None of the game's inns uses its branches.
            return cannot();
        } else if cmd.code == CALL_EVENT {
            piece = compile_call(ctx, cmd, length, depth, map_events.as_ref())?;
        } else {
            let mut p = compile_command(ctx, cmd, &extra, map_events.as_ref())?;
            // A jump to another map: the page keeps running there.
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
            // goes right here.
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
    // What was noted from the `PlayBGM`s counts only if the page compiles.
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
    if depth == 0 {
        code.push(OP_DONE);
    }
    Ok(code)
}

// --- following an exit song ------------------------------------------------------

/// Follows whether the page's last `PlayBGM` is an exit one: it is if what
/// comes up to a `Teleport` to another map plays no effect, turns on no
/// other song and does not branch. And notes each jump to another map with
/// the song it carries, or None.
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
/// with a constant before —the breaking floors load it and jump right
/// away—, or None. What is known is noted as a destination, like a
/// `Teleport`'s.
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
/// variable if it wrote it some other way.
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

/// The equipment common events whose switch this command turns on.
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

/// `CallEvent`, compiled in place: the called one's body goes where the call
/// is. If the called one does not compile, the call is skipped.
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
    let (body, context) = if p[0] == 0 {
        // A common event, by number.
        (
            ctx.game
                .common_events
                .get(&p[1])
                .map(|c| c.commands.clone()),
            map_events.cloned(),
        )
    } else if p[0] == 1 && p.len() >= 3 && map_events.is_some() {
        // A map event, by id and page number, which starts at one. "This
        // event" inside it is the called one.
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
        // By variable: the number comes from the save.
        return Ok(vec![]);
    };
    let Some(body) = body else { return Ok(vec![]) };
    if body.is_empty() {
        return Ok(vec![]);
    }
    Ok(compile_page(ctx, &body, context, length, depth + 1)?.unwrap_or_default())
}

/// `ControlSwitches` that toggles: one branch per switch, with what the
/// interpreter already does.
///
/// ```text
///  0  OP_IF       on, and if not, to 14
///  7  OP_SWITCH   turn it off
/// 11  OP_GOTO     to 18
/// 14  OP_SWITCH   turn it on
/// 18  the next one
/// ```
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

/// `ShowInn`, expanded into commands the ROM already knows: the greeting,
/// a choice, a branch on gold, the charge and the heal.
///
/// ```text
///  0  OP_MESSAGE  the greeting, two lines
///  3  OP_CHOICE   "Yes" and "No"; cancel is "No"
/// 14  OP_IF       gold >= price, and if not, to the end
/// 21  OP_GOLD     it is charged
/// 26  OP_HEAL     the whole party to the maximum
/// 30  the end
/// ```
///
/// A free inn is just the heal, which is what RM2k does with the price at
/// zero.
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
        return cannot();
    }
    let t = &ctx.game.inn_terms[kind as usize];
    let greeting = format!("{} {}{} {}", t[0], price, ctx.game.gold_term, t[1]);
    let at = messages.add(&[greeting, t[2].clone()])?;
    let frames = choice_boxes(&[(0, t[3].clone()), (1, t[4].clone())], messages)?;
    let end = length + 30;
    let mut out = vec![OP_MESSAGE];
    out.extend(usize_word(at)?);
    // Cancel is the second option: cancelling is not staying.
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

/// The options of the `ShowChoice` at `commands[i]`: `GetChoices`, which
/// gathers the options on the next command's indent up to the end.
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
/// nested `ConditionalBranch`es that compare one variable with another for
/// equality. `OP_CELL_TEST` does the four in one turn of the interpreter.
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

/// The troop of an `EnemyEncounter`: by constant, and without cutting the
/// page on escape. `[0]` is whether the troop comes from a variable, `[1]`
/// the troop, `[2]` the backdrop, `[3]` escape, `[4]` defeat.
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

/// The actor operand of `OP_HEAL` and `OP_EQUIPMENT`: 0 is the party, and a
/// fixed actor its number. By variable does not compile.
fn target_actor(p: &[i32]) -> Step<u8> {
    if p[0] == 0 {
        return Ok(0);
    }
    if p[0] == 1 && 0 < p[1] && p[1] <= 0xFF {
        return Ok(p[1] as u8);
    }
    cannot()
}

/// A step's chance of an encounter, `1 / steps` in 1/65536; zero is off.
pub fn enc_base(steps: i64) -> i64 {
    if steps <= 0 {
        0
    } else {
        0x10000 / steps
    }
}

/// At which step each row of RM2k's table is crossed: `ratio >= row` with
/// `ratio = 100 * n / steps` is `n >= ceil(row * steps / 100)`.
pub fn enc_step_thresholds(steps: i64) -> Vec<i64> {
    ENC_TABLE[1..]
        .iter()
        .map(|&(row, _)| -((-row * steps).div_euclid(ENC_RATE)))
        .collect()
}

// --- sound ---------------------------------------------------------------------------

/// The index of an effect asked for on the map being compiled —a
/// `PlaySound`'s or, with `from_route`, a route's— with the project's
/// decisions applied: another sample on some map, left out of a map's
/// package, or in the battle's.
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
        in_package = ctx.sound.troop_in_package.contains(&name);
    }
    songs.sound((name, volume, tempo, balance), in_package)
}

// --- pictures --------------------------------------------------------------------------

/// Whether the parameters of a `ShowPicture` or a `MovePicture` fall within
/// what the console's picture does. The indices are easyrpg's: the color
/// and the saturation go in 8..11 and the effect in 12.
fn picture_fits(p: &[i32]) -> bool {
    p.len() >= 14
        && p[1] == 0
        && p[4] == 0
        && p[5] == 100
        && p[6] == 0
        && p[11] == 100
        && p[12] == 0
        && p[8..12].iter().all(|&v| (0..=200).contains(&v))
}

/// The three `Picture` commands, or None if this picture does not fit.
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
        // The PNG's transparent color would need one color less.
        if p[7] != 0 || !picture.shows(p[0], &cmd.string, p[2], p[3]) {
            return Ok(None);
        }
        let mut out = vec![OP_PICTURE];
        out.extend(tone);
        return Ok(Some(out));
    }
    // MovePicture: the same picture, in the same place, with another tone,
    // over so many tenths.
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
    if p.len() > 15 && p[15] != 0 && frames != 0 {
        out.push(OP_DELAY);
        out.extend(word(frames)?);
    }
    Ok(Some(out))
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

/// Whether a write to variable `number` asks for the page refresh: only if
/// some page condition of the map looks at it. Without the map, or after
/// leaving it, always.
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
/// event its index plus one.
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
            // Without a song registry it is accepted and not done. An empty
            // name is "(OFF)".
            if ctx.songs.is_none() || cmd.string.is_empty() || n < 3 {
                return Ok(vec![]);
            }
            let k = sound_index(ctx, (cmd.string.clone(), p[0], p[1], p[2]), false);
            let mut out = vec![OP_SOUND];
            out.extend(usize_word(k)?);
            Ok(out)
        }
        WEATHER_EFFECTS => {
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
            if n < 2 {
                return cannot();
            }
            Ok(vec![OP_HEAL, target_actor(p)?, 0, 0])
        }
        CHANGE_HP => {
            // Only the one that adds, by constant; zero does nothing, and in
            // OP_HEAL zero means `FullHeal`.
            if n < 5 || q(2) != 0 {
                return cannot();
            }
            if q(3) != 0 {
                return cannot();
            }
            if !(0..=0xFFFF).contains(&q(4)) {
                return cannot();
            }
            if q(4) == 0 {
                return Ok(vec![]);
            }
            let mut out = vec![OP_HEAL, target_actor(p)?];
            out.extend(word(q(4))?);
            Ok(out)
        }
        CHANGE_SKILLS => {
            // Fixed actor and constant skill, which is every one in the game:
            // the operand is the pair's bit.
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
            // Unequipping one slot, which is what the game does outside
            // battle.
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
        GAME_OVER => Ok(vec![OP_GAME_OVER]),
        RETURN_TO_TITLE => Ok(vec![OP_RETURN_TO_TITLE]),
        CHANGE_CONDITION => {
            // Removing a state: outside battle there are none.
            if n < 3 || q(2) != 1 {
                return cannot();
            }
            Ok(vec![])
        }
        KEY_INPUT_PROC => {
            // [variable, wait, directions, action, cancel], exactly five.
            if n != 5 {
                return cannot();
            }
            let flags = (if q(1) != 0 { KEY_WAIT } else { 0 })
                | (if q(2) != 0 { KEY_DIRS } else { 0 })
                | (if q(3) != 0 { KEY_DECISION } else { 0 })
                | (if q(4) != 0 { KEY_CANCEL } else { 0 });
            if flags & (KEY_DIRS | KEY_DECISION | KEY_CANCEL) == 0 {
                return cannot();
            }
            if q(1) == 0 {
                // It reads what is held, and the page goes on.
                let slot = ctx.indices.variable_slot(q(0))?;
                return Ok(vec![
                    OP_KEY,
                    slot,
                    (flags | refresh(q(0), map_events)) as u8,
                ]);
            }
            // The one that waits goes twice: the first eats the edge that
            // closed the message before it.
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
            // [actor, CharSet index, transparent].
            if n != 3 {
                return cannot();
            }
            if q(2) != 0 {
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
            if n < 2 {
                return cannot();
            }
            let (which, rm2k) = (q(0), q(1));
            if which != TRANSITION_ERASE && which != TRANSITION_SHOW {
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
            // [add or remove, item by constant, item, amount by constant,
            // amount].
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
            // Without a song registry it is accepted and not done.
            let Some(songs) = ctx.songs.as_deref_mut() else {
                return Ok(vec![]);
            };
            if cmd.string.is_empty() {
                return Ok(vec![]);
            }
            Ok(vec![OP_BGM, (songs.index(&cmd.string) & 0xFF) as u8])
        }
        PAN_SCREEN => {
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
                [(0, -1), (1, 0), (0, 1), (-1, 0)][q(1) as usize]
            };
            dx *= q(2) * PAN_UNIT;
            dy *= q(2) * PAN_UNIT;
            if !((-0x8000..0x8000).contains(&dx) && (-0x8000..0x8000).contains(&dy)) {
                return cannot();
            }
            // `2 << speed`, the speed clamped between 1 and 6.
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
            if n == 0 || q(0) < 0 {
                return cannot();
            }
            // The volume goes down by `ceil(65536 / frames)` each frame.
            let frames = (q(0) * FRAMES_PER_SECOND / 1000).max(1);
            let step = (-((-0x10000i64).div_euclid(frames))).min(0xFFFF);
            let mut out = vec![OP_FADE_BGM];
            out.extend(word(step)?);
            Ok(out)
        }
        OPEN_SAVE_MENU => Ok(vec![OP_SAVE]),
        SHOW_PICTURE | MOVE_PICTURE | ERASE_PICTURE => {
            // One that does not fit is accepted without being done.
            Ok(compile_picture(cmd, ctx.picture)?.unwrap_or_default())
        }
        CHANGE_SYSTEM_BGM | CHANGE_HERO_TITLE => Ok(vec![]),
        CHANGE_ENCOUNTER_STEPS => {
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
        COMMENT | COMMENT_2 => Ok(vec![]),
        CONTROL_SWITCHES => {
            if n < 4 || !(q(0) == SWITCH_SINGLE || q(0) == SWITCH_RANGE) {
                return cannot();
            }
            if q(3) == SWITCH_TOGGLE {
                // The page's loop builds it; here it would only arrive fused.
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
            if n < 3 {
                return cannot();
            }
            let Some(dest) = (ctx.map_index)(q(0)) else {
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
            if ctx.songs.is_none() {
                return Ok(vec![]);
            }
            Ok(vec![
                OP_MEMORIZED_BGM,
                (cmd.code == PLAY_MEMORIZED_BGM) as u8,
            ])
        }
        CHANGE_PARTY_MEMBERS => {
            if n < 3 || q(1) != PARTY_FIXED_ID {
                return cannot();
            }
            if !(q(0) == PARTY_ADD || q(0) == PARTY_REMOVE) || !(0..=255).contains(&q(2)) {
                return cannot();
            }
            Ok(vec![OP_PARTY, q(0) as u8, q(2) as u8])
        }
        PROCEED_WITH_MOVEMENT => Ok(vec![OP_WAIT_ROUTES]),
        HALT_ALL_MOVEMENT => Ok(vec![OP_STOP_ROUTES]),
        CHANGE_PBG => Ok(vec![]),
        FLASH_SPRITE => {
            if n < 7 {
                return cannot();
            }
            // A flash on an event that shares a palette is emitted anyway:
            // the two flash together, a declared divergence.
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
                out.push(OP_DELAY);
                out.extend(word(frames)?);
            }
            Ok(out)
        }
        CONTROL_VARS => {
            // [how it is chosen, from, to, operation, operand kind, a, b]:
            // one variable at a time.
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
            } else if operand_kind == VAR_CHARACTER {
                // A character's cell: `a` becomes the target byte.
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
            if n < 5 {
                return cannot();
            }
            if q(0) == TIMER_SET {
                if q(1) != TIMER_FIXED_SECONDS {
                    let slot = ctx.indices.variable_slot(q(2))?;
                    return Ok(vec![OP_TIMER, TIMER_SET_VAR as u8, slot, 0, 0]);
                }
                // The ROM counts the frames in sixteen bits.
                if !(0..=0xFFFF).contains(&(q(2) * FRAMES_PER_SECOND + TIMER_EXTRA_FRAMES)) {
                    return cannot();
                }
                let mut out = vec![OP_TIMER, TIMER_SET as u8];
                out.extend(word(q(2))?);
                out.push(0);
                return Ok(out);
            }
            if q(0) == TIMER_START || q(0) == TIMER_STOP {
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
            if n < 4 || !(q(1) == PLACE_CONSTANT || q(1) == PLACE_BY_VARIABLE) {
                return cannot();
            }
            // Nobody moves the hero this way: that is what Teleport is for.
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
                // The cell is read when it runs, from two variables.
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
            // [upper layer?, old tile, new tile], translated to the ROM's
            // blocks by the caller, who built them.
            if n < 3 {
                return cannot();
            }
            let Some(subs) = map_events.and_then(|m| m.substitutions.as_ref()) else {
                return cannot();
            };
            let Some(pairs) = subs.pairs(q(0) != 0, q(1), q(2))? else {
                return cannot();
            };
            if pairs.is_empty() {
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
            // [mode, x, y, variable]: in mode 1 the cell is two variables,
            // read when it runs.
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
            // Only from a troop page.
            if n < 1 || !(0..256).contains(&q(0)) {
                return cannot();
            }
            Ok(vec![OP_SHOW_ENEMY, q(0) as u8])
        }
        SHAKE_SCREEN => {
            // Power, speed, tenths and whether it waits; zero tenths is the
            // end of a shake, and never waits.
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
            // Color, power, tenths and whether it waits.
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
                return cannot();
            }
            let mut out = vec![OP_SWAP];
            for t in targets {
                out.push(byte(t.unwrap() as i64)?);
            }
            Ok(out)
        }
        WAIT => {
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
            // The duration goes: the tint is applied at once.
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
            let Some(messages) = ctx.messages.as_deref_mut() else {
                return cannot();
            };
            let mut lines = vec![cmd.string.clone()];
            lines.extend_from_slice(extra);
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
fn compile_route(ctx: &mut Ctx, cmd: &Command, map_events: Option<&MapEvents>) -> Step<Vec<u8>> {
    let p = &cmd.parameters;
    if p.len() < 4 {
        return cannot();
    }
    let target = target_of(p[0] as i64, map_events)?;
    if !(route::FREQUENCY_MIN..=route::FREQUENCY).contains(&p[1]) {
        return cannot();
    }
    let commands = route::decode(&p[4..])?;
    let codes: Vec<i32> = commands.iter().map(|(c, _)| *c).collect();
    if route::min_frequency(p[1], &codes, p[2] != 0) < route::FREQUENCY_MIN {
        return cannot();
    }
    let mut path: Vec<i64> = Vec::new();
    // Inside a jump the commands are only added up, so 9 there would have
    // to ask about the hero in the middle of the math: nothing does it.
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
            // Dropped inside a jump, without a registry, or "(OFF)".
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
            continue;
        }
        if !route::known(command) {
            return cannot();
        }
        if (command == ROUTE_FACE_HERO || command == ROUTE_TOWARD_HERO) && target == 0 {
            return cannot();
        }
        if (command == ROUTE_LOCK_DIR || command == ROUTE_UNLOCK_DIR) && target == 0 {
            // Dropped on the hero.
            continue;
        }
        if route::diagonal(command) && target == 0 {
            return cannot();
        }
        if command == ROUTE_CHANGE_GRAPHIC {
            // The only command with an operand: the graphic's index in the
            // map's table.
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
        // Only sound or transparency: RM2k consumes it on the same frame.
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
        return Ok(vec![]);
    };
    // The hero is never flashed, and an event that shares its palette
    // neither.
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
    entries.sort_by_key(|e| e[0]);
    if entries.len() > 255 {
        return cannot();
    }
    // A `global` one is not drawn.
    let number = if p[0] <= 255 && !(p.len() > 3 && p[3] != 0) {
        p[0] as i64
    } else {
        ANIM_NO_DRAWING as i64
    };
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

/// Which commands of this page are accepted without being done: the
/// converter warns about them. A `Picture` one is not a debt if it is the
/// picture the ROM draws.
pub fn page_debts(commands: &[Command], picture: Option<&Picture>) -> Result<Vec<i32>> {
    let mut out = BTreeSet::new();
    for cmd in commands {
        if !ACCEPTED_UNDONE.contains(&cmd.code) {
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
}
