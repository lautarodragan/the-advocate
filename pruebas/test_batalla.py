"""La batalla por turnos: los HP, el daño, el orden de turnos y por dónde sigue
la página.

Es la mitad de la red que la tanda de pixeles no puede cubrir. `snes-batalla`
compara **la pantalla** contra `pantallas.pantalla_batalla` y no puede hacer
más: la pelea bloquea adentro del intérprete y no cuesta ningún tick, así que
del lado de `snes_expect.py` no hay nada dibujado —ver `OP_BATALLA` en
tools/eventos.py—. Lo que pasa adentro se mira desde acá.

**Lo que hace fuerte a este archivo** es que no se conforma con "bajó": el
modelo de `tools/batalla.py` juega la misma pelea con el mismo azar y las
mismas fórmulas, y la prueba exige que la consola dé **el número exacto** en
cada HP, turno por turno. Si la ROM y el modelo se separan en un tiro de dado
o en una división, el primer turno ya no coincide.

Las dos peleas de la intro, medidas el 2026-09-12:

    mapa 2  FightableDroid  tropa 82  Sentry Drone x1   se alcanza jugando
    mapa 9  EV0004          tropa 86  GangMember LT x4  **no se alcanza**

La segunda no es culpa de la batalla: su página la corta un `MoveEvent` con la
orden de ruta 9 —"hacia el héroe"—, que la ROM no camina. Por eso la tropa de
cuatro enemigos la ejercita `just snes-batalla`, con la página de prueba.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import lcf                                                  # noqa: E402
import batalla as modelo                                    # noqa: E402
from render_map import GAME_DIR                             # noqa: E402

from conftest import LINKAGE                                # noqa: E402

# El droide del mapa 2 está en (30,55) y se le habla desde abajo.
DROIDE = (30, 56)
TROPA_DROIDE = 82
# El grupo de la escena: Kersh, Core y Manta, que es con quienes se llega.
GRUPO = (11, 12, 13)

# Los modos de la pantalla, como `pantallas.BA_ELIGE_ORDEN` y compañía.
ORDEN, BLANCO, MENSAJE, FIN = 0, 1, 2, 3


def db():
    return lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))


class Pelea:
    """La pelea de la consola, manejada por cuadros de hardware.

    Por cuadros y no por ticks porque **el reloj del juego no corre mientras se
    ve**: es lo mismo que hace `snes-guardar` con la pantalla de ranuras, y lo
    que le da sentido a que la referencia diga que una batalla no cuesta ningún
    tick.
    """

    def __init__(self, una):
        self.una = una
        self.s = una.simbolos

    def byte(self, nombre):
        return self.una.consola.ram(self.s[nombre], 1)[0]

    def palabra(self, direccion):
        bajo, alto = self.una.consola.ram(direccion, 2)
        return bajo | (alto << 8)

    def hp(self, k):
        return self.palabra(self.s["BA_UNO"] + k * self.s["BA_BYTES"])

    def hp_guardado(self, actor):
        return self.palabra(self.s["FAR_HP"] + 2 * actor)

    def modo(self):
        return self.byte("BA_MODO")

    def abierta(self):
        return bool(self.una.byte("menu_abierto"))

    def tocar(self, boton="a", cuadros=3):
        self.una.consola.apretar(boton)
        self.una.consola.correr(cuadros)
        self.una.consola.apretar()
        self.una.consola.correr(cuadros)

    def abrir(self, tope=400):
        """Le habla al droide y pasa los cuatro cuadros de texto."""
        self.una.tocar("a")
        for _ in range(tope):
            if self.abierta():
                return self
            if self.una.byte("msg_abierto"):
                self.tocar("a", 2)
            else:
                self.una.consola.correr(1)
        raise AssertionError("la batalla no se abrió")

    def turno(self, cuantos, tope=400):
        """Un turno entero con `cuantos` actores atacando al primer enemigo."""
        for _ in range(cuantos):
            for _ in range(tope):
                if self.modo() != ORDEN:
                    break
                self.tocar()
            for _ in range(tope):
                if self.modo() != BLANCO:
                    break
                self.tocar()
        for _ in range(tope):
            if self.modo() in (ORDEN, FIN):
                return self
            self.tocar()
        raise AssertionError("el turno no terminó")

    def cerrar(self, tope=200):
        for _ in range(tope):
            if not self.abierta():
                return self
            self.tocar()
        raise AssertionError("la batalla no se cerró")


def modelo_de(base, actores=GRUPO, tropa=TROPA_DROIDE):
    return modelo.Batalla(
        [modelo.actor_de(base, a) for a in actores],
        [modelo.enemigo_de(base, e, n)
         for n, e in enumerate(base.troops[tropa].members)])


def en_el_droide(partida):
    una = partida(mapas=LINKAGE)
    una.poner_grupo(*GRUPO)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    return una


# --- los HP como estado ----------------------------------------------------

def test_los_hp_arrancan_llenos(partida):
    """`Game_Actor::Setup`: un actor nuevo arranca con los HP del nivel.

    Hasta el 2026-09-12 los HP no eran estado —el menú los mostraba llenos
    siempre— y esto es lo que lo vuelve comprobable.
    """
    una = partida()
    base = db()
    pelea = Pelea(una)
    for actor in GRUPO:
        assert pelea.hp_guardado(actor) == base.actors[actor].hp_max[0], \
            "el actor %d no arranca con los HP del nivel" % actor


def test_los_hp_viajan_en_la_partida(partida):
    """Bajarlos, guardar y volver a cargar tiene que devolver los mismos.

    Es lo que obliga a que `FAR_HP` esté en `partida_tabla`: sin eso una
    partida cargada después de una pelea volvería con todos llenos, que es
    justo lo que hacía la ROM antes de que los HP existieran.

    La prueba **resetea la consola de verdad**, como `test_guardar.py`: la
    SRAM sobrevive al reset y por eso lo que vuelve salió del cartucho. Se
    pisan los HP en la RAM antes de reiniciar porque snes9x no la borra —está
    en ESTADO.md— así que sin eso el 7 podría ser el de antes.
    """
    una = partida(guardar=200)
    pelea = Pelea(una)
    una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * GRUPO[0], [7, 0])
    una.guardar_en()
    una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * GRUPO[0], [99, 0])
    una.reiniciar()
    assert pelea.hp_guardado(GRUPO[0]) == 7, \
        "los HP no volvieron de la SRAM: quedaron en %d" \
        % pelea.hp_guardado(GRUPO[0])


# --- la pelea del droide ---------------------------------------------------

def test_la_pelea_del_droide_se_abre_con_la_tropa_del_juego(partida):
    """El `EnemyEncounter` del `FightableDroid`: tropa 82, un Sentry Drone.

    Los parámetros del enemigo salen del LDB y los del grupo de
    `eq_parametro`, la misma función que la pantalla de equipo. Que coincidan
    con `batalla.py` es lo que hace que el resto de este archivo signifique
    algo: si la ROM peleara con otros números, los turnos también darían otra
    cosa y no se sabría cuál de las dos está mal.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    base = db()
    esperado = modelo_de(base)
    assert pelea.byte("BA_NACT") == 3
    assert pelea.byte("BA_NENE") == 1
    for k, quien in enumerate(esperado.actores + [None] + esperado.enemigos):
        if quien is None:
            continue
        d = una.simbolos["BA_UNO"] + k * una.simbolos["BA_BYTES"]
        assert pelea.palabra(d + 0) == quien.hp, "los HP del %d" % k
        assert pelea.palabra(d + 4) == quien.ataque, "el ataque del %d" % k
        assert pelea.palabra(d + 6) == quien.defensa, "la defensa del %d" % k
        assert pelea.palabra(d + 8) == quien.agilidad, "la agilidad del %d" % k


