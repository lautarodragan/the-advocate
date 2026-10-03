//! The game, as much of it as the screens read: of the database the terms,
//! the actors, the items and the System's name, font and way of filling a
//! window; and of the game's folder the System's picture and the faces.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types, so there is no model of the format here. The other
//! sections are not parsed.

use crate::fail::{Bad, Result};
use ditto::dump::Dump;
use ditto::schema::{Actor, Item, System, Terms};
use rm2k_render::picture::{self, Picture};
use rm2k_rules::system::{self as system_rules, Background};
use rm2k_snes_text::font::Font;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// The item types this reads: `lcf::rpg::Item::Type`.
pub const ITEM_MEDICINE: i32 = 6;
pub const ITEM_SWITCH: i32 = 10;

/// The five bytes cp1252 does not define. Ditto keeps them as their C1
/// control, and a text that carries one is in another encoding —the
/// leftovers of a Japanese RPG Maker—: the screens have no letters for
/// it, and would draw it wrong.
const C1: [char; 5] = ['\u{81}', '\u{8d}', '\u{8f}', '\u{90}', '\u{9d}'];

/// What the screens read of a game.
#[derive(Debug, Clone)]
pub struct Game {
    pub terms: Terms,
    pub actors: BTreeMap<i32, Actor>,
    pub items: BTreeMap<i32, Item>,
    pub system: System,
    /// The game's folder, where the System and the FaceSets are.
    pub game_dir: PathBuf,
    /// The font every text is drawn with: RM2k's, the one `font_id` asks
    /// for, until a request names another —see [`Game::use_font`]—.
    pub font: Font,
}

fn answer(e: ditto::lcf::Error) -> Bad {
    Bad::answer(e.0)
}

impl Game {
    /// The game in the dump at `data`, with its pictures in `game_dir`.
    pub fn from_dump(data: &Path, game_dir: &Path) -> Result<Game> {
        let dump = Dump::open(data).map_err(answer)?;
        let actors: Vec<Actor> = dump.section("actors").map_err(answer)?;
        let items: Vec<Item> = dump.section("items").map_err(answer)?;
        let system: System = dump.section("system").map_err(answer)?;
        Ok(Game {
            terms: dump.section("terms").map_err(answer)?,
            actors: actors.into_iter().map(|a| (a.id, a)).collect(),
            items: items.into_iter().map(|i| (i.id, i)).collect(),
            font: Font::rm2k(system.font_id.to_i32()),
            system,
            game_dir: game_dir.to_path_buf(),
        })
    }

    /// Draws with the font `spec` names: `rm2k`, one the engine carries,
    /// or the path of a sheet —see `rm2k_snes_text::font`—. It is what the
    /// project file's `[text] font` says, and the converter passes it on;
    /// with `spacing` pixels more after every letter, its `[text]
    /// letter_spacing` —see `Font::with_spacing`—.
    pub fn use_font(&mut self, spec: &str, spacing: i64) -> Result<()> {
        self.font = Font::named(spec, self.font_id())
            .and_then(|f| f.with_spacing(spacing))
            .map_err(Bad::answer)?;
        Ok(())
    }

    /// The font the game asks for: `font_id`, 0 Gothic and 1 Mincho.
    pub fn font_id(&self) -> i32 {
        self.system.font_id.to_i32()
    }

    /// The game's System, the one the database names, read with its
    /// colour key; and how its windows fill their background.
    ///
    /// The System is looked for in the game's `System/`, and then in the
    /// game's folder itself.
    pub fn skin(&self) -> Result<Skin> {
        let name = &self.system.system_name;
        let background = system_rules::background(self.system.message_stretch).ok_or_else(|| {
            Bad::answer(format!(
                "the System's `message_stretch`, {:?}, is not one RM2k draws",
                self.system.message_stretch
            ))
        })?;
        for base in [self.game_dir.join("System"), self.game_dir.clone()] {
            let path = base.join(format!("{name}.png"));
            if path.exists() {
                return Ok(Skin {
                    picture: picture::read_rm2k(&path)?,
                    background,
                    path,
                });
            }
        }
        Err(Bad::answer(format!(
            "System {name:?} is not in {}",
            self.game_dir.display()
        )))
    }

    /// Actor `number`'s face, 48x48, or None if it has none. It is looked
    /// for in the game's `FaceSet/`.
    pub fn face(&self, number: i32) -> Result<Option<Picture>> {
        let actor = &self.actors[&number];
        if actor.face_name.is_empty() {
            return Ok(None);
        }
        let path = self
            .game_dir
            .join("FaceSet")
            .join(format!("{}.png", actor.face_name));
        let faceset = picture::read_rm2k(&path)?;
        Ok(Some(rm2k_render::face::face(&faceset, actor.face_index)))
    }

    /// Actor `number`'s name, or "" if there is no such actor.
    pub fn actor_name(&self, number: i32) -> Result<String> {
        match self.actors.get(&number) {
            None => Ok(String::new()),
            Some(a) => plain(&a.name),
        }
    }

    /// An item's name and description.
    pub fn item_name(&self, number: i32) -> Result<String> {
        plain(&self.item(number)?.name)
    }

    pub fn item_description(&self, number: i32) -> Result<String> {
        plain(&self.item(number)?.description)
    }

