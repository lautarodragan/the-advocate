//! What the cartridge carries per map, ready for ca65: the map record and
//! its table, the ChipSet's animation, the event pages, the tables of the
//! drawn events, of the poses and of the leaders, each map's data blocks,
//! and the poses of whoever changes pose, for the whole cartridge.
//!
//! Everything here reads what the map's conversion already decided, and
//! writes text: nothing here decides anything about a map.

use crate::asm::{block, pointer};
use crate::cgram::BACKDROP;
use crate::fail::{Bad, Result};
use crate::materials::{grid_high_used, map_ram, Materials, COMPRESSED_KINDS};
use crate::objects::{
    block_tile, LAYER_ABOVE, OBJ_COLORS, OBJ_PRIORITY, OBJ_PRIORITY_ABOVE, POSE_BYTES, SPRITE_POSES,
};
use crate::request::{Map, Page, Slot};
use crate::snes::{cgram_word, BYTES_PER_TILE, COLORS_PER_PALETTE};
use crate::text::quoted;
use crate::vram::{self, Layout};
use std::collections::{BTreeSet, HashMap};
use std::fmt::Write;

/// A map's record in the table. The stride is a power of two so that going
/// from index to offset is shifts and not a multiplication, and there is
/// room to spare on purpose: adding a field must not move anything already
/// there.
pub const MAP_STRIDE: usize = 128;

/// The record's 16-bit fields, with their comment.
pub const MAP_SCALARS: [(&str, &str); 26] = [
    ("MAP_BW", "width in 16x16 cells"),
    ("MAP_BH", "height in 16x16 cells"),
    ("CAM_MAX_X", "how far the camera reaches without going out"),
    ("CAM_MAX_Y", ""),
    ("HERO_MAX_X", "how far the hero reaches"),
    ("HERO_MAX_Y", ""),
    ("HERO_START_X", "where it starts, in pixels"),
    ("HERO_START_Y", ""),
    ("VRAM_TILES", "the VRAM layout, in words"),
    // Where the background tilemap goes. The upper layer's base has no
    // field: it is the high nibble of BG12NBA_VALUE, and the record is full.
    ("VRAM_MAP", ""),
    ("VRAM_SPRITE", ""),
    ("VRAM_WINDOW", "0 if this ROM carries no message window"),
    ("VRAM_WINDOW_MAP", "and its own 32x32 tilemap"),
    ("MAP_TILES", "how many background tiles, for the DMA"),
    ("MAP_CGRAM", "how many CGRAM words"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "how many NPCs with a CharSet"),
    (
        "EV_COUNT",
        "how many events the map has, with or without a graphic",
    ),
    (
        "TIMER_BASE",
        "the first tile of the timer digits, 0 if there are none",
    ),
    (
        "RAIN_BASE",
        "the first tile of the raindrops, 0 if there are none",
    ),
    ("ACTOR_COUNT", "how many party leader candidates"),
    ("PAGE_COUNT", "how many event pages have to be resolved"),
    (
        "ROUTE_GRAPHIC_COUNT",
        "how many distinct graphics command 34 asks for",
    ),
];

/// The record's 8-bit fields.
pub const MAP_BYTES: [(&str, &str); 8] = [
    (
        "OBSEL_VALUE",
        "8x8 and 32x32 objects, and the page of their tiles",
    ),
    ("BG12NBA_VALUE", "the tile pages of BG1 and BG2"),
    ("ABOVE_FIRST", "which CGRAM entry the upper layer starts at"),
    ("TIMER_PAL", "the sprite palette of the timer digits"),
    ("RAIN_PAL", "the sprite palette of the raindrops"),
    // A byte and not a scalar because the record is at exactly its 128. A
    // block's tile is always a multiple of four and less than 512.
    (
        "TURN_TILE4",
        "the tile of the turn slot divided by four, or $FF",
    ),
    // The terrain, which is what `StoreTerrainID` answers: an index into the
    // database's terrains, which does not go over 255.
    ("TERRAIN_OUTSIDE", "the terrain of a cell outside the map"),
    (
        "TERRAIN_PLANE",
        "the terrain of the whole map, or 0 if there is a table",
    ),
];

/// The record's pointers, to the map's data blocks.
pub const MAP_POINTERS: [&str; 17] = [
    "map_tiles",
    "map_cgram",
    "above_tiles",
    "above_cgram",
    "sprite_tiles",
    "sprite_cgram",
    "map_cells",
    "map_blocks",
    "block_pass",
    "block_terrain",
    "npc_table",
    "actor_table",
    "pages",
    "ev_pos",
    "npc_poses",
    "route_graphic",
    // The ChipSet animation: the two tile runs and their drawings.
    "anim_tiles",
];

/// The pointers go four bytes at a time even though they are three: the
/// low part of each always lands on an even address, which is how it is
/// read with the accumulator in 16 bits.
pub const MAP_PTR_STEP: usize = 4;

/// Where the pointers start: right after the scalars and the bytes, rounded
/// up to their step. **It is computed and not written by hand**: written by
/// hand it already failed once —a scalar more left `ABOVE_FIRST` and the
/// first pointer at the same offset, and the screen came out a flat
/// colour—, and neither end can see that.
pub const MAP_PTR_BASE: usize =
    (MAP_SCALARS.len() * 2 + MAP_BYTES.len()).div_ceil(MAP_PTR_STEP) * MAP_PTR_STEP;

const _: () = assert!(
    MAP_PTR_BASE + MAP_POINTERS.len() * MAP_PTR_STEP <= MAP_STRIDE,
    "the map record doesn't fit in its stride"
);

/// An event page: which event it belongs to, what activates it, and where
/// its code is.
pub const PAGE_BYTES: usize = 32;
/// No turn slot: the map has no still event that turns around.
pub const TURN_NONE: u32 = 0xFFFF;
/// A leader candidate's colours, as CGRAM words.
pub const ACTOR_COLORS: usize = 2 * OBJ_COLORS;
/// A leader candidate: id, palette, its colours and twelve 24-bit pointers
/// to its poses.
pub const ACTOR_BYTES: usize = 2 + ACTOR_COLORS + 3 * 12;
/// How many distinct graphics command 34 can ask for in a map: the table is
/// copied to RAM, two bytes a graphic, in bank 0. Measured against A
/// Blurred Line, whose map that asks for most asks for six.
pub const ROUTE_GFX_MAX: usize = 8;

