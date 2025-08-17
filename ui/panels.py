"""
UIパネルモジュール - 時間トラッカーのUIパネルを提供
"""

import datetime
import time

from bpy.types import Panel, STATUSBAR_HT_header, UIList

from ..core.time_data import TimeDataManager
from ..utils.formatting import format_hours_minutes, format_time
from ..utils.logging import get_logger
from ..utils.ui_utils import ic, ui_prop
from ..addon import get_prefs

log = get_logger(__name__)


class WTT_UL_sessions(UIList):
    """作業セッション一覧"""

    bl_idname = "WTT_UL_sessions"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index
    ):
        # item は WTT_TimeSession
        row = layout.row(align=True)
        row.alignment = "LEFT"
        # 最小項目: 番号 / 合計(セッション)時間 / コメント編集
        row.label(text=f"#{item.id}")
        dur_sec = (
            item.duration
            if item.end > 0
            else (max(0.0, time.time() - item.start) if item.start > 0 else 0.0)
        )
        row.label(text=format_time(dur_sec))
        # コメントはpropで直接編集
        ui_prop(row, item, "comment", text="", emboss=False, placeholder="Comment")


class WTT_UL_breaks(UIList):
    """休憩セッション一覧"""

    bl_idname = "WTT_UL_breaks"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index
    ):
        # item は WTT_BreakSession
        row = layout.row(align=True)
        row.alignment = "LEFT"
        row.label(text=f"#{item.id}")

        dur = (
            item.duration
            if item.end > 0
            else (max(0.0, time.time() - item.start) if item.start > 0 else 0.0)
        )
        row.label(text=format_time(dur))
        # 休憩コメント編集
        ui_prop(row, item, "comment", text="", emboss=False, placeholder="Comment")


class VIEW3D_PT_time_tracker(Panel):
    """Time Tracker Panel"""

    bl_label = "Time Tracker"
    bl_idname = "VIEW3D_PT_time_tracker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Time"
    bl_ui_units_x = 15

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if not time_data:
            layout.label(text="Time tracker not initialized")
            return

        if self.is_popover:
            layout.label(text="Work Time Tracker", icon="TIME")
            layout.separator(type="LINE")

        if time_data:
            # Ensure data is loaded
            time_data.ensure_loaded()

            summary_box = layout.box()
            summary_col = summary_box.column()

            # File info
            if time_data.file_id:
                row = summary_col.row()
                row.label(text="File ID:")
                row.alert = not context.blend_data.is_saved
                row.label(text=time_data.file_id)

                if time_data.file_creation_time:
                    creation_time = datetime.datetime.fromtimestamp(
                        time_data.file_creation_time
                    )
                    row = summary_col.row()
                    row.label(text="Created:")
                    row.label(text=creation_time.strftime("%Y-%m-%d %H:%M"))

            # Display total time
            row = summary_col.row()
            row.label(text="Total Work Time:")
            row.label(text=time_data.get_formatted_total_time())

            # Display current session time
            row = summary_col.row()
            row.label(text="Current Session:")
            row.label(text=time_data.get_formatted_session_time())

            # Display time since last save
            time_since_save = time_data.get_time_since_last_save()
            row = summary_col.row()
            row.label(text="Time Since Save:")

            # Show warning if unsaved for too long
            prefs = get_prefs(context)
            warn_threshold = max(
                30, int(getattr(prefs, "unsaved_warning_threshold_seconds", 600))
            )
            if context.blend_data.is_dirty and time_since_save > warn_threshold:
                row = summary_col.row()
                row.alert = True
                row.label(text=f"{time_data.get_formatted_time_since_save()}")
                row_alert = summary_col.row()
                row_alert.alert = True
                row_alert.label(text="Consider saving your work!")
            else:
                row.label(text=time_data.get_formatted_time_since_save())

            row = summary_col.row()
            row.operator(
                "timetracker.export_data", text="Export Report", icon="TEXT"
            )

            # Sessions list
            # TODO: 前のセッションとマージできるようにする
            pg = getattr(context.scene, "wtt_time_data", None)
            sessions_box = layout.box()
            col = sessions_box.column()
            header = col.row()
            header.label(text="Sessions", icon="TEXT")
            if pg:
                col.template_list(
                    "WTT_UL_sessions",
                    "",
                    pg,
                    "sessions",
                    pg,
                    "active_session_index",
                    rows=4,
                )
            col.operator(
                "timetracker.switch_session", text="New Session", icon="FILE_REFRESH"
            )

            # Breaks
            breaks_box = layout.box()
            bc = breaks_box.column()
            h = bc.row()
            h.label(text="Breaks", icon=ic("SORTTIME"))
            if pg:
                # 状態表示
                # state_row = bc.row()
                # if pg.is_on_break:
                #     state_row.alert = True
                #     state_row.label(text="Now: On Break")
                # else:
                #     state_row.label(text="Now: Working")

                # アイドル経過
                idle = (
                    max(0.0, time.time() - pg.last_activity_time)
                    if pg.last_activity_time > 0
                    else 0.0
                )
                row = bc.row()
                row.alert = pg.is_on_break
                row.label(text="Idle:")
                state = "On Break" if pg.is_on_break else "Working"
                row.label(text=f"{format_time(idle)} ({state})")

                # 一覧
                bc.template_list(
                    "WTT_UL_breaks",
                    "",
                    pg,
                    "break_sessions",
                    pg,
                    "active_break_index",
                    rows=3,
                )

                # 操作
                ops = bc.row(align=True)
                ops.operator(
                    "timetracker.clear_breaks", text="Clear Breaks", icon=ic("TRASH")
                )

            # layout.separator()
            header, sub_panel = layout.panel(
                idname="time_tracker_subpanel", default_closed=True
            )
            header.label(text="Reset Data", icon="ERROR")
            if sub_panel:
                sub_panel.operator(
                    "timetracker.reset_session",
                    text="Reset Current Session",
                    icon="CANCEL",
                )
                sub_panel.alert = True
                sub_panel.operator(
                    "timetracker.reset_data", text="Reset All Session", icon="ERROR"
                )


