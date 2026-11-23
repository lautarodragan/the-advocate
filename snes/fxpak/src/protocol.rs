//! The usb2snes wire format, as sd2snes **v1.11.0** speaks it.
//!
//! Every layout here is read from that tag's `src/usbinterface.c`, and the
//! comments cite its lines: `git show v1.11.0:src/usbinterface.c` in a
//! clone of sd2snes. Nothing is taken from memory or from other clients:
//! a command built from memory once left an FX Pak answering nothing until
//! it was powered off with the cable out.

/// Every command, response and data block is 512 bytes:
/// `#define USB_BLOCK_SIZE 512` in `usbinterface.h`, and `cmd_size` is 512
/// for every opcode but VGET/VPUT (`usbinterface.c` 236).
pub const BLOCK: usize = 512;

/// The opcodes, in the order of `FOREACH_SERVER_OPCODE` (107-126): the enum
/// numbers them from 0. Only those this tool sends are named; RM (6), MV
/// (7), POWER_CYCLE (10), STREAM (13) and TIME (14) are left out on
/// purpose, and VGET/VPUT (2, 3) take a 64-byte command this tool does not
/// build.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Opcode {
    Get = 0,
    Put = 1,
    Ls = 4,
    Mkdir = 5,
    Reset = 8,
    Boot = 9,
    Info = 11,
    MenuReset = 12,
    Response = 15,
}

/// The spaces, in the order of `FOREACH_SERVER_SPACE` (132-137). MSU (2),
/// CMD (3) and CONFIG (4) are not used.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Space {
    /// The SD card, through FatFs.
    File = 0,
    /// The FX Pak's memory as `sram_readblock`/`sram_writeblock` address it
    /// (783-784, 315-317): the ROM in PSRAM from `$000000`, the save RAM
    /// at `$E00000`, the WRAM copy at `$F50000`, the menu's mailboxes at
    /// `$FF0000` (`memory.h`).
    Snes = 1,
}

/// What follows the size at byte 256 of a command.
#[derive(Clone, Copy, Debug)]
pub enum Arg<'a> {
    None,
    /// An address in the space, U32 big-endian at 256-259 (480-483 for GET,
    /// 493-496 for PUT).
    Offset(u32),
    /// A file name, NUL-ended from 256: `fileName = cmd_buffer + 256` (447).
    /// FatFs is built with `_LFN_UNICODE 0` and code page 1252, so the bytes
    /// are the name's, not UTF-8; [`crate::sdpath`] only lets ASCII through.
    Name(&'a [u8]),
}

/// The longest name that fits: from byte 256 to the block's end, with its
/// NUL. `MAX_STRING_LENGTH` (54) is 255 too.
pub const MAX_NAME: usize = BLOCK - 256 - 1;

/// A command block: `"USBA"` at 0-3 (checked at 277), the opcode at 4, the
/// space at 5, the flags at 6 (453-455), the size U32 big-endian at 252-255
/// (457-460), and at 256 the offset or the name. The flags are always 0
/// here: NORESP (64) would skip the response this tool waits for, SETX/CLRX
/// patch the running game's code, and 64BDATA changes the data blocks to
/// 64 bytes (244).
pub fn command(op: Opcode, space: Space, size: u32, arg: Arg) -> [u8; BLOCK] {
    let mut b = [0u8; BLOCK];
    b[0..4].copy_from_slice(b"USBA");
    b[4] = op as u8;
    b[5] = space as u8;
    b[6] = 0;
    b[252..256].copy_from_slice(&size.to_be_bytes());
    match arg {
        Arg::None => {}
        Arg::Offset(o) => b[256..260].copy_from_slice(&o.to_be_bytes()),
        Arg::Name(n) => {
            assert!(n.len() <= MAX_NAME, "a name longer than {MAX_NAME} bytes");
            assert!(!n.contains(&0), "a name with a NUL");
            b[256..256 + n.len()].copy_from_slice(n);
        }
    }
    b
}

