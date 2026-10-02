# Qué

**Los eventos translúcidos no se dibujan con el color math de la consola**,
aunque está implementado y verificado en el tag `color-math`. Van horneados:
ver `los-translucidos-van-horneados.md`.

**Las imágenes translúcidas sí**, desde el 2026-10-02: taro aprobó el
experimento de Gallareta (`testing/varias-imagenes-en-sprites.md`). Las dos
objeciones de abajo no aplican a una imagen en sprites: la mezcla se prende
sólo en las paletas de objeto 4 a 7, así que el héroe y los eventos de las
0 a 3 siguen opacos y animando, y la ventana de mensaje no se mezcla. Lo que
sí cuesta, y está en `divergencias/`: mientras hay una imagen mezclada,
también se mezclan los personajes de las paletas 4 y 5 y la caja de la
animación si cae ahí; y la consola mezcla al 50 % o suma, así que de 25 a
75 % sale al 50 %.

# Por qué

taro lo probó y lo rechazó por dos cosas que no son defectos de la
implementación:

* **El objeto deja de animar.** El translúcido sale de OAM y pasa a ser tiles
  de BG2, que se suben una vez al entrar al mapa, y casi todos los del juego
  animan: son el save point. Revivirlo pide subirle los tiles por DMA con la
  cadencia del evento, que es la máquina de los tiles animados del ChipSet.
* **El héroe se ve a través.** El orden del modo 3 no deja ninguna ranura de
  capa de fondo entre el piso y el héroe, así que la única disponible queda
  por encima. Es lo de FF5, y a taro no le gustó.

# Para quien lo retome

Cómo estaba hecho: `ppu_init` fija `TS` y `CGWSEL` para siempre y **`CGADSUB`
solo** prende y apaga la mezcla, escrito desde `flush_video` con el valor por
mapa que emite el conversor; `render_map.dibujar_translucidos` mete el objeto
adentro de la capa de encima, así que no toca el reparto de VRAM ni el de
CGRAM.

Y dos cosas que valen aunque no entre:

* **La ventana de mensaje también es BG2**, así que la mezcla la vuelve
  semitransparente. Se arregla con un canal de HDMA que pone `CGADSUB` en cero
  en las líneas de la ventana.
* **snes9x redondea distinto que el hardware en la suma de color math**: bsnes
  y mesen-s truncan, que es lo que hace el chip, y snes9x redondea para arriba
  cuando la suma de un canal es impar. Como las goldens son capturas de
  snes9x, un caso con color math va a `rom/pruebas/rpgmaker/test_cores.py`.
