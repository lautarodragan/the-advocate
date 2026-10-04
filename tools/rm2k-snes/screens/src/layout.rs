//! Where everything goes on the screens: the geometry they are drawn with,
//! which is also what the cartridge's code needs to write on them.
//!
//! **It lives here and nowhere else.** The emission of the cartridge —the
//! tables and constants its code reads— writes these same numbers, and it
//! gets them from [`publish`], by the names below, instead of keeping a
//! copy: a screen drawn with one number and written with another is a
//! screen that breaks without anyone having touched it.
//!
//! RM2k draws these screens at 320x240, with windows and the font at six
//! pixels. The console's are 256x224, and most text goes one letter per
//! 8x8 cell, so the geometry is the port's and not RM2k's: it is cosmetic,
//! and declared. What does come from RM2k —the terms, the order of
//! things, how a window is drawn— comes from the game.

use crate::cells::{CELL, COLS, HEIGHT, WIDTH};
use rm2k_snes_text::font;
use serde_json::{json, Map, Value};

// --- the slot screen ---------------------------------------------------------
//
// Both ends use it: "load" on the title, and a save point. It is a screen of
// its own, so it has VRAM all to itself and everything can go at 4bpp.
//
// **The text that does not depend on the save is pre-rendered**, including
// the two variants of each slot —empty and taken— and the level term. What
// does depend on it —the leader's name and level— is composed one letter per
// cell with loose glyphs: baked, each actor's text added some seven tiles it
// shared with nobody, and the bank grew with every actor that could be in
// the party.
//
// What the cartridge does on the fly is **choose which block of cells it
// writes on each row**: per slot there are four —empty or full, with cursor
// or without— and moving the cursor is rewriting two rows.
//
// The row is **48 pixels, six cells**, which is the size of a FaceSet face:
// `Window_SaveFile::Refresh` in easyrpg draws, per file, the file name, the
// leader's, the level and the hit points, and the faces of up to four of the
// party. Here there are three lines of text on the left and up to three faces
// on the right: the fourth does not fit in 256 pixels. Four rows of 48 plus
// the header end at line 216 of the 224.
/// Where the first row starts, in pixels.
pub const SLOT_Y: usize = 24;
/// And how far apart the next one is. **A multiple of 8 on purpose**: each
/// row is uploaded to the tilemap as a block of whole cells.
pub const SLOT_STEP: usize = 48;
/// The 8 px cells each row takes.
pub const SLOT_ROWS: usize = 6;
/// Where the text starts.
pub const SLOT_X: usize = 56;
/// How far apart the text lines in a row are.
pub const LINE: usize = 16;
pub const HEADER_Y: usize = 4;
pub const HEADER_ROWS: usize = 2;
/// What a slot without a save says. RM2k has no term for this —its menu
/// shows the empty gap— so the text is the port's, and is written here and
/// not taken from the database.
///
/// Measured against A Blurred Line: an assumption of the engine, not a fact
/// of the game.
pub const EMPTY: &str = "- Empty -";
/// The faces: where the first one goes, in cells from the left edge, and
/// how far apart the next one is. Six wide by six tall, touching.
pub const FACE: usize = 48;
pub const FACE_CELLS: usize = FACE / CELL;
pub const FACE_COL: usize = 14;
pub const FACE_STEP: usize = FACE_CELLS;
pub const FACES_MAX: usize = 3;
/// The leader's name, on the second line: from the text to the first face.
pub const NAME_COL: usize = SLOT_X / CELL;
pub const NAME_COLS: usize = FACE_COL - NAME_COL;
pub const NAME_ROW: usize = LINE / CELL;
/// The third line, the level: the two digits after the level term, which
/// is baked because it is the same for everyone. The number starts in the
/// cell after the term, which is two of the font's letters wide.
pub const LEVEL_ROW: usize = 2 * LINE / CELL;
/// `"%2d"`, which is what RM2k shows.
pub const LEVEL_DIGITS: usize = 2;
pub const LEVEL_COL: usize = (SLOT_X + 2 * font::WIDTH) / CELL;
/// The palettes of BG2 at 4bpp are eight: 0 is the text's, 1 the disabled
/// commands', and each face carries its own from 2.
pub const FACE_PALETTES_MAX: usize = 7;
/// How many tiles fit in the screen's bank: see the VRAM checks.
pub const SLOT_TILES_MAX: usize = 448;

// --- what depends on the actor ----------------------------------------------------
//
// The name, the level and the max HP **are not baked** per actor: the only
// thing that grows per actor is the faces. The numbers go **one per cell**,
// like the gold, from glyphs —the digits, the slash, the dash and the
// space—, and the price is declared: they go at an 8-pixel pitch and not at
// the font's. The names are **composed**, since 2026-10-03, into tiles of
// their own each time the screen opens: one per cell they left gaps of three
// pixels between the letters of a variable-width font. See `tl_strip` in
// the runtime.
//
// Both are drawn **from the same place in the cell** —one in x, two in y—,
// which is also the text screens' (`SCR_TEXT_X`, `SCR_TEXT_Y`).
/// The cell where a loose glyph is drawn; both are arbitrary.
pub const GLYPH_COL: usize = 3;
pub const GLYPH_ROW: usize = 25;
/// Centered in the cell: 6 px of font in 8.
pub const GLYPH_DX: usize = 1;
pub const GLYPH_DY: usize = 2;

