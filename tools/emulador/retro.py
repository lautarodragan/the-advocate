"""Drives a libretro core from Python. No X, no clock, no sleeps.

`retro_run()` advances exactly one frame, the D-pad goes in frame by frame and
the framebuffer comes out through the video callback. A case stops being "sleep
45 seconds and take a picture of the screen" and becomes "run N frames with
Right held and look at frame N". That fixes two things at once: the suite stops
waiting in real time, and stops depending on how many frames the machine
managed to emulate while we slept.

The three installed cores work —snes9x, bsnes and mesen-s— and all three draw
**the same frame at 15 bits**, which is the precision the tests compare at: 0
pixels of difference out of 57344, measured on map 7 at 180 frames. Three
independent emulators agreeing is what makes any of them credible as a
second opinion.

All three took a while to work because of bugs in this file, not in them, and
all three failed silently or in a way that did not point at the cause. It is
worth writing down what each one required, because the libretro contract does
not say it that clearly:

  * **The order of the calls.** The video, audio and input callbacks go AFTER
    `retro_init`, not before; only the environment one goes before. mesen-s
    keeps the pointer inside an object that `retro_init` creates, so calling
    it before writes into nothing: segfault in `retro_set_video_refresh`,
    without a message. It is the order RetroArch uses.
  * **`need_fullpath`.** bsnes declares it in `retro_get_system_info` and its
    `retro_load_game` **ignores `game->data` completely**: it does
    `program->superFamicom.location = string(game->path)` and opens the file
    itself. With `path` set to NULL it loaded "" and returned true anyway, so
    the ROM never got in: the screen stayed black, the audio played —the APU
    runs without a ROM— and nobody said anything. Here the path is always
    passed, and the data only to whoever does not ask for the file.
  * **The system directory.** mesen-s cuts `retro_load_game` short on the
    first line if `GET_SYSTEM_DIRECTORY` answers no. It returned false and
    that was it.
  * **Answering "no such variable" to `GET_VARIABLE` is not neutral.** The core
    keeps values nobody chose. Here the first value of each list is answered,
    which is the default by libretro convention, and on top of that go the
    ones in OPCIONES.

What is left out on purpose: `GET_LOG_INTERFACE` is answered no. The callback
is a variadic printf and ctypes does not build those; the three cores put up
with it and only diagnostic messages are lost.
"""
import ctypes
import os
import shutil
import sys
import tempfile
import weakref

from PIL import Image

# The suite's core. It is not the most accurate —bsnes is— but the fastest by
# far: 2747 frames per second against 121. The justfile chooses with CORE.
CORE = "/usr/lib/libretro/snes9x_libretro.so"

# The environment commands that are needed. The rest are answered no, which
# is legal: the core has to make do with its default values.
ENV_GET_OVERSCAN = 2
ENV_GET_CAN_DUPE = 3
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_SAVE_DIRECTORY = 31
FORMATOS = {0: "0RGB1555", 1: "XRGB8888", 2: "RGB565"}

# The lines the project compares. Each core returns the height it wants
# —bsnes and snes9x 224, mesen-s 239— and the excess is cropped around the
# center, which is where the usual window falls: with mesen-s the crop comes to
# (239-224)/2 = 7 and it is exactly the one that makes the three cores agree
# at 0 pixels.
ALTO = 224

# What has to be forced on each core so that it draws the same as the others,
# and so that the test measures what we want. The key is the `library_name`
# the core declares, not the file name.
OPCIONES = {
    # The 150% gamma is a television's, and here the comparison is against a
    # Python reference that does not model it: with the default, bsnes differs
    # from snes9x in 56189 pixels out of 57344; with 100 it differs in 0.
    #
    # And the entropy goes to the maximum on purpose, which is the reason this
    # core is worth it: bsnes fills the WRAM with garbage at power-on, like
    # the real console, and snes9x leaves it at zero. Commenting out the two
    # lines that initialize `ruta_n`/`ruta_i` in tools/runtime/ —the bug taro
    # found while playing and the suite did not see— over 20 runs of map 7:
    # with "None" they differ in 0, with "Low" in 3 and with "High" in 11. With
    # the healthy ROM, 20 runs out of 20 give the same frame, so this does not
    # make the suite flaky: only a red that does not always repeat, and a red
    # like that is a real bug. To reproduce it, `bsnes_entropy=None`.
    "bsnes": {"bsnes_video_gamma": "100", "bsnes_entropy": "High"},
}

