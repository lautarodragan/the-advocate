//! Los seis structs que no son chunk-based.
//!
//! `fields.csv` les declara los campos pero no los índices, porque no los
//! tienen: van uno detrás del otro dentro del chunk que los contiene. liblcf
//! los resuelve con especializaciones a mano (`RawStruct<T>`) y acá pasa lo
//! mismo. Son pocos y no cambian, así que generarlos costaría más que
//! escribirlos.

use crate::esquema::*;
use crate::lcf::*;

// --- Parameters ------------------------------------------------------------

impl Parameters {
    /// Seis arrays de `int16` del mismo largo, uno atrás del otro. El largo no
    /// está escrito: sale de dividir el del chunk por seis.
    pub fn leer_crudo(d: &[u8]) -> Resultado<Parameters> {
        let n = d.len() / 6 / 2;
        let mut l = Lector::nuevo(d);
        let tirar = |l: &mut Lector| -> Resultado<Vec<i16>> {
            Ok(dec_vec_i16(l.bytes(n * 2)?))
        };
        Ok(Parameters {
            maxhp: tirar(&mut l)?,
            maxsp: tirar(&mut l)?,
            attack: tirar(&mut l)?,
            defense: tirar(&mut l)?,
            spirit: tirar(&mut l)?,
            agility: tirar(&mut l)?,
            desconocidos: Vec::new(),
        })
    }

    pub fn escribir_crudo(&self) -> Vec<u8> {
        let mut b = Vec::new();
        for v in [
            &self.maxhp,
            &self.maxsp,
            &self.attack,
            &self.defense,
            &self.spirit,
            &self.agility,
        ] {
            b.extend_from_slice(&cod_vec_i16(v));
        }
        b
    }
}

// --- Equipment -------------------------------------------------------------

impl Equipment {
    /// Cinco `int16`. liblcf exige que el chunk mida 10 y avisa si no.
    pub fn leer_crudo(d: &[u8]) -> Resultado<Equipment> {
        let v = dec_vec_i16(d);
        let g = |i: usize| v.get(i).copied().unwrap_or(0) as i32;
        Ok(Equipment {
            weapon_id: g(0),
            shield_id: g(1),
            armor_id: g(2),
            helmet_id: g(3),
            accessory_id: g(4),
            desconocidos: Vec::new(),
        })
    }

    pub fn escribir_crudo(&self) -> Vec<u8> {
        cod_vec_i16(&[
            self.weapon_id as i16,
            self.shield_id as i16,
            self.armor_id as i16,
            self.helmet_id as i16,
            self.accessory_id as i16,
        ])
    }
}

// --- Rect ------------------------------------------------------------------

impl Rect {
    /// Cuatro enteros de 32 bits **crudos**, no BER.
    pub fn leer_crudo(d: &[u8]) -> Resultado<Rect> {
        let v = dec_vec_u32(d);
        let g = |i: usize| v.get(i).copied().unwrap_or(0);
        Ok(Rect {
            l: g(0),
            t: g(1),
            r: g(2),
            b: g(3),
            desconocidos: Vec::new(),
        })
    }

    pub fn escribir_crudo(&self) -> Vec<u8> {
        cod_vec_u32(&[self.l, self.t, self.r, self.b])
    }
}

// --- EventCommand ----------------------------------------------------------

/// La lista de comandos de un evento **no** guarda cuántos son: termina con
/// cuatro ceros. Cada comando es código, indentación, un string con su largo
/// adelante, y una lista de enteros con su cantidad adelante; todo en BER.
pub fn dec_comandos_evento(d: &[u8]) -> Resultado<Vec<EventCommand>> {
    let mut l = Lector::nuevo(d);
    let mut fuera = Vec::new();
    loop {
        if l.eof() || l.espiar()? == 0 {
            break;
        }
        let code = EventCommandCode::de_i32(l.ber()?);
        let indent = l.ber()?;
        let n = l.ber()? as usize;
        let string = dec_texto(l.bytes(n)?);
        let cuantos = l.ber()? as usize;
        let mut parameters = Vec::with_capacity(cuantos.min(256));
        for _ in 0..cuantos {
            parameters.push(l.ber()?);
        }
        fuera.push(EventCommand {
            code,
            indent,
            string,
            parameters,
            desconocidos: Vec::new(),
        });
    }
    Ok(fuera)
}

