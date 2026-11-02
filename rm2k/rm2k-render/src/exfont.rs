//! RPG_RT's ExFont: the 52 icons a `$` and a letter draw in a text —`$A`
//! to `$Z` and `$a` to `$z`—, read from where RPG_RT has them, a bitmap
//! resource of its own executable.
//!
//! The sheet is 13 icons by 4, each 12x12, indexed with index 0 as the
//! colour key: RM2k paints the rest with the text's colour, like a letter,
//! so what an icon is here is its mask. easyrpg-player reads it the same
//! way, `EXEReader::GetExFont`: the `BITMAP` resource named `EXFONT`, whose
//! bytes are a BMP without its file header.
//!
//! The executable is the game's, read from its directory like its
//! ChipSets: nothing of it is kept anywhere but in what is built from it.
//!
//! **Which one**, as easyrpg-player looks for it: a sheet of the game's own,
//! `Font/ExFont` or `ExFont` as a PNG or a BMP, before anything —see
//! [`find`]—; then `RPG_RT.exe`. A game that runs with another executable
//! names it: easyrpg's `engine_path`, the project file's `[text] exfont` in
//! the converter.

use crate::fail::{Bad, Result};
use crate::picture::{bmp_from_bytes, Picture};
use std::path::{Path, PathBuf};

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

    /// The ExFont of an executable's bytes: `None` if it carries none.
    pub fn from_exe(exe: &[u8], name: &str) -> Result<Option<ExFont>> {
        let Some(bitmap) = exfont_resource(exe) else {
            return Ok(None);
        };
        // The resource is a BMP without the 14 bytes of its file header:
        // they are written back, with where the pixels start —after the info
        // header and the palette—.
        let u32_at = |at: usize| {
            bitmap
                .get(at..at + 4)
                .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        };
        let short = || Bad::answer(format!("{name}: its EXFONT is cut short"));
        let header = u32_at(0).ok_or_else(short)? as usize;
        let (depth, colors) = if header == 12 {
            let d = bitmap.get(10..12).ok_or_else(short)?;
            (u16::from_le_bytes([d[0], d[1]]) as usize, 0)
        } else {
            let d = bitmap.get(14..16).ok_or_else(short)?;
            (
                u16::from_le_bytes([d[0], d[1]]) as usize,
                u32_at(32).ok_or_else(short)? as usize,
            )
        };
        let colors = if colors == 0 && depth <= 8 {
            1 << depth
        } else {
            colors
        };
        let entry = if header == 12 { 3 } else { 4 };
        let bits = 14 + header + colors * entry;
        let mut file = Vec::with_capacity(14 + bitmap.len());
        file.extend_from_slice(b"BM");
        file.extend_from_slice(&((14 + bitmap.len()) as u32).to_le_bytes());
        file.extend_from_slice(&[0; 4]);
        file.extend_from_slice(&(bits as u32).to_le_bytes());
        file.extend_from_slice(bitmap);
        let sheet = bmp_from_bytes(&file, &format!("{name}'s EXFONT"), true)?;
        Ok(Some(ExFont::from_sheet(&sheet)))
    }

    /// The ExFont in the file at `path`: a sheet, if it is a PNG or a BMP,
    /// or an executable's. `None` for an executable without one.
    pub fn read(path: &Path) -> Result<Option<ExFont>> {
        let sheet = path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| e.eq_ignore_ascii_case("png") || e.eq_ignore_ascii_case("bmp"));
        if sheet {
            return Ok(Some(ExFont::from_sheet(&crate::picture::read_rm2k(path)?)));
        }
        let bytes =
            std::fs::read(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        ExFont::from_exe(&bytes, &path.display().to_string())
    }
}

/// Where the game in `game_dir` keeps its ExFont: `named`, a file of its
/// directory, when the project names one; otherwise a sheet of its own,
/// `Font/ExFont` or `ExFont` as a PNG or a BMP, and otherwise its
/// `RPG_RT.exe` —easyrpg's order—. Names are matched without case: a game
/// copied from Windows may have `RPG_RT.EXE`. `None` when it has none of
/// them.
pub fn find(game_dir: &Path, named: Option<&str>) -> Option<PathBuf> {
    if let Some(name) = named {
        return Some(game_dir.join(name));
    }
    let candidates = [
        ("Font", "ExFont.png"),
        ("Font", "ExFont.bmp"),
        ("", "ExFont.png"),
        ("", "ExFont.bmp"),
        ("", "RPG_RT.exe"),
    ];
    candidates.iter().find_map(|(dir, file)| {
        let dir = if dir.is_empty() {
            game_dir.to_path_buf()
        } else {
            entry(game_dir, dir)?
        };
        entry(&dir, file)
    })
}

