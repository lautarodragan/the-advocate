//! The screens of a small game against what the Python that drew them
//! until 2026-09-30 answered for the same game: the sha256 of each answer,
//! taken from it before it was deleted.
//!
//! The game is in `tests/game/`: a dump with eight actors —seven with a
//! face, one of them with more colours than a palette holds, and two more
//! faces than palettes—, twelve items of every kind the screens treat
//! apart, the terms with a greeting that takes two lines and a command with
//! a leading space, two maps' worth of message boxes; and its System and
//! FaceSet, made by formula.
//!
//! On 2026-10-02 the message boxes, which were dialogue of the game this
//! was built for, became invented ones, word for word of the same length,
//! and the hash of the box table moved with them. The new table breaks
//! every box at the same places as the Python's, line for line and space
//! for space: the comparison is still against the Python, reworded.
//!
//! On 2026-10-03 the item, equipment and shop screens stopped drawing a
//! letter per cell and compose their text, like the message window: each
//! write goes from its cell one pixel in, and each letter moves the line by
//! its own advance —six pixels with this game's font, eight before—. Their
//! eleven hashes moved, and only the text did: drawn side by side with the
//! old ones, every pixel that differs is a letter's. The same day the
//! names of the menu, the actor choice and the slot screen got composed,
//! and their five hashes moved: side by side, only the names did.
//!
//! On 2026-10-04 the message window took the System's arrow and its cursor
//! —`arrow`, `bar` and `bar_bare`, the arrow's tiles among its own and its
//! colours in its palette—, and the hash of the whole answer moved: without
//! `window`, the answer is the old one byte for byte.
//!
//! And the same day the battle got its windows, `battle_windows`, which the
//! Python never drew: they are taken out before hashing, and checked on
//! their own by `the_battle_windows_fit`.

use rm2k_snes_screens::checks::Vram;
use rm2k_snes_screens::convert::{self, Request};
use rm2k_snes_screens::render::{self, Party, Shop};
use rm2k_snes_screens::{boxes, Game};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game")
}

fn game() -> Game {
    Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap()
}

fn sha(data: &[u8]) -> String {
    Sha256::digest(data).iter().map(|b| format!("{b:02x}")).collect()
}

/// A value as Python's `json.dumps(sort_keys=True, separators=(",", ":"),
/// ensure_ascii=False)` writes it: the keys sorted whatever order the map
/// keeps them in.
fn canon(v: &Value) -> String {
    match v {
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            let fields: Vec<String> = keys
                .iter()
                .map(|k| format!("{}:{}", Value::from(k.as_str()), canon(&map[*k])))
                .collect();
            format!("{{{}}}", fields.join(","))
        }
        Value::Array(items) => format!("[{}]", items.iter().map(canon).collect::<Vec<_>>().join(",")),
        other => other.to_string(),
    }
}

/// The layouts of a real cartridge's BG1 banks.
fn vram() -> Vram {
    Vram {
        slot_vram: 0x2000,
        slot_map: 0x3C00,
        bg1_banks: vec![("WINDOW".into(), 0x1000, 0x5000), ("WINDOW_BG".into(), 0x1000, 0x5000)],
    }
}

