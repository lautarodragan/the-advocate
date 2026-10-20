//! The project: the game being built, found by its file.

use std::fmt;
use std::path::{Path, PathBuf};

use toml::{Table, Value};

use crate::paths::absolute;

/// The project file's name. A game declares itself by having one at its root.
pub const FILENAME: &str = "advocate.toml";

/// What the project file was called until 2026-10-20. It is not read: a game
/// that still has one is found, and told to rename it, instead of being
/// skipped for some other project further up or reported as missing.
const OLD_FILENAME: &str = "rm2k-snes.toml";

/// What stops a tool before it does anything: no project, a setting that is
/// missing or has the wrong type, a machine value nobody passed. What fixes
/// it is how the tool was run or what the game declares, never the tool's
/// code, so it is a message and not a panic.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

impl From<String> for Error {
    fn from(message: String) -> Self {
        Error(message)
    }
}

/// So a tool whose errors are plain messages can use `?` on these.
impl From<Error> for String {
    fn from(error: Error) -> Self {
        error.0
    }
}

/// A game: its root, and the settings its project file declares.
#[derive(Debug, Clone)]
pub struct Project {
    directory: PathBuf,
    settings: Table,
}

impl Project {
    /// The nearest directory, `start` or one above it, that has a project
    /// file —or one with the old name, which `open` refuses with what to
    /// do—; or None. It is how cargo finds its `Cargo.toml`.
    pub fn find(start: &Path) -> Option<PathBuf> {
        let mut current = absolute(start);
        loop {
            if current.join(FILENAME).is_file() || current.join(OLD_FILENAME).is_file() {
                return Some(current);
            }
            if !current.pop() {
                return None;
            }
        }
    }

    /// The project in `explicit` —that is `--project`—, or the one found
    /// from the current directory upwards.
    pub fn locate(explicit: Option<&Path>) -> Result<Project, Error> {
        match explicit {
            Some(directory) => Project::open(directory),
            None => {
                let start = std::env::current_dir()
                    .map_err(|e| Error(format!("cannot read the current directory: {e}")))?;
                let found = Project::find(&start).ok_or_else(|| {
                    Error(format!(
                        "found no {FILENAME} in {} nor in any folder above it: run this \
                         from inside the project, or pass it --project <directory>",
                        start.display()
                    ))
                })?;
                Project::open(&found)
            }
        }
    }

    /// The project whose root is `directory`, without searching.
    pub fn open(directory: &Path) -> Result<Project, Error> {
        let directory = absolute(directory);
        let file = directory.join(FILENAME);
        if !file.is_file() && directory.join(OLD_FILENAME).is_file() {
            return Err(Error(format!(
                "{} has {OLD_FILENAME}, which is called {FILENAME} since 2026-10-20: rename it",
                directory.display()
            )));
        }
        if !file.is_file() {
            return Err(Error(format!(
                "{} has no {FILENAME}: --project is the directory where that file is",
                directory.display()
            )));
        }
        let text = std::fs::read_to_string(&file)
            .map_err(|e| Error(format!("{}: {e}", file.display())))?;
        Project::from_text(&directory, &text)
    }

    /// A project from the text of its file, as if it were at `directory`:
    /// what the tests use, so they do not need one on disk.
    pub fn from_text(directory: &Path, text: &str) -> Result<Project, Error> {
        let settings: Table = text
            .parse()
            .map_err(|e| Error(format!("{}: {e}", directory.join(FILENAME).display())))?;
        Ok(Project {
            directory: absolute(directory),
            settings,
        })
    }

    /// The project root: where its file is.
    pub fn directory(&self) -> &Path {
        &self.directory
    }

    /// The project file itself.
    pub fn file(&self) -> PathBuf {
        self.directory.join(FILENAME)
    }

    // --- The settings ------------------------------------------------------

    /// The whole file, as it was read: for whoever hands it on as is, like
    /// `rm2k-snes-project`. A tool that wants one setting asks for it with
    /// the functions below, which name the key when it is missing.
    pub fn settings(&self) -> &Table {
        &self.settings
    }

    /// The setting at `keys` —`["rom", "name"]` is `[rom] name`—. Fails
    /// naming the first key that is missing.
    pub fn value(&self, keys: &[&str]) -> Result<&Value, Error> {
        let mut table = &self.settings;
        for (k, key) in keys.iter().enumerate() {
            let found = table.get(*key).ok_or_else(|| self.missing(&keys[..=k]))?;
            if k + 1 == keys.len() {
                return Ok(found);
            }
            table = found
                .as_table()
                .ok_or_else(|| self.missing(&keys[..=k + 1]))?;
        }
        Err(Error(format!(
            "{}: no key asked for",
            self.file().display()
        )))
    }

    fn missing(&self, keys: &[&str]) -> Error {
        Error(format!(
            "{}: missing key {}",
            self.file().display(),
            keys.join(".")
        ))
    }

    /// The error for a setting that is there with another type.
    pub fn wrong_type(&self, keys: &[&str], expected: &str, found: &Value) -> Error {
        Error(format!(
            "{}: {} must be {expected} and is {found}",
            self.file().display(),
            keys.join(".")
        ))
    }

