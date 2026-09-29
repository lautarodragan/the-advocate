"""Que ningún tema recorte, con el techo de cada uno que dice la tabla
versionada (`parches/auto/musica/techos.toml`), y que la tabla no esté vieja.

El DSP suma las ocho voces y satura la suma antes del volumen general, así
que lo que evita el recorte es el techo de cada voz, y desde el 2026-09-26
hay uno por tema: el más alto que no recorta, medido tocando cada tema en la
ROM —`just techos`, ver `rm2k-snes-volume-ceilings`—. Medirlo cuesta unos cuatro
minutos, así que acá no se mide: se cobra que lo medido siga valiendo.

* **La huella**: lo que el pico de un tema puede mover —lo que le escribe al
  DSP y las muestras que toca, ver `mix_fingerprint` en `rm2k-snes-audio`—
  tiene que ser lo que se midió. El paso 6 cambia las muestras y con ellas
  los picos; sin esto, la tabla quedaría vieja sin avisar.
* **Los que quedaron cerca del tope**, tocados en la ROM hasta pasar por su
  pico —el `hasta` de la tabla, no el tema entero—: ninguna muestra en el
  tope. Con la mezcla igual, lo único que mueve el pico es cuándo cae cada
  escritura dentro del cuadro, que cambia con cualquier cambio de la ROM:
  medido, del orden de 0,2 dB. Así que se tocan los que quedaron a menos de
  `CERCA` dB del tope, que son los que eso puede hacer recortar.
"""

import json
import os
import subprocess
import tomllib

import pytest

import tanda

from common import project

# A cuántos dB del tope un tema se toca en la prueba. La tabla los deja a
# 0,5 dB (`margin` en `rm2k-snes-audio`); lo que hace falta es que entren
# ésos con margen.
CERCA = 1.5

# El que mide los techos, y el que toca un tema solo con `--play`: la misma
# consola de libretro y las mismas cuentas con que se midió la tabla.
TECHOS = "rm2k-snes-volume-ceilings"


def _ruta():
    return os.path.join(project.auto_patches(), "musica", "techos.toml")


def _tabla():
    with open(_ruta(), "rb") as archivo:
        return tomllib.load(archivo)["temas"]


def _cerca():
    return sorted(n for n, fila in _tabla().items() if fila["pico"] > -CERCA)


def _hechos(directorio):
    """Los temas del cartucho como los armó el compilador, en el orden de sus
    índices: `musica.json`, al lado de `musicdata.inc`."""
    with open(os.path.join(directorio, "musica.json")) as archivo:
        return json.load(archivo)["temas"]


def _indice(directorio, nombre):
    """El índice del tema en el cartucho: la línea `; Songs:` de
    `musicdata.inc`, que es la que lee también el que mide."""
    with open(os.path.join(directorio, "musicdata.inc")) as archivo:
        for linea in archivo:
            if linea.startswith("; Songs: "):
                return linea[len("; Songs: "):].rstrip("\n").split(", ").index(nombre)
    raise AssertionError("musicdata.inc no dice sus temas")


def test_la_tabla_de_techos_es_la_de_esta_mezcla():
    release = tanda.cartucho()
    tabla = _tabla()
    hechos = {t["nombre"]: t for t in _hechos(release.dir) if t["largo"]}
    assert sorted(hechos) == sorted(tabla), (
        "los temas del release no son los de la tabla de techos: sobran %s, "
        "faltan %s. Correr `just techos`."
        % (sorted(set(tabla) - set(hechos)), sorted(set(hechos) - set(tabla))))
    viejos = [n for n, t in sorted(hechos.items())
              if t["huella"] != tabla[n]["huella"]]
    assert not viejos, (
        "la mezcla de %s cambió desde que se midió su techo, así que su pico "
        "ya no es el de la tabla: correr `just techos` y mirar el diff de %s"
        % (", ".join(viejos), os.path.relpath(_ruta())))


@pytest.mark.parametrize("nombre", _cerca())
def test_el_tema_no_recorta_en_su_pico(nombre):
    release = tanda.cartucho()
    fila = _tabla()[nombre]
    tema = _indice(release.dir, nombre)
    hecho = subprocess.run(
        [TECHOS, "--play", release.sfc, "--song", str(tema),
         "--frames", str(fila["hasta"])], capture_output=True, text=True)
    assert hecho.returncode == 0, hecho.stderr
    recortes = json.loads(hecho.stdout)["recortes"]
    assert not recortes, (
        "%s recorta %d muestras en sus primeros %d cuadros, con el aire en "
        "%.3f: correr `just techos`" % (nombre, recortes, fila["hasta"],
                                         fila["aire"]))
