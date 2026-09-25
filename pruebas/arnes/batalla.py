"""La pelea de la consola, manejada desde afuera, y lo que las pruebas de
pelea comparten: el droide del mapa 2, el grupo de la intro, el modelo de
`port.batalla` y perder sin pelear.

**Todo en cuadros de hardware**: la pelea corre su propio lazo y `vueltas` no
avanza mientras dura.
"""

from port import batalla as modelo

from consola import en_la_rom, en_la_wram
import datos
from tanda import LINKAGE

# El droide del mapa 2 está en (30,55) y se le habla desde abajo.
DROIDE = (30, 56)
TROPA_DROIDE = 82
# El grupo de la escena: Kersh, Core y Manta, que es con quienes se llega.
GRUPO = (11, 12, 13)

# Los modos de la pantalla y las cinco órdenes del menú **se leen de la tabla
# de símbolos**: `Pelea.modo()` contesta el nombre de la constante `BA_M_*` de
# la ROM sin el prefijo —"ORDEN", "BLANCO", "FIN"...— y las órdenes son
# `BA_ORDEN_ATACAR` y compañía. El orden es el del original —Attack /
# <habilidad> / Defend / Use Item— y `Escape` va quinta, que es la
# simplificación que `port/batalla.py` declara.


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

    # Los HP y SP **de la pelea**: la ranura `BA_UNO` del combatiente `k`, que
    # es el puesto en la pantalla —0 a 2 los actores, desde `BA_GRUPO_MAX` los
    # enemigos— y no el número de actor. Los de la partida son
    # `Partida.hp(actor)`, y la pelea los copia ahí recién al terminar.

    def hp_del_combatiente(self, k):
        return self.palabra(self.s["BA_UNO"] + k * self.s["BA_BYTES"])

    def sp_del_combatiente(self, k):
        return self.palabra(self.s["BA_UNO"] + k * self.s["BA_BYTES"]
                            + self.s["BA_SP"])

    def modo(self):
        """El nombre del modo de la pantalla: el de su `BA_M_*` sin el
        prefijo. Un valor que no es de ninguno vuelve como número."""
        valor = self.byte("BA_MODO")
        return self._modos.get(valor, valor)

    def orden(self, nombre):
        """El número de la orden del menú: `BA_ORDEN_<nombre>`."""
        return self.s["BA_ORDEN_" + nombre]

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
            self.una.consola.correr(1)
        raise AssertionError("la pelea no llegó al modo %s, quedó en %s"
                             % (modo, self.modo()))

    def ordenar(self, que, tope=400):
        """Le da a un actor la orden `que` y deja el cursor en el que sigue.

        `que` es `("atacar", enemigo)`, `("defender",)` o
        `("habilidad", k, blanco)`, donde `k` es el lugar en la lista de
        habilidades del actor —la misma que `batalla.habilidades_de` arma— y
        `blanco` el lugar del enemigo o del actor al que apunta, según su
        `scope`. Una de switch va sin blanco, `("habilidad", k)`: no lo pide.
        """
        self.esperar("ORDEN", tope)
        cual = que[0]
        pasos = self.orden({"atacar": "ATACAR", "defender": "DEFENDER",
                            "habilidad": "HABILIDAD"}[cual])
        # El cursor primero a la izquierda del todo: volver de la lista de
        # habilidades con B lo deja donde estaba, así que contar derechas desde
        # donde quedó elegiría otra orden.
        for _ in range(5):
            self.tocar("left")
        for _ in range(pasos):
            self.tocar("right")
        assert self.byte("BA_ORDEN") == pasos, (
            "el cursor tenía que quedar en la orden %d y quedó en %d"
            % (pasos, self.byte("BA_ORDEN")))
        self.tocar()
        if cual == "defender":
            return self
        if cual == "habilidad":
            self.esperar("HAB", tope)
            for _ in range(que[1]):
                self.tocar("right")
            assert self.byte("BA_HAB_SEL") == que[1]
            self.tocar()
            if len(que) == 2:
                # Una de switch no pide blanco: `Scene_Battle::AssignSkill`
                # la anota sobre el que la usa. El cursor ya está en el que
                # sigue, o el turno ya arrancó.
                assert self.modo() not in ("BLANCO", "ACTOR"), \
                    "una habilidad de switch pidió blanco"
                return self
        # El blanco: los enemigos se eligen con el cursor hacia abajo desde el
        # primero vivo, y el grupo igual.
        for _ in range(tope):
            if self.modo() in ("BLANCO", "ACTOR"):
                break
            self.una.consola.correr(1)
        else:
            raise AssertionError("la orden no pidió blanco")
        destino = que[-1]
        for _ in range(destino):
            self.tocar("down")
        self.tocar()
        return self

    def correr_turno(self, tope=600):
        """Con las órdenes ya dadas, pasa los mensajes hasta que el turno
        termina."""
        for _ in range(tope):
            if self.modo() in ("ORDEN", "FIN"):
                return self
            self.tocar()
        raise AssertionError("el turno no terminó")

    def turno(self, cuantos, tope=400):
        """Un turno entero con `cuantos` actores atacando al primer enemigo."""
        for _ in range(cuantos):
            for _ in range(tope):
                if self.modo() != "ORDEN":
                    break
                self.tocar()
            for _ in range(tope):
                if self.modo() != "BLANCO":
                    break
                self.tocar()
        for _ in range(tope):
            if self.modo() in ("ORDEN", "FIN"):
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
    donde = en_la_rom(una.simbolos["hab_id"]) + 2 * k
    return rom[donde] | (rom[donde + 1] << 8)


