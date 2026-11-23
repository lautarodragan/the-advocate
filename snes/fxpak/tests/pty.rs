//! The client against a fake FX Pak on a pseudo-terminal: a protocol peer
//! that answers as sd2snes v1.11.0's `src/usbinterface.c` does —the line
//! numbers cite it—, hangs where that firmware hangs, and logs every command
//! it gets. The client opens the pty's slave with the same code it opens the
//! real port with.

use std::collections::BTreeMap;
use std::ffi::CStr;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use fxpak::client::{Client, Error, Timeouts};
use fxpak::protocol::{Kind, BLOCK};
use fxpak::sdpath::SdPath;

const SPACE: usize = 0x100_0000;

#[derive(Default)]
struct Card {
    /// Directories, lowercase full paths without a trailing slash; "/" too.
    dirs: Vec<String>,
    files: BTreeMap<String, Vec<u8>>,
}

impl Card {
    fn key(p: &str) -> String {
        let p = p.trim_end_matches('/').to_ascii_lowercase();
        if p.is_empty() {
            "/".into()
        } else {
            p
        }
    }
    fn parent(p: &str) -> String {
        match p.rfind('/') {
            Some(0) | None => "/".into(),
            Some(i) => p[..i].into(),
        }
    }
    fn is_dir(&self, p: &str) -> bool {
        self.dirs.contains(&Card::key(p))
    }
    /// The entries of a directory: `.` and `..` first, as FatFs gives them
    /// for a subdirectory, then its children.
    fn list(&self, p: &str) -> Vec<(u8, String)> {
        let d = Card::key(p);
        let mut out = Vec::new();
        if d != "/" {
            out.push((0, ".".into()));
            out.push((0, "..".into()));
        }
        for x in &self.dirs {
            if x != "/" && Card::parent(x) == d {
                out.push((0, x.rsplit('/').next().unwrap().into()));
            }
        }
        for x in self.files.keys() {
            if Card::parent(x) == d {
                out.push((1, x.rsplit('/').next().unwrap().into()));
            }
        }
        out
    }
}

#[derive(Default)]
struct State {
    card: Card,
    mem: Vec<u8>,
    rom: String,
    /// Every command, as `OP space arg`.
    log: Vec<String>,
    /// Set where the real firmware would never answer again.
    wedged: Option<String>,
    /// Cut GET data after this many bytes, as a cable pulled mid-transfer.
    cut_after: Option<usize>,
}

struct Fake {
    state: Arc<Mutex<State>>,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
    slave: PathBuf,
}

impl Drop for Fake {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(t) = self.thread.take() {
            t.join().unwrap();
        }
    }
}

fn openpt() -> (OwnedFd, PathBuf) {
    // SAFETY: POSIX calls on the fd they return; ptsname's buffer is copied
    // at once.
    unsafe {
        let fd = libc::posix_openpt(libc::O_RDWR | libc::O_NOCTTY);
        assert!(fd >= 0);
        assert_eq!(libc::grantpt(fd), 0);
        assert_eq!(libc::unlockpt(fd), 0);
        let name = CStr::from_ptr(libc::ptsname(fd))
            .to_str()
            .unwrap()
            .to_string();
        (OwnedFd::from_raw_fd(fd), PathBuf::from(name))
    }
}

/// The master side, read with a short poll so the thread can stop, and so
/// a closed slave (the client dropped DTR) reads as a disconnect.
struct Wire {
    fd: OwnedFd,
}

enum Got {
    Data(Vec<u8>),
    Disconnected,
    Stop,
}

