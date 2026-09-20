# El menú de pausa

**B abre el menú**, que es `Scene_Menu` de RM2k: las cinco
órdenes a la izquierda —`Use Item`, `Tech Skill`, `Equipment`, `Save`, `End
Game`, con los términos del LDB—, el oro abajo y el grupo a la derecha, con la
cara, el nombre, el nivel —el de su `initial_level`, como en las ranuras—, el
estado y los HP. **Hacen algo tres órdenes** —`MENU_HECHAS` en `titulo.py`—:
los ítems, el equipo y guardar. Guardar abre la pantalla de
ranuras en modo guardar y, elija o cancele, vuelve al menú con el cursor en
Save, como `Scene_Save` vuelve a `Scene_Menu`. Las otras dos van en el
color 3 del sistema, el de "no se puede", y A no hace nada con ellas: las
técnicas son un paso que sigue, y terminar el juego pide volver al
título sin reiniciar el SPC700.

**La geometría es nuestra**, no la de RM2k: allá son 320x240 con ventanas, acá
256x224 sobre fondo negro como la pantalla de ranuras, sin el título del
actor, la experiencia ni los SP, y el oro con una cifra por celda y no a los 6
pixeles de la fuente, para que la ROM las escriba de a una sin armar tiles. Es
cosmético y está declarado.

**Los HP de ahora se escriben corriendo.** El bloque de la fila lo dibuja el
conversor una vez, así que cualquier número que llevara adentro sería el del
día que se convirtió: con los HP ahí el menú muestra siempre el máximo del
nivel por más que una pelea los baje, y la comparación de pixeles no lo ve
porque `render_menu` hornea el mismo número. Las tres cifras las escribe
`menu_hp_escribir` desde `FAR_HP`, con las mismas celdas de una por cifra que
el oro y por la misma razón. El "/máximo" de al lado tampoco va horneado desde
el 2026-09-20, pero por otro motivo: cambia de un actor a otro, y todo lo que
cambia con el actor se compone con glifos. Vale para las dos pantallas que
comparten el panel, el menú y la elección de actor, porque las dos pasan por
`menu_grupo_pintar`.

Las cifras caen alineadas con las del oro sin tocar nada: las dos líneas se
dibujan a dos pixeles del borde de arriba de su celda. Y el precio de las
celdas de 8 pixeles es el mismo que ya se paga en el oro. Todo lo demás sale de
`titulo.py`: `render_menu` es la referencia y el conversor emite **los mismos
bloques de celdas**, en el mismo banco de tiles y la misma paleta que la
pantalla de ranuras —las caras son las mismas y guardar se abre desde el menú—.
Las órdenes en gris llevan su propia paleta de BG2: el color 3 es un degradé y
con el del texto sumaban 18 colores, así que a las caras les quedan seis
paletas.

### Lo que depende del actor se compone con glifos

**El nombre, el nivel y los HP máximos no se hornean**: la ROM los escribe de
a una letra por celda con los glifos de `ranura_glifo_celdas`, que son las
mismas dos celdas por carácter que ya usaban el oro y los HP de ahora. Es una
decisión de presupuesto, medida: el banco de tiles de estas dos pantallas es
**uno solo y está deduplicado**, así que lo que se hornea por actor no lo
comparte con nadie, y el texto de un actor eran unos siete tiles marginales
cada uno. Con 12 actores el banco juntaba 446 de los 448 que entran en la
VRAM; con el actor 21 adentro, 462 —por eso sus casos vivían en un cartucho
aparte—; y los 52 actores con cara del juego entero, 751. Componiendo, lo que
se paga una vez son las letras que los nombres usan y lo único que sigue
costando por actor es su cara: los mismos 12 actores juntan 364 tiles, y el 21
entra.

Subir el texto **a demanda** en vez de componerlo se midió y no servía: una
cara residente cuesta 8,4 tiles marginales contra 13 de una ranura a demanda,
y el texto suelto de un actor son de 22 a 39 tiles contra los 7 que cuesta
estando adentro del banco deduplicado.

Lo que se paga, y está declarado como cosmético: las letras compuestas van a 8
pixeles de paso y no a los 6 de la fuente, así que el nombre, el nivel y el
máximo salen un poco más anchos que si se hornearan. Es el mismo precio que ya
pagaban el oro, los HP y las pantallas de ítems, equipo y tienda. Lo que no
depende del actor —"File 1", "- Empty -", el término del nivel, "Normal",
"HP", las órdenes— se sigue horneando con la fuente, y por eso al hacer el
cambio sólo se movieron las dos goldens del menú.