// --- the pause menu ----------------------------------------------------------
//
// RM2k's `Scene_Menu` at 256x224: the command column on the left, the gold at
// the bottom left and the party on the right, **without the windows** —black
// background, like the slot screen— and without what does not fit: the
// actor's title and the SP. It lives in the **same tile bank and the same
// palette** as the slot screen: the faces are the same, and the save screen
// is opened from the menu.
pub const MENU_OPTIONS: usize = 5;
pub const MENU_OPT_Y: usize = 8;
pub const MENU_OPT_STEP: usize = 16;
pub const MENU_OPT_COL: usize = 3;
pub const MENU_OPT_COLS: usize = 9;
pub const MENU_CURSOR_COL: usize = 1;
/// Which commands do something. The others are drawn in the "cannot"
/// colour, system colour 3, the way RM2k draws "Save" when it is
/// forbidden: today that is only the skills. Saving also depends on
/// `ChangeSaveAccess`.
pub const MENU_ITEMS: usize = 0;
pub const MENU_EQUIPMENT: usize = 2;
pub const MENU_SAVE: usize = 3;
pub const MENU_END: usize = 4;
pub const MENU_DONE: [usize; 4] = [MENU_ITEMS, MENU_EQUIPMENT, MENU_SAVE, MENU_END];
/// The gold, at the bottom left: up to six digits **one cell each**, so the
/// cartridge writes them one at a time without rebuilding tiles, and the
/// currency term after them, in colour 1.
pub const MENU_GOLD_Y: usize = 200;
pub const MENU_GOLD_COL: usize = 3;
pub const MENU_GOLD_DIGITS: usize = 6;
pub const MENU_CURRENCY_COL: usize = MENU_GOLD_COL + MENU_GOLD_DIGITS;
pub const MENU_CURRENCY_COLS: usize = 3;
/// The party: a row of seven cells per actor, with the face on the left and
/// the text beside it. Four rows are exactly 224 pixels.
pub const MENU_ACTOR_COL: usize = 12;
pub const MENU_ACTOR_COLS: usize = COLS - MENU_ACTOR_COL;
pub const MENU_ACTOR_ROWS: usize = 7;
pub const MENU_TEXT_X: usize = MENU_ACTOR_COL * CELL + FACE + 8;
/// "Normal" goes 42 from the level, as in RM2k.
pub const MENU_STATUS_DX: usize = 42;
pub const MENU_PARTY_ROWS: usize = 4;
/// The current HP: three digits **one cell each**, for the same reason as
/// the gold. They go on the third line of the actor's row, where the gold
/// digits land aligned; the maximum goes after, with the slash.
pub const MENU_HP_DIGITS: usize = 3;
pub const MENU_HP_COL: usize = 21;
pub const MENU_HP_ROW: usize = 4;
pub const MENU_MAX_X: usize = (MENU_HP_COL + MENU_HP_DIGITS) * CELL;
/// Where, inside the actor's row, the three strips the cartridge composes
/// with glyphs land: the name, the two level digits and the maximum.
pub const MENU_NAME_COL: usize = MENU_TEXT_X / CELL;
pub const MENU_NAME_COLS: usize = COLS - MENU_NAME_COL;
pub const MENU_NAME_ROW: usize = 0;
pub const MENU_LEVEL_COL: usize = (MENU_TEXT_X + 2 * font::WIDTH) / CELL;
pub const MENU_LEVEL_ROW: usize = LINE / CELL;
pub const MENU_MAX_COL: usize = MENU_MAX_X / CELL;
/// The slash and up to three digits: "/168".
pub const MENU_MAX_DIGITS: usize = 4;
/// The experience, the third line of `Window_MenuStatus`: the term in
/// colour 1, and the current one and the next level's, six digits each with
/// the slash in between, `"%6d/%6d"` like `DrawActorExp`.
///
/// **It goes in sprites, not in the tilemap**, and it is the only line on
/// this screen that is not on the grid: RM2k's two columns do not fit in 256
/// pixels, and a fourth line of cells does not fit in the row. In sprites it
/// goes twelve pixels below the HP, at the font's six pixels. The tiles are
/// the bank's own glyphs.
pub const MENU_EXP_X: usize = MENU_TEXT_X;
pub const MENU_EXP_Y: usize = 2 + 2 * LINE + 11;
pub const MENU_EXP_NUM_DX: usize = 12;
pub const MENU_EXP_DIGITS: usize = 6;
pub const MENU_EXP_LETTERS: usize = 2 * MENU_EXP_DIGITS + 1;
/// The term, "Ex" in A Blurred Line: twelve pixels, two cells wide.
pub const MENU_EXP_TERM_CELLS: usize = 2;

