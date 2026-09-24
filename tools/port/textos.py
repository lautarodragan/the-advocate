r"""Los cuadros de texto rearmados para el ancho de la SNES.

RM2k no tiene auto-wrap: cada salto de un `ShowMessage` lo puso el autor a mano,
pensando en una ventana de 320 px. La de acá es más angosta —`ventana.COLUMNAS`
caracteres por renglón—, y hasta esto lo que no entraba se truncaba.

`reajustar` recibe los renglones de **un** cuadro, tal como están en `data/`, y
devuelve uno o más cuadros que entran. Es una función pura: el mismo cuadro da
siempre el mismo resultado, y eso es lo que permite aplicarla en cada build en
vez de guardar su salida.

Las reglas, y de dónde sale cada una:

* **Un cuadro que entra se devuelve tal cual**, con sus saltos y sus espacios.
  La mayoría entra, y así conservan todo lo que el autor decidió.
* **La línea del que habla no se toca** —`KERSH`, `MANTA`, `?????`— y el
  cuerpo tiene un renglón menos.
* **Un salto original es un buen lugar para cortar, no uno obligado.**
  Tratarlo como obligado dejaba una palabra sola en un renglón ("it still /
  is.") y hacía que más cuadros no entraran.
* **Lo que no entra en un cuadro se parte en varios**, cortando entre
  oraciones si se puede, y **cada uno repite la línea del que habla.** Es lo
  que hace el juego: medido el 2026-09-24, de los cuadros seguidos del mismo
  personaje ninguno deja de repetir el nombre, y el autor mismo parte así una
  frase —`MANTA` / "...up to the Emitter Room -" y `MANTA` / "- where the Link
  is projected!"—.
* **La cola de escapes** —`\|` y `\^`, ver `eventos.cola_de_escapes`— va al
  final del último cuadro, que es donde el jugador la veía.

Lo que se pierde en un cuadro rearmado son los espacios de más entre palabras:
las palabras se vuelven a juntar con uno. En uno que entra, no se pierde nada.
"""

import re

from port import eventos
from port import ventana

# Un fin de oración, con las comillas o el paréntesis que lo cierren: cortar
# ahí es gratis. `...` entra por el punto.
FIN_DE_ORACION = re.compile(r"""[.!?]["')]*$""")
# Una pausa menor: cortar ahí cuesta poco.
PAUSA = re.compile(r"""[,;:\-]["')]*$""")

# Los costos de cortar un renglón después de una palabra. Son gusto y no una
# medida: con otros valores el mismo cuadro sale de otra forma. Éstos son los
# que se probaron sobre la introducción y Lashe City el 2026-09-24.
COSTO_FIN_DE_ORACION = 0
COSTO_PAUSA = 15
COSTO_CUALQUIERA = 40
DESCUENTO_SALTO_ORIGINAL = 10   # donde cortaba el autor
COSTO_HUERFANA = 200            # una palabra sola en el último renglón
PESO_HUECO = 20                 # el hueco de un renglón corto, al cuadrado


def ancho(texto):
    """Cuántas columnas ocupa: un caracter, una columna. La fuente es de ancho
    fijo, y los únicos escapes que compilan van en la cola, afuera de esto."""
    return len(texto)


def es_hablante(linea):
    """Si el renglón nombra al que habla: todo en mayúsculas, corto, y sin
    puntuación de frase al final.

    `?????` es el caso raro que tiene que entrar —lo usa el juego mientras no
    se sabe quién habla—, así que un signo de pregunta al final sólo cuenta si
    no hay nada más que signos de pregunta. "WHAT?" es una frase gritada, no
    un nombre.
    """
    texto = linea.strip()
    if not texto or len(texto) > 20 or texto != texto.upper():
        return False
    if set(texto) == {"?"}:
        return True
    return not texto.endswith((".", "!", "?", ","))


def entra(lineas, columnas=ventana.COLUMNAS, renglones=ventana.LINEAS):
    """Si el cuadro se ve entero, sin contar su cola de escapes."""
    sin_cola, _pausas, _autocierre = eventos.cola_de_escapes(lineas)
    return (len(sin_cola) <= renglones
            and all(ancho(t) <= columnas for t in sin_cola))


