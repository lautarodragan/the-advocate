//! The bank packing, and the memory map `ld65` links against.
//!
//! A DMA that crosses a bank does not read the next bank's ROM: the address
//! wraps inside the same bank. So everything the ROM uploads by DMA —a pose,
//! a tilemap, a block of samples— has to fit **whole** in a bank, and when it
//! does not fit in what is left of the current one, it has to go to another.
//!
//! `ld65` cannot pack variable-size blocks, so it is done here, before the
//! assembler runs: the generated data sends everything to one segment,
//! `RODATA`, with a directive in front of each piece that says what kind it
//! is, and this rewrites the files so that what reaches the assembler is one
//! segment per bank, `BANKnn`, which is what [`cfg`] declares.
//!
//! # The map: 8 MB, ExHiROM
//!
//! The cartridge inverts the address's top bit before it reaches the ROM.
//! The file's first 4 MB are banks `$C0-$FF`, whole, and their upper halves
//! show again at `$80-$BF:8000`; the second 4 MB are banks `$40-$7D`, and
//! their upper halves show again at `$00-$3F:8000`. [`file_offset`] is that,
//! and nothing else here computes it. What it means for the data:
//!
//! * **A bank starts at `$0000` and the next one follows it**: inside a run
//!   of whole banks, the byte after `$C2:FFFF` is `$C3:0000`. What jumps
//!   banks by hand only has to carry into the bank byte.
//! * **Only `$80-$FF` is fast.** `MEMSEL` speeds up the first 4 MB and
//!   nothing else: the second are read at 2.68 MHz always. That is why the
//!   packing fills the first 4 MB before touching the second.
//! * **Banks 0 and 1, the code, go twice**: at `$008000` and `$018000` of
//!   the file —what the console sees at `$80:8000` and `$81:8000`, the fast
//!   mirror the code runs from— and at `$408000` and `$418000` —what it sees
//!   at `$00` and `$01`, where the vectors land—. In LoROM those were one and
//!   the same ROM, and the runtime still assumes so: it is linked at
//!   `$00:8000` and jumps to `+ FAST`. The second copy is also what Mednafen's
//!   `snes_faust` reads at `$80-$BF`, where it does not invert the top bit:
//!   measured with a test ROM, and it is what its `cart.cpp` does.
//!   [`MIRRORS`] says which; the
//!   assembler writes the copy after linking.
//! * **The low halves of `$70-$7D` are not used.** On the cartridge they are
//!   ROM, but mesen-s, Mesen2 —unless its strict board mappings are on— and
//!   Mednafen's `snes` module put LoROM's SRAM there in ExHiROM too, and
//!   Mesen2 is the debugger. Nor are those of `$7E` and `$7F`, which are the
//!   WRAM on every console: what is left of those sixteen banks is their
//!   upper halves, through `$70-$7D:8000` and `$3E-$3F:8000`.
//!
//! **What this module assumes about the runtime** is that banks 0 and 1 are
//! its first two code banks, that the low half of `$C0` is the third
//! —[`FAR2`]—, and that the generated data goes in the rest: [`slots`].

use std::path::Path;

use crate::text::{code, first_word, is_constant, is_label, split_lines};

/// A whole ExHiROM bank: 64 KB, from `$0000`.
pub const BANK_SIZE: usize = 0x10000;

/// Half a bank: the data that shares a bank with something else gets this.
pub const HALF: usize = 0x8000;

/// The cartridge: 8 MB.
pub const ROM_SIZE: usize = 0x800000;

/// The two LoROM code banks, by file offset: where `ld65` puts them, where the
/// assembler copies them, and how long they are. See the module's docs.
pub const MIRRORS: [(usize, usize, usize); 2] =
    [(0x008000, 0x408000, HALF), (0x018000, 0x418000, HALF)];

/// The third code bank: `FAR2`, linked at `$C0:0000` and 32 KB long.
///
/// Banks 0 and 1 are full, and they cannot grow: each is the upper half of a
/// LoROM-like bank, and they go twice in the file. This one is a plain
/// ExHiROM half, in the fast 4 MB and with no copy: the code in it is only
/// ever entered with `jsl`, at this address, so it needs no mirror. It was the
/// low half of `$C0`, the last data slot of the fast 4 MB, which no
/// cartridge was using when it became code (2026-10-02).
pub const FAR2: Slot = Slot { bank: 0xC0, start: 0, size: HALF };

/// The file offset of a CPU address, as the cartridge decodes it, or `None`
/// if the cartridge does not answer there.
pub fn file_offset(address: usize) -> Option<usize> {
    let (bank, inside) = (address >> 16, address & 0xFFFF);
    match bank {
        0xC0..=0xFF => Some((bank - 0xC0) << 16 | inside),
        0x80..=0xBF if inside >= 0x8000 => Some((bank - 0x80) << 16 | inside),
        0x40..=0x7D => Some(0x400000 | (bank - 0x40) << 16 | inside),
        0x00..=0x3F if inside >= 0x8000 => Some(0x400000 | bank << 16 | inside),
        _ => None,
    }
}

/// A place the packing can put data: the bank as the CPU sees it, where in
/// the bank it starts, and how long it is.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Slot {
    pub bank: usize,
    pub start: usize,
    pub size: usize,
}

impl Slot {
    /// Its first byte, in 24 bits.
    pub fn address(&self) -> usize {
        self.bank << 16 | self.start
    }

    /// Whether `next` continues it: the byte after its last is `next`'s
    /// first. That is what a piece walked by hand needs to cross.
    pub fn continues_into(&self, next: &Slot) -> bool {
        self.address() + self.size == next.address()
    }