def time_tracker_draw(self, context):
    """ステータスバーに時間情報を表示"""
    # TimeDataManagerからインスタンスを取得
    time_data = TimeDataManager.get_instance()
    if not time_data:
        log.warning("Time tracker not initialized")
        return

    layout = self.layout
    row = layout.row(align=True)

    total_time_str = format_hours_minutes(time_data.total_time)
    session_time_str = format_hours_minutes(time_data.get_current_session_time())

    # セッション表示
    td = TimeDataManager.get_instance()
    current = td.get_current_session() if td else None
    compact_text = f"{total_time_str} | {session_time_str}"
    row.popover(panel="VIEW3D_PT_time_tracker", text=compact_text, icon="TIME")

    # セッション切替
    sid = f"#{current['id']}" if current and "id" in current else "#-"
    row.operator("timetracker.switch_session", text=sid)

    row.separator()

    # 休憩状態
    pg = getattr(context.scene, "wtt_time_data", None)
    if pg and pg.is_on_break:
        row.label(text="On Break", icon=ic("SORTTIME"))

    # 未保存警告
    time_since_save = time_data.get_time_since_last_save()
    if not context.blend_data.is_saved:
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Unsaved File", icon="ERROR")
    else:
        prefs = get_prefs(context)
        warn_threshold = max(
            30, int(getattr(prefs, "unsaved_warning_threshold_seconds", 600))
        )
        if context.blend_data.is_dirty and time_since_save > warn_threshold:
            row_alert = row.row(align=True)
            row_alert.alert = True
            row_alert.label(text="Save Pending", icon="ERROR")


def register():
    STATUSBAR_HT_header.prepend(time_tracker_draw)


def unregister():
    STATUSBAR_HT_header.remove(time_tracker_draw)
