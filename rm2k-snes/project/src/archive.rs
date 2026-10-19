//! A machine value that is a `.zip` instead of a directory: the original
//! game or the RTP, packed.
//!
//! **Nobody reads inside the `.zip`.** The tools look a resource up in
//! three different places, join paths by hand in a few more, and hand what
//! they find to other processes —the stages, `fluidsynth`, `ffmpeg`— as a
//! path. So the `.zip` is unpacked once, into the project's cache, and from
//! there on it is a directory like any other: see
//! [`crate::environment::Environment::unpack`], the only caller.
//!
//! The copy is named by the `.zip`'s content, so a different `.zip` is a
//! different directory and a copy is never half the old one and half the
//! new. It is written aside and renamed, because a game's tests ask for it
//! from several processes at once.
//!
//! What it reads is the plain `.zip`: stored or deflated entries, no
//! ZIP64, no encryption, names in UTF-8 —or ASCII—. What a game's `.zip`
//! needs, and what anything else gets an error for.

use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use flate2::read::DeflateDecoder;
use sha2::{Digest, Sha256};

use crate::cache;
use crate::Error;

/// Whether `path` is a `.zip`, by its name: a directory can not end in
/// `.zip` and be a game at the same time.
pub fn is_zip(path: &Path) -> bool {
    path.is_file()
        && path
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("zip"))
}

/// The sha256 of the whole `.zip`, in hex: what the copy is named by and
/// what the cartridges' fingerprint takes. Measured on 2026-10-11, the
/// biggest of the eight games —64 MB— takes ~50 ms.
pub fn content_hash(zip: &Path) -> Result<String, Error> {
    let bytes = fs::read(zip).map_err(|e| Error(format!("{}: {e}", zip.display())))?;
    Ok(cache::hex(&Sha256::digest(&bytes)))
}

/// The directory with `zip` unpacked, below `into`: made if it is not
/// there. `hash` is [`content_hash`] of the `.zip`.
pub fn unpacked(zip: &Path, hash: &str, into: &Path) -> Result<PathBuf, Error> {
    let stem = zip
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    let target = into.join(format!("{stem}-{}", &hash[..16]));
    if target.is_dir() {
        return Ok(target);
    }
    let fail = |e: std::io::Error, p: &Path| Error(format!("{}: {e}", p.display()));
    fs::create_dir_all(into).map_err(|e| fail(e, into))?;
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    let aside = into.join(format!(".{stem}.tmp-{}-{nanos}", std::process::id()));
    let _ = fs::remove_dir_all(&aside);
    let result = extract(zip, &aside);
    if let Err(e) = result {
        let _ = fs::remove_dir_all(&aside);
        return Err(e);
    }
    // Another process may have finished first: then its copy stays, which
    // is the same one.
    if fs::rename(&aside, &target).is_err() {
        let _ = fs::remove_dir_all(&aside);
        if !target.is_dir() {
            return Err(Error(format!(
                "{}: could not unpack into it",
                target.display()
            )));
        }
    }
    Ok(target)
}

fn u16_at(b: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([b[at], b[at + 1]])
}

fn u32_at(b: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([b[at], b[at + 1], b[at + 2], b[at + 3]])
}

/// Every entry of `zip`, written below `dest`.
pub fn extract(zip: &Path, dest: &Path) -> Result<(), Error> {
    let bad = |what: &str| Error(format!("{}: {what}", zip.display()));
    let b = fs::read(zip).map_err(|e| Error(format!("{}: {e}", zip.display())))?;
    // The end of central directory record: 22 bytes, plus a comment of up
    // to 64 KB after it.
    let lowest = b.len().saturating_sub(22 + 0xFFFF);
    let end = (lowest..b.len().saturating_sub(21))
        .rev()
        .find(|&i| u32_at(&b, i) == 0x0605_4b50)
        .ok_or_else(|| bad("not a .zip: it has no end of central directory"))?;
    let count = u16_at(&b, end + 10) as usize;
    let mut at = u32_at(&b, end + 16) as usize;
    if count == 0xFFFF || at == 0xFFFF_FFFF {
        return Err(bad("a ZIP64 archive, which this does not read"));
    }
    fs::create_dir_all(dest).map_err(|e| Error(format!("{}: {e}", dest.display())))?;
    for _ in 0..count {
        if at + 46 > b.len() || u32_at(&b, at) != 0x0201_4b50 {
            return Err(bad("a broken central directory"));
        }
        let flags = u16_at(&b, at + 8);
        let method = u16_at(&b, at + 10);
        let crc = u32_at(&b, at + 16);
        let packed = u32_at(&b, at + 20) as usize;
        let size = u32_at(&b, at + 24) as usize;
        let name_len = u16_at(&b, at + 28) as usize;
        let extra_len = u16_at(&b, at + 30) as usize;
        let comment_len = u16_at(&b, at + 32) as usize;
        let local = u32_at(&b, at + 42) as usize;
        let raw_name = b
            .get(at + 46..at + 46 + name_len)
            .ok_or_else(|| bad("a broken name"))?;
        at += 46 + name_len + extra_len + comment_len;
        // Bit 11 says UTF-8; without it, only ASCII is the same in every
        // encoding a `.zip` may have used.
        let name = std::str::from_utf8(raw_name)
            .ok()
            .filter(|n| flags & 0x0800 != 0 || n.is_ascii())
            .ok_or_else(|| bad("a name that is not UTF-8"))?;
        if flags & 0x0001 != 0 {
            return Err(bad(&format!("{name} is encrypted")));
        }
        let relative = Path::new(name);
        if relative
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
        {
            return Err(bad(&format!("{name}: a name that goes out of the .zip")));
        }
        let out = dest.join(relative);
        if name.ends_with('/') {
            fs::create_dir_all(&out).map_err(|e| Error(format!("{}: {e}", out.display())))?;
            continue;
        }
        if local + 30 > b.len() || u32_at(&b, local) != 0x0403_4b50 {
            return Err(bad(&format!("{name}: a broken local header")));
        }
        let start = local + 30 + u16_at(&b, local + 26) as usize + u16_at(&b, local + 28) as usize;
        let data = b
            .get(start..start + packed)
            .ok_or_else(|| bad(&format!("{name}: cut short")))?;
        let bytes = match method {
            0 => data.to_vec(),
            8 => {
                let mut out = Vec::with_capacity(size);
                DeflateDecoder::new(data)
                    .read_to_end(&mut out)
                    .map_err(|e| bad(&format!("{name}: {e}")))?;
                out
            }
            other => {
                return Err(bad(&format!(
                    "{name}: compression method {other}, not stored or deflate"
                )))
            }
        };
        let mut check = flate2::Crc::new();
        check.update(&bytes);
        if bytes.len() != size || check.sum() != crc {
            return Err(bad(&format!("{name}: its CRC or its size do not match")));
        }
        if let Some(parent) = out.parent() {
            fs::create_dir_all(parent).map_err(|e| Error(format!("{}: {e}", parent.display())))?;
        }
        fs::write(&out, &bytes).map_err(|e| Error(format!("{}: {e}", out.display())))?;
    }
    Ok(())
}
