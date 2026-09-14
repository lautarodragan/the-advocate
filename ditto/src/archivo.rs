//! Un archivo entero: el encabezado y lo que viene atrás.
//!
//! El encabezado es un largo en BER y un nombre (`LcfMapUnit`, `LcfDataBase`,
//! `LcfMapTree`), y se guarda en el JSON en vez de darlo por sentado: liblcf
//! tiene una opción para conservarlo justamente porque hay juegos con el
//! nombre cambiado, y reescribirlo daría otro binario.

use crate::esquema::*;
use crate::lcf::*;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "formato")]
pub enum Documento {
    #[serde(rename = "ldb")]
    Ldb { encabezado: String, datos: Database },
    #[serde(rename = "lmu")]
    Lmu { encabezado: String, datos: Map },
    #[serde(rename = "lmt")]
    Lmt { encabezado: String, datos: TreeMap },
}

impl Documento {
    pub fn extension(&self) -> &'static str {
        match self {
            Documento::Ldb { .. } => "ldb",
            Documento::Lmu { .. } => "lmu",
            Documento::Lmt { .. } => "lmt",
        }
    }
}

pub fn leer(d: &[u8]) -> Resultado<Documento> {
    let mut l = Lector::nuevo(d);
    let n = l.ber()? as usize;
    let encabezado = dec_texto(l.bytes(n)?);
    match encabezado.as_str() {
        "LcfDataBase" => Ok(Documento::Ldb {
            encabezado,
            datos: leer_struct(&mut l)?,
        }),
        "LcfMapUnit" => Ok(Documento::Lmu {
            encabezado,
            datos: leer_struct(&mut l)?,
        }),
        "LcfMapTree" => Ok(Documento::Lmt {
            encabezado,
            datos: TreeMap::leer_arbol(&mut l)?,
        }),
        otro => error(format!("encabezado desconocido: {otro:?}")),
    }
}

pub fn escribir(doc: &Documento) -> Resultado<Vec<u8>> {
    let mut e = Escritor::nuevo();
    let cab = match doc {
        Documento::Ldb { encabezado, .. }
        | Documento::Lmu { encabezado, .. }
        | Documento::Lmt { encabezado, .. } => cod_texto(encabezado),
    };
    e.ber(cab.len() as i32);
    e.bytes(&cab);
    match doc {
        Documento::Ldb { datos, .. } => escribir_struct(datos, &mut e)?,
        Documento::Lmu { datos, .. } => escribir_struct(datos, &mut e)?,
        Documento::Lmt { datos, .. } => datos.escribir_arbol(&mut e)?,
    }
    Ok(e.b)
}
