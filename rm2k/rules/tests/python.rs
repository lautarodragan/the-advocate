//! The rules against the Python ones they copy.
//!
//! These rules also exist in Python, in the converter that still uses them,
//! and the two copies live side by side until it moves to Rust. What keeps
//! them the same is `python.json`: some inputs, in the dump's shape, and what
//! the Python answered for them. This test requires the Rust answers to be
//! those; on the Python side, `tests/test_rm2k_rules.py` of the tools requires
//! the Python to still give them. So neither side runs the other's language,
//! and a rule changed on one side only goes red on that side.
//!
//! **The answers are not to be edited to make this pass**: they are the
//! other copy's, and the only independent answer there is.

use ditto::schema::{Actor, Chipset, Event, EventPage, MapInfo};
use rm2k_rules::event::Graphic;
use rm2k_rules::tree::Tree;
use rm2k_rules::{actor, animation, chipset, event, passability};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

fn fixture() -> Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/python.json");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn read<T: serde::de::DeserializeOwned>(v: &Value) -> T {
    serde_json::from_value(v.clone()).unwrap()
}

fn numbers(v: &Value) -> Vec<i32> {
    v.as_array().unwrap().iter().map(|n| n.as_i64().unwrap() as i32).collect()
}

fn sha256(data: &[u8]) -> String {
    Sha256::digest(data).iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn the_tile_ids_and_the_chipset_tables() {
    let f = fixture();
    let (inputs, answers) = (&f["inputs"], &f["answers"]);
    let ids = numbers(&inputs["tile_ids"]);
    let index: Vec<i32> = ids.iter().map(|&i| chipset::chip_index(i)).collect();
    assert_eq!(index, numbers(&answers["chip_index"]), "chip_index");

    let chipsets: Vec<Chipset> = read(&inputs["chipsets"]);
    let tables: Vec<Vec<u8>> = chipsets
        .iter()
        .map(|c| chipset::passability_table(&c.passable_data_lower, &c.passable_data_upper))
        .collect();
    let hashes: Vec<String> = tables.iter().map(|t| sha256(t)).collect();
    assert_eq!(json!(hashes), answers["passability_sha256"], "the passability table");

    let terrain: Vec<Vec<i32>> = chipsets
        .iter()
        .map(|c| {
            ids.iter()
                .filter(|&&i| i < chipset::UPPER)
                .map(|&i| chipset::terrain_of(c, i))
                .collect()
        })
        .collect();
    assert_eq!(json!(terrain), answers["terrain"], "terrain_of");

    let cells: Vec<Vec<u8>> = tables
        .iter()
        .map(|t| {
            inputs["cells"]
                .as_array()
                .unwrap()
                .iter()
                .map(|pair| {
                    let pair = numbers(pair);
                    passability::cell(t, pair[0], pair[1])
                })
                .collect()
        })
        .collect();
    assert_eq!(json!(cells), answers["cells"], "the passability of a cell");
}

#[test]
fn where_the_pieces_are_in_the_chipset() {
    let f = fixture();
    let terrain: Vec<[i32; 2]> = (0..12)
        .map(|n| {
            let (x, y) = chipset::terrain_origin(n);
            [x, y]
        })
        .collect();
    assert_eq!(json!(terrain), f["answers"]["terrain_box"]);
    let common: Vec<[i32; 2]> = (0..288)
        .map(|i| {
            let (x, y) = chipset::common_origin(i);
            [x, y]
        })
        .collect();
    assert_eq!(json!(common), f["answers"]["common_box"]);
}

#[test]
fn the_animated_tiles() {
    let f = fixture();
    let steps: Vec<u32> = f["inputs"]["frames"]
        .as_array()
        .unwrap()
        .iter()
        .map(|t| animation::animated_drawing(t.as_u64().unwrap() as u32))
        .collect();
    assert_eq!(json!(steps), f["answers"]["animated_step"]);
}

#[test]
fn what_a_page_draws_and_what_it_does_to_its_cell() {
    let f = fixture();
    let chipsets: Vec<Chipset> = read(&f["inputs"]["chipsets"]);
    let (lower, upper) = (&chipsets[0].passable_data_lower, &chipsets[0].passable_data_upper);
    let flags = chipset::passability_table(lower, upper);
    let (mut graphics, mut passes) = (Vec::new(), Vec::new());
    for p in f["inputs"]["pages"].as_array().unwrap() {
        let page: EventPage = read(p);
        let graphic = event::page_graphic(&page);
        graphics.push(match &graphic {
            None => Value::Null,
            Some(Graphic::CharSet { name, index, pose }) => {
                json!({"name": name, "index": index, "pose": pose})
            }
            Some(Graphic::Tile { tile, pose }) => json!({"tile": tile, "pose": pose}),
        });
        passes.push(graphic.and_then(|g| event::tile_passability(&flags, &g, page.layer)));
    }
    assert_eq!(json!(graphics), f["answers"]["page_graphic"], "page_graphic");
    assert_eq!(json!(passes), f["answers"]["tile_passability"], "tile_passability");
}

#[test]
fn the_page_a_new_game_starts_on() {
    let f = fixture();
    let starting: Vec<Option<i32>> = f["inputs"]["events"]
        .as_array()
        .unwrap()
        .iter()
        .map(|e| event::starting_page(&read::<Event>(e)).map(|p| p.id))
        .collect();
    assert_eq!(json!(starting), f["answers"]["starting_page"]);
}

#[test]
fn experience_and_level() {
    let f = fixture();
    let gains: Vec<Vec<i64>> = read(&f["inputs"]["exp_gains"]);
    let answers = f["answers"]["actors"].as_array().unwrap();
    for (data, expected) in f["inputs"]["actors"].as_array().unwrap().iter().zip(answers) {
        let a: Actor = read(data);
        let top = actor::max_level(&a);
        let got = json!({
            "max_level": top,
            "initial_level": actor::initial_level(&a),
            "initial_exp": actor::initial_exp(&a),
            "exp_list": actor::exp_list(&a),
            "next_exp": (-1..top + 2).map(|n| actor::next_exp(&a, n)).collect::<Vec<_>>(),
            "add_exp": gains
                .iter()
                .map(|g| {
                    let (level, exp) = actor::add_exp(&a, g[0], g[1], g[2]);
                    vec![level, exp]
                })
                .collect::<Vec<_>>(),
        });
        assert_eq!(&got, expected, "actor {}", a.id);
    }
}

#[test]
fn what_a_map_inherits_from_the_tree() {
    let f = fixture();
    let mut tree = Tree::default();
    let mut ids = Vec::new();
    for n in f["inputs"]["tree"].as_array().unwrap() {
        let node: MapInfo = read(n);
        ids.push(node.id);
        tree.insert(node);
    }
    ids.push(99);
    let background: Vec<Option<&str>> = ids.iter().map(|&i| tree.background(i)).collect();
    assert_eq!(json!(background), f["answers"]["background"], "the battle background");
    let music: Vec<Option<&str>> =
        ids.iter().map(|&i| tree.music(i).map(|m| m.name.as_str())).collect();
    assert_eq!(json!(music), f["answers"]["music"], "the song");
}
