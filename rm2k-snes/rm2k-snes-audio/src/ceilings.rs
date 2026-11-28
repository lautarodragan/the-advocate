//! Each song's volume ceiling, measured while the music is compiled, by
//! playing what the song writes to the S-DSP in a model of the chip.
//!
//! The S-DSP adds up the eight voices and saturates the sum before the
//! master volume, so what keeps a song from clipping is each voice's
//! ceiling —its headroom, see `HEADROOM` in [`sdsp`]—; this gives each song
//! the highest one that does not clip, no higher than the usual:
//!
//! 1. **The song at half the headroom** ([`MEASURING_HEADROOM`]), or at
//!    half that again for one that clips even so, up to [`HALVINGS`] times.
//!    Without clipping the peak measured is the true one, and since each
//!    voice's volume is linear in the headroom, the full one's scales.
//! 2. **Played in the S-DSP**, blargg's `SPC_DSP` in `spc-dsp`, from the
//!    writes the song's stream makes, frame by frame —the SPC700 driver
//!    only forwards them, see `runtime/spc700.s`—, with the samples it
//!    plays in the ARAM. **Six times**, each with the writes of a frame
//!    spread differently ([`TIMINGS`]), and the loudest is the peak.
//! 3. **The ceiling** leaves that peak [`margin`] below the cap.
//! 4. **The songs that end close to the cap are played again with their
//!    ceiling**: each voice's volume is rounded to an integer, so the
//!    arithmetic is approximate. One that clips is lowered by as much as it
//!    went over, and played again.
//!
//! **What the model does not see is when each write lands inside its
//! frame**: the 65816 sends a frame's writes one after another, through
//! the driver, so a KON after thirty writes reaches the DSP later than one
//! alone, and that moves a peak by up to 2.85 dB. Played with every write
//! of a frame at its start, the model is equal to the ROM sample for sample
//! until the first write that lands elsewhere, and the peak comes out
//! between 1.40 dB below the ROM's and 1.30 dB above. The loudest of six
//! timings left every song of the first game measured within 0.36 dB of
//! the ROM's peak, inside the margin, at the cost of songs 0.42 dB quieter
//! on average: measured on 2026-11-27, in
//! `tasks/the-volume-ceilings-are-measured-without-a-rom.md` of
//! the-advocate-work. A song that turned the echo on would need the echo
//! buffer modelled; the stream turns it off (`init_writes` in [`stream`]).
//!
//! **Each song's peak is kept per mix**, in the converter's cache: what it
//! writes, the samples it plays and this model's code are its key, so a
//! change to one song plays only that one again, and every cartridge of a
//! game shares the songs they have in common. Until 2026-11-28 the table
//! was measured by hand, building a copy of the cartridge and playing each
//! song on its title screen in a libretro core —`rm2k-snes-audio
//! volume-ceilings`—, and versioned in the game's automatic patches, where
//! it went stale with every change to the mix.
//!
//! [`sdsp`]: crate::sdsp
//! [`stream`]: crate::stream

use crate::bank::SAMPLES_ADDR;
use crate::fail::{Bad, Result};
use crate::sdsp;
use crate::stream::Write;
use rm2k_project::cache;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

/// The usual headroom: what a song that does not clip keeps.
pub const HEADROOM: f64 = sdsp::HEADROOM;

/// Half the usual headroom: measured on 2026-09-26, with 0.25 none of the
/// 32 songs of the first game's cartridge clips, and the loudest one stays
/// 3.9 dB below the cap.
pub const MEASURING_HEADROOM: f64 = HEADROOM / 2.0;

/// How many times a song that clips at [`MEASURING_HEADROOM`] is measured
/// again at half: three songs of two other games clip at 0.25 (measured on
/// 2026-11-28). One that still clips at 0.25/16 stops the build.
pub const HALVINGS: u32 = 4;

