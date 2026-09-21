"""Los parches versionados dicen lo mismo que el conversor acaba de decidir.

Un parche es una **decisión artística**: qué color se fusionó con cuál porque
la CGRAM no daba para los dos. Se toman solas, cambian lo que se ve, y hasta
que existió `parches/` no dejaban rastro: si un cambio hacía que un mapa
perdiera dos colores más, la única forma de enterarse era mirar la ROM.

Esto es a las decisiones lo que las goldens son a los pixeles, y por eso falla
diciendo **qué decisión cambió** y no "el archivo difiere": ver `diferencias`
en `port/parches.py`. Cuando el cambio es el buscado, se corre `just parches`
y el diff va al commit, que es donde alguien lo mira.

No arranca ninguna ROM: compara lo que dejaron escrito los cartuchos que armó
`just cartuchos` contra lo commiteado. Y los compara **todos**, que es lo que
sostiene que el cartucho no entre en la clave —medido el 2026-09-21: los tres
cartuchos deciden lo mismo para los mapas que comparten—.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from port import parches                                      # noqa: E402

import cartuchos                                              # noqa: E402


def _armados():
    """Los cartuchos que dejó `just cartuchos`, con sus parches adentro."""
    return [os.path.join(cartuchos.DESTINO, nombre)
            for nombre in sorted(os.listdir(cartuchos.DESTINO))
            if os.path.isdir(os.path.join(cartuchos.DESTINO, nombre,
                                          parches.EN_BUILD))]


def test_los_parches_versionados_son_los_que_decide_el_conversor():
    armados = _armados()
    assert armados, (
        "ningún cartucho de %s dejó parches: se arman con `just cartuchos`"
        % cartuchos.DESTINO)
    quejas = parches.revisar(RAIZ, armados)
    assert not quejas, "\n\n".join(quejas)
