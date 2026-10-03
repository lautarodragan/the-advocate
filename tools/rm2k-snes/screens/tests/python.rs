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
        bank_items: vec![1, 3, 4],
        title: true,
        cgram_reserved: 9,
        vram: vram(),
    };
    let mut answer = convert::convert(&game(), &request).unwrap();
    // The geometry is constants, and the Python had them as its own.
    answer.as_object_mut().unwrap().remove("layout");
    // The actor choice is no longer the Python's since 2026-09-30: whom to
    // equip is chosen on the pause menu, over nothing, which adds that bar's
    // tiles and rectangle, and the choice without an item and its erased
    // cells went away. Everything else is still the Python's, but the
    // message window's font, which since 2026-10-03 carries eight phases
    // and not four, the cursor's blank, and each glyph's advance and reach:
    // the font got variable width, and this game draws with RM2k's, the
    // fixed one, so the rest of what it draws did not move.
    assert_eq!(
        sha(canon(&answer).as_bytes()),
        "0236f833f14f862f4d5f8c57d6e0580e2094eb20943a47238ef65c4291128ea6"
    );
    assert_eq!(
        answer["says"],
        serde_json::json!(["  faces without a palette of their own, drawn with another's: Gus"])
    );
}

#[test]
fn a_medicine_whose_letters_the_bank_lacks_is_refused() {
    // Without Elixir in the bank nobody has an "x" or an "r", and the
    // medicine 2 has both: the actor choice would draw a gap.
    let request = Request {
        slots: 4,
        actors: (1..=8).collect(),
        items: (1..=12).collect(),
        bank_items: vec![1, 4],
        title: true,
        cgram_reserved: 9,
        vram: vram(),
    };
    let bad = convert::convert(&game(), &request).unwrap_err();
    assert!(bad.message().contains("the menu's bank does not carry: \"xr\""), "{}", bad.message());
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
        "385725e4540ce73c8cc0f936c8ecc3540574c8a1e0325e1a506ae806498b6531",
    );
    // Choosing whom to equip, with the bar on the second row: not drawn by
    // the Python, which never had it.
    check(
        "menu-choosing",
        render::menu(&game, &skin, 4, &party(&[1, 2, 5]), 1234, 2, false, Some(1)).unwrap(),
        "7aeb78f03237b9a6aea75bf9d02712061d9e093fcd200fa975190f680903d858",
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
        "dc9748330fd80647a550df9481f80ce7dd52a4aeaa7bea99cfa5776e2739c21b",
    );
    check(
        "target-item",
        render::target(&game, &skin, 4, &party(&[1, 2, 3]), 2, 2, 7).unwrap(),
        "1fe4cd2469ae066fa13905f97412cb005694dacda7e48a2dae7e36881caf0867",
    );
    check(
        "items",
        render::item_screen(&game, &skin, &inventory(), 11, 2, None).unwrap(),
        "7f7bcde9837c874a79cbe539c0528a60b76912e01ca52434b6ce3230d680eff3",
    );
    let parties: BTreeMap<usize, Vec<i32>> = [(0, vec![2, 1]), (2, vec![7, 8, 3, 4])].into_iter().collect();
    let levels: BTreeMap<usize, i64> = [(0, 9)].into_iter().collect();
    check(
        "slots",
        render::slot_screen(&game, &skin, 4, &[true, false, true, false], 2, 1, &parties, &levels).unwrap(),
        "8ddb935e9fbe72002c9bcf071392cac78cbd9bbb2f61ed3b24297402b5bdc345",
    );
    let worn = [6, 8, 0, 10, 0];
    check(
        "equipment",
        render::equipment_screen(&game, &skin, 1, &worn, &inventory(), 0, false, 0, 0, None).unwrap(),
        "4c13c8b3fed040302a29ae13acc52a73b6e94501f61986f013dd296a791e2256",
    );
    check(
        "equipment-list",
        render::equipment_screen(&game, &skin, 1, &worn, &inventory(), 0, true, 1, 0, None).unwrap(),
        "0b14e82e1bd2d68ae25ff92b7f4d6e66c9cf6a8c6b0b71265b34e181f39b0b05",
    );
    check(
        "equipment-shield",
        render::equipment_screen(&game, &skin, 3, &[7, 0, 0, 0, 0], &inventory(), 1, true, 0, 0, None)
            .unwrap(),
        "7d4423e5b18aa1946d3c738184e25b35a9177b51d147c772ad9f68027cdf82d6",
    );
    let shops = [
        "43f23ea46270479c79f952261e34930755635c0b00b39d3737a618ce0416aed9",
        "f9785d837afcd59cec979954107f07ab7ae5578e23dbe60bacbeb81cf1cc72e0",
        "7c6bdda3fba78f4c5ad2c76751fa392433cfba4eb0fc1deffa931f4d72efa285",
        "3fd2366e9f00996df2d0985d2c77f1cf95d20d1fbf9692178eb6ca6af4ea94b9",
        "c14e7a6fe51ffa0735896dddf1a9a4c68c9385651d08278dcff327c10761d616",
        "aa0fe57718f293b2a8d44982fbfb3fff9250c40ff25fa13262c2384a87789819",
        "f85085eba46c408ef786f4bfb43279752c99be4db53d0be61ac8566bcc2c7f2d",
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
