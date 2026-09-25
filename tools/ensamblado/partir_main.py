"""Parte `rom/src/main.s` en un archivo por subsistema, sin cambiar un byte.

    python3 tools/ensamblado/partir_main.py            parte rom/src/main.s
    python3 tools/ensamblado/partir_main.py --ver      sólo muestra los cortes
    python3 tools/ensamblado/partir_main.py --dir D    lee y escribe en D
    python3 tools/ensamblado/partir_main.py --colgadas los comentarios que
                                               el corte deja apuntando mal

Es un script de una sola vez que se queda en el árbol mientras haya ramas
abiertas desde antes del corte: sobre una de ésas se vuelve a correr y la parte
igual —ver la tarea `partir-main.s`—. Cuando no quede ninguna, se borra.

**Cortar no reordena.** Cada archivo es un tramo contiguo del `main.s` viejo,
en el mismo orden, y `main.s` queda con lo que no se movió y un `.include` por
tramo: lo que ve `ca65` es el mismo texto, línea por línea. Por eso la ROM y la
tabla de símbolos salen iguales, y por eso cada tramo hereda el `.segment` y
los anchos de registro del anterior —no son de cada archivo sino de la
posición—.

Los cortes no están por número de línea sino por **ancla**: una expresión que
tiene que aparecer una sola vez, y el corte cae al principio del comentario que
la precede —o en ella misma, si es una marca de sección—. Así el script
sobrevive a que `main.s` se mueva, y si un ancla desaparece o se duplica, se
niega en vez de cortar en otro lado.
"""

import argparse
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (ancla, archivo). `None` como archivo: el tramo se queda escrito en `main.s`.
# El primero no tiene ancla: es el principio.
TRAMOS = [
    (None, None),
    (r"^INIDISP\s*=", "registros.s"),
    (r"^; --- la RAM del banco 1 -", "ram_lejana.s"),
    (r'^\.include "event_opcodes\.inc"', None),
    (r'^\.segment "ZEROPAGE"', "pagina_cero.s"),
    (r"^\.proc reset\b", "arranque.s"),
    (r"^\.proc cargar_mapa_sin_eventos\b", "cargar_mapa.s"),
    (r"^\.proc leer_pagina\b", "paginas_de_eventos.s"),
    (r"^\.proc correr_codigo\b", "interprete.s"),
    (r"^\.proc var_apuntar\b", "variables.s"),
    (r"^\.proc tabla_canal\b", "tinte.s"),
    (r"^\.proc en_el_grupo\b", "grupo.s"),
    (r"^\.proc paso_de_ruta\b", "ruta_del_heroe.s"),
    (r"^\.proc dma_origen\b", "cargar_graficos.s"),
    (r"^\.proc ruta_para_evento\b", "rutas_de_eventos.s"),
    (r"^\.proc evento_en_celda\b", "tecla_de_accion.s"),
    (r"^\.proc flash_empezar\b", "destello_de_personaje.s"),
    (r"^\.proc animar_ruta_ev\b", "eventos_caminando.s"),
    (r"^; --- guardar y cargar la partida -", "partida.s"),
    (r"^; --- la pantalla de título -", "titulo.s"),
    (r"^; --- la pantalla de ranuras -", "ranuras.s"),
    (r"^; --- el menú de pausa -", "menu.s"),
    (r"^; --- las pantallas de texto -", "pantallas_de_texto.s"),
    (r"^; --- la batalla -", "batalla_puentes.s"),
    (r"^; --- la lluvia -", "lluvia.s"),
    (r"^; --- el MSU-1 -", "msu1.s"),
    (r"^; --- el paquete de audio de cada mapa -", "paquete_de_audio.s"),
    (r"^; --- los efectos de sonido -", "efectos_de_sonido.s"),
    (r"^; --- la pantalla de ítems -", "items.s"),
    (r"^; --- los eventos quietos que animan igual -", "quietos_que_animan.s"),
    (r"^; --- el cartel del ShowPicture -", "imagen.s"),
    (r"^; --- la animación de batalla -", "animacion_de_batalla.s"),
    (r"^; --- el giro hacia el héroe -", "giro_hacia_el_heroe.s"),
    (r"^\.proc subir_pose_npc\b", "npcs.s"),
    (r"^\.proc celda_vecina_existe\b", "celdas.s"),
    (r"^; --- el destello de pantalla -", "destello_de_pantalla.s"),
    (r"^; --- la cámara corrida sin el héroe -", "camara.s"),
    (r"^; --- la ventana móvil del mapa -", "ventana_del_mapa.s"),
    (r"^; --- la ventana de mensaje -", "mensajes.s"),
    (r"^; --- lo que va sí o sí dentro del vblank -", "vblank.s"),
    (r"^; --- la animación del ChipSet -", "animacion_del_chipset.s"),
    (r"^PASS_DOWN\s*=", "heroe.s"),
    (r"^; --- el cronómetro -", "cronometro.s"),
    (r"^; --- armado de OAM -", "oam.s"),
    (r"^; --- lectura del control -", "control.s"),
    (r"^; --- carga al SPC700 -", "spc700.s"),
    (r'^\.segment "BSS"', "ram_baja.s"),
    (r"^\.proc irq_musica\b", "musica.s"),
    (r'^\.segment "FAR"', "banco1.s"),
    (r"^; --- el nivel y el máximo en el menú -", "nivel.s"),
    (r"^; --- una medicina desde el menú -", "medicina.s"),
    (r"^; --- el equipo y las habilidades desde un evento -",
     "equipo_desde_eventos.s"),
    (r"^\.proc ba_azar\b", "batalla.s"),
    (r"^; --- usar un ítem en la pelea -", "batalla_items.s"),
    (r"^; --- ejecutar una habilidad -", "batalla_habilidades.s"),
    (r"^; --- el lazo de la pelea -", "batalla_lazo.s"),
    (r"^; --- las páginas de evento de la tropa -", "batalla_tropa.s"),
    (r"^; --- la escena de la pelea -", "batalla_escena.s"),
    (r"^\.proc batalla_correr\b", "batalla_correr.s"),
    (r"^; --- el banco de la pantalla, también fuera del banco 0 -",
     "banco_de_la_pantalla.s"),
    (r"^; --- los encuentros al azar, fuera del banco 0 -", "encuentros.s"),
    (r"^; --- el equipo y la tienda, fuera del banco 0 -",
     "pantalla_de_equipo.s"),
    (r"^; --- la tienda -", "tienda.s"),
    (r"^\.align \$8000", "cabecera.s"),
]