/// An event in the position table: x and y in cells, 16 bits each.
pub const EV_STRIDE: usize = 4;
/// How many events the console's RAM holds per map. Measured against A
/// Blurred Line, whose most populated map has 114.
pub const EV_MAX: usize = 120;
/// How many forced routes can be running at once on events.
pub const ROUTE_EV_MAX: usize = 12;
/// How many flashes can be running at once.
pub const FLASH_MAX: usize = 4;
/// How many events with a parallel page there can be at once in a map.
/// Measured against A Blurred Line: forty obstacles of the car chase.
pub const PARALLEL_MAX: usize = 48;
/// A drawn event in the console's RAM: position, sort key, tile and
/// attributes, its event, its pose table entry, where it faces, the pose in
/// VRAM, its speed, whether it is drawn and what its tile lets through.
pub const NPC_STRIDE: usize = 16;
/// In +9: this NPC does not walk.
pub const NPC_STILL: u8 = 0xFF;
/// How many drawn events the table holds: OAM has 128 objects, one is the
/// hero, and the RAM of bank 0 is what sets the cap. Measured against A
/// Blurred Line, whose map with the most has 99.
pub const NPC_MAX: usize = 104;

/// The ChipSet's animation table: one entry per map, eight bytes a family.
pub const ANIM_STRIDE: usize = 16;
pub const ANIM_FAM_STRIDE: usize = ANIM_STRIDE / 2;

/// The two tile families the ChipSet animates, with how many drawings each
/// one has, in the order their runs go to VRAM: by the name the `.inc`
/// gives them and the one the maps' stage does.
pub const FAMILIES: [(&str, &str, usize); 2] = [("agua", "water", 3), ("animado", "animated", 4)];

/// The 4-byte pointer to a map's block, by the record's name.
pub type Labels = HashMap<&'static str, String>;

/// The poses of each changing character, by the labels of their blocks.
pub type PoseLabels = HashMap<(String, i64), Vec<String>>;

/// A map's layout.
pub fn layout_of(map: &Map) -> Result<&'static Layout> {
    vram::LAYOUTS
        .iter()
        .find(|l| l.name == map.layout)
        .ok_or_else(|| {
            Bad::answer(format!(
                "map {}: there is no VRAM layout {:?}",
                map.id, map.layout
            ))
        })
}

/// A drawn event, as the console's table carries it.
#[derive(Debug, Clone)]
pub struct NpcRow {
    pub x: i64,
    pub y: i64,
    pub tile: u32,
    pub palette: u32,
    pub layer: i64,
    pub event: i64,
    pub dir: i64,
    pub pose: i64,
    pub poses: Option<usize>,
    pub speed: i64,
    pub animates: bool,
    pub visible: bool,
    pub tile_pass: Option<i64>,
}

/// The drawn events ready for the console, already sorted the way RM2k draws
/// them: first by layer, then by Y, X and id, from front to back —on the
/// console the object with the lowest OAM index is shown on top—. This
/// initial order also rules afterwards: the console re-sorts the walking ones
/// with an insertion that keeps the order of ties.
///
/// The ones that walk carry which entry of the pose table their twelve are
/// in, so the console uploads them on the fly.
pub fn npc_table(map: &Map) -> Result<Vec<NpcRow>> {
    let sprite = map.sprite.as_ref();
    let movable: BTreeSet<i64> = map.movable.iter().copied().collect();
    let still: BTreeSet<i64> = map.animates_still.iter().copied().collect();
    let mut order: Vec<&crate::request::Npc> = map.npcs.iter().collect();
    // `GetScreenZ`: the layer on top, then Y, X and the id. The table index
    // stands for the id: the events come sorted by id.
    order.sort_by_key(|n| std::cmp::Reverse((n.layer, n.y, n.x, n.event)));
    let mut rows = Vec::new();
    for npc in order {
        let walks = movable.contains(&npc.event);
        let wanted = if walks {
            Slot::Event { event: npc.event }
        } else {
            Slot::Still {
                charset: npc.charset.clone(),
                index: npc.index,
                pose: npc.pose,
            }
        };
        let place = sprite.and_then(|s| s.place.iter().find(|(slot, ..)| *slot == wanted));
        let Some(&(_, block, palette)) = place else {
            return Err(Bad::answer(format!(
                "map {}: event {} is drawn and has no slot in the sprite bank",
                map.id, npc.event
            )));
        };
        let poses = if walks {
            let animated = sprite.map(|s| s.animated.as_slice()).unwrap_or(&[]);
            Some(
                animated
                    .iter()
                    .position(|(c, i)| *c == npc.charset && *i == npc.index)
                    .ok_or_else(|| {
                        Bad::answer(format!(
                            "map {}: event {} walks without its poses",
                            map.id, npc.event
                        ))
                    })?,
            )
        } else {
            None
        };
        rows.push(NpcRow {
            x: npc.x * 16,
            y: npc.y * 16,
            tile: block_tile(block),
            palette,
            layer: npc.layer,
            event: npc.event,
            dir: npc.pose / 3,
            pose: npc.pose,
            poses,
            speed: npc.speed,
            // The still ones with continuous animation: their column comes
            // from the game clock. The walking ones carry it in their route
            // slot.
            animates: still.contains(&npc.event),
            visible: npc.visible,
            tile_pass: npc.tile_pass,
        });
    }
    if rows.len() > NPC_MAX {
        return Err(Bad::answer(format!(
            "map {} has {} NPCs and {NPC_MAX} fit in OAM",
            map.id,
            rows.len()
        )));
    }
    Ok(rows)
}

