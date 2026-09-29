"""Los parches versionados dicen lo mismo que el conversor acaba de decidir.

Un parche es una **decisión artística**: qué color se fusionó con cuál porque
la CGRAM no daba para los dos, o a qué tamaño se achicó una animación de
batalla para entrar en la caja de la consola. Se toman solas, cambian lo que se
ve, y hasta que existió `parches/` no dejaban rastro: si un cambio hacía que un
mapa perdiera dos colores más, la única forma de enterarse era mirar la ROM.

Esto es a las decisiones lo que las goldens son a los pixeles, y por eso falla
diciendo **qué decisión cambió** y no "el archivo difiere": ver `diferencias`
en `port/patches.py`. Cuando el cambio es el buscado, se corre `just parches`
y el diff va al commit, que es donde alguien lo mira.

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
"""

import os

from common import project                                    # noqa: E402
from port import animation                                    # noqa: E402
from port import patches                                      # noqa: E402

import cartuchos


def _armados():
    """Los cartuchos que dejó `just cartuchos`, con sus parches adentro.

    `release` también, y es el que más importa: es el único del que
    `patches.check` exige que todo lo que convierte esté versionado. Salen
    de la lista de cartuchos y no de listar los de prueba: ahí puede quedar el directorio
    de un cartucho que ya no existe —`main`, hasta el 2026-09-25— con
    decisiones de otro día.
    """
    candidatos = [cartuchos.directorio(n) for n in sorted(cartuchos.nombres())]
    return [c for c in candidatos
            if os.path.isdir(os.path.join(c, patches.MAPS_IN_BUILD))]


def test_los_parches_versionados_son_los_que_decide_el_conversor():
    armados = _armados()
    assert cartuchos.directorio(cartuchos.RELEASE) in armados, (
        "`release` no dejó parches en %s: se arma con `just cartuchos`, y sin "
        "él nada mira que lo que el juego convierte esté versionado"
        % cartuchos.directorio(cartuchos.RELEASE))
    quejas, _propios = patches.check(project.auto_patches(), armados)
    assert not quejas, "\n\n".join(quejas)


def test_el_tamano_de_cada_animacion_versionada_sale_de_su_caja_y_de_nada_mas():
    """Lo versionado de una animación se lee como lo va a leer la fase 2.

    Y de paso sostiene lo que hace que el número de animación alcance como
    clave: el tamaño es función de la caja que la animación ocupa en RM2k y de
    la caja de la consola, que es una sola para toda la ROM. Si algún día
    dependiera del mapa —de la VRAM que le quede—, dos cartuchos con los
    mismos mapas podrían decidir distinto y esta cuenta dejaría de dar.
    """
    clase = dict((c.key, c) for c in patches.KINDS)["animacion"]
    numeros = patches.versioned(project.auto_patches(), clase)
    assert numeros, "no hay ninguna animación versionada en %s" % clase.directory
    for numero in numeros:
        doc = patches.read_animation(project.auto_patches(), numero)
        assert doc["animacion"] == numero
        assert tuple(doc["tamano"]) == animation.fit_size(*doc["original"]), (
            "la animación %d dice que se dibuja a %s y su caja de %s da %s"
            % (numero, doc["tamano"], doc["original"],
               animation.fit_size(*doc["original"])))
        assert max(doc["tamano"]) <= animation.BOX


def test_armar_otra_vez_no_deja_los_parches_de_la_corrida_anterior(tmp_path):
    """Un cartucho que deja de llevar un mapa, una animación o un battler no
    puede seguir teniendo su parche al lado de la ROM: `revisar` mira lo que
    hay en el directorio, y un `.toml` viejo cuenta como convertido. Pasó al
    sacar los mapas de prueba de `release`: el `0052.toml` de la corrida
    anterior hacía caer la prueba de arriba."""
    viejos = []
    for clase in patches.KINDS:
        carpeta = tmp_path / clase.in_build
        carpeta.mkdir(parents=True)
        viejos.append(carpeta / "9999.toml")
        viejos[-1].write_text("de la corrida anterior\n")
    patches.write_maps(str(tmp_path), [])
    patches.write_animations(str(tmp_path), [])
    patches.write_battlers(str(tmp_path), [])
    quedan = [str(v) for v in viejos if v.exists()]
    assert not quedan, "quedaron parches de una corrida anterior: %s" % quedan


def test_lo_que_sale_solo_por_la_tanda_no_pide_parche(tmp_path):
    """La ROM que se juega lleva también los mapas y las páginas de la tanda,
    y eso no se versiona: un mapa de prueba, y una animación o un battler que
    sólo piden los mapas de prueba o los casos. Lo que pide también un mapa
    del juego, o lo que no dice quién lo pidió, sí."""
    clases = dict((c.key, c) for c in patches.KINDS)
    prueba = patches.test_maps()
    uno = min(prueba)
    del_juego = min(cartuchos.mapas_del_juego())
    assert not prueba & set(cartuchos.mapas_del_juego())
    (tmp_path / "parches").mkdir()
    patches.write_uses(str(tmp_path), {
        "animacion": {91: {"caso"}, 92: {uno, "caso"}, 93: {uno, del_juego}},
        "battler": {"solo-prueba": {uno}, "de-los-dos": {"caso", del_juego}}})

    def de_prueba(clase, cual):
        return patches.only_for_tests(str(tmp_path), clases[clase], cual, prueba)
    assert de_prueba("mapa", uno)
    assert not de_prueba("mapa", del_juego)
    assert de_prueba("animacion", 91) and de_prueba("animacion", 92)
    assert not de_prueba("animacion", 93)
    assert not de_prueba("animacion", 94), "sin origen conocido es del juego"
    assert de_prueba("battler", "solo-prueba")
    assert not de_prueba("battler", "de-los-dos")
    assert not patches.only_for_tests(str(tmp_path / "sin-usos"),
                                      clases["animacion"], 91, prueba)
