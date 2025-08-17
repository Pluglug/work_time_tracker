# pyright: reportInvalidTypeForm=false
"""
時間データ管理モジュール
"""

import datetime
import os
import time

import bpy
from bpy.app.handlers import persistent
from bpy.types import PropertyGroup
from bpy.props import (
    FloatProperty,
    IntProperty,
    StringProperty,
    CollectionProperty,
    PointerProperty,
)

from ..utils.formatting import format_time
from ..utils.logging import get_logger

log = get_logger(__name__)

DATA_VERSION = 1  # データ形式のバージョン管理用

timer = None


class WTT_TimeSession(PropertyGroup):
    """セッション情報 (PropertyGroup)"""

    id: IntProperty(name="ID", default=0)
    start: FloatProperty(name="Start", default=0.0)
    end: FloatProperty(name="End", default=0.0)  # 0.0 はアクティブ（未終了）
    duration: FloatProperty(name="Duration", default=0.0)
    file_id: StringProperty(name="File ID", default="")
    date: StringProperty(name="Date", default="")
    comment: StringProperty(name="Comment", default="")


class WTT_TimeData(PropertyGroup):
    """時間データ (PropertyGroup)"""

    version: IntProperty(name="Version", default=DATA_VERSION)
    total_time: FloatProperty(name="Total Time", default=0.0)
    last_save_time: FloatProperty(name="Last Save Time", default=0.0)
    file_creation_time: FloatProperty(name="File Creation Time", default=0.0)
    file_id: StringProperty(name="File ID", default="")
    sessions: CollectionProperty(type=WTT_TimeSession)
    active_session_index: IntProperty(name="Active Session Index", default=-1)




