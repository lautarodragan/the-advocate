//! The conversion, in order: what the game says, each map, the pages,
//! the screens, the pictures, the battle, and the emission, the patches and
//! the music last.

use crate::animations::{self, Animations};
use crate::bytecode;
use crate::compiler::{
    self, variable_slot, CompileMap, Compiler, CASE_VARIABLE, COMPARE_AT_LEAST, TEST_SWITCH,
};
use crate::degradations::Degradations;
use crate::emit;
use crate::fail::{Result, Stop};
use crate::font::FontChoice;
use crate::fullscreen;
use crate::game::{Command, Game, GameMap};
use crate::maps::{self, Cartridge, MapInfo, PageRecord};
use crate::options::{case_map, Options};
use crate::pictures;
use crate::scan;
use crate::scene;
use crate::screens;
use crate::settings::Settings;
use crate::stage;
use crate::text::quoted;
use crate::variants;
use rm2k_project::Project;
use rm2k_snes_bytecode::events::{
    INN_GOLD_WINDOW, OP_FLASH, OP_INN, OP_ROUTE, OP_TELEPORT, OP_TELEPORT_FACING,
};
use rm2k_snes_events::codes::{ROUTE_CHANGE_GRAPHIC, TELEPORT, TIMER_OPERATION};
use rm2k_snes_events::request::{Picture, Place};
use rm2k_snes_events::route;
use rm2k_snes_mapdata::{engine, record, request, vram};

/// What fits in the title's VRAM: the image's 8bpp tiles (32 words each)
/// below `TITLE_MENU_MAP` ($4400) and the menu's 4bpp ones (16 words) from
/// $5000 to `SCREEN_MAP` ($7C00). They are the numbers `emit/header.rs`
/// writes and `title.s` asserts; this crate cannot read them from there.
/// Past the first, the title goes at 4bpp, where it always fits.
const TITLE_TILES_MAX: usize = 0x4400 / 32;
const TITLE_MENU_TILES_MAX: usize = (0x7C00 - 0x5000) / 16;

/// The battle's two stages: its tables, before the pages compile, and its
/// model, after.
const BATTLE_TABLES: stage::Stage = stage::Stage {
    binary: "rm2k-snes-battle",
    command: "tables",
};
const BATTLE_MODEL: stage::Stage = stage::Stage {
    binary: "rm2k-snes-battle",
    command: "model",
};
const AUDIO_CARTRIDGE: stage::Stage = stage::Stage {
    binary: "rm2k-snes-audio",
    command: "cartridge",
};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::PathBuf;

/// How many block pairs the ROM's substitution table holds at once. It is
/// `SUB_MAX` in the runtime's `low_ram.s`, and it is written on both sides
/// on purpose: the converter has to be able to refuse **before** emitting a
/// map that does not fit. `test_substitutions.py` compares the two.
pub const SUB_MAX: usize = 16;

/// The commands of a test page, as written by hand: the command by its
/// name or its number, and only the fields that say something.
pub fn handwritten_commands(path: &std::path::Path) -> Result<Vec<Command>> {
    let text = std::fs::read_to_string(path).map_err(|e| crate::fail::io(path, e))?;
    let data: Value =
        serde_json::from_str(&text).map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
    let mut out = Vec::new();
    for c in data["event_commands"]
        .as_array()
        .cloned()
        .unwrap_or_default()
    {
        let code = match &c["code"] {
            Value::String(name) => ditto::schema::EventCommandCode::from_json_name(name)
                .map(|c| c.to_i32())
                .ok_or_else(|| Stop::new(format!("{}: {name} is not a command", path.display())))?,
            other => other.as_i64().unwrap_or(0) as i32,
        };
        out.push(Command {
            code,
            indent: c.get("indent").and_then(Value::as_i64).unwrap_or(0) as i32,
            string: c
                .get("string")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            parameters: c
                .get("parameters")
                .and_then(Value::as_array)
                .map(|p| p.iter().map(|v| v.as_i64().unwrap_or(0) as i32).collect())
                .unwrap_or_default(),
        });
    }
    Ok(out)
}

/// Which party the test continues with after its page, if the page touches
/// it: the case's `ChangePartyMembers` applied to the cartridge's party.
fn page_party(commands: &[Command], party: &[i32]) -> Option<Vec<i32>> {
    let mut state = scan::PartyState::new(party);
    let mut touches = false;
    for cmd in commands {
        let p = &cmd.parameters;
        if cmd.code == rm2k_snes_events::codes::CHANGE_PARTY_MEMBERS
            && p.len() >= 3
            && p[1] == scan::PARTY_FIXED_ID
        {
            state.change_party(p[0], p[2]);
            touches = true;
        }
    }
    touches.then_some(state.party)
}

/// Where a compiled page flashes the hero, in order, as the flash check
/// in [`run`] reads it: the map's index the flash runs on —`here`, or the
/// last `Teleport`'s destination before it—, the graphic the last route on
/// the hero gave it —from `graphics`, the map's route graphics—, and
/// whether a teleport came before. The walk is in bytecode order and does
/// not follow jumps.
fn hero_flashes(
    code: &[u8],
    here: usize,
    graphics: &[(String, i64)],
) -> Result<Vec<(usize, Option<(String, i64)>, bool)>> {
    let mut out = Vec::new();
    let mut at = here;
    let mut teleported = false;
    let mut hero: Option<(String, i64)> = None;
    for i in bytecode::walk(code)? {
        if code[i] == OP_TELEPORT || code[i] == OP_TELEPORT_FACING {
            // The facing's byte goes before the map.
            let map = i + 1 + usize::from(code[i] == OP_TELEPORT_FACING);
            teleported = true;
            at = bytecode::at(code, map) as usize | (bytecode::at(code, map + 1) as usize) << 8;
        } else if code[i] == OP_ROUTE && bytecode::at(code, i + 1) == 0 {
            let path = &code[i + 4..i + 4 + bytecode::at(code, i + 3) as usize];
            // The operands come with their command, so a sound's index or a
            // switch's number whose low byte is 34 is not a graphic change.
            for (command, operands) in route::path_commands(path) {
                if command == ROUTE_CHANGE_GRAPHIC {
                    hero = operands
                        .first()
                        .and_then(|&g| graphics.get(g as usize))
                        .cloned();
                }
            }
        } else if code[i] == OP_FLASH && bytecode::at(code, i + 1) == 0 {
            out.push((at, hero.clone(), teleported));
        }
    }
    Ok(out)
}

fn join<T: ToString>(items: impl IntoIterator<Item = T>, sep: &str) -> String {
    items
        .into_iter()
        .map(|i| i.to_string())
        .collect::<Vec<_>>()
        .join(sep)
}

