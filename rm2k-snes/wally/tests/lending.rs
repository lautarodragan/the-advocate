//! Which palette a character that fits in none is lent: the one it is drawn
//! nearest with, over the poses the map shows.
//!
//! It is map 38 of A Blurred Line made small. There a chest of greys stood
//! still, and the rest of its block —other objects the map never shows—
//! was painted with browns: counting the pixels of all twelve poses that
//! missed, the browns' palette missed fewest, and the chest was drawn
//! golden. Until 2026-10-17 that was the measure.

use rm2k_render::Picture;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use wally::events::{collect_npcs, Event, Page};
use wally::sprites::character::{Key, Sheets};
use wally::sprites::npc::map_poses;
use wally::sprites::split::{drawable_npcs, Ask};

/// A CharSet whose first character paints pose `p` with `colors(p)`, in
/// 4x4 blocks, every colour in turn.
fn sheet(colors: impl Fn(i32) -> Vec<[u8; 3]>) -> Picture {
    let mut picture = Picture::transparent(288, 256);
    for pose in 0..12 {
        let colors = colors(pose);
        let (ox, oy) = ((pose % 3) as usize * 24, (pose / 3) as usize * 32);
        for y in 0..32usize {
            for x in 0..24usize {
                let c = colors[(x / 4 + 6 * (y / 4)) % colors.len()];
                let at = ((oy + y) * 288 + ox + x) * 4;
                picture.rgba[at..at + 4].copy_from_slice(&[c[0], c[1], c[2], 255]);
            }
        }
    }
    picture
}

/// Fifteen greys.
fn greys() -> Vec<[u8; 3]> {
    (0..15)
        .map(|j| [8 * (j + 1), 8 * (j + 1), 8 * (j + 1)])
        .collect()
}

/// Fifteen browns.
fn browns() -> Vec<[u8; 3]> {
    (0..15).map(|j| [64 + 8 * j, 16 + 8 * j, 0]).collect()
}

/// Fifteen greens, which nobody wants.
fn greens() -> Vec<[u8; 3]> {
    (0..15).map(|j| [0, 64 + 8 * j, 32]).collect()
}

fn page(name: &str) -> Page {
    Page {
        name: name.to_string(),
        index: 0,
        pose: 7,
        layer: 1,
        speed: 3,
        animation: 0,
        move_type: 0,
        own_route: false,
        conditions: Vec::new(),
        commands: Vec::new(),
    }
}

#[test]
fn a_character_is_lent_the_palette_it_is_drawn_nearest_with() {
    let mut sheets: Sheets = Default::default();
    sheets.insert("greys".into(), Some(sheet(|_| greys())));
    sheets.insert("browns".into(), Some(sheet(|_| browns())));
    sheets.insert("greens".into(), Some(sheet(|_| greens())));
    // The chest: the pose the map shows is the greys a step bluer, none of
    // them exact; the other eleven are the browns exactly.
    let bluish: Vec<[u8; 3]> = greys().iter().map(|c| [c[0], c[1], c[2] + 8]).collect();
    sheets.insert(
        "chest".into(),
        Some(sheet(
            move |p| if p == 7 { bluish.clone() } else { browns() },
        )),
    );

    let names = ["greys", "browns", "greens", "chest"];
    let events: Vec<Event> = names
        .iter()
        .enumerate()
        .map(|(i, name)| Event {
            id: i as i32 + 1,
            x: i as i32,
            y: 0,
            pages: vec![page(name)],
        })
        .collect();
    let npcs = collect_npcs(&events, "chip", &vec![0u8; 65536]);
    let poses = map_poses(
        &[],
        &npcs,
        &BTreeSet::new(),
        &BTreeMap::new(),
        &[],
        &BTreeSet::new(),
    );
    let only_here: HashSet<Key> = Default::default();
    let ask = Ask {
        sheets: &sheets,
        leaders: &[],
        cap: 3,
        route_graphics: &[],
        hero_graphics: &Default::default(),
        timer_colors: &[],
        only_here: &only_here,
        poses: &poses,
        weights: &Default::default(),
    };
    let s = drawable_npcs(&ask, npcs).unwrap().split;
    let chest = ("chest".to_string(), 0);
    assert!(s.lent.contains(&chest), "it fits in none: {:?}", s.palettes);
    assert_eq!(
        s.palette_of.get(&chest),
        s.palette_of.get(&("greys".to_string(), 0)),
        "drawn with the greys, not with the browns of the poses it does not show"
    );
}
