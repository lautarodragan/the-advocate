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
//!
//! On 2026-10-10 a map with more events than the RAM holds got its twins
//! —events left without a row, which share another's— as a table behind
//! its positions, a word with how many first. These maps have none, and
//! the three hashes moved: the difference against the old text is
//! `TWIN_STRIDE` and its comment, and a zero word behind each map's
//! positions.
//!
//! On 2026-10-12 `TROOP_PAGE_MAX` went from 32 to 64, because the agency
//! captain's troop brings 33 pages once they all compile, and the two
//! hashes of the whole `.inc` moved: with it back at 32, the text is the old
//! one byte for byte.
//!
//! On 2026-10-14 the poses stopped going whole: a pose is a mask of the
//! tiles that draw something and only those tiles, and the console zeroes
//! the rest in the slot. These maps' poses are made up and none has an
//! empty tile, so each one grew by its two bytes of mask and the three
//! hashes that carry them moved; `with_whole_poses_as_before` puts each
//! pose back to its 512 bytes, checking that the mask counts the tiles
//! that follow, and with it the text is the old one byte for byte. The
//! same day each map's `npc_poses` table started being stored once when
//! two maps bring the same one, under the first one's label: none of
//! these maps shares one, so that moved nothing here, and it is checked in
//! `materials.rs`. And the console has to know what the sprite bank left in
//! each slot, to zero only what a pose leaves empty: `pose_masks_maps` and
//! `pose_masks_data` came with it, in the tables, and `without_pose_masks`
//! takes them away.
//!
//! On 2026-10-17 a map with at most 256 blocks started carrying its grid
//! one byte a cell —`cell_bytes` in `materials.rs`—, and every map here has
//! that few: their grid streams, the fourth byte of their grid pointer in
//! the map table, the report's `map_cells` line and the decompression
//! frames moved, and four hashes and the two line counts with them.
//! `without_grid_narrow` takes away the new `M_GRID_NARROW` line, and with
//! it and the grids forced wide (`NARROW_BLOCKS` at 0) the text was the old
//! one byte for byte; the new hashes are the narrow grids'.

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
        sha(&without_grid_narrow(&written.offsets)),
        "1739ecfe74a25a7d9c0fa8001ea8c338117c81189df83a9196643a6173976fc1"
    );
    assert_eq!(
        sha(&with_whole_poses_as_before(&without_hero_colors(&with_the_turn_as_before(&written.maps)))),
        "20e390800ee76ba822286a03ea4f55123e754cce30d97a1e0131b18745dec4bb"
    );
    assert_eq!(
        sha(&without_pose_masks(&written.tables)),
        "c0cc2585dfd0de58f4e76cb7b6421853fa72f31a6c9fa2e7d307310bf9b38a55"
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
            "  poses: 33 distinct out of 36, 1.5 KB less",
            // Made-up poses, with no empty tile: only the masks are added.
            "  poses: 0 of their 528 tiles empty, -0.1 KB less"
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
            "                    1.6 KB in LZ2, was    2.1: 0.6 KB less",
            "  map_tiles       1 shared block(s),    0.2 KB",
            "  map_cgram       1 shared block(s),    0.0 KB",
            "                  2                 0.2 KB in total"
        ]
    );
    assert_eq!(written.frames, [0.3885415444442582, 0.256625152952614]);
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
    emit_request_with(name, 0)
}

/// [`emit_request`], with the old slot rows' variant `cursor` as the rows:
/// see [`with_the_system_cursors`].
fn emit_request_with(name: &str, cursor: usize) -> Emit {
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
    with_the_skills_screen(&mut value["screens"]);
    with_the_shop_party(&mut value["screens"]);
    with_the_system_cursors(&mut value["screens"], cursor);
    serde_json::from_value(value).unwrap()
}

/// The System's cursors in the screens stage's answer, which came on
/// 2026-10-16, after the requests were written: the slot rows lose their
/// variant with a ">" —the one without it, `cursor` 0, or the one with it,
/// 1, which is how [`with_the_cursors_as_before`] gets those blocks back—,
/// the menu loses its ">", and the actor choice's answer carries the command
/// cursor and the slot cursor, made up here: one cell each.
fn with_the_system_cursors(screens: &mut serde_json::Value, cursor: usize) {
    let rows: Vec<Vec<serde_json::Value>> = screens["slots"]["rows"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row.as_array().unwrap().iter().map(|full| full[cursor].clone()).collect())
        .collect();
    screens["slots"]["rows"] = serde_json::json!(rows);
    screens["slots"]["menu"].as_object_mut().unwrap().remove("cursor");
    screens["target"]["menu_cmd"] = serde_json::json!([1]);
    screens["target"]["menu_cmd_at"] = serde_json::json!([1, 1, 1, 1]);
    screens["target"]["slot_bar"] = serde_json::json!([2]);
    screens["target"]["slot_bar_at"] = serde_json::json!([3, 1, 6, 1]);
}

/// The shop's party in the screens stage's answer, which came on
/// 2026-10-15, after the requests were written: no member with a CharSet
/// and the System's sixteen arrows blank, with its geometry; taken out of
/// the text by [`without_shop_party`].
fn with_the_shop_party(screens: &mut serde_json::Value) {
    screens["shop_party"] = serde_json::json!({
        "members": [],
        "arrows": vec![vec![vec![0; 8]; 8]; 16],
        "arrow_colors": [],
        "tile0": 0,
    });
    let geometry = [
        "TI_PARTY_MEMBERS", "TI_PARTY_X0", "TI_PARTY_Y0", "TI_PARTY_STEP", "TI_ARROW_DX", "TI_ARROW_DY",
        "TI_PARTY_RATE", "TI_ARROW_FRAMES", "TI_ARROW_UP", "TI_ARROW_SAME", "TI_ARROW_DOWN",
        "TI_ARROW_EQUIPPED",
    ];
    for (k, name) in geometry.iter().enumerate() {
        if screens["layout"].get(*name).is_none() {
            screens["layout"][*name] = k.into();
        }
    }
}

