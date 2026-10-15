//! A whole game as a directory of JSON, and back.
//!
//! `ditto read` gives one JSON per binary file, which is right for looking at a
//! single map and wrong for keeping a game in a repository: the database alone
//! is one 17 MB file, and a one-line edit to a term shows up in a diff next to
//! every enemy in the game. So `ditto unpack` lays a game out as a tree, and
//! `ditto pack` builds the binaries back from that tree.
//!
//! `unpack` writes that tree **twice**, in one run: the *exact* dump, which is
//! the binary's own shape —a field holding its default left out, an enum by
//! its name— and which is what `pack` reads back; and the *resolved* view,
//! which is the same document with every field written, its default already
//! filled in, and every enum as the number the file stores. The second one
//! needs no schema to be read, which is what it is for: a consumer that is not
//! Ditto gets the data and not the rules. `ditto.json` says which one a
//! directory is, and `pack` refuses the resolved one.
//!
//! ```text
//! ditto.json            the dump's version and view, and the header of every file
//! maps.json             the map tree: the .lmt
//! maps/Map0001.json     one file per map, without its tile layers
//! maps/Map0001.tiles    those layers, as a legible grid
//! db/actors.json        the .ldb, one file per section
//! db/database.json      what is left of the database: its version
//! ```
//!
//! Three decisions are worth writing down, because none of them is forced:
//!
//! **The envelope is gone from the files and lives in `ditto.json`.** A single
//! JSON needs `{"format": "lmu", "header": ..., "data": ...}` around it because
//! nothing else says what it is. In a tree the place says it: `db/` is the
//! database, `maps/Map0001.json` is a map. What the place does **not** say is
//! the header string —`LcfMapUnit` and friends— and that one cannot be assumed,
//! because there are games with a changed name and rewriting it would give a
//! different binary. So it is kept, once per kind, in the manifest, with a
//! per-map override for the map that disagrees (normally there is none). Losing
//! it would mean not being able to write the binary back, which is the one
//! thing this format may not lose.
//!
//! **The tile layers stay out of the JSON.** They are 100x100 numbers per
//! layer; inside the JSON they are what makes a map file unreadable, and in a
//! diff they are noise that buries the event that actually changed. As a grid
//! with one line per row, a changed tile is a changed line, and the row and the
//! column are where they look like on the map.
//!
//! It is **not** done to save space, and the measurement says as much: the
//! 837,270 tiles of the corpus are 5,123,812 bytes as `.tiles` against some
//! 5,334,435 packed into the JSON, which is 4%. The reason is that one is
//! readable and the other is not. When a layer's length is not exactly
//! `width * height` —a file no editor would write— it stays in the JSON and no
//! `.tiles` is emitted; `pack` takes the layers from the `.tiles` if there is
//! one and from the JSON if there is not, so the dump says which it is.
//!
//! **The split of the database is by shape, not by a list of names.** Every
//! field of `Database` that is an array or an object gets its own file, named
//! after the field; the scalars stay together in `database.json`. A section
//! liblcf adds tomorrow gets its own file without this module learning its
//! name.

use crate::file::Document;
use crate::lcf::{error, Error, Result};
use crate::schema::{Database, Map, TreeMap};
use serde_json::{Map as JsonMap, Value};
use std::path::{Path, PathBuf};

/// The layout's version. It goes in `ditto.json` so that a dump made by an
/// older Ditto says so instead of being read wrong.
pub const VERSION: u32 = 2;

/// Which of the two views a dump directory holds. It is written into
/// `ditto.json`, and it is what lets `pack` refuse a resolved dump instead of
/// writing a binary with every chunk in it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum View {
    /// The binary's own shape: defaults omitted, enums by name. The only one
    /// `pack` reads.
    Exact,
    /// Every field written, its default filled in, enums as numbers. Needs no
    /// schema to be read, and cannot be written back.
    Resolved,
}

impl View {
    pub fn name(self) -> &'static str {
        match self {
            View::Exact => "exact",
            View::Resolved => "resolved",
        }
    }
}

