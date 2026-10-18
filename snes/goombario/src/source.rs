//! What the source says the register widths are.
//!
//! `ca65` keeps the width of A and of X/Y as state while it reads the text:
//! `.a8`, `.a16`, `.i8` and `.i16` set it, and under `.smart` so does every
//! `rep`/`sep` with a constant operand. That state is what each immediate is
//! assembled with, and it is the closest thing a routine has to a declaration
//! of the widths it expects. It is state **of the text**, in the order
//! `.include` pastes the files —not of the code's flow—, so it is read here
//! by going through the text the same way.
//!
//! What is not followed: `.if`/`.else` (both branches are read, as if they
//! were one after the other), and width changes inside a macro's body, which
//! are skipped where it is defined and not applied where it is expanded. The
//! debug file lets the immediates check how far this can be trusted: see
//! `Program::width_disagreements`.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use crate::dbg::DebugInfo;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Widths {
    /// A is 8 bits wide; None while nothing has said.
    pub m8: Option<bool>,
    pub x8: Option<bool>,
}

/// The widths in effect at the start of each line, by (file id, line number),
/// for every file the debug file names that is reached from a main file.
pub struct Declared {
    pub at: HashMap<(usize, u32), Widths>,
    /// The lines of macros' bodies, with what the body has changed of the
    /// widths before each one: what the text says around a body is not what
    /// is in effect where it is expanded. The debug file marks most of these
    /// lines, but not the ones inside a `.repeat`.
    pub macro_lines: HashMap<(usize, u32), Widths>,
    /// The `.include`s that could not be found, and the files that could not
    /// be read.
    pub missing: Vec<String>,
}

/// Where a line's comment starts: its `;`, outside strings and character
/// constants.
pub(crate) fn comment_start(line: &str) -> Option<usize> {
    let bytes = line.as_bytes();
    let mut in_string = false;
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'"' => in_string = !in_string,
            // A character constant, `';'`.
            b'\'' if !in_string && bytes.get(i + 2) == Some(&b'\'') => i += 2,
            b';' if !in_string => return Some(i),
            _ => {}
        }
        i += 1;
    }
    None
}

pub(crate) fn strip_comment(line: &str) -> &str {
    &line[..comment_start(line).unwrap_or(line.len())]
}

/// The line without its labels: `name:`, `@name:` and the anonymous `:`.
fn strip_labels(mut s: &str) -> &str {
    loop {
        s = s.trim_start();
        if let Some(rest) = s.strip_prefix(':') {
            if !rest.starts_with(['+', '-']) {
                s = rest;
                continue;
            }
            return s;
        }
        let end = s
            .char_indices()
            .find(|&(_, c)| !(c.is_alphanumeric() || c == '_' || c == '@'))
            .map(|(i, _)| i)
            .unwrap_or(s.len());
        if end > 0 && s[end..].starts_with(':') && !s[end..].starts_with("::") {
            s = &s[end + 1..];
            continue;
        }
        return s;
    }
}

/// A constant operand of `rep`/`sep`: `$30`, `%00100000`, `32`, and those
/// joined with `|` or `+`. None for anything else.
pub fn constant(expr: &str) -> Option<u32> {
    let mut total = 0;
    for term in expr.split(['|', '+']) {
        let term = term.trim().trim_start_matches('(').trim_end_matches(')').trim();
        let value = if let Some(hex) = term.strip_prefix('$') {
            u32::from_str_radix(hex, 16).ok()?
        } else if let Some(bin) = term.strip_prefix('%') {
            u32::from_str_radix(bin, 2).ok()?
        } else {
            term.parse().ok()?
        };
        total |= value;
    }
    Some(total)
}

struct Reader<'a> {
    info: &'a DebugInfo,
    root: &'a Path,
    ids: HashMap<String, usize>,
    widths: Widths,
    smart: bool,
    out: Declared,
    depth: usize,
    /// Each macro's body, by name in lower case.
    macros: HashMap<String, Vec<String>>,
}

