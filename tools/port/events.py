#!/usr/bin/env python3
"""Compiles RM2k's event pages into something the ROM can run.

RM2k has about 130 event commands. The ROM understands a handful, and will
understand more over time. The rule that makes that safe is a single one:

    **a page is emitted only if all its commands can be run.**

If one we do not model shows up, the page is not emitted and the event does
nothing. Running half a script would be worse than not running it: it would
leave the game in a state that does not exist, and a golden captured there
would defend it as good from day one.

The command codes come from tools/rpgmaker/event_codes.py, which is
generated from liblcf. Never from memory: the first version of the door
filter wrote them down by eye and three were wrong.
"""

import collections
import math
import os

from port import picture as picture_mod
from port import rules
from port.constants import COLUMNS, LINES, EQUIPMENT_SLOTS
from rpgmaker import rm2k

# The opcodes' numbers, lengths and layout. **They are not declared here**:
# they come from `tools/protocol/events.toml`, which belongs to both sides —this
# one and the interpreter in tools/runtime/interprete*.s— and to neither. See
# tools/protocol/README.md.
from port.event_opcodes import *   # noqa: F401,F403
from port.event_opcodes import OPCODE_SIZE, opcode_size  # noqa: F401

# --- the RM2k commands we know how to run ------------------------------------
END = 10
CONTROL_SWITCHES = 10210
TELEPORT = 10810
# The hero's location into three variables, and the jump to whatever they say:
# the plant's breaking floors, and the way back from the tutorials. See
# OP_LOCATION.
MEMORIZE_LOCATION = 10820
RECALL_TO_LOCATION = 10830
# The song playing, noted down, and put back. See OP_MEMORIZED_BGM.
MEMORIZE_BGM = 11530
PLAY_MEMORIZED_BGM = 11540
TINT_SCREEN = 11030
WAIT = 11410
CHANGE_SAVE_ACCESS = 11930
# Opening the save menu: the slot screen, which freezes the game while it is
# shown and costs no tick. See `OP_SAVE`.
OPEN_SAVE_MENU = 11910
CHANGE_PARTY_MEMBERS = 10330
PLAY_BGM = 11510
# Fading out the song that is playing, over so many milliseconds.
# `Game_Interpreter::CommandFadeOutBGM` calls `BgmFade` and returns **true** on
# the same frame: it does not block the page, so it costs no frame and moves
# nothing of what is compared.
FADE_OUT_BGM = 11520
MOVE_EVENT = 11330
# Placing an event on a cell. It is `CommandChangeEventLocation`: `MoveTo`,
# which sets the cell and leaves the step at zero, and nothing else —only RM2k3
# touches the direction, and this game is RM2k—. The opening cutscene uses it
# six times to bring Core, Manta and the droid into the scene.
CHANGE_EVENT_LOCATION = 10860
TRADE_EVENT_LOCATIONS = 10870
# Changing one map tile for another, on every cell where it is:
# `CommandTileSubstitution`. It is by **tile number** and not by cell, and
# that is why in the ROM it is a small table that translates blocks while
# drawing, and not a write to the grid —which lives in ROM and cannot be
# written—. The converter resolves which block goes to which: see
# `Substitutions`.
TILE_SUBSTITUTION = 11750
# A cell's terrain into a variable: `CommandStoreTerrainID`. The terrain comes
# from the tile of the **lower** layer —"RPG_RT always uses the terrain of the
# first lower tile"— so the upper layer does not change it.
STORE_TERRAIN_ID = 10910
SHAKE_SCREEN = 11050
FLASH_SCREEN = 11040
# Moving the camera without the hero: `CommandPanScreen`. Of its four
# operations the game uses two —112 `pan` and 21 `reset`, and not one `lock`
# or `unlock`— so those are the ones that compile.
PAN_SCREEN = 11060
PAN_LOCK, PAN_UNLOCK, PAN_SHIFT, PAN_RETURN = 0, 1, 2, 3
# The camera's units inside RM2k: `SCREEN_TILE_SIZE`, that is 1/16 of a
# pixel, with a 16-pixel cell worth 256. Keeping them is not a whim: speed 2
# moves the camera **half a pixel per frame**, and in whole pixels that cannot
# be counted.
PAN_UNIT = 256
PAN_UP, PAN_RIGHT, PAN_DOWN, PAN_LEFT = 0, 1, 2, 3
# Which way the camera moves for each direction, in (dx, dy) per unit.
PAN_DIRECTION = {PAN_UP: (0, -1), PAN_RIGHT: (1, 0),
                 PAN_DOWN: (0, 1), PAN_LEFT: (-1, 0)}
PAN_SPEED_MIN, PAN_SPEED_MAX = 1, 6


def pan_bytes(operation, direction, distance, speed, wait):
    """The OP_PAN of a `PanScreen`, or None if it cannot be done.

    The direction and the distance are resolved here to a signed offset in
    1/16 of a pixel, and the speed to its step per frame: they are fixed
    computations and the ROM has no reason to repeat them. What is left to
    the console are the frames the page waits.
    """
    dx, dy = (0, 0) if operation == PAN_RETURN else PAN_DIRECTION[direction]
    dx *= distance * PAN_UNIT
    dy *= distance * PAN_UNIT
    if not (-0x8000 <= dx < 0x8000 and -0x8000 <= dy < 0x8000):
        return None
    return bytes([OP_PAN, operation,
                  dx & 0xFF, (dx >> 8) & 0xFF,
                  dy & 0xFF, (dy >> 8) & 0xFF,
                  pan_step(speed), 1 if wait else 0])


def pan_step(speed):
    """How far the camera moves per frame, in 1/16 of a pixel.

    It is `data()->pan_speed = 2 << speed` from `Game_Player::StartPan`, with
    the speed clamped between 1 and 6 as `CommandPanScreen` does. The game
    uses 2 to 6: from half a pixel per frame to eight.
    """
    return 2 << min(PAN_SPEED_MAX, max(PAN_SPEED_MIN, speed))


PLACE_CONSTANT = 0         # p[1]: 0 is the written cell, 1 reads it from variables
PLACE_BY_VARIABLE = 1      # and there is no third: `CommandChangeEventLocation`
                            # has two branches and nothing else

# A text box. RM2k emits a `ShowMessage` with the first line and a
# `ShowMessage_2` for each of the following lines of the same box: they are a
# single command —one window, one wait for the player— and whoever counts them
# separately measures nonsense. It already happened: counting them apart, the
# text boxes seemed to unlock three pages instead of fifty-five.
SHOW_MESSAGE = 10110
SHOW_MESSAGE_2 = 20110

# The escape codes this game's text uses: `\|` is a pause and `\^` closes the
# box without waiting for the player to press anything. Both are time and not
# text, and since 2026-09-13 both are done: they travel in the box's header
# —see `message_bytes`— and the ROM's interpreter and the one below read them
# the same way.
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


# A forced MoveEvent route. The parameters are (whom, frequency, a repeat
# bitmask, whether it is skippable) and from there on the route's commands,
# with the codes of liblcf's `rpg::MoveCommand::Code`.
#
# The four turns, the four moves and the wait are accepted. The moves came in
# last because in RM2k the character walks cell by cell over several frames,
# and that has to be compared *while* it walks: comparing only where it ends
# lets the whole animation cycle slip through. A blocked move is skipped,
# which is our decision and not RM2k's —RM2k would retry forever and a hung
# test says nothing—.
ROUTE_HERO = 10001
ROUTE_THIS_EVENT = 10005                    # "this event", the page's owner
# 10002 to 10004 are the vehicles —boat, ship, airship—, which do not exist here.
ROUTE_LOOK = {12: 0, 13: 1, 14: 2, 15: 3}   # face_up/right/down/left
ROUTE_MOVE = {n: n for n in range(8)}      # the four move_* and the
                                           # four diagonals: the command's
                                           # code **is** the direction. See
                                           # ROUTE_DIAGONALS
ROUTE_WAIT = 23

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


def min_frequency(frequency, commands, repeats=False):
    """The lowest frequency a route with commands 30 and 31 goes through.

    It is what decides whether the route can be compiled: with frequency 1
    the wait after a step is 256 frames and the `route_after_step` byte cannot
    hold it, so a route that goes down that far is rejected whole.

    `commands` are bare codes, without operands: the two callers pass what
    `decode_route` returned, which already separated them. It is not the
    same as a compiled route, where 34 drags a byte along that has to be
    skipped.

    With `repeats` the commands are walked nine times and not once. It is not
    just in case: the frequency is clamped at 8 and at 1, so a repeating
    route that goes down more than it goes up ends at 1 no matter what, and
    nine passes are enough for it to get there from any starting point.
    """
    current = lowest = frequency
    for _ in range(9 if repeats else 1):
        for command in commands:
            if command == ROUTE_FREQ_UP:
                current = min(ROUTE_FREQUENCY, current + 1)
            elif command == ROUTE_FREQ_DOWN:
                current = max(1, current - 1)
            lowest = min(lowest, current)
    return lowest


def wait_after_step(frequency):
    """`GetMaxStopCountForStep`: the frames standing still after a step."""
    return 0 if frequency >= 8 else 1 << (9 - frequency)


def wait_after_turn(frequency):
    """`GetMaxStopCountForTurn`: the frames standing still after a turn. The
    `wait` is `ROUTE_WAIT_FRAMES` plus this."""
    return 0 if frequency >= 8 else 1 << (8 - frequency)


# Facing the hero: `GetDirectionToCharacter`. The axis with more distance
# wins, and on a tie the vertical one; on the same cell it looks down. Only on
# events: no page uses the hero facing itself.
ROUTE_FACE_HERO = 21

# And moving toward the hero: `move_towards_hero`. It is not a new command but
# two that already exist stuck together —in `UpdateMoveRoute` it is
# `TurnTowardCharacter(hero)` and then `Move(GetDirection())`—, that is 21 and
# a `move_*` on the same frame, with the same step cost as any other.
#
# It is the command that unlocks the most of the ones that were missing, by
# far: measured over the whole game, **+31 pages**, against +1 for the other
# nine together —random, fleeing the hero, forward and the five in-place
# turns—. It is used 267 times in forced routes on four maps, 9, 11, 38 and
# 166; map 9 is the Lazer Teeth battle.
#
# Only on events, like 21: no route in the game asks for the hero moving
# toward itself —measured, zero— and it would mean nothing.
ROUTE_TOWARD_HERO = 9

# Turning without moving —`turn_90_degree_right` and its siblings— is still
# out, and not because of cost: RM2k turns relative to the direction the
# character already had, and for an event that has not turned yet that is its
# page's, which the route does not read.

# The jump: what lies between the two is added up as an offset and the
# character does it in one go, in an arc.
ROUTE_JUMP_START, ROUTE_JUMP_END = 24, 25

# Walking through walls, and stopping or resuming the walking animation.
ROUTE_THROUGH_ON, ROUTE_THROUGH_OFF = 36, 37
ROUTE_ANIM_STOP, ROUTE_ANIM_RESUME = 38, 39
# Locking and unlocking the facing —`lock_facing`—, and raising and lowering
# the speed by one, between 1 and 6. They came in on 2026-09-05 with the
# pages' own routes: map 2's droids use them.
ROUTE_LOCK_DIR, ROUTE_UNLOCK_DIR = 26, 27
ROUTE_SPEED_UP, ROUTE_SPEED_DOWN = 28, 29
# The four above, **on the hero**, are not compiled: see `traducir`. On the
# hero, locking and unlocking the facing are dropped; raising and lowering the
# speed **are done** since 2026-09-10 —the Tram Officer asks for it, and 170
# routes in the game— and they stay: RM2k restores the frequency when the
# route ends and not the speed, so the pad walks afterwards at the speed the
# route left.
ROUTE_HERO_OUTSIDE = {ROUTE_LOCK_DIR, ROUTE_UNLOCK_DIR}
# Raising and lowering the frequency in the middle of a route:
# `increase/decrease_movement_frequence`, which RM2k clamps at 8 and 1. **A
# single route in the whole game** uses them —the one that shakes Manta in the
# Emitter Room scene, which goes down twice from 8 to 6— and without them that
# page does not compile.
ROUTE_FREQ_UP, ROUTE_FREQ_DOWN = 30, 31
# Changing the graphic in the middle of a route. It is the **only command with
# an operand**: the bytecode carries after it the CharSet's index in
# `Graphics`. Only on events; on the hero it is not compiled, see `traducir`.
ROUTE_CHANGE_GRAPHIC = 34

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

# The four route diagonals, each with its two components: vertical first and
# then horizontal. They are `move_upright`, `move_downright`, `move_downleft`
# and `move_upleft`.
#
# **Only events** walk them. Of the game's 26 routes that use them none is
# the hero's, so the ROM does not have them on it: walking diagonally with the
# pad does not exist and giving the hero a diagonal step would require
# duplicating `try_up` and its three siblings for nothing. The converter
# rejects the page that tries it —see MOVE_EVENT in `traducir`—, which is what
# keeps the ROM from silently walking something else.
ROUTE_DIAGONALS = {4: (0, 1), 5: (2, 1), 6: (2, 3), 7: (0, 3)}


# The move commands we know how to walk, in a single place.
ROUTE_COMMANDS = (set(ROUTE_LOOK) | set(ROUTE_MOVE)
                  | {ROUTE_WAIT, ROUTE_JUMP_START, ROUTE_JUMP_END,
                     ROUTE_THROUGH_ON, ROUTE_THROUGH_OFF,
                     ROUTE_ANIM_STOP, ROUTE_ANIM_RESUME, ROUTE_FACE_HERO,
                     ROUTE_TOWARD_HERO,
                     ROUTE_LOCK_DIR, ROUTE_UNLOCK_DIR, ROUTE_SPEED_UP, ROUTE_SPEED_DOWN,
                     ROUTE_FREQ_UP, ROUTE_FREQ_DOWN, ROUTE_CHANGE_GRAPHIC})


# The commands that carry something after them, and what. The numbers are
# those of `rpg::MoveCommand::Code` in liblcf.
ROUTE_SWITCH_ON, ROUTE_SWITCH_OFF = 32, 33
# ROUTE_CHANGE_GRAPHIC, 34, is further up: `ROUTE_COMMANDS` needs it.
# Raising and lowering the transparency by an eighth. They are accepted and
# dropped, like the sound: the SNES does not fade a sprite in steps without
# color math, and the game's eight routes that use it —map 2's four screens,
# which fade while Manta hacks— are a decorative fade inside a 78-command
# scene that did not compile without this. They cost no frames: in
# `UpdateMoveRoute` they go through the branch that does not touch the stop
# counter.
ROUTE_TRANSPARENCY = (40, 41)
# The sound inside the route: it plays when the route reaches that step, since
# 2026-09-27. In a MoveEvent it goes with two bytes after it, the effect's
# index in `Songs.sounds` —the same one OP_SOUND carries—, so the effect goes
# into the map's audio package like that of a `PlaySound`. It costs no frame:
# `UpdateMoveRoute` does not touch its stop counter.
#
# It is still dropped in two places. **Inside a jump**, because RM2k does not
# touch it there: `BeginMoveRouteJump` walks up to the `end_jump` adding up the
# steps and runs nothing else. And **in a page's own route**, which is a bare
# list of codes with no room for the operand —see `own_route`—: a single
# one in the game asks for it, that of event 40 on map 2.
ROUTE_SOUND = 35


def decode_route(params):
    """The commands of a forced route, with whatever each one drags along.

    Returns a list of `(codigo, extras)`. It is needed because **the route is
    not a list of codes**: three commands carry operands inside the same
    stream of integers, and two of them a text —the CharSet's name, the
    sound's— with one integer per letter. Walking it flat worked while the
    first unknown command cut everything; as soon as one of those is
    accepted, the letters of the text would be read as commands.

    The integers come in RM2k's format: seven bits per integer and bit 7
    says another follows. It is `Game_Interpreter_Shared::DecodeMove` and
    `DecodeInt`.

    Running out of data in the middle of an operand is a broken route and
    does not compile; running out of data between one command and the next
    is the normal end. The difference matters: mixing them up left out 258
    pages that are perfectly fine.
    """
    commands = []
    i = 0
    n = len(params)

    def integer():
        nonlocal i
        value = 0
        while True:
            if i >= n:
                raise CannotCompile()
            x = params[i]
            i += 1
            value = (value << 7) | (x & 0x7F)
            if not x & 0x80:
                return value

    def text():
        nonlocal i
        length = integer()
        if i + length > n:
            raise CannotCompile()
        letters = "".join(chr(c & 0xFF) for c in params[i:i + length])
        i += length
        return letters

    while i < n:
        code = params[i]
        i += 1
        if code in (ROUTE_SWITCH_ON, ROUTE_SWITCH_OFF):
            extras = [integer()]
        elif code == ROUTE_CHANGE_GRAPHIC:
            extras = [text(), integer()]
        elif code == ROUTE_SOUND:
            extras = [text(), integer(), integer(), integer()]
        else:
            extras = []
        commands.append((code, extras))
    return commands

# "Wait for the routes to finish". In RM2k it waits until **none** is
# pending, neither the hero's nor any event's: it is `Game_Map::IsAnyMovePending`
# in `Game_Interpreter::Update`, and not a wait for the event that was just sent
# walking.
PROCEED_WITH_MOVEMENT = 11340

# A flash on a character: `Game_Character::Flash`. The parameters are whom, r,
# g and b from 0 to 31, the power, how many **tenths of a second** it lasts,
# and whether the page waits for it to finish.
#
# The tenths are not a detail: `CommandFlashSprite` does
# `event->Flash(r, g, b, p, tenths * DEFAULT_FPS / 10)` and, if it waits,
# `SetupWait(tenths)`, which is the same wait as the Wait command. So the
# time comes for free: it is an OP_DELAY after it.
FLASH_SPRITE = 11320

# How a forced route consumes time, and it is a modeling decision both sides
# have to share: turning is instantaneous —it goes to the next command on the
# same frame—, waiting consumes a frame, and moving starts a one-cell step,
# which the ROM walks at WALK_SPEED = 2 pixels per frame like any other step.
# A blocked move is skipped: RM2k's alternative is to retry forever, and a
# hung test tells nobody anything.

# ChangePartyMembers: the first parameter says whether it adds or removes, the
# second where the actor's id comes from, and the third the id. From liblcf
# and `Game_Interpreter::CommandChangePartyMember` in easyrpg-player.
PARTY_ADD, PARTY_REMOVE = 0, 1
PARTY_FIXED_ID = 0
PARTY_MAX = 4           # `Game_Party::AddActor` does not add if there are four

# Commands accepted while doing nothing, because doing nothing does not show.
# It is the same criterion as the doors', and it has to be applied with the
# same distrust: if the command changes something we do draw, it does not go
# here.
MESSAGE_OPTIONS = 10120

IGNORABLE = {
    MESSAGE_OPTIONS,      # where and how the message window is drawn,
                          # which without messages is drawn nowhere
}

# And this is something else, and the difference matters. The ones above do
# nothing because there is nothing to do: the save menu does not exist and
# neither do the message windows. The ones here **do** do something and we do
# not do it; they are accepted anyway because what they leave undone does not
# appear on the screen being compared, and in exchange they let pages run that
# would otherwise be left out whole.
#
# It is a debt, not an equivalence, and that is why it is in a separate list
# with its own name: whoever adds something here has to be able to say what
# breaks.
#
# PlayBGM changes the song that plays, and it is no longer one of these: it is
# done, see OP_BGM. Each map uploads its audio package to ARAM, with the songs
# its pages can turn on —`package_load`, in tools/runtime/paquete_de_audio.s—,
# and each sample's budget is that of its worst pack: see
# `workflow/decisiones/un-solo-banco-de-muestras.md`. It is accepted without
# being done only when compiling without a song registry.
# WeatherEffects turns the rain on or off. It is accepted without drawing it,
# and the debt is one of the big ones, so it is spelled out.
#
# **In mode 3 there is no layer left to put it on.** BG1 is the map's eight
# bits and BG2 the upper layer plus the message window; there is no third.
# Not with objects either: RM2k's rain is up to 100 streaks of 6x24 spread
# across the whole screen, and the console draws 34 sprite tiles per line —a
# 32x32 object takes four—, so a rain that covers the screen blows the budget
# on almost every line.
#
# And even if it fit: each drop has its own transparency —`alpha = min((5 +
# fuerza) * t, 255)` in `Weather::DrawParticles`— and the console has a single
# color operation for the whole screen, not one per object. The positions also
# come from a random number generator that would have to be reproduced.
#
# What is lost, measured on an EasyRPG capture of the opening: thin diagonal
# streaks 24 pixels tall, which between two consecutive frames move 3.9% of
# the screen. They show mostly in the dark areas.
#
# It is accepted because **it is the only thing blocking the opening
# cutscene**. Without this the ROM does not start the story; with it, it
# starts, without rain.
#
# **Since 2026-09-11 the rain is drawn**: see OP_WEATHER. Snow, fog and
# sandstorm are still not drawn, and they turn the rain off.
WEATHER_EFFECTS = 11070

# PlaySound plays an effect: a door, a hit, Talan's Insta-Shave. It sounds
# since 2026-09-11 (see OP_SOUND); until then it was accepted without playing
# it, and it was the cheapest debt of all the ones here: **it does not
# show**. The screen being compared is exactly the same with and without
# sound.
#
# What made it costly was ARAM. The effects go in each map's audio package,
# together with its songs —`package_load`, in
# tools/runtime/paquete_de_audio.s—, with the same per-pack budget as the
# music's samples: `workflow/decisiones/un-solo-banco-de-muestras.md`. One
# that does not fit in its pack does not sound.
#
# How much it unlocks, measured and not assumed: **+10 action-key pages and +6
# automatic ones**. It is much less than it seems: `PlaySound` is the command
# that cuts *first* in 349 pages, but almost all of them are also cut by
# something else: the command that cuts first is not the only one that cuts,
# and counting by it promises more than it unlocks.
#
# What it does unlock is concrete: the Insta-Shave on Talan's pad plays four
# effects before its message, so without this that branch does not run.
#
# **Since 2026-09-11 they sound**: see OP_SOUND.
PLAY_SOUND = 11550

# `ShowBattleAnimation` on the map —`CommandShowBattleAnimation`, 11210—: the
# battle animation is drawn over the character, with its own graphics and its
# own sound. The ROM carries no battle animations, so the command is accepted
# and nothing is done: what is lost is the drawing. In the opening it is the
# explosion with which CORE breaks map 2's security door; the page that asks
# for it continues with a `FlashScreen`, which does show, and with the
# message "CORE performs FURY PUNCH!". With the command cutting, that page did
# not run and the game was left without the corridor to the elevator.
SHOW_BATTLE_ANIMATION = 11210

# `ChangeItems` (10320) and `ChangeGold` (10310): give and take items and
# money. They are accepted without being done because **nobody reads the
# inventory**: there is no menu, there are no battles, and
# `ConditionalBranch` only knows how to ask about switches. The day one of
# those three things exists, this goes back to the list of what cuts.
#
# How much it unlocks, measured: `ChangeItems` +5 automatic pages and
# `ChangeGold` +1. What matters is not the number but which: the "1 year
# earlier" page —map 4, event 1, page 3— starts with seven `ChangeItems` in a
# row, and it is the one that continues the story after CORE and MANTA's
# memory.
CHANGE_GOLD = 10310
CHANGE_ITEMS = 10320

