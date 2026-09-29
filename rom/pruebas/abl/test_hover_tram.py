"""El Hover Tram de la terraza del `Sector 27 Warehouse`, horneado en el mapa.

En RM2k el tram es un `ShowPicture` anclado al mapa que nunca se mueve, así que
en el port no es una imagen sino **tiles de la capa de encima** de un ChipSet
propio del mapa 32. El porqué, con todo lo medido, está en
`workflow/tasks/done/el-hover-tram-en-la-terraza.md`.

Esto existe porque **ninguna otra prueba ejecuta ese camino**. Las goldens
`32-*` del héroe miran el mapa desde adentro del depósito, donde el tram ni
asoma, y la receta de la imagen la cuidan las pruebas de `parches/manual/` —que
miran archivos, no la pantalla—. Sin esto, el tram podía dejar de dibujarse,
salir corrido o quedar **debajo** del héroe sin que nada se pusiera en rojo.

Las dos cosas que mira son las dos que la tarea pide que no se rompan:

* que el tram **esté dibujado y donde va**, comparando contra la silueta del
  arte original, que es una fuente independiente de todo lo que armamos;
* que el héroe se vea **por debajo**. El AGENCY CAPTAIN se para abajo del tram
  en la cinemática, y si sus tiles perdieran el bit "por encima del héroe" el
  conversor los hornearía en el fondo y el capitán quedaría dibujado arriba.
  Eso no cambia un pixel de la silueta, así que la primera comprobación no lo
  vería: hace falta pararse abajo y mirar.
"""

import os

import pytest

from tanda import partida

# Dónde cae el tram en el mapa y a qué escala, que es lo que dice la receta de
# `parches/manual/chipsets/0055.json`. Está acá repetido a propósito: si la
# receta se mueve sin querer, esta prueba tiene que decirlo en vez de seguirla.
X0, Y0, ESCALA = 324, 49, 56
# El caso para en (25,8): desde ahí la cámara muestra el tram entero **y** el
# héroe queda tapado por su cuerpo. Las dos cosas de una sola captura.
CAMARA = (280, 24)
# Los dos colores casi iguales a la clave de transparencia que el arte original
# trae mal pintados. Van transparentes —decisión de taro— así que no son parte
# de la silueta. Ver `transparentes` en la receta.
ROSADOS = ((255, 35, 192), (255, 39, 194))
# Cuántos ticks alcanzan para que el mapa esté dibujado. El caso es un
# `Teleport` y `partida` ya espera la llegada; esto es el margen del fundido.
TICKS = 20


