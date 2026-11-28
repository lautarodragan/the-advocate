//! A cartridge's MSU-1 tracks, from the game's MIDIs.
//!
//! MSU-1 is not Super Nintendo hardware: it is an extension supported by
//! the FX Pak Pro and by emulators, with the music in PCM files next to the
//! ROM. Every song has a track —the number comes from the compiler, in
//! `music.json`—, and with MSU-1 the ROM silences the SPC700 and plays the
//! track; without MSU-1 the signature is not there and everything sounds as
//! always.
//!
//! A track is `<rom>-<number>.pcm`: the "MSU1" signature, the loop point in
//! samples —four bytes— and the raw audio, signed 16-bit stereo at
//! 44.1 kHz. Next to it there has to be `<rom>.msu`, which is what turns
//! MSU-1 on. That one is not written here but by whoever builds the
//! cartridge, with the other data MSU-1 serves to the ROM; for the tracks
//! it can be empty.
//!
//! The audio comes from rendering the MIDI with `fluidsynth` and **the same
//! SoundFont the samples come from**: the idea is not to change the
//! arrangement but to stop synthesizing it with eight voices and trimmed
//! samples. A song that in the game is a WAV —the SPC700 does not play it—
//! gets a track anyway, decoded with `ffmpeg` like a replacement; and one
//! that is both, a WAV and a MIDI for the SPC700, gets the WAV's.
//!
//! **Only the tracks of the cartridge's songs are built**: the ones listed
//! in the `music.json` next to the ROM, with each song's number. A
//! `<rom>-N.pcm` that no longer belongs to any song is deleted: whoever
//! copies the tracks to a card copies every one it finds.
//!
//! **A track can come from an audio file instead of the MIDI**: if the
//! replacements directory has a `<song>.mp3`, `.ogg`, `.flac` or `.wav`,
//! the track is that audio, decoded with `ffmpeg`.
//!
//! **A track that already exists is not rendered again.** What it depends
//! on —the MIDI, the SoundFont, the synthesizer and how it is normalized—
//! goes into a key, see [`Tracks::midi_key`], and what the disk cache keeps
//! under it is the sha256 of the `.pcm`, not the `.pcm`: the tracks weigh
//! hundreds of megabytes and are already on disk, next to the ROM. With
//! `NO_CACHE=1` they are all redone, which is how one checks that they come
//! out the same.
//!
//! **A MIDI's track loops like RPG_RT**: see [`rm2k_cut`]. Until
//! 2026-11-14 it was the whole render with the loop point at 0, so every
//! loop carried the two seconds of silence fluidsynth leaves after the end
//! —a bar of `hzstream`, in A Blurred Line—. The tracks from an audio file
//! still loop at 0: they bring no loop mark to read.

use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::midi;
use rm2k_project::cache;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::io::Read as _;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{mpsc, Mutex, OnceLock};

/// fluidsynth's gain. With 1.0 the songs with many voices saturate, so it
/// is rendered low and then normalized: the track's peak ends up at
/// [`PEAK`], which is almost full scale. Without this the track played at a
/// quarter of the SPC700 music's volume —measured: peak 4632 against
/// 17012— and switching from one song to another gave a jump in volume.
pub const GAIN: f64 = 0.6;
pub const PEAK: f64 = 0.97;

/// Which extensions the replacements are looked for with, in this order.
pub const EXTENSIONS: [&str; 4] = [".mp3", ".ogg", ".flac", ".wav"];

/// The disk cache's category: each track's sha256, under its key.
const CATEGORY: &str = "msu";

/// And the tracks themselves, under the same key: a hard link to the
/// build's `.pcm` when the cache is on its disk, so keeping them costs no
/// space. What a build finds here it links into its own directory. A track
/// is never written in place —see [`Tracks::one`]—, so replacing a linked
/// one leaves the cache's as it was.
const TRACKS: &str = "msu-tracks";

fn io(path: &Path, e: std::io::Error) -> Bad {
    Bad::usage(format!("{}: {e}", path.display()))
}

/// The sha256 of a file, read in pieces: a SoundFont or a track weighs
/// megabytes.
fn file_sha256(path: &Path) -> std::io::Result<String> {
    let mut f = std::fs::File::open(path)?;
    let mut h = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(cache::hex(&h.finalize()))
}

/// The sha256 of an already written file, or None if it is not there.
pub fn file_fingerprint(path: &Path) -> Option<String> {
    file_sha256(path).ok()
}

/// Where a program is on the PATH.
fn which(program: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path)
        .map(|d| d.join(program))
        .find(|p| p.is_file())
}