const MANIFEST: &str = "ditto.json";
const TREE: &str = "maps.json";
const MAPS: &str = "maps";
const DB: &str = "db";
/// The fields of `Database` that are not a section of their own.
const DB_REST: &str = "database.json";

const LOWER: &str = "lower_layer";
const UPPER: &str = "upper_layer";

// --- unpack ----------------------------------------------------------------

/// Reads a game directory —`RPG_RT.ldb`, `RPG_RT.lmt`, `Map*.lmu`— and lays it
/// out **twice**: the exact dump under `exact` and the resolved view under
/// `resolved`.
///
/// The two come out of one read of the game and one set of values on purpose.
/// They are the same document said in two ways, and the only thing that makes
/// comparing them mean anything is that neither can be made without the other:
/// generated apart, it is a matter of time before one is from one run and the
/// other from another.
pub fn unpack(game: &Path, exact: &Path, resolved: &Path) -> Result<Vec<PathBuf>> {
    let ldb = read_doc(&in_any_case(game, "RPG_RT.ldb")?)?;
    let lmt = read_doc(&in_any_case(game, "RPG_RT.lmt")?)?;

    let Document::Ldb { header: db_header, data: db } = ldb else {
        return error("RPG_RT.ldb is not a database");
    };
    let Document::Lmt { header: tree_header, data: tree } = lmt else {
        return error("RPG_RT.lmt is not a map tree");
    };
    let mut maps = Vec::new();
    for path in map_files(game)? {
        let stem = stem(&path)?;
        let Document::Lmu { header, data } = read_doc(&path)? else {
            return error(format!("{}: not a map", path.display()));
        };
        maps.push((stem, header, data));
    }
    let game = Game { db_header, db, tree_header, tree, maps };

    let mut written = write_view(&game, exact, View::Exact)?;
    written.extend(crate::lcf::as_resolved(|| {
        write_view(&game, resolved, View::Resolved)
    })?);
    written.sort();
    Ok(written)
}

/// A game in memory, read once and written out once per view.
struct Game {
    db_header: String,
    db: Database,
    tree_header: String,
    tree: TreeMap,
    maps: Vec<(String, String, Map)>,
}

fn write_view(game: &Game, out: &Path, view: View) -> Result<Vec<PathBuf>> {
    prepare(out)?;
    let mut written = Vec::new();

    for (name, value) in split_database(&game.db)? {
        written.push(write_json(&out.join(DB).join(name), &value)?);
    }
    written.push(write_json(&out.join(TREE), &serde_json::to_value(&game.tree)?)?);

    let mut overrides = JsonMap::new();
    for (stem, header, map) in &game.maps {
        if header != "LcfMapUnit" {
            overrides.insert(stem.clone(), Value::String(header.clone()));
        }
        let (json, tiles) = split_map(map)?;
        written.push(write_json(&out.join(MAPS).join(format!("{stem}.json")), &json)?);
        if let Some(t) = tiles {
            written.push(write_text(&out.join(MAPS).join(format!("{stem}.tiles")), &t)?);
        }
    }

    let mut headers = JsonMap::new();
    headers.insert("database".into(), Value::String(game.db_header.clone()));
    headers.insert("tree".into(), Value::String(game.tree_header.clone()));
    headers.insert("map".into(), Value::String("LcfMapUnit".into()));
    if !overrides.is_empty() {
        headers.insert("map_overrides".into(), Value::Object(overrides));
    }
    let mut manifest = JsonMap::new();
    manifest.insert("ditto".into(), Value::from(VERSION));
    manifest.insert("view".into(), Value::String(view.name().into()));
    manifest.insert("headers".into(), Value::Object(headers));
    written.push(write_json(&out.join(MANIFEST), &Value::Object(manifest))?);

    Ok(written)
}