pub fn run(options: Options) -> Result<()> {
    let project = Project::locate(options.project.as_deref())?;
    let settings = Settings { project: &project };
    let mut environment = options.environment.clone();
    // A `.zip` game or RTP, as a directory from here on, and the game with
    // the port's own files on top: see `unpack`.
    environment.unpack(&project)?;
    // The stages' answers, from the disk cache when they were already
    // asked the same thing: see `stage`. `NO_CACHE=1` runs every one.
    if !rm2k_project::cache::disabled() {
        crate::stage::keep_answers_in(environment.cache(&project)?);
    }
    if let Some(own) = environment.own_files() {
        println!("The port's own files, in front of the game's:");
        for line in own.lines() {
            println!("  {line}");
        }
    }
    let order = options.map_order();
    if !(0 <= options.start_index && (options.start_index as usize) < order.len()) {
        crate::stop!(
            "--start-index {} but there are {} maps",
            options.start_index,
            order.len()
        );
    }
    let start_index = options.start_index as usize;
    let output = match &options.output {
        Some(o) => rm2k_project::absolute(o),
        None => project.build()?.join("inc").join("mapdata.inc"),
    };
    let game_dir = environment.game()?.to_path_buf();
    let rtp_dir = environment.rtp()?.to_path_buf();

    // The cases: each one's page, and the map where it runs.
    let mut cases: Vec<(String, Vec<Command>, i32)> = Vec::new();
    for file in &options.case_files {
        let commands = handwritten_commands(std::path::Path::new(file))?;
        let run_map = case_map(file, &commands, &order, start_index)?;
        cases.push((file.clone(), commands, run_map));
    }
    let file_commands: Vec<Command> = cases
        .iter()
        .flat_map(|(_, c, _)| c.iter().cloned())
        .collect();
    let case_pairs: Vec<(i32, Vec<Command>)> =
        cases.iter().map(|(_, c, m)| (*m, c.clone())).collect();

    let mut game = Game::read(&game_dir, &project)?;
    game.rtp_dir = Some(rtp_dir.clone());
    game.check_window_backgrounds()?;
    // The hero's graphic comes from the party: in RM2k the first of the
    // list gives it. An empty one is valid, as in RM2k: the hero is not
    // drawn until someone joins (`pick_hero_graphic` in the runtime).
    let party: Vec<i32> = match &options.party {
        Some(p) if !p.is_empty() => p.clone(),
        _ => game.db.party.clone(),
    };
    // The events that do not fit in the console's RAM, before anything
    // reads a map: from here on every stage numbers them without those.
    let test_event_map = (!cases.is_empty()).then(|| order[start_index]);
    let events_max = options
        .test_events_max
        .unwrap_or(rm2k_snes_mapdata::record::EV_MAX);
    game.trim(&order, &file_commands, test_event_map, events_max)?;
    // What the cartridge does with less than RM2k, gathered from whoever
    // loses it and written next to the ROM: see [`crate::degradations`].
    let mut degradations = Degradations::default();
    for &(map, event, at, what) in &game.trimmed {
        let text = format!("the event is left out: the console's RAM does not hold every event, and it loses {what}");
        degradations.event(
            map as i64,
            event as i64,
            (at.0 as i64, at.1 as i64),
            "event-left-out",
            &text,
        );
    }

    let search_dirs = search_dirs(&game, &project, &rtp_dir)?;

    // The cartridge's maps, read once.
    let mut every: Vec<GameMap> = Vec::new();
    for id in &order {
        every.push(game.map(*id)?);
    }
    let every_refs: Vec<&GameMap> = every.iter().collect();
    // Whether the message window keeps an entry for a box's ink, before
    // anything asks the screens for its colours.
    game.text_ink = scan::types_a_colour(
        every_refs.iter().copied(),
        &game.db.common_events,
        &file_commands,
    );

    // **The indices go before anything that compiles a page**: without the
    // variables' slots no `ControlVars` compiled in that pass, and the
    // actors a page adds were lost. The compiler answers both in its first
    // call: the whole game's indices and which pages of each map compile.
    let mut extra = BTreeSet::new();
    if cases.len() > 1 {
        // The one that picks the case. With a single one it isn't needed,
        // and that way that cartridge comes out the same as before `--case`.
        extra.insert(CASE_VARIABLE);
    }
    // And the ones the custom menus read: a variable no page names would
    // have no slot. In a game whose menus read what its pages write, which
    // is what a menu is for, this adds none.
    let custom_menus = settings.menus()?;
    for menu in &custom_menus {
        extra.extend(menu.variables().into_iter().map(|v| v as i32));
    }
    // The Systems the pages switch to, which the compiler numbers and the
    // screens draw a message window for.
    let (switched, any_system, system_says) =
        crate::systems::switched(&game, &every_refs, &file_commands);
    for line in &system_says {
        println!("{line}");
    }
    let mut compiler = Compiler::new(&game, &settings)?;
    // And the ones the custom menus' conditions ask for, which no page may
    // name.
    for menu in &custom_menus {
        compiler
            .extra_switches
            .extend(menu.switches().into_iter().map(|s| s as i32));
    }
    compiler.systems = crate::systems::names(&game, &switched, any_system);
    // The automatic common events with pictures, copied into every map
    // with room for them: see [`crate::common_pages`]. Not the ones whose
    // body is not their commands: a custom menu's and a counter's.
    let mut not_copied: BTreeSet<i32> = custom_menus
        .iter()
        .filter_map(|m| m.replaces_common())
        .collect();
    not_copied.extend(
        compiler::counters(&settings)?
            .iter()
            .map(|c| c.common_event),
    );
    let mut common_pages = crate::common_pages::CommonPages::decide(
        &game,
        &not_copied,
        &order,
        test_event_map,
        events_max,
    )?;
    compiler.common_pages = common_pages.request();
    // For `rm2k-snes-events culprits --request`, which asks the same thing
    // of the same dump.
    compiler.keep_request = output
        .parent()
        .map(|d| rm2k_project::absolute(d).join("events-request.json"));
    if !switched.is_empty() {
        println!("  Systems: {}", compiler.systems.join(", "));
    }
    let mut scan_answer =
        compiler.scan(&order, &file_commands, &extra, test_event_map, &case_pairs)?;
    // A copy is for the small pictures, and which pictures a body shows the
    // scan says: the ones whose copy would draw nothing are decided again
    // as not copied —they run anywhere then, and can turn on another's
    // switch—, and the scan asked again, so no map gathers their pictures.
    // A cartridge where every copy draws scans once, as before.
    let drawing_nothing = common_pages.drawing_nothing(&game, &scan_answer)?;
    if !drawing_nothing.is_empty() {
        println!(
            "  common events {}: not copied into the maps, every picture they show is big, and \
             a big one is the same with a map and without one",
            join(&drawing_nothing, ", ")
        );
        not_copied.extend(drawing_nothing);
        common_pages = crate::common_pages::CommonPages::decide(
            &game,
            &not_copied,
            &order,
            test_event_map,
            events_max,
        )?;
        compiler.common_pages = common_pages.request();
        scan_answer = compiler.scan(&order, &file_commands, &extra, test_event_map, &case_pairs)?;
    }
    if !common_pages.maps.is_empty() {
        println!(
            "  common events {} copied into {} of the {} maps, for their pictures",
            common_pages
                .commons
                .iter()
                .rev()
                .map(|n| n.to_string())
                .collect::<Vec<_>>()
                .join(", "),
            common_pages.maps.len(),
            order.len()
        );
    }
    let mut indices = scan_answer.indices.clone();
    if !cases.is_empty() {
        // The test pages turn it on, and the table has to hold it: the one
        // the scan found free, which is `TEST_SWITCH` unless the game names
        // it.
        let switch = indices.test_switch.ok_or_else(|| {
            Stop::new("the events' scan does not say which switch the test pages turn on")
        })?;
        if switch != TEST_SWITCH as i64 {
            println!("  the test pages turn on switch {switch}: the game names {TEST_SWITCH}");
        }
        compiler.test_switch = switch as i32;
        compiler.extra_switches.insert(switch as i32);
    }
    // The slot is a byte: the variables past it have no place in far RAM.
    // They are dropped from the list, and the compiler already leaves out
    // the pages that name one (`variable_slot`), so the game loses those
    // pages and not the cartridge.
    let slot_max = rm2k_snes_mapdata::engine::VAR_SLOT_MAX as i64;
    let lost: Vec<i64> = indices
        .variables
        .iter()
        .filter(|(_, s)| *s > slot_max)
        .map(|(v, _)| *v)
        .collect();
    if !lost.is_empty() {
        indices.variables.retain(|(_, s)| *s <= slot_max);
        println!(
            "WARNING: the game names {} variables and {} fit in far RAM: the pages that use one of the {} past it are left out (variables {:?})",
            indices.variables.len() + lost.len(),
            slot_max + 1,
            lost.len(),
            lost
        );
    }
    let changes = scan::party_changes(&every_refs, &scan_answer)?;
    let mut leaders = scan::possible_leaders(&changes, &party);
    // And those of the party each test page continues with: the test can
    // start with it in any map of the cartridge. Only in file order: see
    // `leaders_in_file_order`.
    for (_, commands, _) in &cases {
        if let Some(test_party) = page_party(commands, &party) {
            for actor in scan::leaders_in_file_order(&changes, &test_party) {
                if !leaders.contains(&actor) {
                    leaders.push(actor);
                }
            }
        }
    }
    // Which maps carry the timer digits, which cost a sprite palette: the
    // ones the timer can be running in. With `--no-timer`, only the maps
    // where a case that touches it runs. A map without digits doesn't draw
    // them.
    let mut timer_maps: BTreeSet<i32> = cases
        .iter()
        .filter(|(_, commands, _)| commands.iter().any(|c| c.code == TIMER_OPERATION))
        .map(|(_, _, m)| *m)
        .collect();
    if !options.no_timer {
        let never: BTreeSet<i32> = project
            .ints(&["graphics", "timer_never_runs_in"])?
            .into_iter()
            .map(|m| m as i32)
            .collect();
        // A knob at rest when it is missing, as `int_or` says: a game
        // without a hub the walk floods from does not write it.
        let stays: BTreeSet<i32> = match project.value(&["graphics", "timer_stays_in"]) {
            Err(_) => BTreeSet::new(),
            Ok(_) => project
                .ints(&["graphics", "timer_stays_in"])?
                .into_iter()
                .map(|m| m as i32)
                .collect(),
        };
        let counters: BTreeSet<i32> = compiler::counters(&settings)?
            .iter()
            .map(|c| c.common_event)
            .collect();
        timer_maps.extend(scan::timer_reach(
            &every_refs,
            &scan_answer,
            &game.db.common_events,
            &never,
            &stays,
            &counters,
        )?);
    }
    println!(
        "  the timer's digits go in {} of the {} maps: {}",
        timer_maps.len(),
        order.len(),
        join(&timer_maps, " ")
    );
    // If some map sets rain, all of them carry the drops.
    let with_rain = scan::has_rain(every_refs.iter().copied(), &file_commands);
    // And the sandstorm's grains, where it can blow. A common event or a
    // test page that starts one can run on any map: then all of them.
    let sand_maps: Option<BTreeSet<i32>> = if !scan::has_sandstorm(
        every_refs.iter().copied(),
        &game.db.common_events,
        &file_commands,
    ) {
        None
    } else if scan::has_sandstorm([], &game.db.common_events, &file_commands) {
        Some(order.iter().copied().collect())
    } else {
        Some(scan::sandstorm_reach(
            &every_refs,
            &scan_answer,
            &game.db.common_events,
        )?)
    };
    if let Some(maps) = &sand_maps {
        println!(
            "  the sandstorm's grains go in {} of the {} maps: {}",
            maps.len(),
            order.len(),
            join(maps, " ")
        );
    }
    let per_character = maps::maps_per_character(&every_refs);
    // Where the hero arrives is asked for the tiles above him nobody can
    // cover, and for the still events drawn past their cells: see `reach`.
    let arrivals = if game.unreachable_above_below
        || game.posed != crate::game::OnMaps::Nowhere
        || game.painted_events != crate::game::OnMaps::Nowhere
    {
        // Over the whole game's maps, not only the cartridge's: what a map
        // decides from it —its still events drawn past their cells, its
        // tiles above lowered— is then the same in every cartridge that
        // carries it, and a test cartridge tests what the playable ROM
        // draws. The versioned patches are checked on all of them.
        let others: Vec<GameMap> = game
            .dump_map_ids()?
            .into_iter()
            .filter(|id| !order.contains(id))
            .map(|id| game.map(id))
            .collect::<Result<_>>()?;
        let whole: Vec<&GameMap> = every_refs.iter().copied().chain(others.iter()).collect();
        let arrivals = crate::reach::Arrivals::gather(&game, &whole, &case_pairs)?;
        if let Some(why) = arrivals.anywhere() {
            println!("  the hero can be anywhere on every map: {why}");
        } else if let Some((why, on)) = arrivals.any_open() {
            match on {
                None => println!("  the hero can be on any cell one can step on: {why}"),
                Some(maps) => println!(
                    "  the hero can be on any cell one can step on of maps {}: {why}",
                    join(maps.iter().copied().collect::<Vec<_>>(), " ")
                ),
            }
        }
        arrivals
    } else {
        crate::reach::Arrivals::default()
    };

    let test_maps: BTreeSet<i32> = if cases.is_empty() {
        BTreeSet::from([order[start_index]])
    } else {
        cases.iter().map(|(_, _, m)| *m).collect()
    };
    // The message window's colours, from the System: once, for every map and
    // for the screens and the emission. See `screens::window_colors`.
    let (window_colors, window_answer) = screens::window_colors(&game, &switched)?;
    for other in &window_answer.systems {
        let rows = other.mixed_text_rows.len();
        if rows > 0 {
            let line = format!(
                "  WARNING, System {}: {rows} row(s) of its text colour are not one colour, and its message \
                 window draws each with the one most of it has",
                quoted(&other.other.system)
            );
            println!("{line}");
            degradations.cartridge("window-text-colour-merged", &line);
        }
        if let Some(had) = other.frame_fused {
            let line = format!(
                "  WARNING, System {}: its message window's frame and arrow took {had} tiles and were fused into \
                 bands to fit",
                quoted(&other.other.system)
            );
            println!("{line}");
            degradations.cartridge("window-frame-fused", &line);
        }
    }
    let map_pictures = if game.map_pictures {
        // The parts of the drawings that share a number go next to the
        // cartridge's `mapdata.inc`: see `map_pictures::Parts`.
        let cartridge_dir = output
            .parent()
            .map(rm2k_project::absolute)
            .unwrap_or_default();
        let decided = crate::map_pictures::decide(&every_refs, &game.game_dir, &cartridge_dir)?;
        println!(
            "  pictures drawn into their map: {} in {} of the {} maps",
            decided.per_map.values().map(Vec::len).sum::<usize>(),
            decided.per_map.len(),
            order.len()
        );
        for (map, shows) in &decided.per_map {
            let names: Vec<String> = shows
                .iter()
                .map(|p| format!("'{}' at {} %", p.name, 100 - p.transparency))
                .collect();
            println!("  map {map}: drawn into the map: {}", names.join(", "));
        }
        for ((map, number, name), path) in &decided.parts {
            println!(
                "  map {map}: the picture '{name}' under {number} shows only what it has of its own: {}",
                path.display()
            );
        }
        // The translucent big ones the rule leaves as pictures stay over
        // black, with the map hidden: a loss, next to the ROM.
        for h in &decided.hidden {
            let text = format!(
                "the picture '{}', at {} % over the map, is shown over black with the map hidden: {}",
                h.name,
                100 - h.transparency,
                h.why
            );
            degradations.event(
                h.map as i64,
                h.event as i64,
                (h.at.0 as i64, h.at.1 as i64),
                "translucent-picture-hides-the-map",
                &text,
            );
        }
        decided
    } else {
        crate::map_pictures::MapPictures::default()
    };
    let cartridge = Cartridge {
        game: &game,
        settings: &settings,
        scan: &scan_answer,
        order: order.clone(),
        start_index,
        has_cases: !cases.is_empty(),
        cases: case_pairs.clone(),
        test_graphics: options.test_graphic.clone(),
        test_maps: test_maps.clone(),
        leaders: leaders.clone(),
        timer_maps: timer_maps.clone(),
        with_rain,
        sand_maps,
        // How a map shows its panorama is Wally's to decide; the project
        // can only force it, by map, and does not have to say anything.
        panorama_ways: match settings.table(&["maps", "panorama_ways"]) {
            Ok(Value::Object(t)) => t
                .iter()
                .map(|(k, v)| {
                    let map = k.parse::<i32>().map_err(|_| {
                        Stop::new(format!("[maps] panorama_ways: {k:?} is not a map"))
                    })?;
                    let way = v.as_str().ok_or_else(|| {
                        Stop::new(format!("[maps] panorama_ways: map {k} is {v}, not a way"))
                    })?;
                    Ok((map, way.to_string()))
                })
                .collect::<Result<_>>()?,
            _ => BTreeMap::new(),
        },
        maps_per_character: per_character,
        search_dirs: search_dirs.clone(),
        common_substitutions: maps::common_substitutions(&game),
        map_pictures,
        window_colors,
        common_pages: common_pages.clone(),
        arrivals,
    };
    let mut animation_cache = Animations::new(&search_dirs, &game.dump);
    let mut prepared = Vec::new();
    // What stops one map says which in its own line, also from Wally's
    // calls in `run_requests`: see `Stop::in_map`.
    for id in &order {
        prepared
            .push(maps::prepare(&cartridge, &mut animation_cache, *id).map_err(|e| e.in_map(*id))?);
    }
    // And each map once more for each ChipSet its pages swap in, in the
    // same run: see `variants.rs`.
    let mut asked: Vec<(usize, i32, bool, Value)> = Vec::new();
    for (k, p) in prepared.iter().enumerate() {
        for chipset in variants::asked(&game, &p.map) {
            let draws = !variants::draws_alike(&game, p.map.chipset_id, chipset);
            asked.push((
                k,
                chipset,
                draws,
                variants::request(&p.request, p.map.id, chipset),
            ));
        }
    }
    let requests: Vec<(i32, &Value)> = prepared
        .iter()
        .map(|p| (p.map.id, &p.request))
        .chain(asked.iter().map(|(k, _, _, r)| (prepared[*k].map.id, r)))
        .collect();
    let mut answers = maps::run_requests(&cartridge, &requests)?;
    let theirs = answers.split_off(prepared.len());
    let mut drawn: BTreeMap<usize, Vec<variants::Drawn>> = BTreeMap::new();
    for ((k, chipset, draws, _), written) in asked.iter().zip(&theirs) {
        let d = variants::drawn(written, *chipset, *draws)
            .map_err(|e| e.in_map(prepared[*k].map.id))?;
        drawn.entry(*k).or_default().push(d);
    }
    let mut infos: Vec<MapInfo> = Vec::new();
    for (k, (p, written)) in prepared.into_iter().zip(answers).enumerate() {
        let id = p.map.id;
        let mut info = maps::map_info(&game, p, written).map_err(|e| e.in_map(id))?;
        if let Some(d) = drawn.remove(&k) {
            let events = info.events_drawn.clone();
            info.variants = variants::take(&game, &mut info, &events, d);
        }
        infos.push(info);
    }
    // A map whose grid does not fit in WRAM either way —see `cell_bytes` in
    // rm2k-snes-mapdata— is left out, before anything compiles a teleport
    // to it: those become the box that says the map is missing. Only the
    // boot map stops the conversion.
    let mut left_out = Vec::new();
    infos.retain(|m| {
        let ram = m.blocks.len() + m.block_pass.len();
        let blocks = m.blocks.len() / rm2k_snes_mapdata::materials::BLOCK_BYTES;
        if rm2k_snes_mapdata::materials::cell_bytes(m.cells.len() / 2, blocks, ram).is_some() {
            return true;
        }
        left_out.push((m.id, m.map.width, m.map.height, blocks));
        false
    });
    for &(id, width, height, blocks) in &left_out {
        if id == order[start_index] {
            crate::stop!("map {id} is where the ROM boots, and its grid of {width}x{height} cells and {blocks} blocks does not fit in WRAM");
        }
        let line = format!(
            "  map {id}: WARNING, it is left out: its grid of {width}x{height} cells and {blocks} blocks does not fit in \
             WRAM, neither two bytes a cell nor one; see `cell_bytes` in rm2k-snes-mapdata"
        );
        println!("{line}");
        degradations.map(id as i64, "map-left-out", &line, &[]);
    }
    let boot_map = order[start_index];
    let order: Vec<i32> = infos.iter().map(|m| m.id).collect();
    let start_index = order
        .iter()
        .position(|&m| m == boot_map)
        .expect("the boot map stays");
    // The big pictures, which the cartridge carries once whatever map shows
    // them. And last, so no map's numbers move, the ones the common events
    // without a map show —the automatic and parallel ones, which run on any
    // map—: a big picture is the same on every map, so their bodies show it
    // wherever they run. See `common_pictures` in `rm2k-snes-events`.
    //
    // **Only a common event that shows one big picture at a time**: the
    // layer holds one, and each one it shows takes the screen off to load.
    // A body that stacks several —Desert Nightmare's picture menus, dozens
    // under as many numbers, redrawn at every key— would show the last one
    // alone, over black, after a run of black frames; it stays as it was,
    // with its pictures not shown and the map under its keys. That is
    // judged by the numbers: big pictures under two numbers can be up
    // together, under one they cannot.
    let mut common_bigs = Vec::new();
    for c in &scan_answer.commons_pictures {
        let n = c.common;
        let bigs = pictures::big_for_map(
            &game.game_dir,
            &pictures::keys(&c.pictures),
            &c.zooms,
            &format!("common event {n}"),
            &game.cropped,
            &|_| false,
            None,
        )?;
        let numbers: BTreeSet<i64> = bigs.iter().map(|b| i64::from(b.key.number)).collect();
        if numbers.len() > 1 {
            println!(
                "  common event {n}: its {} big pictures are not shown: they are under {} \
                 numbers, so they can be up together, and the layer holds one",
                bigs.len(),
                numbers.len()
            );
            continue;
        }
        common_bigs.extend(bigs);
    }
    let mut bigs: Vec<&[pictures::Big]> = infos.iter().map(|m| m.big_pictures.as_slice()).collect();
    bigs.push(&common_bigs);
    let (mut big_layers, mut big_tables) = pictures::number_big(&bigs);
    // A byte names them: the common events' take what the maps leave of
    // it, in the order they were met —they come last, so leaving one out
    // moves no number before it—, and the rest are not shown, as before.
    let kept: Vec<pictures::Big>;
    if big_layers.len() > pictures::BIG_IMAGES {
        let fits = |entry: &Picture| {
            matches!(entry.place, Place::Background { image, .. }
                if usize::from(image) < pictures::BIG_IMAGES)
        };
        kept = common_bigs
            .iter()
            .zip(big_tables.last().into_iter().flatten())
            .filter(|(_, e)| fits(e))
            .map(|(b, _)| b.clone())
            .collect();
        let left_out = common_bigs.len() - kept.len();
        bigs.pop();
        if pictures::number_big(&bigs).0.len() > pictures::BIG_IMAGES {
            crate::stop!(
                "the maps show more big pictures than the {} the cartridge's table names",
                pictures::BIG_IMAGES
            );
        }
        println!(
            "  the common events: WARNING, {left_out} of their big pictures are not shown: with \
             the maps' they pass the {} the cartridge's table names",
            pictures::BIG_IMAGES
        );
        bigs.push(&kept);
        (big_layers, big_tables) = pictures::number_big(&bigs);
    }
    pictures::keep_objects(&mut big_layers);
    pictures::say_big(&big_layers);
    compiler.common_pictures = big_tables.pop().unwrap_or_default();
    // And their small ones, in the cartridge's common table, after the big
    // ones: see [`crate::common_pictures`].
    let common_small = crate::common_pictures::sets(&game, &scan_answer)?;
    compiler
        .common_pictures
        .extend(common_small.entries.iter().cloned());
    compiler.common_sets = common_small.sets.clone();
    for (m, table) in infos.iter_mut().zip(big_tables) {
        m.big_table = table;
    }
    // Teleports are resolved when all the maps are there.
    let table_index: BTreeMap<i32, usize> =
        infos.iter().enumerate().map(|(n, m)| (m.id, n)).collect();
    for m in &infos {
        for (upper, old, new) in &m.missing_substitutions {
            // It doesn't stop the conversion: the page that asks for it
            // doesn't compile. But it is said, because from outside it
            // looks like an event that does nothing.
            println!(
                "  map {}: TileSubstitution {old} -> {new} on the {} layer: the block that would be \
                 needed can't be built. Either the new tile isn't drawn in any cell of the map, or \
                 one of the two is an upper tile without 'Above' and is baked into the background. \
                 The page doesn't compile.",
                m.id,
                if *upper { "upper" } else { "lower" }
            );
        }
    }

    // The actors that can be in the party when saving, to have their face
    // and their name in the cartridge. A superset on purpose.
    let members = scan::possible_members(every_refs.iter().copied(), &party, &file_commands);
    // The random encounters of each map, and the experience tables:
    // `rm2k-snes-battle`'s first call.
    let request = rm2k_snes_battle::Request {
        party: members.iter().map(|&a| a.into()).collect(),
        maps: infos
            .iter()
            .map(|m| rm2k_snes_battle::Map {
                id: m.id.into(),
                width: m.map.width.into(),
                height: m.map.height.into(),
            })
            .collect(),
        encounter_steps: options.test_encounters,
        tree_nodes: game.tree.added_nodes.clone(),
    };
    let written = stage::call(
        BATTLE_TABLES,
        &json!(request),
        &["--data".into(), game.dump.clone().into_os_string()],
        || rm2k_snes_battle::stage::tables(&game.dump, &request),
    )?;
    let tables_answer: rm2k_snes_battle::Answer = stage::typed(&written, "battle.json")?;
    let encounters = tables_answer.encounters;
    let battle_tables = request::BattleTables {
        experience: stage::text(&written, "experience.inc")?,
        slots: tables_answer.experience.slots,
        encounters: stage::text(&written, "encounters.inc")?,
    };
    if encounters.records != 0 {
        println!(
            "  random encounters: {} map(s), {} zone(s), {} troop(s)",
            encounters.records,
            encounters.zones,
            encounters.troops.len()
        );
    }
    // Every page of the cartridge, compiled: `rm2k-snes-events`' second
    // call.
    let compile_maps: Vec<CompileMap> = infos
        .iter()
        .map(|m| CompileMap {
            id: m.id,
            names: compiler::names([&m.map]),
            substitution_table: m.substitution_table.clone(),
            pictures: m.pictures.as_ref().map(|(_, table, _)| table.clone()),
            big_table: m.big_table.clone(),
            panoramas: maps::panorama_names(m.panorama.as_ref()),
            tilesets: if m.variants.is_empty() {
                Vec::new()
            } else {
                std::iter::once(m.map.chipset_id)
                    .chain(m.variants.iter().map(|v| v.chipset))
                    .collect()
            },
            route_graphics: m
                .route_graphics
                .iter()
                .map(|(name, index)| (name.clone(), *index as i32))
                .collect(),
        })
        .collect();
    let test_graphics: BTreeMap<i32, Vec<(String, i32)>> = match &options.test_graphic {
        Some(graphics) if !graphics.is_empty() => {
            test_maps.iter().map(|m| (*m, graphics.clone())).collect()
        }
        _ => BTreeMap::new(),
    };
    let compiled = compiler.compile(
        &compile_maps,
        &case_pairs,
        &file_commands,
        &extra,
        test_event_map,
        &test_graphics,
        &encounters
            .troops
            .iter()
            .map(|&t| t as i32)
            .collect::<Vec<_>>(),
    )?;
    degradations.add_compiler_answer(&compiled);
    // The events the RAM left out that Wally painted into their map lose
    // nothing: see `Loss::Painted` in [`crate::trim`].
    let painted: BTreeSet<(i64, i64)> = infos
        .iter()
        .flat_map(|m| m.painted_trimmed.iter().map(move |&e| (m.id as i64, e)))
        .collect();
    degradations.forget(|l| {
        l["kind"] == "event-left-out"
            && match (l["map"].as_i64(), l["event"].as_i64()) {
                (Some(m), Some(e)) => painted.contains(&(m, e)),
                _ => false,
            }
    });
    // The pictures drawn into their map were shown by the conversion, not
    // lost: the compiler is not given them, so it says they are not shown.
    degradations.forget(|l| {
        l["kind"] == "picture-not-shown"
            && l["map"].as_i64().is_some_and(|m| {
                cartridge
                    .map_pictures
                    .done(m as i32, l["subject"].as_str().unwrap_or(""))
            })
    });
    // Nor is the picture a `ChangePBG` names on a map whose panorama is
    // never seen, the map's own or that one: keeping the one there is
    // loses nothing.
    let unseen: BTreeSet<i64> = infos
        .iter()
        .filter(|m| m.panorama_unseen)
        .map(|m| m.id as i64)
        .collect();
    degradations.forget(|l| {
        l["kind"] == "panorama-not-changed"
            && l["map"].as_i64().is_some_and(|m| unseen.contains(&m))
    });
    // And what the copies of the automatic common events lose: the common
    // event's own body says it once, under `"common"`, and a copy whose
    // pictures did not go in has its map's `pictures-not-drawn`. See
    // [`crate::common_pages`].
    let copy_events: BTreeSet<(i64, i64)> = infos
        .iter()
        .filter(|m| cartridge.common_pages.maps.contains(&m.id))
        .filter_map(|m| m.map.events.last().map(|e| (m.id as i64, e.id as i64)))
        .collect();
    degradations.forget(|l| match (l["map"].as_i64(), l["event"].as_i64()) {
        (Some(m), Some(e)) => copy_events.contains(&(m, e)),
        _ => false,
    });
    let messages = compiled.messages.data.0.clone();
    let message_count = compiled.messages.count as i64;
    let troops = scene::Troops {
        ids: compiled.troops.ids.clone(),
        backdrops: compiled.troops.backdrops.iter().cloned().collect(),
    };
    // A troop of the cartridge's with more members than a battle holds:
    // which ones it left out, see `rm2k_snes_battle::fit`.
    for (n, cut) in &game.db.troop_cuts {
        if troops.ids.contains(n) {
            println!("{}", cut.text());
            degradations.troop(*n as i64, "troop-members-left-out", &cut.text());
        }
    }
    if let Some(commons) = &compiled.commons {
        let bodies = &commons.bodies;
        println!(
            "shared common events: {} bodies, {} bytes; automatic ones that run: {}; left out, not compiling: {}",
            bodies.len(),
            bodies.iter().map(|(_, code)| code.0.len()).sum::<usize>(),
            join(commons.autostart.iter().map(|(_, body)| bodies[*body as usize].0), ", "),
            if commons.left_out.is_empty() {
                "none".to_string()
            } else {
                join(&commons.left_out, ", ")
            }
        );
    }
    let mut test_code: Vec<Vec<u8>> = Vec::new();
    for (k, code) in compiled.cases.iter().enumerate() {
        match code {
            None => crate::stop!("{}: the test page doesn't compile", cases[k].0),
            Some(code) => test_code.push(code.0.clone()),
        }
    }

    let triggers = [
        engine::TRIGGER_ACTION as i64,
        engine::TRIGGER_TOUCH_HERO as i64,
        engine::TRIGGER_COLLISION as i64,
        engine::TRIGGER_AUTOSTART as i64,
        engine::TRIGGER_PARALLEL as i64,
    ];
    for m in infos.iter_mut() {
        let entry = compiled
            .map(m.id)
            .ok_or_else(|| Stop::new(format!("map {} is not in the answer", m.id)))?;
        // The pages of the map's events: their conditions, and the code of
        // the ones that can be run.
        let pages = maps::pages(&entry.pages, m)?;
        // And which substitutions they asked for: the blocks their pairs
        // start from are the keys of the ROM's table. See `SUB_MAX`.
        let mut sub_keys = BTreeSet::new();
        for &(upper, old, new) in &entry.substitutions {
            let found = m
                .substitution_table
                .iter()
                .find(|(u, o, n, _)| (*u, i64::from(*o), i64::from(*n)) == (upper, old, new));
            if let Some((_, _, _, Some(pairs))) = found {
                sub_keys.extend(pairs.iter().map(|&(from, _)| i64::from(from)));
            }
        }
        m.sub_keys = sub_keys;
        // One interpreter per event with some parallel page that compiles.
        // The ROM carries them in a fixed-cap list and **doesn't warn** if
        // it goes over, so the stop goes here.
        let with_parallel: BTreeSet<i64> = pages
            .iter()
            .filter(|p| p.trigger == engine::TRIGGER_PARALLEL as i64 && p.has_code)
            .map(|p| p.event)
            .collect();
        if with_parallel.len() > record::PARALLEL_MAX {
            crate::stop!(
                "map {} has {} events with a parallel page and {} fit: see PARALLEL_MAX",
                m.id,
                with_parallel.len(),
                record::PARALLEL_MAX
            );
        }
        if !with_parallel.is_empty() {
            println!(
                "  map {}: {} event(s) with a parallel page",
                m.id,
                with_parallel.len()
            );
        }
        // The graphics command 34 and `ChangeSpriteAssociation` carry by
        // index: the two passes have to have numbered them the same.
        let graphics = &entry.graphics;
        if *graphics != m.route_graphics {
            crate::stop!(
                "map {}: the two passes numbered the route graphics differently: {:?} against {:?}",
                m.id,
                graphics,
                m.route_graphics
            );
        }
        for (graphic, index) in &entry.graphics_dropped {
            println!(
                "  map {}: WARNING, a route changes to the graphic {graphic} {index} and the map's table does not have it —full at {}, or a page the scan did not get that far in—: the change is ignored",
                m.id,
                record::ROUTE_GFX_MAX
            );
        }
        m.pages = pages;
        // And the teleports to a map that didn't make it into the ROM: each is
        // compiled as a message box saying so (see `TELEPORT` in the events'
        // compile.rs), so the hole shows when played, and here.
        let mut outside_of = BTreeSet::new();
        let mut how_many = 0;
        for page in &m.pages {
            if !page.has_code || !triggers.contains(&page.trigger) || page.test {
                continue;
            }
            let event = &m.map.events[page.event as usize];
            for c in &event.pages[page.page as usize].commands {
                if c.code == TELEPORT
                    && !c.parameters.is_empty()
                    && !table_index.contains_key(&c.parameters[0])
                {
                    outside_of.insert(c.parameters[0]);
                    how_many += 1;
                }
            }
        }
        if !outside_of.is_empty() {
            println!(
                "  map {}: WARNING, {how_many} teleport(s) to a map that didn't make it into the ROM, each a message box instead: {}",
                m.id,
                join(&outside_of, ", ")
            );
        }
        // Debts are warned about: a page accepted without doing everything
        // it asks for is a difference from the original game.
        for &code in &entry.debts {
            let name = ditto::schema::EventCommandCode::from_i32(code)
                .json_name()
                .map_or_else(|| code.to_string(), str::to_string);
            println!(
                "  map {}: WARNING, a page uses {name} and the ROM doesn't do it; see ACCEPTED_UNDONE in rm2k-snes/events",
                m.id
            );
        }
    }

    // The second round: with the pages of all the cases compiled, they are
    // put in the boot map and each map's block is built.
    let boot = order[start_index];
    // Where the hero is flashed, by the map's index, and the map whose page
    // does it: checked once every map is known.
    let mut flashes: BTreeMap<(usize, Option<(String, i64)>, bool), i32> = BTreeMap::new();
    // The maps whose copy of the common events is not kept, and why: see
    // below, before each map's code is laid out.
    let mut copies_pushing: Vec<i32> = Vec::new();
    let mut copies_drawing_nothing: Vec<i32> = Vec::new();
    for m in infos.iter_mut() {
        if !cases.is_empty() && m.id == boot {
            // The test pages, only in the map the ROM boots in, at **index
            // 0** —the empty event put first—: the ROM walks the events from
            // lowest to highest, and they run before the game's. **One page
            // per case**, and page k asks for `CASE_VARIABLE` to be at least
            // k; and one that turns it off, which asks for `TEST_SWITCH` and
            // has no code.
            for (k, code) in test_code.iter().enumerate() {
                let variable = if k > 0 {
                    let slot = variable_slot(&indices, CASE_VARIABLE as i64)?;
                    Some((slot, COMPARE_AT_LEAST.into(), k as i64))
                } else {
                    None
                };
                m.pages.push(test_page(k as i64, 0, variable, code.clone()));
            }
            m.pages.push(test_page(
                cases.len() as i64,
                compiler.test_switch,
                None,
                Vec::new(),
            ));
        }
        // The copy of the automatic common events stays only where it draws
        // and its map's bytecode still goes to WRAM: see
        // [`lay_out_with_copy`].
        let copy = common_pages
            .maps
            .contains(&m.id)
            .then(|| (m.map.events.len() as i64 - 1, m.copies_draw));
        let behind = |code: usize| {
            rm2k_snes_mapdata::materials::code_behind_grid(
                m.cells.len() / 2,
                m.blocks.len() / rm2k_snes_mapdata::materials::BLOCK_BYTES,
                m.blocks.len() + m.block_pass.len(),
                code,
            )
        };
        let (code, dropped) = lay_out_with_copy(&mut m.pages, copy, behind);
        match dropped {
            None => {}
            Some(CopyDropped::DrawsNothing) => copies_drawing_nothing.push(m.id),
            Some(CopyDropped::Pushes { with, without }) => {
                let line = format!(
                    "  map {}: WARNING, the copy of the common events {} isn't kept here: with it \
                     the map's bytecode, {with} bytes, would not decompress into WRAM, and \
                     without it it is {without}; their shared bodies run, and their small \
                     pictures are drawn only if the cartridge's set of them fits beside the map's",
                    m.id,
                    join(&common_pages.commons, ", "),
                );
                println!("{line}");
                degradations.map(m.id as i64, "pictures-not-drawn", &line, &[]);
                copies_pushing.push(m.id);
            }
        }
        if dropped.is_some() {
            common_pages.maps.remove(&m.id);
        }
        // What each page of the events that change graphic draws: where
        // its poses are in the sprite bank —`page_oam` in the emission—.
        for page in m.pages.iter_mut() {
            let continues = m.changing.contains(&page.event);
            if !continues && !m.appearing.contains(&page.event) {
                continue;
            }
            let Some(graphic) = &page.graphic else {
                continue;
            };
            if m.outside
                .get(&page.event)
                .is_some_and(|o| o.contains(&(graphic.0.clone(), graphic.1)))
            {
                continue;
            }
            // What it draws wherever it is drawn: the pose it shows, and the
            // passage its tile imposes.
            let drawn = request::Draws {
                block: None,
                key: None,
                palette: 0,
                posed: None,
                pose: graphic.2 as u32,
                tile_pass: page.tile_pass.map(|t| t as u32),
                translucent: page.translucent,
            };
            // Drawn into the background: the page carries its number among
            // them and which of its characters, and the console writes its
            // cell. See `posed` in Wally.
            if let Some((p, graphics)) = m.posed.get(&page.event) {
                let g = graphics
                    .iter()
                    .position(|(c, i)| *c == graphic.0 && *i == graphic.1)
                    .ok_or_else(|| {
                        Stop::new(format!(
                            "map {}: {graphic:?} is not among event {}'s poses in the background",
                            m.id, page.event
                        ))
                    })?;
                page.draws = Some(request::Draws {
                    posed: Some([*p as u32, g as u32]),
                    ..drawn
                });
                continue;
            }
            let (mut block, mut palette) = (None, 0);
            // A map with a cache of slots: the page carries its still pose,
            // and the console finds it a slot. See `sprites::cache` in Wally.
            if continues && !m.cached.is_empty() {
                let (key, p) = m.cached.get(graphic).cloned().ok_or_else(|| {
                    Stop::new(format!("map {}: {graphic:?} is not in the cache", m.id))
                })?;
                page.draws = Some(request::Draws {
                    key: Some(key),
                    palette: p,
                    ..drawn
                });
                continue;
            }
            if continues {
                // The one that only appears goes without a block: its own
                // row points at its slot of twelve poses.
                let (b, p) = match m.shared.get(&page.event) {
                    Some(&shared) => shared,
                    None => m
                        .where_
                        .get(graphic)
                        .map(|&(block, palette)| (Some(block), palette))
                        .ok_or_else(|| {
                            Stop::new(format!(
                                "map {}: {graphic:?} is not in the sprite bank",
                                m.id
                            ))
                        })?,
                };
                block = b;
                palette = p;
            }
            page.draws = Some(request::Draws {
                block,
                palette,
                ..drawn
            });
        }
        m.evcode = code;
        // The ROM's substitution table has a fixed cap and **doesn't warn**
        // if it goes over.
        if m.sub_keys.len() > SUB_MAX {
            crate::stop!(
                "map {} substitutes {} distinct blocks and the RAM table carries {SUB_MAX}: see SUB_MAX",
                m.id,
                m.sub_keys.len()
            );
        }
        // How many distinct events this map can end up sending walking: a
        // route that finds no room is discarded **without saying
        // anything**. The pages that **run** here: the map's and those of
        // the cases that jump to it.
        let mut run_here: Vec<&[u8]> = m
            .pages
            .iter()
            .filter(|p| p.has_code && !p.test)
            .map(|p| p.code.as_slice())
            .collect();
        for (k, (_, _, run_map)) in cases.iter().enumerate() {
            if *run_map == m.id {
                run_here.push(&test_code[k]);
            }
        }
        let mut targets = BTreeSet::new();
        for code in &run_here {
            for i in bytecode::walk(code)? {
                if code[i] == OP_ROUTE && bytecode::at(code, i + 1) != 0 {
                    targets.insert(code[i + 1]);
                }
            }
        }
        // And that nobody flashes someone who shares a graphic with another:
        // on the console the flash is done on the character's palette, so
        // two that share a graphic would flash together. This covers what
        // the compiler can't see, which is the hero's: which graphic it has
        // depends on the party.
        //
        // **A flash runs on the map the page is on when it reaches it**: one
        // after a `Teleport` is the destination's, so it is noted for that
        // map and checked after the loop against its NPCs (a common event
        // pasted into a page flashes the hero after teleporting, which is
        // what the Frozen World's refusal on maps 1 and 3 was). The walk is
        // in bytecode order and does not follow jumps: a teleport on one
        // branch counts for what comes after it in the text.
        //
        // **And the graphic the hero has then is the last one a route on the
        // hero gave it**, not the actor's: `OP_ROUTE`'s path carries command
        // 34 followed by the index in the map's route graphics. Frozen World's
        // common event 3 teleports, gives the hero `rangedmelee[7]` and flashes.
        let here = table_index[&m.id];
        for code in &run_here {
            for flash in hero_flashes(code, here, &m.route_graphics)? {
                flashes.entry(flash).or_insert(m.id);
            }
        }
        // More than that is not lost while they do not all move at once:
        // a slot whose route ended goes to the next one —`reclaim_slot` in
        // the runtime—. How many move at once the pages do not say.
        if targets.len() > record::ROUTE_EV_MAX {
            let line = format!(
                "  map {}: WARNING, its pages send {} distinct events walking and the ROM has {} route \
                 slots: one whose route ended gives its slot to the next, and a route that finds them \
                 all moving is lost",
                m.id,
                targets.len(),
                record::ROUTE_EV_MAX
            );
            println!("{line}");
            degradations.map(m.id as i64, "route-slots-short", &line, &[]);
        }
        // A map RM2k loops on an axis the console cannot: see `wrap_axes`.
        for why in emit::wrap_axes(m).1 {
            let line = format!("  map {}: WARNING, {why}: its edges are walls", m.id);
            println!("{line}");
            degradations.map(m.id as i64, "map-does-not-wrap", &line, &[]);
        }
        let runnable = m.pages.iter().filter(|p| p.has_code).count();
        if !m.pages.is_empty() {
            println!(
                "  map {}: {} automatic event page(s), {} runnable",
                m.id,
                m.pages.len(),
                runnable
            );
        }
    }
    if !copies_drawing_nothing.is_empty() || !copies_pushing.is_empty() {
        println!(
            "  the copy of the common events is kept in {} maps: {} draw nothing with it, {} \
             would keep their bytecode in the cartridge",
            common_pages.maps.len(),
            copies_drawing_nothing.len(),
            copies_pushing.len()
        );
    }

    let mut shared_flashes: Vec<String> = Vec::new();
    for ((index, given, away), &from) in &flashes {
        let m = &infos[*index];
        let mut graphics: BTreeMap<(String, i64), usize> = BTreeMap::new();
        for row in &m.npcs {
            *graphics
                .entry((row.npc.charset.clone(), i64::from(row.npc.index)))
                .or_insert(0) += 1;
        }
        // The graphic a route gave the hero, or each leader's own: the flash
        // is on its palette, which an NPC drawn with the same one shares.
        let mut heroes: Vec<(String, i64, String)> = Vec::new();
        match given {
            Some((name, i)) => heroes.push((name.clone(), *i, "the hero".to_string())),
            None => {
                for actor in &leaders {
                    let a = game.db.actor(*actor)?;
                    heroes.push((
                        a.character_name.clone(),
                        a.character_index as i64,
                        format!("actor {actor}"),
                    ));
                }
            }
        }
        for (name, i, who) in heroes {
            if graphics.get(&(name.clone(), i)).copied().unwrap_or(0) > 0 {
                // A flash on the map the page is on stops the build, as it
                // always did. One after a `Teleport` is the destination's: it
                // is warned about and not refused, since checking it stopped
                // ABL (map 32's pages flashing the hero on 33) and Frozen
                // World, whose pages now compile. It is a cosmetic double
                // flash, not a broken page.
                let line = format!(
                    "map {}: a page (of map {from}) makes the hero flash there, and {who} is drawn with {name}[{i}], \
                     which an NPC of the map also uses. On the console they share a palette and \
                     both would flash",
                    m.id
                );
                if *away {
                    println!("  WARNING, {line}");
                    degradations.map(m.id as i64, "flash-shared-palette", &line, &[]);
                } else {
                    shared_flashes.push(line);
                }
            }
        }
    }
    if !shared_flashes.is_empty() {
        crate::stop!("{}", shared_flashes.join("\n"));
    }

    // The screens, all at once. And the items that can be in the
    // inventory, to carry their name and their description; the ones the
    // enemies of the cartridge's troops drop too.
    let items_rom = scan::possible_items(
        every_refs.iter().copied(),
        &members,
        &game.db,
        &file_commands,
    );
    let mut items_all: BTreeSet<i32> = items_rom.iter().copied().collect();
    items_all.extend(scan::drop_items(&game.db, &troops.ids));
    let items_all: Vec<i32> = items_all.into_iter().collect();
    let font = FontChoice::of(&settings)?;
    let menu_before: serde_json::Map<String, Value> = compiled
        .commons
        .iter()
        .flat_map(|c| &c.menu_before)
        .map(|(n, body)| (n.to_string(), json!(body)))
        .collect();
    let menus_request = json!({
        "menus": custom_menus.iter().map(|m| json!({"name": m.name, "spec": m.spec})).collect::<Vec<_>>(),
        "variables": indices.variables.iter().map(|(v, s)| json!([v, s])).collect::<Vec<_>>(),
        "before_bodies": menu_before,
        // And the names `ChangeHeroName` gives: one more row each of the
        // actors' text.
        "names": indices.names.iter().map(|(a, n)| json!([a, n])).collect::<Vec<_>>(),
        // And the debug screen, which shows every variable by its slot.
        "debug": options.debug_screen,
    });
    // The battle terms the project gives over the database's, if any: a
    // knob at rest when missing. See `battle_term` in the mapdata stage.
    let battle_terms = settings.battle_terms()?;
    let renames: Vec<String> = indices.names.iter().map(|(_, n)| n.clone()).collect();
    let screen_letters =
        crate::letters::screen_letters(&game.dump, &font.font, &battle_terms, &renames)?;
    let screens_answer = screens::convert(
        &game,
        &font,
        &members,
        &items_all,
        !options.no_title,
        &menus_request,
        window_colors,
        window_answer.text_rows.as_ref(),
        &json!(compiled.messages.letters),
        &screen_letters,
    )?;
    for loss in &screens_answer.losses {
        degradations.cartridge(&loss.kind, &loss.text);
    }
    let w = &screens_answer.window;
    println!(
        "  message window: {} fixed tiles + {} of text, {} colors; font {} B, {} text box(es) in {} B",
        w.system.tiles.len() / 32,
        w.system.background.len() / 32,
        window_colors,
        w.font.len(),
        message_count,
        messages.len()
    );
    for line in &screens_answer.says {
        println!("{line}");
    }
    vram::check_splits().map_err(|e| Stop::new(e.message().to_string()))?;
    let s = &screens_answer.slots;
    let slot_tiles = s.tiles.len();
    let headers = &s.headers;
    let faces: Vec<&i32> = s.faces.keys().collect();
    let face_names: Vec<String> = faces
        .iter()
        .map(|a| {
            format!(
                "{a} {}",
                game.db.actors.get(a).map_or("", |x| x.name.as_str())
            )
        })
        .collect();
    println!(
        "  slots screen: {}, {} 4bpp tiles ({} B) + {} palettes, {} B of cells; {} actors with a face: {}",
        vram::SLOTS,
        slot_tiles,
        slot_tiles * 32,
        s.palettes.len(),
        // Only the headers': the slots' rows were never counted, see the
        // draft `the-slots-screen-line-counts-no-row-cells`.
        headers.len() * headers.first().map_or(0, Vec::len) * 2,
        faces.len(),
        if face_names.is_empty() { "none".to_string() } else { face_names.join(", ") }
    );
    let mut title_screen = None;
    if let Some(t) = &screens_answer.title {
        let name = &game.db.title_name;
        // The game's, or the RTP's, in any case; where it was looked for
        // when there is none.
        let picture = crate::resources::find(&[&game.game_dir, &rtp_dir], "Title", name, &[".png"])
            .unwrap_or_else(|| game.game_dir.join("Title").join(format!("{name}.png")));
        let texts = &t.texts;
        let menu_tiles = t.tiles.len();
        let menu_palette = t.palette.clone();
        let menu_maps = t.tilemaps.len();
        // The image, compressed like the Game Over one, and with the menu's
        // colours below its own in the same stream: the whole CGRAM at
        // once, the menu's palette at the bottom because a 4-bit BG only
        // reaches those.
        let mut below = menu_palette.clone();
        while (below.len() as i64) < fullscreen::MENU_CGRAM {
            below.push([0, 0, 0]);
        }
        let screen =
            fullscreen::compressed(&picture, fullscreen::MENU_CGRAM, fullscreen::COLORS, &below)?;
        println!(
            "  title screen {}: {} 8bpp tiles + {} colors, {} B in an LZ2 stream of {} B",
            quoted(name),
            screen.tiles,
            screen.colors - below.len(),
            screen.raw,
            screen.stream.len()
        );
        println!(
            "    menu ({}): {} 4bpp tiles ({} B) + {} colors, {} tilemap(s)",
            texts
                .iter()
                .map(|t| quoted(t))
                .collect::<Vec<_>>()
                .join(", "),
            menu_tiles,
            menu_tiles * 32,
            menu_palette.len(),
            menu_maps
        );
        // The image's tiles go below the menu's tilemap, and the menu's end
        // before the image's tilemap: the limits `title.s` asserts. An image
        // that does not fit at eight bits goes at four, in mode 1, where it
        // always fits —see `compressed_4bpp`—, and what it loses is what
        // Adeleine decides, in the build's `adeleine/title.png`. A menu that
        // does not fit starts the game without a title, as `--no-title`
        // does, and says so: the assembler would stop on it instead.
        if menu_tiles > TITLE_MENU_TILES_MAX {
            let line = format!(
                "  WARNING, the title menu doesn't fit in VRAM ({menu_tiles} tiles of {TITLE_MENU_TILES_MAX}): the game starts without a title screen"
            );
            println!("{line}");
            degradations.cartridge("title-screen-not-drawn", &line);
        } else if screen.tiles <= TITLE_TILES_MAX && !options.title_4bpp {
            title_screen = Some(screen);
        } else {
            let (four, png) = fullscreen::compressed_4bpp(&picture, &menu_palette)?;
            println!(
                "    {}: at 4bpp in mode 1, {} tiles + {} palette(s), {} B in an LZ2 stream of {} B",
                if options.title_4bpp {
                    "--title-4bpp".to_string()
                } else {
                    format!("{} 8bpp tiles don't fit in {TITLE_TILES_MAX}", screen.tiles)
                },
                four.tiles,
                (four.colors as i64 - fullscreen::MENU_CGRAM) / 16,
                four.raw,
                four.stream.len()
            );
            let dir = output
                .parent()
                .map(rm2k_project::absolute)
                .unwrap_or_default()
                .join("adeleine");
            std::fs::create_dir_all(&dir).map_err(|e| crate::fail::io(&dir, e))?;
            let path = dir.join("title.png");
            std::fs::write(&path, png).map_err(|e| crate::fail::io(&path, e))?;
            title_screen = Some(four);
        }
    }
    // The Game Over screen: the image the LDB's `System` names, in the
    // game's or the RTP's `GameOver/` —as RM2k looks for it—, compressed.
    let mut game_over = None;
    let gameover_name = &game.db.gameover_name;
    let path = crate::resources::find(
        &[&game.game_dir, &rtp_dir],
        "GameOver",
        gameover_name,
        &[".png", ".bmp"],
    );
    if let (false, Some(path)) = (gameover_name.is_empty(), path) {
        let screen = fullscreen::compressed(&path, 0, 256, &[])?;
        println!(
            "  Game Over screen {}: {} 8bpp tiles + {} colors, {} B in an LZ2 stream of {} B",
            quoted(&path.file_name().unwrap().to_string_lossy()),
            screen.tiles,
            screen.colors,
            screen.raw,
            screen.stream.len()
        );
        game_over = Some(screen);
    }
    // Whether the cartridge needs the MSU-1, and if it does, the screen
    // that says so when it is not there.
    let msu_data = if options.msu_everything {
        request::MsuData::Everything
    } else {
        settings.msu()?
    };
    let mut msu_missing = None;
    if msu_data != request::MsuData::Optional {
        let png = output
            .parent()
            .map(rm2k_project::absolute)
            .unwrap_or_default()
            .join("sin-msu.png");
        let screen = crate::msu_missing::screen(&font.font, &png)?;
        println!(
            "  the cartridge needs the MSU-1 ({}); the screen that says so when it is missing: \
             {} 8bpp tiles + {} colors, an LZ2 stream of {} B",
            msu_data.name(),
            screen.tiles,
            screen.colors,
            screen.stream.len()
        );
        msu_missing = Some(screen);
    }
    // The battle animations the already emitted bytecode shows: their
    // prerendered frames go to the cartridge.
    let shown = animations::shown(
        infos
            .iter()
            .flat_map(|m| m.pages.iter().map(|p| p.code.as_slice())),
    )?;
    let shown: Vec<i32> = shown.into_iter().collect();
    let animations: BTreeMap<i32, animations::Info> = animation_cache
        .by_numbers(&game, &shown)?
        .into_iter()
        .filter_map(|(n, info)| info.map(|i| (n, i)))
        .collect();
    for (number, info) in &animations {
        let r = animations::report(info);
        println!(
            "  animation {number}: {} frames of {}x{}, shrunk from {}x{} to {}%, {} colors, {} B",
            r.frames, r.size.0, r.size.1, r.original.0, r.original.1, r.percent, r.colors, r.bytes
        );
    }
    // The backdrops and the battlers the cartridge's battles ask for,
    // each one once.
    let scenes = scene::rom_scene(
        &game,
        &settings,
        &rtp_dir,
        &troops,
        &infos,
        &encounters.per_map,
    )?;
    for b in &scenes.backdrops {
        let (rom_tiles, rom_colors) = scene::fallback_bytes(&b.light);
        let (msu_tiles, msu_colors) = &scenes.quality[b.number];
        println!(
            "  battle backdrop {} {}: {}x{}, {} tiles from CGRAM entry {}; in the ROM {}x{} at 4bpp and {} colors ({} B), in the .msu 8bpp and {} colors ({} B)",
            b.number,
            quoted(&b.name),
            scene::WIDTH,
            scene::HEIGHT,
            scene::TILES,
            scene::CGRAM_BASE,
            scene::FALLBACK_WIDTH,
            scene::FALLBACK_HEIGHT,
            b.light.palette.len(),
            rom_tiles.len() + rom_colors.len(),
            scene::COLORS,
            msu_tiles.len() + msu_colors.len()
        );
    }
    let in_rom: BTreeSet<usize> = scenes.backdrops.iter().map(|b| b.number).collect();
    let outside: Vec<usize> = (0..scenes.game.len())
        .filter(|k| !in_rom.contains(k))
        .collect();
    if !outside.is_empty() && !scenes.backdrops.is_empty() {
        let line = format!(
            "  battle backdrops only in the .msu, which without MSU-1 fall back to {}: {}",
            quoted(&scenes.backdrops[scenes.fallback_of[outside[0]]].name),
            outside
                .iter()
                .map(|k| format!("{k} {}", scenes.game[*k]))
                .collect::<Vec<_>>()
                .join(", ")
        );
        println!("{line}");
        degradations.cartridge("backdrop-only-in-msu", &line);
    }
    for b in &scenes.battlers {
        println!("{}", scene::battler_report(b));
    }
    // The event pages of the troops some battle of the cartridge asks for.
    let tp = &compiled.troop_pages;
    println!(
        "  troop pages: {} of {} in {} distinct body(ies), {} B of code and {} B in {} message(s)",
        tp.pages - tp.left_out,
        tp.pages,
        tp.distinct,
        tp.code.0.len(),
        tp.messages.0.len(),
        tp.message_count
    );
    // And their debts, as the maps' automatic pages': one line per command,
    // with the troops, because the game copies its systems' pages into every
    // troop and one line per troop would be the warning nobody reads.
    for (code, pages) in &tp.debts {
        let name = ditto::schema::EventCommandCode::from_i32(*code)
            .json_name()
            .map_or_else(|| code.to_string(), str::to_string);
        let troops: BTreeSet<i32> = pages.iter().map(|(troop, _)| *troop).collect();
        println!(
            "  troop pages: WARNING, {} page(s) of {} troop(s) use {name} and the ROM doesn't do it; \
             see ACCEPTED_UNDONE in rm2k-snes/events. Troops: {}",
            pages.len(),
            troops.len(),
            join(troops, ", ")
        );
    }
    // The battle's model, `rm2k-snes-battle`'s second call.
    let mut pairs = indices.skills.clone();
    pairs.sort_by_key(|(_, _, slot)| *slot);
    let request = rm2k_snes_battle::model::ModelRequest {
        actors: members.clone(),
        troops: troops.ids.clone(),
        items: items_all.clone(),
        skill_pairs: pairs
            .iter()
            .map(|&(a, h, _)| (a as i32, h as i32))
            .collect(),
        item_name_width: rm2k_snes_screens::layout::ITEM_NAME_WIDTH,
        // The letters the text screens carry: an item's name in a
        // victory line keeps them.
        letters: Some(screens_answer.font.screen_letters.clone()),
        font: Some(font.spec.clone()),
        letter_spacing: Some(font.spacing),
        exfont: font
            .exfont
            .as_ref()
            .map(|sheet| sheet.to_string_lossy().into_owned()),
    };
    let written = stage::call(
        BATTLE_MODEL,
        &json!(request),
        &["--data".into(), game.dump.clone().into_os_string()],
        || rm2k_snes_battle::stage::model(&game.dump, &request),
    )?;
    let battle_model: rm2k_snes_battle::model::Model = stage::typed(&written, "model.json")?;
    for place in battle_model.cut.iter().flatten() {
        let line = cut_report(place);
        println!("{line}");
        degradations.cartridge("names-cut", &line);
    }
    // The party's line, whose HP and SP the console writes as runs that do
    // not get cut: with a font too wide they would step on each other.
    if let Some(why) = &battle_model.party_line {
        let line = format!("  WARNING, battle text: the party's line does not fit: {why}");
        println!("{line}");
        degradations.cartridge("names-cut", &line);
    }
    // What the battle's busiest lists ask of the text layer's pool. The
    // console does not stop when it runs out —it shows what it has typeset
    // and goes on (`TL_FLUSH`)—, but what does not get a pair does not show,
    // so it is a warning. The battle's pool is not the shop's: its pairs go
    // from word 0 up to the battle's windows —`TL_POOL_BATTLE` in the
    // runtime's `screen_bank.s`, and `TEXT_PAIRS_END`—.
    let pool = scene::TEXT_PAIRS_END / 32 - 1;
    if let Some(asked) = &battle_model.pairs {
        let (skills, items) = (asked.skills as i64, asked.items as i64);
        let warning = if skills.max(items) > pool {
            "WARNING, "
        } else {
            ""
        };
        let line = format!(
            "  {warning}battle text: the skill list asks for {skills} pairs of tiles at most \
             (actor {}, who can know {} skills) and the item list {items}, of the {pool} of \
             the pool",
            asked.skills_actor, asked.skills_known
        );
        println!("{line}");
        if skills.max(items) > pool {
            degradations.cartridge("text-pool-short", &line);
        }
    }
    // The parallel common events, which the ROM runs every frame while their
    // switch is on: the ones that compile, and a line for those that do not.
    let mut parallel_common = Vec::new();
    let mut parallel_left_out = Vec::new();
    for (number, switch, pure, code) in &compiled.parallel_commons {
        match code {
            Some(code) => parallel_common.push((
                i64::from(*switch),
                i64::from(*number),
                *pure,
                crate::text::hex(&code.0),
            )),
            None => parallel_left_out.push(*number),
        }
    }
    if !parallel_common.is_empty() || !parallel_left_out.is_empty() {
        println!(
            "  parallel common events: {} run, {} do not compile {parallel_left_out:?}",
            parallel_common.len(),
            parallel_left_out.len()
        );
    }
    let case_slot = if cases.len() > 1 {
        Some(variable_slot(&indices, CASE_VARIABLE as i64)?)
    } else {
        None
    };
    // The shared bodies, with the copies of the automatic ones by map index:
    // see [`crate::common_pages`].
    let commons = compiled.commons.as_ref().map(|c| request::Commons {
        bodies: c
            .bodies
            .iter()
            .map(|(n, code)| (i64::from(*n), crate::text::hex(&code.0)))
            .collect(),
        autostart: c
            .autostart
            .iter()
            .map(|&(s, b)| (i64::from(s), i64::from(b)))
            .collect(),
        depth: c.depth.map(|d| d as i64),
        copies: if common_pages.maps.is_empty() {
            request::Copies::default()
        } else {
            request::Copies {
                commons: common_pages.commons.iter().map(|&n| n.into()).collect(),
                maps: order
                    .iter()
                    .enumerate()
                    .filter(|(_, m)| common_pages.maps.contains(m))
                    .map(|(k, _)| k as i64)
                    .collect(),
            }
        },
    });
    // The maps whose pages open an inn's gold window, `OP_INN 3`: the
    // emission says which of them have no room for it in the sprites. See
    // `arrow_obj` in rm2k-snes-mapdata and the runtime's gold_window.s.
    let mut gold_maps = Vec::new();
    for m in &infos {
        let mut wants = false;
        for page in &m.pages {
            let code = page.code.as_slice();
            for i in bytecode::walk(code)? {
                wants |= code[i] == OP_INN && bytecode::at(code, i + 1) == INN_GOLD_WINDOW;
            }
        }
        if wants {
            gold_maps.push(m.id as i64);
        }
    }
    // And the faces the message window shows, in the order `OP_FACE` counts
    // them, drawn by the screens. One whose FaceSet is nowhere comes as the
    // window's own background —blank, the text still moves over for it—
    // and is a degradation: the page runs, the face is what is lost.
    let faces = screens::faces(&game, &indices.faces)?;
    let mut missing = 0;
    for (drawn, (name, index, _)) in faces.iter().zip(&indices.faces) {
        if drawn.missing {
            missing += 1;
            degradations.cartridge(
                "face-missing",
                &format!("FaceSet {name:?} is neither in the game nor in the RTP: its face {index} shows blank in the message window"),
            );
        }
    }
    if !faces.is_empty() {
        println!(
            "  message faces: {}, {} B ({} with a missing FaceSet)",
            faces.len(),
            faces.len() * rm2k_snes_mapdata::emit::MESSAGE_FACE_BYTES,
            missing
        );
    }
    let request = request::Emit {
        maps: infos
            .iter()
            .map(|m| emit::map_record(m, emit::access_bits(game.tree.rules.access(m.id))))
            .collect::<Result<_>>()?,
        start: start_index as i64,
        hero_above: options.hero_above,
        speed_keys: !options.no_speed_keys,
        enemy_hp: options.enemy_hp,
        // Whether Select walks the hero through everything, for debugging.
        phasing: options.phasing,
        // Whether the ROM leaves the vblank's last line in RAM, for a test.
        vblank_probe: options.vblank_probe,
        // Whether some `Teleport` asks for a facing, which the runtime
        // assembles only then: see `scan::teleports_with_a_facing`.
        teleport_facing: scan::teleports_with_a_facing(
            every_refs.iter().copied(),
            &game.db.common_events,
            &file_commands,
        ),
        // Whether some `MessageOptions` takes the window's background away,
        // which bakes the maps' layers above for it: see
        // `scan::transparent_messages`.
        transparent_messages: scan::transparent_messages(
            every_refs.iter().copied(),
            &game.db.common_events,
            &file_commands,
        ),
        // How many windows the game's `ShowWindow`s name, which the runtime
        // keeps a slot for each: see `scan::window_slots`.
        window_slots: scan::window_slots(
            every_refs.iter().copied(),
            &game.db.common_events,
            &file_commands,
        ),
        party: party.iter().map(|&a| a.into()).collect(),
        // What the ROM says about itself, from the `[rom]` of the project
        // file: the header title and the save signature in SRAM.
        rom: request::Rom {
            title: settings.ascii(&["rom", "title"], None, Some(TITLE_HEADER))?,
            sram_signature: settings.ascii(&["rom", "sram_signature"], Some(4), None)?,
            msu: msu_data,
        },
        screens: screens_answer,
        window_colors,
        // The message window of every other System the cartridge switches
        // to, in its order: the starting one's is the screens'.
        window_systems: window_answer
            .systems
            .iter()
            .map(|s| s.other.clone())
            .collect(),
        messages,
        message_pairs: request::MessagePairs {
            first: compiled.messages.pair_first.into(),
            table: compiled.messages.pairs.0.clone(),
        },
        faces: faces
            .into_iter()
            .map(|f| request::MessageFace {
                tiles: f.tiles,
                palette: f.palette,
            })
            .collect(),
        title: title_screen.as_ref().map(fullscreen::Screen::request),
        game_over: game_over.as_ref().map(fullscreen::Screen::request),
        msu_missing: msu_missing.as_ref().map(fullscreen::Screen::request),
        animations: animations::request(&animations)?,
        troops: troops.ids.iter().map(|&t| t.into()).collect(),
        battle_audio: compiled.battle_audio.clone(),
        scene: scene::request(&scenes, &troops.ids, &game.db)?,
        battle_tables,
        troop_pages: Some(compiled.troop_pages.clone()),
        parallel_common,
        gold_maps,
        // The battle terms the project gives over the database's, if any: a
        // knob at rest when missing. See `battle_term` in the mapdata stage.
        battle_terms,
        commons,
        battle_model,
        // The compiler's indices: each variable's slot and each (actor,
        // skill) pair's bit; the highest switch the game names, which the
        // table holds; and the names `ChangeHeroName` gives, in the order
        // `OP_CHANGE_NAME` counts them.
        variables: indices.variables.clone(),
        skill_pairs: indices.skills.clone(),
        names: indices.names.clone(),
        switch_top: indices.switch_top,
        items: items_all.iter().map(|&i| i.into()).collect(),
        actors: members.iter().map(|&a| a.into()).collect(),
        text_padding: options.text_padding as usize,
        case_slot,
        // The switch the test pages turn on, which the cartridge says to the
        // harnesses.
        test_switch: (!cases.is_empty()).then_some(compiler.test_switch.into()),
        // The big pictures' layers, and which of them keep the small ones
        // over them: see `pictures::keep_objects`.
        big_pictures: big_layers
            .into_iter()
            .map(pictures::BigLayer::request)
            .collect(),
        // The common events' small pictures, by set: see
        // [`crate::common_pictures`].
        common_pictures: common_small.emit,
    };
    let emitted = emit::emit(&output, request, &game.dump)?;
    println!(
        "{} map(s) -> {}, boots at {start_index} (map {})",
        infos.len(),
        output.display(),
        infos[start_index].id
    );
    let directory = output
        .parent()
        .map(rm2k_project::absolute)
        .unwrap_or_default();
    // Wally's losses, map by map, and the emission's.
    for m in &infos {
        for (kind, text, events) in &m.losses {
            degradations.map(m.id as i64, kind, text, events);
        }
    }
    for loss in &emitted.losses {
        degradations.map(loss.map, &loss.kind, &loss.text, &[]);
    }
    // `degradations.json` is written after the music, below: the audio
    // stage is the last to decide what is lost.
    // What Adeleine decided, as images: to look at which colours were lost
    // and which palette each cell ended up in without building or running
    // the ROM.
    maps::write_adeleine(&directory.join("adeleine"), &infos)?;
    // And **what it decided to lose**, written down: which colour was
    // merged with which in each layer, at what size each battle animation
    // is drawn, and which fifteen colours each battler is reduced to. What
    // travels is the decision; the text it is written as is
    // `rm2k-snes-patches`'.
    let patches_request = rm2k_snes_patches::Request {
        maps: infos.iter().map(|m| m.patches.clone()).collect(),
        animations: animations
            .iter()
            .map(|(number, info)| {
                let r = animations::report(info);
                let anim = &game.db.animations[number];
                rm2k_snes_patches::AnimationDecision {
                    number: i64::from(*number),
                    name: anim.name.clone(),
                    sheet: anim.sheet.clone(),
                    side: animations::BOX,
                    size: [r.size.0, r.size.1],
                    original: [r.original.0, r.original.1],
                    frames: r.frames as i64,
                }
            })
            .collect(),
        battlers: scenes
            .battlers
            .iter()
            .map(|b| rm2k_snes_patches::BattlerDecision {
                key: b.key.clone(),
                image: b.image.clone(),
                hue: b.hue,
                width: b.width,
                height: b.height,
                colors: b.colors,
                palette: b.palette.iter().map(|c| c.map(i64::from)).collect(),
                merges: b.merges,
            })
            .collect(),
        // And the colours the message window lost, if its System did not
        // fit in one palette: one that fits writes nothing.
        windows: screens::window_losses(&window_answer),
    };
    // Not kept in the cache, as when it was a process: it is a few
    // kilobytes of text made from the request alone.
    const PATCHES: stage::Stage = stage::Stage {
        binary: "rm2k-snes-patches",
        command: "--request",
    };
    let patches = stage::call_uncached(PATCHES, || {
        Ok::<_, String>(rm2k_snes_patches::stage::patches(&patches_request))
    })?;
    for written in rm2k_snes_patches::put(&directory, &patches).map_err(Stop::new)? {
        println!("{}", rm2k_snes_patches::report(&written));
    }
    // And who asked for each one, which isn't versioned: what separates, in
    // the ROM that is played, what belongs to the game from what only
    // exists because of the suite.
    let uses = scene::patch_uses(&infos, &game)?;
    let uses_path = directory.join("patches").join("uses.json");
    std::fs::write(
        &uses_path,
        serde_json::to_string_pretty(&uses).expect("uses are JSON") + "\n",
    )
    .map_err(|e| crate::fail::io(&uses_path, e))?;
    if !emitted.report.is_empty() {
        println!("material compressed and shared between maps:");
        for line in &emitted.report {
            println!("{line}");
        }
    }
    // The music comes from here and not from a separate recipe: emitting
    // them together is the only thing that guarantees both describe the
    // same ROM. What each map's package carries, whether the boot fits and
    // the `.msu` are `rm2k-snes-audio cartridge`'s.
    let msu = options
        .msu
        .clone()
        .map(rm2k_project::absolute)
        .unwrap_or_else(|| directory.join("datos.msu"));
    let request = rm2k_snes_audio::stage::Request {
        songs: compiler::songs(&compiled.songs),
        maps: infos.iter().map(|m| i64::from(m.id)).collect(),
        start: start_index,
        title: title_screen.is_some(),
        game_over: game_over.is_some(),
        decompress_frames: emitted
            .frames
            .get(start_index)
            .copied()
            .ok_or_else(|| Stop::new("the emission answered no frames for the boot map"))?,
        measuring_headroom: options.measure_headroom,
        // The quality backdrops are the emission's bytes: the stage only
        // puts them in their place in the `.msu`.
        backdrops: scenes.quality.clone(),
        tree_nodes: game.tree.added_nodes.clone(),
        // Whether the samples may travel in the `.msu`, in a cartridge
        // that needs the MSU-1: see `Emit::msu_samples` in the stage.
        msu_samples: msu_data != request::MsuData::Optional,
    };
    let flags = rm2k_snes_audio::stage::Flags {
        place: rm2k_snes_audio::stage::Place {
            game_dir: environment.game()?.to_path_buf(),
            rtp_dir: Some(environment.rtp()?.to_path_buf()),
            project: Some(project.directory().to_path_buf()),
        },
        data: game.dump.clone(),
        soundfont: environment.soundfont()?.to_path_buf(),
        out: directory.clone(),
        msu: msu.clone(),
    };
    let rm2k_snes_audio::stage::Answer { mut files, losses } =
        stage::call_uncached(AUDIO_CARTRIDGE, || {
            rm2k_snes_audio::stage::cartridge(&flags, &request)
        })?;
    let blob = files
        .remove(rm2k_snes_audio::stage::MSU)
        .ok_or_else(|| Stop::new("rm2k-snes-audio cartridge answered no .msu"))?;
    for (name, bytes) in &files {
        let path = directory.join(name);
        std::fs::write(&path, bytes).map_err(|e| crate::fail::io(&path, e))?;
    }
    // Alongside and renamed, and not overwritten in place: an emulator may
    // have it open.
    let fresh = PathBuf::from(format!("{}.nuevo", msu.display()));
    std::fs::write(&fresh, &blob).map_err(|e| crate::fail::io(&fresh, e))?;
    std::fs::rename(&fresh, &msu).map_err(|e| crate::fail::io(&msu, e))?;
    // And what the music lost to fit in the ARAM —a package's songs that
    // its `PlayBGM` uploads, its sound effects left out—, which only the
    // stage knows because it runs after everything else. With it, the list
    // is complete, and it is written.
    for loss in &losses {
        match loss.map {
            Some(map) => degradations.map(map, loss.kind, &loss.text, &[]),
            None => degradations.cartridge(loss.kind, &loss.text),
        }
    }
    degradations.write(&directory)?;
    // The bank packing is not decided here: both files send everything to
    // RODATA, and `rm2k-snes-cartridges assemble` spreads it into banks.
    Ok(())
}

