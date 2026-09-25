"""Las páginas de evento de las tropas, corriendo en la pelea: el sistema de
batalla de Talan de punta a punta.

Talan usa `Detect Aura` —la habilidad 133, de tipo switch— y eso prende el
switch 134; la página de la tropa que lo mira le dice de qué color es el aura,
le cambia `Detect Aura` por `Absorb Aura`, anota el color en la variable 28 y
apaga el 134. Después usa `Absorb Aura`, que prende el 135, y la página de ése
le enseña las técnicas del enemigo, cuenta cuántas veces absorbió cada una y
apaga el 135. Es lo que pasa en RM2k, y lo que cuándo corre cada página está
copiado de `Scene_Battle_Rpg2k` y `Game_Interpreter_Battle` de easyrpg: ver
`ba_pag_probar` en main.s.

**Lo que se espera no se escribe a mano: se lee de la página del LDB**, con
un recorrido de sus comandos que no comparte nada con el compilador —el texto
de su `ShowMessage`, qué enseña y qué olvida su `ChangeSkills`, qué ponen y
suman sus `ControlVars` de afuera de las ramas—. Si la ROM corriera otra
página, u otra tropa, o la misma a medias, alguno de los tres no da.

La pelea es contra la tropa 121, un Nomadic Droid: uno solo, con 50 HP y 19 de
ataque, que en dos turnos no llega a matar a Talan, que es de nivel 1. El caso
de prueba es `tropa-talan-aura`: le enseña `Detect Aura` con un
`ChangeSkills` y abre la pelea un segundo después. El grupo se escribe en la
RAM y no con un `ChangePartyMembers` en la página a propósito: así Talan no
pasa a ser un líder posible del cartucho de pruebas, que le pondría su sprite
en todos los mapas y le podría mover los colores a más de una golden.
"""

import functools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "arnes"))

from rpgmaker import lcf                                    # noqa: E402
from port import eventos                                    # noqa: E402
from render.render_map import GAME_DIR                      # noqa: E402

from consola import en_la_rom                               # noqa: E402
from test_batalla import Pelea, ORDEN, FIN, hab_id          # noqa: E402

CASO = "tropa-talan-aura"
TALAN = 14
DETECT_AURA, ABSORB_AURA = 133, 134
TROPA = 121
# `BA_M_PAGINA` de main.s: corriendo una página de tropa.
PAGINA = 7


def db():
    return lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))


def casos_del_cartucho():
    import cartuchos
    comandos = []
    for nombre in cartuchos.casos_de(cartuchos.PRUEBAS):
        with open(os.path.join(cartuchos.CASOS, nombre + ".json"),
                  encoding="utf-8") as archivo:
            comandos += lcf.comandos_escritos(json.load(archivo))
    return comandos


@functools.lru_cache(maxsize=None)
def ranuras_de_variable():
    """El índice de variables del cartucho de pruebas: el del juego, con las
    de sus casos y la que elige el caso, que es lo que le pasa el conversor."""
    extra = eventos.variables_de_comandos(casos_del_cartucho())
    extra.add(eventos.VARIABLE_DE_CASO)
    return eventos.variables_de(GAME_DIR, None, extra)


@functools.lru_cache(maxsize=None)
def ranuras_de_habilidad():
    return eventos.pares_de_habilidad(
        GAME_DIR, eventos.pares_de_habilidad_de_comandos(casos_del_cartucho()))


def sabe(una, habilidad):
    r = ranuras_de_habilidad()[(TALAN, habilidad)]
    octeto = una.consola.ram(una.simbolos["FAR_HAB"] + (r >> 3), 1)[0]
    return bool(octeto & (1 << (r & 7)))


def variable(una, numero):
    return una.variable(ranuras_de_variable()[numero])


def pagina_del_switch(base, switch):
    """La página de la tropa que dispara ese switch, y sólo él."""
    suyas = [p for p in base.troops[TROPA].pages
             if p.activos == ["switch_a"]
             and p.condicion["switch_a_id"] == switch]
    assert len(suyas) == 1, "la tropa %d tiene %d páginas del switch %d" % (
        TROPA, len(suyas), switch)
    return suyas[0]


def lo_que_dice(pagina):
    """Los renglones de su primer `ShowMessage`, como los corta la pantalla."""
    renglones = []
    for cmd in pagina.commands:
        if cmd.code == eventos.SHOW_MESSAGE and not renglones:
            renglones.append(cmd.string)
        elif cmd.code == eventos.SHOW_MESSAGE_2 and renglones:
            renglones.append(cmd.string)
        elif renglones:
            break
    return renglones


