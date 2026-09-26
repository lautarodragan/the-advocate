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
* **Un renglón que parte una oración va lleno**; uno con oraciones enteras
  puede quedar corto. Lo que taro no quiere ver es un renglón que se
  interrumpe mucho antes del borde —"Remember," solo, y abajo el resto—, y
  eso pasa cuando cortar en un punto sale más barato que llenar.
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

# Los costos. Son gusto y no una medida: con otros valores el mismo cuadro sale
# de otra forma. Los primeros se probaron sobre la introducción y Lashe City el
# 2026-09-24; los del hueco, la cola y el cuadro de más salieron el mismo día de
# lo que taro jugó hasta los Back Alleys, comparando contra la versión anterior
# en todos los cuadros del juego.
#
# Cortar un renglón después de una palabra:
COSTO_FIN_DE_ORACION = 0
COSTO_PAUSA = 15
COSTO_CUALQUIERA = 40
DESCUENTO_SALTO_ORIGINAL = 10   # donde cortaba el autor
COSTO_HUERFANA = 200            # una palabra sola en el último renglón
# Entre un nombre propio y su número —"Sector / 33."—. Es casi prohibido: sale
# más caro que un cuadro de más.
COSTO_ANTES_DE_NUMERO = 1000

# El hueco que deja un renglón que no es el último. Cuánto pesa depende de dónde
# corta, y ésa es la regla que más cambia lo que se ve: **un renglón que parte
# una oración tiene que ir lleno.** Uno que tiene oraciones enteras puede quedar
# corto —"Time is running out." / "There's no turning back."—, porque se lee
# como un salto que el autor quiso. Con un solo peso para todos, cortar en un
# fin de oración era tan barato frente al hueco que el reajuste dejaba
# "Remember," o "Well," solos en un renglón para que los de abajo terminaran
# en punto: de eso se quejó taro.
PESO_HUECO = 20                 # oraciones enteras: el hueco al cuadrado / 20
PESO_HUECO_PAUSA = 8            # corta en una coma: al cuadrado / 8
PESO_HUECO_PARTIDO = 1000       # parte una oración: al cubo, relativo al ancho

# El pedazo de oración que queda del otro lado de un corte —"sure." al principio
# de un renglón, "There" al final—, si es más corto que esto. Es la huérfana
# generalizada: "in time?" solo abajo se ve tan interrumpido como "Well," arriba.
COLA_MINIMA = 16
PESO_COLA = 3                   # lo que le falta, al cuadrado / 3

# Un cuadro de más es una tecla de más para el jugador. Si lo más lindo no entra
# en un cuadro pero hay una forma que entra y cuesta a lo sumo esto más, gana
# la que entra.
COSTO_CUADRO_DE_MAS = 300


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
    if (palabra[:1].isupper() and palabra[-1:].isalpha()
            and i + 1 < len(palabras) and palabras[i + 1][:1].isdigit()):
        costo += COSTO_ANTES_DE_NUMERO
    return costo


def _costo_del_renglon(palabras, cortes, i, j, columnas):
    """Lo que cuesta un renglón con las palabras de `i` a `j`: su hueco, el
    corte con que termina y los pedazos de oración que deja sueltos.

    El último renglón no paga su hueco —termina donde termina el texto—, pero
    sí quedar con una sola palabra o con un pedazo corto de la oración de
    arriba.
    """
    n = len(palabras)
    largo = ancho(" ".join(palabras[i:j]))
    fines = [k for k in range(i, j) if FIN_DE_ORACION.search(palabras[k])]
    empieza_oracion = i == 0 or FIN_DE_ORACION.search(palabras[i - 1])
    costo = 0
    # El final de una oración que empezó en el renglón de arriba.
    if not empieza_oracion and (j == n or (fines and fines[0] < j - 1)):
        hasta = fines[0] + 1 if fines else j
        costo += _costo_de_fragmento(palabras[i:hasta])
    if j == n:
        if j - i == 1 and i > 0:
            costo += COSTO_HUERFANA
        return costo
    # El principio de una oración que sigue en el renglón de abajo.
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
    """Un pedazo de oración separado del resto por un corte de renglón."""
    falta = max(0, COLA_MINIMA - ancho(" ".join(palabras)))
    return falta * falta / PESO_COLA


def _renglones(palabras, cortes, columnas, maximo=None):
    """Las palabras en renglones, eligiendo los cortes que cuestan menos.

    Es el algoritmo de párrafo de TeX en chico: programación dinámica sobre
    dónde termina cada renglón, llevando la cuenta de cuántos van.
    """
    n = len(palabras)
    if n == 0:
        return []
    # mejor[j][k]: el costo de poner las primeras j palabras en k renglones,
    # y desde dónde arranca el último.
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
                # `<` y no `<=`: ante un empate gana el renglón más largo,
                # que es el que se encontró primero. Es lo que lo hace
                # determinístico.
                if k + 1 not in mejor[j] or costo < mejor[j][k + 1][0]:
                    mejor[j][k + 1] = (costo, i)
    opciones = sorted(mejor[n].items(), key=lambda kv: (kv[1][0], kv[0]))
    elegido = opciones[0][0]
    if maximo is not None and elegido > maximo:
        # Lo más lindo no entra en un cuadro. Si hay una forma que entra y no
        # es mucho peor, se usa ésa: un cuadro de más es una tecla de más.
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

    Se recuerda por texto: la cuenta es pura, y un mapa se carga varias veces
    por conversión —cada vez con todos sus cuadros— así que la mayoría de las
    llamadas repiten una anterior. Se devuelve una copia, porque hay quien
    agrega renglones a lo que recibe.
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
