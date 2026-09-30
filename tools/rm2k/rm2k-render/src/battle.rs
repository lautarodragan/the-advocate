//! What a battle is drawn on and with: its backdrop, and its enemies'
//! pictures, the battlers.
//!
//! * **A backdrop** is drawn opaque: RM2k gives it no colour key, so index
//!   0 is a colour like any other —easyrpg's `Cache`, whose `Backdrop` is
//!   not `transparent`—. Any transparency the file declares is dropped too.
//! * **A battler** is a picture of `Monster/` with its colour key, turned
//!   by the enemy's `battler_hue`: that is what makes one picture two
//!   different enemies.
//!
//! Where a battler stands, and which covers which, is the caller's: nothing
//! here puts a troop together.

use crate::fail::{Bad, Result};
use crate::picture::{self, Picture};
use std::path::{Path, PathBuf};

/// A backdrop's picture, opaque.
pub fn backdrop(path: &Path) -> Result<Picture> {
    let mut picture = picture::read_rm2k(path)?;
    for px in picture.rgba.chunks_exact_mut(4) {
        px[3] = 255;
    }
    Ok(picture)
}

/// A battler's picture, with its colour key and turned by `hue` degrees.
pub fn battler(path: &Path, hue: i32) -> Result<Picture> {
    let mut picture = picture::read_rm2k(path)?;
    if hue != 0 {
        rotate_hue(&mut picture, hue);
    }
    Ok(picture)
}

/// easyrpg's `RGB_to_HSL` (`bitmap_hslrgb.h`), with its integers: hue in
/// 0..0x600, saturation and lightness in 0..0xFF.
///
/// Every division truncates toward zero, as C's and Rust's do: the hue of
/// a colour whose green is below its blue has a negative numerator, and
/// flooring it would be one off.
fn to_hsl(r: i32, g: i32, b: i32) -> (i32, i32, i32) {
    // The spread between the largest channel and the smallest, the
    // numerator of the hue inside its sector, where the sector starts, and
    // largest plus smallest. Which channel counts as which, ties included,
    // is the way easyrpg's comparisons send them.
    let (c, num, sector, l2) = if r > g {
        if r > b {
            if g < b {
                (r - g, g - b, 0x600, r + g)
            } else {
                (r - b, g - b, 0, r + b)
            }
        } else {
            (b - g, r - g, 0x400, b + g)
        }
    } else if r < b {
        if g > b {
            (g - r, b - r, 0x200, g + r)
        } else {
            (b - r, r - g, 0x400, b + r)
        }
    } else {
        (g - b, b - r, 0x200, g + b)
    };
    let h = if c == 0 { 0 } else { 0x100 * num / c + sector };
    if l2 == 0 {
        return (h, 0, 0);
    }
    let s = 0x100 * c / spread(l2);
    (h, s, l2 / 2)
}

/// How far a lightness, doubled, is from the nearer of black and white.
fn spread(l2: i32) -> i32 {
    if l2 > 0xFF {
        0x1FF - l2
    } else {
        l2
    }
}

/// easyrpg's `HSL_to_RGB`.
fn from_hsl(h: i32, s: i32, l: i32) -> (i32, i32, i32) {
    let l2 = 2 * l;
    let c = s * spread(l2) / 0x100;
    let m = (l2 - c) / 2;
    let h0 = h & 0xFF;
    let h1 = 0xFF - h0;
    match h >> 8 {
        0 => (m + c, m + h0 * c / 0x100, m),
        1 => (m + h1 * c / 0x100, m + c, m),
        2 => (m, m + c, m + h0 * c / 0x100),
        3 => (m, m + h1 * c / 0x100, m + c),
        4 => (m + h0 * c / 0x100, m, m + c),
        _ => (m + c, m, m + h1 * c / 0x100),
    }
}

/// easyrpg's `Bitmap::HueChangeBlit`: every pixel that is not fully
/// transparent turned `degrees` around the colour wheel, in its integer
/// HSL. A transparent pixel keeps whatever colour it had.
pub fn rotate_hue(picture: &mut Picture, degrees: i32) {
    let mut hue = (degrees as f64 / 60.0 * 256.0) as i32;
    if hue < 0 {
        hue += ((-hue + 0x5FF) / 0x600) * 0x600;
    } else if hue > 0x600 {
        hue -= (hue / 0x600) * 0x600;
    }
    for px in picture.rgba.chunks_exact_mut(4) {
        if px[3] == 0 {
            continue;
        }
        let (mut h, s, l) = to_hsl(px[0] as i32, px[1] as i32, px[2] as i32);
        h += hue;
        if h >= 0x600 {
            h -= 0x600;
        }
        let (r, g, b) = from_hsl(h, s.min(0xFF), l.clamp(0, 0xFF));
        px[0] = r.clamp(0, 255) as u8;
        px[1] = g.clamp(0, 255) as u8;
        px[2] = b.clamp(0, 255) as u8;
    }
}

/// One picture a request asks for.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Wanted {
    Backdrop(PathBuf),
    Battler { picture: PathBuf, hue: i32 },
}

/// A request: a JSON list, one entry per picture, and picture `i` is
/// written as `<i>.png`. An entry is `{"backdrop_file": path}` or
/// `{"monster_file": path, "hue": degrees}`, the hue 0 if left out. A
/// relative path is relative to the request's directory.
pub fn request(path: &Path) -> Result<Vec<Wanted>> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let whose = path.display().to_string();
    let bad = |what: String| Bad::answer(format!("{whose}: {what}"));
    let data: serde_json::Value = serde_json::from_str(&text).map_err(|e| bad(e.to_string()))?;
    let base = path.parent().unwrap_or(Path::new(""));
    let entries = data
        .as_array()
        .ok_or_else(|| bad("not a list".to_string()))?;
    let mut wanted = Vec::with_capacity(entries.len());
    for (i, entry) in entries.iter().enumerate() {
        let file = |key: &str| {
            entry.get(key).map(|v| {
                v.as_str()
                    .map(|s| base.join(s))
                    .ok_or_else(|| bad(format!("entry {i}: `{key}` is not a path")))
            })
        };
        wanted.push(match (file("backdrop_file"), file("monster_file")) {
            (Some(backdrop), None) => Wanted::Backdrop(backdrop?),
            (None, Some(monster)) => {
                let hue = match entry.get("hue") {
                    None => 0,
                    Some(v) => v
                        .as_i64()
                        .and_then(|h| i32::try_from(h).ok())
                        .ok_or_else(|| bad(format!("entry {i}: `hue` is not a number")))?,
                };
                Wanted::Battler {
                    picture: monster?,
                    hue,
                }
            }
            _ => {
                return Err(bad(format!(
                    "entry {i}: it needs `backdrop_file` or `monster_file`, and only one"
                )))
            }
        });
    }
    Ok(wanted)
}

/// Draws every picture of a request into `dir`, which is created if it is
/// not there.
pub fn write(dir: &Path, wanted: &[Wanted]) -> Result<()> {
    std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
    for (i, w) in wanted.iter().enumerate() {
        let picture = match w {
            Wanted::Backdrop(path) => backdrop(path)?,
            Wanted::Battler { picture, hue } => battler(picture, *hue)?,
        };
        picture::write_png(&dir.join(format!("{i}.png")), &picture)?;
    }
    Ok(())
}
