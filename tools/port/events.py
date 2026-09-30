#!/usr/bin/env python3
"""What the converter keeps of the event compiler.

The compiler —RM2k's event pages to the bytecode the ROM runs— is
`rm2k-snes-events` since 2026-09-29, in Rust: `port/compiler.py` says what
goes into its two calls and puts what comes back where the rest of the
converter reads it. The rule it keeps is the one this module had:

    **a page is emitted only if all its commands can be run.**

What stays here is what others read and is not the compiler: the numbers
the ROM's tables are emitted with (`mapdata.py`), the command codes a few
scans look for (`game_scan.py`, `baking.py`, `cases.py`), the registries the
compiler's answer is read into (`Songs`, `Troops`, `Trigger`), the indices it
answers (`VARIABLE_SLOT`, `SKILL_SLOT`, `PARTY_COMMON_EVENTS`), which picture
takes the cartridge's place (`Pictures`), the escape tail `texts.py`
rebuilds boxes around, and the models the game's tests predict the ROM with
(`Encounters`, `key_value`, `PartyState`).

The whys of how each command compiles live next to the code that compiles
it, in the crate: `tools/rm2k-snes/events/src/compile.rs` and its
neighbors. What stays here is what protects code that is still here, or
that both sides share —the escapes and the box's header, the routes'
frequency, the songs' numbering, the troops' triggers—, and the notes the
runtime and `mapdata.inc` cite as "see X in events.py": until those
citations point at the crate, the note stays here too, with its copy
there.

The command codes come from tools/rpgmaker/event_codes.py, which is
generated from liblcf. Never from memory: the first version of the door
filter wrote them down by eye and three were wrong.
"""

import collections
import math
import os

from port import picture as picture_mod

# The opcodes' numbers, lengths and layout. **They are not declared here**:
# they come from `tools/snes/protocol/events.toml`, which belongs to both sides —this
# one and the interpreter in tools/runtime/interpreter*.s— and to neither. See
# tools/snes/protocol/README.md.
from port.event_opcodes import *   # noqa: F401,F403
from port.event_opcodes import OPCODE_SIZE, opcode_size  # noqa: F401

CONTROL_SWITCHES = 10210
TELEPORT = 10810

CHANGE_PARTY_MEMBERS = 10330

MOVE_EVENT = 11330
CHANGE_EVENT_LOCATION = 10860
TRADE_EVENT_LOCATIONS = 10870
TILE_SUBSTITUTION = 11750

SHAKE_SCREEN = 11050

PAN_LOCK, PAN_UNLOCK, PAN_SHIFT, PAN_RETURN = 0, 1, 2, 3

SHOW_MESSAGE = 10110
SHOW_MESSAGE_2 = 20110

# The escape codes this game's text uses: `\|` is a pause and `\^` closes the
# box without waiting for the player to press anything. Both are time and not
# text, and since 2026-09-13 both are done: they travel in the box's header
# —see `HEADER_LINES`— and the ROM's interpreter reads them from there.
#
# They are done for real and not by quietly deleting them, which was the cheap
# temptation: with `\^` the box closes on its own, so the ROM would be left
# waiting for an A that RM2k never asked for and the whole page would last as
# long as the player takes.
#
# **Any other escape still does not compile**, and that is on purpose: the
# three `\V` of the common events —the value of a variable inserted into the
# text— require composing the text when opening it, which is something else.
# Drawing them as two letters would show.
ESCAPE = "\\"
ESCAPE_PAUSE = "|"
ESCAPE_CLOSE = "^"

# What a `\|` costs. **It is not one second**: it is the
# `SetWaitForNonPrintable(61)` of `window_message.cpp`, with its comment next to
# it —"Despite documentation saying 1 second, RPG_RT waits for 61 frames"—. It
# is 61 and not 60, and that difference is exactly the kind of number that
# cannot be written from memory.
PAUSE_FRAMES = 61

# How many pauses fit in the box's header. The most the game uses is three in a
# row (`\|\|\|\^`, twice, on map 108); more than fifteen does not fit in the
# high nibble and the page does not compile instead of lasting too little.
PAUSES_MAX = 15


def escape_tail(lines):
    r"""The lines without their escape tail, how many pauses it has and
    whether it closes on its own.

    Across the 328 maps both escapes appear **always as a tail at the end of
    the box's last line** —measured: 40 boxes, and not one with an escape in
    the middle nor on a line other than the last—, so that is the only thing
    accepted. One in the middle still does not compile, which is the honest
    thing: with the window drawn all at once, a pause halfway through the text
    cannot be modeled without making up how much text had been drawn.

    The tail may carry spaces in between —it happens only once, in map 98's
    `RunDirectorScene`, which writes `\| \| \| \^`— and it eats them: a space
    at the end of a line does not draw a single pixel, so removing it does not
    change the screen.

    The compiler has the same rule, in its `messages.rs`: this copy is the
    one `texts.py` rebuilds the boxes around, before the compiler sees them.
    `rm2k-snes/events/tests/escapes.json` holds the two together.
    """
    lines = list(lines)
    pauses = 0
    auto_close = False
    if lines:
        text = lines[-1]
        i = cut = len(text)
        escapes = 0
        while i > 0:
            if i >= 2 and text[i - 2] == ESCAPE \
                    and text[i - 1] in (ESCAPE_PAUSE, ESCAPE_CLOSE):
                i -= 2
                cut = i
                escapes += 1
            elif text[i - 1] == " ":
                i -= 1
            else:
                break
        if escapes:
            tail = text[cut:]
            pauses = tail.count(ESCAPE + ESCAPE_PAUSE)
            auto_close = ESCAPE + ESCAPE_CLOSE in tail
            lines[-1] = text[:cut]
    if any(ESCAPE in t for t in lines) or pauses > PAUSES_MAX:
        raise CannotCompile()
    return tuple(lines), pauses, auto_close


ROUTE_HERO = 10001
ROUTE_THIS_EVENT = 10005                    # "this event", the page's owner

# What a `wait` inside a forced route costs. **It is not one frame**: in RM2k
# it is `SetMaxStopCountForWait`, which gives `20 + (1 << (8 - frecuencia))`,
# and with frequency 8 —the only one this repo accepts, see `ROUTE_FREQUENCY`—
# that is twenty.
ROUTE_WAIT_FRAMES = 20

# The frequency a forced route is walked at. It governs two things: how long
# it waits between one command and the next —`1 << (9 - frecuencia)` frames,
# and zero with 8— and how long a `wait` lasts. Only 8 is accepted, which is
# the one 3463 of the game's 3509 routes use and **all** of those of the
# pages that compile; with any other the wait between commands has to be
# modeled, and since 2026-09-04 it is: it is RM2k's stop counter. After each
# command the character stays still `max_stop_count` frames
# —`SetMaxStopCountForStep` after a step, `ForTurn` after a turn, `ForWait` on
# a `wait`— and with 8 the first two give zero, which is why the model of
# "turning is free and steps go back to back" was exact without knowing it.
# The game uses 2, 3, 4, 7 and 8; 1 would give 256 frames after each step,
# which do not fit in the ROM's wait byte, and nobody uses it: it is
# rejected.
ROUTE_FREQUENCY = 8
ROUTE_FREQUENCY_MIN = 2


def wait_after_step(frequency):
    """`GetMaxStopCountForStep`: the frames standing still after a step."""
    return 0 if frequency >= 8 else 1 << (9 - frequency)


def wait_after_turn(frequency):
    """`GetMaxStopCountForTurn`: the frames standing still after a turn. The
    `wait` is `ROUTE_WAIT_FRAMES` plus this."""
    return 0 if frequency >= 8 else 1 << (8 - frequency)


# How far a step advances per frame by speed, out of 256 per cell: it is the
# `1 << (1 + GetMoveSpeed())` of `Game_Character::UpdateMovement`. 4 is the
# hero's, 32 per frame, that is two pixels and eight frames per cell; 3 is
# sixteen frames and 2 thirty-two, at half a pixel per frame.
STEP_PER_SPEED = (4, 8, 16, 32, 64, 128)

# A jump lasts as long as `remaining_step` takes to go from 256 to 0 at
# `jump_speed[move_speed - 1]` per frame. At speed 4 —the hero's at the
# start— that is 24 per frame, that is eleven frames, and **it does not
# depend on the distance**: jumping five cells costs the same as jumping in
# place. The ROM has the same table in `jump_per_speed`; this is the one the
# tests look at.
JUMP_STEP = 256
JUMP_PER_SPEED = (8, 12, 16, 24, 32, 64)

FLASH_SPRITE = 11320

# ChangePartyMembers: the first parameter says whether it adds or removes, the
# second where the actor's id comes from, and the third the id. From liblcf
# and `Game_Interpreter::CommandChangePartyMember` in easyrpg-player.
PARTY_ADD, PARTY_REMOVE = 0, 1
PARTY_FIXED_ID = 0
PARTY_MAX = 4           # `Game_Party::AddActor` does not add if there are four

WEATHER_EFFECTS = 11070

PLAY_SOUND = 11550

SHOW_BATTLE_ANIMATION = 11210

CHANGE_ITEMS = 10320

SHOW_PICTURE = 11110

CONTROL_VARS = 10220

OPEN_SHOP = 10720


