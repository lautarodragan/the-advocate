//! The six structs that are not chunk-based.
//!
//! `fields.csv` declares their fields but not their indices, because they have
//! none: they sit one after another inside the chunk that contains them. liblcf
//! resolves them with hand-written specializations (`RawStruct<T>`) and so does
//! this module. There are few of them and they do not change, so generating
//! them would cost more than writing them.

use crate::lcf::*;
use crate::schema::*;

// --- Parameters ------------------------------------------------------------

impl Parameters {
    /// Six `int16` arrays of the same length, one after another. The length is
    /// not written down: it comes from dividing the chunk's by six.
    pub fn read_raw(d: &[u8]) -> Result<Parameters> {
        let n = d.len() / 6 / 2;
        let mut l = Reader::new(d);
        let take = |l: &mut Reader| -> Result<Vec<i16>> { Ok(dec_vec_i16(l.bytes(n * 2)?)) };
        Ok(Parameters {
            maxhp: take(&mut l)?,
            maxsp: take(&mut l)?,
            attack: take(&mut l)?,
            defense: take(&mut l)?,
            spirit: take(&mut l)?,
            agility: take(&mut l)?,
            unknown: Vec::new(),
        })
    }

    pub fn write_raw(&self) -> Vec<u8> {
        let mut b = Vec::new();
        for v in [
            &self.maxhp,
            &self.maxsp,
            &self.attack,
            &self.defense,
            &self.spirit,
            &self.agility,
        ] {
            b.extend_from_slice(&enc_vec_i16(v));
        }
        b
    }
}

// --- Equipment -------------------------------------------------------------

impl Equipment {
    /// Five `int16`. liblcf requires the chunk to be 10 bytes and warns if not.
    pub fn read_raw(d: &[u8]) -> Result<Equipment> {
        let v = dec_vec_i16(d);
        let g = |i: usize| v.get(i).copied().unwrap_or(0) as i32;
        Ok(Equipment {
            weapon_id: g(0),
            shield_id: g(1),
            armor_id: g(2),
            helmet_id: g(3),
            accessory_id: g(4),
            unknown: Vec::new(),
        })
    }

    pub fn write_raw(&self) -> Vec<u8> {
        enc_vec_i16(&[
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
    /// Four **raw** 32-bit integers, not BER.
    pub fn read_raw(d: &[u8]) -> Result<Rect> {
        let v = dec_vec_u32(d);
        let g = |i: usize| v.get(i).copied().unwrap_or(0);
        Ok(Rect {
            l: g(0),
            t: g(1),
            r: g(2),
            b: g(3),
            unknown: Vec::new(),
        })
    }

    pub fn write_raw(&self) -> Vec<u8> {
        enc_vec_u32(&[self.l, self.t, self.r, self.b])
    }
}

// --- EventCommand ----------------------------------------------------------

/// The command list of an event does **not** store how many there are: it ends
/// with four zero bytes. Each command is a code, an indent, a string with its
/// length in front, and a list of integers with its count in front; all in BER.
pub fn dec_event_commands(d: &[u8]) -> Result<Vec<EventCommand>> {
    let mut l = Reader::new(d);
    let mut out = Vec::new();
    loop {
        if l.eof() || l.peek()? == 0 {
            break;
        }
        let code = EventCommandCode::from_i32(l.ber()?);
        let indent = l.ber()?;
        let n = l.ber()? as usize;
        let string = dec_text(l.bytes(n)?);
        let count = l.ber()? as usize;
        let mut parameters = Vec::with_capacity(count.min(256));
        for _ in 0..count {
            parameters.push(l.ber()?);
        }
        out.push(EventCommand {
            code,
            indent,
            string,
            parameters,
            unknown: Vec::new(),
        });
    }
    Ok(out)
}

pub fn enc_event_commands(v: &[EventCommand]) -> Vec<u8> {
    let mut e = Writer::new();
    for c in v {
        e.ber(c.code.to_i32());
        e.ber(c.indent);
        let s = enc_text(&c.string);
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

/// A movement route: commands until the chunk runs out. How many parameters
/// each one carries depends on its code, and only four carry any.
pub fn dec_move_commands(d: &[u8]) -> Result<Vec<MoveCommand>> {
    let mut l = Reader::new(d);
    let mut out = Vec::new();
    while !l.eof() {
        let command_id = MoveCommandCode::from_i32(l.ber()?);
        let mut c = MoveCommand {
            command_id,
            ..Default::default()
        };
        match command_id.to_i32() {
            32 | 33 => c.parameter_a = l.ber()?,
            34 => {
                let n = l.ber()? as usize;
                c.parameter_string = dec_text(l.bytes(n)?);
                c.parameter_a = l.ber()?;
            }
            35 => {
                let n = l.ber()? as usize;
                c.parameter_string = dec_text(l.bytes(n)?);
                c.parameter_a = l.ber()?;
                c.parameter_b = l.ber()?;
                c.parameter_c = l.ber()?;
            }
            _ => {}
        }
        out.push(c);
    }
    Ok(out)
}

pub fn enc_move_commands(v: &[MoveCommand]) -> Vec<u8> {
    let mut e = Writer::new();
    for c in v {
        e.ber(c.command_id.to_i32());
        match c.command_id.to_i32() {
            32 | 33 => e.ber(c.parameter_a),
            34 => {
                let s = enc_text(&c.parameter_string);
                e.ber(s.len() as i32);
                e.bytes(&s);
                e.ber(c.parameter_a);
            }
            35 => {
                let s = enc_text(&c.parameter_string);
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
    /// The map tree is all there is to a `.lmt`: an array of `MapInfo`, the
    /// order of the tree, the active node and the `Start`. No chunks at all.
    pub fn read_tree(l: &mut Reader) -> Result<TreeMap> {
        let maps: Vec<MapInfo> = read_array(l)?;
        let count = l.ber()? as usize;
        let mut tree_order = Vec::with_capacity(count.min(4096));
        for _ in 0..count {
            tree_order.push(l.ber()?);
        }
        let active_node = l.ber()?;
        let start: Start = read_struct(l)?;
        Ok(TreeMap {
            maps,
            tree_order,
            active_node,
            start,
            unknown: Vec::new(),
        })
    }

    pub fn write_tree(&self, e: &mut Writer) -> Result<()> {
        write_array(&self.maps, e)?;
        e.ber(self.tree_order.len() as i32);
        for t in &self.tree_order {
            e.ber(*t);
        }
        e.ber(self.active_node);
        write_struct(&self.start, e)
    }
}
