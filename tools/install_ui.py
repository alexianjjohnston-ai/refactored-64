#!/usr/bin/env python3
"""Install a UI composed only from original SM64 and GoldenEye UI elements."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from goldeneye_ui_assets import read_bank_gothic_asset
from sm64_assets import read_sm64_hud_asset

MARKER="// MARIO_GOLDENEYE_ORIGINAL_UI_V1"
BACKUP="ui-backup"


def c_bytes(data:bytes,indent="    "):
    lines=[]
    for offset in range(0,len(data),24):
        lines.append(indent+", ".join(f"0x{value:02x}" for value in data[offset:offset+24]))
    return ",\n".join(lines)


def header_source():
    return r'''#pragma once
#include "../src/libsm64.h"

#ifdef __cplusplus
extern "C" {
#endif

void mario_goldeneye_ui_handle_input(int pauseDown, int leftDown, int rightDown);
int mario_goldeneye_ui_paused(void);
void mario_goldeneye_ui_draw_gl20(const struct SM64MarioState *marioState);

#ifdef __cplusplus
}
#endif
'''


def source(hud,font):
    digit_rows=",\n".join(
        "    {\n"+c_bytes(hud[f"digit-{i}"],"        ")+"\n    }"
        for i in range(10)
    )
    power_rows=",\n".join(
        "    {\n"+c_bytes(hud[f"power-{i}"],"        ")+"\n    }"
        for i in range(1,9)
    )

    font_pixels=bytearray()
    glyph_rows=[]
    for glyph in font["glyphs"]:
        offset=len(font_pixels)
        font_pixels.extend(glyph["pixels"])
        glyph_rows.append(
            "    {%d,%d,%d,%d,%d,%d,%d}"
            % (
                offset,glyph["width"],glyph["padded_width"],glyph["height"],
                glyph["baseline"],glyph["kerning_index"],glyph["ascii"]
            )
        )
    kerning=", ".join(str(value) for value in font["kerning"])

    template=r'''#ifdef __APPLE__
#include <OpenGL/gl.h>
#else
#include <GL/glew.h>
#endif

#include <stdio.h>
#include <string.h>

#include "mario_goldeneye_ui.h"
#include "coins.h"
#include "goldeneye_intro.h"

#define REF_W 320.0f
#define REF_H 240.0f
#define GE_FONT_FIRST 0x21
#define GE_FONT_COUNT 94

struct GeGlyph {
    int pixelOffset;
    int width;
    int paddedWidth;
    int height;
    int baseline;
    int kerningIndex;
    int ascii;
};

static const unsigned char gDigits[10][16*16*4]={
__DIGITS__
};
static const unsigned char gMultiply[16*16*4]={
__MULTIPLY__
};
static const unsigned char gCoinIcon[16*16*4]={
__COIN__
};
static const unsigned char gStarIcon[16*16*4]={
__STAR__
};
static const unsigned char gPowerLeft[32*64*4]={
__POWER_LEFT__
};
static const unsigned char gPowerRight[32*64*4]={
__POWER_RIGHT__
};
static const unsigned char gPowerHealth[8][32*32*4]={
__POWER_HEALTH__
};

static const int gGeKerning[169]={
__KERNING__
};
static const struct GeGlyph gGeGlyphs[GE_FONT_COUNT]={
__GLYPHS__
};
static const unsigned char gGePixels[]={
__GE_PIXELS__
};

static GLuint gDigitsTex[10]={0};
static GLuint gMultiplyTex=0;
static GLuint gCoinTex=0;
static GLuint gStarTex=0;
static GLuint gPowerLeftTex=0;
static GLuint gPowerRightTex=0;
static GLuint gPowerHealthTex[8]={0};
static GLuint gGeGlyphTex[GE_FONT_COUNT]={0};
static int gTexturesReady=0;
static int gPaused=0;
static int gPage=0;
static int gPrevPause=0;
static int gPrevLeft=0;
static int gPrevRight=0;
static float gScaleX=1.0f;
static float gScaleY=1.0f;

static void upload_rgba(GLuint *texture,int width,int height,const unsigned char *pixels)
{
    glGenTextures(1,texture);
    glBindTexture(GL_TEXTURE_2D,*texture);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);
}

static void ensure_textures(void)
{
    if(gTexturesReady) return;
    for(int i=0;i<10;i++) upload_rgba(&gDigitsTex[i],16,16,gDigits[i]);
    upload_rgba(&gMultiplyTex,16,16,gMultiply);
    upload_rgba(&gCoinTex,16,16,gCoinIcon);
    upload_rgba(&gStarTex,16,16,gStarIcon);
    upload_rgba(&gPowerLeftTex,32,64,gPowerLeft);
    upload_rgba(&gPowerRightTex,32,64,gPowerRight);
    for(int i=0;i<8;i++) upload_rgba(&gPowerHealthTex[i],32,32,gPowerHealth[i]);

    glGenTextures(GE_FONT_COUNT,gGeGlyphTex);
    for(int i=0;i<GE_FONT_COUNT;i++){
        const struct GeGlyph *glyph=&gGeGlyphs[i];
        glBindTexture(GL_TEXTURE_2D,gGeGlyphTex[i]);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
        glTexImage2D(
            GL_TEXTURE_2D,0,GL_ALPHA,
            glyph->paddedWidth,glyph->height,0,
            GL_ALPHA,GL_UNSIGNED_BYTE,gGePixels+glyph->pixelOffset
        );
    }
    gTexturesReady=1;
}

static void begin_2d(void)
{
    GLint viewport[4];
    glGetIntegerv(GL_VIEWPORT,viewport);
    gScaleX=(float)viewport[2]/REF_W;
    gScaleY=(float)viewport[3]/REF_H;

    glPushAttrib(GL_ENABLE_BIT|GL_CURRENT_BIT|GL_TEXTURE_BIT|GL_COLOR_BUFFER_BIT|GL_TRANSFORM_BIT);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_LIGHTING);
    glDisable(GL_CULL_FACE);
    glEnable(GL_TEXTURE_2D);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_MODULATE);

    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0.0,viewport[2],viewport[3],0.0,-1.0,1.0);
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();
}

static void end_2d(void)
{
    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glPopAttrib();
    glMatrixMode(GL_MODELVIEW);
}

static void quad(GLuint texture,float x,float y,float w,float h,float umax)
{
    float x0=x*gScaleX, y0=y*gScaleY;
    float x1=(x+w)*gScaleX, y1=(y+h)*gScaleY;
    glBindTexture(GL_TEXTURE_2D,texture);
    glBegin(GL_QUADS);
    glTexCoord2f(0.0f,0.0f); glVertex2f(x0,y0);
    glTexCoord2f(umax,0.0f); glVertex2f(x1,y0);
    glTexCoord2f(umax,1.0f); glVertex2f(x1,y1);
    glTexCoord2f(0.0f,1.0f); glVertex2f(x0,y1);
    glEnd();
}

static void draw_integer(int value,float x,float y)
{
    char buffer[16];
    snprintf(buffer,sizeof(buffer),"%d",value);
    for(int i=0;buffer[i];i++){
        int digit=buffer[i]-'0';
        if(digit>=0 && digit<=9) quad(gDigitsTex[digit],x+i*12.0f,y,16.0f,16.0f,1.0f);
    }
}

static void draw_sm64_hud(const struct SM64MarioState *state)
{
    glColor4ub(255,255,255,255);

    // Original US SM64 HUD: print_text(168,209,"+"), 184 "*", value at 198.
    // print.c converts y to 224-y, giving a top screen coordinate of 15.
    quad(gCoinTex,168.0f,15.0f,16.0f,16.0f,1.0f);
    quad(gMultiplyTex,184.0f,15.0f,16.0f,16.0f,1.0f);
    draw_integer(mario_goldeneye_coin_value(),198.0f,15.0f);

    // US HUD_STARS_X=78 -> right-edge position 242, then X at 258, count at 272.
    quad(gStarTex,242.0f,15.0f,16.0f,16.0f,1.0f);
    quad(gMultiplyTex,258.0f,15.0f,16.0f,16.0f,1.0f);
    draw_integer(mario_goldeneye_stars(),272.0f,15.0f);

    int wedges=(state->health>>8)&0x0f;
    if(wedges<1) wedges=1;
    if(wedges>8) wedges=8;
    if(wedges<8){
        // Original meter center is (140,166) in SM64's bottom-origin HUD space.
        // The 64x64 base therefore begins at top-left reference (108,42).
        quad(gPowerLeftTex,108.0f,42.0f,32.0f,64.0f,1.0f);
        quad(gPowerRightTex,140.0f,42.0f,32.0f,64.0f,1.0f);
        quad(gPowerHealthTex[wedges-1],124.0f,58.0f,32.0f,32.0f,1.0f);
    }
}

static float ge_text_width(const char *text)
{
    float x=0.0f;
    int prev='H';
    for(const unsigned char *p=(const unsigned char *)text;*p;p++){
        if(*p==' '){ x+=5.0f; prev='H'; continue; }
        if(*p=='\n'){ break; }
        if(*p<0x21 || *p>0x7e) continue;
        const struct GeGlyph *glyph=&gGeGlyphs[*p-GE_FONT_FIRST];
        const struct GeGlyph *previous=&gGeGlyphs[prev-GE_FONT_FIRST];
        int kern=gGeKerning[previous->kerningIndex*13+glyph->kerningIndex];
        x-=(float)(kern-1);
        x+=(float)glyph->width;
        prev=*p;
    }
    return x;
}

static void ge_color(unsigned int rgba)
{
    glColor4ub(
        (rgba>>24)&0xff,(rgba>>16)&0xff,(rgba>>8)&0xff,rgba&0xff
    );
}

static void ge_text(float x,float y,const char *text,unsigned int rgba)
{
    float start=x;
    int prev='H';
    ge_color(rgba);

    for(const unsigned char *p=(const unsigned char *)text;*p;p++){
        if(*p==' '){ x+=5.0f; prev='H'; continue; }
        if(*p=='\n'){ y+=12.0f; x=start; prev='H'; continue; }
        if(*p<0x21 || *p>0x7e) continue;

        int slot=*p-GE_FONT_FIRST;
        const struct GeGlyph *glyph=&gGeGlyphs[slot];
        const struct GeGlyph *previous=&gGeGlyphs[prev-GE_FONT_FIRST];
        int kern=gGeKerning[previous->kerningIndex*13+glyph->kerningIndex];
        x-=(float)(kern-1);

        float drawY=y+(float)glyph->baseline;
        float umax=(float)glyph->width/(float)glyph->paddedWidth;
        quad(gGeGlyphTex[slot],x,drawY,(float)glyph->width,(float)glyph->height,umax);
        x+=(float)glyph->width;
        prev=*p;
    }
}

static void ge_menu_box(float x0,float y0,float x1,float y1)
{
    // GoldenEye's watch/inventory renderer uses primitive black rectangles
    // behind selectable text. This is that original UI element, without a
    // fabricated watch casing.
    glDisable(GL_TEXTURE_2D);
    glColor4ub(0,0,0,128);
    glBegin(GL_QUADS);
    glVertex2f(x0*gScaleX,y0*gScaleY);
    glVertex2f(x1*gScaleX,y0*gScaleY);
    glVertex2f(x1*gScaleX,y1*gScaleY);
    glVertex2f(x0*gScaleX,y1*gScaleY);
    glEnd();
    glEnable(GL_TEXTURE_2D);
}

static void draw_status_page(void)
{
    const unsigned int GE_GREEN=0x00ff00b0u;
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;

    ge_menu_box(72.0f,40.0f,252.0f,92.0f);
    ge_text(101.0f,49.0f,"q watch v2.01 beta",GE_GREEN);

    const char *label="mission status:";
    ge_text(81.0f,65.0f,label,GE_GREEN);
    float x=81.0f+ge_text_width(label)+4.0f;
    ge_text(
        x,65.0f,
        mario_goldeneye_stars()>=3 ? "complete" : "incomplete",
        mario_goldeneye_stars()>=3 ? GE_GREEN : GE_LIGHT_GREEN
    );
}

static void objective_line(float y,const char *label,int complete)
{
    const unsigned int GE_GREEN=0x00ff00b0u;
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;
    ge_text(60.0f,y,label,complete?GE_LIGHT_GREEN:GE_GREEN);
    ge_text(205.0f,y,complete?"complete":"incomplete",complete?GE_LIGHT_GREEN:GE_GREEN);
}

static void draw_objectives_page(void)
{
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;
    ge_menu_box(52.0f,31.0f,270.0f,128.0f);
    ge_text(60.0f,38.0f,"1. mission objectives",GE_LIGHT_GREEN);
    objective_line(60.0f,"8 red coins",mario_goldeneye_star_collected(0));
    objective_line(76.0f,"100 coins",mario_goldeneye_star_collected(1));
    objective_line(92.0f,"exploration",mario_goldeneye_star_collected(2));
    ge_text(60.0f,112.0f,"[ / ]  page",0x00ff00b0u);
}

void mario_goldeneye_ui_handle_input(int pauseDown,int leftDown,int rightDown)
{
    if(goldeneye_intro_active()){
        gPrevPause=pauseDown; gPrevLeft=leftDown; gPrevRight=rightDown;
        return;
    }
    if(pauseDown && !gPrevPause) gPaused=!gPaused;
    if(gPaused){
        if(leftDown && !gPrevLeft) gPage=(gPage+1)%2;
        if(rightDown && !gPrevRight) gPage=(gPage+1)%2;
    }
    gPrevPause=pauseDown; gPrevLeft=leftDown; gPrevRight=rightDown;
}

int mario_goldeneye_ui_paused(void){ return gPaused; }

void mario_goldeneye_ui_draw_gl20(const struct SM64MarioState *marioState)
{
    if(goldeneye_intro_active()) return;
    ensure_textures();
    begin_2d();
    if(gPaused){
        if(gPage==0) draw_status_page();
        else draw_objectives_page();
    }else{
        draw_sm64_hud(marioState);
    }
    end_2d();
}
'''
    return (template
        .replace("__DIGITS__",digit_rows)
        .replace("__MULTIPLY__",c_bytes(hud["multiply"]))
        .replace("__COIN__",c_bytes(hud["coin"]))
        .replace("__STAR__",c_bytes(hud["star"]))
        .replace("__POWER_LEFT__",c_bytes(hud["power-left"]))
        .replace("__POWER_RIGHT__",c_bytes(hud["power-right"]))
        .replace("__POWER_HEALTH__",power_rows)
        .replace("__KERNING__",kerning)
        .replace("__GLYPHS__",",\n".join(glyph_rows))
        .replace("__GE_PIXELS__",c_bytes(bytes(font_pixels)))
    )


def patch_main(source):
    if MARKER in source:
        return source

    include_anchor='#include "goldeneye_intro.h"'
    variables_anchor="        float x_axis, y_axis, x0_axis;"
    keyboard_anchor="            const Uint8* state = SDL_GetKeyboardState(NULL);"
    controller_anchor=(
        "            marioInputs.buttonZ = SDL_GameControllerGetButton( "
        "controller, SDL_CONTROLLER_BUTTON_LEFTSHOULDER );"
    )
    rotation_anchor="        cameraRot += x0_axis * dt * 2;"
    tick_anchor=(
        "            sm64_mario_tick( marioId, &marioInputs, "
        "&marioState, &marioGeometry );"
    )
    coin_tick="            mario_goldeneye_coins_tick(marioId, marioState.position);"
    coin_draw=(
        "#ifndef GL33_CORE\n"
        "        mario_goldeneye_coins_draw_gl20();\n"
        "#endif"
    )

    for anchor,name in (
        (include_anchor,"intro include"),
        (variables_anchor,"input variables"),
        (keyboard_anchor,"keyboard state"),
        (controller_anchor,"controller buttons"),
        (rotation_anchor,"camera rotation"),
        (tick_anchor,"Mario tick"),
        (coin_tick,"collectible tick"),
        (coin_draw,"collectible draw"),
    ):
        if source.count(anchor)!=1:
            raise ValueError(f"Could not find unique {name} anchor for original UI")

    source=source.replace(
        include_anchor,
        include_anchor+'\n#include "mario_goldeneye_ui.h"\n'+MARKER,
        1,
    )
    source=source.replace(
        variables_anchor,
        variables_anchor+"\n        int uiPauseDown = 0, uiLeftDown = 0, uiRightDown = 0;",
        1,
    )
    source=source.replace(
        keyboard_anchor,
        keyboard_anchor+
        "\n            uiPauseDown = state[SDL_SCANCODE_RETURN] || state[SDL_SCANCODE_ESCAPE];"
        "\n            uiLeftDown = state[SDL_SCANCODE_LEFTBRACKET];"
        "\n            uiRightDown = state[SDL_SCANCODE_RIGHTBRACKET];",
        1,
    )
    source=source.replace(
        controller_anchor,
        controller_anchor+
        "\n            uiPauseDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_START);"
        "\n            uiLeftDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_LEFT);"
        "\n            uiRightDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);",
        1,
    )
    source=source.replace(
        rotation_anchor,
        "        mario_goldeneye_ui_handle_input(uiPauseDown, uiLeftDown, uiRightDown);"
        "\n        if (mario_goldeneye_ui_paused()) {"
        "\n            x_axis = 0.0f; y_axis = 0.0f; x0_axis = 0.0f;"
        "\n            marioInputs.buttonA = 0; marioInputs.buttonB = 0; marioInputs.buttonZ = 0;"
        "\n        }"
        "\n\n"+rotation_anchor,
        1,
    )
    source=source.replace(
        tick_anchor,
        "            if (!mario_goldeneye_ui_paused()) "
        "sm64_mario_tick( marioId, &marioInputs, &marioState, &marioGeometry );",
        1,
    )
    source=source.replace(
        coin_tick,
        "            if (!mario_goldeneye_ui_paused()) "
        "mario_goldeneye_coins_tick(marioId, marioState.position);",
        1,
    )
    source=source.replace(
        coin_draw,
        coin_draw+
        "\n#ifndef GL33_CORE\n"
        "        mario_goldeneye_ui_draw_gl20(&marioState);\n"
        "#endif",
        1,
    )
    return source


def patch_makefile(source):
    object_line="TEST_OBJS += $(BUILD_DIR)/test/mario_goldeneye_ui.o"
    dependency_line="$(TEST_FILE): $(BUILD_DIR)/test/mario_goldeneye_ui.o"
    additions=[]
    if object_line not in source: additions.append(object_line)
    if dependency_line not in source: additions.append(dependency_line)
    if not additions: return source
    suffix="" if source.endswith("\n") else "\n"
    marker="" if "# MARIO_GOLDENEYE_ORIGINAL_UI_V1" in source else "\n# MARIO_GOLDENEYE_ORIGINAL_UI_V1\n"
    return source+suffix+marker+"\n".join(additions)+"\n"


def install(root:Path,sm64_assets:Path,goldeneye_assets:Path):
    main=root/"test/main.cpp"
    makefile=root/"Makefile"
    if not main.is_file() or not makefile.is_file():
        raise ValueError("libsm64 prototype checkout was not found")

    hud=read_sm64_hud_asset(sm64_assets)
    font=read_bank_gothic_asset(goldeneye_assets)

    main_source=main.read_text(encoding="utf-8")
    make_source=makefile.read_text(encoding="utf-8")
    patched_main=patch_main(main_source)
    patched_make=patch_makefile(make_source)

    backup=root/BACKUP
    first_install=MARKER not in main_source
    if first_install:
        if backup.exists():
            raise ValueError("ui-backup exists but UI marker is absent; refusing to overwrite")
        backup.mkdir()
        shutil.copy2(main,backup/"main.cpp")
        shutil.copy2(makefile,backup/"Makefile")

    (root/"test/mario_goldeneye_ui.h").write_text(header_source(),encoding="utf-8")
    (root/"test/mario_goldeneye_ui.c").write_text(source(hud,font),encoding="utf-8")
    main.write_text(patched_main,encoding="utf-8")
    makefile.write_text(patched_make,encoding="utf-8")

    backup.mkdir(exist_ok=True)
    state={
        "version":1,
        "sm64_elements":["HUD digits","multiply","coin icon","star icon","POWER meter"],
        "goldeneye_elements":["Bank Gothic","q watch v2.01 beta","mission status","watch menu colors/positions"],
        "fabricated_ui_art":False,
        "main_sha256":hashlib.sha256(main.read_bytes()).hexdigest(),
        "makefile_sha256":hashlib.sha256(makefile.read_bytes()).hexdigest(),
    }
    (backup/"state.json").write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
    print("Original UI merge ready: SM64 HUD + GoldenEye Bank Gothic watch elements.")
    print("Pause: Return/Escape or controller Start. [ and ] / D-pad left-right switch watch pages.")
    print("No imitation UI artwork was generated; all visual assets come from the local ROMs.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64",type=Path,required=True)
    parser.add_argument("--sm64-assets",type=Path,required=True)
    parser.add_argument("--goldeneye-assets",type=Path,required=True)
    args=parser.parse_args()
    install(
        args.libsm64.expanduser().resolve(),
        args.sm64_assets.expanduser().resolve(),
        args.goldeneye_assets.expanduser().resolve(),
    )
