"""
UIパネルモジュール - 時間トラッカーのUIパネルを提供
"""

import datetime

import bpy

from ..core.time_data import TimeDataManager
from ..utils.formatting import format_hours_minutes

# Constants
UNSAVED_WARNING_THRESHOLD = 10 * 60  # 10 minutes in seconds


class VIEW3D_PT_time_tracker(bpy.types.Panel):
    """Time Tracker Panel"""

    bl_label = "Time Tracker"
    bl_idname = "VIEW3D_PT_time_tracker"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Time"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        # TimeDataManagerからインスタンスを取得
        time_data = TimeDataManager.get_instance()
        if not time_data:
            layout.label(text="Time tracker not initialized")
            return

        if time_data:
            # Ensure data is loaded
            time_data.ensure_loaded()

            # Display total time
            row = layout.row()
            row.label(text="Total Work Time:")
            row.label(text=time_data.get_formatted_total_time())

            # Display current session time
            row = layout.row()
            row.label(text="Current Session:")
            row.label(text=time_data.get_formatted_session_time())

            # Display time since last save
            time_since_save = time_data.get_time_since_last_save()
            row = layout.row()
            row.label(text="Time Since Save:")

            # Show warning if unsaved for too long
            if (
                context.blend_data.is_dirty
                and time_since_save > UNSAVED_WARNING_THRESHOLD
            ):
                # row_alert = layout.row()
                row.alert = True
                row.label(text=f"{time_data.get_formatted_time_since_save()}")
                row_alert = layout.row()
                row_alert.alert = True
                row_alert.label(text="Consider saving your work!")
            else:
                row.label(text=time_data.get_formatted_time_since_save())

            box = layout.box()
            row = box.row()
            row.label(text="Session Info:", icon="TEXT")

            # コメント表示/編集
            current_comment = time_data.get_session_comment()
            if current_comment:
                row = box.row()
                row.label(text=current_comment, icon="SMALL_CAPS")
            row = box.row()
            row.operator(
                "timetracker.edit_comment", text="Edit Comment", icon="GREASEPENCIL"
            )

            # File info
            if time_data.file_id:
                layout.separator()
                row = layout.row()
                row.label(text=f"File ID: {time_data.file_id}")

                if time_data.file_creation_time:
                    creation_time = datetime.datetime.fromtimestamp(
                        time_data.file_creation_time
                    )
                    row = layout.row()
                    row.label(
                        text=f"Created: {creation_time.strftime('%Y-%m-%d %H:%M')}"
                    )

            # layout.separator()
            layout.operator(
                "timetracker.switch_session", text="New Session", icon="FILE_REFRESH"
            )
            layout.operator(
                "timetracker.export_data", text="Export Report", icon="TEXT"
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
        print("Time tracker not initialized")
        return

    layout = self.layout
    row = layout.row(align=True)

    total_time_str = format_hours_minutes(time_data.total_time)
    session_time_str = format_hours_minutes(time_data.get_current_session_time())

    compact_text = f"{total_time_str} | {session_time_str}"

    row.popover(panel="VIEW3D_PT_time_tracker", text=compact_text, icon="TIME")

    row.separator()

    time_since_save = time_data.get_time_since_last_save()
    if not context.blend_data.is_saved:
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Unsaved File", icon="ERROR")
    elif context.blend_data.is_dirty and time_since_save > UNSAVED_WARNING_THRESHOLD:
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Save Pending", icon="ERROR")


def register():
    bpy.types.STATUSBAR_HT_header.prepend(time_tracker_draw)


def unregister():
    bpy.types.STATUSBAR_HT_header.remove(time_tracker_draw)
