"""
UIパネルモジュール - 時間トラッカーのUIパネルを提供
"""

import datetime

import bpy

from ..core.time_data import TimeDataManager
from ..utils.formatting import format_hours_minutes

# Constants
UNSAVED_WARNING_THRESHOLD = 10 * 60  # 10 minutes in seconds

# モジュールの依存関係を明示的に指定
# DEPENDS_ON = ["core.time_data", "utils.formatting"]


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

        # 現在のセッション情報
        current_session = time_data.get_current_session()
        if current_session:
            box = layout.box()
            row = box.row()
            row.label(text="Current Session", icon="TIME")

            # セッション時間
            session_time = time_data.get_current_session_time()
            row = box.row()
            row.label(text=f"Time: {time_data.format_time(session_time)}")

            # セッション開始時間
            if current_session.get("start"):
                start_time = datetime.datetime.fromtimestamp(
                    current_session["start"]
                )
                row = box.row()
                row.label(text=f"Started: {start_time.strftime('%H:%M:%S')}")

            # セッションコメント
            comment = current_session.get("comment", "")
            if comment:
                row = box.row()
                row.label(text=f"Comment: {comment}")
            
            row = box.row()
            row.operator(
                "timetracker.edit_comment", 
                text="Edit Comment", 
                icon="GREASEPENCIL"
            )

            # File info
            box = layout.box()
            row = box.row()
            row.label(text="File Info", icon="FILE_BLEND")

            # ファイル名
            if bpy.data.filepath:
                filename = bpy.path.basename(bpy.data.filepath)
                row = box.row()
                row.label(text=f"File: {filename}")

                # ファイル作成日時
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
                "timetracker.switch_session", 
                text="New Session", 
                icon="FILE_REFRESH"
            )
            layout.operator(
                "timetracker.export_data", 
                text="Export Report", 
                icon="TEXT"
            )

            # 合計時間
            box = layout.box()
            row = box.row()
            row.label(text="Total Time", icon="SORTTIME")
            row = box.row()
            row.label(text=time_data.get_formatted_total_time())

            # リセットボタン
            layout.operator(
                "timetracker.reset_session", 
                text="Reset Session", 
                icon="X"
            )

            # 危険な操作は別のパネルに
            layout.separator()
            box = layout.box()
            sub_panel = box.column()
            sub_panel.label(text="Danger Zone", icon="ERROR")
            sub_panel.alert = True
            sub_panel.operator(
                "timetracker.reset_data", 
                text="Reset All Session", 
                icon="ERROR"
            )


def time_tracker_draw(self, context):
    """ステータスバーに時間情報を表示"""
    # TimeDataManagerからインスタンスを取得
    time_data = TimeDataManager.get_instance()
    if not time_data:
        print("Time tracker not initialized")
        return

    # 時間データを取得
    total_time_str = format_hours_minutes(time_data.total_time)
    session_time_str = format_hours_minutes(
        time_data.get_current_session_time()
    )

    compact_text = f"{total_time_str} | {session_time_str}"

    # ステータスバーに表示
    layout = self.layout
    row = layout.row(align=True)
    row.label(text=f"Work Time: {compact_text}")

    # 未保存警告
    time_since_save = time_data.get_time_since_last_save()
    if not bpy.data.filepath:
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Unsaved File", icon="ERROR")
    elif (context.blend_data.is_dirty and 
          time_since_save > UNSAVED_WARNING_THRESHOLD):
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Save Pending", icon="ERROR")


def register():
    bpy.types.STATUSBAR_HT_header.prepend(time_tracker_draw)


def unregister():
    bpy.types.STATUSBAR_HT_header.remove(time_tracker_draw)
