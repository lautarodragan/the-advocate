//! A game's screens from the command line: a dump, the game's folder and a
//! request in, what the cartridge carries of its screens out.
//!
//! Where the dump and the pictures are is the caller's to say: nothing here
//! has a default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_render::picture::{self, Picture};
use rm2k_snes_screens::request::Json;
use rm2k_snes_screens::game::Skin;
use rm2k_snes_screens::{boxes, convert, fit, layout, message_window, render, Bad, Game, Result};
use rm2k_snes_text::font::Font;
use rm2k_snes_text::refit::Measure;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// "The window uses more colours than a palette holds" is this tool
/// answering no; "that flag makes no sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-screens",
    about = "An RPG Maker 2000 game's screens, for a Super Nintendo cartridge",
    after_help = "Exit codes: 1 the answer is no (a screen does not fit, the dump is broken), \
                  2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Every screen a cartridge carries: the message window and its font,
    /// the title's menu, the save slots and the pause menu, the text
    /// screens with their windows, and End Game
    Convert(GameArgs),
    /// One screen as the console has to show it, built from what the
    /// cartridge uploads
    Render(GameArgs),
    /// Every message box of the game reflowed for the console's window
    Boxes(BoxesArgs),
    /// The message boxes of the request reflowed for the console's window
    Refit(LayoutArgs),
    /// The geometry the screens are drawn with, by name
    Layout(LayoutArgs),
    /// What equipping an item leaves, as the equipment screen does it
    #[command(after_help = "Writes equip.json into --out: {\"equipment\": the five slots, \
        \"inventory\": item number to how many}, after `Game_Actor::ChangeEquipment`. The \
        request carries `equipment`, `inventory`, `slot` and `item`, 0 to unequip.")]
    Equip(GameArgs),
    /// How many colour-memory entries the message window takes, from the
    /// game's System
    #[command(after_help = "Writes window.json into --out: {\"colors\": n, \"brought\": m, \
        \"merges\": [[from, to, pixels], ...], \"system\": its name}. The window takes entries 1 to n of colour \
        memory —0 is transparent—, so whatever shares the lower palettes with it starts at \
        n + 1. A System with more than fifteen is reduced by Adeleine: m is how many it \
        brought, and the merges are what it lost, in order.\n\n\
        Its request may carry `systems`, the other Systems the cartridge switches to, \
        [{\"system\": name, \"background\": \"#rrggbb\" or null, \"stretch\": n or null}]: \
        then the text takes the same entries in all of them, `text_rows` answers which glyph rows \
        take one each —what `convert` takes back—, n is what the starting one takes with them, the \
        others are reduced to fit in it, and \
        `systems` answers each one's window as `convert` writes it, without the font, with \
        its `brought`, `merges`, `colors` and `frame_fused`.")]
    Window(GameArgs),
}

