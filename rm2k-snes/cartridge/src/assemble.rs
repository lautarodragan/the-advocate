//! Builds the ROM: the bank packing, `ca65` + `ld65`, the header checksum
//! and the symbols.
//!
//! `ca65` and `ld65` do the assembling and the linking. What lives here is
//! what they do not do:
//!
//! * **The bank packing** of the generated data, and the memory map it is
//!   linked against: see [`crate::banks`].
//! * **The header checksum.** Emulators do not look at it, but flash cart
//!   menus read the header to learn the mapping, and with garbage they may
//!   guess wrong.
//! * **The symbol table, in a format anything can read**: one line per
//!   symbol, `name value`, with the value in decimal. `ld65` gives it in its
//!   debug file, which carries much more.
//! * **The bytecodes' equates**, written next to the generated data from
//!   their declaration in `rm2k-snes-bytecode`: see [`write_bytecodes`].
//! * **Refusing to build with a generated file shadowed.** `ca65` looks up
//!   `.include`s first in the directory of the including file and only then
//!   in the `-I`s, so a stale copy next to the source would be read instead
//!   of the one in the include directory, without saying anything: the ROM
//!   would come out with another build's data.

use std::path::{Path, PathBuf};
use std::process::Command;

use rm2k_project::{absolute, cache, relative};

use crate::banks;

/// Where the checksum goes in the file: bank 0's `$FFDE`, and its complement
/// at `$FFDC`, in each of its two copies —the console reads the one at
/// `$40FFC0`, and flash cart menus score both—. See [`banks::MIRRORS`].
pub const CHECKSUM: usize = 0x00FFDE;
pub const COMPLEMENT: usize = 0x00FFDC;

/// What `ld65` links against, written next to the generated data.
pub const MEMORY_MAP: &str = "memory.cfg";

const MISSING: &str = "`{}` is missing, from the cc65 project (https://cc65.github.io).

It is not packaged everywhere; it is built once from a clone and stays on the
PATH:

    git clone --depth 1 https://github.com/cc65/cc65.git
    make -C cc65 -j8 bin
    # and put cc65/bin/ca65 and cc65/bin/ld65 on the PATH";

/// The first executable called `name` on the PATH.
pub fn which(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path)
        .map(|dir| dir.join(name))
        .find(|candidate| is_executable(candidate))
}

fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(path).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
}

/// The paths of `ca65` and `ld65` on the PATH.
pub fn binaries() -> Result<[PathBuf; 2], String> {
    let find = |name| which(name).ok_or_else(|| MISSING.replace("{}", name));
    Ok([find("ca65")?, find("ld65")?])
}

/// The `.include`s written in `text`, in order: the real ones, not one
/// quoted in a comment.
fn includes(text: &str) -> Vec<String> {
    let mut found = Vec::new();
    for line in text.lines() {
        let Some(rest) = line.trim_start().strip_prefix(".include") else {
            continue;
        };
        // At least one blank between the directive and the name.
        if !rest.starts_with(char::is_whitespace) {
            continue;
        }
        let Some(quoted) = rest.trim_start().strip_prefix('"') else {
            continue;
        };
        if let Some(end) = quoted.find('"').filter(|&end| end > 0) {
            found.push(quoted[..end].to_string());
        }
    }
    found
}

/// `main` and the `.s` files it includes, in the order `ca65` reads them.
///
/// It is the ROM's hand-written source: what has to be read to ask "does the
/// ROM declare such a thing?". The `.inc` files are left out because they
/// are generated. An `.include` is looked up next to the file that does it,
/// which is the first thing `ca65` tries.
pub fn sources(main: &Path) -> Result<Vec<PathBuf>, String> {
    let mut out = Vec::new();
    walk(main, &mut |path, _| {
        out.push(path.to_path_buf());
        Ok(())
    })?;
    Ok(out)
}

/// Calls `visit` with every `.s` file from `main` down, in `ca65`'s order,
/// and with the names it includes.
fn walk(
    path: &Path,
    visit: &mut dyn FnMut(&Path, &[String]) -> Result<(), String>,
) -> Result<(), String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let names = includes(&text);
    visit(path, &names)?;
    let directory = absolute(path);
    let directory = directory.parent().unwrap_or(Path::new("/"));
    for name in names {
        if name.ends_with(".s") {
            walk(&directory.join(name), visit)?;
        }
    }
    Ok(())
}