#[test]
fn everything_a_cartridge_carries() {
    let request = Request {
        slots: 4,
        actors: (1..=8).collect(),
        items: (1..=12).collect(),
        title: true,
        cgram_reserved: 9,
        vram: vram(),
        menus: Vec::new(),
        menu_context: Default::default(),
    };
    let mut answer = convert::convert(&game(), &request).unwrap();
    // The geometry is constants, and the Python had them as its own.
    answer.as_object_mut().unwrap().remove("layout");
    // And without custom menus, what goes of them is their geometry too:
    // they came on 2026-10-04, and the Python never had them.
    answer.as_object_mut().unwrap().remove("custom_menus");
    answer.as_object_mut().unwrap().remove("battle_windows");
    let says: Vec<Value> = answer["says"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| !s.as_str().unwrap().starts_with("  battle windows:"))
        .cloned()
        .collect();
    answer["says"] = Value::from(says);
    // The actor choice is no longer the Python's since 2026-09-30: whom to
    // equip is chosen on the pause menu, over nothing, which adds that bar's
    // tiles and rectangle, and the choice without an item and its erased
    // cells went away. Everything else is still the Python's, but the
    // message window's font, which since 2026-10-03 carries eight phases
    // and not four, the cursor's blank, and each glyph's advance and reach:
    // the font got variable width, and this game draws with RM2k's, the
    // fixed one, so the rest of what it draws did not move. Nor the item,
    // equipment and shop screens' font, also since 2026-10-03: they compose
    // their text, so what goes is `text_inks` —their palettes and the font
    // precomposed for them— instead of a font bank, and the windows' tiles
    // go at the end of the bank instead of after the font. And the names of
    // the menu, the actor choice and the slot screen are composed too: the
    // menu's bank carries only the numbers' glyphs, and the font
    // precomposed for its text palette.
    assert_eq!(
        sha(canon(&answer).as_bytes()),
        "cf1cf4d5254114b1b4ca7ba199aef123e0dbb2206d58ed0430bf314754da1b8d"
    );
    assert_eq!(
        answer["says"],
        serde_json::json!([
            "  menu bank: 255 tiles of 448; the composed names ask for 62 of the 192 the menu leaves \
             and 48 of the 192 the slot screen does",
            "  WARNING, 1 actor names in the menu don't fit in 13 cells (104 px) and are cut: \
             \"Bobby-Longname\" 84 px, shows \"Bobby-Longnam\"",
            "  WARNING, 1 leader names in the slot screen don't fit in 7 cells (56 px) and are cut: \
             \"Bobby-Longname\" 84 px, shows \"Bobby-L\"",
            "  WARNING, 1 medicine names in the actor choice don't fit in two lines of 11 cells and \
             are cut: \"Hi-Potion Deluxe Extra\" 132 px, shows \"Hi-Potion / Deluxe\"",
            "  shop text: its lists ask for 127 pairs of tiles at most, of the 191 of the pool",
            "  faces without a palette of their own, drawn with another's: Gus"
        ])
    );
}

