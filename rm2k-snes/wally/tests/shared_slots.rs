//! `wally map` with still events taking turns in a slot: only when the map
//! fits none of the layouts it is given, only the still ones nobody moves,
//! and only those that no camera shows together.
//!
//! A small game is generated inside each test: a map 40 cells wide with
//! three still events of the same CharSet, each facing another way —two
//! at opposite ends, one next to the first—. None of this needs a game.

use rm2k_render::{picture, Picture};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("wally-shared-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn write(path: &Path, width: usize, height: usize, pixel: impl Fn(usize, usize) -> [u8; 4]) {
    let mut rgba = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        for x in 0..width {
            rgba.extend_from_slice(&pixel(x, y));
        }
    }
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    picture::write_png(
        path,
        &Picture {
            width,
            height,
            rgba,
        },
    )
    .unwrap();
}

/// A page facing `direction` (0 up, 1 right, 2 down, 3 left), with
/// `commands`.
fn page(direction: i32, commands: Value) -> Value {
    json!({"id": 1, "character_name": "Folk", "character_index": 0,
           "character_direction": direction, "character_pattern": 1, "layer": 1,
           "move_type": 0, "move_speed": 3, "animation_type": 0,
           "condition": {"flags": {"switch_a": false, "switch_b": false, "variable": false,
                                   "item": false, "actor": false, "timer": false}},
           "move_route": {"move_commands": []}, "event_commands": commands})
}

/// The game, with the third event's page running `commands`: its dump and
/// its pictures.
fn game(dir: &Path, commands: Value) -> (PathBuf, PathBuf) {
    let dump = dir.join("dump");
    std::fs::create_dir_all(dump.join("maps")).unwrap();
    std::fs::create_dir_all(dump.join("db")).unwrap();
    std::fs::write(
        dump.join("ditto.json"),
        json!({"ditto": 2, "view": "resolved"}).to_string(),
    )
    .unwrap();
    std::fs::write(
        dump.join("db/chipsets.json"),
        json!([{"id": 2, "chipset_name": "tiles", "passable_data_lower": vec![15u8; 162],
                "passable_data_upper": vec![15u8; 144]}])
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dump.join("db/actors.json"),
        json!([{"id": 1, "character_name": "Folk", "character_index": 1}]).to_string(),
    )
    .unwrap();
    std::fs::write(dump.join("db/commonevents.json"), "[]").unwrap();
    std::fs::write(
        dump.join("maps.json"),
        json!({"maps": [], "start": {"party_map_id": 9, "party_x": 1, "party_y": 1}}).to_string(),
    )
    .unwrap();
    // Two at the ends of the map, 29 cells apart: no camera shows both. The
    // third next to the first.
    let events = json!([
        {"id": 1, "x": 1, "y": 1, "pages": [page(2, json!([]))]},
        {"id": 2, "x": 30, "y": 1, "pages": [page(1, json!([]))]},
        {"id": 3, "x": 2, "y": 1, "pages": [page(3, commands)]},
    ]);
    std::fs::write(
        dump.join("maps/Map0007.json"),
        json!({"chipset_id": 2, "width": 40, "height": 4, "events": events}).to_string(),
    )
    .unwrap();
    let lower: Vec<String> = (0..4).map(|_| ["  5000"; 40].concat()).collect();
    let upper: Vec<String> = (0..4).map(|_| [" 10000"; 40].concat()).collect();
    std::fs::write(
        dump.join("maps/Map0007.tiles"),
        format!(
            "# 40x4\n# lower\n{}\n# upper\n{}\n",
            lower.join("\n"),
            upper.join("\n")
        ),
    )
    .unwrap();
    let pictures = dir.join("game");
    write(&pictures.join("ChipSet/tiles.png"), 480, 256, |x, y| {
        let k = (x / 8 + y / 8) % 5;
        [(k * 40) as u8, (k * 30) as u8, (200 - k * 30) as u8, 255]
    });
    write(&pictures.join("CharSet/Folk.png"), 288, 256, |x, y| {
        if (x * 3 + y * 5) % 7 == 0 {
            return [0, 0, 0, 0];
        }
        let k = (x / 6 + y / 4 * 3) % 9;
        [
            (k * 40 % 256) as u8,
            (k * 90 % 256) as u8,
            (k * 150 % 256) as u8,
            255,
        ]
    });
    (dump, pictures)
}

/// The map with these layouts: its answer.
fn convert(dir: &Path, dump: &Path, pictures: &Path, layouts: Value) -> Value {
    let request = dir.join("request.json");
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": false, "leaders": [1], "pages": [],
        "route_graphics": [], "also_walk": [],
        "timer": null, "rain": false, "picture": null,
        "battle_animation": false, "singles": [], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        "layouts": layouts, "window_colors": 13,
    });
    std::fs::write(&request, body.to_string()).unwrap();
    let out = dir.join("out");
    let _ = std::fs::remove_dir_all(&out);
    let done = Command::new(env!("CARGO_BIN_EXE_wally"))
        .args(["map", "--data"])
        .arg(dump)
        .arg("--search-dir")
        .arg(pictures)
        .arg("--request")
        .arg(&request)
        .arg("--out")
        .arg(&out)
        .output()
        .unwrap();
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let mut answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    answer["tiles"] = json!(std::fs::read(out.join("sprites.bin")).unwrap().len() / 32);
    answer
}

