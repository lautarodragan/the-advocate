//! Genera `src/esquema/` desde las tablas CSV de liblcf.
//!
//! No corre en el build: se llama a mano, y **lo que produce se commitea**.
//!
//!     cargo xtask generar --liblcf /extras/ref/liblcf
//!
//! La razón de que sea explícito y no un `build.rs` es que el código generado
//! es la fuente de verdad de este proyecto: si liblcf renombra un campo, el
//! diff tiene que decir exactamente eso —un nombre que cambia en el struct que
//! corresponde— y pasar por una revisión como cualquier otro cambio. Un paso
//! oculto del build daría el mismo resultado sin que nadie lo mire.
//!
//! Conceptualmente el CSV es una dependencia de Ditto y esto es lo que corre
//! al subirle la versión.
//!
//! # Qué emite
//!
//! Tres cosas, y las tres salen del CSV y de ningún criterio nuestro:
//!
//! * los **structs** y los **enums**, con los nombres de liblcf;
//! * el **default de cada campo**, con el valor que la columna `Default Value`
//!   declara —acá estaba el `max_hp` que valía 1 y vale 10—, escrito **una
//!   sola vez y al lado del campo**: `esquema_struct!` arma el `Default` desde
//!   ahí, y el `#[serde(default)]` del struct lo usa para el JSON;
//! * el **códec**: qué campo es qué chunk, cómo se codifica, y si se emite
//!   cuando vale el default (la columna `PersistIfDefault`).
//!
//! Lo que **no** se genera son los seis structs que liblcf lee a mano
//! (`RawStruct`): `Parameters`, `Equipment`, `Rect`, `EventCommand`,
//! `MoveCommand` y `TreeMap`. El CSV les declara los campos pero no los
//! índices de chunk, porque no los tienen: van posicionales. Sus códecs están
//! escritos a mano en `src/crudos.rs`.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

/// Una fila de `fields.csv`.
#[derive(Clone)]
struct Campo {
    estructura: String,
    nombre: String,
    /// `f` es un campo común; `t` es el largo de un vector, que va en su propio
    /// chunk; vacío es un campo posicional de un struct crudo.
    clase: String,
    tipo: String,
    indice: u32,
    default: String,
    /// Si el binario guarda el campo aunque valga el default.
    persiste: bool,
    /// Los campos que sólo existen en RPG Maker 2003: este port es de 2000.
    es_2k3: bool,
}

/// Una fila de `structs.csv`.
struct Estructura {
    /// `ldb`, `lmu`, `lmt` o `lsd`.
    archivo: String,
    nombre: String,
    /// Si cada elemento del array lleva su ID adelante.
    con_id: bool,
}

/// Los structs que liblcf lee a mano porque no son chunk-based.
const CRUDOS: &[&str] = &[
    "Parameters",
    "Equipment",
    "Rect",
    "EventCommand",
    "MoveCommand",
    "TreeMap",
];

