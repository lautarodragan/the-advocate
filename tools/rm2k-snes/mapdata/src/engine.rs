//! The numbers of the engine the `.inc` hands the runtime: RM2k's own,
//! taken from easyrpg-player where it says, and the console's caps.
//!
//! They lived in the converter's `events.py` until 2026-10-01, where the
//! long comment of each one still is, next to the compiler's use of it;
//! the runtime only names them. The ones marked as measured against A
//! Blurred Line are assumptions of the engine, not facts of a game: see
//! `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

/// A text box's header: the lines in the low three bits, the auto-close of
/// `\^` in bit 3, the `\|` pauses in the high nibble.
pub const HEADER_LINES: u32 = 0x07;
pub const HEADER_AUTO_CLOSE: u32 = 0x08;
/// What a `\|` costs: `SetWaitForNonPrintable(61)` —"Despite documentation
/// saying 1 second, RPG_RT waits for 61 frames"—.
pub const PAUSE_FRAMES: u32 = 61;
/// The top bit of the flags byte of the opcodes that write a variable: the
/// write asks for the page refresh; the slot is the low eight.
pub const VAR_REFRESH: u32 = 0x80;
pub const VAR_SLOT_MAX: u32 = 0xFF;
/// `OP_ANIMATION`'s entries: eight bytes, a sound or a screen flash.
pub const ANIM_ENTRY_BYTES: u32 = 8;
pub const ANIM_SOUND: u32 = 0;
pub const ANIM_SCREEN_FLASH: u32 = 1;
/// `KeyInputProc`'s flags, in `OP_KEY`'s second byte.
pub const KEY_WAIT: u32 = 0x01;
pub const KEY_DIRS: u32 = 0x02;
pub const KEY_DECISION: u32 = 0x04;
pub const KEY_CANCEL: u32 = 0x08;
pub const KEY_START: u32 = 0x10;
/// The value RM2k stores for each key; the order they are checked in is
/// from highest to lowest.
pub const KEY_VALUE_DECISION: u32 = 5;
pub const KEY_VALUE_CANCEL: u32 = 6;
/// By the console's direction: up, right, down, left.
pub const KEY_VALUE_DIR: [u32; 4] = [4, 3, 1, 2];
/// The rain: drops per power, how long each one lives, the chance one is
/// born per frame out of 256, and the seed.
pub const WEATHER_RAIN: u32 = 1;
pub const RAIN_DROPS: [u32; 3] = [15, 45, 75];
pub const RAIN_LIFE: u32 = 12;
pub const RAIN_SPAWN: u32 = 26;
pub const RAIN_SEED: u32 = 0x1D2B;
/// One byte per item of the database and RM2k's cap. Measured against A
/// Blurred Line: its database has 450 items, plus 0.
pub const ITEMS_N: usize = 451;
pub const ITEM_MAX: u32 = 99;
/// The `ControlVars` operand classes the console tells apart.
pub const VAR_ADD: u32 = 1;
pub const VAR_VARIABLE: u32 = 1;
pub const VAR_RANDOM: u32 = 3;
pub const VAR_OTHER: u32 = 7;
/// Class 6, a character's coordinate, and class 5, an actor's datum.
pub const VAR_CHARACTER: u32 = 6;
pub const CHARACTER_X: u32 = 1;
pub const CHARACTER_Y: u32 = 2;
pub const VAR_ACTOR: u32 = 5;
/// The top bits of each `OP_CELL_TEST` write: y instead of x, and the
/// refresh.
pub const CELL_Y: u32 = 0x4000;
pub const CELL_REFRESH: u32 = 0x8000;
/// The seeds of the map's randomness and of the encounters', different on
/// purpose: walking does not advance the map's.
pub const RANDOM_SEED: u32 = 0xACE1;
pub const ENC_SEED: u32 = 0x5A17;
/// The timer's fourth operation: the seconds from a variable.
pub const TIMER_SET_VAR: u32 = 3;
/// The `ConditionalBranch` classes, RM2k's numbers.
pub const COND_GOLD: u32 = 3;
pub const COND_ITEM: u32 = 4;
pub const COND_ACTOR: u32 = 5;
pub const COND_ACTOR_SKILL: u32 = 4;
pub const COND_ACTOR_EQUIPMENT: u32 = 5;
/// `MaxGoldValue()`.
pub const GOLD_MAX: u32 = 999_999;
/// The two `PanScreen` operations that compile, and the timer's two.
pub const PAN_SHIFT: u32 = 2;
pub const PAN_RETURN: u32 = 3;
pub const TIMER_SET: u32 = 0;
pub const TIMER_START: u32 = 1;
/// `DEFAULT_FPS`, and the 59 `SetTimer` adds so the first second shows
/// whole.
pub const FRAMES_PER_SECOND: u32 = 60;
pub const TIMER_EXTRA_FRAMES: u32 = 59;
/// `rpg::EventPage::Trigger`.
pub const TRIGGER_ACTION: u32 = 0;
pub const TRIGGER_TOUCH_HERO: u32 = 1;
pub const TRIGGER_AUTOSTART: u32 = 3;
pub const TRIGGER_PARALLEL: u32 = 4;
/// A one-cell step: sixteen pixels at two a frame.
pub const FRAMES_PER_CELL: u32 = 8;
/// A route's highest frequency and the lowest that compiles, and what a
/// `wait` costs at the highest: `20 + (1 << (8 - frequency))`.
pub const ROUTE_FREQUENCY: u32 = 8;
pub const ROUTE_FREQUENCY_MIN: u32 = 2;
pub const ROUTE_WAIT_FRAMES: u32 = 20;
/// What is left of a jump when it starts.
pub const JUMP_STEP: u32 = 256;
/// The teleport's fade: the ticks from the jump to the first live one, as
/// the RPG_RT shows them; the ramp, each way; and the master brightness.
pub const FADE_TOTAL: u32 = 68;
pub const FADE_RAMP: u32 = 24;
pub const BRIGHTNESS_MAX: u32 = 15;
/// The teleport transitions the console does besides the fade.
pub const TRANSITION_MOSAIC: u32 = 1;
pub const TRANSITION_CUT: u32 = 2;
/// `Game_Party::AddActor` does not add a fifth.
pub const PARTY_MAX: u32 = 4;
/// `OP_MESSAGE`'s operand counts the text block in steps of this. Measured
/// against A Blurred Line.
pub const MESSAGES_STEP: usize = 4;
/// How many pages of a troop the battle notes, a far RAM cap.
pub const TROOP_PAGES_MAX: usize = 32;
/// The troop page triggers the console looks at, by their bit in
/// `tpage_flags`; the ones with a header in front of the code; and how long
/// the header is.
pub const TROOP_TRIGGER_SWITCH_A: u32 = 0x01;
pub const TROOP_TRIGGER_SWITCH_B: u32 = 0x02;
pub const TROOP_TRIGGER_VARIABLE: u32 = 0x04;
pub const TROOP_TRIGGER_TURN: u32 = 0x08;
pub const TROOP_TRIGGER_ENEMY: u32 = 0x10;
pub const TROOP_TRIGGER_ACTOR: u32 = 0x20;
pub const TROOP_WITH_HEADER: u32 = TROOP_TRIGGER_TURN | TROOP_TRIGGER_ENEMY | TROOP_TRIGGER_ACTOR;
pub const TROOP_HEADER_BYTES: u32 = 10;
/// A battle animation that is not drawn, and the "screen" scope.
pub const ANIM_NO_DRAWING: u32 = 0xFF;
pub const ANIM_TARGET_SCREEN: u32 = 0xFF;

