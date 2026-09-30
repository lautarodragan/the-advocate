//! The layers against the Python they replaced.
//!
//! Until 2026-09-30 a map's layers were converted by the converter in
//! Python (`map_layers.py`, with Adeleine and Voodoo as binaries). What is
//! left of it is here: the SHA-256 of what it made of a few layers built
//! inside this file, which needs no real game.
//!
//! The layers are made to touch every path: a background that fits and one
//! that has to merge; a layer above that is empty, one that fits in one
//! palette, one that takes three and so leaves the background less, and
//! two whose tiles bring more colours than fit and have to merge; and a
//! background with both families of the ChipSet's animation, each moving
//! its own cells. Colours go in at 24 bits, so the 15-bit cut is in it too.
//!
//! The blocks are made of those layers' tilemaps, over made-up tile ids of
//! every family, passability and terrain: the terrain from a ChipSet whose
//! table is not all 1, through `rm2k-rules`.
//!
//! **If one of these changes, a byte of the cartridge changed.** The
//! hashes are not to be regenerated to make a test pass: the Python that
//! produced them is gone, and with it the only independent answer.

use ditto::schema::Chipset;
use rm2k_render::{Family, Layers, Picture};
use rm2k_rules::chipset::terrain_of;
use rm2k_snes_map_background::blocks::{blocks, Map};
use rm2k_snes_map_background::{convert, Merge};
use sha2::{Digest, Sha256};

fn h(n: u64) -> u64 {
    let mut n = (n * 2654435761) & 0xFFFF_FFFF;
    n ^= n >> 13;
    n = (n * 1274126177) & 0xFFFF_FFFF;
    n ^ (n >> 16)
}

/// What a drawing looks like, in the same terms the Python that made the
/// hashes used: `kinds` distinct cells of `colors` colours —times `groups`,
/// each kind drawing from one group—, `holes` in 256 of them transparent in
/// part or whole, and `change` = (d, every, rem) redraws the cells whose
/// kind is `rem` modulo `every`, for drawing `d` of an animation.
struct Drawing {
    width: u64,
    height: u64,
    seed: u64,
    colors: u64,
    kinds: u64,
    holes: u64,
    change: Option<(u64, u64, u64)>,
    groups: u64,
}

fn drawing(width: u64, height: u64, seed: u64, colors: u64, kinds: u64) -> Drawing {
    Drawing {
        width,
        height,
        seed,
        colors,
        kinds,
        holes: 0,
        change: None,
        groups: 1,
    }
}

impl Drawing {
    fn holes(mut self, holes: u64) -> Self {
        self.holes = holes;
        self
    }

    fn change(mut self, d: u64, every: u64, rem: u64) -> Self {
        self.change = Some((d, every, rem));
        self
    }

    fn groups(mut self, groups: u64) -> Self {
        self.groups = groups;
        self
    }

    fn picture(&self) -> Picture {
        let mut rgba = Vec::new();
        for y in 0..self.height {
            for x in 0..self.width {
                let mut kind = h(self.seed * 7919 + x / 8 + 1000 * (y / 8)) % self.kinds;
                if let Some((d, every, rem)) = self.change {
                    if kind % every == rem {
                        kind += d * 101;
                    }
                }
                let k = h(kind * 64 + x % 8 + 8 * (y % 8) + self.seed) % self.colors
                    + (kind % self.groups) * self.colors;
                let channel = |i: u64| (h(k * 3 + i + self.seed) & 255) as u8;
                let mut a = 255;
                if self.holes > 0 && h(kind + 77) % 256 < self.holes && !h(kind * 5 + (x % 8) * 3 + y % 8).is_multiple_of(3) {
                    a = 0;
                }
                if self.holes > 0 && h(kind + 91) % 256 < self.holes / 2 {
                    a = 0;
                }
                rgba.extend_from_slice(&[channel(0), channel(1), channel(2), a]);
            }
        }
        Picture {
            width: self.width as usize,
            height: self.height as usize,
            rgba,
        }
    }
}