ABREN = re.compile(r"^\s*\.(proc|scope|macro|if|ifdef|ifndef|ifblank|ifnblank"
                   r"|ifconst|ifref|ifnref|repeat|struct|union|enum)\b", re.I)
CIERRAN = re.compile(r"^\s*\.(endproc|endscope|endmacro|endif|endrep|endrepeat"
                     r"|endstruct|endunion|endenum)\b", re.I)
SEGMENTO = re.compile(r"^\s*\.segment\b")
ANONIMA = re.compile(r"^\s*:(\s|$)")
A_ANONIMA = re.compile(r":(\++|-+)")


def sin_comentario(linea):
    """La línea hasta el `;`, salteando los que están adentro de comillas."""
    adentro = False
    for i, c in enumerate(linea):
        if c == '"':
            adentro = not adentro
        elif c == ";" and not adentro:
            return linea[:i]
    return linea


def es_codigo(linea):
    return bool(sin_comentario(linea).strip())


def corte(lineas, ancla):
    """El índice donde empieza el tramo del ancla: el principio del comentario
    que la precede, con el `.segment` que haya en el medio adentro."""
    hallados = [i for i, l in enumerate(lineas) if re.search(ancla, l)]
    if len(hallados) != 1:
        sys.exit("el ancla %r aparece %d veces: tiene que ser una" %
                 (ancla, len(hallados)))
    i = hallados[0]
    # Una marca de sección es un encabezado: el tramo arranca ahí, y lo que
    # esté pegado arriba es el final del anterior.
    if lineas[i].startswith(";"):
        return i
    # Para atrás mientras sea comentario, blanco o un `.segment`.
    j = i
    while j > 0 and (not es_codigo(lineas[j - 1])
                     or SEGMENTO.match(lineas[j - 1])):
        j -= 1
    # `j` es la primera línea después del último código. Si en el medio hay un
    # `.segment`, lo que está antes del último blanco que lo precede es el
    # final del tramo anterior —el comentario de lo que se reservó arriba—.
    seg = [k for k in range(j, i + 1) if SEGMENTO.match(lineas[k])]
    if seg:
        k = seg[0]
        while k > j and lineas[k - 1].strip():
            k -= 1
        j = k
    while j < i and not lineas[j].strip():
        j += 1
    return j


def profundidad(lineas, hasta):
    p = 0
    for l in lineas[:hasta]:
        l = sin_comentario(l)
        if ABREN.match(l):
            p += 1
        elif CIERRAN.match(l):
            p -= 1
    return p