/// RM2k's tint goes from 0 to 200, 100 neutral.
pub const NEUTRAL_TINT: u32 = 100;
/// Y'CbCr's luminance weights, which add up to 65536: `saturation_tone`.
pub const LUMA_R: u32 = 19595;
pub const LUMA_G: u32 = 38470;
pub const LUMA_B: u32 = 7471;

/// One bit per switch: up to 1024, of which A Blurred Line checks up to 1003.
pub const SWITCH_BYTES: u32 = 128;

/// The timer's eleven glyphs —ten digits and the colon—, eight pixels wide,
/// where `Sprite_Timer` draws the first.
pub const TIMER_GLYPHS: u32 = 11;
pub const TIMER_GLYPH_W: u32 = 8;
pub const TIMER_X: u32 = 4;
pub const TIMER_Y: u32 = 4;

/// The ChipSet animation's cadences: the water's slow frames and its cycle,
/// the animated tiles' frames and steps (`rm2k.py`).
pub const WATER_FRAMES_SLOW: u32 = 24;
pub const WATER_CYCLE: usize = 4;
pub const ANIMATED_FRAMES: u32 = 6;
pub const ANIMATED_STEPS: u32 = 4;

/// How many characters fit on a line of the message window. Measured
/// against A Blurred Line.
pub const COLUMNS: u32 = 39;
/// The screen in cells, and the menu's CGRAM: one palette at 4bpp.
pub const CELL: i64 = 8;
pub const COLS: i64 = 32;
pub const ROWS: i64 = 28;
pub const MENU_CGRAM: usize = 16;
/// An RM2k actor's equipment slots, and how many enemies a battle holds.
pub const EQUIPMENT_SLOTS: usize = 5;
pub const ENEMIES_MAX: usize = 8;
/// The 32x32 object's side in tiles, and the name grid's width.
pub const OBJ_SIDE: u32 = 4;
pub const GRID: u32 = 16;