/// The text with the ">" cursors as the Python wrote them, before the
/// System's cursors of 2026-10-16. Each slot's row had four variants and not
/// two: the one with the ">" goes back after each, from the answer with
/// `cursor` 1 —its `.block` the same size—, and the slot block tables, the
/// faces' indices and the menu's blocks shift by the two variants per slot
/// that are back. The menu had its ">" in two cells, and where each one went,
/// in bank 0; what goes out is where the two cursors go on BG1 and their
/// cells, checked here to be the made-up ones of
/// [`with_the_system_cursors`].
fn with_the_cursors_as_before(text: &str, name: &str) -> String {
    let with_cursor = rm2k_snes_mapdata::emit::emit(&emit_request_with(name, 1), &db()).unwrap().text;
    let request: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(here().join(format!("tests/emit-{name}.json"))).unwrap()).unwrap();
    let screens = &request["screens"];
    let slots = screens["slots"]["rows"].as_array().unwrap().len();
    let shift = 2 * slots as i64;
    let is_row = |label: &str| -> bool {
        let parts: Vec<&str> = label.split('_').collect();
        parts.len() == 3
            && parts[0] == "slot"
            && parts[1].chars().all(|c| c.is_ascii_digit())
            && parts[2].len() == 1
            && parts[2].chars().all(|c| c.is_ascii_digit())
    };
    let lines: Vec<&str> = text.split('\n').collect();
    let other: Vec<&str> = with_cursor.split('\n').collect();
    assert_eq!(lines.len(), other.len());
    let mut out: Vec<String> = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let line = lines[i];
        if let Some(label) = line.strip_suffix(':').filter(|l| is_row(l)) {
            assert!(out.last().unwrap().starts_with(".block "));
            let size = out.last().unwrap().clone();
            out.push(format!("{label}0:"));
            out.push(lines[i + 1].to_string());
            out.push(size);
            out.push(format!("{label}1:"));
            out.push(other[i + 1].to_string());
            i += 2;
            continue;
        }
        if ["slot_block_lo:", "slot_block_hi:", "slot_block_bk:"].contains(&line) {
            let size: i64 = out.pop().unwrap().strip_prefix(".block ").unwrap().parse().unwrap();
            out.push(format!(".block {}", size + shift));
            out.push(line.to_string());
            let (indent, list) = lines[i + 1].split_at(lines[i + 1].find(".byte ").unwrap() + 6);
            let names: Vec<String> = list
                .split(", ")
                .flat_map(|n| {
                    let (prefix, label) = n.split_at(1);
                    if is_row(label) {
                        vec![format!("{prefix}{label}0"), format!("{prefix}{label}1")]
                    } else {
                        vec![n.to_string()]
                    }
                })
                .collect();
            out.push(format!("{indent}{}", names.join(", ")));
            i += 2;
            continue;
        }
        if line == "slot_face_block:" {
            out.push(line.to_string());
            let (indent, list) = lines[i + 1].split_at(lines[i + 1].find(".byte ").unwrap() + 6);
            let blocks: Vec<String> = list
                .split(", ")
                .map(|b| match b.parse::<i64>().unwrap() {
                    255 => "255".to_string(),
                    n => (n + shift).to_string(),
                })
                .collect();
            out.push(format!("{indent}{}", blocks.join(", ")));
            i += 2;
            continue;
        }
        if let Some((name, value)) = ["MENU_BLK_OPTION   = ", "MENU_BLK_CURRENCY = ", "MENU_BLK_ROW      = "]
            .iter()
            .find_map(|p| line.strip_prefix(p).map(|v| (*p, v)))
        {
            out.push(format!("{name}{}", value.parse::<i64>().unwrap() + shift));
            i += 1;
            continue;
        }
        if line == "menu_option_vram:" {
            let layout = &screens["layout"];
            let back = layout["MENU_OPT_COL"].as_i64().unwrap() - layout["MENU_CURSOR_COL"].as_i64().unwrap();
            let (indent, list) = lines[i + 1].split_at(lines[i + 1].find(".word ").unwrap() + 6);
            let cursor: Vec<String> = list.split(", ").map(|v| (v.parse::<i64>().unwrap() - back).to_string()).collect();
            out.push(line.to_string());
            out.push(lines[i + 1].to_string());
            out.push("menu_cursor_vram:".to_string());
            out.push(format!("{indent}{}", cursor.join(", ")));
            i += 2;
            continue;
        }
        if line == "menu_row_vram:" {
            let cells: Vec<String> = screens["slots"]["menu"]["cursor"]
                .as_array()
                .unwrap()
                .iter()
                .map(|c| format!("${:04X}", c.as_i64().unwrap() | 0x2000))
                .collect();
            out.push(line.to_string());
            out.push(lines[i + 1].to_string());
            out.push("menu_cursor_cells:".to_string());
            out.push(format!("     .word {}", cells.join(", ")));
            i += 2;
            continue;
        }
        if line == "menu_cursor_vram:" || line == "slot_bar_vram:" {
            assert!(out.pop().unwrap().starts_with(".block "));
            assert!(lines[i + 1].starts_with("    .word "));
            i += 2;
            continue;
        }
        if line == "menu_cmd_cells:" {
            out.pop();
            let cut = [
                "menu_cmd_cells:", "    .byte $01,$00", "MENU_CMD_ROW0 = 1", "MENU_CMD_ROWS = 1",
                "MENU_CMD_COL0 = 1", "MENU_CMD_COLS = 1", ".block 2", "slot_bar_cells:", "    .byte $02,$00",
                "SLOT_BAR_ROW0 = 3", "SLOT_BAR_ROWS = 1", "SLOT_BAR_COL0 = 6", "SLOT_BAR_COLS = 1",
            ];
            assert_eq!(&lines[i..i + cut.len()], &cut);
            i += cut.len();
            continue;
        }
        out.push(line.to_string());
        i += 1;
    }
    out.join("\n")
}

