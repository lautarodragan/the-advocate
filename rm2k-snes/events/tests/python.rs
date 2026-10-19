//! The compiler against the one it replaces.
//!
//! Until 2026-09-29 the event compiler was the converter's Python
//! (`events.py`). It was deleted once both gave the same bytes on every page
//! of every cartridge of a whole game; what is left of it is here: a small
//! game in `tests/game/`, the two requests a caller would send for it
//! —`scan.json` and `compile.json`—, and in `python.json` the SHA-256 of each
//! part of what the Python answered for them, written in this crate's shape.
//! It needs no real game.
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
//! **If one of these changes, a byte of a cartridge changed.** The hashes
//! are not to be regenerated to make a test pass: the Python that produced
//! them is gone, and with it the only independent answer.
//!
//! On 2026-10-02 the speaker of the rebuilt box, a character of the game
//! this was built for, became an invented one of the same length, and the
//! hash of `messages` moved with it: the new answer, with the old name put
//! back in the console's text encoding, is the Python's byte for byte. The
//! comparison is still against the Python, renamed.
//!
//! On 2026-10-03 it moved again, on purpose: a `ShowChoice`'s options the
//! cursor is not on start with the cursor's blank —glyph 95, as wide as the
//! `>`— and not with a space, because the font got variable width and a
//! space is narrower. The choice's boxes are the only bytes that changed:
//! with `CHOICE_INDENT` back at a space, the answer was the old one.
//!
//! On 2026-10-04 the hash of `maps` moved, on purpose too: `MessageOptions`
//! compiles to `OP_MESSAGE_OPTIONS` and the Python dropped it. With its arm
//! answering no bytes, the answer was the old one.
//!
//! And the same day the hashes of `maps`, of the scan and of the
//! compilation, and the compilation's `messages`, moved on purpose: a
//! `ShowChoice`'s options are a single box without the `>`, because the
//! console draws the System's bar under the highlighted one. With
//! `choice_boxes` writing one box per option with the `>` again, the answer
//! was the old one.
//!
//! And the same day the hashes of `maps` and `cases` moved again, on
//! purpose: a battle with `escape_mode` 0 carries `BATTLE_NO_ESCAPE` where
//! its escape goes, so the ROM leaves Escape out. With
//! `BATTLE_NO_ESCAPE_MODE` set to one no battle has, the answer was the
//! old one.
//!
//! On 2026-10-05 the hashes of `maps`, of the scan and of the compilation,
//! moved on purpose: a touch page on the hero's layer —event 4 of map 1,
//! its second page— compiles, because RM2k fires it from the cell in front.
//! The Python left it without code, and that change, which only removed the
//! layer test, is the whole difference.
//!
//! And the same day the hash of the compilation's `maps` moved again, on
//! purpose: `ChangePBG` compiles to `OP_PANORAMA`, and the Python dropped
//! it. With its arm answering no bytes, the answer was the old one.
//!
//! On 2026-10-12 the hashes of the compilation's `maps`, `cases` and
//! `troop_pages` moved, on purpose: `OP_BATTLE` carries a fourth
//! destination, where a battle a troop page ended with `TerminateBattle`
//! goes on, and a troop page can `Wait`, so the test game's one that waits
//! compiles. With the fourth word taken out —of the declaration and of both
//! places that write it— and `Wait` out of `TROOP_COMMANDS`, the answer was
//! the old one.
//!
//! And the same day the hash of the compilation's `maps` moved, on
//! purpose: the equipment common event is no longer pasted after the
//! `ControlSwitches` that turns it on —the ROM runs every parallel common
//! event on its own, see `commons::parallel_commons`—. With the pasting put
//! back, the answer's `maps` was the old one. And `party_common_events` left
//! both answers: which ones only look at the equipment is
//! `commons::pure`, in `parallel_commons`.
//!
//! On 2026-10-15 the hashes of the compilation's `maps` and `messages` and
//! of the scan's `maps` moved, on purpose: a `Teleport` to a map the
//! cartridge does not carry —the one "out of the cartridge"— compiles to a
//! message box saying so, and the page goes on, where the Python left the
//! page out. With the arm answering `cannot()` again, the answer was the
//! old one.
//!
//! And the same day the hash of the compilation's `maps` moved, on
//! purpose: a `CallEvent` to a map event's page from a page that runs in
//! the foreground compiles to `OP_CALL_PAGE` with the page's index in the
//! table, and the Python pasted the page in place. With the call compiled
//! as a paste again —`compile_call`'s `if me.stack && !me.jumped` never
//! taken— the answer was the old one.
//!
//! On 2026-10-17 the hashes of the compilation's `maps` and the scan's
//! `maps` moved again, on purpose: that box comes after a `ShowScreen` with
//! the cut, so it is not up in the black of an erased screen. Without those
//! two bytes in `compile_missing_teleport` the answer was the one before.
//!
//! On 2026-10-19 the hash of the compilation's `maps` moved again, on
//! purpose: `OP_PANORAMA` carries the picture a `ChangePBG` swaps in, $FF
//! for the one there is, which every `ChangePBG` here keeps. Without that
//! byte the answer was the one before.
//!
//! And the same day the hash of the compilation's `maps` moved again, on
//! purpose: both inns of the test game stage the night —the fades, the
//! song noted and put back, the heal in the black—, which is RM2k's
//! `Scene_Map::CallInn`. With `inn_staging` answering the heal alone, the
//! answer was the one before. And again, on purpose: a paid inn opens with
//! `OP_INN 3`, a gold branch and `OP_INN 4` —its gold window and its greyed
//! "Yes"—. Without those eleven bytes in front of the greeting, and the
//! choice's and the branch's destinations eleven back, the answer was the
//! one before.

