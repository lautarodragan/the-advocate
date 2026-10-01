//! The cartridge's data blocks: which of them go compressed with LZ2, in how
//! many streams, and the WRAM caps each stream has to fit in.

use crate::compress;
use crate::fail::{Bad, Result};
use std::collections::{BTreeMap, HashMap};

/// What the console decompresses when it loads a map, per block class: see
/// `lz2_decompress` in the runtime's `decompress.s`.
pub const COMPRESSED_KINDS: [&str; 5] =
    ["map_tiles", "above_tiles", "sprite_tiles", "anim_tiles", "map_cells"];

// The largest each decompressed stream can be, by where it lands in WRAM:
// see the LZ2 reservation in the runtime's `far_ram.s`, which is where they
// come from, and the `.assert` in `decompress.s`, which checks them against
// the ones the `.inc` carries. The background's tiles are decompressed
// before the animation drawings and can step on their place; the upper layer
// and the sprites go after and cannot.
//
// The background's is **per stream**, not per block: a background of more
// than 32 KB goes in two, and the console decompresses and uploads the first
// before decompressing the second on top of it: see `lz2_backdrop`.
pub const LZ2_CAP_BACKDROP: usize = 0x8000;
pub const LZ2_CAP_ABOVE_AND_SPRITES: usize = 0x6000;
pub const LZ2_CAP_ANIM: usize = 0x2000;
/// Two halves of [`HALF_GRID`].
pub const LZ2_CAP_GRID: usize = 0x10000;

/// The grid goes to the upper half of the two WRAM banks —see `lz2_grid`—,
/// so it is compressed in two streams of up to 32 KB: each one lands whole
/// in one bank, and the decompressor does not have to know how to cross.
pub const HALF_GRID: usize = 0x8000;

/// How many streams of background tiles `lz2_backdrop` reads. A background
/// that fits in one buffer goes in one.
pub const BACKDROP_STREAMS_MAX: usize = 2;

// What decompressing costs on the console, in master cycles, **on the high
// side**: measured on 2026-09-26 over the forty maps of a 4 MB cartridge,
// against loading uncompressed; what was measured does not exceed this model
// by more than half a frame. The boot's budget uses it.
pub const LZ2_CYCLES_PER_COMMAND: usize = 700;
pub const LZ2_CYCLES_PER_BYTE: usize = 60;
/// An NTSC frame, in master cycles.
pub const CYCLES_PER_FRAME: usize = 357_954;

/// The pieces of a block that are each compressed in their own stream.
pub fn compressed_parts<'a>(kind: &str, data: &'a [u8]) -> Vec<&'a [u8]> {
    if kind == "map_cells" {
        let half = data.len().min(HALF_GRID);
        return vec![&data[..half], &data[half..]];
    }
    if kind == "map_tiles" && data.len() > LZ2_CAP_BACKDROP {
        return data.chunks(LZ2_CAP_BACKDROP).collect();
    }
    vec![data]
}

/// How much of each stream fits in WRAM, and how many streams the console
/// reads per block. The grid always goes in two, one per half; the rest in
/// one, except the background.
pub fn caps_per_stream(kind: &str) -> (usize, usize) {
    match kind {
        "map_tiles" => (LZ2_CAP_BACKDROP, BACKDROP_STREAMS_MAX),
        "above_tiles" | "sprite_tiles" => (LZ2_CAP_ABOVE_AND_SPRITES, 1),
        "anim_tiles" => (LZ2_CAP_ANIM, 1),
        "map_cells" => (HALF_GRID, 2),
        _ => panic!("{kind} is not compressed"),
    }
}

/// That each stream of the block fits in its WRAM place, and that there
/// are not more streams than the console reads. A stream that goes over
/// breaks nothing when building: the console decompresses it anyway and
/// steps on whatever is behind, and it shows or not depending on the map.
pub fn check_streams(map_id: i64, kind: &str, data: &[u8]) -> Result<()> {
    let (cap, count) = caps_per_stream(kind);
    let parts = compressed_parts(kind, data);
    for part in &parts {
        if part.len() > cap {
            return Err(Bad::answer(format!(
                "map {map_id}: a stream of {kind} is {} bytes and {cap} fit in WRAM: see the LZ2 \
                 reservation in tools/runtime/far_ram.s",
                part.len()
            )));
        }
    }
    if parts.len() > count {
        return Err(Bad::answer(format!(
            "map {map_id}: {kind} is {} bytes, which is {} streams, and the ROM reads {count}",
            data.len(),
            parts.len()
        )));
    }
    Ok(())
}

