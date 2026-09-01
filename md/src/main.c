/* ---------------------------------------------------------------------------
 * Renderiza un mapa de A Blurred Line en el VDP de la Mega Drive y deja mover
 * la cámara con la cruceta.
 *
 * El personaje se mueve como en RM2k: la posición "real" es el tile destino,
 * que se fija apenas arranca el paso, y un contador de 256 unidades por tile
 * dice cuánto falta para llegar. El sprite se dibuja interpolado entre el tile
 * anterior y el destino. La cámara lo sigue, centrada y con clamp.
 *
 * La colisión sale de una tabla que el conversor deja resuelta: un byte por
 * tile con los cuatro bits de dirección. Moverse pide permiso a los dos tiles,
 * el de origen para salir y el destino para entrar.
 *
 * El plano A mide 64x64 celdas de 8x8 y se repite cada 512 píxeles, así que un
 * mapa más grande no entra de una. Lo que se hace es tenerlo poblado sólo
 * alrededor de la cámara —41 columnas por 31 filas, una más que lo visible en
 * cada eje por el scroll sub-celda— y redibujar la columna o la fila que va
 * entrando a medida que la cámara se mueve. El plano se comporta como un
 * anillo: la celda del mapa (x, y) siempre cae en la posición (x mod 64,
 * y mod 64), y el registro de scroll se encarga del resto.
 *
 * El modo de video se elige según la consola: V30 (240 renglones) sólo funciona
 * a 50 Hz, así que en NTSC se usan los 224 de siempre y se ve un poco menos.
 * --------------------------------------------------------------------------- */
#include "mapdata.h"
#include "musicdata.h"

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef signed short   s16;

#define VDP_DATA_W   (*(volatile u16 *)0xC00000)
#define VDP_DATA_L   (*(volatile u32 *)0xC00000)
#define VDP_CTRL_W   (*(volatile u16 *)0xC00004)
#define VDP_CTRL_L   (*(volatile u32 *)0xC00004)

/* Bit 6 del registro de versión: 1 = consola PAL de 50 Hz. */
#define VERSION_REG  (*(volatile u8 *)0xA10001)
#define PAD1_DATA    (*(volatile u8 *)0xA10003)
#define PAD1_CTRL    (*(volatile u8 *)0xA10009)
#define PSG_PORT     (*(volatile u8 *)0xC00011)
/* El YM2612 tiene dos mitades: los canales 1 a 3 en la parte 1 y los 4 a 6 en
 * la parte 2. Cada una con su par dirección/dato. */
#define YM_ADDR1     (*(volatile u8 *)0xA04000)
#define YM_DATA1     (*(volatile u8 *)0xA04001)
#define YM_ADDR2     (*(volatile u8 *)0xA04002)
#define YM_DATA2     (*(volatile u8 *)0xA04003)

/* --- mapa de la VRAM ------------------------------------------------------
 * Con los planos de 64x64 celdas cada uno ocupa 8 KB. Los tiles van abajo de
 * todo: hay lugar para 1024, que a 32 bytes son los primeros 32 KB.
 */
#define TILESET_ADDR 0x0020     /* el tile 0 se deja en blanco */
/* El plano B lleva el mapa y el A los tiles que van por encima del héroe, con
 * el bit de prioridad puesto. El orden del hardware —plano B sin prioridad,
 * sprites, plano A con prioridad— es exactamente el de RM2k. */
#define PLANE_OVER   0x8000
#define PLANE_BASE   0xA000
#define PLANE_A      PLANE_OVER
#define PLANE_B      PLANE_BASE
#define PLANE_W      0xD000
#define SPRITE_TAB   0xF000
#define HSCROLL_TAB  0xFC00

#define PLANE_CELLS_W 64
#define PLANE_CELLS_H 64

/* Una columna y una fila más de lo que se ve, porque la cámara se mueve de a
 * píxeles y casi siempre hay media celda asomando de cada lado. En NTSC se ven
 * dos filas menos y sobran, que no molesta. */
#define VIEW_W       41
#define VIEW_H       31

#define SCREEN_W     320
#define WORLD_W      (MAP_CELLS_W * 8)
#define WORLD_H      (MAP_CELLS_H * 8)

