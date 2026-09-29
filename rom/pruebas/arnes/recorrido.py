"""Jugar un tramo largo del juego y preguntarle a la RAM si llegó.

Las demás pruebas de estado ponen a la partida en un estado y miran una cosa.
Ésta hace lo contrario: **juega**, de corrido, apretando A donde el juego pide A
y caminando donde el juego pide caminar, y verifica en cada hito en qué mapa
está, en qué celda y qué switches prendió. Es la única red que ve que la cadena
entera siga siendo jugable; todo lo demás mira una pieza a la vez.

Dos reglas de diseño, y las dos vienen de que un guion de cuadros contados se
pudre solo:

**Nada se cuenta en cuadros, se espera por RAM.** "Apretá derecha 400 cuadros"
se rompe con cualquier cambio de velocidad —Lashe City pasó de 30 a 60 fps el
mismo día que esto se escribió—. "Caminá hasta que `mapa()` valga 16, con tope"
sobrevive. Los topes existen igual, pero son el límite de paciencia y no el
guion: cuando uno se agota, el mensaje dice **en qué hito** se agotó y **con qué
estado**, porque un fallo al minuto siete no se depura con un `assert False`.

**Por dónde se camina lo dice el juego original, no una lista escrita a mano.**
La ruta sale de un BFS sobre la misma tabla de colisión que usa el conversor
—`rm2k.passability_map`—, así que si un tile cambia de lado, la
prueba camina por donde se pueda caminar y no por donde alguien anotó que se
podía. Lo único escrito a mano es **a dónde** hay que ir, y eso también sale del
juego: es la celda del evento que teletransporta al mapa que sigue.
"""

import collections
import os

import lugares
from consola import TITULO_AIRE
from render.render_map import Renderer
from rpgmaker.resources import GAME_DIR
from rpgmaker.rm2k import (PASS_DOWN, PASS_LEFT, PASS_RIGHT,
                           PASS_UP, TELEPORT, grafico_de_pagina,
                           pasabilidad_del_tile, passability_map)

# El switch que prende el final del Emitter Room y que hace que el enrutador del
# mapa 4 mande a la casa de Talan con el cartel de "One year previously". Es el
# mismo que usa el caso `cartel` de la tanda, y con el que arrancan las
# jugadas que empiezan en la casa de Talan.
UN_ANO_DESPUES = 21


def puede_pasar(passable, width, height, x, y, dx, dy, blocked=()):
    """Si desde (x,y) se puede dar un paso en (dx,dy).

    Las dos caras se consultan, la que se deja y la que se entra, que es la
    regla de RM2k —la misma que `pass_salir`/`pass_entrar` de `runtime/banco1.s`—. Es una
    función y no está escrita en cada lugar porque acá se camina de dos maneras
    —el BFS que arma la ruta y el paso a paso que la recorre mirando si la
    celda tiene una puerta— y las reglas tienen que ser las mismas, no una
    copia parecida.

    Vive acá y no en `rpgmaker/rm2k.py` porque este archivo es su único
    llamador.
    """
    leaving = {(1, 0): PASS_RIGHT, (-1, 0): PASS_LEFT,
               (0, 1): PASS_DOWN, (0, -1): PASS_UP}[(dx, dy)]
    entering = {(1, 0): PASS_LEFT, (-1, 0): PASS_RIGHT,
                (0, 1): PASS_UP, (0, -1): PASS_DOWN}[(dx, dy)]
    nx, ny = x + dx, y + dy
    if not (0 <= nx < width and 0 <= ny < height):
        return False
    if not passable[y * width + x] & leaving:
        return False
    if not passable[ny * width + nx] & entering:
        return False
    if (nx, ny) in blocked:
        return False                # hay un NPC parado ahí
    return True


# Los disparos de una página, en el orden de `lcf.TRIGGERS`.
TRIGGER_ACCION, TRIGGER_CONTACTO, TRIGGER_CHOQUE, TRIGGER_AUTO, \
    TRIGGER_PARALELO = range(5)

# Cuántos ticks se le da a un paso de una celda antes de darlo por trabado. Un
# paso a velocidad normal son unos ocho ticks; los mapas de Lashe City corren
# más lento y un teletransporte de puerta se come varios. Cuarenta es paciencia
# de sobra sin que un trabado cueste una corrida entera.
PASO_TOPE = 40

# Cada cuántos ticks se toca A mientras se espera que una cinemática avance. El
# juego pide A por cada cuadro de texto; tocarlo más seguido no saltea nada
# —cada cuadro espera su flanco— y tocarlo más lento sólo hace la prueba más
# lenta. Ocho es un toque cada 130 ms de tiempo real.
A_CADA = 8

# Dónde viven las capturas que taro bendijo, y cuánto se les tolera. Ver `foto`.
GOLDEN = os.path.join(lugares.GOLDENS, "playthrough")
GOLDEN_TOLERANCIA = 0.15
# Las fotos que todavía no tienen golden, dichas una por una: ver
# `pendientes` y el encabezado del archivo.
PENDIENTES = os.path.join(GOLDEN, "pendientes.txt")


def pendientes(ruta=PENDIENTES):
    """Las fotos de la lista de pendientes, como `<tramo>/<NN>-<hito>.png`.

    Se lee de nuevo cada vez y no se cachea: son unos cien renglones, y una
    prueba que la cambie a mitad de corrida no tiene que ver la vieja.
    """
    with open(ruta, encoding="utf-8") as archivo:
        renglones = [r.strip() for r in archivo]
    fotos = [r for r in renglones if r and not r.startswith("#")]
    repetidas = sorted({f for f in fotos if fotos.count(f) > 1})
    assert not repetidas, "%s repite %s" % (ruta, ", ".join(repetidas))
    return set(fotos)


# Los `Recorrido` con carpeta de fotos creados en la prueba que corre: al
# terminar, `conftest._tramos_completos` le pide a cada uno
# `verificar_el_tramo`. Es una lista del módulo y no un fixture porque
# `test_mapa_de_debug.py` arma los suyos sin pasar por el de `recorrido`.
ABIERTOS = []


# Cuántas veces se insiste con un paso antes de dar la celda por bloqueada. Los
# NPCs de este juego caminan solos: el que tapa el pasillo se corre en unos
# ticks, y rodearlo a la primera es peor camino que esperarlo.
INSISTIR = 4


