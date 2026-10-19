//! The patches: what a converter **decides to lose** when taking an RPG Maker
//! 2000 game to the SNES.
//!
//! Going from RPG Maker to the console there are two kinds of transformation
//! and only one is a patch. Baking opaque events, reusing mirrored tiles or
//! separating a character from the hero require no judgment and do not change
//! what is seen: they are optimizations and are not here. Merging two colors
//! because CGRAM does not have room for both, on the other hand, **loses
//! something and someone chose what**, and that is a patch.
//!
//! Until they were written down those decisions were made silently and left no
//! trace: if a change made a map lose two more colors, the only way to find
//! out was to look at the ROM. Here they come out written, they are
//! versioned, and a check fails if what is committed does not match. The
//! point is that **the diff
//! warns**: it is what golden images do with the pixels, for the decisions.
//!
//! What is written is **the desired state and not a report**, because the
//! next step —already decided— is for the converter to read these files
//! instead of deciding again. That is why each merge is written as "this
//! color goes to this other one" and in the order they were applied:
//! replaying the list rebuilds the whole mapping, which is exactly what
//! Adeleine's least-visible merge returns. And that is why an animation
//! writes the rectangle it is drawn at and not how much it was shrunk: the
//! percentage is for reading and the rectangle is for applying.
//!
//! # The three places
//!
//! * **The converter** decides, and hands the decisions of one build to this
//!   in a request —`rm2k-snes-patches --request decisions.json <build>`, see
//!   [`Request`]—: this writes them as TOML in `<build>/patches/auto/`, next
//!   to the ROM. Which situation each one was asked for by —a map of the
//!   game, a map or a page that only exists for a test suite— the converter
//!   writes itself, in `<build>/patches/uses.json` ([`USES_FILE`]), and this
//!   only reads it.
//! * **`rm2k-snes-patches <build>`** copies what the playable ROM decided
//!   into the project's automatic patches, which is what goes to version
//!   control, and removes what it no longer carries.
//! * **`rm2k-snes-patches --check`** compares what is versioned against what
//!   **every** built cartridge decided, and says **which decision changed**,
//!   not that a file differs: see [`check`].
//!
//! # The key
//!
//! One file per game situation: `maps/<id>.toml` for the layers of a map,
//! with one section per layer, `animations/<n>.toml` for the battle
//! animations and `battlers/<key>.toml` for the battlers. **The map id is the
//! game's and not the cartridge's**: it does not move when the ROM's list of
//! maps changes, nor when the converter's internal order changes, nor when
//! Adeleine's algorithm changes. Colors are written by their value —15-bit
//! RGB, which is the console's real depth— and not by their index in any
//! palette, for the same reason: the index shifts with anything and the value
//! identifies the color forever.
//!
//! And the cartridge **is not part of the key**: *the versioned decision is
//! always the playable ROM's*, `release`. What is versioned is what **the
//! game** lost, which is the only thing that matters to someone looking at
//! the repository; a test cartridge reuses it when it applies, and when it
//! does not apply it decides on its own and that is not versioned.
//!
//! What happens **when the playable ROM's decision cannot be applied** in a
//! test cartridge is, then, an expected path and not an exception: that
//! cartridge decides on its own, writes what it decided next to its ROM and
//! `--check` asks nothing of it. In this kind of decision, moreover, the
//! question never even comes up: the layer merges depend on the map and its
//! ChipSet and nothing else. That this is true **is not assumed**: `--check`
//! compares against what is versioned **every** cartridge that carries a
//! versioned map, so if any decided differently, the check says so with its
//! name on it.
//!
//! # The battle animations
//!
//! The second kind: **the size each animation is drawn at**. One that does
//! not fit in the console's box is shrunk whole, keeping its proportions, and
//! that shows. Its key is **the RM2k animation number**, and it is enough
//! alone because the size comes from the box the animation takes in RM2k and
//! the console's box, which is **a single one for the whole ROM**. Neither the
//! cartridge nor the map is part of it, and as with the layers it is not
//! assumed: `--check` compares every cartridge that shows a versioned
//! animation.
//!
//! What **does** depend on the map is something else and is not here:
//! whether the animation is drawn at all, when the map already took the eight
//! sprite palettes. It is another decision —and another kind—, and putting it
//! here would mix the cartridge with the game again.
//!
//! # The battlers
//!
//! The third: since the battle scene is composited on the console, each
//! battler has **fifteen colors and the transparent one**, and which ones are
//! lost is a decision. What is written is the palette that remained and how
//! many merges were needed, with the battler's key: its image and its hue. It
//! looks at neither the troop nor the cartridge: the reduction is of the
//! already shrunk drawing and nothing else.
//!
//! What **is not here yet**: the character palettes —which do depend on the
//! cartridge, because the palette split looks at the whole map—, the voices
//! dropped from a MIDI, the trimmed samples, the fifteen colors each
//! animation is reduced to, and translucent decorations.
//!
//! The tests write and check a small game made of requests, in
//! `tests/game/`, and compare against what the Python that did this until
//! 2026-09-30 answered for it: they need no game.

