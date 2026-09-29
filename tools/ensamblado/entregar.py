#!/usr/bin/env python3
"""Deja el `release` armado en `/shared/builds/<fecha>-<commit>/` para que taro
lo juegue: `just entregar "<qué mirar>"`. La regla es la de "Sub-agentes" en
AGENTS.md; esto es esa regla escrita una sola vez.

    abl-entregar "qué mirar"
    abl-entregar "qué mirar" --actualizar-msu

El build lleva `abl.sfc`, `abl.sfc.dbg`, `abl.msu`, el `rom/src/` del commit
y un `LEEME.txt`. Las pistas de MSU-1 no: van a `/shared/msu/`, y sólo con
`--actualizar-msu`. El `abl.msu` va también ahí, siempre: ver `MSU_DEL_BUILD`.
"""

import argparse
import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import textwrap

# `realpath` y no `abspath`: `just herramientas` instala este script en el PATH
# como symlink, y lo que importa es dónde está el archivo de verdad.
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
RELEASE = os.path.join(RAIZ, "rom", "build", "release")
SHARED = os.environ.get("SHARED", "/shared")
BUILDS = os.path.join(SHARED, "builds")
MSU = os.path.join(SHARED, "msu")

# Lo que entra en la ROM: lo que mira `cartuchos.huella()` más lo que lee el
# conversor. Un cambio sin commitear ahí haría un build que no es el del commit
# que lo nombra. `README.md`, `docs/` o un `.box.yml` suelto no entran.
LO_QUE_ENTRA = ("rom/src", "tools", "parches", "data")

# `<fecha>-<commit>` y lo que siga. Sólo esos se cuentan y se borran: lo demás
# que haya en /shared/builds/ es de taro.
BUILD = re.compile(r"^(\d{4}-\d{2}-\d{2})-([0-9a-f]{7,40})")

# Lo que escribe esto adentro del build. Si el directorio ya existía, se pisa
# esto y nada más: taro deja ahí la partida de su emulador (`abl.ram`).
LO_NUESTRO = ("abl.sfc", "abl.sfc.dbg", "abl.msu", "LEEME.txt", "rom")

# **El `abl.msu` es del build, no de las pistas.** Lleva los fondos de batalla
# que el MSU-1 le sirve a la ROM —ver tools/port/msu_datos.py—, así que cambia
# con lo que cambie el conversor, y pesa 32 KB por fondo y no medio giga. Va en
# el build, para que cada `abl.sfc` tenga el suyo al lado, y se copia siempre a
# /shared/msu/, que es donde taro juega con MSU-1: ahí tiene que estar el del
# último build. Con el `abl.sfc` de otro build no se rompe nada: la ROM no
# encuentra su firma y lee los fondos de sí misma.
MSU_DEL_BUILD = "abl.msu"

# El comando de la huella tal cual lo escribe `/shared/msu/LEEME.txt`, y se
# corre con un shell y no reimplementado: la línea que hashea el segundo
# `sha256sum` lleva la ruta, y el orden lo pone el glob del shell.
HUELLA_MSU = "sha256sum rom/build/release/abl-*.pcm | sha256sum"


def fallar(mensaje):
    sys.exit("entregar: " + mensaje)


def git(*args):
    return subprocess.run(["git", "-C", RAIZ] + list(args), check=True,
                          capture_output=True, text=True).stdout


def huella_msu():
    salida = subprocess.run(["sh", "-c", HUELLA_MSU], cwd=RAIZ, check=True,
                            capture_output=True, text=True).stdout
    return salida.split()[0]


def huella_msu_entregada():
    """La huella que dice `/shared/msu/LEEME.txt`: la línea de 64 hexa que va
    después del comando. None si no hay LEEME o no se reconoce."""
    try:
        with open(os.path.join(MSU, "LEEME.txt"), encoding="utf-8") as f:
            texto = f.read()
    except FileNotFoundError:
        return None
    m = re.search(re.escape(HUELLA_MSU) + r"\s+([0-9a-f]{64})", texto)
    return m.group(1) if m else None


def actualizar_msu(commit, fecha, huella):
    """Copia los `abl-N.pcm` a /shared/msu/, borra los que ya no salen, y le
    cambia al LEEME el commit y la huella. No toca el `abl.sfc` ni la partida
    que taro tenga ahí. El `abl.msu` no va acá: se copia con cada build, ver
    `MSU_DEL_BUILD`."""
    os.makedirs(MSU, exist_ok=True)
    nuevas = {os.path.basename(p) for p in glob.glob(os.path.join(RELEASE, "abl-*.pcm"))}
    for vieja in glob.glob(os.path.join(MSU, "abl-*.pcm")):
        if os.path.basename(vieja) not in nuevas:
            os.remove(vieja)
    for nombre in sorted(nuevas):
        shutil.copyfile(os.path.join(RELEASE, nombre), os.path.join(MSU, nombre))
    leeme = os.path.join(MSU, "LEEME.txt")
    with open(leeme, encoding="utf-8") as f:
        texto = f.read()
    texto = re.sub(r"en el commit\s+[0-9a-f]{7,40} \(\d{4}-\d{2}-\d{2}\)",
                   "en el commit\n%s (%s)" % (commit, fecha), texto)
    texto = re.sub(r"(" + re.escape(HUELLA_MSU) + r"\s+)[0-9a-f]{64}",
                   lambda m: m.group(1) + huella, texto)
    with open(leeme, "w", encoding="utf-8") as f:
        f.write(texto)


