---
name: "El audio después de Lashe City"
description: "Recuperar la calidad que los paquetes de los mapas nuevos de Lashe City le bajan a los instrumentos sin MSU-1"
type: bug
---

# Qué

El hito 1 de Lashe City (2026-09-27) sumó paquetes de audio nuevos (el 38 y
el 47 con `vswar` y `golden_axe-turtlevillage2`; el `38+cd4`, con tres temas
juntos y 1267 B libres), y sin MSU-1 **bajan 47 pares (tema, instrumento)** y
suben 26; la mediana pasa de 18,9 a 16,5 kHz. `vswar` es el más afectado
(polysynth 21,1 → 12,6, platillos y toms 22 → 14,1); `escape_newyork` vuelve a
perder el polysynth (21,1 → 12,6) que el directorio le había devuelto. Parte es
el paquete de tres temas; parte son copias que la segunda tanda de
`snes_music.copias` dejó de hacer (el banco pasa de 221 a 212 muestras).

Con MSU-1 no se oye (todos los temas tienen pista). Se encara **cuando
terminen los mapas de Lashe City** (cada hito suma paquetes y lo vuelve a
mover), con el mismo método que `testing/el-directorio-de-los-efectos.md`:
medir par por par con `Banco` contra el `main` de antes de los mapas nuevos,
y buscar que ningún instrumento de los temas que ya estaban quede peor.

**Del hito 2 (2026-09-27):** el conversor no sabe que `Kfmus5` sigue sonando
del 41 al 45 (`temas_heredados` corta en el 41), así que esos paquetes no le
reservan lugar. No se escuchó sin MSU-1: mirarlo en la misma pasada.

Y del hito 3 de la carrera: Flash1 en el 13 y Earth4 en el 21 quedaron fuera
de sus paquetes (`SE_DE_RUTA_SIN_PAQUETE`) porque con ellos bajaban dos
golpes unos 7 kHz. Mirar si con lo de acá entran sin costo.

# Status

2026-09-27, en `testing/`: hecho sobre 77996bf (main con Lashe City y la
carrera enteras), en la rama del agente. Para taro: escuchar los wav de
antes, main y después (con su `LEEME.txt`), y jugar la escena del HQ de los
Vipers (38) y la de los guardias (47) sin MSU-1: al prender `vswar` la
escena se congela un momento mientras sube.

# Cómo se midió

Los argumentos que el conversor le pasa a `build_varios` en `release`,
capturados en 93af39f (el main de antes de los mapas nuevos de Lashe City) y
en cada variante, y el reparto de verdad —el `Banco`, con el redondeo a
bloques— rearmado con cada uno. Un par es (tema, programa o golpe), sin la
tecla, que cambia con los temas nuevos. "Baja" es perder más de 0,5 kHz,
como en las tareas anteriores. Contra 93af39f, main baja 48 pares (los 47 del
hito 1 y uno del hito 2).

# Lo que se encontró

**`vswar` no entra con nadie.** Solo, a la tasa que tenía, son 61 KB de los
63 que tiene cada paquete. Antes de Lashe City sonaba sólo como tema de
salida del 26 —solo en la ARAM—; ahora el 38 y el 47 lo prenden y lo juntan
con `golden_axe` (77 KB) y el `38+cd4` con `cd4` (82 KB). Con esos paquetes
**ningún reparto** devuelve lo que había: lo midió un script que suma, grupo
por grupo, cada muestra a la tasa de antes, y los únicos cinco grupos que no
entran son los de `vswar` con otro tema. Y como los temas de afuera
comparten muestras con los de adentro, las copias que los separaban dejaron
de hacerse: eso es el resto de los 48.

Probé antes lo barato, y no alcanza: contar la primera tanda de copias con
los efectos de siempre (47 pares debajo de antes), tolerancias contra el
piso (46 a 53), aislar el racimo de `vswar`, `golden_axe` y `cd4` con copias
(50 y 55: se come el directorio), y hasta la segunda tanda con la tasa de
antes como piso (46):
mientras el racimo no entra, cualquier copia le mueve algo adentro.

**En las páginas nunca suenan juntos.** En el 47 la escena de los guardias
prende `vswar` y en la misma página `golden_axe`. En el 38 se entra al
basural por un `Teleport` (eventos 20 y 21), `vswar` suena en la escena del
HQ vacío, y se sale por otro que antes prende `golden_axe` (evento 26). Así
que `vswar` puede subir solo cuando su `PlayBGM` lo pide, como un tema de
salida; lo que no puede es soltar los efectos, como hace uno de salida: con
`vswar` sonando se abren los cofres del basural (Bow2).

# Lo hecho

**Los temas aparte** (`TEMAS_APARTE` en `tools/audio/snes_music.py`, `vswar`
en el 38 y el 47). Van en una cuarta lista del paquete, detrás de los de
salida; el conversor los reparte **solos con los efectos del paquete** y no
los hereda a los mapas a los que se sale de ahí. En la ROM,
`extra_aparte` (rom/src/paquete_de_audio.s): el `PlayBGM` de uno que no está
sube el tema y los efectos del paquete, suelta los otros temas y deja el
paquete incompleto para que el próximo `PlayBGM` lo complete. `extra_de_salida`
y `extra_aparte` son dos entradas de `extra_en_lista`.