mod check;
mod text;

pub use check::{check, versioned, Checked, Own};
pub use text::{animation_text, battler_text, map_text, window_text};

use serde::Deserialize;
use std::collections::BTreeSet;
use std::fmt;
use std::path::{Path, PathBuf};

/// Where each cartridge leaves its patches, relative to its build directory.
/// It is the shape of the build, which imitates the project's patches; not
/// where those are.
pub const IN_BUILD: &str = "patches/auto";

/// Who asked for each of the cartridge's patches, next to its patches and
/// **not versioned**: the converter writes it, and [`only_for_tests`] reads
/// it. `{kind key: {key: [origin, ...]}}`, where an origin is a map id or
/// `"case"`, a test page.
pub const USES_FILE: &str = "patches/uses.json";

/// The origin a test page is written as in [`USES_FILE`].
const TEST_PAGE: &str = "case";

/// The cartridge whose decisions are versioned: the playable ROM.
pub const PLAYABLE: &str = "release";

/// The kinds of decision that are written, each with its directory, the key
/// that identifies it —which is always something **of the game**— and how
/// what changed is told. Adding a kind is adding a variant here and its text:
/// the check, the copy and the messages come from this.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Kind {
    Map,
    Animation,
    Battler,
    Window,
}

impl Kind {
    pub const ALL: [Kind; 4] = [Kind::Map, Kind::Animation, Kind::Battler, Kind::Window];

    /// How a count of them is printed.
    pub fn plural(self) -> &'static str {
        match self {
            Kind::Map => "map(s)",
            Kind::Animation => "animation(s)",
            Kind::Battler => "battler(s)",
            Kind::Window => "window(s)",
        }
    }

    /// How one of them is named in a message.
    pub fn article(self) -> &'static str {
        match self {
            Kind::Map => "map",
            Kind::Animation => "animation",
            Kind::Battler => "battler",
            Kind::Window => "window",
        }
    }

    /// Its folder, among the versioned ones and in a build's `IN_BUILD`.
    pub fn directory(self) -> &'static str {
        match self {
            Kind::Map => "maps",
            Kind::Animation => "animations",
            Kind::Battler => "battlers",
            Kind::Window => "windows",
        }
    }

    /// Where a cartridge leaves them, relative to its build directory.
    pub fn in_build(self) -> String {
        format!("{IN_BUILD}/{}", self.directory())
    }

    /// The field inside each file that holds its key, and the kind's name in
    /// [`USES_FILE`].
    pub fn key(self) -> &'static str {
        match self {
            Kind::Map => "map",
            Kind::Animation => "animation",
            Kind::Battler => "battler",
            Kind::Window => "system",
        }
    }

    /// The file one of them is written to, inside its folder.
    pub fn file_name(self, key: &Key) -> String {
        match key {
            Key::Number(n) => format!("{n:04}.toml"),
            // RM2k battlers can have spaces —`sentry drone`—, and a file with
            // spaces in a repository is a nuisance in every command that
            // names it.
            Key::Text(t) => format!("{}.toml", t.replace(' ', "_")),
        }
    }
}

/// What identifies a situation of the game: a map id or an animation number,
/// or a battler's name. Numbers sort as numbers and names as text; one kind
/// never mixes the two.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Key {
    Number(i64),
    Text(String),
}

impl fmt::Display for Key {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            Key::Number(n) => write!(f, "{n}"),
            Key::Text(t) => f.write_str(t),
        }
    }
}

/// A color, in 15-bit RGB: each component 0 to 31.
pub type Rgb = [i64; 3];

/// One colour change. A global merge is `[from, to, pixels]`; a tile-palette
/// reduction is `[palette, from, to, pixels]`, because one source colour may
/// go to different targets in different palettes.
#[derive(Clone, Debug, Deserialize)]
#[serde(untagged)]
pub enum Merge {
    Global((Rgb, Rgb, i64)),
    Palette((i64, Rgb, Rgb, i64)),
}

