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

import eventos
import lcf
import rm2k
import pixeles
import snes_convert
from rm2k import collect_doors, collect_npcs, passability_map, puede_pasar
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                        find_resource, load_image)

# El paso del héroe son dieciséis pixeles y la ROM avanza WALK_SPEED = 2 por
# cuadro, así que cada celda cuesta ocho cuadros. Este número es el puente entre
# la referencia —que sabe cuántas celdas se camina— y el emulador, que ahora
# corre cuadros exactos en vez de segundos de reloj. Si alguna vez cambia
# WALK_SPEED en main.s, cambia acá: son los dos lados de la misma cuenta y
# separarlos es el error que este repo ya cometió cinco veces.
CUADROS_POR_CELDA = 8

# El ciclo de caminata de la ROM, de `animate_hero` en main.s: cuatro pasos
# sobre tres columnas del CharSet —0, 1, 2, 1—, uno cada ANIM_FRAMES cuadros, y
# quieto vuelve al del medio. Se arranca en el 1 con el contador lleno.
#
# Esto no lo modelaba nadie de este lado, y por eso las poses de caminata no las
# verificaba ninguna prueba: cuando el héroe choca contra la pared `moving` es
# cero, así que la única pose que llegaba a compararse era la parada.
ANIM_FRAMES = 6
ANIM_INICIAL = 1


def columna_de_caminata(cuadros_moviendose):
    """En qué columna del CharSet está el héroe tras N cuadros caminando."""
    paso = (ANIM_INICIAL + cuadros_moviendose // ANIM_FRAMES) % 4
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
                 grupo=(), con_timer=False):
        self.prueba = prueba
        # Para `npcs_dibujables`: qué líderes puede haber y cuántas paletas de
        # sprite quedan, que deciden qué eventos dibujados con un tile se ven.
        self.grupo = list(grupo)
        self.con_timer = con_timer
        self.renderer = renderer
        self.game_dir = game_dir
        self.ids = list(ids)
        self.indices = {map_id: i for i, map_id in enumerate(self.ids)}
        self.cache = {}
        self.npcs_cache = {}
        self.paginas_cache = {}
        self.mensajes = mensajes
        # Los temas se numeran igual que en el conversor, en el orden en que los
        # PlayBGM los piden. Acá no suena nada —la comparación es de pixeles—
        # pero el opcode **ocupa dos bytes** en el bytecode, así que si un lado
        # lo emitiera y el otro no, los dos recorrerían streams distintos.
        self.temas = eventos.Temas()
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
            paginas = eventos.paginas_del_mapa(self.mapa(map_id)[0],
                                               self.indices.get, self.mensajes,
                                               self.temas)
            if self.prueba is not None and map_id == self.ids[0]:
                # La página inventada va sólo en el mapa donde arranca la ROM,
                # que es el mismo que el conversor le agrega la suya.
                espera, tinte = 0, ()
                if self.prueba[0] is not None:
                    espera, *tinte = self.prueba[0]
                paginas = paginas + [dict(EVENTO_DE_PRUEBA,
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
                                              pan=self.prueba[11]))]
            self.paginas_cache[map_id] = paginas
        return self.paginas_cache[map_id]

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
            self.npcs_cache[map_id] = snes_convert.npcs_dibujables(
                self.renderer, game_map, lideres,
                7 if self.con_timer else 8)[0]
        return self.npcs_cache[map_id]


# El mismo tope que `saltos_restantes` en la ROM: dos mapas que se
# teletransporten entre sí colgarían a los dos lados, y una prueba colgada no
# le dice nada a nadie.
SALTOS_MAX = 8


