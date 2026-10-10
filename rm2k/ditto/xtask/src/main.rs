//! Generates `src/schema/` from liblcf's CSV tables.
//!
//! It does not run as part of the build: it is invoked by hand, and **what it
//! produces is committed**.
//!
//!     cargo xtask generate --liblcf /path/to/liblcf
//!
//! The reason it is explicit and not a `build.rs` is that the generated code
//! is this project's source of truth: if liblcf renames a field, the diff has
//! to say exactly that —a name changing in the corresponding struct— and go
//! through review like any other change. A hidden build step would give the
//! same result with nobody looking at it.
//!
//! Conceptually the CSV is a dependency of Ditto, and this is what runs when
//! its version is bumped.
//!
//! # What it emits
//!
//! Four things, and all four come from the CSV and from no judgement of
//! ours:
//!
//! * the **structs** and the **enums**, with liblcf's names;
//! * the **default of every field**, with the value the `Default Value`
//!   column declares —this is where the `max_hp` that read 1 and is really 10
//!   lived—, written **once and next to the field**: `schema_struct!` builds
//!   the `Default` from there, and the struct's `#[serde(default)]` uses it
//!   for JSON;
//! * the **codec**: which field is which chunk, how it is encoded, and whether
//!   it is emitted when it holds the default (the `PersistIfDefault` column);
//! * the **description** —`src/schema/description.rs`—, which is the same
//!   thing as data, for `ditto schema` to hand to a reader that is not Rust.
//!   It is emitted here and not read back out of the generated structs so
//!   that the two cannot say different things.
//!
//! What is **not** generated are the six structs liblcf reads by hand
//! (`RawStruct`): `Parameters`, `Equipment`, `Rect`, `EventCommand`,
//! `MoveCommand` and `TreeMap`. The CSV declares their fields but not their
//! chunk indices, because they have none: they are positional. Their codecs
//! are written by hand in `src/raw.rs`.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

/// A row of `fields.csv`.
#[derive(Clone)]
struct Field {
    structure: String,
    name: String,
    /// `f` is an ordinary field; `t` is the length of a vector, which lives in
    /// its own chunk; empty is a positional field of a raw struct.
    kind: String,
    ty: String,
    index: u32,
    default: String,
    /// Whether the binary stores the field even when it holds the default.
    persist: bool,
    /// Fields that only exist in RPG Maker 2003. Ditto targets 2000.
    is_2k3: bool,
}

/// A row of `structs.csv`.
struct StructDef {
    /// `ldb`, `lmu`, `lmt` or `lsd`.
    file: String,
    name: String,
    /// Whether every element of the array carries its ID in front.
    with_id: bool,
}

/// The structs liblcf reads by hand because they are not chunk-based.
const RAW_STRUCTS: &[&str] = &[
    "Parameters",
    "Equipment",
    "Rect",
    "EventCommand",
    "MoveCommand",
    "TreeMap",
];

fn main() {
    let mut args = std::env::args().skip(1);
    let command = args.next().unwrap_or_default();
    if command != "generate" {
        eprintln!("usage: cargo xtask generate --liblcf <path to liblcf> [--out <dir>]");
        std::process::exit(2);
    }
    let mut liblcf: Option<PathBuf> = std::env::var_os("LIBLCF").map(PathBuf::from);
    let mut out_dir = PathBuf::from("src/schema");
    while let Some(a) = args.next() {
        match a.as_str() {
            "--liblcf" => liblcf = Some(PathBuf::from(args.next().expect("--liblcf takes a path"))),
            "--out" => out_dir = PathBuf::from(args.next().expect("--out takes a path")),
            other => panic!("unknown argument {other:?}"),
        }
    }
    let liblcf = liblcf.unwrap_or_else(|| {
        eprintln!(
            "xtask: where is liblcf? Pass `--liblcf <path>` or set the LIBLCF\n\
             environment variable. It is cloned from\n\
             https://github.com/EasyRPG/liblcf and only its `generator/csv/`\n\
             directory is read."
        );
        std::process::exit(2);
    });
    let csv = liblcf.join("generator/csv");
    let fields = read_fields(&csv.join("fields.csv"));
    let enums = read_enums(&csv.join("enums.csv"));
    let flags = read_flags(&csv.join("flags.csv"));
    let structs = read_structs(&csv.join("structs.csv"));
    let constants = read_constants(&csv.join("constants.csv"));

    // The CSV order **is** the order of the chunks in the file: liblcf writes
    // the fields in the order the table declares them, and its own generator
    // even warns on stderr when an index breaks the ascending order. So it is
    // kept as it comes.
    let mut by_structure: BTreeMap<&str, Vec<&Field>> = BTreeMap::new();
    for f in &fields {
        if f.is_2k3 {
            continue; // Ditto targets RPG Maker 2000
        }
        by_structure.entry(&f.structure).or_default().push(f);
    }

    let mut text = String::new();
    header(&mut text);
    for (name, value) in &constants {
        text.push_str(&format!(
            "/// Generated from `constants.csv`.\n#[allow(non_upper_case_globals)]\npub const {name}: i32 = {value};\n\n"
        ));
    }
    let mut enum_names: BTreeMap<String, Vec<(String, i64)>> = BTreeMap::new();
    for (name, variants) in &enums {
        enum_names.insert(name.clone(), emit_enum(&mut text, name, variants));
    }
    for (structure, fields) in &flags {
        emit_flags(&mut text, structure, fields);
    }
    for (structure, fields) in &by_structure {
        emit_struct(&mut text, structure, fields, &enums, &structs);
    }
    let mut with_codec = 0;
    for s in &structs {
        // The codec only covers what Ditto reads today. `.lsd` —the save
        // files— has the structs but not the reader: it is not in the corpus
        // the round trip is measured against, and without that there would be
        // nothing to check it with.
        if s.file == "lsd" || RAW_STRUCTS.contains(&s.name.as_str()) {
            continue;
        }
        let Some(fields) = by_structure.get(s.name.as_str()) else {
            continue;
        };
        emit_codec(&mut text, s, fields, &enums, &structs);
        with_codec += 1;
    }

    fs::create_dir_all(&out_dir).expect("could not create the output directory");
    let target = out_dir.join("mod.rs");
    fs::write(&target, text).expect("could not write the schema");

    // The same pass writes the description, on purpose: it says the same
    // things the structs above say —the chunk, the default, the enum— and
    // the only way for the two not to drift is for one run to write both.
    let mut desc = String::new();
    emit_description(
        &mut desc,
        &by_structure,
        &enums,
        &enum_names,
        &structs,
        &constants,
    );
    let desc_target = out_dir.join("description.rs");
    fs::write(&desc_target, desc).expect("could not write the description");

    println!(
        "{} structures ({} with codec), {} enums and {} flag sets -> {}, {}",
        by_structure.len(),
        with_codec,
        enums.len(),
        flags.len(),
        target.display(),
        desc_target.display()
    );
}

