"""Blender-hosted interface for general prompt-to-pose transitions."""
from pathlib import Path
import queue
import threading
import time
import bpy
from bpy.props import StringProperty
from .planning.pose_interpreter import interpret_pose as interpret_request
from .models import PlanError
from .blender.avatar import import_avatar, discard_avatar
from .blender.pose import build_pose_transition as build_transition
from .blender.scene import prepare_preview


_state = {'avatar': None, 'plan': None, 'history': [], 'busy': False,
          'cancel_requested': False}
ROOT = Path(__file__).resolve().parents[2]


def apply_candidate(context, candidate, explanation, started, expected_avatar, expected_plan):
    if (_state['avatar'] is not expected_avatar or _state['plan'] is not expected_plan
            or context.scene != expected_avatar.scene):
        raise PlanError('The avatar or result changed while interpreting. Submit the request again.')
    if context.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=False)
    context.scene.avatar_status = 'Building motion from the checked plan…'
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
        f'{time.perf_counter() - started:.1f}s. Ready to play. {explanation}')


def generate(context, text):
    started = time.perf_counter()
    avatar, current = _state['avatar'], _state['plan']
    candidate, explanation = interpret_request(text, current)
    apply_candidate(context, candidate, explanation, started, avatar, current)


class AVATAR_OT_load(bpy.types.Operator):
    bl_idname = 'avatar.load'
    bl_label = 'Load avatar'
    bl_description = 'Import into a separate preview scene, preserving existing scenes'

    @classmethod
    def poll(cls, context):
        return not _state['busy']

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
            handle.scene.avatar_prompt = ''
            generate(context, 'neutral pose')
            handle.scene.frame_set(handle.scene.frame_end)
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
        # Command-line integration checks remain synchronous; the UI uses a worker.
        if bpy.app.background:
            try:
                generate(context, context.scene.avatar_prompt)
                return {'FINISHED'}
            except Exception as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        self._avatar = _state['avatar']
        self._plan = _state['plan']
        self._scene = context.scene
        self._started = time.perf_counter()
        self._results = queue.Queue(maxsize=1)
        text = context.scene.avatar_prompt
        current = self._plan
        results = self._results
        _state['busy'] = True
        _state['cancel_requested'] = False
        context.scene.avatar_status = 'Interpreting your request locally… (Esc to cancel)'
        if context.area:
            context.area.tag_redraw()

        def interpret_in_background():
            # This worker receives plain data only and never accesses bpy.
            try:
                results.put((True, interpret_request(text, current)))
            except Exception as exc:
                results.put((False, str(exc)))

        threading.Thread(target=interpret_in_background, daemon=True,
                         name='Avatar local interpretation').start()
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        _state['busy'] = False
        _state['cancel_requested'] = False

    def modal(self, context, event):
        if (event.type == 'ESC' or _state['cancel_requested']
                or context.scene != self._scene or _state['avatar'] is not self._avatar):
            self._scene.avatar_status = ('Request canceled. Previous animation kept. '
                                         'An active local inference may finish in the background.')
            self.finish(context)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if context.area:
            context.area.tag_redraw()
        try:
            success, result = self._results.get_nowait()
        except queue.Empty:
            return {'PASS_THROUGH'}
        try:
            if not success:
                raise PlanError(result)
            candidate, explanation = result
            apply_candidate(context, candidate, explanation, self._started,
                            self._avatar, self._plan)
            return {'FINISHED'}
        except Exception as exc:
            context.scene.avatar_status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            self.finish(context)


class AVATAR_OT_cancel(bpy.types.Operator):
    bl_idname = 'avatar.cancel'
    bl_label = 'Cancel request'

    @classmethod
    def poll(cls, context):
        return _state['busy']

    def execute(self, context):
        _state['cancel_requested'] = True
        return {'FINISHED'}


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
        layout.label(text='Prompt-to-pose prototype')
        layout.prop(context.scene, 'avatar_path', text='FBX')
        layout.operator('avatar.load')
        layout.separator()
        layout.prop(context.scene, 'avatar_prompt', text='Prompt')
        layout.operator('avatar.prompt')
        if _state['busy']:
            layout.operator('avatar.cancel')
        layout.operator('avatar.play')
        plan = _state['plan']
        if plan:
            layout.label(text=f'Revision {plan.revision} · {plan.duration:g} seconds')
            layout.label(text=f'{len(plan.values)} body controls · contact: {plan.contact}')
        box = layout.box()
        for text in ('Describe any body pose in your own words.',
                     'Examples: reach overhead, salute,',
                     'sit, bow, balance, lie on your back.',
                     'Follow up to adjust individual body parts.',
                     'Local Qwen AI interprets the whole pose.',
                     'Motion loops and precise fingers are pending.'):
            box.label(text=text)
        # Wrap status so an unsupported request remains readable in a narrow sidebar.
        import textwrap
        for line in textwrap.wrap(context.scene.avatar_status, width=42):
            layout.label(text=line)


CLASSES = (AVATAR_OT_load, AVATAR_OT_prompt, AVATAR_OT_cancel, AVATAR_OT_play, AVATAR_PT_panel)


def _default_avatar():
    return ROOT / 'Hip Hop Andrejs.fbx'


def main():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.avatar_path = StringProperty(name='Avatar FBX', subtype='FILE_PATH',
                                               default=str(_default_avatar()))
    bpy.types.Scene.avatar_prompt = StringProperty(name='Prompt', default='')
    bpy.types.Scene.avatar_status = StringProperty(default='Load an avatar to begin.')
    if _default_avatar().is_file():
        bpy.ops.avatar.load()
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            # Panel category becomes available after Blender's first UI redraw.
    print('Avatar prototype ready. Open the Avatar tab in the 3D View sidebar (N).')
