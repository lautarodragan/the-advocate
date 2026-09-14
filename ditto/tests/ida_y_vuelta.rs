//! La prueba que hace valiosa a Ditto: leer un archivo de RPG Maker, volcarlo
//! a JSON, escribirlo de nuevo desde el JSON, y que el binario sea **idéntico**
//! al original.
//!
//! Un "casi" no sirve: la idea es abrir el juego con el editor de verdad y
//! volver, y un byte de más rompe el juego de otro.
//!
//! Por omisión corre sobre una muestra chica para que `cargo test` siga siendo
//! algo que uno corre sin pensarlo. La tanda entera —los 328 mapas, el LDB y el
//! árbol— va detrás de una variable de entorno:
//!
//!     DITTO_TODO=1 cargo test --release -- --nocapture

use std::path::{Path, PathBuf};

/// De dónde sale el juego. `/extras/abl-rm` adentro del contenedor.
fn juego() -> PathBuf {
    PathBuf::from(std::env::var("GAME_DIR").unwrap_or_else(|_| "/extras/abl-rm".into()))
}

/// Lee, vuelca a JSON, vuelve, y compara. Devuelve dónde está la diferencia.
fn vuelta(ruta: &Path) -> Result<(), String> {
    let original = std::fs::read(ruta).map_err(|e| format!("no pude leer: {e}"))?;
    let doc = ditto::archivo::leer(&original).map_err(|e| format!("al leer: {e}"))?;

    // El JSON no es un intermedio decorativo: si no cierra, no se puede tener
    // el juego en el repo como JSON, que es el punto de todo esto.
    let json = serde_json::to_vec(&doc).map_err(|e| format!("al serializar: {e}"))?;
    let devuelto: ditto::archivo::Documento =
        serde_json::from_slice(&json).map_err(|e| format!("al deserializar: {e}"))?;
    if devuelto != doc {
        return Err("el JSON no devuelve la misma estructura".into());
    }

    let binario = ditto::archivo::escribir(&devuelto).map_err(|e| format!("al escribir: {e}"))?;
    if binario == original {
        return Ok(());
    }
    let n = binario
        .iter()
        .zip(original.iter())
        .position(|(a, b)| a != b)
        .unwrap_or(binario.len().min(original.len()));
    Err(format!(
        "difiere en el byte {n} (de {} originales, salieron {}): {:02x?} en vez de {:02x?}",
        original.len(),
        binario.len(),
        &binario[n.saturating_sub(4)..(n + 4).min(binario.len())],
        &original[n.saturating_sub(4)..(n + 4).min(original.len())],
    ))
}

fn mapas() -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(juego())
        .expect("no encontré el juego; poné GAME_DIR")
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().map_or(false, |x| x.eq_ignore_ascii_case("lmu")))
        .collect();
    v.sort();
    v
}

/// El corpus entero: los 328 `.lmu`, el `RPG_RT.ldb` y el `RPG_RT.lmt`.
fn corpus() -> Vec<PathBuf> {
    let mut v = vec![juego().join("RPG_RT.ldb"), juego().join("RPG_RT.lmt")];
    v.extend(mapas());
    v
}

fn tanda(archivos: &[PathBuf]) {
    let mut fallados = Vec::new();
    for a in archivos {
        if let Err(e) = vuelta(a) {
            fallados.push(format!("{}: {e}", a.file_name().unwrap().to_string_lossy()));
        }
    }
    println!(
        "ida y vuelta byte por byte: {} de {}",
        archivos.len() - fallados.len(),
        archivos.len()
    );
    for f in &fallados {
        println!("  {f}");
    }
    assert!(fallados.is_empty(), "{} archivos no vuelven iguales", fallados.len());
}

#[test]
fn el_ldb_y_el_arbol_vuelven_iguales() {
    tanda(&[juego().join("RPG_RT.ldb"), juego().join("RPG_RT.lmt")]);
}

#[test]
fn una_muestra_de_mapas_vuelve_igual() {
    let todos = mapas();
    assert!(!todos.is_empty(), "no encontré ningún .lmu en {:?}", juego());
    if std::env::var("DITTO_TODO").is_ok() {
        tanda(&todos);
        return;
    }
    // Uno de cada veinte, más el primero y el último: alcanza para que una
    // regresión en el códec se vea sin pagar los 328 en cada `cargo test`.
    let muestra: Vec<PathBuf> = todos
        .iter()
        .step_by(20)
        .chain(todos.last())
        .cloned()
        .collect();
    tanda(&muestra);
}

/// El corpus completo. Es el número que se reporta.
#[test]
#[ignore = "la tanda larga: `cargo test --release -- --ignored --nocapture`"]
fn el_juego_entero_vuelve_igual() {
    tanda(&corpus());
}

/// La ida y vuelta sola no alcanza como prueba: un lector que no entendiera
/// **nada** y guardara cada chunk crudo también daría byte por byte, y el JSON
/// no serviría para nada. Así que además se exige que no quede ni un chunk sin
/// nombre. `desconocidos` sólo aparece en el JSON cuando tiene algo adentro.
#[test]
fn ningun_chunk_queda_sin_nombre() {
    for a in [juego().join("RPG_RT.ldb"), juego().join("RPG_RT.lmt")]
        .into_iter()
        .chain(mapas().into_iter().step_by(20))
    {
        let doc = ditto::archivo::leer(&std::fs::read(&a).unwrap()).unwrap();
        let json = serde_json::to_string(&doc).unwrap();
        assert!(
            !json.contains("desconocidos"),
            "{:?} tiene chunks que el esquema no nombra",
            a.file_name().unwrap()
        );
    }
}
