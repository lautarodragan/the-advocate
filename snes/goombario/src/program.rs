//! The program as the checks see it: every instruction the assembler emitted,
//! read from the ROM where the debug file says each source line went.
//!
//! Nothing is disassembled by guessing where instructions start: each line's
//! span says where its bytes are, and a span with a type is data. A span
//! that is one instruction is the common case; a macro's expansion comes with
//! a line per instruction, and a `.repeat`, which has no lines of its own, is
//! decoded from the start of its span with the widths that make it end
//! exactly where the span ends.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;

use crate::cpu;
use crate::dbg::{DebugInfo, Segment};
use crate::source::{self, Declared, Widths};

#[derive(Clone, Debug)]
pub struct Insn {
    pub addr: u32,
    pub offset: usize,
    pub op: u8,
    pub len: u32,
    /// The source line it came from: the line of the text, not of a macro's
    /// body, so for an expansion it is where the macro is used.
    pub line: Option<usize>,
    /// The line of a macro's body it came from, if it did.
    pub macro_line: Option<usize>,
}

pub struct Program {
    pub rom: Vec<u8>,
    segments: Vec<Segment>,
    pub insns: BTreeMap<u32, Insn>,
    /// Data inside the ROM segments, start to end.
    data: BTreeMap<u32, u32>,
    /// The line each piece of data came from.
    data_lines: BTreeMap<u32, usize>,
    /// Every label in the ROM, by address.
    labels: BTreeMap<u32, String>,
    /// The labels outside any `.proc`: routines, mostly.
    routines: BTreeMap<u32, String>,
    pub files: HashMap<usize, String>,
    lines: HashMap<usize, (usize, u32)>,
    /// The lines of the text that put bytes in the ROM, code or data, by
    /// file id and line number.
    assembled: HashSet<(usize, u32)>,
    declared: Declared,
    /// The widths of each instruction of a line with several, which the
    /// line's own do not say.
    expanded: HashMap<u32, Widths>,
    /// Spans that could not be read as instructions: the file, and what.
    pub undecoded: Vec<(String, String)>,
}

struct RawSpan {
    addr: u32,
    offset: usize,
    size: u32,
    line: usize,
    in_macro: bool,
    data: bool,
}

/// The directives that put bytes in a segment and are not instructions.
const DATA_DIRECTIVES: &[&str] = &[
    ".byte",
    ".byt",
    ".db",
    ".word",
    ".dbyt",
    ".addr",
    ".dw",
    ".faraddr",
    ".dword",
    ".res",
    ".align",
    ".incbin",
    ".asciiz",
    ".lobytes",
    ".hibytes",
    ".bankbytes",
    ".tag",
];

fn is_data_directive(text: &str) -> bool {
    // Past a label, if the line has one.
    let text = match text.split_once(':') {
        Some((label, rest)) if !label.contains(char::is_whitespace) && !rest.starts_with(':') => {
            rest
        }
        _ => text,
    };
    let first = text
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    DATA_DIRECTIVES.contains(&first.as_str())
}

