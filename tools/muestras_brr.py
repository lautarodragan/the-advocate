"""De dónde salen las muestras del port, y cómo llegan a BRR.

Acá no hay ni códec ni lector de SoundFont: los dos son `brr/`, el binario de
Rust, y este módulo es el puente entre él y el conversor. Lo que sí hay es lo
que el binario no puede tener, porque no sabe nada de este juego: el caché en
disco del conversor y la memoria de lo ya pedido.

**Las dos memorias son lo que hace viable un proceso por muestra.** Medido el
2026-09-15 sobre una conversión entera de `demo-ciudad` con `SIN_CACHE=1`: el
conversor pide 34.493 codificaciones para **608 muestras distintas** y 70.279
zonas del SoundFont para **100 selectores distintos**. Sin memoria serían
104.772 arranques de proceso; con ella son 708, y las 708 —binario, archivos
temporales y todo— cuestan **1,33 s** de una conversión de 102 s.

Por eso **no hay un modo por lotes**, que era la otra forma de hacer esto.
Arrancar el binario cuesta 0,0005 s —0,30 s las 608, medidas sueltas—, así que
juntar todas las muestras en una sola invocación ahorraría 0,35 s de esos
102 s: menos del medio por ciento, a cambio de un modo más en `brr/`. Y encima
no se pueden juntar del todo: `snes_samples.build_bank` decide el presupuesto
de la muestra siguiente mirando cuánto ocupó la anterior, así que los trabajos
no existen todos juntos en ningún momento.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cache_disco

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRR = os.path.join(RAIZ, "brr")
BINARIO = os.environ.get("ABL_BRR",
                         os.path.join(BRR, "target", "release", "brr"))

# El mismo texto que da la receta `brr-binario`, por lo mismo que en
# `w65_bin.py`: el que corre pytest directo se choca con esto y no con ella.
FALTA_CARGO = (
    "falta cargo: desde el 2026-09-15 el códec BRR y el lector de SoundFont\n"
    "son un binario de Rust (brr/) y hay que compilarlo para armar las\n"
    "muestras de la ROM.\n"
    "  en Arch:   pacman -S rust   (o rustup, y 'rustup default stable')\n"
    "  y después: just brr-binario")

# Propiedades del formato, no nuestras: el DSP lee bloques de nueve bytes que
# guardan dieciséis muestras, y vuelve del loop al principio de uno.
BLOQUE_MUESTRAS = 16
BLOQUE_BYTES = 9

# Lo que le da la clave al caché en disco. Van los fuentes del codificador y
# este archivo: si cambia cualquiera de los dos, lo guardado deja de valer. El
# binario compilado no entra a propósito —cambia con cada versión del
# compilador sin que el BRR cambie—, y tampoco `Cargo.lock`, que hoy no tiene
# ninguna dependencia que toque las muestras.
FUENTES = ("brr/src/codec.rs", "brr/src/wav.rs", "brr/Cargo.toml",
           "tools/muestras_brr.py")


class Error(Exception):
    """El binario contestó que no, o la llamada estaba mal."""


_version = None
_codificadas = {}
_extraidas = {}
_compilado = False


def binario():
    """La ruta al códec, ya compilado y al día.

    Igual que `w65_bin.binario()` y por la misma razón: las recetas que
    convierten de arriba de todo dependen de `brr-binario`, pero **pytest no
    tiene recetas** —`python3 -m pytest pruebas` convierte mapas, y convertir
    un mapa codifica muestras—, y las recetas que convierten llamando a otra
    tampoco la tienen. Se compila a pedido y una sola vez por proceso.
    """
    global _compilado
    if _compilado or "ABL_BRR" in os.environ:
        return BINARIO

    if shutil.which("cargo") is None:
        # Sin cargo no se puede comprobar que esté al día, pero quien no tiene
        # cargo tampoco tiene cómo haber cambiado los fuentes de Rust.
        if os.path.exists(BINARIO):
            _compilado = True
            return BINARIO
        raise SystemExit(FALTA_CARGO)

    subprocess.run(["cargo", "build", "--release", "--quiet"],
                   check=True, cwd=BRR)
    _compilado = True
    return BINARIO


def _correr(args):
    """El binario, con sus dos códigos de salida separados del resto.

    1 y 2 son respuestas suyas —"no hay nada que matchee" y "la llamada está
    mal"—; cualquier otra cosa es que no se lo pudo correr, y ahí conviene
    decir cómo se compila antes que dejar un "command not found" suelto.
    """
    try:
        hecho = subprocess.run([binario()] + args, capture_output=True)
    except OSError as e:
        # Un SystemExit y no una excepción: que falte el binario no es un error
        # de programa, es que hay que compilarlo, y un traceback de veinte
        # líneas tapa la única línea que dice cómo.
        raise SystemExit("no se pudo correr %s: %s\n\n%s"
                         % (BINARIO, e, FALTA_CARGO))
    if hecho.returncode:
        raise Error("%s salió con %d: %s"
                    % (" ".join([os.path.basename(BINARIO)] + args),
                       hecho.returncode,
                       hecho.stderr.decode("utf-8", "replace").strip()))
    return hecho.stdout.decode("utf-8", "replace")


def _json(texto):
    """La última línea que el binario imprimió con `--json`.

    Es un objeto de escalares y nada más —así lo emite `brr`—, así que el
    módulo `json` alcanza y sobra.
    """
    import json
    for linea in reversed(texto.strip().splitlines()):
        if linea.startswith("{"):
            return json.loads(linea)
    raise Error("el binario no imprimió JSON: %r" % texto[:200])


def codificar(muestras, loop_block=None):
    """Una muestra entera a BRR, con el punto de loop en el bloque que se diga.

    La entrada va cruda —enteros de 16 bits con signo, sin cabecera—, que es lo
    que el binario lee cuando el archivo no empieza con `RIFF`: escribir un WAV
    para algo que ya está en memoria sería cabecera de más.
    """
    if not muestras:
        # El conversor pide esto cuando un instrumento se quedó sin ataque, y
        # la respuesta honesta es cero bloques; el binario, en cambio, rechaza
        # una entrada vacía, que es lo correcto para alguien que le pasa un
        # archivo.
        return b""

    global _version
    clave = (tuple(muestras), loop_block)
    hecha = _codificadas.get(clave)
    if hecha is not None:
        return hecha

    if _version is None:
        _version = cache_disco.version_de_fuentes(*FUENTES)
    en_disco = cache_disco.clave(_version, str(loop_block),
                                 " ".join(str(x) for x in clave[0]))
    hecha = cache_disco.leer("brr", en_disco)
    if hecha is None:
        hecha = _codificar(muestras, loop_block)
        cache_disco.guardar("brr", en_disco, hecha)
    _codificadas[clave] = hecha
    return hecha


def _codificar(muestras, loop_block):
    with tempfile.TemporaryDirectory(prefix="abl-brr-") as donde:
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
    """Lo que el SoundFont trae de un instrumento, ya extraído.

    `pcm` son los cuadros crudos, y `loop_start`/`loop_end` están en cuadros y
    relativos a ellos: afuera del archivo el loop no significa nada en las
    coordenadas de adentro.
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
        return "<Muestra %r %d cuadros a %d Hz>" % (self.nombre, self.cuadros,
                                                    self.tasa)


def extraer(selector, soundfont):
    """Un instrumento del SoundFont, o None si el banco no lo tiene.

    El selector es el del binario: `program:N`, `program:N@NOTA` o `drum:N`.
    Que no haya nada es una respuesta y no un error —el binario sale con 1— y
    acá se vuelve un None, que es lo que el conversor ya sabía manejar.
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
            if "salió con 1" in str(e):
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


def presets(soundfont):
    """Los presets que declara el banco: (banco, programa, nombre)."""
    salida = _correr(["sf2", soundfont, "--list", "--json"])
    import json
    filas = [json.loads(l) for l in salida.splitlines() if l.startswith("{")]
    return [(f["bank"], f["program"], f["name"]) for f in filas]
