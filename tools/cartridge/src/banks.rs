//! The bank packing, and the memory map `ld65` links against.
//!
//! A DMA that crosses a bank does not read the next bank's ROM: it reads the
//! WRAM. So everything the ROM uploads by DMA —a pose, a tilemap, a block of
//! samples— has to fit **whole** in a bank, and when it does not fit in what
//! is left of the current one, it has to go to another.
//!
//! `ld65` cannot pack variable-size blocks, so it is done here, before the
//! assembler runs: the generated data sends everything to one segment,
//! `RODATA`, with a directive in front of each piece that says what kind it
//! is, and this rewrites the files so that what reaches the assembler is one
//! segment per bank, `BANKnn`, which is what [`cfg`] declares.
//!
//! **The only thing this module assumes about the memory map is which bank
//! the generated data starts in**, [`FIRST_BANK`]. The `.cfg` knows the rest.

use std::path::Path;

use crate::text::{code, first_word, is_constant, is_label, split_lines};

/// A LoROM bank, as the CPU sees it at `$8000-$FFFF`.
pub const BANK_SIZE: usize = 0x8000;

/// 4 MB LoROM: 128 banks of 32 KB.
pub const BANKS: usize = 128;

/// The last two are not used for data: on the console, banks `$7E` and `$7F`
/// **are** the WRAM, and data there would be read as RAM. They still go into
/// the file, as zeros, so the image is the 4 MB its header says.
pub const RESERVED_BANKS: usize = 2;

/// The bank where the generated data starts. Bank 0 is the code and the
/// tables, and bank 1 is `FAR`, the hand-written code that lives outside
/// bank 0.
pub const FIRST_BANK: usize = 2;

/// The stack starts at `$1FFF` and grows downwards, towards the BSS: the two
/// share the low 8 KB of the WRAM. This is what the stack is given, and the
/// lowest byte it gets is `$2000 - STACK`.
///
/// It is a cap and not a measurement: a runtime whose deepest call chain
/// needs more eats into the BSS, and nothing at link time can tell. Whoever
/// lowers it has to be measuring how deep the stack really goes.
pub const STACK: usize = 128;

/// The segment the generated data sends everything to.
pub const SEGMENT: &str = "RODATA";

/// The name of the segment pinned at the start of `bank`.
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

/// How many pieces were packed, and into how many banks.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Packing {
    pub pieces: usize,
    pub banks: usize,
}

/// Splits into banks what `paths` send to `RODATA`, and rewrites them.
///
/// **It is first-fit decreasing**: each piece goes to the first bank where
/// it fits, from the largest to the smallest. The pieces are declared by
/// whoever wrote the files, and there are three kinds.
///
/// * **A `.block N` of up to one bank** fits whole in one: almost all of
///   them are uploaded by DMA, and a DMA that crosses a bank reads the WRAM.
///   It carries everything that follows up to the next directive —the tables
///   the `.block` measures together, and the one-byte labels after them—.
/// * **One of more than a bank** starts a bank and goes on into the
///   following ones, split between operands: it is walked by code that jumps
///   banks by hand. What is left over in its last bank is used by the
///   others.
/// * **A `.crossbank`** can be split anywhere **between two consecutive
///   banks**: the code that walks it jumps from `$FFFF` to the next bank's
///   `$8000`, not to any bank. First it is tried whole in a gap; the ones
///   that do not fit go at the end, one after the other, as a chain that
///   starts in whatever is left of the last bank and continues in new banks.
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
/// split, the second half is read from the next bank's `$0000`, which in
/// LoROM is not ROM. The rule is enforced on every build, and not on the day
/// the cut lands on one.
///
/// Running it twice changes nothing: the second time there is no `RODATA`
/// left, and the banks the first one wrote stay as they are.
pub fn resolve<P: AsRef<Path>>(paths: &[P]) -> Result<Packing, String> {
    resolve_from(paths, FIRST_BANK)
}

