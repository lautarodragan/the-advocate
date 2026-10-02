# Qué

Las páginas de evento de las tropas corren con las condiciones y los comandos
de RM2k que las peleas de `release` piden —ver
`tasks/*/eventos-de-tropa-de-release.md`— y los que usan los sistemas de los
personajes —`tasks/*/eventos-de-tropa-en-la-pelea.md`—, con estas
diferencias.

**Los HP de un actor, sólo si pelea.** La condición `actor_hp` de una página se
cumple sólo si el actor está en el grupo: sus HP y su máximo están a mano en
la pelea, y los de uno que no pelea no —el máximo sale de su nivel—. En RM2k
`Game_Actors::GetActor` contesta por cualquiera. Las dos páginas del juego que
lo miran son de la pelea de los Lazer Teeth (tropa 86) y miran a Talan; si
Talan no estuviera en esa pelea, en RM2k podrían salir sus mensajes y acá no.
Ver `ba_page_met` y `batalla.PaginaDeTropa`.

**`ShakeScreen` sacude la escena y no el texto.** Es lo que corre
`Spriteset_Battle` con `GetShakeOffsetX` —el fondo y los battlers—; las
ventanas de RM2k quedan quietas y acá los renglones, que son BG2, también. Lo
que la ROM no hace es sacudir a los que se dibujan como objetos: en la pelea
no hay ninguno.

**Un `PlaySound` de página se pide y no suena**, salvo que su efecto esté en
`troop_effects_in_package` (`[sound_effects]` del archivo de proyecto): el paquete de la pelea
no tiene lugar sin bajarle la tasa al tema de batalla, y ésa es la regla de
taro para los efectos. Hoy es uno solo, el `Thunder9` del despegue de la pelea
de los agentes; los números están al lado de la lista.

**Un `PlayBGM` de página se hace desde el 2026-09-30, con menos calidad.** Es
el de `Play Radio` (el sistema del 809), que pone uno de tres temas
—`dd2shad2`, `patchb` y el de Ryan Bury—. Van **aparte** en el paquete de la
pelea: no suben con el tema de batalla, los sube su `PlayBGM` solos con los
efectos del paquete, así que el tema de batalla no baja. Lo que baja es lo
que comparten con otros temas: con tres temas más, al banco de muestras le
quedan menos entradas para copias, y varias muestras de otros temas quedan a
la tasa del peor paquete. Lo midió la tarea
`tasks/*/el-comun-35-y-la-radio.md`. Con el MSU-1 los tres tienen su pista y
suenan enteros.

**El que entra al grupo en la pelea toma el lugar del que salió.** En RM2k
`RemoveActor` saca al actor de la lista del grupo y `AddActor` pone al nuevo
al final, así que la ventana de la pelea se reacomoda. Acá los lugares de la
pelea no se mueven —todo lo pendiente del turno, las órdenes, el orden y los
blancos, apunta a ellos—: el que sale deja su renglón vacío y el que entra va
al primero vacío. Con las invocaciones del juego, que sacan a Lerle y ponen a
la invocación, se ve como la invocación en el renglón de Lerle y no abajo de
todo, y le toca dar órdenes en ese orden. El grupo de la partida sí queda en
el orden de RM2k: `party` lo cambian los mismos opcodes del mapa. Ver
`ba_sync_in`.

Y de ahí sale otra, más chica: **un enemigo que ya había elegido al que salió
le pega al que entró en su lugar**, si entró en ese mismo turno. En RM2k el
blanco ya no existe y la acción se reapunta al primero del grupo. Medido en la
prueba de la invocación: el Gigante le pega al droide en el turno en que
entra, que en RM2k habría sido a Kersh. El modelo hace lo mismo que la
consola, así que la prueba no lo cobra.

**Lo que las páginas cambian del grupo lo cambian en la partida, entre
tramo y tramo.** La consola guarda los HP de la pelea en `BA_ONE`; antes de
cada tramo de página los copia a `FAR_HP` y después los trae de vuelta, así
los opcodes del mapa —`ChangeHP`, `FullHeal`, el `ChangeCondition` que
revive, el `ControlVars` con los HP de un actor— andan sin saber que hay una
pelea. En RM2k no hay copia porque hay un solo `Game_Actor`. La diferencia no
se ve salvo en el `CheckGameOver` del mapa, que la consola no hace: en la
pelea no hace falta, porque perder es de la pelea.

# Cómo reproducirlo

`pruebas/rpgmaker/test_eventos_de_tropa.py` de ABL, con los casos `pelea-86` y
`pelea-102`; y `pruebas/rpgmaker/test_sistemas_de_tropa.py` de ABL, con
`pelea-invocacion` y `pelea-radio`.