// --- the item screen ---------------------------------------------------------
//
// `Scene_Item`: on top the description of the marked item and below the
// inventory list with how many there are, in **one** column —RM2k's two do
// not fit—. The text goes **one letter per cell**: the screen carries its own
// bank with each font character in two cells, in four colours, and the
// cartridge writes two tilemap words per letter. That way the cost does not
// depend on how many items there are.
pub const ITEM_DESC_Y: usize = 8;
pub const ITEM_DESC_COL: usize = 1;
/// The description's cells: a line takes [`DESC_WIDTH_PX`].
pub const ITEM_DESC_WIDTH: usize = 30;
/// The pixels a description line may take: its cells, from where a text
/// starts inside its first one.
pub const DESC_WIDTH_PX: usize = ITEM_DESC_WIDTH * CELL - SCR_TEXT_X;
pub const ITEM_DESC_LINES: usize = 2;
/// With ten rows from 56 both windows leave the same spacing as RM2k.
pub const ITEM_LIST_Y: usize = 56;
pub const ITEM_ROWS: usize = 10;
pub const ITEM_CURSOR_COL: usize = 1;
/// x = 24, like the menu's commands.
pub const ITEM_NAME_COL: usize = 3;
/// The longest name in A Blurred Line.
pub const ITEM_NAME_WIDTH: usize = 20;
pub const ITEM_COLON_COL: usize = 27;
/// Two digits, 28 and 29.
pub const ITEM_DIGITS_COL: usize = 28;
/// The characters the font has: from the space to the tilde.
pub const ITEM_FIRST_CHAR: usize = font::FIRST as usize;
pub const ITEM_CHARS: usize = font::GLYPHS;
/// The font variants: the index is what the cartridge carries, and also
/// its palette. `ITEM_UP` is system colour 2, `Window_EquipStatus`'s "goes
/// up" one, and only the equipment screen uses it for a parameter's new
/// value, so it carries **only the digits**: the whole font in one more
/// colour is some 150 tiles the battle's bank does not have. `ITEM_RED` is
/// colour 1, the red of the terms, and goes **whole**: tiles are
/// deduplicated by index and the red's gradient lands on the same indices
/// as the white's, so it is ten more tiles.
pub const ITEM_WHITE: usize = 0;
pub const ITEM_GRAY: usize = 1;
pub const ITEM_UP: usize = 2;
pub const ITEM_RED: usize = 3;
/// The system colour of each variant.
pub const ITEM_COLORS: [i32; 4] = [0, 3, 2, 1];
pub const ITEM_UP_CHARS: &str = "0123456789 ";
/// How far the font bank can grow: the battle uploads it and then writes
/// its scene's tilemap at VRAM word $3800, which is tile 384 counting from
/// the bank's base.
pub const ITEMS_TILES_MAX: usize = (0x3800 - 0x2000) / 16;
/// The screen's windows, like `Scene_Item`: the help one on top and the
/// list one below, the System's, right against each other. The help one is
/// taller than RM2k's —32— because the description goes on two lines.
///
/// They go on **BG1**, and the text stays on BG2: that way the text does
/// not have to know anything about the windows. At 8bpp a pixel is
/// directly its colour-memory entry: the frame's colours go from
/// `ITEM_BORDER_CGRAM`, after the four text palettes, and black is 0, the
/// transparent one.
pub const ITEM_HELP_HEIGHT: usize = 48;
pub const ITEM_WINDOWS: [Rect; 2] = [
    (0, 0, WIDTH, ITEM_HELP_HEIGHT),
    (0, ITEM_HELP_HEIGHT, WIDTH, HEIGHT - ITEM_HELP_HEIGHT),
];
pub const ITEM_BORDER_CGRAM: usize = 4 * MENU_CGRAM;
/// The windows' tilemap: where the battle puts its scene's, so nothing of
/// this screen is there.
pub const ITEM_BORDER_MAP: usize = 0x3800;
/// The list's cursor is the System's —RM2k's red bar—: four pixels wider
/// than the text on each side.
pub const ITEM_BAR_X: usize = ITEM_NAME_COL * CELL - 4;
pub const ITEM_BAR_WIDTH: usize = (ITEM_DIGITS_COL + 2 - ITEM_NAME_COL) * CELL + 8;

/// How many colour-memory entries a 4bpp palette takes: the menu's, at the
/// bottom because a 4bpp BG only reaches the low ones.
pub const MENU_CGRAM: usize = 16;

// --- the text layer ------------------------------------------------------------
//
// The text screens' text is composed —see `text_layer.s` in the runtime—: a
// write starts at a cell, and its letters go one after the other at their own
// advance, each line in two cell rows of its own tiles.
/// Where a text starts inside its first cell, in x: the pixel the
/// one-letter-per-cell font drew its letters from, so the text did not move.
pub const SCR_TEXT_X: usize = 1;
/// And where the glyph's first row goes, inside the line's two cell rows.
pub const SCR_TEXT_Y: usize = 2;

/// A window: x, y, width and height.
pub type Rect = (usize, usize, usize, usize);

