"""Where the port's samples come from, and how they get to BRR.

There is neither a codec nor a SoundFont reader here: both are Gunter
—`tools/gunter/`, the Rust binary—, and this module is the bridge between it
and the converter. What there is here is what the binary cannot have,
because it knows nothing about this game: the converter's disk cache and the
memory of what has already been asked for.

What is cached here is **the BRR**. The already prepared sample —the
resampling and normalization that come before— is cached by `snes_samples`,
in another category and with another key; the two expire together because
both carry `version()`.

**The two memories are what make one process per sample viable.** Measured
on 2026-09-15 over a whole conversion of `abl` with `SIN_CACHE=1`: the
converter asks for 34,493 encodings for **608 distinct samples** and 70,279
SoundFont zones for **100 distinct selectors**. Without memory that would be
104,772 process launches; with it they are 708, and the 708 —binary,
temporary files and all— cost **1.33 s** of a 102 s conversion.

That is why **there is no batch mode**, which was the other way to do this.
Launching the binary costs 0.0005 s —0.30 s for the 608, measured one by
one—, so gathering all the samples into a single invocation would save
0.35 s, in exchange for one more mode in Gunter. And on top of that they
cannot be gathered completely: `snes_music`'s `Banco` rebuilds the samples
of a package that went over by looking at how much they took, so the jobs
never all exist together at any point.

What has changed since that measurement is what those 0.35 s are compared
against: the prepared-sample cache of 2026-09-20 took away half of the
conversion, so today it weighs quite a bit more than it did. It is still not
enough, but if anyone ever looks again at where the time goes, this is no
longer a negligible number.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import wave

from common import cache_disco

FALTA = """`gunter`, the SPC700 sample codec, is missing.

It is a Rust binary that lives in `tools/gunter/` and is installed as a system
tool, not built on every run:

    just -f tools/justfile herramientas