De qué sale cada tira: `ranura_actor_texto` es una fila de 32 bytes ASCII por
actor —el nombre, las dos cifras del nivel y el máximo detrás de su barra—,
emitida por el conversor fuera del banco 0. `ranura_texto_de` arma el puntero
y `ranura_texto_escribir` escribe primero las celdas de arriba de todas las
letras, que van seguidas en la VRAM, y después las de abajo, que es lo mismo
que hace `texto_escribir` en la pantalla de ítems con su propia tabla de
glifos.

**La séptima cara se cuelga de una paleta prestada.** La lista de caras no es la
del grupo sino la de todos los que algún `ChangePartyMembers` de los mapas de la
ROM pueda meter, y con Lashe City entera son ocho: los cuatro de la intro más
Arden, Saldra, el Gang Member de los Rat Tracks y AG7-17. Cada color de la cara
que sobra va al más cercano por luma de la paleta a la que menos colores le
falte, que es lo que `cabe` hace con los sprites y por la misma razón: un
personaje con colores raros es un error visible y un mapa que no entra es un
mapa menos. Se ve en el informe del conversor, que las nombra.

**Cuándo se abre es lo de RM2k.** `Game_Player::Update` anota el pedido
—`menu_calling`— si B se aprieta con el menú permitido, sin mensaje y sin
página corriendo; `UpdateNextMovementAction` lo atiende con el héroe quieto:
con una página corriendo lo tira, con un mensaje lo deja esperando, y si no,
abre el menú antes de mirar la cruceta. O sea que B a mitad de un paso abre el
menú al terminarlo. En la ROM el pedido es el bit 7 de `FAR_ACCESO`,
`pedir_menu` lo anota después de `move_hero` y `move_hero` lo atiende; un
teletransporte lo tira, como `MoveTo`. Y el B que cancela una elección se
consume ahí mismo: en RM2k la ventana procesa la tecla después del héroe, y
acá la elección corre antes que `pedir_menu`. Lo mismo al cerrar el menú y la
pantalla de ranuras: el B que cerró no le llega a nadie más.

`ChangeSaveAccess` y `ChangeMainMenuAccess` **se honran**: dejaron de estar
entre los comandos ignorados, compilan a `OP_ACCESS` y apagan o prenden los
bits 0 y 1 de `FAR_ACCESO`, que viaja en la partida. Guardar prohibido pone
Save en gris; el menú prohibido hace que B no lo pida. El save point no mira
el permiso, como `OpenSaveMenu`.

Mientras el menú se ve **el reloj del juego no corre**, igual que con la
pantalla de ranuras, así que el menú no cuesta ningún tick y el mapa sigue por
el cuadro que le tocaba. Lo cobran `test_menu` y `test_menu_vuelve` de
`pruebas/rpgmaker/test_tanda_pantallas.py`: el menú como se abre, con el cursor movido, y
el mapa después de cerrar. Quien lo compara contra una referencia en Python
—`titulo.render_menu`, que sigue viva— es `pruebas/rpgmaker/test_menu.py`, y es además lo
que mira lo que la tanda no alcanza: el menú con un grupo y oro
puestos, guardar desde el menú, los dos permisos puestos por el bytecode, B a
mitad de un paso, y que los permisos vuelvan de la SRAM.

### La pantalla de ítems

"Use Item" abre `Scene_Item`: arriba la descripción del
ítem marcado y abajo la lista del inventario con cuántos hay de cada uno, en
orden de número como `Game_Party`. En gris va lo que A no usa, como
`Window_Item`. Hoy A usa **los ítems de switch**, que en la demo son uno solo,
la Portable Console: prende su switch —el 710—, gasta uno si tiene usos
—`uses` en cero es infinito—, pide el refresco de páginas y vuelve derecho al
mapa, que es el `PopUntil(Scene::Map)` de RM2k. B vuelve al menú. Las
medicinas quedan en gris: piden HP que cambien, y en los mapas de la demo la
única forma de perderlos es una pelea. El switch 710 dispara el evento común 39, "NewMenuActivated",
que es el menú propio del juego hecho con imágenes: 568 comandos, y los
eventos comunes todavía no corren.

