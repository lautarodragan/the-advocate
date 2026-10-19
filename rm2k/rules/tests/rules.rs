//! The rules the Python copy has no function for: they are checked here
//! against what easyrpg-player's source says, case by case.

use ditto::schema::{ChipsetAnimType, Encounter, MapInfo, Rect, TreeMapMapType};
use rm2k_rules::animation::water_drawing;
use rm2k_rules::tree::{Tree, Zone};

/// `TilemapLayer::Draw`: `frames / speed`, then `% 3` if the type is not 0,
/// and otherwise `% 4` with the fourth step drawing the second.
#[test]
fn the_water_walks_its_three_drawings() {
    let walk = |kind, speed| -> Vec<u32> {
        (0..8)
            .map(|step| water_drawing(step * if speed == 0 { 24 } else { 12 }, kind, speed))
            .collect()
    };
    assert_eq!(
        walk(ChipsetAnimType::Reciprocating, 0),
        [0, 1, 2, 1, 0, 1, 2, 1]
    );
    assert_eq!(walk(ChipsetAnimType::Cyclic, 1), [0, 1, 2, 0, 1, 2, 0, 1]);
    assert_eq!(walk(ChipsetAnimType::Other(7), 0), [0, 1, 2, 0, 1, 2, 0, 1]);
    assert_eq!(water_drawing(23, ChipsetAnimType::Reciprocating, 0), 0);
    assert_eq!(water_drawing(11, ChipsetAnimType::Reciprocating, 5), 0);
    assert_eq!(water_drawing(12, ChipsetAnimType::Reciprocating, 5), 1);
}

fn node(id: i32, kind: TreeMapMapType, parent: i32, troops: &[i32], rect: [u32; 4]) -> MapInfo {
    MapInfo {
        id,
        r#type: kind,
        parent_map: parent,
        // Out of order, as a dump could hold them: they go by encounter id.
        encounters: troops
            .iter()
            .enumerate()
            .rev()
            .map(|(k, &t)| Encounter {
                id: k as i32 + 1,
                troop_id: t,
                ..Default::default()
            })
            .collect(),
        area_rect: Rect {
            l: rect[0],
            t: rect[1],
            r: rect[2],
            b: rect[3],
            ..Default::default()
        },
        ..Default::default()
    }
}

#[test]
fn a_map_meets_its_own_troops_and_those_of_its_areas() {
    let mut tree = Tree::default();
    tree.insert(node(1, TreeMapMapType::Map, 0, &[4, 5], [0; 4]));
    tree.insert(node(2, TreeMapMapType::Area, 1, &[6], [1, 2, 3, 4]));
    tree.insert(node(3, TreeMapMapType::Area, 1, &[], [0, 0, 9, 9]));
    tree.insert(node(4, TreeMapMapType::Area, 5, &[7], [0, 0, 1, 1]));
    tree.insert(node(5, TreeMapMapType::Map, 0, &[], [0; 4]));
    assert_eq!(
        tree.encounter_zones(1, 20, 15),
        [
            Zone {
                rect: [0, 0, 20, 15],
                troops: vec![4, 5]
            },
            Zone {
                rect: [1, 2, 3, 4],
                troops: vec![6]
            },
        ]
    );
    assert_eq!(
        tree.encounter_zones(5, 20, 15),
        [Zone {
            rect: [0, 0, 1, 1],
            troops: vec![7]
        }]
    );
    assert!(
        tree.encounter_zones(9, 20, 15).is_empty(),
        "a map the tree does not have"
    );
    assert_eq!(tree.encounter_steps(9), 25, "the format's default");
    tree.insert(MapInfo {
        id: 1,
        ..Default::default()
    });
    assert!(
        tree.encounter_zones(1, 20, 15).len() == 1,
        "a node inserted replaces the old one"
    );
}

/// `Game_Map::Setup`: "the parent's" climbs, each of the three on its own,
/// and reaching the root leaves it allowed, whatever the root says.
#[test]
fn a_map_inherits_what_it_allows_from_its_parents() {
    use ditto::schema::MapInfoTriState::{Allow, Forbid, Parent};
    use rm2k_rules::tree::Access;
    let mut tree = Tree::default();
    let with = |id, parent, save, escape, teleport| MapInfo {
        id,
        parent_map: parent,
        save,
        escape,
        teleport,
        ..Default::default()
    };
    tree.insert(with(0, 0, Forbid, Forbid, Forbid));
    tree.insert(with(1, 0, Forbid, Parent, Allow));
    tree.insert(with(2, 1, Parent, Forbid, Parent));
    tree.insert(with(3, 2, Parent, Allow, Forbid));
    tree.insert(with(4, 0, Parent, Parent, Parent));
    let all = |save, escape, teleport| Access {
        save,
        escape,
        teleport,
    };
    assert_eq!(
        tree.access(1),
        all(false, true, true),
        "the root's own are not read"
    );
    assert_eq!(tree.access(2), all(false, false, true));
    assert_eq!(
        tree.access(3),
        all(false, true, false),
        "each one stops on its own"
    );
    assert_eq!(tree.access(4), all(true, true, true));
    assert_eq!(
        tree.access(9),
        all(true, true, true),
        "a map the tree does not have"
    );
    tree.insert(with(5, 6, Parent, Parent, Parent));
    tree.insert(with(6, 5, Parent, Parent, Parent));
    assert_eq!(
        tree.access(5),
        all(true, true, true),
        "a loop in the tree ends"
    );
}
