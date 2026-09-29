r"""Text boxes reflowed for the SNES width.

RM2k has no auto-wrap: every break in a `ShowMessage` was put there by hand
by the author, thinking of a 320 px window. The one here is narrower
—`constantes.COLUMNAS` characters per line—, and until this, whatever did
not fit was truncated.

`reajustar` takes the lines of **one** box, exactly as they are in
`rom/data/`, and returns one or more boxes that fit. It is a pure function:
the same box always gives the same result, and that is what allows applying
it on every build instead of storing its output.

The rules, and where each one comes from:

* **A box that fits is returned as is**, with its breaks and its spaces.
  Most fit, and that way they keep everything the author decided.
* **The speaker's line is not touched** —`KERSH`, `MANTA`, `?????`— and the
  body has one line less.
* **An original break is a good place to cut, not a mandatory one.**
  Treating it as mandatory left a word alone on a line ("it still /
  is.") and made more boxes not fit.
* **A line that splits a sentence goes full**; one with whole sentences may
  be short. What taro does not want to see is a line that stops long before
  the edge —"Remember," alone, and the rest below—, and that happens when
  cutting at a period comes out cheaper than filling.
* **What does not fit in one box is split into several**, cutting between
  sentences when possible, and **each one repeats the speaker's line.** It
  is what the game does: measured on 2026-09-24, of the consecutive boxes
  of the same character none fails to repeat the name, and the author
  himself splits a sentence that way —`MANTA` / "...up to the Emitter Room
  -" and `MANTA` / "- where the Link is projected!"—.
* **The escape tail** —`\|` and `\^`, see `eventos.cola_de_escapes`— goes at
  the end of the last box, which is where the player saw it.

What is lost in a reflowed box are the extra spaces between words: the words
are joined again with one. In one that fits, nothing is lost.
"""

import re

from port import eventos
from port import constantes

# An end of sentence, with the quotes or parenthesis that close it: cutting
# there is free. `...` matches through the period.
FIN_DE_ORACION = re.compile(r"""[.!?]["')]*$""")
# A minor pause: cutting there costs little.
PAUSA = re.compile(r"""[,;:\-]["')]*$""")

# The costs. They are taste and not a measurement: with other values the same
# box comes out differently. The first ones were tried on the introduction and
# Lashe City on 2026-09-24; those of the gap, the tail and the extra box came
# out the same day from what taro played up to the Back Alleys, comparing
# against the previous version on every box of the game.
#
# Cutting a line after a word:
COSTO_FIN_DE_ORACION = 0
COSTO_PAUSA = 15
COSTO_CUALQUIERA = 40
DESCUENTO_SALTO_ORIGINAL = 10   # where the author cut
COSTO_HUERFANA = 200            # a lone word on the last line
# Between a proper name and its number —"Sector / 33."—. It is almost
# forbidden: it costs more than an extra box.
COSTO_ANTES_DE_NUMERO = 1000

# The gap a line that is not the last one leaves. How much it weighs depends
# on where it cuts, and that is the rule that most changes what is seen: **a
# line that splits a sentence has to go full.** One with whole sentences may
# be short —"Time is running out." / "There's no turning back."—, because it
# reads as a break the author intended. With a single weight for all, cutting
# at an end of sentence was so cheap against the gap that the reflow left
# "Remember," or "Well," alone on a line so that the ones below would end in
# a period: that is what taro complained about.
PESO_HUECO = 20                 # whole sentences: the gap squared / 20
PESO_HUECO_PAUSA = 8            # cuts at a comma: squared / 8
PESO_HUECO_PARTIDO = 1000       # splits a sentence: cubed, relative to the width

# The piece of sentence left on the other side of a cut —"sure." at the start
# of a line, "There" at the end—, if it is shorter than this. It is the
# generalized orphan: "in time?" alone below looks as cut off as "Well," above.
COLA_MINIMA = 16
PESO_COLA = 3                   # what it is short of, squared / 3

# An extra box is an extra key press for the player. If the nicest layout
# does not fit in one box but there is one that fits and costs at most this
# much more, the one that fits wins.
COSTO_CUADRO_DE_MAS = 300


def ancho(texto):
    """How many columns it takes: one character, one column. The font is
    fixed-width, and the only escapes that compile go in the tail, outside
    of this."""
    return len(texto)


# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
def es_hablante(linea):
    """Whether the line names the speaker: all caps, short, and with no
    sentence punctuation at the end.

    `?????` is the odd case that has to match —the game uses it while it is
    not known who is speaking—, so a question mark at the end only counts if
    there is nothing but question marks. "WHAT?" is a shouted sentence, not
    a name.
    """
    texto = linea.strip()
    if not texto or len(texto) > 20 or texto != texto.upper():
        return False
    if set(texto) == {"?"}:
        return True
    return not texto.endswith((".", "!", "?", ","))