/// How far below the cap the peak is allowed to go: 0.5 dB. What it
/// absorbs is how far the console's peak may be above the model's
/// loudest timing —0.36 dB, measured—, and the rounding of each voice's
/// volume to an integer.
pub fn margin() -> f64 {
    10.0f64.powf(-0.5 / 20.0)
}

/// How close to the cap a song's peak, scaled to its ceiling, has to come
/// for the song to be played again with it: the rounding moves a peak by
/// tenths of a dB, so 1.5 dB leaves it out of reach.
pub fn close() -> f64 {
    10.0f64.powf(-1.5 / 20.0)
}

/// Where the cap lies in what comes out of the console: the DSP saturates
/// the sum of the voices at 16 bits and then multiplies it by the master
/// volume, MVOL/128.
pub fn cap() -> i64 {
    (32767 * sdsp::master()) >> 7
}

/// How many frames past its last write a song is played: its last notes
/// ring on.
pub const AFTER_END: i64 = 60;

/// The S-DSP's clocks in one of the console's frames: it runs at
/// 1,024,000 Hz, and an NTSC frame lasts 1/60.0988 s.
pub const CLOCKS_PER_FRAME: f64 = spc_dsp::CLOCKS_PER_SECOND as f64 / 60.0988;

/// How many DSP clocks each write takes in each of the six runs: the
/// writes of a frame land one after another, that far apart, from its
/// start. Six spreads were enough: eighteen —these, each also from a
/// third and two thirds into the frame— did not bring any song closer to
/// the ROM's peak than 0.36 dB, and three left one 0.66 dB past the
/// margin. Measured on 2026-11-27, see the top of this module.
pub const TIMINGS: [f64; 6] = [0.0, 25.0, 50.0, 75.0, 100.0, 125.0];

/// Where the directory goes in the model's ARAM, and where the samples
/// start: after room for every entry a byte can name. Where a sample sits
/// does not change what it sounds like, so they are not placed where the
/// ROM places them.
const DIRECTORY: usize = SAMPLES_ADDR as usize;
const FIRST_SAMPLE: usize = DIRECTORY + 4 * 256;

/// What is played: a song's writes, frame by frame, and the ARAM with the
/// samples they name.
pub struct Song {
    pub writes: Vec<Write>,
    pub aram: Vec<u8>,
    /// How many frames: the song's length and [`AFTER_END`].
    pub frames: i64,
}

impl Song {
    /// `writes`, with the ARAM made of the samples each SRCN they write
    /// names: `sample(srcn)` gives its BRR and where it loops, in bytes from
    /// its start. One the song names and `sample` lacks plays silence, as a
    /// key the SoundFont lacks.
    pub fn new<'a>(
        name: &str,
        writes: Vec<Write>,
        sample: impl Fn(u8) -> Option<(&'a [u8], usize)>,
    ) -> Result<Song> {
        let mut aram = vec![0u8; spc_dsp::ARAM];
        let mut used: Vec<u8> = writes
            .iter()
            .filter(|(_, r, _)| *r < 0x80 && r & 0x0F == sdsp::V_SRCN)
            .map(|w| w.2)
            .collect();
        used.sort_unstable();
        used.dedup();
        // Two keys may carry the same BRR and loop: placed once.
        let mut placed: HashMap<(&[u8], usize), usize> = HashMap::new();
        let mut at = FIRST_SAMPLE;
        for srcn in used {
            let Some((data, loop_at)) = sample(srcn) else {
                continue;
            };
            let start = match placed.get(&(data, loop_at)) {
                Some(&start) => start,
                None => {
                    if at + data.len() > aram.len() {
                        return Err(Bad::answer(format!(
                            "{name}: its samples do not fit in the ARAM of the model that \
                             measures its volume ceiling"
                        )));
                    }
                    aram[at..at + data.len()].copy_from_slice(data);
                    placed.insert((data, loop_at), at);
                    at += data.len();
                    at - data.len()
                }
            };
            let entry = DIRECTORY + 4 * srcn as usize;
            aram[entry..entry + 2].copy_from_slice(&(start as u16).to_le_bytes());
            aram[entry + 2..entry + 4].copy_from_slice(&((start + loop_at) as u16).to_le_bytes());
        }
        let frames = writes.last().map_or(0, |w| w.0 + 1) + AFTER_END;
        Ok(Song {
            writes,
            aram,
            frames,
        })
    }