fn main() {
    let mut args = std::env::args().skip(1);
    let orden = args.next().unwrap_or_default();
    if orden != "generar" {
        eprintln!("uso: cargo xtask generar --liblcf <ruta a liblcf>");
        std::process::exit(2);
    }
    let mut liblcf = PathBuf::from("/extras/ref/liblcf");
    let mut salida = PathBuf::from("src/esquema");
    while let Some(a) = args.next() {
        match a.as_str() {
            "--liblcf" => liblcf = PathBuf::from(args.next().expect("--liblcf pide una ruta")),
            "--salida" => salida = PathBuf::from(args.next().expect("--salida pide una ruta")),
            otro => panic!("no entiendo {otro:?}"),
        }
    }
    let csv = liblcf.join("generator/csv");
    let campos = leer_campos(&csv.join("fields.csv"));
    let enums = leer_enums(&csv.join("enums.csv"));
    let banderas = leer_banderas(&csv.join("flags.csv"));
    let estructuras = leer_estructuras(&csv.join("structs.csv"));
    let constantes = leer_constantes(&csv.join("constants.csv"));

    // El orden del CSV **es** el orden de los chunks en el archivo: liblcf
    // escribe los campos en el orden en que los declara la tabla, y el
    // generador de allá hasta avisa por stderr si un índice sale del orden
    // ascendente. Así que acá se conserva tal cual.
    let mut por_estructura: BTreeMap<&str, Vec<&Campo>> = BTreeMap::new();
    for c in &campos {
        if c.es_2k3 {
            continue; // este port es de RPG Maker 2000
        }
        por_estructura.entry(&c.estructura).or_default().push(c);
    }

    let mut texto = String::new();
    cabecera(&mut texto, &liblcf);
    for (nombre, valor) in &constantes {
        texto.push_str(&format!(
            "/// Generado desde `constants.csv`.\n#[allow(non_upper_case_globals)]\npub const {nombre}: i32 = {valor};\n\n"
        ));
    }
    for (nombre, variantes) in &enums {
        emitir_enum(&mut texto, nombre, variantes);
    }
    for (estructura, campos) in &banderas {
        emitir_banderas(&mut texto, estructura, campos);
    }
    for (estructura, campos) in &por_estructura {
        emitir_struct(&mut texto, estructura, campos, &enums, &estructuras);
    }
    let mut con_codec = 0;
    for e in &estructuras {
        // El códec sólo para lo que Ditto lee hoy. `.lsd` —las partidas
        // guardadas— tiene los structs pero no el lector: no está en el
        // corpus con el que se mide la ida y vuelta, y sin eso no habría con
        // qué comprobarlo.
        if e.archivo == "lsd" || CRUDOS.contains(&e.nombre.as_str()) {
            continue;
        }
        let Some(campos) = por_estructura.get(e.nombre.as_str()) else {
            continue;
        };
        emitir_codec(&mut texto, e, campos, &enums, &estructuras);
        con_codec += 1;
    }

    fs::create_dir_all(&salida).expect("no pude crear el directorio de salida");
    let destino = salida.join("mod.rs");
    fs::write(&destino, texto).expect("no pude escribir el esquema");
    println!(
        "{} estructuras ({} con códec), {} enums y {} juegos de banderas -> {}",
        por_estructura.len(),
        con_codec,
        enums.len(),
        banderas.len(),
        destino.display()
    );
}

fn cabecera(out: &mut String, liblcf: &Path) {
    out.push_str(&format!(
        "//! El esquema de los archivos de RPG Maker 2000, y su códec.\n\
         //!\n\
         //! **Generado por `cargo xtask generar`, y commiteado a propósito.**\n\
         //! No se edita a mano: lo que se edita es el generador o el CSV de\n\
         //! arriba. Ver `xtask/src/main.rs` para el porqué.\n\
         //!\n\
         //! Sale de las tablas de liblcf ({}), que es de donde el ecosistema\n\
         //! entero saca los nombres: en el binario no hay ninguno, sólo\n\
         //! índices de campo.\n\
         //!\n\
         //! Cada campo lleva su default al lado (`= 10`): es lo que rellena al\n\
         //! leer y lo que decide omitir al escribir, y `esquema_struct!` arma\n\
         //! el `Default` con eso. Ver `crate::lcf::esquema_struct`.\n\
         \n\
         #![allow(dead_code, unused_variables, clippy::all)]\n\
         \n\
         use crate::lcf::*;\n\
         use serde::{{Deserialize, Serialize}};\n\n",
        liblcf.display()
    ));
}

// --- Lectura de los CSV ---------------------------------------------------

/// Un CSV con comillas: `fields.csv` las usa para los defaults que llevan
/// comas o comillas adentro (`"(OFF)"`, `Sound{ "" }`).
fn filas(texto: &str) -> Vec<Vec<String>> {
    let mut fuera = Vec::new();
    for linea in texto.lines() {
        let mut celdas = Vec::new();
        let mut actual = String::new();
        let mut entre_comillas = false;
        let mut chars = linea.chars().peekable();
        while let Some(c) = chars.next() {
            match c {
                '"' if entre_comillas && chars.peek() == Some(&'"') => {
                    actual.push('"');
                    chars.next();
                }
                '"' => entre_comillas = !entre_comillas,
                ',' if !entre_comillas => celdas.push(std::mem::take(&mut actual)),
                otro => actual.push(otro),
            }
        }
        celdas.push(actual);
        fuera.push(celdas);
    }
    fuera
}

fn leer_campos(ruta: &Path) -> Vec<Campo> {
    let texto = fs::read_to_string(ruta).expect("no encontré fields.csv");
    let mut salida = Vec::new();
    for (n, c) in filas(&texto).into_iter().enumerate() {
        if n == 0 || c.len() < 8 || c[0].is_empty() || c[1].is_empty() {
            continue;
        }
        let indice = if c[4].is_empty() {
            0
        } else {
            u32::from_str_radix(c[4].trim_start_matches("0x"), 16).expect("índice raro")
        };
        salida.push(Campo {
            estructura: c[0].clone(),
            nombre: c[1].clone(),
            clase: c[2].clone(),
            tipo: c[3].clone(),
            indice,
            default: c[5].clone(),
            persiste: c[6] == "1",
            es_2k3: c[7] == "1",
        });
    }
    salida
}

