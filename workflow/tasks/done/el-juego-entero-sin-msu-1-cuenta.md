---
name: "Plan: el juego entero sin MSU-1, la cuenta"
description: "Lo que faltó en la cuenta de Lechuza (las animaciones de la pelea, sus efectos) y lo que la achica (animaciones sólo en el .msu, fondos de mapa cuantizados por ChipSet, LZ2 donde va crudo, la música más chica): ¿entra en 4 MB, o en 8?"
type: research
assignee: taro
---

De taro, el 2026-10-01, después de leer
`docs/research/2026-10-01-los-mapas-por-el-msu-1.md`. La decisión nueva:
`decisiones/el-juego-se-juega-sin-msu-1.md`. Lo que quiere saber es si,
pasando a 8 MB si hace falta, comprimiendo lo que se pueda y bajando la
calidad de algo en la ROM sin MSU-1, el juego entero entra.

# Lo que salió (Tucu-tucu)

El estudio es `docs/research/2026-10-01-el-juego-entero-sin-msu-1.md`.
Lo corto:

* **En 4 MB no entra con ningún recorte**; en **8 MB (ExHiROM) entra sin
  bajar la calidad de nada**, con ~850 KB de margen, usando sólo LZ2 donde
  va crudo, DTE en los mensajes y saltos en las secuencias.
* **La cuenta de Lechuza contaba las muestras de más**: compilado el audio
  del juego entero de una vez, son 1.052 KB y no 2.120. El juego entero
  como hoy son ~7.450 KB.
* **Lo que faltaba**: ~630 KB (imágenes de `ShowPicture` ~430 estimado,
  los cinco mapas ~105, los efectos de las animaciones de la pelea 92). Las
  84 animaciones que sólo usa la pelea son 462 KB y van al `.msu`. Los
  panoramas quedan afuera.
* **Fondos por ChipSet**: −840 KB, 94 mapas pierden colores y casi no se
  ve. Queda de reserva para cuando 8 MB apriete.
* Recomienda **revisar `decisiones/el-cartucho-se-queda-en-4-mb.md`**.

Para taro:

* Las capturas de los fondos están en
  `/shared/capturas/2026-10-01-fondos-por-chipset/`: hoy a la izquierda,
  por ChipSet a la derecha, los diez mapas que más colores pierden.
* Decidir si pasar a 8 MB, y si la pelea sin MSU-1 lleva los sonidos de
  sus animaciones (92 KB).

No toca el juego: `just pruebas`, 923 en verde. **Al mergear no hay nada
que instalar.** Los scripts descartables quedaron en el scratchpad, en
`tucu-tucu/`, y reusan las corridas de `lechuza/`.
