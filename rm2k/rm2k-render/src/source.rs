//! Where a map and its ChipSet come from.
//!
//! Two ways in, and they end in the same [`Map`]:
//!
//! * **a request**: a JSON file with the map's size, its two layers and its
//!   ChipSet entry. It is how a caller that has already changed the map
//!   —patched it, baked something into a layer— asks for exactly that map;
//! * **the dump**: a map number, read from a Ditto dump with Ditto's own
//!   reader, and its ChipSet entry from the database's `chipsets`. The dump
//!   as Ditto wrote it: whatever a project patches on top of it is the
//!   caller's to apply, and then it is a request.
//!
//! A request is a piece of the dump —a `Map` and a `Chipset`, with Ditto's
//! field names— and Ditto's types read it, so it is not a format of its own:
//! a field it leaves out holds the format's default, as in the exact dump.

use crate::fail::{Bad, Result};
use crate::layers::Map;
use ditto::dump::Dump;
use ditto::schema::{Chipset, Map as DumpMap};
use std::path::{Path, PathBuf};

/// A map ready to draw, and the name of the ChipSet it is drawn with.
pub struct Source {
    pub map: Map,
    pub chipset_name: String,
}

fn source(map: DumpMap, chipset: Chipset, whose: &str) -> Result<Source> {
    let size = |name: &str, v: i32| {
        usize::try_from(v).map_err(|_| Bad::answer(format!("{whose}: `{name}` is {v}")))
    };
    let layer = |l: &[i16]| l.iter().map(|&t| t as i64).collect();
    Ok(Source {
        map: Map {
            width: size("width", map.width)?,
            height: size("height", map.height)?,
            lower_layer: layer(&map.lower_layer),
            upper_layer: layer(&map.upper_layer),
            passable_lower: chipset.passable_data_lower,
            passable_upper: chipset.passable_data_upper,
        },
        chipset_name: chipset.chipset_name,
    })
}

/// A request: `width`, `height`, `lower_layer`, `upper_layer`, and
/// `chipset` with `chipset_name`, `passable_data_lower` and
/// `passable_data_upper`.
pub fn request(path: &Path) -> Result<Source> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let whose = path.display().to_string();
    let bad = |e: serde_json::Error| Bad::answer(format!("{whose}: {e}"));
    let mut data: serde_json::Value = serde_json::from_str(&text).map_err(bad)?;
    let chipset = data
        .as_object_mut()
        .and_then(|o| o.remove("chipset"))
        .ok_or_else(|| Bad::answer(format!("{whose}: no `chipset`")))?;
    let chipset: Chipset = serde_json::from_value(chipset)
        .map_err(|e| Bad::answer(format!("{whose}: chipset: {e}")))?;
    source(serde_json::from_value(data).map_err(bad)?, chipset, &whose)
}

/// Map `id` from a Ditto dump.
pub fn dump(data_dir: &Path, id: u32) -> Result<Source> {
    let answer = |e: ditto::lcf::Error| Bad::answer(e.0);
    let dump = Dump::open(data_dir).map_err(answer)?;
    let map = dump.map(id).map_err(answer)?;
    let chipsets: Vec<Chipset> = dump.section("chipsets").map_err(answer)?;
    let whose = format!("map {id} of {}", data_dir.display());
    let chipset = chipsets
        .into_iter()
        .find(|c| c.id == map.chipset_id)
        .ok_or_else(|| {
            Bad::answer(format!(
                "{whose} is drawn with ChipSet {}, and the database has none",
                map.chipset_id
            ))
        })?;
    source(map, chipset, &whose)
}

/// Looks for `<dir>/<folder>/<name>.png` or `.bmp`, in each directory in
/// order, **without regard to case**: RM2k stores names without extension
/// and the games were made on Windows, so a map says nothing about the real
/// case of a file.
pub fn find_resource(dirs: &[PathBuf], folder: &str, name: &str) -> Option<PathBuf> {
    let (folder, name) = (folder.to_lowercase(), name.to_lowercase());
    for dir in dirs {
        let Ok(entries) = std::fs::read_dir(dir) else {
            continue;
        };
        for entry in entries.flatten() {
            if entry.file_name().to_string_lossy().to_lowercase() != folder {
                continue;
            }
            let Ok(files) = std::fs::read_dir(entry.path()) else {
                continue;
            };
            for file in files.flatten() {
                let path = file.path();
                let file_name = file.file_name().to_string_lossy().to_string();
                let (base, extension) = split_extension(&file_name);
                if base.to_lowercase() == name
                    && matches!(extension.to_lowercase().as_str(), ".png" | ".bmp")
                {
                    return Some(path);
                }
            }
        }
    }
    None
}

/// `name.ext` into `name` and `.ext`. A leading dot is not an extension.
fn split_extension(file_name: &str) -> (&str, &str) {
    match file_name.rfind('.') {
        Some(0) | None => (file_name, ""),
        Some(at) => file_name.split_at(at),
    }
}
