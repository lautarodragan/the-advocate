"""Maneja un core de libretro desde Python. Sin X, sin reloj, sin sleeps.

`retro_run()` avanza exactamente un cuadro, la cruceta entra cuadro por cuadro y
el framebuffer sale por el callback de video. Un caso deja de ser "dormí 45
segundos y sacale una foto a la pantalla" para ser "corré N cuadros con Right
apretado y mirá el cuadro N". Eso arregla las dos cosas a la vez: la tanda deja
de esperar en tiempo real, y deja de depender de cuántos cuadros alcanzó a
emular la máquina mientras dormíamos.

Andan los tres cores que hay instalados —snes9x, bsnes y mesen-s— y los tres
dibujan **el mismo cuadro a 15 bits**, que es la precisión a la que compara
`snes_compare.py`: 0 pixeles de diferencia de 57344, medido en el mapa 7 a los
180 cuadros. Que tres emuladores independientes coincidan es lo que vuelve
creíble a cualquiera de ellos como segunda opinión.

Los tres tardaron en andar por errores de este archivo, no de ellos, y los tres
fallaban en silencio o de una manera que no señalaba la causa. Vale la pena
dejar escrito qué pedía cada uno, porque el contrato de libretro no lo dice tan
claro:

  * **El orden de las llamadas.** Los callbacks de video, audio e input van
    DESPUÉS de `retro_init`, no antes; sólo el de entorno va antes. mesen-s
    guarda el puntero adentro de un objeto que crea `retro_init`, así que
    llamarlo antes escribe en la nada: segfault en `retro_set_video_refresh`,
    sin un mensaje. Es el orden que usa RetroArch.
  * **`need_fullpath`.** bsnes lo declara en `retro_get_system_info` y su
    `retro_load_game` **ignora `game->data` por completo**: hace
    `program->superFamicom.location = string(game->path)` y abre el archivo él
    mismo. Con `path` en NULL cargaba "" y devolvía true igual, así que la ROM
    nunca entraba: la pantalla quedaba negra, el audio sonaba —el APU corre sin
    ROM— y nadie decía nada. Acá se le pasa siempre el path, y los datos sólo a
    quien no pide el archivo.
  * **El directorio del sistema.** mesen-s corta `retro_load_game` en la
    primera línea si `GET_SYSTEM_DIRECTORY` contesta que no. Devolvía false y
    listo.
  * **Contestar "no hay variable" a `GET_VARIABLE` no es neutral.** El core se
    queda con valores que uno no eligió. Acá se contesta el primer valor de cada
    lista, que es el default por convención de libretro, y encima de eso van las
    de OPCIONES.

Lo que queda afuera a propósito: `GET_LOG_INTERFACE` se contesta que no. El
callback es un printf variádico y ctypes no los arma; los tres cores se lo
bancan y sólo se pierden mensajes de diagnóstico.
"""
import ctypes
import os
import sys

from PIL import Image

# El de la tanda. No es el más preciso —bsnes lo es— sino el más rápido por
# lejos: 2747 cuadros por segundo contra 121. El justfile elige con CORE.
CORE = "/usr/lib/libretro/snes9x_libretro.so"

# Los comandos de entorno que hacen falta. Al resto se le contesta que no, que
# es legal: el core tiene que arreglarse con sus valores por defecto.
ENV_GET_OVERSCAN = 2
ENV_GET_CAN_DUPE = 3
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_SAVE_DIRECTORY = 31
FORMATOS = {0: "0RGB1555", 1: "XRGB8888", 2: "RGB565"}

# Las líneas que compara el proyecto. Cada core devuelve el alto que quiere
# —bsnes y snes9x 224, mesen-s 239— y lo de más se recorta al centro, que es
# donde cae la ventana de siempre: con mesen-s el recorte da (239-224)/2 = 7 y
# es exactamente el que hace coincidir los tres cores en 0 pixeles.
ALTO = 224

# Lo que hay que forzarle a cada core para que dibuje lo mismo que los otros, y
# para que la prueba mida lo que queremos. La clave es el `library_name` que
# declara el core, no el nombre del archivo.
OPCIONES = {
    # El gamma de 150% es el de un televisor, y acá se compara contra una
    # referencia en Python que no lo modela: con el default, bsnes difiere de
    # snes9x en 56189 pixeles de 57344; con 100 difiere en 0.
    #
    # Y la entropía va al máximo a propósito, que es la razón por la que este
    # core vale la pena: bsnes llena la WRAM de basura al encender, como la
    # consola de verdad, y snes9x la deja en cero. Comentando las dos líneas
    # que inicializan `ruta_n`/`ruta_i` en main.s —el error que taro encontró
    # jugando y que la tanda no vio— sobre 20 corridas del mapa 7: con "None"
    # difieren 0, con "Low" 3 y con "High" 11. Con la ROM sana, 20 corridas de
    # 20 dan el mismo cuadro, así que esto no vuelve inestable a la tanda: sólo
    # a un rojo que no siempre se repite, y un rojo así es un error de verdad.
    # Para reproducirlo, `bsnes_entropy=None`.
    "bsnes": {"bsnes_video_gamma": "100", "bsnes_entropy": "High"},
}

