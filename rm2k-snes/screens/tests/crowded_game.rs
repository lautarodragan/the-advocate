//! The screens of a small game made to crowd them.
//!
//! The game is in `tests/game/`: a dump with eight actors —seven with a
//! face, one of them with more colours than a palette holds, and two more
//! faces than palettes—, twelve items of every kind the screens treat
//! apart, the terms with a greeting that takes two lines and a command with
//! a leading space, two maps' worth of message boxes; and its System and
//! FaceSet, made by formula.
//!
//!
//! **The paths they guard**: what a game's build does not reach, or does
//! not say. A Blurred Line's suite holds the console's screens against
//! `render` —menu, items, target, slots, equipment, shop, End Game,
//! title— and the message window against its goldens; what is here is what
//! that game does not have: names that do not fit, a face with no palette
//! of its own, a bank that runs out of room, the System and the faces
//! found in the RTP, and the windows' geometry.

use rm2k_snes_screens::checks::Vram;
use rm2k_snes_screens::convert::{self, Request};
use rm2k_snes_screens::{boxes, Game};
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game")
}

fn game() -> Game {
    Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap()
}

/// The layouts of a real cartridge's BG1 banks.
fn vram() -> Vram {
    Vram {
        slot_vram: 0x2000,
        slot_map: 0x3C00,
        bg1_banks: vec![
            ("WINDOW".into(), 0x1000, 0x5000),
            ("WINDOW_BG".into(), 0x1000, 0x5000),
        ],
    }
}

/// What the conversion says of the small game: how full the menu's bank
/// is, the two names cut, the shop's pool, and the face drawn with
/// another's palette.
#[test]
fn what_a_crowded_game_is_told() {
    let request = Request {
        slots: 4,
        actors: (1..=8).collect(),
        items: (1..=12).collect(),
        title: true,
        cgram_reserved: 9,
        letters: Vec::new(),
        screen_letters: Vec::new(),
        vram: vram(),
        menus: Vec::new(),
        menu_context: Default::default(),
        text_rows: None,
        names: Vec::new(),
        debug: false,
    };
    let answer = convert::convert(&game(), &request).unwrap();
    assert_eq!(
        answer["says"],
        serde_json::json!([
            "  menu bank: 238 tiles of 448; the composed names ask for 90 of the 210 the menu leaves \
             and 80 of the 210 the slot screen does",
            "  WARNING, 1 actor names in the menu don't fit in 13 cells (104 px) and are cut: \
             \"Bobby-Longname\" 84 px, shows \"Bobby-Longnam\"",
            "  WARNING, 1 leader names in the slot screen don't fit in 13 cells (104 px) and are cut: \
             \"Bobby-Longname\" 84 px, shows \"Bobby-Longnam\"",
            "  shop text: its lists ask for 127 pairs of tiles at most, of the 191 of the pool",
            "  faces without a palette of their own, drawn with another's: Gus",
            "  item text: its busiest list asks for 139 pairs of tiles at most, of the 365 the item \
             and equipment screens have —173 below their windows and 192 of the map's—: items 1, \
             2, 3, 4, 6, 7, 8, 9, 11, 12, at 99, with the description of 3",
            "  battle windows: 34 tiles of 192, 4 colours of 16, 224 words of bars",
            "  skills screen: 16 tiles of windows, and a page asks for 0 pairs of tiles at most, of \
             the 447 of its pool"
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
    std::fs::copy(
        here().join("pictures/System/Skin.png"),
        rtp.join("system/SKIN.PNG"),
    )
    .unwrap();
    std::fs::copy(
        here().join("pictures/FaceSet/Faces.png"),
        rtp.join("FACESET/faces.png"),
    )
    .unwrap();
    let from_game = game();
    let mut game = Game::from_dump(&here().join("dump"), &empty).unwrap();
    assert!(game.skin().is_err(), "without the RTP there is no System");
    game.rtp_dir = Some(rtp);
    assert_eq!(
        game.skin().unwrap().picture.rgba,
        from_game.skin().unwrap().picture.rgba
    );
    assert_eq!(
        game.face(1).unwrap().unwrap().rgba,
        from_game.face(1).unwrap().unwrap().rgba
    );
    let _ = std::fs::remove_dir_all(&tmp);
}

/// The skills screen's windows: they fit, the
/// tilemap is a whole screen, and each of the sixteen places has its bar as
/// two half rows that differ from the arrangement's.
#[test]
fn the_skills_screen_windows_fit() {
    let skin = game().skin().unwrap();
    let windows = rm2k_snes_screens::skills::windows_json(&skin).unwrap();
    let tiles = windows["tiles"].as_array().unwrap().len();
    assert!(tiles > 0 && tiles <= rm2k_snes_screens::skills::SK_TILES_MAX);
    let map: Vec<i64> = windows["map"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_i64().unwrap())
        .collect();
    assert_eq!(map.len(), 32 * 28);
    let bars: Vec<i64> = windows["bars"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_i64().unwrap())
        .collect();
    assert_eq!(bars.len(), 16 * 2 * 16);
    for (p, bar) in bars.chunks(32).enumerate() {
        let row0 = 11 + 2 * (p / 2);
        let col0 = 16 * (p % 2);
        let under: Vec<i64> = (0..2)
            .flat_map(|r| map[(row0 + r) * 32 + col0..(row0 + r) * 32 + col0 + 16].to_vec())
            .collect();
        assert_ne!(bar, under.as_slice(), "the bar on place {p} draws nothing");
    }
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
        for bar in sets
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|s| s.as_array().unwrap())
        {
            let b: Vec<i64> = bar
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_i64().unwrap())
                .collect();
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
        letters: Vec::new(),
        screen_letters: Vec::new(),
        vram: vram(),
        menus: Vec::new(),
        menu_context: Default::default(),
        text_rows: None,
        names: Vec::new(),
        debug: false,
    };
    let bad = convert::convert(&game(), &request).unwrap_err();
    assert!(
        bad.message().contains("has no room for the composed names"),
        "{}",
        bad.message()
    );
}

/// The two maps' boxes and the common events', in one table.
#[test]
fn the_boxes_of_the_maps_and_the_common_events() {
    let table = boxes::table(
        &here().join("dump"),
        &[],
        &rm2k_snes_text::refit::Measure::columns(39),
        4,
    )
    .unwrap();
    assert_eq!(table.as_array().unwrap().len(), 4);
}
