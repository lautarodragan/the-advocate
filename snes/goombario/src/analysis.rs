//! The checks.
//!
//! One of them looks at a few instructions after each pull. The others walk
//! the code from each routine's entry —every target of a `jsr`, `jsl` or
//! `jsr (table, x)`, and the interrupt vectors— following every branch, with
//! an abstract state: the width of A and of X/Y, and the bytes the routine
//! has on the stack. A call is not walked into: the callee has its own walk,
//! and the caller takes from it only the widths it comes back with.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

use crate::cpu;
use crate::program::{Insn, Program};
use crate::source::Widths;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Check {
    PullBranch,
    CallReturn,
    Stack,
    Width,
}

impl Check {
    pub fn name(self) -> &'static str {
        match self {
            Check::PullBranch => "pull-branch",
            Check::CallReturn => "call-return",
            Check::Stack => "stack",
            Check::Width => "width",
        }
    }

    pub fn from_name(s: &str) -> Option<Check> {
        [Check::PullBranch, Check::CallReturn, Check::Stack, Check::Width]
            .into_iter()
            .find(|c| c.name() == s)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Finding {
    pub check: Check,
    pub addr: u32,
    pub message: String,
}

/// A register's width on a path: known, or the one the routine was entered
/// with, which is the one its entry declares as far as its own instructions
/// go, and the caller's as far as the caller goes.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum W {
    B8,
    B16,
    Entry,
    Unknown,
}

fn join(a: Option<W>, b: W) -> Option<W> {
    match a {
        None => Some(b),
        Some(a) if a == b => Some(a),
        Some(_) => Some(W::Unknown),
    }
}

