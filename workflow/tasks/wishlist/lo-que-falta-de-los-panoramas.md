---
name: "Lo que falta de los panoramas"
description: "Lo que el camino de cada panorama no cubre: ChangePBG a otra imagen, los de un evento común, el cielo en modo 1 y el grano del aplanado"
type: feature
---

# Qué

Lo que quedó afuera de `testing/los-panoramas.md`, para cualquier juego:

* **Un `ChangePBG` que nombra otra imagen.** Hoy cambia los bucles y la
  velocidad y deja la imagen. Haría falta convertir cada imagen que las
  páginas del mapa nombran y subir sus tiles a mitad del mapa, con la
  pantalla apagada un cuadro. En A Blurred Line no hay ninguno: los siete del
  Hover-Tram nombran la del mapa.
* **Un `ChangePBG` en un evento común, o en un mapa sin panorama.** Wally
  mira las páginas del mapa para saber qué ejes van a hacer bucle; uno de un
  evento común no lo ve, y un mapa sin panorama no tiene capa que cambiar.
* **El cielo en modo 1.** A 2 bits un cielo del RTP queda en cuatro colores
  (el 105, el atardecer). El estudio dejó otro camino sin probar: el
  panorama en BG2 a 4 bits y lo de encima en BG3 a 2, con la prioridad de
  BG3 arriba de todo y la ventana de mensajes tapándola por HDMA.
* **El grano del aplanado.** Lo de encima va de a celdas de 8x8: una celda
  que cubre menos de la mitad queda detrás del héroe. Lo de encima con
  objetos, en las celdas del borde, lo arreglaría si sobran paletas.

# Por qué

Ninguno frena a A Blurred Line hoy: son los bordes de la regla, y lo que
otro juego va a pedir.
