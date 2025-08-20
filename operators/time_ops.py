# pyright: reportInvalidTypeForm=false
"""
時間トラッカーのオペレータモジュール
"""

import datetime
import time

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty

from ..core.time_data import TimeDataManager
from ..core import time_data as core_time
from ..utils.formatting import format_time
from ..utils.logging import get_logger
from ..addon import get_prefs

log = get_logger(__name__)


class TIMETRACKER_OT_edit_comment(Operator):
    """セッションコメントを編集"""

    bl_idname = "timetracker.edit_comment"
    bl_label = "Edit Session Comment"
    bl_description = "Edit comment for the current session"
    bl_options = {"REGISTER", "UNDO"}

    comment: StringProperty(
        name="コメント", description="セッションのコメント", default=""
    )

    def invoke(self, context, event):
        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if time_data:
            self.comment = time_data.get_session_comment()
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if time_data:
            time_data.set_session_comment(self.comment)
            self.report({"INFO"}, "Comment updated")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "comment")


class TIMETRACKER_OT_switch_session(Operator):
    """現在のセッションを終了し、新しいセッションを開始"""

    bl_idname = "timetracker.switch_session"
    bl_label = "Switch Session"
    bl_description = "End current session and start a new one"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if time_data:
            time_data.switch_session()
            self.report({"INFO"}, "Started new session")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class TIMETRACKER_OT_reset_session(Operator):
    """現在のセッションをリセット"""

    bl_idname = "timetracker.reset_session"
    bl_label = "Reset Current Session"
    bl_description = "Reset the current session time to zero"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if time_data:
            time_data.reset_current_session()
            self.report({"INFO"}, "Reset current session")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class TIMETRACKER_OT_reset_data(Operator):
    """Reset time tracking data"""

    bl_idname = "timetracker.reset_data"
    bl_label = "Reset Time Data"
    bl_description = "Reset all time tracking data"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if time_data:
            time_data.reset()
            time_data.save_data()
            self.report({"INFO"}, "Reset all time tracking data")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class TIMETRACKER_OT_export_data(Operator):
    """Export time tracking data"""

    bl_idname = "timetracker.export_data"
    bl_label = "Export Time Report"
    bl_description = "Export time tracking data to a text file"

    def execute(self, context):
        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if time_data:
            # Create a report
            current_time = datetime.datetime.now()
            report_name = f"WorkTimeReport_{current_time.strftime('%Y%m%d_%H%M%S')}.md"
            report = bpy.data.texts.new(report_name)

            # Get file name
            if bpy.data.filepath:
                filename = bpy.path.basename(bpy.data.filepath)
            else:
                filename = "Unsaved File"

            # Get creation date
            creation_date = datetime.datetime.fromtimestamp(
                time_data.file_creation_time
            )

            # Write report header
            report.write(f"# Work Time Report for {filename}\n")
            report.write(f"Generated: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            report.write(
                f"File created: {creation_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            report.write(f"File ID: {time_data.file_id}\n\n")

            # Write summary
            report.write("## Summary\n")
            report.write(f"- Total work time: {time_data.get_formatted_total_time()}\n")
            report.write(
                f"- Current session: {time_data.get_formatted_session_time()}\n"
            )
            report.write(
                f"- Time since last save: "
                f"{time_data.get_formatted_time_since_save()}\n\n"
            )

            # Write detailed session info
            report.write("## Session History\n")
            pg = getattr(context.scene, "wtt_time_data", None)
            sessions = list(pg.sessions) if pg else []
            for i, session in enumerate(sessions):
                start_time = datetime.datetime.fromtimestamp(session.start).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if session.end <= 0.0:
                    end_time = "Active"
                else:
                    end_time = datetime.datetime.fromtimestamp(session.end).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                duration = time_data.get_session_work_seconds_by_id(session.id)
                formatted_duration = format_time(duration)
                report.write(f"### Session {i + 1}\n")
                report.write(f"- Start: {start_time}\n")
                report.write(f"- End: {end_time}\n")
                report.write(f"- Duration: {formatted_duration}\n")

                if session.comment:
                    report.write(f"- Comment: {session.comment}\n")

                report.write("\n")

            self.report({"INFO"}, f"Report exported to text editor: {report_name}")
            return {"FINISHED"}
        return {"CANCELLED"}


class TIMETRACKER_OT_clear_breaks(Operator):
    """Clear all break sessions and reset break state"""

    bl_idname = "timetracker.clear_breaks"
    bl_label = "Clear Break History"
    bl_description = "Delete all recorded breaks and reset break state"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        pg = getattr(context.scene, "wtt_time_data", None)
        if not pg:
            self.report({"WARNING"}, "No time tracker data")
            return {"CANCELLED"}

        # 終了処理中なら閉じる
        if pg.is_on_break and 0 <= getattr(pg, "active_break_index", -1) < len(pg.break_sessions):
            br = pg.break_sessions[pg.active_break_index]
            if br.start > 0.0:
                now = time.time()
                br.end = now
        pg.is_on_break = False
        pg.active_break_index = -1

        # 履歴削除
        pg.break_sessions.clear()
        self.report({"INFO"}, "Break history cleared")
        log.info("Break sessions cleared by user")
        return {"FINISHED"}


class TIMETRACKER_OT_debug_dump(Operator):
    """内部状態をダンプ（ハンドラ/タイマー/セッション/休憩/しきい値）"""

    bl_idname = "timetracker.debug_dump"
    bl_label = "Debug: Dump Tracker State"
    bl_description = "Dump handler, timer, session and break state for diagnostics"
    bl_options = {"REGISTER"}

    to_text: BoolProperty(name="To Text", default=True, options={"SKIP_SAVE"})
    to_console: BoolProperty(name="To Console", default=True, options={"SKIP_SAVE"})

    def execute(self, context):
        lines = []
        now = int(time.time())
        lines.append(f"[WTT Debug Dump] now={now}")

        # Preferences
        try:
            prefs = get_prefs(context)
            warn_th = int(getattr(prefs, "unsaved_warning_threshold_seconds", 600))
            break_th = int(getattr(prefs, "break_threshold_seconds", 300))
        except Exception:
            warn_th = 600
            break_th = 300
        lines.append(f"prefs: unsaved_warn={warn_th}s, break_threshold={break_th}s")

        # PG state
        pg = getattr(context.scene, "wtt_time_data", None)
        if pg:
            idle = max(0, now - int(getattr(pg, "last_activity_time", 0)))
            lines.append(
                f"pg: is_on_break={pg.is_on_break}, last_activity={pg.last_activity_time} (idle={idle}s), active_break_idx={pg.active_break_index}"
            )
            lines.append(
                f"pg: sessions={len(pg.sessions)}, active_session_idx={pg.active_session_index}, breaks={len(pg.break_sessions)}"
            )
        else:
            lines.append("pg: <none>")

        # Handlers registration
        is_load = core_time.load_handler in bpy.app.handlers.load_post
        is_save = core_time.save_handler in bpy.app.handlers.save_post
        is_dep = core_time.depsgraph_activity_handler in bpy.app.handlers.depsgraph_update_post
        lines.append(f"handlers: load_post={is_load}, save_post={is_save}, depsgraph_update_post={is_dep}")

        # Timer
        is_registered = False
        timer_api = getattr(bpy.app, "timers", None)
        if timer_api and hasattr(timer_api, "is_registered"):
            try:
                is_registered = bpy.app.timers.is_registered(core_time.update_time_callback)
            except Exception:
                is_registered = False
        lines.append(f"timer: registered={is_registered}, _timer_running={getattr(core_time, '_timer_running', None)}")

        # TimeData / sessions
        td = TimeDataManager.get_instance()
        td.ensure_loaded()
        cur = td.get_current_session()
        lines.append(f"total_time={format_time(td.total_time)}, current_session_time={format_time(td.get_current_session_time())}")
        if cur:
            lines.append(
                f"current_session: id={cur.id}, start={cur.start}, end={cur.end}"
            )
        # List recent breaks (max 5)
        if pg and len(pg.break_sessions) > 0:
            lines.append("breaks (recent):")
            for b in list(pg.break_sessions)[-5:]:
                bend = b.end if b.end > 0 else now
                dur = max(0, bend - b.start) if b.start > 0 else 0
                lines.append(
                    f"  - id={b.id}, sid={b.session_id}, start={b.start}, end={b.end}, dur={format_time(dur)}"
                )

        # Would start break?
        if pg:
            would_break = (not pg.is_on_break) and (max(0, now - pg.last_activity_time) >= max(30, break_th))
            lines.append(f"decision: would_break_now={would_break}")

        report = "\n".join(lines)

        if self.to_console:
            print(report)
        if self.to_text:
            name = f"WTT_Debug_{time.strftime('%Y%m%d_%H%M%S')}"
            text = bpy.data.texts.new(name)
            text.write(report)
            self.report({"INFO"}, f"Debug written to Text: {name}")
        else:
            self.report({"INFO"}, "Debug dump printed to console")
        return {"FINISHED"}