/* --- el personaje, con el modelo de RM2k ----------------------------------
 * remaining_step va de 256 a 0 y baja 1 << (1 + velocidad) por cuadro. A la
 * velocidad 4, la normal, son 32 por cuadro: ocho cuadros por tile, o sea 2 px
 * por cuadro. La animación avanza cada 6 cuadros, que es lo que EasyRPG saca
 * de las tablas de RPG_RT para esa velocidad.
 */
#define TILE_UNITS   256
#define MOVE_SPEED   4
#define MOVE_STEP    (1 << (1 + MOVE_SPEED))
#define ANIM_PERIOD  6

/* El sprite mide 24x32 y se para en una celda de 16x16: va centrado a lo ancho
 * y apoyado por los pies. */
#define SPRITE_OFFSET_X (-((SPRITE_CELLS_W * 8 - 16) / 2))
#define SPRITE_OFFSET_Y (-(SPRITE_CELLS_H * 8 - 16))

/* Los tiles del personaje van en la VRAM justo después de los del mapa. */
#define SPRITE_TILE_BASE (1 + MAP_TILE_COUNT)

/* Los bits de paso de RM2k, uno por lado del tile. */
#define PASS_DOWN  0x01
#define PASS_LEFT  0x02
#define PASS_RIGHT 0x04
#define PASS_UP    0x08

/* Las filas del CharSet de RM2k, en ese orden. */
#define FACE_UP    0
#define FACE_RIGHT 1
#define FACE_DOWN  2
#define FACE_LEFT  3

#define BTN_UP    0x01
#define BTN_DOWN  0x02
#define BTN_LEFT  0x04
#define BTN_RIGHT 0x08

#define VRAM_WRITE  0x40000000u
#define CRAM_WRITE  0xC0000000u
#define VSRAM_WRITE 0x40000010u

static void vdp_reg(u8 reg, u8 value)
{
    VDP_CTRL_W = (u16)(0x8000 | (reg << 8) | value);
}

/* El VDP direcciona con un patrón de bits repartido en dos palabras. */
static void vdp_addr(u32 kind, u16 addr)
{
    VDP_CTRL_L = kind | ((u32)(addr & 0x3FFF) << 16) | ((addr >> 14) & 3);
}

/* Qué partes del init se aplican.
 *
 * El default son los 16 registros que escribía el primer build que funcionó en
 * una consola de verdad. Después agregué los ocho que faltaban, convencido de
 * que dejar registros sin escribir era lo que rompía en hardware, y fue al
 * revés: con eso dejó de andar.
 *
 * Bisecando en la consola resultó ser **el registro 23 con el valor 0x00**. Sus
 * dos bits de arriba eligen el tipo de DMA, y 00 es "transferencia del 68000 al
 * VDP"; con 0x80, que es "relleno de VRAM", no pasa nada. Los otros siete
 * registros y la lectura del puerto de control se probaron uno por uno en
 * hardware y son inofensivos. Ningún emulador reproduce esto.
 *
 * Por eso la tabla lleva 0x80 en el 23: el valor peligroso no está escrito en
 * ningún lado. El default igual no toca los de DMA, porque no los necesitamos
 * todavía y lo que anda, anda.
 */
#define VDP_STATUS_READ 1
#define VDP_REGS_8_9    2
#define VDP_REG_14      4
#define VDP_REGS_DMA    8    /* los cinco de DMA, 19 a 23 */

#ifndef VDP_EXTRA
#define VDP_EXTRA 0
#endif

/* Los 24 registros del VDP, todos, en orden.
 *
 * La tabla los tiene todos; VDP_EXTRA decide cuáles se escriben.
 */
static const u8 vdp_regs[24] = {
    0x04,                   /*  0  modo 1: MODE5, sin interrupción de línea   */
    0x04,                   /*  1  modo 2: display OFF hasta terminar         */
    PLANE_A >> 10,          /*  2  base del plano A                           */
    PLANE_W >> 10,          /*  3  base de la ventana                         */
    PLANE_B >> 13,          /*  4  base del plano B                           */
    SPRITE_TAB >> 9,        /*  5  base de la tabla de sprites                */
    0x00,                   /*  6  base de patrones de sprites (modo 128K)    */
    0x00,                   /*  7  color de fondo: paleta 0, índice 0         */
    0x00,                   /*  8  sin uso en Mega Drive (es del Master)      */
    0x00,                   /*  9  sin uso en Mega Drive                      */
    0xFF,                   /* 10  contador de HINT, sin uso                  */
    0x00,                   /* 11  modo 3: scroll de pantalla completa        */
    0x81,                   /* 12  modo 4: H40 (320 px), sin entrelazado      */
    HSCROLL_TAB >> 10,      /* 13  base de la tabla de hscroll                */
    0x00,                   /* 14  base de patrones de los planos (modo 128K) */
    0x02,                   /* 15  autoincremento de 2 bytes por escritura    */
    0x11,                   /* 16  tamaño de los planos: 64x64 celdas         */
    0x00,                   /* 17  posición horizontal de la ventana          */
    0x00,                   /* 18  posición vertical de la ventana            */
    0x00, 0x00,             /* 19-20  largo del DMA                           */
    0x00, 0x00,             /* 21-22  origen del DMA                          */
    0x80                    /* 23  tipo de DMA. NUNCA 0x00: cuelga la consola */
};