# `ShowPicture` (11110), `MovePicture` (11120) and `ErasePicture` (11130): an
# image on top of everything, moved and erased.
#
# **Since 2026-09-12 one is done**: the "One year previously" picture, and any
# other that fits the same mold. See `Pictures`, OP_PICTURE and
# workflow/tasks/done/show-picture-phase-1.md. The ones that do not fit —27 of
# the 34 the game has— are still accepted without being done, and what follows
# applies to those.
#
# In mode 3 both background layers are taken by the map, so an image on top
# requires a video decision, not one more opcode. But there is a shortcut this
# game allows and it is worth noting: **the cutscenes tint to black before
# showing the picture**, that is the map is invisible while it lasts and the
# image could borrow a whole layer instead of being composited on top. That
# does not work for the game's custom systems, which use them over the map,
# but it does for the pictures.
#
# How much it unlocks, measured: +8 automatic pages, the three together. The
# one that matters is the "1 year earlier" one, where the image is the "One
# year previous" picture: accepting it, the player sees black where the
# picture goes and the scene continues up to Talan's Pad.
SHOW_PICTURE = 11110
MOVE_PICTURE = 11120
ERASE_PICTURE = 11130

# The two command codes of the variables, which are used further down and in
# the list here: see "RM2k's variables".
CONTROL_VARS = 10220
CALL_EVENT = 12330
# And the shop: `OpenShop`. Forty-three in the game, none with the
# "bought"/"did not buy" branches. From the night of 2026-09-10 to the 11th it
# was accepted without opening anything, so that the Lashe City Interiors
# vendors —EV0021 and EV0023— would answer; since the 11th it opens the real
# shop: see OP_SHOP.
OPEN_SHOP = 10720

# And the inn: `ShowInn`, with its three branches. The game has 18 pages with
# one and none uses the branches —measured on 2026-09-20—, so the command is
# compiled alone: see `_compile_inn`.
SHOW_INN = 10730
INN_STAY, INN_NO_STAY, INN_END = 20730, 20731, 20732

# `ChangeSystemBGM` (10660): changes the song the system uses for fighting,
# for winning, for the inn. The game uses it **130 times on 25 maps** and
# always in pairs —0 and 1, that is `battle_music` and `battle_end_music`—:
# each zone has its battle music.
#
# It is accepted without being done, and the debt is concrete: **a battle on
# those maps plays the LDB's song instead of the zone's**. It is not "it does
# not sound": what sounds is the one `BATTLE_AUDIO` brings from the database,
# which is the one the map's audio package already carries, so nothing goes
# silent and nothing asks for a sample that is not there. And it does not
# change a pixel, so the suite measures the same with and without this.
#
# How much it unlocks, measured over the game's 5603 triggerable pages:
# **+24**. Doing it for real is not this command but an audio feature: the
# system song would become state that travels in the save, and the songs
# those 130 occurrences name would have to fit in their maps' audio packages.
# Today the worst package is 54945 of 63831 B of ARAM; adding a battle song to
# twenty-five maps requires room in those packages: see
# workflow/decisiones/un-solo-banco-de-muestras.md.
CHANGE_SYSTEM_BGM = 10660

# `ChangeHeroTitle` (10620): an actor's "title", which in RM2k is the text the
# status screen shows under the name. Eight occurrences in the whole game and
# **all on Talan**: "Fugitive", "Limping", "Defender".
#
# It is accepted without being done because **this port does not show the
# title anywhere**: the converter emits an actor's name and starting
# equipment, and nothing else —there is no status screen—. So doing it for
# real is not this command but that screen, and while it does not exist the
# data would have nowhere to show. Storing it anyway would be state that
# travels in the save without anyone reading it.
#
# What it unlocks: **+5 pages**, and among them map 19's `RunDirectorScene`,
# which is automatic. With it not compiling, the director's scene did not
# start: taro reached the office on 2026-09-13, the speech ran whole, the
# teleport back worked, and then nothing else happened.
CHANGE_HERO_TITLE = 10620

# `ChangeEncounterSteps` (11740): every how many steps there is a random
# encounter. Nineteen occurrences on nine maps, and thirteen of them set it to
# **zero**, which in RM2k is turning them off. Until 2026-09-27 it was left out
# because "there are no random encounters"; there are since 2026-09-13 —see
# `tools/runtime/encuentros.s`— and Dalia's trip to Tasgarde asked for it, the
# automatic `DaliaGoingToTasgarde` on map 66, which turns them off before
# forcing the hero's route. It compiles to OP_ENCOUNTER_STEPS: see
# `encounter_steps`.
CHANGE_ENCOUNTER_STEPS = 11740

ACCEPTED_UNDONE = {
    # CallEvent **is no longer here**: since 2026-09-12 it is compiled
    # inline, see `_compile_call`. What is left of that is that a call
    # whose target does not compile is skipped just like before, and that is
    # decided in there and not in this list: the command itself is no longer
    # a whole debt.
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
    CHANGE_SYSTEM_BGM,
    CHANGE_HERO_TITLE,
}


