//! El formato binario de RPG Maker 2000, de los dos lados.
//!
//! El archivo es un encabezado —un largo y un nombre— y después un struct.
//! Un struct es una tira de *chunks* `(id, largo, bytes)` cerrada por un id 0;
//! un array de structs es una cantidad y, por cada elemento, su id y su struct.
//! Los enteros van en BER: siete bits por byte, el bit alto dice que sigue.
//!
//! Lo que hace difícil la vuelta exacta no es eso, sino la regla de omisión:
//! **un campo que vale su default no se escribe**, salvo los que
//! `fields.csv` marca con `PersistIfDefault`. Así que leer y escribir no son
//! simétricos por construcción: son simétricos porque el default que rellena
//! al leer es el mismo que decide omitir al escribir, y los dos salen de la
//! misma tabla. Ver `src/esquema/mod.rs`.

use serde::{Deserialize, Serialize};
use std::fmt;

pub type Resultado<T> = Result<T, Error>;

#[derive(Debug)]
pub struct Error(pub String);

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for Error {}

pub fn error<T>(m: impl Into<String>) -> Resultado<T> {
    Err(Error(m.into()))
}

/// Un chunk que el esquema no nombra. Se guarda tal cual y vuelve al archivo
/// en su lugar, para que un campo que liblcf no conoce no rompa la vuelta.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ChunkCrudo {
    pub id: u32,
    pub bytes: Vec<u8>,
}

// --- Lector ---------------------------------------------------------------

pub struct Lector<'a> {
    d: &'a [u8],
    pub pos: usize,
}

impl<'a> Lector<'a> {
    pub fn nuevo(d: &'a [u8]) -> Self {
        Lector { d, pos: 0 }
    }

    pub fn eof(&self) -> bool {
        self.pos >= self.d.len()
    }

    pub fn restante(&self) -> usize {
        self.d.len() - self.pos
    }

    pub fn espiar(&self) -> Resultado<u8> {
        self.d
            .get(self.pos)
            .copied()
            .ok_or_else(|| Error("lectura fuera de rango".into()))
    }

    pub fn byte(&mut self) -> Resultado<u8> {
        let b = self.espiar()?;
        self.pos += 1;
        Ok(b)
    }

    pub fn bytes(&mut self, n: usize) -> Resultado<&'a [u8]> {
        if self.pos + n > self.d.len() {
            return error(format!(
                "pedí {n} bytes en {} y quedan {}",
                self.pos,
                self.restante()
            ));
        }
        let t = &self.d[self.pos..self.pos + n];
        self.pos += n;
        Ok(t)
    }

    /// Entero BER. No tiene signo: los negativos llegan en complemento a dos.
    pub fn ber(&mut self) -> Resultado<i32> {
        let mut v: u32 = 0;
        loop {
            let b = self.byte()?;
            v = (v << 7) | (b & 0x7F) as u32;
            if b & 0x80 == 0 {
                return Ok(v as i32);
            }
        }
    }
}

// --- Escritor -------------------------------------------------------------

#[derive(Default)]
pub struct Escritor {
    pub b: Vec<u8>,
}

impl Escritor {
    pub fn nuevo() -> Self {
        Escritor { b: Vec::new() }
    }

    pub fn bytes(&mut self, s: &[u8]) {
        self.b.extend_from_slice(s);
    }

    pub fn ber(&mut self, v: i32) {
        self.bytes(&cod_ber(v));
    }

    /// Escribe los chunks de un struct: los que el esquema conoce y los que
    /// no, mezclados por id. El orden del esquema ya es ascendente —lo garantiza
    /// el CSV de liblcf— así que un orden estable por id deja cada desconocido
    /// donde estaba.
    pub fn volcar(&mut self, conocidos: Vec<(u32, Vec<u8>)>, extras: &[ChunkCrudo]) {
        let mut todos = conocidos;
        if !extras.is_empty() {
            for e in extras {
                todos.push((e.id, e.bytes.clone()));
            }
            todos.sort_by_key(|c| c.0);
        }
        for (id, cuerpo) in todos {
            self.ber(id as i32);
            self.ber(cuerpo.len() as i32);
            self.bytes(&cuerpo);
        }
    }
}