    /// Whether the CPU reads it at 3.58 MHz, with `MEMSEL` on.
    pub fn fast(&self) -> bool {
        self.bank >= 0x80
    }
}

/// Where the generated data can go, **in the order the packing fills it**:
/// the first 4 MB before the second, because they are fast, and in each the
/// whole banks before the halves.
pub fn slots() -> Vec<Slot> {
    let whole = |bank| Slot { bank, start: 0, size: BANK_SIZE };
    let low = |bank| Slot { bank, start: 0, size: HALF };
    let high = |bank| Slot { bank, start: 0x8000, size: HALF };
    let mut out: Vec<Slot> = (0xC2..=0xFF).map(whole).collect();
    // The low half of `$C1`, whose upper half is bank 1. That of `$C0` is
    // the third code bank: see [`FAR2`].
    out.push(low(0xC1));
    out.extend((0x42..=0x6F).map(whole));
    // The low halves of the copies of banks 0 and 1, the upper halves of the
    // banks whose low one is not used, and those of `$7E` and `$7F`, which
    // only show through `$3E` and `$3F`.
    out.extend([low(0x40), low(0x41)]);
    out.extend((0x70..=0x7D).map(high));
    out.extend([high(0x3E), high(0x3F)]);
    out
}

/// The stack starts at `$1FFF` and grows downwards, towards the BSS: the two
/// share the low 8 KB of the WRAM. This is what the stack is given, and the
/// lowest byte it gets is `$2000 - STACK`.
///
/// It is a cap and not a measurement: a runtime whose deepest call chain
/// needs more eats into the BSS, and nothing at link time can tell. Whoever
/// lowers it has to be measuring how deep the stack really goes.
pub const STACK: usize = 128;

/// The far RAM the linker hands out: the `FARBSS` segment, where the runtime
/// declares a variable of bank `$7E` with a `.res` in the file of the
/// subsystem that owns it, instead of writing its address by hand. Two
/// variables that land here cannot overlap, and when they no longer fit the
/// link fails, the same as with the `BSS`.
///
/// The rest of `$7E2000`–`$7E7FFF` is still a map of addresses written by
/// hand —`far_ram.s` and its neighbours, in the runtime—, and this is a
/// stretch of it nobody used: the end of the battle scene's reservation,
/// after `SCN_DP_SAVE`, which the runtime asserts ends before it. It grows by
/// taking over another stretch of that map and moving whatever lived there
/// into the segment: on 2026-10-12 it took a medicine's, `$7E6800` to
/// `$7E68FF` —its twenty-one bytes went into the segment—, when the battle's
/// conditions did not fit in what was left. `$7E6900` is the map's flash.
///
/// The address carries the bank, so a label in the segment is a 24-bit one:
/// read plainly it is a long access, which works whatever the data bank;
/// code that runs with the data bank at `$7E` takes its `.loword`.
pub const FAR_POOL_START: usize = 0x7E66C0;
pub const FAR_POOL_SIZE: usize = 0x0240;

/// The segment the generated data sends everything to.
pub const SEGMENT: &str = "RODATA";

/// The name of the segment pinned at the start of the CPU bank `bank`. No
/// bank has two slots, so the bank alone names it.
pub fn segment_of(bank: usize) -> String {
    format!("BANK{bank:02X}")
}

/// How many bytes each operand of the byte-emitting directives takes.
fn width(directive: &str) -> Option<usize> {
    match directive {
        ".byte" => Some(1),
        ".word" | ".addr" => Some(2),
        ".dword" => Some(4),
        _ => None,
    }
}

/// How many operands a comma-separated list has. Commas inside a string do
/// not separate: the generated data carries no strings today, but the rule
/// is the assembler's and it is cheaper to respect it than to find out the
/// day it does.
fn operand_count(rest: &str) -> usize {
    let rest = code(rest);
    if rest.is_empty() {
        return 0;
    }
    let mut count = 1;
    let mut quoted = false;
    for c in rest.chars() {
        if c == '"' {
            quoted = !quoted;
        } else if c == ',' && !quoted {
            count += 1;
        }
    }
    count
}

/// How many bytes a line takes.
pub fn size(line: &str) -> Result<usize, String> {
    let (first, rest) = first_word(line.trim());
    if first.is_empty() {
        return Ok(0);
    }
    if first == ".res" {
        // The ones this very module leaves, in case someone runs it twice.
        let n = code(rest.unwrap_or(""));
        return n
            .parse()
            .map_err(|_| format!("a `.res` whose size is not a number: {:?}", line.trim()));
    }
    Ok(match width(first) {
        Some(w) => w * operand_count(rest.unwrap_or("")),
        None => 0,
    })
}

/// Splits a data line into the first `fitting` bytes and the rest: (the
/// first part if it has anything, the second, how many bytes the second
/// takes). It can only be done between operands: a word split across two
/// banks is not a word.
fn split(line: &str, fitting: usize) -> Result<(Option<String>, String, usize), String> {
    let (code_part, comment) = match line.find(';') {
        Some(i) => (&line[..i], &line[i + 1..]),
        None => (line, ""),
    };
    let (directive, rest) = first_word(code_part.trim());
    let w = width(directive)
        .ok_or_else(|| format!("cannot split a line that is not data: {:?}", line.trim()))?;
    if fitting % w != 0 {
        return Err(format!(
            "the end of the bank falls in the middle of a {w}-byte operand: {:?}",
            line.trim()
        ));
    }
    let operands: Vec<&str> = rest.unwrap_or("").split(',').map(str::trim).collect();
    let count = fitting / w;
    let comment = comment.trim();
    let tail = if comment.is_empty() {
        String::new()
    } else {
        format!("  ; {comment}")
    };
    let first = (count > 0).then(|| {
        format!("    {directive} {}{tail}", operands[..count.min(operands.len())].join(", "))
    });
    let second = format!(
        "    {directive} {}",
        operands[count.min(operands.len())..].join(", ")
    );
    Ok((first, second, operands.len().saturating_sub(count) * w))
}

