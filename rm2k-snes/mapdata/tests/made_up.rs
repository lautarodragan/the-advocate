//! The emission over made-up input: the maps of `tests/maps.json` and two
//! whole cartridge requests, `tests/emit-*.json`.
//!
//! The maps are made up to go through every path: an own route and a forced
//! one, a page without code, one that turns and one that changes graphic, a
//! walking event and a still one that animates, a leader without a graphic,
//! both ChipSet animation families, a flat terrain and a table, two maps
//! sharing blocks and a pose bank, and one quantized differently.
//!
//! The whole `.inc` goes twice over them, with the database of
//! `rm2k-snes-battle`'s test game: once bare —no title, no Game Over, no
//! picture, no animations, no battle audio, no troop pages— and once with
//! all of it, a hero above, the enemies' HP, dead texts and a case slot.
//!
//! **The paths they guard**: what no game's build reaches. What the bytes
//! of a real cartridge do is checked by playing them —A Blurred Line's
//! suite and the test game—, and `record.rs`, `materials.rs` and the other
//! files here check each table; what is here is what those games do not
//! have: these maps' shapes, a cartridge with none of the optional parts,
//! more troops, members and actions than a byte numbers, a 4bpp title, a
//! second System's window, a map that does not fit and an event without
//! its slot.

use rm2k_snes_battle::db::Db;
use rm2k_snes_mapdata::record;
use rm2k_snes_mapdata::request::{self, Emit, Maps};
use std::path::{Path, PathBuf};

fn maps() -> Maps {
    request::read(&Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json")).unwrap()
}

/// What the made-up maps share and lose, and how long the console takes
/// to unpack the first two: every path of `maps.json` goes through
/// `record::maps` here, which a panic or a refusal would stop.
#[test]
fn the_made_up_maps_say_what_they_shared_and_lost() {
    let written = record::maps(&maps().maps).unwrap();
    assert_eq!(
        written.notes,
        [
            "  map 8: Chubby2:2 goes with a pose bank of its own, quantized differently than in \
             another map",
            "  poses: 33 distinct out of 36, 1.5 KB less",
            // Made-up poses, with no empty tile: only the masks are added.
            "  poses: 0 of their 528 tiles empty, -0.1 KB less",
            // A made-up map whose pictures take four palettes from the top
            // and its battle animation's box the sixth from the bottom.
            "  map 8: the message arrow stays in the window's cells, and a window without its \
             background that does not carry the layer above keeps it off its bottom row: its 8 \
             sprite palettes are taken: \
             up to 5 by the characters and the battle animation's box, and the top 4 by the pictures"
        ]
    );
    assert_eq!(
        written.report,
        [
            "  map_tiles         0.2 KB in LZ2, was    0.2",
            "  above_tiles       0.1 KB in LZ2, was    0.1",
            "  sprite_tiles      0.3 KB in LZ2, was    0.4",
            "  anim_tiles        0.3 KB in LZ2, was    0.6",
            "  map_cells         0.5 KB in LZ2, was    0.8",
            "  map_ram           0.1 KB in LZ2, was    0.1",
            "  map_code          0.0 KB in LZ2, was    0.0",
            "  map_pages         0.1 KB in LZ2, was    0.1",
            "                    1.7 KB in LZ2, was    2.2: 0.6 KB less",
            "  map_tiles       1 shared block(s),    0.2 KB",
            "  map_cgram       1 shared block(s),    0.0 KB",
            "                  2                 0.2 KB in total"
        ]
    );
    assert_eq!(written.frames, [0.42809969996144753, 0.256625152952614]);
}

#[test]
fn a_map_that_does_not_fit_its_layout_is_refused() {
    let mut maps = maps().maps;
    maps[0].tiles = vec![0; 449 * 64];
    let bad = record::maps(&maps).err().unwrap();
    assert_eq!(
        bad.message(),
        "map 7: with this VRAM layout, tiles needs 449 tiles and 448 fit"
    );
}

#[test]
fn an_event_without_its_slot_is_refused() {
    let mut maps = maps().maps;
    maps[0].movable.clear();
    let bad = record::maps(&maps).err().unwrap();
    assert_eq!(
        bad.message(),
        "map 7: event 2 is drawn and has no slot in the sprite bank"
    );
}

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

/// A whole cartridge's request: the made-up maps, each with its timer's
/// mask, and the rest of `emit-<name>.json`.
fn emit_request(name: &str) -> Emit {
    let read = |file: &str| -> serde_json::Value {
        serde_json::from_str(&std::fs::read_to_string(here().join(file)).unwrap()).unwrap()
    };
    let mut value = read(&format!("tests/emit-{name}.json"));
    let mut maps = read("tests/maps.json");
    for m in maps["maps"].as_array_mut().unwrap() {
        let id = m["id"].as_i64().unwrap();
        m["sprite"]["timer_mask"] = (id * 3).into();
    }
    value["maps"] = maps["maps"].take();
    serde_json::from_value(value).unwrap()
}

/// `rm2k-snes-battle`'s test game: its actors, items, skills, enemies and
/// troops are what the tables of the `.inc` are read from.
fn db() -> Db {
    Db::from_dump(&here().join("../battle/tests/game/dump"), true).unwrap()
}

/// A cartridge with none of the optional parts, and one with all of them,
/// are emitted whole: the bare one is what no game's build asks for.
#[test]
fn a_bare_cartridge_and_a_whole_one_are_emitted() {
    for name in ["bare", "whole"] {
        let emitted = rm2k_snes_mapdata::emit::emit(&emit_request(name), &db()).unwrap();
        assert!(emitted.text.contains("\nmap_access:\n"), "{name}");
    }
}

#[test]
fn a_troop_page_that_asks_for_a_variable_carries_its_tables() {
    // No page of A Blurred Line's asks for a variable. This is what the
    // console reads.
    let mut request = emit_request("whole");
    let pages = request.troop_pages.as_mut().unwrap();
    pages.per_troop[0].1[0].0 = [4, 5, 0, 17, -2, 0, 0, 0, 0, 0, 0, 0, 0];
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains(".block 6\ntpage_var:\n    .word 17, 0, 0\n"));
    assert!(text.contains(".block 6\ntpage_value:\n    .word 65534, 0, 0\n"));
    assert!(text.contains(".block 2\ntpage_sw_b:\n    .word 0\n"));
}