class TimeData:
    """時間データを管理するクラス"""

    def __init__(self):
        self.total_time = 0
        self.last_save_time = time.time()
        self.sessions = []
        self.file_creation_time = time.time()
        self.file_id = None
        self.current_session_start = None
        self.data_loaded = False  # このフラグは必要

        log.debug("TimeData initialized")

    # PropertyGroup 同期ヘルパー -----------------------------
    def _pg(self):
        """Sceneに紐づくPropertyGroupを取得"""
        scene = getattr(bpy.context, "scene", None)
        if not scene:
            return None
        return getattr(scene, "wtt_time_data", None)

    def _sync_from_pg(self):
        """PropertyGroupからローカル属性へ同期"""
        pg = self._pg()
        if not pg:
            return
        self.total_time = float(pg.total_time)
        self.last_save_time = float(pg.last_save_time) if pg.last_save_time else time.time()
        self.file_creation_time = float(pg.file_creation_time) if pg.file_creation_time else time.time()
        if pg.file_id:
            self.file_id = pg.file_id

        sessions = []
        for item in pg.sessions:
            sessions.append(
                {
                    "id": int(item.id),
                    "start": float(item.start),
                    "end": None if item.end <= 0.0 else float(item.end),
                    "duration": float(item.duration),
                    "file_id": item.file_id,
                    "date": item.date,
                    "comment": item.comment,
                }
            )
        self.sessions = sessions
        current = self.get_current_session()
        self.current_session_start = current["start"] if current else None

    def _sync_to_pg(self):
        """ローカル属性からPropertyGroupへ同期"""
        pg = self._pg()
        if not pg:
            return
        pg.version = DATA_VERSION
        pg.total_time = float(self.total_time)
        pg.last_save_time = float(self.last_save_time)
        pg.file_creation_time = float(self.file_creation_time)
        pg.file_id = self.file_id or ""

        pg.sessions.clear()
        for s in self.sessions:
            item = pg.sessions.add()
            item.id = int(s.get("id", 0))
            item.start = float(s.get("start", 0.0))
            end_val = s.get("end", None)
            item.end = 0.0 if end_val is None else float(end_val)
            item.duration = float(s.get("duration", 0.0))
            item.file_id = s.get("file_id", "")
            item.date = s.get("date", "")
            item.comment = s.get("comment", "")

        active_idx = -1
        for i, s in enumerate(self.sessions):
            if s.get("end") is None:
                active_idx = i
        pg.active_session_index = active_idx

    def reset(self):
        """すべてのデータをデフォルト値にリセットする"""
        self.total_time = 0
        self.last_save_time = time.time()
        self.sessions = []
        self.file_creation_time = time.time()
        self.current_session_start = None

    def ensure_loaded(self):
        """データが読み込まれていることを保証する（Blenderが完全に初期化された後で安全に呼び出せる）"""
        if not self.data_loaded:
            self.load_data()
            self.data_loaded = True

    def start_session(self):
        """セッションを開始 - ファイル読み込み時のみ呼び出す"""
        # アクティブなセッションがあるか確認
        active_sessions = [s for s in self.sessions if s.get("end") is None]

        if active_sessions:
            log.warning(
                f"{len(active_sessions)} active sessions found, ending them first"
            )
            self.end_active_sessions()

        # 新しいセッションを開始
        self.current_session_start = time.time()
        session_id = len(self.sessions) + 1

        self.sessions.append(
            {
                "id": session_id,
                "start": self.current_session_start,
                "end": None,
                "duration": 0.0,
                "file_id": self.file_id,
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "comment": "",
            }
        )

        log.info(
            f"Started session #{session_id} at "
            f"{datetime.datetime.fromtimestamp(self.current_session_start)}"
        )
        # PGへ同期
        self._sync_to_pg()
        return session_id

    def switch_session(self):
        """現在のセッションを終了し、新しいセッションを開始する"""
        # アクティブなセッションを終了
        ended_count = self.end_active_sessions()
        if ended_count == 0:
            log.info("No active sessions to end")
        else:
            log.info(f"Ended {ended_count} active sessions")

        # 新しいセッションを開始
        new_session_id = self.start_session()
        log.info(f"Started new session #{new_session_id}")

        # データを保存
        self.save_data()
        return True

    def reset_current_session(self):
        """現在のセッションをリセットする"""
        if not self.sessions:
            return False

        # 最後のセッションを取得
        current_session = next(
            (s for s in reversed(self.sessions) if s.get("end") is None), None
        )
        if not current_session:
            return False

        # 古いセッション時間を計算
        old_duration = time.time() - current_session["start"]

        # 開始時間を現在時刻に更新
        current_session["start"] = time.time()
        current_session["duration"] = 0

        # トータル時間から古いセッション時間を引く
        self.total_time -= old_duration

        # 現在のセッション開始時間も更新
        self.current_session_start = current_session["start"]

        # PGへ同期して保存
        self._sync_to_pg()
        self.save_data()
        return True

    def end_active_sessions(self):
        """アクティブなセッションを終了する"""
        end_time = time.time()
        ended_count = 0

        for session in self.sessions:
            if session.get("end") is None:
                session["end"] = end_time
                session["duration"] = session["end"] - session["start"]
                log.info(
                    f"Ended session #{session.get('id', '?')}: "
                    f"{datetime.datetime.fromtimestamp(session['start'])} to "
                    f"{datetime.datetime.fromtimestamp(session['end'])}"
                )
                ended_count += 1

        if ended_count > 0:
            # トータル時間を更新
            self.total_time = sum(
                session.get("duration", 0) for session in self.sessions
            )
            log.info(f"Updated total time: {format_time(self.total_time)}")
            self._sync_to_pg()

        return ended_count

    def get_current_session(self):
        """現在のアクティブなセッションを取得する"""
        if not self.sessions:
            return None
        return next((s for s in reversed(self.sessions) if s.get("end") is None), None)

    def set_session_comment(self, comment):
        """現在のセッションにコメントを設定する"""
        current_session = self.get_current_session()
        if current_session:
            current_session["comment"] = comment
            self._sync_to_pg()
            self.save_data()
            return True
        return False

    def get_session_comment(self):
        """現在のセッションのコメントを取得する"""
        current_session = self.get_current_session()
        return current_session.get("comment", "") if current_session else ""

    def load_data(self):
        """データを読み込む（PropertyGroupベース）"""
        # ファイルIDを現在のファイルに基づいて設定
        if bpy.data.filepath:
            current_file_id = bpy.path.basename(bpy.data.filepath)
            try:
                file_stat = os.stat(bpy.data.filepath)
                last_modified = file_stat.st_mtime
                file_exists = True
            except (FileNotFoundError, OSError):
                last_modified = time.time()
                file_exists = False
        else:
            current_file_id = "unsaved_file"
            last_modified = time.time()
            file_exists = False

        log.info(f"Loading data for file: {current_file_id}")
        self.file_id = current_file_id

        # PropertyGroup からの読み込み（既存データがある場合）
        pg = self._pg()
        if pg and (pg.file_id or len(pg.sessions) > 0):
            self._sync_from_pg()
            return

        # 新規作成（PG未初期化）
        self.total_time = 0
        self.last_save_time = time.time()
        self.sessions = []
        self.file_creation_time = time.time()

        # PGへ初回同期し、メモリに反映
        self._sync_to_pg()
        self._sync_from_pg()

    def update_session(self):
        """現在のセッションの継続時間を更新する"""
        current_session = self.get_current_session()
        if current_session:
            # 現在のセッション時間を計算
            current_time = time.time()
            session_duration = current_time - current_session["start"]

            # トータル時間を更新
            self.total_time = sum(
                (
                    session.get("duration", 0)
                    if session.get("end") is not None
                    else current_time - session.get("start", current_time)
                )
                for session in self.sessions
            )
            # PGへ反映
            pg = self._pg()
            if pg:
                pg.total_time = float(self.total_time)
            return session_duration
        return 0

    def save_data(self):
        """時間データを保存する（PropertyGroupに同期）"""
        # 現在のセッションを更新
        self.update_session()

        # 保存時間を更新
        self.last_save_time = time.time()

        # PGへ同期
        self._sync_to_pg()

        log.info(
            f"Saved time data: {len(self.sessions)} sessions, {format_time(self.total_time)} total time"
        )

    def get_current_session_time(self):
        """現在のセッションで費やした時間を取得する"""
        current_session = self.get_current_session()
        if current_session:
            return time.time() - current_session["start"]
        return 0

    def get_time_since_last_save(self):
        """最後に保存してからの経過時間を取得する"""
        return time.time() - self.last_save_time

    def get_formatted_total_time(self):
        """合計時間をフォーマットして取得する"""
        return format_time(self.total_time)

    def get_formatted_session_time(self):
        """セッション時間をフォーマットして取得する"""
        return format_time(self.get_current_session_time())

    def get_formatted_time_since_save(self):
        """最後の保存からの経過時間をフォーマットして取得する"""
        return format_time(self.get_time_since_last_save())

    def format_time(self, seconds):
        """秒数を人間が読みやすい形式にフォーマットする"""
        return format_time(seconds)


