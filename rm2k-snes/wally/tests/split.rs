//! A map's characters split into the eight object palettes, its VRAM
//! bank, its pose bank and the extras at the end of the bank, over a map
//! built inside this file, which needs no real game.
//!
//! The map touches every path it can without a game: CharSets that fit in
//! fifteen colours and ones that have to merge, events drawn with a tile —
//! one that imposes its passage bits, one above the hero that imposes
//! none—, an event whose graphic changes with a condition, one with a
//! single conditioned page, one with a condition the console does not
//! check, one that animates standing still, a gap in the ids; leader
//! candidates that are also events of the map, one without a graphic, one
//! that shares the leaders' slot; graphics a route changes to, and one that
//! turns. And five splits of it: with room for everything, with the
//! timer, with eight more characters that fill the palettes, with five
//! palettes where they have to be lent, and with only the eight, where a
//! character has to lose colours for the timer.
//!
//!
//! **The path it guards**: those five splits over those shapes. A game's
//! maps go through the split on every build, and A Blurred Line's goldens
//! see how they are drawn, but none of its maps is all of these at once;
//! `lending.rs` and `timer_room.rs` take two of its maps' hard cases. What
//! is checked is what the console needs of any split: no more palettes
//! than it has, fifteen colours each, every character with a palette, the
//! leaders' palettes nobody else's, and the extras each in its own place.

use rm2k_render::Picture;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use wally::events::{collect_npcs, Event, Page};
use wally::sprites::bank::{build_characters, pose_bank, Slot, SlotPose};
use wally::sprites::character::{Key, Sheets, INITIAL_POSE};
use wally::sprites::extras::{
    first_place, map_animation, picture_of_image, rain_drops, timer_colors, timer_digits, Image,
    RAIN_COLORS,
};
use wally::sprites::npc::map_poses;
use wally::sprites::split::{drawable_npcs, Ask};

fn h(n: u64) -> u64 {
    let mut n = (n * 2654435761) & 0xFFFF_FFFF;
    n ^= n >> 13;
    n = (n * 1274126177) & 0xFFFF_FFFF;
    n ^ (n >> 16)
}

/// A CharSet sheet from a formula: blocks of 4x4 of `colors` colours, one
/// pixel in five transparent.
fn sheet(seed: u64, colors: u64) -> Picture {
    let mut rgba = Vec::with_capacity(288 * 256 * 4);
    for y in 0..256u64 {
        for x in 0..288u64 {
            let k = h(seed * 131 + x / 4 + 97 * (y / 4)) % colors;
            let a = if h(x * 7 + y * 13 + seed).is_multiple_of(5) {
                0
            } else {
                255
            };
            rgba.extend_from_slice(&[
                (h(k * 3 + seed) & 255) as u8,
                (h(k * 3 + 1 + seed) & 255) as u8,
                (h(k * 3 + 2 + seed) & 255) as u8,
                a,
            ]);
        }
    }
    Picture {
        width: 288,
        height: 256,
        rgba,
    }
}

fn sheets() -> Sheets {
    let mut out: Sheets = [
        ("people", 1, 6),
        ("crowd", 2, 40),
        ("savept", 3, 30),
        ("ghost", 4, 9),
        ("future", 5, 8),
        ("@tile:chip:5", 6, 3),
        ("@tile:chip:9", 7, 2),
        ("@tile:chip:11", 8, 5),
    ]
    .into_iter()
    .map(|(name, seed, colors)| (name.to_string(), Some(sheet(seed, colors))))
    .collect();
    out.insert("blank".to_string(), Some(Picture::transparent(288, 256)));
    out
}

type Row = (
    i32,
    i32,
    i32,
    Vec<(
        &'static str,
        i32,
        i32,
        i32,
        i32,
        i32,
        i32,
        Vec<&'static str>,
    )>,
);

fn table(which: &str) -> Vec<Row> {
    let events: Vec<Row> = vec![
        (1, 3, 4, vec![("people", 0, 2, 1, 1, 3, 0, vec![])]),
        (2, 5, 4, vec![("people", 1, 1, 0, 1, 4, 1, vec![])]),
        (
            4,
            7,
            2,
            vec![
                ("crowd", 2, 0, 2, 0, 3, 0, vec!["switch_a"]),
                ("crowd", 5, 3, 1, 1, 3, 0, vec![]),
            ],
        ),
        (5, 1, 1, vec![("", 5, 2, 1, 0, 3, 0, vec![])]),
        (6, 2, 1, vec![("", 9, 2, 1, 0, 3, 0, vec![])]),
        (7, 9, 9, vec![("savept", 3, 0, 3, 1, 3, 3, vec![])]),
        (8, 4, 8, vec![("ghost", 4, 2, 1, 2, 3, 0, vec!["switch_a"])]),
        (9, 6, 6, vec![("", 0, 2, 1, 1, 3, 0, vec![])]),
        (
            10,
            8,
            3,
            vec![
                ("crowd", 7, 1, 1, 1, 3, 0, vec!["timer", "variable"]),
                ("people", 2, 2, 1, 1, 3, 0, vec![]),
            ],
        ),
        (11, 10, 3, vec![("future", 1, 2, 1, 1, 3, 0, vec![])]),
        (12, 11, 3, vec![("", 11, 2, 1, 0, 3, 0, vec![])]),
    ];
    let crowd: Vec<Row> = (0..8)
        .map(|k| {
            (
                20 + k,
                12 + k % 6,
                10 + k / 6,
                vec![("crowd", k, 2, 1, 1, 3, 0, vec![])],
            )
        })
        .collect();
    match which {
        "light" => events,
        "full" => events.into_iter().chain(crowd).collect(),
        _ => crowd,
    }
}

