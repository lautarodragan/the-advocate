# Los comandos que faltan

> **Escrito el 2026-10-05 sobre `6094a205`**, por Aguará, con ABL en
> `b28864d`. Es una foto: los números son de ese día y este archivo no se
> actualiza. Cómo rehacer cada cuenta está al final, en "Cómo se midió".

La pregunta de taro: "¿qué comandos del sistema de eventos nos falta
implementar?". Medida sobre **el juego entero**: las 5.601 páginas de los
328 mapas, los 60 eventos comunes y las 4.588 páginas de tropa, y no sólo
lo que lleva `release`.

## Resumen

* **En los mapas falta muy poco.** De 5.601 páginas compilan **5.565**. Las
  36 que no compilan las traban **siete cosas**, y cada página tiene una
  sola: no hay ninguna que necesite dos comandos distintos. Ninguna está en
  `release`.
* **Treinta y una de esas 36 son una sola variante**: `ConditionalBranch`
  preguntando hacia dónde mira el héroe, en los cuartos de la simulación
  de Eisen (mapas 281 a 344). Las otras cinco son de a una.
* **Lo que traba el día siguiente es `EraseEvent`**, dos veces: el comienzo
  del trabajo en la cantera (mapa 150, evento 4) y el común que le lleva el
  tiempo (36, `ManageQuarryTimer`). El de la cantera es el único comando
  que falta en todo lo que se alcanza desde la granja: los otros mapas a
  los que salta el 108, el 114, el 117 y el 127 —142, 152, 158, 160— ya
  compilan enteros.
* **En la pelea falta más**, y es más caro: `ChangeMonsterCondition` deja
  afuera 164 páginas de tropa, 140 de ellas junto con `FlashScreen`. Son
  dos habilidades enteras, `Inscribe` de Talan (switch 799) y
  `ControlMachines` (803), y las dos se usan ya en las peleas de `release`.
* **Lo que se pierde sin que se caiga una página** —una llamada a un común
  que no compila, que se saltea— son hoy **47 llamadas**, todas al común
  45 desde los mismos cuartos de la simulación, por un `ControlVars` con
  una constante que no entra en 16 bits.
* **Por dónde empezar**: los dos `EraseEvent` de la cantera, porque son lo
  único entre la granja y el día siguiente; después, en un solo lote, los
  cinco chicos de los mapas; y la pelea —`FlashScreen` en la escena y una
  decisión sobre los estados— como su propio trabajo. Ver
  "Recomendación".

## Cómo se contó

Con una herramienta nueva, `rm2k-snes-events culprits` (ver el README del
crate), que queda: el compilador dice en qué comando se para una página que
no compila, y la herramienta **persigue** cada página —anota el culpable,
lo saca, vuelve a compilar— hasta que compila. Así sale cada comando que la
traba, y de ahí lo que importa para elegir: **cuántas páginas deja afuera
un comando solo**, que son las que entrarían si se hiciera.

Cada página se compila como la compila el cartucho: las de mapa con su
mapa, como `scan`, y con las `TileSubstitution` resueltas como las resuelve
`compile` donde el request las trae; los comunes como cuerpo compartido
—una llamada a otro común es una llamada, no su cuerpo pegado—; las de
tropa con la lista de comandos de la pelea y su ventana. Un comando cuenta
con sus partes: un `else` o un fin de bloque es de su rama, una opción es
de su elección.

Dos cosas que el recuento **no** son comandos y se separaron:

* **Un `Teleport` a un mapa que el cartucho no lleva no compila**, a
  propósito: con `--every-map` todos los mapas están, así que no aparece.
  En `release` traba 18 páginas, y son la frontera: las salidas de la
  granja al día siguiente (108 → 150, 114 → 160, 117 → 142, 127 → 152 y
  158), y las de los mapas de prueba 261 y 269.
* **137 páginas de tropa no tienen ninguna condición**, y en RM2k una página
  así no corre nunca (`AreConditionsMet` devuelve falso). No se pierde
  nada: es un cuerpo vacío copiado en 137 tropas.

## 1. Todos los comandos que usa el juego

Usos y páginas por tipo de página: mapas / comunes / tropas. "Usos que
traban" es cuántos de esos usos dejan su página afuera. Un comando con
"sí" compila en todos sus usos; "en parte" quiere decir que compila con
unos parámetros y no con otros —la variante está en la sección 2—.

Las tropas copian las páginas de sus sistemas en cada tropa: las 4.588
páginas son **295 cuerpos distintos**, así que sus números están inflados
por las copias, no por la variedad.

