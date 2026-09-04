#!/usr/bin/env python3
"""Cuánto destraba cada comando de evento que todavía no hacemos.

Existe porque el número que este repo venía usando para decidir el orden medía
otra cosa. La tabla de `rom/LEEME.md` cuenta **qué comando corta primero** cada
página automática, y de ahí salía "ShowMessage 144, es lo que más
desbloquearía". Pero una página cortada por un cuadro de texto puede estar
cortada además por otras cuatro cosas: hacer los cuadros de texto no la
destraba. Lo que hay que contar es cuántas páginas pasan a compilar **enteras**.

Dos trampas que costaron una medición mal hecha cada una:

* **`ShowMessage_2`.** RM2k emite un `ShowMessage` y después un `ShowMessage_2`
  por cada línea de más del mismo cuadro. Contándolos aparte, los cuadros de
  texto parecían destrabar tres páginas en vez de cincuenta y cinco.
* **`CallEvent`.** Aceptarlo sin hacerlo daba +97, que es mentira: el evento
  común llamado tiene que compilar él también, y los de este juego se cortan
  casi todos en `FullHeal` y en `ControlVars`. Hecho de verdad destraba cero.

Uso:
    python3 tools/destraba.py
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import event_codes
import eventos
import lcf
from render_map import GAME_DIR

NOMBRES = {v: k for k, v in vars(event_codes).items() if isinstance(v, int)}

CALL_EVENT = 12330
DB_COMMON_EVENTS = 0x19          # el chunk de la base; el 0x16 de cada uno son
COMMON_COMMANDS = 0x16           # sus comandos, con el formato de una página
MAX_ANIDADO = 4                  # por si dos eventos comunes se llaman entre sí

# Los grupos. Un comando no se puede medir suelto cuando RM2k lo emite siempre
# acompañado: los tres de acá abajo son un solo trabajo cada uno.
CANDIDATOS = [
    # Las líneas 2 a 4 de un cuadro de texto, y el retrato de quien habla.
    ("ShowMessage", {10110, 20110, 10130}),
    ("FlashSprite", {11320}),
    ("PlaySound", {11550}),
    ("ControlVars", {10220}),
    # ProceedWithMovement es "esperá a que termine de caminar": va con las
    # rutas forzadas y sin él no sirven de mucho.
    ("MoveEvent de otro evento", {11330, 11340}),
    ("TintScreen con saturación", {11030}),
    ("ChangeEventLocation", {10860}),
    ("ConditionalBranch", {12010, 22010, 22011}),
    ("WeatherEffects", {11070}),
    ("FullHeal", {10490}),
    ("PanScreen", {11060}),
    ("ChangeItems", {10320}),
    ("FadeOutBGM", {11520}),
    ("CallEvent", set()),        # el suyo no es un código: es entrar al evento
]


def cargar(game_dir):
    """Las páginas automáticas con comandos, y los eventos comunes."""
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    comunes = {i: lcf.read_commands(f.get(COMMON_COMMANDS, b""))
               for i, f in lcf.Reader(
                   db.fields[DB_COMMON_EVENTS]).read_struct_array().items()}
    paginas = []
    for nombre in sorted(os.listdir(game_dir)):
        if not (nombre.startswith("Map") and nombre.endswith(".lmu")):
            continue
        game_map = lcf.Map(os.path.join(game_dir, nombre))
        for event in game_map.events:
            for page in event.pages:
                if (page.trigger == eventos.TRIGGER_AUTOMATICO
                        and page.commands):
                    paginas.append(page)
    return paginas, comunes


def compila(comandos, extra, con_call, comunes, hondo=0):
    """Como el filtro de `eventos.py`, con `extra` aceptado además.

    `con_call` entra al evento común en vez de aceptarlo, que es la única forma
    honesta de medir CallEvent.
    """
    if hondo > MAX_ANIDADO:
        return False
    for cmd in comandos:
        if cmd.code == CALL_EVENT and con_call:
            p = list(cmd.parameters)
            if len(p) < 2 or p[0] != 0 or p[1] not in comunes:
                return False        # el id sale de una variable, o no existe
            if not compila(comunes[p[1]], extra, con_call, comunes, hondo + 1):
                return False
            continue
        if cmd.code in extra:
            continue
        try:
            eventos._compilar(cmd, lambda m: 0)
        except eventos.NoSePuede:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=GAME_DIR)
    args = parser.parse_args()

    paginas, comunes = cargar(args.game_dir)

    def cuenta(extra, con_call=False):
        return sum(1 for p in paginas
                   if compila(p.commands, extra, con_call, comunes))

    base = cuenta(set())
    print("%d páginas automáticas con comandos, %d compilan enteras hoy\n"
          % (len(paginas), base))

    filas = [(etiqueta, cuenta(codigos, not codigos), codigos)
             for etiqueta, codigos in CANDIDATOS]
    filas.sort(key=lambda f: -f[1])

    print("cada una sola:")
    for etiqueta, n, _codigos in filas:
        print("  %-30s %4d  (+%d)" % (etiqueta, n, n - base))

    print("\nacumuladas, en ese orden:")
    juntas, call = set(), False
    for etiqueta, _n, codigos in filas:
        juntas |= codigos
        call = call or not codigos
        print("  + %-28s %4d" % (etiqueta, cuenta(juntas, call)))

    corta = collections.Counter()
    for p in paginas:
        if compila(p.commands, juntas, call, comunes):
            continue
        for cmd in p.commands:
            if cmd.code in juntas or cmd.code == CALL_EVENT:
                continue
            try:
                eventos._compilar(cmd, lambda m: 0)
            except eventos.NoSePuede:
                corta[cmd.code] += 1
                break
    print("\ny lo que seguiría cortando después de todas ésas:")
    for code, n in corta.most_common(8):
        print("  %-24s %4d" % (NOMBRES.get(code, str(code)), n))


if __name__ == "__main__":
    main()