def lo_que_enseña(pagina):
    """`{habilidad: la sabe al terminar}` según sus `ChangeSkills` a Talan."""
    cambios = {}
    for cmd in pagina.commands:
        p = cmd.parameters
        if cmd.code == eventos.CHANGE_SKILLS and p[0] == 1 and p[1] == TALAN:
            cambios[p[4]] = p[2] == 0
    return cambios


def lo_que_cuenta(pagina):
    """`{variable: valor}` de sus `ControlVars` de afuera de las ramas, desde
    cero: poner y sumar una constante, que es todo lo que estas páginas hacen
    ahí."""
    valores = {}
    for cmd in pagina.commands:
        p = cmd.parameters
        if cmd.code != eventos.CONTROL_VARS or cmd.indent != 0:
            continue
        assert p[0] == 0 and p[1] == p[2] and p[4] == 0, p
        if p[3] == 0:
            valores[p[1]] = p[5]
        elif p[3] == 1:
            valores[p[1]] = valores.get(p[1], 0) + p[5]
        else:
            raise AssertionError("una ControlVars que este recorrido no sabe")
    return valores


def mensaje_en_pantalla(una, pelea):
    """Los renglones del mensaje de página que la ROM tiene puesto, leídos del
    cartucho en el desplazamiento que dejó `op_message`."""
    desplazamiento = pelea.palabra(una.simbolos["BA_PAG_MSG"])
    assert desplazamiento != 0xFFFF, "no hay ningún mensaje de página"
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    i = en_la_rom(una.simbolos["mensajes_tropa"]) + desplazamiento
    cuantos = rom[i] & eventos.CABECERA_LINEAS
    i += 1
    renglones = []
    for _ in range(cuantos):
        largo = rom[i]
        renglones.append("".join(chr(b + 32) for b in rom[i + 1:i + 1 + largo]))
        i += 1 + largo
    return renglones


def hasta_el_mensaje(una, pelea, tope=1500):
    """Pasa los mensajes de la pelea hasta que una página muestre el suyo."""
    for n in range(tope):
        if (pelea.modo() == PAGINA
                and pelea.palabra(una.simbolos["BA_PAG_MSG"]) != 0xFFFF):
            return
        if pelea.modo() in (ORDEN, FIN):
            raise AssertionError("el turno terminó sin que corriera ninguna "
                                 "página de la tropa")
        una.consola.apretar(*(("a",) if n % 6 < 2 else ()))
        una.consola.correr(1)
    raise AssertionError("ninguna página mostró su mensaje")


def cerrar_y_esperar_ordenes(una, pelea, tope=1500):
    for n in range(tope):
        if pelea.modo() == ORDEN:
            return
        assert pelea.modo() != FIN, "la pelea terminó"
        una.consola.apretar(*(("a",) if n % 6 < 2 else ()))
        una.consola.correr(1)
    raise AssertionError("la pelea no volvió a pedir órdenes")


def lugar_en_la_lista(una, pelea, habilidad):
    """En qué lugar de la lista de la pelea está esa habilidad, o None."""
    lista = una.consola.ram(una.simbolos["BA_HAB_LISTA"],
                            pelea.byte("BA_HAB_N"))
    numeros = [hab_id(una, k) for k in lista]
    return numeros.index(habilidad) if habilidad in numeros else None


def abrir_la_lista(una, pelea):
    """Entra a la lista de habilidades de Talan y vuelve a las órdenes, para
    que la ROM la arme: `BA_HAB_LISTA` se arma al entrar."""
    pelea.esperar(ORDEN)
    for _ in range(5):
        pelea.tocar("left")
    pelea.tocar("right")
    pelea.tocar()
    lugares = (lugar_en_la_lista(una, pelea, DETECT_AURA),
               lugar_en_la_lista(una, pelea, ABSORB_AURA))
    pelea.tocar("b")
    return lugares