That does `cargo install --locked --path tools/gunter`. If cargo is missing, on
Arch it is `pacman -S rust`."""

# Properties of the format, not ours: the DSP reads nine-byte blocks that
# hold sixteen samples, and loops back to the start of one.
BLOQUE_MUESTRAS = 16
BLOQUE_BYTES = 9


class Error(Exception):
    """The binary said no, or the call was wrong."""


_version = None
_codificadas = {}
_extraidas = {}


def binario():
    """The path of the `gunter` on the PATH, like `ensamblar.binarios()`.

    Raises `SystemExit` if it is not there: a missing system tool is not a
    program error, and a twenty-line traceback buries the only line that says
    how to get it.
    """
    ruta = shutil.which("gunter")
    if ruta is None:
        raise SystemExit(FALTA)
    return ruta


def version():
    """Which version of "the encoder" produced what is in the cache.

    It covers this file and **the installed binary**, not the sources in
    `tools/gunter/`: the binary on the PATH is installed separately, so a tree
    with `tools/gunter/src` touched and without `just herramientas` run keeps
    encoding with the old one. What the key has to describe is what produced
    the bytes.

    It is public because `snes_samples` caches **the already prepared
    sample** —the resampling and normalization that come before encoding— and
    that also comes out of this binary: its key has to expire when this one's
    does.
    """
    global _version
    if _version is None:
        h = hashlib.sha256()
        for ruta in (os.path.abspath(__file__), binario()):
            with open(ruta, "rb") as f:
                h.update(f.read())
        _version = h.hexdigest()
    return _version


def _correr(args):
    """The binary, with its two exit codes kept apart from the rest.

    1 and 2 are its own answers —"nothing matches" and "the call is wrong"—;
    anything else means it could not be run.
    """
    try:
        hecho = subprocess.run([binario()] + args, capture_output=True)
    except OSError as e:
        raise SystemExit("could not run `gunter`: %s\n\n%s" % (e, FALTA))
    if hecho.returncode:
        raise Error("gunter %s exited with %d: %s"
                    % (" ".join(args), hecho.returncode,
                       hecho.stderr.decode("utf-8", "replace").strip()))
    return hecho.stdout.decode("utf-8", "replace")


def _json(texto):
    """The last line the binary printed with `--json`.

    It is an object of scalars and nothing else —that is how `gunter` emits
    it—, so the `json` module is more than enough.
    """
    import json
    for linea in reversed(texto.strip().splitlines()):
        if linea.startswith("{"):
            return json.loads(linea)
    raise Error("the binary printed no JSON: %r" % texto[:200])


def codificar(muestras, loop_block=None):
    """A whole sample to BRR, with the loop point at the given block.

    The input goes raw —signed 16-bit integers, no header—, which is what the
    binary reads when the file does not start with `RIFF`: writing a WAV for
    something already in memory would be a needless header.
    """
    if not muestras:
        # The converter asks for this when an instrument was left without an
        # attack, and the honest answer is zero blocks; the binary, on the
        # other hand, rejects an empty input, which is correct for someone
        # passing it a file.
        return b""

    clave = (tuple(muestras), loop_block)
    hecha = _codificadas.get(clave)
    if hecha is not None:
        return hecha

    en_disco = cache_disco.clave(version(), str(loop_block),
                                 " ".join(str(x) for x in clave[0]))
    hecha = cache_disco.leer("brr", en_disco)
    if hecha is None:
        hecha = _codificar(muestras, loop_block)
        cache_disco.guardar("brr", en_disco, hecha)
    _codificadas[clave] = hecha
    return hecha


def _codificar(muestras, loop_block):
    with tempfile.TemporaryDirectory(prefix="abl-gunter-") as donde:
        entrada = os.path.join(donde, "pcm")
        salida = os.path.join(donde, "brr")
        with open(entrada, "wb") as f:
            for s in muestras:
                f.write(int(s).to_bytes(2, "little", signed=True))
        args = [entrada, "-o", salida]
        if loop_block is not None:
            args += ["--loop-block", str(loop_block)]
        _correr(["encode"] + args)
        with open(salida, "rb") as f:
            return f.read()


class Muestra:
    """What the SoundFont has for an instrument, already extracted.

    `pcm` are the raw frames, and `loop_start`/`loop_end` are in frames and
    relative to them: outside the file the loop means nothing in the
    coordinates inside it.
    """

    def __init__(self, campos, pcm):
        self.nombre = campos["name"]
        self.cuadros = campos["frames"]
        self.tasa = campos["rate"]
        self.nota = campos["root_key"]
        self.cents = campos["tuning_cents"]
        self.loop = bool(campos["loops"])
        self.loop_start = campos["loop_start"] or 0
        self.loop_end = campos["loop_end"] or 0
        self.pcm = pcm

    def __repr__(self):
        return "<Muestra %r %d frames at %d Hz>" % (self.nombre, self.cuadros,
                                                    self.tasa)


_envolventes = {}
# The volume envelope fields `gunter sf2 --json` returns, generators 33 to 40
# already resolved —the instrument zone plus the preset's, with the
# specification's defaults and caps—. In SoundFont units: timecents, and
# centibels for the sustain.
CAMPOS_ENVOLVENTE = ("env_delay_timecents", "env_attack_timecents",
                     "env_hold_timecents", "env_decay_timecents",
                     "env_sustain_centibels", "env_release_timecents",
                     "env_key_to_hold", "env_key_to_decay")


def _contrato(selector, soundfont):
    """What `gunter sf2 --extract --json` says about the zone the selector
    picks, without extracting the PCM, or None if the bank has nothing there.

    It is one call per zone and is not cached on disk: without `-o` the
    binary writes nothing and answers in under a millisecond.
    """
    clave = (selector, soundfont)
    if clave not in _contratos:
        try:
            _contratos[clave] = _json(_correr(["sf2", soundfont, "--extract",
                                               selector, "--json"]))
        except Error as e:
            if "exited with 1" not in str(e):
                raise
            _contratos[clave] = None
    return _contratos[clave]


_contratos = {}


def precargar(selectores, soundfont):
    """Asks at once for the contracts of those selectors not yet asked for.

    It is the same call as `_contrato`, one per zone, but in threads: each one
    is a process of under a millisecond and the converter asks for one per
    program and key that plays, so serially what was being paid for was
    waiting for the binary to start.
    """
    import concurrent.futures
    faltan = [s for s in dict.fromkeys(selectores)
              if (s, soundfont) not in _contratos]
    if len(faltan) < 2:
        return
    with concurrent.futures.ThreadPoolExecutor(os.cpu_count() or 1) as hilos:
        for _hecho in hilos.map(lambda s: _contrato(s, soundfont), faltan):
            pass


def zona(selector, soundfont):
    """(sample name, its root key) of the zone the selector picks, or None.
    It is what tells one zone from another without extracting it."""
    campos = _contrato(selector, soundfont)
    return (campos["name"], campos["root_key"]) if campos else None


def envolvente(selector, soundfont):
    """The volume envelope of the zone the selector picks, as a dict with
    `CAMPOS_ENVOLVENTE`, or None if the bank has nothing there."""
    clave = (selector, soundfont)
    if clave not in _envolventes:
        campos = _contrato(selector, soundfont)
        if campos is not None:
            if any(c not in campos for c in CAMPOS_ENVOLVENTE):
                raise SystemExit("the `gunter` on the PATH (%s) does not "
                                 "return the SoundFont envelope: it predates "
                                 "2026-09-25. Reinstall it with `just "
                                 "herramientas`." % binario())
            campos = {c: campos[c] for c in CAMPOS_ENVOLVENTE}
        _envolventes[clave] = campos
    return _envolventes[clave]


def extraer(selector, soundfont):
    """An instrument from the SoundFont, or None if the bank does not have it.

    The selector is the binary's: `program:N`, `program:N@NOTE` or `drum:N`.
    Nothing being there is an answer and not an error —the binary exits with
    1— and here it becomes a None, which is what the converter already knew
    how to handle.
    """
    clave = (selector, soundfont)
    if clave in _extraidas:
        return _extraidas[clave]

    with tempfile.TemporaryDirectory(prefix="abl-sf2-") as donde:
        salida = os.path.join(donde, "pcm.wav")
        try:
            texto = _correr(["sf2", soundfont, "--extract", selector,
                             "-o", salida, "--json"])
        except Error as e:
            if "exited with 1" in str(e):
                _extraidas[clave] = None
                return None
            raise
        campos = _json(texto)
        with wave.open(salida, "rb") as w:
            crudo = w.readframes(w.getnframes())
        pcm = [int.from_bytes(crudo[i:i + 2], "little", signed=True)
               for i in range(0, len(crudo), 2)]

    muestra = Muestra(campos, pcm)
    _extraidas[clave] = muestra
    return muestra
