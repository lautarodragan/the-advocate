//! The assembler proper: read the source, place every piece, emit the image.
//!
//! Two passes. The first reads the source and builds a list of pieces per
//! segment, without knowing where any of them will land. The second gives
//! each piece an offset —and with that, each label an address— and only then
//! resolves the expressions and writes the bytes.
//!
//! The split is what makes a forward reference work, and it is also why the
//! errors come in two flavours: the ones the first pass finds carry the line
//! they were read from, and the ones the second pass finds —a branch that
//! ended up too far, an operand that does not fit— carry the line the piece
//! came from, which is kept for exactly that reason.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::rc::Rc;

use crate::expr::{Error, Expression, Result, Symbols};
use crate::layout::{self, AREAS, BANK_SIZE, RAM_AREAS, ROM_BANKS, SEGMENTS, ZP_SEGMENT};
use crate::opcodes;

fn bad(message: String) -> Error {
    Error(message)
}

// --- the pieces that pile up ------------------------------------------------

/// One entry of a `.byte`/`.word`/`.addr`/`.dword` list.
enum Part {
    /// A quoted string, already turned into bytes.
    Bytes(Vec<u8>),
    /// A literal, folded at parse time: most of a generated data file is this
    /// and nothing else, and keeping a parser per byte is not free.
    Literal(i64, u8),
    Expr(Expression, u8),
}

impl Part {
    fn size(&self) -> u32 {
        match self {
            Part::Bytes(b) => b.len() as u32,
            Part::Literal(_, width) | Part::Expr(_, width) => *width as u32,
        }
    }
}

enum Kind {
    /// Literal bytes, or expressions of a fixed width once they are placed.
    Data(Vec<Part>),
    Instruction { opcode: u8, expression: Option<Expression>, width: u8, relative: bool },
    /// Padding so that what follows starts at an address that is a multiple of
    /// `unit`. It is needed when something will read words out of a table with
    /// a 24-bit pointer: if the table started at an odd address, one of its
    /// words would fall right between the `$FFFF` of one bank and the `$8000`
    /// of the next, and that read would bring a byte from each side.
    Align { unit: i64 },
    /// Padding so that what follows does not cross a bank boundary.
    ///
    /// A DMA walks its source address linearly, and in LoROM the byte after
    /// `$02FFFF` is not the ROM of bank 3 but the RAM: any block uploaded by
    /// DMA that crosses that boundary reads garbage from there on.
    ///
    /// Whoever emits the data declares it, because it is the only one that
    /// knows how big the block will be. How much has to be padded is worked
    /// out while placing, which is when it is known where it landed.
    ///
    /// **On its way out.** A linker cannot place variable-size blocks, so the
    /// padding is now worked out upstream, by whoever generates the data: what
    /// reaches this assembler is a plain `.res`. What is left are the blocks
    /// written by hand *after* the generated ones in the same segment, whose
    /// offset the generator cannot know. Those need either a segment of their
    /// own, aligned by the memory map, or a layout that puts them first.
    BankFit { needed: i64 },
    /// Space reserved in RAM: it takes up room but is not written to the ROM.
    Reserve,
}

struct Item {
    kind: Kind,
    size: u32,
    /// Which line this came from. Not used while reading —there the error is
    /// caught on the spot— but while emitting, which is a separate pass.
    origin: Rc<str>,
}

// --- the assembler ----------------------------------------------------------

pub struct Assembler {
    checksum: bool,
    include: Vec<PathBuf>,
    items: Vec<Vec<Item>>,
    segment: usize,
    origin: Rc<str>,
    symbols: Symbols,
    /// (segment, index of the item, name) of every label, so that the second
    /// pass can turn each into an address.
    pending: Vec<(usize, usize, String)>,
    /// So that a repeated one does not go unnoticed.
    defined: HashSet<String>,
    /// Names that live in the direct page.
    zeropage: HashSet<String>,
    /// The `.proc` in progress, for the local labels.
    scope: String,
    /// (segment, index) of every `:`.
    anonymous: Vec<(usize, usize)>,
    /// The `:+` / `:-` references still to resolve, each naming the item whose
    /// operand it is.
    anon_refs: Vec<AnonRef>,
    /// The width in force for the accumulator and for X/Y.
    a16: bool,
    i16: bool,
    /// Which declared width each label was defined with, and which one each
    /// branch arrives with. They are compared at the end: see [`Assembler::check_widths`].
    label_width: HashMap<String, (bool, bool, Rc<str>)>,
    branches: Vec<Branch>,
    /// The labels defined since the last byte was emitted. An `.a8` right
    /// behind a label talks about that label, not about the code above it:
    /// without this, `not_above:` followed by `.a8` was recorded with the
    /// width that was in force before and the check complained about
    /// something that was right.
    fresh_labels: Vec<String>,
    addresses: Vec<Vec<i64>>,
}

struct AnonRef {
    text: String,
    segment: usize,
    index: usize,
}

struct Branch {
    mnemonic: String,
    target: String,
    scope: String,
    a16: bool,
    i16: bool,
    origin: Rc<str>,
}

impl Assembler {
    pub fn new(checksum: bool, include: &[PathBuf]) -> Assembler {
        Assembler {
            checksum,
            include: include.iter().map(absolute).collect(),
            items: SEGMENTS.iter().map(|_| Vec::new()).collect(),
            segment: layout::segment_index("CODE").unwrap(),
            origin: Rc::from("?"),
            symbols: Symbols::new(),
            pending: Vec::new(),
            defined: HashSet::new(),
            zeropage: HashSet::new(),
            scope: String::new(),
            anonymous: Vec::new(),
            anon_refs: Vec::new(),
            a16: false,
            i16: false,
            label_width: HashMap::new(),
            branches: Vec::new(),
            fresh_labels: Vec::new(),
            addresses: Vec::new(),
        }
    }

    pub fn assemble(&mut self, path: &Path) -> Result<Vec<u8>> {
        self.read(path)?;
        self.check_widths()?;
        self.place()?;
        self.emit()
    }

    /// The symbol table, for whoever wants to write it out.
    pub fn symbols(&self) -> &Symbols {
        &self.symbols
    }

