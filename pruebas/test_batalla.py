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
from consola import en_la_rom, en_la_wram                  # noqa: E402

# El droide del mapa 2 está en (30,55) y se le habla desde abajo.
DROIDE = (30, 56)
TROPA_DROIDE = 82
# El grupo de la escena: Kersh, Core y Manta, que es con quienes se llega.
GRUPO = (11, 12, 13)

# Los modos de la pantalla, como `pantallas.BA_ELIGE_ORDEN` y compañía.
ORDEN, BLANCO, ITEM, ACTOR, MENSAJE, FIN = range(6)
# Las cinco órdenes, como `pantallas.BA_ORDENES`.
(O_ATACAR, O_DEFENDER, O_USAR, O_HABILIDAD, O_HUIR) = range(5)
# La Potion del LDB: cincuenta HP planos, que es el ítem de curar más barato
# y el único que hace falta para cobrar la cuenta.
POCION = 1
# Y uno que **no** se puede usar en una pelea: el Theatre Key, un ítem de
# trama. Va en el inventario a propósito, para que la lista tenga algo que
# dejar afuera; sin él, ofrecer todo y ofrecer lo correcto dan lo mismo.
LLAVE = 151
# Un tema para el mapa del droide, que no trae ninguno: sin él no se puede
# comprobar que el tema del mapa vuelva al terminar la pelea.
TEMA_DEL_MAPA = "escape_newyork"
# Qué dice el mensaje, como `BA_MSG_ATAQUE` en main.s.
MSG_ATAQUE = 0
# El nombre de la constante de la ROM para cada caso del reparto.
PENDIENTE_DE = {"errar": "BA_SE_ERRAR",
                "dano_actor": "BA_SE_DANO_ACTOR",
                "dano_enemigo": "BA_SE_DANO_ENEMIGO",
                "muerte": "BA_SE_MUERTE"}


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


def en_el_droide(partida, tema=None):
    una = partida(mapas=LINKAGE, tema=tema)
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


# --- el audio de la pelea --------------------------------------------------
#
# Esto es lo que ninguna prueba de pixeles puede ver: **el silencio no cambia
# un pixel**, que es el argumento que ESTADO.md ya dejó escrito con los dos
# defectos de audio del 2026-09-12. El caso `batalla` de la tanda compara la
# pantalla y da cero con la pelea muda.
#
# Lo que se pregunta acá es lo mismo que en `test_musica_paquete.py`: qué dice
# la ROM estar tocando, y si lo que dice tocar tiene sus muestras arriba.

def sonido_muestra(una, indice):
    """La muestra que le toca a una fila de `sonido_tabla`, leída del
    cartucho: siete bytes por entrada y la muestra es el primero.

    Se lee de la ROM y no se recalcula, por lo mismo que `muestras_del_tema`:
    recalcularla sería una segunda manera de contestar la pregunta, y las dos
    se pueden equivocar igual.
    """
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    return rom[en_la_rom(una.simbolos["sonido_tabla"]) + 7 * indice]


def se_disparado(una):
    """La muestra del efecto que la ROM acaba de dejar pendiente.

    `op_sonido` y `sonido_tocar` copian los siete bytes de la fila a `SE_NUEVO`
    y prenden `SE_PENDIENTE`; `irq_musica` lo levanta en el cuadro siguiente y
    a partir de ahí lo que queda es `SE_CUADROS`. Acá se mira `SE_NUEVO`, que
    es lo que sobrevive a leer la RAM entre cuadro y cuadro.
    """
    return una.consola.ram(en_la_wram(una.simbolos["SE_NUEVO"]), 1)[0]


def test_la_pelea_prende_el_tema_de_batalla_del_ldb(partida):
    """`Scene_Battle`, al construirse: `BgmPlay(GetSystemBGM(BGM_Battle))`.

    El tema sale del LDB —`battle_music`, que en el ABL es
    T_VGFighterMAX_Masako— y no de una elección nuestra, igual que el de la
    pantalla de título. Y no alcanza con que `tema_actual` lo diga: las
    muestras que su stream escribe en SRCN tienen que estar en la ARAM, o son
    notas contra el bloque de silencio. Por eso el tema se anota en el paquete
    de audio **del mapa que tiene la pelea**, que es lo que hace
    `eventos.audio_de_batalla`.
    """
    una = en_el_droide(partida)
    tema = una.simbolos["BA_TEMA"]
    assert tema != 0xFF, "esta ROM no lleva tema de batalla: el caso no mide nada"
    Pelea(una).abrir()
    assert una.palabra("tema_actual") == tema, (
        "la pelea dice estar tocando el tema %d y el de batalla es el %d"
        % (una.palabra("tema_actual"), tema))
    assert not una.byte("music_apagada"), \
        "la pelea arrancó callada: `batalla_bgm` no llegó a prender el tema"
    faltan = sorted(set(una.muestras_del_tema(tema)) - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema de batalla suena con las muestras %s sin subir de las %s que "
        "usa" % (faltan, sorted(una.muestras_del_tema(tema))))


