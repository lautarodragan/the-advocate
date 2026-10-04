# Qué

`MessageOptions` sin fondo deja el texto sobre el mapa, con su sombra, en
el lugar donde iría la ventana. En la ROM eso tiene dos diferencias con RM2k,
y las dos salen de lo mismo: la ventana es **BG2**, la misma capa que la de
encima del mapa, y el modo 3 no tiene una tercera.

* **Los personajes pasan por encima del texto.** En RM2k la ventana está
  por encima de todo —`Priority_Window` es 130, y los personajes van de 30
  a 70—. Acá el texto es BG2 con prioridad 1, y el héroe y los eventos son
  objetos con prioridad 2, que en el modo 3 van adelante. Con fondo no se
  nota porque el HDMA esconde los objetos en las líneas de la ventana
  —`mask_*`, en `message_place.s`—; sin fondo no se los puede esconder, porque
  se tienen que ver.
* **La capa de encima del mapa no se ve en las 80 líneas de la ventana.**
  En esas líneas BG2 muestra el tilemap de la ventana —el plano sin marco,
  con las celdas que no son texto en blanco—, así que los techos, las copas
  de los árboles y todo lo que el chipset pone arriba desaparecen de esa
  franja mientras dura el mensaje. La capa de abajo y los personajes sí se
  ven.

Y una que no es de la capa: la flecha roja de "seguir" que RM2k dibuja al pie
de la ventana no está, con fondo ni sin él. Es de antes.

# Medido

Contra el original con Wine, el 2026-10-04, con la página de
`ventana-medio-sin-fondo` puesta en una copia del juego: el texto cae en el
mismo lugar y con la misma sombra, y la única diferencia en pantalla es que
el héroe tapa "Ready". Las capturas, en `/shared/capturas/2026-10-04-ventana-de-mensajes/`.

ABL pide la ventana sin fondo en más de un tercio de sus `MessageOptions`,
casi siempre en cinemáticas sobre la pantalla negra o una imagen, donde
ninguna de las dos se ve.

# Cuándo deja de alcanzar

En un juego que hable sin fondo sobre un mapa con techos o árboles en la
franja de la ventana, o con personajes caminando por ella. Arreglarlo pide
dibujar el texto con otra cosa que BG2: con objetos no entra —una línea de
texto son 30 tiles de ancho y el PPU dibuja 34 por línea entre todos—, y el
modo 3 no tiene más capas.
