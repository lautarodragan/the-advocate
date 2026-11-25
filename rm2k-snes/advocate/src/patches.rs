//! The versioned patches, `patches/auto/`: what the converter decided to
//! lose in the playable ROM, written down so a change to it shows in a
//! diff. See `rm2k-snes-patches` for what a patch is.
//!
//! **Every build compares them** against what its cartridges decided, says
//! the stale ones when it prints, and keeps the comparison in
//! `build/advocate.json` under `patches`; `--write-patches` writes them
//! from `release` first. Until 2026-11-25 that was `rm2k-snes-patches
//! --check` and `rm2k-snes-patches build/release`, run by hand and by ABL's
//! tests (taro, 2026-11-25: neither a command of its own nor a
//! subcommand).

use std::collections::BTreeSet;

use cartridge::cartridges::{Cartridges, RELEASE};
use rm2k_snes_patches::{check, copy, has_patches, versioned, Kind};
use serde_json::{json, Map, Value};

/// The project's test maps: what `release` carries only for the suite is
/// not versioned.
fn test_maps(cartridges: &Cartridges) -> Result<BTreeSet<i64>, String> {
    Ok(cartridges
        .project
        .ints(&["maps", "test"])?
        .into_iter()
        .collect())
}

/// Writes `release`'s decisions over the versioned ones, and says what it
/// wrote and what it removed, the paths relative to the project.
pub fn write(cartridges: &Cartridges) -> Result<(), String> {
    let project = &cartridges.project;
    let auto = project.auto_patches()?;
    let build = cartridges.directory(RELEASE)?;
    if !has_patches(&build) {
        return Err(format!(
            "{RELEASE} has no patches to write: build it first, {}",
            build.display()
        ));
    }
    let tests = test_maps(cartridges)?;
    for kind in Kind::ALL {
        let (count, bytes, removed) = copy(&auto, &build, kind, &tests)?;
        for path in removed {
            println!(
                "  {}: the game no longer carries it, removing it",
                rm2k_project::relative(&path, project.directory()).display()
            );
        }
        println!(
            "{count} patch(es) in {}, {bytes} B",
            rm2k_project::relative(auto.join(kind.directory()), project.directory()).display()
        );
    }
    Ok(())
}

/// The versioned patches against what every built cartridge decided, as
/// the file keeps it: `stale`, each complaint —empty when they match—;
/// `versioned`, how many there are of each kind; and `own`, what only some
/// cartridge decided and is not versioned, by kind and key, with the
/// cartridges that did.
pub fn compare(cartridges: &Cartridges) -> Result<Value, String> {
    let project = &cartridges.project;
    let auto = project.auto_patches()?;
    let mut builds = Vec::new();
    for name in cartridges.names() {
        let directory = cartridges.directory(&name)?;
        if has_patches(&directory) {
            builds.push(directory);
        }
    }
    if builds.is_empty() {
        return Ok(Value::Null);
    }
    let checked = check(&auto, &builds, &test_maps(cartridges)?, project.directory())?;
    let mut counts = Map::new();
    for kind in Kind::ALL {
        counts.insert(kind.plural().into(), json!(versioned(&auto, kind)?.len()));
    }
    let own: Map<String, Value> = checked
        .own
        .iter()
        .map(|(kind, keys)| {
            let keys: Map<String, Value> = keys
                .iter()
                .map(|(key, which)| (key.to_string(), json!(which)))
                .collect();
            (kind.plural().to_string(), Value::Object(keys))
        })
        .collect();
    Ok(json!({
        "stale": checked.complaints,
        "versioned": counts,
        "own": own,
    }))
}
