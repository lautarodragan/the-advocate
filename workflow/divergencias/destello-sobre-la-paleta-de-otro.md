# Qué

En la consola `FlashSprite` es **un tinte de CGRAM**: `paint_flash` sube la
paleta entera del personaje, así que tiñe todo lo que la comparta —otro evento
con el mismo gráfico, uno al que le prestaron la paleta, o el héroe cuando el
líder es además NPC del mapa—. **RM2k lo aplica sobre la imagen del sprite**, o
sea sobre uno solo. Son dos cosas distintas.

# Medido

Antes de aceptarlo, el 2026-09-13, el compilador se defendía no compilando
ninguna página que destellara a un evento que compartiera gráfico: costaba
**51 páginas**, y una de ellas —el `EV0027` del mapa 20— es la cinemática del
Bum, sin la cual el jugador aparece invisible en Rat Tracks B2 y el juego no se
puede seguir. Ahí el que destella es `BumGuardingEntrance` y el que se tiñe con
él es `InnBum`: los dos son `Future3:1`.

Lo cubre el caso `destello-compartido` de la tanda, sobre el mapa 6, donde el
blanco es el Kersh NPC y quien se tiñe con él es el héroe. Fuera de ése, ningún
caso tiene un segundo sprite visible compartiendo la paleta del que destella.

# Cómo se ve hoy

Lo cuida `rom/pruebas/herramientas/test_destello_paleta.py`, que exige que nadie
comparta la paleta de un líder posible, porque ahí el que filtra es el héroe,
que está en pantalla todo el tiempo. **Protege al líder y no al que destella**:
el blanco se decide corriendo y el héroe es el único que se puede saber al
convertir, así que un destello sobre otro evento filtraría igual.

# Cuándo deja de alcanzar

Cuando el que comparte la paleta esté al lado del que destella y se note. La
salida general sería darle una paleta propia al que destella, en caliente, y
hoy no hay ninguna libre: los mapas apretados ya piden más de las ocho.
