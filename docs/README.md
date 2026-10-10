# docs/

    rpgmaker/   el formato de RPG Maker 2000: qué es un ChipSet, qué es el RTP.
                No sabe nada de este port, pero hace falta para entenderlo.
    snes/       la consola y cómo probarla. Tampoco sabe nada del port.
    port/       cómo funciona el port **hoy**.
    research/   estudios fechados: "el día tal, con el commit tal, medimos
                esto".

    jetbrains.md  lo que hay que configurar en el IDE para este repo.

Los research sobre A Blurred Line —cuánto pesa entero, hasta dónde llega su
cartucho, la inspección del repo de antes del corte— se fueron con el juego
a su repo el 2026-10-02, junto con lo de ABL de `pipeline.md` y `rtp.md`.
Los que hablan del motor se quedaron, aunque lo hayan medido sobre ABL.

La diferencia que importa es entre `port/` y `research/`:

* **Un doc de `port/` tiene que estar al día, o miente.** Por eso conviene que
  sea corto y apunte al código en vez de repetirlo: lo que el código ya dice
  envejece sin avisar si se copia acá. El que cambia lo que un doc de `port/`
  describe, lo cambia en el mismo commit.
* **Un research es una foto y no se toca.** Arriba dice la fecha y el commit de
  lo que midió, y sus números son de ese momento. Si algo cambió, se mide de
  nuevo y va un research nuevo; el viejo queda como estaba.

Si una tarea termina en un documento en vez de código, el documento va a
`research/` y la tarea pasa a `snes-rm2k-work/tasks/done/` apuntando a él.
