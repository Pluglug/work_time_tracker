import datetime
import logging
import os
import sys
import traceback
from collections import deque
from enum import Enum

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, PropertyGroup

# ANSIカラーコード
COLORS = {
    "RESET": "\033[0m",
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[31;1m",  # Bold Red
}


class ColoredFormatter(logging.Formatter):
    """コンソール向けカラーフォーマッタ"""

    def format(self, record):
        color = COLORS.get(record.levelname, COLORS["RESET"])
        message = super().format(record)
        return f"{color}{message}{COLORS['RESET']}"


class MemoryHandler(logging.Handler):
    """ログをメモリに保持するハンドラ"""

    def __init__(self, capacity=1000):
        super().__init__()
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)

    def emit(self, record):
        self.buffer.append(record)

    def get_records(self):
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()


class LoggerRegistry:
    """ロガーレジストリ - すべてのロガーインスタンスを管理"""

    _loggers = {}
    _config = None

    @classmethod
    def get_logger(cls, module_name):
        """モジュール名でロガーを取得（なければ作成）"""
        if module_name not in cls._loggers:
            logger = AddonLogger(module_name)
            cls._loggers[module_name] = logger
            # 既存の設定があれば適用
            if cls._config:
                logger.configure(cls._config, module_name)
        return cls._loggers[module_name]

    @classmethod
    def configure_all(cls, config):
        """すべてのロガーに設定を適用"""
        cls._config = config
        for module_name, logger in cls._loggers.items():
            logger.configure(config, module_name)

    @classmethod
    def get_all_loggers(cls):
        """登録されているすべてのロガーを取得"""
        return cls._loggers

    @classmethod
    def export_all_logs(cls, file_path):
        """すべてのロガーのログをエクスポート"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for module_name, logger in sorted(cls._loggers.items()):
                    f.write(f"\n=== Module: {module_name} ===\n")
                    for record in logger.memory_handler.get_records():
                        f.write(f"[{record.levelname}] {record.msg}\n")
            return True
        except Exception as e:
            # エラーを報告するためのロガーがない可能性があるので、標準エラー出力を使用
            print(f"Log export failed: {str(e)}", file=sys.stderr)
            return False


class AddonLogger:
    """アドオン用ロガークラス"""

    def __init__(self, module_name):
        self.module_name = module_name
        self.logger = logging.getLogger(module_name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        self.memory_handler = MemoryHandler()
        self.console_handler = None
        self.file_handler = None

        self.logger.addHandler(self.memory_handler)

    def configure(self, config, module_name=None):
        """設定を更新"""
        # 使用するモジュール名を決定
        module_name = module_name or self.module_name

        # デフォルトログレベルを取得
        default_level = getattr(logging, config.log_level)

        # モジュール別の設定があれば、そのログレベルを使用
        module_level = default_level
        for module_config in config.modules:
            if module_config.name == module_name and module_config.enabled:
                module_level = getattr(logging, module_config.log_level)
                break

        # ロガーのレベルを設定
        self.logger.setLevel(module_level)

        # コンソールハンドラ
        if config.log_to_console and not self.console_handler:
            self.console_handler = logging.StreamHandler()
            self.console_handler.setFormatter(
                ColoredFormatter("%(name)s - %(levelname)s: %(message)s")
                if config.use_colors
                else logging.Formatter("%(name)s - %(levelname)s: %(message)s")
            )
            self.logger.addHandler(self.console_handler)
        elif not config.log_to_console and self.console_handler:
            self.logger.removeHandler(self.console_handler)
            self.console_handler = None

        # ファイルハンドラ
        if config.log_to_file and config.log_file_path:
            # ディレクトリが存在しない場合は作成
            log_dir = os.path.dirname(config.log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            if (
                not self.file_handler
                or self.file_handler.baseFilename != config.log_file_path
            ):
                if self.file_handler:
                    self.logger.removeHandler(self.file_handler)
                self.file_handler = logging.FileHandler(
                    config.log_file_path, encoding="utf-8"
                )
                self.file_handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s [%(name)s] [%(levelname)s] %(message)s"
                    )
                )
                self.logger.addHandler(self.file_handler)
        elif not config.log_to_file and self.file_handler:
            self.logger.removeHandler(self.file_handler)
            self.file_handler = None

        self.memory_handler.capacity = config.memory_capacity

    def debug(self, message):
        """デバッグレベルのログを記録"""
        self.logger.debug(message)

    def info(self, message):
        """情報レベルのログを記録"""
        self.logger.info(message)

    def warning(self, message):
        """警告レベルのログを記録"""
        self.logger.warning(message)

    def error(self, message):
        """エラーレベルのログを記録"""
        self.logger.error(message)

    def critical(self, message):
        """致命的エラーのログを記録"""
        self.logger.critical(message)

    def capture_exception(self, additional_info=None):
        """例外をキャプチャしてログに記録"""
        exc_info = sys.exc_info()
        tb_text = "".join(traceback.format_exception(*exc_info))
        error_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        info = f"Error ID: {error_id}\n{tb_text}"
        if additional_info:
            info += f"\nAdditional Info: {additional_info}"

        self.logger.error(info)
        return error_id

    def section(self, title, level=logging.INFO):
        """セクション区切りデコレータ"""

        def decorator(func):
            def wrapper(*args, **kwargs):
                self.logger.log(level, f"=== {title} ===")
                try:
                    return func(*args, **kwargs)
                finally:
                    self.logger.log(level, f"=== End: {title} ===")

            return wrapper

        return decorator

    def timer(self, message=None):
        """実行時間計測デコレータ"""

        def decorator(func):
            def wrapper(*args, **kwargs):
                start = datetime.datetime.now()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed = datetime.datetime.now() - start
                    msg = message or f"{func.__name__} executed"
                    self.logger.info(f"{msg} in {elapsed.total_seconds():.2f}s")

            return wrapper

        return decorator

    def export_logs(self, file_path):
        """ログをファイルにエクスポート"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for record in self.memory_handler.get_records():
                    f.write(f"[{record.levelname}] {record.msg}\n")
            return True
        except Exception as e:
            self.logger.error(f"Log export failed: {str(e)}")
            return False


