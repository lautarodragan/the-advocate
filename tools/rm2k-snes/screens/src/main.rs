//! A game's screens from the command line: a dump, the game's folder and a
//! request in, what the cartridge carries of its screens out.
//!
//! Where the dump and the pictures are is the caller's to say: nothing here
//! has a default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_render::picture::{self, Picture};
use rm2k_snes_screens::request::Json;
use rm2k_snes_screens::{boxes, convert, layout, render, Bad, Game, Result};
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
}

#[derive(ClapArgs)]
#[command(after_help = "`convert` writes screens.json into --out: the message window \
    (its tiles and text-area tiles in hex, its palette words, cells, the font and its four \
    precomposed tables), the title's menu, the slot and menu bank, the text screens' font, \
    the windows of the item, equipment, shop and actor-choice screens as the cartridge \
    stores them, End Game, the texts the cartridge composes, the geometry, and what the \
    conversion says. Its request carries `slots`, `actors`, `items`, `bank_items`, `title`, \
    `cgram_reserved` and `vram` (`slot_vram`, `slot_map` and each layout's BG1 bank as \
    [name, from, to]).\n\n\
    `render` writes screen.png, RGB. Its request carries `screen` —menu, items, target, \
    slots, equipment, shop or end_game— and that screen's state: see `render.rs`.")]
struct GameArgs {
    /// The Ditto dump the game is read from: the directory with maps/ and
    /// db/
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    /// The game's folder, with System/ and FaceSet/ inside
    #[arg(long = "game-dir", value_name = "DIRECTORY")]
    game_dir: PathBuf,

    /// What the cartridge decided
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,
}

#[derive(ClapArgs)]
#[command(after_help = "Writes boxes.json into --out: the boxes that change, as \
    {\"from\": lines, \"to\": boxes}. The request carries `columns` and `lines`, the \
    window's size in characters, and `map_files`, the project's maps over the dump's, by \
    number.")]
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
    The request carries `columns` and `lines` too, the window's size in characters.")]
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

fn do_convert(args: &GameArgs) -> Result<()> {
    let game = Game::from_dump(&args.data, &args.game_dir)?;
    let request = Json::read(&args.request)?.convert()?;
    let answer = convert::convert(&game, &request)?;
    write(&args.out, "screens.json", &answer.to_string())
}

fn do_render(args: &GameArgs) -> Result<()> {
    let game = Game::from_dump(&args.data, &args.game_dir)?;
    let skin = game.skin()?;
    let json = Json::read(&args.request)?;
    let slots = json.index_or("slots", 0)?;
    let chosen = json.index_or("chosen", 0)?;
    let screen: Picture = match json.text("screen")?.as_str() {
        "menu" => render::menu(
            &game,
            &skin,
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
            &skin,
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
                &skin,
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
                &skin,
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
        "shop" => render::shop_screen(&game, &skin, &json.shop()?)?,
        "end_game" => render::end_game_screen(&game, &skin, chosen)?,
        other => {
            return Err(Bad::answer(format!(
                "{}: `screen` is {other:?}, and it is menu, items, target, slots, equipment, \
                 shop or end_game",
                json.whose
            )))
        }
    };
    std::fs::create_dir_all(&args.out).map_err(|e| Bad::usage(format!("{}: {e}", args.out.display())))?;
    picture::write_png(&args.out.join("screen.png"), &screen)?;
    Ok(())
}

fn do_boxes(args: &BoxesArgs) -> Result<()> {
    let json = Json::read(&args.request)?;
    let table = boxes::table(
        &args.data,
        &json.files("map_files")?,
        json.index_or("columns", 0)?,
        json.index_or("lines", 0)?,
    )?;
    write(&args.out, "boxes.json", &table.to_string())
}

fn do_equip(args: &GameArgs) -> Result<()> {
    let game = Game::from_dump(&args.data, &args.game_dir)?;
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
    let answer = boxes::refit_each(&boxes, json.index_or("columns", 0)?, json.index_or("lines", 0)?);
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
