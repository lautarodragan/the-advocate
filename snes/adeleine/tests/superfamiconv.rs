//! SuperFamiconv as a referee for `try_pack`.
//!
//! Packing is the one question SuperFamiconv and Adeleine answer the same
//! way with no taste involved: without `-Q` SuperFamiconv keeps every
//! colour and only chooses how to group them, so whichever needs fewer
//! palettes is simply better. Each picture here is built from a seed,
//! written as a PNG and handed to both, and the test is red when
//! SuperFamiconv fits it in fewer palettes than `try_pack`, or fits it where
//! `try_pack` answers `None` —unless the seed is in `KNOWN`, with its
//! reason—.
//!
//! SuperFamiconv is <https://github.com/Optiroc/SuperFamiconv>, a separate
//! program and not a dependency: without `superfamiconv` on the PATH these
//! tests are skipped with a message. Its answer is checked before it is
//! believed: every palette has to start with colour zero and hold exactly
//! the picture's colours, so a referee that dropped or merged one would be
//! caught here and not counted as a win.

use adeleine::{try_pack, Color, Colors, COLORS_PER_PALETTE, USABLE_COLORS};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process::Command;

/// Background palettes of a four-bit picture: what both packers get unless
/// a case says otherwise.
const LIMIT: usize = 8;

/// How many seeds the test runs. `ADELEINE_ORACLE_SEEDS` runs more, to
/// measure.
const SEEDS: u64 = 120;

/// Seeds where SuperFamiconv packs tighter and that is a known limit of
/// `try_pack`, not a regression, grouped by their reason. A seed that stops
/// being a win is red too, so the list cannot go stale: whoever fixes a
/// reason takes its seeds out, and the ones still red say what is left.
///
/// The split between the two was measured on 2026-11-22 with a copy of
/// `try_pack` that picks the group that grows the least: in the first list
/// that copy fits in as few palettes as SuperFamiconv, in the second it
/// does not.
const KNOWN: &[(&str, &[u64])] = &[
    (
        "try_pack puts each tile in the group that ends smallest, not in the \
         one that grows the least as its comment says: \
         tasks/try-pack-picks-the-smallest-group.md in the-advocate-work",
        &[
            0, 2, 7, 9, 10, 11, 15, 18, 27, 28, 31, 38, 48, 49, 53, 55, 57, 59, 61, 63, 73, 79, 81,
            82, 91, 95, 97, 98, 102, 107, 114, 116,
        ],
    ),
    (
        "best fit never undoes a placement, and SuperFamiconv's \
         overload-and-remove does: tasks/overload-and-remove-for-try-pack.md \
         in the-advocate-work",
        &[1, 16, 29, 34, 35, 68, 76, 84, 96, 104],
    ),
];

/// splitmix64: small, and the same numbers on every machine.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }

    /// Uniform in `low..=high`.
    fn range(&mut self, low: usize, high: usize) -> usize {
        low + (self.next() % (high - low + 1) as u64) as usize
    }

    /// A colour at 15 bits, five per channel: the depth both packers see.
    fn color(&mut self) -> Color {
        let v = self.next();
        [
            (v & 31) as u8,
            ((v >> 5) & 31) as u8,
            ((v >> 10) & 31) as u8,
        ]
    }
}

/// A picture of 8x8 tiles: each pixel is a colour, or `None` for colour
/// zero, the one every palette reserves.
struct Picture {
    zero: Color,
    tiles: Vec<[Option<Color>; 64]>,
}

impl Picture {
    /// What `try_pack` gets: each tile's colours without colour zero, which
    /// is what SuperFamiconv takes out of each tile too.
    fn sets(&self) -> Vec<Colors> {
        self.tiles
            .iter()
            .map(|tile| tile.iter().flatten().copied().collect())
            .collect()
    }
}