/// The text without the shop's party, which came on 2026-10-15: its
/// section, from its comment to the one that ends it.
fn without_shop_party(text: &str) -> String {
    let start = text.find("\n; --- the shop's party: see shop_party.s ---\n").unwrap();
    let last = "; --- the shop's party ends ---\n";
    let end = text[start..].find(last).unwrap() + start + last.len();
    format!("{}{}", &text[..start], &text[end..])
}

/// The skills screen's part of the screens stage's answer, which came on
/// 2026-10-12, after the requests were written: made up here —no tiles, a
/// tilemap and bars of zeros, each skill of the battle's test game with
/// its description in one line of five letters, the odd ones usable on the
/// map—, and taken out of the text by [`without_skills_screen`]. And the
/// actor choice for a skill, which came on 2026-10-13: the name cut at its
/// fourth letter, nothing that raises, one cell of term and a bar of one
/// row for each party size.
fn with_the_skills_screen(screens: &mut serde_json::Value) {
    let mut skills = serde_json::Map::new();
    for id in 1..=200 {
        skills.insert(
            id.to_string(),
            serde_json::json!({"lines": [5, 6, 0], "field": id % 2 == 1, "revives": false, "name_cut": 4}),
        );
    }
    screens["skills"] = skills.into();
    screens["target"]["skill"] = serde_json::json!({
        "term_at": [7, 1, 1, 1], "term": [0], "all_at": [0, 1, 13, 2],
        "all_rows": [[0, 0]], "all": [[0], [0], [0], [0]],
    });
    screens["skills_screen"] =
        serde_json::json!({"tiles": [], "colors": [], "map": vec![0; 32 * 28], "bars": vec![0; 16 * 64]});
    let geometry = [
        "SK_HELP_ROW0", "SK_HELP_COL", "SK_STATUS_ROW", "SK_NAME_COL", "SK_NAME_WIDTH", "SK_LEVEL_COL",
        "SK_LEVEL_NUM_COL", "SK_STATE_COL", "SK_STATE_WIDTH", "SK_HP_COL", "SK_HP_NUM_COL", "SK_SP_COL",
        "SK_SP_NUM_COL", "SK_LIST_ROW0", "SK_ROWS", "SK_COLUMNS", "SK_COLUMN_DX", "SK_NAME_DX",
        "SK_NAME_CELLS", "SK_DASH_DX", "SK_COST_DIGITS", "SK_HALF_COLS", "MENU_SKILL",
        "ITEM_WHITE", "ITEM_GRAY", "ITEM_RED",
        // The message's face, which came on 2026-10-15.
        "MSG_FACE_ROW", "MSG_FACE_COL_LEFT", "MSG_FACE_COL_RIGHT", "MSG_FACE_TEXT_X", "MSG_FACE_RIGHT_X",
    ];
    for (k, name) in geometry.iter().enumerate() {
        if screens["layout"].get(*name).is_none() {
            screens["layout"][*name] = k.into();
        }
    }
}

/// The text without what the skills screen added on 2026-10-12: its
/// section, the four per-skill tables and the level term's number —its
/// text is the last of the block, and [`without_states`] cuts it with the
/// conditions'—. Checked here: the tables have one entry per carried skill.
/// The stop counters with frequency 1 at zero, as before 2026-10-14: since
/// then a page that walks by a movement type can have frequency 1, so the
/// tables carry its counters too —see `route::own` in the compiler—.
fn with_frequency_one_as_before(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    for label in ["route_after_step:", "route_after_turn:"] {
        let at = lines.iter().position(|l| l == label).unwrap();
        let mut values: Vec<String> = lines[at + 1]
            .trim_start_matches("  .byte ")
            .split(',')
            .map(String::from)
            .collect();
        values[1] = "0".into();
        lines[at + 1] = format!("  .byte {}", values.join(","));
    }
    lines.join("\n")
}

fn without_skills_screen(text: &str) -> String {
    let text = &without_skill_choice(text);
    let start = text.find("\n; --- the skills screen: see skills_screen.s ---\n").unwrap();
    let last = "sk_border_cgram:\n";
    let from_last = text[start..].find(last).unwrap() + start + last.len();
    // The block's data: up to the next line that is not a `.byte`.
    let mut end = from_last;
    for line in text[from_last..].split_inclusive('\n') {
        if !line.starts_with("    .byte ") {
            break;
        }
        end += line.len();
    }
    let out = format!("{}{}", &text[..start], &text[end..]);
    let mut lines: Vec<&str> = out.split('\n').collect();
    let carried = lines
        .iter()
        .position(|l| *l == "skill_id:")
        .map(|at| lines[at + 1].split(',').count())
        .unwrap();
    for label in ["skill_line1_n:", "skill_line2_at:", "skill_line2_n:", "skill_on_map:", "skill_name_cut:"] {
        let at = lines.iter().position(|l| *l == label).unwrap();
        assert_eq!(lines[at + 1].split(',').count(), carried, "{label}");
        lines.drain(at - 1..=at + 1);
    }
    let at = lines.iter().position(|l| l.starts_with("SK_TXT_LEVEL = ")).unwrap();
    lines.remove(at);
    lines.join("\n")
}

