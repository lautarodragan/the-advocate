//! What this emits, against what the Python it replaced emitted for the same
//! input: the hashes of its text, taken from the converter's Python on
//! 2026-10-01, before it was deleted.
//!
//! The maps (`tests/maps.json`) are made up to go through every path: an own
//! route and a forced one, a page without code, one that turns and one that
//! changes graphic, a walking event and a still one that animates, a leader
//! without a graphic, both ChipSet animation families, a flat terrain and a
//! table, two maps sharing blocks and a pose bank, and one quantized
//! differently.
//!
//! The whole `.inc` goes twice over them (`tests/emit-*.json`), with the
//! database of `rm2k-snes-battle`'s test game: once bare —no title, no Game
//! Over, no picture, no animations, no battle audio, no troop pages— and
//! once with all of it, a hero above, the enemies' HP, dead texts and a case
//! slot.
//!
//! **If one of these changes, a byte of the cartridge changed.** The hashes
//! are not to be regenerated to make a test pass: the Python that produced
//! them is gone.
//!
//! They are regenerated when the cartridge changes **on purpose**, and the
//! commit says so. Since then they are this code's and not the Python's:
//! on 2026-10-01 the block table, its passability and the event bytecode
//! went into LZ2, behind the grid —`map_ram` and `map_code` in
//! `materials.rs`—, and so did the battlers, the
//! backdrops —`scene.rs`— and the battle animations' frames; what the
//! console makes of the new bytes is checked by the game's tests, not here.
//!
//! On 2026-10-02 a page that changes graphic stopped coming with its OAM
//! bytes and came with where its poses are, which `page_oam` turns into
//! them. The made-up bytes the map carried, `$01, $02`, are not a tile any
//! block starts at, so it asks for block 5 with palette 1 now: that one
//! line of the page table is what moved the three hashes.
//!
//! Also on 2026-10-02, the two map names that came from the game this was
//! built for —one with an apostrophe, one with a comma— became invented
//! ones of the same length, and the four hashes of text that carries them
//! in a comment moved: the new text, with the old names put back, is the
//! old one byte for byte. No byte of a cartridge moved.
//!
//! And also on 2026-10-02 the actors got their critical hit, which comes
//! from three new tables —`item_crit_k`, `actor_crit_row` and
//! `crit_table`, nine lines— and the two hashes of the whole `.inc` moved:
//! without those nine lines the text is the old one byte for byte.
//!
//! On 2026-10-03 the font got variable width: the window's line is
//! measured in pixels, `MESSAGE_WIDTH` and not `MESSAGE_COLS`, and two
//! tables more go with the font, `font_advance` and `font_reach`. The two
//! requests carry them now —RM2k's fixed font, six pixels a letter— and
//! the two hashes of the whole `.inc` moved: the difference against the old
//! text is those two tables, that constant, and the two comments that
//! name them.
//!
//! Also on 2026-10-03 the item, equipment, shop and battle screens stopped
//! drawing a letter per cell: they compose their text like the window, from
//! the font precomposed for their palettes. The requests carry
//! `text_inks` —the same four palettes, and eight made-up tables of six
//! bytes— where they carried `items_font`, and `SCR_TEXT_X` and
//! `SCR_TEXT_Y` in the geometry, and the two hashes moved: the difference
//! against the old text is `items_tiles`, `item_glyph_cells`,
//! `ITEMS_TILES` and `ITEM_GLYPHS_GRAY` gone, and the eight `scr_pre`
//! tables and the two constants in their place.
//!
//! And the same day the menu's bank started composing the names: the
//! requests carry `slots.prerender`, eight more made-up tables, and the two
//! hashes moved by the eight `slot_pre` tables they come out as and nothing
//! else.
//!
//! On 2026-10-04 the message window took the System's arrow and its cursor:
//! the requests carry `arrow`, `bar` and `bar_bare` in the window —made up
//! out of its background— and four numbers in the geometry, and the window
//! reserves thirteen colour-memory entries and not eight. The two hashes
//! moved: without the four constants and their comments, the three new
//! blocks, and with `CGRAM_BASE` at 9 and `window_cgram` cut to nine words,
//! the text is the old one byte for byte. Later that day the thirteen
//! stopped being a constant and came in the request, `window_colors`, which
//! the two requests carry as thirteen so the hashes did not move.
//!
//! And the same day the battle's windows went to the band below the scene,
//! as RM2k's, with the System's frame and bar: the requests carry
//! `rm2k-snes-battle`'s new `layout`, the dead state's name in
//! `texts.dead` and the screens stage's `battle_windows` —of the screens'
//! test game—, and the two hashes moved. The difference against the old
//! text, compared line by line, is the battle's geometry constants —new
//! names, new values, in another order—, the two tables of where each
//! command went gone, `BA_TXT_SP`, `BA_TXT_NORMAL` and `BA_TXT_DEAD` and
//! those three texts, `ba_item_desc` and the items' whole descriptions, and
//! the windows' blocks and constants (`ba_win_*`, `BA_WIN_*`).
//!
//! On 2026-10-10 `troop_init` went from bytes to words, because Vampires
//! Dawn's troops take 470 members, and the two hashes moved: the difference
//! is that table's `.byte` turned `.word` and its `.block` doubled, nothing
//! else. The same day `enemy_acc_init` did the same, for Vampires Dawn's 344
//! enemy actions, and the hashes moved again by that table alone.