// --- the actor choice --------------------------------------------------------
//
// `Scene_ActorTarget`: the menu's party panel, three System windows on BG1
// and the red bar over the marked row. The left column reaches x = 104: the
// faces are 48 wide but what shows of them starts twelve pixels in, so the
// party window can start left of the menu row without covering them. At 104
// eleven 8-pixel letters fit, and the medicine's name goes on two lines.
//
// "Owned Items" is **baked into BG1**, in red and at the font's six pixels:
// at eight its letters fill the window and leave no room for the quantity,
// and the red has no free palette on BG2. The quantity goes with the glyphs.
//
// It is only for medicines: whom to equip is chosen on the pause menu, with
// `MENU_BAR`.
pub const TARGET_LEFT: usize = 104;
pub const TARGET_NAME_HEIGHT: usize = 48;
pub const TARGET_COUNT_HEIGHT: usize = 32;
pub const TARGET_PARTY: Rect = (TARGET_LEFT, 0, WIDTH - TARGET_LEFT, HEIGHT);
pub const TARGET_WINDOWS: [Rect; 3] = [
    (0, 0, TARGET_LEFT, TARGET_NAME_HEIGHT),
    (0, TARGET_NAME_HEIGHT, TARGET_LEFT, TARGET_COUNT_HEIGHT),
    TARGET_PARTY,
];
pub const TARGET_NAME_COL: usize = 1;
/// y = 8, and the second line at y = 24.
pub const TARGET_NAME_ROW: usize = 1;
pub const TARGET_NAME_WIDTH: usize = (TARGET_LEFT - 8) / CELL - TARGET_NAME_COL;
pub const TARGET_COUNT_ROW: usize = (TARGET_NAME_HEIGHT + 8) / CELL;
pub const TARGET_COUNT_COL: usize = TARGET_NAME_COL + TARGET_NAME_WIDTH - 2;
/// The bar goes over the row's three lines of text, as in RM2k, and not
/// over the face; from two pixels inside the row, so as not to touch the
/// top frame, and it ends on a cell boundary: with the bottom tip
/// mid-cell it was 64 tiles, exactly what fits before the tilemap.
pub const TARGET_BAR: Rect = (MENU_TEXT_X - 4, 2, WIDTH - MENU_TEXT_X, 3 * LINE - 2);
/// The same bar on the pause menu, where `Scene_Menu` chooses whom to equip
/// over its own party panel: there are no windows under it, so it is drawn
/// over nothing, and it is taller because the row has a fourth line, the
/// experience. It covers every pixel of the row's text and its shadows —the
/// cursor's edge is one dark pixel, so the red starts one in—: the name
/// starts at y = 3 and the experience, which is sprites below the cell
/// grid, ends at y = 56, one past the row. So the bar goes from y = 2 to
/// y = 57 —red from 3 to 56— and reaches into the next row, which has no
/// bar then. Measured against the capture on 2026-09-30: at y = 2..53 the
/// bottom of "Ex" was left over black. Starting at 2 and not higher, the
/// top cells are the actor choice's and the bar costs two tiles.
pub const MENU_BAR: Rect = (MENU_TEXT_X - 4, 2, WIDTH - MENU_TEXT_X, MENU_ACTOR_ROWS * CELL + 1);
/// BG1's colours: those of sprite palette 0, which on this screen are off
/// and on the pause menu are not used: the experience goes in palette 1.
/// There is no room in 0..127: they are the menu bank's palettes.
pub const TARGET_CGRAM: usize = 128;
pub const TARGET_COLORS_MAX: usize = 16;
/// BG1's tiles and tilemap, after the menu's tilemap: BG1 has its own base
/// at $4000, so they do not touch BG2's bank.
pub const TARGET_VRAM: usize = 0x4000;
pub const TARGET_MAP: usize = 0x4800;

// --- equipment ---------------------------------------------------------------
//
// `Scene_Equip`: the actor, its four parameters, the five slots with what it
// has equipped, and on choosing a slot the list of what can go there, with
// the parameters that would result. The list **replaces** the slots while
// choosing. The actor and the slots do not fit side by side, so there are
// three windows, one below the other: the help, same as the item screen's;
// the actor's, with its parameters in one column; and the bottom one, which
// shows the slots or the list.
pub const EQ_WEAPON: usize = rm2k_rules::actor::SLOT_WEAPON;
pub const EQ_SHIELD: usize = rm2k_rules::actor::SLOT_SHIELD;
/// How many equipment slots an RM2k actor has: weapon, shield, armor,
/// helmet, accessory.
pub const EQUIPMENT_SLOTS: usize = rm2k_rules::actor::EQUIPMENT_SLOTS;
pub const EQ_STATUS_Y: usize = ITEM_HELP_HEIGHT;
/// Four parameters of 16, and RM2k's spacing.
pub const EQ_BOTTOM_Y: usize = 128;
pub const EQ_WINDOWS: [Rect; 3] = [
    (0, 0, WIDTH, ITEM_HELP_HEIGHT),
    (0, EQ_STATUS_Y, WIDTH, EQ_BOTTOM_Y - EQ_STATUS_Y),
    (0, EQ_BOTTOM_Y, WIDTH, HEIGHT - EQ_BOTTOM_Y),
];
pub const EQ_ACTOR_ROW: usize = EQ_STATUS_Y / CELL + 1;
/// Two cells of spacing, and twelve letters up to 30.
pub const EQ_ACTOR_COL: usize = 19;
pub const EQ_PARAMS: [(usize, usize); 4] = [
    (EQ_ACTOR_ROW, 1),
    (EQ_ACTOR_ROW + 2, 1),
    (EQ_ACTOR_ROW + 4, 1),
    (EQ_ACTOR_ROW + 6, 1),
];
/// The value, three digits from here, with spacing.
pub const EQ_PARAM_VALUE: usize = 9;
/// ">" and the new value, while choosing.
pub const EQ_PARAM_ARROW: usize = 12;
pub const EQ_SLOT_ROW0: usize = EQ_BOTTOM_Y / CELL + 1;
/// The three windows start their text in the same column, the
/// parameters'.
pub const EQ_TEXT_COL: usize = EQ_PARAMS[0].1;
/// The term and what is equipped go together, with no cell in between: that
/// is how RM2k puts them, and how the longest name fits before where the
/// bar ends.
pub const EQ_SLOT_TERM_COL: usize = EQ_TEXT_COL;
/// "Right Hand".
pub const EQ_SLOT_TERM_WIDTH: usize = 10;
pub const EQ_SLOT_NAME_COL: usize = EQ_SLOT_TERM_COL + EQ_SLOT_TERM_WIDTH;
/// Up to column 29, like the item count.
pub const EQ_SLOT_NAME_WIDTH: usize = 19;
pub const EQ_LIST_ROW0: usize = EQ_SLOT_ROW0;
/// 17 + 5 * 2 = 27: the bottom frame.
pub const EQ_LIST_ROWS: usize = 5;
pub const EQ_LIST_NAME_COL: usize = EQ_TEXT_COL;
/// The bars, four pixels wider than the text on each side, as on the item
/// screen: x and width.
pub const EQ_BAR_SLOT: (usize, usize) = (
    EQ_TEXT_COL * CELL - 4,
    (ITEM_DIGITS_COL + 2 - EQ_TEXT_COL) * CELL + 8,
);
pub const EQ_BAR_LIST: (usize, usize) = EQ_BAR_SLOT;

