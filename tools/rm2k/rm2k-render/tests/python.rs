//! The drawings against the ones they replace.
//!
//! Until this crate existed, the same layers were drawn by a Python port of
//! the same code. It was deleted once the two gave the same pixels on every
//! map of a whole game; what is left of it is here: the SHA-256 of what it
//! drew for a ChipSet and a map generated inside this file, which need no
//! game and no RTP.
//!
//! The inputs are built to touch everything: every water, terrain and
//! animated family and every combination id, including the ones past the
//! 47 the atlas has per frame; plain tiles past the end of a page; tiles on
//! both sides of the hero; and two ChipSets, an indexed one —the colour key
//! at index 0— and an RGBA one with half-transparent pixels, which is the
//! only case where the rounding of the blend shows.
//!
//! **If one of these changes, a pixel changed.** The hashes are not to be
//! regenerated to make a test pass: the Python that produced them is gone,
//! and with it the only independent answer.

mod common;

use common::{indexed_chipset, rgba_chipset, sha};
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

/// Draws everything for one ChipSet and checks it against the hashes, in the
/// order: the atlas, lower, upper, then each family's drawings 1 and up.
fn check(name: &str, write: fn(&std::path::Path), expected: [&str; 8]) {
    let dir = scratch(name);
    let path = dir.join("chipset.png");
    write(&path);
    let atlas = Atlas::new(&picture::read_rm2k(&path).unwrap());
    let layers = map().render(&atlas).unwrap();
    let mut got = vec![
        ("atlas".to_string(), sha(&atlas.picture)),
        ("lower".to_string(), sha(&layers.lower)),
        ("upper".to_string(), sha(&layers.upper)),
    ];
    assert_eq!(
        layers.variants.iter().map(|(f, _)| *f).collect::<Vec<_>>(),
        vec![Family::Water, Family::Animated]
    );
    for (family, drawings) in &layers.variants {
        for (i, drawing) in drawings.iter().enumerate() {
            got.push((format!("{}-{}", family.name(), i + 1), sha(drawing)));
        }
    }
    let wrong: Vec<String> = got
        .iter()
        .zip(expected)
        .filter(|((_, g), e)| g != e)
        .map(|((what, g), e)| format!("{what}: {g}, and the Python gave {e}"))
        .collect();
    std::fs::remove_dir_all(&dir).unwrap();
    assert!(wrong.is_empty(), "{name} ChipSet:\n{}", wrong.join("\n"));
}

#[test]
fn an_indexed_chipset_draws_what_the_python_drew() {
    check(
        "indexed",
        indexed_chipset,
        [
            "4f6980ceed100404702093d986adac9af3d22198ca931fb586bb7c25f235e231",
            "eb744f898cd301ebc2a76319d68ff9e083e14d44ca02d0611c875018b3c1e84f",
            "851b3815e6de7bfd267e10038da649fffb34b4ef5f46b0121592ffe6b667d123",
            "c72c5bf6ea1f7692b0bf665f124f87877ff581d47cacf176860414700a0cefd0",
            "d340c79b15776369c470d9f6a9f645bd6f81a47f51cbe0a8671de599b782dcac",
            "eeb6f95a11351d430b1bdb4b8ccf3f512a0c7f1fec680a5d5f7f0eb295f1282c",
            "30305d52d294e871a6bd1a78e589a527bcb7ed38cebfa6cd68c4757d0bdb1ee9",
            "1b0cea1518dc211d2866e533bb4f5d06eac7eab005118ab12a37397549502ee7",
        ],
    );
}

#[test]
fn a_half_transparent_chipset_rounds_like_the_python() {
    check(
        "rgba",
        rgba_chipset,
        [
            "dc28d0bfedce51d54396f05e7180cc39ad3f865d9808a90a1669292f86697caf",
            "09137428a585656b962505c71ba7eb1dcaf427b9401a441717435cec934c067d",
            "da8183e15908245440227d905ed24dd42e84c4ab25592b3fc4d5447030e8bfed",
            "5ca869111d084830bd8ddd0004e99f3948d3ec5a59cb34b9734c8b7dfa882e7f",
            "d15523a6af26ae8273540c0a3c0fc67fde01640a35ed583802fa1edba735ae49",
            "0adee812f4356f9cd0bcd49ce50494dec65c4446a989a304f125431e12095d58",
            "26cafd59d226a0814817eb900dbf32b5993b2ff65457259d16a3af7e14f8ed75",
            "fcdee33167eb32c62957d8ec561f78e8560303b4780b1967cb2e7678447f304b",
        ],
    );
}
