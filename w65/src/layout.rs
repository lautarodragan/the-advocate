//! The memory map: where each segment lands, and the header checksum.
//!
//! This is the one part of the assembler that is not about 65816 syntax. It
//! decides which file offset a segment starts at, which address the CPU will
//! see for a byte at that offset, and how much room each area has before it
//! overflows into the next one.

/// LoROM of 4 MB: banks of 32 KB, each mapped at `$8000-$FFFF` of the bank it
/// belongs to. The header and the vectors go at the end of the first one.
///
/// The comfortable thing about LoROM is that the file is linear even though
/// the addresses are not: the byte after `$007FFF` in the file is `$018000`.
/// So the pieces are placed by their offset inside the file, which is
/// contiguous, and the address is worked out afterwards. A large block of data
/// can cross a bank boundary without having to be split.
///
/// What does pay for that is the 65816 itself: a 24-bit pointer does not walk
/// from `$00FFFF` to `$018000` on its own, it has to be helped across. That is
/// the caller's code's problem, not this assembler's.
pub const BANK_SIZE: u32 = 0x8000;

/// How many banks the cartridge has. Four megabytes is a perfectly ordinary
/// cartridge size, and the reason to grow into it is usually not that the data
/// does not fit but that the *padding* does not: anything uploaded by DMA has
/// to land entirely inside one bank, and packing blocks of tens of kilobytes
/// without waste is impossible below a certain slack.
pub const ROM_BANKS: u32 = 128;

/// **The last two banks of the file are not used, and that is not waste for
/// convenience.** [`lorom_address`] gives every byte the address `bank:8000`,
/// and on the console banks `$7E` and `$7F` **are the work RAM**: data placed
/// there would be read as RAM and not as cartridge. They are reachable through
/// the `$FE`/`$FF` mirror, but then a 24-bit pointer crossing from `$7D:FFFF`
/// to the next bank would land in the RAM instead of jumping to the mirror,
/// and that would be a silent error in the worst possible place: a stream of
/// data read halfway through turning into garbage.
///
/// So the file is exactly 4 MB, which is what the header declares and what
/// emulators and flash carts expect, and the allocator stops 64 KB short.
pub const RESERVED_BANKS: u32 = 2;

pub struct Area {
    pub name: &'static str,
    pub start: u32,
    pub size: u32,
    pub segments: &'static [&'static str],
}

/// `TABLES` goes in bank 0, next to the code, and that is not a packing
/// detail: absolute indexed addressing —`lda table, x`— uses the data bank
/// register, which stays at 0. A table in another bank would be read from the
/// wrong place without raising any error. Anything the CPU walks with an index
/// has to live here.
pub const AREAS: &[Area] = &[
    Area { name: "ROM", start: 0x00000, size: 0x07FC0, segments: &["CODE", "TABLAS"] },
    Area { name: "HEAD", start: 0x07FC0, size: 0x00020, segments: &["HEADER"] },
    Area { name: "VECT", start: 0x07FE0, size: 0x00020, segments: &["VECTORS"] },
    Area {
        name: "DATA",
        start: 0x08000,
        size: BANK_SIZE * (ROM_BANKS - RESERVED_BANKS) - 0x08000,
        segments: &["RODATA"],
    },
];

/// The RAM does not appear in the file: it is placed by address, not by
/// offset. The stack starts at `$1FFF` and **grows downwards, towards the
/// BSS**: the two share the eight kilobytes of bank 0. So the BSS cannot reach
/// the end, and this is how much is left for the stack.
///
/// The number is measured, not chosen: with the BSS well out of the way, the
/// deepest call chain measured on this map goes down 24 bytes. 256 is ten
/// times that.
///
/// It exists because it was missing, and that cost an afternoon: the BSS grew
/// fourteen bytes, came to occupy exactly the 7936 available, and the stack
/// started writing on top of the last variable. The image did not fail to
/// assemble, and it did not fail at startup; it failed hundreds of frames into
/// a scene, with the whole of RAM trampled.
pub const STACK_RESERVE: u32 = 256;

