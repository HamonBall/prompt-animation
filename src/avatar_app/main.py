"""Blender-hosted interface for general prompt-to-pose transitions."""
from pathlib import Path
from dataclasses import replace
import queue
import threading
import time
import math
import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty
from .planning.action_interpreter import interpret_action as interpret_request
from .motion import ActionPlan, action_from_pose
from .models import PlanError
from .pose import PosePlan
from .blender.avatar import import_avatar, discard_avatar
from .blender.motion import build_action, build_action_frames
from .blender.scene import prepare_preview, resolve_seat
from .blender.demo import create_demo_avatar
from .planning.reference import load_reference


_state = {'avatar': None, 'plan': None, 'history': [], 'busy': False,
          'cancel_requested': False, 'last_error': None, 'reviewed_plan': None,
          'experimental': False, 'phase': '', 'started': 0}
ROOT = Path(__file__).resolve().parents[2]


def build_transition(handle, pose, progress=lambda f: None, allow_experimental=False):
    return build_action(handle, action_from_pose(pose), progress, allow_experimental=allow_experimental)


def apply_candidate(context, candidate, explanation, started, expected_avatar, expected_plan, approximate=False):
    if (_state['avatar'] is not expected_avatar or _state['plan'] is not expected_plan
            or context.scene != expected_avatar.scene):
        raise PlanError('The avatar or result changed while interpreting. Submit the request again.')
    if context.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=False)
    context.scene.avatar_status = 'Creating animation…'
    context.window_manager.progress_begin(0, 100)
    try:
        builder = build_action if isinstance(candidate, ActionPlan) else build_transition
        args = {'allow_experimental': True} if approximate else {}
        result = builder(_state['avatar'], candidate,
                         lambda fraction: context.window_manager.progress_update(fraction * 100), **args)
    finally:
        context.window_manager.progress_end()
    if approximate:
        result['experimental'] = True
    commit_result(context, candidate, result, explanation, started)


def commit_result(context, candidate, result, explanation, started):
    if isinstance(candidate, ActionPlan) and result.get('ending_pose'):
        endpoint = result['ending_pose']
        candidate = replace(candidate, resolved_final=PosePlan(tuple(sorted(endpoint['controls'].items())),
            endpoint['contact'], endpoint['revision'], endpoint['description']))
    if (isinstance(candidate, ActionPlan)
            and any(c.surface == 'floor' and c.part in ('pelvis', 'back')
                    for stage in candidate.stages for c in stage.contacts)
            and not any(s.name == 'seat' for s in candidate.surfaces)
            and any(s.name == 'seat' for s in getattr(_state['avatar'], 'surfaces', ()))):
        # A floor-only route needs clear space behind the avatar. Change the
        # environment only after success so a failed request keeps its seat.
        context.scene.avatar_show_seat = False
        resolve_seat(_state['avatar'], enabled=False)
        explanation += ' Preview seat cleared for floor movement.'
    _state['history'].append((_state['plan'], candidate))
    _state['plan'] = candidate
    _state['experimental'] = result.get('experimental', False)
    _state['last_error'] = None
    if not _state['experimental']:
        _state['reviewed_plan'] = candidate
    context.scene.avatar_status = (
        f'{"Experimental approximation; inspect before use." if _state["experimental"] else "Ready to play."} {explanation}')