impl Merge {
    pub fn parts(&self) -> (Option<i64>, &Rgb, &Rgb, i64) {
        match self {
            Merge::Global((from, to, pixels)) => (None, from, to, *pixels),
            Merge::Palette((palette, from, to, pixels)) => (Some(*palette), from, to, *pixels),
        }
    }
}

/// What the converter decided for one build: the request of
/// `--request`, as JSON.
#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    #[serde(default)]
    pub maps: Vec<MapDecision>,
    #[serde(default)]
    pub animations: Vec<AnimationDecision>,
    #[serde(default)]
    pub battlers: Vec<BattlerDecision>,
    #[serde(default)]
    pub windows: Vec<WindowDecision>,
}

/// The colours the message window lost: what a System that does not fit in
/// one palette was reduced to. Only a System that did not fit has one.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WindowDecision {
    /// The System's name in the database.
    pub system: String,
    /// How many distinct colours the window, its arrow, its cursor and its
    /// text brought, and how many were kept.
    pub colors: i64,
    pub kept: i64,
    /// Adeleine's merges, in the order they were applied.
    pub merges: Vec<Merge>,
}

/// The colors a map's two layers lost.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MapDecision {
    /// The game's map id.
    pub id: i64,
    pub name: String,
    /// How many distinct colors the drawing brought.
    pub colors: i64,
    /// How many CGRAM entries the upper layer left the background.
    pub budget: i64,
    /// The background's global or palette-local colour changes.
    #[serde(default)]
    pub background: Vec<Merge>,
    /// The upper layer's colour changes.
    #[serde(default)]
    pub above: Vec<Merge>,
    /// How it shows its panorama, if it has one, and what that lost.
    #[serde(default)]
    pub panorama: Option<PanoramaDecision>,
}

/// A map's panorama: the way Wally chose and, if it got a layer of its
/// own, the tiles it was grouped into and the colours it merged.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PanoramaDecision {
    pub way: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub mode: Option<i64>,
    /// How many tiles it was drawn with, and how many distinct ones the
    /// picture had, the mirrored ones as one.
    #[serde(default)]
    pub tiles: Option<i64>,
    #[serde(default)]
    pub distinct: Option<i64>,
    /// How many colours it brought and how many it kept.
    #[serde(default)]
    pub colors: Option<i64>,
    #[serde(default)]
    pub kept: Option<i64>,
    #[serde(default)]
    pub merges: Vec<Merge>,
}

/// The size a battle animation is drawn at.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnimationDecision {
    /// The RM2k animation number.
    pub number: i64,
    /// Its name and its sheet in the database, which nobody looks at to
    /// draw: they are there so the diff says which one it is.
    pub name: String,
    pub sheet: String,
    /// The side of the console's square box.
    pub side: i64,
    /// What was decided: the rectangle, in console pixels.
    pub size: [i64; 2],
    /// What it came from: the union of all the cells of all its frames, in
    /// RM2k pixels.
    pub original: [i64; 2],
    pub frames: i64,
}

/// The fifteen colors a battler kept.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BattlerDecision {
    /// Its image and its hue, which is what tells it from another with the
    /// same image.
    pub key: String,
    pub image: String,
    pub hue: i64,
    /// Already shrunk, in scene pixels.
    pub width: i64,
    pub height: i64,
    /// How many distinct 15-bit colors it brought.
    pub colors: i64,
    /// What remained, in palette order.
    pub palette: Vec<Rgb>,
    /// How many merges it took to get there.
    pub merges: usize,
}

/// What [`write`] left of one kind: how many files and how many bytes.
#[derive(Debug, PartialEq, Eq)]
pub struct Written {
    pub kind: Kind,
    pub files: usize,
    pub bytes: usize,
}

fn io(path: &Path) -> impl Fn(std::io::Error) -> String + '_ {
    move |e| format!("{}: {e}", path.display())
}

/// A kind's folder in the build, created and without the previous run's
/// `.toml`s. Without this, a cartridge that stops carrying a map or an
/// animation still had its old patch next to the ROM, and the check counted
/// it as converted.
fn clear(folder: &Path) -> Result<(), String> {
    std::fs::create_dir_all(folder).map_err(io(folder))?;
    for name in toml_files(folder)? {
        let path = folder.join(name);
        std::fs::remove_file(&path).map_err(io(&path))?;
    }
    Ok(())
}

/// The `.toml` files in `folder`, sorted by name.
pub(crate) fn toml_files(folder: &Path) -> Result<Vec<String>, String> {
    let mut names = Vec::new();
    for entry in std::fs::read_dir(folder).map_err(io(folder))? {
        let name = entry.map_err(io(folder))?.file_name();
        let name = name
            .into_string()
            .map_err(|n| format!("{}: {n:?} is not UTF-8", folder.display()))?;
        if name.ends_with(".toml") {
            names.push(name);
        }
    }
    names.sort();
    Ok(names)
}