/// Where the pictures are looked for: the images of the ChipSets the
/// project adds go first, built now —see `chipsets`—, and then the suite's,
/// the game's and the RTP.
pub fn search_dirs(
    game: &Game,
    project: &Project,
    rtp_dir: &std::path::Path,
) -> Result<Vec<PathBuf>> {
    let mut dirs: Vec<PathBuf> = vec![
        rm2k_project::suite::root(),
        game.game_dir.clone(),
        rtp_dir.to_path_buf(),
    ];
    let built = project.build()?.join("patches-manual");
    crate::chipsets::build_images(game, &built, &dirs)?;
    dirs.insert(0, built);
    Ok(dirs)
}

/// A map's code block: each page's bytecode and, behind it, the commands of
/// its own route, one byte per command; each page notes down where its two
/// start.
///
/// **Two pages with the same bytes point at the same code**, and so do two
/// routes. It is safe because nothing the runtime does depends on where a
/// page is: its jumps are offsets from where it starts (see `op_if`), which
/// is also what lets `code_carry_before` move a running one to another
/// address; the block is never written; and what tells two pages apart
/// —the parallel's state, the refresh— is the page's place in the table,
/// `page_ofs`, never its pointer. A routine of the runtime that compared
/// code pointers to know which page is running would break this. Frozen
/// World's battle screen has 52 monster pages with the same code.
///
/// Only within a map: each map's block is its own stream, decompressed alone
/// behind the grid, so a page cannot point into another map's.
fn lay_out_code(pages: &mut [PageRecord]) -> Vec<u8> {
    let mut code = Vec::new();
    let mut placed: HashMap<Vec<u8>, usize> = HashMap::new();
    let mut place = |code: &mut Vec<u8>, bytes: Vec<u8>| -> usize {
        if bytes.is_empty() {
            return code.len();
        }
        *placed.entry(bytes).or_insert_with_key(|bytes| {
            code.extend_from_slice(bytes);
            code.len() - bytes.len()
        })
    };
    for page in pages.iter_mut() {
        page.offset = place(&mut code, page.code.clone());
        if let Some(own) = &page.own_route {
            page.route_offset = place(&mut code, own.commands.iter().map(|&c| c as u8).collect());
        }
    }
    code
}

