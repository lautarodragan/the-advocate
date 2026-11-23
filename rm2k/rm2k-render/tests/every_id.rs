//! A map generated inside this file drawn whole, over two ChipSets
//! generated too: it needs no game and no RTP.
//!
//! The inputs are built to touch everything: every water, terrain and
//! animated family and every combination id, including the ones past the
//! 47 the atlas has per frame; plain tiles past the end of a page; tiles on
//! both sides of the hero; and two ChipSets, an indexed one —the colour key
//! at index 0— and an RGBA one with half-transparent pixels, which is the
//! only case where the rounding of the blend shows.
//!
//!
//! **The path it guards**: the ids no game's map holds —combinations past
//! the 47 of a frame, plain tiles past the end of a page— and an RGBA
//! ChipSet, which RM2k's games do not bring. What a real map looks like is
//! A Blurred Line's goldens'. What is checked is that it is drawn whole:
//! both layers the map's size, and each family's drawings that size too.

mod common;

use common::{indexed_chipset, rgba_chipset};
use rm2k_render::{picture, Atlas, Family, Map};
use std::path::PathBuf;

const WIDTH: usize = 48;
const HEIGHT: usize = 32;

fn map() -> Map {
    let mut lower: Vec<i64> = Vec::new();
    for kind in 0..3 {
        for sub in [0, 7, 19] {
            for comb in 0..50 {
                lower.push(kind * 1000 + sub * 50 + comb);
            }
        }
    }
    lower.extend(3000..3150);
    lower.extend(4000..4600);
    lower.extend(5000..5144);
    let cells = WIDTH * HEIGHT;
    let missing = cells - lower.len();
    lower.extend((0..missing).map(|i| 5000 + (i % 144) as i64));
    let upper = (0..cells)
        .map(|i| {
            if i % 3 == 0 {
                4000 + (i % 600) as i64
            } else {
                10000 + (i % 150) as i64
            }
        })
        .collect();
    Map {
        width: WIDTH,
        height: HEIGHT,
        lower_layer: lower,
        upper_layer: upper,
        passable_lower: (0..162usize)
            .map(|i| match i {
                3 => 0x0F,
                4 => 0x30,
                5 => 0x0A,
                _ => ((i * 29 + 3) % 256) as u8,
            })
            .collect(),
        passable_upper: (0..144usize).map(|i| ((i * 53 + 7) % 256) as u8).collect(),
    }
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-render-test-{}-{name}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn a_map_of_every_id_is_drawn_whole_over_both_chipsets() {
    for (name, write) in [
        ("indexed", indexed_chipset as fn(&std::path::Path)),
        ("rgba", rgba_chipset),
    ] {
        let dir = scratch(name);
        let path = dir.join("chipset.png");
        write(&path);
        let atlas = Atlas::new(&picture::read_rm2k(&path).unwrap());
        let layers = map().render(&atlas).unwrap();
        std::fs::remove_dir_all(&dir).unwrap();
        for (layer, picture) in [("lower", &layers.lower), ("upper", &layers.upper)] {
            assert_eq!(
                (picture.width, picture.height),
                (WIDTH * 16, HEIGHT * 16),
                "{name}: {layer}"
            );
        }
        assert_eq!(
            layers.variants.iter().map(|(f, _)| *f).collect::<Vec<_>>(),
            vec![Family::Water, Family::Animated],
            "{name}"
        );
        for (family, drawings) in &layers.variants {
            assert!(!drawings.is_empty(), "{name}: {}", family.name());
            for d in drawings {
                assert_eq!(
                    (d.width, d.height),
                    (layers.lower.width, layers.lower.height),
                    "{name}: a drawing of {}",
                    family.name()
                );
            }
        }
    }
}
