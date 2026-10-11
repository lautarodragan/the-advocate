//! What a cartridge stores in the `.msu`: the MSU-1's data port.
//!
//! The `.msu` is the file that turns the MSU-1 on. The MSU-1 exposes it as
//! a stream: the ROM writes a 32-bit position to $2000..$2003 —the write to
//! $2003 is the one that seeks—, waits for bit 7 of $2000 to clear and reads
//! from $2001 byte by byte, advancing on its own; by DMA with the source
//! fixed at $2001 it reads at the speed of any DMA.
//!
//! What it carries first are **the quality battle backdrops**, and **all of
//! the game's**, whether or not they are in the cartridge's maps. **Without
//! MSU-1 the game has to work the same**, so the ROM carries a light
//! fallback of its own; the `.msu` replaces it when it is there and it
//! belongs to this cartridge. The backdrops come made: this only puts them
//! in their place. Behind them go the quality sound effects, one entry per
//! effect of each audio package: which version of each goes in each
//! package, and why, is [`crate::msu`]'s.
//!
//! ## The format
//!
//! All little-endian:
//!
//! ```text
//!     $00     8  the signature: the first 8 bytes of the sha256 of
//!                everything that follows, up to the end of the last
//!                entry
//!     $08     4  the game's signature: `[rom] msu_data_signature`
//!     $0C     2  the format version, 2 today
//!     $0E     2  how many entries there are, N
//!     $10     8N per entry: where it starts in the file and how long it
//!                is, 4 and 4
//!     ...        zeros, up to BACKDROPS_START
//!     $10000     the backdrops, one every BACKDROP_SPAN bytes and in order
//!                of number: backdrop k at `backdrop_offset(k)`
//!     ...        after the last one, the other entries, one after the
//!                other and in the order of the index
//!     ...        and, only in a cartridge that needs the MSU-1, from the
//!                next sector, what did not fit in the ROM
//! ```
//!
//! **That last region is not this module's**: the bank packing appends it,
//! after the converter wrote the rest —it is the packing that knows what
//! does not fit—, and it is not in the index nor under the signature,
//! which is why the signature ends where the entries end. It carries its
//! own. See `msu.rs` in `rm2k-snes-cartridge`.
//!
//! **The backdrop region is fixed.** Up to version 1 the entries all went
//! one after the other behind the index, so the place of a backdrop depended
//! on how many entries there were —and the sound effects belong to each
//! cartridge— and on which backdrops the cartridge carried. Since 2026-09-27
//! the `.msu` carries all of the game's backdrops, each one with its number,
//! and backdrop k is at the same byte in the `.msu` of any cartridge:
//! `BACKDROPS_START + k * BACKDROP_SPAN` its tiles, and `COLORS_AT` further
//! on its colors. The index is still there, and says the same thing, for
//! the tools. If the index were ever to go past `BACKDROPS_START` —more than
//! eight thousand entries— [`build`] refuses.
//!
//! Each place is 32,768 bytes of tiles, 192 of colors and padding up to the
//! next multiple of 512: that way the tiles of each backdrop start at a
//! sector of the SD card, which is where the FX Pak reads them from. It is
//! not measured that this makes it faster; it costs 320 bytes per backdrop.
//!
//! **The signature is of the content, not of the build.** The ROM carries
//! the one it expects —it goes in `musicdata.inc`— and compares it with the
//! first 8 bytes of the `.msu` before reading anything: if they do not match
//! —a `.msu` from another build, an empty one, a truncated one— it uses the
//! ROM. That it is of the content and not of the commit means that a `.msu`
//! from another build **with the same data** is accepted, and that is fine:
//! what is protected is that the bytes are the ones the ROM expects, and
//! covering the index with the hash also covers where each thing is.
//!
//! **The ROM reads the positions from its `.inc`, not from the index.** Once
//! the signature is accepted, the file's index and the `.inc` constants are
//! the same data by construction —they come from [`build`]—, and reading it
//! on the console would be one more seek per battle to learn nothing. The
//! index is there for the tools ([`index`]) and so that adding something
//! else later means adding entries, without changing the format.
//!
//! Each backdrop is two entries, in this order: its 512 tiles at 8bpp
//! —32,768 bytes, exactly as they go to WRAM— and its 96 15-bit colors —192
//! bytes, exactly as they go to CGRAM from entry 32—.