/// What the packing moves as one piece: a `.block`, a `.crossbank` or what
/// starts with neither, with all its lines up to the next one.
struct Piece {
    /// Its place in the text, which breaks ties so that the packing always
    /// comes out the same.
    order: usize,
    crosses: bool,
    /// What the `.block` declares.
    asks: usize,
    lines: Vec<String>,
    size: usize,
    align: usize,
    /// Whether its emitter marked it with `.msu`: see [`pack_with_msu`].
    msu: bool,
}

impl Piece {
    fn new(order: usize) -> Piece {
        Piece {
            order,
            crosses: false,
            asks: 0,
            lines: Vec::new(),
            size: 0,
            align: 1,
            msu: false,
        }
    }

    /// What it takes for the purpose of fitting: what the `.block` declares
    /// if it is more than what was emitted.
    fn fit_size(&self) -> usize {
        self.asks.max(self.size)
    }
}

/// A label the packing could split: its name, how long it is, how much of
/// that a `.block` covers, and whether it carries `.crossbank`.
struct Label {
    name: String,
    length: usize,
    covered: usize,
    crosses: bool,
}

/// How many pieces were packed, into how many banks, and how many of those
/// are in the slow 4 MB.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Packing {
    pub pieces: usize,
    pub banks: usize,
    pub slow: usize,
    /// How many pieces went to the `.msu` instead, and how many bytes they
    /// take there: see [`pack_with_msu`].
    pub spilled: usize,
    pub spilled_bytes: usize,
}

/// Splits into banks what `paths` send to `RODATA`, and rewrites them.
///
/// **It is first-fit decreasing**: each piece goes to the first bank where
/// it fits, from the largest to the smallest. The pieces are declared by
/// whoever wrote the files, and there are three kinds.
///
/// * **A `.block N` of up to one bank** fits whole in one: almost all of
///   them are uploaded by DMA, and a DMA that crosses a bank goes back to
///   the bank's start. One of up to half a bank may go in a half. It carries everything that follows up to the next directive —the tables
///   the `.block` measures together, and the one-byte labels after them—.
/// * **One of more than a bank** starts a whole bank and goes on into the
///   following ones, split between operands: it is walked by code that jumps
///   banks by hand. What is left over in its last bank is used by the
///   others.
/// * **A `.crossbank`** can be split anywhere **between two banks that
///   continue each other** ([`Slot::continues_into`]): the code that walks it
///   carries from `$FFFF` into the next bank's `$0000`, not to any bank.
///   First it is tried whole in a gap; the ones that do not fit go at the
///   end, one after the other, as a chain that starts in whatever is left of
///   the last whole bank and continues in new ones. A piece of the chain
///   that would have to cross into a bank that does not continue its own
///   —from `$FF` to `$42`— starts in a new bank instead.
///
/// The banks are taken in the order of [`slots`]: a new one is the first
/// that is free and where the piece fits.
///
/// **To move the pieces they have to be taken out of their place**, because
/// in `ca65` a segment is filled in the order of the text: what is left of
/// `RODATA` in each file is deleted, and all the banks are written at the
/// end of the last of `paths`, in order. The constants (`X = …`) stay where
/// they were. So nothing that moves may depend on its place —a subtraction
/// between labels of two pieces, a `*`—: two things that must stay together
/// go in a single `.block`.
///
/// `paths` come in the order the assembler reads them. What a file sends to
/// another segment does not count.
///
/// **Every label of more than one byte has to be covered by a `.block`**, or
/// carry `.crossbank` in front if it is walked by code that jumps banks by
/// hand. What is read with `lda f:table, x` or with `[ptr], y` does not jump:
/// split, the second half is read from the next bank's `$0000`, which is
/// not where the packing put it unless the two banks continue each other.
/// The rule is enforced on every build, and not on the day
/// the cut lands on one.
///
/// Running it twice changes nothing: the second time there is no `RODATA`
/// left, and the banks the first one wrote stay as they are.
///
/// `msu` is the cartridge's `.msu`, where what does not fit goes when the
/// files allow it: see [`pack_with_msu`].
pub fn resolve<P: AsRef<Path>>(paths: &[P], msu: Option<&Path>) -> Result<Packing, String> {
    let mut texts = Vec::new();
    for path in paths {
        let path = path.as_ref();
        texts.push(
            std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?,
        );
    }
    let names: Vec<String> = paths
        .iter()
        .map(|p| p.as_ref().display().to_string())
        .collect();
    let refs: Vec<&str> = texts.iter().map(String::as_str).collect();
    let start = match msu {
        Some(path) if path.is_file() => {
            let blob = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
            Some(crate::msu::region_start(&blob).map_err(|e| format!("{}: {e}", path.display()))?)
        }
        _ => None,
    };
    let (kept, packing, spill) = pack_with_msu(&names, &refs, &slots(), start)?;
    for (path, own) in paths.iter().zip(kept) {
        let path = path.as_ref();
        std::fs::write(path, own).map_err(|e| format!("{}: {e}", path.display()))?;
    }
    if let (Some(spill), Some(path), Some(start)) = (spill, msu, start) {
        crate::msu::write(path, start, &spill.region)?;
    }
    Ok(packing)
}

