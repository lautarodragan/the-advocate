//! `wally map`: a whole map from the command line —what it reads,
//! what it bakes, the objects it makes and what it says—.
//!
//! A small game is generated inside each test: one map with an opaque tile
//! event on an empty cell, an event with a CharSet and one that walks; its
//! ChipSet, its CharSets and a System. None of this needs a game.

use rm2k_render::{picture, Picture};
use rm2k_rules::chipset::common_origin;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("wally-map-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn picture_of(width: usize, height: usize, pixel: impl Fn(usize, usize) -> [u8; 4]) -> Picture {
    let mut rgba = Vec::with_capacity(width * height * 4);
    for y in 0..height {
        for x in 0..width {
            rgba.extend_from_slice(&pixel(x, y));
        }
    }
    Picture { width, height, rgba }
}

fn write(path: &Path, picture: &Picture) {
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    picture::write_png(path, picture).unwrap();
}

/// A ChipSet of seven colours whose upper-layer tile 0 draws nothing and
/// every other pixel is opaque: an event drawn with an upper tile can be
/// baked, and baking it does not make the background merge.
fn chipset(path: &Path) {
    let (zx, zy) = common_origin(144);
    let picture = picture_of(480, 256, |x, y| {
        let (x, y) = (x as i32, y as i32);
        if (zx..zx + 16).contains(&x) && (zy..zy + 16).contains(&y) {
            [0, 0, 0, 0]
        } else {
            let k = (x / 4 + y / 4) % 7;
            [(k * 36) as u8, (k * 20) as u8, (200 - k * 24) as u8, 255]
        }
    });
    write(path, &picture);
}

/// A CharSet sheet with `colors` colours in blocks, a pixel in seven
/// transparent.
fn charset(path: &Path, colors: usize) {
    let picture = picture_of(288, 256, |x, y| {
        if (x * 3 + y * 5) % 7 == 0 {
            return [0, 0, 0, 0];
        }
        let k = (x / 6 + y / 4 * 3) % colors;
        [(k * 40 % 256) as u8, (k * 90 % 256) as u8, (k * 150 % 256) as u8, 255]
    });
    write(path, &picture);
}

fn page(name: &str, index: i32, layer: i32, move_type: i32) -> Value {
    json!({"id": 1, "character_name": name, "character_index": index,
           "character_direction": 2, "character_pattern": 1, "layer": layer,
           "move_type": move_type, "move_speed": 3, "animation_type": 0,
           "condition": {"flags": {"switch_a": false, "switch_b": false, "variable": false,
                                   "item": false, "actor": false, "timer": false}},
           "move_route": {"move_commands": []}, "event_commands": []})
}

/// The game: its dump in `<dir>/dump` and its pictures in `<dir>/game`.
fn game(dir: &Path) -> (PathBuf, PathBuf) {
    let dump = dir.join("dump");
    std::fs::create_dir_all(dump.join("maps")).unwrap();
    std::fs::create_dir_all(dump.join("db")).unwrap();
    std::fs::write(dump.join("ditto.json"), json!({"ditto": 2, "view": "resolved"}).to_string()).unwrap();
    let mut upper = vec![15u8; 144];
    upper[5] = 0x0F;
    std::fs::write(
        dump.join("db/chipsets.json"),
        json!([{"id": 2, "chipset_name": "tiles", "passable_data_lower": vec![15u8; 162],
                "passable_data_upper": upper}])
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dump.join("db/actors.json"),
        json!([{"id": 1, "character_name": "Hero", "character_index": 0},
               {"id": 2, "character_name": "Nobody", "character_index": 3}])
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dump.join("maps.json"),
        json!({"maps": [], "start": {"party_map_id": 9, "party_x": 1, "party_y": 1}}).to_string(),
    )
    .unwrap();
    let events = json!([
        {"id": 1, "x": 1, "y": 1, "pages": [page("", 5, 0, 0)]},
        {"id": 2, "x": 3, "y": 1, "pages": [page("Hero", 0, 1, 0)]},
        {"id": 4, "x": 4, "y": 2, "pages": [page("Other", 1, 1, 1)]},
    ]);
    std::fs::write(
        dump.join("maps/Map0007.json"),
        json!({"chipset_id": 2, "width": 6, "height": 4, "events": events}).to_string(),
    )
    .unwrap();
    let lower: Vec<String> = (0..4).map(|_| ["  5000"; 6].concat()).collect();
    let upper: Vec<String> = (0..4).map(|_| [" 10000"; 6].concat()).collect();
    std::fs::write(
        dump.join("maps/Map0007.tiles"),
        format!("# 6x4\n# lower\n{}\n# upper\n{}\n", lower.join("\n"), upper.join("\n")),
    )
    .unwrap();
    let pictures = dir.join("game");
    chipset(&pictures.join("ChipSet/tiles.png"));
    charset(&pictures.join("CharSet/Hero.png"), 11);
    charset(&pictures.join("CharSet/Other.png"), 40);
    // A System whose timer's glyphs are two colours.
    let system = picture_of(160, 80, |x, y| {
        if (x + y) % 3 == 0 {
            [0, 0, 0, 0]
        } else if x % 2 == 0 {
            [248, 0, 0, 255]
        } else {
            [0, 0, 0, 255]
        }
    });
    write(&pictures.join("System/system.png"), &system);
    // Nobody's CharSet is fully transparent: a leader with no graphic.
    write(&pictures.join("CharSet/Nobody.png"), &Picture::transparent(288, 256));
    (dump, pictures)
}