/// The generated files `main` includes, in the order the assembler reads
/// them: the `.include`s that are found in `include` and not next to the
/// file that includes them. Fails if one is in both places.
pub fn generated(main: &Path, include: &Path) -> Result<Vec<PathBuf>, String> {
    let mut found = Vec::new();
    walk(main, &mut |path, names| {
        let path = absolute(path);
        let here = path.parent().unwrap_or(Path::new("/"));
        for name in names {
            let theirs = include.join(name);
            if !theirs.is_file() {
                continue;
            }
            if here.join(name).exists() {
                return Err(format!(
                    "{} has {name} next to it, and `ca65` would read it before the one in \
                     {}: the ROM would come out with another build's data. It is \
                     generated; it can be deleted.",
                    path.display(),
                    include.display()
                ));
            }
            found.push(theirs);
        }
        Ok(())
    })?;
    Ok(found)
}

/// Writes the two bytecodes' equates into `include`, where the runtime's
/// `.include`s find them: the opcodes are declared in Rust, in
/// `rm2k-snes-bytecode`, and the 65816 side gets them from there at every
/// build instead of from a generated file kept up to date by hand.
pub fn write_bytecodes(include: &Path) -> Result<(), String> {
    for (name, bytecode, jump_table) in rm2k_snes_bytecode::asm::FILES {
        let path = include.join(name);
        std::fs::write(&path, rm2k_snes_bytecode::asm::asm(bytecode, jump_table))
            .map_err(|e| format!("{}: {e}", path.display()))?;
    }
    Ok(())
}

/// Copies banks 0 and 1 to the second 4 MB, where `ld65` left zeros: see
/// [`banks::MIRRORS`]. Before the checksum, which counts both copies.
pub fn mirror(rom: &mut [u8]) -> Result<(), String> {
    if rom.len() != banks::ROM_SIZE {
        return Err(format!(
            "the linked ROM is {} bytes and the memory map says {}",
            rom.len(),
            banks::ROM_SIZE
        ));
    }
    for (from, to, size) in banks::MIRRORS {
        rom.copy_within(from..from + size, to);
    }
    Ok(())
}

/// Writes the header checksum, in place, and returns it.
///
/// It is the sum of all the bytes modulo 65536, with its complement next to
/// it. The source leaves `$FFFF` and `$0000` in those four bytes on purpose:
/// since the complement is the inverted checksum, the four always add up to
/// 510, so the sum does not change when they are written and there is no
/// need to iterate. That holds for each copy of the header.
pub fn checksum(rom: &mut [u8]) -> Result<u16, String> {
    let sum = |rom: &[u8]| rom.iter().fold(0u16, |s, &b| s.wrapping_add(b as u16));
    let before = sum(rom);
    let (from, to, _) = banks::MIRRORS[0];
    for base in [0, to - from] {
        rom[base + CHECKSUM..base + CHECKSUM + 2].copy_from_slice(&before.to_le_bytes());
        rom[base + COMPLEMENT..base + COMPLEMENT + 2]
            .copy_from_slice(&(before ^ 0xFFFF).to_le_bytes());
    }
    let after = sum(rom);
    if after != before {
        return Err(format!(
            "the checksum did not settle: ${after:04X} against ${before:04X}, which means \
             the header did not carry $FFFF and $0000"
        ));
    }
    Ok(before)
}

/// `path` relative to `root` if it is inside it; otherwise, absolute.
fn under(path: &Path, root: &Path) -> PathBuf {
    let path = absolute(path);
    if path.starts_with(root) {
        relative(&path, root)
    } else {
        path
    }
}

/// How an assembly went wrong: a message, or `ca65`/`ld65` failing with
/// their own exit code, after saying why on their own stderr.
#[derive(Debug)]
pub enum Failure {
    Message(String),
    Tool(i32),
}

impl From<String> for Failure {
    fn from(message: String) -> Self {
        Failure::Message(message)
    }
}

/// The disk cache's category for `ca65`'s objects.
const OBJECTS: &str = "ca65";