// --- the shop ----------------------------------------------------------------
//
// `Scene_Shop`. On the main one, the shopkeeper's greeting and the commands.
// Buying shows what it sells with its price —in gray what the gold does not
// cover or is already at 99— and the gold, how many are owned and how many
// the party has equipped; selling, the inventory at half price. Once one is
// chosen, the quantity. After each purchase or sale the message says "done"
// for one second.
//
// At 256x224 and with 8-pixel letters, the list and RM2k's right column **do
// not fit side by side**, so the right column goes down, between the list and
// the message: "Owned Items" and "Equipped Items" in one window, and the gold
// in another to its right. There are three layouts, which share the help on
// top: the main one, the buy one —which the sale's quantity and both "done"s
// use too— and the sell one.
pub const TI_MAIN: usize = 0;
pub const TI_BUY: usize = 1;
pub const TI_COUNT_BUY: usize = 2;
pub const TI_BOUGHT: usize = 3;
pub const TI_SELL: usize = 4;
pub const TI_COUNT_SALE: usize = 5;
pub const TI_SOLD: usize = 6;
/// Frames the "done" lasts: `DEFAULT_FPS`.
pub const TI_SECOND: usize = 60;
pub const TI_LAYER_MAIN: usize = 0;
pub const TI_LAYER_BUY: usize = 1;
pub const TI_LAYER_SALE: usize = 2;
pub const TI_LAYER_OF_MODE: [usize; 7] = [
    TI_LAYER_MAIN,
    TI_LAYER_BUY,
    TI_LAYER_BUY,
    TI_LAYER_BUY,
    TI_LAYER_SALE,
    TI_LAYER_BUY,
    TI_LAYER_BUY,
];
pub const TI_MIDDLE_Y: usize = ITEM_HELP_HEIGHT;
/// The main one: the message at the bottom with two lines and the three
/// commands **right after the message**, as in RM2k: with a one-line
/// greeting they start one line higher.
pub const TI_MAIN_MSG_Y: usize = 128;
pub const TI_MAIN_MSG_ROW: usize = TI_MAIN_MSG_Y / CELL + 1;
/// 16 pixels further in than the message: RM2k.
pub const TI_COMMAND_COL: usize = 3;
/// The first, with a one-line greeting.
pub const TI_COMMAND_POSITIONS: usize = 4;
/// The buy one: the count and the gold under the list, side by side, and
/// the one-line message.
pub const TI_STATUS_Y: usize = 144;
pub const TI_MSG_Y: usize = 192;
/// "Equipped Items" and two digits, and the frame.
pub const TI_GOLD_X: usize = 152;
pub const TI_MSG_ROW: usize = TI_MSG_Y / CELL + 1;
pub const TI_OWNED_ROW: usize = TI_STATUS_Y / CELL + 1;
pub const TI_CARRIED_ROW: usize = TI_OWNED_ROW + 2;
pub const TI_STATUS_COL: usize = 1;
/// Two digits, up to the frame.
pub const TI_STATUS_NUM: usize = TI_GOLD_X / CELL - 3;
/// In the middle of its window.
pub const TI_GOLD_ROW: usize = TI_OWNED_ROW + 1;
/// The gold's last digit; the currency after it.
pub const TI_GOLD_COL: usize = 28;
pub const TI_LIST_ROW0: usize = TI_MIDDLE_Y / CELL + 1;
pub const TI_LIST_COL: usize = 1;
/// 7 + 5 * 2 = 17: the bottom frame.
pub const TI_LIST_ROWS_BUY: usize = 5;
pub const TI_LIST_ROWS_SALE: usize = 8;
/// The price's last digit.
pub const TI_PRICE_COL: usize = 29;
/// The quantity: the item, "x" and the two digits, which carry the bar, and
/// the total below.
pub const TI_COUNT_ROW: usize = TI_LIST_ROW0 + 2;
pub const TI_COUNT_X_COL: usize = 24;
pub const TI_COUNT_COL: usize = 26;
pub const TI_TOTAL_ROW: usize = TI_COUNT_ROW + 4;
/// The windows of each layout, under the help on top.
pub fn ti_windows(layer: usize) -> Vec<Rect> {
    match layer {
        TI_LAYER_MAIN => vec![
            (0, TI_MIDDLE_Y, WIDTH, TI_MAIN_MSG_Y - TI_MIDDLE_Y),
            (0, TI_MAIN_MSG_Y, WIDTH, HEIGHT - TI_MAIN_MSG_Y),
        ],
        TI_LAYER_BUY => vec![
            (0, TI_MIDDLE_Y, WIDTH, TI_STATUS_Y - TI_MIDDLE_Y),
            (0, TI_STATUS_Y, TI_GOLD_X, TI_MSG_Y - TI_STATUS_Y),
            (TI_GOLD_X, TI_STATUS_Y, WIDTH - TI_GOLD_X, TI_MSG_Y - TI_STATUS_Y),
            (0, TI_MSG_Y, WIDTH, HEIGHT - TI_MSG_Y),
        ],
        _ => vec![
            (0, TI_MIDDLE_Y, WIDTH, TI_MSG_Y - TI_MIDDLE_Y),
            (0, TI_MSG_Y, WIDTH, HEIGHT - TI_MSG_Y),
        ],
    }
}
/// The bars, x and width. The lists' are the equipment one; the commands'
/// starts where the message does and ends where the others do; the
/// quantity's goes over the two digits.
pub const TI_BAR_LIST: (usize, usize) = (
    TI_LIST_COL * CELL - 4,
    (TI_PRICE_COL + 1 - TI_LIST_COL) * CELL + 8,
);
pub const TI_BAR_COMMAND: (usize, usize) = (12, TI_BAR_LIST.0 + TI_BAR_LIST.1 - 12);
pub const TI_BAR_COUNT: (usize, usize) = (TI_COUNT_COL * CELL - 4, 2 * CELL + 8);
/// Where they go in VRAM: the tiles with **their own BG1 base** —there is
/// no room left in the font's—, and the tilemap where the items' is.
pub const TI_VRAM: usize = 0x4000;
pub const TI_MAP: usize = ITEM_BORDER_MAP;
/// The terms of a message set, in the order the cartridge indexes them, by
/// the database's name without the set's number: `shop_greeting1` is the
/// first of set 0. The first two, the greetings, go on the main screen's
/// two-line message; the rest, on a one-line one.
pub const TI_TERMS: [&str; 11] = [
    "shop_greeting",
    "shop_regreeting",
    "shop_buy",
    "shop_sell",
    "shop_leave",
    "shop_buy_select",
    "shop_buy_number",
    "shop_purchased",
    "shop_sell_select",
    "shop_sell_number",
    "shop_sold",
];
/// How many message sets `OpenShop` can ask for.
pub const TI_TERM_SETS: usize = 3;
pub const TI_TERM_OWNED: &str = "possessed_items";
pub const TI_TERM_CARRIED: &str = "equipped_items";

