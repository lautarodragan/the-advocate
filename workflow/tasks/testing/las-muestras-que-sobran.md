---
name: "Las muestras que sobran no suenan"
description: "Cuando un cartucho pide más de 255 muestras (SRCN es un byte), las que sobran se dejan afuera con un aviso, en vez de cortar el armado"
type: feature
agents: [Mulita]
assignee: taro
---

De taro, el 2026-10-06: "en vez de lograr que entren las muestras, estaría
bueno no necesitar excluir a esos mapas, y simplemente droppear las muestras
> 255 y ya. Que el juego no falle — simplemente, que no emita sonido, donde
no puede." Dooms 2 hoy arma sólo excluyendo los mapas 40 a 93.

## Hecho (Mulita, 2026-10-06)

- `bank::drop_surplus`, llamada en `compile.rs` antes de repartir copias:
  si las muestras de las canciones no caben en `255 - lugares de efectos`,
  se dejan afuera las **menos usadas** (por cantidad de canciones; empate:
  la última en el orden de `Key`), con un `WARNING` en el log del conversor.
  Una clave descartada queda fuera de todos los conjuntos de claves, igual
  que una que el SoundFont no tiene: esas notas no suenan y nada apunta a
  una muestra inexistente. Prueba: `over_255_keys_the_least_used_are_left_out`.
- **La causa real de Dooms 2 no era ésa**: tenía 247 claves o menos y el
  corte venía de las *copias* (`bank::copies`), que llenaban el directorio
  hasta 255 contando sólo `usual` (min de efectos y ranuras) y no los lugares
  reales de los efectos (8). Ahora `usual` nunca baja de `places`. Con eso
  Dooms 2 arma con los mapas 40 a 93 y el drop no llega a dispararse.
- Verificado: `release` de ABL con estas herramientas, `abl.sfc`
  `27e94e67...` igual; Dooms 2 arma, arranca y muestra el diálogo (captura
  a los 3 s). La tanda de ABL no se corrió.