    /// The key it is kept under: what is played, and the code that plays
    /// it.
    fn key(&self) -> String {
        let writes: Vec<u8> = self
            .writes
            .iter()
            .flat_map(|&(f, r, v)| {
                let mut bytes = f.to_le_bytes().to_vec();
                bytes.extend([r, v]);
                bytes
            })
            .collect();
        cache::key(&[
            model_version().as_bytes(),
            &self.frames.to_le_bytes(),
            &writes,
            &self.aram,
        ])
    }
}

/// What a song gave: its loudest sample, and how many reached the cap.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Played {
    pub peak: i64,
    pub clipped: usize,
}

/// `song` played once, with each write of a frame taking `per_write` DSP
/// clocks from the start of the frame.
///
/// **Frame 0's writes land before any clock runs**: they are what the ROM
/// writes at boot, long before a song starts, and the DSP's power-on
/// registers would play otherwise —see `Dsp::new`—.
pub fn play(song: &Song, per_write: f64) -> Played {
    let mut dsp = spc_dsp::Dsp::new(song.aram.clone());
    let cap = cap();
    let mut played = Played {
        peak: 0,
        clipped: 0,
    };
    // The clocks are fractional, and what is not run yet carries on.
    let mut owed = 0.0f64;
    let mut run = |dsp: &mut spc_dsp::Dsp, clocks: f64| {
        owed += clocks;
        let whole = owed.floor();
        owed -= whole;
        for &s in dsp.run(whole as u32) {
            let s = s as i64;
            played.peak = played.peak.max(s.abs());
            // `< -cap` is the negative rail, as -32768 is 16 bits'.
            if s >= cap || s < -cap {
                played.clipped += 1;
            }
        }
    };
    let mut next = 0;
    for frame in 0..song.frames {
        let per_write = if frame == 0 { 0.0 } else { per_write };
        let mut spent = 0.0;
        while let Some(&(at, register, value)) = song.writes.get(next) {
            if at != frame {
                break;
            }
            dsp.write(register, value);
            next += 1;
            if per_write > 0.0 {
                run(&mut dsp, per_write);
                spent += per_write;
            }
        }
        run(&mut dsp, (CLOCKS_PER_FRAME - spent).max(0.0));
    }
    played
}

/// `song` played with each of the [`TIMINGS`]: the loudest peak, and the
/// most samples at the cap.
///
/// The six at once, each in a thread: a long song is several seconds of
/// each, and one after another the longest song of a game was what
/// [`measure`] waited on at the end, with the rest of the threads idle.
pub fn loudest(song: &Song) -> Played {
    std::thread::scope(|scope| {
        let runs: Vec<_> = TIMINGS
            .iter()
            .map(|&t| scope.spawn(move || play(song, t)))
            .collect();
        runs.into_iter()
            .map(|run| run.join().expect("a play of the S-DSP panicked"))
            .fold(
                Played {
                    peak: 0,
                    clipped: 0,
                },
                |a, b| Played {
                    peak: a.peak.max(b.peak),
                    clipped: a.clipped.max(b.clipped),
                },
            )
    })
}

/// What this model is, for the key: the S-DSP's sources and this module's,
/// hashed. A change to either plays every song again; nothing has to be
/// remembered to be bumped.
fn model_version() -> &'static str {
    static VERSION: OnceLock<String> = OnceLock::new();
    VERSION.get_or_init(|| {
        let mut h = Sha256::new();
        for source in spc_dsp::SOURCES {
            h.update((source.len() as u64).to_le_bytes());
            h.update(source);
        }
        h.update(include_str!("ceilings.rs").as_bytes());
        cache::hex(&h.finalize())
    })
}