class Songs:
    """The songs the game's `PlayBGM`s ask for, numbered in the order they
    appear.

    The compiler numbers them —the bytecode carries an index and not a
    name— and the answer is read into this, over which the music numbers
    what it adds after: see `compiler.songs`. The ROM
    carries **the first `SONG_TOTAL`**, which are the ones that fit in ARAM:
    all of them share the samples and the shared bank lives in the SPC700's
    64 KB, which are uploaded only once at boot. A higher index is a song
    that did not fit and does not sound.

    Numbering all of them and not only the ones that fit is what keeps the
    bytecode from depending on which were chosen. Until 2026-09-06 only one
    fit and this was already written this way; the day four fit nothing
    different had to be recompiled.
    """

    def __init__(self):
        self.names = []
        # And the `PlaySound` effects, the same way: each combination of
        # effect, volume, tempo and pan is an entry, and the bytecode carries
        # its index. They live here and not apart because this is what the
        # converter already passes from compilation to compilation.
        self.sounds = []
        # And who asks for what: the converter puts in `game_map` the index of the
        # map it is compiling, and each song and each effect is noted in its
        # own, in the order they appear. It is what builds each map's audio
        # package: see `package_load` in tools/runtime/audio_package.s.
        # And which ROM maps each one jumps to —`destinos`, indices into the
        # map table—, which is where it comes from which song may be playing
        # when a package is loaded: see `inherited_songs` in music.py.
        self.current_map = None
        self.per_map = {}
        # And which `PlayBGM`s of each map are **exit ones**: see
        # `exit_songs`.
        self.exits = {}
        # And with which song each `Teleport` of each map jumps —None is
        # whatever is playing—: see `inherited_songs` in music.py.
        self.jumps = {}
        # How many effects went into a package, which the compiler counts to
        # know whether a command made one sound.
        self.requested = 0

    def _note(self, what, value):
        if self.current_map is None:
            return
        values = self.per_map.setdefault(
            self.current_map, {"temas": [], "sonidos": [], "destinos": []})[what]
        if value not in values:
            values.append(value)

    def index(self, name):
        if name not in self.names:
            self.names.append(name)
        self._note("temas", self.names.index(name))
        return self.names.index(name)

    def exit_songs(self, game_map):
        """The songs a map turns on only to leave: each of its `PlayBGM`s is
        followed by a jump to another map, with no effects or branches in
        between. In the game it is `lufsorr` on map 3: it plays after the
        sequence of effects, when none is left to play, and the map is left
        right away. So it has no reason to fit in ARAM with those effects: it
        goes in the **separate** package, it is uploaded if there is room,
        and if not its `PlayBGM` uploads it —see `exit_extra` in
        tools/runtime/audio_package.s—. It is from 2026-09-26."""
        return [t for t, is_exit in self.exits.get(game_map, {}).items() if is_exit]


# --- the opcodes we emit ----------------------------------------------------
# What each opcode carries and why is in the crate, next to the arm of
# `compile_command` that emits it. This one stays here too because
# tools/runtime/interpreter_save.s cites it:
#
# OP_SAVE: no operands: the save to the cartridge's SRAM.
#     It is `OpenSaveMenu`, but without a menu: there is
#     a single slot and the event overwrites it. What is
#     saved is said by `save_table` in
#     tools/runtime/bank1.s, which is the only place
#     where it is written. It costs no frame: in RM2k the
#     menu blocks, and here there is nothing to look at.

TIMER_OPERATION = 10230
TIMER_SET, TIMER_START, TIMER_STOP = 0, 1, 2

# `Game_Party::SetTimer` stores `segundos * 60 + 59`, not `segundos * 60`. The
# extra 59 are what makes the first second show whole: without them the timer
# would show the requested value for a single frame.
TIMER_EXTRA_FRAMES = 59

# ControlSwitches: the first parameter says where the ids come from and the
# last what to do with them (liblcf, ControlSwitches::Operation).
SWITCH_SINGLE, SWITCH_RANGE, SWITCH_INDIRECT = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

FRAMES_PER_SECOND = 60        # DEFAULT_FPS: it is what the timer counts with

# A step is sixteen pixels at WALK_SPEED = 2 per frame.
CELL_PX = 16
WALK_SPEED = 2
FRAMES_PER_CELL = CELL_PX // WALK_SPEED

# --- the teleport fade -------------------------------------------------------
#
# RM2k fades to black and back on **every** teleport, whether it changes map
# or not: in easyrpg-player's `Scene_Map::UpdateStage2` the `TeleportParams`
# always goes out with `erase_screen = true`, and
# `Scene_Map::StartPendingTeleport` asks for the transition the database says.
# A Blurred Line's is `transition_out = 0` and `transition_in = 0`, which in
# `Game_System::GetTransition`'s table are `TransitionFadeOut` and
# `TransitionFadeIn`, and `Transition::GetDefaultFrames` gives them **35
# frames** each. While the transition runs the game is frozen:
# `Scene::MainFunction` sees `IsAsyncPending()` and calls
# `Player::Update(false)`, which does not update the scene.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
FADE_FRAMES = 35
FADE_TOTAL = FADE_FRAMES * 2

# Of those 35, the ramp is 24 and the other 11 are plain black. The console
# cannot fade any other way: INIDISP's master brightness has sixteen steps and
# nothing more, so stretching the ramp over the 35 frames does not give a
# finer fade, it only repeats steps. And the black at the end is not padding:
# **it is where the map is loaded**. The load writes VRAM and CGRAM by DMA and
# costs six or seven frames; inside the black they are not seen and they do
# not run the clock, because the fade is counted in hardware frames and not
# in loop turns. Between the map being loaded —frame 24— and the ramp back
# leaving zero —frame 47— there are 23 frames of margin.
FADE_RAMP = 24
FADE_BLACK = FADE_FRAMES - FADE_RAMP
BRIGHTNESS_MAX = 15

# `ChangeScreenTransitions` (10690) changes that transition from then on:
# `[which, transition]`, with which 0 the teleport's erase and 1 its show —2
# to 5 are the battle's— and the transition an index into
# `Game_System::GetTransition`'s `fades` table. The game uses it in Boss
# Wick's hideout: zoom (16) to go to the vidcasts, mosaic (17) inside, and fade
# (0) on the way back. It is state that crosses the teleport, and in RM2k it
# travels in the save; here it does not —see `TRANSITION_ERASE` in
# tools/runtime/far_ram.s—.
#
# The ROM does two: **the mosaic**, with the PPU's MOSAIC register tied to the
# brightness ramp —like the battle's, `battle_fade.s`, and for the same
# reason: the map load has to fall inside the black—, and **the fade**, which
# is what goes for the ones the console does not do (the zoom is mode 7, and
# the map is in mode 3): taro decided it on 2026-09-26. See
# workflow/divergencias/las-transiciones-del-teletransporte.md.
#
# And **the cut** (19) for erasing: the screen to black in one frame
# —`TransitionCutOut`, which `Transition::GetDefaultFrames` makes last 1— and
# the new map loaded there; the way back is whatever the show says. Eisen's
# story (95 ev55) asks for it and, for "none" (20), 93 ev4: "none" compiles
# **to the cut**, and it is a divergence. In RM2k erasing with "none" does not
# touch the screen, so the fade back fades from the old map to the new one;
# the console has nothing to blend two frames with, and loading the map
# requires forced blanking: the closest thing is one frame of black. See
# workflow/divergencias/las-transiciones-del-teletransporte.md.
#
# The cut and "none" for **showing** do not compile: no ROM map uses them,
# and with nobody running them they would be a path no test walks. The
# battle's do not either: the ROM always uses the database's.
# What the bytecode carries: what the ROM does, and not the RM2k number.
TRANSITION_FADE, TRANSITION_MOSAIC, TRANSITION_CUT = 0, 1, 2


