# Dónde la ROM no hace lo que RM2k hace

Un archivo por divergencia: **qué hace la ROM, qué hace RM2k, lo medido, y cómo
reproducirlo**. Es descripción y no deseo —lo que nos gustaría hacer y nadie
está haciendo es `wishlist/`—, y no es un rojo abierto: ninguna de éstas falla
hoy. Varias vienen de cuando existía la referencia en Python, y desde el
2026-09-16 la golden es una captura de la propia ROM, así que **hornea adentro
el comportamiento que la referencia discutía**. O sea que son lugares donde
sabemos que la ROM difiere y nada lo cobra. Quedan escritas por eso, y porque
el día que alguna se arregle hay goldens que se van a mover y alguien va a
querer saber por qué.

Lo que **no** va acá: lo que la tanda no mira pero nadie dice que esté mal, lo
que falta hacer del port —eso es `tasks/`— y las diferencias entre emuladores,
que no son de la ROM. Tampoco una divergencia **decidida y cerrada**, de las
que el port se permite a propósito y no piensa deshacer: ésas viven donde está
la decisión, con el código o en `decisiones/`. Acá van las que siguen abiertas,
aunque nadie las esté tocando.

**Salvo las que valen porque *A Blurred Line* es como es.** El horizonte es un
`migrar-rm2k-a-snes juego.zip juego.sfc` que ande sin ajustar tuercas, y varias
elecciones del port no son generales: funcionan por cómo es este juego. Ésas
van acá aunque estén decididas, con el número que las justificó y una sección
**"Cuándo deja de alcanzar"**, porque si mañana esto se apunta a otro juego son
lo primero que hay que volver a mirar. Hasta el 2026-09-25 vivían juntas en
`assets/LIMITACIONES.md`.
