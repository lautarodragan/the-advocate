"""Las hojas de glifos: leerlas y escribirlas.

Una hoja es un PNG indexado con los 95 caracteres ASCII imprimibles, del
espacio a la `~`, en el orden de ASCII: 16 por fila, seis filas. Cada uno
en su celda, y entre celdas una línea de grilla de un pixel. La celda mide
`ancho` columnas por 13 filas:

* las filas 0 a 11 son el glifo, con la misma línea de base que la fuente
  de RM2k (la de las mayúsculas termina en la fila 9);
* la fila 12 es **el avance**: tantos pixeles de la marca, pegados desde la
  izquierda, como columnas avanza la línea después de dibujar el glifo. El
  aire entre letras va adentro del avance, no en el glifo.

Los colores van por índice, no por valor —se pueden cambiar los colores de
la paleta para verlos mejor y la hoja sigue diciendo lo mismo—: 0 el fondo,
1 el glifo, 2 la marca del avance y 3 la grilla. **La sombra no va en la
hoja**: la dibuja el que dibuja la línea, corrida como en RM2k, igual que
la ROM.
"""
from PIL import Image

FONDO, GLIFO, AVANCE, GRILLA = 0, 1, 2, 3
PALETA = [(0, 0, 0), (255, 255, 255), (224, 32, 32), (72, 72, 96)]

CARACTERES = [chr(c) for c in range(32, 127)]
POR_FILA = 16
FILAS_GLIFO = 12
ALTO = FILAS_GLIFO + 1


def _celda(i, ancho):
    return 1 + (i % POR_FILA) * (ancho + 1), 1 + (i // POR_FILA) * (ALTO + 1)


def medidas(ancho):
    filas = (len(CARACTERES) + POR_FILA - 1) // POR_FILA
    return POR_FILA * (ancho + 1) + 1, filas * (ALTO + 1) + 1


def escribir(ruta, glifos, ancho):
    """`glifos`: {caracter: (filas de 0 y 1, avance)}."""
    w, h = medidas(ancho)
    imagen = Image.new("P", (w, h), FONDO)
    paleta = []
    for color in PALETA:
        paleta += color
    imagen.putpalette(paleta + [0] * (768 - len(paleta)))
    pix = imagen.load()
    for x in range(w):
        for y in range(h):
            if x % (ancho + 1) == 0 or y % (ALTO + 1) == 0:
                pix[x, y] = GRILLA
    for i, c in enumerate(CARACTERES):
        x0, y0 = _celda(i, ancho)
        filas, avance = glifos[c]
        for y, fila in enumerate(filas):
            for x, v in enumerate(fila):
                if v:
                    pix[x0 + x, y0 + y] = GLIFO
        for x in range(avance):
            pix[x0 + x, y0 + FILAS_GLIFO] = AVANCE
    imagen.save(ruta)


class Fuente:
    """Una hoja leída: `glifo(c)` son los pixeles (x, y) de tinta y
    `avance(c)` cuánto corre la línea. Un carácter fuera de la hoja se
    dibuja como `?`, que es lo que hace la ROM."""

    def __init__(self, ruta):
        imagen = Image.open(ruta)
        if imagen.mode != "P":
            raise SystemExit("%s: no es indexada" % ruta)
        w, h = imagen.size
        self.ancho = (w - 1) // POR_FILA - 1
        if medidas(self.ancho) != (w, h):
            raise SystemExit("%s: mide %dx%d, y una hoja de celdas de %d mide "
                             "%dx%d" % ((ruta, w, h, self.ancho) + medidas(self.ancho)))
        pix = imagen.load()
        self.glifos, self.avances = {}, {}
        for i, c in enumerate(CARACTERES):
            x0, y0 = _celda(i, self.ancho)
            tinta = []
            for y in range(FILAS_GLIFO):
                for x in range(self.ancho):
                    v = pix[x0 + x, y0 + y]
                    if v == GLIFO:
                        tinta.append((x, y))
                    elif v not in (FONDO, GRILLA):
                        raise SystemExit("%s: '%s' tiene el color %d en (%d, %d): "
                                         "en el glifo van sólo el %d y el %d"
                                         % (ruta, c, v, x, y, FONDO, GLIFO))
            marca = [pix[x0 + x, y0 + FILAS_GLIFO] == AVANCE
                     for x in range(self.ancho)]
            avance = sum(marca)
            if marca[:avance] != [True] * avance:
                raise SystemExit("%s: la marca del avance de '%s' no está "
                                 "pegada a la izquierda" % (ruta, c))
            self.glifos[c] = tinta
            self.avances[c] = avance

    def _c(self, c):
        return c if c in self.glifos else "?"

    def glifo(self, c):
        return self.glifos[self._c(c)]

    def avance(self, c):
        return self.avances[self._c(c)]

    def largo(self, texto):
        """Cuánto avanza `texto`: desde donde empieza hasta donde empezaría
        el siguiente."""
        return sum(self.avance(c) for c in texto)
