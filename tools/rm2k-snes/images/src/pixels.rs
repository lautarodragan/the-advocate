//! The small steps every picture takes: scaling, to fifteen bits, counting
//! its colours, and down to the colours a palette holds.

use adeleine::{keep_most_used, merge_least_visible, Color, Merge};
use rm2k_render::picture::{FilterType, Picture};
use std::collections::HashMap;

/// The PPU's backdrop colour, which is what it paints where there is
/// nothing: a picture reduced with [`most_used`] keeps it at index 0 so
/// the two agree.
pub const BLACK: Color = [0, 0, 0];

/// The picture's colour without its alpha, three bytes a pixel: Pillow's
/// `convert("RGB")`, which drops the alpha and keeps the colour as it is.
pub fn rgb(picture: &Picture) -> Vec<u8> {
    picture
        .rgba
        .chunks_exact(4)
        .flat_map(|p| [p[0], p[1], p[2]])
        .collect()
}

/// The picture's colour scaled to `width` x `height` with LANCZOS, three
/// bytes a pixel. The alpha is dropped **before** scaling, made opaque, so
/// a translucent pixel scales with its colour as it is.
pub fn scaled_rgb(picture: &Picture, width: usize, height: usize) -> Vec<u8> {
    let mut opaque = picture.clone();
    for p in opaque.rgba.chunks_exact_mut(4) {
        p[3] = 255;
    }
    rgb(&opaque.resized(width, height, FilterType::Lanczos3))
}

/// The picture scaled to `width` x `height` with LANCZOS, alpha and all.
pub fn scaled_rgba(picture: &Picture, width: usize, height: usize) -> Picture {
    picture.resized(width, height, FilterType::Lanczos3)
}

/// A colour of eight bits a channel at the console's five: the low three
/// bits dropped.
pub fn to_15_bits(r: u8, g: u8, b: u8) -> Color {
    [r >> 3, g >> 3, b >> 3]
}

/// Three bytes a pixel at the console's five bits a channel.
pub fn rgb_to_15_bits(rgb: &[u8]) -> Vec<Color> {
    rgb.chunks_exact(3)
        .map(|p| to_15_bits(p[0], p[1], p[2]))
        .collect()
}

/// Each colour with its pixels, **in the order they first appear**: the
/// order a merge is handed them in, which is the order its mapping comes
/// back in.
pub fn counts<'a>(colors: impl IntoIterator<Item = &'a Color>) -> Vec<(Color, u64)> {
    let mut at: HashMap<Color, usize> = HashMap::new();
    let mut out: Vec<(Color, u64)> = Vec::new();
    for &c in colors {
        match at.get(&c) {
            Some(&i) => out[i].1 += 1,
            None => {
                at.insert(c, out.len());
                out.push((c, 1));
            }
        }
    }
    out
}

/// Colours kept by use, with black first: the palette and where each
/// colour went. It is how the title, the pictures, the quality backdrops
/// and the animations are reduced; see `adeleine::keep_most_used`.
pub fn most_used(colors: &[Color], keep: usize) -> (Vec<Color>, HashMap<Color, Color>) {
    let counts = counts(colors);
    let kept = keep_most_used(&counts, keep, BLACK);
    let mapping = counts.iter().map(|&(c, _)| c).zip(kept.mapping).collect();
    (kept.palette, mapping)
}

/// Colours merged by what shows the least —`adeleine::merge_least_visible`—
/// down to `keep`: the palette, most used first and ties by the colour; where
/// each colour went; how many colours there were; and the merges. It is how
/// the light backdrops and the battlers are reduced.
pub struct LeastVisible {
    pub palette: Vec<Color>,
    pub mapping: HashMap<Color, Color>,
    pub colors: usize,
    pub merges: Vec<Merge>,
}

pub fn least_visible(colors: &[Color], keep: usize) -> crate::Result<LeastVisible> {
    let counts = counts(colors);
    let merged = merge_least_visible(&counts, keep)?;
    let mapping: HashMap<Color, Color> = counts
        .iter()
        .map(|&(c, _)| c)
        .zip(merged.mapping.iter().copied())
        .collect();
    let mut last: Vec<(Color, u64)> = Vec::new();
    for &(c, n) in &counts {
        let to = mapping[&c];
        match last.iter_mut().find(|(k, _)| *k == to) {
            Some(entry) => entry.1 += n,
            None => last.push((to, n)),
        }
    }
    last.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    Ok(LeastVisible {
        palette: last.into_iter().map(|(c, _)| c).collect(),
        mapping,
        colors: counts.len(),
        merges: merged.merges,
    })
}
