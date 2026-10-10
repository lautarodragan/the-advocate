//! LZ2, what the console decompresses when it loads a map: Nintendo's
//! LC_LZ2, compressed with `lz2`'s optimal parser, as a library.
//!
//! The decompressor on the console reads all of the format but two
//! commands, on purpose: no block used them, and a path no test runs is the
//! one that bites. The increasing fill (3) is left out of the parse, which
//! costs almost nothing; the one-byte word fill the parser never picks,
//! because a literal of one costs less. If either shows up anyway, the
//! conversion stops here and not on the console.

use crate::fail::{Bad, Result};
use std::thread;

/// The longest a stream can expand to: the repeat names its source with
/// sixteen bits. It is the format's.
pub const OUTPUT_MAX: usize = lz2::MAX_OUTPUT;

/// Each block compressed, in the same order, spread over the machine's
/// threads: there are hundreds per cartridge.
pub fn compress_many(blocks: &[&[u8]]) -> Result<Vec<Vec<u8>>> {
    for b in blocks {
        if b.len() > OUTPUT_MAX {
            return Err(Bad::answer(format!(
                "a block of {} bytes does not fit in an LZ2 stream: the limit is {OUTPUT_MAX}",
                b.len()
            )));
        }
    }
    let workers = thread::available_parallelism()
        .map_or(1, |n| n.get())
        .max(1);
    let mut out: Vec<Option<Result<Vec<u8>>>> = (0..blocks.len()).map(|_| None).collect();
    let chunk = blocks.len().div_ceil(workers).max(1);
    thread::scope(|scope| {
        for (inputs, outputs) in blocks.chunks(chunk).zip(out.chunks_mut(chunk)) {
            scope.spawn(move || {
                for (input, slot) in inputs.iter().zip(outputs.iter_mut()) {
                    *slot = Some(compress(input));
                }
            });
        }
    });
    out.into_iter()
        .map(|r| r.expect("every block was compressed"))
        .collect()
}

/// One block, as a stream the console reads.
pub fn compress(block: &[u8]) -> Result<Vec<u8>> {
    let stream = lz2::compress_with(block, lz2::Options { increasing: false })
        .map_err(|e| Bad::answer(format!("lz2: {e}")))?;
    if let Some(missing) = what_the_rom_does_not_read(&stream) {
        return Err(Bad::answer(format!(
            "lz2 emitted {missing}, which `lz2_decompress` does not read"
        )));
    }
    Ok(stream)
}

/// The commands of a stream, as (command, length). Reads only the headers.
pub fn walk(stream: &[u8]) -> Vec<(u8, usize)> {
    let mut out = Vec::new();
    let mut i = 0;
    while stream[i] != lz2::END {
        let header = stream[i];
        let (command, length) = if header >> 5 == 7 {
            let length = ((usize::from(header & 3) << 8) | usize::from(stream[i + 1])) + 1;
            i += 2;
            ((header >> 2) & 7, length)
        } else {
            i += 1;
            (header >> 5, usize::from(header & 31) + 1)
        };
        i += match command {
            0 => length,
            1 | 3 => 1,
            _ => 2,
        };
        out.push((command, length));
    }
    out
}

/// How many commands a stream has: what decompressing it costs depends on
/// this and on how many bytes come out.
pub fn commands(stream: &[u8]) -> usize {
    walk(stream).len()
}

/// Which of the two commands the console does not read the stream has, if
/// any.
pub fn what_the_rom_does_not_read(stream: &[u8]) -> Option<&'static str> {
    for (command, length) in walk(stream) {
        if command == 3 {
            return Some("an increasing fill");
        }
        if command == 2 && length == 1 {
            return Some("a one-byte word");
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_headers_are_walked_short_and_long() {
        let stream = [
            0x02, 1, 2, 3, // literal of 3
            0x23, 9, // byte fill of 4
            0x81, 0x00, 0x01, // repeat of 2
            0xE4, 0x20, 5, // long byte fill of 33
            0xFF,
        ];
        assert_eq!(walk(&stream), vec![(0, 3), (1, 4), (4, 2), (1, 33)]);
        assert_eq!(commands(&stream), 4);
        assert_eq!(what_the_rom_does_not_read(&stream), None);
    }

    #[test]
    fn the_two_commands_the_console_does_not_read_are_named() {
        assert_eq!(
            what_the_rom_does_not_read(&[0x62, 0xFE, 0xFF]),
            Some("an increasing fill")
        );
        assert_eq!(
            what_the_rom_does_not_read(&[0x40, 7, 8, 0xFF]),
            Some("a one-byte word")
        );
    }

    #[test]
    fn many_blocks_come_back_in_order_and_round_trip() {
        let blocks: Vec<Vec<u8>> = (0..37u8)
            .map(|k| {
                (0..(k as usize * 97))
                    .map(|i| (i * k as usize % 7) as u8)
                    .collect()
            })
            .collect();
        let refs: Vec<&[u8]> = blocks.iter().map(Vec::as_slice).collect();
        let streams = compress_many(&refs).unwrap();
        for (block, stream) in blocks.iter().zip(&streams) {
            assert_eq!(&lz2::decompress_prefix(stream).unwrap().0, block);
            assert!(what_the_rom_does_not_read(stream).is_none());
        }
    }

    #[test]
    fn a_block_longer_than_a_stream_is_refused() {
        let big = vec![0u8; OUTPUT_MAX + 1];
        let message = compress_many(&[&big]).unwrap_err().message().to_string();
        assert_eq!(
            message,
            "a block of 65537 bytes does not fit in an LZ2 stream: the limit is 65536"
        );
    }
}