impl Reader<'_> {
    /// The debug file's id for an `.include`: next to the file that includes
    /// it, or any file the debug file names with that name at the end —
    /// which is what the `-I` directories turn into.
    fn resolve(&self, from: &str, name: &str) -> Option<usize> {
        let beside = Path::new(from).parent().unwrap_or(Path::new("")).join(name);
        let beside = normalize(&beside);
        if let Some(&id) = self.ids.get(&beside) {
            return Some(id);
        }
        let suffix = format!("/{}", name);
        let mut found = self
            .ids
            .iter()
            .filter(|(n, _)| n.as_str() == name || n.ends_with(&suffix))
            .map(|(_, &id)| id);
        let first = found.next();
        if found.next().is_some() {
            return None;
        }
        first
    }

    /// What one line of code does to the widths: a directive, a `rep` or
    /// `sep` under `.smart`, or a macro, whose body does it in turn.
    fn apply(&mut self, code: &str, depth: usize) {
        let lower = code.to_ascii_lowercase();
        let mut words = lower.split_whitespace();
        let first = words.next().unwrap_or("");
        match first {
            ".a8" => self.widths.m8 = Some(true),
            ".a16" => self.widths.m8 = Some(false),
            ".i8" => self.widths.x8 = Some(true),
            ".i16" => self.widths.x8 = Some(false),
            ".smart" => {
                let arg = words.next().unwrap_or("+");
                self.smart = !matches!(arg, "-" | "off");
            }
            "rep" | "sep" if self.smart => {
                if let Some(bits) = code[3..].trim().strip_prefix('#').and_then(constant) {
                    let set = first == "sep";
                    if bits & 0x20 != 0 {
                        self.widths.m8 = Some(set);
                    }
                    if bits & 0x10 != 0 {
                        self.widths.x8 = Some(set);
                    }
                }
            }
            name if depth < 8 => {
                if let Some(body) = self.macros.get(name).cloned() {
                    for line in &body {
                        self.apply(strip_labels(line).trim(), depth + 1);
                    }
                }
            }
            _ => {}
        }
    }

    fn read(&mut self, id: usize) {
        self.depth += 1;
        let name = self.info.files[&id].clone();
        let path: PathBuf = self.root.join(&name);
        let text = match std::fs::read_to_string(&path) {
            Ok(t) => t,
            Err(e) => {
                self.out.missing.push(format!("{}: {}", path.display(), e));
                self.depth -= 1;
                return;
            }
        };
        // The macro being defined, and how deep in `.macro`s.
        let mut defining: Option<(String, Vec<String>)> = None;
        let mut body_widths = Widths::default();
        let mut nesting = 0usize;
        for (i, raw) in text.lines().enumerate() {
            self.out.at.insert((id, i as u32 + 1), self.widths);
            let code = strip_labels(strip_comment(raw)).trim().to_string();
            let lower = code.to_ascii_lowercase();
            let first = lower.split_whitespace().next().unwrap_or("");
            if first == ".macro" || first == ".mac" {
                nesting += 1;
                if nesting == 1 {
                    let name = lower.split_whitespace().nth(1).unwrap_or("").trim_end_matches(',');
                    defining = Some((name.to_string(), Vec::new()));
                    body_widths = Widths::default();
                    continue;
                }
            }
            if first == ".endmacro" || first == ".endmac" {
                nesting = nesting.saturating_sub(1);
                if nesting == 0 {
                    if let Some((name, body)) = defining.take() {
                        self.macros.insert(name, body);
                    }
                    continue;
                }
            }
            if let Some((_, body)) = defining.as_mut() {
                // What the body has changed so far, from wherever it is
                // expanded: None is "as it was there".
                self.out.macro_lines.insert((id, i as u32 + 1), body_widths);
                let outside = std::mem::replace(&mut self.widths, body_widths);
                self.apply(&code, 1);
                body_widths = std::mem::replace(&mut self.widths, outside);
                body.push(code);
                continue;
            }
            if first == ".include" {
                let quoted = code.split('"').nth(1);
                match quoted.and_then(|n| self.resolve(&name, n)) {
                    Some(inner) if self.depth < 16 => self.read(inner),
                    _ => self.out.missing.push(format!("{}:{}: {}", name, i + 1, code)),
                }
                continue;
            }
            self.apply(&code, 0);
        }
        self.depth -= 1;
    }
}

fn normalize(path: &Path) -> String {
    let mut parts: Vec<&str> = Vec::new();
    for c in path.to_str().unwrap_or("").split('/') {
        match c {
            "" | "." => {}
            ".." => {
                parts.pop();
            }
            _ => parts.push(c),
        }
    }
    parts.join("/")
}

/// Reads each module's main file from `root` —what the debug file's names
/// are relative to— following its `.include`s.
pub fn declared(info: &DebugInfo, root: &Path) -> Declared {
    let mut reader = Reader {
        info,
        root,
        ids: info.files.iter().map(|(&id, n)| (normalize(Path::new(n)), id)).collect(),
        widths: Widths::default(),
        smart: false,
        out: Declared { at: HashMap::new(), macro_lines: Default::default(), missing: Vec::new() },
        depth: 0,
        macros: HashMap::new(),
    };
    for &main in &info.main_files {
        reader.widths = Widths::default();
        reader.smart = false;
        reader.read(main);
    }
    reader.out
}

/// The text of a line of a file, without its comment: for the messages.
pub struct Texts<'a> {
    root: &'a Path,
    cache: HashMap<String, Vec<String>>,
}

impl<'a> Texts<'a> {
    pub fn new(root: &'a Path) -> Self {
        Texts { root, cache: HashMap::new() }
    }

    pub fn line(&mut self, file: &str, n: u32) -> String {
        let lines = self.cache.entry(file.to_string()).or_insert_with(|| {
            std::fs::read_to_string(self.root.join(file))
                .map(|t| t.lines().map(String::from).collect())
                .unwrap_or_default()
        });
        lines
            .get((n as usize).wrapping_sub(1))
            .map(|l| strip_comment(l).split_whitespace().collect::<Vec<_>>().join(" "))
            .unwrap_or_else(|| "?".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn labels_and_comments_come_off() {
        assert_eq!(strip_labels("foo: rep #$30"), "rep #$30");
        assert_eq!(strip_labels("@x: : sep #$20"), "sep #$20");
        assert_eq!(strip_labels(":+"), ":+");
        assert_eq!(strip_labels("lda ::x"), "lda ::x");
        assert_eq!(strip_comment("lda #';' ; hi"), "lda #';' ");
        assert_eq!(constant("$20 | $10"), Some(0x30));
        assert_eq!(constant("%00100000"), Some(0x20));
        assert_eq!(constant("FOO"), None);
    }
}
