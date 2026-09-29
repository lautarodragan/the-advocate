//! What belongs to the machine and not to the project: where the original
//! game is, the RTP, the SoundFont, the replacements for the MSU-1 tracks,
//! the cache, the test cartridges and where builds are delivered.
//!
//! **It arrives by flags, not by environment variables.** Each executable
//! adds the flags it uses —[`arguments`]—, reads them back into an
//! [`Environment`], and passes on to the tools it runs the ones they need
//! —[`Environment::as_flags`]—. Which variable holds which value, and this
//! machine's values, belong to the caller.
//!
//! **A value nobody set is an error, not a default**, except the ones that
//! hang off the project —the cache and the test cartridges, inside its
//! `build`—: a machine default would be one machine's.

use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::{Path, PathBuf};

use clap::{Arg, ArgMatches};

use crate::paths::absolute;
use crate::{Error, Project};

/// One machine value: its name, its flag and what it is.
pub struct Flag {
    pub name: &'static str,
    pub flag: &'static str,
    pub help: &'static str,
}

/// Every value that can be set, in the order their flags are passed on.
pub const FLAGS: &[Flag] = &[
    Flag {
        name: "game_dir",
        flag: "--game-dir",
        help: "the original RM2k project, where the PNGs, the MIDIs and the .lmu files come from",
    },
    Flag {
        name: "rtp_dir",
        flag: "--rtp-dir",
        help: "the RTP the game was built with: what the game does not ship is looked up there",
    },
    Flag {
        name: "soundfont",
        flag: "--soundfont",
        help: "the bank the SPC700 samples and the MSU-1 tracks come from",
    },
    Flag {
        name: "replacements",
        flag: "--replacements",
        help: "where to look for a <song>.mp3 —or .ogg, .flac, .wav— that replaces that \
               song's MIDI in the MSU-1 tracks",
    },
    Flag {
        name: "cache",
        flag: "--cache",
        help: "the converter's disk cache. Without this, cache/ inside the project's build",
    },
    Flag {
        name: "test_cartridges",
        flag: "--test-cartridges",
        help: "where the test cartridges are built. Without this, tests/ inside the \
               project's build",
    },
    Flag {
        name: "shared",
        flag: "--shared",
        help: "the folder where what gets built is delivered",
    },
];

fn flag(name: &str) -> &'static Flag {
    FLAGS
        .iter()
        .find(|f| f.name == name)
        .unwrap_or_else(|| panic!("{name} is not a machine value"))
}

/// The flags of `names`, to add to an executable's command line.
pub fn arguments(names: &[&str]) -> Vec<Arg> {
    names
        .iter()
        .map(|name| {
            let f = flag(name);
            Arg::new(f.name)
                .long(&f.flag[2..])
                .value_name("PATH")
                .help(f.help)
        })
        .collect()
}

/// The values that were set, each made absolute: whoever reads them may run
/// standing in another directory.
#[derive(Debug, Default, Clone)]
pub struct Environment {
    values: BTreeMap<&'static str, PathBuf>,
}

impl Environment {
    /// What came on the command line for `names`.
    pub fn from_matches(matches: &ArgMatches, names: &[&str]) -> Environment {
        let mut environment = Environment::default();
        for name in names {
            if let Some(value) = matches.get_one::<String>(name) {
                environment.set(name, value);
            }
        }
        environment
    }

    /// Sets one value. A name that is not in [`FLAGS`] is a programming
    /// error, not the caller's.
    pub fn set(&mut self, name: &str, value: impl AsRef<Path>) {
        self.values.insert(flag(name).name, absolute(value));
    }

    /// The set values of `names`, as flags, in the order of [`FLAGS`]: to
    /// pass them on to another tool that runs in a separate process.
    pub fn as_flags(&self, names: &[&str]) -> Vec<OsString> {
        let mut out = Vec::new();
        for f in FLAGS {
            if names.contains(&f.name) {
                if let Some(value) = self.values.get(f.name) {
                    out.push(OsString::from(f.flag));
                    out.push(value.clone().into_os_string());
                }
            }
        }
        out
    }

    fn require(&self, name: &str) -> Result<&Path, Error> {
        let f = flag(name);
        self.values.get(f.name).map(PathBuf::as_path).ok_or_else(|| {
            Error(format!(
                "missing {}: {}. It belongs to the machine, so it has no default value; \
                 whoever runs this passes it",
                f.flag, f.help
            ))
        })
    }

    pub fn game(&self) -> Result<&Path, Error> {
        self.require("game_dir")
    }

    pub fn rtp(&self) -> Result<&Path, Error> {
        self.require("rtp_dir")
    }

    pub fn soundfont(&self) -> Result<&Path, Error> {
        self.require("soundfont")
    }

    pub fn shared(&self) -> Result<&Path, Error> {
        self.require("shared")
    }

    /// Where the MSU-1 track replacements are looked up, or None: without
    /// replacements each track comes from its MIDI.
    pub fn msu_replacements(&self) -> Option<&Path> {
        self.values.get("replacements").map(PathBuf::as_path)
    }

    /// The converter's disk cache: `--cache`, or `cache/` in the project's
    /// build.
    pub fn cache(&self, project: &Project) -> Result<PathBuf, Error> {
        match self.values.get("cache") {
            Some(p) => Ok(p.clone()),
            None => Ok(project.build()?.join("cache")),
        }
    }

    /// Where the test cartridges are built: `--test-cartridges`, or `tests/`
    /// in the project's build.
    pub fn test_cartridges(&self, project: &Project) -> Result<PathBuf, Error> {
        match self.values.get("test_cartridges") {
            Some(p) => Ok(p.clone()),
            None => Ok(project.build()?.join("tests")),
        }
    }
}
