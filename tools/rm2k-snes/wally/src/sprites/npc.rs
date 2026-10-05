//! The map's events that are drawn, and which poses each graphic can show.

use crate::sprites::character::{all_poses, Key};
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

/// Which graphic the row of each event that walks and changes graphic is
/// pinned to, when some of its pages draw a **blank** character —a slot of
/// the CharSet without a single pixel—.
///
/// The row of an event that walks starts with the twelve poses of one
/// graphic, and each page brings its own at run time —`walker_graphic` in
/// the runtime—. The one it starts with is its row's: the page active at
/// load, or the first that draws something. When that is a blank slot the event walks and is never
/// seen. In RM2k a blank slot draws exactly what no graphic draws, so this
/// treats it as that: the row is pinned to the first page graphic with
/// pixels, and the pages with the blank one hide it. The pattern it is for:
/// an event that waits off stage with an empty slot as its graphic, and a
/// cutscene that places it, switches it to a page with a real one and sends
/// it walking —`Future2`'s eighth slot in the RTP is empty—.
///
/// Returns, by event, the blank graphics of its pages, which the caller has
/// to hide: they go with the ones that are not drawn. An event whose pages
/// are all blank, or none, is left alone.
pub fn pin_walkers(
    npcs: &mut [Npc],
    movable: &BTreeSet<usize>,
    blank: impl Fn(&Key) -> bool,
) -> BTreeMap<usize, BTreeSet<Key>> {
    let mut hidden = BTreeMap::new();
    for npc in npcs.iter_mut() {
        if !movable.contains(&npc.event) || !npc.changes {
            continue;
        }
        let blanks: BTreeSet<Key> = npc
            .graphics
            .iter()
            .flatten()
            .map(|g| (g.0.clone(), g.1))
            .filter(|k| blank(k))
            .collect();
        let Some((charset, index, pose)) = npc
            .graphics
            .iter()
            .flatten()
            .find(|g| !blanks.contains(&(g.0.clone(), g.1)))
            .cloned()
        else {
            continue;
        };
        if blanks.is_empty() {
            continue;
        }
        if blanks.contains(&(npc.charset.clone(), npc.index)) {
            // The row's graphic was the active page's at load, if any: that
            // page draws nothing now.
            npc.visible = false;
            npc.tile_pass = None;
            npc.charset = charset;
            npc.index = index;
            npc.pose = pose;
        }
        hidden.insert(npc.event, blanks);
    }
    hidden
}

#[cfg(test)]
mod tests {
    use super::*;

    fn walker(graphics: Vec<Option<Graphic>>, visible: bool) -> Npc {
        let (charset, index, pose) = graphics.iter().flatten().next().cloned().unwrap();
        Npc {
            event: 3,
            x: 0,
            y: 0,
            charset,
            index,
            pose,
            layer: 1,
            blocks: true,
            speed: 3,
            animates: false,
            visible,
            changes: true,
            graphics,
            layers: vec![1, 1],
            tile_pass: None,
            outside: Default::default(),
            appears: false,
        }
    }

    fn blank_seven(k: &Key) -> bool {
        k.1 == 7
    }

    #[test]
    fn a_walker_whose_first_page_is_blank_walks_with_the_next_one() {
        let g = |i| Some(("Townsfolk".to_string(), i, 1));
        let mut npcs = vec![walker(vec![g(7), g(6), g(6)], false)];
        let hidden = pin_walkers(&mut npcs, &BTreeSet::from([3]), blank_seven);
        assert_eq!((npcs[0].charset.as_str(), npcs[0].index), ("Townsfolk", 6));
        assert_eq!(hidden[&3], BTreeSet::from([("Townsfolk".to_string(), 7)]));
    }

    #[test]
    fn a_blank_page_active_at_load_shows_nothing() {
        let g = |i| Some(("Townsfolk".to_string(), i, 1));
        let mut npcs = vec![walker(vec![g(7), g(6)], true)];
        pin_walkers(&mut npcs, &BTreeSet::from([3]), blank_seven);
        assert!(!npcs[0].visible);
    }

    #[test]
    fn only_walkers_are_pinned_and_all_blank_is_left_alone() {
        let g = |i| Some(("Townsfolk".to_string(), i, 1));
        let mut still = vec![walker(vec![g(7), g(6)], false)];
        assert!(pin_walkers(&mut still, &BTreeSet::new(), blank_seven).is_empty());
        assert_eq!(still[0].index, 7);
        let mut empty = vec![walker(vec![g(7), None], false)];
        assert!(pin_walkers(&mut empty, &BTreeSet::from([3]), blank_seven).is_empty());
        assert_eq!(empty[0].index, 7);
    }

    #[test]
    fn a_still_animation_keeps_the_row_of_its_pose() {
        use super::pose_row;
        assert_eq!(pose_row(7), [6, 7, 8].into());
        assert_eq!(pose_row(0), [0, 1, 2].into());
    }
}
