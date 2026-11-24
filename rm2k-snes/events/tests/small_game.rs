//! What the scan and the compilation answer for a small game, in
//! `tests/game/`, with the two requests a caller would send for it
//! —`scan.json` and `compile.json`—. It needs no real game.
//!
//! The game is built to touch as many paths as it can: text boxes with
//! escape tails and one the project rebuilt; choices; the five kinds of
//! branch and the actor's three questions, nested; every `ControlVars` it
//! compiles and the fused "is it on the cell?"; forced routes on the hero
//! and on an event, with sounds, graphics, jumps and diagonals; a battle
//! with its handlers and one without, that loses to a Game Over; both inns;
//! a toggle; calls to a common event, to a map event, to one that does not
//! compile; the picture that took the place and one that did not; a
//! translucent page the project renamed; a page with a condition the ROM
//! cannot evaluate; an automatic page that compiles to nothing; a teleport
//! out of the cartridge; the sound effects decided per map; troop pages
//! with every trigger, one of them shared by two troops; and two test
//! pages, on two maps.
//!
//!
//! **The paths they guard**: what each answer carries beyond the
//! cartridge's bytes —who a page routes, which pictures a map shows, the
//! highest switch, the parallel common events, the pair table, what is
//! degraded—, on edges a game's pages may not have. The bytes themselves
//! are checked by running them: A Blurred Line's suite and the test game
//! compile every page they have and play them on the console.

use rm2k_snes_events::answer::Messages;
use rm2k_snes_events::losses::EVENT_LEFT_OUT;
use rm2k_snes_events::{compile, compile_without_pairs, scan, Game, Request};
use serde_json::Value;
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn read(name: &str) -> Value {
    let path = here().join(name);
    serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap()
}

/// The parallel common events: the small game has one, 2, `Equipment`,
/// parallel on switch 40, which only looks at the equipment —it is pure—,
/// and it comes compiled, with its switch and its flag.
#[test]
fn the_parallel_common_events_come_compiled() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    let answer = compile(&game(&request), &request).unwrap();
    let parallel = &answer.parallel_commons;
    assert_eq!(parallel.len(), 1);
    assert_eq!(parallel[0].0, 2);
    assert_eq!(parallel[0].1, 40);
    assert!(parallel[0].2);
    assert!(parallel[0].3.is_some(), "it does not compile: {parallel:?}");
}

/// Who each page sends walking: map 1's first page routes the hero and events 1 and 3 —the hero is not
/// an event and does not count—, and the test page on map 3, which the
/// request puts first, sends event 0.
#[test]
fn route_targets_are_the_routes_of_the_code() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let answer = scan(&game(&request), &request).unwrap();
    let mut routed = Vec::new();
    for map in &answer.maps {
        for page in &map.pages {
            let targets = &page.route_targets;
            if page.code.is_none() {
                assert!(targets.is_empty(), "a page without code routes nobody");
            }
            if !targets.is_empty() {
                routed.push((map.id, page.event, page.page, targets.clone()));
            }
        }
    }
    assert_eq!(routed, vec![(1, 1, 0, vec![1, 3]), (3, 0, 0, vec![0])]);
}

/// What the scan gathers of each map's pictures: map 1 shows `Pic` and
/// `Other`, in the order its page shows them, and map 2 `Other` again —each
/// map carries its own—. Only `ShowPicture` gathers: the move and the erase
/// say a number and nothing else.
#[test]
fn the_scan_gathers_the_pictures() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let answer = scan(&game(&request), &request).unwrap();
    let names: Vec<(i32, Vec<&str>)> = answer
        .maps
        .iter()
        .map(|m| {
            let names = m.pictures.iter().map(|p| p.name.as_str());
            (m.id, names.collect::<Vec<_>>())
        })
        .filter(|(_, p)| !p.is_empty())
        .collect();
    assert_eq!(names, vec![(1, vec!["Pic", "Other"]), (2, vec!["Other"])]);
    let pic = &answer.maps[0].pictures[0];
    assert_eq!(pic.at, Some((160, 120)));
    assert_eq!(pic.number, 1);
}

