---
name: "Talan negro con DummyHero de líder"
description: "un actor sin gráfico le subía quince colores en cero a la paleta de sprite 0; en el barril del 14 y en la guarida de Wick esa paleta era la de Talan"
type: bug
assignee: taro
---

Reportado por taro jugando en la SNES el 2026-09-27. **Pasaba en `release`.**
Arreglado en el commit que mueve esta tarea a `testing/`.

# El reporte

> en la casa de Boss Wick, luego de ver los vidcasts, Talan queda
> completamente negro. Algo similar ya pasaba antes: en el Lazer Teeth HQ,
> cuando Talan está escondido en el barril [...] aparece Talan sin barril
> (hasta acá, todo OK), pero Talan queda completamente negro. En ambos casos
> un cambio de mapa parece restaurarlo a la normalidad.

# Lo que se midió

**No es el cambio de gráfico.** La sospecha era que un cambio de gráfico en
el mismo mapa subía los tiles y no la paleta. En las dos escenas Talan **no es
el héroe**: es un evento con `Future1:0` —el 4 del mapa 14 (NV Get Talan to
Work, la escena del barril) lo toma con la orden 34 de una ruta; el 8 del
mapa 40, `TalanProxy`, lo trae en su página— y el héroe es `DummyHero`, el
actor 10, que el juego pone de líder en esas cinemáticas: la página 2 del
hotplate saca a Talan antes de ir al 14, y el `Security Footage` (el 45)
pone al 10 antes de volver al 40.

`DummyHero` no tiene un pixel opaco. El conversor le da en la tabla de
actores la paleta 0 y quince colores en cero, con el comentario "la ROM no
los sube" (`5264eada`, 2026-09-07). **La ROM sí los subía**:
`elegir_grafico_heroe` apuntaba `hero_cgram` a esos colores para cualquier
actor que encontrara, y `aplicar_tinte` los copiaba a la paleta de sprite 0
al cargar el mapa. La paleta 0 es la del primer gráfico que reparte el
conversor, y en los dos mapas es la de `Future1:0`.

El volcado de `cgram_sombra` en el momento de cada escena, antes del
arreglo —la paleta 0 entera en cero, y el sprite de Talan en la OAM con la
paleta 0—:

    mapa 14, Talan sale del barril   grupo=10 hero_pal=0  obj pal 0: 0000 x16
    mapa 40, el favor y el cirujano  grupo=10 hero_pal=0  obj pal 0: 0000 x16

Y "un cambio de mapa lo arregla" es porque en los dos casos el mapa siguiente
se carga con Talan de líder: el 14 lo pone en el grupo antes de irse al 16 y
el 41 rearma el grupo.

**Pasaba en todos los mapas del juego**: con `DummyHero` de líder, los 66
mapas de `MAPAS_DEL_JUEGO` cargaban la paleta 0 en negro. Lo mide
`test_lider_sin_grafico.py`: 66 rojos con el código de antes, 0 con el de
ahora. Qué se veía negro en cada uno depende de quién usa la paleta 0.

Dónde llega el juego con `DummyHero` liderando —páginas que ponen al 10, y
los mapas a los que saltan después—, con un script descartable sobre `data/`:

    ponen al 10     4, 12, 18, 26, 33, 37, 38, 40, 45, 47, 48, 81, 84
    se llega así a  4, 5, 14, 20, 36, 40, 66, 82

# El arreglo

`elegir_grafico_heroe` apaga `hero_cgram` cuando el actor no tiene gráfico,
reconocido por el mismo centinela que mira `place_hero` (la primera pose en
`$FFFF`). Es lo que el comentario del conversor y el de `hero_cgram` en
`pagina_cero.s` ya decían que pasaba.

# Lo que queda, parecido y distinto

**Un evento que la orden 34 cambia al gráfico de un líder posible, sin que
ese gráfico esté en ninguna página del mapa, comparte la ranura del líder**
—`npcs_dibujables` sólo le da paleta propia a los líderes que están como NPC
en alguna página—. Se dibuja con los colores de quien lidere. No se pone
negro (con el arreglo, con `DummyHero` liderando la ranura queda con los
colores del cartucho, que son los del primer líder), pero con otro líder que
no sea el del gráfico se vería con colores ajenos. En `release`:

    14  NV Get Talan to Work   ev4  -> Future1:0 (Talan)    6 paletas de 8
    76  Sorbe Mountain         ev5  -> AG717:4 (AG7-17)     7 paletas de 8
    81  Dr. Vago's House       ev2  -> Future1:0 (Talan)    Talan lidera: bien
    83  Dalia at the Factory   ev13 -> Future1:5 (Kersh)    8 paletas de 8

No se tocó: arreglarlo es darles paleta propia en el conversor, y el 83 ya
usa las ocho, así que ahí alguien pasaría a dibujarse con una prestada. Si
taro ve al capitán de la Agencia del 83 o a AG7-17 en el 76 con colores
raros, es esto.

# Qué tiene que probar taro

1. La escena del barril: Talan sale del barril con sus colores.
2. La guarida de Wick, después de los vidcasts: Talan (el evento) con sus
   colores en el cuarto de Wick y en el del cirujano.
