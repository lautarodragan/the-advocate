"""La pelea de la consola, manejada desde afuera, y lo que las pruebas de
pelea comparten: el droide del mapa 2, el grupo de la intro, el modelo de
`port.battle`, perder sin pelear, la experiencia, los textos de la pantalla y
volver del Game Over.

**Todo en cuadros de hardware**: la pelea corre su propio lazo y `ticks` no
avanza mientras dura.
"""

from port import battle as modelo
from port import events
from port import menus
from port import screens

from consola import EMPEZAR, en_la_rom, en_la_wram
import datos
from tanda import LINKAGE

# El droide del mapa 2 está en (30,55) y se le habla desde abajo.
DROIDE = (30, 56)
TROPA_DROIDE = 82
# El grupo de la escena: Kersh, Core y Manta, que es con quienes se llega.
GRUPO = (11, 12, 13)

# Los modos de la pantalla y las cinco órdenes del menú **se leen de la tabla
# de símbolos**: `Pelea.modo()` contesta el nombre de la constante `BA_M_*` de
# la ROM sin el prefijo —"COMMAND", "TARGET", "END"...— y las órdenes son
# `BA_COMMAND_ATTACK` y compañía. El orden es el del original —Attack /
# <habilidad> / Defend / Use Item— y `Escape` va quinta, que es la
# simplificación que `port/battle.py` declara.