/// A game that uses the RTP's System and faces does not ship them: they
/// are looked for in the RTP after the game's folder, and in any case, as
/// RPG_RT finds them on Windows.
#[test]
fn the_system_and_the_faces_come_from_the_rtp_too() {
    let tmp = std::env::temp_dir().join(format!("screens-rtp-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&tmp);
    let (empty, rtp) = (tmp.join("game"), tmp.join("rtp"));
    std::fs::create_dir_all(&empty).unwrap();
    std::fs::create_dir_all(rtp.join("system")).unwrap();
    std::fs::create_dir_all(rtp.join("FACESET")).unwrap();
    std::fs::copy(here().join("pictures/System/Skin.png"), rtp.join("system/SKIN.PNG")).unwrap();
    std::fs::copy(here().join("pictures/FaceSet/Faces.png"), rtp.join("FACESET/faces.png")).unwrap();
    let from_game = game();
    let mut game = Game::from_dump(&here().join("dump"), &empty).unwrap();
    assert!(game.skin().is_err(), "without the RTP there is no System");
    game.rtp_dir = Some(rtp);
    assert_eq!(game.skin().unwrap().picture.rgba, from_game.skin().unwrap().picture.rgba);
    assert_eq!(game.face(1).unwrap().unwrap().rgba, from_game.face(1).unwrap().unwrap().rgba);
    let _ = std::fs::remove_dir_all(&tmp);
}

/// The battle's windows of the small game: every layout's band, its bars
/// and the description's window, in the tiles and colours they have.
#[test]
fn the_battle_windows_fit() {
    let skin = game().skin().unwrap();
    let windows = rm2k_snes_screens::battle::battle_windows(&skin).unwrap();
    let tiles = windows["tiles"].as_array().unwrap().len();
    assert!(tiles > 0 && tiles <= rm2k_snes_screens::battle::BATTLE_WINDOW_TILES_MAX);
    let band = windows["band"].as_array().unwrap();
    assert_eq!(band.len(), 3);
    assert!(band.iter().all(|b| b.as_array().unwrap().len() == 12 * 32));
    assert_eq!(windows["help"].as_array().unwrap().len(), 4 * 32);
    // Every bar draws something, inside the band.
    for sets in windows["bars"].as_array().unwrap() {
        for bar in sets.as_array().unwrap().iter().flat_map(|s| s.as_array().unwrap()) {
            let b: Vec<i64> = bar.as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect();
            assert!(b[0] >= 16 && b[0] + b[2] <= 28 && b[3] > 0, "{b:?}");
        }
    }
}

#[test]
fn names_that_do_not_fit_in_the_bank_are_refused() {
    // The names are composed, each in tiles of its own: a save in each of
    // many slots asks for one name per slot, and the bank's free tiles run
    // out before its rows do.
    let request = Request {
        slots: 24,
        actors: (1..=8).collect(),
        items: (1..=12).collect(),
        title: true,
        cgram_reserved: 9,
        vram: vram(),
        menus: Vec::new(),
        menu_context: Default::default(),
    };
    let bad = convert::convert(&game(), &request).unwrap_err();
    assert!(bad.message().contains("has no room for the composed names"), "{}", bad.message());
}

fn inventory() -> BTreeMap<i32, i64> {
    [(1, 3), (2, 1), (3, 99), (4, 1), (5, 2), (6, 2), (7, 1), (8, 1), (9, 1), (10, 4), (11, 1), (12, 7)]
        .into_iter()
        .collect()
}

fn check(name: &str, picture: rm2k_render::Picture, expected: &str) {
    assert_eq!(sha(&picture.rgba), expected, "{name}");
}

#[test]
fn the_screens_as_the_console_shows_them() {
    let game = game();
    let skin = game.skin().unwrap();
    let party = |members: &[i32]| Party {
        members: members.to_vec(),
        ..Default::default()
    };
    check(
        "menu",
        render::menu(&game, &skin, 4, &party(&[1, 2, 5]), 1234, 2, false, None).unwrap(),
        "9be153547f5801a44405f80a8c40af7a4265c3de66267840428cbcf8326b9c31",
    );
    // Choosing whom to equip, with the bar on the second row: not drawn by
    // the Python, which never had it.
    check(
        "menu-choosing",
        render::menu(&game, &skin, 4, &party(&[1, 2, 5]), 1234, 2, false, Some(1)).unwrap(),
        "cc15356f28270b4bf12387faefabf594c2537de5cb1f38fc2095934e561e077d",
    );
    let state = Party {
        members: vec![2, 7, 8, 4],
        actors: Some((1..=8).collect()),
        hp: [(2, 5), (7, 1234)].into_iter().collect(),
        levels: [(2, 11), (4, 17)].into_iter().collect(),
        exps: [(2, 900), (4, 20000)].into_iter().collect(),
    };
    check(
        "menu-state",
        render::menu(&game, &skin, 4, &state, 999_999, 0, true, None).unwrap(),
        "37d1429fee0998e968c439826ba89ddd9f1b9a113a9b9d2a01c4c0f0dc7ee692",
    );
    check(
        "target-item",
        render::target(&game, &skin, 4, &party(&[1, 2, 3]), 2, 2, 7).unwrap(),
        "bf25611db7907c38abe48a1e1616d13cf43a9c9d30fdce78cbe92774332a5fe2",
    );
    check(
        "items",
        render::item_screen(&game, &skin, &inventory(), 11, 2, None).unwrap(),
        "76f0b4e08732bb3c137e0a1d55b9d5ce5177cadd48c90b26ede01e102a8a26de",
    );
    let parties: BTreeMap<usize, Vec<i32>> = [(0, vec![2, 1]), (2, vec![7, 8, 3, 4])].into_iter().collect();
    let levels: BTreeMap<usize, i64> = [(0, 9)].into_iter().collect();
    check(
        "slots",
        render::slot_screen(&game, &skin, 4, &[true, false, true, false], 2, 1, &parties, &levels).unwrap(),
        "e95f191de94803a8ca0001347e6c3329c3fa839329783b6920aecb30e21a4b85",
    );
    let worn = [6, 8, 0, 10, 0];
    check(
        "equipment",
        render::equipment_screen(&game, &skin, 1, &worn, &inventory(), 0, false, 0, 0, None).unwrap(),
        "81af83c5e9cce8ddf6bcf5d0778a3d1ccecf903e6ca6dcceda52ad57cebcae3d",
    );
    check(
        "equipment-list",
        render::equipment_screen(&game, &skin, 1, &worn, &inventory(), 0, true, 1, 0, None).unwrap(),
        "5ccf555d7e01bed1c0443bba68ec9df6b8a30b72077dd775c2db979ee115b3e4",
    );
    check(
        "equipment-shield",
        render::equipment_screen(&game, &skin, 3, &[7, 0, 0, 0, 0], &inventory(), 1, true, 0, 0, None)
            .unwrap(),
        "3baca089f32ec028d2163de659bbc40853673e9d1ccaba462de57c6180e2688c",
    );
    let shops = [
        "13b51254f6df0f15ec4f5b21d0d642515d2d3afc3c3fa05455ab9e13abc50e8e",
        "dd4c797796e9c51583db3963d717d6838320dd5f236656030326d9099e1dbc33",
        "37819e041016ffd87a5eabba5eb6a929ce05da6020a30af470112bded8fac46d",
        "0872e29ee5bac1f1a97684ae4336e5e06be318dc5d54237ba0a3d228dcb0d7ad",
        "903e435c5112f166089770de8f8573f3b2dcfbd66127af9cb2f1c4765e1dc890",
        "7dfa656f02e6de79ff6920a195ba5e92d9ef78587dcadc5a49743a285f0857e1",
        "8805f617eba61c1629705f7518f077344772b4ecafa499eaa179a0bf83c132f3",
    ];
    for (mode, expected) in shops.iter().enumerate() {
        let shop = Shop {
            kind: 0,
            term_set: 1,
            sells: vec![6, 7, 8, 1, 3],
            gold: 350,
            inventory: inventory(),
            party_equipment: vec![worn.to_vec(), vec![0, 8, 9, 0, 11]],
            mode,
            chosen: 1,
            top: 0,
            count: 3,
            regreeting: mode == 0,
            known: None::<BTreeSet<i32>>,
        };
        check(&format!("shop-{mode}"), render::shop_screen(&game, &skin, &shop).unwrap(), expected);
    }
    check(
        "end-0",
        render::end_game_screen(&game, &skin, 0).unwrap(),
        "3b83320609808d9cffa8e47798fa285c7d0ef63b814eb38afca6fdc5cf5bb876",
    );
    check(
        "end-1",
        render::end_game_screen(&game, &skin, 1).unwrap(),
        "0a96d734d2536862fc0e8f097564e8529472a0d7cfdc0981c02d528d51f958e2",
    );
}

#[test]
fn the_boxes_of_the_maps_and_the_common_events() {
    let table = boxes::table(&here().join("dump"), &[], &rm2k_snes_text::refit::Measure::columns(39), 4).unwrap();
    assert_eq!(table.as_array().unwrap().len(), 4);
    assert_eq!(
        sha(canon(&table).as_bytes()),
        "ef4a9e02b7c689eec2138eca765a9dfa986992d00a0bbad34118c11e68856576"
    );
}