/// `enums.csv`: Structure, Entry, Value, Index.
fn leer_enums(ruta: &Path) -> BTreeMap<String, Vec<(String, i64)>> {
    let texto = fs::read_to_string(ruta).expect("no encontré enums.csv");
    let mut fuera: BTreeMap<String, Vec<(String, i64)>> = BTreeMap::new();
    for (n, c) in filas(&texto).into_iter().enumerate() {
        if n == 0 || c.len() < 4 || c[0].is_empty() {
            continue;
        }
        let Ok(indice) = c[3].trim().parse::<i64>() else {
            continue;
        };
        fuera
            .entry(format!("{}{}", c[0], mayuscula(&c[1])))
            .or_default()
            .push((c[2].clone(), indice));
    }
    fuera
}

/// `flags.csv`: Structure, Field, Is2k3. El orden **es** el orden de los bits.
fn leer_banderas(ruta: &Path) -> BTreeMap<String, Vec<String>> {
    let texto = fs::read_to_string(ruta).expect("no encontré flags.csv");
    let mut fuera: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for (n, c) in filas(&texto).into_iter().enumerate() {
        if n == 0 || c.len() < 3 || c[0].is_empty() {
            continue;
        }
        // Las banderas de 2003 no se escriben en un archivo de 2000, y el bit
        // que ocupan tampoco: liblcf las saltea al empaquetar.
        if c[2] == "1" {
            fuera.entry(c[0].clone()).or_default();
            continue;
        }
        fuera.entry(c[0].clone()).or_default().push(c[1].clone());
    }
    fuera
}

/// `constants.csv`: los pocos valores con nombre que el CSV usa como default.
/// Sólo los enteros: el único que no lo es (`kEmptyName`) se resuelve aparte.
fn leer_constantes(ruta: &Path) -> Vec<(String, String)> {
    let texto = fs::read_to_string(ruta).expect("no encontré constants.csv");
    let mut fuera = Vec::new();
    for (n, c) in filas(&texto).into_iter().enumerate() {
        if n == 0 || c.len() < 4 || c[1].is_empty() || c[2] != "int" {
            continue;
        }
        fuera.push((c[1].clone(), c[3].clone()));
    }
    fuera
}

fn leer_estructuras(ruta: &Path) -> Vec<Estructura> {
    let texto = fs::read_to_string(ruta).expect("no encontré structs.csv");
    let mut fuera = Vec::new();
    for (n, c) in filas(&texto).into_iter().enumerate() {
        if n == 0 || c.len() < 4 || c[0].is_empty() {
            continue;
        }
        fuera.push(Estructura {
            archivo: c[0].clone(),
            nombre: c[1].clone(),
            con_id: c[3] == "1",
        });
    }
    fuera
}

// --- Tipos ----------------------------------------------------------------

/// Cómo se codifica un campo en el binario.
#[derive(Clone, PartialEq)]
enum Cod {
    /// Entero BER: 7 bits por byte, el bit alto dice que sigue.
    Ber,
    Enum(String),
    Bandera(String),
    Bool,
    U8,
    I8,
    F64,
    Texto,
    VecU8,
    VecI16,
    /// `Vector<Int32>`: cuatro bytes crudos por elemento, **no** BER.
    VecI32,
    VecU32,
    /// Un byte por bool, tanto `Vector<Boolean>` como `DBBitArray`.
    VecBool,
    /// Cuatro bytes crudos: sólo `Rect`, que va posicional.
    U32,
    /// Un struct chunk-based anidado.
    Struct(String),
    /// `count` + por elemento `id` + struct.
    Array(String),
    /// Los tres que liblcf lee a mano dentro de un chunk.
    Crudo(String),
    ComandosEvento,
    ComandosRuta,
}

