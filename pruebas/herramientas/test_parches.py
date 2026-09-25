"""Los parches versionados dicen lo mismo que el conversor acaba de decidir.

Un parche es una **decisión artística**: qué color se fusionó con cuál porque
la CGRAM no daba para los dos, o a qué tamaño se achicó una animación de
batalla para entrar en la caja de la consola. Se toman solas, cambian lo que se
ve, y hasta que existió `parches/` no dejaban rastro: si un cambio hacía que un
mapa perdiera dos colores más, la única forma de enterarse era mirar la ROM.

Esto es a las decisiones lo que las goldens son a los pixeles, y por eso falla
diciendo **qué decisión cambió** y no "el archivo difiere": ver `diferencias`
en `port/parches.py`. Cuando el cambio es el buscado, se corre `just parches`
y el diff va al commit, que es donde alguien lo mira.

No arranca ninguna ROM: compara lo que dejaron escrito los cartuchos que armó
`just cartuchos` contra lo commiteado. Y los compara **todos**, que es lo que
sostiene que el cartucho no entre en la clave —medido el 2026-09-21, con las
capas y con las animaciones: los tres cartuchos de prueba y `abl` emiten los
mismos archivos byte por byte—.

Lo versionado es lo que decide `abl`, el ROM jugable. Lo que los cartuchos de
prueba llevan de más —mapas que el juego no tiene, y una animación que sólo
muestra un caso de la tanda— no se versiona: ahí el cartucho decide solo y esto
no le pide nada; cuáles son los imprime `just parches-check`. De `abl`, en
cambio, exige que todo lo que convierte esté versionado.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from port import animacion                                    # noqa: E402
from port import parches                                      # noqa: E402

from ensamblado import cartuchos                             # noqa: E402


def _armados():
    """Los cartuchos que dejó `just cartuchos`, con sus parches adentro.

    `release` también, y es el que más importa: es el único del que
    `parches.revisar` exige que todo lo que convierte esté versionado. Vive
    fuera de `DESTINO`, así que listar ese directorio no lo encontraba.
    """
    candidatos = ([os.path.join(cartuchos.DESTINO, nombre)
                   for nombre in sorted(os.listdir(cartuchos.DESTINO))]
                  + [cartuchos.directorio(cartuchos.RELEASE)])
    return [c for c in candidatos
            if os.path.isdir(os.path.join(c, parches.EN_BUILD))]


def test_los_parches_versionados_son_los_que_decide_el_conversor():
    armados = _armados()
    assert cartuchos.directorio(cartuchos.RELEASE) in armados, (
        "`release` no dejó parches en %s: se arma con `just cartuchos`, y sin "
        "él nada mira que lo que el juego convierte esté versionado"
        % cartuchos.directorio(cartuchos.RELEASE))
    quejas, _propios = parches.revisar(RAIZ, armados)
    assert not quejas, "\n\n".join(quejas)


def test_el_tamano_de_cada_animacion_versionada_sale_de_su_caja_y_de_nada_mas():
    """Lo versionado de una animación se lee como lo va a leer la fase 2.

    Y de paso sostiene lo que hace que el número de animación alcance como
    clave: el tamaño es función de la caja que la animación ocupa en RM2k y de
    la caja de la consola, que es una sola para toda la ROM. Si algún día
    dependiera del mapa —de la VRAM que le quede—, dos cartuchos con los
    mismos mapas podrían decidir distinto y esta cuenta dejaría de dar.
    """
    clase = dict((c.clave, c) for c in parches.CLASES)["animacion"]
    numeros = parches.versionados(RAIZ, clase)
    assert numeros, "no hay ninguna animación versionada en %s" % clase.directorio
    for numero in numeros:
        doc = parches.leer_animacion(RAIZ, numero)
        assert doc["animacion"] == numero
        assert tuple(doc["tamano"]) == animacion.tamano(*doc["original"]), (
            "la animación %d dice que se dibuja a %s y su caja de %s da %s"
            % (numero, doc["tamano"], doc["original"],
               animacion.tamano(*doc["original"])))
        assert max(doc["tamano"]) <= animacion.CAJA