/// Why a map's copy of the automatic common events is not kept: see
/// [`lay_out_with_copy`].
#[derive(Debug, PartialEq, Eq)]
enum CopyDropped {
    /// Wally put the map's own pictures in instead of the copy's.
    DrawsNothing,
    /// With it the map's bytecode, `with` bytes, would stay in the
    /// cartridge raw; without it, `without`, it goes to WRAM.
    Pushes { with: usize, without: usize },
}

/// A map's bytecode, laid out by [`lay_out_code`], and whether the copy of
/// the automatic common events stays in it. `copy` is the copy's event
/// —the map's last— and whether its pictures went in, on a map that
/// carries one; `behind` says whether a bytecode of so many bytes goes to
/// WRAM behind the map's grid —`code_behind_grid` in rm2k-snes-mapdata—.
///
/// The copy is kept only where it draws, and where it does not push the
/// bytecode into the cartridge raw, which would cost every byte of the
/// map's there —a copy can be most of it—. A map already past it without
/// the copy keeps it: the copy only adds its own bytes there. A copy not
/// kept leaves its event with no pages, last, so no index moves; the
/// caller takes the map off the copies, and the shared bodies start there
/// as on a map without room for the event. See [`crate::common_pages`].
fn lay_out_with_copy(
    pages: &mut Vec<PageRecord>,
    copy: Option<(i64, bool)>,
    behind: impl Fn(usize) -> bool,
) -> (Vec<u8>, Option<CopyDropped>) {
    let code = lay_out_code(pages);
    let Some((event, draws)) = copy else {
        return (code, None);
    };
    let mut without: Vec<PageRecord> = pages.iter().filter(|p| p.event != event).cloned().collect();
    let bare = lay_out_code(&mut without);
    let dropped = if !behind(code.len()) && behind(bare.len()) {
        Some(CopyDropped::Pushes {
            with: code.len(),
            without: bare.len(),
        })
    } else if !draws {
        Some(CopyDropped::DrawsNothing)
    } else {
        None
    };
    if dropped.is_none() {
        return (code, None);
    }
    *pages = without;
    (bare, dropped)
}