/* En hardware real el autoincremento se aplica cuando el VDP saca la escritura
 * de la FIFO, no cuando el 68000 la mete. Si se cambia el registro 15 con la
 * FIFO todavía cargada, las escrituras que están esperando se guardan con el
 * incremento nuevo y terminan en cualquier lado. Los emuladores aplican el
 * incremento en el momento de la escritura, así que esto no se ve nunca ahí.
 *
 * El bit 9 del registro de estado dice que la FIFO está vacía. */
static void vdp_wait_fifo(void)
{
#ifndef NO_FIFO_WAIT
    while (!(VDP_CTRL_W & 0x0200))
        ;
#endif
}

static void vdp_init(void)
{
    u8 i;

    /* Una lectura del puerto de control descarta cualquier primera mitad de
     * comando que haya quedado colgada, por ejemplo del BIOS de TMSS. Sin
     * esto, la primera escritura se interpretaría como la segunda mitad. */
#if VDP_EXTRA & VDP_STATUS_READ
    (void)VDP_CTRL_W;
#endif

    for (i = 0; i < 24; i++) {
        if ((i == 8 || i == 9) && !(VDP_EXTRA & VDP_REGS_8_9))
            continue;
        if (i == 14 && !(VDP_EXTRA & VDP_REG_14))
            continue;
        if (i >= 19 && !(VDP_EXTRA & VDP_REGS_DMA))
            continue;
        vdp_reg(i, vdp_regs[i]);
    }
}

static void vram_clear(void)
{
    u16 i;
    vdp_addr(VRAM_WRITE, 0x0000);
    for (i = 0; i < 0x8000; i++)
        VDP_DATA_W = 0x0000;
}

/* El índice 0 de cada paleta es transparente y ningún tile lo usa: el conversor
 * pone magenta ahí, que es el color de fondo y a la vez un canario. Si se ve
 * magenta dentro de la pantalla, algún tile está usando el índice 0. */
static void load_palette(void)
{
    u16 i;
    vdp_addr(CRAM_WRITE, 0x0000);
    for (i = 0; i < 64; i++)
        VDP_DATA_W = md_palette[i];
}

static void load_tiles(void)
{
    u16 i;
    vdp_addr(VRAM_WRITE, TILESET_ADDR);
    for (i = 0; i < MAP_TILE_COUNT * 8; i++)
        VDP_DATA_L = md_tiles[i];

    /* Las 12 poses del héroe y, atrás, una pose por cada NPC distinto. */
    vdp_addr(VRAM_WRITE, (u16)(TILESET_ADDR + MAP_TILE_COUNT * 32));
    for (i = 0; i < SPRITE_POSES * SPRITE_POSE_TILES * 8; i++)
        VDP_DATA_L = md_sprite_tiles[i];
    for (i = 0; i < sizeof(md_npc_tiles) / sizeof(md_npc_tiles[0]); i++)
        VDP_DATA_L = md_npc_tiles[i];
}

/* El VDP admite 80 sprites, encadenados en una lista: cada entrada apunta a la
 * siguiente y el enlace 0 la termina. Los primeros de la lista tapan a los
 * últimos.
 *
 * Por scanline el límite es de 20 sprites o 320 píxeles, lo que llegue primero.
 * Con personajes de 24 px de ancho eso son 13; en el Auditorium, que es el
 * mapa más cargado, se juntan 11 más el héroe.
 */
#define MAX_SPRITES 80

/* El héroe va en la capa "same": la 1. */
#define HERO_LAYER 1