/// How RM2k sorts: first the layer and only then the Y, in one 16-bit key.
pub fn sort_key(layer: i64, y: i64) -> i64 {
    (layer << 12) | (y & 0x0FFF)
}

/// The table of drawn events: [`NPC_STRIDE`] bytes each.
pub fn npc_bytes(rows: &[NpcRow]) -> Vec<u8> {
    let mut out = Vec::with_capacity(NPC_STRIDE * rows.len());
    let word = |out: &mut Vec<u8>, v: i64| out.extend_from_slice(&(v as u16).to_le_bytes());
    for npc in rows {
        word(&mut out, npc.x);
        word(&mut out, npc.y);
        // The key goes with the Y in pixels, which is how the console
        // computes the hero's.
        word(&mut out, sort_key(npc.layer, npc.y));
        out.push((npc.tile & 0xFF) as u8);
        // vhoopppN: the events marked "above" go at priority 2, the rest
        // share 1 with the hero.
        let priority = if npc.layer == LAYER_ABOVE {
            OBJ_PRIORITY_ABOVE
        } else {
            OBJ_PRIORITY
        };
        out.push((priority | ((npc.palette & 0x07) << 1) | ((npc.tile >> 8) & 0x01)) as u8);
        // The event's index goes always: it is the last tie-breaker of the
        // drawing order.
        out.push(npc.event as u8);
        out.push(npc.poses.map_or(NPC_STILL, |k| k as u8));
        out.push(npc.dir as u8);
        out.push(0);
        // +12: the pose in VRAM, which on loading is its page's.
        out.push(npc.pose as u8);
        // +13: its page's speed, and in bit 7 whether it is a still one with
        // continuous animation.
        out.push((npc.speed | if npc.animates { 0x80 } else { 0 }) as u8);
        // +14: whether it is drawn; +15: the passage bits its tile imposes.
        out.push(u8::from(npc.visible));
        out.push(npc.tile_pass.map_or(0xFF, |t| t as u8));
    }
    out
}

/// The terrain the whole map has, or 0 if it has more than one: 0 is not
/// a terrain, so it says "there is a table".
pub fn terrain_plane(terrain: &[u8]) -> u8 {
    let unique: BTreeSet<u8> = terrain.iter().copied().collect();
    if unique.len() == 1 {
        *unique.iter().next().unwrap()
    } else {
        0
    }
}

/// The terrain block: one byte if the map is flat —shared by every flat map
/// with the same terrain—, the table if not.
pub fn map_terrain(terrain: &[u8]) -> Vec<u8> {
    match terrain_plane(terrain) {
        0 => terrain.to_vec(),
        plane => vec![plane],
    }
}

/// The sprite palettes as CGRAM bytes: sixteen entries each, index 0 the
/// backdrop's —it takes its place even if it is transparent—, and the
/// leftover ones padded.
pub fn sprite_colors_bytes(map: &Map) -> Vec<u8> {
    let mut out = Vec::new();
    if let Some(sprite) = &map.sprite {
        for palette in &sprite.palettes {
            out.extend_from_slice(&cgram_word(BACKDROP).to_le_bytes());
            for &color in palette {
                out.extend_from_slice(&cgram_word(color).to_le_bytes());
            }
            out.resize(out.len() + 2 * (COLORS_PER_PALETTE - 1 - palette.len()), 0);
        }
    }
    out
}

/// Where each event starts, in cells and in the map's order: the whole map,
/// drawn or not, because a forced route can land on an invisible one.
pub fn ev_pos_bytes(map: &Map) -> Result<Vec<u8>> {
    if map.events.len() > EV_MAX {
        return Err(Bad::answer(format!(
            "the map has {} events and the ROM's RAM holds {EV_MAX}",
            map.events.len()
        )));
    }
    let mut out = Vec::new();
    for [x, y] in &map.events {
        out.extend_from_slice(&(*x as u16).to_le_bytes());
        out.extend_from_slice(&(*y as u16).to_le_bytes());
    }
    Ok(out)
}

/// The map's ChipSet animation drawings, one after the other in VRAM order.
pub fn anim_bytes(map: &Map) -> Vec<u8> {
    let mut data = Vec::new();
    for (_, family, _) in FAMILIES {
        if let Some(run) = map.runs.iter().find(|r| r.family == family) {
            for drawing in &run.drawings {
                data.extend_from_slice(drawing);
            }
        }
    }
    data
}

/// What the console decompresses of a map, by class.
pub fn raw_blocks(map: &Map) -> crate::materials::RawBlocks {
    let mut raw = crate::materials::RawBlocks::new();
    raw.insert("map_tiles".into(), map.tiles.clone());
    raw.insert("above_tiles".into(), map.above_tiles.clone());
    raw.insert(
        "sprite_tiles".into(),
        map.sprite
            .as_ref()
            .map_or_else(Vec::new, |s| s.tiles.clone()),
    );
    raw.insert("anim_tiles".into(), anim_bytes(map));
    raw.insert("map_cells".into(), map.cells.clone());
    raw.insert("map_ram".into(), map_ram(&map.blocks, &map.block_pass));
    raw
}

