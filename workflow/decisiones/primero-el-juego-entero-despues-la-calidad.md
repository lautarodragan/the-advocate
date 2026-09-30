# Qué

**Hasta que el juego entero se pueda jugar, destrabar una parte vale más que
su calidad.** Cuando algo no entra —un tema, un efecto, un gráfico—, entra con
la calidad que haga falta en la ROM, y con la más alta que se pueda en el
`.msu`. Y **romper la compatibilidad de las partidas guardadas nunca es un
problema**: entre cartuchos no se conserva nada.

# Por qué

De taro, el 2026-09-30, sobre la música de la radio de las páginas de tropa
(sus tres temas en el paquete de la pelea le bajan la tasa al tema de
batalla) y el común 35 (`ResetAfterBattles`), cuyas variables no tenían
ranura en la partida: *"Cuando terminemos de implementar todo y el juego
entero sea jugable podemos ajustar tuercas en lo que a calidad de gráficos y
sonidos respecta"*, y *"siempre aceptaré romper saves"*.

# Cómo se aplica

- Si la forma simple de destrabar algo es bajarle la calidad a otra cosa —el
  tema de batalla, por ejemplo—, se hace así, y la calidad queda anotada como
  deuda en la tarea.
- Si separar la calidad de la ROM y la del `.msu` es igual de barato, se
  separan: la ROM baja, el `.msu` no.
- Un cambio en el formato de la partida no se evita ni se versiona: se hace.

No contradice que taro elija de oído cuando la calidad es la pregunta —como
con los efectos del `.msu`—: eso sigue valiendo cuando no traba nada.
