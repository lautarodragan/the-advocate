//! What comes from the game: where its songs and sound effects are, what
//! its project file decides about them, and each song's MSU-1 track.

use crate::fail::{Bad, Result};
use rm2k_project::Project;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// Where the game and the RTP are, and what the game decides.
pub struct Game {
    pub game_dir: PathBuf,
    pub rtp_dir: Option<PathBuf>,
    pub project: Project,
}

/// Where a project's measured volume ceilings are: with what was decided
/// automatically, in its patches. Whoever reads the table and whoever
/// writes it ask here.
pub fn ceilings_path(project: &Project) -> Result<PathBuf> {
    Ok(project.auto_patches()?.join("musica").join("techos.toml"))
}

/// Python's `os.path.splitext`: the extension is from the last dot, unless
/// everything before it is dots.
fn splitext(name: &str) -> (&str, &str) {
    match name.rfind('.') {
        Some(i) if name[..i].chars().any(|c| c != '.') => (&name[..i], &name[i..]),
        _ => (name, ""),
    }
}

fn entries(dir: &Path) -> Vec<String> {
    match std::fs::read_dir(dir) {
        Ok(read) => read
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect(),
        Err(_) => Vec::new(),
    }
}

/// Looks for `<dir>/<folder>/<name>.<ext>`, case-insensitively, in each of
/// `dirs` in turn. RM2k stores names without extension and the games were
/// made on Windows, so a name says nothing about the file's real case.
pub fn find_resource(dirs: &[&Path], folder: &str, name: &str, extensions: &[&str]) -> Option<PathBuf> {
    for dir in dirs {
        if !dir.is_dir() {
            continue;
        }
        for entry in entries(dir) {
            if entry.to_lowercase() != folder.to_lowercase() {
                continue;
            }
            let sub = dir.join(&entry);
            for file in entries(&sub) {
                let (base, ext) = splitext(&file);
                if base.to_lowercase() == name.to_lowercase()
                    && extensions.contains(&ext.to_lowercase().as_str())
                {
                    return Some(sub.join(file));
                }
            }
        }
    }
    None
}

/// What a song can be: a MIDI, or a WAV the SPC700 does not play but an
/// MSU-1 track can come from.
const TRACK_EXTENSIONS: [&str; 2] = [".mid", ".wav"];

impl Game {
    fn dirs(&self) -> Vec<&Path> {
        let mut dirs = vec![self.game_dir.as_path()];
        if let Some(rtp) = &self.rtp_dir {
            dirs.push(rtp);
        }
        dirs
    }

    /// The song's file: the game's and, if it is not there, the RTP's,
    /// which is how RM2k looks for it. None if it is in neither.
    pub fn song_path(&self, name: &str) -> Option<PathBuf> {
        if name.is_empty() {
            return None;
        }
        find_resource(&self.dirs(), "Music", name, &TRACK_EXTENSIONS)
    }

    /// A sound effect's WAV, looked for the same way.
    pub fn sound_path(&self, name: &str) -> Option<PathBuf> {
        find_resource(&self.dirs(), "Sound", name, &[".wav", ".WAV"])
    }

    /// {lowercase song name: MSU-1 track number}.
    ///
    /// **The number comes from the game, not the cartridge**: it is the
    /// song's place in the sorted list of `Music/` —case-insensitive,
    /// counting from 1—. The song's index in the cartridge would have been
    /// the obvious choice, but that is decided by the order in which the
    /// `PlayBGM`s appear when compiling, so a new map would shift the
    /// numbering of the ones after it, and renumbering means hundreds of
    /// megabytes to redo and copy to the card again. `Music/` belongs to the
    /// original game and does not change, so a song's number is always the
    /// same, in any cartridge: a new song is a new file and nothing else.
    ///
    /// **And after them, the RTP ones named by the database's `System`**
    /// —`system_songs`— that the game does not ship, sorted, so they do not
    /// shift any of the game's; only those, because the whole RTP does not
    /// fit in the byte.
    pub fn track_numbers(&self, system_songs: &[String]) -> Result<BTreeMap<String, u8>> {
        fn names(dir: &Path) -> BTreeSet<String> {
            let mut out = BTreeSet::new();
            if !dir.is_dir() {
                return out;
            }
            let folder = entries(dir).into_iter().find(|e| e.to_lowercase() == "music");
            if let Some(folder) = folder {
                for file in entries(&dir.join(folder)) {
                    let (base, ext) = splitext(&file);
                    if TRACK_EXTENSIONS.contains(&ext.to_lowercase().as_str()) {
                        out.insert(base.to_lowercase());
                    }
                }
            }
            out
        }
        let game = names(&self.game_dir);
        let rtp = self.rtp_dir.as_deref().map(names).unwrap_or_default();
        let system: BTreeSet<String> = system_songs
            .iter()
            .map(|s| s.to_lowercase())
            .filter(|s| !game.contains(s) && rtp.contains(s))
            .collect();
        let order: Vec<&String> = game.iter().chain(system.iter()).collect();
        // The number goes in a byte of `song_msu`, and $FF is "no track".
        if order.len() > 0xFE {
            return Err(Bad::answer(format!(
                "Music/ has {} songs and the track goes in a byte",
                order.len()
            )));
        }
        Ok(order.into_iter().enumerate().map(|(i, n)| (n.clone(), i as u8 + 1)).collect())
    }