pub fn cod_comandos_evento(v: &[EventCommand]) -> Vec<u8> {
    let mut e = Escritor::nuevo();
    for c in v {
        e.ber(c.code.a_i32());
        e.ber(c.indent);
        let s = cod_texto(&c.string);
        e.ber(s.len() as i32);
        e.bytes(&s);
        e.ber(c.parameters.len() as i32);
        for p in &c.parameters {
            e.ber(*p);
        }
    }
    e.bytes(&[0, 0, 0, 0]);
    e.b
}

// --- MoveCommand -----------------------------------------------------------

/// Una ruta de movimiento: comandos hasta que se acabe el chunk. Cuántos
/// parámetros lleva cada uno depende del código, y sólo cuatro llevan alguno.
pub fn dec_comandos_ruta(d: &[u8]) -> Resultado<Vec<MoveCommand>> {
    let mut l = Lector::nuevo(d);
    let mut fuera = Vec::new();
    while !l.eof() {
        let command_id = MoveCommandCode::de_i32(l.ber()?);
        let mut c = MoveCommand {
            command_id,
            ..Default::default()
        };
        match command_id.a_i32() {
            32 | 33 => c.parameter_a = l.ber()?,
            34 => {
                let n = l.ber()? as usize;
                c.parameter_string = dec_texto(l.bytes(n)?);
                c.parameter_a = l.ber()?;
            }
            35 => {
                let n = l.ber()? as usize;
                c.parameter_string = dec_texto(l.bytes(n)?);
                c.parameter_a = l.ber()?;
                c.parameter_b = l.ber()?;
                c.parameter_c = l.ber()?;
            }
            _ => {}
        }
        fuera.push(c);
    }
    Ok(fuera)
}

pub fn cod_comandos_ruta(v: &[MoveCommand]) -> Vec<u8> {
    let mut e = Escritor::nuevo();
    for c in v {
        e.ber(c.command_id.a_i32());
        match c.command_id.a_i32() {
            32 | 33 => e.ber(c.parameter_a),
            34 => {
                let s = cod_texto(&c.parameter_string);
                e.ber(s.len() as i32);
                e.bytes(&s);
                e.ber(c.parameter_a);
            }
            35 => {
                let s = cod_texto(&c.parameter_string);
                e.ber(s.len() as i32);
                e.bytes(&s);
                e.ber(c.parameter_a);
                e.ber(c.parameter_b);
                e.ber(c.parameter_c);
            }
            _ => {}
        }
    }
    e.b
}

// --- TreeMap ---------------------------------------------------------------

impl TreeMap {
    /// El árbol de mapas es lo único del `.lmt`: un array de `MapInfo`, el
    /// orden del árbol, el nodo activo y el `Start`. Nada de chunks.
    pub fn leer_arbol(l: &mut Lector) -> Resultado<TreeMap> {
        let maps: Vec<MapInfo> = leer_array(l)?;
        let cuantos = l.ber()? as usize;
        let mut tree_order = Vec::with_capacity(cuantos.min(4096));
        for _ in 0..cuantos {
            tree_order.push(l.ber()?);
        }
        let active_node = l.ber()?;
        let start: Start = leer_struct(l)?;
        Ok(TreeMap {
            maps,
            tree_order,
            active_node,
            start,
            desconocidos: Vec::new(),
        })
    }

    pub fn escribir_arbol(&self, e: &mut Escritor) -> Resultado<()> {
        escribir_array(&self.maps, e)?;
        e.ber(self.tree_order.len() as i32);
        for t in &self.tree_order {
            e.ber(*t);
        }
        e.ber(self.active_node);
        escribir_struct(&self.start, e)
    }
}