/// The header of the generated file. It deliberately does not mention where
/// liblcf was checked out: the path differs per machine, and printing it would
/// make the output depend on the caller instead of on the CSV.
fn header(out: &mut String) {
    out.push_str(
        "//! The schema of the RPG Maker 2000 files, and its codec.\n\
         //!\n\
         //! **Generated by `cargo xtask generate`, and committed on purpose.**\n\
         //! It is not edited by hand: what is edited is the generator or the\n\
         //! CSV it reads. See `xtask/src/main.rs` for the why.\n\
         //!\n\
         //! It comes from liblcf's tables, which is where the whole ecosystem\n\
         //! takes the names from: the binary has none, only field indices.\n\
         //!\n\
         //! Every field carries its default next to it (`= 10`): that is what\n\
         //! fills it in when reading and what decides omission when writing,\n\
         //! and `schema_struct!` builds the `Default` out of it. See\n\
         //! `crate::lcf::schema_struct`.\n\
         \n\
         #![allow(dead_code, unused_variables, clippy::all)]\n\
         \n\
         pub mod description;\n\
         \n\
         use crate::lcf::*;\n\
         use serde::{Deserialize, Serialize};\n\n",
    );
}

// --- Reading the CSVs -----------------------------------------------------

/// A CSV with quotes: `fields.csv` uses them for defaults that carry commas or
/// quotes inside (`"(OFF)"`, `Sound{ "" }`).
fn rows(text: &str) -> Vec<Vec<String>> {
    let mut out = Vec::new();
    for line in text.lines() {
        let mut cells = Vec::new();
        let mut current = String::new();
        let mut in_quotes = false;
        let mut chars = line.chars().peekable();
        while let Some(c) = chars.next() {
            match c {
                '"' if in_quotes && chars.peek() == Some(&'"') => {
                    current.push('"');
                    chars.next();
                }
                '"' => in_quotes = !in_quotes,
                ',' if !in_quotes => cells.push(std::mem::take(&mut current)),
                other => current.push(other),
            }
        }
        cells.push(current);
        out.push(cells);
    }
    out
}

fn read_fields(path: &Path) -> Vec<Field> {
    let text = fs::read_to_string(path).expect("could not find fields.csv");
    let mut out = Vec::new();
    for (n, c) in rows(&text).into_iter().enumerate() {
        if n == 0 || c.len() < 8 || c[0].is_empty() || c[1].is_empty() {
            continue;
        }
        let index = if c[4].is_empty() {
            0
        } else {
            u32::from_str_radix(c[4].trim_start_matches("0x"), 16).expect("malformed index")
        };
        out.push(Field {
            structure: c[0].clone(),
            name: c[1].clone(),
            kind: c[2].clone(),
            ty: c[3].clone(),
            index,
            default: c[5].clone(),
            persist: c[6] == "1",
            is_2k3: c[7] == "1",
        });
    }
    out
}

/// `enums.csv`: Structure, Entry, Value, Index.
fn read_enums(path: &Path) -> BTreeMap<String, Vec<(String, i64)>> {
    let text = fs::read_to_string(path).expect("could not find enums.csv");
    let mut out: BTreeMap<String, Vec<(String, i64)>> = BTreeMap::new();
    for (n, c) in rows(&text).into_iter().enumerate() {
        if n == 0 || c.len() < 4 || c[0].is_empty() {
            continue;
        }
        let Ok(index) = c[3].trim().parse::<i64>() else {
            continue;
        };
        out.entry(format!("{}{}", c[0], capitalize(&c[1])))
            .or_default()
            .push((c[2].clone(), index));
    }
    out
}

/// `flags.csv`: Structure, Field, Is2k3. The order **is** the order of the bits.
fn read_flags(path: &Path) -> BTreeMap<String, Vec<String>> {
    let text = fs::read_to_string(path).expect("could not find flags.csv");
    let mut out: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (n, c) in rows(&text).into_iter().enumerate() {
        if n == 0 || c.len() < 3 || c[0].is_empty() {
            continue;
        }
        // The 2003 flags are not written into a 2000 file, and neither is the
        // bit they would occupy: liblcf skips them when packing.
        if c[2] == "1" {
            out.entry(c[0].clone()).or_default();
            continue;
        }
        out.entry(c[0].clone()).or_default().push(c[1].clone());
    }
    out
}

/// `constants.csv`: the few named values the CSV uses as defaults. Only the
/// integers: the one that is not (`kEmptyName`) is resolved separately.
fn read_constants(path: &Path) -> Vec<(String, String)> {
    let text = fs::read_to_string(path).expect("could not find constants.csv");
    let mut out = Vec::new();
    for (n, c) in rows(&text).into_iter().enumerate() {
        if n == 0 || c.len() < 4 || c[1].is_empty() || c[2] != "int" {
            continue;
        }
        out.push((c[1].clone(), c[3].clone()));
    }
    out
}