class Songs:
    """The songs the game's `PlayBGM`s ask for, numbered in the order they
    appear.

    It is the sibling of `Messages`: the bytecode carries an index and not a
    name, and the converter is the one that resolves the index. The ROM
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
        # package: see `package_load` in tools/runtime/paquete_de_audio.s.
        # And which ROM maps each one jumps to —`destinos`, indices into the
        # map table—, which is where it comes from which song may be playing
        # when a package is loaded: see `inherited_songs` in snes_convert.py.
        self.current_map = None
        self.per_map = {}
        # And which `PlayBGM`s of each map are **exit ones**: see `output`.
        self.exits = {}
        # And with which song each `Teleport` of each map jumps: see `jump`.
        self.jumps = {}
        # How many times an effect was asked for, so the page can see whether
        # a command made one sound: see `_follow_exit`.
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

    def dest(self, game_map):
        self._note("destinos", game_map)

    def jump(self, dest, song):
        """Notes a jump from the map being compiled to `dest`: with `song`
        if it goes right after a `PlayBGM` of that song, with no branches or
        effects in between —the one it surely carries—, or with None if it
        carries whatever is playing. The page notes it when it compiles, and
        `_recalled_destination` that of a `RecallToLocation`, always with None.
        See `inherited_songs` in snes_convert.py."""
        if self.current_map is None:
            return
        self.jumps.setdefault(self.current_map, {}).setdefault(dest, set()).add(
            song)

    def note_exit(self, song, is_exit):
        """Notes a `PlayBGM` of the song on the map being compiled: `is_exit` if
        after it, with no branches or effects in between, the page jumps to
        another map. A song is an exit song on a map if **all** its
        `PlayBGM`s there are: see `exit_songs`."""
        if self.current_map is None:
            return
        noted = self.exits.setdefault(self.current_map, {})
        noted[song] = noted.get(song, True) and is_exit

    def exit_songs(self, game_map):
        """The songs a map turns on only to leave: each of its `PlayBGM`s is
        followed by a jump to another map, with no effects or branches in
        between. In the game it is `lufsorr` on map 3: it plays after the
        sequence of effects, when none is left to play, and the map is left
        right away. So it has no reason to fit in ARAM with those effects: it
        goes in the **separate** package, it is uploaded if there is room,
        and if not its `PlayBGM` uploads it —see `exit_extra` in
        tools/runtime/paquete_de_audio.s—. It is from 2026-09-26."""
        return [t for t, is_exit in self.exits.get(game_map, {}).items() if is_exit]

    def sound(self, name, volume, tempo, balance, in_package=True):
        """The effect's index. Without `in_package` it is not noted in the
        map's package: it only sounds if something else puts it there. See
        `se_route_left_out` in snes_music.py. It does not count in
        `requested` either: one that is not in the package does not sound, so
        it does not keep a song from being an exit song."""
        key = (name, volume, tempo, balance)
        if key not in self.sounds:
            self.sounds.append(key)
        if in_package:
            self.requested += 1
            self._note("sonidos", name)
        return self.sounds.index(key)

class Graphics:
    """The graphics the routes change to with command 34, numbered in the
    order they appear.

    Sibling of `Songs` and `Messages`, with a difference that matters: it is
    **per map**. What the ROM needs from a graphic —its twelve poses and its
    palette— lives in the sprite bank, and the bank belongs to each map; two
    maps that change to the same CharSet number it each on their own.

    The bytecode carries the index and not the name, as with songs and maps:
    the converter is the one that resolves it, and the ROM does not look at
    the LCF again.

    `associations` half breaks the "per map", and it is worth understanding
    why: they are the graphics `ChangeSpriteAssociation` can give an actor,
    and that **survives the map change** —every time the game uses it, the
    command is right next to a teleport and what shows is the graphic on the
    other side—. So its index cannot mean one thing here and another there.
    It is solved by reserving the first slots of the table of **every** ROM
    map for them, in the same order: see `sprite_associations`, which is the
    prior pass that gathers them, and `Pictures.choose`, which is the same
    pattern.
    """

    def __init__(self, associations=()):
        self.pairs = list(associations)

    def index(self, charset, index):
        pair = (charset, index)
        if pair not in self.pairs:
            self.pairs.append(pair)
        return self.pairs.index(pair)


# `ChangeSpriteAssociation`: changes the CharSet of an **actor**, not an
# event. In RM2k it is `actor->SetSprite(...)` plus a `ResetGraphic()` on
# `Game_Player`, so it shows right away if that actor is leading and stays
# stored for when it leads.
#
# The parameters are [actor, index within the CharSet, transparent] and the
# name goes in `string`. A fourth parameter is the bitfield that says which
# of the three come from a variable —`ValueOrVariableBitfield(com, 3, ...)`—:
# this game does not use it in any of its 212 occurrences and it is rejected
# here, as always.
CHANGE_SPRITE_ASSOCIATION = 10630


def sprite_associations(game_maps, extra=()):
    """The (CharSet, index) pairs some `ChangeSpriteAssociation` names.

    It is `Graphics`' prior pass: it reserves for each one the same slot in
    the graphics table of every ROM map, because the graphic the command
    gives an actor **crosses the teleport** and its index has to mean the
    same on both sides of the jump.

    **All** the pages are looked at and not only the ones that compile, on
    purpose: if it depended on what compiles, the list would depend on
    whether the ROM carries a message window —same as `possible_leaders`—
    and the converter's two passes would number differently. Reserving one
    slot too many costs the twelve poses of a CharSet in the sprite bank and
    nothing else.

    In this game they are two pairs —`Future3:0` and `BLVehicles:2`— and only
    if the ROM carries any of maps 49, 50, 52 or 54, which are the car chase.

    `extra` are the commands of the test pages, which go after.
    """
    pairs = []
    commands = [cmd for game_map in game_maps for event in game_map.events
                for page in event.pages for cmd in page.commands]
    for cmd in commands + list(extra):
        if cmd.code != CHANGE_SPRITE_ASSOCIATION:
            continue
        p = list(cmd.parameters)
        if len(p) != 3 or p[2]:
            continue        # the ones `_compile` is going to reject
        pair = (cmd.string, p[1])
        if pair not in pairs:
            pairs.append(pair)
    return pairs


# --- the opcodes we emit ----------------------------------------------------
# One per command, with the operands already resolved: the ROM does not look
# at the LCF again nor knows its numbers.
#
# **The numbers and layouts are in `tools/protocol/events.toml`**, not here:
# this is what there is to know about each one that a declaration cannot say.
#
# OP_SWITCH: id (word), value (byte)
#
# OP_TELEPORT: map (word), x (word), y (word). The map used to go in a
#     byte and that put a ceiling of 256 maps **on the
#     format**: the game has 328. Today it does not
#     matter —the demos carry 29— but it was a written
#     ceiling, and removing it while it is still cheap
#     is cheaper than removing it the day a demo goes
#     over.
#
# OP_DELAY: frames (word): the cutscene waits six
#     seconds, that is 360, and they do not fit in a byte
#
# OP_TINT: r, g, b, sat (a byte each)
#
# OP_PARTY: operation (byte), actor (byte)
#
# OP_ROUTE: target (byte), frequency (byte), how many commands (byte), and
#     the commands. The target is 0 for the hero, and
#     otherwise the event's index in the map's table plus
#     one.
#
#     **The index is not the RM2k id.** 39 maps of this
#     game have gaps in the event numbering, so a route
#     aimed at id 8 would move whichever is eighth in the
#     list, which can be any other. The converter
#     translates it, being the only one that sees the map.
#
# OP_MESSAGE: offset (word) within the `messages` block: opens
#     that window and blocks the page until the player
#     presses A
#
# OP_WAIT_ROUTES: no operands: the page does not continue until no forced
#     route is left running
#
# OP_FLASH: target (byte), r, g, b, power (a byte each, 0 to
#     31) and how many frames it lasts (byte)
#
# OP_PLACE: target (byte, as in OP_ROUTE: the event's index
#     plus one), x (word), y (word). Places the event on
#     the cell and cuts the step in progress; it does not
#     touch its route nor where it faces, which is what
#     `MoveTo` does.
#
# OP_SWAP: two targets (a byte each, as in OP_PLACE): the two
#     events trade cells, each one with `MoveTo`, which is
#     `CommandTradeEventLocations`.
#
# OP_SHAKE: power (byte), speed (byte), frames (word):
#     `ShakeOnce`. With zero frames it is `ShakeEnd`: the
#     screen goes back to its place. The math is
#     `shake_tick` in tools/runtime/camara.s.
#
# OP_FLASH_SCREEN: r, g, b, power (a byte each, 0..31) and frames
#     (byte): `FlashOnce`, the whole-screen flash. The
#     math is `flash_tick` in
#     tools/runtime/destello_de_pantalla.s.
#
# OP_IF: kind (byte), operand (word), polarity (byte),
#     destination (word):
#     `ConditionalBranch` with a switch condition. If it
#     is not met, the cursor jumps to the destination,
#     which is the `else` or the `end` of that same
#     branch. The polarity is RM2k's reversed and on
#     purpose: there `parameters[2] == 0` means "has to be
#     on", so here 0 is "on" and 1 is "off", same as the
#     data.
#
#     The destination is **absolute** within the page,
#     not relative: the ROM's cursor is a 16-bit index
#     into the same array, so assigning it is the whole
#     jump.
#
# OP_GOTO: destination (word): the unconditional jump emitted
#     where the `else` was, so the branch above skips the
#     one below.
#
# OP_SAVE: no operands: the save to the cartridge's SRAM.
#     It is `OpenSaveMenu`, but without a menu: there is
#     a single slot and the event overwrites it. What is
#     saved is said by `save_table` in
#     tools/runtime/banco1.s, which is the only place
#     where it is written. It costs no frame: in RM2k the
#     menu blocks, and here there is nothing to look at.
#
# OP_GOLD: sign (byte: 0 adds, 1 subtracts) and a 24-bit amount.
#     It is `ChangeGold`, and it goes in three bytes
#     because RM2k's cap is 999999 and the game uses the
#     whole value: there is a command that gives exactly
#     that.
#
#     The ROM clamps to [0, GOLD_MAX] like
#     `Game_Party::GainGold`. There is still nowhere to
#     show it —the menu does not exist— but there is who
#     asks for it: the gold branch of `ConditionalBranch`.
#
# OP_CHOICE: how many options (byte), what cancel does (byte), and
#     then one entry per option: the text box (word) and
#     the destination (word). It is `ShowChoice`.
#
#     **One text box per option, not a single one.** The
#     boxes carry the same lines and differ in where the
#     cursor is, so moving the cursor is recomposing the
#     window with another offset and not drawing anything
#     new. It costs a few dozen bytes per choice and saves
#     a sprite tile, a palette and all the code to draw
#     it: on the console there is nowhere to put a cursor
#     that is not a sprite, and this map's sprites are
#     already spread among the characters.
#
#     The destination is absolute within the page, like
#     OP_IF's, and each option's body ends in an OP_GOTO
#     to the end of the choice.
#
# OP_PAN: operation (byte: PAN_RUN or PAN_RETURN), how far
#     the destination moves in x and in y (a signed word
#     each, in 1/16 of a pixel), the step per frame
#     (byte) and whether the page waits (byte).
#
#     The direction and the distance come resolved to a
#     signed offset, and the speed to its step: they are
#     fixed computations and the converter does them
#     once. What **cannot** be resolved here are the
#     frames the page waits: they come from what the pan
#     has left when the command runs, and with one still
#     in progress that is not what this command asked for.
#     See `GetPanWait` and `CommandPanScreen`'s comment on
#     the maximum.
#
# OP_FADE_BGM: step (word): how much the song's volume goes down
#     per frame, in 1/65536 of whatever was playing.
#
#     The step goes and not the milliseconds RM2k brings
#     because the 65816 does not divide without hardware
#     and the math is always the same:
#     `ceil(65536 / frames)`. It is the same kind of
#     number as a teleport's map index —resolved by the
#     converter so the ROM does not look at it again—, and
#     `fade_step` does it.
#
# OP_BGM: the song's index in `Songs` (byte). The ROM plays the
#     ones it carried —the first `SONG_TOTAL`— and with
#     any other it does nothing. See `Songs`.
#
# OP_TIMER: operation (byte), seconds (word), visible (byte).
#     The five bytes are fixed even though each operation
#     uses two: that way the interpreter skips it without
#     looking at which one it is, which is what the
#     converter's `walk_code` does.

# The operand is an offset and not a text, and that is what makes it fit. An
# already composed message page is ~240 tiles at 4bpp, that is 7.5 KB, and
# emitting one for every text box in the game does not come close to fitting
# in a 256 KB cartridge: the 2895 boxes would be 21 MB. What is emitted is the
# text —one byte per letter— and the 65816 composes it on the fly, with the
# font in ROM, which is FF6's way out. The same 2895 boxes are 180 KB of text,
# and a single map quite a lot less.
#
# Sixteen bits are enough because the block has to fit in a 32 KB bank:
# `lda [msg_ptr], y` reads it with a pointer that increments one byte at a
# time and does **not** carry into the bank byte, so `bloque()` emits it with
# `.bloque`, which keeps it whole in one bank. If some day it does not fit,
# what has to grow is the pointer, not the operand.

# TimerOperation. The parameters are (operation, where the seconds come from,
# seconds, visible, in battle): liblcf, TimerOperation::Operation.
TIMER_OPERATION = 10230
TIMER_SET, TIMER_START, TIMER_STOP = 0, 1, 2
TIMER_FIXED_SECONDS = 0        # the other value takes them from a variable
# `Game_Party::SetTimer` stores `segundos * 60 + 59`, not `segundos * 60`. The
# extra 59 are what makes the first second show whole: without them the timer
# would show the requested value for a single frame.
TIMER_EXTRA_FRAMES = 59

# ControlSwitches: the first parameter says where the ids come from and the
# last what to do with them (liblcf, ControlSwitches::Operation).
SWITCH_SINGLE, SWITCH_RANGE, SWITCH_INDIRECT = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

# An absurd range is not unrolled: better not to run the page than to emit
# thousands of opcodes for one line.
MAX_RANGE = 64

# RM2k measures waits in tenths of a second.
FRAMES_PER_TENTH = 6
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
# tools/runtime/ram_lejana.s—.
#
# The ROM does two: **the mosaic**, with the PPU's MOSAIC register tied to the
# brightness ramp —like the battle's, `fundido_de_pelea.s`, and for the same
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
CHANGE_SCREEN_TRANSITIONS = 10690
TRANSITION_ERASE, TRANSITION_SHOW = 0, 1
RM2K_TRANSITION_MOSAIC = 17
RM2K_CUT_TRANSITIONS = (19, 20)       # the cut and "none"
RM2K_TRANSITIONS_NOT_DONE = {19: "the cut", 20: "none"}
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
#   the direction, `pagina["gira"]`— and it has no route: with a route, the
#   route decides where it looks. The ones that walk on their own always have
#   a route, so they do not turn; in RM2k they pause while their page runs
#   and they do, and that is not modeled.
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
ANIM_FIXED = (2, 3, 4, 5)

# Only the events on the hero's layer are triggered with the action key: it is
# the `GetLayer() == Layers_same` of `CheckEventTriggerThere`.
LAYER_SAME = 1


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
        # The pages of each event, by id, for `CallEvent`: calling a map
        # event compiles its page in place. The pages go and not their
        # commands because the number the call brings is the page's, and in
        # RM2k it starts at one.
        self.pages = {ev.id: ev.pages for ev in game_map.events}
        # Visible is having a graphic on the active page, which is the same
        # rule `collect_npcs` uses to decide what goes in the ROM's table.
        self.visible = {ev.id for ev in game_map.events
                        if ev.active_page() is not None
                        and ev.active_page().character_name}
        # Which character each one is drawn with, to know which share a
        # palette. On the console the flash is done on the character's
        # palette, so two events with the same graphic would flash together:
        # see `_compile`.
        self.graphic = {}
        for ev in game_map.events:
            page = ev.active_page()
            if page is not None and page.character_name:
                self.graphic[ev.id] = (page.character_name,
                                       page.character_index)
        # Which variables some page condition of this map looks at: it is
        # `Game_Map::RefreshEvent`'s `map_cache`, which is filled with each
        # page's `pg.condition.variable_id`. `write_needs_refresh` reads
        # it. Measured over the 328 maps: at most **one** per map, and 314
        # have none.
        self.watched_vars = {pg.condition.ids["variable"]
                             for ev in game_map.events for pg in ev.pages
                             if "variable" in pg.condition.active}
        # Which map it belongs to, to know when a page leaves it: see
        # `after_jump`.
        self.map_id = getattr(game_map, "map_id", None)
        # How a `TileSubstitution` translates to ROM block pairs. The
        # converter sets it on the map, because it depends on how the blocks
        # ended up —which is the console's business— and not on RM2k.
        # Without it the command does not compile, which is what happens in
        # any ROM built without going through `snes_convert`.
        self.substitutions = getattr(game_map, "substitutions", None)
        self.owner = owner

    def shares_graphic(self, who):
        """Whether this event draws with the same character as another one on
        the map."""
        which = self.graphic.get(who)
        return which is not None and sum(1 for g in self.graphic.values()
                                         if g == which) > 1

    def for_event(self, event_id):
        other = MapEvents.__new__(MapEvents)
        other.indices, other.visible = self.indices, self.visible
        other.graphic, other.owner = self.graphic, event_id
        other.pages = self.pages
        other.watched_vars = self.watched_vars
        other.map_id = self.map_id
        other.substitutions = self.substitutions
        return other

    def after_jump(self):
        """The same, for what the page does **after jumping to another map**:
        it keeps running there, and which variables the pages there look at
        cannot be known from here, so every write asks for a refresh. See
        `write_needs_refresh`.

        The rest does not change, and not because it is right: an event named
        by id after the jump is translated against this map and not against
        the destination. No page of the game that compiles today does it.
        """
        other = self.for_event(self.owner)
        other.watched_vars = None
        # And the blocks there are not these: a substitution after the jump
        # would talk about the new map's tiles and the translation is the old
        # one's.
        other.substitutions = None
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


class Messages:
    """The ROM's text block, and the offset of each box.

    It belongs to the whole ROM and not to the map: `OP_MESSAGE` carries an
    offset within this block, so all maps share the numbering and the
    converter emits it only once. What is repeated is stored only once —the
    game repeats whole boxes, 418 of 2895— and it comes for free because the
    content already is the key.
    """

    def __init__(self, step=1):
        # How many bytes at a time the offset in the bytecode counts. The
        # game's block goes by four —see MESSAGES_STEP— and each box starts
        # at a multiple of four; the others, like the troops', by one.
        # Inside, everything is in bytes: the step is applied going in and
        # going out.
        self.step = step
        self.data = bytearray()
        self.where = {}         # the lines already stored -> their offset
        self.texts = {}        # and back: the offset -> the lines

    def add(self, lines):
        r"""The offset of this box, storing it if it is the first time.

        The escape tail is removed **here** —see `escape_tail`— and not
        in the compiler, so that everyone who builds a box goes through the
        same place: the game's `ShowMessage`s and those of the test pages
        —which is how this is tested: `autocierre` in the suite— and a
        `ShowChoice`'s options.

        Trimming to what fits in a line is done after the tail and before
        deduplicating: two texts that differ only in what gets cut are the
        same box on screen, and giving them two different offsets would emit
        the same bytes twice. The other way around —trimming first— a
        39-character line would eat its own `\|\^` and the box would be left
        waiting for an A that RM2k does not ask for.

        **The deduplication key carries the tail**, and it is not a detail:
        two boxes with the same text and different tails are two different
        boxes —one waits for the player and the other does not— and sharing
        an offset would make them last the same.
        """
        lines, pauses, auto_close = escape_tail(lines)
        lines = tuple(t[:COLUMNS]
                      for t in list(lines)[:LINES])
        key = (lines, pauses, auto_close)
        if key not in self.where:
            while len(self.data) % self.step:
                self.data.append(0)
            where = len(self.data)
            self.data += message_bytes(lines, pauses, auto_close)
            if where // self.step > 0xFFFF:
                raise SystemExit(
                    "this ROM's messages are %d bytes and the OP_MESSAGE "
                    "operand is 16 bits, counting by %d bytes"
                    % (len(self.data), self.step))
            self.where[key] = where
            self.texts[where] = lines
        return self.where[key] // self.step

    def lines(self, where):
        """The lines `add` stored at that offset."""
        return self.texts[where * self.step]

    def tail(self, where):
        """How many pauses that box carries and whether it closes on its own.

        It comes from **the same bytes the ROM reads** and not from a
        parallel dictionary: `msg_start` decodes that header byte with the
        same masks. A format read in two different ways is exactly the
        failure mode this repo has already paid for twice.
        """
        header = self.data[where * self.step]
        return (header >> 4, bool(header & HEADER_AUTO_CLOSE))

    def mark(self):
        return len(self.data)

    def rewind(self, mark):
        """Undoes what was added since `mark`.

        It is needed because a page is compiled command by command and can
        be cut at the last one: without this, the text of all the pages that
        **do not** compile would stay in the cartridge anyway. It is not a
        micro-optimization, it is the whole game's 161 KB against the few
        that are needed.
        """
        del self.data[mark:]
        self.where = {k: v for k, v in self.where.items() if v < mark}
        self.texts = {k: v for k, v in self.texts.items() if k < mark}

    def bytes(self):
        # Never empty: the assembler needs the label resolved even if the ROM
        # is never going to read it.
        return bytes(self.data) or b"\x00"


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


def message_bytes(lines, pauses=0, auto_close=False):
    """A text box as the ROM reads it: the header, and each line with its
    length.

    The characters go as an index into the font's table, that is ASCII minus
    32. All of this game's text fits there: it was measured, and it does not
    have a single accented letter.
    """
    assert 0 <= pauses <= PAUSES_MAX
    out = bytearray([min(len(lines), LINES)
                     | (HEADER_AUTO_CLOSE if auto_close else 0)
                     | (pauses << 4)])
    for text in list(lines)[:LINES]:
        text = text[:COLUMNS]
        out.append(len(text))
        for ch in text:
            if not 32 <= ord(ch) < 127:
                raise SystemExit("the message has a character that is not in "
                                 "the font: %r" % ch)
            out.append(ord(ch) - 32)
    return bytes(out)


def group_boxes(commands):
    """The commands one at a time, except the text boxes.

    Returns (command, extra lines), where the extra ones are the
    `ShowMessage_2`s that follow a `ShowMessage` and are part of the same
    box. A loose `ShowMessage_2` is returned alone and does not compile,
    which is right: it would be a line with no window to put it in.

    It is part of the filter and not of the emitter: counting the commands
    separately is what made the measurement of how much the text boxes
    unlocked come out wrong.
    """
    commands = list(commands)
    i = 0
    while i < len(commands):
        j = i + 1
        if commands[i].code == SHOW_MESSAGE:
            while j < len(commands) and commands[j].code == SHOW_MESSAGE_2:
                j += 1
        yield commands[i], [c.string for c in commands[i + 1:j]]
        i = j


def can_trigger(page):
    """Whether the ROM knows how to trigger this page, apart from whether its
    commands compile.

    The two layer rules come from `Game_Player`, and they are opposite on
    purpose:

    * **Action key**: the cell in front is looked at, and there only the
      events on the hero's layer count —`CheckEventTriggerThere` asks for
      `GetLayer() == Layers_same`—. An action event on the **own** cell does
      exist in RM2k, but it asks for the opposite layer
      —`CheckEventTriggerHere` asks for `!= Layers_same`— and we do not do
      those.
    * **Touch**: it triggers on stepping on the cell, and there it is the
      other way around: the layer has to be different from the hero's,
      because an event on the same layer blocks its way and it would never
      get to step on it. Of the game's 983 touch pages, 978 are on the lower
      layer.

    **Turning toward the hero does not stop the page.** Until 2026-09-08 it
    did, and that cost **1572 action pages across 1224 events on 220 maps**:
    half the game's NPCs could not be used. Since 2026-09-11 the event also
    turns for real: see TURN.
    """
    if page.trigger == TRIGGER_ACTION:
        # Both cells count, and each one asks for the opposite layer. The one
        # in front is `CheckEventTriggerThere`, which asks for `Layers_same`;
        # the own one is `CheckEventTriggerHere`, which asks for
        # `!= Layers_same` —it has to be so: an event on the hero's layer
        # closes its way and it would never get to stand on it—.
        #
        # The own one was not done until 2026-09-07 and taro found it while
        # playing: the door out of Talan's pad is `TalDoorTop`, action and
        # **layer 2**, and it opens by standing on it. Without this it never
        # triggered and there was no way out of the pad.
        return True
    if page.trigger == TRIGGER_TOUCH_HERO:
        return page.layer != LAYER_SAME
    return True


# `ConditionalBranch` and its two closers. They come from `event_codes.py`,
# which is generated from liblcf: the doors' ones were written from memory
# once and three were wrong.
COND_BRANCH = 12010
COND_ELSE = 22010
COND_END = 22011

# The condition kinds we know how to do. The number is RM2k's as is
# —`parameters[0]`— and not a numbering of ours: copying it avoids the
# translation that already went wrong once with the doors' command codes.
#
# Measured over the whole game, by how many pages each one unlocks:
#
#     variable               332 pages     asks for variables, which there are none
#     switch                 145           done
#     hero in the party       48           done, but only subtype 0
#     hero's facing           31           unlocks **zero**: those pages are
#                                          held back by something else anyway
#     item                    24           asks for an inventory, which there is none
#     gold                    10           done
#     timer                    1           unlocks zero
#
# Measured again on 2026-09-13 over the game's 5603 triggerable pages, with
# the inventory and the variables already done, counting **the ones that go
# on to compile whole** and not the rejected commands:
#
#     actor, "has the item equipped"    36 pages use it,  +18 unlocks
#     actor, "knows the skill"          10 pages use it,  +10 **on top** of
#                                       the previous one: they are the same
#                                       pages and need both, so alone it
#                                       gives +0
#     facing of a character             31 pages use it,   +0, measured
#                                       again and with the two above in
#     timer                              1 page,           +0
#
# So of the 433 pages that did not compile, the two actor questions are worth
# **+28** and the other two kinds are worth nothing.
COND_SWITCH = 0
COND_GOLD = 3
# The inventory **already exists** —`OP_ITEM` and `FAR_ITEMS`, since
# 2026-09-10— so the line above is stale: the item branch is
# `GetItemCount(id) > 0`, exactly the same question as the page condition by
# item, which the ROM already answers by reading `FAR_ITEMS`. Equipment does
# not count, as in `conditions_ok`: `GetEquippedItemCount` asks for
# equipment, which there is none.
COND_ITEM = 4
COND_ACTOR = 5

# And of the "hero", three of its seven questions. The numbers are those of
# RM2k's `com.parameters[2]` as is, and they come from the `switch` of
# `Game_Interpreter::CommandConditionalBranch` case 5 in easyrpg-player: 0 is
# in the party, 1 is named so, 2 level >=, 3 HP >=, 4 knows the skill, 5 has
# that item equipped, 6 has that state.
#
# The ones left out —the name, the level, the HP and the state— ask for stats
# this port does not carry or that never change; measured over the whole
# game, the four together cut **zero** pages.
COND_ACTOR_IN_PARTY = 0
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
# and travel in the saved game. `index_variables` builds the index. Until
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
# HP, SP and states. Until 2026-09-12 outside battle they never went down
# —measured over the 328 maps: the 11 `ChangeHP`s add, the 16
# `ChangeCondition`s remove a state and the 54 `FullHeal`s fill up— so the
# three commands compiled to nothing and it was exact. **It stopped being so
# the next day**, with the battle: HP and SP became state, in `FAR_HP` and
# `FAR_SP`, and a `FullHeal` that does not heal leaves the party down. That
# blocked the demo until 2026-09-19, because the battle on map 9 is lost by
# script and its defeat handler is precisely a `FullHeal`.
#
# Today `FullHeal` and the `ChangeHP` that adds are both OP_HEAL, and the
# amount tells them apart; the one that subtracts still does not compile.
# `ChangeCondition` that removes a state still compiles to nothing, and that
# is **not** debt: outside battle states do not exist —the battle sets them
# up and throws them away— so there is nothing to remove. The one that sets a
# state still does not compile.
#
# OP_HEAL: actor (byte), amount (word). Actor 0 is the whole party and amount
#     0 is `FullHeal`, that is HP and SP to the maximum.
# The shop, since 2026-09-11: `OpenShop` compiles to OP_SHOP with the type
# —0 buys and sells, 1 only buys, 2 only sells—, the message set and the list
# of what it sells, by item number. It is variable-length, like OP_CHOICE.
# Like saving, the screen opens inside the interpreter and costs no tick: the
# map does not run while it is shown. The "bought" and "did not buy" branches
# do not compile; none of the game's 43 shops uses them.
#
# OP_SHOP: type, set, how many (bytes), and two bytes per item
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


# The sound effects, since 2026-09-11: `PlaySound` compiles to OP_SOUND with
# the index of its entry in `Songs.sounds`, and the ROM's table says with
# which sample, what pitch, what volume on each side and how many frames. The
# samples go in ARAM next to the music's bank, with a budget of their own: see
# `build_sound_effects` in snes_music.py. They play on voice 7, which is stolen from
# the music while they last. They cost no tick, as in RM2k.
#
# OP_SOUND: index (word)

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
# tools/runtime/animacion_de_batalla.s.
#
# The flash is not exactly RM2k's: there the power is
# `min((7 - (d + 1) / 2) * potencia / 6, 31)` for ten frames, in steps; here
# it is a `FlashScreen` or a `FlashSprite` that starts at the first and goes
# down linearly over `ANIM_FLASH_FRAMES`. It is the same light and it
# lasts the same.
#
# OP_ANIMATION: n, and n entries of ANIM_ENTRY_BYTES bytes
ANIM_ENTRY_BYTES = 8
ANIM_SOUND, ANIM_SCREEN_FLASH, ANIM_FLASH = 0, 1, 2
# Ten, which is how long RM2k's lasts, and **even** on purpose: the screen
# flash works in two phases according to the parity of what it has left —see
# `flash_tick`—, and a `FlashScreen` of the game always lasts tenths times
# six. With eleven the first phase was the even one, a path no page takes and
# that therefore tests nothing: `animacion` showed it.
ANIM_FLASH_FRAMES = 10
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


def drawing_target(anim, target):
    """What this animation is drawn over: the target, or the screen.

    With "screen" scope —`Animation::Scope_screen`, which is 1— RM2k draws it
    at the center and asks the target nothing; with the other, over the
    target, which is the same byte the routes and the flashes already use.
    """
    if anim.get("alcance", 0) == 1:
        return ANIM_TARGET_SCREEN
    return target

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
PICTURE_FRAMES_MAX = 255


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

# `HaltAllMovement`: all of the map's forced routes are abandoned at once. It
# is `Game_Map::RemoveAllPendingMoves`, that is a `CancelMoveRoute` on the
# hero and on each event, and what cancelling means is written only once: it
# is **the same as what happens when the route ends on its own** —whoever had
# a page route of its own goes back to it, whoever did not stands still— and
# that is why the ROM calls `resume_page`.
#
# What it **does not** touch, same as `CancelMoveRoute`: the step or jump in
# progress are finished, and where each one faces stays where the route left
# it.
#
# In the whole game there is **a single one** —map 11, the event that
# rearranges the Lazer Teeth hideout when you are discovered— and that is why
# it is worth it: without it that page does not compile and the HQ cannot be
# played again after you get caught.
#
# OP_STOP_ROUTES: no operands

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

HALT_ALL_MOVEMENT = 11350

# `ChangePBG`, the parallax background. **It is accepted and dropped**, which
# is the same the port already does with the whole panorama: mode 3 has two
# background layers and both are taken —the map and the upper layer with the
# window—, so there is nowhere to draw it. See
# workflow/tasks/wishlist/panorama-del-mapa-2.md.
#
# It is dropped **when compiling**: it emits nothing and the ROM does not
# find out, like move commands 26 and 27.
#
# It appears **only once in the whole game**: seven commands in a single
# page, the Hover-Tram ride on map 13, where the afternoon landscape runs
# behind and changes speed when starting and braking. It is the only page
# that blocks that map, so the debt declared here is exactly "the tram is
# ridden with no background landscape".
CHANGE_PBG = 11720

# `ChangeSpriteAssociation`: actor (byte) and which graphic of the map's table
# (byte). It is the same as move command 34 but on an **actor**, and the
# two differences come from there:
#
# * **It survives the map change**, because in RM2k it belongs to the actor
#   and not to `Game_Player`. That is why its index comes from `Graphics`'
#   reserved slots —see `sprite_associations`— and not from the map's free
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
# **The number is chosen by looking at the ones already there, not the last
# one you remember.** On 2026-09-13 three sub-agent branches chose "the next
# free one" at the same time without seeing each other: $23 came out twice
# and $24 twice, git merged them without a single conflict —each on its own
# line— and what broke was the walk over the bytecode.
# `test_no_opcode_shares_a_number_with_another` guards it.
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

KEY_INPUT_PROC = 11610

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
# **The number is chosen by looking at the ones already there**, not the last
# one you remember: see `OP_ACTOR_SPRITE`'s warning.
#
# OP_PLACE_VAR: target (byte, as in OP_PLACE), slot of x
#     (byte), slot of y (byte)
#
# OP_LOCATION: mode (byte), and the slots of the map, x and y (a byte each).
#     `MemorizeLocation` and `RecallToLocation` are the same opcode because
#     they are the same location read or written: bit 0 of the mode says
#     which —`PLACE_JUMP`—, and when recalling bits 7, 6 and 5 are the
#     VAR_REFRESH of each of the three writes. **The map in the variable is
#     the RM2k id**, which is what any other page reads and writes; the ROM
#     translates it with `map_rm2k`. They unlock 55 pages of Lashe City's
#     milestone 3 —the plant's floors, 28 on 60 and 26 on 62, and the droid
#     tutorial— and they are what holds back the most pages in the whole
#     game.
#
# OP_MEMORIZED_BGM: 0 remember the song that plays, 1 put it back.
PLACE_JUMP = 0x01
PLACE_REFRESHES = (0x80, 0x40, 0x20)    # the map, x and y


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
VICTORY_HANDLER = 20710
ESCAPE_HANDLER = 20711
DEFEAT_HANDLER = 20712
END_BATTLE = 20713

# The three handlers, in the order their destinations go in the opcode.
BATTLE_HANDLERS = (VICTORY_HANDLER, ESCAPE_HANDLER, DEFEAT_HANDLER)

# The parameters of `EnemyEncounter`, from `Game_Interpreter_Map::
# CommandEnemyEncounter`: [troop by variable, troop, where the backdrop comes
# from, what happens on escape, what happens on defeat, whether it strikes
# first]. This port only does the case the game's 51 battles use —troop by
# constant— and stops on the others, as always: better to emit nothing than
# to emit something the ROM does differently.
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
# The escape parameter: 0 cannot, 1 cuts the battle. Only 1 is asked
# about.
BATTLE_ESCAPE_CUTS = 1
BATTLE_DEFEAT_GAME_OVER = 0


# --- the battle's audio -----------------------------------------------------
#
# All from the LDB, nothing made up: the battle song, the victory one and the
# five effects `Game_System::GetSystemSE` hands out. Who sounds at what moment
# comes from easyrpg-player and **not from memory**, which is this repo's
# rule:
#
#   battle_music      `Scene_Battle`, on construction
#   battle_end_music  `Scene_Battle_Rpg2k`, on winning (BGM_Victory)
#   dodge_se          `AlgorithmBase::GetFailureSe`: the hit that misses
#   enemy_attack_se   `Normal::GetStartSe` with the enemy as source
#   enemy_damaged_se  the hit's `eMessage` sub-state, enemy target
#   actor_damaged_se  same, party target
#   enemy_death_se    `ProcessBattleActionDeath`
#   escape_se         `Scene_Battle_Rpg2k`, when the party escapes
#
# In ABL `battle_se` —the battle-start one— is "(OFF)", so nothing is
# registered for it: a name that does not resolve to any file still goes into
# the tables but would take up an entry that is forever silent.
#
# **This is registered inside the compilation** —`battle_audio`, when
# compiling the `EnemyEncounter`— and not in the converter: the `Songs`
# indices are carried by the bytecode of each `PlayBGM` and each `PlaySound`,
# so everyone who compiles pages has to number the same way, and a song noted
# from outside would shift all the ones after it.
BATTLE_AUDIO = {}

# The order is the contract with the ROM: the converter emits `BA_SE_<n>` with
# the index each one got from `Songs`, in this order.
BATTLE_AUDIO_SE = ("dodge_se", "enemy_attack_se", "enemy_damaged_se",
                   "actor_damaged_se", "enemy_death_se", "escape_se",
                   # The one from 2026-09-13, when the battle started
                   # letting items be used: easyrpg's `Item::GetStartSe`,
                   # which is the LDB's `item_se`.
                   "item_se")
BATTLE_AUDIO_BGM = ("battle_music", "battle_end_music")

# A name RM2k uses to say "nothing": neither the song nor the effect exist.
AUDIO_OFF = ("", "(OFF)")


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


def index_battle_audio(game_dir):
    """The battle's song and effects, from the LDB. The converter and the
    tests that compile pages call it, same as `index_animations`."""
    db = database(game_dir)
    BATTLE_AUDIO.clear()
    BATTLE_AUDIO["battle_music"] = db.battle_music
    BATTLE_AUDIO["battle_end_music"] = db.battle_end_music
    for name in BATTLE_AUDIO_SE:
        BATTLE_AUDIO[name] = db.system_se[name]


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


def battle_audio(songs):
    """Notes in `songs` what the battle is going to play, and returns their
    indices: two songs and `BATTLE_AUDIO_SE` effects, $FF or $FFFF the off
    one.

    It is called every time a page compiles an `EnemyEncounter`. What is
    noted falls into the `BATTLE_PACKAGE` package and not into that of the
    map that has the battle, so `temas.mapa` has to be saved and restored
    around it.
    """
    if songs is None or not BATTLE_AUDIO:
        return None
    indices = {}
    previous = songs.current_map
    songs.current_map = BATTLE_PACKAGE
    for name in BATTLE_AUDIO_BGM:
        song = BATTLE_AUDIO[name]
        indices[name] = (0xFF if song in AUDIO_OFF
                         else songs.index(song))
    for name in BATTLE_AUDIO_SE:
        effect = BATTLE_AUDIO[name]
        indices[name] = (0xFFFF if effect[0] in AUDIO_OFF
                         else songs.sound(*effect))
    songs.current_map = previous
    return indices


class Pictures:
    """The only picture that goes into the cartridge, and which commands
    move it.

    It is the sibling of `Songs` and `Graphics`: the converter builds one,
    and the decision is here and not there.

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

    def show(self, number, name, cx, cy):
        """The slot's picture if this `ShowPicture` is its own, or None."""
        if self.name is None:
            return None
        return (self.info if (self.name, self.number, self.where)
                == (name, number, (cx, cy)) else None)

    def owns(self, number, cx, cy):
        """Whether the slot's picture is the one this command names and it
        does not move from where it is. `MovePicture` and `ErasePicture` ask
        it, since they do not carry the name: in RM2k the picture number is
        all that ties them to their `ShowPicture`."""
        return (self.name is not None and self.number == number
                and (cx is None or self.where == (cx, cy)))


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
CHANGE_HP = 10460
CHANGE_CONDITION = 10480
FULL_HEAL = 10490
CHANGE_MENU_ACCESS = 11960
CHANGE_ESCAPE_ACCESS = 11840
ACCESS_SAVE, ACCESS_MENU, ACCESS_ESCAPE = 0, 1, 2
# Each one's bit in `FAR_ACCESS`, and the bits mean "forbidden" so that the
# reset's zero is "everything allowed", which is how RM2k starts. $80 is the
# menu request —`menu_calling`— and it is not a permission.
ACCESS_BIT = (0x01, 0x02, 0x04)
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
OTHER_GOLD, OTHER_TIMER = 0, 1
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


