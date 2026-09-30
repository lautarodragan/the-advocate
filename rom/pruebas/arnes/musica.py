"""La música del juego, como la ve el que la compila.

Las pruebas de música no importan el compilador: le preguntan a
`rm2k-snes-audio` lo que necesitan, en JSON —que arme el banco con tales
temas y tales paquetes, qué escribe un stream al DSP, cómo se lee un WAV—,
igual que `cartuchos.py` le pregunta al que arma. Hasta el 2026-09-29 el
compilador era de Python y las pruebas lo importaban, y dependían de cómo
estaba escrito por dentro.

Lo de la máquina —dónde están el juego, el RTP y el SoundFont— sale de
`lugares`, como para el resto de la tanda.
"""

import functools
import json
import os
import subprocess
import tempfile

import lugares

from common import environment

AUDIO = "rm2k-snes-audio"


def _correr(*args, entrada=None):
    hecho = subprocess.run([AUDIO, *args], capture_output=True)
    if hecho.returncode:
        raise AssertionError("%s %s falló:\n%s" % (
            AUDIO, " ".join(args), hecho.stderr.decode("utf-8", "replace")))
    return hecho.stdout


def _del_juego(*args):
    """El ejecutable con el juego, su RTP y este proyecto."""
    return _correr(*args, "--project", lugares.ABL,
                   *environment.as_flags("game_dir", "rtp_dir"))


@functools.lru_cache(maxsize=None)
def constantes():
    """Los números del motor con que calculan las pruebas: `headroom`,
    `master`, `directory_max`, `ticks_per_second`, y los registros del DSP
    que miran —`kon`, `v_srcn`— y los bytes de un bloque de BRR."""
    return json.loads(_correr("constants"))


def msu_indice(msu):
    """Las entradas del `.msu` con datos `msu` —sus bytes—, como `(dónde,
    largo)`; falla si no es uno válido de este juego. El formato es de
    `rm2k-snes-audio` (`msu_data.rs`), y las pruebas se lo preguntan en vez
    de tener otra copia."""
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "datos.msu")
        with open(ruta, "wb") as archivo:
            archivo.write(msu)
        return [tuple(e) for e in json.loads(
            _correr("msu-index", ruta, "--project", lugares.ABL))]


def msu_entradas(msu):
    """Los bytes de cada entrada del `.msu`, en el orden del índice."""
    return [msu[donde:donde + largo] for donde, largo in msu_indice(msu)]


def msu_firmado(msu):
    """El mismo `.msu` con la firma recalculada: con otros bytes adentro, es
    el `.msu` bien formado de otro build."""
    with tempfile.TemporaryDirectory() as carpeta:
        ruta, otro = (os.path.join(carpeta, n) for n in ("a.msu", "b.msu"))
        with open(ruta, "wb") as archivo:
            archivo.write(msu)
        _correr("msu-sign", ruta, "--out", otro)
        with open(otro, "rb") as archivo:
            return archivo.read()


def msu_fondo(k):
    """Dónde están los tiles del fondo `k` en el `.msu`: su lugar fijo."""
    c = constantes()
    return c["msu_backdrops_start"] + k * c["msu_backdrop_span"]


class Banco:
    """El banco de muestras compartido, como lo dejó `compile`: sus claves
    —`p:programa:tecla`, `g:golpe`, y las copias con `@grupo`—, cuánto pesa
    cada muestra, qué muestra toca cada tema de cada clave y qué paquete
    limitó a cada una."""

    def __init__(self, dato):
        self.keys = dato["keys"]
        self.voices = dato["voices"]
        self.assignment = dato["assignment"]
        self.limited_by = dato["limited_by"]
        self.melodic = {int(p): i for p, i in dato["melodic"].items()}
        self.hits = {int(k): i for k, i in dato["hits"].items()}
        self.constraints = dato["constraints"]

    def takes(self, claves):
        """Cuánto ocupan en la ARAM las muestras de esas claves."""
        return sum(v["bytes"] for k, v in zip(self.keys, self.voices)
                   if k in claves)