/// BER canónico: la misma forma que `LcfWriter::WriteInt`, el mínimo de bytes.
pub fn cod_ber(v: i32) -> Vec<u8> {
    let v = v as u32;
    let mut fuera = Vec::new();
    let mut i = 28i32;
    while i >= 0 {
        if v >= (1u32 << i) || i == 0 {
            fuera.push(((v >> i) & 0x7F) as u8 | if i > 0 { 0x80 } else { 0 });
        }
        i -= 7;
    }
    fuera
}

// --- Structs chunk-based ---------------------------------------------------

pub trait Chunked: Default + Sized {
    const NOMBRE: &'static str;
    /// El 0 que cierra el struct. `Database` y `Save` no lo llevan: liblcf
    /// avisa que ponérselo rompe el parser de RPG_RT.
    const TERMINADOR: bool;
    /// Si dentro de un array cada elemento lleva su id adelante.
    const CON_ID: bool;

    fn id(&self) -> i32;
    fn poner_id(&mut self, v: i32);
    fn desconocidos_mut(&mut self) -> &mut Vec<ChunkCrudo>;
    /// Devuelve `false` si el id no es de este struct: el chunk se guarda crudo.
    fn leer_chunk(&mut self, id: u32, d: &[u8]) -> Resultado<bool>;
    fn escribir_chunks(&self, e: &mut Escritor) -> Resultado<()>;
}

pub fn leer_struct<T: Chunked>(l: &mut Lector) -> Resultado<T> {
    let mut o = T::default();
    while !l.eof() {
        let id = l.ber()? as u32;
        if id == 0 {
            break;
        }
        let largo = l.ber()? as usize;
        let d = l.bytes(largo)?;
        if !o.leer_chunk(id, d)? {
            o.desconocidos_mut().push(ChunkCrudo {
                id,
                bytes: d.to_vec(),
            });
        }
    }
    Ok(o)
}

pub fn escribir_struct<T: Chunked>(o: &T, e: &mut Escritor) -> Resultado<()> {
    o.escribir_chunks(e)?;
    if T::TERMINADOR {
        e.ber(0);
    }
    Ok(())
}

pub fn dec_struct<T: Chunked>(d: &[u8]) -> Resultado<T> {
    leer_struct(&mut Lector::nuevo(d))
}

pub fn cod_struct<T: Chunked>(o: &T) -> Resultado<Vec<u8>> {
    let mut e = Escritor::nuevo();
    escribir_struct(o, &mut e)?;
    Ok(e.b)
}

pub fn leer_array<T: Chunked>(l: &mut Lector) -> Resultado<Vec<T>> {
    let n = l.ber()? as usize;
    let mut v = Vec::with_capacity(n.min(4096));
    for _ in 0..n {
        let id = if T::CON_ID { l.ber()? } else { 0 };
        let mut o: T = leer_struct(l)?;
        o.poner_id(id);
        v.push(o);
    }
    Ok(v)
}

pub fn escribir_array<T: Chunked>(v: &[T], e: &mut Escritor) -> Resultado<()> {
    e.ber(v.len() as i32);
    for o in v {
        if T::CON_ID {
            e.ber(o.id());
        }
        escribir_struct(o, e)?;
    }
    Ok(())
}

pub fn dec_array<T: Chunked>(d: &[u8]) -> Resultado<Vec<T>> {
    leer_array(&mut Lector::nuevo(d))
}

pub fn cod_array<T: Chunked>(v: &[T]) -> Resultado<Vec<u8>> {
    let mut e = Escritor::nuevo();
    escribir_array(v, &mut e)?;
    Ok(e.b)
}

// --- Tipos sueltos ---------------------------------------------------------

pub fn dec_ber(d: &[u8]) -> i32 {
    if d.is_empty() {
        return 0;
    }
    Lector::nuevo(d).ber().unwrap_or(0)
}

pub fn dec_bool(d: &[u8]) -> bool {
    d.first().map_or(false, |b| *b != 0)
}

pub fn cod_bool(v: bool) -> Vec<u8> {
    vec![v as u8]
}

pub fn dec_u8(d: &[u8]) -> u8 {
    d.first().copied().unwrap_or(0)
}

pub fn dec_i8(d: &[u8]) -> i8 {
    dec_u8(d) as i8
}

pub fn dec_u32(d: &[u8]) -> u32 {
    let mut b = [0u8; 4];
    b[..d.len().min(4)].copy_from_slice(&d[..d.len().min(4)]);
    u32::from_le_bytes(b)
}