/// The INIDISP brightness on each frame of the fade's ramp, from black to
/// full: a rounded straight line over the sixteen steps.
pub fn fade_ramp() -> Vec<u32> {
    let last = FADE_RAMP - 1;
    (0..FADE_RAMP)
        .map(|s| (BRIGHTNESS_MAX * s + last / 2) / last)
        .collect()
}

/// How much a song's volume goes down per frame, in 1/65536, to fade out
/// in `milliseconds`: rounded up, so it ends within the frames it asks for.
pub fn fade_step(milliseconds: i64) -> i64 {
    let frames = (milliseconds * i64::from(FRAMES_PER_SECOND) / 1000).max(1);
    ((0x10000 + frames - 1) / frames).min(0xFFFF)
}

/// `GetMaxStopCountForStep`: the frames standing still after a step.
pub fn wait_after_step(frequency: u32) -> u32 {
    if frequency >= 8 {
        0
    } else {
        1 << (9 - frequency)
    }
}

/// `GetMaxStopCountForTurn`: the frames standing still after a turn.
pub fn wait_after_turn(frequency: u32) -> u32 {
    if frequency >= 8 {
        0
    } else {
        1 << (8 - frequency)
    }
}

/// The sine at scale 127 the screen shake reads by index.
pub fn shake_sine() -> Vec<i64> {
    (0..256)
        .map(|t| {
            let v = (f64::from(t) * std::f64::consts::PI / 128.0).sin() * 127.0;
            round_half_even(v)
        })
        .collect()
}

/// Python's `round`: to the nearest, ties to even.
fn round_half_even(v: f64) -> i64 {
    let r = v.round();
    if (v - v.trunc()).abs() == 0.5 && (r as i64) % 2 != 0 {
        (r - v.signum()) as i64
    } else {
        r as i64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_fade_ramp_goes_from_black_to_full() {
        assert_eq!(
            fade_ramp(),
            [0, 1, 1, 2, 3, 3, 4, 5, 5, 6, 7, 7, 8, 8, 9, 10, 10, 11, 12, 12, 13, 14, 14, 15]
        );
    }

    #[test]
    fn the_waits_after_a_step_and_a_turn() {
        let step: Vec<u32> = (2..9).map(wait_after_step).collect();
        let turn: Vec<u32> = (2..9).map(wait_after_turn).collect();
        assert_eq!(step, [128, 64, 32, 16, 8, 4, 0]);
        assert_eq!(turn, [64, 32, 16, 8, 4, 2, 0]);
    }

    #[test]
    fn the_fade_step_ends_within_its_frames() {
        assert_eq!(fade_step(5000), 219);
        assert_eq!(fade_step(0), 0xFFFF);
    }

    #[test]
    fn the_sine_starts_like_the_one_the_converter_built() {
        assert_eq!(
            &shake_sine()[..20],
            [0, 3, 6, 9, 12, 16, 19, 22, 25, 28, 31, 34, 37, 40, 43, 46, 49, 51, 54, 57]
        );
        assert_eq!(shake_sine()[64], 127);
        assert_eq!(shake_sine()[192], -127);
    }
}
