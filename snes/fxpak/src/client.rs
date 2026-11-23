//! The operations, each one a command, its response and its data, with the
//! checks that keep the firmware out of the paths that hang it.
//!
//! sd2snes v1.11.0 (`src/usbinterface.c`) has error paths that never come
//! back, and they are why most operations look before they act:
//!
//! * **GET of a file that does not exist** sets the error but keeps the size
//!   of the last `f_stat` (474-477) and goes on to send data (654-656);
//!   `usbint_handler_dat` then reads an unopened file, gets 0 bytes and
//!   loops forever (763-770). The FX Pak answers nothing until the console
//!   is off with the cable out. So `get_file` lists the parent first.
//! * **PUT of a file that cannot be opened** answers the error but still
//!   waits for the data (278-281, 658-659), and each data block then loops
//!   forever writing to the unopened file (297-307). So `put_file` checks
//!   the parent directory first, and if the PUT is answered with an error
//!   anyway it sends no data and closes the port: a dropped DTR is a
//!   disconnect, which clears the wait (409-417).
//! * **A transfer of 0 bytes** sends no data block (953), so the server
//!   stays in its data state, which drops every new command (`cdcuser.c`
//!   419), until a disconnect. A zero-length GET is refused for memory; a
//!   file that turns out empty makes the client reopen the port.
//! * **BOOT of a missing file** loads nothing and takes the console out of
//!   reset all the same (`memory.c` 249-253, `usbinterface.c` 635-646).

use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::port::{Port, PortError};
use crate::protocol::{
    self, blocks_for, Arg, Entry, Info, Kind, LsParser, Opcode, Response, Space, BLOCK,
};
use crate::sdpath::SdPath;

/// How long each wait may last.
#[derive(Clone, Copy, Debug)]
pub struct Timeouts {
    /// For a response.
    pub response: Duration,
    /// For BOOT's response, which comes only after the ROM is in PSRAM
    /// (629-648 come before the response at 677): seconds, for 8 MB.
    pub boot: Duration,
    /// For the response to the INFO that follows a PUT, which waits for the
    /// card to take the last block.
    pub sync: Duration,
    /// The longest silence inside a data transfer.
    pub data_idle: Duration,
    /// The longest the port may refuse to take more bytes.
    pub write_idle: Duration,
}

impl Default for Timeouts {
    fn default() -> Self {
        Timeouts {
            response: Duration::from_secs(5),
            boot: Duration::from_secs(60),
            sync: Duration::from_secs(30),
            data_idle: Duration::from_secs(5),
            write_idle: Duration::from_secs(10),
        }
    }
}

/// The 24-bit space `sram_readblock` addresses (`memory.h`: up to the
/// menu's scratchpad at `$FFFF00`).
pub const SNES_SPACE_END: u64 = 0x100_0000;
/// Where `poke` may write: the ROM's copy in PSRAM, `$000000` to the
/// menu's own image at `$C00000` (`memory.h`: `SRAM_MENU_ADDR`). Above it
/// are the menu, its directory and database, the cheats, the save RAM
/// —which the FX Pak writes back to the card's `/sd2snes/saves/`—, the
/// skin, the SPC player, the savestate handler and the menu's mailboxes at
/// `$FF0000`, where a command can make the MCU load a ROM.
pub const POKE_END: u64 = 0xC0_0000;