fn request(dir: &Path, pictures: &Path, test_event: bool) -> PathBuf {
    // The test's empty event takes index 0.
    let first = usize::from(test_event);
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": test_event, "leaders": [1, 2],
        // The hero-looking event's page sends the other one walking.
        "pages": [{"event": first + 1, "page": 0, "trigger": 3, "code": "00",
                   "route_targets": [first + 2], "own_route": null, "turns": false}],
        "route_graphics": [], "also_walk": [],
        "timer": pictures.join("System/system.png"), "rain": true, "picture": null,
        "battle_animation": true, "singles": [["Hero", 0]], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        "layouts": [], "window_colors": 13,
    });
    let path = dir.join("request.json");
    std::fs::write(&path, body.to_string()).unwrap();
    path
}

fn run(dump: &Path, pictures: &Path, request: &Path, out: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_wally"))
        .args(["map", "--data"])
        .arg(dump)
        .arg("--search-dir")
        .arg(pictures)
        .arg("--request")
        .arg(request)
        .arg("--out")
        .arg(out)
        .output()
        .unwrap()
}

#[test]
fn a_whole_map_bakes_draws_and_says_what_it_did() {
    let dir = scratch("whole");
    let (dump, pictures) = game(&dir);
    let out = dir.join("out");
    let done = run(&dump, &pictures, &request(&dir, &pictures, false), &out);
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let answer: Value = serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();

    // The tile event is baked into its cell, and its row starts hidden.
    assert_eq!(answer["baked"], json!([[0, 7, 10005]]));
    let notes: Vec<&str> = answer["notes"].as_array().unwrap().iter().map(|n| n["text"].as_str().unwrap()).collect();
    assert!(notes.contains(&"  map 7: 1 opaque event(s) baked into the map: 1"), "{notes:?}");
    let npcs = answer["npcs"].as_array().unwrap();
    assert_eq!(npcs.len(), 3);
    assert_eq!(npcs[0]["visible"], json!(false));
    assert_eq!(npcs[0]["charset"], json!("@tile:tiles:5"));
    // The layers were converted with it: the upper tile is in the table.
    let layers: Value = serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    let combos = layers["blocks"]["combos"].as_array().unwrap();
    assert!(combos.iter().any(|c| c[0] == json!(5000) && c[1] == json!(10005)), "{combos:?}");

    // Who moves comes back with the answer.
    assert_eq!(answer["movable"], json!([2]));
    assert_eq!(answer["animates_still"], json!([]));
    assert_eq!(answer["turning"], json!([]));

    let sprite = &answer["sprite"];
    // The leader first, then the one that walks; the one without a graphic
    // gets no bank.
    assert_eq!(sprite["animated"], json!([["Hero", 0], ["Other", 1]]));
    assert_eq!(sprite["actors"][1], json!([2, 0, null, []]));
    for bank in sprite["banks"].as_array().unwrap() {
        assert_eq!(std::fs::read(out.join(bank[2].as_str().unwrap())).unwrap().len(), 12 * 512);
    }
    let tiles = std::fs::read(out.join("sprites.bin")).unwrap();
    assert_eq!(tiles.len() % 32, 0);
    // The hero's block, a slot for the one that walks and one per still
    // pose; the timer, the rain and the animation box at the end.
    assert_eq!(sprite["place"][0][0], json!({"hero": true}));
    assert!(sprite["timer"].is_array());
    // Its two colours, each at one entry of its palette.
    assert_eq!(sprite["timer_mask"].as_u64().unwrap().count_ones(), 2);
    assert_ne!(sprite["rain"][0], json!(0));
    assert!(sprite["animation"]["base"].as_u64().unwrap() > 0);
    // Where the hero starts: the open cell nearest the centre with no event.
    assert_eq!(answer["start"], json!([3, 2]));
    std::fs::remove_dir_all(&dir).unwrap();
}