use rm2k_snes_events::{compile, compile_without_pairs, scan, Game, Request};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn read(name: &str) -> Value {
    let path = here().join(name);
    serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap()
}

/// A value with its objects' keys sorted, as Python's `json.dumps(...,
/// sort_keys=True, separators=(",", ":"), ensure_ascii=False)` writes it,
/// whatever order the map keeps.
fn canonical(v: &Value) -> String {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            let fields: Vec<String> = keys
                .iter()
                .map(|k| format!("{}:{}", Value::String((*k).clone()), canonical(&m[*k])))
                .collect();
            format!("{{{}}}", fields.join(","))
        }
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(canonical).collect::<Vec<_>>().join(",")
        ),
        other => other.to_string(),
    }
}

fn sha256(v: &Value) -> String {
    Sha256::digest(canonical(v).as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// The songs a package's jumps can carry are a set on the Python side: they
/// are compared sorted, with "whatever is playing" first.
fn sorted_jumps(answer: &mut Value) {
    let Some(jumps) = answer
        .pointer_mut("/songs/jumps")
        .and_then(Value::as_array_mut)
    else {
        return;
    };
    for package in jumps {
        for dest in package[1].as_array_mut().unwrap() {
            dest[1]
                .as_array_mut()
                .unwrap()
                .sort_by_key(|s| s.as_i64().unwrap_or(-1));
        }
    }
}

/// `route_targets` came into the page records after the Python was gone,
/// so it is not in its hashes: it is taken out here and has a test of its
/// own, `route_targets_are_the_routes_of_the_code`.
fn without_route_targets(answer: &mut Value) {
    let Some(maps) = answer.get_mut("maps").and_then(Value::as_array_mut) else {
        return;
    };
    for map in maps {
        for page in map["pages"].as_array_mut().into_iter().flatten() {
            page.as_object_mut().unwrap().remove("route_targets");
            // And whether a parallel page is pure, which came on
            // 2026-10-17: see `commons::pure_page` and its tests.
            page.as_object_mut().unwrap().remove("pure");
        }
    }
}

/// The pictures each map can show, which the scan gathers since 2026-10-01,
/// came after the Python too: taken out here, and checked on their own by
/// `the_scan_gathers_the_pictures`. And so did what its moves zoom to, since
/// 2026-10-03.
fn without_pictures(answer: &mut Value) {
    let Some(maps) = answer.get_mut("maps").and_then(Value::as_array_mut) else {
        return;
    };
    for map in maps {
        if let Some(m) = map.as_object_mut() {
            m.remove("pictures");
            m.remove("zooms");
            // Which numbers are toned came on 2026-10-16.
            m.remove("tinted");
            // Which graphics a route gives an event came on 2026-10-11.
            m.remove("graphics_on_events");
        }
    }
}

/// The text block's pair table came after the Python too: the answer
/// compared is the one without pairs, and the two fields that say which
/// table it was written with —an empty one— are taken out. That the pairs
/// write the same text is `the_pairs_write_the_same_boxes`.
fn without_pairs(answer: &mut Value) {
    // And the parallel common events, which came on 2026-10-12: see
    // `the_parallel_common_events_come_compiled`.
    if let Some(m) = answer.as_object_mut() {
        m.remove("parallel_commons");
        // And the highest switch the game names, which came on 2026-10-15:
        // see `the_scan_says_the_highest_switch`.
        m.remove("switch_top");
        // And what the cartridge does with less than RM2k, which came on
        // 2026-10-15 and is no byte of a cartridge: see
        // `the_compilation_says_what_it_degrades`.
        m.remove("degradations");
        // And the names `ChangeHeroName` gives, which came on 2026-10-15:
        // see `a_rename_is_the_actors_place_and_the_names` in `compile.rs`.
        m.remove("names");
        // And the faces the message window shows, which came on 2026-10-15:
        // see `change_face_graphic_is_its_face_and_side` in `compile.rs`.
        m.remove("faces");
    }
    if let Some(m) = answer.get_mut("messages").and_then(Value::as_object_mut) {
        m.remove("pairs");
        m.remove("pair_first");
        // And the Latin-1 letters the boxes draw, which came on 2026-10-16:
        // none here, the game's text is ASCII.
        if let Some(letters) = m.remove("letters") {
            assert_eq!(letters, serde_json::json!([]));
        }
    }
}

fn check(which: &str, answer: Value) {
    let mut answer = answer;
    sorted_jumps(&mut answer);
    without_route_targets(&mut answer);
    without_pictures(&mut answer);
    without_pairs(&mut answer);
    let expected = read("python.json");
    let expected = expected[which].as_object().unwrap();
    let got = answer.as_object().unwrap();
    let mut keys: Vec<&String> = got.keys().collect();
    keys.sort();
    assert_eq!(
        keys,
        expected.keys().collect::<Vec<_>>(),
        "the parts of the answer"
    );
    for (part, hash) in expected {
        assert_eq!(
            sha256(&got[part]),
            hash.as_str().unwrap(),
            "{which}: {part}"
        );
    }
}

/// The parallel common events: the test game has one, 2, `Equipment`,
/// parallel on switch 40, which only looks at the equipment —it is pure—,
/// and it comes compiled, with its switch and its flag.
#[test]
fn the_parallel_common_events_come_compiled() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    let answer = compile(&game(&request), &request).unwrap();
    let parallel = answer["parallel_commons"].as_array().unwrap();
    assert_eq!(parallel.len(), 1);
    assert_eq!(parallel[0][0], 2);
    assert_eq!(parallel[0][1], 40);
    assert_eq!(parallel[0][2], true);
    assert!(
        parallel[0][3].is_string(),
        "it does not compile: {parallel:?}"
    );
}

/// Who each page sends walking. The answer was checked against the
/// converter's Python rule, `events.route_targets`, before it was deleted:
/// map 1's first page routes the hero and events 1 and 3 —the hero is not
/// an event and does not count—, and the test page on map 3, which the
/// request puts first, sends event 0.
#[test]
fn route_targets_are_the_routes_of_the_code() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let answer = scan(&game(&request), &request).unwrap();
    let mut routed = Vec::new();
    for map in answer["maps"].as_array().unwrap() {
        for page in map["pages"].as_array().unwrap() {
            let targets = page["route_targets"].as_array().unwrap();
            if page["code"].is_null() {
                assert!(targets.is_empty(), "a page without code routes nobody");
            }
            if !targets.is_empty() {
                routed.push((
                    map["id"].clone(),
                    page["event"].clone(),
                    page["page"].clone(),
                    targets.clone(),
                ));
            }
        }
    }
    let expected: Vec<(Value, Value, Value, Vec<Value>)> = vec![
        (1.into(), 1.into(), 0.into(), vec![1.into(), 3.into()]),
        (3.into(), 0.into(), 0.into(), vec![0.into()]),
    ];
    assert_eq!(routed, expected);
}