/// The text without the actor choice for a skill, which came on 2026-10-13:
/// from `target_term`'s `.block` to `TARGET_ALL_COLS`, right after the
/// choice's colours.
fn without_skill_choice(text: &str) -> String {
    let label = text.find("\ntarget_term:\n").unwrap();
    let start = text[..label].rfind("\n.block ").unwrap() + 1;
    let last = text[start..].find("TARGET_ALL_COLS = ").unwrap() + start;
    let end = text[last..].find('\n').unwrap() + last + 1;
    format!("{}{}", &text[..start], &text[end..])
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

/// The parallel common events as the equipment ones were written before
/// 2026-10-12, when only those ran, from the menu: `COMEQ_N` and four
/// `comeq_*` tables, with the bank as a word and no flag, instead of
/// `compar_table`, and each body as `common_equipment_<n>`. The requests'
/// two are equipment ones, in the order of their switches, which was the
/// old order.
fn with_the_equipment_commons_as_before(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(str::to_string).collect();
    let at = lines.iter().position(|l| l.starts_with("COMPAR_N = ")).unwrap();
    let n: usize = lines[at]["COMPAR_N = ".len()..].parse().unwrap();
    assert_eq!(lines[at + 2], "compar_table:");
    let entries: Vec<&[String]> = lines[at + 3..at + 3 + 3 * n].chunks(3).collect();
    let field = |line: &str, prefix: &str| line.trim_start().strip_prefix(prefix).unwrap().to_string();
    let first: Vec<Vec<String>> = entries
        .iter()
        .map(|e| field(&e[0], ".byte ").split(", ").map(str::to_string).collect())
        .collect();
    let bytes: Vec<String> = first.iter().map(|f| f[0].clone()).collect();
    let masks: Vec<String> = first.iter().map(|f| f[1].clone()).collect();
    let codes: Vec<String> = entries.iter().map(|e| field(&e[1], ".word ")).collect();
    let banks: Vec<String> = entries.iter().map(|e| field(&e[2], ".byte ")).collect();
    let old = vec![
        format!("COMEQ_N = {n}"),
        format!(".block {}", 2 * n),
        "comeq_byte:".to_string(),
        format!("    .word {}", bytes.join(", ")),
        format!(".block {n}"),
        "comeq_mask:".to_string(),
        format!("    .byte {}", masks.join(", ")),
        format!(".block {}", 2 * n),
        "comeq_code:".to_string(),
        format!("    .word {}", codes.join(", ")),
        format!(".block {}", 2 * n),
        "comeq_bank:".to_string(),
        format!("    .word {}", banks.join(", ")),
    ];
    lines.splice(at..at + 3 + 3 * n, old);
    lines.join("\n").replace("common_parallel_", "common_equipment_")
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
        // And the copies' —see `Copies` in the request—, which a cartridge
        // without them carries all at zero: one byte per eight maps.
        ("comauto_copied:", "    .byte 0"),
        ("comcopy_maps:", "    .byte 0"),
    ] {
        let at = lines.iter().position(|l| *l == label).unwrap();
        if label == "comcopy_maps:" {
            let zeros = lines[at + 1].strip_prefix("    .byte ").is_some_and(|b| b.split(", ").all(|v| v == "0"));
            assert!(zeros, "{label}: {}", lines[at + 1]);
        } else {
            assert_eq!(lines[at + 1], data, "{label}");
        }
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

/// The poses as they were before 2026-10-14, 512 bytes each: since then a
/// pose is a mask of the tiles that draw and only those tiles —see
/// `pose_record`—, and this puts the empty ones back where the mask says.
/// These maps' poses are made up and have no empty tile, so it only takes
/// the mask away; the round trip is what is checked, here, and that the
/// tiles are the ones it says.
fn with_whole_poses_as_before(text: &str) -> String {
    let lines: Vec<&str> = text.split('\n').collect();
    let mut out: Vec<String> = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let is_pose = lines[i].starts_with(".block ")
            && lines.get(i + 1).is_some_and(|l| {
                l.strip_prefix("pose_")
                    .and_then(|r| r.strip_suffix(':'))
                    .is_some_and(|n| n.chars().all(|c| c.is_ascii_digit()))
            });
        if !is_pose {
            out.push(lines[i].to_string());
            i += 1;
            continue;
        }
        let label = lines[i + 1];
        let mut bytes = Vec::new();
        let mut j = i + 2;
        while let Some(rest) = lines.get(j).and_then(|l| l.strip_prefix("    .byte ")) {
            bytes.extend(rest.split(',').map(|b| u8::from_str_radix(&b[1..], 16).unwrap()));
            j += 1;
        }
        assert_eq!(lines[i], format!(".block {}", bytes.len()));
        let mask = u16::from_le_bytes([bytes[0], bytes[1]]);
        assert_eq!(bytes.len(), 2 + 32 * mask.count_ones() as usize, "{label}");
        let mut drawn = bytes[2..].chunks(32);
        let mut whole = Vec::new();
        for t in 0..16 {
            if mask & (1 << t) != 0 {
                whole.extend_from_slice(drawn.next().unwrap());
            } else {
                whole.extend([0u8; 32]);
            }
        }
        out.push(".block 512".into());
        out.push(label.into());
        for chunk in whole.chunks(16) {
            let row: Vec<String> = chunk.iter().map(|b| format!("${b:02X}")).collect();
            out.push(format!("    .byte {}", row.join(",")));
        }
        i = j;
    }
    out.join("\n")
}

/// The text without `pose_masks_maps` and `pose_masks_data`, which came on
/// 2026-10-14 with the poses without their empty tiles: what each block of
/// the sprite bank holds when a map loads. Checked here: a word per map
/// pointing at a whole entry, and 32 words an entry.
fn without_pose_masks(text: &str) -> String {
    let head = "\n.segment \"RODATA\"\n; What each block of the sprite bank holds";
    let at = text.find(head).expect("the cartridge has no pose_masks table");
    let lines: Vec<&str> = text[at + 1..].split('\n').collect();
    assert_eq!(lines[3], "pose_masks_maps:");
    let starts: Vec<usize> =
        lines[4].trim_start_matches("    .word ").split(", ").map(|n| n.parse().unwrap()).collect();
    assert_eq!(lines[6], "pose_masks_data:");
    let words = lines[7..].iter().take_while(|l| l.starts_with("    .word $")).count();
    assert_eq!(lines[5], format!(".block {}", 2 * 16 * words));
    assert!(starts.iter().all(|s| s % 64 == 0 && *s < 32 * words));
    // The section and the blank line `maps_with` puts before it.
    let end = lines[..7 + words].iter().map(|l| l.len() + 1).sum::<usize>();
    format!("{}{}", &text[..at], &text[at + 1 + end..])
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

/// The text without the colours of the graphics only the hero shows, which
/// came on 2026-10-11: the `hero_colors` table —one byte, none of these
/// maps' graphics brings colours— and the byte per graphic behind each
/// `route_graphic`, checked here to be 0.
fn without_hero_colors(text: &str) -> String {
    let empty = ".block 1\nhero_colors:\n    .byte $00\n\n";
    assert!(text.contains(empty), "a hero_colors table with something in it");
    let text = text.replacen(empty, "", 1);
    let mut lines: Vec<String> = text.split('\n').map(str::to_string).collect();
    let mut at = 0;
    while at < lines.len() {
        if !(lines[at].starts_with("route_graphic_") && lines[at].ends_with(':')) {
            at += 1;
            continue;
        }
        let mut end = at + 1;
        let mut bytes: Vec<String> = Vec::new();
        while end < lines.len() && lines[end].starts_with("    .byte ") {
            bytes.extend(lines[end]["    .byte ".len()..].split(',').map(str::to_string));
            end += 1;
        }
        let n = bytes.len() / 3;
        assert!(bytes[2 * n..].iter().all(|b| b == "$00"), "a graphic with colours");
        bytes.truncate(2 * n);
        let rows: Vec<String> = bytes.chunks(16).map(|c| format!("    .byte {}", c.join(","))).collect();
        lines[at - 1] = format!(".block {}", 2 * n);
        let count = rows.len();
        lines.splice(at + 1..end, rows);
        at += 1 + count;
    }
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

/// The text without the battle's conditions, which came on 2026-10-12: the
/// `state_*` tables and `STATES_N`, and their messages, which are the last
/// texts —from the empty one the conditions share on—. Checked here: each
/// condition's two texts are among those last ones.
fn without_states(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l.starts_with("STATES_N = ")).unwrap();
    lines.remove(at);
    let mut theirs = Vec::new();
    for label in [
        "state_priority:",
        "state_restrict:",
        "state_hold:",
        "state_auto:",
        "state_damage:",
        "state_hit:",
        "state_halves:",
        "state_affected:",
        "state_recovery:",
    ] {
        let at = lines.iter().position(|l| l == label).unwrap();
        if label == "state_affected:" || label == "state_recovery:" {
            let values = lines[at + 1].trim_start_matches("    .word ");
            theirs.extend(values.split(", ").map(|v| v.parse::<usize>().unwrap()));
        }
        lines.drain(at - 1..=at + 1);
    }
    let first = *theirs.iter().min().unwrap();
    // The four tables that name the texts, cut at the first of theirs; and
    // the block, at where it starts.
    let mut cut_at = None;
    for label in ["item_txt_lo:", "item_txt_hi:", "item_txt_bk:", "item_txt_n:"] {
        let at = lines.iter().position(|l| l == label).unwrap();
        let entries: Vec<String> = lines[at + 1]
            .trim_start_matches("    .byte ")
            .split(", ")
            .map(String::from)
            .collect();
        assert!(theirs.iter().all(|&k| k < entries.len()), "{label}");
        if label == "item_txt_lo:" {
            let e = &entries[first];
            let ofs = e.trim_start_matches("<(item_texts + ").trim_end_matches(')');
            cut_at = Some(ofs.parse::<usize>().unwrap());
        }
        lines[at - 1] = format!(".block {first}");
        lines[at + 1] = format!("    .byte {}", entries[..first].join(", "));
    }
    let cut_at = cut_at.unwrap();
    let at = lines.iter().position(|l| l == "item_texts:").unwrap();
    let end = (at + 1..lines.len())
        .find(|&k| !lines[k].starts_with("    .byte "))
        .unwrap();
    let bytes: Vec<String> = lines[at + 1..end]
        .iter()
        .flat_map(|l| l.trim_start_matches("    .byte ").split(',').map(String::from).collect::<Vec<_>>())
        .collect();
    let rows: Vec<String> = bytes[..cut_at]
        .chunks(16)
        .map(|c| format!("    .byte {}", c.join(",")))
        .collect();
    lines[at - 1] = format!(".block {cut_at}");
    lines.splice(at + 1..end, rows);
    lines.join("\n")
}

/// The text with the switch table's comment as it was: since 2026-10-15
/// the table is the game's —`SWITCH_BYTES` comes from the request's
/// `switch_top`, 1023 in both, so it is 128 as it was— and the comment no
/// longer says ABL's highest.
fn with_the_switch_comment_as_before(text: &str) -> String {
    let now = "; One bit per switch, up to the highest the game names.";
    assert!(text.contains(now));
    assert!(text.contains("\nSWITCH_BYTES = 128\n"));
    text.replace(now, "; One bit per switch. The highest the game checks is 1003.")
}

/// The text without the attributes, which came on 2026-10-15: `ATTR_N` and
/// its six tables, three lines each. The test game carries none, so
/// `ATTR_N` is zero —checked here—, and every item and skill has the empty
/// set's row.
fn without_attributes(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l.starts_with("ATTR_N = ")).unwrap();
    assert_eq!(lines[at], "ATTR_N = 0");
    lines.remove(at);
    for label in [
        "attr_rate:",
        "attr_magic:",
        "attr_sets:",
        "item_attr:",
        "skill_attr:",
        "attr_ranks:",
    ] {
        let at = lines.iter().position(|l| l == label).unwrap();
        if label == "item_attr:" || label == "skill_attr:" {
            let values = lines[at + 1].trim_start_matches("    .word ");
            assert!(values.split(", ").all(|v| v == "0"), "{label}");
        }
        lines.drain(at - 1..=at + 1);
    }
    lines.join("\n")
}

/// The text without what each map forbids, which came on 2026-10-15: the
/// `map_access` table, three lines. The test maps carry no `access`, so
/// every byte is zero —checked here—.
fn without_map_access(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l == "map_access:").unwrap();
    let values = lines[at + 1].trim_start_matches("    .byte ");
    assert!(values.split(", ").all(|v| v == "$00"), "map_access");
    lines.drain(at - 1..=at + 1);
    lines.join("\n")
}