use crate::fail::{Bad, Result};
use sha2::{Digest, Sha256};

pub const VERSION: u16 = 2;
pub const SIGNATURE_SIZE: usize = 8;
pub const HEADER_SIZE: usize = 16;
pub const ENTRY_SIZE: usize = 8;

/// The backdrop region: see "The format".
pub const BACKDROPS_START: usize = 0x10000;
/// 512 tiles at 8bpp.
pub const COLORS_AT: usize = 0x8000;
/// And the 192 bytes of colors, to the sector.
pub const BACKDROP_SPAN: usize = 0x8200;
pub const SECTOR: usize = 512;
const _: () = assert!(BACKDROP_SPAN % SECTOR == 0 && BACKDROP_SPAN >= COLORS_AT + 96 * 2);

/// Where the tiles of backdrop number `k` are; its colors, `COLORS_AT`
/// further on.
pub fn backdrop_offset(k: usize) -> usize {
    BACKDROPS_START + k * BACKDROP_SPAN
}

/// The 8 bytes that go at the start: from the sha256 of what follows.
pub fn signature_of(body: &[u8]) -> [u8; SIGNATURE_SIZE] {
    let digest = Sha256::digest(body);
    digest[..SIGNATURE_SIZE].try_into().unwrap()
}

/// The `.msu` with these entries, and where each one ended up.
///
/// `magic` is the game's four bytes. The first `2 * backdrops` entries are
/// the backdrops —tiles and colors of each— and go in their fixed place,
/// [`backdrop_offset`]; the rest after the backdrop region, one after the
/// other. Without backdrops, all of them in a row after the index.
pub fn build(entries: &[&[u8]], backdrops: usize, magic: &[u8; 4]) -> Result<(Vec<u8>, Vec<usize>)> {
    let mut offsets = Vec::with_capacity(entries.len());
    let mut offset = HEADER_SIZE + ENTRY_SIZE * entries.len();
    if backdrops > 0 {
        if offset > BACKDROPS_START {
            return Err(Bad::answer(format!(
                "the .msu index is {offset} B long and overlaps the backdrop region, at ${BACKDROPS_START:X}"
            )));
        }
        for k in 0..backdrops {
            let (tiles, colors) = (entries[2 * k], entries[2 * k + 1]);
            if tiles.len() > COLORS_AT || COLORS_AT + colors.len() > BACKDROP_SPAN {
                return Err(Bad::answer(format!("backdrop {k} does not fit in its place in the .msu")));
            }
            offsets.push(backdrop_offset(k));
            offsets.push(backdrop_offset(k) + COLORS_AT);
        }
        // What follows goes after the whole region, not after the last byte
        // written: that way it does not depend on the size of the last
        // backdrop either.
        offset = backdrop_offset(backdrops);
    }
    for data in &entries[2 * backdrops..] {
        offsets.push(offset);
        offset += data.len();
    }
    let mut blob = vec![0u8; SIGNATURE_SIZE];
    blob.extend_from_slice(magic);
    blob.extend_from_slice(&VERSION.to_le_bytes());
    blob.extend_from_slice(&(entries.len() as u16).to_le_bytes());
    for (&p, data) in offsets.iter().zip(entries) {
        blob.extend_from_slice(&(p as u32).to_le_bytes());
        blob.extend_from_slice(&(data.len() as u32).to_le_bytes());
    }
    for (&p, data) in offsets.iter().zip(entries) {
        // Zero padding up to where it goes: the signature covers it like
        // everything else.
        blob.resize(p.max(blob.len()), 0);
        blob.extend_from_slice(data);
    }
    let signature = signature_of(&blob[SIGNATURE_SIZE..]);
    blob[..SIGNATURE_SIZE].copy_from_slice(&signature);
    Ok((blob, offsets))
}