/// Which program produced a track: the binary on the PATH and what it says
/// its version is.
///
/// The binary goes in because it is what produces the bytes, and the
/// version text goes in because the bulk of the synthesis lives in
/// `libfluidsynth`, which the binary does not contain: updating the library
/// without the executable changing has to expire the tracks all the same.
/// **Only stdout**: stderr carries the PipeWire and ALSA warnings of a
/// machine without a sound card, and inside them goes a pointer address
/// that changes on every run with ASLR —measured: the key never repeated—.
fn program_fingerprint(program: &str, version_flag: &str, missing: &str) -> Result<String> {
    let path = which(program).ok_or_else(|| Bad::usage(missing.to_string()))?;
    let mut h = Sha256::new();
    h.update(std::fs::read(&path).map_err(|e| io(&path, e))?);
    let out = Command::new(program)
        .arg(version_flag)
        .stderr(Stdio::null())
        .output()
        .map_err(|e| Bad::usage(format!("{program}: {e}")))?;
    h.update(&out.stdout);
    Ok(cache::hex(&h.finalize()))
}

/// The code a track's bytes come from, by its source: this file, what it
/// uses from the crate —and what that uses, closed: a test checks that each
/// `crate::` they name is here—. Until 2026-11-25 the subcommand that ran
/// it, `commands/msu.rs`, was here too; the builder calls [`Tracks`] since,
/// and its going rendered every track once more.
///
/// **Not the running executable**, which is what went in until 2026-11-23:
/// it was `rm2k-snes-msu` then, with only this code in it. Since the tracks
/// are a subcommand of `rm2k-snes-audio` the executable carries the whole
/// compiler, and a change to it would have rendered every track again for
/// nothing —measured over the seven weeks before: 18 of the crate's 31
/// commits— and left one more copy of them in the cache, which keeps them
/// as hard links and has no eviction: 2.4 GB each time, A Blurred Line's
/// alone. The source still changes exactly when the code does, without
/// anyone having to remember to bump a number; a comment changed in one of
/// these files renders them again too.
const OWN_SOURCES: [(&str, &str); 4] = [
    ("tracks.rs", include_str!("tracks.rs")),
    ("midi.rs", include_str!("midi.rs")),
    ("game.rs", include_str!("game.rs")),
    ("fail.rs", include_str!("fail.rs")),
];

/// What this program is, for the key: [`OWN_SOURCES`], hashed.
fn own_version() -> Result<String> {
    let mut h = Sha256::new();
    for (name, text) in OWN_SOURCES {
        h.update(name.as_bytes());
        h.update([0]);
        h.update(text.as_bytes());
        h.update([0]);
    }
    Ok(cache::hex(&h.finalize()))
}

/// The audio file that replaces this song's MIDI, or None.
pub fn replacement(directory: Option<&Path>, name: &str) -> Option<PathBuf> {
    let directory = directory?;
    EXTENSIONS
        .iter()
        .map(|ext| directory.join(format!("{name}{ext}")))
        .find(|p| p.is_file())
}

/// The audio a `<song>.link.wav` points to, or None if `path` is not one.
///
/// Desert Nightmare ships its songs as MP3s in an `mp3/` folder next to
/// `Music/`, and in `Music/` a `.link.wav` per song: not audio, a line of
/// text with the path —`..\mp3\Credits.mp3loop`—, the convention of a patch
/// of RPG_RT that plays MP3s, the `loop` after the extension saying it
/// loops. The track is the MP3 the line names, found case-insensitively from
/// the link's folder; `ffmpeg` cannot open the link itself.
pub fn followed_link(path: &Path) -> Option<PathBuf> {
    let name = path.file_name()?.to_string_lossy().to_lowercase();
    if !name.ends_with(".link.wav") {
        return None;
    }
    let text = std::fs::read_to_string(path).ok()?;
    let line = text.lines().next()?.trim();
    let line = line
        .strip_suffix("loop")
        .or_else(|| line.strip_suffix("LOOP"))
        .unwrap_or(line);
    let mut here = path.parent()?.to_path_buf();
    for part in line.split(['\\', '/']).filter(|p| !p.is_empty()) {
        if part == ".." {
            here = here.parent()?.to_path_buf();
        } else if part != "." {
            let want = part.to_lowercase();
            let found = std::fs::read_dir(&here)
                .ok()?
                .filter_map(|e| e.ok())
                .find(|e| e.file_name().to_string_lossy().to_lowercase() == want)?;
            here = found.path();
        }
    }
    here.is_file().then_some(here)
}

/// [(name, number)] of the cartridge's songs that have a track, in order of
/// number: from the `music.json` next to the ROM.
pub fn cartridge_tracks(rom: &Path) -> Result<Vec<(String, i64)>> {
    let rom = rm2k_project::absolute(rom);
    let path = rom.parent().unwrap_or(Path::new("/")).join("music.json");
    let text = std::fs::read_to_string(&path).map_err(|_| {
        Bad::usage(format!(
            "{} is missing: the tracks are those of the cartridge's songs, so it has to be built first",
            path.display()
        ))
    })?;
    let json: Value = serde_json::from_str(&text).map_err(|e| io(&path, e.into()))?;
    let songs = json["songs"]
        .as_array()
        .ok_or_else(|| Bad::usage(format!("{}: no \"songs\"", path.display())))?;
    // By number and not by name: two songs that differ only in case are the
    // same file, and two threads writing the same track clobber each other.
    // The last one with a number wins, as in a dict.
    let mut by_number = BTreeMap::new();
    for t in songs {
        if let Some(n) = t["track"].as_i64().filter(|&n| n != 0) {
            let name = t["name"].as_str().unwrap_or_default().to_string();
            by_number.insert(n, name);
        }
    }
    Ok(by_number.into_iter().map(|(n, name)| (name, n)).collect())
}

