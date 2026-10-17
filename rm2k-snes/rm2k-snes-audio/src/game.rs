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
    Ok(project.auto_patches()?.join("music").join("ceilings.toml"))
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
            // The earliest extension of `extensions` that has a file wins,
            // not the first file the directory happens to list: a song can
            // be both a MIDI and a WAV, and which one is the caller's choice.
            let found = entries(&sub)
                .into_iter()
                .filter_map(|file| {
                    let (base, ext) = splitext(&file);
                    let rank = extensions.iter().position(|e| *e == ext.to_lowercase())?;
                    (base.to_lowercase() == name.to_lowercase()).then(|| (rank, file.clone()))
                })
                .min();
            if let Some((_, file)) = found {
                return Some(sub.join(file));
            }
        }
    }
    None
}

/// What a song can be: a MIDI, or a WAV the SPC700 does not play but an
/// MSU-1 track can come from. In this order the SPC700 asks for it: the
/// MIDI first, the one thing it can play.
const TRACK_EXTENSIONS: [&str; 2] = [".mid", ".wav"];

/// And in this one the MSU-1 does: the game's own recording first, over
/// rendering a MIDI of the same song.
const RECORDING_FIRST: [&str; 2] = [".wav", ".mid"];

impl Game {
    fn dirs(&self) -> Vec<&Path> {
        let mut dirs = vec![self.game_dir.as_path()];
        if let Some(rtp) = &self.rtp_dir {
            dirs.push(rtp);
        }
        dirs
    }

    /// The song's file: the game's and, if it is not there, the RTP's,
    /// which is how RM2k looks for it. None if it is in neither. The MIDI
    /// if there is one, which is what the SPC700 plays.
    ///
    /// **A song can have both**, a `.wav` the game plays and a `.mid` under
    /// the same name: Zounds' title theme is a recording, and a MIDI of it
    /// was put next to it for the cartridge without MSU-1. Then this gives
    /// the MIDI and [`Self::track_source`] the WAV. EasyRPG takes the WAV
    /// over the MIDI (`MUSIC_TYPES` in its `filefinder.h`), so the game
    /// plays the same there with the MIDI next to it; RPG Maker 2003's own
    /// order was not checked.
    pub fn song_path(&self, name: &str) -> Option<PathBuf> {
        if name.is_empty() {
            return None;
        }
        find_resource(&self.dirs(), "Music", name, &TRACK_EXTENSIONS)
    }