static s16 sprite_order[MAX_SPRITES];   /* índice de NPC, o -1 para el héroe */

/* El VDP suma 128 a las coordenadas, así que un sprite en 0,0 va en 128,128. */
static void draw_sprites(s16 cam_x, s16 cam_y, s16 screen_h,
                         s16 hero_x, s16 hero_y, u16 hero_attr)
{
    u16 count = 0;
    u16 i;
    u8 hero_placed = 0;

    (void)screen_h;   /* sólo se usa para recortar, y sin NPCs no hay qué recortar */

    /* Los NPCs vienen ordenados como los dibuja RM2k: primero por capa y
     * después por Y. El héroe está en la capa 1, la suya, y se mete donde le
     * toca por su Y dentro de esa banda. Así un evento de capa 0 —un punto de
     * guardado en el piso, una alfombra— queda siempre debajo, aunque esté más
     * adelante en la pantalla, y uno de capa 2 lo tapa siempre. */
#if NPC_COUNT
    for (i = 0; i < NPC_COUNT && count < MAX_SPRITES; i++) {
        s16 x = md_npcs[i].x - cam_x;
        s16 y = md_npcs[i].y - cam_y;

        if (!hero_placed
            && (md_npcs[i].layer < HERO_LAYER
                || (md_npcs[i].layer == HERO_LAYER
                    && md_npcs[i].y < hero_y))) {
            sprite_order[count++] = -1;
            hero_placed = 1;
            if (count >= MAX_SPRITES)
                break;
        }
        /* Fuera de pantalla no gasta entrada ni presupuesto de scanline. */
        if (x <= -(SPRITE_CELLS_W * 8) || x >= SCREEN_W)
            continue;
        if (y <= -(SPRITE_CELLS_H * 8) || y >= screen_h)
            continue;
        sprite_order[count++] = (s16)i;
    }
#endif
    if (!hero_placed && count < MAX_SPRITES)
        sprite_order[count++] = -1;

    vdp_addr(VRAM_WRITE, SPRITE_TAB);
    for (i = 0; i < count; i++) {
        s16 x, y;
        u16 attr;

        if (sprite_order[i] < 0) {
            x = hero_x; y = hero_y; attr = hero_attr;
        } else {
            x = md_npcs[sprite_order[i]].x;
            y = md_npcs[sprite_order[i]].y;
            attr = md_npcs[sprite_order[i]].attr;
        }

        VDP_DATA_W = (u16)(y - cam_y + 128);
        VDP_DATA_W = (u16)(((SPRITE_CELLS_W - 1) << 10)
                           | ((SPRITE_CELLS_H - 1) << 8)
                           | (i + 1 < count ? i + 1 : 0));
        VDP_DATA_W = attr;
        VDP_DATA_W = (u16)(x - cam_x + 128);
    }
}

/* --- el plano como ventana móvil sobre el mapa -----------------------------
 * top_x, top_y son las coordenadas, en celdas del mapa, de la esquina de
 * arriba a la izquierda de lo que está poblado en el plano.
 */
static s16 top_x;
static s16 top_y;

static u16 cell_at(const u16 *cells, s16 x, s16 y)
{
    if (x < 0 || y < 0 || x >= MAP_CELLS_W || y >= MAP_CELLS_H)
        return 0;               /* fuera del mapa: celda en blanco */
    return cells[(u32)y * MAP_CELLS_W + (u32)x];
}

static u16 plane_addr(u16 plane, u16 col, u16 row)
{
    return (u16)(plane + row * (PLANE_CELLS_W * 2) + col * 2);
}

/* Las dos escriben una tira de celdas y la parten en dos cuando se pasa del
 * borde del plano, que es donde el anillo da la vuelta. */

