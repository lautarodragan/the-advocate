/* ---------------------------------------------------------------------------
 * "Hola mundo" de RPG Maker 2000 en Sega Mega Drive.
 *
 * Renderiza un mapa de tiles de 16x16 convertido de un ChipSet de RM2k,
 * dibuja un personaje de un CharSet de RM2k y lo hace caminar con la cruceta,
 * con la camara siguiendolo. Sin dialogos, sin eventos, sin audio.
 * --------------------------------------------------------------------------- */
#include "assets.h"

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef signed short   s16;

/* --- puertos ------------------------------------------------------------- */
#define VDP_DATA_W   (*(volatile u16 *)0xC00000)
#define VDP_DATA_L   (*(volatile u32 *)0xC00000)
#define VDP_CTRL_W   (*(volatile u16 *)0xC00004)
#define VDP_CTRL_L   (*(volatile u32 *)0xC00004)

#define Z80_BUSREQ   (*(volatile u16 *)0xA11100)
#define Z80_RESET    (*(volatile u16 *)0xA11200)
#define VERSION_REG  (*(volatile u8  *)0xA10001)
#define TMSS_REG     (*(volatile u32 *)0xA14000)
#define PAD1_DATA    (*(volatile u8  *)0xA10003)
#define PAD1_CTRL    (*(volatile u8  *)0xA10009)

/* --- mapa de la VRAM ----------------------------------------------------- */
#define PLANE_A      0xC000
#define PLANE_W      0xB000
#define PLANE_B      0xE000
#define SPRITE_TAB   0xF000
#define HSCROLL_TAB  0xFC00

/* tile 0 se deja en blanco, el tileset arranca en el 1 */
#define TILESET_BASE 1
#define SPRITE_BASE  (TILESET_BASE + RM2K_TILES * 4)

#define SCREEN_W     320
#define SCREEN_H     224
#define WORLD_W      (MAP_W * 16)
#define WORLD_H      (MAP_H * 16)

/* --- botones ------------------------------------------------------------- */
#define BTN_UP    0x01
#define BTN_DOWN  0x02
#define BTN_LEFT  0x04
#define BTN_RIGHT 0x08

/* --- helpers del VDP ----------------------------------------------------- */
static inline void vdp_reg(u8 r, u8 v)
{
    VDP_CTRL_W = (u16)(0x8000 | (r << 8) | v);
}

static inline void vdp_addr_vram(u16 a)
{
    VDP_CTRL_L = 0x40000000u | ((u32)(a & 0x3FFF) << 16) | ((a >> 14) & 3);
}

static inline void vdp_addr_cram(u16 a)
{
    VDP_CTRL_L = 0xC0000000u | ((u32)(a & 0x3FFF) << 16) | ((a >> 14) & 3);
}

static inline void vdp_addr_vsram(u16 a)
{
    VDP_CTRL_L = 0x40000010u | ((u32)(a & 0x3FFF) << 16) | ((a >> 14) & 3);
}

static void vdp_init(void)
{
    vdp_reg(0,  0x04);   /* modo 1: sin HINT                                */
    vdp_reg(1,  0x44);   /* modo 2: display ON, VINT OFF, V28, MODE5        */
    vdp_reg(2,  PLANE_A >> 10);
    vdp_reg(3,  PLANE_W >> 10);
    vdp_reg(4,  PLANE_B >> 13);
    vdp_reg(5,  SPRITE_TAB >> 9);
    vdp_reg(6,  0x00);
    vdp_reg(7,  0x00);   /* color de fondo: paleta 0, indice 0              */
    vdp_reg(10, 0xFF);
    vdp_reg(11, 0x00);   /* scroll de pantalla completa                     */
    vdp_reg(12, 0x81);   /* H40: 320 pixels de ancho                        */
    vdp_reg(13, HSCROLL_TAB >> 10);
    vdp_reg(15, 0x02);   /* autoincremento de 2 bytes                       */
    vdp_reg(16, 0x01);   /* tamano de plano: 64x32 celdas = 512x256 px      */
    vdp_reg(17, 0x00);
    vdp_reg(18, 0x00);
}

static void vram_clear(void)
{
    int i;
    vdp_addr_vram(0);
    for (i = 0; i < 32768; i++)
        VDP_DATA_W = 0;
}

static void load_palette(u8 slot, const u16 *pal)
{
    int i;
    vdp_addr_cram((u16)(slot << 5));
    for (i = 0; i < 16; i++)
        VDP_DATA_W = pal[i];
}

static void load_tiles(u16 first, const u32 *src, int ntiles)
{
    int i, n = ntiles << 3;
    vdp_addr_vram((u16)(first << 5));
    for (i = 0; i < n; i++)
        VDP_DATA_L = src[i];
}

/* Vuelca el mapa entero al plano A.
 * Un tile de 16x16 de RM2k = 4 celdas del VDP, guardadas en VRAM en el
 * orden TL, TR, BL, BR, asi el tile N de RM2k arranca en 4*N. */