/// The answer to every command: `"USBA"`, opcode RESPONSE at 4, the error
/// at 5 and the size U32 big-endian at 252-255 (677-690).
#[derive(Clone, Debug)]
pub struct Response {
    /// Nonzero when the operation failed. For GET and PUT of a file it is
    /// FatFs's results OR-ed together (474, 477, 490), so the number says
    /// little beyond "failed"; for LS and MKDIR it is 0 or 1 (546, 552).
    pub error: u8,
    /// `total_size` (687-690): a file's size for GET of a file (475-476),
    /// 1 for LS (547), the command's own size otherwise (462).
    pub size: u32,
    pub raw: [u8; BLOCK],
}

#[derive(Debug, PartialEq, Eq)]
pub enum ParseError {
    Short(usize),
    NotUsba([u8; 4]),
    NotResponse(u8),
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            ParseError::Short(n) => write!(f, "a response of {n} bytes, not {BLOCK}"),
            ParseError::NotUsba(m) => {
                write!(f, "a response that does not start with USBA: {m:02x?}")
            }
            ParseError::NotResponse(op) => write!(f, "a block with opcode {op}, not RESPONSE (15)"),
        }
    }
}

pub fn parse_response(raw: &[u8]) -> Result<Response, ParseError> {
    if raw.len() != BLOCK {
        return Err(ParseError::Short(raw.len()));
    }
    if &raw[0..4] != b"USBA" {
        return Err(ParseError::NotUsba(raw[0..4].try_into().unwrap()));
    }
    if raw[4] != Opcode::Response as u8 {
        return Err(ParseError::NotResponse(raw[4]));
    }
    let mut r = [0u8; BLOCK];
    r.copy_from_slice(raw);
    Ok(Response {
        error: raw[5],
        size: u32::from_be_bytes(raw[252..256].try_into().unwrap()),
        raw: r,
    })
}

/// What INFO answers, inside its RESPONSE block (692-707).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Info {
    /// `current_features` at 6 (701).
    pub features: u8,
    /// The ROM running, `current_filename` from 16, at most 239 bytes
    /// (703-706); the menu's own when no game is.
    pub rom: String,
    /// `CONFIG_FWVER`, U32 big-endian at 256-259 (693-696).
    pub fw_version: u32,
    /// `CONFIG_VERSION`, from 260, at most 64 bytes (697).
    pub version: String,
    /// `DEVICE_NAME`, from 324, at most 64 bytes (698).
    pub device: String,
}

/// A NUL-ended string in `b[from..from+max]`; `strncpy` leaves it without a
/// NUL when it fills the field.
fn cstr(b: &[u8], from: usize, max: usize) -> String {
    let field = &b[from..from + max];
    let end = field.iter().position(|&c| c == 0).unwrap_or(max);
    latin1(&field[..end])
}

/// FatFs's names are code page 1252 bytes (`ffconf.h`: `_CODE_PAGE 1252`,
/// `_LFN_UNICODE 0`). Latin-1 is that page but for 0x80-0x9F, which is
/// close enough to show a name; this tool only sends ASCII.
pub fn latin1(b: &[u8]) -> String {
    b.iter().map(|&c| c as char).collect()
}

pub fn parse_info(r: &Response) -> Info {
    Info {
        features: r.raw[6],
        rom: cstr(&r.raw, 16, 255 - 16),
        fw_version: u32::from_be_bytes(r.raw[256..260].try_into().unwrap()),
        version: cstr(&r.raw, 260, 64),
        device: cstr(&r.raw, 324, 64),
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Kind {
    Dir,
    File,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Entry {
    pub kind: Kind,
    pub name: String,
}

/// LS's data blocks (828-877), one at a time. Each entry is a type byte
/// —0 a directory, 1 a file (865)— and its NUL-ended name (866-867); a 2
/// means the next entry did not fit and goes on in the next block (872),
/// and 0xFF that there are no more (836, 844). An entry that fills the
/// block to its last byte leaves no marker (864, 876): the next block
/// follows all the same, since the transfer only ends after the 0xFF (837,
/// 845, 959). What follows a 2 or a 0xFF in its block is stale buffer.
#[derive(Default)]
pub struct LsParser {
    pub entries: Vec<Entry>,
    done: bool,
}

#[derive(Debug, PartialEq, Eq)]
pub enum LsError {
    BadType(u8, usize),
    Unterminated(usize),
}

impl std::fmt::Display for LsError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            LsError::BadType(t, at) => write!(f, "LS: type byte {t:#04x} at {at}"),
            LsError::Unterminated(at) => write!(f, "LS: a name without its NUL at {at}"),
        }
    }
}