    pub fn int(&self, keys: &[&str]) -> Result<i64, Error> {
        let v = self.value(keys)?;
        v.as_integer()
            .ok_or_else(|| self.wrong_type(keys, "int", v))
    }

    /// An int setting that may be missing, and then is `default`. Only for
    /// a setting whose absence means "as if it were not there" —a knob at
    /// rest, like `[text] letter_spacing`—: one whose default would be
    /// some other game's value is asked for with [`Project::int`], which
    /// names it when it is missing. There with another type, it is an error.
    pub fn int_or(&self, keys: &[&str], default: i64) -> Result<i64, Error> {
        match self.value(keys) {
            Err(_) => Ok(default),
            Ok(_) => self.int(keys),
        }
    }

    pub fn boolean(&self, keys: &[&str]) -> Result<bool, Error> {
        let v = self.value(keys)?;
        v.as_bool().ok_or_else(|| self.wrong_type(keys, "bool", v))
    }

    pub fn string(&self, keys: &[&str]) -> Result<&str, Error> {
        let v = self.value(keys)?;
        v.as_str().ok_or_else(|| self.wrong_type(keys, "str", v))
    }

    pub fn list(&self, keys: &[&str]) -> Result<&[Value], Error> {
        let v = self.value(keys)?;
        v.as_array()
            .map(|a| a.as_slice())
            .ok_or_else(|| self.wrong_type(keys, "list", v))
    }

    pub fn table(&self, keys: &[&str]) -> Result<&Table, Error> {
        let v = self.value(keys)?;
        v.as_table().ok_or_else(|| self.wrong_type(keys, "dict", v))
    }

    /// A list of integers.
    pub fn ints(&self, keys: &[&str]) -> Result<Vec<i64>, Error> {
        let list = self.list(keys)?;
        list.iter()
            .map(|v| v.as_integer())
            .collect::<Option<Vec<_>>>()
            .ok_or_else(|| self.wrong_type(keys, "a list of int", self.value(keys).unwrap()))
    }

    /// A list of strings.
    pub fn strings(&self, keys: &[&str]) -> Result<Vec<String>, Error> {
        let list = self.list(keys)?;
        list.iter()
            .map(|v| v.as_str().map(str::to_owned))
            .collect::<Option<Vec<_>>>()
            .ok_or_else(|| self.wrong_type(keys, "a list of str", self.value(keys).unwrap()))
    }

    /// A text setting that ends up in the ROM as is: printable ASCII without
    /// quotes —it goes between quotes in an assembler file—, exactly
    /// `length` characters long or at most `max_length`.
    pub fn ascii(
        &self,
        keys: &[&str],
        length: Option<usize>,
        max_length: Option<usize>,
    ) -> Result<&str, Error> {
        let text = self.string(keys)?;
        let name = keys.join(".");
        let file = self.file();
        if !text.chars().all(|c| (' '..='~').contains(&c) && c != '"') {
            return Err(Error(format!(
                "{}: {name} must be printable ASCII without quotes, and is {text:?}",
                file.display()
            )));
        }
        let n = text.chars().count();
        if let Some(length) = length {
            if n != length {
                return Err(Error(format!(
                    "{}: {name} must have {length} characters, and has {n}",
                    file.display()
                )));
            }
        }
        if let Some(max) = max_length {
            if !(1..=max).contains(&n) {
                return Err(Error(format!(
                    "{}: {name} must have 1 to {max} characters, and has {n}",
                    file.display()
                )));
            }
        }
        Ok(text)
    }

    // --- How the game is laid out: `[paths]` -----------------------------

    /// A path from `[paths]`: the file declares it, relative to itself.
    pub fn path(&self, key: &str) -> Result<PathBuf, Error> {
        Ok(absolute(self.directory.join(self.string(&["paths", key])?)))
    }

    /// `[paths] build`: everything that gets built, and nothing versioned.
    pub fn build(&self) -> Result<PathBuf, Error> {
        self.path("build")
    }

    /// `[paths] data`: the game dumped to JSON.
    pub fn data(&self) -> Result<PathBuf, Error> {
        self.path("data")
    }

    /// `[paths] patches`: what was decided about the game.
    pub fn patches(&self) -> Result<PathBuf, Error> {
        self.path("patches")
    }

    /// What was redesigned by hand, inside the patches.
    pub fn manual_patches(&self) -> Result<PathBuf, Error> {
        Ok(self.patches()?.join("manual"))
    }

    /// The maps inside the hand-made patches, forks and new ones: see
    /// [`crate::own_files::MAPS`].
    pub fn manual_maps(&self) -> Result<PathBuf, Error> {
        Ok(self.manual_patches()?.join(crate::own_files::MAPS))
    }

    /// The port's own files, which replace the game's by name: the RM2k
    /// folders of the hand-made patches, which are the hand-made patches
    /// themselves. See [`crate::own_files`].
    pub fn own_files(&self) -> Result<PathBuf, Error> {
        self.manual_patches()
    }

    /// What the converter decided and is versioned, inside the patches.
    pub fn auto_patches(&self) -> Result<PathBuf, Error> {
        Ok(self.patches()?.join("auto"))
    }

    /// `[paths] cases`: the test cases, one JSON per case.
    pub fn cases(&self) -> Result<PathBuf, Error> {
        self.path("cases")
    }
}
