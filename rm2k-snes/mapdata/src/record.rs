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
use crate::materials::{
    grid_high_used, map_ram, Materials, COMPRESSED_KINDS, HALF_GRID, LZ2_CAP_CODE,
};
use crate::objects::{
    block_tile, page_oam, pose_record, LAYER_ABOVE, OBJ_COLORS, OBJ_PRIORITY, OBJ_PRIORITY_ABOVE,
    POSE_BYTES, POSE_TILES, SPRITE_POSES, TILE_BYTES,
};
use crate::request::{Map, Page, Slot};
use crate::snes::{cgram_word, BYTES_PER_TILE, COLORS_PER_PALETTE};
use crate::text::quoted;
use crate::vram::{self, Layout};
use std::collections::{BTreeMap, BTreeSet, HashMap};
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
/// How many pages a map's table can have: the console walks it with a
/// 16-bit offset (`page_ofs`, and `pick_by_ev` keeps it per event, with
/// `$FFFD` and up as sentinels), so the last page has to start below
/// `$FFFD` —2048 pages of 32 bytes—. It is the bound of the test pages too,
/// which are one event of one map, with that map's own pages.
pub const MAX_PAGES: usize = 0x1_0000 / PAGE_BYTES;
/// No turn slot: the map has no still event that turns around.
pub const TURN_NONE: u32 = 0xFFFF;
/// A leader candidate's colours, as CGRAM words.
pub const ACTOR_COLORS: usize = 2 * OBJ_COLORS;
/// A leader candidate: id, palette, its colours and twelve 24-bit pointers
/// to its poses.
pub const ACTOR_BYTES: usize = 2 + ACTOR_COLORS + 3 * 12;
/// How many distinct graphics command 34 can ask for in a map: the route
/// carries the index in a byte. The RAM table is not this big: it is sized
/// by the cartridge's map that asks for most —`route_gfx_buf` in the
/// runtime's far_ram.s—. Until 2026-10-19 it was eight, in bank 0, and
/// Frozen World's plate menu asks for 28.
pub const ROUTE_GFX_MAX: usize = 255;