/// A WAV's samples, if it is 16-bit stereo at 44100: the channels
/// interleaved, as they are in the file.
fn read_wav(path: &Path) -> Result<(Vec<i16>, usize)> {
    let bytes = std::fs::read(path).map_err(|e| io(path, e))?;
    let bad = || Bad::usage(format!("{} is not a WAV", path.display()));
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err(bad());
    }
    let mut format = None;
    let mut at = 12;
    while at + 8 <= bytes.len() {
        let id = &bytes[at..at + 4];
        let size = u32::from_le_bytes(bytes[at + 4..at + 8].try_into().unwrap()) as usize;
        let body = at + 8;
        if id == b"fmt " {
            let f = bytes.get(body..body + 16).ok_or_else(bad)?;
            let channels = u16::from_le_bytes([f[2], f[3]]);
            let rate = u32::from_le_bytes([f[4], f[5], f[6], f[7]]);
            let bits = u16::from_le_bytes([f[14], f[15]]);
            format = Some((channels, bits, rate));
        } else if id == b"data" {
            if format != Some((2, 16, 44100)) {
                return Err(Bad::usage(format!(
                    "{} is not 16-bit stereo at 44100",
                    path.display()
                )));
            }
            // Whole frames only, and no further than the file goes: that is
            // what reading `nframes` frames gave.
            let end = body.saturating_add(size).min(bytes.len());
            let frames = (end - body) / 4;
            let data = &bytes[body..body + frames * 4];
            let samples = data
                .chunks_exact(2)
                .map(|c| i16::from_le_bytes([c[0], c[1]]))
                .collect();
            return Ok((samples, frames));
        }
        at = body.saturating_add(size).saturating_add(size & 1);
    }
    Err(bad())
}

/// The samples of a WAV as an MSU-1 track —the signature, the loop point
/// and the audio—, normalized so the peak ends at `peak` of full scale.
/// Returns the file's bytes and the scale.
///
/// The product in double precision, truncated towards zero and clipped. A scale close enough to one is left out, and the audio goes
/// as it came.
pub fn track(samples: &[i16], loop_point: u32, peak: f64) -> (Vec<u8>, f64) {
    // In i32: the absolute value of -32768 does not fit in 16 bits.
    let top = samples.iter().map(|&s| (s as i32).abs()).max().unwrap_or(0);
    let top = if top == 0 { 1 } else { top };
    let scale = peak * 32767.0 / top as f64;
    let mut out = Vec::with_capacity(8 + samples.len() * 2);
    out.extend_from_slice(b"MSU1");
    out.extend_from_slice(&loop_point.to_le_bytes());
    let rescale = !(1.0..=1.02).contains(&scale);
    for &s in samples {
        let v = if rescale {
            (s as f64 * scale).trunc().clamp(-32768.0, 32767.0) as i16
        } else {
            s
        };
        out.extend_from_slice(&v.to_le_bytes());
    }
    (out, scale)
}

/// The frames of a MIDI rendered from its tick 0, cut to loop like RPG_RT:
/// returns the samples —channels interleaved— and the loop point in frames.
///
/// The first pass starts at `start` and the track ends at `end`, which is
/// the end of the MIDI's track and not of fluidsynth's render: fluidsynth
/// goes on two seconds after it, with the tail of the last notes and then
/// silence. From `end` the MSU-1 goes back to the loop point, which is `to`
/// counted from `start`. **The tail is cut there**: what still sounds at
/// `end` stops at once. RPG_RT keeps it sounding over the start of the next
/// pass, because its synthesizer is not reset; baking that is the next step
/// of the task `music-loop-like-rm2k`.
///
/// `to` before `start` is a song without CC111 whose first pass skips the
/// silence before its first note: RPG_RT plays that silence on every pass
/// but the first. The track can only start at 0, so that silence goes **at
/// the end**, after `end`, and the loop point is 0: the same sequence, and
/// in it goes what fluidsynth rendered there, the tail of the last notes.
/// Past the render, zeros.
///
/// **A render shorter than `end` is an error**, and the caller keeps the
/// whole render looping at 0: fluidsynth always goes on past the
/// end-of-track, so it is a file fluidsynth refused or read otherwise, and
/// `end` cannot be trusted. That also bounds what is allocated by what was
/// rendered: on 2026-11-14 a Vampires Dawn MIDI gave an end 2^32 ticks
/// away and the cut asked for eight terabytes.
pub fn rm2k_cut(
    samples: &[i16],
    start: usize,
    to: usize,
    end: usize,
) -> std::result::Result<(Vec<i16>, u32), String> {
    let frames = samples.len() / 2;
    if end > frames {
        return Err(format!(
            "the MIDI ends at {:.1} s and fluidsynth rendered {:.1} s",
            end as f64 / 44100.0,
            frames as f64 / 44100.0
        ));
    }
    // A MIDI that ends before it starts —no notes, or only an end-of-track
    // at 0— keeps the whole render, as before.
    if end <= start {
        return Ok((samples.to_vec(), 0));
    }
    let silence = start.saturating_sub(to);
    let mut out = Vec::with_capacity((end - start + silence) * 2);
    for frame in start..end + silence {
        match samples.get(frame * 2..frame * 2 + 2) {
            Some(pair) => out.extend_from_slice(pair),
            None => out.extend_from_slice(&[0, 0]),
        }
    }
    let loop_point = to.saturating_sub(start);
    // A CC111 at or past the end loops onto the end: RPG_RT keeps the song
    // there, silent. Here, the last frame.
    let loop_point = loop_point.min((end - start).saturating_sub(1));
    Ok((out, loop_point as u32))
}