static void draw_column(s16 map_x, s16 map_y)
{
    u16 col = (u16)map_x & (PLANE_CELLS_W - 1);
    u16 row = (u16)map_y & (PLANE_CELLS_H - 1);
    s16 left = VIEW_H;
    s16 y = map_y;
    s16 run, i;

    /* Con el autoincremento en una fila entera del plano, una columna se
     * escribe de corrido en vez de reposicionar el VDP en cada celda. */
    vdp_wait_fifo();
    vdp_reg(15, PLANE_CELLS_W * 2);
    while (left > 0) {
        run = (s16)(PLANE_CELLS_H - row);
        if (run > left)
            run = left;

        vdp_addr(VRAM_WRITE, plane_addr(PLANE_BASE, col, row));
        for (i = 0; i < run; i++)
            VDP_DATA_W = cell_at(md_tilemap, map_x, (s16)(y + i));
#if MAP_OVERLAY
        vdp_addr(VRAM_WRITE, plane_addr(PLANE_OVER, col, row));
        for (i = 0; i < run; i++)
            VDP_DATA_W = cell_at(md_overlay, map_x, (s16)(y + i));
#endif
        left -= run;
        y += run;
        row = 0;
    }
    vdp_wait_fifo();
    vdp_reg(15, 2);
}

static void draw_row(s16 map_y, s16 map_x)
{
    u16 col = (u16)map_x & (PLANE_CELLS_W - 1);
    u16 row = (u16)map_y & (PLANE_CELLS_H - 1);
    s16 left = VIEW_W;
    s16 x = map_x;
    s16 run, i;

    while (left > 0) {
        run = (s16)(PLANE_CELLS_W - col);
        if (run > left)
            run = left;

        vdp_addr(VRAM_WRITE, plane_addr(PLANE_BASE, col, row));
        for (i = 0; i < run; i++)
            VDP_DATA_W = cell_at(md_tilemap, (s16)(x + i), map_y);
#if MAP_OVERLAY
        vdp_addr(VRAM_WRITE, plane_addr(PLANE_OVER, col, row));
        for (i = 0; i < run; i++)
            VDP_DATA_W = cell_at(md_overlay, (s16)(x + i), map_y);
#endif
        left -= run;
        x += run;
        col = 0;
    }
}

static void fill_plane(s16 x, s16 y)
{
    s16 i;
    top_x = x;
    top_y = y;
    for (i = 0; i < VIEW_W; i++)
        draw_column((s16)(x + i), y);
}

/* Mueve la ventana hasta donde la quiere la cámara, redibujando sólo lo que
 * entra. Normalmente es una columna, una fila, o ninguna. */
static void stream_to(s16 want_x, s16 want_y)
{
    while (top_x < want_x) {
        draw_column((s16)(top_x + VIEW_W), top_y);
        top_x++;
    }
    while (top_x > want_x) {
        top_x--;
        draw_column(top_x, top_y);
    }
    while (top_y < want_y) {
        draw_row((s16)(top_y + VIEW_H), top_x);
        top_y++;
    }
    while (top_y > want_y) {
        top_y--;
        draw_row(top_y, top_x);
    }
}

static u8 read_pad(void)
{
    u8 value;

    /* Con TH en alto el puerto devuelve C, B, derecha, izquierda, abajo y
     * arriba, activos en bajo. Los nops le dan tiempo al pad a responder. */
    PAD1_DATA = 0x40;
    __asm__ volatile ("nop\n\tnop\n\tnop\n\tnop");
    value = PAD1_DATA;
    return (u8)(~value & 0x3F);
}

static void wait_vblank(void)
{
    while (VDP_CTRL_W & 0x0008)     /* si ya estamos adentro, salir primero */
        ;
    while (!(VDP_CTRL_W & 0x0008))  /* y ahora esperar el siguiente         */
        ;
}

static s16 clamp(s16 value, s16 high)
{
    if (value < 0)
        return 0;
    if (value > high)
        return high;
    return value;
}

static void set_scroll(s16 x, s16 y)
{
    /* El scroll horizontal va al revés que la cámara: correr la ventana a la
     * derecha es correr el plano a la izquierda. El vertical no. */
    vdp_addr(VRAM_WRITE, HSCROLL_TAB);
    VDP_DATA_W = (u16)(-x);
    VDP_DATA_W = (u16)(-x);
    vdp_addr(VSRAM_WRITE, 0x0000);
    VDP_DATA_W = (u16)y;
    VDP_DATA_W = (u16)y;
}

/* --- música ---------------------------------------------------------------
 *
 * El PSG tiene tres canales de onda cuadrada y uno de ruido, y no hay
 * envolventes ni polifonía: todo el trabajo lo hizo el conversor, que dejó un
 * log de escrituras con el tiempo entre medio. Acá sólo hay que escupir bytes
 * al puerto cuando toca.
 *
 * Formato: cuántos bytes escribir, los bytes, y cuántos cuadros esperar
 * después. Un 0xFF en la cantidad marca el final y vuelve a empezar.
 */
