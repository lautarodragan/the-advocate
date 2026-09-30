"""`mapdata.inc`, the `.inc` that is assembled together with main.s: the
header constants, the tables of every map, the window and the font, the
screens, the menus, the battle, and what the save game is signed with.

Everything comes in already converted —the maps from `convert_map`, the
screens, the scenes, the audio— and `emit` only writes it.
"""

import json
import os
import sys
import zlib

from port import compiler, events
from rpgmaker import lcf
from rpgmaker import rm2k
from port import picture
from port import menus as menus_mod
from port import end_game as end_game_mod
from port import screens as screens_mod
from port import battle as battle_mod
from port import experience as X
from port import color as color_mod
from port import constants
from port import rules
from common import settings
from port.snes_format import (BYTES_PER_TILE, COLORS_PER_PALETTE, cgram_word,
                              entry, pack_tile)
from port.asm import block
from port.map_layers import (CGRAM_RESERVED, FAMILIES, PRIORITY_ABOVE,
                             window_palette)
from port.sprites import (OBJ_COLORS, OBJ_PRIORITY, OBJ_PRIORITY_ABOVE,
                          POSE_BYTES, SPRITE_POSES)
from port.obj_extras import TIMER_GLYPHS, TIMER_GLYPH_W, TIMER_X, TIMER_Y
from port.vram import (MAP_LAYOUT, SLOTS, SLOT_MAP, SLOT_TEXT_LEVEL,
                       SLOT_TEXT_MAX, SLOT_TEXT_WIDTH, SLOT_VRAM,
                       VRAM_ABOVE_MAP, WINDOW_BASES, items_border_first)
from port.message_window import (FONT_HEIGHT, FONT_PRE_CHAR, FONT_PRE_ROWS,
                                 FONT_WIDTH, WINDOW_COLS_INC, WINDOW_ROWS_INC,
                                 WINDOW_TEXT_COL, WINDOW_TEXT_COLS,
                                 WINDOW_TEXT_ROW, WINDOW_TEXT_ROWS, _columns,
                                 font_prerender)
from port.materials import (LZ2_CAP_ABOVE_AND_SPRITES, LZ2_CAP_ANIM,
                            LZ2_CAP_BACKDROP, LZ2_CAP_GRID, Materials,
                            compress_blocks, write_raw)
from port.map_record import (ACTOR_BYTES, ACTOR_COLORS, ANIM_FAM_STRIDE,
                             ANIM_STRIDE, EV_MAX, EV_STRIDE, FLASH_MAX,
                             MAP_STRIDE, NPC_MAX, NPC_STILL, NPC_STRIDE,
                             PAGE_BYTES, PARALLEL_MAX, ROUTE_EV_MAX,
                             ROUTE_GFX_MAX, TURN_NONE, anim_table, map_data,
                             map_table, offsets)
from port.battle_animations import animations_asm
from port.battle_scenes import scenes_asm


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
         battle_tables=None, troop_pages=None, compressed=None,
         enemy_hp=False, game_over=None, party_common=None):
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

    `party_common` is `{common event: its code}` of the equipment common
    events, compiled: see `events.PARTY_COMMON_EVENTS`.
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
        "; The teleport fade: the ticks from the jump's, which already\n"
        "; darkens, to the first live one, and of those the ramp is 24 going\n"
        "; down and 24 going up. The map is loaded on tick %d, in the black.\n"
        "; These numbers and the table below come from the fade constants of\n"
        "; tools/port/events.py.\n"
        "FADE_TOTAL      = %d\n"
        "FADE_RAMP       = %d\n"
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
           events.FADE_TOTAL,
           events.FADE_RAMP,
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
        # See `rm2k-snes-battle`, which leaves the segment in RODATA.
        handle.write(battle_tables["experience"])
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
                               party_common[n]) + "\n")
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
                         pairs, battle_tables["slots"],
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
        # deduplicates them. See `TroopPages` in the compiler's `troops.rs`
        # and `ba_page_test` in tools/runtime/battle_troop.s.
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
        pt = troop_pages or compiler.no_troop_pages()
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
        # front of the code, see `Trigger::header` in the compiler.
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
        # is about two hundred. `rm2k-snes-battle` writes them, and opens no
        # segment: they land in this RODATA. See `tools/runtime/encounters.s`.
        handle.write(battle_tables["encounters"])
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
        # this game. Who sounds at which moment is in `battle_audio`, in the
        # compiler, taken from easyrpg-player; only the numbers travel here.
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
