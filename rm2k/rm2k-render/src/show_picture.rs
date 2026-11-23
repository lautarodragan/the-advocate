//! The picture of a `ShowPicture`, as RM2k puts it on the screen: the file
//! with its transparent colour, if the command asks for it, and at the
//! command's transparency.
//!
//! * **The transparent colour** is index 0 of an indexed picture, as in
//!   every RM2k picture; but here it is the command's to choose, and
//!   without it index 0 is drawn like any other colour.
//! * **The transparency**, `top_trans`, is a percentage, and the picture is
//!   drawn at [`opacity`](rm2k_rules::picture::opacity) of it.
//!
//! Where it goes, at what size and in which tone, is the caller's.

use crate::picture::Picture;
use rm2k_rules::picture::opacity;

/// `file` —the picture read without its colour key— as RM2k draws it: with
/// index 0 transparent if `transparent_color`, and every other pixel at
/// the opacity of `top_trans`.
///
/// `keyed` is the same file read with its colour key, which is how this
/// knows which pixels are index 0 without asking the file twice. A pixel
/// the file itself makes translucent keeps that, scaled by the opacity.
pub fn picture(
    file: &Picture,
    keyed: &Picture,
    transparent_color: bool,
    top_trans: i32,
) -> Picture {
    let opacity = opacity(top_trans) as u32;
    let mut out = file.clone();
    for (at, key) in (0..out.rgba.len()).step_by(4).zip(keyed.rgba.chunks(4)) {
        out.rgba[at + 3] = if transparent_color && key[3] == 0 {
            0
        } else {
            (out.rgba[at + 3] as u32 * opacity / 255) as u8
        };
    }
    out
}
