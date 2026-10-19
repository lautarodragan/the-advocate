//! The game, as much of it as the screens read: of the database the terms,
//! the actors, the items and the System's name, font and way of filling a
//! window; and of the game's folder the System's picture and the faces.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types, so there is no model of the format here. The other
//! sections are not parsed.

use crate::fail::{Bad, Result};
use ditto::dump::Dump;
use ditto::schema::{Actor, Attribute, Item, Skill, State, System, Terms};
use rm2k_render::picture::{self, Picture};
use rm2k_render::source::find_resource;
use rm2k_rules::system::{self as system_rules, Background, BACKGROUND, PIECE};
use rm2k_snes_text::font::Font;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// The item types this reads: `lcf::rpg::Item::Type`.
pub const ITEM_MEDICINE: i32 = 6;
pub const ITEM_MATERIAL: i32 = 8;
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
    /// The skills and the states, which the skills screen reads.
    pub skills: BTreeMap<i32, Skill>,
    pub states: Vec<State>,
    /// The attributes, in id order: a skill with a physical one is grey
    /// unless the actor's weapon carries it —see
    /// [`rm2k_rules::skill::weapons_allow`]—.
    pub attributes: Vec<Attribute>,
    pub system: System,
    /// The game's folder, where the System and the FaceSets are.
    pub game_dir: PathBuf,
    /// The RTP the game was made with, where the System and the FaceSets
    /// it does not ship are: `--rtp-dir`. None, only the game's folder.
    pub rtp_dir: Option<PathBuf>,
    /// The font every text is drawn with: RM2k's, the one `font_id` asks
    /// for, until a request names another —see [`Game::use_font`]—.
    pub font: Font,
    /// The System's picture when the project names a file of its own
    /// —see [`Game::use_system`]—: then it is not looked for.
    pub system_file: Option<PathBuf>,
    /// The colour the windows are drawn over instead of the System's own
    /// background —see [`Game::use_window_background`]—: None, the System's.
    pub window_background: Option<[u8; 3]>,
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
        let skills: Vec<Skill> = dump.section("skills").map_err(answer)?;
        let states: Vec<State> = dump.section("states").map_err(answer)?;
        let attributes: Vec<Attribute> = dump.section("attributes").map_err(answer)?;
        Ok(Game {
            terms: dump.section("terms").map_err(answer)?,
            actors: actors.into_iter().map(|a| (a.id, a)).collect(),
            items: items.into_iter().map(|i| (i.id, i)).collect(),
            skills: skills.into_iter().map(|s| (s.id, s)).collect(),
            states,
            attributes,
            font: Font::rm2k(system.font_id.to_i32()),
            system,
            game_dir: game_dir.to_path_buf(),
            rtp_dir: None,
            system_file: None,
            window_background: None,
        })
    }

    /// Draws with the System `spec` names instead of the database's: the
    /// project file's `[graphics] system`, which the converter passes on.
    /// A picture's path —it ends in `.png` or `.bmp`— is read as is; any
    /// other text is a name, looked for as the database's would be.
    pub fn use_system(&mut self, spec: &str) {
        let lower = spec.to_ascii_lowercase();
        if lower.ends_with(".png") || lower.ends_with(".bmp") {
            self.system_file = Some(PathBuf::from(spec));
        } else {
            self.system.system_name = spec.to_string();
        }
    }

    /// Draws every window over one colour, `"#rrggbb"`, instead of the
    /// System's background: the project file's `[windows.background]` for
    /// the System this draws with, which the converter passes on —a
    /// gradient arrives as the one colour it is drawn with for now—. The
    /// System keeps giving the frame, the cursor, the arrow, the digits and
    /// the text colours.
    pub fn use_window_background(&mut self, spec: &str) -> Result<()> {
        let hex = spec.strip_prefix('#').filter(|h| h.len() == 6 && h.chars().all(|c| c.is_ascii_hexdigit()));
        let hex = hex.ok_or_else(|| Bad::usage(format!("a window background is \"#rrggbb\", and {spec:?} is not")))?;
        let channel = |k: usize| u8::from_str_radix(&hex[k..k + 2], 16).unwrap();
        self.window_background = Some([channel(0), channel(2), channel(4)]);
        Ok(())
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

    /// The game's System, the one the database names —or the project,
    /// see [`Game::use_system`]—, read with its
    /// colour key; and how its windows fill their background.
    ///
    /// The System is looked for in the game's `System/`, then in the
    /// game's folder itself, and then in the RTP's `System/`; without regard
    /// to case, as RPG_RT finds it on Windows.
    pub fn skin(&self) -> Result<Skin> {
        let name = &self.system.system_name;
        let background = system_rules::background(self.system.message_stretch).ok_or_else(|| {
            Bad::answer(format!(
                "the System's `message_stretch`, {:?}, is not one RM2k draws",
                self.system.message_stretch
            ))
        })?;
        let found = self
            .system_file
            .clone()
            .or_else(|| find_resource(&[self.game_dir.clone()], "System", name))
            .or_else(|| Some(self.game_dir.join(format!("{name}.png"))).filter(|p| p.exists()))
            .or_else(|| find_resource(&self.rtp(), "System", name));
        match found {
            Some(path) => Ok(Skin {
                picture: self.flattened(picture::read_rm2k(&path)?),
                background,
                path,
                redrawn: None,
            }),
            None => Err(Bad::answer(format!(
                "System {name:?} is not in {}{}",
                self.game_dir.display(),
                self.rtp_dir.as_ref().map_or(String::new(), |r| format!(" nor in {}", r.display()))
            ))),
        }
    }

    /// The System with its background's square filled with
    /// [`Game::window_background`], if there is one: stretched or tiled,
    /// one colour fills a window the same, so every window drawn from the
    /// skin —the message window, the screens', the battle's— gets it, and
    /// takes one entry of colour memory for it.
    fn flattened(&self, mut system: Picture) -> Picture {
        let Some([r, g, b]) = self.window_background else {
            return system;
        };
        let square = Picture::filled(PIECE as usize, PIECE as usize, [r, g, b, 255]);
        system.put(BACKGROUND.0 as usize, BACKGROUND.1 as usize, &square);
        system
    }

    /// The RTP, as a list of directories to look in: empty without one.
    fn rtp(&self) -> Vec<PathBuf> {
        self.rtp_dir.iter().cloned().collect()
    }

    /// Actor `number`'s face, 48x48, or None if it has none. It is looked
    /// for in the game's `FaceSet/` and then in the RTP's, in any case.
    pub fn face(&self, number: i32) -> Result<Option<Picture>> {
        let actor = &self.actors[&number];
        if actor.face_name.is_empty() {
            return Ok(None);
        }
        let mut dirs = vec![self.game_dir.clone()];
        dirs.extend(self.rtp());
        let path = find_resource(&dirs, "FaceSet", &actor.face_name).ok_or_else(|| {
            Bad::answer(format!("FaceSet {:?} is not in {}", actor.face_name, self.game_dir.display()))
        })?;
        let faceset = picture::read_rm2k(&path)?;
        Ok(Some(rm2k_render::face::face(&faceset, actor.face_index)))
    }

    /// Actor `number`'s CharSet, the database's, or None if it has none or
    /// the game does not have it. It is looked for in the game's `CharSet/`
    /// and then in the RTP's, in any case.
    pub fn charset(&self, number: i32) -> Result<Option<Picture>> {
        let actor = &self.actors[&number];
        if actor.character_name.is_empty() {
            return Ok(None);
        }
        let mut dirs = vec![self.game_dir.clone()];
        dirs.extend(self.rtp());
        match find_resource(&dirs, "CharSet", &actor.character_name) {
            Some(path) => Ok(Some(picture::read_rm2k(&path)?)),
            None => Ok(None),
        }
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

    pub fn skill(&self, number: i32) -> Result<&Skill> {
        self.skills
            .get(&number)
            .ok_or_else(|| Bad::answer(format!("there is no skill {number} in the database")))
    }

    /// A skill's name and description as the cartridge carries them: in
    /// the text block, with a '?' for each letter the font lacks —`Texts`
    /// in the emission—, and not refused like the screens' own texts: they
    /// are the battle's, which carries them that way.
    pub fn skill_name(&self, number: i32) -> Result<String> {
        Ok(crate::texts::item_text(&self.skill(number)?.name, usize::MAX))
    }

    pub fn skill_description(&self, number: i32) -> Result<String> {
        Ok(crate::texts::item_text(&self.skill(number)?.description, usize::MAX))
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
            "exit_game" => &t.exit_game,
            "load_game_message" => &t.load_game_message,
            "save_game_message" => &t.save_game_message,
            "file" => &t.file,
            "lvl_short" => &t.lvl_short,
            "gold" => &t.gold,
            "normal_status" => &t.normal_status,
            "hp_short" => &t.hp_short,
            "sp_short" => &t.sp_short,
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
            "sp_cost" => &t.sp_cost,
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
    /// The cells a screen's windows are redrawn with so that they fit their
    /// bank: `None`, as RM2k draws them. See `fit`.
    pub redrawn: Option<std::rc::Rc<crate::fit::Redrawn>>,
}

impl Skin {
    /// An empty window: the background and the frame on top.
    pub fn window(&self, width: usize, height: usize) -> Picture {
        rm2k_render::system::window(&self.picture, width, height, self.background)
    }

    /// A window's background alone, without its frame.
    pub fn window_background(&self, width: usize, height: usize) -> Picture {
        rm2k_render::system::window_background(&self.picture, width, height, self.background)
    }

    /// A screen's windows, drawn whole on a screen-sized `layer`, redrawn
    /// with the cells `fit` chose for them if they had to be: what the
    /// screens that cut their windows into a bank of tiles call last.
    pub fn redraw(&self, layer: &mut Picture) {
        if let Some(redrawn) = &self.redrawn {
            redrawn.apply(layer);
        }
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