| código | comando | usos (m / c / t) | páginas (m / c / t) | usos que traban (m / c / t) | ¿compila? |
|---|---|---|---|---|---|
| 10110 | ShowMessage | 6938 / 76 / 6888 | 2140 / 13 / 1742 | 0 / 0 / 0 | sí |
| 10210 | ControlSwitches | 1668 / 182 / 8291 | 1155 / 24 / 4445 | 0 / 0 / 0 | sí |
| 13310 | ConditionalBranchB | 0 / 0 / 7260 | 0 / 0 / 1322 | 0 / 0 / 0 | sí |
| 10330 | ChangePartyMembers | 429 / 40 / 5040 | 125 / 2 / 2520 | 0 / 0 / 0 | sí |
| 10220 | ControlVars | 1688 / 211 / 2451 | 597 / 28 / 1320 | 4 / 6 / 0 | en parte |
| 11410 | Wait | 3562 / 6 / 0 | 813 / 2 / 0 | 0 / 0 / 0 | sí |
| 11550 | PlaySound | 1250 / 26 / 2242 | 819 / 5 / 422 | 0 / 0 / 0 | sí |
| 11330 | MoveEvent | 3444 / 6 / 0 | 1013 / 5 / 0 | 1 / 1 / 0 | en parte |
| 12010 | ConditionalBranch | 1523 / 615 / 0 | 534 / 33 / 0 | 124 / 0 / 0 | en parte |
| 10320 | ChangeItems | 509 / 21 / 706 | 321 / 5 / 310 | 0 / 0 / 0 | sí |
| 10120 | MessageOptions | 1099 / 11 / 0 | 404 / 5 / 0 | 0 / 0 / 0 | sí |
| 10810 | Teleport | 1069 / 10 / 0 | 958 / 5 / 0 | 0 / 0 / 0 | sí |
| 13110 | ChangeMonsterHP | 0 / 0 / 1045 | 0 / 0 / 410 | 0 / 0 / 0 | sí |
| 11040 | FlashScreen | 60 / 0 / 840 | 38 / 0 / 140 | 0 / 0 / 840 | no en la pelea |
| 10440 | ChangeSkills | 20 / 173 / 705 | 12 / 5 / 331 | 0 / 0 / 0 | sí |
| 10460 | ChangeHP | 11 / 1 / 829 | 7 / 1 / 549 | 0 / 0 / 0 | sí |
| 11030 | TintScreen | 826 / 0 / 2 | 400 / 0 / 2 | 0 / 0 / 2 | no en la pelea |
| 11340 | ProceedWithMovement | 818 / 2 / 0 | 370 / 2 / 0 | 0 / 0 / 0 | sí |
| 10860 | ChangeEventLocation | 749 / 0 / 0 | 276 / 0 / 0 | 0 / 0 / 0 | sí |
| 10450 | ChangeEquipment | 34 / 1 / 560 | 9 / 1 / 140 | 0 / 0 / 0 | sí |
| 11510 | PlayBGM | 168 / 0 / 420 | 117 / 0 / 140 | 0 / 0 / 0 | sí |
| 11210 | ShowBattleAnimation | 388 / 0 / 0 | 287 / 0 / 0 | 0 / 0 / 0 | sí |
| 11110 | ShowPicture | 34 / 314 / 0 | 23 / 18 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 12330 | CallEvent | 224 / 114 / 0 | 205 / 7 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 10480 | ChangeCondition | 16 / 0 / 280 | 16 / 0 / 280 | 0 / 0 / 0 | sí (ver 3) |
| 13130 | ChangeMonsterCondition | 0 / 0 / 268 | 0 / 0 / 164 | 0 / 0 / 268 | no |
| 13120 | ChangeMonsterMP | 0 / 0 / 229 | 0 / 0 / 140 | 0 / 0 / 0 | sí |
| 10630 | ChangeSpriteAssociation | 212 / 0 / 0 | 103 / 0 / 0 | 0 / 0 / 0 | sí |
| 11130 | ErasePicture | 23 / 139 / 0 | 17 / 8 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 11060 | PanScreen | 135 / 0 / 0 | 72 / 0 / 0 | 0 / 0 / 0 | sí |
| 10660 | ChangeSystemBGM | 130 / 0 / 0 | 41 / 0 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 11320 | FlashSprite | 113 / 0 / 0 | 92 / 0 / 0 | 0 / 0 / 0 | sí |
| 10140 | ShowChoice | 98 / 1 / 0 | 70 / 1 / 0 | 0 / 0 / 0 | sí |
| 12120 | JumpToLabel | 8 / 86 / 0 | 8 / 3 / 0 | 0 / 0 / 0 | sí |
| 11520 | FadeOutBGM | 81 / 0 / 0 | 62 / 0 / 0 | 0 / 0 / 0 | sí |
| 10490 | FullHeal | 54 / 19 / 0 | 38 / 1 / 0 | 0 / 0 / 0 | sí |
| 11930 | ChangeSaveAccess | 70 / 2 / 0 | 70 / 2 / 0 | 0 / 0 / 0 | sí |
| 10830 | RecallToLocation | 60 / 0 / 0 | 60 / 0 / 0 | 0 / 0 / 0 | sí |
| 11840 | ChangeEscapeAccess | 58 / 0 / 0 | 38 / 0 / 0 | 0 / 0 / 0 | sí |
| 10310 | ChangeGold | 48 / 4 / 0 | 40 / 3 / 0 | 1 / 3 / 0 | en parte |
| 10710 | EnemyEncounter | 51 / 0 / 0 | 40 / 0 / 0 | 0 / 0 / 0 | sí |
| 11610 | KeyInputProc | 32 / 17 / 0 | 31 / 4 / 0 | 0 / 0 / 0 | sí |
| 10720 | OpenShop | 43 / 0 / 0 | 40 / 0 / 0 | 0 / 0 / 0 | sí |
| 10870 | TradeEventLocations | 40 / 0 / 0 | 30 / 0 / 0 | 0 / 0 / 0 | sí |
| 11910 | OpenSaveMenu | 34 / 0 / 0 | 34 / 0 / 0 | 0 / 0 / 0 | sí |
| 11120 | MovePicture | 16 / 17 / 0 | 11 / 2 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 11050 | ShakeScreen | 29 / 0 / 2 | 17 / 0 / 2 | 0 / 0 / 0 | sí |
| 12110 | Label | 8 / 20 / 0 | 8 / 3 / 0 | 0 / 0 / 0 | sí |
| 12410 | Comment | 8 / 15 / 0 | 5 / 7 / 0 | 0 / 0 / 0 | sí |
| 10690 | ChangeScreenTransitions | 20 / 0 / 0 | 15 / 0 / 0 | 1 / 0 / 0 | en parte |
| 11740 | ChangeEncounterSteps | 19 / 0 / 0 | 15 / 0 / 0 | 0 / 0 / 0 | sí |
| 10230 | TimerOperation | 16 / 2 / 0 | 7 / 1 / 0 | 0 / 0 / 0 | sí |
| 10730 | ShowInn | 18 / 0 / 0 | 18 / 0 / 0 | 0 / 0 / 0 | sí |
| 11070 | WeatherEffects | 16 / 2 / 0 | 12 / 1 / 0 | 0 / 0 / 0 | sí |
| 11750 | TileSubstitution | 10 / 0 / 0 | 5 / 0 / 0 | 0 / 0 / 0 | sí |
| 10620 | ChangeHeroTitle | 8 / 0 / 0 | 6 / 0 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 11720 | ChangePBG | 8 / 0 / 0 | 1 / 0 / 0 | 0 / 0 / 0 | sí (ver 3) |
| 10820 | MemorizeLocation | 1 / 6 / 0 | 1 / 3 / 0 | 0 / 0 / 0 | sí |
| 12420 | GameOver | 6 / 0 / 0 | 4 / 0 / 0 | 0 / 0 / 0 | sí |
| 12320 | EraseEvent | 2 / 2 / 0 | 2 / 1 / 0 | 1 / 2 / 0 | en parte |
| 11530 | MemorizeBGM | 4 / 0 / 0 | 4 / 0 / 0 | 0 / 0 / 0 | sí |
| 11540 | PlayMemorizedBGM | 4 / 0 / 0 | 4 / 0 / 0 | 0 / 0 / 0 | sí |
| 11960 | ChangeMainMenuAccess | 4 / 0 / 0 | 4 / 0 / 0 | 0 / 0 / 0 | sí |
| 13150 | ShowHiddenMonster | 0 / 0 / 3 | 0 / 0 / 3 | 0 / 0 / 0 | sí |
| 10150 | InputNumber | 2 / 0 / 0 | 2 / 0 / 0 | 0 / 0 / 0 | sí |
| 12510 | ReturntoTitleScreen | 2 / 0 / 0 | 2 / 0 / 0 | 0 / 0 / 0 | sí |
| 10910 | StoreTerrainID | 1 / 0 / 0 | 1 / 0 / 0 | 0 / 0 / 0 | sí |
| 11350 | HaltAllMovement | 1 / 0 / 0 | 1 / 0 / 0 | 0 / 0 / 0 | sí |
| 10470 | ChangeSP | 0 / 1 / 0 | 0 / 1 / 0 | 0 / 0 / 0 | sí |
| 13410 | TerminateBattle | 0 / 0 / 1 | 0 / 0 / 1 | 0 / 0 / 1 | no |