#[derive(ClapArgs)]
#[command(after_help = "`convert` writes screens.json into --out: the message window \
    (its tiles and text-area tiles in hex, its palette words, cells, the font and its four \
    precomposed tables), the title's menu, the slot and menu bank, the text screens' font, \
    the windows of the item, equipment, shop and actor-choice screens as the cartridge \
    stores them, End Game, the texts the cartridge composes, the geometry, and what the \
    conversion says. Its request carries `font` and `letter_spacing`, as `boxes` takes \
    them, `slots`, `actors`, `items`, `title`, \
    `cgram_reserved` and `vram` (`slot_vram`, `slot_map` and each layout's BG1 bank as \
    [name, from, to]).\n\n\
    `render` writes screen.png, RGB. Its request carries `screen` —menu, items, target, \
    slots, equipment, shop, end_game or title— and that screen's state: see `render.rs`.")]
struct GameArgs {
    /// The Ditto dump the game is read from: the directory with maps/ and
    /// db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    /// The game's folder, with System/ and FaceSet/ inside
    #[arg(long = "game-dir", value_name = "DIRECTORY")]
    game_dir: PathBuf,

    /// The RTP the game was made with: the System and the faces the game
    /// does not ship are looked for there
    #[arg(long = "rtp-dir", value_name = "DIRECTORY")]
    rtp_dir: Option<PathBuf>,

    /// The System to draw with instead of the one the database names: a
    /// name, looked for like the database's, or the path of a picture
    #[arg(long, value_name = "NAME|PATH")]
    system: Option<String>,

    /// The colour every window is drawn over instead of the System's
    /// background, "#rrggbb": the System keeps giving its frame, cursor,
    /// arrow and text colours
    #[arg(long = "window-background", value_name = "#RRGGBB")]
    window_background: Option<String>,

    /// What the cartridge decided
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

impl GameArgs {
    /// The game, with its RTP.
    fn game(&self) -> Result<Game> {
        let mut game = Game::from_dump(&self.data, &self.game_dir)?;
        game.rtp_dir = self.rtp_dir.clone();
        if let Some(system) = &self.system {
            game.use_system(system);
        }
        if let Some(background) = &self.window_background {
            game.use_window_background(background)?;
        }
        Ok(game)
    }
}

#[derive(ClapArgs)]
#[command(after_help = "Writes boxes.json into --out: the boxes that change, as \
    {\"from\": lines, \"to\": boxes}. The request carries the window: `font` —`rm2k`, \
    one the engine carries, or a sheet's path— and `letter_spacing`, pixels more after \
    every letter, 0 if missing; `width`, a line's pixels, and `lines`; or, without `font`, \
    `columns` characters of RM2k's font. And `map_files`, the project's \
    maps over the dump's, by number.")]
struct BoxesArgs {
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,
    #[arg(long, value_name = "PATH")]
    request: PathBuf,
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(after_help = "`layout` writes layout.json into --out, and its request is \
    ignored: it is taken so every subcommand is called the same way.\n\n\
    `refit` writes refit.json: for each of the request's `boxes`, each a list of lines, \
    {\"to\": the boxes it becomes, \"speaker\": whether its first line names who speaks}. \
    The request carries the window too, as `boxes` takes it.")]
struct LayoutArgs {
    #[arg(long, value_name = "PATH")]
    request: Option<PathBuf>,
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

fn write(out: &Path, name: &str, text: &str) -> Result<()> {
    std::fs::create_dir_all(out).map_err(|e| Bad::usage(format!("{}: {e}", out.display())))?;
    std::fs::write(out.join(name), text).map_err(|e| Bad::usage(format!("{}: {e}", out.join(name).display())))
}

/// The game, drawing with the font the request names: `font`, which is the
/// project file's `[text] font` —`rm2k`, one the engine carries, or the
/// path of a sheet—, spaced by its `letter_spacing`.
fn game_with_font(args: &GameArgs, json: &Json) -> Result<Game> {
    let mut game = args.game()?;
    game.use_font(&json.text("font")?, json.number_or("letter_spacing", 0)?)?;
    Ok(game)
}

fn do_convert(args: &GameArgs) -> Result<()> {
    let json = Json::read(&args.request)?;
    let game = game_with_font(args, &json)?;
    let request = json.convert()?;
    let answer = convert::convert(&game, &request)?;
    write(&args.out, "screens.json", &answer.to_string())
}

fn do_render(args: &GameArgs) -> Result<()> {
    let json = Json::read(&args.request)?;
    let game = game_with_font(args, &json)?;
    let skin = game.skin()?;
    let slots = json.index_or("slots", 0)?;
    let chosen = json.index_or("chosen", 0)?;
    // The System each screen's windows are drawn with: the one `convert`
    // gives the cartridge, redrawn if they do not fit —see `fit`—. The item
    // and equipment windows leave room for the text of the items the
    // cartridge knows: the request's `items`, and without it, the
    // inventory's, as the screens themselves take them.
    let fitted = |screen| -> Result<Skin> {
        let text = if screen == fit::Screen::Items {
            let items: Vec<i32> = match json.known_items("items")? {
                Some(known) => known.into_iter().collect(),
                None => json.by_number("inventory").map(|i| i.into_keys().collect()).unwrap_or_default(),
            };
            convert::item_pairs(&game, &skin, &items)?
        } else {
            0
        };
        Ok(fit::skin_for(&game, &skin, screen, text)?.0)
    };
    let screen: Picture = match json.text("screen")?.as_str() {
        // The pause menu's bar is the actor choice's: see `menu_bar_layer`.
        "menu" => render::menu(
            &game,
            &fitted(fit::Screen::Target)?,
            slots,
            &json.party()?,
            json.number_or("gold", 0)?,
            chosen,
            json.flag("save_allowed", true)?,
            match json.number_or("choosing", -1)? {
                n if n < 0 => None,
                n => Some(n as usize),
            },
        )?,
        "target" => render::target(
            &game,
            &fitted(fit::Screen::Target)?,
            slots,
            &json.party()?,
            chosen,
            json.number("item")? as i32,
            json.number_or("amount", 0)?,
        )?,
        "items" => {
            let known = json.known_items("items")?.map(|k| k.into_iter().collect::<Vec<_>>());
            render::item_screen(
                &game,
                &fitted(fit::Screen::Items)?,
                &json.by_number("inventory")?,
                chosen,
                json.index_or("top", 0)?,
                known.as_deref(),
            )?
        }
        "slots" => {
            let levels = json
                .by_number("levels")?
                .into_iter()
                .map(|(k, v)| (k as usize, v))
                .collect();
            render::slot_screen(
                &game,
                &skin,
                slots,
                &json.flags("full")?,
                chosen,
                json.index_or("mode", 0)?,
                &json.parties()?,
                &levels,
            )?
        }
        "equipment" => {
            let equipment: Vec<i32> = json.numbers("equipment")?.into_iter().map(|n| n as i32).collect();
            render::equipment_screen(
                &game,
                &fitted(fit::Screen::Items)?,
                json.number("actor")? as i32,
                &equipment,
                &json.by_number("inventory")?,
                json.index_or("slot", 0)?,
                json.flag("choosing", false)?,
                chosen,
                json.index_or("top", 0)?,
                json.known_items("items")?.as_ref(),
            )?
        }
        "shop" => render::shop_screen(&game, &fitted(fit::Screen::Shop)?, &json.shop()?)?,
        "skills" => {
            // The actor's level, HP and SP, each the starting one —and full—
            // when the request does not say.
            let actor = json.number("actor")? as i32;
            let a = game
                .actors
                .get(&actor)
                .ok_or_else(|| Bad::answer(format!("{}: there is no actor {actor}", json.whose)))?;
            let level = json.number_or("level", rm2k_rules::actor::level_of(a))?;
            let curve = |values: &[i16]| rm2k_rules::actor::curve_at(values, level).unwrap_or(0);
            let hp_max = json.number_or("hp_max", curve(&a.parameters.maxhp))?;
            let sp_max = json.number_or("sp_max", curve(&a.parameters.maxsp))?;
            let skills: Vec<i32> = json.numbers("skills")?.into_iter().map(|n| n as i32).collect();
            render::skill_screen(
                &game,
                &fitted(fit::Screen::Skills)?,
                actor,
                &skills,
                level,
                (json.number_or("hp", hp_max)?, hp_max),
                (json.number_or("sp", sp_max)?, sp_max),
                chosen,
                json.index_or("top", 0)?,
            )?
        }
        "end_game" => render::end_game_screen(&game, &skin, chosen)?,
        "title" => render::title_menu(&game, &skin, chosen, json.flag("saved", false)?)?,
        other => {
            return Err(Bad::answer(format!(
                "{}: `screen` is {other:?}, and it is menu, items, target, slots, equipment, \
                 shop, skills, end_game or title",
                json.whose
            )))
        }
    };
    std::fs::create_dir_all(&args.out).map_err(|e| Bad::usage(format!("{}: {e}", args.out.display())))?;
    picture::write_png(&args.out.join("screen.png"), &screen)?;
    Ok(())
}

/// How a request's window measures a line: `font` —the project file's
/// `[text] font`, spaced by `letter_spacing`— and `width` in pixels; or `advances`, each glyph's from
/// the space on, and `width`, which is the window the converter hands the
/// event compiler; or, without either, `columns` characters of RM2k's
/// fixed-width font, which is how it was asked until 2026-10-03.
fn measure_of(json: &Json) -> Result<Measure> {
    if json.data.get("advances").is_some_and(|f| !f.is_null()) {
        let advances = json.numbers("advances")?.into_iter().map(|a| a as u8).collect();
        return Ok(Measure::from_advances(advances, json.index_or("width", 0)?));
    }
    if json.data.get("font").is_some_and(|f| !f.is_null()) {
        let spacing = json.number_or("letter_spacing", 0)?;
        let font = Font::named(&json.text("font")?, rm2k_snes_text::font::MINCHO)
            .and_then(|f| f.with_spacing(spacing))
            .map_err(Bad::answer)?;
        Ok(Measure::new(&font, json.index_or("width", 0)?))
    } else {
        Ok(Measure::columns(json.index_or("columns", 0)?))
    }
}

fn do_boxes(args: &BoxesArgs) -> Result<()> {
    let json = Json::read(&args.request)?;
    let table = boxes::table(
        &args.data,
        &json.files("map_files")?,
        &measure_of(&json)?,
        json.index_or("lines", 0)?,
    )?;
    write(&args.out, "boxes.json", &table.to_string())
}

fn do_equip(args: &GameArgs) -> Result<()> {
    let game = args.game()?;
    let json = Json::read(&args.request)?;
    let mut equipment: Vec<i32> = json.numbers("equipment")?.into_iter().map(|n| n as i32).collect();
    let mut inventory = json.by_number("inventory")?;
    let slot = json.index_or("slot", 0)?;
    if slot >= equipment.len() {
        return Err(Bad::answer(format!("{}: there is no slot {slot}", json.whose)));
    }
    render::equip(&game, &mut equipment, &mut inventory, slot, json.number("item")? as i32)?;
    let inventory: serde_json::Map<String, serde_json::Value> =
        inventory.into_iter().map(|(k, v)| (k.to_string(), v.into())).collect();
    let answer = serde_json::json!({"equipment": equipment, "inventory": inventory});
    write(&args.out, "equip.json", &answer.to_string())
}

fn do_window(args: &GameArgs) -> Result<()> {
    let game = args.game()?;
    let skin = game.skin()?;
    let others = Json::read(&args.request)?.systems()?;
    let merges_json = |merges: &[adeleine::Merge]| -> Vec<serde_json::Value> {
        merges.iter().map(|m| serde_json::json!([m.victim, m.target, m.pixels])).collect()
    };
    if others.is_empty() {
        let (brought, merges) = message_window::reduction(&skin)?;
        let answer = serde_json::json!({
            "colors": message_window::colors(&skin)?, "brought": brought, "merges": merges_json(&merges),
            "system": game.system.system_name,
        });
        return write(&args.out, "window.json", &answer.to_string());
    }
    // Each other System is the same game drawn with it, over its own
    // background or none: the starting one's does not carry over.
    let mut skins = Vec::new();
    for other in &others {
        let mut drawn = args.game()?;
        drawn.system_file = None;
        drawn.use_system(&other.system);
        drawn.window_background = None;
        if let Some(background) = &other.background {
            drawn.use_window_background(background)?;
        }
        if let Some(stretch) = other.stretch {
            drawn.system.message_stretch = ditto::schema::SystemStretch::from_i32(stretch);
        }
        skins.push((other.system.clone(), drawn.skin()?));
    }
    let mut each = vec![message_window::text_rows(&skin)?];
    for (_, s) in &skins {
        each.push(message_window::text_rows(s)?);
    }
    let rows = message_window::common_rows(&each);
    // The starting System's entries are the cartridge's, and the others fit
    // in them: see `message_window::convert_with`.
    let colors = message_window::colors_with(&skin, Some(&rows))?;
    let mut systems = Vec::new();
    for (name, s) in &skins {
        let (brought, merges) = message_window::reduction_capped(s, Some(&rows), colors)?;
        let window = message_window::convert_with(s, colors + 1, Some(&rows))?;
        systems.push(serde_json::json!({
            "system": name,
            "window": convert::window_json(&window),
            "brought": brought,
            "merges": merges_json(&merges),
            "colors": colors,
            "frame_fused": window.frame_fused,
            "mixed_text_rows": message_window::mixed_text_rows(s),
        }));
    }
    let (brought, merges) = message_window::reduction_with(&skin, Some(&rows))?;
    let answer = serde_json::json!({
        "colors": colors, "brought": brought, "merges": merges_json(&merges),
        "system": game.system.system_name,
        "text_rows": rows,
        "systems": systems,
    });
    write(&args.out, "window.json", &answer.to_string())
}

fn do_layout(args: &LayoutArgs) -> Result<()> {
    write(&args.out, "layout.json", &layout::publish().to_string())
}

fn do_refit(args: &LayoutArgs) -> Result<()> {
    let path = args
        .request
        .as_ref()
        .ok_or_else(|| Bad::usage("refit needs --request, with the boxes"))?;
    let json = Json::read(path)?;
    let bad = || Bad::answer(format!("{}: `boxes` is not a list of lists of lines", json.whose));
    let boxes: Vec<Vec<String>> = json
        .data
        .get("boxes")
        .and_then(|b| b.as_array())
        .ok_or_else(bad)?
        .iter()
        .map(|lines| {
            lines
                .as_array()
                .ok_or_else(bad)?
                .iter()
                .map(|l| l.as_str().map(str::to_string).ok_or_else(bad))
                .collect()
        })
        .collect::<Result<_>>()?;
    let answer = boxes::refit_each(&boxes, &measure_of(&json)?, json.index_or("lines", 0)?);
    write(&args.out, "refit.json", &answer.to_string())
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Convert(args) => do_convert(args),
        Command::Render(args) => do_render(args),
        Command::Boxes(args) => do_boxes(args),
        Command::Layout(args) => do_layout(args),
        Command::Refit(args) => do_refit(args),
        Command::Equip(args) => do_equip(args),
        Command::Window(args) => do_window(args),
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            eprintln!("rm2k-snes-screens: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
