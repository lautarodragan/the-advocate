//! Just enough WAV to get PCM in and out.
//!
//! BRR carries no sample rate and no loop point, so the thing on either side
//! of this codec has to carry them instead. A mono 16-bit WAV is the least
//! surprising way to hand a sample around, and the one every editor opens.
//!
//! Reading is deliberately forgiving about what it accepts and loud about what
//! it does not: an 8-bit or multi-channel file is converted and said so, and
//! anything else stops with what the file actually contained.

use crate::fail::{Bad, Result};
use std::path::Path;

#[derive(Debug)]
pub struct Audio {
    pub samples: Vec<i16>,
    pub rate: u32,
    /// What had to be done to the file to get mono 16-bit out of it, if
    /// anything: worth printing, because it is a change to the data.
    pub note: Option<String>,
}

const FORMAT_PCM: u16 = 1;
const FORMAT_EXTENSIBLE: u16 = 0xFFFE;

fn u16_at(data: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([data[at], data[at + 1]])
}

fn u32_at(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
}

/// Signed 16-bit little-endian with no header at all.
pub fn read_raw(bytes: &[u8], rate: u32, path: &Path) -> Result<Audio> {
    if !bytes.len().is_multiple_of(2) {
        return Err(Bad(format!(
            "{}: {} bytes of raw 16-bit PCM, which is not a whole number of samples",
            path.display(),
            bytes.len()
        )));
    }
    Ok(Audio {
        samples: bytes
            .chunks_exact(2)
            .map(|c| i16::from_le_bytes([c[0], c[1]]))
            .collect(),
        rate,
        note: None,
    })
}

pub fn looks_like_wav(bytes: &[u8]) -> bool {
    bytes.len() >= 12 && &bytes[..4] == b"RIFF" && &bytes[8..12] == b"WAVE"
}

pub fn read(bytes: &[u8], path: &Path) -> Result<Audio> {
    let where_ = || path.display().to_string();
    if !looks_like_wav(bytes) {
        return Err(Bad(format!("{}: not a RIFF/WAVE file", where_())));
    }

    let (mut fmt_chunk, mut data_chunk) = (None, None);
    let mut at = 12;
    while at + 8 <= bytes.len() {
        let tag = &bytes[at..at + 4];
        let size = u32_at(bytes, at + 4) as usize;
        let body = at + 8;
        let end = (body + size).min(bytes.len());
        match tag {
            b"fmt " => fmt_chunk = Some(&bytes[body..end]),
            b"data" => data_chunk = Some(&bytes[body..end]),
            _ => {}
        }
        // Chunks are padded to an even length.
        at = body + size + (size & 1);
    }

    let fmt = fmt_chunk.ok_or_else(|| Bad(format!("{}: no fmt chunk", where_())))?;
    if fmt.len() < 16 {
        return Err(Bad(format!(
            "{}: fmt chunk is {} bytes, needs 16",
            where_(),
            fmt.len()
        )));
    }
    let data = data_chunk.ok_or_else(|| Bad(format!("{}: no data chunk", where_())))?;

    let format = u16_at(fmt, 0);
    let channels = u16_at(fmt, 2) as usize;
    let rate = u32_at(fmt, 4);
    let bits = u16_at(fmt, 14);

    if format != FORMAT_PCM && format != FORMAT_EXTENSIBLE {
        return Err(Bad(format!(
            "{}: format {format} is not uncompressed PCM; decode it first",
            where_()
        )));
    }
    if channels == 0 {
        return Err(Bad(format!("{}: zero channels", where_())));
    }

    let mut notes = Vec::new();
    let mut frames: Vec<i32> = match bits {
        8 => {
            notes.push("8-bit widened to 16".to_string());
            data.iter().map(|&b| ((b as i32) - 128) << 8).collect()
        }
        16 => data
            .chunks_exact(2)
            .map(|c| i16::from_le_bytes([c[0], c[1]]) as i32)
            .collect(),
        other => {
            return Err(Bad(format!(
                "{}: {other}-bit samples; only 8 and 16 are read",
                where_()
            )))
        }
    };

    if channels > 1 {
        notes.push(format!("{channels} channels averaged to mono"));
        frames = frames
            .chunks(channels)
            .map(|f| f.iter().sum::<i32>() / channels as i32)
            .collect();
    }

    Ok(Audio {
        samples: frames
            .into_iter()
            .map(|s| s.clamp(-32768, 32767) as i16)
            .collect(),
        rate,
        note: if notes.is_empty() {
            None
        } else {
            Some(notes.join(", "))
        },
    })
}

/// A mono 16-bit PCM file, which is what everything downstream expects.
pub fn write(samples: &[i16], rate: u32) -> Vec<u8> {
    let payload = samples.len() * 2;
    let mut out = Vec::with_capacity(44 + payload);
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&((36 + payload) as u32).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&FORMAT_PCM.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes()); // channels
    out.extend_from_slice(&rate.to_le_bytes());
    out.extend_from_slice(&(rate * 2).to_le_bytes()); // bytes per second
    out.extend_from_slice(&2u16.to_le_bytes()); // block align
    out.extend_from_slice(&16u16.to_le_bytes()); // bits
    out.extend_from_slice(b"data");
    out.extend_from_slice(&(payload as u32).to_le_bytes());
    for s in samples {
        out.extend_from_slice(&s.to_le_bytes());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn here() -> &'static Path {
        Path::new("test.wav")
    }

    #[test]
    fn what_is_written_is_what_comes_back() {
        let samples: Vec<i16> = (-100..100).map(|i| i * 300).collect();
        let back = read(&write(&samples, 22050), here()).unwrap();
        assert_eq!(back.samples, samples);
        assert_eq!(back.rate, 22050);
        assert!(back.note.is_none());
    }

    #[test]
    fn a_file_that_is_not_a_wav_says_so_and_names_itself() {
        let e = read(b"this is not audio at all", here()).unwrap_err();
        assert!(e.0.contains("test.wav"), "{e}");
        assert!(e.0.contains("RIFF"), "{e}");
    }

    #[test]
    fn a_wav_with_no_data_chunk_says_which_chunk_is_missing() {
        let mut bytes = write(&[0i16; 8], 8000);
        bytes[36..40].copy_from_slice(b"junk");
        let e = read(&bytes, here()).unwrap_err();
        assert!(e.0.contains("no data chunk"), "{e}");
    }

    #[test]
    fn an_unsupported_depth_says_what_the_file_actually_had() {
        let mut bytes = write(&[0i16; 8], 8000);
        bytes[34..36].copy_from_slice(&24u16.to_le_bytes());
        let e = read(&bytes, here()).unwrap_err();
        assert!(e.0.contains("24-bit"), "{e}");
    }

    #[test]
    fn raw_pcm_with_a_dangling_byte_is_refused_rather_than_truncated() {
        let e = read_raw(&[0, 0, 0], 8000, here()).unwrap_err();
        assert!(e.0.contains("not a whole number of samples"), "{e}");
    }
}
