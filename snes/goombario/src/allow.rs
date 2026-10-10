//! The exceptions: findings that are what the code means.
//!
//! One per line, `CHECK ROUTINE [LINE]`: the check's name, the routine the
//! finding is in, and optionally the text of the source line it points at,
//! without its comment and with its spaces collapsed —what the finding's
//! `allow:` line prints—. Without the text, it covers every finding of that
//! check in the routine. Line numbers are left out on purpose: they move with
//! every edit above them, and the text does not.
//!
//! **Every exception needs a comment right above it** saying why, with no
//! blank line in between; several exceptions in a row can share one. An
//! exception without a reason is refused, and so is one that matches
//! nothing: a list that only grows stops saying anything.

use crate::analysis::Check;

#[derive(Debug, Clone)]
pub struct Exception {
    pub check: Check,
    pub routine: String,
    pub text: Option<String>,
    /// Where it is in its file, for the messages.
    pub line: usize,
}

pub fn parse(text: &str) -> Result<Vec<Exception>, String> {
    let mut out = Vec::new();
    // Whether the lines right above have a reason: a comment, or an
    // exception that had one.
    let mut reason = false;
    for (i, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() {
            reason = false;
            continue;
        }
        if line.starts_with('#') {
            reason = true;
            continue;
        }
        if !reason {
            return Err(format!("line {}: an exception without a comment above saying why", i + 1));
        }
        let mut parts = line.splitn(3, char::is_whitespace);
        let check = parts.next().unwrap_or("");
        let check = Check::from_name(check).ok_or_else(|| {
            format!(
                "line {}: {:?} is not a check: they are pull-branch, call-return, stack and width",
                i + 1,
                check
            )
        })?;
        let routine = parts
            .next()
            .filter(|r| !r.is_empty())
            .ok_or_else(|| format!("line {}: an exception without a routine", i + 1))?;
        let text = parts
            .next()
            .map(|t| t.split_whitespace().collect::<Vec<_>>().join(" "))
            .filter(|t| !t.is_empty());
        out.push(Exception { check, routine: routine.to_string(), text, line: i + 1 });
    }
    Ok(out)
}

impl Exception {
    pub fn covers(&self, check: Check, routine: &str, text: &str) -> bool {
        self.check == check
            && self.routine == routine
            && self.text.as_deref().map_or(true, |t| t == text)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn needs_a_reason() {
        assert!(parse("stack foo\n").is_err());
        assert!(parse("# why\n\nstack foo\n").is_err());
        let list = parse("# why\nstack foo\npull-branch bar  ply   x\n").unwrap();
        assert_eq!(list.len(), 2);
        assert_eq!(list[1].text.as_deref(), Some("ply x"));
        assert!(list[0].covers(Check::Stack, "foo", "anything"));
        assert!(!list[1].covers(Check::PullBranch, "bar", "ply"));
    }

    #[test]
    fn knows_the_checks() {
        assert!(parse("# why\nnope foo\n").is_err());
    }
}
