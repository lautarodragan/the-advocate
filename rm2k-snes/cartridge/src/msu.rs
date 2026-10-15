//! The data that travels in the `.msu` because it does not fit in the ROM.
//!
//! The `.msu` is the file the MSU-1 serves to the ROM as a stream: the ROM
//! writes a 32-bit position and reads on from there. `rm2k-snes-audio`
//! writes it, with its header, its index and its entries —the battle
//! backdrops and the sound effects, see its `msu_data.rs`—, and **this
//! module appends one more region behind them**: the pieces the packing
//! could not fit in the ROM, when the project allows it (see
//! [`crate::banks`]).
//!
//! ```text
//!     start       8  the region's signature: the first 8 bytes of the
//!                    sha256 of everything after `start + UNIT`
//!     ...            zeros up to `start + UNIT`
//!     start + UNIT   the pieces, each from a multiple of UNIT and padded
//!                    with zeros to the next one
//! ```
//!
//! `start` is where the entries the index describes end, rounded up to the
//! SD card's sector. The region is **not** in the index, and the `.msu`'s
//! own signature does not cover it —it covers up to where the entries end:
//! see `index` in `msu_data.rs`—: that is how the packing can add it after
//! the converter wrote the file, without the ROM's other signature
//! changing. It carries its own, which the packing emits for the ROM as
//! `msu_spill_signature`.
//!
//! **Each piece is named by its unit**: the ROM gets, instead of the
//! piece's address, bank [`SPILL_BANK`] —one no data of the cartridge is
//! ever in— and the unit it starts at, and seeks to `start + unit * UNIT`.
//! A unit is 256 bytes so that the seek is three bytes added and one at
//! zero, and so that sixteen bits reach 16 MB. Unit `$FFFF` is never used:
//! the runtime takes it as "go on from where the stream was left".

use sha2::{Digest, Sha256};
use std::path::Path;

/// The bank byte of a piece that lives in the `.msu`. It is in `$00-$3F`,
/// where the cartridge has the system area below `$8000` and no data slot
/// —[`crate::banks::slots`] gives none here—, so no pointer of the
/// cartridge's data has it. The runtime compares against
/// `MSU_SPILL_BANK`, which the packing emits from this.
pub const SPILL_BANK: usize = 0x3D;

/// How the region counts: each piece starts at a multiple of this.
pub const UNIT: usize = 256;

/// The units a piece can start at: from 1 —0 is the signature's— to
/// `$FFFE`.
pub const LAST_UNIT: usize = 0xFFFE;

/// The SD card's sector: where the region starts.
pub const SECTOR: usize = 512;

pub const SIGNATURE: usize = 8;

/// The `.msu` header, as `rm2k-snes-audio` writes it: the signature, the
/// game's four bytes, the version and how many entries; and each entry,
/// where it starts and how long it is.
const HEADER: usize = 16;
const ENTRY: usize = 8;

/// Where the entries of `blob` end: the byte after the last one, or after
/// the index if there are none.
pub fn entries_end(blob: &[u8]) -> Result<usize, String> {
    if blob.len() < HEADER {
        return Err(format!("a .msu of {} bytes, shorter than its header", blob.len()));
    }
    let n = u16::from_le_bytes([blob[14], blob[15]]) as usize;
    let index_end = HEADER + ENTRY * n;
    if blob.len() < index_end {
        return Err("the .msu is shorter than its index".into());
    }
    let long = |at: usize| u32::from_le_bytes(blob[at..at + 4].try_into().unwrap()) as usize;
    Ok((0..n)
        .map(|k| HEADER + ENTRY * k)
        .map(|at| long(at) + long(at + 4))
        .fold(index_end, usize::max))
}

/// Where the region starts in `blob`.
pub fn region_start(blob: &[u8]) -> Result<usize, String> {
    Ok(entries_end(blob)?.div_ceil(SECTOR) * SECTOR)
}

/// How many units a piece of `length` bytes takes.
pub fn units(length: usize) -> usize {
    length.div_ceil(UNIT).max(1)
}

