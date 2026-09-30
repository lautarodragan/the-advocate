//! The reflow and a line of text against what the Python that did them
//! until 2026-09-30 answered for the same input: the sha256 of each answer,
//! taken from it before it was deleted.
//!
//! The input is made here: three hundred boxes of words a linear
//! congruence picks —with speakers, quotes, numbers after a name, a word
//! wider than the window, escape tails—, and a System made by formula.

use rm2k_render::Picture;
use rm2k_snes_text::{font, line, refit};
use sha2::{Digest, Sha256};

fn sha(data: &[u8]) -> String {
    Sha256::digest(data).iter().map(|b| format!("{b:02x}")).collect()
}

const WORDS: [&str; 24] = [
    "the", "Link", "Colony", "is", "connected", "to", "Block.", "Sector", "33.", "Well,",
    "maybe...", "\"Kersh.\"", "surprise!", "why?", "(really)", "no-one", "a", "an",
    "electromagnetic", "supercalifragilisticexpialidocious", "Remember,", "it's", "I", "go",
];

fn made_up_boxes() -> Vec<Vec<String>> {
    let mut seed: u64 = 12345;
    let mut out = Vec::new();
    for n in 0..300usize {
        let mut lines = Vec::new();
        if n % 3 == 0 {
            lines.push(["KERSH", "?????", "TRAM OFFICER", "WHAT?"][n % 4].to_string());
        }
        for _ in 0..1 + n % 5 {
            let mut words = Vec::new();
            for _ in 0..2 + n % 9 {
                seed = (seed * 1_103_515_245 + 12345) % 2_147_483_648;
                words.push(WORDS[(seed >> 16) as usize % WORDS.len()]);
            }
            lines.push(words.join(" "));
        }
        if n % 7 == 0 {
            let last = lines.last_mut().unwrap();
            last.push_str(if n % 2 == 1 { "\\|\\^" } else { " \\|" });
        }
        out.push(lines);
    }
    out
}

#[test]
fn the_reflow_of_three_hundred_boxes() {
    let boxes = made_up_boxes();
    assert_eq!(
        sha(serde_json::to_string(&boxes).unwrap().as_bytes()),
        "01abd81789299bc66c90f8d04e31f4872d04f4ccfe371f30b1b3b0233cb5b17b",
        "the boxes are not the ones the Python was given"
    );
    let reflowed: Vec<Vec<Vec<String>>> = boxes.iter().map(|b| refit::refit(b, 39, 4)).collect();
    assert_eq!(
        sha(serde_json::to_string(&reflowed).unwrap().as_bytes()),
        "8d5380590f859ae299bf508f08800f2ee01cedba2f819b7cd36682f9ee2c47c9"
    );
}

/// A System: a background of two colours, a frame, the cursors, the shadow,
/// the timer, and twenty text colours with a gradient of four rows each.
pub fn system() -> Picture {
    let pixel = |x: usize, y: usize| -> [u8; 4] {
        if y < 32 && x < 32 {
            let k = ((x / 11 + y / 11) % 2) as u8;
            return [40 + 20 * k, 40 + 20 * k, 120 + 30 * k, 255];
        }
        if y < 32 && (32..64).contains(&x) {
            let (fx, fy) = (x - 32, y);
            return if !(8..24).contains(&fx) || !(8..24).contains(&fy) {
                [200, 200, 220, 255]
            } else {
                [0; 4]
            };
        }
        if y < 32 && (64..128).contains(&x) {
            return [220, 60, 60, 255];
        }
        if (32..48).contains(&y) && (16..32).contains(&x) {
            return [10, 10, 10, 255];
        }
        if (32..48).contains(&y) && (32..120).contains(&x) {
            return if (x + y) % 3 != 0 { [255, 255, 0, 255] } else { [0; 4] };
        }
        if y >= 48 {
            let n = x / 16 + 10 * ((y - 48) / 16);
            let shade = ((y - 48) % 16) / 4 * 8;
            return [
                (n * 37 % 160 + 40 + shade) as u8,
                (n * 91 % 160 + 40 + shade) as u8,
                (n * 53 % 160 + 40 + shade) as u8,
                255,
            ];
        }
        [0; 4]
    };
    let mut rgba = Vec::with_capacity(160 * 80 * 4);
    for y in 0..80 {
        for x in 0..160 {
            rgba.extend_from_slice(&pixel(x, y));
        }
    }
    Picture {
        width: 160,
        height: 80,
        rgba,
    }
}

#[test]
fn a_line_in_each_font_and_four_colours() {
    let system = system();
    let expected = [
        (font::GOTHIC, 0, "5ae6a73541aec4a6020e326554b45f9c3ddcf7ff02a5df1f79f737a9e937df78"),
        (font::GOTHIC, 1, "2c62aa85b796a7b69cd50e66fe27cb2186bef4ef30ba7ad770f7115b6c6b7269"),
        (font::GOTHIC, 3, "94929c4a5ba24f75eaeb19501d0e4c5a0dfd26a93896834a3eeca89ac9bb1aaa"),
        (font::GOTHIC, 19, "f417650c08ecd8c3511a4c13919bcb7871b7ab6848af1befbab32cfe12fc90bf"),
        (font::MINCHO, 0, "f0758889403a98193db17d3bae15a99e5f369725b1ada233abed5e74a37024e7"),
        (font::MINCHO, 1, "ae3fab21ad7ecdda5eba217dc271f2ba261d959366140cc0c62e804d66fd6e88"),
        (font::MINCHO, 3, "ffc9a68ae375ebeaba40599126124b36306ddc1cf0a40862058ef2cfdd14e853"),
        (font::MINCHO, 19, "44e55170763c611b826ee5a9919cd603811bff87d4061caff692c6e8e79c62e8"),
    ];
    for (font_id, color, hash) in expected {
        let mut dest = Picture::transparent(64, 24);
        // Past the left edge and the right one: the line is cut.
        let end = line::draw_line(&mut dest, &system, -2, 3, "Hi, g{}~|!", color, font_id);
        assert_eq!(end, 58);
        assert_eq!(sha(&dest.rgba), hash, "font {font_id}, colour {color}");
    }
}
