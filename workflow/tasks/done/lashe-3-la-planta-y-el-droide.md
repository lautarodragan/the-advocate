---
name: "Lashe 3: la planta de reciclaje y el droide"
description: "Stash, los pisos que se rompen y AG7-17 entrando al grupo: 57, 59 a 63 y 164"
type: feature
assignee: taro
---

# Qué

El hito 3 de `lashe-city-hasta-la-carrera.md` —el contexto y lo medido están
ahí—. Va después del 1 y en paralelo con el 2.

El camino del droide desde el Sector 32 (48): la puerta de Stash, la escena del
"bald man" que te robó en el Hover-Tram (o del guardia sobornado), la planta de
reciclaje con los pisos que se rompen, el Motivator Chip, el túnel de vuelta, y
**AG7-17 entrando al grupo**, con su tutorial. Prende el 150, que es lo que la
rama sin compañero necesita para irse.

Mapas: **57** (Stash's Emporium), **59** (Outside Recycling Plant), **60**,
**61** y **62** (los tres pisos), **63** (el túnel) y **164** (el tutorial del
droide, fuera del subárbol de Lashe City).

# Status

2026-09-27, en `testing/`: hecho en la rama del agente, con `main` mergeado
encima del hito 2. Lo que queda es de taro: jugarlo y mirar las fotos sin
golden de `pruebas/snapshots/playthrough/lashe-planta*/`.

# Lo hecho

**Los siete mapas en `MAPAS_DEL_JUEGO`**, y compilan **todas** sus páginas
disparables, las dos de la puerta de Stash del 48 incluidas.

**`RecallToLocation` y `MemorizeLocation` son un solo opcode, `OP_LOCATION`**:
el mismo lugar leído o escrito en tres variables, con un bit de modo. **En las
variables el mapa es el id de RM2k** —cualquier otra página las lee y las
escribe: los pisos cargan el 61 con un `ControlVars`—, así que la ROM lo
traduce con `mapa_rm2k`, una tabla de ids por índice que el conversor emite en
RODATA (no cuesta banco 0). Saltar es un `Teleport` con el destino leído al
correr, y la página sigue en el mapa nuevo; a un mapa que el cartucho no lleva
**no salta y sigue**. Al recordar, el refresco de cada una de las tres
escrituras va en un bit del modo.

**El tema recordado es `OP_MEMORIZED_BGM`**, con el índice en `TEMA_RECORDADO`
($7E7940, RAM lejana; el reset lo pone en $FF). Poner el que ya suena no lo
reinicia, como `BgmPlay` con el mismo nombre. No viaja en la partida: los dos
comandos van siempre en la misma página automática.

Los cuerpos viven en el banco 1 (`rom/src/lugar_y_tema_recordados.s`) y en el
0 queda sólo la entrada, como `op_heal`: en el 0 quedaban 342 bytes y los dos
pedían casi 200. Leen y escriben las variables directo en la RAM lejana.

**La ranura de variable pasó a ocho bits.** El juego nombra 127 variables y
estos dos comandos suman nueve (127-129, 158-160, 169-171): la ranura, que
llevaba el bit de `VAR_REFRESCO` arriba, no entraba en siete. El bit se mudó al
byte de banderas de cada opcode que escribe (la operación de OP_VAR, las
banderas de OP_KEY, el modo de OP_TERRAIN y de OP_LOCATION). Commit aparte, con
la tanda en verde antes de las variables nuevas. **Una partida guardada con un
build anterior no carga** (la firma de la partida cambia con las ranuras).

El conversor anota como destino del audio el mapa de un `RecallToLocation`
cuando la página lo puso con una constante (los pisos); la vuelta del tutorial
salta a lo que recordó otra página y no se anota.

**AG7-17 entra al grupo sin habilidades**: el evento común 37 (`UpdateAG7
Skills`) es paralelo y la ROM no corre comunes paralelos. Es del hito 4, que
tiene que darle las suyas sin que pueda perderlas.

# Lo medido

Todo sobre `release`. **Banco 0**: 342 libres antes del hito, 244 con el hito
solo, **219 con el hito 2 mergeado**. **Banco 1**: el último símbolo pasó de
$01:F874 (~1,9 KB libres) a $01:FEA4 (**~350 B libres**, con los dos hitos); la
mayor parte son las páginas de tropa y las tablas de los encuentros de la
planta, no el código. **Cartucho**: 2.964.854 B usados, 70,7% de 4 MB (último
banco $61). BSS y ZEROPAGE sin cambio.

**Páginas**: con `medir.py` del plan, 176 de 176 disparables de 48, 57, 59-63 y
164 compilan (antes 120).

**Cuadros perdidos**, caminando 1200 cuadros de a 50 ida y vuelta (el método de
`done/el-mapa-11-se-rediseno.md`), con los encuentros apagados: 0 en 57, 59,
60, 61, 62 y 63. Los únicos 10 salieron de pisar sin querer el pozo de (15,7)
del 62 y caer al 60: un teletransporte.

**Audio.** `fm2bar_gs` (Stash) entra con todas sus notas y su pista de MSU-1
salió sola. Contra `main` con el hito 2, par por par (programa, tema) del
banco compartido: bajan dos, 0,1 kHz (SPACE79 en `TF3_1_awe` y
`T_ProjectJustice_DiscLoad`). `just techos` rehecho: ningún tema recorta.

# Pruebas

`pruebas/rpgmaker/test_lugar_recordado.py`, con cinco casos nuevos:
`lugar-caer` (el piso del 60 entero: cae al 61 en la celda de las variables y
la página sigue allá), `lugar-ida-y-vuelta`, `lugar-ausente` (el mapa 999: no
salta), `tema-recordado` y `tema-recordado-el-mismo` (no reinicia).
`test_cores.py` suma `lugar-ida-y-vuelta`.

`pruebas/abl/test_recorrido_lashe_planta_golden.py`, sobre `release`:

* `test_stash_la_planta_y_ag7_en_el_grupo`: sin compañero y con el ídolo
  robado (71). Del 48 a lo de Stash, la escena, la planta, **cuatro caídas**
  —de la entrada del 60 no se sube sin caer—, el chip, el túnel, la página 5
  de Stash, lo recordado (48, 3, 39), el tutorial y la vuelta: grupo
  [Talan, AG7], el 150, sin el chip, el tema de antes sonando.
* `test_la_escena_de_stash_con_el_soborno`: la página 4 (29), hasta la planta.
* `test_con_arden_la_puerta_de_stash_esta_cerrada`.

Los encuentros al azar de la planta **se apagan** en la prueba (`ENC_BASE` en
cero al llegar a cada mapa): ninguna prueba del recorrido camina por un área
con encuentros, y las peleas de la planta son del hito 4.

Fotos sin golden:

    lashe-planta          la escena de Stash, afuera de la planta, el piso 1,
                          caído en el piso 0, el cuarto del chip, el túnel, el
                          tutorial, AG7 en el grupo
    lashe-planta-soborno  la escena de Stash con el soborno
    lashe-planta-arden    "Looks like they're closed"

Lo que **no** cubren: las páginas 1 y 3 de Stash (créditos y nada), los otros
pozos del 62 y del 60 —el de (12,10) del 62 encadena dos caídas por una página
automática del 60—, y las peleas de la planta.

# Qué tiene que mirar taro jugando

La escena de Stash según cómo haya ido el tram, los pisos que se rompen y la
caída (el héroe tiene que bajar desde arriba atravesando, no aparecer), el
chip, el túnel, el tutorial —el droide en la pantalla negra y el tema que
sigue sin cortarse— y AG7 en el grupo desde el menú de pausa. Pelear en la
planta con AG7: sin habilidades, y los enemigos sin la suya. Y que una partida
de un build anterior no carga.

# Probado

taro, el 2026-09-27, en la SNES con el FX Pak: anduvo todo, incluido el camino
de vender el Idol, sobornar al guardia y llevar a AG7; la carrera sin lag ni
bugs (el compañero al volante, también). Queda aparte el héroe negro después
de cambiar de gráfico en el mismo mapa (HQ de Lazer Teeth, Boss Wick).