def _cola(lineas):
    """La cola de escapes del cuadro, tal como está escrita, y los renglones
    sin ella."""
    sin_cola, _pausas, _autocierre = eventos.cola_de_escapes(lineas)
    sin_cola = list(sin_cola)
    if not sin_cola:
        return sin_cola, ""
    return sin_cola, lineas[-1][len(sin_cola[-1]):]


def _palabras(renglones, columnas):
    """Las palabras del cuerpo, y después de cuáles cortaba el autor.

    Una palabra más ancha que un renglón se parte a la fuerza: no hay otra
    forma de mostrarla.
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
    return costo


def _renglones(palabras, cortes, columnas):
    """Las palabras en renglones, eligiendo los cortes que cuestan menos.

    Es el algoritmo de párrafo de TeX en chico: programación dinámica sobre
    dónde termina cada renglón. El último renglón no paga su hueco, pero sí
    paga quedar con una sola palabra.
    """
    n = len(palabras)
    if n == 0:
        return []
    mejor = [None] * (n + 1)          # (costo, desde dónde)
    mejor[0] = (0, None)
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            renglon = " ".join(palabras[i:j])
            if ancho(renglon) > columnas:
                break
            if mejor[i] is None:
                continue
            costo = mejor[i][0]
            if j < n:
                hueco = columnas - ancho(renglon)
                costo += hueco * hueco / PESO_HUECO
                costo += _costo_de_cortar(palabras, cortes, j - 1)
            elif j - i == 1 and i > 0:
                costo += COSTO_HUERFANA
            # `<` y no `<=`: ante un empate gana el renglón más largo, que es
            # el que se encontró primero. Es lo que lo hace determinístico.
            if mejor[j] is None or costo < mejor[j][0]:
                mejor[j] = (costo, i)
    salida = []
    j = n
    while j > 0:
        i = mejor[j][1]
        salida.append(" ".join(palabras[i:j]))
        j = i
    return salida[::-1]


def _tramos(palabras, cortes, columnas, cuerpo):
    """Las palabras repartidas en tantos cuadros como hagan falta.

    Cada cuadro se llena con oraciones enteras mientras entren. Una oración que
    sola no entra en un cuadro se parte por renglones.
    """
    oraciones = []
    desde = 0
    for i, palabra in enumerate(palabras):
        if FIN_DE_ORACION.search(palabra) or i == len(palabras) - 1:
            oraciones.append((desde, i + 1))
            desde = i + 1

    def renglones_de(a, b):
        locales = {c - a for c in cortes if a <= c < b}
        return _renglones(palabras[a:b], locales, columnas)

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
        # La oración sola no entra en un cuadro: se reparte por renglones.
        todos = renglones_de(a, b)
        for k in range(0, len(todos) - cuerpo, cuerpo):
            tramos.append(todos[k:k + cuerpo])
        resto = todos[(len(todos) - 1) // cuerpo * cuerpo:]
        inicio = b - len(" ".join(resto).split())
        fin = b
    if fin > inicio:
        tramos.append(renglones_de(inicio, fin))
    return tramos


def reajustar(lineas, columnas=ventana.COLUMNAS, renglones=ventana.LINEAS):
    """Los cuadros que reemplazan a éste, cada uno una lista de renglones.

    Devuelve `[lineas]` sin tocar si el cuadro ya entra, o si trae un escape
    que no compila —`eventos.NoSePuede`—: esa página no llega a la ROM, así
    que no hay nada que acomodar.
    """
    lineas = list(lineas)
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


def reajustar_comandos(comandos, columnas=ventana.COLUMNAS,
                       renglones=ventana.LINEAS):
    """Una lista de comandos de `data/` —diccionarios, como están en el JSON—
    con cada cuadro de texto rearmado.

    Un `ShowMessage` con sus `ShowMessage_2` se reemplaza por uno o más cuadros
    del mismo formato, con el mismo `indent`. Lo que no es texto, y los cuadros
    que ya entraban, salen **los mismos objetos**: quien compare con `is` sabe
    qué cambió.
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