/// What the scan gathers of each map's pictures: map 1 shows `Pic` and
/// `Other`, in the order its page shows them, and map 2 `Other` again —each
/// map carries its own—. Only `ShowPicture` gathers: the move and the erase
/// say a number and nothing else.
#[test]
fn the_scan_gathers_the_pictures() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let answer = scan(&game(&request), &request).unwrap();
    let names: Vec<(i64, Vec<&str>)> = answer["maps"]
        .as_array()
        .unwrap()
        .iter()
        .map(|m| {
            (
                m["id"].as_i64().unwrap(),
                m["pictures"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|p| p["name"].as_str().unwrap())
                    .collect::<Vec<_>>(),
            )
        })
        .filter(|(_, p)| !p.is_empty())
        .collect();
    assert_eq!(names, vec![(1, vec!["Pic", "Other"]), (2, vec!["Other"])]);
    let pic = &answer["maps"][0]["pictures"][0];
    assert_eq!(pic["at"], serde_json::json!([160, 120]));
    assert_eq!(pic["number"], 1);
}

fn game(request: &Request) -> Game {
    Game::from_dump(&here().join("game"), request.patches.clone()).unwrap()
}

/// The highest switch the game names, which the cartridge's table holds:
/// the test game names none past the harness's `TEST_SWITCH`, 1023, which
/// the request carries in `extra_switches`; without it, its own highest.
#[test]
fn the_scan_says_the_highest_switch() {
    let mut request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    let g = game(&request);
    assert_eq!(scan(&g, &request).unwrap()["switch_top"], 1023);
    request.extra_switches.clear();
    let own = scan(&g, &request).unwrap()["switch_top"].as_i64().unwrap();
    assert!((1..1023).contains(&own), "{own}");
}

