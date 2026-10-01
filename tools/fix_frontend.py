#!/usr/bin/env python3
"""Post-install frontend repair for mission select, intro gating, pause, and GL state.

The existing installers generate intro/UI/collectible C from local ROM assets. This
step keeps those installers intact and applies a small deterministic patch to the
local libsm64 checkout before build.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "FRONTEND_REPAIR_V1"


def replace_once(source: str, old: str, new: str, name: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Could not find unique {name}; found {count}")
    return source.replace(old, new, 1)


def replace_range(source: str, start: str, end: str, new: str, name: str) -> str:
    start_index = source.find(start)
    if start_index < 0:
        raise ValueError(f"Could not find start of {name}")
    end_index = source.find(end, start_index)
    if end_index < 0:
        raise ValueError(f"Could not find end of {name}")
    return source[:start_index] + new + source[end_index:]


def patch_intro_header(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "goldeneye_intro_start" in source:
        return
    source = replace_once(
        source,
        "void goldeneye_intro_init(void);\n",
        "void goldeneye_intro_init(void);\nvoid goldeneye_intro_start(void);\n",
        "intro start declaration",
    )
    path.write_text(source, encoding="utf-8")


def patch_intro_source(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if MARKER not in source:
        source = replace_once(
            source,
            "enum GoldenEyeIntroPhase {\n    GE_INTRO_FIXED = 0,\n",
            "enum GoldenEyeIntroPhase {\n    GE_INTRO_WAIT = -1,\n    GE_INTRO_FIXED = 0,\n",
            "intro wait phase",
        )
        source = replace_once(
            source,
            "void goldeneye_intro_init(void)\n{\n    unsigned int seed = (unsigned int)time(NULL);\n    gPhase = GE_INTRO_FIXED;\n",
            "void goldeneye_intro_init(void)\n{\n    unsigned int seed = (unsigned int)time(NULL);\n    gPhase = GE_INTRO_WAIT;\n",
            "intro init gate",
        )
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
        source = source.replace("#include \"goldeneye_intro.h\"\n", "#include \"goldeneye_intro.h\"\n// FRONTEND_REPAIR_V1\n", 1)
    path.write_text(source, encoding="utf-8")


def patch_main(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    replacements = {
        "uiPauseDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_START);":
            "uiPauseDown = uiPauseDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_START);",
        "uiLeftDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_LEFT);":
            "uiLeftDown = uiLeftDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_LEFT);",
        "uiRightDown = SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);":
            "uiRightDown = uiRightDown || SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT);",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    path.write_text(source, encoding="utf-8")


def patch_collectible_gl(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "COIN_GL_STATE_FRONTEND_REPAIR_V1" not in source:
        source = source.replace(
            "    glPushAttrib(\n        GL_ENABLE_BIT | GL_CURRENT_BIT | GL_TEXTURE_BIT |\n        GL_COLOR_BUFFER_BIT | GL_LIGHTING_BIT | GL_TRANSFORM_BIT\n    );",
            "    // COIN_GL_STATE_FRONTEND_REPAIR_V1\n    glPushAttrib(GL_ALL_ATTRIB_BITS);\n    glMatrixMode(GL_TEXTURE);\n    glPushMatrix();\n    glLoadIdentity();\n    glMatrixMode(GL_MODELVIEW);",
            1,
        )
        source = source.replace(
            "    glPopAttrib();\n    glMatrixMode(previousMatrixMode);",
            "    glMatrixMode(GL_TEXTURE);\n    glPopMatrix();\n    glPopAttrib();\n    glMatrixMode(previousMatrixMode);",
            1,
        )
    path.write_text(source, encoding="utf-8")


def patch_ui(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "UI_FRONTEND_REPAIR_V1" in source:
        return

    source = source.replace(
        "static int gTexturesReady=0;\nstatic int gPaused=0;",
        "static int gTexturesReady=0;\n// UI_FRONTEND_REPAIR_V1\nenum UiMode { UI_MODE_MISSION_SELECT = 0, UI_MODE_GAME = 1 };\nstatic int gMode=UI_MODE_MISSION_SELECT;\nstatic GLint gPreviousMatrixMode=GL_MODELVIEW;\nstatic int gPaused=0;",
        1,
    )
    source = source.replace(
        "    glPushAttrib(GL_ENABLE_BIT|GL_CURRENT_BIT|GL_TEXTURE_BIT|GL_COLOR_BUFFER_BIT|GL_TRANSFORM_BIT);",
        "    glGetIntegerv(GL_MATRIX_MODE,&gPreviousMatrixMode);\n    glPushAttrib(GL_ALL_ATTRIB_BITS);\n    glMatrixMode(GL_TEXTURE);\n    glPushMatrix();\n    glLoadIdentity();",
        1,
    )
    source = source.replace(
        "    glPopAttrib();\n    glMatrixMode(GL_MODELVIEW);",
        "    glMatrixMode(GL_TEXTURE);\n    glPopMatrix();\n    glPopAttrib();\n    glMatrixMode(gPreviousMatrixMode);",
        1,
    )

    insert_before = "void mario_goldeneye_ui_handle_input"
    menu_functions = r'''
static void draw_mission_select_page(void)
{
    const unsigned int GE_GREEN=0x00ff00b0u;
    const unsigned int GE_LIGHT_GREEN=0xa0ffa0f0u;
    ge_menu_box(38.0f,26.0f,282.0f,151.0f);
    ge_text(52.0f,36.0f,"select mission",GE_LIGHT_GREEN);
    ge_text(58.0f,58.0f,"> mission 1: dam",GE_GREEN);
    ge_text(76.0f,75.0f,"mario as bond",GE_LIGHT_GREEN);
    ge_text(58.0f,99.0f,"stars: 0 / 3",GE_GREEN);
    ge_text(58.0f,116.0f,"agent",GE_GREEN);
    ge_text(58.0f,136.0f,"return/start to begin",GE_LIGHT_GREEN);
}

static void draw_intro_overlay(void)
{
    ge_menu_box(52.0f,178.0f,270.0f,220.0f);
    ge_text(62.0f,187.0f,"mario is bond",0xa0ffa0f0u);
    ge_text(62.0f,203.0f,"a / b / z skips intro",0x00ff00b0u);
}

'''
    source = source.replace(insert_before, menu_functions + insert_before, 1)

    handle_start = "void mario_goldeneye_ui_handle_input"
    paused_start = "int mario_goldeneye_ui_paused"
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
    source = replace_range(source, handle_start, paused_start, new_handle, "UI input handler")
    source = source.replace(
        "int mario_goldeneye_ui_paused(void){ return gPaused; }",
        "int mario_goldeneye_ui_paused(void){ return gPaused || gMode==UI_MODE_MISSION_SELECT; }",
        1,
    )

    draw_start = "void mario_goldeneye_ui_draw_gl20"
    source = replace_range(
        source,
        draw_start,
        "}\n'''\n    return (template",
        r'''void mario_goldeneye_ui_draw_gl20(const struct SM64MarioState *marioState)
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
''',
        "UI draw function",
    )
    source += "}\n'''\n    return (template" if not source.endswith("}\n'''\n    return (template") and "return (template" not in source[-200:] else ""
    # The range replacement removes the delimiter; restore it if the conservative
    # guard above was not needed. Simpler safe fix:
    if "return (template" not in source:
        raise ValueError("UI template return was damaged")
    path.write_text(source, encoding="utf-8")


def install(root: Path) -> None:
    test = root / "test"
    patch_intro_header(test / "goldeneye_intro.h")
    patch_intro_source(test / "goldeneye_intro.c")
    patch_ui(test / "mario_goldeneye_ui.c")
    patch_collectible_gl(test / "coins.c")
    patch_main(test / "main.cpp")
    print("Frontend repair ready: mission select gates intro, pause input fixed, GL state isolated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libsm64", type=Path, required=True)
    args = parser.parse_args()
    install(args.libsm64.expanduser().resolve())