/// The packing over texts already read, into `slots` —[`slots`], except in
/// the tests—: what each file becomes, and the count. `names` are only for
/// the messages. Nothing goes to the `.msu`.
pub fn pack_texts(
    names: &[String],
    texts: &[&str],
    slots: &[Slot],
) -> Result<(Vec<String>, Packing), String> {
    let (kept, packing, _) = pack_with_msu(names, texts, slots, None)?;
    Ok((kept, packing))
}

/// What the packing sent to the `.msu`: the region, from its first byte.
/// See [`crate::msu`].
pub struct Spill {
    pub region: Vec<u8>,
}

/// The constants of the files that say what may go to the `.msu`. The
/// converter emits the first two, and the runtime reads them too.
///
/// * `MSU_REQUIRED = 1`: the cartridge needs the MSU-1, so what does not
///   fit in the ROM may go to the `.msu`. Without it nothing goes, and a
///   cartridge that does not fit is an error, as always.
/// * `MSU_SPILL_EVERYTHING = 1`: every piece that may go, goes, even if it
///   fitted. It is for the tests: so that the path the ROM reads them by
///   runs in a game that fits.
///
/// And `MSU_SPILL_AT`, which this writes: if it is already there, the files
/// were packed before and nothing is decided again.
const REQUIRED: &str = "MSU_REQUIRED";
const EVERYTHING: &str = "MSU_SPILL_EVERYTHING";
const SPILL_AT: &str = "MSU_SPILL_AT";

/// `(name, value)` if `directive` is a constant.
fn constant(directive: &str) -> Option<(&str, &str)> {
    if !is_constant(directive) {
        return None;
    }
    let (name, value) = directive.split_once('=')?;
    Some((name.trim(), value.trim()))
}

