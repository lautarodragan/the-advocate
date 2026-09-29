#!/usr/bin/env python3
"""Converts an A Blurred Line map into data the SNES PPU consumes.

Splitting colors into palettes, and merging the least used ones when they
don't fit, lives in `allocator.py`, and reusing mirrored tiles in Voodoo.
What is left here is what depends on the hardware:

  * **Color is 15 bits, five per channel.** Of the 72 colors in the render of
    Map0007, 60 survive.
  * **The background goes in mode 3, at 8 bits per pixel.** There each pixel is
    a direct index into CGRAM and there is no per-tile palette, so the problem
    of splitting the colors into groups simply does not exist. With 4 bits and
    8 palettes, Map0007 lost 32 of its 60 colors; with 8 bits it loses none.

    It costs twice the VRAM per tile, 64 bytes instead of 32. With 92 tiles
    that is 5.8 KB of the 64 available, so it is not a real constraint.
  * **The tile format is planar**, not packed in nibbles: each bit of a pixel
    lives in a different bitmap, in pairs and 16 bytes at a time. That is why
    a 4-bit tile is exactly the first half of an 8-bit one.

Indices are kept to the lower half of CGRAM. Sprites always use palettes 8 to
15, that is indices 128 to 255, and at 8 bits the background reaches up to
255: staying low avoids stepping on them.

Usage:
    rm2k-snes-convert --map-id 7 -o rom/build/inc/mapdata.inc

With a test page, which is the list of RM2k commands from a file in
`rom/pruebas/casos/`; several in one cartridge, each one after a `--case`, and
the cartridge flags before the first. The harness picks which one runs with
`Partida(case=k)`:
    rm2k-snes-convert -o … --map-id 6 \
        --test-commands rom/pruebas/casos/pan.json \
        --case --test-commands rom/pruebas/casos/pan-vuelve.json
"""

import argparse
import collections
import contextlib
import json
import multiprocessing
import os
import sys
import zlib


# Run as a script —which is how the recipes run it—, Python puts this file's
# folder in `sys.path`, not `tools/`, which is where the packages are imported
# from. It is replaced instead of adding `tools/` next to it: with both, a bare
# `import eventos` would work and load a second copy of the module, distinct
# from `port.events`.
# `realpath` and not `abspath`: `just install` installs it on the PATH as
# a symlink, and the folder that matters is the one of the real file.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from rpgmaker import event_codes
from port import events
from rpgmaker import lcf
from rpgmaker import rm2k

# Translucent events carry their own graphic: see `rm2k.decorate_translucent`
# —baked against the background, dithered, or opaque—.
lcf.DECORATE_TRANSLUCENT = rm2k.decorate_translucent
# And the text boxes, rebuilt for the SNES window: see
# `lcf.REFIT_TEXTS` and `port/texts.py`.
from port import texts
lcf.REFIT_TEXTS = texts.refit_commands
from port import animation as animation_mod
from port import picture
from port import patches as patches_mod
from port import title as title_mod
from port import menus as menus_mod
from port import fullscreen
from port import end_game as end_game_mod
from port import screens as screens_mod
from port import battle as battle_mod
from port import experience as X
from port import scene as scene_mod
from port import color as color_mod
from port import constants
from port import rules
from common import settings
from common import project
from port.allocator import CELL
from port.snes_format import (BYTES_PER_TILE, COLORS_PER_PALETTE, cgram_word,
                               entry, pack_tile)
from rpgmaker.rm2k import TILE, collect_npcs, passability_map
from render.render_map import Renderer, build_passability, load_image
from common import environment
from rpgmaker import resources
from rpgmaker.resources import find_resource
from port.asm import block
from port.map_layers import (BG_PALETTES, CGRAM_RESERVED, FAMILIES,
                             PRIORITY_ABOVE, _layers_in_memory,
                             converted_layers, window_palette)
from port.sprites import (INITIAL_POSE, OBJ_COLORS, OBJ_PALETTES,
                          OBJ_PRIORITY, OBJ_PRIORITY_ABOVE, POSE_BYTES,
                          SPRITE_POSES, block_tile, build_characters,
                          changes_graphic, character_palette, discard_warning,
                          drawable_npcs, map_poses, maps_per_character,
                          movable_events, pose_bank, separate_from_hero,
                          sprite_colors)
from port.obj_extras import (TIMER_GLYPHS, TIMER_GLYPH_W, TIMER_X, TIMER_Y,
                             map_animation, map_palette_cap,
                             map_shows_animation, picture_of_image,
                             rain_drops, timer_colors_of, timer_digits)
from port.baking import (_bake_unless_cgram_moves, bake_into_map,
                         bakeable_events)
from port.vram import (MAP_LAYOUT, SLOTS, SLOT_MAP, SLOT_TEXT_LEVEL,
                       SLOT_TEXT_MAX, SLOT_TEXT_WIDTH, SLOT_VRAM,
                       VRAM_ABOVE_MAP, WINDOW_BASES, WINDOW_H, WINDOW_W,
                       _check_items_border, _check_shop, _check_slots,
                       _check_splits, _check_target, items_border_first,
                       vram_layout)
from port.message_window import (FONT_HEIGHT, FONT_PRE_CHAR, FONT_PRE_ROWS,
                                 FONT_WIDTH, WINDOW_COLS_INC, WINDOW_ROWS_INC,
                                 WINDOW_TEXT_COL, WINDOW_TEXT_COLS,
                                 WINDOW_TEXT_ROW, WINDOW_TEXT_ROWS, _columns,
                                 convert_window, font_bytes, font_prerender)
from port.blocks import (BLOCK_BYTES, SUB_MAX, Substitutions, build_blocks,
                         substitution_triples)
from port.materials import (LZ2_CAP_ABOVE_AND_SPRITES, LZ2_CAP_ANIM,
                            LZ2_CAP_BACKDROP, LZ2_CAP_GRID, Materials,
                            compress_blocks, decompress_frames, write_raw)
from port.map_record import (ACTOR_BYTES, ACTOR_COLORS, ANIM_FAM_STRIDE,
                             ANIM_STRIDE, EV_MAX, EV_STRIDE, FLASH_MAX,
                             MAP_STRIDE, NPC_MAX, NPC_STILL, NPC_STRIDE,
                             PAGE_BYTES, PARALLEL_MAX, ROUTE_EV_MAX,
                             ROUTE_GFX_MAX, TURN_NONE, anim_bytes, anim_table,
                             ev_pos_bytes, map_data, map_table, npc_table,
                             offsets)
from port.battle_animations import animations_asm, rom_animations
from port.battle_scenes import (fallback_bytes, patch_uses, rom_scene,
                                scenes_asm)
from port.battle_tables import experience_asm, experience_slots, rom_encounters
from port.music import (boot_frames, compile_music, inherited_songs,
                        rom_songs, separate_songs, write_msu)
from port.game_scan import (args_game_dir, drop_items, has_rain, images_of,
                            map_start, possible_items, possible_leaders,
                            possible_members)


def precompute_layers(renderer, map_ids, args):
    """The layers of all maps, converted in parallel before `convert_map` asks
    for them.

    It is the most expensive part of a cold build —or of a warm one after
    touching this file, which invalidates the stored layers— and each map is
    independent, so there is one process per map. The processes fork with all
    the state already built, prepare the map like `convert_map` does and return
    what they computed with its key; `convert_map` then asks for the same key.
    **A map prepared differently here than there doesn't give a different
    ROM**: it gives another key, and `convert_map` computes it as always.
    """
    if len(map_ids) < 2:
        return
    global _to_precompute
    _to_precompute = (renderer, args)
    processes = min(len(map_ids), os.cpu_count() or 1)
    with multiprocessing.get_context("fork").Pool(processes) as pool:
        for done_ones in pool.map(_map_layers, map_ids, chunksize=1):
            _layers_in_memory.update(done_ones)
    _to_precompute = None


_to_precompute = None