LEEME = """\
abl.sfc del commit {commit} ({fecha}): {asunto}

{que_mirar}

abl.sfc.dbg: los nombres de las rutinas para el depurador de Mesen2, que lo
carga solo si está al lado de la ROM. rom/src/ es el fuente exacto de este
commit, y es lo que hace que Mesen2 muestre el fuente al lado del
desensamblado (Ctrl+Q) abriendo la ROM desde acá: lo busca subiendo de carpeta
desde el .dbg. No van mapdata.inc ni musicdata.inc, que genera el conversor y
pesan ~15 MB: las líneas que caen en ellos se ven sólo desensambladas. Ver
docs/snes/emulators.md.

Para el MSU-1: las pistas están en /shared/msu/ y no acá, porque pesan medio
giga. Se escucha copiando ahí este abl.sfc y el abl.sfc.dbg (y el rom/ si se
quiere el fuente). {msu}

abl.msu: los fondos de batalla que la ROM lee por el MSU-1 cuando está. Es de
este build y ya se copió a /shared/msu/; con otro abl.sfc hay que llevar el
suyo, y si no se lleva anda igual, con los fondos de la ROM.
"""


def renglones(texto):
    """El texto de qué mirar llega en una sola línea desde la terminal: se
    reparte en renglones como el resto del LEEME, respetando los párrafos que
    traiga."""
    return "\n\n".join(textwrap.fill(p.strip(), 76)
                       for p in texto.strip().split("\n\n"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("que_mirar", help="qué cambió y qué mirar: va al LEEME")
    parser.add_argument("--actualizar-msu", action="store_true",
                        help="copiar las pistas a /shared/msu/ si cambiaron")
    args = parser.parse_args()

    if not os.path.isdir(SHARED):
        fallar("no existe %s: esto corre adentro del contenedor, donde /shared "
               "es la carpeta que taro ve desde el host." % SHARED)

    sucio = git("status", "--porcelain", "--", *LO_QUE_ENTRA)
    if sucio:
        fallar("hay cambios sin commitear en lo que entra en la ROM, y el build "
               "se nombra por commit:\n" + sucio)

    for nombre in ("abl.sfc", "abl.sfc.dbg", MSU_DEL_BUILD):
        if not os.path.isfile(os.path.join(RELEASE, nombre)):
            fallar("falta rom/build/release/%s: `just build release`." % nombre)

    commit = git("rev-parse", "--short", "HEAD").strip()
    asunto = git("log", "-1", "--format=%s").strip()
    hoy = datetime.date.today().isoformat()

    # Si el commit ya tiene su directorio, aunque sea de otro día, se usa ése.
    existentes = [n for n in os.listdir(BUILDS)
                  if BUILD.match(n) and os.path.isdir(os.path.join(BUILDS, n))] \
        if os.path.isdir(BUILDS) else []
    mismos = [n for n in existentes if BUILD.match(n).group(2) == commit]
    destino = os.path.join(BUILDS, mismos[0] if mismos else "%s-%s" % (hoy, commit))
    if mismos:
        print("entregar: %s ya existía; se pisa sólo %s"
              % (destino, ", ".join(LO_NUESTRO)))
    os.makedirs(destino, exist_ok=True)

    for nombre in ("abl.sfc", "abl.sfc.dbg", MSU_DEL_BUILD):
        shutil.copyfile(os.path.join(RELEASE, nombre), os.path.join(destino, nombre))
    os.makedirs(MSU, exist_ok=True)
    shutil.copyfile(os.path.join(RELEASE, MSU_DEL_BUILD),
                    os.path.join(MSU, MSU_DEL_BUILD))

    # `git archive` y no una copia del árbol: así es el del commit, sin nada
    # sin trackear que haya quedado en rom/src/.
    shutil.rmtree(os.path.join(destino, "rom"), ignore_errors=True)
    archivo = subprocess.run(["git", "-C", RAIZ, "archive", "HEAD", "rom/src"],
                             check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", destino], input=archivo, check=True)

    huella = huella_msu()
    entregada = huella_msu_entregada()
    aviso = None
    if huella == entregada:
        msu = "Las pistas no cambiaron."
    elif args.actualizar_msu:
        actualizar_msu(commit, hoy, huella)
        msu = "Las pistas cambiaron y se actualizaron con este build."
    else:
        msu = ("OJO: las pistas de /shared/msu/ no son las de este build; "
               "suenan las viejas.")
        aviso = ("\nentregar: ATENCIÓN, las pistas de MSU-1 cambiaron y "
                 "/shared/msu/ tiene las viejas.\n"
                 "  huella de este build:   %s\n  huella de /shared/msu/: %s\n"
                 "  Para copiarlas (medio giga): just entregar \"...\" "
                 "--actualizar-msu" % (huella, entregada))

    with open(os.path.join(destino, "LEEME.txt"), "w", encoding="utf-8") as f:
        f.write(LEEME.format(commit=commit, fecha=hoy, asunto=asunto,
                             que_mirar=renglones(args.que_mirar), msu=msu))
    # Se dejan dos: éste y el más nuevo de los demás, que sirve para comparar
    # con lo que se venía jugando; los de más atrás se rearman desde su
    # commit. Éste se queda siempre, aunque su nombre lleve una fecha vieja
    # porque el commit ya se había entregado otro día. Entre los del mismo día
    # desempata la fecha de modificación.
    otros = sorted((n for n in os.listdir(BUILDS)
                    if BUILD.match(n) and os.path.isdir(os.path.join(BUILDS, n))
                    and n != os.path.basename(destino)),
                   key=lambda n: (BUILD.match(n).group(1),
                                  os.path.getmtime(os.path.join(BUILDS, n))))
    for viejo in otros[:-1]:
        print("entregar: se borra %s" % os.path.join(BUILDS, viejo))
        shutil.rmtree(os.path.join(BUILDS, viejo))

    print("entregar: %s" % destino)
    # Al final, para que sea lo último que se lee.
    if aviso:
        print(aviso, file=sys.stderr)


if __name__ == "__main__":
    main()
