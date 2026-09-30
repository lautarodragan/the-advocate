"""Los parches versionados dicen lo mismo que el conversor acaba de decidir.

Un parche es una **decisión artística**: qué color se fusionó con cuál porque
la CGRAM no daba para los dos, o a qué tamaño se achicó una animación de
batalla para entrar en la caja de la consola. Se toman solas, cambian lo que se
ve, y hasta que existió `parches/` no dejaban rastro: si un cambio hacía que un
mapa perdiera dos colores más, la única forma de enterarse era mirar la ROM.

Esto es a las decisiones lo que las goldens son a los pixeles, y por eso falla
diciendo **qué decisión cambió** y no "el archivo difiere": lo dice
`rm2k-snes-patches --check`, que es lo que corre esto. Cuando el cambio es el
buscado, se corre `just parches` y el diff va al commit, que es donde alguien
lo mira.

No arranca ninguna ROM: compara lo que dejaron escrito los cartuchos que armó
`just cartuchos` contra lo commiteado. Y los compara **todos**, que es lo que
sostiene que el cartucho no entre en la clave —medido el 2026-09-21, con las
capas y con las animaciones: todos los cartuchos emitían los mismos archivos
byte por byte—.

Lo versionado es lo que decide `release`, el ROM jugable. Lo que lleva sólo por
la tanda —los mapas de prueba, y las animaciones y los battlers que sólo piden
ellos o los casos— no se versiona: ahí el cartucho decide solo y esto no le
pide nada; cuáles son los imprime `just parches-check`. Todo lo demás que
convierte `release` tiene que estar versionado.

Lo que no depende del juego —que armar otra vez no deje los parches de la
corrida anterior, qué es "sólo de la tanda"— lo prueban las pruebas de
`rm2k-snes-patches`, que no necesitan el juego.
"""

import os
import subprocess
import tomllib

from common import project                                    # noqa: E402
from port import animation                                    # noqa: E402

import cartuchos
import lugares

# Dónde deja cada cartucho las decisiones de sus mapas, relativo a su
# directorio: la forma del build, que escribe `rm2k-snes-patches`.
MAPAS_EN_EL_BUILD = os.path.join("parches", "auto", "mapas")


def _armados():
    """Los cartuchos que dejó `just cartuchos`, con sus parches adentro.

    `release` también, y es el que más importa: es el único del que el check
    exige que todo lo que convierte esté versionado. Salen de la lista de
    cartuchos y no de listar los de prueba: ahí puede quedar el directorio
    de un cartucho que ya no existe —`main`, hasta el 2026-09-25— con
    decisiones de otro día.
    """
    candidatos = [cartuchos.directorio(n) for n in sorted(cartuchos.nombres())]
    return [c for c in candidatos
            if os.path.isdir(os.path.join(c, MAPAS_EN_EL_BUILD))]


def test_los_parches_versionados_son_los_que_decide_el_conversor():
    armados = _armados()
    assert cartuchos.directorio(cartuchos.RELEASE) in armados, (
        "`release` no dejó parches en %s: se arma con `just cartuchos`, y sin "
        "él nada mira que lo que el juego convierte esté versionado"
        % cartuchos.directorio(cartuchos.RELEASE))
    hecho = subprocess.run(["rm2k-snes-patches", "--project", lugares.ABL,
                            "--check", *armados],
                           capture_output=True, text=True)
    assert hecho.returncode == 0, hecho.stderr


def test_el_tamano_de_cada_animacion_versionada_sale_de_su_caja_y_de_nada_mas():
    """Lo versionado de una animación se lee como lo va a leer la fase 2.

    Y de paso sostiene lo que hace que el número de animación alcance como
    clave: el tamaño es función de la caja que la animación ocupa en RM2k y de
    la caja de la consola, que es una sola para toda la ROM. Si algún día
    dependiera del mapa —de la VRAM que le quede—, dos cartuchos con los
    mismos mapas podrían decidir distinto y esta cuenta dejaría de dar.
    """
    carpeta = os.path.join(project.auto_patches(), "animaciones")
    archivos = sorted(n for n in os.listdir(carpeta) if n.endswith(".toml"))
    assert archivos, "no hay ninguna animación versionada en %s" % carpeta
    for archivo in archivos:
        with open(os.path.join(carpeta, archivo), "rb") as f:
            doc = tomllib.load(f)
        numero = doc["animacion"]
        assert tuple(doc["tamano"]) == animation.fit_size(*doc["original"]), (
            "la animación %d dice que se dibuja a %s y su caja de %s da %s"
            % (numero, doc["tamano"], doc["original"],
               animation.fit_size(*doc["original"])))
        assert max(doc["tamano"]) <= animation.BOX
