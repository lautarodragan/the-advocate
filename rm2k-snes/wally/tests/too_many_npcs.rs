//! `wally map` on a map with more drawn events than the console's table
//! holds: the ones that fit are drawn, and the rest lose their row —not
//! their event— with a WARNING.
//!
//! A small game is generated inside each test, as in `decorative.rs`: none
//! of this needs a game.

use rm2k_render::{picture, Picture};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;
use wally::sprites::npc::NPC_MAX;

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("wally-npcs-{}-{name}", std::process::id()));
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

fn page(name: &str, commands: Value) -> Value {
    json!({"id": 1, "character_name": name, "character_index": 0,
           "character_direction": 2, "character_pattern": 1, "layer": 1,
           "move_type": 0, "move_speed": 3, "animation_type": 0,
           "condition": {"flags": {"switch_a": false, "switch_b": false, "variable": false,
                                   "item": false, "actor": false, "timer": false}},
           "move_route": {"move_commands": []}, "event_commands": commands})
}

/// A map of 16x8 cells with `count` events, one per cell from the top left.
/// The first `doing` are Folk and each has a page with a command —the first
/// one's moves the last event—; the rest are Water and their page has
/// none, so they do nothing that is not seen. The last one is named.
fn game(dir: &Path, count: usize, doing: usize) -> (PathBuf, PathBuf) {
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
    let wait = json!([{"code": 11410, "indent": 0, "string": "", "parameters": [1]}]);
    let events: Vec<Value> = (1..=count)
        .map(|id| {
            let cell = id - 1;
            let p = if id == 1 {
                page(
                    "Folk",
                    json!([{"code": 11330, "indent": 0, "string": "", "parameters": [count, 0]}]),
                )
            } else if id <= doing {
                page("Folk", wait.clone())
            } else {
                page("Water", json!([]))
            };
            json!({"id": id, "x": cell % 16, "y": cell / 16, "pages": [p]})
        })
        .collect();
    std::fs::write(
        dump.join("maps/Map0007.json"),
        json!({"chipset_id": 2, "width": 16, "height": 8, "events": events}).to_string(),
    )
    .unwrap();
    let lower: Vec<String> = (0..8).map(|_| ["  5000"; 16].concat()).collect();
    let upper: Vec<String> = (0..8).map(|_| [" 10000"; 16].concat()).collect();
    std::fs::write(
        dump.join("maps/Map0007.tiles"),
        format!(
            "# 16x8\n# lower\n{}\n# upper\n{}\n",
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
        let k = (x / 6 + y / 4 * 3) % 9;
        [
            (k * 40 % 256) as u8,
            (k * 90 % 256) as u8,
            (k * 150 % 256) as u8,
            255,
        ]
    });
    write(&pictures.join("CharSet/Water.png"), 288, 256, |x, y| {
        let (px, py) = (x % 24, y % 32);
        if !(4..20).contains(&px) || py < 16 {
            return [0, 0, 0, 0];
        }
        [10, 200, 60, 255]
    });
    (dump, pictures)
}

fn convert(dir: &Path, dump: &Path, pictures: &Path) -> Value {
    convert_with(dir, dump, pictures, json!({}))
}

/// The same, with the fields of `extra` over the request's.
fn convert_with(dir: &Path, dump: &Path, pictures: &Path, extra: Value) -> Value {
    let request = dir.join("request.json");
    let mut body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": false, "leaders": [1], "pages": [],
        "route_graphics": [], "also_walk": [],
        "timer": null, "rain": false, "picture": null,
        "battle_animation": false, "singles": [], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        "layouts": [], "window_colors": 13,
    });
    for (k, v) in extra.as_object().unwrap() {
        body[k] = v.clone();
    }
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
    serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap()
}

fn events(map: &Value) -> Vec<i64> {
    let mut out: Vec<i64> = map["npcs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["event"].as_i64().unwrap())
        .collect();
    out.sort();
    out
}

fn notes(map: &Value) -> Vec<String> {
    map["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap().to_string())
        .collect()
}

#[test]
fn a_map_that_fits_keeps_every_row_and_says_nothing() {
    let dir = scratch("fits");
    let (dump, pictures) = game(&dir, NPC_MAX, NPC_MAX - 10);
    let map = convert(&dir, &dump, &pictures);
    assert_eq!(events(&map), (0..NPC_MAX as i64).collect::<Vec<_>>());
    assert!(
        !notes(&map).iter().any(|n| n.contains("table holds")),
        "{:?}",
        notes(&map)
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn the_ones_that_do_nothing_go_first_and_the_highest_first() {
    // Six over: the Water ones are the ten before the last —the last is
    // named— and of those the six with the highest id lose their row.
    let count = NPC_MAX + 6;
    let doing = count - 11;
    let dir = scratch("over");
    let (dump, pictures) = game(&dir, count, doing);
    let map = convert(&dir, &dump, &pictures);
    // By index: event id n is index n - 1, and the last one is count - 1.
    let dropped: Vec<i64> = ((count - 7) as i64..(count - 1) as i64).collect();
    let kept: Vec<i64> = (0..count as i64).filter(|e| !dropped.contains(e)).collect();
    assert_eq!(events(&map), kept);
    let notes = notes(&map);
    let ids: Vec<String> = dropped.iter().map(|e| (e + 1).to_string()).collect();
    assert!(
        notes
            .iter()
            .any(|n| n.contains("WARNING") && n.contains(&ids.join(", "))),
        "{notes:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn when_those_are_not_enough_the_highest_ids_go() {
    // Every event does something: the highest ids lose their row.
    let count = NPC_MAX + 3;
    let dir = scratch("all");
    let (dump, pictures) = game(&dir, count, count);
    let map = convert(&dir, &dump, &pictures);
    assert_eq!(events(&map), (0..NPC_MAX as i64).collect::<Vec<_>>());
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_dropped_event_is_not_in_the_map() {
    // The converter leaves event 2 out —it does not fit in the console's
    // RAM—: the map is read without it, so there are four rows and the
    // events after it are numbered one less. Its cell is the second.
    let dir = scratch("dropped");
    let (dump, pictures) = game(&dir, 5, 5);
    let map = convert_with(
        &dir,
        &dump,
        &pictures,
        json!({"dropped_events": {"7": [2]}}),
    );
    assert_eq!(events(&map), [0, 1, 2, 3]);
    let second = map["npcs"]
        .as_array()
        .unwrap()
        .iter()
        .find(|n| n["event"] == 1)
        .unwrap();
    assert_eq!(second["x"], json!(2), "{second}");
    std::fs::remove_dir_all(&dir).unwrap();
}