/// The text with `item_k` in bytes as it was: since 2026-10-15 it is a word
/// per RM2k number, $FFFF for one the cartridge does not carry, because
/// ABL's whole game carries 264 items. The test game carries fewer than
/// 255, so each word fits in the byte it was.
fn with_item_k_in_bytes_as_before(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l == "item_k:").unwrap();
    let values: Vec<String> = lines[at + 1]
        .trim_start_matches("    .word ")
        .split(", ")
        .map(|v| if v == "65535" { "255".to_string() } else { v.to_string() })
        .collect();
    assert!(values.iter().all(|v| v.parse::<u32>().unwrap() <= 255));
    lines[at - 1] = format!(".block {}", values.len());
    lines[at + 1] = format!("    .byte {}", values.join(", "));
    lines.join("\n")
}

/// The text without the renames' tables, which came on 2026-10-15: the
/// actors some `ChangeHeroName` renames, the first rename's row and each
/// rename's text. See the runtime's `actor_names.s`.
fn without_names(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l.starts_with("; The actors some ChangeHeroName")).unwrap();
    assert!(lines[at + 6] == "name_actor:");
    lines.drain(at..at + 8);
    let at = lines.iter().position(|l| l == "name_txt:").unwrap();
    lines.drain(at..at + 2);
    lines.join("\n")
}

