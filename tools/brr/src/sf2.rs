//! SoundFont 2, read far enough to pull one sample out per instrument.
//!
//! A .sf2 is a RIFF file in three parts: metadata, one enormous block of raw
//! PCM, and a database saying which piece of that PCM belongs to which
//! instrument and which range of notes.
//!
//! That database —the "hydra"— is nine tables chained together:
//!
//! ```text
//! phdr  presets       each one a General MIDI program
//!  |    pbag  zones   a preset can have several
//!  |     |    pgen    generators: the zone's parameters
//!  v          |
//! inst  instruments   what generator 41 points at
//!       ibag  zones   one per range of notes and velocities
//!        |    igen    generators, generator 53 among them: which sample
//!        v
//! shdr  samples       where it starts and ends in the PCM, and its loop
//! ```
//!
//! A real instrument is multi-sampled: a piano has a different recording every
//! few notes. Anything with a sample budget has to pick one per instrument and
//! transpose it, which is why `zone_for` takes a reference key and answers
//! with the zone covering it.
//!
//! These files run to hundreds of megabytes, nearly all of it PCM. The hydra,
//! which is small, is read whole; the audio is seeked to only when asked for.

use crate::fail::{Bad, Result};
use std::collections::HashMap;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

/// The generators that matter here. The full list has sixty and lives in the
/// specification; the rest are modulation parameters nothing below reads.
pub const GEN_START_OFFSET: u16 = 0;
pub const GEN_END_OFFSET: u16 = 1;
pub const GEN_STARTLOOP_OFFSET: u16 = 2;
pub const GEN_ENDLOOP_OFFSET: u16 = 3;
pub const GEN_START_COARSE: u16 = 4;
pub const GEN_END_COARSE: u16 = 12;
pub const GEN_PAN: u16 = 17;
pub const GEN_ATTACK: u16 = 34;
pub const GEN_HOLD: u16 = 35;
pub const GEN_DECAY: u16 = 36;
pub const GEN_RELEASE: u16 = 38;
pub const GEN_INSTRUMENT: u16 = 41;
pub const GEN_KEY_RANGE: u16 = 43;
pub const GEN_STARTLOOP_COARSE: u16 = 45;
pub const GEN_ENDLOOP_COARSE: u16 = 50;
pub const GEN_COARSE_TUNE: u16 = 51;
pub const GEN_FINE_TUNE: u16 = 52;
pub const GEN_SAMPLE_ID: u16 = 53;
pub const GEN_SAMPLE_MODES: u16 = 54;
pub const GEN_ROOT_KEY: u16 = 58;

/// Offsets arrive split across two generators, one fine and one in units of
/// 32768 samples, and the two have to be added.
const COARSE: [(u16, u16); 4] = [
    (GEN_START_COARSE, GEN_START_OFFSET),
    (GEN_END_COARSE, GEN_END_OFFSET),
    (GEN_STARTLOOP_COARSE, GEN_STARTLOOP_OFFSET),
    (GEN_ENDLOOP_COARSE, GEN_ENDLOOP_OFFSET),
];

/// Generators whose amount is a signed value rather than a plain number.
const SIGNED: [u16; 7] = [
    GEN_COARSE_TUNE,
    GEN_FINE_TUNE,
    GEN_ATTACK,
    GEN_DECAY,
    GEN_RELEASE,
    GEN_HOLD,
    GEN_PAN,
];

const OFFSETS: [u16; 4] = [
    GEN_START_OFFSET,
    GEN_END_OFFSET,
    GEN_STARTLOOP_OFFSET,
    GEN_ENDLOOP_OFFSET,
];

pub const LOOP_NONE: i32 = 0;
pub const LOOP_CONTINUOUS: i32 = 1;
pub const LOOP_UNTIL_RELEASE: i32 = 3;

/// The percussion bank of General MIDI, where each key is a different
/// instrument instead of a different pitch.
pub const DRUM_BANK: u16 = 128;

