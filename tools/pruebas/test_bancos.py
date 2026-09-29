"""El acomodo de bancos, que hace el conversor y ya no el ensamblador.

Lo que estas pruebas cuidan no es que el relleno sea lindo sino que respete
lo que declara el conversor: un bloque que cruza de banco se sube por DMA
leyendo la WRAM de la mitad para adelante, y eso no falla al ensamblar, falla
dibujando basura. Desde el 2026-09-27 el acomodo es first-fit decreasing y la
ROM ya no sale byte por byte igual a la del acomodo secuencial, así que la
red grande son las goldens y la tanda; ésta es la chica, y sirve para que un
error se vea acá y no en una captura.
"""

import re

import pytest

from ensamblado import bancos


def resolver(texto, tmp_path, segundo=None):
    """Corre el acomodo sobre uno o dos archivos y devuelve lo que quedó."""
    rutas = []
    for i, cuerpo in enumerate([texto] + ([segundo] if segundo else [])):
        ruta = tmp_path / ("parte%d.inc" % i)
        ruta.write_text(cuerpo)
        rutas.append(str(ruta))
    cuenta = bancos.resolver(rutas)
    return [open(r).read() for r in rutas], cuenta


B2, B3 = '.segment "BANK02"', '.segment "BANK03"'


def bytes_(n):
    return "    .byte " + ",".join(["$00"] * n) + "\n"


def test_rodata_pasa_a_ser_el_banco_donde_arrancan_los_datos(tmp_path):
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque 16\n' + bytes_(1), tmp_path)
    assert B2 in salida and "RODATA" not in salida and ".bloque" not in salida
    assert cuenta == (1, 1)


