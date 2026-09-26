# Qué

**Los eventos translúcidos van horneados**: la mezcla del "Trans" de una
página —`translucent`, que en RM2k dibuja el evento con opacidad 160 de 255—
se calcula en el conversor contra la capa de abajo de su celda y queda en el
gráfico. Ni color math, ni trama, ni paletas aparte. Cómo, en
`decorar_translucido` (`tools/rpgmaker/rm2k.py`); la excepción, el save point,
que va opaco, en `SIN_TRAMA`, al lado.

# Por qué

Los otros dos caminos no alcanzan en este juego:

* **El color math** es transparencia de verdad, pero la consola la aplica a
  todos los sprites de las paletas 4 a 7 a la vez, así que un mapa con
  translúcidos tendría que dejarles esas cuatro paletas solas. Y probado tiene
  dos costos que taro no aceptó: ver `el-color-math-no-se-usa.md`.
* **La trama** —dejar caer parte de los pixeles, que es lo que hacían los
  juegos de la época— no simula transparencia cuando el fondo es oscuro:
  **los fuegos del mapa 9 están sobre negro casi puro**, y la trama agujerea
  la llama.

Lo que permite hornear es que **las páginas translúcidas del juego son todas
estáticas**: `move_type` 0 y sin ruta propia. Si ni el objeto ni el fondo se
mueven, la mezcla contra la capa de abajo da siempre lo mismo y se puede
calcular una vez, exacta.

Lo que se pierde —nadie se ve por detrás, un tile animado debajo vale para un
dibujo solo— y cuándo deja de alcanzar, en
`divergencias/los-translucidos-quedan-opacos.md`.
