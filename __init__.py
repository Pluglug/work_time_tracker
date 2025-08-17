"""
Work Time Tracker - Blenderでの作業時間を追跡するアドオン
"""

bl_info = {
    "name": "Work Time Tracker",
    "author": "Pluglug",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Time Tracker",
    "description": "Tracks working time in Blender sessions",
    "warning": "",
    "doc_url": "",
    "category": "Utility",
}

use_reload = "addon" in locals()
if use_reload:
    import importlib

    importlib.reload(locals()["addon"])

    del importlib

from . import addon

# アドオンの初期化
addon.init_addon(
    module_patterns=[
        "core.*",
        "ui.*",
        "operators.*",
        "utils.*",
        "preferences",
    ],
    use_reload=use_reload,
)


def register():
    addon.register_modules()


def unregister():
    addon.unregister_modules()


if __name__ == "__main__":
    register()