/// [`pack_texts`], and **what does not fit, to the `.msu`**, if the files
/// allow it; `msu_start` is where the region starts in the `.msu`
/// ([`crate::msu::region_start`]).
///
/// A piece may go if its emitter put `.msu` in front of its `.block`: it is
/// saying that the ROM only ever reads it through something that knows how
/// to read from the `.msu` —today `lz2_decompress`, in the runtime's
/// `decompress.s`—. It has to be one label at its start followed by
/// literal `.byte`s, which is what the packing can turn into bytes without
/// the assembler. Where the files do not say `MSU_REQUIRED`, the mark is
/// ignored and the piece is packed like any other.
///
/// **Which ones go**: the fewest that make the rest fit, taking the largest
/// first. The candidates are sorted from the largest to the smallest, and
/// the count is the smallest for which the packing succeeds, found by
/// halving: so the ROM keeps as much as fits, and what is read from the
/// `.msu` —a seek each, which costs Mednafen one or two frames: see
/// `msu_data_seek`— is as few pieces as it can be. With
/// `MSU_SPILL_EVERYTHING`, all of them.
///
/// Each one that goes leaves its label as a constant: bank
/// [`crate::msu::SPILL_BANK`] and its unit in the region, which is what the
/// ROM seeks. And the last file gets `MSU_SPILL_BANK`, `MSU_SPILL_AT` —the
/// region's start, in units— and `MSU_SPILLED`, and one more piece for the
/// ROM, `msu_spill_signature`: the region's, which the runtime compares
/// before reading from it. All of them even if nothing went: the cartridge
/// needs the MSU-1 all the same, and the region is there, empty.
pub fn pack_with_msu(
    names: &[String],
    texts: &[&str],
    slots: &[Slot],
    msu_start: Option<usize>,
) -> Result<(Vec<String>, Packing, Option<Spill>), String> {
    let mut pieces: Vec<Piece> = Vec::new();
    let mut kept: Vec<Vec<String>> = Vec::new();
    let mut labels: Vec<Label> = Vec::new();
    let mut covers = 0usize;
    let mut crosses = false;
    let (mut required, mut everything, mut packed_before) = (false, false, false);
    for (name, text) in names.iter().zip(texts) {
        let mut own: Vec<String> = Vec::new();
        let mut current: Option<String> = None;
        // Indices into `pieces` and `labels`.
        let mut piece: Option<usize> = None;
        let mut current_label: Option<usize> = None;
        // A `.msu` waiting for its `.block`.
        let mut msu_next = false;
        for line in split_lines(text) {
            let directive = code(line);
            match constant(directive) {
                Some((REQUIRED, value)) => required = value == "1",
                Some((EVERYTHING, value)) => everything = value == "1",
                Some((SPILL_AT, _)) => packed_before = true,
                _ => {}
            }
            if msu_next && !directive.is_empty() && !directive.starts_with(".block ") {
                return Err(format!(
                    "{name}: a `.msu` that is not right before a `.block`: {:?}",
                    line.trim()
                ));
            }
            if directive == ".msu" && current.as_deref() == Some(SEGMENT) {
                msu_next = true;
                continue;
            }
            if directive.starts_with(".segment") {
                let (_, rest) = first_word(directive);
                let segment = rest.unwrap_or("").trim().trim_matches('"').to_string();
                piece = None;
                current_label = None;
                if segment != SEGMENT {
                    own.push(line.to_string());
                }
                current = Some(segment);
                continue;
            }
            if current.as_deref() != Some(SEGMENT) || is_constant(directive) {
                own.push(line.to_string());
                continue;
            }
            // An `.align` right after a `.block` or a `.crossbank` belongs to
            // the same piece: the alignment is of what follows.
            let just_opened =
                piece.is_some_and(|p| pieces[p].align > 1 && pieces[p].lines.len() == 1);
            if directive.starts_with(".block ") {
                covers = number(directive, line)?;
                if !just_opened {
                    pieces.push(Piece::new(pieces.len()));
                    piece = Some(pieces.len() - 1);
                }
                pieces[piece.unwrap()].asks = covers;
                pieces[piece.unwrap()].msu = std::mem::take(&mut msu_next);
                continue;
            }
            if directive == ".crossbank" {
                crosses = true;
                if !just_opened {
                    pieces.push(Piece::new(pieces.len()));
                    piece = Some(pieces.len() - 1);
                }
                pieces[piece.unwrap()].crosses = true;
                continue;
            }
            if directive.starts_with(".align ") {
                // This one stays: aligning is not packing banks, and `ca65`
                // knows how to do it. Here it only has to be counted, and
                // since the segment is the bank, the padding depends on what
                // comes before it in the bank.
                if piece.is_none_or(|p| !pieces[p].lines.is_empty()) {
                    pieces.push(Piece::new(pieces.len()));
                    piece = Some(pieces.len() - 1);
                }
                let p = &mut pieces[piece.unwrap()];
                p.align = number(directive, line)?;
                p.lines.push(line.to_string());
                continue;
            }
            if piece.is_none() {
                if directive.is_empty() {
                    own.push(line.to_string());
                    continue;
                }
                pieces.push(Piece::new(pieces.len()));
                piece = Some(pieces.len() - 1);
            }
            if is_label(directive) {
                labels.push(Label {
                    name: directive.split(':').next().unwrap_or("").to_string(),
                    length: 0,
                    covered: covers,
                    crosses,
                });
                current_label = Some(labels.len() - 1);
                crosses = false;
            }
            let n = size(line)?;
            covers = covers.saturating_sub(n);
            if let Some(l) = current_label {
                labels[l].length += n;
            }
            let p = &mut pieces[piece.unwrap()];
            p.lines.push(line.to_string());
            p.size += n;
        }
        let leaked: Vec<&String> = own
            .iter()
            .filter(|l| {
                let d = code(l);
                d.starts_with(".block") || d.starts_with(".crossbank") || d == ".msu"
            })
            .collect();
        if let Some(first) = leaked.first() {
            // A `.block` that reaches the assembler is a `ca65` error far
            // from here, which does not say which block or why.
            return Err(format!(
                "{name} left {} `.block` unresolved, the first one {:?}: it is outside \
                 {SEGMENT}, and there the packing cannot be computed",
                leaked.len(),
                first.trim()
            ));
        }
        kept.push(own);
    }
    let loose = undeclared(&labels);
    if !loose.is_empty() {
        return Err(format!(
            "{} label(s) in {SEGMENT} without a `.block` covering them, and the packing \
             may split them across two banks: {}. If the ROM walks one jumping banks by \
             hand, put `.crossbank` in front of it",
            loose.len(),
            loose.join(", ")
        ));
    }

    let mut spill = None;
    let mut spilled_bytes = 0;
    let mut gone: Vec<usize> = Vec::new();
    if required && !packed_before {
        let start = msu_start.ok_or_else(|| {
            "the cartridge needs the MSU-1 (MSU_REQUIRED) and there is no .msu with data \
             next to the ROM to put what does not fit in"
                .to_string()
        })?;
        if start % crate::msu::UNIT != 0 {
            return Err(format!("the .msu region would start at {start}, not on a unit"));
        }
        // The region's signature, as one more piece: zeros while deciding,
        // which take the same.
        let signature = pieces.len();
        let mut piece = Piece::new(signature);
        piece.asks = crate::msu::SIGNATURE;
        piece.size = crate::msu::SIGNATURE;
        piece.lines = signature_lines(&[0; crate::msu::SIGNATURE]);
        pieces.push(piece);

        let mut candidates: Vec<usize> = (0..pieces.len()).filter(|&k| pieces[k].msu).collect();
        candidates.sort_by_key(|&k| (std::cmp::Reverse(pieces[k].fit_size()), pieces[k].order));
        let without = |count: usize| -> Vec<&Piece> {
            let out: std::collections::HashSet<usize> = candidates[..count].iter().copied().collect();
            pieces.iter().filter(|p| !out.contains(&p.order)).collect()
        };
        let count = if everything {
            candidates.len()
        } else if pack(&without(0), slots).is_ok() {
            0
        } else {
            if let Err(e) = pack(&without(candidates.len()), slots) {
                return Err(format!(
                    "{e}, even with the {} piece(s) that may go to the .msu there",
                    candidates.len()
                ));
            }
            let (mut fails, mut fits) = (0, candidates.len());
            while fits - fails > 1 {
                let middle = (fails + fits) / 2;
                if pack(&without(middle), slots).is_ok() {
                    fits = middle;
                } else {
                    fails = middle;
                }
            }
            fits
        };
        gone = candidates[..count].to_vec();
        gone.sort();

        let mut datas = Vec::new();
        let mut constants = vec![
            "; --- what the packing sent to the `.msu`: see `pack_with_msu` in".to_string(),
            "; rm2k-snes-cartridge. Each label is bank MSU_SPILL_BANK and its unit ---".to_string(),
            format!("MSU_SPILL_BANK = ${:02X}", crate::msu::SPILL_BANK),
            format!("{SPILL_AT} = ${:06X}", start / crate::msu::UNIT),
            format!("MSU_SPILLED = {}", gone.len()),
        ];
        let mut unit = 1;
        for &k in &gone {
            let (label, data) = piece_bytes(&pieces[k])
                .map_err(|e| format!("a piece marked `.msu` that cannot go: {e}"))?;
            if unit > crate::msu::LAST_UNIT {
                return Err(format!(
                    "the .msu region goes past {} units of {} bytes",
                    crate::msu::LAST_UNIT,
                    crate::msu::UNIT
                ));
            }
            constants.push(format!("{label} = ${:06X}", crate::msu::SPILL_BANK << 16 | unit));
            unit += crate::msu::units(data.len());
            spilled_bytes += data.len();
            datas.push(data);
        }
        let region = crate::msu::region(&datas);
        pieces[signature].lines = signature_lines(&region[..crate::msu::SIGNATURE]);
        spill = Some(Spill { region });
        if let Some(last) = kept.last_mut() {
            last.extend(constants);
        }
    }
    let staying: Vec<&Piece> = pieces.iter().filter(|p| gone.binary_search(&p.order).is_err()).collect();
    let banks = pack(&staying, slots)?;
    let packing = Packing {
        pieces: staying.len(),
        banks: banks.len(),
        slow: banks.iter().filter(|b| !slots[b.slot].fast()).count(),
        spilled: gone.len(),
        spilled_bytes,
    };
    if let Some(last) = kept.last_mut() {
        for bank in banks {
            last.push(format!(".segment \"{}\"", segment_of(slots[bank.slot].bank)));
            last.extend(bank.lines);
        }
    }
    let texts = kept
        .into_iter()
        .map(|own| own.join("\n") + "\n")
        .collect();
    Ok((texts, packing, spill))
}

