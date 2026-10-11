//! A System whose windows have a gradient behind a frame that lets it
//! through: Book of Three's, Frozen World's, Vampires Dawn's. Stretched as
//! RM2k stretches it, every row of the gradient is a cell of its own, and
//! until 2026-10-11 that stopped the game —"the window needs 266 tiles —26
//! of its frame and its arrow— and the bank has 256", "the actor choice's
//! windows are 96 8bpp tiles and reach $4C00"—. Now the message window's
//! frame shows the gradient in bands, and the screens that cut their
//! windows into a bank merge their cells that show the least until it holds
//! them.

use rm2k_render::picture::{self, Picture};
use rm2k_rules::system::{BACKGROUND, EDGE, FRAME, PIECE};
use rm2k_snes_screens::checks::Vram;
use rm2k_snes_screens::convert::{self, Request};
use rm2k_snes_screens::Game;
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game")
}

/// The small game's System, with a gradient of reds by row as its
/// background, and the inner half of each edge of the frame see-through.
fn gradient_system() -> Picture {
    let game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    let mut system = game.skin().unwrap().picture;
    let width = system.width;
    let at = |x: i32, y: i32| (y as usize * width + x as usize) * 4;
    for y in 0..PIECE {
        for x in 0..PIECE {
            let p = at(BACKGROUND.0 + x, BACKGROUND.1 + y);
            system.rgba[p..p + 4].copy_from_slice(&[(y * 8) as u8, 40, 80, 255]);
        }
    }
    for y in 0..PIECE {
        for x in 0..PIECE {
            let inner = |v: i32| (EDGE / 2..EDGE).contains(&v) || (PIECE - EDGE..PIECE - EDGE / 2).contains(&v);
            let corner = (x < EDGE || x >= PIECE - EDGE) && (y < EDGE || y >= PIECE - EDGE);
            if !corner && (inner(x) || inner(y)) {
                let p = at(FRAME.0 + x, FRAME.1 + y);
                system.rgba[p + 3] = 0;
            }
        }
    }
    system
}

fn game_with(system: &Picture, name: &str) -> Game {
    let path = std::env::temp_dir().join(format!("rm2k-snes-screens-{}-{name}.png", std::process::id()));
    picture::write_png(&path, system).unwrap();
    let mut game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    game.use_system(path.to_str().unwrap());
    game
}

fn request() -> Request {
    Request {
        slots: 4,
        actors: (1..=8).collect(),
        items: (1..=12).collect(),
        title: false,
        cgram_reserved: 16,
        vram: Vram {
            slot_vram: 0x2000,
            slot_map: 0x3C00,
            bg1_banks: vec![("WINDOW".into(), 0x1000, 0x4C00)],
        },
        menus: Vec::new(),
        menu_context: Default::default(),
    }
}

#[test]
fn a_gradient_behind_the_frame_fits_every_bank() {
    let game = game_with(&gradient_system(), "fits");
    let answer = convert::convert(&game, &request()).unwrap();
    let says: Vec<&str> = answer["says"].as_array().unwrap().iter().map(|s| s.as_str().unwrap()).collect();
    for what in ["the message window's frame", "the actor choice's windows"] {
        assert!(
            says.iter().any(|s| s.contains("WARNING") && s.contains(what)),
            "{what} should have been fused: {says:#?}"
        );
    }
    // The frame and the arrow, before the text area's 240.
    assert!(answer["window"]["base"].as_u64().unwrap() <= 16);
    // And the same System gives the same cartridge.
    assert_eq!(convert::convert(&game, &request()).unwrap(), answer);
}
