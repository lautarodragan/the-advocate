# Qué

Hornear en un ChipSet propio a los sprites que son **decoración**: el público
del Auditorio, que no se mueve nunca, y los que estén en la misma.

# Status

**Hecho el 2026-09-21 en el mapa 18**, el Auditorio. Sus 31 eventos de público
son tiles de la capa alta del ChipSet 54, que es propio del mapa; el fork está
en `juego/mapas/Map0018.json` y la receta de la imagen en
`juego/chipsets/0054.json`.

Lo que ganó, del conversor, contra los mismos números de antes:

    cartucho   personajes   paletas de sprite   tiles de sprite   NPCs
    abl           8 -> 6         8 -> 6            219 -> 158     36 -> 5
    juego         9 -> 7         8 -> 6            219 -> 158     36 -> 5
    pruebas      10 -> 8         8 -> 5            211 -> 147     36 -> 5

Y lo que costó, que es fondo y sobraba: **21 -> 64 colores de los 103** que el
mapa tiene, con **cero fusionados**; 54 -> 102 tiles de fondo y 29 -> 43
bloques, o sea 224 B más de tabla de bloques.

**El mapa se dibuja igual**: el render de RM2k con y sin el fork sale con cero
pixeles de diferencia en los 320x240.

# Por qué

La otra de las dos ideas para **cuando haga falta apretar assets**. Un sprite
que no se mueve nunca paga banco de sprites, paleta de sprite y ranuras de OAM
por nada: horneado en el ChipSet es tile de fondo, que es lo que ya se comparte
entre los mapas del mismo chipset.

En el 18 el límite no era teórico: el mapa estaba **clavado en 8 de 8 paletas
de sprite**, que es donde
`workflow/decisiones/un-grafico-que-no-entra-no-se-dibuja.md` empieza a decidir
por nosotros. Y decidía: las cinco goldens `18-*` cambiaron al hornear porque
**ahora se dibuja gente que el port venía descartando**.

# Cuál es "decoración", medido

La pregunta que quedaba anotada —"un evento que nunca camina pero al que se le
puede hablar sigue siendo un evento"— se contestó mirando el mapa:

* **cero comandos en todas sus páginas**: no hablan, no disparan nada;
* **una sola página**, así que su dibujo no depende de ningún switch;
* **`animation_type` 0** en las 41 páginas del mapa: ninguno anima;
* y **nadie los nombra**: las dos páginas de `EV0036` —259 comandos, la
  cinemática entera— le hablan a los eventos 1, 9, 16 y 37 y a nadie más.

De los 36 eventos dibujados del mapa quedan cinco como sprite: el `Director`,
que está en el escenario; `Dessen` y los dos `WalkIn*`, que la cinemática
mueve; y `EV0019`, la mujer de pelo amarillo, que es la única cuyo sprite se
sale de su celda —dos pixeles, medidos— y que se deja como está para que el
fork no tome ninguna decisión sobre cómo se ve.

# El orden de dibujo, que es lo que había que confirmar

Horneado, el público pasa de ordenarse por Y con el héroe a ser fondo: nadie
puede volver a taparlo. Vale porque **en el mapa 18 no se camina libremente**:
`EV0036` es autostart y no suelta al jugador. Las tres posiciones del héroe
salen de la cinemática, y las tres están en el pasillo del medio —x 7 a 12,
que el público no ocupa— o detrás de todos:

* entra en **(9,14)** desde el mapa 17 y desde el 83, que son los únicos
  teleports que apuntan acá;
* camina a **(6,12)**, la última fila, al lado de `Dessen`;
* los dos `WalkIn*` suben por las columnas 8 y 10, que también son pasillo.

O sea que ningún sprite queda nunca en una celda por delante de un horneado, y
la única celda pisable desde la que se los vería por detrás —la fila 7— no la
pisa nadie en el juego.

# Las ranuras, y cómo se eligieron

Son **cuatro combinaciones de (gráfico, dirección)** para los 31 eventos, y
dos tiles altos cada una —la cabeza cae en la celda de adelante y el cuerpo en
la suya—, así que **ocho tiles**:

    gráfico             dirección   eventos   cabeza   cuerpo
    Future1  índice 0       0          3       120      121
    Future2  índice 6       0          9       122      123
    Future2  índice 2       3          5       124      125
    Future3  índice 5       0         14       126      127

El ChipSet 25, del que sale el 54, tiene **arte en 143 de sus 144 ranuras
altas**, así que no hay ninguna vacía: lo que hace que pisar ocho sea gratis es
que **el 54 es privado del mapa 18**, y el 18 dibuja diez —la 0 y las 105 a
119—. Las otras 134 son de uso libre, y lo cuida
`test_fork_no_pisa_una_ranura_que_su_mapa_dibuja_con_el_arte_de_antes`.

**La pasabilidad la escribe el ChipSet, y es lo que sostiene el horneado**: el
tile del cuerpo va en 0 —un evento en la capa del héroe es una pared, y de
tiles sueltos la celda quedaría abierta y el jugador caminaría por encima de la
gente— y el de la cabeza en 15, que es lo que la celda de adelante daba. Las
celdas abiertas del mapa pasan de 197 a 166: las 31, ninguna más.

# Lo que hizo falta del mecanismo

El fork de mapas ya existía —lo estrenó el mapa 11, ver
`el-mapa-11-se-rediseno.md`— y no se tocó. Lo único que se le agregó es una
tercera operación a la receta de la imagen del ChipSet, `desde_charset`, que es
la primera que **trae pixeles de afuera del ChipSet**.

Su trampa, que no se ve venir: **los dos PNG son indexados y sus índices no
quieren decir lo mismo.** Copiar los bytes de un CharSet adentro de un ChipSet
da un sprite pintado con la paleta del ChipSet. Se copia por color, y el que
falta se agrega en un índice que el ChipSet no use; el índice 0 queda afuera de
la búsqueda en las dos puntas porque es el color key.

# Cómo se reproduce

Los scripts descartables quedaron en `/extras/scratch/fork-auditorio/`:
`inventario.py` lista los 37 eventos con sus páginas, `celdas.py` dice qué tile
tiene cada celda con gente y la de arriba, `ev36c.py` dice a quién nombra la
cinemática, `pasa.py` dibuja la pasabilidad, `ranuras.py` cuenta las ranuras
altas libres, `generar.py` arma los tres archivos del fork y `render18.py` saca
el render de RM2k con y sin fork, que `comparar.py` compara pixel por pixel.

Las capturas están en `/extras/capturas/auditorio/`.
