//! Running a stage of the conversion, which is a program of its own.
//!
//! Each domain is an executable on the PATH: it reads the game from the
//! dump itself, gets what the cartridge decided in a JSON request, and
//! writes what it made into a directory —pieces of the `.inc` and a JSON
//! with what the rest of the conversion needs—. This runs one of those and
//! hands back what it wrote. What goes in the request and where each piece
//! goes is the converter's business, not this module's. See "One stage of a
//! converter" in `rm2k-snes-battle`'s README for the shape.

use crate::fail::{io, Result, Stop};
use serde_json::Value;
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};


/// A directory of its own for one call, removed when it is dropped.
pub struct Scratch(pub PathBuf);

impl Scratch {
    pub fn new(prefix: &str) -> Result<Scratch> {
        static COUNT: AtomicUsize = AtomicUsize::new(0);
        let n = COUNT.fetch_add(1, Ordering::Relaxed);
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.subsec_nanos())
            .unwrap_or(0);
        let dir = std::env::temp_dir().join(format!("{prefix}-{}-{n}-{stamp:x}", std::process::id()));
        std::fs::create_dir_all(&dir).map_err(|e| io(&dir, e))?;
        Ok(Scratch(dir))
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// The path of `binary` on the PATH, or why it is not there.
pub fn which(binary: &str, project: &str) -> Result<PathBuf> {
    let path = std::env::var_os("PATH").unwrap_or_default();
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(binary);
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    Err(Stop::new(format!(
        "`{binary}` is missing, one of the converter's stages.\n\nIt is a Rust binary of the \
         suite, and is installed as a system tool:\n\n    just install {project}"
    )))
}

fn write_request(dir: &Path, request: &Value) -> Result<PathBuf> {
    let path = dir.join("request.json");
    let text = serde_json::to_string(request).expect("a request is JSON");
    std::fs::write(&path, text).map_err(|e| io(&path, e))?;
    Ok(path)
}

/// `binary command --request <request> --out <dir> *flags`, and `{name:
/// bytes}` of every file it wrote. `project` is the name `install` knows
/// it by, for the message when it is not on the PATH. What it answers no
/// to stops the conversion with its message.
pub fn run(
    binary: &str,
    project: &str,
    command: &str,
    request: &Value,
    flags: &[OsString],
) -> Result<BTreeMap<String, Vec<u8>>> {
    let path = which(binary, project)?;
    let scratch = Scratch::new(binary)?;
    let request_path = write_request(&scratch.0, request)?;
    let out = scratch.0.join("out");
    let _ = std::io::stdout().flush();
    let done = Command::new(&path)
        .arg(command)
        .arg("--request")
        .arg(&request_path)
        .arg("--out")
        .arg(&out)
        .args(flags)
        .stdin(Stdio::null())
        .output()
        .map_err(|e| Stop::new(format!("{binary}: {e}")))?;
    if !done.status.success() {
        let text = String::from_utf8_lossy(&done.stderr).trim().to_string();
        return Err(Stop::new(if text.is_empty() {
            format!("{binary} {command} exited with {}", done.status.code().unwrap_or(-1))
        } else {
            text
        }));
    }
    let mut written = BTreeMap::new();
    let mut names: Vec<_> = std::fs::read_dir(&out)
        .map_err(|e| io(&out, e))?
        .flatten()
        .map(|e| e.file_name().to_string_lossy().to_string())
        .collect();
    names.sort();
    for name in names {
        let file = out.join(&name);
        written.insert(name, std::fs::read(&file).map_err(|e| io(&file, e))?);
    }
    Ok(written)
}

/// A file a stage wrote, as text.
pub fn text(written: &BTreeMap<String, Vec<u8>>, name: &str) -> Result<String> {
    let bytes = written
        .get(name)
        .ok_or_else(|| Stop::new(format!("the stage did not write {name}")))?;
    String::from_utf8(bytes.clone()).map_err(|e| Stop::new(format!("{name}: {e}")))
}

/// A JSON file a stage wrote.
pub fn json(written: &BTreeMap<String, Vec<u8>>, name: &str) -> Result<Value> {
    serde_json::from_str(&text(written, name)?).map_err(|e| Stop::new(format!("{name}: {e}")))
}

/// `binary [command] --request <request> *args`, for a program that writes
/// what it makes where `args` say, and whose output goes out with what the
/// converter prints: `rm2k-snes-patches`, which writes what the converter
/// decided to lose next to the ROM, and the music, `rm2k-snes-audio
/// cartridge`, whose pieces the rest of the conversion reads none of.
pub fn hand_over(
    binary: &str,
    project: &str,
    request: &Value,
    args: &[OsString],
    command: Option<&str>,
) -> Result<()> {
    let path = which(binary, project)?;
    let scratch = Scratch::new(binary)?;
    let request_path = write_request(&scratch.0, request)?;
    let _ = std::io::stdout().flush();
    let mut call = Command::new(&path);
    if let Some(command) = command {
        call.arg(command);
    }
    let done = call
        .arg("--request")
        .arg(&request_path)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| Stop::new(format!("{binary}: {e}")))?;
    if !done.status.success() {
        let text = String::from_utf8_lossy(&done.stderr).trim().to_string();
        return Err(Stop::new(if text.is_empty() {
            format!("{binary} exited with {}", done.status.code().unwrap_or(-1))
        } else {
            text
        }));
    }
    Ok(())
}
