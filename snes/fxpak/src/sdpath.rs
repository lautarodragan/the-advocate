//! Paths on the FX Pak's SD card, normalised here before the firmware sees
//! them, and the one rule for writing: only under `/advocate/`.
//!
//! The firmware's FatFs (sd2snes v1.11.0, `src/ffconf.h` and `src/ff.c`) is
//! built with `_FS_RPATH 2`: a path that does not start with a separator is
//! relative to a current directory the menu moves, and `.` and `..` are
//! resolved by FatFs itself. Both `/` and `\` separate (`ff.c` 1809, 1814),
//! FAT compares names without case, and trailing dots and spaces are
//! dropped from a long name. So a path is only trusted after this: absolute,
//! `/`-separated, `.` and `..` resolved here —and `..` above the root
//! refused—, printable ASCII without FAT's illegal characters (`ff.c` 1828:
//! `"*:<>?|`) nor `\`, and no component ending in a dot or a space.

use crate::protocol::MAX_NAME;

/// A normalised absolute path: `/` or `/a/b`, without a trailing slash.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SdPath(String);

/// The one folder this tool writes in, compared without case like FAT.
pub const WRITABLE: &str = "advocate";

impl SdPath {
    pub fn parse(raw: &str) -> Result<SdPath, String> {
        if !raw.starts_with('/') {
            return Err(format!("{raw:?}: an SD path must be absolute, from /"));
        }
        let mut parts: Vec<&str> = Vec::new();
        for part in raw.split('/') {
            match part {
                "" | "." => {}
                ".." => {
                    if parts.pop().is_none() {
                        return Err(format!("{raw:?}: .. goes above the card's root"));
                    }
                }
                p => {
                    if let Some(c) = p
                        .chars()
                        .find(|&c| !(' '..='~').contains(&c) || "\"*:<>?|\\".contains(c))
                    {
                        return Err(format!("{raw:?}: {c:?} is not allowed in an SD path here"));
                    }
                    if p.ends_with(' ') || p.ends_with('.') || p.starts_with(' ') {
                        return Err(format!(
                            "{raw:?}: {p:?} starts with a space or ends with a dot or a space, which FAT drops"
                        ));
                    }
                    parts.push(p);
                }
            }
        }
        let s = format!("/{}", parts.join("/"));
        if s.len() > MAX_NAME {
            return Err(format!(
                "{raw:?}: longer than the {MAX_NAME} bytes a command carries"
            ));
        }
        Ok(SdPath(s))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn components(&self) -> Vec<&str> {
        self.0.split('/').filter(|p| !p.is_empty()).collect()
    }

    /// The parent and the last component; `None` for the root.
    pub fn split(&self) -> Option<(SdPath, &str)> {
        let i = self.0.rfind('/')?;
        let name = &self.0[i + 1..];
        if name.is_empty() {
            return None;
        }
        let parent = if i == 0 {
            "/".to_string()
        } else {
            self.0[..i].to_string()
        };
        Some((SdPath(parent), name))
    }

    pub fn join(&self, name: &str) -> Result<SdPath, String> {
        SdPath::parse(&format!("{}/{}", self.0, name))
    }

    /// Whether a write may go here: `/advocate` itself (only to create it)
    /// or anything under it. AGENTS.md: never delete or overwrite anything
    /// outside `/advocate/` on the card, least of all `/sd2snes/`.
    pub fn writable(&self) -> Result<(), String> {
        match self.components().first() {
            Some(first) if first.eq_ignore_ascii_case(WRITABLE) => Ok(()),
            _ => Err(format!(
                "{}: this tool writes only under /{WRITABLE}/ on the card (the firmware, its settings and the saves live outside it)",
                self.0
            )),
        }
    }
}

impl std::fmt::Display for SdPath {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(s: &str) -> Result<String, String> {
        SdPath::parse(s).map(|p| p.0)
    }

    #[test]
    fn normalises_dots_and_slashes() {
        assert_eq!(p("/advocate//a/./b/../c/").unwrap(), "/advocate/a/c");
        assert_eq!(p("/").unwrap(), "/");
        assert_eq!(p("/a/..").unwrap(), "/");
    }

    #[test]
    fn refuses_what_fatfs_would_read_another_way() {
        assert!(
            p("advocate/x").is_err(),
            "relative: FatFs has a current directory"
        );
        assert!(p("/..").is_err());
        assert!(p("/advocate/../../sd2snes").is_err());
        assert!(
            p("/advocate\\..\\sd2snes").is_err(),
            "\\ separates in FatFs"
        );
        assert!(p("/advocate/0:/x").is_err(), ": names a drive");
        assert!(
            p("/advocate/.. /x").is_err(),
            "FAT drops the trailing space"
        );
        assert!(p("/advocate/a./x").is_err());
        assert!(
            p("/advocate/caf\u{e9}").is_err(),
            "names are code page 1252, not UTF-8"
        );
        assert!(p("/advocate/a\u{1}b").is_err());
        assert!(p(&format!("/advocate/{}", "a".repeat(300))).is_err());
    }

    #[test]
    fn writes_only_under_advocate() {
        for ok in [
            "/advocate",
            "/advocate/x",
            "/ADVOCATE/x",
            "/advocate/a/../b",
            "/sd2snes/../advocate/x",
        ] {
            assert!(SdPath::parse(ok).unwrap().writable().is_ok(), "{ok}");
        }
        for bad in [
            "/",
            "/sd2snes/x",
            "/advocate/../sd2snes/x",
            "/advocatex/y",
            "/x/advocate/y",
        ] {
            assert!(SdPath::parse(bad).unwrap().writable().is_err(), "{bad}");
        }
    }

    #[test]
    fn splits_into_parent_and_name() {
        let x = SdPath::parse("/advocate/a/b.sfc").unwrap();
        let (parent, name) = x.split().unwrap();
        assert_eq!((parent.as_str(), name), ("/advocate/a", "b.sfc"));
        let (parent, name) = SdPath::parse("/advocate")
            .unwrap()
            .split()
            .map(|(p, n)| (p.0, n.to_string()))
            .unwrap();
        assert_eq!((parent.as_str(), name.as_str()), ("/", "advocate"));
        assert!(SdPath::parse("/").unwrap().split().is_none());
    }
}