#[test]
fn the_scan_is_the_pythons() {
    let request = Request::from_json(&read("scan.json"), "scan.json").unwrap();
    check("scan", scan(&game(&request), &request).unwrap());
}

#[test]
fn the_compilation_is_the_pythons() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    check(
        "compile",
        compile_without_pairs(&game(&request), &request).unwrap(),
    );
}

/// The boxes of a text block, in order and as letters: each one at a
/// multiple of `step`, its header, and each line with its length in
/// letters, a byte from `pair_first` up being two of them.
fn boxes(messages: &Value, step: usize) -> Vec<(u8, Vec<Vec<u8>>)> {
    let bytes = |key: &str| -> Vec<u8> {
        let hex = messages[key].as_str().unwrap();
        (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect()
    };
    let (data, pairs) = (bytes("data"), bytes("pairs"));
    let first = messages["pair_first"].as_u64().unwrap() as u8;
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
    let (a, b) = (
        boxes(&plain["messages"], step),
        boxes(&paired["messages"], step),
    );
    assert!(!a.is_empty());
    assert_eq!(a, b);
    let size = |v: &Value| v["messages"]["data"].as_str().unwrap().len();
    assert!(size(&paired) < size(&plain));
    assert_eq!(paired["messages"]["count"], plain["messages"]["count"]);
}

/// What the cartridge does with less than RM2k, each where it is: a map's
/// page with its event's cell, a whole event left out, and a troop's page.
/// The test game has one of each of these.
#[test]
fn the_compilation_says_what_it_degrades() {
    let request = Request::from_json(&read("compile.json"), "compile.json").unwrap();
    let answer = compile(&game(&request), &request).unwrap();
    let losses = answer["degradations"]["losses"].as_array().unwrap();
    let find = |kind: &str| {
        losses
            .iter()
            .find(|l| l["kind"] == kind)
            .unwrap_or_else(|| panic!("no {kind}"))
    };
    let teleport = find("teleport-to-missing-map");
    assert_eq!(
        [
            &teleport["map"],
            &teleport["event"],
            &teleport["page"],
            &teleport["command"],
            &teleport["name"]
        ],
        [
            &json!(2),
            &json!(1),
            &json!(2),
            &json!(1),
            &json!("Teleport")
        ]
    );
    let left_out = find("event-left-out");
    assert_eq!(
        [&left_out["map"], &left_out["event"], &left_out["page"]],
        [&json!(1), &json!(8), &Value::Null]
    );
    let troop = losses
        .iter()
        .find(|l| l.get("troop").is_some())
        .expect("a troop page's loss");
    assert_eq!(
        [&troop["page"], &troop["command"], &troop["name"]],
        [&json!(1), &json!(2), &json!("PlaySound")]
    );
}