fn cod(tipo: &str, enums: &BTreeMap<String, Vec<(String, i64)>>, nombre_enum: &str) -> Cod {
    match tipo {
        "Int32" | "DatabaseVersion" => Cod::Ber,
        "UInt32" => Cod::U32,
        // Los parámetros de un comando de evento: enteros BER, pero en Rust un
        // Vec y nada más. Su códec es posicional y está a mano.
        "DBArray<Int32>" => Cod::VecI32,
        "Boolean" => Cod::Bool,
        "UInt8" => Cod::U8,
        "Int8" => Cod::I8,
        "Double" => Cod::F64,
        "String" | "DBString" => Cod::Texto,
        "DBBitArray" | "Vector<Boolean>" => Cod::VecBool,
        "Vector<UInt8>" => Cod::VecU8,
        "Vector<Int16>" => Cod::VecI16,
        "Vector<Int32>" | "Vector<Ref<BattleCommand:Int32>>" => Cod::VecI32,
        "Vector<UInt32>" => Cod::VecU32,
        "Vector<EventCommand>" => Cod::ComandosEvento,
        "Vector<MoveCommand>" => Cod::ComandosRuta,
        t if t.starts_with("Vector<Ref<") => Cod::VecI32,
        t if t.starts_with("Ref<") => Cod::Ber,
        t if t.ends_with("_Flags") => Cod::Bandera(identificador(&t.replace("_Flags", "Flags"))),
        t if t.starts_with("Enum<") => {
            if enums.contains_key(nombre_enum) {
                Cod::Enum(nombre_enum.to_string())
            } else {
                Cod::Ber
            }
        }
        t if t.starts_with("Array<") => {
            let dentro = &t["Array<".len()..t.len() - 1];
            Cod::Array(identificador(dentro.split(':').next().unwrap_or(dentro)))
        }
        otro => {
            let id = identificador(otro);
            if CRUDOS.contains(&id.as_str()) {
                Cod::Crudo(id)
            } else {
                Cod::Struct(id)
            }
        }
    }
}

/// El nombre del enum que le tocaría a este campo, si existe uno.
fn nombre_enum(campo: &Campo, enums: &BTreeMap<String, Vec<(String, i64)>>) -> String {
    // Primero el que declara el tipo, que es lo que manda; si no, el que se
    // arma con Estructura + Campo, que es la convención de `enums.csv`.
    if let Some(dentro) = campo.tipo.strip_prefix("Enum<") {
        let dentro = &dentro[..dentro.len() - 1];
        let (est, cam) = dentro.split_once('_').unwrap_or((dentro, ""));
        let n = format!("{est}{}", mayuscula(cam));
        if enums.contains_key(&n) {
            return n;
        }
    }
    let candidato = format!("{}{}", campo.estructura, mayuscula(&campo.nombre));
    if enums.contains_key(&candidato) {
        return candidato;
    }
    String::new()
}

fn tipo_rust(c: &Cod) -> String {
    match c {
        Cod::Ber => "i32".into(),
        Cod::Enum(n) | Cod::Bandera(n) | Cod::Struct(n) | Cod::Crudo(n) => n.clone(),
        Cod::Bool => "bool".into(),
        Cod::U8 => "u8".into(),
        Cod::I8 => "i8".into(),
        Cod::F64 => "f64".into(),
        Cod::Texto => "String".into(),
        Cod::VecU8 => "Vec<u8>".into(),
        Cod::VecI16 => "Vec<i16>".into(),
        Cod::VecI32 => "Vec<i32>".into(),
        Cod::VecU32 => "Vec<u32>".into(),
        Cod::VecBool => "Vec<bool>".into(),
        Cod::U32 => "u32".into(),
        Cod::Array(n) => format!("Vec<{n}>"),
        Cod::ComandosEvento => "Vec<EventCommand>".into(),
        Cod::ComandosRuta => "Vec<MoveCommand>".into(),
    }
}

// --- Emisión --------------------------------------------------------------