impl Wire {
    fn read_block(&self, stop: &AtomicBool) -> Got {
        let mut buf = vec![0u8; BLOCK];
        let mut got = 0;
        while got < BLOCK {
            if stop.load(Ordering::SeqCst) {
                return Got::Stop;
            }
            let mut p = libc::pollfd {
                fd: self.fd.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: one pollfd.
            let r = unsafe { libc::poll(&mut p, 1, 20) };
            if r <= 0 {
                continue;
            }
            if p.revents & libc::POLLHUP != 0 && p.revents & libc::POLLIN == 0 {
                std::thread::sleep(Duration::from_millis(5));
                return Got::Disconnected;
            }
            // SAFETY: into the free part of a live buffer.
            let n = unsafe {
                libc::read(
                    self.fd.as_raw_fd(),
                    buf[got..].as_mut_ptr().cast(),
                    BLOCK - got,
                )
            };
            if n <= 0 {
                std::thread::sleep(Duration::from_millis(5));
                return Got::Disconnected;
            }
            got += n as usize;
        }
        Got::Data(buf)
    }
    fn write(&self, mut data: &[u8]) {
        while !data.is_empty() {
            // SAFETY: from a live slice.
            let n = unsafe { libc::write(self.fd.as_raw_fd(), data.as_ptr().cast(), data.len()) };
            if n <= 0 {
                return;
            }
            data = &data[n as usize..];
        }
    }
}

fn response(error: u8, size: u32) -> [u8; BLOCK] {
    // 677-690
    let mut b = [0u8; BLOCK];
    b[0..4].copy_from_slice(b"USBA");
    b[4] = 15;
    b[5] = error;
    b[252..256].copy_from_slice(&size.to_be_bytes());
    b
}

fn padded(data: &[u8]) -> Vec<u8> {
    let mut v = data.to_vec();
    v.resize(data.len().div_ceil(BLOCK) * BLOCK, 0);
    v
}

fn name(cmd: &[u8]) -> String {
    let n = &cmd[256..];
    String::from_utf8_lossy(&n[..n.iter().position(|&c| c == 0).unwrap()]).into_owned()
}

/// LS's data (828-877): type byte and NUL-ended name per entry, a 2 when
/// the next does not fit, 0xFF at the end; the rest of a block is stale.
fn ls_blocks(entries: &[(u8, String)]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut block = vec![0xEEu8; BLOCK];
    let mut at = 0;
    for (t, n) in entries {
        if at + 1 + n.len() + 1 > BLOCK {
            block[at] = 2;
            out.extend_from_slice(&block);
            block = vec![0xEEu8; BLOCK];
            at = 0;
        }
        block[at] = *t;
        block[at + 1..at + 1 + n.len()].copy_from_slice(n.as_bytes());
        block[at + 1 + n.len()] = 0;
        at += n.len() + 2;
        if at == BLOCK {
            out.extend_from_slice(&block);
            block = vec![0xEEu8; BLOCK];
            at = 0;
        }
    }
    block[at] = 0xFF;
    out.extend_from_slice(&block);
    out
}

fn serve(wire: Wire, state: Arc<Mutex<State>>, stop: Arc<AtomicBool>) {
    loop {
        let cmd = match wire.read_block(&stop) {
            Got::Stop => return,
            Got::Disconnected => continue,
            Got::Data(b) => b,
        };
        let mut s = state.lock().unwrap();
        if s.wedged.is_some() {
            continue;
        }
        assert_eq!(&cmd[0..4], b"USBA", "a command without USBA");
        let (op, space) = (cmd[4], cmd[5]);
        let size = u32::from_be_bytes(cmd[252..256].try_into().unwrap());
        let offset = u32::from_be_bytes(cmd[256..260].try_into().unwrap()) as usize;
        let file = space == 0;
        s.log.push(format!(
            "{op} {space} {}",
            if file {
                name(&cmd)
            } else {
                format!("{offset:x}+{size:x}")
            }
        ));
        match (op, file) {
            (11, _) => {
                // 692-707
                let mut r = response(0, 0);
                let rom = s.rom.clone();
                r[16..16 + rom.len()].copy_from_slice(rom.as_bytes());
                r[256..260].copy_from_slice(&0x0001_0b00u32.to_be_bytes());
                r[260..266].copy_from_slice(b"1.11.0");
                r[324..338].copy_from_slice(b"sd2snes Mk.III");
                wire.write(&r);
            }
            (0, false) => {
                if size == 0 {
                    // 953: no block is sent, and the server sits in its data
                    // state until a disconnect.
                    wire.write(&response(0, 0));
                    drop(s);
                    wait_disconnect(&wire, &stop);
                    continue;
                }
                let data = s.mem[offset..offset + size as usize].to_vec();
                wire.write(&response(0, size));
                let d = padded(&data);
                let n = s.cut_after.unwrap_or(d.len()).min(d.len());
                wire.write(&d[..n]);
            }
            (0, true) => {
                let n = name(&cmd);
                let Some(data) = s.card.files.get(&Card::key(&n)).cloned() else {
                    // 474-477, 763-770: the read loop never ends.
                    s.wedged = Some(format!("GET of a missing file, {n}"));
                    continue;
                };
                wire.write(&response(0, data.len() as u32));
                if data.is_empty() {
                    drop(s);
                    wait_disconnect(&wire, &stop);
                    continue;
                }
                wire.write(&padded(&data));
            }
            (1, true) => {
                let n = name(&cmd);
                let ok = s.card.is_dir(&Card::parent(&Card::key(&n))) && !s.card.is_dir(&n);
                wire.write(&response(if ok { 0 } else { 1 }, size));
                // 278-281: data is expected whether or not the open worked.
                let mut data = Vec::new();
                drop(s);
                while data.len() < size as usize {
                    match wire.read_block(&stop) {
                        Got::Data(b) => data.extend_from_slice(&b),
                        Got::Disconnected => break,
                        Got::Stop => return,
                    }
                }
                let mut s = state.lock().unwrap();
                if !ok && !data.is_empty() {
                    // 297-307: f_write on an unopened file, forever.
                    s.wedged = Some(format!("PUT data for a file that did not open, {n}"));
                } else if ok && data.len() >= size as usize {
                    data.truncate(size as usize);
                    s.card.files.insert(Card::key(&n), data);
                }
            }
            (1, false) => {
                wire.write(&response(0, size));
                drop(s);
                let mut data = Vec::new();
                while data.len() < size as usize {
                    match wire.read_block(&stop) {
                        Got::Data(b) => data.extend_from_slice(&b),
                        Got::Disconnected => break,
                        Got::Stop => return,
                    }
                }
                let mut s = state.lock().unwrap();
                if data.len() >= size as usize {
                    s.mem[offset..offset + size as usize].copy_from_slice(&data[..size as usize]);
                }
            }
            (4, _) => {
                let n = name(&cmd);
                if s.card.is_dir(&n) {
                    wire.write(&response(0, 1));
                    wire.write(&ls_blocks(&s.card.list(&n)));
                } else {
                    // 546, 835-839
                    wire.write(&response(1, 1));
                    wire.write(&ls_blocks(&[]));
                }
            }
            (5, _) => {
                let n = Card::key(&name(&cmd));
                let ok = s.card.is_dir(&Card::parent(&n))
                    && !s.card.is_dir(&n)
                    && !s.card.files.contains_key(&n);
                if ok {
                    s.card.dirs.push(n);
                }
                wire.write(&response(if ok { 0 } else { 1 }, 0));
            }
            (9, _) => {
                let n = name(&cmd);
                if !s.card.files.contains_key(&Card::key(&n)) {
                    s.wedged = Some(format!("BOOT of a missing file, {n}"));
                    continue;
                }
                s.rom = n;
                wire.write(&response(0, 0));
            }
            (8, _) | (12, _) => wire.write(&response(0, 0)),
            _ => panic!("a command this fake does not know: {op}"),
        }
    }
}

fn wait_disconnect(wire: &Wire, stop: &AtomicBool) {
    // CDC_BulkOut drops what comes while the server is busy (cdcuser.c
    // 419): only a disconnect gets it back.
    loop {
        match wire.read_block(stop) {
            Got::Disconnected | Got::Stop => return,
            Got::Data(_) => {}
        }
    }
}

fn fake() -> Fake {
    let (master, slave) = openpt();
    let mut card = Card::default();
    for d in ["/", "/sd2snes", "/advocate", "/advocate/roms"] {
        card.dirs.push(d.into());
    }
    card.files
        .insert("/sd2snes/config.yml".into(), b"secret".to_vec());
    card.files.insert(
        "/advocate/roms/game.sfc".into(),
        (0..1300u32).map(|i| (i * 7) as u8).collect(),
    );
    card.files.insert("/advocate/empty".into(), Vec::new());
    for i in 0..40 {
        // Enough long names to need more than one LS block.
        card.files.insert(
            format!("/advocate/roms/a-long-name-to-fill-the-listing-{i:02}.sfc"),
            vec![i as u8],
        );
    }
    let mut mem = vec![0u8; SPACE];
    for (i, b) in mem.iter_mut().enumerate().take(0x20000) {
        *b = (i ^ (i >> 8)) as u8;
    }
    let state = Arc::new(Mutex::new(State {
        card,
        mem,
        rom: "/sd2snes/m3nu.bin".into(),
        ..Default::default()
    }));
    let stop = Arc::new(AtomicBool::new(false));
    let (s2, st2) = (state.clone(), stop.clone());
    let thread = std::thread::spawn(move || serve(Wire { fd: master }, s2, st2));
    Fake {
        state,
        stop,
        thread: Some(thread),
        slave,
    }
}

fn client(f: &Fake) -> Client {
    let mut c = Client::open(Path::new(&f.slave)).unwrap();
    c.timeouts = Timeouts {
        response: Duration::from_secs(2),
        boot: Duration::from_secs(2),
        sync: Duration::from_secs(2),
        data_idle: Duration::from_millis(500),
        write_idle: Duration::from_secs(2),
    };
    c
}

fn p(s: &str) -> SdPath {
    SdPath::parse(s).unwrap()
}

fn assert_alive(f: &Fake) {
    assert_eq!(f.state.lock().unwrap().wedged, None);
}

fn log(f: &Fake) -> Vec<String> {
    f.state.lock().unwrap().log.clone()
}

#[test]
fn info_reads_the_rom_firmware_and_device() {
    let f = fake();
    let i = client(&f).info().unwrap();
    assert_eq!(
        (i.rom.as_str(), i.version.as_str(), i.device.as_str()),
        ("/sd2snes/m3nu.bin", "1.11.0", "sd2snes Mk.III")
    );
}

#[test]
fn peek_reads_memory_across_blocks() {
    let f = fake();
    let mut c = client(&f);
    let got = c.get_snes(0x18E93, 1000).unwrap();
    assert_eq!(got, f.state.lock().unwrap().mem[0x18E93..0x18E93 + 1000]);
    // And the next command still lines up with its response.
    assert_eq!(
        c.get_snes(0, 16).unwrap(),
        f.state.lock().unwrap().mem[0..16]
    );
}

#[test]
fn peek_refuses_zero_bytes_and_the_end_of_the_space() {
    let f = fake();
    let mut c = client(&f);
    assert!(matches!(c.get_snes(0, 0), Err(Error::Refused(_))));
    assert!(matches!(c.get_snes(0xFFFFF0, 0x20), Err(Error::Refused(_))));
    assert!(log(&f).is_empty());
}

#[test]
fn ls_follows_continuations() {
    let f = fake();
    let mut c = client(&f);
    let e = c.ls(&p("/advocate/roms")).unwrap();
    assert_eq!(e.len(), 2 + 1 + 40);
    assert!(e
        .iter()
        .any(|e| e.name == "a-long-name-to-fill-the-listing-39.sfc" && e.kind == Kind::File));
    assert!(matches!(c.ls(&p("/nothing")), Err(Error::Failed(_))));
    assert_eq!(c.info().unwrap().version, "1.11.0");
}

#[test]
fn get_reads_a_file_and_never_asks_for_a_missing_one() {
    let f = fake();
    let mut c = client(&f);
    let want = f.state.lock().unwrap().card.files["/advocate/roms/game.sfc"].clone();
    assert_eq!(c.get_file(&p("/advocate/roms/game.sfc")).unwrap(), want);
    assert_eq!(
        c.get_file(&p("/ADVOCATE/roms/GAME.sfc")).unwrap(),
        want,
        "FAT ignores case"
    );
    assert!(matches!(
        c.get_file(&p("/advocate/roms/missing.sfc")),
        Err(Error::Refused(_))
    ));
    assert!(matches!(
        c.get_file(&p("/nowhere/x")),
        Err(Error::Refused(_))
    ));
    assert!(matches!(
        c.get_file(&p("/advocate/roms")),
        Err(Error::Refused(_))
    ));
    assert_alive(&f);
    assert!(!log(&f)
        .iter()
        .any(|l| l.starts_with("0 0 ") && l.contains("missing")));
}

#[test]
fn an_empty_file_comes_back_empty_and_the_port_is_freed() {
    let f = fake();
    let mut c = client(&f);
    assert_eq!(c.get_file(&p("/advocate/empty")).unwrap(), Vec::<u8>::new());
    assert_eq!(c.info().unwrap().version, "1.11.0");
}

#[test]
fn put_and_get_round_trip_under_advocate() {
    let f = fake();
    let mut c = client(&f);
    c.mkdir(&p("/advocate/test/deeper")).unwrap();
    c.mkdir(&p("/advocate/test/deeper")).unwrap();
    let data: Vec<u8> = (0..5000u32).map(|i| (i * 31 + 7) as u8).collect();
    c.put_file(&p("/advocate/test/deeper/x.bin"), &data)
        .unwrap();
    assert_eq!(c.get_file(&p("/advocate/test/deeper/x.bin")).unwrap(), data);
    assert_alive(&f);
}

#[test]
fn nothing_is_written_outside_advocate() {
    let f = fake();
    let mut c = client(&f);
    for bad in [
        "/sd2snes/config.yml",
        "/advocate/../sd2snes/config.yml",
        "/x.bin",
    ] {
        assert!(
            matches!(c.put_file(&p(bad), b"overwritten"), Err(Error::Refused(_))),
            "{bad}"
        );
        assert!(matches!(c.mkdir(&p(bad)), Err(Error::Refused(_))), "{bad}");
    }
    assert!(log(&f).is_empty(), "something was sent: {:?}", log(&f));
    assert_eq!(
        f.state.lock().unwrap().card.files["/sd2snes/config.yml"],
        b"secret"
    );
}

#[test]
fn put_into_a_missing_directory_is_refused_before_the_put() {
    let f = fake();
    let mut c = client(&f);
    assert!(matches!(
        c.put_file(&p("/advocate/nope/x.bin"), b"data"),
        Err(Error::Refused(_))
    ));
    assert!(matches!(
        c.put_file(&p("/advocate/roms/e"), b""),
        Err(Error::Refused(_))
    ));
    assert!(!log(&f).iter().any(|l| l.starts_with("1 ")));
    assert_alive(&f);
}

#[test]
fn a_transfer_cut_halfway_is_reported_and_drained() {
    let f = fake();
    let mut c = client(&f);
    f.state.lock().unwrap().cut_after = Some(700);
    let e = c.get_snes(0, 2048).unwrap_err();
    assert!(
        matches!(&e, Error::Wire(m) if m.contains("middle") && m.contains("cable")),
        "{e}"
    );
    f.state.lock().unwrap().cut_after = None;
    assert_eq!(c.get_snes(0, 4).unwrap(), f.state.lock().unwrap().mem[0..4]);
}

#[test]
fn boot_checks_the_file_first() {
    let f = fake();
    let mut c = client(&f);
    assert!(matches!(
        c.boot(&p("/advocate/roms/missing.sfc")),
        Err(Error::Refused(_))
    ));
    c.boot(&p("/advocate/roms/game.sfc")).unwrap();
    assert_eq!(c.info().unwrap().rom, "/advocate/roms/game.sfc");
    assert_alive(&f);
}

#[test]
fn poke_writes_only_the_roms_copy() {
    let f = fake();
    let mut c = client(&f);
    c.poke(0x8000, &[0xa9, 0x00, 0x8d]).unwrap();
    assert_eq!(
        f.state.lock().unwrap().mem[0x8000..0x8003],
        [0xa9, 0x00, 0x8d]
    );
    let before = log(&f).len();
    for addr in [0xBFFFFE, 0xE00000, 0xF50000, 0xFF1000] {
        assert!(
            matches!(c.poke(addr, &[1, 2, 3]), Err(Error::Refused(_))),
            "{addr:x}"
        );
    }
    assert_eq!(log(&f).len(), before);
}

#[test]
fn a_second_client_is_kept_out() {
    let f = fake();
    let _c = client(&f);
    assert!(
        matches!(Client::open(Path::new(&f.slave)), Err(Error::Wire(m)) if m.contains("another fxpak"))
    );
}
