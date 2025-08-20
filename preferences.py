"""
アドオンプリファレンス
"""

# pyright: reportInvalidTypeForm=false
from bpy.types import AddonPreferences
from bpy.props import IntProperty, BoolProperty, EnumProperty
from .addon import ADDON_ID, get_prefs
from .utils.logging import get_logger

log = get_logger(__name__)


class WTT_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column()
        col.prop(self, "popover_panel_width", text="Popover Panel Width")
        col.prop(self, "unsaved_warning_threshold_seconds")
        col.prop(self, "break_threshold_seconds")
        col.prop(self, "debug_level", text="Debug Level", icon="CONSOLE")

    # パネルサイズ設定
    popover_panel_width: IntProperty(
        name="Popover Panel Width",
        description="Width of the time tracker panel when displayed as popover (in UI units)",
        default=15,
        min=10,
        max=30,
    )

    debug_level: EnumProperty(
        name="デバッグレベル",
        description="ログ出力の詳細レベルを設定します",
        items=[
            ("DEBUG", "Debug", "最も詳細なログ出力"),
            ("INFO", "Info", "一般的な情報のログ出力"),
            ("WARNING", "Warning", "警告とエラーのみ"),
            ("ERROR", "Error", "エラーのみ"),
        ],
        default="INFO",
        update=lambda self, context: self._update_debug_level(),
    )

    # 共通設定
    unsaved_warning_threshold_seconds: IntProperty(
        name="Unsaved Warning Threshold (sec)",
        description="Show warning when time since last save exceeds this threshold",
        default=600,
        min=30,
        max=24 * 3600,
    )

    break_threshold_seconds: IntProperty(
        name="Break Threshold (sec)",
        description="Inactivity duration considered as break",
        default=300,
        min=30,
        max=3600,
    )

    def _update_debug_level(self):
        """デバッグレベルが変更されたときにログレベルを更新"""
        log.set_level(self.debug_level.lower())
        log.info(f"Work Time Tracker: debug level set to {self.debug_level}")


def register():
    pr = get_prefs()
    pr._update_debug_level()
