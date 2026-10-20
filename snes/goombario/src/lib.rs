//! Goombario: static checks for 65816 code assembled with `ca65` and linked
//! with `ld65`, for the mistakes that assemble and link fine and are wrong.
//! See the README for what each check looks at and what it cannot see.

pub mod allow;
pub mod analysis;
pub mod cpu;
pub mod dbg;
pub mod program;
pub mod source;

use std::path::Path;

pub use analysis::{Check, Finding, Stats};
pub use program::Program;

/// A finding, placed: where it is and the annotation that would allow it.
#[derive(Debug, Clone)]
pub struct Report {
    pub check: Check,
    pub file: String,
    pub line: u32,
    pub routine: String,
    /// The line's text, without its comment.
    pub text: String,
    pub message: String,
}

impl Report {
    pub fn allow_line(&self) -> String {
        format!("; goombario: {}: <why it is right>", self.check.name())
    }
}

/// The annotations in the program's sources whose debug-file path `wanted`
/// accepts, and the ones that are wrong: see `allow`.
pub fn annotations(
    program: &Program,
    root: &Path,
    wanted: impl Fn(&str) -> bool,
) -> (Vec<allow::Annotation>, Vec<String>) {
    let mut files: Vec<&String> = program.files.values().filter(|f| wanted(f)).collect();
    files.sort();
    files.dedup();
    let mut list = Vec::new();
    let mut wrong = Vec::new();
    for file in files {
        // One that cannot be read is already said by `missing_sources`.
        let Ok(text) = std::fs::read_to_string(root.join(file)) else {
            continue;
        };
        let (a, w) = allow::scan(file, &text);
        // A line of code that put nothing in this program is one an `.if`
        // left out of it: there is nothing there to allow or not, and the
        // annotation is judged in the programs that assemble it. One on a
        // line that is never code —a directive, a label— is judged here.
        let lines: Vec<&str> = text.lines().collect();
        list.extend(a.into_iter().filter(|a| {
            program.assembles(file, a.covers)
                || !lines
                    .get(a.covers as usize - 1)
                    .is_some_and(|l| source::is_code(l))
        }));
        wrong.extend(w);
    }
    (list, wrong)
}

/// The reports no annotation covers, and the annotations that covered none.
pub fn apply_exceptions(
    reports: Vec<Report>,
    annotations: &[allow::Annotation],
) -> (Vec<Report>, Vec<allow::Annotation>) {
    let mut used = vec![false; annotations.len()];
    let mut left = Vec::new();
    for r in reports {
        match annotations
            .iter()
            .position(|a| a.covers(r.check, &r.file, r.line))
        {
            Some(i) => used[i] = true,
            None => left.push(r),
        }
    }
    let unused = annotations
        .iter()
        .zip(used)
        .filter(|(_, u)| !u)
        .map(|(a, _)| a.clone())
        .collect();
    (left, unused)
}

/// Loads a ROM and its debug file, with the sources read from `root`.
pub fn load(rom: &Path, dbg: &Path, root: &Path) -> Result<Program, String> {
    let bytes = std::fs::read(rom).map_err(|e| format!("{}: {}", rom.display(), e))?;
    let text = std::fs::read_to_string(dbg).map_err(|e| format!("{}: {}", dbg.display(), e))?;
    let info = dbg::parse(&text).map_err(|e| format!("{}: {}", dbg.display(), e))?;
    Ok(Program::load(bytes, &info, root))
}

/// Runs the checks and places what they find.
pub fn lint(program: &Program, root: &Path) -> (Vec<Report>, Stats) {
    let (findings, stats) = analysis::Analysis::new(program).run();
    let mut texts = source::Texts::new(root);
    let reports = findings
        .into_iter()
        .map(|f| {
            let (file, line) = program.place_of(f.addr).unwrap_or(("?", 0));
            Report {
                check: f.check,
                file: file.to_string(),
                line,
                routine: program.routine(f.addr).to_string(),
                text: texts.line(file, line),
                message: f.message,
            }
        })
        .collect();
    (reports, stats)
}