def compilar(temas, paquetes=None, herencia=(), aire=None,
             fin_de_la_aram=None):
    """La música de esos temas, como la compila el conversor, con el detalle
    de cada tema —sus notas, sus escrituras, su reparto de voces—.

    `paquetes` son `[(nombre, temas, efectos)]`; sin ellos, cada tema es un
    paquete. `herencia` son `[(paquete, tema que puede venir sonando)]`.
    `aire` es el de todos los temas en vez del techo de cada uno, y
    `fin_de_la_aram` achica la ARAM, para las pruebas que quieren que no
    entre todo.

    Devuelve (los temas de `audio.json`, el banco, lo que sobra en cada
    paquete para muestras)."""
    pedido = {"songs": list(temas),
              "inheritance": [list(h) for h in herencia],
              "measuring_headroom": aire}
    if paquetes is not None:
        pedido["packages"] = [{"name": n, "songs": list(t), "effects": list(e)}
                              for n, t, e in paquetes]
    with tempfile.TemporaryDirectory(prefix="abl-musica-") as carpeta:
        ruta = os.path.join(carpeta, "pedido.json")
        with open(ruta, "w") as archivo:
            json.dump(pedido, archivo)
        extra = (["--aram-end", str(fin_de_la_aram)]
                 if fin_de_la_aram is not None else [])
        _del_juego("compile", "--job", ruta, "--out", carpeta, "--detail",
                   *environment.as_flags("soundfont"), *extra)
        with open(os.path.join(carpeta, "audio.json")) as archivo:
            hecho = json.load(archivo)
    return hecho["songs"], Banco(hecho["bank"]), hecho["free"]


def claves(temas):
    """(las claves que pide cada tema, {clave: cuánto pesa su muestra
    entera}): lo que pesa todo antes de repartir la ARAM."""
    hecho = json.loads(_del_juego("keys", *temas,
                                  *environment.as_flags("soundfont")))
    return [set(ks) for ks in hecho["songs"]], hecho["natives"]


def decodificar(flujo, sonidos):
    """Lo que escribe al DSP el stream que empieza en `flujo` —bytes, que
    pueden seguir después de su `OP_END`—, con esos sonidos de seis bytes:
    ([(cuadro, registro, valor)], cuántos bytes ocupa, su `OP_END`
    incluido). Es el modelo de `music_frame`."""
    with tempfile.TemporaryDirectory(prefix="abl-stream-") as carpeta:
        ruta_flujo = os.path.join(carpeta, "stream")
        ruta_sonidos = os.path.join(carpeta, "sonidos")
        with open(ruta_flujo, "wb") as archivo:
            archivo.write(bytes(flujo))
        with open(ruta_sonidos, "wb") as archivo:
            archivo.write(b"".join(bytes(s) for s in sonidos))
        hecho = json.loads(_correr("decode", "--stream", ruta_flujo,
                                   "--sounds", ruta_sonidos))
    return [tuple(e) for e in hecho["writes"]], hecho["length"]


def wav(nombre):
    """(las muestras, la tasa) del WAV de un efecto, como lo lee el
    compilador: en mono y en enteros de dieciséis bits."""
    hecho = json.loads(_del_juego("wav", nombre))
    return hecho["samples"], hecho["rate"]


def archivo_del_tema(nombre):
    """Dónde está el archivo de un tema —el del juego, o el del RTP—, o
    None si no está en ninguno de los dos."""
    hecho = subprocess.run(
        [AUDIO, "find-song", nombre, "--project", lugares.ABL,
         *environment.as_flags("game_dir", "rtp_dir")],
        capture_output=True, text=True)
    if hecho.returncode == 1:
        return None
    if hecho.returncode:
        raise AssertionError("%s find-song falló:\n%s" % (AUDIO, hecho.stderr))
    return hecho.stdout.strip()


def altura_de_efecto(tasa, tempo):
    """El registro de altura del DSP de un efecto a esa tasa y ese tempo."""
    return int(_correr("pitch", "--rate", str(tasa), "--tempo", str(tempo)))