/// The request of `emit-whole.json`, with the maps of `maps.json`, and troop
/// `copied` repeated —in the database, the model and the scene— under each
/// number of `numbers`.
fn whole_with_troop_copies(copied: i32, numbers: std::ops::Range<i32>) -> (Emit, Db) {
    let mut db = db();
    let read = |file: &str| -> serde_json::Value {
        serde_json::from_str(&std::fs::read_to_string(here().join(file)).unwrap()).unwrap()
    };
    let mut value = read("tests/emit-whole.json");
    let mut maps = read("tests/maps.json");
    for m in maps["maps"].as_array_mut().unwrap() {
        let id = m["id"].as_i64().unwrap();
        m["sprite"]["timer_mask"] = (id * 3).into();
    }
    value["maps"] = maps["maps"].take();
    let original = db.troops[&copied].clone();
    let k = copied as usize - 1;
    let model_original = value["battle_model"]["troops"][k].clone();
    let scene_original = value["scene"]["troops"][k].clone();
    for n in numbers {
        let mut troop = original.clone();
        troop.id = n;
        db.troops.insert(n, troop);
        value["troops"].as_array_mut().unwrap().push(n.into());
        let mut model = model_original.clone();
        model["id"] = n.into();
        value["battle_model"]["troops"]
            .as_array_mut()
            .unwrap()
            .push(model);
        let mut scene = scene_original.clone();
        scene[0] = n.into();
        value["scene"]["troops"].as_array_mut().unwrap().push(scene);
    }
    (serde_json::from_value(value).unwrap(), db)
}

/// Vampires Dawn's troops take 470 members: where each troop's list starts
/// in `troop_member` does not fit in a byte, and goes in a word. Made up out
/// of troop 4 —eight members— copied under 34 more numbers.
#[test]
fn troops_with_more_members_than_a_byte_numbers_start_in_words() {
    let (request, db) = whole_with_troop_copies(4, 7..41);
    let text = rm2k_snes_mapdata::emit::emit(&request, &db).unwrap().text;
    // Six troops of 2, 3, 3, 8, 3 and 4 members, and then 34 of eight: the
    // last one starts at 23 + 33 * 8.
    let starts = text
        .split("troop_init:\n")
        .nth(1)
        .unwrap()
        .lines()
        .next()
        .unwrap();
    assert!(
        starts.starts_with("    .word 0, 2, 5, 8, 16, 19, 23, 31,"),
        "{starts}"
    );
    assert!(starts.ends_with(", 287"), "{starts}");
}