    // --- pass 1: read the source and place every piece ---

    /// Where a `.include` is: the -I directories first, the source's own
    /// directory afterwards.
    ///
    /// The -I directories go first on purpose. That is what makes it possible
    /// to assemble against a generated include that is not the one in the
    /// tree —one just produced into a run's own directory— without trampling
    /// the one another run is using.
    fn find(&self, name: &str, directory: &Path) -> Result<PathBuf> {
        let mut places: Vec<&Path> = self.include.iter().map(PathBuf::as_path).collect();
        places.push(directory);
        for base in &places {
            let candidate = base.join(name);
            if candidate.exists() {
                return Ok(candidate);
            }
        }
        let looked: Vec<String> = places.iter().map(|p| p.display().to_string()).collect();
        Err(bad(format!("cannot find {name:?}; looked in {}", looked.join(", "))))
    }

    fn read(&mut self, path: &Path) -> Result<()> {
        let directory = absolute(path).parent().unwrap_or(Path::new(".")).to_path_buf();
        let text = std::fs::read_to_string(path)
            .map_err(|e| bad(format!("{}: {e}", path.display())))?;

        for (number, raw) in text.lines().enumerate() {
            let line = raw.split(';').next().unwrap_or("").trim();
            if line.is_empty() {
                continue;
            }
            self.origin = Rc::from(format!("{}:{}: {}", path.display(), number + 1, line).as_str());
            if let Err(error) = self.line(line, &directory) {
                let origin = Rc::clone(&self.origin);
                return Err(bad(format!("{error}\n  at {origin}")));
            }
        }
        Ok(())
    }

    fn line(&mut self, line: &str, directory: &Path) -> Result<()> {
        // Labels: they can come on their own or with an instruction behind.
        let mut line = line;
        loop {
            if let Some((name, rest)) = split_label(line) {
                self.label(name)?;
                line = rest;
                continue;
            }
            if let Some(rest) = line.strip_prefix(':') {
                self.anonymous.push((self.segment, self.items[self.segment].len()));
                line = rest.trim();
                continue;
            }
            break;
        }
        if line.is_empty() {
            return Ok(());
        }

        if line.starts_with('.') {
            return self.directive(line, directory);
        }

        if let Some((name, rest)) = split_assignment(line) {
            let value = Expression::new(rest)?.value(&self.symbols)?;
            // A repeated constant is an error just like a repeated label, and
            // for the same reason: the last one used to win in silence.
            // Redefining it with the same value is allowed: generated includes
            // declare constants the source may also have, and there there is
            // no ambiguity.
            if let Some(Some(previous)) = self.symbols.get(name) {
                if *previous != value {
                    return Err(bad(format!(
                        "the constant {name:?} was already {previous} and here it is {value} ({})",
                        self.origin
                    )));
                }
            }
            self.symbols.insert(name.to_string(), Some(value));
            return Ok(());
        }

        self.instruction(line)
    }

    fn label(&mut self, name: &str) -> Result<()> {
        let full = if self.scope.is_empty() {
            name.to_string()
        } else {
            format!("{}{name}", self.scope)
        };
        // A repeated label is always an error, and it used to pass in
        // silence: both ended up pending and the last one won. The name
        // carries the `.proc` in front, so two `loop:` in different
        // procedures are still two different labels.
        if self.defined.contains(&full) {
            return Err(bad(format!(
                "the label {full:?} is defined twice ({})",
                self.origin
            )));
        }
        self.defined.insert(full.clone());
        self.label_width
            .insert(full.clone(), (self.a16, self.i16, Rc::clone(&self.origin)));
        self.fresh_labels.push(full.clone());
        self.pending
            .push((self.segment, self.items[self.segment].len(), full.clone()));
        if SEGMENTS[self.segment] == ZP_SEGMENT {
            self.zeropage.insert(full);
        }
        Ok(())
    }

    fn directive(&mut self, line: &str, directory: &Path) -> Result<()> {
        let mut parts = line.splitn(2, char::is_whitespace);
        let name = parts.next().unwrap_or("").to_ascii_lowercase();
        let rest = parts.next().unwrap_or("").trim();

        match name.as_str() {
            // A condition that has to hold while assembling. It exists to tie
            // a hand-written sum to the constant it depends on: a routine
            // multiplying by twelve with two shifts and an add agreed with the
            // constant until the constant grew and nobody noticed.
            ".controlar" => {
                let (condition, note) = match rest.split_once(',') {
                    Some((c, n)) => (c, Some(n.trim().trim_matches('"'))),
                    None => (rest, None),
                };
                let (left, right) = condition
                    .split_once('=')
                    .ok_or_else(|| bad(".controlar wants `expression = expression`".into()))?;
                if right.is_empty() {
                    return Err(bad(".controlar wants `expression = expression`".into()));
                }
                let a = Expression::new(left)?.value(&self.symbols)?;
                let b = Expression::new(right)?.value(&self.symbols)?;
                if a != b {
                    return Err(bad(format!(
                        "{} is {a} and {} is {b}{}",
                        left.trim(),
                        right.trim(),
                        note.map(|n| format!(": {n}")).unwrap_or_default()
                    )));
                }
                Ok(())
            }
            ".p816" | ".smart" | ".setcpu" | ".feature" => Ok(()),
            ".endproc" => {
                self.scope.clear();
                Ok(())
            }
            ".a8" | ".a16" | ".i8" | ".i16" => {
                match name.as_str() {
                    ".a8" => self.a16 = false,
                    ".a16" => self.a16 = true,
                    ".i8" => self.i16 = false,
                    _ => self.i16 = true,
                }
                self.relabel_widths();
                Ok(())
            }
            ".segment" => {
                let wanted = rest.trim_matches('"');
                self.segment = layout::segment_index(wanted)
                    .ok_or_else(|| bad(format!("unknown segment: {wanted}")))?;
                Ok(())
            }
            ".proc" => {
                self.label(rest)?;
                self.scope = format!("{rest}::");
                Ok(())
            }
            ".include" => {
                let found = self.find(rest.trim_matches('"'), directory)?;
                self.read(&found)
            }
            ".bloque" => {
                let needed = Expression::new(rest)?.value(&self.symbols)?;
                self.add(Kind::BankFit { needed }, 0);
                Ok(())
            }
            ".alinear" => {
                let unit = Expression::new(rest)?.value(&self.symbols)?;
                if unit <= 0 {
                    return Err(bad(format!(".alinear wants a positive unit, not {unit}")));
                }
                self.add(Kind::Align { unit }, 0);
                Ok(())
            }
            ".res" => {
                let size = Expression::new(rest)?.value(&self.symbols)?;
                if size < 0 {
                    return Err(bad(format!(".res wants a size that is not negative, not {size}")));
                }
                self.add(Kind::Reserve, size as u32);
                Ok(())
            }
            ".byte" | ".word" | ".addr" | ".dword" => {
                let width: u8 = match name.as_str() {
                    ".byte" => 1,
                    ".dword" => 4,
                    _ => 2,
                };
                let parts = self.data(rest, width)?;
                let size = parts.iter().map(Part::size).sum();
                self.add(Kind::Data(parts), size);
                Ok(())
            }
            _ => Err(bad(format!("there is no directive {name}"))),
        }
    }