class TimeDataManager:
    """時間データマネージャー（シングルトン）"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """TimeDataのシングルトンインスタンスを取得する"""
        if cls._instance is None:
            log.debug("Creating new TimeData instance")
            cls._instance = TimeData()
            cls._instance.ensure_loaded()
        return cls._instance

    @classmethod
    def clear_instance(cls):
        """TimeDataのインスタンスをクリアする"""
        if cls._instance:
            log.debug("Clearing TimeData instance")
            cls._instance.end_active_sessions()
            cls._instance.save_data()
        cls._instance = None


@persistent
def load_handler(_dummy):
    """ファイル読み込み時のハンドラ"""
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()

    # データを読み込む
    time_data.load_data()

    # 新しいセッションを開始
    time_data.start_session()

    log.info(f"File loaded: {bpy.data.filepath}")


@persistent
def save_handler(_dummy):
    """ファイル保存時のハンドラ"""
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()

    # ファイルIDを更新
    if bpy.data.filepath:
        old_id = time_data.file_id
        time_data.file_id = bpy.path.basename(bpy.data.filepath)
        log.info(f"File saved: Updated file_id from {old_id} to {time_data.file_id}")

    # Just update the current session (don't end it) and save
    # No new session should be created on save
    time_data.save_data()


def update_time_callback():
    """タイマーコールバック - 定期的に時間を更新する"""
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()

    time_data.update_session()

    # Check if filepath has changed, which might indicate new file via "Save As"
    filepath = getattr(bpy.data, "filepath", "")
    if filepath and time_data.file_id != bpy.path.basename(filepath):
        log.info(
            f"Detected file path change during timer: {time_data.file_id} -> "
            f"{bpy.path.basename(filepath)}"
        )
        # End current sessions (they belong to the old file)
        time_data.end_active_sessions()
        # Update file ID
        time_data.file_id = bpy.path.basename(filepath)
        # Start new session for the new file
        time_data.start_session()
        # Save data
        time_data.save_data()

    # 1秒後に再実行
    return 1.0


def delayed_start():
    """Blender起動後に遅延実行する関数"""
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()
    time_data.ensure_loaded()

    # タイマーを開始
    start_timer()
    return None  # 一度だけ実行


def start_timer():
    """タイマーを開始する"""
    global timer
    if timer is None:
        timer = bpy.app.timers.register(update_time_callback, persistent=True)


def stop_timer():
    """タイマーを停止し、データを保存する"""
    global timer
    if timer and timer in bpy.app.timers.registered:
        bpy.app.timers.unregister(timer)
    timer = None
    td = TimeDataManager.get_instance()
    if td:
        td.save_data()


def get_file_modification_time():
    """現在のファイルの更新日時を取得する"""
    if bpy.data.filepath and os.path.exists(bpy.data.filepath):
        return os.path.getmtime(bpy.data.filepath)
    return time.time()


def register():
    """モジュールの登録"""
    # SceneにPropertyGroupへのポインタを追加
    if not hasattr(bpy.types.Scene, "wtt_time_data"):
        bpy.types.Scene.wtt_time_data = PointerProperty(type=WTT_TimeData)

    # ハンドラーを登録
    bpy.app.handlers.load_post.append(load_handler)
    bpy.app.handlers.save_post.append(save_handler)

    bpy.app.timers.register(delayed_start, first_interval=1.0)


def unregister():
    """モジュールの登録解除"""
    # ハンドラーを解除
    if load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler)
    if save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(save_handler)

    # タイマーを停止
    stop_timer()

    # インスタンスをクリア
    TimeDataManager.clear_instance()

    # Sceneプロパティを削除
    if hasattr(bpy.types.Scene, "wtt_time_data"):
        try:
            del bpy.types.Scene.wtt_time_data
        except Exception:
            pass

    log.debug("Time data module unregistered")