def _map_layers(map_id):
    """What `precompute_layers` does in each process: the same steps as
    `convert_map` up to its two calls to `converted_layers`."""
    renderer, args = _to_precompute
    try:
        # Quiet: whatever it has to say, `convert_map` says it, in order.
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            game_map = renderer.load_map(
                os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
            separate_from_hero(renderer, game_map, args,
                               case_commands(args, map_id))
            converted_layers(renderer, game_map)
            baked = bakeable_events(renderer, game_map)
            if baked:
                bake_into_map(game_map, baked)
                converted_layers(renderer, game_map)
    except BaseException:
        # If it fails, let it fail in `convert_map`, which can say why.
        pass
    return _layers_in_memory


# One bit per switch. The game checks up to 1003 in page conditions, so 1024
# is more than enough: it is 128 bytes of RAM.
SWITCH_BYTES = 128


# The header title of a SNES ROM: 21 bytes, at `$FFC0`.
TITLE_HEADER = 21


def rom_identity():
    """What the ROM says about itself, from the `[rom]` of the project file:
    the header title, already padded with blanks, and the save signature in
    SRAM. They are `.define`s because they are text: `header.s` and
    `save_game.s` use them, and until 2026-09-29 they had them written in."""
    title = settings.ascii("rom", "title", max_length=TITLE_HEADER)
    signature = settings.ascii("rom", "sram_signature", length=4)
    return ("; Who the ROM is, from the project file: the header title and\n"
            "; the signature with which the SRAM says a slot holds a save of\n"
            "; this game.\n"
            '.define ROM_TITLE "%s"\n'
            '.define SRAM_MAGIC_TEXT "%s"\n\n'
            % (title.ljust(TITLE_HEADER), signature))


def emit(path, maps, initial=0, hero_above=False, initial_party=(),
         window=None, title=None, slots=None, picture_info=None,
         animations=None, troops=(), battle_audio=None, scenes=None,
         encounters=None, troop_pages=None, compressed=None,
         enemy_hp=False, game_over=None):
    """The .inc that is assembled together with main.s.

    `enemy_hp` is `--enemy-hp`: whether the battle draws the
    enemies' HP, which RM2k doesn't show.

    `compressed` is what `compress_blocks` returns; if missing it is
    compressed here.

    `title` is the title screen —the image and its menu— and may be missing;
    `game_over`, the Game Over one, too: it is what
    `fullscreen.compressed` returns.
    `slots` is the slots screen and **always goes**: the save point opens it
    from inside the game, whether the ROM has a title or not. See
    `slots_screen` in menus.py.
    """
    for number, map_info in enumerate(maps):
        layout = map_info["layout"]
        for count, name in (
                (len(map_info["tiles"]) // BYTES_PER_TILE, "tiles"),
                (len(map_info["above"][0]) // 32, "encima"),
                (len(map_info["sprite"][0]) // 32 if map_info["sprite"] else 0,
                 "sprites")):
            if count > layout[name][1]:
                raise SystemExit(
                    "map %d: with this VRAM layout, %s needs %d tiles and "
                    "%d fit" % (map_info["id"], name, count,
                                layout[name][1]))

    # Where the picture ended up: the map of the table that took its tiles, and
    # at which tile and with which palette. It comes from the already
    # converted maps and not from a variable that has to be passed around: the
    # one that has it is the only one with a nonzero `image_base`.
    picture_base, picture_pal = 0, 0
    for map_info in maps:
        if map_info["sprite"] and map_info["sprite"][13]:
            picture_base, picture_pal = map_info["sprite"][13], map_info["sprite"][14]
            break

    header = (
        "; Generated by tools/port/snes_convert.py. Do not edit.\n"
        "; Maps: %s\n\n"
        "MAP_COUNT    = %d\n"
        "MAP_STRIDE   = %d\n"
        "MAP_INITIAL = %d\n"
        "; What doesn't depend on the map: the upper layer's tilemap always\n"
        "; lives in the same place in VRAM —the background's is chosen by the\n"
        "; layout, M_VRAM_MAP—, and the NPC table's stride doesn't change.\n"
        "VRAM_ABOVE_MAP = $%04X\n"
        "MAP_LAYOUT  = %d\n"
        "NPC_STRIDE  = %d\n"
        "NPC_MAX     = %d\n"
        "NPC_STILL   = $%02X\n"
        "; The event position table, and how many forced routes can be\n"
        "; running on them at once.\n"
        "EV_STRIDE   = %d\n"
        "EV_MAX      = %d\n"
        "ROUTE_EV_MAX = %d\n"
        "PAGE_BYTES = %d\n"
        "TURN_NONE = $%04X\n"
        "; And how many distinct graphics command 34 can ask for in a map:\n"
        "; its table is copied to RAM like the NPC one.\n"
        "ROUTE_GFX_MAX = %d\n"
        "; The header of a text box, which is the first byte of the one\n"
        "; `OP_MESSAGE` names: the lines in the low three bits, the\n"
        "; auto-close of `\\^` in bit 3 and how many `\\|` pauses it carries in\n"
        "; the high nibble. And how long each pause lasts, which is 61 frames\n"
        "; and not 60: see PAUSE_FRAMES in events.py.\n"
        "HEADER_LINES        = $%02X\n"
        "HEADER_AUTOCLOSE = $%02X\n"
        "PAUSE_FRAMES        = %d\n"
        "; The top bit of the flags byte of the opcodes that write a\n"
        "; variable: whether the write asks for the page refresh. The\n"
        "; converter resolves it by looking at which variables this map's\n"
        "; page conditions look at; `var_apuntar` masks the slot with\n"
        "; VAR_SLOT. See VAR_REFRESH in events.py: without this half of\n"
        "; Lashe City ran at 30 frames.\n"
        "VAR_REFRESH = $%02X\n"
        "VAR_SLOT     = $%02X\n"
        "ANIM_ENTRY = %d\n"
        "ANIM_SOUND   = %d\n"
        "ANIM_FLASH = %d\n"
        "; The ShowPicture picture: where its corner falls on the console's\n"
        "; screen and how many 32x32 objects it measures.\n"
        "; The coordinates already come scaled from 320x240 to 256x224 and X\n"
        "; can be negative: the \"1 year earlier\" picture goes off the left\n"
        "; edge, which is what RM2k shows. See tools/port/picture.py.\n"
        "; The flags of `KeyInputProc`, which go in the second byte of\n"
        # `rom/src/` on purpose: it goes into the `.inc`, which isn't touched
        # yet.
        "; OP_KEY. See `op_key` in rom/src/interpreter_keys_and_waits.s.\n"
        "KEY_WAIT       = $%02X\n"
        "KEY_DIRS       = $%02X\n"
        "KEY_DECISION = $%02X\n"
        "KEY_CANCEL = $%02X\n"
        "KEY_STARTS     = $%02X\n"
        "KEY_VALUE_DECISION = %d\n"
        "KEY_VALUE_CANCEL = %d\n"
        "; And the four directions, with the same number `CheckInput` gives\n"
        "; them. The order they are checked in comes from here: from highest\n"
        "; to lowest, which is what \"RPG processes keys from highest\n"
        "; variable value to lowest\" says.\n"
        "KEY_VALUE_UP         = %d\n"
        "KEY_VALUE_RIGHT      = %d\n"
        "KEY_VALUE_LEFT = %d\n"
        "KEY_VALUE_DOWN       = %d\n"
        "; Which tile of its sprite bank it starts at and with which palette.\n"
        "; They are globals and not in the map record because the picture is\n"
        "; **a single one per ROM** and lives in a single map: the two fields\n"
        "; took the last free bytes of MAP_STRIDE, and growing the record\n"
        "; for that would have been expensive for nothing. That no other map\n"
        "; shows it is enforced by the converter, which stops.\n"
        "PICTURE_BASE = %d\n"
        "PICTURE_PAL = %d\n"
        "PICTURE_X   = %d\n"
        "PICTURE_Y   = %d\n"
        "PICTURE_OBJECTS = %d\n"
        "; How many tiles of the name grid have to be skipped to go from one\n"
        "; object to the next, and from a row of four to the following one.\n"
        "PICTURE_OBJ_STRIDE = %d\n"
        "PICTURE_ROW_STRIDE = %d\n"
        "; The rain: see OP_WEATHER in events.py.\n"
        "RAIN_DROPS_MAX = %d\n"
        "RAIN_DROPS_0 = %d\n"
        "RAIN_DROPS_1 = %d\n"
        "RAIN_DROPS_2 = %d\n"
        "RAIN_LIFE     = %d\n"
        "RAIN_BORN     = %d\n"
        "RAIN_SEED = $%04X\n"
        "WEATHER_RAIN  = %d\n"
        "; The inventory: one byte per item of the LDB and RM2k's cap. See\n"
        "; OP_ITEM in events.py.\n"
        "ITEMS_N       = %d\n"
        "ITEM_MAX      = %d\n"
        "; The variables: how many slots this ROM carries —at least one,\n"
        "; because a zero length would close the save table—, the ControlVars\n"
        "; operand classes the ROM distinguishes, the sum, and the random\n"
        "; seed. See 'RM2k's variables' in events.py.\n"
        "VARIABLES_N   = %d\n"
        "VAR_ADD       = %d\n"
        "VAR_VARIABLE  = %d\n"
        "VAR_RANDOM    = %d\n"
        "VAR_OTHER     = %d\n"
        "; Class 6, a character's coordinates: the target goes like that of\n"
        "; OP_ROUTE —0 the hero, the event's index plus one— and the other\n"
        "; operand says which coordinate. See VAR_CHARACTER in events.py.\n"
        "VAR_CHARACTER = %d\n"
        "CHARACTER_X   = %d\n"
        "CHARACTER_Y   = %d\n"
        "; The high bits of each OP_CELL_TEST write. See CELL_Y in\n"
        "; events.py.\n"
        "CELL_Y        = $%04X\n"
        "CELL_REFRESH = $%04X\n"
        "RANDOM_SEED   = $%04X\n"
        "; And the one for the encounters' randomness, which is a different\n"
        "; one on purpose: walking doesn't advance the map's randomness. See\n"
        "; ENC_SEED in events.py.\n"
        "ENC_SEED      = $%04X\n"
        "TIMER_SET_VAR = %d\n"
        "; The ConditionalBranch condition classes we know, with the RM2k\n"
        "; number as is.\n"
        "COND_GOLD   = %d\n"
        "COND_ITEM   = %d\n"
        "COND_ACTOR  = %d\n"
        "; And the two actor questions that carry two operands, with their\n"
        "; own opcode: see OP_IF_ACTOR in events.py.\n"
        "COND_ACTOR_SKILL = %d\n"
        "COND_ACTOR_EQUIPMENT = %d\n"
        "GOLD_MAX    = %d\n"
        "; The two PanScreen operations that compile.\n"
        "PAN_RUN     = %d\n"
        "PAN_RETURN  = %d\n"
        "; The three timer operations.\n"
        "TIMER_SET      = %d\n"
        "TIMER_START = %d\n"
        "; And its five glyphs on screen: where the first goes and how wide\n"
        "; each one is. The colon's is number 10.\n"
        "TIMER_X        = %d\n"
        "TIMER_Y        = %d\n"
        "TIMER_GLYPH_W  = %d\n"
        "TIMER_TWO_POINTS = %d\n"
        "; How many frames fit in a second, and the extra ones `SetTimer`\n"
        "; adds so that the first second shows whole.\n"
        "TIMER_FRAMES   = %d\n"
        "MORE_TIMER     = %d\n"
        "; How many flashes can be running at once.\n"
        "FLASH_MAX   = %d\n"
        "; How many events with a parallel page there can be in a map.\n"
        "PARALLEL_MAX = %d\n"
        "TRIGGER_AUTO = %d\n"
        "TRIGGER_ACTION     = %d\n"
        "TRIGGER_TOUCHES_HERO = %d\n"
        "TRIGGER_PARALLEL   = %d\n"
        "; How many frames a one-cell step lasts. It comes from events.py and\n"
        "; not from a computation in the ROM.\n"
        "FRAMES_PER_CELL = %d\n"
        "; A route's highest frequency, which is where commands 30 and 31\n"
        "; cap. The lowest is capped by the ROM at 1, like RM2k; what\n"
        "; guarantees it isn't reached is the converter, which rejects the\n"
        "; route.\n"
        "ROUTE_FREQUENCY = %d\n"
        "; And how much a `wait` inside a forced route costs. **It isn't one\n"
        "; frame**: in RM2k it is `SetMaxStopCountForWait`, that is\n"
        "; `20 + (1 << (8 - frecuencia))`, and with frequency 8 —the only\n"
        "; one the converter lets through— it is twenty.\n"
        "ROUTE_WAIT = %d\n"
        "; And the jump: how much is left when it starts. How much it drops\n"
        "; per frame depends on the speed —`jump_per_speed`— and not on the\n"
        "; distance.\n"
        "JUMP_STEP = %d\n"
        "TINT_NEUTRAL = %d\n"
        "; The teleport fade: 35 frames out and 35 back, like RM2k, and of\n"
        "; each 35 the ramp is 24. The map is loaded on the first black\n"
        "; frame, which is number %d. These numbers and the table below come\n"
        "; from the fade constants of tools/port/events.py.\n"
        "FADE_FRAMES = %d\n"
        "FADE_TOTAL      = %d\n"
        "FADE_RAMP       = %d\n"
        "FADE_BLACK      = %d\n"
        "FADE_LOAD       = %d\n"
        "BRIGHTNESS_MAX  = %d\n"
        "; The teleport transitions the ROM does with the mosaic and with\n"
        "; the cut; any other is the fade. See `ChangeScreenTransitions` in\n"
        "; tools/port/events.py.\n"
        "TRANSITION_MOSAIC = %d\n"
        "TRANSITION_CUTOFF  = %d\n"
        "; The Y'CbCr luminance weights, which are the ones RM2k saturates\n"
        "; with. They add up to exactly 65536, so over five-bit channels they\n"
        "; give a five-bit luminance without rescaling anything.\n"
        "LIGHT_R = %d\n"
        "LIGHT_G = %d\n"
        "LIGHT_B = %d\n"
        "; One bit per switch. The highest the game checks is 1003.\n"
        "SWITCH_BYTES = %d\n"
        "; The party the game starts with, and its cap. In RM2k the hero's\n"
        "; graphic is the first one's, so this decides which sprite is\n"
        "; drawn; `ChangePartyMembers` moves it on the fly.\n"
        "PARTY_MAX      = %d\n"
        "PARTY_INITIAL_N = %d\n"
        "ACTOR_BYTES    = %d\n"
        "; How many bytes of that entry are the actor's fifteen colors: the\n"
        "; ROM uploads them to the slot the leaders share. See\n"
        "; `pick_hero_graphic`.\n"
        "ACTOR_COLORS   = %d\n"
        "OBJ_COLORS     = %d\n"
        "; The hero's layer, to sort it against the NPCs.\n"
        "HERO_LAYER  = %d\n"
        "; Its object priority. $10 —below the upper layer— in every ROM\n"
        "; other than `encima`'s, which raises it to $20 to exercise priority\n"
        "; 2. No event of the game gets to exercise it: see `test_encima` in\n"
        "; test_caminar_golden.py.\n"
        "HERO_PRIORITY = $%02X\n"
        "; The message window: its tiles live in the second half of the BG2\n"
        "; bank, that is from index 256, and its cells already come built\n"
        "; with that shift and with the upper layer's priority.\n"
"; And where the background starts in CGRAM: below it live the\n"
        "; screen's backdrop color and the message window's palette, which\n"
        "; belong to the whole ROM. The background goes at 8 bits and\n"
        "; addresses CGRAM directly, so it is enough for it to start shifted.\n"
        "CGRAM_BASE     = %d\n"
"WINDOW_CGADD   = %d\n"
        "WINDOW_TILES   = %d\n"
        "WINDOW_ROWS_ = %d\n"
        "TEXT_WINDOW_COLS = %d\n"
        "; The text area: where it starts in the window's tile bank and\n"
        "; which cells it takes. Its tiles aren't deduplicated —the ROM\n"
        "; rewrites them— and that is where the cap of characters per line\n"
        "; comes from.\n"
        "WINDOW_TEXT_BASE = %d\n"
        "WINDOW_TEXT_ROW = %d\n"
        "WINDOW_TEXT_ROWS = %d\n"
        "WINDOW_TEXT_COL    = %d\n"
        "WINDOW_TEXT_COLS = %d\n"
        "MESSAGE_COLS   = %d\n"
        "; The font: 95 ASCII glyphs of six bits by twelve rows, and the\n"
        "; shadow's palette index. That of each row of the glyph is in\n"
        "; font_color.\n"
        "FONT_HEIGHT    = %d\n"
        "FONT_WIDTH     = %d\n"
        "FONT_SHADOW    = %d\n"
        "FONT_PRE_ROWS = %d\n"
        "FONT_PRE_CHAR    = %d\n"
        "; The ChipSet animation. Each map has an entry in `anim_table` with\n"
        "; its two runs and a block with the drawings; see `anim_table` in\n"
        "; snes_convert.py. The cadences and the water cycle come from\n"
        "; `rm2k.py`.\n"
        "ANIM_FAMILIES  = %d\n"
        "ANIM_STRIDE    = %d\n"
        "ANIM_FAM_STRIDE = %d\n"
        "WATER_FRAMES   = %d\n"
        "WATER_DRAWINGS = %d\n"
        "WATER_CYCLE_N  = %d\n"
        "ANIMATED_FRAMES = %d\n"
        "ANIMATED_STEPS = %d\n"
        "BYTES_PER_TILE = %d\n"
        "; The title screen. TITLE_TILES at 0 means this ROM doesn't carry\n"
        "; it and the blocks below are one byte of padding; the code in\n"
        # `rom/src/` on purpose: it goes into the `.inc`, which isn't touched
        # yet.
        "; rom/src/ turns itself off with that. It lives alone in VRAM —it\n"
        "; shares with no map, because while it is shown there is no map\n"
        "; loaded— so its addresses are fixed and don't come from the\n"
        "; `vram_layout` layout. The image is uploaded by `screen_upload`,\n"
        "; from its row in `screens_table`: the tiles from $0000 and the\n"
        "; tilemap at SCREEN_MAP.\n"
        "TITLE_TILES    = %d\n"
        "; The menu, on BG2 at four bits per pixel: its tile bank, how many\n"
        "; options it has and which is selected on entering. The cursor isn't\n"
        "; drawn separately: there is one tilemap per option and moving it is\n"
        "; uploading the other.\n"
        ";\n"
        "; The VRAM layout on this screen, in words, and why each one is\n"
        "; where it is: the image tiles start at 0 and take 15872, so\n"
        "; everything else goes **above** that. A BG's tile base goes in\n"
        "; steps of 4096 words, which is what fixes $5000 for the menu; the\n"
        "; tilemaps go in steps of 1024 and fit in the gap next to it.\n"
        ";\n"
        ";   $0000 .. $3E00   the image's 496 tiles, at 8bpp\n"
        ";   $4400 .. $4800   the menu's tilemap\n"
        ";   $5000 ..         the menu's tiles, at 4bpp\n"
        ";   $7C00 .. $8000   the image's, SCREEN_MAP of game_over.s\n"
        "TITLE_MENU_CGRAM = %d\n"
        "TITLE_MENU_TILES = %d\n"
        "TITLE_MENU_VRAM   = $5000\n"
        "TITLE_MENU_MAP    = $4400\n"
        "TITLE_MENU_N      = %d\n"
        "; The slots screen, which both ends use: 'Resume the Story' and the\n"
        "; save point. It is a screen of its own —not a layer over the\n"
        "; title— so it is uploaded whole on entering. **It goes in every\n"
        "; ROM**, with a title or without: the save point opens it from\n"
        "; inside the game, and that is why its VRAM addresses are its own\n"
        "; and not the menu's: they fall in the BG1 tile bank of every\n"
        "; layout, which is what `back_to_map` restores with `load_map`.\n"
        "; See SLOT_MAP in the converter.\n"
        "SLOT_VRAM         = $%04X\n"
        "SLOT_MAP          = $%04X\n"
        ";\n"
        "; The cell blocks: the header has two variants —load and save— and\n"
        "; each slot four —empty or full, with cursor or without—. Moving the\n"
        "; cursor is rewriting two rows and not a whole tilemap.\n"
        "SRAM_SLOTS_N      = %d\n"
        "SLOT_TILES        = %d\n"
        "SLOT_HDR_ROW      = %d\n"
        "SLOT_HDR_ROWS     = %d\n"
        "SLOT_HDR_CELLS = %d\n"
        "SLOT_ROW0         = %d\n"
        "SLOT_JUMP         = %d\n"
        "SLOT_ROWS         = %d\n"
        "SLOT_CELLS        = %d\n"
        "; And where each row goes in the tilemap, in words. It also comes\n"
        "; from a table: the computation is SLOT_ROW0 + n * SLOT_JUMP,\n"
        "; times 32, and writing it in the 65816 would be the fourth place to\n"
        "; get it wrong.\n"
        "SLOT_HDR_VRAM     = %d\n"
        "; How many blocks there are before the first of the rows: they are\n"
        "; the two headers, load and save.\n"
        "SLOT_BLOCK_ROWS = 2\n"
        "; The saved game's party, above the row: the faces of up to\n"
        "; SLOT_FACES_MAX, of SLOT_FACE_COLS by SLOT_FACE_ROWS cells,\n"
        "; and the first one's name and level. Which face block each actor\n"
        "; gets is said by `slot_face_block`, by actor id up to\n"
        "; SLOT_ACTORS_N, with $FF for 'has none'; and where they go,\n"
        "; `slot_face_vram` —four per slot— and `slot_name_vram`.\n"
        ";\n"
        "; The name and the level aren't blocks: they are composed one letter\n"
        "; per cell with `slot_glyph_cells`, and each actor's text comes\n"
        "; from its row of `slot_actor_text` —the name, the two digits of\n"
        "; the level and max HP, one after the other—. See 'lo que depende\n"
        "; del actor' in menus.py: it is what keeps the tile bank from\n"
        "; growing with the number of actors.\n"
        "SLOT_FACES_MAX    = %d\n"
        "SLOT_FACE_COLS    = %d\n"
        "SLOT_FACE_ROWS = %d\n"
        "SLOT_NAME_COLS      = %d\n"
        "; How long an actor's row is in `slot_actor_text` and where each\n"
        "; strip starts inside it. The width is a power of two even if bytes\n"
        "; are left over: that way the index comes from shifts and not from a\n"
        "; multiplication.\n"
        "SLOT_TEXT_WIDTH     = %d\n"
        "SLOT_TEXT_NAME = 0\n"
        "SLOT_TEXT_LEVEL     = %d\n"
        "SLOT_TEXT_MAX       = %d\n"
        "SLOT_LEVEL_DIGITS = %d\n"
        "; How many cells from the name the first digit of the level falls.\n"
        "SLOT_LEVEL_OFS      = %d\n"
        "; And where digit 0 starts inside `slot_glyph_cells`, which is\n"
        "; indexed by character: it is where the gold and the HP get their\n"
        "; digits from.\n"
        "GLYPH_DIGIT_0     = %d\n"
        "SLOT_ACTORS_N     = %d\n"
        "; How many CGRAM entries the slots screen uploads: palette 0 for\n"
        "; the text and one per face, of sixteen each.\n"
        "SLOT_CGRAM_N      = %d\n"
        "; How many CGRAM entries the title menu uses: one palette of\n"
        "; sixteen, number 0. It is already defined above, with the title\n"
        "; screen; this confirms both computations give the same.\n"
        ".assert TITLE_MENU_CGRAM = %d, error, \"two computations of the menu's CGRAM\"\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in maps),
           len(maps), MAP_STRIDE, initial,
           VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           NPC_STILL,
           EV_STRIDE, EV_MAX, ROUTE_EV_MAX,
           PAGE_BYTES, TURN_NONE, ROUTE_GFX_MAX,
           events.HEADER_LINES, events.HEADER_AUTO_CLOSE,
           events.PAUSE_FRAMES, events.VAR_REFRESH, events.VAR_SLOT_MAX,
           events.ANIM_ENTRY_BYTES, events.ANIM_SOUND, events.ANIM_SCREEN_FLASH, events.KEY_WAIT,
           events.KEY_DIRS, events.KEY_DECISION,
           events.KEY_CANCEL, events.KEY_START,
           events.KEY_VALUE_DECISION, events.KEY_VALUE_CANCEL,
           events.KEY_VALUE_DIR[0], events.KEY_VALUE_DIR[1],
           events.KEY_VALUE_DIR[3], events.KEY_VALUE_DIR[2],
           picture_base, picture_pal,
           picture_info["x"] if picture_info else 0, picture_info["y"] if picture_info else 0,
           picture_info["objetos"] if picture_info else 0,
           picture.OBJ_SIDE, 4 * picture.GRID,
           max(events.RAIN_DROPS),
           events.RAIN_DROPS[0], events.RAIN_DROPS[1],
           events.RAIN_DROPS[2], events.RAIN_LIFE,
           events.RAIN_SPAWN, events.RAIN_SEED,
           events.WEATHER_RAIN,
           events.ITEMS_N,
           events.ITEM_MAX,
           variables_n(),
           events.VAR_ADD, events.VAR_VARIABLE, events.VAR_RANDOM,
           events.VAR_OTHER,
           events.VAR_CHARACTER, events.CHARACTER_X, events.CHARACTER_Y,
           events.CELL_Y, events.CELL_REFRESH,
           events.RANDOM_SEED, events.ENC_SEED,
           events.TIMER_SET_VAR,
           events.COND_GOLD, events.COND_ITEM,
           events.COND_ACTOR, events.COND_ACTOR_SKILL,
           events.COND_ACTOR_EQUIPMENT,
           events.GOLD_MAX,
           events.PAN_SHIFT, events.PAN_RETURN,
           events.TIMER_SET, events.TIMER_START,
           TIMER_X, TIMER_Y, TIMER_GLYPH_W, TIMER_GLYPHS - 1,
           events.FRAMES_PER_SECOND, events.TIMER_EXTRA_FRAMES,
           FLASH_MAX, PARALLEL_MAX,
           events.TRIGGER_AUTOSTART, events.TRIGGER_ACTION,
           events.TRIGGER_TOUCH_HERO, events.TRIGGER_PARALLEL,
           events.FRAMES_PER_CELL, events.ROUTE_FREQUENCY,
           events.ROUTE_WAIT_FRAMES,
           events.JUMP_STEP,
           color_mod.NEUTRAL_TINT,
           events.FADE_RAMP,
           events.FADE_FRAMES, events.FADE_TOTAL,
           events.FADE_RAMP, events.FADE_BLACK,
           events.FADE_RAMP, events.BRIGHTNESS_MAX,
           events.TRANSITION_MOSAIC, events.TRANSITION_CUT,
           color_mod.LUMA_R, color_mod.LUMA_G, color_mod.LUMA_B, SWITCH_BYTES,
           events.PARTY_MAX, len(initial_party), ACTOR_BYTES,
           ACTOR_COLORS, OBJ_COLORS,
           rm2k.LAYER_SAME,
           OBJ_PRIORITY_ABOVE if hero_above else OBJ_PRIORITY,
           CGRAM_RESERVED,
           window_palette() * COLORS_PER_PALETTE,
           len(window["tiles"]) // 32,
           WINDOW_ROWS_INC, WINDOW_COLS_INC,
           window["base"],
           WINDOW_TEXT_ROW, WINDOW_TEXT_ROWS,
           WINDOW_TEXT_COL, WINDOW_TEXT_COLS, _columns(),
           FONT_HEIGHT, FONT_WIDTH,
           window["sombra"],
           FONT_PRE_ROWS, FONT_PRE_CHAR,
           len(FAMILIES), ANIM_STRIDE, ANIM_FAM_STRIDE,
           rm2k.WATER_FRAMES_SLOW,
           FAMILIES[0][1],
           len(rm2k.WATER_CYCLE), rm2k.ANIMATED_FRAMES, rm2k.ANIMATED_STEPS,
           BYTES_PER_TILE,
           0 if title is None else title["pantalla"]["tiles"],
           constants.MENU_CGRAM,
           0 if title is None else len(title["menu_tiles"]),
           0 if title is None else len(title["menu_tilemaps"]),
           SLOT_VRAM, SLOT_MAP,
           len(slots["filas"]),
           len(slots["tiles"]),
           menus_mod.HEADER_Y // constants.CELL,
           menus_mod.HEADER_ROWS,
           menus_mod.HEADER_ROWS * constants.COLS,
           menus_mod.SLOT_Y // constants.CELL,
           menus_mod.SLOT_STEP // constants.CELL,
           menus_mod.SLOT_ROWS,
           menus_mod.SLOT_ROWS * constants.COLS,
           menus_mod.HEADER_Y // constants.CELL * 32,
           menus_mod.FACES_MAX, menus_mod.FACE_CELLS,
           menus_mod.FACE_CELLS, menus_mod.NAME_COLS,
           SLOT_TEXT_WIDTH, SLOT_TEXT_LEVEL, SLOT_TEXT_MAX,
           menus_mod.LEVEL_DIGITS,
           ((menus_mod.LEVEL_ROW - menus_mod.NAME_ROW) * 32
            + menus_mod.LEVEL_COL - menus_mod.NAME_COL),
           (ord("0") - menus_mod.ITEM_FIRST_CHAR) * 4,
           (max(list(slots["caras"]) + list(slots["actores"]) + [-1])
            + 1),
           len(slots["paletas"]) * constants.MENU_CGRAM,
           constants.MENU_CGRAM))

    with open(path, "w") as handle:
        handle.write(header)
        handle.write(rom_identity())
        handle.write(offsets())
        handle.write("\n\n")
        # The fade ramp, in bank 0 because `fade_tick` reads it with
        # `lda fade_ramp, x`. It comes from `events.fade_ramp()`:
        # writing it in tools/runtime/ too would be having two copies that can
        # get out of sync without anything noticing.
        handle.write('.segment "TABLES"\n'
                     '; The master brightness on each frame of the ramp, from\n'
                     '; black to full. Going down it is read backwards.\n'
                     'fade_ramp:\n        .byte %s\n\n'
                     % ",".join(str(v) for v in events.fade_ramp()))
        # The data goes in RODATA, which the linker spreads over the upper
        # banks. What stays in TABLES —that is, in bank 0— is what the ROM
        # walks with a bare `lda tabla, x`, which addresses the data bank.
        # `map_table` is no longer among those: see `map_table`.
        handle.write('.segment "RODATA"\n')
        # The twelve poses of each character that changes pose, **once per
        # quantization** and not once per ROM: two maps that draw the same
        # character with the same palette share the bank, and if one quantized
        # it differently —because it lent it someone else's palette, as map 8
        # does to Chara2:0, or took a color off— it carries its own. Until
        # 2026-09-10 this was a `sys.exit`, and the palette split had a rule to
        # dodge it that the lending didn't look at: adding Lashe City 33,36 to
        # the demo stopped there. One extra bank is 6 KB of cartridge; a stop
        # is a map that doesn't fit.
        global_index, banks, index_per_map = {}, [], []
        for map_info in maps:
            own = {}
            for pair, data in (map_info["sprite"][8].items()
                               if map_info["sprite"] else ()):
                key = (pair, data)
                if key not in global_index:
                    if any(k[0] == pair for k in global_index):
                        print("  map %d: %s:%d goes with a pose bank of its "
                              "own, quantized differently than in another map"
                              % (map_info["id"], pair[0], pair[1]))
                    global_index[key] = len(banks)
                    banks.append(data)
                own[pair] = global_index[key]
            index_per_map.append(own)
        handle.write("; --- the poses of the characters that change pose, "
                     "for the whole ROM ---\n")
        # **Each pose once**, even if several characters or the same one
        # repeat it: the pose tables carry one pointer per pose —`npc_poses`,
        # `actor_table`—, so two equal ones point to the same block and the
        # ROM uploads the same bytes from another place. It happens a lot: the
        # equal walking frames of the same CharSet, and the characters that
        # repeat across maps with another quantization that didn't change a
        # pose. Each one with its `.block`, because it is uploaded by DMA.
        pose_label, bank_poses = {}, []
        for data in banks:
            theirs = []
            for pose in range(SPRITE_POSES):
                bytes_ = data[pose * POSE_BYTES:(pose + 1) * POSE_BYTES]
                if bytes_ not in pose_label:
                    pose_label[bytes_] = "pose_%d" % len(pose_label)
                    handle.write(block(pose_label[bytes_], bytes_) + "\n")
                theirs.append(pose_label[bytes_])
            bank_poses.append(theirs)
        handle.write("\n")
        print("  poses: %d distinct out of %d, %.1f KB less"
              % (len(pose_label), SPRITE_POSES * len(banks),
                 (SPRITE_POSES * len(banks) - len(pose_label))
                 * POSE_BYTES / 1024.0))
        index_per_map = [{pair: bank_poses[g] for pair, g in own.items()}
                         for own in index_per_map]
        write_raw(os.path.dirname(os.path.abspath(path)), maps)
        materials = Materials(dedupe=True,
                              compressed=compressed
                              or compress_blocks(maps))
        handle.write("; The LZ2 caps, which decompress.s enforces\n"
                     "LZ2_CAP_BACKDROP = $%04X\n"
                     "LZ2_CAP_ABOVE_Y_SPRITES = $%04X\n"
                     "LZ2_CAP_ANIM = $%04X\n"
                     "LZ2_CAP_GRID = $%05X\n\n"
                     % (LZ2_CAP_BACKDROP, LZ2_CAP_ABOVE_AND_SPRITES,
                        LZ2_CAP_ANIM, LZ2_CAP_GRID))
        labels = []
        for number, map_info in enumerate(maps):
            # `mapas_de` in rom/pruebas/arnes/consola.py reads the table
            # order from this line with a regex that expects "map".
            handle.write("; --- %d: map %d %r ---\n"
                         % (number, map_info["id"], map_info["nombre"]))
            text, theirs = map_data(map_info, number,
                                    index_per_map[number], materials)
            labels.append(theirs)
            handle.write(text)
            handle.write("\n")
        if True:
            # The message window is a single one for the whole ROM —the same
            # skin, the same size— so it goes as a global block and not in the
            # map table. The only thing that depends on the map is which
            # palette it goes in, and that is resolved above, when choosing the
            # CGRAM split.
            #
            # BG2 goes at 4 bits, so its cell **does** use the three palette
            # bits —unlike the background, which goes at 8 and ignores them—.
            # The window goes in 0 and is the same for every map: its cells
            # are emitted only once. That the background doesn't step on it
            # comes from the split —it starts at `CGRAM_RESERVED`— but it is
            # checked anyway: if it stepped on it, the window would come out
            # with the map's colors and no single-map comparison would see it.
            palette = window_palette()
            for m in maps:
                if len(m["cram_words"]) + CGRAM_RESERVED > \
                        m["above"][3] * COLORS_PER_PALETTE:
                    raise SystemExit(
                        "the background of map %d uses %d CGRAM entries from "
                        "%d and steps on the upper layer, which starts at %d"
                        % (m["id"], len(m["cram_words"]), CGRAM_RESERVED,
                           m["above"][3] * COLORS_PER_PALETTE))
            handle.write("\n; --- the message window ---\n")
            handle.write(block("window_tiles", window["tiles"]) + "\n")
            # Only the `CGRAM_RESERVED` at the bottom: from 8 up it belongs
            # to the background, and uploading all sixteen would erase it.
            handle.write(block("window_cgram",
                               b"".join(w.to_bytes(2, "little")
                                        for w in window["cram"]
                                        [:CGRAM_RESERVED])) + "\n")
            # One layout for each window base the VRAM layouts use: the tile
            # index goes shifted behind the upper layer, and the upper layer
            # measures 128 or 256 depending on the layout. See
            # `WINDOW_BASES` and `stamp_window`.
            for base, label in zip(WINDOW_BASES, ("window_cells",
                                                  "window_cells_256")):
                plane = bytearray()
                for row in window["celdas"]:
                    for cell in row:
                        # With the upper layer's priority so that it covers
                        # the hero and the NPCs.
                        plane += (entry(base + cell, False, False,
                                        PRIORITY_ABOVE)
                                  | (palette << 10)).to_bytes(2, "little")
                handle.write(block(label, bytes(plane)) + "\n")
            # The text area without text: the 240 tiles the ROM copies to the
            # buffer before drawing on top. They go in the order the ROM needs
            # them, that is the cells' order.
            handle.write(block("window_backdrop", window["fondo"]) + "\n")
            # The font and the colors. `font_color` is the palette index of
            # each of the glyph's twelve rows: RM2k's gradient comes from a
            # 16x16 mask, but each row is a single color, so twelve bytes are
            # enough and the ROM doesn't have to sample anything.
            handle.write(block("font_table", window["fuente"]) + "\n")
            pre = font_prerender(window["fuente"], window["color"],
                                 window["sombra"])
            for phase, data in enumerate(pre):
                handle.write(block("font_pre%d" % phase, data) + "\n")
            handle.write(block("messages", window["mensajes"]) + "\n")
            # How big it is and how big it can be: the ROM doesn't use them,
            # `just espacio` reads them from the symbol table. The cap is what
            # the operand of `OP_MESSAGE` reaches, 16 bits and in steps of
            # `MENSAJES_PASO` bytes.
            handle.write("MESSAGES_BYTES = %d\nMESSAGES_CAP = %d\n"
                         % (len(window["mensajes"]),
                            0x10000 * events.MESSAGES_STEP))
        # --- the ShowPicture picture ---
        #
        # Its fifteen colors as they came out of `picture.convert`, in the
        # order the tiles index them. They go in a global block and not in the
        # map table because the picture is a single one per ROM; what does belong
        # to the map is which tile and which palette it ended up in, which
        # goes in the record.
        #
        # Entry 0 goes too, in black, and not because it is drawn —a sprite's
        # index 0 is transparent— but so that the ROM uploads all sixteen at
        # once: the DMA starts at the palette's entry, not one further on, and
        # subtracting one here is exactly the kind of computation that is
        # written right on one side and wrong on the other.
        handle.write("\n; --- the ShowPicture picture ---\n")
        colors = ([(0, 0, 0)] + list(picture_info["paleta"])) if picture_info else [(0, 0, 0)]
        handle.write(block("picture_cgram",
                           b"".join(cgram_word(c).to_bytes(2, "little")
                                    for c in colors)) + "\n")
        # The screen flash products: `d * nivel // 31` for d and level from 0
        # to 31, in the level's row. It is `destellar_canal`'s computation, and
        # the ROM read it from the multiplier and the divider for each of the
        # 96 entries of its tables on every odd frame: see
        # `one_flash_table`.
        handle.write(block("prod31_table", bytes(
            d * n // 31 for n in range(32) for d in range(32))) + "\n")
        handle.write(animations_asm(animations or {}, maps))
        # --- the title screen ---
        #
        # It goes entirely on BG1, which in mode 3 has eight bits per pixel:
        # the image addresses CGRAM directly and doesn't have to be split into
        # palettes of sixteen, which is what a map does have to do because the
        # sprites need theirs. There are no sprites here.
        #
        # The tiles are deduplicated like the map's. The image has a lot of
        # black —the bottom half, which is where the menu goes— so of the 1024
        # cells fewer than 500 are left.
        #
        # The image goes compressed, together with the menu's colors, in its
        # row of `screens_table`: see "the full screens", below. What stays
        # here is the menu, which isn't part of the image.
        handle.write("\n; --- the title screen ---\n")
        if title is None:
            handle.write(block("title_menu_tiles", b"\x00") + "\n")
            handle.write(block("title_menu_cells", b"\x00") + "\n")
        else:
            # The menu: a 4-bit tile bank and one tilemap per selected option.
            # Moving the cursor is uploading the other tilemap, and that is why
            # they go one after the other and the same size: the ROM indexes
            # them by multiplying.
            menu = bytearray()
            for cell in title["menu_tiles"]:
                menu += pack_tile(cell, planes=4)
            handle.write(block("title_menu_tiles", bytes(menu)) + "\n")
            plane = bytearray()
            for menu_map in title["menu_tilemaps"]:
                for index in menu_map:
                    plane += entry(index, False, False,
                                   PRIORITY_ABOVE).to_bytes(2, "little")
            handle.write(block("title_menu_cells", bytes(plane)) + "\n")

        # --- the full screens: Game Over and the title ---
        #
        # Each one is an LZ2 stream with the tiles, the tilemap and the
        # colors, and its row in `screens_table`, which is what
        # `screen_upload` reads: see tools/port/fullscreen.py. Without
        # a Game Over image, GAME_OVER_TILES at 0 and the ROM goes back to the
        # title without a screen, as until 2026-09-28; without a title screen,
        # TITLE_TILES at 0 and no row. Without either of them SCREEN_ROW
        # isn't defined, and `screen_upload` isn't assembled.
        handle.write("\n; --- the full screens ---\n")
        handle.write("GAME_OVER_TILES = %d\n"
                     % (0 if game_over is None else game_over["tiles"]))
        rows = []
        if game_over is not None:
            rows.append(("GAME_OVER", "game_over_lz2", game_over))
        if title is not None:
            rows.append(("TITLE", "title_lz2", title["pantalla"]))
        if not rows:
            handle.write(block("screens_table", b"\x00") + "\n")
        else:
            handle.write(
                "; Each screen's row in `screens_table`: where its stream is,\n"
                "; how many bytes of tiles and colors it brings, and from which\n"
                "; CGRAM color they go. See `screen_upload`.\n"
                "SCREEN_ROW = 8\n")
            for number, (name, _, _) in enumerate(rows):
                handle.write("SCREEN_%s = %d\n" % (name, number))
            handle.write(".block %d\nscreens_table:\n" % (8 * len(rows)))
            for _, label, data in rows:
                handle.write("    .word .loword(%s)\n"
                             "    .byte ^%s\n"
                             "    .word %d, %d\n"
                             "    .byte %d\n"
                             % (label, label, data["tiles"] * 64,
                                data["colores"] * 2, data["primer_color"]))
            handle.write("\n")
            for _, label, data in rows:
                handle.write(block(label, data["flujo"]) + "\n")

        # The slots screen, which **goes in every ROM** and not only in the
        # ones that carry a title: the save point opens it from inside the
        # game. Until 2026-09-10 it came out only with the title screen and
        # without it a byte of padding was left with `SLOT_TILES` at zero;
        # and a DMA of "zero bytes" is 65536, so opening it from a ROM without
        # a title filled VRAM with garbage. It is the "black screen with
        # garbage on top" that for a while was noted down as a mystery of the
        # interpreter's context.
        #
        # Its tile bank is its own: it shares the VRAM address with the title
        # menu's, but not the tiles, because both screens are uploaded whole
        # every time one is entered.
        handle.write("\n; --- the slots screen ---\n")
        data = bytearray()
        for cell in slots["tiles"]:
            data += pack_tile(cell, planes=4)
        handle.write(block("slot_tiles", bytes(data)) + "\n")

        # The bank of the slots and the menu goes **with the priority bit
        # set**, like the item glyphs: the actor choice turns on BG1 with its
        # windows, and in mode 3 BG1 at priority 0 stays above BG2 at priority
        # 0 —the red bar would cover the row—. In the other screens of this
        # bank BG1 is off and the bit doesn't change a pixel; the experience
        # sprites discard it.
        def cells_asm(blocks):
            plane = bytearray()
            for cells in blocks:
                for index in cells:
                    plane += entry(index, False, False,
                                   priority=1).to_bytes(2, "little")
            return bytes(plane)

        # Each cell block goes with its own label and is named by a pointer
        # table, just like the music songs. It is more ROM than computing the
        # offset with shifts —three one-byte tables per block— and in exchange
        # the ROM doesn't have to multiply by 96 or by 192 anywhere. That
        # multiplication would be written here and there, which is exactly
        # the shape of error this repo has already paid for three times.
        #
        # The order: first the two headers —load and save— and then, per slot,
        # the four variants as full * 2 + cursor.
        slot_blocks = []
        for mode, cells in enumerate(slots["cabeceras"]):
            name = "slot_hdr_%d" % mode
            handle.write(block(name, cells_asm([cells])) + "\n")
            slot_blocks.append(name)
        for number, row in enumerate(slots["filas"]):
            for full in (0, 1):
                for cursor in (0, 1):
                    name = "slot_%d_%d%d" % (number, full, cursor)
                    handle.write(
                        block(name, cells_asm([row[full][cursor]]))
                        + "\n")
                    slot_blocks.append(name)
        # And behind, per actor that can join the party, its face: the ROM
        # writes it over the row according to what the save stored. The face
        # cells carry the palette in their three bits, which are used here: it
        # is BG2 at 4bpp.
        #
        # Its name and its level are **not** blocks: the ROM composes them with
        # glyphs, see "what depends on the actor" in menus.py. That is what
        # keeps the bank from growing with the number of actors.
        face_block = {}
        for actor in sorted(slots["caras"]):
            name = "slot_face_%d" % actor
            handle.write(block(name, cells_asm([slots["caras"][actor]]))
                         + "\n")
            face_block[actor] = len(slot_blocks)
            slot_blocks.append(name)
        # And the pause menu's, which live in the same tile bank: each command
        # in its two variants —1 is disabled, in the gray palette—, the coin,
        # and the text of a party row, which is a single one for the four and
        # for every actor. The cursor and the glyphs don't go as blocks: they
        # are two cells each and the ROM writes them word by word, see
        # `slot_glyph_cells`.
        menu = slots["menu"]
        menu_option_block = len(slot_blocks)
        for order, variants in enumerate(menu["opciones"]):
            for disabled, cells in enumerate(variants):
                name = "menu_option_%d_%d" % (order, disabled)
                handle.write(block(name, cells_asm([cells])) + "\n")
                slot_blocks.append(name)
        menu_currency_block = len(slot_blocks)
        handle.write(block("menu_currency", cells_asm([menu["moneda"]]))
                     + "\n")
        slot_blocks.append("menu_currency")
        menu_row_block = len(slot_blocks)
        handle.write(block("menu_row", cells_asm([menu["fila"]])) + "\n")
        slot_blocks.append("menu_row")
        # And the item screen, which has a bank of its own: the font one
        # letter per cell, its two palettes, and the text of each item the ROM
        # knows —name and two lines of description—, in ASCII.
        data = bytearray()
        for cell in slots["items_tiles"]:
            data += pack_tile(cell, planes=4)
        handle.write(block("items_tiles", bytes(data)) + "\n")
        def palettes_cgram(palettes):
            return b"".join(
                cgram_word(c).to_bytes(2, "little") for palette in palettes
                for c in list(palette) + [(0, 0, 0)] * (constants.MENU_CGRAM
                                                        - len(palette)))

        # The first two, which are uploaded with the bank on every screen that
        # uses it; the "goes up" one and the red one go separately and only
        # the equipment screen uploads them, because in battle the entries
        # from the third palette on are the backdrop's —`scene.CGRAM_BASE`—
        # and uploading them there wouldn't help anyone.
        handle.write(block("items_cgram", palettes_cgram(
            slots["items_paletas"][:menus_mod.ITEM_UP])) + "\n")
        handle.write(block("item_cgram_uploads", palettes_cgram(
            slots["items_paletas"][menus_mod.ITEM_UP:])) + "\n")
        # The windows of the item and equipment screens, on BG1: see
        # `ITEM_WINDOWS` and `screens.EQ_WINDOWS`. The tiles and the
        # colors are the same for both. Each tilemap goes without the bottom
        # rows the screen doesn't show, and each cursor as the two rows of
        # cells it takes, which the ROM copies on top: 128 bytes.
        border_tiles, border_colors, ((border_map, border_bars),
                                      (eq_map, eq_bars)) = \
            slots["items_marco"]
        handle.write(block("items_border_tiles", b"".join(
            pack_tile(cell, planes=8) for cell in border_tiles)) + "\n")
        handle.write(block("items_border_map", b"".join(
            word.to_bytes(2, "little") for word in border_map)) + "\n")
        handle.write(block("items_border_bars", b"".join(
            word.to_bytes(2, "little") for bar in border_bars
            for word in bar)) + "\n")
        handle.write(block("eq_border_map", b"".join(
            word.to_bytes(2, "little") for word in eq_map)) + "\n")
        handle.write(block("eq_border_bars", b"".join(
            word.to_bytes(2, "little") for bar in eq_bars
            for word in bar)) + "\n")
        handle.write(block("items_border_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little")
            for c in border_colors)) + "\n")
        # The shop windows, on BG1 with their own base: see
        # `screens.TI_WINDOWS` and `compact_shop`, which says what is
        # stored. The stretches of each layer are `(VRAM word, source byte in
        # `ti_border_rows`, bytes)`, terminated by three zeros; the bars,
        # `(VRAM word, source byte in `ti_border_patches`, bytes per row,
        # rows)`.
        PM = screens_mod
        ti_tiles, ti_colors, ti_maps = slots["tienda_marco"]
        ti_rows, ti_top, ti_layers, ti_patches, ti_bars = \
            PM.compact_shop(ti_maps)

        def le_words(values):
            return b"".join(v.to_bytes(2, "little") for v in values)

        handle.write(block("ti_border_tiles", b"".join(
            pack_tile(cell, planes=8) for cell in ti_tiles)) + "\n")
        handle.write(block("ti_border_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little") for c in ti_colors)) + "\n")
        handle.write(block("ti_border_rows", le_words(
            p for f in ti_rows for p in f)) + "\n")
        handle.write(block("ti_border_patches", le_words(ti_patches))
                     + "\n")
        cols = constants.COLS
        stretches, layer_stretches = [], []
        for layer in ti_layers:
            layer_stretches.append(2 * len(stretches))
            for row, origin, how_many in layer:
                stretches += [PM.TI_MAP + row * cols, origin * 2 * cols,
                              how_many * 2 * cols]
            stretches += [0, 0, 0]
        handle.write(block("ti_stretches", le_words(stretches)) + "\n")
        handle.write(block("ti_layer_stretches", le_words(layer_stretches))
                     + "\n")
        handle.write(block("ti_bars", le_words(
            v for layer in ti_bars for row, col, rows, width, origin in layer
            for v in (PM.TI_MAP + row * cols + col, 2 * origin, 2 * width,
                      rows))) + "\n")
        base_bars = [0]
        for layer in ti_bars:
            base_bars.append(base_bars[-1] + len(layer))
        handle.write(block("ti_bar_base", bytes(base_bars[:-1])) + "\n")
        handle.write(block("ti_layer_mode", bytes(PM.TI_LAYER_OF_MODE))
                     + "\n")
        handle.write(
            "TI_BORDER_VRAM    = $%04X\n"
            "TI_BORDER_MAP     = $%04X\n"
            "TI_BORDER_TILES   = %d\n"
            "TI_BORDER_COLORS  = %d\n"
            "TI_BORDER_UP      = %d\n"
            % (PM.TI_VRAM, PM.TI_MAP, len(ti_tiles), len(ti_colors),
               ti_top))
        # The End Game screen, whole: see tools/port/end_game.py. The two
        # palettes go one after the other, the "Yes" one first: the ROM picks
        # one by multiplying.
        end_tiles, end_rows, end_row0, end_palettes = slots["fin"]
        handle.write(block("end_tiles", b"".join(
            pack_tile(cell, planes=4) for cell in end_tiles)) + "\n")
        handle.write(block("end_map", b"".join(
            word.to_bytes(2, "little") for word in end_rows)) + "\n")
        handle.write(block("end_cgram", palettes_cgram(end_palettes)) + "\n")
        handle.write(block("end_ramp", bytes(end_game_mod.ramp())) + "\n")
        handle.write(
            "END_TILES   = %d\n"
            "END_ROW0    = %d\n"
            "END_ROWS    = %d\n"
            "END_ENTERS  = %d\n"
            "END_NO      = %d\n"
            "END_FRAMES = %d\n"
            "END_STEP_SONG = %d\n"
            % (len(end_tiles), end_row0, len(end_rows) // constants.COLS,
               end_game_mod.DEFAULT_CHOICE, end_game_mod.NO, end_game_mod.FADE_FRAMES,
               events.fade_step(end_game_mod.SONG_FADE_MS)))
        item_texts, item_texts_ofs = bytearray(), []

        def new_text(text):
            text = menus_mod.item_text(text, 255)
            item_texts_ofs.append((len(item_texts), len(text)))
            item_texts.extend(text.encode("ascii"))
            return len(item_texts_ofs) - 1

        for number in slots["items"]:
            item = slots["items_db"][number]
            for text in ([menus_mod.item_text(
                    item.name, menus_mod.ITEM_NAME_WIDTH)]
                    + menus_mod.split_description(item.description)):
                new_text(text)
        # Dead texts **after the item ones and before all the others**, so
        # that the battle's indices go past 255 in a one-map cartridge:
        # reproducing it for real takes the fifty-seven items of `abl`, that
        # is its twenty-nine maps and two and a half minutes of converter per
        # case. It had a sibling, `--relleno-de-mensajes`, that did the same
        # with the text block; that one went away on 2026-09-20 because the
        # push can be given by a case —see the `test-special` cartridge in the
        # project file— and this one can't, because what shifts isn't a text
        # but an index.
        #
        # **They go here and not at the start, which is where they were until
        # 2026-09-20.** An item's name isn't named through a table but by the
        # computation `3k` —`3k + 1` and `3k + 2` are its two description
        # lines, see `text_write`—, so a dead text before the first one
        # shifts every item and the ROM ends up drawing the dead ones, which
        # measure zero: the battle's "Use Item" list came out with the cursor
        # and the quantities and without a single name. With the padding here
        # the flag goes back to doing what it promises, which is not changing
        # a pixel.
        for _ in range(slots.get("relleno_textos") or 0):
            item_texts_ofs.append((0, 0))
        # And the fixed ones, behind: the parameters and the equipment slots,
        # and the name of each actor that can join the party. See screens.py.
        P = screens_mod
        B = battle_mod
        db = slots["db"]
        param_text = [new_text(t[:P.EQ_PARAM_VALUE - 1])
                      for t in db.term_params]
        slot_text = [new_text(t[:P.EQ_SLOT_TERM_WIDTH])
                     for t in db.term_equipment]
        actor_text = {a: new_text(db.actors[a].name)
                      for a in slots["actores"]}
        # The shop's: the eleven messages of each of the three sets, two lines
        # each —`split_description`, as in screens.py—, and "Owned Items",
        # "Equipped Items" and the currency.
        shop_text = None
        for names_in_game in range(3):
            term = P.shop_terms(db, names_in_game)
            for name, _term in P.TI_TERMS:
                lines = menus_mod.split_description(term[name])
                # Outside the main one, the message goes in a one-line window:
                # `ti_message` writes only the first.
                if lines[1] and name not in ("saludo", "resaludo"):
                    raise SystemExit(
                        "the shop message %r, of set %d, takes two "
                        "lines and its window has one"
                        % (term[name], names_in_game))
                for line in lines:
                    t = new_text(line)
                    if shop_text is None:
                        shop_text = t
        owned_text = new_text(P.lcf_term(db, P.TI_TERM_OWNED))
        carried_text = new_text(P.lcf_term(db, P.TI_TERM_CARRIED))
        currency_text = new_text(db.term_gold)
        # And the battle's: the fifteen LDB terms the screen uses —in the order
        # of `rules.BATTLE_TERMS`, which is the one the ROM indexes— and the
        # name of each enemy some troop of the cartridge brings. The three
        # commands go **already trimmed**, by `screens.command_text`: the
        # LDB brings them with leading spaces and that would shift the text of
        # their column.
        battle_term = rules.battle_terms(db)
        battle_text = None
        victory = P.victory_lines(battle_term["victory"])
        if len(victory) > P.BA_VICTORY_TERM_MAX:
            raise SystemExit("the victory term takes %d lines and "
                             "the window leaves it %d: %r"
                             % (len(victory), P.BA_VICTORY_TERM_MAX, victory))
        for name, _term in rules.BATTLE_TERMS:
            text = battle_term[name]
            if name in ("attack", "defend", "escape"):
                text = P.command_text(text)
            if name == "victory":
                text = victory[0]
            t = new_text(text)
            if battle_text is None:
                battle_text = t
        # And the line for a fallen one an item revived: the dead state's
        # `message_recovery`, which goes stuck to the name —"Core has
        # revived!"—. It isn't a term but a piece of the state's data, so it
        # goes separately and with its own index. See `ba_message`.
        revived_text = new_text(P.revived_text(db))
        # The second line of the victory, empty if it fits in one: it goes
        # separately so as not to shift the indices of `BATTLE_TERMS`.
        victory2_text = new_text((victory + [""])[1])
        rom_enemies = sorted({e for number in troops
                              if number in db.troops
                              for e in db.troops[number].members})
        enemy_text = {e: new_text(menus_mod.item_text(
            db.enemies[e].name, P.BA_NAME_WIDTH)) for e in rom_enemies}
        # And the skills': the ones some actor that can join the party knows,
        # **at their LDB level** —see `battle.skills_of`—, sorted by
        # number, which is the order the menu puts them in. With the intro's
        # party they are seven: 129, 130, 131, 143, 144, 146 and 150.
        #
        # **All the ones they can end up knowing**, and not only the LDB's: a
        # `ChangeSkills` teaches the actor what the learning table doesn't
        # have, and since 2026-09-21 that shows in battle. They are those of
        # their pairs in `events.SKILL_SLOT` that the battle knows how
        # to offer.
        #
        # And the ones some enemy of the cartridge's troops uses, since
        # 2026-09-27: `ShortCircuit`, from the ones at the recycling plant. See
        # `battle.actions_of_enemy`.
        rom_actions = {e: B.actions_of_enemy(db, e) for e in rom_enemies}
        rom_skills = sorted(
            {h for (a, h) in events.SKILL_SLOT
             if a in slots["actores"] and B.skill_usable(db.skills[h])}
            | {skill.id for values in rom_actions.values()
               for _r, skill, _ef in values if skill is not None})
        skill_text = {h: new_text(menus_mod.item_text(
            db.skills[h].name, P.BA_SKILL_NAME_WIDTH))
            for h in rom_skills}
        skill_desc_text = {h: new_text(menus_mod.item_text(
            db.skills[h].description, P.BA_SKILL_DESC_WIDTH))
            for h in rom_skills}
        # And the **whole** name of the ones learned on leveling up, which is
        # what "<skill> acquired!" says at the victory: the list's is cut to
        # its column, and some of these the battle doesn't know how to offer
        # —Lurk In Shadows, Arden's— and aren't in the list. See
        # `skill_pair_learns_txt`.
        taught = {h for (a, h) in events.SKILL_SLOT
                  if a in slots["actores"] and a in db.actors
                  and B.level_learned(db, a, h)
                  > X.initial_level(db.actors[a])}
        whole_skill_text = {
            h: new_text(menus_mod.item_text(db.skills[h].name, 255))
            for h in sorted(taught)}
        # The two lines RM2k says when using it: `using_message1` goes after
        # the name of the one using it and `using_message2` alone, on the line
        # below. `GetSkillFirstStartMessage2k` and its sibling.
        skill_msg1_text = {h: new_text(db.skills[h].using_message1)
                           for h in rom_skills}
        skill_msg2_text = {h: new_text(db.skills[h].using_message2)
                           for h in rom_skills}
        # And what each actor's command is called: `Game_Actor::GetSkillName`,
        # that is its `skill_name` —"AgentTrain", "Telepathy", "Slicing"— and
        # not the LDB's `command_skill`. It goes trimmed like the other four
        # commands.
        skill_command_text = {a: new_text(P.command_text(
            B.skill_command_name(db, a))) for a in slots["actores"]}
        handle.write(block("item_texts", bytes(item_texts) or b"\x00")
                     + "\n")
        if len(slot_blocks) > 255:
            raise SystemExit("the slots screen has %d blocks and the "
                             "tables that name them are one byte"
                             % len(slot_blocks))
        # The tables that name them **don't go here**: the ROM reads them with
        # `lda slot_block_lo, x`, which addresses the data bank, so they
        # have to live in bank 0 together with the code. They are emitted
        # further down, in the TABLES segment.
        #
        # The palette goes padded up to the TITLE_MENU_CGRAM entries, which
        # is what the ROM uploads at once: if the text uses fewer colors, the
        # DMA would read whatever follows in the cartridge.
        colors = []
        for palette in slots["paletas"]:
            palette = list(palette)
            colors += palette + [(0, 0, 0)] * (constants.MENU_CGRAM
                                               - len(palette))
        handle.write(block("slot_cgram",
                           b"".join(cgram_word(c).to_bytes(2, "little")
                                    for c in colors)) + "\n")

        handle.write('\n.segment "TABLES"\n')
        # The cell blocks of the slots screen are named by pointers, and the
        # three tables go in bank 0 because the ROM reads them with
        # `lda slot_block_lo, x`. The same for `slot_vram`, which says
        # which tilemap address each row goes to: the computation comes from
        # the same geometry that drew the text and that is why it lives in a
        # single place.
        for field, prefix in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write("slot_block_%s:\n       .byte %s\n"
                         % (field, ", ".join(prefix + e
                                             for e in slot_blocks)))
        row_of = [SLOT_MAP + (menus_mod.SLOT_Y
                              + n * menus_mod.SLOT_STEP)
                  // constants.CELL * 32 for n in range(SLOTS)]
        handle.write("slot_vram:\n      .word %s\n" % ", ".join(
            str(v) for v in row_of))
        # Where the faces go —four entries per slot, so that the index is the
        # slot times four plus the place, without multiplying by three— and
        # the leader's name.
        handle.write("slot_face_vram:\n      .word %s\n" % ", ".join(
            str(row_of[n] + menus_mod.FACE_COL
                + place * menus_mod.FACE_STEP if place < menus_mod.FACES_MAX
                else 0)
            for n in range(SLOTS) for place in range(4)))
        handle.write("slot_name_vram:\n        .word %s\n" % ", ".join(
            str(row_of[n] + menus_mod.NAME_ROW * 32
                + menus_mod.NAME_COL) for n in range(SLOTS)))
        n_actors = max(list(face_block) + list(slots["actores"])
                       + [-1]) + 1
        handle.write("slot_face_block:\n       .byte %s\n" % (", ".join(
            str(face_block.get(actor, 0xFF))
            for actor in range(n_actors)) or "$FF"))
        # The pause menu: its blocks, and where each thing goes in the
        # tilemap, in words. The geometry is `menus.py`'s and comes from
        # there.
        T = menus_mod
        from port import font as font_mod

        def vram_cell(row, col):
            return SLOT_MAP + row * 32 + col

        option_rows = [(T.MENU_OPT_Y + n * T.MENU_OPT_STEP)
                       // constants.CELL for n in range(T.MENU_OPTIONS)]
        handle.write(
            "MENU_OPTIONS      = %d\n"
            "MENU_SAVE         = %d\n"
            "MENU_END          = %d\n"
            "MENU_BLK_OPTION   = %d\n"
            "MENU_BLK_CURRENCY = %d\n"
            "MENU_BLK_ROW      = %d\n"
            "MENU_OPT_COLS     = %d\n"
            "MENU_CURRENCY_COLS = %d\n"
            "MENU_CURRENCY_VRAM = %d\n"
            "MENU_ACTOR_COLS   = %d\n"
            "MENU_ACTOR_ROWS   = %d\n"
            "MENU_ROWS_PARTY   = %d\n"
            "MENU_ACTORS_N     = %d\n"
            "MENU_HP_DIGITS    = %d\n"
            "MENU_HP_OFS       = %d\n"
            "MENU_FACE_CELLS   = %d\n"
            "MENU_NAME_COLS    = %d\n"
            "MENU_NAME_OFS = %d\n"
            "MENU_LEVEL_OFS    = %d\n"
            "MENU_MAX_DIGITS   = %d\n"
            "MENU_MAX_OFS      = %d\n"
            % (T.MENU_OPTIONS, T.MENU_SAVE, T.MENU_END, menu_option_block,
               menu_currency_block, menu_row_block,
               T.MENU_OPT_COLS, T.MENU_CURRENCY_COLS,
               vram_cell(T.MENU_GOLD_Y // constants.CELL, T.MENU_CURRENCY_COL),
               T.MENU_ACTOR_COLS, T.MENU_ACTOR_ROWS, T.MENU_PARTY_ROWS,
               n_actors,
               # And how many cells from the first of the actor's block the
               # hundreds of its HP fall, which is what `menu_hp_write`
               # adds to `menu_row_vram`.
               T.MENU_HP_DIGITS,
               T.MENU_HP_ROW * 32 + T.MENU_HP_COL - T.MENU_ACTOR_COL,
               # The face goes in the top-left corner of the row —that is why
               # it carries no offset— and the three strips the ROM composes,
               # each in its own.
               T.FACE_CELLS, T.MENU_NAME_COLS,
               T.MENU_NAME_ROW * 32 + T.MENU_NAME_COL - T.MENU_ACTOR_COL,
               T.MENU_LEVEL_ROW * 32 + T.MENU_LEVEL_COL - T.MENU_ACTOR_COL,
               T.MENU_MAX_DIGITS,
               T.MENU_HP_ROW * 32 + T.MENU_MAX_COL - T.MENU_ACTOR_COL))
        # Which commands do something: 1 yes, 0 no. The save one also checks
        # the permission, in the ROM.
        handle.write("menu_done:\n     .byte %s\n" % ", ".join(
            "1" if n in T.MENU_DONE else "0"
            for n in range(T.MENU_OPTIONS)))
        handle.write("menu_option_vram:\n    .word %s\n" % ", ".join(
            str(vram_cell(f, T.MENU_OPT_COL)) for f in option_rows))
        handle.write("menu_cursor_vram:\n    .word %s\n" % ", ".join(
            str(vram_cell(f, T.MENU_CURSOR_COL)) for f in option_rows))
        handle.write("menu_row_vram:\n     .word %s\n" % ", ".join(
            str(vram_cell(r * T.MENU_ACTOR_ROWS, T.MENU_ACTOR_COL))
            for r in range(T.MENU_PARTY_ROWS)))
        # The cursor's two cells, top and bottom: the ROM writes them one word
        # at a time.
        handle.write("menu_cursor_cells:\n     .word %s\n" % ", ".join(
            "$%04X" % entry(c, False, False, priority=1)
            for c in menu["cursor"]))
        # And what the screen composes on the fly, which goes **outside bank
        # 0**: it is read with `lda f:`, and it is almost a thousand bytes the
        # code's bank would miss. The glyphs are indexed by character —from
        # ITEM_FIRST_CHAR, like those of the item screen— and the letters
        # this cartridge doesn't use stay in the empty cell: nobody asks for
        # them, and a complete table is indexed without subtracting anything
        # else.
        handle.write('.segment "RODATA"\n')
        empty = "$%04X, $%04X" % (entry(0, False, False),
                                  entry(0, False, False))
        handle.write(".block %d\nslot_glyph_cells:\n        .word %s\n"
                     % (menus_mod.ITEM_CHARS * 4, ", ".join(
                         ", ".join("$%04X" % entry(c, False, False,
                                                   priority=1)
                                   for c in menu["glifos"][letter])
                         if letter in menu["glifos"] else empty
                         for letter in map(
                             chr, range(menus_mod.ITEM_FIRST_CHAR,
                                        menus_mod.ITEM_FIRST_CHAR
                                        + menus_mod.ITEM_CHARS)))))
        # The experience line, which the ROM draws with sprites: see
        # `MENU_EXP_X` in menus.py. The term is four tiles —two wide, top and
        # bottom— and the digits come from `slot_glyph_cells`.
        handle.write(".block %d\nmenu_exp_finished:\n    .word %s\n" % (
            2 * len(menu["exp_termino"]), ", ".join(
                "$%04X" % entry(c, False, False)
                for c in menu["exp_termino"])))
        # The actor choice: its windows on BG1 —see `TARGET_WINDOWS` in
        # menus.py—. A single tilemap, the one with an item, and the bar only
        # in the rectangle that changes: see `menus.compact_target`. And
        # the name of each medicine on two lines, in ASCII, with a table of
        # one byte per `k` that says which one it is —$FF if it isn't a
        # medicine—: only medicines open this screen.
        obj_tiles, obj_colors, obj_maps = slots["objetivo"]
        (obj_map, obj_bars, obj_row0, obj_rows, obj_col0, obj_cols,
         obj_erase_rows, obj_erase_cols) = T.compact_target(obj_maps)
        handle.write(block("target_tiles", b"".join(
            pack_tile(cell, planes=8) for cell in obj_tiles)) + "\n")
        handle.write(block("target_map", b"".join(
            word.to_bytes(2, "little") for word in obj_map)) + "\n")
        handle.write(block("target_bars", b"".join(
            word.to_bytes(2, "little") for bar in obj_bars
            for word in bar)) + "\n")
        handle.write(block("target_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little") for c in obj_colors)) + "\n")
        medicines = [n for n in slots["items"]
                     if slots["items_db"][n].type == lcf.ITEM_TYPE_MEDICINE]
        if len(medicines) > 255:
            raise SystemExit("%d medicines don't fit in `target_name`"
                             % len(medicines))
        handle.write(block("target_name", bytes(
            medicines.index(n) if n in medicines else 0xFF
            for n in slots["items"])) + "\n")
        handle.write(block("target_names", b"".join(
            "".join(T.name_in_lines(slots["items_db"][n].name))
            .encode("ascii", "replace") for n in medicines)) + "\n")
        handle.write(
            "TARGET_VRAM       = $%04X\n"
            "TARGET_MAP        = $%04X\n"
            "TARGET_TILES      = %d\n"
            "TARGET_CGRAM      = %d\n"
            "TARGET_COLORS     = %d\n"
            "TARGET_NAME_WIDTH = %d\n"
            "TARGET_NAME_VRAM = %d\n"
            "TARGET_COUNT_VRAM = %d\n"
            "TARGET_BAR_ROW0 = %d\n"
            "TARGET_BAR_ROWS = %d\n"
            "TARGET_BAR_COL0 = %d\n"
            "TARGET_BAR_COLS = %d\n"
            "TARGET_ERASE_ROWS = %d\n"
            "TARGET_ERASE_COLS = %d\n"
            % (T.TARGET_VRAM, T.TARGET_MAP, len(obj_tiles),
               T.TARGET_CGRAM, len(obj_colors), T.TARGET_NAME_WIDTH,
               vram_cell(T.TARGET_NAME_ROW, T.TARGET_NAME_COL),
               vram_cell(T.TARGET_COUNT_ROW, T.TARGET_COUNT_COL),
               obj_row0, obj_rows, obj_col0, obj_cols, obj_erase_rows,
               obj_erase_cols))
        handle.write(
            "MENU_EXP_X        = %d\n"
            "MENU_EXP_NUM_X    = %d\n"
            "MENU_EXP_Y        = %d\n"
            "MENU_EXP_STEP     = %d\n"
            "MENU_EXP_DIGITS   = %d\n"
            "MENU_EXP_LETTERS  = %d\n"
            "MENU_ACTOR_HEIGHT = %d\n"
            % (T.MENU_EXP_X,
               T.MENU_EXP_X + T.MENU_EXP_NUM_DX - T.GLYPH_DX,
               T.MENU_EXP_Y - T.GLYPH_DY, font_mod.WIDTH, T.MENU_EXP_DIGITS,
               T.MENU_EXP_LETTERS, T.MENU_ACTOR_ROWS * constants.CELL))
        # Each actor's text, in ASCII: the name —with trailing spaces, which
        # are what erase whatever was there—, the two digits of the level and
        # max HP after its bar. **The three together, in one row per actor**,
        # so the ROM has a single address to compute and three offsets that
        # are constants.
        db_slots = slots["db"]
        if (SLOT_TEXT_LEVEL < menus_mod.MENU_NAME_COLS
                or SLOT_TEXT_MAX + menus_mod.MENU_MAX_DIGITS
                > SLOT_TEXT_WIDTH):
            raise SystemExit("the actor's three strips don't fit in the %d "
                             "bytes of its row" % SLOT_TEXT_WIDTH)
        strip = bytearray()
        for a in range(n_actors):
            row = (menus_mod.name_text(db_slots, a)
                   .ljust(SLOT_TEXT_LEVEL)
                   + menus_mod.level_text(db_slots, a)
                   + menus_mod.max_text(db_slots, a))
            strip += row.ljust(SLOT_TEXT_WIDTH).encode("ascii")
        handle.write(".block %d\nslot_actor_text:\n        .byte %s\n"
                     % (max(1, len(strip)),
                        ", ".join(str(b) for b in strip) or "0"))
        handle.write('.segment "TABLES"\n')
        # The item screen. `item_k` goes from the RM2k number to its place in
        # the ROM's tables, $FF if this ROM doesn't know it; the rest is per
        # place. `item_use`: bit 0 if it goes in white and A does something,
        # bit 1 if using it spends one —the switch ones with uses—, bit 2 if it
        # opens the actor choice —the medicines—, bit 3 if it is a two-handed
        # weapon. The texts go three per item —the name and the two lines of
        # the description—: text `t` is `3k + field`.
        items = slots["items"]
        db_items = slots["items_db"]
        if len(items) > 255:
            raise SystemExit("%d items don't fit in one-byte tables"
                             % len(items))
        k_of = {number: k for k, number in enumerate(items)}
        handle.write(
            "ITEMS_ROM         = %d\n"
            "ITEMS_TILES       = %d\n"
            "ITEMS_CGRAM_N     = %d\n"
            "ITEM_ROWS         = %d\n"
            "ITEM_CURSOR_COL   = %d\n"
            "ITEM_NAME_COL     = %d\n"
            "ITEM_TWO_POINTS_COL = %d\n"
            "ITEM_DIGITS_COL   = %d\n"
            "ITEM_DESC_VRAM    = %d\n"
            "ITEM_DESC_COL     = %d\n"
            "ITEM_FIRST_CHAR = %d\n"
            "ITEM_GLYPHS_GRAY  = %d\n"
            "ITEM_BORDER_VRAM  = $%04X\n"
            "ITEM_BORDER_TILES = %d\n"
            "ITEM_BORDER_MAP   = $%04X\n"
            "ITEM_BORDER_CGRAM = %d\n"
            "ITEM_BORDER_COLORS = %d\n"
            "ITEM_BORDER_ROWS  = %d\n"
            "ITEM_BORDER_LIST  = %d\n"
            % (len(items), len(slots["items_tiles"]),
               menus_mod.ITEM_UP * constants.MENU_CGRAM,
               T.ITEM_ROWS, T.ITEM_CURSOR_COL, T.ITEM_NAME_COL,
               T.ITEM_COLON_COL, T.ITEM_DIGITS_COL,
               vram_cell(T.ITEM_DESC_Y // constants.CELL, T.ITEM_DESC_COL),
               T.ITEM_DESC_COL,
               T.ITEM_FIRST_CHAR, T.ITEM_CHARS * 4,
               SLOT_VRAM
               + items_border_first(len(slots["items_tiles"])) * 32,
               len(border_tiles), T.ITEM_BORDER_MAP, T.ITEM_BORDER_CGRAM,
               len(border_colors), constants.ROWS,
               T.ITEM_LIST_Y // constants.CELL))

        def bytes_asm(label, values, fmt="%d", declare=False):
            if declare:
                handle.write(".block %d\n" % max(1, len(values)))
            handle.write("%s:\n    .byte %s\n" % (label, ", ".join(
                fmt % v for v in values) or "$FF"))

        def words_asm(label, values, fmt="%d", declare=False):
            if declare:
                handle.write(".block %d\n" % max(2, 2 * len(values)))
            handle.write("%s:\n    .word %s\n" % (label, ", ".join(
                fmt % v for v in values) or "0"))

        # `item_k` goes outside bank 0 —it is read with `lda f:item_k, x`—:
        # the code's bank filled up with the audio package.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_k", [k_of.get(n, 0xFF)
                             for n in range(events.ITEMS_N)],
                  declare=True)
        handle.write('.segment "TABLES"\n')
        words_asm("item_id", items)
        bytes_asm("item_use", [
            (1 if T.item_usable(db_items[n]) else 0)
            | (2 if T.item_usable(db_items[n])
               and not T.item_needs_actor(db_items[n])
               and db_items[n].uses else 0)
            | (4 if T.item_needs_actor(db_items[n]) else 0)
            | (8 if db_items[n].two_handed else 0)
            for n in items])
        # `item_switch` goes outside bank 0 —it is read with
        # `lda f:item_switch, x`, only once per item used— because the random
        # encounters pushed it over by 34 bytes on 2026-09-13. It is 124: the
        # largest of the tables that are read with X and aren't in any
        # per-frame loop.
        handle.write('.segment "RODATA"\n')
        words_asm("item_switch", [db_items[n].switch_id for n in items],
                  declare=True)
        handle.write('.segment "TABLES"\n')
        # What each item does in a battle: whether it goes in the list that is
        # offered and how much it heals. The rule for which ones go in is
        # `battle.item_usable_in_battle`, that is `Game_Party::IsItemUsable`
        # with the battle open plus what this port knows how to do; the
        # computation of how much it heals is
        # `Game_BattleAlgorithm::Item::vExecute`.
        # **Outside bank 0**, like `item_k` and for the same reason: with the
        # maps of `abl` the code area ended up at 32775 of 32704 when putting
        # them here. The battle reads them with `lda f:item_battle, x`.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_battle", [
            1 if B.item_usable_in_battle(db_items[n]) else 0 for n in items],
            declare=True)
        bytes_asm("item_heal_rate", [db_items[n].recover_hp_rate
                                     for n in items], declare=True)
        words_asm("item_heal_hp", [min(db_items[n].recover_hp, 0xFFFF)
                                   for n in items], declare=True)
        # And what a medicine does outside battle, which is the whole of
        # `Game_Battler::UseItem`: the SP, like the HP, and `item_medicine`
        # with three bits —1 if it is `ko_only`, 2 if it removes the dead
        # state, which is the first of `state_set` and what revives a fallen
        # one, 4 if using it spends one, which is `uses` nonzero—. The other
        # states of `state_set` don't go: outside battle this port has no
        # states, so removing them is never useful. See `medicine_use`.
        bytes_asm("item_heal_sp_rate", [db_items[n].recover_sp_rate
                                        for n in items], declare=True)
        words_asm("item_heal_sp", [min(db_items[n].recover_sp, 0xFFFF)
                                   for n in items], declare=True)
        bytes_asm("item_medicine", [
            (1 if db_items[n].ko_only else 0)
            | (2 if db_items[n].state_set[:1] == [True] else 0)
            | (4 if db_items[n].uses else 0)
            for n in items], declare=True)
        handle.write('.segment "TABLES"\n')
        # The four text ones go **outside bank 0**, like `item_k` and for the
        # same reason: they don't fit there. With the ten maps of `abl` the
        # code area was at 32622 of 32704 —eighty-two free bytes— and the
        # `ShowPicture` picture didn't fit. They are read with
        # `lda f:item_txt_lo, x`, which costs one byte and one cycle per read
        # in thirteen places, none inside a per-frame loop.
        handle.write('.segment "RODATA"\n')
        for field, prefix in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write(".block %d\n" % max(1, len(item_texts_ofs)))
            handle.write("item_txt_%s:\n    .byte %s\n" % (field, ", ".join(
                "%s(item_texts + %d)" % (prefix, ofs)
                for ofs, _ in item_texts_ofs) or "0"))
        bytes_asm("item_txt_n", [n for _, n in item_texts_ofs],
                  declare=True)
        handle.write('.segment "TABLES"\n')
        words_asm("item_row_vram", [
            vram_cell(T.ITEM_LIST_Y // constants.CELL + 2 * f, 0)
            for f in range(T.ITEM_ROWS)])
        # The two cells of each character, top and bottom: first the 95 in
        # white, then in gray and then in the "goes up" color. Character `c`
        # in variant `g` is at
        # `g * ITEM_GLYPHS_GRAY + (c - ITEM_FIRST_CHAR) * 4`.
        # --- the equipment ---
        # Per known item: its type, what it adds —attack, defense, spirit,
        # agility, signed— and who can equip it, one bit per actor. Per actor,
        # from 0 to the LDB's last: its level parameters and its initial
        # equipment, which the ROM copies to `FAR_EQUIPMENT` on reset. And where
        # each thing goes in the screen's buffer, in bytes: row * 64 + col * 2.
        n_actors = max(db.actors) + 1

        def pos(row, col):
            return row * 64 + col * 2

        bytes_asm("item_type", [db_items[n].type for n in items])
        handle.write('.segment "RODATA"\n')     # same: see `item_txt_lo`
        words_asm("item_points", [p & 0xFFFF for n in items
                                  for p in db_items[n].points],
                  declare=True)
        # And what attacking with each one costs: the weapons' `sp_cost`, zero
        # for the rest —`battle.weapon_sp_of`—. The battle reads it once per
        # actor when it is set up.
        bytes_asm("item_sp", [db_items[n].sp_cost
                              if db_items[n].type == lcf.ITEM_TYPE_WEAPON
                              else 0 for n in items], declare=True)
        # `item_actors` also goes outside bank 0 —it is read with
        # `lda f:item_actors, x`—: it is 496 bytes, the fattest ones `TABLES`
        # had left, and bank 0 overflowed. It isn't a precaution: on
        # 2026-09-13 `just demo` stopped with "el área no
        # entra: 32719 bytes en 32704" and no case of the suite saw it.
        # It is read once per item when building the equipment screen's list,
        # so the extra cycle of long addressing doesn't show.
        bytes_asm("item_actors", [
            sum(1 << b for b in range(8)
                if 8 * byte + b + 1 < n_actors
                and db_items[n].equippable_by(8 * byte + b + 1))
            for n in items for byte in range(8)], declare=True)
        # `actor_params` goes outside bank 0 —it is read with
        # `lda f:actor_params, x`, only once per equipment screen— for the same
        # reason as `item_k`: it is 488 bytes and the code's bank filled up,
        # and this time with the drawing of the battle animations.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_params", [
            (rules.param_of(db.actors[a], k)
             if a in db.actors else 0) & 0xFFFF
            for a in range(n_actors)
            for k in ("attack", "defense", "spirit", "agility")],
            declare=True)
        handle.write('.segment "TABLES"\n')
        handle.write('\n.segment "RODATA"\n')
        handle.write(".block %d\n"
                     % (2 * n_actors * constants.EQUIPMENT_SLOTS))
        handle.write("equipment_initial:\n .word %s\n" % ", ".join(
            str(db.actors[a].initial_equipment[r] if a in db.actors else 0)
            for a in range(n_actors)
            for r in range(constants.EQUIPMENT_SLOTS)))
        handle.write('\n.segment "TABLES"\n')
        words_asm("actor_txt", [actor_text.get(a, 0xFFFF)
                                for a in range(n_actors)], "$%04X")
        words_asm("eq_param_pos", [pos(f, c) for f, c in P.EQ_PARAMS])
        words_asm("item_price", [db_items[n].price for n in items])
        handle.write(
            "TI_TEXT           = %d\n"
            "TI_TEXT_HAVE      = %d\n"
            "TI_TEXT_CARRIED   = %d\n"
            "TI_TEXT_CURRENCY  = %d\n"
            "TI_SECOND         = %d\n"
            "TI_MAIN_MSG_POS = %d\n"
            "TI_MSG_POS        = %d\n"
            "TI_COMMAND_POS0   = %d\n"
            "TI_GOLD_POS       = %d\n"
            "TI_HAVE_POS       = %d\n"
            "TI_HAVE_NUM       = %d\n"
            "TI_CARRIED_POS    = %d\n"
            "TI_CARRIED_NUM    = %d\n"
            "TI_LIST_POS0      = %d\n"
            "TI_LIST_ROWS_BUY = %d\n"
            "TI_LIST_ROWS_SALE = %d\n"
            "TI_NAME           = %d\n"
            "TI_PRICE          = %d\n"
            "TI_COUNT_POS      = %d\n"
            "TI_COUNT_X_POS    = %d\n"
            "TI_COUNT_NUM_POS = %d\n"
            "TI_TOTAL_POS      = %d\n"
            "TI_RED            = %d\n"
            % (shop_text, owned_text, carried_text, currency_text,
               P.TI_SECOND,
               pos(P.TI_MAIN_MSG_ROW, T.ITEM_DESC_COL),
               pos(P.TI_MSG_ROW, T.ITEM_DESC_COL),
               pos(P.TI_MAIN_MSG_ROW + 2, P.TI_COMMAND_COL),
               pos(P.TI_GOLD_ROW, P.TI_GOLD_COL),
               pos(P.TI_OWNED_ROW, P.TI_STATUS_COL),
               pos(P.TI_OWNED_ROW, P.TI_STATUS_NUM),
               pos(P.TI_CARRIED_ROW, P.TI_STATUS_COL),
               pos(P.TI_CARRIED_ROW, P.TI_STATUS_NUM),
               pos(P.TI_LIST_ROW0, 0), P.TI_LIST_ROWS_BUY,
               P.TI_LIST_ROWS_SALE, P.TI_LIST_COL * 2,
               P.TI_PRICE_COL * 2,
               pos(P.TI_COUNT_ROW, P.TI_LIST_COL),
               pos(P.TI_COUNT_ROW, P.TI_COUNT_X_COL),
               pos(P.TI_COUNT_ROW, P.TI_COUNT_COL),
               pos(P.TI_TOTAL_ROW, P.TI_GOLD_COL), T.ITEM_RED))
        # `eq_bar` counts the rows of the slots and those of the list from
        # the same one: they are the same window.
        if P.EQ_LIST_ROW0 != P.EQ_SLOT_ROW0:
            raise SystemExit("the equipment list starts at row %d and the "
                             "slots at %d" % (P.EQ_LIST_ROW0,
                                              P.EQ_SLOT_ROW0))
        handle.write(
            "ACTORS_N          = %d\n"
            "SLOTS_EQUIPMENT   = %d\n"
            "EQ_TEXT_PARAM     = %d\n"
            "EQ_TEXT_SLOT      = %d\n"
            "EQ_ACTOR_POS      = %d\n"
            "EQ_BAR_ROW0       = %d\n"
            "EQ_BORDER_TEXT    = %d\n"
            "EQ_BORDER_TEXT_N  = %d\n"
            "EQ_PARAM_VALUE    = %d\n"
            "EQ_PARAM_ARROW    = %d\n"
            "EQ_SLOT_POS0      = %d\n"
            "EQ_SLOT_TERM      = %d\n"
            "EQ_SLOT_NAME      = %d\n"
            "EQ_SLOT_WIDTH     = %d\n"
            "EQ_LIST_POS0      = %d\n"
            "EQ_LIST_ROWS      = %d\n"
            "EQ_LIST_NAME      = %d\n"
            "SCR_TWO_POINTS    = %d\n"
            "SCR_DESC_POS      = %d\n"
            % (n_actors, constants.EQUIPMENT_SLOTS, param_text[0],
               slot_text[0],
               pos(P.EQ_ACTOR_ROW, P.EQ_ACTOR_COL), P.EQ_SLOT_ROW0,
               P.EQ_SLOT_ROW0,
               max(constants.EQUIPMENT_SLOTS, P.EQ_LIST_ROWS) * 2,
               P.EQ_PARAM_VALUE * 2,
               P.EQ_PARAM_ARROW * 2, pos(P.EQ_SLOT_ROW0, 0),
               P.EQ_SLOT_TERM_COL * 2, P.EQ_SLOT_NAME_COL * 2,
               P.EQ_SLOT_NAME_WIDTH, pos(P.EQ_LIST_ROW0, 0),
               P.EQ_LIST_ROWS,
               P.EQ_LIST_NAME_COL * 2,
               T.ITEM_COLON_COL * 2,
               pos(T.ITEM_DESC_Y // constants.CELL, T.ITEM_DESC_COL)))
        # --- the battle ---
        # Each actor's max HP at its level, by actor number. They go separately
        # from `actor_params`, which carries the four the equipment screen
        # shows; the equipment doesn't touch the HP, as in RM2k.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_hpmax", [
            (rules.param_of(db.actors[a], "maxhp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(n_actors)], declare=True)
        # And the SP, which are state since 2026-09-13 for the same reason as
        # the HP: the skills spend them. See `hp_initial_set` in
        # tools/runtime/bank1.s.
        words_asm("actor_spmax", [
            (rules.param_of(db.actors[a], "maxsp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(n_actors)], declare=True)
        handle.write(experience_asm(db, slots["actores"], n_actors))
        # --- the skills ---
        #
        # One row per skill the cartridge carries, in the order of
        # `rom_skills`, which is by RM2k number. The fields are those of
        # `lcf.Skill` and the computations that use them are in `battle.py`:
        # `skill_effect` is `Algo::CalcSkillEffect` and `cost_of` is
        # `CalcSkillCost`.
        #
        # They go **outside bank 0** and declared with `.block`, like
        # everything the battle reads with `lda f:`: the code's bank is full,
        # and a table split between two banks would be read wrong from the
        # middle on.
        skill_place = {h: k for k, h in enumerate(rom_skills)}
        # That all the ones that reach here are of the kind the battle knows
        # how to offer is guaranteed by `battle.skill_usable`, which is
        # the filter `skills_of` applies on both sides. It is checked
        # again in case they were ever emitted from somewhere else: a
        # multi-target scope or a three-digit cost would be drawn wrong
        # silently.
        for h in rom_skills:
            if not B.skill_usable(db.skills[h]):
                raise SystemExit(
                    "skill %d —type %d, scope %d, %d SP— isn't one of the "
                    "ones this battle knows how to offer" % (h, db.skills[h].type,
                                                             db.skills[h].scope,
                                                             db.skills[h].sp_cost))
        words_asm("skill_id", rom_skills, declare=True)
        words_asm("skill_txt", [skill_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_desc", [skill_desc_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_msg1", [skill_msg1_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_msg2", [skill_msg2_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_power", [db.skills[h].power for h in rom_skills],
                  declare=True)
        words_asm("skill_switch", [db.skills[h].switch_id
                                 for h in rom_skills], declare=True)
        bytes_asm("skill_sp", [db.skills[h].sp_cost for h in rom_skills],
                  declare=True)
        # The type: 0 is `normal` and 3 is `switch`, which is the one that
        # turns on a switch and does nothing else. See `Skill::vExecute`.
        bytes_asm("skill_type", [db.skills[h].type for h in rom_skills],
                  declare=True)
        bytes_asm("skill_phys", [db.skills[h].physical_rate
                              for h in rom_skills], declare=True)
        bytes_asm("skill_mag", [db.skills[h].magical_rate
                              for h in rom_skills], declare=True)
        bytes_asm("skill_var", [db.skills[h].variance
                              for h in rom_skills], declare=True)
        bytes_asm("skill_hit", [db.skills[h].hit for h in rom_skills],
                  declare=True)
        # What it touches, one bit per thing, in the order `Skill::vExecute`
        # looks at them —which is the order it consumes randomness in and
        # that is why it matters—: HP, SP, attack, defense, spirit and
        # agility. Bit 6 says whether it targets enemies
        # —`Algo::SkillTargetsEnemies`— and 7 whether it ignores defense.
        bytes_asm("skill_affects", [
            (1 if db.skills[h].affect_hp else 0)
            | (2 if db.skills[h].affect_sp else 0)
            | (4 if db.skills[h].affect_attack else 0)
            | (8 if db.skills[h].affect_defense else 0)
            | (16 if db.skills[h].affect_spirit else 0)
            | (32 if db.skills[h].affect_agility else 0)
            | (64 if db.skills[h].targets_enemies else 0)
            | (128 if db.skills[h].ignore_defense else 0)
            for h in rom_skills], "$%02X", declare=True)
        # And the scope as is, `rpg::Skill::Scope`: 0 one enemy, 1 all, 2
        # oneself, 3 one ally, 4 the whole party. Since 2026-09-27 the battle
        # knows all five: see `battle.skill_targets`.
        bytes_asm("skill_scope", [db.skills[h].scope for h in rom_skills],
                  declare=True)
        # The parallel common events that only look at the equipment,
        # compiled: the ROM runs them when closing the menu if their switch is
        # on. For each one, where its switch is in the bitmap —byte and mask—
        # and its code. See `events.PARTY_COMMON_EVENTS`.
        party_ones = sorted(events.PARTY_COMMON_EVENTS.items())
        handle.write("COMEQ_N = %d\n" % len(party_ones))
        words_asm("comeq_byte", [sw >> 3 for sw, _n in party_ones],
                  declare=True)
        bytes_asm("comeq_mask", ["$%02X" % (1 << (sw & 7))
                                    for sw, _n in party_ones], "%s",
                  declare=True)
        words_asm("comeq_code", [".loword(common_equipment_%d)" % n
                                for _sw, n in party_ones], "%s",
                  declare=True)
        # The bank goes as a word —its high byte isn't read— so that the ROM
        # indexes it with the same X as `comeq_code`.
        words_asm("comeq_bank", ["^common_equipment_%d" % n
                                  for _sw, n in party_ones], "%s",
                  declare=True)
        for _sw, n in party_ones:
            handle.write(block("common_equipment_%d" % n,
                               events.compile_party_common_event(n)) + "\n")
        # And what each actor knows, which since 2026-09-21 is state: one bit
        # per (actor, skill) pair in `FAR_SKILL`, with the slots of
        # `events.SKILL_SLOT`. It is answered by branch 4 of
        # `ConditionalBranch` —which already brings the slot in the bytecode—
        # and by the battle's list, which walks the actor's pairs: where they
        # start —`skill_pair_start`, as words because there are more than 255—,
        # how many there are, and the `k` of each one in the `hab_*` tables
        # above, or $FF if this one doesn't know how to offer it. Since an
        # actor's pairs go together and by number, the list comes out sorted
        # like `LearnSkill`'s.
        #
        # The bits start with `rules.learned_skills`, which is what the LDB
        # says at its initial level: `initial_skills_set` copies them on reset.
        pairs = sorted(events.SKILL_SLOT.items(), key=lambda x: x[1])
        skill_pair_start, skill_pair_n = [], []
        for a in range(n_actors):
            own_ones = [r for (actor, _s), r in pairs if actor == a]
            skill_pair_start.append(own_ones[0] if own_ones else 0)
            skill_pair_n.append(len(own_ones))
            if own_ones and own_ones != list(range(own_ones[0], own_ones[0] + len(own_ones))):
                raise SystemExit("the skill pairs of actor %d aren't "
                                 "contiguous" % a)
        if max(skill_pair_n, default=0) > 255:
            raise SystemExit("an actor has more than 255 skill pairs and "
                             "`skill_pair_n` is one byte")
        skill_bytes = max(1, (len(pairs) + 7) // 8)
        knows = {a: set(rules.learned_skills(db, a)) for a in db.actors}
        bits = [0] * skill_bytes
        for (a, h), r in pairs:
            if h in knows.get(a, ()):
                bits[r >> 3] |= 1 << (r & 7)
        handle.write("; How many bytes the skill bits take in `FAR_SKILL`.\n"
                     "SKILL_BYTES = %d\n" % skill_bytes)
        handle.write("; The signature of the save format: see `SRAM_SIGNATURE`.\n"
                     "GAME_SIGNATURE = $%04X\n" % save_signature(
                         pairs, experience_slots(db, slots["actores"]),
                         n_actors))
        words_asm("skill_pair_init", skill_pair_start, declare=True)
        bytes_asm("skill_pair_n", skill_pair_n, declare=True)
        bytes_asm("skill_pair_k", [skill_place.get(h, 0xFF)
                                if a in slots["actores"] else 0xFF
                                for (a, h), _r in pairs], declare=True)
        bytes_asm("skill_initial", bits, "$%02X", declare=True)
        # And at which level the LDB's learning table teaches each pair, or 0
        # if it doesn't —the ones only a `ChangeSkills` gives—: on leveling
        # up, `exp_add` sets the bits of the pairs whose level it just
        # passed, which is `LearnLevelSkills(old_level + 1, new_level)`.
        bytes_asm("skill_pair_level", [B.level_learned(db, a, h)
                                    if a in db.actors else 0
                                    for (a, h), _r in pairs], declare=True)
        # And the name the victory tells it by —"<skill> acquired!"—, or $FFFF
        # if it isn't learned by leveling up from the starting one.
        words_asm("skill_pair_learns_txt", [
            whole_skill_text[h] if a in slots["actores"]
            and B.level_learned(db, a, h) > 0 and h in whole_skill_text
            else 0xFFFF for (a, h), _r in pairs], "$%04X", declare=True)
        # 254 and not 256: `eacc_skill` uses $FF for the attack and
        # `ba_enemy_action` answers $FE when it has none left.
        if len(rom_skills) > 254:
            raise SystemExit("the cartridge's skills are %d and `skill_pair_k` "
                             "is one byte" % len(rom_skills))
        # And what each actor's skills command is called in the menu.
        words_asm("actor_skill_txt", [skill_command_text.get(a, 0xFFFF)
                                    for a in range(n_actors)], "$%04X",
                  declare=True)
        # The troops some battle of the cartridge asks for, and the enemies
        # that form them. The bytecode carries the troop's **RM2k number**, so
        # `troop_id` is what the ROM looks up; the list being only that of the
        # used troops doesn't change a byte of any page. See
        # `events.Troops`.
        used = [n for n in troops if n in db.troops]
        place_of = {e: k for k, e in enumerate(rom_enemies)}
        members, starts = [], []
        for number in used:
            values = db.troops[number].members[:constants.ENEMIES_MAX]
            starts.append(len(members))
            members += [place_of[e] for e in values]
        if len(members) > 255 or len(used) > 255:
            raise SystemExit("the cartridge's troops don't fit in one-byte "
                             "tables: %d troops, %d members"
                             % (len(used), len(members)))
        words_asm("troop_id", used, declare=True)
        # The experience beating each one gives, already added up: see
        # `experience.troop_exp`. It goes outside bank 0, like
        # everything here, because it is read once per battle.
        troop_exp = [X.troop_exp(db, n) for n in used]
        for n, exp in zip(used, troop_exp):
            if exp > 0xFFFF:
                raise SystemExit("troop %d gives %d experience and the ROM "
                                 "adds it in sixteen bits" % (n, exp))
        words_asm("troop_exp", troop_exp, declare=True)
        # And the gold, the same: `battle.troop_gold`. The victory tells
        # it with `ba_vic_number`, which reaches five digits.
        troop_gold = [B.troop_gold(db, n) for n in used]
        for n, gold in zip(used, troop_gold):
            if gold > 0xFFFF:
                raise SystemExit("troop %d gives %d gold and the ROM adds it "
                                 "in sixteen bits" % (n, gold))
        words_asm("troop_gold", troop_gold, declare=True)
        # What the victory writes has to fit on its line: the ROM builds it
        # with a number or a name in the middle and doesn't split it.
        P.collect_victory(
            battle_term, max(troop_exp, default=0),
            [db.actors[a].name for a in slots["actores"] if a in db.actors],
            [db.skills[h].name for h in sorted(taught)],
            max(troop_gold, default=0),
            [db_items[i].name for i in sorted({db.enemies[e].drop_id
                                               for e in rom_enemies}
                                              - {0})])
        bytes_asm("troop_init", starts, declare=True)
        # Which members of each troop start **hidden** —the troop's
        # `invisible`—, one bit per place: a page with `ShowHiddenMonster`
        # makes them appear. It is the Rat King, who calls his rats. See
        # `BAF_HIDDEN`.
        bytes_asm("troop_hidden", [
            sum(1 << k for k, hidden in enumerate(
                db.troops[n].hidden[:constants.ENEMIES_MAX]) if hidden)
            for n in used], "$%02X", declare=True)
        bytes_asm("troop_n",
                  [len(db.troops[n].members[:constants.ENEMIES_MAX])
                   for n in used], declare=True)
        bytes_asm("troop_member", members, declare=True)
        # And the event pages of each troop, in LDB order —which is the order
        # `ScheduleNextPage` tries them in—, without the ones that didn't
        # compile: skipping them doesn't change the order of the others. Per
        # troop, where they start and how many there are; per page, its
        # trigger and where its code is inside `troop_code`, which
        # deduplicates them. See `events.TroopPages` and `ba_page_test`
        # in tools/runtime/battle_troop.s.
        #
        # **The small tables go to bank 1, `FAR`; the two big blocks —the code
        # and the messages—, to RODATA.** Until 2026-09-27 all four went to
        # bank 1, because with them in RODATA the `names_in_game` cartridge went over
        # 4 MB (measured on 2026-09-21); that cartridge no longer exists,
        # `release` is around 71%, and in bank 1 the two blocks were almost
        # eleven KB of which the battle's hand-written code didn't have even
        # four hundred bytes. Both are read with a long pointer whose bank
        # comes from `^troop_code` and `^messages_troop`, so it is enough
        # for each to fit whole in one bank, which is what `block` asks for.
        pt = troop_pages or events.TroopPages()
        entries, page_start, page_n = [], [], []
        for number in used:
            theirs = pt.per_troop.get(number, [])
            page_start.append(len(entries))
            page_n.append(len(theirs))
            entries += theirs
        if max(page_n, default=0) > events.TROOP_PAGES_MAX:
            raise SystemExit("a troop brings %d pages and the battle tracks %d"
                             % (max(page_n), events.TROOP_PAGES_MAX))
        handle.write('.segment "FAR"\n')
        words_asm("troop_page_init", page_start)
        bytes_asm("troop_page_n", page_n)
        bytes_asm("tpage_flags", [d.flags for d, _ofs in entries], "$%02X")
        words_asm("tpage_sw_a", [d.switch_a for d, _ofs in entries])
        words_asm("tpage_code", [".loword(troop_code + %d)" % ofs
                               for _d, ofs in entries], "%s")
        # The three for `switch_b` and the variable only if some page uses
        # them: the characters' 32 systems only look at `switch_a`, and with
        # none the ROM never reads them —the bit in `tpage_flags` is zero—, so
        # the label is enough. The turn and the HP have no table: they go in
        # front of the code, see `events.troop_header`.
        for name, field, bit in (
                ("tpage_sw_b", "switch_b", events.TROOP_TRIGGER_SWITCH_B),
                ("tpage_var", "ranura", events.TROOP_TRIGGER_VARIABLE),
                ("tpage_value", "valor", events.TROOP_TRIGGER_VARIABLE)):
            uses_it = any(d.flags & bit for d, _ofs in entries)
            words_asm(name, [getattr(d, field) & 0xFFFF
                             for d, _ofs in entries] if uses_it else [])
        handle.write('.segment "RODATA"\n')
        handle.write(block("troop_code", bytes(pt.bodies) or b"\x00")
                     + "\n")
        handle.write(block("messages_troop", pt.messages.bytes())
                     + "\n")
        # And the random encounters, which also talk about troops by their
        # RM2k number. They go here outside bank 0 —they are read with
        # `lda f:tabla, x`— because eighty-five bytes were left there and this
        # is about two hundred. See `rom_encounters` and
        # `tools/runtime/encounters.s`.
        enc = encounters or {"por_mapa": [0xFF] * len(maps), "registros": [],
                             "zonas": [], "tropas": []}
        bytes_asm("enc_map", enc["por_mapa"], declare=True)
        words_asm("enc_base", [r["base"] for r in enc["registros"]],
                  declare=True)
        thresholds = []
        for r in enc["registros"]:
            # Seven thresholds and one of padding: with eight the record's
            # index is a shift and not a multiplication. See ENC_STRIDE.
            thresholds += list(r["umbrales"]) + [0xFF]
        bytes_asm("enc_threshold_n", thresholds, declare=True)
        bytes_asm("enc_zone_init", [r["zona_ini"] for r in enc["registros"]],
                  declare=True)
        bytes_asm("enc_zone_n", [r["zona_n"] for r in enc["registros"]],
                  declare=True)
        for k, label in enumerate(("enc_left", "enc_arr", "enc_right",
                                   "enc_down")):
            words_asm(label, [z["rect"][k] for z in enc["zonas"]],
                      declare=True)
        bytes_asm("enc_troop_init", [z["troop_init"] for z in enc["zonas"]],
                  declare=True)
        bytes_asm("enc_troop_n", [z["troop_n"] for z in enc["zonas"]],
                  declare=True)
        words_asm("enc_troop", enc["tropas"], declare=True)
        words_asm("enemy_hp", [db.enemies[e].max_hp for e in rom_enemies],
                  declare=True)
        words_asm("enemy_atk", [db.enemies[e].attack for e in rom_enemies],
                  declare=True)
        words_asm("enemy_def", [db.enemies[e].defense for e in rom_enemies],
                  declare=True)
        words_asm("enemy_agi", [db.enemies[e].agility for e in rom_enemies],
                  declare=True)
        # The spirit and the SP: `CalcSkillEffect` asks for them, subtracting
        # `magical_rate * spi_del_blanco / 80` from the effect. Until
        # 2026-09-13 nobody read them because no computation of the battle
        # used them.
        words_asm("enemy_spi", [db.enemies[e].spirit for e in rom_enemies],
                  declare=True)
        words_asm("enemy_sp", [db.enemies[e].max_sp for e in rom_enemies],
                  declare=True)
        bytes_asm("enemy_hit", [db.enemies[e].hit for e in rom_enemies],
                  declare=True)
        # The critical hit, already as a whole percentage:
        # `CalcCriticalHitChance` computes it as `1 / critical_hit_chance`
        # times a hundred and truncates it.
        bytes_asm("enemy_crit", [
            (100 // (db.enemies[e].critical_hit_chance or 30))
            if db.enemies[e].critical_hit else 0 for e in rom_enemies],
            declare=True)
        words_asm("enemy_txt", [enemy_text[e] for e in rom_enemies],
                  declare=True)
        # Each one's experience and gold, which the victory subtracts from the
        # troop's for each enemy that stayed hidden: see `ba_no_hidden`.
        words_asm("enemy_exp", [db.enemies[e].exp for e in rom_enemies],
                  declare=True)
        words_asm("enemy_gold", [db.enemies[e].gold for e in rom_enemies],
                  declare=True)
        # What it drops on dying: the LDB item, or 0 if it drops nothing, and
        # the chance as a percentage. See `ba_vic_drop` and
        # `battle.roll_drops`. Every item that can be dropped is in
        # `items`: see `drop_items`, which adds it.
        for e in rom_enemies:
            if db.enemies[e].drop_id and db.enemies[e].drop_id not in k_of:
                raise SystemExit("enemy %d drops item %d and the "
                                 "cartridge doesn't carry it"
                                 % (e, db.enemies[e].drop_id))
        words_asm("enemy_drop", [db.enemies[e].drop_id
                                    for e in rom_enemies], declare=True)
        bytes_asm("enemy_drop_pct", [db.enemies[e].drop_prob
                                        for e in rom_enemies], declare=True)
        # What each enemy can do on its turn: its list from
        # `battle.actions_of_enemy`, contiguous in `eacc_*` —where it
        # starts and how many there are—. Per action, the skill as a `k` of the
        # `hab_*` tables or $FF for the attack, and its `rating` with bit 7 set
        # if it isn't `effective`: it counts for the maximum and then weighs
        # zero. See `ba_enemy_action` in tools/runtime/battle.s.
        eacc_start, eacc_skill, eacc_weight = [], [], []
        for e in rom_enemies:
            if len(rom_actions[e]) > B.ACTIONS_MAX:
                raise SystemExit("enemy %d brings %d actions and the ROM "
                                 "weighs %d: see `battle.ACTIONS_MAX`"
                                 % (e, len(rom_actions[e]), B.ACTIONS_MAX))
            eacc_start.append(len(eacc_skill))
            for rating, skill, effective in rom_actions[e]:
                if not 0 < rating < 0x80:
                    raise SystemExit("enemy %d brings an action with rating "
                                     "%d and the ROM carries it in seven bits"
                                     % (e, rating))
                eacc_skill.append(0xFF if skill is None
                                  else skill_place[skill.id])
                eacc_weight.append(rating | (0 if effective else 0x80))
        if len(eacc_skill) > 255:
            raise SystemExit("the actions of the cartridge's enemies are %d "
                             "and `enemy_acc_init` is one byte"
                             % len(eacc_skill))
        handle.write("ACTIONS_MAX = %d\n" % B.ACTIONS_MAX)
        bytes_asm("enemy_acc_init", eacc_start, declare=True)
        bytes_asm("enemy_acc_n", [len(rom_actions[e]) for e in rom_enemies],
                  declare=True)
        bytes_asm("eacc_skill", eacc_skill, declare=True)
        bytes_asm("eacc_weight", eacc_weight, declare=True)
        # And the battle scene: the backdrops and the battlers separately.
        # `used` is the same order as `troop_id`, which is what
        # `scene_troop_backdrop` indexes, and that of `troop_member`.
        handle.write(scenes_asm(scenes or {"fondos": [], "battlers": [],
                                           "battler_de": {},
                                           "tropa_fondo": {},
                                           "mapa_fondo": [0xFF] * len(maps)},
                                used, db))
        handle.write('.segment "TABLES"\n')
        # The product of the hit computation has to fit in sixteen bits:
        # (100 - hit rate) times the sum of both agilities. With the minimum
        # hit rate of 70 that is 30 times 1998, and the agility cap is guarded
        # by `BA_AGI_CAP`; an enemy with a lower hit rate would overflow it
        # without warning, so it stops here.
        # `recover_hp_rate * hp_max` has to fit in sixteen bits: the ROM does
        # it with the hardware multiplier, which gives a word. With the
        # percentage capped at 100 that is hp_max of up to 655, and this
        # game's actors are around 40. A fatter actor would overflow without
        # warning, so it stops here.
        for a in range(n_actors):
            max_levels = (rules.param_of(db.actors[a], "maxhp")
                          if a in db.actors else 0)
            if max_levels * 100 > 0xFFFF:
                raise SystemExit(
                    "actor %d has %d HP and the ROM's healing computation "
                    "is sized for 655" % (a, max_levels))
        for e in rom_enemies:
            if db.enemies[e].hit < 70:
                raise SystemExit("enemy %d has a hit rate of %d, and the ROM's "
                                 "hit computation is sized for 70"
                                 % (e, db.enemies[e].hit))
        handle.write(
            "TROOPS_N          = %d\n"
            "BATTLE_SEED       = $%04X\n"
            "BA_TXT_BASE       = %d\n"
            "BA_ENEMY_POS0     = %d\n"
            "BA_PARTY_POS0     = %d\n"
            "BA_MSG_POS1       = %d\n"
            "BA_MSG_POS2       = %d\n"
            "BA_ROW_BYTES      = %d\n"
            "BA_CURSOR_DX      = %d\n"
            "BA_NAME_DX        = %d\n"
            "BA_NAME_WIDTH     = %d\n"
            "BA_HP_DX          = %d\n"
            "BA_HP_NUM_DX      = %d\n"
            "BA_HP_ENEMIES     = %d\n"
            "BA_BAR_DX         = %d\n"
            "BA_HPMAX_DX       = %d\n"
            "BA_MSG_DX         = %d\n"
            "BA_PAGE_MSG_POS0  = %d\n"
            "BA_PAGE_MSG_DX    = %d\n"
            "BA_PAGE_MSG_WIDTH = %d\n"
            "TROOP_PAGE_MAX    = %d\n"
            "TPAGE_SWITCH_A    = $%02X\n"
            "TPAGE_SWITCH_B    = $%02X\n"
            "TPAGE_VARIABLE    = $%02X\n"
            "TPAGE_TURN        = $%02X\n"
            "TPAGE_ENEMY       = $%02X\n"
            "TPAGE_ACTOR       = $%02X\n"
            "TPAGE_WITH_HEADER = $%02X\n"
            "TPAGE_HEADER      = %d\n"
            % (len(used), B.BATTLE_SEED, battle_text,
               pos(P.BA_ENEMY_ROW0, 0), pos(P.BA_PARTY_ROW0, 0),
               pos(P.BA_MSG_ROW1, 0), pos(P.BA_MSG_ROW2, 0), 2 * 64,
               P.BA_CURSOR_COL * 2, P.BA_NAME_COL * 2, P.BA_NAME_WIDTH,
               P.BA_HP_COL * 2, P.BA_HP_NUM * 2, int(enemy_hp),
               P.BA_BAR_COL * 2,
               P.BA_HP_MAX_NUM * 2, 1 * 2,
               pos(P.BA_PAGE_MSG_ROW0, 0), P.BA_PAGE_MSG_COL * 2,
               P.BA_PAGE_MSG_WIDTH, events.TROOP_PAGES_MAX,
               events.TROOP_TRIGGER_SWITCH_A, events.TROOP_TRIGGER_SWITCH_B,
               events.TROOP_TRIGGER_VARIABLE, events.TROOP_TRIGGER_TURN,
               events.TROOP_TRIGGER_ENEMY, events.TROOP_TRIGGER_ACTOR,
               events.TROOP_WITH_HEADER, events.TROOP_HEADER_BYTES))
        # The audio: the battle song, the victory one and the five sound
        # effects, with the index they got from `Songs`. $FF and $FFFF mean
        # "the LDB has it turned off", which is the case of `battle_se` in
        # this game. Who sounds at which moment is in `events.BATTLE_AUDIO`,
        # taken from easyrpg-player; only the numbers travel here.
        audio = battle_audio or {}
        # The battle's audio package goes after the maps' ones, so its index
        # is how many maps the ROM carries. It is emitted here and checked by
        # the music section, which is the one that builds the list.
        #
        # Sixteen bits, and "there is none" is $FFFF: with the 328 maps of the
        # whole game the index doesn't fit in a byte, same as `map_current`.
        # See `battle_audio_load`.
        handle.write(
            "BA_SONG           = $%02X\n"
            "BA_SONG_END       = $%02X\n"
            "BA_PACKAGE        = $%04X\n"
            % (audio.get("battle_music", 0xFF),
               audio.get("battle_end_music", 0xFF),
               len(maps) if audio else 0xFFFF))
        for name, constant in (("dodge_se", "BA_SE_MISS"),
                               ("enemy_attack_se", "BA_SE_ATTACK"),
                               ("enemy_damaged_se", "BA_SE_DAMAGE_ENEMY"),
                               ("actor_damaged_se", "BA_SE_DAMAGE_ACTOR"),
                               ("enemy_death_se", "BA_SE_DEATH"),
                               ("escape_se", "BA_SE_FLEE"),
                               ("item_se", "BA_SE_ITEM")):
            handle.write("%-18s= $%04X\n"
                         % (constant, audio.get(name, 0xFFFF)))
        handle.write("BA_TXT_VICTORY2   = %d\n"
                     "BA_VIC_FINISHED_N = %d\n"
                     % (victory2_text, len(victory)))
        # The terms, by their place in `rules.BATTLE_TERMS`.
        for k, (name, _term) in enumerate(rules.BATTLE_TERMS):
            handle.write("BA_TXT_%-11s= BA_TXT_BASE + %d\n"
                         % (name.upper(), k))
        handle.write("BA_TXT_REVIVED    = %d\n" % revived_text)
        # The menu's five commands, with what the ROM needs of each one: which
        # line and which column it goes in, which term names it and whether it
        # always goes in gray. They go in tables and not in a computation
        # because since 2026-09-13 **they aren't three in a row on one line**:
        # they are the five of ABL's menu spread over two. See
        # `screens.BA_COMMANDS`.
        handle.write("BA_COMMANDS_N     = %d\n" % len(P.BA_COMMANDS))
        handle.write("BA_ITEM_COUNT_DX = %d\n" % (P.BA_ITEM_COUNT_COL * 2))
        handle.write("BA_COMMAND_USE    = %d\n" % P.BA_COMMAND_USE)
        handle.write("BA_COMMAND_ESCAPE = %d\n" % P.BA_COMMAND_ESCAPE)
        handle.write("BA_COMMAND_ATTACK = %d\n" % P.BA_COMMAND_ATTACK)
        handle.write("BA_COMMAND_DEFEND = %d\n" % P.BA_COMMAND_DEFEND)
        handle.write("BA_COMMAND_SKILL= %d\n" % P.BA_COMMAND_SKILL)
        # The skills screen: two columns with the name and the cost, and the
        # description of the one under the cursor at the very top. The
        # geometry comes from `screens.py`, like the item list's.
        handle.write(
            "SKILLS_N          = %d\n"
            "BA_SKILL_DESC_POS = %d\n"
            "BA_SKILL_POS0     = %d\n"
            "BA_SKILL_ROWS     = %d\n"
            "BA_SKILL_COLUMNS  = %d\n"
            "BA_SKILL_COLUMN_DX = %d\n"
            "BA_SKILL_NAME_DX  = %d\n"
            "BA_SKILL_NAME_WIDTH = %d\n"
            "BA_SKILL_DASH_DX  = %d\n"
            "BA_SKILL_COST_DX  = %d\n"
            "BA_SKILL_COST_DIGITS = %d\n"
            % (len(rom_skills),
               pos(P.BA_SKILL_DESC_ROW, P.BA_SKILL_DESC_COL),
               pos(P.BA_SKILL_ROW0, 0), P.BA_SKILL_ROWS, P.BA_SKILL_COLUMNS,
               P.BA_SKILL_COLUMN_DX * 2, P.BA_SKILL_NAME_COL * 2,
               P.BA_SKILL_NAME_WIDTH, P.BA_SKILL_DASH_COL * 2,
               P.BA_SKILL_COST_COL * 2, P.BA_SKILL_COST_DIGITS))
        handle.write('.segment "RODATA"\n')
        words_asm("ba_command_row", [
            pos((P.BA_MSG_ROW1, P.BA_MSG_ROW2)[f], 0)
            for _n, f, _c in P.BA_COMMANDS], declare=True)
        words_asm("ba_command_dx", [c * 2 for _n, _f, c in P.BA_COMMANDS],
                  declare=True)
        # **Two bytes.** A text index doesn't fit in one: with the 29 maps of
        # `abl` the battle's start at 273, and the one-byte table that was here
        # until 2026-09-14 emitted them anyway —`.byte 273`— for the assembler
        # to truncate them without saying anything.
        words_asm("ba_command_txt", [
            battle_text + [n for n, _c in rules.BATTLE_TERMS].index(name)
            for name, _f, _c in P.BA_COMMANDS], declare=True)
        bytes_asm("ba_command_gray", [
            1 if k in P.BA_COMMAND_UNDONE else 0
            for k in range(len(P.BA_COMMANDS))], declare=True)
        handle.write('.segment "TABLES"\n')

        glyphs = slots["items_glifos"]
        # Outside bank 0, like `item_k`: it is read with `lda f:`.
        handle.write('.segment "RODATA"\n')
        # **With the priority bit set**, since the battle draws the scene on
        # BG1: in mode 3 the PPU order leaves BG1 at priority 0 **above** BG2
        # at priority 0, so without this the backdrop would cover the letters.
        # On the other screens that use these glyphs —items, equipment, shop—
        # BG1 is off and the bit doesn't change a pixel, and in the empty
        # cells neither, because their pixels are transparent. The "goes up"
        # variant brings only the digits; the other letters fall on the white
        # ones, which nobody asks for in that color but that way the table is
        # indexed the same as the others.
        words_asm("item_glyph_cells", [
            entry(cell, False, False, priority=1)
            for gray in (T.ITEM_WHITE, T.ITEM_GRAY, T.ITEM_UP,
                         T.ITEM_RED)
            for n in range(T.ITEM_CHARS)
            for cell in glyphs[gray].get(
                chr(T.ITEM_FIRST_CHAR + n),
                glyphs[T.ITEM_WHITE][chr(T.ITEM_FIRST_CHAR + n)])],
            "$%04X", declare=True)
        handle.write('.segment "TABLES"\n')
        handle.write("\n")
        # `font_color` goes in bank 0 and not with the rest of the window:
        # the ROM reads it with `lda font_color, y`, and that mode addresses
        # the data bank. With it in RODATA it read garbage, and the text came
        # out black.
        handle.write(block("font_color", bytes(window["color"]),
                           fit=False) + "\n")
        handle.write("party_initial:\n    .byte %s\n\n"
                     % ",".join("%d" % a for a in initial_party) or "0")
        handle.write(sine_table() + "\n")
        # How many frames a character stays still after a step and after a
        # turn, per route frequency: RM2k's stop counter, in two tables of
        # nine to index with the frequency as is. They come from
        # `events.wait_after_step` and `wait_after_turn`. 0 and 1 aren't
        # compiled; they carry zero so that the table has no holes.
        handle.write("route_after_step:\n  .byte %s\n" % ",".join(
            "%d" % (events.wait_after_step(f)
                    if f >= events.ROUTE_FREQUENCY_MIN else 0)
            for f in range(events.ROUTE_FREQUENCY + 1)))
        handle.write("route_after_turn:\n  .byte %s\n\n" % ",".join(
            "%d" % (events.wait_after_turn(f)
                    if f >= events.ROUTE_FREQUENCY_MIN else 0)
            for f in range(events.ROUTE_FREQUENCY + 1)))
        handle.write(map_table(maps, labels))
        handle.write("\n\n")
        # After the map one, which already left the segment in RODATA.
        handle.write(anim_table(maps))
        handle.write("\n")
    return materials.report()


# How much each opcode takes, to walk the bytecode without running it. The
# variable-length ones go with None and are measured separately.
# The bytecode walk lives in events.py, with the length table: there was a
# copy here and the one there went stale without anyone seeing it.
walk_code = events.walk_code


def map_order(args):
    """The ROM's maps, in table order and without repeats.

    It is in a function and not written three times because **the order is
    the contract**: a compiled teleport stores the index in this table, not
    the RM2k id. Two lists built differently would take the same bytecode to
    different maps.
    """
    return [args.map_id] + [m for m in (args.maps or []) if m != args.map_id]


def test_graphics(argument):
    """The (CharSet, index) pairs of `--test-graphic`, or () if none."""
    return tuple((charset, int(index)) for charset, index in argument or ())


def save_signature(pairs, slots_exp, n_actors):
    """Sixteen bits that change when **what each byte of the saved game
    means** changes, so that the ROM rejects one from another build.

    The size is guarded by the ROM on its own —`SAVE_BYTES`, which comes
    from the same constants—; this covers what the size doesn't see: which
    RM2k variable goes in each slot, which actor each skill pair and each
    experience slot belongs to. Two builds can carry the same number of
    variables and slot 5 be a different variable in each; then the save would
    load with the same length and everything shifted.

    It is the assignments and not the whole ROM on purpose: two builds whose
    save reads the same have to be able to share it, even if everything else
    changes.
    """
    shape = {
        "variables": sorted(events.VARIABLE_SLOT.items(), key=lambda x: x[1]),
        "items": events.ITEMS_N,
        "switches": SWITCH_BYTES,
        "actores": n_actors,
        "habilidades": [[a, h, r] for (a, h), r in pairs],
        "experiencia": slots_exp,
    }
    return zlib.crc32(json.dumps(shape).encode()) & 0xFFFF


def variables_n():
    """How many variable slots the ROM carries: at least one —a zero length
    would close the save table— and up to 256, which is what fits between
    `FAR_VARIABLES` and `FAR_ITEMS`."""
    n = max(1, len(events.VARIABLE_SLOT))
    if n > 256:
        sys.exit("%d variables don't fit in far RAM: FAR_ITEMS is "
                 "512 bytes from FAR_VARIABLES" % n)
    return n


def sine_table():
    """The sine the screen shake reads by index, for the bank."""
    out = ["; The sine at scale 127, for the screen shake: it is the same",
           "; list `SENO_SACUDIDA` builds in events.py.",
           ";",
           "; It goes outside bank 0 —`lda f:sine_shake, x`, one read per",
           "; shake frame— for the same reason as `item_k`: it is 256 bytes",
           "; and the code's bank filled up.",
           '.segment "RODATA"',
           ".block 256",
           "sine_shake:"]
    values = events.SHAKE_SINE
    for i in range(0, 256, 16):
        out.append("    .byte " + ",".join("$%02X" % (v & 0xFF)
                                            for v in values[i:i + 16]))
    # And back to bank 0: what follows —`route_after_step` and company— is read
    # with absolute indexed addressing and has to stay here.
    out.append('.segment "TABLES"')
    return "\n".join(out) + "\n"


def flags_parser():
    """The converter's flags. Separate from `main` for whoever needs to read a
    command line without converting anything."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Mandatory, but without `required`: `test_cases` reads the flags of
    # each `--case` again with this same parser, and there it doesn't go.
    # `main` enforces it.
    parser.add_argument("--map-id", type=int, default=None,
                        help="the boot map, which goes first in the "
                             "table. Mandatory and with no default: it "
                             "belongs to the game, and its project file "
                             "declares it")
    project.add_argument(parser)
    # No default, and no `required` for the same reason as `--map-id`:
    # `environment` enforces them when they are read.
    environment.add_arguments(parser, "game_dir", "rtp_dir", "soundfont",
                              "cache")
    parser.add_argument("-o", "--output",
                        default=os.path.join(project.build(), "inc", "mapdata.inc"))
    parser.add_argument("--msu",
                        help="where to write the .msu with the data the\n"
                             "MSU-1 serves to the ROM: next to the .sfc and\n"
                             "with its name, so the emulator finds it.\n"
                             "Without this, datos.msu next to --output")
    parser.add_argument("--text-padding", type=int, default=0,
                        help="dead texts after the item ones, so that\n"
                             "the battle's indices go past 255 without\n"
                             "building a twenty-nine-map cartridge. It\n"
                             "doesn't change a pixel, and that is why they\n"
                             "don't go first: item k's name is text 3k")
    parser.add_argument("--no-title", action="store_true",
                        help="without the game's title screen and its "
                             "start and load menu: the ROM boots straight "
                             "into the map. It is what the regression "
                             "suite's cartridges ask for: the title screen "
                             "would add frames to the boot, and the cases "
                             "compare frames counted from reset.")
    parser.add_argument("--measure-headroom", type=float, metavar="HEADROOM",
                        help="the same headroom for every song, instead of "
                             "the volume ceiling table: it is what "
                             "`tools/audio/ceilings.py` builds the ROM where it "
                             "measures each song's peak with. It goes to "
                             "`rm2k-snes-audio` as the job's "
                             "`measuring_headroom`")
    parser.add_argument("--enemy-hp", action="store_true",
                        help="the battle shows the enemies' HP, which RM2k "
                             "never shows: for debugging. It is asked for by "
                             "`[debug] enemy_hp` of the project file")
    parser.add_argument("--no-timer", action="store_true",
                        help="the timer digits —eleven glyphs of the System "
                             "image at the end of the sprite bank, which "
                             "share a palette with a character— only in the "
                             "maps where a case that uses them runs, and not "
                             "in all. It is what the suite's cartridges ask "
                             "for: see `args.timer_en`")
    parser.add_argument("--test-graphic", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDEX"),
                        help="puts this graphic in the sprite bank of the\n"
                             "maps where some case runs, so that the test\n"
                             "page can change someone's graphic with\n"
                             "command 34 or with ChangeSpriteAssociation.\n"
                             "It can be repeated. No page that compiles\n"
                             "today changes graphic, so without this\n"
                             "nothing runs that path")
    parser.add_argument("--test-encounters", type=int, default=None,
                        metavar="STEPS",
                        help="every how many steps there is a random "
                             "encounter, for every map of the cartridge. "
                             "Without this the game tree's value applies, "
                             "which goes from 25 to 85 steps; 0 turns them off")
    parser.add_argument("--hero-above", action="store_true",
                        help="the hero at object priority 2, above the "
                             "layer that should cover it. It is the only "
                             "way to exercise it: the game's only above "
                             "event never gets to step on the upper layer")
    parser.add_argument("--party", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="the party it starts with, by actor ids. The "
                             "hero's graphic is the first one's, which is how "
                             "RM2k decides it. By default, the database's: "
                             "this game starts with actor 10, DummyHero, whose "
                             "sprite is an empty cell on purpose")
    parser.add_argument("--test-commands", default=None,
                        metavar="FILE",
                        help="this case's test page, as the command list of "
                             "an RM2k page in Ditto's JSON —see "
                             "rom/pruebas/casos/—. It is compiled by the same "
                             "path as a page of the game, with the context of "
                             "the map where it runs: that of its Teleport if "
                             "it starts with one, and otherwise the boot "
                             "map's")
    parser.add_argument("--charset", default=None,
                        help="force the hero's CharSet; by default it comes "
                             "from the party's first, which is how RM2k "
                             "decides it")
    parser.add_argument("--charset-index", type=int, default=None,
                        help="which of the CharSet's 8 characters")
    parser.add_argument("--maps", nargs="+", type=int, metavar="ID",
                        help="other maps to put in the same ROM. The one "
                             "from --map-id goes first in the table")
    parser.add_argument("--start-index", type=int, default=0, metavar="N",
                        help="which table index the ROM boots at. It serves "
                             "to test a map other than the first, which is "
                             "the only case where the record's offset isn't "
                             "zero")
    return parser


def main():
    project.from_command_line()
    parser = flags_parser()
    argv, stretches = split_cases(sys.argv[1:])
    args = parser.parse_args(argv)
    if args.map_id is None:
        parser.error("--map-id is missing, the boot map")
    environment.from_arguments(args, "game_dir", "rtp_dir", "soundfont",
                               "cache")
    args.game_dir = environment.game()
    args.cases = test_cases(parser, args, stretches)
    order = map_order(args)
    if not 0 <= args.start_index < len(order):
        sys.exit("--start-index %d but there are %d maps" % (args.start_index, len(order)))
    for case in args.cases:
        case.run_map = case_map(case, order, args.start_index)
    file_commands = case_commands(args)
    # Which maps carry the timer digits, which cost a sprite palette.
    # Normally, all: it is what the game asks for, where the countdown starts
    # in one map and is seen in the following ones. With `--no-timer`, the
    # maps where a case that touches it runs: until step 9e one was enough for
    # every map of the cartridge to carry them, and in the single cartridge of
    # 9f that took the palette away from every map —measured, fifteen goldens
    # moved—. A map without digits doesn't draw them: `TIMER_BASE` at zero,
    # see `timer_oam`.
    args.timer_maps = set(order) if not args.no_timer else {
        case.run_map for case in args.cases
        if any(cmd.code == events.TIMER_OPERATION for cmd in case.commands)}

    renderer = Renderer(args.game_dir)

    # The hero's graphic comes from the party, not from here. In RM2k the
    # first of the list gives it, and this game starts with actor 10
    # —'DummyHero', which is Chubby2[2]—. Until now there was a hand-set
    # default that gave Future1[0], that is another character's sprite.
    # --charset stays to force it by hand when needed.
    party = args.party if args.party else renderer.database.party
    if args.charset is None:
        args.charset, table_index = renderer.database.leader(party)
        if args.charset_index is None:
            args.charset_index = table_index
    if args.charset_index is None:
        args.charset_index = 0

    # The leader candidates are computed with all the ROM's maps together,
    # because the party is global state: a page of map A can add someone who
    # then walks around map B.
    args_game_dir[0] = args.game_dir
    every = map_order(args)
    # **The indices go before anything that compiles a page**, and
    # `possible_leaders` compiles pages. They were after, and the price was
    # concrete: without `index_variables`, no `ControlVars` compiles, so
    # `RaceController1` of map 49 —which starts with a `PlayBGM` and goes on
    # with two `ControlVars`— didn't compile **in that pass** and did in the
    # real one. The actors it adds to the party were lost: `CarRED` didn't go
    # into the map's actor table and the chase's hero was drawn **with no
    # graphic**, that is the car wasn't visible. It is the same hole that was
    # already noted for the page counts, in another place.
    #
    # The variables of the whole game, with their slot.
    extra = events.command_variables(file_commands)
    if len(args.cases) > 1:
        # The one that picks the case: see `events.CASE_VARIABLE`. With a
        # single one it isn't needed, and that way that cartridge comes out
        # the same as before `--case`.
        extra.add(events.CASE_VARIABLE)
    events.index_variables(args.game_dir, extra)
    # And the battle animations, which `ShowBattleAnimation` compiles with its
    # timeline inside: see OP_ANIMATION.
    events.index_animations(args.game_dir)
    # And the common events, which `CallEvent` compiles in place.
    events.index_common_events(args.game_dir)
    events.index_battle_audio(args.game_dir)
    # And the inn terms, which `ShowInn` builds its greeting with.
    events.index_terms(args.game_dir)
    # And the equipment and skills of each actor of the LDB: it is what the
    # two actor branches with two operands answer. **Before
    # `possible_leaders`**, which compiles pages: see its comment.
    events.index_actors(args.game_dir)
    # And the (actor, skill) pairs of the whole game, with those of the test
    # pages: it is the operand of `ChangeSkills` and of the branch that asks
    # whether it knows one, so it goes before compiling anything, same as the
    # variables.
    events.index_skills(
        args.game_dir, events.command_skill_pairs(file_commands))
    args.leaders = possible_leaders(renderer, every, party)
    # And those of the party each test page continues with, behind: the test
    # can start with it in any map of the cartridge.
    for case in args.cases:
        test_party = page_party(case, party)
        if test_party:
            for actor in possible_leaders(renderer, every, test_party):
                if actor not in args.leaders:
                    args.leaders.append(actor)
    # If some map sets rain, all of them carry the drops: see `has_rain`.
    args.with_rain = has_rain(every, file_commands)
    # How many maps of this ROM each character appears in. The palette split
    # uses it to choose who can lose a color without breaking anything: the
    # pose bank is **the whole ROM's**, so a character that is in two maps has
    # to be quantized the same in both. Quantizing it differently doesn't give
    # an ugly image but a `sys.exit` when emitting, which is what happened the
    # first time this was written: `Future1:4` dropped in one map and not in
    # the other.
    args.maps_per_character = maps_per_character(renderer, every,
                                                 args.game_dir)
    # The `ShowPicture` picture, one per ROM: see `events.Pictures`. The first
    # map of the table that shows it keeps it, which is the order `convert_map`
    # walks them in.
    args.pictures = events.Pictures(args.game_dir)
    args.pictures.map_id = None
    # And the slots `ChangeSpriteAssociation` reserves in the graphics table
    # of **all** maps, for the same reason as the picture: the graphic it gives
    # an actor crosses the teleport, so its index has to mean the same in both
    # maps. See `events.sprite_associations`.
    #
    # The test pages' ones come in through the same door: if they went by
    # `--test-graphic` they would have an index only in the maps where a
    # case runs, and what the command does —crossing the teleport— couldn't
    # be tested.
    args.associations = events.sprite_associations(
        [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
         for m in every], file_commands)

    precompute_layers(renderer, every, args)
    maps = [convert_map(renderer, map_id, args) for map_id in every]
    # The maps whose upper layer started higher than the window's palette used
    # to be reconverted here, to squeeze their background below it. With the
    # window in palette 0 there is nothing to squeeze: each map's background
    # starts at `CGRAM_RESERVED` and reaches up to its own upper layer,
    # without depending on what the other maps of the ROM need.
    # Teleports are resolved when all the maps are there: one can lead to any
    # other, so the destination index isn't known until the end.
    indices = {map_info["id"]: number for number, map_info in enumerate(maps)}

    # The blocks the map's `TileSubstitution`s are going to need, built
    # **before** compiling any page: see `Substitutions`. A map without that
    # command builds nothing and doesn't grow a byte, which is the case of the
    # game's 328 maps as of today.
    for map_info in maps:
        chipset = renderer.database.chipsets[map_info["game_map"].chipset_id]
        map_info["sustituciones"] = Substitutions(
            map_info, build_passability(chipset), chipset)
        # It hangs from the map so it reaches `events.MapEvents`, which is what
        # the compiler already passes around.
        map_info["game_map"].substitutions = map_info["sustituciones"]
        triples = substitution_triples(map_info["game_map"], args.cases,
                                       map_info["id"])
        for absent in map_info["sustituciones"].close(triples):
            # It doesn't stop the conversion: the page that asks for it
            # doesn't compile, which is what any command that can't be run
            # does. But it is said, because from outside it looks like an
            # event that does nothing.
            #
            # The two reasons a substitution can't be built, and both are
            # fixed on the data side: either the new tile isn't drawn in any
            # cell of the map —and then its 8x8s didn't go into VRAM—, or the
            # combination that would be needed carries an upper tile **without
            # the "Above" bit**, which isn't drawn on BG2 but baked into the
            # background, and then the block's two layers stop being
            # independent. See `Substitutions._bakes`.
            print("  map %d: TileSubstitution %d -> %d on the %s layer: the "
                  "block that would be needed can't be built. Either the new "
                  "tile isn't drawn in any cell of the map, or one of the two "
                  "is an upper tile without 'Above' and is baked into the "
                  "background. The page doesn't compile."
                  % (map_info["id"], absent[1], absent[2],
                     "upper" if absent[0] else "lower"))

    # The text block belongs to the whole ROM and is built while the pages
    # are compiled: each `ShowMessage` leaves its text here and takes an
    # offset, which is what goes in the bytecode.
    messages = events.Messages(step=events.MESSAGES_STEP)
    # The songs the pages' PlayBGMs ask for, numbered in the order they
    # appear. The ROM carries a single one —see `Songs`— and picks it further
    # down, when all are compiled and it is known which ones are asked for.
    songs = events.Songs()
    # And the troops the EnemyEncounters ask for. It doesn't number anything
    # —the bytecode carries the RM2k id— so it only says which enemy tables
    # have to be emitted. See `events.Troops`.
    troops = events.Troops()
    # The test pages' texts go **first**, before all the maps, and that isn't
    # aesthetic: that way their offset doesn't depend on how many texts the
    # map the ROM boots in brings nor on the order they are compiled in —the
    # first is 0—. They are stored here and the page's compilation, further
    # down, finds them stored, because the block deduplicates by content.
    for cmd, extra_lines in events.group_boxes(file_commands):
        if cmd.code == events.SHOW_MESSAGE:
            messages.add([cmd.string] + extra_lines)
    # The test pages already compiled, per case: see the second round.
    test_party = {}

    for map_info in maps:
        # The automatic events: their pages with the conditions, and the code
        # of the ones that can be run, all together in a single block.
        # One graphics registry per map: command 34 carries the index and the
        # map's `ruta_grafico` table resolves it. See `events.Graphics`.
        graphics = events.Graphics(args.associations)
        songs.current_map = maps.index(map_info)      # for its audio package
        pages = events.map_pages(map_info["game_map"], indices.get,
                                 messages, songs, graphics,
                                 args.pictures, troops)
        songs.current_map = None
        # One interpreter per event with some parallel page that compiles. The
        # ROM carries them in a fixed-cap list and **doesn't warn** if it goes
        # over —the extra ones wouldn't run and nothing would say so—, so the
        # stop goes here.
        with_parallel = {p["event"] for p in pages
                         if p["trigger"] == events.TRIGGER_PARALLEL
                         and p["codigo"]}
        if len(with_parallel) > PARALLEL_MAX:
            sys.exit("map %d has %d events with a parallel page and %d "
                     "fit: see PARALLEL_MAX"
                     % (map_info["id"], len(with_parallel), PARALLEL_MAX))
        if with_parallel:
            print("  map %d: %d event(s) with a parallel page"
                  % (map_info["id"], len(with_parallel)))
        if args.test_graphic and map_info["id"] in test_maps(args):
            for charset, index in test_graphics(args.test_graphic):
                graphics.index(charset, index)
        # **Only the map that took its tiles can show the picture.** The sprite
        # bank belongs to each map, so from another one the six objects would
        # read whatever was in those tiles. It doesn't happen today —the "1
        # year earlier" picture is shown by a single page— and that is why this
        # stops instead of choosing: the day two maps show the same one, it
        # has to be decided whether its tiles go in both, and the converter
        # can't make that decision alone.
        if (args.pictures.name is not None
                and map_info["id"] != args.pictures.map_id):
            for test_page in pages:
                code = test_page["codigo"]
                if code and any(code[i] == events.OP_PICTURE
                                for i, _c in events.walk_code(code)):
                    sys.exit(
                        "map %d: shows the picture %r and its tiles ended up in "
                        "map %d; the ROM carries it in a single one. See "
                        "`cartel_de_imagen`."
                        % (map_info["id"], args.pictures.name,
                           args.pictures.map_id))
        if graphics.pairs != map_info["graficos_de_ruta"]:
            # The two passes compiled different things. It can't happen —both
            # use `map_pages` with the same text block— and if it did,
            # the bytecode would end up pointing at the wrong table without
            # anything saying so.
            sys.exit("map %d: the two passes numbered the route graphics "
                     "differently: %s against %s"
                     % (map_info["id"], graphics.pairs, map_info["graficos_de_ruta"]))
        # The pages of the cases that run in this map, compiled with its
        # context even though they will live in the boot map: see
        # `case_map`. They are put there in the second round, when all
        # are done.
        for k, case in enumerate(args.cases):
            if case.run_map == map_info["id"]:
                test_party[k] = case_page(case, map_info, songs, graphics,
                                          messages, indices,
                                          args.pictures)
        map_info["pages"] = pages
        # And which maps outside the ROM the ones that don't compile point to.
        #
        # A `Teleport` to a map that didn't make it cuts the whole page, and a
        # page that doesn't compile does **nothing**: neither the teleport nor
        # what came before. `event` has always said so in its comment, but
        # the count above doesn't tell this reason apart from the others a
        # page falls out for, and it is the only one that is fixed from
        # outside —adding the map— and not by touching the compiler. That is
        # how the elevator page of map 2 was overlooked, which was seen
        # opening and led nowhere because it ends up jumping to map 3.
        outside_of, how_many = set(), 0
        for test_page in pages:
            if test_page["codigo"] or test_page["trigger"] not in events.TRIGGERS \
                    or test_page.get("prueba"):
                continue        # the test page doesn't come from the game
            event = map_info["game_map"].events[test_page["event"]]
            missing = {cmd.parameters[0]
                       for cmd in event.pages[test_page["pagina"]].commands
                       if cmd.code == events.TELEPORT and cmd.parameters
                       and indices.get(cmd.parameters[0]) is None}
            if missing:
                outside_of |= missing
                how_many += 1
        if outside_of:
            print("  map %d: %d of those %s because of a teleport to a map "
                  "that didn't make it into the ROM: %s"
                  % (map_info["id"], how_many,
                     "doesn't compile" if how_many == 1 else "don't compile",
                     ", ".join(str(m) for m in sorted(outside_of))))
        # Debts are warned about. A page that is accepted without doing
        # everything it asks for is a difference from the original game, and
        # keeping quiet about it is how it becomes invisible: here the command
        # and what is lost are named.
        debts = set()
        for event in map_info["game_map"].events:
            for page in event.pages:
                if page.trigger != events.TRIGGER_AUTOSTART:
                    continue
                # With the same text block as above: if it were None here, a
                # page with a text box wouldn't compile and its debt —a
                # PlayBGM, say— would go unwarned even though the ROM does run
                # it. Adding a text that is already there again doesn't grow
                # the block: the key is the content.
                if events.compile_page(page, indices.get,
                                       messages) is None:
                    continue
                debts |= set(events.page_debts(page,
                                               args.pictures))
        for cmd_code in sorted(debts):
            print("  map %d: WARNING, a page uses %s and the ROM doesn't do it; "
                  "see ACCEPTED_UNDONE in tools/port/events.py"
                  % (map_info["id"], event_codes.EVENT_CODES.get(cmd_code,
                                                                 cmd_code)))


    # The second round: with the pages of all the cases compiled, they are
    # put in the boot map and each map's block is built.
    for map_info in maps:
        pages = map_info["pages"]
        if args.cases and map_info is maps[args.start_index]:
            # The test pages, only in the map the ROM boots in. They don't come
            # from the game but from `rom/pruebas/casos/`: they exist because
            # there are interpreter paths no page of the game that compiles
            # exercises —the first was a wait—.
            #
            # It goes at **index 0**, that of the empty event `convert_map` put
            # at the start of the map: the ROM walks the events from lowest to
            # highest, and this page has to run before the game's. Until
            # 2026-09-17 it went at the first free index, at the end.
            #
            # **One page per case**, and page k asks for `CASE_VARIABLE` to
            # be at least k: see its comment. Page 0 asks for nothing, so a
            # single-case cartridge is the usual one.
            pages = pages + [{
                "event": 0, "pagina": k, "prueba": True,
                "trigger": events.TRIGGER_AUTOSTART,
                "switch_a": 0, "switch_b": 0, "actor": 0,
                "variable": ((events.variable_slot(
                    events.CASE_VARIABLE),
                    events.COMPARE_AT_LEAST, k) if k else None),
                "item": 0, "capa": 0,
                "frecuencia": events.ROUTE_FREQUENCY, "speed": 4,
                "codigo": test_party[k]} for k in range(len(args.cases))] + [{
                # And the one that turns it off: it asks for
                # `TEST_SWITCH` and has no code, so as soon as it wins,
                # the invented event no longer has an automatic page to run and
                # the first one doesn't repeat.
                "event": 0, "pagina": len(args.cases), "prueba": True,
                "trigger": events.TRIGGER_AUTOSTART,
                "switch_a": events.TEST_SWITCH, "switch_b": 0,
                "actor": 0, "variable": None, "item": 0, "capa": 0,
                "frecuencia": events.ROUTE_FREQUENCY, "speed": 4,
                "codigo": b""}]
        code = bytearray()
        for test_page in pages:
            test_page["offset"] = len(code)
            if test_page["codigo"]:
                code += test_page["codigo"]
            # And the commands of the own route, behind, one byte per command.
            own = test_page.get("ruta_propia")
            if own:
                test_page["ruta_offset"] = len(code)
                code += bytes(own["ordenes"])
        map_info["pages"] = pages
        # What each page of the events that change graphic draws, already as
        # OAM wants it: it is what the ROM copies to the NPC's row when the
        # active page changes. See `page_table`, +20.
        for test_page in pages:
            continues = test_page["event"] in map_info["cambian"]
            if not continues and test_page["event"] not in map_info["aparecen"]:
                continue
            graphic = test_page.get("grafico")
            if graphic is None \
                    or graphic[:2] in map_info["afuera"].get(test_page["event"], ()):
                continue
            if not continues:
                # The one that only appears carries no tile or attributes: its
                # own point to its slot of twelve poses and the ROM doesn't
                # touch them. The pose goes —with bit 7, which is "this page
                # draws something"— and what its tile imposes on the cell.
                test_page["oam"] = (0, 0, graphic[2] | 0x80,
                                 0xFF if test_page.get("tile_pass") is None
                                 else test_page["tile_pass"])
                continue
            block, slot = map_info["where"][graphic]
            tile = block_tile(block)
            priority = (OBJ_PRIORITY_ABOVE
                        if test_page["capa"] == rm2k.LAYER_ABOVE
                        else OBJ_PRIORITY)
            test_page["oam"] = (tile & 0xFF,
                             priority | ((slot & 0x07) << 1) | ((tile >> 8) & 1),
                             graphic[2] | 0x80,
                             0xFF if test_page.get("tile_pass") is None
                             else test_page["tile_pass"])
        map_info["evcode"] = bytes(code)
        # The ROM's substitution table has a fixed cap and **doesn't warn** if
        # it goes over: the pairs that don't fit wouldn't be applied and the
        # map would draw too much. How many entries it can end up having is
        # known here, and it is the number of distinct blocks some substitution
        # of the map uses as a key, because a key is never overwritten: the
        # second round changes its value. See `op_tile_sub` in
        # tools/runtime/interpreter_map.s.
        keys = len(map_info["sustituciones"].known_keys)
        if keys > SUB_MAX:
            sys.exit("map %d substitutes %d distinct blocks and the RAM "
                     "table carries %d: see SUB_MAX"
                     % (map_info["id"], keys, SUB_MAX))
        # How many distinct events this map can end up sending walking. The
        # ROM has ROUTE_EV_MAX slots and a route that finds no room is
        # discarded **without saying anything**: the NPC stays still and, if
        # the golden is taken like that, the test defends the error. With this
        # game's data the worst map uses two, so the check bothers nobody; it
        # is there so that a future change doesn't throw them away silently.
        #
        # The pages that **run** here: the map's and those of the cases that
        # jump to it, which live in the boot one. See `case_map`.
        run_here = [p["codigo"] for p in pages
                    if p["codigo"] and not p.get("prueba")]
        run_here += [test_party[k] for k, case in enumerate(args.cases)
                     if case.run_map == map_info["id"]]
        targets = {c[i + 1] for code in run_here
                   for i, c in walk_code(code)
                   if c[i] == events.OP_ROUTE and c[i + 1]}
        # And that nobody flashes someone who shares a graphic with another.
        # On the console the flash is done on the character's palette, so two
        # that share a graphic would flash together. `events.py` already
        # rejects the case of two events; here the one it can't see there is
        # covered, which is the hero's: which graphic it has depends on the
        # party, and the converter knows that and the compiler doesn't.
        #
        # `separate_from_hero` already avoids this in the maps whose pages flash
        # the hero. This stays for what that one doesn't see: a `FlashSprite`
        # that arrives inside a common event, which is compiled in place from
        # any `CallEvent` and isn't in the map's pages.
        graphics = collections.Counter(
            (npc["charset"], npc["index"])
            for npc in rm2k.collect_npcs(map_info["game_map"]))
        for actor in args.leaders:
            a = renderer.database.actors[actor]
            graphics[(a.charset, a.charset_index)] += 1
        for code in run_here:
            for i, c in walk_code(code):
                if c[i] != events.OP_FLASH or c[i + 1] != 0:
                    continue
                for actor in args.leaders:
                    a = renderer.database.actors[actor]
                    if graphics[(a.charset, a.charset_index)] > 1:
                        raise SystemExit(
                            "map %d: a page makes the hero flash, and "
                            "actor %d is drawn with %s[%d], which an NPC of "
                            "the map also uses. On the console they share a "
                            "palette and both would flash"
                            % (map_info["id"], actor, a.charset, a.charset_index))

        if len(targets) > ROUTE_EV_MAX:
            raise SystemExit(
                "map %d: its pages send %d distinct events walking and "
                "the ROM has %d route slots"
                % (map_info["id"], len(targets), ROUTE_EV_MAX))
        runnable = sum(1 for p in pages if p["codigo"])
        if pages:
            print("  map %d: %d automatic event page(s), %d runnable"
                  % (map_info["id"], len(pages), runnable))

    if not 0 <= args.start_index < len(maps):
        sys.exit("--start-index %d but there are %d maps" % (args.start_index, len(maps)))
    from port import window as window_mod
    skin = window_mod.skin(args.game_dir, renderer.database.system_name)
    font_id = renderer.database.font_id
    window_data = convert_window(skin, font_id)
    window_data["fuente"] = font_bytes(font_id)
    window_data["mensajes"] = messages.bytes()
    print("  message window: %d fixed tiles + %d of text, %d colors; "
          "font %d B, %d text box(es) in %d B"
          % (len(window_data["tiles"]) // 32,
             len(window_data["fondo"]) // 32,
             sum(1 for w in window_data["cram"] if w),
             len(window_data["fuente"]), len(messages.texts),
             len(window_data["mensajes"])))
    # The slots screen goes in every ROM: the save point opens it from inside
    # the game, and "Resume the Story" from the title when there is one. It is
    # drawn with the same font and the same skin as the message window, and
    # lives in the title's VRAM, where there is no map.
    # The actors that can be in the party when saving, to have their face and
    # their name in the cartridge: the starting ones and all the ones some
    # `ChangePartyMembers` of these maps adds, whether their pages compile or
    # not. It is a superset on purpose: one face too many costs 36 tiles and
    # one too few leaves a hole in the menu.
    members = possible_members(every, party, file_commands)
    # And the items that can be in the inventory, to carry their name and
    # their description: see "la pantalla de ítems" in menus.py.
    items_rom = possible_items(every, members, renderer.database,
                               file_commands)
    # With the letters of the medicines, which the actor choice writes with
    # the bank's glyphs: see `TARGET_WINDOWS`.
    medicine_letters = "".join(
        renderer.database.items[n].name for n in items_rom
        if renderer.database.items[n].type == lcf.ITEM_TYPE_MEDICINE)
    (slot_tiles, slot_palettes, slot_headers, slot_rows, slot_faces,
     slot_menu) = menus_mod.slots_screen(
        skin, renderer.database, SLOTS, renderer.database.font_id,
        members, args.game_dir, medicine_letters)
    target = menus_mod.borders(
        skin, 0, menus_mod.target_layers(skin, renderer.database,
                                           renderer.database.font_id),
        menus_mod.TARGET_CGRAM,
        menus_mod.TARGET_CGRAM + menus_mod.TARGET_COLORS_MAX)
    _check_target(len(target[0]))
    items_tiles, items_palettes, items_glyphs = menus_mod.items_screen(
        skin, renderer.database.font_id)
    # The item and equipment windows share tiles and colors: see
    # `menus.borders`.
    items_border = menus_mod.borders(
        skin, items_border_first(len(items_tiles)),
        [menus_mod.item_layers(skin), screens_mod.equipment_layers(skin)])
    _check_items_border(len(items_tiles), len(items_border[0]))
    # The shop's, with their own tiles and colors: see
    # `screens.TI_WINDOWS`.
    shop_border = menus_mod.borders(
        skin, 0, screens_mod.shop_layers(skin),
        menus_mod.ITEM_BORDER_CGRAM, menus_mod.TARGET_CGRAM)
    _check_shop(len(shop_border[0]))
    # The End Game screen's tiles go where the slots' do, so what is checked
    # is the same.
    end = end_game_mod.convert(skin, renderer.database, renderer.database.font_id)
    _check_slots(len(end[0]))
    slots_data = {"tiles": slot_tiles, "paletas": slot_palettes,
                  "cabeceras": slot_headers, "filas": slot_rows,
                  "caras": slot_faces,
                  "menu": slot_menu, "items": items_rom,
                  "db": renderer.database, "actores": members,
                  "relleno_textos": args.text_padding,
                  "items_db": renderer.database.items,
                  "items_tiles": items_tiles,
                  "items_paletas": items_palettes,
                  "items_glifos": items_glyphs,
                  "items_marco": items_border, "fin": end,
                  "tienda_marco": shop_border,
                  "objetivo": target}
    _check_slots(len(slot_tiles))
    _check_splits()
    print("  slots screen: %d, %d 4bpp tiles (%d B) + %d palettes, "
          "%d B of cells; %d actors with a face: %s"
          % (SLOTS, len(slot_tiles), len(slot_tiles) * 32,
             len(slot_palettes),
             (len(slot_headers) * len(slot_headers[0])
              + SLOTS * 4 * len(slot_rows[0][0][0])) * 2,
             len(slot_faces),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(slot_faces)) or "none"))
    title_data = None
    if not args.no_title:
        from PIL import Image
        name = renderer.database.title_name
        picture = Image.open(os.path.join(args.game_dir, "Title",
                                          name + ".png"))
        texts = title_mod.options(renderer.database)
        menu_tiles, menu_palette, menu_maps = title_mod.menu(
            skin, texts, renderer.database.font_id)
        # The image, compressed like the Game Over one, and with the menu's
        # colors below its own in the same stream: the whole CGRAM at once,
        # the menu's palette at the bottom because a 4-bit BG only reaches
        # those. The tiles' indices already come shifted from
        # `palette.convert`.
        below = list(menu_palette)
        below += [(0, 0, 0)] * (constants.MENU_CGRAM - len(below))
        screen = fullscreen.compressed(
            picture, constants.MENU_CGRAM, constants.COLORS, below)
        title_data = {"pantalla": screen,
                      "menu_tiles": menu_tiles, "menu_paleta": menu_palette,
                      "menu_tilemaps": menu_maps}
        print("  title screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (name, screen["tiles"],
                 screen["colores"] - len(below), screen["crudo"],
                 len(screen["flujo"])))
        print("    menu (%s): %d 4bpp tiles (%d B) + %d colors, %d tilemap(s)"
              % (", ".join(repr(t) for t in texts), len(menu_tiles),
                 len(menu_tiles) * 32, len(menu_palette), len(menu_maps)))
    # The Game Over screen: the image the LDB's `System` names, in the game's
    # or the RTP's `GameOver/` —as RM2k looks for it—, compressed. It goes in
    # every ROM that finds it: any cartridge can lose a battle or run a
    # `GameOver`. See tools/port/fullscreen.py.
    game_over_data = None
    path = find_resource([args.game_dir, resources.RTP_DIR], "GameOver",
                         renderer.database.gameover_name)
    if renderer.database.gameover_name and path:
        from PIL import Image
        game_over_data = fullscreen.compressed(Image.open(path))
        print("  Game Over screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (os.path.basename(path), game_over_data["tiles"],
                 game_over_data["colores"], game_over_data["crudo"],
                 len(game_over_data["flujo"])))
    # The battle animations the already emitted bytecode shows: their
    # prerendered frames go to the cartridge and the ROM uploads them by DMA.
    animations = rom_animations(maps, renderer)
    for number in sorted(animations):
        data = animation_mod.report(number, animations[number])
        print("  animation %d: %d frames of %dx%d, shrunk from %dx%d to %d%%,"
              " %d colors, %d B"
              % (data["animacion"], data["cuadros"], data["caja"][0],
                 data["caja"][1], data["original"][0], data["original"][1],
                 data["porciento"], data["colores"], data["bytes"]))
    # The random encounters of each map, which ask for their troops. They go
    # **before** those of the test pages, which go at the end: that way the
    # cartridge's troops are numbered by the maps and the invented one goes
    # last, which is the same `rom_songs` does with the map's song.
    # Asking for it first always gave it index 0, and with that no case of the
    # suite exercised that `scene_troop_backdrop` and `troop_id` are really
    # indexed. That is why `case_page` compiles without `Troops`.
    encounters = rom_encounters(maps, renderer.tree,
                                args.test_encounters, troops)
    how_many = sum(z["troop_n"] for z in encounters["zonas"])
    if encounters["registros"]:
        print("  random encounters: %d map(s), %d zone(s), %d troop(s)"
              % (len(encounters["registros"]), len(encounters["zonas"]),
                 how_many))
    for cmd in file_commands:
        if cmd.code == events.ENEMY_ENCOUNTER:
            troops.request(events.encounter_troop(cmd),
                           events.encounter_backdrop(cmd))
    # The battle's audio, with the indices it already got from `songs` while
    # the pages compiled. It is asked for again only to read them: `Songs`
    # numbers once and returns the same, and what was noted goes to the
    # battle's package and not to any map's.
    battle_audio = events.battle_audio(songs) if troops.ids else None
    # The backdrops and the battlers the cartridge's battles ask for, each one
    # once: the ROM composes them when each battle starts. See
    # tools/port/scene.py, which is where the reason and the budget are.
    scenes = rom_scene(renderer.database, troops, maps, renderer.tree,
                       encounters, args.game_dir)
    # The `.msu` is written after the audio, because it also carries the
    # quality sound effects: see `msu_asm`.
    for info in scenes["fondos"]:
        rom_tiles, rom_colors = fallback_bytes(info)
        msu_tiles, msu_colors = scenes["calidad"][info["numero"]]
        print("  battle backdrop %d %r: %dx%d, %d tiles from CGRAM entry %d; "
              "in the ROM %dx%d at 4bpp and %d colors (%d B), in "
              "the .msu 8bpp and %d colors (%d B)"
              % (info["numero"], info["nombre"], scene_mod.WIDTH,
                 scene_mod.HEIGHT, scene_mod.TILES, scene_mod.CGRAM_BASE,
                 scene_mod.FALLBACK_WIDTH, scene_mod.FALLBACK_HEIGHT,
                 len(info["respaldo"]["paleta"]),
                 len(rom_tiles) + len(rom_colors), scene_mod.COLORS,
                 len(msu_tiles) + len(msu_colors)))
    # And the ones that aren't in the ROM, with which one replaces them
    # without MSU-1.
    in_rom = {info["numero"] for info in scenes["fondos"]}
    outside = [k for k in range(len(scenes["juego"])) if k not in in_rom]
    if outside and scenes["fondos"]:
        print("  battle backdrops only in the .msu, which without MSU-1 fall "
              "back to %r: %s" % (scenes["fondos"][scenes["respaldo_de"][outside[0]]]
                                  ["nombre"], ", ".join(
                                      "%d %s" % (k, scenes["juego"][k])
                                      for k in outside)))
    for info in scenes["battlers"]:
        d = scene_mod.battler_report(info)
        print("  battler %r: %dx%d, %d B, %d colors of %d"
              % (d["clave"], d["ancho"], d["alto"], d["bytes"], d["quedan"],
                 d["colores"]))
    # The event pages of the troops some battle of the cartridge asks for,
    # with **all** the troops already asked for: the maps', the random
    # encounters' and the test pages'. See `events.TroopPages`, which is
    # also why their messages go to a separate block. With `songs`, because a
    # page's `PlaySound` sounds in the battle's package, which isn't built
    # yet: it is built further down.
    troop_pages = events.TroopPages()
    for number in troops.ids:
        if number in renderer.database.troops:
            troop_pages.compile(number, renderer.database.troops[number],
                                songs)
    print("  troop pages: %d of %d in %d distinct body(ies), %d B of "
          "code and %d B in %d message(s)"
          % (troop_pages.pages - troop_pages.left_out,
             troop_pages.pages, len(troop_pages.where),
             len(troop_pages.bodies), len(troop_pages.messages.data),
             len(troop_pages.messages.texts)))
    # The items the enemies of those troops drop can also reach the
    # inventory: see `drop_items`.
    slots_data["items"] = sorted(
        set(items_rom) | drop_items(renderer.database, troops.ids))
    compressed = compress_blocks(maps)
    report = emit(args.output, maps, args.start_index, args.hero_above, party,
                  window_data, title_data, slots_data,
                  args.pictures.info, animations, troops.ids, battle_audio,
                  scenes, encounters, troop_pages, compressed,
                  enemy_hp=args.enemy_hp,
                  game_over=game_over_data)
    # Which entries of their palette the timer digits use, one bit per entry
    # and one word per map, in the order of `map_table`. `upload_timer_pal`
    # uploads **those** again untinted and not the whole palette, because the
    # palette belongs to a character that is tinted. It goes separately and
    # not as a record field because the record is at exactly its 128. The
    # index is the same `index + 1` `timer_digits` painted the glyphs
    # with: the first one that has that color.
    timer_color_list = sorted(timer_colors_of(skin))
    masks = []
    for map_info in maps:
        sprite, mask = map_info["sprite"], 0
        if sprite and sprite[5]:
            palette = sprite[1][sprite[6]]
            for color in timer_color_list:
                mask |= 1 << (palette.index(color) + 1)
        masks.append(mask)
    with open(args.output, "a") as handle:
        handle.write('\n.segment "RODATA"\n.block %d\ntimer_mask:\n'
                     '    .word %s\n'
                     % (2 * len(masks),
                        ", ".join("$%04X" % m for m in masks)))
    if len(args.cases) > 1:
        # Where the harness writes the case number: see `--case`.
        with open(args.output, "a") as handle:
            handle.write("\nCASE_SLOT = %d\n" % events.variable_slot(
                events.CASE_VARIABLE))
    print("%d map(s) -> %s, boots at %d (map %d)"
          % (len(maps), args.output, args.start_index, maps[args.start_index]["id"]))
    # What the allocator decided, as images: to look at which colors were lost
    # and which palette each cell ended up in without building or running the
    # ROM. They are indexed and their indices are CGRAM entries, so an editor
    # in indexed mode opens them just as `tiles` is going to see them.
    allocator = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "asignador")
    os.makedirs(allocator, exist_ok=True)
    for map_info in maps:
        pictures = list(map_info["imagenes_fondo"]) + [("encima", map_info["above"][5])]
        for name, png in pictures:
            with open(os.path.join(allocator, "%04d-%s.png"
                                   % (map_info["id"], name)), "wb") as handle:
                handle.write(png)
    # And **what it decided to lose**, written down: which color was merged
    # with which in each layer. It goes next to the images because it comes
    # from the same decision, but it is something else: the images are for
    # looking at and this is for reading back and for the diff to warn. What
    # is versioned is in `rom/parches/`, and `just parches --check` compares.
    # See tools/port/patches.py.
    patches_dest = os.path.dirname(os.path.abspath(args.output))
    count, weigh = patches_mod.write_maps(patches_dest, maps)
    print("patches of %d map(s) -> %s (%d B)"
          % (count, patches_mod.MAPS_IN_BUILD, weigh))
    # And the other decision that is already written down: **at what size
    # each battle animation is drawn**. It comes from the same round above;
    # here it is joined with the name and the sheet the animation has in the
    # LDB, which nobody looks at to draw and are there so that the diff says
    # which one it is about.
    count, weigh = patches_mod.write_animations(
        patches_dest,
        [dict(animation_mod.report(number, animations[number]),
              nombre=events.ANIMATIONS[number].get("nombre", ""),
              hoja=events.ANIMATIONS[number].get("imagen", ""),
              lado=animation_mod.BOX)
         for number in sorted(animations)])
    print("patches of %d animation(s) -> %s (%d B)"
          % (count, patches_mod.ANIMS_IN_BUILD, weigh))
    # And **which fifteen colors each battler is reduced to**, which is the
    # decision the scene composed on the console brought: see
    # tools/port/scene.py.
    count, weigh = patches_mod.write_battlers(patches_dest,
                                              scenes["battlers"])
    print("patches of %d battler(s) -> %s (%d B)"
          % (count, patches_mod.BATTLERS_IN_BUILD, weigh))
    # And who asked for each one, which isn't versioned: it is what separates,
    # in the ROM that is played, what belongs to the game from what only
    # exists because of the suite.
    patches_mod.write_uses(patches_dest, patch_uses(
        maps, renderer.database, renderer.tree))
    if report:
        print("material compressed and shared between maps:")
        for line in report:
            print(line)

    # The music comes from here and not from a separate recipe.
    # `musicdata.inc` was global state as `mapdata.inc` was, with the
    # aggravating factor that nobody regenerated it: a ROM built for maps 4, 7,
    # 19 and 1 —which have no music— played the song of map 348, which was the
    # last one somebody had generated by hand. Emitting them together is the
    # only thing that guarantees both describe the same ROM.
    #
    # **All the songs** go, sharing a single sample bank, and the one of the
    # map the ROM boots in plays; the others are started by a `PlayBGM`, or
    # by the map that is entered if it brings its own —see `map_song_mute`
    # in tools/runtime/enter_map.s—. What rate each sample ends up at is
    # decided by the ARAM, package by package: see `Bank` in the `bank.rs`
    # of `rm2k-snes-audio`.
    music = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                         "musicdata.inc")
    requested, boot, title_song, map_song, game_over_song = (
        rom_songs(
            maps[args.start_index]["id"], songs, args.game_dir,
            renderer.database.title_music if not args.no_title else None,
            [m["id"] for m in maps],
            renderer.database.gameover_music if game_over_data else None))
    # The sound effects, in the order the compiled pages ask for them: the
    # maps are compiled in ROM order, so those of the map where it boots go
    # first —in the demo, the rain and the thunder of the opening—. Only the
    # ones that are in some package: one that isn't in any doesn't sound
    # anywhere —its row of `sound_table` stays at $FF— and building it would
    # cost the music, because the copies of `rm2k-snes-audio` count the
    # cartridge's sound effects. It happens with the route ones of
    # `se_route_left_out`.
    packed = {n for palettes_needed in songs.per_map.values()
              for n in palettes_needed["sonidos"]}
    requested_se = []
    for name, _v, _t, _b in songs.sounds:
        if name not in requested_se and name in packed:
            requested_se.append(name)
    # Each map's audio package, in the order of the map table: the songs its
    # pages can start —plus, in the boot one, the one that plays from the
    # start, and in all the map's own— and its sound effects, in the order
    # they appear, which is the priority the ROM uploads them with if they
    # don't all fit. See `package_load` in tools/runtime/audio_package.s.
    # They are built **before** the bank, by name, because each sample's
    # budget comes from them: see `Bank` in `rm2k-snes-audio`.
    packages, separate_ones = [], []
    for i, _map in enumerate(maps):
        palettes_needed = songs.per_map.get(i, {"temas": [], "sonidos": []})
        owned = list(palettes_needed["temas"])
        if i == args.start_index and boot != 0xFF and boot not in owned:
            owned.insert(0, boot)
        # And the map's own song, **in front**: it is the only one on the list
        # that surely plays on entering, so if the ARAM isn't enough for
        # everything it is the last one that has to fall. Without it in the
        # package, its samples would have to be uploaded by `song_ensure`
        # when starting it, rebuilding the whole package a second time.
        if map_song[i] != 0xFF:
            if map_song[i] in owned:
                owned.remove(map_song[i])
            owned.insert(0, map_song[i])
        # And the exit ones, separate and after the sound effects: the ones
        # the map starts only to leave have no reason to go in with its sound
        # effects. See `Songs.exit_songs`. Not the map's own nor the boot one:
        # those play on entering.
        out = [t for t in songs.exit_songs(i)
               if t in owned and t != map_song[i]
               and not (i == args.start_index and t == boot)]
        owned = [t for t in owned if t not in out]
        # And the separate ones, which don't go with the other songs either:
        # their `PlayBGM` uploads them with the package's sound effects. See
        # `separate_songs`.
        separate = [t for t in owned if requested[t] in separate_songs().get(
                      _map["id"], ()) and t != map_song[i]
                    and not (i == args.start_index and t == boot)]
        owned = [t for t in owned if t not in separate]
        separate_ones.append(separate)
        packages.append((owned, list(palettes_needed["sonidos"]), out))
    # And the battle's package, after the maps: the battle song and its sound
    # effects, which the ROM uploads when opening the battle and unloads when
    # closing it. It goes separately and not inside the map's package because
    # the battle song alone fills the ARAM; see `events.BATTLE_PACKAGE`.
    palettes_needed = songs.per_map.get(events.BATTLE_PACKAGE)
    if palettes_needed:
        packages.append((list(palettes_needed["temas"]), list(palettes_needed["sonidos"]), []))
        separate_ones.append([])
    package_names = ([str(m["id"]) for m in maps]
                     + (["pelea"] if palettes_needed else []))
    # And the Game Over screen's, last: its song alone and no sound effects.
    # The ROM uploads it with the screen black, before the fade in —see
    # `game_over_black` in tools/runtime/game_over.s—, and with a package of
    # its own it uploads only that: arriving with `song_ensure` would
    # rebuild the whole map package behind it, which is one more second of
    # black. For the allocation it is a one-song package, which doesn't lower
    # anyone's rate: its samples fit alone in the ARAM.
    game_over_package = 0xFFFF
    if game_over_song != 0xFF:
        game_over_package = len(packages)
        packages.append(([game_over_song], [], []))
        separate_ones.append([])
        package_names.append("gameover")
    per_name = [(name, owned, theirs, out, separate)
                for name, (owned, theirs, out), separate
                in zip(package_names, packages, separate_ones)]
    # And the title screen's, which isn't in the table: `song_ensure`
    # uploads its song with the boot map's package behind.
    if title_song != 0xFF:
        owned, theirs, _out = packages[args.start_index]
        per_name.append(("titulo", [title_song] + owned, theirs))
    inheritance = inherited_songs(songs, map_song, args.start_index,
                                  title_song, package_names,
                                  [owned for owned, _e, _s in packages],
                                  separate_ones, not_given=settings.value(
                                   "music", "jumps_that_never_happen",
                                   kind=list))
    # The music itself is `rm2k-snes-audio`'s: it gets what was decided
    # here —the songs, the sound effects, the packages—, and writes
    # `musicdata.inc`, `musica.json` —what `tools/audio/msu.py` and the
    # volume ceilings read of each song— and `audio.json`, what the rest of
    # this function needs from the music. The job stays next to them, so
    # the music of a cartridge can be rebuilt alone.
    # Each package's sound effects go by number and not by SRCN: several
    # share the directory's place, which is its business.
    job = {
        "songs": requested,
        "effects": requested_se,
        "packages": [{"name": name, "songs": list(owned),
                      "effects": list(theirs), "exits": list(out),
                      "separate": list(separate)}
                     for name, owned, theirs, out, separate
                     in per_name[:len(packages)]]
                    + [{"name": p[0], "songs": list(p[1]),
                        "effects": list(p[2])}
                       for p in per_name[len(packages):]],
        "inheritance": [[name, t] for name, t in inheritance],
        "measuring_headroom": args.measure_headroom,
        "system_songs": lcf.system_songs(
            os.path.join(args.game_dir, "RPG_RT.ldb")),
        "emit": {
            "packages": len(packages),
            "boot": boot,
            "title": title_song,
            "game_over": [game_over_song, game_over_package],
            "map_song": list(map_song),
            "sounds": [list(sound) for sound in songs.sounds],
            "start": args.start_index,
            "decompress_frames": decompress_frames(maps[args.start_index],
                                                   compressed),
        },
    }
    audio = compile_music(job, os.path.dirname(music))
    done_ones = audio["songs"]
    effects = {e["name"]: e for e in audio["effects"]}
    packages = [(owned, theirs, out)
                for owned, theirs, out, _separate in audio["packages"]]
    if palettes_needed:
        assert package_names[len(maps)] == "pelea", (
            "the battle's package has to end up at the index `emit` emitted "
            "as PAQUETE_BATALLA")
        print("  battle audio package: %d song(s), %d sound effect(s)"
              % (len(palettes_needed["temas"]), len(packages[-1][1])))
    # **And that the boot fits in `BOOT_FRAMES`**: the ROM waits until that
    # frame so that the loop always starts on the same one, and if uploading
    # the boot map's package took longer, it would come out later and the
    # tests —which count from there— would count wrong. See the comment on
    # `BOOT_FRAMES` in tools/runtime/far_ram.s.
    frames, in_package = audio["boot"]["frames"], audio["boot"]["bytes"]
    cap = boot_frames()
    if frames > cap:
        raise SystemExit(
            "the boot doesn't fit in BOOT_FRAMES: the boot map's package is "
            "%d B and with the map, the driver and the directory the "
            "computation gives %.0f frames, against %d. Raise BOOT_FRAMES in "
            "tools/runtime/far_ram.s, or shrink that package"
            % (in_package, frames, cap))
    print("  boot: the boot map's package is %d B, %.0f of "
          "the %d frames of BOOT_FRAMES" % (in_package, frames, cap))
    # The `.msu`: the quality backdrops and the quality sound effects, to read
    # them through the MSU-1 when it is there. It is always written, even if
    # the cartridge carries neither backdrops nor sound effects, because it is
    # also the file that turns on the MSU-1 for the tracks.
    write_msu(args.msu or os.path.join(os.path.dirname(os.path.abspath(
        args.output)), "datos.msu"), music, scenes["calidad"],
        audio, songs.sounds)
    for i, (owned, theirs, out) in enumerate(packages[:len(maps)]):
        if owned or theirs or out or separate_ones[i]:
            print("  audio package of map %d: %d song(s), %d sound effect(s)%s%s"
                  % (maps[i]["id"], len(owned), len(theirs),
                     ", and for exit %s" % ", ".join(done_ones[t]["name"]
                                                     for t in out)
                     if out else "",
                     ", and separate %s" % ", ".join(done_ones[t]["name"]
                                                     for t in separate_ones[i])
                     if separate_ones[i] else ""))
    if requested_se:
        print("  sound effects: %d, %d B in the cartridge"
              % (len(effects), sum(e["bytes"] for e in effects.values())))
    print("music -> %s: %s"
          % (music, ", ".join(t["name"] for t in done_ones)
             or "none, it comes out silent"))
    # The bank packing is not decided here: both files send everything to
    # RODATA, with a `.block` or a `.crossbank` in front of each piece, and
    # `rm2k-snes-assemble` spreads it into banks and writes the memory map
    # before running `ca65`.


def page_party(case, party):
    """Which party the test continues with after its page, if the page
    touches it: the case's `ChangePartyMembers` applied to the cartridge's
    party, with the same rules as the interpreter. None if it doesn't touch
    it."""
    state = events.PartyState(party)
    touches = False
    for cmd in case.commands:
        p = cmd.parameters
        if (cmd.code == events.CHANGE_PARTY_MEMBERS and len(p) >= 3
                and p[1] == events.PARTY_FIXED_ID):
            state.change_party(p[0], p[2])
            touches = True
    return state.party if touches else None


# The flags that describe **a test case** —what its page does— and not the
# cartridge. They are the ones that can go after a `--case`; the rest belong
# to the whole cartridge and go before the first one. Since cut 3 of step 9d
# there is a single one, the file with the page: what the page does is RM2k
# data, not flags. `--test-graphic` belongs to the cartridge on purpose:
# it says which graphics are in the sprite bank of the maps where the cases
# run, not what the page does. And where a case runs isn't a flag either: the
# `Teleport` it starts with says so, see `case_map`.
CASE_FLAGS = ("test_commands",)


def split_cases(argv):
    """The command line split at `--case`: the cartridge's part, and the
    flags of each case that goes after."""
    stretches = [[]]
    for token in argv:
        if token == "--case":
            stretches.append([])
        else:
            stretches[-1].append(token)
    return stretches[0], stretches[1:]


def test_cases(parser, args, stretches):
    """The cartridge's test pages, one per case, in the order of their pages.
    Each one is a copy of `args` with its case's flags.

    Case 0 is the flags before the first `--case`, so a single-case cartridge
    is built as before this existed. If there are none, the first `--case`
    becomes 0. Each case takes the commands of its file in `commands`.
    """
    import copy
    cases = [args] if asks_test_page(args) else []
    default_args = parser.parse_args([])
    for stretch in stretches:
        loose = parser.parse_args(stretch)
        for dest, value in vars(loose).items():
            if dest not in CASE_FLAGS and value != getattr(default_args, dest):
                sys.exit("--%s belongs to the cartridge and not to a case: it "
                         "goes before the first --case" % dest.replace("_", "-"))
        case = copy.copy(args)
        for dest in CASE_FLAGS:
            setattr(case, dest, getattr(loose, dest))
        if not asks_test_page(case):
            sys.exit("a --case with nothing for the test page to do")
        cases.append(case)
    for case in cases:
        with open(case.test_commands, encoding="utf-8") as fh:
            case.commands = lcf.handwritten_commands(json.load(fh))
    return cases


def case_commands(args, map_id=None):
    """The commands of all the test pages, one after the other.

    It is what the functions that look at the map's pages to decide what the
    cartridge carries —variables, items, members, rain— sweep: a test page is
    one more page.

    With `map_id`, only those of the cases that **run** in that map —see
    `case_map`—: they are the ones that decide what belongs to each map,
    like who walks or which graphics go in its sprite bank.
    """
    return [cmd for case in args.cases
            if map_id is None or case.run_map == map_id
            for cmd in case.commands]


def case_map(case, order, initial):
    """The map where a case runs: that of its `Teleport`, if it starts with
    one, and otherwise the map where the ROM boots.

    It is how a case chooses where to start since step 9e, instead of a
    `--map-id` and a starting cell per cartridge: with RM2k's `Teleport`,
    which is data and not a flag. The page still lives in event 0 of the boot
    map —that is where the ROM finds it and where it runs first—, but what
    comes after the jump runs in the other map, so it is compiled with that
    one's context: its events, the variables its pages look at, its graphics.
    Compiled with the boot map's, a write to a variable only the destination
    looks at didn't ask for a refresh, and the chest of map 133 didn't appear
    even though the variable already held what its page asks for.
    """
    first = case.commands[0] if case.commands else None
    if first is None or first.code != events.TELEPORT:
        return order[initial]
    dest = first.parameters[0]
    if dest not in order:
        sys.exit("%s: the case jumps to map %d, which isn't in the cartridge "
                 "(it carries %s)" % (case.test_commands, dest,
                                      " ".join(str(m) for m in order)))
    return dest


def test_maps(args):
    """The maps where some case runs, which are the ones that carry the
    graphics of `--test-graphic` in their bank."""
    if args.cases:
        return {case.run_map for case in args.cases}
    return {map_order(args)[args.start_index]}


def case_page(case, map_info, songs, graphics, messages, indices, pictures):
    """The bytecode of a case's test page.

    It is compiled like any page of the game, with the context of the map
    where it runs —see `case_map`—; the only thing the converter puts in
    front of it is the `ControlSwitches` that turns it off, which is a
    convention of the harness and not of the case —see
    `events.TEST_SWITCH`—. The troops aren't noted here but at the end,
    in `main`: the test's goes last.
    """
    turn_off = lcf.EventCommand(
        events.CONTROL_SWITCHES, 0, "",
        [events.SWITCH_SINGLE, events.TEST_SWITCH,
         events.TEST_SWITCH, events.SWITCH_ON])
    code = events.compile_page(
        events._Commands([turn_off] + list(case.commands)), indices.get,
        messages, events.MapEvents(map_info["game_map"]).for_event(0), songs,
        graphics, pictures)
    if code is None:
        sys.exit("%s: the test page doesn't compile"
                 % case.test_commands)
    return code

def asks_test_page(args):
    """Whether there is a test page before the first `--case`."""
    return bool(args.test_commands)

def convert_map(renderer, map_id, args):
    """A whole map: tiles, colors, sprites, collision and blocks."""
    game_map = renderer.load_map(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    if args.cases and map_id == map_order(args)[args.start_index]:
        # The test page's event goes **first**: the ROM walks the events from
        # lowest to highest, and the test page has to run before the game's.
        # It builds the party the test starts with, and a map whose page
        # touches the party on entering —21 adds Talan— found it already
        # changed. It is an event without pages: nothing is drawn or compiled,
        # it only takes index 0 so that everything that numbers events after
        # reading the map numbers the same.
        empty = lcf.Event.__new__(lcf.Event)
        empty.id, empty.name, empty.x, empty.y, empty.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, empty)
    separate_from_hero(renderer, game_map, args,
                       case_commands(args, map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    layers = converted_layers(renderer, game_map)
    if layers is None:
        sys.exit("can't find the chipset of map %d" % map_id)

    # And the layers again, with the opaque events baked into the map. **Both**
    # are converted and compared because baking adds colors to the
    # background: if that made it merge colors, or shifted the upper layer's
    # CGRAM split, what is seen in cells that have nothing to do with the
    # baking would change. In that case the map goes unbaked, which is the
    # usual. The second conversion isn't paid twice in a warm build: both stay
    # in the disk cache, with their key.
    without_baked = layers
    baked = bakeable_events(renderer, game_map)
    if baked:
        layers, baked = _bake_unless_cgram_moves(
            renderer, game_map, map_id, without_baked, baked)

    # The characters: the hero with its 12 poses because it walks, and each
    # NPC with the one its page declares. If an NPC uses the same character as
    # the hero, they share palette and tiles without anything having to be
    # done.
    #
    # The timer digits take one of the eight sprite palettes, so the ceiling
    # drops to seven. The events drawn with a chipset tile go in while they
    # fit under that ceiling.
    # Who is going to walk and which graphics the routes change to. It goes
    # **before** the palette split because a graphic of command 34 is one
    # more character and asks for a palette like anyone: splitting without
    # counting it, it would come in later and there might be no room.
    order = map_order(args)
    movable, route_graphics, animates_still, turning = movable_events(
        game_map, {m: i for i, m in enumerate(order)}.get,
        associations=args.associations)
    # And the ones from `--test-graphic`, which go only in the maps where
    # some case runs, and for the same reason their pages are compiled with
    # that map's context. They are added **after** the game's, which is the
    # order the real compilation numbers them in.
    if args.test_graphic and map_id in test_maps(args):
        for charset, index in test_graphics(args.test_graphic):
            if (charset, index) not in route_graphics:
                route_graphics.append((charset, index))
    if case_commands(args, map_id):
        # And the ones the test pages send walking, which don't come from
        # `map_pages`: they have to be added by hand or the NPC would
        # walk with a single pose. It goes **before** the palette split: since
        # the palette is chosen over the poses that are seen, knowing who walks
        # is part of choosing the colors and not only of splitting the VRAM.
        # The event goes by its RM2k id and the same `MapEvents` the compilation
        # uses translates it.
        map_events = events.MapEvents(game_map)
        for cmd in case_commands(args, map_id):
            if cmd.code == events.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != events.ROUTE_HERO:
                target = map_events.route_target(cmd.parameters[0])
                if target:
                    movable = movable | {target - 1}
    # And with that, which poses each graphic can show: it is what decides
    # over which pixels its fifteen colors are chosen. See `map_poses`.
    poses_by_graphic = map_poses(renderer, game_map, args.leaders,
                                 movable, turning, route_graphics,
                                 animates_still)

    # All eight, with or without the timer: its two colors fit in some
    # character's palette. Reserving one for it here took events away from
    # the map, because this number is the one that decides which ones are
    # drawn.
    #
    # **One less in the maps that show battle animations**, since 2026-09-12:
    # the box needs a whole palette just for it —its fifteen colors belong to
    # the animation and are overwritten when another starts— and maps 2 and
    # 3, which are the intro's, filled all eight. Without this the Emitter
    # Room scene was left without its drawing, which is exactly what was
    # being done. What it costs —which characters merge more colors— is said
    # by each map's report.
    sample_animation = map_shows_animation(
        game_map, renderer,
        case_commands(args, map_id))
    # The timer's colors are passed to the split and not only to the packing:
    # in a map that fills the eight palettes someone has to be chosen to lose
    # a color to make room for it, and that changes how that character is
    # quantized.
    timer_colors = ()
    if map_id in args.timer_maps:
        from port import window as window_mod
        timer_colors = sorted(timer_colors_of(window_mod.skin(
            args.game_dir, renderer.database.system_name)))
    singles = {c for c, n in getattr(args, "maps_per_character", {}).items()
               if n == 1}
    palette_cap = map_palette_cap(
        renderer, game_map, args.leaders, route_graphics, timer_colors,
        singles, poses_by_graphic, sample_animation)

    npcs, discarded, split = drawable_npcs(renderer, game_map,
                                           args.leaders, palette_cap,
                                           route_graphics,
                                           timer_colors,
                                           singles,
                                           poses_by_graphic)
    lent = split[5]
    if lent:
        print("  map %d: %d graphic(s) without a palette of their own, drawn "
              "with someone else's: %s" % (map_id, len(lent),
                                          ", ".join(sorted("%s:%d" % k for k in lent))))
    # A baked event that was drawn with someone else's palette can't be
    # hidden: the sprite and the background tile would show different colors
    # —the lent ones and the real ones— and covering it with the second
    # changes what is seen. So that one is unbaked and goes back to being a
    # sprite, with the lent colors: it looks as it would without the baking.
    # It is asked here and not in `bakeable_events` because the lent ones
    # come from the split, which runs after drawing the layers. The first was
    # `PawnDoorTop`, event 11 of map 37: until 2026-09-26 this was a
    # `sys.exit`.
    lent_baked = sorted(
        event for event in baked
        for npc in npcs
        if npc["event"] == event and (npc["charset"], npc["index"]) in lent)
    if lent_baked:
        print("  map %d: event %s is drawn with someone else's palette, so "
              "it isn't baked" % (map_id, ", ".join(str(e + 1)
                                                    for e in lent_baked)))
        for event in lent_baked:
            cell_idx, _tile = baked.pop(event)
            game_map.upper_layer[cell_idx] = rm2k.UPPER_BASE
        layers = without_baked
        if baked:
            layers, baked = _bake_unless_cgram_moves(
                renderer, game_map, map_id, without_baked, baked)
    (tile_data, cram, tilemap, summary), above_data = layers
    if baked:
        print("  map %d: %d opaque event(s) baked into the map: %s"
              % (map_id, len(baked),
                 ", ".join(str(e + 1) for e in sorted(baked))))
    for event, tile in discarded:
        discard_warning(
            "map %d: event %d, drawn with tile %s, doesn't fit in "
            "the %d sprite palettes and isn't drawn"
            % (map_id, event + 1, tile[len(rm2k.TILE_PREFIX):],
               palette_cap),
            changes_graphic(game_map.events[event]))
    # Who changes pose and therefore carries their twelve to the cartridge:
    # the leader candidates with a graphic and the NPCs that walk. In that
    # order, with the initial leader first, which is the order the rest
    # expects.
    actors_with_graphic = []
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_of(renderer, args, a.charset),
                             a.charset_index):
            continue            # not a single opaque pixel: it isn't drawn
        actors_with_graphic.append(actor)
    first = renderer.database.leader(args.leaders)   # (CharSet, index)
    animated = []
    for actor in actors_with_graphic:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index) not in animated:
            animated.append((a.charset, a.charset_index))
    animated.sort(key=lambda pair: pair != first)   # the initial leader first
    for npc in npcs:
        if npc["event"] in movable \
                and (npc["charset"], npc["index"]) not in animated:
            animated.append((npc["charset"], npc["index"]))
    # And the graphics a command 34 changes to. They go to the bank for the
    # same reason as the ones that walk: after changing, the event keeps
    # walking, so it needs the twelve poses of the new graphic and not the one
    # its page declared.
    #
    # The ones without **a single opaque pixel** don't go in, and it isn't a
    # rare case: `nobodyhere` is 185 of the game's 437 commands 34. A
    # transparent CharSet has no colors, so it has no palette to ask of the
    # bank; and it isn't needed, because what the command does there is hide
    # the row. It is the same `sprite_colors` an actor without a graphic is
    # discarded with.
    graphic_visible = []
    for charset, index in route_graphics:
        # It is drawn if it has an opaque pixel **and** it made it into the
        # palette split. The second is almost always yes; when not, the
        # command hides it just like a transparent one, which is what the ROM
        # does with any graphic that didn't make it.
        graphic_visible.append(
            bool(sprite_colors(images_of(renderer, args, charset), index))
            and (charset, index) in split[1])
        if graphic_visible[-1] and (charset, index) not in animated:
            animated.append((charset, index))
    # And the ones that turn toward the hero: their twelve poses, to upload
    # the one facing it. They go at the end so as not to move anyone else's
    # index.
    for pairs in turning.values():
        for pair in sorted(pairs):
            if pair in split[1] and pair not in animated:
                animated.append(pair)
    off_route = [pair for pair, visible in zip(route_graphics, graphic_visible)
                 if not visible and sprite_colors(
                          images_of(renderer, args, pair[0]), pair[1])]
    for charset, index in off_route:
        discard_warning(
            "map %d: graphic %s:%d, which a route changes to, doesn't fit "
            "in the %d sprite palettes: that command hides the event instead "
            "of changing it" % (map_id, charset, index, palette_cap),
            # A command 34 **is** a graphic change, so it always counts.
            True)

    # The slots of the VRAM bank, one pose each: the hero in block 0 —if some
    # leader candidate has a graphic—, then each NPC that walks with its own,
    # and the still ones shared by (CharSet, index, pose), which never change.
    # An NPC that walks doesn't share even with an identical one: each changes
    # pose on its own.
    slots = []
    if actors_with_graphic:
        charset, index = animated[0]
        slots.append(("heroe", charset, index, INITIAL_POSE))
    for npc in npcs:
        if npc["event"] in movable:
            if npc["changes"]:
                # Two mechanisms on the same row: the cartridge's twelve poses
                # and the page's graphic. The ROM doesn't know both at once, so
                # **walking wins** and its graphic stops following the page. It
                # is the same it did before `collect_npcs` counted "nothing" as
                # a state —see `changes` there—, that is nothing that used to
                # work is lost.
                #
                # This was a `sys.exit`, and it was fine while no event asked
                # for it. Counting the "nothing" state, event 10 of map 8 asks
                # for it, and stopping because of that would be not building
                # the ROM over a detail of an NPC that walks.
                # What **does** follow the page is whether the row is visible:
                # that is bit 4 and it doesn't overwrite the tile. Without
                # separating them, an event that walks and appears with the
                # page never appeared, because the row starts hidden when on
                # loading the map no page qualifies. See `page_graphic` in
                # tools/runtime/event_pages.s.
                npc["aparece"] = True
                npc["changes"] = False
            slots.append((("ev", npc["event"]), npc["charset"],
                          npc["index"], npc["pose"]))
        else:
            # The pose of its row and, if the graphic follows the page, that of
            # each page: the ROM's refresh chooses between slots that are
            # already in VRAM.
            poses = [(npc["charset"], npc["index"], npc["pose"])]
            if npc["changes"]:
                poses += [g for g in npc["graphics"]
                          if g is not None and g[:2] not in npc["afuera"]]
            for key in poses:
                if key not in {r[0] for r in slots}:
                    slots.append((key,) + key)
    # The turn slot: one more pose, for the still one that turns toward the
    # hero. The still ones share a slot by (CharSet, index, pose), so turning
    # its own would also turn the others that use it; the one that turns
    # moves to this one while its page lasts. It is a single one because only
    # the event the hero triggered turns, and there is one at a time. The
    # ones that walk or animate don't need it: they have their own. See TURN
    # in events.py.
    still_turning = [npc for npc in npcs
                     if npc["event"] in turning
                     and npc["event"] not in movable
                     and any(pair in split[1]
                             for pair in turning[npc["event"]])]
    if still_turning:
        npc = still_turning[0]
        slots.append(("giro", npc["charset"], npc["index"], npc["pose"]))
    characters = list(animated)
    for _key, charset, index, _pose in slots:
        if (charset, index) not in characters:
            characters.append((charset, index))

    images = {}
    for charset, _index in characters:
        if charset not in images:
            # Through the renderer's loader, which also builds the CharSet of
            # an event drawn with a chipset tile.
            images[charset] = renderer.charsets.get(charset)
            if images[charset] is None:
                sys.exit("can't find CharSet %r" % charset)

    tiles, palettes, where, palette_of, char_colors = build_characters(
        images, characters, slots, split)
    # It is counted here and not inside because the message has to name the
    # culprit, which is the map. With `drawable_npcs` above this shouldn't
    # fail because of a tile anymore; if it fails it is because of the
    # CharSets.
    if len(palettes) > palette_cap:
        sys.exit("the map uses %d characters in %d palettes and there are %d "
                 "sprite ones" % (len(characters), len(palettes), palette_cap))
    banks = pose_bank(images, animated, char_colors)
    animated_index = {p: k for k, p in enumerate(animated)}
    # The table of command 34: for each graphic a route asks for, which entry
    # of `npc_poses` it is in and with which palette. $FF in the entry is
    # "hide the row", which is what a transparent CharSet does.
    route_gfx = [
        (animated_index[pair], palette_of[pair]) if visible else (0xFF, 0)
        for pair, visible in zip(route_graphics, graphic_visible)]
    # The timer, if this ROM carries it: its glyphs go at the end of the bank
    # and share a palette with whoever has room, which there almost always is.
    timer_base, timer_pal = 0, None
    if map_id in args.timer_maps:
        from port import window as window_mod
        sys_img = window_mod.skin(args.game_dir, renderer.database.system_name)
        tiles, timer_base, timer_pal = timer_digits(
            sys_img, tiles, palettes, split[3],
            palette_cap)
    rain_base, rain_pal = 0, 0
    if args.with_rain:
        tiles, rain_base, rain_pal = rain_drops(
            tiles, palettes, split[3],
            timer_base, palette_cap, timer_pal)
        if not rain_base:
            print("  map %d: WARNING, the raindrops don't fit in the "
                  "sprite palettes and it doesn't rain here" % map_id)
    # The `ShowPicture` picture, if its own belongs to this map. The slot is
    # chosen by `Pictures.choose` **in the order of the map table**, which is
    # this same loop.
    image_base, image_pal = 0, 0
    record = getattr(args, "pictures", None)
    if record is not None:
        info = record.choose([game_map])
        if info is not None and record.map_id is None:
            record.map_id = map_id
        if info is not None and record.map_id == map_id:
            tiles, image_base, image_pal = picture_of_image(
                info, tiles, palettes, rain_base or timer_base)
            if not image_base:
                sys.exit("map %d: the picture %r doesn't fit: the map already uses "
                         "the %d sprite palettes and the fade needs a whole "
                         "one. See `cartel_de_imagen`."
                         % (map_id, record.name, OBJ_PALETTES))
            print("  map %d: the picture %r, %d objects in %d tiles from "
                  "%d, palette %d" % (map_id, record.name,
                                      info["objetos"],
                                      picture.reserved_tiles(info),
                                      image_base, image_pal))
    # And the battle animation box, if some page of this map can show one that
    # is drawn. It goes last because it takes the end of the bank and the
    # palette left free after the picture. The criterion for it to fit is a
    # computation and the converter emits it: if there is no palette or no
    # VRAM, **this map doesn't draw animations** and says so.
    anim_base, anim_pal = 0, 0
    if sample_animation:
        trial, trial_base, trial_pal = map_animation(
            tiles, palettes, 1 if image_base else 0)
        if not trial_base:
            # Without a palette this map doesn't draw animations. It is the
            # same that is done with the raindrops: it is declared and it goes
            # on.
            print("  map %d: WARNING, battle animations aren't drawn "
                  "here: the map already uses the %d sprite palettes and the "
                  "box needs a whole one" % (map_id, OBJ_PALETTES))
        else:
            # The VRAM, instead, **stops**: whether it fits depends on the
            # tile layout and not on the palettes. It stopped because the
            # Python reference couldn't recompute it without redoing the whole
            # bank; without it, it could warn and go on, as with the palettes.
            count = len(trial) // 32
            try:
                layout = vram_layout(len(tile_data) // BYTES_PER_TILE, count,
                                     len(above_data[0]) // 32)
            except SystemExit:
                layout = None
            if layout is None or count > layout["sprites"][1]:
                sys.exit(
                    "map %d: shows battle animations and the %d tiles of its "
                    "box don't fit in the sprite bank: it spends %d of %d. "
                    "See `animacion_de_mapa`."
                    % (map_id, animation_mod.TILES, count,
                       layout["sprites"][1] if layout else 0))
            tiles, anim_base, anim_pal = trial, trial_base, trial_pal
            print("  map %d: battle animations are drawn in %d "
                  "tiles from %d, palette %d"
                  % (map_id, animation_mod.TILES, anim_base, anim_pal))
    # And the rows of the baked events start hidden: their tile is already
    # drawn in the map. The row is still whole —the event triggers, blocks the
    # way and is the target of a route like any other—, and `build_oam` skips
    # it without building an object, which is what is being saved.
    # `tile_pass` is left set on purpose: the cell is already resolved by the
    # map's table with the same bits, and if a page ever showed this row
    # again, the data it needs is there.
    for npc in npcs:
        if npc["event"] in baked:
            npc["visible"] = False
    table = npc_table(npcs, where, movable, animated_index, animates_still)
    # For each leader candidate, its palette and which pose bank its twelve
    # are in. The ROM computes nothing from the pose: it looks up the pointer
    # here and queues it.
    actors = []
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        if actor not in actors_with_graphic:
            # An actor with an empty graphic. `DummyHero`, 10, is like that:
            # its eight poses don't have an opaque pixel, and RM2k draws
            # nothing. It goes with the sentinel pointer and the ROM skips the
            # object.
            actors.append((actor, 0, None, []))
            continue
        # Its colors, in the same order as the `lookup` its poses were packed
        # with: `character_palette` returns the sorted palette and
        # `build_characters` indexes 1..15 over it. If the two orders drifted
        # apart, the hero would come out with its colors swapped around.
        own, _, _ = character_palette(
            images[a.charset], a.charset_index)
        actors.append((actor, palette_of[(a.charset, a.charset_index)],
                       animated_index[(a.charset, a.charset_index)],
                       [cgram_word(c) for c in own]))
    turn_tile = (block_tile(where["giro"][0]) if "giro" in where
                 else TURN_NONE)
    sprite = (tiles, palettes, where, table, actors, timer_base, timer_pal,
              animated, banks, route_gfx, rain_base, rain_pal,
              turn_tile, image_base, image_pal, anim_base, anim_pal)

    # The collision: one byte per 16x16 cell with the four direction bits
    # already resolved. All of RM2k's logic —that the upper layer rules unless
    # it is decoration, that wall faces are always crossed— is decided here,
    # not on the console.
    chipset = renderer.database.chipsets[game_map.chipset_id]
    flags = build_passability(chipset)
    passable = passability_map(game_map, flags)
    # The cells with an NPC are left out: if the hero started on one, both
    # would have the same sort key and which one stays on top would depend on
    # a tie-breaker that has no reason to match between the console and the
    # render. With **all** the ones drawn on some page: a tile left out of the
    # palettes still takes space.
    used = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
    start_x, start_y = map_start(
        renderer, map_id, passable, game_map.width, game_map.height, used)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("map %d has %d NPCs and %d fit in OAM"
                 % (map_id, len(table), NPC_MAX))
    if len(route_gfx) > ROUTE_GFX_MAX:
        sys.exit("map %d has %d graphics of command 34 and %d fit: see "
                 "ROUTE_GFX_MAX" % (map_id, len(route_gfx), ROUTE_GFX_MAX))

    print("Map %d %r: %dx%d cells of %dx%d px"
          % (map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d distinct colors, %d in CGRAM of %d available, %d merged"
          % (summary["colores"], summary["usados"], summary["presupuesto"],
             summary["fusionados"]))
    print("  %d unique tiles of %d cells (%.0f%% reuse)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprites: %d characters, %d slots, %d tiles in VRAM, %d palettes; "
          "%d with their twelve poses in the cartridge"
          % (len(characters), len(where), len(tiles) // 32, len(palettes),
             len(animated)))
    print("  %d NPCs with a CharSet out of %d events" % (len(table), len(game_map.events)))

    open_ones = sum(1 for b in passable if b == 0x0F)
    print("  collision: %d cells, %d open on all four sides (%.0f%%), "
          "the hero starts at (%d,%d)"
          % (len(passable), open_ones, 100.0 * open_ones / len(passable),
             start_x, start_y))

    print("  layer above the hero: %d tiles, %d colors in %d palette(s) "
          "from %d, %d merged"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    cells, blocks, block_pass, block_terrain, combos = build_blocks(
        game_map, tilemap, above_data[2], passable,
        game_map.width, game_map.height, chipset)
    print("  the map fits in %d 16x16 blocks for %d cells: %d B of "
          "grid plus %d B of table, against the %d B of the expanded tilemap"
          % (len(blocks) // BLOCK_BYTES, len(cells), 2 * len(cells),
             len(blocks), 2 * summary["celdas"]))
    windows_x = (len(tilemap[0]) + WINDOW_W - 1) // WINDOW_W
    windows_y = (len(tilemap) + WINDOW_H - 1) // WINDOW_H
    if windows_x > 1 or windows_y > 1:
        print("  it doesn't fit in the %dx%d window: the ROM is going to redraw"
              % (WINDOW_W, WINDOW_H))

    words = bytearray()
    for cell in cells:
        words += cell.to_bytes(2, "little")
    colors = bytearray()
    for word in cram:
        colors += word.to_bytes(2, "little")

    return {
        "id": map_id, "nombre": name,
        "tiles": tile_data, "cram": bytes(colors), "cram_words": cram,
        "tilemap": tilemap, "above": above_data, "sprite": sprite,
        # The graphics of command 34 as the pass that builds the bank numbered
        # them. `main()` compares against the ones it gathers compiling for
        # real: if the two passes drifted apart, the bytecode would carry
        # indices of a table that says something else.
        "graficos_de_ruta": route_graphics,
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        # Both grow while the pages are compiled, if some substitutes tiles:
        # see `Substitutions`. That is why they are mutable and are frozen
        # only when emitted.
        "bloques": blocks, "pass": block_pass, "terreno": block_terrain,
        "combos": combos,
        # The terrain of a cell **outside the map**: `GetTerrainTag` uses the
        # ChipSet's index 0, that is the first autotile, and not that of any
        # cell. See `op_terrain`.
        "terreno_fuera": rm2k.terrain_of(chipset, 0),
        "layout": vram_layout(
            len(tile_data) // BYTES_PER_TILE,
            len(sprite[0]) // 32 if sprite else 0,
            len(above_data[0]) // 32),
        "resumen": summary,
        "anim": anim_bytes(summary["animacion"]),
        "imagenes_fondo": summary["imagenes"],
        # The whole map is stored because the events' pages can't be compiled
        # until all the maps are there: a `Teleport` translates map ids to
        # table indices.
        "game_map": game_map,
        # For the page table: where each (CharSet, index, pose) ended up in
        # the sprite bank, which events change graphic with the page and which
        # of their graphics were left out of the palettes.
        "where": where,
        # For the turn toward the hero: which entry of `npc_poses` the twelve
        # poses of each graphic are in, which is the page's +30.
        "giro_k": {pair: animated_index[pair] for pair in animated},
        "giran": set(turning),
        "cambian": {npc["event"] for npc in npcs if npc["changes"]},
        # And the ones that only appear and disappear with it: the ones that
        # walk, whose graphic was pinned further up.
        "aparecen": {npc["event"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["event"]: npc["afuera"] for npc in npcs},
    }


if __name__ == "__main__":
    main()