def test_un_bloque_que_no_entra_va_a_otro_banco(tmp_path):
    """El caso que da sentido a todo: un bloque no queda nunca partido. El
    grande va primero, y los 16 bytes ya no entran en los 8 que deja."""
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque 16\nchico:\n' + bytes_(16)
        + ".bloque %d\netiqueta:\n" % (bancos.BANCO - 8)
        + bytes_(8) * ((bancos.BANCO - 8) // 8), tmp_path)
    b2, b3 = salida.split(B3)
    assert "etiqueta:" in b2 and "chico:" in b3
    assert cuenta == (2, 2)


def test_first_fit_decreasing_llena_los_huecos(tmp_path):
    """Lo que ganó el acomodo: en orden, dos bloques de más de medio banco y
    dos de menos piden tres bancos, porque el segundo grande salta y el último
    chico ya no entra detrás del primero. De mayor a menor, dos."""
    mitad = bancos.BANCO // 2
    texto = '.segment "RODATA"\n'
    for nombre, n in (("a", mitad + 16), ("b", mitad + 16),
                      ("c", mitad - 16), ("d", mitad - 16)):
        texto += ".bloque %d\n%s:\n" % (n, nombre) + bytes_(16) * (n // 16)
    (salida,), cuenta = resolver(texto, tmp_path)
    assert cuenta == (4, 2)
    b2, b3 = salida.split(B3)
    assert "a:" in b2 and "c:" in b2 and "b:" in b3 and "d:" in b3


def test_uno_de_mas_de_un_banco_arranca_banco_y_presta_lo_que_sobra(tmp_path):
    """El bloque de textos: arranca en el `$8000` de un banco y sigue en el
    siguiente, como lo decidía el acomodo secuencial —lo recorre código que
    salta de banco a mano—, y lo que sobra en su último banco lo usa otro."""
    texto = ('.segment "RODATA"\n.bloque 64\nchico:\n' + bytes_(16) * 4
             + ".bloque %d\ntextos:\n" % (bancos.BANCO + 32)
             + bytes_(16) * (bancos.BANCO // 16 + 2))
    (salida,), cuenta = resolver(texto, tmp_path)
    assert cuenta == (2, 2)
    b2, b3 = salida.split(B3)
    assert b2.split("\n")[1] == "textos:", "tiene que arrancar el banco"
    assert "chico:" in b3 and b3.index("chico:") > b3.index("$00")


def test_el_borde_justo_entra(tmp_path):
    (salida,), _ = resolver(
        '.segment "RODATA"\n.bloque %d\n' % bancos.BANCO, tmp_path)
    assert B3 not in salida


def test_un_banco_lleno_se_deja_antes_de_la_etiqueta(tmp_path):
    """Una etiqueta en el final de un banco apuntaría afuera de la ROM."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16)
        + "etiqueta:\n" + bytes_(1), tmp_path)
    assert salida.index(B3) < salida.index("etiqueta:")


def test_lo_que_no_entra_se_parte_entre_los_dos_bancos(tmp_path):
    """La grilla de celdas: más grande que un banco, contigua en el archivo."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
        + bytes_(8) + "    .word $1111,$2222,$3333,$4444,$5555,$6666\n",
        tmp_path)
    antes, despues = salida.split(B3)
    assert "$1111, $2222, $3333, $4444" in antes
    assert "$5555, $6666" in despues and "$4444" not in despues


def test_una_palabra_no_se_parte(tmp_path):
    with pytest.raises(ValueError, match="medio de un operando"):
        resolver('.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
                 + bytes_(15) + "    .word $1111,$2222\n", tmp_path)


def test_lo_que_no_es_rodata_no_cuenta(tmp_path):
    """Las tablas del banco 0 van por otra área y no corren a los datos."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16)
        + '.segment "TABLAS"\n' + bytes_(bancos.BANCO - 16)
        + '.segment "RODATA"\n'
        + ".bloque %d\n" % (bancos.BANCO - 16), tmp_path)
    assert B3 not in salida
    assert '.segment "TABLAS"' in salida


def test_los_bancos_van_al_final_del_ultimo_archivo(tmp_path):
    """Para mover las piezas hay que sacarlas de su lugar: `ca65` llena un
    segmento en el orden del texto. Las constantes se quedan donde estaban."""
    (primero, segundo), _ = resolver(
        '.segment "RODATA"\nCONSTANTE = 7\n.bloque 16\nuna:\n' + bytes_(16),
        tmp_path,
        segundo='.segment "RODATA"\n.bloque %d\notra:\n    .res %d\n'
        % ((bancos.BANCO - 8,) * 2))
    assert "BANK" not in primero and "una:" not in primero
    assert "CONSTANTE = 7" in primero
    assert B2 in segundo and B3 in segundo and "una:" in segundo


def test_lo_que_no_entra_en_el_cartucho_lo_dice(tmp_path):
    """Sin esto se queja `ld65`, con un error interno que no dice que falta
    lugar."""
    entran = bancos.BANCOS - bancos.BANCOS_RESERVADOS - bancos.PRIMER_BANCO
    texto = '.segment "RODATA"\n' + "".join(
        ".bloque %d\nb%d:\n    .res %d\n" % (bancos.BANCO, k, bancos.BANCO)
        for k in range(entran + 1))
    with pytest.raises(ValueError, match="piden %d bancos y entran %d"
                       % (entran + 1, entran)):
        resolver(texto, tmp_path)


@pytest.mark.parametrize("linea,bytes_", [
    ("    .byte $00,$01,$02", 3),
    ("    .word $0000,$0001", 4),
    ("    .dword $00000000", 4),
    ("    .byte", 0),
    ("    .byte  ; sin nada", 0),
    ("    .byte $00,$01  ; dos, y una coma en el comentario", 2),
    ("etiqueta:", 0),
    ("CONSTANTE = 7", 0),
    ("; un comentario", 0),
    ("", 0),
    ("    .res 12", 12),
])
def test_cuánto_ocupa_cada_línea(linea, bytes_):
    assert bancos._tamano(linea) == bytes_


def test_alinear_no_se_toca_pero_se_cuenta(tmp_path):
    """`.align` es de `ca65`, así que sobrevive al paso.

    Lo que no puede pasar es que deje de contarse: si su relleno no entra en la
    cuenta, todos los bloques de abajo se acomodan contra un número corrido.
    """
    (salida,), _ = resolver(
        '.segment "RODATA"\n'
        ".bloque %d\ngrande:\n    .res %d\n" % ((bancos.BANCO - 1,) * 2)
        + ".align 2\n.bloque 1\nalineada:\n    .byte $00\n", tmp_path)
    assert ".align 2" in salida
    # Queda un byte, y con la alineación contada la de un byte ya no entra.
    assert salida.index(B3) < salida.index("alineada:")


def test_un_bloque_fuera_de_rodata_no_pasa_callado(tmp_path):
    """El caso que se descubrió al escribir esto: uno en TABLAS.

    Ahí el acomodo no se puede calcular —el área depende del tamaño del código,
    que el conversor no conoce— y tampoco hace falta, porque TABLAS vive entera
    adentro del banco 0. Lo que no puede es colarse: la directiva todavía
    existe para los dos de `rom/src/`, así que el ensamblador lo aceptaría.
    """
    ruta = tmp_path / "tablas.inc"
    ruta.write_text('.segment "TABLAS"\n.bloque 12\n    .byte $00\n')
    with pytest.raises(ValueError, match="sin resolver"):
        bancos.resolver([str(ruta)])


def test_una_tabla_sin_bloque_no_pasa_callada(tmp_path):
    """Una tabla que la ROM lee con `lda f:tabla, x` no puede cruzar de banco:
    el índice lleva la cuenta al `$0000` del banco siguiente, que en LoROM no
    es ROM. Sin `.bloque`, el acomodo la parte donde caiga el final del banco,
    y si cae entre dos palabras no hay nada que se queje: la ROM lee basura
    para las últimas entradas. Así estuvieron `actor_hpmax`, `actor_spmax` y
    una treintena más hasta el 2026-09-27, y lo destapó una variante de
    `release` con más mapas, donde el corte cayó en el medio de una palabra.

    Por eso el acomodo se niega **siempre**, no sólo el día que el corte cae
    encima: el error es latente, y depende de cuánto haya antes en RODATA.
    """
    with pytest.raises(ValueError, match="tabla_suelta"):
        resolver('.segment "RODATA"\n.bloque 4\ncubierta:\n'
                 "    .word $1111,$2222\n"
                 "tabla_suelta:\n    .word $3333,$4444\n", tmp_path)


def test_un_bloque_cubre_las_tablas_que_entran_en_él(tmp_path):
    """Un `.bloque` que mide varias tablas las cubre a todas, y una etiqueta
    de un solo byte no se puede partir."""
    resolver('.segment "RODATA"\n.bloque 8\nuna:\n    .word 1,2\n'
             "otra:\n    .word 3,4\nsuelta:\n    .byte 5\n", tmp_path)


def test_lo_que_cruza_a_proposito_se_declara(tmp_path):
    """El stream de la música, el driver y las muestras del SPC700 sí cruzan:
    los recorre código que salta de banco a mano. `.cruza` lo dice."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
        + ".cruza\nstream:\n" + bytes_(16) + bytes_(16), tmp_path)
    antes, despues = salida.split(B3)
    assert "stream:" in antes and ".cruza" not in salida
    # Y la continuación va primera en el banco siguiente, que es donde la
    # buscan `spc_block` y `advance`: en su `$8000`.
    assert despues.split("\n")[1].startswith("    .byte")


def test_lo_que_cruza_y_entra_entero_llena_un_hueco(tmp_path):
    """Un stream chico no hace falta partirlo: si entra en lo que sobra de un
    banco, va ahí entero, y la cadena de lo que cruza no crece."""
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque %d\ngrande:\n    .res %d\n'
        % ((bancos.BANCO - 64,) * 2)
        + ".bloque %d\notro:\n    .res %d\n" % ((bancos.BANCO - 16,) * 2)
        + ".cruza\nstream:\n" + bytes_(16) * 3, tmp_path)
    assert cuenta == (3, 2)
    b2, b3 = salida.split(B3)
    assert "otro:" in b2 and "grande:" in b3 and "stream:" in b3


def test_el_mapa_de_memoria_pone_cada_banco_en_su_lugar():
    """Lo que ata el `.cfg` al reparto: `BANKnn` arranca en `$nn:8000`."""
    texto = bancos.cfg()
    assert "BANK01: start = $018000, size = $8000, fill = yes;" in texto
    assert "BANK7D: start = $7D8000, size = $8000, fill = yes;" in texto
    assert "BANK7E" not in texto, "los bancos $7E y $7F son la WRAM"
    assert "FAR:      load = BANK01" in texto
    assert "%s: load = %s" % ((bancos.segmento_de(bancos.PRIMER_BANCO),) * 2) in texto
    # El archivo tiene que medir 4 MB: 126 bancos de datos, más el 0 partido
    # en tres áreas, más los dos reservados.
    tamanos = [int(t, 16) for t in re.findall(r"size = \$([0-9A-F]+), fill", texto)]
    assert sum(tamanos) == 4 * 1024 * 1024
