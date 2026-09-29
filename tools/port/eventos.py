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

from port import imagen as imagen_mod
from port import reglas
from port.constantes import COLUMNAS, LINEAS, RANURAS_EQUIPO
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
# `Sustituciones`.
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
PAN_FIJAR, PAN_SOLTAR, PAN_CORRER, PAN_VOLVER = 0, 1, 2, 3
# The camera's units inside RM2k: `SCREEN_TILE_SIZE`, that is 1/16 of a
# pixel, with a 16-pixel cell worth 256. Keeping them is not a whim: speed 2
# moves the camera **half a pixel per frame**, and in whole pixels that cannot
# be counted.
PAN_UNIDAD = 256
PAN_ARRIBA, PAN_DERECHA, PAN_ABAJO, PAN_IZQUIERDA = 0, 1, 2, 3
# Which way the camera moves for each direction, in (dx, dy) per unit.
PAN_SENTIDO = {PAN_ARRIBA: (0, -1), PAN_DERECHA: (1, 0),
               PAN_ABAJO: (0, 1), PAN_IZQUIERDA: (-1, 0)}
PAN_VEL_MIN, PAN_VEL_MAX = 1, 6


def bytes_de_pan(operacion, direccion, distancia, velocidad, esperar):
    """The OP_PAN of a `PanScreen`, or None if it cannot be done.

    The direction and the distance are resolved here to a signed offset in
    1/16 of a pixel, and the speed to its step per frame: they are fixed
    computations and the ROM has no reason to repeat them. What is left to
    the console are the frames the page waits.
    """
    dx, dy = (0, 0) if operacion == PAN_VOLVER else PAN_SENTIDO[direccion]
    dx *= distancia * PAN_UNIDAD
    dy *= distancia * PAN_UNIDAD
    if not (-0x8000 <= dx < 0x8000 and -0x8000 <= dy < 0x8000):
        return None
    return bytes([OP_PAN, operacion,
                  dx & 0xFF, (dx >> 8) & 0xFF,
                  dy & 0xFF, (dy >> 8) & 0xFF,
                  paso_de_pan(velocidad), 1 if esperar else 0])


def paso_de_pan(velocidad):
    """How far the camera moves per frame, in 1/16 of a pixel.

    It is `data()->pan_speed = 2 << speed` from `Game_Player::StartPan`, with
    the speed clamped between 1 and 6 as `CommandPanScreen` does. The game
    uses 2 to 6: from half a pixel per frame to eight.
    """
    return 2 << min(PAN_VEL_MAX, max(PAN_VEL_MIN, velocidad))


LUGAR_CONSTANTE = 0         # p[1]: 0 is the written cell, 1 reads it from variables
LUGAR_POR_VARIABLE = 1      # and there is no third: `CommandChangeEventLocation`
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
# —see `mensaje_bytes`— and the ROM's interpreter and the one below read them
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
ESCAPE_PAUSA = "|"
ESCAPE_CERRAR = "^"

# What a `\|` costs. **It is not one second**: it is the
# `SetWaitForNonPrintable(61)` of `window_message.cpp`, with its comment next to
# it —"Despite documentation saying 1 second, RPG_RT waits for 61 frames"—. It
# is 61 and not 60, and that difference is exactly the kind of number that
# cannot be written from memory.
CUADROS_DE_PAUSA = 61

# How many pauses fit in the box's header. The most the game uses is three in a
# row (`\|\|\|\^`, twice, on map 108); more than fifteen does not fit in the
# high nibble and the page does not compile instead of lasting too little.
PAUSAS_MAX = 15


def cola_de_escapes(lineas):
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
    lineas = list(lineas)
    pausas = 0
    autocierre = False
    if lineas:
        texto = lineas[-1]
        i = corte = len(texto)
        escapes = 0
        while i > 0:
            if i >= 2 and texto[i - 2] == ESCAPE \
                    and texto[i - 1] in (ESCAPE_PAUSA, ESCAPE_CERRAR):
                i -= 2
                corte = i
                escapes += 1
            elif texto[i - 1] == " ":
                i -= 1
            else:
                break
        if escapes:
            cola = texto[corte:]
            pausas = cola.count(ESCAPE + ESCAPE_PAUSA)
            autocierre = ESCAPE + ESCAPE_CERRAR in cola
            lineas[-1] = texto[:corte]
    if any(ESCAPE in t for t in lineas) or pausas > PAUSAS_MAX:
        raise NoSePuede()
    return tuple(lineas), pausas, autocierre


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
RUTA_HEROE = 10001
RUTA_ESTE_EVENTO = 10005                    # "this event", the page's owner
# 10002 to 10004 are the vehicles —boat, ship, airship—, which do not exist here.
RUTA_MIRAR = {12: 0, 13: 1, 14: 2, 15: 3}   # face_up/right/down/left
RUTA_MOVER = {n: n for n in range(8)}      # the four move_* and the
                                           # four diagonals: the command's
                                           # code **is** the direction. See
                                           # RUTA_DIAGONALES
RUTA_ESPERAR = 23

# What a `wait` inside a forced route costs. **It is not one frame**: in RM2k
# it is `SetMaxStopCountForWait`, which gives `20 + (1 << (8 - frecuencia))`,
# and with frequency 8 —the only one this repo accepts, see `RUTA_FRECUENCIA`—
# that is twenty.
CUADROS_DE_ESPERA_DE_RUTA = 20

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
RUTA_FRECUENCIA = 8
RUTA_FRECUENCIA_MIN = 2


def frecuencia_minima(frecuencia, ordenes, repite=False):
    """The lowest frequency a route with commands 30 and 31 goes through.

    It is what decides whether the route can be compiled: with frequency 1
    the wait after a step is 256 frames and the `ruta_tras_paso` byte cannot
    hold it, so a route that goes down that far is rejected whole.

    `ordenes` are bare codes, without operands: the two callers pass what
    `decodificar_ruta` returned, which already separated them. It is not the
    same as a compiled route, where 34 drags a byte along that has to be
    skipped.

    With `repite` the commands are walked nine times and not once. It is not
    just in case: the frequency is clamped at 8 and at 1, so a repeating
    route that goes down more than it goes up ends at 1 no matter what, and
    nine passes are enough for it to get there from any starting point.
    """
    actual = minima = frecuencia
    for _ in range(9 if repite else 1):
        for orden in ordenes:
            if orden == RUTA_FREC_MAS:
                actual = min(RUTA_FRECUENCIA, actual + 1)
            elif orden == RUTA_FREC_MENOS:
                actual = max(1, actual - 1)
            minima = min(minima, actual)
    return minima


def espera_tras_paso(frecuencia):
    """`GetMaxStopCountForStep`: the frames standing still after a step."""
    return 0 if frecuencia >= 8 else 1 << (9 - frecuencia)


def espera_tras_giro(frecuencia):
    """`GetMaxStopCountForTurn`: the frames standing still after a turn. The
    `wait` is `CUADROS_DE_ESPERA_DE_RUTA` plus this."""
    return 0 if frecuencia >= 8 else 1 << (8 - frecuencia)


# Facing the hero: `GetDirectionToCharacter`. The axis with more distance
# wins, and on a tie the vertical one; on the same cell it looks down. Only on
# events: no page uses the hero facing itself.
RUTA_ENCARAR_HEROE = 21

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
RUTA_HACIA_HEROE = 9

# Turning without moving —`turn_90_degree_right` and its siblings— is still
# out, and not because of cost: RM2k turns relative to the direction the
# character already had, and for an event that has not turned yet that is its
# page's, which the route does not read.

# The jump: what lies between the two is added up as an offset and the
# character does it in one go, in an arc.
RUTA_SALTO_INICIO, RUTA_SALTO_FIN = 24, 25

# Walking through walls, and stopping or resuming the walking animation.
RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF = 36, 37
RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR = 38, 39
# Locking and unlocking the facing —`lock_facing`—, and raising and lowering
# the speed by one, between 1 and 6. They came in on 2026-09-05 with the
# pages' own routes: map 2's droids use them.
RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR = 26, 27
RUTA_VEL_MAS, RUTA_VEL_MENOS = 28, 29
# The four above, **on the hero**, are not compiled: see `traducir`. On the
# hero, locking and unlocking the facing are dropped; raising and lowering the
# speed **are done** since 2026-09-10 —the Tram Officer asks for it, and 170
# routes in the game— and they stay: RM2k restores the frequency when the
# route ends and not the speed, so the pad walks afterwards at the speed the
# route left.
RUTA_HEROE_AFUERA = {RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR}
# Raising and lowering the frequency in the middle of a route:
# `increase/decrease_movement_frequence`, which RM2k clamps at 8 and 1. **A
# single route in the whole game** uses them —the one that shakes Manta in the
# Emitter Room scene, which goes down twice from 8 to 6— and without them that
# page does not compile.
RUTA_FREC_MAS, RUTA_FREC_MENOS = 30, 31
# Changing the graphic in the middle of a route. It is the **only command with
# an operand**: the bytecode carries after it the CharSet's index in
# `Graficos`. Only on events; on the hero it is not compiled, see `traducir`.
RUTA_CAMBIAR_GRAFICO = 34

# How far a step advances per frame by speed, out of 256 per cell: it is the
# `1 << (1 + GetMoveSpeed())` of `Game_Character::UpdateMovement`. 4 is the
# hero's, 32 per frame, that is two pixels and eight frames per cell; 3 is
# sixteen frames and 2 thirty-two, at half a pixel per frame.
PASO_POR_VELOCIDAD = (4, 8, 16, 32, 64, 128)

# A jump lasts as long as `remaining_step` takes to go from 256 to 0 at
# `jump_speed[move_speed - 1]` per frame. At speed 4 —the hero's at the
# start— that is 24 per frame, that is eleven frames, and **it does not
# depend on the distance**: jumping five cells costs the same as jumping in
# place. The ROM has the same table in `salto_por_vel`; this is the one the
# tests look at.
SALTO_PASO = 256
SALTO_POR_VELOCIDAD = (8, 12, 16, 24, 32, 64)

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
RUTA_DIAGONALES = {4: (0, 1), 5: (2, 1), 6: (2, 3), 7: (0, 3)}


# The move commands we know how to walk, in a single place.
RUTA_ORDENES = (set(RUTA_MIRAR) | set(RUTA_MOVER)
                | {RUTA_ESPERAR, RUTA_SALTO_INICIO, RUTA_SALTO_FIN,
                   RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF,
                   RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR, RUTA_ENCARAR_HEROE,
                   RUTA_HACIA_HEROE,
                   RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR, RUTA_VEL_MAS, RUTA_VEL_MENOS,
                   RUTA_FREC_MAS, RUTA_FREC_MENOS, RUTA_CAMBIAR_GRAFICO})


# The commands that carry something after them, and what. The numbers are
# those of `rpg::MoveCommand::Code` in liblcf.
RUTA_SWITCH_ON, RUTA_SWITCH_OFF = 32, 33
# RUTA_CAMBIAR_GRAFICO, 34, is further up: `RUTA_ORDENES` needs it.
# Raising and lowering the transparency by an eighth. They are accepted and
# dropped, like the sound: the SNES does not fade a sprite in steps without
# color math, and the game's eight routes that use it —map 2's four screens,
# which fade while Manta hacks— are a decorative fade inside a 78-command
# scene that did not compile without this. They cost no frames: in
# `UpdateMoveRoute` they go through the branch that does not touch the stop
# counter.
RUTA_TRANSPARENCIA = (40, 41)
# The sound inside the route: it plays when the route reaches that step, since
# 2026-09-27. In a MoveEvent it goes with two bytes after it, the effect's
# index in `Temas.sonidos` —the same one OP_SOUND carries—, so the effect goes
# into the map's audio package like that of a `PlaySound`. It costs no frame:
# `UpdateMoveRoute` does not touch its stop counter.
#
# It is still dropped in two places. **Inside a jump**, because RM2k does not
# touch it there: `BeginMoveRouteJump` walks up to the `end_jump` adding up the
# steps and runs nothing else. And **in a page's own route**, which is a bare
# list of codes with no room for the operand —see `ruta_propia`—: a single
# one in the game asks for it, that of event 40 on map 2.
RUTA_SONIDO = 35


def decodificar_ruta(parametros):
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
    ordenes = []
    i = 0
    n = len(parametros)

    def entero():
        nonlocal i
        valor = 0
        while True:
            if i >= n:
                raise NoSePuede()
            x = parametros[i]
            i += 1
            valor = (valor << 7) | (x & 0x7F)
            if not x & 0x80:
                return valor

    def texto():
        nonlocal i
        largo = entero()
        if i + largo > n:
            raise NoSePuede()
        letras = "".join(chr(c & 0xFF) for c in parametros[i:i + largo])
        i += largo
        return letras

    while i < n:
        codigo = parametros[i]
        i += 1
        if codigo in (RUTA_SWITCH_ON, RUTA_SWITCH_OFF):
            extras = [entero()]
        elif codigo == RUTA_CAMBIAR_GRAFICO:
            extras = [texto(), entero()]
        elif codigo == RUTA_SONIDO:
            extras = [texto(), entero(), entero(), entero()]
        else:
            extras = []
        ordenes.append((codigo, extras))
    return ordenes

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
GRUPO_AGREGAR, GRUPO_SACAR = 0, 1
GRUPO_ID_FIJO = 0
GRUPO_MAX = 4           # `Game_Party::AddActor` does not add if there are four

# Commands accepted while doing nothing, because doing nothing does not show.
# It is the same criterion as the doors', and it has to be applied with the
# same distrust: if the command changes something we do draw, it does not go
# here.
MESSAGE_OPTIONS = 10120