/// Where the record's pointers into what lives behind the grid land: WRAM
/// addresses, which the converter knows because it is the one that lays
/// it out —the grid's second half, then the block table, then its
/// passability—, and the runtime does not compute: `lz2_grid` only
/// decompresses the third stream where the second one ended. If both sides
/// disagreed, `test_carga_descomprimida.py` sees it.
pub fn map_ram_pointers(map: &Map) -> [(&'static str, String); 2] {
    let start = grid_high_used(map.cells.len());
    let pass = start + map.blocks.len();
    [
        ("map_blocks", format!("GRID_HIGH + ${start:04X}")),
        ("block_pass", format!("GRID_HIGH + ${pass:04X}")),
    ]
}

/// The values of a map's record, by field.
fn map_fields(map: &Map, layout: &Layout, rows: &[NpcRow]) -> HashMap<&'static str, i64> {
    let [width, height] = map.tilemap;
    let sprite = map.sprite.as_ref();
    let cell = 8;
    let turn_tile = sprite
        .and_then(|s| s.turn_block)
        .map_or(TURN_NONE, block_tile);
    let fields: [(&'static str, i64); 34] = [
        ("MAP_BW", map.size[0]),
        ("MAP_BH", map.size[1]),
        ("CAM_MAX_X", (width * cell - 256).max(0)),
        ("CAM_MAX_Y", (height * cell - 224).max(0)),
        ("HERO_MAX_X", width * cell - 16),
        ("HERO_MAX_Y", height * cell - 16),
        ("HERO_START_X", map.start[0] * 16),
        ("HERO_START_Y", map.start[1] * 16),
        ("VRAM_TILES", layout.tiles.base.into()),
        ("VRAM_MAP", layout.map.base.into()),
        ("VRAM_SPRITE", layout.sprites.base.into()),
        ("VRAM_WINDOW", layout.window.base.into()),
        ("VRAM_WINDOW_MAP", layout.window_map.base.into()),
        ("MAP_TILES", (map.tiles.len() / BYTES_PER_TILE) as i64),
        ("MAP_CGRAM", (map.cgram.len() / 2) as i64),
        ("ABOVE_TILES", (map.above_tiles.len() / 32) as i64),
        ("ABOVE_CGRAM", (map.above_cgram.len() / 2) as i64),
        (
            "SPRITE_TILES",
            sprite.map_or(0, |s| (s.tiles.len() / 32) as i64),
        ),
        // One more than the colours: sprite index 0 is transparent and also
        // takes its place in CGRAM.
        (
            "SPRITE_CGRAM",
            sprite.map_or(0, |s| (COLORS_PER_PALETTE * s.palettes.len()) as i64),
        ),
        (
            "NPC_COUNT",
            if sprite.is_some() {
                rows.len() as i64
            } else {
                0
            },
        ),
        ("EV_COUNT", map.events.len() as i64),
        (
            "TIMER_BASE",
            sprite.and_then(|s| s.timer).map_or(0, |t| t.0),
        ),
        ("RAIN_BASE", sprite.map_or(0, |s| s.rain.0)),
        ("ACTOR_COUNT", sprite.map_or(0, |s| s.actors.len() as i64)),
        ("PAGE_COUNT", map.pages.len() as i64),
        (
            "ROUTE_GRAPHIC_COUNT",
            sprite.map_or(0, |s| s.route_gfx.len() as i64),
        ),
        (
            "OBSEL_VALUE",
            (0x20 | (layout.sprites.base / 0x2000)).into(),
        ),
        (
            "BG12NBA_VALUE",
            (((layout.above.base / 0x1000) << 4) | (layout.tiles.base / 0x1000)).into(),
        ),
        ("ABOVE_FIRST", map.above_first * COLORS_PER_PALETTE as i64),
        (
            "TIMER_PAL",
            sprite.and_then(|s| s.timer).and_then(|t| t.1).unwrap_or(0),
        ),
        ("RAIN_PAL", sprite.map_or(0, |s| s.rain.1)),
        (
            "TURN_TILE4",
            if sprite.is_some() && turn_tile != TURN_NONE {
                (turn_tile / 4).into()
            } else {
                0xFF
            },
        ),
        ("TERRAIN_OUTSIDE", map.terrain_outside),
        ("TERRAIN_PLANE", terrain_plane(&map.block_terrain).into()),
    ];
    fields.into_iter().collect()
}

/// The names of the record's fields, so that the runtime does not repeat
/// them: if a field is added here, there is no number to update there.
pub fn offsets() -> String {
    let mut out = vec!["; Where each field falls inside a map's record.".to_string()];
    let mut used = 0;
    for (name, _) in MAP_SCALARS {
        out.push(format!("M_{name:<14} = {used}"));
        used += 2;
    }
    for (name, _) in MAP_BYTES {
        out.push(format!("M_{name:<14} = {used}"));
        used += 1;
    }
    for (number, name) in MAP_POINTERS.iter().enumerate() {
        out.push(format!(
            "M_PTR_{:<10} = {}",
            name.to_uppercase(),
            MAP_PTR_BASE + number * MAP_PTR_STEP
        ));
    }
    out.join("\n")
}

/// The table the console walks to know what to load. `labels` says, per
/// map, which block each pointer points to.
pub fn map_table(maps: &[Map], labels: &[Labels], rows: &[Vec<NpcRow>]) -> Result<String> {
    let mut out: Vec<String> = vec![
        ".segment \"RODATA\"".into(),
        format!("; The map table: one record of {MAP_STRIDE} bytes per map, with everything"),
        "; the ROM needs to load it. The pointers are 24 bits because the".into(),
        "; data lives spread over all the banks.".into(),
        ";".into(),
        "; **It lives in RODATA and is read with `lda f:map_table + campo, x`.**".into(),
        "; It is 144 bytes per map, and in bank 0 —where the table has to be".into(),
        "; if it is walked with the data bank register— that was enough for".into(),
        "; fourteen maps and no more: with the whole of Lashe City it is 33".into(),
        "; and the bank went over by 3739 bytes. It is the third table that".into(),
        "; moves for the same reason; the price is one byte per instruction".into(),
        "; and that the two uses with Y had to switch to X, because long".into(),
        "; absolute indexed addressing only exists with X.".into(),
        ";".into(),
        "; **Whole within one bank**, which is what `.block` asks for. In".into(),
        "; LoROM what follows $03FFFF isn't bank 4's ROM but RAM, and the".into(),
        "; first version of this landed at $03FFB1: the 144 bytes of the only".into(),
        "; record were split in half and map 5 started black. The other maps".into(),
        "; of the suite didn't see it because their table landed somewhere".into(),
        "; else, which is exactly the kind of error that shows up when adding".into(),
        "; a byte anywhere else.".into(),
        format!(".block {}", MAP_STRIDE * maps.len()),
        "map_table:".into(),
    ];
    for (number, map) in maps.iter().enumerate() {
        let fields = map_fields(map, layout_of(map)?, &rows[number]);
        // The console's tests read the table order from this line.
        out.push(format!(
            "    ; --- {number}: map {} {} ---",
            map.id,
            quoted(&map.name)
        ));
        let mut used = 0;
        for (name, comment) in MAP_SCALARS {
            let comment = if comment.is_empty() {
                String::new()
            } else {
                format!("  {comment}")
            };
            out.push(format!(
                "    .word {:<6} ; +{used:<3} {name}{comment}",
                fields[name]
            ));
            used += 2;
        }
        for (name, comment) in MAP_BYTES {
            out.push(format!(
                "    .byte ${:02X}    ; +{used:<3} {name}  {comment}",
                fields[name]
            ));
            used += 1;
        }
        let padding = MAP_PTR_BASE - used;
        // Without padding the line does not go: a `.byte` without operands
        // is an error for ca65.
        if padding > 0 {
            out.push(format!(
                "    .byte {} ; +{used}  padding up to the pointers",
                vec!["$00"; padding].join(",")
            ));
        }
        used += padding;
        for name in MAP_POINTERS {
            let label = &labels[number][name];
            out.push(format!(
                "    .byte <({label}), >({label}), ^({label}), $00 ; +{used}  {name}"
            ));
            used += MAP_PTR_STEP;
        }
        if used < MAP_STRIDE {
            out.push(format!(
                "    .byte {}",
                vec!["$00"; MAP_STRIDE - used].join(",")
            ));
        }
    }
    // And each map's RM2k id, by index: `MemorizeLocation` writes it into a
    // variable and `RecallToLocation` looks it up.
    out.push(String::new());
    out.push("; Each map's RM2k id, in the order of `map_table`.".into());
    out.push(format!(".block {}", 2 * maps.len()));
    out.push("map_rm2k:".into());
    out.push(format!(
        "    .word {}",
        maps.iter()
            .map(|m| m.id.to_string())
            .collect::<Vec<_>>()
            .join(", ")
    ));
    Ok(out.join("\n"))
}

/// One entry per map with both runs of the ChipSet's animation already
/// resolved: per family, the VRAM address in words, where drawing 0 is
/// inside the block, how many bytes a drawing is, and how many tiles. The
/// padding of the second family carries whether the map has some still
/// event with continuous animation.
pub fn anim_table(maps: &[Map], rows: &[Vec<NpcRow>]) -> Result<String> {
    let mut out: Vec<String> = vec![
        ".segment \"RODATA\"".into(),
        format!("; The ChipSet animation, one entry of {ANIM_STRIDE} bytes per map."),
        // `rom/src/` and not `tools/runtime/`, on purpose: it goes into the
        // `.inc`, and what is emitted is not touched yet.
        "; See `anim_table` in tools/port/snes_convert.py and `anim_flush` in rom/src/chipset_animation.s.".into(),
        ";".into(),
        "; **It lives in RODATA and is read with `lda f:anim_table + campo, x`**,".into(),
        "; for the same reason as `map_table`: it is 16 bytes per map, and".into(),
        "; with the maps the tests ask for bank 0 went over by 361. Whole".into(),
        "; within one bank, because what follows $xxFFFF isn't the next one's ROM.".into(),
        format!(".block {}", ANIM_STRIDE * maps.len()),
        "anim_table:".into(),
    ];
    for (number, map) in maps.iter().enumerate() {
        let layout = layout_of(map)?;
        out.push(format!(
            "    ; --- map {} {} ---",
            map.id,
            quoted(&map.name)
        ));
        let mut offset = 0;
        for (k, (name, family, count)) in FAMILIES.iter().enumerate() {
            let run = map.runs.iter().find(|r| r.family == *family);
            let tiles = run.map_or(0, |r| r.tiles);
            let vram = i64::from(layout.tiles.base)
                + run.map_or(0, |r| r.base) * BYTES_PER_TILE as i64 / 2;
            out.push(format!("    .word {vram:<6} ; VRAM of {name}"));
            out.push(format!(
                "    .word {offset:<6} ; drawing 0, inside the block"
            ));
            out.push(format!(
                "    .word {:<6} ; bytes per drawing",
                tiles * BYTES_PER_TILE as i64
            ));
            let padding =
                u8::from(k == FAMILIES.len() - 1 && rows[number].iter().any(|n| n.animates));
            out.push(format!(
                "    .byte {tiles}, {padding}   ; {tiles} tile(s){}",
                if padding != 0 {
                    ", and the map has still events that animate"
                } else {
                    ""
                }
            ));
            offset += tiles * BYTES_PER_TILE as i64 * *count as i64;
        }
    }
    Ok(out.join("\n"))
}

/// The map's event pages, with the pointer to their code: `evcode` is the
/// label of its code block, which two maps can share.
///
/// It does not go through [`block`] because its pointers are symbolic, but
/// it is declared with `.block`: the console walks it with `[page_ptr], y`,
/// and a table that crosses a bank continues wherever the next bank is.
pub fn page_table(map: &PageMap, number: usize, evcode: &str) -> String {
    let mut out = vec![
        format!(".block {}", PAGE_BYTES * map.pages.len()),
        format!("pages_{number}:"),
    ];
    let events_where = |f: &dyn Fn(&Page) -> bool| -> BTreeSet<i64> {
        map.pages.iter().filter(|p| f(p)).map(|p| p.event).collect()
    };
    // Which events have some page with its own route: the refresh only looks
    // at the pages of those.
    let with_route = events_where(&|p| p.own_route.is_some());
    // And which ones have some automatic or parallel page that compiled:
    // bit 7, "look at this event's pages in the refresh".
    let with_autostart = events_where(&|p| {
        (p.trigger == TRIGGER_AUTOSTART || p.trigger == TRIGGER_PARALLEL) && p.has_code
    });
    // Bit 5: the graphic follows the page, or the event only appears and
    // disappears with it —the console tells them apart by whether the row
    // walks—.
    let follows = |e: i64| map.changing.contains(&e) || map.appearing.contains(&e);
    for page in map.pages {
        let pointer = if page.has_code {
            let dest = format!("{evcode} + {}", page.offset);
            format!("<({dest}), >({dest}), ^({dest})")
        } else {
            "$00, $00, $00".to_string()
        };
        out.push(format!(
            "    .word {:<4} ; +0  the event it belongs to",
            page.event
        ));
        out.push(format!("    .byte {:<4} ; +2  its page number", page.page));
        out.push(format!(
            "    .byte {:<4} ; +3  what triggers it",
            page.trigger
        ));
        out.push(format!(
            "    .word {:<4} ; +4  switch it asks for, or 0",
            page.switch_a
        ));
        out.push(format!(
            "    .word {:<4} ; +6  the second, or 0",
            page.switch_b
        ));
        out.push(format!("    .byte {pointer} ; +8  its code"));
        out.push(format!(
            "    .byte {:<4} ; +11 the actor it asks for in the party, or 0",
            page.actor
        ));
        out.push(format!(
            "    .byte {:<4} ; +12 its layer: 1 is the hero's, the one that blocks its way",
            page.layer
        ));
        let bit = |on: bool, b: i64| if on { b } else { 0 };
        if let Some(own) = &page.own_route {
            // Bit 0 it has one, 1 it repeats, 2 it skips what is blocked, 3
            // it always faces the same way, 4 the animation continues while
            // still.
            let flags = 1
                | bit(own.repeats, 2)
                | bit(own.skippable, 4)
                | bit(own.fixed_direction, 8)
                | bit(own.animation_continues, 16)
                | 64
                | bit(follows(page.event), 32)
                | bit(with_autostart.contains(&page.event), 128);
            let dest = format!("{evcode} + {}", page.route_offset);
            out.push(format!(
                "    .byte {flags:<4} ; +13 the flags of its own route"
            ));
            out.push(format!(
                "    .byte {:<4} ; +14 its frequency",
                own.frequency
            ));
            out.push(format!("    .byte {:<4} ; +15 and its speed", own.speed));
            out.push(format!(
                "    .byte <({dest}), >({dest}), ^({dest}) ; +16 its commands"
            ));
            out.push(format!("    .byte {:<4} ; +19 how many", own.orders));
        } else {
            let flags = bit(with_route.contains(&page.event), 64)
                | bit(follows(page.event), 32)
                | bit(with_autostart.contains(&page.event), 128)
                | bit(page.fixed_direction, 8);
            out.push(format!(
                "    .byte {flags:<4} ; +13 no own route; bit 6 says whether another page of the \
                 event has one, 5 whether the graphic follows the page, 7 whether the event has \
                 some automatic one, 3 whether it always faces the same way"
            ));
            out.push(format!(
                "    .byte {:<4} ; +14 its frequency",
                page.frequency
            ));
            out.push(format!(
                "    .byte {:<4} ; +15 and its speed, that of a route forced on the event",
                page.speed
            ));
            out.push("    .byte 0,0,0,0".into());
        }
        // +20: what the page draws, for the events that change graphic.
        match page.oam {
            None => out.push("    .byte $00, $00, $00, $FF ; +20 no graphic".into()),
            Some([a, b, c, d]) => out.push(format!(
                "    .byte ${a:02X}, ${b:02X}, ${c:02X}, ${d:02X} ; +20 its graphic: tile, attributes, \
                 pose, passage"
            )),
        }
        // +24: the variable condition: the slot or $FF, how it is compared
        // and against what, signed.
        match page.variable {
            None => {
                out.push("    .byte $FF, 0 ; +24 no variable condition".into());
                out.push("    .word 0".into());
            }
            Some((slot, comparison, against)) => {
                out.push(format!(
                    "    .byte {slot}, {comparison} ; +24 the variable it asks for and the comparison"
                ));
                out.push(format!("    .word {} ; +26 against what", against & 0xFFFF));
            }
        }
        out.push(format!(
            "    .word {:<4} ; +28 the item it asks for, or 0",
            page.item
        ));
        // +30: the turn toward the hero: which entry of `npc_poses` the poses
        // of its graphic are in, or $FF, and its pose.
        let k = match &page.graphic {
            Some((charset, index, _)) if page.turns && map.turning.contains(&page.event) => map
                .animated
                .iter()
                .position(|(c, i)| c == charset && i == index),
            _ => None,
        };
        let pose = match (&k, &page.graphic) {
            (Some(_), Some((_, _, pose))) => *pose,
            _ => 0,
        };
        out.push(format!(
            "    .byte ${:02X}, {pose} ; +30 the turn: its poses and its pose",
            k.map_or(0xFF, |k| k as i64)
        ));
    }
    if map.pages.is_empty() {
        // A label cannot be left empty.
        out.push("    .byte $00".into());
    }
    out.join("\n")
}

/// RM2k's triggers the page table looks at.
pub const TRIGGER_AUTOSTART: i64 = 3;
pub const TRIGGER_PARALLEL: i64 = 4;

/// What a page table reads of its map.
pub struct PageMap<'a> {
    pub pages: &'a [Page],
    pub changing: &'a [i64],
    pub appearing: &'a [i64],
    pub turning: &'a [i64],
    /// The characters that change pose, in the order of the pose table.
    pub animated: &'a [(String, i64)],
}