# # シンプルなモジュールロガー設定
# class ModuleLoggerSettings(PropertyGroup):
#     """モジュール別ロガー設定"""

#     name: StringProperty(
#         name="Module Name", description="ロギング設定を適用するモジュール名"
#     )

#     enabled: BoolProperty(
#         name="Enable", description="このモジュールの個別設定を有効にする", default=True
#     )

#     log_level: EnumProperty(
#         items=[
#             ("DEBUG", "Debug", "詳細なデバッグ情報"),
#             ("INFO", "Info", "一般的な情報"),
#             ("WARNING", "Warning", "警告のみ"),
#             ("ERROR", "Error", "エラーのみ"),
#             ("CRITICAL", "Critical", "致命的なエラーのみ"),
#         ],
#         name="Log Level",
#         description="このモジュールのログレベル",
#         default="DEBUG",
#     )


# class AddonLoggerPreferencesMixin:
#     """アドオンプリファレンス向けMixinクラス"""

#     log_enable: BoolProperty(
#         name="Enable Logging",
#         description="ロギングシステムを有効化",
#         default=True,
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     log_level: EnumProperty(
#         items=[
#             ("DEBUG", "Debug", "詳細なデバッグ情報"),
#             ("INFO", "Info", "一般的な情報"),
#             ("WARNING", "Warning", "警告のみ"),
#             ("ERROR", "Error", "エラーのみ"),
#             ("CRITICAL", "Critical", "致命的なエラーのみ"),
#         ],
#         name="Log Level",
#         description="デフォルトのログレベル",
#         default="DEBUG",
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     log_to_console: BoolProperty(
#         name="Console Logging",
#         description="コンソールにログを出力",
#         default=True,
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     use_colors: BoolProperty(
#         name="Use Colors",
#         description="コンソール出力に色を使用",
#         default=True,
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     log_to_file: BoolProperty(
#         name="File Logging",
#         description="ファイルにログを出力",
#         default=False,
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     log_file_path: StringProperty(
#         name="Log File",
#         description="ログファイルのパス",
#         subtype="FILE_PATH",
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     memory_capacity: IntProperty(
#         name="Memory Capacity",
#         description="メモリに保持するログの最大数",
#         default=1000,
#         min=100,
#         max=10000,
#         update=lambda self, context: self.update_logger_settings(context),
#     )

#     # モジュール設定のコレクション
#     modules: CollectionProperty(type=ModuleLoggerSettings)
#     active_module_index: IntProperty(default=0)

#     def draw_logger_preferences(self, layout):
#         """ロガー設定UI描画"""
#         box = layout.box()
#         box.label(text="Logging Settings", icon="CONSOLE")
#         row = box.row()
#         row.prop(self, "log_enable")

#         if not self.log_enable:
#             return

#         # row = box.row()
#         # row.prop(self, "log_level", text="Default Level")

#         row = box.row()
#         row.prop(self, "log_to_console")
#         # if self.log_to_console:
#         #     row.prop(self, "use_colors")

#         row = box.row()
#         row.prop(self, "log_to_file")
#         if self.log_to_file:
#             row = box.row()
#             row.prop(self, "log_file_path")

#         row = box.row()
#         row.prop(self, "memory_capacity")

#         row.separator()

#         # モジュール設定セクション（読み取り専用のリスト）
#         if len(self.modules) > 0:
#             box.label(text="Module Settings")
#             row = box.row()
#             row.template_list(
#                 "LOGGER_UL_modules", "", self, "modules", self, "active_module_index"
#             )

#             # アクティブなモジュール設定を表示
#             # if self.active_module_index < len(self.modules):
#             #     module = self.modules[self.active_module_index]
#             #     row = box.row()
#             #     row.prop(module, "enabled")
#             #     if module.enabled:
#             #         row.prop(module, "log_level")

#             # モジュール設定を変更したらアップデートボタンを表示
#             row = box.row()
#             row.operator("logger.update_settings", text="Apply Module Settings")

#         # ログ操作ボタン
#         row = box.row()
#         row.operator("logger.export_logs", text="Export Logs")
#         row.operator("logger.clear_logs", text="Clear Logs")

#     def update_logger_settings(self, context=None):
#         """ロガー設定を更新"""
#         if not hasattr(self, "log_enable") or not self.log_enable:
#             return

#         # 自動でログファイルパスを設定
#         if self.log_to_file and not self.log_file_path:
#             addon_name = self.bl_idname.split(".")[0]
#             log_dir = os.path.join(
#                 bpy.utils.user_resource("CONFIG"), addon_name, "logs"
#             )
#             os.makedirs(log_dir, exist_ok=True)
#             today = datetime.datetime.now().strftime("%Y-%m-%d")
#             self.log_file_path = os.path.join(log_dir, f"{addon_name}_{today}.log")

#         # すべてのロガーに設定を適用
#         LoggerRegistry.configure_all(self)

#     def register_module(self, module_name, log_level="INFO"):
#         """モジュール設定を登録（既存の場合は更新）"""
#         # 既存のモジュールを探す
#         for module in self.modules:
#             if module.name == module_name:
#                 module.log_level = log_level
#                 return

#         # 新しいモジュールを追加
#         module = self.modules.add()
#         module.name = module_name
#         module.enabled = True
#         module.log_level = log_level

#     def register_modules(self, module_config):
#         """複数のモジュール設定を一度に登録

#         Args:
#             module_config: Dict[str, str] - モジュール名とログレベルのマッピング
#                 例: {"my_addon.core": "DEBUG", "my_addon.ui": "INFO"}
#         """
#         for module_name, log_level in module_config.items():
#             self.register_module(module_name, log_level)

#     def get_logger(self, module_name):
#         """モジュール用のロガーを取得"""
#         return LoggerRegistry.get_logger(module_name)


# class LOGGER_UL_modules(bpy.types.UIList):
#     """モジュール設定リスト表示"""

#     def draw_item(
#         self, context, layout, data, item, icon, active_data, active_propname
#     ):
#         if self.layout_type in {"DEFAULT", "COMPACT"}:
#             row = layout.row()
#             row.prop(item, "name", text="", emboss=False)
#             icon = "CHECKBOX_HLT" if item.enabled else "CHECKBOX_DEHLT"
#             row.prop(item, "enabled", text="", icon=icon, emboss=False)
#             row.prop(item, "log_level", text="")


# class LOGGER_OT_update_settings(bpy.types.Operator):
#     """ロガー設定を更新"""

#     bl_idname = "logger.update_settings"
#     bl_label = "Update Logger Settings"
#     bl_options = {"REGISTER", "INTERNAL"}

#     def execute(self, context):
#         # アドオン設定を取得
#         from ..addon import prefs

#         pr = prefs()
#         if hasattr(pr, "update_logger_settings"):
#             pr.update_logger_settings(context)
#             self.report({"INFO"}, "Logger settings updated")
#             return {"FINISHED"}

#         self.report({"ERROR"}, "Failed to update logger settings")
#         return {"CANCELLED"}


# class LOGGER_OT_export_logs(bpy.types.Operator):
#     """ログをエクスポートするオペレータ"""

#     bl_idname = "logger.export_logs"
#     bl_label = "Export Logs"
#     bl_options = {"REGISTER", "INTERNAL"}

#     filepath: StringProperty(subtype="FILE_PATH")

#     def execute(self, context):
#         if LoggerRegistry.export_all_logs(self.filepath):
#             self.report({"INFO"}, f"Logs exported to {self.filepath}")
#         else:
#             self.report({"ERROR"}, "Failed to export logs")
#         return {"FINISHED"}

#     def invoke(self, context, event):
#         # デフォルトパスを設定
#         addon_id = getattr(context.preferences, "active_addon", None)
#         if addon_id:
#             addon_name = addon_id.split(".")[0]
#             file_dir = os.path.join(
#                 bpy.utils.user_resource("CONFIG"), addon_name, "logs"
#             )
#             os.makedirs(file_dir, exist_ok=True)
#             timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
#             self.filepath = os.path.join(file_dir, f"logs_{timestamp}.txt")

#         context.window_manager.fileselect_add(self)
#         return {"RUNNING_MODAL"}


# class LOGGER_OT_clear_logs(bpy.types.Operator):
#     """すべてのログをクリア"""

#     bl_idname = "logger.clear_logs"
#     bl_label = "Clear Logs"
#     bl_options = {"REGISTER", "INTERNAL"}

#     def execute(self, context):
#         # すべてのロガーのメモリハンドラをクリア
#         for module_name, logger in LoggerRegistry.get_all_loggers().items():
#             logger.memory_handler.clear()

#         self.report({"INFO"}, "All logs cleared")
#         return {"FINISHED"}


# # ユーティリティ関数
# def get_logger(module_name: str) -> AddonLogger:
#     """モジュール用のロガーを取得（ショートカット関数）"""
#     return LoggerRegistry.get_logger(module_name)


# def register():
#     from ..addon import prefs

#     pr = prefs()

#     mods = LoggerRegistry.get_all_loggers()
#     for module_name, logger in mods.items():
#         pr.register_module(module_name, "DEBUG")

#     pr.update_logger_settings()


# 使用例 - 実際のアドオンでの利用方法
"""
from ..utils.logging import get_logger
log = get_logger(__name__)

log.debug("This is a debug message")
log.info("This is an info message")
log.warning("This is a warning message")
log.error("This is an error message")
log.critical("This is a critical message")
"""