IGNORABLES = {
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
# its pages can turn on —`paquete_cargar`, in tools/runtime/paquete_de_audio.s—,
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
# together with its songs —`paquete_cargar`, in
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
# other that fits the same mold. See `Imagenes`, OP_PICTURE and
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
# compiled alone: see `_compilar_posada`.
SHOW_INN = 10730
INN_STAY, INN_NO_STAY, INN_END = 20730, 20731, 20732

# `ChangeSystemBGM` (10660): changes the song the system uses for fighting,
# for winning, for the inn. The game uses it **130 times on 25 maps** and
# always in pairs —0 and 1, that is `battle_music` and `battle_end_music`—:
# each zone has its battle music.
#
# It is accepted without being done, and the debt is concrete: **a battle on
# those maps plays the LDB's song instead of the zone's**. It is not "it does
# not sound": what sounds is the one `AUDIO_BATALLA` brings from the database,
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
# `encuentro_pasos`.
CHANGE_ENCOUNTER_STEPS = 11740

ACEPTADOS_SIN_HACER = {
    # CallEvent **is no longer here**: since 2026-09-12 it is compiled
    # inline, see `_compilar_llamada`. What is left of that is that a call
    # whose target does not compile is skipped just like before, and that is
    # decided in there and not in this list: the command itself is no longer
    # a whole debt.
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
    CHANGE_SYSTEM_BGM,
    CHANGE_HERO_TITLE,
}


class Temas:
    """The songs the game's `PlayBGM`s ask for, numbered in the order they
    appear.

    It is the sibling of `Mensajes`: the bytecode carries an index and not a
    name, and the converter is the one that resolves the index. The ROM
    carries **the first `TEMA_TOTAL`**, which are the ones that fit in ARAM:
    all of them share the samples and the shared bank lives in the SPC700's
    64 KB, which are uploaded only once at boot. A higher index is a song
    that did not fit and does not sound.

    Numbering all of them and not only the ones that fit is what keeps the
    bytecode from depending on which were chosen. Until 2026-09-06 only one
    fit and this was already written this way; the day four fit nothing
    different had to be recompiled.
    """

    def __init__(self):
        self.nombres = []
        # And the `PlaySound` effects, the same way: each combination of
        # effect, volume, tempo and pan is an entry, and the bytecode carries
        # its index. They live here and not apart because this is what the
        # converter already passes from compilation to compilation.
        self.sonidos = []
        # And who asks for what: the converter puts in `mapa` the index of the
        # map it is compiling, and each song and each effect is noted in its
        # own, in the order they appear. It is what builds each map's audio
        # package: see `paquete_cargar` in tools/runtime/paquete_de_audio.s.
        # And which ROM maps each one jumps to —`destinos`, indices into the
        # map table—, which is where it comes from which song may be playing
        # when a package is loaded: see `temas_heredados` in snes_convert.py.
        self.mapa = None
        self.por_mapa = {}
        # And which `PlayBGM`s of each map are **exit ones**: see `salida`.
        self.salidas = {}
        # And with which song each `Teleport` of each map jumps: see `salto`.
        self.saltos = {}
        # How many times an effect was asked for, so the page can see whether
        # a command made one sound: see `_seguir_la_salida`.
        self.pedidos = 0

    def _anotar(self, que, valor):
        if self.mapa is None:
            return
        lista = self.por_mapa.setdefault(
            self.mapa, {"temas": [], "sonidos": [], "destinos": []})[que]
        if valor not in lista:
            lista.append(valor)

    def indice(self, nombre):
        if nombre not in self.nombres:
            self.nombres.append(nombre)
        self._anotar("temas", self.nombres.index(nombre))
        return self.nombres.index(nombre)

    def destino(self, mapa):
        self._anotar("destinos", mapa)

    def salto(self, destino, tema):
        """Notes a jump from the map being compiled to `destino`: with `tema`
        if it goes right after a `PlayBGM` of that song, with no branches or
        effects in between —the one it surely carries—, or with None if it
        carries whatever is playing. The page notes it when it compiles, and
        `_destino_recordado` that of a `RecallToLocation`, always with None.
        See `temas_heredados` in snes_convert.py."""
        if self.mapa is None:
            return
        self.saltos.setdefault(self.mapa, {}).setdefault(destino, set()).add(
            tema)

    def salida(self, tema, sale):
        """Notes a `PlayBGM` of the song on the map being compiled: `sale` if
        after it, with no branches or effects in between, the page jumps to
        another map. A song is an exit song on a map if **all** its
        `PlayBGM`s there are: see `de_salida`."""
        if self.mapa is None:
            return
        anotadas = self.salidas.setdefault(self.mapa, {})
        anotadas[tema] = anotadas.get(tema, True) and sale

    def de_salida(self, mapa):
        """The songs a map turns on only to leave: each of its `PlayBGM`s is
        followed by a jump to another map, with no effects or branches in
        between. In the game it is `lufsorr` on map 3: it plays after the
        sequence of effects, when none is left to play, and the map is left
        right away. So it has no reason to fit in ARAM with those effects: it
        goes in the **separate** package, it is uploaded if there is room,
        and if not its `PlayBGM` uploads it —see `extra_de_salida` in
        tools/runtime/paquete_de_audio.s—. It is from 2026-09-26."""
        return [t for t, sale in self.salidas.get(mapa, {}).items() if sale]

    def sonido(self, nombre, volumen, tempo, balance, al_paquete=True):
        """The effect's index. Without `al_paquete` it is not noted in the
        map's package: it only sounds if something else puts it there. See
        `se_de_ruta_sin_paquete` in snes_music.py. It does not count in
        `pedidos` either: one that is not in the package does not sound, so
        it does not keep a song from being an exit song."""
        clave = (nombre, volumen, tempo, balance)
        if clave not in self.sonidos:
            self.sonidos.append(clave)
        if al_paquete:
            self.pedidos += 1
            self._anotar("sonidos", nombre)
        return self.sonidos.index(clave)

class Graficos:
    """The graphics the routes change to with command 34, numbered in the
    order they appear.

    Sibling of `Temas` and `Mensajes`, with a difference that matters: it is
    **per map**. What the ROM needs from a graphic —its twelve poses and its
    palette— lives in the sprite bank, and the bank belongs to each map; two
    maps that change to the same CharSet number it each on their own.

    The bytecode carries the index and not the name, as with songs and maps:
    the converter is the one that resolves it, and the ROM does not look at
    the LCF again.

    `asociaciones` half breaks the "per map", and it is worth understanding
    why: they are the graphics `ChangeSpriteAssociation` can give an actor,
    and that **survives the map change** —every time the game uses it, the
    command is right next to a teleport and what shows is the graphic on the
    other side—. So its index cannot mean one thing here and another there.
    It is solved by reserving the first slots of the table of **every** ROM
    map for them, in the same order: see `asociaciones_de`, which is the
    prior pass that gathers them, and `Imagenes.elegir`, which is the same
    pattern.
    """

    def __init__(self, asociaciones=()):
        self.pares = list(asociaciones)

    def indice(self, charset, index):
        par = (charset, index)
        if par not in self.pares:
            self.pares.append(par)
        return self.pares.index(par)


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


def asociaciones_de(game_maps, extra=()):
    """The (CharSet, index) pairs some `ChangeSpriteAssociation` names.

    It is `Graficos`' prior pass: it reserves for each one the same slot in
    the graphics table of every ROM map, because the graphic the command
    gives an actor **crosses the teleport** and its index has to mean the
    same on both sides of the jump.

    **All** the pages are looked at and not only the ones that compile, on
    purpose: if it depended on what compiles, the list would depend on
    whether the ROM carries a message window —same as `lideres_posibles`—
    and the converter's two passes would number differently. Reserving one
    slot too many costs the twelve poses of a CharSet in the sprite bank and
    nothing else.

    In this game they are two pairs —`Future3:0` and `BLVehicles:2`— and only
    if the ROM carries any of maps 49, 50, 52 or 54, which are the car chase.

    `extra` are the commands of the test pages, which go after.
    """
    pares = []
    comandos = [cmd for game_map in game_maps for evento in game_map.events
                for page in evento.pages for cmd in page.commands]
    for cmd in comandos + list(extra):
        if cmd.code != CHANGE_SPRITE_ASSOCIATION:
            continue
        p = list(cmd.parameters)
        if len(p) != 3 or p[2]:
            continue        # the ones `_compilar` is going to reject
        par = (cmd.string, p[1])
        if par not in pares:
            pares.append(par)
    return pares


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
# OP_MESSAGE: offset (word) within the `mensajes` block: opens
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
#     `sacudida_tick` in tools/runtime/camara.s.
#
# OP_FLASH_SCREEN: r, g, b, power (a byte each, 0..31) and frames
#     (byte): `FlashOnce`, the whole-screen flash. The
#     math is `destello_tick` in
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
#     saved is said by `partida_tabla` in
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
#     The ROM clamps to [0, ORO_MAX] like
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
# OP_PAN: operation (byte: PAN_CORRER or PAN_VOLVER), how far
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
#     `ceil(65536 / cuadros)`. It is the same kind of
#     number as a teleport's map index —resolved by the
#     converter so the ROM does not look at it again—, and
#     `paso_de_fundido` does it.
#
# OP_BGM: the song's index in `Temas` (byte). The ROM plays the
#     ones it carried —the first `TEMA_TOTAL`— and with
#     any other it does nothing. See `Temas`.
#
# OP_TIMER: operation (byte), seconds (word), visible (byte).
#     The five bytes are fixed even though each operation
#     uses two: that way the interpreter skips it without
#     looking at which one it is, which is what the
#     converter's `recorrer_codigo` does.

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
TIMER_PONER, TIMER_ARRANCAR, TIMER_PARAR = 0, 1, 2
TIMER_SEGUNDOS_FIJOS = 0        # the other value takes them from a variable
# `Game_Party::SetTimer` stores `segundos * 60 + 59`, not `segundos * 60`. The
# extra 59 are what makes the first second show whole: without them the timer
# would show the requested value for a single frame.
TIMER_CUADROS_DE_MAS = 59

# ControlSwitches: the first parameter says where the ids come from and the
# last what to do with them (liblcf, ControlSwitches::Operation).
SWITCH_UNICO, SWITCH_RANGO, SWITCH_INDIRECTO = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

# An absurd range is not unrolled: better not to run the page than to emit
# thousands of opcodes for one line.
MAX_RANGO = 64

# RM2k measures waits in tenths of a second.
CUADROS_POR_DECIMA = 6
CUADROS_POR_SEGUNDO = 60        # DEFAULT_FPS: it is what the timer counts with

# A step is sixteen pixels at WALK_SPEED = 2 per frame.
CELDA_PX = 16
WALK_SPEED = 2
CUADROS_POR_CELDA = CELDA_PX // WALK_SPEED

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
FUNDIDO_CUADROS = 35
FUNDIDO_TOTAL = FUNDIDO_CUADROS * 2

# Of those 35, the ramp is 24 and the other 11 are plain black. The console
# cannot fade any other way: INIDISP's master brightness has sixteen steps and
# nothing more, so stretching the ramp over the 35 frames does not give a
# finer fade, it only repeats steps. And the black at the end is not padding:
# **it is where the map is loaded**. The load writes VRAM and CGRAM by DMA and
# costs six or seven frames; inside the black they are not seen and they do
# not run the clock, because the fade is counted in hardware frames and not
# in loop turns. Between the map being loaded —frame 24— and the ramp back
# leaving zero —frame 47— there are 23 frames of margin.
FUNDIDO_RAMPA = 24
FUNDIDO_NEGRO = FUNDIDO_CUADROS - FUNDIDO_RAMPA
BRILLO_MAX = 15

# `ChangeScreenTransitions` (10690) changes that transition from then on:
# `[which, transition]`, with which 0 the teleport's erase and 1 its show —2
# to 5 are the battle's— and the transition an index into
# `Game_System::GetTransition`'s `fades` table. The game uses it in Boss
# Wick's hideout: zoom (16) to go to the vidcasts, mosaic (17) inside, and fade
# (0) on the way back. It is state that crosses the teleport, and in RM2k it
# travels in the save; here it does not —see `TRANSICION_BORRAR` in
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
TRANSICION_BORRAR, TRANSICION_MOSTRAR = 0, 1
RM2K_TRANSICION_MOSAICO = 17
RM2K_TRANSICIONES_CORTE = (19, 20)       # the cut and "none"
RM2K_TRANSICIONES_QUE_NO = {19: "the cut", 20: "none"}
# What the bytecode carries: what the ROM does, and not the RM2k number.
TRANSICION_FUNDIDO, TRANSICION_MOSAICO, TRANSICION_CORTE = 0, 1, 2


def paso_de_fundido(milisegundos):
    """How much the song's volume goes down per frame, in 1/65536.

    RM2k measures `FadeOutBGM` in milliseconds and the ROM counts frames, so
    the conversion is done here once: the 65816 does not divide without
    asking the hardware, and the hardware divider is eight bits —the 5000 ms
    of map 3's door are 300 frames and do not fit—.

    The level starts at 65535 and goes down by `paso`; it is rounded up so
    the fade ends **within** the frames it asks for and not one after.
    """
    cuadros = max(1, milisegundos * CUADROS_POR_SEGUNDO // 1000)
    return min(0xFFFF, -(-0x10000 // cuadros))


def rampa_de_fundido():
    """The INIDISP brightness on each frame of the ramp, from black to full.

    It is a rounded straight line over the sixteen steps the master
    brightness has. The ROM does not compute it: the converter emits it in
    `mapdata.inc` as `fundido_rampa`, so the number lives in a single
    place.
    """
    ultimo = FUNDIDO_RAMPA - 1
    return [(BRILLO_MAX * s + ultimo // 2) // ultimo
            for s in range(FUNDIDO_RAMPA)]


# What triggers a page. Those of liblcf's `rpg::EventPage::Trigger`.
TRIGGER_ACCION = 0          # the player presses the action key facing it
TRIGGER_TOCA_HEROE = 1      # the hero walks onto it
# 2 is the collision —the event walks into the hero—, and it is not named here.
TRIGGER_AUTOMATICO = 3
TRIGGER_PARALELO = 4

# The ones the ROM knows how to trigger. The rest of an event's pages are
# emitted anyway —they are needed to know which one is active— but without
# code.
TRIGGERS = (TRIGGER_ACCION, TRIGGER_TOCA_HEROE, TRIGGER_AUTOMATICO,
            TRIGGER_PARALELO)

# TURN. An event with a graphic **turns toward the hero** when he triggers it,
# unless it has a fixed direction: it is the
# `SetFacing(GetDirectionToCharacter(GetPlayer()))` of
# `Game_Event::ScheduleForegroundExecution`. Since 2026-09-11 it is done, on
# both sides —before, it answered facing wherever it was—. The rules, which
# the ROM follows in `giro_disparar` and company:
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
ANIM_FIJAS = (2, 3, 4, 5)

# Only the events on the hero's layer are triggered with the action key: it is
# the `GetLayer() == Layers_same` of `CheckEventTriggerThere`.
LAYER_MISMA = 1


class NoSePuede(Exception):
    """This page has something the ROM does not know how to do yet."""


class Eventos:
    """The map's events, as the compiler sees them.

    It exists for a reason that was measured and is paid dearly otherwise:
    **RM2k's event id is not the index in the ROM's table**. 39 maps of this
    game have gaps in the numbering —events deleted in the editor— so a
    route aimed at id 8 would move whichever is eighth in the list, which can
    be any other. The translation is done here, once, and the bytecode never
    sees an RM2k id again.

    `mio` is the event that owns the page being compiled, which is whom
    "this event" points to.
    """

    def __init__(self, game_map, mio=None):
        self.indices = {ev.id: n for n, ev in enumerate(game_map.events)}
        # The pages of each event, by id, for `CallEvent`: calling a map
        # event compiles its page in place. The pages go and not their
        # commands because the number the call brings is the page's, and in
        # RM2k it starts at one.
        self.paginas = {ev.id: ev.pages for ev in game_map.events}
        # Visible is having a graphic on the active page, which is the same
        # rule `collect_npcs` uses to decide what goes in the ROM's table.
        self.visibles = {ev.id for ev in game_map.events
                         if ev.active_page() is not None
                         and ev.active_page().character_name}
        # Which character each one is drawn with, to know which share a
        # palette. On the console the flash is done on the character's
        # palette, so two events with the same graphic would flash together:
        # see `_compilar`.
        self.grafico = {}
        for ev in game_map.events:
            page = ev.active_page()
            if page is not None and page.character_name:
                self.grafico[ev.id] = (page.character_name,
                                       page.character_index)
        # Which variables some page condition of this map looks at: it is
        # `Game_Map::RefreshEvent`'s `map_cache`, which is filled with each
        # page's `pg.condition.variable_id`. `escritura_pide_refresco` reads
        # it. Measured over the 328 maps: at most **one** per map, and 314
        # have none.
        self.vars_observadas = {pg.condition.ids["variable"]
                                for ev in game_map.events for pg in ev.pages
                                if "variable" in pg.condition.active}
        # Which map it belongs to, to know when a page leaves it: see
        # `afuera`.
        self.map_id = getattr(game_map, "map_id", None)
        # How a `TileSubstitution` translates to ROM block pairs. The
        # converter sets it on the map, because it depends on how the blocks
        # ended up —which is the console's business— and not on RM2k.
        # Without it the command does not compile, which is what happens in
        # any ROM built without going through `snes_convert`.
        self.sustituciones = getattr(game_map, "sustituciones", None)
        self.mio = mio

    def comparte_grafico(self, quien):
        """Whether this event draws with the same character as another one on
        the map."""
        cual = self.grafico.get(quien)
        return cual is not None and sum(1 for g in self.grafico.values()
                                        if g == cual) > 1

    def para(self, id_evento):
        otro = Eventos.__new__(Eventos)
        otro.indices, otro.visibles = self.indices, self.visibles
        otro.grafico, otro.mio = self.grafico, id_evento
        otro.paginas = self.paginas
        otro.vars_observadas = self.vars_observadas
        otro.map_id = self.map_id
        otro.sustituciones = self.sustituciones
        return otro

    def afuera(self):
        """The same, for what the page does **after jumping to another map**:
        it keeps running there, and which variables the pages there look at
        cannot be known from here, so every write asks for a refresh. See
        `escritura_pide_refresco`.

        The rest does not change, and not because it is right: an event named
        by id after the jump is translated against this map and not against
        the destination. No page of the game that compiles today does it.
        """
        otro = self.para(self.mio)
        otro.vars_observadas = None
        # And the blocks there are not these: a substitution after the jump
        # would talk about the new map's tiles and the translation is the old
        # one's.
        otro.sustituciones = None
        return otro

    def blanco(self, quien):
        """The target byte that goes in OP_ROUTE, or None if it cannot be
        moved.

        0 is the hero; for an event, its index plus one. Vehicles do not
        exist in this ROM and neither does an id the map does not have: both
        return None, which cuts the page.
        """
        if quien == RUTA_HEROE:
            return 0
        if quien == RUTA_ESTE_EVENTO:
            quien = self.mio
        if quien in self.indices:
            return self.indices[quien] + 1
        return None


class Mensajes:
    """The ROM's text block, and the offset of each box.

    It belongs to the whole ROM and not to the map: `OP_MESSAGE` carries an
    offset within this block, so all maps share the numbering and the
    converter emits it only once. What is repeated is stored only once —the
    game repeats whole boxes, 418 of 2895— and it comes for free because the
    content already is the key.
    """

    def __init__(self, paso=1):
        # How many bytes at a time the offset in the bytecode counts. The
        # game's block goes by four —see MENSAJES_PASO— and each box starts
        # at a multiple of four; the others, like the troops', by one.
        # Inside, everything is in bytes: the step is applied going in and
        # going out.
        self.paso = paso
        self.datos = bytearray()
        self.donde = {}         # the lines already stored -> their offset
        self.textos = {}        # and back: the offset -> the lines

    def agregar(self, lineas):
        r"""The offset of this box, storing it if it is the first time.

        The escape tail is removed **here** —see `cola_de_escapes`— and not
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
        lineas, pausas, autocierre = cola_de_escapes(lineas)
        lineas = tuple(t[:COLUMNAS]
                       for t in list(lineas)[:LINEAS])
        clave = (lineas, pausas, autocierre)
        if clave not in self.donde:
            while len(self.datos) % self.paso:
                self.datos.append(0)
            donde = len(self.datos)
            self.datos += mensaje_bytes(lineas, pausas, autocierre)
            if donde // self.paso > 0xFFFF:
                raise SystemExit(
                    "this ROM's messages are %d bytes and the OP_MESSAGE "
                    "operand is 16 bits, counting by %d bytes"
                    % (len(self.datos), self.paso))
            self.donde[clave] = donde
            self.textos[donde] = lineas
        return self.donde[clave] // self.paso

    def lineas(self, donde):
        """The lines `agregar` stored at that offset."""
        return self.textos[donde * self.paso]

    def cola(self, donde):
        """How many pauses that box carries and whether it closes on its own.

        It comes from **the same bytes the ROM reads** and not from a
        parallel dictionary: `msg_empezar` decodes that header byte with the
        same masks. A format read in two different ways is exactly the
        failure mode this repo has already paid for twice.
        """
        cabecera = self.datos[donde * self.paso]
        return (cabecera >> 4, bool(cabecera & CABECERA_AUTOCIERRE))

    def marca(self):
        return len(self.datos)

    def volver(self, marca):
        """Undoes what was added since `marca`.

        It is needed because a page is compiled command by command and can
        be cut at the last one: without this, the text of all the pages that
        **do not** compile would stay in the cartridge anyway. It is not a
        micro-optimization, it is the whole game's 161 KB against the few
        that are needed.
        """
        del self.datos[marca:]
        self.donde = {k: v for k, v in self.donde.items() if v < marca}
        self.textos = {k: v for k, v in self.textos.items() if k < marca}

    def bytes(self):
        # Never empty: the assembler needs the label resolved even if the ROM
        # is never going to read it.
        return bytes(self.datos) or b"\x00"


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
# the ROM reads in the compositor's loop —`and #CABECERA_LINEAS` and done— and
# the pauses at the top because they are read only once, on opening, where an
# extra `lsr` does not show.
CABECERA_LINEAS = 0x07
CABECERA_AUTOCIERRE = 0x08

# The `OP_MESSAGE` offset in the game's block counts by four bytes, so the
# block can be 256 KB with a 16-bit operand. It went by two from when the
# texts were reflowed for the window (`port/textos.py`) until 2026-09-27, when
# the main path of the world chapter went past 128 KB; the whole game is about
# 161 KB. It costs a byte and a half of padding per box, on average, against
# half a byte by two: step 3 was measured (half the padding, 192 KB, and a
# multiplication by three in the ROM) and a 24-bit operand (no padding but one
# more byte for each `OP_MESSAGE`, which outnumber the boxes), and neither
# saves what it complicates: see `workflow/tasks/*/mundo-3-el-espacio.md`.
# `msg_empezar` multiplies it by four, and an `.assert` there enforces that
# both sides of the math are the same: `MENSAJES_TOPE`.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
MENSAJES_PASO = 4


def mensaje_bytes(lineas, pausas=0, autocierre=False):
    """A text box as the ROM reads it: the header, and each line with its
    length.

    The characters go as an index into the font's table, that is ASCII minus
    32. All of this game's text fits there: it was measured, and it does not
    have a single accented letter.
    """
    assert 0 <= pausas <= PAUSAS_MAX
    out = bytearray([min(len(lineas), LINEAS)
                     | (CABECERA_AUTOCIERRE if autocierre else 0)
                     | (pausas << 4)])
    for texto in list(lineas)[:LINEAS]:
        texto = texto[:COLUMNAS]
        out.append(len(texto))
        for ch in texto:
            if not 32 <= ord(ch) < 127:
                raise SystemExit("the message has a character that is not in "
                                 "the font: %r" % ch)
            out.append(ord(ch) - 32)
    return bytes(out)


def agrupar(comandos):
    """The commands one at a time, except the text boxes.

    Returns (command, extra lines), where the extra ones are the
    `ShowMessage_2`s that follow a `ShowMessage` and are part of the same
    box. A loose `ShowMessage_2` is returned alone and does not compile,
    which is right: it would be a line with no window to put it in.

    It is part of the filter and not of the emitter: counting the commands
    separately is what made the measurement of how much the text boxes
    unlocked come out wrong.
    """
    comandos = list(comandos)
    i = 0
    while i < len(comandos):
        j = i + 1
        if comandos[i].code == SHOW_MESSAGE:
            while j < len(comandos) and comandos[j].code == SHOW_MESSAGE_2:
                j += 1
        yield comandos[i], [c.string for c in comandos[i + 1:j]]
        i = j


def puede_dispararse(page):
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
    if page.trigger == TRIGGER_ACCION:
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
    if page.trigger == TRIGGER_TOCA_HEROE:
        return page.layer != LAYER_MISMA
    return True


# `ConditionalBranch` and its two closers. They come from `event_codes.py`,
# which is generated from liblcf: the doors' ones were written from memory
# once and three were wrong.
COND_RAMA = 12010
COND_SINO = 22010
COND_FIN = 22011

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
COND_ORO = 3
# The inventory **already exists** —`OP_ITEM` and `FAR_ITEMS`, since
# 2026-09-10— so the line above is stale: the item branch is
# `GetItemCount(id) > 0`, exactly the same question as the page condition by
# item, which the ROM already answers by reading `FAR_ITEMS`. Equipment does
# not count, as in `condiciones_ok`: `GetEquippedItemCount` asks for
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
COND_ACTOR_EN_GRUPO = 0
# `actor->IsSkillLearned(p[3])`. Since 2026-09-21 it is state: the bit of the
# (actor, skill) pair in `FAR_HAB`, which starts with what
# `reglas.aprendidas_de` says from the LDB and which `ChangeSkills` turns on
# and off. The operand that travels is the pair's slot and not the skill; see
# `HABILIDAD_RANURA`.
COND_ACTOR_HABILIDAD = 4
# easyrpg's five `Get*Id()`s compared against `p[3]`: weapon, shield, armor,
# helmet and accessory. This **is** real state —`FAR_EQUIPO`, which the
# equipment screen writes and which travels in the save— and it starts from
# the LDB's `initial_equipment`. Asking about item 0 says yes as soon as there
# is an empty slot, which is what RM2k does; no page of the game does it.
COND_ACTOR_EQUIPO = 5
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
# and travel in the saved game. `indexar_variables` builds the index. Until
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
VAR_REFRESCO = 0x80
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
VAR_RANURA_MAX = 0xFF
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
# allowed. The ROM stores it in `FAR_ACCESO`. Saving from the save point does
# not look at it, like `OpenSaveMenu` in RM2k.
#
# The operand is the bit and not the permission's number, and that is from the
# third round: the ROM got it with an `inc a` on the number, which gives $01
# and $02 for the first two and **$03 for the third**, that is forbidding the
# other two things at once. With the bit set by the converter the opcode has
# no math to do and accepts whatever permissions are needed.
#
# OP_ACCESS: the bit in FAR_ACCESO (byte), allowed (byte)
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
CLIMA_LLUVIA = 1
LLUVIA_GOTAS = (15, 45, 75)
LLUVIA_VIDA = 12
LLUVIA_NACE = 26    # out of 256
LLUVIA_SEMILLA = 0x1D2B
LLUVIA_COLORES = ((16, 16, 18), (11, 11, 13), (6, 6, 7))   # 5-bit


def lluvia_pixeles(x, y):
    """The pixels of a drop with its corner at (x, y): a 4x16 streak going
    down to the left, one pixel every four rows."""
    return [(x + 3 - r // 4, y + r) for r in range(16)]


# The sound effects, since 2026-09-11: `PlaySound` compiles to OP_SOUND with
# the index of its entry in `Temas.sonidos`, and the ROM's table says with
# which sample, what pitch, what volume on each side and how many frames. The
# samples go in ARAM next to the music's bank, with a budget of their own: see
# `build_efectos` in snes_music.py. They play on voice 7, which is stolen from
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
# long as it lasts: two frames per animation frame. See `animacion_tick` in
# tools/runtime/animacion_de_batalla.s.
#
# The flash is not exactly RM2k's: there the power is
# `min((7 - (d + 1) / 2) * potencia / 6, 31)` for ten frames, in steps; here
# it is a `FlashScreen` or a `FlashSprite` that starts at the first and goes
# down linearly over `ANIM_DESTELLO_CUADROS`. It is the same light and it
# lasts the same.
#
# OP_ANIMATION: n, and n entries of ANIM_ENTRADA bytes
ANIM_ENTRADA = 8
ANIM_SONIDO, ANIM_DESTELLO, ANIM_FLASH = 0, 1, 2
# Ten, which is how long RM2k's lasts, and **even** on purpose: the screen
# flash works in two phases according to the parity of what it has left —see
# `destello_tick`—, and a `FlashScreen` of the game always lasts tenths times
# six. With eleven the first phase was the even one, a path no page takes and
# that therefore tests nothing: `animacion` showed it.
ANIM_DESTELLO_CUADROS = 10
ANIMACIONES = {}
# The **drawing**, since 2026-09-12. The opcode carries two more bytes: the
# RM2k animation number as is —180 at most, so it fits in one— and what it is
# drawn over. The number goes raw and not as an index of ours on purpose: the
# ROM looks it up in `anim_batalla_de`, a table by number, so neither end has
# to carry a counter the other one guesses. See `animacion.py`.
#
# `ANIM_SIN_DIBUJO` is "this animation is not drawn", and it is used by the
# ones RM2k repeats three by three to cover the screen —`global`—, which are
# not done.
ANIM_SIN_DIBUJO = 0xFF
ANIM_BLANCO_PANTALLA = 0xFF     # "screen" scope: goes to the center, no target


def dibujo_blanco(anim, blanco):
    """What this animation is drawn over: the target, or the screen.

    With "screen" scope —`Animation::Scope_screen`, which is 1— RM2k draws it
    at the center and asks the target nothing; with the other, over the
    target, which is the same byte the routes and the flashes already use.
    """
    if anim.get("alcance", 0) == 1:
        return ANIM_BLANCO_PANTALLA
    return blanco

# The picture of a `ShowPicture`, since 2026-09-12. The ROM carries **a
# single one** —see `Imagenes`— and that is why the three opcodes do not say
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
IMAGEN_CUADROS_MAX = 255


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
# it by looking it up in `tropa_id`, and a troop that is not there is a battle
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
BATALLA_PERDER = 0xFFFF

# `HaltAllMovement`: all of the map's forced routes are abandoned at once. It
# is `Game_Map::RemoveAllPendingMoves`, that is a `CancelMoveRoute` on the
# hero and on each event, and what cancelling means is written only once: it
# is **the same as what happens when the route ends on its own** —whoever had
# a page route of its own goes back to it, whoever did not stands still— and
# that is why the ROM calls `retomar_pagina`.
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
# 60 and `ACTORES_N` counts them, and the data does not, because the items go
# up to 450.
#
# It carries no polarity: RM2k gives none to these two —the branch below is
# the `else`— same as to "is in the party". The destination goes last, as in
# all of them, because it is what `con_destino` patches when closing the
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
#   and not to `Game_Player`. That is why its index comes from `Graficos`'
#   reserved slots —see `asociaciones_de`— and not from the map's free
#   numbering.
# * **It is stored per actor and shows only if that actor leads.** The one
#   that does not lead is not drawn, so the change stays waiting; the ROM
#   resolves it in `elegir_grafico_heroe`, which is the only one that decides
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
# `test_ningun_opcode_comparte_numero_con_otro` guards it.
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
# The waiting one is emitted **twice**, the first with `TECLA_ARRANCA`: that
# one sets the variable to zero, eats whatever edge there was and returns
# control without looking at anything. It is RPG_RT's
# `Input::ResetTriggerKeys()`, which exists so the command does not eat the
# same key that just closed a message —and in this game the 23 waits come
# right after a `ShowMessage`, so without it the sign would skip past—. Two
# opcodes and not a state byte because the interpreter has nowhere to keep
# it: the one that waits **rewinds its own cursor** and runs again frame after
# frame, so it cannot tell the first turn from the others.
TECLA_ESPERA   = 0x01    # bit 0 on purpose: `tecla_valor` reads it with an `lsr`
TECLA_DIRS     = 0x02
TECLA_DECISION = 0x04
TECLA_CANCELAR = 0x08
TECLA_ARRANCA  = 0x10

KEY_INPUT_PROC = 11610

# The value RM2k stores for each key, and from here also comes the order they
# are checked in: from highest to lowest.
TECLA_VALOR_CANCELAR = 6
TECLA_VALOR_DECISION = 5
# By ROM direction: 0 up, 1 right, 2 down, 3 left.
TECLA_VALOR_DIR = {0: 4, 1: 3, 3: 2, 2: 1}

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
#     which —`LUGAR_SALTAR`—, and when recalling bits 7, 6 and 5 are the
#     VAR_REFRESCO of each of the three writes. **The map in the variable is
#     the RM2k id**, which is what any other page reads and writes; the ROM
#     translates it with `mapa_rm2k`. They unlock 55 pages of Lashe City's
#     milestone 3 —the plant's floors, 28 on 60 and 26 on 62, and the droid
#     tutorial— and they are what holds back the most pages in the whole
#     game.
#
# OP_MEMORIZED_BGM: 0 remember the song that plays, 1 put it back.
LUGAR_SALTAR = 0x01
LUGAR_REFRESCOS = (0x80, 0x40, 0x20)    # the map, x and y


def tecla_de(banderas, apretadas):
    """Which value the variable gets with these keys pressed.

    `apretadas` is the set of what the player is holding: integers 0 to 3
    for the directions, "a" and "b" for the two keys. It is what
    `test_tecla.py` expects from `op_key`, and the order is `CheckInput`'s.

    **Which set is passed depends on the form of the command**, and the
    caller decides that: the waiting one looks at this frame's **edges**
    —`Input::IsTriggered`— and the non-waiting one at what is held
    —`Input::IsPressed`—. Here they cannot be told apart: both are "what
    counts as pressed" for this question.
    """
    if banderas & TECLA_CANCELAR and "b" in apretadas:
        return TECLA_VALOR_CANCELAR
    if banderas & TECLA_DECISION and "a" in apretadas:
        return TECLA_VALOR_DECISION
    if banderas & TECLA_DIRS:
        for direccion in (0, 1, 3, 2):          # up, right, left, down
            if direccion in apretadas:
                return TECLA_VALOR_DIR[direccion]
    return 0

ENEMY_ENCOUNTER = 10710
VICTORY_HANDLER = 20710
ESCAPE_HANDLER = 20711
DEFEAT_HANDLER = 20712
END_BATTLE = 20713

# The three handlers, in the order their destinations go in the opcode.
BATALLA_HANDLERS = (VICTORY_HANDLER, ESCAPE_HANDLER, DEFEAT_HANDLER)

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
BATALLA_FONDO_DEL_LUGAR = 0
BATALLA_FONDO_DEL_COMANDO = 1
# The backdrop of a troop that fights with the local one: it is not known when
# compiling, because it depends on where the hero is. See
# `fondo_de_encuentro`.
FONDO_DEL_LUGAR = ("del lugar",)
# The troop pages' command that changes the backdrop mid-battle. The game does
# not use it, and the port does not compile it; it is swept for the names it
# gives, so that `fondos_nombrados` is the whole game's.
CHANGE_BATTLE_BG = 13210
# The escape parameter: 0 cannot, 1 cuts the battle. Only 1 is asked
# about.
BATALLA_ESCAPE_CORTA = 1
BATALLA_DERROTA_GAME_OVER = 0


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
# **This is registered inside the compilation** —`audio_de_batalla`, when
# compiling the `EnemyEncounter`— and not in the converter: the `Temas`
# indices are carried by the bytecode of each `PlayBGM` and each `PlaySound`,
# so everyone who compiles pages has to number the same way, and a song noted
# from outside would shift all the ones after it.
AUDIO_BATALLA = {}

# The order is the contract with the ROM: the converter emits `BA_SE_<n>` with
# the index each one got from `Temas`, in this order.
AUDIO_BATALLA_SE = ("dodge_se", "enemy_attack_se", "enemy_damaged_se",
                    "actor_damaged_se", "enemy_death_se", "escape_se",
                    # The one from 2026-09-13, when the battle started
                    # letting items be used: easyrpg's `Item::GetStartSe`,
                    # which is the LDB's `item_se`.
                    "item_se")
AUDIO_BATALLA_BGM = ("battle_music", "battle_end_music")

# A name RM2k uses to say "nothing": neither the song nor the effect exist.
AUDIO_APAGADO = ("", "(OFF)")


def base_de_datos(game_dir):
    """The game's LDB, **for reading**: the `indexar_*`s and the sweeps
    share it, which used to load it each on its own.

    None of the ones asking for it here modifies it, and that is why it can
    be the same object. It is memoized while nothing that builds it changes:
    the dump's files and the fork's ChipSets —name, date and size— and the
    two `lcf` hooks, which change what is read.
    """
    from rpgmaker import fork, lcf
    ruta = os.path.join(game_dir, "RPG_RT.ldb")
    huella = [ruta, lcf.REAJUSTAR_TEXTOS, lcf.DECORAR_TRANSLUCIDO]
    for carpeta in (os.path.join(lcf.volcado(ruta), "db"), fork.carpeta_chipsets()):
        if os.path.isdir(carpeta):
            for nombre in sorted(os.listdir(carpeta)):
                estado = os.stat(os.path.join(carpeta, nombre))
                huella.append((carpeta, nombre, estado.st_mtime_ns,
                               estado.st_size))
    huella = tuple(huella)
    if _BASE[:1] != [huella]:
        _BASE[:] = [huella, lcf.Database(ruta)]
    return _BASE[1]


_BASE = []


def indexar_audio_de_batalla(game_dir):
    """The battle's song and effects, from the LDB. The converter and the
    tests that compile pages call it, same as `indexar_animaciones`."""
    db = base_de_datos(game_dir)
    AUDIO_BATALLA.clear()
    AUDIO_BATALLA["battle_music"] = db.battle_music
    AUDIO_BATALLA["battle_end_music"] = db.battle_end_music
    for nombre in AUDIO_BATALLA_SE:
        AUDIO_BATALLA[nombre] = db.system_se[nombre]


# The `Temas.por_mapa` key where the battle's audio goes. It is not a map: it
# is **an audio package of its own**, which the ROM loads when opening the
# battle and unloads when closing it.
#
# It goes separately and not ahead of the map's package, and that is
# measured: the battle song is 18 samples and 51,480 B of ARAM's 64,512, so
# putting it in map 2's package the 24 effects of that map —49,068 B, which
# all fit today— dropped almost entirely. With its own package the map pays
# nothing while there is no battle.
PAQUETE_BATALLA = "batalla"


def audio_de_batalla(temas):
    """Notes in `temas` what the battle is going to play, and returns their
    indices: two songs and `AUDIO_BATALLA_SE` effects, $FF or $FFFF the off
    one.

    It is called every time a page compiles an `EnemyEncounter`. What is
    noted falls into the `PAQUETE_BATALLA` package and not into that of the
    map that has the battle, so `temas.mapa` has to be saved and restored
    around it.
    """
    if temas is None or not AUDIO_BATALLA:
        return None
    indices = {}
    anterior = temas.mapa
    temas.mapa = PAQUETE_BATALLA
    for nombre in AUDIO_BATALLA_BGM:
        tema = AUDIO_BATALLA[nombre]
        indices[nombre] = (0xFF if tema in AUDIO_APAGADO
                           else temas.indice(tema))
    for nombre in AUDIO_BATALLA_SE:
        efecto = AUDIO_BATALLA[nombre]
        indices[nombre] = (0xFFFF if efecto[0] in AUDIO_APAGADO
                           else temas.sonido(*efecto))
    temas.mapa = anterior
    return indices


class Imagenes:
    """The only picture that goes into the cartridge, and which commands
    move it.

    It is the sibling of `Temas` and `Graficos`: the converter builds one,
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
        self.nombre = None      # the picture that took the slot
        self.info = None        # what `imagen.convertir` got from it
        self.numero = None      # the RM2k picture number that shows it
        self.donde = None       # where its ShowPicture centered it

    def _leer(self, nombre):
        import os
        from PIL import Image
        ruta = os.path.join(self.game_dir, "Picture", nombre + ".png")
        if not os.path.exists(ruta):
            return None
        return Image.open(ruta)

    def elegir(self, game_maps):
        """Which of the ROM's `ShowPicture`s takes the slot.

        It is decided **before compiling a single page** and looking at all
        of the cartridge's maps in table order, and not by order of arrival:
        that way the choice does not depend on the order the maps are
        compiled in.
        """
        if self.nombre is not None:
            return self.info    # the slot is already taken
        for game_map in game_maps:
            for event in game_map.events:
                for page in event.pages:
                    for cmd in page.commands:
                        if cmd.code != SHOW_PICTURE:
                            continue
                        if not imagen_aceptable(cmd.parameters):
                            continue
                        if cmd.parameters[7]:
                            continue    # the PNG's transparent color
                        im = self._leer(cmd.string)
                        if im is None:
                            continue
                        p = cmd.parameters
                        info = imagen_mod.convertir(im, p[2], p[3])
                        if not imagen_mod.cabe(info):
                            continue
                        self.nombre, self.info = cmd.string, info
                        self.numero, self.donde = p[0], (p[2], p[3])
                        return info
        return None

    def mostrar(self, numero, nombre, cx, cy):
        """The slot's picture if this `ShowPicture` is its own, or None."""
        if self.nombre is None:
            return None
        return (self.info if (self.nombre, self.numero, self.donde)
                == (nombre, numero, (cx, cy)) else None)

    def suyo(self, numero, cx, cy):
        """Whether the slot's picture is the one this command names and it
        does not move from where it is. `MovePicture` and `ErasePicture` ask
        it, since they do not carry the name: in RM2k the picture number is
        all that ties them to their `ShowPicture`."""
        return (self.nombre is not None and self.numero == numero
                and (cx is None or self.donde == (cx, cy)))


def indexar_animaciones(game_dir):
    """The LDB's battle animations, by id: their frames and their timings,
    with liblcf's default values —the decoder omits the ones that are not
    there—. The converter and the tests that compile pages call it."""
    db = base_de_datos(game_dir)
    ANIMACIONES.clear()
    for numero, anim in db.decode().get("animations", {}).items():
        timings = []
        for _i, t in sorted((anim.get("timings") or {}).items()):
            se = t.get("se") or {}
            timings.append({
                "frame": t.get("frame", 0),
                "se": (se.get("name", ""), se.get("volume", 100),
                       se.get("tempo", 100), se.get("balance", 50)),
                "alcance": t.get("flash_scope", 0),
                "rgb": (t.get("flash_red", 31), t.get("flash_green", 31),
                        t.get("flash_blue", 31)),
                "fuerza": t.get("flash_power", 31),
            })
        # And what is needed to **draw it**, since 2026-09-12: the `Battle`
        # sheet, each frame's cells and where the box goes. `animacion.py`
        # reads it, being the only one that knows what to do with this;
        # here it is stored exactly as it comes from the LDB.
        cuadros = anim.get("frames") or {}
        ANIMACIONES[numero] = {"cuadros": [cuadros[k].get("cells") or {}
                                           for k in sorted(cuadros)],
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
ACCESO_GUARDAR, ACCESO_MENU, ACCESO_ESCAPAR = 0, 1, 2
# Each one's bit in `FAR_ACCESO`, and the bits mean "forbidden" so that the
# reset's zero is "everything allowed", which is how RM2k starts. $80 is the
# menu request —`menu_calling`— and it is not a permission.
ACCESO_BIT = (0x01, 0x02, 0x04)
# `ChangeEscapeAccess` is the permission to escape from a battle, and it is
# stored without being read: the battle looks at the escape, and that belongs
# to someone else. It is here anyway because it is what unlocks the most for
# what a bit costs —**30 of the game's 39 pages with `EnemyEncounter` that do
# not compile have it ahead**—, and because a command accepted without being
# done would be a lie: RM2k stores it in `Game_System` and it travels in the
# save, and here too.
# The ControlVars operations that compile: set, add, subtract. Multiply,
# divide and modulo are not used by any page of the game.
VAR_PONER, VAR_SUMAR, VAR_RESTAR = 0, 1, 2
# And where the operand comes from, with the RM2k number: a constant, another
# variable, a random number between a and b, or "other", which here are the
# gold and the seconds the timer has left. The random one requires b - a to be
# less than 256: the ROM divides with the hardware's eight-bit divider.
VAR_CONSTANTE, VAR_VARIABLE, VAR_AZAR, VAR_OTRO = 0, 1, 3, 7
OTRO_ORO, OTRO_TIMER = 0, 1
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
VAR_PERSONAJE = 6
PERSONAJE_X, PERSONAJE_Y = 1, 2
CMP_IGUAL, CMP_MAYOR_IGUAL, CMP_MENOR_IGUAL, CMP_MAYOR, CMP_MENOR, \
    CMP_DISTINTO = range(6)
# The random generator: a sixteen-bit xorshift —x ^= x << 7; x ^= x >> 9;
# x ^= x << 8— seeded at reset. There is no real entropy, on purpose: a page
# with randomness always gets the same sequence, and that is why what it
# draws can be frozen in a golden.
AZAR_SEMILLA = 0xACE1
TIMER_PONER_VAR = 3     # the timer's fourth operation: the seconds from a
                        # variable. RM2k's three are 0, 1 and 2.

VARIABLE_SLOT = {}      # RM2k variable -> slot in the ROM


def mapas_del_juego(game_dir):
    """The numbers of all the maps in the game, in order."""
    import glob
    return sorted(int(os.path.basename(p)[3:7]) for p in
                  glob.glob(os.path.join(game_dir, "Map[0-9][0-9][0-9][0-9].lmu")))


def variables_de(game_dir, map_ids=None, extra=()):
    """Which variables the pages of these maps name —without a list, the
    whole game's—, each with its slot.

    All the commands and conditions of all the pages are looked at, whether
    they compile or not: it is a cheap superset —two bytes per variable— and
    that way a page that compiles later does not change the others' slots.
    `extra` are those of the test pages, which do not come from any map: the
    converter sweeps them with `variables_de_comandos`.

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
    ids |= barrer_los_mapas(
        game_dir, mapas_del_juego(game_dir) if map_ids is None else map_ids,
        _variables_del_mapa)
    if map_ids is None:
        # And those of the troops' pages, which belong to the whole game and
        # not to a map. They add up to **forty**, measured on 2026-09-21: the
        # characters' systems each carry their counters —Talan's 81 and 106
        # count how many times he absorbed each technique—, and no map names
        # them.
        db = base_de_datos(game_dir)
        for tropa in db.troops.values():
            for pagina in tropa.pages:
                if "variable" in pagina.activos:
                    ids.add(pagina.condicion["variable_id"])
        for comandos in comandos_de_las_tropas(db):
            ids |= variables_de_comandos(comandos)
    return {variable: ranura for ranura, variable in enumerate(sorted(ids))}


def _variables_del_mapa(game_map):
    """The `variables_de` sweep over one map."""
    ids = set()
    for evento in game_map.events:
        for page in evento.pages:
            if "variable" in page.condition.active:
                ids.add(page.condition.ids["variable"])
            ids |= variables_de_comandos(page.commands)
    return ids


def barrer_los_mapas(game_dir, map_ids, barrido):
    """The union of `barrido(mapa)` —a set— over those maps.

    The sweeps of `variables_de` and `pares_de_habilidad` each load the
    game's 328 maps, and loading them is almost all they cost: they run in
    parallel, in batches, and each batch returns the union of its own. The
    result is a set, so the order does not matter.
    """
    from rpgmaker import lcf
    from common.parallel import in_parallel
    rutas = [os.path.join(game_dir, "Map%04d.lmu" % m) for m in map_ids]
    tandas = max(1, min(len(rutas), os.cpu_count() or 1))
    hallado = set()
    for parte in in_parallel(
            lambda suyas: set().union(*(barrido(lcf.Map(r)) for r in suyas)),
            [rutas[k::tandas] for k in range(tandas)]):
        hallado |= parte
    return hallado


def comandos_de_las_tropas(db):
    """The commands of each troop page of the LDB, with the battle branches
    translated to the map's —see `RAMA_DE_PELEA`—, for the sweeps that look
    for variables and skill pairs. **It does not filter**: the sweep is a
    superset, like the maps', whether the page compiles or not."""
    from rpgmaker import lcf
    for tropa in db.troops.values():
        for pagina in tropa.pages:
            yield [lcf.EventCommand(RAMA_DE_PELEA.get(c.code, c.code),
                                    c.indent, c.string, c.parameters)
                   for c in pagina.commands]


def variables_de_comandos(comandos):
    """The variables these commands name: the `variables_de` sweep, which is
    also that of the test pages.

    `ChangeEventLocation` with the cell in two variables came in on
    2026-09-18, when the test page started using it. In the game they are
    129 and add none: measured, all their variables are already named by
    another command.
    """
    ids = set()
    for cmd in comandos:
        p = cmd.parameters
        if cmd.code == CONTROL_VARS and len(p) >= 7:
            if p[0] == 0:
                ids.add(p[1])
            elif p[0] == 1:
                ids.update(range(p[1], p[2] + 1))
            if p[4] == VAR_VARIABLE:
                ids.add(p[5])
        elif cmd.code == COND_RAMA and len(p) >= 5 \
                and p[0] == COND_VARIABLE:
            ids.add(p[1])
            if p[2] == 1:
                ids.add(p[3])
        elif cmd.code == KEY_INPUT_PROC and p:
            ids.add(p[0])
        elif cmd.code == TIMER_OPERATION and len(p) >= 3 \
                and p[0] == TIMER_PONER \
                and p[1] != TIMER_SEGUNDOS_FIJOS:
            ids.add(p[2])
        elif cmd.code == CHANGE_EVENT_LOCATION and len(p) >= 4 \
                and p[1] == LUGAR_POR_VARIABLE:
            ids.update((p[2], p[3]))
        elif cmd.code == STORE_TERRAIN_ID and len(p) >= 4:
            ids.add(p[3])
            if p[0] == 1:
                ids.update((p[1], p[2]))
        elif cmd.code in (MEMORIZE_LOCATION, RECALL_TO_LOCATION) \
                and len(p) >= 3:
            ids.update(p[:3])
    return ids


COMUNES = {}            # RM2k common event -> its commands

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
# changed —the ROM runs it from `menu_pantalla`, see `comunes_del_equipo` in
# tools/runtime/equipo_desde_eventos.s—. It is what the droid tutorial says:
# "these abilities become available once you equip a particular component and
# exit the menu".
#
# What is left out: a page's `ChangeEquipment` on the actor the event looks
# at does not run it again. In the game there is none on 18.
COMUNES_DEL_EQUIPO = {}
# The `rpg::CommonEvent` `trigger` that runs in parallel.
COMUN_PARALELO = 4
# The end of a block of commands: the empty line that closes each branch.
FIN_DE_BLOQUE = 10


def es_comun_del_equipo(trigger, comandos):
    """Whether a common event is one of `COMUNES_DEL_EQUIPO`'s: parallel,
    with a switch, and with nothing but `ChangeSkills` and branches on an
    actor's equipment —with their `else`, their closer and the block
    ends—."""
    tipo, con_switch, _switch = trigger
    permitidos = (CHANGE_SKILLS, COND_RAMA, COND_SINO, COND_FIN,
                  FIN_DE_BLOQUE)
    return (tipo == COMUN_PARALELO and con_switch and comandos
            and all(c.code in permitidos for c in comandos)
            and all(c.parameters[:1] == [COND_ACTOR]
                    and c.parameters[2:3] == [COND_ACTOR_EQUIPO]
                    for c in comandos if c.code == COND_RAMA))


def indexar_comunes(game_dir):
    """Leaves in `COMUNES` the commands of each common event, and in
    `COMUNES_DEL_EQUIPO` the ones that are of that kind.

    The converter and the tests that compile pages call it before compiling
    anything, same as `indexar_variables`: `CallEvent` compiles them in
    place, so without the database loaded none compiles.
    """
    db = base_de_datos(game_dir)
    COMUNES.clear()
    COMUNES.update(db.common_events)
    COMUNES_DEL_EQUIPO.clear()
    for numero, trigger in sorted(db.common_event_triggers.items()):
        if es_comun_del_equipo(trigger, db.common_events.get(numero)):
            COMUNES_DEL_EQUIPO[trigger[2]] = numero
    return COMUNES


def compilar_comun_del_equipo(numero):
    """The body of a `COMUNES_DEL_EQUIPO` common event as a loose page, with
    its `OP_DONE`: what the ROM runs when closing the menu. It needs no map
    nor texts —it does not use them—, and if it does not compile it is a
    converter bug: `es_comun_del_equipo` only lets through what always
    compiles.
    """
    codigo = compilar_pagina(_Comandos(COMUNES[numero]), lambda _m: None)
    if codigo is None:
        raise SystemExit("common event %d is an equipment one and does not "
                         "compile" % numero)
    return codigo


# What the two actor questions of `ConditionalBranch` need to know from the
# LDB: what each one has equipped at the start and which skills it knows.
# They go in a module index, like `COMUNES` and `VARIABLE_SLOT`: it is built
# only once before compiling anything, so all pages read the same reading of
# the LDB.
ACTOR_EQUIPO = {}       # RM2k actor -> its five slots, in the order of
                        # `constantes.RANURAS_EQUIPO`
ACTOR_SABE = {}         # RM2k actor -> the skills it knows
_ACTORES_INDEXADOS = []


def indexar_actores(game_dir):
    """Leaves in `ACTOR_EQUIPO` and `ACTOR_SABE` what the LDB says about
    each actor.

    Without this the interpreter would answer that nobody has anything
    equipped and that nobody knows anything, **silently and on one side
    only**, which is the failure mode `AGENTS.md` names. That is why there is
    a list that says whether it was called and `OP_IF_ACTOR` looks at it.
    """
    db = base_de_datos(game_dir)
    ACTOR_EQUIPO.clear()
    ACTOR_SABE.clear()
    ACTOR_EQUIPO.update({a: tuple(act.initial_equipment)
                         for a, act in db.actors.items()})
    ACTOR_SABE.update({a: reglas.aprendidas_de(db, a)
                       for a in db.actors})
    _ACTORES_INDEXADOS[:] = [True]
    return dict(ACTOR_EQUIPO)


# The terms the inn's greeting is built with. They are the game's and not
# ours —ABL charges in "Cr"— so they come from the LDB and not from a literal,
# for the same reason as the title screen's. They go in a module index like
# `ACTOR_EQUIPO`: the converter builds it once before compiling anything.
#
# The two sets of terms are `ShowInn`'s `inn_type`: 0 set A and 1 set B.
TERMINOS_POSADA = {}
_TERMINOS_DE_POSADA = ("greeting_1", "greeting_2", "greeting_3", "accept",
                       "cancel")


def indexar_terminos(game_dir):
    """Leaves in `TERMINOS_POSADA` the inn's terms and the gold's.

    Without this `ShowInn` does not compile —and says so—, instead of
    building the greeting with made-up words: the price and the currency are
    the only thing the player is going to read to decide.
    """
    from rpgmaker import lcf
    db = base_de_datos(game_dir)
    terminos = db.secciones["terms"]
    TERMINOS_POSADA.clear()
    TERMINOS_POSADA["gold"] = lcf.campo(terminos, "gold")
    for tipo, letra in ((0, "a"), (1, "b")):
        TERMINOS_POSADA[tipo] = tuple(
            lcf.campo(terminos, "inn_%s_%s" % (letra, nombre))
            for nombre in _TERMINOS_DE_POSADA)
    return dict(TERMINOS_POSADA)


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
HABILIDAD_RANURA = {}   # (actor, skill) -> slot
# The ceiling: the bits live in `FAR_HAB`, which has 256 bytes in the far RAM
# map. Today the game uses far fewer; if some day they are not enough, the
# converter stops instead of overwriting the neighbor.
HABILIDAD_RANURAS_MAX = 256 * 8
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


def pares_de_habilidad_de_comandos(comandos):
    """The (actor, skill) pairs these commands name: the
    `pares_de_habilidad` sweep, which is also that of the test pages.

    Only the forms that compile —fixed actor and constant skill—: a pair that
    comes in a variable cannot be indexed, and those commands do not compile.
    None in the game does it."""
    pares = set()
    for cmd in comandos:
        p = cmd.parameters
        if cmd.code == CHANGE_SKILLS and len(p) >= 5 \
                and p[0] == 1 and p[3] == 0:
            pares.add((p[1], p[4]))
        elif cmd.code == COND_RAMA and len(p) >= 4 and p[0] == COND_ACTOR \
                and p[2] == COND_ACTOR_HABILIDAD:
            pares.add((p[1], p[3]))
    return pares


def _pares_del_mapa(game_map):
    """The `pares_de_habilidad` sweep over one map."""
    pares = set()
    for evento in game_map.events:
        for page in evento.pages:
            pares |= pares_de_habilidad_de_comandos(page.commands)
    return pares


def pares_de_habilidad(game_dir, extra=()):
    """Each (actor, skill) pair the game can look at, with its slot.

    See `HABILIDAD_RANURA`. The ones naming an actor or a skill the LDB does
    not have are discarded: RM2k ignores them with a warning, and here they
    do not compile."""
    db = base_de_datos(game_dir)
    pares = set(extra)
    for numero, actor in db.actors.items():
        pares |= {(numero, s) for _nivel, s in actor.skills if s}
    pares |= barrer_los_mapas(game_dir, mapas_del_juego(game_dir),
                              _pares_del_mapa)
    for comandos in db.common_events.values():
        pares |= pares_de_habilidad_de_comandos(comandos)
    # And the troops' pages, which since 2026-09-21 run in the battle. Today
    # they add no pair —the ones the systems teach are already named by some
    # map—, but without this the first one that is not would not compile.
    for comandos in comandos_de_las_tropas(db):
        pares |= pares_de_habilidad_de_comandos(comandos)
    pares = {(a, s) for a, s in pares if a in db.actors and s in db.skills}
    return {par: ranura for ranura, par in enumerate(sorted(pares))}


def indexar_habilidades(game_dir, extra=()):
    """Leaves in `HABILIDAD_RANURA` the whole game's index. The converter
    calls it before compiling anything, like `indexar_variables`."""
    HABILIDAD_RANURA.clear()
    HABILIDAD_RANURA.update(pares_de_habilidad(game_dir, extra))
    if len(HABILIDAD_RANURA) > HABILIDAD_RANURAS_MAX:
        raise SystemExit("there are %d skill pairs and `FAR_HAB` holds %d"
                         % (len(HABILIDAD_RANURA), HABILIDAD_RANURAS_MAX))
    return dict(HABILIDAD_RANURA)


def ranura_de_habilidad(actor, habilidad):
    if (actor, habilidad) not in HABILIDAD_RANURA:
        raise NoSePuede("the pair actor %d, skill %d has no slot"
                        % (actor, habilidad))
    return HABILIDAD_RANURA[(actor, habilidad)]


def indexar_variables(game_dir, extra=()):
    """Leaves in `VARIABLE_SLOT` the whole game's index. The converter and
    the tests that compile pages call it before compiling anything; it takes
    a third of a second to read the 328 maps."""
    VARIABLE_SLOT.clear()
    VARIABLE_SLOT.update(variables_de(game_dir, None, extra))
    return dict(VARIABLE_SLOT)


def ranura_de_variable(numero):
    if numero not in VARIABLE_SLOT:
        raise NoSePuede("variable %d has no slot in this ROM" % numero)
    ranura = VARIABLE_SLOT[numero]
    if ranura > VAR_RANURA_MAX:
        # The slot is a byte, and far RAM has room for 256.
        raise NoSePuede("slot %d does not fit in a byte: see VAR_RANURA_MAX"
                        % ranura)
    return ranura


def escritura_pide_refresco(numero, eventos_mapa):
    """The `VAR_REFRESCO` bit for a write to variable `numero`.

    It is `SetNeedRefreshForVarChange` resolved at compile time: only the
    variables some page condition of the map looks at ask for a refresh.
    **Without the map it is always asked for**, which is what the port did
    before this and the only honest thing when it is not known who looks at
    what.
    """
    if eventos_mapa is None or eventos_mapa.vars_observadas is None:
        return VAR_REFRESCO     # without the map, or after leaving it
    return VAR_REFRESCO if numero in eventos_mapa.vars_observadas else 0


def azar_siguiente(x):
    """The xorshift step, in sixteen bits."""
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x

# RM2k's gold cap: `Game_Party::GainGold` clamps to `MaxGoldValue()`, which
# by default is this.
ORO_MAX = 999999

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
ELEGIR_MAX = 4

# The cursor, and what is put in front of the options that do not have it so
# the text does not shift from line to line.
ELEGIR_CURSOR = ">"
ELEGIR_SANGRIA = " "


def opciones_de_eleccion(comandos, i):
    """The options of the `ShowChoice` at `comandos[i]`.

    It is `Game_Interpreter::GetChoices`: it walks forward from the next
    command, gathers the `ShowChoiceOption`s on its same indentation and
    stops at the `ShowChoiceEnd`. Returns (index, text).
    """
    if i + 1 >= len(comandos):
        return []
    nivel = comandos[i + 1].indent
    salida = []
    for cmd in comandos[i + 1:]:
        if cmd.indent != nivel:
            continue
        if cmd.code == SHOW_CHOICE_END:
            break
        if cmd.code == SHOW_CHOICE_OPTION and cmd.parameters \
                and cmd.parameters[0] < ELEGIR_MAX:
            salida.append((cmd.parameters[0], cmd.string or ""))
    return salida


def cuadros_de_eleccion(opciones, mensajes):
    """One `mensajes` offset per option, with the cursor on its line.

    The boxes are the same except for the cursor. `Mensajes` deduplicates by
    content, so the common lines are not stored twice: what is paid is one
    small box per option.
    """
    textos = [t for _, t in opciones]
    return [mensajes.agregar(
                [(ELEGIR_CURSOR if k == n else ELEGIR_SANGRIA) + " " + t
                 for k, t in enumerate(textos)])
            for n in range(len(textos))]


def bytes_de_rama(cmd):
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
        raise NoSePuede("a branch with no operands")
    if p[0] == COND_SWITCH:
        numero = p[1]
        if not 0 <= numero < SWITCH_MAX:
            raise NoSePuede("switch %d out of the bitmap" % numero)
    elif p[0] == COND_ORO:
        numero = p[1]
        if not 0 <= numero <= 0xFFFF:
            # The operand travels in a word. In this game the biggest is
            # 2000, so nothing is lost; if some day a bigger one appears,
            # this says so instead of comparing it wrong.
            raise NoSePuede("gold comparison against %d, which does not fit "
                            "in a word" % numero)
    elif p[0] == COND_ITEM:
        numero = p[1]
        if not 0 <= numero < ITEMS_N:
            raise NoSePuede("item %d is not in the LDB" % numero)
    elif p[0] == COND_ACTOR:
        numero = p[1]
        if not 0 <= numero <= 0xFFFF:
            raise NoSePuede("actor %d out of range" % numero)
        if p[2] == COND_ACTOR_EN_GRUPO:
            # "Is in the party" has no polarity: the branch below is the
            # `else`.
            return bytes([OP_IF, COND_ACTOR, numero & 0xFF, numero >> 8,
                          0, 0, 0])
        if p[2] in (COND_ACTOR_HABILIDAD, COND_ACTOR_EQUIPO):
            if len(p) < 4:
                raise NoSePuede("an actor branch without the item or the "
                                "skill")
            if not 0 <= numero <= 0xFF:
                # The actor travels in a byte: see OP_IF_ACTOR. The LDB has 60.
                raise NoSePuede("actor %d, which does not fit in a byte" % numero)
            if _ACTORES_INDEXADOS and numero not in ACTOR_EQUIPO:
                # The ROM's tables go from 0 to the LDB's last actor, so an
                # extra number would be read out of the table. RM2k warns and
                # goes through the `else`; here it does not compile, which is
                # what this port does with everything it cannot answer. No
                # page of the game does it: it is checked only when the index
                # is loaded, so as not to change the answer for whoever
                # compiles without calling `indexar_actores`.
                raise NoSePuede("actor %d is not in the LDB" % numero)
            dato = p[3]
            if p[2] == COND_ACTOR_HABILIDAD:
                # The skill travels as its pair's slot: it is the bit the ROM
                # looks at, and that way it does not have to search. See
                # `HABILIDAD_RANURA`.
                dato = ranura_de_habilidad(numero, dato)
            if not 0 <= dato <= 0xFFFF:
                raise NoSePuede("an actor branch against %d, which does not "
                                "fit in a word" % dato)
            return bytes([OP_IF_ACTOR, p[2], numero,
                          dato & 0xFF, dato >> 8, 0, 0])
        raise NoSePuede("of the hero we know whether it is in the party, "
                        "whether it knows a skill and what it has equipped, "
                        "and not %d" % p[2])
    elif p[0] == COND_VARIABLE:
        if len(p) < 5:
            raise NoSePuede("a variable branch with no operands")
        ranura = ranura_de_variable(p[1])
        if p[2] == 0:
            clase, valor = VAR_CONSTANTE, p[3]
            if not -0x8000 <= valor <= 0x7FFF:
                raise NoSePuede("comparison against %d, which does not fit "
                                "in a signed word" % valor)
        elif p[2] == 1:
            clase, valor = VAR_VARIABLE, ranura_de_variable(p[3])
        else:
            raise NoSePuede("variable branch against something we do not "
                            "know")
        if not 0 <= p[4] <= CMP_DISTINTO:
            raise NoSePuede("comparison %d does not exist" % p[4])
        return bytes([OP_IF_VAR, ranura, clase, p[4], valor & 0xFF,
                      (valor >> 8) & 0xFF, 0, 0])
    else:
        raise NoSePuede("branch on a condition we do not know how to do")
    return bytes([OP_IF, p[0], numero & 0xFF, numero >> 8,
                  1 if p[2] else 0, 0, 0])


class Tropas:
    """The troops the compiled battles ask for, to know which tables to emit.

    Sibling of `Temas`, with a difference that matters: **the bytecode does
    not depend on it**. `Temas` numbers and the opcode carries the number;
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
        # troop. See tools/port/escena.py.
        self.fondos = {}

    def pedir(self, numero, fondo=None):
        if numero not in self.ids:
            self.ids.append(numero)
        if fondo and numero not in self.fondos:
            self.fondos[numero] = fondo     # a name, or FONDO_DEL_LUGAR
        return numero


# --- the troops' event pages -------------------------------------------------
#
# `Game_Interpreter_Battle`: each troop brings its pages, and the battle runs
# them **with the same interpreter as the maps**, `correr_codigo`, so they are
# compiled with the same `compilar_pagina`. The only thing that changes is
# what is accepted: see `TROPA_COMANDOS`.
#
# When each one runs is decided by the ROM and it is copied from
# `Scene_Battle_Rpg2k`; see `ba_pag_probar` in tools/runtime/batalla_tropa.s.

# The battle's three branch commands, with their map twin. Of the six
# questions of `CommandConditionalBranchBattle` the game uses **only two** —the
# switch and the variable, in 1108 branches of 295 distinct bodies, measured
# on 2026-09-21— and those have the operands in the same place as the map's:
# `[kind, number, polarity or value kind, value, comparison, else]`. So they
# are translated to the map's code and compile to OP_IF and OP_IF_VAR without
# a new opcode. The other four —whether an actor or an enemy can act, whom it
# targets, which command it gave— ask for battle state and do not compile.
RAMA_DE_PELEA = {13310: COND_RAMA, 23310: COND_SINO, 23311: COND_FIN}
RAMA_DE_PELEA_CLASES = (COND_SWITCH, COND_VARIABLE)

# `ShowHiddenMonster`, which only exists in battle: the troop member in that
# place —from 0, in troop order— stops being hidden. See OP_SHOW_ENEMY and
# `ba_mostrar_oculto`.
SHOW_HIDDEN_MONSTER = 13150

# What a troop page can do in this port. **It is a list of the ones that do,
# not of the ones that do not**, on purpose: almost everything that compiles
# on a map assumes the map —a teleport, a route, a tint, a choice, which opens
# the map's window— and inside the battle it would do something else without
# warning.
#
# `PlaySound` sounds in the battle's audio package if its effect fits there
# —see `PaginasDeTropa.compilar`—, and `ShakeScreen` moves the scene: see
# `ba_sacudir`. Its wait, an OP_DELAY, is counted by `ba_pag_paso`.
#
# The ones left out that the game uses, in case someone wants to add them:
# `ChangeHP` and `FullHeal` —in battle HP lives in `BA_UNO` and `FAR_HP` is
# overwritten when closing it—, `ChangePartyMembers`, `ChangeEquipment`,
# `Wait`, `TintScreen` and five of the six that only exist in battle.
TROPA_COMANDOS = ({END, SHOW_MESSAGE, SHOW_MESSAGE_2, CONTROL_SWITCHES,
                   CONTROL_VARS, CHANGE_SKILLS, CHANGE_GOLD, CHANGE_ITEMS,
                   PLAY_SOUND, SHAKE_SCREEN, SHOW_HIDDEN_MONSTER,
                   COND_RAMA, COND_SINO, COND_FIN} | IGNORABLES)

# Which triggers the ROM knows how to look at, with their bit in
# `tpag_flags`: RM2k's six. The three from 2003 —an actor's or an enemy's
# turn, fatigue and an actor's command— do not exist in a 2000 game, and a
# page that asked for them is left out.
TROPA_DISPARO_SWITCH_A = 0x01
TROPA_DISPARO_SWITCH_B = 0x02
TROPA_DISPARO_VARIABLE = 0x04
TROPA_DISPARO_TURNO = 0x08
TROPA_DISPARO_ENEMIGO = 0x10
TROPA_DISPARO_ACTOR = 0x20
TROPA_DISPAROS = {"switch_a": TROPA_DISPARO_SWITCH_A,
                  "switch_b": TROPA_DISPARO_SWITCH_B,
                  "variable": TROPA_DISPARO_VARIABLE,
                  "turn": TROPA_DISPARO_TURNO,
                  "enemy_hp": TROPA_DISPARO_ENEMIGO,
                  "actor_hp": TROPA_DISPARO_ACTOR}
# How many pages of a troop the battle notes as "already ran this turn", one
# byte each in `BA_PAG_HECHA`. It is a far RAM cap and not the game's: the
# converter stops if any troop goes over.
TROPA_PAGINAS_MAX = 32

# The triggers that carry a **header**: the turn and HP numbers do not go in
# per-page tables in bank 1 —which no longer has room for ten bytes for each
# of the five hundred— but in front of the page's code, in `tropa_codigo`,
# which is in RODATA. See `cabecera_de_tropa` and `ba_pag_cabecera`.
TROPA_CON_CABECERA = (TROPA_DISPARO_TURNO | TROPA_DISPARO_ENEMIGO
                      | TROPA_DISPARO_ACTOR)
TROPA_CABECERA_BYTES = 10


def cabecera_de_tropa(disparo):
    """The ten bytes that go in front of the code of a page that looks at
    the turn or the HP: the turn's base and multiple, a word each, and the
    enemy's place, the actor and their ranges, a byte each. Empty if it looks
    at none of that. The order is `BA_COND`'s in
    tools/runtime/ram_lejana.s."""
    if not disparo.flags & TROPA_CON_CABECERA:
        return b""
    d = disparo
    salida = bytes([d.turno_base & 0xFF, d.turno_base >> 8,
                    d.turno_mult & 0xFF, d.turno_mult >> 8,
                    d.enemigo, d.enemigo_min, d.enemigo_max,
                    d.actor, d.actor_min, d.actor_max])
    assert len(salida) == TROPA_CABECERA_BYTES
    return salida


def comandos_de_tropa(comandos):
    """The commands of a troop page as if they were a map's, or `NoSePuede`
    if any is not in `TROPA_COMANDOS`.

    Returns copies: the database's are shared by all the troops that have
    the same page, and translating them in place would leave them translated
    for whoever reads them later."""
    from rpgmaker import lcf
    salida = []
    for cmd in comandos:
        codigo = RAMA_DE_PELEA.get(cmd.code, cmd.code)
        if cmd.code == 13310 and (not cmd.parameters
                                  or cmd.parameters[0]
                                  not in RAMA_DE_PELEA_CLASES):
            raise NoSePuede("a battle branch that asks about the battle")
        if codigo not in TROPA_COMANDOS:
            raise NoSePuede("command %d does not run in a troop page"
                            % cmd.code)
        salida.append(lcf.EventCommand(codigo, cmd.indent, cmd.string,
                                       cmd.parameters))
    return salida


# The trigger of a troop page, with what the ROM reads from each one. The
# fields of what the page does not look at go at zero.
Disparo = collections.namedtuple("Disparo", (
    "flags", "switch_a", "switch_b", "ranura", "valor",
    "turno_base", "turno_mult", "enemigo", "enemigo_min", "enemigo_max",
    "actor", "actor_min", "actor_max"))


def disparo_de_tropa(pagina):
    """The `Disparo` of a troop page, or None if it looks at something the
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
    if not pagina.activos:
        return None
    if any(a not in TROPA_DISPAROS for a in pagina.activos):
        return None
    c = pagina.condicion
    flags = 0
    for a in pagina.activos:
        flags |= TROPA_DISPAROS[a]
    switch_a = c["switch_a_id"] if "switch_a" in pagina.activos else 0
    switch_b = c["switch_b_id"] if "switch_b" in pagina.activos else 0
    for s in (switch_a, switch_b):
        if not 0 <= s < SWITCH_MAX:
            return None
    ranura, valor = 0, 0
    if "variable" in pagina.activos:
        valor = c["variable_value"]
        if not -0x8000 <= valor <= 0x7FFF:
            return None
        try:
            ranura = ranura_de_variable(c["variable_id"])
        except NoSePuede:
            return None
    base, mult = 0, 0
    if "turn" in pagina.activos:
        base, mult = c["turn_b"], c["turn_a"]
        if not (0 <= base <= 0xFFFF and 0 <= mult < 0x8000):
            return None     # `ba_div` requires the divisor below 32768
    enemigo, e_min, e_max = 0, 0, 0
    if "enemy_hp" in pagina.activos:
        enemigo, e_min, e_max = (c["enemy_id"], c["enemy_hp_min"],
                                 c["enemy_hp_max"])
        if not (0 <= enemigo < 256 and 0 <= e_min <= 100
                and 0 <= e_max <= 100):
            return None
    actor, a_min, a_max = 0, 0, 0
    if "actor_hp" in pagina.activos:
        actor, a_min, a_max = (c["actor_id"], c["actor_hp_min"],
                               c["actor_hp_max"])
        if not (0 <= actor < 256 and 0 <= a_min <= 100
                and 0 <= a_max <= 100):
            return None
    return Disparo(flags, switch_a, switch_b, ranura, valor, base, mult,
                   enemigo, e_min, e_max, actor, a_min, a_max)


class PaginasDeTropa:
    """The pages of the cartridge's troops, compiled and deduplicated.

    `cuerpos` is the code of all of them, one after the other and **each
    distinct body only once**: the game copies its systems' pages into every
    troop —4588 pages and 295 distinct bodies—, so the key is the already
    compiled bytecode, same as `Materiales` with the map's blocks.

    The messages go to **their own block**, `mensajes_tropa`, and not to the
    maps': `OP_MESSAGE` carries a sixteen-bit offset and the maps' block of
    the test cartridge is already around 65 KB. The battle draws them on its
    screen and not in the map's window, so reading them from elsewhere costs
    it nothing.
    """

    def __init__(self):
        self.mensajes = Mensajes()
        self.cuerpos = bytearray()
        self.donde = {}             # bytecode -> offset in `cuerpos`
        self.por_tropa = {}         # troop -> [(Disparo, ofs)]
        self.paginas = 0            # how many were looked at
        self.afuera = 0             # and how many did not get in

    def compilar(self, numero, tropa, temas=None):
        """A troop's pages. With `temas`, a `PlaySound` is compiled with its
        effect, which counts for **the battle's audio package** —the one
        loaded when the page runs, see `PAQUETE_BATALLA`— and not for the
        map's; and it goes into it only if it is in `se_de_tropa_al_paquete`
        (snes_music.py): otherwise it is asked for and does not sound, like a
        route one that does not fit. Without `temas` it is accepted and not
        done."""
        suyas = []
        anterior = temas.mapa if temas is not None else None
        if temas is not None:
            temas.mapa = PAQUETE_BATALLA
        try:
            for pagina in tropa.pages:
                self.paginas += 1
                disparo = disparo_de_tropa(pagina)
                codigo = None
                if disparo is not None:
                    try:
                        comandos = comandos_de_tropa(pagina.commands)
                    except NoSePuede:
                        comandos = None
                    if comandos is not None:
                        codigo = compilar_pagina(_Comandos(comandos),
                                                 lambda _mapa: None,
                                                 self.mensajes, temas=temas)
                if codigo is None:
                    self.afuera += 1
                    continue
                # The header goes right in front and is part of the key: two
                # pages with the same code and another turn are two bodies.
                # The offset noted is the code's, so the ROM finds the header
                # `TROPA_CABECERA_BYTES` before it.
                cabecera = cabecera_de_tropa(disparo)
                clave = cabecera + bytes(codigo)
                if clave not in self.donde:
                    self.donde[clave] = len(self.cuerpos) + len(cabecera)
                    self.cuerpos += clave
                suyas.append((disparo, self.donde[clave]))
        finally:
            if temas is not None:
                temas.mapa = anterior
        self.por_tropa[numero] = suyas
        return suyas


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
# can do without floating point: see `enc_umbrales_de_paso`.

# Every how many steps, by default, if the node does not carry the chunk
# (liblcf: rpg::MapInfo::encounter_steps).
ENC_PASOS_DEFECTO = 25

# The tree node type that is an area. See `lcf.TreeMap.map_types`.
TREE_AREA = 2

# `UpdateEncounterSteps`' table, as (minimum ratio, pmod exponent): easyrpg's
# eight `pmod`s are powers of two —1/16, 1/8, 1/4, 1/2, 2, 4, 8, 16— so here
# they go as shifts and the math needs no floats. The ninth row there is
# `{INT_MAX, 16.0}`, that is a cap that is never reached: the `while` does not
# go past the last of these.
ENC_TABLA = ((0, -4), (20, -3), (40, -2), (60, -1),
             (100, 1), (140, 2), (160, 3), (180, 4))

# The `encounter_rate` the accumulated goes up by: the terrain's, which in
# this game is 100 on the 53 maps with encounters. See above.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ENC_RATE = 100

# The seed of the encounters' randomness. It differs from `AZAR_SEMILLA` and
# from `BATALLA_SEMILLA` on purpose, and for the same reason as that one:
# walking does not advance the map's randomness —a random `ControlVars` has
# to give the same with and without encounters—. All that is asked of it is
# not to be zero —the xorshift gets stuck— and to be the same in
# `Encuentros` and in the ROM.
ENC_SEMILLA = 0x5A17


def enc_base(pasos):
    """The formula's `1 / encounter_steps`, in 1/65536.

    A step's chance is `pmod / pasos`, and `pmod` is a power of two: if the
    quotient is precomputed here, on the console what is left is a shift and
    a sixteen-bit comparison, with no division. **The truncation is part of
    the contract**: both sides use this same number.

    Zero means off, which is what `encounter_steps` 0 means in RM2k.
    """
    return 0 if pasos <= 0 else 0x10000 // pasos


def enc_umbrales_de_paso(pasos):
    """At which step each row of `ENC_TABLA` is crossed, counting from zero.

    There the comparison is `ratio >= fila`, with `ratio = acumulado / pasos`
    integer and `acumulado = 100 * n`. Since the row is an integer,

        acumulado / pasos >= fila   <=>   100 * n >= fila * pasos

    that is `n >= ceil(fila * pasos / 100)`, which is what is emitted: seven
    bytes per map and not a single division on the console. The first row is
    0 and is not needed.
    """
    return [-(-fila * pasos // ENC_RATE) for fila, _ in ENC_TABLA[1:]]


def enc_umbral(base, idx):
    """The step's chance, in 1/65536, or None if it is "always".

    `pmod` shifts `base` one way or the other. With small steps —the ones
    `ChangeEncounterSteps` sets, or a test ROM— `pmod / pasos` can go past 1,
    and there RM2k has certainty: `PercentChance` with `rate >= 1` always
    says yes. On the console that is the shift's carry.
    """
    corrimiento = ENC_TABLA[idx][1]
    if corrimiento < 0:
        return base >> -corrimiento
    valor = base << corrimiento
    return None if valor >= 0x10000 else valor


def zonas_de_encuentro(tree, map_id, ancho, alto):
    """A map's zones: its own and one per area that hangs from it.

    A zone is (left, top, right, bottom, troops) with the rectangle
    **half-open**, which is what `Rect::IsOutOfBounds` says: inside is
    `l <= x < r` and `t <= y < b`. The map's covers the whole map.

    The order is `GetEncountersAt`'s, which walks the tree by index: in this
    game no map has troops of its own **and** areas —measured—, so putting
    its own first cannot change which troop comes out.
    """
    zonas = []
    if tree.encounters.get(map_id):
        zonas.append((0, 0, ancho, alto, list(tree.encounters[map_id])))
    for i in sorted(tree.map_types):
        if (tree.map_types[i] == TREE_AREA and tree.map_parents.get(i) == map_id
                and tree.encounters.get(i)):
            izq, arr, der, aba = tree.area_rect[i]
            zonas.append((izq, arr, der, aba, list(tree.encounters[i])))
    return zonas


class Encuentros:
    """The encounter state of a game, the same on both sides.

    The tests use it; the ROM does the same with the tables the converter
    emits. Whoever changes it has to change `tools/runtime/` in the same
    commit: otherwise the model and the console stop being the same
    program.
    """

    def __init__(self, pasos, zonas, semilla=ENC_SEMILLA):
        self.zonas = list(zonas)
        self.poner_pasos(pasos)
        self.semilla = semilla
        self.reiniciar()

    def poner_pasos(self, pasos):
        """The map's `encounter_steps`: on entering, and
        `ChangeEncounterSteps`."""
        self.pasos = pasos
        self.base = enc_base(pasos) if self.zonas else 0
        self.umbrales = enc_umbrales_de_paso(pasos)

    def reiniciar(self):
        """The `SetTotalEncounterRate(0)` of `Game_Player::MoveTo`: every
        teleport —and every door— sets the accumulated to zero."""
        self.n = 0
        self.idx = 0
        self.pendiente = False

    def _azar(self):
        self.semilla = azar_siguiente(self.semilla)
        return self.semilla

    def paso(self):
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
        while (self.idx + 1 < len(ENC_TABLA)
               and self.n >= self.umbrales[self.idx]):
            self.idx += 1
        umbral = enc_umbral(self.base, self.idx)
        salio = umbral is None or self._azar() < umbral
        if salio:
            self.n = 0
            self.idx = 0
            self.pendiente = True
        return salio

    def candidatas(self, x, y):
        """The troops that can be fought on that cell: the map's plus those
        of each area covering it. It is `GetEncountersAt`."""
        salida = []
        for izq, arr, der, aba, tropas in self.zonas:
            if izq <= x < der and arr <= y < aba:
                salida += tropas
        return salida

    def elegir(self, x, y):
        """The next frame's `PrepareEncounter`: which troop is fought, or
        None if there is none on that cell."""
        self.pendiente = False
        tropas = self.candidatas(x, y)
        if not tropas:
            return None
        return tropas[self._azar() % len(tropas)]


def tropa_de_encuentro(cmd):
    """The troop number of an `EnemyEncounter`, or `NoSePuede`.

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
      Over screen, and since 2026-09-13 it is emitted as `BATALLA_PERDER` in
      the defeat's destination. The ROM notes it before fighting and, if it
      loses, shows the Game Over screen and from there goes back to boot
      —that is to the title screen, with the saved game waiting in SRAM—:
      see tools/runtime/game_over.s and what it still does not do in
      `workflow/divergencias/lo-que-la-pantalla-de-game-over-no-modela.md`.
      What is not done is what was done before 2026-09-13, which was not
      compiling the page: it cost 15, among them the Rat Tracks boss.

    The backdrop is not looked at here: `fondo_de_encuentro` gets it.
    """
    p = cmd.parameters
    if len(p) < 6:
        raise NoSePuede("EnemyEncounter with no operands")
    if p[0] != 0:
        raise NoSePuede("EnemyEncounter with the troop in a variable")
    if not 0 < p[1] <= 0xFFFF:
        raise NoSePuede("EnemyEncounter of troop %d" % p[1])
    if p[3] == BATALLA_ESCAPE_CORTA:
        raise NoSePuede("EnemyEncounter that cuts the page on escape")
    return p[1]


def fondo_de_encuentro(cmd):
    """The battle backdrop of an `EnemyEncounter`: the name it carries,
    `FONDO_DEL_LUGAR`, or "" if none.

    Parameter `[2]` of `CommandEnemyEncounter` says where the backdrop comes
    from: 1 is "the one this command says", which is what 49 of the game's 51
    battles do, with the name in the string —empty is no backdrop—; 0 is the
    local one, `Game_Map::SetupBattle`, which is what the other two do (on
    105 and on 141), and the ROM resolves it when the battle starts. 2 is
    RM2k3's.
    """
    p = cmd.parameters
    if len(p) > 2 and p[2] == BATALLA_FONDO_DEL_COMANDO:
        return cmd.string
    if len(p) > 2 and p[2] == BATALLA_FONDO_DEL_LUGAR:
        return FONDO_DEL_LUGAR
    return ""


def fondos_de_comandos(comandos):
    """The battle backdrops these commands name: the `fondos_nombrados`
    sweep."""
    nombres = set()
    for cmd in comandos:
        if cmd.code == ENEMY_ENCOUNTER:
            fondo = fondo_de_encuentro(cmd)
            if fondo and fondo is not FONDO_DEL_LUGAR:
                nombres.add(fondo)
        elif cmd.code == CHANGE_BATTLE_BG and cmd.string:
            nombres.add(cmd.string)
    return nombres


def _fondos_del_mapa(game_map):
    """The `fondos_nombrados` sweep over one map."""
    nombres = set()
    for evento in game_map.events:
        for page in evento.pages:
            nombres |= fondos_de_comandos(page.commands)
    return nombres


def fondos_nombrados(game_dir):
    """The battle backdrops some command of the game names: the
    `EnemyEncounter`s and `ChangeBattleBG`s of all the maps, of the common
    events and of the troops' pages, whether they compile or not. The map
    tree's and the terrains' are added by `escena.fondos_del_juego`.
    """
    db = base_de_datos(game_dir)
    nombres = barrer_los_mapas(game_dir, mapas_del_juego(game_dir),
                               _fondos_del_mapa)
    for comandos in db.common_events.values():
        nombres |= fondos_de_comandos(comandos)
    for tropa in db.troops.values():
        for pagina in tropa.pages:
            nombres |= fondos_de_comandos(pagina.commands)
    return nombres


def actor_de_blanco(p, que):
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
    raise NoSePuede("%s with the actor in a variable" % que)


def con_destino(pieza, destino):
    """The same piece with the destination set in its last two bytes."""
    return pieza[:-2] + bytes([destino & 0xFF, destino >> 8])


def _parchear(piezas, abierta, destino):
    """Puts `destino` in the open piece of the branch stack. An entry is the
    piece's index, with the destination in its last two bytes, or (index,
    offset) for a piece with more than one destination: `OP_CELL_TEST`."""
    if not isinstance(abierta, tuple):
        piezas[abierta] = con_destino(piezas[abierta], destino)
        return
    i, donde = abierta
    pieza = piezas[i]
    piezas[i] = (pieza[:donde] + bytes([destino & 0xFF, destino >> 8])
                 + pieza[donde + 2:])


# Where the two destinations go inside `OP_CELL_TEST`: see events.toml.
CELDA_DESTINO_A = 10
CELDA_DESTINO_B = 16
# The top two bits of each `OP_CELL_TEST` write, over the variable's offset:
# y instead of x, and the refresh. See `celda_probar` in
# tools/runtime/interprete_celdas.s.
CELDA_Y = 0x4000
CELDA_REFRESCO = 0x8000


def celdas_fundibles(comandos):
    """Where each "is it on the cell?" pattern that `OP_CELL_TEST` does in a
    single opcode starts: two `ControlVars` that put the x and the y of the
    same character in two variables, and two nested `ConditionalBranch`es
    —the second is the first thing inside the first— that compare one
    variable with another for equality.

    It is the pattern of the parallel pages that check whether two
    characters touch: the forty of each lap of the race, the lights of map 11
    and some two hundred more in the game. Fused, it runs in a single turn of
    the interpreter instead of four, and it is what keeps the race at 60
    frames: see `celda_probar` in tools/runtime/interprete_celdas.s.

    Only the shape is looked at here; whether the operands compile is said
    by `_pieza_de_celdas`, which is the one that emits.
    """
    def poner_celda(c):
        p = c.parameters
        return (c.code == CONTROL_VARS and len(p) >= 7 and p[0] == 0
                and p[3] == VAR_PONER and p[4] == VAR_PERSONAJE)

    def igual_a_variable(c):
        p = c.parameters
        return (c.code == COND_RAMA and len(p) >= 5 and p[0] == COND_VARIABLE
                and p[2] == 1 and p[4] == CMP_IGUAL)

    inicios = []
    i = 0
    while i + 3 < len(comandos):
        a, b, c, d = comandos[i:i + 4]
        if (poner_celda(a) and poner_celda(b)
                and a.parameters[5] == b.parameters[5]
                and igual_a_variable(c) and igual_a_variable(d)
                and a.indent == b.indent == c.indent
                and d.indent == c.indent + 1):
            inicios.append(i)
            i += 4
        else:
            i += 1
    return inicios


def _pieza_de_celdas(escrituras, ramas):
    """`OP_CELL_TEST` with the two destinations blank, built with what the
    four loose opcodes would emit —so the validations and the refresh are
    the same—, or None if it cannot be fused."""
    v1, v2 = escrituras
    r1, r2 = ramas
    for v in (v1, v2):
        if (v[0] != OP_VAR or v[3] != VAR_PERSONAJE or v[5] != 0
                or v[7] != 0 or v[6] not in (PERSONAJE_X, PERSONAJE_Y)
                or v[2] & ~VAR_REFRESCO != VAR_PONER):
            return None
    if v1[4] != v2[4]:
        return None
    for r in (r1, r2):
        if (r[0] != OP_IF_VAR or r[2] != VAR_VARIABLE or r[3] != CMP_IGUAL
                or r[5] != 0):
            return None
    def escritura(v):
        return (v[1] * 2 | (CELDA_Y if v[6] == PERSONAJE_Y else 0)
                | (CELDA_REFRESCO if v[2] & VAR_REFRESCO else 0))

    palabras = [escritura(v1), escritura(v2),
                r1[1] * 2, r1[4] * 2, 0, r2[1] * 2, r2[4] * 2, 0]
    pieza = bytes([OP_CELL_TEST, v1[4]]) + b"".join(
        bytes([w & 0xFF, w >> 8]) for w in palabras)
    assert len(pieza) == OPCODE_SIZE[OP_CELL_TEST]
    return pieza


def compilar_pagina(page, indice_de_mapa, mensajes=None, eventos_mapa=None,
                    temas=None, graficos=None, imagenes=None, tropas=None,
                    base=0, hondo=0):
    """A page's commands as bytes, or None if it cannot be done.

    `indice_de_mapa` translates the RM2k map id to the index in the ROM's
    table, and returns None for the maps that did not get into the
    cartridge: a teleport to one of those makes the page not runnable, which
    is more honest than jumping anywhere.

    `mensajes` is the ROM's text block. Without it the text boxes do not
    compile, and it is not a matter of taste: the window takes 8 KB of VRAM
    and a palette, so a ROM that does not carry it has nowhere to draw them.

    `eventos_mapa` is the map's `Eventos`, already pointed at the page's
    owner. Without it a forced route can only be on the hero: there is
    nothing to translate the RM2k id to the table's index with.

    `tropas` is the registry of the troops the cartridge is going to have to
    carry. **It does not change the bytecode** —the troop number emitted is
    RM2k's— so a ROM without a registry compiles exactly the same; the only
    thing lost is knowing which tables have to be emitted.

    `base` and `hondo` are for `CallEvent`, which is compiled **inline**: the
    called event's body is emitted in the place of the call. `base` is where
    this piece starts inside the outer page, because the branches'
    destinations are absolute; `hondo` is the nesting, which is capped. An
    inline piece **carries no `OP_DONE`**: in RM2k the called event's `END`
    returns to the caller, it does not end the page.
    """
    marca = mensajes.marca() if mensajes is not None else None
    try:
        # The branches are emitted with the destination blank and patched
        # when closing them, which is the only way: until what is inside is
        # compiled it is not known how much it takes. The stack carries the
        # nesting, so there is no need to look at the indentation as
        # `SkipToNextConditional` does —it walks the list of commands, here
        # the blocks already come properly nested—.
        piezas = []
        largo = base         # see `base`: the branches' destinations are
                             # absolute within the outer page
        pila = []            # pieces with the destination still blank
        # The options of each `ShowChoice` are gathered looking ahead, which
        # is what `GetChoices` does, so they are resolved before the loop:
        # in here the commands come one at a time and already grouped.
        comandos = list(page.commands)
        opciones_de = {id(c): opciones_de_eleccion(comandos, i)
                       for i, c in enumerate(comandos) if c.code == SHOW_CHOICE}
        # Which `EnemyEncounter`s come **without a handler block**. RM2k does
        # not emit it when the battle has no branch to write, which is
        # exactly what happens with `defeat_mode` 0: losing is the Game Over
        # screen and not a branch of the page. They are the game's 15 pages
        # this port did not compile —among them the Rat Tracks boss—, and
        # all 15 are like this: without this, accepting the Game Over left
        # them falling into "an unclosed battle". It looks ahead like a
        # `ShowChoice`'s options, because inside the loop the commands come
        # one at a time.
        sin_bloque = {id(c) for i, c in enumerate(comandos)
                      if c.code == ENEMY_ENCOUNTER
                      and (i + 1 >= len(comandos)
                           or comandos[i + 1].code not in BATALLA_HANDLERS)}
        # The four of "is it on the cell?", which go in a single opcode: see
        # `celdas_fundibles`. Each command's role —0 and 1 the writes, 2 and
        # 3 the branches— by its id, and each pattern's fused piece by its
        # first command's id, when it is emitted.
        celda_papel = {}
        for i in celdas_fundibles(comandos):
            for n in range(4):
                celda_papel[id(comandos[i + n])] = (n, id(comandos[i]))
        celda_pieza = {}
        eleg = []            # the open choices
        bat = []             # and the open battles, same as them
        bgm = [None, [], []]  # the pending `PlayBGM`, what was noted and
                              # the jumps: see `_seguir_la_salida`
        constantes = {}      # the last thing the page put in each variable,
                             # if it was a constant: see `_destino_recordado`
        for cmd, extra in agrupar(comandos):
            pedidos = temas.pedidos if temas is not None else 0
            papel = celda_papel.get(id(cmd))
            if papel is not None and papel[0] == 0:
                # It is built here and not before because the refresh
                # depends on `eventos_mapa`, which changes after a
                # `Teleport`.
                i = comandos.index(cmd)
                sueltos = comandos[i:i + 4]
                fundida = _pieza_de_celdas(
                    [_compilar(c, indice_de_mapa, mensajes, (), eventos_mapa,
                               temas, graficos, imagenes)
                     for c in sueltos[:2]],
                    [bytes_de_rama(c) for c in sueltos[2:]])
                if fundida is None:
                    for c in sueltos:
                        del celda_papel[id(c)]
                    papel = None
                else:
                    celda_pieza[id(cmd)] = len(piezas)
            if papel is not None:
                n, primero = papel
                pieza = b""
                if n == 0:
                    pieza = fundida
                if n < 2:
                    _anotar_constante(cmd, constantes)
                else:
                    pila.append((celda_pieza[primero],
                                 CELDA_DESTINO_A if n == 2
                                 else CELDA_DESTINO_B))
            elif cmd.code == ENEMY_ENCOUNTER:
                tropa = tropa_de_encuentro(cmd)
                if tropas is not None:
                    tropas.pedir(tropa, fondo_de_encuentro(cmd))
                # The song and effects the battle plays, noted in the
                # battle's package: see `audio_de_batalla`.
                audio_de_batalla(temas)
                perder_es_game_over = (len(cmd.parameters) > 4
                                       and cmd.parameters[4]
                                       == BATALLA_DERROTA_GAME_OVER)
                if id(cmd) in sin_bloque:
                    # No handlers: the battle closes right here. Winning and
                    # escaping continue with the command below —which is what
                    # RM2k does when there are no branches— and losing goes
                    # to `BATALLA_PERDER`, that is to the Game Over.
                    #
                    # **Escaping points to victory and not elsewhere**, and
                    # it is a declared approximation: the 24 battles of this
                    # form carry `escape_mode` 0 —escape forbidden—, so there
                    # the exit does not exist; here the battle lets you
                    # escape anyway, because the permission does not travel
                    # in the opcode: `ChangeEscapeAccess` is accepted and not
                    # done.
                    sigue = largo + 9
                    perder = (BATALLA_PERDER if perder_es_game_over
                              else sigue)
                    pieza = bytes([OP_BATTLE, tropa & 0xFF, tropa >> 8,
                                   sigue & 0xFF, sigue >> 8,
                                   sigue & 0xFF, sigue >> 8,
                                   perder & 0xFF, perder >> 8])
                else:
                    bat.append({"i": len(piezas), "tropa": tropa,
                                "destinos": [None, None, None],
                                "game_over": perder_es_game_over,
                                "vistas": 0, "salidas": []})
                    pieza = bytes(9)  # the room, filled in at the EndBattle
            elif cmd.code in BATALLA_HANDLERS:
                if not bat:
                    raise NoSePuede("a battle handler without its battle")
                actual = bat[-1]
                n = BATALLA_HANDLERS.index(cmd.code)
                # The previous handler's body ends here and is taken out of
                # the block with a jump to the end, patched when closing it.
                # It is the same `ShowChoiceOption` does, and for the same
                # reason: that way there is no need to look at the
                # indentation.
                pieza = b"" if not actual["vistas"] else bytes([OP_GOTO, 0, 0])
                if pieza:
                    actual["salidas"].append(len(piezas))
                actual["vistas"] += 1
                if actual["destinos"][n] is not None:
                    raise NoSePuede("two identical battle handlers")
                actual["destinos"][n] = largo + len(pieza)
            elif cmd.code == END_BATTLE:
                if not bat:
                    raise NoSePuede("a battle end without its battle")
                actual = bat.pop()
                tabla = bytes([OP_BATTLE,
                               actual["tropa"] & 0xFF, actual["tropa"] >> 8])
                for n, destino in enumerate(actual["destinos"]):
                    # The handler the page does not have falls at the end of
                    # the block, which is what RM2k does with a sub-index
                    # without a branch: `SetSubcommandIndex` and carry on.
                    # **Except the defeat with `defeat_mode` 0**, which there
                    # is not a missing branch but the Game Over: see
                    # `BATALLA_PERDER`.
                    if destino is None and n == 2 and actual["game_over"]:
                        d = BATALLA_PERDER
                    else:
                        d = largo if destino is None else destino
                    tabla += bytes([d & 0xFF, d >> 8])
                piezas[actual["i"]] = tabla
                for salida in actual["salidas"]:
                    piezas[salida] = con_destino(piezas[salida], largo)
                pieza = b""
            elif cmd.code == SHOW_CHOICE:
                if mensajes is None:
                    raise NoSePuede("a choice with no window to put it in")
                opciones = opciones_de[id(cmd)]
                if not opciones:
                    raise NoSePuede("a choice without options")
                if [n for n, _ in opciones] != list(range(len(opciones))):
                    raise NoSePuede("options numbered out of order")
                cancelar = cmd.parameters[0] if cmd.parameters else 0
                if cancelar > len(opciones):
                    # `cancel_type` 5 with four options is the "cancel
                    # branch", a fifth one that is not in the list. Nobody
                    # uses it in this game and doing it blindly would be
                    # making things up.
                    raise NoSePuede("choice with a cancel branch")
                cuadros = cuadros_de_eleccion(opciones, mensajes)
                eleg.append({"i": len(piezas), "n": len(opciones),
                             "cancelar": cancelar, "cuadros": cuadros,
                             "destinos": [None] * len(opciones),
                             "vistas": 0, "salidas": []})
                # The table's room, filled in at the `ShowChoiceEnd`.
                pieza = bytes(3 + 4 * len(opciones))
            elif cmd.code == SHOW_CHOICE_OPTION:
                if not eleg:
                    raise NoSePuede("an option without its choice")
                actual = eleg[-1]
                n = cmd.parameters[0] if cmd.parameters else 0
                if not 0 <= n < actual["n"]:
                    raise NoSePuede("an option that is not in the list")
                # The previous option's body ends here: it is taken out of
                # the choice with a jump to the end, patched when closing it.
                # Emitting it here and not at the body's `END` is what keeps
                # this from depending on looking at the indentation.
                pieza = b"" if not actual["vistas"] else bytes([OP_GOTO, 0, 0])
                if pieza:
                    actual["salidas"].append(len(piezas))
                actual["vistas"] += 1
                actual["destinos"][n] = largo + len(pieza)
            elif cmd.code == SHOW_CHOICE_END:
                if not eleg:
                    raise NoSePuede("a choice end without its choice")
                actual = eleg.pop()
                if any(d is None for d in actual["destinos"]):
                    raise NoSePuede("an option without a body")
                tabla = bytes([OP_CHOICE, actual["n"], actual["cancelar"]])
                for cuadro, destino in zip(actual["cuadros"],
                                           actual["destinos"]):
                    tabla += bytes([cuadro & 0xFF, cuadro >> 8,
                                    destino & 0xFF, destino >> 8])
                piezas[actual["i"]] = tabla
                for salida in actual["salidas"]:
                    piezas[salida] = con_destino(piezas[salida], largo)
                pieza = b""
            elif cmd.code == COND_RAMA:
                pila.append(len(piezas))
                pieza = bytes_de_rama(cmd)
            elif cmd.code == COND_SINO:
                if not pila:
                    raise NoSePuede("an `else` without its `if`")
                abierta = pila.pop()
                pieza = bytes([OP_GOTO, 0, 0])
                # The `if`'s destination is **after** this jump, which is
                # where the branch below starts; the jump's is resolved at
                # the `end`, with the piece left open in its place.
                _parchear(piezas, abierta, largo + 3)
                pila.append(len(piezas))
            elif cmd.code == COND_FIN:
                if not pila:
                    raise NoSePuede("an `end` without its `if`")
                abierta = pila.pop()
                _parchear(piezas, abierta, largo)
                pieza = b""
            elif cmd.code == SHOW_INN:
                pieza = _compilar_posada(cmd, largo, mensajes)
            elif cmd.code == CONTROL_SWITCHES \
                    and len(cmd.parameters) >= 4 \
                    and cmd.parameters[3] == SWITCH_TOGGLE:
                pieza = _compilar_alternar(cmd, largo)
            elif cmd.code in (INN_STAY, INN_NO_STAY, INN_END):
                # The inn's three branches. None of the game's 18 pages
                # uses them —measured—, and doing them requires exactly what
                # `_compilar_posada` does not have: a place to put the body of
                # "stayed" inside a choice that is already built.
                raise NoSePuede("an inn with its branches")
            elif cmd.code == CALL_EVENT:
                pieza = _compilar_llamada(cmd, largo, hondo, indice_de_mapa,
                                          mensajes, eventos_mapa, temas,
                                          graficos, imagenes, tropas)
            else:
                pieza = _compilar(cmd, indice_de_mapa, mensajes, extra,
                                  eventos_mapa, temas, graficos, imagenes)
                # A jump to another map: the page keeps running there. See
                # `Eventos.afuera`.
                if cmd.code == TELEPORT and eventos_mapa is not None \
                        and cmd.parameters[0] != eventos_mapa.map_id:
                    eventos_mapa = eventos_mapa.afuera()
                if cmd.code == RECALL_TO_LOCATION:
                    destino = _destino_recordado(cmd, constantes, temas,
                                                 indice_de_mapa)
                    if eventos_mapa is not None \
                            and destino != eventos_mapa.map_id:
                        eventos_mapa = eventos_mapa.afuera()
                _anotar_constante(cmd, constantes)
                # The switch of an equipment common event, turned on: its
                # body goes right here, as if a `CallEvent` followed it. In
                # RM2k it would run on the next frame; see
                # `COMUNES_DEL_EQUIPO`.
                for numero in _comunes_que_prende(cmd):
                    pieza += compilar_pagina(
                        _Comandos(COMUNES[numero]), indice_de_mapa, mensajes,
                        eventos_mapa, temas, graficos, imagenes, tropas,
                        base=largo + len(pieza), hondo=hondo + 1) or b""
            if temas is not None:
                _seguir_la_salida(cmd, bgm, temas, indice_de_mapa,
                                  temas.pedidos != pedidos)
            piezas.append(pieza)
            largo += len(pieza)
        if pila:
            raise NoSePuede("an unclosed branch")
        if eleg:
            raise NoSePuede("an unclosed choice")
        if bat:
            raise NoSePuede("an unclosed battle")
        # What was noted from the `PlayBGM`s counts only if the page
        # compiles: one that does not, does not run, and says nothing about
        # how the map is left.
        if bgm[0] is not None:
            bgm[1].append((bgm[0], False))
        for tema, sale in bgm[1]:
            temas.salida(tema, sale)
        for destino, tema in bgm[2]:
            temas.salto(destino, tema)
        codigo = b"".join(piezas)
        # The `OP_DONE` belongs to the page and not to the piece: an inline
        # body carrying it would end the caller's page instead of returning
        # control to it. See `base`.
        return codigo if hondo else codigo + bytes([OP_DONE])
    except NoSePuede:
        if mensajes is not None:
            mensajes.volver(marca)
        return None


def _comunes_que_prende(cmd):
    """The `COMUNES_DEL_EQUIPO` events whose switch this command turns on."""
    p = cmd.parameters
    if cmd.code != CONTROL_SWITCHES or len(p) < 4 or p[3] != SWITCH_ON \
            or p[0] not in (SWITCH_UNICO, SWITCH_RANGO):
        return []
    return [numero for switch, numero in sorted(COMUNES_DEL_EQUIPO.items())
            if p[1] <= switch <= p[2]]


def _anotar_constante(cmd, constantes):
    """Keeps in `constantes` the last thing the page put in each variable
    when it was a constant, and forgets the variable if it wrote it some
    other way. It does not look at branches: it is for `_destino_recordado`,
    which only uses it to note an audio destination."""
    p = cmd.parameters
    if cmd.code == CONTROL_VARS and len(p) >= 7:
        desde, hasta = (p[1], p[1]) if p[0] == 0 else (p[1], p[2])
        for numero in range(desde, hasta + 1):
            constantes.pop(numero, None)
        if p[0] == 0 and p[3] == VAR_PONER and p[4] == VAR_CONSTANTE:
            constantes[p[1]] = p[5]
    elif cmd.code in (MEMORIZE_LOCATION, KEY_INPUT_PROC, STORE_TERRAIN_ID) \
            and p:
        for numero in (p[:3] if cmd.code == MEMORIZE_LOCATION
                       else p[3:4] if cmd.code == STORE_TERRAIN_ID else p[:1]):
            constantes.pop(numero, None)


def _destino_recordado(cmd, constantes, temas, indice_de_mapa):
    """The RM2k id of the map a `RecallToLocation` jumps to, if the page set
    it with a constant before —the breaking floors load 61 or 60 into the
    variable, and jump right away—, or None.

    What is known is noted as the map's destination in `temas`, same as a
    `Teleport`: it is where it comes from which song may be playing on
    arrival. What is not known —the way back from a tutorial, which jumps to
    whatever another page remembered— is not noted, and it is the only thing
    the audio does not see: the song that arrives that way has to be in the
    destination's package by another path. In the game it is the droid
    tutorial going back to 48 with the song it left there with."""
    destino = constantes.get(cmd.parameters[0]) if cmd.parameters else None
    if destino is not None and temas is not None:
        indice = indice_de_mapa(destino)
        if indice is not None:
            temas.destino(indice)
            if indice != temas.mapa:
                temas.salto(indice, None)
    return destino


# What cuts an exit `PlayBGM` before the jump: branches, choices, battles,
# calls and loops —with them, what follows is no longer a single line—. The
# effects too, but those show in `Temas.pedidos`, which also counts an
# animation's.
CORTAN_LA_SALIDA = frozenset((
    COND_RAMA, COND_SINO, COND_FIN, SHOW_CHOICE, SHOW_CHOICE_OPTION,
    SHOW_CHOICE_END, ENEMY_ENCOUNTER, END_BATTLE, CALL_EVENT, SHOW_INN,
    INN_STAY, INN_NO_STAY, INN_END,
    # A jump whose destination is not always known: it is taken as not
    # leaving.
    RECALL_TO_LOCATION, PLAY_MEMORIZED_BGM) + BATALLA_HANDLERS
    # Label, JumpToLabel, Loop, BreakLoop, EndLoop and EndEventProcessing.
    + (12110, 12120, 12210, 12220, 22210, 12310))


def _seguir_la_salida(cmd, salida, temas, indice_de_mapa, sono):
    """Follows, command by command, whether the page's last `PlayBGM` is an
    exit one —see `Temas.de_salida`—: it is if what comes up to a
    `Teleport` to another map plays no effect (`sono`), turns on no other
    song and does not branch. `salida` is [the pending song or None, what
    was noted]; what was noted is passed to `temas` only if the page
    compiles.

    A jump to the same map also cuts it: it reloads the package with the
    song playing, which is the inheritance case and not the leaving one.

    And it notes in `salida[2]` each jump to another map with the song it
    carries if it is an exit one, or None: see `Temas.salto`."""
    pendiente, anotado = salida[:2]
    if cmd.code == TELEPORT and temas.mapa is not None:
        destino = indice_de_mapa(cmd.parameters[0])
        if destino is not None and destino != temas.mapa:
            salida[2].append((destino, pendiente))
    if cmd.code == PLAY_BGM and cmd.string:
        if pendiente is not None:
            anotado.append((pendiente, False))
        salida[0] = temas.nombres.index(cmd.string)
        return
    if pendiente is None:
        return
    if cmd.code == TELEPORT:
        sale = indice_de_mapa(cmd.parameters[0]) != temas.mapa
        anotado.append((pendiente, sale))
        salida[0] = None
    elif sono or cmd.code in CORTAN_LA_SALIDA:
        anotado.append((pendiente, False))
        salida[0] = None


# How deep a `CallEvent` nests. It is not an abstract precaution: a common
# event can call itself —the inline body would be infinite— and two can call
# each other. In this game the longest chain that compiles is one.
LLAMADA_MAX = 4


class _Comandos:
    """A wrapper with `.commands`, which is the only thing `compilar_pagina`
    looks at in a page. The common events, which are not pages, need it."""

    def __init__(self, comandos):
        self.commands = comandos


def _compilar_llamada(cmd, largo, hondo, indice_de_mapa, mensajes,
                      eventos_mapa, temas, graficos, imagenes, tropas):
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
    if len(p) < 2 or hondo >= LLAMADA_MAX:
        return b""
    if p[0] == 0:
        # A common event, by number. This game's are cut almost all of them
        # at `ControlVars` and at the original's own menus.
        destino, ctx = COMUNES.get(p[1]), eventos_mapa
    elif p[0] == 1 and len(p) >= 3 and eventos_mapa is not None:
        # A map event, by id and **page number**, which in RM2k starts at
        # one: it is `CommandCallEvent`'s `page->ID`.
        paginas = eventos_mapa.paginas.get(p[1])
        if paginas is None or not 1 <= p[2] <= len(paginas):
            return b""
        destino = paginas[p[2] - 1].commands
        # "This event" inside the called one is **the called one**, not the
        # caller: `Push` passes it `event->GetId()`. Without this a
        # Hover-Tram route would move the Tram Officer.
        ctx = eventos_mapa.para(p[1])
    else:
        # By variable —type 2— it is not resolved at compile time and never
        # will be: the number comes from the save. It is skipped, as
        # before.
        return b""
    if not destino:
        return b""
    return compilar_pagina(_Comandos(destino), indice_de_mapa, mensajes, ctx,
                           temas, graficos, imagenes, tropas,
                           base=largo, hondo=hondo + 1) or b""


def _compilar_alternar(cmd, largo):
    """`ControlSwitches` that toggles: no opcode of its own, one branch per
    switch with what the interpreter already does —like the inn, it is
    built here because the destinations are absolute within the page and the
    one that carries `largo` is `compilar_pagina`'s loop—. For each switch,
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
    if p[0] not in (SWITCH_UNICO, SWITCH_RANGO):
        raise NoSePuede("toggling switches by variable")
    desde, hasta = p[1], p[2]
    if hasta < desde or hasta - desde >= MAX_RANGO:
        raise NoSePuede("toggling a range from %d to %d" % (desde, hasta))
    out = b""
    for numero in range(desde, hasta + 1):
        aca = largo + len(out)
        prender, fin = aca + 14, aca + 18
        bajo, alto = numero & 0xFF, numero >> 8
        out += bytes([OP_IF, COND_SWITCH, bajo, alto, 0,
                      prender & 0xFF, prender >> 8,
                      OP_SWITCH, bajo, alto, 0,
                      OP_GOTO, fin & 0xFF, fin >> 8,
                      OP_SWITCH, bajo, alto, 1])
    return out


def _compilar_posada(cmd, largo, mensajes):
    r"""`ShowInn`, expanded into commands the ROM already knows how to do.

    The inn is not a new opcode: it is the greeting with its choice, a branch
    on gold, the charge and the heal, which are five things the interpreter
    already did. It is built here and not in `_compilar` because the
    destinations of the choice and of the branch are offsets **absolute
    within the page**, and that is known by `compilar_pagina`'s loop, which
    is the one that carries `largo`.

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
    terms are from the LDB: see `indexar_terminos`.

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
        raise NoSePuede("ShowInn with no operands")
    tipo, precio = p[0], p[1]
    if precio == 0:
        return bytes([OP_HEAL, 0, 0, 0])
    if mensajes is None:
        raise NoSePuede("an inn with no window to put it in")
    if tipo not in TERMINOS_POSADA:
        raise NoSePuede("inn of type %d, which is not in the terms: was "
                        "indexar_terminos called?" % tipo)
    if not precio <= 0xFFFF:
        # The cap is the gold branch's operand, which goes in a word; the
        # game's most expensive is 100.
        raise NoSePuede("inn of %d, which does not fit in the gold branch"
                        % precio)
    saludo_1, saludo_2, saludo_3, si, no = TERMINOS_POSADA[tipo]
    donde = mensajes.agregar(
        ["%s %d%s %s" % (saludo_1, precio, TERMINOS_POSADA["gold"], saludo_2),
         saludo_3])
    cuadros = cuadros_de_eleccion([(0, si), (1, no)], mensajes)
    fin = largo + 30
    rama = bytes([OP_IF, COND_ORO, precio & 0xFF, precio >> 8, 0,
                  fin & 0xFF, fin >> 8])
    return (bytes([OP_MESSAGE, donde & 0xFF, donde >> 8])
            # Cancel is the second option: there the default
            # `choice_cancel_type` is 5 and `inn_stay` is
            # `choice_result == 0`, that is cancelling is not staying.
            + bytes([OP_CHOICE, 2, 2])
            + bytes([cuadros[0] & 0xFF, cuadros[0] >> 8,
                     (largo + 14) & 0xFF, (largo + 14) >> 8])
            + bytes([cuadros[1] & 0xFF, cuadros[1] >> 8,
                     fin & 0xFF, fin >> 8])
            + rama
            + bytes([OP_GOLD, 1, precio & 0xFF, (precio >> 8) & 0xFF, 0])
            + bytes([OP_HEAL, 0, 0, 0]))


def imagen_aceptable(p):
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


def _compilar_imagen(cmd, imagenes):
    """The three `Picture` commands, or None if this picture does not fit.

    The parameter indices come from easyrpg-player's `CommandShowPicture` and
    `CommandMovePicture`, **not from memory**: the two read fourteen and
    sixteen, and the order is not the one one would guess —the color and the
    saturation go in 8..11 and the effect mode in 12—.
    """
    p = cmd.parameters
    if imagenes is None:
        return None
    if cmd.code == ERASE_PICTURE:
        if not p or not imagenes.suyo(p[0], None, None):
            return None
        return bytes([OP_PICTURE_ERASE])
    if not imagen_aceptable(p):
        return None
    tono = (p[8], p[9], p[10], p[11])
    if cmd.code == SHOW_PICTURE:
        # `use_transparent_color`: whether the PNG's index 0 is drawn or not.
        # The "1 year earlier" picture has it off, so it is an opaque
        # rectangle; making it transparent would require one palette color
        # less and knowing which was index 0 before reducing.
        if p[7] or imagenes.mostrar(p[0], cmd.string, p[2], p[3]) is None:
            return None
        return bytes([OP_PICTURE]) + bytes(tono)
    # MovePicture: the same picture, in the same place, with another tone.
    # The duration comes in **tenths** —`data.time_left = duration *
    # DEFAULT_FPS / 10`—, which is what had to be looked up: the first one's
    # 35 are three and a half seconds, not half a second.
    if not imagenes.suyo(p[0], p[2], p[3]):
        return None
    cuadros = p[14] * CUADROS_POR_DECIMA
    if not 0 <= cuadros <= IMAGEN_CUADROS_MAX:
        return None
    salida = bytes([OP_PICTURE_MOVE]) + bytes(tono) + bytes([cuadros])
    if len(p) > 15 and p[15] and cuadros:
        # `options.wait`: the page waits as long as it lasts, like
        # `FlashScreen`.
        salida += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
    return salida


def indice_de_sonido(temas, indice_de_mapa, nombre, volumen, tempo, balance,
                     de_ruta=False):
    """The `Temas.sonidos` index of an effect asked for on the map being
    compiled: `PlaySound`'s and, with `de_ruta`, that of move command
    35.

    The ones that on some map sound with another sample —map 1's whole
    thunder— carry another name for the same WAV, so the other maps keep
    theirs. See `se_del_mapa` in snes_music.py. And the route ones of the
    `se_de_ruta_sin_paquete` maps do not go into the package: see there."""
    from audio import snes_music

    def es(mapa):
        try:
            return temas.mapa == indice_de_mapa(mapa)
        except Exception:
            return False

    al_paquete = True
    if temas.mapa is not None:
        for (base, mapa), alias in snes_music.se_del_mapa().items():
            if nombre == base and es(mapa):
                nombre = alias
                break
        if de_ruta:
            al_paquete = not any(
                es(m) and (cuales is None or nombre in cuales)
                for m, cuales in snes_music.se_de_ruta_sin_paquete().items())
    if temas.mapa == PAQUETE_BATALLA:
        # A troop page's: see `se_de_tropa_al_paquete`.
        al_paquete = nombre in snes_music.se_de_tropa_al_paquete()
    return temas.sonido(nombre, volumen, tempo, balance, al_paquete)


def _compilar(cmd, indice_de_mapa, mensajes=None, extra=(),
              eventos_mapa=None, temas=None, graficos=None, imagenes=None):
    p = cmd.parameters

    if cmd.code == END or cmd.code in IGNORABLES:
        return b""

    if cmd.code == PLAY_SOUND:
        # Without a song registry it is accepted and not done, as before. An
        # empty name is "(OFF)": it plays nothing.
        if temas is None or not cmd.string or len(p) < 3:
            return b""
        k = indice_de_sonido(temas, indice_de_mapa, cmd.string, p[0], p[1],
                             p[2])
        return bytes([OP_SOUND, k & 0xFF, k >> 8])

    if cmd.code == WEATHER_EFFECTS:
        if len(p) < 2:
            raise NoSePuede("WeatherEffects with no operands")
        return bytes([OP_WEATHER, p[0] & 0xFF, min(max(p[1], 0), 2)])

    if cmd.code == OPEN_SHOP:
        if len(p) < 4:
            raise NoSePuede("OpenShop with no operands")
        if p[2]:
            raise NoSePuede("OpenShop with the bought and did-not-buy branches")
        vende = [i for i in p[4:] if 0 < i < ITEMS_N]
        if len(vende) > 255 or not 0 <= p[0] <= 2 or not 0 <= p[1] <= 2:
            raise NoSePuede("OpenShop that does not fit in OP_SHOP")
        return bytes([OP_SHOP, p[0], p[1], len(vende)]) + b"".join(
            bytes([i & 0xFF, i >> 8]) for i in vende)

    if cmd.code == FULL_HEAL:
        # The amount at 0 is what tells it apart from `ChangeHP`, below.
        if len(p) < 2:
            raise NoSePuede("FullHeal with no operands")
        return bytes([OP_HEAL, actor_de_blanco(p, "FullHeal"), 0, 0])
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
            raise NoSePuede("ChangeHP that subtracts")
        if p[3] != 0:
            raise NoSePuede("ChangeHP with the amount in a variable")
        if not 0 <= p[4] <= 0xFFFF:
            raise NoSePuede("ChangeHP of %d" % p[4])
        if p[4] == 0:
            return b""
        return bytes([OP_HEAL, actor_de_blanco(p, "ChangeHP"),
                      p[4] & 0xFF, p[4] >> 8])
    if cmd.code == CHANGE_SKILLS:
        # [type, id, forgets, skill by variable, skill]. It is easyrpg's
        # `CommandChangeSkills`: `LearnSkill` or `UnlearnSkill` on each actor
        # of the target, without asking for the page refresh —it does not
        # ask for it there either— and without a message: the "learned such
        # a thing" is written by the page with a `ShowMessage`.
        #
        # The game's 898 are all fixed actor and constant skill, so the
        # operand is directly the bit: see `HABILIDAD_RANURA`. The party, the
        # actor by variable and the skill by variable do not compile.
        if len(p) < 5:
            raise NoSePuede("ChangeSkills with no operands")
        if p[0] != 1:
            raise NoSePuede("ChangeSkills on the party or an actor by "
                            "variable")
        if p[3] != 0:
            raise NoSePuede("ChangeSkills with the skill in a variable")
        ranura = ranura_de_habilidad(p[1], p[4])
        return bytes([OP_SKILL, ranura & 0xFF, ranura >> 8,
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
            raise NoSePuede("ChangeEquipment with no operands")
        if p[2] != 1:
            raise NoSePuede("ChangeEquipment that equips")
        if not 0 <= p[3] < RANURAS_EQUIPO:
            raise NoSePuede("ChangeEquipment that unequips everything")
        actor = actor_de_blanco(p, "ChangeEquipment")
        if _ACTORES_INDEXADOS and actor and actor not in ACTOR_EQUIPO:
            raise NoSePuede("actor %d is not in the LDB" % actor)
        return bytes([OP_EQUIPMENT, actor, p[3]])
    if cmd.code == GAME_OVER:
        # `CommandGameOver`: the Game Over screen and, on pressing, the
        # title. It is the same as losing a battle without a handler —see
        # `BATALLA_PERDER`—: tools/runtime/game_over.s.
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
            raise NoSePuede("ChangeCondition that sets a state")
        return b""

    if cmd.code == KEY_INPUT_PROC:
        # [variable, wait, the four directions, the action one, cancel]. The
        # game's 32 occurrences have the five and no more: with six or more
        # RM2k 1.50 goes on to look at each direction separately, which is
        # another program, so the length is required instead of assumed.
        if len(p) != 5:
            raise NoSePuede("KeyInputProc with %d operands" % len(p))
        banderas = ((TECLA_ESPERA if p[1] else 0)
                    | (TECLA_DIRS if p[2] else 0)
                    | (TECLA_DECISION if p[3] else 0)
                    | (TECLA_CANCELAR if p[4] else 0))
        if not banderas & (TECLA_DIRS | TECLA_DECISION | TECLA_CANCELAR):
            # With no key asked for, the waiting form never comes out.
            raise NoSePuede("KeyInputProc with no key")
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
            # looked at edges in this form too —see `tecla_valor`— and that
            # a `Teleport` from a parallel page was not handled with the
            # foreground idle —see the main loop—.
            # `test_recorrido_carrera_golden.py` enforces it.
            return bytes([OP_KEY, ranura_de_variable(p[0]),
                          banderas | escritura_pide_refresco(p[0],
                                                             eventos_mapa)])
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
        ranura = ranura_de_variable(p[0])
        banderas |= escritura_pide_refresco(p[0], eventos_mapa)
        return bytes([OP_KEY, ranura, banderas | TECLA_ARRANCA,
                      OP_KEY, ranura, banderas])

    if cmd.code == CHANGE_SPRITE_ASSOCIATION:
        # [actor, CharSet index, transparent]. See OP_ACTOR_SPRITE.
        if len(p) != 3:
            # With four it is the bitfield of "this comes from a variable",
            # which this game never uses.
            raise NoSePuede("ChangeSpriteAssociation with operands we do not "
                            "know how to read")
        if p[2]:
            raise NoSePuede("transparent ChangeSpriteAssociation: the console "
                            "does not fade a sprite without color math")
        if not 0 < p[0] < 256:
            raise NoSePuede("ChangeSpriteAssociation on actor %d" % p[0])
        if graficos is None:
            raise NoSePuede("ChangeSpriteAssociation without a graphics table")
        elegido = graficos.indice(cmd.string, p[1])
        if elegido > 0xFF:
            raise NoSePuede("too many graphics on the map")
        return bytes([OP_ACTOR_SPRITE, p[0], elegido])

    if cmd.code in (CHANGE_SAVE_ACCESS, CHANGE_MENU_ACCESS,
                    CHANGE_ESCAPE_ACCESS):
        if not p:
            raise NoSePuede("%s with no operands" % cmd.code)
        cual = {CHANGE_SAVE_ACCESS: ACCESO_GUARDAR,
                CHANGE_MENU_ACCESS: ACCESO_MENU,
                CHANGE_ESCAPE_ACCESS: ACCESO_ESCAPAR}[cmd.code]
        return bytes([OP_ACCESS, ACCESO_BIT[cual], 1 if p[0] else 0])

    if cmd.code == CHANGE_SCREEN_TRANSITIONS:
        # See CHANGE_SCREEN_TRANSITIONS and OP_TRANSITION.
        if len(p) < 2:
            raise NoSePuede("ChangeScreenTransitions with no operands")
        cual, rm2k = p[0], p[1]
        if cual not in (TRANSICION_BORRAR, TRANSICION_MOSTRAR):
            raise NoSePuede("the battle's ChangeScreenTransitions: the ROM "
                            "always uses the database's")
        if cual == TRANSICION_BORRAR and rm2k in RM2K_TRANSICIONES_CORTE:
            return bytes([OP_TRANSITION, cual, TRANSICION_CORTE])
        if rm2k in RM2K_TRANSICIONES_QUE_NO:
            raise NoSePuede("ChangeScreenTransitions to %s for showing, which "
                            "no ROM map uses"
                            % RM2K_TRANSICIONES_QUE_NO[rm2k])
        tipo = (TRANSICION_MOSAICO if rm2k == RM2K_TRANSICION_MOSAICO
                else TRANSICION_FUNDIDO)
        return bytes([OP_TRANSITION, cual, tipo])

    if cmd.code == CHANGE_ITEMS:
        # [add or remove, item by constant or variable, item, amount by
        # constant or variable, amount]. See OP_ITEM.
        if len(p) < 5:
            raise NoSePuede("ChangeItems with no operands")
        if p[1] != 0 or p[3] != 0:
            raise NoSePuede("ChangeItems with the item or the amount in a "
                            "variable")
        if not 1 <= p[2] < ITEMS_N:
            raise NoSePuede("ChangeItems of item %d, which is not in the LDB"
                            % p[2])
        delta = -p[4] if p[0] else p[4]
        if not -128 <= delta <= 127:
            raise NoSePuede("ChangeItems of %d, which does not fit in a byte"
                            % p[4])
        return bytes([OP_ITEM, p[2] & 0xFF, p[2] >> 8, delta & 0xFF])

    if cmd.code == CHANGE_GOLD:
        # `OperateValue(operation, type, value)`: the operation is 0 add and
        # 1 subtract, and the type 0 constant and 1 "the value is in a
        # variable". Without variables, the latter cannot be done.
        if len(p) < 3:
            raise NoSePuede("ChangeGold with no operands")
        if p[1] != 0:
            raise NoSePuede("ChangeGold with the amount in a variable")
        monto = p[2]
        if not 0 <= monto <= 0xFFFFFF:
            raise NoSePuede("ChangeGold of %d, which does not fit in three "
                            "bytes" % monto)
        return bytes([OP_GOLD, 1 if p[0] else 0,
                      monto & 0xFF, (monto >> 8) & 0xFF, (monto >> 16) & 0xFF])

    if cmd.code == PLAY_BGM:
        # Without a song registry it is accepted and not done, which is what
        # this repo did with PlayBGM from the start. With a registry the index
        # is emitted and the ROM plays the song if it got to carry it.
        if temas is None or not cmd.string:
            return b""
        return bytes([OP_BGM, temas.indice(cmd.string) & 0xFF])

    if cmd.code == PAN_SCREEN:
        # Locking and unlocking the camera are used by no page of the game,
        # so they do not compile: modeling them with nothing exercising them
        # is making up a difference. Moving and resetting do, which are the
        # 133 there are.
        if len(p) < 5 or p[0] not in (PAN_CORRER, PAN_VOLVER):
            raise NoSePuede()
        if p[0] == PAN_CORRER and p[1] not in PAN_SENTIDO:
            raise NoSePuede()
        if not 0 <= p[2] <= 255:
            raise NoSePuede()
        salida = bytes_de_pan(p[0], p[1], p[2], p[3], p[4])
        if salida is None:
            raise NoSePuede()
        return salida

    if cmd.code == FADE_OUT_BGM:
        if not p or p[0] < 0:
            raise NoSePuede()
        paso = paso_de_fundido(p[0])
        return bytes([OP_FADE_BGM, paso & 0xFF, paso >> 8])

    if cmd.code == OPEN_SAVE_MENU:
        return bytes([OP_SAVE])

    if cmd.code in (SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE):
        salida = _compilar_imagen(cmd, imagenes)
        # None is "this picture does not fit the model": it is accepted
        # without being done, which is what the three did until 2026-09-12.
        # Cutting the page would take away from the game the eight that
        # compile today because of it.
        return b"" if salida is None else salida

    if cmd.code in ACEPTADOS_SIN_HACER:
        return b""     # accepted with the debt declared above

    if cmd.code == CHANGE_ENCOUNTER_STEPS:
        # The `1 / pasos` and the rows' seven thresholds, computed here as for
        # the map's registry —`encuentros_de_la_rom`—, so a change of steps
        # changes the chance and the rows together, same as
        # `Encuentros.poner_pasos`. It lasts until the next map load: the ROM
        # sets the map's again, which is what RM2k does.
        if not p:
            raise NoSePuede("ChangeEncounterSteps with no operands")
        pasos = max(p[0], 0)
        umbrales = enc_umbrales_de_paso(pasos)
        if max(umbrales) > 0xFF:
            raise NoSePuede("ChangeEncounterSteps of %d steps: the thresholds "
                            "do not fit in a byte" % pasos)
        base = enc_base(pasos)
        return bytes([OP_ENCOUNTER_STEPS, base & 0xFF, base >> 8]
                     + umbrales + [0xFF])

    if cmd.code in (COMMENT, COMMENT_2):
        # It is not debt: in RM2k it does nothing either. Map 64's farewell
        # asked for it, whose only command that did not compile was the
        # "LYS" note the author left after the `Teleport` to the world.
        return b""

    if cmd.code == CONTROL_SWITCHES:
        if len(p) < 4 or p[0] not in (SWITCH_UNICO, SWITCH_RANGO):
            raise NoSePuede()       # by variable: it needs variables
        if p[3] == SWITCH_TOGGLE:
            # `_compilar_alternar` builds it from `compilar_pagina`'s loop,
            # which is the one that knows `largo`; here it would only arrive
            # from another path —the fused cells'—, which no toggle of the
            # game takes.
            raise NoSePuede("toggling a switch outside the page's loop")
        desde, hasta = p[1], p[2]
        if hasta < desde or hasta - desde >= MAX_RANGO:
            raise NoSePuede()
        valor = 1 if p[3] == SWITCH_ON else 0
        out = b""
        for numero in range(desde, hasta + 1):
            out += bytes([OP_SWITCH, numero & 0xFF, numero >> 8, valor])
        return out

    if cmd.code == TELEPORT:
        if len(p) < 3:
            raise NoSePuede()
        destino = indice_de_mapa(p[0])
        if destino is None:
            raise NoSePuede()       # the map did not get into the ROM
        if temas is not None:
            temas.destino(destino)
        return bytes([OP_TELEPORT, destino & 0xFF, destino >> 8,
                      p[1] & 0xFF, p[1] >> 8, p[2] & 0xFF, p[2] >> 8])

    if cmd.code == MEMORIZE_LOCATION:
        if len(p) < 3:
            raise NoSePuede("MemorizeLocation without its three variables")
        modo = 0
        for bit, numero in zip(LUGAR_REFRESCOS, p[:3]):
            if escritura_pide_refresco(numero, eventos_mapa):
                modo |= bit
        return bytes([OP_LOCATION, modo]
                     + [ranura_de_variable(n) for n in p[:3]])

    if cmd.code == RECALL_TO_LOCATION:
        if len(p) < 3:
            raise NoSePuede("RecallToLocation without its three variables")
        return bytes([OP_LOCATION, LUGAR_SALTAR]
                     + [ranura_de_variable(n) for n in p[:3]])

    if cmd.code in (MEMORIZE_BGM, PLAY_MEMORIZED_BGM):
        # Without a song registry it is accepted and not done, like
        # `PlayBGM`.
        if temas is None:
            return b""
        return bytes([OP_MEMORIZED_BGM, int(cmd.code == PLAY_MEMORIZED_BGM)])

    if cmd.code == CHANGE_PARTY_MEMBERS:
        if len(p) < 3 or p[1] != GRUPO_ID_FIJO:
            raise NoSePuede()   # the id comes from a variable, and we do not read them
        if p[0] not in (GRUPO_AGREGAR, GRUPO_SACAR) or not 0 <= p[2] <= 255:
            raise NoSePuede()
        return bytes([OP_PARTY, p[0], p[2]])

    if cmd.code == PROCEED_WITH_MOVEMENT:
        return bytes([OP_WAIT_ROUTES])

    if cmd.code == HALT_ALL_MOVEMENT:
        return bytes([OP_STOP_ROUTES])

    if cmd.code == CHANGE_PBG:
        return b""      # accepted and dropped: see CHANGE_PBG

    if cmd.code == FLASH_SPRITE:
        if len(p) < 7:
            raise NoSePuede()
        if p[0] == RUTA_HEROE:
            blanco = 0
        elif eventos_mapa is None:
            raise NoSePuede()
        else:
            blanco = eventos_mapa.blanco(p[0])
            if blanco is None:
                raise NoSePuede()   # a vehicle, or an event that does not exist
            # **A flash on an event that shares a palette is emitted anyway.**
            # On the console the flash is a CGRAM tint —`pintar_flash`
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
            raise NoSePuede()
        cuadros = p[5] * CUADROS_POR_DECIMA
        if not 0 < cuadros <= 255:
            raise NoSePuede()
        out = bytes([OP_FLASH, blanco, p[1], p[2], p[3], p[4], cuadros])
        if p[6]:
            # Waiting is exactly the Wait command: `SetupWait(tenths)`, that
            # is the same tenths times CUADROS_POR_DECIMA.
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == CONTROL_VARS:
        # `[how it is chosen, from, to, operation, operand kind, a, b]`. One
        # variable at a time and nothing else: ranges and indirect are used
        # by no page of the game. See OP_VAR.
        if len(p) < 7:
            raise NoSePuede("a ControlVars with no operands")
        if p[0] != 0:
            raise NoSePuede("ControlVars on a range or indirect")
        ranura = ranura_de_variable(p[1])
        refresco = escritura_pide_refresco(p[1], eventos_mapa)
        if p[3] not in (VAR_PONER, VAR_SUMAR, VAR_RESTAR):
            raise NoSePuede("ControlVars operation %d" % p[3])
        clase, a, b = p[4], p[5], p[6]
        if clase == VAR_CONSTANTE:
            if not -0x8000 <= a <= 0x7FFF:
                raise NoSePuede("constant %d that does not fit in a word" % a)
            b = 0
        elif clase == VAR_VARIABLE:
            a, b = ranura_de_variable(a), 0
        elif clase == VAR_AZAR:
            if not (0 <= a <= b <= 0x7FFF and b - a < 256):
                raise NoSePuede("random between %d and %d: the ROM divides by "
                                "a byte" % (a, b))
        elif clase == VAR_OTRO:
            if a not in (OTRO_ORO, OTRO_TIMER):
                raise NoSePuede("ControlVars 'other' %d" % a)
            b = 0
        elif clase == VAR_PERSONAJE:
            # A character's cell. `a` becomes the same target byte OP_ROUTE
            # carries —0 the hero, the event's index plus one— and not the
            # RM2k id: the bytecode never sees an id again, which is what
            # `Eventos` exists to guarantee. `b` is which coordinate.
            if b not in (PERSONAJE_X, PERSONAJE_Y):
                raise NoSePuede("ControlVars kind 6 with sub-operand %d"
                                % b)
            if a == RUTA_HEROE:
                a = 0
            elif eventos_mapa is None:
                raise NoSePuede("kind 6 on an event without the map")
            else:
                a = eventos_mapa.blanco(a)
                if a is None:
                    raise NoSePuede()   # a vehicle, or an event that does not exist
        else:
            raise NoSePuede("operand of kind %d in ControlVars" % clase)
        return bytes([OP_VAR, ranura, p[3] | refresco, clase, a & 0xFF,
                      (a >> 8) & 0xFF, b & 0xFF, b >> 8])
    if cmd.code == TIMER_OPERATION:
        # The timer. The whole operation is done —set, start and stop— and
        # the seconds can come from a variable: it is the fourth operation,
        # `TIMER_PONER_VAR`, with the slot in the operand.
        if len(p) < 5:
            raise NoSePuede()
        if p[0] == TIMER_PONER:
            if p[1] != TIMER_SEGUNDOS_FIJOS:
                ranura = ranura_de_variable(p[2])
                return bytes([OP_TIMER, TIMER_PONER_VAR, ranura, 0, 0])
            # The ROM counts the frames in sixteen bits, so the cap is not the
            # operand's but the count's. It is eighteen minutes, and the
            # game's longest timer is ten.
            if not 0 <= p[2] * CUADROS_POR_SEGUNDO + TIMER_CUADROS_DE_MAS \
                    <= 0xFFFF:
                raise NoSePuede()
            return bytes([OP_TIMER, TIMER_PONER, p[2] & 0xFF, p[2] >> 8, 0])
        if p[0] in (TIMER_ARRANCAR, TIMER_PARAR):
            # The fifth parameter is "also in battle", and here there are no
            # battles: it is compiled anyway and ignored, like the rest of
            # what belongs to combat.
            return bytes([OP_TIMER, p[0], 0, 0, 1 if p[3] else 0])
        raise NoSePuede()

    if cmd.code == MOVE_EVENT:
        if len(p) < 4:
            raise NoSePuede()
        if p[0] == RUTA_HEROE:
            blanco = 0
        elif eventos_mapa is None:
            raise NoSePuede()   # without the map there is no way to translate the id
        else:
            blanco = eventos_mapa.blanco(p[0])
            if blanco is None:
                raise NoSePuede()   # a vehicle, or an event that does not exist
        if not RUTA_FRECUENCIA_MIN <= p[1] <= RUTA_FRECUENCIA:
            raise NoSePuede()   # 1 does not fit in the ROM's wait byte
        ordenes = decodificar_ruta(list(p[4:]))
        if frecuencia_minima(p[1], [o for o, _ in ordenes],
                             bool(p[2])) < RUTA_FRECUENCIA_MIN:
            raise NoSePuede()   # commands 30 and 31 would take it down to 1
        ruta = []
        # Whether the cursor is between a `begin_jump` and its `end_jump`.
        # Inside a jump the commands are not run: `BeginMoveRouteJump` only
        # **adds up** the `move_*`s and the turns, and 9 there would have to
        # ask about the hero in the middle of the math. No route of the game
        # does it —measured, zero—, so it is rejected instead of letting the
        # ROM walk it down a path no test exercises.
        en_salto = False
        for orden, extras in ordenes:
            if orden == RUTA_SALTO_INICIO:
                en_salto = True
            elif orden == RUTA_SALTO_FIN:
                en_salto = False
            elif orden == RUTA_HACIA_HEROE and en_salto:
                raise NoSePuede()

            if orden == RUTA_SONIDO:
                # See RUTA_SONIDO. Without a song registry, or "(OFF)", it is
                # dropped as before.
                if en_salto or temas is None or extras[0] in ("", "(OFF)"):
                    continue
                k = indice_de_sonido(temas, indice_de_mapa, *extras,
                                     de_ruta=True)
                ruta += [orden, k & 0xFF, k >> 8]
                continue
            if orden in RUTA_TRANSPARENCIA:
                # Accepted and dropped: it does not show and costs no frames.
                # See RUTA_TRANSPARENCIA.
                continue
            # Turning, waiting and moving. The `move_*`s came in on
            # 2026-09-03, and they are looked at *during* the walk and not
            # only at the end: `ruta` tests it, comparing four frames of a
            # twelve-cell route with waits in the middle. What goes in from
            # `rpg::MoveCommand::Code` is `RUTA_ORDENES`, and moving toward
            # the hero is in since 2026-09-12 —see RUTA_HACIA_HEROE—; moving
            # away from him, turning in place and the switches are still out.
            if orden not in RUTA_ORDENES:
                raise NoSePuede()
            if orden in (RUTA_ENCARAR_HEROE, RUTA_HACIA_HEROE) and blanco == 0:
                raise NoSePuede()   # the hero facing or moving toward itself
            if orden in RUTA_HEROE_AFUERA and blanco == 0:
                # Locking and unlocking the facing on **the hero**: accepted
                # and dropped, like the sound and the transparency. On events
                # they are done. Raising and lowering the speed were also
                # dropped on the hero, and they are done since 2026-09-10:
                # see RUTA_HEROE_AFUERA.
                #
                # Dropping them and not rejecting the whole page, which was
                # the first thing tried, is from 2026-09-06: **Talan's scene
                # has a hero route that starts with 28**, so the scene that
                # motivated that day's six points did not compile and the
                # player could not leave the Emitter Room corridor.
                continue
            if orden in RUTA_DIAGONALES and blanco == 0:
                # And the hero diagonally: the ROM does not know how to do it
                # and none of the game's 26 routes with diagonals is the
                # hero's. Without this cut the ROM would go left —the `mover`
                # of `paso_de_ruta` falls into `try_left` by elimination—.
                raise NoSePuede()
            if orden == RUTA_CAMBIAR_GRAFICO:
                # The only command with an operand: after 34 goes the
                # graphic's index in `Graficos`, which the converter resolves
                # to the map's sprite bank. Whoever walks an already compiled
                # route has to skip that byte: read as a command, a 30 or a
                # 31 change the route's frequency without anyone asking.
                #
                # **On the hero too**, since 2026-09-12. Its graphic comes
                # from the actor table, but the actor's twelve poses are
                # written with the same shape as an `npc_poses` entry, so the
                # ROM changes the pointer and that is it: see `grafico_heroe`
                # in tools/runtime/ruta_del_heroe.s. They are +29 pages of the
                # game, and among them the three of map 8's `EV0047`, which
                # could not be interacted with.
                if graficos is None or len(extras) < 2:
                    raise NoSePuede()
                elegido = graficos.indice(extras[0], extras[1])
                if elegido > 0xFF:
                    raise NoSePuede()
                ruta.append(orden)
                ruta.append(elegido)
                continue
            ruta.append(orden)
        if len(ruta) > 255:
            raise NoSePuede()
        if not ruta:
            # A route left without commands —only sound or transparency,
            # like those of map 2's screens— is not emitted: in RM2k
            # `UpdateMoveRoute` consumes it whole on the same frame and
            # considers it finished, so it neither costs frames nor leaves
            # anything to wait for in `ProceedWithMovement`.
            return b""
        return bytes([OP_ROUTE, blanco, p[1], len(ruta)]) + bytes(ruta)

    if cmd.code == CHANGE_EVENT_LOCATION:
        if len(p) < 4 or p[1] not in (LUGAR_CONSTANTE, LUGAR_POR_VARIABLE):
            raise NoSePuede()
        if p[0] == RUTA_HEROE or eventos_mapa is None:
            # Nobody moves the hero this way in this game —that is what
            # Teleport is for— and without the map there is no way to
            # translate the id.
            raise NoSePuede()
        blanco = eventos_mapa.blanco(p[0])
        if blanco is None:
            raise NoSePuede()   # a vehicle, or an event that does not exist
        if p[1] == LUGAR_POR_VARIABLE:
            # The cell comes from two variables, and they are read **when it
            # runs**: it is `CommandChangeEventLocation`'s
            # `Main_Data::game_variables->Get(x)`. It goes in a separate
            # opcode and not in a bit of `OP_PLACE` because the operands are
            # different —two one-byte slots against two words— and a
            # variable-length opcode is what the walk over the bytecode does
            # not know how to do: `OPCODE_SIZE` is a table.
            return bytes([OP_PLACE_VAR, blanco, ranura_de_variable(p[2]),
                          ranura_de_variable(p[3])])
        if not (0 <= p[2] <= 0xFFFF and 0 <= p[3] <= 0xFFFF):
            raise NoSePuede()
        return bytes([OP_PLACE, blanco, p[2] & 0xFF, p[2] >> 8,
                      p[3] & 0xFF, p[3] >> 8])

    if cmd.code == TILE_SUBSTITUTION:
        # `[upper layer?, old tile, new tile]`, with the tiles numbered from
        # the first of their layer, which is how `DoSubstitute` numbers
        # them.
        if len(p) < 3:
            raise NoSePuede("TileSubstitution with no operands")
        if eventos_mapa is None or eventos_mapa.sustituciones is None:
            # Without the converter in between there are no blocks to
            # translate against. See `Sustituciones` in snes_convert.py.
            raise NoSePuede("TileSubstitution without the map's blocks")
        pares = eventos_mapa.sustituciones.pares(bool(p[0]), p[1], p[2])
        if pares is None:
            raise NoSePuede("TileSubstitution that cannot be translated to "
                            "blocks: see `Sustituciones`")
        if not pares:
            # No cell of the map draws the old tile, so there is nothing to
            # change. In RM2k the substitution is still recorded, but nobody
            # looks at what it records: there is no cell that can use it.
            return b""
        out = bytearray([OP_TILE_SUB, len(pares)])
        for viejo, nuevo in pares:
            out += bytes([viejo & 0xFF, viejo >> 8, nuevo & 0xFF, nuevo >> 8])
        return bytes(out)

    if cmd.code == STORE_TERRAIN_ID:
        # `[mode, x, y, variable]`, with `ValueOrVariable`: in mode 0 the cell
        # comes written and in mode 1 the two numbers are variable ids. Both
        # are resolved **when it runs**, so both go in the same opcode with
        # the mode set: reading them here in mode 1 would answer with what
        # the variables were worth at compile time.
        if len(p) < 4 or p[0] not in (0, 1):
            raise NoSePuede("StoreTerrainID with a mode that is neither 0 nor 1")
        destino = ranura_de_variable(p[3])
        if p[0]:
            x, y = ranura_de_variable(p[1]), ranura_de_variable(p[2])
        else:
            if not (0 <= p[1] <= 0xFFFF and 0 <= p[2] <= 0xFFFF):
                raise NoSePuede("StoreTerrainID outside the 16 bits")
            x, y = p[1], p[2]
        modo = p[0] | escritura_pide_refresco(p[3], eventos_mapa)
        return bytes([OP_TERRAIN, modo, x & 0xFF, x >> 8, y & 0xFF, y >> 8,
                      destino])

    if cmd.code == SHOW_HIDDEN_MONSTER:
        # It only arrives from a troop page: see `TROPA_COMANDOS`. A place
        # the troop does not have does nothing in easyrpg —`GetEnemy` gives
        # null—, and the ROM checks it against `BA_NENE`.
        if len(p) < 1 or not 0 <= p[0] < 256:
            raise NoSePuede("ShowHiddenMonster without a place")
        return bytes([OP_SHOW_ENEMY, p[0]])

    if cmd.code == SHAKE_SCREEN:
        # `CommandShakeScreen`, in its RM2k form: power, speed, tenths and
        # whether it waits. The game's 29 are of that form. With zero tenths
        # it is `ShakeEnd` and never waits.
        if len(p) < 4 or not 0 <= p[0] <= 9 or not 0 <= p[1] <= 9:
            raise NoSePuede()
        cuadros = p[2] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        out = bytes([OP_SHAKE, p[0], p[1], cuadros & 0xFF, cuadros >> 8])
        if cuadros and p[3]:
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == SHOW_BATTLE_ANIMATION:
        # (animation, target, wait, global): see OP_ANIMATION.
        if len(p) < 3:
            raise NoSePuede()
        anim = ANIMACIONES.get(p[0])
        if p[1] == RUTA_HEROE:
            blanco, quien = 0, None
        elif eventos_mapa is None:
            blanco, quien = None, None
        else:
            blanco = eventos_mapa.blanco(p[1])
            quien = (eventos_mapa.mio if p[1] == RUTA_ESTE_EVENTO else p[1])
        if anim is None or blanco is None:
            return b""      # without an animation or a target RM2k does nothing
        # The target's flash is a tint of its palette on the console, and two
        # events with the same graphic share it: see FLASH_SPRITE. Here the
        # page is not cut for that: that flash is not done. **The hero is
        # never flashed**: whom he shares a palette with depends on the
        # party, which the compiler does not see —the converter looks at it
        # for the `FlashSprite`s and cuts the whole ROM—, and an animation is
        # not worth that.
        destella = (blanco != 0
                    and not eventos_mapa.comparte_grafico(quien))
        entradas = []
        for t in anim["timings"]:
            tick = (t["frame"] - 1) * 2
            if not 0 <= tick <= 255:
                continue
            nombre, volumen, tempo, balance = t["se"]
            if nombre and nombre != "(OFF)" and temas is not None:
                k = temas.sonido(nombre, volumen, tempo, balance)
                entradas.append(bytes([tick, ANIM_SONIDO, k & 0xFF, k >> 8,
                                       0, 0, 0, 0]))
            r, g, b = (min(31, max(0, v)) for v in t["rgb"])
            fuerza = min(7 * max(0, t["fuerza"]) // 6, 31)
            if t["alcance"] == 2:
                entradas.append(bytes([tick, ANIM_DESTELLO, r, g, b, fuerza,
                                       ANIM_DESTELLO_CUADROS, 0]))
            elif t["alcance"] == 1 and destella:
                entradas.append(bytes([tick, ANIM_FLASH, blanco, r, g, b,
                                       fuerza, ANIM_DESTELLO_CUADROS]))
        entradas.sort(key=lambda e: e[0])   # stable: the LDB's order
        if len(entradas) > 255:
            raise NoSePuede()
        # A `global` one —the one RM2k repeats three by three to cover the
        # screen— is accepted and not drawn: it is still heard and still
        # flashes, which is what it already did. None of the intro's eleven
        # asks for it.
        numero = (p[0] if p[0] <= 255 and not (len(p) > 3 and p[3])
                  else ANIM_SIN_DIBUJO)
        out = (bytes([OP_ANIMATION, numero, dibujo_blanco(anim, blanco),
                      len(entradas)])
               + b"".join(entradas))
        cuadros = 2 * len(anim["cuadros"])
        if p[2] and cuadros:
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == FLASH_SCREEN:
        # `CommandFlashScreen`, in its RM2k form: color, power, tenths and
        # whether it waits. The game's 62 are of that form, and none lasts
        # more than twenty tenths: the frames byte is enough, and the ROM
        # divides the level by what is left with the hardware's eight-bit
        # divider.
        if len(p) < 6 or any(not 0 <= v <= 31 for v in p[:4]):
            raise NoSePuede()
        cuadros = p[4] * CUADROS_POR_DECIMA
        if cuadros > 0xFF:
            raise NoSePuede()
        out = bytes([OP_FLASH_SCREEN, p[0], p[1], p[2], p[3], cuadros])
        if cuadros and p[5]:
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == TRADE_EVENT_LOCATIONS:
        # `CommandTradeEventLocations`: each one goes with `MoveTo` to the
        # other's cell. No page of the game uses it on the hero.
        if len(p) < 2 or eventos_mapa is None:
            raise NoSePuede()
        blancos = [eventos_mapa.blanco(q) for q in p[:2]]
        if any(b is None or b == 0 for b in blancos):
            raise NoSePuede()   # the hero, a vehicle or an event that does not exist
        return bytes([OP_SWAP] + blancos)

    if cmd.code == WAIT:
        if len(p) < 1:
            raise NoSePuede()
        cuadros = p[0] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        return bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])

    if cmd.code == TINT_SCREEN:
        if len(p) < 4:
            raise NoSePuede()
        if any(not 0 <= v <= 200 for v in p[:4]):
            raise NoSePuede()
        # The duration is discarded: the tint is applied at once. The screen
        # being compared is always settled, so the final value is the one
        # that matters; what is lost is the one-second gradient.
        return bytes([OP_TINT, p[0], p[1], p[2], p[3]])

    if cmd.code == SHOW_MESSAGE:
        if mensajes is None:
            raise NoSePuede()   # this ROM carries no window: nowhere to put it
        lineas = [cmd.string] + list(extra)
        # `Mensajes.agregar` removes the escape tail, since every box goes
        # through it; anything that is not `\|` or `\^` still cuts the page
        # from there. See `cola_de_escapes`.
        donde = mensajes.agregar(lineas)
        return bytes([OP_MESSAGE, donde & 0xFF, donde >> 8])

    raise NoSePuede()


class Estado:
    """The party, to simulate its changes when converting:
    `lideres_posibles` and `grupo_de_la_pagina` in snes_convert.py. It is
    what is left of the Python interpreter's state, which went away with the
    reference; the ROM is the only one that runs the bytecode."""

    def __init__(self, grupo=()):
        # The party, in order. The hero's graphic is the first one's, so the
        # order decides which poses have to fit in VRAM.
        self.grupo = list(grupo)

    def cambiar_grupo(self, operacion, actor):
        """Adds or removes an actor, with RM2k's rules.

        Adding one who is already there does not duplicate it nor move it,
        adding with a full party does nothing, and removing one who is not
        there does nothing either: it is what
        `Game_Party::AddActor`/`RemoveActor` do in easyrpg-player, which also
        call `ResetGraphic` in both cases. It matters because the order
        decides who the leader is, that is which sprite is drawn.
        """
        if operacion == GRUPO_SACAR:
            if actor in self.grupo:
                self.grupo.remove(actor)
        elif actor not in self.grupo and len(self.grupo) < GRUPO_MAX:
            self.grupo.append(actor)

    def lider(self):
        return self.grupo[0] if self.grupo else None


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
SENO_SACUDIDA = [round(math.sin(t * math.pi / 128) * 127) for t in range(256)]


def recorrer_codigo(codigo):
    """(offset, code) of each opcode of an already compiled page."""
    i = 0
    while i < len(codigo):
        yield i, codigo
        i += opcode_size(codigo, i)


def blancos_de_ruta(paginas):
    """The events these already compiled pages send a route to.

    It walks the bytecode and not the RM2k commands, which is what makes it
    the truth and not a guess: what counts is what ended up emitted, after
    the filter decided which pages go in.
    """
    blancos = set()
    for pagina in paginas:
        codigo = pagina.get("codigo")
        for i, c in recorrer_codigo(codigo or b""):
            if c[i] == OP_ROUTE and c[i + 1]:
                blancos.add(c[i + 1] - 1)
    return blancos


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
SWITCH_DE_PRUEBA = 1023

# The variable that chooses which of the test pages runs, when a cartridge
# carries several: see `--caso` in snes_convert.py. Page k asks for it to be
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
VARIABLE_DE_CASO = 1000
COMPARAR_AL_MENOS = 1   # the `>=` of RM2k's page conditions
# The switch that is never turned on: it is what a page with a condition the
# port cannot meet —an item, see `rm2k.CONDICIONES_IMPOSIBLES`— carries as
# `switch_a`, so the ROM never picks it, and does pick the event's other
# pages. The game checks switches up to 1003 and 1023 is the test page's.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
SWITCH_IMPOSIBLE = 1021


def deudas_de_la_pagina(page, imagenes=None):
    """Which commands of this page are accepted without being done.

    So the converter can warn instead of the debt going silent.

    The three `Picture` ones are debt only **if this page is not the one of
    the picture the ROM does draw**: warning anyway would be the warning
    nobody reads, which is how a real debt gets lost among the ones that no
    longer are.
    """
    salida = set()
    for cmd in page.commands:
        if cmd.code not in ACEPTADOS_SIN_HACER:
            continue
        if (cmd.code in (SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE)
                and _compilar_imagen(cmd, imagenes) is not None):
            continue
        salida.add(cmd.code)
    return sorted(salida)


def paginas_del_mapa(game_map, indice_de_mapa, mensajes=None, temas=None,
                     graficos=None, imagenes=None, tropas=None):
    """The pages the ROM needs to resolve the map's events.

    *All* the pages of an event that has some triggerable one are emitted,
    not only those: which one stays active depends on the conditions of all
    of them, and a later page that triggers nothing still wins and keeps the
    one below from running.
    """
    salida = []
    del_mapa = Eventos(game_map)
    chipset = getattr(game_map, "chipset_nombre", None)
    for numero_evento, event in enumerate(game_map.events):
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
        if not rm2k.condiciones_soportadas(event):
            continue

        grupo = []
        for numero_pagina, page in enumerate(event.pages):
            cond = page.condition
            codigo = None
            if rm2k.pagina_imposible(page):
                # Never active: no code, no graphic, and with the switch that
                # never turns on. The pages below keep winning when their turn
                # comes, which is what RM2k does while the item is not there.
                grupo.append({
                    "evento": numero_evento, "pagina": numero_pagina,
                    "trigger": page.trigger,
                    "switch_a": SWITCH_IMPOSIBLE, "switch_b": 0, "actor": 0,
                    "variable": None, "item": 0,
                    "capa": page.layer, "frecuencia": page.move_frequency,
                    "velocidad": page.move_speed, "codigo": None,
                    "ruta_propia": None, "grafico": None, "tile_pasa": None,
                    "gira": False,
                })
                continue
            grafico = rm2k.grafico_de_pagina(page, chipset)
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
            vacia = not page.commands and page.trigger in (TRIGGER_AUTOMATICO,
                                                           TRIGGER_PARALELO)
            if page.trigger in TRIGGERS and puede_dispararse(page) and not vacia:
                codigo = compilar_pagina(page, indice_de_mapa, mensajes,
                                         del_mapa.para(event.id), temas,
                                         graficos, imagenes, tropas)
                # **And the same with one that compiles to nothing**: all it
                # had were calls that got skipped —see `_compilar_llamada`—.
                # In RM2k it is not empty, and what it calls is what turns it
                # off; here it would be the empty page above, with the map
                # frozen. It is `AfterBattleMint` on the maps with encounters:
                # with switch 498, which turns on each troop's turn 0 page, it
                # calls common event 35, `ResetAfterBattles`, which does not
                # compile and is the one that turns 498 off. Without this, the
                # first battle on those maps left the hero unable to take a
                # step.
                if codigo == bytes([OP_DONE]) and page.trigger in (
                        TRIGGER_AUTOMATICO, TRIGGER_PARALELO):
                    codigo = None
            grupo.append({
                "evento": numero_evento,
                "pagina": numero_pagina,
                "trigger": page.trigger,
                "switch_a": cond.ids["switch_a"] if "switch_a" in cond.active else 0,
                "switch_b": cond.ids["switch_b"] if "switch_b" in cond.active else 0,
                "actor": cond.ids["actor"] if "actor" in cond.active else 0,
                "variable": ((ranura_de_variable(cond.ids["variable"]),
                              cond.operator, cond.variable_value)
                             if "variable" in cond.active else None),
                "item": cond.ids["item"] if "item" in cond.active else 0,
                "capa": page.layer,
                "frecuencia": page.move_frequency,
                "velocidad": page.move_speed,
                "codigo": codigo,
                "ruta_propia": ruta_propia(page),
                # What the page draws and what its tile imposes on the cell:
                # see `rm2k.collect_npcs`, and `pasa_con_evento` in
                # tools/runtime/heroe.s, which is the one that applies them.
                "grafico": grafico,
                "tile_pasa": (rm2k.pasabilidad_del_tile(game_map, grafico[0],
                                                        page.layer)
                              if grafico is not None else None),
                # Whether the event turns around toward the hero with this
                # page: a CharSet —a chipset tile has nowhere to look— and an
                # animation type that does not fix the direction. See TURN.
                "gira": bool(page.character_name)
                        and page.animation_type not in ANIM_FIJAS,
            })
        salida += grupo
    return salida


# The page's animation types, `rpg::EventPage::AnimType`.
ANIM_NO_CONTINUA, ANIM_CONTINUA_TIPO, ANIM_FIJA_NO_CONTINUA = 0, 1, 2
ANIM_FIJA_CONTINUA, ANIM_GRAFICO_FIJO, ANIM_GIRO = 3, 4, 5


def ruta_propia(page):
    """The page's own route —`move_type` 6, the route it walks on its own—,
    or None if it has none or it cannot be done.

    The same commands as in a MoveEvent go, with the transparency dropped and
    also the sound, which in a MoveEvent does play: here there is nowhere to
    put its operand —see RUTA_SONIDO—. The diagonals go in: an own route is
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
    if not RUTA_FRECUENCIA_MIN <= page.move_frequency <= RUTA_FRECUENCIA:
        return None
    if not 1 <= page.move_speed <= 6 or page.animation_type == ANIM_GIRO:
        return None
    ordenes = []
    for orden in page.move_route.commands:
        if orden == RUTA_SONIDO or orden in RUTA_TRANSPARENCIA:
            continue
        if orden not in RUTA_ORDENES or orden in (RUTA_ENCARAR_HEROE,
                                                  RUTA_HACIA_HEROE):
            return None
        if orden == RUTA_CAMBIAR_GRAFICO:
            # Here there is nowhere to put the operand —a page's route is a
            # bare list of codes, not a MoveEvent with its text— and it is not
            # needed: **none of the game's 3509 own routes changes graphic**,
            # measured. The day one shows up, this rejects it instead of
            # compiling a 34 with nothing to change to.
            return None
        ordenes.append(orden)
    if frecuencia_minima(page.move_frequency, ordenes,
                         page.move_route.repeat) < RUTA_FRECUENCIA_MIN:
        return None             # commands 30 and 31 would take it down to 1
    if not ordenes or len(ordenes) > 255:
        return None
    return {
        "ordenes": ordenes,
        "frecuencia": page.move_frequency,
        "velocidad": page.move_speed,
        "repite": page.move_route.repeat,
        "saltable": page.move_route.skippable,
        "dir_fija": page.animation_type in (ANIM_FIJA_NO_CONTINUA,
                                           ANIM_FIJA_CONTINUA,
                                           ANIM_GRAFICO_FIJO),
        "anim_continua": page.animation_type in (ANIM_CONTINUA_TIPO,
                                                ANIM_FIJA_CONTINUA),
    }
