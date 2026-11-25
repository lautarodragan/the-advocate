//! The emission as a stage of a converter: what `emit` answers, as the
//! files it makes, by name. The converter calls [`emit`] as a function with
//! the request it built.
//!
//! **It reads nothing but the dump and the request it is given, and writes
//! nothing**: each map's raw data, which the converter leaves in `raw/`, is
//! in the answer too, under [`RAW`].

use crate::answer::{self, Answer, Loss};
use crate::fail::{Bad, Result};
use crate::materials;
use crate::{animation, layer_text, record, request};
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
pub fn emit(data: &Path, mut request: request::Emit) -> Result<Files> {
    // A ChipSet animation cut to fit is a loss, which the converter lists
    // with the cartridge's others.
    let cut = animation::fit_all_by_map(&mut request.maps);
    let mut losses: Vec<Loss> = cut
        .iter()
        .map(|(map, text)| Loss {
            map: *map,
            kind: answer::CHIPSET_ANIMATION_CUT.into(),
            text: text.trim().into(),
        })
        .collect();
    // And an inn's gold window, on a map without room for it in the sprites.
    for map in &request.maps {
        if request.gold_maps.contains(&map.id) && record::arrow_obj(map)? & record::GOLD_ROOM == 0 {
            losses.push(Loss {
                map: map.id,
                kind: answer::INN_NO_GOLD_WINDOW.into(),
                text: format!(
                    "map {}: an inn opens no gold window, which goes in objects past the sprite \
                     bank and in a sprite palette nobody takes, and the map has no room for them",
                    map.id
                ),
            });
        }
    }
    let mut notes: Vec<String> = cut.into_iter().map(|(_, note)| note).collect();
    notes.extend(layer_text::bake_all(&mut request));
    let db = rm2k_snes_battle::db::Db::from_dump(data, true)
        .map_err(|b| Bad::answer(b.message().to_string()))?;
    let emitted = crate::emit::emit(&request, &db)?;
    notes.extend(emitted.notes);
    let answer = Answer {
        notes,
        report: emitted.report,
        frames: emitted.frames,
        losses,
    };
    // Through a JSON value, whose keys serde_json sorts unless the binary
    // that links it keeps their order —the converter does—: the binary's
    // file has the keys sorted, as it always had.
    let answer = serde_json::to_value(&answer).expect("an answer is JSON");
    let mut files = Files::from([
        ("mapdata.inc".to_string(), emitted.text.into_bytes()),
        ("mapdata.json".to_string(), answer.to_string().into_bytes()),
    ]);
    for (name, bytes) in materials::raw_files(&emitted.raw) {
        files.insert(format!("{RAW}{name}"), bytes);
    }
    Ok(files)
}