/// The entry of `dir` called `name`, matched without case.
fn entry(dir: &Path, name: &str) -> Option<PathBuf> {
    std::fs::read_dir(dir)
        .ok()?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .find(|p| {
            p.file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.eq_ignore_ascii_case(name))
        })
}

/// The bytes of the `BITMAP` resource named `EXFONT` of a PE executable,
/// if it has one: the resource directory's type 2, then the entry with that
/// name, then its first language.
fn exfont_resource(exe: &[u8]) -> Option<&[u8]> {
    let u16_at = |at: usize| {
        exe.get(at..at + 2)
            .map(|b| u16::from_le_bytes([b[0], b[1]]))
    };
    let u32_at = |at: usize| {
        exe.get(at..at + 4)
            .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    };
    if exe.get(0..2)? != b"MZ" {
        return None;
    }
    let pe = u32_at(0x3C)? as usize;
    if exe.get(pe..pe + 4)? != b"PE\0\0" {
        return None;
    }
    let sections = u16_at(pe + 6)? as usize;
    let optional = pe + 24;
    let optional_size = u16_at(pe + 20)? as usize;
    // The data directories start at 96 in a 32-bit optional header and at
    // 112 in a 64-bit one; the resources are the third.
    let directories = optional
        + match u16_at(optional)? {
            0x10B => 96,
            0x20B => 112,
            _ => return None,
        };
    let rsrc_rva = u32_at(directories + 2 * 8)? as usize;
    if rsrc_rva == 0 {
        return None;
    }
    // The section the resources are in, to turn their addresses into
    // offsets of the file.
    let table = optional + optional_size;
    let (base, delta) = (0..sections).find_map(|i| {
        let s = table + 40 * i;
        let (size, va, raw_size, raw) = (
            u32_at(s + 8)? as usize,
            u32_at(s + 12)? as usize,
            u32_at(s + 16)? as usize,
            u32_at(s + 20)? as usize,
        );
        (va <= rsrc_rva && rsrc_rva < va + size.max(raw_size))
            .then(|| (raw + (rsrc_rva - va), va as i64 - raw as i64))
    })?;
    // A directory's entries: (name or id, offset of what it points to).
    let entries = |dir: usize| -> Option<Vec<(u32, u32)>> {
        let n = u16_at(dir + 12)? as usize + u16_at(dir + 14)? as usize;
        (0..n)
            .map(|i| Some((u32_at(dir + 16 + 8 * i)?, u32_at(dir + 20 + 8 * i)?)))
            .collect()
    };
    let named = |id: u32, name: &str| -> bool {
        if id & 0x8000_0000 == 0 {
            return false;
        }
        let at = base + (id & 0x7FFF_FFFF) as usize;
        let Some(len) = u16_at(at) else {
            return false;
        };
        let units: Option<Vec<u16>> = (0..len as usize).map(|k| u16_at(at + 2 + 2 * k)).collect();
        units.is_some_and(|u| String::from_utf16_lossy(&u).eq_ignore_ascii_case(name))
    };
    let subdirectory =
        |to: u32| (to & 0x8000_0000 != 0).then(|| base + (to & 0x7FFF_FFFF) as usize);
    let (_, bitmaps) = entries(base)?.into_iter().find(|&(id, _)| id == 2)?;
    let (_, exfont) = entries(subdirectory(bitmaps)?)?
        .into_iter()
        .find(|&(id, _)| named(id, "EXFONT"))?;
    // A name points to its languages, and the first is the one taken.
    let mut leaf = exfont;
    while let Some(dir) = subdirectory(leaf) {
        leaf = entries(dir)?.first()?.1;
    }
    let data = base + leaf as usize;
    let (rva, size) = (u32_at(data)? as i64, u32_at(data + 4)? as usize);
    let at = usize::try_from(rva - delta).ok()?;
    exe.get(at..at + size)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A PE with one section of resources: a `BITMAP` directory with
    /// `name`, one language, and `bitmap` as its data. Only what the reader
    /// looks at is filled in.
    fn exe_with(name: &str, bitmap: &[u8]) -> Vec<u8> {
        const SECTION_VA: u32 = 0x3000;
        const RAW: usize = 0x200;
        let mut exe = vec![0u8; RAW];
        exe[0..2].copy_from_slice(b"MZ");
        let pe = 0x40usize;
        exe[0x3C..0x40].copy_from_slice(&(pe as u32).to_le_bytes());
        exe[pe..pe + 4].copy_from_slice(b"PE\0\0");
        exe[pe + 6..pe + 8].copy_from_slice(&1u16.to_le_bytes());
        let optional_size = 224u16;
        exe[pe + 20..pe + 22].copy_from_slice(&optional_size.to_le_bytes());
        let optional = pe + 24;
        exe[optional..optional + 2].copy_from_slice(&0x10Bu16.to_le_bytes());
        let directories = optional + 96;
        exe[directories + 16..directories + 20].copy_from_slice(&SECTION_VA.to_le_bytes());
        // The resources: root -> type 2 -> the name -> language -> data.
        let mut r = vec![0u8; 0x100];
        let put32 =
            |r: &mut Vec<u8>, at: usize, v: u32| r[at..at + 4].copy_from_slice(&v.to_le_bytes());
        let put16 =
            |r: &mut Vec<u8>, at: usize, v: u16| r[at..at + 2].copy_from_slice(&v.to_le_bytes());
        // Root, one id entry: type 2 at 0x18.
        put16(&mut r, 14, 1);
        put32(&mut r, 16, 2);
        put32(&mut r, 20, 0x8000_0018);
        // Type 2, one named entry: the name at 0x60, languages at 0x30.
        put16(&mut r, 0x18 + 12, 1);
        put32(&mut r, 0x18 + 16, 0x8000_0060);
        put32(&mut r, 0x18 + 20, 0x8000_0030);
        // Languages, one: the data entry at 0x48.
        put16(&mut r, 0x30 + 14, 1);
        put32(&mut r, 0x30 + 16, 0x411);
        put32(&mut r, 0x30 + 20, 0x48);
        // The data entry: the bitmap at 0x100 of the section.
        put32(&mut r, 0x48, SECTION_VA + 0x100);
        put32(&mut r, 0x48 + 4, bitmap.len() as u32);
        let units: Vec<u16> = name.encode_utf16().collect();
        put16(&mut r, 0x60, units.len() as u16);
        for (k, u) in units.iter().enumerate() {
            put16(&mut r, 0x62 + 2 * k, *u);
        }
        r.extend_from_slice(bitmap);
        let table = optional + optional_size as usize;
        let size = r.len() as u32;
        exe[table..table + 8].copy_from_slice(b".rsrc\0\0\0");
        exe[table + 8..table + 12].copy_from_slice(&size.to_le_bytes());
        exe[table + 12..table + 16].copy_from_slice(&SECTION_VA.to_le_bytes());
        exe[table + 16..table + 20].copy_from_slice(&size.to_le_bytes());
        exe[table + 20..table + 24].copy_from_slice(&(RAW as u32).to_le_bytes());
        exe.extend_from_slice(&r);
        exe
    }

    /// A sheet as RPG_RT carries it, without the file header: 156x48 at 8
    /// bits, index 0 the key, and `ink` the pixels at index 1.
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
        b
    }

    /// Icon 0's top left pixel, icon 14's —`$O`, second row— last one, and
    /// icon 51's —`$z`— first pixel of its last row.
    #[test]
    fn the_exfont_is_read_from_the_executable_s_resource() {
        let exe = exe_with(
            "EXFONT",
            &sheet(&[(0, 0), (12 + 11, 12 + 11), (12 * 12, 36 + 11)]),
        );
        let font = ExFont::from_exe(&exe, "test").unwrap().expect("an ExFont");
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
    }

    /// easyrpg's order: a sheet of the game's own, `Font/` first, before
    /// the executable, whatever the case of the names; and the one the
    /// project names, before all of them.
    #[test]
    fn a_sheet_of_the_game_s_own_goes_before_the_executable() {
        let dir = std::env::temp_dir().join(format!("exfont-find-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("FONT")).unwrap();
        assert_eq!(find(&dir, None), None);
        std::fs::write(dir.join("RPG_RT.EXE"), b"MZ").unwrap();
        assert_eq!(find(&dir, None), Some(dir.join("RPG_RT.EXE")));
        std::fs::write(dir.join("exfont.png"), b"").unwrap();
        assert_eq!(find(&dir, None), Some(dir.join("exfont.png")));
        std::fs::write(dir.join("FONT").join("ExFont.bmp"), b"").unwrap();
        assert_eq!(find(&dir, None), Some(dir.join("FONT").join("ExFont.bmp")));
        assert_eq!(
            find(&dir, Some("RPG_RT_a.exe")),
            Some(dir.join("RPG_RT_a.exe"))
        );
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn an_executable_without_it_has_none() {
        let exe = exe_with("LOGO1", &sheet(&[]));
        assert_eq!(ExFont::from_exe(&exe, "test").unwrap(), None);
        assert_eq!(
            ExFont::from_exe(b"not an executable", "test").unwrap(),
            None
        );
    }
}