    fn data(&mut self, rest: &str, width: u8) -> Result<Vec<Part>> {
        let mut parts = Vec::new();
        for piece in split_commas(rest) {
            let piece = piece.trim();
            if piece.starts_with('"') {
                parts.push(Part::Bytes(latin1(unquote(piece))?));
            } else {
                let expression = Expression::new(piece)?;
                match expression.as_literal() {
                    Some(value) => parts.push(Part::Literal(value, width)),
                    None => parts.push(Part::Expr(expression, width)),
                }
            }
        }
        Ok(parts)
    }

    fn instruction(&mut self, line: &str) -> Result<()> {
        let (mnemonic, operand) =
            split_instruction(line).ok_or_else(|| bad("cannot read the instruction".into()))?;
        let mnemonic = mnemonic.to_ascii_lowercase();

        if let Some(opcode) = opcodes::implied(&mnemonic) {
            if !operand.is_empty() {
                return Err(bad(format!("{mnemonic} takes no operand")));
            }
            self.add(Kind::Instruction { opcode, expression: None, width: 0, relative: false }, 1);
            return Ok(());
        }

        if let Some(opcode) = opcodes::branch(&mnemonic) {
            let target = self.target(operand)?;
            self.branches.push(Branch {
                mnemonic: mnemonic.clone(),
                target: operand.trim().to_string(),
                scope: self.scope.clone(),
                a16: self.a16,
                i16: self.i16,
                origin: Rc::clone(&self.origin),
            });
            self.add(
                Kind::Instruction { opcode, expression: Some(target), width: 1, relative: true },
                2,
            );
            return Ok(());
        }

        let modes = opcodes::modes_of(&mnemonic)
            .ok_or_else(|| bad(format!("there is no instruction {mnemonic}")))?;
        let (mode, expression) = self.decode(operand, modes)?;
        let opcode = opcodes::code_of(modes, &mode)
            .ok_or_else(|| bad(format!("{mnemonic} does not take the mode {mode}")))?;
        let width = if mode == "imm" {
            let wide = if opcodes::uses_index_width(&mnemonic) { self.i16 } else { self.a16 };
            if wide {
                2
            } else {
                1
            }
        } else {
            opcodes::operand_width(&mode)
                .ok_or_else(|| bad(format!("the operand of mode {mode} has no known size")))?
        };
        self.add(
            Kind::Instruction { opcode, expression, width, relative: false },
            1 + width as u32,
        );
        Ok(())
    }

    /// Which addressing mode this operand asks for.
    fn decode(&mut self, operand: &str, modes: opcodes::Modes) -> Result<(String, Option<Expression>)> {
        if operand.is_empty() || operand.eq_ignore_ascii_case("a") {
            return Ok(("acc".to_string(), None));
        }

        // The indexed modes are recognised by their suffix. That comes after
        // looking at the immediate and the indirects, which do not carry one.
        let mut operand = operand;
        let mut index = "";
        if !operand.starts_with('#') && !operand.ends_with(']') && !operand.ends_with(')') {
            if let Some((head, letter)) = split_index(operand) {
                operand = head;
                index = letter;
            }
        }

        if let Some(rest) = operand.strip_prefix('#') {
            let mode = if opcodes::has_mode(modes, "imm8") { "imm8" } else { "imm" };
            return Ok((mode.to_string(), Some(Expression::new(rest)?)));
        }
        // The indirects carry the index glued to the mode, not apart: `[dp]`
        // and `[dp],y` are different opcodes. If the index were dropped here,
        // a `lda [ptr],y` would assemble as `lda [ptr]` without saying
        // anything, which is exactly the class of error this assembler exists
        // not to have. It is handed to the mode, and let it fail if it does
        // not exist.
        if operand.starts_with('[') && operand.ends_with(']') {
            let inner = &operand[1..operand.len() - 1];
            return Ok((format!("dpil{index}"), Some(self.target(inner)?)));
        }
        if operand.starts_with('(') && operand.ends_with(')') {
            let inner = &operand[1..operand.len() - 1];
            return Ok((format!("dpi{index}"), Some(self.target(inner)?)));
        }

        // The long mode, with its prefix: `lda f:$7E30A0`. The address carries
        // the bank, so it does not depend on the data bank register. It exists
        // for code that runs inside an interrupt and reads state from far
        // memory, where a windowed access cannot be used because the interrupt
        // would land in the middle of someone else's walk and move the
        // pointer.
        if operand.len() >= 2 && operand[..2].eq_ignore_ascii_case("f:") {
            return Ok((format!("long{index}"), Some(self.target(&operand[2..])?)));
        }

        let expression = self.target(operand)?;
        // Direct page in two cases: the symbol lives in the ZEROPAGE segment,
        // or the expression can already be worked out and fits in a byte. A
        // label that is not defined yet cannot be judged, so it goes as
        // absolute, which is what a forward reference gets.
        let direct = match expression.base_name() {
            Some(base) if self.zeropage.contains(base) => true,
            _ => matches!(expression.value(&self.symbols), Ok(value) if value < 0x100),
        };
        let mode = if direct && opcodes::has_mode(modes, &format!("dp{index}")) {
            "dp"
        } else {
            "abs"
        };
        Ok((format!("{mode}{index}"), Some(expression)))
    }