/// Built like a drawing is: colours come in ramps —themes of six to
/// fourteen colours, each sharing a few with the one before, as shades
/// do—, and each tile draws with some of one theme, now and then borrowing
/// a colour from another. Random sets from one pool would rarely share
/// anything, which is not what packing is for; themes that overlap are
/// where grouping them well matters.
fn picture(seed: u64) -> Picture {
    let mut r = Rng(seed);
    let mut used: BTreeSet<Color> = BTreeSet::new();
    let zero = r.color();
    used.insert(zero);
    let mut fresh = |r: &mut Rng| loop {
        let c = r.color();
        if used.insert(c) {
            return c;
        }
    };
    let mut themes: Vec<Vec<Color>> = Vec::new();
    for _ in 0..r.range(6, 12) {
        let size = r.range(6, 14);
        let mut theme: Vec<Color> = Vec::new();
        if let Some(previous) = themes.last() {
            for _ in 0..r.range(0, 4) {
                let c = previous[r.range(0, previous.len() - 1)];
                if !theme.contains(&c) {
                    theme.push(c);
                }
            }
        }
        while theme.len() < size {
            theme.push(fresh(&mut r));
        }
        themes.push(theme);
    }
    let mut tiles = Vec::new();
    for _ in 0..r.range(48, 160) {
        let theme = &themes[r.range(0, themes.len() - 1)];
        let k = r.range(1, theme.len().min(USABLE_COLORS));
        let mut colors: Vec<Color> = Vec::new();
        while colors.len() < k {
            let c = theme[r.range(0, theme.len() - 1)];
            if !colors.contains(&c) {
                colors.push(c);
            }
        }
        if r.range(0, 5) == 0 && k < USABLE_COLORS {
            let other = &themes[r.range(0, themes.len() - 1)];
            let c = other[r.range(0, other.len() - 1)];
            if !colors.contains(&c) {
                colors.push(c);
            }
        }
        // Every colour drawn at least once, the rest of the pixels at
        // random among them and, in half the tiles, colour zero.
        let with_zero = r.range(0, 1) == 0;
        let mut pixels = [None; 64];
        for (i, pixel) in pixels.iter_mut().enumerate() {
            *pixel = if i < colors.len() {
                Some(colors[i])
            } else {
                let pick = r.range(0, colors.len() - usize::from(!with_zero));
                colors.get(pick).copied()
            };
        }
        tiles.push(pixels);
    }
    Picture { zero, tiles }
}

/// Eight bits from five, the way the console's colours are usually widened:
/// SuperFamiconv truncates back to the same five.
fn widen(c: u8) -> u8 {
    (c << 3) | (c >> 2)
}

/// The picture as an RGB PNG, sixteen tiles a row; the cells past the last
/// tile are colour zero.
fn write_png(path: &Path, picture: &Picture) {
    const ROW: usize = 16;
    let (width, height) = (ROW * 8, picture.tiles.len().div_ceil(ROW) * 8);
    let mut data = vec![0u8; width * height * 3];
    for y in 0..height {
        for x in 0..width {
            let tile = (y / 8) * ROW + x / 8;
            let pixel = picture
                .tiles
                .get(tile)
                .and_then(|t| t[(y % 8) * 8 + x % 8])
                .unwrap_or(picture.zero);
            let at = (y * width + x) * 3;
            for (byte, channel) in data[at..at + 3].iter_mut().zip(pixel) {
                *byte = widen(channel);
            }
        }
    }
    let file = std::fs::File::create(path).unwrap();
    let mut encoder = png::Encoder::new(std::io::BufWriter::new(file), width as u32, height as u32);
    encoder.set_color(png::ColorType::Rgb);
    encoder.set_depth(png::BitDepth::Eight);
    encoder
        .write_header()
        .unwrap()
        .write_image_data(&data)
        .unwrap();
}

fn hex(c: Color) -> String {
    format!("{:02x}{:02x}{:02x}", widen(c[0]), widen(c[1]), widen(c[2]))
}