/// The text without the message's faces, which came on 2026-10-15: the
/// header's five constants with their comment, and the faces' block —the
/// count, the bytes of one, and the pointer table, empty here—. See the
/// runtime's `message_face.s`.
fn without_faces(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l.starts_with("; A box's face, `ChangeFaceGraphic`'s")).unwrap();
    assert!(lines[at + 9].starts_with("MSG_FACE_RIGHT_X = "));
    lines.drain(at..at + 10);
    let at = lines.iter().position(|l| l.starts_with("; The faces of the message window")).unwrap();
    assert!(lines[at + 5] == "message_face_ptr:" && lines[at + 7].is_empty());
    lines.drain(at..at + 8);
    lines.join("\n")
}

/// The text with `PanScreen`'s two operations, as it was: since 2026-10-16
/// the header names all four, because the lock and the unlock compile.
fn without_grid_narrow(text: &str) -> String {
    let line = format!("\nM_GRID_NARROW  = {}", record::grid_narrow_offset());
    assert!(text.contains(&line));
    text.replacen(&line, "", 1)
}

fn with_two_pan_operations_as_before(text: &str) -> String {
    let now = "; PanScreen's four operations.\nPAN_LOCK    = 0\nPAN_UNLOCK  = 1\n";
    assert!(text.contains(now));
    text.replace(now, "; The two PanScreen operations that compile.\n")
}

/// The text without each actor's starting level, which came on 2026-10-16
/// for `ControlVars` from an actor who never fights: its `.block`, the
/// label and the bytes. See the runtime's `actor_stats.s`.
fn without_actor_level(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l == "actor_level:").unwrap();
    assert!(lines[at - 1].starts_with(".block ") && lines[at + 1].starts_with("    .byte "));
    lines.drain(at - 1..at + 2);
    lines.join("\n")
}

/// The text without the skills that shift a rank, which came on
/// 2026-10-18: `ATTR_SHIFT_N`, after `ATTR_N`, and `skill_shifts`, a byte
/// per skill in its `.block`. See the runtime's `battle_attributes.s`.
fn without_attribute_shifts(text: &str) -> String {
    let mut lines: Vec<String> = text.split('\n').map(String::from).collect();
    let at = lines.iter().position(|l| l.starts_with("ATTR_SHIFT_N = ")).unwrap();
    assert!(lines[at - 1].starts_with("ATTR_N = "));
    lines.remove(at);
    let at = lines.iter().position(|l| l == "skill_shifts:").unwrap();
    assert!(lines[at - 1].starts_with(".block ") && lines[at + 1].starts_with("    .byte "));
    lines.drain(at - 1..at + 2);
    lines.join("\n")
}

#[test]
fn a_bare_cartridge_comes_out_as_the_python_wrote_it() {
    let emitted = rm2k_snes_mapdata::emit::emit(&emit_request("bare"), &db()).unwrap();
    let text = with_the_cursors_as_before(&emitted.text, "bare");
    let text = with_item_k_in_bytes_as_before(&with_the_switch_comment_as_before(&without_map_access(&without_attributes(&without_shop_party(&without_faces(&without_attribute_shifts(&text)))))));
    let text = without_collision(&without_title_bpp(&with_the_title_menu_comment_as_before(&without_backdrop_lines(&without_hero_colors(&with_the_turn_as_before(&without_item_up(&without_bare_window(&without_menu_tiles(&without_commons(&with_the_equipment_commons_as_before(&without_pairs(&without_custom_menus(&without_states(&without_skills_screen(&with_whole_poses_as_before(&without_pose_masks(&with_frequency_one_as_before(&with_the_actor_questions_as_before(&without_names(&without_actor_level(&with_two_pan_operations_as_before(&without_grid_narrow(&text)))))))))))))))))))))));
    assert_eq!(text.lines().count(), 3766);
    assert_eq!(
        sha(&text),
        "797dcc5caeacad9f97b9d8345fb7de8b68d4185c568b043113f77db16668703f"
    );
}

