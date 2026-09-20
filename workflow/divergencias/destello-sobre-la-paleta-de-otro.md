# Qué

En la consola `FlashSprite` es **un tinte de CGRAM**: `pintar_flash` sube la
paleta entera del personaje, así que tiñe todo lo que la comparta. **RM2k lo
aplica sobre la imagen del sprite**, o sea sobre uno solo. Son dos cosas
distintas.

# Medido

Ningún caso de la tanda lo ve, porque ninguno tiene un segundo sprite visible
compartiendo la paleta del que destella.

# Cómo se ve hoy

Lo cuida `pruebas/herramientas/test_destello_paleta.py`, que exige que nadie
comparta la paleta de un líder posible. **Protege al líder y no al que
destella**: el blanco se decide corriendo y el héroe es el único que se puede
saber al convertir, así que un destello sobre otro evento filtraría igual.
