"""Que ningún tema recorte, con el techo de cada uno que dice la tabla
versionada (`parches/auto/musica/techos.toml`), y que la tabla no esté vieja.

El DSP suma las ocho voces y satura la suma antes del volumen general, así
que lo que evita el recorte es el techo de cada voz, y desde el 2026-09-26
hay uno por tema: el más alto que no recorta, medido tocando cada tema en la
ROM —`just techos`, ver tools/audio/techos.py—. Medirlo cuesta unos cuatro
minutos, así que acá no se mide: se cobra que lo medido siga valiendo.

* **La huella**: lo que el pico de un tema puede mover —lo que le escribe al
  DSP y las muestras que toca, ver `huella_de_la_mezcla`— tiene que ser lo
  que se midió. El paso 6 cambia las muestras y con ellas los picos; sin
  esto, la tabla quedaría vieja sin avisar.
* **Los que quedaron cerca del tope**, tocados en la ROM hasta pasar por su
  pico —el `hasta` de la tabla, no el tema entero—: ninguna muestra en el
  tope. Con la mezcla igual, lo único que mueve el pico es cuándo cae cada
  escritura dentro del cuadro, que cambia con cualquier cambio de la ROM:
  medido, del orden de 0,2 dB. Así que se tocan los que quedaron a menos de
  `CERCA` dB del tope, que son los que eso puede hacer recortar.
"""

import os
import tomllib

import pytest

import tanda

from audio import snes_music, techos

# A cuántos dB del tope un tema se toca en la prueba. La tabla los deja a
# 0,5 dB (`techos.MARGEN`); lo que hace falta es que entren ésos con margen.
CERCA = 1.5


def _tabla():
    with open(snes_music.TECHOS, "rb") as archivo:
        return tomllib.load(archivo)["temas"]


def _cerca():
    return sorted(n for n, fila in _tabla().items() if fila["pico"] > -CERCA)


def test_la_tabla_de_techos_es_la_de_esta_mezcla():
    release = tanda.cartucho()
    tabla = _tabla()
    hechos = {t["nombre"]: t for t in techos.temas_armados(release.dir)
              if t["largo"]}
    assert sorted(hechos) == sorted(tabla), (
        "los temas del release no son los de la tabla de techos: sobran %s, "
        "faltan %s. Correr `just techos`."
        % (sorted(set(tabla) - set(hechos)), sorted(set(hechos) - set(tabla))))
    viejos = [n for n, t in sorted(hechos.items())
              if t["huella"] != tabla[n]["huella"]]
    assert not viejos, (
        "la mezcla de %s cambió desde que se midió su techo, así que su pico "
        "ya no es el de la tabla: correr `just techos` y mirar el diff de %s"
        % (", ".join(viejos), os.path.relpath(snes_music.TECHOS)))


@pytest.mark.parametrize("nombre", _cerca())
def test_el_tema_no_recorta_en_su_pico(nombre):
    release = tanda.cartucho()
    fila = _tabla()[nombre]
    tema = techos.temas_de(release.dir).index(nombre)
    muestras, _tasa = techos.tocar(release.sfc, tema, fila["hasta"])
    recortes = techos.recortes(muestras)
    assert not recortes, (
        "%s recorta %d muestras en sus primeros %d cuadros, con el aire en "
        "%.3f: correr `just techos`" % (nombre, recortes, fila["hasta"],
                                         fila["aire"]))