# RETRO_DEVICE_JOYPAD, in the order libretro numbers them.
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


class AvInfo(ctypes.Structure):
    _fields_ = [("base_width", ctypes.c_uint), ("base_height", ctypes.c_uint),
                ("max_width", ctypes.c_uint), ("max_height", ctypes.c_uint),
                ("aspect_ratio", ctypes.c_float),
                ("fps", ctypes.c_double), ("sample_rate", ctypes.c_double)]


class Consola:

    def __init__(self, rom, core=CORE, opciones=None, msu=False):
        self.lib = ctypes.CDLL(core)
        self._forzadas = dict(opciones or {})
        self.formato = 0
        # The options the core declares, with their default value. Answering
        # "no such variable" is not the same as having no opinions: bsnes
        # leaves the luminance at zero and returns a black screen with the
        # audio playing anyway. A real frontend answers the first value of the
        # list, which is the default by libretro convention.
        self.opciones = {}
        self.cuadro = None          # (bytes, width, height, pitch) of the last one
        self.cuadros = 0
        self.apretados = set()
        self.audio = bytearray()

        info = SystemInfo()
        self.lib.retro_get_system_info(ctypes.byref(info))
        self.nombre = "%s %s" % (info.library_name.decode(),
                                 info.library_version.decode())
        # bsnes opens the file itself and does not even look at `data`. See
        # the docstring.
        pide_archivo = info.need_fullpath
        self._forzadas = dict(OPCIONES.get(info.library_name.decode(), {}),
                              **self._forzadas)

        datos = open(rom, "rb").read()
        # **Whoever creates the console decides the MSU-1, not the
        # directory.** The cores look for `<rom>.msu` and `<rom>-N.pcm` next to
        # the path they are given —bsnes in `program.cpp`, with the path's
        # `Location::notsuffix`—, and none has a libretro option not to. Since
        # `release/` carries the tracks, loading its `abl.sfc` as is made the
        # suite run with the SPC700 silenced or not depending on whether they
        # were built: with them, 1200 frames of the title screen give different
        # audio in snes9x and in bsnes. So by default the core receives a
        # **copy** in a directory of its own, empty. A copy and not a symlink:
        # snes9x and bsnes do not follow the link —measured—, but the copy does
        # not depend on what each core does and comes for free, because the
        # bytes are already read.
        #
        # And the system and save directory —mesen-s does not load without
        # it— is that same one: if it were the ROM's, a core looking there
        # would also find the tracks.
        if msu:
            ruta = os.path.abspath(rom)
        else:
            propio = tempfile.mkdtemp(prefix="retro-")
            # It is deleted when the console is collected, or at exit: there
            # is no `retro_deinit` marking the end. Each console has its own,
            # so two at once do not step on each other.
            weakref.finalize(self, shutil.rmtree, propio, True)
            ruta = os.path.join(propio, os.path.basename(rom))
            with open(ruta, "wb") as archivo:
                archivo.write(datos)
        self._directorio = ctypes.c_char_p(os.path.dirname(ruta).encode())

        # The callbacks are kept on self: if they are left as temporaries,
        # Python's collector frees them and the core calls into dead memory.
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

        # The environment one before retro_init, the rest after: it is
        # RetroArch's order, and the only one mesen-s does not crash with. See
        # the docstring.
        self.lib.retro_set_environment(self._env)
        self.lib.retro_init()
        self.lib.retro_set_video_refresh(self._video)
        self.lib.retro_set_audio_sample(self._audio_uno)
        self.lib.retro_set_audio_sample_batch(self._audio)
        self.lib.retro_set_input_poll(self._poll)
        self.lib.retro_set_input_state(self._state)

        self._buf = ctypes.create_string_buffer(datos, len(datos))
        juego = GameInfo(ruta.encode(),
                         None if pide_archivo
                         else ctypes.cast(self._buf, ctypes.c_void_p),
                         len(datos), None)
        # snes9x writes "Map_LoROMMap" to standard output when loading. It is a
        # printf from the core, not from Python, so silencing it requires
        # moving the descriptor and not redirecting sys.stdout. It would
        # clutter the log of every case in the suite. And libc's buffer has to
        # be flushed before restoring the descriptor: the printf does not write
        # right away, it stays in the buffer and only comes out when the
        # process ends, that is, when the redirection is no longer there.
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
            raise SystemExit("the core could not load %s" % rom)

    def _on_env(self, cmd, data):
        if cmd == ENV_SET_VARIABLES and data:
            arr = ctypes.cast(data, ctypes.POINTER(Variable))
            i = 0
            while arr[i].key:
                texto = arr[i].value.decode()
                # "Description; one|two|three" -> the default is the first.
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
            # The core keeps the pointer, so the bytes object has to outlive
            # this call.
            self._vivas[clave] = self.opciones[clave].encode()
            var[0].value = self._vivas[clave]
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.formato = ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0]
            return self.formato in FORMATOS
        if cmd == ENV_GET_OVERSCAN:
            # No cropping: we want the whole framebuffer, which is what the
            # console captures, not what a television would let through.
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = True
            return True
        if cmd == ENV_GET_CAN_DUPE:
            # Yes: a repeated frame arrives with data set to NULL and
            # `_on_video` keeps the previous one, which is exactly what the
            # console shows.
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
            self.audio += ctypes.string_at(data, frames * 4)   # 2 s16 channels
        return frames

    def _on_state(self, port, device, index, ident):
        return 1 if (port == 0 and ident in self.apretados) else 0

    def apretar(self, *nombres):
        """Which buttons are held from now on."""
        self.apretados = {BOTONES[n] for n in nombres}

    def correr(self, cuadros=1):
        for _ in range(cuadros):
            self.lib.retro_run()

    def tasa(self):
        """At how many samples per second the core delivers the audio.

        It is not a constant of the console but of each core and each load:
        bsnes gives 48000, and snes9x gives 32040 without MSU-1 and **44100
        with it**, because then it mixes at the tracks' rate. Whoever writes
        `audio` to a wav has to ask for it, or the sound drifts from the video.
        """
        info = AvInfo()
        self.lib.retro_get_system_av_info(ctypes.byref(info))
        return info.sample_rate

    # The emulator's WRAM, which is the only way to look inside without a
    # debugger. libretro exposes it with `retro_get_memory_data(2)`, which is
    # RETRO_MEMORY_SYSTEM_RAM; the three cores implement it.
    #
    # It is not part of any test: it is for debugging, and it showed up while
    # building the text compositor, when the screen said "something is wrong"
    # and not where.
    #
    # **Upstream bsnes does not expose it**: `retro_get_memory_data` returns
    # null for every id —`bsnes/target-libretro/libretro.cpp:1039`— even
    # though the rest of the interface works. This used to say the three cores
    # implemented it and that is not true; the tick clock uncovered it, since
    # it reads it to know which tick the ROM is on. The core installed in this
    # container is a custom build with that fixed; see `/extras/bsnes-wram/`.
    # Without that fix the clock falls back to counting frames, which still
    # works.
    MEMORIA_SISTEMA = 2
    # And the cartridge's SRAM, which is what a frontend saves to disk and what
    # the EverDrive keeps with a battery. `RETRO_MEMORY_SAVE_RAM` is 0, and bsnes
    # returns this one as null too: snes9x reads it, which is the suite's core.
    MEMORIA_SRAM = 0
    # And the PPU's VRAM, `RETRO_MEMORY_VIDEO_RAM`: 64 KB. snes9x exposes it,
    # which is the suite's core; upstream bsnes returns it as null just like
    # the WRAM.
    MEMORIA_VRAM = 3

    def sram(self, direccion=0, largo=None):
        """Bytes of the cartridge's SRAM.

        It is what lets "persisting to disk" be tested without a disk: the
        frontend dumps this very thing to a `.srm`, so what is here is what
        survives turning the console off.
        """
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_SRAM)
        total = self.lib.retro_get_memory_size(self.MEMORIA_SRAM)
        if not base or not total:
            raise RuntimeError("this core does not expose the cartridge's SRAM")
        if largo is None:
            largo = total - direccion
        return ctypes.string_at(base + direccion, largo)

    def escribir_sram(self, direccion, datos):
        """Writes bytes into the cartridge's SRAM: it is putting another
        `.srm` into the cartridge, like the one a previous build left. It
        exists to test that the ROM rejects a save file that is not in its
        format."""
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_SRAM)
        total = self.lib.retro_get_memory_size(self.MEMORIA_SRAM)
        if not base or not total:
            raise RuntimeError("this core does not expose the cartridge's SRAM")
        datos = bytes(datos)
        if direccion + len(datos) > total:
            raise ValueError("writing %d bytes at %d goes past the SRAM (%d)"
                             % (len(datos), direccion, total))
        ctypes.memmove(base + direccion, datos, len(datos))

    def reset(self):
        """The console's reset button: the SRAM survives and the WRAM does not.

        It is how a saved game is tested to really load: save, reset, and look
        at where the hero starts.
        """
        self.lib.retro_reset()
        self.cuadro = None

    def ram(self, direccion=0, largo=None):
        """Bytes of the WRAM from `direccion`, which is the one in bank $7E."""
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_SISTEMA)
        total = self.lib.retro_get_memory_size(self.MEMORIA_SISTEMA)
        if not base or not total:
            raise RuntimeError("this core does not expose the WRAM")
        if largo is None:
            largo = total - direccion
        return ctypes.string_at(base + direccion, largo)

    def vram(self, palabra=0, palabras=None):
        """Words of the VRAM, from the PPU's **word address**.

        It is asked for in words and not in bytes because that is how the 65816
        talks to the PPU: `VMADDL` is a word address, and the symbols of
        `tools/runtime/` —`VRAM_ABOVE_MAP`, `M_VRAM_MAP`— are written in those
        units. Asking for it in bytes would force everyone to remember the
        times two.

        It is the only thing that lets the tilemap be checked without looking
        at the screen: the map window is a torus and a PNG does not tell which
        cell ended up in which slot. `RETRO_MEMORY_VIDEO_RAM` is id 3.
        """
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_VRAM)
        total = self.lib.retro_get_memory_size(self.MEMORIA_VRAM)
        if not base or not total:
            raise RuntimeError("this core does not expose the VRAM")
        if palabras is None:
            palabras = total // 2 - palabra
        crudo = ctypes.string_at(base + palabra * 2, palabras * 2)
        return [crudo[i] | (crudo[i + 1] << 8) for i in range(0, len(crudo), 2)]

    def escribir_ram(self, direccion, datos):
        """Writes bytes into the WRAM, at the bank $7E address.

        The pointer `retro_get_memory_data` returns is the core's memory, not a
        copy, so writing to it is writing to the console.

        It exists for the state tests, which put the world in a situation the
        game reaches later —a switch turned on, for example— without having to
        build a different ROM for each one. **The pixel suite does not use it
        and must not use it**: there the comparison is against a reference that
        models the real path, and skipping that path would be comparing two
        things that did not go through the same thing.
        """
        self.lib.retro_get_memory_data.restype = ctypes.c_void_p
        self.lib.retro_get_memory_size.restype = ctypes.c_size_t
        base = self.lib.retro_get_memory_data(self.MEMORIA_SISTEMA)
        total = self.lib.retro_get_memory_size(self.MEMORIA_SISTEMA)
        if not base or not total:
            raise RuntimeError("this core does not expose the WRAM")
        datos = bytes(datos)
        if direccion + len(datos) > total:
            raise ValueError("writing %d bytes at %d goes past the WRAM (%d)"
                             % (len(datos), direccion, total))
        ctypes.memmove(base + direccion, datos, len(datos))

    def imagen(self):
        """The last frame as PIL, at 8 bits per channel and cropped to ALTO."""
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