pub fn cod_u32(v: u32) -> Vec<u8> {
    v.to_le_bytes().to_vec()
}

pub fn dec_f64(d: &[u8]) -> f64 {
    let mut b = [0u8; 8];
    b[..d.len().min(8)].copy_from_slice(&d[..d.len().min(8)]);
    f64::from_le_bytes(b)
}

pub fn cod_f64(v: f64) -> Vec<u8> {
    v.to_le_bytes().to_vec()
}

pub fn dec_vec_i16(d: &[u8]) -> Vec<i16> {
    d.chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect()
}

pub fn cod_vec_i16(v: &[i16]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 2);
    for x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

pub fn dec_vec_i32(d: &[u8]) -> Vec<i32> {
    d.chunks_exact(4)
        .map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

pub fn cod_vec_i32(v: &[i32]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 4);
    for x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

pub fn dec_vec_u32(d: &[u8]) -> Vec<u32> {
    d.chunks_exact(4)
        .map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

pub fn cod_vec_u32(v: &[u32]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 4);
    for x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

/// `Vector<Boolean>` y `DBBitArray`: un byte entero por valor, no un bit.
pub fn dec_vec_bool(d: &[u8]) -> Vec<bool> {
    d.iter().map(|b| *b != 0).collect()
}

pub fn cod_vec_bool(v: &[bool]) -> Vec<u8> {
    v.iter().map(|b| *b as u8).collect()
}

/// Un bit de un campo `*_Flags`, desde el menos significativo del primer byte.
pub fn bit(d: &[u8], i: usize) -> bool {
    d.get(i / 8).map_or(false, |b| (b >> (i % 8)) & 1 == 1)
}

// --- Texto -----------------------------------------------------------------

/// Los 32 caracteres con los que cp1252 se aparta de Latin-1 (0x80..0x9F).
const CP1252_ALTO: [char; 32] = [
    '\u{20AC}', '\u{0081}', '\u{201A}', '\u{0192}', '\u{201E}', '\u{2026}', '\u{2020}', '\u{2021}',
    '\u{02C6}', '\u{2030}', '\u{0160}', '\u{2039}', '\u{0152}', '\u{008D}', '\u{017D}', '\u{008F}',
    '\u{0090}', '\u{2018}', '\u{2019}', '\u{201C}', '\u{201D}', '\u{2022}', '\u{2013}', '\u{2014}',
    '\u{02DC}', '\u{2122}', '\u{0161}', '\u{203A}', '\u{0153}', '\u{009D}', '\u{017E}', '\u{0178}',
];

/// cp1252 **completo**, con los cinco bytes que la tabla oficial deja sin
/// definir (0x81, 0x8D, 0x8F, 0x90, 0x9D) mapeados a su control C1. Así la
/// tabla es una biyección byte ⇄ carácter y ningún texto se pierde al volver.
///
/// El juego tiene un par de mensajes en Shift-JIS que el autor nunca tocó: acá
/// salen como caracteres raros, y vuelven al binario idénticos. Traducirlos
/// bien costaría adivinar la codificación por campo, y a cambio se perdería la
/// vuelta exacta, que es lo único que hace útil a esta herramienta.
pub fn dec_texto(d: &[u8]) -> String {
    d.iter()
        .map(|b| match b {
            0x80..=0x9F => CP1252_ALTO[(b - 0x80) as usize],
            otro => *otro as char,
        })
        .collect()
}

pub fn cod_texto(s: &str) -> Vec<u8> {
    let mut fuera = Vec::with_capacity(s.len());
    for c in s.chars() {
        if (c as u32) < 0x80 || (0xA0..=0xFF).contains(&(c as u32)) {
            fuera.push(c as u8);
        } else if let Some(i) = CP1252_ALTO.iter().position(|x| *x == c) {
            fuera.push(0x80 + i as u8);
        } else {
            // Un carácter que cp1252 no tiene: sólo puede venir de un JSON
            // editado a mano. Se avisa en vez de escribir basura.
            fuera.push(b'?');
        }
    }
    fuera
}

// Los códecs a mano de los structs que no son chunk-based viven al lado, pero
// el esquema generado sólo importa esto.
pub use crate::crudos::*;