def variables_named(game_dir, map_ids=None, extra=()):
    """Which variables the pages of these maps name —without a list, the
    whole game's—, each with its slot.

    All the commands and conditions of all the pages are looked at, whether
    they compile or not: it is a cheap superset —two bytes per variable— and
    that way a page that compiles later does not change the others' slots.
    `extra` are those of the test pages, which do not come from any map: the
    converter sweeps them with `command_variables`.

    **`KeyInputProc` also names a variable, and until 2026-09-13 it was not
    in this list.** It is the only command in the game that writes to a
    variable without being a `ControlVars`, so a variable only it touched was
    left without a slot and the page did not compile for a reason that had
    nothing to do with the command. **Two** get through: 5, from the stones
    minigame engine on map 11, and 151, from two other pages; all three are
    written by this command and read by nobody else.
    It was not circular —it did not depend on the page compiling—: this sweep
    looks at all the commands whether they compile or not, and it did not
    look at this one.
    """
    ids = set(extra)
    ids |= sweep_maps(
        game_dir, game_map_ids(game_dir) if map_ids is None else map_ids,
        _map_variables)
    if map_ids is None:
        # And those of the troops' pages, which belong to the whole game and
        # not to a map. They add up to **forty**, measured on 2026-09-21: the
        # characters' systems each carry their counters —Talan's 81 and 106
        # count how many times he absorbed each technique—, and no map names
        # them.
        db = database(game_dir)
        for troop in db.troops.values():
            for page in troop.pages:
                if "variable" in page.active:
                    ids.add(page.condition["variable_id"])
        for commands in troop_page_commands(db):
            ids |= command_variables(commands)
    return {variable: slot for slot, variable in enumerate(sorted(ids))}


def _map_variables(game_map):
    """The `variables_named` sweep over one map."""
    ids = set()
    for event in game_map.events:
        for page in event.pages:
            if "variable" in page.condition.active:
                ids.add(page.condition.ids["variable"])
            ids |= command_variables(page.commands)
    return ids


def sweep_maps(game_dir, map_ids, sweep):
    """The union of `sweep(game_map)` —a set— over those maps.

    The sweeps of `variables_named` and `skill_pairs` each load the
    game's 328 maps, and loading them is almost all they cost: they run in
    parallel, in batches, and each batch returns the union of its own. The
    result is a set, so the order does not matter.
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


def troop_page_commands(db):
    """The commands of each troop page of the LDB, with the battle branches
    translated to the map's —see `BATTLE_BRANCH`—, for the sweeps that look
    for variables and skill pairs. **It does not filter**: the sweep is a
    superset, like the maps', whether the page compiles or not."""
    from rpgmaker import lcf
    for troop in db.troops.values():
        for page in troop.pages:
            yield [lcf.EventCommand(BATTLE_BRANCH.get(c.code, c.code),
                                    c.indent, c.string, c.parameters)
                   for c in page.commands]


def command_variables(commands):
    """The variables these commands name: the `variables_named` sweep, which is
    also that of the test pages.

    `ChangeEventLocation` with the cell in two variables came in on
    2026-09-18, when the test page started using it. In the game they are
    129 and add none: measured, all their variables are already named by
    another command.
    """
    ids = set()
    for cmd in commands:
        p = cmd.parameters
        if cmd.code == CONTROL_VARS and len(p) >= 7:
            if p[0] == 0:
                ids.add(p[1])
            elif p[0] == 1:
                ids.update(range(p[1], p[2] + 1))
            if p[4] == VAR_VARIABLE:
                ids.add(p[5])
        elif cmd.code == COND_BRANCH and len(p) >= 5 \
                and p[0] == COND_VARIABLE:
            ids.add(p[1])
            if p[2] == 1:
                ids.add(p[3])
        elif cmd.code == KEY_INPUT_PROC and p:
            ids.add(p[0])
        elif cmd.code == TIMER_OPERATION and len(p) >= 3 \
                and p[0] == TIMER_SET \
                and p[1] != TIMER_FIXED_SECONDS:
            ids.add(p[2])
        elif cmd.code == CHANGE_EVENT_LOCATION and len(p) >= 4 \
                and p[1] == PLACE_BY_VARIABLE:
            ids.update((p[2], p[3]))
        elif cmd.code == STORE_TERRAIN_ID and len(p) >= 4:
            ids.add(p[3])
            if p[0] == 1:
                ids.update((p[1], p[2]))
        elif cmd.code in (MEMORIZE_LOCATION, RECALL_TO_LOCATION) \
                and len(p) >= 3:
            ids.update(p[:3])
    return ids


COMMON_EVENTS = {}            # RM2k common event -> its commands

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
# tools/runtime/equipo_desde_eventos.s—. It is what the droid tutorial says:
# "these abilities become available once you equip a particular component and
# exit the menu".
#
# What is left out: a page's `ChangeEquipment` on the actor the event looks
# at does not run it again. In the game there is none on 18.
PARTY_COMMON_EVENTS = {}
# The `rpg::CommonEvent` `trigger` that runs in parallel.
COMMON_PARALLEL = 4
# The end of a block of commands: the empty line that closes each branch.
BLOCK_END = 10


def is_party_common_event(trigger, commands):
    """Whether a common event is one of `PARTY_COMMON_EVENTS`'s: parallel,
    with a switch, and with nothing but `ChangeSkills` and branches on an
    actor's equipment —with their `else`, their closer and the block
    ends—."""
    kind, has_switch, _switch = trigger
    allowed = (CHANGE_SKILLS, COND_BRANCH, COND_ELSE, COND_END,
               BLOCK_END)
    return (kind == COMMON_PARALLEL and has_switch and commands
            and all(c.code in allowed for c in commands)
            and all(c.parameters[:1] == [COND_ACTOR]
                    and c.parameters[2:3] == [COND_ACTOR_EQUIPMENT]
                    for c in commands if c.code == COND_BRANCH))


def index_common_events(game_dir):
    """Leaves in `COMMON_EVENTS` the commands of each common event, and in
    `PARTY_COMMON_EVENTS` the ones that are of that kind.

    The converter and the tests that compile pages call it before compiling
    anything, same as `index_variables`: `CallEvent` compiles them in
    place, so without the database loaded none compiles.
    """
    db = database(game_dir)
    COMMON_EVENTS.clear()
    COMMON_EVENTS.update(db.common_events)
    PARTY_COMMON_EVENTS.clear()
    for number, trigger in sorted(db.common_event_triggers.items()):
        if is_party_common_event(trigger, db.common_events.get(number)):
            PARTY_COMMON_EVENTS[trigger[2]] = number
    return COMMON_EVENTS


def compile_party_common_event(number):
    """The body of a `PARTY_COMMON_EVENTS` common event as a loose page, with
    its `OP_DONE`: what the ROM runs when closing the menu. It needs no map
    nor texts —it does not use them—, and if it does not compile it is a
    converter bug: `is_party_common_event` only lets through what always
    compiles.
    """
    code = compile_page(_Commands(COMMON_EVENTS[number]), lambda _m: None)
    if code is None:
        raise SystemExit("common event %d is an equipment one and does not "
                         "compile" % number)
    return code


# What the two actor questions of `ConditionalBranch` need to know from the
# LDB: what each one has equipped at the start and which skills it knows.
# They go in a module index, like `COMMON_EVENTS` and `VARIABLE_SLOT`: it is built
# only once before compiling anything, so all pages read the same reading of
# the LDB.
ACTOR_EQUIPMENT = {}       # RM2k actor -> its five slots, in the order of
                        # `constants.EQUIPMENT_SLOTS`
ACTOR_SKILLS = {}         # RM2k actor -> the skills it knows
_INDEXED_ACTORS = []


def index_actors(game_dir):
    """Leaves in `ACTOR_EQUIPMENT` and `ACTOR_SKILLS` what the LDB says about
    each actor.

    Without this the interpreter would answer that nobody has anything
    equipped and that nobody knows anything, **silently and on one side
    only**, which is the failure mode `AGENTS.md` names. That is why there is
    a list that says whether it was called and `OP_IF_ACTOR` looks at it.
    """
    db = database(game_dir)
    ACTOR_EQUIPMENT.clear()
    ACTOR_SKILLS.clear()
    ACTOR_EQUIPMENT.update({a: tuple(act.initial_equipment)
                            for a, act in db.actors.items()})
    ACTOR_SKILLS.update({a: rules.learned_skills(db, a)
                         for a in db.actors})
    _INDEXED_ACTORS[:] = [True]
    return dict(ACTOR_EQUIPMENT)


# The terms the inn's greeting is built with. They are the game's and not
# ours —ABL charges in "Cr"— so they come from the LDB and not from a literal,
# for the same reason as the title screen's. They go in a module index like
# `ACTOR_EQUIPMENT`: the converter builds it once before compiling anything.
#
# The two sets of terms are `ShowInn`'s `inn_type`: 0 set A and 1 set B.
INN_TERMS = {}
_INN_TERMS = ("greeting_1", "greeting_2", "greeting_3", "accept",
              "cancel")


def index_terms(game_dir):
    """Leaves in `INN_TERMS` the inn's terms and the gold's.

    Without this `ShowInn` does not compile —and says so—, instead of
    building the greeting with made-up words: the price and the currency are
    the only thing the player is going to read to decide.
    """
    from rpgmaker import lcf
    db = database(game_dir)
    terms = db.sections["terms"]
    INN_TERMS.clear()
    INN_TERMS["gold"] = lcf.field(terms, "gold")
    for kind, letter in ((0, "a"), (1, "b")):
        INN_TERMS[kind] = tuple(
            lcf.field(terms, "inn_%s_%s" % (letter, name))
            for name in _INN_TERMS)
    return dict(INN_TERMS)


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
# The ceiling: the bits live in `FAR_SKILL`, which has 256 bytes in the far RAM
# map. Today the game uses far fewer; if some day they are not enough, the
# converter stops instead of overwriting the neighbor.
SKILL_SLOTS_MAX = 256 * 8
CHANGE_SKILLS = 10440
CHANGE_EQUIPMENT = 10450
GAME_OVER = 12420
RETURN_TO_TITLE = 12510
# `Comment` and its extra lines: the author's notes in the editor, which RM2k
# skips when running the page. EasyRPG's `CommandComment` only does something
# with the DynRPG and Destiny patches —comments starting with `@` or `$`—, and
# none of the game's 23 starts like that.
COMMENT = 12410
COMMENT_2 = 22410


def command_skill_pairs(commands):
    """The (actor, skill) pairs these commands name: the
    `skill_pairs` sweep, which is also that of the test pages.

    Only the forms that compile —fixed actor and constant skill—: a pair that
    comes in a variable cannot be indexed, and those commands do not compile.
    None in the game does it."""
    pairs = set()
    for cmd in commands:
        p = cmd.parameters
        if cmd.code == CHANGE_SKILLS and len(p) >= 5 \
                and p[0] == 1 and p[3] == 0:
            pairs.add((p[1], p[4]))
        elif cmd.code == COND_BRANCH and len(p) >= 4 and p[0] == COND_ACTOR \
                and p[2] == COND_ACTOR_SKILL:
            pairs.add((p[1], p[3]))
    return pairs


def _map_skill_pairs(game_map):
    """The `skill_pairs` sweep over one map."""
    pairs = set()
    for event in game_map.events:
        for page in event.pages:
            pairs |= command_skill_pairs(page.commands)
    return pairs


def skill_pairs(game_dir, extra=()):
    """Each (actor, skill) pair the game can look at, with its slot.

    See `SKILL_SLOT`. The ones naming an actor or a skill the LDB does
    not have are discarded: RM2k ignores them with a warning, and here they
    do not compile."""
    db = database(game_dir)
    pairs = set(extra)
    for number, actor in db.actors.items():
        pairs |= {(number, s) for _level, s in actor.skills if s}
    pairs |= sweep_maps(game_dir, game_map_ids(game_dir),
                        _map_skill_pairs)
    for commands in db.common_events.values():
        pairs |= command_skill_pairs(commands)
    # And the troops' pages, which since 2026-09-21 run in the battle. Today
    # they add no pair —the ones the systems teach are already named by some
    # map—, but without this the first one that is not would not compile.
    for commands in troop_page_commands(db):
        pairs |= command_skill_pairs(commands)
    pairs = {(a, s) for a, s in pairs if a in db.actors and s in db.skills}
    return {pair: slot for slot, pair in enumerate(sorted(pairs))}


def index_skills(game_dir, extra=()):
    """Leaves in `SKILL_SLOT` the whole game's index. The converter
    calls it before compiling anything, like `index_variables`."""
    SKILL_SLOT.clear()
    SKILL_SLOT.update(skill_pairs(game_dir, extra))
    if len(SKILL_SLOT) > SKILL_SLOTS_MAX:
        raise SystemExit("there are %d skill pairs and `FAR_SKILL` holds %d"
                         % (len(SKILL_SLOT), SKILL_SLOTS_MAX))
    return dict(SKILL_SLOT)


def skill_slot(actor, skill):
    if (actor, skill) not in SKILL_SLOT:
        raise CannotCompile("the pair actor %d, skill %d has no slot"
                            % (actor, skill))
    return SKILL_SLOT[(actor, skill)]


def index_variables(game_dir, extra=()):
    """Leaves in `VARIABLE_SLOT` the whole game's index. The converter and
    the tests that compile pages call it before compiling anything; it takes
    a third of a second to read the 328 maps."""
    VARIABLE_SLOT.clear()
    VARIABLE_SLOT.update(variables_named(game_dir, None, extra))
    return dict(VARIABLE_SLOT)


def variable_slot(number):
    if number not in VARIABLE_SLOT:
        raise CannotCompile("variable %d has no slot in this ROM" % number)
    slot = VARIABLE_SLOT[number]
    if slot > VAR_SLOT_MAX:
        # The slot is a byte, and far RAM has room for 256.
        raise CannotCompile("slot %d does not fit in a byte: see VAR_SLOT_MAX"
                            % slot)
    return slot


def write_needs_refresh(number, map_events):
    """The `VAR_REFRESH` bit for a write to variable `number`.

    It is `SetNeedRefreshForVarChange` resolved at compile time: only the
    variables some page condition of the map looks at ask for a refresh.
    **Without the map it is always asked for**, which is what the port did
    before this and the only honest thing when it is not known who looks at
    what.
    """
    if map_events is None or map_events.watched_vars is None:
        return VAR_REFRESH     # without the map, or after leaving it
    return VAR_REFRESH if number in map_events.watched_vars else 0


def next_random(x):
    """The xorshift step, in sixteen bits."""
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x

# RM2k's gold cap: `Game_Party::GainGold` clamps to `MaxGoldValue()`, which
# by default is this.
GOLD_MAX = 999999

# How many switches the ROM's bitmap fits: `SWITCH_BYTES` is 128, that is 0 to
# 1023. A branch on a higher one would write out of bounds, so it does not
# compile.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
SWITCH_MAX = 1024


# `ShowChoice` and its two companions, from `event_codes.py`. The `10` that
# closes each option's body is `END`, and there is no need to look at it: the
# jump to the end of the choice is emitted in the next option, which is where
# it is known that the previous one ended.
SHOW_CHOICE = 10140
SHOW_CHOICE_OPTION = 20140
SHOW_CHOICE_END = 20141

# RM2k shows four options at most, and `GetChoices(4)` discards the ones with
# a higher index. This ROM's window has four lines, so the cap is the same on
# both sides.
CHOICE_MAX = 4

# The cursor, and what is put in front of the options that do not have it so
# the text does not shift from line to line.
CHOICE_CURSOR = ">"
CHOICE_INDENT = " "


def choice_options(commands, i):
    """The options of the `ShowChoice` at `comandos[i]`.

    It is `Game_Interpreter::GetChoices`: it walks forward from the next
    command, gathers the `ShowChoiceOption`s on its same indentation and
    stops at the `ShowChoiceEnd`. Returns (index, text).
    """
    if i + 1 >= len(commands):
        return []
    level = commands[i + 1].indent
    output = []
    for cmd in commands[i + 1:]:
        if cmd.indent != level:
            continue
        if cmd.code == SHOW_CHOICE_END:
            break
        if cmd.code == SHOW_CHOICE_OPTION and cmd.parameters \
                and cmd.parameters[0] < CHOICE_MAX:
            output.append((cmd.parameters[0], cmd.string or ""))
    return output


def choice_boxes(options, messages):
    """One `messages` offset per option, with the cursor on its line.

    The boxes are the same except for the cursor. `Messages` deduplicates by
    content, so the common lines are not stored twice: what is paid is one
    small box per option.
    """
    texts = [t for _, t in options]
    return [messages.add(
                [(CHOICE_CURSOR if k == n else CHOICE_INDENT) + " " + t
                 for k, t in enumerate(texts)])
            for n in range(len(texts))]


def branch_bytes(cmd):
    """A `ConditionalBranch` of the kinds we know, with the destination
    blank.

    Five of the twelve kinds: switch, variable, gold, item and actor; and of
    the actor one, three of its seven questions —is in the party, knows the
    skill and has the item equipped—. The missing ones ask for state this
    port does not carry —an actor's level, HP and state, a character's
    facing, the timer, the vehicle— and a branch on any of those would always
    give the same answer, so it could not even be tested. The two that would
    be worth the most are measured above, where the constants are: **neither
    unlocks a single page**.

    The polarity is copied as is from RM2k and means different things
    depending on the kind: on a switch, 0 is "has to be on"; on the item, 0
    is "has to have it"; on the gold, 0 is ">=" and 1 is "<=". It is
    `com.parameters[2]` from there, untranslated.
    """
    p = cmd.parameters
    if len(p) < 3:
        raise CannotCompile("a branch with no operands")
    if p[0] == COND_SWITCH:
        number = p[1]
        if not 0 <= number < SWITCH_MAX:
            raise CannotCompile("switch %d out of the bitmap" % number)
    elif p[0] == COND_GOLD:
        number = p[1]
        if not 0 <= number <= 0xFFFF:
            # The operand travels in a word. In this game the biggest is
            # 2000, so nothing is lost; if some day a bigger one appears,
            # this says so instead of comparing it wrong.
            raise CannotCompile("gold comparison against %d, which does not fit "
                                "in a word" % number)
    elif p[0] == COND_ITEM:
        number = p[1]
        if not 0 <= number < ITEMS_N:
            raise CannotCompile("item %d is not in the LDB" % number)
    elif p[0] == COND_ACTOR:
        number = p[1]
        if not 0 <= number <= 0xFFFF:
            raise CannotCompile("actor %d out of range" % number)
        if p[2] == COND_ACTOR_IN_PARTY:
            # "Is in the party" has no polarity: the branch below is the
            # `else`.
            return bytes([OP_IF, COND_ACTOR, number & 0xFF, number >> 8,
                          0, 0, 0])
        if p[2] in (COND_ACTOR_SKILL, COND_ACTOR_EQUIPMENT):
            if len(p) < 4:
                raise CannotCompile("an actor branch without the item or the "
                                    "skill")
            if not 0 <= number <= 0xFF:
                # The actor travels in a byte: see OP_IF_ACTOR. The LDB has 60.
                raise CannotCompile("actor %d, which does not fit in a byte" % number)
            if _INDEXED_ACTORS and number not in ACTOR_EQUIPMENT:
                # The ROM's tables go from 0 to the LDB's last actor, so an
                # extra number would be read out of the table. RM2k warns and
                # goes through the `else`; here it does not compile, which is
                # what this port does with everything it cannot answer. No
                # page of the game does it: it is checked only when the index
                # is loaded, so as not to change the answer for whoever
                # compiles without calling `index_actors`.
                raise CannotCompile("actor %d is not in the LDB" % number)
            operand = p[3]
            if p[2] == COND_ACTOR_SKILL:
                # The skill travels as its pair's slot: it is the bit the ROM
                # looks at, and that way it does not have to search. See
                # `SKILL_SLOT`.
                operand = skill_slot(number, operand)
            if not 0 <= operand <= 0xFFFF:
                raise CannotCompile("an actor branch against %d, which does not "
                                    "fit in a word" % operand)
            return bytes([OP_IF_ACTOR, p[2], number,
                          operand & 0xFF, operand >> 8, 0, 0])
        raise CannotCompile("of the hero we know whether it is in the party, "
                            "whether it knows a skill and what it has equipped, "
                            "and not %d" % p[2])
    elif p[0] == COND_VARIABLE:
        if len(p) < 5:
            raise CannotCompile("a variable branch with no operands")
        slot = variable_slot(p[1])
        if p[2] == 0:
            operand_kind, value = VAR_CONSTANT, p[3]
            if not -0x8000 <= value <= 0x7FFF:
                raise CannotCompile("comparison against %d, which does not fit "
                                    "in a signed word" % value)
        elif p[2] == 1:
            operand_kind, value = VAR_VARIABLE, variable_slot(p[3])
        else:
            raise CannotCompile("variable branch against something we do not "
                                "know")
        if not 0 <= p[4] <= CMP_NOT_EQUAL:
            raise CannotCompile("comparison %d does not exist" % p[4])
        return bytes([OP_IF_VAR, slot, operand_kind, p[4], value & 0xFF,
                      (value >> 8) & 0xFF, 0, 0])
    else:
        raise CannotCompile("branch on a condition we do not know how to do")
    return bytes([OP_IF, p[0], number & 0xFF, number >> 8,
                  1 if p[2] else 0, 0, 0])


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

    def request(self, number, backdrop=None):
        if number not in self.ids:
            self.ids.append(number)
        if backdrop and number not in self.backdrops:
            self.backdrops[number] = backdrop     # a name, or PLACE_BACKDROP
        return number


# --- the troops' event pages -------------------------------------------------
#
# `Game_Interpreter_Battle`: each troop brings its pages, and the battle runs
# them **with the same interpreter as the maps**, `run_code`, so they are
# compiled with the same `compile_page`. The only thing that changes is
# what is accepted: see `TROOP_COMMANDS`.
#
# When each one runs is decided by the ROM and it is copied from
# `Scene_Battle_Rpg2k`; see `ba_page_test` in tools/runtime/batalla_tropa.s.

# The battle's three branch commands, with their map twin. Of the six
# questions of `CommandConditionalBranchBattle` the game uses **only two** —the
# switch and the variable, in 1108 branches of 295 distinct bodies, measured
# on 2026-09-21— and those have the operands in the same place as the map's:
# `[kind, number, polarity or value kind, value, comparison, else]`. So they
# are translated to the map's code and compile to OP_IF and OP_IF_VAR without
# a new opcode. The other four —whether an actor or an enemy can act, whom it
# targets, which command it gave— ask for battle state and do not compile.
BATTLE_BRANCH = {13310: COND_BRANCH, 23310: COND_ELSE, 23311: COND_END}
BATTLE_BRANCH_KINDS = (COND_SWITCH, COND_VARIABLE)

# `ShowHiddenMonster`, which only exists in battle: the troop member in that
# place —from 0, in troop order— stops being hidden. See OP_SHOW_ENEMY and
# `ba_show_hidden`.
SHOW_HIDDEN_MONSTER = 13150

# What a troop page can do in this port. **It is a list of the ones that do,
# not of the ones that do not**, on purpose: almost everything that compiles
# on a map assumes the map —a teleport, a route, a tint, a choice, which opens
# the map's window— and inside the battle it would do something else without
# warning.
#
# `PlaySound` sounds in the battle's audio package if its effect fits there
# —see `TroopPages.compile`—, and `ShakeScreen` moves the scene: see
# `ba_shake`. Its wait, an OP_DELAY, is counted by `ba_page_step`.
#
# The ones left out that the game uses, in case someone wants to add them:
# `ChangeHP` and `FullHeal` —in battle HP lives in `BA_ONE` and `FAR_HP` is
# overwritten when closing it—, `ChangePartyMembers`, `ChangeEquipment`,
# `Wait`, `TintScreen` and five of the six that only exist in battle.
TROOP_COMMANDS = ({END, SHOW_MESSAGE, SHOW_MESSAGE_2, CONTROL_SWITCHES,
                   CONTROL_VARS, CHANGE_SKILLS, CHANGE_GOLD, CHANGE_ITEMS,
                   PLAY_SOUND, SHAKE_SCREEN, SHOW_HIDDEN_MONSTER,
                   COND_BRANCH, COND_ELSE, COND_END} | IGNORABLE)

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
TROOP_TRIGGERS = {"switch_a": TROOP_TRIGGER_SWITCH_A,
                  "switch_b": TROOP_TRIGGER_SWITCH_B,
                  "variable": TROOP_TRIGGER_VARIABLE,
                  "turn": TROOP_TRIGGER_TURN,
                  "enemy_hp": TROOP_TRIGGER_ENEMY,
                  "actor_hp": TROOP_TRIGGER_ACTOR}
