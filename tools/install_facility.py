#!/usr/bin/env python3
"""Install a geometry-only Mario/GoldenEye Facility prototype in libsm64.
No ROM or extracted assets are distributed. Python standard library only.
Format references: goldeneye-pc-port src/game/bg.c, tools_pc/bg_gdl_census.py.
"""
import argparse, collections, hashlib, json, math, pathlib, shutil, struct, zlib

LEVELS = {
    # ROM offsets come from the US GoldenEye asset table used by the reference
    # port. They identify the compressed background segment, not a distributed
    # asset; the user's ROM remains the only source.
    'facility': (0x630000, 'facility'),
    'dam': (0x5ffc50, 'dam'),
}

# GoldenEye background vertices are much smaller than libsm64's Mario units.
# Keep the whole level in a signed 16-bit-friendly range while making rooms
# read at a useful scale beside Mario.
WORLD_SCALE = 3.0

def extract(rom, level='facility'):
    if hashlib.sha1(rom).hexdigest() != 'abe01e4aeb033b6c0836819f549c791b26cfde83':
        raise ValueError('Expected the original US GoldenEye .z64 ROM.')
    try:
        segment_start, _ = LEVELS[level]
    except KeyError as error:
        raise ValueError(f'Unsupported GoldenEye level: {level}') from error
    data = rom[segment_start:]
    off = struct.unpack_from('>I', data, 4)[0] & 0xffffff
    rooms = []
    while off + 24 <= len(data):
        row = struct.unpack_from('>IIIfff', data, off)
        rooms.append(row)
        off += 24
        if len(rooms) > 1 and not any(row[:3]):
            break
        if len(rooms) > 256:
            raise ValueError('Invalid room table')
    tris, colors, room_ids = [], [], []
    def inflate(address):
        offset = address & 0xffffff
        if data[offset:offset+2] != b'\x11\x72':
            raise ValueError('Missing compressed room header')
        return zlib.decompressobj(-15).decompress(data[offset+2:])
    for room_id, row in enumerate(rooms[1:-2], 1):
        verts = inflate(row[0])
        if len(verts) % 16:
            raise ValueError('Misaligned vertex table')
        cache = {}
        for address in row[1:3]:
            if not address:
                continue
            gdl = inflate(address)
            for o in range(0, len(gdl)//8*8, 8):
                w0,w1 = struct.unpack_from('>II',gdl,o)
                op = w0 >> 24
                if op == 4:
                    n, start = ((w0 >> 20)&15)+1, (w0 >> 16)&15
                    vo = w1 & 0xffffff
                    if vo+n*16 > len(verts) or start+n > 16:
                        raise ValueError('Invalid vertex batch')
                    for j in range(n):
                        xyz = struct.unpack_from('>hhh', verts, vo+j*16)
                        rgb = verts[vo+j*16+12:vo+j*16+15]
                        cache[start+j] = (tuple(xyz[k]+row[k+3] for k in range(3)),tuple(v/255 for v in rgb))
                indices = []
                if op == 0xbf:
                    indices = [tuple(((w1 >> s)&255)//10 for s in (16,8,0))]
                elif op == 0xb1:
                    indices = [((w1>>(8*j))&15,(w1>>(8*j+4))&15,(w0>>(4*j))&15) for j in range(4)]
                for ix in indices:
                    if len(set(ix)) != 3:
                        continue
                    if any(i not in cache for i in ix):
                        raise ValueError('Triangle refers to unloaded vertex')
                    pts = [cache[i][0] for i in ix]
                    a = [pts[1][k]-pts[0][k] for k in range(3)]
                    b = [pts[2][k]-pts[0][k] for k in range(3)]
                    norm = (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
                    if sum(v*v for v in norm) < 1:
                        continue
                    tris.append(pts);colors.append([cache[i][1] for i in ix]);room_ids.append(room_id)
    if len(tris) < 1000:
        raise ValueError('Too few Facility triangles')
    # Choose a large horizontal interior floor with overhead clearance.
    floors = []
    for i,t in enumerate(tris):
        if max(p[1] for p in t)-min(p[1] for p in t) > 1:
            continue
        area = abs((t[1][0]-t[0][0])*(t[2][2]-t[0][2])-(t[1][2]-t[0][2])*(t[2][0]-t[0][0]))
        x,y,z = [sum(p[k] for p in t)/3 for k in range(3)]
        if area > 50000:
            floors.append((area,x,y,z,room_ids[i]))
    for _,x,y,z,rid in sorted(floors,reverse=True):
        higher=[]
        for t in tris:
            if min(p[1] for p in t) <= y+2:
                continue
            ax,az=t[0][0],t[0][2];bx,bz=t[1][0],t[1][2];cx,cz=t[2][0],t[2][2]
            det=(bz-cz)*(ax-cx)+(cx-bx)*(az-cz)
            if abs(det)<1:continue
            u=((bz-cz)*(x-cx)+(cx-bx)*(z-cz))/det
            v=((cz-az)*(x-cx)+(ax-cx)*(z-cz))/det
            if u>=0 and v>=0 and u+v<=1:
                higher.append(u*t[0][1]+v*t[1][1]+(1-u-v)*t[2][1])
        if higher and 220 < min(higher)-y < 1000:
            spawn=(x,y+15,z);break
    else:
        if not floors:
            raise ValueError('No candidate floor found')
        # Some outdoor levels have no ceiling triangle above the largest
        # playable floor. Use that floor and let the runtime collision check
        # handle the final safe placement.
        _,x,y,z,rid = max(floors)
        spawn=(x,y+15,z)
    # Center the map and expand GoldenEye's compact background units into the
    # scale used by Mario. The old 1.2 cap made Dam look miniature in-game.
    origin=tuple((min(p[k] for t in tris for p in t)+max(p[k] for t in tris for p in t))/2 if k != 1 else spawn[1]-15 for k in range(3))
    horizontal_extent=max(abs(p[k]-origin[k]) for t in tris for p in t for k in (0,2))
    scale=min(WORLD_SCALE, 24000/max(horizontal_extent, 1))
    spawn=tuple(round((spawn[k]-origin[k])*scale) for k in range(3))
    tris=[[[round((p[k]-origin[k])*scale) for k in range(3)] for p in t] for t in tris]
    if max(abs(p[k]) for t in tris for p in t for k in (0,2))>30000:
        raise ValueError(f'{level.title()} exceeds the supported collision bounds')
    return tris,colors,spawn,rid

def install(root,rom,level='facility'):
    if not (root/'src/libsm64.h').is_file() or not (root/'test/main.cpp').is_file():
        raise ValueError('libsm64 checkout not found: use --libsm64 with its folder path.')
    tris,colors,spawn,rid=extract(rom.read_bytes(), level)
    paths=['test/main.cpp','test/level.c','test/level.h','test/gl20/gl20_renderer.c','Makefile']
    backup=root/'facility-backup'
    if backup.exists():
        raise ValueError('Already installed: restore facility-backup before reinstalling.')
    for name in paths:
        src=root/name
        if src.exists():
            dst=backup/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    h='#pragma once\n#include <stddef.h>\n#include "../src/libsm64.h"\nextern const struct SM64Surface surfaces[];\nextern const size_t surfaces_count;\n'
    (root/'test/level.h').write_text(h)
    out=['#include "level.h"','const struct SM64Surface surfaces[] = {']
    for t in tris:
        # Both sides collide: room display lists contain mixed winding.
        for pts in (t,list(reversed(t))):
            out.append('{0,0,0,{'+','.join('{'+','.join(map(str,p))+'}' for p in pts)+'}},')
    out+=['};','const size_t surfaces_count=sizeof(surfaces)/sizeof(surfaces[0]);']
    (root/'test/level.c').write_text('\n'.join(out)+'\n')
    main=(root/'test/main.cpp').read_text()
    main=main.replace('float dir;','float dir = 0.0f;')
    spawn_args=','.join(map(str,spawn))
    main=main.replace('sm64_mario_create( 0, 1000, 0 )','sm64_mario_create('+spawn_args+')')
    main=main.replace('"libsm64", 800, 600','"Mario in GoldenEye Facility - prototype", 1280, 800')
    main=main.replace('struct SM64MarioInputs marioInputs;','struct SM64MarioInputs marioInputs = {};')
    main=main.replace('struct SM64MarioState marioState;','struct SM64MarioState marioState = {};\n'+''.join('    marioState.position[%d] = %d;\n'%(k,v) for k,v in enumerate(spawn)))
    main=main.replace('float lastPos[3], currPos[3];','float lastPos[3] = {'+spawn_args+'}, currPos[3] = {'+spawn_args+'};')
    main=main.replace('float lastGeoPos[9 * SM64_GEO_MAX_TRIANGLES], currGeoPos[9 * SM64_GEO_MAX_TRIANGLES];','float lastGeoPos[9 * SM64_GEO_MAX_TRIANGLES] = {}, currGeoPos[9 * SM64_GEO_MAX_TRIANGLES] = {};')
    main=main.replace('1000.0f *','300.0f *').replace('+ 200.0f;','+ 180.0f;')
    main=main.replace('state[SDL_SCANCODE_X]','(state[SDL_SCANCODE_X] || state[SDL_SCANCODE_SPACE])')
    for old,new in [('UP','W'),('DOWN','S'),('LEFT','A'),('RIGHT','D')]:
        main=main.replace('state[SDL_SCANCODE_'+old+']','(state[SDL_SCANCODE_'+old+'] || state[SDL_SCANCODE_'+new+'])')
    main=main.replace('memcpy(currPos, marioState.position, sizeof(currPos));','if (marioState.position[1] < -15000) { sm64_mario_delete(marioId); marioId = sm64_mario_create('+spawn_args+'); }\n            memcpy(currPos, marioState.position, sizeof(currPos));')
    (root/'test/main.cpp').write_text(main)
    gl=(root/'test/gl20/gl20_renderer.c').read_text()
    gl=gl.replace('glm_perspective( 45.0f,','glm_perspective( 0.785398f,').replace('100.0f, 20000.0f','10.0f, 30000.0f')
    gl=gl.replace('glEnable( GL_CULL_FACE );','glDisable( GL_CULL_FACE );')
    gl=gl.replace('glDrawElements(GL_TRIANGLES, renderState->collision.num_vertices, GL_UNSIGNED_SHORT, renderState->collision.index);','glDisable(GL_TEXTURE_2D);\n\tglDrawArrays(GL_TRIANGLES, 0, renderState->collision.num_vertices);\n\tglEnable(GL_TEXTURE_2D);')
    # Initialize every UV, including the last triangle for odd surface counts.
    gl=gl.replace('worldUv = malloc(sizeof(float) * surfaces_count * 6);','worldUv = calloc(surfaces_count * 6, sizeof(float));')
    gl=gl.replace('(.5+.5*mesh->normal[9*i+j])','(.5+.5*fabsf(mesh->normal[9*i+j]))')
    (root/'test/gl20/gl20_renderer.c').write_text(gl)
    mk=(root/'Makefile').read_text()
    mk=mk.replace('C_FILES := $(foreach dir,$(SRC_DIRS),$(wildcard $(dir)/*.c)) $(C_IMPORTED)',
                  'C_FILES := $(filter-out $(C_IMPORTED),$(foreach dir,$(SRC_DIRS),$(wildcard $(dir)/*.c))) $(C_IMPORTED)')
    mk=mk.replace('test/level.c: ./import-test-collision.py\n\t./import-test-collision.py','test/level.c:\n\t@test -f test/level.c')
    mk=mk.replace('\tlipo -create -output $@ $@.arm64 $@.x86_64\n\trm $@.arm64 $@.x86_64',
                  '\tlipo -create -output $@ $@.arm64 $@.x86_64\n\tinstall_name_tool -id @executable_path/dist/libsm64.dylib $@\n\trm $@.arm64 $@.x86_64')
    (root/'Makefile').write_text(mk)
    print(f'Installed {len(tris):,} {level.title()} triangles. Spawn room {rid}.')
    print('Geometry-only prototype: no GoldenEye textures, doors, guards, or weapons yet.')
    print('Backup:',backup)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--libsm64',type=pathlib.Path,default=pathlib.Path.home()/'Projects/n64-mashup/libsm64')
    p.add_argument('--rom',type=pathlib.Path,help='US GoldenEye ROM; defaults to finding it in Downloads')
    p.add_argument('--level',choices=sorted(LEVELS),default='facility')
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    if a.rom is None:
        downloads=pathlib.Path.home()/'Downloads'
        candidates=sorted(downloads.glob('*.z64')) if downloads.exists() else []
        a.rom=next((f for f in candidates if hashlib.sha1(f.read_bytes()).hexdigest()=='abe01e4aeb033b6c0836819f549c791b26cfde83'),None)
        if a.rom is None:
            p.error('US GoldenEye ROM not found in Downloads. Supply --rom "/path/to/GoldenEye.z64".')
    if a.check:
        t,c,s,r=extract(a.rom.read_bytes(), a.level);print(json.dumps({'level':a.level,'triangles':len(t),'spawn':s,'spawn_room':r}))
    else:install(a.libsm64.resolve(),a.rom.expanduser(),a.level)