/// The layout's cursor positions, in the order the cartridge counts them:
/// `(x, width, row)`, with `row` the first of the two cell rows it covers.
pub fn shop_bars(layer: usize) -> Vec<(usize, usize, usize)> {
    if layer == TI_LAYER_MAIN {
        return (0..TI_COMMAND_POSITIONS)
            .map(|n| (TI_BAR_COMMAND.0, TI_BAR_COMMAND.1, TI_MAIN_MSG_ROW + 2 + 2 * n))
            .collect();
    }
    let rows = if layer == TI_LAYER_BUY { TI_LIST_ROWS_BUY } else { TI_LIST_ROWS_SALE };
    let mut bars: Vec<_> = (0..rows)
        .map(|f| (TI_BAR_LIST.0, TI_BAR_LIST.1, TI_LIST_ROW0 + 2 * f))
        .collect();
    if layer == TI_LAYER_BUY {
        bars.push((TI_BAR_COUNT.0, TI_BAR_COUNT.1, TI_COUNT_ROW));
    }
    bars
}

// --- End Game ----------------------------------------------------------------
//
// `Scene_End`: two windows over black, the question and "Yes" / "No". In
// RM2k, at 320x240, the question is at y = 72 and the commands 48 further
// down, centered in x; here they are centered on 256 and moved up 8, half
// of the 16 missing rows.
pub const END_Y_QUESTION: usize = 72;
pub const END_Y_COMMANDS: usize = 72 + 48;
pub const END_Y_SHIFT: usize = (240 - HEIGHT) / 2;
/// `Window`'s borders.
pub const BORDER: usize = 8;
pub const END_YES: usize = 0;
pub const END_NO: usize = 1;
/// Which command the cursor marks on entering. The 2015 RPG_RT enters on
/// "Yes", measured under Wine; easyrpg-player enters on "No"
/// (`SetIndex(1)`). The original wins.
pub const END_DEFAULT_CHOICE: usize = END_YES;
pub const END_COLORS_MAX: usize = 16;
/// How many frames the fade to black of "Yes" lasts, and how long the
/// song's: the screen's measured on the 2015 RPG_RT —about 330 ms—, and the
/// song's is `Scene_End`'s `BgmFade(400)`.
pub const END_FADE_FRAMES: usize = 20;
pub const END_SONG_FADE_MS: usize = 400;

/// The INIDISP brightness on each frame of the fade to black: a straight
/// line from 15 to 0 in `END_FADE_FRAMES` steps, the last one black.
pub fn end_ramp() -> Vec<u8> {
    let last = END_FADE_FRAMES - 1;
    (0..END_FADE_FRAMES)
        .map(|n| (15 * (last - n) / last) as u8)
        .collect()
}

// --- the title's menu --------------------------------------------------------
//
// The two options go on **BG2, at four bits per pixel**, and not on BG1 with
// the picture: there the text would have to be mixed with the picture, a new
// tile for every cell it covers, and could no longer move. The cursor **is
// not drawn separately**: one tilemap per selected option.
//
// Measured against A Blurred Line: an assumption of the engine, not a fact of
// the game.
/// Where the first option starts, in pixels, and how far apart the next is.
pub const TITLE_MENU_Y: usize = 152;
pub const TITLE_MENU_STEP: usize = 24;
pub const TITLE_MENU_X: usize = 72;
pub const TITLE_CURSOR: &str = "> ";
pub const TITLE_NO_CURSOR: &str = "  ";