# How many pages of a troop the battle notes as "already ran this turn", one
# byte each in `BA_PAGE_DONE`. It is a far RAM cap and not the game's: the
# converter stops if any troop goes over.
TROOP_PAGES_MAX = 32

# The triggers that carry a **header**: the turn and HP numbers do not go in
# per-page tables in bank 1 —which no longer has room for ten bytes for each
# of the five hundred— but in front of the page's code, in `troop_code`,
# which is in RODATA. See `troop_header` and `ba_page_header`.
TROOP_WITH_HEADER = (TROOP_TRIGGER_TURN | TROOP_TRIGGER_ENEMY
                     | TROOP_TRIGGER_ACTOR)
TROOP_HEADER_BYTES = 10


def troop_header(trigger):
    """The ten bytes that go in front of the code of a page that looks at
    the turn or the HP: the turn's base and multiple, a word each, and the
    enemy's place, the actor and their ranges, a byte each. Empty if it looks
    at none of that. The order is `BA_COND`'s in
    tools/runtime/ram_lejana.s."""
    if not trigger.flags & TROOP_WITH_HEADER:
        return b""
    d = trigger
    output = bytes([d.turn_base & 0xFF, d.turn_base >> 8,
                    d.turn_mult & 0xFF, d.turn_mult >> 8,
                    d.enemy, d.enemy_min, d.enemy_max,
                    d.actor, d.actor_min, d.actor_max])
    assert len(output) == TROOP_HEADER_BYTES
    return output


def troop_commands(commands):
    """The commands of a troop page as if they were a map's, or `CannotCompile`
    if any is not in `TROOP_COMMANDS`.

    Returns copies: the database's are shared by all the troops that have
    the same page, and translating them in place would leave them translated
    for whoever reads them later."""
    from rpgmaker import lcf
    output = []
    for cmd in commands:
        code = BATTLE_BRANCH.get(cmd.code, cmd.code)
        if cmd.code == 13310 and (not cmd.parameters
                                  or cmd.parameters[0]
                                  not in BATTLE_BRANCH_KINDS):
            raise CannotCompile("a battle branch that asks about the battle")
        if code not in TROOP_COMMANDS:
            raise CannotCompile("command %d does not run in a troop page"
                                % cmd.code)
        output.append(lcf.EventCommand(code, cmd.indent, cmd.string,
                                       cmd.parameters))
    return output


# The trigger of a troop page, with what the ROM reads from each one. The
# fields of what the page does not look at go at zero.
Trigger = collections.namedtuple("Trigger", (
    "flags", "switch_a", "switch_b", "slot", "value",
    "turn_base", "turn_mult", "enemy", "enemy_min", "enemy_max",
    "actor", "actor_min", "actor_max"))


def troop_trigger(page):
    """The `Trigger` of a troop page, or None if it looks at something the
    ROM does not know how to look at.

    A page **without any trigger never runs** —`AreConditionsMet` returns
    false right away— and it also gives None: there is no point carrying it.
    The variable one is `>=`, always: RM2k gives it no operator.

    **The turn goes with base and multiple in that order**, and not in the
    names' order: easyrpg calls `CheckTurns(turno, turn_b, turn_a)` and its
    signature is `(turns, base, multiple)`, so `turn_b` is the base. With the
    other order the agents' takeoff page —`turn_a` 0, `turn_b` 1— would run on
    every turn instead of on the first.

    HP is in percent, from 0 to 100: an enemy's by its place in the troop,
    an actor's by its LDB number."""
    if not page.active:
        return None
    if any(a not in TROOP_TRIGGERS for a in page.active):
        return None
    c = page.condition
    flags = 0
    for a in page.active:
        flags |= TROOP_TRIGGERS[a]
    switch_a = c["switch_a_id"] if "switch_a" in page.active else 0
    switch_b = c["switch_b_id"] if "switch_b" in page.active else 0
    for s in (switch_a, switch_b):
        if not 0 <= s < SWITCH_MAX:
            return None
    slot, value = 0, 0
    if "variable" in page.active:
        value = c["variable_value"]
        if not -0x8000 <= value <= 0x7FFF:
            return None
        try:
            slot = variable_slot(c["variable_id"])
        except CannotCompile:
            return None
    base, mult = 0, 0
    if "turn" in page.active:
        base, mult = c["turn_b"], c["turn_a"]
        if not (0 <= base <= 0xFFFF and 0 <= mult < 0x8000):
            return None     # `ba_div` requires the divisor below 32768
    enemy, e_min, e_max = 0, 0, 0
    if "enemy_hp" in page.active:
        enemy, e_min, e_max = (c["enemy_id"], c["enemy_hp_min"],
                               c["enemy_hp_max"])
        if not (0 <= enemy < 256 and 0 <= e_min <= 100
                and 0 <= e_max <= 100):
            return None
    actor, a_min, a_max = 0, 0, 0
    if "actor_hp" in page.active:
        actor, a_min, a_max = (c["actor_id"], c["actor_hp_min"],
                               c["actor_hp_max"])
        if not (0 <= actor < 256 and 0 <= a_min <= 100
                and 0 <= a_max <= 100):
            return None
    return Trigger(flags, switch_a, switch_b, slot, value, base, mult,
                   enemy, e_min, e_max, actor, a_min, a_max)


class TroopPages:
    """The pages of the cartridge's troops, compiled and deduplicated.

    `cuerpos` is the code of all of them, one after the other and **each
    distinct body only once**: the game copies its systems' pages into every
    troop —4588 pages and 295 distinct bodies—, so the key is the already
    compiled bytecode, same as `Materials` with the map's blocks.

    The messages go to **their own block**, `messages_troop`, and not to the
    maps': `OP_MESSAGE` carries a sixteen-bit offset and the maps' block of
    the test cartridge is already around 65 KB. The battle draws them on its
    screen and not in the map's window, so reading them from elsewhere costs
    it nothing.
    """

    def __init__(self):
        self.messages = Messages()
        self.bodies = bytearray()
        self.where = {}             # bytecode -> offset in `cuerpos`
        self.per_troop = {}         # troop -> [(Trigger, ofs)]
        self.pages = 0            # how many were looked at
        self.left_out = 0             # and how many did not get in

    def compile(self, number, troop, songs=None):
        """A troop's pages. With `songs`, a `PlaySound` is compiled with its
        effect, which counts for **the battle's audio package** —the one
        loaded when the page runs, see `BATTLE_PACKAGE`— and not for the
        map's; and it goes into it only if it is in `se_troop_in_package`
        (snes_music.py): otherwise it is asked for and does not sound, like a
        route one that does not fit. Without `songs` it is accepted and not
        done."""
        theirs = []
        previous = songs.current_map if songs is not None else None
        if songs is not None:
            songs.current_map = BATTLE_PACKAGE
        try:
            for page in troop.pages:
                self.pages += 1
                trigger = troop_trigger(page)
                code = None
                if trigger is not None:
                    try:
                        commands = troop_commands(page.commands)
                    except CannotCompile:
                        commands = None
                    if commands is not None:
                        code = compile_page(_Commands(commands),
                                            lambda _map: None,
                                            self.messages, songs=songs)
                if code is None:
                    self.left_out += 1
                    continue
                # The header goes right in front and is part of the key: two
                # pages with the same code and another turn are two bodies.
                # The offset noted is the code's, so the ROM finds the header
                # `TROOP_HEADER_BYTES` before it.
                header = troop_header(trigger)
                key = header + bytes(code)
                if key not in self.where:
                    self.where[key] = len(self.bodies) + len(header)
                    self.bodies += key
                theirs.append((trigger, self.where[key]))
        finally:
            if songs is not None:
                songs.current_map = previous
        self.per_troop[number] = theirs
        return theirs


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
# can do without floating point: see `enc_step_thresholds`.

# Every how many steps, by default, if the node does not carry the chunk
# (liblcf: rpg::MapInfo::encounter_steps).
ENC_DEFAULT_STEPS = 25

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
    the contract**: both sides use this same number.

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


def encounter_troop(cmd):
    """The troop number of an `EnemyEncounter`, or `CannotCompile`.

    The indices come from easyrpg-player's
    `Game_Interpreter_Map::CommandEnemyEncounter`, **not from memory**: `[0]`
    says whether the troop comes from a variable, `[1]` is the troop, `[2]`
    where the backdrop comes from, `[3]` what happens on escape, `[4]` what
    happens on defeat and `[5]` whether the party strikes first.

    What this port does, and why the rest cuts the page:

    * **the troop by constant**: reading it from a variable would require
      resolving in the ROM which troop it is, and none of the game's 51
      battles uses it;
    * **escape forbidden or with a handler**, but not `escape_mode` 1, which
      in RM2k cuts the whole page on escaping —`abort_on_escape`— and would
      be a path with nothing exercising it;
    * **defeat**, with a handler or without: `defeat_mode` 0 is RM2k's Game
      Over screen, and since 2026-09-13 it is emitted as `BATTLE_LOSE` in
      the defeat's destination. The ROM notes it before fighting and, if it
      loses, shows the Game Over screen and from there goes back to boot
      —that is to the title screen, with the saved game waiting in SRAM—:
      see tools/runtime/game_over.s and what it still does not do in
      `workflow/divergencias/lo-que-la-pantalla-de-game-over-no-modela.md`.
      What is not done is what was done before 2026-09-13, which was not
      compiling the page: it cost 15, among them the Rat Tracks boss.

    The backdrop is not looked at here: `encounter_backdrop` gets it.
    """
    p = cmd.parameters
    if len(p) < 6:
        raise CannotCompile("EnemyEncounter with no operands")
    if p[0] != 0:
        raise CannotCompile("EnemyEncounter with the troop in a variable")
    if not 0 < p[1] <= 0xFFFF:
        raise CannotCompile("EnemyEncounter of troop %d" % p[1])
    if p[3] == BATTLE_ESCAPE_CUTS:
        raise CannotCompile("EnemyEncounter that cuts the page on escape")
    return p[1]


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


def target_actor(p, what):
    """The actor operand of OP_HEAL and OP_EQUIPMENT, from RM2k's
    `[tipo, id]`.

    It is easyrpg's `GetActors` (`game_interpreter.cpp:1539`): 0 the party,
    1 a fixed actor, 2 the actor a variable says. The operand is the actor,
    with 0 for "the whole party": the LDB has no actor 0, so it is not
    mistaken for anyone.

    Form 2 is not used by any `FullHeal` nor by any `ChangeHP` that adds
    —measured on 2026-09-19 over the 328 maps and the common events—, nor by
    any `ChangeEquipment` —on 2026-09-21—, so it does not compile instead of
    being resolved in the ROM with nothing exercising it.
    """
    if p[0] == 0:
        return 0
    if p[0] == 1 and 0 < p[1] <= 0xFF:
        return p[1]
    raise CannotCompile("%s with the actor in a variable" % what)


def with_dest(piece, dest):
    """The same piece with the destination set in its last two bytes."""
    return piece[:-2] + bytes([dest & 0xFF, dest >> 8])


def _patch(pieces, open_at, dest):
    """Puts `dest` in the open piece of the branch stack. An entry is the
    piece's index, with the destination in its last two bytes, or (index,
    offset) for a piece with more than one destination: `OP_CELL_TEST`."""
    if not isinstance(open_at, tuple):
        pieces[open_at] = with_dest(pieces[open_at], dest)
        return
    i, where = open_at
    piece = pieces[i]
    pieces[i] = (piece[:where] + bytes([dest & 0xFF, dest >> 8])
                 + piece[where + 2:])


# Where the two destinations go inside `OP_CELL_TEST`: see events.toml.
CELL_DEST_A = 10
CELL_DEST_B = 16
# The top two bits of each `OP_CELL_TEST` write, over the variable's offset:
# y instead of x, and the refresh. See `cell_test` in
# tools/runtime/interprete_celdas.s.
CELL_Y = 0x4000
CELL_REFRESH = 0x8000


def fadable_cells(commands):
    """Where each "is it on the cell?" pattern that `OP_CELL_TEST` does in a
    single opcode starts: two `ControlVars` that put the x and the y of the
    same character in two variables, and two nested `ConditionalBranch`es
    —the second is the first thing inside the first— that compare one
    variable with another for equality.

    It is the pattern of the parallel pages that check whether two
    characters touch: the forty of each lap of the race, the lights of map 11
    and some two hundred more in the game. Fused, it runs in a single turn of
    the interpreter instead of four, and it is what keeps the race at 60
    frames: see `cell_test` in tools/runtime/interprete_celdas.s.

    Only the shape is looked at here; whether the operands compile is said
    by `_cell_test_piece`, which is the one that emits.
    """
    def set_cell(c):
        p = c.parameters
        return (c.code == CONTROL_VARS and len(p) >= 7 and p[0] == 0
                and p[3] == VAR_SET and p[4] == VAR_CHARACTER)

    def equal_to_variable(c):
        p = c.parameters
        return (c.code == COND_BRANCH and len(p) >= 5 and p[0] == COND_VARIABLE
                and p[2] == 1 and p[4] == CMP_EQUAL)

    starts = []
    i = 0
    while i + 3 < len(commands):
        a, b, c, d = commands[i:i + 4]
        if (set_cell(a) and set_cell(b)
                and a.parameters[5] == b.parameters[5]
                and equal_to_variable(c) and equal_to_variable(d)
                and a.indent == b.indent == c.indent
                and d.indent == c.indent + 1):
            starts.append(i)
            i += 4
        else:
            i += 1
    return starts


def _cell_test_piece(writes, branches):
    """`OP_CELL_TEST` with the two destinations blank, built with what the
    four loose opcodes would emit —so the validations and the refresh are
    the same—, or None if it cannot be fused."""
    v1, v2 = writes
    r1, r2 = branches
    for v in (v1, v2):
        if (v[0] != OP_VAR or v[3] != VAR_CHARACTER or v[5] != 0
                or v[7] != 0 or v[6] not in (CHARACTER_X, CHARACTER_Y)
                or v[2] & ~VAR_REFRESH != VAR_SET):
            return None
    if v1[4] != v2[4]:
        return None
    for r in (r1, r2):
        if (r[0] != OP_IF_VAR or r[2] != VAR_VARIABLE or r[3] != CMP_EQUAL
                or r[5] != 0):
            return None
    def write(v):
        return (v[1] * 2 | (CELL_Y if v[6] == CHARACTER_Y else 0)
                | (CELL_REFRESH if v[2] & VAR_REFRESH else 0))

    words = [write(v1), write(v2),
             r1[1] * 2, r1[4] * 2, 0, r2[1] * 2, r2[4] * 2, 0]
    piece = bytes([OP_CELL_TEST, v1[4]]) + b"".join(
        bytes([w & 0xFF, w >> 8]) for w in words)
    assert len(piece) == OPCODE_SIZE[OP_CELL_TEST]
    return piece


def compile_page(page, map_index, messages=None, map_events=None,
                 songs=None, graphics=None, pictures=None, troops=None,
                 base=0, depth=0):
    """A page's commands as bytes, or None if it cannot be done.

    `map_index` translates the RM2k map id to the index in the ROM's
    table, and returns None for the maps that did not get into the
    cartridge: a teleport to one of those makes the page not runnable, which
    is more honest than jumping anywhere.

    `messages` is the ROM's text block. Without it the text boxes do not
    compile, and it is not a matter of taste: the window takes 8 KB of VRAM
    and a palette, so a ROM that does not carry it has nowhere to draw them.

    `map_events` is the map's `MapEvents`, already pointed at the page's
    owner. Without it a forced route can only be on the hero: there is
    nothing to translate the RM2k id to the table's index with.

    `troops` is the registry of the troops the cartridge is going to have to
    carry. **It does not change the bytecode** —the troop number emitted is
    RM2k's— so a ROM without a registry compiles exactly the same; the only
    thing lost is knowing which tables have to be emitted.

    `base` and `depth` are for `CallEvent`, which is compiled **inline**: the
    called event's body is emitted in the place of the call. `base` is where
    this piece starts inside the outer page, because the branches'
    destinations are absolute; `depth` is the nesting, which is capped. An
    inline piece **carries no `OP_DONE`**: in RM2k the called event's `END`
    returns to the caller, it does not end the page.
    """
    mark = messages.mark() if messages is not None else None
    try:
        # The branches are emitted with the destination blank and patched
        # when closing them, which is the only way: until what is inside is
        # compiled it is not known how much it takes. The stack carries the
        # nesting, so there is no need to look at the indentation as
        # `SkipToNextConditional` does —it walks the list of commands, here
        # the blocks already come properly nested—.
        pieces = []
        length = base         # see `base`: the branches' destinations are
                             # absolute within the outer page
        stack = []            # pieces with the destination still blank
        # The options of each `ShowChoice` are gathered looking ahead, which
        # is what `GetChoices` does, so they are resolved before the loop:
        # in here the commands come one at a time and already grouped.
        commands = list(page.commands)
        options_of = {id(c): choice_options(commands, i)
                      for i, c in enumerate(commands) if c.code == SHOW_CHOICE}
        # Which `EnemyEncounter`s come **without a handler block**. RM2k does
        # not emit it when the battle has no branch to write, which is
        # exactly what happens with `defeat_mode` 0: losing is the Game Over
        # screen and not a branch of the page. They are the game's 15 pages
        # this port did not compile —among them the Rat Tracks boss—, and
        # all 15 are like this: without this, accepting the Game Over left
        # them falling into "an unclosed battle". It looks ahead like a
        # `ShowChoice`'s options, because inside the loop the commands come
        # one at a time.
        no_block = {id(c) for i, c in enumerate(commands)
                    if c.code == ENEMY_ENCOUNTER
                    and (i + 1 >= len(commands)
                         or commands[i + 1].code not in BATTLE_HANDLERS)}
        # The four of "is it on the cell?", which go in a single opcode: see
        # `fadable_cells`. Each command's role —0 and 1 the writes, 2 and
        # 3 the branches— by its id, and each pattern's fused piece by its
        # first command's id, when it is emitted.
        cell_role = {}
        for i in fadable_cells(commands):
            for n in range(4):
                cell_role[id(commands[i + n])] = (n, id(commands[i]))
        cell_piece = {}
        choices = []            # the open choices
        bat = []             # and the open battles, same as them
        bgm = [None, [], []]  # the pending `PlayBGM`, what was noted and
                              # the jumps: see `_follow_exit`
        constants = {}      # the last thing the page put in each variable,
                             # if it was a constant: see `_recalled_destination`
        for cmd, extra in group_boxes(commands):
            requested = songs.requested if songs is not None else 0
            role = cell_role.get(id(cmd))
            if role is not None and role[0] == 0:
                # It is built here and not before because the refresh
                # depends on `map_events`, which changes after a
                # `Teleport`.
                i = commands.index(cmd)
                loose = commands[i:i + 4]
                faded = _cell_test_piece(
                    [_compile(c, map_index, messages, (), map_events,
                              songs, graphics, pictures)
                     for c in loose[:2]],
                    [branch_bytes(c) for c in loose[2:]])
                if faded is None:
                    for c in loose:
                        del cell_role[id(c)]
                    role = None
                else:
                    cell_piece[id(cmd)] = len(pieces)
            if role is not None:
                n, first = role
                piece = b""
                if n == 0:
                    piece = faded
                if n < 2:
                    _note_constant(cmd, constants)
                else:
                    stack.append((cell_piece[first],
                                  CELL_DEST_A if n == 2
                                  else CELL_DEST_B))
            elif cmd.code == ENEMY_ENCOUNTER:
                troop = encounter_troop(cmd)
                if troops is not None:
                    troops.request(troop, encounter_backdrop(cmd))
                # The song and effects the battle plays, noted in the
                # battle's package: see `battle_audio`.
                battle_audio(songs)
                losing_is_game_over = (len(cmd.parameters) > 4
                                       and cmd.parameters[4]
                                       == BATTLE_DEFEAT_GAME_OVER)
                if id(cmd) in no_block:
                    # No handlers: the battle closes right here. Winning and
                    # escaping continue with the command below —which is what
                    # RM2k does when there are no branches— and losing goes
                    # to `BATTLE_LOSE`, that is to the Game Over.
                    #
                    # **Escaping points to victory and not elsewhere**, and
                    # it is a declared approximation: the 24 battles of this
                    # form carry `escape_mode` 0 —escape forbidden—, so there
                    # the exit does not exist; here the battle lets you
                    # escape anyway, because the permission does not travel
                    # in the opcode: `ChangeEscapeAccess` is accepted and not
                    # done.
                    next_at = length + 9
                    lose = (BATTLE_LOSE if losing_is_game_over
                            else next_at)
                    piece = bytes([OP_BATTLE, troop & 0xFF, troop >> 8,
                                   next_at & 0xFF, next_at >> 8,
                                   next_at & 0xFF, next_at >> 8,
                                   lose & 0xFF, lose >> 8])
                else:
                    bat.append({"i": len(pieces), "tropa": troop,
                                "destinos": [None, None, None],
                                "game_over": losing_is_game_over,
                                "vistas": 0, "salidas": []})
                    piece = bytes(9)  # the room, filled in at the EndBattle
            elif cmd.code in BATTLE_HANDLERS:
                if not bat:
                    raise CannotCompile("a battle handler without its battle")
                current = bat[-1]
                n = BATTLE_HANDLERS.index(cmd.code)
                # The previous handler's body ends here and is taken out of
                # the block with a jump to the end, patched when closing it.
                # It is the same `ShowChoiceOption` does, and for the same
                # reason: that way there is no need to look at the
                # indentation.
                piece = b"" if not current["vistas"] else bytes([OP_GOTO, 0, 0])
                if piece:
                    current["salidas"].append(len(pieces))
                current["vistas"] += 1
                if current["destinos"][n] is not None:
                    raise CannotCompile("two identical battle handlers")
                current["destinos"][n] = length + len(piece)
            elif cmd.code == END_BATTLE:
                if not bat:
                    raise CannotCompile("a battle end without its battle")
                current = bat.pop()
                table = bytes([OP_BATTLE,
                               current["tropa"] & 0xFF, current["tropa"] >> 8])
                for n, dest in enumerate(current["destinos"]):
                    # The handler the page does not have falls at the end of
                    # the block, which is what RM2k does with a sub-index
                    # without a branch: `SetSubcommandIndex` and carry on.
                    # **Except the defeat with `defeat_mode` 0**, which there
                    # is not a missing branch but the Game Over: see
                    # `BATTLE_LOSE`.
                    if dest is None and n == 2 and current["game_over"]:
                        d = BATTLE_LOSE
                    else:
                        d = length if dest is None else dest
                    table += bytes([d & 0xFF, d >> 8])
                pieces[current["i"]] = table
                for output in current["salidas"]:
                    pieces[output] = with_dest(pieces[output], length)
                piece = b""
            elif cmd.code == SHOW_CHOICE:
                if messages is None:
                    raise CannotCompile("a choice with no window to put it in")
                options = options_of[id(cmd)]
                if not options:
                    raise CannotCompile("a choice without options")
                if [n for n, _ in options] != list(range(len(options))):
                    raise CannotCompile("options numbered out of order")
                cancel = cmd.parameters[0] if cmd.parameters else 0
                if cancel > len(options):
                    # `cancel_type` 5 with four options is the "cancel
                    # branch", a fifth one that is not in the list. Nobody
                    # uses it in this game and doing it blindly would be
                    # making things up.
                    raise CannotCompile("choice with a cancel branch")
                frames = choice_boxes(options, messages)
                choices.append({"i": len(pieces), "n": len(options),
                                "cancelar": cancel, "cuadros": frames,
                                "destinos": [None] * len(options),
                                "vistas": 0, "salidas": []})
                # The table's room, filled in at the `ShowChoiceEnd`.
                piece = bytes(3 + 4 * len(options))
            elif cmd.code == SHOW_CHOICE_OPTION:
                if not choices:
                    raise CannotCompile("an option without its choice")
                current = choices[-1]
                n = cmd.parameters[0] if cmd.parameters else 0
                if not 0 <= n < current["n"]:
                    raise CannotCompile("an option that is not in the list")
                # The previous option's body ends here: it is taken out of
                # the choice with a jump to the end, patched when closing it.
                # Emitting it here and not at the body's `END` is what keeps
                # this from depending on looking at the indentation.
                piece = b"" if not current["vistas"] else bytes([OP_GOTO, 0, 0])
                if piece:
                    current["salidas"].append(len(pieces))
                current["vistas"] += 1
                current["destinos"][n] = length + len(piece)
            elif cmd.code == SHOW_CHOICE_END:
                if not choices:
                    raise CannotCompile("a choice end without its choice")
                current = choices.pop()
                if any(d is None for d in current["destinos"]):
                    raise CannotCompile("an option without a body")
                table = bytes([OP_CHOICE, current["n"], current["cancelar"]])
                for frame, dest in zip(current["cuadros"],
                                       current["destinos"]):
                    table += bytes([frame & 0xFF, frame >> 8,
                                    dest & 0xFF, dest >> 8])
                pieces[current["i"]] = table
                for output in current["salidas"]:
                    pieces[output] = with_dest(pieces[output], length)
                piece = b""
            elif cmd.code == COND_BRANCH:
                stack.append(len(pieces))
                piece = branch_bytes(cmd)
            elif cmd.code == COND_ELSE:
                if not stack:
                    raise CannotCompile("an `else` without its `if`")
                open_at = stack.pop()
                piece = bytes([OP_GOTO, 0, 0])
                # The `if`'s destination is **after** this jump, which is
                # where the branch below starts; the jump's is resolved at
                # the `end`, with the piece left open in its place.
                _patch(pieces, open_at, length + 3)
                stack.append(len(pieces))
            elif cmd.code == COND_END:
                if not stack:
                    raise CannotCompile("an `end` without its `if`")
                open_at = stack.pop()
                _patch(pieces, open_at, length)
                piece = b""
            elif cmd.code == SHOW_INN:
                piece = _compile_inn(cmd, length, messages)
            elif cmd.code == CONTROL_SWITCHES \
                    and len(cmd.parameters) >= 4 \
                    and cmd.parameters[3] == SWITCH_TOGGLE:
                piece = _compile_toggle(cmd, length)
            elif cmd.code in (INN_STAY, INN_NO_STAY, INN_END):
                # The inn's three branches. None of the game's 18 pages
                # uses them —measured—, and doing them requires exactly what
                # `_compile_inn` does not have: a place to put the body of
                # "stayed" inside a choice that is already built.
                raise CannotCompile("an inn with its branches")
            elif cmd.code == CALL_EVENT:
                piece = _compile_call(cmd, length, depth, map_index,
                                      messages, map_events, songs,
                                      graphics, pictures, troops)
            else:
                piece = _compile(cmd, map_index, messages, extra,
                                 map_events, songs, graphics, pictures)
                # A jump to another map: the page keeps running there. See
                # `MapEvents.after_jump`.
                if cmd.code == TELEPORT and map_events is not None \
                        and cmd.parameters[0] != map_events.map_id:
                    map_events = map_events.after_jump()
                if cmd.code == RECALL_TO_LOCATION:
                    dest = _recalled_destination(cmd, constants, songs,
                                                 map_index)
                    if map_events is not None \
                            and dest != map_events.map_id:
                        map_events = map_events.after_jump()
                _note_constant(cmd, constants)
                # The switch of an equipment common event, turned on: its
                # body goes right here, as if a `CallEvent` followed it. In
                # RM2k it would run on the next frame; see
                # `PARTY_COMMON_EVENTS`.
                for number in _common_events_turned_on(cmd):
                    piece += compile_page(
                        _Commands(COMMON_EVENTS[number]), map_index, messages,
                        map_events, songs, graphics, pictures, troops,
                        base=length + len(piece), depth=depth + 1) or b""
            if songs is not None:
                _follow_exit(cmd, bgm, songs, map_index,
                             songs.requested != requested)
            pieces.append(piece)
            length += len(piece)
        if stack:
            raise CannotCompile("an unclosed branch")
        if choices:
            raise CannotCompile("an unclosed choice")
        if bat:
            raise CannotCompile("an unclosed battle")
        # What was noted from the `PlayBGM`s counts only if the page
        # compiles: one that does not, does not run, and says nothing about
        # how the map is left.
        if bgm[0] is not None:
            bgm[1].append((bgm[0], False))
        for song, is_exit in bgm[1]:
            songs.note_exit(song, is_exit)
        for dest, song in bgm[2]:
            songs.jump(dest, song)
        code = b"".join(pieces)
        # The `OP_DONE` belongs to the page and not to the piece: an inline
        # body carrying it would end the caller's page instead of returning
        # control to it. See `base`.
        return code if depth else code + bytes([OP_DONE])
    except CannotCompile:
        if messages is not None:
            messages.rewind(mark)
        return None