/// Empties a previous dump, or refuses a directory that is not one: writing a
/// dump over somebody else's files would leave both mixed, and leaving a stale
/// `Map0400.json` behind would put a map back into the game that is no longer
/// in it.
fn prepare(out: &Path) -> Result<()> {
    if out.join(MANIFEST).is_file() {
        for d in [MAPS, DB] {
            if out.join(d).is_dir() {
                std::fs::remove_dir_all(out.join(d))?;
            }
        }
    } else if out.is_dir() && out.read_dir()?.next().is_some() {
        return error(format!(
            "{} is not empty and has no {MANIFEST}: it is not a Ditto dump",
            out.display()
        ));
    }
    std::fs::create_dir_all(out.join(MAPS))?;
    std::fs::create_dir_all(out.join(DB))?;
    Ok(())
}

/// One file per section, and the scalars together. The rule is the shape of the
/// value, so a section added to `fields.csv` needs no change here.
fn split_database(db: &Database) -> Result<Vec<(String, Value)>> {
    let Value::Object(fields) = serde_json::to_value(db)? else {
        return error("the database did not serialize as an object");
    };
    let mut out = Vec::new();
    let mut rest = JsonMap::new();
    for (name, value) in fields {
        match value {
            Value::Array(_) | Value::Object(_) => out.push((format!("{name}.json"), value)),
            scalar => {
                rest.insert(name, scalar);
            }
        }
    }
    out.push((DB_REST.to_string(), Value::Object(rest)));
    Ok(out)
}

/// The map without its tile layers, and the layers as text. `None` when they
/// cannot be laid out as a `width * height` grid; then they stay in the JSON.
fn split_map(map: &Map) -> Result<(Value, Option<String>)> {
    let Value::Object(mut fields) = serde_json::to_value(map)? else {
        return error("a map did not serialize as an object");
    };
    let (w, h) = (map.width.max(0) as usize, map.height.max(0) as usize);
    let fits = |v: Option<&Value>| v.map_or(false, |v| v.as_array().map_or(false, |a| a.len() == w * h));
    if !(fits(fields.get(LOWER)) && fits(fields.get(UPPER))) {
        return Ok((Value::Object(fields), None));
    }
    fields.remove(LOWER);
    fields.remove(UPPER);
    Ok((Value::Object(fields), Some(grid(w, h, &map.lower_layer, &map.upper_layer))))
}

/// The two layers as one number per tile, `width` per line: a `.tiles`.
///
/// Public so that whoever makes a map's layers some other way —from a text
/// sketch, say— writes them in the very shape `pack` reads back, instead of
/// with a second writer of the format.
pub fn grid(w: usize, h: usize, lower: &[i16], upper: &[i16]) -> String {
    let mut s = format!(
        "# {w}x{h}, {} tiles per layer\n\
         # The two tile layers, in reading order: one id per tile, {w} per line.\n\
         # These are the ids the binary stores; what turns them into pictures is\n\
         # the chipset. Edited by hand, the count has to stay the same.\n",
        w * h
    );
    for (name, layer) in [("lower", lower), ("upper", upper)] {
        s.push_str(&format!("# {name}\n"));
        for row in layer.chunks(w.max(1)) {
            for t in row {
                s.push_str(&format!("{t:6}"));
            }
            s.push('\n');
        }
    }
    s
}

// --- reading a dump --------------------------------------------------------

/// A dump directory, to read the game from **with the schema's types**.
///
/// It is the one place that knows the layout —which file is which section,
/// where a map's layers are— and `pack` reads through it too, so the
/// binary and a consumer read the same tree the same way.
///
/// Either view reads into the same types. The exact dump leaves a field out
/// when it holds its default and `#[serde(default)]` puts it back; the
/// resolved view writes it, and writes an enum as its number, which the
/// generated `Deserialize` reads too. So a consumer that reads the resolved
/// view —the one that needs no schema to be read by anybody else— still gets
/// liblcf's names and types, and not a model of its own.
pub struct Dump {
    dir: PathBuf,
    view: View,
    manifest: Value,
}