fn emitir_enum(out: &mut String, nombre: &str, variantes: &[(String, i64)]) {
    // `Otro` es el que hace que la ida y vuelta no dependa de que liblcf
    // conozca todos los valores: un número que la tabla no nombra se guarda
    // como número y vuelve igual.
    out.push_str(&format!(
        "/// Generado desde `enums.csv`.\n\
         #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]\n\
         pub enum {nombre} {{\n"
    ));
    let mut vistas = BTreeSet::new();
    let mut usables: Vec<(String, i64)> = Vec::new();
    for (variante, valor) in variantes {
        let id = identificador(variante);
        if !vistas.insert(id.clone()) {
            continue; // el CSV repite alguna con el mismo nombre
        }
        out.push_str(&format!("    #[serde(rename = \"{variante}\")]\n"));
        out.push_str(&format!("    {id},\n"));
        usables.push((id, *valor));
    }
    out.push_str("    /// Un valor que `enums.csv` no nombra. Vuelve al binario tal cual.\n");
    out.push_str("    Otro(i32),\n}\n\n");

    out.push_str(&format!("impl {nombre} {{\n    pub fn a_i32(self) -> i32 {{\n        match self {{\n"));
    let mut valores = BTreeSet::new();
    for (id, valor) in &usables {
        out.push_str(&format!("            {nombre}::{id} => {valor},\n"));
        valores.insert(*valor);
    }
    out.push_str(&format!("            {nombre}::Otro(v) => v,\n        }}\n    }}\n"));
    out.push_str(&format!("    pub fn de_i32(v: i32) -> Self {{\n        match v {{\n"));
    let mut puestos = BTreeSet::new();
    for (id, valor) in &usables {
        if !puestos.insert(*valor) {
            continue; // dos nombres para el mismo número: gana el primero
        }
        out.push_str(&format!("            {valor} => {nombre}::{id},\n"));
    }
    out.push_str(&format!("            v => {nombre}::Otro(v),\n        }}\n    }}\n}}\n\n"));

    if let Some((primera, _)) = usables.first() {
        out.push_str(&format!(
            "impl Default for {nombre} {{\n    fn default() -> Self {{ {nombre}::{primera} }}\n}}\n\n"
        ));
    }
}

/// Un campo `*_Flags` es un bitfield: `flags.csv` da el orden de los bits y
/// liblcf los empaqueta desde el menos significativo, salteando los de 2003.
fn emitir_banderas(out: &mut String, estructura: &str, campos: &[String]) {
    let nombre = format!("{}Flags", identificador(estructura));
    out.push_str(&format!(
        "/// Generado desde `flags.csv`: el orden de los campos **es** el orden\n\
         /// de los bits, del menos significativo para arriba.\n\
         #[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]\n\
         pub struct {nombre} {{\n"
    ));
    for c in campos {
        out.push_str(&format!("    pub {}: bool,\n", identificador_campo(c)));
    }
    out.push_str("}\n\n");
    out.push_str(&format!("impl {nombre} {{\n"));
    out.push_str("    pub fn leer(d: &[u8]) -> Self {\n");
    out.push_str(if campos.is_empty() {
        "        let f = Self::default();\n"
    } else {
        "        let mut f = Self::default();\n"
    });
    for (i, c) in campos.iter().enumerate() {
        out.push_str(&format!(
            "        f.{} = bit(d, {i});\n",
            identificador_campo(c)
        ));
    }
    out.push_str("        f\n    }\n");
    out.push_str("    pub fn escribir(&self) -> Vec<u8> {\n");
    out.push_str(&format!(
        "        let {}b = vec![0u8; {}];\n",
        if campos.is_empty() { "" } else { "mut " },
        (campos.len() + 7) / 8
    ));
    for (i, c) in campos.iter().enumerate() {
        out.push_str(&format!(
            "        if self.{} {{ b[{}] |= 1 << {}; }}\n",
            identificador_campo(c),
            i / 8,
            i % 8
        ));
    }
    out.push_str("        b\n    }\n}\n\n");
}