def _common_events_turned_on(cmd):
    """The `PARTY_COMMON_EVENTS` events whose switch this command turns on."""
    p = cmd.parameters
    if cmd.code != CONTROL_SWITCHES or len(p) < 4 or p[3] != SWITCH_ON \
            or p[0] not in (SWITCH_SINGLE, SWITCH_RANGE):
        return []
    return [number for switch, number in sorted(PARTY_COMMON_EVENTS.items())
            if p[1] <= switch <= p[2]]


def _note_constant(cmd, constants):
    """Keeps in `constants` the last thing the page put in each variable
    when it was a constant, and forgets the variable if it wrote it some
    other way. It does not look at branches: it is for `_recalled_destination`,
    which only uses it to note an audio destination."""
    p = cmd.parameters
    if cmd.code == CONTROL_VARS and len(p) >= 7:
        first, last = (p[1], p[1]) if p[0] == 0 else (p[1], p[2])
        for number in range(first, last + 1):
            constants.pop(number, None)
        if p[0] == 0 and p[3] == VAR_SET and p[4] == VAR_CONSTANT:
            constants[p[1]] = p[5]
    elif cmd.code in (MEMORIZE_LOCATION, KEY_INPUT_PROC, STORE_TERRAIN_ID) \
            and p:
        for number in (p[:3] if cmd.code == MEMORIZE_LOCATION
                       else p[3:4] if cmd.code == STORE_TERRAIN_ID else p[:1]):
            constants.pop(number, None)


def _recalled_destination(cmd, constants, songs, map_index):
    """The RM2k id of the map a `RecallToLocation` jumps to, if the page set
    it with a constant before —the breaking floors load 61 or 60 into the
    variable, and jump right away—, or None.

    What is known is noted as the map's destination in `songs`, same as a
    `Teleport`: it is where it comes from which song may be playing on
    arrival. What is not known —the way back from a tutorial, which jumps to
    whatever another page remembered— is not noted, and it is the only thing
    the audio does not see: the song that arrives that way has to be in the
    destination's package by another path. In the game it is the droid
    tutorial going back to 48 with the song it left there with."""
    dest = constants.get(cmd.parameters[0]) if cmd.parameters else None
    if dest is not None and songs is not None:
        index = map_index(dest)
        if index is not None:
            songs.dest(index)
            if index != songs.current_map:
                songs.jump(index, None)
    return dest


# What cuts an exit `PlayBGM` before the jump: branches, choices, battles,
# calls and loops —with them, what follows is no longer a single line—. The
# effects too, but those show in `Songs.requested`, which also counts an
# animation's.
CUT_THE_EXIT = frozenset((
    COND_BRANCH, COND_ELSE, COND_END, SHOW_CHOICE, SHOW_CHOICE_OPTION,
    SHOW_CHOICE_END, ENEMY_ENCOUNTER, END_BATTLE, CALL_EVENT, SHOW_INN,
    INN_STAY, INN_NO_STAY, INN_END,
    # A jump whose destination is not always known: it is taken as not
    # leaving.
    RECALL_TO_LOCATION, PLAY_MEMORIZED_BGM) + BATTLE_HANDLERS
    # Label, JumpToLabel, Loop, BreakLoop, EndLoop and EndEventProcessing.
    + (12110, 12120, 12210, 12220, 22210, 12310))


def _follow_exit(cmd, output, songs, map_index, played_sound):
    """Follows, command by command, whether the page's last `PlayBGM` is an
    exit one —see `Songs.exit_songs`—: it is if what comes up to a
    `Teleport` to another map plays no effect (`played_sound`), turns on no other
    song and does not branch. `output` is [the pending song or None, what
    was noted]; what was noted is passed to `songs` only if the page
    compiles.

    A jump to the same map also cuts it: it reloads the package with the
    song playing, which is the inheritance case and not the leaving one.

    And it notes in `salida[2]` each jump to another map with the song it
    carries if it is an exit one, or None: see `Songs.jump`."""
    pending, noted = output[:2]
    if cmd.code == TELEPORT and songs.current_map is not None:
        dest = map_index(cmd.parameters[0])
        if dest is not None and dest != songs.current_map:
            output[2].append((dest, pending))
    if cmd.code == PLAY_BGM and cmd.string:
        if pending is not None:
            noted.append((pending, False))
        output[0] = songs.names.index(cmd.string)
        return
    if pending is None:
        return
    if cmd.code == TELEPORT:
        is_exit = map_index(cmd.parameters[0]) != songs.current_map
        noted.append((pending, is_exit))
        output[0] = None
    elif played_sound or cmd.code in CUT_THE_EXIT:
        noted.append((pending, False))
        output[0] = None


# How deep a `CallEvent` nests. It is not an abstract precaution: a common
# event can call itself —the inline body would be infinite— and two can call
# each other. In this game the longest chain that compiles is one.
CALL_MAX = 4


class _Commands:
    """A wrapper with `.commands`, which is the only thing `compile_page`
    looks at in a page. The common events, which are not pages, need it."""

    def __init__(self, commands):
        self.commands = commands


def _compile_call(cmd, length, depth, map_index, messages,
                  map_events, songs, graphics, pictures, troops):
    """`CallEvent`, compiled **inline**: the called event's body goes in the
    place of the call.

    In RM2k this is `Push<ExecutionType::Call>`, that is a stack of
    interpreters. Here none is needed, and that is the decision: the called
    one runs whole before the caller continues, so pasting its bytecode in
    the middle gives exactly the same. What a real stack would cost —a cursor
    and a page per level in bank 0's RAM, which is full— buys no observable
    difference: **no call in this game is recursive**, and the only price of
    pasting is the size, measured below.

    And it comes without touching the ROM: it runs the same bytecode as
    always.

    **If the called one does not compile, the call is skipped**, which is
    what the port has always done with this command. It is declared debt and
    not equivalence, and requiring it to compile would cost 183 pages that
    run today: measured, only 6 of the 189 pages that compile and call have
    all their targets compilable.
    """
    p = list(cmd.parameters)
    if len(p) < 2 or depth >= CALL_MAX:
        return b""
    if p[0] == 0:
        # A common event, by number. This game's are cut almost all of them
        # at `ControlVars` and at the original's own menus.
        dest, ctx = COMMON_EVENTS.get(p[1]), map_events
    elif p[0] == 1 and len(p) >= 3 and map_events is not None:
        # A map event, by id and **page number**, which in RM2k starts at
        # one: it is `CommandCallEvent`'s `page->ID`.
        pages = map_events.pages.get(p[1])
        if pages is None or not 1 <= p[2] <= len(pages):
            return b""
        dest = pages[p[2] - 1].commands
        # "This event" inside the called one is **the called one**, not the
        # caller: `Push` passes it `event->GetId()`. Without this a
        # Hover-Tram route would move the Tram Officer.
        ctx = map_events.for_event(p[1])
    else:
        # By variable —type 2— it is not resolved at compile time and never
        # will be: the number comes from the save. It is skipped, as
        # before.
        return b""
    if not dest:
        return b""
    return compile_page(_Commands(dest), map_index, messages, ctx,
                        songs, graphics, pictures, troops,
                        base=length, depth=depth + 1) or b""


def _compile_toggle(cmd, length):
    """`ControlSwitches` that toggles: no opcode of its own, one branch per
    switch with what the interpreter already does —like the inn, it is
    built here because the destinations are absolute within the page and the
    one that carries `length` is `compile_page`'s loop—. For each switch,
    with the offsets relative to its piece:

         0  OP_IF       on, and if not, to 14
         7  OP_SWITCH   turn it off
        11  OP_GOTO     to 18
        14  OP_SWITCH   turn it on
        18  the next one

    It is 18 bytes per switch against the 4 of an opcode that flipped the
    bit, and the game toggles a single one, 286, twelve times in Eisen's
    story (89 ev4 and 93 ev4 p2): it does not justify code in the ROM."""
    p = cmd.parameters
    if p[0] not in (SWITCH_SINGLE, SWITCH_RANGE):
        raise CannotCompile("toggling switches by variable")
    first, last = p[1], p[2]
    if last < first or last - first >= MAX_RANGE:
        raise CannotCompile("toggling a range from %d to %d" % (first, last))
    out = b""
    for number in range(first, last + 1):
        here = length + len(out)
        turn_on, end = here + 14, here + 18
        low, height = number & 0xFF, number >> 8
        out += bytes([OP_IF, COND_SWITCH, low, height, 0,
                      turn_on & 0xFF, turn_on >> 8,
                      OP_SWITCH, low, height, 0,
                      OP_GOTO, end & 0xFF, end >> 8,
                      OP_SWITCH, low, height, 1])
    return out


def _compile_inn(cmd, length, messages):
    r"""`ShowInn`, expanded into commands the ROM already knows how to do.

    The inn is not a new opcode: it is the greeting with its choice, a branch
    on gold, the charge and the heal, which are five things the interpreter
    already did. It is built here and not in `_compile` because the
    destinations of the choice and of the branch are offsets **absolute
    within the page**, and that is known by `compile_page`'s loop, which
    is the one that carries `length`.

    What comes out, with the offsets relative to the start of the block:

         0  OP_MESSAGE  the greeting, two lines
         3  OP_CHOICE   "Yes" and "No"; cancel is "No"
        14  OP_IF       gold >= price, and if not, to the end
        21  OP_GOLD     it is charged
        26  OP_HEAL     the whole party to the maximum
        30  the end, which is where "No" and "cannot afford it" land

    The greeting is `CommandShowInn`'s (easyrpg
    `game_interpreter_map.cpp:449-560`): `"{greeting_1} {precio}{gold}
    {greeting_2}"` on the first line —hence the two spaces, because this
    game's `greeting_2` starts with one— and `greeting_3` on the second. The
    terms are from the LDB: see `index_terms`.

    **Three declared debts**, and all three are about what is seen and not
    about what happens:

    * there is no gold window next to the greeting;
    * "Yes" is not grayed out when it cannot be afforded, so it can be
      chosen; choosing it amounts to "No", which is what the gold branch
      does. In RM2k the cursor does not let it be selected;
    * there is no fade to black nor inn music: it charges and heals on the
      spot. That is `Scene_Map::CallInn`.

    **A free inn is just the heal**: with the price at zero `CommandShowInn`
    shows nothing and goes straight to
    `ContinuationShowInnStart(indent, 0, 0)`, which stays, charges zero and
    rests. They are 6 of the game's 18 pages, those of maps 39, 59, 77 and
    111 —the rooms where the script lets you sleep—.
    """
    p = cmd.parameters
    if len(p) < 2:
        raise CannotCompile("ShowInn with no operands")
    kind, price = p[0], p[1]
    if price == 0:
        return bytes([OP_HEAL, 0, 0, 0])
    if messages is None:
        raise CannotCompile("an inn with no window to put it in")
    if kind not in INN_TERMS:
        raise CannotCompile("inn of type %d, which is not in the terms: was "
                            "index_terms called?" % kind)
    if not price <= 0xFFFF:
        # The cap is the gold branch's operand, which goes in a word; the
        # game's most expensive is 100.
        raise CannotCompile("inn of %d, which does not fit in the gold branch"
                            % price)
    greeting_1, greeting_2, greeting_3, yes, no = INN_TERMS[kind]
    where = messages.add(
        ["%s %d%s %s" % (greeting_1, price, INN_TERMS["gold"], greeting_2),
         greeting_3])
    frames = choice_boxes([(0, yes), (1, no)], messages)
    end = length + 30
    branch = bytes([OP_IF, COND_GOLD, price & 0xFF, price >> 8, 0,
                    end & 0xFF, end >> 8])
    return (bytes([OP_MESSAGE, where & 0xFF, where >> 8])
            # Cancel is the second option: there the default
            # `choice_cancel_type` is 5 and `inn_stay` is
            # `choice_result == 0`, that is cancelling is not staying.
            + bytes([OP_CHOICE, 2, 2])
            + bytes([frames[0] & 0xFF, frames[0] >> 8,
                     (length + 14) & 0xFF, (length + 14) >> 8])
            + bytes([frames[1] & 0xFF, frames[1] >> 8,
                     end & 0xFF, end >> 8])
            + branch
            + bytes([OP_GOLD, 1, price & 0xFF, (price >> 8) & 0xFF, 0])
            + bytes([OP_HEAL, 0, 0, 0]))


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


def _compile_picture(cmd, pictures):
    """The three `Picture` commands, or None if this picture does not fit.

    The parameter indices come from easyrpg-player's `CommandShowPicture` and
    `CommandMovePicture`, **not from memory**: the two read fourteen and
    sixteen, and the order is not the one one would guess —the color and the
    saturation go in 8..11 and the effect mode in 12—.
    """
    p = cmd.parameters
    if pictures is None:
        return None
    if cmd.code == ERASE_PICTURE:
        if not p or not pictures.owns(p[0], None, None):
            return None
        return bytes([OP_PICTURE_ERASE])
    if not picture_fits(p):
        return None
    tone = (p[8], p[9], p[10], p[11])
    if cmd.code == SHOW_PICTURE:
        # `use_transparent_color`: whether the PNG's index 0 is drawn or not.
        # The "1 year earlier" picture has it off, so it is an opaque
        # rectangle; making it transparent would require one palette color
        # less and knowing which was index 0 before reducing.
        if p[7] or pictures.show(p[0], cmd.string, p[2], p[3]) is None:
            return None
        return bytes([OP_PICTURE]) + bytes(tone)
    # MovePicture: the same picture, in the same place, with another tone.
    # The duration comes in **tenths** —`data.time_left = duration *
    # DEFAULT_FPS / 10`—, which is what had to be looked up: the first one's
    # 35 are three and a half seconds, not half a second.
    if not pictures.owns(p[0], p[2], p[3]):
        return None
    frames = p[14] * FRAMES_PER_TENTH
    if not 0 <= frames <= PICTURE_FRAMES_MAX:
        return None
    output = bytes([OP_PICTURE_MOVE]) + bytes(tone) + bytes([frames])
    if len(p) > 15 and p[15] and frames:
        # `options.wait`: the page waits as long as it lasts, like
        # `FlashScreen`.
        output += bytes([OP_DELAY, frames & 0xFF, frames >> 8])
    return output


def sound_index(songs, map_index, name, volume, tempo, balance,
                from_route=False):
    """The `Songs.sounds` index of an effect asked for on the map being
    compiled: `PlaySound`'s and, with `from_route`, that of move command
    35.

    The ones that on some map sound with another sample —map 1's whole
    thunder— carry another name for the same WAV, so the other maps keep
    theirs. See `se_per_map` in snes_music.py. And the route ones of the
    `se_route_left_out` maps do not go into the package: see there."""
    from audio import snes_music

    def is_it(game_map):
        try:
            return songs.current_map == map_index(game_map)
        except Exception:
            return False

    in_package = True
    if songs.current_map is not None:
        for (base, game_map), alias in snes_music.se_per_map().items():
            if name == base and is_it(game_map):
                name = alias
                break
        if from_route:
            in_package = not any(
                is_it(m) and (which_ones is None or name in which_ones)
                for m, which_ones in snes_music.se_route_left_out().items())
    if songs.current_map == BATTLE_PACKAGE:
        # A troop page's: see `se_troop_in_package`.
        in_package = name in snes_music.se_troop_in_package()
    return songs.sound(name, volume, tempo, balance, in_package)


