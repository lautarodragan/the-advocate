//! `build/advocate.json`: what a build leaves for whoever is not a tool
//! —a game's tests, its recipes—, so that they read a file instead of
//! asking a binary. Written by every `advocate build`, also when every
//! cartridge was up to date and when one failed, **aside and renamed**: the
//! ports' suite builds several games at once, and a reader must never see
//! half a file.
//!
//! One object, each key what one of the old questions answered, unchanged
//! inside, so a reader's change is "read a key" instead of "run a binary":
//!
//! * `project`, `suite`, `settings`: what `rm2k-snes-project` printed —the
//!   project's paths, the suite's own (`directory`, `root`, `runtime`,
//!   `harness`) and the whole project file—, see `resolved` in
//!   `rm2k-project`;
//! * `machine`: each machine value the build was given, `{"given": …,
//!   "read": …}`, `read` being the directory it is read from —its unpacked
//!   copy if it is a `.zip`, the game with the port's own files on top—:
//!   what `rm2k-snes-project --unpacked` printed;
//! * `listing`: what `rm2k-snes-cartridges --list --json` printed —the
//!   cartridges, their cases, where each case runs, the fingerprint and
//!   whether each one is up to date **when the build ended**—, with each
//!   cartridge's `space`: what `space --json` printed of it, from when it was
//!   built, or `null` if it is stale;
//! * `patches`: the versioned patches against what the cartridges decided
//!   —`stale`, `compared`, `versioned`, `own`—, what `rm2k-snes-patches
//!   --check` said;
//!   `null` if the game versions none (it has no `patches/auto/`) or no
//!   cartridge is built with patches. See `patches.rs`;
//! * `memory_map`: what `assemble --memory-map` printed;
//! * `sources`: the runtime's `main.s` and what it includes, in `ca65`'s
//!   order, as `assemble --sources` printed them.
//!
//! **"Up to date" is what the build saw**, not what a test sees later: a
//! source edited after building and before a `pytest` run by hand is not
//! noticed. Every recipe that runs tests builds first. taro's, 2026-11-25.

use std::path::Path;

use cartridge::assemble::{memory_map, sources};
use cartridge::cartridges::Cartridges;
use rm2k_project::environment::Environment;
use serde_json::{json, Map, Value};

/// The file's name, in the project's build.
pub const NAME: &str = "advocate.json";

/// Writes the file for `cartridges`, built with what the machine `given`,
/// and answers what it wrote.
pub fn write(cartridges: &Cartridges, given: &Environment) -> Result<Value, String> {
    let project = &cartridges.project;
    let Value::Object(mut out) = rm2k_project::resolved(project)? else {
        unreachable!("resolved is an object");
    };
    let mut machine = Map::new();
    for (name, value) in given.values() {
        let read = cartridges
            .environment
            .values()
            .into_iter()
            .find(|(n, _)| *n == name)
            .map(|(_, read)| read.to_path_buf())
            .unwrap_or_else(|| value.to_path_buf());
        machine.insert(name.into(), json!({"given": value, "read": read}));
    }
    out.insert("machine".into(), Value::Object(machine));
    let mut listing = cartridges.describe()?;
    for entry in listing["cartridges"]
        .as_array_mut()
        .expect("describe lists the cartridges")
    {
        let name = entry["name"].as_str().unwrap_or_default().to_string();
        let space = if entry["stale"].is_null() {
            // One built by another builder has none yet.
            match cartridges.space(&name)? {
                Some(space) => space,
                None => cartridges.measure_space(&name)?,
            }
        } else {
            Value::Null
        };
        entry["space"] = space;
    }
    out.insert("listing".into(), listing);
    out.insert("patches".into(), crate::patches::compare(cartridges)?);
    out.insert("memory_map".into(), memory_map());
    let main = cartridges.runtime.join("main.s");
    out.insert("sources".into(), json!(sources(&main)?));
    let out = Value::Object(out);

    let build = project.build()?;
    std::fs::create_dir_all(&build).map_err(|e| format!("{}: {e}", build.display()))?;
    let file = build.join(NAME);
    aside_and_renamed(&file, format!("{out:#}\n").as_bytes())?;
    Ok(out)
}

/// `bytes` into `file`, written beside it and renamed over it, so a reader
/// sees the old file or the new one and never half of either.
fn aside_and_renamed(file: &Path, bytes: &[u8]) -> Result<(), String> {
    let aside = file.with_extension(format!("json.{}.tmp", std::process::id()));
    std::fs::write(&aside, bytes).map_err(|e| format!("{}: {e}", aside.display()))?;
    std::fs::rename(&aside, file).map_err(|e| {
        let _ = std::fs::remove_file(&aside);
        format!("{}: {e}", file.display())
    })
}
