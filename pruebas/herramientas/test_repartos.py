"""Los repartos de VRAM de `vram_layout`: que respeten al hardware y que uno
nuevo no le cambie el suyo a ningún mapa.

No corren ninguna ROM. Lo que la ROM hace con el reparto lo cobra la tanda, y
el reparto que mueve el tilemap del fondo —`LAYOUT_VENTANA_AMBOS`— no lo usa
hoy ningún cartucho: ver `workflow/tasks/done/el-tilemap-del-fondo-lo-elige-el-reparto.md`.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from port import snes_convert as S                      # noqa: E402


def test_los_repartos_respetan_al_hardware():
    """Alineaciones, que nada se pise y lo que la ROM supone del tilemap: si
    no, `_controlar_repartos` corta la conversión con un SystemExit."""
    S._controlar_repartos()


def test_cada_mapa_se_queda_con_el_primer_reparto_que_le_entra():
    """`vram_layout` devuelve el primero que entra. Es lo que deja agregar un
    reparto al final sin mover ningún mapa: si alguien lo inserta en el medio,
    esto no lo ve, pero sí lo ve el orden de `LAYOUTS` de abajo."""
    for fondo in range(0, 545, 16):
        for sprites in range(0, 513, 16):
            entran = [layout for _n, layout in S.LAYOUTS
                      if fondo <= layout["tiles"][1]
                      and sprites <= layout["sprites"][1]]
            if entran:
                assert S.vram_layout(fondo, sprites) is entran[0]


def test_los_repartos_van_en_el_orden_en_que_se_agregaron():
    """Un reparto nuevo va al final. Cambiar este orden le cambia el reparto a
    mapas que ya convertían, y eso mueve goldens."""
    assert [n for n, _l in S.LAYOUTS] == [
        "VENTANA", "VENTANA_FONDO", "VENTANA_SPRITE", "VENTANA_AMBOS"]


def test_el_mapa_38_entra_en_el_reparto_que_baja_el_tilemap():
    """`Sector 34 With Car` gasta 476 tiles de fondo y 347 de sprite, medido
    el 2026-09-25, y no entraba en ninguno de los otros tres."""
    assert S.vram_layout(476, 347) is S.LAYOUT_VENTANA_AMBOS
    assert S.LAYOUT_VENTANA_AMBOS["mapa"][0] != S.LAYOUT_VENTANA["mapa"][0]