**`Kfmus5` del 41 al 45.** `temas_heredados` llevaba de un mapa con `PlayBGM`
sus temas a todos sus destinos; el 41 y el 40 sólo prenden temas para irse
(`golden_axe`, `tsmedit`), así que `Kfmus5`, que llega al 41 desde el 37, no
seguía. Ahora cada `Teleport` anota con qué tema salta (`Temas.salto`), y en
un mapa cuyos `PlayBGM` son todos de salida cada salto lleva su tema de
salida o lo que entró. El de arranque sigue con la regla de siempre: es el
enrutador, y lo que entra ahí saldría para cualquier lado. Con eso `Kfmus5`
hereda en el 40, 42, 43, 44 y 45, que no cuesta nada —esos paquetes están
vacíos—, **y en el 20**, por el evento 4 del 45, que es el salto al 20 del 19
que vino con la copia y no se puede dar: eso le bajaba dos golpes a
`Lunar_Pyramid` y dos a `wb3shop` de 22 a 14 kHz. Va en
`SALTOS_QUE_NO_SE_DAN` (snes_convert.py), que se lleva también el
`20+tsmedit` de main, falso por lo mismo.

**Flash1 en el 13 y Earth4 en el 21 suenan.** Lo que los dejaba afuera no
era su paquete sino la primera tanda de `copias`, que contaba una entrada del
directorio por cada efecto del cartucho aunque ya compartan lugares: cada
efecto nuevo le sacaba una copia. Ahora cuenta los 92 de cuando taro la
escuchó (`SE_DE_SIEMPRE`), y los dos entran sin mover ningún par (medido a
0,1 kHz). Earth4 dura 1,36 s: en el 21 va entero a 22 kHz con un alias
(`Earth4@entero`), en lo que la música deja libre; el del 3 sigue como
estaba.

**Y el informe del conversor** restaba dos veces lo de más de los efectos
enteros en "sobran" (desde fc78dad las restricciones del banco ya lo traen):
el 49 decía -1573 y le sobraban 1,7 KB.

# Cómo queda

Contra 93af39f, sin MSU-1, `release`:

| | main | después |
|---|---:|---:|
| pares debajo de antes (más de 0,5 kHz) | 48 | 4 |
| de ésos, debajo también de main | — | 0 |
| mediana de los 338 pares | 16,5 | 18,5 (antes 18,9) |

Los 48 vuelven a la tasa de antes (o a 0,1 kHz) salvo cuatro, que quedan
como en main:

    Deflector1  golpe 36    22,0 -> 14,1 -> 14,1  (y el 40: 14,0 -> 14,0 -> 21,9)
    TF3_1_awe   programa 34 15,2 -> 14,0 -> 14,0  (del hito 2)
    vswar       golpe 45    22,0 -> 14,1 -> 14,1
    vswar       golpe 46    22,1 -> 14,1 -> 14,1

Los cuatro los limita el paquete de la pelea o el `18+hzstream`, y la copia
que los separaría le baja una décima a otros; forzar la de `vswar` hace que
el reparto suelte otra de `vswar` (las cuerdas 48). Contra main bajan 26
pares, todos a la tasa de antes o a 0,04 kHz: son los que subieron en main por las
copias que se hicieron distinto. Los temas nuevos (`Kfmus5`, `tsmedit`,
`fm2bar_gs`) quedan a la tasa del SoundFont o a una décima.

# Lo que cuesta

* **Cargar `vswar` al prenderlo**: 71 cuadros congelados en el 38 al empezar
  la escena del HQ vacío (medido con el caso `tema-aparte`), y lo mismo en el
  47. En main esas muestras subían al entrar al mapa, con el paquete.
* **El 21 carga Earth4 entero**: unos 30 KB más al entrar.
* **El 49 con `golden_axe` sonando** —se llega así desde el 36—: el último
  efecto de su lista (Flame3) no entra al lado y espera al `PlayBGM` de la
  carrera, que llega antes de que se use; Evasion2, que suena antes, está.
  Lo mismo en el 64 con el tema de la carrera, que prende el suyo en el
  cuadro 5. Es la decisión `el-tema-que-suena-gana-y-los-efectos-esperan`; el
  conversor lo avisa, y se miró en la ROM recorriendo el cierre de Arden.
* **Banco 0** de `release`: de 344 a 280 B libres. BSS y ZEROPAGE igual.
* **Cartucho**: 228 muestras de música en vez de 220, 454 KB en vez de 426.

# Pruebas

`just techos` rehecho (la mezcla cambió: ningún tema recorta), `just
cartuchos` y `just pruebas` en verde, y el `release` con `SIN_CACHE=1` sale
byte por byte igual. Nuevas:

* `test_el_tema_aparte_sube_con_los_efectos_del_paquete`
  (`pruebas/rpgmaker/test_musica_paquete.py`), con el caso `tema-aparte`: en
  el 38, `golden_axe` y después `vswar`, que tiene que quedar entero con
  Bow2 al lado, sin `golden_axe` y con el paquete incompleto. Con
  `extra_aparte` contestando siempre que no, falla por Bow2.
* `pruebas/herramientas/test_temas_heredados.py`: `Kfmus5` del 41 al 40 y a
  los vidcasts con la forma de esos mapas, el de arranque con la regla de
  siempre, un tema aparte que no sale del mapa, y lo que anota `Temas.salto`.

**Lo que no cubre `just pruebas`**: las tasas par por par las midió un script
aparte contra 93af39f; que los efectos del 49 estén al llegar con
`golden_axe` y que en la escena del HQ `vswar` suene entero con Bow2, una
sonda descartable sobre el recorrido del cierre de Arden; los 71 cuadros,
otra.

# Escuchado

taro, el 2026-09-27, con los wav de antes/main/después: todo bien, nada que
cambiar. Acepta el intercambio de Deflector1 (golpe 36 a 14,1 kHz, el 40 a
21,9) y el programa 34 de TF3_1_awe a 14,0.