fn read_structs(path: &Path) -> Vec<StructDef> {
    let text = fs::read_to_string(path).expect("could not find structs.csv");
    let mut out = Vec::new();
    for (n, c) in rows(&text).into_iter().enumerate() {
        if n == 0 || c.len() < 4 || c[0].is_empty() {
            continue;
        }
        out.push(StructDef {
            file: c[0].clone(),
            name: c[1].clone(),
            with_id: c[3] == "1",
        });
    }
    out
}

// --- Types ----------------------------------------------------------------

/// How a field is encoded in the binary.
#[derive(Clone, PartialEq)]
enum Enc {
    /// BER integer: 7 bits per byte, the high bit says it continues.
    Ber,
    Enum(String),
    Flags(String),
    Bool,
    U8,
    I8,
    F64,
    Text,
    VecU8,
    VecI16,
    /// `Vector<Int32>`: four raw bytes per element, **not** BER.
    VecI32,
    VecU32,
    /// One byte per bool, both `Vector<Boolean>` and `DBBitArray`.
    VecBool,
    /// Four raw bytes: only `Rect`, which is positional.
    U32,
    /// A nested chunk-based struct.
    Struct(String),
    /// `count` + per element `id` + struct.
    Array(String),
    /// The ones liblcf reads by hand inside a chunk.
    Raw(String),
    EventCommands,
    MoveCommands,
}

fn enc(ty: &str, enums: &BTreeMap<String, Vec<(String, i64)>>, enum_name: &str) -> Enc {
    match ty {
        "Int32" | "DatabaseVersion" => Enc::Ber,
        "UInt32" => Enc::U32,
        // The parameters of an event command: BER integers, but in Rust just a
        // Vec. Their codec is positional and written by hand.
        "DBArray<Int32>" => Enc::VecI32,
        "Boolean" => Enc::Bool,
        "UInt8" => Enc::U8,
        "Int8" => Enc::I8,
        "Double" => Enc::F64,
        "String" | "DBString" => Enc::Text,
        "DBBitArray" | "Vector<Boolean>" => Enc::VecBool,
        "Vector<UInt8>" => Enc::VecU8,
        "Vector<Int16>" => Enc::VecI16,
        "Vector<Int32>" | "Vector<Ref<BattleCommand:Int32>>" => Enc::VecI32,
        "Vector<UInt32>" => Enc::VecU32,
        "Vector<EventCommand>" => Enc::EventCommands,
        "Vector<MoveCommand>" => Enc::MoveCommands,
        t if t.starts_with("Vector<Ref<") => Enc::VecI32,
        t if t.starts_with("Ref<") => Enc::Ber,
        t if t.ends_with("_Flags") => Enc::Flags(type_ident(&t.replace("_Flags", "Flags"))),
        t if t.starts_with("Enum<") => {
            if enums.contains_key(enum_name) {
                Enc::Enum(enum_name.to_string())
            } else {
                Enc::Ber
            }
        }
        t if t.starts_with("Array<") => {
            let inner = &t["Array<".len()..t.len() - 1];
            Enc::Array(type_ident(inner.split(':').next().unwrap_or(inner)))
        }
        other => {
            let id = type_ident(other);
            if RAW_STRUCTS.contains(&id.as_str()) {
                Enc::Raw(id)
            } else {
                Enc::Struct(id)
            }
        }
    }
}

/// The name of the enum this field would get, if one exists.
fn enum_name(field: &Field, enums: &BTreeMap<String, Vec<(String, i64)>>) -> String {
    // First the one the type declares, which is what rules; failing that, the
    // one built out of Structure + Field, which is the `enums.csv` convention.
    if let Some(inner) = field.ty.strip_prefix("Enum<") {
        let inner = &inner[..inner.len() - 1];
        let (structure, name) = inner.split_once('_').unwrap_or((inner, ""));
        let n = format!("{structure}{}", capitalize(name));
        if enums.contains_key(&n) {
            return n;
        }
    }
    let candidate = format!("{}{}", field.structure, capitalize(&field.name));
    if enums.contains_key(&candidate) {
        return candidate;
    }
    String::new()
}

fn rust_type(e: &Enc) -> String {
    match e {
        Enc::Ber => "i32".into(),
        Enc::Enum(n) | Enc::Flags(n) | Enc::Struct(n) | Enc::Raw(n) => n.clone(),
        Enc::Bool => "bool".into(),
        Enc::U8 => "u8".into(),
        Enc::I8 => "i8".into(),
        Enc::F64 => "f64".into(),
        Enc::Text => "String".into(),
        Enc::VecU8 => "Vec<u8>".into(),
        Enc::VecI16 => "Vec<i16>".into(),
        Enc::VecI32 => "Vec<i32>".into(),
        Enc::VecU32 => "Vec<u32>".into(),
        Enc::VecBool => "Vec<bool>".into(),
        Enc::U32 => "u32".into(),
        Enc::Array(n) => format!("Vec<{n}>"),
        Enc::EventCommands => "Vec<EventCommand>".into(),
        Enc::MoveCommands => "Vec<MoveCommand>".into(),
    }
}

// --- Emission -------------------------------------------------------------

