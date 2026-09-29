//! An event: which of its pages is showing, what that page draws, and what
//! it does to the cell it stands on.

use crate::chipset::UPPER;
use crate::passability::{ABOVE, ALL};
use ditto::schema::{Event, EventPage, EventPageAnimType, EventPageCondition, EventPageLayers};

/// The opacity RM2k draws a translucent page with, out of 255.
pub const TRANSLUCENT_OPACITY: u8 = 160;

/// Whether a condition asks for anything. A page without one is always
/// eligible.
pub fn conditioned(condition: &EventPageCondition) -> bool {
    let f = &condition.flags;
    f.switch_a || f.switch_b || f.variable || f.item || f.actor || f.timer
}

/// The page the engine shows **in a freshly started game**: RM2k takes the
/// highest-numbered page whose conditions all hold, and with no switch,
/// variable or item set that is the last page with no condition at all.
/// There may be none.
///
/// It answers for a new game and nothing else: with the game running, which
/// page is showing is the interpreter's to know.
pub fn starting_page(event: &Event) -> Option<&EventPage> {
    let mut pages: Vec<&EventPage> = event.pages.iter().collect();
    pages.sort_by_key(|p| p.id);
    pages.into_iter().rev().find(|p| !conditioned(&p.condition))
}

/// What a page draws.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Graphic {
    /// Character `index` of a CharSet, in pose `pose` —see
    /// [`crate::charset::pose`]—.
    CharSet { name: String, index: i32, pose: i32 },
    /// A plain tile of the ChipSet's upper layer: `tile` is 0 to 143, the id
    /// `UPPER + tile`. It is how doors, chests and much of the decoration are
    /// made. The page still has a direction and a pattern, and `pose` is
    /// what they say, which a tile does not use.
    Tile { tile: i32, pose: i32 },
}

/// What `page` draws, or `None`: no CharSet and tile 0 is "no graphic".
pub fn page_graphic(page: &EventPage) -> Option<Graphic> {
    let pose = crate::charset::pose(page.character_direction, page.character_pattern);
    if !page.character_name.is_empty() {
        return Some(Graphic::CharSet {
            name: page.character_name.clone(),
            index: page.character_index,
            pose,
        });
    }
    (page.character_index != 0).then_some(Graphic::Tile { tile: page.character_index, pose })
}

/// Whether an event on this layer stops the hero: only the hero's own
/// layer collides with him.
pub fn blocks(layer: EventPageLayers) -> bool {
    layer == EventPageLayers::Same
}

/// Whether a page animates while standing still: "continuous" and "fixed
/// direction, continuous".
pub fn continuous(animation: EventPageAnimType) -> bool {
    matches!(animation, EventPageAnimType::Continuous | EventPageAnimType::FixedContinuous)
}

/// The four side bits an event imposes on its cell, or `None` if it imposes
/// nothing: easyrpg's `Game_Map::IsPassableTile`.
///
/// An event **below** the hero drawn with a tile replaces the terrain's
/// passability with its tile's, read from the upper layer's table —`flags`
/// is [`crate::chipset::passability_table`]—, unless the tile is one of
/// those that go above. That is how a door opens: the cell is a wall, and
/// with its switch on, the page shows a tile that can be stepped on.
pub fn tile_passability(flags: &[u8], graphic: &Graphic, layer: EventPageLayers) -> Option<u8> {
    let Graphic::Tile { tile, .. } = graphic else {
        return None;
    };
    if layer != EventPageLayers::Below {
        return None;
    }
    let value = flags[(UPPER + tile) as usize];
    (value & ABOVE == 0).then_some(value & ALL)
}