impl Dump {
    /// Opens the dump in `dir`: reads its `ditto.json` and refuses one of
    /// another layout version, which would be read wrong instead of failing.
    pub fn open(dir: &Path) -> Result<Dump> {
        let manifest = read_json(&dir.join(MANIFEST))?;
        let version = manifest.get("ditto").and_then(Value::as_u64).unwrap_or(0);
        if version != VERSION as u64 {
            return error(format!(
                "{}: it says it is a dump of version {version} and this Ditto writes {VERSION}",
                dir.join(MANIFEST).display()
            ));
        }
        let view = match manifest.get("view").and_then(Value::as_str).unwrap_or("") {
            v if v == View::Exact.name() => View::Exact,
            v if v == View::Resolved.name() => View::Resolved,
            v => {
                return error(format!(
                    "{}: {v:?} is not a view this Ditto writes",
                    dir.join(MANIFEST).display()
                ))
            }
        };
        Ok(Dump { dir: dir.to_path_buf(), view, manifest })
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    pub fn view(&self) -> View {
        self.view
    }

    /// The whole database: every section joined back into one `Database`.
    pub fn database(&self) -> Result<Database> {
        Ok(serde_json::from_value(join_database(&self.dir.join(DB))?)?)
    }

    /// One section of the database, by the name of its field in `Database`
    /// —`actors`, `chipsets`, `system`—, without reading the others: the
    /// battle's tables have no reason to parse every animation.
    ///
    /// ```no_run
    /// # let dump = ditto::dump::Dump::open(std::path::Path::new("data")).unwrap();
    /// let actors: Vec<ditto::schema::Actor> = dump.section("actors").unwrap();
    /// ```
    pub fn section<T: serde::de::DeserializeOwned>(&self, name: &str) -> Result<T> {
        let path = self.dir.join(DB).join(format!("{name}.json"));
        serde_json::from_value(read_json(&path)?)
            .map_err(|e| Error(format!("{}: {e}", path.display())))
    }

    /// The map tree: the `.lmt`.
    pub fn tree(&self) -> Result<TreeMap> {
        let path = self.dir.join(TREE);
        serde_json::from_value(read_json(&path)?)
            .map_err(|e| Error(format!("{}: {e}", path.display())))
    }

    /// Map `id`, with its tile layers.
    pub fn map(&self, id: u32) -> Result<Map> {
        read_map(&self.dir.join(MAPS).join(format!("Map{id:04}.json")))
    }

    /// The map files of the dump, sorted: what `map` reads, by path.
    pub fn map_files(&self) -> Result<Vec<PathBuf>> {
        json_files(&self.dir.join(MAPS))
    }

    /// The header the manifest keeps for a kind of file —`database`, `tree`,
    /// `map`— or `fallback` if it has none.
    fn header(&self, kind: &str, fallback: &str) -> String {
        self.manifest
            .get("headers")
            .and_then(|h| h.get(kind))
            .and_then(Value::as_str)
            .unwrap_or(fallback)
            .to_string()
    }

    /// The header of one map, which is the manifest's for every map unless
    /// it keeps one of its own for it.
    fn map_header(&self, stem: &str) -> String {
        self.manifest
            .get("headers")
            .and_then(|h| h.get("map_overrides"))
            .and_then(|o| o.get(stem))
            .and_then(Value::as_str)
            .map_or_else(|| self.header("map", "LcfMapUnit"), str::to_string)
    }
}

/// A map from its JSON, with its layers from the `.tiles` beside it if there
/// is one. It takes a path and not a number so that a map in the same shape
/// that is not in a dump —one a project changed, kept elsewhere— reads the
/// same way.
pub fn read_map(path: &Path) -> Result<Map> {
    let stem = stem(path)?;
    serde_json::from_value(join_map(path, &stem)?)
        .map_err(|e| Error(format!("{}: {e}", path.display())))
}

// --- pack ------------------------------------------------------------------

/// Builds the binaries back from a dump: `RPG_RT.ldb`, `RPG_RT.lmt` and one
/// `.lmu` per map, written into `out`.
pub fn pack(dump: &Path, out: &Path) -> Result<Vec<PathBuf>> {
    let source = Dump::open(dump)?;
    // The resolved view has every field written, so packing it would write
    // every chunk and give a binary the editor never wrote. It is refused
    // rather than left to the person to notice, because what comes out is a
    // valid file: nothing downstream would complain.
    if source.view() != View::Exact {
        return error(format!(
            "{}: it is the {} view, and only the {} one can be written back",
            dump.join(MANIFEST).display(),
            source.view().name(),
            View::Exact.name()
        ));
    }
    std::fs::create_dir_all(out)?;
    let mut written = Vec::new();

    written.push(write_binary(
        &out.join("RPG_RT.ldb"),
        &Document::Ldb {
            header: source.header("database", "LcfDataBase"),
            data: source.database()?,
        },
    )?);

    written.push(write_binary(
        &out.join("RPG_RT.lmt"),
        &Document::Lmt { header: source.header("tree", "LcfMapTree"), data: source.tree()? },
    )?);

    for path in source.map_files()? {
        let stem = stem(&path)?;
        written.push(write_binary(
            &out.join(format!("{stem}.lmu")),
            &Document::Lmu { header: source.map_header(&stem), data: read_map(&path)? },
        )?);
    }

    written.sort();
    Ok(written)
}

/// The sections back into one object. `database.json` carries the scalars; a
/// file whose name the schema does not know is a mistake worth reporting, not a
/// file to ignore in silence.
fn join_database(dir: &Path) -> Result<Value> {
    let mut fields = JsonMap::new();
    for path in json_files(dir)? {
        let value = read_json(&path)?;
        if path.file_name().is_some_and(|n| n == DB_REST) {
            let Value::Object(rest) = value else {
                return error(format!("{}: it is not an object", path.display()));
            };
            fields.extend(rest);
        } else {
            fields.insert(stem(&path)?, value);
        }
    }
    Ok(Value::Object(fields))
}

/// Where the layers of the map whose JSON is at `map` go: the `.tiles`
/// beside it. A map kept outside a dump in the same shape —one a project
/// changed— has its layers there too, and whoever checks such a file is
/// whole asks here instead of copying the layout.
pub fn layers_path(map: &Path) -> PathBuf {
    let stem = map.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
    map.with_file_name(format!("{stem}.tiles"))
}

/// Whether `dir` holds a dump: whether its manifest is there. It does not
/// read it; [`Dump::open`] does, and refuses one of another version.
pub fn is_dump(dir: &Path) -> bool {
    dir.join(MANIFEST).is_file()
}

/// A map's JSON with its layers put back, from the `.tiles` when there is one.
fn join_map(path: &Path, stem: &str) -> Result<Value> {
    let Value::Object(mut fields) = read_json(path)? else {
        return error(format!("{}: it is not an object", path.display()));
    };
    let tiles = path.with_file_name(format!("{stem}.tiles"));
    if !tiles.is_file() {
        return Ok(Value::Object(fields));
    }
    let (lower, upper) = ungrid(&tiles)?;
    // The count is checked here and not on the way in: a hand-edited grid with
    // a row too many would otherwise become a map of another size without a
    // word.
    let n = fields.get("width").and_then(Value::as_i64).unwrap_or(20)
        * fields.get("height").and_then(Value::as_i64).unwrap_or(15);
    for (name, layer) in [(LOWER, &lower), (UPPER, &upper)] {
        if layer.len() as i64 != n {
            return error(format!(
                "{}: the {name} has {} tiles and the map is {n}",
                tiles.display(),
                layer.len()
            ));
        }
    }
    fields.insert(LOWER.into(), Value::from(lower));
    fields.insert(UPPER.into(), Value::from(upper));
    Ok(Value::Object(fields))
}

/// The two layers of a `.tiles`. A `#` line is a comment, except `# lower` and
/// `# upper`, which say which layer the numbers that follow belong to.
fn ungrid(path: &Path) -> Result<(Vec<i16>, Vec<i16>)> {
    let text = std::fs::read_to_string(path)?;
    let (mut lower, mut upper) = (Vec::new(), Vec::new());
    let mut into_upper = false;
    let mut seen = false;
    for line in text.lines() {
        if let Some(rest) = line.trim().strip_prefix('#') {
            match rest.trim() {
                "lower" => (into_upper, seen) = (false, true),
                "upper" => (into_upper, seen) = (true, true),
                _ => {}
            }
            continue;
        }
        for word in line.split_whitespace() {
            let t: i16 = word
                .parse()
                .map_err(|e| Error(format!("{}: {word:?} is not a tile id: {e}", path.display())))?;
            if into_upper {
                upper.push(t);
            } else {
                lower.push(t);
            }
        }
    }
    if !seen {
        return error(format!(
            "{}: it has no `# lower` or `# upper` line saying which layer is which",
            path.display()
        ));
    }
    Ok((lower, upper))
}

// --- the disk --------------------------------------------------------------

fn read_doc(path: &Path) -> Result<Document> {
    let d = std::fs::read(path).map_err(|e| Error(format!("{}: {e}", path.display())))?;
    crate::file::read(&d).map_err(|e| Error(format!("{}: {e}", path.display())))
}

fn read_json(path: &Path) -> Result<Value> {
    let d = std::fs::read(path).map_err(|e| Error(format!("{}: {e}", path.display())))?;
    serde_json::from_slice(&d).map_err(|e| Error(format!("{}: {e}", path.display())))
}

fn write_json(path: &Path, v: &Value) -> Result<PathBuf> {
    let mut d = pretty(v);
    d.push('\n');
    write_text_bytes(path, d.as_bytes())
}

/// How wide a line of packed numbers is allowed to get.
const WIDTH: usize = 96;

/// `serde_json::to_vec_pretty`, except that **a list of plain values stays on
/// its line**, wrapped at `WIDTH`.
///
/// It is not decoration: one element per line is what the default does, and in
/// this format there are lists everywhere —the parameters of a command, the
/// ranks of a state, the frames of an animation—. Over the measured game it is
/// the difference between a 29 MB dump and a 17 MB one, and a command whose
/// four parameters take six lines is also harder to read than one that takes
/// one. Objects always go one key per line: those are what a diff is read for.
fn pretty(v: &Value) -> String {
    let mut s = String::new();
    write_value(&mut s, v, 0);
    s
}

/// A small object with nothing but plain values inside goes on one line, when
/// it fits. That is what turns an event command —a code, an indent, a string
/// and a handful of parameters— from six lines into one, and there are 65,596
/// of them in the battle events of the measured game alone.
///
/// An object holding another object never gets this: the nesting is the shape
/// of the data and flattening it would hide it.
fn flat_object(o: &serde_json::Map<String, Value>, indent: usize) -> Option<String> {
    let plain = |v: &Value| match v {
        Value::Object(_) => false,
        Value::Array(a) => a.iter().all(|e| !e.is_array() && !e.is_object()),
        _ => true,
    };
    if !o.values().all(plain) {
        return None;
    }
    let body: Vec<String> = o
        .iter()
        .map(|(k, v)| {
            let mut rendered = String::new();
            write_value(&mut rendered, v, indent);
            format!("{}: {rendered}", Value::String(k.clone()))
        })
        .collect();
    let line = format!("{{{}}}", body.join(", "));
    (indent * 2 + line.len() <= WIDTH && !line.contains('\n')).then_some(line)
}

fn write_value(s: &mut String, v: &Value, indent: usize) {
    let pad = |s: &mut String, n: usize| s.push_str(&"  ".repeat(n));
    match v {
        Value::Array(a) if a.is_empty() => s.push_str("[]"),
        Value::Array(a) if a.iter().all(|e| !e.is_array() && !e.is_object()) => {
            // The whole list on one line while it fits, and packed into as few
            // lines as possible when it does not.
            let items: Vec<String> = a.iter().map(|e| e.to_string()).collect();
            let flat = items.join(", ");
            if indent * 2 + flat.len() + 2 <= WIDTH {
                s.push('[');
                s.push_str(&flat);
                s.push(']');
                return;
            }
            s.push_str("[\n");
            let mut line = String::new();
            for (i, it) in items.iter().enumerate() {
                let last = i + 1 == items.len();
                let piece = if last { it.clone() } else { format!("{it},") };
                if !line.is_empty() && (indent + 1) * 2 + line.len() + 1 + piece.len() > WIDTH {
                    pad(s, indent + 1);
                    s.push_str(&line);
                    s.push('\n');
                    line.clear();
                }
                if !line.is_empty() {
                    line.push(' ');
                }
                line.push_str(&piece);
            }
            if !line.is_empty() {
                pad(s, indent + 1);
                s.push_str(&line);
                s.push('\n');
            }
            pad(s, indent);
            s.push(']');
        }
        Value::Array(a) => {
            s.push_str("[\n");
            for (i, e) in a.iter().enumerate() {
                pad(s, indent + 1);
                write_value(s, e, indent + 1);
                s.push_str(if i + 1 == a.len() { "\n" } else { ",\n" });
            }
            pad(s, indent);
            s.push(']');
        }
        Value::Object(o) if o.is_empty() => s.push_str("{}"),
        Value::Object(o) => {
            if let Some(line) = flat_object(o, indent) {
                s.push_str(&line);
                return;
            }
            s.push_str("{\n");
            for (i, (k, e)) in o.iter().enumerate() {
                pad(s, indent + 1);
                s.push_str(&Value::String(k.clone()).to_string());
                s.push_str(": ");
                write_value(s, e, indent + 1);
                s.push_str(if i + 1 == o.len() { "\n" } else { ",\n" });
            }
            pad(s, indent);
            s.push('}');
        }
        scalar => s.push_str(&scalar.to_string()),
    }
}

fn write_text(path: &Path, s: &str) -> Result<PathBuf> {
    write_text_bytes(path, s.as_bytes())
}

fn write_text_bytes(path: &Path, d: &[u8]) -> Result<PathBuf> {
    if let Some(p) = path.parent() {
        std::fs::create_dir_all(p)?;
    }
    std::fs::write(path, d).map_err(|e| Error(format!("{}: {e}", path.display())))?;
    Ok(path.to_path_buf())
}

fn write_binary(path: &Path, doc: &Document) -> Result<PathBuf> {
    let d = crate::file::write(doc)?;
    write_text_bytes(path, &d)
}

fn stem(path: &Path) -> Result<String> {
    match path.file_stem().and_then(|s| s.to_str()) {
        Some(s) => Ok(s.to_string()),
        None => error(format!("{}: a name that is not text", path.display())),
    }
}

/// The files of a directory with a given extension, sorted, so a dump does not
/// depend on the order the filesystem hands them out.
fn by_extension(dir: &Path, ext: &str) -> Result<Vec<PathBuf>> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(dir)
        .map_err(|e| Error(format!("{}: {e}", dir.display())))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x.eq_ignore_ascii_case(ext)))
        .collect();
    v.sort();
    Ok(v)
}

/// The file of `dir` called `name` in any case. The games were made on
/// Windows, where `RPG_RT.LDB` and `RPG_RT.ldb` are the same file, and some
/// ship it in capitals. The exact name wins if there is one; without any, the
/// path that does not exist, so that the error names what was looked for.
fn in_any_case(dir: &Path, name: &str) -> Result<PathBuf> {
    let exact = dir.join(name);
    if exact.is_file() {
        return Ok(exact);
    }
    let found = std::fs::read_dir(dir)
        .map_err(|e| Error(format!("{}: {e}", dir.display())))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .find(|p| p.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.eq_ignore_ascii_case(name)));
    Ok(found.unwrap_or(exact))
}

fn json_files(dir: &Path) -> Result<Vec<PathBuf>> {
    by_extension(dir, "json")
}

fn map_files(dir: &Path) -> Result<Vec<PathBuf>> {
    let v = by_extension(dir, "lmu")?;
    if v.is_empty() {
        return error(format!("{}: it has no .lmu files", dir.display()));
    }
    Ok(v)
}
