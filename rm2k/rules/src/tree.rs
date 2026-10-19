//! The map tree: what a map inherits from the nodes above it, and the
//! random encounters, which live in the tree and not in the maps.
//!
//! A node is the root (type 0), a map (1) or an **area** (2): a node with
//! no map of its own that hangs from a map and covers a rectangle of it,
//! with encounters of its own.

use ditto::schema::{
    MapInfo, MapInfoBGMType, MapInfoMusicType, MapInfoTriState, Music, TreeMap, TreeMapMapType,
};
use std::collections::BTreeMap;

/// The tree's nodes by number, and whatever a caller put over them.
#[derive(Debug, Clone, Default)]
pub struct Tree {
    pub nodes: BTreeMap<i32, MapInfo>,
}

impl From<&TreeMap> for Tree {
    fn from(tree: &TreeMap) -> Tree {
        let mut t = Tree::default();
        for node in &tree.maps {
            t.insert(node.clone());
        }
        t
    }
}

/// One place a map's encounters come from: the whole map, or an area.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Zone {
    /// Left, top, right, bottom, **half-open** —`Rect::IsOutOfBounds`:
    /// inside is `l <= x < r` and `t <= y < b`—.
    pub rect: [i64; 4],
    /// The troops, by number, in the order of their encounter ids.
    pub troops: Vec<i64>,
}

/// What a map lets the player do, once its "the parent's" are resolved:
/// RM2k writes these over `Game_System`'s permissions when the map is
/// entered, the same ones `ChangeSaveAccess`, `ChangeEscapeAccess` and
/// `ChangeTeleportAccess` set.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Access {
    /// The pause menu's Save.
    pub save: bool,
    /// The Escape skill, the one that takes the party to the escape
    /// point. **Not the battle's Escape command**, which only the battle
    /// decides —`EnemyEncounter`'s option, and always for a random one—.
    pub escape: bool,
    /// The Teleport skill.
    pub teleport: bool,
}

/// A node's troops, in the order of their encounter ids.
pub fn troops(node: &MapInfo) -> Vec<i64> {
    let mut encounters: Vec<(i32, i32)> =
        node.encounters.iter().map(|e| (e.id, e.troop_id)).collect();
    encounters.sort_by_key(|&(id, _)| id);
    encounters
        .into_iter()
        .map(|(_, troop)| troop as i64)
        .collect()
}

impl Tree {
    /// A node, over the one with its number if there is one: it is how a
    /// caller adds a map the game does not have.
    pub fn insert(&mut self, node: MapInfo) {
        self.nodes.insert(node.id, node);
    }

    pub fn get(&self, id: i32) -> Option<&MapInfo> {
        self.nodes.get(&id)
    }

    /// Every how many steps an encounter comes on a map, on average; 0 is
    /// never. A map the tree does not have gets the format's default.
    pub fn encounter_steps(&self, map: i32) -> i32 {
        self.get(map)
            .map_or_else(|| MapInfo::default().encounter_steps, |n| n.encounter_steps)
    }

    /// A map's zones, `width` by `height` cells: its own, covering it all,
    /// and one per area that hangs from it, in the order of their numbers.
    /// A node without troops gives no zone.
    ///
    /// It is easyrpg's `Game_Map::GetEncountersAt`, which walks the tree by
    /// index: putting the map's own first can only change which troop comes
    /// out on a map with troops of its own **and** areas.
    pub fn encounter_zones(&self, map: i32, width: i64, height: i64) -> Vec<Zone> {
        let mut zones = Vec::new();
        if let Some(node) = self.get(map) {
            let own = troops(node);
            if !own.is_empty() {
                zones.push(Zone {
                    rect: [0, 0, width, height],
                    troops: own,
                });
            }
        }
        for node in self.nodes.values() {
            if node.r#type == TreeMapMapType::Area && node.parent_map == map {
                let theirs = troops(node);
                if !theirs.is_empty() {
                    let r = &node.area_rect;
                    zones.push(Zone {
                        rect: [r.l as i64, r.t as i64, r.r as i64, r.b as i64],
                        troops: theirs,
                    });
                }
            }
        }
        zones
    }

    /// The battle background of an encounter on this map: its name, or
    /// `None` if it is that of the terrain the hero stands on.
    ///
    /// easyrpg's `Game_Map::SetupBattle`: it climbs the tree while the node
    /// says "the parent's", and only "this one" carries a name. Anything
    /// else —"the terrain's", or reaching the root— leaves it to the terrain.
    /// What is asked is the map and not the area.
    pub fn background(&self, map: i32) -> Option<&str> {
        let mut seen = std::collections::BTreeSet::new();
        let mut id = map;
        while id != 0 && seen.insert(id) {
            let Some(node) = self.get(id) else {
                return None;
            };
            match node.background_type {
                MapInfoBGMType::Parent => id = node.parent_map,
                MapInfoBGMType::Specific if !node.background_name.is_empty() => {
                    return Some(&node.background_name)
                }
                _ => return None,
            }
        }
        None
    }

    /// A map's song, inherited from its parents.
    ///
    /// "The parent's" climbs; "this one" is the map's own, if it names one
    /// —an empty name climbs too—; "an event sets it" is, until an event
    /// does, nothing.
    pub fn music(&self, map: i32) -> Option<&Music> {
        let mut seen = std::collections::BTreeSet::new();
        let mut id = map;
        while id != 0 && seen.insert(id) {
            let node = self.get(id)?;
            match node.music_type {
                MapInfoMusicType::Specific if !node.music.name.is_empty() => {
                    return Some(&node.music)
                }
                MapInfoMusicType::Event => return None,
                _ => id = node.parent_map,
            }
        }
        None
    }

    /// What a map allows, inherited from its parents.
    ///
    /// easyrpg's `Game_Map::Setup`: each of the three climbs while it says
    /// "the parent's", and reaching the root —a parent 0, whose own values
    /// are never read— leaves it allowed; only a "forbid" forbids. A map
    /// the tree does not have allows everything.
    pub fn access(&self, map: i32) -> Access {
        let resolve = |pick: fn(&MapInfo) -> MapInfoTriState| {
            let mut seen = std::collections::BTreeSet::new();
            let mut id = map;
            while id != 0 && seen.insert(id) {
                let Some(node) = self.get(id) else {
                    return true;
                };
                match pick(node) {
                    MapInfoTriState::Parent => id = node.parent_map,
                    state => return state != MapInfoTriState::Forbid,
                }
            }
            true
        };
        Access {
            save: resolve(|n| n.save),
            escape: resolve(|n| n.escape),
            teleport: resolve(|n| n.teleport),
        }
    }
}