class Pelea:
    """La pelea de la consola, manejada por cuadros de hardware.

    Por cuadros y no por ticks porque **el reloj del juego no corre mientras se
    ve**: es lo mismo que pasa con la pantalla de ranuras, y por eso una
    batalla no cuesta ningún tick.
    """

    def __init__(self, una):
        self.una = una
        self.s = una.simbolos
        self._modos = {int(valor): nombre[len("BA_M_"):]
                       for nombre, valor in self.s.tabla.items()
                       if nombre.startswith("BA_M_")}

    def byte(self, nombre):
        return self.una.consola.ram(self.s[nombre], 1)[0]

    def palabra(self, direccion):
        bajo, alto = self.una.consola.ram(direccion, 2)
        return bajo | (alto << 8)

    # Los HP y SP **de la pelea**: la ranura `BA_ONE` del combatiente `k`, que
    # es el puesto en la pantalla —0 a 2 los actores, desde `BA_PARTY_MAX` los
    # enemigos— y no el número de actor. Los de la partida son
    # `Partida.hp(actor)`, y la pelea los copia ahí recién al terminar.

    def hp_del_combatiente(self, k):
        return self.palabra(self.s["BA_ONE"] + k * self.s["BA_BYTES"])

    def sp_del_combatiente(self, k):
        return self.palabra(self.s["BA_ONE"] + k * self.s["BA_BYTES"]
                            + self.s["BA_SP"])

    def modo(self):
        """El nombre del modo de la pantalla: el de su `BA_M_*` sin el
        prefijo. Un valor que no es de ninguno vuelve como número."""
        valor = self.byte("BA_MODE")
        return self._modos.get(valor, valor)

    def orden(self, nombre):
        """El número de la orden del menú: `BA_COMMAND_<nombre>`."""
        return self.s["BA_COMMAND_" + nombre]

    def abierta(self):
        return bool(self.una.byte("menu_open"))

    def tocar_cuadros(self, boton="a", aire=3):
        """`Partida.tocar_cuadros`, con A y tres de aire por omisión: la pelea
        congela el reloj del juego."""
        self.una.tocar_cuadros(boton, aire)

    def abrir(self, tope=400):
        """Le habla al droide y pasa los cuatro cuadros de texto."""
        self.una.tocar_ticks("a")
        for _ in range(tope):
            if self.abierta():
                return self
            if self.una.byte("msg_open"):
                self.tocar_cuadros("a", 2)
            else:
                self.una.consola.run(1)
        raise AssertionError("la batalla no se abrió")

    def switch(self, numero):
        """Si el switch `numero` está prendido. El bitmap es el mismo que usan
        los eventos: un bit por switch, en el orden del `switch_id` del LDB."""
        byte = self.una.consola.ram(
            en_la_wram(self.s["switches"] + numero // 8), 1)[0]
        return bool(byte & (1 << (numero % 8)))

    def esperar(self, modo, tope=400):
        for _ in range(tope):
            if self.modo() == modo:
                return self
            self.una.consola.run(1)
        raise AssertionError("la pelea no llegó al modo %s, quedó en %s"
                             % (modo, self.modo()))

    def ordenar(self, que, tope=400):
        """Le da a un actor la orden `que` y deja el cursor en el que sigue.

        `que` es `("atacar", enemigo)`, `("defender",)` o
        `("habilidad", k, blanco)`, donde `k` es el lugar en la lista de
        habilidades del actor —la misma que `battle.skills_of` arma— y
        `blanco` el lugar del enemigo o del actor al que apunta, según su
        `scope`. Una de switch va sin blanco, `("habilidad", k)`: no lo pide.
        """
        self.esperar("COMMAND", tope)
        cual = que[0]
        pasos = self.orden({"atacar": "ATTACK", "defender": "DEFEND",
                            "habilidad": "SKILL"}[cual])
        # El cursor primero a la izquierda del todo: volver de la lista de
        # habilidades con B lo deja donde estaba, así que contar derechas desde
        # donde quedó elegiría otra orden.
        for _ in range(5):
            self.tocar_cuadros("left")
        for _ in range(pasos):
            self.tocar_cuadros("right")
        assert self.byte("BA_COMMAND") == pasos, (
            "el cursor tenía que quedar en la orden %d y quedó en %d"
            % (pasos, self.byte("BA_COMMAND")))
        self.tocar_cuadros()
        if cual == "defender":
            return self
        if cual == "habilidad":
            self.esperar("SKILL", tope)
            for _ in range(que[1]):
                self.tocar_cuadros("right")
            assert self.byte("BA_SKILL_SEL") == que[1]
            self.tocar_cuadros()
            if len(que) == 2:
                # Una de switch no pide blanco: `Scene_Battle::AssignSkill`
                # la anota sobre el que la usa. El cursor ya está en el que
                # sigue, o el turno ya arrancó.
                assert self.modo() not in ("TARGET", "ACTOR"), \
                    "una habilidad de switch pidió blanco"
                return self
        # El blanco: los enemigos se eligen con el cursor hacia abajo desde el
        # primero vivo, y el grupo igual.
        for _ in range(tope):
            if self.modo() in ("TARGET", "ACTOR"):
                break
            self.una.consola.run(1)
        else:
            raise AssertionError("la orden no pidió blanco")
        destino = que[-1]
        for _ in range(destino):
            self.tocar_cuadros("down")
        self.tocar_cuadros()
        return self

    def correr_turno(self, tope=600):
        """Con las órdenes ya dadas, pasa los mensajes hasta que el turno
        termina."""
        for _ in range(tope):
            if self.modo() in ("COMMAND", "END"):
                return self
            self.tocar_cuadros()
        raise AssertionError("el turno no terminó")

    def turno(self, cuantos, tope=400):
        """Un turno entero con `cuantos` actores atacando al primer enemigo."""
        for _ in range(cuantos):
            for _ in range(tope):
                if self.modo() != "COMMAND":
                    break
                self.tocar_cuadros()
            for _ in range(tope):
                if self.modo() != "TARGET":
                    break
                self.tocar_cuadros()
        for _ in range(tope):
            if self.modo() in ("COMMAND", "END"):
                return self
            self.tocar_cuadros()
        raise AssertionError("el turno no terminó")

    def cerrar(self, tope=200, transicion=600):
        """Toca A hasta que la pelea termina, y espera a que el mapa vuelva
        a correr.

        Lo segundo es por la transición de salida —`fundido_de_pelea.s`—, que
        dura de dos a tres segundos entre el mosaico, la carga del paquete del
        mapa en negro y el fundido de vuelta, **sin que corra ningún tick**:
        un `Partida.correr(1)` justo después se daba por colgado, porque le da
        a cada tick sesenta cuadros por lado.
        """
        for _ in range(tope):
            if not self.abierta():
                break
            self.tocar_cuadros()
        else:
            raise AssertionError("la batalla no se cerró")
        vueltas = self.una.palabra("ticks")
        for _ in range(transicion):
            if self.una.palabra("ticks") != vueltas:
                return self
            self.una.consola.run(1)
        raise AssertionError("el mapa no volvió a correr después de la pelea")


def modelo_de(base, actores=GRUPO, tropa=TROPA_DROIDE, **extra):
    return modelo.Battle(
        [modelo.actor_of(base, a) for a in actores],
        modelo.troop_enemies(base, tropa), **extra)


def en_el_droide(partida, con_musica=None):
    # El mapa del droide no trae tema, y sin uno no se puede comprobar que el
    # del mapa vuelva al terminar la pelea: con `con_musica` se llega con el
    # de la apertura sonando, que un mapa sin tema deja seguir.
    if con_musica:
        una = con_musica()
    else:
        una = partida(caso=LINKAGE)
    una.poner_grupo(*GRUPO)
    una.ir_al_mapa(2, *DROIDE)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])
    return una