def cursor_del_stream(una):
    """Por dónde va el stream de música: los tres bytes de `music`.

    Avanza solo y nunca vuelve atrás mientras dure un tema —el de batalla son
    226 segundos y ninguna de estas peleas llega—, así que verlo **bajar** es
    ver un `music_start`.
    """
    bajo, alto, banco = una.consola.ram(una.simbolos["music"], 3)
    return bajo | (alto << 8) | (banco << 16)


def test_ganar_prende_el_tema_de_la_victoria(partida):
    """El `BGM_Victory` de `Scene_Battle_Rpg2k`, al quedarse sin enemigos.

    En el ABL `battle_end_music` es **el mismo** que `battle_music`, así que
    mirar `tema_actual` no distingue nada: ya vale eso desde que la pelea
    empezó, y sacarle el `music_start` del final da verde igual. Lo que sí se
    ve es que el stream **vuelve a empezar**, que es lo que `music_start`
    hace: el cursor de `music` avanza solo y nunca retrocede.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(db())
    antes = None
    while esperado.resultado is None:
        antes = cursor_del_stream(una)
        pelea.turno(len(esperado.vivos(esperado.actores)))
        esperado.jugar_turno(
            [(modelo.ORDEN_ATACAR, 0)] * len(esperado.vivos(esperado.actores)))
    assert pelea.byte("BA_RESULT") == modelo.VICTORIA
    assert una.palabra("tema_actual") == una.simbolos["BA_TEMA_FIN"], \
        "al ganar tiene que sonar el battle_end_music del LDB"
    assert not una.byte("music_apagada")
    assert cursor_del_stream(una) < antes, (
        "el tema de la victoria tiene que arrancar de cero: el cursor del "
        "stream quedó en $%06X y antes del último turno estaba en $%06X"
        % (cursor_del_stream(una), antes))


def test_al_terminar_vuelve_lo_que_sonaba_en_el_mapa(partida):
    """El `before_battle_music` de RM2k: `Scene_Battle` lo anota al entrar y
    `Game_Map` lo repone al volver.

    El mapa 2 **no trae música**, así que sin `--tema-de-arranque` lo que
    tiene que volver es el silencio —y eso no distingue nada: al salir se
    recarga el paquete del mapa, y recargarlo ya calla—. Con un tema puesto el
    caso mide de verdad: si el `batalla_bgm` del final no estuviera, el mapa
    quedaría mudo después de cada pelea.

    Y además el tema del mapa tiene que volver **con sus muestras**: el
    paquete de la pelea las desaloja, así que salir sin recargar el del mapa
    dejaría el tema sonando contra el bloque de silencio.
    """
    una = en_el_droide(partida, tema=TEMA_DEL_MAPA)
    tema = una.palabra("tema_actual")
    assert not una.byte("music_apagada"), \
        "el mapa tenía que arrancar con su tema: el caso no mide nada"
    pelea = Pelea(una).abrir()
    assert una.palabra("tema_actual") == una.simbolos["BA_TEMA"], \
        "la pelea tiene que tapar el tema del mapa"
    esperado = modelo_de(db())
    while esperado.resultado is None:
        pelea.turno(len(esperado.vivos(esperado.actores)))
        esperado.jugar_turno(
            [(modelo.ORDEN_ATACAR, 0)] * len(esperado.vivos(esperado.actores)))
    pelea.cerrar()
    # Y hay que dejarla terminar: reponer el paquete del mapa son **65 cuadros
    # medidos**, porque son cincuenta kilobytes que viajan al SPC700 por los
    # cuatro puertos. `cerrar` vuelve en cuanto `menu_abierto` se apaga, que es
    # antes; sin esperar, lo que se mira es una ARAM a medio llenar.
    for _ in range(300):
        if una.palabra("tema_actual") == tema and not una.byte("music_apagada"):
            break
        una.consola.correr(1)
    assert not una.byte("music_apagada"), \
        "al salir de la pelea el mapa se quedó mudo"
    assert una.palabra("tema_actual") == tema, (
        "al salir de la pelea tenía que volver el tema %d y quedó el %d"
        % (tema, una.palabra("tema_actual")))
    faltan = sorted(set(una.muestras_del_tema(tema)) - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema del mapa volvió con las muestras %s sin subir: el paquete de "
        "la pelea las desalojó y nadie recargó el del mapa" % faltan)


def mirar_los_golpes(una, pelea, esperados):
    """Va por los mensajes de un turno mirando qué efecto salió en cada golpe.

    Devuelve qué casos del reparto se vieron, para que la prueba pueda exigir
    que alguno se haya visto: un turno que no llegue a ningún golpe no
    probaría nada.
    """
    vistos = set()
    for _ in range(30):
        if pelea.modo() != MENSAJE:
            break
        if pelea.byte("BA_MTIPO") != MSG_ATAQUE:
            pelea.tocar()
            continue
        dano = pelea.palabra(una.simbolos["BA_MDANO"])
        blanco = pelea.byte("BA_MBLA")
        quien = pelea.byte("BA_MQUIEN")
        if dano == 0xFFFF:
            cual = "errar"
        elif blanco < una.simbolos["BA_GRUPO_MAX"]:
            cual = "dano_actor"
        elif pelea.hp(blanco) == 0:
            cual = "muerte"
        else:
            cual = "dano_enemigo"
        if quien >= una.simbolos["BA_GRUPO_MAX"]:
            # Pega un enemigo: primero el suyo, y el del daño espera su turno.
            primero, pendiente = "ataque", cual
        else:
            primero, pendiente = cual, None
        assert se_disparado(una) == esperados[primero], (
            "el golpe tenía que sonar con %s —la muestra %d— y sonó con la %d"
            % (primero, esperados[primero], se_disparado(una)))
        sigue = pelea.palabra(una.simbolos["BA_SE2"])
        if pendiente is None:
            assert sigue == 0xFFFF, \
                "un golpe del grupo no deja ningún efecto pendiente"
        else:
            assert sigue == una.simbolos[PENDIENTE_DE[pendiente]], (
                "el golpe de un enemigo tenía que dejar %s pendiente y dejó "
                "$%04X" % (pendiente, sigue))
        vistos.add(primero)
        pelea.tocar()
    return vistos


def test_el_golpe_suena_con_el_efecto_que_le_toca(partida):
    """Cuál de los cinco efectos del LDB sale en cada golpe.

    El reparto es el de easyrpg-player y está escrito en
    `eventos.AUDIO_BATALLA`: errar es `GetFailureSe` —dodge_se—, pegarle a un
    actor es actor_damaged_se, y a un enemigo enemy_damaged_se salvo que lo
    mate, que es el enemy_death_se de `ProcessBattleActionDeath`. Cuando el que
    pega es un enemigo, primero suena su enemy_attack_se y el del daño queda
    pendiente en `BA_SE2`, que es lo que RM2k hace con dos efectos y acá hace
    falta porque **hay una sola voz**.

    Lo que se compara no es circular: `BA_MDANO` y `BA_MBLA` son la mecánica,
    que el resto de este archivo ya cobra contra `batalla.py` número por
    número; lo que se mide acá es la elección del efecto, que es lo nuevo.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperados = {
        "errar": sonido_muestra(una, una.simbolos["BA_SE_ERRAR"]),
        "ataque": sonido_muestra(una, una.simbolos["BA_SE_ATAQUE"]),
        "dano_enemigo": sonido_muestra(una, una.simbolos["BA_SE_DANO_ENEMIGO"]),
        "dano_actor": sonido_muestra(una, una.simbolos["BA_SE_DANO_ACTOR"]),
        "muerte": sonido_muestra(una, una.simbolos["BA_SE_MUERTE"]),
    }
    vistos = set()
    for _ in range(8):
        if pelea.modo() == FIN:
            break
        vivos = len([k for k in range(3) if pelea.hp(k)])
        for _ in range(vivos):
            for _ in range(400):
                if pelea.modo() != ORDEN:
                    break
                pelea.tocar()
            for _ in range(400):
                if pelea.modo() != BLANCO:
                    break
                pelea.tocar()
        vistos |= mirar_los_golpes(una, pelea, esperados)
    assert vistos, "ningún golpe llegó a sonar: la prueba no midió nada"