/// Seconds to frames at 44.1 kHz.
fn frames_at(seconds: f64) -> usize {
    (seconds * 44100.0).round().max(0.0) as usize
}

/// Where the tracks' audio comes from, and what they are compared against.
pub struct Tracks {
    pub game: Game,
    pub soundfont: PathBuf,
    pub gain: f64,
    pub replacements: Option<PathBuf>,
    /// The disk cache, or None with `NO_CACHE=1`.
    pub cache: Option<PathBuf>,
    own: OnceLock<String>,
    fluidsynth: OnceLock<String>,
    ffmpeg: OnceLock<String>,
    font: OnceLock<String>,
    // The fingerprints are computed once, by whichever thread asks first.
    lock: Mutex<()>,
}

/// What one track came out as.
pub enum Outcome {
    /// It was already there, made from these same sources.
    Already,
    /// Made now: the line that reports it.
    Made(String),
}

impl Tracks {
    pub fn new(
        game: Game,
        soundfont: PathBuf,
        gain: f64,
        replacements: Option<PathBuf>,
        cache: Option<PathBuf>,
    ) -> Tracks {
        Tracks {
            game,
            soundfont,
            gain,
            replacements,
            cache,
            own: OnceLock::new(),
            fluidsynth: OnceLock::new(),
            ffmpeg: OnceLock::new(),
            font: OnceLock::new(),
            lock: Mutex::new(()),
        }
    }

    fn once(&self, cell: &OnceLock<String>, f: impl FnOnce() -> Result<String>) -> Result<String> {
        if let Some(v) = cell.get() {
            return Ok(v.clone());
        }
        let _guard = self.lock.lock().unwrap();
        if let Some(v) = cell.get() {
            return Ok(v.clone());
        }
        let v = f()?;
        let _ = cell.set(v.clone());
        Ok(v)
    }

    /// Everything that changes the bytes of a track rendered from a MIDI.
    ///
    /// The MIDI, the SoundFont and the synthesizer are where the audio
    /// comes from; the gain and the peak, how it is scaled; and the code
    /// that normalizes and writes it, by its source —[`OWN_SOURCES`]—.
    /// **The track number does not go in**: it does not change a single
    /// sample, only the file name.
    /// The SoundFont goes in by content and not by path: a bank can change
    /// without changing its name.
    pub fn midi_key(&self, midi: &Path) -> Result<String> {
        let own = self.once(&self.own, own_version)?;
        let synth = self.once(&self.fluidsynth, || {
            program_fingerprint(
                "fluidsynth",
                "--version",
                "fluidsynth is missing: on Arch, pacman -S fluidsynth",
            )
        })?;
        let font = self.once(&self.font, || {
            file_sha256(&self.soundfont).map_err(|e| io(&self.soundfont, e))
        })?;
        let raw = std::fs::read(midi).map_err(|e| io(midi, e))?;
        let scaling = format!("{:?} {:?}", self.gain, PEAK);
        Ok(cache::key(&[
            own.as_bytes(),
            synth.as_bytes(),
            font.as_bytes(),
            scaling.as_bytes(),
            &raw,
        ]))
    }

    /// The same, for a track that comes from an audio file: a replacement,
    /// or a song that in the game is a WAV.
    pub fn audio_key(&self, audio: &Path) -> Result<String> {
        let own = self.once(&self.own, own_version)?;
        let decoder = self.once(&self.ffmpeg, || {
            program_fingerprint(
                "ffmpeg",
                "-version",
                "ffmpeg is missing: on Arch, pacman -S ffmpeg",
            )
        })?;
        let raw = std::fs::read(audio).map_err(|e| io(audio, e))?;
        let scaling = format!("{:?}", PEAK);
        Ok(cache::key(&[
            own.as_bytes(),
            decoder.as_bytes(),
            scaling.as_bytes(),
            &raw,
        ]))
    }

    fn cached(&self, key: &str) -> Option<String> {
        String::from_utf8(cache::load(self.cache.as_ref()?, CATEGORY, key)?).ok()
    }

    /// Stores the value whole or not at all. A cache that cannot be written
    /// breaks nothing.
    fn store(&self, key: &str, value: &str) {
        if let Some(dir) = &self.cache {
            cache::store(dir, CATEGORY, key, value.as_bytes());
        }
    }

