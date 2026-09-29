# Lo que la ROM dibuja, congelado

Una captura del emulador por cuadro que la tanda mira, y los `plan-*.txt` que
dicen cuántos ticks correr en cada mapa y dirección. Las compara
`tanda.golden`, y las usan los `test_*_golden.py` de `pruebas/`.

**No son lo que calculaba una referencia: son lo que la ROM hace.** Hasta el
2026-09-15 se comparaba contra una referencia en Python que hacía lo mismo que
la ROM; ese día se congelaron sus salidas, y el mismo día se cambiaron por
capturas del emulador, por una razón medida.

## Por qué la captura y no la referencia

La referencia no podía modelar **cuál** sprite descarta el PPU cuando un
scanline pasa los 34 tiles de objeto, así que cada caso traía una máscara de
líneas a excluir. Eran 25 máscaras, 1.496 líneas, **382.976 píxeles —6,7
pantallas enteras— que la tanda miraba y descartaba.**

El emulador sí lo sabe, porque lo emula. Medido entonces: dos corridas
completas de la tanda daban las capturas byte por byte iguales, así que
comparar captura contra captura congelada no necesita máscara, y esas 6,7
pantallas pasaron a estar cubiertas. La comparación dejó de ser "cero salvo
estas líneas" y es cero.

Lo único que queda de la referencia son los `plan-*.txt`: los escribió ella, y
por eso no se regeneran —ver `tanda.plan`—.

## Lo que esto cuesta, dicho claro

La tanda compara **la ROM contra sí misma**: detecta cambios, no errores. La
referencia era una segunda implementación y podía discrepar; en los píxeles
donde podían discrepar se sabía que no lo hacían —la tanda estaba en verde—, y
en los que faltaban la única fuente posible era el emulador.

Lo que sostiene la corrección es que taro juegue.

## La regla

Cambiar uno de estos archivos es un **acto deliberado**: va a git, se mira, y
el commit explica por qué el render cambió. Si regenerarlos fuera automático
—o si la tanda lo hiciera sola— dejarían de cumplir ninguna función, que es lo
mismo que pasa con cualquier snapshot testing.

Cuando una da rojo, la captura queda en `pruebas/snapshots/tanda/` con el
mismo nombre, para mirarlas lado a lado.

La clave es el nombre del archivo y no el número de caso, que es posicional y
se correría al insertar uno. Los nombres son únicos entre casos: se comprobó
al congelarlas.