def fade_step(milliseconds):
    """How much the song's volume goes down per frame, in 1/65536.

    RM2k measures `FadeOutBGM` in milliseconds and the ROM counts frames, so
    the conversion is done here once: the 65816 does not divide without
    asking the hardware, and the hardware divider is eight bits —the 5000 ms
    of map 3's door are 300 frames and do not fit—.

    The level starts at 65535 and goes down by `step`; it is rounded up so
    the fade ends **within** the frames it asks for and not one after.
    """
    frames = max(1, milliseconds * FRAMES_PER_SECOND // 1000)
    return min(0xFFFF, -(-0x10000 // frames))


def fade_ramp():
    """The INIDISP brightness on each frame of the ramp, from black to full.

    It is a rounded straight line over the sixteen steps the master
    brightness has. The ROM does not compute it: the converter emits it in
    `mapdata.inc` as `fade_ramp`, so the number lives in a single
    place.
    """
    last = FADE_RAMP - 1
    return [(BRIGHTNESS_MAX * s + last // 2) // last
            for s in range(FADE_RAMP)]


# What triggers a page. Those of liblcf's `rpg::EventPage::Trigger`.
TRIGGER_ACTION = 0          # the player presses the action key facing it
TRIGGER_TOUCH_HERO = 1      # the hero walks onto it
# 2 is the collision —the event walks into the hero—, and it is not named here.
TRIGGER_AUTOSTART = 3
TRIGGER_PARALLEL = 4

# The ones the ROM knows how to trigger. The rest of an event's pages are
# emitted anyway —they are needed to know which one is active— but without
# code.
TRIGGERS = (TRIGGER_ACTION, TRIGGER_TOUCH_HERO, TRIGGER_AUTOSTART,
            TRIGGER_PARALLEL)

# TURN. An event with a graphic **turns toward the hero** when he triggers it,
# unless it has a fixed direction: it is the
# `SetFacing(GetDirectionToCharacter(GetPlayer()))` of
# `Game_Event::ScheduleForegroundExecution`. Since 2026-09-11 it is done, on
# both sides —before, it answered facing wherever it was—. The rules, which
# the ROM follows in `turn_fire` and company:
#
# * It turns if its page turns —a CharSet and an animation that does not fix
#   the direction, `pagina["gira"]`, which the compiler answers: see `turns`
#   in its `pages.rs`— and it has no route: with a route, the route decides
#   where it looks. The ones that walk on their own always have a route, so
#   they do not turn; in RM2k they pause while their page runs and they do,
#   and that is not modeled.
# * It looks toward the hero while **that event's page** lasts, and at the end
#   it goes back to its pose: `OnFinishForegroundEvent`'s `UpdateFacing`.
# * A refresh that changes its page undoes it if the new one does not turn or
#   draws something else; with the same graphic it stays turned, as in
#   `RefreshPage`. If the new one brings another CharSet with the same
#   direction and column, RM2k leaves it turned with the new drawing and here
#   it is undone: declared.
# * A route that grabs it undoes it, and so does loading a map.
#
# On the console a still one shares its VRAM slot with the other still ones
# of the same pose, so to turn it moves to **the map's turn slot** —a single
# one, because one turns at a time— and there the pose is uploaded from the
# twelve of its graphic, which is why they go into the cartridge. The one that
# walks or animates while still turns in its own slot.
#
# The animation types with a fixed direction are the `fixed_*` of
# `rpg::EventPage::AnimType`, plus `spin`, which turns on its own and does not
# obey either.


class CannotCompile(Exception):
    """This page has something the ROM does not know how to do yet."""


class MapEvents:
    """The map's events, as the compiler sees them.

    It exists for a reason that was measured and is paid dearly otherwise:
    **RM2k's event id is not the index in the ROM's table**. 39 maps of this
    game have gaps in the numbering —events deleted in the editor— so a
    route aimed at id 8 would move whichever is eighth in the list, which can
    be any other. The translation is done here, once, and the bytecode never
    sees an RM2k id again.

    `owner` is the event that owns the page being compiled, which is whom
    "this event" points to.
    """

    def __init__(self, game_map, owner=None):
        self.indices = {ev.id: n for n, ev in enumerate(game_map.events)}
        self.owner = owner

    def for_event(self, event_id):
        other = MapEvents.__new__(MapEvents)
        other.indices, other.owner = self.indices, event_id
        return other

    def route_target(self, who):
        """The target byte that goes in OP_ROUTE, or None if it cannot be
        moved.

        0 is the hero; for an event, its index plus one. Vehicles do not
        exist in this ROM and neither does an id the map does not have: both
        return None, which cuts the page.
        """
        if who == ROUTE_HERO:
            return 0
        if who == ROUTE_THIS_EVENT:
            who = self.owner
        if who in self.indices:
            return self.indices[who] + 1
        return None


# The header of a text box. The escapes go here and not in one more operand of
# `OP_MESSAGE` because here they come for free: a window's lines are four at
# most, so the byte that counts them had five unused bits. One more operand
# would cost one byte for each of the game's 2895 boxes and it would have to
# be emitted anyway in the 2855 that carry no tail.
#
#     bits 0-2   how many lines it carries, from 0 to 4
#     bit  3     it closes on its own: the `\^`
#     bits 4-7   how many pauses, from 0 to 15: the `\|`s
#
# The order is not arbitrary: the lines go at the bottom because it is what
# the ROM reads in the compositor's loop —`and #HEADER_LINES` and done— and
# the pauses at the top because they are read only once, on opening, where an
# extra `lsr` does not show.
HEADER_LINES = 0x07
HEADER_AUTO_CLOSE = 0x08

# The `OP_MESSAGE` offset in the game's block counts by four bytes, so the
# block can be 256 KB with a 16-bit operand. It went by two from when the
# texts were reflowed for the window (`port/texts.py`) until 2026-09-27, when
# the main path of the world chapter went past 128 KB; the whole game is about
# 161 KB. It costs a byte and a half of padding per box, on average, against
# half a byte by two: step 3 was measured (half the padding, 192 KB, and a
# multiplication by three in the ROM) and a 24-bit operand (no padding but one
# more byte for each `OP_MESSAGE`, which outnumber the boxes), and neither
# saves what it complicates: see `workflow/tasks/*/mundo-3-el-espacio.md`.
# `msg_start` multiplies it by four, and an `.assert` there enforces that
# both sides of the math are the same: `MESSAGES_CAP`.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
MESSAGES_STEP = 4

# `ConditionalBranch` and its two closers. They come from `event_codes.py`,
# which is generated from liblcf: the doors' ones were written from memory
# once and three were wrong.
COND_BRANCH = 12010
COND_ELSE = 22010
COND_END = 22011

COND_GOLD = 3
# The inventory **already exists** —`OP_ITEM` and `FAR_ITEMS`, since
# 2026-09-10— so the line above is stale: the item branch is
# `GetItemCount(id) > 0`, exactly the same question as the page condition by
# item, which the ROM already answers by reading `FAR_ITEMS`. Equipment does
# not count, as in `conditions_ok`: `GetEquippedItemCount` asks for
# equipment, which there is none.
COND_ITEM = 4
COND_ACTOR = 5

# `actor->IsSkillLearned(p[3])`. Since 2026-09-21 it is state: the bit of the
# (actor, skill) pair in `FAR_SKILL`, which starts with what
# `rules.learned_skills` says from the LDB and which `ChangeSkills` turns on
# and off. The operand that travels is the pair's slot and not the skill; see
# `SKILL_SLOT`.
COND_ACTOR_SKILL = 4
# easyrpg's five `Get*Id()`s compared against `p[3]`: weapon, shield, armor,
# helmet and accessory. This **is** real state —`FAR_EQUIPMENT`, which the
# equipment screen writes and which travels in the save— and it starts from
# the LDB's `initial_equipment`. Asking about item 0 says yes as soon as there
# is an empty slot, which is what RM2k does; no page of the game does it.
COND_ACTOR_EQUIPMENT = 5
# The branch by variable: `[1, variable, value kind, value, comparison, has
# else]`. The kind is 0 for a constant and 1 for another variable; the
# comparison, `==`, `>=`, `<=`, `>`, `<` and `!=`, in that order, which is
# RM2k's. It compiles to OP_IF_VAR, not to OP_IF: it does not fit in seven
# bytes.
COND_VARIABLE = 1

# --- RM2k's variables ---------------------------------------------------------
#
# The game declares five thousand and uses **81**, the highest being 201. The
# ROM does not carry the five thousand: the converter looks at which variables
# the pages **of every map in the game** name and gives each one a **slot**,
# from zero up —`VARIABLE_SLOT`—, and the bytecode talks in slots. That way
# the RAM it costs is 162 bytes, they live in bank 1's RAM (`FAR_VARIABLES`)
# and travel in the saved game. The compiler builds the index, and
# `compiler.apply_indices` leaves it in `VARIABLE_SLOT`. Until
# the night of 2026-09-10 the index was of each ROM's maps —six variables on
# maps 1 to 10— and with that a game saved with one ROM was not valid for
# another with more maps: the slots shifted. With the whole game's index a
# variable's slot is the same in any ROM, and the save went from 256 to 512
# bytes of SRAM.
#
# They are **sixteen-bit signed**: RM2k carries them at 32 and caps them at
# ±999999, but none of the game's goes past a few hundred —timer seconds, a
# random 0 to 100, counters—. What does not fit in the word does not compile,
# which is more honest than truncating.
#
# OP_VAR: slot (byte), operation (byte), kind (byte), a (word), b (word)
# The top bit of the **flags byte** of every opcode that writes a variable
# —the operation in OP_VAR, the flags in OP_KEY, the mode in OP_TERRAIN and in
# OP_LOCATION—: whether this write asks for the page refresh.
#
# It is `Game_Map::SetNeedRefreshForVarChange`, which does **not** mark the
# refresh for any write: it asks the `map_cache`, which has the list of the
# variables some page condition of the loaded map looks at. Here that question
# does not need to be run: who looks at what is static per map and a page's
# bytecode is compiled **for its map**, so the converter answers it and on the
# console what is left is a `bpl`.
#
# Without this the port ran at **30 frames per second in half of Lashe City**:
# maps 8, 20, 23, 26, 28 and 32 have a parallel page that writes four
# variables per frame —the hero's coordinates against an event's— and each
# write asked for the whole refresh, which on map 8 is 68 events and 106 pages
# and **does not fit in a frame**. None of those four variables is looked at
# by any page condition, neither there nor on any other map of the game.
#
# **Until 2026-09-27 the bit went in the slot**, which that way fit in seven
# bits: 128 variables. The game names 127, and `MemorizeLocation` and
# `RecallToLocation` add nine more —127 to 129 of the droid tutorial and
# `DisplayNameMenu`, 158 to 160 and 169 to 171 of the opening menus—, so the
# bit moved to the flags byte, which in the three opcodes had the top one
# free, and the slot was left at eight bits: 256, which is what far RAM
# reserves between `FAR_VARIABLES` and `FAR_ITEMS`.
VAR_REFRESH = 0x80
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
VAR_SLOT_MAX = 0xFF
#
# OP_IF_VAR: slot (byte), kind (byte), comparison (byte), value (word),
#     destination (word): like OP_IF, the destination goes last for patching
# The inventory, since the night of 2026-09-10: one byte per LDB item in far
# RAM —`FAR_ITEMS`, right after the variables—, indexed by the RM2k number,
# and `ChangeItems` compiles to OP_ITEM with the item and how much is added,
# signed. The count stays in [0, ITEM_MAX], which is `Game_Party::AddItem`
# with RM2k's cap. The game uses it 509 times, always with constant item and
# quantity: the item by variable does not compile. With this the page
# condition by item is evaluated for real —`GetItemCount(id) > 0`, without
# equipment yet— and stops being "never active". Changing an item asks for
# the page refresh.
#
# OP_ITEM: item (word), delta (signed byte)
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ITEMS_N = 451       # the LDB's 450 items plus 0, which is not used;
                    # test_items.py enforces it against RPG_RT.ldb
ITEM_MAX = 99
# `ChangeSaveAccess`, `ChangeMainMenuAccess` and `ChangeEscapeAccess`, since
# there is a pause menu: **the bit** of the permission and whether it stays
# allowed. The ROM stores it in `FAR_ACCESS`. Saving from the save point does
# not look at it, like `OpenSaveMenu` in RM2k.
#
# The operand is the bit and not the permission's number, and that is from the
# third round: the ROM got it with an `inc a` on the number, which gives $01
# and $02 for the first two and **$03 for the third**, that is forbidding the
# other two things at once. With the bit set by the converter the opcode has
# no math to do and accepts whatever permissions are needed.
#
# OP_ACCESS: the bit in FAR_ACCESS (byte), allowed (byte)
# The weather, since 2026-09-11: `WeatherEffects` compiles to OP_WEATHER with
# the type and the power, and the rain is drawn. It is
# `Game_Screen::UpdateRain` with RM2k's rule —each drop lives twelve frames,
# goes down four pixels and moves one to the left per frame, and an off one is
# born with a ten percent chance at a random place— over the 256x224 screen,
# with **the drops scaled to that surface**: RM2k has 20, 60 and 100 at
# 320x240, and here they are 15, 45 and 75, the same density. The randomness
# is its own xorshift, seeded every time the weather changes; RM2k's cannot be
# reproduced.
#
# Each drop is a 4x16 streak with the slope of RM2k's, which is 6x24: two 8x8
# objects with priority 2, which the message window covers with the same mask
# as the "above" events. It is not semi-transparent: it is three opaque grays
# depending on how much life it has left, which is where RM2k fades it. The
# screen tone tints it, like everything else. They go last in OAM, so any
# character covers them, and if OAM fills up they get cut there.
#
# **The rain is attached to the map**, as in RM2k: there the drops' surface is
# the size of the screen, wraps around at the edges, and is pasted shifted by
# the pan, which is how much the camera moved. Here it is the same with a
# 256x256 surface: the drops live in bytes, each frame's step wraps on its
# own, and to draw them the map's scroll —shake included— is subtracted in
# eight bits. Until 2026-09-11 it was attached to the screen, and taro saw it
# while walking. Of the surface 224 of the 256 lines are seen: the on-screen
# density is the same as before, with drops that are also born in the band
# that is not seen.
#
# The ten percent chance is `azar & 255 < 26`, 10.2%: with `% 100` the ROM
# spent the divider on every off drop of every frame.
#
# OP_WEATHER: type, power
WEATHER_RAIN = 1
RAIN_DROPS = (15, 45, 75)
RAIN_LIFE = 12
RAIN_SPAWN = 26    # out of 256
RAIN_SEED = 0x1D2B
RAIN_COLORS = ((16, 16, 18), (11, 11, 13), (6, 6, 7))   # 5-bit


def rain_pixels(x, y):
    """The pixels of a drop with its corner at (x, y): a 4x16 streak going
    down to the left, one pixel every four rows."""
    return [(x + 3 - r // 4, y + r) for r in range(16)]


# The battle animations on the map, since 2026-09-11: their sounds and their
# flashes, **without the drawing**. `ShowBattleAnimation` compiles to
# OP_ANIMATION with the whole timeline inside: how many entries and, for each
# one, eight bytes —the tick it fires at, counted from the command's, the type
# and six of data—. It is what `BattleAnimation::Update` does with the
# animation's `timings`: on the even frame `2 * (frame - 1)` the effect plays
# and the flash of the screen or of the target event starts. There is a
# single one at a time —`Game_Screen::ShowBattleAnimation` replaces the
# previous one— and it advances once per frame **before** the flashes, which
# is where `Game_Screen::Update` puts it. With "wait", the page waits for as
# long as it lasts: two frames per animation frame. See `battle_anim_tick` in
# tools/runtime/battle_animation.s.
#
# The flash is not exactly RM2k's: there the power is
# `min((7 - (d + 1) / 2) * potencia / 6, 31)` for ten frames, in steps; here
# it is a `FlashScreen` or a `FlashSprite` that starts at the first and goes
# down linearly over ten frames. It is the same light and it
# lasts the same.
#
# OP_ANIMATION: n, and n entries of ANIM_ENTRY_BYTES bytes
ANIM_ENTRY_BYTES = 8
ANIM_SOUND, ANIM_SCREEN_FLASH, ANIM_FLASH = 0, 1, 2

ANIMATIONS = {}
# The **drawing**, since 2026-09-12. The opcode carries two more bytes: the
# RM2k animation number as is —180 at most, so it fits in one— and what it is
# drawn over. The number goes raw and not as an index of ours on purpose: the
# ROM looks it up in `anim_battle`, a table by number, so neither end has
# to carry a counter the other one guesses. See `animation.py`.
#
# `ANIM_NO_DRAWING` is "this animation is not drawn", and it is used by the
# ones RM2k repeats three by three to cover the screen —`global`—, which are
# not done.
ANIM_NO_DRAWING = 0xFF
ANIM_TARGET_SCREEN = 0xFF     # "screen" scope: goes to the center, no target

# --- the battle -------------------------------------------------------------
#
# `EnemyEncounter` and its three handlers. It is the sibling of `OP_CHOICE`:
# the command opens a screen that blocks, and **the outcome chooses where the
# page continues**, so the opcode carries the three destinations and the
# converter patches them when closing the block, same as a choice's options.
#
# The troop number goes **as RM2k's** and not as an index of ours, on
# purpose: which ones go in the cartridge is decided by the converter looking
# at all the pages, and if the bytecode carried the index, the same number
# would mean another troop depending on which maps each ROM carries. With the
# RM2k number inside, a page's bytecode is always the same; the ROM resolves
# it by looking it up in `troop_id`, and a troop that is not there is a battle
# that does not happen and goes out through the victory branch.
#
# The destinations are **absolute within the page**, like `OP_IF`'s. A
# handler the page does not have points to the end of the block, that is to
# the `EndBattle`, which is what RM2k does when the sub-index has no branch.
#
# OP_BATTLE: troop (word), victory (word), escape (word), defeat (word)
# The destination that means "this does not continue: this is a Game Over".
# It goes in the defeat's place when the `EnemyEncounter` carries
# `defeat_mode` 0, which in RM2k is `Scene_Gameover`. It is an impossible
# destination —all three are absolute within the page and none in the game
# reaches 64 KB— so no new opcode or extra byte per battle is needed. The ROM
# looks at it in `op_battle`.
BATTLE_LOSE = 0xFFFF

# The two actor questions that do not fit in `OP_IF`, since 2026-09-13: "does
# it have this item equipped?" and "does it know this skill?". They do not fit
# because they carry **two** operands —the actor and the item or the skill—
# and `OP_IF` has a single one; the actor fits in a byte because the LDB has
# 60 and `ACTORS_N` counts them, and the data does not, because the items go
# up to 450.
#
# It carries no polarity: RM2k gives none to these two —the branch below is
# the `else`— same as to "is in the party". The destination goes last, as in
# all of them, because it is what `with_dest` patches when closing the
# branch.
#
# OP_IF_ACTOR: sub (byte), actor (byte), data (word), destination (word)

# The picture of a `ShowPicture`, since 2026-09-12. The ROM carries **a
# single one** —see `Pictures`— and that is why the three opcodes do not say
# which: they say what to do to it.
#
#   OP_PICTURE        r, g, b, sat (bytes, 100 neutral): puts it up with that
#                     tone.
#   OP_PICTURE_MOVE  the tone it goes to, and in how many frames. It does not
#                    cut the frame: if the page waits, the converter puts an
#                    OP_DELAY after it, as with `FlashScreen` and the shake.
#   OP_PICTURE_ERASE takes it down.
#
# **The picture's fade is the tone and not the transparency**, which is what
# had to be checked: the two `MovePicture`s of the "1 year earlier" page leave
# `top_trans` at 0 and move (r, g, b) between 0 and 100 with the saturation
# still at 100. So the image appears **black**, goes up to its color and back
# to black; on the console that is tinting its fifteen CGRAM entries, which is
# exactly the math the screen tint already did.
#
# OP_PICTURE: r, g, b, sat
#
# OP_PICTURE_MOVE: r, g, b, sat, frames (byte)
# How many frames a `MovePicture` can last to fit in `OP_PICTURE_MOVE`'s byte.
# The page's two last 210 and 120.

# `ChangeSpriteAssociation`: actor (byte) and which graphic of the map's table
# (byte). It is the same as move command 34 but on an **actor**, and the
# two differences come from there:
#
# * **It survives the map change**, because in RM2k it belongs to the actor
#   and not to `Game_Player`. That is why its index comes from the slots
#   the graphics table of every map reserves for it —see `associations` in
#   the compiler's indices— and not from the map's free
#   numbering.
# * **It is stored per actor and shows only if that actor leads.** The one
#   that does not lead is not drawn, so the change stays waiting; the ROM
#   resolves it in `pick_hero_graphic`, which is the only one that decides
#   what the hero is drawn with.
#
# And one thing that **is not** done: if the graphic is not in the map's
# sprite bank, the actor keeps its own from the LDB instead of stopping being
# drawn. It is the difference with command 34, which there hides the row, and
# it is chosen: here the target is the hero, and an invisible hero on a map
# where the CharSet did not fit is worse than a hero with the old graphic.
#
# OP_ACTOR_SPRITE: actor (byte), graphic (byte)

# `KeyInputProc`: variable slot (byte) and which keys it looks at (byte).
#
# In RM2k it is `CommandKeyInputProc` plus the piece of
# `Game_Interpreter::Update` that handles it while it waits, and the value it
# stores comes from `CheckInput`: 1 down, 2 left, 3 right, 4 up, 5 the action
# key, 6 cancel. They are checked from highest to lowest, which is what the
# comment "RPG processes keys from highest variable value to lowest" says.
#
# The two forms are different programs and that is why they carry a flag:
#
#   no wait      reads what is pressed **now** —`Input::IsPressed`— and the
#                page continues on the same frame. It is the car's steering
#                wheel.
#   with wait    the page stops here until there is an **edge**
#                —`IsTriggered`— of any of the requested keys.
#
# The waiting one is emitted **twice**, the first with `KEY_START`: that
# one sets the variable to zero, eats whatever edge there was and returns
# control without looking at anything. It is RPG_RT's
# `Input::ResetTriggerKeys()`, which exists so the command does not eat the
# same key that just closed a message —and in this game the 23 waits come
# right after a `ShowMessage`, so without it the sign would skip past—. Two
# opcodes and not a state byte because the interpreter has nowhere to keep
# it: the one that waits **rewinds its own cursor** and runs again frame after
# frame, so it cannot tell the first turn from the others.
KEY_WAIT   = 0x01    # bit 0 on purpose: `key_value` reads it with an `lsr`
KEY_DIRS     = 0x02
KEY_DECISION = 0x04
KEY_CANCEL = 0x08
KEY_START  = 0x10

# The value RM2k stores for each key, and from here also comes the order they
# are checked in: from highest to lowest.
KEY_VALUE_CANCEL = 6
KEY_VALUE_DECISION = 5
# By ROM direction: 0 up, 1 right, 2 down, 3 left.
KEY_VALUE_DIR = {0: 4, 1: 3, 3: 2, 2: 1}

# `ChangeEventLocation` with the cell **in two variables**, which is RM2k's
# other `LUGAR`: same effects as `OP_PLACE` —`MoveTo`, the cell changes right
# away and the step in progress is cut— but the two numbers are read when it
# runs.
#
# It goes in its own opcode and not in a bit of `OP_PLACE` because the
# operands are different: two one-byte slots against two words. `OPCODE_SIZE`
# is a table, so an opcode whose size depends on a bit cannot be walked by
# either the converter or the ROM.
#
# What it unlocks is **one page**, measured over the whole game, and there are
# 129 occurrences in 32 pages: the other 31 are held back by something else
# anyway. That page is the one that matters: the engine of the stones
# minigame on map 11, which without this cannot place the stone where the
# player is standing and therefore none can be thrown.
#
# OP_PLACE_VAR: target (byte, as in OP_PLACE), slot of x
#     (byte), slot of y (byte)
#
# OP_LOCATION: mode (byte), and the slots of the map, x and y (a byte each).
#     `MemorizeLocation` and `RecallToLocation` are the same opcode because
#     they are the same location read or written: bit 0 of the mode says
#     which —`PLACE_JUMP`, in the compiler—, and when memorizing, which is
#     what writes the three variables, bits 7, 6 and 5 are the VAR_REFRESH
#     of each of those writes. **The map in the variable is
#     the RM2k id**, which is what any other page reads and writes; the ROM
#     translates it with `map_rm2k`. They unlock 55 pages of Lashe City's
#     milestone 3 —the plant's floors, 28 on 60 and 26 on 62, and the droid
#     tutorial— and they are what holds back the most pages in the whole
#     game.
#
# OP_MEMORIZED_BGM: 0 remember the song that plays, 1 put it back.


def key_value(flags, pressed):
    """Which value the variable gets with these keys pressed.

    `pressed` is the set of what the player is holding: integers 0 to 3
    for the directions, "a" and "b" for the two keys. It is what
    `test_tecla.py` expects from `op_key`, and the order is `CheckInput`'s.

    **Which set is passed depends on the form of the command**, and the
    caller decides that: the waiting one looks at this frame's **edges**
    —`Input::IsTriggered`— and the non-waiting one at what is held
    —`Input::IsPressed`—. Here they cannot be told apart: both are "what
    counts as pressed" for this question.
    """
    if flags & KEY_CANCEL and "b" in pressed:
        return KEY_VALUE_CANCEL
    if flags & KEY_DECISION and "a" in pressed:
        return KEY_VALUE_DECISION
    if flags & KEY_DIRS:
        for direction in (0, 1, 3, 2):          # up, right, left, down
            if direction in pressed:
                return KEY_VALUE_DIR[direction]
    return 0

ENEMY_ENCOUNTER = 10710

# Where the backdrop comes from, parameter [2] of `CommandEnemyEncounter`: 0
# the local one —the map's, or that of the terrain the hero stands on: it is
# `Game_Map::SetupBattle`—, 1 the one the command names and 2 that of a given
# terrain, which is RM2k3's.
BATTLE_BACKDROP_OF_PLACE = 0
BATTLE_BACKDROP_OF_COMMAND = 1
# The backdrop of a troop that fights with the local one: it is not known when
# compiling, because it depends on where the hero is. See
# `encounter_backdrop`.
PLACE_BACKDROP = ("del lugar",)
# The troop pages' command that changes the backdrop mid-battle. The game does
# not use it, and the port does not compile it; it is swept for the names it
# gives, so that `named_backdrops` is the whole game's.
CHANGE_BATTLE_BG = 13210


def database(game_dir):
    """The game's LDB, **for reading**: the `indexar_*`s and the sweeps
    share it, which used to load it each on its own.

    None of the ones asking for it here modifies it, and that is why it can
    be the same object. It is memoized while nothing that builds it changes:
    the dump's files and the fork's ChipSets —name, date and size— and the
    two `lcf` hooks, which change what is read.
    """
    from rpgmaker import fork, lcf
    path = os.path.join(game_dir, "RPG_RT.ldb")
    fingerprint = [path, lcf.REFIT_TEXTS, lcf.DECORATE_TRANSLUCENT]
    for folder in (os.path.join(lcf.dump_dir(path), "db"), fork.chipsets_folder()):
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                state = os.stat(os.path.join(folder, name))
                fingerprint.append((folder, name, state.st_mtime_ns,
                                    state.st_size))
    fingerprint = tuple(fingerprint)
    if _BASE[:1] != [fingerprint]:
        _BASE[:] = [fingerprint, lcf.Database(path)]
    return _BASE[1]


_BASE = []

# The `Songs.per_map` key where the battle's audio goes. It is not a map: it
# is **an audio package of its own**, which the ROM loads when opening the
# battle and unloads when closing it.
#
# It goes separately and not ahead of the map's package, and that is
# measured: the battle song is 18 samples and 51,480 B of ARAM's 64,512, so
# putting it in map 2's package the 24 effects of that map —49,068 B, which
# all fit today— dropped almost entirely. With its own package the map pays
# nothing while there is no battle.
BATTLE_PACKAGE = "batalla"


class Pictures:
    """The only picture that goes into the cartridge, and which commands
    move it.

    The converter builds one, and the decision is here and not in the
    compiler: to know whether a picture fits it has to be converted, which
    is the images' business. The compiler is told which `ShowPicture` took
    the place.

    **A single one per ROM**, and that is the decision that bounds the
    scope. It takes a whole sprite palette —fifteen colors that cannot be
    merged with anyone's, because the fade tints them all— and two rows of
    blocks of the sprite bank. A second picture would require deciding how
    many of those there are to share, and for that one first has to know how
    many of the game's `ShowPicture`s can be drawn; today the answer is in
    the report and not in the code.

    The one that does not fit is still accepted without being done, as
    before: cutting the page would take away from the game the eight that
    compile today.
    """

    def __init__(self, game_dir):
        self.game_dir = game_dir
        self.name = None      # the picture that took the slot
        self.info = None        # what `picture.convert` got from it
        self.number = None      # the RM2k picture number that shows it
        self.where = None       # where its ShowPicture centered it

    def _read(self, name):
        import os
        from PIL import Image
        path = os.path.join(self.game_dir, "Picture", name + ".png")
        if not os.path.exists(path):
            return None
        return Image.open(path)

    def choose(self, game_maps):
        """Which of the ROM's `ShowPicture`s takes the slot.

        It is decided **before compiling a single page** and looking at all
        of the cartridge's maps in table order, and not by order of arrival:
        that way the choice does not depend on the order the maps are
        compiled in.
        """
        if self.name is not None:
            return self.info    # the slot is already taken
        for game_map in game_maps:
            for event in game_map.events:
                for page in event.pages:
                    for cmd in page.commands:
                        if cmd.code != SHOW_PICTURE:
                            continue
                        if not picture_fits(cmd.parameters):
                            continue
                        if cmd.parameters[7]:
                            continue    # the PNG's transparent color
                        im = self._read(cmd.string)
                        if im is None:
                            continue
                        p = cmd.parameters
                        info = picture_mod.convert(im, p[2], p[3])
                        if not picture_mod.fits(info):
                            continue
                        self.name, self.info = cmd.string, info
                        self.number, self.where = p[0], (p[2], p[3])
                        return info
        return None


def index_animations(game_dir):
    """The LDB's battle animations, by id: their frames and their timings,
    with liblcf's default values —the decoder omits the ones that are not
    there—. The converter and the tests that compile pages call it."""
    db = database(game_dir)
    ANIMATIONS.clear()
    for number, anim in db.decode().get("animations", {}).items():
        timings = []
        for _i, t in sorted((anim.get("timings") or {}).items()):
            sound_effect = t.get("se") or {}
            timings.append({
                "frame": t.get("frame", 0),
                "se": (sound_effect.get("name", ""), sound_effect.get("volume", 100),
                       sound_effect.get("tempo", 100), sound_effect.get("balance", 50)),
                "alcance": t.get("flash_scope", 0),
                "rgb": (t.get("flash_red", 31), t.get("flash_green", 31),
                        t.get("flash_blue", 31)),
                "fuerza": t.get("flash_power", 31),
            })
        # And what is needed to **draw it**, since 2026-09-12: the `Battle`
        # sheet, each frame's cells and where the box goes. `animation.py`
        # reads it, being the only one that knows what to do with this;
        # here it is stored exactly as it comes from the LDB.
        frames = anim.get("frames") or {}
        ANIMATIONS[number] = {"cuadros": [frames[k].get("cells") or {}
                                          for k in sorted(frames)],
                              "timings": timings,
                              # The name the animation has in the editor
                              # —"Whole Magic Flame C"—: nobody looks at it
                              # to draw, its patch writes it so whoever
                              # reads the diff knows which one it is.
                              "nombre": anim.get("name", ""),
                              "imagen": anim.get("animation_name", ""),
                              "grande": bool(anim.get("large")),
                              "alcance": anim.get("scope", 0),
                              "posicion": anim.get("position", 1)}


# `ChangeEscapeAccess` is the permission to escape from a battle, and it is
# stored without being read: the battle looks at the escape, and that belongs
# to someone else. It is here anyway because it is what unlocks the most for
# what a bit costs —**30 of the game's 39 pages with `EnemyEncounter` that do
# not compile have it ahead**—, and because a command accepted without being
# done would be a lie: RM2k stores it in `Game_System` and it travels in the
# save, and here too.
# The ControlVars operations that compile: set, add, subtract. Multiply,
# divide and modulo are not used by any page of the game.
VAR_SET, VAR_ADD, VAR_SUBTRACT = 0, 1, 2
# And where the operand comes from, with the RM2k number: a constant, another
# variable, a random number between a and b, or "other", which here are the
# gold and the seconds the timer has left. The random one requires b - a to be
# less than 256: the ROM divides with the hardware's eight-bit divider.
VAR_CONSTANT, VAR_VARIABLE, VAR_RANDOM, VAR_OTHER = 0, 1, 3, 7

# And kind 6: **a character's coordinates**. The sub-operands are those of
# easyrpg-player's `ControlVariables::Event` —the `op` of
# `game_interpreter_control_variables.cpp`—: 0 the map id, 1 x, 2 y, 3 where
# it faces, 4 and 5 the screen coordinates and 6 the event id. They are not
# from memory, which is the house rule.
#
# Of the 829 times this game uses it, **827 ask for x or y** and the other two
# for the screen x and y; nobody asks for the map id, the facing or the event
# id. So the ROM does 1 and 2, and the rest does not compile:
#
# * **0** in RM2k returns 0 for an event —an RPG_RT defect easyrpg copies—, so
#   doing it would be copying a defect nobody uses;
# * **3** returns 8, 6, 2 or 4 —the numeric keypad— and not 0..3;
# * **4** and **5** are screen pixels, and ours is 256x224 against RM2k's
#   320x240: the number the variable would end up with is not the original
#   game's. They are two occurrences in the whole game, and accepting them
#   would unlock **one** more page —measured, 5135 against 5136—: it is not
#   worth making up a coordinate that is not the one there for one page.
VAR_CHARACTER = 6
CHARACTER_X, CHARACTER_Y = 1, 2
CMP_EQUAL, CMP_GREATER_EQUAL, CMP_LESS_EQUAL, CMP_GREATER, CMP_LESS, \
    CMP_NOT_EQUAL = range(6)
# The random generator: a sixteen-bit xorshift —x ^= x << 7; x ^= x >> 9;
# x ^= x << 8— seeded at reset. There is no real entropy, on purpose: a page
# with randomness always gets the same sequence, and that is why what it
# draws can be frozen in a golden.
RANDOM_SEED = 0xACE1
TIMER_SET_VAR = 3     # the timer's fourth operation: the seconds from a
                        # variable. RM2k's three are 0, 1 and 2.

VARIABLE_SLOT = {}      # RM2k variable -> slot in the ROM


def game_map_ids(game_dir):
    """The numbers of all the maps in the game, in order."""
    import glob
    return sorted(int(os.path.basename(p)[3:7]) for p in
                  glob.glob(os.path.join(game_dir, "Map[0-9][0-9][0-9][0-9].lmu")))


def sweep_maps(game_dir, map_ids, sweep):
    """The union of `sweep(game_map)` —a set— over those maps.

    The sweep of `named_backdrops` loads the game's 328 maps, and loading
    them is almost all it costs: they run in parallel, in batches, and each
    batch returns the union of its own. The result is a set, so the order
    does not matter.
    """
    from rpgmaker import lcf
    from common.parallel import in_parallel
    paths = [os.path.join(game_dir, "Map%04d.lmu" % m) for m in map_ids]
    batches = max(1, min(len(paths), os.cpu_count() or 1))
    found = set()
    for part in in_parallel(
            lambda theirs: set().union(*(sweep(lcf.Map(r)) for r in theirs)),
            [paths[k::batches] for k in range(batches)]):
        found |= part
    return found


# **The parallel common events that only look at the equipment**: switch ->
# the common event. It is the tailored path of Lashe City's milestone 4, and in
# the game there is a single one: 37, `UpdateAG7 Skills`, parallel on switch
# 150, which takes AG7-17's seventeen skills away and gives it the one of each
# piece it has equipped.
#
# The ROM does not run parallel common events. Doing them for real —one more
# interpreter, running the body **on every frame** while the switch is on— is
# the general way, and it was measured on 2026-09-27 against this (see
# `workflow/tasks/*/lashe-4-ag7-en-la-pelea.md`): what ruled it out was not
# the cost but that it would also turn on 2 (`DisableSaving`, parallel
# **without a switch**, which turns saving off every time 236 is off), 3 and
# 8, and that changes `release` far beyond this milestone.
#
# A parallel one that only reads its switch and the equipment, and only
# writes skills, gives the same result on every frame until one of those two
# things changes, and what it writes depends on nobody but itself. So it is
# enough to run it **when they change**: when the switch turns on —the
# converter pastes the body after the `ControlSwitches` that turns it on, like
# a `CallEvent`— and when closing the menu, which is where the equipment is
# changed —the ROM runs it from `menu_screen`, see `equipment_commons` in
# tools/runtime/equipment_from_events.s—. It is what the droid tutorial says:
# "these abilities become available once you equip a particular component and
# exit the menu".
#
# What is left out: a page's `ChangeEquipment` on the actor the event looks
# at does not run it again. In the game there is none on 18.
PARTY_COMMON_EVENTS = {}

# --- which skills each actor knows, as state --------------------------------
#
# `ChangeSkills` teaches an actor skills and makes it forget them, and that is
# world state: it travels in the save, like the equipment. What the ROM stores
# is **one bit per (actor, skill) pair**, and not a list per actor, because the
# game teaches many at a time —actor 14 gets seventy set and removed in the
# common events— and a variable-length list in far RAM would require
# searching, sorted insertion and capping.
#
# The pairs are the ones the whole game may end up looking at, and no more:
# those of the LDB's learning table **at every level** —the day there is
# leveling up, `LearnLevelSkills` turns on the ones that apply—, the ones some
# `ChangeSkills` names and the ones some "knows the skill" branch asks about.
# A pair nobody names can neither change nor be asked about, so its bit is not
# needed. All of the game's maps and all common events are swept, whether they
# compile or not, for the same reason as the variables: that way a page that
# compiles later does not shift anyone else's slot, and a game saved with one
# ROM works with another.
#
# The order is by actor and then by skill, and it is not cosmetic: it leaves
# each actor's pairs together and sorted by number, which is the order
# `LearnSkill` leaves them in and the one the battle menu shows them in. That
# way the ROM builds the list by walking a stretch, without sorting anything.
#
# OP_SKILL: pair slot (word), learns (byte: 1 learns, 0 forgets)
SKILL_SLOT = {}   # (actor, skill) -> slot

CHANGE_SKILLS = 10440


def variable_slot(number):
    if number not in VARIABLE_SLOT:
        raise CannotCompile("variable %d has no slot in this ROM" % number)
    slot = VARIABLE_SLOT[number]
    if slot > VAR_SLOT_MAX:
        # The slot is a byte, and far RAM has room for 256.
        raise CannotCompile("slot %d does not fit in a byte: see VAR_SLOT_MAX"
                            % slot)
    return slot


def next_random(x):
    """The xorshift step, in sixteen bits."""
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x

# RM2k's gold cap: `Game_Party::GainGold` clamps to `MaxGoldValue()`, which
# by default is this.
GOLD_MAX = 999999

# The cursor, and what is put in front of the options that do not have it so
# the text does not shift from line to line.
CHOICE_CURSOR = ">"


class Troops:
    """The troops the compiled battles ask for, to know which tables to emit.

    Sibling of `Songs`, with a difference that matters: **the bytecode does
    not depend on it**. `Songs` numbers and the opcode carries the number;
    here the opcode carries the RM2k id and this only gathers the list, so a
    registry with other troops inside does not change a single byte of any
    page. It is what allows compiling a loose page without knowing which
    tables the cartridge has.
    """

    def __init__(self):
        self.ids = []
        # And which backdrop each one fights with, which is the text of the
        # `EnemyEncounter` itself —`SJBackdropABL04` on map 2— and not
        # something to look up in the LDB. It goes here and not in a
        # separate registry because it is a fact of the battle, like the
        # troop. See tools/port/scene.py.
        self.backdrops = {}


# `ShowHiddenMonster`, which only exists in battle: the troop member in that
# place —from 0, in troop order— stops being hidden. See OP_SHOW_ENEMY and
# `ba_show_hidden`.
SHOW_HIDDEN_MONSTER = 13150

# Which triggers the ROM knows how to look at, with their bit in
# `tpage_flags`: RM2k's six. The three from 2003 —an actor's or an enemy's
# turn, fatigue and an actor's command— do not exist in a 2000 game, and a
# page that asked for them is left out.
TROOP_TRIGGER_SWITCH_A = 0x01
TROOP_TRIGGER_SWITCH_B = 0x02
TROOP_TRIGGER_VARIABLE = 0x04
TROOP_TRIGGER_TURN = 0x08
TROOP_TRIGGER_ENEMY = 0x10
TROOP_TRIGGER_ACTOR = 0x20

# How many pages of a troop the battle notes as "already ran this turn", one
# byte each in `BA_PAGE_DONE`. It is a far RAM cap and not the game's: the
# converter stops if any troop goes over.
TROOP_PAGES_MAX = 32

# The triggers that carry a **header**: the turn and HP numbers do not go in
# per-page tables in bank 1 —which no longer has room for ten bytes for each
# of the five hundred— but in front of the page's code, in `troop_code`,
# which is in RODATA. See `Trigger::header` in the compiler's `troops.rs`,
# and `ba_page_header`.
TROOP_WITH_HEADER = (TROOP_TRIGGER_TURN | TROOP_TRIGGER_ENEMY
                     | TROOP_TRIGGER_ACTOR)
TROOP_HEADER_BYTES = 10

# The trigger of a troop page, with what the ROM reads from each one. The
# fields of what the page does not look at go at zero.
Trigger = collections.namedtuple("Trigger", (
    "flags", "switch_a", "switch_b", "slot", "value",
    "turn_base", "turn_mult", "enemy", "enemy_min", "enemy_max",
    "actor", "actor_min", "actor_max"))

# --- random encounters -------------------------------------------------------
#
# Everything here comes from easyrpg-player —`Game_Player::UpdateEncounterSteps`,
# `Game_Map::GetEncountersAt` and `Game_Map::PrepareEncounter`— and not from
# intuition, which in this repo has already cost three times.
#
# **Where the data lives**: not in the `.lmu` but in the tree, `RPG_RT.lmt`.
# Each node —map or *area*— carries `encounters` (a list of troops),
# `encounter_steps` (25 by default, 0 = off) and `area_rect`. An area is a
# type 2 node: it has no `.lmu`, hangs from a map and covers a rectangle of it.
# See `lcf.TreeMap`.
#
# **How it triggers**, step by step of the hero and only those from the pad —a
# forced route leaves through `IsMoveRouteOverwritten` before `IncSteps`, so
# it does not count—:
#
#     accumulated += encounter_rate of the terrain it stands on
#     ratio = accumulated / encounter_steps         (integer)
#     while ratio >= TABLE[idx + 1][0]: idx++       (idx never goes down)
#     p = (1 / encounter_steps) * pmod * (rate / 100)
#     if it hits, accumulated = 0 and idx = 0, and an encounter is pending
#
# The pending one is collected on the next frame, with the hero already
# standing: the map's troops plus those of each area covering its cell are
# gathered and one is chosen at random. If there is none —the hero is outside
# all areas— nothing happens, which is what `PrepareEncounter` does when it
# returns `false`.
#
# **Two simplifications, both measured over the whole game** and enforced by
# `rom/pruebas/herramientas/test_encuentros.py`, which is what keeps them
# from becoming a lie the day someone touches the data:
#
# * **the terrain changes nothing**: the eleven terrain tags the 53 maps with
#   encounters step on have `encounter_rate` 100, so the accumulated goes up
#   by 100 always and the `rate / 100` factor is 1;
# * **no troop filters by terrain**: the 129 the encounters name have an
#   empty `terrain_set`, and in RM2k empty means "on all of them".
#
# With that the model stays entirely in integers, which is what the console
# can do without floating point: see `enc_step_thresholds`. The compiler has
# the same note, next to its `ENC_TABLE`.

# The tree node type that is an area. See `lcf.TreeMap.map_types`.
TREE_AREA = 2

# `UpdateEncounterSteps`' table, as (minimum ratio, pmod exponent): easyrpg's
# eight `pmod`s are powers of two —1/16, 1/8, 1/4, 1/2, 2, 4, 8, 16— so here
# they go as shifts and the math needs no floats. The ninth row there is
# `{INT_MAX, 16.0}`, that is a cap that is never reached: the `while` does not
# go past the last of these.
ENC_TABLE = ((0, -4), (20, -3), (40, -2), (60, -1),
             (100, 1), (140, 2), (160, 3), (180, 4))

# The `encounter_rate` the accumulated goes up by: the terrain's, which in
# this game is 100 on the 53 maps with encounters. See above.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ENC_RATE = 100

# The seed of the encounters' randomness. It differs from `RANDOM_SEED` and
# from `BATTLE_SEED` on purpose, and for the same reason as that one:
# walking does not advance the map's randomness —a random `ControlVars` has
# to give the same with and without encounters—. All that is asked of it is
# not to be zero —the xorshift gets stuck— and to be the same in
# `Encounters` and in the ROM.
ENC_SEED = 0x5A17


def enc_base(steps):
    """The formula's `1 / encounter_steps`, in 1/65536.

    A step's chance is `pmod / pasos`, and `pmod` is a power of two: if the
    quotient is precomputed here, on the console what is left is a shift and
    a sixteen-bit comparison, with no division. **The truncation is part of
    the contract**: both sides use this same number. The cartridge's comes
    from `base` in `rm2k-snes-battle`, which does the same; this one is the
    model's and `ChangeEncounterSteps`', and the tests compare the ROM
    against it.

    Zero means off, which is what `encounter_steps` 0 means in RM2k.
    """
    return 0 if steps <= 0 else 0x10000 // steps


def enc_step_thresholds(steps):
    """At which step each row of `ENC_TABLE` is crossed, counting from zero.

    There the comparison is `ratio >= fila`, with `ratio = acumulado / pasos`
    integer and `acumulado = 100 * n`. Since the row is an integer,

        acumulado / pasos >= fila   <=>   100 * n >= fila * pasos

    that is `n >= ceil(fila * pasos / 100)`, which is what is emitted: seven
    bytes per map and not a single division on the console. The first row is
    0 and is not needed.
    """
    return [-(-row * steps // ENC_RATE) for row, _ in ENC_TABLE[1:]]


def enc_threshold(base, idx):
    """The step's chance, in 1/65536, or None if it is "always".

    `pmod` shifts `base` one way or the other. With small steps —the ones
    `ChangeEncounterSteps` sets, or a test ROM— `pmod / pasos` can go past 1,
    and there RM2k has certainty: `PercentChance` with `rate >= 1` always
    says yes. On the console that is the shift's carry.
    """
    shift = ENC_TABLE[idx][1]
    if shift < 0:
        return base >> -shift
    value = base << shift
    return None if value >= 0x10000 else value


def encounter_zones(tree, map_id, width, height):
    """A map's zones: its own and one per area that hangs from it.

    A zone is (left, top, right, bottom, troops) with the rectangle
    **half-open**, which is what `Rect::IsOutOfBounds` says: inside is
    `l <= x < r` and `t <= y < b`. The map's covers the whole map.

    The order is `GetEncountersAt`'s, which walks the tree by index: in this
    game no map has troops of its own **and** areas —measured—, so putting
    its own first cannot change which troop comes out.
    """
    zones = []
    if tree.encounters.get(map_id):
        zones.append((0, 0, width, height, list(tree.encounters[map_id])))
    for i in sorted(tree.map_types):
        if (tree.map_types[i] == TREE_AREA and tree.map_parents.get(i) == map_id
                and tree.encounters.get(i)):
            left, top, right, bottom = tree.area_rect[i]
            zones.append((left, top, right, bottom, list(tree.encounters[i])))
    return zones


class Encounters:
    """The encounter state of a game, the same on both sides.

    The tests use it; the ROM does the same with the tables the converter
    emits. Whoever changes it has to change `tools/runtime/` in the same
    commit: otherwise the model and the console stop being the same
    program.
    """

    def __init__(self, steps, zones, seed=ENC_SEED):
        self.zones = list(zones)
        self.set_steps(steps)
        self.seed = seed
        self.reset()

    def set_steps(self, steps):
        """The map's `encounter_steps`: on entering, and
        `ChangeEncounterSteps`."""
        self.steps = steps
        self.base = enc_base(steps) if self.zones else 0
        self.thresholds = enc_step_thresholds(steps)

    def reset(self):
        """The `SetTotalEncounterRate(0)` of `Game_Player::MoveTo`: every
        teleport —and every door— sets the accumulated to zero."""
        self.n = 0
        self.idx = 0
        self.pending = False

    def _roll(self):
        self.seed = next_random(self.seed)
        return self.seed

    def step(self):
        """One step of the hero with the pad. Returns whether an encounter
        was left pending."""
        if not self.base:
            self.n = 0
            self.idx = 0
            return False
        # It is capped at 255 because on the other side it is a byte. It
        # changes nothing and that needs saying: the game's highest threshold
        # is 153 steps —map 258, with 85—, so by the time `n` reached the cap
        # the row is already the last and is no longer looked at. But both
        # sides have to **count the same**, and there the counter does not
        # wrap around.
        self.n = min(255, self.n + 1)
        while (self.idx + 1 < len(ENC_TABLE)
               and self.n >= self.thresholds[self.idx]):
            self.idx += 1
        threshold = enc_threshold(self.base, self.idx)
        hit = threshold is None or self._roll() < threshold
        if hit:
            self.n = 0
            self.idx = 0
            self.pending = True
        return hit

    def candidates(self, x, y):
        """The troops that can be fought on that cell: the map's plus those
        of each area covering it. It is `GetEncountersAt`."""
        output = []
        for left, top, right, bottom, troops in self.zones:
            if left <= x < right and top <= y < bottom:
                output += troops
        return output

    def choose(self, x, y):
        """The next frame's `PrepareEncounter`: which troop is fought, or
        None if there is none on that cell."""
        self.pending = False
        troops = self.candidates(x, y)
        if not troops:
            return None
        return troops[self._roll() % len(troops)]


def encounter_backdrop(cmd):
    """The battle backdrop of an `EnemyEncounter`: the name it carries,
    `PLACE_BACKDROP`, or "" if none.

    Parameter `[2]` of `CommandEnemyEncounter` says where the backdrop comes
    from: 1 is "the one this command says", which is what 49 of the game's 51
    battles do, with the name in the string —empty is no backdrop—; 0 is the
    local one, `Game_Map::SetupBattle`, which is what the other two do (on
    105 and on 141), and the ROM resolves it when the battle starts. 2 is
    RM2k3's.
    """
    p = cmd.parameters
    if len(p) > 2 and p[2] == BATTLE_BACKDROP_OF_COMMAND:
        return cmd.string
    if len(p) > 2 and p[2] == BATTLE_BACKDROP_OF_PLACE:
        return PLACE_BACKDROP
    return ""


def command_backdrops(commands):
    """The battle backdrops these commands name: the `named_backdrops`
    sweep."""
    names = set()
    for cmd in commands:
        if cmd.code == ENEMY_ENCOUNTER:
            backdrop = encounter_backdrop(cmd)
            if backdrop and backdrop is not PLACE_BACKDROP:
                names.add(backdrop)
        elif cmd.code == CHANGE_BATTLE_BG and cmd.string:
            names.add(cmd.string)
    return names


def _map_backdrops(game_map):
    """The `named_backdrops` sweep over one map."""
    names = set()
    for event in game_map.events:
        for page in event.pages:
            names |= command_backdrops(page.commands)
    return names


def named_backdrops(game_dir):
    """The battle backdrops some command of the game names: the
    `EnemyEncounter`s and `ChangeBattleBG`s of all the maps, of the common
    events and of the troops' pages, whether they compile or not. The map
    tree's and the terrains' are added by `scene.game_backdrops`.
    """
    db = database(game_dir)
    names = sweep_maps(game_dir, game_map_ids(game_dir),
                       _map_backdrops)
    for commands in db.common_events.values():
        names |= command_backdrops(commands)
    for troop in db.troops.values():
        for page in troop.pages:
            names |= command_backdrops(page.commands)
    return names


# Where the two destinations go inside `OP_CELL_TEST`: see events.toml.
CELL_DEST_A = 10
CELL_DEST_B = 16
# The top two bits of each `OP_CELL_TEST` write, over the variable's offset:
# y instead of x, and the refresh. See `cell_test` in
# tools/runtime/interpreter_cells.s.
CELL_Y = 0x4000
CELL_REFRESH = 0x8000


def picture_fits(p):
    """Whether the parameters of a `ShowPicture` or a `MovePicture` fall
    within what the console's picture knows how to do.

    The indices come from easyrpg-player's `CommandShowPicture` and
    `CommandMovePicture`, **not from memory**: the color and the saturation
    go in 8..11 and the effect mode in 12, which is not what one would
    guess.
    """
    return (len(p) >= 14
            and p[1] == 0               # position by variable
            and p[4] == 0               # attached to the map
            and p[5] == 100             # the zoom
            and p[6] == 0               # translucent
            and p[11] == 100            # the saturation
            and p[12] == 0              # rotate or wave
            and all(0 <= v <= 200 for v in p[8:12]))


class PartyState:
    """The party, to simulate its changes when converting:
    `possible_leaders` in game_scan.py and `page_party` in cases.py. It is
    what is left of the Python interpreter's state, which went away with the
    reference; the ROM is the only one that runs the bytecode."""

    def __init__(self, party=()):
        # The party, in order. The hero's graphic is the first one's, so the
        # order decides which poses have to fit in VRAM.
        self.party = list(party)

    def change_party(self, operation, actor):
        """Adds or removes an actor, with RM2k's rules.

        Adding one who is already there does not duplicate it nor move it,
        adding with a full party does nothing, and removing one who is not
        there does nothing either: it is what
        `Game_Party::AddActor`/`RemoveActor` do in easyrpg-player, which also
        call `ResetGraphic` in both cases. It matters because the order
        decides who the leader is, that is which sprite is drawn.
        """
        if operation == PARTY_REMOVE:
            if actor in self.party:
                self.party.remove(actor)
        elif actor not in self.party and len(self.party) < PARTY_MAX:
            self.party.append(actor)

    def leader(self):
        return self.party[0] if self.party else None


# How much each opcode takes is derived from its declared arguments, so
# `OPCODE_SIZE` and `opcode_size` come from `opcodes.py`, generated from
# `tools/snes/protocol/events.toml`. They used to be written by hand, and there
# were two copies —one here and another in the converter—: this one kept the
# old OP_ROUTE when the new one added the frequency, and that was twelve
# suite cases in red.


# The screen shake, easyrpg's `Shake::NextPosition`:
#
#     amplitude = 1 + 2 * power
#     new       = -amplitude * sin((left * 4 * (speed + 2)) % 256 * pi / 128)
#     cut       = speed * amplitude / 8 + 1
#     position  = clamp(new, position - cut, position + cut)
#
# with `left` the frames it has left, and the position the pixels added to the
# camera when drawing the map —`GetDisplayX`—: the message window does not
# move. RPG_RT does it in floating point and truncates; here the sine is a
# 256-byte table at scale 127 and the division is integer, so the ROM may
# differ from RPG_RT by one pixel on some frame. The converter emits the table
# to mapdata.inc from this same list.
SHAKE_SINE = [round(math.sin(t * math.pi / 128) * 127) for t in range(256)]


def walk_code(code):
    """(offset, code) of each opcode of an already compiled page."""
    i = 0
    while i < len(code):
        yield i, code
        i += opcode_size(code, i)


def route_targets(pages):
    """The events these already compiled pages send a route to.

    It walks the bytecode and not the RM2k commands, which is what makes it
    the truth and not a guess: what counts is what ended up emitted, after
    the filter decided which pages go in.
    """
    targets = set()
    for page in pages:
        code = page.get("codigo")
        for i, c in walk_code(code or b""):
            if c[i] == OP_ROUTE and c[i + 1]:
                targets.add(c[i + 1] - 1)
    return targets


# The switch with which the test page turns itself off: the last one of the
# ROM's bitmap —`SWITCH_BYTES` is 128, that is 0 to 1023— and the game goes up
# to 1003. A higher one would be written **outside** the bitmap, which is what
# happened the first time this was written with 2000.
#
# It exists since the automatic pages repeat while they stay active, which is
# what they do in RM2k: a made-up page without a condition would repeat
# forever and restart its own route every time. The real pages do not have
# that problem because they end up turning on the switch that deactivates
# them —it is RM2k's idiom— so the test one does the same, and exercises that
# idiom along the way.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
TEST_SWITCH = 1023

# The variable that chooses which of the test pages runs, when a cartridge
# carries several: see `--case` in snes_convert.py. Page k asks for it to be
# **at least** k, which is the only comparison RM2k 2000 offers in a page's
# condition, and since the highest-numbered one that is met wins, with the
# variable at k page k runs and no other. With a single variable it is enough
# for any number of cases; with one switch per case it is not: free ones are
# 1004 to 1020 and 1022.
#
# The number does not matter, because the ROM talks in slots, and no page of
# the game names 1000. It goes higher than all of the game's, so its slot is
# the last and shifts nobody else's.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
CASE_VARIABLE = 1000
COMPARE_AT_LEAST = 1   # the `>=` of RM2k's page conditions
# The switch that is never turned on: it is what a page with a condition the
# port cannot meet —an item, see `rm2k.IMPOSSIBLE_CONDITIONS`— carries as
# `switch_a`, so the ROM never picks it, and does pick the event's other
# pages. The game checks switches up to 1003 and 1023 is the test page's.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
SWITCH_IMPOSSIBLE = 1021