/// What `ca65` is given besides the files.
const CA65_FLAGS: [&str; 3] = ["-g", "--cpu", "65816"];

/// The key of the object `ca65` makes of `source`: the binary, its flags,
/// and every file it reads —each `.s` from `source` down and each `.inc`
/// they include, from next to the file or from `include`, as `ca65` looks
/// them up—, by name and content. **Not where they are**: two worktrees
/// that assemble the same thing give the same key.
///
/// The object also carries, for the debug file, the path, size and date of
/// each source, and those do not go in: an object from the cache names the
/// files of the build that made it, and `ld65` passes that on to the
/// `.dbg`. [`assemble`] puts this build's back in the `.dbg`: see
/// [`retarget_dbg`].
pub fn object_key(ca65: &Path, source: &Path, include: &Path) -> Result<String, String> {
    let read = |path: &Path| std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()));
    let base = absolute(source);
    let base = base.parent().unwrap_or(Path::new("/")).to_path_buf();
    let mut parts: Vec<Vec<u8>> = vec![
        b"ca65 object 2".to_vec(),
        read(ca65)?,
        CA65_FLAGS.join(" ").into_bytes(),
    ];
    walk(source, &mut |path, names| {
        let path = absolute(path);
        let name = path.strip_prefix(&base).unwrap_or(&path);
        parts.push(name.as_os_str().as_encoded_bytes().to_vec());
        parts.push(read(&path)?);
        let here = path.parent().unwrap_or(Path::new("/"));
        for name in names.iter().filter(|n| !n.ends_with(".s")) {
            let found = [here.join(name), include.join(name)]
                .into_iter()
                .find(|p| p.is_file());
            parts.push(name.as_bytes().to_vec());
            parts.push(match found {
                Some(file) => read(&file)?,
                None => b"\0missing".to_vec(),
            });
        }
        Ok(())
    })?;
    Ok(cache::key(&parts))
}