    /// Puts at `out_path` the track another build made from the same
    /// sources, if the cache keeps it and it is still what was stored —its
    /// sha256, `stored`—. Says whether it did.
    fn restore_from_the_cache(&self, key: &str, stored: &str, out_path: &Path) -> bool {
        let Some(dir) = &self.cache else {
            return false;
        };
        file_fingerprint(&cache::entry(dir, TRACKS, key)).as_deref() == Some(stored)
            && cache::fetch_file(dir, TRACKS, key, out_path)
    }

    /// One track: `<base>-<number>.pcm`.
    pub fn one(&self, base: &str, name: &str, number: i64) -> Result<Outcome> {
        let out_path = PathBuf::from(format!("{base}-{number}.pcm"));
        let mut audio = replacement(self.replacements.as_deref(), name);
        let mut midi = None;
        if audio.is_none() {
            let source = self
                .game
                .track_source(name)
                .ok_or_else(|| Bad::usage(format!("cannot find the music for {name}")))?;
            if source.to_string_lossy().to_lowercase().ends_with(".mid") {
                midi = Some(source);
            } else {
                audio = Some(followed_link(&source).unwrap_or(source));
            }
        }
        let key = match (&audio, &midi) {
            (Some(a), _) => self.audio_key(a)?,
            (None, Some(m)) => self.midi_key(m)?,
            (None, None) => unreachable!(),
        };
        // The track that is already there, if this same program wrote it
        // from these same sources. What is stored is the `.pcm`'s sha256,
        // so a run cut off halfway is not taken as good: it does not match
        // and is redone.
        //
        // And if it is not there, the one another build made: with the cache
        // shared, a worktree finds every track another one already rendered.
        if let Some(stored) = self.cached(&key) {
            if file_fingerprint(&out_path).as_ref() == Some(&stored) {
                // Still used, though not read from the cache: the cache's
                // copy is what the next worktree takes instead of
                // rendering the track again, so it must not be evicted.
                if let Some(dir) = &self.cache {
                    cache::touch(dir, TRACKS, &key);
                }
                return Ok(Outcome::Already);
            }
            if self.restore_from_the_cache(&key, &stored, &out_path) {
                return Ok(Outcome::Already);
            }
        }
        let tmp_wav = PathBuf::from(format!("{}.wav", out_path.display()));
        // What did not go as it should, and was worked around: it goes in
        // the track's line, so that it is seen.
        let mut warnings = Vec::new();
        let mut cut = None;
        match (&audio, &midi) {
            (Some(a), _) => decode(a, &tmp_wav)?,
            (None, Some(m)) => {
                let data = std::fs::read(m).map_err(|e| io(m, e))?;
                let mut source = m.clone();
                let tmp_mid = PathBuf::from(format!("{}.mid", out_path.display()));
                match midi::parse(&data, &m.display().to_string()) {
                    Err(e) => warnings.push(format!("{e}: the whole render, looping at 0")),
                    Ok(parsed) => {
                        match midi::for_fluidsynth(&data, &parsed) {
                            Ok(None) => {}
                            Ok(Some(fixed)) => {
                                std::fs::write(&tmp_mid, fixed).map_err(|e| io(&tmp_mid, e))?;
                                source = tmp_mid.clone();
                                warnings.push(format!(
                                    "{}: a delta of more than four bytes before an end-of-track, \
                                     written as 0 for fluidsynth",
                                    m.display()
                                ));
                            }
                            Err(why) => warnings.push(format!(
                                "{}: {why}; fluidsynth refuses the file",
                                m.display()
                            )),
                        }
                        cut = Some(parsed.rm2k_loop());
                    }
                }
                let rendered = render(&source, &tmp_wav, &self.soundfont, self.gain);
                if source == tmp_mid {
                    let _ = std::fs::remove_file(&tmp_mid);
                }
                rendered?;
            }
            (None, None) => unreachable!(),
        }
        let (samples, frames) = read_wav(&tmp_wav)?;
        let (samples, loop_point) = match cut {
            Some(cut) => match rm2k_cut(
                &samples,
                frames_at(cut.start),
                frames_at(cut.to),
                frames_at(cut.end),
            ) {
                Ok(done) => done,
                Err(why) => {
                    warnings.push(format!("{why}: the whole render, looping at 0"));
                    (samples, 0)
                }
            },
            None => (samples, 0),
        };
        let frames = if midi.is_some() {
            samples.len() / 2
        } else {
            frames
        };
        let (bytes, scale) = track(&samples, loop_point, PEAK);
        // Written alongside and renamed, instead of overwriting the `.pcm`
        // in place: truncating it would change the content for whoever has
        // it open —an emulator playing it— or linked under another name.
        let new = PathBuf::from(format!("{}.nuevo", out_path.display()));
        std::fs::write(&new, &bytes).map_err(|e| io(&new, e))?;
        std::fs::rename(&new, &out_path).map_err(|e| io(&out_path, e))?;
        std::fs::remove_file(&tmp_wav).map_err(|e| io(&tmp_wav, e))?;
        if let Some(fp) = file_fingerprint(&out_path) {
            // The track first and its sha256 after: whoever finds the
            // sha256 finds the track too.
            if let Some(dir) = &self.cache {
                cache::store_file(dir, TRACKS, &key, &out_path);
            }
            self.store(&key, &fp);
        }
        let from = audio
            .map(|a| format!("  (from {})", a.display()))
            .unwrap_or_default();
        let looped = if loop_point != 0 {
            format!(", loop at {:.2} s", loop_point as f64 / 44100.0)
        } else {
            String::new()
        };
        let warned: String = warnings
            .iter()
            .map(|w| format!("\n  warning: {w}"))
            .collect();
        Ok(Outcome::Made(format!(
            "track {number}: {name:<22} {:6.1} s{looped}, {} MB, normalized x{scale:.2} -> {}{from}{warned}",
            frames as f64 / 44100.0,
            bytes.len() >> 20,
            out_path.display()
        )))
    }