fn case(name: &str) -> Layers {
    let (lower, upper, variants) = match name {
        "plain" => (drawing(64, 48, 1, 40, 12), drawing(64, 48, 2, 1, 1).holes(256), vec![]),
        "crowded" => (
            drawing(96, 64, 3, 200, 60),
            drawing(96, 64, 4, 90, 40).holes(120),
            vec![],
        ),
        "animated" => {
            let water = |d| drawing(80, 64, 5, 60, 20).change(d, 4, 1).picture();
            let animated = |d: u64| drawing(80, 64, 5, 60, 20).change(d + 5, 4, 2).picture();
            (
                drawing(80, 64, 5, 60, 20).change(0, 4, 1),
                drawing(80, 64, 6, 20, 10).holes(200),
                vec![
                    (Family::Water, vec![water(1), water(2)]),
                    (Family::Animated, vec![animated(1), animated(2), animated(3)]),
                ],
            )
        }
        "split" => (
            drawing(64, 64, 9, 60, 16),
            drawing(64, 64, 10, 12, 24).holes(90).groups(3),
            vec![],
        ),
        "above" => (
            drawing(64, 64, 7, 30, 10),
            drawing(64, 64, 8, 120, 30).holes(60),
            vec![],
        ),
        _ => unreachable!(),
    };
    Layers {
        lower: lower.picture(),
        upper: upper.picture(),
        variants,
    }
}

struct Expected {
    tiles: &'static str,
    cgram: &'static str,
    tilemap: &'static str,
    above_tiles: &'static str,
    above_cgram: &'static str,
    above_tilemap: &'static str,
    above_first: usize,
    above_merged: usize,
    colors: usize,
    used: usize,
    budget: usize,
    merged: usize,
    runs: &'static [(&'static str, usize, usize, &'static str)],
    merges: &'static str,
    above_merges: &'static str,
}