    /// An expression, resolving the scope of the local labels.
    fn target(&mut self, text: &str) -> Result<Expression> {
        let text = text.trim();
        if is_anonymous_reference(text) {
            self.anon_refs.push(AnonRef {
                text: text.to_string(),
                segment: self.segment,
                index: self.items[self.segment].len(),
            });
            return Ok(Expression::number(0));
        }
        let mut expression = Expression::new(text)?;
        if expression.base_name().is_some() && !self.scope.is_empty() {
            // Inside a `.proc`, a label may be local; that is decided on the
            // second pass, when they all exist. Here only the scope is noted.
            expression.scope = Some(self.scope.clone());
        }
        Ok(expression)
    }

    /// The width of the labels that have not emitted anything yet.
    fn relabel_widths(&mut self) {
        for name in &self.fresh_labels {
            if let Some(entry) = self.label_width.get_mut(name) {
                entry.0 = self.a16;
                entry.1 = self.i16;
            }
        }
    }

    fn add(&mut self, kind: Kind, size: u32) {
        self.items[self.segment].push(Item { kind, size, origin: Rc::clone(&self.origin) });
        self.fresh_labels.clear();
    }

    /// That every branch reaches its label with the width the label declares.
    ///
    /// This is the check for the trap that cost most in this design, because
    /// nobody sees it: the width set by `sep`/`rep` is tracked **in reading
    /// order**, so a label reached by a branch that skips the width change is
    /// recorded with the width of the fall-through path, not of the branch.
    /// The `cmp #2` that follows is then emitted with a two byte immediate,
    /// the CPU in eight bit mode reads only one, and the second —usually the
    /// `$00` of the high byte— is executed as BRK.
    ///
    /// It does not show in a diff and it does not show in a pixel comparison
    /// —the image wanders off and draws anything at all— and it can only be
    /// found by bisecting. Here it comes out as an error with a name and a
    /// line.
    ///
    /// Only relative branches are looked at. A `jsr` does not count: there the
    /// procedure declares the width it wants to be called with, which is a
    /// convention and not an error.
    fn check_widths(&self) -> Result<()> {
        for branch in &self.branches {
            if !is_plain_label(&branch.target) {
                continue; // `:+`, an expression: not a label
            }
            let qualified = format!("{}{}", branch.scope, branch.target);
            let name = if self.label_width.contains_key(&qualified) {
                qualified
            } else {
                branch.target.clone()
            };
            let Some(declared) = self.label_width.get(&name) else { continue };
            if (branch.a16, branch.i16) != (declared.0, declared.1) {
                return Err(bad(format!(
                    "{} {} branches with the accumulator at {} and the index registers at {}, \
                     and the label is declared with {} and {} ({}).\n  \
                     If the branch skips a sep/rep, the label is missing an .a8/.a16/.i8/.i16 \
                     saying which width it is reached with.\n  at {}",
                    branch.mnemonic,
                    branch.target,
                    width_of(branch.a16),
                    width_of(branch.i16),
                    width_of(declared.0),
                    width_of(declared.1),
                    declared.2,
                    branch.origin
                )));
            }
        }
        Ok(())
    }

    // --- pass 2: place and emit ---

    /// Gives every piece an address, and with that every label one.
    fn place(&mut self) -> Result<()> {
        self.addresses = self.items.iter().map(|s| vec![0i64; s.len() + 1]).collect();

        for area in AREAS {
            let mut offset = area.start;
            for name in area.segments {
                let segment = layout::segment_index(name).expect("declared segment");
                for index in 0..self.items[segment].len() {
                    let item = &mut self.items[segment][index];
                    match item.kind {
                        // If the block that follows does not fit in what is
                        // left of the bank, pad up to the next one.
                        Kind::BankFit { needed } => {
                            let left = (BANK_SIZE - offset % BANK_SIZE) as i64;
                            item.size = if needed > left { left as u32 } else { 0 };
                        }
                        Kind::Align { unit } => {
                            item.size = ((unit - offset as i64 % unit) % unit) as u32;
                        }
                        _ => {}
                    }
                    let size = item.size;
                    self.addresses[segment][index] = layout::lorom_address(offset);
                    offset += size;
                }
                let end = self.items[segment].len();
                self.addresses[segment][end] = layout::lorom_address(offset);
            }
            if offset > area.start + area.size {
                return Err(bad(format!(
                    "the area does not fit: {} bytes in {}",
                    offset - area.start,
                    area.size
                )));
            }
        }

        // The RAM is handed out just like the ROM, and with the same check
        // that it fits. It did not have one, and that was not theoretical: the
        // zero page came to 260 bytes, so its last variables landed on top of
        // the stack and the start of the BSS. Nothing said so.
        for area in RAM_AREAS {
            let mut address = area.start;
            for name in area.segments {
                let segment = layout::segment_index(name).expect("declared segment");
                for index in 0..self.items[segment].len() {
                    self.addresses[segment][index] = address as i64;
                    address += self.items[segment][index].size;
                }
                let end = self.items[segment].len();
                self.addresses[segment][end] = address as i64;
            }
            if address > area.start + area.size {
                let stack = if area.name == "RAM" {
                    format!(" (and {} more reserved for the stack)", layout::STACK_RESERVE)
                } else {
                    String::new()
                };
                return Err(bad(format!(
                    "{} does not fit: {} bytes in {}{stack}",
                    area.name,
                    address - area.start,
                    area.size
                )));
            }
        }

        for (segment, index, name) in &self.pending {
            self.symbols.insert(name.clone(), Some(self.addresses[*segment][*index]));
        }

        // The anonymous labels: `:+` is the next one forwards, `:-` the
        // previous one. They are ordered by position inside their segment.
        let mut spots = self.anonymous.clone();
        spots.sort();
        for reference in &self.anon_refs {
            let forward = reference.text.as_bytes()[1] == b'+';
            let count = reference.text.len() - 1;
            let mut candidates: Vec<(usize, usize)> = spots
                .iter()
                .copied()
                .filter(|(segment, index)| {
                    *segment == reference.segment
                        && if forward { *index > reference.index } else { *index <= reference.index }
                })
                .collect();
            if !forward {
                candidates.reverse();
            }
            if candidates.len() < count {
                return Err(bad(format!("cannot find the anonymous label {}", reference.text)));
            }
            let (segment, index) = candidates[count - 1];
            let address = self.addresses[segment][index];
            let item = &mut self.items[reference.segment][reference.index];
            if let Kind::Instruction { expression: Some(expression), .. } = &mut item.kind {
                *expression = Expression::number(address);
            }
        }

        // The local labels of each .proc win over the global ones.
        let qualified: Vec<String> = self
            .symbols
            .keys()
            .filter(|name| name.contains("::"))
            .cloned()
            .collect();
        for name in qualified {
            let plain = name.rsplit("::").next().unwrap().to_string();
            self.symbols.entry(plain).or_insert(None);
        }
        Ok(())
    }

