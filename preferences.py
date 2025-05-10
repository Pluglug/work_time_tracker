# pyright: reportInvalidTypeForm=false
import bpy
from bpy.types import AddonPreferences
from bpy.props import PointerProperty

from .addon import ADDON_ID, get_prefs
from .utils.logging import LoggerRegistry
from .ui.logger_prefs import WTT_LoggerPreferences


class WTT_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    logger_prefs: PointerProperty(type=WTT_LoggerPreferences)

    def draw(self, context):
        layout = self.layout

        WTT_LoggerPreferences.draw(self.logger_prefs, layout)


def register():
    context = bpy.context
    l_pr = get_prefs(context).logger_prefs
    mods = LoggerRegistry.get_all_loggers()
    current_module_names = {m.name for m in l_pr.modules}

    for module_name, logger in mods.items():
        if module_name not in current_module_names:
            l_pr.register_module(module_name, "INFO")

        for module in l_pr.modules:
            module.log_level = "INFO"

        l_pr.update_logger_settings(context)
