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

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

/// Una fila de `fields.csv`.
struct Campo {
    estructura: String,
    nombre: String,
    /// `f` es un campo común; `s` es el largo de un vector que va aparte.
    clase: String,
    tipo: String,
    indice: String,
    default: String,
    /// Si el binario guarda el campo aunque valga el default.
    persiste: bool,
    /// Los campos que sólo existen en RPG Maker 2003: este port es de 2000.
    es_2k3: bool,
}

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

    fs::create_dir_all(&salida).expect("no pude crear el directorio de salida");
    let mut texto = String::new();
    cabecera(&mut texto, &liblcf);
    for (nombre, variantes) in &enums {
        emitir_enum(&mut texto, nombre, variantes);
    }
    let mut por_estructura: BTreeMap<&str, Vec<&Campo>> = BTreeMap::new();
    for c in &campos {
        if c.es_2k3 {
            continue; // este port es de RPG Maker 2000
        }
        por_estructura.entry(&c.estructura).or_default().push(c);
    }
    for (estructura, campos) in &por_estructura {
        emitir_struct(&mut texto, estructura, campos, &enums);
    }
    let destino = salida.join("mod.rs");
    fs::write(&destino, texto).expect("no pude escribir el esquema");
    println!(
        "{} estructuras y {} enums -> {}",
        por_estructura.len(),
        enums.len(),
        destino.display()
    );
}

fn cabecera(out: &mut String, liblcf: &Path) {
    out.push_str(&format!(
        "//! El esquema de los archivos de RPG Maker 2000.\n\
         //!\n\
         //! **Generado por `cargo xtask generar`, y commiteado a propósito.**\n\
         //! No se edita a mano: lo que se edita es el generador o el CSV de\n\
         //! arriba. Ver `xtask/src/main.rs` para el porqué.\n\
         //!\n\
         //! Sale de las tablas de liblcf ({}), que es de donde el ecosistema\n\
         //! entero saca los nombres: en el binario no hay ninguno, sólo\n\
         //! índices de campo.\n\
         \n\
         #![allow(dead_code)]\n\
         \n\
         use serde::{{Deserialize, Serialize}};\n\n",
        liblcf.display()
    ));
}

fn leer_campos(ruta: &Path) -> Vec<Campo> {
    let texto = fs::read_to_string(ruta).expect("no encontré fields.csv");
    let mut filas = Vec::new();
    for (n, linea) in texto.lines().enumerate() {
        if n == 0 || linea.trim().is_empty() {
            continue;
        }
        let c: Vec<&str> = linea.split(',').collect();
        if c.len() < 8 || c[0].is_empty() || c[1].is_empty() {
            continue;
        }
        filas.push(Campo {
            estructura: c[0].to_string(),
            nombre: c[1].to_string(),
            clase: c[2].to_string(),
            tipo: c[3].to_string(),
            indice: c[4].to_string(),
            default: c[5].to_string(),
            persiste: c[6] == "1",
            es_2k3: c[7] == "1",
        });
    }
    filas
}

/// `enums.csv`: Structure, Entry, Value, Index.
fn leer_enums(ruta: &Path) -> BTreeMap<String, Vec<(String, i64)>> {
    let texto = fs::read_to_string(ruta).expect("no encontré enums.csv");
    let mut fuera: BTreeMap<String, Vec<(String, i64)>> = BTreeMap::new();
    for (n, linea) in texto.lines().enumerate() {
        if n == 0 || linea.trim().is_empty() {
            continue;
        }
        let c: Vec<&str> = linea.split(',').collect();
        if c.len() < 4 || c[0].is_empty() {
            continue;
        }
        let indice: i64 = match c[3].trim().parse() {
            Ok(v) => v,
            Err(_) => continue,
        };
        fuera
            .entry(format!("{}{}", c[0], mayuscula(c[1])))
            .or_default()
            .push((c[2].to_string(), indice));
    }
    fuera
}

fn emitir_enum(out: &mut String, nombre: &str, variantes: &[(String, i64)]) {
    out.push_str(&format!(
        "/// Generado desde `enums.csv`.\n\
         #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]\n\
         pub enum {nombre} {{\n"
    ));
    let mut vistas = std::collections::BTreeSet::new();
    for (variante, valor) in variantes {
        let id = identificador(variante);
        if !vistas.insert(id.clone()) {
            continue; // el CSV repite alguna con el mismo nombre
        }
        out.push_str(&format!("    #[serde(rename = \"{variante}\")]\n"));
        out.push_str(&format!("    {id} = {valor},\n"));
    }
    out.push_str("}\n\n");
    // Los structs derivan `Default`, así que cada enum necesita el suyo: la
    // primera variante, que en estas tablas es siempre el valor cero o el
    // "ninguno". El binario, igual, nunca deja un campo sin valor: o está o
    // vale su default declarado.
    if let Some((_, _)) = variantes.first() {
        let primera = identificador(&variantes[0].0);
        out.push_str(&format!(
            "impl Default for {nombre} {{\n    fn default() -> Self {{ {nombre}::{primera} }}\n}}\n\n"
        ));
    }
}