def generate(context, text, approximate=False):
    started = time.perf_counter()
    avatar, current = _state['avatar'], _state['plan']
    references = [load_reference(context.scene.avatar_reference_url)] if context.scene.avatar_use_reference else []
    candidate, explanation = interpret_request(text, current, surfaces=getattr(avatar, 'surfaces', ()),
                                              approximate=approximate, references=references)
    apply_candidate(context, candidate, explanation, started, avatar, current, approximate)


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
            handle = import_avatar(bpy.path.abspath(source_path)) if source_path.strip() else create_demo_avatar()
            prepare_preview(handle)
            old = _state['avatar']
            _state.update(avatar=handle, plan=None, history=[], reviewed_plan=None, last_error=None,
                          experimental=False)
            context.window.scene = handle.scene
            handle.scene.avatar_path = str(Path(source_path)) if source_path.strip() else ''
            resolve_seat(handle, handle.scene.avatar_seat_height, handle.scene.avatar_show_seat)
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
    approximate: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return (_state['avatar'] is not None
                and context.scene == _state['avatar'].scene and not _state['busy'])

    def execute(self, context):
        # Command-line integration checks remain synchronous; the UI uses a worker.
        if bpy.app.background:
            try:
                generate(context, context.scene.avatar_prompt, self.approximate)
                return {'FINISHED'}
            except Exception as exc:
                _state['last_error'] = str(exc)
                context.scene.avatar_status = str(exc)
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        self._avatar = _state['avatar']
        self._plan = _state['plan']
        self._scene = context.scene
        self._started = time.perf_counter()
        self._results = queue.Queue(maxsize=1)
        self._progress = queue.SimpleQueue()
        self._surfaces = tuple(self._avatar.surfaces)
        self._approximate = self.approximate
        self._builder = None
        reference_url = context.scene.avatar_reference_url if context.scene.avatar_use_reference else ''
        text = context.scene.avatar_prompt
        current = self._plan
        results = self._results
        phases = self._progress
        surfaces = self._surfaces
        approximate = self._approximate
        _state['busy'] = True
        _state['cancel_requested'] = False
        _state.update(phase='Preparing request', started=self._started)
        context.scene.avatar_status = 'Interpreting your request locally… (Esc to cancel)'
        if context.area:
            context.area.tag_redraw()

        def interpret_in_background():
            # This worker receives plain data only and never accesses bpy.
            try:
                phases.put('Loading reference page' if reference_url else 'Understanding your request')
                references = [load_reference(reference_url)] if reference_url else []
                candidate, explanation = interpret_request(text, current, surfaces=surfaces,
                    approximate=approximate, references=references, progress=phases.put)
                if references:
                    explanation += ' Reference: ' + reference_url
                results.put((True, (candidate, explanation)))
            except Exception as exc:
                results.put((False, str(exc)))

        threading.Thread(target=interpret_in_background, daemon=True,
                         name='Avatar local interpretation').start()
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        if getattr(self, '_builder', None) is not None:
            self._builder.close()
            self._builder = None
            context.window_manager.progress_end()
        context.window_manager.event_timer_remove(self._timer)
        _state['busy'] = False
        _state['cancel_requested'] = False
        _state['phase'] = ''

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
        phases = getattr(self, '_progress', None)
        if phases:
            while not phases.empty():
                _state['phase'] = phases.get_nowait()
            context.scene.avatar_status = f'{_state["phase"]} · {time.perf_counter()-self._started:.0f}s elapsed (Esc to cancel)'
        if getattr(self, '_builder', None) is not None:
            try:
                deadline = time.perf_counter() + .04
                while time.perf_counter() < deadline:
                    next(self._builder)
                return {'PASS_THROUGH'}
            except StopIteration as completed:
                self._builder = None
                context.window_manager.progress_end()
                if self._approximate:
                    completed.value['experimental'] = True
                commit_result(context, self._candidate, completed.value, self._explanation, self._started)
                self.finish(context)
                return {'FINISHED'}
            except Exception as exc:
                _state['last_error'] = str(exc)
                context.scene.avatar_status = str(exc)
                self.finish(context)
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
        try:
            success, result = self._results.get_nowait()
        except queue.Empty:
            return {'PASS_THROUGH'}
        try:
            if not success:
                raise PlanError(result)
            candidate, explanation = result
            if tuple(self._avatar.surfaces) != self._surfaces:
                raise PlanError('The support surfaces changed during interpretation. Submit again.')
            if _state['plan'] is not self._plan:
                raise PlanError('The result changed during interpretation. Submit again.')
            self._candidate, self._explanation = candidate, explanation
            context.window_manager.progress_begin(0, 100)
            _state['phase'] = 'Creating animation'
            plan = candidate if isinstance(candidate, ActionPlan) else action_from_pose(candidate)
            self._builder = build_action_frames(self._avatar, plan,
                lambda fraction: context.window_manager.progress_update(fraction*100),
                allow_experimental=self._approximate)
            return {'PASS_THROUGH'}
        except Exception as exc:
            context.scene.avatar_status = str(exc)
            _state['last_error'] = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            if self._builder is None:
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


class AVATAR_OT_try(bpy.types.Operator):
    bl_idname = 'avatar.try_anyway'
    bl_label = 'Try anyway (experimental)'
    bl_description = 'Approximate this request; preview may fail quality checks but data and reach remain checked'
    @classmethod
    def poll(cls, context):
        return AVATAR_OT_prompt.poll(context) and bool(_state['last_error'])
    def execute(self, context):
        result = bpy.ops.avatar.prompt(approximate=True)
        return {'CANCELLED'} if result == {'CANCELLED'} else {'FINISHED'}


