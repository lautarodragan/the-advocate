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

/// A finding, placed: where it is and what the exception that allows it
/// would say.
#[derive(Debug, Clone)]
pub struct Report {
    pub check: Check,
    pub file: String,
    pub line: u32,
    pub routine: String,
    pub text: String,
    pub message: String,
}

impl Report {
    pub fn allow_line(&self) -> String {
        format!("{} {} {}", self.check.name(), self.routine, self.text)
    }
}

/// The reports no exception covers, and the exceptions that covered none.
pub fn apply_exceptions(reports: Vec<Report>, exceptions: &[allow::Exception]) -> (Vec<Report>, Vec<allow::Exception>) {
    let mut used = vec![false; exceptions.len()];
    let mut left = Vec::new();
    for r in reports {
        match exceptions.iter().position(|e| e.covers(r.check, &r.routine, &r.text)) {
            Some(i) => used[i] = true,
            None => left.push(r),
        }
    }
    let unused = exceptions.iter().zip(used).filter(|(_, u)| !u).map(|(e, _)| e.clone()).collect();
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