/// The lines of `msu_spill_signature`, with these bytes.
fn signature_lines(bytes: &[u8]) -> Vec<String> {
    let hex: Vec<String> = bytes.iter().map(|b| format!("${b:02X}")).collect();
    vec!["msu_spill_signature:".to_string(), format!("    .byte {}", hex.join(","))]
}

/// The label and the bytes of a piece that goes to the `.msu`: one label
/// at its start and nothing but literal `.byte`s after it.
fn piece_bytes(piece: &Piece) -> Result<(String, Vec<u8>), String> {
    let mut label: Option<String> = None;
    let mut data = Vec::new();
    for line in &piece.lines {
        let directive = code(line);
        if directive.is_empty() {
            continue;
        }
        if is_label(directive) {
            if label.is_some() || !data.is_empty() {
                return Err(format!("{:?} is not the piece's only label at its start", directive));
            }
            label = Some(directive.split(':').next().unwrap_or("").to_string());
            continue;
        }
        let (first, rest) = first_word(directive);
        if first != ".byte" || label.is_none() {
            return Err(format!("{:?} is not a literal byte", line.trim()));
        }
        for operand in rest.unwrap_or("").split(',').map(str::trim) {
            let value = match operand.strip_prefix('$') {
                Some(hex) => u8::from_str_radix(hex, 16).ok(),
                None => operand.parse().ok(),
            };
            data.push(value.ok_or_else(|| format!("{operand:?} is not a literal byte"))?);
        }
    }
    let label = label.ok_or("a piece without a label")?;
    if data.len() < piece.asks {
        return Err(format!("{label} declares {} bytes and carries {}", piece.asks, data.len()));
    }
    Ok((label, data))
}

/// The number after `.block` or `.align`.
fn number(directive: &str, line: &str) -> Result<usize, String> {
    directive
        .split_whitespace()
        .nth(1)
        .and_then(|n| n.parse().ok())
        .ok_or_else(|| format!("expected a number: {:?}", line.trim()))
}

/// The labels that can be split without anyone having asked for it.
///
/// A single-byte one is never split, and that is why it is let through: the
/// converter emits empty tables with one byte of padding, and one that grows
/// is caught the day it grows.
fn undeclared(labels: &[Label]) -> Vec<String> {
    labels
        .iter()
        .filter(|l| l.length > 1 && l.covered < l.length && !l.crosses)
        .map(|l| l.name.clone())
        .collect()
}

struct Bank {
    /// Which of the slots it is.
    slot: usize,
    used: usize,
    lines: Vec<String>,
}

fn padding(used: usize, align: usize) -> usize {
    (align - used % align) % align
}

/// The banks being filled, out of `slots`.
struct Packer<'a> {
    slots: &'a [Slot],
    taken: Vec<bool>,
    banks: Vec<Bank>,
}

