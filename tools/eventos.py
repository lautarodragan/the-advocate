#!/usr/bin/env python3
"""Compila las páginas de evento de RM2k a algo que la ROM pueda ejecutar.

RM2k tiene unos 130 comandos de evento. La ROM entiende un puñado, y va a ir
entendiendo más. La regla que hace que eso sea seguro es una sola:

    **una página se emite sólo si todos sus comandos se pueden ejecutar.**

Si aparece uno que no modelamos, la página no se emite y el evento no hace
nada. Ejecutar la mitad de un script sería peor que no ejecutarlo: dejaría al
juego en un estado que no existe, y la comparación pixel a pixel no lo vería
porque la referencia haría exactamente lo mismo mal.

Los códigos de comando salen de tools/event_codes.py, que se genera desde
liblcf. Nunca de memoria: la primera versión del filtro de puertas los puso a
ojo y tres estaban mal.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- los comandos de RM2k que sabemos ejecutar ------------------------------
END = 10
CONTROL_SWITCHES = 10210
TELEPORT = 10810
TINT_SCREEN = 11030
WAIT = 11410
CHANGE_SAVE_ACCESS = 11930
CHANGE_PARTY_MEMBERS = 10330
PLAY_BGM = 11510
MOVE_EVENT = 11330

# Una ruta forzada de MoveEvent. Los parámetros son (a quién, frecuencia, un
# bitmask de repetición, si es salteable) y de ahí en adelante los comandos de
# la ruta, con los códigos de `rpg::MoveCommand::Code` de liblcf.
#
# De todos ellos hoy se aceptan sólo los cuatro de girar y la espera. Moverse
# por una ruta forzada no está: en RM2k el personaje camina celda por celda a lo
# largo de varios cuadros y hay que decidir qué pasa cuando lo bloquean, y no
# hay ninguna página del juego que compile y lo ejercite. Cuando la haya se
# agrega acá; mientras tanto, una ruta que se mueva no compila.
RUTA_HEROE = 10001
RUTA_MIRAR = {12: 0, 13: 1, 14: 2, 15: 3}   # face_up/right/down/left
RUTA_MOVER = {0: 0, 1: 1, 2: 2, 3: 3}       # move_up/right/down/left
RUTA_ESPERAR = 23

# Cómo consume el tiempo una ruta forzada, y es una decisión de modelo que los
# dos lados tienen que compartir: girar es instantáneo —se pasa al comando
# siguiente en el mismo cuadro—, esperar consume un cuadro, y moverse arranca un
# paso de una celda, que la ROM recorre a WALK_SPEED = 2 pixeles por cuadro como
# cualquier otro paso. Un movimiento bloqueado se saltea: la alternativa de RM2k
# es reintentar para siempre, y una prueba colgada no le dice nada a nadie.

# ChangePartyMembers: el primer parámetro dice si agrega o saca, el segundo de
# dónde sale el id del actor, y el tercero el id. De liblcf y de
# `Game_Interpreter::CommandChangePartyMember` en easyrpg-player.
GRUPO_AGREGAR, GRUPO_SACAR = 0, 1
GRUPO_ID_FIJO = 0
GRUPO_MAX = 4           # `Game_Party::AddActor` no agrega si ya hay cuatro

# Comandos que se aceptan sin hacer nada, porque no hacer nada no se ve. Es el
# mismo criterio que el de las puertas, y hay que aplicarlo con la misma
# desconfianza: si el comando cambia algo que sí dibujamos, no va acá.
MESSAGE_OPTIONS = 10120

IGNORABLES = {
    CHANGE_SAVE_ACCESS,   # habilita o no el menú de guardar, que no existe
    MESSAGE_OPTIONS,      # dónde y cómo se dibuja la ventana de mensaje, que
                          # sin mensajes no se dibuja en ningún lado
}

# Y esto es otra cosa, y la diferencia importa. Los de arriba no hacen nada
# porque no hay nada que hacer: el menú de guardar no existe y las ventanas de
# mensaje tampoco. Los de acá **sí** hacen algo y nosotros no lo hacemos; se
# aceptan igual porque lo que dejan sin hacer no aparece en la pantalla que se
# compara, y a cambio dejan correr páginas que si no quedarían afuera enteras.
#
# Es una deuda, no una equivalencia, y por eso está en una lista aparte con
# nombre propio: quien agregue algo acá tiene que poder decir qué se rompe.
#
# PlayBGM cambia el tema que suena. La ROM sube un solo banco de muestras al
# SPC700 al arrancar, así que cambiar de tema en caliente pide varios bancos en
# el cartucho y volver a subir en mitad del juego; es una feature de audio, no
# un comando más. Lo que se pierde: una página que cambie la música deja la que
# venía sonando. La pantalla no lo nota, pero `snes-check` compararía el audio
# contra el MIDI del mapa y no contra el tema que la página pidió, así que ahí
# la prueba mediría lo que no es. Ver "Lo que falta" en rom/LEEME.md.
ACEPTADOS_SIN_HACER = {
    PLAY_BGM,
}

# --- los opcodes que emitimos -----------------------------------------------
# Uno por comando, con los operandos ya resueltos: la ROM no vuelve a mirar el
# LCF ni conoce sus números.
OP_FIN      = 0x00
OP_SWITCH   = 0x01      # id (word), valor (byte)
OP_TELEPORT = 0x02      # mapa (byte), x (word), y (word)
OP_ESPERAR  = 0x03      # cuadros (word): la cinemática espera seis
                        # segundos, o sea 360, y no entran en un byte
OP_TINTE    = 0x04      # r, g, b, sat (byte cada uno)
OP_GRUPO    = 0x05      # operación (byte), actor (byte)
OP_RUTA     = 0x06      # cuántos comandos (byte), y los comandos

# ControlSwitches: el primer parámetro dice de dónde salen los ids y el último
# qué hacer con ellos (liblcf, ControlSwitches::Operation).
SWITCH_UNICO, SWITCH_RANGO, SWITCH_INDIRECTO = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

# Un rango absurdo no se desenrolla: mejor no ejecutar la página que emitir
# miles de opcodes por una línea.
MAX_RANGO = 64

# RM2k mide las esperas en décimas de segundo.
CUADROS_POR_DECIMA = 6

# Un paso son dieciséis pixeles a WALK_SPEED = 2 por cuadro.
CUADROS_POR_CELDA = 8

TRIGGER_AUTOMATICO = 3

# El tinte de RM2k va de 0 a 200 con 100 como neutro. En la ROM se guarda tal
# cual y se aplica al subir la paleta.
TINTE_NEUTRO = 100


class NoSePuede(Exception):
    """Esta página tiene algo que la ROM todavía no sabe hacer."""


def compilar_pagina(page, indice_de_mapa):
    """Los comandos de una página como bytes, o None si no se puede.

    `indice_de_mapa` traduce el id de mapa de RM2k al índice en la tabla de la
    ROM, y devuelve None para los mapas que no entraron en el cartucho: un
    teletransporte hacia uno de ésos hace que la página no sea ejecutable, que
    es más honesto que saltar a cualquier lado.
    """
    try:
        return b"".join(_compilar(cmd, indice_de_mapa)
                        for cmd in page.commands) + bytes([OP_FIN])
    except NoSePuede:
        return None


def _compilar(cmd, indice_de_mapa):
    p = cmd.parameters

    if cmd.code == END or cmd.code in IGNORABLES:
        return b""

    if cmd.code in ACEPTADOS_SIN_HACER:
        return b""     # se acepta con la deuda declarada arriba

    if cmd.code == CONTROL_SWITCHES:
        if len(p) < 4 or p[0] not in (SWITCH_UNICO, SWITCH_RANGO):
            raise NoSePuede()       # por variable: hace falta variables
        if p[3] == SWITCH_TOGGLE:
            raise NoSePuede()       # invertir pide leer, y todavía no leemos
        desde, hasta = p[1], p[2]
        if hasta < desde or hasta - desde >= MAX_RANGO:
            raise NoSePuede()
        valor = 1 if p[3] == SWITCH_ON else 0
        out = b""
        for numero in range(desde, hasta + 1):
            out += bytes([OP_SWITCH, numero & 0xFF, numero >> 8, valor])
        return out

    if cmd.code == TELEPORT:
        if len(p) < 3:
            raise NoSePuede()
        destino = indice_de_mapa(p[0])
        if destino is None:
            raise NoSePuede()       # el mapa no entró en la ROM
        return bytes([OP_TELEPORT, destino,
                      p[1] & 0xFF, p[1] >> 8, p[2] & 0xFF, p[2] >> 8])

    if cmd.code == CHANGE_PARTY_MEMBERS:
        if len(p) < 3 or p[1] != GRUPO_ID_FIJO:
            raise NoSePuede()   # el id sale de una variable, y no las leemos
        if p[0] not in (GRUPO_AGREGAR, GRUPO_SACAR) or not 0 <= p[2] <= 255:
            raise NoSePuede()
        return bytes([OP_GRUPO, p[0], p[2]])

    if cmd.code == MOVE_EVENT:
        if len(p) < 4 or p[0] != RUTA_HEROE:
            raise NoSePuede()   # mover otro evento pide que los NPCs se muevan
        ruta = list(p[4:])
        if not ruta or len(ruta) > 255:
            raise NoSePuede()
        for orden in ruta:
            # Moverse por una ruta forzada todavía no se acepta. La maquinaria
            # está de los dos lados —la ROM la camina en `paso_de_ruta` y la
            # referencia en `Estado.cuadro_de_ruta`— pero no coinciden: en el
            # cuadro asentado el héroe queda en la misma celda y mirando para el
            # mismo lado, y aun así hay 410 pixeles de diferencia, que es la
            # columna del ciclo de caminata. Está en la lista de ESTADO.md con
            # lo que ya se descartó. Aceptarlo sin que coincida sería emitir un
            # opcode que los dos lados ejecutan distinto.
            if (orden not in RUTA_MIRAR and orden != RUTA_ESPERAR):
                raise NoSePuede()
        return bytes([OP_RUTA, len(ruta)]) + bytes(ruta)

    if cmd.code == WAIT:
        if len(p) < 1:
            raise NoSePuede()
        cuadros = p[0] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        return bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])

    if cmd.code == TINT_SCREEN:
        if len(p) < 4:
            raise NoSePuede()
        if any(not 0 <= v <= 200 for v in p[:4]):
            raise NoSePuede()
        if p[3] != TINTE_NEUTRO:
            # La saturación no es un factor por canal sino una mezcla hacia el
            # gris, y todavía no la hacemos. Aceptar la página y no aplicarla
            # sería el error de siempre: la referencia haría lo mismo mal y la
            # comparación no lo vería.
            raise NoSePuede()
        # La duración se descarta: el tinte se aplica de una. La pantalla que
        # se compara está siempre asentada, así que el valor final es el que
        # importa; lo que se pierde es el degradé de un segundo.
        return bytes([OP_TINTE, p[0], p[1], p[2], p[3]])

    raise NoSePuede()


# --- ejecutar lo compilado --------------------------------------------------
#
# La ROM y la referencia corren el mismo bytecode. Tener el intérprete una sola
# vez del lado de Python no evita que haya dos implementaciones —la otra está en
# main.s— pero sí evita que haya dos *lenguajes*: lo que se ejecuta es el mismo
# programa, y las reglas de selección de página están escritas una vez acá y una
# vez allá, no una vez por llamador.


class Estado:
    """Lo que el intérprete recuerda entre páginas y entre mapas."""

    def __init__(self, grupo=()):
        self.switches = set()
        self.tinte = (TINTE_NEUTRO, TINTE_NEUTRO, TINTE_NEUTRO)
        self.salto = None       # (mapa, x, y) si una página pidió mudarse
        # El grupo, en orden. El gráfico del héroe es el del primero, así que
        # esto no es contabilidad: se ve en la pantalla que se compara.
        self.grupo = list(grupo)
        # Hacia dónde mira el héroe si una ruta forzada se lo dijo. None es
        # "lo decide la caminata", que es lo de siempre.
        self.mirando = None
        # La ruta forzada pendiente y el paso en curso, en cuadros.
        self.ruta = []
        self.paso_dir = None
        self.paso_cuadros = 0
        # Cuántos cuadros seguidos lleva moviéndose, para la pose de caminata.
        # `animate_hero` lo reinicia en cuanto se queda quieto.
        self.cuadros_moviendose = 0

    def cuadro_de_ruta(self, puede):
        """Un cuadro de la ruta forzada. `puede(direccion)` dice si se puede dar
        el paso; devuelve la dirección del paso que se está dando, o None.

        Girar no consume cuadro y se sigue con el comando siguiente; esperar sí;
        y moverse arranca un paso de una celda, que dura CUADROS_POR_CELDA.
        """
        if self.paso_cuadros:
            self.paso_cuadros -= 1
            self.cuadros_moviendose += 1
            direccion = self.paso_dir
            if not self.paso_cuadros:
                self.paso_dir = None
            return direccion
        while self.ruta:
            orden = self.ruta.pop(0)
            if orden in RUTA_MIRAR:
                self.mirando = RUTA_MIRAR[orden]
                continue
            if orden == RUTA_ESPERAR:
                return None
            direccion = RUTA_MOVER[orden]
            self.mirando = direccion
            if not puede(direccion):
                continue            # bloqueado: se saltea
            self.paso_dir = direccion
            self.paso_cuadros = CUADROS_POR_CELDA - 1
            self.cuadros_moviendose += 1
            return direccion
        self.cuadros_moviendose = 0
        return None

    def encendido(self, numero):
        return numero in self.switches

    def cambiar_grupo(self, operacion, actor):
        """Agrega o saca un actor, con las reglas de RM2k.

        Agregar uno que ya está no lo duplica y no lo mueve de lugar, agregar
        con el grupo lleno no hace nada, y sacar uno que no está tampoco: es lo
        que hace `Game_Party::AddActor`/`RemoveActor` en easyrpg-player, que
        además llama a `ResetGraphic` en los dos casos. Importa porque el orden
        decide quién es el líder, o sea qué sprite se dibuja.
        """
        if operacion == GRUPO_SACAR:
            if actor in self.grupo:
                self.grupo.remove(actor)
        elif actor not in self.grupo and len(self.grupo) < GRUPO_MAX:
            self.grupo.append(actor)

    def lider(self):
        return self.grupo[0] if self.grupo else None


def pagina_activa(paginas, evento, estado):
    """La página de número más alto del evento cuyas condiciones se cumplen.

    Es la regla de RM2k, y es la misma pasada que hace la ROM.
    """
    elegida = None
    for pagina in paginas:
        if pagina["evento"] != evento:
            continue
        if pagina["switch_a"] and not estado.encendido(pagina["switch_a"]):
            continue
        if pagina["switch_b"] and not estado.encendido(pagina["switch_b"]):
            continue
        if pagina["actor"] and pagina["actor"] not in estado.grupo:
            continue
        elegida = pagina
    return elegida


def pagina_de_prueba(espera=0, tinte=(), ruta=()):
    """Una página automática inventada: una ruta forzada, una espera, un tinte.

    No sale de ningún dato del juego, y ésa es la idea. El intérprete corre
    cuadro a cuadro desde que dejó de colapsar el tiempo, pero **ninguna página
    del juego que compile tiene una espera**, así que ese camino —el corazón del
    cambio— no lo ejercitaba nada. Es el mismo caso que `snes-encima`, que
    existe porque ningún evento del juego llega a la prioridad 2.

    Lo sintético es la entrada, no la comparación: los dos lados corren este
    bytecode y se comparan como siempre, la ROM contra la referencia. Y es una
    prueba filosa por construcción: antes del cuadro N la pantalla está sin
    teñir y después está teñida, así que si la ROM y la referencia no cuentan
    los mismos cuadros, se ve.

    La escribe el conversor con `--pagina-de-prueba` y la corre la referencia
    con la misma función, que es lo que garantiza que sea el mismo programa.
    """
    codigo = b""
    if ruta:
        codigo += bytes([OP_RUTA, len(ruta)]) + bytes(ruta)
    if espera:
        codigo += bytes([OP_ESPERAR, espera & 0xFF, espera >> 8])
    if tinte:
        codigo += bytes([OP_TINTE]) + bytes(tinte) + bytes([TINTE_NEUTRO])
    return codigo + bytes([OP_FIN])


class Interprete:
    """El intérprete corriendo, con su cursor y su espera, cuadro a cuadro.

    Antes esto era una sola pasada: la página entera se ejecutaba de golpe, con
    la pantalla apagada mientras se cargaba el mapa, y las esperas se salteaban.
    Eso colapsaba el tiempo. Todo lo que en RM2k pasa *durante* una página —una
    espera de seis segundos, un NPC caminando su ruta, un fundido— no existía:
    quedaba nada más el estado final. Y como el 46% de las páginas automáticas
    del juego terminan en un teletransporte, lo que ocurría antes del salto era
    además imposible de verificar, porque el cuadro que se compara ya está en el
    mapa de destino.

    Ahora avanza un cuadro por vuelta, igual que `eventos_tick` en la ROM:
    ejecuta opcodes hasta toparse con una espera o con un teletransporte, y ahí
    devuelve el control.
    """

    def __init__(self, paginas, estado):
        self.estado = estado
        # Las páginas elegidas, en el orden en que la ROM recorre los eventos.
        self.cola = []
        for evento in sorted({p["evento"] for p in paginas}):
            pagina = pagina_activa(paginas, evento, estado)
            if (pagina is not None
                    and pagina["trigger"] == TRIGGER_AUTOMATICO
                    and pagina["codigo"]):
                self.cola.append(pagina["codigo"])
        self.codigo = None
        self.cursor = 0
        self.esperando = 0

    @property
    def terminado(self):
        return self.codigo is None and not self.cola

    def cuadro(self):
        """Avanza un cuadro. Devuelve True si en éste se pidió un salto."""
        if self.esperando:
            self.esperando -= 1
            return False
        while True:
            if self.codigo is None:
                if not self.cola:
                    return False
                self.codigo, self.cursor = self.cola.pop(0), 0
            corte = ejecutar(self.codigo, self.estado, self.cursor)
            if corte is None:               # la página terminó
                self.codigo = None
                continue
            self.cursor, self.esperando, salto = corte
            return salto


def correr_automaticos(paginas, estado, cuadros=100000):
    """Corre las páginas automáticas del mapa hasta que pidan un salto.

    Atajo para quien no necesita mirar el tiempo: adelanta cuadros hasta que el
    intérprete pida mudarse o se quede sin páginas. Lo que sí mira el tiempo
    —la referencia de la pantalla— usa `Interprete` directamente.

    El salto pendiente se borra al entrar, que es el `stz salto_hay` de la ROM:
    sin eso, el primer mapa que teletransporta dejaría el salto puesto y el
    mapa de destino saldría saltando de nuevo al mismo lado sin haber corrido
    ningún evento.
    """
    estado.salto = None
    interprete = Interprete(paginas, estado)
    for _ in range(cuadros):
        if interprete.cuadro():
            return estado.salto
        if interprete.terminado:
            break
    return None


def ejecutar(codigo, estado, desde=0):
    """Corre la página desde `desde` hasta toparse con una espera o el final.

    Devuelve None si la página terminó, o (cursor, cuadros_a_esperar, salto) si
    hay que devolver el control. Igual que `correr_codigo` en la ROM, que ahora
    también vuelve con el cursor guardado en vez de correr la página entera.
    """
    i = desde
    while i < len(codigo):
        op = codigo[i]
        if op == OP_FIN:
            return None
        if op == OP_SWITCH:
            numero = codigo[i + 1] | (codigo[i + 2] << 8)
            if codigo[i + 3]:
                estado.switches.add(numero)
            else:
                estado.switches.discard(numero)
            i += 4
        elif op == OP_TELEPORT:
            # El resto de la página sí corre. En
            # `Game_Interpreter_Map::CommandTeleport` el motor reserva el
            # teletransporte, hace `index++` y devuelve false: corta el cuadro,
            # pero retoma en el comando siguiente una vez cambiado el mapa. Acá
            # la página corre entera de una, así que seguir es lo mismo que
            # retomar, y con dos teletransportes gana el último —que es también
            # dónde RM2k deja al héroe—.
            #
            # Lo que este modelo no hace es correr los eventos automáticos del
            # mapa intermedio, que RM2k sí correría entre un teletransporte y el
            # siguiente. En la cinemática de apertura los dos van al mismo mapa,
            # así que no cambia nada; si alguna vez aparece una página que salte
            # entre mapas distintos, esto hay que mirarlo de nuevo.
            estado.salto = (codigo[i + 1],
                            codigo[i + 2] | (codigo[i + 3] << 8),
                            codigo[i + 4] | (codigo[i + 5] << 8))
            return (i + 6, 0, True)     # corta el cuadro, como `return false`
        elif op == OP_ESPERAR:
            # Y acá se devuelve el control. Antes se salteaba: "no tenemos
            # cuadros que dejar pasar", decía el comentario, y era cierto
            # mientras la página corriera entera con la pantalla apagada.
            cuadros = codigo[i + 1] | (codigo[i + 2] << 8)
            return (i + 3, cuadros, False)
        elif op == OP_RUTA:
            # La ruta se encola y la camina el héroe, no el intérprete: en RM2k
            # `ForceMoveRoute` es asincrónico y la página sigue. Quien la hace
            # avanzar es `Estado.cuadro_de_ruta`, una vez por cuadro.
            cuantos = codigo[i + 1]
            estado.ruta = list(codigo[i + 2:i + 2 + cuantos])
            i += 2 + cuantos
        elif op == OP_GRUPO:
            estado.cambiar_grupo(codigo[i + 1], codigo[i + 2])
            i += 3
        elif op == OP_TINTE:
            estado.tinte = (codigo[i + 1], codigo[i + 2], codigo[i + 3])
            i += 5
        else:
            raise ValueError("opcode %d que no conozco" % op)
    return None


def tenir(palabra, tinte):
    """Un color de 15 bits escalado por el tinte.

    La misma cuenta con enteros que hace la consola con sus unidades de
    multiplicación y división: `canal * valor / 100`, truncado, topado en 31.
    Si acá se hiciera con flotantes o con corrimientos, la comparación pixel a
    pixel fallaría por el redondeo.
    """
    canales = (palabra & 0x1F, (palabra >> 5) & 0x1F, (palabra >> 10) & 0x1F)
    salida = 0
    for numero, (canal, valor) in enumerate(zip(canales, tinte)):
        salida |= min(31, canal * valor // 100) << (numero * 5)
    return salida


def deudas_de_la_pagina(page):
    """Qué comandos de esta página se aceptan sin hacerlos.

    Para que el conversor pueda avisar en vez de que la deuda quede muda.
    """
    return sorted({cmd.code for cmd in page.commands
                   if cmd.code in ACEPTADOS_SIN_HACER})


def paginas_del_mapa(game_map, indice_de_mapa):
    """Las páginas que la ROM necesita para resolver los eventos automáticos.

    Se emiten *todas* las páginas de un evento que tenga alguna automática, no
    sólo las automáticas: cuál queda activa depende de las condiciones de todas
    ellas, y una página posterior que no sea automática igual gana y le impide
    correr a la de más abajo.
    """
    salida = []
    for numero_evento, event in enumerate(game_map.events):
        if not any(page.trigger == TRIGGER_AUTOMATICO for page in event.pages):
            continue

        # Si alguna página del evento pide una condición que la ROM no sabe
        # evaluar —un ítem, un héroe en el grupo, un cronómetro— entonces no se
        # sabe cuál página está activa, y correr la equivocada es peor que no
        # correr ninguna. El evento entero queda afuera.
        if any(c not in ("switch_a", "switch_b", "actor")
               for page in event.pages for c in page.condition.active):
            continue

        grupo = []
        for numero_pagina, page in enumerate(event.pages):
            cond = page.condition
            codigo = None
            if page.trigger == TRIGGER_AUTOMATICO:
                codigo = compilar_pagina(page, indice_de_mapa)
            grupo.append({
                "evento": numero_evento,
                "pagina": numero_pagina,
                "trigger": page.trigger,
                "switch_a": cond.ids["switch_a"] if "switch_a" in cond.active else 0,
                "switch_b": cond.ids["switch_b"] if "switch_b" in cond.active else 0,
                "actor": cond.ids["actor"] if "actor" in cond.active else 0,
                "codigo": codigo,
            })

        # Un evento cuyas páginas automáticas no se pueden compilar no aporta
        # nada: sin código no hay nada que ejecutar y sólo ocuparía tabla.
        if any(p["codigo"] for p in grupo):
            salida += grupo
    return salida
