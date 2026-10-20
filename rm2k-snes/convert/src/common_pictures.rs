//! The small pictures of the common events compiled without a map: one
//! table the whole cartridge shares, by sets.
//!
//! A small picture belongs to a map —its tiles to the map's sprite bank,
//! its entry to the map's table—, so a body compiled once, without a map,
//! could name none: Zounds' pick-axe, notebook and notes, automatic common
//! events on the switch a switch item turns on, showed nothing. Here the
//! pictures each set shows —see `commons::picture_sets` in the event
//! compiler: a common event with every body it calls— are cut once, as a
//! map's are, but from tile 0 and palette 0: the cartridge carries their
//! tiles once, and the console uploads a set's beside the loaded map's
//! bank when one of its pictures is shown, if it fits there. Which maps it
//! fits on is the emission's to say, with the map's bank laid out: see
//! `picture_common_section` in rm2k-snes-mapdata, and
//! `runtime/picture_common.s`.
//!
//! Each picture gets an entry of the cartridge's common table, named by
//! the bytecode with bit 7 set —the maps' own tables hold far fewer than
//! 128—, and a slot **from the top**: the map's own take theirs from 0, so
//! a set's only meets them on a map that shows sixteen numbers between
//! both. The order of the slots within a set is RM2k's, the highest number
//! in front.

use crate::fail::Result;
use crate::game::Game;
use crate::pictures::{self, SLOTS};
use serde_json::{json, Value};

/// The bit of an image that names an entry of the common table, and how
/// many entries it can name: $FF is the runtime's `PIC_NONE`.
const COMMON_BIT: usize = 0x80;
const COMMON_MAX: usize = 0x7F;

/// What the converter does with the sets: the event compiler's entries and
/// sets, and what the emission writes.
#[derive(Debug, Default)]
pub struct CommonPictures {
    /// For the compiler's `common_pictures`, after the big ones: each picture
    /// with `"plane": "common"`, its image, its slot and its set.
    pub entries: Vec<Value>,
    /// For the compiler's `common_sets`: each set kept, by its index,
    /// `{"parallel", "commons"}`.
    pub sets: Vec<Value>,
    /// For the emission's `common_pictures`: each set's tiles, how many it
    /// reserves, its palettes and its pictures, as a map's.
    pub emit: Vec<Value>,
}

/// The sets of the scan's `common_sets`, cut as a map's pictures are. A set
/// whose pictures are all big —those go in the background layer, see
/// `common_bigs`— or missing is no set.
///
/// **The fewest pictures first**: the table names 127, and a set that would
/// pass them is left out, as the log says. Zounds' pick-axe is 104 of them
/// —a digit is a picture under each of its numbers—, and first by number it
/// took the room the notebook needed.
pub fn sets(game: &Game, scan: &Value) -> Result<CommonPictures> {
    let mut cuts = Vec::new();
    for set in scan["common_sets"].as_array().into_iter().flatten() {
        let commons: Vec<i64> = set["commons"]
            .as_array()
            .map(|a| a.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default();
        let names = commons
            .iter()
            .map(i64::to_string)
            .collect::<Vec<_>>()
            .join(", ");
        let whose = format!("common events {names}");
        let keys = set["pictures"].as_array().cloned().unwrap_or_default();
        let tinted: Vec<i64> = set["tinted"]
            .as_array()
            .map(|a| a.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default();
        if let Some(cut) = pictures::for_map(&game.game_dir, &keys, &tinted, &whose, &game.cropped)?
        {
            cuts.push((whose, set["parallel"].clone(), commons, cut));
        }
    }
    cuts.sort_by_key(|(_, _, _, cut)| cut.table.len());
    let mut out = CommonPictures::default();
    for (whose, parallel, commons, cut) in cuts {
        let first = out.entries.len();
        if first + cut.table.len() > COMMON_MAX {
            println!(
                "  {whose}: WARNING, their {} small pictures aren't shown: with the ones before \
                 they pass the {COMMON_MAX} the common table names",
                cut.table.len()
            );
            continue;
        }
        let k = out.sets.len();
        // The slots from the top: the set's `used` ones end at the last.
        let used = cut
            .table
            .iter()
            .filter_map(|e| e["slot"].as_u64())
            .max()
            .map_or(0, |m| m as usize + 1);
        for (i, entry) in cut.table.iter().enumerate() {
            let mut entry = entry.clone();
            let slot = entry["slot"].as_u64().unwrap_or(0) as usize + SLOTS - used;
            entry["plane"] = json!("common");
            entry["image"] = json!(COMMON_BIT | (first + i));
            entry["slot"] = json!(slot);
            entry["set"] = json!(k);
            out.entries.push(entry);
        }
        println!(
            "  {whose}: their small pictures {}, {} objects in {} tiles and {} palette(s), go up \
             when shown",
            crate::text::repr(cut.asked["name"].as_str().unwrap_or("")),
            cut.asked["objects"],
            cut.asked["tiles"],
            cut.asked["palettes"]
        );
        out.sets
            .push(json!({"parallel": parallel, "commons": commons}));
        out.emit.push(json!({
            "name": whose,
            "tiles": cut.asked["tiles"],
            "cells": cut.asked["cells"],
            "palettes": cut.asked["palettes"],
            "images": cut.images,
        }));
    }
    Ok(out)
}
