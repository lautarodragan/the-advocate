//! A map's events and characters against the Python they replaced.
//!
//! Until 2026-09-30 which events a map draws, how its eight object palettes
//! are split, its VRAM bank, its pose bank and the extras at the end of the
//! bank were the converter's Python (`rm2k.collect_npcs`, `sprites.py`,
//! `obj_extras.py`). What is left of it is here: the SHA-256 of what it
//! made of a map built inside this file, which needs no real game.
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
//! **If one of these changes, a byte of the cartridge changed.** The
//! hashes are not to be regenerated to make a test pass: the Python that
//! produced them is gone, and with it the only independent answer.

use rm2k_render::Picture;
use rm2k_snes_map_sprites::bank::{build_characters, pose_bank, Slot, SlotPose};
use rm2k_snes_map_sprites::character::{Key, Sheets, INITIAL_POSE};
use rm2k_snes_map_sprites::extras::{
    map_animation, picture_of_image, rain_drops, timer_colors, timer_digits, Image,
};
use rm2k_snes_map_sprites::npc::{map_poses, Npc};
use rm2k_snes_map_sprites::split::{drawable_npcs, Ask};
use rm2k_snes_maps::events::{collect_npcs, Event, Page};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashSet};

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
            let a = if h(x * 7 + y * 13 + seed) % 5 == 0 { 0 } else { 255 };
            rgba.extend_from_slice(&[
                (h(k * 3 + seed) & 255) as u8,
                (h(k * 3 + 1 + seed) & 255) as u8,
                (h(k * 3 + 2 + seed) & 255) as u8,
                a,
            ]);
        }
    }
    Picture { width: 288, height: 256, rgba }
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

type Row = (i32, i32, i32, Vec<(&'static str, i32, i32, i32, i32, i32, i32, Vec<&'static str>)>);

