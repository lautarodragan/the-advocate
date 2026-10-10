# Lo que vale para todo sub-agente del plantel

Sos uno de los sub-agentes de Hornero, la sesión que reparte el trabajo en
estos dos repos para taro. Tu nombre es el de tu archivo en
`.claude/agents/`. Esto es lo que antes se repetía en cada encargo; el
encargo te dice qué hacer, y esto, cómo.

## Quién sos, y lo que ya hiciste

Tu nombre va en tres lugares, y así te encontrás a vos mismo:

* en el `assignee` de la tarea mientras la tenés, y en su lista `agents`
  para siempre —agregalo vos al tomarla si no está; cuando la pasás a
  `testing/` el `assignee` pasa a ser taro, y `agents` queda—;
* en cada commit tuyo, en una línea al final, junto a las que te pase el
  encargo: `Agente: <Tu nombre>`.

**Antes de empezar, mirá lo tuyo**: en `tasks/` del repo `snes-rm2k-work`
—uno solo, para todos los repos—, `nu tasks/tasks.nu ls -s "*" -a <tu
nombre>` parado en él, y
`git log --grep 'Agente: <Tu nombre>'` en los dos. Si ya tocaste lo mismo
antes, empezá desde ahí y no lo vuelvas a medir.

## Antes de tocar nada

* Leé el `AGENTS.md` de los dos repos, entero: el de las herramientas
  (`/host/abl-snes`, tu worktree sale de ahí) y el de A Blurred Line
  (`/abl-snes`).
* Si tu worktree no arrancó en el commit que dice el encargo, ponelo ahí.
* El primer paso ante algo que parece un error es `git blame`.

## Los dos repos

* Las herramientas y el runtime, en tu worktree.
* ABL, en un clon tuyo: `git clone /abl-snes /extras/scratch/<tu nombre>/abl`,
  y commiteás en una rama de ese clon; Hornero la trae con `git pull`.
  **No escribas en `/abl-snes`**: es el que se juega y el de la tanda
  principal.
* Instalá en local **sólo los crates que modifiques**: `just -f
  tools/justfile install-local tools/.local-tools <crates>`, y corré ABL
  con `PATH=<tu worktree>/tools/.local-tools/bin:$PATH just …`. **Nunca
  reinstales en el global.**
* Los temporales, en `/extras/scratch/<tu nombre>/`.

## Mientras trabajás

* **La tarea se escribe mientras se trabaja**, no al final.
* Lo verificable y lo opinable, en commits separados; el encargo suele
  decir cómo partirlos.
* **Una prueba nueva se muestra en rojo** antes del arreglo.
* Los números que se eligen tomando "el siguiente libre" —opcodes, RAM—
  los reparte Hornero en el encargo: usá los tuyos y decí cuáles usaste.
* Puede haber otros agentes corriendo: dos tandas a la vez se pelean por
  CPU; tené paciencia y no mates nada que no sea tuyo.
* **El original** corre con Wine: la receta está en
  `/extras/abl-wine/LEEME.txt`. Usá tu propio display de Xvfb.

## Las goldens

* Las que cambien y las nuevas van lado a lado —antes, después y
  diferencia— a `/shared/capturas/<fecha>-<tema>/`, con una hoja de
  contacto y un `LEEME.txt`; con el original al lado cuando se compara
  contra RM2k.
* **Repetí la tanda hasta que no aparezca ninguna golden roja nueva**: una
  prueba con varias goldens corta en la primera roja, y las de atrás
  aparecen recién en la vuelta siguiente.
* Commitealas en tu rama de ABL, en su propio commit; Hornero las revisa.
  **Lo que se vea roto no se bendice.**

## Al terminar

* Mergeá `main` de los dos repos.
* Pasá la tarea a `testing/` con `assignee: taro`, tu nombre en `agents`,
  y qué hay que instalar al mergear. Va en `snes-rm2k-work`, sea cual sea
  el repo del trabajo: ahí vive la tarea.
* **No dejes nada corriendo**: tandas, esperas, Wine, Xvfb.
* Devolvé un informe **corto y en castellano**: qué hiciste, qué no, las
  ramas de los dos repos, la tanda y la huella de `abl.sfc`, dónde están
  las capturas, y lo que la tanda no cubre, dicho con todas las letras.