# --- perder sin pelear ------------------------------------------------------
#
# Con todo el grupo en cero HP, `batalla_correr` contesta derrota antes de abrir
# la pantalla —el `ba_actor_siguiente` que devuelve $FF—, así que las pruebas
# de Game Over y de `FullHeal` no dependen de ningún tiro de dado.

# Cuántos ticks se le dan a la página `pelea-82-curar` para perder la pelea y
# correr el manejador. La pelea sale a los 18 y, perdida sin pelear, no abre
# pantalla.
DESPUES_DE_PERDER = 60


def sin_hp(una):
    """Todo el grupo caído, escrito en la RAM lejana."""
    largo = una.simbolos["FAR_SP"] - una.simbolos["FAR_HP"]
    una.consola.escribir_ram(una.simbolos["FAR_HP"], [0] * largo)
    return una


def cuadros_hasta_reiniciar(una, tope=900):
    """Cuántos cuadros de hardware pasan hasta que `vueltas` se va para atrás.

    Se cuenta en cuadros y no en ticks a propósito: `Partida.correr` avanza
    hasta que `vueltas` **suba**, y un reinicio la pone en cero, así que
    esperar un tick después del Game Over no terminaría nunca.
    """
    alto = una.palabra("vueltas")
    for n in range(tope):
        una.consola.correr(1)
        ahora = una.palabra("vueltas")
        if ahora < alto:
            return n
        alto = ahora
    return None


def con_encuentros(partida):
    """El mapa de `test-special` con encuentros al azar y el grupo de la
    intro, que los gana en un turno."""
    return partida(caso="grupo-11-12-13", en="test-special")


# --- el grupo, leído de la RAM ------------------------------------------------

def grupo_de(una):
    """Hasta `grupo_n`: las ranuras de más no se limpian y traen basura."""
    return list(una.consola.ram(una.simbolos["grupo"], una.palabra("grupo_n")))


def sabe(una, actor, habilidad):
    """Si el actor sabe la habilidad: su bit en `FAR_HAB`, con el índice de
    pares del cartucho de pruebas."""
    r = datos.ranuras_de_habilidad()[(actor, habilidad)]
    octeto = una.consola.ram(una.simbolos["FAR_HAB"] + (r >> 3), 1)[0]
    return bool(octeto & (1 << (r & 7)))
