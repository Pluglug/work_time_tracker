"""
ステータスバー（STATUSBAR_HT_header）への表示機能を提供
"""

import time
import datetime

from bpy.types import STATUSBAR_HT_header

from ..core.time_data import TimeDataManager
from ..utils.formatting import format_hours_minutes, format_time
from ..utils.logging import get_logger
from ..utils.ui_utils import ic
from ..addon import get_prefs

log = get_logger(__name__)


# ステータスバー描画の状態管理（重複登録防止）
_STATUSBAR_ENABLED = False


def time_tracker_draw(self, context):
    """ステータスバーに時間情報を表示"""
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
    sid = f"#{current.id}" if current and getattr(current, "id", None) else "#-"
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


def enable_statusbar(enabled: bool):
    global _STATUSBAR_ENABLED
    if enabled and not _STATUSBAR_ENABLED:
        STATUSBAR_HT_header.prepend(time_tracker_draw)
        _STATUSBAR_ENABLED = True
    elif not enabled and _STATUSBAR_ENABLED:
        try:
            STATUSBAR_HT_header.remove(time_tracker_draw)
        except Exception:
            pass
        _STATUSBAR_ENABLED = False


def register():
    # 何もしない（初期適用はpreferences.registerで行う）
    pass


def unregister():
    try:
        enable_statusbar(False)
    except Exception:
        pass