    /// The bytes of the image, each piece written at its own offset.
    fn emit(&self) -> Result<Vec<u8>> {
        let mut rom = vec![0u8; (BANK_SIZE * ROM_BANKS) as usize];
        for area in AREAS {
            let mut offset = area.start;
            for name in area.segments {
                let segment = layout::segment_index(name).expect("declared segment");
                for (index, item) in self.items[segment].iter().enumerate() {
                    let data = self.emit_item(item, self.addresses[segment][index]).map_err(
                        |error| bad(format!("{error}\n  at {}", item.origin)),
                    )?;
                    let at = offset as usize;
                    rom[at..at + data.len()].copy_from_slice(&data);
                    offset += item.size;
                }
            }
        }
        if self.checksum {
            layout::checksum(&mut rom).map_err(bad)?;
        }
        Ok(rom)
    }

    fn emit_item(&self, item: &Item, address: i64) -> Result<Vec<u8>> {
        match &item.kind {
            Kind::Instruction { opcode, expression: None, .. } => Ok(vec![*opcode]),
            Kind::Instruction { opcode, expression: Some(expression), width, relative } => {
                let value = expression.value(&self.symbols)?;
                encode(*opcode, value, *width, *relative, address, item.size as i64)
            }
            Kind::Data(parts) => {
                let mut out = Vec::with_capacity(item.size as usize);
                for part in parts {
                    match part {
                        Part::Bytes(bytes) => out.extend_from_slice(bytes),
                        Part::Literal(value, width) => push_le(&mut out, *value, *width),
                        Part::Expr(expression, width) => {
                            push_le(&mut out, expression.value(&self.symbols)?, *width)
                        }
                    }
                }
                Ok(out)
            }
            _ => Ok(vec![0u8; item.size as usize]),
        }
    }
}

/// The bytes of an instruction with its operand already resolved.
fn encode(opcode: u8, mut value: i64, width: u8, relative: bool, address: i64, size: i64) -> Result<Vec<u8>> {
    if relative {
        // The branch is counted from the byte after the instruction.
        value -= address + size;
        if !(-128..=127).contains(&value) {
            return Err(bad(format!("branch too far: {value} bytes")));
        }
        value &= 0xFF;
    } else {
        let bits = 8 * width as u32;
        // An operand that does not fit its mode is an error, not a silent
        // truncation. The case that motivated it: an indirect long through a
        // variable that did not live in the direct page. That mode addresses
        // the direct page only, so the assembler emitted the low byte of
        // $0129 and the image read the pointer from $0029, which is another
        // variable. Everything compiled and the screen said something was
        // wrong without saying where.
        //
        // Negatives fit: `lda #-SPEED` is two's complement and a normal way
        // to write it.
        let low = -(1i64 << (bits - 1));
        let high = 1i64 << bits;
        if value < low || value >= high {
            // A `jsr` or a `jmp` to a label **in the same bank** is the
            // legitimate case: both instructions change only the cursor, so
            // their operand is the low word and the bank is supplied by
            // whichever one is already running. This assembler's labels always
            // carry the full 24-bit address, which is what a `jml` or a
            // `lda f:` needs. It is what a linker does; what is **not**
            // accepted is a jump to another bank, which stays an error and is
            // the one that would break without warning.
            if width == 2 && value >= 0 && (value >> 16) == (address >> 16) {
                value &= 0xFFFF;
            } else {
                return Err(bad(format!(
                    "the operand does not fit in {width} byte(s): {value}. If it is a direct \
                     page mode, the variable has to live in the ZEROPAGE segment"
                )));
            }
        }
    }
    let mut out = vec![opcode];
    push_le(&mut out, value, width);
    Ok(out)
}

fn push_le(out: &mut Vec<u8>, value: i64, width: u8) {
    let mask = if width >= 8 { !0u64 } else { (1u64 << (8 * width as u32)) - 1 };
    let masked = (value as u64) & mask;
    out.extend_from_slice(&masked.to_le_bytes()[..width as usize]);
}

fn width_of(wide: bool) -> u32 {
    if wide {
        16
    } else {
        8
    }
}

fn absolute(path: impl AsRef<Path>) -> PathBuf {
    let path = path.as_ref();
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")).join(path)
    }
}

// --- reading the shapes a line can have -------------------------------------

/// `name:` at the start of a line, and whatever comes after it.
fn split_label(line: &str) -> Option<(&str, &str)> {
    let bytes = line.as_bytes();
    let first = *bytes.first()?;
    if !(first.is_ascii_alphabetic() || first == b'_' || first == b'@') {
        return None;
    }
    let mut end = 1;
    while end < bytes.len() && (bytes[end].is_ascii_alphanumeric() || bytes[end] == b'_') {
        end += 1;
    }
    if bytes.get(end) != Some(&b':') {
        return None;
    }
    Some((&line[..end], line[end + 1..].trim()))
}

