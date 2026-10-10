//! `wally map` with `decorative` on: an event that is pure decoration —one
//! page, no commands, no conditions, nobody names it, it does not move—
//! is painted into the background and stops being an event.
//!
//! A small game is generated inside each test, as in `shared_slots.rs`:
//! none of this needs a game.

use rm2k_render::{picture, Picture};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("wally-decor-{}-{name}", std::process::id()));
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
    picture::write_png(path, &Picture { width, height, rgba }).unwrap();
}

fn page(name: &str, layer: i32, animation: i32, commands: Value) -> Value {
    json!({"id": 1, "character_name": name, "character_index": 0,
           "character_direction": 2, "character_pattern": 1, "layer": layer,
           "move_type": 0, "move_speed": 3, "animation_type": animation,
           "condition": {"flags": {"switch_a": false, "switch_b": false, "variable": false,
                                   "item": false, "actor": false, "timer": false}},
           "move_route": {"move_commands": []}, "event_commands": commands})
}

/// A map 8 cells wide and 3 high with six events, in a row at y = 1:
///
/// * id 1, x 4: Water, below the hero, animated: decorative;
/// * id 2, x 5: Water, with the hero, still: decorative, and it blocks;
/// * id 3, x 1: Folk, with the hero, and its pose spills out of its cell:
///   stays an object;
/// * id 4, x 2: Folk, and its page has a command: an object, and it names
///   id 5;
/// * id 5, x 6: Water, still and with the hero, but named: an object;
/// * id 6, x 7: Water, but with a condition: an object.
fn game(dir: &Path) -> (PathBuf, PathBuf) {
    let dump = dir.join("dump");
    std::fs::create_dir_all(dump.join("maps")).unwrap();
    std::fs::create_dir_all(dump.join("db")).unwrap();
    std::fs::write(dump.join("ditto.json"), json!({"ditto": 2, "view": "resolved"}).to_string()).unwrap();
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
    let mut conditioned = page("Water", 1, 0, json!([]));
    conditioned["condition"]["flags"]["switch_a"] = json!(true);
    let events = json!([
        {"id": 1, "x": 4, "y": 1, "pages": [page("Water", 0, 1, json!([]))]},
        {"id": 2, "x": 5, "y": 1, "pages": [page("Water", 1, 0, json!([]))]},
        {"id": 3, "x": 1, "y": 1, "pages": [page("Folk", 1, 0, json!([]))]},
        {"id": 4, "x": 2, "y": 1, "pages": [page("Folk", 1, 0, json!([
            {"code": 11330, "indent": 0, "string": "", "parameters": [5, 0]}]))]},
        {"id": 5, "x": 6, "y": 1, "pages": [page("Water", 1, 0, json!([]))]},
        {"id": 6, "x": 7, "y": 1, "pages": [conditioned]},
    ]);
    std::fs::write(
        dump.join("maps/Map0007.json"),
        json!({"chipset_id": 2, "width": 8, "height": 3, "events": events}).to_string(),
    )
    .unwrap();
    let lower: Vec<String> = (0..3).map(|_| ["  5000"; 8].concat()).collect();
    let upper: Vec<String> = (0..3).map(|_| [" 10000"; 8].concat()).collect();
    std::fs::write(
        dump.join("maps/Map0007.tiles"),
        format!("# 8x3\n# lower\n{}\n# upper\n{}\n", lower.join("\n"), upper.join("\n")),
    )
    .unwrap();
    let pictures = dir.join("game");
    write(&pictures.join("ChipSet/tiles.png"), 480, 256, |x, y| {
        let k = (x / 8 + y / 8) % 5;
        [(k * 40) as u8, (k * 30) as u8, (200 - k * 30) as u8, 255]
    });
    // Folk fills every pose, edge to edge. Water draws only the 16x16 where
    // the cell is, in a colour for each column.
    write(&pictures.join("CharSet/Folk.png"), 288, 256, |x, y| {
        let k = (x / 6 + y / 4 * 3) % 9;
        [(k * 40 % 256) as u8, (k * 90 % 256) as u8, (k * 150 % 256) as u8, 255]
    });
    write(&pictures.join("CharSet/Water.png"), 288, 256, |x, y| {
        let (px, py) = (x % 24, y % 32);
        if !(4..20).contains(&px) || py < 16 {
            return [0, 0, 0, 0];
        }
        let column = ((x % 72) / 24) as u8;
        [10 + 90 * column, 200 - 70 * column, 60 + 60 * column, 255]
    });
    (dump, pictures)
}

fn convert(dir: &Path, dump: &Path, pictures: &Path, decorative: Option<bool>) -> (Value, Value) {
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
    if let Some(on) = decorative {
        body["decorative"] = json!(on);
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
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let map: Value = serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let layers: Value = serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    (map, layers)
}

fn events(map: &Value) -> Vec<i64> {
    map["npcs"].as_array().unwrap().iter().map(|n| n["event"].as_i64().unwrap()).collect()
}

#[test]
fn off_by_default_nothing_changes() {
    let dir = scratch("off");
    let (dump, pictures) = game(&dir);
    let (plain, _) = convert(&dir, &dump, &pictures, None);
    let (off, _) = convert(&dir, &dump, &pictures, Some(false));
    assert_eq!(plain, off);
    assert_eq!(plain["decorative"], json!([]));
    assert_eq!(events(&plain).len(), 6);
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn decoration_goes_into_the_background_and_the_hero_one_still_blocks() {
    let dir = scratch("on");
    let (dump, pictures) = game(&dir);
    let (plain, plain_layers) = convert(&dir, &dump, &pictures, None);
    let (map, layers) = convert(&dir, &dump, &pictures, Some(true));
    // Ids 1 and 2, by index. The others keep their rows.
    assert_eq!(map["decorative"], json!([0, 1]));
    assert_eq!(events(&map), vec![2, 3, 4, 5]);
    // The one with the hero blocks its cell, which the grid now says; the
    // one below him does not.
    let pass = |l: &Value, x: usize| l["passability"][8 + x].as_i64().unwrap();
    assert_eq!(pass(&plain_layers, 5), 15);
    assert_eq!(pass(&layers, 5), 0);
    assert_eq!(pass(&layers, 4), 15);
    // Its three columns animate like the water of a ChipSet: a run of the
    // water family with three drawings, and none without it.
    assert_eq!(plain_layers["background"]["runs"], json!([]));
    let runs = layers["background"]["runs"].as_array().unwrap();
    assert_eq!(runs.len(), 1, "{runs:?}");
    assert_eq!(runs[0]["family"], "water");
    assert_eq!(runs[0]["drawings"].as_array().unwrap().len(), 3);
    // And the objects it did not spend.
    assert!(events(&map).len() < events(&plain).len());
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_decoration_that_leaves_its_cell_with_the_hero_stays_an_object() {
    // Folk spills out of its cell and is on the hero's layer: baked, the
    // hero would walk in front of what is in front of him.
    let dir = scratch("spill");
    let (dump, pictures) = game(&dir);
    let (map, _) = convert(&dir, &dump, &pictures, Some(true));
    assert!(events(&map).contains(&2));
    std::fs::remove_dir_all(&dir).unwrap();
}