    pub fn item(&self, number: i32) -> Result<&Item> {
        self.items
            .get(&number)
            .ok_or_else(|| Bad::answer(format!("there is no item {number} in the database")))
    }

    /// A term of the database, by its liblcf name.
    pub fn term(&self, name: &str) -> Result<String> {
        let t = &self.terms;
        let value = match name {
            "new_game" => &t.new_game,
            "load_game" => &t.load_game,
            "load_game_message" => &t.load_game_message,
            "save_game_message" => &t.save_game_message,
            "file" => &t.file,
            "lvl_short" => &t.lvl_short,
            "gold" => &t.gold,
            "normal_status" => &t.normal_status,
            "hp_short" => &t.hp_short,
            "exp_short" => &t.exp_short,
            "command_item" => &t.command_item,
            "command_skill" => &t.command_skill,
            "menu_equipment" => &t.menu_equipment,
            "menu_save" => &t.menu_save,
            "menu_quit" => &t.menu_quit,
            "attack" => &t.attack,
            "defense" => &t.defense,
            "spirit" => &t.spirit,
            "agility" => &t.agility,
            "weapon" => &t.weapon,
            "shield" => &t.shield,
            "armor" => &t.armor,
            "helmet" => &t.helmet,
            "accessory" => &t.accessory,
            "possessed_items" => &t.possessed_items,
            "equipped_items" => &t.equipped_items,
            "exit_game_message" => &t.exit_game_message,
            "yes" => &t.yes,
            "no" => &t.no,
            _ => return self.shop_term(name),
        };
        plain(value)
    }

    /// One of the shop's terms: `shop_greeting1` to `shop_sold3`.
    fn shop_term(&self, name: &str) -> Result<String> {
        let t = &self.terms;
        let sets = [
            [
                &t.shop_greeting1, &t.shop_regreeting1, &t.shop_buy1, &t.shop_sell1,
                &t.shop_leave1, &t.shop_buy_select1, &t.shop_buy_number1, &t.shop_purchased1,
                &t.shop_sell_select1, &t.shop_sell_number1, &t.shop_sold1,
            ],
            [
                &t.shop_greeting2, &t.shop_regreeting2, &t.shop_buy2, &t.shop_sell2,
                &t.shop_leave2, &t.shop_buy_select2, &t.shop_buy_number2, &t.shop_purchased2,
                &t.shop_sell_select2, &t.shop_sell_number2, &t.shop_sold2,
            ],
            [
                &t.shop_greeting3, &t.shop_regreeting3, &t.shop_buy3, &t.shop_sell3,
                &t.shop_leave3, &t.shop_buy_select3, &t.shop_buy_number3, &t.shop_purchased3,
                &t.shop_sell_select3, &t.shop_sell_number3, &t.shop_sold3,
            ],
        ];
        let set = name
            .chars()
            .last()
            .and_then(|c| c.to_digit(10))
            .filter(|&d| (1..=3).contains(&d));
        let base = name.trim_end_matches(['1', '2', '3']);
        let order = [
            "shop_greeting", "shop_regreeting", "shop_buy", "shop_sell", "shop_leave",
            "shop_buy_select", "shop_buy_number", "shop_purchased", "shop_sell_select",
            "shop_sell_number", "shop_sold",
        ];
        match (set, order.iter().position(|o| *o == base)) {
            (Some(set), Some(k)) => plain(sets[set as usize - 1][k]),
            _ => Err(Bad::usage(format!("the screens do not read the term {name:?}"))),
        }
    }
}

/// A text of the game as the screens take it. One in another encoding
/// —see [`C1`]— or with a letter cp1252 does not have is refused: the
/// screens could not write it.
pub fn plain(text: &str) -> Result<String> {
    if text.chars().any(|c| C1.contains(&c) || !cp1252(c)) {
        return Err(Bad::answer(format!(
            "{text:?} is not in cp1252, and the screens only write that"
        )));
    }
    Ok(text.to_string())
}

/// Whether cp1252 has the character.
fn cp1252(c: char) -> bool {
    const HIGH: &str = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ";
    (c as u32) < 0x80 || (0xA0..=0xFF).contains(&(c as u32)) || HIGH.contains(c)
}

/// The System, read, with how its windows fill their background.
#[derive(Debug, Clone)]
pub struct Skin {
    pub picture: Picture,
    pub background: Background,
    pub path: PathBuf,
}

impl Skin {
    /// An empty window: the background and the frame on top.
    pub fn window(&self, width: usize, height: usize) -> Picture {
        rm2k_render::system::window(&self.picture, width, height, self.background)
    }

    /// The cursor of a list, the first of the System's two drawings.
    pub fn cursor(&self, width: usize, height: usize) -> Picture {
        rm2k_render::system::cursor(&self.picture, width, height, 0)
    }

    /// A line of text in colour `color`: see `rm2k_snes_text::line`.
    #[allow(clippy::too_many_arguments)]
    pub fn draw_line(
        &self,
        dest: &mut Picture,
        x: i64,
        y: i64,
        text: &str,
        color: i32,
        font: &Font,
    ) -> i64 {
        rm2k_snes_text::line::draw_line(dest, &self.picture, x, y, text, color, font)
    }
}