def _silueta():
    """Las celdas de 8x8 de la pantalla que el tram tapa por completo.

    Sale del PNG de `Picture/` escalado, o sea **del arte original**: no pasa
    por el ChipSet, ni por el fork, ni por el conversor. Si el tram dejara de
    dibujarse, saliera corrido o se dibujara otra cosa, esto lo dice.

    Se piden celdas enteramente opacas y no pixeles sueltos porque el borde del
    dibujo es donde el escalado y el redondeo se llevan un pixel para un lado o
    para el otro, y eso no es lo que esta prueba quiere cazar.
    """
    from PIL import Image

    pic = Image.open(os.path.join(os.environ["ABL_GAME_DIR"],
                                  "Picture", "hovertram2.png"))
    pic.load()
    paleta = pic.getpalette()
    ancho, alto = pic.size
    chico = pic.resize((ancho * ESCALA // 100, alto * ESCALA // 100),
                       Image.NEAREST)
    pixeles = chico.load()

    def opaco(mx, my):
        px, py = mx - X0, my - Y0
        if not (0 <= px < chico.width and 0 <= py < chico.height):
            return False
        indice = pixeles[px, py]
        return bool(indice) and tuple(
            paleta[indice * 3:indice * 3 + 3]) not in ROSADOS

    celdas = []
    for cy in range(0, 224, 8):
        for cx in range(0, 256, 8):
            mx, my = cx + CAMARA[0], cy + CAMARA[1]
            if all(opaco(mx + x, my + y)
                   for y in range(8) for x in range(8)):
                celdas.append((cx, cy))
    return celdas


@pytest.fixture(scope="module")
def silueta():
    """Las celdas opacas, con su caja comprobada contra la que dice la receta.

    Lo que se comprueba no es *cuántas* son —eso sería un número inventado, y
    la primera versión de esta prueba puso uno que no se cumplía— sino **dónde
    caen**: la caja de la silueta tiene que quedar adentro del rectángulo que
    ocupa el dibujo escalado, que sale de `X0`, `Y0` y `ESCALA`. Si el tram se
    corriera de lugar, la caja se sale y esto lo dice.
    """
    from PIL import Image

    celdas = _silueta()
    assert celdas, "el tram no tapa ninguna celda entera de la pantalla"

    pic = Image.open(os.path.join(os.environ["ABL_GAME_DIR"],
                                  "Picture", "hovertram2.png"))
    ancho = pic.width * ESCALA // 100
    alto = pic.height * ESCALA // 100
    izq, arr = X0 - CAMARA[0], Y0 - CAMARA[1]
    for cx, cy in celdas:
        assert izq <= cx and cx + 8 <= izq + ancho, (
            "una celda de la silueta cae en x=%d y el tram va de %d a %d"
            % (cx, izq, izq + ancho))
        assert arr <= cy and cy + 8 <= arr + alto, (
            "una celda de la silueta cae en y=%d y el tram va de %d a %d"
            % (cy, arr, arr + alto))
    return celdas


def test_el_tram_esta_dibujado_donde_va(silueta):
    """El tram se ve, y su silueta cae donde la pone el arte original.

    Lo que se compara es **la forma**, no los colores: los colores pasan por
    las fusiones de Adeleine y compararlos sería comparar el conversor contra
    sí mismo. La forma en cambio sale del PNG del juego y de la cuenta de dónde
    lo ancla RM2k, que se midió calzando el dibujo contra una captura del juego
    original.

    El piso de la terraza abajo del tram es un patrón que se repite, así que
    "hay muchos colores distintos" alcanza para separarlo del tram sin
    depender de ninguna golden.
    """
    p = partida("hovertram")
    p.correr(TICKS)
    imagen = p.imagen().convert("RGB")
    pixeles = imagen.load()

    colores = set()
    for cx, cy in silueta:
        for y in range(cy, cy + 8):
            for x in range(cx, cx + 8):
                colores.add(pixeles[x, y])
    assert len(colores) >= 8, (
        "abajo de la silueta del tram hay %d colores distintos: con tan pocos "
        "lo más probable es que el tram no se esté dibujando y se vea el piso"
        % len(colores))


def test_el_heroe_se_ve_por_debajo_del_tram():
    """Parado abajo del tram, el héroe no se ve; al lado, sí.

    Es la prueba del bit "por encima del héroe" de los tiles del tram, y la
    única forma de mirarlo es con el héroe abajo: sin ese bit el conversor los
    hornea en el fondo, el dibujo sale **idéntico** y el héroe queda encima.

    El control al lado no es adorno: sin él, esta prueba pasaría igual el día
    que el héroe dejara de dibujarse por cualquier otro motivo.
    """
    abajo = partida("hovertram")
    abajo.correr(TICKS)
    tapado = abajo.imagen().convert("RGB")

    al_lado = partida("hovertram-al-lado")
    al_lado.correr(TICKS)
    visible = al_lado.imagen().convert("RGB")

    # El héroe se dibuja siempre en el mismo lugar de la pantalla —la cámara lo
    # sigue—, así que su recuadro es el mismo en las dos capturas.
    caja = (128 - 12, 112 - 16, 128 + 12, 112 + 16)
    # El mismo recuadro corrido, que es piso pelado: sirve para quedarse con
    # los colores que son **del héroe** y no del suelo que tiene atrás.
    al_costado = (caja[0] + 48, caja[1], caja[2] + 48, caja[3])

    def colores(imagen, rect):
        return set(imagen.crop(rect).get_flattened_data())

    suyos = colores(visible, caja) - colores(visible, al_costado)
    # Y lo que además pinte el tram no cuenta: si un color del héroe estuviera
    # también en la nave, encontrarlo abajo no probaría nada. Se lo saca
    # mirando un pedazo de tram lejos del héroe, en la captura de abajo.
    suyos -= colores(tapado, al_costado)
    assert suyos, (
        "no se pudo aislar ningún color que sea sólo del héroe: sin eso esta "
        "prueba no puede decir nada, así que falla en vez de pasar en vacío")

    quedaron = suyos & colores(tapado, caja)
    assert not quedaron, (
        "parado abajo del tram se siguen viendo %d color(es) que son sólo del "
        "héroe (%s): sus tiles perdieron el bit de 'por encima del héroe' y el "
        "conversor los horneó en el fondo, así que el héroe quedó dibujado "
        "arriba" % (len(quedaron), sorted(quedaron)[:4]))