impl LsParser {
    /// Feeds one 512-byte block; true when the list is over.
    pub fn feed(&mut self, block: &[u8]) -> Result<bool, LsError> {
        assert_eq!(block.len(), BLOCK);
        let mut i = 0;
        while i < BLOCK {
            match block[i] {
                0xFF => {
                    self.done = true;
                    return Ok(true);
                }
                2 => return Ok(false),
                t @ (0 | 1) => {
                    let start = i + 1;
                    let len = block[start..]
                        .iter()
                        .position(|&c| c == 0)
                        .ok_or(LsError::Unterminated(start))?;
                    self.entries.push(Entry {
                        kind: if t == 0 { Kind::Dir } else { Kind::File },
                        name: latin1(&block[start..start + len]),
                    });
                    i = start + len + 1;
                }
                t => return Err(LsError::BadType(t, i)),
            }
        }
        Ok(false)
    }

    pub fn done(&self) -> bool {
        self.done
    }
}

/// How many data blocks carry `n` bytes: the last one is padded (949).
pub fn blocks_for(n: u64) -> u64 {
    n.div_ceil(BLOCK as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_get_of_snes_space_puts_size_and_offset_big_endian() {
        let b = command(Opcode::Get, Space::Snes, 0x10, Arg::Offset(0x018E93));
        assert_eq!(&b[0..7], b"USBA\x00\x01\x00");
        assert_eq!(&b[252..256], &[0, 0, 0, 0x10]);
        assert_eq!(&b[256..260], &[0x00, 0x01, 0x8E, 0x93]);
        assert!(b[7..252].iter().all(|&c| c == 0));
        assert!(b[260..].iter().all(|&c| c == 0));
    }

    #[test]
    fn a_put_of_a_file_carries_its_name_nul_ended() {
        let b = command(
            Opcode::Put,
            Space::File,
            1000,
            Arg::Name(b"/advocate/x.sfc"),
        );
        assert_eq!(b[4], 1);
        assert_eq!(b[5], 0);
        assert_eq!(&b[252..256], &1000u32.to_be_bytes());
        assert_eq!(&b[256..271], b"/advocate/x.sfc");
        assert_eq!(b[271], 0);
    }

    #[test]
    fn the_opcodes_are_the_enum_order_of_the_source() {
        // FOREACH_SERVER_OPCODE: GET PUT VGET VPUT LS MKDIR RM MV RESET
        // BOOT POWER_CYCLE INFO MENU_RESET STREAM TIME RESPONSE.
        let order = [
            "GET",
            "PUT",
            "VGET",
            "VPUT",
            "LS",
            "MKDIR",
            "RM",
            "MV",
            "RESET",
            "BOOT",
            "POWER_CYCLE",
            "INFO",
            "MENU_RESET",
            "STREAM",
            "TIME",
            "RESPONSE",
        ];
        let ours = [
            (Opcode::Get, "GET"),
            (Opcode::Put, "PUT"),
            (Opcode::Ls, "LS"),
            (Opcode::Mkdir, "MKDIR"),
            (Opcode::Reset, "RESET"),
            (Opcode::Boot, "BOOT"),
            (Opcode::Info, "INFO"),
            (Opcode::MenuReset, "MENU_RESET"),
            (Opcode::Response, "RESPONSE"),
        ];
        for (op, name) in ours {
            assert_eq!(
                order.iter().position(|&n| n == name),
                Some(op as usize),
                "{name}"
            );
        }
    }

    #[test]
    fn a_response_is_refused_unless_it_is_one() {
        assert_eq!(
            parse_response(&[0; 100]).unwrap_err(),
            ParseError::Short(100)
        );
        assert!(matches!(
            parse_response(&[0; BLOCK]),
            Err(ParseError::NotUsba(_))
        ));
        let mut b = command(Opcode::Info, Space::Snes, 0, Arg::None);
        assert_eq!(parse_response(&b).unwrap_err(), ParseError::NotResponse(11));
        b[4] = 15;
        b[5] = 1;
        b[252..256].copy_from_slice(&0x1234u32.to_be_bytes());
        let r = parse_response(&b).unwrap();
        assert_eq!((r.error, r.size), (1, 0x1234));
    }

    /// INFO's reply, laid out as the source writes it.
    #[test]
    fn info_reads_the_fields_where_the_source_writes_them() {
        let mut b = [0u8; BLOCK];
        b[0..4].copy_from_slice(b"USBA");
        b[4] = 15;
        b[6] = 0x42;
        b[16..16 + 22].copy_from_slice(b"/sd2snes/m3nu.bin\0junk");
        b[256..260].copy_from_slice(&0x0001_0b00u32.to_be_bytes());
        b[260..267].copy_from_slice(b"1.11.0\0");
        b[324..338].copy_from_slice(b"sd2snes Mk.III");
        let i = parse_info(&parse_response(&b).unwrap());
        assert_eq!(i.features, 0x42);
        assert_eq!(i.rom, "/sd2snes/m3nu.bin");
        assert_eq!(i.fw_version, 0x0001_0b00);
        assert_eq!(i.version, "1.11.0");
        assert_eq!(i.device, "sd2snes Mk.III");
    }

    #[test]
    fn ls_reads_entries_across_blocks() {
        let mut p = LsParser::default();
        let mut b = [0xAAu8; BLOCK];
        let mut i = 0;
        for (t, n) in [(0u8, &b"."[..]), (0, b".."), (1, b"rom.sfc"), (0, b"sub")] {
            b[i] = t;
            b[i + 1..i + 1 + n.len()].copy_from_slice(n);
            b[i + 1 + n.len()] = 0;
            i += n.len() + 2;
        }
        b[i] = 2; // continuation; the rest is stale
        assert_eq!(p.feed(&b), Ok(false));
        let mut c = [0x55u8; BLOCK];
        c[0] = 1;
        c[1..7].copy_from_slice(b"last\0\xFF");
        assert_eq!(p.feed(&c), Ok(true));
        assert!(p.done());
        let names: Vec<_> = p
            .entries
            .iter()
            .map(|e| (e.kind.clone(), e.name.as_str()))
            .collect();
        assert_eq!(
            names,
            [
                (Kind::Dir, "."),
                (Kind::Dir, ".."),
                (Kind::File, "rom.sfc"),
                (Kind::Dir, "sub"),
                (Kind::File, "last")
            ]
        );
    }

    #[test]
    fn ls_of_a_missing_directory_is_a_lone_ff() {
        let mut p = LsParser::default();
        let mut b = [0u8; BLOCK];
        b[0] = 0xFF;
        assert_eq!(p.feed(&b), Ok(true));
        assert!(p.entries.is_empty());
    }

    #[test]
    fn ls_with_a_block_filled_to_the_last_byte_goes_on() {
        let mut p = LsParser::default();
        let mut b = [0u8; BLOCK];
        b[0] = 1;
        for c in &mut b[1..BLOCK - 1] {
            *c = b'a';
        }
        b[BLOCK - 1] = 0;
        assert_eq!(p.feed(&b), Ok(false));
        assert_eq!(p.entries[0].name.len(), BLOCK - 2);
    }

    #[test]
    fn ls_refuses_a_type_it_does_not_know() {
        let mut p = LsParser::default();
        let mut b = [0u8; BLOCK];
        b[0] = 7;
        assert_eq!(p.feed(&b), Err(LsError::BadType(7, 0)));
    }
}