/// `NAME = expression`, which is how a constant is declared.
fn split_assignment(line: &str) -> Option<(&str, &str)> {
    let bytes = line.as_bytes();
    let first = *bytes.first()?;
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return None;
    }
    let mut end = 1;
    while end < bytes.len() && (bytes[end].is_ascii_alphanumeric() || bytes[end] == b'_') {
        end += 1;
    }
    let name = &line[..end];
    let rest = &line[end..];
    let rest = rest.trim_start();
    let rest = rest.strip_prefix('=')?.trim_start();
    if rest.is_empty() {
        return None;
    }
    Some((name, rest))
}

/// A mnemonic, and its operand if there is one.
fn split_instruction(line: &str) -> Option<(&str, &str)> {
    let bytes = line.as_bytes();
    let mut end = 0;
    while end < bytes.len() && bytes[end].is_ascii_alphabetic() {
        end += 1;
    }
    if end == 0 {
        return None;
    }
    if end == bytes.len() {
        return Some((line, ""));
    }
    if !(bytes[end] as char).is_ascii_whitespace() {
        return None;
    }
    Some((&line[..end], line[end..].trim()))
}

/// The `, x` / `, y` suffix of an indexed mode, if the operand ends in one.
fn split_index(operand: &str) -> Option<(&str, &'static str)> {
    for (at, c) in operand.char_indices() {
        if c != ',' {
            continue;
        }
        let rest = operand[at + 1..].trim_start();
        let letter = match rest {
            "x" | "X" => "x",
            "y" | "Y" => "y",
            _ => continue,
        };
        return Some((operand[..at].trim_end(), letter));
    }
    None
}

fn is_anonymous_reference(text: &str) -> bool {
    let Some(rest) = text.strip_prefix(':') else { return false };
    !rest.is_empty() && rest.bytes().all(|b| b == b'+' || b == b'-')
}

fn is_plain_label(text: &str) -> bool {
    let bytes = text.as_bytes();
    let Some(first) = bytes.first() else { return false };
    if !(first.is_ascii_alphabetic() || *first == b'_' || *first == b'@') {
        return false;
    }
    bytes[1..].iter().all(|b| b.is_ascii_alphanumeric() || *b == b'_')
}

/// Splits on commas without breaking the ones inside quotes.
fn split_commas(text: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    for c in text.chars() {
        if c == '"' {
            quoted = !quoted;
        }
        if c == ',' && !quoted {
            parts.push(std::mem::take(&mut current));
        } else {
            current.push(c);
        }
    }
    if !current.trim().is_empty() {
        parts.push(current);
    }
    parts
}

/// Drops the quotes around a string literal, without looking at what is
/// between them: there are no escapes.
fn unquote(piece: &str) -> String {
    let mut chars: Vec<char> = piece.chars().collect();
    if chars.len() >= 2 {
        chars.pop();
    }
    if !chars.is_empty() {
        chars.remove(0);
    }
    chars.into_iter().collect()
}

