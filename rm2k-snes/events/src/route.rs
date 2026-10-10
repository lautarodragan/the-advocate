//! Move routes: the forced one a `MoveEvent` carries inside its integers,
//! and the one a page walks on its own.

use crate::codes::*;
use crate::fail::{Step, Stop};
use crate::game::Page;
use serde_json::{json, Value};

/// The frequency a route is walked at. It governs two things: how long it
/// waits between one command and the next —`1 << (9 - frequency)` frames,
/// and zero with 8— and how long a `wait` lasts. Only 8 is accepted, which
/// is the one 3463 of the game's 3509 routes use and **all** of those of the
/// pages that compile; with any other the wait between
/// commands has to be modeled, and since 2026-09-04 it is: it is RM2k's stop
/// counter. After each command the character stays still `max_stop_count`
/// frames —`SetMaxStopCountForStep` after a step, `ForTurn` after a turn,
/// `ForWait` on a `wait`— and with 8 the first two give zero, which is why
/// the model of "turning is free and steps go back to back" was exact
/// without knowing it. The game uses 2, 3, 4, 7 and 8; 1 would give 256
/// frames after each step, which do not fit in the ROM's wait byte, and
/// nobody uses it: it is rejected.
pub const FREQUENCY: i32 = 8;
pub const FREQUENCY_MIN: i32 = 2;

/// An operand a route command drags along: a number or a text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Extra {
    Int(i64),
    Text(String),
}

impl Extra {
    pub fn int(&self) -> i64 {
        match self {
            Extra::Int(v) => *v,
            Extra::Text(_) => 0,
        }
    }

    pub fn text(&self) -> &str {
        match self {
            Extra::Text(t) => t,
            Extra::Int(_) => "",
        }
    }
}

/// The commands of a forced route, with whatever each one drags along.
///
/// It is needed because **the route is not a list of codes**: three
/// commands carry operands inside the same stream of integers, and two of
/// them a text —the CharSet's name, the sound's— with one integer per
/// letter. Walking it flat worked while the first unknown command cut
/// everything; as soon as one of those is accepted, the letters of the text
/// would be read as commands.
///
/// The integers come in RM2k's format: seven bits per integer and bit 7
/// says another follows. It is `Game_Interpreter_Shared::DecodeMove` and
/// `DecodeInt`.
///
/// Running out of data in the middle of an operand is a broken route and
/// does not compile; running out of data between one command and the next
/// is the normal end. The difference matters: mixing them up left out 258
/// pages that are perfectly fine.
pub fn decode(params: &[i32]) -> Step<Vec<(i32, Vec<Extra>)>> {
    let n = params.len();
    let mut i = 0;
    let integer = |i: &mut usize| -> Step<i64> {
        let mut value: i64 = 0;
        loop {
            if *i >= n {
                return Err(Stop::Cannot);
            }
            let x = params[*i] as i64;
            *i += 1;
            value = value.wrapping_shl(7) | (x & 0x7F);
            if x & 0x80 == 0 {
                return Ok(value);
            }
        }
    };
    let text = |i: &mut usize| -> Step<String> {
        let length = integer(i)?;
        if length < 0 || *i as i64 + length > n as i64 {
            return Err(Stop::Cannot);
        }
        let end = *i + length as usize;
        // One letter per integer, its low byte: Latin-1, as the format
        // stores it.
        let letters = params[*i..end]
            .iter()
            .map(|&c| ((c & 0xFF) as u8) as char)
            .collect();
        *i = end;
        Ok(letters)
    };
    let mut commands = Vec::new();
    while i < n {
        let code = params[i];
        i += 1;
        let extras = match code {
            ROUTE_SWITCH_ON | ROUTE_SWITCH_OFF => vec![Extra::Int(integer(&mut i)?)],
            ROUTE_CHANGE_GRAPHIC => {
                let t = text(&mut i)?;
                vec![Extra::Text(t), Extra::Int(integer(&mut i)?)]
            }
            ROUTE_SOUND => {
                let t = text(&mut i)?;
                vec![
                    Extra::Text(t),
                    Extra::Int(integer(&mut i)?),
                    Extra::Int(integer(&mut i)?),
                    Extra::Int(integer(&mut i)?),
                ]
            }
            _ => vec![],
        };
        commands.push((code, extras));
    }
    Ok(commands)
}