# RETRO_DEVICE_JOYPAD, en el orden en que los numera libretro.
BOTONES = {"b": 0, "y": 1, "select": 2, "start": 3, "up": 4, "down": 5,
           "left": 6, "right": 7, "a": 8, "x": 9, "l": 10, "r": 11}


class SystemInfo(ctypes.Structure):
    _fields_ = [("library_name", ctypes.c_char_p),
                ("library_version", ctypes.c_char_p),
                ("valid_extensions", ctypes.c_char_p),
                ("need_fullpath", ctypes.c_bool),
                ("block_extract", ctypes.c_bool)]


class Variable(ctypes.Structure):
    _fields_ = [("key", ctypes.c_char_p), ("value", ctypes.c_char_p)]


class GameInfo(ctypes.Structure):
    _fields_ = [("path", ctypes.c_char_p), ("data", ctypes.c_void_p),
                ("size", ctypes.c_size_t), ("meta", ctypes.c_char_p)]


class Consola:

    def __init__(self, rom, core=CORE, opciones=None):
        self.lib = ctypes.CDLL(core)
        self._forzadas = dict(opciones or {})
        self.formato = 0
        # Las opciones que el core declara, con su valor por defecto. Contestar
        # "no hay variable" no es lo mismo que no tener opiniones: bsnes deja
        # la luminancia en cero y devuelve una pantalla negra con el audio
        # sonando igual. Un frontend de verdad contesta el primer valor de la
        # lista, que es el default por convención de libretro.
        self.opciones = {}
        self.cuadro = None          # (bytes, ancho, alto, pitch) del último
        self.cuadros = 0
        self.apretados = set()
        self.audio = bytearray()

        info = SystemInfo()
        self.lib.retro_get_system_info(ctypes.byref(info))
        self.nombre = "%s %s" % (info.library_name.decode(),
                                 info.library_version.decode())
        # bsnes abre el archivo él mismo y ni mira `data`. Ver el docstring.
        pide_archivo = info.need_fullpath
        self._forzadas = dict(OPCIONES.get(info.library_name.decode(), {}),
                              **self._forzadas)

        # Adonde el core guarda partidas y busca BIOS. Al lado de la ROM, que
        # es un directorio que ya es descartable; mesen-s no carga sin esto.
        self._directorio = ctypes.c_char_p(
            os.path.dirname(os.path.abspath(rom)).encode())

        # Los callbacks se guardan en self: si se los deja como temporales, el
        # recolector de Python los libera y el core llama a memoria muerta.
        self._env = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint,
                                     ctypes.c_void_p)(self._on_env)
        self._video = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_size_t)(self._on_video)
        self._audio = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p,
                                       ctypes.c_size_t)(self._on_audio)
        self._audio_uno = ctypes.CFUNCTYPE(None, ctypes.c_int16,
                                           ctypes.c_int16)(lambda i, d: None)
        self._poll = ctypes.CFUNCTYPE(None)(lambda: None)
        self._state = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_uint,
                                       ctypes.c_uint)(self._on_state)

        # El de entorno antes de retro_init, el resto después: es el orden de
        # RetroArch, y el único con el que mesen-s no se cae. Ver el docstring.
        self.lib.retro_set_environment(self._env)
        self.lib.retro_init()
        self.lib.retro_set_video_refresh(self._video)
        self.lib.retro_set_audio_sample(self._audio_uno)
        self.lib.retro_set_audio_sample_batch(self._audio)
        self.lib.retro_set_input_poll(self._poll)
        self.lib.retro_set_input_state(self._state)

        datos = open(rom, "rb").read()
        self._buf = ctypes.create_string_buffer(datos, len(datos))
        juego = GameInfo(os.path.abspath(rom).encode(),
                         None if pide_archivo
                         else ctypes.cast(self._buf, ctypes.c_void_p),
                         len(datos), None)
        # snes9x escribe "Map_LoROMMap" en la salida estándar al cargar. Es un
        # printf del core, no de Python, así que taparlo pide mover el descriptor
        # y no redirigir sys.stdout. Ensuciaría el log de cada caso de la tanda.
        # Y hay que vaciar el buffer de libc antes de devolver el descriptor:
        # el printf no escribe al toque, se queda en el buffer y sale recién al
        # terminar el proceso, o sea cuando la redirección ya no está.
        libc = ctypes.CDLL(None)
        guardado = os.dup(1)
        nulo = os.open(os.devnull, os.O_WRONLY)
        sys.stdout.flush()
        os.dup2(nulo, 1)
        try:
            cargo = self.lib.retro_load_game(ctypes.byref(juego))
        finally:
            libc.fflush(None)
            os.dup2(guardado, 1)
            os.close(nulo)
            os.close(guardado)
        if not cargo:
            raise SystemExit("el core no pudo cargar %s" % rom)

    def _on_env(self, cmd, data):
        if cmd == ENV_SET_VARIABLES and data:
            arr = ctypes.cast(data, ctypes.POINTER(Variable))
            i = 0
            while arr[i].key:
                texto = arr[i].value.decode()
                # "Descripción; uno|dos|tres" -> el default es el primero.
                defecto = texto.split(";", 1)[-1].strip().split("|")[0].strip()
                self.opciones[arr[i].key.decode()] = defecto
                i += 1
            self.opciones.update(self._forzadas)
            return True
        if cmd == ENV_GET_VARIABLE and data:
            var = ctypes.cast(data, ctypes.POINTER(Variable))
            clave = var[0].key.decode() if var[0].key else ""
            if clave not in self.opciones:
                return False
            self._vivas = getattr(self, "_vivas", {})
            # El core se queda con el puntero, así que el bytes tiene que
            # sobrevivir a esta llamada.
            self._vivas[clave] = self.opciones[clave].encode()
            var[0].value = self._vivas[clave]
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.formato = ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0]
            return self.formato in FORMATOS
        if cmd == ENV_GET_OVERSCAN:
            # Que no recorte: queremos el framebuffer entero, que es lo que
            # captura la consola, no lo que un televisor dejaría ver.
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if cmd == ENV_GET_CAN_DUPE:
            # Sí: un cuadro repetido llega con data en NULL y `_on_video` se
            # queda con el anterior, que es justo lo que la consola muestra.
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY) and data:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = self._directorio
            return True
        return False

    def _on_video(self, data, w, h, pitch):
        if data:
            self.cuadro = (ctypes.string_at(data, pitch * h), w, h, pitch)
        self.cuadros += 1

    def _on_audio(self, data, frames):
        if data:
            self.audio += ctypes.string_at(data, frames * 4)   # 2 canales s16
        return frames

    def _on_state(self, port, device, index, ident):
        return 1 if (port == 0 and ident in self.apretados) else 0

    def apretar(self, *nombres):
        """Qué botones se mantienen apretados de acá en adelante."""
        self.apretados = {BOTONES[n] for n in nombres}

    def correr(self, cuadros=1):
        for _ in range(cuadros):
            self.lib.retro_run()

    # La WRAM del emulador, que es la única forma de mirar adentro sin un
    # depurador. libretro la expone con `retro_get_memory_data(2)`, que es
    # RETRO_MEMORY_SYSTEM_RAM; los tres cores la implementan.
    #
    # No es parte de ninguna prueba: sirve para depurar, y apareció haciendo el
    # compositor de texto, cuando la pantalla decía "algo está mal" y no dónde.
    MEMORIA_SISTEMA = 2

    def ram(self, direccion=0, largo=None):
        """Bytes de la WRAM desde `direccion`, que es la del banco $7E."""
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_SISTEMA)
        total = self.lib.retro_get_memory_size(self.MEMORIA_SISTEMA)
        if not base or not total:
            raise RuntimeError("este core no expone la WRAM")
        if largo is None:
            largo = total - direccion
        return ctypes.string_at(base + direccion, largo)

    def escribir_ram(self, direccion, datos):
        """Escribe bytes en la WRAM, en la dirección del banco $7E.

        El puntero que devuelve `retro_get_memory_data` es la memoria del core,
        no una copia, así que escribirla es escribirle a la consola.

        Existe para las pruebas de estado, que ponen el mundo en una situación a
        la que el juego llega más tarde —un switch prendido, por ejemplo— sin
        tener que armar una ROM distinta para cada una. **La tanda de pixeles no
        lo usa ni tiene que usarlo**: ahí se compara contra una referencia que
        modela el camino de verdad, y saltearse ese camino sería comparar dos
        cosas que no pasaron por lo mismo.
        """
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_SISTEMA)
        total = self.lib.retro_get_memory_size(self.MEMORIA_SISTEMA)
        if not base or not total:
            raise RuntimeError("este core no expone la WRAM")
        datos = bytes(datos)
        if direccion + len(datos) > total:
            raise ValueError("escribir %d bytes en %d se pasa de la WRAM (%d)"
                             % (len(datos), direccion, total))
        ctypes.memmove(base + direccion, datos, len(datos))

    def imagen(self):
        """El último cuadro como PIL, a 8 bits por canal y recortado a ALTO."""
        datos, w, h, pitch = self.cuadro
        if self.formato == 1:                      # XRGB8888
            img = Image.frombuffer("RGBX", (pitch // 4, h), datos,
                                   "raw", "BGRX", 0, 1)
            img = img.convert("RGB")
        else:
            modo = "BGR;16" if self.formato == 2 else "BGR;15"
            img = Image.frombuffer("RGB", (pitch // 2, h), datos, "raw", modo,
                                   0, 1)
        arriba = max(0, (h - ALTO) // 2)
        return img.crop((0, arriba, w, arriba + min(h, ALTO)))