/// The index of a `.msu` of this game: `(where, length)` per entry, or why
/// it is not a valid one.
pub fn index(blob: &[u8], magic: &[u8; 4]) -> Result<Vec<(u32, u32)>> {
    if blob.len() < HEADER_SIZE || &blob[SIGNATURE_SIZE..SIGNATURE_SIZE + 4] != magic {
        return Err(Bad::answer("not a .msu with data from this game"));
    }
    let entries = raw_index(blob)?;
    if signature_of(&blob[SIGNATURE_SIZE..signed_end(&entries)]) != blob[..SIGNATURE_SIZE] {
        return Err(Bad::answer("the signature does not match the content"));
    }
    let version = u16::from_le_bytes([blob[SIGNATURE_SIZE + 4], blob[SIGNATURE_SIZE + 5]]);
    if version != VERSION {
        return Err(Bad::answer(format!("version {version}, and this reads {VERSION}")));
    }
    Ok(entries)
}

/// The index as it is written, checking only that the file reaches it and
/// its entries.
fn raw_index(blob: &[u8]) -> Result<Vec<(u32, u32)>> {
    if blob.len() < HEADER_SIZE {
        return Err(Bad::answer("not a .msu with data"));
    }
    let n = u16::from_le_bytes([blob[SIGNATURE_SIZE + 6], blob[SIGNATURE_SIZE + 7]]) as usize;
    if blob.len() < HEADER_SIZE + ENTRY_SIZE * n {
        return Err(Bad::answer("the .msu is shorter than its index"));
    }
    let long = |at: usize| u32::from_le_bytes(blob[at..at + 4].try_into().unwrap());
    let entries: Vec<(u32, u32)> = (0..n)
        .map(|k| {
            let at = HEADER_SIZE + ENTRY_SIZE * k;
            (long(at), long(at + 4))
        })
        .collect();
    if signed_end(&entries) > blob.len() {
        return Err(Bad::answer("the .msu is shorter than its entries"));
    }
    Ok(entries)
}

/// Where what the signature covers ends: after the last entry, or after
/// the index if there are none. What may come behind is the region of what
/// did not fit in the ROM, which carries its own: see "The format".
fn signed_end(entries: &[(u32, u32)]) -> usize {
    entries
        .iter()
        .map(|&(at, length)| at as usize + length as usize)
        .fold(HEADER_SIZE + ENTRY_SIZE * entries.len(), usize::max)
}

/// The same `.msu`, signed again: what whoever changes its bytes has to do
/// for it to pass as the `.msu` of another build.
pub fn sign(blob: &[u8]) -> Result<Vec<u8>> {
    let end = signed_end(&raw_index(blob)?);
    let mut out = blob.to_vec();
    let signature = signature_of(&out[SIGNATURE_SIZE..end]);
    out[..SIGNATURE_SIZE].copy_from_slice(&signature);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn what_it_builds_it_reads_back() {
        let tiles = vec![7u8; COLORS_AT];
        let colors = vec![9u8; 192];
        let effect = vec![1u8, 2, 3];
        let (blob, offsets) = build(&[&tiles, &colors, &effect], 1, b"TEST").unwrap();
        assert_eq!(offsets, vec![BACKDROPS_START, BACKDROPS_START + COLORS_AT, backdrop_offset(1)]);
        let found = index(&blob, b"TEST").unwrap();
        assert_eq!(found, vec![(0x10000, 0x8000), (0x18000, 192), (0x18200, 3)]);
        assert_eq!(&blob[0x18200..], &[1, 2, 3]);
        assert!(index(&blob, b"ELSE").is_err());
        let mut other = blob.clone();
        other[0x18200] ^= 0xFF;
        assert!(index(&other, b"TEST").is_err());
        assert!(index(&sign(&other).unwrap(), b"TEST").is_ok());
    }

    #[test]
    fn what_goes_behind_the_entries_is_not_under_the_signature() {
        let (blob, _) = build(&[&[1u8, 2, 3][..]], 0, b"TEST").unwrap();
        let mut longer = blob.clone();
        longer.resize(blob.len() + 700, 5);
        assert_eq!(index(&longer, b"TEST").unwrap(), index(&blob, b"TEST").unwrap());
        assert_eq!(sign(&longer).unwrap()[..SIGNATURE_SIZE], blob[..SIGNATURE_SIZE]);
        assert!(index(&blob[..blob.len() - 1], b"TEST").is_err(), "an entry cut short");
    }

    #[test]
    fn a_backdrop_that_does_not_fit_is_refused() {
        let tiles = vec![0u8; COLORS_AT + 1];
        assert!(build(&[&tiles, &[]], 1, b"TEST").is_err());
    }
}