/// The disk cache's category for the songs' peaks.
const CATEGORY: &str = "ceilings";

/// What this process already played, by key, so that the cartridges a
/// build converts at once, in threads, play a song they share once: the
/// second waits for the first.
type Memo = HashMap<String, Arc<OnceLock<Played>>>;
static PLAYED: Mutex<Option<Memo>> = Mutex::new(None);

/// What [`measure`] gave: each song's [`Played`], and how many of them it
/// had to play —the rest came from the cache, or from another cartridge of
/// the same process—, which is what the time went on.
pub struct Measured {
    pub played: Vec<Played>,
    pub new: usize,
}

/// Each of `songs` [`loudest`], in threads, from the cache in `cache` when
/// it has it —and into it when it did not—.
pub fn measure(songs: &[Song], cache: Option<&Path>) -> Measured {
    let keys: Vec<String> = songs.iter().map(Song::key).collect();
    let cells: Vec<Arc<OnceLock<Played>>> = {
        let mut played = PLAYED.lock().unwrap_or_else(|e| e.into_inner());
        let played = played.get_or_insert_with(HashMap::new);
        keys.iter()
            .map(|k| played.entry(k.clone()).or_default().clone())
            .collect()
    };
    let new = AtomicUsize::new(0);
    let one = |i: usize| -> Played {
        *cells[i].get_or_init(|| {
            if let Some(stored) = cache
                .and_then(|dir| cache::load(dir, CATEGORY, &keys[i]))
                .and_then(|v| parse(&v))
            {
                return stored;
            }
            let played = loudest(&songs[i]);
            new.fetch_add(1, Ordering::Relaxed);
            if let Some(dir) = cache {
                cache::store(
                    dir,
                    CATEGORY,
                    &keys[i],
                    format!("{} {}\n", played.peak, played.clipped).as_bytes(),
                );
            }
            played
        })
    };
    let threads = std::thread::available_parallelism()
        .map_or(1, |n| n.get())
        .min(songs.len().max(1));
    let next = Mutex::new(0usize);
    let out: Mutex<Vec<Option<Played>>> = Mutex::new(vec![None; songs.len()]);
    std::thread::scope(|scope| {
        for _ in 0..threads {
            scope.spawn(|| loop {
                let i = {
                    let mut n = next.lock().unwrap_or_else(|e| e.into_inner());
                    *n += 1;
                    *n - 1
                };
                if i >= songs.len() {
                    break;
                }
                let played = one(i);
                out.lock().unwrap_or_else(|e| e.into_inner())[i] = Some(played);
            });
        }
    });
    let played = out
        .into_inner()
        .unwrap_or_else(|e| e.into_inner())
        .into_iter()
        .map(|p| p.expect("every song was played"))
        .collect();
    Measured {
        played,
        new: new.into_inner(),
    }
}

/// A stored `<peak> <clipped>`.
fn parse(value: &[u8]) -> Option<Played> {
    let text = std::str::from_utf8(value).ok()?;
    let mut parts = text.split_whitespace();
    let peak = parts.next()?.parse().ok()?;
    let clipped = parts.next()?.parse().ok()?;
    Some(Played { peak, clipped })
}

/// The peak in dB against the cap.
pub fn db(peak: i64) -> f64 {
    20.0 * (peak.max(1) as f64 / cap() as f64).log10()
}

/// The headroom that leaves a peak `peak` measured at `measured_with` at
/// [`margin`] below the cap, in thousandths and rounded down, and never
/// more than `limit`.
pub fn ceiling(peak: f64, measured_with: f64, limit: f64) -> f64 {
    let full = peak * HEADROOM / measured_with;
    let c = (1000.0 * HEADROOM * cap() as f64 * margin() / full.max(1.0)).floor() / 1000.0;
    c.min(limit)
}