/// Emits the enum and returns the variants that made it in, by the name they
/// carry in the JSON. The caller needs them for `description.rs`: an enum value
/// travels as that name, so whoever reads the JSON needs the same table, and
/// building it twice is how it would drift.
fn emit_enum(out: &mut String, name: &str, variants: &[(String, i64)]) -> Vec<(String, i64)> {
    // `Other` is what keeps the round trip from depending on liblcf knowing
    // every value: a number the table does not name is stored as a number and
    // comes back the same.
    // Neither `Serialize` nor `Deserialize` is derived: an enum goes into the
    // JSON as its name in the exact dump and as its number in the resolved
    // view, and both have to read back —the resolved one is what a consumer
    // of the library reads—. Writing is `lcf::serialize_enum`'s; reading,
    // `lcf::EnumRepr`'s.
    out.push_str(&format!(
        "/// Generated from `enums.csv`.\n\
         #[derive(Debug, Clone, Copy, PartialEq, Eq)]\n\
         pub enum {name} {{\n"
    ));
    let mut seen = BTreeSet::new();
    let mut usable: Vec<(String, i64)> = Vec::new();
    let mut json_names: Vec<(String, i64)> = Vec::new();
    for (variant, value) in variants {
        let id = type_ident(variant);
        if !seen.insert(id.clone()) {
            continue; // the CSV repeats some entry under the same name
        }
        out.push_str(&format!("    {id},\n"));
        usable.push((id, *value));
        json_names.push((variant.clone(), *value));
    }
    out.push_str("    /// A value `enums.csv` does not name. It goes back to the binary as is.\n");
    out.push_str("    Other(i32),\n}\n\n");

    out.push_str(&format!(
        "impl {name} {{\n    pub fn to_i32(self) -> i32 {{\n        match self {{\n"
    ));
    for (id, value) in &usable {
        out.push_str(&format!("            {name}::{id} => {value},\n"));
    }
    out.push_str(&format!(
        "            {name}::Other(v) => v,\n        }}\n    }}\n"
    ));
    out.push_str("    pub fn from_i32(v: i32) -> Self {\n        match v {\n");
    let mut placed = BTreeSet::new();
    for (id, value) in &usable {
        if !placed.insert(*value) {
            continue; // two names for the same number: the first one wins
        }
        out.push_str(&format!("            {value} => {name}::{id},\n"));
    }
    out.push_str(&format!(
        "            v => {name}::Other(v),\n        }}\n    }}\n"
    ));
    out.push_str(
        "    /// The name `enums.csv` gives this value, and `None` for one it\n\
         \x20   /// does not name.\n\
         \x20   pub fn json_name(self) -> Option<&'static str> {\n        match self {\n",
    );
    for ((id, _), (variant, _)) in usable.iter().zip(json_names.iter()) {
        out.push_str(&format!(
            "            {name}::{id} => Some(\"{variant}\"),\n"
        ));
    }
    out.push_str(&format!(
        "            {name}::Other(_) => None,\n        }}\n    }}\n"
    ));
    out.push_str(
        "    /// The value `enums.csv` gives this name, and `None` for a name it\n\
         \x20   /// does not have.\n\
         \x20   pub fn from_json_name(name: &str) -> Option<Self> {\n        match name {\n",
    );
    for ((id, _), (variant, _)) in usable.iter().zip(json_names.iter()) {
        out.push_str(&format!("            \"{variant}\" => Some({name}::{id}),\n"));
    }
    out.push_str("            _ => None,\n        }\n    }\n}\n\n");

    // `{"Other": n}` is read as `Other(n)` as is, and not through `from_i32`:
    // it is what the exact dump wrote for that value, and the round trip
    // gives back what it was given.
    let names: Vec<String> = json_names.iter().map(|(v, _)| format!("\"{v}\"")).collect();
    out.push_str(&format!(
        "impl<'de> serde::Deserialize<'de> for {name} {{\n    \
         fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {{\n        \
         match EnumRepr::deserialize(d)? {{\n            \
         EnumRepr::Number(v) => Ok({name}::from_i32(v)),\n            \
         EnumRepr::Other {{ other }} => Ok({name}::Other(other)),\n            \
         EnumRepr::Name(n) => {name}::from_json_name(&n)\n                \
         .ok_or_else(|| serde::de::Error::unknown_variant(&n, &[{}])),\n        \
         }}\n    }}\n}}\n\n",
        names.join(", ")
    ));

    out.push_str(&format!(
        "impl serde::Serialize for {name} {{\n    \
         fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {{\n        \
         serialize_enum(\"{name}\", self.json_name(), self.to_i32(), s)\n    \
         }}\n}}\n\n"
    ));

    if let Some((first, _)) = usable.first() {
        out.push_str(&format!(
            "impl Default for {name} {{\n    fn default() -> Self {{ {name}::{first} }}\n}}\n\n"
        ));
    }
    json_names
}

/// A `*_Flags` field is a bitfield: `flags.csv` gives the order of the bits and
/// liblcf packs them from the least significant one, skipping the 2003 ones.
fn emit_flags(out: &mut String, structure: &str, fields: &[String]) {
    let name = format!("{}Flags", type_ident(structure));
    out.push_str(&format!(
        "/// Generated from `flags.csv`: the order of the fields **is** the order\n\
         /// of the bits, from the least significant one upwards.\n\
         #[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]\n\
         pub struct {name} {{\n"
    ));
    for f in fields {
        out.push_str(&format!("    pub {}: bool,\n", field_ident(f)));
    }
    out.push_str("}\n\n");
    out.push_str(&format!("impl {name} {{\n"));
    out.push_str("    pub fn read(d: &[u8]) -> Self {\n");
    out.push_str(if fields.is_empty() {
        "        let f = Self::default();\n"
    } else {
        "        let mut f = Self::default();\n"
    });
    for (i, c) in fields.iter().enumerate() {
        out.push_str(&format!("        f.{} = bit(d, {i});\n", field_ident(c)));
    }
    out.push_str("        f\n    }\n");
    out.push_str("    pub fn write(&self) -> Vec<u8> {\n");
    out.push_str(&format!(
        "        let {}b = vec![0u8; {}];\n",
        if fields.is_empty() { "" } else { "mut " },
        (fields.len() + 7) / 8
    ));
    for (i, c) in fields.iter().enumerate() {
        out.push_str(&format!(
            "        if self.{} {{ b[{}] |= 1 << {}; }}\n",
            field_ident(c),
            i / 8,
            i % 8
        ));
    }
    out.push_str("        b\n    }\n}\n\n");
}