def entra(lineas, columnas=constantes.COLUMNAS, renglones=constantes.LINEAS):
    """Whether the box is fully visible, not counting its escape tail."""
    sin_cola, _pausas, _autocierre = eventos.cola_de_escapes(lineas)
    return (len(sin_cola) <= renglones
            and all(ancho(t) <= columnas for t in sin_cola))


def _cola(lineas):
    """The box's escape tail, exactly as written, and the lines without
    it."""
    sin_cola, _pausas, _autocierre = eventos.cola_de_escapes(lineas)
    sin_cola = list(sin_cola)
    if not sin_cola:
        return sin_cola, ""
    return sin_cola, lineas[-1][len(sin_cola[-1]):]


def _palabras(renglones, columnas):
    """The words of the body, and after which of them the author cut.

    A word wider than a line is split by force: there is no other way to
    show it.
    """
    palabras = []
    cortes = set()
    for renglon in renglones:
        for palabra in renglon.split():
            while ancho(palabra) > columnas:
                palabras.append(palabra[:columnas])
                palabra = palabra[columnas:]
            palabras.append(palabra)
        if palabras:
            cortes.add(len(palabras) - 1)
    return palabras, cortes


def _costo_de_cortar(palabras, cortes, i):
    palabra = palabras[i]
    if FIN_DE_ORACION.search(palabra):
        costo = COSTO_FIN_DE_ORACION
    elif PAUSA.search(palabra):
        costo = COSTO_PAUSA
    else:
        costo = COSTO_CUALQUIERA
    if i in cortes:
        costo -= DESCUENTO_SALTO_ORIGINAL
    if (palabra[:1].isupper() and palabra[-1:].isalpha()
            and i + 1 < len(palabras) and palabras[i + 1][:1].isdigit()):
        costo += COSTO_ANTES_DE_NUMERO
    return costo


def _costo_del_renglon(palabras, cortes, i, j, columnas):
    """What a line with the words from `i` to `j` costs: its gap, the cut it
    ends with and the pieces of sentence it leaves loose.

    The last line does not pay for its gap —it ends where the text ends—,
    but it does pay for being left with a single word or with a short piece
    of the sentence above.
    """
    n = len(palabras)
    largo = ancho(" ".join(palabras[i:j]))
    fines = [k for k in range(i, j) if FIN_DE_ORACION.search(palabras[k])]
    empieza_oracion = i == 0 or FIN_DE_ORACION.search(palabras[i - 1])
    costo = 0
    # The end of a sentence that started on the line above.
    if not empieza_oracion and (j == n or (fines and fines[0] < j - 1)):
        hasta = fines[0] + 1 if fines else j
        costo += _costo_de_fragmento(palabras[i:hasta])
    if j == n:
        if j - i == 1 and i > 0:
            costo += COSTO_HUERFANA
        return costo
    # The start of a sentence that continues on the line below.
    if not FIN_DE_ORACION.search(palabras[j - 1]) and fines:
        costo += _costo_de_fragmento(palabras[fines[-1] + 1:j])
    hueco = columnas - largo
    if FIN_DE_ORACION.search(palabras[j - 1]) and empieza_oracion:
        costo += hueco * hueco / PESO_HUECO
    elif PAUSA.search(palabras[j - 1]):
        costo += hueco * hueco / PESO_HUECO_PAUSA
    else:
        costo += PESO_HUECO_PARTIDO * (hueco / columnas) ** 3
    return costo + _costo_de_cortar(palabras, cortes, j - 1)


def _costo_de_fragmento(palabras):
    """A piece of sentence separated from the rest by a line break."""
    falta = max(0, COLA_MINIMA - ancho(" ".join(palabras)))
    return falta * falta / PESO_COLA


def _renglones(palabras, cortes, columnas, maximo=None):
    """The words in lines, choosing the cuts that cost the least.

    It is TeX's paragraph algorithm in miniature: dynamic programming over
    where each line ends, keeping count of how many there are so far.
    """
    n = len(palabras)
    if n == 0:
        return []
    # mejor[j][k]: the cost of putting the first j words in k lines, and
    # where the last one starts.
    mejor = [dict() for _ in range(n + 1)]
    mejor[0][0] = (0, None)
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            renglon = " ".join(palabras[i:j])
            if ancho(renglon) > columnas:
                break
            if not mejor[i]:
                continue
            propio = _costo_del_renglon(palabras, cortes, i, j, columnas)
            for k, (antes, _desde) in mejor[i].items():
                costo = antes + propio
                # `<` and not `<=`: on a tie the longest line wins, which is
                # the one found first. It is what makes it deterministic.
                if k + 1 not in mejor[j] or costo < mejor[j][k + 1][0]:
                    mejor[j][k + 1] = (costo, i)
    opciones = sorted(mejor[n].items(), key=lambda kv: (kv[1][0], kv[0]))
    elegido = opciones[0][0]
    if maximo is not None and elegido > maximo:
        # The nicest layout does not fit in one box. If there is one that
        # fits and is not much worse, that one is used: an extra box is an
        # extra key press.
        entran = [kv for kv in opciones if kv[0] <= maximo]
        if entran and entran[0][1][0] < opciones[0][1][0] + COSTO_CUADRO_DE_MAS:
            elegido = entran[0][0]
    salida = []
    j, k = n, elegido
    while j > 0:
        i = mejor[j][k][1]
        salida.append(" ".join(palabras[i:j]))
        j, k = i, k - 1
    return salida[::-1]


