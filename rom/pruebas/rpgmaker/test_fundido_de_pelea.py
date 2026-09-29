"""La transición de la pelea tapa la carga del paquete de audio.

Al entrar a una pelea se sube su paquete de audio, y al salir se vuelve a subir
el del mapa: la ARAM casi entera cada vez, que tarda de medio segundo a uno y
medio según el cartucho. Hasta el 2026-09-26 eso se veía como la pantalla
congelada —el mapa al entrar, la pelea al salir—; desde ese día la transición
de RM2k apaga la pantalla antes de cargar y la prende después. Ver
`runtime/fundido_de_pelea.s`.

Lo que se cobra es exactamente eso: **cada cuadro en el que el paquete avanza
se ve negro**. Que el paquete avanza lo dicen `PKG_DEST` y `PKG_S` —dónde va
la muestra que se sube y cuál es—, que cambian a lo largo de toda la carga y
en ningún otro momento de la pelea. Negro es negro de verdad: ningún canal de
ningún pixel por encima de cero.

Ninguna golden puede ver esto: la pelea no cuesta ningún tick, así que lo que
pasa adentro de la transición queda entre dos capturas de la tanda.
"""

from batalla import Pelea, en_el_droide
from consola import en_la_wram


class Grabador:
    """Corre de a un cuadro de hardware y anota, de cada uno, si la pantalla
    se vio negra y si el paquete de audio avanzó."""

    def __init__(self, una):
        self.una = una
        self.cuadros = []
        self._paquete = self._leer_paquete()

    def _leer_paquete(self):
        s = self.una.simbolos
        c = self.una.consola
        return (bytes(c.ram(en_la_wram(s["PKG_DEST"]), 2))
                + bytes(c.ram(en_la_wram(s["PKG_S"]), 2)))

    def cuadro(self, *botones):
        self.una.consola.hold(*botones)
        self.una.consola.run(1)
        negro = max(self.una.imagen().tobytes()) == 0
        paquete = self._leer_paquete()
        self.cuadros.append((negro, paquete != self._paquete))
        self._paquete = paquete

    def tocar_cuadros(self, boton="a"):
        for _ in range(2):
            self.cuadro(boton)
        for _ in range(2):
            self.cuadro()

    def cargando(self):
        return [n for n, (_, avanza) in enumerate(self.cuadros) if avanza]

    def visibles_cargando(self):
        return [n for n, (negro, avanza) in enumerate(self.cuadros)
                if avanza and not negro]


def _entrar(una, tope=2000):
    grabador = Grabador(una)
    grabador.tocar_cuadros("a")         # hablarle al droide
    for _ in range(tope):
        if una.byte("menu_open"):
            return grabador
        if una.byte("msg_open"):
            grabador.tocar_cuadros("a")
        else:
            grabador.cuadro()
    raise AssertionError("la pelea no se abrió")


def _salir(una, tope=600):
    pelea = Pelea(una)
    for _ in range(6):
        if pelea.modo() == "END":
            break
        pelea.turno(3)
    pelea.esperar("END")
    vueltas = una.palabra("ticks")
    grabador = Grabador(una)
    grabador.tocar_cuadros("a")         # el mensaje de la victoria
    for _ in range(tope):
        if una.palabra("ticks") != vueltas:
            return grabador             # el mapa volvió a correr
        grabador.cuadro()
    raise AssertionError("el mapa no volvió a correr")


def test_la_carga_al_entrar_a_la_pelea_se_ve_negra(partida):
    una = en_el_droide(partida)
    grabador = _entrar(una)
    assert grabador.cargando(), \
        "no se vio subir ningún paquete de audio al entrar a la pelea"
    visibles = grabador.visibles_cargando()
    assert not visibles, (
        "el paquete de la pelea se sube con la pantalla a la vista en %d de "
        "%d cuadros (el primero, el %d desde que se le habló al droide)"
        % (len(visibles), len(grabador.cargando()), visibles[0]))


def test_la_carga_al_volver_al_mapa_se_ve_negra(partida):
    una = en_el_droide(partida)
    _entrar(una)
    grabador = _salir(una)
    assert grabador.cargando(), \
        "no se vio subir ningún paquete de audio al volver de la pelea"
    visibles = grabador.visibles_cargando()
    assert not visibles, (
        "el paquete del mapa se sube con la pantalla a la vista en %d de "
        "%d cuadros (el primero, el %d desde la A que cierra la pelea)"
        % (len(visibles), len(grabador.cargando()), visibles[0]))