Son **70 comandos**: de los ~130 de RM2k, el juego no usa el resto
—ningún vehículo, ningún `Loop`, ninguna tienda con ramas—. Que un
comando de los que el compilador no conoce (`Loop`, `ChangeBattleBG`) no
esté en la tabla quiere decir eso: no hay ningún uso que traer.

## 2. Lo que falta, ordenado por páginas que destraba

"Solo" son las páginas que entrarían si se hiciera ése y nada más; "con
otros", las que también necesitan otra cosa; "llamadas" son las llamadas
desde un mapa a un común que se saltean por él. En los mapas y los comunes
no hay ninguna página "con otros": cada una tiene un solo culpable.

| qué falta | tipo | solo | con otros | llamadas | dónde | ¿en el camino? | costo |
|---|---|---|---|---|---|---|---|
| `ChangeMonsterCondition`, poner un estado a un enemigo | tropas | 24 (3 cuerpos) | 140 (3 cuerpos), con `FlashScreen` | — | 164 tropas | **sí**: al menos 66 de esas páginas son de tropas de los encuentros aleatorios de `release` | grande |
| `ConditionalBranch` por la dirección de un personaje (tipo 6) | mapas | 31 | 0 | — | 281–283, 324–340, 342–344: la simulación de Eisen | no | chico |
| `ControlVars` con una constante fuera de 16 bits (999999) | comunes | 1 (común 45) | 0 | **47** | los mismos cuartos de la simulación | no | chico, con una decisión |
| `ChangeGold` por variable | mapas y comunes | 4 (mapa 321; comunes 5, 6, 44) | 0 | — | la forja de Sern; las apuestas | no | chico |
| `EraseEvent` antes de un salto, de verdad | mapas | 1 | 0 | — | 150, la cantera | **sí: el día siguiente** | mediano |
| `EraseEvent` en un común —en RM2k no hace nada— | comunes | 1 (común 36) | 0 | — | el reloj de la cantera | **sí: el día siguiente** | chico |
| `ControlVars` con la posición en pantalla de un evento (tipo 6, campos 4 y 5) | mapas | 1 | 0 | — | 207, Memnosyne's Adobe | no | mediano |
| `ChangeScreenTransitions`, mostrar con corte (19) | mapas | 1 | 0 | — | 302, Screen Adjust | no | chico |
| `MoveEvent` con "alejarse del héroe" (10) | mapas | 1 | 0 | — | 330, Room J | no | chico |
| `TintScreen` en la pelea | tropas | 1 | 1, con `TerminateBattle` | — | 2 tropas | no se sabe | mediano |
| `FlashScreen` en la pelea | tropas | 0 | 140, con `ChangeMonsterCondition` | — | 140 tropas | **sí**, con el de arriba | mediano |
| `TerminateBattle` | tropas | 0 | 1, con `TintScreen` | — | 1 tropa | no se sabe | chico |