/// One shdr entry: where the audio lives and how it is meant to be played.
#[derive(Clone, Debug)]
pub struct Sample {
    pub name: String,
    pub start: u32,
    pub end: u32,
    pub loop_start: u32,
    pub loop_end: u32,
    pub rate: u32,
    pub root_key: u8,
    /// Pitch correction in cents, on top of the root key.
    pub correction: i8,
}

impl Sample {
    pub fn frames(&self) -> u32 {
        self.end.saturating_sub(self.start)
    }
}

/// An instrument zone with its generators already resolved.
#[derive(Clone, Debug, Default)]
pub struct Zone {
    gens: HashMap<u16, i32>,
}

impl Zone {
    pub fn get(&self, operator: u16) -> Option<i32> {
        self.gens.get(&operator).copied()
    }

    pub fn get_or(&self, operator: u16, default: i32) -> i32 {
        self.get(operator).unwrap_or(default)
    }

    /// A range generator packs its two ends into one amount: low byte, high byte.
    pub fn covers(&self, key: u8) -> bool {
        match self.get(GEN_KEY_RANGE) {
            None => true,
            Some(range) => {
                let (low, high) = ((range & 0xFF) as u8, ((range >> 8) & 0xFF) as u8);
                low <= key && key <= high
            }
        }
    }

    pub fn sample_id(&self) -> Option<i32> {
        self.get(GEN_SAMPLE_ID)
    }