/// An event in the position table: x and y in cells, 16 bits each.
pub const EV_STRIDE: usize = 4;
/// How many events the console's RAM holds per map. Measured against A
/// Blurred Line, whose most populated map has 114.
pub const EV_MAX: usize = 120;
/// A twin behind the positions: x and y in cells and its event's index,
/// 16 bits each. See [`ev_pos_bytes`].
pub const TWIN_STRIDE: usize = 6;
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
/// How many drawn events the table holds: Wally's, which leaves out the
/// rows that do not fit.
pub const NPC_MAX: usize = wally::sprites::npc::NPC_MAX;

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
    /// Whether others animate in its slot: it uploads its pose even hidden.
    pub leads: bool,
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
    let with: BTreeMap<i64, i64> = map
        .animates_with
        .iter()
        .map(|&[e, whose]| (e, whose))
        .collect();
    let leaders: BTreeSet<i64> = with.values().copied().collect();
    let mut order: Vec<&crate::request::Npc> = map.npcs.iter().collect();
    // `GetScreenZ`: the layer on top, then Y, X and the id. The table index
    // stands for the id: the events come sorted by id.
    order.sort_by_key(|n| std::cmp::Reverse((n.layer, n.y, n.x, n.event)));
    let mut rows = Vec::new();
    let shared = sprite.and_then(|s| s.shared.as_ref());
    for npc in order {
        let walks = movable.contains(&npc.event);
        // One that takes turns in a shared slot is drawn with its own
        // character's palette: the slot's is only the first one's.
        let turns = shared.and_then(|s| s.events.iter().find(|e| e.0 == npc.event));
        let wanted = if let Some(&(_, slot, ..)) = turns {
            Slot::Shared {
                shared: slot as i64,
            }
        } else if walks {
            Slot::Event { event: npc.event }
        } else if let Some(&whose) = with.get(&npc.event) {
            // A still one that animates in its twin's slot: it shows the
            // pose the other uploads, and uploads nothing.
            Slot::Event { event: whose }
        } else {
            Slot::Still {
                charset: npc.charset.clone(),
                index: npc.index,
                pose: npc.pose,
            }
        };
        // In a map with a cache of slots nobody has one: the row carries the
        // still pose it starts with in its tile byte —0 if it walks—, and
        // the console finds it a slot when it comes into view. See
        // `cache_table`.
        //
        // A still one that animates in its twin's slot asks for that one's
        // own: it carries its key, 128 plus the twin, in the tile byte, and
        // its twelve poses, which the console uploads from when it is the
        // first of them to come into view. See `cache_want`.
        let cached = sprite
            .and_then(|s| s.cache.as_ref())
            .map(|c| c.events.iter().find(|e| e.0 == npc.event));
        let twin = with.get(&npc.event).copied().filter(|_| cached.is_some());
        let (tile, palette) = match cached {
            Some(Some(&(_, _, palette))) if twin.is_some() => {
                let whose = twin.unwrap();
                if !(0..0x80).contains(&whose) {
                    return Err(Bad::answer(format!(
                        "map {}: event {} animates in {whose}'s slot of the cache, and a cache's key names \
                         events below 128",
                        map.id, npc.event
                    )));
                }
                (0x80 | whose as u32, palette)
            }
            Some(Some(&(_, key, palette))) => (key.unwrap_or(0), palette),
            Some(None) => {
                return Err(Bad::answer(format!(
                    "map {}: event {} is drawn and the cache does not know it",
                    map.id, npc.event
                )))
            }
            None => {
                let place = sprite.and_then(|s| s.place.iter().find(|(slot, ..)| *slot == wanted));
                let Some(&(_, block, palette)) = place else {
                    return Err(Bad::answer(format!(
                        "map {}: event {} is drawn and has no slot in the sprite bank",
                        map.id, npc.event
                    )));
                };
                (block_tile(block), turns.map_or(palette, |t| t.3))
            }
        };
        let poses = if walks || twin.is_some() {
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
            tile,
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
            animates: still.contains(&npc.event) || twin.is_some(),
            leads: leaders.contains(&npc.event),
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
        // +13: its page's speed, in bit 7 whether it is a still one with
        // continuous animation, and in bit 6 whether others animate in its
        // slot —`animate_still` uploads its pose even when it is hidden—.
        out.push(
            (npc.speed | if npc.animates { 0x80 } else { 0 } | if npc.leads { 0x40 } else { 0 })
                as u8,
        );
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
///
/// Behind them, the twins: a word with how many, and then
/// [`TWIN_STRIDE`] bytes each —x and y in cells, and the index of the event
/// whose row it shares—. The load copies only the positions, `EV_COUNT`
/// of them, to `ev_pos_buf`; `twin_in_cell` reads the rest in place.
pub fn ev_pos_bytes(map: &Map) -> Result<Vec<u8>> {
    if map.events.len() > EV_MAX {
        return Err(Bad::answer(format!(
            "map {} has {} events and the ROM's RAM holds {EV_MAX}",
            map.id,
            map.events.len()
        )));
    }
    let mut out = Vec::new();
    for [x, y] in &map.events {
        out.extend_from_slice(&(*x as u16).to_le_bytes());
        out.extend_from_slice(&(*y as u16).to_le_bytes());
    }
    out.extend_from_slice(&(map.twins.len() as u16).to_le_bytes());
    for &[x, y, owner] in &map.twins {
        if !(0..map.events.len() as i64).contains(&owner) {
            return Err(Bad::answer(format!(
                "map {}: a twin at ({x}, {y}) shares the row of event {owner}, and the map has {}",
                map.id,
                map.events.len()
            )));
        }
        for v in [x, y, owner] {
            out.extend_from_slice(&(v as u16).to_le_bytes());
        }
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
    raw.insert("map_cells".into(), map.grid());
    raw.insert("map_ram".into(), map_ram(&map.blocks, &map.block_pass));
    // A map whose bytecode stays in the cartridge decompresses none: see
    // [`code_in_rom`].
    let code = if code_in_rom(map) {
        Vec::new()
    } else {
        map.evcode.clone()
    };
    raw.insert("map_code".into(), code);
    raw
}

/// The largest block of a map's bytecode in the cartridge: one bank,
/// because the routes and the battle animation add their offsets to the
/// page's pointer without carrying into the bank byte —see `op_route`—, so
/// a page cannot cross one. A map with more goes in several blocks, each
/// with whole pages: see [`rom_code_chunks`].
pub const ROM_CODE_MAX: usize = 0x10000;

/// A map's code block cut into pieces of up to [`ROM_CODE_MAX`] bytes, each
/// with whole pages and routes, as `(where it starts in the block, its
/// bytes)`. It can be cut anywhere a page or a route starts because nothing
/// in a page points into another: its jumps are offsets from where it
/// starts —see `lay_out_code` in the converter—.
pub fn rom_code_chunks(map: &Map) -> Result<Vec<(usize, &[u8])>> {
    let code = &map.evcode;
    let mut starts: BTreeSet<usize> = BTreeSet::from([0, code.len()]);
    for page in &map.pages {
        if page.has_code {
            starts.insert(page.offset);
        }
        if page.own_route.is_some() {
            starts.insert(page.route_offset);
        }
    }
    let starts: Vec<usize> = starts.into_iter().filter(|&s| s <= code.len()).collect();
    let mut chunks: Vec<(usize, &[u8])> = Vec::new();
    let mut from = 0;
    for pair in starts.windows(2) {
        let (start, end) = (pair[0], pair[1]);
        if end - start > ROM_CODE_MAX {
            return Err(Bad::answer(format!(
                "map {}: a page's bytecode is {} bytes, and one page has to fit in a bank, \
                 {ROM_CODE_MAX}: see `rom_code_chunks` in rm2k-snes-mapdata",
                map.id,
                end - start
            )));
        }
        if end - from > ROM_CODE_MAX {
            chunks.push((from, &code[from..start]));
            from = start;
        }
    }
    if from < code.len() || chunks.is_empty() {
        chunks.push((from, &code[from..]));
    }
    Ok(chunks)
}

/// Whether a map's bytecode stays in the cartridge, uncompressed, instead of
/// going to WRAM behind its grid: only when it does not fit there, either
/// over its LZ2 reserve —which is also what `CODE_CARRY` holds— or over what
/// the grid and the block table leave of bank $7F's upper half. The other
/// maps stay as they were, byte for byte.
///
/// The page table then points into the cartridge, and nothing else in the
/// runtime has to know: the interpreter, the routes and the battle animation
/// take the bank from the page's pointer; `carry_one` leaves a pointer
/// outside bank $7F where it is, which is right, because the cartridge does
/// not change with the map; and the map's `map_code` entry says the bytecode
/// is 0 bytes long behind the grid and names an empty stream, so `lz2_grid`
/// decompresses nothing and `carry_one` never takes a pointer into
/// `CODE_CARRY` for one of this map's because it fell in its range.
///
/// Why not every map: see the task `map-streams-that-dont-fit-in-wram.md`,
/// where it was measured —in short, the ROM it costs uncompressed against a
/// few frames of decompression when loading—.
pub fn code_in_rom(map: &Map) -> bool {
    let behind = grid_high_used(map.grid().len()) + map.blocks.len() + map.block_pass.len();
    map.evcode.len() > LZ2_CAP_CODE || behind + map.evcode.len() > HALF_GRID
}

/// Where the pointers into what lives behind the grid land: WRAM addresses,
/// which the converter knows because it is the one that lays it out —the
/// grid's second half, then the block table, then its passability, then
/// the bytecode—, and the runtime does not compute: `lz2_grid` only
/// decompresses each stream where the one before ended. If both sides
/// disagreed, `test_decompressed_load.py` sees it. `evcode` is where the
/// bytecode starts, which the page table adds each page's offset to.
pub fn map_ram_pointers(map: &Map) -> [(&'static str, String); 3] {
    let start = grid_high_used(map.grid().len());
    let pass = start + map.blocks.len();
    let code = pass + map.block_pass.len();
    [
        ("map_blocks", format!("GRID_HIGH + ${start:04X}")),
        ("block_pass", format!("GRID_HIGH + ${pass:04X}")),
        ("evcode", format!("GRID_HIGH + ${code:04X}")),
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
    out.push(format!("M_GRID_NARROW  = {}", grid_narrow_offset()));
    out.push(format!("M_WRAP         = {}", wrap_offset()));
    out.join("\n")
}

/// Where the record says whether the grid goes one byte a cell —see
/// [`Map::narrow`]—: the fourth byte of the grid's pointer, which a pointer
/// does not use. The record has no other room.
pub fn grid_narrow_offset() -> usize {
    let cells = MAP_POINTERS
        .iter()
        .position(|&p| p == "map_cells")
        .expect("the grid has a pointer");
    MAP_PTR_BASE + cells * MAP_PTR_STEP + 3
}

/// Where the record says which axes the map loops on —bit 0 across, bit 1
/// down; see `wrap.s`—: the fourth byte of the last pointer, the ChipSet
/// animation's, which nobody reads. Like [`grid_narrow_offset`], because
/// the record has no other room; and zero in a map that does not loop, so
/// a cartridge without one comes out as before.
pub fn wrap_offset() -> usize {
    MAP_PTR_BASE + (MAP_POINTERS.len() - 1) * MAP_PTR_STEP + 3
}

/// The bits of [`wrap_offset`].
fn wrap_bits(map: &Map) -> u8 {
    u8::from(map.wrap[0]) | u8::from(map.wrap[1]) << 1
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
            let fourth = if name == "map_cells" && map.narrow() {
                "$01".to_string()
            } else if name == MAP_POINTERS[MAP_POINTERS.len() - 1] {
                format!("${:02X}", wrap_bits(map))
            } else {
                "$00".to_string()
            };
            out.push(format!(
                "    .byte <({label}), >({label}), ^({label}), {fourth} ; +{used}  {name}"
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

/// How many shared slots the runtime keeps track of: its `SHARE_MAX`, which
/// the `.inc` asserts against.
pub const SHARED_MAX: usize = 15;

/// The slots still events take turns in, for the maps that have them: see
/// `sprites::share` in Wally and `share_want` in the runtime.
///
/// `share_maps` has a word per map, in the order of `map_table`: where its
/// record starts inside `share_data`, or 0 if it shares nothing —offset 0 is
/// a byte nobody points at—. A record is
///
/// ```text
///   +0  word  where its event table starts, inside share_data
///   +2  word  where its pose table starts
///   +4  byte  how many slots
///   +5  word per slot: where it starts in VRAM, in words from the sprites'
///   then, per event of the map: the slot or $FF, and its pose
///   then, per pose: where it is in `npc_poses`, (entry * 12 + pose) * 3
/// ```
///
/// Both in one `.block`: `share_want` reads them with `lda f:share_data, x`,
/// and the offsets are sixteen bits.
pub fn share_table(maps: &[Map]) -> Result<String> {
    let mut data: Vec<String> = vec!["    .byte $00 ; offset 0: no map shares".into()];
    let mut size = 1usize;
    let mut starts = Vec::with_capacity(maps.len());
    for map in maps {
        let Some(shared) = map.sprite.as_ref().and_then(|s| s.shared.as_ref()) else {
            starts.push(0);
            continue;
        };
        let n = shared.slots.len();
        if n == 0 || n > SHARED_MAX {
            return Err(Bad::answer(format!(
                "map {}: {n} shared slots, and the console keeps between 1 and {SHARED_MAX}",
                map.id
            )));
        }
        let start = size;
        let events_at = start + 5 + 2 * n;
        let poses_at = events_at + 2 * map.events.len();
        starts.push(start);
        data.push(format!("    ; map {} {}", map.id, quoted(&map.name)));
        data.push(format!("    .word {events_at}, {poses_at}"));
        data.push(format!("    .byte {n}"));
        data.push(format!(
            "    .word {}",
            shared
                .slots
                .iter()
                .map(|&b| (block_tile(b) * 16).to_string())
                .collect::<Vec<_>>()
                .join(", ")
        ));
        let mut by_event = vec![(0xFFu8, 0u8); map.events.len()];
        for &(event, slot, pose, _) in &shared.events {
            let e = usize::try_from(event)
                .ok()
                .filter(|&e| e < by_event.len())
                .ok_or_else(|| {
                    Bad::answer(format!(
                        "map {}: event {event} takes turns and is not in the map",
                        map.id
                    ))
                })?;
            by_event[e] = (slot as u8, pose as u8);
        }
        for chunk in by_event.chunks(8) {
            data.push(format!(
                "    .byte {}",
                chunk
                    .iter()
                    .map(|(s, p)| format!("${s:02X},{p}"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        data.push(format!(
            "    .word {}",
            shared
                .poses
                .iter()
                .map(|&(k, pose)| ((k * SPRITE_POSES + pose) * 3).to_string())
                .collect::<Vec<_>>()
                .join(", ")
        ));
        data.push(format!(
            ".assert {n} <= SHARE_MAX, error, \"map {}: more shared slots than SHARE_MAX\"",
            map.id
        ));
        size = poses_at + 2 * shared.poses.len();
    }
    let mut out = vec![
        ".segment \"RODATA\"".to_string(),
        "; The slots still events take turns in: see `share_table` in rm2k-snes-mapdata.".into(),
        format!(".block {}", 2 * maps.len().max(1)),
        "share_maps:".into(),
        format!(
            "    .word {}",
            if starts.is_empty() {
                "0".to_string()
            } else {
                starts
                    .iter()
                    .map(|s| s.to_string())
                    .collect::<Vec<_>>()
                    .join(", ")
            }
        ),
        format!(".block {size}"),
        "share_data:".into(),
    ];
    out.extend(data);
    Ok(out.join("\n"))
}

/// How many slots a cache can have: the runtime's `CACHE_MAX` and Wally's,
/// which the `.inc` asserts against. And how many still poses it can name:
/// below 128, which is how a slot that holds one tells it from one that
/// holds an event's own.
pub const CACHE_MAX: usize = wally::sprites::cache::CACHE_MAX;
pub const CACHE_STILLS_MAX: usize = wally::sprites::cache::STILLS_MAX;

/// The caches of slots, for the maps that have one: see `sprites::cache`
/// in Wally and cache_slots.s in the runtime.
///
/// `cache_maps` has a word per map, in the order of `map_table`: where its
/// record starts inside `cache_data`, or 0 if it has none —offset 0 is a
/// byte nobody points at—. A record is
///
/// ```text
///   +0  byte  how many slots
///   +1  word  where its still poses start, inside cache_data
///   +3  word per slot: its first tile in the sprite bank
///   then, per still pose: where it is in `npc_poses`, (entry * 12 + pose) * 3
/// ```
///
/// Which still pose each event starts with is not here: its row carries it
/// in the tile byte, and so do the pages of the ones that change graphic.
pub fn cache_table(maps: &[Map]) -> Result<String> {
    let mut data: Vec<String> = vec!["    .byte $00 ; offset 0: no map has a cache".into()];
    let mut size = 1usize;
    let mut starts = Vec::with_capacity(maps.len());
    for map in maps {
        let Some(cache) = map.sprite.as_ref().and_then(|s| s.cache.as_ref()) else {
            starts.push(0);
            continue;
        };
        let n = cache.slots.len();
        if n == 0 || n > CACHE_MAX {
            return Err(Bad::answer(format!(
                "map {}: a cache of {n} slots, and the console keeps between 1 and {CACHE_MAX}",
                map.id
            )));
        }
        if cache.stills.len() > CACHE_STILLS_MAX {
            return Err(Bad::answer(format!(
                "map {}: {} still poses in its cache, and the console names {CACHE_STILLS_MAX}",
                map.id,
                cache.stills.len()
            )));
        }
        let start = size;
        let stills_at = start + 3 + 2 * n;
        starts.push(start);
        data.push(format!("    ; map {} {}", map.id, quoted(&map.name)));
        data.push(format!("    .byte {n}"));
        data.push(format!("    .word {stills_at}"));
        data.push(format!(
            "    .word {}",
            cache
                .slots
                .iter()
                .map(|&b| block_tile(b).to_string())
                .collect::<Vec<_>>()
                .join(", ")
        ));
        if !cache.stills.is_empty() {
            data.push(format!(
                "    .word {}",
                cache
                    .stills
                    .iter()
                    .map(|&(_, _, pose, k, _)| ((k * SPRITE_POSES + pose as usize) * 3).to_string())
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        data.push(format!(
            ".assert {n} <= CACHE_MAX, error, \"map {}: a bigger cache than CACHE_MAX\"",
            map.id
        ));
        size = stills_at + 2 * cache.stills.len();
    }
    let mut out = vec![
        ".segment \"RODATA\"".to_string(),
        "; The caches of slots: see `cache_table` in rm2k-snes-mapdata.".into(),
        format!(".block {}", 2 * maps.len().max(1)),
        "cache_maps:".into(),
        format!(
            "    .word {}",
            if starts.is_empty() {
                "0".to_string()
            } else {
                starts
                    .iter()
                    .map(|s| s.to_string())
                    .collect::<Vec<_>>()
                    .join(", ")
            }
        ),
        format!(".block {size}"),
        "cache_data:".into(),
    ];
    out.extend(data);
    Ok(out.join("\n"))
}

/// The 32x32 blocks the sprite bank has, the 512 tiles an object names.
pub const POSE_BLOCKS: usize = 32;

/// Which tiles of each 32x32 block of the sprite bank hold something once
/// the bank is uploaded, per map: a word per block, bit *i* tile *i* of the
/// 4x4 by rows, as a pose's mask (see [`pose_record`]). `vram_drain` zeroes
/// the tiles a slot held and its new pose does not draw, and it has to know
/// what the bank left there: `load_sprite` copies the map's 64 bytes to
/// `pose_slot_masks`. Without them every slot started as "anything" and its
/// first pose zeroed all its empty tiles, which in the first steps after
/// entering a map made the vblank longer than uploading the poses whole.
///
/// A tile the bank does not reach is "anything": VRAM there holds whatever
/// was before.
///
/// `pose_masks_maps` has a word per map, in the order of `map_table`: where
/// its 64 bytes start inside `pose_masks_data`. Maps with the same masks
/// share them. It goes here and not in the record because the record is
/// full.
pub fn pose_masks_table(maps: &[Map]) -> String {
    let mut distinct: Vec<Vec<u16>> = Vec::new();
    let mut starts = Vec::with_capacity(maps.len());
    for map in maps {
        let masks = block_masks(map.sprite.as_ref().map_or(&[][..], |s| s.tiles.as_slice()));
        let at = match distinct.iter().position(|d| *d == masks) {
            Some(k) => k,
            None => {
                distinct.push(masks);
                distinct.len() - 1
            }
        };
        starts.push(at * 2 * POSE_BLOCKS);
    }
    let mut out = vec![
        ".segment \"RODATA\"".to_string(),
        "; What each block of the sprite bank holds when a map loads: see `pose_masks_table` in rm2k-snes-mapdata.".into(),
        format!(".block {}", 2 * maps.len().max(1)),
        "pose_masks_maps:".into(),
        format!(
            "    .word {}",
            if starts.is_empty() {
                "0".to_string()
            } else {
                starts.iter().map(|s| s.to_string()).collect::<Vec<_>>().join(", ")
            }
        ),
        format!(".block {}", 2 * POSE_BLOCKS * distinct.len().max(1)),
        "pose_masks_data:".into(),
    ];
    if distinct.is_empty() {
        out.push(format!(
            "    .word {}",
            vec!["$FFFF"; POSE_BLOCKS].join(", ")
        ));
    }
    for masks in &distinct {
        for half in masks.chunks(POSE_BLOCKS / 2) {
            out.push(format!(
                "    .word {}",
                half.iter()
                    .map(|m| format!("${m:04X}"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
    }
    out.join("\n")
}

/// The sprite palettes an object names: OAM has three bits for them.
pub const OBJ_PALETTES: usize = 8;

/// The tiles the message window's arrow takes as objects: two 8x8, side by
/// side —`WINDOW_ARROW_CELLS`, which the runtime checks against this—.
pub const ARROW_OBJ_TILES: usize = 2;

/// The tiles the gold window takes as objects, after the arrow's: 88x32 in
/// 8x8 tiles. See the runtime's gold_window.s.
pub const GOLD_OBJ_TILES: usize = 11 * 4;

/// The bit of [`arrow_obj`]'s word that says the gold window fits too.
pub const GOLD_ROOM: u16 = 0x4000;

/// Where a window without its background draws its arrow as two objects,
/// per map: the first of its two tiles and a sprite palette nobody else
/// takes, as a word —the tile in bits 0 to 8, the palette in 9 to 11, bit
/// 14 if the gold window's [`GOLD_OBJ_TILES`] fit after the arrow's two, and
/// bit 15 set—; 0 if the map has no room for one of the two, and there the
/// arrow stays in the window's cells and keeps BG2 on its eight lines, and
/// an inn shows no gold window.
///
/// **The tiles are the two past the bank**, if the layout's sprite tiles
/// reach them: everything the console writes into the bank —the slots, the
/// cache's, the animation's box, a picture's 8x8 objects— is inside its
/// length, so what is past it nobody touches. **The palette is the top one
/// the pictures leave**, if it is above the characters' and the animation
/// box's: the pictures take theirs from 7 down and the rest from 0 up. The
/// console copies the window's colours into it, and the arrow's tiles from
/// the window's own, when the window appears: see `arrow_obj_load` in the
/// runtime's message_arrow.s. Nobody tints it —the tint runs over the
/// map's palettes only—, and RM2k does not tint the window either.
pub fn arrow_obj(map: &Map) -> Result<u16> {
    Ok(arrow_room(map)?.unwrap_or(0))
}

/// [`arrow_obj`]'s word, or why there is no room: what the converter's log
/// says of each map that keeps the arrow in the cells.
fn arrow_room(map: &Map) -> Result<std::result::Result<u16, String>> {
    let layout = layout_of(map)?;
    let (tiles, characters, animation, top) = match &map.sprite {
        None => (0, 0, None, 0),
        Some(s) => (
            s.tiles.len() / TILE_BYTES,
            s.palettes.len(),
            s.animation.as_ref().map(|a| a.palette as usize),
            s.image.1.max(0) as usize,
        ),
    };
    let cap = layout.sprites.count as usize;
    if tiles + ARROW_OBJ_TILES > cap {
        return Ok(Err(format!(
            "its sprite bank takes {tiles} of the {cap} sprite tiles of its layout"
        )));
    }
    let low = characters.max(animation.map_or(0, |a| a + 1));
    if low + top >= OBJ_PALETTES {
        return Ok(Err(format!(
            "its {OBJ_PALETTES} sprite palettes are taken: up to {} by the characters{}, and the top {top} by the pictures",
            low - 1,
            if animation.is_some() { " and the battle animation's box" } else { "" }
        )));
    }
    let palette = OBJ_PALETTES - 1 - top;
    // And the gold window's tiles after the arrow's, in the same palette, if
    // the bank's room reaches them.
    let gold = if tiles + ARROW_OBJ_TILES + GOLD_OBJ_TILES <= cap {
        GOLD_ROOM
    } else {
        0
    };
    Ok(Ok(0x8000 | gold | (palette as u16) << 9 | tiles as u16))
}

/// Where a map takes the common events' small pictures —see
/// `picture_common_section` in emit.rs—: the first tile past its bank and
/// what the arrow and the gold window take after it, rounded to a row of
/// blocks, as the pictures' own are; and the first sprite palette from the
/// top past its pictures' and the arrow's. With how many tiles and palettes
/// are left there.
pub struct CommonRoom {
    pub base: usize,
    pub tiles: usize,
    pub palette: usize,
    pub palettes: usize,
}

pub fn common_room(map: &Map) -> Result<CommonRoom> {
    let layout = layout_of(map)?;
    let (tiles, characters, animation, top) = match &map.sprite {
        None => (0, 0, None, 0),
        Some(s) => (
            s.tiles.len() / TILE_BYTES,
            s.palettes.len(),
            s.animation.as_ref().map(|a| a.palette as usize),
            s.image.1.max(0) as usize,
        ),
    };
    let arrow = arrow_obj(map)?;
    let mut end = tiles;
    let mut palette = top;
    if arrow & 0x8000 != 0 {
        end += ARROW_OBJ_TILES;
        palette += 1;
        if arrow & GOLD_ROOM != 0 {
            end += GOLD_OBJ_TILES;
        }
    }
    let base = end.div_ceil(BLOCK_ROW_TILES) * BLOCK_ROW_TILES;
    let cap = layout.sprites.count as usize;
    let low = characters.max(animation.map_or(0, |a| a + 1));
    Ok(CommonRoom {
        base,
        tiles: cap.saturating_sub(base),
        palette,
        palettes: OBJ_PALETTES.saturating_sub(low + palette),
    })
}

/// A row of 32x32 blocks in the sprites' name grid: four across its
/// sixteen tiles, four tall. A picture's blocks start at one.
pub const BLOCK_ROW_TILES: usize = 64;

/// What the converter's log says of each map that keeps the arrow in the
/// window's cells.
fn arrow_notes(maps: &[Map]) -> Result<Vec<String>> {
    let mut notes = Vec::new();
    for map in maps {
        if let Err(why) = arrow_room(map)? {
            notes.push(format!(
                "  map {}: the message arrow stays in the window's cells, and a window without its \
                 background keeps the layer above off its bottom row: {why}",
                map.id
            ));
        }
    }
    Ok(notes)
}

/// `arrow_obj` for every map, a word each in the order of `map_table`:
/// `arrow_objs`. It goes here and not in the record because the record is
/// full.
pub fn arrow_objs_table(maps: &[Map]) -> Result<String> {
    let words = maps.iter().map(arrow_obj).collect::<Result<Vec<u16>>>()?;
    Ok([
        ".segment \"RODATA\"".to_string(),
        "; Where a window without its background draws its arrow as objects, per map: see `arrow_obj` in rm2k-snes-mapdata.".into(),
        format!("ARROW_OBJ_TILES = {ARROW_OBJ_TILES}"),
        format!(".block {}", 2 * maps.len().max(1)),
        "arrow_objs:".into(),
        format!(
            "    .word {}",
            if words.is_empty() {
                "0".to_string()
            } else {
                words.iter().map(|w| format!("${w:04X}")).collect::<Vec<_>>().join(", ")
            }
        ),
    ]
    .join("\n"))
}

/// Each block's mask, from the sprite bank's tiles as they are uploaded:
/// a tile beyond the bank holds whatever VRAM had.
fn block_masks(tiles: &[u8]) -> Vec<u16> {
    (0..POSE_BLOCKS as u32)
        .map(|b| {
            (0..POSE_TILES).fold(0u16, |mask, i| {
                let t = block_tile(b) as usize + (i / 4) * 16 + i % 4;
                let held = tiles
                    .get(t * TILE_BYTES..(t + 1) * TILE_BYTES)
                    .is_none_or(|tile| tile.iter().any(|&b| b != 0));
                if held {
                    mask | 1 << i
                } else {
                    mask
                }
            })
        })
        .collect()
}

/// One entry per map, `MAP_CODE_STRIDE` bytes: where its bytecode's LZ2
/// stream is, where in bank $7F the bytecode lands behind the grid, and
/// how long it is. It is what the console needs to carry a page that goes
/// on running after a teleport: see `code_carry_before` in the runtime's
/// `decompress.s`.
pub fn map_code_table(maps: &[Map], labels: &[Labels]) -> String {
    let mut out = vec![
        ".segment \"RODATA\"".to_string(),
        "MAP_CODE_STRIDE = 8".to_string(),
        format!("LZ2_CAP_CODE = ${:04X}", LZ2_CAP_CODE),
        format!(".block {}", 8 * maps.len().max(1)),
        "map_code:".to_string(),
    ];
    for (map, labels) in maps.iter().zip(labels) {
        // One in the cartridge is 0 bytes behind the grid: see
        // [`code_in_rom`].
        let length = if code_in_rom(map) {
            0
        } else {
            map.evcode.len()
        };
        out.push(format!(
            "    .byte {}, $00\n    .word .loword({}), {}",
            pointer(&labels["code_stream"]),
            labels["evcode"],
            length
        ));
    }
    if maps.is_empty() {
        out.push("    .byte 0, 0, 0, 0, 0, 0, 0, 0".into());
    }
    out.join("\n")
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
        // `rom/src/` and not `runtime/`, on purpose: it goes into the
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
        // A background at 4bpp —a map whose panorama goes in mode 1— has
        // tiles of half the bytes.
        let bytes_per_tile = (BYTES_PER_TILE * map.bpp / 8) as i64;
        for (k, (name, family, count)) in FAMILIES.iter().enumerate() {
            let run = map.runs.iter().find(|r| r.family == *family);
            let tiles = run.map_or(0, |r| r.tiles);
            let vram =
                i64::from(layout.tiles.base) + run.map_or(0, |r| r.base) * bytes_per_tile / 2;
            out.push(format!("    .word {vram:<6} ; VRAM of {name}"));
            out.push(format!(
                "    .word {offset:<6} ; drawing 0, inside the block"
            ));
            out.push(format!(
                "    .word {:<6} ; bytes per drawing",
                tiles * bytes_per_tile
            ));
            // The last family's padding: how many rows animate standing
            // still and upload their pose, so `animate_still` stops walking
            // the table after the last one.
            let padding = if k == FAMILIES.len() - 1 {
                rows[number]
                    .iter()
                    .filter(|n| n.animates)
                    .count()
                    .min(u8::MAX as usize)
            } else {
                0
            };
            out.push(format!(
                "    .byte {tiles}, {padding}   ; {tiles} tile(s){}",
                if padding != 0 {
                    ", and the map has still events that animate"
                } else {
                    ""
                }
            ));
            offset += tiles * bytes_per_tile * *count as i64;
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
    page_table_with(map, number, &|offset| format!("{evcode} + {offset}"))
}

/// [`page_table`], with where each offset of the code block lands said by
/// `dest`: a map whose bytecode stays in the cartridge has it in several
/// blocks, one per bank —see [`rom_code_chunks`]—.
pub fn page_table_with(map: &PageMap, number: usize, dest: &dyn Fn(usize) -> String) -> String {
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
            let dest = dest(page.offset);
            format!("<({dest}), >({dest}), ^({dest})")
        } else {
            "$00, $00, $00".to_string()
        };
        out.push(format!(
            "    .word {:<4} ; +0  the event it belongs to",
            page.event
        ));
        // Only its low byte, on purpose: the console never reads +2 —it is
        // here for whoever reads the `.inc`— and the test event carries one
        // page per case, which went past 255 on 2026-10-01 and stopped
        // assembling with a `Range error`. Widening it would cost a byte of
        // every page for a number nobody reads. What does bound the pages is
        // `MAX_PAGES`.
        out.push(format!(
            "    .byte {:<4} ; +2  its page number",
            page.page & 0xFF
        ));
        // Bit 7: a parallel page that runs only when what it reads changes
        // —`pure_page` in the events compiler—; the console masks it off
        // where it reads the trigger, and the parallels' list keeps it.
        out.push(format!(
            "    .byte {:<4} ; +3  what triggers it",
            page.trigger | if page.pure { 0x80 } else { 0 }
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
            let dest = dest(page.route_offset);
            out.push(format!(
                "    .byte {flags:<4} ; +13 the flags of its own route"
            ));
            out.push(format!(
                "    .byte {:<4} ; +14 its frequency",
                own.frequency
            ));
            // The speed is 1 to 6, so the spin rides in its high bits: the
            // byte at +13 is full. Bit 7 it turns in place, bits 4 and 5
            // the column it shows. See `load_page_into_slot`. And bit 3,
            // it walks by a movement type: see `walk_may_take`.
            let speed = own.speed
                | bit(own.by_type, 8)
                | bit(own.spin, 128)
                | if own.spin { own.pattern << 4 } else { 0 }
                | fixed_graphic(page);
            // The comment is the old one on purpose: `tests/python.rs`
            // hashes the `.inc`, comments and all.
            out.push(format!("    .byte {speed:<4} ; +15 and its speed"));
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
                page.speed | fixed_graphic(page)
            ));
            out.push("    .byte 0,0,0,0".into());
        }
        // +20: what the page draws, for the events that change graphic.
        match page.draws.as_ref().map(|d| page_oam(d, page.layer)) {
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
        // +30: which entry of `npc_poses` the poses of its graphic are in,
        // or $FF; +31 its pose, bit 7 if it does **not** turn toward the
        // hero, and in bits 4 to 6 its graphic's palette. Two readers: the
        // turn toward the hero, and an event that walks, whose row carries
        // one graphic's twelve poses and takes the page's from here —see
        // `page_graphic`—. Until 2026-10-05 only the turn had it, and an
        // event that walked kept its first page's graphic for good: Boss
        // Wick, on ABL's map 40, came back from the vidcasts as one of his
        // girls.
        let turns = page.turns && map.turning.contains(&page.event);
        let k = match &page.graphic {
            Some((charset, index, _)) if turns || map.movable.contains(&page.event) => map
                .animated
                .iter()
                .position(|(c, i)| c == charset && i == index),
            _ => None,
        };
        let pose = match (&k, &page.graphic) {
            (Some(k), Some((_, _, pose))) => {
                let palette = map.animated_palettes.get(*k).copied().unwrap_or(0) & 0x07;
                *pose | palette << 4
            }
            _ => 0,
        };
        let pose = pose | bit(!(turns && k.is_some()), 0x80);
        out.push(format!(
            "    .byte ${:02X}, ${pose:02X} ; +30 its poses and +31 its pose, palette and whether it turns",
            k.map_or(0xFF, |k| k as i64)
        ));
    }
    if map.pages.is_empty() {
        // A label cannot be left empty.
        out.push("    .byte $00".into());
    }
    out.join("\n")
}

/// What `AnimType_fixed_graphic` adds to a page's speed byte, +15: bit 6,
/// and its column in bits 4 and 5 —the ones the spin uses, which never
/// comes with it—. A move route that takes the event does not change its
/// column, which is how ABL's missile silos (map 92) open: they turn and
/// show the first column of each row of their sheet, and the middle one is
/// a soldier. See `route_for_event` and `animate_ev_route`.
fn fixed_graphic(page: &Page) -> i64 {
    match &page.graphic {
        Some((_, _, pose)) if page.fixed_graphic => 0x40 | (pose % 3) << 4,
        _ => 0,
    }
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
    /// The events that walk: their rows carry a pose bank.
    pub movable: &'a [i64],
    /// The characters that change pose, in the order of the pose table,
    /// and each one's palette.
    pub animated: &'a [(String, i64)],
    pub animated_palettes: &'a [i64],
}

impl<'a> PageMap<'a> {
    pub fn of(map: &'a Map) -> Self {
        PageMap {
            pages: &map.pages,
            changing: &map.changing,
            appearing: &map.appearing,
            turning: &map.turning,
            movable: &map.movable,
            animated: map.sprite.as_ref().map_or(&[], |s| s.animated.as_slice()),
            animated_palettes: map
                .sprite
                .as_ref()
                .map_or(&[], |s| s.animated_palettes.as_slice()),
        }
    }
}

/// The pointers to the twelve poses of each character that changes pose,
/// one entry per character —the same index the drawn event's row carries
/// in +9 and the leader in its table—: its size and its lines.
///
/// **Stored once for the whole cartridge** when two maps bring the same
/// one (see [`Materials::store_symbolic`]): 307 maps of ABL carried 191
/// different ones. The record points to it with 24 bits, so the console
/// does not notice which map's it is.
fn npc_poses_asm(animated: &[(String, i64)], poses: &PoseLabels) -> (usize, Vec<String>) {
    let mut out = Vec::new();
    for pair in animated {
        for label in &poses[pair] {
            out.push(format!("    .byte {}", pointer(label)));
        }
    }
    if animated.is_empty() {
        out.push("    .byte $00".into());
    }
    (3 * SPRITE_POSES * animated.len().max(1), out)
}

/// The leader candidates: id, palette, their fifteen colours and the
/// pointer to each of their poses; twelve at `$FFFFFF` for one without a
/// graphic, which is the sentinel `place_hero` looks at. Its size and its
/// lines, without the label: two maps that give the same lines share the
/// table —see `map_data`—.
fn actor_table_asm(map: &Map, poses: &PoseLabels) -> (usize, String) {
    let sprite = map.sprite.as_ref();
    let actors = sprite.map_or(&[][..], |s| s.actors.as_slice());
    let animated = sprite.map_or(&[][..], |s| s.animated.as_slice());
    let mut out = Vec::new();
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
    (ACTOR_BYTES * actors.len().max(1), out.join("\n"))
}

/// A map's data blocks, and which label each record pointer gets.
pub fn map_data(
    map: &Map,
    number: usize,
    rows: &[NpcRow],
    poses: &PoseLabels,
    hero_colors: &HeroColors,
    materials: &mut Materials,
) -> Result<(String, Labels)> {
    let sprite = map.sprite.as_ref();
    // Two bytes per graphic, and behind them one per graphic: its entry in
    // `hero_colors`, from 1, or 0. See `hero_poses_of_graphic`.
    let route_graphic: Vec<u8> = sprite
        .map(|s| {
            let mut out: Vec<u8> = s
                .route_gfx
                .iter()
                .flat_map(|g| [g.entry() as u8, g.palette() as u8])
                .collect();
            out.extend(s.route_gfx.iter().map(|g| hero_colors.entry(g.colors())));
            out
        })
        .unwrap_or_default();
    let pairs: [(&'static str, Vec<u8>); 11] = [
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
    let (size, lines) = npc_poses_asm(animated, poses);
    let (label, text) = materials.store_symbolic("npc_poses", number, size, &lines);
    if !text.is_empty() {
        out.push(text);
    }
    labels.insert("npc_poses", label);
    // The leader candidates are the party's, so most maps of a cartridge
    // carry the same table: shared by its text, pointers included, under the
    // label of the first map that has it. Until 2026-10-14 each map had its
    // own, and ABL's whole game carried 307 of them and 22 different.
    let (size, body) = actor_table_asm(map, poses);
    let (label, text) =
        materials.store_text("actor_table", &format!("actor_table_{number}"), size, &body);
    if !text.is_empty() {
        out.push(text);
    }
    labels.insert("actor_table", label);
    // The grid, in its two streams, and the block table and its passability
    // in a third: see `lz2_grid`.
    let ram = map_ram(&map.blocks, &map.block_pass);
    let grid = map.grid();
    let (label, text) =
        materials.store_compressed_joined(&[("map_cells", &grid), ("map_ram", &ram)]);
    if !text.is_empty() {
        out.push(text);
    }
    labels.insert("map_cells", label);
    // And the bytecode, which lands behind them, in a block of its own:
    // `map_code_table` names it. Joined to the others, two maps with the
    // same grid and different events would not share the grid.
    let in_rom = code_in_rom(map);
    let stream: &[u8] = if in_rom { &[] } else { &map.evcode };
    let (label, text) = materials.store_compressed("map_code", stream);
    if !text.is_empty() {
        out.push(text);
    }
    labels.insert("code_stream", label);
    for (name, address) in map_ram_pointers(map) {
        labels.insert(name, address);
    }
    // Or it stays in the cartridge, in blocks of up to a bank, and the
    // pages point there: see [`code_in_rom`]. Two maps with the same block
    // share it.
    let mut chunks: Vec<(usize, String)> = Vec::new();
    if in_rom {
        for (start, bytes) in rom_code_chunks(map)? {
            let (label, text) = materials.store("rom_code", bytes);
            if !text.is_empty() {
                out.push(text);
            }
            chunks.push((start, label));
        }
        labels.insert("evcode", chunks[0].1.clone());
    }
    if in_rom {
        let dest = |offset: usize| {
            let (start, label) = chunks
                .iter()
                .rev()
                .find(|(start, _)| *start <= offset)
                .unwrap();
            format!("{label} + {}", offset - start)
        };
        out.push(page_table_with(&PageMap::of(map), number, &dest));
    } else {
        out.push(page_table(&PageMap::of(map), number, &labels["evcode"]));
    }
    // The page table is not shared: it carries symbolic pointers inside,
    // whose bytes the linker sets, so there is no content to compare it by.
    // The npc_poses and the actor table are shared, and already have their
    // labels.
    labels.insert("pages", format!("pages_{number}"));
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
    if map.pages.len() > MAX_PAGES {
        return Err(Bad::answer(format!(
            "map {} has {} event pages and {MAX_PAGES} fit: see MAX_PAGES",
            map.id,
            map.pages.len()
        )));
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
    let mut drawn = 0;
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
                    let record = pose_record(&bytes);
                    drawn += (record.len() - 2) / TILE_BYTES;
                    let _ = writeln!(text, "{}", block(&l, &record));
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
    // And what leaving out their empty tiles saves, the masks paid.
    let tiles = label_of.len() * POSE_TILES;
    notes.push(format!(
        "  poses: {} of their {tiles} tiles empty, {:.1} KB less",
        tiles - drawn,
        ((tiles - drawn) * TILE_BYTES) as f64 / 1024.0 - (2 * label_of.len()) as f64 / 1024.0
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

/// The colours of the graphics only the hero shows, which go in the
/// leaders' palette with colours of their own —see `drawable_npcs` in
/// Wally—: each set once for the whole cartridge, thirty bytes each, and
/// the console uploads the one the graphic names when the hero takes it.
pub struct HeroColors {
    sets: Vec<Vec<u32>>,
}

impl HeroColors {
    /// The entries a graphic can name: one byte, and 0 is none.
    pub const MAX: usize = 255;

    pub fn of(maps: &[Map]) -> Result<HeroColors> {
        let mut sets: Vec<Vec<u32>> = Vec::new();
        for map in maps {
            for g in map
                .sprite
                .as_ref()
                .map_or(&[][..], |s| s.route_gfx.as_slice())
            {
                let colors = g.colors();
                if colors.is_empty() || sets.iter().any(|s| s == colors) {
                    continue;
                }
                if colors.len() > OBJ_COLORS {
                    return Err(Bad::answer(format!(
                        "map {}: a graphic of command 34 brings {} colours and a palette holds {OBJ_COLORS}",
                        map.id,
                        colors.len()
                    )));
                }
                sets.push(colors.to_vec());
            }
        }
        if sets.len() > Self::MAX {
            return Err(Bad::answer(format!(
                "the graphics only the hero shows bring {} sets of colours and `hero_colors` names {}",
                sets.len(),
                Self::MAX
            )));
        }
        Ok(HeroColors { sets })
    }

    /// Which entry holds `colors`, from 1; 0 for none.
    pub fn entry(&self, colors: &[u32]) -> u8 {
        if colors.is_empty() {
            return 0;
        }
        self.sets
            .iter()
            .position(|s| s == colors)
            .map_or(0, |k| k as u8 + 1)
    }

    /// The table, with one byte when it is empty: the runtime names it
    /// always.
    pub fn asm(&self) -> String {
        let mut bytes = Vec::new();
        for set in &self.sets {
            let mut words = set.clone();
            words.resize(OBJ_COLORS, 0);
            bytes.extend(
                words
                    .iter()
                    .flat_map(|w| [(w & 0xFF) as u8, (w >> 8) as u8]),
            );
        }
        if bytes.is_empty() {
            bytes.push(0);
        }
        format!("{}\n\n", block("hero_colors", &bytes))
    }
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
    maps_with(maps, false)
}

/// [`maps`], and with `msu` each LZ2 stream marked as one that may go to
/// the `.msu`: see [`Materials::msu`].
pub fn maps_with(maps: &[Map], msu: bool) -> Result<Written> {
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
    let hero_colors = HeroColors::of(maps)?;
    let mut text = poses.text;
    text.push_str(&hero_colors.asm());
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
    materials.msu = msu;
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
            &hero_colors,
            &mut materials,
        )?;
        text.push_str(&data);
        text.push('\n');
        labels.push(theirs);
    }
    let mut tables = format!(
        "{}\n\n{}\n\n{}\n\n{}\n\n{}\n",
        map_table(maps, &labels, &rows)?,
        anim_table(maps, &rows)?,
        map_code_table(maps, &labels),
        share_table(maps)?,
        cache_table(maps)?
    );
    let _ = write!(tables, "\n{}\n", pose_masks_table(maps));
    let _ = write!(tables, "\n{}\n", arrow_objs_table(maps)?);
    // Only in a cartridge that shows some panorama: one that does not gets
    // the same `.inc` as before there were any. See `pano.s`.
    if maps.iter().any(|m| m.panorama.is_some()) {
        let _ = write!(
            tables,
            "\n{}\n",
            crate::panorama::panorama_table(maps, msu)?
        );
    }
    // And the code of the maps that loop, only in a cartridge that has one:
    // see `wrap.s`, which assembles nothing without `wrap_maps`.
    if maps.iter().any(|m| m.wrap[0] || m.wrap[1]) {
        tables.push_str("\n; Some map loops: see `wrap.s`.\nwrap_maps = 1\n");
    }
    // And the painted ones, only in a cartridge that has some: see
    // `painted.s`, which assembles nothing without `paint_table`.
    if maps
        .iter()
        .any(|m| m.panorama.as_ref().is_some_and(|p| p.mode == 4))
    {
        let _ = write!(tables, "\n{}\n", crate::panorama::paint_table(maps)?);
    }
    Ok(Written {
        offsets: offsets(),
        maps: text,
        tables,
        notes: poses.notes.into_iter().chain(arrow_notes(maps)?).collect(),
        report: materials.report(),
        frames,
        raw,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_block_s_mask_is_what_the_bank_leaves_in_its_tiles() {
        // Sixty-four tiles: the first row of blocks, 0 to 3, whole, and
        // nothing of the rest.
        let mut tiles = vec![0u8; 64 * TILE_BYTES];
        tiles[0] = 1; // block 0, tile 0
        tiles[(16 + 1) * TILE_BYTES + 31] = 1; // block 0, tile 5: second row
        tiles[(48 + 15) * TILE_BYTES] = 1; // block 3, tile 15: its corner
        let masks = block_masks(&tiles);
        assert_eq!(masks.len(), POSE_BLOCKS);
        assert_eq!(masks[..4], [0x0021, 0, 0, 0x8000]);
        // Beyond the bank, VRAM holds whatever it had.
        assert!(masks[4..].iter().all(|&m| m == 0xFFFF));
    }

    /// Each literal operand of the `.byte`s and `.word`s, with the largest
    /// value its directive holds: what `ca65` checks, and answers with a
    /// `Range error` when it does not fit.
    fn literals(table: &str) -> Vec<(String, i64, i64)> {
        let mut out = vec![];
        for line in table.lines() {
            let code = line.split(';').next().unwrap().trim();
            let (max, operands) = if let Some(rest) = code.strip_prefix(".byte ") {
                (0xFF, rest)
            } else if let Some(rest) = code.strip_prefix(".word ") {
                (0xFFFF, rest)
            } else {
                continue;
            };
            for operand in operands.split(',').map(str::trim) {
                let value = match operand.strip_prefix('$') {
                    Some(hex) => i64::from_str_radix(hex, 16).ok(),
                    None => operand.parse().ok(),
                };
                if let Some(value) = value {
                    out.push((line.to_string(), value, max));
                }
            }
        }
        out
    }

    /// The test event as the converter writes it: one page per case, the
    /// k-th asking for the case variable to be at least k.
    fn test_pages(count: i64) -> Vec<Page> {
        (0..count)
            .map(|k| Page {
                event: 1,
                page: k,
                trigger: TRIGGER_AUTOSTART,
                has_code: true,
                offset: 4 * k as usize,
                variable: (k > 0).then_some((7, 1, k)),
                ..Page::default()
            })
            .collect()
    }

    #[test]
    fn more_than_256_test_pages_fit_in_the_page_table() {
        // On 2026-10-01 the release cartridge reached 256 and the next one
        // did not assemble, because +2 carried the page number whole.
        let pages = test_pages(300);
        let map = PageMap {
            pages: &pages,
            changing: &[],
            appearing: &[],
            turning: &[],
            movable: &[],
            animated: &[],
            animated_palettes: &[],
        };
        let table = page_table(&map, 0, "evcode_0");
        let operands = literals(&table);
        assert!(operands.len() > 300 * 10, "the table was not read");
        for (line, value, max) in operands {
            assert!(
                (0..=max).contains(&value),
                "{value} does not fit in: {line}"
            );
        }
        // And the page that asks for the case variable at 299 says so whole.
        assert!(table.contains(".word 299 ; +26 against what"), "{table}");
    }

    /// The arrow's objects take the two tiles past the bank and the top
    /// palette the pictures leave, and nothing when one of the two is not
    /// there: the tiles past the layout's sprites, or the palettes all
    /// taken between the characters, the animation's box and the pictures.
    #[test]
    fn the_arrow_s_objects_go_past_the_bank_and_under_the_pictures() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut map = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps
            .remove(0);
        let cap = layout_of(&map).unwrap().sprites.count as usize;
        let sprite = map.sprite.as_mut().unwrap();
        sprite.tiles = vec![0; 300 * TILE_BYTES];
        sprite.palettes = vec![vec![[1, 2, 3]]; 3];
        sprite.image = (0, 0);
        sprite.animation = None;
        assert_eq!(
            arrow_obj(&map).unwrap(),
            0x8000 | GOLD_ROOM | 7 << 9 | 300,
            "tile 300, palette 7, and the gold window after"
        );
        // Under two palettes of pictures, and over an animation's box.
        let sprite = map.sprite.as_mut().unwrap();
        sprite.image = (256, 2);
        sprite.animation = Some(crate::request::Animation {
            base: 192,
            palette: 3,
        });
        assert_eq!(arrow_obj(&map).unwrap(), 0x8000 | GOLD_ROOM | 5 << 9 | 300);
        // With the eight taken, the cells.
        let sprite = map.sprite.as_mut().unwrap();
        sprite.palettes = vec![vec![[1, 2, 3]]; 4];
        sprite.animation = Some(crate::request::Animation {
            base: 192,
            palette: 4,
        });
        sprite.image = (256, 3);
        assert_eq!(arrow_obj(&map).unwrap(), 0);
        // The gold window's 44 tiles after the arrow's two, while they reach.
        let sprite = map.sprite.as_mut().unwrap();
        sprite.image = (0, 0);
        sprite.animation = None;
        let gold = ARROW_OBJ_TILES + GOLD_OBJ_TILES;
        sprite.tiles = vec![0; (cap - gold) * TILE_BYTES];
        assert_eq!(
            arrow_obj(&map).unwrap(),
            0x8000 | GOLD_ROOM | 7 << 9 | (cap - gold) as u16
        );
        // And without them, the arrow alone, until the last tile but one.
        let sprite = map.sprite.as_mut().unwrap();
        sprite.tiles = vec![0; (cap - gold + 1) * TILE_BYTES];
        assert_eq!(
            arrow_obj(&map).unwrap(),
            0x8000 | 7 << 9 | (cap - gold + 1) as u16
        );
        let sprite = map.sprite.as_mut().unwrap();
        sprite.tiles = vec![0; (cap - 2) * TILE_BYTES];
        assert_eq!(arrow_obj(&map).unwrap(), 0x8000 | 7 << 9 | (cap - 2) as u16);
        map.sprite.as_mut().unwrap().tiles = vec![0; (cap - 1) * TILE_BYTES];
        assert_eq!(arrow_obj(&map).unwrap(), 0);
        // A map nobody is drawn in has the whole bank.
        map.sprite = None;
        assert_eq!(arrow_obj(&map).unwrap(), 0x8000 | GOLD_ROOM | 7 << 9);
    }

    #[test]
    fn the_twins_go_behind_the_positions_with_how_many() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut map = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps
            .remove(0);
        map.events = vec![[1, 2], [3, 4]];
        // Without twins, the word says none: the console reads it always.
        assert_eq!(ev_pos_bytes(&map).unwrap(), [1, 0, 2, 0, 3, 0, 4, 0, 0, 0]);
        map.twins = vec![[5, 6, 1], [7, 8, 0]];
        assert_eq!(
            ev_pos_bytes(&map).unwrap(),
            [1, 0, 2, 0, 3, 0, 4, 0, 2, 0, 5, 0, 6, 0, 1, 0, 7, 0, 8, 0, 0, 0]
        );
        assert_eq!(
            ev_pos_bytes(&map).unwrap().len(),
            2 * EV_STRIDE + 2 + 2 * TWIN_STRIDE
        );
        // One that points past the map's events is the converter's mistake.
        map.twins = vec![[5, 6, 2]];
        assert!(ev_pos_bytes(&map).is_err());
    }

    #[test]
    fn a_map_whose_code_does_not_fit_in_wram_keeps_it_in_the_cartridge() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut maps = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps;
        maps.truncate(2);
        // The first one fits, at the cap; the second goes over by a byte.
        maps[0].evcode = vec![1; LZ2_CAP_CODE];
        maps[1].evcode = (0..=LZ2_CAP_CODE).map(|i| i as u8).collect();
        maps[1].pages = test_pages(1);
        assert!(!code_in_rom(&maps[0]));
        assert!(code_in_rom(&maps[1]));
        // The second decompresses nothing behind its grid.
        assert!(raw_blocks(&maps[1])["map_code"].is_empty());
        let written = super::maps(&maps).map(|w| w.maps + &w.tables).unwrap();
        // Its bytecode goes whole in one bank, and its `map_code` entry says
        // 0 bytes behind the grid, so that `carry_one` never matches it.
        assert!(
            written.contains(&format!(".block {}\nrom_code_0:", LZ2_CAP_CODE + 1)),
            "no rom_code_0"
        );
        assert!(
            written.contains(".word .loword(rom_code_0), 0\n"),
            "the entry is not empty"
        );
        assert!(
            written.contains(&format!("), {LZ2_CAP_CODE}\n")),
            "the first lost its length"
        );
        // And its pages point there.
        assert!(
            written.contains("<(rom_code_0 + "),
            "no page points into the cartridge"
        );
        // Past one bank it goes in two blocks, cut where a page starts:
        // the second page, in the second block, points at its start.
        maps[1].evcode = vec![1; ROM_CODE_MAX + 10];
        maps[1].pages = test_pages(2);
        maps[1].pages[1].offset = ROM_CODE_MAX;
        let chunks = rom_code_chunks(&maps[1]).unwrap();
        let cuts: Vec<(usize, usize)> = chunks.iter().map(|(s, b)| (*s, b.len())).collect();
        assert_eq!(cuts, [(0, ROM_CODE_MAX), (ROM_CODE_MAX, 10)]);
        let written = super::maps(&maps).map(|w| w.maps + &w.tables).unwrap();
        assert!(
            written.contains("<(rom_code_1 + 0)"),
            "the second page is not in the second block"
        );
        // But a page longer than a bank cannot be laid out.
        maps[1].pages[1].offset = 5;
        let error = super::maps(&maps).err().unwrap().to_string();
        assert!(error.contains("in a bank"), "{error}");
    }

    #[test]
    fn a_map_with_more_pages_than_the_console_walks_is_refused() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut map = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps
            .remove(0);
        map.pages = test_pages(MAX_PAGES as i64);
        check_counts(&map).unwrap();
        map.pages = test_pages(MAX_PAGES as i64 + 1);
        let error = check_counts(&map).unwrap_err().to_string();
        assert!(error.contains("2049 event pages and 2048 fit"), "{error}");
    }

    #[test]
    fn a_cache_goes_where_the_console_reads_it_and_its_rows_carry_their_still_pose() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut maps = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps;
        // Nobody has one: a zero per map.
        let none = cache_table(&maps).unwrap();
        assert!(
            none.contains(&format!(
                "cache_maps:\n    .word {}\n",
                vec!["0"; maps.len()].join(", ")
            )),
            "{none}"
        );
        // A map with objects gets a cache of two slots, blocks 5 and 6, and
        // two still poses; every event it draws starts with the second, but
        // the first, which walks.
        let k = maps
            .iter()
            .position(|m| m.sprite.is_some() && !m.npcs.is_empty())
            .unwrap();
        let events: Vec<(i64, Option<u32>, u32)> = maps[k]
            .npcs
            .iter()
            .enumerate()
            .map(|(i, n)| (n.event, (i > 0).then_some(1), 3))
            .collect();
        let walker = maps[k].npcs[0].event;
        maps[k].movable = vec![walker];
        maps[k].sprite.as_mut().unwrap().cache = Some(crate::request::Cache {
            events,
            stills: vec![("Folk".into(), 0, 7, 2, 3), ("Folk".into(), 0, 4, 0, 3)],
            slots: vec![5, 6],
        });
        let table = cache_table(&maps).unwrap();
        let mut starts = vec!["0"; maps.len()];
        starts[k] = "1";
        assert!(
            table.contains(&format!("cache_maps:\n    .word {}\n", starts.join(", "))),
            "{table}"
        );
        // Its record: how many slots, where the still poses start, and each
        // slot's first tile.
        let stills_at = 1 + 3 + 4;
        assert!(
            table.contains(&format!("    .byte 2\n    .word {stills_at}\n")),
            "{table}"
        );
        assert!(
            table.contains(&format!("    .word {}, {}\n", block_tile(5), block_tile(6))),
            "{table}"
        );
        // Each still pose's place in `npc_poses`.
        assert!(
            table.contains(&format!("    .word {}, {}\n", (2 * 12 + 7) * 3, 4 * 3)),
            "{table}"
        );
        assert!(
            table.contains(&format!(".block {}\ncache_data:", stills_at + 4)),
            "{table}"
        );
        for (line, value, max) in literals(&table) {
            assert!(
                (0..=max).contains(&value),
                "{value} does not fit in: {line}"
            );
        }
        // The rows: the still ones carry their pose in the tile byte, the
        // walking one a zero; all with the cache's palette.
        let rows = npc_table(&maps[k]).unwrap();
        for row in &rows {
            let expected = if row.event == walker { 0 } else { 1 };
            assert_eq!(
                (row.tile, row.palette),
                (expected, 3),
                "event {}",
                row.event
            );
        }
        // A twin of the walker —a still one that animates in its slot—
        // carries the walker's key, 128 plus it, its poses and the bit
        // that walks its column; the walker uploads even hidden.
        let twin = maps[k].npcs[1].event;
        let (charset, index) = (maps[k].npcs[0].charset.clone(), maps[k].npcs[0].index);
        maps[k].npcs[1].charset = charset;
        maps[k].npcs[1].index = index;
        maps[k].animates_with = vec![[twin, walker]];
        let rows = npc_table(&maps[k]).unwrap();
        let row = rows.iter().find(|r| r.event == twin).unwrap();
        assert_eq!(row.tile, 0x80 | walker as u32);
        assert!(row.animates && row.poses.is_some() && !row.leads);
        assert!(rows.iter().find(|r| r.event == walker).unwrap().leads);
    }

    #[test]
    fn the_shared_slots_go_where_the_console_reads_them() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json");
        let mut maps = crate::request::read::<crate::request::Maps>(&path)
            .unwrap()
            .maps;
        // Nobody shares: a zero per map, and the byte offset 0 points at.
        let none = share_table(&maps).unwrap();
        assert!(
            none.contains(&format!(
                "share_maps:\n    .word {}\n",
                vec!["0"; maps.len()].join(", ")
            )),
            "{none}"
        );
        // A map with objects and three events shares two slots, blocks 5 and
        // 6, among its first three events; the third one does not take turns.
        let k = maps
            .iter()
            .position(|m| m.sprite.is_some() && m.events.len() >= 3)
            .unwrap();
        let events = maps[k].events.len();
        maps[k].sprite.as_mut().unwrap().shared = Some(crate::request::Shared {
            events: vec![(0, 0, 1, 2), (1, 1, 0, 3)],
            poses: vec![(2, 7), (0, 4)],
            slots: vec![5, 6],
        });
        let table = share_table(&maps).unwrap();
        let mut starts = vec!["0"; maps.len()];
        starts[k] = "1";
        assert!(
            table.contains(&format!("share_maps:\n    .word {}\n", starts.join(", "))),
            "{table}"
        );
        // Its record: the event table after the header and two slots, the
        // pose table after one entry per event of the map.
        let events_at = 1 + 5 + 4;
        let poses_at = events_at + 2 * events;
        assert!(
            table.contains(&format!("    .word {events_at}, {poses_at}\n    .byte 2\n")),
            "{table}"
        );
        // A block's VRAM is its first tile times sixteen words.
        assert!(
            table.contains(&format!(
                "    .word {}, {}\n",
                block_tile(5) * 16,
                block_tile(6) * 16
            )),
            "{table}"
        );
        assert!(table.contains("    .byte $00,1, $01,0, $FF,0"), "{table}");
        // Each pose's place in `npc_poses`: three bytes a pose, twelve a
        // character.
        assert!(
            table.contains(&format!("    .word {}, {}\n", (2 * 12 + 7) * 3, 4 * 3)),
            "{table}"
        );
        assert!(
            table.contains(&format!(".block {}\nshare_data:", poses_at + 4)),
            "{table}"
        );
        for (line, value, max) in literals(&table) {
            assert!(
                (0..=max).contains(&value),
                "{value} does not fit in: {line}"
            );
        }
    }
}
