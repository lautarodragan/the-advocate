//! Wally's `map` stage: a whole map —what it reads, what it bakes, the
//! objects it makes and what it says—.
//!
//! A small game is generated inside each test: one map with an opaque tile
//! event on an empty cell, an event with a CharSet and one that walks; its
//! ChipSet, its CharSets and a System. None of this needs a game.

mod common;

use rm2k_render::{picture, Picture};
use rm2k_rules::chipset::common_origin;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

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
    Picture {
        width,
        height,
        rgba,
    }
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
        [
            (k * 40 % 256) as u8,
            (k * 90 % 256) as u8,
            (k * 150 % 256) as u8,
            255,
        ]
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
    std::fs::write(
        dump.join("ditto.json"),
        json!({"ditto": 2, "view": "resolved"}).to_string(),
    )
    .unwrap();
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
        format!(
            "# 6x4\n# lower\n{}\n# upper\n{}\n",
            lower.join("\n"),
            upper.join("\n")
        ),
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
    write(
        &pictures.join("CharSet/Nobody.png"),
        &Picture::transparent(288, 256),
    );
    (dump, pictures)
}

fn request(dir: &Path, pictures: &Path, test_event: bool) -> PathBuf {
    // The test's empty event takes index 0.
    let first = usize::from(test_event);
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": test_event, "leaders": [1, 2],
        // The hero-looking event's page sends the other one walking.
        "pages": [{"event": first + 1, "page": 0, "trigger": 3, "compiles": true,
                   "route_targets": [first + 2], "own_route": false, "turns": false}],
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

#[test]
fn a_whole_map_bakes_draws_and_says_what_it_did() {
    let dir = scratch("whole");
    let (dump, pictures) = game(&dir);
    let out = dir.join("out");
    common::map(&dump, &pictures, &request(&dir, &pictures, false), &out);
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();

    // The tile event is baked into its cell, and its row starts hidden.
    assert_eq!(answer["baked"], json!([[0, 7, 10005]]));
    let notes: Vec<&str> = answer["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap())
        .collect();
    assert!(
        notes.contains(&"  map 7: 1 opaque event(s) baked into the map: 1"),
        "{notes:?}"
    );
    let npcs = answer["npcs"].as_array().unwrap();
    assert_eq!(npcs.len(), 3);
    assert_eq!(npcs[0]["visible"], json!(false));
    assert_eq!(npcs[0]["charset"], json!("@tile:tiles:5"));
    // The layers were converted with it: the upper tile is in the table.
    let layers: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    let combos = layers["blocks"]["combos"].as_array().unwrap();
    assert!(
        combos
            .iter()
            .any(|c| c[0] == json!(5000) && c[1] == json!(10005)),
        "{combos:?}"
    );

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
        assert_eq!(
            std::fs::read(out.join(bank[2].as_str().unwrap()))
                .unwrap()
                .len(),
            12 * 512
        );
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
            "pages": [{"event": 1, "page": 0, "trigger": 3, "compiles": true,
                       "route_targets": [2], "own_route": false, "turns": false}],
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
        common::map(&dump, &pictures, &path, &out);
        let answer: Value =
            serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
        (
            answer,
            std::fs::read(out.join("sprites.bin")).unwrap().len() / 32,
        )
    };
    let (_, without) = ask_map("plain", body(false, json!([])));
    // Room for everything but the box, which is 64 tiles.
    let layouts = json!([[1000, without, 1000]]);
    let (answer, tiles) = ask_map("asked", body(true, layouts));
    assert!(
        answer["sprite"]["animation"].is_null(),
        "{}",
        answer["sprite"]["animation"]
    );
    assert_eq!(tiles, without);
    let notes: Vec<&str> = answer["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap())
        .collect();
    assert!(
        notes
            .iter()
            .any(|n| n.contains("WARNING, battle animations aren't drawn here")),
        "{notes:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// The stage's question `command` —`bakeable` or `split`— on `body`, as
/// the `wally` binary asked it until 2026-11-27: its JSON answer.
fn ask(command: &str, dump: &Path, pictures: &Path, dir: &Path, body: Value) -> Value {
    let request = dir.join(format!("{command}.request.json"));
    std::fs::write(&request, body.to_string()).unwrap();
    let question: wally::stage::Command = match command {
        "bakeable" => wally::stage::bakeable_of,
        "split" => wally::stage::split_of,
        _ => panic!("no question {command}"),
    };
    let (asked, whose) = wally::request::read(&request).unwrap();
    let files = question(dump, &[pictures.to_path_buf()], &asked, &whose)
        .unwrap_or_else(|e| panic!("{e}"));
    serde_json::from_slice(&files[&format!("{command}.json")]).unwrap()
}

#[test]
fn bakeable_says_what_is_baked_and_why_it_is_safe() {
    let dir = scratch("bakeable");
    let (dump, pictures) = game(&dir);
    let answer = ask(
        "bakeable",
        &dump,
        &pictures,
        &dir,
        json!({"map": 7, "map_files": {}, "chipset_files": {}}),
    );
    let baked = answer["baked"].as_array().unwrap();
    assert_eq!(baked.len(), 1);
    let b = &baked[0];
    assert_eq!(
        (b["event"].clone(), b["cell"].clone(), b["tile"].clone()),
        (json!(0), json!(7), json!(10005))
    );
    // What the row imposed is what the table says once the tile is in.
    assert_eq!(b["imposed"], b["after"]);
    assert!(b["alphas"].as_array().unwrap().iter().all(|a| a == 255));
    assert!(answer["tile_zero"]
        .as_array()
        .unwrap()
        .iter()
        .all(|a| a == 0));
    std::fs::remove_dir_all(&dir).unwrap();
}

/// An event some page moves or flashes is not baked, whichever way it is
/// named: the second of a `SwapEventLocations`, "this event" from its own
/// page, and the target of a battle animation.
#[test]
fn an_event_a_page_moves_is_not_baked() {
    for (name, mover, command) in [
        (
            "swapped-second",
            1,
            json!({"code": 10870, "indent": 0, "parameters": [4, 1], "string": ""}),
        ),
        (
            "swapped-first",
            1,
            json!({"code": 10870, "indent": 0, "parameters": [1, 4], "string": ""}),
        ),
        (
            "moves-itself",
            0,
            json!({"code": 10860, "indent": 0, "parameters": [10005, 0, 2, 2], "string": ""}),
        ),
        // A battle animation flashes its target's object: baked, the row
        // has none, and the flash fell on whoever has its palette bits.
        (
            "animates-itself",
            0,
            json!({"code": 11210, "indent": 0, "parameters": [1, 10005, 1, 0], "string": ""}),
        ),
        (
            "animated-by-id",
            1,
            json!({"code": 11210, "indent": 0, "parameters": [1, 1, 1, 0], "string": ""}),
        ),
    ] {
        let dir = scratch(&format!("not-baked-{name}"));
        let (dump, pictures) = game(&dir);
        let path = dump.join("maps/Map0007.json");
        let mut map: Value =
            serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        map["events"][mover]["pages"][0]["event_commands"] = json!([command]);
        std::fs::write(&path, map.to_string()).unwrap();
        let answer = ask(
            "bakeable",
            &dump,
            &pictures,
            &dir,
            json!({"map": 7, "map_files": {}, "chipset_files": {}}),
        );
        assert_eq!(answer["baked"].as_array().unwrap().len(), 0, "{name}");
        std::fs::remove_dir_all(&dir).unwrap();
    }
}

#[test]
fn split_answers_with_the_palettes_it_is_given() {
    let dir = scratch("split");
    let (dump, pictures) = game(&dir);
    let answer = ask(
        "split",
        &dump,
        &pictures,
        &dir,
        json!({"map": 7, "map_files": {}, "chipset_files": {}, "leaders": [1], "palettes": 8}),
    );
    let owners: Vec<Value> = answer["palette_of"].as_array().unwrap().clone();
    assert!(owners.contains(&json!(["Hero", 0, 0])), "{owners:?}");
    assert_eq!(answer["leader_owned"], json!([0]));
    assert_eq!(answer["discarded"], json!([]));
    // With a single palette the leader, who is also an event here, does
    // not take it for itself: it would leave the other events none. It
    // shares it, and the tile goes in with it.
    let tight = ask(
        "split",
        &dump,
        &pictures,
        &dir,
        json!({"map": 7, "map_files": {}, "chipset_files": {}, "leaders": [1], "palettes": 1}),
    );
    assert_eq!(tight["shared_leaders"], json!([["Hero", 0]]));
    assert_eq!(tight["leader_owned"], json!([]));
    assert_eq!(tight["discarded"], json!([]));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn the_test_event_goes_first() {
    let dir = scratch("test-event");
    let (dump, pictures) = game(&dir);
    let out = dir.join("out");
    common::map(&dump, &pictures, &request(&dir, &pictures, true), &out);
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let events: Vec<u64> = answer["npcs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["event"].as_u64().unwrap())
        .collect();
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
    std::fs::write(
        &request,
        text.replace("\"leaders\":[1,2]", "\"leaders\":[2,1]"),
    )
    .unwrap();
    let out = dir.join("out");
    common::map(&dump, &pictures, &request, &out);
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let notes: Vec<&str> = answer["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap())
        .collect();
    assert!(
        !notes.iter().any(|n| n.contains("can't find CharSet")),
        "{notes:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// The game with its events renumbered as if some had been deleted in the
/// editor: the tile event is id 3, the hero-looking one 5 and the walker 8.
/// Requests still name them by index; the notes name them by id.
fn renumbered(dump: &Path) {
    let path = dump.join("maps/Map0007.json");
    let mut map: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    for (event, id) in map["events"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .zip([3, 5, 8])
    {
        event["id"] = json!(id);
    }
    std::fs::write(&path, map.to_string()).unwrap();
}

fn notes_of(out: &Path) -> Vec<String> {
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    answer["notes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|n| n["text"].as_str().unwrap().to_string())
        .collect()
}

#[test]
fn the_baked_note_names_the_event_by_its_id() {
    let dir = scratch("baked-id");
    let (dump, pictures) = game(&dir);
    renumbered(&dump);
    let out = dir.join("out");
    common::map(&dump, &pictures, &request(&dir, &pictures, false), &out);
    let notes = notes_of(&out);
    assert!(
        notes.contains(&"  map 7: 1 opaque event(s) baked into the map: 3".to_string()),
        "{notes:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// With the eight sprite palettes taken by CharSets of fifteen colours
/// each, the baked tile event is lent someone else's palette and goes back
/// to being a sprite: the note names it by its id.
#[test]
fn the_lent_baked_note_names_the_event_by_its_id() {
    let dir = scratch("lent-id");
    let (dump, pictures) = game(&dir);
    renumbered(&dump);
    let path = dump.join("maps/Map0007.json");
    let mut map: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    // Eight CharSets of fifteen colours no other has, on the free cells of
    // the top and bottom rows.
    for k in 0..8usize {
        let name = format!("Fill{k}");
        let sheet = picture_of(288, 256, |x, y| {
            let j = (x / 4 + y / 4) % 15;
            [(8 * (j + 1)) as u8, (128 + 8 * k) as u8, 8, 255]
        });
        write(&pictures.join(format!("CharSet/{name}.png")), &sheet);
        let (x, y) = (k % 6, if k < 6 { 0 } else { 3 });
        map["events"]
            .as_array_mut()
            .unwrap()
            .push(json!({"id": 10 + k, "x": x, "y": y, "pages": [page(&name, 0, 1, 0)]}));
    }
    std::fs::write(&path, map.to_string()).unwrap();
    let request = dir.join("request.json");
    std::fs::write(
        &request,
        json!({
            "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
            "test_event": false, "leaders": [1], "pages": [],
            "route_graphics": [], "also_walk": [],
            "timer": null, "rain": false, "picture": null,
            "battle_animation": false, "singles": [], "palette_weight": {},
            "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
            "layouts": [], "window_colors": 13,
        })
        .to_string(),
    )
    .unwrap();
    let out = dir.join("out");
    common::map(&dump, &pictures, &request, &out);
    let notes = notes_of(&out);
    assert!(
        notes.contains(
            &"  map 7: event 3 is drawn with someone else's palette, so it isn't baked".to_string()
        ),
        "{notes:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// Zounds' spikes, map 59: two groups of lower tiles, 94 and 95, swapped
/// through a lower tile 1 the map draws nowhere —95→1, 94→95, 1→94—, which
/// is how RM2k swaps two tiles. Tile 1's 8x8 cells are in VRAM only if
/// something draws it, so the map is converted with a row below it that
/// does, and the row is cut off again: the map keeps its cells, and every
/// substitution has its blocks.
///
/// And tile 1 draws exactly like the floor, tile 0, as in Zounds: the two
/// cannot share a block, or the console's swap of tile 1's block —which it
/// does wherever the block is— would turn the floor into spikes.
#[test]
fn a_tile_the_map_does_not_draw_is_drawn_below_it_for_a_substitution() {
    let dir = scratch("undrawn-tile");
    let (dump, pictures) = game(&dir);
    let (fx, fy) = common_origin(0);
    let (ox, oy) = common_origin(1);
    let (zx, zy) = common_origin(144);
    let floor_like = picture_of(480, 256, |x, y| {
        let (mut x, mut y) = (x as i32, y as i32);
        if (zx..zx + 16).contains(&x) && (zy..zy + 16).contains(&y) {
            return [0, 0, 0, 0];
        }
        if (ox..ox + 16).contains(&x) && (oy..oy + 16).contains(&y) {
            (x, y) = (x - ox + fx, y - oy + fy);
        }
        let k = (x / 4 + y / 4) % 7;
        [(k * 36) as u8, (k * 20) as u8, (200 - k * 24) as u8, 255]
    });
    write(&pictures.join("ChipSet/tiles.png"), &floor_like);
    let row = |tiles: [&str; 6]| tiles.concat();
    let lower = [
        row(["  5094", "  5094", "  5095", "  5095", "  5000", "  5000"]),
        row(["  5000"; 6]),
        row(["  5000"; 6]),
        row(["  5000"; 6]),
    ];
    let upper: Vec<String> = (0..4).map(|_| [" 10000"; 6].concat()).collect();
    std::fs::write(
        dump.join("maps/Map0007.tiles"),
        format!(
            "# 6x4\n# lower\n{}\n# upper\n{}\n",
            lower.join("\n"),
            upper.join("\n")
        ),
    )
    .unwrap();
    let ring = json!([[false, 95, 1], [false, 94, 95], [false, 1, 94]]);
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": false, "leaders": [1, 2],
        "pages": [], "route_graphics": [], "also_walk": [],
        "timer": pictures.join("System/system.png"), "rain": false, "picture": null,
        "battle_animation": false, "singles": [["Hero", 0]], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": ring, "common_substitutions": [],
        "layouts": [], "window_colors": 13,
    });
    let path = dir.join("request.json");
    std::fs::write(&path, body.to_string()).unwrap();
    let out = dir.join("out");
    common::map(&dump, &pictures, &path, &out);
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("map.json")).unwrap()).unwrap();
    let subs = &answer["substitutions"];
    assert_eq!(subs["missing"], json!([]), "{subs}");
    let table = subs["table"].as_array().unwrap();
    let pairs = |k: usize| -> Vec<(u64, u64)> {
        let p = table[k][3]
            .as_array()
            .unwrap_or_else(|| panic!("{}", table[k]));
        p.iter()
            .map(|p| (p[0].as_u64().unwrap(), p[1].as_u64().unwrap()))
            .collect()
    };
    let (b95, b1) = pairs(0)[0];
    let (b94, to95) = pairs(1)[0];
    let (from1, to94) = pairs(2)[0];
    assert_eq!((to95, from1, to94), (b95, b1, b94));
    // Three distinct blocks, or the runtime's table, which matches by
    // value, could not tell the groups apart.
    assert!(b1 != b94 && b1 != b95 && b94 != b95, "{table:?}");

    // And the map is the map: the extra row is not in its cells.
    let layers: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    assert_eq!(layers["blocks"]["cells"].as_array().unwrap().len(), 24);
    assert_eq!(layers["passability"].as_array().unwrap().len(), 24);
    assert_eq!(layers["background"]["tilemap"].as_array().unwrap().len(), 8);
    let floor = layers["blocks"]["cells"][23].as_u64().unwrap();
    assert!(
        floor != b1,
        "the floor is block {floor}, the one tile 1 swaps: {table:?}"
    );
    std::fs::remove_dir_all(&dir).unwrap();
}

/// A Blurred Line's Lashe City, map 8: its panorama is never seen —the map
/// covers it everywhere, so it goes hidden and the map is drawn as one
/// without it—, and its still events go into the background as on a map
/// with no panorama: the panorama is no reason to keep them objects.
#[test]
fn a_still_event_goes_into_the_background_of_a_map_that_hides_its_panorama() {
    let dir = scratch("posed-hidden-panorama");
    let (dump, pictures) = game(&dir);
    // A CharSet whose poses stay inside their 16x16 cell.
    let small = picture_of(288, 256, |x, y| {
        let (px, py) = (x % 24, y % 32);
        if (4..20).contains(&px) && (16..32).contains(&py) {
            [200, (x * 3 % 256) as u8, 40, 255]
        } else {
            [0, 0, 0, 0]
        }
    });
    write(&pictures.join("CharSet/Small.png"), &small);
    write(
        &pictures.join("Panorama/pano.png"),
        &picture_of(320, 240, |_, _| [10, 200, 10, 255]),
    );
    let path = dump.join("maps/Map0007.json");
    let mut map: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    map["parallax_flag"] = json!(true);
    map["parallax_name"] = json!("pano");
    map["events"] = json!([{"id": 6, "x": 2, "y": 2, "pages": [page("Small", 0, 0, 0)]}]);
    std::fs::write(&path, map.to_string()).unwrap();
    // The common events, which the choice reads for what moves "this event".
    std::fs::write(dump.join("db/commonevents.json"), "[]").unwrap();
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": false, "leaders": [1],
        "pages": [], "route_graphics": [], "also_walk": [],
        "timer": null, "rain": false, "picture": null,
        "battle_animation": false, "singles": [], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        "layouts": [], "window_colors": 13, "posed_stills": true,
        "panorama": {"layouts": [[3, 256, 384, 1, 576]], "baked_tiles": 544},
    });
    let request = dir.join("request.json");
    std::fs::write(&request, body.to_string()).unwrap();
    let out = dir.join("out");
    common::map(&dump, &pictures, &request, &out);
    let notes = notes_of(&out);
    let layers: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    assert_eq!(layers["panorama_way"], json!("hidden"), "{notes:?}");
    assert!(
        notes.contains(
            &"  map 7: 1 still event(s) drawn into the background, a block per pose: 6".to_string()
        ),
        "{notes:?}"
    );
    // And the map is the map: the pose's row is not in its cells.
    assert_eq!(layers["blocks"]["cells"].as_array().unwrap().len(), 24);
    assert_eq!(layers["background"]["tilemap"].as_array().unwrap().len(), 8);
    std::fs::remove_dir_all(&dir).unwrap();
}

/// `baked_events_nudge`: a still event whose poses are drawn a pixel right
/// and two up of its cell —A Blurred Line's chests, `BLObjs` character 2—
/// goes into the background moved back into its cell when the request
/// allows two pixels, and the log says by how much; with one, or with the
/// request not saying, it stays an object, and says why.
#[test]
fn a_still_event_drawn_a_little_past_its_cell_goes_in_shifted() {
    let convert = |offset: Option<i32>| -> Vec<String> {
        let dir = scratch(&format!("posed-offset-{offset:?}"));
        let (dump, pictures) = game(&dir);
        // Each pose a 16x16 square from (5, 14) of its 24x32 frame.
        let off = picture_of(288, 256, |x, y| {
            let (px, py) = (x % 24, y % 32);
            if (5..21).contains(&px) && (14..30).contains(&py) {
                [200, (x * 3 % 256) as u8, 40, 255]
            } else {
                [0, 0, 0, 0]
            }
        });
        write(&pictures.join("CharSet/Off.png"), &off);
        let path = dump.join("maps/Map0007.json");
        let mut map: Value =
            serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        map["events"] = json!([{"id": 6, "x": 2, "y": 2, "pages": [page("Off", 0, 0, 0)]}]);
        std::fs::write(&path, map.to_string()).unwrap();
        std::fs::write(dump.join("db/commonevents.json"), "[]").unwrap();
        let mut body = json!({
            "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
            "test_event": false, "leaders": [1],
            "pages": [], "route_graphics": [], "also_walk": [],
            "timer": null, "rain": false, "picture": null,
            "battle_animation": false, "singles": [], "palette_weight": {},
            "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
            "layouts": [], "window_colors": 13, "posed_stills": true,
        });
        if let Some(n) = offset {
            body["baked_events_nudge"] = json!(n);
        }
        let request = dir.join("request.json");
        std::fs::write(&request, body.to_string()).unwrap();
        let out = dir.join("out");
        common::map(&dump, &pictures, &request, &out);
        let notes = notes_of(&out);
        std::fs::remove_dir_all(&dir).unwrap();
        notes
    };
    let shifted = convert(Some(2));
    assert!(
        shifted.contains(
            &"  map 7: 1 still event(s) drawn into the background, a block per pose: 6".to_string()
        ),
        "{shifted:?}"
    );
    assert!(
        shifted.contains(
            &"  map 7: 1 of them shifted into their cell, in pixels: 6 by (-1, +2)".to_string()
        ),
        "{shifted:?}"
    );
    for strict in [convert(Some(1)), convert(None)] {
        assert!(
            strict.contains(
                &"  map 7: 1 event(s) stay objects, a pose is drawn past its cell: 6".to_string()
            ),
            "{strict:?}"
        );
    }
}

/// Converts map 7 with `events` drawn by two CharSets —`Fits`, whose poses
/// fit their cell, and `Off`, drawn a pixel right and two up of it— with
/// still events into the background and a nudge of 2, and the background's
/// tiles capped by `room`. The notes, and how many tiles the background
/// took.
fn baked_with(name: &str, events: Value, room: Option<usize>) -> (Vec<String>, u64) {
    let dir = scratch(name);
    let (dump, pictures) = game(&dir);
    let sheet = |x0: usize, y0: usize, tint: u8| {
        picture_of(288, 256, move |x, y| {
            let (px, py) = (x % 24, y % 32);
            if (x0..x0 + 16).contains(&px) && (y0..y0 + 16).contains(&py) {
                // A drawing of its own in every 8x8 tile of the cell.
                [
                    tint,
                    ((px * 13 + py * 7) % 4 * 60) as u8,
                    ((px + py) % 2 * 90) as u8,
                    255,
                ]
            } else {
                [0, 0, 0, 0]
            }
        })
    };
    write(&pictures.join("CharSet/Fits.png"), &sheet(4, 16, 240));
    write(&pictures.join("CharSet/Off.png"), &sheet(5, 14, 16));
    let path = dump.join("maps/Map0007.json");
    let mut map: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    map["events"] = events;
    std::fs::write(&path, map.to_string()).unwrap();
    std::fs::write(dump.join("db/commonevents.json"), "[]").unwrap();
    let layouts = room.map_or(json!([]), |r| json!([[r, 512, 512]]));
    let body = json!({
        "map": 7, "map_files": {}, "chipset_files": {}, "names": [],
        "test_event": false, "leaders": [1],
        "pages": [], "route_graphics": [], "also_walk": [],
        "timer": null, "rain": false, "picture": null,
        "battle_animation": false, "singles": [], "palette_weight": {},
        "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        "layouts": layouts, "window_colors": 13, "posed_stills": true,
        "baked_events_nudge": 2,
    });
    let request = dir.join("request.json");
    std::fs::write(&request, body.to_string()).unwrap();
    let out = dir.join("out");
    common::map(&dump, &pictures, &request, &out);
    let notes = notes_of(&out);
    let layers: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    (notes, layers["background"]["tiles"].as_u64().unwrap())
}

/// With room for only some of them, the events that fit their cell as
/// they are go in before the shifted ones, even if the shifted ones are
/// more: the nudge never leaves out an event that went in without it.
#[test]
fn a_shifted_event_never_takes_the_place_of_one_that_fits_as_it_is() {
    let fits = json!({"id": 2, "x": 1, "y": 1, "pages": [page("Fits", 0, 0, 0)]});
    let off = |id: i32, x: i32| json!({"id": id, "x": x, "y": 2, "pages": [page("Off", 0, 0, 0)]});
    // Each alone, to know the room each takes.
    let (_, with_fits) = baked_with("tiers-fits", json!([fits.clone()]), None);
    let (_, with_off) = baked_with("tiers-off", json!([off(3, 3), off(4, 4)]), None);
    let room = with_fits.max(with_off) as usize;
    let (notes, _) = baked_with(
        "tiers-both",
        json!([fits, off(3, 3), off(4, 4)]),
        Some(room),
    );
    assert!(
        notes.contains(
            &"  map 7: 1 still event(s) drawn into the background, a block per pose: 2".to_string()
        ),
        "room {room}: {notes:?}"
    );
    assert!(
        notes.contains(
            &"  map 7: 2 still event(s) stay objects: drawn into the background they move its colours or its tiles past the layouts: 3, 4".to_string()
        ),
        "room {room}: {notes:?}"
    );
}
