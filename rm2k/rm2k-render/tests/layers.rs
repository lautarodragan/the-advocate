//! A small map drawn whole: which layer each tile lands on, which families
//! of the ChipSet's animation come out, how a broken map says no, and how a
//! ChipSet is found by name.
//!
//! The map and the ChipSet are generated here, so none of this needs a game.

use rm2k_render::source::find_resource;
use rm2k_render::{picture, Atlas, Bad, Family, Map, Picture};
use std::path::{Path, PathBuf};

/// A ChipSet where every pixel is opaque and differs from its neighbours.
fn chipset() -> Picture {
    let rgba = (0..256usize)
        .flat_map(|y| (0..480usize).flat_map(move |x| [x as u8, y as u8, (x ^ y) as u8, 255]))
        .collect();
    Picture {
        width: 480,
        height: 256,
        rgba,
    }
}

/// A 3x2 map with water, an animated tile and a terrain on the lower layer
/// and one tile drawn above the hero.
const LOWER: [i64; 6] = [0, 3000, 4000, 5000, 5001, 5002];
const UPPER: [i64; 6] = [10000, 10001, 10000, 10000, 10000, 10000];

fn map(lower: &[i64]) -> Map {
    let mut passable_upper = vec![15u8; 144];
    passable_upper[1] = 0x1F; // the star: above the hero
    Map {
        width: 3,
        height: 2,
        lower_layer: lower.to_vec(),
        upper_layer: UPPER.to_vec(),
        passable_lower: vec![15u8; 162],
        passable_upper,
    }
}

#[test]
fn a_map_draws_both_layers_and_each_family_it_uses() {
    let atlas = Atlas::new(&chipset());
    let layers = map(&LOWER).render(&atlas).unwrap();
    assert_eq!((layers.lower.width, layers.lower.height), (48, 32));
    // Cell (1, 0) carries the starred tile, and nothing else is in front.
    assert_eq!(layers.upper.get(16, 0)[3], 255);
    assert_eq!(layers.upper.get(0, 0), [0; 4]);
    assert_eq!(layers.upper.get(32, 16), [0; 4]);
    let families: Vec<(Family, usize)> = layers
        .variants
        .iter()
        .map(|(family, drawings)| (*family, drawings.len()))
        .collect();
    assert_eq!(families, [(Family::Water, 2), (Family::Animated, 3)]);

    // With only plain tiles there is nothing else to draw.
    let layers = map(&[5000; 6]).render(&atlas).unwrap();
    assert!(layers.variants.is_empty());
}

#[test]
fn a_layer_of_the_wrong_size_is_an_answer() {
    let atlas = Atlas::new(&chipset());
    match map(&LOWER[..5]).render(&atlas) {
        Err(Bad::Answer(message)) => {
            assert!(
                message.contains("the lower layer has 5 tiles for a 3x2 map"),
                "{message}"
            )
        }
        Err(other) => panic!("expected an answer, got {other}"),
        Ok(_) => panic!("expected it to be refused"),
    }
}

fn scratch(name: &str) -> PathBuf {
    let dir =
        std::env::temp_dir().join(format!("rm2k-render-layers-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn put(dir: &Path, folder: &str, file: &str) -> PathBuf {
    std::fs::create_dir_all(dir.join(folder)).unwrap();
    let path = dir.join(folder).join(file);
    picture::write_png(&path, &Picture::filled(16, 16, [1, 2, 3, 255])).unwrap();
    path
}

/// RM2k keeps names without extension, and the games were made on
/// Windows: a map says nothing about the real case of a file or a folder.
#[test]
fn a_resource_is_found_whatever_its_case_and_in_the_order_given() {
    let dir = scratch("find");
    let (game, rtp) = (dir.join("game"), dir.join("rtp"));
    let in_game = put(&game, "CHIPSET", "TILES.png");
    put(&rtp, "ChipSet", "tiles.bmp");
    let only_rtp = put(&rtp, "ChipSet", "Other.bmp");
    put(&game, "ChipSet", "notes.txt.png.bak");
    let dirs = [game, rtp, dir.join("nowhere")];
    assert_eq!(find_resource(&dirs, "ChipSet", "Tiles"), Some(in_game));
    assert_eq!(find_resource(&dirs, "ChipSet", "other"), Some(only_rtp));
    assert_eq!(find_resource(&dirs, "ChipSet", "notes.txt"), None);
    assert_eq!(find_resource(&dirs, "Panorama", "Tiles"), None);
    std::fs::remove_dir_all(&dir).unwrap();
}