impl Program {
    pub fn load(rom: Vec<u8>, info: &DebugInfo, root: &Path) -> Program {
        let mut segments: Vec<Segment> = info
            .segments
            .values()
            .filter(|s| s.ooffs.is_some() && s.size > 0)
            .cloned()
            .collect();
        segments.sort_by_key(|s| s.start);
        let declared = source::declared(info, root);
        let mut texts = source::Texts::new(root);
        let mut spans = Vec::new();
        for (&id, line) in &info.lines {
            // Not every piece of data gets a type in the debug file: `.res`,
            // `.align` and `.dword` do not. The directive on the line says.
            let directive = match info.files.get(&line.file) {
                Some(name) => is_data_directive(&texts.line(name, line.line)),
                None => false,
            };
            for span_id in &line.spans {
                let Some(span) = info.spans.get(span_id) else {
                    continue;
                };
                let Some(seg) = info.segments.get(&span.seg) else {
                    continue;
                };
                let Some(ooffs) = seg.ooffs else { continue };
                if span.size == 0 || ooffs + (span.start + span.size) as usize > rom.len() {
                    continue;
                }
                spans.push(RawSpan {
                    addr: seg.start + span.start,
                    offset: ooffs + span.start as usize,
                    size: span.size,
                    line: id,
                    in_macro: line.in_macro
                        || declared.macro_lines.contains_key(&(line.file, line.line)),
                    data: span.data || directive,
                });
            }
        }
        // A line's spans that touch are one piece: `ca65` gives an
        // instruction whose operand is an expression —`mvn #^x, #^x`— a span
        // for the opcode and another for the operand.
        spans.sort_by_key(|s| (s.line, s.addr));
        let mut merged: Vec<RawSpan> = Vec::new();
        for s in spans {
            if let Some(last) = merged.last_mut() {
                if last.line == s.line && last.data == s.data && last.addr + last.size == s.addr {
                    last.size += s.size;
                    continue;
                }
            }
            merged.push(s);
        }
        let mut spans = merged;
        // The narrowest first: an instruction's own line before the line of
        // the macro it came from, and data before the code around it.
        spans.sort_by_key(|s| (s.size, !s.data, s.addr));
        let mut program = Program {
            rom,
            segments,
            insns: BTreeMap::new(),
            data: BTreeMap::new(),
            data_lines: BTreeMap::new(),
            labels: BTreeMap::new(),
            routines: BTreeMap::new(),
            files: info.files.clone(),
            lines: info
                .lines
                .iter()
                .map(|(&id, l)| (id, (l.file, l.line)))
                .collect(),
            assembled: HashSet::new(),
            declared,
            expanded: HashMap::new(),
            undecoded: Vec::new(),
        };
        for s in &spans {
            if let Some(&place) = program.lines.get(&s.line) {
                program.assembled.insert(place);
            }
        }
        for s in spans.iter().filter(|s| s.data) {
            program.data.insert(s.addr, s.addr + s.size);
            program.data_lines.entry(s.addr).or_insert(s.line);
        }
        for s in spans.iter().filter(|s| !s.data) {
            let hint = info
                .lines
                .get(&s.line)
                .map(|l| program.declared_at(l.file, l.line));
            if !program.decode(s, hint.unwrap_or_default()) {
                let (file, line) = program.lines[&s.line];
                let name = program.files.get(&file).cloned().unwrap_or_default();
                program.undecoded.push((
                    name.clone(),
                    format!(
                        "{}:{}: {} bytes at ${:06X} that are not whole instructions",
                        name, line, s.size, s.addr
                    ),
                ));
            }
        }
        // Which line each instruction is from: the narrowest line of the text
        // whose span covers it.
        for s in spans.iter().filter(|s| !s.data) {
            for (_, insn) in program.insns.range_mut(s.addr..s.addr + s.size) {
                let slot = if s.in_macro {
                    &mut insn.macro_line
                } else {
                    &mut insn.line
                };
                if slot.is_none() {
                    *slot = Some(s.line);
                }
            }
        }
        // A line with several instructions —a macro's expansion, a
        // `.repeat`— starts with the widths the text has there, and its own
        // `rep`/`sep` change them for the instructions after them: `.smart`
        // follows them inside the expansion too.
        for s in spans.iter().filter(|s| !s.data && !s.in_macro) {
            let mut inside = program
                .insns
                .range(s.addr..s.addr + s.size)
                .filter(|(_, i)| i.line == Some(s.line));
            if inside.clone().count() < 2 {
                continue;
            }
            let (file, line) = program.lines[&s.line];
            let mut w = program.declared_at(file, line);
            let mut each = Vec::new();
            for (&addr, insn) in &mut inside {
                each.push((addr, w));
                if insn.op == cpu::REP || insn.op == cpu::SEP {
                    let bits = program.rom.get(insn.offset + 1).copied().unwrap_or(0);
                    if bits & 0x20 != 0 {
                        w.m8 = Some(insn.op == cpu::SEP);
                    }
                    if bits & 0x10 != 0 {
                        w.x8 = Some(insn.op == cpu::SEP);
                    }
                }
            }
            program.expanded.extend(each);
        }
        for sym in info.syms.values() {
            let Some(value) = sym.value else { continue };
            if !sym.label {
                continue;
            }
            let Some(addr) = program.locate(value) else {
                continue;
            };
            // A label made by a macro's `.local` is in the file's scope, with
            // a name of `ca65`'s: it is not a routine.
            if sym.scope == 0 && !sym.name.starts_with("LOCAL-MACRO") {
                program.routines.insert(addr, sym.name.clone());
                program.labels.insert(addr, sym.name.clone());
            } else {
                program
                    .labels
                    .entry(addr)
                    .or_insert_with(|| sym.name.clone());
            }
        }
        program
    }