def _compile(cmd, map_index, messages=None, extra=(),
             map_events=None, songs=None, graphics=None, pictures=None):
    p = cmd.parameters

    if cmd.code == END or cmd.code in IGNORABLE:
        return b""

    if cmd.code == PLAY_SOUND:
        # Without a song registry it is accepted and not done, as before. An
        # empty name is "(OFF)": it plays nothing.
        if songs is None or not cmd.string or len(p) < 3:
            return b""
        k = sound_index(songs, map_index, cmd.string, p[0], p[1],
                        p[2])
        return bytes([OP_SOUND, k & 0xFF, k >> 8])

    if cmd.code == WEATHER_EFFECTS:
        if len(p) < 2:
            raise CannotCompile("WeatherEffects with no operands")
        return bytes([OP_WEATHER, p[0] & 0xFF, min(max(p[1], 0), 2)])

    if cmd.code == OPEN_SHOP:
        if len(p) < 4:
            raise CannotCompile("OpenShop with no operands")
        if p[2]:
            raise CannotCompile("OpenShop with the bought and did-not-buy branches")
        sells = [i for i in p[4:] if 0 < i < ITEMS_N]
        if len(sells) > 255 or not 0 <= p[0] <= 2 or not 0 <= p[1] <= 2:
            raise CannotCompile("OpenShop that does not fit in OP_SHOP")
        return bytes([OP_SHOP, p[0], p[1], len(sells)]) + b"".join(
            bytes([i & 0xFF, i >> 8]) for i in sells)

    if cmd.code == FULL_HEAL:
        # The amount at 0 is what tells it apart from `ChangeHP`, below.
        if len(p) < 2:
            raise CannotCompile("FullHeal with no operands")
        return bytes([OP_HEAL, target_actor(p, "FullHeal"), 0, 0])
    if cmd.code == CHANGE_HP:
        # [type, id, subtracts, amount by variable, amount, lethal]. The one
        # that adds shares OP_HEAL with `FullHeal`, with the amount set: it
        # is `Game_Battler::ChangeHp` (`game_battler.cpp:480`), which does not
        # touch the downed and caps at the maximum —`SetHp`—. It does not
        # touch SP.
        #
        # An amount of zero does nothing in RM2k, and here it is not
        # emitted: in OP_HEAL zero means `FullHeal`.
        #
        # The 11 that add outside battle are constants —seven of 1 to the
        # party, four of 300 and 999 to one actor—, so the amount in a
        # variable does not compile. The ones that subtract are still out:
        # they can kill, and `lethal` asks what to do about that.
        if len(p) < 5 or p[2] != 0:
            raise CannotCompile("ChangeHP that subtracts")
        if p[3] != 0:
            raise CannotCompile("ChangeHP with the amount in a variable")
        if not 0 <= p[4] <= 0xFFFF:
            raise CannotCompile("ChangeHP of %d" % p[4])
        if p[4] == 0:
            return b""
        return bytes([OP_HEAL, target_actor(p, "ChangeHP"),
                      p[4] & 0xFF, p[4] >> 8])
    if cmd.code == CHANGE_SKILLS:
        # [type, id, forgets, skill by variable, skill]. It is easyrpg's
        # `CommandChangeSkills`: `LearnSkill` or `UnlearnSkill` on each actor
        # of the target, without asking for the page refresh —it does not
        # ask for it there either— and without a message: the "learned such
        # a thing" is written by the page with a `ShowMessage`.
        #
        # The game's 898 are all fixed actor and constant skill, so the
        # operand is directly the bit: see `SKILL_SLOT`. The party, the
        # actor by variable and the skill by variable do not compile.
        if len(p) < 5:
            raise CannotCompile("ChangeSkills with no operands")
        if p[0] != 1:
            raise CannotCompile("ChangeSkills on the party or an actor by "
                                "variable")
        if p[3] != 0:
            raise CannotCompile("ChangeSkills with the skill in a variable")
        slot = skill_slot(p[1], p[4])
        return bytes([OP_SKILL, slot & 0xFF, slot >> 8,
                      0 if p[2] else 1])
    if cmd.code == CHANGE_EQUIPMENT:
        # [type, id, operation, a, b]. Operation 1 is unequipping slot `a`
        # —0 to 4, weapon to accessory; 5 is everything— and it is
        # `Game_Actor::ChangeEquipment(ranura, 0)`: the slot is left empty and
        # what it had goes back to the inventory, capped at ITEM_MAX. It does
        # not ask for the refresh either: `CommandChangeEquipment` does not
        # ask for it.
        #
        # The 35 the game runs outside battle all unequip a slot; the 560
        # that equip belong to the troops, which this port does not run. So
        # equipping does not compile, and unequipping everything does not
        # either: nobody uses it.
        if len(p) < 4:
            raise CannotCompile("ChangeEquipment with no operands")
        if p[2] != 1:
            raise CannotCompile("ChangeEquipment that equips")
        if not 0 <= p[3] < EQUIPMENT_SLOTS:
            raise CannotCompile("ChangeEquipment that unequips everything")
        actor = target_actor(p, "ChangeEquipment")
        if _INDEXED_ACTORS and actor and actor not in ACTOR_EQUIPMENT:
            raise CannotCompile("actor %d is not in the LDB" % actor)
        return bytes([OP_EQUIPMENT, actor, p[3]])
    if cmd.code == GAME_OVER:
        # `CommandGameOver`: the Game Over screen and, on pressing, the
        # title. It is the same as losing a battle without a handler —see
        # `BATTLE_LOSE`—: tools/runtime/game_over.s.
        return bytes([OP_GAME_OVER])
    if cmd.code == RETURN_TO_TITLE:
        # `ReturntoTitleScreen`: the same without the screen, that is going
        # back to boot, which in `release` is the title screen. The end of
        # the demo asks for it, in map 66's fork (`rom/parches/manual/`).
        # Until 2026-09-28 it shared the opcode with `GameOver`, when neither
        # of the two drew anything.
        return bytes([OP_RETURN_TO_TITLE])
    if cmd.code == CHANGE_CONDITION:
        if len(p) < 3 or p[2] != 1:
            raise CannotCompile("ChangeCondition that sets a state")
        return b""

    if cmd.code == KEY_INPUT_PROC:
        # [variable, wait, the four directions, the action one, cancel]. The
        # game's 32 occurrences have the five and no more: with six or more
        # RM2k 1.50 goes on to look at each direction separately, which is
        # another program, so the length is required instead of assumed.
        if len(p) != 5:
            raise CannotCompile("KeyInputProc with %d operands" % len(p))
        flags = ((KEY_WAIT if p[1] else 0)
                 | (KEY_DIRS if p[2] else 0)
                 | (KEY_DECISION if p[3] else 0)
                 | (KEY_CANCEL if p[4] else 0))
        if not flags & (KEY_DIRS | KEY_DECISION | KEY_CANCEL):
            # With no key asked for, the waiting form never comes out.
            raise CannotCompile("KeyInputProc with no key")
        if not p[1]:
            # The form that does not wait: it reads what is pressed and the
            # page continues on the same frame. In the game there are four
            # pages, the steering wheel of the car chase —`RaceController2`
            # on maps 49, 51, 52 and 54—, which also forces the hero's route
            # on every frame.
            #
            # It was not accepted until 2026-09-27, first because of the
            # Python reference —which did not know that a forced route rules
            # over the pad— and then, when the reference went away, because
            # nobody had looked at it again. On accepting it two things of the
            # ROM that no compiled page exercised showed up: that `op_key`
            # looked at edges in this form too —see `key_value`— and that
            # a `Teleport` from a parallel page was not handled with the
            # foreground idle —see the main loop—.
            # `test_recorrido_carrera_golden.py` enforces it.
            return bytes([OP_KEY, variable_slot(p[0]),
                          flags | write_needs_refresh(p[0],
                                                      map_events)])
        # **The wait is done with all three: the D-pad, the action key and
        # cancel**, since 2026-09-13. Until that day only the action one
        # counted, and the written reason was the **harness**'s and not the
        # ROM's: the suite held a direction from boot and pressed A on noted
        # frames, so a D-pad edge in the middle of a scene could not be
        # produced by any case, and modeling it anyway would have been
        # writing a path nothing runs.
        #
        # That reason stopped holding with `rom/pruebas/arnes/recorrido.py`,
        # which plays the real game and can press any button on any frame,
        # and with `--tocar` of both halves of the suite, which presses a
        # direction on a noted frame the way A was already pressed.
        #
        # What it unlocks, measured: the two pages of `(151, 1, 1, 1, 1)`
        # —the one that waits for all three— and, together with variable 5's
        # slot, the one of the stones minigame engine on map 11, which is
        # `(8, 1, 1, 0, 0)`: without this no stone can be thrown.
        slot = variable_slot(p[0])
        flags |= write_needs_refresh(p[0], map_events)
        return bytes([OP_KEY, slot, flags | KEY_START,
                      OP_KEY, slot, flags])

    if cmd.code == CHANGE_SPRITE_ASSOCIATION:
        # [actor, CharSet index, transparent]. See OP_ACTOR_SPRITE.
        if len(p) != 3:
            # With four it is the bitfield of "this comes from a variable",
            # which this game never uses.
            raise CannotCompile("ChangeSpriteAssociation with operands we do not "
                                "know how to read")
        if p[2]:
            raise CannotCompile("transparent ChangeSpriteAssociation: the console "
                                "does not fade a sprite without color math")
        if not 0 < p[0] < 256:
            raise CannotCompile("ChangeSpriteAssociation on actor %d" % p[0])
        if graphics is None:
            raise CannotCompile("ChangeSpriteAssociation without a graphics table")
        chosen = graphics.index(cmd.string, p[1])
        if chosen > 0xFF:
            raise CannotCompile("too many graphics on the map")
        return bytes([OP_ACTOR_SPRITE, p[0], chosen])

    if cmd.code in (CHANGE_SAVE_ACCESS, CHANGE_MENU_ACCESS,
                    CHANGE_ESCAPE_ACCESS):
        if not p:
            raise CannotCompile("%s with no operands" % cmd.code)
        which = {CHANGE_SAVE_ACCESS: ACCESS_SAVE,
                 CHANGE_MENU_ACCESS: ACCESS_MENU,
                 CHANGE_ESCAPE_ACCESS: ACCESS_ESCAPE}[cmd.code]
        return bytes([OP_ACCESS, ACCESS_BIT[which], 1 if p[0] else 0])

    if cmd.code == CHANGE_SCREEN_TRANSITIONS:
        # See CHANGE_SCREEN_TRANSITIONS and OP_TRANSITION.
        if len(p) < 2:
            raise CannotCompile("ChangeScreenTransitions with no operands")
        which, rm2k = p[0], p[1]
        if which not in (TRANSITION_ERASE, TRANSITION_SHOW):
            raise CannotCompile("the battle's ChangeScreenTransitions: the ROM "
                                "always uses the database's")
        if which == TRANSITION_ERASE and rm2k in RM2K_CUT_TRANSITIONS:
            return bytes([OP_TRANSITION, which, TRANSITION_CUT])
        if rm2k in RM2K_TRANSITIONS_NOT_DONE:
            raise CannotCompile("ChangeScreenTransitions to %s for showing, which "
                                "no ROM map uses"
                                % RM2K_TRANSITIONS_NOT_DONE[rm2k])
        kind = (TRANSITION_MOSAIC if rm2k == RM2K_TRANSITION_MOSAIC
                else TRANSITION_FADE)
        return bytes([OP_TRANSITION, which, kind])

    if cmd.code == CHANGE_ITEMS:
        # [add or remove, item by constant or variable, item, amount by
        # constant or variable, amount]. See OP_ITEM.
        if len(p) < 5:
            raise CannotCompile("ChangeItems with no operands")
        if p[1] != 0 or p[3] != 0:
            raise CannotCompile("ChangeItems with the item or the amount in a "
                                "variable")
        if not 1 <= p[2] < ITEMS_N:
            raise CannotCompile("ChangeItems of item %d, which is not in the LDB"
                                % p[2])
        delta = -p[4] if p[0] else p[4]
        if not -128 <= delta <= 127:
            raise CannotCompile("ChangeItems of %d, which does not fit in a byte"
                                % p[4])
        return bytes([OP_ITEM, p[2] & 0xFF, p[2] >> 8, delta & 0xFF])

    if cmd.code == CHANGE_GOLD:
        # `OperateValue(operation, type, value)`: the operation is 0 add and
        # 1 subtract, and the type 0 constant and 1 "the value is in a
        # variable". Without variables, the latter cannot be done.
        if len(p) < 3:
            raise CannotCompile("ChangeGold with no operands")
        if p[1] != 0:
            raise CannotCompile("ChangeGold with the amount in a variable")
        amount = p[2]
        if not 0 <= amount <= 0xFFFFFF:
            raise CannotCompile("ChangeGold of %d, which does not fit in three "
                                "bytes" % amount)
        return bytes([OP_GOLD, 1 if p[0] else 0,
                      amount & 0xFF, (amount >> 8) & 0xFF, (amount >> 16) & 0xFF])

    if cmd.code == PLAY_BGM:
        # Without a song registry it is accepted and not done, which is what
        # this repo did with PlayBGM from the start. With a registry the index
        # is emitted and the ROM plays the song if it got to carry it.
        if songs is None or not cmd.string:
            return b""
        return bytes([OP_BGM, songs.index(cmd.string) & 0xFF])

    if cmd.code == PAN_SCREEN:
        # Locking and unlocking the camera are used by no page of the game,
        # so they do not compile: modeling them with nothing exercising them
        # is making up a difference. Moving and resetting do, which are the
        # 133 there are.
        if len(p) < 5 or p[0] not in (PAN_SHIFT, PAN_RETURN):
            raise CannotCompile()
        if p[0] == PAN_SHIFT and p[1] not in PAN_DIRECTION:
            raise CannotCompile()
        if not 0 <= p[2] <= 255:
            raise CannotCompile()
        output = pan_bytes(p[0], p[1], p[2], p[3], p[4])
        if output is None:
            raise CannotCompile()
        return output

    if cmd.code == FADE_OUT_BGM:
        if not p or p[0] < 0:
            raise CannotCompile()
        step = fade_step(p[0])
        return bytes([OP_FADE_BGM, step & 0xFF, step >> 8])

    if cmd.code == OPEN_SAVE_MENU:
        return bytes([OP_SAVE])

    if cmd.code in (SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE):
        output = _compile_picture(cmd, pictures)
        # None is "this picture does not fit the model": it is accepted
        # without being done, which is what the three did until 2026-09-12.
        # Cutting the page would take away from the game the eight that
        # compile today because of it.
        return b"" if output is None else output

    if cmd.code in ACCEPTED_UNDONE:
        return b""     # accepted with the debt declared above

    if cmd.code == CHANGE_ENCOUNTER_STEPS:
        # The `1 / pasos` and the rows' seven thresholds, computed here as for
        # the map's registry —`rom_encounters`—, so a change of steps
        # changes the chance and the rows together, same as
        # `Encounters.set_steps`. It lasts until the next map load: the ROM
        # sets the map's again, which is what RM2k does.
        if not p:
            raise CannotCompile("ChangeEncounterSteps with no operands")
        steps = max(p[0], 0)
        thresholds = enc_step_thresholds(steps)
        if max(thresholds) > 0xFF:
            raise CannotCompile("ChangeEncounterSteps of %d steps: the thresholds "
                                "do not fit in a byte" % steps)
        base = enc_base(steps)
        return bytes([OP_ENCOUNTER_STEPS, base & 0xFF, base >> 8]
                     + thresholds + [0xFF])

    if cmd.code in (COMMENT, COMMENT_2):
        # It is not debt: in RM2k it does nothing either. Map 64's farewell
        # asked for it, whose only command that did not compile was the
        # "LYS" note the author left after the `Teleport` to the world.
        return b""

    if cmd.code == CONTROL_SWITCHES:
        if len(p) < 4 or p[0] not in (SWITCH_SINGLE, SWITCH_RANGE):
            raise CannotCompile()       # by variable: it needs variables
        if p[3] == SWITCH_TOGGLE:
            # `_compile_toggle` builds it from `compile_page`'s loop,
            # which is the one that knows `length`; here it would only arrive
            # from another path —the fused cells'—, which no toggle of the
            # game takes.
            raise CannotCompile("toggling a switch outside the page's loop")
        first, last = p[1], p[2]
        if last < first or last - first >= MAX_RANGE:
            raise CannotCompile()
        value = 1 if p[3] == SWITCH_ON else 0
        out = b""
        for number in range(first, last + 1):
            out += bytes([OP_SWITCH, number & 0xFF, number >> 8, value])
        return out

    if cmd.code == TELEPORT:
        if len(p) < 3:
            raise CannotCompile()
        dest = map_index(p[0])
        if dest is None:
            raise CannotCompile()       # the map did not get into the ROM
        if songs is not None:
            songs.dest(dest)
        return bytes([OP_TELEPORT, dest & 0xFF, dest >> 8,
                      p[1] & 0xFF, p[1] >> 8, p[2] & 0xFF, p[2] >> 8])

    if cmd.code == MEMORIZE_LOCATION:
        if len(p) < 3:
            raise CannotCompile("MemorizeLocation without its three variables")
        mode = 0
        for bit, number in zip(PLACE_REFRESHES, p[:3]):
            if write_needs_refresh(number, map_events):
                mode |= bit
        return bytes([OP_LOCATION, mode]
                     + [variable_slot(n) for n in p[:3]])

    if cmd.code == RECALL_TO_LOCATION:
        if len(p) < 3:
            raise CannotCompile("RecallToLocation without its three variables")
        return bytes([OP_LOCATION, PLACE_JUMP]
                     + [variable_slot(n) for n in p[:3]])

    if cmd.code in (MEMORIZE_BGM, PLAY_MEMORIZED_BGM):
        # Without a song registry it is accepted and not done, like
        # `PlayBGM`.
        if songs is None:
            return b""
        return bytes([OP_MEMORIZED_BGM, int(cmd.code == PLAY_MEMORIZED_BGM)])

    if cmd.code == CHANGE_PARTY_MEMBERS:
        if len(p) < 3 or p[1] != PARTY_FIXED_ID:
            raise CannotCompile()   # the id comes from a variable, and we do not read them
        if p[0] not in (PARTY_ADD, PARTY_REMOVE) or not 0 <= p[2] <= 255:
            raise CannotCompile()
        return bytes([OP_PARTY, p[0], p[2]])

    if cmd.code == PROCEED_WITH_MOVEMENT:
        return bytes([OP_WAIT_ROUTES])

    if cmd.code == HALT_ALL_MOVEMENT:
        return bytes([OP_STOP_ROUTES])

    if cmd.code == CHANGE_PBG:
        return b""      # accepted and dropped: see CHANGE_PBG

    if cmd.code == FLASH_SPRITE:
        if len(p) < 7:
            raise CannotCompile()
        if p[0] == ROUTE_HERO:
            target = 0
        elif map_events is None:
            raise CannotCompile()
        else:
            target = map_events.route_target(p[0])
            if target is None:
                raise CannotCompile()   # a vehicle, or an event that does not exist
            # **A flash on an event that shares a palette is emitted anyway.**
            # On the console the flash is a CGRAM tint —`paint_flash`
            # uploads the whole row— so two events with the same graphic
            # flash together. Until 2026-09-13 that cut the page, and the cut
            # cost **51 pages**, measured, and one of them is map 20's
            # `EV0027`: the Bum cutscene that turns on the Rat Tracks B2
            # event. Without it the player shows up invisible and the game
            # cannot continue.
            #
            # What is left is a declared divergence from RM2k, which flashes
            # the image of a single sprite, and it is in
            # `workflow/divergencias/destello-sobre-la-paleta-de-otro.md`.
        if any(not 0 <= v <= 31 for v in p[1:5]):
            raise CannotCompile()
        frames = p[5] * FRAMES_PER_TENTH
        if not 0 < frames <= 255:
            raise CannotCompile()
        out = bytes([OP_FLASH, target, p[1], p[2], p[3], p[4], frames])
        if p[6]:
            # Waiting is exactly the Wait command: `SetupWait(tenths)`, that
            # is the same tenths times FRAMES_PER_TENTH.
            out += bytes([OP_DELAY, frames & 0xFF, frames >> 8])
        return out

    if cmd.code == CONTROL_VARS:
        # `[how it is chosen, from, to, operation, operand kind, a, b]`. One
        # variable at a time and nothing else: ranges and indirect are used
        # by no page of the game. See OP_VAR.
        if len(p) < 7:
            raise CannotCompile("a ControlVars with no operands")
        if p[0] != 0:
            raise CannotCompile("ControlVars on a range or indirect")
        slot = variable_slot(p[1])
        refresh = write_needs_refresh(p[1], map_events)
        if p[3] not in (VAR_SET, VAR_ADD, VAR_SUBTRACT):
            raise CannotCompile("ControlVars operation %d" % p[3])
        operand_kind, a, b = p[4], p[5], p[6]
        if operand_kind == VAR_CONSTANT:
            if not -0x8000 <= a <= 0x7FFF:
                raise CannotCompile("constant %d that does not fit in a word" % a)
            b = 0
        elif operand_kind == VAR_VARIABLE:
            a, b = variable_slot(a), 0
        elif operand_kind == VAR_RANDOM:
            if not (0 <= a <= b <= 0x7FFF and b - a < 256):
                raise CannotCompile("random between %d and %d: the ROM divides by "
                                    "a byte" % (a, b))
        elif operand_kind == VAR_OTHER:
            if a not in (OTHER_GOLD, OTHER_TIMER):
                raise CannotCompile("ControlVars 'other' %d" % a)
            b = 0
        elif operand_kind == VAR_CHARACTER:
            # A character's cell. `a` becomes the same target byte OP_ROUTE
            # carries —0 the hero, the event's index plus one— and not the
            # RM2k id: the bytecode never sees an id again, which is what
            # `MapEvents` exists to guarantee. `b` is which coordinate.
            if b not in (CHARACTER_X, CHARACTER_Y):
                raise CannotCompile("ControlVars kind 6 with sub-operand %d"
                                    % b)
            if a == ROUTE_HERO:
                a = 0
            elif map_events is None:
                raise CannotCompile("kind 6 on an event without the map")
            else:
                a = map_events.route_target(a)
                if a is None:
                    raise CannotCompile()   # a vehicle, or an event that does not exist
        else:
            raise CannotCompile("operand of kind %d in ControlVars" % operand_kind)
        return bytes([OP_VAR, slot, p[3] | refresh, operand_kind, a & 0xFF,
                      (a >> 8) & 0xFF, b & 0xFF, b >> 8])
    if cmd.code == TIMER_OPERATION:
        # The timer. The whole operation is done —set, start and stop— and
        # the seconds can come from a variable: it is the fourth operation,
        # `TIMER_SET_VAR`, with the slot in the operand.
        if len(p) < 5:
            raise CannotCompile()
        if p[0] == TIMER_SET:
            if p[1] != TIMER_FIXED_SECONDS:
                slot = variable_slot(p[2])
                return bytes([OP_TIMER, TIMER_SET_VAR, slot, 0, 0])
            # The ROM counts the frames in sixteen bits, so the cap is not the
            # operand's but the count's. It is eighteen minutes, and the
            # game's longest timer is ten.
            if not 0 <= p[2] * FRAMES_PER_SECOND + TIMER_EXTRA_FRAMES \
                    <= 0xFFFF:
                raise CannotCompile()
            return bytes([OP_TIMER, TIMER_SET, p[2] & 0xFF, p[2] >> 8, 0])
        if p[0] in (TIMER_START, TIMER_STOP):
            # The fifth parameter is "also in battle", and here there are no
            # battles: it is compiled anyway and ignored, like the rest of
            # what belongs to combat.
            return bytes([OP_TIMER, p[0], 0, 0, 1 if p[3] else 0])
        raise CannotCompile()

    if cmd.code == MOVE_EVENT:
        if len(p) < 4:
            raise CannotCompile()
        if p[0] == ROUTE_HERO:
            target = 0
        elif map_events is None:
            raise CannotCompile()   # without the map there is no way to translate the id
        else:
            target = map_events.route_target(p[0])
            if target is None:
                raise CannotCompile()   # a vehicle, or an event that does not exist
        if not ROUTE_FREQUENCY_MIN <= p[1] <= ROUTE_FREQUENCY:
            raise CannotCompile()   # 1 does not fit in the ROM's wait byte
        commands = decode_route(list(p[4:]))
        if min_frequency(p[1], [o for o, _ in commands],
                         bool(p[2])) < ROUTE_FREQUENCY_MIN:
            raise CannotCompile()   # commands 30 and 31 would take it down to 1
        path = []
        # Whether the cursor is between a `begin_jump` and its `end_jump`.
        # Inside a jump the commands are not run: `BeginMoveRouteJump` only
        # **adds up** the `move_*`s and the turns, and 9 there would have to
        # ask about the hero in the middle of the math. No route of the game
        # does it —measured, zero—, so it is rejected instead of letting the
        # ROM walk it down a path no test exercises.
        in_jump = False
        for command, extras in commands:
            if command == ROUTE_JUMP_START:
                in_jump = True
            elif command == ROUTE_JUMP_END:
                in_jump = False
            elif command == ROUTE_TOWARD_HERO and in_jump:
                raise CannotCompile()

            if command == ROUTE_SOUND:
                # See ROUTE_SOUND. Without a song registry, or "(OFF)", it is
                # dropped as before.
                if in_jump or songs is None or extras[0] in ("", "(OFF)"):
                    continue
                k = sound_index(songs, map_index, *extras,
                                from_route=True)
                path += [command, k & 0xFF, k >> 8]
                continue
            if command in ROUTE_TRANSPARENCY:
                # Accepted and dropped: it does not show and costs no frames.
                # See ROUTE_TRANSPARENCY.
                continue
            # Turning, waiting and moving. The `move_*`s came in on
            # 2026-09-03, and they are looked at *during* the walk and not
            # only at the end: `path` tests it, comparing four frames of a
            # twelve-cell route with waits in the middle. What goes in from
            # `rpg::MoveCommand::Code` is `ROUTE_COMMANDS`, and moving toward
            # the hero is in since 2026-09-12 —see ROUTE_TOWARD_HERO—; moving
            # away from him, turning in place and the switches are still out.
            if command not in ROUTE_COMMANDS:
                raise CannotCompile()
            if command in (ROUTE_FACE_HERO, ROUTE_TOWARD_HERO) and target == 0:
                raise CannotCompile()   # the hero facing or moving toward itself
            if command in ROUTE_HERO_OUTSIDE and target == 0:
                # Locking and unlocking the facing on **the hero**: accepted
                # and dropped, like the sound and the transparency. On events
                # they are done. Raising and lowering the speed were also
                # dropped on the hero, and they are done since 2026-09-10:
                # see ROUTE_HERO_OUTSIDE.
                #
                # Dropping them and not rejecting the whole page, which was
                # the first thing tried, is from 2026-09-06: **Talan's scene
                # has a hero route that starts with 28**, so the scene that
                # motivated that day's six points did not compile and the
                # player could not leave the Emitter Room corridor.
                continue
            if command in ROUTE_DIAGONALS and target == 0:
                # And the hero diagonally: the ROM does not know how to do it
                # and none of the game's 26 routes with diagonals is the
                # hero's. Without this cut the ROM would go left —the `mover`
                # of `step_route` falls into `try_left` by elimination—.
                raise CannotCompile()
            if command == ROUTE_CHANGE_GRAPHIC:
                # The only command with an operand: after 34 goes the
                # graphic's index in `Graphics`, which the converter resolves
                # to the map's sprite bank. Whoever walks an already compiled
                # route has to skip that byte: read as a command, a 30 or a
                # 31 change the route's frequency without anyone asking.
                #
                # **On the hero too**, since 2026-09-12. Its graphic comes
                # from the actor table, but the actor's twelve poses are
                # written with the same shape as an `npc_poses` entry, so the
                # ROM changes the pointer and that is it: see `graphic_hero`
                # in tools/runtime/ruta_del_heroe.s. They are +29 pages of the
                # game, and among them the three of map 8's `EV0047`, which
                # could not be interacted with.
                if graphics is None or len(extras) < 2:
                    raise CannotCompile()
                chosen = graphics.index(extras[0], extras[1])
                if chosen > 0xFF:
                    raise CannotCompile()
                path.append(command)
                path.append(chosen)
                continue
            path.append(command)
        if len(path) > 255:
            raise CannotCompile()
        if not path:
            # A route left without commands —only sound or transparency,
            # like those of map 2's screens— is not emitted: in RM2k
            # `UpdateMoveRoute` consumes it whole on the same frame and
            # considers it finished, so it neither costs frames nor leaves
            # anything to wait for in `ProceedWithMovement`.
            return b""
        return bytes([OP_ROUTE, target, p[1], len(path)]) + bytes(path)

    if cmd.code == CHANGE_EVENT_LOCATION:
        if len(p) < 4 or p[1] not in (PLACE_CONSTANT, PLACE_BY_VARIABLE):
            raise CannotCompile()
        if p[0] == ROUTE_HERO or map_events is None:
            # Nobody moves the hero this way in this game —that is what
            # Teleport is for— and without the map there is no way to
            # translate the id.
            raise CannotCompile()
        target = map_events.route_target(p[0])
        if target is None:
            raise CannotCompile()   # a vehicle, or an event that does not exist
        if p[1] == PLACE_BY_VARIABLE:
            # The cell comes from two variables, and they are read **when it
            # runs**: it is `CommandChangeEventLocation`'s
            # `Main_Data::game_variables->Get(x)`. It goes in a separate
            # opcode and not in a bit of `OP_PLACE` because the operands are
            # different —two one-byte slots against two words— and a
            # variable-length opcode is what the walk over the bytecode does
            # not know how to do: `OPCODE_SIZE` is a table.
            return bytes([OP_PLACE_VAR, target, variable_slot(p[2]),
                          variable_slot(p[3])])
        if not (0 <= p[2] <= 0xFFFF and 0 <= p[3] <= 0xFFFF):
            raise CannotCompile()
        return bytes([OP_PLACE, target, p[2] & 0xFF, p[2] >> 8,
                      p[3] & 0xFF, p[3] >> 8])

    if cmd.code == TILE_SUBSTITUTION:
        # `[upper layer?, old tile, new tile]`, with the tiles numbered from
        # the first of their layer, which is how `DoSubstitute` numbers
        # them.
        if len(p) < 3:
            raise CannotCompile("TileSubstitution with no operands")
        if map_events is None or map_events.substitutions is None:
            # Without the converter in between there are no blocks to
            # translate against. See `Substitutions` in snes_convert.py.
            raise CannotCompile("TileSubstitution without the map's blocks")
        pairs = map_events.substitutions.pairs(bool(p[0]), p[1], p[2])
        if pairs is None:
            raise CannotCompile("TileSubstitution that cannot be translated to "
                                "blocks: see `Substitutions`")
        if not pairs:
            # No cell of the map draws the old tile, so there is nothing to
            # change. In RM2k the substitution is still recorded, but nobody
            # looks at what it records: there is no cell that can use it.
            return b""
        out = bytearray([OP_TILE_SUB, len(pairs)])
        for old, new in pairs:
            out += bytes([old & 0xFF, old >> 8, new & 0xFF, new >> 8])
        return bytes(out)

    if cmd.code == STORE_TERRAIN_ID:
        # `[mode, x, y, variable]`, with `ValueOrVariable`: in mode 0 the cell
        # comes written and in mode 1 the two numbers are variable ids. Both
        # are resolved **when it runs**, so both go in the same opcode with
        # the mode set: reading them here in mode 1 would answer with what
        # the variables were worth at compile time.
        if len(p) < 4 or p[0] not in (0, 1):
            raise CannotCompile("StoreTerrainID with a mode that is neither 0 nor 1")
        dest = variable_slot(p[3])
        if p[0]:
            x, y = variable_slot(p[1]), variable_slot(p[2])
        else:
            if not (0 <= p[1] <= 0xFFFF and 0 <= p[2] <= 0xFFFF):
                raise CannotCompile("StoreTerrainID outside the 16 bits")
            x, y = p[1], p[2]
        mode = p[0] | write_needs_refresh(p[3], map_events)
        return bytes([OP_TERRAIN, mode, x & 0xFF, x >> 8, y & 0xFF, y >> 8,
                      dest])

    if cmd.code == SHOW_HIDDEN_MONSTER:
        # It only arrives from a troop page: see `TROOP_COMMANDS`. A place
        # the troop does not have does nothing in easyrpg —`GetEnemy` gives
        # null—, and the ROM checks it against `BA_KID`.
        if len(p) < 1 or not 0 <= p[0] < 256:
            raise CannotCompile("ShowHiddenMonster without a place")
        return bytes([OP_SHOW_ENEMY, p[0]])

    if cmd.code == SHAKE_SCREEN:
        # `CommandShakeScreen`, in its RM2k form: power, speed, tenths and
        # whether it waits. The game's 29 are of that form. With zero tenths
        # it is `ShakeEnd` and never waits.
        if len(p) < 4 or not 0 <= p[0] <= 9 or not 0 <= p[1] <= 9:
            raise CannotCompile()
        frames = p[2] * FRAMES_PER_TENTH
        if frames > 0xFFFF:
            raise CannotCompile()
        out = bytes([OP_SHAKE, p[0], p[1], frames & 0xFF, frames >> 8])
        if frames and p[3]:
            out += bytes([OP_DELAY, frames & 0xFF, frames >> 8])
        return out

    if cmd.code == SHOW_BATTLE_ANIMATION:
        # (animation, target, wait, global): see OP_ANIMATION.
        if len(p) < 3:
            raise CannotCompile()
        anim = ANIMATIONS.get(p[0])
        if p[1] == ROUTE_HERO:
            target, who = 0, None
        elif map_events is None:
            target, who = None, None
        else:
            target = map_events.route_target(p[1])
            who = (map_events.owner if p[1] == ROUTE_THIS_EVENT else p[1])
        if anim is None or target is None:
            return b""      # without an animation or a target RM2k does nothing
        # The target's flash is a tint of its palette on the console, and two
        # events with the same graphic share it: see FLASH_SPRITE. Here the
        # page is not cut for that: that flash is not done. **The hero is
        # never flashed**: whom he shares a palette with depends on the
        # party, which the compiler does not see —the converter looks at it
        # for the `FlashSprite`s and cuts the whole ROM—, and an animation is
        # not worth that.
        flashes = (target != 0
                   and not map_events.shares_graphic(who))
        entries = []
        for t in anim["timings"]:
            tick = (t["frame"] - 1) * 2
            if not 0 <= tick <= 255:
                continue
            name, volume, tempo, balance = t["se"]
            if name and name != "(OFF)" and songs is not None:
                k = songs.sound(name, volume, tempo, balance)
                entries.append(bytes([tick, ANIM_SOUND, k & 0xFF, k >> 8,
                                      0, 0, 0, 0]))
            r, g, b = (min(31, max(0, v)) for v in t["rgb"])
            strength = min(7 * max(0, t["fuerza"]) // 6, 31)
            if t["alcance"] == 2:
                entries.append(bytes([tick, ANIM_SCREEN_FLASH, r, g, b, strength,
                                      ANIM_FLASH_FRAMES, 0]))
            elif t["alcance"] == 1 and flashes:
                entries.append(bytes([tick, ANIM_FLASH, target, r, g, b,
                                      strength, ANIM_FLASH_FRAMES]))
        entries.sort(key=lambda e: e[0])   # stable: the LDB's order
        if len(entries) > 255:
            raise CannotCompile()
        # A `global` one —the one RM2k repeats three by three to cover the
        # screen— is accepted and not drawn: it is still heard and still
        # flashes, which is what it already did. None of the intro's eleven
        # asks for it.
        number = (p[0] if p[0] <= 255 and not (len(p) > 3 and p[3])
                  else ANIM_NO_DRAWING)
        out = (bytes([OP_ANIMATION, number, drawing_target(anim, target),
                      len(entries)])
               + b"".join(entries))
        frames = 2 * len(anim["cuadros"])
        if p[2] and frames:
            out += bytes([OP_DELAY, frames & 0xFF, frames >> 8])
        return out

    if cmd.code == FLASH_SCREEN:
        # `CommandFlashScreen`, in its RM2k form: color, power, tenths and
        # whether it waits. The game's 62 are of that form, and none lasts
        # more than twenty tenths: the frames byte is enough, and the ROM
        # divides the level by what is left with the hardware's eight-bit
        # divider.
        if len(p) < 6 or any(not 0 <= v <= 31 for v in p[:4]):
            raise CannotCompile()
        frames = p[4] * FRAMES_PER_TENTH
        if frames > 0xFF:
            raise CannotCompile()
        out = bytes([OP_FLASH_SCREEN, p[0], p[1], p[2], p[3], frames])
        if frames and p[5]:
            out += bytes([OP_DELAY, frames & 0xFF, frames >> 8])
        return out

    if cmd.code == TRADE_EVENT_LOCATIONS:
        # `CommandTradeEventLocations`: each one goes with `MoveTo` to the
        # other's cell. No page of the game uses it on the hero.
        if len(p) < 2 or map_events is None:
            raise CannotCompile()
        targets = [map_events.route_target(q) for q in p[:2]]
        if any(b is None or b == 0 for b in targets):
            raise CannotCompile()   # the hero, a vehicle or an event that does not exist
        return bytes([OP_SWAP] + targets)

    if cmd.code == WAIT:
        if len(p) < 1:
            raise CannotCompile()
        frames = p[0] * FRAMES_PER_TENTH
        if frames > 0xFFFF:
            raise CannotCompile()
        return bytes([OP_DELAY, frames & 0xFF, frames >> 8])

    if cmd.code == TINT_SCREEN:
        if len(p) < 4:
            raise CannotCompile()
        if any(not 0 <= v <= 200 for v in p[:4]):
            raise CannotCompile()
        # The duration is discarded: the tint is applied at once. The screen
        # being compared is always settled, so the final value is the one
        # that matters; what is lost is the one-second gradient.
        return bytes([OP_TINT, p[0], p[1], p[2], p[3]])

    if cmd.code == SHOW_MESSAGE:
        if messages is None:
            raise CannotCompile()   # this ROM carries no window: nowhere to put it
        lines = [cmd.string] + list(extra)
        # `Messages.add` removes the escape tail, since every box goes
        # through it; anything that is not `\|` or `\^` still cuts the page
        # from there. See `escape_tail`.
        where = messages.add(lines)
        return bytes([OP_MESSAGE, where & 0xFF, where >> 8])

    raise CannotCompile()


class PartyState:
    """The party, to simulate its changes when converting:
    `possible_leaders` and `page_party` in snes_convert.py. It is
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
# `tools/protocol/events.toml`. They used to be written by hand, and there
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


def page_debts(page, pictures=None):
    """Which commands of this page are accepted without being done.

    So the converter can warn instead of the debt going silent.

    The three `Picture` ones are debt only **if this page is not the one of
    the picture the ROM does draw**: warning anyway would be the warning
    nobody reads, which is how a real debt gets lost among the ones that no
    longer are.
    """
    output = set()
    for cmd in page.commands:
        if cmd.code not in ACCEPTED_UNDONE:
            continue
        if (cmd.code in (SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE)
                and _compile_picture(cmd, pictures) is not None):
            continue
        output.add(cmd.code)
    return sorted(output)


def map_pages(game_map, map_index, messages=None, songs=None,
              graphics=None, pictures=None, troops=None):
    """The pages the ROM needs to resolve the map's events.

    *All* the pages of an event that has some triggerable one are emitted,
    not only those: which one stays active depends on the conditions of all
    of them, and a later page that triggers nothing still wins and keeps the
    one below from running.
    """
    output = []
    map_events = MapEvents(game_map)
    chipset = getattr(game_map, "chipset_filename", None)
    for event_number, event in enumerate(game_map.events):
        # **All** events go, whether or not they have a page that triggers
        # something: since 2026-09-05 the table also says which layer the
        # active page is on, which is what decides whether the event blocks
        # the hero's way —or another event's—, and any event does that, even
        # one that runs nothing. Before, only the ones with code were stored,
        # and a droid without a compilable page —the battle one— would not
        # have stopped anyone.
        #
        # If some page of the event asks for a condition the ROM does not
        # know how to evaluate —a variable, a timer— then it is not known
        # which page is active, and running the wrong one is worse than
        # running none. The whole event is left out, and it does not block
        # either: its layer is as unknown as its code. The **item** condition
        # is something else: it is known that it is never met, and the page
        # is emitted as such.
        if not rm2k.supported_conditions(event):
            continue

        party = []
        for page_number, page in enumerate(event.pages):
            cond = page.condition
            code = None
            if rm2k.impossible_page(page):
                # Never active: no code, no graphic, and with the switch that
                # never turns on. The pages below keep winning when their turn
                # comes, which is what RM2k does while the item is not there.
                party.append({
                    "evento": event_number, "pagina": page_number,
                    "trigger": page.trigger,
                    "switch_a": SWITCH_IMPOSSIBLE, "switch_b": 0, "actor": 0,
                    "variable": None, "item": 0,
                    "capa": page.layer, "frecuencia": page.move_frequency,
                    "velocidad": page.move_speed, "codigo": None,
                    "ruta_propia": None, "grafico": None, "tile_pasa": None,
                    "gira": False,
                })
                continue
            graphic = rm2k.page_graphic(page, chipset)
            # **An automatic or parallel page without a single command starts
            # nothing.** It is `Game_Interpreter::Push`, which returns right
            # away with an empty list: the interpreter does not keep running
            # and the player walks. Here, instead, the empty page became the
            # active one, ran in one tick, ended, and since an automatic page
            # repeats while it stays active, it started again: the map stayed
            # frozen forever and the hero did not take a step.
            #
            # It is the idiom with which RM2k deactivates an event —a page
            # below turns on the switch that activates one above, and that one
            # is empty—, so it is not a rare case: in Rat Tracks B1 there are
            # two, and the map was unplayable.
            #
            # It is turned off by setting its code to None, which is what the
            # converter already looks at to decide whether an automatic page
            # counts: the page's bit 7.
            empty = not page.commands and page.trigger in (TRIGGER_AUTOSTART,
                                                           TRIGGER_PARALLEL)
            if page.trigger in TRIGGERS and can_trigger(page) and not empty:
                code = compile_page(page, map_index, messages,
                                    map_events.for_event(event.id), songs,
                                    graphics, pictures, troops)
                # **And the same with one that compiles to nothing**: all it
                # had were calls that got skipped —see `_compile_call`—.
                # In RM2k it is not empty, and what it calls is what turns it
                # off; here it would be the empty page above, with the map
                # frozen. It is `AfterBattleMint` on the maps with encounters:
                # with switch 498, which turns on each troop's turn 0 page, it
                # calls common event 35, `ResetAfterBattles`, which does not
                # compile and is the one that turns 498 off. Without this, the
                # first battle on those maps left the hero unable to take a
                # step.
                if code == bytes([OP_DONE]) and page.trigger in (
                        TRIGGER_AUTOSTART, TRIGGER_PARALLEL):
                    code = None
            party.append({
                "evento": event_number,
                "pagina": page_number,
                "trigger": page.trigger,
                "switch_a": cond.ids["switch_a"] if "switch_a" in cond.active else 0,
                "switch_b": cond.ids["switch_b"] if "switch_b" in cond.active else 0,
                "actor": cond.ids["actor"] if "actor" in cond.active else 0,
                "variable": ((variable_slot(cond.ids["variable"]),
                              cond.operator, cond.variable_value)
                             if "variable" in cond.active else None),
                "item": cond.ids["item"] if "item" in cond.active else 0,
                "capa": page.layer,
                "frecuencia": page.move_frequency,
                "velocidad": page.move_speed,
                "codigo": code,
                "ruta_propia": own_route(page),
                # What the page draws and what its tile imposes on the cell:
                # see `rm2k.collect_npcs`, and `pass_with_event` in
                # tools/runtime/heroe.s, which is the one that applies them.
                "grafico": graphic,
                "tile_pasa": (rm2k.event_tile_passability(game_map, graphic[0],
                                                          page.layer)
                              if graphic is not None else None),
                # Whether the event turns around toward the hero with this
                # page: a CharSet —a chipset tile has nowhere to look— and an
                # animation type that does not fix the direction. See TURN.
                "gira": bool(page.character_name)
                        and page.animation_type not in ANIM_FIXED,
            })
        output += party
    return output


# The page's animation types, `rpg::EventPage::AnimType`.
ANIM_NOT_CONTINUOUS, ANIM_CONTINUOUS_KIND, ANIM_FIXED_NOT_CONTINUOUS = 0, 1, 2
ANIM_FIXED_CONTINUOUS, ANIM_FIXED_GRAPHIC, ANIM_TURN = 3, 4, 5


def own_route(page):
    """The page's own route —`move_type` 6, the route it walks on its own—,
    or None if it has none or it cannot be done.

    The same commands as in a MoveEvent go, with the transparency dropped and
    also the sound, which in a MoveEvent does play: here there is nowhere to
    put its operand —see ROUTE_SOUND—. The diagonals go in: an own route is
    always an event's, which is what the ROM walks them on. What is left
    out: moving toward or away from the hero, changing the graphic —none uses
    it— and the switches; and turning in place (`AnimType_spin`), which
    neither of the game's two pages that use it is in the first maps. The
    other movement types —random, vertical, horizontal, toward the hero—
    neither: they are another machine.

    **Moving toward the hero is left out here too**, even though since
    2026-09-12 the ROM walks it in a forced route: they are two pages of map
    105 —measured, the only ones of the game's 37 own routes that use it—
    and no test gets there, so accepting it would be opening the path with
    nothing exercising it. 21 is out for the same reason since before: zero
    own routes use it.
    """
    if page.move_type != 6 or not page.move_route.commands:
        return None
    if not ROUTE_FREQUENCY_MIN <= page.move_frequency <= ROUTE_FREQUENCY:
        return None
    if not 1 <= page.move_speed <= 6 or page.animation_type == ANIM_TURN:
        return None
    commands = []
    for command in page.move_route.commands:
        if command == ROUTE_SOUND or command in ROUTE_TRANSPARENCY:
            continue
        if command not in ROUTE_COMMANDS or command in (ROUTE_FACE_HERO,
                                                        ROUTE_TOWARD_HERO):
            return None
        if command == ROUTE_CHANGE_GRAPHIC:
            # Here there is nowhere to put the operand —a page's route is a
            # bare list of codes, not a MoveEvent with its text— and it is not
            # needed: **none of the game's 3509 own routes changes graphic**,
            # measured. The day one shows up, this rejects it instead of
            # compiling a 34 with nothing to change to.
            return None
        commands.append(command)
    if min_frequency(page.move_frequency, commands,
                     page.move_route.repeat) < ROUTE_FREQUENCY_MIN:
        return None             # commands 30 and 31 would take it down to 1
    if not commands or len(commands) > 255:
        return None
    return {
        "ordenes": commands,
        "frecuencia": page.move_frequency,
        "velocidad": page.move_speed,
        "repite": page.move_route.repeat,
        "saltable": page.move_route.skippable,
        "dir_fija": page.animation_type in (ANIM_FIXED_NOT_CONTINUOUS,
                                           ANIM_FIXED_CONTINUOUS,
                                           ANIM_FIXED_GRAPHIC),
        "anim_continues": page.animation_type in (ANIM_CONTINUOUS_KIND,
                                                ANIM_FIXED_CONTINUOUS),
    }