    pub fn looped(&self) -> bool {
        let modes = self.get_or(GEN_SAMPLE_MODES, LOOP_NONE);
        modes == LOOP_CONTINUOUS || modes == LOOP_UNTIL_RELEASE
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Preset {
    pub program: u16,
    pub bank: u16,
    pub bag: u16,
}

#[derive(Clone, Copy, Debug)]
struct Bag {
    gen: u16,
}

#[derive(Debug)]
pub struct SoundFont {
    handle: File,
    pub path: PathBuf,
    pcm_offset: u64,
    pub pcm_frames: u64,
    presets: Vec<Preset>,
    preset_names: Vec<String>,
    preset_bags: Vec<Bag>,
    preset_gens: Vec<(u16, u16)>,
    instruments: Vec<(String, u16)>,
    inst_bags: Vec<Bag>,
    inst_gens: Vec<(u16, u16)>,
    pub samples: Vec<Sample>,
}

fn u16_at(data: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([data[at], data[at + 1]])
}

fn u32_at(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
}

/// A fixed-length name field, cut at its first NUL.
fn name_at(data: &[u8], at: usize, len: usize) -> String {
    let field = &data[at..at + len];
    let end = field.iter().position(|&b| b == 0).unwrap_or(len);
    field[..end].iter().map(|&b| b as char).collect()
}

/// A generator amount read as a signed 16-bit value.
fn signed(amount: u16) -> i32 {
    amount as i16 as i32
}

impl SoundFont {
    pub fn open(path: &Path) -> Result<SoundFont> {
        let mut handle = File::open(path)
            .map_err(|e| Bad(format!("{}: {e}", path.display())))?;

        let mut header = [0u8; 12];
        handle
            .read_exact(&mut header)
            .map_err(|_| Bad(format!("{}: too short to be a SoundFont", path.display())))?;
        if &header[..4] != b"RIFF" || &header[8..12] != b"sfbk" {
            return Err(Bad(format!(
                "{}: not a SoundFont (RIFF/sfbk), it starts with {:?}",
                path.display(),
                String::from_utf8_lossy(&header[..4])
            )));
        }

        let total = u32_at(&header, 4) as u64 + 8;
        let mut chunks: HashMap<[u8; 4], Vec<u8>> = HashMap::new();
        let mut pcm = None;

        let mut position = 12u64;
        while position < total {
            let Some((tag, size)) = read_tag(&mut handle, position) else { break };
            if &tag == b"LIST" {
                let mut kind = [0u8; 4];
                if handle.read_exact(&mut kind).is_err() {
                    break;
                }
                if &kind == b"sdta" || &kind == b"pdta" {
                    read_list(
                        &mut handle,
                        position + 12,
                        position + 8 + size as u64,
                        &mut chunks,
                        &mut pcm,
                    )?;
                }
            }
            // Chunks are aligned to two bytes.
            position += 8 + size as u64 + (size as u64 & 1);
        }

        let (pcm_offset, pcm_size) = pcm.ok_or_else(|| {
            Bad(format!("{}: no smpl chunk, so the file carries no audio", path.display()))
        })?;

        let table = |tag: &[u8; 4], size: usize| -> Result<Vec<&[u8]>> {
            let data = chunks.get(tag).ok_or_else(|| {
                Bad(format!(
                    "{}: missing the {} chunk",
                    path.display(),
                    String::from_utf8_lossy(tag)
                ))
            })?;
            Ok(data.chunks_exact(size).collect())
        };

        // The last record of phdr, inst and shdr is a terminator whose only
        // job is to say where the one before it ends.
        let phdr = table(b"phdr", 38)?;
        let presets: Vec<Preset> = phdr
            .iter()
            .map(|r| Preset { program: u16_at(r, 20), bank: u16_at(r, 22), bag: u16_at(r, 24) })
            .collect();
        let preset_names: Vec<String> = phdr.iter().map(|r| name_at(r, 0, 20)).collect();
        let preset_bags: Vec<Bag> =
            table(b"pbag", 4)?.iter().map(|r| Bag { gen: u16_at(r, 0) }).collect();
        let preset_gens: Vec<(u16, u16)> =
            table(b"pgen", 4)?.iter().map(|r| (u16_at(r, 0), u16_at(r, 2))).collect();
        let instruments: Vec<(String, u16)> =
            table(b"inst", 22)?.iter().map(|r| (name_at(r, 0, 20), u16_at(r, 20))).collect();
        let inst_bags: Vec<Bag> =
            table(b"ibag", 4)?.iter().map(|r| Bag { gen: u16_at(r, 0) }).collect();
        let inst_gens: Vec<(u16, u16)> =
            table(b"igen", 4)?.iter().map(|r| (u16_at(r, 0), u16_at(r, 2))).collect();
        let samples: Vec<Sample> = table(b"shdr", 46)?
            .iter()
            .map(|r| Sample {
                name: name_at(r, 0, 20),
                start: u32_at(r, 20),
                end: u32_at(r, 24),
                loop_start: u32_at(r, 28),
                loop_end: u32_at(r, 32),
                rate: u32_at(r, 36),
                root_key: r[40],
                correction: r[41] as i8,
            })
            .collect();

        if presets.len() < 2 || instruments.len() < 2 || samples.len() < 2 {
            return Err(Bad(format!(
                "{}: the hydra is empty ({} presets, {} instruments, {} samples)",
                path.display(),
                presets.len(),
                instruments.len(),
                samples.len()
            )));
        }

        Ok(SoundFont {
            handle,
            path: path.to_path_buf(),
            pcm_offset,
            pcm_frames: pcm_size as u64 / 2,
            presets,
            preset_names,
            preset_bags,
            preset_gens,
            instruments,
            inst_bags,
            inst_gens,
            samples,
        })
    }

    pub fn preset_count(&self) -> usize {
        self.presets.len().saturating_sub(1)
    }

    pub fn preset(&self, index: usize) -> (Preset, &str) {
        (self.presets[index], &self.preset_names[index])
    }

    /// The preset for a General MIDI program, or none.
    pub fn find_preset(&self, program: u16, bank: u16) -> Option<usize> {
        (0..self.preset_count())
            .find(|&i| self.presets[i].program == program && self.presets[i].bank == bank)
    }

    /// The zones of a preset or instrument, with their generators.
    ///
    /// The first zone may be global: if it does not carry the generator
    /// pointing at whatever comes next —an instrument or a sample—, its values
    /// are the defaults for the zones that follow and have to be carried down.
    fn zones(
        bags: &[Bag],
        gens: &[(u16, u16)],
        first: usize,
        last: usize,
        terminal: u16,
    ) -> Vec<Zone> {
        let mut zones = Vec::new();
        let mut common: HashMap<u16, i32> = HashMap::new();

        for index in first..last.min(bags.len()) {
            let start = bags[index].gen as usize;
            let end = if index + 1 < bags.len() {
                bags[index + 1].gen as usize
            } else {
                gens.len()
            };
            let mut generators = common.clone();

            let (start, end) = (start.min(gens.len()), end.min(gens.len()));
            for &(operator, amount) in &gens[start..end.max(start)] {
                if let Some(&(_, target)) = COARSE.iter().find(|(c, _)| *c == operator) {
                    let was = generators.get(&target).copied().unwrap_or(0);
                    generators.insert(target, was + signed(amount) * 32768);
                } else if OFFSETS.contains(&operator) {
                    let was = generators.get(&operator).copied().unwrap_or(0);
                    generators.insert(operator, was + signed(amount));
                } else if SIGNED.contains(&operator) {
                    generators.insert(operator, signed(amount));
                } else {
                    generators.insert(operator, amount as i32);
                }
            }

            if index == first && !generators.contains_key(&terminal) {
                common = generators; // a global zone: its values are inherited
                continue;
            }
            zones.push(Zone { gens: generators });
        }
        zones
    }

    pub fn preset_zones(&self, index: usize) -> Vec<Zone> {
        let first = self.presets[index].bag as usize;
        let last = self.presets[index + 1].bag as usize;
        Self::zones(&self.preset_bags, &self.preset_gens, first, last, GEN_INSTRUMENT)
    }

    pub fn instrument_zones(&self, index: usize) -> Vec<Zone> {
        let first = self.instruments[index].1 as usize;
        let last = self.instruments[index + 1].1 as usize;
        Self::zones(&self.inst_bags, &self.inst_gens, first, last, GEN_SAMPLE_ID)
    }

    /// The instrument zone covering that note, with its sample.
    ///
    /// Where several zones cover the note —usually velocity layers— the first
    /// one wins, which in the common banks is the softest and the one with the
    /// least attack noise.
    pub fn zone_for(&self, program: u16, key: u8, bank: u16) -> Option<(Zone, Sample)> {
        let preset = self.find_preset(program, bank)?;
        for zone in self.preset_zones(preset) {
            let Some(instrument) = zone.get(GEN_INSTRUMENT) else { continue };
            if !zone.covers(key) {
                continue;
            }
            let instrument = instrument as usize;
            if instrument + 1 >= self.instruments.len() {
                continue;
            }
            for inner in self.instrument_zones(instrument) {
                let Some(id) = inner.sample_id() else { continue };
                if !inner.covers(key) {
                    continue;
                }
                let id = id as usize;
                if id >= self.samples.len() {
                    continue;
                }
                let sample = self.samples[id].clone();
                return Some((inner, sample));
            }
        }
        None
    }

    /// The shdr entry with that exact name, if the font has one.
    pub fn find_sample(&self, name: &str) -> Option<&Sample> {
        self.samples.iter().find(|s| s.name == name)
    }

    /// The signed 16-bit samples between those two indices into the PCM block.
    pub fn pcm(&mut self, start: u32, end: u32) -> Result<Vec<i16>> {
        if end <= start {
            return Ok(Vec::new());
        }
        let count = (end - start) as usize;
        self.handle
            .seek(SeekFrom::Start(self.pcm_offset + start as u64 * 2))
            .map_err(|e| Bad(format!("{}: {e}", self.path.display())))?;
        let mut raw = vec![0u8; count * 2];
        self.handle
            .read_exact(&mut raw)
            .map_err(|_| {
                Bad(format!(
                    "{}: the audio block ends before sample {end} (it holds {})",
                    self.path.display(),
                    self.pcm_frames
                ))
            })?;
        Ok(raw.chunks_exact(2).map(|c| i16::from_le_bytes([c[0], c[1]])).collect())
    }
}

fn read_tag(handle: &mut File, position: u64) -> Option<([u8; 4], u32)> {
    handle.seek(SeekFrom::Start(position)).ok()?;
    let mut head = [0u8; 8];
    handle.read_exact(&mut head).ok()?;
    let mut tag = [0u8; 4];
    tag.copy_from_slice(&head[..4]);
    Some((tag, u32_at(&head, 4)))
}

fn read_list(
    handle: &mut File,
    start: u64,
    end: u64,
    chunks: &mut HashMap<[u8; 4], Vec<u8>>,
    pcm: &mut Option<(u64, u32)>,
) -> Result<()> {
    let mut position = start;
    while position < end {
        let Some((tag, size)) = read_tag(handle, position) else { break };
        if &tag == b"smpl" {
            // Of the PCM only its whereabouts are kept: it is most of the file.
            *pcm = Some((position + 8, size));
        } else {
            let mut body = vec![0u8; size as usize];
            if handle.read_exact(&mut body).is_err() {
                break;
            }
            chunks.insert(tag, body);
        }
        position += 8 + size as u64 + (size as u64 & 1);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write_temp(name: &str, bytes: &[u8]) -> PathBuf {
        let path = std::env::temp_dir().join(format!(
            "brr-test-{}-{:?}-{name}",
            std::process::id(),
            std::thread::current().id()
        ));
        std::fs::write(&path, bytes).unwrap();
        path
    }

    #[test]
    fn a_file_that_is_not_a_soundfont_says_so_and_names_itself() {
        let path = write_temp("junk.sf2", b"MThd\0\0\0\x06not a soundfont at all");
        let e = SoundFont::open(&path).unwrap_err();
        let _ = std::fs::remove_file(&path);
        assert!(e.0.contains("not a SoundFont"), "{e}");
        assert!(e.0.to_lowercase().contains("junk.sf2"), "{e}");
    }

    #[test]
    fn a_missing_file_is_reported_with_its_name() {
        let e = SoundFont::open(Path::new("/nonexistent/none.sf2")).unwrap_err();
        assert!(e.0.contains("/nonexistent/none.sf2"), "{e}");
    }

    #[test]
    fn a_truncated_file_does_not_panic() {
        let path = write_temp("tiny.sf2", b"RIFF");
        let e = SoundFont::open(&path).unwrap_err();
        let _ = std::fs::remove_file(&path);
        assert!(e.0.contains("too short"), "{e}");
    }

    #[test]
    fn a_riff_with_no_audio_says_the_audio_is_what_is_missing() {
        // A well-formed sfbk header with nothing in it: the shape is right and
        // the content is not, which is the confusing case worth a message.
        let mut bytes = b"RIFF\0\0\0\0sfbk".to_vec();
        let size = (bytes.len() - 8) as u32;
        bytes[4..8].copy_from_slice(&size.to_le_bytes());
        let path = write_temp("empty.sf2", &bytes);
        let e = SoundFont::open(&path).unwrap_err();
        let _ = std::fs::remove_file(&path);
        assert!(e.0.contains("no smpl chunk"), "{e}");
    }

    #[test]
    fn a_key_range_is_two_bytes_of_one_amount() {
        let mut zone = Zone::default();
        zone.gens.insert(GEN_KEY_RANGE, 36 | (48 << 8));
        assert!(!zone.covers(35));
        assert!(zone.covers(36) && zone.covers(42) && zone.covers(48));
        assert!(!zone.covers(49));
        // No range at all means every key, which is what the format says.
        assert!(Zone::default().covers(0) && Zone::default().covers(127));
    }
}