fn table(which: &str) -> Vec<Row> {
    let events: Vec<Row> = vec![
        (1, 3, 4, vec![("people", 0, 2, 1, 1, 3, 0, vec![])]),
        (2, 5, 4, vec![("people", 1, 1, 0, 1, 4, 1, vec![])]),
        (4, 7, 2, vec![("crowd", 2, 0, 2, 0, 3, 0, vec!["switch_a"]), ("crowd", 5, 3, 1, 1, 3, 0, vec![])]),
        (5, 1, 1, vec![("", 5, 2, 1, 0, 3, 0, vec![])]),
        (6, 2, 1, vec![("", 9, 2, 1, 0, 3, 0, vec![])]),
        (7, 9, 9, vec![("savept", 3, 0, 3, 1, 3, 3, vec![])]),
        (8, 4, 8, vec![("ghost", 4, 2, 1, 2, 3, 0, vec!["switch_a"])]),
        (9, 6, 6, vec![("", 0, 2, 1, 1, 3, 0, vec![])]),
        (10, 8, 3, vec![("crowd", 7, 1, 1, 1, 3, 0, vec!["timer"]), ("people", 2, 2, 1, 1, 3, 0, vec![])]),
        (11, 10, 3, vec![("future", 1, 2, 1, 1, 3, 0, vec![])]),
        (12, 11, 3, vec![("", 11, 2, 1, 0, 3, 0, vec![])]),
    ];
    let crowd: Vec<Row> = (0..8)
        .map(|k| (20 + k, 12 + k % 6, 10 + k / 6, vec![("crowd", k, 2, 1, 1, 3, 0, vec![])]))
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
                .map(|(name, index, direction, pattern, layer, speed, animation, conditions)| Page {
                    name: name.to_string(),
                    index,
                    pose: direction * 3 + if pattern == 3 { 1 } else { pattern },
                    layer,
                    speed,
                    animation,
                    move_type: 0,
                    own_route: false,
                    conditions: conditions
                        .into_iter()
                        .map(|c| match c {
                            "switch_a" => "switch_a",
                            _ => "timer",
                        })
                        .collect(),
                    commands: Vec::new(),
                })
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
            if h(x * 3 + y * 31) % 3 != 0 {
                let color = if h(x + y) % 2 != 0 { [248, 0, 0, 255] } else { [0, 0, 0, 255] };
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

fn sha(data: &[u8]) -> String {
    Sha256::digest(data).iter().map(|b| format!("{b:02x}")).collect()
}

/// `json.dumps(value, sort_keys=True)`, which is what the Python hashed.
fn py_json(v: &Value) -> String {
    match v {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => serde_json::to_string(s).unwrap(),
        Value::Array(a) => format!("[{}]", a.iter().map(py_json).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => {
            let mut keys: Vec<&String> = o.keys().collect();
            keys.sort();
            let items: Vec<String> = keys
                .into_iter()
                .map(|k| format!("{}: {}", serde_json::to_string(k).unwrap(), py_json(&o[k])))
                .collect();
            format!("{{{}}}", items.join(", "))
        }
    }
}

fn js(v: Value) -> String {
    sha(py_json(&v).as_bytes())
}

fn key_json(k: &Key) -> Value {
    json!([k.0, k.1])
}

fn npc_view(n: &Npc) -> Value {
    json!({
        "event": n.event, "x": n.x, "y": n.y,
        "charset": n.charset, "index": n.index, "pose": n.pose,
        "layer": n.layer, "blocks": n.blocks, "speed": n.speed,
        "animates": n.animates, "visible": n.visible, "changes": n.changes,
        "graphics": n.graphics.iter().map(|g| g.as_ref().map(|(c, i, p)| json!([c, i, p]))).collect::<Vec<_>>(),
        "layers": n.layers, "tile_pass": n.tile_pass,
        "outside": n.outside.iter().map(key_json).collect::<Vec<_>>(),
    })
}

struct Expected {
    events: &'static str,
    cap: usize,
    timer: bool,
    npcs: &'static str,
    discarded: &'static str,
    palettes: &'static str,
    palette_of: &'static str,
    own: &'static str,
    leader_owned: &'static [usize],
    caps: &'static str,
    lent: &'static str,
    notes: &'static str,
    tiles: &'static str,
    place: &'static str,
    banks: &'static str,
    extras: [Option<usize>; 8],
    final_tiles: &'static str,
    final_palettes: &'static str,
}

const EXPECTED: [Expected; 5] = [
    Expected {
        events: "light", cap: 8, timer: false,
        npcs: "2cc5fe7483471f559ff1088341c1d34ee8c5e9c73c7aaab5e3caeb9a5a737d97",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "9d9614594e68e3da987f220ee1802db6204321ff7af241d9c9222639eaeb4aa1",
        palette_of: "d7568f8bc0c2b00f1fe6c83c551a222930a7fb8549d3a3ebde44cc68326b4712",
        own: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        leader_owned: &[0, 1],
        caps: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        lent: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        notes: "",
        tiles: "ebd0b724715d565781c86b133c3ff72f1961b3e82ca65e56a299a8b3bdabbc4b",
        place: "67f58f2534fd6de243cbc81c4d28673fe6ed86ca891491145bd1bd0eb8d7d4ff",
        banks: "7571bcffb14c74e78ea860fe569419d1ad6efa531ff4fabb467a8e5ac885c9b5",
        extras: [Some(0), None, Some(192), Some(6), Some(256), Some(7), Some(0), Some(0)],
        final_tiles: "b8c3ef35369a35c5c942f4e20595ff47930639ed5302083865dea24adea91f40",
        final_palettes: "9b608fdd4b557033390525a4d0566fe0a80a1fb3e051745e77e261915738b96e",
    },
    Expected {
        events: "light", cap: 8, timer: true,
        npcs: "2cc5fe7483471f559ff1088341c1d34ee8c5e9c73c7aaab5e3caeb9a5a737d97",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "4174bfc125d200647d3c5d8f5f5b0ec5a7f8c50768a962b20216a3e53e71fa97",
        palette_of: "d7568f8bc0c2b00f1fe6c83c551a222930a7fb8549d3a3ebde44cc68326b4712",
        own: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        leader_owned: &[0, 1],
        caps: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        lent: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        notes: "",
        tiles: "a0c922cb6f4b390f73360bd3f89dc69336d8a01ae31605765126bdfd4ac4454a",
        place: "67f58f2534fd6de243cbc81c4d28673fe6ed86ca891491145bd1bd0eb8d7d4ff",
        banks: "7571bcffb14c74e78ea860fe569419d1ad6efa531ff4fabb467a8e5ac885c9b5",
        extras: [Some(192), Some(3), Some(203), Some(6), Some(256), Some(7), Some(0), Some(0)],
        final_tiles: "c75481d235ebf47b0e259ac3b9966f67205d65fef913799e87dd5848549fc61d",
        final_palettes: "c0d77d70c1948364eff7178568c14e604aadfdf91bac03087103c50aa0f81a1f",
    },
    Expected {
        events: "full", cap: 8, timer: true,
        npcs: "2a122f4a7f0f74a4b1e5f3074dda27c90985aa750a82e9ac0f29b6720be07d8f",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "2f00c8e1c22f1e44fea55f2a417fcb9a0ba415cca5b7018980d3bbc92cd76231",
        palette_of: "e734d7f32e8a9aa80c2e80cae59f08f72472ae2e0262a069bf11f0d95185edee",
        own: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        leader_owned: &[0, 1],
        caps: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        lent: "da96daf6857d758b7995223724a0a7e91a32b009b64fc6443d0c68a78c36d549",
        notes: "",
        tiles: "c69fae703be26b8837c92cd69f1e2c5c604c27bc5ce14da998c1e4a0483e2427",
        place: "9b263877eec9f358c73642c7145d38547e7141447a0b551c88a7b7f9288b9d8d",
        banks: "7571bcffb14c74e78ea860fe569419d1ad6efa531ff4fabb467a8e5ac885c9b5",
        extras: [Some(320), Some(3), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0)],
        final_tiles: "c2708ff234b2316241c3833300bb134038791add24b930c09b3820a2fa697477",
        final_palettes: "2f00c8e1c22f1e44fea55f2a417fcb9a0ba415cca5b7018980d3bbc92cd76231",
    },
    Expected {
        events: "full", cap: 5, timer: false,
        npcs: "2a122f4a7f0f74a4b1e5f3074dda27c90985aa750a82e9ac0f29b6720be07d8f",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "f68785dd1e3051fb5a06050dc1cb482cf4372557844ee32b25f4315819ac43b5",
        palette_of: "d290f736160f44a20a100536a14b194390ea0e9047b782457a0fd52b93fd7b23",
        own: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        leader_owned: &[0, 1],
        caps: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        lent: "336912bdbe3d5dd03e646453e46fdd732425dd1026af9f050109d9db6e698068",
        notes: "",
        tiles: "c99b1f2acd7354b57ec6dced2d9b6c229fb422deba1ebf2a1d07d5312696e1ea",
        place: "a8b4dfa49686e39b6d9cda02c1d08069e3b472a2a3ad8d2d95dbc1bc226e8842",
        banks: "7571bcffb14c74e78ea860fe569419d1ad6efa531ff4fabb467a8e5ac885c9b5",
        extras: [Some(0), None, Some(0), Some(0), Some(320), Some(5), Some(384), Some(6)],
        final_tiles: "219511947efd09cd3e2a63ad17d96e53740e838643561e0d8ae8695d10c9e6bb",
        final_palettes: "f68785dd1e3051fb5a06050dc1cb482cf4372557844ee32b25f4315819ac43b5",
    },
    Expected {
        events: "crowd", cap: 8, timer: true,
        npcs: "3d11b0f32f2a726e0a8e913814deecd59ccc48959940df45b6567640d225e313",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "5e309090441059861a3b8845514a5e5e7d882e17dc7c33a936127d3553475e56",
        palette_of: "817fb66254c83c8bbfbc8ce7286e702216c87ec75461b76926d256904187f4a5",
        own: "ceb66eef073f361e1db1b0ae91b1528199bc0fc6072f6edf7c7fefb0897e331e",
        leader_owned: &[0],
        caps: "28b0e48541b3222987d7b58a56d57fa934d202d97aca28ada6df069cbb4c9888",
        lent: "325580ea971dbb07b2a4d9135efb973839e95afc88a15bf5b2d2223bba091a31",
        notes: "  to make room for the timer, crowd:2 drops to 13 colors (41.20% of its pixels)\n",
        tiles: "d28bdb3736a696736b3770af658718f8d6a7280a1f3cba0b7d3ab2e54720e505",
        place: "7b58785ce5230ae33de86820b822f3a97f79553620b3113febcfd0546885fc4e",
        banks: "2e3bd12c989636d1b1f1258a4f3de813a03a8c8174a670475f7b6113829a897a",
        extras: [Some(192), Some(3), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0)],
        final_tiles: "1812428df7249339d05675e38f94d8fe9f1b9fe4ad98604dbf28dc362e3c4f61",
        final_palettes: "6245b8b83cc910252ce0281383da7bf418cb2e67a1ceaea278cecb7312b35dab",
    },
];


fn leaders() -> Vec<Key> {
    vec![
        ("future".to_string(), 1),
        ("people".to_string(), 0),
        ("blank".to_string(), 0),
        ("ghost".to_string(), 2),
    ]
}

#[test]
fn the_characters_are_the_ones_the_python_made() {
    let sheets = sheets();
    let flags = flags();
    let leaders = leaders();
    let route_graphics: Vec<Key> = vec![("ghost".to_string(), 6), ("people".to_string(), 3)];
    let movable: BTreeSet<usize> = [1, 5].into();
    let animates_still: BTreeSet<usize> = [5].into();
    let turning: BTreeMap<usize, BTreeSet<Key>> = [(0, [("people".to_string(), 0)].into())].into();
    let singles: HashSet<Key> = [("people".to_string(), 0), ("crowd".to_string(), 2)].into();
    let weights: BTreeMap<String, i64> = [("savept".to_string(), 5)].into();
    for want in &EXPECTED {
        let name = format!("{} {} {}", want.events, want.cap, want.timer);
        let events = events(want.events);
        let npcs = collect_npcs(&events, "chip", &flags);
        let poses = map_poses(&leaders, &npcs, &movable, &turning, &route_graphics, &animates_still);
        let glyphs = glyphs();
        let timer = if want.timer { timer_colors(&glyphs) } else { Vec::new() };
        let ask = Ask {
            sheets: &sheets,
            leaders: &leaders,
            cap: want.cap,
            route_graphics: &route_graphics,
            timer_colors: &timer,
            only_here: &singles,
            poses: &poses,
            weights: &weights,
        };
        let d = drawable_npcs(&ask, npcs).unwrap();
        let s = &d.split;
        assert_eq!(js(json!(d.npcs.iter().map(npc_view).collect::<Vec<_>>())), want.npcs, "{name}: the events");
        assert_eq!(
            js(json!(d.discarded.iter().map(|(e, c)| json!([e, c])).collect::<Vec<_>>())),
            want.discarded,
            "{name}: the discarded"
        );
        assert_eq!(js(json!(s.palettes)), want.palettes, "{name}: the palettes");
        assert_eq!(
            js(json!(s.palette_of.iter().map(|(k, n)| json!([k.0, k.1, n])).collect::<Vec<_>>())),
            want.palette_of,
            "{name}: whose palette"
        );
        assert_eq!(js(json!(s.own.iter().map(key_json).collect::<Vec<_>>())), want.own, "{name}: own");
        assert_eq!(s.leader_owned.iter().copied().collect::<Vec<_>>(), want.leader_owned, "{name}: leaders'");
        assert_eq!(
            js(json!(s.caps.iter().map(|(k, c)| json!([k.0, k.1, c])).collect::<Vec<_>>())),
            want.caps,
            "{name}: caps"
        );
        assert_eq!(js(json!(s.lent.iter().map(key_json).collect::<Vec<_>>())), want.lent, "{name}: lent");
        let notes: String = d.notes.iter().map(|n| format!("{n}\n")).collect();
        assert_eq!(notes, want.notes, "{name}: what it said");

        // The bank: the first leader in block 0, then each drawn event's
        // pose, shared by (CharSet, index, pose).
        let first = leaders[0].clone();
        let mut slots = vec![SlotPose { slot: Slot::Hero, charset: first.0.clone(), index: first.1, pose: INITIAL_POSE }];
        for n in &d.npcs {
            let slot = Slot::Still(n.charset.clone(), n.index, n.pose);
            if !slots.iter().any(|s| s.slot == slot) {
                slots.push(SlotPose { slot, charset: n.charset.clone(), index: n.index, pose: n.pose });
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
        let place: Vec<Value> = bank
            .place
            .iter()
            .map(|(slot, b, p)| {
                let key = match slot {
                    Slot::Hero => "heroe".to_string(),
                    Slot::Still(c, i, p) => format!("('{c}', {i}, {p})"),
                    other => panic!("{other:?}"),
                };
                json!([key, b, p])
            })
            .collect();
        let mut animated = vec![first.clone()];
        animated.extend(d.npcs.iter().filter(|n| movable.contains(&n.event)).map(|n| (n.charset.clone(), n.index)));
        let banks = pose_bank(&sheets, &animated, &bank.colors).unwrap();
        assert_eq!(sha(&bank.tiles), want.tiles, "{name}: the VRAM bank");
        assert_eq!(js(json!(place)), want.place, "{name}: the slots");
        assert_eq!(sha(&banks.into_iter().flat_map(|(_, b)| b).collect::<Vec<_>>()), want.banks, "{name}: the pose bank");

        let (mut tiles, mut palettes) = (bank.tiles, bank.palettes);
        let timer_at = if want.timer {
            Some(timer_digits(&glyphs, &mut tiles, &mut palettes, &s.leader_owned, want.cap).unwrap())
        } else {
            None
        };
        let rain = rain_drops(&mut tiles, &mut palettes, &s.leader_owned, timer_at, want.cap).unwrap_or((0, 0));
        let previous = if rain.0 != 0 { rain.0 } else { timer_at.map_or(0, |t| t.0) };
        let image = picture_of_image(&picture_cells(), &mut tiles, &palettes, previous).unwrap_or((0, 0));
        let animation = map_animation(&mut tiles, &palettes, usize::from(image.0 != 0)).unwrap_or((0, 0));
        let extras = [
            Some(timer_at.map_or(0, |t| t.0)),
            timer_at.map(|t| t.1),
            Some(rain.0),
            Some(rain.1),
            Some(image.0),
            Some(image.1),
            Some(animation.0),
            Some(animation.1),
        ];
        assert_eq!(extras, want.extras, "{name}: where the extras went");
        assert_eq!(sha(&tiles), want.final_tiles, "{name}: the bank with the extras");
        assert_eq!(js(json!(palettes)), want.final_palettes, "{name}: the palettes with the extras");
    }
}