def test_la_chance_de_huir_es_la_de_rm2k(partida):
    """`Scene_Battle::InitEscapeChance`, con la división entera de los dos
    lados. Con el droide da cero: es cinco veces más ágil que el grupo."""
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    assert pelea.byte("BA_HUIDA") == modelo_de(db()).huida_chance


def test_la_pelea_entera_da_los_mismos_hp_que_el_modelo(partida):
    """El corazón de todo esto: turno por turno, el mismo número.

    Los tres actores atacan al droide y la consola tiene que llegar al mismo HP
    que `batalla.Batalla` en cada uno de los doce valores. Ahí adentro están el
    orden de turnos, los tres tiros de cada golpe —acierto, crítico y
    varianza—, el daño con `atk / 2 - def / 4`, la mitad del que se defiende y
    el reapuntado del blanco muerto. **Si cualquiera de esos se separa, el
    primer turno ya no coincide.**

    Con estos números la pelea la gana el grupo en tres turnos y Core cae en el
    segundo, así que el caso además pasa por un actor muerto —que no actúa y al
    que el droide ya no puede elegir— sin tener que forzarlo.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(db())
    for turno in range(1, 8):
        pelea.turno(len(esperado.vivos(esperado.actores)))
        esperado.jugar_turno(
            [(modelo.ORDEN_ATACAR, 0)] * len(esperado.vivos(esperado.actores)))
        de_la_rom = [pelea.hp(k) for k in range(3)] + [pelea.hp(4)]
        del_modelo = [c.hp for c in esperado.actores] + [esperado.enemigos[0].hp]
        assert de_la_rom == del_modelo, \
            "turno %d: la consola dejó %r y el modelo %r" % (
                turno, de_la_rom, del_modelo)
        if esperado.resultado is not None:
            break
    assert esperado.resultado == modelo.VICTORIA, \
        "la pelea de banco tendría que terminar en victoria"
    assert pelea.modo() == FIN
    assert pelea.byte("BA_RESULT") == modelo.VICTORIA


def test_ganar_sigue_por_el_victory_handler(partida):
    """`VictoryHandler`: los dos cuadros de texto de CORE y KERSH.

    Es lo que cobra el parcheo de los tres destinos del opcode: si el cursor
    volviera al comando siguiente en vez de saltar al manejador, la página
    terminaría ahí y no se vería ningún mensaje. Y los HP con los que se salió
    de la pelea tienen que quedar en la partida.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(db())
    while esperado.resultado is None:
        pelea.turno(len(esperado.vivos(esperado.actores)))
        esperado.jugar_turno(
            [(modelo.ORDEN_ATACAR, 0)] * len(esperado.vivos(esperado.actores)))
    quedaron = [pelea.hp(k) for k in range(3)]
    pelea.cerrar()
    assert [pelea.hp_guardado(a) for a in GRUPO] == quedaron, \
        "los HP de la pelea no quedaron en la partida"
    mensajes = 0
    for _ in range(600):
        if una.byte("msg_abierto"):
            mensajes += 1
            una.tocar("a")
        else:
            una.correr(1)
        if mensajes and not una.corriendo_una_pagina():
            break
    assert mensajes == 2, \
        "el VictoryHandler abre dos cuadros de texto y abrió %d" % mensajes
    assert una.mapa() == 2, "la pelea tiene que volver al mapa donde estaba"