// --- the message window ------------------------------------------------------
//
// In RM2k the screen is 320x240 and the window takes 320x80 at the bottom;
// here the screen is 256x224, so the window is 256x80.
pub const WINDOW_WIDTH: usize = 256;
pub const WINDOW_HEIGHT: usize = 80;
/// Its size in cells: fixed, stuck to the bottom of the screen.
pub const WINDOW_COLS_INC: usize = WINDOW_WIDTH / CELL;
pub const WINDOW_ROWS_INC: usize = WINDOW_HEIGHT / CELL;
/// The window's bank of 256 tiles is split in two: the empty window,
/// deduplicated, and **the text area, 30 columns by 8 rows of cells, not
/// deduplicated**: each cell has its fixed tile, because the cartridge
/// rewrites them and cannot go around looking for repeats. That is where
/// the width of a line comes from: [`MESSAGE_WIDTH`].
pub const WINDOW_TEXT_ROW: usize = 1;
pub const WINDOW_TEXT_ROWS: usize = 8;
pub const WINDOW_TEXT_COL: usize = 1;
pub const WINDOW_TEXT_COLS: usize = 30;
/// The pixels a line of the window may take: the text area's, from the
/// border. A letter that would paint past it is not drawn —see
/// `font_reach`—. With RM2k's six-pixel font it was 39 characters; RM2k's
/// own window takes about 50 of its letters, and the variable-width font
/// about 49.
pub const MESSAGE_WIDTH: usize = WINDOW_TEXT_COLS * CELL;
/// The glyph, which is what the cartridge composes. `FONT_WIDTH` is RM2k's
/// fixed advance, which the menu's experience line still steps by.
pub const FONT_WIDTH: usize = font::WIDTH;
pub const FONT_HEIGHT: usize = font::HEIGHT;
/// How many glyphs the cartridge's font tables carry —the sheet's and the
/// cursor's blank— and in how many phases each is precomposed: one per
/// column of a cell a letter can start at.
pub const FONT_GLYPHS: usize = font::CONSOLE_GLYPHS;
pub const FONT_PHASES: usize = 8;
/// The precomposed glyphs: per glyph and phase, the cell rows it touches
/// —its twelve, and one more of shadow— and per row the two cells it can
/// step on, three words each.
pub const FONT_PRE_ROWS: usize = FONT_HEIGHT + 1;
pub const FONT_PRE_CHAR: usize = FONT_PRE_ROWS * 2 * 6;
/// A line of the window, in pixels: RM2k's, which a glyph of twelve and
/// its shadow fit in.
pub const WINDOW_LINE: usize = 16;
/// A `ShowChoice`'s options go `CHOICE_INDENT` pixels further in than the
/// text —`Window_Message::InsertNewLine` adds 12 on a choice's lines—, and
/// the System's cursor goes under the highlighted one, a line tall,
/// `CHOICE_BAR_X` pixels in from the text area and `CHOICE_BAR_TRIM`
/// narrower than it: `Window_Message::UpdateCursorRect`.
pub const CHOICE_INDENT: usize = 12;
pub const CHOICE_BAR_X: usize = 2;
pub const CHOICE_BAR_TRIM: usize = 4;
/// The arrow of a message waiting for a key, in cells: on the bottom edge
/// and centred, as easyrpg's `Window::Draw` puts it —`x + width / 2 - 8`,
/// `y + height - 8`—. On a window 256 wide that falls on a cell's edge,
/// which is what lets the cartridge show it by changing two cells of the
/// window's tilemap.
pub const WINDOW_ARROW_COL: usize = (WINDOW_WIDTH / 2 - ARROW_WIDTH / 2) / CELL;
pub const WINDOW_ARROW_ROW: usize = WINDOW_ROWS_INC - 1;
/// The arrow's size, in pixels and in cells.
pub const ARROW_WIDTH: usize = rm2k_rules::system::ARROW_WIDTH as usize;
pub const ARROW_HEIGHT: usize = rm2k_rules::system::ARROW_HEIGHT as usize;
pub const WINDOW_ARROW_CELLS: usize = ARROW_WIDTH / CELL;
const _: () = assert!(
    (WINDOW_WIDTH / 2 - ARROW_WIDTH / 2).is_multiple_of(CELL) && ARROW_WIDTH.is_multiple_of(CELL) && ARROW_HEIGHT == CELL,
    "the window's arrow has to cover whole cells of its bottom row"
);

fn rects(rects: &[Rect]) -> Value {
    Value::from(
        rects
            .iter()
            .map(|r| json!([r.0, r.1, r.2, r.3]))
            .collect::<Vec<_>>(),
    )
}