    fn data_at(&self, addr: u32) -> Option<u32> {
        self.data
            .range(..=addr)
            .next_back()
            .filter(|(_, &end)| addr < end)
            .map(|(_, &end)| end)
    }

    /// Reads the instructions of one span, unless they are already read.
    fn decode(&mut self, s: &RawSpan, hint: Widths) -> bool {
        let starts = [
            (hint.m8.unwrap_or(true), hint.x8.unwrap_or(true)),
            (true, true),
            (true, false),
            (false, true),
            (false, false),
        ];
        let end = s.addr + s.size;
        for (m0, x0) in starts {
            let (mut m8, mut x8) = (m0, x0);
            let mut p = s.addr;
            let mut new = Vec::new();
            while p < end {
                let offset = s.offset + (p - s.addr) as usize;
                let (op, len) = if let Some(insn) = self.insns.get(&p) {
                    (insn.op, insn.len)
                } else if let Some(data_end) = self.data_at(p) {
                    p = data_end;
                    continue;
                } else {
                    let op = self.rom[offset];
                    // One instruction filling the span is that instruction,
                    // whatever the widths say.
                    let len = if p == s.addr && cpu::lengths(op).contains(&s.size) {
                        s.size
                    } else {
                        cpu::length(op, m8, x8)
                    };
                    new.push(Insn {
                        addr: p,
                        offset,
                        op,
                        len,
                        line: None,
                        macro_line: None,
                    });
                    (op, len)
                };
                if op == cpu::REP || op == cpu::SEP {
                    let bits = self.rom.get(offset + 1).copied().unwrap_or(0);
                    if bits & 0x20 != 0 {
                        m8 = op == cpu::SEP;
                    }
                    if bits & 0x10 != 0 {
                        x8 = op == cpu::SEP;
                    }
                }
                p += len;
            }
            if p == end {
                for insn in new {
                    self.insns.insert(insn.addr, insn);
                }
                return true;
            }
        }
        false
    }

    /// The address as the debug file has it, if it is in a ROM segment:
    /// banks `$80-$BF` are taken as mirrors of `$00-$3F` from `$8000` up,
    /// which is how every Super NES memory map has the system area.
    pub fn locate(&self, addr: u32) -> Option<u32> {
        let inside = |a: u32| {
            self.segments
                .iter()
                .any(|s| a >= s.start && a < s.start + s.size)
        };
        if inside(addr) {
            return Some(addr);
        }
        let mirror = addr ^ 0x80_0000;
        if (addr >> 16) & 0x7F < 0x40 && addr & 0xFFFF >= 0x8000 && inside(mirror) {
            return Some(mirror);
        }
        None
    }

    /// The bytes at an address of the ROM.
    pub fn bytes(&self, addr: u32, n: usize) -> Option<&[u8]> {
        let addr = self.locate(addr)?;
        let seg = self
            .segments
            .iter()
            .find(|s| addr >= s.start && addr < s.start + s.size)?;
        let offset = seg.ooffs? + (addr - seg.start) as usize;
        self.rom.get(offset..offset + n)
    }

    pub fn operand(&self, insn: &Insn) -> u32 {
        let mut v = 0;
        for i in (1..insn.len as usize).rev() {
            v = v << 8 | self.rom[insn.offset + i] as u32;
        }
        v
    }

    /// The label right at an address, if there is one.
    pub fn label(&self, addr: u32) -> Option<&str> {
        self.labels.get(&addr).map(String::as_str)
    }

    /// The first label after an address: where a table that starts there
    /// ends, at the latest.
    pub fn next_label(&self, addr: u32) -> Option<u32> {
        self.labels.range(addr + 1..).next().map(|(&a, _)| a)
    }

    /// The routine an address is in: the last label outside any `.proc`
    /// at or before it.
    pub fn routine(&self, addr: u32) -> &str {
        self.routines
            .range(..=addr)
            .next_back()
            .map(|(_, n)| n.as_str())
            .unwrap_or("?")
    }