fn emit_struct(
    out: &mut String,
    structure: &str,
    fields: &[&Field],
    enums: &BTreeMap<String, Vec<(String, i64)>>,
    structs: &[StructDef],
) {
    let name = type_ident(structure);
    let with_id = structs.iter().any(|s| s.name == structure && s.with_id);
    // The `= <value>` on every field is the default the CSV declares, and it is
    // the only thing that decides which field is omitted when writing: a
    // misplaced default is a different file (and, before this, an enemy with 1
    // HP). It sits next to the field instead of in a separate `impl Default`
    // because written in two places the two can drift apart with nothing
    // warning about it; `schema_struct!` builds the `Default` from here.
    //
    // The `#[serde(default)]` goes on the struct and not on each field on
    // purpose: that way a JSON missing a field takes it from that `Default`
    // —the CSV's— and not from the zero of the type. Field by field, a missing
    // `max_hp` would go back to being 0 instead of 10.
    //
    // `Serialize` is **not** in the derive list: `schema_struct!` writes it, so
    // that a field holding its default is left out of the JSON the same way the
    // binary leaves out its chunk. See the macro for why it cannot be an
    // attribute.
    out.push_str(&format!(
        "schema_struct! {{\n\
         /// Generated from `fields.csv`.\n\
         #[derive(Debug, Clone, PartialEq, Deserialize)]\n\
         #[serde(default)]\n\
         pub struct {name} {{\n"
    ));
    if with_id {
        out.push_str("    /// The number the array names this element with.\n");
        out.push_str("    pub id: i32 = 0,\n");
    }
    for c in visible(fields) {
        let e = enc(&c.ty, enums, &enum_name(c, enums));
        out.push_str(&format!(
            "    /// field {:#04x} of the binary{}\n",
            c.index,
            if c.persist {
                ", stored even when it holds the default"
            } else {
                ""
            }
        ));
        // A field the CSV declares no default for still carries one written
        // out: left implicit it would fall back to the zero of the type.
        out.push_str(&format!(
            "    pub {}: {} = {},\n",
            field_ident(&c.name),
            rust_type(&e),
            default_value(&c.default, &e)
        ));
    }
    // A chunk the schema does not name is kept raw and goes back to the file in
    // its place. Without this, any field liblcf does not know —or that belongs
    // to 2003— would silently break the round trip.
    //
    // It needs no `skip_serializing_if`: an empty list is this field's default,
    // and the macro's `Serialize` already leaves out whatever holds it.
    out.push_str(
        "    /// The chunks the schema does not name, so the round trip is exact.\n\
         \x20   pub unknown: Vec<RawChunk> = Vec::new(),\n}\n}\n\n",
    );
}

/// The fields that exist as a Rust field: the `f` ones and the positional ones
/// of the raw structs. The `t` ones are the length of another field, which in
/// Rust the `Vec` itself carries, but in the binary they take their own chunk.
fn visible<'a>(fields: &'a [&'a Field]) -> impl Iterator<Item = &'a &'a Field> {
    fields.iter().filter(|c| c.kind != "t")
}

fn default_value(default: &str, e: &Enc) -> String {
    let d = default.trim();
    match e {
        Enc::Bool => {
            if d == "True" {
                "true".into()
            } else {
                "false".into()
            }
        }
        Enc::Ber | Enc::U8 | Enc::I8 | Enc::U32 => {
            let v = d.split('|').next().unwrap_or("0");
            if v.is_empty() {
                "0".into()
            } else {
                v.to_string()
            }
        }
        Enc::F64 => {
            let v = d.split('|').next().unwrap_or("0.0");
            if v.is_empty() {
                "0.0".into()
            } else {
                v.to_string()
            }
        }
        // The sentinel a save file uses to say "use the name the LDB carries".
        // `constants.csv` declares it as `"\x1"`.
        Enc::Text if d == "kEmptyName" => "\"\\u{1}\".to_string()".into(),
        // A text default is written in the CSV as the C++ literal, quotes and
        // all: `Music,name` holds `"(OFF)"` and the name is the five characters
        // inside. Quoting it again would make the default seven characters
        // long, which is a value no file can ever hold, so the field would
        // never be recognised as holding its default.
        Enc::Text => format!("{:?}.to_string()", d.strip_prefix('"')
            .and_then(|d| d.strip_suffix('"')).unwrap_or(d)),
        Enc::Enum(n) => {
            if d.is_empty() {
                format!("{n}::default()")
            } else if let Ok(v) = d.split('|').next().unwrap_or("").parse::<i32>() {
                format!("{n}::from_i32({v})")
            } else {
                format!("{n}::default()")
            }
        }
        Enc::VecU8 | Enc::VecI16 | Enc::VecI32 | Enc::VecU32 | Enc::VecBool => list(d),
        _ => "Default::default()".into(),
    }
}

/// The list defaults the CSV uses: `[1]`, `[1]*162`, `[31]+[15]*143`.
fn list(d: &str) -> String {
    if d.is_empty() {
        return "Vec::new()".into();
    }
    // The CSV has one default written as a Python comprehension:
    // `[x for x in range(0, 144)]`, that is 0..144.
    if let Some(r) = d.strip_prefix("[x for x in range(") {
        let inner = r.trim_end_matches(')').trim_end_matches("]").trim_end_matches(')');
        let mut it = inner.split(',').map(|x| x.trim());
        let a = it.next().unwrap_or("0");
        let b = it.next().unwrap_or("0");
        return format!("({a}..{b}).collect()");
    }
    let mut parts = Vec::new();
    for piece in d.split('+') {
        let piece = piece.trim();
        let (body, times) = match piece.split_once('*') {
            Some((a, b)) => (a.trim(), b.trim().parse::<usize>().unwrap_or(1)),
            None => (piece, 1),
        };
        let value = body.trim_start_matches('[').trim_end_matches(']');
        parts.push(format!("vec![{value}; {times}]"));
    }
    if parts.len() == 1 {
        parts.pop().unwrap()
    } else {
        format!("[{}].concat()", parts.join(", "))
    }
}

