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
//!
//! **Except where the port decided otherwise, on purpose**: on 2026-10-17
//! the palette a character is lent stopped being the one it misses fewest
//! pixels of, over its twelve poses, and became the one it is drawn
//! nearest with, over the poses the map shows, decided once every palette
//! is whole (see `lend` in `sprites/split.rs`). The splits where someone is
//! lent —"full 8 true", "crowd 8 true" and "full 5 false"— moved what
//! depends on whose palette each one got, or on the order they got it in;
//! the rest of each, and the other splits, are still the Python's. And the
//! same day the nearest colour stopped being the nearest by luma and became
//! the nearest in CIE Lab (`nearest` in `sprites/character.rs`): the banks
//! of those three, where someone is drawn with a colour it does not have,
//! moved too.

use rm2k_render::Picture;
use wally::sprites::bank::{build_characters, pose_bank, Slot, SlotPose};
use wally::sprites::character::{Key, Sheets, INITIAL_POSE};
use wally::sprites::extras::{
    first_place, map_animation, picture_of_image, rain_drops, timer_colors, timer_digits, Image, RAIN_COLORS,
};
use wally::sprites::npc::{map_poses, Npc};
use wally::sprites::split::{drawable_npcs, Ask};
use wally::events::{collect_npcs, Event, Page};
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
            let a = if h(x * 7 + y * 13 + seed).is_multiple_of(5) { 0 } else { 255 };
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
        (10, 8, 3, vec![("crowd", 7, 1, 1, 1, 3, 0, vec!["timer", "variable"]), ("people", 2, 2, 1, 1, 3, 0, vec![])]),
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
                            "variable" => "variable",
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
            if !h(x * 3 + y * 31).is_multiple_of(3) {
                let color = if !h(x + y).is_multiple_of(2) { [248, 0, 0, 255] } else { [0, 0, 0, 255] };
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
        palette_of: "644914f8faea7f5ec0f12d34831c40b7b49250d350a7ddd9d452214ef53d8ceb",
        own: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        leader_owned: &[0, 1],
        caps: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        lent: "da96daf6857d758b7995223724a0a7e91a32b009b64fc6443d0c68a78c36d549",
        notes: "",
        tiles: "7179c231f57068779bbdd4b35d8751b7da587843828548101f8b7219ac51e60f",
        place: "5a2cdff87e8d20dd89c901c30b1f0a65cce284b25fd3c53396e420633cbfdc6f",
        banks: "7571bcffb14c74e78ea860fe569419d1ad6efa531ff4fabb467a8e5ac885c9b5",
        extras: [Some(320), Some(3), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0)],
        final_tiles: "c43a5c1511bb5c9bdebb72fc870ab147305d6f76e37f5ea1c309f40148638ae9",
        final_palettes: "2f00c8e1c22f1e44fea55f2a417fcb9a0ba415cca5b7018980d3bbc92cd76231",
    },
    Expected {
        events: "full", cap: 5, timer: false,
        npcs: "2a122f4a7f0f74a4b1e5f3074dda27c90985aa750a82e9ac0f29b6720be07d8f",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "f68785dd1e3051fb5a06050dc1cb482cf4372557844ee32b25f4315819ac43b5",
        palette_of: "91cdc57a8a065b65163ebe3d9de1d24e6e7f7f9ed401217fb3a3fbc6a8fd2149",
        own: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        leader_owned: &[0, 1],
        caps: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        lent: "336912bdbe3d5dd03e646453e46fdd732425dd1026af9f050109d9db6e698068",
        notes: "",
        tiles: "22a698df41957d150e7f797626f69d3d22328582603c631fb77b17d8e77d0484",
        place: "a8b4dfa49686e39b6d9cda02c1d08069e3b472a2a3ad8d2d95dbc1bc226e8842",
        banks: "7571bcffb14c74e78ea860fe569419d1ad6efa531ff4fabb467a8e5ac885c9b5",
        extras: [Some(0), None, Some(0), Some(0), Some(320), Some(5), Some(384), Some(6)],
        final_tiles: "cd5af362c5b0d0e729f31da4106d068f08095512d759df273f29718df133f158",
        final_palettes: "f68785dd1e3051fb5a06050dc1cb482cf4372557844ee32b25f4315819ac43b5",
    },
    Expected {
        events: "crowd", cap: 8, timer: true,
        npcs: "3d11b0f32f2a726e0a8e913814deecd59ccc48959940df45b6567640d225e313",
        discarded: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        palettes: "5e309090441059861a3b8845514a5e5e7d882e17dc7c33a936127d3553475e56",
        palette_of: "1bc8c590c96cc9aa5b36e2101f9eeac5bd8c2ba83616f8c299677bfe7b94410a",
        own: "ceb66eef073f361e1db1b0ae91b1528199bc0fc6072f6edf7c7fefb0897e331e",
        leader_owned: &[0],
        caps: "28b0e48541b3222987d7b58a56d57fa934d202d97aca28ada6df069cbb4c9888",
        lent: "325580ea971dbb07b2a4d9135efb973839e95afc88a15bf5b2d2223bba091a31",
        notes: "  to make room for the timer, crowd:2 drops to 13 colors (41.20% of its pixels)\n",
        tiles: "700b4974516d2b380ea2f48e201e3306026edace279a6545808a818d9c11c331",
        place: "cc1744a5d26216f04993cfa1209a8eca8faf93b6518ace8f6208fd0b683873ae",
        banks: "a4cc10fa136c9935382858051a6057f618d6842f62b253db569b9d12b9ec59e1",
        extras: [Some(192), Some(3), Some(0), Some(0), Some(0), Some(0), Some(0), Some(0)],
        final_tiles: "25d03f638259703493bac852b0c7f1760ec85e1dc9bc462fd3d1939eaa80a672",
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
            hero_graphics: &Default::default(),
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
        // Since 2026-10-17 the timer and the drops go into the columns the
        // last row of blocks leaves free —see `strip_base`—, and the Python
        // always started a new row: the bank is padded to it here, blank as
        // the Python left it, so the rest is still checked against it.
        tiles.resize(tiles.len().div_ceil(32 * 64) * 32 * 64, 0);
        let timer_at = if want.timer {
            Some(timer_digits(&glyphs, &mut tiles, &mut palettes, &s.leader_owned, want.cap, true).unwrap())
        } else {
            None
        };
        // And since then a map with no palette with room for the drops'
        // greys lends them one, where the Python drew no rain: those are
        // left out here the Python's way.
        let mut avoid = s.leader_owned.clone();
        avoid.extend(timer_at.map(|t| t.1));
        let rain = if first_place(&mut palettes.clone(), &avoid, &RAIN_COLORS, want.cap).is_some() {
            rain_drops(&mut tiles, &mut palettes, &s.leader_owned, timer_at, want.cap).unwrap()
        } else {
            (0, 0)
        };
        let previous = if rain.0 != 0 { rain.0 } else { timer_at.map_or(0, |t| t.0) };
        let image = picture_of_image(&picture_cells(), &mut tiles, &palettes, previous, 1).unwrap_or((0, 0));
        let animation = map_animation(&mut tiles, &palettes, image.1).unwrap_or((0, 0));
        // Since 2026-10-01 the pictures take their palettes from the top
        // down —see `picture_of_image`— and the Python gave the picture the
        // first free one and the animation the next: same tiles, other
        // palette numbers. They are written back the Python's way here, so
        // the tiles and the rest are still checked against it.
        let first_free = palettes.len();
        let image = if image.0 != 0 { (image.0, first_free) } else { image };
        let animation = if animation.0 != 0 && image.0 != 0 {
            assert_eq!(animation.1, first_free, "{name}: the animation's palette");
            (animation.0, first_free + 1)
        } else {
            animation
        };
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
