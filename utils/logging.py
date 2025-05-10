# pyright: reportInvalidTypeForm=false

"""
# Usage
from ..utils.logging import get_logger
log = get_logger(__name__)

log.debug("This is a debug message")
log.info("This is an info message")
log.warning("This is a warning message")
log.error("This is an error message")
log.critical("This is a critical message")
"""

import datetime
import logging
import os
import sys
import traceback
from collections import deque
import threading

from ..addon import ADDON_ID

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
    def __init__(self, capacity=1000):
        super().__init__()
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)
        self._lock = threading.RLock()

    def emit(self, record):
        try:
            with self._lock:
                self.buffer.append(record)
        except Exception as e:
            print(f"MemoryHandler emit error: {str(e)}", file=sys.stderr)

    def get_records(self):
        with self._lock:
            return list(self.buffer)

    def clear(self):
        with self._lock:
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
        self.logger.propagate = False  # 親ロガーへの伝播を無効化

        self.memory_handler = MemoryHandler()
        # 初期状態ではコンソール/ファイルハンドラはNone
        self.console_handler = None
        self.file_handler = None

        # MemoryHandlerは常に最初に1つだけ追加
        # リロード時に重複しないように、既に追加済みか確認
        if not any(isinstance(h, MemoryHandler) for h in self.logger.handlers):
            self.logger.addHandler(self.memory_handler)

    def configure(self, config, module_name=None):
        """設定を更新"""
        module_name = module_name or self.module_name
        default_level = getattr(logging, config.log_level)

        module_level = default_level
        matched_config = None

        for module_config in config.modules:
            # モジュール名のマッチングロジック
            is_match = (
                module_config.name == module_name  # 完全一致
                or module_name.endswith(module_config.name)  # 部分一致
            )

            if is_match and module_config.enabled:
                module_level = getattr(logging, module_config.log_level)
                matched_config = module_config
                break

        self.logger.setLevel(module_level)

        # # デバッグ情報
        # if matched_config:
        #     print(
        #         f"DEBUG: Module '{module_name}' matched with config '{matched_config.name}'"
        #     )
        #     print(
        #         f"DEBUG: Log level set to {matched_config.log_level} ({module_level})"
        #     )
        # else:
        #     print(
        #         f"DEBUG: Module '{module_name}' using default log level {config.log_level} ({module_level})"
        #     )

        # --- コンソールハンドラのガード処理 ---
        has_console_handler = any(
            isinstance(h, logging.StreamHandler) for h in self.logger.handlers
        )

        if config.log_to_console and not has_console_handler:
            # 既存ハンドラがない場合のみ追加
            self.console_handler = logging.StreamHandler()
            formatter = (
                ColoredFormatter("%(name)s - %(levelname)s: %(message)s")
                if config.use_colors
                else logging.Formatter("%(name)s - %(levelname)s: %(message)s")
            )
            self.console_handler.setFormatter(formatter)
            self.logger.addHandler(self.console_handler)
            # print(f"DEBUG: Added console handler for {module_name}") # デバッグ用
        elif not config.log_to_console and has_console_handler:
            # 設定が無効で既存ハンドラがある場合は削除
            # 複数のStreamHandlerがある可能性も考慮し、全て削除する（通常は1つのはずだが念のため）
            for handler in list(
                self.logger.handlers
            ):  # イテレート中に削除するためコピー
                if isinstance(handler, logging.StreamHandler):
                    self.logger.removeHandler(handler)
            self.console_handler = None  # 参照もクリア
            # print(f"DEBUG: Removed console handler for {module_name}") # デバッグ用

        # --- ファイルハンドラのガード処理 ---
        has_file_handler = any(
            isinstance(h, logging.FileHandler) for h in self.logger.handlers
        )
        current_file_path = (
            self.file_handler.baseFilename if self.file_handler else None
        )

        if config.log_to_file and config.log_file_path:
            log_dir = os.path.dirname(config.log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            # ファイルハンドラがない、またはパスが変わった場合のみ再作成/追加
            if not has_file_handler or current_file_path != config.log_file_path:
                # 既存があればまず削除
                if has_file_handler:
                    for handler in list(self.logger.handlers):
                        if isinstance(handler, logging.FileHandler):
                            self.logger.removeHandler(handler)

                self.file_handler = logging.FileHandler(
                    config.log_file_path, encoding="utf-8"
                )
                formatter = logging.Formatter(
                    "%(asctime)s [%(name)s] [%(levelname)s] %(message)s"
                )
                self.file_handler.setFormatter(formatter)
                self.logger.addHandler(self.file_handler)
                # print(f"DEBUG: Added/Updated file handler for {module_name} to {config.log_file_path}") # デバッグ用

        elif not config.log_to_file and has_file_handler:
            # 設定が無効で既存ハンドラがある場合は削除
            for handler in list(self.logger.handlers):
                if isinstance(handler, logging.FileHandler):
                    self.logger.removeHandler(handler)
            self.file_handler = None  # 参照もクリア
            # print(f"DEBUG: Removed file handler for {module_name}") # デバッグ用

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
        try:
            exc_info = sys.exc_info()
            if exc_info[0] is None:  # 例外が発生していない場合
                self.logger.warning("No exception to capture")
                return None

            tb_text = "".join(traceback.format_exception(*exc_info))
            error_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

            info = f"Error ID: {error_id}\n{tb_text}"
            if additional_info:
                try:
                    info += f"\nAdditional Info: {str(additional_info)}"
                except Exception as e:
                    self.logger.error(f"Failed to format additional info: {str(e)}")

            self.logger.error(info)
            return error_id
        except Exception as e:
            print(f"Failed to capture exception: {str(e)}", file=sys.stderr)
            return None

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


def get_logger(module_name: str = ADDON_ID) -> AddonLogger:
    """Get a logger for a module"""
    return LoggerRegistry.get_logger(module_name)