fn emit_codec(
    out: &mut String,
    def: &StructDef,
    fields: &[&Field],
    enums: &BTreeMap<String, Vec<(String, i64)>>,
    structs: &[StructDef],
) {
    let name = type_ident(&def.name);
    // The trailing 0 closes a struct. liblcf warns that giving one to
    // `Database` or to `Save` breaks RPG_RT's parser, so those two go without.
    let terminator = !matches!(def.name.as_str(), "Database" | "Save");
    out.push_str(&format!(
        "impl Chunked for {name} {{\n\
         \x20   const NAME: &'static str = \"{name}\";\n\
         \x20   const TERMINATOR: bool = {terminator};\n\
         \x20   const WITH_ID: bool = {};\n\
         \x20   fn id(&self) -> i32 {{ {} }}\n\
         \x20   fn set_id(&mut self, v: i32) {{ {} }}\n\
         \x20   fn unknown_mut(&mut self) -> &mut Vec<RawChunk> {{ &mut self.unknown }}\n",
        def.with_id,
        if def.with_id { "self.id" } else { "0" },
        if def.with_id { "self.id = v;" } else { "let _ = v;" },
    ));

    // --- read ---
    out.push_str("    fn read_chunk(&mut self, id: u32, d: &[u8]) -> Result<bool> {\n        match id {\n");
    for c in fields {
        if c.kind == "t" {
            out.push_str(&format!(
                "            {:#04x} => {{}} // length of `{}`, recomputed when writing\n",
                c.index, c.name
            ));
            continue;
        }
        let e = enc(&c.ty, enums, &enum_name(c, enums));
        out.push_str(&format!(
            "            {:#04x} => self.{} = {},\n",
            c.index,
            field_ident(&c.name),
            read_expr(&e)
        ));
    }
    out.push_str("            _ => return Ok(false),\n        }\n        Ok(true)\n    }\n");

    // --- write ---
    out.push_str("    fn write_chunks(&self, e: &mut Writer) -> Result<()> {\n");
    out.push_str(&format!("        let p = {name}::default();\n"));
    out.push_str("        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();\n");
    let mut i = 0;
    while i < fields.len() {
        let c = fields[i];
        if c.kind == "t" {
            // The length chunk goes before the data one, and comes from it.
            let data = fields
                .iter()
                .find(|o| o.kind != "t" && o.name == c.name)
                .expect("a `t` field with no `f`");
            let e = enc(&data.ty, enums, &enum_name(data, enums));
            let field = field_ident(&data.name);
            out.push_str(&format!(
                "        let v_{field} = {};\n",
                write_expr(&e, &format!("self.{field}"))
            ));
            if c.ty.starts_with("Count<") {
                // `Count` stores the number of elements, not the bytes.
                out.push_str(&format!(
                    "        {}c.push(({:#04x}, enc_ber(self.{field}.len() as i32)));{}\n",
                    if c.persist {
                        String::new()
                    } else {
                        format!("if self.{field}.len() != p.{field}.len() {{ ")
                    },
                    c.index,
                    if c.persist { "" } else { " }" },
                ));
            } else {
                out.push_str(&format!(
                    "        {}c.push(({:#04x}, enc_ber(v_{field}.len() as i32)));{}\n",
                    if c.persist {
                        String::new()
                    } else {
                        format!(
                            "if v_{field}.len() != {}.len() {{ ",
                            write_expr(&e, &format!("p.{field}"))
                        )
                    },
                    c.index,
                    if c.persist { "" } else { " }" },
                ));
            }
            out.push_str(&format!(
                "        {}c.push(({:#04x}, v_{field}));{}\n",
                if data.persist {
                    String::new()
                } else {
                    format!("if self.{field} != p.{field} {{ ")
                },
                data.index,
                if data.persist { "" } else { " }" },
            ));
            i += 1;
            // The data field was already emitted here; skip it when its turn comes.
            continue;
        }
        // Was it already emitted by its length chunk?
        if fields[..i].iter().any(|o| o.kind == "t" && o.name == c.name) {
            i += 1;
            continue;
        }
        let e = enc(&c.ty, enums, &enum_name(c, enums));
        let field = field_ident(&c.name);
        out.push_str(&format!(
            "        {}c.push(({:#04x}, {}));{}\n",
            if c.persist {
                String::new()
            } else {
                format!("if self.{field} != p.{field} {{ ")
            },
            c.index,
            write_expr(&e, &format!("self.{field}")),
            if c.persist { "" } else { " }" },
        ));
        i += 1;
    }
    out.push_str("        e.dump(c, &self.unknown);\n        Ok(())\n    }\n}\n\n");
    let _ = structs;
}

fn read_expr(e: &Enc) -> String {
    match e {
        Enc::Ber => "dec_ber(d)".into(),
        Enc::Bool => "dec_bool(d)".into(),
        Enc::U8 => "dec_u8(d)".into(),
        Enc::U32 => "dec_u32(d)".into(),
        Enc::I8 => "dec_i8(d)".into(),
        Enc::F64 => "dec_f64(d)".into(),
        Enc::Text => "dec_text(d)".into(),
        Enc::VecU8 => "d.to_vec()".into(),
        Enc::VecI16 => "dec_vec_i16(d)".into(),
        Enc::VecI32 => "dec_vec_i32(d)".into(),
        Enc::VecU32 => "dec_vec_u32(d)".into(),
        Enc::VecBool => "dec_vec_bool(d)".into(),
        Enc::Enum(n) => format!("{n}::from_i32(dec_ber(d))"),
        Enc::Flags(n) => format!("{n}::read(d)"),
        Enc::Struct(n) => format!("dec_struct::<{n}>(d)?"),
        Enc::Raw(n) => format!("{n}::read_raw(d)?"),
        Enc::Array(n) => format!("dec_array::<{n}>(d)?"),
        Enc::EventCommands => "dec_event_commands(d)?".into(),
        Enc::MoveCommands => "dec_move_commands(d)?".into(),
    }
}