fn events(which: &str) -> Vec<Event> {
    table(which)
        .into_iter()
        .map(|(id, x, y, pages)| Event {
            id,
            x,
            y,
            pages: pages
                .into_iter()
                .map(
                    |(name, index, direction, pattern, layer, speed, animation, conditions)| Page {
                        name: name.to_string(),
                        index,
                        pose: direction * 3 + if pattern == 3 { 1 } else { pattern },
                        layer,
                        speed,
                        animation,
                        move_type: 0,
                        own_route: false,
                        translucent: false,
                        conditions: conditions
                            .into_iter()
                            .map(|c| match c {
                                "switch_a" => "switch_a",
                                "variable" => "variable",
                                _ => "timer",
                            })
                            .collect(),
                        commands: Vec::new(),
                    },
                )
                .collect(),
        })
        .collect()
}

fn flags() -> Vec<u8> {
    let mut flags = vec![0u8; 65536];
    flags[10005] = 0x0F;
    flags[10009] = 0x1F;
    flags[10011] = 0x03;
    flags
}

fn glyphs() -> Picture {
    let mut picture = Picture::transparent(88, 16);
    for y in 0..16u64 {
        for x in 0..88u64 {
            if !h(x * 3 + y * 31).is_multiple_of(3) {
                let color = if !h(x + y).is_multiple_of(2) {
                    [248, 0, 0, 255]
                } else {
                    [0, 0, 0, 255]
                };
                let at = ((y * 88 + x) * 4) as usize;
                picture.rgba[at..at + 4].copy_from_slice(&color);
            }
        }
    }
    picture
}

fn picture_cells() -> Image {
    Image {
        tiles: 64,
        cells: (0..40u64)
            .step_by(3)
            .map(|n| {
                let mut cell = [[0u8; 8]; 8];
                for (y, row) in cell.iter_mut().enumerate() {
                    for (x, v) in row.iter_mut().enumerate() {
                        *v = (h(n * 64 + y as u64 * 8 + x as u64) % 16) as u8;
                    }
                }
                (n as usize, cell)
            })
            .collect(),
    }
}

fn leaders() -> Vec<Key> {
    vec![
        ("future".to_string(), 1),
        ("people".to_string(), 0),
        ("blank".to_string(), 0),
        ("ghost".to_string(), 2),
    ]
}

/// The five splits: which characters, how many palettes, the timer.
const SPLITS: [(&str, usize, bool); 5] = [
    ("light", 8, false),
    ("light", 8, true),
    ("full", 8, true),
    ("full", 5, false),
    ("crowd", 8, true),
];

