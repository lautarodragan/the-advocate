"""The VRAM layouts of `vram_layout`: that they respect the hardware and that
a new one does not change any map's layout.

They run no ROM. What the ROM does with the layout is enforced by the suite,
and the layout that moves the background tilemap —`LAYOUT_VENTANA_AMBOS`— is
used by no cartridge today: see `workflow/tasks/done/el-tilemap-del-fondo-lo-elige-el-reparto.md`.
"""

from port import snes_convert as S


def test_los_repartos_respetan_al_hardware():
    """Alignments, that nothing overlaps, and what the ROM assumes about the
    tilemap: otherwise `_controlar_repartos` stops the conversion with a
    SystemExit."""
    S._controlar_repartos()


def test_cada_mapa_se_queda_con_el_primer_reparto_que_le_entra():
    """`vram_layout` returns the first one that fits. That is what allows adding
    a layout at the end without moving any map: if someone inserts it in the
    middle, this does not see it, but the `LAYOUTS` order below does."""
    for fondo in range(0, 545, 16):
        for sprites in range(0, 513, 16):
            entran = [layout for _n, layout in S.LAYOUTS
                      if fondo <= layout["tiles"][1]
                      and sprites <= layout["sprites"][1]]
            if entran:
                assert S.vram_layout(fondo, sprites) is entran[0]


def test_los_repartos_van_en_el_orden_en_que_se_agregaron():
    """A new layout goes at the end. Changing this order changes the layout of
    maps that already converted, and that moves goldens."""
    assert [n for n, _l in S.LAYOUTS] == [
        "VENTANA", "VENTANA_FONDO", "VENTANA_SPRITE", "VENTANA_AMBOS",
        "VENTANA_FONDO_TECHO", "VENTANA_ENCIMA"]


def test_el_mapa_38_entra_en_el_reparto_que_baja_el_tilemap():
    """`Sector 34 With Car` uses 476 background tiles and 347 sprite tiles,
    measured on 2026-09-25, and did not fit in any of the other three."""
    assert S.vram_layout(476, 347) is S.LAYOUT_VENTANA_AMBOS
    assert S.LAYOUT_VENTANA_AMBOS["mapa"][0] != S.LAYOUT_VENTANA["mapa"][0]


def test_el_mundo_entra_en_el_techo_de_fondo():
    """Map 66 uses 527 background tiles and 222 sprite tiles, measured on
    2026-09-27, and with 222 sprites the other four give at most 480 for the
    background. With 256 sprites the hardware gives 544: see docs/port/vram.md."""
    assert S.vram_layout(527, 222) is S.LAYOUT_VENTANA_FONDO_TECHO
    assert S.vram_layout(544, 256) is S.LAYOUT_VENTANA_FONDO_TECHO


def test_sorbe_entra_en_el_reparto_de_la_capa_de_encima_de_256():
    """Map 69 uses 329 background tiles, 157 upper-layer tiles and 283 sprite
    tiles, measured on 2026-09-27: the other five give 128 to the upper layer.
    Without the upper layer in the count, the same map stays in the first one,
    which is what happens to every map that fits in 128."""
    assert S.vram_layout(329, 283, 157) is S.LAYOUT_VENTANA_ENCIMA
    assert S.vram_layout(329, 283) is S.LAYOUT_VENTANA


def test_cada_base_de_la_ventana_tiene_su_plano():
    """`estampar_ventana` chooses between two cell plans, and the layouts cannot
    put the window at a third distance from BG2's base."""
    assert {S.ventana_base(layout) for _n, layout in S.LAYOUTS} == set(
        S.VENTANA_BASES)
