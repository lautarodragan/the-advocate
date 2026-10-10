//! A cache of slots, for a map whose events do not fit in VRAM even with
//! the still ones taking turns.
//!
//! Nobody owns a slot: an event asks for one when it comes into view and
//! leaves it when it goes, and the console uploads its pose into whichever
//! it got. Still events showing the same pose share one, as always; one
//! that walks, or a still one whose pages show more than one graphic, has
//! one of its own while it is in view. What a cache needs from the
//! converter is only how many slots there are and which still poses there
//! can be: who is in view, and which graphic each one shows, the console
//! knows better —an event whose page draws nothing does not ask—.
//!
//! What can be counted here is how many can be on screen at once by where
//! they start, which says whether the cache is likely to be enough. It is
//! an estimate and not a guarantee: the walking ones move, and two events
//! of scenes that never happen together count as if they did.

use crate::sprites::share::reach;
use std::collections::BTreeSet;

/// How many slots the console keeps track of: one byte each for what it
/// holds and one for how long ago it was drawn. It is the runtime's
/// `CACHE_MAX`, and the emission checks the two agree.
pub const CACHE_MAX: usize = 32;

/// The blocks of 32x32 the sprite bank has room for at most: the 512 tiles
/// an object's nine-bit name reaches. The fixed ones —the hero's, the
/// turn's— come out of these.
pub const BLOCKS: usize = 32;

/// The still poses one map can name: the console keeps what a slot holds in
/// a byte, a still pose below 128 and an event's own slot as 128 plus the
/// event.
pub const STILLS_MAX: usize = 128;

/// What an event asks the cache for: the slot of a still pose, which others
/// showing it share, or one of its own.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Wants {
    Still(usize),
    Own(usize),
}

/// The most different slots that the events at these cells, asking for
/// these, can want at once for some position of the camera: what the
/// console draws is what the 32x32 box puts on screen —[`reach`] cells
/// across and down—. A map smaller than that is one window.
pub fn peak(events: &[(i32, i32, Wants)], width: i32, height: i32) -> usize {
    let (rx, ry) = reach();
    let mut best = 0;
    for cx in 0..=(width - rx).max(0) {
        for cy in 0..=(height - ry).max(0) {
            let seen: BTreeSet<&Wants> = events
                .iter()
                .filter(|(x, y, _)| (cx..cx + rx).contains(x) && (cy..cy + ry).contains(y))
                .map(|(_, _, w)| w)
                .collect();
            best = best.max(seen.len());
        }
    }
    best
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_same_still_pose_counts_once_and_whoever_walks_counts_alone() {
        let events = [
            (0, 0, Wants::Still(0)),
            (1, 0, Wants::Still(0)),
            (2, 0, Wants::Own(2)),
            (3, 0, Wants::Own(3)),
        ];
        assert_eq!(peak(&events, 40, 40), 3);
    }

    #[test]
    fn only_what_one_camera_shows_counts_together() {
        // 18 cells apart across: never on the same screen.
        let events = [(0, 0, Wants::Own(0)), (18, 0, Wants::Own(1)), (17, 0, Wants::Own(2))];
        assert_eq!(peak(&events, 40, 40), 2);
        // A map smaller than the screen is all one window.
        assert_eq!(peak(&[(0, 0, Wants::Own(0)), (9, 9, Wants::Own(1))], 10, 10), 2);
    }
}
