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
//! gets a track anyway, decoded with `ffmpeg` like a replacement.
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
//! Until 2026-09-29 this was a Python program, and the tracks come out
//! byte for byte the same: see [`track`].

use crate::fail::{Bad, Result};
use crate::game::Game;
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

/// The disk cache's category.
const CATEGORY: &str = "msu";

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
    std::env::split_paths(&path).map(|d| d.join(program)).find(|p| p.is_file())
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

/// What this program is, for the key: the sha256 of the running executable.
/// It is what normalizes and writes the track, so changing it has to expire
/// the tracks; and it is the only thing that changes exactly when the code
/// does, without anyone having to remember to bump a number.
fn own_version() -> Result<String> {
    let exe = std::env::current_exe().map_err(|e| Bad::usage(format!("the running executable: {e}")))?;
    file_sha256(&exe).map_err(|e| io(&exe, e))
}

/// The audio file that replaces this song's MIDI, or None.
pub fn replacement(directory: Option<&Path>, name: &str) -> Option<PathBuf> {
    let directory = directory?;
    EXTENSIONS
        .iter()
        .map(|ext| directory.join(format!("{name}{ext}")))
        .find(|p| p.is_file())
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
                return Err(Bad::usage(format!("{} is not 16-bit stereo at 44100", path.display())));
            }
            // Whole frames only, and no further than the file goes: that is
            // what reading `nframes` frames gave.
            let end = body.saturating_add(size).min(bytes.len());
            let frames = (end - body) / 4;
            let data = &bytes[body..body + frames * 4];
            let samples = data.chunks_exact(2).map(|c| i16::from_le_bytes([c[0], c[1]])).collect();
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
/// The arithmetic is the Python program's, so the tracks come out byte for
/// byte the same: the product in double precision, truncated towards zero
/// and clipped. A scale close enough to one is left out, and the audio goes
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
        let v = if rescale { (s as f64 * scale).trunc().clamp(-32768.0, 32767.0) as i16 } else { s };
        out.extend_from_slice(&v.to_le_bytes());
    }
    (out, scale)
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
    /// comes from; the gain and the peak, how it is scaled; and this
    /// program, what normalizes and writes it. **The track number does not
    /// go in**: it does not change a single sample, only the file name.
    /// The SoundFont goes in by content and not by path: a bank can change
    /// without changing its name.
    pub fn midi_key(&self, midi: &Path) -> Result<String> {
        let own = self.once(&self.own, own_version)?;
        let synth = self.once(&self.fluidsynth, || {
            program_fingerprint("fluidsynth", "--version", "fluidsynth is missing: on Arch, pacman -S fluidsynth")
        })?;
        let font = self.once(&self.font, || file_sha256(&self.soundfont).map_err(|e| io(&self.soundfont, e)))?;
        let raw = std::fs::read(midi).map_err(|e| io(midi, e))?;
        let scaling = format!("{:?} {:?}", self.gain, PEAK);
        Ok(cache::key(&[own.as_bytes(), synth.as_bytes(), font.as_bytes(), scaling.as_bytes(), &raw]))
    }

    /// The same, for a track that comes from an audio file: a replacement,
    /// or a song that in the game is a WAV.
    pub fn audio_key(&self, audio: &Path) -> Result<String> {
        let own = self.once(&self.own, own_version)?;
        let decoder =
            self.once(&self.ffmpeg, || program_fingerprint("ffmpeg", "-version", "ffmpeg is missing: on Arch, pacman -S ffmpeg"))?;
        let raw = std::fs::read(audio).map_err(|e| io(audio, e))?;
        let scaling = format!("{:?}", PEAK);
        Ok(cache::key(&[own.as_bytes(), decoder.as_bytes(), scaling.as_bytes(), &raw]))
    }

    fn cached(&self, key: &str) -> Option<String> {
        let path = self.cache.as_ref()?.join(CATEGORY).join(key);
        std::fs::read_to_string(path).ok()
    }

    /// Stores the value whole or not at all: written aside and renamed. A
    /// cache that cannot be written breaks nothing.
    fn store(&self, key: &str, value: &str) {
        let Some(dir) = &self.cache else { return };
        let dir = dir.join(CATEGORY);
        if std::fs::create_dir_all(&dir).is_err() {
            return;
        }
        let tmp = dir.join(format!(".tmp-{}-{key}", std::process::id()));
        if std::fs::write(&tmp, value).is_ok() && std::fs::rename(&tmp, dir.join(key)).is_err() {
            let _ = std::fs::remove_file(&tmp);
        }
    }

    /// One track: `<base>-<number>.pcm`.
    pub fn one(&self, base: &str, name: &str, number: i64) -> Result<Outcome> {
        let out_path = PathBuf::from(format!("{base}-{number}.pcm"));
        let mut audio = replacement(self.replacements.as_deref(), name);
        let mut midi = None;
        if audio.is_none() {
            let source =
                self.game.song_path(name).ok_or_else(|| Bad::usage(format!("cannot find the music for {name}")))?;
            if source.to_string_lossy().to_lowercase().ends_with(".mid") {
                midi = Some(source);
            } else {
                audio = Some(source);
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
        if let Some(stored) = self.cached(&key) {
            if Some(stored) == file_fingerprint(&out_path) {
                return Ok(Outcome::Already);
            }
        }
        let tmp_wav = PathBuf::from(format!("{}.wav", out_path.display()));
        match (&audio, &midi) {
            (Some(a), _) => decode(a, &tmp_wav)?,
            (None, Some(m)) => render(m, &tmp_wav, &self.soundfont, self.gain)?,
            (None, None) => unreachable!(),
        }
        let (samples, frames) = read_wav(&tmp_wav)?;
        let (bytes, scale) = track(&samples, 0, PEAK);
        // Written alongside and renamed, instead of overwriting the `.pcm`
        // in place: truncating it would change the content for whoever has
        // it open —an emulator playing it— or linked under another name.
        let new = PathBuf::from(format!("{}.nuevo", out_path.display()));
        std::fs::write(&new, &bytes).map_err(|e| io(&new, e))?;
        std::fs::rename(&new, &out_path).map_err(|e| io(&out_path, e))?;
        std::fs::remove_file(&tmp_wav).map_err(|e| io(&tmp_wav, e))?;
        if let Some(fp) = file_fingerprint(&out_path) {
            self.store(&key, &fp);
        }
        let from = audio.map(|a| format!("  (from {})", a.display())).unwrap_or_default();
        Ok(Outcome::Made(format!(
            "track {number}: {name:<22} {:6.1} s, {} MB, normalized x{scale:.2} -> {}{from}",
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
    pub fn build(&self, rom: &Path, verbose: bool, print: &mut dyn FnMut(&str)) -> Result<(usize, usize)> {
        // Python's `splitext`, which is what `Path::with_extension` does:
        // `abl.sfc` gives `abl`, and a name without a dot stays as it is.
        let base = rom.with_extension("").to_string_lossy().into_owned();
        // The file that turns MSU-1 on. The cartridge's builder writes it
        // with its data, so here it is created only if missing —a loose ROM,
        // built by hand—, and empty. Appending does not truncate it.
        let msu = PathBuf::from(format!("{base}.msu"));
        std::fs::OpenOptions::new().create(true).append(true).open(&msu).map_err(|e| io(&msu, e))?;

        let tracks = cartridge_tracks(rom)?;
        let numbers: std::collections::BTreeSet<i64> = tracks.iter().map(|&(_, n)| n).collect();
        let base_path = Path::new(&base);
        let dir = match base_path.parent() {
            Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
            _ => PathBuf::from("."),
        };
        let stem = base_path.file_name().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
        let mut old = Vec::new();
        for entry in std::fs::read_dir(&dir).map_err(|e| io(&dir, e))? {
            let file = entry.map_err(|e| io(&dir, e))?.file_name().to_string_lossy().into_owned();
            let Some(number) = file.strip_prefix(&format!("{stem}-")).and_then(|r| r.strip_suffix(".pcm")) else {
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
            print(&format!("track {number}: no longer belongs to any song, deleted"));
        }

        // The tracks at once, in threads: each one writes its own file, the
        // heavy part runs in fluidsynth or ffmpeg, and one by one they were
        // what took longest in a cold build. What is printed stays in order.
        let workers = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1).min(tracks.len().max(1));
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
                    let Some((name, number)) = tracks.get(i) else { break };
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
        return Err(Bad::usage(format!("ffmpeg could not decode {}: {status}", audio.display())));
    }
    Ok(())
}

/// Python's `str()` of a float: the shortest text that reads back as the
/// same number, with a `.0` when it is whole. It is what went to fluidsynth
/// as `-g`, so it keeps going the same.
fn python_float(x: f64) -> String {
    format!("{x:?}")
}

/// The MIDI to 44.1 kHz stereo WAV, with fluidsynth.
fn render(midi: &Path, out: &Path, soundfont: &Path, gain: f64) -> Result<()> {
    let status = Command::new("fluidsynth")
        .args(["-ni", "-r", "44100", "-g", &python_float(gain), "-F"])
        .arg(out)
        .arg(soundfont)
        .arg(midi)
        .stdout(Stdio::null())
        .status()
        .map_err(|e| Bad::usage(format!("fluidsynth: {e}")))?;
    if !status.success() {
        return Err(Bad::usage(format!("fluidsynth could not render {}: {status}", midi.display())));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_quiet_track_is_raised_to_the_peak() {
        let (bytes, scale) = track(&[100, -200, 50, 0], 7, PEAK);
        assert_eq!(&bytes[..4], b"MSU1");
        assert_eq!(u32::from_le_bytes(bytes[4..8].try_into().unwrap()), 7);
        let samples: Vec<i16> = bytes[8..].chunks(2).map(|c| i16::from_le_bytes([c[0], c[1]])).collect();
        assert_eq!(scale, 0.97 * 32767.0 / 200.0);
        // Truncated towards zero, not rounded.
        assert_eq!(samples, vec![15891, -31783, 7945, 0]);
    }

    #[test]
    fn a_scale_close_to_one_leaves_the_audio_as_it_came() {
        let top = (0.97f64 * 32767.0 / 1.01) as i16;
        let (bytes, _) = track(&[top, -3], 0, PEAK);
        assert_eq!(&bytes[8..], &[top.to_le_bytes(), (-3i16).to_le_bytes()].concat()[..]);
    }

    #[test]
    fn minus_32768_is_the_loudest_sample() {
        let (_, scale) = track(&[-32768, 1000], 0, PEAK);
        assert_eq!(scale, 0.97 * 32767.0 / 32768.0);
    }

    #[test]
    fn python_writes_the_gain_like_this() {
        assert_eq!(python_float(0.6), "0.6");
        assert_eq!(python_float(1.0), "1.0");
        assert_eq!(python_float(0.25), "0.25");
    }
}
