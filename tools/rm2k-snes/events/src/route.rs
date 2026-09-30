//! Move routes: the forced one a `MoveEvent` carries inside its integers,
//! and the one a page walks on its own.

use crate::codes::*;
use crate::fail::{Step, Stop};
use crate::game::Page;
use serde_json::{json, Value};

/// The frequency a route is walked at: only 8 waits nothing between one
/// command and the next, and 1 would wait 256 frames after each step, which
/// do not fit in the ROM's wait byte. The game uses 2, 3, 4, 7 and 8.
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
/// The route is not a list of codes: three commands carry operands inside
/// the same stream, two of them a text with one integer per letter. The
/// integers are RM2k's, seven bits each with bit 7 saying another follows
/// —`DecodeMove` and `DecodeInt`—. Running out in the middle of an operand
/// is a broken route and does not compile; running out between two
/// commands is the normal end.
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

/// The lowest frequency a route with commands 30 and 31 goes through, which
/// decides whether it can be compiled. With `repeats` the commands are
/// walked nine times: the frequency is clamped at 8 and at 1, so nine
/// passes take a repeating route that goes down more than up all the way
/// to 1.
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

/// The four turns, the eight moves and the rest the ROM knows how to walk.
pub fn known(command: i32) -> bool {
    (0..=7).contains(&command)
        || (12..=15).contains(&command)
        || matches!(
            command,
            ROUTE_WAIT
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
/// them.
pub fn diagonal(command: i32) -> bool {
    (4..=7).contains(&command)
}

/// A page's own route —`move_type` 6—, or None if it has none or it cannot
/// be done.
///
/// The same commands as a `MoveEvent`'s go, with the transparency and the
/// sound dropped —a page's route is a bare list of codes, with no room for
/// the sound's operand—. Moving toward the hero, facing it and changing the
/// graphic are left out: nothing in the game walks them on a page's own
/// route, and a path nothing exercises is not opened. Turning in place
/// (`spin`) and the other move types are another machine.
pub fn own(page: &Page) -> Option<Value> {
    if page.move_type != MOVE_CUSTOM || page.route.is_empty() {
        return None;
    }
    if !(FREQUENCY_MIN..=FREQUENCY).contains(&page.move_frequency) {
        return None;
    }
    if !(1..=6).contains(&page.move_speed) || page.animation_type == ANIM_SPIN {
        return None;
    }
    let mut commands = Vec::new();
    for &command in &page.route {
        if command == ROUTE_SOUND || ROUTE_TRANSPARENCY.contains(&command) {
            continue;
        }
        if !known(command) || command == ROUTE_FACE_HERO || command == ROUTE_TOWARD_HERO {
            return None;
        }
        if command == ROUTE_CHANGE_GRAPHIC {
            return None;
        }
        commands.push(command);
    }
    if min_frequency(page.move_frequency, &commands, page.route_repeat) < FREQUENCY_MIN {
        return None;
    }
    if commands.is_empty() || commands.len() > 255 {
        return None;
    }
    Some(json!({
        "commands": commands,
        "frequency": page.move_frequency,
        "speed": page.move_speed,
        "repeats": page.route_repeat,
        "skippable": page.route_skippable,
        "fixed_direction": matches!(
            page.animation_type,
            ANIM_FIXED_NOT_CONTINUOUS | ANIM_FIXED_CONTINUOUS | ANIM_FIXED_GRAPHIC
        ),
        "animation_continues": matches!(page.animation_type, ANIM_CONTINUOUS | ANIM_FIXED_CONTINUOUS),
    }))
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

    #[test]
    fn a_repeating_route_goes_all_the_way_down() {
        assert_eq!(min_frequency(8, &[31, 31], false), 6);
        assert_eq!(min_frequency(8, &[31, 31, 30], true), 1);
    }
}