fn game(request: &Request) -> Game {
    Game::from_dump(&here().join("game"), request.patches.clone()).unwrap()
}

/// The highest switch the game names, which the cartridge's table holds:
/// the small game names none past the harness's `TEST_SWITCH`, 1023, which
/// the request carries in `extra_switches`; without it, its own highest.
#[test]
fn the_scan_says_the_highest_switch() {
    let mut request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let g = game(&request);
    assert_eq!(scan(&g, &request).unwrap().indices.switch_top, 1023);
    request.extra_switches.clear();
    let own = scan(&g, &request).unwrap().indices.switch_top;
    assert!((1..1023).contains(&own), "{own}");
    // Asked which switch the test pages can turn on, 1023, which this game
    // does not name: that one, and the table holds it.
    request.test_switch = Some(1023);
    let answer = scan(&g, &request).unwrap().indices;
    assert_eq!(answer.test_switch, Some(1023));
    assert_eq!(answer.switch_top, 1023);
}

/// The boxes of a text block, in order and as letters: each one at a
/// multiple of `step`, its header, and each line with its length in
/// letters, a byte from `pair_first` up being two of them.
fn boxes(messages: &Messages, step: usize) -> Vec<(u8, Vec<Vec<u8>>)> {
    let (data, pairs) = (&messages.data.0, &messages.pairs.0);
    let first = messages.pair_first;
    let mut out = Vec::new();
    let mut at = 0;
    while at < data.len() {
        let header = data[at];
        at += 1;
        let mut lines = Vec::new();
        for _ in 0..header & 7 {
            let n = data[at] as usize;
            at += 1;
            let mut line = Vec::new();
            while line.len() < n {
                let b = data[at];
                at += 1;
                if b >= first {
                    let k = 2 * (b - first) as usize;
                    line.extend([pairs[k], pairs[k + 1]]);
                } else {
                    line.push(b);
                }
            }
            assert_eq!(line.len(), n, "a pair crossed the end of a line");
            lines.push(line);
        }
        out.push((header, lines));
        while at % step != 0 && at < data.len() {
            assert_eq!(data[at], 0, "the padding between boxes");
            at += 1;
        }
    }
    out
}

/// With pairs, the same boxes in the same order, and in fewer bytes: the
/// offsets in the code change, the text does not.
#[test]
fn the_pairs_write_the_same_boxes() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    let plain = compile_without_pairs(&game(&request), &request).unwrap();
    let paired = compile(&game(&request), &request).unwrap();
    let step = request.messages_step;
    let (plain, paired) = (plain.messages, paired.messages);
    let (a, b) = (boxes(&plain, step), boxes(&paired, step));
    assert!(!a.is_empty());
    assert_eq!(a, b);
    assert!(paired.data.0.len() < plain.data.0.len());
    assert_eq!(paired.count, plain.count);
}

/// What the cartridge does with less than RM2k, each where it is: a map's
/// page with its event's cell, a whole event left out, and a troop's page.
/// The small game has one of each of these.
#[test]
fn the_compilation_says_what_it_degrades() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    let answer = compile(&game(&request), &request).unwrap();
    let losses = &answer.degradations.losses;
    let find = |kind: &str| {
        losses
            .iter()
            .find(|l| l.kind == kind)
            .unwrap_or_else(|| panic!("no {kind}"))
    };
    let teleport = find("teleport-to-missing-map");
    let p = &teleport.place;
    assert_eq!(
        (p.map, p.event, p.page, p.command, teleport.name.as_deref()),
        (
            Some(2),
            Some(1),
            Some(Some(2)),
            Some(Some(1)),
            Some("Teleport")
        )
    );
    let left_out = find(EVENT_LEFT_OUT);
    let p = &left_out.place;
    assert_eq!((p.map, p.event, p.page), (Some(1), Some(8), Some(None)));
    let troop = losses
        .iter()
        .find(|l| l.place.troop.is_some())
        .expect("a troop page's loss");
    assert_eq!(
        (troop.place.page, troop.place.command, troop.name.as_deref()),
        (Some(Some(1)), Some(Some(2)), Some("PlaySound"))
    );
}