#[test]
fn far_apart_still_ones_take_turns_only_when_the_map_does_not_fit() {
    let dir = scratch("turns");
    let (dump, pictures) = game(&dir, json!([]));
    // With room, as always: the hero and a slot per pose.
    let plain = convert(&dir, &dump, &pictures, json!([]));
    assert_eq!(plain["sprite"]["shared"], Value::Null);
    assert_eq!(plain["sprite"]["place"].as_array().unwrap().len(), 4);
    let tiles = plain["tiles"].as_u64().unwrap();
    let fits = convert(&dir, &dump, &pictures, json!([[1000, tiles, 1000]]));
    assert_eq!(fits, plain);

    // A sprite tile short: the two at the ends take turns in one slot, and
    // the one next to the first keeps its own.
    let tight = convert(&dir, &dump, &pictures, json!([[1000, tiles - 1, 1000]]));
    let sprite = &tight["sprite"];
    let place = sprite["place"].as_array().unwrap();
    assert_eq!(place.len(), 3);
    assert_eq!(
        place[1][0],
        json!({"charset": "Folk", "index": 0, "pose": 10})
    );
    assert_eq!(place[2][0], json!({"shared": 0}));
    let shared = &sprite["shared"];
    // Each with its slot, its pose among the slot's and its palette.
    let palette = &place[2][2];
    assert_eq!(
        shared["events"],
        json!([[0, 0, 1, palette], [1, 0, 0, palette]])
    );
    // Their poses come from the cartridge's twelve of Folk:0, after the
    // leader's.
    assert_eq!(sprite["animated"], json!([["Folk", 1], ["Folk", 0]]));
    assert_eq!(shared["poses"], json!([[1, 4], [1, 7]]));
    assert_eq!(shared["slots"], json!([place[2][1]]));
    assert!(tight["tiles"].as_u64().unwrap() < tiles);
    let notes: Vec<&str> = tight["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap())
        .collect();
    assert!(
        notes.contains(
            &"  map 7: 2 still events take turns in 1 slots, never two of them on screen at once"
        ),
        "{notes:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn one_that_something_places_elsewhere_does_not_take_turns() {
    let dir = scratch("placed");
    // The third one's page places the second one: `SetEventLocation`.
    let (dump, pictures) = game(
        &dir,
        json!([{"code": 10860, "indent": 0, "string": "",
                                             "parameters": [2, 0, 5, 1]}]),
    );
    let plain = convert(&dir, &dump, &pictures, json!([]));
    let tiles = plain["tiles"].as_u64().unwrap();
    // Nobody is left to take turns with the first: it is not shared. What
    // goes is the cache, which does not care who is placed where.
    let tight = convert(&dir, &dump, &pictures, json!([[1000, tiles - 1, 1000]]));
    assert_eq!(tight["sprite"]["shared"], Value::Null);
    assert_ne!(tight["sprite"]["cache"], Value::Null);
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_map_that_does_not_fit_even_taking_turns_gets_a_cache() {
    let dir = scratch("cache");
    // The third one placed elsewhere: nobody takes turns, so only a cache
    // can make it fit.
    let (dump, pictures) = game(
        &dir,
        json!([{"code": 10860, "indent": 0, "string": "",
                                             "parameters": [2, 0, 5, 1]}]),
    );
    let plain = convert(&dir, &dump, &pictures, json!([]));
    let tiles = plain["tiles"].as_u64().unwrap();
    let tight = convert(&dir, &dump, &pictures, json!([[1000, tiles - 1, 1000]]));
    let sprite = &tight["sprite"];
    // The hero keeps block 0; the cache gets as many blank blocks as fit
    // —two, of the three still poses— and nobody else has one.
    let place = sprite["place"].as_array().unwrap();
    assert_eq!(place.len(), 3);
    assert_eq!(place[0][0], json!({"hero": true}));
    assert_eq!(place[1][0], json!({"cache": 0}));
    assert_eq!(place[2][0], json!({"cache": 1}));
    let cache = &sprite["cache"];
    assert_eq!(cache["slots"], json!([1, 2]));
    // The still poses, sorted, with their character's twelve in the
    // cartridge —after the leader's— and its palette.
    let palette = &cache["stills"][0][4];
    assert_eq!(
        cache["stills"],
        json!([
            ["Folk", 0, 4, 1, palette],
            ["Folk", 0, 7, 1, palette],
            ["Folk", 0, 10, 1, palette]
        ])
    );
    assert_eq!(sprite["animated"], json!([["Folk", 1], ["Folk", 0]]));
    // Each event starts asking for its own pose.
    assert_eq!(
        cache["events"],
        json!([[0, 1, palette], [1, 0, palette], [2, 2, palette]])
    );
    // The second one is 29 cells from the other two: no camera shows the
    // three, so two slots are enough and nothing warns.
    let notes: Vec<&str> = tight["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap())
        .collect();
    assert_eq!(
        notes,
        ["  map 7: 3 events take a slot of a cache of 2 when they come into view, 3 still poses among \
          them; by where they start, up to 2 are on screen at once"]
    );
    // With room for the hero and a single slot, the cache still goes, and
    // says that two can be on screen at once.
    let one = convert(&dir, &dump, &pictures, json!([[1000, 56, 1000]]));
    assert_eq!(one["sprite"]["cache"]["slots"], json!([1]));
    assert!(one["notes"].as_array().unwrap().iter().any(|n| n["text"]
        .as_str()
        .unwrap()
        .contains("WARNING, by where they start up to 2 events are on screen at once and the cache has 1 slots")));
    // And without room for even one, the map goes as always: it does not
    // fit, and the emission says so.
    let none = convert(&dir, &dump, &pictures, json!([[1000, 55, 1000]]));
    assert_eq!(none, plain);
    std::fs::remove_dir_all(&dir).unwrap();
}
