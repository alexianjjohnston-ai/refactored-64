#!/usr/bin/env python3
"""Post-install frontend repair for the merged Mario/GoldenEye shell.

The normal installers generate C files from local ROM assets. This pass patches
those generated files before build so the run path becomes:
mission select -> GoldenEye intro -> gameplay HUD -> GoldenEye watch pause.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "FRONTEND_REPAIR_V2"


def replace_once(source: str, old: str, new: str, name: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Could not find unique {name}; found {count}")
    return source.replace(old, new, 1)


def replace_c_function(source: str, signature_start: str, replacement: str, name: str) -> str:
    """Replace a generated C function by matching its outer braces."""
    start = source.find(signature_start)
    if start < 0:
        raise ValueError(f"Could not find start of {name}")

    brace = source.find("{", start)
    if brace < 0:
        raise ValueError(f"Could not find opening brace of {name}")

    depth = 0
    index = brace
    while index < len(source):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                while end < len(source) and source[end] in " \t\r\n":
                    end += 1
                return source[:start] + replacement.strip() + "\n\n" + source[end:]
        index += 1

    raise ValueError(f"Could not find closing brace of {name}")


def insert_before_once(source: str, anchor: str, inserted: str, name: str) -> str:
    if inserted.strip() in source:
        return source
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f"Could not find unique {name}; found {count}")
    return source.replace(anchor, inserted.rstrip() + "\n\n" + anchor, 1)


def patch_intro_header(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "goldeneye_intro_start" not in source:
        source = replace_once(
            source,
            "void goldeneye_intro_init(void);\n",
            "void goldeneye_intro_init(void);\nvoid goldeneye_intro_start(void);\n",
            "intro start declaration",
        )
    path.write_text(source, encoding="utf-8")


def patch_intro_source(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "GE_INTRO_WAIT" not in source:
        source = replace_once(
            source,
            "enum GoldenEyeIntroPhase {\n    GE_INTRO_FIXED = 0,\n",
            "enum GoldenEyeIntroPhase {\n    GE_INTRO_WAIT = -1,\n    GE_INTRO_FIXED = 0,\n",
            "intro wait phase",
        )
    if "gPhase = GE_INTRO_WAIT;" not in source:
        source = replace_once(
            source,
            "void goldeneye_intro_init(void)\n{\n    unsigned int seed = (unsigned int)time(NULL);\n    gPhase = GE_INTRO_FIXED;\n",
            "void goldeneye_intro_init(void)\n{\n    unsigned int seed = (unsigned int)time(NULL);\n    gPhase = GE_INTRO_WAIT;\n",
            "intro init gate",
        )
    if "goldeneye_intro_start" not in source:
        source = replace_once(
            source,
            "int goldeneye_intro_active(void)\n{\n    return gPhase != GE_INTRO_DONE;\n}\n",
            "void goldeneye_intro_start(void)\n{\n    if (gPhase != GE_INTRO_WAIT) return;\n    gPhase = GE_INTRO_FIXED;\n    gTimer = 0.0f;\n    gSwirlIndex = 1;\n    gSkip = 0;\n    gTargetOverride = 0;\n}\n\nint goldeneye_intro_active(void)\n{\n    return gPhase != GE_INTRO_WAIT && gPhase != GE_INTRO_DONE;\n}\n",
            "intro active/start functions",
        )
    source = source.replace(
        "if (pressed) gSkip = 1;",
        "if (pressed && goldeneye_intro_active()) gSkip = 1;",
        1,
    )
    if MARKER not in source:
        source = source.replace(
            "#include \"goldeneye_intro.h\"\n",
            f"#include \"goldeneye_intro.h\"\n// {MARKER}\n",
            1,
        )
    path.write_text(source, encoding="utf-8")


def patch_ui_header(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "mario_goldeneye_ui_frontend_active" not in source:
        source = replace_once(
            source,
            "int mario_goldeneye_ui_paused(void);\n",
            "int mario_goldeneye_ui_paused(void);\nint mario_goldeneye_ui_frontend_active(void);\n",
            "frontend-active declaration",
        )
    path.write_text(source, encoding="utf-8")


def patch_main(path: Path) -> None:
    source = path.read_text(encoding="utf-8")

    for old, new in {
        "uiPauseDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_START);":
            "uiPauseDown = uiPauseDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_START);",
        "uiLeftDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_LEFT);":
            "uiLeftDown = uiLeftDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_LEFT);",
        "uiRightDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);":
            "uiRightDown = uiRightDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);",
    }.items():
        source = source.replace(old, new)

    renderer_line = "        renderer->draw( &renderState, cameraPos, &marioState, &marioGeometry );"
    renderer_wrapped = "        if (!mario_goldeneye_ui_frontend_active()) renderer->draw( &renderState, cameraPos, &marioState, &marioGeometry );"
    if renderer_wrapped not in source:
        source = replace_once(source, renderer_line, renderer_wrapped, "renderer draw frontend gate")

    coin_draw = "#ifndef GL33_CORE\n        mario_goldeneye_coins_draw_gl20();\n#endif"
    coin_draw_wrapped = "#ifndef GL33_CORE\n        if (!mario_goldeneye_ui_frontend_active()) mario_goldeneye_coins_draw_gl20();\n#endif"
    if coin_draw_wrapped not in source:
        source = replace_once(source, coin_draw, coin_draw_wrapped, "coin draw frontend gate")

    path.write_text(source, encoding="utf-8")


def patch_collectible_gl(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "COIN_GL_STATE_FRONTEND_REPAIR_V1" not in source:
        source = replace_once(
            source,
            "    glPushAttrib(\n        GL_ENABLE_BIT | GL_CURRENT_BIT | GL_TEXTURE_BIT |\n        GL_COLOR_BUFFER_BIT | GL_LIGHTING_BIT | GL_TRANSFORM_BIT\n    );",
            "    // COIN_GL_STATE_FRONTEND_REPAIR_V1\n    glPushAttrib(GL_ALL_ATTRIB_BITS);\n    glMatrixMode(GL_TEXTURE);\n    glPushMatrix();\n    glLoadIdentity();\n    glMatrixMode(GL_MODELVIEW);",
            "collectible GL push state",
        )
        source = replace_once(
            source,
            "    glPopAttrib();\n    glMatrixMode(previousMatrixMode);",
            "    glMatrixMode(GL_TEXTURE);\n    glPopMatrix();\n    glPopAttrib();\n    glMatrixMode(previousMatrixMode);",
            "collectible GL pop state",
        )
    path.write_text(source, encoding="utf-8")


def patch_ui(path: Path) -> None:
    source = path.read_text(encoding="utf-8")

    if "UI_FRONTEND_REPAIR_V2" not in source:
        source = replace_once(
            source,
            "static int gTexturesReady=0;\nstatic int gPaused=0;",
            "static int gTexturesReady=0;\n// UI_FRONTEND_REPAIR_V2\nenum UiMode { UI_MODE_MISSION_SELECT = 0, UI_MODE_GAME = 1 };\nstatic int gMode=UI_MODE_MISSION_SELECT;\nstatic GLint gPreviousMatrixMode=GL_MODELVIEW;\nstatic int gPaused=0;",
            "UI mode state",
        )
        source = replace_once(
            source,
            "    glPushAttrib(GL_ENABLE_BIT|GL_CURRENT_BIT|GL_TEXTURE_BIT|GL_COLOR_BUFFER_BIT|GL_TRANSFORM_BIT);",
            "    glGetIntegerv(GL_MATRIX_MODE,&gPreviousMatrixMode);\n    glPushAttrib(GL_ALL_ATTRIB_BITS);\n    glMatrixMode(GL_TEXTURE);\n    glPushMatrix();\n    glLoadIdentity();",
            "UI GL push state",
        )
        source = replace_once(
            source,
            "    glPopAttrib();\n    glMatrixMode(GL_MODELVIEW);",
            "    glMatrixMode(GL_TEXTURE);\n    glPopMatrix();\n    glPopAttrib();\n    glMatrixMode(gPreviousMatrixMode);",
            "UI GL pop state",
        )

    menu_functions = r'''
static void ge_fullscreen_backdrop(unsigned char alpha)
{
    glDisable(GL_TEXTURE_2D);
    glColor4ub(0,0,0,alpha);
    glBegin(GL_QUADS);
    glVertex2f(0.0f,0.0f);
    glVertex2f(REF_W*gScaleX,0.0f);
    glVertex2f(REF_W*gScaleX,REF_H*gScaleY);
    glVertex2f(0.0f,REF_H*gScaleY);
    glEnd();
    glEnable(GL_TEXTURE_2D);
}

static void ge_outline_box(float x0,float y0,float x1,float y1)
{
    glDisable(GL_TEXTURE_2D);
    glColor4ub(0,0,0,178);
    glBegin(GL_QUADS);
    glVertex2f(x0*gScaleX,y0*gScaleY);
    glVertex2f(x1*gScaleX,y0*gScaleY);
    glVertex2f(x1*gScaleX,y1*gScaleY);
    glVertex2f(x0*gScaleX,y1*gScaleY);
    glEnd();
    glColor4ub(0,255,0,190);
    glBegin(GL_LINE_LOOP);
    glVertex2f(x0*gScaleX,y0*gScaleY);
    glVertex2f(x1*gScaleX,y0*gScaleY);
    glVertex2f(x1*gScaleX,y1*gScaleY);
    glVertex2f(x0*gScaleX,y1*gScaleY);
    glEnd();
    glEnable(GL_TEXTURE_2D);
}

static void draw_mission_select_page(void)
{
    const unsigned int GE_GREEN=0x00ff00d8u;
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;
    ge_fullscreen_backdrop(235);
    ge_text(38.0f,23.0f,"goldeneye 64 x super mario 64",GE_LIGHT_GREEN);
    ge_outline_box(34.0f,44.0f,286.0f,174.0f);
    ge_text(52.0f,57.0f,"select mission",GE_LIGHT_GREEN);
    ge_text(58.0f,79.0f,"> mission 1: dam",GE_GREEN);
    ge_text(76.0f,96.0f,"agent",GE_GREEN);
    ge_text(76.0f,112.0f,"3 power stars",GE_GREEN);
    ge_text(76.0f,128.0f,"mario as bond",GE_LIGHT_GREEN);
    ge_text(48.0f,190.0f,"return/start: begin    esc: pause later",GE_GREEN);
}

static void draw_intro_overlay(void)
{
    ge_outline_box(50.0f,176.0f,272.0f,222.0f);
    ge_text(62.0f,187.0f,"mario is bond",0xa0ffa0f0u);
    ge_text(62.0f,203.0f,"a / b / z skips intro",0x00ff00d8u);
}
'''
    source = insert_before_once(
        source,
        "void mario_goldeneye_ui_handle_input",
        menu_functions,
        "UI frontend page insertion",
    )

    status_page = r'''static void draw_status_page(void)
{
    const unsigned int GE_GREEN=0x00ff00d8u;
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;
    ge_fullscreen_backdrop(185);
    ge_outline_box(54.0f,35.0f,266.0f,142.0f);
    ge_text(78.0f,48.0f,"q watch v2.01 beta",GE_GREEN);
    ge_text(70.0f,68.0f,"mission:",GE_GREEN);
    ge_text(136.0f,68.0f,mario_goldeneye_stars()>=3 ? "complete" : "incomplete",GE_LIGHT_GREEN);

    char line[64];
    snprintf(line,sizeof(line),"coins: %d / 100",mario_goldeneye_coin_value());
    ge_text(70.0f,90.0f,line,GE_GREEN);
    snprintf(line,sizeof(line),"red coins: %d / 8",mario_goldeneye_red_coins());
    ge_text(70.0f,106.0f,line,GE_GREEN);
    snprintf(line,sizeof(line),"stars: %d / 3",mario_goldeneye_stars());
    ge_text(70.0f,122.0f,line,GE_LIGHT_GREEN);
}
'''
    source = replace_c_function(source, "static void draw_status_page", status_page, "watch status page")

    objectives_page = r'''static void draw_objectives_page(void)
{
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;
    ge_fullscreen_backdrop(185);
    ge_outline_box(44.0f,30.0f,276.0f,140.0f);
    ge_text(58.0f,42.0f,"mission objectives",GE_LIGHT_GREEN);
    objective_line(62.0f,"8 red coins",mario_goldeneye_star_collected(0));
    objective_line(80.0f,"100 coins",mario_goldeneye_star_collected(1));
    objective_line(98.0f,"exploration star",mario_goldeneye_star_collected(2));
    ge_text(62.0f,122.0f,"[ / ]  page",0x00ff00d8u);
}
'''
    source = replace_c_function(source, "static void draw_objectives_page", objectives_page, "watch objectives page")

    new_handle = r'''void mario_goldeneye_ui_handle_input(int pauseDown,int leftDown,int rightDown)
{
    if(gMode==UI_MODE_MISSION_SELECT){
        if(pauseDown && !gPrevPause){
            gMode=UI_MODE_GAME;
            goldeneye_intro_start();
        }
        gPrevPause=pauseDown; gPrevLeft=leftDown; gPrevRight=rightDown;
        return;
    }
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
'''
    source = replace_c_function(source, "void mario_goldeneye_ui_handle_input", new_handle, "UI input handler")

    paused_function = "int mario_goldeneye_ui_paused(void){ return gPaused || gMode==UI_MODE_MISSION_SELECT; }"
    source = replace_c_function(source, "int mario_goldeneye_ui_paused", paused_function, "UI pause predicate")
    if "mario_goldeneye_ui_frontend_active" not in source:
        source = source.replace(
            paused_function + "\n\n",
            paused_function + "\n\nint mario_goldeneye_ui_frontend_active(void){ return gMode==UI_MODE_MISSION_SELECT; }\n\n",
            1,
        )

    new_draw = r'''void mario_goldeneye_ui_draw_gl20(const struct SM64MarioState *marioState)
{
    ensure_textures();
    begin_2d();
    if(gMode==UI_MODE_MISSION_SELECT){
        draw_mission_select_page();
    }else if(goldeneye_intro_active()){
        draw_intro_overlay();
    }else if(gPaused){
        if(gPage==0) draw_status_page();
        else draw_objectives_page();
    }else{
        draw_sm64_hud(marioState);
    }
    end_2d();
}
'''
    source = replace_c_function(source, "void mario_goldeneye_ui_draw_gl20", new_draw, "UI draw function")
    path.write_text(source, encoding="utf-8")


def install(root: Path) -> None:
    test = root / "test"
    patch_intro_header(test / "goldeneye_intro.h")
    patch_intro_source(test / "goldeneye_intro.c")
    patch_ui_header(test / "mario_goldeneye_ui.h")
    patch_ui(test / "mario_goldeneye_ui.c")
    patch_collectible_gl(test / "coins.c")
    patch_main(test / "main.cpp")
    print("Frontend repair ready: mission select hides gameplay, pause works, coin/status UI is live, GL state isolated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    args = parser.parse_args()
    install(args.libsm64.expanduser().resolve())