#[test]
fn a_whole_cartridge_comes_out_as_the_python_wrote_it() {
    let emitted = rm2k_snes_mapdata::emit::emit(&emit_request("whole"), &db()).unwrap();
    let text = with_the_cursors_as_before(&emitted.text, "whole");
    let text = with_item_k_in_bytes_as_before(&with_the_switch_comment_as_before(&without_map_access(&without_attributes(&without_shop_party(&without_faces(&without_attribute_shifts(&text)))))));
    let text = without_collision(&without_title_bpp(&with_the_title_menu_comment_as_before(&without_backdrop_lines(&without_hero_colors(&with_the_turn_as_before(&without_item_up(&without_bare_window(&without_menu_tiles(&without_commons(&with_the_equipment_commons_as_before(&without_pairs(&without_custom_menus(&without_states(&without_skills_screen(&with_whole_poses_as_before(&without_pose_masks(&with_frequency_one_as_before(&with_the_actor_questions_as_before(&without_names(&without_actor_level(&with_two_pan_operations_as_before(&without_grid_narrow(&text)))))))))))))))))))))));
    assert_eq!(text.lines().count(), 3885);
    assert_eq!(
        sha(&text),
        "274162971159b72a82a386c13bcd1c41e19e1efdd33bf3585f27e13cbeefe384"
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
        value["battle_model"]["troops"].as_array_mut().unwrap().push(model);
        let mut scene = scene_original.clone();
        scene[0] = n.into();
        value["scene"]["troops"].as_array_mut().unwrap().push(scene);
    }
    with_the_skills_screen(&mut value["screens"]);
    with_the_shop_party(&mut value["screens"]);
    with_the_system_cursors(&mut value["screens"], 0);
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
    let starts = text.split("troop_init:\n").nth(1).unwrap().lines().next().unwrap();
    assert!(starts.starts_with("    .word 0, 2, 5, 8, 16, 19, 23, 31,"), "{starts}");
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
    let ids = text.split("troop_id:\n").nth(1).unwrap().lines().next().unwrap();
    assert!(ids.ends_with(", 299, 300"), "{ids}");
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

/// The text with the actor questions of `OP_IF_ACTOR` as they were: since
/// 2026-10-15 there are three, with `COND_ACTOR_HP`, and the comment over
/// them no longer counts them nor points to a Python file.
fn with_the_actor_questions_as_before(text: &str) -> String {
    let now = concat!(
        "; And the actor questions that carry two operands, with their\n",
        "; own opcode: see OP_IF_ACTOR in the events compiler.\n",
        "COND_ACTOR_SKILL = 4\n",
        "COND_ACTOR_EQUIPMENT = 5\n",
        "COND_ACTOR_HP = 3\n",
    );
    let before = concat!(
        "; And the two actor questions that carry two operands, with their\n",
        "; own opcode: see OP_IF_ACTOR in events.py.\n",
        "COND_ACTOR_SKILL = 4\n",
        "COND_ACTOR_EQUIPMENT = 5\n",
    );
    assert!(text.contains(now), "the actor questions should go whole");
    text.replacen(now, before, 1)
}

/// The text with the comment over the title menu's constants as it was:
/// since 2026-10-13 the menu carries tilemaps with and without a save, and
/// the comment says so. What is emitted under it did not change.
fn with_the_title_menu_comment_as_before(text: &str) -> String {
    let now = concat!(
        "; The menu, on BG2 at four bits per pixel: its tile bank and how many\n",
        "; options it has. The cursor isn't drawn separately: there is one\n",
        "; tilemap per option, TITLE_MENU_N without a save and as many with\n",
        "; one after them, and moving it is uploading the other.\n",
    );
    let before = concat!(
        "; The menu, on BG2 at four bits per pixel: its tile bank, how many\n",
        "; options it has and which is selected on entering. The cursor isn't\n",
        "; drawn separately: there is one tilemap per option and moving it is\n",
        "; uploading the other.\n",
    );
    assert!(text.contains(now), "the title menu's comment should go whole");
    text.replacen(now, before, 1)
}

/// The text without `TITLE_BPP` and its comment, and with the two lines of
/// the title's VRAM layout that it changed as they were: they came after
/// the Python (2026-10-12), with the title at 4bpp.
/// The text without the event's touch trigger, which came on 2026-10-14:
/// its constant in the header, with its comment.
fn without_collision(text: &str) -> String {
    let added = concat!(
        "; The event's touch: the hero touching it, or it walking into him.\n",
        "TRIGGER_COLLISION  = 2\n",
    );
    assert!(text.contains(added), "the event's touch trigger should go whole");
    text.replacen(added, "", 1)
}

fn without_title_bpp(text: &str) -> String {
    let added = concat!(
        "; Its bits per pixel: 8, on BG1 in mode 3 with all of CGRAM; or 4,\n",
        "; on BG1 in mode 1 with palettes 1 to 7, when its tiles at 8 don't\n",
        "; fit below the menu's tilemap. Then they take half: 897 at most,\n",
        "; every cell of the screen distinct and the blank one, $3810 words.\n",
        "TITLE_BPP      = 8\n",
    );
    assert!(text.contains(added), "the title's bits per pixel should go whole");
    text.replacen(added, "", 1)
        .replacen(
            "the image tiles start at 0 and end below $4400, so",
            "the image tiles start at 0 and take 15872, so",
            1,
        )
        .replacen(
            ";   $0000 .. $4400   the image's tiles: 544 at 8bpp, or 897 at 4bpp",
            ";   $0000 .. $3E00   the image's 496 tiles, at 8bpp",
            1,
        )
}

/// A title at 4bpp says so to `title.s`, and its row in `screens_table`
/// counts its tiles at 32 bytes and not 64.
#[test]
fn a_title_at_4bpp_counts_its_tiles_at_32_bytes() {
    let row = |request: &Emit| -> (String, String) {
        let text = rm2k_snes_mapdata::emit::emit(request, &db()).unwrap().text;
        let bpp = text.lines().find(|l| l.starts_with("TITLE_BPP")).unwrap().to_string();
        let table = text.split("screens_table:\n").nth(1).unwrap();
        let at = text.lines().find_map(|l| l.strip_prefix("SCREEN_TITLE = ")).unwrap();
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
        ("TITLE_BPP      = 8".to_string(), format!("    .word {}, {}", tiles * 64, colors * 2))
    );
    request.title.as_mut().unwrap().bpp = 4;
    assert_eq!(
        row(&request),
        ("TITLE_BPP      = 4".to_string(), format!("    .word {}, {}", tiles * 32, colors * 2))
    );
}

/// The text without `WINDOW_BACKDROP_LINES`, which came after the Python
/// (2026-10-12): checked here to say the four lines this request's
/// window has, which are not the same.
fn without_backdrop_lines(text: &str) -> String {
    let line = "WINDOW_BACKDROP_LINES = 4\n";
    assert!(text.contains(line), "the window's backdrop should go whole");
    without_window_systems(&text.replacen(line, "", 1))
}

/// And without `WINDOW_SYSTEMS`, which came after it (2026-10-12, for
/// `ChangeSystemGraphics`): one, a cartridge that does not switch, whose
/// window goes with its plain labels and no table.
fn without_window_systems(text: &str) -> String {
    let line = "WINDOW_SYSTEMS = 1\n";
    assert!(text.contains(line), "a cartridge with one System says so");
    assert!(!text.contains("window_systems:"), "one System needs no table");
    text.replacen(line, "", 1)
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
        serde_json::from_str(&std::fs::read_to_string(here().join("tests/maps.json")).unwrap()).unwrap();
    for m in maps["maps"].as_array_mut().unwrap() {
        let id = m["id"].as_i64().unwrap();
        m["sprite"]["timer_mask"] = (id * 3).into();
    }
    value["maps"] = maps["maps"].take();
    with_the_skills_screen(&mut value["screens"]);
    with_the_shop_party(&mut value["screens"]);
    with_the_system_cursors(&mut value["screens"], 0);
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
    assert!(text.contains(&format!(".block {bytes}\nwindow_backdrop:\n")), "one line");

    let (request, bytes) = with_backdrop(|k| if k == 3 { 0xAB } else { 0xAA });
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains("WINDOW_BACKDROP_LINES = 4\n"));
    assert!(text.contains(&format!(".block {}\nwindow_backdrop:\n", bytes * 4)), "all four");
}

