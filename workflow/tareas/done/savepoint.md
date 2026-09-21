### El save point: anima quieto y guarda a disco

**La animación de un evento quieto no tiene dónde guardar su contador.** Los que
caminan lo llevan adentro de su ranura de ruta; los quietos no tienen ranura, la
fila del NPC no tiene un byte libre —el +11 es el alto del salto— y la BSS está
en 7680 de 7680. Así que la columna sale del reloj del juego, igual que el agua:
`vueltas` dividido por `ANIM_CONTINUA[velocidad]`, y el mismo ciclo de cuatro
pasos con el tercero repitiendo el primero. Lo que se pierde es la fase —en RM2k
cada personaje arranca su contador cuando el mapa lo crea— y está declarado en
`assets/LIMITACIONES.md`.

Lo que **sí** cuesta VRAM es que deje de compartir tiles: un evento quieto usa la
ranura de su (CharSet, índice, pose), y para animarse necesita las doce poses
suyas, como los que caminan. Son doce tiles de sprite por evento. El mapa 52
tiene **treinta** eventos así y pedía 572 tiles de sprite contra los 384 que
entran, así que hay un tope: **un mapa con más de cuatro no anima ninguno**, y no
unos sí y otros no —dos fuentes iguales, una moviéndose y la otra congelada, se
ve peor que las dos quietas—. Medido sobre los 328 mapas del juego: 312 tienen
cuatro o menos.

La fase se midió como la del agua, y la cobra
`escena 8 "9 55" 0 down "20 30 40 50"`: la celda (9,55) lo deja en pantalla
y los cuatro cuadros caen en tres columnas distintas del ciclo. Sin el `inc` que
corrige la fase se queda una columna atrás, que son 76 pixeles.

**Guardar abre la pantalla de ranuras, como en RM2k.** `OpenSaveMenu` apila
la misma pantalla que "Resume the Story" abre desde el título, en modo guardar
—"Save in which slot?", que es `save_game_message` del LDB—, con el cursor en
la ranura que la partida está usando, que es el `latest_slot` de
`Scene_File::Start` sin fechas. A elige y guarda ahí, B vuelve sin guardar, y
no se pregunta si la ranura estaba ocupada porque `Scene_Save::Action` tampoco
pregunta. El cartucho declara SRAM con batería en la cabecera —`$02` y 8 KB— y
en el EverDrive eso es una pila de verdad.

Tres cosas de cómo está hecho:

* **Bloquea adentro del intérprete y no cuesta ningún tick.** La pantalla corre
  su propio lazo de cuadros desde `op_save`, igual que desde el título, y
  `vueltas` no avanza mientras se ve. Es lo que hace RM2k: la escena apilada
  para el reloj del mapa, y la página sigue por el comando siguiente cuando se
  cierra. Por eso `OP_SAVE` ocupa su byte y no cuesta un cuadro, y
  después de cerrar el mapa sigue por el tick que le tocaba, tarde lo que tarde
  el jugador.
* **Al cerrar se repone sólo lo que la pantalla pisó**, y no el mapa entero:
  `volver_al_mapa` vuelve a subir el banco de tiles de BG1 con `load_map`, tiñe
  de nuevo, y repone los registros con `ppu_init`. Llamar a `cargar_mapa`
  reiniciaría los eventos, las rutas y las poses, que es justo lo que tiene que
  sobrevivir. Para que eso alcance, **la pantalla vive en `$2000`..`$3600` de
  la VRAM**, que es la intersección del banco de BG1 de los cuatro repartos de
  `vram_layout`, y el conversor lo comprueba. Con las direcciones del menú del
  título —`$4400` y `$5000`— pisaba los sprites del reparto ancho, que arrancan
  en `$4000`: 267 pixeles en el héroe del mapa 73, sólo con el grupo 11, porque
  el líder del grupo 10 cae en el bloque 0 y se salvaba. Cuesta dos cuadros
  negros al volver: 30 KB de DMA no entran en un vblank.
* **La pantalla va en toda ROM**, con título o sin él. Con sus tiles emitidos
  sólo bajo `--con-titulo`, abrirla desde una ROM sin título era un DMA de cero
  bytes —o sea de 65536— que llenaba la VRAM de basura.

**Cada ranura con partida muestra lo que muestra RM2k**, que es lo que
`Window_SaveFile::Refresh` dibuja por archivo: el nombre del archivo, el
nombre del líder, el nivel —`lvl_short` en el color 1 del sistema y el número
a dos cifras, "L 20" con Kersh, que sale de su `initial_level`— y las
**caras** del grupo, del FaceSet y a 48x48, que es por lo que la fila mide 48
pixeles.

Está mirado contra el juego original corriendo la misma escena en EasyRPG, y
no sólo leído del código. Lo que difiere a propósito: los puntos de vida
no van, porque este port no los tiene; entran tres caras y no cuatro, y
pegadas en vez de a 56 px, porque en 256 de ancho no hay más lugar sin comerse
el borde que un televisor de tubo no muestra; y el cursor es un ">" sobre
fondo negro y no la caja del skin, que es como estaba el menú desde el título.

