//! RPG_RT's ExFont: the 52 icons a `$` and a letter draw in a text —`$A`
//! to `$Z` and `$a` to `$z`—, read from a sheet, a PNG or a BMP.
//!
//! The sheet is 13 icons by 4, each 12x12, indexed with index 0 as the
//! colour key: RM2k paints the rest with the text's colour, like a letter,
//! so what an icon is here is its mask. easyrpg-player reads a sheet the
//! same way, `Font/ExFont` in the game's directory.
//!
//! RPG_RT keeps its own as the `EXFONT` bitmap resource of its executable,
//! and that is **not read here**: which sheet a game is drawn with is the
//! caller's choice, a file it names —the converter's `[text] exfont`, in
//! the port's directory—, not something found in the game's directory. A
//! game's executable is not a file the tools open.

use crate::fail::{Bad, Result};
use crate::picture::Picture;
use std::path::Path;

/// An icon's side, in pixels.
pub const SIZE: usize = 12;
/// How many icons a row of the sheet has, and how many there are.
pub const PER_ROW: usize = 13;
pub const ICONS: usize = 52;

/// The 52 icons, each as twelve rows: bit `x` of a row is column `x`, bit
/// 0 the leftmost, set where the icon has ink.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExFont {
    pub icons: Vec<[u16; SIZE]>,
}

impl ExFont {
    /// The icons of a sheet as RPG_RT keeps it: ink wherever the picture is
    /// not transparent. A sheet smaller than 13x4 icons leaves the ones it
    /// does not reach blank, as easyrpg does.
    pub fn from_sheet(sheet: &Picture) -> ExFont {
        let icons = (0..ICONS)
            .map(|i| {
                let (x0, y0) = ((i % PER_ROW) * SIZE, (i / PER_ROW) * SIZE);
                let mut rows = [0u16; SIZE];
                for (y, row) in rows.iter_mut().enumerate() {
                    for x in 0..SIZE {
                        if sheet.get((x0 + x) as i64, (y0 + y) as i64)[3] != 0 {
                            *row |= 1 << x;
                        }
                    }
                }
                rows
            })
            .collect();
        ExFont { icons }
    }

    /// The ExFont in the sheet at `path`, a PNG or a BMP; anything else is
    /// refused, an executable too.
    pub fn read(path: &Path) -> Result<ExFont> {
        let sheet = path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| e.eq_ignore_ascii_case("png") || e.eq_ignore_ascii_case("bmp"));
        if !sheet {
            return Err(Bad::usage(format!(
                "{}: an ExFont is a sheet, a PNG or a BMP",
                path.display()
            )));
        }
        Ok(ExFont::from_sheet(&crate::picture::read_rm2k(path)?))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A BMP file: 156x48 at 8 bits, index 0 the key, and `ink` the pixels
    /// at index 1.
    fn sheet(ink: &[(usize, usize)]) -> Vec<u8> {
        let (w, h) = (PER_ROW * SIZE, 4 * SIZE);
        let mut b = Vec::new();
        b.extend_from_slice(&40u32.to_le_bytes());
        b.extend_from_slice(&(w as i32).to_le_bytes());
        b.extend_from_slice(&(h as i32).to_le_bytes());
        b.extend_from_slice(&1u16.to_le_bytes());
        b.extend_from_slice(&8u16.to_le_bytes());
        b.extend_from_slice(&[0; 4]); // no compression
        b.extend_from_slice(&[0; 4]);
        b.extend_from_slice(&[0; 8]);
        b.extend_from_slice(&2u32.to_le_bytes()); // two colours
        b.extend_from_slice(&[0; 4]);
        b.extend_from_slice(&[0, 0, 0, 0, 255, 255, 255, 0]);
        // Rows bottom to top, 156 bytes each, already a multiple of four.
        for y in (0..h).rev() {
            for x in 0..w {
                b.push(u8::from(ink.contains(&(x, y))));
            }
        }
        let mut file = b"BM".to_vec();
        file.extend_from_slice(&((14 + b.len()) as u32).to_le_bytes());
        file.extend_from_slice(&[0; 4]);
        // The pixels start after this header, the info header and the two
        // colours.
        file.extend_from_slice(&(14u32 + 40 + 8).to_le_bytes());
        file.extend_from_slice(&b);
        file
    }

    fn scratch(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("exfont-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// Icon 0's top left pixel, icon 14's —`$O`, second row— last one, and
    /// icon 51's —`$z`— first pixel of its last row.
    #[test]
    fn the_exfont_is_read_from_a_sheet() {
        let dir = scratch("sheet");
        let path = dir.join("exfont.bmp");
        std::fs::write(
            &path,
            sheet(&[(0, 0), (12 + 11, 12 + 11), (12 * 12, 36 + 11)]),
        )
        .unwrap();
        let font = ExFont::read(&path).unwrap();
        assert_eq!(font.icons.len(), ICONS);
        assert_eq!(font.icons[0][0], 1);
        assert_eq!(font.icons[14][11], 1 << 11);
        assert_eq!(font.icons[51][11], 1);
        let lit: usize = font
            .icons
            .iter()
            .flatten()
            .map(|r| r.count_ones() as usize)
            .sum();
        assert_eq!(lit, 3, "index 0 is the key");
        std::fs::remove_dir_all(&dir).unwrap();
    }

    /// The executable that carries RPG_RT's own is not read, even if it is
    /// there.
    #[test]
    fn an_executable_is_not_a_sheet() {
        let dir = scratch("exe");
        let path = dir.join("RPG_RT.exe");
        std::fs::write(&path, b"MZ").unwrap();
        assert!(ExFont::read(&path).is_err());
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