def test_perder_sigue_por_el_defeat_handler(partida):
    """`DefeatHandler`: con `defeat_mode` 1 no hay Game Over, sigue la página.

    Se llega poniéndole un HP a cada uno antes de pelear, que es lo que hace
    comprobable un camino que jugando cuesta media hora de mala suerte.
    """
    una = en_el_droide(partida)
    for actor in GRUPO:
        una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * actor, [1, 0])
    pelea = Pelea(una).abrir()
    for _ in range(12):
        vivos = sum(1 for k in range(3) if pelea.hp(k))
        if pelea.modo() == FIN:
            break
        pelea.turno(vivos)
    assert pelea.byte("BA_RESULT") == modelo.DERROTA, \
        "con un HP cada uno la pelea se pierde"
    pelea.cerrar()
    mensajes = 0
    for _ in range(600):
        if una.byte("msg_abierto"):
            mensajes += 1
            una.tocar("a")
        else:
            una.correr(1)
        if mensajes and not una.corriendo_una_pagina():
            break
    assert mensajes == 1, \
        "el DefeatHandler abre un cuadro de texto y abrió %d" % mensajes


def test_la_pelea_no_gasta_ningun_tick(partida):
    """La regla que sostiene la comparación de pixeles: `vueltas` no avanza
    mientras se ve la pantalla.

    Es lo mismo que la pantalla de ranuras y la tienda, y es lo que le permite
    a la referencia salir del opcode en el mismo tick tarde lo que tarde el
    jugador. Sin esto, `OP_BATALLA` tendría que modelar cuántos cuadros dura
    una pelea, que es justo lo que no se puede medir honestamente.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    antes = una.palabra("vueltas")
    una.consola.correr(240)
    assert una.palabra("vueltas") == antes, \
        "el reloj del juego corrió durante la batalla"