fn on_path(name: &str) -> bool {
    Command::new(name)
        .arg("--version")
        .output()
        .is_ok_and(|o| o.status.success())
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "adeleine-superfamiconv-{}-{name}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// SuperFamiconv's palettes for the picture, lossless —no `-Q`—, in at most
/// `limit` palettes of sixteen with `zero` first; `None` when it says they
/// do not fit. Any other failure is the test's, not an answer.
fn superfamiconv(dir: &Path, picture: &Picture, limit: usize) -> Option<Vec<Vec<Color>>> {
    let png = dir.join("picture.png");
    let json = dir.join("palette.json");
    write_png(&png, picture);
    let _ = std::fs::remove_file(&json);
    let out = Command::new("superfamiconv")
        .arg("palette")
        .args(["-M", "snes", "-C", &COLORS_PER_PALETTE.to_string()])
        .args(["-N", &limit.to_string(), "-Z", &hex(picture.zero)])
        .arg("-i")
        .arg(&png)
        .arg("-j")
        .arg(&json)
        .output()
        .unwrap();
    if !out.status.success() {
        let message = String::from_utf8_lossy(&out.stderr);
        assert!(
            message.contains("do not fit"),
            "superfamiconv failed: {message}"
        );
        return None;
    }
    let text = std::fs::read_to_string(&json).unwrap();
    let value: serde_json::Value = serde_json::from_str(&text).unwrap();
    let palettes = value["palettes_native_rgb"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| {
            p.as_array()
                .unwrap()
                .iter()
                .map(|c| {
                    let c = c.as_array().unwrap();
                    [0, 1, 2].map(|i| c[i].as_u64().unwrap() as u8)
                })
                .collect()
        })
        .collect();
    Some(palettes)
}

/// What makes SuperFamiconv's answer a fair one to compare against: every
/// palette starts with colour zero and holds at most sixteen distinct
/// colours, together they hold exactly the picture's colours —none merged,
/// none invented, at 15 bits—, and every tile draws with one of them.
fn check_referee(picture: &Picture, palettes: &[Vec<Color>]) -> Result<(), String> {
    let sets = picture.sets();
    let picture_colors: Colors = sets.iter().flatten().copied().collect();
    let mut seen = Colors::new();
    for (i, palette) in palettes.iter().enumerate() {
        if palette.first() != Some(&picture.zero) {
            return Err(format!("palette {i} does not start with colour zero"));
        }
        let distinct: Colors = palette.iter().copied().collect();
        if distinct.len() != palette.len() || palette.len() > COLORS_PER_PALETTE {
            return Err(format!("palette {i} repeats colours or holds too many"));
        }
        seen.extend(palette[1..].iter().copied());
    }
    if seen != picture_colors {
        return Err(format!(
            "the palettes hold {} colours, the picture has {}",
            seen.len(),
            picture_colors.len()
        ));
    }
    for (t, set) in sets.iter().enumerate() {
        if !palettes.iter().any(|p| set.iter().all(|c| p.contains(c))) {
            return Err(format!("tile {t} draws with no single palette"));
        }
    }
    Ok(())
}

/// How many palettes each needs for one picture, with at most `limit`:
/// `None` when it does not fit.
struct Verdict {
    adeleine: Option<usize>,
    superfamiconv: Option<usize>,
}

impl Verdict {
    /// SuperFamiconv fits in fewer palettes, or fits where `try_pack` does
    /// not.
    fn referee_wins(&self) -> bool {
        match (self.adeleine, self.superfamiconv) {
            (_, None) => false,
            (None, Some(_)) => true,
            (Some(a), Some(s)) => s < a,
        }
    }
}

fn judge(dir: &Path, seed: u64, limit: usize) -> Verdict {
    let picture = picture(seed);
    let adeleine = try_pack(&picture.sets(), limit, USABLE_COLORS).map(|p| p.len());
    let palettes = superfamiconv(dir, &picture, limit);
    if let Some(palettes) = &palettes {
        if let Err(why) = check_referee(&picture, palettes) {
            panic!("seed {seed}: SuperFamiconv's answer is not lossless: {why}");
        }
    }
    Verdict {
        adeleine,
        superfamiconv: palettes.map(|p| p.len()),
    }
}

fn seeds() -> u64 {
    std::env::var("ADELEINE_ORACLE_SEEDS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(SEEDS)
}

#[test]
fn superfamiconv_never_packs_tighter_than_try_pack() {
    if !on_path("superfamiconv") {
        eprintln!("skipped: superfamiconv is not on the PATH");
        return;
    }
    let dir = scratch("tighter");
    let known: BTreeMap<u64, &str> = KNOWN
        .iter()
        .flat_map(|&(why, seeds)| seeds.iter().map(move |&seed| (seed, why)))
        .collect();
    let mut wins = Vec::new();
    let mut stale = Vec::new();
    for seed in 0..seeds() {
        let verdict = judge(&dir, seed, LIMIT);
        let line = format!(
            "seed {seed}: try_pack {:?}, superfamiconv {:?}",
            verdict.adeleine, verdict.superfamiconv
        );
        match (verdict.referee_wins(), known.contains_key(&seed)) {
            (true, false) => wins.push(line),
            (false, true) => stale.push(line),
            _ => {}
        }
    }
    let _ = std::fs::remove_dir_all(&dir);
    assert!(
        wins.is_empty() && stale.is_empty(),
        "SuperFamiconv packs tighter than try_pack:\n{}\n\
         in KNOWN but no longer a win:\n{}",
        wins.join("\n"),
        stale.join("\n")
    );
}

/// The colours of `picture` reach SuperFamiconv as they are: a picture with
/// one colour per channel value, widened and truncated back, comes out with
/// the same thirty-one colours and colour zero. Without this a mismatch in
/// depth would show up as a packing difference.
#[test]
fn superfamiconv_sees_the_same_fifteen_bit_colours() {
    if !on_path("superfamiconv") {
        eprintln!("skipped: superfamiconv is not on the PATH");
        return;
    }
    let dir = scratch("depth");
    let zero = [0, 0, 0];
    let tiles = (1..32u8)
        .map(|v| {
            let mut pixels = [None; 64];
            pixels[0] = Some([v, 31 - v, v / 2]);
            pixels
        })
        .collect();
    let picture = Picture { zero, tiles };
    let palettes = superfamiconv(&dir, &picture, LIMIT).expect("31 colours fit in 8 palettes");
    let _ = std::fs::remove_dir_all(&dir);
    check_referee(&picture, &palettes).unwrap();
}

/// Not a test: the distribution over `ADELEINE_ORACLE_SEEDS` seeds (by
/// default `SEEDS`), with no limit that matters, so both packers say how
/// many palettes they need. `cargo test --test superfamiconv -- --ignored
/// --nocapture`.
#[test]
#[ignore]
fn distribution() {
    if !on_path("superfamiconv") {
        eprintln!("skipped: superfamiconv is not on the PATH");
        return;
    }
    let dir = scratch("distribution");
    let mut table: BTreeMap<(usize, usize), u64> = BTreeMap::new();
    let (mut ties, mut adeleine_wins, mut referee_wins) = (0, 0, 0);
    for seed in 0..seeds() {
        let v = judge(&dir, seed, 64);
        let (a, s) = (v.adeleine.unwrap(), v.superfamiconv.unwrap());
        *table.entry((a, s)).or_default() += 1;
        match a.cmp(&s) {
            std::cmp::Ordering::Equal => ties += 1,
            std::cmp::Ordering::Less => adeleine_wins += 1,
            std::cmp::Ordering::Greater => {
                referee_wins += 1;
                println!("seed {seed}: try_pack {a}, superfamiconv {s}");
            }
        }
    }
    let _ = std::fs::remove_dir_all(&dir);
    println!("ties {ties}, try_pack fewer {adeleine_wins}, superfamiconv fewer {referee_wins}");
    for ((a, s), n) in table {
        println!("try_pack {a:2}  superfamiconv {s:2}  {n}");
    }
}