Cómo está hecho, porque no es una variante más de la fila pre-renderizada: el
grupo lo dice **la partida guardada** —los seis bytes de `grupo` en la SRAM de
la ranura, en `PARTIDA_GRUPO`— y por cada actor que pueda entrar al grupo con
los mapas de la ROM, `miembros_posibles`, el conversor emite un bloque de 36
celdas con su cara. `ranura_pintar` sube la fila y
después, si tiene partida, `ranura_grupo_pintar` lee el grupo de la SRAM y
escribe encima los rectángulos que le tocan, con `ranura_rect_subir`: un DMA
por fila de celdas, con el puntero de origen que el DMA mismo va dejando donde
terminó. **El nombre del líder y su nivel no son bloques**: los compone
`ranura_texto_escribir` de a una letra por celda, ver "Lo que depende del
actor se compone con glifos" más abajo. A dónde va cada cara y cada nombre lo
dicen dos tablas del conversor —`ranura_cara_vram`, de a cuatro por ranura
para no multiplicar por tres, y
`ranura_nombre_vram`—, como `ranura_vram` para las filas. Cada cara lleva su
paleta, reducida a 15 colores con `reducir` como la imagen del título, en las
paletas 1 a 7 de BG2; en RM2k el índice 0 del FaceSet es transparente, igual
que en un CharSet, y `ABLFaces` lo usa: dibujado opaco cada cara era un
cuadrado rojo. Un actor sin cara —DummyHero— no dibuja nada, como `DrawFace`
con un nombre vacío.

La variante llena no la puede ver la tanda —la SRAM del emulador arranca
virgen— y la cobra `test_la_pantalla_de_ranuras_muestra_el_grupo_guardado`,
que guarda con Talan y DummyHero en el grupo, reinicia, entra por "Resume the
Story" y compara la pantalla **pixel por pixel** contra `titulo.render_ranuras`
con ese grupo, con el cursor en la primera fila y después sobre la de Talan,
que es lo que la repinta en el vblank. Contra una referencia sin grupo o con
Kersh son unos 400 pixeles, así que el cero no es vacío.

Lo cobran `test_guardar_pantalla` y `test_guardar_vuelve`, de
`pruebas/rpgmaker/test_tanda_pantallas.py`, en seis cuadros y todos en cero: la pantalla
al abrirse y con el cursor dos ranuras abajo, y el mapa de vuelta después de
cancelar y después de elegir, en dos ticks. Los toques de adentro de la
pantalla van con `toques_hardware`,
que cuenta cuadros de hardware desde el arranque: un toque por tick no puede
caer donde no hay ticks. Y lo que queda en la SRAM lo mira
`pruebas/rpgmaker/test_guardar.py`, que ahora **atraviesa la pantalla** —baja el cursor
y aprieta A— en vez de escribir `ranura` a mano; `menu_abierto` es el byte que
la ROM le deja para saber cuándo, porque esperar por ticks ahí se colgaría.

Qué se guarda lo dice **una tabla y nada más**, `partida_tabla` en `main.s`:
pares de (dirección en la WRAM, cuántos bytes). Guardar y cargar la recorren los
dos, así que no se pueden ir uno del otro, y agregar un campo es una línea. Hoy
son 154 bytes: dónde está el héroe, en qué mapa, el grupo, el tinte, el
cronómetro, el oro y los 128 bytes de switches.

La copia va **por DMA en las dos direcciones**, y lo que lo hace posible es la
ventana de la WRAM: el bus B no llega a la SRAM, pero sí a `WMDATA`, así que la
SRAM va del lado del bus A y la WRAM del otro. Guardar es un DMA de B a A —el
bit 7 de DMAP— y cargar el mismo al revés.

Dos detalles que costaron su rato y que están anotados donde muerden, arriba de
`SRAM_MAGIA` en `main.s`: que la partida viva en `$0100` y no en `$0000`, y que
la magia se compare contra inmediatos.

Una ranura vale si tiene la magia `ABLS` y la suma de sus bytes cuadra. Las dos
cosas hacen falta: la SRAM sin escribir trae basura —snes9x la llena de $60— y
una ROM de prueba que la tomara por buena cargaría una partida inventada.

**Lo que se escribe no lo puede cubrir la tanda de pixeles**, porque guardar
no cambia un pixel. Lo cubre `pruebas/rpgmaker/test_guardar.py`, que hace lo único que
prueba algo: va a otro mapa, prende un switch, guarda, **resetea la consola de
verdad** y mira dónde arranca. La SRAM sobrevive al reset y la WRAM no, así que
si la partida vuelve es porque salió del cartucho. Con `guardar_partida`
cortado a propósito, tres de sus cuatro pruebas dan rojo.