fn write_expr(e: &Enc, v: &str) -> String {
    match e {
        Enc::Ber => format!("enc_ber({v})"),
        Enc::Bool => format!("enc_bool({v})"),
        Enc::U8 => format!("vec![{v}]"),
        Enc::U32 => format!("enc_u32({v})"),
        Enc::I8 => format!("vec![{v} as u8]"),
        Enc::F64 => format!("enc_f64({v})"),
        Enc::Text => format!("enc_text(&{v})"),
        Enc::VecU8 => format!("{v}.clone()"),
        Enc::VecI16 => format!("enc_vec_i16(&{v})"),
        Enc::VecI32 => format!("enc_vec_i32(&{v})"),
        Enc::VecU32 => format!("enc_vec_u32(&{v})"),
        Enc::VecBool => format!("enc_vec_bool(&{v})"),
        Enc::Enum(_) => format!("enc_ber({v}.to_i32())"),
        Enc::Flags(_) => format!("{v}.write()"),
        Enc::Struct(_) => format!("enc_struct(&{v})?"),
        Enc::Raw(_) => format!("{v}.write_raw()"),
        Enc::Array(_) => format!("enc_array(&{v})?"),
        Enc::EventCommands => format!("enc_event_commands(&{v})"),
        Enc::MoveCommands => format!("enc_move_commands(&{v})"),
    }
}

// --- Names ----------------------------------------------------------------

fn capitalize(s: &str) -> String {
    s.split('_')
        .map(|p| {
            let mut c = p.chars();
            match c.next() {
                Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
                None => String::new(),
            }
        })
        .collect()
}

/// A valid Rust identifier, in CamelCase.
fn type_ident(s: &str) -> String {
    let clean: String = s
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '_' })
        .collect();
    let camel = capitalize(&clean);
    if camel.chars().next().map(|c| c.is_numeric()).unwrap_or(true) {
        return format!("N{camel}");
    }
    // `Self`, `crate` and `super` cannot be escaped with `r#`, not even as
    // variants, so they get a trailing underscore. The `#[serde(rename)]`
    // keeps the original name in the JSON, which is what gets read.
    match camel.as_str() {
        "Self" | "Crate" | "Super" => format!("{camel}_"),
        _ => camel,
    }
}

/// A field name: snake_case and not clashing with Rust's keywords.
fn field_ident(s: &str) -> String {
    let clean: String = s
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '_' })
        .collect();
    match clean.as_str() {
        "type" | "move" | "ref" | "box" | "loop" | "match" | "final" | "self" | "super" => {
            format!("r#{clean}")
        }
        _ => clean,
    }
}

// --- The description ------------------------------------------------------

/// Emits `description.rs`: the same schema, as data one can hand to someone
/// who is not Rust.
///
/// Why it exists: the JSON Ditto writes **omits every field holding its
/// default** and stores enums **by name**, so reading that JSON without the
/// defaults and the enum tables is reading it wrong. Whoever reads it needs
/// them, and the one that has them is this generator. Published here they are
/// data; scraped out of the generated Rust —which is how it used to be done—
/// they are a guess about someone else's source code.
fn emit_description(
    out: &mut String,
    by_structure: &BTreeMap<&str, Vec<&Field>>,
    enums: &BTreeMap<String, Vec<(String, i64)>>,
    enum_names: &BTreeMap<String, Vec<(String, i64)>>,
    structs: &[StructDef],
    constants: &[(String, String)],
) {
    let consts = constant_values(constants);
    let known: BTreeSet<String> = by_structure.keys().map(|s| type_ident(s)).collect();

    out.push_str(
        "//! The schema as data: what `ditto schema` writes out.\n\
         //!\n\
         //! **Generated by `cargo xtask generate`, and committed on purpose**,\n\
         //! in the same run that writes `mod.rs` so that the two cannot drift.\n\
         //! It is not edited by hand.\n\
         //!\n\
         //! Each field carries what a reader of the JSON needs and cannot see\n\
         //! in the JSON itself: the chunk it is in the binary, the default it\n\
         //! holds when it is absent, the enum whose names its values are, and\n\
         //! the struct it nests.\n\
         \n\
         #![allow(dead_code)]\n\
         \n\
         /// A field of a schema struct.\n\
         pub struct FieldDesc {\n\
         \x20   pub name: &'static str,\n\
         \x20   /// Its chunk in the binary. `None` for `id`, which the array\n\
         \x20   /// carries in front of the element instead of in a chunk.\n\
         \x20   pub chunk: Option<u32>,\n\
         \x20   /// What the field holds when the JSON leaves it out, as JSON\n\
         \x20   /// itself. `None` means the default of the type: an empty list,\n\
         \x20   /// or a struct all in default.\n\
         \x20   pub default: Option<&'static str>,\n\
         \x20   /// The enum its value is a name of, if it is one.\n\
         \x20   pub enumeration: Option<&'static str>,\n\
         \x20   /// `PersistIfDefault`: the binary writes this chunk even when it\n\
         \x20   /// holds the default. The JSON omits it like any other, and that\n\
         \x20   /// is the only difference in presence between the two.\n\
         \x20   pub persist: bool,\n\
         \x20   /// The struct it carries inside, one or a list of them.\n\
         \x20   pub nested: Option<&'static str>,\n\
         }\n\
         \n\
         /// Every struct of the schema, with its fields in the order of the\n\
         /// chunks.\n\
         pub static STRUCTS: &[(&str, &[FieldDesc])] = &[\n",
    );
    for (structure, fields) in by_structure {
        let name = type_ident(structure);
        let with_id = structs.iter().any(|s| &s.name == structure && s.with_id);
        out.push_str(&format!("    (\"{name}\", &[\n"));
        if with_id {
            out.push_str(
                "        FieldDesc { name: \"id\", chunk: None, default: Some(\"0\"), \
                 enumeration: None, persist: false, nested: None },\n",
            );
        }
        for c in visible(fields) {
            let e = enc(&c.ty, enums, &enum_name(c, enums));
            let field = field_ident(&c.name).replace("r#", "");
            let default = match json_default(&c.default, &e, &consts, enum_names) {
                Some(v) => format!("Some({v:?})"),
                None => "None".to_string(),
            };
            let enumeration = match &e {
                Enc::Enum(n) => format!("Some({n:?})"),
                _ => "None".to_string(),
            };
            let nested = match nested_struct(&e) {
                Some(n) if known.contains(&n) => format!("Some({n:?})"),
                _ => "None".to_string(),
            };
            out.push_str(&format!(
                "        FieldDesc {{ name: {field:?}, chunk: Some({:#04x}), \
                 default: {default}, enumeration: {enumeration}, persist: {}, \
                 nested: {nested} }},\n",
                c.index, c.persist
            ));
        }
        out.push_str("    ]),\n");
    }
    out.push_str("];\n\n");

    out.push_str(
        "/// Every enum, by the name each value travels under in the JSON.\n\
         pub static ENUMS: &[(&str, &[(&str, i32)])] = &[\n",
    );
    for (name, variants) in enum_names {
        out.push_str(&format!("    (\"{name}\", &[\n"));
        for (variant, value) in variants {
            out.push_str(&format!("        ({variant:?}, {value}),\n"));
        }
        out.push_str("    ]),\n");
    }
    out.push_str("];\n");
}

