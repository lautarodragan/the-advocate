//! The answers as JSON, the way the hashes of `python.rs` were taken.
//!
//! Until 2026-11-23 the `adeleine` executable wrote them, and the Python
//! version before it: the hashes of `python.rs` are of these bytes, so their
//! shape is frozen here. A colour is `[r, g, b]`.

#![allow(dead_code)]

use adeleine::{Color, Colors, Merge, Merged, Reduced};
use serde_json::{json, Value};

/// `{"mapping": [[r, g, b], ...], "merges": [[victim, target, pixels], ...]}`:
/// the mapping in the order of the request's counts.
pub fn merged_answer(merged: &Merged) -> Value {
    json!({
        "mapping": merged.mapping.iter().map(|c| color_value(*c)).collect::<Vec<_>>(),
        "merges": merges_value(&merged.merges),
    })
}

/// `{"palettes": [[[r, g, b], ...], ...]}`, each palette's colours in order,
/// or `{"palettes": null}` if they do not fit.
pub fn packed_answer(palettes: Option<&[Colors]>) -> Value {
    json!({ "palettes": palettes.map(palettes_value) })
}

/// The palettes, each tile's palette and local mapping, and every local
/// colour change as `[palette, victim, target, pixels]`.
pub fn reduced_answer(reduced: &Reduced) -> Value {
    // The keys go in alphabetical order on purpose. Built alone, serde_json
    // sorts them; built in the workspace, another crate switches on
    // `preserve_order` and they come out as written here. In this order the
    // answer is the same bytes either way.
    json!({
        "merges": reduced.merges.iter().map(|m| json!([
            m.palette, color_value(m.victim), color_value(m.target), m.pixels
        ])).collect::<Vec<_>>(),
        "palettes": palettes_value(&reduced.palettes),
        "tiles": reduced.tiles.iter().map(|tile| json!({
            "mapping": tile.mapping.iter().map(|c| color_value(*c)).collect::<Vec<_>>(),
            "palette": tile.palette,
        })).collect::<Vec<_>>(),
    })
}

fn color_value(c: Color) -> Value {
    json!([c[0], c[1], c[2]])
}

fn palettes_value(palettes: &[Colors]) -> Value {
    Value::Array(
        palettes
            .iter()
            .map(|p| Value::Array(p.iter().map(|c| color_value(*c)).collect()))
            .collect(),
    )
}

fn merges_value(merges: &[Merge]) -> Value {
    Value::Array(
        merges
            .iter()
            .map(|m| json!([color_value(m.victim), color_value(m.target), m.pixels]))
            .collect(),
    )
}
