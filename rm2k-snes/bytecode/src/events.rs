//! The event bytecode: one entry per opcode, its number and its layout.
//!
//! This file is the source of truth for both ends of the contract —the
//! compiler that emits the bytes, `rm2k-snes-events`, and the interpreter
//! that reads them, the runtime's `run_code`— and it is owned by neither.
//! The grammar is `bytecode!`'s, in `lib.rs`.
//!
//! The runtime also gets the dispatch table from here, so the numbers run
//! from 0 with no gaps, and this does not compile otherwise: a new opcode is
//! its entry here and its `.proc op_x` in the runtime, and the dispatch is
//! not touched. If one is taken out, the gap is closed —renumbering, or
//! giving its number to the next one added—.
//!
//! Adding a feature RM2k does not have is adding opcodes here, not declaring
//! another bytecode: this is the runtime's format, not RM2k's.

bytecode! {
    "event";
    OP_DONE = 0x00 ();

    OP_SWITCH = 0x01 (id: word, value: byte);

    OP_TELEPORT = 0x02 (map: word, x: word, y: word);

    OP_DELAY = 0x03 (frames: word);

    OP_TINT = 0x04 (red: byte, green: byte, blue: byte, saturation: byte);

    OP_PARTY = 0x05 (operation: byte, actor: byte);

    OP_ROUTE = 0x06 (target: byte, frequency: byte, length: count byte)
        repeated commands (order: byte);

    OP_MESSAGE = 0x07 (offset: word);

    OP_WAIT_ROUTES = 0x08 ();

    OP_FLASH = 0x09 (
        target: byte, red: byte, green: byte, blue: byte, power: byte,
        frames: byte,
    );

    OP_TIMER = 0x0A (operation: byte, seconds: word, visible: byte);

    /// `PlayBGM`: the song, and how loud and how fast, already in the console's
    /// units. `left` and `right` are the gain of each side in 128ths —128 is the
    /// song as written—, which is RM2k's volume and balance together; `step` is
    /// how much of a music frame each video frame advances, in 256ths —256 is
    /// RM2k's tempo 100—.
    OP_BGM = 0x0B (track: byte, left: byte, right: byte, step: word);

    OP_PLACE = 0x0C (target: byte, x: word, y: word);

    OP_SWAP = 0x0D (first: byte, second: byte);

    OP_SHAKE = 0x0E (power: byte, speed: byte, frames: word);

    OP_FLASH_SCREEN = 0x0F (
        red: byte, green: byte, blue: byte, power: byte, frames: byte,
    );

    OP_FADE_BGM = 0x10 (step: word);

    OP_PAN = 0x11 (
        operation: byte, dx: signed word, dy: signed word, step: byte,
        wait: byte,
    );

    OP_IF = 0x12 (kind: byte, operand: word, polarity: byte, destination: word);

    OP_GOTO = 0x13 (destination: word);

    OP_CHOICE = 0x14 (length: count byte, on_cancel: byte)
        repeated options (window: word, destination: word);

    OP_GOLD = 0x15 (sign: byte, amount: long);

    OP_SAVE = 0x16 ();

    OP_VAR = 0x17 (slot: byte, operation: byte, kind: byte, a: word, b: word);

    OP_IF_VAR = 0x18 (
        slot: byte, kind: byte, comparison: byte, value: word,
        destination: word,
    );

    OP_ITEM = 0x19 (item: word, delta: signed byte);

    OP_ACCESS = 0x1A (bit: byte, allowed: byte);

    OP_SHOP = 0x1B (kind: byte, layout: byte, length: count byte)
        repeated goods (item: word);

    OP_WEATHER = 0x1C (kind: byte, power: byte);

    OP_SOUND = 0x1D (index: word);

    OP_ANIMATION = 0x1E (animation: byte, target: byte, length: count byte)
        repeated frames (
            cell: byte, x: byte, y: byte, palette: byte, tiles: byte, flip: byte,
            sound: byte, spare: byte,
        );

    /// The three picture ones act on a `slot` the interpreter keeps a picture in.
    /// `OP_PICTURE` puts up `image` —an entry of the loaded map's picture table—
    /// centred at (`x`, `y`): RM2k's screen pixels, or, with bit 0 of `mode`,
    /// two variable slots in the low bytes. Bit 1 of `mode` is "it goes with the
    /// map". The tone is RM2k's, 100 neutral, and `transparency` its percentage.
    OP_PICTURE = 0x1F (
        slot: byte, image: byte, mode: byte, x: signed word, y: signed word,
        red: byte, green: byte, blue: byte, transparency: byte,
    );

    OP_PICTURE_MOVE = 0x20 (
        slot: byte, red: byte, green: byte, blue: byte, transparency: byte,
        frames: byte,
    );

    OP_PICTURE_ERASE = 0x21 (slot: byte);

    /// `on_abort` is where a battle a troop page ended with `TerminateBattle`
    /// goes on: past the handlers, as EasyRPG's `BattleResult::Abort`. The
    /// four go in the order of `BA_RESULT`'s values, which index them.
    OP_BATTLE = 0x22 (
        troop: word, on_win: word, on_escape: word, on_lose: word,
        on_abort: word,
    );

    OP_STOP_ROUTES = 0x23 ();

    /// `ConditionalBranch` on an actor with two operands: `subkind` is
    /// RM2k's —3 the HP, 4 a skill, 5 an equipped item—, and `data` the HP,
    /// the skill's slot or the item.
    OP_IF_ACTOR = 0x24 (
        subkind: byte, actor: byte, data: word, destination: word,
    );

    OP_ACTOR_SPRITE = 0x25 (actor: byte, graphic: byte);

    OP_KEY = 0x26 (slot: byte, flags: byte);

    OP_PLACE_VAR = 0x27 (target: byte, x_slot: byte, y_slot: byte);

    OP_HEAL = 0x28 (actor: byte, amount: word);

    OP_TILE_SUB = 0x29 (pairs: count byte)
        repeated substitutions (old_cell: word, new_cell: word);

    OP_TERRAIN = 0x2A (mode: byte, x: word, y: word, slot: byte);

    OP_EQUIPMENT = 0x2B (actor: byte, slot: byte);

    OP_SKILL = 0x2C (pair: word, learn: byte);

    OP_GAME_OVER = 0x2D ();

    OP_TRANSITION = 0x2E (which: byte, kind: byte);

    OP_LOCATION = 0x2F (mode: byte, map_slot: byte, x_slot: byte, y_slot: byte);

    OP_MEMORIZED_BGM = 0x30 (play: byte);

    /// Two `OP_VAR` that copy a character's cell into two variables, followed by
    /// two nested `OP_IF_VAR` that compare two variables for equality: the same
    /// four instructions, in one. Variables go as their byte offset (slot times
    /// two), so the interpreter indexes with them as they come; the two writes
    /// also carry which coordinate and the refresh bit in their top bits.
    /// `else_a` and `else_b` are where each condition goes when it fails.
    OP_CELL_TEST = 0x31 (
        target: byte, first: word, second: word, left_a: word, right_a: word,
        else_a: word, left_b: word, right_b: word, else_b: word,
    );

    /// `ChangeEncounterSteps`: the new `1 / steps` in 1/65536 (0 turns random
    /// encounters off) and the step at which each row of the encounter table is
    /// crossed, rows 1 to 7, computed from the same steps. `pad` fills the eight
    /// bytes of a threshold record, so the interpreter copies it in four words.
    OP_ENCOUNTER_STEPS = 0x32 (
        base: word, row_1: byte, row_2: byte, row_3: byte, row_4: byte,
        row_5: byte, row_6: byte, row_7: byte, pad: byte,
    );

    /// `ShowHiddenMonster`, the battle-only command: the troop member at that
    /// index (0-based, in the order of the troop) stops being hidden. It only runs
    /// in a troop page, inside a battle.
    OP_SHOW_ENEMY = 0x33 (member: byte);

    /// `ReturntoTitleScreen`: back to the title, with no Game Over screen. Like
    /// `OP_GAME_OVER`, it waits while a message is open.
    OP_RETURN_TO_TITLE = 0x34 ();

    /// A counter: a common event the project declares as the display of a
    /// variable, in two digit pictures, called with `CallEvent`. Instead of its
    /// body, this: show the variable's value **now**, clamped to 0..99 and with no
    /// leading zero, in the timer's glyphs, with the tens' top-left corner at
    /// (`x`, `y`) of the console's screen and the ones eight pixels to its right.
    /// It stays until the map changes. `slot` is the variable's.
    OP_COUNTER = 0x35 (slot: byte, x: byte, y: byte);

    /// What `OP_HEAL` does not do to an actor —0 the whole party—: the `ChangeHP`
    /// that subtracts or reads a variable, `ChangeSP`, and the `ChangeCondition`
    /// that removes the death state. `what` carries bits: the SP and not the HP
    /// ($01), getting a fallen one up with 1 HP and nothing else ($02), `amount`
    /// as a variable's slot ($20), a loss of HP that can kill ($40), and
    /// subtracting ($80).
    OP_ACTOR = 0x36 (actor: byte, what: byte, amount: word);

    /// `ChangeMonsterHP` and `ChangeMonsterMP`: the enemy at `member` of the troop
    /// —from 0, in troop order— gains or loses `amount`. `what` is 0 for the HP and
    /// 1 for the SP, and bit 7 on top lets a loss of HP kill. It only runs in a
    /// troop page, inside a battle.
    OP_ENEMY = 0x37 (member: byte, what: byte, amount: signed word);

    /// `InputNumber`, together with the `ShowMessage` right before it: the box
    /// `window` opens with its lines and, on the line below them, `digits` digits
    /// the player changes one at a time. A writes the number to the variable at
    /// `slot`, saturated at 65535 —the variables are sixteen bits—, and the page
    /// goes on.
    OP_NUMBER = 0x38 (slot: byte, digits: byte, window: word);

    /// Numbers held for opcodes that other branches are adding at the same time:
    /// the dispatch table cannot have gaps, so until those land each one is here
    /// and ends the page like an unknown number would. Whoever brings the real
    /// opcode replaces its entry.
    OP_RESERVED_39 = 0x39 ();

    OP_RESERVED_3A = 0x3A ();

    OP_RESERVED_3B = 0x3B ();

    OP_RESERVED_3C = 0x3C ();

    /// The big pictures, the ones the cartridge carries as a background layer
    /// instead of in the sprites: `image` is an entry of `big_table`, which is the
    /// cartridge's and not a map's. Showing one takes the screen off a moment to
    /// put BG1 in mode 1 with the picture; its place is in the layer, so it has no
    /// position. The tone is RM2k's, 100 neutral; `transparency` darkens it, since
    /// there is only black under it; `saturation` is RM2k's, 100 neutral; `wave`
    /// is the strength of RM2k's wave effect, 0 for none. `OP_PICTURE_ERASE` with
    /// slot $80 takes it down.
    OP_BIG_SHOW = 0x3D (
        image: byte, red: byte, green: byte, blue: byte, transparency: byte,
        saturation: byte, wave: byte,
    );

    /// And its `MovePicture`: the tone, the transparency, the centre's `y` on
    /// RM2k's screen —it scrolls the layer up or down; sideways it does not move—
    /// and the wave's strength it goes to in `frames`, and the saturation it
    /// takes at once.
    OP_BIG_MOVE = 0x3E (
        red: byte, green: byte, blue: byte, transparency: byte, frames: byte,
        y: signed word, wave: byte, saturation: byte,
    );

    /// `CallEvent` inside a shared common event body: the body `body` —its index
    /// among the cartridge's shared bodies— runs, and when it ends the page goes
    /// on after this. The interpreter keeps where it was on a short stack; a call
    /// with the stack full is skipped.
    OP_CALL = 0x3F (body: byte);

    /// The end of a shared body: back to whoever called it or, if nobody did
    /// —an automatic common event—, the end of the page. Since 2026-10-15
    /// `OP_DONE` does the same, because a called page ends in it: the two are
    /// one handler in the runtime, and this one stays for the bodies that
    /// end in it.
    OP_RETURN = 0x40 ();

    /// `MessageOptions`: how and where the message window is drawn from now
    /// on, in one byte the console keeps in the save —`FAR_MSG_OPTIONS`—. The
    /// position in bits 0 and 1 (0 top, 1 middle, 2 bottom); bit 2 without
    /// the frame and the background; bit 3 that the window moves out of the
    /// hero's way; bit 4 that the events go on moving while a page runs.
    OP_MESSAGE_OPTIONS = 0x41 (options: byte);

    /// `ChangeExp` and `ChangeLevel`: actor `actor` —0 the whole party—
    /// gains or loses `amount` of experience or of levels, as
    /// `Game_Actor::ChangeExp` and `ChangeLevel` do it, with the skills the
    /// levels it goes through teach. `what` carries bits: levels and not
    /// experience ($01), note the level-up message for `OP_LEVEL_PAGE`
    /// ($02), `amount`'s low byte as a variable's slot ($20), and
    /// subtracting ($80). See `exp_change` in the runtime's `level.s`.
    OP_EXP = 0x42 (actor: byte, what: byte, amount: long);

    /// A big picture's `MovePicture` that zooms: `OP_BIG_MOVE`'s operands and
    /// the size it goes to in the same `frames`, in percent of the size it was
    /// shown at —0 is gone—. It is only emitted for a picture the cartridge
    /// carries with a mode 7 texture: the console shows it still in mode 1 and
    /// zooms it in mode 7. See `big_picture.s` in the runtime.
    OP_BIG_ZOOM = 0x43 (
        red: byte, green: byte, blue: byte, transparency: byte, frames: byte,
        y: signed word, wave: byte, saturation: byte, size: byte,
    );

    /// The level-up message of the `OP_EXP` right before it, one page at a
    /// time: "<name> <level> <n><level_up>" for each actor that went up and
    /// a line for each skill it did not know, four lines a page and a new
    /// page for each actor, which is RM2k's `PendingMessage`. It opens each
    /// page in the map's window and stays on itself until none is left;
    /// with none, the page goes on. See `level_page` in `level.s`.
    OP_LEVEL_PAGE = 0x44 ();

    /// A custom menu, `menu` by its order in the project's `[menus]`: the
    /// engine's screen, which blocks inside the page like the save screen
    /// and costs no tick, and the map back when it closes. It is what the
    /// common event the menu replaces compiles to —`replaces_common`—, so an
    /// item or a page that turned that common event on opens the menu. See
    /// `custom_menu.s` in the runtime.
    OP_MENU_OPEN = 0x45 (menu: byte);

    /// `ChangePBG`: how the map's panorama loops —bit 0 across, bit 1
    /// down— and how far it moves on its own each frame on each axis, in
    /// 1/32 px. The picture stays. See `op_panorama` in `pano.s`.
    OP_PANORAMA = 0x46 (loops: byte, across: word, down: word);

    /// `ConditionalBranch` by a character's direction (case 6): `target` is
    /// 0 for the hero and an event's index plus one —as in `OP_ROUTE`—, and
    /// `direction` is RM2k's facing, 0 up, 1 right, 2 down, 3 left. Like
    /// `OP_IF_ACTOR` it has no polarity: the branch below is the `else`.
    OP_IF_FACING = 0x47 (target: byte, direction: byte, destination: word);

    /// `PlayerVisibility`: whether the hero's sprite is drawn. He stays where he
    /// is, and keeps blocking and triggering: only the drawing goes. The state
    /// outlives the map and travels in the save, as RM2k's does.
    OP_HERO_VISIBLE = 0x48 (visible: byte);

    /// `EraseEvent`: event `target` —its index plus one, as in `OP_ROUTE`—
    /// is out until the map is loaded again: it is not drawn, it does not
    /// block and nothing fires it. A parallel page that runs it ends there;
    /// a foreground one goes on, as in RM2k. See `op_erase_event` in the
    /// runtime's `interpreter_movement.s`.
    OP_ERASE_EVENT = 0x49 (target: byte);

    /// `EraseScreen`: the screen down to black and left there, with the game
    /// frozen while it goes, as RM2k does. `transition` is what the ROM does
    /// —the fade, the mosaic or the cut, `ChangeScreenTransitions`' values—
    /// or $FF for the teleport's erase. Over a screen already erased it does
    /// nothing. See `screen_erase` in the runtime's `teleport_transition.s`.
    OP_ERASE_SCREEN = 0x4A (transition: byte);

    /// `ShowScreen`: the screen an `OP_ERASE_SCREEN` left black, back up;
    /// $FF for the teleport's show. Over a screen that is not erased it does
    /// nothing. See `screen_show` in `teleport_transition.s`.
    OP_SHOW_SCREEN = 0x4B (transition: byte);

    /// `TerminateBattle`, from a troop page: the page ends and so does the
    /// battle, with no victory —no experience, no gold, no screen— and
    /// `BA_ABORT` as its result, which `OP_BATTLE` sends to `on_abort`. On a
    /// map it does nothing, as in RM2k. See `op_battle_abort` in the
    /// runtime's `battle_troop.s`.
    OP_BATTLE_ABORT = 0x4C ();

    /// `ChangeSystemGraphics`: the message window is drawn with System
    /// `system` from here on, an index into the cartridge's Systems —0 the
    /// one it starts with—. It lasts, and travels in the save. See
    /// `op_change_system` in the runtime's `window_system.s`.
    OP_CHANGE_SYSTEM = 0x4D (system: byte);

    /// `ChangeMonsterCondition`, from a troop page: the enemy at `place` of
    /// the troop gets —`remove` at 0— or loses condition `state`, by its
    /// LDB number, as `Game_Battler::AddState` and `RemoveState` do in
    /// battle. Adding the dead one (1) kills it. See `ba_st_change` in the
    /// runtime's `battle_states.s`.
    OP_MONSTER_STATE = 0x4E (place: byte, remove: byte, state: byte);

    /// `ChangeItems` with the item or the amount in a variable: what `OP_ITEM`
    /// does, read at run time. `how` carries bits: subtracting ($01), `item`
    /// as a variable's slot ($02) and `amount` as a variable's slot ($04);
    /// without them each is the constant, the item by its LDB number. As
    /// `CommandChangeItems`, a value below zero does nothing, and an item out
    /// of the inventory neither. See `item_by_variable` in the runtime's
    /// `items_by_variable.s`.
    OP_ITEM_VAR = 0x4F (how: byte, item: word, amount: word);

    /// `CallEvent` to a page of a map event: the page whose index in the
    /// loaded map's page table is `page` runs —its own bytes, the ones the
    /// table points at for the page itself—, and when its `OP_DONE` comes the
    /// caller goes on after this. The interpreter keeps where it was on the
    /// same stack as `OP_CALL`'s, `CALL_LEVELS` deep; a call with the stack
    /// full, or to a page with no code, is skipped. Until 2026-10-15 the
    /// called page was pasted into the caller, and Frozen World's battle
    /// screen, a chain of such calls, came to four megabytes of bytecode.
    OP_CALL_PAGE = 0x50 (page: word);

    /// RPG Maker 2003's `ForceFlee` for the party, from a troop page: the
    /// page ends here and the battle with it, as an escape that cannot fail
    /// —EasyRPG's `force_flee_enabled`, which `Scene_Battle::TryEscape`
    /// honours before the dice—: the fled message, the escape sound, and the
    /// encounter's escape handler. `ba_page_step` sees it when the stretch
    /// comes back, like `OP_BATTLE_ABORT`; on a map it does nothing. See
    /// `op_battle_flee` in the runtime's `interpreter_shop_and_battle.s`.
    OP_BATTLE_FLEE = 0x51 ();

    /// Held for opcodes other branches are adding: they end the page until
    /// they land.
    OP_RESERVED_52 = 0x52 ();
    OP_RESERVED_53 = 0x53 ();

    /// `ChangeHeroName`: the actor at `place` among the ones some
    /// `ChangeHeroName` of the game renames carries rename `name` of the
    /// game's from here on, counted from one; zero would be the database's
    /// name. It lasts, and travels in the save. Every screen that draws an
    /// actor's name, and the `\N[n]` of a message, asks `actor_name_txt`. See
    /// `op_change_name` in the runtime's `actor_names.s`.
    OP_CHANGE_NAME = 0x54 (place: byte, name: byte);

    /// `ChangeFaceGraphic`: from the next box on, the message window draws
    /// face `face` of the cartridge's —its place in `message_face_ptr`,
    /// $FFFF for none— on the left or, with `right` at 1, on the right. It
    /// lasts, as `Game_System`'s face does, until the next one. A mirrored
    /// face is a face of its own: the converter emits it flipped. See
    /// `face_change` in the runtime's `message_face.s`.
    OP_FACE = 0x55 (face: word, right: byte);
}

/// How deep the interpreter's call stack is: how many `OP_CALL` and
/// `OP_CALL_PAGE` can be waiting for an `OP_DONE` at once. A call past it is
/// skipped. It is the runtime's `CALL_LEVELS` in `common_events.s`, where
/// the stack is declared and the number is explained, and a test in
/// `rm2k-snes-convert` keeps the two the same; the compiler reports, in the
/// degradations, every chain of calls it can see is deeper.
pub const CALL_LEVELS: usize = 8;

// `run_code` jumps through a table indexed by the opcode.
const _: () = BYTECODE.check_dispatch();
