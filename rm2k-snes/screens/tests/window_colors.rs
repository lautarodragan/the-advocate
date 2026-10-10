//! A System whose window does not fit in one palette: its background is a
//! gradient of thirty-two reds. Until 2026-10-05 that stopped the whole
//! game —"the window, its arrow and its cursor use N colours and 15
//! fit"—; now Adeleine takes it to fifteen and the window is built.

use rm2k_snes_screens::{borders, message_window};
use rm2k_snes_screens::game::Skin;
use rm2k_snes_screens::Game;
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
    assert!(brought > 15, "the gradient has to overflow the palette: {brought} colours");
    assert_eq!(merges.len(), brought - 15, "Adeleine merges exactly down to fifteen");
    assert_eq!(message_window::colors(&skin).unwrap(), 15);

    let window = message_window::convert(&skin, 16).unwrap();
    assert_eq!(window.cgram.len(), 16);
    // The text keeps colours of its own: every glyph row and the shadow
    // index a palette entry, none the transparent one.
    assert!(window.color.iter().chain([&window.shadow]).all(|&i| (1..16).contains(&i)));
    // And it is deterministic: the same System, the same merges.
    assert_eq!(message_window::reduction(&skin).unwrap().1, merges);
}

#[test]
fn the_text_screens_windows_with_more_colours_than_room_are_reduced() {
    // The 8bpp windows of the item, equipment, shop and actor-choice
    // screens take their colours in a row from an entry; with the gradient
    // they are more than the room, and that used to stop the game too.
    let skin = gradient_skin();
    let screen = borders::Screen { background: borders::item_windows(&skin, None), bars: vec![] };
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