/// One byte on the stack: where it was pushed, and, for a `php`, the widths
/// it saved.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct Slot {
    pushed_at: u32,
    saved: Option<(W, W)>,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct State {
    m: W,
    x: W,
    /// What the routine has pushed since its entry; None once it cannot be
    /// followed (`tcs`, `txs`, a pull of more than was pushed).
    stack: Option<Vec<Slot>>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Kind {
    Jsr,
    Jsl,
    Interrupt,
    /// The reset vector: it does not come back at all.
    Reset,
}

impl Kind {
    fn returns_with(self) -> u8 {
        match self {
            Kind::Jsr => cpu::RTS,
            Kind::Jsl => cpu::RTL,
            Kind::Interrupt => cpu::RTI,
            Kind::Reset => 0,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Kind::Jsr => "jsr",
            Kind::Jsl => "jsl",
            Kind::Interrupt => "an interrupt",
            Kind::Reset => "the reset",
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct Summary {
    declared: Widths,
    /// Every `rts`, `rtl` and `rti` some path reaches.
    returns: BTreeSet<u32>,
    exit_m: Option<W>,
    exit_x: Option<W>,
    /// Whether some instruction depends on the width the routine was
    /// entered with, before the routine sets it.
    needs_m: bool,
    needs_x: bool,
    unfollowed: bool,
}

/// How much the width study could decide.
#[derive(Clone, Debug, Default)]
pub struct WidthStats {
    pub immediates_known: usize,
    pub immediates_unknown: usize,
    pub immediates_wrong: usize,
    pub others_known: usize,
    pub others_unknown: usize,
    pub others_wrong: usize,
    pub calls_known: usize,
    pub calls_unknown: usize,
    pub calls_wrong: usize,
}

#[derive(Default)]
pub struct Stats {
    pub instructions: usize,
    pub pulls: usize,
    pub entries: usize,
    pub calls: usize,
    pub returns_checked: usize,
    /// Where a walk had to stop, and why: indirect jumps, code that is not in
    /// the debug file, stacks that grow in a loop.
    pub unfollowed: BTreeMap<u32, String>,
    pub width: WidthStats,
}

const MAX_STATES: usize = 32;
const MAX_STACK: usize = 64;

pub struct Analysis<'a> {
    p: &'a Program,
    summaries: HashMap<u32, Option<Summary>>,
    /// Who calls each entry, and how.
    callers: BTreeMap<u32, BTreeMap<Kind, u32>>,
    findings: BTreeSet<Finding>,
    found: HashSet<(Check, u32)>,
    width_seen: HashSet<(u32, char)>,
    width_known: HashSet<(u32, char)>,
    width_unknown: HashSet<(u32, char)>,
    width_wrong: HashSet<(u32, char)>,
    pub stats: Stats,
}

fn resolve(w: W, declared: Option<bool>) -> Option<bool> {
    match w {
        W::B8 => Some(true),
        W::B16 => Some(false),
        W::Entry => declared,
        W::Unknown => None,
    }
}

fn bits(m8: bool) -> &'static str {
    if m8 { "8" } else { "16" }
}

impl<'a> Analysis<'a> {
    pub fn new(p: &'a Program) -> Self {
        Analysis {
            p,
            summaries: HashMap::new(),
            callers: BTreeMap::new(),
            findings: BTreeSet::new(),
            found: HashSet::new(),
            width_seen: HashSet::new(),
            width_known: HashSet::new(),
            width_unknown: HashSet::new(),
            width_wrong: HashSet::new(),
            stats: Stats::default(),
        }
    }

    /// One finding per check and instruction: the first path that shows it.
    fn find(&mut self, check: Check, addr: u32, message: String) {
        if self.found.insert((check, addr)) {
            self.findings.insert(Finding { check, addr, message });
        }
    }

    fn unfollowed(&mut self, addr: u32, why: String) {
        self.stats.unfollowed.entry(addr).or_insert(why);
    }

    fn at(&self, addr: u32) -> String {
        match self.p.place_of(addr) {
            Some((file, line)) => format!("{}:{}", file, line),
            None => format!("${:06X}", addr),
        }
    }

    pub fn run(mut self) -> (Vec<Finding>, Stats) {
        self.stats.instructions = self.p.insns.len();
        self.pull_branches();
        let entries = self.entries();
        self.stats.entries = entries.len();
        for &entry in entries.keys() {
            self.summary(entry);
        }
        self.call_returns();
        let immediate = |a: &u32| {
            matches!(cpu::mode(self.p.bytes(*a, 1).map_or(0, |b| b[0])), cpu::Mode::ImmM | cpu::Mode::ImmX)
        };
        let w = &mut self.stats.width;
        for &(a, _) in &self.width_known {
            if immediate(&a) { w.immediates_known += 1 } else { w.others_known += 1 }
        }
        for k in self.width_unknown.difference(&self.width_known) {
            if immediate(&k.0) { w.immediates_unknown += 1 } else { w.others_unknown += 1 }
        }
        for &(a, _) in &self.width_wrong {
            if immediate(&a) { w.immediates_wrong += 1 } else { w.others_wrong += 1 }
        }
        (self.findings.into_iter().collect(), self.stats)
    }

    // --- 1. A pull, then a branch on what it pulled -------------------------

    /// `pla`, `plx`, `ply`, `plb` and `pld` set N and Z from what they pull,
    /// and `plp` sets every flag. A branch on one of those, with nothing in
    /// between that sets it again —`sep`/`rep` set only the bits in their
    /// operand, a store sets nothing—, is branching on the pulled value.
    fn pull_branches(&mut self) {
        let pulls: Vec<u32> = self
            .p
            .insns
            .values()
            .filter(|i| cpu::pull_flags(i.op) != 0)
            .map(|i| i.addr)
            .collect();
        self.stats.pulls = pulls.len();
        for pull in pulls {
            let flags = cpu::pull_flags(self.p.insns[&pull].op);
            let mut seen = HashSet::new();
            let mut work = vec![(self.p.insns[&pull].addr + self.p.insns[&pull].len, flags)];
            while let Some((addr, live)) = work.pop() {
                if live == 0 || !seen.insert((addr, live)) || seen.len() > 256 {
                    continue;
                }
                let Some(insn) = self.p.insns.get(&addr) else { continue };
                if let Some(flag) = cpu::branch_flag(insn.op) {
                    if live & flag != 0 {
                        self.pull_branch(pull, insn, flag);
                    }
                }
                let imm = self.p.rom.get(insn.offset + 1).copied().unwrap_or(0);
                let live = live & !cpu::writes_flags(insn.op, imm);
                for next in self.successors_local(insn) {
                    work.push((next, live));
                }
            }
        }
    }

    fn pull_branch(&mut self, pull: u32, branch: &Insn, flag: u8) {
        let pull_insn = &self.p.insns[&pull];
        let message = format!(
            "`{}` looks at {}, and the last instruction to set it is the `{}` at {}, \
             with what it pulled{}. If the branch means the pulled value, this is an \
             exception; if it means something from before the pull, a compare goes \
             between the two",
            cpu::mnemonic(branch.op),
            cpu::flag_name(flag),
            cpu::mnemonic(pull_insn.op),
            self.at(pull),
            if flag == cpu::Z || flag == cpu::N { ": `sep` and `rep` do not set it" } else { "" },
        );
        self.find(Check::PullBranch, branch.addr, message);
    }

    /// Where control goes after an instruction, within its routine: calls
    /// and returns end the search, since a call sets the flags anew.
    fn successors_local(&self, insn: &Insn) -> Vec<u32> {
        let bank = insn.addr & 0xFF_0000;
        let next = insn.addr + insn.len;
        match insn.op {
            cpu::JSR | cpu::JSL | cpu::JSR_X | cpu::RTS | cpu::RTL | cpu::RTI | cpu::JMP_IND
            | cpu::JMP_X | cpu::JML_IND => vec![],
            0x00 | 0x02 | 0xDB => vec![],
            cpu::JMP => vec![bank | self.p.operand(insn)],
            cpu::JML => self.p.locate(self.p.operand(insn)).into_iter().collect(),
            cpu::BRA => vec![self.relative(insn)],
            cpu::BRL => vec![self.relative(insn)],
            op if cpu::branch_flag(op).is_some() => vec![next, self.relative(insn)],
            _ => vec![next],
        }
    }

    fn relative(&self, insn: &Insn) -> u32 {
        let bank = insn.addr & 0xFF_0000;
        let next = insn.addr.wrapping_add(insn.len);
        let offset = if insn.len == 2 {
            self.p.rom[insn.offset + 1] as i8 as i32
        } else {
            self.p.operand(insn) as u16 as i16 as i32
        };
        bank | (next as i32 + offset) as u32 & 0xFFFF
    }

    // --- The entries ---------------------------------------------------------

    /// The entries of `jmp (table, x)` and `jsr (table, x)`: the words from
    /// the table's address to the next label, in the program bank.
    fn table(&self, insn: &Insn) -> Option<Vec<u32>> {
        let bank = insn.addr & 0xFF_0000;
        let start = self.p.locate(bank | self.p.operand(insn))?;
        let end = self.p.next_label(start).unwrap_or(start + 512).min(start + 512);
        let bytes = self.p.bytes(start, (end - start) as usize & !1)?;
        Some(
            bytes
                .chunks(2)
                .map(|w| bank | (w[0] as u32 | (w[1] as u32) << 8))
                .collect(),
        )
    }

    fn call_target(&self, insn: &Insn) -> Option<u32> {
        match insn.op {
            cpu::JSR => Some(insn.addr & 0xFF_0000 | self.p.operand(insn)),
            cpu::JSL => self.p.locate(self.p.operand(insn)),
            _ => None,
        }
    }

    fn entries(&mut self) -> BTreeMap<u32, BTreeSet<Kind>> {
        let mut entries: BTreeMap<u32, BTreeSet<Kind>> = BTreeMap::new();
        let insns: Vec<Insn> = self.p.insns.values().cloned().collect();
        for insn in &insns {
            let (targets, kind) = match insn.op {
                cpu::JSR => (self.call_target(insn).into_iter().collect(), Kind::Jsr),
                cpu::JSL => (self.call_target(insn).into_iter().collect(), Kind::Jsl),
                cpu::JSR_X => (self.table(insn).unwrap_or_default(), Kind::Jsr),
                _ => continue,
            };
            for t in targets {
                if self.p.insns.contains_key(&t) {
                    entries.entry(t).or_default().insert(kind);
                    self.callers.entry(t).or_default().entry(kind).or_insert(insn.addr);
                }
            }
        }
        // The native-mode vectors that come back with `rti` —COP, BRK, NMI
        // and IRQ— and the reset, which is in the emulation-mode ones and
        // does not come back.
        for (vector, kind) in [
            (0xFFE4u32, Kind::Interrupt),
            (0xFFE6, Kind::Interrupt),
            (0xFFEA, Kind::Interrupt),
            (0xFFEE, Kind::Interrupt),
            (0xFFFC, Kind::Reset),
        ] {
            let Some(b) = self.p.bytes(vector, 2) else { continue };
            let target = b[0] as u32 | (b[1] as u32) << 8;
            if let Some(t) = self.p.locate(target) {
                if self.p.insns.contains_key(&t) {
                    entries.entry(t).or_default().insert(kind);
                    self.callers.entry(t).or_default().entry(kind).or_insert(vector);
                }
            }
        }
        entries
    }

    // --- 2, 3 and 4: the walk of a routine ----------------------------------

    fn summary(&mut self, entry: u32) -> Option<Summary> {
        if let Some(s) = self.summaries.get(&entry) {
            return s.clone();
        }
        self.summaries.insert(entry, None);
        let s = self.walk(entry);
        self.summaries.insert(entry, Some(s.clone()));
        Some(s)
    }

    fn walk(&mut self, entry: u32) -> Summary {
        let p = self.p;
        let declared = p.insns.get(&entry).map(|i| p.declared(i)).unwrap_or_default();
        let mut summary = Summary { declared, ..Summary::default() };
        let start = State { m: W::Entry, x: W::Entry, stack: Some(Vec::new()) };
        let mut seen: HashSet<(u32, State)> = HashSet::new();
        let mut per_addr: HashMap<u32, Vec<State>> = HashMap::new();
        // The stack's findings wait for the end of the walk: if the routine
        // pushes on a loop —`ldx #3`, a `pha` per turn, then four pulls—,
        // how many bytes it has depends on data the walk does not follow,
        // and every count it tries but the right one would be a finding.
        let mut stack_findings: Vec<(u32, String)> = Vec::new();
        let mut stack_loop: Option<u32> = None;
        let mut work = vec![(entry, start)];
        while let Some((addr, mut s)) = work.pop() {
            if seen.contains(&(addr, s.clone())) {
                continue;
            }
            let before = per_addr.entry(addr).or_default();
            let grows = before.iter().any(|t| {
                t.m == s.m
                    && t.x == s.x
                    && match (&t.stack, &s.stack) {
                        (Some(a), Some(b)) => a.len() < b.len() && b.starts_with(a),
                        _ => false,
                    }
            });
            if grows {
                stack_loop.get_or_insert(addr);
                continue;
            }
            if before.len() >= MAX_STATES {
                summary.unfollowed = true;
                self.unfollowed(addr, "too many different states reach it".into());
                continue;
            }
            before.push(s.clone());
            seen.insert((addr, s.clone()));
            let decoded;
            let insn = match p.insns.get(&addr) {
                Some(i) => i,
                None => {
                    let m8 = resolve(s.m, summary.declared.m8).unwrap_or(true);
                    let x8 = resolve(s.x, summary.declared.x8).unwrap_or(true);
                    match p.decode_at(addr, m8, x8) {
                        Some(i) => {
                            decoded = i;
                            &decoded
                        }
                        None => {
                            summary.unfollowed = true;
                            self.unfollowed(
                                addr,
                                format!("reached from `{}`, and it is not in the ROM", p.name(entry)),
                            );
                            continue;
                        }
                    }
                }
            };
            let here = p.declared(insn);
            let decl = summary.declared;
            self.widths(insn, &s, &decl, here, entry, &mut summary);
            let op = insn.op;
            let next = addr + insn.len;
            let imm = p.rom.get(insn.offset + 1).copied().unwrap_or(0);
            let decl = summary.declared;
            let resolve_m = |s: &State| resolve(s.m, decl.m8).or(here.m8);
            let resolve_x = |s: &State| resolve(s.x, decl.x8).or(here.x8);

            // The stack.
            let size = match cpu::stack_effect(op) {
                cpu::StackEffect::None => 0i32,
                cpu::StackEffect::Push(n) => n as i32,
                cpu::StackEffect::Pull(n) => -(n as i32),
                cpu::StackEffect::PushWidth(r) | cpu::StackEffect::PullWidth(r) => {
                    let w = if r == 'm' { resolve_m(&s) } else { resolve_x(&s) };
                    let n = match w {
                        Some(true) => 1,
                        Some(false) => 2,
                        None => {
                            s.stack = None;
                            0
                        }
                    };
                    if matches!(cpu::stack_effect(op), cpu::StackEffect::PushWidth(_)) { n } else { -n }
                }
            };
            let mut restored = None;
            if let Some(stack) = s.stack.as_mut() {
                if size > 0 {
                    for _ in 0..size {
                        stack.push(Slot {
                            pushed_at: addr,
                            saved: if op == cpu::PHP { Some((s.m, s.x)) } else { None },
                        });
                    }
                    if stack.len() > MAX_STACK {
                        summary.unfollowed = true;
                        self.unfollowed(addr, "the stack keeps growing on a loop".into());
                        continue;
                    }
                } else if size < 0 {
                    let n = (-size) as usize;
                    if stack.len() < n {
                        stack_findings.push((
                            addr,
                            format!(
                                "`{}` pulls more than `{}` has pushed since its entry: it takes \
                                 bytes of the return address",
                                cpu::mnemonic(op),
                                p.name(entry)
                            ),
                        ));
                        s.stack = None;
                    } else {
                        let top = stack.split_off(stack.len() - n);
                        if op == cpu::PLP {
                            restored = top[0].saved;
                        }
                    }
                }
            }
            if op == cpu::TCS || op == cpu::TXS {
                s.stack = None;
            }

            // The widths.
            match op {
                cpu::REP | cpu::SEP => {
                    let w = if op == cpu::SEP { W::B8 } else { W::B16 };
                    if imm & 0x20 != 0 {
                        s.m = w;
                    }
                    if imm & 0x10 != 0 {
                        s.x = w;
                    }
                }
                cpu::PLP => {
                    let (m, x) = restored.unwrap_or((W::Unknown, W::Unknown));
                    s.m = m;
                    s.x = x;
                }
                cpu::XCE => {
                    s.m = W::Unknown;
                    s.x = W::Unknown;
                }
                _ => {}
            }

            // Where it goes.
            let bank = addr & 0xFF_0000;
            match op {
                cpu::RTS | cpu::RTL | cpu::RTI => {
                    summary.returns.insert(addr);
                    summary.exit_m = join(summary.exit_m, s.m);
                    summary.exit_x = join(summary.exit_x, s.x);
                    self.stats.returns_checked += 1;
                    if let Some(stack) = &s.stack {
                        if !stack.is_empty() {
                            let mut at: Vec<String> = Vec::new();
                            for slot in stack {
                                let a = self.at(slot.pushed_at);
                                let pusher = p.bytes(slot.pushed_at, 1).map_or(0, |b| b[0]);
                                let what = format!("`{}` at {}", cpu::mnemonic(pusher), a);
                                if !at.contains(&what) {
                                    at.push(what);
                                }
                            }
                            stack_findings.push((
                                addr,
                                format!(
                                    "`{}` leaves `{}` with {} byte{} still pushed, by {}: it returns \
                                     to wherever those bytes point",
                                    cpu::mnemonic(op),
                                    p.name(entry),
                                    stack.len(),
                                    if stack.len() == 1 { "" } else { "s" },
                                    at.join(", ")
                                ),
                            ));
                        }
                    }
                }
                0x00 | 0x02 | 0xDB => {} // brk, cop, stp
                cpu::JSR | cpu::JSL | cpu::JSR_X => {
                    self.stats.calls += 1;
                    let targets = match op {
                        cpu::JSR_X => self.table(insn).unwrap_or_default(),
                        _ => self.call_target(insn).into_iter().collect(),
                    };
                    let (mut m, mut x) = (None, None);
                    if targets.is_empty() {
                        summary.unfollowed = true;
                        self.unfollowed(addr, "a call to somewhere outside the ROM".into());
                    }
                    for t in targets {
                        let callee = if p.insns.contains_key(&t) { self.summary(t) } else { None };
                        let Some(callee) = callee else {
                            m = join(m, W::Unknown);
                            x = join(x, W::Unknown);
                            continue;
                        };
                        // Passing on the width it was entered with to a callee
                        // that uses it is using it.
                        summary.needs_m |= callee.needs_m && s.m == W::Entry;
                        summary.needs_x |= callee.needs_x && s.x == W::Entry;
                        self.call_widths(insn, t, &callee, &s, &decl, here);
                        m = join(m, match callee.exit_m { Some(W::Entry) => s.m, Some(w) => w, None => W::Unknown });
                        x = join(x, match callee.exit_x { Some(W::Entry) => s.x, Some(w) => w, None => W::Unknown });
                    }
                    s.m = m.unwrap_or(W::Unknown);
                    s.x = x.unwrap_or(W::Unknown);
                    work.push((next, s));
                }
                cpu::JMP_IND | cpu::JML_IND => {
                    summary.unfollowed = true;
                    self.unfollowed(addr, "an indirect jump".into());
                }
                cpu::JMP_X => match self.table(insn) {
                    Some(t) => {
                        for target in t {
                            work.push((target, s.clone()));
                        }
                    }
                    None => {
                        summary.unfollowed = true;
                        self.unfollowed(addr, "a jump whose table is not in the ROM".into());
                    }
                },
                cpu::JMP => work.push((bank | p.operand(insn), s)),
                cpu::JML => match p.locate(p.operand(insn)) {
                    Some(t) => work.push((t, s)),
                    None => {
                        summary.unfollowed = true;
                        self.unfollowed(addr, "a long jump out of the ROM".into());
                    }
                },
                cpu::BRA | cpu::BRL => work.push((self.relative(insn), s)),
                op if cpu::branch_flag(op).is_some() => {
                    work.push((self.relative(insn), s.clone()));
                    work.push((next, s));
                }
                _ => work.push((next, s)),
            }
        }
        match stack_loop {
            None => {
                for (addr, message) in stack_findings {
                    self.find(Check::Stack, addr, message);
                }
            }
            Some(addr) => {
                summary.unfollowed = true;
                self.unfollowed(
                    addr,
                    format!(
                        "`{}` pushes on a loop, so its stack is not checked: how many times \
                         depends on data",
                        p.name(entry)
                    ),
                );
            }
        }
        summary
    }

    /// 4, inside a routine: an instruction whose behaviour depends on a
    /// width, where the width on this path is not the one the source
    /// declares. For an immediate the declaration is in the ROM —how many
    /// bytes `ca65` emitted—, and a mismatch means the CPU reads the
    /// instruction with a different length from the one assembled.
    fn widths(&mut self, insn: &Insn, s: &State, entry: &Widths, here: Widths, from: u32, summary: &mut Summary) {
        let Some(reg) = cpu::width_of(insn.op) else { return };
        let (w, declared_entry, declared_here) = if reg == 'm' {
            (s.m, entry.m8, here.m8)
        } else {
            (s.x, entry.x8, here.x8)
        };
        if w == W::Entry {
            if reg == 'm' {
                summary.needs_m = true;
            } else {
                summary.needs_x = true;
            }
        }
        let immediate = matches!(cpu::mode(insn.op), cpu::Mode::ImmM | cpu::Mode::ImmX);
        let believed = if immediate { Some(insn.len == 2) } else { declared_here };
        let actual = resolve(w, declared_entry);
        let (Some(actual), Some(believed)) = (actual, believed) else {
            self.width_unknown.insert((insn.addr, reg));
            return;
        };
        self.width_known.insert((insn.addr, reg));
        if actual == believed || !self.width_wrong.insert((insn.addr, reg)) {
            return;
        }
        let register = if reg == 'm' { "A" } else { "X/Y" };
        // Of the several instructions of a macro's line, which one.
        let which = match insn.macro_line {
            Some(_) => format!(" (at ${:06X})", insn.addr),
            None => String::new(),
        };
        let message = if immediate {
            format!(
                "`{}`{} was assembled for a {}-bit {}, and on the path from `{}` {} is {} bits wide \
                 here: the CPU reads it with a different length",
                cpu::mnemonic(insn.op),
                which,
                bits(believed),
                register,
                self.p.name(from),
                register,
                bits(actual)
            )
        } else {
            format!(
                "`{}`{} is under a {}-bit {} in the source, and on the path from `{}` it is {} \
                 bits wide",
                cpu::mnemonic(insn.op),
                which,
                bits(believed),
                register,
                self.p.name(from),
                bits(actual)
            )
        };
        self.find(Check::Width, insn.addr, message);
    }

    /// 4, at a call: the caller's widths against what the callee declares at
    /// its entry, for the registers the callee uses before setting them.
    fn call_widths(&mut self, insn: &Insn, target: u32, callee: &Summary, s: &State, entry: &Widths, here: Widths) {
        for (reg, needs, w, declared_entry, declared_here, callee_declares) in [
            ('m', callee.needs_m, s.m, entry.m8, here.m8, callee.declared.m8),
            ('x', callee.needs_x, s.x, entry.x8, here.x8, callee.declared.x8),
        ] {
            if !needs {
                continue;
            }
            let actual = resolve(w, declared_entry).or(declared_here);
            let (Some(actual), Some(wanted)) = (actual, callee_declares) else {
                self.stats.width.calls_unknown += 1;
                continue;
            };
            if !self.width_seen.insert((insn.addr, reg)) {
                continue;
            }
            self.stats.width.calls_known += 1;
            if actual != wanted {
                self.stats.width.calls_wrong += 1;
                self.find(
                    Check::Width,
                    insn.addr,
                    format!(
                        "`{}` declares a {}-bit {} at its entry and uses it before setting it, and \
                         it is called here with a {}-bit one",
                        self.p.name(target),
                        bits(wanted),
                        if reg == 'm' { "A" } else { "X/Y" },
                        bits(actual)
                    ),
                );
            }
        }
    }

    /// 2: a routine entered with `jsr` comes back with `rts`, one entered
    /// with `jsl` with `rtl`, an interrupt with `rti`. The message goes on
    /// the return, which can be in another routine the entry jumped to.
    fn call_returns(&mut self) {
        let callers = std::mem::take(&mut self.callers);
        for (entry, kinds) in &callers {
            let Some(Some(summary)) = self.summaries.get(entry).cloned() else { continue };
            for (&kind, &site) in kinds {
                if kind == Kind::Reset {
                    continue;
                }
                for &ret in &summary.returns {
                    let op = self.p.bytes(ret, 1).map_or(0, |b| b[0]);
                    if op == kind.returns_with() {
                        continue;
                    }
                    let message = format!(
                        "`{}` is entered with {} (at {}), and this path out of it is an `{}`, \
                         which pulls {} bytes of return address where {} pushed {}",
                        self.p.name(*entry),
                        kind.name(),
                        if kind == Kind::Interrupt { format!("the vector ${:04X}", site) } else { self.at(site) },
                        cpu::mnemonic(op),
                        match op { cpu::RTS => 2, cpu::RTL => 3, _ => 4 },
                        kind.name(),
                        match kind { Kind::Jsr => 2, Kind::Jsl => 3, _ => 4 },
                    );
                    self.find(Check::CallReturn, ret, message);
                }
            }
        }
        self.callers = callers;
    }
}