#[test]
fn every_split_fits_the_console_and_keeps_the_leaders_apart() {
    let sheets = sheets();
    let flags = flags();
    let leaders = leaders();
    let route_graphics: Vec<Key> = vec![("ghost".to_string(), 6), ("people".to_string(), 3)];
    let movable: BTreeSet<usize> = [1, 5].into();
    let animates_still: BTreeSet<usize> = [5].into();
    let turning: BTreeMap<usize, BTreeSet<Key>> = [(0, [("people".to_string(), 0)].into())].into();
    let singles: HashSet<Key> = [("people".to_string(), 0), ("crowd".to_string(), 2)].into();
    let weights: BTreeMap<String, i64> = [("savept".to_string(), 5)].into();
    for (which, cap, with_timer) in SPLITS {
        let name = format!("{which} {cap} {with_timer}");
        let events = events(which);
        let npcs = collect_npcs(&events, "chip", &flags);
        let poses = map_poses(
            &leaders,
            &npcs,
            &movable,
            &turning,
            &route_graphics,
            &animates_still,
        );
        let glyphs = glyphs();
        let timer = if with_timer {
            timer_colors(&glyphs)
        } else {
            Vec::new()
        };
        let ask = Ask {
            sheets: &sheets,
            leaders: &leaders,
            cap,
            route_graphics: &route_graphics,
            hero_graphics: &Default::default(),
            timer_colors: &timer,
            only_here: &singles,
            poses: &poses,
            weights: &weights,
        };
        let d = drawable_npcs(&ask, npcs).unwrap();
        let s = &d.split;
        assert!(d.discarded.is_empty(), "{name}: {:?}", d.discarded);
        assert!(
            s.palettes.len() <= cap,
            "{name}: {} palettes",
            s.palettes.len()
        );
        for (p, colors) in s.palettes.iter().enumerate() {
            assert!(
                colors.len() <= 15,
                "{name}: palette {p} has {}",
                colors.len()
            );
        }
        for n in &d.npcs {
            let key = (n.charset.clone(), n.index);
            let p = s
                .palette_of
                .get(&key)
                .unwrap_or_else(|| panic!("{name}: {key:?} has no palette"));
            assert!(p < s.palettes.len(), "{name}: {key:?} in palette {p}");
            if !leaders.contains(&key) {
                assert!(
                    !s.leader_owned.contains(&p),
                    "{name}: {key:?} is drawn with a leader's palette {p}"
                );
            }
        }
        // Only the crowd with the timer has no room for it, and only there
        // a character is brought down a colour and says so.
        let crowded = which == "crowd";
        assert_eq!(!s.caps.is_empty(), crowded, "{name}: {:?}", s.caps);
        assert_eq!(!d.notes.is_empty(), crowded, "{name}: {:?}", d.notes);
        // Lent only where the palettes run out.
        assert_eq!(!s.lent.is_empty(), which != "light", "{name}: {:?}", s.lent);

        // The bank: the first leader in block 0, then each drawn event's
        // pose, shared by (CharSet, index, pose).
        let first = leaders[0].clone();
        let mut slots = vec![SlotPose {
            slot: Slot::Hero,
            charset: first.0.clone(),
            index: first.1,
            pose: INITIAL_POSE,
        }];
        for n in &d.npcs {
            let slot = Slot::Still(n.charset.clone(), n.index, n.pose);
            if !slots.iter().any(|s| s.slot == slot) {
                slots.push(SlotPose {
                    slot,
                    charset: n.charset.clone(),
                    index: n.index,
                    pose: n.pose,
                });
            }
        }
        let mut characters: Vec<Key> = Vec::new();
        for s in &slots {
            let key = (s.charset.clone(), s.index);
            if !characters.contains(&key) {
                characters.push(key);
            }
        }
        let bank = build_characters(&sheets, &characters, &slots, s).unwrap();
        assert_eq!(bank.place.len(), slots.len(), "{name}: a slot per pose");
        let mut animated = vec![first.clone()];
        animated.extend(
            d.npcs
                .iter()
                .filter(|n| movable.contains(&n.event))
                .map(|n| (n.charset.clone(), n.index)),
        );
        pose_bank(&sheets, &animated, &bank.colors).unwrap();

        // The extras each past the one before —the timer and the drops in
        // the columns the last row of blocks leaves free, see `strip_base`—,
        // the timer and the drops in palettes that are not the leaders'.
        let (mut tiles, mut palettes) = (bank.tiles, bank.palettes);
        let timer_at = with_timer.then(|| {
            timer_digits(
                &glyphs,
                &mut tiles,
                &mut palettes,
                &s.leader_owned,
                cap,
                true,
            )
            .unwrap()
        });
        let mut avoid = s.leader_owned.clone();
        avoid.extend(timer_at.map(|t| t.1));
        let rain = if first_place(&mut palettes.clone(), &avoid, &RAIN_COLORS, cap).is_some() {
            rain_drops(&mut tiles, &mut palettes, &s.leader_owned, timer_at, cap).unwrap()
        } else {
            (0, 0)
        };
        let previous = if rain.0 != 0 {
            rain.0
        } else {
            timer_at.map_or(0, |t| t.0)
        };
        let image = picture_of_image(&picture_cells(), &mut tiles, &palettes, previous, 1)
            .unwrap_or((0, 0));
        let animation = map_animation(&mut tiles, &palettes, image.1).unwrap_or((0, 0));
        for (what, at) in [("timer", timer_at), ("rain", Some(rain))] {
            if let Some((_, palette)) = at.filter(|a| a.0 != 0) {
                assert!(
                    !s.leader_owned.contains(&palette),
                    "{name}: the {what} in a leader's palette"
                );
            }
        }
        let starts: Vec<usize> = [timer_at.map_or(0, |t| t.0), rain.0, image.0, animation.0]
            .into_iter()
            .filter(|&t| t != 0)
            .collect();
        assert!(
            starts.windows(2).all(|w| w[0] < w[1]),
            "{name}: the extras overlap: {starts:?}"
        );
        assert!(
            starts.iter().all(|&t| t < tiles.len() / 32),
            "{name}: an extra past the bank: {starts:?}"
        );
        assert!(palettes.len() <= cap, "{name}: {} palettes", palettes.len());
    }
}