fn emitir_struct(
    out: &mut String,
    estructura: &str,
    campos: &[&Campo],
    enums: &BTreeMap<String, Vec<(String, i64)>>,
    estructuras: &[Estructura],
) {
    let nombre = identificador(estructura);
    let con_id = estructuras
        .iter()
        .any(|e| e.nombre == estructura && e.con_id);
    // El `= <valor>` de cada campo es el default que declara el CSV, y es lo
    // único que decide qué campo se omite al escribir: un default mal puesto
    // es un archivo distinto (y, antes de esto, un enemigo con 1 de HP). Va
    // pegado al campo y no en un `impl Default` aparte porque escrito en dos
    // lugares se puede separar sin que nada avise; `esquema_struct!` arma el
    // `Default` desde acá.
    //
    // El `#[serde(default)]` va en el struct y no en cada campo a propósito:
    // así un JSON al que le falta un campo lo toma de ese `Default` —el del
    // CSV— y no del cero del tipo. Campo por campo, un `max_hp` que falta
    // volvería a valer 0 en vez de 10.
    out.push_str(&format!(
        "esquema_struct! {{\n\
         /// Generado desde `fields.csv`.\n\
         #[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]\n\
         #[serde(default)]\n\
         pub struct {nombre} {{\n"
    ));
    if con_id {
        out.push_str("    /// El número con el que el array nombra a este elemento.\n");
        out.push_str("    pub id: i32 = 0,\n");
    }
    for c in visibles(campos) {
        let cd = cod(&c.tipo, enums, &nombre_enum(c, enums));
        out.push_str(&format!(
            "    /// campo {:#04x} del binario{}\n",
            c.indice,
            if c.persiste {
                ", se guarda aunque valga el default"
            } else {
                ""
            }
        ));
        // Un campo que el CSV no declara con default igual lleva el suyo
        // escrito: si quedara implícito volvería al cero del tipo.
        out.push_str(&format!(
            "    pub {}: {} = {},\n",
            identificador_campo(&c.nombre),
            tipo_rust(&cd),
            valor_default(&c.default, &cd, enums)
        ));
    }
    // Un chunk que el esquema no nombra se guarda crudo y vuelve al archivo en
    // su lugar. Sin esto, cualquier campo que liblcf no conozca —o que sea de
    // 2003— rompería la ida y vuelta en silencio.
    out.push_str(
        "    /// Los chunks que el esquema no nombra, para que la vuelta sea exacta.\n\
         \x20   #[serde(skip_serializing_if = \"Vec::is_empty\")]\n\
         \x20   pub desconocidos: Vec<ChunkCrudo> = Vec::new(),\n}\n}\n\n",
    );
}

/// Los campos que existen como campo de Rust: los `f` y los posicionales de
/// los structs crudos. Los `t` son el largo de otro campo, que en Rust lo
/// lleva el propio `Vec`, pero en el binario ocupan su propio chunk.
fn visibles<'a>(campos: &'a [&'a Campo]) -> impl Iterator<Item = &'a &'a Campo> {
    campos.iter().filter(|c| c.clase != "t")
}

fn valor_default(
    default: &str,
    cd: &Cod,
    enums: &BTreeMap<String, Vec<(String, i64)>>,
) -> String {
    let d = default.trim();
    match cd {
        Cod::Bool => if d == "True" { "true".into() } else { "false".into() },
        Cod::Ber | Cod::U8 | Cod::I8 | Cod::U32 => {
            let v = d.split('|').next().unwrap_or("0");
            if v.is_empty() { "0".into() } else { v.to_string() }
        }
        Cod::F64 => {
            let v = d.split('|').next().unwrap_or("0.0");
            if v.is_empty() { "0.0".into() } else { v.to_string() }
        }
        // El centinela con el que una partida guardada dice "usá el nombre
        // que trae el LDB". `constants.csv` lo declara como `"\x1"`.
        Cod::Texto if d == "kEmptyName" => "\"\\u{1}\".to_string()".into(),
        Cod::Texto => format!("{:?}.to_string()", d),
        Cod::Enum(n) => {
            if d.is_empty() {
                format!("{n}::default()")
            } else if let Ok(v) = d.split('|').next().unwrap_or("").parse::<i32>() {
                let _ = enums;
                format!("{n}::de_i32({v})")
            } else {
                format!("{n}::default()")
            }
        }
        Cod::VecU8 | Cod::VecI16 | Cod::VecI32 | Cod::VecU32 | Cod::VecBool => lista(d),
        _ => "Default::default()".into(),
    }
}

/// Los defaults de lista que usa el CSV: `[1]`, `[1]*162`, `[31]+[15]*143`.
fn lista(d: &str) -> String {
    if d.is_empty() {
        return "Vec::new()".into();
    }
    // El CSV tiene un default escrito como un *comprehension* de Python:
    // `[x for x in range(0, 144)]`, o sea 0..144.
    if let Some(r) = d.strip_prefix("[x for x in range(") {
        let dentro = r.trim_end_matches(')').trim_end_matches("]").trim_end_matches(')');
        let mut it = dentro.split(',').map(|x| x.trim());
        let a = it.next().unwrap_or("0");
        let b = it.next().unwrap_or("0");
        return format!("({a}..{b}).collect()");
    }
    let mut partes = Vec::new();
    for trozo in d.split('+') {
        let trozo = trozo.trim();
        let (cuerpo, veces) = match trozo.split_once('*') {
            Some((a, b)) => (a.trim(), b.trim().parse::<usize>().unwrap_or(1)),
            None => (trozo, 1),
        };
        let valor = cuerpo.trim_start_matches('[').trim_end_matches(']');
        partes.push(format!("vec![{valor}; {veces}]"));
    }
    if partes.len() == 1 {
        partes.pop().unwrap()
    } else {
        format!("[{}].concat()", partes.join(", "))
    }
}