/// [`resolve`], with the data starting at `first_bank`.
pub fn resolve_from<P: AsRef<Path>>(paths: &[P], first_bank: usize) -> Result<Packing, String> {
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
    let (kept, packing) = pack_texts(&names, &refs, first_bank)?;
    for (path, own) in paths.iter().zip(kept) {
        let path = path.as_ref();
        std::fs::write(path, own).map_err(|e| format!("{}: {e}", path.display()))?;
    }
    Ok(packing)
}

/// The packing over texts already read: what each file becomes, and the
/// count. `names` are only for the messages.
pub fn pack_texts(
    names: &[String],
    texts: &[&str],
    first_bank: usize,
) -> Result<(Vec<String>, Packing), String> {
    let mut pieces: Vec<Piece> = Vec::new();
    let mut kept: Vec<Vec<String>> = Vec::new();
    let mut labels: Vec<Label> = Vec::new();
    let mut covers = 0usize;
    let mut crosses = false;
    for (name, text) in names.iter().zip(texts) {
        let mut own: Vec<String> = Vec::new();
        let mut current: Option<String> = None;
        // Indices into `pieces` and `labels`.
        let mut piece: Option<usize> = None;
        let mut current_label: Option<usize> = None;
        for line in split_lines(text) {
            let directive = code(line);
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
                d.starts_with(".block") || d.starts_with(".crossbank")
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

    let banks = pack(&pieces)?;
    let fitting = BANKS - RESERVED_BANKS - first_bank;
    if banks.len() > fitting {
        // Without this the one complaining is `ld65`, with an internal error
        // that does not say that space ran out.
        return Err(format!(
            "the data needs {} banks and {fitting} fit: from ${first_bank:02X} to ${:02X}",
            banks.len(),
            first_bank + fitting - 1
        ));
    }
    let packing = Packing {
        pieces: pieces.len(),
        banks: banks.len(),
    };
    if let Some(last) = kept.last_mut() {
        for (k, bank) in banks.into_iter().enumerate() {
            last.push(format!(".segment \"{}\"", segment_of(first_bank + k)));
            last.extend(bank.lines);
        }
    }
    let texts = kept
        .into_iter()
        .map(|own| own.join("\n") + "\n")
        .collect();
    Ok((texts, packing))
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
    used: usize,
    lines: Vec<String>,
}

impl Bank {
    fn new() -> Bank {
        Bank {
            used: 0,
            lines: Vec::new(),
        }
    }
}

fn padding(used: usize, align: usize) -> usize {
    (align - used % align) % align
}

/// The banks, with the pieces inside. See [`resolve`], which says what each
/// kind is.
fn pack(pieces: &[Piece]) -> Result<Vec<Bank>, String> {
    let mut banks: Vec<Bank> = Vec::new();
    let large: Vec<&Piece> = pieces
        .iter()
        .filter(|u| !u.crosses && u.fit_size() > BANK_SIZE)
        .collect();
    let mut whole: Vec<&Piece> = pieces
        .iter()
        .filter(|u| !u.crosses && u.fit_size() <= BANK_SIZE)
        .collect();
    let mut crossing: Vec<&Piece> = pieces.iter().filter(|u| u.crosses).collect();

    fn fits(bank: &Bank, u: &Piece) -> bool {
        // A lone label takes space too: at the end of a bank it would point
        // to the address after `$FFFF`, which is not the ROM.
        bank.used + padding(bank.used, u.align) + u.fit_size().max(1) <= BANK_SIZE
    }

    fn place(banks: &mut [Bank], u: &Piece) -> bool {
        for bank in banks.iter_mut() {
            if fits(bank, u) {
                bank.used += padding(bank.used, u.align) + u.size;
                bank.lines.extend(u.lines.iter().cloned());
                return true;
            }
        }
        false
    }

    // The large ones first, each from a new bank: what is left over in their
    // last bank is used by the others.
    for u in large {
        banks.push(Bank::new());
        spill(&mut banks, &u.lines)?;
    }
    let by_size = |u: &&Piece| (std::cmp::Reverse(u.fit_size()), u.order);
    whole.sort_by_key(by_size);
    for u in whole {
        if !place(&mut banks, u) {
            banks.push(Bank::new());
            place(&mut banks, u);
        }
    }
    crossing.sort_by_key(by_size);
    let mut chain: Vec<&Piece> = Vec::new();
    for u in crossing {
        if u.fit_size() > BANK_SIZE || !place(&mut banks, u) {
            chain.push(u);
        }
    }
    if !chain.is_empty() && banks.is_empty() {
        banks.push(Bank::new());
    }
    chain.sort_by_key(|u| u.order);
    for u in chain {
        spill(&mut banks, &u.lines)?;
    }
    Ok(banks)
}

/// Writes `lines` from the end of the last bank, splitting between operands
/// and continuing in new banks: the sequential packing, for what can or has
/// to cross.
fn spill(banks: &mut Vec<Bank>, lines: &[String]) -> Result<(), String> {
    for line in lines {
        let directive = code(line);
        // A full bank is left behind before writing anything else, labels
        // included: a label at the end of a bank would point to the address
        // after `$FFFF`, which is not the ROM.
        if banks.last().unwrap().used == BANK_SIZE && !directive.is_empty() {
            banks.push(Bank::new());
        }
        let bank = banks.last_mut().unwrap();
        if directive.starts_with(".align ") {
            bank.used += padding(bank.used, number(directive, line)?);
            bank.lines.push(line.clone());
            continue;
        }
        let mut line = line.clone();
        let mut n = size(&line)?;
        while banks.last().unwrap().used + n > BANK_SIZE {
            let bank = banks.last_mut().unwrap();
            let (first, rest, rest_size) = split(&line, BANK_SIZE - bank.used)?;
            if let Some(first) = first {
                bank.lines.push(first);
            }
            banks.push(Bank::new());
            line = rest;
            n = rest_size;
        }
        let bank = banks.last_mut().unwrap();
        bank.used += n;
        bank.lines.push(line);
    }
    Ok(())
}

/// The `ld65` `.cfg`: one area per bank, and each segment in its own.
///
/// An area with `fill = yes` is padded to the end, so each bank takes its
/// 32 KB in the file even if its segment does not fill them, and a segment
/// that overflows makes the link fail instead of spilling into the next
/// one. The `BANKnn` are optional because how many are used depends on the
/// cartridge.
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
        // Bank 0: the code and the tables, and the header and the vectors at
        // the end, where the console looks for them.
        "ROM:  start = $008000, size = $7FC0, fill = yes;".to_string(),
        "HEAD: start = $00FFC0, size = $0020, fill = yes;".to_string(),
        "VECT: start = $00FFE0, size = $0020, fill = yes;".to_string(),
    ];
    let mut segments = vec![
        "ZEROPAGE: load = ZP,   type = zp;".to_string(),
        "BSS:      load = RAM,  type = bss;".to_string(),
        "CODE:     load = ROM,  type = ro;".to_string(),
        "TABLES:   load = ROM,  type = ro;".to_string(),
        "HEADER:   load = HEAD, type = ro;".to_string(),
        "VECTORS:  load = VECT, type = ro;".to_string(),
        // The hand-written code that lives outside bank 0.
        format!("FAR:      load = {}, type = ro, align = $8000;", segment_of(1)),
    ];
    for bank in 1..BANKS - RESERVED_BANKS {
        memory.push(format!(
            "{}: start = ${bank:02X}8000, size = $8000, fill = yes;",
            segment_of(bank)
        ));
        if bank >= FIRST_BANK {
            segments.push(format!(
                "{}: load = {}, type = ro, align = $8000, optional = yes;",
                segment_of(bank),
                segment_of(bank)
            ));
        }
    }
    // The two reserved ones go into the file anyway, as zeros: the cartridge
    // is 4 MB, which is what the header says and what flash carts expect.
    // The area keeps the name it had when this map was written by a script in
    // Spanish: renaming it changes the `.cfg` every ROM has been built with,
    // and nothing reads the name.
    memory.push(format!(
        "RESERVADO: start = ${:02X}8000, size = ${:X}, fill = yes;",
        BANKS - RESERVED_BANKS,
        0x8000 * RESERVED_BANKS
    ));
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