/// The geometry the cartridge's emission writes, by name: numbers, lists
/// of numbers, and texts.
pub fn publish() -> Value {
    let mut m = Map::new();
    macro_rules! put {
        ($($name:ident),* $(,)?) => {
            $( m.insert(stringify!($name).to_string(), json!($name)); )*
        };
    }
    put!(
        SLOT_Y, SLOT_STEP, SLOT_ROWS, SLOT_X, LINE, HEADER_Y, HEADER_ROWS, EMPTY, FACE,
        FACE_CELLS, FACE_COL, FACE_STEP, FACES_MAX, NAME_COL, NAME_COLS, NAME_ROW, LEVEL_ROW,
        LEVEL_DIGITS, LEVEL_COL, FACE_PALETTES_MAX, SLOT_TILES_MAX, GLYPH_COL, GLYPH_ROW,
        GLYPH_DX, GLYPH_DY, MENU_OPTIONS, MENU_OPT_Y, MENU_OPT_STEP, MENU_OPT_COL,
        MENU_OPT_COLS, MENU_CURSOR_COL, MENU_ITEMS, MENU_EQUIPMENT, MENU_SAVE, MENU_END,
        MENU_DONE, MENU_GOLD_Y, MENU_GOLD_COL, MENU_GOLD_DIGITS, MENU_CURRENCY_COL,
        MENU_CURRENCY_COLS, MENU_ACTOR_COL, MENU_ACTOR_COLS, MENU_ACTOR_ROWS, MENU_TEXT_X,
        MENU_STATUS_DX, MENU_PARTY_ROWS, MENU_HP_DIGITS, MENU_HP_COL, MENU_HP_ROW,
        MENU_MAX_X, MENU_NAME_COL, MENU_NAME_COLS, MENU_NAME_ROW, MENU_LEVEL_COL,
        MENU_LEVEL_ROW, MENU_MAX_COL, MENU_MAX_DIGITS, MENU_EXP_X, MENU_EXP_Y,
        MENU_EXP_NUM_DX, MENU_EXP_DIGITS, MENU_EXP_LETTERS, MENU_EXP_TERM_CELLS,
        ITEM_DESC_Y, ITEM_DESC_COL, ITEM_DESC_WIDTH, DESC_WIDTH_PX, SCR_TEXT_X, SCR_TEXT_Y,
        ITEM_DESC_LINES, ITEM_LIST_Y, ITEM_ROWS,
        ITEM_CURSOR_COL, ITEM_NAME_COL, ITEM_NAME_WIDTH, ITEM_COLON_COL, ITEM_DIGITS_COL,
        ITEM_FIRST_CHAR, ITEM_CHARS, ITEM_WHITE, ITEM_GRAY, ITEM_UP, ITEM_RED,
        ITEM_UP_CHARS, ITEMS_TILES_MAX, ITEM_HELP_HEIGHT, ITEM_BORDER_CGRAM,
        ITEM_BORDER_MAP, ITEM_BAR_X, ITEM_BAR_WIDTH, MENU_CGRAM, TARGET_LEFT,
        TARGET_NAME_HEIGHT, TARGET_COUNT_HEIGHT, TARGET_NAME_COL, TARGET_NAME_ROW,
        TARGET_NAME_WIDTH, TARGET_COUNT_ROW, TARGET_COUNT_COL, TARGET_CGRAM,
        TARGET_COLORS_MAX, TARGET_VRAM, TARGET_MAP, EQ_WEAPON, EQ_SHIELD, EQUIPMENT_SLOTS,
        EQ_STATUS_Y, EQ_BOTTOM_Y, EQ_ACTOR_ROW, EQ_ACTOR_COL, EQ_PARAMS, EQ_PARAM_VALUE,
        EQ_PARAM_ARROW, EQ_SLOT_ROW0, EQ_TEXT_COL, EQ_SLOT_TERM_COL, EQ_SLOT_TERM_WIDTH,
        EQ_SLOT_NAME_COL, EQ_SLOT_NAME_WIDTH, EQ_LIST_ROW0, EQ_LIST_ROWS, EQ_LIST_NAME_COL,
        TI_MAIN, TI_BUY, TI_COUNT_BUY, TI_BOUGHT, TI_SELL, TI_COUNT_SALE, TI_SOLD,
        TI_SECOND, TI_LAYER_MAIN, TI_LAYER_BUY, TI_LAYER_SALE, TI_LAYER_OF_MODE,
        TI_MIDDLE_Y, TI_MAIN_MSG_Y, TI_MAIN_MSG_ROW, TI_COMMAND_COL, TI_COMMAND_POSITIONS,
        TI_STATUS_Y, TI_MSG_Y, TI_GOLD_X, TI_MSG_ROW, TI_OWNED_ROW, TI_CARRIED_ROW,
        TI_STATUS_COL, TI_STATUS_NUM, TI_GOLD_ROW, TI_GOLD_COL, TI_LIST_ROW0, TI_LIST_COL,
        TI_LIST_ROWS_BUY, TI_LIST_ROWS_SALE, TI_PRICE_COL, TI_COUNT_ROW, TI_COUNT_X_COL,
        TI_COUNT_COL, TI_TOTAL_ROW, TI_VRAM, TI_MAP, TI_TERM_OWNED, TI_TERM_CARRIED, TI_TERM_SETS,
        BORDER, END_YES, END_NO, END_DEFAULT_CHOICE, END_FADE_FRAMES, END_SONG_FADE_MS,
        WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_COLS_INC, WINDOW_ROWS_INC, WINDOW_TEXT_ROW,
        WINDOW_TEXT_ROWS, WINDOW_TEXT_COL, WINDOW_TEXT_COLS, FONT_WIDTH, FONT_HEIGHT,
        FONT_PRE_ROWS, FONT_PRE_CHAR, MESSAGE_WIDTH, FONT_GLYPHS, FONT_PHASES, WINDOW_LINE,
        CHOICE_INDENT, WINDOW_ARROW_COL, WINDOW_ARROW_ROW, WINDOW_ARROW_CELLS,
    );
    m.insert("TEXT_POOL_PAIRS".into(), json!(crate::checks::TEXT_POOL_PAIRS));
    m.insert("ITEM_WINDOWS".into(), rects(&ITEM_WINDOWS));
    m.insert("TARGET_WINDOWS".into(), rects(&TARGET_WINDOWS));
    m.insert("EQ_WINDOWS".into(), rects(&EQ_WINDOWS));
    m.insert(
        "TI_WINDOWS".into(),
        Value::from(
            [TI_LAYER_MAIN, TI_LAYER_BUY, TI_LAYER_SALE]
                .iter()
                .map(|&l| rects(&ti_windows(l)))
                .collect::<Vec<_>>(),
        ),
    );
    m.insert("TI_TERMS".into(), json!(TI_TERMS));
    m.insert("END_RAMP".into(), json!(end_ramp()));
    Value::Object(m)
}
