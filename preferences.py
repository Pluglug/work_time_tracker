# pyright: reportInvalidTypeForm=false
from bpy.types import AddonPreferences
from .addon import ADDON_ID, get_prefs


class WTT_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    def draw(self, context):
        layout = self.layout