/// Vampires Dawn carries 277 troops: a troop's place, `BA_TROOP_K`, does
/// not fit in a byte, and since 2026-10-11 it is a word. Made up out of
/// troop 1 —two members— copied under 294 more numbers, 300 in all.
#[test]
fn more_troops_than_a_byte_numbers_fit() {
    let (request, db) = whole_with_troop_copies(1, 7..301);
    let text = rm2k_snes_mapdata::emit::emit(&request, &db).unwrap().text;
    assert!(text.contains("TROOPS_N          = 300\n"), "TROOPS_N");
    let ids = text
        .split("troop_id:\n")
        .nth(1)
        .unwrap()
        .lines()
        .next()
        .unwrap();
    assert!(ids.ends_with(", 299, 300"), "{ids}");
}

/// Vampires Dawn's enemies take 344 actions: where each enemy's list starts
/// in `eacc_*` does not fit in a byte, and goes in a word. Made up giving each
/// of the eight enemies forty attacks.
#[test]
fn enemies_with_more_actions_than_a_byte_numbers_start_in_words() {
    let mut request = emit_request("whole");
    for e in 1..=8 {
        request
            .battle_model
            .actions
            .insert(e, vec![(50, None, true); 40]);
    }
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    let starts = text
        .split("enemy_acc_init:\n")
        .nth(1)
        .unwrap()
        .lines()
        .next()
        .unwrap();
    assert_eq!(starts, "    .word 0, 40, 80, 120, 160, 200, 240, 280");
}

/// A title at 4bpp says so to `title.s`, and its row in `screens_table`
/// counts its tiles at 32 bytes and not 64.
#[test]
fn a_title_at_4bpp_counts_its_tiles_at_32_bytes() {
    let row = |request: &Emit| -> (String, String) {
        let text = rm2k_snes_mapdata::emit::emit(request, &db()).unwrap().text;
        let bpp = text
            .lines()
            .find(|l| l.starts_with("TITLE_BPP"))
            .unwrap()
            .to_string();
        let table = text.split("screens_table:\n").nth(1).unwrap();
        let at = text
            .lines()
            .find_map(|l| l.strip_prefix("SCREEN_TITLE = "))
            .unwrap();
        let row: usize = at.parse().unwrap();
        // Four lines a row: the stream's address and bank, the two sizes,
        // the first colour.
        (bpp, table.lines().nth(row * 4 + 2).unwrap().to_string())
    };
    let mut request = emit_request("whole");
    let tiles = request.title.as_ref().unwrap().tiles;
    let colors = request.title.as_ref().unwrap().colors;
    assert_eq!(
        row(&request),
        (
            "TITLE_BPP      = 8".to_string(),
            format!("    .word {}, {}", tiles * 64, colors * 2)
        )
    );
    request.title.as_mut().unwrap().bpp = 4;
    assert_eq!(
        row(&request),
        (
            "TITLE_BPP      = 4".to_string(),
            format!("    .word {}, {}", tiles * 32, colors * 2)
        )
    );
}

/// The window's text area, as `background` of the request, with each of its
/// four lines made of `line(k)`'s bytes: a line is 30 cells by two rows of
/// 32-byte tiles.
fn with_backdrop(line: impl Fn(usize) -> u8) -> (Emit, usize) {
    let mut value: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(here().join("tests/emit-whole.json")).unwrap(),
    )
    .unwrap();
    let bytes = 30 * 2 * 32;
    let hex: String = (0..4)
        .flat_map(|k| std::iter::repeat_n(format!("{:02x}", line(k)), bytes))
        .collect();
    value["screens"]["window"]["background"] = hex.into();
    let mut maps: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(here().join("tests/maps.json")).unwrap())
            .unwrap();
    for m in maps["maps"].as_array_mut().unwrap() {
        let id = m["id"].as_i64().unwrap();
        m["sprite"]["timer_mask"] = (id * 3).into();
    }
    value["maps"] = maps["maps"].take();
    (serde_json::from_value(value).unwrap(), bytes)
}

