# Qué

Las páginas de evento de las tropas corren con las condiciones y los comandos
de RM2k que las peleas de `release` piden —ver
`tasks/*/eventos-de-tropa-de-release.md`—, con tres diferencias.

**Los HP de un actor, sólo si pelea.** La condición `actor_hp` de una página se
cumple sólo si el actor está en el grupo: sus HP y su máximo están a mano en
la pelea, y los de uno que no pelea no —el máximo sale de su nivel—. En RM2k
`Game_Actors::GetActor` contesta por cualquiera. Las dos páginas del juego que
lo miran son de la pelea de los Lazer Teeth (tropa 86) y miran a Talan; si
Talan no estuviera en esa pelea, en RM2k podrían salir sus mensajes y acá no.
Ver `ba_pag_cumple` y `batalla.PaginaDeTropa`.

**`ShakeScreen` sacude la escena y no el texto.** Es lo que corre
`Spriteset_Battle` con `GetShakeOffsetX` —el fondo y los battlers—; las
ventanas de RM2k quedan quietas y acá los renglones, que son BG2, también. Lo
que la ROM no hace es sacudir a los que se dibujan como objetos: en la pelea
no hay ninguno.

**Un `PlaySound` de página se pide y no suena**, salvo que su efecto esté en
`SE_DE_TROPA_AL_PAQUETE` (tools/audio/snes_music.py): el paquete de la pelea
no tiene lugar sin bajarle la tasa al tema de batalla, y ésa es la regla de
taro para los efectos. Hoy es uno solo, el `Thunder9` del despegue de la pelea
de los agentes; los números están al lado de la lista.

# Cómo reproducirlo

`rom/pruebas/rpgmaker/test_eventos_de_tropa.py`, con los casos `pelea-86` y
`pelea-102`.
