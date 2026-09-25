"""Los eventos que se hornean en el mapa: que tapen de verdad y que la celda
siga pasándose igual.

Un evento dibujado con un tile opaco del ChipSet deja de dibujarse y su tile se
mete en la capa alta del mapa —ver `eventos_horneables` en snes_convert.py—. Lo
que sostiene que eso no cambie nada son dos invariantes, y las dos se miran acá
porque ninguna se ve en una captura:

* **la pasabilidad de la celda no cambia.** La fila del evento imponía los bits
  de su tile (`rm2k.pasabilidad_del_tile`) y `pasa_con_evento` saltea las filas
  escondidas, así que si la tabla del mapa no llegara al mismo valor, la celda
  pasaría a pasarse distinto y no habría un pixel que lo delatara;
* **el tile tapa las 16x16.** Un pixel transparente deja ver el tile de abajo,
  y en una golden del mapa 11 eso serían unos pocos pixeles en una celda:
  exactamente lo que una comparación con tope no cobra.

No arranca ninguna ROM: mira al conversor.
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))

from port import snes_convert                                # noqa: E402
from render.render_map import GAME_DIR, Renderer, build_passability  # noqa: E402
from rpgmaker import rm2k                                    # noqa: E402

from ensamblado import cartuchos                             # noqa: E402

# Los mapas que se miran: los del cartucho de pruebas, que son los que las
# goldens dibujan. Salen de `cartuchos` y no copiados acá, que es lo que evita
# que la lista envejezca cuando se le suma un mapa al proyecto. El 11 —el HQ de
# los Lazer Teeth— fue el que horneaba la mayoría y el que motivó todo esto,
# hasta que sus baldosas dejaron de ser eventos.
MAPAS = cartuchos.MAPAS


def horneados_de(renderer, map_id):
    game_map = renderer.cargar_mapa(
        os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
    return game_map, snes_convert.eventos_horneables(renderer, game_map)


def test_la_regla_sigue_alcanzando_a_algun_mapa_del_cartucho():
    """La regla no se puede apagar sola.

    Sin número escrito: un filtro de más y no se hornea nada, y nadie se
    entera. Cuántos son lo dice el conversor en su informe.

    **El sujeto ya no es el mapa 11**, que es para el que se escribió. El
    2026-09-21 su minijuego se rediseñó y sus 52 baldosas de luz dejaron de ser
    eventos —ver `parches/manual/README.md`—, así que las 22 que horneaba no
    existen: lo que le quedaba a la regla en este cartucho es otro mapa. La
    regla sigue entera y sigue valiendo para el resto del juego; lo que se fue
    es su cliente más grande.
    """
    renderer = Renderer()
    horneados = {m: horneados_de(renderer, m)[1] for m in MAPAS}
    assert any(horneados.values()), \
        "ningún mapa del cartucho hornea un evento: la regla dejó de alcanzar"


def test_lo_que_se_hornea_tapa_la_celda_entera():
    """Opaco en las 16x16, con el tile 0 —el de una celda vacía— transparente."""
    renderer = Renderer()
    for map_id in MAPAS:
        game_map, horneados = horneados_de(renderer, map_id)
        if not horneados:
            continue
        atlas = renderer.atlas_por_nombre(game_map.chipset_nombre)
        assert not any(snes_convert._alfas_del_tile(atlas, 0)), \
            "mapa %d: el tile 0 de la capa alta dibuja algo, así que la celda " \
            "vacía donde se hornea no estaba vacía" % map_id
        for evento, (_celda, tile) in horneados.items():
            alfas = snes_convert._alfas_del_tile(atlas, tile - rm2k.UPPER_BASE)
            assert all(a == 255 for a in alfas), \
                "mapa %d: el evento %d se hornea con un tile que tiene " \
                "pixeles transparentes" % (map_id, evento + 1)


def test_hornear_no_cambia_la_pasabilidad_de_la_celda():
    """La tabla del mapa tiene que dar lo mismo que imponía la fila del evento.

    Es la invariante que permite esconder la fila: `pasa_con_evento` no mira las
    escondidas, así que el valor tiene que estar en la tabla.
    """
    renderer = Renderer()
    for map_id in MAPAS:
        game_map, horneados = horneados_de(renderer, map_id)
        if not horneados:
            continue
        chipset = renderer.database.chipsets[game_map.chipset_id]
        flags = build_passability(chipset)
        # Lo que la fila imponía, antes de hornear.
        antes = {}
        for npc in snes_convert.collect_npcs(game_map):
            if npc["evento"] in horneados:
                antes[npc["evento"]] = rm2k.pasabilidad_del_tile(
                    game_map, npc["charset"], npc["layer"])
        snes_convert.hornear_en_el_mapa(game_map, horneados)
        pasable = rm2k.passability_map(game_map, flags)
        for evento, (celda, _tile) in horneados.items():
            assert antes[evento] is not None, \
                "mapa %d: el evento %d se hornea y no imponía pasabilidad, " \
                "así que hornearlo le cambia la celda" % (map_id, evento + 1)
            assert pasable[celda] == antes[evento], \
                "mapa %d: el evento %d imponía %#x a su celda y horneado la " \
                "tabla dice %#x" % (map_id, evento + 1, antes[evento],
                                    pasable[celda])