/// A cartridge that switches System carries one window per System, all
/// with the text area at the same tile: a smaller frame is padded up to the
/// largest, and its text cells renumbered from there. And the table the
/// runtime finds each one's pieces in.
#[test]
fn a_second_system_s_window_takes_the_largest_frame_s_tile_numbers() {
    let (request, _) = with_backdrop(|_| 0xAA);
    let mut value = serde_json::to_value(&request.screens).unwrap();
    let first = value["window"].clone();
    let base = first["base"].as_i64().unwrap();
    // The other System's frame, two tiles smaller.
    let mut other = first.clone();
    let tiles = first["tiles"].as_str().unwrap();
    other["tiles"] = tiles[..tiles.len() - 2 * 64].into();
    other["base"] = (base - 2).into();
    let cells: Vec<serde_json::Value> = first["cells"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| {
            row.as_array()
                .unwrap()
                .iter()
                .map(|c| {
                    let c = c.as_i64().unwrap();
                    serde_json::Value::from(if c >= base { c - 2 } else { c.min(base - 3) })
                })
                .collect()
        })
        .collect();
    other["cells"] = cells.into();
    value["window"] = first.clone();
    let mut request = request;
    request.screens = value;
    request.window_systems = vec![serde_json::json!({"system": "Other", "window": other})];
    let text = rm2k_snes_mapdata::emit::emit(&request, &db()).unwrap().text;
    assert!(text.contains("WINDOW_SYSTEMS = 2\n"));
    assert!(text.contains(&format!(".block {}\nwindow_tiles_1:\n", base * 32)), "padded to the largest frame");
    assert!(text.contains(".block 48\nwindow_systems:\n"), "two entries of eight pointers");
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
            .flat_map(|l| l[10..].split(',').map(|b| u8::from_str_radix(&b[1..], 16).unwrap()).collect::<Vec<_>>())
            .collect();
        bytes.chunks(2).map(|w| u16::from_le_bytes([w[0], w[1]])).collect()
    };
    let (one, two) = (words("window_cells"), words("window_cells_1"));
    assert_eq!(one.len(), two.len());
    // The tile numbers carry the window base the layout puts in front.
    let tile = |w: u16| i64::from(w & 0x3FF);
    let at = tile(one[0]) - first["cells"][0][0].as_i64().unwrap();
    let mut frame = 0;
    for (a, b) in one.iter().zip(&two) {
        if *a == 0 || tile(*a) - at >= base {
            assert_eq!(a, b, "a text cell, or a blank one, is the same in both");
        } else {
            assert_eq!(tile(*b) - at, (tile(*a) - at).min(base - 3), "a frame cell keeps its own tile");
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
