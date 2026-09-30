//! Against what Pillow 12.3.0 wrote: pictures of noise made by a
//! congruence, resized with `Image.LANCZOS`, and the sha256 of each result.
//! Noise is the hard case —every weight of the filter counts, and the
//! negative lobes push sums past both ends of a byte—, and the sizes are
//! the ones a converter asks for: a screen shrunk to a smaller one, a
//! picture enlarged, one axis only, and a picture a hundred times taller
//! than wide, which Pillow does in two calls. The RGBA ones carry fully
//! transparent, fully opaque and translucent pixels.

use sha2::{Digest, Sha256};

/// (width, height, new width, new height, channels, sha256 of Pillow's).
const CASES: &[(usize, usize, usize, usize, usize, &str)] = &[
    (320, 240, 256, 224, 3, "5a63804bad2ab13dabcd1db3d50faa4a6acbfe55f2c73f222c24a32b2421a1ee"),
    (320, 160, 256, 128, 3, "52f4e74e3e26e5788598ded8b2df1e5229eb764d2aa161d9ba19a715845be8e6"),
    (320, 160, 128, 64, 3, "42c8c6dacf8acb297ad65668009e0394d0148b9ab330c3dab6d447f6a0dfe178"),
    (233, 31, 186, 29, 3, "2c10bcee9266ef4214f860a1f6aa920281595bd95f732a57c280867efa222367"),
    (7, 5, 13, 11, 3, "c52db0ed4d69b4fc273ffed90158cbebb3fd01d63f8edd52f0f460774309e4a2"),
    (10, 3, 10, 7, 3, "ee888a18273836f51821ad2b0b68777f565169a76f4b9e4791e3bf462c8e7207"),
    (2, 300, 1, 50, 3, "09b58a0e9d03490596213226cc0cf9199a81dc86eeed455fef344d90fef476a5"),
    (96, 96, 64, 64, 4, "2159b01137ef7ad214fdc9282fe92ab6800e812e75b1fa8b6bd2d111a8bb8fcf"),
    (536, 416, 64, 49, 4, "2397d56faa01e68ba26f0072c30463e28d57f2ccfdd104e54a0bf7f29ea6e85b"),
    (48, 40, 38, 32, 4, "27ebbbc18059e736c84d7747d8dc1543e968bc93967629bb1cfdafa2fdbd4d0f"),
    (9, 4, 3, 4, 4, "f73e378c3674f34e94091571c1c86b65789c26663204d43780844c3b3a1197ae"),
];

/// The noise: glibc's `rand` congruence, a byte from bits 16 to 23. An
/// alpha is folded to 0 below 64 and to 255 from 192, so all three kinds
/// of pixel are common.
fn picture(width: usize, height: usize, channels: usize, seed: u64) -> Vec<u8> {
    let mut x = seed;
    let mut out = Vec::with_capacity(width * height * channels);
    for _ in 0..width * height {
        for c in 0..channels {
            x = (x * 1103515245 + 12345) % (1 << 31);
            let b = ((x >> 16) & 0xFF) as u8;
            out.push(if c == 3 {
                match b {
                    0..=63 => 0,
                    192..=255 => 255,
                    _ => b,
                }
            } else {
                b
            });
        }
    }
    out
}

#[test]
fn every_case_is_what_pillow_wrote() {
    for (k, &(w, h, ow, oh, channels, sha)) in CASES.iter().enumerate() {
        let data = picture(w, h, channels, k as u64 + 1);
        let out = if channels == 3 {
            resample::lanczos_rgb(&data, w, h, ow, oh)
        } else {
            resample::lanczos_rgba(&data, w, h, ow, oh)
        };
        let got = format!("{:x}", Sha256::digest(&out));
        assert_eq!(got, sha, "{w}x{h} -> {ow}x{oh}, {channels} channels");
    }
}