fn emitir_codec(
    out: &mut String,
    est: &Estructura,
    campos: &[&Campo],
    enums: &BTreeMap<String, Vec<(String, i64)>>,
    estructuras: &[Estructura],
) {
    let nombre = identificador(&est.nombre);
    // El 0 del final cierra un struct. liblcf avisa que ponérselo a `Database`
    // o a `Save` rompe el parser de RPG_RT, así que ésos no lo llevan.
    let terminador = !matches!(est.nombre.as_str(), "Database" | "Save");
    out.push_str(&format!(
        "impl Chunked for {nombre} {{\n\
         \x20   const NOMBRE: &'static str = \"{nombre}\";\n\
         \x20   const TERMINADOR: bool = {terminador};\n\
         \x20   const CON_ID: bool = {};\n\
         \x20   fn id(&self) -> i32 {{ {} }}\n\
         \x20   fn poner_id(&mut self, v: i32) {{ {} }}\n\
         \x20   fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo> {{ &mut self.desconocidos }}\n",
        est.con_id,
        if est.con_id { "self.id" } else { "0" },
        if est.con_id { "self.id = v;" } else { "let _ = v;" },
    ));

    // --- leer ---
    out.push_str("    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool> {\n        match id {\n");
    for c in campos {
        if c.clase == "t" {
            out.push_str(&format!(
                "            {:#04x} => {{}} // largo de `{}`, se recalcula al escribir\n",
                c.indice, c.nombre
            ));
            continue;
        }
        let cd = cod(&c.tipo, enums, &nombre_enum(c, enums));
        out.push_str(&format!(
            "            {:#04x} => self.{} = {},\n",
            c.indice,
            identificador_campo(&c.nombre),
            leer_expr(&cd)
        ));
    }
    out.push_str("            _ => return Ok(false),\n        }\n        Ok(true)\n    }\n");

    // --- escribir ---
    out.push_str("    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()> {\n");
    out.push_str(&format!("        let p = {nombre}::default();\n"));
    out.push_str("        let mut c: Vec<(u32, Vec<u8>)> = Vec::new();\n");
    let mut i = 0;
    while i < campos.len() {
        let c = campos[i];
        if c.clase == "t" {
            // El chunk del largo va antes que el del dato, y sale del dato.
            let dato = campos
                .iter()
                .find(|o| o.clase != "t" && o.nombre == c.nombre)
                .expect("un campo `t` sin su `f`");
            let cd = cod(&dato.tipo, enums, &nombre_enum(dato, enums));
            let campo = identificador_campo(&dato.nombre);
            out.push_str(&format!("        let v_{campo} = {};\n", escribir_expr(&cd, &format!("self.{campo}"))));
            if c.tipo.starts_with("Count<") {
                // `Count` guarda la cantidad de elementos, no los bytes.
                out.push_str(&format!(
                    "        {}c.push(({:#04x}, cod_ber(self.{campo}.len() as i32)));{}\n",
                    if c.persiste { String::new() } else { format!("if self.{campo}.len() != p.{campo}.len() {{ ") },
                    c.indice,
                    if c.persiste { "" } else { " }" },
                ));
            } else {
                out.push_str(&format!(
                    "        {}c.push(({:#04x}, cod_ber(v_{campo}.len() as i32)));{}\n",
                    if c.persiste {
                        String::new()
                    } else {
                        format!(
                            "if v_{campo}.len() != {}.len() {{ ",
                            escribir_expr(&cd, &format!("p.{campo}"))
                        )
                    },
                    c.indice,
                    if c.persiste { "" } else { " }" },
                ));
            }
            out.push_str(&format!(
                "        {}c.push(({:#04x}, v_{campo}));{}\n",
                if dato.persiste { String::new() } else { format!("if self.{campo} != p.{campo} {{ ") },
                dato.indice,
                if dato.persiste { "" } else { " }" },
            ));
            i += 1;
            // El campo del dato ya salió acá; saltearlo cuando toque.
            continue;
        }
        // ¿Ya lo emitió su chunk de largo?
        if campos[..i].iter().any(|o| o.clase == "t" && o.nombre == c.nombre) {
            i += 1;
            continue;
        }
        let cd = cod(&c.tipo, enums, &nombre_enum(c, enums));
        let campo = identificador_campo(&c.nombre);
        out.push_str(&format!(
            "        {}c.push(({:#04x}, {}));{}\n",
            if c.persiste { String::new() } else { format!("if self.{campo} != p.{campo} {{ ") },
            c.indice,
            escribir_expr(&cd, &format!("self.{campo}")),
            if c.persiste { "" } else { " }" },
        ));
        i += 1;
    }
    out.push_str("        e.volcar(c, &self.desconocidos);\n        Ok(())\n    }\n}\n\n");
    let _ = estructuras;
}

