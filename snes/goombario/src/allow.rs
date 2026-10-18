//! The exceptions: findings that are what the code means, said in the source
//! itself, on the line they are about.
//!
//! A comment that starts with `goombario:`, then the check's name, a colon
//! and why the line is right:
//!
//! ```text
//!     beq off             ; goombario: pull-branch: the value to write, 0 is off
//! ```
//!
//! On a line with code it covers that line. On a line that is only a
//! comment it covers the next line with code, and the comment lines in
//! between carry on its why; a blank line in between is an error, so that an
//! annotation never lands somewhere nobody sees it from.
//!
//! **The why is required**: an annotation without one is an error, and so is
//! one that covers nothing —a list of exceptions that only grows stops saying
//! anything, and one spread over the source too—. An annotation covers only
//! the check it names.

use crate::analysis::Check;
use crate::source::{comment_start, strip_comment};

const MARK: &str = "goombario:";

#[derive(Debug, Clone)]
pub struct Annotation {
    pub check: Check,
    pub file: String,
    /// Where the annotation is written.
    pub line: u32,
    /// The line it covers: its own, or the next with code.
    pub covers: u32,
    pub why: String,
}

/// The annotations in one source file, and the ones that are wrong, as
/// `file:line: why it is wrong`.
pub fn scan(file: &str, text: &str) -> (Vec<Annotation>, Vec<String>) {
    let lines: Vec<&str> = text.lines().collect();
    let mut out = Vec::new();
    let mut wrong = Vec::new();
    for (i, raw) in lines.iter().enumerate() {
        let Some(at) = comment_start(raw) else { continue };
        let comment = raw[at..].trim_start_matches(';').trim();
        let Some(rest) = comment.strip_prefix(MARK) else { continue };
        let n = i as u32 + 1;
        let place = format!("{}:{}", file, n);
        let Some((name, why)) = rest.split_once(':') else {
            wrong.push(format!("{}: a goombario annotation is `goombario: CHECK: why`", place));
            continue;
        };
        let Some(check) = Check::from_name(name.trim()) else {
            wrong.push(format!(
                "{}: {:?} is not a check: they are pull-branch, call-return, stack and width",
                place,
                name.trim()
            ));
            continue;
        };
        let why = why.trim();
        if why.is_empty() {
            wrong.push(format!("{}: a goombario annotation without its why", place));
            continue;
        }
        let covers = if strip_comment(raw).trim().is_empty() {
            // The first line below that is code or blank: only comments
            // can stand between the annotation and what it covers.
            let next = lines[i + 1..]
                .iter()
                .position(|l| l.trim().is_empty() || !strip_comment(l).trim().is_empty())
                .map(|k| i + 1 + k);
            match next {
                Some(k) if !lines[k].trim().is_empty() => k as u32 + 1,
                _ => {
                    wrong.push(format!(
                        "{}: a goombario annotation alone on its line covers the next line with code, \
                         and there is none before a blank line",
                        place
                    ));
                    continue;
                }
            }
        } else {
            n
        };
        out.push(Annotation { check, file: file.to_string(), line: n, covers, why: why.to_string() });
    }
    (out, wrong)
}

impl Annotation {
    pub fn covers(&self, check: Check, file: &str, line: u32) -> bool {
        self.check == check && self.file == file && self.covers == line
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn on_its_line_or_above_the_next_with_code() {
        let text = "\
    pla
    beq off      ; goombario: pull-branch: the value to write
    ; goombario: stack: a shared exit,
    ; which drops the return address
    rts
";
        let (list, wrong) = scan("a.s", text);
        assert!(wrong.is_empty(), "{:?}", wrong);
        assert_eq!(list.len(), 2);
        assert_eq!((list[0].check, list[0].covers), (Check::PullBranch, 2));
        assert_eq!(list[0].why, "the value to write");
        assert_eq!((list[1].check, list[1].line, list[1].covers), (Check::Stack, 3, 5));
    }

    #[test]
    fn what_is_wrong_is_said() {
        let (list, wrong) = scan(
            "a.s",
            "beq x ; goombario: pull-branch:\nbeq x ; goombario: pull-branch\nbeq x ; goombario: nope: why\n\
             ; goombario: stack: why\n\nrts\n",
        );
        assert!(list.is_empty(), "{:?}", list);
        assert_eq!(wrong.len(), 4, "{:?}", wrong);
        assert!(wrong[0].starts_with("a.s:1:") && wrong[0].contains("without its why"));
        assert!(wrong[3].starts_with("a.s:4:"));
    }

    #[test]
    fn other_comments_and_strings_are_not_annotations() {
        let (list, wrong) = scan("a.s", ".byte \"; goombario: stack: x\"\nrts ; see goombario: stack: x\n");
        assert!(list.is_empty() && wrong.is_empty(), "{:?} {:?}", list, wrong);
    }
}
