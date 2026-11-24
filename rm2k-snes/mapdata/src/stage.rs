//! The emission as a stage of a converter: what `emit` answers, as the
//! files the binary writes, by name. The converter calls [`emit`] as a
//! function, and the binary is a `main` over [`emit_of`] that reads the
//! request and writes the files.
//!
//! **It reads nothing but the dump and the request it is given, and writes
//! nothing**: each map's raw data, which the binary leaves in `--raw`, is in
//! the answer too, under [`RAW`].

use crate::fail::{Bad, Result};
use crate::materials;
use crate::{animation, layer_text, record, request};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::Path;

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// Where each map's raw data goes among the files: `raw/<map>.<class>.bin`,
/// what the console decompresses of the map, uncompressed —see
/// [`materials::raw_files`]—. The rest are `mapdata.inc` and
/// `mapdata.json`.
pub const RAW: &str = "raw/";

/// `emit`: the whole `.inc` of a cartridge, from what every domain of the
/// conversion answered —see `Emit` in `request.rs`—, with the database read
/// from the dump in `data`.
pub fn emit(data: &Path, request: &Value) -> Result<Files> {
    let request = request::Emit::deserialize(request)
        .map_err(|e| Bad::answer(format!("the request: {e}")))?;
    emit_of(data, request)
}

/// [`emit`], of a request already read.
pub fn emit_of(data: &Path, mut request: request::Emit) -> Result<Files> {
    // A ChipSet animation cut to fit is a loss, which the converter lists
    // with the cartridge's others.
    let cut = animation::fit_all_by_map(&mut request.maps);
    let mut losses: Vec<Value> = cut
        .iter()
        .map(
            |(map, text)| json!({"map": map, "kind": "chipset-animation-cut", "text": text.trim()}),
        )
        .collect();
    // And an inn's gold window, on a map without room for it in the sprites.
    for map in &request.maps {
        if request.gold_maps.contains(&map.id) && record::arrow_obj(map)? & record::GOLD_ROOM == 0 {
            losses.push(json!({
                "map": map.id,
                "kind": "inn-no-gold-window",
                "text": format!(
                    "map {}: an inn opens no gold window, which goes in objects past the sprite \
                     bank and in a sprite palette nobody takes, and the map has no room for them",
                    map.id
                ),
            }));
        }
    }
    let mut notes: Vec<String> = cut.into_iter().map(|(_, note)| note).collect();
    notes.extend(layer_text::bake_all(&mut request));
    let db = rm2k_snes_battle::db::Db::from_dump(data, true)
        .map_err(|b| Bad::answer(b.message().to_string()))?;
    let emitted = crate::emit::emit(&request, &db)?;
    notes.extend(emitted.notes);
    let answer = json!({"notes": notes, "report": emitted.report, "frames": emitted.frames, "losses": losses});
    let mut files = Files::from([
        ("mapdata.inc".to_string(), emitted.text.into_bytes()),
        ("mapdata.json".to_string(), answer.to_string().into_bytes()),
    ]);
    for (name, bytes) in materials::raw_files(&emitted.raw) {
        files.insert(format!("{RAW}{name}"), bytes);
    }
    Ok(files)
}