def test_el_sistema_de_batalla_de_talan(partida):
    base = db()
    detecta = pagina_del_switch(base, base.skills[DETECT_AURA].switch_id)
    absorbe = pagina_del_switch(base, base.skills[ABSORB_AURA].switch_id)
    s_detecta = base.skills[DETECT_AURA].switch_id
    s_absorbe = base.skills[ABSORB_AURA].switch_id
    assert (s_detecta, s_absorbe) == (134, 135)
    # Que las dos páginas hagan lo que este caso mira: si el juego cambiara,
    # el caso no distinguiría nada.
    assert lo_que_enseña(detecta) == {DETECT_AURA: False, ABSORB_AURA: True}
    assert lo_que_dice(absorbe)[0] == "TALAN absorbed aura techniques:"

    una = partida(caso=CASO)
    una.poner_grupo(TALAN)
    pelea = Pelea(una)
    for _ in range(600):
        if pelea.abierta():
            break
        una.consola.correr(1)
    else:
        raise AssertionError("la página no abrió la pelea")
    assert pelea.byte("BA_NACT") == 1

    # --- Detect Aura ---
    assert sabe(una, DETECT_AURA) and not sabe(una, ABSORB_AURA)
    detect, absorb = abrir_la_lista(una, pelea)
    assert detect is not None and absorb is None, (
        "Talan tendría que ofrecer Detect Aura y no Absorb Aura: %r"
        % ((detect, absorb),))
    assert not pelea.switch(s_detecta)
    pelea.ordenar(("habilidad", detect))
    hasta_el_mensaje(una, pelea)
    assert mensaje_en_pantalla(una, pelea) == lo_que_dice(detecta), (
        "la página de Detect Aura dijo %r y el LDB dice %r"
        % (mensaje_en_pantalla(una, pelea), lo_que_dice(detecta)))
    cerrar_y_esperar_ordenes(una, pelea)
    assert not pelea.switch(s_detecta), "la página tenía que apagar el 134"
    for habilidad, la_sabe in lo_que_enseña(detecta).items():
        assert sabe(una, habilidad) == la_sabe, (
            "después de Detect Aura, la habilidad %d" % habilidad)
    for numero, valor in lo_que_cuenta(detecta).items():
        assert variable(una, numero) == valor, (
            "la variable %d quedó en %d y la página la pone en %d"
            % (numero, variable(una, numero), valor))

    # --- Absorb Aura ---
    detect, absorb = abrir_la_lista(una, pelea)
    assert detect is None and absorb is not None, (
        "la pelea tendría que ofrecer ahora Absorb Aura y no Detect Aura: %r"
        % ((detect, absorb),))
    pelea.ordenar(("habilidad", absorb))
    hasta_el_mensaje(una, pelea)
    assert mensaje_en_pantalla(una, pelea) == lo_que_dice(absorbe), (
        "la página de Absorb Aura dijo %r y el LDB dice %r"
        % (mensaje_en_pantalla(una, pelea), lo_que_dice(absorbe)))
    cerrar_y_esperar_ordenes(una, pelea)
    assert not pelea.switch(s_absorbe), "la página tenía que apagar el 135"
    enseña = lo_que_enseña(absorbe)
    assert len([h for h, si in enseña.items() if si]) >= 1
    for habilidad, la_sabe in enseña.items():
        assert sabe(una, habilidad) == la_sabe, (
            "después de Absorb Aura, la habilidad %d" % habilidad)
    for numero, valor in lo_que_cuenta(absorbe).items():
        assert variable(una, numero) == valor, (
            "la variable %d quedó en %d y la página la deja en %d"
            % (numero, variable(una, numero), valor))
    # Y las de antes siguen como estaban: la página de Absorb Aura no corrió
    # la de Detect Aura otra vez.
    for numero, valor in lo_que_cuenta(detecta).items():
        assert variable(una, numero) == valor


def test_cada_pagina_corre_una_vez_por_turno(partida):
    """`executed[i]`: una página que se cumple no vuelve a correr en el mismo
    turno aunque siga cumpliéndose. La de Detect Aura apaga su switch, así
    que esto se mira con el switch prendido **a mano** entre la página y el
    fin del turno: si la ROM la volviera a probar sin mirar lo anotado, el
    mensaje saldría dos veces antes de las órdenes."""
    una = partida(caso=CASO)
    una.poner_grupo(TALAN)
    pelea = Pelea(una)
    for _ in range(600):
        if pelea.abierta():
            break
        una.consola.correr(1)
    detect, _ = abrir_la_lista(una, pelea)
    pelea.ordenar(("habilidad", detect))
    hasta_el_mensaje(una, pelea)
    # El switch otra vez prendido, antes de que la página lo apague: la página
    # sigue y lo apaga, así que se prende después, con el mensaje cerrado.
    vistos = 1
    for n in range(1500):
        if pelea.modo() == ORDEN:
            break
        if (pelea.modo() != PAGINA
                or pelea.palabra(una.simbolos["BA_PAG_MSG"]) == 0xFFFF):
            s = una.simbolos["switches"] + 134 // 8
            octeto = una.consola.ram(s, 1)[0] | (1 << (134 % 8))
            una.consola.escribir_ram(s, [octeto])
        antes = pelea.palabra(una.simbolos["BA_PAG_MSG"])
        una.consola.apretar(*(("a",) if n % 6 < 2 else ()))
        una.consola.correr(1)
        if (pelea.modo() == PAGINA and antes == 0xFFFF
                and pelea.palabra(una.simbolos["BA_PAG_MSG"]) != 0xFFFF):
            vistos += 1
    assert pelea.modo() == ORDEN
    assert vistos == 1, "la página de Detect Aura corrió %d veces en el " \
        "turno" % vistos
