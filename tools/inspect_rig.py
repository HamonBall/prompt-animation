import bpy
import json
import sys

path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path, use_anim=False)
for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        print('RIG_PROFILE ' + json.dumps({
            'name': obj.name, 'scale': list(obj.scale),
            'bones': [{ 'name': b.name, 'head': list(b.head_local),
                        'tail': list(b.tail_local)} for b in obj.data.bones]
        }))
