#!/usr/bin/env python3
"""Construye lo que la consola debería estar mostrando, para comparar contra ella.

No alcanza con el render del mapa: ahora hay un personaje encima, y hay que
saber dónde quedó. Eso no se estima mirando la captura — se calcula con las
mismas reglas que sigue la ROM, y si la ROM lo dejó en otro lado la comparación
falla. Es lo mismo que se hizo en la Mega Drive.

Dónde queda es predecible porque se camina hasta chocar: contra un borde del
mapa la posición es exactamente el tamaño del mapa menos una celda. Y como la
ROM sólo anima cuando la posición realmente cambia, contra el borde el
personaje queda en su pose parada, que también es predecible.

Los colores del personaje son los ya fusionados a 15: el sprite de la consola
tiene 4 bits por pixel y no entran los 36 que trae el CharSet.

Y tampoco alcanza con dibujar el mapa que se pidió. Al entrar a uno, la ROM le
corre sus eventos automáticos, y ésos prenden switches, tiñen la pantalla y
teletransportan: acá se corre el mismo bytecode, con el mismo estado, para
terminar dibujando el mapa donde la consola realmente terminó.

Uso:
    python3 tools/snes_expect.py --map-id 7 --walk right -o esperado.png
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import animacion as animacion_mod
import eventos
import lcf
import rm2k
import pixeles
import snes_convert
from rm2k import collect_doors, collect_npcs, passability_map, puede_pasar
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                        find_resource, load_image)

# El paso del héroe son 256 unidades de RM2k por celda a `PASO_POR_VELOCIDAD`
# por cuadro: a la velocidad 4 son ocho cuadros. Este número es el puente entre
# la referencia —que sabe cuántas celdas se camina— y el emulador, que corre
# cuadros exactos; y desde el 2026-09-10 sale de la velocidad del héroe, que
# una ruta puede dejar cambiada. La ROM hace la misma cuenta en
# `paso_medio_por_vel`.
CUADROS_POR_CELDA = 8           # a la velocidad 4, que es la de arranque


def cuadros_por_celda(estado):
    paso = eventos.PASO_POR_VELOCIDAD[estado.ruta_heroe.velocidad - 1]
    return -(-eventos.SALTO_PASO // paso)


def cuadros_de_avance(estado, pixeles):
    """Cuántos cuadros tarda el héroe en andar esos pixeles a su velocidad."""
    paso = eventos.PASO_POR_VELOCIDAD[estado.ruta_heroe.velocidad - 1]
    return -(-pixeles * 16 // paso)

# Cuántos ticks se corren de más después de la caminata. La ROM llega uno o dos
# cuadros después de `pasos x 8` —el pad se lee una vez por cuadro y el primero
# se pierde, y según la dirección la cámara termina de acomodarse un cuadro más
# tarde—, así que sin esto el héroe todavía no llegó. Ocho es una celda entera:
# alcanza de sobra y sigue siendo un número exacto de cuadros.
#
# Hasta el 2026-09-09 esto vivía sólo en snes_correr.py y era holgura: la ROM
# corría ocho cuadros que de este lado no los vivía nadie. Con eventos que se
# mueven solos eso dejó de dar lo mismo —los autos de Lashe City corrían ocho
# cuadros de un solo lado—, así que ahora los vive la referencia y los anota en
# el plan. El de snes_correr.py pasa a ir en cero cuando hay plan.
MARGEN = 8

# El ciclo de caminata de la ROM, de `animate_hero` en main.s: cuatro pasos
# sobre tres columnas del CharSet —0, 1, 2, 1—, uno cada ANIM_FRAMES cuadros, y
# quieto vuelve al del medio. Se arranca en el 1 con el contador lleno.
#
# Esto no lo modelaba nadie de este lado, y por eso las poses de caminata no las
# verificaba ninguna prueba: cuando el héroe choca contra la pared `moving` es
# cero, así que la única pose que llegaba a compararse era la parada.
ANIM_FRAMES = 6
ANIM_INICIAL = 1


def columna_de_caminata(cuadros_moviendose, velocidad=4):
    """En qué columna del CharSet está el héroe tras N cuadros caminando.

    El frame cambia cada `ANIM_PARADO[velocidad - 1]` cuadros: seis a la
    velocidad de arranque, `ANIM_FRAMES`."""
    cada = eventos.ANIM_PARADO[velocidad - 1]
    paso = (ANIM_INICIAL + cuadros_moviendose // cada) % 4
    return 1 if paso == 3 else paso

SCREEN_W, SCREEN_H = 256, 224

# En una misma línea de pantalla la consola no dibuja más de 34 tiles de 8x8 de
# sprite, ni más de 32 objetos. Un objeto de 32x32 aporta cuatro tiles a cada
# línea que cruza, así que a partir de nueve personajes juntos empieza a perder
# los últimos. Se recorren en el orden de OAM y se corta donde se acaba el
# presupuesto.
OBJ_TILES_PER_LINE = 34
OBJ_PER_LINE = 32
OBJ_TILES = OBJ_W // 8 if False else 4
TILE = 16                       # la celda de RM2k sobre la que se para
STAND = 1                       # el frame del medio del ciclo de caminata

# Las direcciones de RM2k, en el orden en que están en el CharSet.
DIRECTIONS = {"up": 0, "right": 1, "down": 2, "left": 3}
# Para el log, que antes decía "abajo" siempre que no se caminara —aunque una
# ruta forzada hubiera girado al héroe—, y mandó a buscar un error que no era.
NOMBRE_DIR = {0: "arriba", 1: "derecha", 2: "abajo", 3: "izquierda"}
# Los mismos, como desplazamiento en celdas.
PASOS = eventos.RUTA_PASOS      # una sola definición: la del modelo
WALK = {"none": None, "up": (0, -1), "down": (0, 1),
        "left": (-1, 0), "right": (1, 0)}


class Mundo:
    """Los mapas que entraron en la ROM, cargados a medida que se los pisa.

    `ids` es la tabla de la ROM en su orden, porque el orden es dato: un
    teletransporte compilado no guarda el número de mapa de RM2k sino el índice
    en esta tabla. Si acá estuviera en otro orden, el mismo bytecode llevaría a
    otro mapa y la comparación mediría dos ROMs distintas.
    """

    def __init__(self, renderer, game_dir, ids, prueba=None, mensajes=None,
                 grupo=(), con_timer=False, graficos_de_prueba=()):
        self.prueba = prueba
        # Los (CharSet, índice) de `--grafico-de-prueba`, que la página
        # inventada usa con la orden 34. Se registran **después** de los del
        # juego y sólo en el mapa donde arranca la ROM, que es el mismo orden
        # y el mismo lugar que en el conversor: el índice que lleva el
        # bytecode tiene que significar lo mismo de los dos lados.
        self.graficos_de_prueba = tuple(graficos_de_prueba)
        # Para `npcs_dibujables`: qué líderes puede haber y cuántas paletas de
        # sprite quedan, que deciden qué eventos dibujados con un tile se ven.
        self.grupo = list(grupo)
        self.con_timer = con_timer
        self.renderer = renderer
        self.game_dir = game_dir
        self.ids = list(ids)
        self.indices = {map_id: i for i, map_id in enumerate(self.ids)}
        self.cache = {}
        self.lluvia_cache = {}
        # Y si en cada mapa se dibujan las animaciones de batalla: ver
        # `dibuja_animacion`. Cuesta rehacer el reparto de paletas, así que se
        # guarda como el de la lluvia.
        self.anim_cabe_cache = {}
        # Y cuántas paletas de sprite se reparten los personajes de cada mapa,
        # que no siempre son las ocho: ver `tope_de_paletas`.
        self.tope_cache = {}
        # Y en qué mapa quedó el cartel, que es el que se lleva una paleta de
        # sprite de más: ver `cartel_de_mapa`.
        self.cartel_map = None
        self.cartel_visto = False
        self.hay_lluvia = None
        self.npcs_cache = {}
        self.paginas_cache = {}
        # Los gráficos a los que las rutas de cada mapa cambian con la orden
        # 34. Van por mapa y no globales —ver `eventos.Graficos`— y se guardan
        # porque el dibujo los necesita: la ruta lleva el índice, y de acá sale
        # el CharSet.
        self.graficos_cache = {}
        # Qué eventos animan quietos en cada mapa. Sale de la misma función que
        # se lo dice al conversor: los que además caminan llevan el contador en
        # su ranura de ruta y no entran acá.
        self.anima_cache = {}
        # Qué poses puede mostrar cada gráfico en cada mapa: lo pide el dibujo
        # de cada cuadro y cuesta recorrer los eventos, así que se guarda.
        self.poses_cache = {}
        self.mensajes = mensajes
        # Cada cuántos pasos hay un encuentro, si una ROM de prueba lo forzó.
        # None es "lo que diga el árbol del juego". Es el mismo
        # `--encuentros-de-prueba` del conversor y tiene que valer lo mismo:
        # de acá sale en qué paso sale el encuentro, y eso decide qué se ve.
        self.pasos_encuentro = None
        # Los temas se numeran igual que en el conversor, en el orden en que los
        # PlayBGM los piden. Acá no suena nada —la comparación es de pixeles—
        # pero el opcode **ocupa dos bytes** en el bytecode, así que si un lado
        # lo emitiera y el otro no, los dos recorrerían streams distintos.
        self.temas = eventos.Temas()
        # Y el cartel del `ShowPicture`, numerado igual que en el conversor: la
        # ROM lleva uno solo y el bytecode no dice cuál, así que si un lado lo
        # aceptara y el otro no, los dos leerían streams distintos. Ver
        # `eventos.Imagenes`.
        self.imagenes = eventos.Imagenes(game_dir)
        self.imagenes.elegir(self.mapa(i)[0] for i in self.ids)
        # Y las ranuras reservadas de la tabla de gráficos, por lo mismo que el
        # cartel: si un lado numerara distinto que el otro, los dos leerían el
        # mismo índice y dibujarían otro CharSet. Ver `eventos.asociaciones_de`.
        self.asociaciones = eventos.asociaciones_de(
            self.mapa(i)[0] for i in self.ids)
        # Y el de `--sprite-de-prueba`, con la misma regla que en el conversor.
        # Los índices de esta tupla son posicionales y **se corren cuando dos
        # ramas agregan un campo cada una**: el 2026-09-13 quedaron dos usos
        # apuntando al campo de otro —`sprite` leyendo `parar`, la tecla
        # leyendo `rama_item`— porque git los auto-mergeó lejos del conflicto.
        # Si se agrega un campo, hay que hacer `grep -n 'prueba\[2[0-9]\]'` y
        # mirarlos todos, no sólo los que git marcó.
        if prueba is not None and prueba[24] and (
                prueba[24][1], prueba[24][2]) not in self.asociaciones:
            self.asociaciones.append((prueba[24][1], prueba[24][2]))
        # El mismo índice de variables que el conversor: el del juego entero.
        eventos.indexar_variables(game_dir, (
            snes_convert.variables_de_prueba(prueba[15], prueba[16],
                                             prueba[25])
            if prueba is not None else ()))
        eventos.indexar_animaciones(game_dir)
        # Y los eventos comunes, que `CallEvent` compila en el lugar:
        # los dos lados tienen que mirar la misma base.
        eventos.indexar_comunes(game_dir)
        eventos.indexar_audio_de_batalla(game_dir)
        # Y lo que el LDB dice del equipo y de las habilidades de cada actor,
        # que es lo que contestan las dos ramas de actor con dos operandos.
        eventos.indexar_actores(game_dir)
        if mensajes is not None:
            # Con ventana los mapas se compilan **todos y en el orden de la
            # tabla**, acá y no cuando el héroe pise cada uno. El bloque de
            # textos es de la ROM entera y los desplazamientos salen del orden
            # en que se van juntando: compilar el mapa 3 antes que el 1 porque
            # una puerta llevó para allá le daría al mismo texto otro número
            # que el que emitió el conversor, y los dos lados dibujarían
            # mensajes distintos con el mismo bytecode.
            for otro in self.ids:
                self.paginas(otro)

    def paginas(self, map_id):
        """Las páginas de evento del mapa, compiladas como las compiló la ROM."""
        if map_id not in self.paginas_cache:
            self.graficos_cache[map_id] = eventos.Graficos(self.asociaciones)
            paginas = eventos.paginas_del_mapa(self.mapa(map_id)[0],
                                               self.indices.get, self.mensajes,
                                               self.temas,
                                               self.graficos_cache[map_id],
                                               self.imagenes)
            if self.graficos_de_prueba and map_id == self.ids[0]:
                for charset, index in self.graficos_de_prueba:
                    self.graficos_cache[map_id].indice(charset, index)
            if self.prueba is not None and map_id == self.ids[0]:
                # La página inventada va sólo en el mapa donde arranca la ROM,
                # que es el mismo que el conversor le agrega la suya.
                espera, tinte = 0, ()
                if self.prueba[0] is not None:
                    espera, *tinte = self.prueba[0]
                numero = eventos.evento_de_prueba(self.mapa(map_id)[0])
                paginas = paginas + [dict(EVENTO_DE_PRUEBA, evento=numero,
                                          codigo=eventos.pagina_de_prueba(
                                              espera, tinte,
                                              self.prueba[1] or (),
                                              self.prueba[2],
                                              self.prueba[3],
                                              self.prueba[4],
                                              self.prueba[5],
                                              self.prueba[6],
                                              self.prueba[7],
                                              frecuencia=self.prueba[8],
                                              sacudida=self.prueba[9],
                                              fundir_bgm=self.prueba[10],
                                              pan=self.prueba[11],
                                              rama=self.prueba[12],
                                              destello=self.prueba[13],
                                              guardar=self.prueba[14],
                                              variables=self.prueba[15],
                                              rama_var=self.prueba[16],
                                              items=self.prueba[17],
                                              acceso=self.prueba[18],
                                              lluvia=self.prueba[19],
                                              animacion=self.prueba[20],
                                              eventos_mapa=eventos.Eventos(
                                                  self.mapa(map_id)[0]),
                                              batalla=self.prueba[21],
                                              parar=self.prueba[22],
                                              rama_item=self.prueba[23],
                                              temas=self.temas,
                                              sprite=self.prueba[24],
                                              graficos=self.graficos_cache[
                                                  map_id],
                                              tecla=self.prueba[25],
                                              rama_actor=self.prueba[26])),
                                     dict(PAGINA_DE_PRUEBA_APAGADA,
                                          evento=numero)]
            self.paginas_cache[map_id] = paginas
        return self.paginas_cache[map_id]

    def anima_quieto(self, map_id):
        """Los eventos del mapa que recorren el ciclo de caminata sin moverse.

        `animation_type` 1 y 3 de RM2k. Sale de `eventos_movibles`, que es
        quien se lo dice al conversor: los dos lados tienen que animar a los
        mismos, y quién queda afuera —el que además tiene ruta— lo decide una
        sola función.
        """
        return self.movibles(map_id)[2]

    def movibles(self, map_id):
        """`snes_convert.eventos_movibles` del mapa, con la ruta inventada de
        `--ruta-de-evento` ya sumada a los que caminan.

        Es el mismo dato que el conversor calcula en `convertir`, y desde que
        la paleta se elige sobre las poses que se ven **decide colores**: un
        evento que camina muestra las doce y uno quieto una sola. Sale de una
        función y no de dos copias por lo de siempre: dos listas que se armen
        distinto elegirían dos paletas y la comparación mediría dos ROMs.
        """
        if map_id not in self.anima_cache:
            movibles, graficos, animados, giran = snes_convert.eventos_movibles(
                self.mapa(map_id)[0], self.indices.get,
                con_ventana=self.mensajes is not None)
            if (self.prueba is not None and self.prueba[3]
                    and map_id == self.ids[0]):
                movibles = movibles | {self.prueba[3][0] - 1}
            self.anima_cache[map_id] = (movibles, graficos, animados, giran)
        return self.anima_cache[map_id]

    def poses(self, map_id):
        """Qué poses puede mostrar cada (CharSet, índice) en este mapa.

        Es `snes_convert.poses_del_mapa` con los mismos datos que el conversor:
        de acá salen los quince colores de cada personaje."""
        if map_id in self.poses_cache:
            return self.poses_cache[map_id]
        movibles, _graficos, animados, giran = self.movibles(map_id)
        self.poses_cache[map_id] = snes_convert.poses_del_mapa(
            self.renderer, self.mapa(map_id)[0],
            snes_convert.lideres_posibles(self.renderer, self.ids, self.grupo,
                                          self.mensajes is not None),
            movibles, giran, self.graficos(map_id).pares, animados)
        return self.poses_cache[map_id]

    def graficos(self, map_id):
        """Los gráficos que las rutas de este mapa piden, en el mismo orden en
        que los numeró el conversor."""
        self.paginas(map_id)            # los junta compilando las páginas
        return self.graficos_cache[map_id]

    def encuentros(self, map_id):
        """El estado de los encuentros al azar al entrar a un mapa.

        Nace nuevo en cada mapa porque entrar a uno es un `MoveTo`, y `MoveTo`
        pone el acumulado en cero. Las zonas y los pasos salen del árbol, que
        es donde RM2k los guarda: ver `eventos.zonas_de_encuentro`.
        """
        game_map = self.mapa(map_id)[0]
        tree = self.renderer.tree
        pasos = (self.pasos_encuentro if self.pasos_encuentro is not None
                 else tree.encounter_steps.get(map_id,
                                               eventos.ENC_PASOS_DEFECTO))
        return eventos.Encuentros(
            pasos, eventos.zonas_de_encuentro(tree, map_id, game_map.width,
                                              game_map.height))

    def mapa(self, map_id):
        if map_id not in self.cache:
            game_map = self.renderer.cargar_mapa(
                os.path.join(self.game_dir, "Map%04d.lmu" % map_id))
            chipset = self.renderer.database.chipsets[game_map.chipset_id]
            passable = passability_map(game_map, build_passability(chipset))
            ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
            puertas = {(p["x"], p["y"]): p for p in collect_doors(game_map)
                       if p["mapa"] in self.ids}
            self.cache[map_id] = (game_map, passable, ocupadas, puertas)
        return self.cache[map_id]

    def npcs(self, map_id):
        """Los NPCs que se dibujan en el mapa: los mismos que dibuja la ROM.

        Es `snes_convert.npcs_dibujables`, con los mismos líderes posibles y
        el mismo tope de paletas que usó el conversor: un evento dibujado con
        un tile que no entró en las paletas de sprite no se dibuja de ningún
        lado. Para chocar y para las velocidades siguen valiendo todos, por
        `collect_npcs` directo.
        """
        if map_id not in self.npcs_cache:
            game_map = self.mapa(map_id)[0]
            snes_convert.args_game_dir[0] = self.game_dir
            lideres = snes_convert.lideres_posibles(
                self.renderer, self.ids, self.grupo,
                self.mensajes is not None)
            # Con los gráficos de la orden 34, que son un personaje más y
            # piden paleta: sin ellos acá el reparto sería otro y un evento
            # dibujado con un tile podía entrar de este lado y no del otro.
            self.npcs_cache[map_id] = snes_convert.npcs_dibujables(
                self.renderer, game_map, lideres,
                min(7 if self.con_timer else 8,
                    self.tope_de_paletas(map_id)),
                self.graficos(map_id).pares,
                poses=self.poses(map_id))
        return self.npcs_cache[map_id][0]

    def lleva_lluvia(self, map_id):
        """Si en este mapa se dibujan las gotas: la ROM las lleva si alguna
        página pone lluvia y si entran en las paletas de sprite. Es
        `snes_convert.lluvia_cabe` sobre el mismo reparto que hace el
        conversor —con el tope de ocho, los colores del cronómetro y los
        personajes de un solo mapa—, que no es el que cachea `npcs`."""
        if map_id in self.lluvia_cache:
            return self.lluvia_cache[map_id]
        snes_convert.args_game_dir[0] = self.game_dir
        if self.hay_lluvia is None:
            self.hay_lluvia = (snes_convert.hay_lluvia(self.ids)
                               or (self.prueba is not None
                                   and self.prueba[19] is not None))
        cabe = False
        if self.hay_lluvia:
            timer_colores = ()
            if self.con_timer:
                import ventana as ventana_mod
                timer_colores = sorted(snes_convert.colores_del_timer(
                    ventana_mod.skin(self.game_dir,
                                     self.renderer.database.system_name)))
            solos = {c for c, n in snes_convert.mapas_por_personaje(
                self.renderer, self.ids, self.game_dir).items() if n == 1}
            lideres = snes_convert.lideres_posibles(
                self.renderer, self.ids, self.grupo,
                self.mensajes is not None)
            tope = self.tope_de_paletas(map_id)
            reparto = snes_convert.npcs_dibujables(
                self.renderer, self.mapa(map_id)[0], lideres, tope,
                self.graficos(map_id).pares,
                timer_colores, solos, self.poses(map_id))[2]
            cabe = snes_convert.lluvia_cabe(reparto[0], reparto[3],
                                            timer_colores, tope)
        self.lluvia_cache[map_id] = cabe
        return cabe

    def _timer_colores(self):
        """Los dos colores del cronómetro, si esta ROM lo lleva."""
        if not self.con_timer:
            return ()
        import ventana as ventana_mod
        return sorted(snes_convert.colores_del_timer(
            ventana_mod.skin(self.game_dir,
                             self.renderer.database.system_name)))

    def _solos(self):
        return {c for c, n in snes_convert.mapas_por_personaje(
            self.renderer, self.ids, self.game_dir).items() if n == 1}

    def muestra_animacion(self, map_id):
        """Si alguna página de este mapa puede mostrar una animación de
        batalla que se dibuje. Es la misma función que usa el conversor para
        reservarle la VRAM: `snes_convert.mapa_muestra_animacion`."""
        snes_convert.args_game_dir[0] = self.game_dir
        extra = ()
        if self.prueba is not None and map_id == self.ids[0] and self.prueba[20]:
            extra = tuple(self.prueba[20])[:1]
        return snes_convert.mapa_muestra_animacion(
            self.mapa(map_id)[0], self.renderer, extra)

    def tope_de_paletas(self, map_id):
        """Cuántas paletas de sprite reparte este mapa entre sus personajes.

        Es `snes_convert.tope_de_paletas_del_mapa`, la misma que usa el
        conversor: un mapa que muestra animaciones de batalla le deja una a la
        caja de la animación, y eso cambia cómo se cuantiza a sus personajes.
        """
        if map_id not in self.tope_cache:
            snes_convert.args_game_dir[0] = self.game_dir
            lideres = snes_convert.lideres_posibles(
                self.renderer, self.ids, self.grupo, self.mensajes is not None)
            self.tope_cache[map_id] = snes_convert.tope_de_paletas_del_mapa(
                self.renderer, self.mapa(map_id)[0], lideres,
                self.graficos(map_id).pares, self._timer_colores(),
                self._solos(), self.poses(map_id),
                self.muestra_animacion(map_id))
        return self.tope_cache[map_id]

    def cartel_de_mapa(self):
        """El mapa de la tabla que se llevó los tiles del cartel, o None.

        El conversor lo decide recorriendo los mapas en el orden de la tabla y
        quedándose con el primero que muestre uno; acá se repite con un
        registro nuevo, porque el de `self.imagenes` ya está tomado desde el
        arranque y no dice en cuál fue.
        """
        if not self.cartel_visto:
            self.cartel_visto = True
            registro = eventos.Imagenes(self.game_dir)
            for otro in self.ids:
                if registro.elegir([self.mapa(otro)[0]]) is not None:
                    self.cartel_map = otro
                    break
        return self.cartel_map

    def dibuja_animacion(self, map_id):
        """Si en este mapa se dibujan las animaciones de batalla.

        Es `snes_convert.animacion_cabe` sobre el mismo reparto que hace el
        conversor, igual que `lleva_lluvia` con las gotas: la caja necesita una
        paleta de sprite entera y en un mapa que ya use las ocho no hay. La
        otra mitad del criterio —que sus 64 tiles entren en el banco— no se
        repite acá: ahí el conversor **corta**, así que si la ROM se armó, el
        mapa tiene lugar. Ver `animacion_de_mapa`.
        """
        if map_id in self.anim_cabe_cache:
            return self.anim_cabe_cache[map_id]
        snes_convert.args_game_dir[0] = self.game_dir
        if not self.muestra_animacion(map_id):
            self.anim_cabe_cache[map_id] = False
            return False
        timer_colores = self._timer_colores()
        lideres = snes_convert.lideres_posibles(
            self.renderer, self.ids, self.grupo, self.mensajes is not None)
        tope = self.tope_de_paletas(map_id)
        reparto = snes_convert.npcs_dibujables(
            self.renderer, self.mapa(map_id)[0], lideres, tope,
            self.graficos(map_id).pares,
            timer_colores, self._solos(), self.poses(map_id))[2]
        cabe = snes_convert.animacion_cabe(
            reparto[0], reparto[3], timer_colores,
            self.lleva_lluvia(map_id),
            self.cartel_de_mapa() == map_id, tope)
        self.anim_cabe_cache[map_id] = cabe
        return cabe

    def paleta_de_sprite(self, map_id):
        """Qué (CharSet, índice) entraron en las paletas de sprite del mapa.

        Lo mira el dibujo de la orden 34: un gráfico que no entró no se
        dibuja, igual que una página cuyo gráfico quedó afuera."""
        self.npcs(map_id)
        return self.npcs_cache[map_id][2][1]

    def paleta_prestada(self, map_id, clave):
        """La paleta ajena que le tocó a un gráfico, o None si tiene la suya.

        Desde que se dibujan **todos** los eventos, el que no consigue paleta
        propia usa la de otro. Acá hace falta el mismo dato que del lado del
        cartucho para dibujarlo igual de mal."""
        self.npcs(map_id)
        paletas, paleta_de, propios = self.npcs_cache[map_id][2][:3]
        prestadas = self.npcs_cache[map_id][2][5]
        if clave in propios or clave not in prestadas:
            return None
        return paletas[paleta_de[clave]]


# El mismo tope que `saltos_restantes` en la ROM: dos mapas que se
# teletransporten entre sí colgarían a los dos lados, y una prueba colgada no
# le dice nada a nadie.
SALTOS_MAX = 8


class DemasiadosSaltos(RuntimeError):
    """Se alcanzó el tope de teletransportes encadenados. Ver `SALTOS_MAX`."""


# Cómo se ve la página inventada en la tabla. El número de evento es alto a
# propósito: tiene que no chocar con ninguno del mapa.
EVENTO_DE_PRUEBA = {"evento": 0, "pagina": 0,
                    "trigger": eventos.TRIGGER_AUTOMATICO,
                    "switch_a": 0, "switch_b": 0, "actor": 0, "variable": None,
                    "item": 0, "capa": 0,
                    "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                    "codigo": b""}

# La segunda página del evento inventado: sin código y pidiendo el switch que
# la primera prende al terminar. Gana en cuanto ese switch está —la activa es
# la de número más alto que cumple— y con eso la primera deja de repetirse. Es
# el mismo idioma con el que las páginas del juego se apagan solas.
PAGINA_DE_PRUEBA_APAGADA = dict(EVENTO_DE_PRUEBA, pagina=1,
                                switch_a=eventos.SWITCH_DE_PRUEBA)


def puede_caer(passable, game_map, x, y):
    """Si se puede aterrizar en esa celda, que no es lo mismo que pisarla.

    Es `Game_Map::CheckOrMakeWayEx` con el personaje saltando: se saltea la cara
    que se deja —de ahí que un salto pueda salir de un lugar del que no se
    podría caminar— y la celda de destino tiene que ser pasable por **los cuatro
    lados**, no sólo por la que se entra.
    """
    if not (0 <= x < game_map.width and 0 <= y < game_map.height):
        return False
    cuatro = (rm2k.PASS_UP | rm2k.PASS_DOWN | rm2k.PASS_LEFT | rm2k.PASS_RIGHT)
    return passable[y * game_map.width + x] & cuatro == cuatro


def paso_de_ruta(estado, passable, game_map, x, y, paginas=()):
    """Un cuadro de la ruta forzada del héroe, en celdas.

    Devuelve (x, y, llegó), donde `llegó` es que en este cuadro terminó el
    **último** paso de la ruta: es el único en que RM2k mira si el héroe pisó
    un evento de contacto. `Game_Player::UpdateMovement` no lo mira mientras
    `IsMoveRouteOverwritten()`, y un movimiento que es la última orden cancela
    la ruta entera antes de ese chequeo —`Game_Character::UpdateMovement`,
    comentado ahí mismo—; con órdenes por leer, aunque sean giros o esperas,
    la ruta sigue puesta y no se mira. Un salto que termine la ruta también
    cuenta en RM2k y acá no —ni en la ROM—: ninguna ruta del juego termina
    saltando sobre un evento de contacto, y si alguna vez pasa, es acá.

    La celda se mueve al **empezar** el paso y los pixeles van detrás, que es lo
    que hace la ROM: `begin_step` deja el índice en la celda nueva con dieciséis
    pixeles por recorrer, y `advance_step` los va comiendo de a dos por cuadro.
    Los pixeles que faltan quedan en `estado.paso_cuadros`, y `hero_position`
    los descuenta: sin eso la referencia mostraba al héroe ya en la celda de
    destino mientras la ROM lo mostraba a mitad de camino. En el cuadro final da
    igual —por eso no se notó hasta comparar durante la caminata— y en los
    intermedios son 560 pixeles de diferencia.
    """
    # Y los eventos de su capa le cierran el paso, como con el pad: es el
    # mismo `MakeWay`. Atravesando paredes no mira a nadie, que es el
    # `if (self.GetThrough()) return true;` de arriba de todo.
    def libre(cx, cy):
        return estado.ruta_heroe.atraviesa or not eventos.bloqueada(
            paginas, estado, (cx, cy), eventos.LAYER_MISMA)

    def pasa(cx, cy):
        return eventos.pasabilidad_de_evento(paginas, estado, (cx, cy))

    def puede(direccion, desde=(0, 0)):
        dx, dy = PASOS[direccion]
        ox, oy = desde
        return rm2k.puede_pasar(passable, game_map.width, game_map.height,
                                x + ox, y + oy, dx, dy, pasa_evento=pasa) \
            and libre(x + ox + dx, y + oy + dy)

    antes = estado.paso_cuadros
    direccion = estado.cuadro_de_ruta(
        puede,
        saltar=lambda dx, dy: (puede_caer(passable, game_map, x + dx, y + dy)
                               and libre(x + dx, y + dy)),
        existe=lambda d: (0 <= x + PASOS[d][0] < game_map.width
                          and 0 <= y + PASOS[d][1] < game_map.height))
    salto = estado.ruta_heroe.arranco_salto
    if salto is not None:
        return x + salto[0], y + salto[1], False
    if direccion is not None and antes == 0:
        dx, dy = PASOS[direccion]
        return x + dx, y + dy, False  # el paso arranca: la celda ya es la nueva
    # El paso terminó en este cuadro —es el mismo cuadro en que `advance_step`
    # deja `step_left` en cero— y no quedan órdenes: ver arriba.
    llego = antes > 0 and estado.paso_cuadros == 0 and not estado.ruta
    return x, y, llego


def paso_del_paralelo(estado, passable, game_map, heroe, paginas=(),
                      congelada=False):
    """Cómo `Interprete.cuadro` mueve al evento cuyo intérprete paralelo acaba
    de correr. Ver `eventos.Interprete.cuadro_de_paralelos`: en RM2k el paso de
    un evento va pegado a su intérprete y no al final de la vuelta."""
    return lambda indice: cuadro_de_eventos(estado, passable, game_map, heroe,
                                            paginas, congelada, solo=(indice,))


def cuadro_de_eventos(estado, passable, game_map, heroe, paginas=(),
                      congelada=False, solo=None):
    """Un cuadro de lo que corre solo: las rutas de los eventos y los destellos.

    `heroe` es la celda del héroe: `face_hero` la necesita, y en RM2k es la
    de `GetX()`/`GetY()`, o sea la de destino si está a mitad de un paso. Y
    desde el 2026-09-05 también le cierra el paso a los eventos de su capa,
    igual que ellos entre sí: `paginas` es de donde sale la capa de cada uno.

    Va todo junto porque el orden importa y es uno solo: la ROM los avanza en
    el mismo lugar del lazo, después del intérprete y después del héroe.

    Se les aplica la misma regla de paso que al héroe —las dos caras, la que se
    deja y la que se entra— y sin mirar quién está parado dónde, que es lo que
    hace `paso_de_ruta`. Un movimiento bloqueado se saltea; en las 26 rutas de
    este juego pasa una sola vez, en el mapa 117, y por esa sola vez hay que
    modelarlo: si los dos lados lo ignoraran igual, esa ruta duraría ocho
    cuadros de más de los dos lados y la comparación daría cero.
    """
    def libre(indice, cx, cy):
        # Un evento sin página activa no choca con nadie —`IsActive()`—, y
        # el que atraviesa paredes tampoco: `Ruta.cuadro` ya no llama con
        # `atraviesa` puesto, así que acá sólo queda la capa.
        capa = eventos.capa_activa(paginas, estado, indice)
        return capa is None or not eventos.bloqueada(
            paginas, estado, (cx, cy), capa, ignorar=indice, heroe=heroe)

    def pasa(cx, cy):
        return eventos.pasabilidad_de_evento(paginas, estado, (cx, cy))

    def puede(indice, x, y, direccion):
        # La celda de partida ya viene corrida por el codo de la diagonal:
        # `cuadro_de_rutas_ev` le suma el `desde` antes de llamar.
        dx, dy = PASOS[direccion]
        return rm2k.puede_pasar(passable, game_map.width, game_map.height,
                                x, y, dx, dy, pasa_evento=pasa) \
            and libre(indice, x + dx, y + dy)

    def existe(x, y, direccion):
        """Si la celda de destino está adentro del mapa.

        Es lo único que frena a quien atraviesa paredes: en
        `Game_Map::CheckOrMakeWayEx` el `IsValid` va antes que el
        `if (self.GetThrough()) return true;`. Ver `puede_celda` en main.s.
        """
        dx, dy = PASOS[direccion]
        return 0 <= x + dx < game_map.width and 0 <= y + dy < game_map.height

    # La celda del héroe queda anotada en el estado, que es donde la lee el
    # intérprete —la clase 6 de `ControlVars`— y donde la ROM la tiene en
    # `tile_x`/`tile_y`. Acá y no antes a propósito: esto corre después del
    # intérprete y después del paso del héroe, igual que `move_hero` corre
    # después de `eventos_tick`, así que la página del cuadro que viene lee la
    # celda con la que terminó éste. Ver `Estado.poner_heroe`.
    estado.poner_heroe(*heroe)
    estado.cuadro_de_rutas_ev(
        puede,
        lambda cx, cy, indice: (puede_caer(passable, game_map, cx, cy)
                                and libre(indice, cx, cy)),
        heroe=heroe, congelada=congelada, solo=solo, existe=existe)
    if solo is not None:
        # La vuelta de un evento suelto, la que va pegada a su intérprete
        # paralelo: sólo su paso. Lo demás —los destellos, el cronómetro, la
        # sacudida— es de la pantalla y va una vez por cuadro, más abajo.
        return
    # Un cuadro entero del mundo, y por acá pasan todos: el lazo con
    # presupuesto, la entrada, el asentamiento y la caminata. Contarlos acá es
    # lo que le deja al plan decir cuántos ticks correr. La vuelta de un evento
    # suelto no cuenta: ya salió más arriba.
    estado.ticks += 1
    estado.cuadro_de_animacion()    # antes que los destellos que dispara
    estado.cuadro_de_dibujo()       # y su dibujo, que dura más que las entradas
    estado.cuadro_de_flashes()
    estado.cuadro_de_timer()
    estado.cuadro_de_sacudida()
    estado.cuadro_de_pan()
    estado.cuadro_de_destello()
    estado.cuadro_de_imagen()
    estado.cuadro_de_lluvia()


def entrar_al_mapa(mundo, estado, map_id, entrada=None, cuadros=None,
                   apretar_a=None, mirando=None, tocar=None):
    """Entra a un mapa y le corre los eventos automáticos, como `cargar_mapa`.

    Primero se para al héroe —donde diga la puerta o el teletransporte que nos
    trajo, y si no, donde el mapa lo pone— y recién después corren los eventos,
    que es el orden de la ROM: una página que teletransporta pisa esa posición,
    pero una que sólo tiñe la deja donde estaba.

    Si un evento pide mudarse, el ciclo se repite acá y no adentro del
    intérprete, con el mismo tope de vueltas que la consola.

    `estado` sobrevive a los mapas: los switches que prende una página son los
    que deciden qué página está activa en el siguiente, y el tinte se queda
    puesto hasta que otro lo cambie.
    """
    saltos = SALTOS_MAX
    # El presupuesto de cuadros es de toda la entrada, no de cada mapa: una
    # página que teletransporta y sigue corriendo cruza el corte, y volver a
    # contar desde cero en el mapa nuevo le regalaría los cuadros de la espera
    # que venía haciendo.
    restantes = cuadros
    # Y la página que estuviera corriendo sobrevive al teletransporte. En RM2k
    # `CommandTeleport` hace `index++` y devuelve false: reserva el salto, corta
    # el cuadro, y **la misma página retoma en el comando siguiente una vez
    # cambiado el mapa**. Reiniciarla, que es lo que hacíamos, deja a la
    # cinemática de apertura dando vueltas para siempre: espera, teletransporta
    # al mismo mapa, y vuelve a empezar.
    pendiente = None
    # Los cuadros se cuentan desde el arranque y a través de los mapas: el
    # `n` de cada vuelta arranca de uno en el mapa nuevo, pero el cuadro en que
    # el jugador aprieta A lo dice el emulador, que tiene un solo contador.
    # Comparar `n` a secas corría cada presión los cuadros que se hubieran
    # gastado en el mapa anterior, y la apertura gasta unos cuantos en el 4
    # antes de saltar al 1.
    base = 0
    apretar_a = set(apretar_a) if apretar_a else set()
    # `tocar` es {cuadro: (botones,)}, con los mismos cuadros que `apretar_a`:
    # son toques de un cuadro, o sea flancos. Ver `--tocar`.
    tocar = dict(tocar or {})
    # Y hasta el último toque, por lo mismo que `ultimo_a`: un mapa sin nada
    # que correr cortaría el lazo antes de que el jugador llegue a apretar.
    aprietes = list(apretar_a) + list(tocar)
    ultimo_a = max(aprietes) if aprietes else None
    anterior = None
    while True:
        game_map, passable, ocupadas, _puertas = mundo.mapa(map_id)
        # Dónde arranca cada evento del mapa, en celdas y por índice de la tabla
        # de la ROM. Se rearma al entrar, como `cargar_mapa` vuelve a copiar la
        # tabla desde el cartucho, y con eso se tiran las rutas que estuvieran
        # corriendo en el mapa que se deja.
        #
        # **Sólo si el mapa cambió.** Es el `map_changed` de
        # `Game_Player::PerformTeleport`: un salto al mismo mapa no recarga
        # nada. Rearmarlo igual borra lo que haya movido a los eventos —un
        # `ChangeEventLocation`, un `TradeEventLocations`— aunque el jugador
        # nunca haya salido del mapa, y eso se ve: ver la puerta del mapa 2 en
        # `pruebas/test_puerta_misma.py`.
        if map_id != anterior:
            estado.entrar_a_un_mapa({n: (ev.x, ev.y)
                                     for n, ev in enumerate(game_map.events)},
                                    mundo.paginas(map_id),
                                    {npc["evento"]: npc["velocidad"]
                                     for npc in collect_npcs(game_map)},
                                    {npc["evento"]: npc["pose"] // 3
                                     for npc in collect_npcs(game_map)})
        anterior = map_id
        if entrada is None:
            x, y = snes_convert.inicio_del_mapa(mundo.renderer, map_id,
                                                passable, game_map.width,
                                                game_map.height, ocupadas)
        else:
            x, y = entrada
            entrada = None
        # Antes de que corra el primer cuadro del mapa nadie pasó todavía por
        # `cuadro_de_eventos`, así que la celda del héroe se pone acá: es el
        # `sta tile_x` de `cargar_mapa`. Sin esto una página automática que
        # lea la posición del héroe en el primer cuadro leería la del mapa
        # anterior.
        estado.poner_heroe(x, y)
        # Con un presupuesto de cuadros el intérprete avanza sólo esos; sin él,
        # hasta que las páginas terminen. Lo primero hace falta para comparar
        # *durante* una espera: el emulador corrió N cuadros y la referencia
        # tiene que haber corrido los mismos.
        if cuadros is None:
            salto = eventos.correr_automaticos(
                mundo.paginas(map_id), estado,
                avanzar=lambda: cuadro_de_eventos(estado, passable, game_map,
                                                  (x, y), mundo.paginas(map_id),
                                                  congelada=True),
                mover_evento=paso_del_paralelo(estado, passable, game_map,
                                               (x, y), mundo.paginas(map_id)))
            # Sin presupuesto de cuadros la ruta forzada igual tiene que
            # caminarse entera: lo que se compara es dónde queda todo. Antes el
            # giro lo aplicaba el intérprete y esto no hacía falta; ahora la
            # ruta la camina el héroe, y saltearla dejaba al héroe mirando a
            # cámara mientras la ROM lo mostraba mirando arriba.
            for _ in range(10000):
                # El refresco que se mira es `refresco_frena` y no `refresco` a
                # secas: el que pide un intérprete paralelo no cuenta, porque
                # lo pide en cada cuadro y este lazo no terminaría nunca. Ver
                # `Estado.refresco_frena`, que cuenta lo que costó encontrarlo.
                if not estado.ruta and not estado.paso_cuadros \
                        and not estado.cuadros_moviendose \
                        and not estado.refresco_frena() \
                        and estado.asentado(mundo.paginas(map_id)):
                    break
                estado.refrescar()
                # Los paralelos no terminan nunca: siguen corriendo mientras el
                # mapa esté cargado, así que también durante el asentamiento.
                # Antes acá no corrían y el mapa se asentaba con los autos
                # quietos.
                estado.cuadro_de_paralelos(
                    mundo.paginas(map_id),
                    paso_del_paralelo(estado, passable, game_map, (x, y),
                                      mundo.paginas(map_id)))
                x, y, llego = paso_de_ruta(estado, passable, game_map, x, y,
                                           mundo.paginas(map_id))
                cuadro_de_eventos(estado, passable, game_map, (x, y),
                                  mundo.paginas(map_id))
                if llego:
                    # El último paso de la ruta pisó la celda: si hay un
                    # evento de contacto, corre. Acá el tiempo ya está
                    # colapsado, así que corre colapsado también, como el de
                    # la caminata con el pad.
                    map_id, x, y, frena = contacto_al_pisar(
                        mundo, estado, map_id, x, y, passable, game_map)
                    if frena:
                        break   # cambió de mapa o abrió un mensaje: se queda
        else:
            # Cuadro a cuadro, con el intérprete y la ruta forzada del héroe
            # avanzando juntos: en RM2k `ForceMoveRoute` es asincrónico, la
            # página sigue y quien camina es el personaje.
            salto = None
            interprete = eventos.Interprete(mundo.paginas(map_id), estado)
            if pendiente is not None:
                interprete.retomar(pendiente)
                pendiente = None
            for n in range(1, restantes + 1):
                # El fundido del teletransporte congela el juego entero, como
                # `fundido_tick` en la ROM y como RM2k, que mientras la
                # transición corre llama a `Player::Update(false)`. Acá eso es
                # no hacer nada: ni el intérprete, ni la ruta del héroe, ni los
                # eventos. El salto se aplica adentro, en el primer cuadro
                # negro, que es donde la consola carga el mapa.
                if estado.fundido is not None and \
                        estado.fundido + 1 >= eventos.FUNDIDO_TOTAL:
                    # El último cuadro del fundido, y **corre igual**: en la
                    # ROM `fundido_tick` devuelve cero y el lazo sigue con
                    # `eventos_tick` y `move_hero`. Acá se hacía `continue` y
                    # se le regalaba un cuadro a cada teletransporte, que es la
                    # misma trampa que ya se había arreglado del lado de la
                    # ida —"el cuadro sigue"—.
                    estado.fundido = None
                elif estado.fundido is not None:
                    estado.fundido += 1
                    if estado.fundido != eventos.FUNDIDO_RAMPA \
                            or estado.salto is None:
                        continue
                    if mundo.ids[estado.salto[0]] == map_id:
                        # Un teletransporte **al mismo mapa** no recarga nada:
                        # sólo mueve al héroe. Es el `map_changed = (GetMapId()
                        # != teleport_target.GetMapId())` de
                        # `Game_Player::PerformTeleport`. Recargarlo volvía a
                        # encolar los eventos automáticos, y con eso la
                        # cinemática de apertura —que salta dos veces adentro
                        # del mapa 1— se reiniciaba sola para siempre.
                        x, y = estado.salto[1], estado.salto[2]
                        estado.poner_heroe(x, y)
                        estado.salto = None
                        continue
                    # Al mapa nuevo se entra desde el lazo de afuera, y el
                    # fundido sigue contando del otro lado: le quedan los
                    # cuadros del negro y la rampa de vuelta.
                    salto = estado.salto
                    estado.salto = None
                    restantes -= n
                    base += n
                    pendiente = interprete.pendiente()
                    break
                estado.refrescar()
                # `apretar_a` son los cuadros en que el jugador aprieta A, y
                # sólo cuentan esos: RM2k cierra el mensaje con el flanco, no
                # con el botón sostenido. El emulador aprieta en los mismos
                # números y suelta al cuadro siguiente, para que cada uno sea
                # un flanco nuevo.
                apreta = base + n in apretar_a
                if apreta and estado.mensaje is None \
                        and not interprete.ocupado() and mirando is not None:
                    # La tecla de acción, que es la misma que cierra un
                    # mensaje. Con un mensaje abierto lo cierra y nada más: en
                    # RM2k el jugador no se actualiza mientras `Game_Message`
                    # esté activo, así que no puede hablarle a nadie. Y el mismo
                    # flanco no hace las dos cosas.
                    if interprete.probar_accion(x, y, mirando, estado):
                        apreta = False
                if interprete.cuadro(
                        apreto_a=apreta,
                        direccion=mirando,
                        tocados=tocar.get(base + n, ()),
                        mover_evento=paso_del_paralelo(
                            estado, passable, game_map, (x, y),
                            interprete.paginas)):
                    # El salto queda pedido y nada más: lo que arranca es el
                    # fundido, y el mapa cambia adentro. `estado.salto` lo
                    # guarda mientras tanto.
                    #
                    # Y el cuadro **sigue**: la ROM pide el fundido desde
                    # `eventos_tick` y después corre `move_hero`,
                    # `mover_eventos` y el resto del lazo igual. Cortarlo acá
                    # le regalaba un cuadro a cada teletransporte.
                    estado.fundido = 0
                x, y, llego = paso_de_ruta(estado, passable, game_map, x, y,
                                           interprete.paginas)
                if llego:
                    # Como `probar_contacto` en `advance_step`: la página va a
                    # la cola y corre en el cuadro siguiente, detrás de la que
                    # esté corriendo. Una puerta al final de una ruta la ROM
                    # sí la cruza y acá no se mira: ninguna ruta del juego
                    # termina sobre una, y ninguna prueba lo ejercita.
                    interprete.probar_celda(x, y, eventos.TRIGGER_TOCA_HEROE,
                                            estado)
                cuadro_de_eventos(estado, passable, game_map, (x, y),
                                  interprete.paginas,
                                  congelada=interprete.ocupado())
                if interprete.terminado and not estado.ruta \
                        and not estado.paso_cuadros \
                        and not estado.cuadros_moviendose \
                        and not estado.algo_corriendo() \
                        and not estado.refresco_frena() \
                        and not estado.paginas_caminando() \
                        and not estado.timer_activo \
                        and not estado.gotas \
                        and (ultimo_a is None or base + n >= ultimo_a) \
                        and restantes is not None:
                    # Y no se corta antes de la última vez que el jugador
                    # aprieta: si el mapa no tiene nada que correr, el lazo
                    # terminaba en el primer cuadro y la tecla no llegaba a
                    # existir.
                    #
                    # El cronómetro corriendo también lo sostiene, y no va en
                    # `algo_corriendo` con las rutas y los destellos: eso lo
                    # mira además el camino sin presupuesto, que corre hasta que
                    # todo se aquiete, y un cronómetro no se aquieta nunca —se
                    # comería las diez mil vueltas del tope—. Acá el presupuesto
                    # es el que manda, así que basta con no cortar antes.
                    #
                    # Y la lluvia, por lo mismo: se mueve sola en cada tick y
                    # no se aquieta nunca. Sin esto la referencia paraba con
                    # la escena quieta y la ROM seguía lloviendo: el final de
                    # la apertura salía con las gotas de 26 ticks antes.
                    break
        if salto is None:
            return map_id, x, y
        saltos -= 1
        if not saltos:
            # No se descarta el salto: se rompe. Es el `entrar_en_panico` de la
            # ROM, que hace lo mismo del otro lado —parar y avisar— y por la
            # misma razón: seguir andando en el mapa equivocado convierte un
            # error acá en un síntoma irreconocible media hora después.
            raise DemasiadosSaltos(
                "%d teletransportes encadenados sin devolver el control, y el "
                "próximo iba al mapa %s. O dos mapas se apuntan entre sí —que "
                "en RM2k cuelga el juego— o el presupuesto no se está "
                "reponiendo." % (SALTOS_MAX, salto[0]))
        map_id = mundo.ids[salto[0]]
        entrada = (salto[1], salto[2])


def contacto_al_pisar(mundo, estado, map_id, x, y, passable, game_map):
    """Corre el evento de contacto de la celda que el héroe acaba de pisar.

    Es `CheckEventTriggerHere` desde `Game_Player::UpdateMovement`: al terminar
    el paso se mira si en esa celda hay un evento de contacto, y si lo hay se
    ejecuta. Las puertas son un caso particular de esto —un teletransporte en
    una página de contacto— y siguen atendiéndose aparte, antes que esto, para
    no cambiar un camino que ya está probado.

    Acá el tiempo se colapsa, igual que en el resto de la caminata: la página
    corre hasta terminar o hasta que abra un mensaje. Devuelve dónde queda el
    héroe y si la caminata tiene que frenar, que es lo que pasa cuando el
    mensaje se abre: con `Game_Message` activo el pad deja de mover.
    """
    # Se construye con la lista vacía y después se le pasan las páginas del
    # mapa: `Interprete(paginas, ...)` encolaría además las automáticas, y ésas
    # ya corrieron al entrar.
    interprete = eventos.Interprete([], estado)
    interprete.paginas = mundo.paginas(map_id)
    if not interprete.probar_celda(x, y, eventos.TRIGGER_TOCA_HEROE, estado):
        return map_id, x, y, False
    for _ in range(10000):
        # El refresco va **arriba de todo**, antes del intérprete, que es donde
        # lo hace `Game_Map::Update`: `if (GetNeedRefresh()) Refresh();` y
        # recién después `UpdateMapEvents` y `game_player->Update()`. Acá
        # estaba después del intérprete, o sea que un switch prendido en este
        # cuadro le abría el paso al héroe en este mismo cuadro y en la ROM no.
        # Ver "El refresco va antes del intérprete" en el README.
        estado.refrescar()
        if interprete.cuadro(mover_evento=paso_del_paralelo(
                estado, passable, game_map, (x, y), interprete.paginas)):
            salto = estado.salto
            estado.salto = None
            if mundo.ids[salto[0]] == map_id:
                x, y = salto[1], salto[2]
            else:
                map_id, x, y = entrar_al_mapa(mundo, estado, mundo.ids[salto[0]],
                                              (salto[1], salto[2]))
                return map_id, x, y, True
            continue
        x, y, llego = paso_de_ruta(estado, passable, game_map, x, y,
                                   interprete.paginas)
        if llego:
            interprete.probar_celda(x, y, eventos.TRIGGER_TOCA_HEROE, estado)
        cuadro_de_eventos(estado, passable, game_map, (x, y),
                          interprete.paginas, congelada=interprete.ocupado())
        if estado.mensaje is not None:
            return map_id, x, y, True
        # `refresco_frena`: con un refresco pendiente el cuadro que viene
        # **sí** hace algo —rehacer la página activa de cada evento— y cortar
        # antes dejaba la instantánea vieja. Es lo que hacía que `puerta-emisor`
        # dibujara la puerta cerrada después de abrirla: la página que la abre
        # es un `ControlSwitches` y nada más, así que el intérprete terminaba en
        # el mismo cuadro y el lazo cortaba con el refresco sin hacer. Lo que no
        # cuenta es el que pide un intérprete paralelo, que lo pide siempre.
        if interprete.terminado and not estado.algo_corriendo() \
                and not estado.refresco_frena() \
                and not estado.paso_cuadros and not estado.cuadros_moviendose:
            break
    return map_id, x, y, False


def hero_position(mundo, estado, map_id, direction_name, inicio=None,
                  avance=None, cuadros=None, apretar_a=None, mirando=None,
                  margen=0, tocar=None):
    """En qué mapa y en qué celda termina el héroe, y hacia dónde mira.

    No se estima: se entra al mapa como entra la ROM —corriéndole los eventos—
    y después se camina con sus mismas reglas, de a un paso, mirando entre paso
    y paso si la celda tiene una puerta, que es cuando la consola la mira. Si la
    tiene, se cambia de mapa —y al mapa nuevo también le corren sus eventos— y
    se sigue caminando desde donde deja, con la cruceta todavía apretada.

    Devuelve (mapa, x, y, dirección) con x e y en pixeles.
    """
    map_id, x, y = entrar_al_mapa(mundo, estado, map_id, inicio, cuadros,
                                  apretar_a, mirando, tocar)
    # Los encuentros al azar del mapa donde se camina. La caminata **se corta**
    # cuando sale uno: del otro lado la pelea toma la pantalla, así que seguir
    # caminando acá sería comparar dos escenas distintas.
    encuentros = mundo.encuentros(map_id)

    def correr(n, en_x, en_y):
        """`n` ticks del mundo con el héroe quieto en esa celda.

        Es el margen: los cuadros que el emulador corre de más sobre lo que
        dura la caminata. Existen porque la ROM llega uno o dos cuadros después
        de `pasos x 8` —el pad se lee una vez por cuadro y el primero se
        pierde—, y hasta ahora eran holgura: nadie los vivía de este lado. Con
        eventos que se mueven solos la holgura dejó de ser gratis, así que se
        viven acá y se cuentan en el plan.
        """
        game_map, passable, _ocupadas, _puertas = mundo.mapa(map_id)
        for _ in range(n):
            estado.refrescar()
            estado.cuadro_de_paralelos(
                mundo.paginas(map_id),
                paso_del_paralelo(estado, passable, game_map, (en_x, en_y),
                                  mundo.paginas(map_id)))
            cuadro_de_eventos(estado, passable, game_map, (en_x, en_y),
                              mundo.paginas(map_id))

    step = WALK[direction_name]
    direction = DIRECTIONS.get(direction_name, DIRECTIONS["down"])
    if estado.mensaje is not None:
        # Con un mensaje en pantalla el pad no mueve al héroe, así que la
        # caminata es como no haber apretado nada. Es el guard de
        # `Game_Player::UpdateNextMovementAction`: vuelve sin mirar el input si
        # `Game_Message::IsMessageActive()`. La ruta forzada es otra cosa y sí
        # sigue —la mueve `entrar_al_mapa`, más arriba— porque allá
        # `UpdateMoveRoute` corre antes del guard.
        step = None
    if step is None:
        # Sin caminata, hacia dónde mira lo puede haber dicho una ruta forzada;
        # si no, mira a cámara, que es como RM2k deja al héroe.
        quieto = estado.mirando if estado.mirando is not None else DIRECTIONS["down"]
        # Los pixeles que le faltan al paso en curso, descontados de la celda de
        # destino. La cuenta es la misma que la de un evento caminando, y por eso
        # vive en `eventos.pixeles_del_paso` y no acá.
        px, py = eventos.pixeles_del_paso(x, y, estado.ruta_heroe)
        correr(margen, x, y)
        return map_id, px, py, quieto, 0
    desde = (x, y)

    # Cuántas celdas camina. Hasta ahora este número se calculaba y se tiraba;
    # es el que dice cuántos cuadros tarda la ROM en llegar, porque el paso son
    # dieciséis pixeles a WALK_SPEED = 2 por cuadro, o sea ocho cuadros por
    # celda. Antes la prueba pedía "45 segundos, seguro alcanza"; con esto pide
    # un número que sale de la misma referencia contra la que se compara.
    pasos = 0
    # Los ticks de caminata ya vividos, para que `--avance` corte donde pide.
    vividos = 0

    # El tope es por si dos puertas se apuntan entre sí: la ROM se quedaría
    # rebotando y la referencia también, y colgar una prueba no ayuda a nadie.
    for _ in range(10000):
        game_map, passable, _ocupadas, puertas = mundo.mapa(map_id)
        # **La ruta forzada manda sobre el pad**, y por eso va antes que todo lo
        # demás: `move_hero` mira `ruta_i / ruta_n` y se vuelve sin tocar el
        # pad si hay una ruta puesta, igual que `Game_Player::
        # UpdateNextMovementAction` vuelve sin mirar el input mientras
        # `IsMoveRouteOverwritten()`. Acá la caminata avanzaba de a una celda
        # entera sin mirar la ruta, así que el pad y la ruta movían al héroe a
        # la vez y en direcciones distintas.
        #
        # Mientras la ruta esté puesta se vive **de a un cuadro**, que es lo
        # único que puede intercalarse con ella: el paso de la ruta, los
        # paralelos y los eventos que caminan solos. Cuando se acaba, la
        # caminata sigue donde estaba.
        #
        # Lo que lo destapó es el volante de la persecución en auto: su página
        # paralela le vuelve a poner la ruta al héroe **en todos los cuadros**,
        # así que el pad no lo mueve nunca. Medido con
        # `TECLA_SIN_ESPERA=1 just snes-heroe 52`, que es lo que acepta esa
        # página: sin esto, apretando la izquierda da **55,42%** de pixeles
        # distintos; con esto, **0,59%**.
        #
        # **Hoy esto no lo alcanza ningún caso de la tanda, y hay que decirlo.**
        # Con el volante todavía sin aceptar, ninguna página compilada le pone
        # una ruta al héroe mientras el jugador camina: la de una automática la
        # consume `entrar_al_mapa` antes de la caminata, y la de un evento de
        # contacto la consume `contacto_al_pisar` —su corte mira
        # `algo_corriendo()`, que cuenta las rutas pendientes—. Queda como la
        # guarda de la paleta vacía de `tenir_paleta`: código inalcanzable con
        # lo que el conversor sabe emitir hoy, no un camino a medias. El día
        # que el `KeyInputProc` sin espera entre, es lo primero que se ejercita.
        if estado.ruta or estado.paso_cuadros:
            estado.refrescar()
            estado.cuadro_de_paralelos(
                mundo.paginas(map_id),
                paso_del_paralelo(estado, passable, game_map, (x, y),
                                  mundo.paginas(map_id)))
            x, y, llego = paso_de_ruta(estado, passable, game_map, x, y,
                                       mundo.paginas(map_id))
            cuadro_de_eventos(estado, passable, game_map, (x, y),
                              mundo.paginas(map_id))
            if llego:
                map_id, x, y, frena = contacto_al_pisar(
                    mundo, estado, map_id, x, y, passable, game_map)
                if frena:
                    break
            continue
        # Las celdas ocupadas sólo sirven para elegir dónde arranca. No se le
        # pasan a la caminata: en RM2k un NPC bloquea el paso, pero la ROM
        # todavía no lo mira, y modelar acá algo que la consola no hace es
        # inventar una diferencia.
        if not puede_pasar(passable, game_map.width, game_map.height,
                           x, y, step[0], step[1],
                           pasa_evento=lambda cx, cy:
                           eventos.pasabilidad_de_evento(
                               mundo.paginas(map_id), estado, (cx, cy))):
            break
        # Y un evento de su capa parado en la celda de destino lo frena igual
        # que una pared: `WouldCollide`, con el héroe en la capa del medio. Es
        # lo que hace que un droide no se atraviese, y que no se pueda pisar
        # un evento de contacto de la capa del héroe —978 de las 983 páginas
        # de contacto del juego están en la de abajo justamente por esto—.
        if eventos.bloqueada(mundo.paginas(map_id), estado,
                             (x + step[0], y + step[1]), eventos.LAYER_MISMA):
            break
        x, y = x + step[0], y + step[1]
        pasos += 1
        # Los ocho cuadros que cuesta la celda **se viven**, no se cuentan al
        # final. El héroe sí se mueve de un saque —dónde queda es lo único que
        # se compara de él— pero lo que corre solo no puede colapsarse: los
        # intérpretes paralelos y las rutas forzadas de los eventos avanzan un
        # cuadro cada uno, con el héroe ya en la celda de destino, que es el
        # `GetX()`/`GetY()` de RM2k mientras dura el paso.
        #
        # Sin esto una caminata de 37 celdas le regalaba 296 cuadros a los
        # autos de Lashe City, y era el último rojo de la tanda. El intérprete
        # de primer plano **no** corre acá: mientras el jugador camina no hay
        # ninguna página en curso, y la que arranque la pone `contacto_al_pisar`
        # unas líneas más abajo.
        #
        # Con `--avance` se viven sólo los que van hasta el pixel que se pide:
        # el cuadro que se compara es uno de **adentro** de la caminata, así
        # que los eventos tienen que estar donde estaban ahí y no donde
        # terminan. La caminata sigue igual, para saber cuántas celdas son.
        vivir = cuadros_por_celda(estado)
        if avance is not None:
            vivir = max(0, min(vivir, cuadros_de_avance(estado, avance)
                               - vividos))
        vividos += vivir
        correr(vivir, x, y)
        # El paso cuenta para el encuentro **antes** que la puerta: allá el
        # acumulado sube al empezar el paso —`IncSteps`— y la pelea recién
        # arranca en el cuadro siguiente, así que una puerta en la celda de
        # llegada llega primero y su `MoveTo` borra lo que quedó pendiente.
        encuentros.paso()
        puerta = puertas.get((x, y))
        if puerta is None:
            # Sin puerta, puede haber un evento de contacto.
            map_id, nx, ny, frena = contacto_al_pisar(
                mundo, estado, map_id, x, y, passable, game_map)
            if (nx, ny) != (x, y) or frena:
                x, y = nx, ny
                encuentros.reiniciar()   # moverlo de celda es un `MoveTo`
                if frena:
                    break
            elif encuentros.pendiente:
                # Y el encuentro se cobra con el héroe parado y sin página
                # corriendo, que es el orden de `UpdateNextMovementAction`: el
                # contacto de arriba manda, porque allá una página en el frente
                # devuelve antes.
                tropa = encuentros.elegir(x, y)
                if tropa is not None:
                    estado.encuentro = (pasos, tropa)
                    break
            continue
        if avance is not None:
            # Un avance a mitad de camino no cruza puertas: del otro lado el
            # mapa es otro y la cuenta de pixeles desde el arranque no
            # significa nada. Se corta acá en vez de dibujar cualquier cosa.
            sys.exit("el avance pedido cruza una puerta en el paso %d; este "
                     "caso no sirve para comparar a mitad de camino" % pasos)
        # La puerta también funde: es un teletransporte y le toca la misma
        # transición. Acá el tiempo está colapsado y el fundido no se ve —la
        # caminata se compara cuando ya terminó todo— pero sus cuadros existen
        # y el plan los cuenta.
        estado.fundidos += 1
        if puerta["mapa"] == map_id:
            # Una puerta al **mismo** mapa no recarga nada: sólo mueve al héroe,
            # igual que un `Teleport` al mismo mapa. Los dos cuartos del mapa 2
            # que parecen dos mapas se cruzan por puertas así, y recargar les
            # devolvía a los eventos su posición original.
            x, y = puerta["destino_x"], puerta["destino_y"]
            continue
        map_id, x, y = entrar_al_mapa(mundo, estado, puerta["mapa"],
                                      (puerta["destino_x"], puerta["destino_y"]))
    if avance is not None:
        if avance > pasos * TILE:
            sys.exit("se pidió un avance de %d px pero la caminata son %d "
                     "celdas = %d px" % (avance, pasos, pasos * TILE))
        return (map_id,
                desde[0] * TILE + step[0] * avance,
                desde[1] * TILE + step[1] * avance,
                direction, pasos)
    correr(margen, x, y)
    return map_id, x * TILE, y * TILE, direction, pasos


def destellar_pantalla(view, color, nivel):
    """El destello de pantalla, color por color, con la cuenta de
    `eventos.destellar_pantalla` sobre los 15 bits. Es el hermano de
    `tenir_imagen`, y no es `destellar_imagen`, que es el destello de **un
    personaje** y tiene otra cuenta."""
    pixels = view.load()
    memo = {}
    for y in range(view.height):
        for x in range(view.width):
            pixel = pixels[x, y]
            nuevo = memo.get(pixel)
            if nuevo is None:
                r, g, b = pixel[:3]
                palabra = eventos.destellar_pantalla(
                    (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10), color, nivel)
                nuevo = ((palabra & 0x1F) << 3,
                         ((palabra >> 5) & 0x1F) << 3,
                         ((palabra >> 10) & 0x1F) << 3) + tuple(pixel[3:])
                memo[pixel] = nuevo
            pixels[x, y] = nuevo
    return view


def tenir_imagen(view, tinte):
    """El tinte del evento, aplicado color por color.

    La consola no tiñe la pantalla sino CGRAM, y como cada pixel del fondo, de
    la capa de encima y de los sprites sale de una entrada de CGRAM, teñir cada
    color de la imagen ya compuesta da exactamente lo mismo.

    La cuenta es la de `eventos.tenir`, con enteros y sobre los 15 bits. Hacerla
    sobre los 24 del PNG redondearía distinto y la comparación fallaría por el
    redondeo en vez de por la consola.
    """
    pixels = view.load()
    memo = {}
    for y in range(view.height):
        for x in range(view.width):
            color = pixels[x, y]
            nuevo = memo.get(color)
            if nuevo is None:
                r, g, b = color[:3]
                palabra = eventos.tenir(
                    (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10), tinte)
                nuevo = ((palabra & 0x1F) << 3,
                         ((palabra >> 5) & 0x1F) << 3,
                         ((palabra >> 10) & 0x1F) << 3) + color[3:]
                memo[color] = nuevo
            pixels[x, y] = nuevo
    return view


def oscurecer_imagen(view, brillo):
    """El brillo maestro de INIDISP, aplicado color por color.

    Va sobre **todo** —el mapa, los sprites, la ventana de mensaje y el
    cronómetro—, porque en la consola es lo último que toca el PPU antes de
    sacar el pixel, después de mezclar todo. Por eso no es un tinte: el tinte
    transforma CGRAM y la ventana, que tiene su propia paleta, no se entera.

    La cuenta es la de `eventos.oscurecer`, sobre los 15 bits.
    """
    if brillo >= eventos.BRILLO_MAX:
        return view
    pixels = view.load()
    memo = {}
    for y in range(view.height):
        for x in range(view.width):
            color = pixels[x, y]
            nuevo = memo.get(color)
            if nuevo is None:
                r, g, b = color[:3]
                palabra = eventos.oscurecer(
                    (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10), brillo)
                nuevo = ((palabra & 0x1F) << 3,
                         ((palabra >> 5) & 0x1F) << 3,
                         ((palabra >> 10) & 0x1F) << 3) + color[3:]
                memo[color] = nuevo
            pixels[x, y] = nuevo
    return view


def camera_for(x, y, map_w, map_h, pan=(0, 0)):
    """Dónde mira la cámara: centrada en el héroe, corrida por el pan y pegada
    a los bordes.

    El pan viene en dieciseisavos de pixel y se baja a pixeles enteros con
    división **al piso**, que es lo que hace `Spriteset_Map` dividiendo
    `GetDisplayX()` por 16. Va adentro del acote y no después, como la
    sacudida: RM2k corre la posición del mapa, y el borde la frena.
    """
    cam_x = max(0, min(map_w * 8 - SCREEN_W,
                       x + 8 - SCREEN_W // 2 + (pan[0] >> 4)))
    cam_y = max(0, min(map_h * 8 - SCREEN_H,
                       y + 8 - SCREEN_H // 2 + (pan[1] >> 4)))
    return cam_x, cam_y


def pose_image(charset, index, pose, ajena=None, poses=None):
    """Una pose, con los colores ya fusionados a los 15 que entran en un sprite.

    La fusión es la misma que hace el conversor —mismo criterio, mismos datos—
    así que si difiere algo no es esto.

    `ajena` es la paleta que le prestaron al personaje cuando el mapa se quedó
    sin ninguna libre. Sus colores no están ahí, así que cada uno se dibuja con
    el más cercano de los que hay: es lo que hace `build_characters`, con la
    misma cuenta de distancia, y sin esto la referencia dibujaría los colores
    de verdad contra una consola que dibuja los aproximados.

    `poses` son las que el evento puede mostrar en este mapa, que es sobre lo
    que el conversor eligió sus quince colores: ver `Mundo.poses`. Con `None`
    se cuentan las doce, que es lo que corresponde a quien camina.
    """
    _paleta, _lookup, mapping = snes_convert.paleta_del_personaje(
        charset, index, poses=poses)

    ox, oy = snes_convert.pose_origin(index, pose)
    out = Image.new("RGBA", (snes_convert.SPRITE_W, snes_convert.SPRITE_H),
                    (0, 0, 0, 0))
    for y in range(snes_convert.SPRITE_H):
        for x in range(snes_convert.SPRITE_W):
            r, g, b, a = charset.getpixel((ox + x, oy + y))
            if not a:
                continue
            # Se guarda el color de 15 bits corrido a 8, que es la misma escala
            # en la que después se compara.
            cr, cg, cb = mapping[(r >> 3, g >> 3, b >> 3)]
            if ajena is not None and (cr, cg, cb) not in ajena:
                cr, cg, cb = min(ajena, key=lambda p: pixeles.luma_distance(
                    p, (cr, cg, cb)))
            out.putpixel((x, y), (cr << 3, cg << 3, cb << 3, 255))
    return out


def destellar_imagen(imagen, color, nivel):
    """La pose con el destello aplicado, **en el espacio de cinco bits**.

    Los pixeles vienen del PNG en ocho bits, así que se bajan a cinco, se
    mezclan y se vuelven a subir: es lo que hace la consola, que sólo tiene esos
    cinco. Mezclar en ocho y recortar después da otro número, y la comparación
    —que mira quince bits— lo vería.

    Se resuelve por color y no por pixel: una pose tiene quince colores como
    mucho.
    """
    if nivel <= 0:
        return imagen
    salida = imagen.copy()
    pixels = salida.load()
    mapa = {}
    for y in range(salida.height):
        for x in range(salida.width):
            r, g, b, a = pixels[x, y]
            if not a:
                continue
            clave = (r, g, b)
            if clave not in mapa:
                palabra = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
                nueva = eventos.destellar(palabra, color, nivel)
                mapa[clave] = ((nueva & 0x1F) << 3,
                               ((nueva >> 5) & 0x1F) << 3,
                               ((nueva >> 10) & 0x1F) << 3)
            pixels[x, y] = mapa[clave] + (a,)
    return salida


def glifos_del_timer(estado):
    """Dónde va cada glifo del cronómetro, en objetos de 8x8.

    Cinco glifos de 8x16, o sea diez objetos, y los dos puntos se saltean
    cuando les toca parpadear. Se devuelven las esquinas porque hacen falta dos
    veces: para contar el presupuesto de sprites de la línea —los dígitos lo
    gastan como cualquier otro objeto— y para pegarlos al final.
    """
    if not estado.timer_visible:
        return []
    texto = estado.timer_texto()
    fuera = []
    for i, letra in enumerate(texto):
        if letra == " ":
            continue            # los dos puntos, apagados este cuadro
        glifo = (snes_convert.TIMER_GLIFOS - 1 if letra == ":"
                 else int(letra))
        for mitad in (0, 1):
            fuera.append((glifo, mitad,
                          snes_convert.TIMER_X + i * snes_convert.TIMER_GLIFO_W,
                          snes_convert.TIMER_Y + mitad * 8))
    return fuera


def gotas_en_oam(gotas, usados, pan_x, pan_y):
    """Los objetos de 8x8 que la ROM pone por la lluvia: (x, y, mitad, tono).

    Van en el orden de las gotas, arriba y abajo. La gota está en la
    superficie de 256x256 que va pegada al mapa, así que en pantalla es su
    lugar menos el scroll (`pan_x` con la sacudida, `pan_y`), en ocho bits: la
    X queda siempre adentro, y de la Y se descarta lo que cae entre 224 y 247
    —de 248 en adelante el PPU lo dibuja asomando por arriba—. Ver
    `lluvia_oam`. Y se corta lo que ya no entra en los 128 de OAM después de
    los `usados` por los personajes y el cronómetro.
    """
    objetos = []
    libres = 128 - usados
    for x, y, t in gotas:
        if t <= 0:
            continue
        ox = (x - pan_x) & 0xFF
        for mitad in (0, 1):
            oy = (y - pan_y + 8 * mitad) & 0xFF
            if 224 <= oy < 248:
                continue
            if len(objetos) >= libres:
                return objetos
            objetos.append((ox, oy if oy < 224 else oy - 256, mitad,
                            eventos.lluvia_tono(t)))
    return objetos


def draw_actors(view, sprites, encima=None, timer=(), lluvia=(),
                ventana=False, cartel=None, animacion_y=None):
    """Pinta los sprites y avisa en qué líneas la consola no va a poder.

    No se intenta reproducir *cuáles* se pierden. La consola arma la lista de
    los que caen en cada línea recorriendo OAM y después busca sus tiles en un
    orden que depende del modelo y que acá sería una conjetura; probar dos
    reglas plausibles dio peor que no modelar nada. Lo que sí se puede afirmar
    con certeza es en qué líneas el presupuesto no alcanza, y ésas se declaran
    para excluirlas de la comparación en vez de fingir que se saben.

    Devuelve la lista de líneas donde el límite se pasa.
    """
    excedidas = []
    for y in range(SCREEN_H):
        presentes = sum(1 for _img, _sx, sy, _a in sprites
                        if sy <= y < sy + snes_convert.OBJ_H)
        # Los glifos del cronómetro son objetos como cualquier otro y gastan el
        # mismo presupuesto: uno de 8x8 es un objeto y un tile. Contarlos
        # importa poco —son cinco por línea de las treinta y cuatro— pero no
        # contarlos sería una diferencia que sólo aparecería con la pantalla
        # llena, que es donde nadie mira.
        chicos = sum(1 for _g, _m, _sx, sy in timer if sy <= y < sy + 8)
        # Y las gotas de lluvia, que son objetos de 8x8 como los dígitos.
        chicos += sum(1 for _x, gy, _m, _t in lluvia if gy <= y < gy + 8)
        # Y el cartel, que son objetos de 32x32 como los personajes. Se cuenta
        # y **no se pinta acá**: va después del tinte y del destello, que es
        # donde lo pone RM2k —`Priority_PictureOld` es 120 contra los 90 de
        # `Priority_Screen`—. Ocupa sus 32 líneas enteras aunque la imagen mida
        # 29: las líneas de relleno son transparentes pero el objeto está, y el
        # presupuesto de la consola cuenta objetos, no pixeles.
        if cartel is not None:
            cy, cuantos = cartel
            if cy <= y < cy + snes_convert.OBJ_H:
                presentes += cuantos
        # Y la animación de batalla: dos objetos de 32x32 en cada una de sus
        # 64 líneas, porque la caja es de dos por dos. Se cuenta y **no se
        # pinta acá**: va después del tinte y del destello, que es donde la
        # pone RM2k.
        if animacion_y is not None:
            if animacion_y <= y < animacion_y + animacion_mod.CAJA:
                presentes += animacion_mod.CAJA // snes_convert.OBJ_W
        if (presentes * OBJ_TILES + chicos > OBJ_TILES_PER_LINE
                or presentes + chicos > OBJ_PER_LINE):
            excedidas.append(y)

    # Se pintan de atrás hacia adelante, o sea al revés del orden de OAM.
    for image, sx, sy, arriba in reversed(sprites):
        if arriba:
            continue                # esos van después de la capa de encima
        view.alpha_composite(image, (sx, sy))

    if encima is not None:
        view.alpha_composite(encima, (0, 0))

    for image, sx, sy, arriba in reversed(sprites):
        if arriba:
            view.alpha_composite(image, (sx, sy))

    # La lluvia: prioridad 2, así que va por encima de las dos capas, pero es
    # lo último de OAM y en la consola el objeto de índice más bajo gana, así
    # que **cualquier pixel de personaje la tapa**, aunque el personaje mismo
    # quede detrás de la capa de encima. Y la ventana de mensaje la tapa con
    # la máscara de objetos, en sus líneas.
    if lluvia:
        tapado = set()
        for image, sx, sy, _arriba in sprites:
            alfa = image.getchannel("A").load()
            for py in range(image.height):
                for px in range(image.width):
                    if alfa[px, py]:
                        tapado.add((sx + px, sy + py))
        pix = view.load()
        tope = SCREEN_H - (snes_convert.VENTANA_FILAS_INC * 8 if ventana
                           else 0)
        # Al revés: entre dos gotas encimadas gana la de índice más bajo de
        # OAM, que es la primera de la lista. Pintándolas en orden ganaba la
        # última, y la apertura no lo cobró nunca porque ahí no se enciman
        # en ningún cuadro que se compare; lo encontró `pan-lluvia`.
        for x, y, mitad, tono in reversed(lluvia):
            color = tuple(v << 3 for v in eventos.LLUVIA_COLORES[tono]) + (255,)
            for px, py in eventos.lluvia_pixeles(x, y - 8 * mitad)[
                    8 * mitad:8 * mitad + 8]:
                if (0 <= px < SCREEN_W and 0 <= py < tope
                        and (px, py) not in tapado):
                    pix[px, py] = color
    return excedidas


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--walk", nargs="+", default=["none"],
                        choices=sorted(WALK),
                        help="una o varias direcciones. Con varias, -o y --saltar\n"
                             "tienen que llevar un {} donde va la dirección: se\n"
                             "convierte el mapa una sola vez para todas")
    parser.add_argument("--grupo", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="el grupo con el que arranca, por ids de actor. El gráfico "
                             "del héroe es el del primero, que es como lo decide "
                             "RM2k. Por defecto, el de la base: este juego "
                             "arranca con el actor 10, DummyHero, cuyo sprite es "
                             "una celda vacía a propósito")
    parser.add_argument("--charset", default=None,
                        help="forzar el CharSet del héroe; por defecto sale\n"
                             "del primero del grupo, que es como lo decide RM2k")
    parser.add_argument("--heroe-encima", action="store_true",
                        help="el héroe en prioridad 2, por encima de "
                             "la capa que debería taparlo. El otro "
                             "lado del mismo flag de snes_convert.py")
    parser.add_argument("--charset-index", type=int, default=None)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--saltar", help="archivo donde anotar las líneas que "
                        "pasan el límite de sprites")
    parser.add_argument("--avance", type=int, nargs="+", default=None,
                        metavar="PX",
                        help="dibujar al héroe a mitad de camino, con este "
                             "avance en pixeles desde donde arrancó la "
                             "caminata, y en la pose de caminata que le toca. "
                             "Sin esto se dibuja donde termina, que es la "
                             "única pose que las pruebas miraban hasta ahora. "
                             "Con avances el {} de -o lleva el avance en vez "
                             "de la dirección, y si se piden varios el mapa se "
                             "convierte una sola vez")
    parser.add_argument("--cuadros", type=int, nargs="+", default=None,
                        metavar="N",
                        help="cuántos cuadros del intérprete simular. Hace "
                             "falta para comparar durante una espera: el "
                             "emulador corrió N cuadros y esto tiene que haber "
                             "corrido los mismos. Sin esto, las páginas corren "
                             "hasta terminar")
    parser.add_argument("--mensaje-de-prueba", nargs="*", metavar="LINEA",
                        help="agrega la página automática que abre una ventana "
                             "de mensaje con estas líneas. El otro lado del "
                             "mismo flag de snes_convert.py. Implica "
                             "--con-ventana")
    parser.add_argument("--relleno-de-mensajes", type=int, default=0,
                        help="bytes muertos al principio del bloque de textos, para\n"
                             "que los desplazamientos pasen los 32 KB que mide\n"
                             "la ventana de un banco de LoROM. Es lo único que\n"
                             "reproduce el defecto de `msg_empezar` sin armar un\n"
                             "cartucho de diez mapas hablados. El otro lado del\n"
                             "mismo flag de la otra herramienta")
    parser.add_argument("--con-ventana", action="store_true",
                        help="la ROM lleva la ventana de mensaje, o sea que "
                             "los ShowMessage del juego compilan y el reparto "
                             "de CGRAM le reserva una paleta. El otro lado del "
                             "mismo flag de snes_convert.py")
    parser.add_argument("--apretar-a", type=int, nargs="+", default=None,
                        metavar="N",
                        help="en qué cuadros el jugador aprieta A, que es lo "
                             "que cierra un mensaje. Se cuentan desde el "
                             "arranque y a través de los teletransportes. El "
                             "otro lado del mismo flag de snes_correr.py")
    parser.add_argument("--tocar", nargs="+", default=None,
                        metavar="BOTON:CUADRO",
                        help="toques anotados de cualquier botón —`up`, "
                             "`down`, `left`, `right` y `b`—, con los cuadros "
                             "contados como los de --apretar-a. El otro lado "
                             "del mismo flag de snes_correr.py. Existe para "
                             "la forma de KeyInputProc que espera la cruceta: "
                             "es la única que pide un **flanco** de dirección "
                             "a mitad de una escena, y sostener con --walk no "
                             "lo produce")
    parser.add_argument("--batalla-de-prueba", type=int, default=0,
                        metavar="TROPA",
                        help="una pelea contra esta tropa al final de la "
                             "página de prueba. De este lado no cuesta ningún "
                             "tick y no dibuja nada: ver OP_BATTLE en "
                             "tools/eventos.py")
    parser.add_argument("--guardar-de-prueba", action="store_true",
                        help="la página de prueba guarda la partida en la "
                             "SRAM. El otro lado del mismo flag de "
                             "snes_convert.py: acá no guarda nada —la "
                             "referencia es un modelo— pero el opcode ocupa su "
                             "byte y los dos intérpretes tienen que leer el "
                             "mismo stream")
    parser.add_argument("--timer-de-prueba", nargs=2, type=int, default=None,
                        metavar=("SEGUNDOS", "VISIBLE"),
                        help="arranca el cronómetro desde la página de prueba. "
                             "Existe por lo mismo que el resto de esa página: "
                             "las seis del juego que lo prenden están cortadas "
                             "por otra cosa, así que sin esto no habría con qué "
                             "comparar. Implica --con-timer")
    parser.add_argument("--con-timer", action="store_true",
                        help="la ROM lleva los dígitos del cronómetro: once "
                             "glifos de la imagen de System al final del banco "
                             "de sprites, y una paleta")
    parser.add_argument("--switch", nargs="+", type=int, default=None,
                        metavar="N",
                        help="prende estos switches desde la página de prueba, "
                             "que es la forma de poner al mundo en un estado al "
                             "que el juego llega más tarde")
    parser.add_argument("--vars-de-prueba", nargs="+", type=int, default=None,
                        help="el otro lado del mismo flag de snes_convert.py")
    parser.add_argument("--rama-var-de-prueba", nargs=5, type=int,
                        default=None,
                        help="el otro lado del mismo flag de snes_convert.py")
    parser.add_argument("--animacion-de-prueba", nargs=3, type=int,
                        default=None, help="el mismo flag del conversor")
    parser.add_argument("--lluvia-de-prueba", type=int, default=None,
                        help="FUERZA: el mismo flag del conversor")
    parser.add_argument("--acceso-de-prueba", nargs="+", type=int,
                        default=None,
                        help="CUAL PERMITIDO, repetible de a dos: el mismo "
                             "flag del conversor")
    parser.add_argument("--items-de-prueba", nargs="+", type=int, default=None,
                        help="ITEM CUANTO, repetible de a dos: el mismo flag "
                             "del conversor")
    parser.add_argument("--rama-de-prueba", nargs=3, type=int, default=None,
                        metavar=("SWITCH", "ADENTRO", "DESPUES"),
                        help="la misma rama que arma el conversor; ver allá")
    parser.add_argument("--destello-de-prueba", nargs=5, type=int, default=None,
                        metavar=("R", "G", "B", "POTENCIA", "CUADROS"),
                        help="destella la pantalla desde la página de prueba: "
                             "es FlashScreen, y no es lo mismo que "
                             "--flash-de-prueba, que destella a un personaje")
    parser.add_argument("--flash-de-prueba", nargs=6, type=int, default=None,
                        metavar=("BLANCO", "R", "G", "B", "POTENCIA", "CUADROS"),
                        help="hace destellar a alguien desde la página de "
                             "prueba: el blanco es 0 para el héroe o el índice "
                             "del evento más uno, el color va de 0 a 31 y los "
                             "cuadros son cuántos dura")
    parser.add_argument("--tecla-de-prueba", nargs=5, type=int,
                        default=None,
                        metavar="N",
                        help="el mismo de snes_convert.py: agrega un\n"
                             "KeyInputProc con los cinco parámetros de\n"
                             "RM2k: variable, esperar, las cuatro\n"
                             "direcciones, la tecla de acción y\n"
                             "cancelar. Ninguna página del juego que\n"
                             "hoy compile lo usa, así que sin esto el\n"
                             "camino no lo corre nada")
    parser.add_argument("--sprite-de-prueba", nargs=3, default=None,
                        metavar=("ACTOR", "CHARSET", "INDICE"),
                        help="el mismo de snes_convert.py: agrega a la\n"
                             "ChangeSpriteAssociation: le cambia el\n"
                             "CharSet a ese actor **después de la\n"
                             "espera**, y si es el que lidera, el\n"
                             "héroe pasa a dibujarse con él. El\n"
                             "gráfico tiene que ir además en\n"
                             "--grafico-de-prueba, que es lo que le\n"
                             "pone las poses en el banco de sprites\n"
                             "del mapa. Las 212 apariciones del\n"
                             "comando en el juego están en los cuatro\n"
                             "mapas de la persecución en auto")
    parser.add_argument("--grafico-de-prueba", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDICE"),
                        help="el mismo de snes_convert.py: registra un gráfico\n"
                             "para que la orden 34 de --ruta-de-evento pueda\n"
                             "cambiarse a él")
    parser.add_argument("--ruta-de-evento", nargs="+", type=int, default=None,
                        metavar="N",
                        help="el primer número es sobre quién —el índice del "
                             "evento en la tabla del mapa más uno— y los que "
                             "siguen son las órdenes de la ruta. Detrás va un "
                             "ProceedWithMovement, así que lo que venga "
                             "después de la página no corre hasta que el "
                             "evento termine de caminar")
    parser.add_argument("--pan-de-prueba", nargs="+", type=int,
                        default=None, metavar="N",
                        help="OPERACION DIRECCION DISTANCIA VELOCIDAD ESPERAR:\n"
                             "agrega a la página de prueba un PanScreen. La\n"
                             "operación es 2 para correr la cámara y 3 para\n"
                             "devolverla; ninguna página del juego que hoy\n"
                             "compile corre la cámara. Se puede repetir de a\n"
                             "cinco para encadenar varios")
    parser.add_argument("--fundir-bgm", type=int, default=0,
                        metavar="MS",
                        help="agrega a la página de prueba un FadeOutBGM de esos\n"
                             "milisegundos. Ninguna página del juego que hoy\n"
                             "compile apaga la música, así que sin esto el\n"
                             "camino no lo corre nada")
    parser.add_argument("--lugar-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="BLANCO X Y [ESPERA]: el otro lado del mismo flag "
                             "del conversor")
    parser.add_argument("--rama-item-de-prueba", nargs=5, type=int,
                        default=None,
                        metavar=("ITEM", "R", "G", "B", "SAT"),
                        help="ITEM R G B SAT: el otro lado del mismo flag del "
                             "conversor")
    parser.add_argument("--rama-actor-de-prueba", nargs=7, type=int,
                        default=None,
                        metavar=("SUB", "ACTOR", "DATO", "R", "G", "B", "SAT"),
                        help="SUB ACTOR DATO R G B SAT: el otro lado del mismo "
                             "flag del conversor")
    parser.add_argument("--parar-de-prueba", type=int, default=None,
                        metavar="CUADROS",
                        help="HaltAllMovement después de esos cuadros: el otro "
                             "lado del mismo flag del conversor")
    parser.add_argument("--sacudida-de-prueba", nargs="+", type=int,
                        default=None, metavar="N",
                        help="FUERZA VELOCIDAD DECIMAS [ESPERA]: el otro lado "
                             "del mismo flag del conversor")
    parser.add_argument("--frecuencia", type=int, default=eventos.RUTA_FRECUENCIA,
                        metavar="F",
                        help="la frecuencia de las rutas de prueba, como en el "
                             "conversor")
    parser.add_argument("--ruta-de-prueba", nargs="+", type=int, default=None,
                        metavar="ORDEN",
                        help="agrega a la página de prueba una ruta forzada "
                             "sobre el héroe, con los códigos de "
                             "rpg::MoveCommand::Code: 0..3 mover, 12..15 girar")
    parser.add_argument("--encuentros-de-prueba", type=int, default=None,
                        metavar="PASOS",
                        help="cada cuántos pasos hay un encuentro al azar, "
                             "como el del conversor. **Tiene que ser el "
                             "mismo**: de acá sale en qué paso sale y contra "
                             "qué tropa")
    parser.add_argument("--encuentro", metavar="ARCHIVO",
                        help="archivo donde anotar el encuentro que corta la "
                             "caminata: la tropa y en qué paso salió. Es lo "
                             "que la receta le pasa a pantallas.py para "
                             "dibujar la pelea que la ROM tiene que estar "
                             "peleando")
    parser.add_argument("--pagina-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="ESPERA R G B [SAT]: agrega una página automática "
                             "inventada que espera N cuadros y después tiñe. Ningún dato "
                             "del juego ejercita las esperas, y sin esto el "
                             "intérprete cuadro a cuadro no lo prueba nada. La "
                             "saturación es opcional y por defecto es la neutra")
    parser.add_argument("--plan", help="archivo donde anotar, por dirección, "
                        "cuántas celdas camina el héroe y **cuántos ticks vive "
                        "la referencia**: la entrada, la caminata, los fundidos "
                        "y el margen. Es lo que le dice al emulador cuánto "
                        "correr, en vez de un número de segundos elegido a ojo")
    parser.add_argument("--margen", type=int, default=MARGEN, metavar="N",
                        help="cuántos ticks correr de más después de la "
                             "caminata. La ROM llega uno o dos cuadros después "
                             "de `pasos x 8`, así que sin margen el héroe "
                             "todavía no llegó. Acá **se viven** y entran en el "
                             "plan, que es lo que hace que el emulador corra "
                             "exactamente los mismos: es el otro lado de "
                             "--margen de snes_correr.py, que con un plan tiene "
                             "que ir en cero")
    parser.add_argument("--mapas", nargs="*", type=int, default=[], metavar="ID",
                        help="los otros mapas que entraron en la ROM, en el "
                             "mismo orden que le pasaste al conversor. Sin esto "
                             "una puerta no lleva a ningún lado, que es lo que "
                             "pasa en la consola")
    parser.add_argument("--inicial", type=int, default=0, metavar="N",
                        help="en qué índice de la tabla arranca la ROM, igual "
                             "que en el conversor")
    parser.add_argument("--hero-tile", nargs=2, type=int, metavar=("TX", "TY"),
                        help="poner al héroe en esta celda en vez de calcularla; "
                             "sirve para averiguar dónde lo dejó la ROM")
    parser.add_argument("--dir", default=None, choices=sorted(DIRECTIONS),
                        help="hacia dónde mira, si se fija la celda a mano")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()
    # La misma cuenta que hace el conversor, y por la misma razón: si un lado
    # reserva la paleta de la ventana y el otro no, el reparto de CGRAM difiere
    # y la comparación mide dos ROMs distintas.
    args.con_ventana = args.con_ventana or args.mensaje_de_prueba is not None
    args.con_timer = args.con_timer or args.timer_de_prueba is not None

    renderer = Renderer(args.game_dir)

    # El gráfico del héroe sale del grupo, no de acá. En RM2k lo da el primero
    # de la lista, y este juego arranca con el actor 10 —'DummyHero', que es
    # Chubby2[2]—. Hasta ahora había un default puesto a mano que daba
    # Future1[0], o sea el sprite de otro personaje; los dos lados de la
    # comparación lo tenían igual de mal, así que el cero no lo delataba.
    # --charset queda para forzarlo a mano cuando hace falta.
    grupo = args.grupo if args.grupo else renderer.database.party

    # El mundo son los mapas que entraron en la ROM, en el mismo orden y armado
    # con la misma regla que usa el conversor, incluido que un mapa repetido en
    # --mapas no entra dos veces. Sin --mapas es uno solo y no hay puerta que
    # lleve a ningún lado, que es como se comportaba esto antes de que hubiera
    # varios.
    tabla = [args.map_id] + [m for m in args.mapas if m != args.map_id]
    if not 0 <= args.inicial < len(tabla):
        sys.exit("--inicial %d pero la tabla tiene %d mapas"
                 % (args.inicial, len(tabla)))
    hay_prueba = (args.pagina_de_prueba or args.ruta_de_prueba
                  or args.ruta_de_evento or args.flash_de_prueba or args.switch
                  or args.destello_de_prueba
                  or args.timer_de_prueba or args.lugar_de_prueba
                  or args.parar_de_prueba
                  or args.rama_item_de_prueba
                  or args.rama_actor_de_prueba
                  or args.sacudida_de_prueba or args.fundir_bgm
                or args.pan_de_prueba or args.rama_de_prueba
                  or args.vars_de_prueba or args.rama_var_de_prueba
                  or args.items_de_prueba or args.acceso_de_prueba
                  or args.lluvia_de_prueba is not None
                  or args.animacion_de_prueba or args.batalla_de_prueba
                  or args.sprite_de_prueba
                  or args.tecla_de_prueba
                  or args.mensaje_de_prueba is not None)
    # El bloque de textos, armado igual que en el conversor y en el mismo orden:
    # el mensaje de prueba primero —desplazamiento 0— y después los mapas de la
    # tabla, que los junta `Mundo` al construirse.
    mensajes = (eventos.Mensajes(args.relleno_de_mensajes)
                if args.con_ventana else None)
    prueba = (mensajes.agregar(args.mensaje_de_prueba)
              if args.mensaje_de_prueba is not None else None)
    mundo = Mundo(renderer, args.game_dir, tabla,
                  (args.pagina_de_prueba, args.ruta_de_prueba, prueba,
                   snes_convert.ruta_de_evento(args.ruta_de_evento),
                   args.flash_de_prueba or (), args.switch or (),
                   args.timer_de_prueba or (),
                   snes_convert.lugar_de_prueba(args.lugar_de_prueba),
                   args.frecuencia,
                   snes_convert.sacudida_de_prueba(args.sacudida_de_prueba),
                   args.fundir_bgm, snes_convert.pan_de_prueba(args.pan_de_prueba),
                   tuple(args.rama_de_prueba or ()),
                   tuple(args.destello_de_prueba or ()),
                   args.guardar_de_prueba,
                   tuple(args.vars_de_prueba or ()),
                   tuple(args.rama_var_de_prueba or ()),
                   tuple(args.items_de_prueba or ()),
                   tuple(args.acceso_de_prueba or ()),
                   args.lluvia_de_prueba,
                   tuple(args.animacion_de_prueba or ()),
                   args.batalla_de_prueba,
                   args.parar_de_prueba,
                   tuple(args.rama_item_de_prueba or ()),
                   snes_convert.sprite_de_prueba(args.sprite_de_prueba),
                   tuple(args.tecla_de_prueba or ()),
                   tuple(args.rama_actor_de_prueba or ()))
                  if hay_prueba else None, mensajes,
                  graficos_de_prueba=snes_convert.graficos_de_prueba(
                      args.grafico_de_prueba),
                  grupo=grupo, con_timer=args.con_timer)
    # Cada cuántos pasos hay un encuentro, si la ROM de prueba lo forzó. Va
    # acá afuera del constructor y no adentro por lo que dice el comentario de
    # la tupla de prueba: agregarle un campo posicional a `Mundo` es
    # exactamente lo que ya se mergeó mal una vez.
    mundo.pasos_encuentro = args.encuentros_de_prueba

    # Los CharSets y los mapas ya convertidos se comparten entre las
    # direcciones. Convertir un mapa es lo más caro de todo esto —el 52 son
    # 14 segundos— y las cinco direcciones de un mapa comparten absolutamente
    # todo lo caro: los tiles, el reparto de paletas, el reuso y los
    # espejados. Lo único que cambia entre ellas es dónde termina el héroe y
    # dónde queda la cámara. Antes cada dirección era un proceso aparte y
    # rehacía la conversión entera; ahora se hace una vez por mapa.
    images = {}
    convertidos = {}
    naturales = {}

    def charset_image(name):
        # Por el cargador del renderer, que es el que sabe fabricar el CharSet
        # de un evento dibujado con un tile del chipset.
        image = renderer.charsets.get(name)
        if image is None:
            sys.exit("no encuentro el CharSet %r" % name)
        return image

    def natural(map_id):
        """Las capas del mapa convertidas como si estuviera solo en la ROM."""
        if map_id not in naturales:
            game_map = mundo.mapa(map_id)[0]
            base, above_img, variantes = renderer.capas_animadas(game_map)
            if base is None:
                sys.exit("no encuentro el chipset del mapa %d" % map_id)
            # La referencia se arma desde los datos convertidos, no desde el
            # render: entre uno y otro están la fusión de colores, el reparto en
            # paletas, el reuso de tiles y los espejados, y todo eso aparecería
            # como diferencia aunque la consola hiciera exactamente lo que se le
            # pidió. Las dos capas van juntas con la misma función que usa el
            # conversor, porque el reparto de CGRAM depende de las dos.
            #
            # Y con ventana el reparto es otro: le reserva una paleta y el
            # fondo fusiona. Esto faltaba, y no se veía porque en los mapas que
            # corría `snes-ventana` el fondo no llegaba a fusionar y las
            # paletas quedaban iguales igual. En el mapa 1 sí llega.
            naturales[map_id] = (game_map, base, above_img,
                                 snes_convert.convert_layers(
                                     base, above_img,
                                     con_ventana=args.con_ventana,
                                     variantes=variantes))
        return naturales[map_id]

    def convertir(map_id, pasos=(0, 0)):
        """El mapa como lo va a mostrar la consola, en ese paso de la animación.

        `pasos` son los dos de la animación del ChipSet, y entran en la clave
        del caché: el mapa se convierte una sola vez, pero los tiles de las
        corridas animadas se pisan con el dibujo que toque —lo mismo que la ROM
        sube por DMA— antes de dibujar.
        """
        if (map_id, pasos) not in convertidos:
            game_map, base, above_img, capas = natural(map_id)
            # Antes acá se volvía a convertir el mapa cuando la paleta de la
            # ventana —que es de la ROM entera— quedaba más abajo de donde este
            # mapa la habría puesto, y para saberla había que convertir todos
            # los mapas de la tabla aunque se dibujara uno solo. Con la ventana
            # en la paleta 0 no depende de nadie: el fondo arranca en
            # `CGRAM_RESERVADAS` y llega hasta su propia capa de encima.
            (tile_data, cram, tilemap, resumen), above_data = capas
            convertidos[(map_id, pasos)] = (
                game_map,
                snes_convert.render_converted(
                    snes_convert.anim_dibujo(tile_data, resumen["animacion"],
                                             pasos),
                    cram, tilemap),
                snes_convert.render_above(cram, above_data))
        return convertidos[(map_id, pasos)]

    def salida(patron, etiqueta):
        """El nombre de archivo de esta vuelta.

        La etiqueta es el avance si se pidió alguno, y si no la dirección. Con
        una sola vuelta y sin `{}` el nombre queda igual que siempre, que es lo
        que mantiene andando a las recetas que pasan una dirección sola.
        """
        return patron.format(etiqueta) if "{}" in patron else patron

    # Qué se recorre: o varias direcciones, o los avances de una misma
    # dirección. Los dos casos comparten la conversión del mapa, que es lo caro,
    # y en los dos el {} de -o lleva lo que está variando.
    #
    # Con avance la etiqueta es el avance aunque haya uno solo. Antes eso
    # dependía de si eran uno o varios, y `snes-caminando` con un solo avance
    # escribía la referencia como `-right` y después la buscaba como `-60`: la
    # receta no andaba con menos de dos.
    #
    # Y lo mismo con --cuadros: varios presupuestos de cuadros de una misma
    # dirección comparten la conversión. Es lo que hace falta para comparar una
    # ruta forzada *mientras* camina y no sólo donde termina, que es donde el
    # ciclo de caminata se vuelve visible.
    if args.avance:
        if len(args.walk) != 1:
            sys.exit("con avances hay que pedir una sola dirección")
        vueltas = [(args.walk[0], px, None, str(px)) for px in args.avance]
    elif args.cuadros and len(args.cuadros) > 1:
        if len(args.walk) != 1:
            sys.exit("con varios --cuadros hay que pedir una sola dirección")
        vueltas = [(args.walk[0], None, n, str(n)) for n in args.cuadros]
    else:
        n = args.cuadros[0] if args.cuadros else None
        vueltas = [(w, None, n, w) for w in args.walk]

    plan = []
    for walk, avance, cuadros, etiqueta in vueltas:
        # Los switches arrancan apagados y la pantalla sin teñir, como una
        # partida nueva de RM2k, y cada dirección arranca de cero: el estado lo
        # mueven los eventos y no puede filtrarse de una caminata a la otra.
        estado = eventos.Estado(grupo)
        # El bloque de textos, que el intérprete lee para saber si el cuadro
        # que abre trae pausas o se cierra solo. Es el mismo objeto que el que
        # dibuja la ventana más abajo, y los mismos bytes que la ROM tiene en
        # el cartucho.
        estado.mensajes = mensajes
        # Hacia dónde mira al arrancar, si se pidió. Es el estado y no un
        # arreglo al final: si una página lo gira después con un `face_*`
        # —la puerta del mapa 2 lo hace mirar abajo— gana la página, que es
        # lo que muestra la ROM. Antes `--dir` pisaba el giro al dibujar.
        if args.hero_tile and args.dir:
            estado.mirando = DIRECTIONS[args.dir]

        # Los toques anotados de `--tocar`, en el mismo formato que el modelo
        # nombra las teclas: los enteros 0 a 3 para las direcciones y "b" para
        # cancelar. A no entra acá —lo lleva `--apretar-a`, que además le habla
        # a los eventos— y tampoco start, que en el mapa no lo mira nadie.
        tocados = {}
        for toque in args.tocar or ():
            boton, _, cuadro = toque.partition(":")
            if boton not in DIRECTIONS and boton != "b":
                sys.exit("--tocar no sabe apretar %r: son las cuatro "
                         "direcciones y `b`" % boton)
            if not cuadro.isdigit():
                sys.exit("--tocar quiere BOTON:CUADRO, y vino %r" % toque)
            tocados.setdefault(int(cuadro), []).append(
                DIRECTIONS[boton] if boton in DIRECTIONS else boton)

        # Adónde se llega es lo primero: entre los eventos del arranque y las
        # puertas que cruce la caminata, el mapa que hay que dibujar bien puede
        # no ser el que se pidió.
        inicio = tuple(args.hero_tile) if args.hero_tile else None
        map_id, x, y, direction, pasos = hero_position(mundo, estado,
                                                       tabla[args.inicial],
                                                       walk, inicio,
                                                       avance, cuadros,
                                                       args.apretar_a,
                                                       DIRECTIONS[args.dir]
                                                       if args.dir else None,
                                                       # Un avance a mitad de
                                                       # camino no lleva
                                                       # margen: el cuadro que
                                                       # se compara es uno de
                                                       # adentro de la
                                                       # caminata.
                                                       0 if avance is not None
                                                       or cuadros is not None
                                                       else args.margen,
                                                       tocar=tocados)

        # Con qué se dibuja al héroe se decide *después* de correr los eventos,
        # no antes: `ChangePartyMembers` puede cambiar el líder del grupo, y en
        # RM2k el gráfico del héroe es el del líder —`AddActor` y `RemoveActor`
        # llaman los dos a `ResetGraphic`—. La página del mapa 121 hace
        # exactamente eso: saca al 10 y mete al 14, así que el héroe pasa de
        # `DummyHero`, que es una celda vacía, a Talan.
        def en_el_banco(par):
            """Si el gráfico tiene tiles y paleta en este mapa.

            Es la misma pregunta que del lado de la ROM contesta la tabla
            `ruta_grafico` del mapa, con $FF para "no está": ver
            `grafico_se_ve` en snes_convert.py, que es quien la emite.
            """
            return (bool(snes_convert.sprite_colors(charset_image(par[0]),
                                                    par[1]))
                    and par in mundo.paleta_de_sprite(map_id))

        if args.charset is not None:
            charset, charset_index = args.charset, args.charset_index or 0
        else:
            charset, charset_index = renderer.database.lider(estado.grupo)
            # Y encima del LDB, el `ChangeSpriteAssociation` que le hayan hecho
            # al líder, que **sí** cruza el teletransporte: en RM2k el gráfico
            # vive en el actor. Si el CharSet no está en el banco de sprites de
            # este mapa se queda con el del LDB, que es lo mismo que hace la
            # ROM en `elegir_grafico_heroe`. Ver OP_ACTOR_SPRITE.
            lider = estado.grupo[0] if estado.grupo else None
            if lider in estado.actor_graf:
                par = mundo.graficos(map_id).pares[estado.actor_graf[lider]]
                if en_el_banco(par):
                    charset, charset_index = par

        # Y encima de eso, la orden 34 de una ruta forzada sobre el héroe, que
        # gana sobre el líder: es `SetSpriteGraphic` sobre `Game_Player`, el
        # mismo dato que la orden le cambia a un evento. La ROM lo hace
        # apuntando `hero_poses` adentro de `npc_poses`; ver `grafico_heroe` en
        # main.s. No sobrevive al cambio de mapa **de los dos lados**: allá
        # porque las poses viven en el banco de sprites del mapa, y acá porque
        # `entrar_a_un_mapa` lo repone.
        heroe_se_ve = True
        if estado.ruta_heroe.grafico is not None:
            charset, charset_index = mundo.graficos(map_id).pares[
                estado.ruta_heroe.grafico]
            if not en_el_banco((charset, charset_index)):
                # Un CharSet sin un solo pixel opaco, o uno que no entró en las
                # ocho paletas de sprite: el héroe deja de dibujarse, igual que
                # un evento al que la 34 le esconde la fila.
                heroe_se_ve = False

        # En qué paso de la animación del ChipSet está el mapa. El reloj es
        # `vueltas`, el de la ROM, y ése **no es `estado.ticks`**: adentro del
        # negro de un teletransporte el mundo está congelado y `cuadro_de_eventos`
        # no corre, pero la consola sigue dando vueltas al lazo. Es la misma
        # cuenta que el plan de la caminata le pasa al emulador —ver el `plan`
        # de más abajo— y sin ella la escena de Core y Manta se iba 70 ticks
        # por cada fundido: el agua quedaba en otro dibujo desde el primer
        # teletransporte.
        chipset = renderer.database.chipsets[
            mundo.mapa(map_id)[0].chipset_id]
        tick = estado.ticks + estado.fundidos * eventos.FUNDIDO_TOTAL
        pasos_anim = (rm2k.paso_de_agua(tick, chipset.animation_type,
                                        chipset.animation_speed),
                      rm2k.paso_animado(tick))
        game_map, mapa, encima_todo = convertir(map_id, pasos_anim)
        cam_x, cam_y = camera_for(x, y, game_map.width * 2,
                                  game_map.height * 2,
                                  (estado.pan_x, estado.pan_y))
        # La sacudida de pantalla corre el mapa y los personajes, no la
        # ventana: es `GetDisplayX`, la posición de la cámara más la sacudida
        # en pixeles, sin volver a acotarla al mapa. Afuera del mapa PIL deja
        # negro, que es lo que dibuja RM2k del otro lado del borde.
        cam_x += estado.sacudida_pos
        view = mapa.crop((cam_x, cam_y, cam_x + SCREEN_W, cam_y + SCREEN_H))

        # Todo lo que se dibuja encima del mapa, con la clave con la que RM2k lo
        # ordena: primero por capa y recién después por Y. Se pinta de atrás
        # hacia adelante, que es al revés del orden en que van a OAM.
        # La clave lleva los tres desempates de RM2k: capa y Y en la palabra
        # que la consola compara, y después X e id, que allá los resuelve el
        # orden de la tabla. Ver `orden_de_dibujo` en snes_convert.py.
        actors = []
        # Dónde está cada blanco posible en pixeles del mapa: el héroe es el 0
        # y un evento su índice más uno, que es la misma numeración de las
        # rutas y de los destellos. Lo pide la animación de batalla.
        anclas = {}
        paginas_del_mapa = mundo.paginas(map_id)
        for npc in mundo.npcs(map_id):
            blanco_flash = npc["evento"] + 1
            ruta = estado.rutas_ev.get(npc["evento"])
            altura = 0
            cx, cy = estado.pos_ev.get(npc["evento"], (npc["x"], npc["y"]))
            # Lo que dibuja: lo de su fila, salvo que el gráfico siga a la
            # página activa —una puerta que se abre—, y ahí es el de ésta,
            # con su capa, o nada. Es lo que la ROM copia en el refresco.
            charset_npc, index_npc, pose_pagina, capa = (
                npc["charset"], npc["index"], npc["pose"], npc["layer"])
            if npc["cambia"]:
                pagina = eventos.pagina_activa(paginas_del_mapa, npc["evento"],
                                               estado)
                grafico = pagina["grafico"] if pagina is not None else None
                if grafico is None or grafico[:2] in npc["afuera"]:
                    continue
                charset_npc, index_npc, pose_pagina = grafico
                capa = pagina["capa"]
            elif not npc["visible"]:
                continue
            if ruta is not None and ruta.grafico is not None:
                # Una orden 34 le cambió el gráfico, y eso gana sobre lo de la
                # página: `SetSpriteGraphic` escribe el dato del personaje. La
                # pose no se toca —sigue el ciclo de caminata donde estaba— y
                # tampoco la capa, que es de la página.
                charset_npc, index_npc = mundo.graficos(map_id).pares[
                    ruta.grafico]
                if (not snes_convert.sprite_colors(charset_image(charset_npc),
                                                   index_npc)
                        or (charset_npc, index_npc)
                        not in mundo.paleta_de_sprite(map_id)):
                    # Un CharSet sin un solo pixel opaco —`nobodyhere`, 185
                    # de las 437 órdenes 34 del juego— o uno que no entró en
                    # las paletas de sprite: el evento desaparece. Hay que
                    # saltearlo y no dibujarlo transparente, porque en la
                    # consola la fila se esconde y deja de ocupar un objeto:
                    # dibujarlo acá cambiaría qué se pierde en una línea con
                    # muchos sprites.
                    continue
            if ruta is None:
                px, py, pose = cx * TILE, cy * TILE, pose_pagina
                if npc["evento"] in mundo.anima_quieto(map_id):
                    # Quieto pero animando: la columna sale del reloj del juego
                    # y no de un contador suyo. Ver `columna_animada` en
                    # tools/eventos.py y `animar_quietos` en main.s.
                    pose = (pose_pagina // 3) * 3 + eventos.columna_animada(
                        tick, npc["velocidad"])
            else:
                altura = eventos.altura_del_salto(ruta)
                px, py = eventos.pixeles_del_paso(cx, cy, ruta)
                mira = (ruta.mirando if ruta.mirando is not None
                        else pose_pagina // 3)
                pose = mira * 3 + ruta.columna()
            # Y si es el que el héroe acaba de disparar, mirándolo: ver
            # `Estado.girar`. Vale también con una ranura de ruta, si la ruta
            # ya terminó.
            pose = estado.pose_girada(npc["evento"], pose)
            actors.append(((snes_convert.sort_key(capa, py), px,
                            npc["evento"]),
                           charset_npc, index_npc, pose, px, py,
                           capa == rm2k.LAYER_ABOVE, blanco_flash,
                           altura))
            # Dónde está, para la animación de batalla que lo tenga de
            # objetivo. Sólo los que se dibujan: en la consola un evento sin
            # fila —o con la fila escondida— no tiene de dónde sacar la
            # posición, y `animacion_dibujo_oam` se saltea la animación.
            anclas[npc["evento"] + 1] = (px, py)
        # El último campo es si va por encima de la capa de encima. Para el
        # héroe es falso salvo en la ROM de `snes-encima`, donde su prioridad
        # de objeto sube a 2 —el mismo bit que llevan los eventos "above"— y
        # el hardware lo pone adelante de BG2. Su capa para ordenarlo contra
        # los NPCs no cambia: la prioridad es de la PPU y la capa es de RM2k.
        # La pose: parado al final de la caminata, y la del ciclo cuando se
        # pide un avance. El héroe se mueve WALK_SPEED = 2 pixeles por cuadro,
        # así que los cuadros que lleva moviéndose son el avance sobre dos.
        if avance is not None:
            columna = columna_de_caminata(cuadros_de_avance(estado, avance),
                                          estado.ruta_heroe.velocidad)
        elif estado.cuadros_moviendose:
            # Caminando por una ruta forzada: la pose sale del mismo ciclo que
            # `animate_hero`, contando los cuadros que lleva moviéndose. Sin
            # `-1`, que es el mismo número que usa la caminata con el pad de acá
            # arriba: en la ROM `advance_step` prende `moving` y `animate_hero`
            # corre en la misma vuelta, así que a los N cuadros moviéndose el
            # contador de animación ya bajó N veces. Con el `-1` los dos lados
            # cambiaban de columna en cuadros distintos y sólo se notaba en los
            # múltiplos de ANIM_FRAMES: barriendo los 70 cuadros de una ruta de
            # ocho celdas, fallaban exactamente el 6, el 12, el 18 y así.
            columna = estado.ruta_heroe.columna_del_heroe()
        else:
            columna = STAND
        # El héroe finge la X más alta posible, que es lo que hace
        # `Game_Player::GetScreenZ`: "when the Player is on the same
        # Y-coordinate as an event the Player is always rendered first". Sin
        # eso la referencia lo dibujaba **detrás** del NPC con el que empataba,
        # y la ROM adelante; se ve parado encima de uno en el mapa 73.
        if heroe_se_ve:
            actors.append(((snes_convert.sort_key(rm2k.LAYER_SAME, y),
                            0xFFFF, 0xFFFF),
                           charset, charset_index,
                           direction * 3 + columna, x, y, args.heroe_encima, 0,
                           eventos.altura_del_salto(estado.ruta_heroe)))
        # El héroe es el blanco 0, como en las rutas. Va puesto aunque no se
        # dibuje: su celda se sabe igual —la ROM la tiene en `hero_x`—, que no
        # es el caso de un evento, que sin fila no tiene de dónde sacarla.
        anclas[0] = (x, y)

        # En OAM van del frente hacia el fondo, que es al revés del orden en que
        # se pintan. La consola recorre ese mismo orden para decidir qué entra
        # en cada línea, así que hay que respetarlo para reproducir lo que se
        # pierde.
        order = sorted(actors, key=lambda a: a[0], reverse=True)
        # **El destello es por paleta y no por sprite**, que es lo que hace la
        # consola: `pintar_flash` mira `paleta_del_blanco` y sube **esa fila de
        # CGRAM** mezclada, así que destella todo lo que la comparta —otro
        # evento con el mismo gráfico, uno al que le prestaron la paleta, o el
        # héroe cuando el líder es además NPC del mapa—. RM2k lo hace sobre la
        # imagen de un sprite solo; acá el hardware no deja, y antes que los dos
        # lados se equivoquen distinto, la referencia modela lo que la consola
        # hace. Es una divergencia declarada con RM2k, no una entre los dos
        # lados: ver `assets/LIMITACIONES.md`.
        #
        # De quién es cada fila sale del mismo reparto que usa el conversor, y
        # el blanco se resuelve con lo que **se está dibujando**, que es de
        # donde la ROM saca el byte de atributos de la fila del NPC. Un blanco
        # que no se dibuja no tiñe nada, igual que el `$FF` de
        # `paleta_del_blanco`.
        paleta_de = mundo.paleta_de_sprite(map_id)
        fila_de_blanco = {}
        for _key, name, index, _pose, _px, _py, _arr, blanco, _alt in actors:
            fila = paleta_de.get((name, index))
            if fila is not None:
                fila_de_blanco[blanco] = fila
        # Fila -> qué destello la está tiñendo. Si dos destellos vivos cayeran
        # en la misma fila gana el último, que es lo que pasa en la consola:
        # `flashes_tick` recorre las ranuras en orden y cada una sube la fila
        # entera, así que la última escrita es la que queda. En este juego no
        # pasa —una página se bloquea mientras dura su destello— y ningún caso
        # de la tanda lo ejercita.
        destello_de_fila = {}
        for blanco in estado.flashes:
            fila = fila_de_blanco.get(blanco)
            if fila is not None:
                destello_de_fila[fila] = blanco
        sprites = []
        for _key, name, index, pose, px, py, arriba, blanco, altura in order:
            imagen = pose_image(charset_image(name), index, pose,
                                mundo.paleta_prestada(map_id, (name, index)),
                                mundo.poses(map_id).get((name, index)))
            # El destello va sobre el personaje ya dibujado, que en la consola
            # es su paleta. El tinte de pantalla va antes —`Cache::SpriteEffect`
            # aplica el tono y después la mezcla— y acá lo aplica `tenir_imagen`
            # sobre todo al final, que es el mismo orden.
            quien = destello_de_fila.get(paleta_de.get((name, index)))
            imagen = destellar_imagen(imagen, estado.color_de_flash(quien),
                                      estado.nivel_de_flash(quien)) \
                if quien is not None else imagen
            sprites.append((imagen, px - 4 - cam_x,
                            py - 16 - cam_y - altura, arriba))

        # La capa que va por encima del héroe se compone entre los sprites
        # comunes y los eventos marcados "above", que es el orden de RM2k y el
        # que el hardware reproduce con las prioridades del modo 3.
        encima = encima_todo.crop((cam_x, cam_y,
                                   cam_x + SCREEN_W, cam_y + SCREEN_H))
        glifos = glifos_del_timer(estado)
        # El cartel del `ShowPicture`, si hay uno puesto: sus objetos gastan el
        # presupuesto de OAM y el de la línea como cualquier otro. Sólo lo
        # dibuja el mapa que se llevó sus tiles al banco de sprites, que es el
        # mismo que lo muestra: ver `cartel_de_imagen` en snes_convert.py.
        cartel = (mundo.imagenes.info
                  if estado.imagen is not None and mundo.imagenes.info
                  else None)
        # Y la animación de batalla, si hay una dibujándose y este mapa la
        # dibuja. Los cuatro objetos gastan el presupuesto de OAM y el de la
        # línea como cualquier otro. Ver `animacion_dibujo_oam` en main.s.
        anim = None
        if estado.anim_cuadro is not None and mundo.dibuja_animacion(map_id):
            numero, blanco, _t, _n = estado.anim_dibujo
            info = animacion_mod.de_numero(renderer, numero)
            donde = None
            if info is None:
                pass
            elif blanco == eventos.ANIM_BLANCO_PANTALLA:
                donde = animacion_mod.esquina(info, 0, 0)
            elif blanco in anclas:
                ax, ay = animacion_mod.esquina(info, *anclas[blanco])
                donde = (ax - cam_x, ay - cam_y)
            if donde is not None:
                anim = (info, estado.anim_cuadro, donde[0], donde[1])
        usados = sum(1 for _i, sx, sy, _a in sprites
                     if -32 <= sx < 256 and -32 <= sy < 224) + len(glifos)
        if cartel is not None:
            usados += cartel["objetos"]
        if anim is not None:
            usados += animacion_mod.OBJETOS
        gotas = (gotas_en_oam(estado.gotas, usados, cam_x, cam_y)
                 if mundo.lleva_lluvia(map_id) else [])
        excedidas = draw_actors(view, sprites, encima, glifos, gotas,
                                estado.mensaje is not None,
                                (cartel["y"], cartel["objetos"])
                                if cartel is not None else None,
                                anim[3] if anim is not None else None)
        if excedidas:
            print("  %d líneas pasan el límite de sprites de la consola: ahí se"
                  " pierden objetos y no se comparan" % len(excedidas))
        # El archivo se escribe siempre, aunque no haya nada que excluir. Si
        # sólo se escribiera cuando sobran sprites, al cambiar de mapa quedaría
        # el del anterior y la comparación seguiría salteando líneas que ya no
        # corresponden: aflojaría la prueba justo donde nadie está mirando.
        if args.saltar:
            with open(salida(args.saltar, etiqueta), "w") as handle:
                handle.write("".join("%d\n" % y for y in excedidas))

        # El tinte va sobre el mapa entero: en la consola es una
        # transformación de CGRAM, y CGRAM la comparten el fondo, la capa de
        # encima y los sprites.
        view = tenir_imagen(view, estado.tinte)
        # Y el destello de pantalla encima del tinte, y también antes de la
        # ventana y del cronómetro: en RM2k `Priority_Screen` es 90, contra
        # 130 de la ventana y 140 del cronómetro. En la consola es la misma
        # transformación de CGRAM que el tinte, sobre las tres paletas del
        # mapa, y la paleta de la ventana y la del cronómetro no la reciben.
        if estado.destello_mostrado > 0:
            view = destellar_pantalla(view, estado.destello,
                                      estado.destello_mostrado)

        # Y el cartel, encima del tinte y del destello y debajo de la ventana
        # y del cronómetro: `Priority_PictureOld` es 120, contra 90 de la
        # pantalla, 130 de la ventana y 140 de los dígitos. En la consola sale
        # de que su paleta cae **arriba** de `SPRITE_CGRAM`, o sea afuera del
        # rango que `aplicar_tinte` recorre.
        #
        # Lo que esto **no** hace y RM2k sí: el destello de pantalla sí toca a
        # las imágenes —`affected_by_flash` viene prendido de fábrica— y acá no
        # las toca, por la misma razón por la que el tinte tampoco. Es deuda
        # declarada; ninguna página del juego destella con un cartel puesto.

        # La animación de batalla va entre el destello de pantalla y el
        # cartel: `Priority_Screen` es 90, `Priority_BattleAnimation` 110 y
        # `Priority_PictureOld` 120. Que el destello no la toque es lo mismo
        # que le pasa al cartel y por lo mismo: en la consola su paleta cae
        # arriba de `SPRITE_CGRAM`. En RM2k sí la tocaría —`SetFlashEffect` en
        # `BattleAnimation::Update`— y es deuda declarada.
        if anim is not None:
            info, cuadro, ax, ay = anim
            view = view.convert("RGBA")
            view.alpha_composite(animacion_mod.render(info, cuadro), (ax, ay))

        if cartel is not None:
            import imagen as imagen_mod
            pintado = imagen_mod.render(cartel, estado.imagen[0])
            view = view.convert("RGB")
            view.paste(pintado.convert("RGB"), (cartel["x"], cartel["y"]))

        # La ventana de mensaje va **después** del tinte, sin teñir. Es lo que
        # hace RM2k: en `Spriteset_Map::Update` el tono se le aplica al
        # tilemap, a los personajes, al panorama y a las sombras, y la ventana
        # no está entre ellos —`Priority_Window` es 130 contra el
        # `Priority_Screen` de 90—. Y es lo que hace la ROM sin proponérselo:
        # `aplicar_tinte` vuelve a subir las tres paletas del mapa desde el
        # cartucho y la de la ventana no es ninguna de ellas, así que queda
        # como la subió `load_ventana`. Acá decía lo contrario, "como en la
        # consola", y ninguna prueba abría un mensaje sobre una pantalla
        # teñida: `snes-cerrar` tiñe recién después de cerrarlo. La primera
        # que lo hizo, `snes-ruta-pisa` con la cola, dio 4122 pixeles.
        if estado.mensaje is not None:
            import ventana as ventana_mod
            skin = ventana_mod.skin(args.game_dir,
                                    renderer.database.system_name)
            # El texto sale del bloque, no del flag: con `--mensaje-de-prueba`
            # es el que se pidió, y con los ShowMessage del juego es el que el
            # bytecode nombró. La ROM lee esos mismos bytes del cartucho.
            caja = ventana_mod.pagina(skin, mensajes.lineas(estado.mensaje),
                                      font_id=renderer.database.font_id)
            view = view.convert("RGBA")
            view.paste(caja, (0, view.height - caja.height), caja)

        # El cronómetro va al final de todo, **incluido el tinte**. En RM2k es
        # `Priority_Timer` = 140 contra el `Priority_Screen` = 90 del tinte: la
        # pantalla se oscurece y los dígitos no. En la consola eso sale de la
        # prioridad 3 de objeto más una paleta propia que `aplicar_tinte`
        # vuelve a subir sin teñir.
        if glifos:
            import ventana as ventana_mod
            sys_img = ventana_mod.skin(args.game_dir,
                                       renderer.database.system_name)
            view = view.convert("RGBA")
            for glifo, mitad, sx, sy in glifos:
                ox = snes_convert.TIMER_ORIGEN[0] + glifo * 8
                oy = snes_convert.TIMER_ORIGEN[1] + mitad * 8
                view.paste(sys_img.crop((ox, oy, ox + 8, oy + 8)), (sx, sy),
                           sys_img.crop((ox, oy, ox + 8, oy + 8)))

        # Y el brillo maestro al final de todo, que es donde lo aplica el PPU:
        # si hay un fundido corriendo, la pantalla entera sale más oscura.
        # `estado.fundido` es el cuadro del fundido en que quedó la corrida.
        if estado.fundido is not None:
            view = oscurecer_imagen(view.convert("RGB"),
                                    eventos.brillo_de_fundido(estado.fundido))

        # El plan cuenta los cuadros del fundido: cada teletransporte que la
        # caminata cruce son FUNDIDO_TOTAL cuadros más en los que el emulador
        # no tiene que hacer nada, pero que igual pasan.
        # Los ticks que esta corrida vivió, no los que dura la caminata: la
        # entrada corre eventos, el margen también, y los dos mueven a los
        # eventos que caminan solos. Los cuadros del fundido se suman aparte
        # porque adentro del negro el mundo está congelado y `cuadro_de_eventos`
        # no corre, pero el reloj de la consola sí avanza.
        plan.append((walk, pasos,
                     estado.ticks
                     + estado.fundidos * eventos.FUNDIDO_TOTAL))
        destino = salida(args.output, etiqueta)
        view.convert("RGB").save(destino)
        # La dirección que se imprime es la que se dibuja, no la que se pidió
        # caminar. Antes se imprimía `walk` cuando había caminata, y eso miente
        # justo donde importa: con un mensaje abierto el pad no mueve ni gira al
        # héroe, así que `--walk right` dibuja al héroe mirando abajo. Es el
        # mismo error que el "mirando abajo" fijo que ya costó un rato.
        print("esperado -> %s: mapa %d, héroe en (%d,%d) mirando %s, cámara en"
              " (%d,%d)%s"
              % (destino, map_id, x, y, NOMBRE_DIR[direction],
                 cam_x, cam_y,
                 ("" if estado.tinte == (eventos.TINTE_NEUTRO,) * 4
                  else ", tinte %d/%d/%d y saturación %d" % estado.tinte)
                 + (", con la ventana de mensaje abierta diciendo %r"
                    % (mensajes.lineas(estado.mensaje),)
                    if estado.mensaje is not None else "")))
        if pasos:
            por_celda = cuadros_por_celda(estado)
            print("  camina %d celdas = %d cuadros a %d por celda"
                  % (pasos, pasos * por_celda, por_celda))
        if estado.encuentro is not None:
            # La caminata se cortó porque salió un encuentro al azar. La imagen
            # de arriba es el mapa **sin la pelea encima**, así que no es
            # contra eso que hay que comparar: contra la pantalla de batalla
            # que dibuja `pantallas.py --batalla`, con esta tropa.
            print("  encuentro al azar en el paso %d: la tropa %d"
                  % estado.encuentro)
            if args.encuentro:
                with open(args.encuentro, "w") as handle:
                    # Y con qué grupo se pelea, que **no** es el del arranque:
                    # las páginas del mapa lo pueden haber cambiado mientras se
                    # caminaba. En el mapa 21 pasa: entra Talan. Sin esto la
                    # pantalla de la pelea se dibuja con un renglón de menos.
                    handle.write("%d %d %s\n"
                                 % (estado.encuentro[1], estado.encuentro[0],
                                    ",".join(str(a) for a in estado.grupo)))

    if args.plan:
        with open(args.plan, "w") as handle:
            for walk, pasos, duracion in plan:
                handle.write("%s %d %d\n" % (walk, pasos, duracion))


if __name__ == "__main__":
    main()