def hab_id(una, k):
    """El número de RM2k de la habilidad `k` del cartucho.

    Se lee de la tabla que emitió el conversor y no se recalcula, por lo mismo
    que `sonido_muestra` de `test_batalla.py`: recalcularlo sería una segunda
    manera de contestar la pregunta, y las dos se pueden equivocar igual.
    """
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    donde = en_la_rom(una.simbolos["skill_id"]) + 2 * k
    return rom[donde] | (rom[donde + 1] << 8)


# --- perder sin pelear ------------------------------------------------------
#
# Con todo el grupo en cero HP, `battle_run` contesta derrota antes de abrir
# la pantalla —el `ba_next_actor` que devuelve $FF—, así que las pruebas
# de Game Over y de `FullHeal` no dependen de ningún tiro de dado.

# Cuántos ticks se le dan a la página `pelea-82-curar` para perder la pelea y
# correr el manejador. La pelea sale a los 18 y, perdida sin pelear, no abre
# pantalla.
DESPUES_DE_PERDER = 60


def sin_hp(una):
    """Todo el grupo caído, escrito en la RAM lejana."""
    largo = una.simbolos["FAR_SP"] - una.simbolos["FAR_HP"]
    una.consola.write_ram(una.simbolos["FAR_HP"], [0] * largo)
    return una


def cuadros_hasta_reiniciar(una, tope=900):
    """Cuántos cuadros de hardware pasan hasta que `ticks` se va para atrás.

    Se cuenta en cuadros y no en ticks a propósito: `Partida.correr` avanza
    hasta que `ticks` **suba**, y un reinicio la pone en cero, así que
    esperar un tick después del Game Over no terminaría nunca.
    """
    alto = una.palabra("ticks")
    for n in range(tope):
        una.consola.run(1)
        ahora = una.palabra("ticks")
        if ahora < alto:
            return n
        alto = ahora
    return None


def en_el_game_over(una):
    """Si la pantalla de Game Over está a la vista, esperando la tecla: es
    `GO_WAIT`, que la ROM prende al terminar el fundido de entrada. Ver
    runtime/game_over.s."""
    return una.consola.ram(en_la_wram(una.simbolos["GO_WAIT"]), 1)[0] != 0


def cuadros_hasta_el_game_over(una, tope=900):
    """Cuántos cuadros de hardware pasan hasta que la pantalla de Game Over
    espera la tecla, o `None`. Desde el 2026-09-28 perder no reinicia la ROM
    hasta que se aprieta: mirar `ticks` sola ya no alcanza."""
    for n in range(tope):
        if en_el_game_over(una):
            return n
        una.consola.run(1)
    return None


def pasar_el_game_over(una, tope=900):
    """Espera la pantalla de Game Over y la cierra con A: devuelve cuántos
    cuadros tardó en reiniciarse después, o `None` si no se reinició. Si la
    pantalla no llegó, es un error, no un `None`."""
    assert cuadros_hasta_el_game_over(una, tope) is not None, (
        "la pantalla de Game Over no llegó a esperar la tecla en %d cuadros"
        % tope)
    una.consola.hold("a")
    una.consola.run(2)
    una.consola.hold()
    return cuadros_hasta_reiniciar(una, tope)


def con_encuentros(partida):
    """El mapa de `test-special` con encuentros al azar y el grupo de la
    intro, que los gana en un turno."""
    return partida(caso="grupo-11-12-13", en="test-special")


# --- el grupo, leído de la RAM ------------------------------------------------

def grupo_de(una):
    """Hasta `party_n`: las ranuras de más no se limpian y traen basura."""
    return list(una.consola.ram(una.simbolos["party"], una.palabra("party_n")))