/// The region with `pieces` in this order, the first from unit 1.
pub fn region(pieces: &[Vec<u8>]) -> Vec<u8> {
    let mut out = vec![0u8; UNIT];
    for piece in pieces {
        out.extend_from_slice(piece);
        out.resize(out.len().div_ceil(UNIT) * UNIT, 0);
    }
    let digest = Sha256::digest(&out[UNIT..]);
    out[..SIGNATURE].copy_from_slice(&digest[..SIGNATURE]);
    out
}

/// `region` written into the `.msu` at `path`, from `start`: what was there
/// after the entries —a region from an earlier packing— goes.
pub fn write(path: &Path, start: usize, region: &[u8]) -> Result<(), String> {
    let mut blob = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    blob.truncate(entries_end(&blob)?);
    blob.resize(start, 0);
    blob.extend_from_slice(region);
    std::fs::write(path, blob).map_err(|e| format!("{}: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A `.msu` header with these entries, and their bytes after it.
    fn msu(entries: &[(u32, u32)]) -> Vec<u8> {
        let mut out = vec![0u8; 8];
        out.extend_from_slice(b"TEST");
        out.extend_from_slice(&2u16.to_le_bytes());
        out.extend_from_slice(&(entries.len() as u16).to_le_bytes());
        for (at, length) in entries {
            out.extend_from_slice(&at.to_le_bytes());
            out.extend_from_slice(&length.to_le_bytes());
        }
        let end = entries.iter().map(|(a, l)| (a + l) as usize).max().unwrap_or(0);
        out.resize(out.len().max(end), 7);
        out
    }

    #[test]
    fn no_data_of_the_cartridge_is_in_the_spill_bank() {
        assert!(crate::banks::slots().iter().all(|s| s.bank != SPILL_BANK));
        assert!(crate::banks::FAR2.bank != SPILL_BANK && crate::banks::FAR3.bank != SPILL_BANK && SPILL_BANK > 1);
    }

    #[test]
    fn the_region_goes_after_the_last_entry_on_a_sector() {
        assert_eq!(entries_end(&msu(&[])).unwrap(), 16);
        assert_eq!(region_start(&msu(&[])).unwrap(), 512);
        let blob = msu(&[(0x10000, 0x8000), (0x18000, 192), (0x18200, 3)]);
        assert_eq!(entries_end(&blob).unwrap(), 0x18203);
        assert_eq!(region_start(&blob).unwrap(), 0x18400);
        assert!(entries_end(&blob[..20]).is_err());
    }

    #[test]
    fn each_piece_starts_on_a_unit_and_the_signature_covers_them() {
        let r = region(&[vec![1; 3], vec![2; 257]]);
        assert_eq!(r.len(), 4 * UNIT);
        assert_eq!(&r[UNIT..UNIT + 3], &[1, 1, 1]);
        assert_eq!(r[2 * UNIT], 2);
        assert_eq!(r[4 * UNIT - 1], 0);
        let mut other = r.clone();
        other[2 * UNIT] = 3;
        assert_ne!(region(&[vec![1; 3], vec![3; 257]])[..SIGNATURE], r[..SIGNATURE]);
        assert_eq!(units(0), 1);
        assert_eq!(units(256), 1);
        assert_eq!(units(257), 2);
    }

    #[test]
    fn writing_it_twice_leaves_one_region() {
        let dir = std::env::temp_dir().join(format!("msu-region-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("x.msu");
        let blob = msu(&[(16, 4)]);
        std::fs::write(&path, &blob).unwrap();
        let start = region_start(&blob).unwrap();
        write(&path, start, &region(&[vec![9; 600]])).unwrap();
        write(&path, start, &region(&[vec![5; 10]])).unwrap();
        let back = std::fs::read(&path).unwrap();
        assert_eq!(back.len(), start + 2 * UNIT);
        assert_eq!(&back[..20], &blob[..20]);
        assert_eq!(back[start + UNIT], 5);
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