impl Packer<'_> {
    fn capacity(&self, bank: usize) -> usize {
        self.slots[self.banks[bank].slot].size
    }

    fn take(&mut self, slot: usize) -> usize {
        self.taken[slot] = true;
        self.banks.push(Bank { slot, used: 0, lines: Vec::new() });
        self.banks.len() - 1
    }

    /// A new bank: the first free slot where `need` bytes fit.
    fn open(&mut self, need: usize) -> Result<usize, String> {
        match (0..self.slots.len()).find(|&k| !self.taken[k] && self.slots[k].size >= need) {
            Some(k) => Ok(self.take(k)),
            // Without this the one complaining is `ld65`, with an internal
            // error that does not say that space ran out.
            None => Err(format!(
                "the data does not fit: a piece of {need} bytes needs a new bank, and the \
                 {} banks the cartridge has for data are taken",
                self.slots.len()
            )),
        }
    }

    /// The slot that continues `bank`'s, if it is free.
    fn after(&self, bank: usize) -> Option<usize> {
        let k = self.banks[bank].slot;
        (k + 1 < self.slots.len()
            && !self.taken[k + 1]
            && self.slots[k].continues_into(&self.slots[k + 1]))
        .then_some(k + 1)
    }

    /// The new bank a piece crossing out of `bank` goes on into.
    fn continue_after(&mut self, bank: usize) -> Result<usize, String> {
        match self.after(bank) {
            Some(k) => Ok(self.take(k)),
            None => {
                let slot = self.slots[self.banks[bank].slot];
                Err(format!(
                    "a piece walked by hand would cross from ${:06X}, and no free bank \
                     continues it: the data does not fit, or one piece is longer than a \
                     run of whole banks",
                    slot.address() + slot.size - 1
                ))
            }
        }
    }

    fn fits(&self, bank: usize, u: &Piece) -> bool {
        // A lone label takes space too: at the end of a bank it would point
        // to the address after `$FFFF`, which is not the next bank.
        let b = &self.banks[bank];
        b.used + padding(b.used, u.align) + u.fit_size().max(1) <= self.capacity(bank)
    }

    fn put(&mut self, bank: usize, u: &Piece) {
        let b = &mut self.banks[bank];
        b.used += padding(b.used, u.align) + u.size;
        b.lines.extend(u.lines.iter().cloned());
    }

    /// First fit over the banks already open.
    fn place(&mut self, u: &Piece) -> bool {
        match (0..self.banks.len()).find(|&b| self.fits(b, u)) {
            Some(b) => {
                self.put(b, u);
                true
            }
            None => false,
        }
    }

    /// Writes `lines` from the end of `bank`, splitting between operands and
    /// continuing in the banks that continue it: the sequential packing, for
    /// what can or has to cross. Returns the bank it ended in.
    fn spill(&mut self, mut bank: usize, lines: &[String]) -> Result<usize, String> {
        for line in lines {
            let directive = code(line);
            // A full bank is left behind before writing anything else,
            // labels included: a label at the end of a bank would point to
            // the address after `$FFFF`.
            if self.banks[bank].used == self.capacity(bank) && !directive.is_empty() {
                bank = self.continue_after(bank)?;
            }
            if directive.starts_with(".align ") {
                let b = &mut self.banks[bank];
                b.used += padding(b.used, number(directive, line)?);
                b.lines.push(line.clone());
                continue;
            }
            let mut line = line.clone();
            let mut n = size(&line)?;
            while self.banks[bank].used + n > self.capacity(bank) {
                let room = self.capacity(bank) - self.banks[bank].used;
                let (first, rest, rest_size) = split(&line, room)?;
                let full = self.capacity(bank);
                let b = &mut self.banks[bank];
                if let Some(first) = first {
                    b.lines.push(first);
                }
                b.used = full;
                bank = self.continue_after(bank)?;
                line = rest;
                n = rest_size;
            }
            let b = &mut self.banks[bank];
            b.used += n;
            b.lines.push(line);
        }
        Ok(bank)
    }
}

/// The banks, with the pieces inside, in the order they were opened. See
/// [`resolve`], which says what each kind is.
///
/// **If it does not fit, it tries once more with the chain first.** The
/// chain of `.crossbank` pieces needs whole banks that continue each other,
/// and it goes last: in a cartridge that is almost full the whole pieces
/// have taken every whole bank by then —opening a new one takes the first
/// free slot, and the whole banks come before the halves—, and the chain
/// finds only halves, where it cannot go. Measured on 2026-10-11 with a
/// game of 7.10 MB for the 7.94: it did not fit. With the chain
/// first, from a new whole bank, the whole pieces fill the halves when the
/// whole banks run out. A cartridge that fits the first way is packed the
/// first way, as it always was.
fn pack(pieces: &[&Piece], slots: &[Slot]) -> Result<Vec<Bank>, String> {
    match pack_in_order(pieces, slots, false) {
        Ok(banks) => Ok(banks),
        Err(first) => pack_in_order(pieces, slots, true).map_err(|_| first),
    }
}

fn pack_in_order(pieces: &[&Piece], slots: &[Slot], chain_first: bool) -> Result<Vec<Bank>, String> {
    let mut packer = Packer { slots, taken: vec![false; slots.len()], banks: Vec::new() };
    if chain_first {
        let mut chain: Vec<&Piece> = pieces.iter().copied().filter(|u| u.crosses).collect();
        chain.sort_by_key(|u| u.order);
        if !chain.is_empty() {
            let mut bank = packer.open(BANK_SIZE)?;
            for u in chain {
                let left = packer.capacity(bank) - packer.banks[bank].used;
                if u.fit_size() > left && packer.after(bank).is_none() {
                    bank = packer.open(BANK_SIZE)?;
                }
                bank = packer.spill(bank, &u.lines)?;
            }
        }
    }
    let large: Vec<&Piece> = pieces
        .iter().copied()
        .filter(|u| !u.crosses && u.fit_size() > BANK_SIZE)
        .collect();
    let mut whole: Vec<&Piece> = pieces
        .iter().copied()
        .filter(|u| !u.crosses && u.fit_size() <= BANK_SIZE)
        .collect();
    let mut crossing: Vec<&Piece> =
        pieces.iter().copied().filter(|u| u.crosses && !chain_first).collect();

    // The large ones first, each from a new whole bank: what is left over in
    // their last bank is used by the others.
    for u in large {
        let bank = packer.open(BANK_SIZE)?;
        packer.spill(bank, &u.lines)?;
    }
    let by_size = |u: &&Piece| (std::cmp::Reverse(u.fit_size()), u.order);
    whole.sort_by_key(by_size);
    for u in whole {
        if !packer.place(u) {
            let bank = packer.open(u.fit_size().max(1))?;
            packer.put(bank, u);
        }
    }
    crossing.sort_by_key(by_size);
    let mut chain: Vec<&Piece> = Vec::new();
    for u in crossing {
        if u.fit_size() > BANK_SIZE || !packer.place(u) {
            chain.push(u);
        }
    }
    if chain.is_empty() {
        return Ok(packer.banks);
    }
    // The chain starts in what is left of the last whole bank opened, which
    // is the one a crossing can go on from.
    let last_whole = (0..packer.banks.len())
        .rev()
        .find(|&b| packer.capacity(b) == BANK_SIZE);
    let mut bank = match last_whole {
        Some(b) => b,
        None => packer.open(BANK_SIZE)?,
    };
    chain.sort_by_key(|u| u.order);
    for u in chain {
        // A piece that does not fit in what is left, where no bank continues
        // this one, starts in a new bank: it may cross inside a run of whole
        // banks, never between two runs.
        let left = packer.capacity(bank) - packer.banks[bank].used;
        if u.fit_size() > left && packer.after(bank).is_none() {
            bank = packer.open(BANK_SIZE)?;
        }
        bank = packer.spill(bank, &u.lines)?;
    }
    Ok(packer.banks)
}

