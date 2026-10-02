"""Los eventos que se hornean en el mapa: que tapen de verdad y que la celda
siga pasándose igual.

Un evento dibujado con un tile opaco del ChipSet deja de dibujarse y su tile se
mete en la capa alta del mapa —ver `baking.rs` en `wally`—. Lo
que sostiene que eso no cambie nada son dos invariantes, y las dos se miran acá
porque ninguna se ve en una captura:

* **la pasabilidad de la celda no cambia.** La fila del evento imponía los bits
  de su tile y `pass_with_event` saltea las filas escondidas, así que si la
  tabla del mapa no llegara al mismo valor, la celda pasaría a pasarse distinto
  y no habría un pixel que lo delatara;
* **el tile tapa las 16x16.** Un pixel transparente deja ver el tile de abajo,
  y en una golden del mapa 11 eso serían unos pocos pixeles en una celda:
  exactamente lo que una comparación con tope no cobra.

No arranca ninguna ROM: le pregunta a la etapa del conversor, `wally
bakeable`, qué hornea en cada mapa, con lo que imponía cada fila y lo que
dice la tabla después.
"""

import cartuchos
from etapa_mapas import preguntar

# Los mapas que se miran: los del cartucho de pruebas, que son los que las
# goldens dibujan. Salen de `cartuchos` y no copiados acá, que es lo que evita
# que la lista envejezca cuando se le suma un mapa al proyecto.
MAPAS = cartuchos.mapas()


def horneados():
    return {m: preguntar("bakeable", m) for m in MAPAS}


def test_la_regla_sigue_alcanzando_a_algun_mapa_del_cartucho():
    """La regla no se puede apagar sola.

    Sin número escrito: un filtro de más y no se hornea nada, y nadie se
    entera. Cuántos son lo dice el conversor en su informe.
    """
    assert any(r["baked"] for r in horneados().values()), \
        "ningún mapa del cartucho hornea un evento: la regla dejó de alcanzar"


def test_lo_que_se_hornea_tapa_la_celda_entera():
    """Opaco en las 16x16, con el tile 0 —el de una celda vacía— transparente."""
    for map_id, respuesta in horneados().items():
        if not respuesta["baked"]:
            continue
        assert not any(respuesta["tile_zero"]), \
            "mapa %d: el tile 0 de la capa alta dibuja algo, así que la celda " \
            "vacía donde se hornea no estaba vacía" % map_id
        for h in respuesta["baked"]:
            assert all(a == 255 for a in h["alphas"]), \
                "mapa %d: el evento %d se hornea con un tile que tiene " \
                "pixeles transparentes" % (map_id, h["event"] + 1)


def test_hornear_no_cambia_la_pasabilidad_de_la_celda():
    """La tabla del mapa tiene que dar lo mismo que imponía la fila del evento.

    Es la invariante que permite esconder la fila: `pass_with_event` no mira las
    escondidas, así que el valor tiene que estar en la tabla.
    """
    for map_id, respuesta in horneados().items():
        for h in respuesta["baked"]:
            assert h["imposed"] is not None, \
                "mapa %d: el evento %d se hornea y no imponía pasabilidad, " \
                "así que hornearlo le cambia la celda" % (map_id, h["event"] + 1)
            assert h["after"] == h["imposed"], \
                "mapa %d: el evento %d imponía %#x a su celda y horneado la " \
                "tabla dice %#x" % (map_id, h["event"] + 1, h["imposed"],
                                    h["after"])
