---
name: "Seis habilidades no entran en la pelea"
description: "Con la fuente de ancho variable y espaciado 0, 6 de los 367 nombres de habilidades se pasan de su lugar en la pelea"
type: bug
assignee: taro
---

Lo midió Tordo el 2026-10-03, contando a mano contra el tope de celdas, al
hacer la perilla del espaciado (`workflow/tasks/testing/el-espaciado-entre-letras.md`).
No se corrió en la ROM: falta ver cuáles son, qué se ve, y si el conversor
debería avisarlo.

## Lo que encontró Benteveo, el 2026-10-03

Desde `el-espaciado-sin-tocar-codigo` el conversor las nombra: un WARNING
en `conversor.log`, "skill names in the battle don't fit in 11 cells", con
cada nombre, sus pixeles y lo que se ve.

Lo que más cortaba no eran los pixeles sino las letras: el cartucho guardaba
11 letras de cada nombre, de cuando una letra ocupaba una celda, y eso
cortaba 41 de las habilidades de la pelea de ABL con 0. Ahora guarda 13
—lo que deja el registro de una fila de la capa de texto, `TL_RECORD`, con
las dos columnas de la lista— y quedan 26, todas de catorce letras o más.
Por pixeles no entran 3 con 0 (las seis de Tordo eran sobre las 367 de la
base; el cartucho lleva las que el grupo puede usar) y 27 con 2.

Para que entren todas haría falta más lugar en la fila: correr el guión y
el costo, o un registro más grande, que no entra en la RAM de la capa
(`FAR_TEXT_LAYER` tiene 62 bytes libres y harían falta 432 para ocho
letras más). No se hizo.

## Hecho (Carpintero, 2026-10-04)

Worktree de las herramientas desde `fe0f90ee`; ABL en el clon
`/extras/scratch/carpintero/abl`, rama `texto-de-la-pelea`. Va junto con
`la-lista-de-habilidades-agota-el-pozo`: es la misma capa de texto.

**El cartucho guarda enteros los nombres de habilidades y enemigos**, y la
consola los corta en sus celdas, por pixeles, como ya hacía. Con eso ya no
queda ninguno cortado por letras.

* Los enemigos eran sólo el conversor: la fila de un enemigo tiene lugar de
  sobra en su registro.
* Las habilidades las limitaba el registro de una fila (`TL_RECORD`): la
  lista escribe ahora cada nombre **por referencia** (`TL_BY_REF` en
  `text_layer.s`), un tramo de seis bytes —dónde está el texto en la ROM y
  cuántas letras— sea cual sea el largo, y la composición las lee de ahí
  (`tl_ref_letter`). Sólo lo pide la lista de habilidades; todo lo demás se
  escribe como antes. RAM: 8 bytes más dentro de `FAR_TEXT_LAYER`.
* No hizo falta agrandar el registro (los 432 bytes de Benteveo).

Lo que avisa el conversor con ABL, ahora todo por pixeles:

    espaciado   habilidades   enemigos   ítems
    +0          3             0          0
    +1          14            0          0
    +2          27            3          4

Antes, con +1: 26 habilidades y 14 enemigos. Lo que queda no entra en las
celdas: hacerlo entrar pediría correr el guión y el costo, y eso cambia la
pantalla; no se hizo.

### Verificado

* La tanda de ABL con +1: cambian **cinco goldens, sólo letras de más**
  —"Healing Syringe" entero en `batalla-hab`, `-dos` y `-blanco`, y
  "DecayingShambler" en `msu-datos-rom` y `-msu`—, miradas lado a lado. Se
  repitió hasta que no apareció ninguna roja nueva (dos vueltas): **1045 en
  verde**. `abl.sfc` con +1: `17c71a14…`.
* `cargo test -p rm2k-snes-battle` (la prueba contra el modelo de Python
  corta ahora los dos nombres como él), `just -f tools/justfile test`: 27.
* La lista de Talan con sus 54, con 0, 1 y 2, mirada (`pozo-despues-*.png`).

## Para taro

Una pelea con habilidades de nombre largo y contra un enemigo de nombre
largo. Las goldens lado a lado en
`/shared/capturas/2026-10-04-texto-de-la-pelea/goldens/`.

Al mergear, reinstalar `battle` y `convert`.