fn emitir_struct(
    out: &mut String,
    estructura: &str,
    campos: &[&Campo],
    enums: &BTreeMap<String, Vec<(String, i64)>>,
) {
    out.push_str(&format!(
        "/// Generado desde `fields.csv`.\n\
         #[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]\n\
         pub struct {} {{\n",
        identificador(estructura)
    ));
    let mut vistos = std::collections::BTreeSet::new();
    for c in campos {
        // **Sólo la clase `f`.** Un vector ocupa dos filas: la `f` con el
        // vector y una `s` o `t` con su largo, que en el binario va en su
        // propio campo y en Rust lo dice el `Vec`. El lector sí tiene que
        // consumirlo. Filtrarlas acá y no después importa: si no, la fila del
        // contador gana la deduplicación y el campo sale con el tipo
        // equivocado.
        if c.clase != "f" {
            continue;
        }
        if !vistos.insert(c.nombre.clone()) {
            // `fields.csv` repite algún campo —la versión de 2000 y la de
            // 2003 comparten fila—: nos quedamos con la primera.
            continue;
        }
        let tipo = tipo_rust(&c.tipo, estructura, &c.nombre, enums);
        out.push_str(&format!(
            "    /// campo {} del binario{}\n",
            c.indice,
            if c.persiste {
                ", se guarda aunque valga el default"
            } else {
                ""
            }
        ));
        if !c.default.is_empty() && !c.default.contains('|') {
            out.push_str(&format!("    /// default: {}\n", c.default));
        }
        out.push_str(&format!(
            "    pub {}: {tipo},\n",
            identificador_campo(&c.nombre)
        ));
    }
    out.push_str("}\n\n");
}

fn tipo_rust(
    tipo: &str,
    estructura: &str,
    campo: &str,
    enums: &BTreeMap<String, Vec<(String, i64)>>,
) -> String {
    // Si el campo tiene un enum declarado para esta estructura, es ése.
    let candidato = format!("{estructura}{}", mayuscula(campo));
    if enums.contains_key(&candidato) {
        return candidato;
    }
    match tipo {
        "Int32" => "i32".into(),
        "UInt32" => "u32".into(),
        "Int16" => "i16".into(),
        "UInt8" => "u8".into(),
        "Boolean" => "bool".into(),
        "Double" => "f64".into(),
        "String" | "DBString" => "String".into(),
        "DBBitArray" => "Vec<bool>".into(),
        "Int8" => "i8".into(),
        // `DBArray<T>` y `CountVector<T>` son listas con su largo adelante: en
        // Rust son un Vec y el largo lo lleva él.
        t if t.starts_with("DBArray<") => {
            let dentro = &t["DBArray<".len()..t.len() - 1];
            format!("Vec<{}>", tipo_rust(dentro, estructura, campo, enums))
        }
        t if t.starts_with("CountVector<") => {
            let dentro = &t["CountVector<".len()..t.len() - 1];
            format!("Vec<{}>", tipo_rust(dentro, estructura, campo, enums))
        }
        // Los `Flags` son bitfields: `flags.csv` dice qué bit es cada uno, y
        // hasta que eso se genere van como el entero crudo.
        t if t.ends_with("_Flags") || t.ends_with("Flags") => "u32".into(),
        // La versión del archivo: un entero.
        "Database_Version" | "DatabaseVersion" => "i32".into(),
        t if t.starts_with("Vector<") => {
            let dentro = &t["Vector<".len()..t.len() - 1];
            format!("Vec<{}>", tipo_rust(dentro, estructura, campo, enums))
        }
        // `Array<X>` es una lista indexada por id; acá va como Vec y el id lo
        // lleva el propio elemento. `Array<X:Ref<Y>>` es lo mismo con la clave
        // declarada, que tampoco cambia la forma en Rust.
        t if t.starts_with("Array<") => {
            let dentro = &t["Array<".len()..t.len() - 1];
            let elem = dentro.split(':').next().unwrap_or(dentro);
            format!("Vec<{}>", tipo_rust(elem, estructura, campo, enums))
        }
        // `Enum<Estructura_Campo>` nombra un enum de `enums.csv`, donde la
        // clave es Estructura + Campo en CamelCase.
        t if t.starts_with("Enum<") => {
            let dentro = &t["Enum<".len()..t.len() - 1];
            let (est, cam) = dentro.split_once('_').unwrap_or((dentro, ""));
            let nombre = format!("{est}{}", mayuscula(cam));
            if enums.contains_key(&nombre) {
                nombre
            } else {
                "i32".into()
            }
        }
        t if t.starts_with("Ref<") => "i32".into(),
        // Lo demás son structs del mismo esquema: Sound, Music, Rect, ...
        otro => identificador(otro),
    }
}

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