class Mundo:
    """La colisión de los mapas del juego original, para saber por dónde se
    puede caminar.

    Se carga una vez por corrida y se cachea por mapa: leer un `.lmu` de 100x100
    y resolverle los cuatro bits a cada celda cuesta bastante más que el BFS que
    viene después.
    """

    def __init__(self, game_dir=GAME_DIR):
        self.game_dir = game_dir
        self.renderer = Renderer(game_dir)
        self.cache = {}

    def lmu(self, map_id):
        """El mapa del juego original, con lo que `rm2k` necesita colgado."""
        if ("lmu", map_id) not in self.cache:
            self.cache[("lmu", map_id)] = self.renderer.cargar_mapa(
                os.path.join(self.game_dir, "Map%04d.lmu" % map_id))
        return self.cache[("lmu", map_id)]

    def pagina_activa(self, evento, prendido):
        """La página que RM2k mostraría con estos switches puestos.

        Es `Game_Event::page`: la de número más alto cuyas condiciones se
        cumplen todas. Una condición que no es de switch —objeto, actor,
        cronómetro— se da por no cumplida, que es el lado seguro: perder una
        página cuesta un camino, inventarla manda a la prueba contra una pared.
        """
        activa = None
        for pagina in evento.pages:
            if all(nombre in ("switch_a", "switch_b")
                   and prendido(pagina.condition.ids[nombre])
                   for nombre in pagina.condition.active):
                activa = pagina
        return activa

    def mapa(self, map_id, prendido=None):
        """(colisión, ancho, alto) del mapa.

        **La colisión depende de los switches**, y no es un detalle: un evento
        de la capa de abajo dibujado con un tile le impone sus bits a la celda
        —`Game_Map::IsPassableTile`— así que "se abre una puerta" en este juego
        es una página con otro tile. Con la página de la partida recién
        empezada, la casa de Talan no tiene salida.
        """
        prendido = prendido or (lambda numero: False)
        game_map = self.lmu(map_id)
        # La clave es qué página está activa en cada evento con gráfico de
        # tile, que es todo lo que la colisión puede mirar de los switches.
        eventos = []
        for evento in game_map.events:
            pagina = self.pagina_activa(evento, prendido)
            if pagina is None:
                continue
            grafico = grafico_de_pagina(pagina, getattr(
                game_map, "chipset_nombre", None))
            pasa = (None if grafico is None else
                    pasabilidad_del_tile(game_map, grafico[0], pagina.layer))
            eventos.append(((evento.x, evento.y), pasa))
        clave = ("mapa", map_id, tuple(eventos))
        if clave not in self.cache:
            pasable = bytearray(
                passability_map(game_map, game_map.pasabilidad_tiles))
            for (x, y), pasa in eventos:
                if pasa is not None:
                    pasable[y * game_map.width + x] = pasa
            self.cache[clave] = (bytes(pasable), game_map.width,
                                 game_map.height)
        return self.cache[clave]

    def puertas(self, map_id, prendido):
        """Las celdas del mapa que teletransportan con sólo pisarlas."""
        return frozenset(celda for celda, trigger, _
                         in self.salidas(map_id, prendido)
                         if trigger in (TRIGGER_CONTACTO, TRIGGER_CHOQUE))

    def islas(self, map_id, prendido):
        """Qué celdas del mapa están conectadas con cuáles, por número de isla.

        Dos cosas, y las dos vienen de cómo está armada esta ciudad.

        Los mapas de ciudad de este juego **no son un solo recinto**: son
        bandas de calle separadas por pared, y lo que las une son
        teletransportes de contacto en los bordes —caminar hacia la izquierda
        en (0,56) del mapa 8 te deja en (73,32) del mismo mapa 8—. El mapa 8
        tiene 32 islas; sin esto, la ruta de un extremo al otro no existe.

        Y **las puertas no son celdas de la isla**: pisar una no es dar un paso,
        es irse. Contándolas adentro, el planificador creía que del extremo
        este del mapa 9 se llegaba caminando al oeste, y el camino más corto
        pasaba justo por el teletransporte que devuelve a Lashe City. Contarlas
        afuera hace que la única manera de cambiar de isla sea una arista del
        plan, que es lo que son.
        """
        clave = ("islas", map_id, self.puertas(map_id, prendido))
        if clave not in self.cache:
            pasable, ancho, alto = self.mapa(map_id, prendido)
            puertas = clave[2]
            isla = {}
            numero = 0
            for y0 in range(alto):
                for x0 in range(ancho):
                    if not pasable[y0 * ancho + x0] or (x0, y0) in isla \
                            or (x0, y0) in puertas:
                        continue
                    numero += 1
                    cola = collections.deque([(x0, y0)])
                    isla[(x0, y0)] = numero
                    while cola:
                        x, y = cola.popleft()
                        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                            siguiente = (x + dx, y + dy)
                            if siguiente in isla or siguiente in puertas:
                                continue
                            if puede_pasar(pasable, ancho, alto, x, y, dx, dy):
                                isla[siguiente] = numero
                                cola.append(siguiente)
            self.cache[clave] = isla
        return self.cache[clave]

    def islas_de(self, map_id, celda, prendido, hablando=False):
        """Desde qué islas se dispara el evento parado en `celda`.

        La suya, si es una celda de andar; y las de al lado, que es lo que hace
        falta cuando la celda es una puerta —que a propósito no pertenece a
        ninguna isla— o una pared con un evento encima. Pisarla pide que el
        paso sea legal; **hablarle no**, que para eso alcanza con estar al lado
        y girar.
        """
        isla = self.islas(map_id, prendido)
        pasable, ancho, alto = self.mapa(map_id, prendido)
        cuales = set()
        if celda in isla:
            cuales.add(isla[celda])
        x, y = celda
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            vecina = (x + dx, y + dy)
            if vecina not in isla:
                continue
            if hablando or puede_pasar(pasable, ancho, alto, vecina[0],
                                       vecina[1], -dx, -dy):
                cuales.add(isla[vecina])
        return cuales

    def islas_desde(self, map_id, celda, prendido):
        """A qué islas se llega estando parado en `celda`, que es donde un
        teletransporte deja al héroe. Casi siempre es una sola: la suya."""
        isla = self.islas(map_id, prendido)
        if celda in isla:
            return {isla[celda]}
        pasable, ancho, alto = self.mapa(map_id, prendido)
        x, y = celda
        cuales = set()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            vecina = (x + dx, y + dy)
            if vecina in isla and puede_pasar(pasable, ancho, alto, x, y,
                                              dx, dy):
                cuales.add(isla[vecina])
        return cuales

    def salidas(self, map_id, prendido):
        """Los teletransportes que el mapa tiene hoy, con su celda y su disparo.

        "Hoy" no es un decir: la página activa de un evento es la de número más
        alto cuyas condiciones se cumplen —`Game_Event::page`— y las de switch
        se le preguntan a la partida que está corriendo, no a una tabla. Por eso
        `prendido` es una función y no un conjunto: la puerta de la casa de
        Talan sólo lleva a Lashe City con el switch 24 puesto, y ese switch lo
        prende el despertador tres minutos antes.

        Una página con condiciones que no son de switch —un objeto, un actor,
        el cronómetro— se da por **no activa**: no se puede contestar desde acá
        sin rehacer el intérprete, y equivocarse hacia el lado de "esa puerta no
        existe" sólo pierde un camino, mientras que el otro lado manda a la
        prueba a caminar contra una pared.
        """
        salidas = []
        for evento in self.eventos(map_id):
            pagina = None
            for una in evento.pages:
                if all(nombre in ("switch_a", "switch_b")
                       and prendido(una.condition.ids[nombre])
                       for nombre in una.condition.active):
                    pagina = una
            if pagina is None:
                continue
            # El **último** `Teleport` de la página, que es donde termina: una
            # cinemática se teletransporta varias veces adentro de su propio
            # mapa antes de mudarte de verdad.
            destino = None
            for comando in pagina.commands:
                if comando.code == TELEPORT:
                    destino = tuple(comando.parameters[:3])
            if destino is not None:
                salidas.append(((evento.x, evento.y), pagina.trigger, destino))
        return salidas

    def eventos(self, map_id):
        return self.lmu(map_id).events

    def plan(self, mapa, celda, destino, prendido, mapas):
        """Cómo ir del mapa donde está la partida hasta `destino`, por puertas.

        Es un BFS sobre un grafo de **islas**, no de mapas: un nodo es "esta
        isla de este mapa" y una arista es un teletransporte que se puede
        disparar desde ahí. Así el plan sale del juego original y no de una
        lista escrita a mano que envejece con el primer mapa que se toque.

        `mapas` son los que el cartucho lleva: una puerta hacia un mapa que no
        está no compila, así que tampoco tiene que estar en el plan.
        """
        origen = (mapa, self.islas(mapa, prendido).get(celda))
        vistos = {origen: None}
        cola = collections.deque([origen])
        while cola:
            nodo = cola.popleft()
            if nodo[0] == destino:
                return self._deshacer_plan(vistos, nodo)
            for donde, trigger, (hacia, dx, dy) in self.salidas(nodo[0],
                                                               prendido):
                if hacia not in mapas:
                    continue
                # Desde dónde se dispara: una página automática corre sola en
                # cualquier isla; a las otras dos hay que llegarles, y a una de
                # tecla se le habla además desde la celda de al lado, que es lo
                # que hace `Recorrido.activar`.
                if trigger in (TRIGGER_AUTO, TRIGGER_PARALELO):
                    desde = {nodo[1]}
                else:
                    desde = self.islas_de(
                        nodo[0], donde, prendido,
                        hablando=trigger == TRIGGER_ACCION)
                if nodo[1] not in desde:
                    continue
                for isla in self.islas_desde(hacia, (dx, dy),
                                             prendido) or {None}:
                    siguiente = (hacia, isla)
                    if siguiente in vistos:
                        continue
                    vistos[siguiente] = (nodo,
                                         (donde, trigger, hacia, (dx, dy)))
                    cola.append(siguiente)
        return None

    @staticmethod
    def _deshacer_plan(vistos, nodo):
        tramos = []
        while vistos[nodo] is not None:
            nodo, tramo = vistos[nodo]
            tramos.append(tramo)
        tramos.reverse()
        return tramos

    def ruta(self, map_id, desde, hasta, prendido, evitar=()):
        """Los pasos —(dx, dy)— para ir de una celda a otra, o None.

        BFS y no A*: los mapas más grandes de esta cadena son de 100x100, o sea
        diez mil celdas, y el BFS entero cuesta menos que un solo cuadro de
        emulación.
        """
        pasable, ancho, alto = self.mapa(map_id, prendido)
        evitar = set(evitar)
        vistos = {desde: None}
        cola = collections.deque([desde])
        while cola:
            celda = cola.popleft()
            if celda == hasta:
                return self._deshacer(vistos, hasta)
            x, y = celda
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                siguiente = (x + dx, y + dy)
                if siguiente in vistos or siguiente in evitar:
                    continue
                if not puede_pasar(pasable, ancho, alto, x, y, dx, dy):
                    continue
                vistos[siguiente] = (celda, (dx, dy))
                cola.append(siguiente)
        return None

    @staticmethod
    def _deshacer(vistos, hasta):
        pasos = []
        celda = hasta
        while vistos[celda] is not None:
            celda, paso = vistos[celda]
            pasos.append(paso)
        pasos.reverse()
        return pasos