/// The lowest frequency a route with commands 30 and 31 goes through.
///
/// It is what decides whether the route can be compiled: with frequency 1
/// the wait after a step is 256 frames and the `route_after_step` byte
/// cannot hold it, so a route that goes down that far is rejected whole.
///
/// `commands` are bare codes, without operands: the two callers pass what
/// [`decode`] returned, which already separated them. It is not the same as
/// a compiled route, where 34 drags a byte along that has to be skipped.
///
/// With `repeats` the commands are walked nine times and not once. It is
/// not just in case: the frequency is clamped at 8 and at 1, so a repeating
/// route that goes down more than it goes up ends at 1 no matter what, and
/// nine passes are enough for it to get there from any starting point.
pub fn min_frequency(frequency: i32, commands: &[i32], repeats: bool) -> i32 {
    let mut current = frequency;
    let mut lowest = frequency;
    for _ in 0..if repeats { 9 } else { 1 } {
        for &command in commands {
            if command == ROUTE_FREQ_UP {
                current = FREQUENCY.min(current + 1);
            } else if command == ROUTE_FREQ_DOWN {
                current = 1.max(current - 1);
            }
            lowest = lowest.min(current);
        }
    }
    lowest
}

/// The four turns, the eight moves and the rest the ROM knows how to walk,
/// in a single place.
///
/// The four turns, the four moves and the wait were the first. The moves
/// came in last because in RM2k the character walks cell by cell over
/// several frames, and that has to be compared *while* it walks: comparing
/// only where it ends lets the whole animation cycle slip through. The
/// `move_*` codes **are** the direction, and 4 to 7 are the diagonals: see
/// [`diagonal`].
///
/// * Facing the hero, 21: `GetDirectionToCharacter`. The axis with more
///   distance wins, and on a tie the vertical one; on the same cell it looks
///   down. Only on events: no page uses the hero facing itself.
/// * Moving toward the hero, 9: `move_towards_hero`. It is not a new command
///   but two that already exist stuck together —in `UpdateMoveRoute` it is
///   `TurnTowardCharacter(hero)` and then `Move(GetDirection())`—, that is
///   21 and a `move_*` on the same frame, with the same step cost as any
///   other.
///
///   It is the command that unlocks the most of the ones that were missing,
///   by far: measured over the whole game, **+31 pages**, against +1 for the
///   other nine together —random, fleeing the hero, forward and the five
///   in-place turns—. It is used 267 times in forced routes on four maps, 9,
///   11, 38 and 166; map 9 is the Lazer Teeth battle.
///
///   Only on events, like 21: no route in the game asks for the hero moving
///   toward itself —measured, zero— and it would mean nothing.
/// * The random step, 8, and moving away from the hero, 10, and facing away
///   from him, 22: **events only**, like 9 and 21. The random one turns to a
///   direction drawn from the map's generator and moves; away is toward
///   turned half a circle. They were not worth it in ABL —+1 page— and are
///   in since 2026-10-06, when other games' pages turned out to wait on
///   them. A page's own route still refuses them, as it does 9 and 21.
/// * Turning without moving —`turn_90_degree_right` and its siblings— is
///   still out, and not because of cost: RM2k turns relative to the
///   direction the character already had, and for an event that has not
///   turned yet that is its page's, which the route does not read.
/// * The jump, 24 and 25: what lies between the two is added up as an offset
///   and the character does it in one go, in an arc.
/// * Walking through walls, 36 and 37, and stopping or resuming the walking
///   animation, 38 and 39.
/// * Locking and unlocking the facing —`lock_facing`, 26 and 27—, and
///   raising and lowering the speed by one, between 1 and 6, 28 and 29. They
///   came in on 2026-09-05 with the pages' own routes: map 2's droids use
///   them. On the hero see `compile_route`.
/// * Raising and lowering the frequency in the middle of a route, 30 and 31:
///   `increase/decrease_movement_frequence`, which RM2k clamps at 8 and 1. **A
///   single route in the whole game** uses them —the one that shakes Manta
///   in the Emitter Room scene, which goes down twice from 8 to 6— and
///   without them that page does not compile.
/// * Changing the graphic in the middle of a route, 34. It is the **only
///   command with an operand**: the bytecode carries after it the CharSet's
///   index in `Graphics`.
pub fn known(command: i32) -> bool {
    (0..=7).contains(&command)
        || (12..=15).contains(&command)
        || matches!(
            command,
            ROUTE_RANDOM
                | ROUTE_AWAY_HERO
                | ROUTE_FACE_AWAY
                | ROUTE_WAIT
                | ROUTE_JUMP_START
                | ROUTE_JUMP_END
                | ROUTE_THROUGH_ON
                | ROUTE_THROUGH_OFF
                | ROUTE_ANIM_STOP
                | ROUTE_ANIM_RESUME
                | ROUTE_FACE_HERO
                | ROUTE_TOWARD_HERO
                | ROUTE_LOCK_DIR
                | ROUTE_UNLOCK_DIR
                | ROUTE_SPEED_UP
                | ROUTE_SPEED_DOWN
                | ROUTE_FREQ_UP
                | ROUTE_FREQ_DOWN
                | ROUTE_CHANGE_GRAPHIC
        )
}