/// A window over one colour —`[windows.background]`— has the same
/// background under every line: it goes once, and `prime_line` copies it
/// under all four.
#[test]
fn a_text_area_whose_lines_are_the_same_goes_as_one_line() {
    let (request, bytes) = with_backdrop(|_| 0xAA);
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains("WINDOW_BACKDROP_LINES = 1\n"));
    assert!(
        text.contains(&format!(".block {bytes}\nwindow_backdrop:\n")),
        "one line"
    );

    let (request, bytes) = with_backdrop(|k| if k == 3 { 0xAB } else { 0xAA });
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains("WINDOW_BACKDROP_LINES = 4\n"));
    assert!(
        text.contains(&format!(".block {}\nwindow_backdrop:\n", bytes * 4)),
        "all four"
    );
}

/// A cartridge that switches System carries one window per System, all
/// with the text area at the same tile: a smaller frame is padded up to the
/// largest, and its text cells renumbered from there. And the table the
/// runtime finds each one's pieces in.
#[test]
fn a_second_system_s_window_takes_the_largest_frame_s_tile_numbers() {
    let (mut request, _) = with_backdrop(|_| 0xAA);
    let first = request.screens.window.system.clone();
    let base = first.base;
    // The other System's frame, two tiles smaller.
    let mut other = first.clone();
    other.tiles.truncate(first.tiles.len() - 2 * 32);
    other.base = base - 2;
    for c in other.cells.iter_mut().flatten() {
        *c = if *c >= base {
            *c - 2
        } else {
            (*c).min(base - 3)
        };
    }
    request.window_systems = vec![rm2k_snes_screens::answer::OtherSystem {
        system: "Other".into(),
        window: other,
    }];
    let base = base as i64;
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains("WINDOW_SYSTEMS = 2\n"));
    assert!(
        text.contains(&format!(".block {}\nwindow_tiles_1:\n", base * 32)),
        "padded to the largest frame"
    );
    assert!(
        text.contains(".block 60\nwindow_systems:\n"),
        "two entries of ten pointers"
    );
    assert!(text.contains("    .word .loword(window_bar_bare_1)\n    .byte ^window_bar_bare_1\n"));
    // The same cells for both: the second's text renumbered back to the
    // first's, and its frame cells the same as they were.
    let words = |label: &str| -> Vec<u16> {
        let bytes: Vec<u8> = text
            .split(&format!("\n{label}:\n"))
            .nth(1)
            .unwrap()
            .lines()
            .take_while(|l| l.starts_with("    .byte "))
            .flat_map(|l| {
                l[10..]
                    .split(',')
                    .map(|b| u8::from_str_radix(&b[1..], 16).unwrap())
                    .collect::<Vec<_>>()
            })
            .collect();
        bytes
            .chunks(2)
            .map(|w| u16::from_le_bytes([w[0], w[1]]))
            .collect()
    };
    let (one, two) = (words("window_cells"), words("window_cells_1"));
    assert_eq!(one.len(), two.len());
    // The tile numbers carry the window base the layout puts in front.
    let tile = |w: u16| i64::from(w & 0x3FF);
    let at = tile(one[0]) - first.cells[0][0] as i64;
    let mut frame = 0;
    for (a, b) in one.iter().zip(&two) {
        if *a == 0 || tile(*a) - at >= base {
            assert_eq!(a, b, "a text cell, or a blank one, is the same in both");
        } else {
            assert_eq!(
                tile(*b) - at,
                (tile(*a) - at).min(base - 3),
                "a frame cell keeps its own tile"
            );
            frame += 1;
        }
    }
    assert!(frame > 0);
    assert!(text.contains("WINDOW_BACKDROP_LINES = 1\n"));
}

#[test]
fn each_map_carries_what_it_forbids_in_its_order() {
    let mut request = emit_request("whole");
    let n = request.maps.len();
    assert!(n >= 2, "the test needs two maps");
    request.maps[0].access = 0x05;
    request.maps[n - 1].access = 0x08;
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    let mut want = vec!["$00"; n];
    want[0] = "$05";
    want[n - 1] = "$08";
    let table = format!(".block {n}\nmap_access:\n    .byte {}\n", want.join(", "));
    assert!(text.contains(&table), "{table}");
}
