"""
アドオンプリファレンス
"""

# pyright: reportInvalidTypeForm=false
from bpy.types import AddonPreferences
from bpy.props import IntProperty, BoolProperty, EnumProperty, StringProperty
from .addon import ADDON_ID, get_prefs
from .utils.logging import get_logger
import bpy

log = get_logger(__name__)


class WTT_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        # Sidebar (N Panel)
        sb = layout.column(heading="Sidebar (N Panel)")
        sb.prop(self, "show_in_n_panel", text="Show in N Panel")
        row = sb.row()
        row.enabled = bool(self.show_in_n_panel)
        row.prop(self, "n_panel_category", text="Category")

        # Popover
        pop = layout.column(heading="Popover")
        pop.prop(self, "show_in_statusbar", text="Show in Status Bar")
        row = pop.row()
        row.enabled = bool(self.show_in_statusbar)
        row.prop(self, "popover_panel_width", text="Panel Width")

        # Behavior
        beh = layout.column(heading="Behavior")
        beh.prop(self, "unsaved_warning_threshold_seconds")
        beh.prop(self, "break_threshold_seconds")

        # Debug
        dbg = layout.column(heading="Debug")
        dbg.prop(self, "debug_level", text="Debug Level")

    # パネルサイズ設定（Popover）
    popover_panel_width: IntProperty(
        name="Popover Panel Width",
        description="Width of the time tracker panel when displayed as popover (in UI units)",
        default=15,
        min=10,
        max=30,
    )

    # ステータスバー表示ON/OFF
    show_in_statusbar: BoolProperty(
        name="Show in Status Bar",
        description="Display compact tracker in the status bar",
        default=True,
        update=lambda self, context: self._apply_statusbar(context),
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

    # Nパネル関連
    show_in_n_panel: BoolProperty(
        name="Show in N Panel",
        description="Show the Time Tracker panel in the 3D Viewport sidebar (N panel)",
        default=True,
        update=lambda self, context: self._apply_sidebar_prefs(context),
    )

    n_panel_category: StringProperty(
        name="N Panel Category",
        description="Category tab name for the sidebar (N panel)",
        default="Time",
        maxlen=64,
        update=lambda self, context: self._apply_sidebar_prefs(context),
    )

    def _update_debug_level(self):
        """デバッグレベルが変更されたときにログレベルを更新"""
        log.set_level(self.debug_level.lower())
        log.info(f"Work Time Tracker: debug level set to {self.debug_level}")

    def _apply_sidebar_prefs(self, context):
        """Nパネルのカテゴリ名・表示状態の変更を反映"""
        panel_cls = getattr(bpy.types, "VIEW3D_PT_time_tracker", None)
        if panel_cls is None:
            return
        # カテゴリ名の適用（再登録）
        new_cat = (self.n_panel_category or "Time").strip() or "Time"
        if getattr(panel_cls, "bl_category", None) != new_cat:
            try:
                bpy.utils.unregister_class(panel_cls)
            except Exception:
                pass
            panel_cls.bl_category = new_cat
            try:
                bpy.utils.register_class(panel_cls)
            except Exception as ex:
                log.warning(f"Failed to re-register panel with new category: {ex}")
        # 再描画
        wm = context.window_manager if context else None
        if wm:
            for window in wm.windows:
                screen = window.screen
                if not screen:
                    continue
                for area in screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()

    def _apply_statusbar(self, context):
        try:
            from .ui.panels import enable_statusbar

            enable_statusbar(bool(self.show_in_statusbar))
        except Exception as ex:
            log.warning(f"Failed to apply statusbar visibility: {ex}")


def register():
    pr = get_prefs()
    pr._update_debug_level()
    # 起動時に現在の設定でサイドバー設定を反映
    try:
        pr._apply_sidebar_prefs(bpy.context)
    except Exception as ex:
        log.warning(f"Failed to apply initial sidebar prefs: {ex}")
    # ステータスバー表示初期反映
    try:
        from .ui.panels import enable_statusbar

        enable_statusbar(bool(getattr(pr, "show_in_statusbar", True)))
    except Exception as ex:
        log.warning(f"Failed to apply initial statusbar visibility: {ex}")
