//! Still characters that share a VRAM slot because they are never on
//! screen together.
//!
//! A still pose already shares its slot with every event that shows the
//! same one —see [`crate::sprites::bank::Slot::Still`]—. A crowded map can still ask
//! for more slots than VRAM has, with most of them far from each other: a
//! town of fifteen people facing three or four ways each. This lets two
//! still events showing **different** poses take the same slot when no
//! position of the camera puts both on screen; the console uploads the
//! pose of whichever comes into view, and the one it replaces is out of
//! view by construction.
//!
//! Who can share —an event nobody moves, with a single graphic— is the
//! caller's to decide: this only knows positions and poses.

use crate::sprites::character::{OBJ_H, OBJ_W};
use crate::sprites::npc::Graphic;

/// The screen, in pixels: what the console shows of the map.
pub const SCREEN_W: i32 = 256;
pub const SCREEN_H: i32 = 224;
/// A map cell, in pixels.
pub const CELL: i32 = 16;

/// How close two cells have to be, on each axis, for both objects to be on
/// screen at once for some position of the camera: less than this many
/// cells apart in x **and** in y.
///
/// An object is drawn when its 32x32 box touches the screen, so for a
/// camera at `c` the one at `p` shows when `c - 32 < p < c + 256`: two of
/// them can show together exactly when they are less than 256 + 32 pixels
/// apart. It is the console's own discard —`build_oam` and `place_npc` in
/// the runtime— and not an estimate: there is no margin to add, because
/// the console decides with the same comparison. Positions are whole
/// cells, so it is 18 cells across and 16 down.
pub fn reach() -> (i32, i32) {
    (
        (SCREEN_W + OBJ_W as i32 + CELL - 1) / CELL,
        (SCREEN_H + OBJ_H as i32 + CELL - 1) / CELL,
    )
}

/// How many shared slots the console keeps track of in a map: one byte of
/// RAM each, saying which pose is in it. It is the runtime's `SHARE_MAX`,
/// and the emission checks the two agree.
pub const SHARED_MAX: usize = 15;

/// A still event that can share: its cell and the pose it shows.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Sharer {
    pub event: usize,
    pub x: i32,
    pub y: i32,
    pub pose: Graphic,
}

/// Whether two sharers can be on screen at once.
fn together(a: &Sharer, b: &Sharer, (rx, ry): (i32, i32)) -> bool {
    (a.x - b.x).abs() < rx && (a.y - b.y).abs() < ry
}

/// The slots the sharers go in, each a list of indices into `sharers`.
///
/// Two can be in the same slot if they show the same pose or if they are
/// never on screen together. It is a colouring, done greedily: in the
/// order of their pose and then their cell, each goes into the first slot
/// that takes it. Greedy is not the fewest slots, and does not need to be:
/// what matters is that the order does not depend on how the map listed
/// its events, so the same map always comes out the same.
pub fn share_slots(sharers: &[Sharer]) -> Vec<Vec<usize>> {
    let reach = reach();
    let mut order: Vec<usize> = (0..sharers.len()).collect();
    order.sort_by(|&a, &b| {
        let (a, b) = (&sharers[a], &sharers[b]);
        (&a.pose, a.x, a.y, a.event).cmp(&(&b.pose, b.x, b.y, b.event))
    });
    let mut slots: Vec<Vec<usize>> = Vec::new();
    for i in order {
        let fits = |slot: &Vec<usize>| {
            slot.iter().all(|&j| {
                sharers[j].pose == sharers[i].pose || !together(&sharers[i], &sharers[j], reach)
            })
        };
        match slots.iter_mut().find(|s| fits(s)) {
            Some(slot) => slot.push(i),
            None => slots.push(vec![i]),
        }
    }
    slots
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(event: usize, x: i32, y: i32, pose: i32) -> Sharer {
        Sharer {
            event,
            x,
            y,
            pose: ("People".to_string(), 0, pose),
        }
    }

    #[test]
    fn the_reach_is_the_screen_plus_an_object() {
        assert_eq!(reach(), (18, 16));
    }

    #[test]
    fn two_poses_share_only_when_never_on_screen_together() {
        // 17 cells apart across: a camera shows both. 18: none does.
        let near = [at(0, 0, 0, 1), at(1, 17, 0, 4)];
        assert_eq!(share_slots(&near).len(), 2);
        let far = [at(0, 0, 0, 1), at(1, 18, 0, 4)];
        assert_eq!(share_slots(&far), vec![vec![0, 1]]);
        // Down it is 16: the screen is shorter.
        assert_eq!(share_slots(&[at(0, 0, 0, 1), at(1, 0, 15, 4)]).len(), 2);
        assert_eq!(share_slots(&[at(0, 0, 0, 1), at(1, 0, 16, 4)]).len(), 1);
        // Near on one axis and far on the other is far.
        assert_eq!(share_slots(&[at(0, 0, 0, 1), at(1, 3, 20, 4)]).len(), 1);
    }

    #[test]
    fn the_same_pose_always_shares() {
        let same = [at(0, 0, 0, 1), at(1, 1, 0, 1), at(2, 2, 0, 1)];
        assert_eq!(share_slots(&same), vec![vec![0, 1, 2]]);
        // And a third pose next to both goes apart.
        let three = [at(0, 0, 0, 1), at(1, 1, 0, 1), at(2, 2, 0, 4)];
        assert_eq!(share_slots(&three), vec![vec![0, 1], vec![2]]);
    }

    #[test]
    fn the_answer_does_not_depend_on_the_order_of_the_events() {
        let a = [
            at(0, 0, 0, 1),
            at(1, 30, 0, 4),
            at(2, 5, 5, 7),
            at(3, 40, 40, 1),
        ];
        let mut b = a.to_vec();
        b.reverse();
        let by_event = |sharers: &[Sharer], slots: Vec<Vec<usize>>| -> Vec<Vec<usize>> {
            let mut out: Vec<Vec<usize>> = slots
                .into_iter()
                .map(|s| s.into_iter().map(|i| sharers[i].event).collect())
                .collect();
            for s in &mut out {
                s.sort();
            }
            out.sort();
            out
        };
        assert_eq!(by_event(&a, share_slots(&a)), by_event(&b, share_slots(&b)));
    }
}