**Las medicinas van en blanco y abren la elección de actor**, que es el panel
del grupo del menú con un cursor al costado —`render_objetivo`—. A no hace
nada, y eso **sí** es deuda: `UseItem` sólo gasta la medicina si sube algo, y
desde que hay peleas los HP bajan, así que usarla tendría algo que hacer.
Hasta el 2026-09-12 no la tenía, porque fuera de batalla nadie bajaba nunca de
los máximos y los tres comandos que tocan HP o estados compilaban a nada; hoy
`FullHeal` y el `ChangeHP` que suma son OP_HEAL y curan de verdad. Libros,
materiales y especiales siguen en gris.

**El texto va de a una letra por celda.** La pantalla tiene su propio banco de
tiles con cada carácter de la fuente en dos celdas, en blanco y en gris —307
tiles, que no dependen de cuántos ítems haya—, y los nombres y las descripciones
van en ASCII en el cartucho; escribir una letra son dos palabras del tilemap. Va
así y no con el texto de cada ítem ya dibujado, como las caras, porque eso crece
con el inventario y con una docena de ítems ya no entra en VRAM. El precio es
que las letras van a 8 pixeles y no a los 6 de la fuente, como las cifras del
oro. En RM2k la lista va en dos columnas de 144 pixeles; acá en una, con la
cantidad a la derecha, y la descripción en dos renglones de 30 letras. Es
cosmético y está declarado.

La descripción se compone en `texto_buf` —el búfer del compositor de
mensajes, libre con el menú abierto— y sube de un DMA al principio de cada
cuadro: escribirla letra por letra al mover el cursor no entraba en el vblank
y el segundo renglón salía cortado. Cuando el cursor se sale de las once
filas, la lista se repinta entera con la pantalla apagada, que es un cuadro
en negro.

Lo cobran `test_items` y `test_items_vuelve` de
`pruebas/rpgmaker/test_tanda_pantallas.py` —la pantalla como se entra, con el cursor
sobre la consola, y el mapa después de usarla— y
`pruebas/rpgmaker/test_items_pantalla.py`, que la compara contra `titulo.render_items`:
la consola prende el 710
y no se gasta, un ítem en gris no hace nada, catorce ítems en once filas se
corren y vuelven, y la lista vacía.

### El equipo, y las pantallas de texto

"Equipment" abre la elección de actor en modo elegir y después `Scene_Equip`
de ése: su nombre, los cuatro parámetros —los del nivel,
mockeado en 1, más lo que suma lo puesto—, y las cinco ranuras. A sobre una
ranura muestra la lista de lo que el actor puede ponerse ahí, con los
parámetros que quedarían; la línea vacía del final es sacarse lo que tiene. Lo
que se saca vuelve al inventario y lo nuevo sale de ahí; un arma a dos manos
saca el escudo y un escudo saca el arma a dos manos, que es
`Game_Actor::ChangeEquipment`. En RM2k la lista y las ranuras se ven a la vez;
acá la lista las reemplaza mientras se elige. Cosmético y declarado.

El equipo es estado: cinco palabras por actor del LDB en `FAR_EQUIPO`, que
arranca con el equipo inicial de la base —un DMA de la tabla del conversor en
el reset— y viaja en la partida. Son 610 bytes más, y con ellos la partida
pasó de los 1024 de la ranura: **la SRAM es de 32 KB** y
las ranuras van cada 2048. `ChangeEquipment` no compila todavía: el juego lo
usa en dos mapas que no están en la demo.

La pantalla de equipo —y la tienda, que sigue— son **pantallas de texto**: no
llevan bloques dibujados sino la fuente de la pantalla de ítems, y se componen
enteras en `texto_buf` —el tilemap de 32 por 28 celdas, 1792 bytes— que sube
de un DMA por cuadro. Componer no tiene apuro, y `pantallas.py` es la
referencia con el mismo compositor de celdas. El DMA va **después** de leer el
control: al revés, sus diez líneas hacían que `read_pad` llegara con la
lectura automática terminada, cada vuelta duraba dos cuadros y la mitad de los
toques se perdía. Lo cobró `equipo`.

Lo cobran `test_equipo` y `test_equipo_vuelve` de
`pruebas/rpgmaker/test_tanda_pantallas.py` —las ranuras de Kersh con su equipo inicial,
la lista del arma con los parámetros que quedarían, y el mapa después de
volver—
y `pruebas/rpgmaker/test_equipo.py`: el equipo inicial en la RAM, equipar desde el
menú, la lanza a dos manos que saca el escudo, la línea vacía, y el equipo en
la partida.
