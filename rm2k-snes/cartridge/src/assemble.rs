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

use rm2k_project::{absolute, relative};

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

/// Builds `rom` from `source`, with the generated files in `include`.
///
/// `ca65` and `ld65` run standing in `root`, with paths relative to it,
/// because `ca65` writes each source into the debug file just as it opened
/// it. With absolute paths the machine's would stay in it, and a debugger on
/// another machine would not find the source in its clone: it looks for it
/// next to the debug file and climbing up folder by folder.
pub fn assemble(
    source: &Path,
    include: &Path,
    rom: &Path,
    table: Option<&Path>,
    root: &Path,
) -> Result<(), Failure> {
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
    run(
        Command::new(&ca65)
            .args(["-g", "--cpu", "65816", "-I"])
            .arg(&include_r)
            .arg(&source_r)
            .arg("-o")
            .arg(&obj)
            .current_dir(&root),
    )?;
    run(
        Command::new(&ld65)
            .arg("-C")
            .arg(include_r.join(MEMORY_MAP))
            .arg(&obj)
            .arg("-o")
            .arg(&rom_r)
            .arg("--dbgfile")
            .arg(&dbg)
            .current_dir(&root),
    )?;
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
    Ok(())
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
