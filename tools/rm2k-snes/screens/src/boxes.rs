//! Every message box of a game, reflowed for the console's window: the
//! table the event compiler reads its boxes through.
//!
//! All the boxes of all the maps and of the common events, whether or not
//! a cartridge carries them: it is cheaper than knowing which it reads.
//! The troops' are not: the battle's window has a different width.

use crate::fail::{Bad, Result};
use ditto::dump::{read_map, Dump};
use ditto::schema::{CommonEvent, EventCommand};
use rm2k_snes_text::refit::refit;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::path::PathBuf;

/// `ShowMessage` and `ShowMessage_2`, the box's first line and the rest.
const SHOW_MESSAGE: i32 = 10110;
const SHOW_MESSAGE_2: i32 = 20110;

fn answer(e: ditto::lcf::Error) -> Bad {
    Bad::answer(e.0)
}

/// The boxes of a command list, each as its lines, in order.
fn boxes_of(commands: &[EventCommand], out: &mut Vec<Vec<String>>) {
    let mut i = 0;
    while i < commands.len() {
        if commands[i].code.to_i32() != SHOW_MESSAGE {
            i += 1;
            continue;
        }
        let mut j = i + 1;
        while j < commands.len() && commands[j].code.to_i32() == SHOW_MESSAGE_2 {
            j += 1;
        }
        out.push(commands[i..j].iter().map(|c| c.string.clone()).collect());
        i = j;
    }
}

/// Each of `boxes` reflowed for a window of `columns` by `rows`, as
/// `{"to": boxes, "speaker": whether its first line names who speaks}`: a
/// box that fits comes back as itself. It is for whoever checks the reflow
/// over a whole game.
pub fn refit_each(boxes: &[Vec<String>], columns: usize, rows: usize) -> Value {
    Value::from(
        boxes
            .iter()
            .map(|lines| {
                json!({
                    "to": refit(lines, columns, rows),
                    "speaker": lines.len() > 1 && rm2k_snes_text::refit::is_speaker(&lines[0]),
                })
            })
            .collect::<Vec<_>>(),
    )
}

/// The boxes that change, as `{"from": lines, "to": boxes}`, in the order
/// they are first found: the dump's maps by file name, then `map_files`
/// —the project's, which override the dump's: both are read, which only
/// adds boxes nobody asks for—, then the common events.
pub fn table(data: &std::path::Path, map_files: &[PathBuf], columns: usize, rows: usize) -> Result<Value> {
    let dump = Dump::open(data).map_err(answer)?;
    let mut paths = dump.map_files().map_err(answer)?;
    paths.sort_by(|a, b| a.file_name().cmp(&b.file_name()));
    paths.extend(map_files.iter().cloned());
    let mut found = Vec::new();
    for path in &paths {
        let map = read_map(path).map_err(answer)?;
        for event in &map.events {
            for page in &event.pages {
                boxes_of(&page.event_commands, &mut found);
            }
        }
    }
    let common: Vec<CommonEvent> = dump.section("commonevents").map_err(answer)?;
    for c in &common {
        boxes_of(&c.event_commands, &mut found);
    }
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for lines in found {
        if !seen.insert(lines.clone()) {
            continue;
        }
        let frames = refit(&lines, columns, rows);
        if frames != [lines.clone()] {
            out.push(json!({"from": lines, "to": frames}));
        }
    }
    Ok(Value::from(out))
}