/// A map whose battle animation box is what makes it not fit any VRAM layout
/// comes out without the box and says so, instead of being cut.
#[test]
fn a_map_whose_animation_box_does_not_fit_loses_the_box() {
    let dir = scratch("box-does-not-fit");
    let (dump, pictures) = game(&dir);
    // Converting again looks at the common events.
    std::fs::write(dump.join("db/commonevents.json"), "[]").unwrap();
    let body = |animation: bool, layouts: Value| {
        json!({
            "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
            "test_event": false, "leaders": [1, 2],
            "pages": [{"event": 1, "page": 0, "trigger": 3, "code": "00",
                       "route_targets": [2], "own_route": null, "turns": false}],
            "route_graphics": [], "also_walk": [],
            "timer": pictures.join("System/system.png"), "rain": true, "picture": null,
            "battle_animation": animation, "singles": [["Hero", 0]], "palette_weight": {},
            "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
            "layouts": layouts, "window_colors": 13,
        })
    };
    let ask_map = |name: &str, body: Value| {
        let path = dir.join(format!("{name}.json"));
        std::fs::write(&path, body.to_string()).unwrap();
        let out = dir.join(name);
        let done = run(&dump, &pictures, &path, &out);
        assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
        let answer: Value = serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
        (answer, std::fs::read(out.join("sprites.bin")).unwrap().len() / 32)
    };
    let (_, without) = ask_map("plain", body(false, json!([])));
    // Room for everything but the box, which is 64 tiles.
    let layouts = json!([[1000, without, 1000]]);
    let (answer, tiles) = ask_map("asked", body(true, layouts));
    assert!(answer["sprite"]["animation"].is_null(), "{}", answer["sprite"]["animation"]);
    assert_eq!(tiles, without);
    let notes: Vec<&str> = answer["notes"].as_array().unwrap().iter().map(|n| n["text"].as_str().unwrap()).collect();
    assert!(notes.iter().any(|n| n.contains("WARNING, battle animations aren't drawn here")), "{notes:?}");
    std::fs::remove_dir_all(&dir).unwrap();
}

fn ask(command: &str, dump: &Path, pictures: &Path, dir: &Path, body: Value) -> Value {
    let request = dir.join(format!("{command}.request.json"));
    std::fs::write(&request, body.to_string()).unwrap();
    let out = dir.join(format!("{command}-out"));
    let done = Command::new(env!("CARGO_BIN_EXE_wally"))
        .args([command, "--data"])
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
    serde_json::from_str(&std::fs::read_to_string(out.join(format!("{command}.json"))).unwrap()).unwrap()
}

#[test]
fn bakeable_says_what_is_baked_and_why_it_is_safe() {
    let dir = scratch("bakeable");
    let (dump, pictures) = game(&dir);
    let answer = ask("bakeable", &dump, &pictures, &dir, json!({"map": 7, "map_files": {}, "chipset_files": {}}));
    let baked = answer["baked"].as_array().unwrap();
    assert_eq!(baked.len(), 1);
    let b = &baked[0];
    assert_eq!((b["event"].clone(), b["cell"].clone(), b["tile"].clone()), (json!(0), json!(7), json!(10005)));
    // What the row imposed is what the table says once the tile is in.
    assert_eq!(b["imposed"], b["after"]);
    assert!(b["alphas"].as_array().unwrap().iter().all(|a| a == 255));
    assert!(answer["tile_zero"].as_array().unwrap().iter().all(|a| a == 0));
    std::fs::remove_dir_all(&dir).unwrap();
}

