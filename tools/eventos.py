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

# Un cuadro de texto. RM2k emite un `ShowMessage` con la primera línea y un
# `ShowMessage_2` por cada una de las que siguen del mismo cuadro: son un solo
# comando —una ventana, una espera del jugador— y quien los cuente por separado
# mide cualquier cosa. Ya pasó: contándolos aparte, los cuadros de texto
# parecían destrabar tres páginas en vez de cincuenta y cinco.
SHOW_MESSAGE = 10110
SHOW_MESSAGE_2 = 20110

# Los códigos de escape que el texto de este juego usa: `\|` es una pausa de un
# segundo y `\^` cierra el cuadro sin esperar a que el jugador apriete nada.
# Los dos son tiempo, no texto, y no los hacemos.
#
# Una página que los use no compila, y eso es a propósito. Dibujarlos como dos
# letras se vería —son 35 líneas del juego—, y borrarlos calladito sería peor:
# con `\^` el cuadro se cierra solo, así que la ROM quedaría esperando un A que
# RM2k nunca pidió y la página entera pasaría a durar lo que tarde el jugador.
# Son 17 páginas de las 279 con texto; cuando el compositor sepa pausar y
# autocerrar, esto se cae solo.
ESCAPE = "\\"

# Una ruta forzada de MoveEvent. Los parámetros son (a quién, frecuencia, un
# bitmask de repetición, si es salteable) y de ahí en adelante los comandos de
# la ruta, con los códigos de `rpg::MoveCommand::Code` de liblcf.
#
# Se aceptan los cuatro de girar, los cuatro de mover y la espera. Los de mover
# entraron últimos porque en RM2k el personaje camina celda por celda a lo largo
# de varios cuadros, y eso hay que compararlo *mientras* camina: comparar sólo
# dónde termina deja pasar el ciclo de animación entero. Un movimiento bloqueado
# se saltea, que es la decisión de modelo que comparten los dos lados —RM2k
# reintentaría para siempre y una prueba colgada no dice nada—.
RUTA_HEROE = 10001
RUTA_ESTE_EVENTO = 10005                    # "este evento", el dueño de la página
RUTA_VEHICULOS = (10002, 10003, 10004)      # barco, nave, avión: no existen acá
RUTA_MIRAR = {12: 0, 13: 1, 14: 2, 15: 3}   # face_up/right/down/left
RUTA_MOVER = {0: 0, 1: 1, 2: 2, 3: 3}       # move_up/right/down/left
RUTA_ESPERAR = 23

# Cuánto cuesta un `wait` adentro de una ruta forzada. **No es un cuadro**: en
# RM2k es `SetMaxStopCountForWait`, que da `20 + (1 << (8 - frecuencia))`, y con
# la frecuencia 8 —la única que este repo acepta, ver `RUTA_FRECUENCIA`— son
# veinte. Acá valía uno, en la ROM y en la referencia a la vez, así que la
# comparación daba cero: es el mismo error que el hard light del tinte.
CUADROS_DE_ESPERA_DE_RUTA = 20

# La frecuencia con la que se camina una ruta forzada. Manda dos cosas: cuánto
# se espera entre una orden y la siguiente —`1 << (9 - frecuencia)` cuadros, y
# cero con 8— y cuánto dura un `wait`. Sólo se acepta la 8, que es la que usan
# 3463 de las 3509 rutas del juego y **todas** las de las páginas que compilan;
# con cualquier otra habría que modelar la espera entre órdenes, que hoy no
# está. Rechazarla no cuesta ninguna página y saca del medio un error que la
# comparación no vería.
RUTA_FRECUENCIA = 8

# Girar sin moverse —`turn_90_degree_right` y sus hermanas— y encarar al héroe
# **no están**, y no por costo: por dónde arranca el giro. RM2k gira sobre la
# dirección que el personaje ya tenía, y para un evento eso es la que trae su
# página; acá la ruta no la conoce hasta que la gira ella misma, así que el
# primer giro de una ruta partiría de otro lado en la ROM y en la referencia.
# Son tres páginas medidas, y entran cuando el mirado inicial de un evento salga
# de su página en los dos lados en vez del centinela que hay hoy.

# El salto: lo que hay entre las dos se suma como desplazamiento y el personaje
# lo hace de un tirón, en arco.
RUTA_SALTO_INICIO, RUTA_SALTO_FIN = 24, 25

# Atravesar paredes, y parar o seguir la animación de caminata.
RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF = 36, 37
RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR = 38, 39

# El sonido va adentro de la ruta y se acepta sin hacerlo, igual que PlaySound:
# no se ve. Se tira al compilar, así que el bytecode sigue siendo un byte por
# orden y no cuesta ni un cuadro, que es lo que hace RM2k —no toca el contador
# de parada—.
RUTA_SONIDO_SE_TIRA = True

# Un salto dura lo que tarda `remaining_step` en bajar de 256 a 0 a
# `jump_speed[move_speed - 1]` por cuadro. Con la velocidad 4 —la de este
# juego— son 24 por cuadro, o sea once cuadros, y **no depende de la
# distancia**: saltar cinco celdas cuesta lo mismo que saltar en el lugar.
SALTO_PASO = 256
SALTO_VELOCIDAD = 24

# Qué celda es "la de al lado" en cada dirección. Vive acá y no en quien camina
# porque ahora camina más de uno: el héroe y los eventos con ruta forzada.
RUTA_PASOS = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0)}

# Las órdenes de ruta que sabemos caminar, en un solo lugar. `destraba.py` mide
# con esta misma lista, así que el día que aprenda una más el número sube solo.
RUTA_ORDENES = (set(RUTA_MIRAR) | set(RUTA_MOVER)
                | {RUTA_ESPERAR, RUTA_SALTO_INICIO, RUTA_SALTO_FIN,
                   RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF,
                   RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR})

# Las órdenes que llevan algo detrás, y qué. Los números son los de
# `rpg::MoveCommand::Code` en liblcf.
RUTA_SWITCH_ON, RUTA_SWITCH_OFF = 32, 33
RUTA_CAMBIAR_GRAFICO = 34
RUTA_SONIDO = 35


def decodificar_ruta(parametros):
    """Las órdenes de una ruta forzada, con lo que cada una arrastre.

    Devuelve una lista de `(codigo, extras)`. Hace falta porque **la ruta no es
    una lista de códigos**: tres órdenes traen operandos metidos en el mismo
    chorro de enteros, y dos de ellas un texto —el nombre del CharSet, el del
    sonido— con un entero por letra. Recorrerla plana funcionaba mientras la
    primera orden desconocida cortara todo; en cuanto una de ésas se acepta, las
    letras del texto se leerían como órdenes.

    Los enteros vienen en el formato de RM2k: siete bits por entero y el bit 7
    dice que sigue. Es `Game_Interpreter_Shared::DecodeMove` y `DecodeInt`.

    Quedarse sin datos en el medio de un operando es una ruta rota y no
    compila; quedarse sin datos entre una orden y la siguiente es el final
    normal. La diferencia importa: confundirlas dejaba afuera 258 páginas que
    están perfectamente bien.
    """
    ordenes = []
    i = 0
    n = len(parametros)

    def entero():
        nonlocal i
        valor = 0
        while True:
            if i >= n:
                raise NoSePuede()
            x = parametros[i]
            i += 1
            valor = (valor << 7) | (x & 0x7F)
            if not x & 0x80:
                return valor

    def texto():
        nonlocal i
        largo = entero()
        if i + largo > n:
            raise NoSePuede()
        letras = "".join(chr(c & 0xFF) for c in parametros[i:i + largo])
        i += largo
        return letras

    while i < n:
        codigo = parametros[i]
        i += 1
        if codigo in (RUTA_SWITCH_ON, RUTA_SWITCH_OFF):
            extras = [entero()]
        elif codigo == RUTA_CAMBIAR_GRAFICO:
            extras = [texto(), entero()]
        elif codigo == RUTA_SONIDO:
            extras = [texto(), entero(), entero(), entero()]
        else:
            extras = []
        ordenes.append((codigo, extras))
    return ordenes

# "Esperá a que terminen las rutas". En RM2k espera a que **ninguna** quede
# pendiente, ni la del héroe ni la de ningún evento: es
# `Game_Map::IsAnyMovePending` en `Game_Interpreter::Update`, y no una espera
# por el evento que se acaba de mandar a caminar.
PROCEED_WITH_MOVEMENT = 11340