def _tramos(palabras, cortes, columnas, cuerpo):
    """The words spread over as many boxes as needed.

    Each box is filled with whole sentences while they fit. A sentence that
    does not fit in a box on its own is split by lines.
    """
    oraciones = []
    desde = 0
    for i, palabra in enumerate(palabras):
        if FIN_DE_ORACION.search(palabra) or i == len(palabras) - 1:
            oraciones.append((desde, i + 1))
            desde = i + 1

    def renglones_de(a, b):
        locales = {c - a for c in cortes if a <= c < b}
        return _renglones(palabras[a:b], locales, columnas, cuerpo)

    tramos = []
    inicio = fin = 0
    for a, b in oraciones:
        if len(renglones_de(inicio, b)) <= cuerpo:
            fin = b
            continue
        if fin > inicio:
            tramos.append(renglones_de(inicio, fin))
            inicio = fin = a
        if len(renglones_de(a, b)) <= cuerpo:
            fin = b
            continue
        # The sentence alone does not fit in a box: it is spread by lines.
        todos = renglones_de(a, b)
        for k in range(0, len(todos) - cuerpo, cuerpo):
            tramos.append(todos[k:k + cuerpo])
        resto = todos[(len(todos) - 1) // cuerpo * cuerpo:]
        inicio = b - len(" ".join(resto).split())
        fin = b
    if fin > inicio:
        tramos.append(renglones_de(inicio, fin))
    return tramos


def reajustar(lineas, columnas=constantes.COLUMNAS,
              renglones=constantes.LINEAS):
    """The boxes that replace this one, each a list of lines.

    Returns `[lineas]` untouched if the box already fits, or if it carries an
    escape that does not compile —`eventos.NoSePuede`—: that page does not
    reach the ROM, so there is nothing to arrange.

    It is memoized by text: the math is pure, and a map is loaded several
    times per conversion —each time with all its boxes— so most calls repeat
    an earlier one. A copy is returned, because some callers add lines to
    what they receive.
    """
    clave = (tuple(lineas), columnas, renglones)
    if clave not in _reajustados:
        _reajustados[clave] = _reajustar(list(lineas), columnas, renglones)
    return [list(cuadro) for cuadro in _reajustados[clave]]


_reajustados = {}


def _reajustar(lineas, columnas, renglones):
    try:
        if entra(lineas, columnas, renglones):
            return [lineas]
        sin_cola, cola = _cola(lineas)
    except eventos.NoSePuede:
        return [lineas]

    cabeza = []
    if len(sin_cola) > 1 and es_hablante(sin_cola[0]):
        cabeza = [sin_cola[0]]
        sin_cola = sin_cola[1:]
    cuerpo = renglones - len(cabeza)

    palabras, cortes = _palabras(sin_cola, columnas)
    tramos = _tramos(palabras, cortes, columnas, cuerpo) or [[]]
    cuadros = [cabeza + tramo for tramo in tramos]
    if not cuadros[-1]:
        cuadros[-1].append("")
    cuadros[-1][-1] += cola
    return cuadros


def reajustar_comandos(comandos, columnas=constantes.COLUMNAS,
                       renglones=constantes.LINEAS):
    """A list of commands from `rom/data/` —dictionaries, as they are in the
    JSON— with each text box reflowed.

    A `ShowMessage` with its `ShowMessage_2`s is replaced by one or more
    boxes in the same format, with the same `indent`. What is not text, and
    the boxes that already fit, come out as **the same objects**: whoever
    compares with `is` knows what changed.
    """
    salida = []
    i = 0
    while i < len(comandos):
        comando = comandos[i]
        if comando["code"] != eventos.SHOW_MESSAGE:
            salida.append(comando)
            i += 1
            continue
        j = i + 1
        while j < len(comandos) and comandos[j]["code"] == eventos.SHOW_MESSAGE_2:
            j += 1
        originales = comandos[i:j]
        lineas = [c["string"] for c in originales]
        cuadros = reajustar(lineas, columnas, renglones)
        if cuadros == [lineas]:
            salida.extend(originales)
        else:
            for cuadro in cuadros:
                for k, texto in enumerate(cuadro):
                    salida.append({
                        "code": (eventos.SHOW_MESSAGE if k == 0
                                 else eventos.SHOW_MESSAGE_2),
                        "indent": comando["indent"],
                        "parameters": [],
                        "string": texto,
                    })
        i = j
    return salida
