#!/usr/bin/env python3
"""Install generated ROM textures into the Mac OpenGL 2 prototype, reversibly."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

RENDERER='test/gl20/gl20_renderer.c'
HEADER='test/ge_textured_level.h'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def generate(manifest, directory):
    textures=json.loads((directory/'decoded.json').read_text())['textures']
    by_id={t['id']:t for t in textures}
    triangles=manifest['geometry']['triangles']
    out=['/* Generated locally from the user ROM. Do not distribute. */']
    for t in textures:
        data=(directory/t['file']).read_bytes()
        if len(data)!=t['width']*t['height']*4 or digest(data)!=t['sha256']:
            raise ValueError('Invalid texture bytes: '+str(t['id']))
        out.append('static const unsigned char ge_pixels_%d[]={%s};'%(t['id'],','.join(map(str,data))))
    out.append('static GLuint ge_textures[%d];'%len(textures))
    out.append('static void ge_texture_init(void) {')
    out.append('glGenTextures(%d, ge_textures);'%len(textures))
    for index,t in enumerate(textures):
        out.extend(['glBindTexture(GL_TEXTURE_2D,ge_textures[%d]);'%index,
                    'glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);',
                    'glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);',
                    'glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT);',
                    'glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT);',
                    'glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,%d,%d,0,GL_RGBA,GL_UNSIGNED_BYTE,ge_pixels_%d);'%(t['width'],t['height'],t['id'])])
    out.append('}')
    vertices=[]; batches=[]
    for index,t in enumerate(textures):
        start=len(vertices)
        for tri in triangles:
            if tri['material_id']!=t['id']: continue
            for xyz,rgb,st in zip(tri['vertices'],tri['colors'],tri['texture_st_s10_5']):
                vertices.append([*xyz,*rgb,st[0]/(32*t['width']),st[1]/(32*t['height'])])
        batches.append((index,start,len(vertices)-start))
    if any(t['material_id'] not in by_id for t in triangles):
        raise ValueError('Missing decoded materials')
    out.append('static const GLfloat ge_vertices[][8]={')
    out.extend('{'+','.join(format(v,'.9g') for v in row)+'},' for row in vertices)
    out.extend(['};','static void ge_texture_draw(void) {',
                'glPushAttrib(GL_ENABLE_BIT|GL_COLOR_BUFFER_BIT|GL_TEXTURE_BIT|GL_CURRENT_BIT);',
                'glDisable(GL_LIGHTING); glDisable(GL_CULL_FACE); glEnable(GL_TEXTURE_2D);',
                'glEnable(GL_ALPHA_TEST); glAlphaFunc(GL_GREATER,0.05f);',
                'glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_MODULATE);'])
    for index,start,count in batches:
        out.append('glBindTexture(GL_TEXTURE_2D,ge_textures[%d]); glBegin(GL_TRIANGLES);'%index)
        out.append('for(int i=%d;i<%d;++i){ glColor3fv(ge_vertices[i]+3); glTexCoord2fv(ge_vertices[i]+6); glVertex3fv(ge_vertices[i]); }'%(start,start+count))
        out.append('glEnd();')
    out.extend(['glPopAttrib();','}'])
    return '\n'.join(out)+'\n'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--libsm64',type=Path,required=True)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--decoded',type=Path)
    p.add_argument('--undo',action='store_true')
    a=p.parse_args(); root=a.libsm64.resolve(); backup=root/'texture-backup'
    renderer=root/RENDERER; header=root/HEADER
    if a.undo:
        state=json.loads((backup/'state.json').read_text())
        for name in (RENDERER,HEADER):
            if digest((root/name).read_bytes())!=state[name]:
                raise ValueError('Later edits detected; rollback refused: '+name)
        shutil.copy2(backup/'renderer.c',renderer)
        header.unlink()
        # Keep the backup as an audit record; repeated undo/install is refused.
        print('Restored renderer; rebuild the game. Backup retained at',backup)
        return
    if backup.exists():
        state=json.loads((backup/'state.json').read_text())
        if all((root/n).is_file() and digest((root/n).read_bytes())==state[n] for n in (RENDERER,HEADER)):
            generated=generate(json.loads(a.manifest.read_text()),a.decoded)
            if generated==header.read_text():
                print('Textures already installed; preserving backup.')
                return
        raise ValueError('texture-backup exists; refusing to overwrite existing work')
    if header.exists(): raise ValueError('Existing generated header; refusing overwrite')
    source=renderer.read_text()
    anchor='glDisable(GL_TEXTURE_2D);\n\tglDrawArrays(GL_TRIANGLES, 0, renderState->collision.num_vertices);\n\tglEnable(GL_TEXTURE_2D);'
    init='load_collision_mesh( &renderState->collision );'
    if source.count(anchor)!=1 or source.count(init)!=1:
        raise ValueError('Renderer differs from expected prototype; no files changed')
    generated=generate(json.loads(a.manifest.read_text()),a.decoded)
    source=source.replace('#include "../level.h"','#include "../level.h"\n#include "../ge_textured_level.h"')
    source=source.replace(init,init+'\n\tge_texture_init();').replace(anchor,'ge_texture_draw();')
    backup.mkdir(); shutil.copy2(renderer,backup/'renderer.c')
    header.write_text(generated); renderer.write_text(source)
    (backup/'state.json').write_text(json.dumps({n:digest((root/n).read_bytes()) for n in (RENDERER,HEADER)},indent=2))
    print('Installed local textures in Mac OpenGL 2 renderer; rebuild required.')

if __name__=='__main__': main()