impl<'a> PageMap<'a> {
    pub fn of(map: &'a Map) -> Self {
        PageMap {
            pages: &map.pages,
            changing: &map.changing,
            appearing: &map.appearing,
            turning: &map.turning,
            animated: map.sprite.as_ref().map_or(&[], |s| s.animated.as_slice()),
        }
    }
}

/// The pointers to the twelve poses of each character that changes pose,
/// one entry per character —the same index the drawn event's row carries
/// in +9 and the leader in its table—.
fn npc_poses_asm(number: usize, animated: &[(String, i64)], poses: &PoseLabels) -> String {
    let mut out = vec![
        format!(".block {}", 3 * SPRITE_POSES * animated.len().max(1)),
        format!("npc_poses_{number}:"),
    ];
    for pair in animated {
        for label in &poses[pair] {
            out.push(format!("    .byte {}", pointer(label)));
        }
    }
    if animated.is_empty() {
        out.push("    .byte $00".into());
    }
    out.join("\n")
}

/// The leader candidates: id, palette, their fifteen colours and the
/// pointer to each of their poses; twelve at `$FFFFFF` for one without a
/// graphic, which is the sentinel `place_hero` looks at.
fn actor_table_asm(number: usize, map: &Map, poses: &PoseLabels) -> String {
    let sprite = map.sprite.as_ref();
    let actors = sprite.map_or(&[][..], |s| s.actors.as_slice());
    let animated = sprite.map_or(&[][..], |s| s.animated.as_slice());
    let mut out = vec![
        format!(".block {}", ACTOR_BYTES * actors.len().max(1)),
        format!("actor_table_{number}:"),
    ];
    for (actor, palette, k, colors) in actors {
        out.push(format!(
            "    .byte ${:02X}, ${:02X}",
            actor & 0xFF,
            palette & 0x07
        ));
        let mut words = colors.clone();
        words.resize(OBJ_COLORS.max(words.len()), 0);
        out.push(format!(
            "    .byte {}",
            words
                .iter()
                .map(|w| format!("${:02X},${:02X}", w & 0xFF, w >> 8))
                .collect::<Vec<_>>()
                .join(",")
        ));
        match k {
            None => out.extend(std::iter::repeat_n(
                "    .byte $FF, $FF, $FF".to_string(),
                SPRITE_POSES,
            )),
            Some(k) => out.extend(
                poses[&animated[*k]]
                    .iter()
                    .map(|l| format!("    .byte {}", pointer(l))),
            ),
        }
    }
    if actors.is_empty() {
        out.push("    .byte $00".into());
    }
    out.join("\n")
}