# --- usar un ítem ----------------------------------------------------------
#
# `Use Item`, desde el 2026-09-13. Lo que se mide acá es lo mismo que en el
# resto del archivo: **el número exacto**. `batalla.curacion` dice cuánto
# tendría que curar y la consola tiene que dejar ese HP, ni uno más.

def en_el_droide_con_pocion(partida, cuantas=3):
    """La pelea del droide con pociones en el inventario y el grupo herido.

    Herido a mano y no peleando: pelear hasta que a alguien le falten HP
    depende del azar, y lo que este caso mide es la cura.
    """
    una = partida(mapas=LINKAGE, items=(POCION, cuantas, LLAVE, 1))
    una.poner_grupo(*GRUPO)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    for actor in GRUPO:
        una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * actor, [1, 0])
    return una


def test_la_lista_de_items_es_la_que_se_puede_usar(partida):
    """`Game_Party::IsItemUsable` con la pelea abierta, más lo que este port
    sabe hacer: ver `batalla.item_usable_en_batalla`.

    La lista la arma la ROM recorriendo el inventario, y lo que se compara es
    contra la misma regla en Python. Si la ROM ofreciera un ítem que no cura
    —un arma, un libro— el jugador podría gastarlo sin que pasara nada.
    """
    una = en_el_droide_con_pocion(partida)
    pelea = Pelea(una).abrir()
    for _ in range(O_USAR):
        pelea.tocar("right")
    assert pelea.byte("BA_ORDEN") == O_USAR
    pelea.tocar()
    assert pelea.modo() == ITEM, "A sobre `Use Item` abre la lista"
    base = db()
    esperados = [n for n in sorted(base.items)
                 if modelo.item_usable_en_batalla(base.items[n])]
    # De ésos, los que hay en el inventario.
    hay = [n for n in esperados if una.item(n)]
    assert hay, "el caso no puso ningún ítem usable: no mide nada"
    assert una.item(LLAVE), (
        "el caso no puso ningún ítem inusable: ofrecer todo y ofrecer lo que "
        "corresponde darían lo mismo y no mediría nada")
    assert pelea.byte("BA_ITEM_N") == len(hay), (
        "la ROM ofrece %d ítems y los usables que hay son %d: %s"
        % (pelea.byte("BA_ITEM_N"), len(hay), hay))


