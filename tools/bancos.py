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
emite, así que el reparto se hace acá: lo que llega al ensamblador es un
segmento por banco, `BANKnn`, que es lo que espera un `.cfg` de `ld65` con un
área por banco.

**Lo único que este módulo asume del mapa de memoria es en qué banco arrancan
los datos generados**, `PRIMER_BANCO`. El resto lo sabe el `.cfg`.
"""


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


# El banco donde arrancan los datos generados. El 0 es el código y las tablas,
# y el 1 es `FAR`, el código a mano que vive afuera del banco 0.
PRIMER_BANCO = 2


def segmento_de(banco):
    """El nombre del segmento que va fijo al principio de `banco`."""
    return "BANK%02X" % banco


def _partir(linea, entran):
    """Parte una línea de datos en los primeros `entran` bytes y el resto.

    Sólo se puede entre operandos: una palabra partida entre dos bancos no es
    una palabra. Si el corte cae en el medio de una, es un error.
    """
    codigo, _, comentario = linea.partition(";")
    directiva, resto = codigo.strip().split(None, 1)
    ancho = ANCHOS[directiva]
    if entran % ancho:
        raise ValueError("el final del banco cae en el medio de un operando "
                         "de %d bytes: %r" % (ancho, linea.strip()))
    operandos = [o.strip() for o in resto.split(",")]
    cuantos = entran // ancho
    cola = ("  ; " + comentario.strip()) if comentario.strip() else ""
    primera = ("    %s %s%s" % (directiva, ", ".join(operandos[:cuantos]), cola)
               if cuantos else None)
    segunda = "    %s %s" % (directiva, ", ".join(operandos[cuantos:]))
    return primera, segunda, (len(operandos) - cuantos) * ancho


def resolver(rutas, segmento="RODATA", primer_banco=PRIMER_BANCO):
    """Reparte en bancos lo que esos archivos mandan a `segmento`.

    Cada `.segment "RODATA"` pasa a ser el segmento del banco que corre, y cada
    `.bloque N` que no entra en lo que queda se convierte en el cambio al banco
    siguiente. Una línea de datos que no entra entera —la grilla de celdas mide
    más que un banco, y se recorre con un puntero, no por DMA— se parte entre
    los dos, así que sus bytes quedan contiguos en el archivo.

    `rutas` va **en el orden en que el ensamblador las va a leer**, que es el
    de los `.include`: el reparto depende de todo lo que haya antes. Lo que un
    archivo mande a otro segmento —las tablas del banco 0— no cuenta.

    Devuelve cuántos `.bloque` se resolvieron y cuántos empezaron banco.
    """
    banco, usado = primer_banco, 0
    resueltos, empezaron = 0, 0
    for ruta in rutas:
        with open(ruta) as handle:
            lineas = handle.read().splitlines()
        salida, actual = [], None

        def cambiar(porque=""):
            nonlocal banco, usado
            banco, usado = banco + 1, 0
            salida.append('.segment "%s"%s' % (segmento_de(banco), porque))

        for linea in lineas:
            directiva = linea.split(";")[0].strip()
            if directiva.startswith(".segment"):
                actual = directiva.split(None, 1)[1].strip().strip('"')
                salida.append('.segment "%s"' % segmento_de(banco)
                              if actual == segmento else linea)
                continue
            if actual != segmento:
                salida.append(linea)
                continue
            # Un banco lleno se deja antes de escribir nada más, etiquetas
            # incluidas: una etiqueta al final de un banco apuntaría a la
            # dirección que sigue a `$FFFF`, que no es la ROM.
            if usado == BANCO and directiva:
                cambiar()
            if directiva.startswith(".bloque "):
                pide = int(directiva.split()[1])
                resueltos += 1
                if pide > BANCO - usado:
                    empezaron += 1
                    cambiar("  ; lo que sigue mide %d y no entraba" % pide)
                continue
            if directiva.startswith(".align "):
                # Ésta se queda: alinear no es acomodar bancos, y `ca65` la
                # sabe hacer. Acá sólo hay que contarla.
                unidad = int(directiva.split()[1])
                usado += (unidad - usado % unidad) % unidad
                salida.append(linea)
                continue
            tamano = _tamano(linea)
            if usado + tamano <= BANCO:
                usado += tamano
                salida.append(linea)
                continue
            primera, segunda, queda = _partir(linea, BANCO - usado)
            if primera:
                salida.append(primera)
            cambiar()
            salida.append(segunda)
            usado = queda
        colados = [l for l in salida if l.split(";")[0].strip()
                   .startswith(".bloque")]
        if colados:
            # Un `.bloque` que llegue al ensamblador no lo entiende nadie más
            # que `w65`, así que pasaría callado hasta el día que se vaya.
            raise ValueError(
                "%s dejó %d `.bloque` sin resolver, el primero %r: está fuera "
                "de %s, y ahí el acomodo no se puede calcular"
                % (ruta, len(colados), colados[0].strip(), segmento))
        with open(ruta, "w") as handle:
            handle.write("\n".join(salida) + "\n")
    return resueltos, empezaron


# --- el mapa de memoria, para `ld65` -----------------------------------------
#
# LoROM de 4 MB: 128 bancos de 32 KB, cada uno visto en `$8000-$FFFF` de su
# número. Los dos últimos del archivo no se usan: en la consola, los bancos
# `$7E` y `$7F` **son** la WRAM, y un dato ahí se leería como RAM.
BANCOS = 128
BANCOS_RESERVADOS = 2

# La pila arranca en `$1FFF` y crece hacia abajo, hacia el BSS: los dos
# comparten los 8 KB bajos. Esto es lo que se le deja a la pila, que medida
# baja 24 bytes en la cadena de llamadas más honda.
PILA = 256


def cfg():
    """El `.cfg` de `ld65`: un área por banco, y cada segmento en la suya.

    Un área con `fill = yes` se rellena hasta el final, así que cada banco
    ocupa sus 32 KB en el archivo aunque su segmento no los llene, y un
    segmento que se pase hace fallar el link en vez de invadir el siguiente.
    Los `BANKnn` son opcionales porque cuántos se usan depende del cartucho.

    El `align = $8000` no mueve nada —cada segmento arranca al principio de su
    área, que ya está alineado a eso—, pero `ld65` exige que un segmento
    declare al menos la alineación de los `.align` que lleva adentro.
    """
    memoria = [
        # La RAM no va al archivo: se reparte por dirección, no por offset.
        'ZP:   start = $0000, size = $0100, type = rw, file = "";',
        'RAM:  start = $0100, size = $%04X, type = rw, file = "";'
        % (0x1F00 - PILA),
        # El banco 0: el código y las tablas, y la cabecera y los vectores
        # al final, donde los busca la consola.
        "ROM:  start = $008000, size = $7FC0, fill = yes;",
        "HEAD: start = $00FFC0, size = $0020, fill = yes;",
        "VECT: start = $00FFE0, size = $0020, fill = yes;",
    ]
    segmentos = [
        "ZEROPAGE: load = ZP,   type = zp;",
        "BSS:      load = RAM,  type = bss;",
        "CODE:     load = ROM,  type = ro;",
        "TABLAS:   load = ROM,  type = ro;",
        "HEADER:   load = HEAD, type = ro;",
        "VECTORS:  load = VECT, type = ro;",
        # El código a mano que vive afuera del banco 0.
        "FAR:      load = %s, type = ro, align = $8000;" % segmento_de(1),
    ]
    for banco in range(1, BANCOS - BANCOS_RESERVADOS):
        memoria.append("%s: start = $%02X8000, size = $8000, fill = yes;"
                       % (segmento_de(banco), banco))
        if banco >= PRIMER_BANCO:
            segmentos.append("%s: load = %s, type = ro, align = $8000, "
                             "optional = yes;"
                             % (segmento_de(banco), segmento_de(banco)))
    # Los dos reservados van igual al archivo, en cero: el cartucho mide 4 MB,
    # que es lo que dice la cabecera y lo que esperan los flash carts.
    memoria.append("RESERVADO: start = $%02X8000, size = $%X, fill = yes;"
                   % (BANCOS - BANCOS_RESERVADOS, 0x8000 * BANCOS_RESERVADOS))
    return ("# Generado por tools/bancos.py: el mapa de memoria de la ROM.\n"
            "MEMORY {\n%s\n}\nSEGMENTS {\n%s\n}\n"
            % ("\n".join("    " + m for m in memoria),
               "\n".join("    " + s for s in segmentos)))