/// A string literal is written out one byte per character. Anything the source
/// file spells that does not have a single byte is refused rather than
/// silently turned into two.
fn latin1(text: String) -> Result<Vec<u8>> {
    text.chars()
        .map(|c| {
            u8::try_from(c as u32)
                .map_err(|_| bad(format!("{c:?} does not fit in a byte of a string")))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    /// Assembles a source written inline and hands back the image.
    fn assemble(source: &str) -> Result<Vec<u8>> {
        assemble_in(&[("main.s", source)], "main.s")
    }

    /// Assembles a little tree of files written to a temporary directory.
    fn assemble_in(files: &[(&str, &str)], entry: &str) -> Result<Vec<u8>> {
        let dir = std::env::temp_dir().join(format!(
            "w65-test-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        for (name, text) in files {
            let mut f = std::fs::File::create(dir.join(name)).unwrap();
            f.write_all(text.as_bytes()).unwrap();
        }
        let out = Assembler::new(false, &[]).assemble(&dir.join(entry));
        let _ = std::fs::remove_dir_all(&dir);
        out
    }

    /// The first bytes of the CODE segment, which is where a bare source
    /// lands.
    fn code(rom: &[u8], len: usize) -> Vec<u8> {
        rom[..len].to_vec()
    }

    #[test]
    fn an_implied_instruction_is_one_byte() {
        let rom = assemble("sei\nclc\nrts\n").unwrap();
        assert_eq!(code(&rom, 3), vec![0x78, 0x18, 0x60]);
    }

    #[test]
    fn the_image_is_the_whole_cartridge() {
        let rom = assemble("rts\n").unwrap();
        assert_eq!(rom.len(), (BANK_SIZE * ROM_BANKS) as usize);
    }

    /// The width in force decides how many bytes an immediate takes, and for
    /// the index registers it is a different width from the accumulator's.
    #[test]
    fn an_immediate_follows_the_width_in_force() {
        let rom = assemble(".a8\n.i16\nlda #$12\nldx #$1234\n").unwrap();
        assert_eq!(code(&rom, 5), vec![0xA9, 0x12, 0xA2, 0x34, 0x12]);
    }

    #[test]
    fn rep_and_sep_always_take_one_byte() {
        let rom = assemble(".a16\nrep #$30\nsep #$20\n").unwrap();
        assert_eq!(code(&rom, 4), vec![0xC2, 0x30, 0xE2, 0x20]);
    }

    #[test]
    fn a_zeropage_symbol_picks_the_direct_page_mode() {
        let rom = assemble(
            ".segment \"ZEROPAGE\"\ncursor: .res 2\n.segment \"CODE\"\nlda cursor\n",
        )
        .unwrap();
        assert_eq!(code(&rom, 2), vec![0xA5, 0x00]);
    }

    /// A label of the CODE segment is not in the direct page, so the same
    /// instruction has to come out absolute.
    #[test]
    fn a_code_label_picks_the_absolute_mode() {
        let rom = assemble("table: .byte 1\nlda table\n").unwrap();
        assert_eq!(code(&rom, 4), vec![0x01, 0xAD, 0x00, 0x80]);
    }

    #[test]
    fn the_indirect_long_keeps_its_index() {
        let rom = assemble(
            ".segment \"ZEROPAGE\"\nptr: .res 3\n.segment \"CODE\"\nlda [ptr],y\nlda [ptr]\n",
        )
        .unwrap();
        assert_eq!(code(&rom, 4), vec![0xB7, 0x00, 0xA7, 0x00]);
    }

    #[test]
    fn the_long_mode_is_written_with_the_f_prefix() {
        let rom = assemble("lda f:$7E30A0\n").unwrap();
        assert_eq!(code(&rom, 4), vec![0xAF, 0xA0, 0x30, 0x7E]);
    }

    #[test]
    fn a_branch_is_relative_to_the_byte_after_it() {
        let rom = assemble("here: nop\nbra here\n").unwrap();
        assert_eq!(code(&rom, 3), vec![0xEA, 0x80, 0xFD]);
    }

    #[test]
    fn a_branch_that_cannot_reach_says_how_far_it_missed_by() {
        let error = assemble("here: .res 200\nbra here\n").unwrap_err();
        assert!(error.0.contains("branch too far"), "{error}");
    }

    #[test]
    fn the_anonymous_labels_count_forwards_and_backwards() {
        let rom = assemble("nop\n:\nnop\nbra :-\nbra :+\nnop\n:\nnop\n").unwrap();
        // nop, nop, bra -3, bra +1, nop, nop
        assert_eq!(code(&rom, 8), vec![0xEA, 0xEA, 0x80, 0xFD, 0x80, 0x01, 0xEA, 0xEA]);
    }

    #[test]
    fn a_label_defined_twice_is_refused() {
        let error = assemble("here: nop\nhere: nop\n").unwrap_err();
        assert!(error.0.contains("defined twice"), "{error}");
    }

    /// Inside a `.proc` a label is local, so the same name can be used again
    /// in another one.
    #[test]
    fn two_procs_can_each_have_their_own_loop() {
        let rom = assemble(
            ".proc one\nloop: bra loop\n.endproc\n.proc two\nloop: bra loop\n.endproc\n",
        )
        .unwrap();
        assert_eq!(code(&rom, 4), vec![0x80, 0xFE, 0x80, 0xFE]);
    }

    #[test]
    fn a_label_of_another_proc_cannot_be_reached_from_outside() {
        let error = assemble(".proc one\nloop: nop\n.endproc\njmp loop\n").unwrap_err();
        assert!(error.0.contains("out of scope"), "{error}");
    }

    #[test]
    fn a_symbol_that_does_not_exist_names_itself_and_its_line() {
        let error = assemble("nop\nlda absent\n").unwrap_err();
        assert!(error.0.contains("unknown symbol: absent"), "{error}");
        assert!(error.0.contains("main.s:2"), "{error}");
    }

    #[test]
    fn a_constant_is_usable_in_an_expression() {
        let rom = assemble("WIDTH = 16\n.a8\nlda #WIDTH * 2 + 1\n").unwrap();
        assert_eq!(code(&rom, 2), vec![0xA9, 33]);
    }

    #[test]
    fn a_constant_redefined_with_another_value_is_refused() {
        let error = assemble("W = 1\nW = 2\n").unwrap_err();
        assert!(error.0.contains("was already 1"), "{error}");
    }

    /// Generated includes declare constants the source may also have; the same
    /// value twice is not ambiguous.
    #[test]
    fn a_constant_redefined_with_the_same_value_is_allowed() {
        assemble("W = 1\nW = 1\nnop\n").unwrap();
    }

    #[test]
    fn the_data_directives_write_little_endian() {
        let rom = assemble(".byte $01\n.word $0203\n.addr $0405\n.dword $06070809\n").unwrap();
        assert_eq!(
            code(&rom, 9),
            vec![0x01, 0x03, 0x02, 0x05, 0x04, 0x09, 0x08, 0x07, 0x06]
        );
    }

    #[test]
    fn a_string_is_written_one_byte_per_character() {
        let rom = assemble(".byte \"AB\", $00, \"C\"\n").unwrap();
        assert_eq!(code(&rom, 4), vec![b'A', b'B', 0x00, b'C']);
    }

    /// A comma inside quotes is part of the string and not a separator.
    #[test]
    fn a_comma_inside_a_string_does_not_split_it() {
        let rom = assemble(".byte \"a,b\"\n").unwrap();
        assert_eq!(code(&rom, 3), vec![b'a', b',', b'b']);
    }

    #[test]
    fn alinear_pads_up_to_the_next_multiple() {
        let rom = assemble(".byte 1\n.alinear 4\n.byte 2\n").unwrap();
        assert_eq!(code(&rom, 5), vec![1, 0, 0, 0, 2]);
    }

    /// The block does not fit in what is left of the bank, so it is pushed to
    /// the start of the next one.
    #[test]
    fn bloque_pushes_a_block_that_would_cross_a_bank() {
        let rom = assemble(
            ".segment \"RODATA\"\n.res $7F00\n.bloque $200\nmark: .byte $AA\n\
             .segment \"CODE\"\n.dword mark\n",
        )
        .unwrap();
        // RODATA starts at file offset $8000, which is bank 1. $7F00 bytes in
        // leaves $100 of the bank, so the block goes to bank 2.
        assert_eq!(code(&rom, 4), vec![0x00, 0x80, 0x02, 0x00]);
    }

    #[test]
    fn a_segment_that_does_not_fit_says_how_much_went_in_and_how_much_there_was() {
        let error = assemble(".res $8000\n").unwrap_err();
        assert!(error.0.contains("the area does not fit"), "{error}");
        assert!(error.0.contains("32704"), "{error}");
    }

    #[test]
    fn a_zero_page_that_does_not_fit_says_so() {
        let error = assemble(".segment \"ZEROPAGE\"\n.res 300\n").unwrap_err();
        assert!(error.0.contains("ZP does not fit"), "{error}");
    }

    #[test]
    fn the_stack_reserve_is_named_when_the_ram_overflows() {
        let error = assemble(".segment \"BSS\"\n.res $1F00\n").unwrap_err();
        assert!(error.0.contains("reserved for the stack"), "{error}");
    }

    #[test]
    fn an_unknown_segment_is_refused() {
        let error = assemble(".segment \"NOWHERE\"\n").unwrap_err();
        assert!(error.0.contains("unknown segment: NOWHERE"), "{error}");
    }

    #[test]
    fn an_unknown_directive_is_refused() {
        let error = assemble(".macro foo\n").unwrap_err();
        assert!(error.0.contains("there is no directive .macro"), "{error}");
    }

    #[test]
    fn an_unknown_instruction_is_refused() {
        let error = assemble("mul $10\n").unwrap_err();
        assert!(error.0.contains("there is no instruction mul"), "{error}");
    }

    #[test]
    fn a_mode_the_instruction_does_not_have_is_refused() {
        let error = assemble("jsr f:$7E0000\n").unwrap_err();
        assert!(error.0.contains("does not take the mode long"), "{error}");
    }

    #[test]
    fn an_implied_instruction_with_an_operand_is_refused() {
        let error = assemble("rts $10\n").unwrap_err();
        assert!(error.0.contains("takes no operand"), "{error}");
    }

    #[test]
    fn controlar_passes_when_the_two_sides_agree() {
        assemble("STRIDE = 12\n.controlar STRIDE = 4 + 8\nnop\n").unwrap();
    }

    #[test]
    fn controlar_fails_with_both_values_and_its_note() {
        let error =
            assemble("STRIDE = 12\n.controlar STRIDE = 16, \"the stride grew\"\n").unwrap_err();
        assert!(error.0.contains("is 12"), "{error}");
        assert!(error.0.contains("the stride grew"), "{error}");
    }

    #[test]
    fn an_include_is_looked_up_and_read() {
        let rom = assemble_in(
            &[("main.s", ".include \"data.inc\"\nlda #VALUE\n"), ("data.inc", "VALUE = $42\n")],
            "main.s",
        )
        .unwrap();
        assert_eq!(code(&rom, 2), vec![0xA9, 0x42]);
    }

    #[test]
    fn a_missing_include_says_what_it_looked_for_and_where() {
        let error = assemble(".include \"absent.inc\"\n").unwrap_err();
        assert!(error.0.contains("cannot find \"absent.inc\""), "{error}");
        assert!(error.0.contains("looked in"), "{error}");
    }

    /// The trap the width check exists for: the branch skips the `sep`, so the
    /// label is reached with a width nobody declared.
    #[test]
    fn a_branch_that_skips_a_width_change_is_refused() {
        let error = assemble(".a16\nbra skip\n.a8\nskip: lda #1\n").unwrap_err();
        assert!(error.0.contains("branches with the accumulator at 16"), "{error}");
        assert!(error.0.contains("declared with 8"), "{error}");
    }

    /// The same source with the label declaring which width it is reached
    /// with, which is the fix the message asks for.
    #[test]
    fn declaring_the_width_at_the_label_settles_it() {
        assemble(".a16\nbra skip\n.a8\nskip:\n.a16\nlda #1\n").unwrap();
    }

    /// A `jsr` to a label in the same bank takes the low word; the bank comes
    /// from whoever is running.
    #[test]
    fn a_jsr_in_the_same_bank_keeps_only_the_low_word() {
        let rom = assemble("jsr here\nhere: rts\n").unwrap();
        assert_eq!(code(&rom, 4), vec![0x20, 0x03, 0x80, 0x60]);
    }

    /// A jump to another bank is the one that would break without warning.
    #[test]
    fn a_jsr_to_another_bank_is_refused() {
        let error = assemble(
            ".segment \"RODATA\"\nfar: rts\n.segment \"CODE\"\njsr far\n",
        )
        .unwrap_err();
        assert!(error.0.contains("does not fit in 2 byte(s)"), "{error}");
    }

    /// The checksum is off in these tests, so this one turns it on to see that
    /// the header ends up consistent.
    ///
    /// The source has to hold `$0000` and `$FFFF` in the two header slots, or
    /// writing the checksum would change the very sum it is the checksum of.
    /// That is the whole reason those values are what they are.
    #[test]
    fn the_checksum_lands_in_the_header() {
        let dir = std::env::temp_dir().join(format!("w65-checksum-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("main.s"),
            "nop\n.segment \"HEADER\"\n.res $1C\n.word $0000\n.word $FFFF\n",
        )
        .unwrap();
        let rom = Assembler::new(true, &[]).assemble(&dir.join("main.s")).unwrap();
        let _ = std::fs::remove_dir_all(&dir);
        let sum = u16::from_le_bytes([rom[layout::CHECKSUM_OFFSET], rom[layout::CHECKSUM_OFFSET + 1]]);
        let complement =
            u16::from_le_bytes([rom[layout::COMPLEMENT_OFFSET], rom[layout::COMPLEMENT_OFFSET + 1]]);
        assert_eq!(complement, !sum);
        assert_eq!((rom.iter().map(|b| *b as u64).sum::<u64>() & 0xFFFF) as u16, sum);
    }

    #[test]
    fn the_symbol_table_carries_the_addresses() {
        let dir = std::env::temp_dir().join(format!("w65-symbols-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("main.s"), "start: nop\nWIDTH = 16\n").unwrap();
        let mut assembler = Assembler::new(false, &[]);
        assembler.assemble(&dir.join("main.s")).unwrap();
        let _ = std::fs::remove_dir_all(&dir);
        assert_eq!(assembler.symbols().get("start"), Some(&Some(0x008000)));
        assert_eq!(assembler.symbols().get("WIDTH"), Some(&Some(16)));
    }

    #[test]
    fn a_comment_is_dropped_and_so_is_an_empty_line() {
        let rom = assemble("; all comment\n\n   nop ; and here\n").unwrap();
        assert_eq!(code(&rom, 1), vec![0xEA]);
    }

    #[test]
    fn a_label_and_its_instruction_can_share_a_line() {
        let rom = assemble("here: nop\njmp here\n").unwrap();
        assert_eq!(code(&rom, 4), vec![0xEA, 0x4C, 0x00, 0x80]);
    }
}
