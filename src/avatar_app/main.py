"""Blender-hosted interface for the first motion feasibility milestone."""
from pathlib import Path
import time
import bpy
from bpy.props import StringProperty
from .planning.interpreter import interpret
from .blender.avatar import import_avatar, discard_avatar
from .blender.animation import build_transition
from .blender.scene import prepare_preview


_state = {'avatar': None, 'plan': None, 'history': [], 'busy': False}
ROOT = Path(__file__).resolve().parents[2]


def generate(context, text):
    candidate = interpret(text, _state['plan'])
    started = time.perf_counter()
    context.window_manager.progress_begin(0, 100)
    try:
        result = build_transition(_state['avatar'], candidate,
                                  lambda fraction: context.window_manager.progress_update(fraction * 100))
    finally:
        context.window_manager.progress_end()
    _state['history'].append((_state['plan'], candidate))
    _state['plan'] = candidate
    context.scene.avatar_status = (
        f'Revision {candidate.revision}: {result["frames"]} frames, '
        f'{time.perf_counter() - started:.1f}s. Ready to play.')


class AVATAR_OT_load(bpy.types.Operator):
    bl_idname = 'avatar.load'
    bl_label = 'Load avatar'
    bl_description = 'Import into a separate preview scene, preserving existing scenes'

    def execute(self, context):
        previous_scene = context.window.scene
        previous_state = dict(_state)
        source_path = context.scene.avatar_path
        handle = None
        try:
            if context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
            handle = import_avatar(bpy.path.abspath(source_path))
            prepare_preview(handle)
            old = _state['avatar']
            _state.update(avatar=handle, plan=None, history=[])
            context.window.scene = handle.scene
            handle.scene.avatar_path = str(Path(source_path))
            handle.scene.avatar_prompt = 'T-rex pose'
            generate(context, 'T-rex pose')
            if old:
                discard_avatar(old)
            context.scene.avatar_status += ' Use the Avatar tab to refine.'
            return {'FINISHED'}
        except Exception as exc:
            if handle:
                context.window.scene = previous_scene
                discard_avatar(handle)
            _state.update(previous_state)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class AVATAR_OT_prompt(bpy.types.Operator):
    bl_idname = 'avatar.prompt'
    bl_label = 'Generate / refine'

    @classmethod
    def poll(cls, context):
        return (_state['avatar'] is not None
                and context.scene == _state['avatar'].scene and not _state['busy'])

    def execute(self, context):
        try:
            _state['busy'] = True
            generate(context, context.scene.avatar_prompt)
            return {'FINISHED'}
        except Exception as exc:
            context.scene.avatar_status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            _state['busy'] = False


class AVATAR_OT_play(bpy.types.Operator):
    bl_idname = 'avatar.play'
    bl_label = 'Play once'

    @classmethod
    def poll(cls, context):
        return (_state['avatar'] is not None
                and context.scene == _state['avatar'].scene and not _state['busy'])

    def execute(self, context):
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
        scene = context.scene
        scene.frame_set(scene.frame_start)
        bpy.ops.screen.animation_play()
        self._timer = context.window_manager.event_timer_add(0.03, window=context.window)
        self._scene = scene
        self._started = time.perf_counter()
        self._duration = (scene.frame_end - scene.frame_start) / scene.render.fps
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if (event.type == 'ESC' or context.scene != self._scene
                or not context.screen.is_animation_playing
                or time.perf_counter() - self._started >= self._duration
                or self._scene.frame_current >= self._scene.frame_end):
            if context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
            context.window_manager.event_timer_remove(self._timer)
            if context.scene == self._scene and event.type != 'ESC':
                self._scene.frame_set(self._scene.frame_end)
            return {'FINISHED'}
        return {'PASS_THROUGH'}


class AVATAR_PT_panel(bpy.types.Panel):
    bl_label = 'Avatar Animation'
    bl_idname = 'AVATAR_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Avatar'

    def draw(self, context):
        layout = self.layout
        layout.label(text='Local motion prototype')
        layout.prop(context.scene, 'avatar_path', text='FBX')
        layout.operator('avatar.load')
        layout.separator()
        layout.prop(context.scene, 'avatar_prompt', text='Prompt')
        layout.operator('avatar.prompt')
        layout.operator('avatar.play')
        plan = _state['plan']
        if plan:
            layout.label(text=f'Revision {plan.revision} · {plan.duration:g} seconds')
            layout.label(text=f'Crouch {plan.crouch:.0%} · arm lift {plan.arm_lift:g}')
        box = layout.box()
        for text in ('Start: T-rex pose in 3 seconds', 'Edit: crouch lower / crouch less',
                     'raise arms / lower arms', 'slower / faster',
                     'Rules-based prompts; no AI connected yet.',
                     'Walking and dancing are not supported.'):
            box.label(text=text)
        # Wrap status so an unsupported request remains readable in a narrow sidebar.
        import textwrap
        for line in textwrap.wrap(context.scene.avatar_status, width=42):
            layout.label(text=line)


CLASSES = (AVATAR_OT_load, AVATAR_OT_prompt, AVATAR_OT_play, AVATAR_PT_panel)


def _default_avatar():
    return ROOT / 'Hip Hop Andrejs.fbx'


def main():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.avatar_path = StringProperty(name='Avatar FBX', subtype='FILE_PATH',
                                               default=str(_default_avatar()))
    bpy.types.Scene.avatar_prompt = StringProperty(name='Prompt', default='T-rex pose')
    bpy.types.Scene.avatar_status = StringProperty(default='Load an avatar to begin.')
    if _default_avatar().is_file():
        bpy.ops.avatar.load()
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            # Panel category becomes available after Blender's first UI redraw.
    print('Avatar prototype ready. Open the Avatar tab in the 3D View sidebar (N).')
    if not bpy.app.background and _state['avatar']:
        def demonstrate():
            bpy.ops.avatar.play()
        bpy.app.timers.register(demonstrate, first_interval=1.0)