    // --- what the game decides ---------------------------------------------
    //
    // **Which sound effects go whole and which ones the music pays for are
    // the game's decisions by ear**, and they live in its project file with
    // the reason for each. They are read when used.

    /// {sound effect: rate in Hz} of the ones that go whole, with no cap or
    /// loop: they end when the sample ends, which is what they do in RM2k.
    /// What one takes beyond the usual has to fit in what the music leaves
    /// free in each package it is in, except for those in
    /// [`Self::paid_by_music`].
    pub fn whole_effects(&self) -> Result<BTreeMap<String, i64>> {
        let table = self.project.table(&["sound_effects", "whole"])?;
        table
            .iter()
            .map(|(name, rate)| {
                rate.as_integer().map(|r| (name.clone(), r)).ok_or_else(|| {
                    Bad::usage(format!(
                        "{}: sound_effects.whole.{name} must be an integer",
                        self.project.file().display()
                    ))
                })
            })
            .collect()
    }

    /// The whole ones that, if they do not fit in the free space, lower the
    /// music's rate.
    pub fn paid_by_music(&self) -> Result<BTreeSet<String>> {
        Ok(self.project.strings(&["sound_effects", "paid_by_music"])?.into_iter().collect())
    }

    /// Up to how many directory entries the first round of copies goes: the
    /// ones the sound effects took when each had its own. The game measured
    /// it.
    pub fn effect_slots_of_first_copies(&self) -> Result<i64> {
        Ok(self.project.int(&["music", "effect_slots_of_first_copies"])?)
    }

    /// Where each song's measured volume ceiling is: a table the game
    /// versions.
    pub fn ceilings_path(&self) -> Result<PathBuf> {
        ceilings_path(&self.project)
    }

    /// {song: headroom} from the versioned table; empty if it does not
    /// exist. A song that is not there goes with `sdsp::HEADROOM`.
    ///
    /// **It is not written by hand**: a tool measures it by playing each
    /// song in the ROM, and what remains is versioned data. Every change to
    /// the mix —the samples, the envelopes, the allocation— makes it stale,
    /// and each song's `fingerprint` is what says so.
    pub fn ceilings(&self) -> Result<BTreeMap<String, f64>> {
        let path = self.ceilings_path()?;
        let text = match std::fs::read_to_string(&path) {
            Ok(t) => t,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(BTreeMap::new()),
            Err(e) => return Err(Bad::usage(format!("{}: {e}", path.display()))),
        };
        let table: toml::Table =
            text.parse().map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        let songs = table
            .get("temas")
            .and_then(|t| t.as_table())
            .ok_or_else(|| Bad::usage(format!("{}: has no [temas]", path.display())))?;
        songs
            .iter()
            .map(|(name, row)| {
                row.get("aire")
                    .and_then(|v| v.as_float().or_else(|| v.as_integer().map(|i| i as f64)))
                    .map(|v| (name.clone(), v))
                    .ok_or_else(|| Bad::usage(format!("{}: {name} has no aire", path.display())))
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splitext_is_pythons() {
        assert_eq!(splitext("Rain1.wav"), ("Rain1", ".wav"));
        assert_eq!(splitext(".hidden"), (".hidden", ""));
        assert_eq!(splitext("a.b.mid"), ("a.b", ".mid"));
        assert_eq!(splitext("..x"), ("..x", ""));
        assert_eq!(splitext("noext"), ("noext", ""));
    }
}