/// The `ld65` `.cfg`: the 8 MB in file order, one area per data slot, and
/// each segment in its own.
///
/// An area with `fill = yes` is padded to the end, so each bank takes its
/// place in the file even if its segment does not fill it, and a segment
/// that overflows makes the link fail instead of spilling into the next
/// one. The `BANKnn` are optional because how many are used depends on the
/// cartridge. What is not data —the copies of banks 0 and 1, the low halves
/// [`slots`] leaves out— goes in as zeros, in areas no segment loads.
///
/// **Banks 0 and 1 are linked at `$00:8000` and `$01:8000`**, as in LoROM,
/// and sit at `$008000` and `$018000` of the file: the addresses are the
/// ones the runtime was written against, and the place is the one the code
/// runs from, which is what `ld65`'s debug file tells Mesen2. See the
/// module's docs.
///
/// The `align = $8000` moves nothing —each segment starts at the beginning
/// of its area, which is already aligned to that—, but `ld65` requires a
/// segment to declare at least the alignment of the `.align`s it carries.
pub fn cfg() -> String {
    let mut memory = vec![
        // The RAM does not go into the file: it is laid out by address, not
        // by offset.
        "ZP:   start = $0000, size = $0100, type = rw, file = \"\";".to_string(),
        format!(
            "RAM:  start = $0100, size = ${:04X}, type = rw, file = \"\";",
            0x1F00 - STACK
        ),
        // `define` gives the runtime `__FARRAM_START__`, to assert that the
        // map written by hand stays out of it.
        format!(
            "FARRAM: start = ${FAR_POOL_START:06X}, size = ${FAR_POOL_SIZE:04X}, type = rw, file = \"\", define = yes;"
        ),
    ];
    let mut segments = vec![
        "ZEROPAGE: load = ZP,   type = zp;".to_string(),
        "BSS:      load = RAM,  type = bss;".to_string(),
        "FARBSS:   load = FARRAM, type = bss;".to_string(),
        "CODE:     load = ROM,  type = ro;".to_string(),
        "TABLES:   load = ROM,  type = ro;".to_string(),
        "HEADER:   load = HEAD, type = ro;".to_string(),
        "VECTORS:  load = VECT, type = ro;".to_string(),
        // The hand-written code that lives outside bank 0.
        format!("FAR:      load = {}, type = ro, align = $8000;", segment_of(1)),
        format!("FAR2:     load = {}, type = ro;", segment_of(FAR2.bank)),
    ];
    let data = slots();
    let area = |name: String, start: usize, size: usize| {
        format!("{name}: start = ${start:06X}, size = ${size:X}, fill = yes;")
    };
    let mut gap = 0;
    // Walking the file in steps of half a bank, which is the finest grain
    // anything in it has.
    let mut offset = 0;
    while offset < ROM_SIZE {
        if offset == 0x008000 {
            // Bank 0: the code and the tables, and the header and the
            // vectors at the end, where the console looks for them.
            memory.push("ROM:  start = $008000, size = $7FC0, fill = yes;".to_string());
            memory.push("HEAD: start = $00FFC0, size = $0020, fill = yes;".to_string());
            memory.push("VECT: start = $00FFE0, size = $0020, fill = yes;".to_string());
            offset += HALF;
            continue;
        }
        if Some(offset) == file_offset(FAR2.address()) {
            memory.push(area(segment_of(FAR2.bank), FAR2.address(), FAR2.size));
            offset += FAR2.size;
            continue;
        }
        if offset == 0x018000 {
            memory.push(area(segment_of(1), 0x018000, HALF));
            offset += HALF;
            continue;
        }
        let slot = data
            .iter()
            .find(|s| file_offset(s.address()) == Some(offset));
        match slot {
            Some(slot) => {
                memory.push(area(segment_of(slot.bank), slot.address(), slot.size));
                segments.push(format!(
                    "{0}: load = {0}, type = ro, align = $8000, optional = yes;",
                    segment_of(slot.bank)
                ));
                offset += slot.size;
            }
            None => {
                // The copies of banks 0 and 1, which the assembler writes
                // after linking, and what the cartridge has but the data
                // cannot use. The start is the file offset: nothing is
                // linked there.
                memory.push(area(format!("NODATA{gap}"), offset, HALF));
                gap += 1;
                offset += HALF;
            }
        }
    }
    let indent = |v: Vec<String>| {
        v.into_iter()
            .map(|l| format!("    {l}"))
            .collect::<Vec<_>>()
            .join("\n")
    };
    format!(
        "# Generated by rm2k-snes-assemble: the ROM's memory map.\n\
         MEMORY {{\n{}\n}}\nSEGMENTS {{\n{}\n}}\n",
        indent(memory),
        indent(segments)
    )
}