/// Builds `rom` from `source`, with the generated files in `include`.
///
/// `ca65` and `ld65` run standing in `root`, with paths relative to it,
/// because `ca65` writes each source into the debug file just as it opened
/// it. With absolute paths the machine's would stay in it, and a debugger on
/// another machine would not find the source in its clone: it looks for it
/// next to the debug file and climbing up folder by folder.
///
/// With `cache_dir`, `ca65`'s object comes from the disk cache if the same
/// sources were assembled before —see [`object_key`]—: it is most of what
/// assembling a big game costs, and a single thread. `ld65` runs always.
/// Says whether the object came from the cache.
pub fn assemble(
    source: &Path,
    include: &Path,
    rom: &Path,
    table: Option<&Path>,
    root: &Path,
    cache_dir: Option<&Path>,
) -> Result<bool, Failure> {
    // The bytecodes' equates first, so that they are generated files like
    // the others: found in `include`, and refused if a stale copy shadows
    // them.
    write_bytecodes(include)?;
    // Before touching anything else: the shadowing check is part of this.
    let generated = generated(source, include)?;
    let [ca65, ld65] = binaries()?;
    // The `.msu` is the one next to the ROM, with its name: the converter
    // writes it there, and the emulator looks for it there.
    let msu = rom.with_extension("msu");
    let packing = banks::resolve(&generated, Some(&msu))?;
    println!(
        "bank packing: {} piece(s) in {} bank(s), {} of them slow",
        packing.pieces, packing.banks, packing.slow
    );
    if packing.spilled > 0 {
        println!(
            "  and {} piece(s) in the .msu instead: {} bytes",
            packing.spilled, packing.spilled_bytes
        );
    }
    let cfg = include.join(MEMORY_MAP);
    std::fs::write(&cfg, banks::cfg()).map_err(|e| format!("{}: {e}", cfg.display()))?;

    let root = absolute(root);
    let source_r = under(source, &root);
    let include_r = under(include, &root);
    let rom_r = under(rom, &root);
    let obj = with_suffix(&rom_r, ".o");
    let dbg = with_suffix(&rom_r, ".dbg");
    // After the packing, which rewrites the generated files in place: the
    // key is what `ca65` is about to read.
    let key = match cache_dir {
        Some(_) => Some(object_key(&ca65, source, include)?),
        None => None,
    };
    let object = root.join(&obj);
    // Copied in and out, never linked: `ca65` rewrites its object in place,
    // and with a link it would rewrite the cache's.
    let cached = match (cache_dir, &key) {
        (Some(dir), Some(key)) => cache::load(dir, OBJECTS, key),
        _ => None,
    };
    let names = Names {
        sources: source_r
            .parent()
            .unwrap_or(Path::new(""))
            .to_string_lossy()
            .into_owned(),
        include: include_r.to_string_lossy().into_owned(),
    };
    let cached = cached.as_deref().and_then(Names::unpack);
    let from_the_cache = cached.is_some();
    let mut named = None;
    if let Some((was, bytes)) = cached {
        std::fs::write(&object, bytes).map_err(|e| format!("{}: {e}", object.display()))?;
        named = Some(was);
    } else {
        run(Command::new(&ca65)
            .args(CA65_FLAGS)
            .arg("-I")
            .arg(&include_r)
            .arg(&source_r)
            .arg("-o")
            .arg(&obj)
            .current_dir(&root))?;
        if let (Some(dir), Some(key)) = (cache_dir, &key) {
            if let Ok(bytes) = std::fs::read(&object) {
                cache::store(dir, OBJECTS, key, &names.pack(&bytes));
            }
        }
    }
    run(Command::new(&ld65)
        .arg("-C")
        .arg(include_r.join(MEMORY_MAP))
        .arg(&obj)
        .arg("-o")
        .arg(&rom_r)
        .arg("--dbgfile")
        .arg(&dbg)
        .current_dir(&root))?;
    if let Some(was) = named {
        retarget_dbg(&root.join(&dbg), &root, &was, &names)?;
    }
    let mut data = std::fs::read(rom).map_err(|e| format!("{}: {e}", rom.display()))?;
    mirror(&mut data)?;
    checksum(&mut data)?;
    std::fs::write(rom, &data).map_err(|e| format!("{}: {e}", rom.display()))?;
    if let Some(table) = table {
        let symbols = crate::dbg::symbols_of(&root.join(&dbg))?;
        let mut text = String::new();
        for (name, value) in symbols {
            text.push_str(&format!("{name} {value}\n"));
        }
        std::fs::write(table, text).map_err(|e| format!("{}: {e}", table.display()))?;
    }
    println!(
        "{} -> {} ({} bytes)",
        source.display(),
        rom.display(),
        data.len()
    );
    Ok(from_the_cache)
}

/// The two directories `ca65` names a build's sources by, as it was given
/// them: the source's, which the runtime's `.s` files hang from, and the
/// include directory, which the generated files hang from.
#[derive(Debug, PartialEq)]
pub struct Names {
    pub sources: String,
    pub include: String,
}

impl Names {
    /// What the cache keeps: these names, then the object. In one value, so
    /// that two builds storing the same key at once cannot leave one's names
    /// with the other's object.
    fn pack(&self, object: &[u8]) -> Vec<u8> {
        let mut out = Vec::with_capacity(object.len() + 512);
        for name in [&self.sources, &self.include] {
            out.extend_from_slice(name.as_bytes());
            out.push(0);
        }
        out.extend_from_slice(object);
        out
    }

    fn unpack(bytes: &[u8]) -> Option<(Names, &[u8])> {
        let mut parts = bytes.splitn(3, |&b| b == 0);
        let sources = String::from_utf8(parts.next()?.to_vec()).ok()?;
        let include = String::from_utf8(parts.next()?.to_vec()).ok()?;
        Some((Names { sources, include }, parts.next()?))
    }

    /// `name` as this build calls it, if the one `was` describes named it.
    fn moved(&self, was: &Names, name: &str) -> String {
        for (old, new) in [(&was.include, &self.include), (&was.sources, &self.sources)] {
            if old.is_empty() || old == new {
                continue;
            }
            if let Some(rest) = name.strip_prefix(old.as_str()).filter(|r| r.starts_with('/')) {
                return format!("{new}{rest}");
            }
        }
        name.to_string()
    }
}

