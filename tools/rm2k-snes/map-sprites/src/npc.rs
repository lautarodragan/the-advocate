//! The map's events that are drawn, and which poses each graphic can show.

use crate::character::{all_poses, Key};
use std::collections::{BTreeMap, BTreeSet};

/// What a page draws: its CharSet —or the made-up sheet of a tile—, the
/// character and the pose.
pub type Graphic = (String, i32, i32);

/// An event drawn with some graphic, as its row of the map's table starts.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Npc {
    /// Its place in the map's event table —**not** its RM2k id: maps have
    /// gaps in the numbering—.
    pub event: usize,
    pub x: i32,
    pub y: i32,
    pub charset: String,
    pub index: i32,
    pub pose: i32,
    pub layer: i32,
    /// Only the hero's layer collides with him.
    pub blocks: bool,
    pub speed: i32,
    /// Whether its page animates standing still.
    pub animates: bool,
    /// Whether it is seen when the map loads.
    pub visible: bool,
    /// Whether its graphic follows the active page.
    pub changes: bool,
    /// Each page's graphic, `None` for one that draws nothing.
    pub graphics: Vec<Option<Graphic>>,
    pub layers: Vec<i32>,
    /// The passage bits it imposes on its cell, if any.
    pub tile_pass: Option<u8>,
    /// The graphics of its that got no palette and are not drawn.
    pub outside: BTreeSet<Key>,
    /// Whether it only appears and disappears with its page: one that walks
    /// and whose graphic was pinned.
    pub appears: bool,
}

impl Npc {
    /// The characters it can end up drawing: its row's and, if the graphic
    /// follows the page, those of all its pages.
    pub fn keys(&self) -> Vec<Key> {
        let mut out = vec![(self.charset.clone(), self.index)];
        if self.changes {
            out.extend(self.graphics.iter().flatten().map(|g| (g.0.clone(), g.1)));
        }
        out
    }
}

/// The three frames of the walking cycle of `pose`'s direction: all an
/// event that animates standing still can show, since it changes column
/// and never row.
pub fn pose_row(pose: i32) -> BTreeSet<i32> {
    (pose / 3 * 3..pose / 3 * 3 + 3).collect()
}

/// Which poses each character can end up showing in this map.
///
/// These take all twelve: the leader candidates, because the hero walks;
/// the events in `movable` that walk; the graphics of the events in
/// `turning`, which can end up facing any way; and the graphics routes
/// change to, which keep walking after the change. One that animates
/// standing still keeps the three frames of its row. The rest keep the pose
/// their page declares, and each page's if the graphic follows them.
///
/// The same character can be a still one and a walking one at once: the
/// union accumulates, which makes the answer independent of the order.
pub fn map_poses(
    leaders: &[Key],
    npcs: &[Npc],
    movable: &BTreeSet<usize>,
    turning: &BTreeMap<usize, BTreeSet<Key>>,
    route_graphics: &[Key],
    animates_still: &BTreeSet<usize>,
) -> BTreeMap<Key, BTreeSet<i32>> {
    let mut poses: BTreeMap<Key, BTreeSet<i32>> = BTreeMap::new();
    let mut add = |key: Key, which: BTreeSet<i32>| {
        poses.entry(key).or_default().extend(which);
    };
    for key in leaders {
        add(key.clone(), all_poses());
    }
    for pairs in turning.values() {
        for pair in pairs {
            add(pair.clone(), all_poses());
        }
    }
    for pair in route_graphics {
        add(pair.clone(), all_poses());
    }
    for npc in npcs {
        let key = (npc.charset.clone(), npc.index);
        let still = animates_still.contains(&npc.event) && movable.contains(&npc.event);
        let walks = movable.contains(&npc.event);
        let own = if still {
            pose_row(npc.pose)
        } else if walks {
            all_poses()
        } else {
            BTreeSet::from([npc.pose])
        };
        add(key, own);
        if npc.changes {
            for (name, index, pose) in npc.graphics.iter().flatten() {
                // One that walks and changes graphic loses the change, but
                // its page's graphic still asks for a palette.
                let which = if still {
                    pose_row(*pose)
                } else if walks {
                    all_poses()
                } else {
                    BTreeSet::from([*pose])
                };
                add((name.clone(), *index), which);
            }
        }
    }
    poses
}
