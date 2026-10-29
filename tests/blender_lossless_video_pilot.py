"""Verify Blender's available FFV1 encoder before permitting PNG retirement."""
from pathlib import Path
import sys
import tempfile
import hashlib
from array import array
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import atomic_json
OUT=ROOT/'artifacts/maintenance/storage-v2';scratch=OUT/'.scratch';scratch.mkdir(exist_ok=True)


def pixels(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    value=hashlib.sha256(array('f',image.pixels[:]).tobytes()).hexdigest();size=list(image.size)
    bpy.data.images.remove(image);return value,size


with tempfile.TemporaryDirectory(dir=scratch,prefix='ffv1-') as temporary:
    folder=Path(temporary).resolve();assert folder.is_relative_to(scratch.resolve())
    source=ROOT/'artifacts/stages/05.2/demo/arm.raise.default/front'
    frames=sorted(source.glob('*.png'))[:5]
    hashes=[pixels(p) for p in frames];scene=bpy.data.scenes.new('LosslessEvidence')
    scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=scene.render.resolution_y=128
    scene.render.resolution_percentage=100;scene.render.fps=30;scene.frame_start=1;scene.frame_end=len(frames)
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.render.dither_intensity=0
    scene.render.image_settings.media_type='VIDEO';scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MKV';scene.render.ffmpeg.codec='FFV1'
    scene.render.image_settings.color_mode='RGBA';scene.render.filepath=str(folder/'frames.mkv')
    editor=scene.sequence_editor_create();strip=editor.strips.new_image('Source',str(frames[0]),channel=1,frame_start=1)
    for path in frames[1:]:strip.elements.append(path.name)
    strip.frame_final_duration=len(frames)
    bpy.ops.render.render(animation=True,scene=scene.name)
    movie=folder/'frames.mkv';clip=bpy.data.movieclips.load(str(movie));print('VIDEO_METADATA',clip.frame_duration,clip.fps,flush=True)
    assert clip.frame_duration==len(frames) and abs(clip.fps-30)<1e-6
    editor.strips.remove(strip);editor.strips.new_movie('Decoded',str(movie),channel=1,frame_start=1)
    decoded=folder/'decoded';decoded.mkdir()
    scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.filepath=str(decoded)+'/'
    bpy.ops.render.render(animation=True,scene=scene.name)
    observed=[pixels(decoded/(str(i+1).zfill(4)+'.png')) for i in range(len(frames))]
    value={'passed':hashes==observed,'frames':len(frames),'source':hashes,'decoded':observed,'bytes':movie.stat().st_size}
    atomic_json(OUT/'lossless-video-pilot.json',value)
    assert value['passed'],'FFV1 decoded pixels differ; PNG originals must remain'
    bpy.data.scenes.remove(scene);bpy.data.movieclips.remove(clip)
print('BLENDER_FFV1_PIXEL_ROUNDTRIP_PASSED',flush=True)