/// A map's data blocks, and which label each record pointer gets.
pub fn map_data(
    map: &Map,
    number: usize,
    rows: &[NpcRow],
    poses: &PoseLabels,
    materials: &mut Materials,
) -> Result<(String, Labels)> {
    let sprite = map.sprite.as_ref();
    let route_graphic: Vec<u8> = sprite
        .map(|s| {
            s.route_gfx
                .iter()
                .flat_map(|&(k, p)| [k as u8, p as u8])
                .collect()
        })
        .unwrap_or_default();
    let pairs: [(&'static str, Vec<u8>); 12] = [
        ("map_tiles", map.tiles.clone()),
        ("map_cgram", map.cgram.clone()),
        ("above_tiles", map.above_tiles.clone()),
        ("above_cgram", map.above_cgram.clone()),
        (
            "sprite_tiles",
            sprite.map_or_else(Vec::new, |s| s.tiles.clone()),
        ),
        ("sprite_cgram", sprite_colors_bytes(map)),
        // The terrain per block, or one byte for a flat map: see
        // `TERRAIN_PLANE`.
        ("block_terrain", map_terrain(&map.block_terrain)),
        (
            "npc_table",
            if sprite.is_some() {
                npc_bytes(rows)
            } else {
                Vec::new()
            },
        ),
        // Two bytes per graphic of command 34: its entry in `npc_poses` —or
        // $FF, which is hiding— and its palette.
        ("route_graphic", route_graphic),
        ("ev_pos", ev_pos_bytes(map)?),
        ("evcode", map.evcode.clone()),
        ("anim_tiles", anim_bytes(map)),
    ];
    let mut labels = Labels::new();
    let mut out = Vec::new();
    for (name, data) in pairs {
        let (label, text) = if COMPRESSED_KINDS.contains(&name) {
            materials.store_compressed(name, &data)
        } else {
            materials.store(name, &data)
        };
        labels.insert(name, label);
        if !text.is_empty() {
            out.push(text);
        }
    }
    let animated = sprite.map_or(&[][..], |s| s.animated.as_slice());
    out.push(npc_poses_asm(number, animated, poses));
    out.push(actor_table_asm(number, map, poses));
    // The grid, in its two streams, and what lives behind it in a third:
    // see `lz2_grid`.
    let ram = map_ram(&map.blocks, &map.block_pass);
    let (label, text) =
        materials.store_compressed_joined(&[("map_cells", &map.cells), ("map_ram", &ram)]);
    labels.insert("map_cells", label);
    if !text.is_empty() {
        out.push(text);
    }
    for (name, address) in map_ram_pointers(map) {
        labels.insert(name, address);
    }
    out.push(page_table(&PageMap::of(map), number, &labels["evcode"]));
    // The three that are not shared carry symbolic pointers inside, whose
    // bytes the linker sets: there is no content to compare them by.
    for name in ["npc_poses", "actor_table", "pages"] {
        labels.insert(name, format!("{name}_{number}"));
    }
    Ok((out.join("\n"), labels))
}

/// That what each map spends fits the VRAM layout it got.
pub fn check_counts(map: &Map) -> Result<()> {
    let layout = layout_of(map)?;
    let sprite_tiles = map.sprite.as_ref().map_or(0, |s| s.tiles.len() / 32);
    for (count, name, room) in [
        (
            map.tiles.len() / BYTES_PER_TILE,
            "tiles",
            layout.tiles.count,
        ),
        (map.above_tiles.len() / 32, "encima", layout.above.count),
        (sprite_tiles, "sprites", layout.sprites.count),
    ] {
        if count > room as usize {
            return Err(Bad::answer(format!(
                "map {}: with this VRAM layout, {name} needs {count} tiles and {room} fit",
                map.id
            )));
        }
    }
    if let Some(sprite) = &map.sprite {
        if sprite.route_gfx.len() > ROUTE_GFX_MAX {
            return Err(Bad::answer(format!(
                "map {} has {} graphics of command 34 and {ROUTE_GFX_MAX} fit: see ROUTE_GFX_MAX",
                map.id,
                sprite.route_gfx.len()
            )));
        }
    }
    Ok(())
}

/// The twelve poses of each character that changes pose, **once per
/// quantization** and not once per cartridge: two maps that draw the same
/// character with the same palette share its bank, and one that quantized it
/// differently carries its own. And each pose once, even if several banks
/// repeat it: the pose tables point to it.
pub struct Poses {
    /// The section of the `.inc`.
    pub text: String,
    /// Per map, the labels of each character's poses.
    pub per_map: Vec<PoseLabels>,
    /// What it says, in order.
    pub notes: Vec<String>,
}

pub fn poses(maps: &[Map]) -> Result<Poses> {
    let mut global: Vec<((String, i64), Vec<u8>)> = Vec::new();
    let mut banks: Vec<Vec<u8>> = Vec::new();
    let mut index_per_map: Vec<Vec<((String, i64), usize)>> = Vec::new();
    let mut notes = Vec::new();
    for map in maps {
        let mut own = Vec::new();
        for (charset, index, hex) in map.sprite.as_ref().map_or(&[][..], |s| s.banks.as_slice()) {
            let data = crate::hex::decode(hex)?;
            let pair = (charset.clone(), *index);
            let found = global.iter().position(|(p, d)| *p == pair && *d == data);
            let g = match found {
                Some(g) => g,
                None => {
                    if global.iter().any(|(p, _)| *p == pair) {
                        notes.push(format!(
                            "  map {}: {charset}:{index} goes with a pose bank of its own, quantized \
                             differently than in another map",
                            map.id
                        ));
                    }
                    global.push((pair.clone(), data.clone()));
                    banks.push(data);
                    banks.len() - 1
                }
            };
            own.push((pair, g));
        }
        index_per_map.push(own);
    }
    let mut text =
        String::from("; --- the poses of the characters that change pose, for the whole ROM ---\n");
    let mut label_of: HashMap<Vec<u8>, String> = HashMap::new();
    let mut bank_poses: Vec<Vec<String>> = Vec::new();
    for data in &banks {
        let mut theirs = Vec::new();
        for pose in 0..SPRITE_POSES {
            let bytes = data
                [(pose * POSE_BYTES).min(data.len())..((pose + 1) * POSE_BYTES).min(data.len())]
                .to_vec();
            let label = match label_of.get(&bytes) {
                Some(l) => l.clone(),
                None => {
                    let l = format!("pose_{}", label_of.len());
                    let _ = writeln!(text, "{}", block(&l, &bytes));
                    label_of.insert(bytes, l.clone());
                    l
                }
            };
            theirs.push(label);
        }
        bank_poses.push(theirs);
    }
    text.push('\n');
    let total = SPRITE_POSES * banks.len();
    notes.push(format!(
        "  poses: {} distinct out of {total}, {:.1} KB less",
        label_of.len(),
        (total - label_of.len()) as f64 * POSE_BYTES as f64 / 1024.0
    ));
    let per_map = index_per_map
        .into_iter()
        .map(|own| {
            own.into_iter()
                .map(|(pair, g)| (pair, bank_poses[g].clone()))
                .collect()
        })
        .collect();
    Ok(Poses {
        text,
        per_map,
        notes,
    })
}

/// What [`maps`] writes: three pieces of the `.inc` and what it says.
pub struct Written {
    /// The record's offsets.
    pub offsets: String,
    /// The poses, the LZ2 caps and each map's data blocks, in `RODATA`.
    pub maps: String,
    /// The map table and the ChipSet animation's.
    pub tables: String,
    /// What it says while it writes, in order.
    pub notes: Vec<String>,
    /// What was shared and compressed.
    pub report: Vec<String>,
    /// Per map, how many frames the console takes to decompress it.
    pub frames: Vec<f64>,
    /// Per map, what the console decompresses, uncompressed.
    pub raw: Vec<crate::materials::RawBlocks>,
}

/// Everything the cartridge carries per map.
pub fn maps(maps: &[Map]) -> Result<Written> {
    for map in maps {
        check_counts(map)?;
    }
    let rows: Vec<Vec<NpcRow>> = maps.iter().map(npc_table).collect::<Result<_>>()?;
    let raw: Vec<crate::materials::RawBlocks> = maps.iter().map(raw_blocks).collect();
    let refs: Vec<(i64, &crate::materials::RawBlocks)> =
        maps.iter().zip(&raw).map(|(m, r)| (m.id, r)).collect();
    let compressed = crate::materials::compress_blocks(&refs)?;
    let frames = raw
        .iter()
        .map(|r| crate::materials::decompress_frames(r, &compressed))
        .collect();
    let poses = poses(maps)?;
    let mut text = poses.text;
    let _ = write!(
        text,
        "; The LZ2 caps, which decompress.s enforces\n\
         LZ2_CAP_BACKDROP = ${:04X}\n\
         LZ2_CAP_ABOVE_Y_SPRITES = ${:04X}\n\
         LZ2_CAP_ANIM = ${:04X}\n\
         LZ2_CAP_GRID = ${:05X}\n\n",
        crate::materials::LZ2_CAP_BACKDROP,
        crate::materials::LZ2_CAP_ABOVE_AND_SPRITES,
        crate::materials::LZ2_CAP_ANIM,
        crate::materials::LZ2_CAP_GRID
    );
    let mut materials = Materials::new(true, compressed);
    let mut labels = Vec::new();
    for (number, map) in maps.iter().enumerate() {
        // The console's tests read the table order from this line.
        let _ = writeln!(
            text,
            "; --- {number}: map {} {} ---",
            map.id,
            quoted(&map.name)
        );
        let (data, theirs) = map_data(
            map,
            number,
            &rows[number],
            &poses.per_map[number],
            &mut materials,
        )?;
        text.push_str(&data);
        text.push('\n');
        labels.push(theirs);
    }
    let tables = format!(
        "{}\n\n{}\n",
        map_table(maps, &labels, &rows)?,
        anim_table(maps, &rows)?
    );
    Ok(Written {
        offsets: offsets(),
        maps: text,
        tables,
        notes: poses.notes,
        report: materials.report(),
        frames,
        raw,
    })
}
