"""
アドオンプリファレンス
"""

# pyright: reportInvalidTypeForm=false
from bpy.types import AddonPreferences
from bpy.props import IntProperty, BoolProperty
from .addon import ADDON_ID


class WTT_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="Work Time Tracker Settings")
        col.prop(self, "unsaved_warning_threshold_seconds")
        col.prop(self, "break_threshold_seconds")

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