    /// Leaves next to `rom` the `.msu` and one track per song of the
    /// cartridge, and deletes the ones that no longer belong to any song.
    /// Each line goes to `print` in order, as it is known; `verbose` false
    /// leaves out the tracks that were already there. Returns how many it
    /// made and how many were already there.
    pub fn build(
        &self,
        rom: &Path,
        verbose: bool,
        print: &mut dyn FnMut(&str),
    ) -> Result<(usize, usize)> {
        // `abl.sfc` gives `abl`, and a name without a dot stays as it is.
        let base = rom.with_extension("").to_string_lossy().into_owned();
        // The file that turns MSU-1 on. The cartridge's builder writes it
        // with its data, so here it is created only if missing —a loose ROM,
        // built by hand—, and empty. Appending does not truncate it.
        let msu = PathBuf::from(format!("{base}.msu"));
        std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&msu)
            .map_err(|e| io(&msu, e))?;

        let tracks = cartridge_tracks(rom)?;
        let numbers: std::collections::BTreeSet<i64> = tracks.iter().map(|&(_, n)| n).collect();
        let base_path = Path::new(&base);
        let dir = match base_path.parent() {
            Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
            _ => PathBuf::from("."),
        };
        let stem = base_path
            .file_name()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        let mut old = Vec::new();
        for entry in std::fs::read_dir(&dir).map_err(|e| io(&dir, e))? {
            let file = entry
                .map_err(|e| io(&dir, e))?
                .file_name()
                .to_string_lossy()
                .into_owned();
            let Some(number) = file
                .strip_prefix(&format!("{stem}-"))
                .and_then(|r| r.strip_suffix(".pcm"))
            else {
                continue;
            };
            if !number.is_empty() && number.bytes().all(|b| b.is_ascii_digit()) {
                if let Ok(n) = number.parse::<i64>() {
                    if !numbers.contains(&n) {
                        old.push((number.to_string(), dir.join(&file)));
                    }
                }
            }
        }
        old.sort();
        for (number, path) in old {
            std::fs::remove_file(&path).map_err(|e| io(&path, e))?;
            print(&format!(
                "track {number}: no longer belongs to any song, deleted"
            ));
        }

        // The tracks at once, in threads: each one writes its own file, the
        // heavy part runs in fluidsynth or ffmpeg, and one by one they were
        // what took longest in a cold build. What is printed stays in order.
        let workers = std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(1)
            .min(tracks.len().max(1));
        let next = Mutex::new(0usize);
        let (tx, rx) = mpsc::channel();
        let mut made = 0;
        let mut already = 0;
        let mut first_error = None;
        std::thread::scope(|scope| {
            for _ in 0..workers {
                let tx = tx.clone();
                let next = &next;
                let tracks = &tracks;
                let base = &base;
                scope.spawn(move || loop {
                    let i = {
                        let mut n = next.lock().unwrap();
                        let i = *n;
                        *n += 1;
                        i
                    };
                    let Some((name, number)) = tracks.get(i) else {
                        break;
                    };
                    if tx.send((i, self.one(base, name, *number))).is_err() {
                        break;
                    }
                });
            }
            drop(tx);
            let mut pending = BTreeMap::new();
            let mut at = 0;
            for (i, outcome) in rx {
                pending.insert(i, outcome);
                while let Some(outcome) = pending.remove(&at) {
                    let (name, number) = &tracks[at];
                    at += 1;
                    if first_error.is_some() {
                        continue;
                    }
                    match outcome {
                        Ok(Outcome::Already) => {
                            already += 1;
                            if verbose {
                                print(&format!("track {number}: {name:<22} already there -> {base}-{number}.pcm"));
                            }
                        }
                        Ok(Outcome::Made(line)) => {
                            made += 1;
                            print(&line);
                        }
                        Err(e) => {
                            // The others stop taking tracks; the ones
                            // halfway finish, and the scope waits for them.
                            *next.lock().unwrap() = usize::MAX;
                            first_error = Some(e);
                        }
                    }
                }
            }
        });
        match first_error {
            Some(e) => Err(e),
            None => Ok((made, already)),
        }
    }
}