fn sha(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn words(words: impl IntoIterator<Item = u16>) -> Vec<u8> {
    words.into_iter().flat_map(u16::to_le_bytes).collect()
}

fn tilemap(rows: &[Vec<u16>]) -> Vec<u8> {
    words(rows.iter().flatten().copied())
}

/// The merges as the Python wrote them for its hash: `json.dumps` of
/// `[[victim, target, pixels], ...]`.
fn merges(merges: &[Merge]) -> String {
    let color = |c: [u8; 3]| format!("[{}, {}, {}]", c[0], c[1], c[2]);
    let each: Vec<String> = merges
        .iter()
        .map(|m| format!("[{}, {}, {}]", color(m.victim), color(m.target), m.pixels))
        .collect();
    format!("[{}]", each.join(", "))
}

const EXPECTED: [(&str, Expected); 5] = [
    ("plain", Expected {
        tiles: "3db3ce3f6114e40adc6fd3f909e1c2bd3ad18206d2014c2d8e74dd15a83d4536",
        cgram: "e75a120deb16d988eaa9d6bf0e0bc544d3d0494ba11683cb2f72d914b52aeafc",
        tilemap: "ba0098a65ed25ff0ad3661763c342f817e40b6d93960c454e6f28259aa71f6ee",
        above_tiles: "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925",
        above_cgram: "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925",
        above_tilemap: "2ea9ab9198d1638007400cd2c3bef1cc745b864b76011a0e1bc52180ac6452d4",
        above_first: 7,
        above_merged: 0,
        colors: 40,
        used: 40,
        budget: 103,
        merged: 0,
        runs: &[],
        merges: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        above_merges: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    }),
    ("crowded", Expected {
        tiles: "cd75e5ee4fe16f60915ea566edd29749d60ad7974b5fe635d4eeb64c9f7b2cc1",
        cgram: "474cea8ae7718655dd93cd155ca3d62cb5adf2c31ca43ce7e4d82d267fa7488b",
        tilemap: "3ad6419cf3051401633184e3b71c7b3a3e59ebf77b04d03367dcea762138457a",
        above_tiles: "99fb45870e36d95add8345e617dac14b2f2b4d09da83f4fdc21315b256d8b59b",
        above_cgram: "700c696f756005781eb30cc47d440de1f61b521418c9595e3ebf342e507b8093",
        above_tilemap: "841cbdb79f817489aa031690cd301e09cd00321dc769e664bbfe30a55524c707",
        above_first: 7,
        above_merged: 75,
        colors: 199,
        used: 103,
        budget: 103,
        merged: 96,
        runs: &[],
        merges: "c92c674606510ad0dbdbd790a48381e31cb07911482f8915c1aa9067c23d2067",
        above_merges: "6054a69f452f6f392cc2ccf151d768afaff3e46204e8aa5b52fdd3888fac36da",
    }),
    ("animated", Expected {
        tiles: "ffe0b04d5ed5bf05bfc9118763c3a2f1174605a1a2517869c1dc9f6f81ef4aef",
        cgram: "198992644ffb83775eebf0cb09f1ea09b805d9fdd02b66e2d71bd80afcd5ab49",
        tilemap: "b70b9a807ac1e6c70bac88fc7ac6786719f2709791bcc2da5dee6dd4289bdd78",
        above_tiles: "72280aaed0b16b3cc0dec9f3e14b639b134e237d3103b8e49f962bb1f9553607",
        above_cgram: "446c5d0d70562691908ec06c2fd5fd2a59096e5dcc7381652fdddc76590e1d64",
        above_tilemap: "8d4b8dbcb8064905fafbb953d381b5a2b9dc3d3051b87e76c3b3a52bbd82c43c",
        above_first: 7,
        above_merged: 5,
        colors: 60,
        used: 60,
        budget: 103,
        merged: 0,
        runs: &[("water", 11, 5, "04ef08ed6984f56ff596c7145c2919d57b15b53335e0d406c276af463363427a"), ("animated", 16, 5, "4e6a35aee83cb10e2c964c15cb6e2343d40900d55145116b81b9ec55496d44b2")],
        merges: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        above_merges: "acb38a875c38d8a77f9543fee16c7235d960cfb2693bc1b92b43d3c629ad538d",
    }),
    ("split", Expected {
        tiles: "7c38c702ca45b24665f3edba27a391e5865775c3bb2b3409c65399043b0a2b0e",
        cgram: "32b95a9855e57965a7c51fd389412cd39c54d3b73ac3c501e42b74671db526b4",
        tilemap: "f129e611d4028da573c5da491d521590a0a1abd9ac22ce1d9ad0b541bb4d5990",
        above_tiles: "6c8af782e0072f786a7aa4f97357a6ebf0b563729c6907e8eb89ab08c35506a7",
        above_cgram: "1f910f2ff017ba51652be668e65e879a958b68c9178cb7c2a451b823cf268405",
        above_tilemap: "250658ee67052bf3d78d7858dcff097c14f11e88e016a1ab3872a309c8de0876",
        above_first: 5,
        above_merged: 0,
        colors: 60,
        used: 60,
        budget: 71,
        merged: 0,
        runs: &[],
        merges: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        above_merges: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    }),
    ("above", Expected {
        tiles: "ed01e273dd25eef30e976a1c2fe93187ca985bffce863e8e82b257b985728350",
        cgram: "4c47b41f9d4fce87d4ef984b9327a839cfce6500797a4a62f9d317ca10aeaef0",
        tilemap: "ebab16a80c31d5446c615983b8e392883b0725de500c9c6c628a87fe0411fabc",
        above_tiles: "1ef1b3621e83db942785d5e599ef4070b4a17541ee2cc3ac8b8161199c140e1b",
        above_cgram: "43e167b12b4f735d7f7985d069bb4baa8f9330ae0e1aa69b426a4922815942d5",
        above_tilemap: "b116e616a5270cba32df8507ae5127362a93de5886c29734e0187491e1f0cb4a",
        above_first: 7,
        above_merged: 105,
        colors: 30,
        used: 30,
        budget: 103,
        merged: 0,
        runs: &[],
        merges: "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        above_merges: "2260679b11e8152e42694b1c43834829634242a0ecd49a10b969dc7b89f940dc",
    }),
];

#[test]
fn the_layers_are_the_ones_the_python_made() {
    for (name, want) in &EXPECTED {
        let done = convert(&case(name)).unwrap();
        let (bg, above) = (&done.background, &done.above);
        assert_eq!(sha(&bg.tiles), want.tiles, "{name}: the tiles");
        assert_eq!(sha(&words(bg.cgram.iter().copied())), want.cgram, "{name}: the colours");
        assert_eq!(sha(&tilemap(&bg.tilemap)), want.tilemap, "{name}: the tilemap");
        assert_eq!(sha(&above.tiles), want.above_tiles, "{name}: the tiles above");
        assert_eq!(sha(&above.cgram), want.above_cgram, "{name}: the colours above");
        assert_eq!(sha(&tilemap(&above.tilemap)), want.above_tilemap, "{name}: the tilemap above");
        assert_eq!(above.first, want.above_first, "{name}: where the layer above starts");
        assert_eq!(above.merges.len(), want.above_merged, "{name}: merged above");
        assert_eq!(bg.colors, want.colors, "{name}: the colours drawn");
        assert_eq!(bg.used, want.used, "{name}: the colours kept");
        assert_eq!(bg.budget, want.budget, "{name}: the budget");
        assert_eq!(bg.merges.len(), want.merged, "{name}: merged");
        assert_eq!(sha(merges(&bg.merges).as_bytes()), want.merges, "{name}: the merges");
        assert_eq!(
            sha(merges(&above.merges).as_bytes()),
            want.above_merges,
            "{name}: the merges above"
        );
        let runs: Vec<(&str, usize, usize, String)> = bg
            .runs
            .iter()
            .map(|r| (r.family.name(), r.base, r.tiles, sha(&r.drawings.concat())))
            .collect();
        let expected: Vec<(&str, usize, usize, String)> = want
            .runs
            .iter()
            .map(|&(f, b, t, s)| (f, b, t, s.to_string()))
            .collect();
        assert_eq!(runs, expected, "{name}: the runs of the animation");
    }
}

#[test]
fn the_pictures_are_what_was_decided() {
    let done = convert(&case("animated")).unwrap();
    let names: Vec<&str> = done.pictures.iter().map(|p| p.name.as_str()).collect();
    assert_eq!(
        names,
        ["background", "water-1", "water-2", "animated-1", "animated-2", "animated-3", "above"]
    );
    // The background's indices are its colours from the first entry past
    // the window's, and the layer above's are inside its palettes.
    let background = &done.pictures[0].picture;
    assert!(background.pixels.iter().all(|&i| i >= 9));
    let above = &done.pictures[6].picture;
    let first = done.above.first * 16;
    assert!(above.pixels.iter().all(|&i| i == 0 || i as usize > first));
}

struct ExpectedBlocks {
    cells: &'static str,
    table: &'static str,
    passability: &'static str,
    terrain: &'static str,
    combos: &'static str,
    blocks: usize,
}

const BLOCKS: [(&str, ExpectedBlocks); 5] = [
    ("plain", ExpectedBlocks {
        cells: "a46b67c8fb1c4c35fdfc8387c647f8c442a84e1520334a92a127f740b4c1dd5c",
        table: "696185753d9192ea3dd865b327d72b09307ccd80c6e1aea6652c544a0629b015",
        passability: "284359ab75a4a675946435affff13377bda58ecb26dbd58197156fd422e96fbb",
        terrain: "93b6673a6e95d9375e47cb83e7c1775af73446f74bc9f18811a9ae37f7d48869",
        combos: "e07d93c5fd046f6bce3a37b978d5bcfaa677a05e4154ba53b2c404b11774c584",
        blocks: 12,
    }),
    ("crowded", ExpectedBlocks {
        cells: "e88624bf274aff4f35798f4bc27027683e9c1d78f132211a3cc4ae5b3decd4e3",
        table: "f06d3e029489100b2b4571155d3b52366b8b2675d738f85abd2dfaf28c9460b0",
        passability: "4abdce997ed94d2d3f7353f3707701ebf205e7642c357d4a1d21e8ae1304848c",
        terrain: "4d0fe0acaf91c4ffbe8f9316fde2ee6b7ecb5b82b6c41cb8cd1b2c889133676e",
        combos: "c5189adc8a8b6c4d49ec1a22b6e07cd0950a36402cc7aaba6777df6774498894",
        blocks: 24,
    }),
    ("animated", ExpectedBlocks {
        cells: "cf6cf8ff894814c395340e3b27ff21b83897b43f30ccad058d8340de5dd46ed8",
        table: "c39c7d9e6240b2ce8edc31c80ad7f337676fd9fa1d141ad70a0013d5d8754f31",
        passability: "ccb9d89a0f646e1157f45fb6cab35a984ae2af6c4912046ab4289a159e05bea4",
        terrain: "65c7dccad540e49232e4cc6f4797b7c3031a8b87fc11927adf7ec36f01ff68cb",
        combos: "76a222edc33d23aca20e582091aca43cede959a5095b782f0206723df6bb0365",
        blocks: 20,
    }),
    ("split", ExpectedBlocks {
        cells: "64a240d34d0c29ec867f653721a1532de6e665e602e7c03e0b853c9ef3094126",
        table: "574bbdf71866c22bd2172a3ea8eeec299bda3e588dbef1fbb396f2bb87fb6169",
        passability: "0d1339c5569dfa55c85cd91580f301ecf44f51759cfbc61f6a98815c97b12da2",
        terrain: "d4368535d31cd5698b1766f38381b24b33c2611f57c7fcdb50f01affba6f8b97",
        combos: "64fd309ebf75eb8984569262e42839e9d2ed452614583982c169a5835492d664",
        blocks: 16,
    }),
    ("above", ExpectedBlocks {
        cells: "64a240d34d0c29ec867f653721a1532de6e665e602e7c03e0b853c9ef3094126",
        table: "66d4ecc11d1169dfd48b38f2e07beb634f8f42b7ac1dc23fb4103fae75626f42",
        passability: "0d1339c5569dfa55c85cd91580f301ecf44f51759cfbc61f6a98815c97b12da2",
        terrain: "d4368535d31cd5698b1766f38381b24b33c2611f57c7fcdb50f01affba6f8b97",
        combos: "64fd309ebf75eb8984569262e42839e9d2ed452614583982c169a5835492d664",
        blocks: 16,
    }),
];

/// Tile ids for `n` cells, as the Python's test made them: water, animated,
/// terrain and plain ones below, a few plain ones above.
fn tile_ids(n: usize, seed: u64) -> (Vec<i32>, Vec<i32>) {
    (0..n as u64)
        .map(|i| {
            let r = h(i * 13 + seed);
            let lower = [r % 3000, 3000 + r % 150, 4000 + r % 600, 5000 + r % 144, 5000 + r % 3]
                [(r % 5) as usize];
            (lower as i32, (10000 + h(i * 17 + seed) % 4) as i32)
        })
        .unzip()
}

#[test]
fn the_blocks_are_the_ones_the_python_made() {
    let chipset = Chipset {
        terrain_data: (0..162).map(|k| (1 + h(k * 11) % 3) as i16).collect(),
        ..Chipset::default()
    };
    for (name, want) in &BLOCKS {
        let done = convert(&case(name)).unwrap();
        let tilemap = &done.background.tilemap;
        let (width, height) = (tilemap[0].len() / 2, tilemap.len() / 2);
        let seed = name.len() as u64;
        let (lower, upper) = tile_ids(width * height, seed);
        let passability: Vec<u8> = (0..(width * height) as u64)
            .map(|i| (h(i * 7 + seed) % 4) as u8)
            .collect();
        let terrain: Vec<i32> = lower.iter().map(|&id| terrain_of(&chipset, id)).collect();
        let made = blocks(
            &Map {
                width,
                height,
                lower: &lower,
                upper: &upper,
                passability: &passability,
                terrain: &terrain,
            },
            tilemap,
            &done.above.tilemap,
        )
        .unwrap();
        let combos: Vec<String> = made
            .combos
            .iter()
            .map(|((l, u), b)| format!("[{l}, {u}, {b}]"))
            .collect();
        assert_eq!(sha(&words(made.cells.iter().copied())), want.cells, "{name}: the cells");
        assert_eq!(sha(&made.table), want.table, "{name}: the table");
        assert_eq!(sha(&made.passability), want.passability, "{name}: the passability");
        assert_eq!(sha(&made.terrain), want.terrain, "{name}: the terrain");
        assert_eq!(
            sha(format!("[{}]", combos.join(", ")).as_bytes()),
            want.combos,
            "{name}: the combinations"
        );
        assert_eq!(made.passability.len(), want.blocks, "{name}: how many blocks");
    }
}