fn leer_expr(cd: &Cod) -> String {
    match cd {
        Cod::Ber => "dec_ber(d)".into(),
        Cod::Bool => "dec_bool(d)".into(),
        Cod::U8 => "dec_u8(d)".into(),
        Cod::U32 => "dec_u32(d)".into(),
        Cod::I8 => "dec_i8(d)".into(),
        Cod::F64 => "dec_f64(d)".into(),
        Cod::Texto => "dec_texto(d)".into(),
        Cod::VecU8 => "d.to_vec()".into(),
        Cod::VecI16 => "dec_vec_i16(d)".into(),
        Cod::VecI32 => "dec_vec_i32(d)".into(),
        Cod::VecU32 => "dec_vec_u32(d)".into(),
        Cod::VecBool => "dec_vec_bool(d)".into(),
        Cod::Enum(n) => format!("{n}::de_i32(dec_ber(d))"),
        Cod::Bandera(n) => format!("{n}::leer(d)"),
        Cod::Struct(n) => format!("dec_struct::<{n}>(d)?"),
        Cod::Crudo(n) => format!("{n}::leer_crudo(d)?"),
        Cod::Array(n) => format!("dec_array::<{n}>(d)?"),
        Cod::ComandosEvento => "dec_comandos_evento(d)?".into(),
        Cod::ComandosRuta => "dec_comandos_ruta(d)?".into(),
    }
}

fn escribir_expr(cd: &Cod, v: &str) -> String {
    match cd {
        Cod::Ber => format!("cod_ber({v})"),
        Cod::Bool => format!("cod_bool({v})"),
        Cod::U8 => format!("vec![{v}]"),
        Cod::U32 => format!("cod_u32({v})"),
        Cod::I8 => format!("vec![{v} as u8]"),
        Cod::F64 => format!("cod_f64({v})"),
        Cod::Texto => format!("cod_texto(&{v})"),
        Cod::VecU8 => format!("{v}.clone()"),
        Cod::VecI16 => format!("cod_vec_i16(&{v})"),
        Cod::VecI32 => format!("cod_vec_i32(&{v})"),
        Cod::VecU32 => format!("cod_vec_u32(&{v})"),
        Cod::VecBool => format!("cod_vec_bool(&{v})"),
        Cod::Enum(_) => format!("cod_ber({v}.a_i32())"),
        Cod::Bandera(_) => format!("{v}.escribir()"),
        Cod::Struct(_) => format!("cod_struct(&{v})?"),
        Cod::Crudo(_) => format!("{v}.escribir_crudo()"),
        Cod::Array(_) => format!("cod_array(&{v})?"),
        Cod::ComandosEvento => format!("cod_comandos_evento(&{v})"),
        Cod::ComandosRuta => format!("cod_comandos_ruta(&{v})"),
    }
}

// --- Nombres --------------------------------------------------------------

fn mayuscula(s: &str) -> String {
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

/// Un identificador de Rust válido, en CamelCase.
fn identificador(s: &str) -> String {
    let limpio: String = s
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '_' })
        .collect();
    let camel = mayuscula(&limpio);
    if camel.chars().next().map(|c| c.is_numeric()).unwrap_or(true) {
        return format!("N{camel}");
    }
    // `Self`, `crate` y `super` no se pueden escapar con `r#` ni siquiera como
    // variantes, así que se les agrega un guión bajo. El `#[serde(rename)]`
    // deja el nombre original en el JSON, que es lo que se lee.
    match camel.as_str() {
        "Self" | "Crate" | "Super" => format!("{camel}_"),
        _ => camel,
    }
}

/// Un nombre de campo: snake_case y sin chocar con las palabras de Rust.
fn identificador_campo(s: &str) -> String {
    let limpio: String = s
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '_' })
        .collect();
    match limpio.as_str() {
        "type" | "move" | "ref" | "box" | "loop" | "match" | "final" | "self" | "super" => {
            format!("r#{limpio}")
        }
        _ => limpio,
    }
}