# Un destello sobre un personaje: `Game_Character::Flash`. Los parámetros son a
# quién, r, g y b de 0 a 31, la potencia, cuántas **décimas de segundo** dura, y
# si la página espera a que termine.
#
# Lo de las décimas no es un detalle: `CommandFlashSprite` hace
# `event->Flash(r, g, b, p, tenths * DEFAULT_FPS / 10)` y, si espera,
# `SetupWait(tenths)`, que es la misma espera del comando Wait. O sea que el
# tiempo sale gratis: es un OP_ESPERAR detrás.
FLASH_SPRITE = 11320

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
# WeatherEffects prende o apaga la lluvia. Se acepta sin dibujarla, y la deuda
# es de las grandes, así que va con todas las letras.
#
# **En modo 3 no queda capa donde ponerla.** BG1 son los ocho bits del mapa y
# BG2 la capa de encima más la ventana de mensaje; no hay una tercera. Con
# objetos tampoco: la lluvia de RM2k son hasta 100 hilos de 6x24 repartidos por
# toda la pantalla, y la consola dibuja 34 tiles de sprite por línea —un objeto
# de 32x32 se lleva cuatro—, así que una lluvia que cubra la pantalla revienta
# el presupuesto en casi todas las líneas. Nuestra propia referencia marca esas
# líneas como no comparables, así que la prueba dejaría de medir justo ahí.
#
# Y aunque entrara: cada gota va con su propia transparencia —`alpha = min((5 +
# fuerza) * t, 255)` en `Weather::DrawParticles`— y la consola tiene una sola
# operación de color para toda la pantalla, no una por objeto. Las posiciones
# además salen de un generador de números al azar que habría que reproducir.
#
# Lo que se pierde, medido sobre una captura de EasyRPG de la apertura: hilos
# diagonales finos de 24 pixeles de alto, que entre dos cuadros seguidos mueven
# el 3,9% de la pantalla. Se ven sobre todo en las zonas oscuras.
#
# Se acepta porque **es lo único que traba la cinemática de apertura**, que es
# la puerta a los primeros diez minutos del juego. Sin esto la ROM no arranca la
# historia; con esto arranca, sin lluvia.
WEATHER_EFFECTS = 11070

# PlaySound toca un efecto: una puerta, un golpe, el Insta-Shave de Talan. Se
# acepta sin tocarlo, y es la deuda más barata de todas las que hay acá: **no se
# ve**. La pantalla que se compara es exactamente la misma con y sin sonido, y
# el audio que sí se compara —`snes-check`, contra el MIDI del mapa— tampoco
# cambia, porque el tema de fondo sigue sonando igual.
#
# Lo que costaría hacerlo: la ROM sube **un solo banco de muestras** al SPC700 al
# arrancar, y son las del tema del mapa. Un efecto pide muestras más en el
# cartucho y subirlas en caliente, que es la misma feature de audio que bloquea
# a PlayBGM. Este juego usa 116 efectos distintos.
#
# Cuánto destraba, medido y no supuesto: **+10 páginas de tecla de acción y +6
# automáticas**. Es mucho menos de lo que parece: `PlaySound` es el comando que
# corta *primero* en 349 páginas, pero casi todas están cortadas además por otra
# cosa. Es exactamente la trampa que la tabla de orden de `rom/LEEME.md` ya tiene
# anotada, y vale la pena que quede escrita también acá.
#
# Lo que sí destraba es concreto: el Insta-Shave del pad de Talan toca cuatro
# efectos antes de su mensaje, así que sin esto esa rama no corre.
PLAY_SOUND = 11550

