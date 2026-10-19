//! A System whose window does not fit in one palette: its background is a
//! gradient of thirty-two reds. Until 2026-10-05 that stopped the whole
//! game —"the window, its arrow and its cursor use N colours and 15
//! fit"—; now Adeleine takes it to fifteen and the window is built.

use rm2k_snes_screens::game::Skin;
use rm2k_snes_screens::Game;
use rm2k_snes_screens::{borders, message_window};
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game")
}

/// The small game's System with a red gradient as the window's background:
/// the System's top-left 32x32 block, one red per row.
fn gradient_skin() -> Skin {
    let game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    let mut skin = game.skin().unwrap();
    let width = skin.picture.width;
    for y in 0..32 {
        for x in 0..32 {
            let at = (y * width + x) * 4;
            skin.picture.rgba[at..at + 4].copy_from_slice(&[(y * 8) as u8, 40, 80, 255]);
        }
    }
    skin
}

#[test]
fn a_window_with_more_colours_than_a_palette_is_reduced() {
    let skin = gradient_skin();
    let (brought, merges) = message_window::reduction(&skin).unwrap();
    assert!(
        brought > 15,
        "the gradient has to overflow the palette: {brought} colours"
    );
    assert_eq!(
        merges.len(),
        brought - 15,
        "Adeleine merges exactly down to fifteen"
    );
    assert_eq!(message_window::colors(&skin).unwrap(), 15);

    let window = message_window::convert(&skin, 16).unwrap();
    assert_eq!(window.cgram.len(), 16);
    // The text keeps colours of its own: every glyph row and the shadow
    // index a palette entry, none the transparent one.
    assert!(window
        .color
        .iter()
        .chain([&window.shadow])
        .all(|&i| (1..16).contains(&i)));
    // And it is deterministic: the same System, the same merges.
    assert_eq!(message_window::reduction(&skin).unwrap().1, merges);
}

#[test]
fn the_text_screens_windows_with_more_colours_than_room_are_reduced() {
    // The 8bpp windows of the item, equipment, shop and actor-choice
    // screens take their colours in a row from an entry; with the gradient
    // they are more than the room, and that used to stop the game too.
    let skin = gradient_skin();
    let screen = borders::Screen {
        background: borders::item_windows(&skin, None),
        bars: vec![],
    };
    let (first, cap) = (128, 144);
    let out = borders::borders(&[screen], 0, first, cap).unwrap();
    assert_eq!(out.colors.len(), cap - first);
}

#[test]
fn a_window_that_fits_loses_nothing() {
    let game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    let skin = game.skin().unwrap();
    let (brought, merges) = message_window::reduction(&skin).unwrap();
    assert!(merges.is_empty());
    assert_eq!(message_window::colors(&skin).unwrap(), brought);
}

/// The small game's System with its first text colour painted one colour
/// per row of the 16x16 block, `shade(row)`: what tells two Systems' text
/// apart.
fn text_skin(shade: impl Fn(usize) -> [u8; 4]) -> Skin {
    let game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    let mut skin = game.skin().unwrap();
    let width = skin.picture.width;
    for y in 0..16 {
        for x in 0..16 {
            let at = ((48 + y) * width + x) * 4;
            skin.picture.rgba[at..at + 4].copy_from_slice(&shade(y));
        }
    }
    skin
}

#[test]
fn two_systems_compose_their_text_with_the_same_entries() {
    // One System's text flat, the other's a gradient in pairs of rows: the
    // font's composed tables carry indices, so both have to give each row
    // the same one, and only their palettes differ.
    let flat = text_skin(|_| [0, 0, 0, 255]);
    let pairs = text_skin(|y| [(y / 2 * 40) as u8, 200, 200, 255]);
    let each = [
        message_window::text_rows(&flat).unwrap(),
        message_window::text_rows(&pairs).unwrap(),
    ];
    assert_eq!(each[0].len(), 1);
    let rows = message_window::common_rows(&each);
    assert_eq!(rows, each[1], "the finer split is the common one");
    let colors = message_window::colors_with(&flat, Some(&rows))
        .unwrap()
        .max(message_window::colors_with(&pairs, Some(&rows)).unwrap());
    let a = message_window::convert_with(&flat, colors + 1, Some(&rows)).unwrap();
    let b = message_window::convert_with(&pairs, colors + 1, Some(&rows)).unwrap();
    assert_eq!((&a.color, a.shadow), (&b.color, b.shadow));
    assert_eq!(a.shadow as usize, rows.len() + 1);
    // The flat one repeats its black in every class's entry.
    assert!(a.cgram[1..=rows.len()].iter().all(|&w| w == a.cgram[1]));
    assert_ne!(a.cgram, b.cgram);
}

#[test]
fn a_system_switched_to_fits_in_what_the_starting_one_takes() {
    // The maps start after the window, so a second System with more
    // colours than the first is reduced to the first's entries, and the
    // maps lose nothing to it.
    let game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    let start = game.skin().unwrap();
    let gradient = gradient_skin();
    let rows = message_window::common_rows(&[
        message_window::text_rows(&start).unwrap(),
        message_window::text_rows(&gradient).unwrap(),
    ]);
    let colors = message_window::colors_with(&start, Some(&rows)).unwrap();
    assert!(message_window::colors_with(&gradient, Some(&rows)).unwrap() > colors);
    let (_, merges) = message_window::reduction_capped(&gradient, Some(&rows), colors).unwrap();
    assert!(!merges.is_empty());
    let window = message_window::convert_with(&gradient, colors + 1, Some(&rows)).unwrap();
    assert!(
        window.cgram[colors + 1..].iter().all(|&w| w == 0),
        "past the starting System's entries"
    );
}
