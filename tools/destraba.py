#!/usr/bin/env python3
"""Cuánto destraba cada comando de evento que todavía no hacemos.

Existe porque el número que este repo venía usando para decidir el orden medía
otra cosa. La tabla de `README.md` cuenta **qué comando corta primero** cada
página automática, y de ahí salía "ShowMessage 144, es lo que más
desbloquearía". Pero una página cortada por un cuadro de texto puede estar
cortada además por otras cuatro cosas: hacer los cuadros de texto no la
destraba. Lo que hay que contar es cuántas páginas pasan a compilar **enteras**.

**Lo que este número es, y lo que no.** Aceptar un código de comando entero es
un **techo**: cuenta lo que se destrabaría si el comando estuviera hecho para
todos los casos que el juego usa, y una implementación real casi siempre cubre
menos. Cuando la diferencia importa —o sea cuando el comando está por hacerse—
el candidato lleva un filtro que dice cuáles de sus casos se van a poder, y la
tabla muestra las dos columnas. Sin filtro, la columna realista queda vacía y el
número hay que leerlo como lo que es.

Tres trampas que costaron una medición mal hecha cada una:

* **`ShowMessage_2`.** RM2k emite un `ShowMessage` y después un `ShowMessage_2`
  por cada línea de más del mismo cuadro. Contándolos aparte, los cuadros de
  texto parecían destrabar tres páginas en vez de cincuenta y cinco. Ahora el
  agrupado lo hace `eventos.agrupar`, que es el mismo que usa el conversor: la
  trampa dejó de tener dónde volver a pasar.
* **`CallEvent`.** Aceptarlo sin hacerlo daba +97, que es mentira: el evento
  común llamado tiene que compilar él también, y los de este juego se cortan
  casi todos en `FullHeal` y en `ControlVars`. Hecho de verdad destraba cero.
  Desde el 2026-09-12 **se hace**, compilado en línea, y su fila de acá mide la
  otra pregunta: qué pasaría si se **exigiera** que el llamado compile en vez
  de saltear la llamada. La respuesta es -98 páginas, y por eso no se exige.
* **`MoveEvent` sobre otro evento.** El techo daba +40 contando rutas que la ROM
  no va a saber caminar —saltos, cambiar el gráfico, diagonales— y blancos que
  no existen: vehículos, y eventos que el mapa no tiene. Con las órdenes que la
  ROM ya hace son +16, y con todas +31. De ahí salió el filtro.

Y al final imprime **qué órdenes de ruta faltan**, sobre todas las páginas del
juego y no sólo las automáticas: es la otra pregunta, la de adentro de
`MoveEvent`. Ver `ordenes_de_ruta`, que cuenta por qué está.

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

NOMBRES = event_codes.EVENT_CODES

CALL_EVENT = 12330
MAX_ANIDADO = 4                  # por si dos eventos comunes se llaman entre sí

# Los grupos. Un comando no se puede medir suelto cuando RM2k lo emite siempre
# acompañado: los tres de acá abajo son un solo trabajo cada uno.
MOVE_EVENT, PROCEED = 11330, 11340
TINT_SCREEN, FLASH_SPRITE = 11030, 11320
MOVE_HEROE, MOVE_ESTE = 10001, 10005

# Las órdenes de ruta que la ROM ya sabe caminar. Salen de `eventos.py` y no de
# una lista propia, así que el día que aprenda una más este número sube solo.
# El sonido y la transparencia van también porque `traducir` los acepta y los
# tira: sin ellos acá, una página que los usa contaba como compilando en la
# medición de base y como no compilando en la columna realista, y ésta daba
# **menos** que aquélla. Apareció con las diagonales, que fueron las que
# hicieron compilar a la primera página que tenía las dos cosas.
ORDENES = (set(eventos.RUTA_ORDENES) | {eventos.RUTA_SONIDO}
           | set(eventos.RUTA_TRANSPARENCIA))


def mover_otro(cmd, pagina):
    """Si este `MoveEvent` es uno que la ROM ya sabe hacer.

    Desde que los eventos con gráfico caminan, esto es lo que la ROM hace, así
    que la columna realista de este candidato da +0 y lo que queda es el techo:
    las órdenes de ruta que no sabemos caminar.

    Tres cosas, y las tres se midieron porque las tres pasan en este juego:
    el blanco tiene que ser el héroe o un evento **que el mapa tenga** —hay
    rutas apuntadas a vehículos y a eventos que ya no existen—, y la ruta tiene
    que estar hecha de órdenes que sabemos caminar.

    `ProceedWithMovement` pasa siempre: es "esperá a que termine", y sin las
    rutas no significa nada.
    """
    if cmd.code == PROCEED:
        return True
    q = list(cmd.parameters)
    if len(q) < 4:
        return False
    blanco = pagina.mio if q[0] == MOVE_ESTE else q[0]
    if blanco != MOVE_HEROE and blanco not in pagina.ids:
        return False
    if not eventos.RUTA_FRECUENCIA_MIN <= q[1] <= eventos.RUTA_FRECUENCIA:
        return False        # habría que modelar la espera entre órdenes
    # La ruta se decodifica de verdad y no se recorre plana: tres órdenes traen
    # operandos metidos en el mismo chorro de enteros, y dos de ellas un texto
    # con un entero por letra. Recorrerla plana alcanzaba mientras la primera
    # orden desconocida cortara todo; con `play_sound_effect` aceptado ya no.
    try:
        ordenes = eventos.decodificar_ruta(q[4:])
    except eventos.NoSePuede:
        return False
    if blanco == MOVE_HEROE and any(
            o in eventos.RUTA_DIAGONALES or o == eventos.RUTA_HACIA_HEROE
            for o, _e in ordenes):
        # Sobre el héroe la ROM no camina en diagonal y no lo manda hacia sí
        # mismo: ver `traducir`. Las órdenes 26 a 29 **no** están acá porque no
        # cortan la página: se aceptan y se tiran, como el sonido. Y la 34
        # tampoco desde el 2026-09-12, que se hace también sobre el héroe;
        # dejarla acá hacía que la columna realista diera **menos** que la
        # base, que es la forma en que este medidor ya falló dos veces.
        return False
    # Una ruta **vacía** cuenta como que se puede: `traducir` la acepta y no
    # emite nada —RM2k la consume entera en el cuadro y no deja nada que
    # esperar—. Pedir `ordenes` no vacía era otra forma del agujero de la
    # transparencia: la columna realista daba menos que la base, esta vez por
    # los dos MoveEvent sin órdenes de una página del mapa 2.
    return all(o in ORDENES for o, _e in ordenes)


# Los grupos. Un comando no se puede medir suelto cuando RM2k lo emite siempre
# acompañado: los tres de acá abajo son un solo trabajo cada uno. El tercer
# campo, cuando está, es el filtro que separa el techo de lo que se va a poder.
CANDIDATOS = [
    ("FlashSprite", {11320}, None),
    ("PlaySound", {11550}, None),
    ("ControlVars", {10220}, None),
    # ProceedWithMovement es "esperá a que termine de caminar": va con las
    # rutas forzadas y sin él no sirven de mucho.
    # Ya está hecho lo que el filtro deja pasar, así que su columna realista
    # da +0. Lo que queda es el techo: las órdenes de ruta que no sabemos
    # caminar —saltar, cambiar el gráfico, las diagonales— y los blancos que no
    # existen.
    ("MoveEvent, las órdenes que faltan", {MOVE_EVENT, PROCEED}, mover_otro),
    ("ConditionalBranch", {12010, 22010, 22011}, None),
    ("WeatherEffects", {11070}, None),
    ("FullHeal", {10490}, None),
    ("PanScreen", {11060}, None),
    ("ChangeItems", {10320}, None),
    ("FadeOutBGM", {11520}, None),
    # No es "cuánto destraba" sino "cuánto costaría exigir que el llamado
    # compile", que es la alternativa a saltear la llamada. Ver arriba.
    ("CallEvent, exigiendo el blanco", set(), None),
]


def cargar(game_dir):
    """Las páginas automáticas con comandos, y los eventos comunes."""
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    comunes = db.common_events
    paginas = []
    for nombre in sorted(os.listdir(game_dir)):
        if not (nombre.startswith("Map") and nombre.endswith(".lmu")):
            continue
        game_map = lcf.Map(os.path.join(game_dir, nombre))
        # Los ids de evento del mapa y el del dueño de la página. Hacen falta
        # para saber si una ruta apunta a algo que existe, y **el id no es el
        # índice**: 39 mapas de este juego tienen huecos en la numeración.
        ids = {event.id for event in game_map.events}
        del_mapa = eventos.Eventos(game_map)
        for event in game_map.events:
            for page in event.pages:
                if (page.trigger == eventos.TRIGGER_AUTOMATICO
                        and page.commands):
                    page.ids, page.mio = ids, event.id
                    # El mismo contexto que le pasa el conversor: sin él una
                    # ruta sobre otro evento no compila ni aunque la ROM sepa
                    # hacerla, porque no hay con qué traducir el id.
                    page.ctx = del_mapa.para(event.id)
                    paginas.append(page)
    return paginas, comunes


def compila(comandos, extra, con_call, comunes, filtros=(), pagina=None,
            hondo=0):
    """Como el filtro de `eventos.py`, con `extra` aceptado además.

    `con_call` entra al evento común en vez de aceptarlo, que es la única forma
    honesta de medir CallEvent.

    Se mide **con** el bloque de textos, o sea contando lo que compila una ROM
    que lleve la ventana de mensaje: sin ella los cuadros de texto no compilan y
    la base sería otra. El bloque se tira; acá sólo importa si el comando se
    pudo o no.
    """
    if hondo > MAX_ANIDADO:
        return False
    for cmd, lineas in eventos.agrupar(comandos):
        if cmd.code == CALL_EVENT and con_call:
            p = list(cmd.parameters)
            if len(p) < 2 or p[0] != 0 or p[1] not in comunes:
                return False        # el id sale de una variable, o no existe
            if not compila(comunes[p[1]], extra, con_call, comunes, filtros,
                           pagina, hondo + 1):
                return False
            continue
        if cmd.code == CALL_EVENT:
            # Sin `con_call`, la llamada no corta: desde el 2026-09-12
            # `compilar_pagina` la compila en línea y saltea la que no puede.
            # Hay que decirlo acá porque el que decide es él y no `_compilar`,
            # que es con lo que este medidor recorre los comandos.
            continue
        if cmd.code in extra:
            # Con filtro, sólo los casos que la ROM va a poder. Sin filtro, el
            # comando entero, que es el techo.
            filtro = filtros.get(cmd.code) if filtros else None
            if filtro is not None and not filtro(cmd, pagina):
                return False
            continue
        try:
            eventos._compilar(cmd, lambda m: 0, eventos.Mensajes(), lineas,
                              pagina.ctx if pagina is not None else None,
                              graficos=eventos.Graficos())
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

    def cuenta(extra, con_call=False, filtros=None):
        return sum(1 for p in paginas
                   if compila(p.commands, extra, con_call, comunes,
                              filtros or {}, p))

    base = cuenta(set())
    print("%d páginas automáticas con comandos, %d compilan enteras hoy\n"
          % (len(paginas), base))

    filas = []
    for etiqueta, codigos, filtro in CANDIDATOS:
        techo = cuenta(codigos, not codigos)
        real = (cuenta(codigos, not codigos, {c: filtro for c in codigos})
                if filtro is not None else None)
        filas.append((etiqueta, techo, real, codigos, filtro))
    filas.sort(key=lambda f: -(f[2] if f[2] is not None else f[1]))

    print("cada una sola, como techo y —si hay filtro— como se va a poder:")
    for etiqueta, techo, real, _codigos, _filtro in filas:
        print("  %-30s %4d  (+%-3d)%s"
              % (etiqueta, techo, techo - base,
                 "  realista %d (+%d)" % (real, real - base)
                 if real is not None else ""))

    print("\nacumuladas, en ese orden y con los filtros puestos:")
    juntas, call, filtros = set(), False, {}
    for etiqueta, _techo, _real, codigos, filtro in filas:
        juntas |= codigos
        call = call or not codigos
        if filtro is not None:
            filtros.update({c: filtro for c in codigos})
        print("  + %-28s %4d" % (etiqueta, cuenta(juntas, call, filtros)))

    corta = collections.Counter()
    juntas_filtro = filtros
    for p in paginas:
        if compila(p.commands, juntas, call, comunes, filtros, p):
            continue
        for cmd, lineas in eventos.agrupar(p.commands):
            if cmd.code == CALL_EVENT:
                continue
            if cmd.code in juntas and (juntas_filtro.get(cmd.code) is None
                                       or juntas_filtro[cmd.code](cmd, p)):
                continue
            try:
                eventos._compilar(cmd, lambda m: 0, eventos.Mensajes(),
                                  lineas, p.ctx, graficos=eventos.Graficos())
            except eventos.NoSePuede:
                corta[cmd.code] += 1
                break
    print("\ny lo que seguiría cortando después de todas ésas:")
    for code, n in corta.most_common(8):
        print("  %-24s %4d" % (NOMBRES.get(code, str(code)), n))

    ordenes_de_ruta(args.game_dir)


def ordenes_de_ruta(game_dir):
    """Qué órdenes de `MoveCommand` no sabemos caminar, y cuánto valen.

    Va aparte de la tabla de arriba y **sobre todas las páginas del juego**, no
    sólo las automáticas, porque es otra pregunta: la tabla dice qué comando
    conviene hacer y esto dice, adentro de `MoveEvent`, qué orden conviene
    aprender.

    Existe porque la respuesta cambió de signo en un día y nadie lo podía ver
    sin volver a medir. El 2026-09-12 faltaban diez órdenes; se midió que la 9
    sola valía +33 páginas y las otras nueve +1 entre todas, se hizo la 9, y al
    día siguiente un encargo pedía "la orden 10, 104 veces" sobre un número que
    ya no existía. Con esto acá, el número se vuelve a sacar en un segundo y no
    hay que acordarse de cuál medición era de cuándo.
    """
    conocidas = ORDENES
    todas = collections.Counter()
    paginas_con = collections.Counter()
    disparables_con = collections.Counter()
    for nombre in sorted(os.listdir(game_dir)):
        if not (nombre.startswith("Map") and nombre.endswith(".lmu")):
            continue
        game_map = lcf.Map(os.path.join(game_dir, nombre))
        for evento in game_map.events:
            for page in evento.pages:
                disparable = (page.trigger in eventos.TRIGGERS
                              and eventos.puede_dispararse(page))
                vistas = set()
                for cmd in page.commands:
                    q = list(cmd.parameters)
                    if cmd.code != MOVE_EVENT or len(q) < 4:
                        continue
                    try:
                        ordenes = eventos.decodificar_ruta(q[4:])
                    except eventos.NoSePuede:
                        continue
                    for orden, _extras in ordenes:
                        if orden not in conocidas:
                            todas[orden] += 1
                            vistas.add(orden)
                for orden in vistas:
                    paginas_con[orden] += 1
                    if disparable:
                        disparables_con[orden] += 1

    print("\nlas órdenes de ruta que no sabemos caminar, en todo el juego:")
    if not todas:
        print("  ninguna: las rutas forzadas del juego se caminan enteras")
        return
    for orden, n in todas.most_common():
        print("  orden %-3d %4d apariciones en %3d páginas, %3d disparables"
              % (orden, n, paginas_con[orden], disparables_con[orden]))


if __name__ == "__main__":
    main()