def sabe(una, actor, habilidad):
    """Si el actor sabe la habilidad: su bit en `FAR_SKILL`, con el índice de
    pares del cartucho de pruebas."""
    r = datos.ranuras_de_habilidad()[(actor, habilidad)]
    octeto = una.consola.ram(una.simbolos["FAR_SKILL"] + (r >> 3), 1)[0]
    return bool(octeto & (1 << (r & 7)))


# --- la experiencia -----------------------------------------------------------
#
# Lo que la pelea deja al terminar: la experiencia y el nivel de cada actor,
# en `FAR_EXP`. Vivía en `test_experiencia_dibujo.py` hasta el 2026-09-29, y
# de ahí lo importaban la victoria y los HP del menú de la pelea.

def rom_de(una):
    with open(una.sfc, "rb") as archivo:
        return archivo.read()


def ranura_exp(una, actor):
    """La ranura de `FAR_EXP` del actor, leída de `actor_exp_k`, o None.

    Se lee del cartucho y no se recalcula con `experience_slots`: depende
    de qué actores pueden entrar al grupo en **este** cartucho, y rehacer esa
    cuenta acá sería una segunda manera de contestar lo mismo.
    """
    k = rom_de(una)[en_la_rom(una.simbolos["actor_exp_k"]) + actor]
    return None if k == 0xFF else k


def exp_y_nivel(una, actor):
    k = ranura_exp(una, actor)
    assert k is not None, "el actor %d no tiene ranura de experiencia" % actor
    b = una.consola.ram(una.simbolos["FAR_EXP"] + 4 * k, 4)
    return b[0] | (b[1] << 8) | (b[2] << 16), b[3]


def poner_exp(una, actor, exp, nivel):
    k = ranura_exp(una, actor)
    una.consola.write_ram(una.simbolos["FAR_EXP"] + 4 * k,
                          [exp & 0xFF, (exp >> 8) & 0xFF, exp >> 16, nivel])


# El actor con que se prueba aprender habilidades al subir de nivel: ver "las
# habilidades del nivel" en `test_experiencia_dibujo.py`.
#
# El que sirve es Arden, el actor 15: arranca en el 3 y aprende la 148 en el 4,
# la 140 en el 5, la 139 en el 6 y la 255 en el 7. De los tres de la intro
# ninguno aprende nada nuevo después de su nivel de arranque.
ARDEN = 15


# --- lo que la pelea escribe ------------------------------------------------
#
# Los textos de la pantalla de la pelea, leídos de la ROM y de la RAM: el
# mensaje de una página de la tropa, que vivía en `test_tropa.py`, y la
# ventana de la victoria, que vivía en `test_victoria.py`, hasta el
# 2026-09-29. Los usan también los eventos de tropa.

def mensaje_en_pantalla(una, pelea):
    """Los renglones del mensaje de página que la ROM tiene puesto, leídos del
    cartucho en el desplazamiento que dejó `op_message`."""
    desplazamiento = pelea.palabra(una.simbolos["BA_PAGE_MSG"])
    assert desplazamiento != 0xFFFF, "no hay ningún mensaje de página"
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    i = en_la_rom(una.simbolos["messages_troop"]) + desplazamiento
    cuantos = rom[i] & events.HEADER_LINES
    i += 1
    renglones = []
    for _ in range(cuantos):
        largo = rom[i]
        renglones.append("".join(chr(b + 32) for b in rom[i + 1:i + 1 + largo]))
        i += 1 + largo
    return renglones


def glifos(una):
    """Las dos celdas de cada letra blanca, al carácter: la tabla
    `item_glyph_cells` del cartucho, cuatro bytes por letra. Las dos, porque
    hay letras que comparten la de arriba —la "h" y la "b"—."""
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    base = en_la_rom(una.simbolos["item_glyph_cells"])
    de = {}
    for n in range(menus.ITEM_CHARS):
        b = rom[base + 4 * n:base + 4 * n + 4]
        de.setdefault((b[0] | (b[1] << 8), b[2] | (b[3] << 8)),
                      chr(menus.ITEM_FIRST_CHAR + n))
    return de