def anonimas_que_cruzan(lineas, cortes):
    """Los usos de `:+`/`:-` cuya etiqueta cae en otro tramo."""
    defs = [i for i, l in enumerate(lineas) if ANONIMA.match(l)]
    tramo = lambda i: sum(1 for c in cortes if c <= i)   # noqa: E731
    malos = []
    for i, l in enumerate(lineas):
        codigo = sin_comentario(l)
        if ANONIMA.match(l):
            codigo = codigo.split(":", 1)[1]
        for m in A_ANONIMA.finditer(codigo):
            n = len(m.group(1))
            if m.group(1)[0] == "+":
                destino = [d for d in defs if d > i][n - 1:n]
            else:
                destino = [d for d in defs if d < i][-n:][:1]
            if not destino:
                malos.append((i + 1, "sin destino"))
            elif tramo(destino[0]) != tramo(i):
                malos.append((i + 1, destino[0] + 1))
    return malos


def partir(texto):
    """[(archivo o None, texto del tramo)], en orden."""
    lineas = texto.split("\n")
    if texto.endswith("\n"):
        lineas = [l + "\n" for l in lineas[:-1]]
    else:
        sys.exit("main.s no termina en fin de línea")
    cortes = [0] + [corte(lineas, a) for a, _ in TRAMOS[1:]]
    if cortes != sorted(cortes) or len(set(cortes)) != len(cortes):
        sys.exit("las anclas no están en orden: %s" % cortes)
    for c, (a, _) in zip(cortes[1:], TRAMOS[1:]):
        if profundidad(lineas, c):
            sys.exit("el corte de %r cae adentro de un bloque" % a)
    malos = anonimas_que_cruzan(lineas, cortes)
    if malos:
        sys.exit("etiquetas anónimas que cruzan un corte: %s" % malos)
    tramos = []
    for k, (c, (_, archivo)) in enumerate(zip(cortes, TRAMOS)):
        fin = cortes[k + 1] if k + 1 < len(cortes) else len(lineas)
        tramos.append((archivo, c + 1, "".join(lineas[c:fin])))
    return tramos


DEFINE = re.compile(r"^(?:\.proc\s+(\w+)|(\w+):|(\w+)\s*=)", re.M)
POSICION = re.compile(r"\b(arriba|abajo|este archivo|del archivo)\b")
CITADO = re.compile(r"`([A-Za-z_]\w*)")


def colgadas(tramos):
    """Los comentarios que ubican algo por posición —"arriba", "abajo", "este
    archivo"— y citan un símbolo que después del corte vive en otro archivo.
    Es la lista de trabajo del commit de prosa, no una prueba: el comentario
    puede estar hablando de otra cosa."""
    donde = {}
    for archivo, _, t in tramos:
        for m in DEFINE.finditer(t):
            donde.setdefault(next(g for g in m.groups() if g), archivo or "main.s")
    for archivo, desde, t in tramos:
        for k, linea in enumerate(t.split("\n")):
            comentario = linea.partition(";")[2]
            if not POSICION.search(comentario):
                continue
            afuera = sorted({c for c in CITADO.findall(comentario)
                             if donde.get(c, archivo or "main.s") != (archivo or "main.s")})
            sin_cita = not CITADO.search(comentario) and "archivo" in comentario
            if afuera or sin_cita:
                print("%s:%d (main.s:%d)  %s  %s" % (
                    archivo or "main.s", k + 1, desde + k,
                    ", ".join("%s está en %s" % (c, donde[c]) for c in afuera),
                    comentario.strip()[:80]))


def principal(tramos):
    return "".join(t if a is None else '.include "%s"\n' % a
                   for a, _, t in tramos)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dir", default=os.path.join(RAIZ, "rom", "src"))
    parser.add_argument("--ver", action="store_true")
    parser.add_argument("--colgadas", action="store_true",
                        help="los comentarios que ubican por posición algo "
                             "que el corte deja en otro archivo")
    args = parser.parse_args()
    ruta = os.path.join(args.dir, "main.s")
    texto = open(ruta, encoding="utf-8").read()
    if any('.include "%s"' % a in texto for _, a in TRAMOS if a):
        sys.exit("%s ya está partido" % ruta)
    tramos = partir(texto)
    # La prueba de que no se perdió ni se movió nada: los tramos, pegados en
    # orden, son el archivo de antes.
    assert "".join(t for _, _, t in tramos) == texto
    if args.colgadas:
        colgadas(tramos)
        return
    for archivo, desde, t in tramos:
        print("%6d %6d  %s" % (desde, t.count("\n"), archivo or "(main.s)"))
        if args.ver:
            print("        " + t.split("\n", 1)[0][:70])
    if args.ver:
        return
    for archivo, _, t in tramos:
        if archivo:
            destino = os.path.join(args.dir, archivo)
            if os.path.exists(destino):
                sys.exit("%s ya existe" % destino)
    for archivo, _, t in tramos:
        if archivo:
            with open(os.path.join(args.dir, archivo), "w",
                      encoding="utf-8") as f:
                f.write(t)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(principal(tramos))


if __name__ == "__main__":
    main()