El común 32 aparece en el reporte con un `MoveEvent` al evento 2, que sin
mapa no compila; se llama desde el 114 y ahí compila. Se descontó.

### Los de los mapas, uno por uno

**`ConditionalBranch` por dirección** (`[6, personaje, dirección]`). Los 31
son la misma automática copiada en cada cuarto de la simulación de Eisen:
según hacia dónde mira el héroe, corre un evento a la celda de adelante. La
ROM ya tiene `hero_dir` y `OP_IF` ya tiene clases; es una clase más que lee
la dirección del héroe o de un evento. EasyRPG:
`CommandConditionalBranch`, `case 6`. **Chico.**

**`ControlVars` = 999999**, el común 45 (`SimClearTweenRooms`), que esos
mismos cuartos llaman 47 veces: pone en 999999 las coordenadas guardadas
como "ninguna". Las variables de la ROM son de 16 bits y RM2k llega a
±9.999.999. Es chico de hacer —saturar al tope de 16 bits— pero es una
divergencia que hay que declarar, y conviene mirar antes que nadie compare
esas variables contra algo mayor que 32.767. **Chico, con una decisión.**
Sin él y sin el de arriba la simulación no anda; con los dos, entra entera.

**`ChangeGold` por variable** (`[operación, 1, variable]`). El comentario
del compilador dice "sin variables no se puede": es de antes de que las
hubiera. Es un bit más en `OP_GOLD` y el slot de la variable. Lo usan la
forja de Sern —el común 44 y el mapa 321 cambian el oro por los puntos de
forja y lo devuelven— y las apuestas (comunes 5 y 6, que llama el 35).
Ojo: la forja guarda el oro en una variable, y el oro de la ROM es de 24
bits. **Chico.**