use rm2k_snes_battle::db::Db;
use rm2k_snes_mapdata::record;
use rm2k_snes_mapdata::request::{self, Emit, Maps};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

fn sha(text: &str) -> String {
    Sha256::digest(text.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn maps() -> Maps {
    request::read(&Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json")).unwrap()
}

#[test]
fn what_goes_per_map_comes_out_as_the_python_wrote_it() {
    let written = record::maps(&maps().maps).unwrap();
    assert_eq!(
        sha(&written.offsets),
        "1739ecfe74a25a7d9c0fa8001ea8c338117c81189df83a9196643a6173976fc1"
    );
    assert_eq!(
        sha(&with_the_turn_as_before(&written.maps)),
        "cb782dcc5d6a59cb08786dea041fabaacbdb78812d565a5b5841be440d55ce42"
    );
    assert_eq!(
        sha(&written.tables),
        "82065b2018a245b9969577d4fc353de15879021e61b93a5c0a29af777e314b06"
    );
}

#[test]
fn what_it_says_is_what_the_python_said() {
    let written = record::maps(&maps().maps).unwrap();
    assert_eq!(
        written.notes,
        [
            "  map 8: Chubby2:2 goes with a pose bank of its own, quantized differently than in \
             another map",
            "  poses: 33 distinct out of 36, 1.5 KB less"
        ]
    );
    assert_eq!(
        written.report,
        [
            "  map_tiles         0.2 KB in LZ2, was    0.2",
            "  above_tiles       0.1 KB in LZ2, was    0.1",
            "  sprite_tiles      0.3 KB in LZ2, was    0.4",
            "  anim_tiles        0.3 KB in LZ2, was    0.6",
            "  map_cells         0.7 KB in LZ2, was    1.6",
            "  map_ram           0.1 KB in LZ2, was    0.1",
            "  map_code          0.0 KB in LZ2, was    0.0",
            "                    1.7 KB in LZ2, was    2.9: 1.2 KB less",
            "  map_tiles       1 shared block(s),    0.2 KB",
            "  map_cgram       1 shared block(s),    0.0 KB",
            "                  2                 0.2 KB in total"
        ]
    );
    assert_eq!(written.frames, [0.4388273353559396, 0.34244623610855024]);
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

/// A whole cartridge's request: the test maps, each with its timer's mask,
/// and the rest of `emit-<name>.json`.
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

/// The text without the text block's pair table, which came after the
/// Python: the four lines right after `MESSAGES_CAP`, checked here against
/// the request's `5f60` —one pair—.
fn without_pairs(text: &str) -> String {
    let pairs = [
        ".block 2",
        "message_pairs:",
        "    .byte $5F,$60",
        "MESSAGE_PAIR_FIRST = 95",
    ];
    let lines: Vec<&str> = text.split('\n').collect();
    let at = lines
        .iter()
        .position(|l| l.starts_with("MESSAGES_CAP = "))
        .unwrap()
        + 1;
    assert_eq!(lines[at..at + pairs.len()], pairs);
    let mut kept = lines[..at].to_vec();
    kept.extend(&lines[at + pairs.len()..]);
    kept.join("\n")
}

/// The text without the shared common event bodies' tables, which came
/// after the Python too: a cartridge without bodies carries their two
/// constants at zero and each table with a dummy entry, checked here.
fn without_commons(text: &str) -> String {
    let mut lines: Vec<&str> = text.split('\n').collect();
    for constant in ["COMMON_DEPTH = 0", "COMAUTO_N = 0"] {
        let at = lines.iter().position(|l| *l == constant).unwrap();
        lines.remove(at);
    }
    for (label, data) in [
        ("common_body_lo:", "    .word 0"),
        ("common_body_bank:", "    .word 0"),
        ("comauto_byte:", "    .word 0"),
        ("comauto_mask:", "    .byte 0"),
        ("comauto_body:", "    .byte 0"),
    ] {
        let at = lines.iter().position(|l| *l == label).unwrap();
        assert_eq!(lines[at + 1], data, "{label}");
        let from = if at > 0 && lines[at - 1].starts_with(".block ") { at - 1 } else { at };
        lines.drain(from..at + 2);
    }
    lines.join("\n")
}

/// The page table's +30 and +31 as they were before 2026-10-05: the turn's
/// pose bank and pose, or `$FF, 0` for a page that does not turn. Since then
/// a page of an event that walks carries its pose bank too, and +31 its
/// palette and, in bit 7, that it does not turn —see `page_table`—; this
/// gives back what the Python wrote, which is what the hashes hold.
fn with_the_turn_as_before(text: &str) -> String {
    text.split('\n')
        .map(|line| {
            let Some(rest) = line.strip_prefix("    .byte $") else {
                return line.to_string();
            };
            if !line.contains("; +30 its poses and +31") {
                return line.to_string();
            }
            let k = u8::from_str_radix(&rest[..2], 16).unwrap();
            let pose = u8::from_str_radix(&rest[5..7], 16).unwrap();
            if pose & 0x80 != 0 {
                "    .byte $FF, 0 ; +30 the turn: its poses and its pose".to_string()
            } else {
                format!("    .byte ${k:02X}, {} ; +30 the turn: its poses and its pose", pose & 0x0F)
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// The text without `item_up`, which came on 2026-10-04 with the materials:
/// what each item adds to an actor for good. The test game has no
/// material, so every word is zero, which is checked here.
fn without_item_up(text: &str) -> String {
    let mut lines: Vec<&str> = text.split('\n').collect();
    let at = lines.iter().position(|l| *l == "item_up:").unwrap();
    assert!(lines[at - 1].starts_with(".block "));
    let words = lines[at + 1].trim_start_matches("    .word ");
    assert!(words.split(", ").all(|w| w == "0"), "a material in the test game");
    lines.drain(at - 1..at + 2);
    lines.join("\n")
}

/// The text without the custom menus, which came on 2026-10-04: a request
/// without them gets the section's empty labels and the pause menu's two
/// counts, checked here to be those of no menu.
fn without_custom_menus(text: &str) -> String {
    let start = text.find("\n; --- the custom menus: see custom_menu.s ---\n").unwrap();
    let last = "cm_portrait_cgram:\n    .byte 0\n";
    let end = text[start..].find(last).unwrap() + start + last.len();
    let mut out = format!("{}{}", &text[..start], &text[end..]);
    for line in ["MENU_CUSTOM = 0\n", "MENU_ROWS_MAX = 5\n"] {
        assert!(out.contains(line), "{line}");
        out = out.replacen(line, "", 1);
    }
    out
}

/// The text without `SLOT_MENU_TILES` and its comment, which came after
/// the Python too, on 2026-10-03: a request without `menu_tiles` says all
/// of the bank, checked here.
fn without_menu_tiles(text: &str) -> String {
    let mut lines: Vec<&str> = text.split('\n').collect();
    let at = lines.iter().position(|l| l.starts_with("SLOT_MENU_TILES ")).unwrap();
    let tiles = lines.iter().find(|l| l.starts_with("SLOT_TILES ")).unwrap();
    assert_eq!(lines[at].split('=').nth(1), tiles.split('=').nth(1));
    lines.drain(at - 3..=at);
    lines.join("\n")
}

/// The text with the window's cells as the Python wrote them: one plane per
/// base and not two. The second, the window without its frame for
/// `MessageOptions`, came after, on 2026-10-04: it is checked here to be the
/// first with some cells at zero —the ones that are not text, which in this
/// request's window are all of them— and dropped.
fn without_bare_window(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    for label in ["window_cells:", "window_cells_256:"] {
        let at = lines.iter().position(|l| l == label).unwrap();
        let size: usize = lines[at - 1].trim_start_matches(".block ").parse().unwrap();
        let rows = size.div_ceil(16);
        let bytes: Vec<u8> = lines[at + 1..at + 1 + rows]
            .iter()
            .flat_map(|l| {
                l.trim_start_matches("    .byte ")
                    .split(',')
                    .map(|b| u8::from_str_radix(b.trim_start_matches('$'), 16).unwrap())
                    .collect::<Vec<_>>()
            })
            .collect();
        assert_eq!(bytes.len(), size, "{label}");
        let (framed, bare) = bytes.split_at(size / 2);
        for (f, b) in framed.chunks(2).zip(bare.chunks(2)) {
            assert!(b == [0, 0] || b == f, "{label} a bare cell that is neither blank nor the window's");
        }
        let old: Vec<String> = framed
            .chunks(16)
            .map(|c| {
                let hex: Vec<String> = c.iter().map(|b| format!("${b:02X}")).collect();
                format!("    .byte {}", hex.join(","))
            })
            .collect();
        lines[at - 1] = format!(".block {}", size / 2);
        lines.splice(at + 1..at + 1 + rows, old);
    }
    lines.join("\n")
}

#[test]
fn a_bare_cartridge_comes_out_as_the_python_wrote_it() {
    let emitted = rm2k_snes_mapdata::emit::emit(&emit_request("bare"), &db()).unwrap();
    let text = with_the_turn_as_before(&without_item_up(&without_bare_window(&without_menu_tiles(&without_commons(&without_pairs(&without_custom_menus(&emitted.text)))))));
    assert_eq!(text.lines().count(), 3774);
    assert_eq!(
        sha(&text),
        "00dcc2552eae4871f0e785669976b799df463e0652204237257cd48a46cac190"
    );
}

#[test]
fn a_whole_cartridge_comes_out_as_the_python_wrote_it() {
    let emitted = rm2k_snes_mapdata::emit::emit(&emit_request("whole"), &db()).unwrap();
    let text = with_the_turn_as_before(&without_item_up(&without_bare_window(&without_menu_tiles(&without_commons(&without_pairs(&without_custom_menus(&emitted.text)))))));
    assert_eq!(text.lines().count(), 3893);
    assert_eq!(
        sha(&text),
        "4de4a91e909f1459794cc556bfa78ae22fab6f23f71f1297546752b70faeeea5"
    );
}

#[test]
fn a_troop_page_that_asks_for_a_variable_carries_its_tables() {
    // The Python never wrote these two tables full —no page of the game it
    // converted asks for a variable—, and it would have failed: it read the
    // trigger's fields by their old names. This is what the console reads.
    let mut request = emit_request("whole");
    let pages = request.troop_pages.as_mut().unwrap();
    pages["per_troop"][0][1][0][0] = serde_json::json!([4, 5, 0, 17, -2, 0, 0, 0, 0, 0, 0, 0, 0]);
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains(".block 6\ntpage_var:\n    .word 17, 0, 0\n"));
    assert!(text.contains(".block 6\ntpage_value:\n    .word 65534, 0, 0\n"));
    assert!(text.contains(".block 2\ntpage_sw_b:\n    .word 0\n"));
}

/// Vampires Dawn's troops take 470 members: where each troop's list starts
/// in `troop_member` does not fit in a byte, and goes in a word. Made up out
/// of troop 4 —eight members— copied under 34 more numbers.
#[test]
fn troops_with_more_members_than_a_byte_numbers_start_in_words() {
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
    let four = db.troops[&4].clone();
    let model_four = value["battle_model"]["troops"][3].clone();
    let scene_four = value["scene"]["troops"][3].clone();
    for n in 7..41 {
        let mut troop = four.clone();
        troop.id = n;
        db.troops.insert(n, troop);
        value["troops"].as_array_mut().unwrap().push(n.into());
        let mut model = model_four.clone();
        model["id"] = n.into();
        value["battle_model"]["troops"].as_array_mut().unwrap().push(model);
        let mut scene = scene_four.clone();
        scene[0] = n.into();
        value["scene"]["troops"].as_array_mut().unwrap().push(scene);
    }
    let request: Emit = serde_json::from_value(value).unwrap();
    let text = rm2k_snes_mapdata::emit::emit(&request, &db).unwrap().text;
    // Six troops of 2, 3, 3, 8, 3 and 4 members, and then 34 of eight: the
    // last one starts at 23 + 33 * 8.
    let starts = text.split("troop_init:\n").nth(1).unwrap().lines().next().unwrap();
    assert!(starts.starts_with("    .word 0, 2, 5, 8, 16, 19, 23, 31,"), "{starts}");
    assert!(starts.ends_with(", 287"), "{starts}");
}

/// Vampires Dawn's enemies take 344 actions: where each enemy's list starts
/// in `eacc_*` does not fit in a byte, and goes in a word. Made up giving each
/// of the eight enemies forty attacks.
#[test]
fn enemies_with_more_actions_than_a_byte_numbers_start_in_words() {
    let mut request = emit_request("whole");
    let attacks = serde_json::json!(vec![serde_json::json!([50, null, true]); 40]);
    for e in 1..=8 {
        request.battle_model["actions"][e.to_string()] = attacks.clone();
    }
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    let starts = text.split("enemy_acc_init:\n").nth(1).unwrap().lines().next().unwrap();
    assert_eq!(starts, "    .word 0, 40, 80, 120, 160, 200, 240, 280");
}
