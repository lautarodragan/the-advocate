# Qué

**La orden 34 de ruta —cambiar el gráfico— se hace también sobre el héroe**,
desde el 2026-09-12.

# Por qué

Lo que la tenía afuera resultó no valer: el gráfico del héroe sale de la tabla
de actores, pero **las doce poses del actor están escritas con la misma forma**
que una entrada de `npc_poses`, así que la ROM le mueve el puntero a
`hero_poses` y `place_hero` ni se entera.

Medido: **+30 páginas** del juego —de 2835 a 2865— y 16 automáticas, y entre
ellas las tres del `EV0047` del mapa 8, con el que taro nunca pudo interactuar,
y la del `Hover-Tram` del mapa 9, que le cambia el gráfico al héroe para
subirlo.

# Lo que cuesta, declarado

* **Mientras el cambio está puesto, el héroe se dibuja con la paleta del
  gráfico nuevo**, que es una de las ocho de sprite del mapa, y no con la
  ranura propia del líder. `hero_cgram` se apaga al cambiar: dejarlo puesto le
  escribiría los quince colores de Talan encima a la paleta del gráfico, porque
  `aplicar_tinte` los sube **en la fila que dice `hero_pal`**.
* **No sobrevive al cambio de mapa.** Las poses viven en el banco de sprites
  del mapa, así que el gráfico de allá no existe acá; la ROM lo repone en
  `elegir_grafico_heroe`. En RM2k `Game_Player` se lo lleva. No se nota: la
  única página del juego que cambia el gráfico del héroe y después salta lo
  vuelve a poner en el comando siguiente al teletransporte.
* **En el cartucho**, medido sobre `abl`: el gráfico al que una ruta cambia al
  héroe entra al banco de sprites del mapa, como el de cualquier evento. En el
  mapa 9 son dos más —`Future2:7` y `Future1:0`— y con ellos un evento dibujado
  con un tile del chipset pasa a colgarse de una paleta ajena. Las animaciones
  de batalla del mapa 9 **no se dibujaban ya antes**: el control sin la 34 da
  el mismo aviso, así que ese mapa llenaba las ocho paletas por su cuenta.

Lo cubren `grafico-heroe` y `heroe-invisible`, uno por rama: el gráfico que se
ve, y el `nobodyhere`, que esconde al héroe como esconde a un evento.

# Y sobre eventos

Sobre eventos la 34 ya se hacía antes, y lo que valió también está medido:
**+25 páginas**. Durante un tiempo ese número vivió debajo de un título que
decía que faltaba.