class AVATAR_OT_restore(bpy.types.Operator):
    bl_idname = 'avatar.restore_reviewed'
    bl_label = 'Restore reviewed result'
    @classmethod
    def poll(cls, context):
        return AVATAR_OT_prompt.poll(context) and _state['experimental'] and _state['reviewed_plan'] is not None
    def execute(self, context):
        try:
            plan = _state['reviewed_plan']
            if isinstance(plan, ActionPlan):
                seat = next((s for s in plan.surfaces if s.name == 'seat'), None)
                if seat:
                    context.scene.avatar_show_seat = True
                    context.scene.avatar_seat_height = seat.height
            apply_candidate(context, _state['reviewed_plan'], 'Restored reviewed motion.', time.perf_counter(),
                            _state['avatar'], _state['plan'])
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


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
        prompt = layout.column()
        prompt.enabled = not _state['busy']
        prompt.prop(context.scene, 'avatar_prompt', text='Prompt')
        layout.operator('avatar.prompt')
        if _state['busy']:
            if hasattr(layout, 'progress'):
                # A cyclic activity indicator, not a completion estimate.
                activity = .5 + .5 * math.sin((time.perf_counter()-_state['started']) * 3)
                layout.progress(type='RING', factor=activity, text='Activity')
            layout.label(text=f'{_state["phase"]}…', icon='TIME')
            layout.label(text=f'{time.perf_counter()-_state["started"]:.0f}s elapsed')
            layout.operator('avatar.cancel')
        elif _state['last_error']:
            layout.operator('avatar.try_anyway')
        if _state['experimental']:
            layout.label(text='Experimental approximation', icon='ERROR')
            layout.operator('avatar.restore_reviewed')
        layout.operator('avatar.play')
        plan = _state['plan']
        if plan:
            layout.label(text=f'{plan.duration:g} seconds')
        # Wrap status so an unsupported request remains readable in a narrow sidebar.
        import textwrap
        for line in textwrap.wrap(context.scene.avatar_status, width=42):
            layout.label(text=line)


class AVATAR_PT_settings(bpy.types.Panel):
    bl_label = 'Avatar settings'
    bl_idname = 'AVATAR_PT_settings'
    bl_parent_id = 'AVATAR_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Avatar'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.enabled = not _state['busy']
        layout.prop(context.scene, 'avatar_path', text='FBX')
        if not context.scene.avatar_path:
            layout.label(text='Built-in try-out avatar · optional FBX')
        layout.operator('avatar.load')
        layout.prop(context.scene, 'avatar_use_reference', text='Use web reference (optional)')
        if context.scene.avatar_use_reference:
            layout.prop(context.scene, 'avatar_reference_url', text='HTTPS URL')


CLASSES = (AVATAR_OT_load, AVATAR_OT_prompt, AVATAR_OT_cancel, AVATAR_OT_try, AVATAR_OT_restore, AVATAR_OT_play, AVATAR_PT_panel, AVATAR_PT_settings)


def update_seat(scene, context):
    handle = _state['avatar']
    if handle and scene == handle.scene and not _state['busy']:
        resolve_seat(handle, scene.avatar_seat_height, scene.avatar_show_seat)


def _default_avatar():
    return ROOT / 'Hip Hop Andrejs.fbx'


def main():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.avatar_path = StringProperty(name='Avatar FBX', subtype='FILE_PATH',
                                               default=str(_default_avatar()) if _default_avatar().is_file() else '')
    bpy.types.Scene.avatar_prompt = StringProperty(name='Prompt', default='')
    bpy.types.Scene.avatar_status = StringProperty(default='Load an avatar to begin.')
    bpy.types.Scene.avatar_show_seat = BoolProperty(default=False, update=update_seat)
    bpy.types.Scene.avatar_seat_height = FloatProperty(default=.45, min=.25, max=.70, subtype='DISTANCE', update=update_seat)
    bpy.types.Scene.avatar_use_reference = BoolProperty(default=False)
    bpy.types.Scene.avatar_reference_url = StringProperty(default='')
    bpy.ops.avatar.load()
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            # Panel category becomes available after Blender's first UI redraw.
    print('Avatar prototype ready. Open the Avatar tab in the 3D View sidebar (N).')