**`EraseEvent` de verdad**, el del mapa 150: Sern arranca el trabajo de la
cantera, el héroe salta **dentro del mismo mapa** y el evento se borra.
Hoy compila sólo después de un salto a otro mapa, donde RM2k no borra a
nadie. Para hacerlo hace falta estado en la ROM: un bit por evento que la
carga del mapa limpia y que el refresco de páginas mira para dejarlo sin
página; EasyRPG (`CommandEraseEvent`) además corta en seco una paralela.
No viaja en la partida, que hoy no guarda los eventos
(`divergencias/la-partida-no-guarda-los-eventos.md`). **Mediano.**

**`EraseEvent` en un común**, el 36 (`ManageQuarryTimer`, paralelo con el
switch 450), que cierra el trabajo cuando se acaba el tiempo. En RM2k no
hace nada: `GetThisEventId` da 0 en un común y `CommandEraseEvent` vuelve
sin tocar a nadie. Es sólo del compilador: aceptarlo vacío cuando lo que
se compila es un común. Ojo con el caso pegado: un común llamado desde una
página se compila hoy con el contexto de esa página, y ahí el
`EraseEvent` tampoco tiene que borrar al que llama. **Chico.**

**`ControlVars` con la posición en pantalla** de un evento (`[…, 6,
10005, 4]` y `5`): el mapa 207 pone humo con `ShowPicture` sobre un evento.
La ROM sabe dónde dibuja cada evento, pero la pantalla de la consola no es
la de RM2k, y la imagen tiene que caer en el mismo lugar que el humo
—`ShowPicture` por variables ya compila—: hay que decidir en qué
coordenadas se habla. EasyRPG: `ControlVariables::Event`, `GetScreenX`.
**Mediano.**

**`ChangeScreenTransitions` para mostrar con corte**, el mapa 302. El
compilador ya hace el corte para borrar y deja afuera el de mostrar "porque
ningún mapa lo usaba": éste lo usa. **Chico.**

**`MoveEvent` con "alejarse del héroe"** (10), el mapa 330. "Acercarse"
(9) ya existe; alejarse es el mismo cálculo con la dirección contraria
(`Game_Character::MoveAwayFromCharacter`). **Chico.**

### Los de la pelea

**`ChangeMonsterCondition`** con dos estados: 22, `Control` —"is being
controlled!", restricción 3, cuatro turnos, se suelta con el daño— y 23,
`BarkWall` —baja ataque, defensa y agilidad, dos turnos—. La pelea no tiene
estados, y hacerlos es un sistema: duración, restricciones, la IA del
controlado, lo que cada uno cambia. EasyRPG: `AddState` de
`Game_Battler`. **Grande.** Hay una salida chica: aceptarlo sin hacerlo,
como deuda, y destrabar así las 24 páginas de `ControlMachines` y, con
`FlashScreen`, las 140 de `Inscribe`, sabiendo que el `Control` y el
`BarkWall` no pasan. Es una decisión de taro.

**`FlashScreen`** en la pelea, seis por página de `Inscribe`. En el mapa
existe; en la pelea "tiñe la paleta del mapa y no la de la escena"
(`workflow/tasks/done/eventos-de-tropa-en-la-pelea.md`). **Mediano**, y
**`TintScreen`** en la pelea va por el mismo lado. **`TerminateBattle`**
es terminar la pelea sin resultado: chico, una sola página.

## 3. Lo que el compilador acepta y no hace

`IGNORABLE`, la lista de lo que se acepta porque no hacer nada no se ve,
**está vacía** desde el 2026-10-04. Lo que hay son **deudas**: comandos que
hacen algo y la ROM no lo hace, aceptados porque si no la página entera se
caería. La lista con nombre es `ACCEPTED_UNDONE`, en `compile.rs`, y el
porqué de cada uno está en su brazo de `compile_command`:

| qué | por qué se acepta | qué se pierde |
|---|---|---|
| `ShowPicture`, `MovePicture`, `ErasePicture` de una imagen que el mapa no lleva | el mapa elige qué imágenes lleva; cortar la página le sacaba al juego páginas que hoy andan | la imagen no aparece |
| `ChangeSystemBGM` (130 usos, 25 mapas) | es una feature de audio, no un comando: la canción de sistema tendría que viajar en la partida y entrar en los paquetes | la pelea de esas zonas suena con la canción del LDB |
| `ChangeHeroTitle` (8 usos, todos de Talan) | el port no muestra el título en ningún lado: no hay pantalla de estado | nada visible hoy |

Y fuera de esa lista, aceptados vacíos a propósito:

* **`ChangePBG`**: el panorama. En modo 3 no hay capa libre; una sola
  página, el Hover-Tram del mapa 13.
* **`Comment`**: en RM2k tampoco hace nada. No es deuda.
* **`EraseEvent` después de un salto a otro mapa**: en RM2k no borra a
  nadie. No es deuda.
* **`ChangeCondition` que saca un estado que no es la muerte**: no hay
  estados que sacar. Poner un estado no compila, y nadie lo pide en un
  mapa.
* **`TileSubstitution` de un tile que el mapa no dibuja**: no hay celda que
  cambiar.
* **Una llamada a un evento que no compila se saltea**
  (`divergencias/llamada-salteada.md`, que habla de 216; hoy son las 47 de
  arriba), y también una que pasa el tope de anidamiento.
* **Sin registro de canciones** —el `scan`— `PlayBGM`, `PlaySound`,
  `MemorizeBGM` y `PlayMemorizedBGM` se aceptan vacíos; en el cartucho se
  hacen.
* En las rutas: **la transparencia** (40 y 41) se tira, y **el sonido**
  dentro de un salto o en la ruta propia de una página.

## Recomendación

1. **Los dos `EraseEvent` de la cantera, primero**: el del común (chico,
   sólo el compilador) y el de verdad del 150 (mediano, estado en la ROM).
   Son lo único que falta entre la granja y el día siguiente, y el trabajo
   de la cantera es la primera escena de ese día que pide algo que no
   existe.
2. **Los chicos de los mapas, en un lote**: `ChangeGold` por variable, el
   corte para mostrar, "alejarse del héroe", la dirección en
   `ConditionalBranch` y la constante de 999999. Con eso los mapas quedan
   en **una sola página afuera**, la del 207, que necesita decidir las
   coordenadas de pantalla. Ninguno es urgente —no están en el camino—,
   pero juntos cuestan poco y dejan el compilador sin pendientes de
   mapa.
3. **La pelea, como trabajo aparte**, empezando por `FlashScreen` en la
   escena —que además sirve a cualquier otra página de tropa— y pidiéndole
   a taro la decisión sobre `ChangeMonsterCondition`: estados de verdad
   (grande) o deuda declarada. Es lo que más páginas destraba, 164, y son
   dos habilidades que ya se usan en las peleas de `release` y hoy no
   hacen nada.

## Cómo se midió

Con las herramientas de `6094a205` y un clon de ABL en `b28864d`. El
request es el que el conversor le manda a `rm2k-snes-events compile` al
armar `release` —se copió con un envoltorio en el PATH que guarda cada
request y llama al binario—, y con `--every-map` se miran todos los mapas
del juego:

    rm2k-snes-events culprits --data <ABL>/data --request compile.json \
        --out <dir> --every-map

Imprime la tabla de la sección 2 por tipo de página —sin agrupar
variantes— y escribe `culprits.json`, con cada página que no compila, sus
culpables y sus parámetros, y cada llamada salteada. La tabla de la sección
1 sale de su `commands`; la sección 2 agrupa a mano los culpables de
`pages` por variante.

Se contrastó con lo que ya se sabía: sin `--every-map` y con el request de
`scan`, compilan **2.913** páginas de mapa de `release`, las mismas que
lista el `compiled` de `scan`; y las páginas de tropa que entran, **4.285**,
son las que dio `eventos-de-tropa-en-la-pelea.md` el 2026-09-30.

Lo que el recuento **no** mira: si una página que compila hace lo que
tiene que hacer —eso lo cuidan la tanda y taro—, ni lo que el conversor
decide aparte del compilador —qué mapas entran, qué imágenes lleva cada
uno—.