/// A map's blocks that go compressed: `{class: the uncompressed bytes}`,
/// for [`COMPRESSED_KINDS`].
pub type RawBlocks = BTreeMap<String, Vec<u8>>;

/// Everything the cartridge carries compressed, each distinct part once:
/// `{raw part: its stream}`. Along the way it enforces the WRAM caps.
pub fn compress_blocks(maps: &[(i64, &RawBlocks)]) -> Result<HashMap<Vec<u8>, Vec<u8>>> {
    let mut parts: Vec<&[u8]> = Vec::new();
    let mut seen: HashMap<&[u8], ()> = HashMap::new();
    for (map_id, blocks) in maps {
        for kind in COMPRESSED_KINDS {
            let data = blocks.get(kind).map(Vec::as_slice).unwrap_or(&[]);
            check_streams(*map_id, kind, data)?;
            for part in compressed_parts(kind, data) {
                if seen.insert(part, ()).is_none() {
                    parts.push(part);
                }
            }
        }
    }
    let streams = compress::compress_many(&parts)?;
    Ok(parts.into_iter().map(<[u8]>::to_vec).zip(streams).collect())
}

/// What goes to the cartridge for a block: its LZ2 stream, or its
/// streams stuck together if it goes in pieces.
pub fn stream_of(kind: &str, data: &[u8], compressed: &HashMap<Vec<u8>, Vec<u8>>) -> Vec<u8> {
    compressed_parts(kind, data)
        .into_iter()
        .flat_map(|part| compressed[part].iter().copied())
        .collect()
}

/// How many frames decompressing a map's blocks takes.
pub fn decompress_frames(blocks: &RawBlocks, compressed: &HashMap<Vec<u8>, Vec<u8>>) -> f64 {
    let mut cycles = 0usize;
    for kind in COMPRESSED_KINDS {
        let data = blocks.get(kind).map(Vec::as_slice).unwrap_or(&[]);
        for part in compressed_parts(kind, data) {
            cycles += compress::commands(&compressed[part]) * LZ2_CYCLES_PER_COMMAND
                + part.len() * LZ2_CYCLES_PER_BYTE;
        }
    }
    cycles as f64 / CYCLES_PER_FRAME as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_background_of_more_than_one_buffer_goes_in_two_streams_and_of_three_is_refused() {
        let cap = LZ2_CAP_BACKDROP;
        assert_eq!(compressed_parts("map_tiles", &vec![0; cap]).len(), 1);
        let two: Vec<u8> = (0..cap + 1152).map(|i| i as u8).collect();
        let parts = compressed_parts("map_tiles", &two);
        assert_eq!(parts.iter().map(|p| p.len()).collect::<Vec<_>>(), vec![cap, 1152]);
        check_streams(66, "map_tiles", &two).unwrap();
        let three = vec![0; 2 * cap + 64];
        assert_eq!(
            check_streams(66, "map_tiles", &three).unwrap_err().message(),
            "map 66: map_tiles is 65600 bytes, which is 3 streams, and the ROM reads 2"
        );
    }

    #[test]
    fn the_grid_always_goes_in_two_halves() {
        assert_eq!(compressed_parts("map_cells", &[1, 2, 3]), vec![&[1u8, 2, 3][..], &[][..]]);
        let big = vec![7u8; HALF_GRID + 2];
        assert_eq!(compressed_parts("map_cells", &big)[1], &[7, 7]);
    }

    #[test]
    fn a_stream_that_does_not_fit_in_its_wram_place_is_refused() {
        assert_eq!(
            check_streams(1, "sprite_tiles", &vec![0; 0x6000 + 32]).unwrap_err().message(),
            "map 1: a stream of sprite_tiles is 24608 bytes and 24576 fit in WRAM: see the LZ2 \
             reservation in tools/runtime/far_ram.s"
        );
    }
}
