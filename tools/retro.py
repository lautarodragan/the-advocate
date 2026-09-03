"""Maneja un core de libretro desde Python. Sin X, sin reloj, sin sleeps.

`retro_run()` avanza exactamente un cuadro, la cruceta entra cuadro por cuadro y
el framebuffer sale por el callback de video. Un caso deja de ser "dormí 45
segundos y sacale una foto a la pantalla" para ser "corré N cuadros con Right
apretado y mirá el cuadro N". Eso arregla las dos cosas a la vez: la tanda deja
de esperar en tiempo real, y deja de depender de cuántos cuadros alcanzó a
emular la máquina mientras dormíamos.

ESTO ES UN SPIKE. Anda con snes9x y está verificado contra el harness viejo: 46
comparaciones bit-exactas —el caso estático y los ocho mapas de snes-heroe por
cinco direcciones— contra los mismos PNG esperados que usa `just snes-hitos`, a
los 15 bits que compara snes_compare.py, honrando las líneas de --saltar.

Y CON BSNES DEVUELVE UNA PANTALLA NEGRA, SIN DECIR NADA. El core carga la ROM,
suena el audio, retro_run avanza, y el framebuffer viene en cero para cualquier
cantidad de cuadros. No es la entropía, ni ppu_fast, ni las opciones, ni la
respuesta a GET_OVERSCAN; durante retro_run sólo pide GET_VARIABLE_UPDATE y
GET_FASTFORWARDING. Lo que sí se sabe es de quién es la culpa: **bajo RetroArch,
el mismo core con la misma ROM dibuja bien**. O sea que falta algo de este
frontend, no de la ROM. Mientras eso no se resuelva, este archivo sirve para
snes9x y para nada más — y falla en silencio, que es la peor manera.

De paso, tres cosas que aprendimos y que valen para cualquier frontend:

  * Contestar "no hay variable" a GET_VARIABLE no es neutral. bsnes se queda con
    valores que uno no eligió y devuelve una pantalla negra con el audio
    sonando. Acá se contesta el primer valor de cada lista, que es el default
    por convención de libretro.
  * bsnes_entropy viene en "Low": bsnes aleatoriza la RAM al encender, a
    propósito. Para una prueba determinista hay que forzarlo a "None".
  * bsnes_ppu_no_sprite_limit viene en OFF, que es lo que queremos: el límite de
    sprites por línea es real y es justo lo que hoy esquiva --saltar.
"""
import ctypes
import os
import sys

from PIL import Image

CORE = "/usr/lib/libretro/bsnes_libretro.so"

# Los pocos comandos de entorno que hacen falta. El resto se contesta que no,
# que es legal: el core tiene que arreglarse con sus valores por defecto.
ENV_GET_OVERSCAN = 2
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
FORMATOS = {0: "0RGB1555", 1: "XRGB8888", 2: "RGB565"}

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

        # Los callbacks se guardan en self: si se los deja como temporales, el
        # recolector de Python los libera y el core llama a memoria muerta.
        self._env = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint,
                                     ctypes.c_void_p)(self._on_env)
        self._video = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_size_t)(self._on_video)
        self._audio = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p,
                                       ctypes.c_size_t)(self._on_audio)
        self._poll = ctypes.CFUNCTYPE(None)(lambda: None)
        self._state = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_uint,
                                       ctypes.c_uint)(self._on_state)

        self.lib.retro_set_environment(self._env)
        self.lib.retro_set_video_refresh(self._video)
        self.lib.retro_set_audio_sample_batch(self._audio)
        self.lib.retro_set_input_poll(self._poll)
        self.lib.retro_set_input_state(self._state)
        self.lib.retro_init()

        datos = open(rom, "rb").read()
        self._buf = ctypes.create_string_buffer(datos, len(datos))
        juego = GameInfo(None, ctypes.cast(self._buf, ctypes.c_void_p),
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

    def imagen(self):
        """El último cuadro como PIL, a 8 bits por canal."""
        datos, w, h, pitch = self.cuadro
        if self.formato == 1:                      # XRGB8888
            img = Image.frombuffer("RGBX", (pitch // 4, h), datos,
                                   "raw", "BGRX", 0, 1)
            return img.convert("RGB").crop((0, 0, w, h))
        modo = "BGR;16" if self.formato == 2 else "BGR;15"
        img = Image.frombuffer("RGB", (pitch // 2, h), datos, "raw", modo, 0, 1)
        return img.crop((0, 0, w, h))
