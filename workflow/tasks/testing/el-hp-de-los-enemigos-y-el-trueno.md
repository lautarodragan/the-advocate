---
name: "El HP de los enemigos escondido, y el trueno del despegue"
description: "Esconder los HP de los enemigos como RM2k (con flag para depurar) y grabar el tema de batalla con y sin Thunder9 para que taro decida"
type: feature
assignee: Ombú
---

Dos cosas chicas de la pelea, del 2026-09-28.

**El HP de los enemigos.** RM2k no lo muestra nunca y ABL no tiene cómo verlo
(lo midió Tero: `testing/el-menu-como-rm2k.md`). taro aceptó la propuesta:
esconderlo por defecto con un flag de armado, `CON_HP_DE_ENEMIGOS = False` en
`cartuchos.py`, como `CON_MAPA_DE_DEBUG`. Hoy lo dibuja `ba_renglon` en
`rom/src/batalla.s`; en `pantallas.py` está anotado como decisión propia.

**El trueno del despegue.** La página de turno 1 de las tropas 102 y 104 pide
Thunder9, y no suena porque meterlo en el paquete de la pelea le baja al tema
de batalla seis instrumentos de ~14 a ~11,5 kHz y el BRASS64 de 16,3 a 10,8
(lo midió Ceibo: `testing/eventos-de-tropa-de-release.md`). Se decide
escuchando.

2026-09-28, en `testing/`: hecho por Ombú en su rama, sobre `main` en
8da66c4, en e15fd72; `just cartuchos` y `just pruebas` en verde. Lo que queda
es de taro: mirar las goldens y escuchar el trueno (ver abajo).

# El HP de los enemigos — hecho

Como lo propuso Tero: `CON_HP_DE_ENEMIGOS = False` en
`tools/ensamblado/cartuchos.py`, al lado de `CON_MAPA_DE_DEBUG`, que pasa
`--hp-de-enemigos` al conversor **en los dos cartuchos**; el conversor emite
`BA_HP_ENEMIGOS` junto a `BA_HP_NUM_DX`, y `ba_renglon` (`rom/src/batalla.s`)
corta después del nombre si el renglón no es del grupo. En `pantallas.py` no
hay una referencia que dibuje la pelea, sólo la geometría y la decisión
escrita arriba de `BA_ENEMIGO_FILA0`: se reescribió.

Una trampa de `ca65` que costó un armado: adentro de un `.proc`, `.if
BA_HP_ENEMIGOS = 0` da "Constant expression expected" aunque la constante
esté definida antes; con `::BA_HP_ENEMIGOS` anda. Está comentado ahí.

**Con el flag prendido la ROM es la de antes, byte por byte**: armado un
`release` aparte con `--hp-de-enemigos` y ensamblado el `rom/src/` de 8da66c4
contra su mismo `mapdata.inc`, los dos `.sfc` salen iguales (`cmp`). Ese
camino no lo corre `just pruebas`: la tanda corre con el flag apagado.

**Las goldens que cambian son nueve**, y en todas lo único distinto es el
rectángulo x 145-191 de los renglones de enemigos: `batalla`,
`batalla-blanco`, `batalla-droide`, `batalla-textos-lejos`, `encuentro`,
`msu-datos-rom`, `msu-datos-msu`, `msu-mundo-rom` y `msu-mundo-msu`. Antes y
después, lado a lado, en `/shared/capturas/2026-09-28-hp-de-enemigos/`.

**Ninguna prueba leía el HP de un enemigo en la pantalla** salvo esas
goldens, y ninguna de ellas muestra un golpe: todas son la pelea recién
abierta o eligiendo blanco, con los HP enteros. Las que miran cuánto le queda
a un enemigo ya lo leen de la RAM (`Pelea.hp_del_combatiente`), así que no
hubo nada que pasar de la pantalla a la RAM.

# El trueno — grabado, para que taro decida

Nada en `main`. Armados aparte, con un envoltorio del conversor que suma
`Thunder9` a `SE_DE_TROPA_AL_PAQUETE` sin tocar el fuente; el control (el
mismo envoltorio sin sumarlo) sale byte por byte igual al `release`. Los wav y
lo que hay que escuchar en cada uno, en `/shared/audio/2026-09-28-trueno/`
(`LEEME.txt`).

Lo medido, comparando las líneas del reparto del `conversor.log`:

- **a 6000 Hz**, la tasa que Thunder9 ya tiene en los mapas 3, 20 y 32:
  BRASS64 de 16,3 a 10,8 kHz —lo usa sólo el tema de batalla— y trece más de
  `T_VGFighterMAX_Masako` de 13,6-14,1 a 11,5-11,7: cinco programas (DSTGT48,
  NYLON48A, FANTA81, STLGT57B, STRNG71B) y **ocho de la batería**, que la
  cuenta de Ceibo no traía.
- **con MSU-1** el tema no pierde nada, pero los efectos de calidad del
  paquete de la pelea en el `.msu` bajan de 14000 a 12000 Hz: los siete que
  ya estaban, más el trueno.
- **sin bajar nada no entra**: el paquete de la pelea tiene 896 B libres y el
  trueno ocupa 6462 B a 6000 Hz, 5382 a 5000, 4302 a 4000 y 3231 a 3000. A
  las cuatro tasas BRASS64 baja igual a 10,8, y los otros trece bajan menos
  cuanto más baja la tasa (a 3000: 12,6-13,0). Entrar en 896 B pediría unos
  800 Hz. Compartir: ningún efecto de la pelea usa esa muestra.
- **de paso**: Thunder9 a 3000 Hz en todos lados le sube a `evilrhys`, en el
  mapa 3, nueve instrumentos de 4,5-5,2 a 6,5-6,8 kHz, porque el 3 hoy paga
  el trueno a 6000.

Lo que queda es de taro: escuchar y decir si entra, y a qué tasa. Si entra,
es sumar `"Thunder9"` a `SE_DE_TROPA_AL_PAQUETE` (y, para otra tasa sólo en
la pelea, un alias como `Thunder9@entero`), rehacer `just techos`, y
`test_el_despegue_pide_su_efecto` deja de decir "no suena".

# Números usados

Ninguno: ni el opcode 0x34 ni la RAM lejana `$7E7A30`-`$7E7A3F`.