pub const RAM_AREAS: &[Area] = &[
    Area { name: "ZP", start: 0x0000, size: 0x0100, segments: &["ZEROPAGE"] },
    Area { name: "RAM", start: 0x0100, size: 0x1F00 - STACK_RESERVE, segments: &["BSS"] },
];

/// Every segment name, in the order the areas lay them out. The index into
/// this list is how a segment is identified inside the assembler.
pub const SEGMENTS: &[&str] = &[
    "CODE", "TABLAS", "HEADER", "VECTORS", "RODATA", "ZEROPAGE", "BSS",
];

pub const ZP_SEGMENT: &str = "ZEROPAGE";

pub fn segment_index(name: &str) -> Option<usize> {
    SEGMENTS.iter().position(|s| *s == name)
}

/// The address the 65816 sees for a byte of the file.
pub fn lorom_address(offset: u32) -> i64 {
    (((offset / BANK_SIZE) as i64) << 16) | 0x8000 | ((offset % BANK_SIZE) as i64)
}

pub const CHECKSUM_OFFSET: usize = 0x07FDE; // $FFDE of bank 0
pub const COMPLEMENT_OFFSET: usize = 0x07FDC; // $FFDC

/// Fills in the header checksum, in place.
///
/// It is the sum of every byte of the image modulo 65536, with its complement
/// next to it. Emulators tend not to look at it, but flash cart menus read the
/// header to work out the mapping and the cartridge size, and with garbage
/// there they can guess wrong. Leaving it right is free.
///
/// The source is expected to hold `$FFFF` and `$0000` there on purpose: since
/// the complement is the checksum inverted, those four bytes always add up to
/// 510 —255+255+0+0 before, and (255-a)+(255-b)+a+b after—, so the sum does
/// not change when they are written and there is no need to iterate.
pub fn checksum(rom: &mut [u8]) -> Result<u16, String> {
    let before = (rom.iter().map(|b| *b as u64).sum::<u64>() & 0xFFFF) as u16;
    rom[CHECKSUM_OFFSET..CHECKSUM_OFFSET + 2].copy_from_slice(&before.to_le_bytes());
    rom[COMPLEMENT_OFFSET..COMPLEMENT_OFFSET + 2].copy_from_slice(&(before ^ 0xFFFF).to_le_bytes());

    let after = (rom.iter().map(|b| *b as u64).sum::<u64>() & 0xFFFF) as u16;
    if after != before {
        return Err(format!("the checksum did not settle: {after:04X} against {before:04X}"));
    }
    Ok(before)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_first_bank_is_addressed_from_8000() {
        assert_eq!(lorom_address(0), 0x008000);
        assert_eq!(lorom_address(0x7FFF), 0x00FFFF);
    }

    /// The point of LoROM: the file is contiguous even though the addresses
    /// jump a whole bank.
    #[test]
    fn the_byte_after_the_first_bank_is_the_start_of_the_second() {
        assert_eq!(lorom_address(0x8000), 0x018000);
    }

    #[test]
    fn the_reserved_banks_are_left_out_of_the_data_area() {
        let data = AREAS.last().unwrap();
        assert_eq!(data.start + data.size, BANK_SIZE * (ROM_BANKS - RESERVED_BANKS));
    }

    #[test]
    fn the_checksum_and_its_complement_do_not_disturb_the_sum() {
        let mut rom = vec![0u8; (BANK_SIZE * ROM_BANKS) as usize];
        rom[CHECKSUM_OFFSET] = 0xFF;
        rom[CHECKSUM_OFFSET + 1] = 0xFF;
        let sum = checksum(&mut rom).unwrap();
        let low = u16::from_le_bytes([rom[CHECKSUM_OFFSET], rom[CHECKSUM_OFFSET + 1]]);
        let complement = u16::from_le_bytes([rom[COMPLEMENT_OFFSET], rom[COMPLEMENT_OFFSET + 1]]);
        assert_eq!(low, sum);
        assert_eq!(complement, !sum);
    }
}
