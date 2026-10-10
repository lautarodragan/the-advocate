//! One picture over another through its alpha, as Pillow's
//! `Image.alpha_composite` does it —`libImaging/AlphaComposite.c`—, with
//! its integers and its roundings: the cells of a battle animation were
//! stacked with it, and the frame they make is what gets scaled and
//! reduced.
//!
//! It is not the blend `rm2k-render` draws with: that one mixes the colour
//! and keeps the destination's alpha; this one is "over", and computes the
//! alpha of the result too, so a translucent cell over nothing stays
//! translucent.

use rm2k_render::Picture;

/// Pillow's fixed point for the colour: seven extra bits.
const PRECISION_BITS: u32 = 7;

/// `((a >> 8) + a) >> 8`: a division by 255, rounded when `a` carries its
/// half.
fn div255(a: u32) -> u32 {
    ((a >> 8) + a) >> 8
}

/// One pixel of `src` over one of `dst`.
fn over(dst: [u8; 4], src: [u8; 4]) -> [u8; 4] {
    if src[3] == 0 {
        return dst;
    }
    let (sa, da) = (src[3] as u32, dst[3] as u32);
    let blend = da * (255 - sa);
    let outa255 = sa * 255 + blend;
    let coef1 = sa * 255 * 255 * (1 << PRECISION_BITS) / outa255;
    let coef2 = 255 * (1 << PRECISION_BITS) - coef1;
    let channel = |k: usize| {
        let tmp = src[k] as u32 * coef1 + dst[k] as u32 * coef2;
        (div255(tmp + (0x80 << PRECISION_BITS)) >> PRECISION_BITS) as u8
    };
    [
        channel(0),
        channel(1),
        channel(2),
        div255(outa255 + 0x80) as u8,
    ]
}

/// `canvas.alpha_composite(piece, (x, y))`: what of `piece` falls inside
/// the canvas goes over it; the rest is cut.
pub fn over_at(canvas: &mut Picture, piece: &Picture, x: i64, y: i64) {
    for py in 0..piece.height as i64 {
        let cy = y + py;
        if cy < 0 || cy >= canvas.height as i64 {
            continue;
        }
        for px in 0..piece.width as i64 {
            let cx = x + px;
            if cx < 0 || cx >= canvas.width as i64 {
                continue;
            }
            let at = (cy as usize * canvas.width + cx as usize) * 4;
            let dst = [
                canvas.rgba[at],
                canvas.rgba[at + 1],
                canvas.rgba[at + 2],
                canvas.rgba[at + 3],
            ];
            let out = over(dst, piece.get(px, py));
            canvas.rgba[at..at + 4].copy_from_slice(&out);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opaque_over_anything_is_itself() {
        assert_eq!(
            over([1, 2, 3, 77], [200, 100, 50, 255]),
            [200, 100, 50, 255]
        );
    }

    #[test]
    fn transparent_over_anything_leaves_it() {
        assert_eq!(over([1, 2, 3, 77], [200, 100, 50, 0]), [1, 2, 3, 77]);
    }

    #[test]
    fn translucent_over_nothing_keeps_its_alpha() {
        assert_eq!(over([0, 0, 0, 0], [200, 100, 50, 128]), [200, 100, 50, 128]);
    }
}
