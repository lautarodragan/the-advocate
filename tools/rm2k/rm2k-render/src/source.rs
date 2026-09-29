//! Where a map and its ChipSet come from.
//!
//! Two ways in, and they end in the same [`Map`]:
//!
//! * **a request**: a JSON file with the map's size, its two layers and its
//!   ChipSet entry. It is how a caller that has already changed the map
//!   —patched it, baked something into a layer— asks for exactly that map;
//! * **the dump**: a map number, read from the project's Ditto dump
//!   (`maps/MapNNNN.json`, with its layers in the `.tiles` beside it) and
//!   its ChipSet entry from `db/chipsets.json`. The dump as Ditto wrote it:
//!   whatever a project patches on top of it is the caller's to apply, and
//!   then it is a request.
//!
//! Both use Ditto's field names, so a request is a piece of the dump and
//! not a format of its own.

use crate::fail::{Bad, Result};
use crate::layers::Map;
use serde_json::Value;
use std::path::{Path, PathBuf};

/// A map ready to draw, and the name of the ChipSet it is drawn with.
pub struct Source {
    pub map: Map,
    pub chipset_name: String,
}

fn read_json(path: &Path) -> Result<Value> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{}: {e}", path.display())))
}

fn field<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Value> {
    data.get(name)
        .ok_or_else(|| Bad::answer(format!("{whose}: no `{name}`")))
}