/// A song that still clipped with `current`, lowered by as much as it went
/// over.
pub fn lowered(current: f64, peak: i64) -> f64 {
    (1000.0 * current * cap() as f64 * margin() / peak as f64).floor() / 1000.0
}

/// Whether a song whose peak was `peak` with `measured_with` comes close
/// enough to the cap with `headroom` to be played again with it.
pub fn is_close(peak: i64, measured_with: f64, headroom: f64) -> bool {
    peak as f64 * headroom / measured_with >= cap() as f64 * close()
}

#[cfg(test)]
mod tests {
    use super::*;

    static SQUARE: [u8; 9] = [0xB3, 0x77, 0x77, 0x77, 0x77, 0x99, 0x99, 0x99, 0x99];

    /// A looping square wave in entry 7, keyed on at frame 1 on voice 0 at
    /// `volume`, and off at frame 30.
    fn square(volume: u8) -> Song {
        let mut writes: Vec<Write> = crate::stream::init_writes()
            .into_iter()
            .map(|(r, v)| (0, r, v))
            .collect();
        for (r, v) in [
            (0x00, volume),
            (0x01, volume),
            (0x02, 0x00),
            (0x03, 0x10),
            (0x04, 7),
            (0x05, 0x00),
            (0x07, 0x7F),
        ] {
            writes.push((0, r, v));
        }
        writes.push((1, sdsp::KON, 0x01));
        writes.push((30, sdsp::KOF, 0x01));
        Song::new("square", writes, |srcn| {
            (srcn == 7).then_some((&SQUARE[..], 0))
        })
        .unwrap()
    }

    #[test]
    fn a_song_sounds_and_a_louder_one_peaks_higher() {
        let soft = loudest(&square(0x20));
        let loud = loudest(&square(0x40));
        assert!(soft.peak > 0, "it sounds");
        assert!(loud.peak > soft.peak + soft.peak / 2, "{loud:?} {soft:?}");
        assert_eq!(soft.clipped, 0);
    }

    #[test]
    fn the_samples_go_where_the_directory_says() {
        let song = square(0x20);
        let entry = DIRECTORY + 4 * 7;
        let at = (FIRST_SAMPLE as u16).to_le_bytes();
        assert_eq!(&song.aram[entry..entry + 4], &[at[0], at[1], at[0], at[1]]);
        assert_eq!(song.aram[FIRST_SAMPLE], 0xB3);
        assert_eq!(song.frames, 31 + AFTER_END);
    }

    #[test]
    fn what_is_measured_is_kept_and_found_again() {
        let dir = std::env::temp_dir().join(format!("ceilings-cache-{}", std::process::id()));
        let songs = [square(0x30)];
        let first = measure(&songs, Some(&dir));
        assert_eq!(first.new, 1);
        let stored = cache::load(&dir, CATEGORY, &songs[0].key()).expect("it was stored");
        assert_eq!(parse(&stored), Some(first.played[0]));
        // What is stored is what is read, with the process's memo
        // forgotten.
        *PLAYED.lock().unwrap() = None;
        cache::store(&dir, CATEGORY, &songs[0].key(), b"123 4\n");
        let again = measure(&songs, Some(&dir));
        assert_eq!(again.new, 0);
        assert_eq!(
            again.played[0],
            Played {
                peak: 123,
                clipped: 4
            }
        );
        *PLAYED.lock().unwrap() = None;
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_ceiling_leaves_the_peak_half_a_db_below_the_cap() {
        let peak = cap() as f64 / 4.0;
        let c = ceiling(peak, MEASURING_HEADROOM, 10.0);
        let full = peak * c / MEASURING_HEADROOM;
        assert!((db(full as i64) + 0.5).abs() < 0.01, "{}", db(full as i64));
        assert_eq!(
            ceiling(cap() as f64 / 100.0, MEASURING_HEADROOM, HEADROOM),
            HEADROOM
        );
    }
}