BOTON = {(0, -1): "up", (0, 1): "down", (-1, 0): "left", (1, 0): "right"}

# El mismo paso, visto como lo que le queda en `hero_dir`. Los números no se
# escriben acá: son `DIR_UP` y sus tres hermanas, y salen de la tabla de
# símbolos del cartucho. Ver `Recorrido.mirar_a`.
DIR_DEL_PASO = {(0, -1): "DIR_UP", (0, 1): "DIR_DOWN",
                (-1, 0): "DIR_LEFT", (1, 0): "DIR_RIGHT"}


class Trabado(AssertionError):
    """El recorrido no llegó a donde tenía que llegar.

    Es `AssertionError` a propósito: pytest lo cuenta como un fallo de la
    prueba y no como un error del arnés, que es lo que es.
    """


class Recorrido:
    """Un guion de hitos sobre una partida corriendo.

    Todo lo que se le pide lleva tope y todo lo que falla dice dónde estaba la
    partida cuando falló.
    """

    def __init__(self, partida, mundo, fotos=None):
        self.p = partida
        self.mundo = mundo
        self.fotos_dir = fotos
        self.hito = "arranque"
        self.fotos = []
        if fotos:
            ABIERTOS.append(self)

    # --- lo que se le dice al mundo ----------------------------------------

    def estado(self):
        """Dónde está parada la partida, en una línea. Es lo que se imprime
        cuando algo falla, y es la diferencia entre depurar y adivinar."""
        p = self.p
        try:
            mapa = "%d" % p.mapa()
        except AssertionError:
            # `mapa()` se planta si el índice no está en la tabla, y acá eso
            # sería tapar el error de verdad con otro: lo que se está armando
            # es el mensaje que explica qué pasó.
            mapa = "índice %d, que no está en la tabla" % p.palabra(
                "mapa_actual")
        return ("hito %r: tick %d, mapa %s, celda (%d,%d), mirando %d, "
                "página %s, mensaje %s, perdidos %d"
                % (self.hito, p.cuadro, mapa, p.palabra("tile_x"),
                   p.palabra("tile_y"), p.byte("hero_dir"),
                   p.byte("ev_activo"), p.byte("msg_abierto"),
                   p.cuadros_perdidos()))

    def celda(self):
        return (self.p.palabra("tile_x"), self.p.palabra("tile_y"))

    def empezar(self, hito):
        """Nombra el tramo que viene. Sólo sirve para los mensajes de error, y
        por eso mismo no se saltea: un tope agotado sin nombre no dice nada."""
        self.hito = hito
        return self

    def asentar(self, tope=90):
        """Espera a que termine el fundido que haya. Sin esto, la captura de
        un hito que acaba de cruzar una puerta sale **negra**: el fundido de
        la puerta dura decenas de ticks y el hito se cumple en el primero."""
        for _ in range(tope):
            if not self.p.byte("fundido"):
                return self
            self.p.correr(1)
        return self

    def foto(self, nombre, asentar=True, imagen=None):
        """Una captura, numerada por orden de aparición, contra su golden.

        Esto es lo que una prueba de RAM **no** puede ver: que la pantalla sea
        basura. El bug que lo motivó salía como el mapa hecho pedazos tres
        cuadros después de un cuadro de texto, en otro mapa, y ningún assert de
        estado lo habría notado.

        La golden la bendice taro mirándola una vez, y vive en
        `pruebas/golden/playthrough/`. Si no hay golden, la captura se guarda
        igual y el caso **no falla sólo si la foto está en
        `pendientes.txt`**, al lado de las goldens: así se agrega un hito
        nuevo sin romper la prueba, y se bendice después, pero que falte una
        golden se declara. Hasta el 2026-09-29 alcanzaba con que no estuviera,
        y "todavía no la aprobó nadie" no se distinguía de "se borró".

        **La tolerancia es grande a propósito.** No es una comparación pixel
        por pixel como la de `tanda.golden`: acá los cuadros no están
        elegidos para ser deterministas —el agua se mueve, los NPCs caminan, el reloj
        corre— y apretar el umbral traería rojos que no son defectos. Lo que
        tiene que cazar es la corrupción, y taro lo dijo mejor: "incluso si no
        logramos 100% de match, con que logremos 90% va a alcanzar, porque las
        imágenes rotas están MUY rotas". Las que vimos rotas iban del 34% al
        71% de pixeles distintos.

        `imagen` es para la pantalla que ya pasó: una captura tomada antes,
        cuando recién después se supo que era la del hito. La usa el fin de la
        demo, que se reconoce porque el toque siguiente vuelve al título.
        """
        if asentar and imagen is None:
            self.asentar()
        if not self.fotos_dir:
            return self
        # La carpeta se crea con la primera foto y no antes: una jugada que no
        # saca ninguna —la de `con_musica`— dejaba una vacía.
        os.makedirs(self.fotos_dir, exist_ok=True)
        archivo = "%02d-%s.png" % (len(self.fotos) + 1, nombre)
        ruta = os.path.join(self.fotos_dir, archivo)
        imagen = imagen or self.p.imagen()
        imagen.save(ruta)
        self.fotos.append((nombre, ruta, self.estado()))
        self._contra_golden(nombre, archivo, imagen)
        return self

    def _contra_golden(self, nombre, archivo, imagen):
        """Compara con la golden, o se fija que la foto esté pendiente. Ver
        `foto`."""
        tramo = os.path.basename(self.fotos_dir)
        carpeta = os.path.join(GOLDEN, tramo)
        golden = os.path.join(carpeta, archivo)
        pendiente = "%s/%s" % (tramo, archivo) in pendientes()
        if not os.path.exists(golden):
            # La golden se busca por el número de orden, así que una foto
            # nueva metida antes corre a todas las de atrás y las deja sin
            # golden. Si el hito tiene golden con otro número, es eso, y se
            # dice antes que lo de la lista, que sería la consecuencia.
            hito = archivo.split("-", 1)[1]
            hay = os.listdir(carpeta) if os.path.isdir(carpeta) else ()
            otras = sorted(n for n in hay if n.split("-", 1)[-1] == hito)
            if otras:
                raise AssertionError(
                    "el hito %r es la foto %s y su golden es %s: se corrió la "
                    "numeración, y las fotos que siguen quedan sin comparar. "
                    "Renombrá las goldens de %s."
                    % (nombre, archivo, ", ".join(otras), carpeta))
            if not pendiente:
                raise AssertionError(
                    "el hito %r es la foto %s/%s, que no tiene golden ni está "
                    "en %s. Si es nueva, anotala ahí hasta que taro la mire; "
                    "si tenía golden, se borró. La captura quedó en %s."
                    % (nombre, tramo, archivo, PENDIENTES,
                       os.path.join(self.fotos_dir, archivo)))
            return
        if pendiente:
            raise AssertionError(
                "la foto %s/%s tiene golden y sigue en %s: si la golden es la "
                "aprobada, sacala de la lista." % (tramo, archivo, PENDIENTES))
        from PIL import Image
        esperada = Image.open(golden).convert("RGB")
        actual = imagen.convert("RGB")
        if esperada.size != actual.size:
            raise AssertionError(
                "el hito %r mide %s y su golden %s" % (nombre, actual.size,
                                                       esperada.size))
        total = esperada.size[0] * esperada.size[1]
        distintos = sum(1 for a, b in zip(actual.getdata(), esperada.getdata())
                        if a != b)
        if distintos > total * GOLDEN_TOLERANCIA:
            raise AssertionError(
                "el hito %r no se parece a su golden: %d de %d pixeles "
                "distintos (%.1f%%, el tope es %.0f%%). La captura quedó en "
                "%s y la golden es %s. Si el cambio es a propósito, mirala y "
                "reemplazá la golden; si no, la pantalla se rompió.\n%s"
                % (nombre, distintos, total, 100.0 * distintos / total,
                   100.0 * GOLDEN_TOLERANCIA, os.path.join(self.fotos_dir,
                                                           archivo),
                   golden, self.estado()))

    def verificar_el_tramo(self):
        """Al terminar la jugada, que cada golden de su tramo y cada renglón
        suyo en `pendientes.txt` sean una foto que sacó: lo inverso de
        `_contra_golden`, que mira foto por foto.

        Una golden que ninguna foto usa es una comparación que ya no se hace
        —la foto se renombró, o la jugada dejó de llegar ahí— y un renglón que
        ninguna foto usa es la lista quedándose vieja. Lo llama el conftest,
        y sólo si la prueba pasó: una que se cortó a la mitad no sacó las de
        atrás.
        """
        if not self.fotos_dir:
            return
        tramo = os.path.basename(self.fotos_dir)
        carpeta = os.path.join(GOLDEN, tramo)
        sacadas = {os.path.basename(ruta) for _n, ruta, _e in self.fotos}
        goldens = set(os.listdir(carpeta)) if os.path.isdir(carpeta) else set()
        anotadas = {f.split("/", 1)[1] for f in pendientes()
                    if f.split("/", 1)[0] == tramo}
        sobran = (["la golden %s/%s" % (carpeta, n)
                   for n in sorted(goldens - sacadas)]
                  + ["el renglón %s/%s de %s" % (tramo, n, PENDIENTES)
                     for n in sorted(anotadas - sacadas)])
        assert not sobran, (
            "la jugada del tramo %r terminó sin sacar ninguna foto para %s. "
            "Si la foto se renombró o se sacó a propósito, eso sobra; si no, "
            "la jugada dejó de mirar ahí. Las que sacó: %s."
            % (tramo, ", ".join(sobran),
               ", ".join(sorted(sacadas)) or "ninguna"))

    # --- esperar, que es la mitad del juego --------------------------------

    def esperar(self, que, cond, tope, a_cada=A_CADA, mirando=None):
        """Corre tocando A hasta que `cond(partida)` sea verdad.

        `a_cada` None es esperar sin tocar nada, para las cinemáticas que
        avanzan solas: tocar A donde el juego no lo pide puede abrir el menú o
        hablarle a un evento de al lado.

        `mirando(partida)` corre en cada muestra, antes de avanzar, y sirve para
        lo que hay que comprobar **durante** un tramo y no al final: un invariante
        que se rompe a mitad de una cinemática y se acomoda sola antes del hito
        siguiente no la ve nadie mirando sólo el hito. Se planta ella misma; acá
        no se le mira lo que devuelve.
        """
        gastado = 0
        while gastado < tope:
            if mirando is not None:
                mirando(self.p)
            if cond(self.p):
                return self
            paso = min(a_cada or 16, tope - gastado)
            if a_cada:
                self.p.correr(paso, apretar_a=[self.p.cuadro + paso - 2])
            else:
                self.p.correr(paso)
            gastado += paso
        if mirando is not None:
            mirando(self.p)
        if cond(self.p):
            return self
        raise Trabado("esperando %s no pasó nada en %d ticks. %s"
                      % (que, tope, self.estado()))

    def mirar_a(self, paso, tope=PASO_TOPE):
        """Gira al héroe hacia `paso`, y **comprueba en la RAM que giró**.

        Girar hacia un evento es apretar la dirección contraria: el héroe gira
        aunque no pueda avanzar, que es `Game_Player::Move` con el paso
        bloqueado. Lo que no alcanza es **un toque de un tick**: la ROM lee el
        pad una vez por vuelta y una vuelta puede durar varios cuadros de
        hardware —ver `Partida.cuadros_perdidos`—, así que el flanco se puede
        perder entero. Medido el 2026-09-23 recién llegado a la celda: no gira
        con uno ni con dos ticks apretados, y sí con cuatro.

        Con el toque pelado que había acá, la puerta del HQ de los Neon Vipers
        —el evento 47 del mapa 8, que es de los que se hablan de al lado— no
        contestaba nunca: el héroe seguía mirando hacia donde había caminado y
        `activar` lo daba por muerto después de probar las cinco celdas.

        Si el héroe **camina** en vez de girar, se vuelve sin quejarse: la celda
        de al lado era pisable, y pararse encima es la otra forma de hablarle a
        un evento. Quien llamó ya sabe qué hacer con eso.
        """
        quiere = self.p.simbolos[DIR_DEL_PASO[paso]]
        desde = self.celda()
        try:
            for _ in range(tope):
                if self.p.byte("hero_dir") == quiere or self.celda() != desde:
                    return self
                self.p.sostener(1, BOTON[paso])
        finally:
            self.p.soltar()
        raise Trabado("el héroe no giró hacia %s en %d vueltas: quedó mirando "
                      "%d. %s" % (paso, tope, self.p.byte("hero_dir"),
                                  self.estado()))

    def esperar_mapa(self, map_id, tope=3000, a_cada=A_CADA):
        return self.esperar("el mapa %d" % map_id,
                            lambda p: p.mapa() == map_id, tope, a_cada)

    def esperar_switch(self, numero, tope=3000, a_cada=A_CADA):
        return self.esperar("el switch %d" % numero,
                            lambda p: p.switch(numero), tope, a_cada)

    def esperar_el_control(self, tope=3000, a_cada=A_CADA):
        """Hasta que no haya ninguna página corriendo, que es cuando el pad
        vuelve a mover al héroe: `Game_Map::IsAnyEventStarting`."""
        return self.esperar("que el jugador tome el control",
                            lambda p: not p.corriendo_una_pagina(),
                            tope, a_cada)

    # --- caminar -----------------------------------------------------------

    def caminar_a(self, destino, tope=4000, hasta=None, evitar=()):
        """Camina hasta la celda `destino` del mapa donde está.

        `hasta(partida)` corta antes si se cumple: es lo que hace que pisar una
        puerta a mitad de camino sea el final feliz del tramo y no un error de
        "me fui del mapa".

        `evitar` son celdas de más que no se pisan, además de las puertas: las
        que el `Mundo` no ve como salidas porque su destino no está escrito en
        el evento —los pisos que se rompen de la planta de reciclaje saltan con
        `RecallToLocation`—.

        Mientras camina atiende lo que se le cruce: si una página arranca —un
        evento de contacto, un cartel—, suelta el pad y le toca A hasta que
        termine, que es lo que hace el jugador. Y si algo le bloquea el paso
        —un NPC que pasaba por ahí—, marca esa celda y vuelve a planear.
        """
        map_id = self.p.mapa()
        gastado = 0
        # **Las puertas que no son la de este tramo se esquivan.** Son eventos
        # de contacto: pisar una a mitad de camino no es un rodeo, es irse del
        # mapa, y la prueba terminaba en Lashe City queriendo caminar por el
        # mapa 9. La primera vez pasó cruzando el 9 de punta a punta, donde el
        # camino corto sale por el borde de la derecha.
        evitar = {celda for celda, trigger, _ in
                  self.mundo.salidas(map_id, self.p.switch)
                  if trigger in (TRIGGER_CONTACTO, TRIGGER_CHOQUE)} | set(evitar)
        evitar.discard(destino)
        # Cuántas veces seguidas no se pudo dar el mismo paso. Un solo intento
        # fallido **no** es una celda bloqueada: recién teletransportado, el
        # fundido de la puerta se come varios ticks y el pad no mueve a nadie.
        # Dando por bloqueada la primera celda, la prueba se quedó a diez
        # celdas del guardia de la fábrica con el pasillo entero libre.
        fallos = collections.Counter()
        while gastado < tope:
            if hasta is not None and hasta(self.p):
                return self
            if self.p.byte("fundido"):
                self.p.correr(4)
                gastado += 4
                continue
            if self.p.mapa() != map_id:
                raise Trabado(
                    "caminando a %s el mapa cambió de %d a %d sin que nadie lo "
                    "pidiera. %s" % (destino, map_id, self.p.mapa(),
                                     self.estado()))
            if self.p.corriendo_una_pagina():
                gastado += self._atender(tope - gastado)
                continue
            aqui = self.celda()
            if aqui == destino:
                return self
            ruta = self.mundo.ruta(map_id, aqui, destino,
                                   self.p.switch, evitar)
            if ruta is None:
                raise Trabado(
                    "no hay camino de %s a %s en el mapa %d esquivando %s. %s"
                    % (aqui, destino, map_id, sorted(evitar), self.estado()))
            movio, ticks = self._paso(ruta[0], hasta)
            gastado += ticks
            if movio:
                fallos.clear()
            else:
                # Algo ocupa la celda de destino. No se sabe qué —un NPC anda
                # por ahí— así que después de insistir se la saca del plano y
                # se vuelve a planear; si era el único camino, el `ruta is
                # None` de arriba lo dice.
                x, y = aqui
                bloqueada = (x + ruta[0][0], y + ruta[0][1])
                fallos[bloqueada] += 1
                if fallos[bloqueada] >= INSISTIR:
                    if bloqueada == destino:
                        # La celda a la que se va está ocupada, y no hay rodeo
                        # posible: es el guardia de la fábrica, que es un
                        # evento de la capa del héroe y por eso **no se pisa**.
                        # Quien llamó sabe qué hacer —`activar` le habla desde
                        # al lado—, así que se lo dice en vez de dar vueltas.
                        raise Trabado(
                            "la celda %s está ocupada por algo que no se "
                            "corre. %s" % (destino, self.estado()))
                    evitar.add(bloqueada)
        if hasta is not None and hasta(self.p):
            return self
        raise Trabado("caminando a %s se gastaron los %d ticks. %s"
                      % (destino, tope, self.estado()))

    def _paso(self, paso, hasta=None):
        """Un paso de una celda. Devuelve (si se movió, ticks gastados)."""
        antes = self.celda()
        self.p.consola.apretar(BOTON[paso])
        for ticks in range(1, PASO_TOPE + 1):
            self.p._un_tick()
            if self.celda() != antes:
                break
            if self.p.corriendo_una_pagina():
                break
            if hasta is not None and hasta(self.p):
                break
        self.p.soltar()
        # Un tick con el pad suelto: si el paso terminó pegado a un evento de
        # contacto, es el tick donde la página arranca.
        self.p._un_tick()
        return self.celda() != antes, ticks + 1

    def viajar(self, destino, tope=40000, tope_tramo=8000):
        """Juega hasta llegar al mapa `destino`, por donde el juego deja ir.

        El plan se rehace **después de cada puerta** y no se calcula una vez al
        principio: los switches cambian mientras se juega —una cinemática abre
        una puerta que antes no estaba— y replanear cuesta veinte milisegundos
        contra los segundos que cuesta emular el tramo.
        """
        gastado = 0
        while self.p.mapa() != destino and gastado < tope:
            desde = (self.p.mapa(), self.celda())
            plan = self.mundo.plan(desde[0], desde[1], destino, self.p.switch,
                                   self.p.mapas)
            if plan is None:
                raise Trabado(
                    "no hay ninguna puerta que lleve de %s al mapa %d con los "
                    "switches que tiene puestos. %s"
                    % (desde, destino, self.estado()))
            celda, trigger, hacia, aterriza = plan[0]
            # El tramo terminó cuando el héroe está en el mapa de destino y en
            # la isla donde el teletransporte lo deja. Mirar sólo el mapa no
            # alcanza: media Lashe City son teletransportes de un mapa a sí
            # mismo, y `mapa()` no se mueve.
            islas = self.mundo.islas_desde(hacia, aterriza, self.p.switch)

            def llego(p, hacia=hacia, islas=islas):
                if p.mapa() != hacia:
                    return False
                aqui = (p.palabra("tile_x"), p.palabra("tile_y"))
                return self.mundo.islas(hacia, p.switch).get(aqui) in islas
            antes = self.p.cuadro
            if trigger in (TRIGGER_AUTO, TRIGGER_PARALELO):
                self.esperar("la escena del mapa %d" % desde[0], llego,
                             tope_tramo)
            elif trigger == TRIGGER_ACCION:
                self.activar(celda, llego, tope_tramo)
            else:
                self.caminar_a(celda, tope_tramo, hasta=llego)
                self.esperar("la puerta de %s" % (celda,), llego, 400)
            gastado += self.p.cuadro - antes
            if (self.p.mapa(), self.celda()) == desde:
                raise Trabado("la puerta de %s no movió nada. %s"
                              % (celda, self.estado()))
        if self.p.mapa() == destino:
            return self
        raise Trabado("viajando al mapa %d se gastaron los %d ticks. %s"
                      % (destino, tope, self.estado()))

    def activar(self, destino, hasta, tope=4000):
        """Le aprieta A al evento de la celda `destino`, hasta que `hasta` sea
        verdad.

        Son las dos formas que tiene RM2k y no una: a un evento de la capa de
        abajo se le habla **desde su propia celda** —`CheckEventTriggerHere`—,
        y a uno de la capa del héroe desde la celda de al lado, mirándolo. Cuál
        es cuál no se adivina desde afuera: el `.lmu` lo dice, pero la puerta de
        la casa de Talan es de las que se pisan y el save point del mapa 8
        también, mientras que la puerta del Emitter Room es de las otras. Así
        que se prueban las dos, empezando por la de encima, que es la que
        además deja al héroe donde el evento lo quiere.

        Este orden ya cobró una: `savepoint-guarda` de la tanda pasó un día
        entero en vacío por hablarle al save point de frente.
        """
        map_id = self.p.mapa()
        _, ancho, alto = self.mundo.mapa(map_id, self.p.switch)
        x, y = destino
        intentos = []
        if self.mundo.ruta(map_id, self.celda(), destino,
                           self.p.switch) is not None:
            intentos.append((destino, None))
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            vecina = (x + dx, y + dy)
            if not (0 <= vecina[0] < ancho and 0 <= vecina[1] < alto):
                continue
            if self.mundo.ruta(map_id, self.celda(), vecina,
                               self.p.switch) is None:
                continue
            intentos.append((vecina, (-dx, -dy)))
        if not intentos:
            raise Trabado("no se puede llegar ni a %s ni a ninguna celda "
                          "pegada, en el mapa %d. %s"
                          % (destino, map_id, self.estado()))
        for celda, mirar in intentos:
            if hasta(self.p):
                return self
            try:
                self.caminar_a(celda, tope, hasta=hasta)
            except Trabado:
                # Ir a pararse encima no salió —el evento bloquea, o alguien
                # se puso en el medio—: se prueba desde la celda que sigue.
                continue
            if hasta(self.p):
                return self
            if mirar is not None:
                self.mirar_a(mirar)
            self.p.tocar_ticks("a")
            # Y un rato de paciencia por intento, siguiéndole tocando A: la
            # página que arranca puede ser un diálogo entero —el guardia de la
            # fábrica pregunta y hay que contestarle— y lo que `hasta` mira
            # puede tardar decenas de ticks más, lo que dure el fundido. Si no
            # contesta, se prueba desde la celda que sigue.
            for _ in range(40):
                if hasta(self.p):
                    break
                self.p.correr(10, apretar_a=[self.p.cuadro + 8])
            if hasta(self.p):
                return self
        raise Trabado("el evento de %s no contestó desde ninguna de las %d "
                      "celdas probadas. %s"
                      % (destino, len(intentos), self.estado()))

    # --- elegir en un `ShowChoice` -----------------------------------------
    #
    # Tocar A donde el juego pide A elige siempre la opción de arriba, porque
    # `Window_Selectable` arranca con el cursor ahí. Para las demás ramas hay
    # que bajar el cursor, y eso tiene tres trampas, las tres de tiempo:
    #
    # * **la ventana no mira el pad mientras se compone**: `eleccion_tick`
    #   contesta cero mientras `msg_abierto` esté apagado, que son de nueve a
    #   diecinueve vueltas según el texto. Un toque ahí no pasa;
    # * **un toque se puede perder** aunque caiga con la ventana lista: la ROM
    #   lee el pad una vez por vuelta —ver `mirar_a`—;
    # * **un A de más elige**: la paciencia de `esperar` toca A a ciegas, y si
    #   uno cae con la elección recién compuesta se lleva la opción de arriba.
    #
    # Así que nada se toca sin mirar antes la RAM, y cada toque se comprueba.

    def _eleccion_lista(self):
        """La elección está en pantalla y mira el pad. Los dos bytes, igual
        que `abierta` de `pruebas/rpgmaker/test_elegir.py`: `eleg_activo` se
        prende en `op_choice`, antes de que la ventana termine de componerse."""
        return bool(self.p.byte("eleg_activo") and self.p.byte("msg_abierto"))

    def marcar(self, opcion, tope=4000):
        """Espera a que se abra el próximo `ShowChoice` y le deja el cursor en
        `opcion`, desde cero, **sin confirmar**. Es la mitad de `elegir`, suelta
        para poder sacarle una foto a la ventana con el cursor puesto.

        Mientras espera cierra los mensajes que haya antes —con A, que es lo
        que el juego pide ahí— pero **sólo cuando hay un mensaje abierto y la
        elección no**: el toque que cierra el último mensaje no puede elegir,
        porque la elección que arranca en esa misma vuelta todavía no está
        compuesta. Lo demás —rutas, esperas, fundidos— corre sin tocar nada.
        """
        p = self.p
        gastado = 0
        while not self._eleccion_lista():
            if gastado >= tope:
                raise Trabado("esperando un ShowChoice no se abrió ninguno en "
                              "%d ticks. %s" % (tope, self.estado()))
            antes = p.cuadro
            if p.byte("msg_abierto") and not p.byte("eleg_activo"):
                p.tocar_ticks("a")
            else:
                p._un_tick()
            gastado += p.cuadro - antes
        n = p.byte("eleg_n")
        if not 0 <= opcion < n:
            raise Trabado("la elección tiene %d opciones y se pidió la %d. %s"
                          % (n, opcion, self.estado()))
        # Abajo, de a un toque y mirando el cursor entre toque y toque. Un
        # toque perdido se repite; uno que llegó no se repite nunca, porque la
        # ventana mira flancos y el cursor ya dice dónde quedó. El tope es
        # generoso a propósito: con `INSISTIR` toques perdidos por renglón
        # también llega.
        for _ in range(n * INSISTIR):
            if p.byte("eleg_sel") == opcion:
                break
            if not p.byte("eleg_activo"):
                raise Trabado("la elección se cerró mientras se bajaba el "
                              "cursor. %s" % self.estado())
            p.tocar_ticks("down")
        else:
            raise Trabado("el cursor no llegó a la opción %d en %d toques de "
                          "abajo: quedó en %d. %s"
                          % (opcion, n * INSISTIR, p.byte("eleg_sel"),
                             self.estado()))
        # Mover el cursor recompone la ventana —ver `eleg_abrir`—, y una foto
        # sacada a mitad de eso muestra el renglón viejo. `msg_estado` en 1 es
        # "componiendo". No hace falta para elegir: sólo para mirar.
        for _ in range(PASO_TOPE):
            if p.byte("msg_estado") != 1:
                break
            p._un_tick()
        return self

    def confirmar(self):
        """Toca A sobre la elección abierta hasta que la resuelva, y
        comprueba que se eligió la opción marcada.

        Resuelta es que la ventana deje de estar lista: al elegir,
        `eleccion_tick` apaga `eleg_activo` y `msg_abierto` en la misma vuelta.
        Si la rama empieza con **otra** elección, `eleg_activo` se vuelve a
        prender enseguida, pero esa no está compuesta todavía, así que no se la
        confunde con la de antes ni se la contesta de paso.
        """
        p = self.p
        if not self._eleccion_lista():
            raise Trabado("no hay ninguna elección abierta para confirmar. %s"
                          % self.estado())
        marcada = p.byte("eleg_sel")
        for _ in range(INSISTIR * 2):
            if not self._eleccion_lista():
                break
            if p.byte("eleg_sel") != marcada:
                raise Trabado("el cursor se movió de %d a %d mientras se "
                              "confirmaba. %s" % (marcada, p.byte("eleg_sel"),
                                                  self.estado()))
            p.tocar_ticks("a")
        else:
            raise Trabado("la elección no contestó a %d toques de A. %s"
                          % (INSISTIR * 2, self.estado()))
        # Si ya se abrió la elección siguiente, `op_choice` volvió a poner el
        # cursor en cero y lo que eligió ésta no se puede leer más.
        if not p.byte("eleg_activo") and p.byte("eleg_sel") != marcada:
            raise Trabado("se confirmó con el cursor en %d y se eligió la %d. "
                          "%s" % (marcada, p.byte("eleg_sel"), self.estado()))
        return self

    def elegir(self, opcion, tope=4000):
        """Espera el próximo `ShowChoice`, pasando los mensajes de antes, y
        elige la opción `opcion`, desde cero. Es `marcar` y `confirmar`.

        Después de elegir no sigue: lo que la rama haga se espera con
        `esperar`, que sí toca A a ciegas, y eso vale mientras la rama no
        traiga otra elección —si la trae, es otro `elegir`—.
        """
        return self.marcar(opcion, tope).confirmar()

    # --- guardar en un save point ------------------------------------------

    def abrir_el_save_point(self, toques=40):
        """Parado sobre un save point, tocarle A hasta que la pantalla de
        ranuras esté a la vista, y dejarla ahí.

        Está separado de `guardar_en_el_save_point` porque hay una prueba que
        mira la pantalla **antes** de elegir: el cursor arranca en la ranura de
        la que se cargó, y elegir lo movería. Ver
        `test_el_cursor_de_guardar_arranca_en_la_ranura_en_uso`.
        """
        p = self.p
        for _ in range(toques):
            if p.byte("menu_abierto"):
                break
            p.consola.apretar("a")
            p.consola.correr(2)
            p.consola.apretar()
            p.consola.correr(8)
        if not p.byte("menu_abierto"):
            raise Trabado(
                "el save point no abrió la pantalla de ranuras en %d toques "
                "de A. %s" % (toques, self.estado()))
        # El mismo aire que `Partida.guardar_en` le da a la pantalla antes de
        # tocarle nada: sube su banco con la pantalla apagada y un toque que
        # caiga ahí se pierde.
        p.consola.correr(TITULO_AIRE)
        return self

    def guardar_en_el_save_point(self, ranura=0, toques=40):
        """Parado sobre un save point, tocarle A y elegir `ranura`.

        Es el camino de guardado **del juego** —`OpenSaveMenu`, el evento 66
        del mapa 8— y no el de la página de prueba de los casos `guardar*`.

        **Todo por cuadros de hardware, y ésa es la parte que hay que saber.**
        `OpenSaveMenu` bloquea adentro del intérprete —como `Scene_Save` en
        RM2k— así que mientras la pantalla de ranuras se ve `vueltas` no
        avanza: cualquier espera por ticks se planta con "la ROM no llegó al
        tick N", y ese error es el **éxito** disfrazado. Por lo mismo no sirve
        `activar`, que le toca A al evento con `Partida.correr`.

        Al volver se resincroniza `Partida.cuadro`, que quedó viejo por los
        cuadros que el jugador pasó eligiendo.
        """
        p = self.abrir_el_save_point(toques).p
        p._bajar_y_elegir(ranura)
        p.consola.correr(10)
        p._un_cuadro()
        return self

    def _atender(self, tope):
        """Una página está corriendo: tocarle A hasta que termine."""
        gastado = 0
        while gastado < tope and self.p.corriendo_una_pagina():
            paso = min(A_CADA, tope - gastado)
            self.p.correr(paso, apretar_a=[self.p.cuadro + paso - 2])
            gastado += paso
        return max(gastado, 1)