def renglones(una, fila0, cuantos):
    """Los renglones de texto de la pantalla de la pelea desde la fila
    `fila0` del tilemap, de a dos filas cada uno, sin los espacios del final.
    Una celda que no es ninguna letra sale como '#'."""
    de = glifos(una)
    buf = una.consola.ram(en_la_wram(una.simbolos["text_buf"]), 64 * 28)
    salida = []
    for r in range(cuantos):
        fila = fila0 + 2 * r
        letras = []
        for col in range(32):
            i = fila * 64 + 2 * col
            celda = (buf[i] | (buf[i + 1] << 8),
                     buf[i + 64] | (buf[i + 65] << 8))
            letras.append(" " if celda == (0, 0) else de.get(celda, "#"))
        salida.append("".join(letras).rstrip())
    return salida


def ventana(una):
    """Lo que dice la ventana de la victoria: los cuatro renglones del grupo,
    desde la columna del mensaje, y los dos de abajo, que tienen que quedar
    vacíos."""
    arriba = renglones(una, screens.BA_PAGE_MSG_ROW0, 4)
    abajo = renglones(una, screens.BA_MSG_ROW1, 2)
    col = screens.BA_PAGE_MSG_COL
    assert all(r[:col].strip() == "" for r in arriba), arriba
    return [r[col:] for r in arriba], abajo


def paginas(una, pelea, tope=10):
    """Cada página de la victoria —sus cuatro renglones— hasta que la pelea
    se cierra, apretando A entre una y otra."""
    vistas = []
    for _ in range(tope):
        if not pelea.abierta():
            return vistas
        assert pelea.modo() == "END"
        arriba, abajo = ventana(una)
        assert abajo == ["", ""], \
            "el renglón del mensaje de la pelea tendría que estar vacío: %r" \
            % abajo
        vistas.append([r for r in arriba if r] if any(arriba) else [])
        pelea.tocar_cuadros()
        for _ in range(10):
            if not pelea.abierta():
                break
            una.consola.run(1)
    raise AssertionError("la victoria no se cerró en %d páginas" % tope)


def primera_pagina(term, exp):
    return (screens.victory_lines(term["victory"])
            + [screens.exp_line(term, exp)])


# --- volver del Game Over ---------------------------------------------------
#
# El reinicio que sigue a la pantalla de Game Over, hasta que el juego vuelve
# a correr. Vivía en `test_game_over.py` hasta el 2026-09-29; lo usa también
# End Game, que termina en el mismo reinicio.

# Cuántos cuadros de hardware se le dan al arranque de después del Game Over
# para volver al lazo. El arranque son BOOT_FRAMES y encima la subida al
# SPC700, que no se cuenta en cuadros: el doble es paciencia de sobra.
VOLVER_TOPE = 600

# Y los que se le dan al título después del reinicio para estar quieto, como
# en `test_titulo_golden.py`.
TITULO_QUIETO = 170


def pasar_el_titulo(una):
    """`BOOT_FRAMES` y, con pantalla de título, "Begin the Story".

    **El Game Over vuelve al título**, que es lo que hace RM2k
    —`Scene_Gameover` termina en `Scene_Title`—, y ahí el juego no corre
    hasta que alguien elige. En un cartucho sin título el arranque va directo
    al mapa y esto es sólo esperar el arranque.
    """
    una.consola.run(una.simbolos["BOOT_FRAMES"])
    if una.titulo is not None:
        una.pasar_el_titulo(EMPEZAR)


def cuadros_hasta_volver(una, tope=VOLVER_TOPE):
    """Cuántos cuadros pasan, desde el reinicio, hasta que el lazo vuelve a
    correr. `None` si no volvió: eso es el cuelgue.

    Se mira que `ticks` **suba**, que es lo único que dice que el arranque
    terminó: `map_current` ya vale lo suyo mucho antes —`load_map` corre
    antes de la subida al SPC700— así que preguntarle a él da verde con la ROM
    clavada. Es exactamente lo que pasaba acá hasta el 2026-09-13.

    Con pantalla de título se la pasa primero —ver `pasar_el_titulo`—: si el
    arranque se colgara antes, los toques caen en nada y `ticks` no sube
    igual.
    """
    if una.titulo is not None:
        pasar_el_titulo(una)
    for n in range(tope):
        antes = una.palabra("ticks")
        una.consola.run(1)
        if una.palabra("ticks") > antes:
            return n
    return None