#[derive(Debug)]
pub enum Error {
    /// Refused before anything was sent.
    Refused(String),
    /// The FX Pak answered with an error.
    Failed(String),
    /// The port or the wire: a timeout, a broken block.
    Wire(String),
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            Error::Refused(m) | Error::Failed(m) | Error::Wire(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

const STUCK: &str = "The FX Pak may still be waiting: closing the port usually lets it go back to idle. If `fxpak info` answers nothing after that, turn the console off, pull the USB cable, and plug it back with the console on (with the cable in, the FX Pak stays half powered and a console reset does not clear it).";

pub struct Client {
    path: PathBuf,
    port: Option<Port>,
    pub timeouts: Timeouts,
}

impl Client {
    /// Opens the port and drops whatever an earlier client left unread.
    pub fn open(path: &Path) -> Result<Client> {
        let port = Port::open(path).map_err(|e| Error::Wire(format!("{}: {e}", path.display())))?;
        let c = Client {
            path: path.to_path_buf(),
            port: Some(port),
            timeouts: Timeouts::default(),
        };
        let dropped = c
            .port()
            .drain(Duration::from_millis(100), Duration::from_secs(3))
            .map_err(wire)?;
        if dropped > 0 {
            eprintln!("fxpak: dropped {dropped} bytes an earlier client left unread");
        }
        Ok(c)
    }

    fn port(&self) -> &Port {
        self.port
            .as_ref()
            .expect("the port is open between operations")
    }

    /// Closes and opens the port again: the close drops DTR, which the
    /// firmware takes as a disconnect and leaves any wait (409-417).
    fn reopen(&mut self) -> Result<()> {
        self.port = None;
        std::thread::sleep(Duration::from_millis(200));
        self.port = Some(Port::open(&self.path).map_err(wire)?);
        Ok(())
    }

    fn transact(
        &mut self,
        op: Opcode,
        space: Space,
        size: u32,
        arg: Arg,
        timeout: Duration,
    ) -> Result<Response> {
        let cmd = protocol::command(op, space, size, arg);
        self.port()
            .write_all(&cmd, self.timeouts.write_idle)
            .map_err(wire)?;
        let mut raw = [0u8; BLOCK];
        match self.port().read_exact(&mut raw, timeout) {
            Ok(()) => {}
            Err(PortError::Timeout { got: 0, .. }) => {
                return Err(Error::Wire(format!(
                    "no response to {op:?} in {timeout:?}. {STUCK}"
                )));
            }
            Err(e) => return Err(self.mid_transfer(e, "the response")),
        }
        protocol::parse_response(&raw).map_err(|e| Error::Wire(format!("{op:?}: {e}")))
    }

    /// Reads `n` bytes of data, in whole blocks.
    fn read_data(&mut self, n: u64) -> Result<Vec<u8>> {
        let total = blocks_for(n) as usize * BLOCK;
        let mut out = vec![0u8; total];
        for chunk in out.chunks_mut(BLOCK) {
            if let Err(e) = self.port().read_exact(chunk, self.timeouts.data_idle) {
                return Err(self.mid_transfer(e, "the data"));
            }
        }
        out.truncate(n as usize);
        Ok(out)
    }

    /// A transfer cut halfway: drain what is still coming, and say so.
    fn mid_transfer(&mut self, e: PortError, what: &str) -> Error {
        let dropped = self
            .port()
            .drain(Duration::from_millis(300), Duration::from_secs(5))
            .unwrap_or(0);
        Error::Wire(format!("the FX Pak stopped in the middle of {what} ({e}; {dropped} more bytes drained after). {STUCK}"))
    }

    pub fn info(&mut self) -> Result<Info> {
        let r = self.transact(
            Opcode::Info,
            Space::Snes,
            0,
            Arg::None,
            self.timeouts.response,
        )?;
        Ok(protocol::parse_info(&r))
    }

    /// GET in the FX Pak's memory (480-483, 777-823).
    pub fn get_snes(&mut self, addr: u32, len: u32) -> Result<Vec<u8>> {
        if len == 0 {
            return Err(Error::Refused(
                "a read of 0 bytes: the firmware would send no data and wait for a disconnect"
                    .into(),
            ));
        }
        if addr as u64 + len as u64 > SNES_SPACE_END {
            return Err(Error::Refused(format!(
                "${addr:06X}+{len:#x} goes past the 24-bit space, ${SNES_SPACE_END:06X}"
            )));
        }
        let r = self.transact(
            Opcode::Get,
            Space::Snes,
            len,
            Arg::Offset(addr),
            self.timeouts.response,
        )?;
        let data = self.read_data(len as u64)?;
        if r.error != 0 {
            return Err(Error::Failed(format!("GET ${addr:06X}: error {}", r.error)));
        }
        Ok(data)
    }

    /// LS (542-550, 828-877). A directory that does not open is answered
    /// with an error and a lone 0xFF (546, 835-839): safe to ask.
    pub fn ls(&mut self, dir: &SdPath) -> Result<Vec<Entry>> {
        let r = self.transact(
            Opcode::Ls,
            Space::File,
            0,
            Arg::Name(dir.as_str().as_bytes()),
            self.timeouts.response,
        )?;
        let mut parser = LsParser::default();
        let mut block = [0u8; BLOCK];
        while !parser.done() {
            if let Err(e) = self.port().read_exact(&mut block, self.timeouts.data_idle) {
                return Err(self.mid_transfer(e, "a directory listing"));
            }
            if let Err(e) = parser.feed(&block) {
                let err = self.mid_transfer(
                    PortError::Io(std::io::Error::other(e.to_string())),
                    "a directory listing",
                );
                return Err(err);
            }
        }
        if r.error != 0 {
            return Err(Error::Failed(format!(
                "{dir}: not a directory, or it does not exist"
            )));
        }
        Ok(parser.entries)
    }

    /// What is at `path`, from a listing of its parent; `None` if nothing.
    pub fn stat(&mut self, path: &SdPath) -> Result<Option<Kind>> {
        let Some((parent, name)) = path.split() else {
            return Ok(Some(Kind::Dir));
        };
        let entries = match self.ls(&parent) {
            Ok(e) => e,
            Err(Error::Failed(_)) => return Ok(None),
            Err(e) => return Err(e),
        };
        // FAT compares without case, and LS gives 8.3 names in lowercase (860).
        Ok(entries
            .into_iter()
            .find(|e| e.name.eq_ignore_ascii_case(name))
            .map(|e| e.kind))
    }

    /// GET of a file (471-478, 763-776), after making sure it is one.
    pub fn get_file(&mut self, path: &SdPath) -> Result<Vec<u8>> {
        match self.stat(path)? {
            Some(Kind::File) => {}
            Some(Kind::Dir) => return Err(Error::Refused(format!("{path} is a directory"))),
            None => {
                return Err(Error::Refused(format!(
                    "{path} does not exist (a GET of a missing file hangs this firmware until a power cycle, so it is not sent)"
                )))
            }
        }
        let r = self.transact(
            Opcode::Get,
            Space::File,
            0,
            Arg::Name(path.as_str().as_bytes()),
            self.timeouts.response,
        )?;
        if r.error != 0 {
            return Err(Error::Failed(format!(
                "GET {path}: error {} after listing it as a file. {STUCK}",
                r.error
            )));
        }
        if r.size == 0 {
            self.reopen()?;
            return Ok(Vec::new());
        }
        self.read_data(r.size as u64)
    }

    /// PUT of a file under `/advocate/` (487-491, 296-308): the response,
    /// then the data in 512-byte blocks, the last one padded (301 writes
    /// only what is left of the size). There is no answer at the end.
    pub fn put_file(&mut self, path: &SdPath, data: &[u8]) -> Result<()> {
        path.writable().map_err(Error::Refused)?;
        if data.is_empty() {
            return Err(Error::Refused(
                "an empty file: the firmware would wait for a data block a size of 0 never sends"
                    .into(),
            ));
        }
        let size =
            u32::try_from(data.len()).map_err(|_| Error::Refused("a file over 4 GB".into()))?;
        let (parent, _) = path
            .split()
            .ok_or_else(|| Error::Refused("PUT of the root".into()))?;
        match self.stat(&parent)? {
            Some(Kind::Dir) => {}
            _ => {
                return Err(Error::Refused(format!(
                    "{parent} is not a directory on the card: `fxpak mkdir {parent}` first"
                )))
            }
        }
        if self.stat(path)? == Some(Kind::Dir) {
            return Err(Error::Refused(format!("{path} is a directory")));
        }
        let r = self.transact(
            Opcode::Put,
            Space::File,
            size,
            Arg::Name(path.as_str().as_bytes()),
            self.timeouts.response,
        )?;
        if r.error != 0 {
            self.reopen()?;
            return Err(Error::Failed(format!(
                "PUT {path}: the card would not open it (error {}); no data sent",
                r.error
            )));
        }
        self.write_blocks(data)?;
        self.sync()
    }

    /// PUT has no answer at its end. An INFO after it is one: the firmware
    /// takes it as a command only once the last data block is in (the flit
    /// collector reads data until the size is met, 228-266, 359-369), and
    /// the file closed (361).
    fn sync(&mut self) -> Result<()> {
        self.transact(Opcode::Info, Space::Snes, 0, Arg::None, self.timeouts.sync)
            .map(|_| ())
    }

    fn write_blocks(&mut self, data: &[u8]) -> Result<()> {
        for chunk in data.chunks(BLOCK) {
            let mut block = [0u8; BLOCK];
            block[..chunk.len()].copy_from_slice(chunk);
            self.port()
                .write_all(&block, self.timeouts.write_idle)
                .map_err(|e| {
                    Error::Wire(format!("the FX Pak stopped taking data ({e}). {STUCK}"))
                })?;
        }
        Ok(())
    }

    /// MKDIR (551-554) of `path` and whatever is missing above it, under
    /// `/advocate/`. One that exists is left alone.
    pub fn mkdir(&mut self, path: &SdPath) -> Result<()> {
        path.writable().map_err(Error::Refused)?;
        let mut at = SdPath::parse("/").unwrap();
        for part in path.components() {
            at = at.join(part).map_err(Error::Refused)?;
            match self.stat(&at)? {
                Some(Kind::Dir) => continue,
                Some(Kind::File) => return Err(Error::Refused(format!("{at} is a file"))),
                None => {}
            }
            let r = self.transact(
                Opcode::Mkdir,
                Space::File,
                0,
                Arg::Name(at.as_str().as_bytes()),
                self.timeouts.response,
            )?;
            if r.error != 0 {
                return Err(Error::Failed(format!("MKDIR {at}: refused by the card")));
            }
        }
        Ok(())
    }

    /// BOOT (629-648): loads the ROM and runs it, cutting whatever was
    /// running. Like booting from the menu, the firmware also records it as
    /// the last game (633), in its own settings on the card.
    pub fn boot(&mut self, path: &SdPath) -> Result<()> {
        if self.stat(path)? != Some(Kind::File) {
            return Err(Error::Refused(format!("{path} is not a file on the card")));
        }
        let r = self.transact(
            Opcode::Boot,
            Space::File,
            0,
            Arg::Name(path.as_str().as_bytes()),
            self.timeouts.boot,
        )?;
        if r.error != 0 {
            return Err(Error::Failed(format!("BOOT {path}: error {}", r.error)));
        }
        Ok(())
    }

    /// RESET (559-561) or MENU_RESET (563-565): no file and no data, only
    /// a command the main loop acts on like the reset button —short, or
    /// long back to the menu (`main.c` 428-436)—.
    pub fn reset(&mut self, to_menu: bool) -> Result<()> {
        let op = if to_menu {
            Opcode::MenuReset
        } else {
            Opcode::Reset
        };
        let r = self.transact(op, Space::Snes, 0, Arg::None, self.timeouts.response)?;
        if r.error != 0 {
            return Err(Error::Failed(format!("{op:?}: error {}", r.error)));
        }
        Ok(())
    }

    /// PUT in the FX Pak's memory (493-496, 313-317), only below
    /// [`POKE_END`].
    pub fn poke(&mut self, addr: u32, data: &[u8]) -> Result<()> {
        if data.is_empty() {
            return Err(Error::Refused("a write of 0 bytes".into()));
        }
        let end = addr as u64 + data.len() as u64;
        if end > POKE_END {
            return Err(Error::Refused(format!(
                "${addr:06X}+{:#x} reaches past ${POKE_END:06X}: above it are the menu, the save RAM the FX Pak writes back to the card, and the menu's mailboxes",
                data.len()
            )));
        }
        let r = self.transact(
            Opcode::Put,
            Space::Snes,
            data.len() as u32,
            Arg::Offset(addr),
            self.timeouts.response,
        )?;
        if r.error != 0 {
            self.reopen()?;
            return Err(Error::Failed(format!(
                "PUT ${addr:06X}: error {}; no data sent",
                r.error
            )));
        }
        self.write_blocks(data)?;
        self.sync()
    }
}

fn wire(e: PortError) -> Error {
    Error::Wire(e.to_string())
}
