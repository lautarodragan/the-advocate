# Lo que la ROM dibuja, congelado

563 capturas del emulador —una por cuadro que la tanda mira— y los 16 planes
que dicen cuántos ticks correr en cada mapa y dirección.

**No son lo que la referencia calcula: son lo que la ROM hace.** Empezaron
siendo lo primero, el 2026-09-15, y se cambiaron el mismo día por una razón
medida.

## Por qué la captura y no la referencia

La referencia no puede modelar **cuál** sprite descarta el PPU cuando un
scanline pasa los 34 tiles de objeto, así que cada caso traía una máscara de
líneas a excluir. Eran 25 máscaras, 1.496 líneas, **382.976 píxeles —6,7
pantallas enteras— que la tanda miraba y descartaba.**

El emulador sí lo sabe, porque lo emula. Medido: dos corridas completas de la
tanda dan las **563 capturas byte por byte iguales**, así que comparar captura
contra captura congelada no necesita máscara, y esas 6,7 pantallas pasan a
estar cubiertas. La comparación deja de ser "cero salvo estas líneas" y es
cero.

## Lo que esto cuesta, dicho claro

La tanda pasa a comparar **la ROM contra sí misma**: detecta cambios, no
errores. Antes la referencia era una segunda implementación y podía discrepar;
hoy, en los píxeles donde podían discrepar ya sabemos que no lo hacen —la tanda
estaba en verde—, y en los que faltaban la única fuente posible era el
emulador.

Lo que sostiene la corrección pasa a ser que taro juegue.

## La regla

Cambiar uno de estos archivos es un **acto deliberado**: va a git, se mira, y
el commit explica por qué el render cambió. Si regenerarlos fuera automático
—o si la tanda lo hiciera sola— dejarían de cumplir ninguna función, que es lo
mismo que pasa con cualquier snapshot testing.

Los nombres son únicos entre casos —comprobado sobre los 1.017 artefactos del
congelado anterior—, así que la clave es el nombre del archivo y no el número
de caso, que es posicional y se correría al insertar uno en `rom/hitos.txt`.