def test_usar_una_pocion_cura_lo_que_dice_el_modelo(partida):
    """`Game_BattleAlgorithm::Item`: `rate * hp_max / 100 + hp`, topado contra
    lo que falta.

    Con la Potion —cincuenta planos— y un actor en 1 HP de 40, lo que tiene
    que quedar son los 40: el tope es lo que falta y no lo que el ítem cura.
    Eso es justamente lo que se equivoca solo si uno suma sin topar.
    """
    una = en_el_droide_con_pocion(partida)
    pelea = Pelea(una).abrir()
    base = db()
    esperado = modelo_de(base)
    for quien in esperado.actores:
        quien.hp = 1
    antes = una.item(POCION)
    # El primer actor usa la poción sobre sí mismo; los otros dos atacan.
    for _ in range(O_USAR):
        pelea.tocar("right")
    pelea.tocar()                       # abre la lista
    pelea.tocar()                       # elige el primero
    assert pelea.modo() == ACTOR
    pelea.tocar()                       # sobre el primer actor
    assert una.item(POCION) == antes - 1, (
        "la poción se gasta al elegirla, como en RM2k")
    for _ in range(2):
        for _ in range(400):
            if pelea.modo() != ORDEN:
                break
            pelea.tocar()
        for _ in range(400):
            if pelea.modo() != BLANCO:
                break
            pelea.tocar()
    for _ in range(400):
        if pelea.modo() in (ORDEN, FIN):
            break
        pelea.tocar()
    esperado.jugar_turno(
        [(modelo.ORDEN_ITEM, (base.items[POCION], 0)),
         (modelo.ORDEN_ATACAR, 0), (modelo.ORDEN_ATACAR, 0)])
    de_la_rom = [pelea.hp(k) for k in range(3)]
    del_modelo = [c.hp for c in esperado.actores]
    assert de_la_rom == del_modelo, (
        "la consola dejó %r y el modelo %r" % (de_la_rom, del_modelo))
    assert de_la_rom[0] == esperado.actores[0].hp_max, (
        "la poción cura cincuenta sobre cuarenta de máximo: tiene que topar")


def test_tech_skill_no_hace_nada_y_escape_sigue_donde_va(partida):
    """Las dos órdenes del final del menú.

    `Tech Skill` está en gris y A no la toma —a este nivel nadie sabe ninguna
    habilidad: las de los cuatro actores se aprenden en el nivel 3 y este port
    tiene a todos en el 1— y `Escape` quedó quinta, que es donde va en el menú
    del ABL. Lo que este caso cobra es que el cursor **pase por encima** de la
    que no hace nada en vez de quedarse trabado ahí.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    for _ in range(4):
        pelea.tocar("right")
    assert pelea.byte("BA_ORDEN") == O_HUIR, \
        "el cursor tiene que llegar hasta `Escape`, que ahora es la quinta"
    for _ in range(3):
        pelea.tocar("left")
    assert pelea.byte("BA_ORDEN") == O_DEFENDER
    pelea.tocar("right")
    assert pelea.byte("BA_ORDEN") == O_USAR
    pelea.tocar("right")
    assert pelea.byte("BA_ORDEN") == O_HABILIDAD
    pelea.tocar()
    assert pelea.modo() == ORDEN, \
        "A sobre `Tech Skill` no tiene que llevar a ningún lado"