fn number(data: &Value, name: &str, whose: &str) -> Result<i64> {
    field(data, name, whose)?
        .as_i64()
        .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` is not a whole number")))
}

fn numbers(data: &Value, name: &str, whose: &str) -> Result<Vec<i64>> {
    let bad = || Bad::answer(format!("{whose}: `{name}` is not a list of whole numbers"));
    field(data, name, whose)?
        .as_array()
        .ok_or_else(bad)?
        .iter()
        .map(|v| v.as_i64().ok_or_else(bad))
        .collect()
}

fn bytes(data: &Value, name: &str, whose: &str) -> Result<Vec<u8>> {
    numbers(data, name, whose)?
        .into_iter()
        .map(|v| {
            u8::try_from(v)
                .map_err(|_| Bad::answer(format!("{whose}: `{name}` has {v}, not a byte")))
        })
        .collect()
}

fn size(data: &Value, name: &str, whose: &str) -> Result<usize> {
    let value = number(data, name, whose)?;
    usize::try_from(value).map_err(|_| Bad::answer(format!("{whose}: `{name}` is {value}")))
}

/// The ChipSet entry's name and passability, as Ditto names them.
fn chipset(entry: &Value, whose: &str) -> Result<(String, Vec<u8>, Vec<u8>)> {
    let name = field(entry, "chipset_name", whose)?
        .as_str()
        .ok_or_else(|| Bad::answer(format!("{whose}: `chipset_name` is not text")))?
        .to_string();
    Ok((
        name,
        bytes(entry, "passable_data_lower", whose)?,
        bytes(entry, "passable_data_upper", whose)?,
    ))
}

/// A request: `width`, `height`, `lower_layer`, `upper_layer`, and
/// `chipset` with `chipset_name`, `passable_data_lower` and
/// `passable_data_upper`.
pub fn request(path: &Path) -> Result<Source> {
    let data = read_json(path)?;
    let whose = path.display().to_string();
    let (chipset_name, passable_lower, passable_upper) = chipset(
        field(&data, "chipset", &whose)?,
        &format!("{whose}: chipset"),
    )?;
    Ok(Source {
        map: Map {
            width: size(&data, "width", &whose)?,
            height: size(&data, "height", &whose)?,
            lower_layer: numbers(&data, "lower_layer", &whose)?,
            upper_layer: numbers(&data, "upper_layer", &whose)?,
            passable_lower,
            passable_upper,
        },
        chipset_name,
    })
}

/// Map `id` from a Ditto dump.
pub fn dump(data_dir: &Path, id: u32) -> Result<Source> {
    let maps = data_dir.join("maps");
    let json = maps.join(format!("Map{id:04}.json"));
    let data = read_json(&json)?;
    let whose = json.display().to_string();
    let (width, height) = (
        size(&data, "width", &whose)?,
        size(&data, "height", &whose)?,
    );
    let tiles = maps.join(format!("Map{id:04}.tiles"));
    let (lower_layer, upper_layer) = if tiles.is_file() {
        grids(&tiles, width, height)?
    } else {
        (
            numbers(&data, "lower_layer", &whose)?,
            numbers(&data, "upper_layer", &whose)?,
        )
    };

    let chipset_id = number(&data, "chipset_id", &whose)?;
    let table = data_dir.join("db").join("chipsets.json");
    let entries = read_json(&table)?;
    let entry = entries
        .as_array()
        .and_then(|list| {
            list.iter()
                .find(|e| e.get("id").and_then(Value::as_i64) == Some(chipset_id))
        })
        .ok_or_else(|| {
            Bad::answer(format!(
                "{whose} is drawn with ChipSet {chipset_id}, and {} has none",
                table.display()
            ))
        })?;
    let (chipset_name, passable_lower, passable_upper) =
        chipset(entry, &format!("{}: ChipSet {chipset_id}", table.display()))?;
    Ok(Source {
        map: Map {
            width,
            height,
            lower_layer,
            upper_layer,
            passable_lower,
            passable_upper,
        },
        chipset_name,
    })
}

/// The two layers from the `.tiles` Ditto writes beside a map: one row per
/// line, and the two grids separated by comment lines.
fn grids(path: &Path, width: usize, height: usize) -> Result<(Vec<i64>, Vec<i64>)> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let mut grids: Vec<Vec<i64>> = vec![Vec::new()];
    for line in text.lines() {
        if line.starts_with('#') {
            if !grids.last().unwrap().is_empty() {
                grids.push(Vec::new());
            }
            continue;
        }
        for token in line.split_whitespace() {
            let id = token.parse().map_err(|_| {
                Bad::answer(format!("{}: `{token}` is not a tile id", path.display()))
            })?;
            grids.last_mut().unwrap().push(id);
        }
    }
    let expected = width * height;
    if grids.len() != 2 || grids.iter().any(|g| g.len() != expected) {
        let counts: Vec<usize> = grids.iter().map(Vec::len).collect();
        return Err(Bad::answer(format!(
            "{}: {counts:?} tiles for a {width}x{height} map",
            path.display()
        )));
    }
    let upper = grids.pop().unwrap();
    Ok((grids.pop().unwrap(), upper))
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

/// The name of the file a project is found by.
pub const PROJECT_FILE: &str = "rm2k-snes.toml";

/// The project's dump: `[paths] data` in its project file, relative to it.
/// The project is `--project`, or the nearest directory from the current
/// one upwards that has the file, the way cargo finds its `Cargo.toml`.
pub fn project_data(project: Option<&Path>) -> Result<PathBuf> {
    let directory = match project {
        Some(dir) => {
            if !dir.join(PROJECT_FILE).is_file() {
                return Err(Bad::usage(format!(
                    "{} has no {PROJECT_FILE}: --project is the directory where that file is",
                    dir.display()
                )));
            }
            dir.to_path_buf()
        }
        None => {
            let start = std::env::current_dir().map_err(|e| Bad::usage(e.to_string()))?;
            start
                .ancestors()
                .find(|dir| dir.join(PROJECT_FILE).is_file())
                .map(Path::to_path_buf)
                .ok_or_else(|| {
                    Bad::usage(format!(
                        "found no {PROJECT_FILE} in {} nor in any folder above it: run this \
                         from inside the project, or pass it --project <directory>",
                        start.display()
                    ))
                })?
        }
    };
    let file = directory.join(PROJECT_FILE);
    let text = std::fs::read_to_string(&file)
        .map_err(|e| Bad::usage(format!("{}: {e}", file.display())))?;
    let table: toml::Table = text
        .parse()
        .map_err(|e| Bad::usage(format!("{}: {e}", file.display())))?;
    let data = table
        .get("paths")
        .and_then(|p| p.get("data"))
        .and_then(|d| d.as_str())
        .ok_or_else(|| Bad::usage(format!("{}: no `data` in [paths]", file.display())))?;
    Ok(directory.join(data))
}