/// An audio file to 44.1 kHz 16-bit stereo WAV, with ffmpeg.
fn decode(audio: &Path, out: &Path) -> Result<()> {
    let status = Command::new("ffmpeg")
        .args(["-loglevel", "error", "-y", "-i"])
        .arg(audio)
        .args(["-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le"])
        .arg(out)
        .status()
        .map_err(|e| Bad::usage(format!("ffmpeg: {e}")))?;
    if !status.success() {
        return Err(Bad::usage(format!(
            "ffmpeg could not decode {}: {status}",
            audio.display()
        )));
    }
    Ok(())
}

/// A float as fluidsynth's `-g` takes it: the shortest text that reads back
/// as the same number, with a `.0` when it is whole.
fn float_text(x: f64) -> String {
    format!("{x:?}")
}

/// The MIDI to 44.1 kHz stereo WAV, with fluidsynth.
fn render(midi: &Path, out: &Path, soundfont: &Path, gain: f64) -> Result<()> {
    let status = Command::new("fluidsynth")
        .args(["-ni", "-r", "44100", "-g", &float_text(gain), "-F"])
        .arg(out)
        .arg(soundfont)
        .arg(midi)
        .stdout(Stdio::null())
        .status()
        .map_err(|e| Bad::usage(format!("fluidsynth: {e}")))?;
    if !status.success() {
        return Err(Bad::usage(format!(
            "fluidsynth could not render {}: {status}",
            midi.display()
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    /// That [`OWN_SOURCES`] is closed: each module of the crate one of them
    /// names —`crate::x`, or `rm2k_snes_audio::x` as the subcommand that ran
    /// them named it until 2026-11-25— is in the list too. One that is not would change a
    /// track's bytes without expiring it.
    #[test]
    fn the_track_sources_name_no_module_outside_them() {
        let listed: Vec<&str> = super::OWN_SOURCES.iter().map(|(n, _)| *n).collect();
        for (name, text) in super::OWN_SOURCES {
            let code = text.lines().filter(|l| !l.trim_start().starts_with("//"));
            for line in code {
                for prefix in ["crate::", "rm2k_snes_audio::"] {
                    for (at, _) in line.match_indices(prefix) {
                        let rest = &line[at + prefix.len()..];
                        assert!(
                            !rest.starts_with('{'),
                            "{name}: a `use` of several modules hides them from this: one per line"
                        );
                        let module: String = rest
                            .chars()
                            .take_while(|c| c.is_ascii_alphanumeric() || *c == '_')
                            .collect();
                        // Nothing after it is the prefix written in a string
                        // —this test's own—; a capital, what the crate
                        // re-exports at its root: `Bad` and `Result`, from
                        // `fail.rs`.
                        if module.is_empty() || module.starts_with(char::is_uppercase) {
                            continue;
                        }
                        let file = format!("{module}.rs");
                        assert!(
                            listed.contains(&file.as_str()),
                            "{name} uses `{prefix}{module}`, and {file} is not in OWN_SOURCES"
                        );
                    }
                }
            }
        }
    }

    use super::*;

    #[test]
    fn a_link_wav_is_followed_to_the_mp3_it_names() {
        let root =
            std::env::temp_dir().join(format!("rm2k-snes-audio-link-{}", std::process::id()));
        let music = root.join("Music");
        std::fs::create_dir_all(&music).unwrap();
        std::fs::create_dir_all(root.join("mp3")).unwrap();
        std::fs::write(root.join("mp3").join("Credits.MP3"), b"ID3").unwrap();
        std::fs::write(
            music.join("Credits.link.wav"),
            "..\\mp3\\Credits.mp3loop\r\n",
        )
        .unwrap();
        std::fs::write(music.join("Plain.wav"), b"RIFF").unwrap();
        assert_eq!(
            followed_link(&music.join("Credits.link.wav")),
            Some(root.join("mp3").join("Credits.MP3"))
        );
        assert_eq!(followed_link(&music.join("Plain.wav")), None);
        std::fs::remove_dir_all(&root).unwrap();
    }

    /// A WAV of `frames` frames of 16-bit stereo at 44.1 kHz.
    fn wav(frames: usize) -> Vec<u8> {
        let data = frames * 4;
        let mut out = b"RIFF".to_vec();
        out.extend((36 + data as u32).to_le_bytes());
        out.extend(b"WAVEfmt ");
        out.extend(16u32.to_le_bytes());
        out.extend(1u16.to_le_bytes());
        out.extend(2u16.to_le_bytes());
        out.extend(44100u32.to_le_bytes());
        out.extend((44100u32 * 4).to_le_bytes());
        out.extend(4u16.to_le_bytes());
        out.extend(16u16.to_le_bytes());
        out.extend(b"data");
        out.extend((data as u32).to_le_bytes());
        for k in 0..frames * 2 {
            out.extend(((k as i16 % 200) * 50).to_le_bytes());
        }
        out
    }

    /// Two worktrees that share the cache build the same track once: the
    /// second one finds the first one's `.pcm` in the cache and links it,
    /// instead of rendering it again. With a replacement, which ffmpeg
    /// decodes, so that it does not need a SoundFont.
    #[test]
    fn a_track_another_build_made_comes_from_the_cache() {
        if which("ffmpeg").is_none() {
            eprintln!("skipped: ffmpeg is not on the PATH");
            return;
        }
        let root =
            std::env::temp_dir().join(format!("rm2k-snes-audio-shared-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        for dir in ["game", "replacements", "one", "two"] {
            std::fs::create_dir_all(root.join(dir)).unwrap();
        }
        std::fs::write(root.join("replacements").join("Song.wav"), wav(4410)).unwrap();
        // Each one a `Tracks` of its own, as two processes would be.
        let tracks = || {
            Tracks::new(
                Game {
                    game_dir: root.join("game"),
                    rtp_dir: None,
                    project: rm2k_project::Project::from_text(&root, "").unwrap(),
                },
                root.join("none.sf2"),
                GAIN,
                Some(root.join("replacements")),
                Some(root.join("cache")),
            )
        };
        let base = |dir: &str| root.join(dir).join("game").display().to_string();
        assert!(matches!(
            tracks().one(&base("one"), "Song", 1).unwrap(),
            Outcome::Made(_)
        ));
        assert!(matches!(
            tracks().one(&base("two"), "Song", 1).unwrap(),
            Outcome::Already
        ));
        let one = std::fs::read(root.join("one").join("game-1.pcm")).unwrap();
        assert_eq!(
            std::fs::read(root.join("two").join("game-1.pcm")).unwrap(),
            one
        );
        std::fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn a_quiet_track_is_raised_to_the_peak() {
        let (bytes, scale) = track(&[100, -200, 50, 0], 7, PEAK);
        assert_eq!(&bytes[..4], b"MSU1");
        assert_eq!(u32::from_le_bytes(bytes[4..8].try_into().unwrap()), 7);
        let samples: Vec<i16> = bytes[8..]
            .chunks(2)
            .map(|c| i16::from_le_bytes([c[0], c[1]]))
            .collect();
        assert_eq!(scale, 0.97 * 32767.0 / 200.0);
        // Truncated towards zero, not rounded.
        assert_eq!(samples, vec![15891, -31783, 7945, 0]);
    }

    #[test]
    fn a_scale_close_to_one_leaves_the_audio_as_it_came() {
        let top = (0.97f64 * 32767.0 / 1.01) as i16;
        let (bytes, _) = track(&[top, -3], 0, PEAK);
        assert_eq!(
            &bytes[8..],
            &[top.to_le_bytes(), (-3i16).to_le_bytes()].concat()[..]
        );
    }

    #[test]
    fn minus_32768_is_the_loudest_sample() {
        let (_, scale) = track(&[-32768, 1000], 0, PEAK);
        assert_eq!(scale, 0.97 * 32767.0 / 32768.0);
    }

    /// Frames numbered 1, 2, 3…, both channels the same.
    fn render(frames: i16) -> Vec<i16> {
        (1..=frames).flat_map(|f| [f, f]).collect()
    }

    fn frames(samples: &[i16]) -> Vec<i16> {
        samples.iter().step_by(2).copied().collect()
    }

    /// `hzstream`: the render goes on after the end of the track —here
    /// frames 7 and 8, fluidsynth's two seconds— and the track does not.
    #[test]
    fn a_track_ends_at_the_end_of_the_midi_not_of_the_render() {
        let (out, loop_point) = rm2k_cut(&render(8), 0, 0, 6).unwrap();
        assert_eq!(frames(&out), [1, 2, 3, 4, 5, 6]);
        assert_eq!(loop_point, 0);
    }

    #[test]
    fn the_loop_point_is_the_cc111_counted_from_the_start() {
        let (out, loop_point) = rm2k_cut(&render(8), 2, 4, 6).unwrap();
        assert_eq!(frames(&out), [3, 4, 5, 6]);
        assert_eq!(loop_point, 2);
    }

    /// The skipped silence goes to the end, with what the render has
    /// there and zeros past it: the second pass hears it, the first does
    /// not.
    #[test]
    fn the_skipped_silence_is_heard_after_the_end() {
        let (out, loop_point) = rm2k_cut(&render(7), 2, 0, 6).unwrap();
        assert_eq!(frames(&out), [3, 4, 5, 6, 7, 0]);
        assert_eq!(loop_point, 0);
    }

    /// A MIDI that says it ends past what fluidsynth rendered is not cut:
    /// the end is not to be trusted, and nothing is allocated for it.
    #[test]
    fn an_end_past_the_render_is_refused() {
        assert!(rm2k_cut(&render(8), 0, 0, 9).is_err());
        assert!(rm2k_cut(&render(8), 0, 0, usize::MAX / 2).is_err());
        assert!(rm2k_cut(&render(8), 0, 0, 8).is_ok());
    }

    #[test]
    fn the_gain_is_written_like_this() {
        assert_eq!(float_text(0.6), "0.6");
        assert_eq!(float_text(1.0), "1.0");
        assert_eq!(float_text(0.25), "0.25");
    }
}
