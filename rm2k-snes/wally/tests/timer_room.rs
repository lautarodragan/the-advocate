//! The timer in a map whose eight palettes are full **and every one also
//! lends itself to someone**, so the split cannot bring an owner down a
//! colour —it only does that to a palette with one character in it—.
//!
//! It is Paradise (ABL's 108) with every leader of the game: three leaders'
//! palettes and five characters', each with a guest drawn with its
//! colours. Until 2026-10-14 the conversion stopped there with "the timer
//! doesn't fit"; now the timer is lent the palette that draws it closest.

use rm2k_render::Picture;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use wally::events::{collect_npcs, Event, Page};
use wally::sprites::character::{Key, Sheets};
use wally::sprites::extras::{timer_colors, timer_digits};
use wally::sprites::npc::map_poses;
use wally::sprites::split::{drawable_npcs, Ask};

/// A CharSet whose first character is painted, in 4x4 blocks, with
/// `colors` in turn: every colour shows, the first ones a little more.
fn sheet(colors: &[[u8; 3]]) -> Picture {
    let mut picture = Picture::transparent(288, 256);
    for y in 0..128usize {
        for x in 0..72usize {
            let c = colors[(x / 4 + 18 * (y / 4)) % colors.len()];
            let at = (y * 288 + x) * 4;
            picture.rgba[at..at + 4].copy_from_slice(&[c[0], c[1], c[2], 255]);
        }
    }
    picture
}

/// Fifteen colours for owner `k`: black, like the timer's, and fourteen of
/// its own; owner 3's last is a red close to the timer's. Each owner's reds
/// are six steps from the next one's: a guest drawn with its neighbour's
/// palette moves every pixel, and that has to cost more than the one colour
/// its own owner lacks. And all of them have the black, so the timer's red
/// alone decides which one it is lent.
fn owner(k: u8) -> Vec<[u8; 3]> {
    let mut colors: Vec<[u8; 3]> = (0..15).map(|j| [48 * (k + 1), 8 * (j + 1), 40]).collect();
    colors[0] = [0, 0, 0];
    if k == 3 {
        colors[14] = [240, 16, 8];
    }
    colors
}

/// Fourteen of owner `k`'s colours and one nobody has: it fits in no
/// palette, and owner `k`'s is the one it is drawn nearest with.
fn guest(k: u8) -> Vec<[u8; 3]> {
    let mut colors = owner(k)[..14].to_vec();
    colors.push([48 * (k + 1), 160, 200]);
    colors
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

/// Black and red, like ABL's System.
fn glyphs() -> Picture {
    let mut picture = Picture::transparent(88, 16);
    for y in 0..16usize {
        for x in 0..88usize {
            let c = if (x + y) % 3 == 0 {
                [248, 0, 0, 255]
            } else {
                [0, 0, 0, 255]
            };
            picture.rgba[(y * 88 + x) * 4..(y * 88 + x) * 4 + 4].copy_from_slice(&c);
        }
    }
    picture
}

#[test]
fn the_timer_is_lent_a_palette_when_every_one_lends_itself() {
    // Three leaders, two of them also events of the map: three palettes
    // nobody else gets. Then five owners and a guest for each.
    let mut sheets: Sheets = Default::default();
    let leaders: Vec<Key> = (0..3).map(|k| (format!("leader{k}"), 0)).collect();
    for k in 0..3u8 {
        let colors: Vec<[u8; 3]> = (0..15).map(|j| [200, 8 * (j + 1), 8 * (k + 1)]).collect();
        sheets.insert(format!("leader{k}"), Some(sheet(&colors)));
    }
    let mut events = Vec::new();
    for k in 1..3 {
        events.push(Event {
            id: events.len() as i32 + 1,
            x: k,
            y: 0,
            pages: vec![page(&format!("leader{k}"))],
        });
    }
    for k in 0..5u8 {
        sheets.insert(format!("owner{k}"), Some(sheet(&owner(k))));
        sheets.insert(format!("guest{k}"), Some(sheet(&guest(k))));
    }
    for name in (0..5)
        .map(|k| format!("owner{k}"))
        .chain((0..5).map(|k| format!("guest{k}")))
    {
        let id = events.len() as i32 + 1;
        events.push(Event {
            id,
            x: id % 16,
            y: 1 + id / 16,
            pages: vec![page(&name)],
        });
    }
    let npcs = collect_npcs(&events, "chip", &vec![0u8; 65536]);
    let poses = map_poses(
        &leaders,
        &npcs,
        &BTreeSet::new(),
        &BTreeMap::new(),
        &[],
        &BTreeSet::new(),
    );
    let glyphs = glyphs();
    let timer = timer_colors(&glyphs);
    let only_here: HashSet<Key> = Default::default();
    let ask = Ask {
        sheets: &sheets,
        leaders: &leaders,
        cap: 8,
        route_graphics: &[],
        hero_graphics: &Default::default(),
        timer_colors: &timer,
        only_here: &only_here,
        poses: &poses,
        weights: &Default::default(),
    };
    let d = drawable_npcs(&ask, npcs).unwrap();
    let s = &d.split;
    assert_eq!(s.palettes.len(), 8);
    assert_eq!(s.leader_owned.len(), 3, "the leaders' palettes");
    assert_eq!(
        s.lent.len(),
        5,
        "a guest in each owner's palette: {:?}",
        s.lent
    );
    let hosts: BTreeSet<usize> = s
        .lent
        .iter()
        .map(|k| s.palette_of.get(k).unwrap())
        .collect();
    assert_eq!(hosts.len(), 5, "each guest in a palette of its own owner");

    assert!(d.notes.is_empty(), "nobody drops colours: {:?}", d.notes);
    assert!(s.caps.is_empty());
    let (mut tiles, mut palettes) = (Vec::new(), s.palettes.clone());
    let (_, palette) = timer_digits(
        &glyphs,
        &mut tiles,
        &mut palettes,
        &s.leader_owned,
        8,
        false,
    )
    .unwrap();
    assert_eq!(
        Some(palette),
        s.palette_of.get(&("owner3".to_string(), 0)),
        "the one with a red"
    );
    assert_eq!(palettes, s.palettes, "no palette grows");
}
