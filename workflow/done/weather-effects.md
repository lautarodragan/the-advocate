### La lluvia

`WeatherEffects` dibuja la lluvia —la apertura llueve, primero débil y después
media—. Compila a `OP_WEATHER` con el tipo y la
fuerza, y la regla es la de `Game_Screen::UpdateRain`: cada gota vive doce
cuadros, baja cuatro pixeles y corre uno a la izquierda por cuadro, y una
apagada nace con un diez por ciento de chance en un lugar al azar.

**La lluvia va pegada al mapa**, como en RM2k, y no a la pantalla. En RPG_RT las
gotas viven en
una superficie del tamaño de la pantalla que da la vuelta en los bordes, y se
pega corrida por el paneo, que es lo que la cámara se movió
(`Weather::DrawParticles`). Acá la superficie es de 256x256: la x y la y de
cada gota son bytes, el paso de cada cuadro da la vuelta solo, y para
dibujarlas se les resta el scroll del mapa —la sacudida incluida— en ocho
bits. De la superficie se ven 224 de las 256 líneas, así que en pantalla la
densidad es la de antes.

Cuatro cosas son nuestras y están declaradas:

* **La densidad, no la cantidad.** RM2k tiene 20, 60 y 100 gotas en 320x240;
  acá son 15, 45 y 75 en 256x224.
* **El azar es un xorshift propio**, sembrado cada vez que el clima cambia e
  igual de los dos lados: el de RM2k no se puede reproducir.
* **El diez por ciento es 26 de 256**, 10,2%: con `% 100` la ROM pagaba el
  divisor por cada gota apagada de cada cuadro.
* **La gota es una raya de 4x16** con la pendiente de la de 6x24 de RM2k, en
  tres grises opacos según le quede de vida, que es donde RM2k la desvanece
  con transparencia.

En la consola cada gota son dos objetos de 8x8 con prioridad 2, al final de la
OAM: pasan por delante de la capa de encima, cualquier personaje las tapa —en la
consola gana el objeto de índice más bajo—, y la ventana de mensaje las tapa con
la misma máscara que a los eventos "above". El tono de pantalla las tiñe, como a
todo, porque sus colores van en una paleta de personaje. Sus seis tiles y sus
tres colores se reservan como los dígitos del cronómetro, y **un mapa sin lugar
en las paletas de sprite no dibuja lluvia**: la ROM lleva `M_LLUVIA_BASE` en
cero, y quién lo decide es el conversor al repartir las paletas de sprite, en
`gotas_de_lluvia`. En la demo pasa en
los mapas 2, 8 y 10, que no la usan. La nieve, la niebla y la arena no se
dibujan y apagan la lluvia; el clima no viaja en la partida.

En OAM las gotas no pasan por `emit_object`: la X queda siempre entre 0 y
255, así que `lluvia_oam` las escribe directo, y de la Y descarta lo que cae
entre 224 y 247 —de 248 en adelante el PPU lo dibuja asomando por arriba—.
Con eso y el direccionamiento largo en vez de la ventana de WMADD, la lluvia
fuerte bajó de 58 a 24 líneas en `lluvia_tick` y `build_oam` de 130 a 84.

Lo cobran `pan-lluvia` y `sacudir-lluvia` en la tanda, que corren la cámara con
lluvia fuerte por la página de prueba —un `WeatherEffects` en su archivo de
`pruebas/casos/`—: en la apertura la cámara no se mueve, así que ella sola no
mira el scroll de las gotas. Y
`apertura` compara con lluvia, que es lo que exige que el caso cuente los ticks
hasta el final: la lluvia no se aquieta nunca, así que cortar cuando la escena
se ve quieta deja las gotas de veintipico de ticks antes.