    /// Where the song's MSU-1 track comes from: like [`Self::song_path`],
    /// but the WAV when there is one.
    pub fn track_source(&self, name: &str) -> Option<PathBuf> {
        if name.is_empty() {
            return None;
        }
        find_resource(&self.dirs(), "Music", name, &RECORDING_FIRST)
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
    ///
    /// **And last, the RTP ones the game's events and maps name** —a
    /// `PlayBGM` anywhere in the game, not only in the cartridge:
    /// `named_songs`— that are neither the game's nor the `System`'s, sorted.
    /// After the `System`'s and not mixed with them, so that a game that
    /// had none of these keeps every number it had. Until 2026-10-02 these
    /// had no track and played through the SPC700 even with the MSU-1.
    pub fn track_numbers(&self, system_songs: &[String], named_songs: &[String]) -> Result<BTreeMap<String, u8>> {
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
        let named: BTreeSet<String> = named_songs
            .iter()
            .map(|s| s.to_lowercase())
            .filter(|s| !game.contains(s) && !system.contains(s) && rtp.contains(s))
            .collect();
        let mut order: Vec<&String> = game.iter().chain(system.iter()).chain(named.iter()).collect();
        // The number goes in a byte of `song_msu`, and $FF is "no track".
        if order.len() > 0xFE {
            // **Past the byte, only the game's songs that something names**:
            // a song no `PlayBGM`, map or `System` names can never play, and
            // `named_songs` is the whole game's, not the cartridge's, so the
            // numbers are still the same in any cartridge. It is the
            // fallback and not the rule because the rule kept every number
            // of the games that fit —A Blurred Line ships 230 songs and names
            // about a hundred—, and renumbering their tracks means copying
            // them all to the card again. The track could also go in two
            // bytes —MSU-1 numbers sixteen bits—, but that is a wider
            // `song_msu` and a runtime change for songs that never play.
            let called: BTreeSet<String> =
                system_songs.iter().chain(named_songs).map(|s| s.to_lowercase()).collect();
            let all = order.len();
            order = game
                .iter()
                .filter(|s| called.contains(*s))
                .chain(system.iter())
                .chain(named.iter())
                .collect();
            if order.len() > 0xFE {
                return Err(Bad::answer(format!(
                    "Music/ has {all} songs, the game names {} of them and the track goes in a byte",
                    order.len()
                )));
            }
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
            .get("songs")
            .and_then(|t| t.as_table())
            .ok_or_else(|| Bad::usage(format!("{}: has no [songs]", path.display())))?;
        songs
            .iter()
            .map(|(name, row)| {
                row.get("headroom")
                    .and_then(|v| v.as_float().or_else(|| v.as_integer().map(|i| i as f64)))
                    .map(|v| (name.clone(), v))
                    .ok_or_else(|| Bad::usage(format!("{}: {name} has no headroom", path.display())))
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

    /// The RTP songs the game names go after the `System`'s, so naming one
    /// does not move any number a game already had.
    #[test]
    fn the_named_rtp_songs_go_last() {
        let root = std::env::temp_dir().join(format!("tracks-{}", std::process::id()));
        let touch = |dir: &str, names: &[&str]| {
            let music = root.join(dir).join("Music");
            std::fs::create_dir_all(&music).unwrap();
            for n in names {
                std::fs::write(music.join(n), b"").unwrap();
            }
        };
        touch("game", &["Town.mid", "battle.MID"]);
        touch("rtp", &["Farewell2.mid", "GameOver3.mid", "Ride1.mid", "Unused.mid"]);
        let game = Game {
            game_dir: root.join("game"),
            rtp_dir: Some(root.join("rtp")),
            project: Project::from_text(&root, "").unwrap(),
        };
        let system = ["GameOver3".to_string(), "Ride1".to_string(), "Town".to_string()];
        let before = game.track_numbers(&system, &[]).unwrap();
        let named = ["Farewell2".to_string(), "Town".to_string(), "Missing".to_string()];
        let after = game.track_numbers(&system, &named).unwrap();
        let _ = std::fs::remove_dir_all(&root);
        for (name, number) in &before {
            assert_eq!(after.get(name), Some(number), "{name} moved");
        }
        assert_eq!(after.get("farewell2"), Some(&5));
        assert_eq!(after.len(), 5, "{after:?}");
    }

    /// A `Music/` with more files than a byte numbers —Vampires Dawn has
    /// 281, and names about 110— numbers only the ones the game names: the
    /// others can never play.
    #[test]
    fn a_music_folder_past_the_byte_numbers_only_the_named_songs() {
        let root = std::env::temp_dir().join(format!("tracks-past-{}", std::process::id()));
        let music = root.join("game").join("Music");
        std::fs::create_dir_all(&music).unwrap();
        for k in 0..300 {
            std::fs::write(music.join(format!("song{k:03}.mid")), b"").unwrap();
        }
        let rtp = root.join("rtp").join("Music");
        std::fs::create_dir_all(&rtp).unwrap();
        for n in ["Ride1.mid", "Farewell2.mid"] {
            std::fs::write(rtp.join(n), b"").unwrap();
        }
        let game = Game {
            game_dir: root.join("game"),
            rtp_dir: Some(root.join("rtp")),
            project: Project::from_text(&root, "").unwrap(),
        };
        let system = ["Song299".to_string(), "Ride1".to_string()];
        let named = ["song007".to_string(), "Farewell2".to_string(), "song120".to_string()];
        let tracks = game.track_numbers(&system, &named);
        let _ = std::fs::remove_dir_all(&root);
        let expected: BTreeMap<String, u8> =
            [("song007", 1), ("song120", 2), ("song299", 3), ("ride1", 4), ("farewell2", 5)]
                .into_iter()
                .map(|(n, k)| (n.to_string(), k))
                .collect();
        assert_eq!(tracks.unwrap(), expected);
    }

    /// A song with both a MIDI and a WAV under its name: the SPC700 plays
    /// the MIDI and the MSU-1 track comes from the WAV.
    #[test]
    fn a_song_with_a_midi_and_a_wav_uses_each_where_it_plays() {
        let root = std::env::temp_dir().join(format!("both-{}", std::process::id()));
        let music = root.join("game").join("Music");
        std::fs::create_dir_all(&music).unwrap();
        for n in ["04 - Cavern.wav", "04 - Cavern.mid", "Title.MID", "Title.WAV", "Town.mid", "Battle.wav"] {
            std::fs::write(music.join(n), b"").unwrap();
        }
        let game = Game { game_dir: root.join("game"), rtp_dir: None, project: Project::from_text(&root, "").unwrap() };
        let file = |p: Option<PathBuf>| p.map(|p| p.file_name().unwrap().to_string_lossy().into_owned());
        let midi = ["04 - Cavern", "Title", "Town", "Battle"].map(|n| file(game.song_path(n)));
        let track = ["04 - Cavern", "Title", "Town", "Battle"].map(|n| file(game.track_source(n)));
        let numbers = game.track_numbers(&[], &[]).unwrap();
        let _ = std::fs::remove_dir_all(&root);
        let some = |s: &str| Some(s.to_string());
        assert_eq!(midi, [some("04 - Cavern.mid"), some("Title.MID"), some("Town.mid"), some("Battle.wav")]);
        assert_eq!(track, [some("04 - Cavern.wav"), some("Title.WAV"), some("Town.mid"), some("Battle.wav")]);
        assert_eq!(numbers.len(), 4, "a pair is one song and one track: {numbers:?}");
    }
}
