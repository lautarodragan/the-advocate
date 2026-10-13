//! Each decision exactly as it goes to disk.
//!
//! Written by hand and not by a TOML serializer, on purpose: the comments
//! are what makes a file readable to whoever finds it in a diff, and the
//! layout —one merge per line, one color per line— is what makes the diff
//! say which one changed.

use crate::{AnimationDecision, BattlerDecision, MapDecision, Rgb, WindowDecision};

pub(crate) fn color(c: &Rgb) -> String {
    format!("[{}, {}, {}]", c[0], c[1], c[2])
}

/// A TOML basic string. Only the backslash and the quote are escaped: the
/// names come from the game's database, and none has a control character.
fn string(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

/// A map's file.
pub fn map_text(map: &MapDecision) -> String {
    let mut lines = vec![
        format!(
            "# The artistic decisions of map {}: what is lost when taking it to the",
            map.id
        ),
        "# SNES. The converter writes it and `rm2k-snes-patches` copies it here".into(),
        "# from the playable ROM's build, which is what has to be run when a".into(),
        "# change moves it; `rm2k-snes-patches --check` —and the suite— fail if".into(),
        "# it is stale.".into(),
        String::new(),
        format!("map = {}", map.id),
        format!("name = {}", string(&map.name)),
    ];
    for (layer, merges) in [("lower", &map.background), ("upper", &map.above)] {
        lines.push(String::new());
        lines.push(format!("[layers.{layer}]"));
        if layer == "lower" {
            lines.extend([
                "# How many distinct colors the drawing brought and how many".into(),
                "# CGRAM entries the upper layer left it.".into(),
                format!("colors = {}", map.colors),
                format!("budget = {}", map.budget),
            ]);
        }
        if merges.iter().any(|merge| merge.parts().0.is_some()) {
            lines.extend([
                "# Each change sends color `from` to color `to`, in 15-bit RGB, and".to_string(),
                "# `pixels` is how many it moved. `palette` makes it local to that".into(),
                "# tile palette, so one source may have another target elsewhere.".into(),
            ]);
        } else {
            lines.extend([
                "# Each merge sends color `from` to color `to`, in 15-bit RGB, and".to_string(),
                "# `pixels` is how many it moved when it was decided. They go **in".into(),
                "# order**: applying them top to bottom rebuilds the whole mapping.".into(),
            ]);
        }
        if merges.is_empty() {
            lines.push("merges = []".into());
            continue;
        }
        lines.push("merges = [".into());
        for merge in merges {
            let (palette, victim, dest, pixels) = merge.parts();
            let local = palette.map_or(String::new(), |p| format!("palette = {p}, "));
            lines.push(format!("  {{ {local}from = {}, to = {}, pixels = {pixels} }},",
                color(victim), color(dest)));
        }
        lines.push("]".into());
    }
    if let Some(p) = &map.panorama {
        lines.extend([
            String::new(),
            "[panorama]".into(),
            "# How the map shows its panorama, as Wally decided from the map and".into(),
            "# the picture: hidden, baked, mode3, flattened, mode1 or black.".into(),
            format!("way = {}", string(&p.way)),
        ]);
        if let (Some(name), Some(mode), Some(tiles), Some(distinct), Some(colors), Some(kept)) =
            (&p.name, p.mode, p.tiles, p.distinct, p.colors, p.kept)
        {
            lines.extend([
                format!("image = {}", string(name)),
                format!("mode = {mode}"),
                "# The distinct 8x8 tiles it had, the mirrored ones as one, and how".into(),
                "# many it is drawn with: the alike ones grouped into one.".into(),
                format!("tiles = {tiles}"),
                format!("distinct = {distinct}"),
                "# The colors it brought and the ones it kept.".into(),
                format!("colors = {colors}"),
                format!("kept = {kept}"),
                if p.merges.iter().any(|merge| merge.parts().0.is_some()) {
                    "# Each palette-local colour change is written as above.".into()
                } else {
                    "# Each merge sends color `from` to color `to`, as above.".into()
                },
            ]);
            if p.merges.is_empty() {
                lines.push("merges = []".into());
            } else {
                lines.push("merges = [".into());
                for merge in &p.merges {
                    let (palette, victim, dest, pixels) = merge.parts();
                    let local = palette.map_or(String::new(), |n| format!("palette = {n}, "));
                    lines.push(format!("  {{ {local}from = {}, to = {}, pixels = {pixels} }},",
                        color(victim), color(dest)));
                }
                lines.push("]".into());
            }
        }
    }
    lines.join("\n") + "\n"
}

/// An animation's file.
pub fn animation_text(animation: &AnimationDecision) -> String {
    let [width, height] = animation.original;
    let [box_w, box_h] = animation.size;
    [
        format!(
            "# The artistic decision of animation {}: **at what size it is drawn**",
            animation.number
        ),
        "# on the console. The converter writes it and `rm2k-snes-patches` copies".into(),
        "# it here from the playable ROM's build, which is what has to be run when".into(),
        "# a change moves it; `rm2k-snes-patches --check` —and the suite— fail if".into(),
        "# it is stale.".into(),
        String::new(),
        format!("animation = {}", animation.number),
        format!("name = {}", string(&animation.name)),
        format!("sheet = {}", string(&animation.sheet)),
        String::new(),
        "# What was decided: the rectangle, in console pixels, the whole".into(),
        format!(
            "# animation is shrunk to so it fits in the {} x {} box. It is what",
            animation.side, animation.side
        ),
        "# phase 2 will read instead of computing it again.".into(),
        format!("size = [{box_w}, {box_h}]"),
        String::new(),
        "# What it came from: the union of all the cells of all its frames in".into(),
        "# RM2k pixels, and how many frames there are. It is not decided, it is".into(),
        "# measured, and it is here so the diff says why the size changed.".into(),
        format!("original = [{width}, {height}]"),
        format!("frames = {}", animation.frames),
        String::new(),
    ]
    .join("\n")
}

/// A battler's file.
pub fn battler_text(battler: &BattlerDecision) -> String {
    let mut lines = vec![
        format!(
            "# The artistic decision of battler {}: **which colors are lost** when",
            battler.key
        ),
        "# taking it to fifteen, which is what the battle scene leaves each one.".into(),
        "# The converter writes it and `rm2k-snes-patches` copies it here from the".into(),
        "# playable ROM's build, which is what has to be run when a change moves".into(),
        "# it; `rm2k-snes-patches --check` —and the suite— fail if it is stale.".into(),
        String::new(),
        format!("battler = {}", string(&battler.key)),
        format!("image = {}", string(&battler.image)),
        format!("hue = {}", battler.hue),
        String::new(),
        "# What it came from, already shrunk to 80%: the size in scene pixels".into(),
        "# and how many distinct 15-bit colors it brought. It is not decided, it".into(),
        "# is measured.".into(),
        format!("size = [{}, {}]", battler.width, battler.height),
        format!("colors = {}", battler.colors),
        String::new(),
        "# What remained, in palette order: index 1 is the first one.".into(),
        "palette = [".into(),
    ];
    for c in &battler.palette {
        lines.push(format!("  {},", color(c)));
    }
    // **The minimal form, on purpose**: the palette that remained and not
    // the list of merges that led to it. An already shrunk battler carries
    // hundreds of colors —the intermediate grays a resampling filter leaves
    // on every edge— and the list measured 179 KB for eleven battlers; what
    // is seen is which fifteen remain, and that is what the diff has to
    // show. The day the converter wants to read this instead of deciding,
    // the list comes back.
    lines.extend([
        "]".to_string(),
        String::new(),
        "# How many merges it took to get there, with".into(),
        "# `adeleine.merge_least_visible`: each one sends the least noticeable".into(),
        "# color to its nearest neighbor.".into(),
        format!("merges = {}", battler.merges),
    ]);
    lines.join("\n") + "\n"
}

/// A message window's file: the colours its System lost.
pub fn window_text(window: &WindowDecision) -> String {
    let mut lines = vec![
        format!(
            "# The artistic decision of System {}: **which colors the message",
            window.system
        ),
        "# window loses** —its background, its frame, its arrow, its cursor, the".into(),
        "# text and its shadow— to fit in one palette of fifteen. Only a System".into(),
        "# that does not fit has one. The converter writes it and".into(),
        "# `rm2k-snes-patches` copies it here from the playable ROM's build,".into(),
        "# which is what has to be run when a change moves it;".into(),
        "# `rm2k-snes-patches --check` —and the suite— fail if it is stale.".into(),
        String::new(),
        format!("system = {}", string(&window.system)),
        String::new(),
        "# How many distinct 15-bit colors it brought and how many were kept.".into(),
        format!("colors = {}", window.colors),
        format!("kept = {}", window.kept),
        String::new(),
        "# Each merge sends color `from` to color `to`, with".into(),
        "# `adeleine.merge_least_visible`, and `pixels` is how much it weighed:".into(),
        "# the pixels it covers, and for the text and its shadow a whole row of".into(),
        "# every line. They go **in order**: applying them top to bottom".into(),
        "# rebuilds the whole mapping.".into(),
        "merges = [".into(),
    ];
    for merge in &window.merges {
        let (_, victim, dest, pixels) = merge.parts();
        lines.push(format!(
            "  {{ from = {}, to = {}, pixels = {pixels} }},",
            color(victim),
            color(dest)
        ));
    }
    lines.push("]".into());
    lines.join("\n") + "\n"
}