/// The struct a field carries inside, if it carries one.
fn nested_struct(e: &Enc) -> Option<String> {
    match e {
        Enc::Struct(n) | Enc::Raw(n) | Enc::Array(n) => Some(n.clone()),
        Enc::EventCommands => Some("EventCommand".to_string()),
        Enc::MoveCommands => Some("MoveCommand".to_string()),
        _ => None,
    }
}

/// `constants.csv` written as numbers. The expressions it uses are three:
/// a literal, `a * b` and `a << b`.
fn constant_values(constants: &[(String, String)]) -> BTreeMap<String, i64> {
    let mut out = BTreeMap::new();
    for (name, expr) in constants {
        let expr = expr.trim();
        let value = if let Some((a, b)) = expr.split_once('*') {
            number(a) * number(b)
        } else if let Some((a, b)) = expr.split_once("<<") {
            number(a) << number(b)
        } else if let Ok(v) = expr.parse::<i64>() {
            v
        } else {
            continue; // not a number: `kEmptyName` is a string, and is handled apart
        };
        out.insert(name.clone(), value);
    }
    out
}

fn number(s: &str) -> i64 {
    s.trim()
        .parse::<i64>()
        .unwrap_or_else(|_| panic!("a number I cannot read: {s:?}"))
}

/// The default of a field as JSON, or `None` for the default of the type.
///
/// It mirrors `default_value`, which writes the same thing as a Rust
/// expression, and the two are kept next to each other for that reason.
fn json_default(
    default: &str,
    e: &Enc,
    consts: &BTreeMap<String, i64>,
    enum_names: &BTreeMap<String, Vec<(String, i64)>>,
) -> Option<String> {
    let d = default.trim();
    match e {
        Enc::Bool => Some(if d == "True" { "true".into() } else { "false".into() }),
        Enc::Ber | Enc::U8 | Enc::I8 | Enc::U32 => {
            let v = d.split('|').next().unwrap_or("0");
            Some(json_number(v, consts))
        }
        Enc::F64 => {
            let v = d.split('|').next().unwrap_or("");
            if v.is_empty() {
                Some("0.0".into())
            } else {
                Some(v.to_string())
            }
        }
        // The same sentinel `default_value` writes as `"\u{1}"`.
        Enc::Text if d == "kEmptyName" => Some("\"\\u0001\"".into()),
        Enc::Text => Some(json_string(
            d.strip_prefix('"')
                .and_then(|d| d.strip_suffix('"'))
                .unwrap_or(d),
        )),
        Enc::Enum(n) => {
            let v = d.split('|').next().unwrap_or("");
            match v.parse::<i64>() {
                Ok(v) => Some(v.to_string()),
                // No default declared: the enum's own, which is its first
                // variant —that is what `impl Default` emits.
                Err(_) => enum_names
                    .get(n)
                    .and_then(|vs| vs.first())
                    .map(|(_, value)| value.to_string()),
            }
        }
        Enc::VecU8 | Enc::VecI16 | Enc::VecI32 | Enc::VecU32 | Enc::VecBool => json_list(d),
        _ => None,
    }
}

fn json_number(v: &str, consts: &BTreeMap<String, i64>) -> String {
    let v = v.trim();
    if v.is_empty() {
        return "0".into();
    }
    if let Ok(n) = v.parse::<i64>() {
        return n.to_string();
    }
    match consts.get(v) {
        Some(n) => n.to_string(),
        None => panic!("fields.csv has a default I cannot turn into a number: {v:?}"),
    }
}

fn json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// The same list defaults `list` reads —`[1]`, `[1]*162`, `[31]+[15]*143`—,
/// written out element by element.
fn json_list(d: &str) -> Option<String> {
    let d = d.trim();
    if d.is_empty() {
        return None;
    }
    let mut items: Vec<String> = Vec::new();
    if let Some(r) = d.strip_prefix("[x for x in range(") {
        let inner = r.trim_end_matches(']').trim_end_matches(')');
        let mut it = inner.split(',').map(|x| x.trim());
        let a: i64 = number(it.next().unwrap_or("0"));
        let b: i64 = number(it.next().unwrap_or("0"));
        items.extend((a..b).map(|v| v.to_string()));
    } else {
        for piece in d.split('+') {
            let piece = piece.trim();
            let (body, times) = match piece.split_once('*') {
                Some((a, b)) => (a.trim(), b.trim().parse::<usize>().unwrap_or(1)),
                None => (piece, 1),
            };
            let value = body.trim_start_matches('[').trim_end_matches(']').trim();
            for _ in 0..times {
                items.push(value.to_string());
            }
        }
    }
    Some(format!("[{}]", items.join(",")))
}