    /// A name for an address in messages: its label, or the routine and how
    /// far into it.
    pub fn name(&self, addr: u32) -> String {
        if let Some(l) = self.label(addr) {
            return l.to_string();
        }
        match self.routines.range(..=addr).next_back() {
            Some((&a, n)) => format!("{}+{}", n, addr - a),
            None => format!("${:06X}", addr),
        }
    }

    /// Whether a line of a source file put any bytes in the ROM. One that
    /// did not may be one an `.if` left out of this program.
    pub fn assembles(&self, file: &str, line: u32) -> bool {
        self.files
            .iter()
            .filter(|(_, name)| name.as_str() == file)
            .any(|(&id, _)| self.assembled.contains(&(id, line)))
    }

    /// The file and line number an instruction came from.
    pub fn place(&self, insn: &Insn) -> Option<(&str, u32)> {
        let (file, line) = *self.lines.get(&insn.line?)?;
        Some((self.files.get(&file)?.as_str(), line))
    }

    /// The file and line number of any address: the instruction that starts
    /// there, or the data it is in.
    pub fn place_of(&self, addr: u32) -> Option<(&str, u32)> {
        if let Some(insn) = self.insns.get(&addr) {
            return self.place(insn);
        }
        let start = self
            .data_at(addr)
            .and(self.data.range(..=addr).next_back().map(|(&a, _)| a))?;
        let (file, line) = *self.lines.get(self.data_lines.get(&start)?)?;
        Some((self.files.get(&file)?.as_str(), line))
    }

    /// An instruction that starts where the debug file has none —inside
    /// data, as in the `.byte $2C` that makes a `bit abs` swallow the next
    /// instruction—, read from the ROM with the widths given. It is what the
    /// CPU does when it gets there.
    pub fn decode_at(&self, addr: u32, m8: bool, x8: bool) -> Option<Insn> {
        let addr = self.locate(addr)?;
        let op = *self.bytes(addr, 1)?.first()?;
        let len = cpu::length(op, m8, x8);
        self.bytes(addr, len as usize)?;
        let seg = self
            .segments
            .iter()
            .find(|s| addr >= s.start && addr < s.start + s.size)?;
        let offset = seg.ooffs? + (addr - seg.start) as usize;
        Some(Insn {
            addr,
            offset,
            op,
            len,
            line: None,
            macro_line: None,
        })
    }

    fn declared_at(&self, file: usize, line: u32) -> Widths {
        self.declared
            .at
            .get(&(file, line))
            .copied()
            .unwrap_or_default()
    }

    /// The widths the source declares where the instruction is.
    pub fn declared(&self, insn: &Insn) -> Widths {
        let at_line = match insn.line.and_then(|l| self.lines.get(&l)) {
            Some(&(file, line)) => self.declared_at(file, line),
            None => Widths::default(),
        };
        // From a macro: as it was where it is used, with what its body
        // changed before the line.
        if let Some(&(file, line)) = insn.macro_line.and_then(|l| self.lines.get(&l)) {
            if let Some(body) = self.declared.macro_lines.get(&(file, line)) {
                return Widths {
                    m8: body.m8.or(at_line.m8),
                    x8: body.x8.or(at_line.x8),
                };
            }
        }
        if let Some(&w) = self.expanded.get(&insn.addr) {
            return w;
        }
        at_line
    }

    /// What the source could not tell: missing `.include`s.
    pub fn missing_sources(&self) -> &[String] {
        &self.declared.missing
    }

    /// The immediates whose size disagrees with the widths read from the
    /// source: where that reading goes wrong. Each one is a line where the
    /// width checks would be working from a wrong declaration.
    pub fn width_disagreements(&self) -> Vec<String> {
        let mut out = Vec::new();
        for insn in self.insns.values() {
            let declared = self.declared(insn);
            let (said, assembled) = match cpu::mode(insn.op) {
                cpu::Mode::ImmM => (declared.m8, insn.len == 2),
                cpu::Mode::ImmX => (declared.x8, insn.len == 2),
                _ => continue,
            };
            if said.is_some_and(|s| s != assembled) {
                if let Some((file, line)) = self.place(insn) {
                    out.push(format!("{}:{}", file, line));
                }
            }
        }
        out
    }
}