ACEPTADOS_SIN_HACER = {
    PLAY_BGM,
    WEATHER_EFFECTS,
    PLAY_SOUND,
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
OP_RUTA     = 0x06      # blanco (byte), cuántos comandos (byte), y los
                        # comandos. El blanco es 0 para el héroe, y si no el
                        # índice del evento en la tabla del mapa más uno.
                        #
                        # **El índice no es el id de RM2k.** 39 mapas de este
                        # juego tienen huecos en la numeración de eventos, así
                        # que una ruta apuntada al id 8 movería al que esté
                        # octavo en la lista, que puede ser cualquier otro. Lo
                        # traduce el conversor, que es el único que ve el mapa.
OP_MENSAJE  = 0x07      # desplazamiento (word) dentro del bloque `mensajes`:
                        # abre esa ventana y bloquea la página hasta que el
                        # jugador apriete A
OP_RUTAS    = 0x08      # sin operandos: la página no sigue hasta que no quede
                        # ninguna ruta forzada corriendo
OP_FLASH    = 0x09      # blanco (byte), r, g, b, potencia (byte cada uno, de 0
                        # a 31) y cuántos cuadros dura (byte)
OP_TIMER    = 0x0A      # operación (byte), segundos (word), visible (byte).
                        # Los cinco bytes son fijos aunque cada operación use
                        # dos: así el intérprete lo saltea sin mirar cuál es,
                        # que es lo que hace `recorrer_codigo` del conversor.

# El operando es un desplazamiento y no un texto, y eso es lo que hace que
# entre. Una página de mensaje ya compuesta son ~240 tiles de 4bpp, o sea
# 7,5 KB, y emitir una por cada cuadro de texto del juego no entra ni cerca en
# un cartucho de 256 KB: los 2895 cuadros serían 21 MB. Lo que se emite es el
# texto —un byte por letra— y lo compone el 65816 en caliente, con la fuente en
# la ROM, que es la salida de FF6. Los mismos 2895 cuadros son 180 KB de texto,
# y un mapa solo bastante menos.
#
# Dieciséis bits alcanzan porque el bloque tiene que entrar en un banco de
# 32 KB: lo lee `lda [msg_ptr], y` con un puntero que se incrementa de a un
# byte y **no** arrastra al byte de banco, así que `bloque()` lo emite con
# `.bloque`, que rellena para que no cruce. Si algún día no entra, lo que hay
# que agrandar es el puntero, no el operando.

# TimerOperation. Los parámetros son (operación, de dónde salen los segundos,
# segundos, visible, en batalla): liblcf, TimerOperation::Operation.
TIMER_OPERATION = 10230
TIMER_PONER, TIMER_ARRANCAR, TIMER_PARAR = 0, 1, 2
TIMER_SEGUNDOS_FIJOS = 0        # el otro valor los saca de una variable
# `Game_Party::SetTimer` guarda `segundos * 60 + 59`, no `segundos * 60`. Los
# 59 de más son lo que hace que el primer segundo se vea entero: sin ellos el
# cronómetro mostraría el valor pedido durante un solo cuadro.
TIMER_CUADROS_DE_MAS = 59

# ControlSwitches: el primer parámetro dice de dónde salen los ids y el último
# qué hacer con ellos (liblcf, ControlSwitches::Operation).
SWITCH_UNICO, SWITCH_RANGO, SWITCH_INDIRECTO = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

# Un rango absurdo no se desenrolla: mejor no ejecutar la página que emitir
# miles de opcodes por una línea.
MAX_RANGO = 64

# RM2k mide las esperas en décimas de segundo.
CUADROS_POR_DECIMA = 6
CUADROS_POR_SEGUNDO = 60        # DEFAULT_FPS: es con lo que cuenta el cronómetro

# Un paso son dieciséis pixeles a WALK_SPEED = 2 por cuadro.
CELDA_PX = 16
WALK_SPEED = 2
CUADROS_POR_CELDA = CELDA_PX // WALK_SPEED

# Qué dispara una página. Los de `rpg::EventPage::Trigger` de liblcf.
TRIGGER_ACCION = 0          # el jugador aprieta la tecla de acción enfrente
TRIGGER_TOCA_HEROE = 1      # el héroe camina encima
TRIGGER_TOCA_EVENTO = 2
TRIGGER_AUTOMATICO = 3
TRIGGER_PARALELO = 4

# Los que la ROM sabe disparar. El resto de las páginas de un evento se emiten
# igual —hacen falta para saber cuál está activa— pero sin código.
TRIGGERS = (TRIGGER_ACCION, TRIGGER_TOCA_HEROE, TRIGGER_AUTOMATICO)

# Un evento con gráfico **gira hacia el héroe** cuando le hablás, salvo que
# tenga la dirección fija: es el `SetFacing(GetDirectionToCharacter(GetPlayer()))`
# de `Game_Event::ScheduleForegroundExecution`. Eso se ve, y pide sus cuatro
# poses paradas en la VRAM, así que por ahora esas páginas no compilan.
#
# No es un recorte grande, y está medido: de las 1006 páginas de tecla de acción
# que compilarían, 474 son sobre eventos sin gráfico y 394 más sobre eventos con
# la dirección fija, que tampoco giran. Quedan 138 afuera.
#
# Los tipos de animación con la dirección fija son los `fixed_*` de
# `rpg::EventPage::AnimType`, más `spin`, que gira solo y tampoco obedece.
ANIM_FIJAS = (2, 3, 4, 5)

# Sólo los eventos que están en la capa del héroe se disparan con la tecla de
# acción: es el `GetLayer() == Layers_same` de `CheckEventTriggerThere`.
LAYER_MISMA = 1

# El tinte de RM2k va de 0 a 200 con 100 como neutro. En la ROM se guarda tal
# cual y se aplica al subir la paleta.
TINTE_NEUTRO = 100


class NoSePuede(Exception):
    """Esta página tiene algo que la ROM todavía no sabe hacer."""


class Eventos:
    """Los eventos del mapa, como los ve el compilador.

    Existe por una razón que se midió y que si no se paga cara: **el id de
    evento de RM2k no es el índice de la tabla de la ROM**. 39 mapas de este
    juego tienen huecos en la numeración —eventos borrados en el editor— así
    que una ruta apuntada al id 8 movería al que esté octavo en la lista, que
    puede ser cualquier otro. La traducción se hace acá, una sola vez, y el
    bytecode no vuelve a ver un id de RM2k.

    `mio` es el evento dueño de la página que se está compilando, que es a
    quién apunta "este evento".
    """

    def __init__(self, game_map, mio=None):
        self.indices = {ev.id: n for n, ev in enumerate(game_map.events)}
        # Visible es tener gráfico en la página activa, que es la misma regla
        # que usa `collect_npcs` para decidir qué entra en la tabla de la ROM.
        self.visibles = {ev.id for ev in game_map.events
                         if ev.active_page() is not None
                         and ev.active_page().character_name}
        # Con qué personaje se dibuja cada uno, para saber cuáles comparten
        # paleta. En la consola el destello se hace sobre la paleta del
        # personaje, así que dos eventos con el mismo gráfico destellarían
        # juntos: ver `_compilar`.
        self.grafico = {}
        for ev in game_map.events:
            page = ev.active_page()
            if page is not None and page.character_name:
                self.grafico[ev.id] = (page.character_name,
                                       page.character_index)
        self.mio = mio

    def comparte_grafico(self, quien):
        """Si este evento dibuja con el mismo personaje que otro del mapa."""
        cual = self.grafico.get(quien)
        return cual is not None and sum(1 for g in self.grafico.values()
                                        if g == cual) > 1

    def para(self, id_evento):
        otro = Eventos.__new__(Eventos)
        otro.indices, otro.visibles = self.indices, self.visibles
        otro.grafico, otro.mio = self.grafico, id_evento
        return otro

    def blanco(self, quien):
        """El byte de blanco que va en OP_RUTA, o None si no se puede mover.

        0 es el héroe; para un evento, su índice más uno. Los vehículos no
        existen en esta ROM y un id que el mapa no tiene tampoco: los dos
        devuelven None, que corta la página.
        """
        if quien == RUTA_HEROE:
            return 0
        if quien == RUTA_ESTE_EVENTO:
            quien = self.mio
        if quien in self.indices:
            return self.indices[quien] + 1
        return None


class Mensajes:
    """El bloque de textos de la ROM, y el desplazamiento de cada cuadro.

    Es de la ROM entera y no del mapa: `OP_MENSAJE` lleva un desplazamiento
    dentro de este bloque, así que todos los mapas comparten la numeración y el
    conversor lo emite una sola vez. Lo repetido se guarda una sola vez —el
    juego repite cuadros enteros, y son 418 de 2895— y sale gratis porque el
    contenido ya es la clave.

    **Los dos lados lo arman en el mismo orden.** El conversor para emitirlo y
    la referencia para saber qué texto dibujar cuando el bytecode abra un
    mensaje; si se juntaran en otro orden, el mismo desplazamiento nombraría
    otro texto y la comparación mediría dos juegos distintos. Por eso la
    referencia compila todos los mapas de la tabla al construirse, en vez de
    hacerlo cuando el héroe pisa cada uno.
    """

    def __init__(self):
        self.datos = bytearray()
        self.donde = {}         # las líneas ya guardadas -> su desplazamiento
        self.textos = {}        # y la vuelta, que es lo que usa la referencia

    def agregar(self, lineas):
        """El desplazamiento de este cuadro, guardándolo si es la primera vez.

        El recorte a lo que entra en un renglón se hace **acá**, antes de
        deduplicar: dos textos que sólo difieran en lo que se corta son el
        mismo cuadro en pantalla, y darles dos desplazamientos distintos sería
        emitir dos veces los mismos bytes.
        """
        import ventana as ventana_mod
        lineas = tuple(t[:ventana_mod.COLUMNAS]
                       for t in list(lineas)[:ventana_mod.LINEAS])
        if lineas not in self.donde:
            donde = len(self.datos)
            self.datos += mensaje_bytes(lineas)
            if len(self.datos) > 0x10000:
                raise SystemExit(
                    "los mensajes de esta ROM son %d bytes y el operando de "
                    "OP_MENSAJE es de 16 bits" % len(self.datos))
            self.donde[lineas] = donde
            self.textos[donde] = lineas
        return self.donde[lineas]

    def lineas(self, donde):
        """Las líneas que hay en ese desplazamiento. Es lo que dibuja la
        referencia: la ROM lee los mismos bytes del cartucho."""
        return self.textos[donde]

    def marca(self):
        return len(self.datos)

    def volver(self, marca):
        """Deshace lo agregado desde `marca`.

        Hace falta porque una página se compila comando por comando y puede
        cortarse en el último: sin esto, el texto de todas las páginas que **no**
        compilan quedaría igual en el cartucho. No es una micro-optimización,
        son los 161 KB del juego entero contra los pocos que hacen falta.
        """
        del self.datos[marca:]
        self.donde = {k: v for k, v in self.donde.items() if v < marca}
        self.textos = {k: v for k, v in self.textos.items() if k < marca}

    def bytes(self):
        # Nunca vacío: el ensamblador necesita la etiqueta resuelta aunque la
        # ROM no vaya a leerla.
        return bytes(self.datos) or b"\x00"


def mensaje_bytes(lineas):
    """Un cuadro de texto como lo lee la ROM: cuántas líneas, y cada una con su
    largo.

    Los caracteres van como índice en la tabla de la fuente, o sea el ASCII
    menos 32. Todo el texto de este juego entra ahí: se midió, y no tiene una
    sola letra acentuada.
    """
    import ventana as ventana_mod
    out = bytearray([min(len(lineas), ventana_mod.LINEAS)])
    for texto in list(lineas)[:ventana_mod.LINEAS]:
        texto = texto[:ventana_mod.COLUMNAS]
        out.append(len(texto))
        for ch in texto:
            if not 32 <= ord(ch) < 127:
                raise SystemExit("el mensaje tiene un caracter que no está en "
                                 "la fuente: %r" % ch)
            out.append(ord(ch) - 32)
    return bytes(out)


def agrupar(comandos):
    """Los comandos de a uno, salvo los cuadros de texto.

    Devuelve (comando, líneas de más), donde las de más son los
    `ShowMessage_2` que siguen a un `ShowMessage` y son parte del mismo cuadro.
    Un `ShowMessage_2` suelto se devuelve solo y no compila, que es lo correcto:
    sería una línea sin ventana donde ponerla.

    Lo usan los dos que filtran páginas —`compilar_pagina` y `destraba.py`—
    porque el agrupado es parte del filtro, no del emisor: contar los comandos
    por separado es lo que hizo medir mal cuánto destrababa hacer los cuadros
    de texto.
    """
    comandos = list(comandos)
    i = 0
    while i < len(comandos):
        j = i + 1
        if comandos[i].code == SHOW_MESSAGE:
            while j < len(comandos) and comandos[j].code == SHOW_MESSAGE_2:
                j += 1
        yield comandos[i], [c.string for c in comandos[i + 1:j]]
        i = j


def puede_dispararse(page):
    """Si la ROM sabe disparar esta página, aparte de si sus comandos compilan.

    Las dos reglas de capa salen de `Game_Player`, y son opuestas a propósito:

    * **Tecla de acción**: se mira la celda de adelante, y ahí sólo cuentan los
      eventos de la capa del héroe —`CheckEventTriggerThere` pide
      `GetLayer() == Layers_same`—. Un evento de acción en la celda **propia**
      sí existe en RM2k, pero pide la capa contraria —`CheckEventTriggerHere`
      pide `!= Layers_same`— y ésos no los hacemos.
    * **Contacto**: se dispara al pisar la celda, y ahí es al revés: la capa
      tiene que ser distinta de la del héroe, porque un evento de su misma capa
      le bloquea el paso y nunca llegaría a pisarlo. De las 983 páginas de
      contacto del juego, 978 son de la capa de abajo.

    Y una de tecla de acción no puede tener que girar hacia el héroe, que es lo
    que todavía no se dibuja.
    """
    if page.trigger == TRIGGER_ACCION:
        if page.layer != LAYER_MISMA:
            return False
        return not page.character_name or page.animation_type in ANIM_FIJAS
    if page.trigger == TRIGGER_TOCA_HEROE:
        return page.layer != LAYER_MISMA
    return True


def compilar_pagina(page, indice_de_mapa, mensajes=None, eventos_mapa=None):
    """Los comandos de una página como bytes, o None si no se puede.

    `indice_de_mapa` traduce el id de mapa de RM2k al índice en la tabla de la
    ROM, y devuelve None para los mapas que no entraron en el cartucho: un
    teletransporte hacia uno de ésos hace que la página no sea ejecutable, que
    es más honesto que saltar a cualquier lado.

    `mensajes` es el bloque de textos de la ROM. Sin él los cuadros de texto no
    compilan, y no es una opción de gusto: la ventana ocupa 8 KB de VRAM y una
    paleta, así que una ROM que no la lleve no tiene dónde dibujarlos.

    `eventos_mapa` es el `Eventos` del mapa, ya apuntado al dueño de la página.
    Sin él una ruta forzada sólo puede ser sobre el héroe: no hay con qué
    traducir el id de RM2k al índice de la tabla.
    """
    marca = mensajes.marca() if mensajes is not None else None
    try:
        codigo = b"".join(_compilar(cmd, indice_de_mapa, mensajes, extra,
                                    eventos_mapa)
                          for cmd, extra in agrupar(page.commands)) \
            + bytes([OP_FIN])
        return codigo
    except NoSePuede:
        if mensajes is not None:
            mensajes.volver(marca)
        return None


def _compilar(cmd, indice_de_mapa, mensajes=None, extra=(),
              eventos_mapa=None):
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

    if cmd.code == PROCEED_WITH_MOVEMENT:
        return bytes([OP_RUTAS])

    if cmd.code == FLASH_SPRITE:
        if len(p) < 7:
            raise NoSePuede()
        if p[0] == RUTA_HEROE:
            blanco = 0
        elif eventos_mapa is None:
            raise NoSePuede()
        else:
            blanco = eventos_mapa.blanco(p[0])
            if blanco is None:
                raise NoSePuede()   # un vehículo, o un evento que no existe
            quien = (eventos_mapa.mio if p[0] == RUTA_ESTE_EVENTO else p[0])
            if eventos_mapa.comparte_grafico(quien):
                # En la consola el destello se hace sobre la paleta del
                # personaje, y dos eventos con el mismo gráfico comparten una
                # sola: destellarían juntos. Antes que emitir eso y que la
                # referencia lo copie —que es cómo un error se vuelve
                # invisible—, la página no compila. Hoy no cuesta ninguna: son
                # tres destellos y sus páginas se cortan igual por otra cosa.
                raise NoSePuede()
        if any(not 0 <= v <= 31 for v in p[1:5]):
            raise NoSePuede()
        cuadros = p[5] * CUADROS_POR_DECIMA
        if not 0 < cuadros <= 255:
            raise NoSePuede()
        out = bytes([OP_FLASH, blanco, p[1], p[2], p[3], p[4], cuadros])
        if p[6]:
            # Esperar es exactamente el comando Wait: `SetupWait(tenths)`, o sea
            # las mismas décimas por CUADROS_POR_DECIMA.
            out += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == TIMER_OPERATION:
        # El cronómetro. Se hace la operación entera —poner, arrancar y parar—
        # menos los segundos que salen de una variable, que es lo mismo que
        # pasa con los switches indirectos: no leemos variables.
        if len(p) < 5:
            raise NoSePuede()
        if p[0] == TIMER_PONER:
            if p[1] != TIMER_SEGUNDOS_FIJOS:
                raise NoSePuede()
            # La ROM cuenta los cuadros en dieciséis bits, así que el tope no
            # es el del operando sino el de la cuenta. Son dieciocho minutos, y
            # el cronómetro más largo del juego son diez.
            if not 0 <= p[2] * CUADROS_POR_SEGUNDO + TIMER_CUADROS_DE_MAS \
                    <= 0xFFFF:
                raise NoSePuede()
            return bytes([OP_TIMER, TIMER_PONER, p[2] & 0xFF, p[2] >> 8, 0])
        if p[0] in (TIMER_ARRANCAR, TIMER_PARAR):
            # El quinto parámetro es "también en batalla", y acá no hay
            # batallas: se compila igual y se ignora, como el resto de lo que
            # es de combate.
            return bytes([OP_TIMER, p[0], 0, 0, 1 if p[3] else 0])
        raise NoSePuede()

    if cmd.code == MOVE_EVENT:
        if len(p) < 4:
            raise NoSePuede()
        if p[0] == RUTA_HEROE:
            blanco = 0
        elif eventos_mapa is None:
            raise NoSePuede()   # sin el mapa no hay cómo traducir el id
        else:
            blanco = eventos_mapa.blanco(p[0])
            if blanco is None:
                raise NoSePuede()   # un vehículo, o un evento que no existe
        if p[1] != RUTA_FRECUENCIA:
            raise NoSePuede()   # habría que modelar la espera entre órdenes
        ordenes = decodificar_ruta(list(p[4:]))
        ruta = []
        for orden, _extras in ordenes:

            if orden == RUTA_SONIDO:
                # Se acepta y se tira, igual que PlaySound: no se ve y no
                # cuesta cuadros —RM2k no le toca el contador de parada—. Así
                # el bytecode sigue siendo un byte por orden.
                continue
            # Girar, esperar y moverse. Los `move_*` entraron el 2026-09-03,
            # cuando los dos lados empezaron a coincidir *durante* la caminata y
            # no sólo al final: lo prueba `snes-ruta`, que compara cuatro
            # cuadros de una ruta de doce celdas con esperas en el medio. Todo
            # lo demás de `rpg::MoveCommand::Code` —saltar, cambiar el gráfico,
            # atravesar paredes, la velocidad, la frecuencia— sigue afuera.
            if orden not in RUTA_ORDENES:
                raise NoSePuede()
            ruta.append(orden)
        if not ruta or len(ruta) > 255:
            raise NoSePuede()
        return bytes([OP_RUTA, blanco, len(ruta)]) + bytes(ruta)

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
        # La duración se descarta: el tinte se aplica de una. La pantalla que
        # se compara está siempre asentada, así que el valor final es el que
        # importa; lo que se pierde es el degradé de un segundo.
        return bytes([OP_TINTE, p[0], p[1], p[2], p[3]])

    if cmd.code == SHOW_MESSAGE:
        if mensajes is None:
            raise NoSePuede()   # esta ROM no lleva ventana: no hay dónde
        lineas = [cmd.string] + list(extra)
        if any(ESCAPE in t for t in lineas):
            raise NoSePuede()   # ver ESCAPE, arriba
        donde = mensajes.agregar(lineas)
        return bytes([OP_MENSAJE, donde & 0xFF, donde >> 8])

    raise NoSePuede()


# --- ejecutar lo compilado --------------------------------------------------
#
# La ROM y la referencia corren el mismo bytecode. Tener el intérprete una sola
# vez del lado de Python no evita que haya dos implementaciones —la otra está en
# main.s— pero sí evita que haya dos *lenguajes*: lo que se ejecuta es el mismo
# programa, y las reglas de selección de página están escritas una vez acá y una
# vez allá, no una vez por llamador.


class Ruta:
    """Una ruta forzada corriendo sobre alguien: el héroe o un evento.

    La misma clase para los dos, y no por ahorrar líneas. Cómo una ruta consume
    el tiempo —girar es gratis y se sigue en el mismo cuadro, esperar cuesta un
    cuadro, moverse arranca un paso de una celda que dura CUADROS_POR_CELDA, y
    un movimiento bloqueado se saltea— es una decisión de modelo que la ROM y la
    referencia comparten. Escrita dos veces es como se separan.

    La posición vive afuera, en quien la use: la del héroe está en pixeles y
    manda la cámara, la de un evento está en celdas y la lleva `Estado`.
    """

    def __init__(self):
        self.ordenes = []
        self.paso_dir = None
        self.paso_cuadros = 0
        # Los cuadros que faltan de un `wait`. Ver CUADROS_DE_ESPERA_DE_RUTA.
        self.espera = 0
        # El salto en curso: lo que le queda de los 256 y de dónde salió, en
        # celdas. La celda de destino ya es la del personaje —se mueve al
        # empezar, igual que un paso— y lo que se interpola es el dibujo.
        self.salto_resta = 0
        self.salto_dx = 0
        self.salto_dy = 0
        # Y el salto que arrancó **en este cuadro**, para que quien lleva la
        # posición mueva la celda. Se limpia en cada vuelta.
        self.arranco_salto = None
        # Atravesar paredes, y la animación de caminata parada. Las dos son
        # estado de la ruta y sobreviven a las órdenes que las prendieron.
        self.atraviesa = False
        self.anim_parada = False
        # Cuántos cuadros seguidos lleva moviéndose, para la pose de caminata.
        # `animate_hero` lo reinicia en cuanto se queda quieto.
        self.cuadros_moviendose = 0
        # Hacia dónde mira si una ruta se lo dijo. None es "lo decide la
        # caminata", que es lo de siempre.
        self.mirando = None

    @property
    def pendiente(self):
        """Si todavía le queda ruta por caminar.

        Es el `IsMoveRouteOverwritten() && !IsMoveRouteFinished()` de
        `Game_Map::IsAnyMovePending`, que es a lo que espera
        `ProceedWithMovement`.
        """
        return (bool(self.ordenes) or self.paso_cuadros > 0
                or self.espera > 0 or self.salto_resta > 0)

    def cuadro(self, puede, saltar=None):
        """Un cuadro de la ruta.

        `puede(direccion)` dice si se puede dar el paso, `saltar(dx, dy)` si se
        puede caer en esa celda —es `MakeWay` con el personaje saltando, que
        saltea la cara que se deja y pide que la de destino sea pasable por los
        cuatro lados—.

        Devuelve la dirección del paso que se está dando, o None. Un salto que
        arranca en este cuadro queda en `arranco_salto` para que quien lleve la
        posición mueva la celda, igual que hace con un paso.
        """
        self.arranco_salto = None
        if self.paso_cuadros:
            self.paso_cuadros -= 1
            # Con la animación parada el ciclo de caminata no avanza: RM2k
            # llama a `ResetAnimation` en cada cuadro mientras `IsAnimPaused()`,
            # que deja la pose del medio y el contador en cero. Camina igual;
            # lo único que no pasa es el ciclo.
            self.cuadros_moviendose = 0 if self.anim_parada else \
                self.cuadros_moviendose + 1
            direccion = self.paso_dir
            if not self.paso_cuadros:
                self.paso_dir = None
            return direccion
        if self.salto_resta:
            # Un salto en curso. No hay pose de caminata: RM2k llama a
            # `ResetAnimation` mientras se salta, o sea la del medio.
            self.salto_resta = max(0, self.salto_resta - SALTO_VELOCIDAD)
            self.cuadros_moviendose = 0
            return None
        if self.espera:
            self.espera -= 1
            self.cuadros_moviendose = 0
            return None
        while self.ordenes:
            orden = self.ordenes.pop(0)
            if orden in RUTA_MIRAR:
                self.mirando = RUTA_MIRAR[orden]
                continue
            if orden == RUTA_ATRAVESAR_ON:
                self.atraviesa = True
                continue
            if orden == RUTA_ATRAVESAR_OFF:
                self.atraviesa = False
                continue
            if orden == RUTA_ANIM_PARAR:
                self.anim_parada = True
                continue
            if orden == RUTA_ANIM_SEGUIR:
                self.anim_parada = False
                continue
            if orden == RUTA_SALTO_FIN:
                continue            # el par ya lo consumió `RUTA_SALTO_INICIO`
            if orden == RUTA_SALTO_INICIO:
                if self._armar_salto(saltar):
                    break           # el salto arrancó y se lleva el cuadro
                continue            # no se pudo, o no había `end_jump`
            if orden == RUTA_ESPERAR:
                # Veinte cuadros, no uno: éste y los diecinueve que siguen.
                self.espera = CUADROS_DE_ESPERA_DE_RUTA - 1
                break
            direccion = RUTA_MOVER[orden]
            self.mirando = direccion
            if not (self.atraviesa or puede(direccion)):
                continue            # bloqueado: se saltea
            self.paso_dir = direccion
            self.paso_cuadros = CUADROS_POR_CELDA - 1
            self.cuadros_moviendose = 0 if self.anim_parada else \
                self.cuadros_moviendose + 1
            return direccion
        # Ningún paso en este cuadro: el contador vuelve a cero, que es lo que
        # hace `animate_hero` cuando `moving` está apagado —la pose parada, y el
        # ciclo empezando de nuevo en el paso siguiente—. La espera cae acá por
        # `break` y no por `return`: en la ROM una espera de ruta deja al héroe
        # quieto, igual que el final de la ruta, y antes acá seguía contando.
        self.cuadros_moviendose = 0
        return None

    def _armar_salto(self, saltar):
        """Consume las órdenes hasta `end_jump` y arranca el salto.

        Es `BeginMoveRouteJump`: lo que hay en el medio no se camina, se **suma**
        —cada `move_*` aporta su desplazamiento y cada giro cambia hacia dónde
        apunta el siguiente— y el personaje aparece del otro lado en once
        cuadros, los mismos salte una celda o cinco.

        Sin `end_jump` el salto se saltea y las órdenes que quedaban se pierden,
        que es lo que hace RM2k al llegar al final de la ruta.
        """
        dx = dy = 0
        direccion = self.mirando
        hubo_fin = False
        while self.ordenes:
            orden = self.ordenes.pop(0)
            if orden == RUTA_SALTO_FIN:
                hubo_fin = True
                break
            if orden in RUTA_MOVER:
                direccion = RUTA_MOVER[orden]
                paso = RUTA_PASOS[direccion]
                dx += paso[0]
                dy += paso[1]
            elif orden in RUTA_MIRAR:
                direccion = RUTA_MIRAR[orden]
        if not hubo_fin:
            self.ordenes = []
            return False
        if saltar is not None and not saltar(dx, dy):
            return False            # no se puede caer ahí: el salto se saltea
        # Hacia dónde queda mirando: gana el eje de mayor recorrido, y con
        # empate el vertical. En el lugar no cambia nada.
        if dx or dy:
            self.mirando = (2 if dy >= 0 else 0) if abs(dy) >= abs(dx) \
                else (1 if dx >= 0 else 3)
        self.salto_dx, self.salto_dy = dx, dy
        self.salto_resta = SALTO_PASO - SALTO_VELOCIDAD
        self.arranco_salto = (dx, dy)
        self.cuadros_moviendose = 0
        return True


class Estado:
    """Lo que el intérprete recuerda entre páginas y entre mapas."""

    def __init__(self, grupo=()):
        self.switches = set()
        self.tinte = (TINTE_NEUTRO,) * 4      # r, g, b y saturación
        self.salto = None       # (mapa, x, y) si una página pidió mudarse
        # El grupo, en orden. El gráfico del héroe es el del primero, así que
        # esto no es contabilidad: se ve en la pantalla que se compara.
        self.grupo = list(grupo)
        # La ruta forzada del héroe. Las de los eventos van en `rutas_ev`,
        # indexadas por el índice del evento en la tabla del mapa; los cinco
        # atributos de siempre —`ruta`, `mirando`, `paso_dir`, `paso_cuadros`,
        # `cuadros_moviendose`— siguen valiendo y son ésta.
        self.ruta_heroe = Ruta()
        self.rutas_ev = {}
        # Los destellos corriendo, por blanco: (r, g, b, potencia, cuadros, k).
        # `k` es cuántos cuadros pasaron desde que empezó.
        self.flashes = {}
        # Dónde está cada evento del mapa, en celdas. La lleva el estado y no el
        # mapa porque una ruta la cambia y la siguiente arranca de ahí: hay una
        # página de este juego que manda a caminar nueve veces al mismo evento.
        # Se rearma al entrar a cada mapa, igual que `load_npcs` en la ROM.
        self.pos_ev = {}
        # El desplazamiento del cuadro de texto que está en pantalla, o None
        # si no hay ninguno. Mientras esté abierto la página no avanza —es lo
        # que hace `Game_Message`— pero todo lo demás sí: la ruta forzada del
        # héroe sigue caminando y la cámara lo sigue.
        #
        # Es None y no False porque el desplazamiento 0 es un mensaje válido, y
        # de hecho es el que más se usa: `--mensaje-de-prueba` va primero en el
        # bloque justamente para no depender de en qué orden se compilen los
        # mapas. Todo lo que pregunte por esto tiene que preguntar `is not
        # None`.
        self.mensaje = None
        # El cronómetro: cuántos cuadros le quedan, si corre y si se dibuja.
        # Son tres cosas y no una porque RM2k las separa: un cronómetro puede
        # estar corriendo sin verse —`StartTimer(visible=false)`—, que es como
        # el juego mide cuánto tardó el jugador sin decírselo.
        self.timer_cuadros = 0
        self.timer_activo = False
        self.timer_visible = False

    # El héroe visto como estaba antes. Su ruta es una `Ruta` como la de
    # cualquier evento, pero el resto del código la lee por estos nombres y no
    # hay razón para hacerlo cambiar.
    @property
    def ruta(self):
        return self.ruta_heroe.ordenes

    @ruta.setter
    def ruta(self, valor):
        self.ruta_heroe.ordenes = list(valor)

    @property
    def mirando(self):
        return self.ruta_heroe.mirando

    @mirando.setter
    def mirando(self, valor):
        self.ruta_heroe.mirando = valor

    @property
    def paso_dir(self):
        return self.ruta_heroe.paso_dir

    @property
    def paso_cuadros(self):
        return self.ruta_heroe.paso_cuadros

    @property
    def cuadros_moviendose(self):
        return self.ruta_heroe.cuadros_moviendose

    def cuadro_de_ruta(self, puede, saltar=None):
        """Un cuadro de la ruta forzada del héroe."""
        return self.ruta_heroe.cuadro(puede, saltar)

    def entrar_a_un_mapa(self, posiciones):
        """Las posiciones de los eventos del mapa nuevo, en celdas.

        Las rutas que estuvieran corriendo se tiran: en RM2k son de los eventos
        del mapa que se deja, y allá no queda nadie caminando. Es el equivalente
        de que `cargar_mapa` vuelva a copiar la tabla desde la ROM.
        """
        self.rutas_ev = {}
        self.flashes = {}
        self.pos_ev = dict(posiciones)

    def evento_en(self, celda):
        """Qué evento está parado en esa celda, o None.

        Los eventos que no se pueden disparar están en la tabla igual: lo que
        decide es la página activa, y eso lo mira quien llama.
        """
        for indice, donde in self.pos_ev.items():
            if donde == celda:
                return indice
        return None

    def ruta_de_evento(self, indice):
        if indice not in self.rutas_ev:
            self.rutas_ev[indice] = Ruta()
        return self.rutas_ev[indice]

    def rutas_pendientes(self):
        """Si queda alguna ruta forzada sin terminar, la del héroe incluida.

        Es `Game_Map::IsAnyMovePending`, y es global a propósito:
        `ProceedWithMovement` no espera al evento que se acaba de mandar a
        caminar sino a que no quede ninguno.
        """
        return (self.ruta_heroe.pendiente
                or any(r.pendiente for r in self.rutas_ev.values()))

    def cuadro_de_rutas_ev(self, puede_pasar, puede_caer=None):
        """Un cuadro de todas las rutas de eventos. `puede_pasar(indice, x, y,
        direccion)` dice si ese evento puede dar ese paso y `puede_caer(x, y)`
        si se puede aterrizar en esa celda.

        La celda se mueve al **empezar** el paso, igual que el héroe: es lo que
        hace `begin_step` en la ROM, y modelarlo distinto acá dejaría a los dos
        lados contando los cuadros de otra manera. Un salto la mueve igual, sólo
        que de una y no de a una celda.
        """
        for indice, ruta in self.rutas_ev.items():
            x, y = self.pos_ev.get(indice, (0, 0))
            empezaba = ruta.paso_cuadros == 0
            direccion = ruta.cuadro(
                lambda d, i=indice, px=x, py=y: puede_pasar(i, px, py, d),
                saltar=(lambda dx, dy, px=x, py=y:
                        puede_caer is None or puede_caer(px + dx, py + dy)))
            if ruta.arranco_salto is not None:
                dx, dy = ruta.arranco_salto
                self.pos_ev[indice] = (x + dx, y + dy)
            elif direccion is not None and empezaba:
                dx, dy = RUTA_PASOS[direccion]
                self.pos_ev[indice] = (x + dx, y + dy)

    def algo_corriendo(self):
        """Si queda algo andando solo: una ruta forzada o un destello.

        Lo mira quien decide cuándo dejar de contar cuadros. Sin los destellos
        acá, una página que sólo destella termina en el primer cuadro y el
        destello no avanza nunca: se queda encendido para siempre.
        """
        return bool(self.flashes) or self.rutas_pendientes()

    def cuadro_de_timer(self):
        """Un cuadro del cronómetro.

        Es `Game_Party::UpdateTimers`, y lo que importa de él es el final: al
        llegar a cero segundos el cronómetro no se queda mostrando `00:00`,
        sino que `StopTimer` lo apaga **y lo esconde**. O sea que el último
        cuadro en que se ve dice `00:01`, y el siguiente ya no hay nada
        dibujado. Modelarlo como "se para" nada más dejaría a la referencia
        dibujando cinco glifos que RM2k no dibuja.
        """
        if self.timer_activo and self.timer_cuadros > 0:
            self.timer_cuadros -= 1
            if self.timer_cuadros // CUADROS_POR_SEGUNDO == 0:
                self.timer_activo = self.timer_visible = False

    def timer_texto(self):
        """Los cinco caracteres que se dibujan: MM:SS, con los dos puntos que
        parpadean.

        Es `Sprite_Timer::Draw`: los minutos y los segundos salen de
        `cuadros / 60`, y los dos puntos se saltean cuando `cuadros % 60 < 30`.
        El espacio en el medio es "no dibujar nada".
        """
        segundos = self.timer_cuadros // CUADROS_POR_SEGUNDO
        return "%02d%s%02d" % (
            segundos // 60,
            ":" if (self.timer_cuadros % CUADROS_POR_SEGUNDO
                    >= CUADROS_POR_SEGUNDO // 2) else " ",
            segundos % 60)

    def cuadro_de_flashes(self):
        """Un cuadro de todos los destellos: los que se acabaron se apagan."""
        for blanco in list(self.flashes):
            r, g, b, potencia, cuadros, k = self.flashes[blanco]
            if k >= cuadros:
                del self.flashes[blanco]
            else:
                self.flashes[blanco] = (r, g, b, potencia, cuadros, k + 1)

    def nivel_de_flash(self, blanco):
        """Con cuánta fuerza destella este blanco ahora mismo, de 0 a 31.

        La curva es la forma cerrada de la que easyrpg calcula a mano:
        `level -= level / time_left` cuadro a cuadro da exactamente
        `potencia * (cuadros - k) / cuadros`. Acá va con enteros porque los dos
        lados tienen que dar el mismo número, y allá va con `double`.
        """
        if blanco not in self.flashes:
            return 0
        _r, _g, _b, potencia, cuadros, k = self.flashes[blanco]
        return potencia * (cuadros - k) // cuadros

    def color_de_flash(self, blanco):
        """(r, g, b) del destello de este blanco, en cinco bits."""
        return self.flashes[blanco][:3]

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


def blancos_de_ruta(paginas):
    """Los eventos a los que estas páginas ya compiladas les mandan una ruta.

    Recorre el bytecode y no los comandos de RM2k, que es lo que hace que sea la
    verdad y no una conjetura: lo que cuenta es lo que quedó emitido, después de
    que el filtro decidiera qué páginas entran.
    """
    blancos = set()
    for pagina in paginas:
        codigo = pagina.get("codigo")
        i = 0
        while codigo and i < len(codigo):
            op = codigo[i]
            if op == OP_FIN:
                break
            if op == OP_RUTA:
                if codigo[i + 1]:
                    blancos.add(codigo[i + 1] - 1)
                i += 3 + codigo[i + 2]
            elif op == OP_RUTAS:
                i += 1
            elif op == OP_FLASH:
                i += 7
            elif op == OP_TIMER:
                i += 5
            elif op == OP_SWITCH:
                i += 4
            elif op == OP_TELEPORT:
                i += 6
            elif op in (OP_ESPERAR, OP_MENSAJE, OP_GRUPO):
                i += 3
            elif op == OP_TINTE:
                i += 5
            else:
                raise ValueError("opcode %d que no conozco" % op)
    return blancos


def pixeles_del_paso(x, y, ruta):
    """Dónde está en pixeles quien está a mitad de un paso, desde su celda.

    La celda se mueve al **empezar** el paso y los pixeles van detrás: a la
    celda de destino se le descuentan los que falten, a WALK_SPEED por cuadro,
    que es como los come `advance_step` en la ROM. Sin esto, quien camina
    aparece en la celda nueva un paso antes de tiempo; en el cuadro final da
    igual, y por eso no se notó hasta comparar *durante* la caminata.

    Lo usan el héroe y los eventos, que es la razón de que viva acá.
    """
    px, py = x * CELDA_PX, y * CELDA_PX
    if ruta.paso_cuadros and ruta.paso_dir is not None:
        dx, dy = RUTA_PASOS[ruta.paso_dir]
        faltan = ruta.paso_cuadros * WALK_SPEED
        px -= dx * faltan
        py -= dy * faltan
    elif ruta.salto_resta:
        # En un salto la interpolación es la de RM2k y la división va **al
        # final**: `GetSpriteX` hace `x * 256 - dx * restante` y recién ahí
        # divide por 16. Dividir el descuento por separado da uno de más o de
        # menos cada vez que no es múltiplo de 16, que con 24 por cuadro es la
        # mitad de los cuadros del salto.
        por_celda = SALTO_PASO // CELDA_PX
        px = (x * SALTO_PASO - ruta.salto_dx * ruta.salto_resta) // por_celda
        py = (y * SALTO_PASO - ruta.salto_dy * ruta.salto_resta) // por_celda
    return px, py


def altura_del_salto(ruta):
    """Cuántos pixeles hay que subir el dibujo por el arco del salto.

    Es `GetJumpHeight`: sube y baja con lo que queda del salto, y la curva no es
    lineal sino la tabla de RM2k. Lo que se dibuja es la posición interpolada
    menos esto; **lo que se ordena contra los demás no**, porque `GetScreenZ`
    llama a `GetScreenY(false)`, o sea sin el salto. Un personaje saltando no
    pasa por delante de los que están más abajo.
    """
    if not ruta.salto_resta:
        return 0
    resta = ruta.salto_resta
    bruta = (SALTO_PASO - resta if resta > SALTO_PASO // 2 else resta) // 8
    if bruta < 5:
        return bruta * 2
    if bruta < 13:
        return bruta + 4
    return 16


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


def pagina_de_prueba(espera=0, tinte=(), ruta=(), mensaje=None, ruta_ev=(),
                    flash=(), switches=(), timer=()):
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

    `mensaje` es el desplazamiento del cuadro de texto en el bloque de la ROM,
    o None si esta página no abre ninguno.

    `ruta_ev` es (blanco, órdenes) para mandar a caminar a un evento, y detrás
    va un OP_RUTAS. Existe por lo mismo que el resto: **ninguna página del juego
    que compile manda a caminar a un evento sin depender de un switch**, así que
    ese camino no lo ejercitaría nada. Y es filoso por construcción: hasta que
    la ruta no termine, el tinte de más abajo no se aplica, así que el cuadro en
    que la pantalla cambia de color es el cuadro en que la ruta terminó.
    """
    codigo = b""
    if timer:
        # (segundos, visible). El cronómetro del juego lo prende una página que
        # no compila —la del despertador del pad—, así que sin esto no habría
        # con qué comparar: es el mismo motivo por el que existe el resto de
        # esta página.
        segundos, visible = timer
        codigo += bytes([OP_TIMER, TIMER_PONER,
                         segundos & 0xFF, segundos >> 8, 0])
        codigo += bytes([OP_TIMER, TIMER_ARRANCAR, 0, 0, 1 if visible else 0])
    for numero in switches:
        # Prender switches a mano pone al mundo en un estado al que el juego
        # llega más tarde. Hace falta para probar lo que depende de ellos sin
        # jugar hasta ahí: todas las páginas del pad de Talan piden el 24, que
        # prende la cinemática de apertura.
        codigo += bytes([OP_SWITCH, numero & 0xFF, numero >> 8, 1])
    if ruta:
        codigo += bytes([OP_RUTA, 0, len(ruta)]) + bytes(ruta)
    if flash:
        # (blanco, r, g, b, potencia, cuadros). Existe por lo mismo que todo lo
        # demás de esta página: ninguna del juego que compile destella sin
        # depender de un switch.
        codigo += bytes([OP_FLASH]) + bytes(flash)
    if ruta_ev:
        blanco, ordenes = ruta_ev
        codigo += bytes([OP_RUTA, blanco, len(ordenes)]) + bytes(ordenes)
        codigo += bytes([OP_RUTAS])
    if mensaje is not None:
        # El mensaje va antes de la espera y del tinte a propósito: bloquea, así
        # que lo que venga después es lo que prueba que la página **siguió**
        # cuando se apretó A. Con el tinte detrás, antes de apretar la pantalla
        # está sin teñir y después está teñida, igual que en `snes-espera`.
        codigo += bytes([OP_MENSAJE, mensaje & 0xFF, mensaje >> 8])
    if espera:
        codigo += bytes([OP_ESPERAR, espera & 0xFF, espera >> 8])
    if tinte:
        # (r, g, b) y, si viene, la saturación; si no, la neutra.
        codigo += bytes([OP_TINTE]) + bytes(tinte[:3])
        codigo += bytes([tinte[3] if len(tinte) > 3 else TINTE_NEUTRO])
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
        self.paginas = paginas
        self.codigo = None
        self.cursor = 0
        self.esperando = 0

    def pendiente(self):
        """La página que está corriendo, para que sobreviva a un teletransporte.

        En RM2k el salto no reinicia nada: `CommandTeleport` hace `index++` y
        devuelve false, así que la misma página retoma en el comando siguiente
        una vez cambiado el mapa. El código vive en el cartucho, que no se mueve.
        """
        if self.codigo is None:
            return None
        return (self.codigo, self.cursor, self.esperando)

    def retomar(self, pendiente):
        """Vuelve a poner la página que venía corriendo antes del salto."""
        self.codigo, self.cursor, self.esperando = pendiente

    def ocupado(self):
        """Si hay una página corriendo o esperando su turno."""
        return self.codigo is not None or bool(self.cola)

    def probar_accion(self, x, y, mirando, estado):
        """La tecla de acción: el evento de la celda de adelante.

        Sólo la de adelante, y no la propia. En `Game_Player::CheckActionEvent`
        están las dos, pero la propia pide la capa contraria
        —`CheckEventTriggerHere` con `GetLayer() != Layers_same`— y ésas no
        compilan: ver `puede_dispararse`. Mirarla igual haría que la ROM
        disparara algo que RM2k no dispara.

        Lo de "hasta tres mostradores" tampoco está: son las celdas de tipo
        counter, que dejan hablar del otro lado de un mostrador.
        """
        dx, dy = RUTA_PASOS[mirando]
        return self.probar_celda(x + dx, y + dy, TRIGGER_ACCION, estado)

    def probar_contacto(self, x, y, estado):
        """El contacto: el evento de la celda que el héroe acaba de pisar.

        Es `CheckEventTriggerHere` desde `Game_Player::UpdateMovement`, que
        corre cuando el paso termina.
        """
        return self.probar_celda(x, y, TRIGGER_TOCA_HEROE, estado)

    def probar_celda(self, x, y, trigger, estado):
        """Encola la página activa del evento de esa celda si la dispara eso."""
        indice = estado.evento_en((x, y))
        if indice is None:
            return False
        pagina = pagina_activa(self.paginas, indice, estado)
        if (pagina is not None and pagina["trigger"] == trigger
                and pagina["codigo"]):
            self.cola.append(pagina["codigo"])
            return True
        return False

    @property
    def terminado(self):
        return self.codigo is None and not self.cola

    def cuadro(self, apreto_a=False):
        """Avanza un cuadro. Devuelve True si en éste se pidió un salto.

        `apreto_a` es que el jugador **acaba de** apretar A en este cuadro, no
        que lo tenga apretado: RM2k cierra el mensaje con `IsTriggered`, o sea
        con el flanco. En la ROM eso es `pad_a` contra `pad_a_ant`.
        """
        if self.estado.mensaje is not None:
            if not apreto_a:
                return False
            # Se cierra y la página sigue **en el mismo cuadro**, que es lo que
            # hace la ROM: `eventos_tick` limpia `msg_abierto` y cae en el
            # `jsr correr_codigo` de siempre. Cerrar acá y seguir el cuadro
            # siguiente sería un cuadro de diferencia entre los dos lados.
            self.estado.mensaje = None
        if self.esperando == ESPERAR_RUTAS:
            if self.estado.rutas_pendientes():
                return False
            self.esperando = 0
        elif self.esperando:
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


def correr_automaticos(paginas, estado, cuadros=100000, avanzar=None):
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
        # Las rutas de los eventos avanzan acá porque este lazo es el dueño del
        # tiempo. Sin esto, una página que espere a que terminen —OP_RUTAS— no
        # terminaría nunca: nadie las estaría caminando.
        if avanzar is not None:
            avanzar()
        if interprete.terminado or estado.mensaje is not None:
            # Con un mensaje abierto no hay a quién esperar: acá no hay
            # jugador. Se corta con la ventana en pantalla, que es exactamente
            # lo que hace la consola si nadie aprieta nada. Quien quiera
            # comparar el cierre pasa cuadros y dice en cuál se aprieta A.
            break
    return None


# Lo que `ejecutar` devuelve como "cuántos cuadros esperar" cuando la espera no
# es una cuenta sino una condición: que no quede ninguna ruta forzada corriendo.
# Es un valor aparte y no un número grande para que nadie lo sume por error.
ESPERAR_RUTAS = "rutas"


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
            # La ruta se encola y la camina quien la recibió, no el intérprete:
            # en RM2k `ForceMoveRoute` es asincrónico y la página sigue. Quien
            # la hace avanzar es `cuadro_de_ruta` / `cuadro_de_rutas_ev`, una
            # vez por cuadro. Y encolar pisa lo que hubiera: RM2k sobrescribe la
            # ruta forzada anterior, no la encadena.
            blanco = codigo[i + 1]
            cuantos = codigo[i + 2]
            ordenes = list(codigo[i + 3:i + 3 + cuantos])
            if blanco == 0:
                estado.ruta = ordenes
            else:
                estado.ruta_de_evento(blanco - 1).ordenes = ordenes
            i += 3 + cuantos
        elif op == OP_FLASH:
            # Empieza un destello. No corta el cuadro: si la página espera, el
            # conversor le pone un OP_ESPERAR detrás, que es lo que hace
            # `CommandFlashSprite` con `SetupWait(tenths)`.
            estado.flashes[codigo[i + 1]] = (codigo[i + 2], codigo[i + 3],
                                             codigo[i + 4], codigo[i + 5],
                                             codigo[i + 6], 0)
            i += 7
        elif op == OP_TIMER:
            # `CommandTimerOperation`. No corta el cuadro: las tres operaciones
            # son asignaciones, y quien hace correr el cronómetro es
            # `cuadro_de_timer`, una vez por cuadro.
            operacion = codigo[i + 1]
            if operacion == TIMER_PONER:
                estado.timer_cuadros = ((codigo[i + 2] | (codigo[i + 3] << 8))
                                        * CUADROS_POR_SEGUNDO
                                        + TIMER_CUADROS_DE_MAS)
            elif operacion == TIMER_ARRANCAR:
                estado.timer_activo = True
                estado.timer_visible = bool(codigo[i + 4])
            else:
                # `StopTimer` apaga las dos cosas, no sólo la cuenta.
                estado.timer_activo = estado.timer_visible = False
            i += 5
        elif op == OP_RUTAS:
            # "Esperá a que terminen las rutas". Se devuelve el control con una
            # marca en vez de una cuenta de cuadros: no se sabe cuántos van a
            # ser, y quien decide es `Interprete.cuadro` mirando si queda alguna
            # pendiente. Si no queda ninguna no cuesta ni un cuadro, que es lo
            # que hace el `while` de `Game_Interpreter::Update`.
            if not estado.rutas_pendientes():
                i += 1
                continue
            return (i + 1, ESPERAR_RUTAS, False)
        elif op == OP_MENSAJE:
            # Abre la ventana y corta el cuadro. El cursor queda en el comando
            # siguiente, pero `Interprete.cuadro` no vuelve a llegar acá hasta
            # que alguien apriete A: la página queda bloqueada, que es lo que
            # hace `Game_Message` en RM2k.
            estado.mensaje = codigo[i + 1] | (codigo[i + 2] << 8)
            return (i + 3, 0, False)
        elif op == OP_GRUPO:
            estado.cambiar_grupo(codigo[i + 1], codigo[i + 2])
            i += 3
        elif op == OP_TINTE:
            estado.tinte = (codigo[i + 1], codigo[i + 2], codigo[i + 3],
                            codigo[i + 4])
            i += 5
        else:
            raise ValueError("opcode %d que no conozco" % op)
    return None


# Los pesos de luminancia de RM2k, que son los de Y' del Y'CbCr: la cuenta de
# `saturation_tone` en easyrpg es `(7471*b + 38470*g + 19595*r) >> 16`. Suman
# exactamente 65536, así que aplicados a canales de cinco bits dan una
# luminancia de cinco bits sin tener que reescalar nada.
LUZ_R, LUZ_G, LUZ_B = 19595, 38470, 7471
LUZ_TOTAL = 65536


def luminancia(r, g, b):
    """La luminancia de un color de 15 bits, en cinco bits."""
    return (LUZ_R * r + LUZ_G * g + LUZ_B * b) // LUZ_TOTAL


def saturar(canal, luz, s):
    """Un canal acercado o alejado del gris, con `s` en las unidades de RM2k.

    Es `saturation_tone` de easyrpg puesto en cinco bits y en las unidades de
    RM2k en vez de las suyas. Allá el factor es
    `sat = gray > 128 ? 1024 + (gray - 128) * 16 : gray * 8` sobre 1024, con
    `gray = s * 128 / 100`; hecha la cuenta, eso es `s / 100` para `s <= 100` y
    `(2s - 100) / 100` para `s > 100`. O sea que 0 lleva todo al gris, 100 no
    hace nada, y 200 triplica la distancia al gris.

    El caso de más de 100 va con el signo separado y truncando, en vez de con
    el desplazamiento aritmético de easyrpg, que redondea hacia abajo también
    con números negativos. La diferencia es de un valor de 31 y sólo cuando
    sobresatura; hacerlo con signo en el 65816 costaría bastante más que eso.
    """
    if s <= TINTE_NEUTRO:
        # Una interpolación entre el gris y el color, con los dos términos
        # positivos: es la forma que el 65816 puede hacer sin signo.
        return (luz * (TINTE_NEUTRO - s) + canal * s) // TINTE_NEUTRO
    m = s - TINTE_NEUTRO
    if canal >= luz:
        return min(31, canal + (canal - luz) * m // TINTE_NEUTRO)
    return max(0, canal - (luz - canal) * m // TINTE_NEUTRO)


def tenir_canal(canal, valor):
    """Un canal de cinco bits pasado por el tinte de RM2k, que es un hard light.

    RM2k no escala el canal: lo compone con un *hard light* —`hard_light.table`
    en easyrpg, que es `2ab` para la mitad de abajo y el screen `1-2(1-a)(1-b)`
    para la de arriba—. En las unidades de RM2k, con 100 neutro, eso es:

        valor <= 100:  canal * valor / 100
        valor  > 100:  31 - (200 - valor) * (31 - canal) / 100

    La primera mitad es exactamente lo que este repo venía haciendo, y por eso
    los tintes que oscurecen no cambian: la ROM y la referencia dan lo mismo que
    antes. La segunda no lo era. `canal * valor / 100` con valor hasta 200
    multiplica por dos y topa, y eso **no es** lo que hace RM2k: la diferencia
    llega a 31 de 31 con valor 200, o sea la pantalla entera. No lo cobró nadie
    porque ninguna página que compilara usaba un tinte que aclare; las dos que
    lo destraba la saturación —los mapas 229 y 230— sí, con (0, 120, 120).

    Medido contra la cuenta de easyrpg sobre ocho bits, esta versión difiere en
    **un valor de 31 como mucho**, para todos los tintes que el juego usa. Es la
    misma tolerancia que ya tenía la mitad de abajo, y viene de que RM2k hace la
    cuenta con ocho bits y la consola tiene cinco.
    """
    if valor <= TINTE_NEUTRO:
        return min(31, canal * valor // TINTE_NEUTRO)
    return min(31, 31 - (2 * TINTE_NEUTRO - valor) * (31 - canal) // TINTE_NEUTRO)


def tenir(palabra, tinte):
    """Un color de 15 bits pasado por el tinte de pantalla.

    Primero la saturación y después el color, que es el orden de `ToneBlit`:
    allá `saturation_tone` corre antes que `color_tone`. Hacerlo al revés da
    otra cosa —el gris se calcularía sobre el color ya teñido— y es de las que
    la comparación no vería, porque los dos lados harían lo mismo mal.

    La cuenta va con enteros y sobre los 15 bits, no sobre los 24 del PNG: la
    consola tiene cinco bits por canal y redondearía distinto.
    """
    canales = [palabra & 0x1F, (palabra >> 5) & 0x1F, (palabra >> 10) & 0x1F]
    if len(tinte) > 3 and tinte[3] != TINTE_NEUTRO:
        # Sólo cuando hace falta, igual que el `apply_sat` de easyrpg: la
        # saturación no se puede hacer canal por canal —necesita el gris del
        # color entero— y es lo caro de esto en la consola.
        luz = luminancia(*canales)
        canales = [saturar(c, luz, tinte[3]) for c in canales]
    salida = 0
    for numero, (canal, valor) in enumerate(zip(canales, tinte)):
        salida |= tenir_canal(canal, valor) << (numero * 5)
    return salida


def destellar(palabra, color, nivel):
    """Un color de 15 bits mezclado hacia el del destello.

    Es la cuenta de easyrpg puesta en cinco bits: allá el destello es un color
    con alfa `nivel * 8` compuesto sobre el sprite —`Flash::MakeColor` y el
    `PIXMAN_OP_OVER` de `BlendBlit`— o sea `destino * a + origen * (255 - a)`
    sobre 255. La diferencia es el espacio: RM2k mezcla los ocho bits del PNG y
    nosotros los cinco que entran en CGRAM, así que **el resultado no es el de
    RM2k**, es el que da la misma cuenta con menos bits.

    Está declarado porque es la clase de cosa que la comparación no ve: los dos
    lados hacen lo mismo y dan cero. Lo mismo pasa con el tinte de pantalla, y
    por la misma razón. Quien quiera medirlo necesita una captura de EasyRPG
    tomada durante un destello.
    """
    if nivel <= 0:
        return palabra
    alfa = nivel * 8
    salida = 0
    for numero in range(3):
        canal = (palabra >> (numero * 5)) & 0x1F
        mezcla = (color[numero] * alfa + canal * (255 - alfa)) // 255
        salida |= min(31, mezcla) << (numero * 5)
    return salida


def deudas_de_la_pagina(page):
    """Qué comandos de esta página se aceptan sin hacerlos.

    Para que el conversor pueda avisar en vez de que la deuda quede muda.
    """
    return sorted({cmd.code for cmd in page.commands
                   if cmd.code in ACEPTADOS_SIN_HACER})


def paginas_del_mapa(game_map, indice_de_mapa, mensajes=None):
    """Las páginas que la ROM necesita para resolver los eventos del mapa.

    Se emiten *todas* las páginas de un evento que tenga alguna disparable, no
    sólo ésas: cuál queda activa depende de las condiciones de todas ellas, y
    una página posterior que no dispare nada igual gana y le impide correr a la
    de más abajo.
    """
    salida = []
    del_mapa = Eventos(game_map)
    for numero_evento, event in enumerate(game_map.events):
        if not any(page.trigger in TRIGGERS for page in event.pages):
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
            if page.trigger in TRIGGERS and puede_dispararse(page):
                codigo = compilar_pagina(page, indice_de_mapa, mensajes,
                                         del_mapa.para(event.id))
            grupo.append({
                "evento": numero_evento,
                "pagina": numero_pagina,
                "trigger": page.trigger,
                "switch_a": cond.ids["switch_a"] if "switch_a" in cond.active else 0,
                "switch_b": cond.ids["switch_b"] if "switch_b" in cond.active else 0,
                "actor": cond.ids["actor"] if "actor" in cond.active else 0,
                "codigo": codigo,
            })

        # Un evento cuyas páginas disparables no se pueden compilar no aporta
        # nada: sin código no hay nada que ejecutar y sólo ocuparía tabla.
        if any(p["codigo"] for p in grupo):
            salida += grupo
    return salida
