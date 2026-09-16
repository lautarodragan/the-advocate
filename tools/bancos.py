"""El acomodo de bancos, que lo decide el conversor y no el ensamblador.

Un DMA que cruza de banco no lee la ROM del banco siguiente: lee la WRAM. Por
eso todo lo que la ROM sube por DMA —una pose, un tilemap, un bloque de
muestras— tiene que entrar **entero** en un banco, y cuando no entra en lo que
queda del que corre hay que rellenar hasta el próximo.

Hasta el 2026-09-16 esa decisión la tomaba el ensamblador, con una directiva
nuestra: `.bloque N` quería decir "lo que sigue mide N bytes, rellená si no
entra". Funcionaba, pero ataba el port a tener un ensamblador propio: `ld65` no
sabe acomodar bloques de tamaño variable, y ésa es la única razón por la que la
directiva existía. Quien sí conoce los tamaños es el conversor, porque los
emite, así que la cuenta se hace acá y lo que llega al ensamblador es relleno
explícito.

**Lo único que este módulo asume del mapa de memoria es que RODATA arranca
pegado a un banco.** No necesita saber en cuál: el relleno sólo depende de
cuánto se lleva acumulado desde ese arranque. Que el arranque esté alineado lo
comprueba el ensamblador, que es quien conoce las áreas.
"""

import re

BANCO = 0x8000

# Cuánto ocupa cada operando de las directivas que emiten bytes.
ANCHOS = {".byte": 1, ".word": 2, ".addr": 2, ".dword": 4}


def _operandos(resto):
    """Cuántos operandos tiene una lista separada por comas.

    Las comas de adentro de una cadena no separan. El conversor no emite
    cadenas hoy, pero la regla es la del ensamblador y sale más barato
    respetarla que descubrir el día que las emita.
    """
    resto = resto.split(";")[0].strip()
    if not resto:
        return 0
    cuantos, comillas = 1, False
    for c in resto:
        if c == '"':
            comillas = not comillas
        elif c == "," and not comillas:
            cuantos += 1
    return cuantos


def _tamano(linea):
    """Cuántos bytes ocupa una línea, o None si no ocupa ninguno."""
    partes = linea.strip().split(None, 1)
    if not partes:
        return 0
    if partes[0] == ".res":
        # Las que deja este mismo módulo, por si alguien lo corre dos veces.
        return int(partes[1].split(";")[0].strip())
    ancho = ANCHOS.get(partes[0])
    if ancho is None:
        return 0
    return ancho * _operandos(partes[1] if len(partes) > 1 else "")


def resolver(rutas, segmento="RODATA"):
    """Reemplaza cada `.bloque N` de esos archivos por el relleno que le toca.

    `rutas` va **en el orden en que el ensamblador las va a leer**, que es el
    de los `.include`: el acomodo depende de todo lo que haya antes. Sólo se
    cuenta lo que cae en `segmento`; lo que un archivo mande a otro —las tablas
    del banco 0— no mueve este offset.

    Devuelve cuántos `.bloque` se resolvieron y cuántos rellenaron de verdad.
    """
    offset = 0
    resueltos, rellenaron = 0, 0
    for ruta in rutas:
        with open(ruta) as handle:
            lineas = handle.read().splitlines()
        salida, actual = [], None
        for linea in lineas:
            directiva = linea.split(";")[0].strip()
            if directiva.startswith(".segment"):
                actual = directiva.split(None, 1)[1].strip().strip('"')
                salida.append(linea)
                continue
            if actual != segmento:
                salida.append(linea)
                continue
            if directiva.startswith(".bloque "):
                pide = int(directiva.split()[1])
                queda = BANCO - offset % BANCO
                relleno = queda if pide > queda else 0
                resueltos += 1
                if relleno:
                    rellenaron += 1
                    salida.append(".res %d%s"
                                  % (relleno, _porque(linea, pide)))
                    offset += relleno
                continue
            if directiva.startswith(".align "):
                # Ésta se queda: alinear no es acomodar bancos, y `ca65` la
                # sabe hacer. Acá sólo hay que contarla.
                unidad = int(directiva.split()[1])
                offset += (unidad - offset % unidad) % unidad
                salida.append(linea)
                continue
            offset += _tamano(linea)
            salida.append(linea)
        colados = [l for l in salida if l.split(";")[0].strip()
                   .startswith(".bloque")]
        if colados:
            # Un `.bloque` que llegue al ensamblador no rompe hoy —la
            # directiva todavía existe para los dos de `main.s`— así que
            # pasaría callado, y el día que se vaya rompería lejos de acá.
            raise ValueError(
                "%s dejó %d `.bloque` sin resolver, el primero %r: está fuera "
                "de %s, y ahí el acomodo no se puede calcular"
                % (ruta, len(colados), colados[0].strip(), segmento))
        with open(ruta, "w") as handle:
            handle.write("\n".join(salida) + "\n")
    return resueltos, rellenaron


def _porque(linea, pide):
    """El comentario que llevaba el `.bloque`, más lo que hacía falta.

    Un `.res 4096` suelto no dice nada; el número que lo explica es el tamaño
    del bloque que venía detrás, que es el que no entraba.
    """
    comentario = linea.split(";", 1)
    cola = ("  ; " + comentario[1].strip()) if len(comentario) > 1 else ""
    return "  ; hasta el próximo banco: lo que sigue mide %d%s" % (pide, cola)
