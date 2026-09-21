## `plx`/`ply` pisan N y Z

Hubo cuatro lugares que lo ignoraban** (todos arreglados el 2026-09-12). 

El patrón es siempre el mismo: una rutina deja la
respuesta en las banderas, se restaura el índice con `ply`, y el `beq` que
sigue mira el índice —que nunca es cero— en vez de la respuesta. 

Lo tenían `tema_asegurar` (la música del título), el `ConditionalBranch` por variable
—que entraba **siempre**, medido—, el `IsActorInParty` y el `SetTimer` desde
una variable negativa. 

Los dos últimos **no los mide nadie todavía**: ninguna
página de prueba los emite y ningún caso de la tanda los ejercita, así que el
arreglo es lectura del manual del 65816 y no medición. Si aparece una página
que use `IsActorInParty`, es el primer lugar donde mirar.

## Audio

`pruebas/rpgmaker/test_musica_paquete.py` le pregunta a la ROM si las muestras del
tema que dice estar tocando están de verdad en la ARAM (`FAR_ARAM_DE` contra
`tema_muestras`). 

Lo que **sigue** sin mirar nadie es que lo que sale del DSP
suene a lo que tiene que sonar: eso es oído, y es de taro.
  
## Dalia's Blast de las catacumbas

El `EV0001` paralelo que espera la
A con `KeyInputProc [176,1,0,1,0]`, tiene el mismo patrón que el motor de las
piedras: medido el 2026-09-19, sus 23 páginas (mapas 281 a 283 y 324 a 344)
**compilan**, pero ningún cartucho —ni los de las pruebas ni los de las
demos— lleva esos mapas, así que ninguna prueba mira que cerrar un mensaje
ahí no dispare la ráfaga. Si entran en un cartucho, ésa es la prueba que
falta.

## Un mapa nuevo en `abl` sin su parche

`pruebas/herramientas/test_parches.py` compara los parches —qué color se
fusionó con cuál— contra lo versionado, y lo hace sobre los cartuchos que arma
`just cartuchos`. **La tanda no arma `abl`**, así que lo que ahí se mira es que
ningún mapa versionado haya cambiado de decisión; lo que no puede ver es que
alguien le sume un mapa al ROM jugable y no corra `just parches`, porque
`rom/build/abl` no existe mientras la tanda corre.

Eso lo cobra `just parches-check`, que incluye a `abl` y **sí** falla diciendo
qué mapa entró sin parche. Hacer que lo cobre la tanda cuesta armar `abl` antes
de cada corrida, que hoy son veinte segundos que ninguna prueba usa para nada
más.