static const u8 *music_at;
static u8 music_wait;
static u16 music_accum;

/* El YM2612 tarda en digerir cada escritura y hay que esperarlo: el bit 7 del
 * puerto de dirección de la parte 1 dice si todavía está ocupado. Vale para las
 * dos partes. */
static void ym_write(u8 part, u8 reg, u8 value)
{
    while (YM_ADDR1 & 0x80)
        ;
    if (part == 1) {
        YM_ADDR1 = reg;
        while (YM_ADDR1 & 0x80)
            ;
        YM_DATA1 = value;
    } else {
        YM_ADDR2 = reg;
        while (YM_ADDR1 & 0x80)
            ;
        YM_DATA2 = value;
    }
}

static void music_start(void)
{
    music_at = md_music;
    music_wait = 0;
    music_accum = 0;
}

/* Opcodes del stream: escritura al PSG, a una de las dos partes del YM2612,
 * esperar cuadros, o fin. */
#define OP_PSG  0x00
#define OP_YM1  0x01
#define OP_YM2  0x02
#define OP_WAIT 0x03
#define OP_END  0xFF

static void music_step(void)
{
#if MUSIC_BYTES > 1
    u8 op;

    if (music_wait) {
        music_wait--;
        return;
    }
    for (;;) {
        op = *music_at++;
        if (op == OP_END) {
            music_at = md_music;        /* se terminó: de nuevo desde arriba */
            continue;
        }
        if (op == OP_WAIT) {
            music_wait = *music_at++;
            if (music_wait) {
                music_wait--;
                return;
            }
            continue;
        }
        if (op == OP_PSG) {
            PSG_PORT = *music_at++;
        } else {
            u8 reg = *music_at++;
            ym_write(op == OP_YM1 ? 1 : 2, reg, *music_at++);
        }
    }
#endif
}

/* El stream se generó a 60 cuadros por segundo. En PAL hay 50, así que se
 * avanza 1.2 pasos por cuadro para que la música dure lo mismo. */
#define MUSIC_STEP_NTSC 256
#define MUSIC_STEP_PAL  307

static void music_update(u16 step)
{
    music_accum += step;
    while (music_accum >= 256) {
        music_accum -= 256;
        music_step();
    }
}

/* Los deltas de cada dirección, en el orden de las filas del CharSet. */
static const s16 dir_dx[4] = {  0, 1, 0, -1 };
static const s16 dir_dy[4] = { -1, 0, 1,  0 };

/* Por qué lado se sale del tile de origen, y por cuál se entra al destino. */
static const u8 leave_bit[4] = { PASS_UP, PASS_RIGHT, PASS_DOWN, PASS_LEFT };
static const u8 enter_bit[4] = { PASS_DOWN, PASS_LEFT, PASS_UP, PASS_RIGHT };

/* Un evento le tapa el paso al héroe si su página está en la capa "same", que
 * es la del héroe. Los de capa "below" —alfombras, marcas en el piso— y los de
 * "above" no. */
static u8 npc_blocks(s16 tx, s16 ty)
{
#if NPC_BLOCKS
    u16 i;
    for (i = 0; i < NPC_BLOCKS; i++)
        if (md_npc_blocks[i][0] == tx && md_npc_blocks[i][1] == ty)
            return 1;
#else
    (void)tx; (void)ty;
#endif
    return 0;
}

static u8 can_step(s16 tx, s16 ty, s16 nx, s16 ny, u8 dir)
{
    if (nx < 0 || ny < 0 || nx >= MAP_TILES_W || ny >= MAP_TILES_H)
        return 0;
    if (npc_blocks(nx, ny))
        return 0;
    if (!(md_passable[(u32)ty * MAP_TILES_W + (u32)tx] & leave_bit[dir]))
        return 0;
    if (!(md_passable[(u32)ny * MAP_TILES_W + (u32)nx] & enter_bit[dir]))
        return 0;
    return 1;
}