/// Gives the `.dbg` linked from a cached object the `file` records `ca65`
/// would have given in this build: the names under this build's directories,
/// and the size and date of this build's files, which `ca65` takes when it
/// opens each one. A debugger looks for each source by that name, next to
/// the `.dbg` and climbing up. `ld65` numbers the files in the order it read
/// them, not by name, so renaming them moves nothing else in the file.
pub fn retarget_dbg(dbg: &Path, root: &Path, was: &Names, now: &Names) -> Result<(), String> {
    let text = std::fs::read_to_string(dbg).map_err(|e| format!("{}: {e}", dbg.display()))?;
    let mut out = String::with_capacity(text.len());
    for line in text.split_inclusive('\n') {
        match retarget_line(line, root, was, now) {
            Some(new) => out.push_str(&new),
            None => out.push_str(line),
        }
    }
    std::fs::write(dbg, out).map_err(|e| format!("{}: {e}", dbg.display()))
}

/// A `file\tid=0,name="x",size=1,mtime=0x00000000,mod=0` record, as `ld65`
/// prints it (`PrintDbgFileInfo`). `None` leaves the line as it was.
fn retarget_line(line: &str, root: &Path, was: &Names, now: &Names) -> Option<String> {
    let rest = line.strip_prefix("file\t")?;
    let (head, rest) = rest.split_once("name=\"")?;
    let (name, rest) = rest.split_once("\",size=")?;
    let (_, tail) = rest.split_once(",mod=")?;
    let name = now.moved(was, name);
    let meta = std::fs::metadata(root.join(&name)).ok()?;
    let mtime = meta
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_secs();
    // `ca65` keeps the date in 32 bits.
    Some(format!(
        "file\t{head}name=\"{name}\",size={},mtime=0x{:08X},mod={tail}",
        meta.len(),
        mtime as u32
    ))
}

fn with_suffix(path: &Path, suffix: &str) -> PathBuf {
    let mut s = path.as_os_str().to_os_string();
    s.push(suffix);
    PathBuf::from(s)
}

fn run(command: &mut Command) -> Result<(), Failure> {
    let status = command
        .status()
        .map_err(|e| format!("{:?}: {e}", command.get_program()))?;
    if status.success() {
        Ok(())
    } else {
        Err(Failure::Tool(status.code().unwrap_or(1)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_real_includes_count() {
        let text = ".include \"a.s\"\n  .include   \"b.inc\" ; x\n\
                    ; .include \"quoted.s\"\n.includex \"no.s\"\n";
        assert_eq!(includes(text), ["a.s", "b.inc"]);
    }

    /// A linked ROM: zeros, with bank 0's header carrying the usual four
    /// bytes, and one more byte inside bank 0.
    fn linked() -> Vec<u8> {
        let mut rom = vec![0u8; banks::ROM_SIZE];
        rom[0x9234] = 0x56;
        rom[CHECKSUM] = 0xFF;
        rom[CHECKSUM + 1] = 0xFF;
        rom
    }

    #[test]
    fn checksum_and_complement_do_not_move_the_sum() {
        let mut rom = linked();
        mirror(&mut rom).unwrap();
        let sum = checksum(&mut rom).unwrap();
        assert_eq!(sum, 2 * (0x56 + 0xFF + 0xFF));
        for base in [0, 0x400000] {
            assert_eq!(rom[base + CHECKSUM..base + CHECKSUM + 2], sum.to_le_bytes());
            assert_eq!(
                rom[base + COMPLEMENT..base + COMPLEMENT + 2],
                (sum ^ 0xFFFF).to_le_bytes()
            );
        }
        let total = rom.iter().fold(0u16, |s, &b| s.wrapping_add(b as u16));
        assert_eq!(total, sum);
    }

    #[test]
    fn the_code_banks_go_twice() {
        let mut rom = linked();
        rom[0x18000] = 0x77;
        mirror(&mut rom).unwrap();
        assert_eq!(rom[0x409234], 0x56);
        assert_eq!(rom[0x418000], 0x77);
        assert_eq!(rom[0x40FFC0..0x410000], rom[0xFFC0..0x10000]);
    }

    #[test]
    fn a_header_without_the_usual_four_bytes_is_an_error() {
        let mut rom = vec![0u8; banks::ROM_SIZE];
        rom[5] = 1;
        assert!(checksum(&mut rom).unwrap_err().contains("did not settle"));
    }
}