# Cómo se ve la página inventada en la tabla. El número de evento es alto a
# propósito: tiene que no chocar con ninguno del mapa.
EVENTO_DE_PRUEBA = {"evento": 9999, "pagina": 0,
                    "trigger": eventos.TRIGGER_AUTOMATICO,
                    "switch_a": 0, "switch_b": 0, "actor": 0, "capa": 0,
                    "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                    "codigo": b""}


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

    def puede(direccion):
        dx, dy = PASOS[direccion]
        return rm2k.puede_pasar(passable, game_map.width, game_map.height,
                                x, y, dx, dy, pasa_evento=pasa) \
            and libre(x + dx, y + dy)

    antes = estado.paso_cuadros
    direccion = estado.cuadro_de_ruta(
        puede,
        saltar=lambda dx, dy: (puede_caer(passable, game_map, x + dx, y + dy)
                               and libre(x + dx, y + dy)))
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


def cuadro_de_eventos(estado, passable, game_map, heroe, paginas=(),
                      congelada=False):
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
        dx, dy = PASOS[direccion]
        return rm2k.puede_pasar(passable, game_map.width, game_map.height,
                                x, y, dx, dy, pasa_evento=pasa) \
            and libre(indice, x + dx, y + dy)

    estado.cuadro_de_rutas_ev(
        puede,
        lambda cx, cy, indice: (puede_caer(passable, game_map, cx, cy)
                                and libre(indice, cx, cy)),
        heroe=heroe, congelada=congelada)
    estado.cuadro_de_flashes()
    estado.cuadro_de_timer()
    estado.cuadro_de_sacudida()
    estado.cuadro_de_pan()
    estado.cuadro_de_destello()


def entrar_al_mapa(mundo, estado, map_id, entrada=None, cuadros=None,
                   apretar_a=None, mirando=None):
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
    ultimo_a = max(apretar_a) if apretar_a else None
    while True:
        game_map, passable, ocupadas, _puertas = mundo.mapa(map_id)
        # Dónde arranca cada evento del mapa, en celdas y por índice de la tabla
        # de la ROM. Se rearma al entrar, como `cargar_mapa` vuelve a copiar la
        # tabla desde el cartucho, y con eso se tiran las rutas que estuvieran
        # corriendo en el mapa que se deja.
        estado.entrar_a_un_mapa({n: (ev.x, ev.y)
                                 for n, ev in enumerate(game_map.events)},
                                mundo.paginas(map_id),
                                {npc["evento"]: npc["velocidad"]
                                 for npc in collect_npcs(game_map)})
        if entrada is None:
            x, y = snes_convert.inicio_del_mapa(mundo.renderer, map_id,
                                                passable, game_map.width,
                                                game_map.height, ocupadas)
        else:
            x, y = entrada
            entrada = None
        # Con un presupuesto de cuadros el intérprete avanza sólo esos; sin él,
        # hasta que las páginas terminen. Lo primero hace falta para comparar
        # *durante* una espera: el emulador corrió N cuadros y la referencia
        # tiene que haber corrido los mismos.
        if cuadros is None:
            salto = eventos.correr_automaticos(
                mundo.paginas(map_id), estado,
                avanzar=lambda: cuadro_de_eventos(estado, passable, game_map,
                                                  (x, y), mundo.paginas(map_id),
                                                  congelada=True))
            # Sin presupuesto de cuadros la ruta forzada igual tiene que
            # caminarse entera: lo que se compara es dónde queda todo. Antes el
            # giro lo aplicaba el intérprete y esto no hacía falta; ahora la
            # ruta la camina el héroe, y saltearla dejaba al héroe mirando a
            # cámara mientras la ROM lo mostraba mirando arriba.
            for _ in range(10000):
                if not estado.ruta and not estado.paso_cuadros \
                        and not estado.cuadros_moviendose \
                        and not estado.algo_corriendo():
                    break
                estado.refrescar()
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
                if estado.fundido is not None:
                    estado.fundido += 1
                    if estado.fundido >= eventos.FUNDIDO_TOTAL:
                        estado.fundido = None
                        continue
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
                if interprete.cuadro(apreto_a=apreta):
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
                        and not estado.paginas_caminando() \
                        and not estado.timer_activo \
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
                    break
        if salto is None:
            return map_id, x, y
        saltos -= 1
        if not saltos:
            return map_id, x, y     # demasiadas vueltas: se queda en este mapa
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
        if interprete.cuadro():
            salto = estado.salto
            estado.salto = None
            if mundo.ids[salto[0]] == map_id:
                x, y = salto[1], salto[2]
            else:
                map_id, x, y = entrar_al_mapa(mundo, estado, mundo.ids[salto[0]],
                                              (salto[1], salto[2]))
                return map_id, x, y, True
            continue
        estado.refrescar()
        x, y, llego = paso_de_ruta(estado, passable, game_map, x, y,
                                   interprete.paginas)
        if llego:
            interprete.probar_celda(x, y, eventos.TRIGGER_TOCA_HEROE, estado)
        cuadro_de_eventos(estado, passable, game_map, (x, y),
                          interprete.paginas, congelada=interprete.ocupado())
        if estado.mensaje is not None:
            return map_id, x, y, True
        if interprete.terminado and not estado.algo_corriendo() \
                and not estado.paso_cuadros and not estado.cuadros_moviendose:
            break
    return map_id, x, y, False


def hero_position(mundo, estado, map_id, direction_name, inicio=None,
                  avance=None, cuadros=None, apretar_a=None, mirando=None):
    """En qué mapa y en qué celda termina el héroe, y hacia dónde mira.

    No se estima: se entra al mapa como entra la ROM —corriéndole los eventos—
    y después se camina con sus mismas reglas, de a un paso, mirando entre paso
    y paso si la celda tiene una puerta, que es cuando la consola la mira. Si la
    tiene, se cambia de mapa —y al mapa nuevo también le corren sus eventos— y
    se sigue caminando desde donde deja, con la cruceta todavía apretada.

    Devuelve (mapa, x, y, dirección) con x e y en pixeles.
    """
    map_id, x, y = entrar_al_mapa(mundo, estado, map_id, inicio, cuadros,
                                  apretar_a, mirando)
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
        return map_id, px, py, quieto, 0
    desde = (x, y)

    # Cuántas celdas camina. Hasta ahora este número se calculaba y se tiraba;
    # es el que dice cuántos cuadros tarda la ROM en llegar, porque el paso son
    # dieciséis pixeles a WALK_SPEED = 2 por cuadro, o sea ocho cuadros por
    # celda. Antes la prueba pedía "45 segundos, seguro alcanza"; con esto pide
    # un número que sale de la misma referencia contra la que se compara.
    pasos = 0

    # El tope es por si dos puertas se apuntan entre sí: la ROM se quedaría
    # rebotando y la referencia también, y colgar una prueba no ayuda a nadie.
    for _ in range(10000):
        game_map, passable, _ocupadas, puertas = mundo.mapa(map_id)
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
        puerta = puertas.get((x, y))
        if puerta is None:
            # Sin puerta, puede haber un evento de contacto.
            map_id, nx, ny, frena = contacto_al_pisar(
                mundo, estado, map_id, x, y, passable, game_map)
            if (nx, ny) != (x, y) or frena:
                x, y = nx, ny
                if frena:
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


def pose_image(charset, index, pose):
    """Una pose, con los colores ya fusionados a los 15 que entran en un sprite.

    La fusión es la misma que hace el conversor —mismo criterio, mismos datos—
    así que si difiere algo no es esto.
    """
    counts = snes_convert.sprite_colors(charset, index)
    if len(counts) <= snes_convert.OBJ_COLORS:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = pixeles.merge_least_used(counts,
                                                 snes_convert.OBJ_COLORS)

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


def draw_actors(view, sprites, encima=None, timer=()):
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
    parser.add_argument("--flash-de-prueba", nargs=6, type=int, default=None,
                        metavar=("BLANCO", "R", "G", "B", "POTENCIA", "CUADROS"),
                        help="hace destellar a alguien desde la página de "
                             "prueba: el blanco es 0 para el héroe o el índice "
                             "del evento más uno, el color va de 0 a 31 y los "
                             "cuadros son cuántos dura")
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
    parser.add_argument("--pagina-de-prueba", nargs="+", type=int, default=None,
                        metavar="N",
                        help="ESPERA R G B [SAT]: agrega una página automática "
                             "inventada que espera N cuadros y después tiñe. Ningún dato "
                             "del juego ejercita las esperas, y sin esto el "
                             "intérprete cuadro a cuadro no lo prueba nada. La "
                             "saturación es opcional y por defecto es la neutra")
    parser.add_argument("--plan", help="archivo donde anotar, por dirección, "
                        "cuántas celdas camina el héroe y cuántos cuadros le "
                        "lleva. Es lo que le dice al emulador cuánto correr, "
                        "en vez de un número de segundos elegido a ojo")
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
                  or args.timer_de_prueba or args.lugar_de_prueba
                  or args.sacudida_de_prueba or args.fundir_bgm
                or args.pan_de_prueba
                  or args.mensaje_de_prueba is not None)
    # El bloque de textos, armado igual que en el conversor y en el mismo orden:
    # el mensaje de prueba primero —desplazamiento 0— y después los mapas de la
    # tabla, que los junta `Mundo` al construirse.
    mensajes = eventos.Mensajes() if args.con_ventana else None
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
                   args.fundir_bgm, snes_convert.pan_de_prueba(args.pan_de_prueba))
                  if hay_prueba else None, mensajes,
                  grupo=grupo, con_timer=args.con_timer)

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
    # La paleta de la ventana, cuando se sepa: es una para la ROM entera y
    # sale de todos sus mapas, no del que se está dibujando.
    ventana_paleta = []

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
            base, above_img = renderer.render_layers(game_map)
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
                                     con_ventana=args.con_ventana))
        return naturales[map_id]

    def convertir(map_id):
        if map_id not in convertidos:
            game_map, base, above_img, capas = natural(map_id)
            if args.con_ventana:
                # La paleta de la ventana es de la ROM entera, así que hay que
                # convertir **todos** sus mapas para saberla, aunque acá se
                # dibuje uno solo: la misma cuenta que hace el conversor, con
                # la misma función. El mapa que la tenía más arriba se vuelve a
                # convertir con el fondo apretado debajo de ella.
                if not ventana_paleta:
                    ventana_paleta.append(snes_convert.paleta_de_la_ventana(
                        natural(m)[3][1][3] for m in tabla))
                if capas[1][3] - 1 != ventana_paleta[0]:
                    capas = snes_convert.convert_layers(
                        base, above_img, con_ventana=True,
                        ventana_paleta=ventana_paleta[0])
            (tile_data, cram, tilemap, _resumen), above_data = capas
            convertidos[map_id] = (
                game_map,
                snes_convert.render_converted(tile_data, cram, tilemap),
                snes_convert.render_above(cram, above_data))
        return convertidos[map_id]

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
        # Hacia dónde mira al arrancar, si se pidió. Es el estado y no un
        # arreglo al final: si una página lo gira después con un `face_*`
        # —la puerta del mapa 2 lo hace mirar abajo— gana la página, que es
        # lo que muestra la ROM. Antes `--dir` pisaba el giro al dibujar.
        if args.hero_tile and args.dir:
            estado.mirando = DIRECTIONS[args.dir]

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
                                                       if args.dir else None)

        # Con qué se dibuja al héroe se decide *después* de correr los eventos,
        # no antes: `ChangePartyMembers` puede cambiar el líder del grupo, y en
        # RM2k el gráfico del héroe es el del líder —`AddActor` y `RemoveActor`
        # llaman los dos a `ResetGraphic`—. La página del mapa 121 hace
        # exactamente eso: saca al 10 y mete al 14, así que el héroe pasa de
        # `DummyHero`, que es una celda vacía, a Talan.
        if args.charset is not None:
            charset, charset_index = args.charset, args.charset_index or 0
        else:
            charset, charset_index = renderer.database.lider(estado.grupo)

        game_map, mapa, encima_todo = convertir(map_id)
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
            if ruta is None:
                px, py, pose = cx * TILE, cy * TILE, pose_pagina
            else:
                altura = eventos.altura_del_salto(ruta)
                px, py = eventos.pixeles_del_paso(cx, cy, ruta)
                mira = (ruta.mirando if ruta.mirando is not None
                        else pose_pagina // 3)
                pose = mira * 3 + ruta.columna()
            actors.append(((snes_convert.sort_key(capa, py), px,
                            npc["evento"]),
                           charset_npc, index_npc, pose, px, py,
                           capa == rm2k.LAYER_ABOVE, blanco_flash,
                           altura))
        # El último campo es si va por encima de la capa de encima. Para el
        # héroe es falso salvo en la ROM de `snes-encima`, donde su prioridad
        # de objeto sube a 2 —el mismo bit que llevan los eventos "above"— y
        # el hardware lo pone adelante de BG2. Su capa para ordenarlo contra
        # los NPCs no cambia: la prioridad es de la PPU y la capa es de RM2k.
        # La pose: parado al final de la caminata, y la del ciclo cuando se
        # pide un avance. El héroe se mueve WALK_SPEED = 2 pixeles por cuadro,
        # así que los cuadros que lleva moviéndose son el avance sobre dos.
        if avance is not None:
            columna = columna_de_caminata(avance // 2)
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
            columna = columna_de_caminata(estado.cuadros_moviendose)
        else:
            columna = STAND
        # El héroe finge la X más alta posible, que es lo que hace
        # `Game_Player::GetScreenZ`: "when the Player is on the same
        # Y-coordinate as an event the Player is always rendered first". Sin
        # eso la referencia lo dibujaba **detrás** del NPC con el que empataba,
        # y la ROM adelante; se ve parado encima de uno en el mapa 73.
        actors.append(((snes_convert.sort_key(rm2k.LAYER_SAME, y), 0xFFFF, 0xFFFF),
                       charset, charset_index,
                       direction * 3 + columna, x, y, args.heroe_encima, 0,
                       eventos.altura_del_salto(estado.ruta_heroe)))

        # En OAM van del frente hacia el fondo, que es al revés del orden en que
        # se pintan. La consola recorre ese mismo orden para decidir qué entra
        # en cada línea, así que hay que respetarlo para reproducir lo que se
        # pierde.
        order = sorted(actors, key=lambda a: a[0], reverse=True)
        sprites = []
        for _key, name, index, pose, px, py, arriba, blanco, altura in order:
            imagen = pose_image(charset_image(name), index, pose)
            # El destello va sobre el personaje ya dibujado, que en la consola
            # es su paleta. El tinte de pantalla va antes —`Cache::SpriteEffect`
            # aplica el tono y después la mezcla— y acá lo aplica `tenir_imagen`
            # sobre todo al final, que es el mismo orden.
            imagen = destellar_imagen(imagen, estado.color_de_flash(blanco),
                                      estado.nivel_de_flash(blanco)) \
                if blanco in estado.flashes else imagen
            sprites.append((imagen, px - 4 - cam_x,
                            py - 16 - cam_y - altura, arriba))

        # La capa que va por encima del héroe se compone entre los sprites
        # comunes y los eventos marcados "above", que es el orden de RM2k y el
        # que el hardware reproduce con las prioridades del modo 3.
        encima = encima_todo.crop((cam_x, cam_y,
                                   cam_x + SCREEN_W, cam_y + SCREEN_H))
        glifos = glifos_del_timer(estado)
        excedidas = draw_actors(view, sprites, encima, glifos)
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
        plan.append((walk, pasos,
                     pasos * CUADROS_POR_CELDA
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
                 + (", con la ventana de mensaje abierta"
                    if estado.mensaje is not None else "")))
        if pasos:
            print("  camina %d celdas = %d cuadros a %d por celda"
                  % (pasos, pasos * CUADROS_POR_CELDA, CUADROS_POR_CELDA))

    if args.plan:
        with open(args.plan, "w") as handle:
            for walk, pasos, duracion in plan:
                handle.write("%s %d %d\n" % (walk, pasos, duracion))


if __name__ == "__main__":
    main()