/// The four diagonals, `move_upright` to `move_upleft`: only events walk
/// them. Each has its two components, vertical first and then horizontal
/// —4 up and right, 5 down and right, 6 down and left, 7 up and left—.
///
/// **Only events** walk them. Of the game's 26 routes that use them none is
/// the hero's, so the ROM does not have them on it: walking diagonally with
/// the pad does not exist and giving the hero a diagonal step would require
/// duplicating `try_up` and its three siblings for nothing. The compiler
/// rejects the page that tries it —see `compile_route`—, which is what keeps
/// the ROM from silently walking something else.
pub fn diagonal(command: i32) -> bool {
    (4..=7).contains(&command)
}

/// A page's own route —`move_type` 6, the route it walks on its own—, or
/// None if it has none or it cannot be done.
///
/// The same commands as in a MoveEvent go, with the transparency dropped
/// and also the sound, which in a MoveEvent does play: here there is nowhere
/// to put its operand —see `ROUTE_SOUND` in `compile_route`—. The diagonals
/// go in: an own route is always an event's, which is what the ROM walks
/// them on. What is left out: moving toward or away from the hero, changing
/// the graphic —none uses it— and the switches; and turning in place
/// (`AnimType_spin`), which neither of the game's two pages that use it is
/// in the first maps. The other movement types —random, vertical,
/// horizontal, toward the hero— neither: they are another machine.
///
/// **Turning in place goes in since 2026-10-04**, with `"spin"` on: the
/// console turns it a quarter every few frames, by its speed, its steps do
/// not turn it —`UpdateAnimation` and `UpdateFacing`— and it always shows
/// the column of its page, `"pattern"`. It was left out while the game's
/// pages that use it were not in the cartridge; now two of them dance in
/// ABL's farm (127), walking a square, and they stood still. The page that
/// spins **without** a route —`MoveType_stationary`— gets one with no
/// commands that repeats: the console only animates an event with a route
/// slot, and an empty one that repeats does nothing else. Those are the
/// other two of the game's four, a robot on maps 64 and 227.
///
/// **Moving toward the hero is left out here too**, even though since
/// 2026-09-12 the ROM walks it in a forced route: they are two pages of map
/// 105 —measured, the only ones of the game's 37 own routes that use it—
/// and no test gets there, so accepting it would be opening the path with
/// nothing exercising it. 21 is out for the same reason since before: zero
/// own routes use it.
pub fn own(page: &Page) -> Option<Value> {
    let spin = page.animation_type == ANIM_SPIN;
    let still_spinning = spin && page.move_type == MOVE_STATIONARY;
    if !still_spinning && (page.move_type != MOVE_CUSTOM || page.route.is_empty()) {
        return None;
    }
    if !(FREQUENCY_MIN..=FREQUENCY).contains(&page.move_frequency) {
        return None;
    }
    if !(1..=6).contains(&page.move_speed) || !(0..=2).contains(&page.character_pattern) {
        return None;
    }
    let route: &[i32] = if still_spinning { &[] } else { &page.route };
    let mut commands = Vec::new();
    for &command in route {
        if command == ROUTE_SOUND || ROUTE_TRANSPARENCY.contains(&command) {
            continue;
        }
        if !known(command)
            || [ROUTE_FACE_HERO, ROUTE_TOWARD_HERO, ROUTE_RANDOM, ROUTE_AWAY_HERO, ROUTE_FACE_AWAY]
                .contains(&command)
        {
            return None;
        }
        if command == ROUTE_CHANGE_GRAPHIC {
            // Here there is nowhere to put the operand —a page's route is a
            // bare list of codes, not a MoveEvent with its text— and it is
            // not needed: **none of the game's 3509 own routes changes
            // graphic**, measured. The day one shows up, this rejects it
            // instead of compiling a 34 with nothing to change to.
            return None;
        }
        commands.push(command);
    }
    if min_frequency(page.move_frequency, &commands, page.route_repeat) < FREQUENCY_MIN {
        // Commands 30 and 31 would take it down to 1.
        return None;
    }
    // Empty is fine for one that spins: the route is only its slot.
    if (commands.is_empty() && !spin) || commands.len() > 255 {
        return None;
    }
    let mut out = json!({
        "commands": commands,
        "frequency": page.move_frequency,
        "speed": page.move_speed,
        "repeats": page.route_repeat || still_spinning,
        "skippable": page.route_skippable,
        "fixed_direction": matches!(
            page.animation_type,
            ANIM_FIXED_NOT_CONTINUOUS | ANIM_FIXED_CONTINUOUS | ANIM_FIXED_GRAPHIC
        ),
        "animation_continues": matches!(page.animation_type, ANIM_CONTINUOUS | ANIM_FIXED_CONTINUOUS),
    });
    // Only on the one that spins: the others' answer stays the one
    // `tests/python.rs` holds the hashes of, byte for byte.
    if spin {
        out["spin"] = json!(true);
        out["pattern"] = json!(page.character_pattern);
    }
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_route_carries_its_texts_inside_the_integers() {
        // 34 "Ab" 3, then a move up, and 35 "x" 100 128+1 0 with a
        // two-integer tempo.
        let params = [34, 2, 65, 98, 3, 0, 35, 1, 120, 100, 129, 0, 50];
        let out = decode(&params).ok().unwrap();
        assert_eq!(out[0], (34, vec![Extra::Text("Ab".into()), Extra::Int(3)]));
        assert_eq!(out[1], (0, vec![]));
        assert_eq!(
            out[2],
            (
                35,
                vec![
                    Extra::Text("x".into()),
                    Extra::Int(100),
                    Extra::Int(128),
                    Extra::Int(50)
                ]
            )
        );
        assert!(decode(&[34, 5, 65]).is_err());
    }

    fn spinning(move_type: i32, route: Vec<i32>) -> Page {
        Page {
            trigger: 0,
            layer: 1,
            move_type,
            move_frequency: 3,
            move_speed: 3,
            animation_type: ANIM_SPIN,
            character_name: "Dancer".into(),
            character_index: 1,
            character_pattern: 2,
            commands: Vec::new(),
            route,
            route_repeat: true,
            route_skippable: false,
            condition: Default::default(),
        }
    }

    #[test]
    fn a_page_that_spins_walks_its_route_spinning() {
        // ABL's dancers, on map 127: a square, turning in place.
        let r = own(&spinning(MOVE_CUSTOM, vec![3, 2, 1, 0])).unwrap();
        assert_eq!(r["commands"], json!([3, 2, 1, 0]));
        assert_eq!(r["spin"], json!(true));
        assert_eq!(r["pattern"], json!(2));
        assert_eq!(r["fixed_direction"], json!(false));
    }

    #[test]
    fn a_still_page_that_spins_gets_an_empty_route_that_repeats() {
        // The console only animates an event with a route slot.
        let r = own(&spinning(MOVE_STATIONARY, Vec::new())).unwrap();
        assert_eq!(r["commands"], json!([]));
        assert_eq!(r["repeats"], json!(true));
        assert_eq!(r["spin"], json!(true));
        // The other movement types are another machine, spinning or not.
        assert!(own(&spinning(1, Vec::new())).is_none());
    }

    #[test]
    fn a_repeating_route_goes_all_the_way_down() {
        assert_eq!(min_frequency(8, &[31, 31], false), 6);
        assert_eq!(min_frequency(8, &[31, 31, 30], true), 1);
    }
}