int main(void)
{
    /* En PAL entran 240 renglones; en NTSC, 224. */
    u8 pal = (VERSION_REG & 0x40) != 0;
    s16 screen_h = pal ? 240 : 224;
    s16 max_cam_x = WORLD_W - SCREEN_W;
    s16 max_cam_y = (s16)(WORLD_H - screen_h);

    /* El tile destino: se fija apenas arranca el paso, como en RM2k. */
    s16 hero_tx = HERO_START_TX;
    s16 hero_ty = HERO_START_TY;
    s16 hero_step = 0;              /* lo que falta para llegar, 256 a 0 */
    u8 facing = FACE_DOWN;
    u8 anim_frame = 1;              /* la del medio es la pose parada */
    u8 anim_count = 0;
    u8 walking = 0;

    s16 hero_x, hero_y, cam_x, cam_y;
    u8 pad, column;

    vdp_init();
    vram_clear();
    load_palette();
    load_tiles();
    PAD1_CTRL = 0x40;    /* TH como salida, el resto entradas */
    music_start();

    hero_x = (s16)(hero_tx * 16);
    hero_y = (s16)(hero_ty * 16);
    cam_x = clamp((s16)(hero_x + 8 - SCREEN_W / 2), max_cam_x);
    cam_y = clamp((s16)(hero_y + 8 - screen_h / 2), max_cam_y);
    fill_plane((s16)(cam_x >> 3), (s16)(cam_y >> 3));
    set_scroll(cam_x, cam_y);

    /* Recién ahora se prende el display, así no se ve la VRAM sin inicializar
     * mientras se carga. 0x4C = V30 (240 renglones), 0x44 = V28 (224). */
    vdp_wait_fifo();
    vdp_reg(1, pal ? 0x4C : 0x44);

    for (;;) {
        /* --- dónde está el personaje ----------------------------------- */
        hero_x = (s16)(hero_tx * 16 - dir_dx[facing] * (hero_step >> 4));
        hero_y = (s16)(hero_ty * 16 - dir_dy[facing] * (hero_step >> 4));

        cam_x = clamp((s16)(hero_x + 8 - SCREEN_W / 2), max_cam_x);
        cam_y = clamp((s16)(hero_y + 8 - screen_h / 2), max_cam_y);

        /* La caminata son cuatro fases sobre tres columnas: 0, 1, 2, 1. */
        column = (u8)(anim_frame == 3 ? 1 : anim_frame);

        wait_vblank();
        music_update(pal ? MUSIC_STEP_PAL : MUSIC_STEP_NTSC);
        /* Primero se pone al día el plano y después se mueve el scroll, así no
         * llega a verse una columna que todavía no se dibujó. */
        stream_to((s16)(cam_x >> 3), (s16)(cam_y >> 3));
        set_scroll(cam_x, cam_y);
        draw_sprites(cam_x, cam_y, screen_h,
                     (s16)(hero_x + SPRITE_OFFSET_X),
                     (s16)(hero_y + SPRITE_OFFSET_Y),
                     (u16)((SPRITE_PALETTE << 13) | (SPRITE_TILE_BASE
                           + (facing * 3 + column) * SPRITE_POSE_TILES)));

        /* --- y para dónde va ------------------------------------------- */
        if (hero_step <= 0) {
            s16 dx = 0, dy = 0;

            /* Como en RM2k, una dirección por vez: nada de diagonales. */
            pad = read_pad();
            if (pad & BTN_LEFT) {
                facing = FACE_LEFT;  dx = -1;
            } else if (pad & BTN_RIGHT) {
                facing = FACE_RIGHT; dx = 1;
            } else if (pad & BTN_UP) {
                facing = FACE_UP;    dy = -1;
            } else if (pad & BTN_DOWN) {
                facing = FACE_DOWN;  dy = 1;
            }

            walking = (u8)(dx || dy);
            if (walking) {
                s16 nx = (s16)(hero_tx + dx);
                s16 ny = (s16)(hero_ty + dy);
                if (can_step(hero_tx, hero_ty, nx, ny, facing)) {
                    hero_tx = nx;
                    hero_ty = ny;
                    hero_step = TILE_UNITS;
                }
            } else {
                anim_frame = 1;     /* quieto: la pose del medio */
                anim_count = 0;
            }
        }

        if (hero_step > 0) {
            hero_step -= MOVE_STEP;
            if (hero_step < 0)
                hero_step = 0;
        }

        /* La animación depende de si se está caminando, no de si se avanza:
         * contra un borde el personaje sigue moviendo las piernas, como en
         * RM2k. */
        if (walking && ++anim_count >= ANIM_PERIOD) {
            anim_count = 0;
            anim_frame = (u8)((anim_frame + 1) & 3);
        }
    }
}