static void draw_map(void)
{
    int my, mx;
    for (my = 0; my < MAP_H; my++) {
        /* fila de arriba del tile */
        vdp_addr_vram((u16)(PLANE_A + (((my << 1) << 6)) * 2));
        for (mx = 0; mx < MAP_W; mx++) {
            u16 base = (u16)(TILESET_BASE + (map_data[my][mx] << 2));
            VDP_DATA_W = base;
            VDP_DATA_W = (u16)(base + 1);
        }
        /* fila de abajo */
        vdp_addr_vram((u16)(PLANE_A + ((((my << 1) + 1) << 6)) * 2));
        for (mx = 0; mx < MAP_W; mx++) {
            u16 base = (u16)(TILESET_BASE + (map_data[my][mx] << 2));
            VDP_DATA_W = (u16)(base + 2);
            VDP_DATA_W = (u16)(base + 3);
        }
    }
}

/* --- joypad -------------------------------------------------------------- */
static u8 read_pad(void)
{
    u8 lo, hi;
    PAD1_DATA = 0x40;
    __asm__ volatile ("nop\n\tnop\n\tnop\n\tnop");
    lo = PAD1_DATA;              /* C B Der Izq Abajo Arriba */
    PAD1_DATA = 0x00;
    __asm__ volatile ("nop\n\tnop\n\tnop\n\tnop");
    hi = PAD1_DATA;              /* Start A */
    PAD1_DATA = 0x40;
    /* activo en bajo: se invierte todo */
    return (u8)((~lo & 0x3F) | ((~hi & 0x30) << 2));
}

static void wait_vblank(void)
{
    while (VDP_CTRL_W & 8) ;     /* salir del vblank actual */
    while (!(VDP_CTRL_W & 8)) ;  /* esperar al siguiente    */
}

/* --- estado -------------------------------------------------------------- */
static s16 player_x, player_y;   /* esquina sup-izq del sprite de 24x32 */
static s16 cam_x, cam_y;
static u8  dir;                  /* 0 abajo, 1 izq, 2 der, 3 arriba */
static u8  anim_step, anim_timer;

static const u8 WALK_CYCLE[4] = { 0, 1, 2, 1 };

static s16 clamp(s16 v, s16 lo, s16 hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static void update_sprite(void)
{
    u8  frame = WALK_CYCLE[anim_step];
    u16 tile  = (u16)(SPRITE_BASE + ((dir * 3 + frame) * SPR_TILES_FRAME));
    s16 sx = (s16)(player_x - cam_x);
    s16 sy = (s16)(player_y - cam_y);

    vdp_addr_vram(SPRITE_TAB);
    VDP_DATA_W = (u16)(sy + 128);
    /* tamano 3x4 celdas: ((3-1)<<2)|(4-1) = 0x0B ; link = 0 (fin de lista) */
    VDP_DATA_W = 0x0B00;
    VDP_DATA_W = (u16)(0x2000 | tile);   /* paleta 1 */
    VDP_DATA_W = (u16)(sx + 128);
}

static void update_scroll(void)
{
    vdp_addr_vram(HSCROLL_TAB);
    VDP_DATA_W = (u16)(-cam_x);          /* plano A */
    VDP_DATA_W = (u16)(-cam_x);          /* plano B */
    vdp_addr_vsram(0);
    VDP_DATA_W = (u16)cam_y;
    VDP_DATA_W = (u16)cam_y;
}

int main(void)
{
    u8 pad;
    int moving;

    /* TMSS: las consolas post-1990 no dejan tocar el VDP sin esto */
    if (VERSION_REG & 0x0F)
        TMSS_REG = 0x53454741;           /* 'SEGA' */

    /* dejar al Z80 quieto y con el bus tomado (todavia no hay audio) */
    Z80_BUSREQ = 0x0100;
    Z80_RESET  = 0x0100;
    while (Z80_BUSREQ & 0x0100) ;

    PAD1_CTRL = 0x40;

    vdp_init();
    vram_clear();

    load_palette(0, tileset_pal);
    load_palette(1, sprite_pal);
    load_tiles(TILESET_BASE, tileset_tiles, RM2K_TILES * 4);
    load_tiles(SPRITE_BASE,  sprite_tiles,  SPR_FRAMES * SPR_TILES_FRAME);
    draw_map();

    player_x = 40;
    player_y = 96;
    dir = 0;
    anim_step = 1;

    for (;;) {
        pad = read_pad();
        moving = 0;

        if (pad & BTN_LEFT)  { player_x -= 2; dir = 1; moving = 1; }
        else if (pad & BTN_RIGHT) { player_x += 2; dir = 2; moving = 1; }
        if (pad & BTN_UP)    { player_y -= 2; dir = 3; moving = 1; }
        else if (pad & BTN_DOWN)  { player_y += 2; dir = 0; moving = 1; }

        player_x = clamp(player_x, 0, WORLD_W - SPR_W);
        player_y = clamp(player_y, 0, WORLD_H - SPR_H);

        if (moving) {
            if (++anim_timer >= 7) {
                anim_timer = 0;
                anim_step = (u8)((anim_step + 1) & 3);
            }
        } else {
            anim_step = 1;               /* pose quieta = frame del medio */
            anim_timer = 0;
        }

        cam_x = clamp((s16)(player_x + 12 - (SCREEN_W / 2)), 0,
                      WORLD_W - SCREEN_W);
        cam_y = clamp((s16)(player_y + 16 - (SCREEN_H / 2)), 0,
                      WORLD_H - SCREEN_H);

        wait_vblank();
        update_scroll();
        update_sprite();
    }
    return 0;
}
