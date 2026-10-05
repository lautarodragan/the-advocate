//! Each decision exactly as it goes to disk.
//!
//! Written by hand and not by a TOML serializer, on purpose: the comments
//! are what makes a file readable to whoever finds it in a diff, and the
//! layout —one merge per line, one color per line— is what makes the diff
//! say which one changed.

use crate::{AnimationDecision, BattlerDecision, MapDecision, Rgb};

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
        format!("mapa = {}", map.id),
        format!("nombre = {}", string(&map.name)),
    ];
    for (layer, merges) in [("fondo", &map.background), ("encima", &map.above)] {
        lines.push(String::new());
        lines.push(format!("[capas.{layer}]"));
        if layer == "fondo" {
            lines.extend([
                "# How many distinct colors the drawing brought and how many".into(),
                "# CGRAM entries the upper layer left it.".into(),
                format!("colores = {}", map.colors),
                format!("presupuesto = {}", map.budget),
            ]);
        }
        lines.extend([
            "# Each merge sends color `de` to color `a`, in 15-bit RGB, and".to_string(),
            "# `pixeles` is how many it moved when it was decided. They go **in".into(),
            "# order**: applying them top to bottom rebuilds the whole mapping.".into(),
        ]);
        if merges.is_empty() {
            lines.push("fusiones = []".into());
            continue;
        }
        lines.push("fusiones = [".into());
        for (victim, dest, pixels) in merges {
            lines.push(format!(
                "  {{ de = {}, a = {}, pixeles = {pixels} }},",
                color(victim),
                color(dest)
            ));
        }
        lines.push("]".into());
    }
    if let Some(p) = &map.panorama {
        lines.extend([
            String::new(),
            "[panorama]".into(),
            "# How the map shows its panorama, as Wally decided from the map and".into(),
            "# the picture: hidden, baked, mode3, flattened, mode1 or black.".into(),
            format!("camino = {}", string(&p.way)),
        ]);
        if let (Some(name), Some(mode), Some(tiles), Some(distinct), Some(colors), Some(kept)) =
            (&p.name, p.mode, p.tiles, p.distinct, p.colors, p.kept)
        {
            lines.extend([
                format!("imagen = {}", string(name)),
                format!("modo = {mode}"),
                "# The distinct 8x8 tiles it had, the mirrored ones as one, and how".into(),
                "# many it is drawn with: the alike ones grouped into one.".into(),
                format!("tiles = {tiles}"),
                format!("distintos = {distinct}"),
                "# The colors it brought and the ones it kept.".into(),
                format!("colores = {colors}"),
                format!("quedan = {kept}"),
                "# Each merge sends color `de` to color `a`, as above.".into(),
            ]);
            if p.merges.is_empty() {
                lines.push("fusiones = []".into());
            } else {
                lines.push("fusiones = [".into());
                for (victim, dest, pixels) in &p.merges {
                    lines.push(format!(
                        "  {{ de = {}, a = {}, pixeles = {pixels} }},",
                        color(victim),
                        color(dest)
                    ));
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
        format!("animacion = {}", animation.number),
        format!("nombre = {}", string(&animation.name)),
        format!("hoja = {}", string(&animation.sheet)),
        String::new(),
        "# What was decided: the rectangle, in console pixels, the whole".into(),
        format!(
            "# animation is shrunk to so it fits in the {} x {} box. It is what",
            animation.side, animation.side
        ),
        "# phase 2 will read instead of computing it again.".into(),
        format!("tamano = [{box_w}, {box_h}]"),
        String::new(),
        "# What it came from: the union of all the cells of all its frames in".into(),
        "# RM2k pixels, and how many frames there are. It is not decided, it is".into(),
        "# measured, and it is here so the diff says why the size changed.".into(),
        format!("original = [{width}, {height}]"),
        format!("cuadros = {}", animation.frames),
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
        format!("imagen = {}", string(&battler.image)),
        format!("tono = {}", battler.hue),
        String::new(),
        "# What it came from, already shrunk to 80%: the size in scene pixels".into(),
        "# and how many distinct 15-bit colors it brought. It is not decided, it".into(),
        "# is measured.".into(),
        format!("tamano = [{}, {}]", battler.width, battler.height),
        format!("colores = {}", battler.colors),
        String::new(),
        "# What remained, in palette order: index 1 is the first one.".into(),
        "paleta = [".into(),
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
        format!("fusiones = {}", battler.merges),
    ]);
    lines.join("\n") + "\n"
}