/// The header title of a SNES ROM: 21 bytes, at `$FFC0`.
const TITLE_HEADER: usize = 21;

/// A test page of the boot map's event 0.
fn test_page(
    k: i64,
    switch_a: i32,
    variable: Option<(i64, i64, i64)>,
    code: Vec<u8>,
) -> PageRecord {
    PageRecord {
        event: 0,
        page: k,
        trigger: engine::TRIGGER_AUTOSTART as i64,
        switch_a,
        switch_b: 0,
        actor: 0,
        variable,
        item: 0,
        layer: 0,
        frequency: engine::ROUTE_FREQUENCY as i32,
        speed: 4,
        has_code: !code.is_empty(),
        code,
        own_route: None,
        graphic: None,
        tile_pass: None,
        turns: false,
        fixed_direction: false,
        fixed_graphic: false,
        translucent: false,
        test: true,
        pure: false,
        offset: 0,
        route_offset: 0,
        draws: None,
    }
}

/// One place of the battle that cuts names, as `rm2k-snes-battle`'s model
/// says it —`{"place", "cells", "names": [[name, pixels, shown]]}`—, in
/// the words of the screens' own: see `cut_names` in `rm2k-snes-screens`.
/// A warning: the console cuts and the battle goes on.
fn cut_report(place: &rm2k_snes_battle::model::Cut) -> String {
    let cells = place.cells;
    let names: Vec<String> = place
        .names
        .iter()
        .map(|(name, px, shows)| format!("{name:?} {px} px, shows {shows:?}"))
        .collect();
    format!(
        "  WARNING, {} {} don't fit in {cells} cells ({} px) and are cut: {}",
        names.len(),
        place.place,
        8 * cells,
        names.join("; ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use rm2k_snes_events::answer::OwnRoute;

    /// The cap is written on both sides, and has to be: the ROM **cannot
    /// warn** that it was exceeded, so the one that refuses a map that does
    /// not fit is the converter. One cannot be generated from the other
    /// —the BSS `.res` and the converter's cutoff share nothing—, so they
    /// are compared; and the table is two words per pair, keys and values in
    /// parallel arrays, which is how `cell_replaced` walks them.
    #[test]
    fn the_substitution_table_cap_is_the_runtime_s() {
        let path = rm2k_project::suite::runtime().join("low_ram.s");
        let source = std::fs::read_to_string(&path).unwrap();
        let line = |prefix: &str| {
            source
                .lines()
                .find(|l| l.starts_with(prefix))
                .unwrap_or_else(|| panic!("{} no longer says {prefix}", path.display()))
                .to_string()
        };
        assert_eq!(
            line("SUB_MAX ").split('=').nth(1).unwrap().trim(),
            SUB_MAX.to_string()
        );
        assert!(line("sub_key:").contains(".res SUB_MAX * 2"));
        assert!(line("sub_value:").contains(".res SUB_MAX * 2"));
    }

    /// The call stack's depth is written on both sides for the same reason:
    /// the ROM skips a call past it without saying, and the compiler is the
    /// one that says which chains go past it, in the degradations. The
    /// runtime declares the stack with it —`.res CALL_LEVELS * CALL_ENTRY`—
    /// and the compiler reports against `CALL_LEVELS` of the bytecode
    /// crate.
    #[test]
    fn the_call_stack_s_depth_is_the_runtime_s() {
        let path = rm2k_project::suite::runtime().join("common_events.s");
        let source = std::fs::read_to_string(&path).unwrap();
        let line = source
            .lines()
            .find(|l| l.starts_with("CALL_LEVELS "))
            .unwrap_or_else(|| panic!("{} no longer says CALL_LEVELS", path.display()));
        assert_eq!(
            line.split('=').nth(1).unwrap().trim(),
            rm2k_snes_bytecode::events::CALL_LEVELS.to_string()
        );
        assert!(source.contains("call_stack: .res CALL_LEVELS * CALL_ENTRY"));
    }

    #[test]
    fn identical_pages_and_routes_are_stored_once() {
        let mut pages = vec![
            test_page(0, 0, None, vec![1, 2, 3]),
            test_page(1, 0, None, vec![4, 5]),
            test_page(2, 0, None, vec![1, 2, 3]),
            test_page(3, 0, None, Vec::new()),
        ];
        pages[1].own_route = Some(OwnRoute {
            commands: vec![7, 8],
            ..Default::default()
        });
        pages[2].own_route = Some(OwnRoute {
            commands: vec![7, 8],
            ..Default::default()
        });
        pages[3].own_route = Some(OwnRoute {
            commands: vec![4, 5],
            ..Default::default()
        });
        let code = lay_out_code(&mut pages);
        assert_eq!(code, [1, 2, 3, 4, 5, 7, 8]);
        let offsets: Vec<usize> = pages.iter().map(|p| p.offset).collect();
        assert_eq!(offsets, [0, 3, 0, 7]);
        let routes: Vec<usize> = pages[1..].iter().map(|p| p.route_offset).collect();
        // The last page's route has the second page's bytes: they are
        // bytes, and nothing writes them.
        assert_eq!(routes, [5, 5, 3]);
    }

    /// A map keeps its copy of the common events where it draws and its
    /// bytecode still goes to WRAM; otherwise the copy's pages go, and the
    /// rest are laid out as if it had never been there.
    #[test]
    fn a_copy_is_kept_only_where_it_draws_and_the_code_goes_to_wram() {
        let pages = || {
            let mut pages = vec![
                test_page(0, 0, None, vec![1, 2, 3]),
                test_page(1, 0, None, vec![9; 8]),
            ];
            pages[1].event = 4;
            pages
        };
        let room = |n: usize| move |code: usize| code <= n;
        // A map without a copy, or one where it draws and fits: as before.
        let mut kept = pages();
        assert_eq!(lay_out_with_copy(&mut kept, None, room(0)).1, None);
        assert_eq!(
            lay_out_with_copy(&mut kept, Some((4, true)), room(11)),
            ([1, 2, 3, 9, 9, 9, 9, 9, 9, 9, 9].to_vec(), None)
        );
        assert_eq!(kept.len(), 2);
        // Where Wally put the map's own pictures in, the copy draws nothing.
        let mut nothing = pages();
        assert_eq!(
            lay_out_with_copy(&mut nothing, Some((4, false)), room(11)),
            (vec![1, 2, 3], Some(CopyDropped::DrawsNothing))
        );
        assert_eq!(nothing.len(), 1);
        // A copy that would leave the map's bytecode in the cartridge raw,
        // which without it goes to WRAM, is not kept, even if it draws.
        let mut pushed = pages();
        assert_eq!(
            lay_out_with_copy(&mut pushed, Some((4, true)), room(10)),
            (
                vec![1, 2, 3],
                Some(CopyDropped::Pushes {
                    with: 11,
                    without: 3
                })
            )
        );
        assert_eq!(pushed.len(), 1);
        // And on a map already past it without the copy, it stays.
        let mut past = pages();
        assert_eq!(
            lay_out_with_copy(&mut past, Some((4, true)), room(2)).1,
            None
        );
    }

    #[test]
    fn a_test_page_party_is_only_that_of_the_cases_that_touch_it() {
        let add = Command {
            code: 10330,
            indent: 0,
            string: String::new(),
            parameters: vec![0, 0, 11],
        };
        assert_eq!(page_party(&[add], &[10]), Some(vec![10, 11]));
        assert_eq!(page_party(&[], &[10]), None);
    }

    use rm2k_snes_bytecode::events::OP_DONE;

    /// A route on the hero and then a flash of the hero, the flash being
    /// target 0 with its five bytes of colour, power and frames.
    fn route_then_flash(path: &[u8]) -> Vec<u8> {
        let mut code = vec![OP_ROUTE, 0, 8, path.len() as u8];
        code.extend(path);
        code.extend([OP_FLASH, 0, 31, 31, 31, 31, 8, OP_DONE]);
        code
    }

    #[test]
    fn a_hero_route_s_sound_is_not_a_graphic_change_at_a_flash() {
        // Sound 290 —low byte 34, high byte 1, which read as a graphic would
        // be the map's second route graphic— and a step up. Until
        // the-advocate 9329f602 the walk skipped no byte after a 35, and
        // the flash ran with `Other[2]`.
        let graphics = [("Own".to_string(), 0), ("Other".to_string(), 2)];
        let code = route_then_flash(&[35, 34, 1, 0]);
        assert_eq!(
            hero_flashes(&code, 7, &graphics).unwrap(),
            [(7, None, false)]
        );
        // A graphic after the sound is read: the operands are skipped, not
        // the command after them.
        let code = route_then_flash(&[35, 34, 1, 34, 0]);
        assert_eq!(
            hero_flashes(&code, 7, &graphics).unwrap(),
            [(7, Some(("Own".to_string(), 0)), false)]
        );
    }

    #[test]
    fn a_hero_route_s_switch_is_not_a_graphic_change_at_a_flash() {
        // Switch 290 on —low byte 34— and switch 34 off: neither number is
        // a graphic, and the graphic the hero had stays.
        let graphics = [("Own".to_string(), 0), ("Other".to_string(), 2)];
        let code = route_then_flash(&[34, 0, 32, 34, 1, 33, 34, 0]);
        assert_eq!(
            hero_flashes(&code, 7, &graphics).unwrap(),
            [(7, Some(("Own".to_string(), 0)), false)]
        );
    }
}