/// An event some page moves is not baked, whichever way it is named: the
/// second of a `SwapEventLocations`, and "this event" from its own page.
#[test]
fn an_event_a_page_moves_is_not_baked() {
    for (name, mover, command) in [
        ("swapped-second", 1, json!({"code": 10870, "indent": 0, "parameters": [4, 1], "string": ""})),
        ("swapped-first", 1, json!({"code": 10870, "indent": 0, "parameters": [1, 4], "string": ""})),
        ("moves-itself", 0, json!({"code": 10860, "indent": 0, "parameters": [10005, 0, 2, 2], "string": ""})),
    ] {
        let dir = scratch(&format!("not-baked-{name}"));
        let (dump, pictures) = game(&dir);
        let path = dump.join("maps/Map0007.json");
        let mut map: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        map["events"][mover]["pages"][0]["event_commands"] = json!([command]);
        std::fs::write(&path, map.to_string()).unwrap();
        let answer = ask("bakeable", &dump, &pictures, &dir, json!({"map": 7, "map_files": {}, "chipset_files": {}}));
        assert_eq!(answer["baked"].as_array().unwrap().len(), 0, "{name}");
        std::fs::remove_dir_all(&dir).unwrap();
    }
}

#[test]
fn split_answers_with_the_palettes_it_is_given() {
    let dir = scratch("split");
    let (dump, pictures) = game(&dir);
    let answer = ask("split", &dump, &pictures, &dir, json!({"map": 7, "map_files": {}, "chipset_files": {}, "leaders": [1], "palettes": 8}));
    let owners: Vec<Value> = answer["palette_of"].as_array().unwrap().clone();
    assert!(owners.contains(&json!(["Hero", 0, 0])), "{owners:?}");
    assert_eq!(answer["leader_owned"], json!([0]));
    assert_eq!(answer["discarded"], json!([]));
    // With a single palette, the leader's, nobody else can be drawn: the
    // tile is left out.
    let tight = ask("split", &dump, &pictures, &dir, json!({"map": 7, "map_files": {}, "chipset_files": {}, "leaders": [1], "palettes": 1}));
    assert_eq!(tight["discarded"], json!([[0, "@tile:tiles:5"]]));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn the_test_event_goes_first() {
    let dir = scratch("test-event");
    let (dump, pictures) = game(&dir);
    let out = dir.join("out");
    let done = run(&dump, &pictures, &request(&dir, &pictures, true), &out);
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let answer: Value = serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let events: Vec<u64> = answer["npcs"].as_array().unwrap().iter().map(|n| n["event"].as_u64().unwrap()).collect();
    assert_eq!(events, [1, 2, 3]);
    assert_eq!(answer["baked"], json!([[1, 7, 10005]]));
    std::fs::remove_dir_all(&dir).unwrap();
}

/// A leader whose CharSet is empty —the invisible hero some games start
/// with, an actor with no graphic at all— is a leader without a graphic,
/// like one pinned to a blank slot, and not a CharSet that is missing.
#[test]
fn a_leader_with_no_charset_has_no_graphic() {
    let dir = scratch("no-charset");
    let (dump, pictures) = game(&dir);
    std::fs::write(
        dump.join("db/actors.json"),
        json!([{"id": 1, "character_name": "Hero", "character_index": 0},
               {"id": 2, "character_name": "", "character_index": 0}])
        .to_string(),
    )
    .unwrap();
    let request = request(&dir, &pictures, false);
    let text = std::fs::read_to_string(&request).unwrap();
    std::fs::write(&request, text.replace("\"leaders\":[1,2]", "\"leaders\":[2,1]")).unwrap();
    let out = dir.join("out");
    let done = run(&dump, &pictures, &request, &out);
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let answer: Value = serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let notes: Vec<&str> = answer["notes"].as_array().unwrap().iter().map(|n| n["text"].as_str().unwrap()).collect();
    assert!(!notes.iter().any(|n| n.contains("can't find CharSet")), "{notes:?}");
    std::fs::remove_dir_all(&dir).unwrap();
}