/// The patches of one build, from what the converter decided, in
/// `<build>/patches/auto/`: every kind's folder is emptied first, so what is
/// left is exactly this request.
pub fn write(build: &Path, request: &Request) -> Result<Vec<Written>, String> {
    let texts: [Vec<(String, String)>; 4] = [
        request
            .maps
            .iter()
            .map(|m| (Kind::Map.file_name(&Key::Number(m.id)), map_text(m)))
            .collect(),
        request
            .animations
            .iter()
            .map(|a| {
                (
                    Kind::Animation.file_name(&Key::Number(a.number)),
                    animation_text(a),
                )
            })
            .collect(),
        request
            .battlers
            .iter()
            .map(|b| {
                (
                    Kind::Battler.file_name(&Key::Text(b.key.clone())),
                    battler_text(b),
                )
            })
            .collect(),
        request
            .windows
            .iter()
            .map(|w| {
                (
                    Kind::Window.file_name(&Key::Text(w.system.clone())),
                    window_text(w),
                )
            })
            .collect(),
    ];
    let mut out = Vec::new();
    for (kind, files) in Kind::ALL.into_iter().zip(texts) {
        let folder = build.join(kind.in_build());
        clear(&folder)?;
        let mut bytes = 0;
        for (name, content) in &files {
            let path = folder.join(name);
            std::fs::write(&path, content).map_err(io(&path))?;
            bytes += content.len();
        }
        out.push(Written {
            kind,
            files: files.len(),
            bytes,
        });
    }
    Ok(out)
}

/// Whether a build directory has any patches inside.
pub fn has_patches(build: &Path) -> bool {
    Kind::ALL.iter().any(|k| build.join(k.in_build()).is_dir())
}

/// Whether `which` is in the cartridge built in `build` only for a test
/// suite: a test map, or an animation or a battler that only the test maps
/// and the test pages ask for. `tests` are the project's test maps.
///
/// Without [`USES_FILE`], or without a known origin, **no**: doubt goes to
/// the side of asking for the patch, which is the complaint that shows.
pub fn only_for_tests(
    build: &Path,
    kind: Kind,
    which: &Key,
    tests: &BTreeSet<i64>,
) -> Result<bool, String> {
    if kind == Kind::Map {
        return Ok(matches!(which, Key::Number(n) if tests.contains(n)));
    }
    let path = build.join(USES_FILE);
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(_) => return Ok(false),
    };
    let uses: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
    let origins = uses
        .get(kind.key())
        .and_then(|k| k.get(which.to_string()))
        .and_then(|o| o.as_array());
    Ok(match origins {
        Some(origins) if !origins.is_empty() => origins.iter().all(|o| {
            o.as_str() == Some(TEST_PAGE) || o.as_i64().is_some_and(|n| tests.contains(&n))
        }),
        _ => false,
    })
}

/// What the playable ROM decided, copied into `auto` —the project's
/// automatic patches—, and out with what it no longer carries except what it
/// carries only for the tests. The files are copied as they are: the build's
/// are already the text that goes to version control. Returns how many and
/// how many bytes, and the files it removed.
pub fn copy(
    auto: &Path,
    build: &Path,
    kind: Kind,
    tests: &BTreeSet<i64>,
) -> Result<(usize, usize, Vec<PathBuf>), String> {
    let dest = auto.join(kind.directory());
    std::fs::create_dir_all(&dest).map_err(io(&dest))?;
    let folder = build.join(kind.in_build());
    let mut seen = BTreeSet::new();
    let mut bytes = 0;
    if folder.is_dir() {
        for name in toml_files(&folder)? {
            let path = folder.join(&name);
            let which = check::key_of(&check::read(&path)?, kind, &path)?;
            if only_for_tests(build, kind, &which, tests)? {
                continue;
            }
            let content = std::fs::read(&path).map_err(io(&path))?;
            let target = dest.join(&name);
            std::fs::write(&target, &content).map_err(io(&target))?;
            bytes += content.len();
            seen.insert(name);
        }
    }
    let mut removed = Vec::new();
    for name in toml_files(&dest)? {
        if !seen.contains(&name) {
            let path = dest.join(name);
            std::fs::remove_file(&path).map_err(io(&path))?;
            removed.push(path);
        }
    }
    Ok((seen.len(), bytes, removed))
}
