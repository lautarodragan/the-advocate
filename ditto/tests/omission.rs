//! Hasta dónde llega la regla de omisión, medido.
//!
//! La vuelta exacta se sostiene sobre **"un campo que vale su default no se
//! escribe"**. Eso no es una decisión nuestra: es lo que hace el editor. Pero
//! es una decisión *del que escribe*, así que un archivo que guardara
//! explícitamente un campo con su valor default saldría de nuestra vuelta sin
//! ese chunk, y el binario no sería idéntico.
//!
//! Estas dos pruebas fijan los dos lados del número: cuánto se pierde si pasa,
//! y cuántas veces el editor de verdad eligió omitir en el juego real. Ver
//! `README.md`, "El límite de la regla de omisión, medido".

use std::path::PathBuf;

fn juego() -> PathBuf {
    PathBuf::from(std::env::var("GAME_DIR").unwrap_or_else(|_| "/extras/abl-rm".into()))
}

/// Parte un `.lmu` en (encabezado crudo, chunks de primer nivel).
fn partir(d: &[u8]) -> (Vec<u8>, Vec<(u32, Vec<u8>)>) {
    let mut l = ditto::lcf::Lector::nuevo(d);
    let n = l.ber().unwrap() as usize;
    l.bytes(n).unwrap();
    let cab = d[..l.pos].to_vec();
    let mut chunks = Vec::new();
    loop {
        let id = l.ber().unwrap() as u32;
        if id == 0 {
            break;
        }
        let largo = l.ber().unwrap() as usize;
        chunks.push((id, l.bytes(largo).unwrap().to_vec()));
    }
    (cab, chunks)
}

fn armar(cab: &[u8], chunks: &[(u32, Vec<u8>)]) -> Vec<u8> {
    let mut e = ditto::lcf::Escritor::nuevo();
    e.bytes(cab);
    e.volcar(chunks.to_vec(), &[]);
    e.ber(0);
    e.b
}

fn vuelta(bin: &[u8]) -> Vec<u8> {
    let doc = ditto::archivo::leer(bin).unwrap();
    ditto::archivo::escribir(&doc).unwrap()
}

/// **El límite conocido, no un bug que se coló.** Un chunk escrito a mano con
/// el valor default del campo no sobrevive la vuelta: se pierden exactamente
/// sus tres bytes —id, largo y cuerpo— y todo lo que viene atrás se corre.
///
/// Si algún día se cubre, esta prueba es la que hay que dar vuelta.
#[test]
fn un_default_escrito_a_mano_se_pierde() {
    let orig = std::fs::read(juego().join("Map0001.lmu")).unwrap();
    let (cab, chunks) = partir(&orig);
    assert_eq!(armar(&cab, &chunks), orig, "el rearmado crudo no da el original");
    assert_eq!(vuelta(&orig), orig, "la vuelta normal ya falla");

    // `generator_surround` es el campo 0x33 de `Map` y su default es `True`.
    // No está en ningún mapa de ABL, justamente porque vale el default.
    assert!(
        !chunks.iter().any(|c| c.0 == 0x33),
        "0x33 ya estaba: elegí otro campo para la medición"
    );
    let mut con = chunks.clone();
    con.push((0x33, vec![0x01]));
    con.sort_by_key(|c| c.0);

    let entrada = armar(&cab, &con);
    assert_eq!(entrada.len(), orig.len() + 3);
    let salida = vuelta(&entrada);
    assert_eq!(
        salida.len(),
        entrada.len() - 3,
        "el chunk explícito tendría que perderse: son sus 3 bytes"
    );
    assert_eq!(salida, orig, "lo que sale es el archivo sin ese chunk");
}

/// La otra mitad del número: el editor **sí** omite. Sobre los 328 mapas, de
/// los 33 chunks que `Map` puede escribir en su primer nivel hay 2.363
/// presentes de 10.824 posibles: RPG Maker omitió 8.461 veces. Con eso, que
/// los 330 archivos vuelvan byte por byte deja de ser suerte y pasa a ser la
/// prueba de que el editor de verdad sigue la misma regla que Ditto.
#[test]
fn el_editor_omite_los_defaults() {
    let mut mapas: Vec<PathBuf> = std::fs::read_dir(juego())
        .unwrap()
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().map_or(false, |x| x.eq_ignore_ascii_case("lmu")))
        .collect();
    mapas.sort();

    let posibles_por_mapa = 33usize;
    let presentes: usize = mapas
        .iter()
        .map(|a| partir(&std::fs::read(a).unwrap()).1.len())
        .sum();
    let posibles = posibles_por_mapa * mapas.len();
    println!(
        "{} mapas: {} chunks presentes de {} posibles; el editor omitió {}",
        mapas.len(),
        presentes,
        posibles,
        posibles - presentes
    );
    assert!(
        posibles - presentes > 8000,
        "si esto baja mucho, la evidencia de que el editor omite se debilitó"
    );
}
