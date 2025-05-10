"""
時間データ管理モジュール
"""

import datetime
import json
import os
import time

import bpy
from bpy.app.handlers import persistent

from ..utils.formatting import format_time

# Constants
TEXT_NAME = ".work_time_tracker"
DATA_VERSION = 1  # データ形式のバージョン管理用

timer = None

# モジュールの依存関係を明示的に指定
# DEPENDS_ON = ["utils.formatting"]


def blend_time_data():
    """Get time tracking data for current blend file, create if doesn't exist"""
    name = TEXT_NAME + ".json"

    # 既存のテキストブロックを探す
    text_block = None

    # まず完全一致で検索
    if name in bpy.data.texts:
        text_block = bpy.data.texts[name]
        print(f"Found primary time tracking data: {name}")
    else:
        # 代替のテキストブロックを検索
        for text in bpy.data.texts:
            if text.name.startswith(TEXT_NAME):
                text_block = text
                # 名前を標準化
                try:
                    text.name = name
                    print(f"Renamed time tracking data from {text.name} to {name}")
                except Exception as e:
                    print(f"Warning: Could not rename text block: {e}")
                break

    # テキストブロックが見つからない場合は新規作成
    if not text_block:
        text_block = bpy.data.texts.new(name)
        print(f"Created new time tracking data: {name}")

        # 初期データを設定
        initial_data = {
            "version": DATA_VERSION,
            "total_time": 0,
            "last_save_time": time.time(),
            "sessions": [],
            "file_creation_time": time.time(),
            "file_id": (
                bpy.path.basename(bpy.data.filepath)
                if bpy.data.filepath
                else "unsaved_file"
            ),
        }
        text_block.write(json.dumps(initial_data, indent=2))

    # fake_userフラグを確実に設定
    text_block.use_fake_user = True

    return text_block


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

        print("TimeData initialized")

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
            print(
                f"Warning: {len(active_sessions)} active sessions found, ending them first"
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
                "duration": 0,
                "file_id": self.file_id,
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "comment": "",
            }
        )

        print(
            f"Started session #{session_id} at "
            f"{datetime.datetime.fromtimestamp(self.current_session_start)}"
        )
        return session_id

    def switch_session(self):
        """現在のセッションを終了し、新しいセッションを開始する"""
        # アクティブなセッションを終了
        ended_count = self.end_active_sessions()
        if ended_count == 0:
            print("No active sessions to end")
        else:
            print(f"Ended {ended_count} active sessions")

        # 新しいセッションを開始
        new_session_id = self.start_session()
        print(f"Started new session #{new_session_id}")

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

        # データを保存
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
                print(
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
            print(f"Updated total time: {format_time(self.total_time)}")

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
            self.save_data()
            return True
        return False

    def get_session_comment(self):
        """現在のセッションのコメントを取得する"""
        current_session = self.get_current_session()
        return current_session.get("comment", "") if current_session else ""

    def load_data(self):
        """テキストブロックからデータを読み込む"""
        # 現在のファイルIDを保存（ファイルの識別用）
        # old_file_id = self.file_id  # 未使用変数

        # ファイルIDを現在のファイルに基づいて設定
        if bpy.data.filepath:
            current_file_id = bpy.path.basename(bpy.data.filepath)

            # ファイルの最終更新時間を取得（ファイルが存在する場合のみ）
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

        print(f"Loading data for file: {current_file_id}")

        # ファイルIDを設定
        self.file_id = current_file_id

        # テキストブロックを取得
        text_block = blend_time_data()

        if text_block:
            # テキストブロックからデータを読み込む
            try:
                text_content = text_block.as_string()
                if text_content.strip():
                    data = json.loads(text_content)

                    # データバージョンチェック (将来の互換性のため)
                    # version = data.get("version", 1)  # 未使用変数
                    stored_file_id = data.get("file_id")

                    # ファイルIDが一致する場合のみデータを読み込む
                    if stored_file_id == self.file_id:
                        # データの内容をすべて読み込む
                        self.total_time = data.get("total_time", 0)
                        self.last_save_time = data.get("last_save_time", time.time())
                        self.sessions = data.get("sessions", [])
                        self.file_creation_time = data.get(
                            "file_creation_time", time.time()
                        )

                        # 未終了のセッションがある場合、ファイルの最終更新時間を使用して終了
                        if file_exists:
                            for session in self.sessions:
                                if session.get("end") is None and session.get("start"):
                                    # 最終更新時間をセッション終了時間として使用
                                    session["end"] = last_modified
                                    session["duration"] = (
                                        session["end"] - session["start"]
                                    )
                                    print(
                                        f"Updated session #{session.get('id', '?')} "
                                        f"end time using file's last modified time"
                                    )

                            # トータル時間を更新
                            self.total_time = sum(
                                session.get("duration", 0) for session in self.sessions
                            )

                        print(
                            f"Loaded time data: {len(self.sessions)} sessions, "
                            f"{format_time(self.total_time)} total time"
                        )
                    else:
                        print(
                            f"File ID mismatch: stored={stored_file_id}, "
                            f"current={self.file_id}"
                        )
                        # ファイルが違う場合は既に実行したresetの値を使用
                else:
                    print("Empty text block, using default data")
            except Exception as e:
                print(f"Error loading time data: {str(e)}")
                # エラーの場合はデフォルト値を使用
        else:
            # テキストブロックが存在しない場合
            print(f"No existing time data found for {self.file_id}, using new data")

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
            return session_duration
        return 0

    def save_data(self):
        """時間データをテキストブロックに保存する"""
        # 現在のセッションを更新
        self.update_session()

        # 保存時間を更新
        self.last_save_time = time.time()

        # データを構築
        data = {
            "version": DATA_VERSION,
            "total_time": self.total_time,
            "last_save_time": self.last_save_time,
            "sessions": self.sessions,
            "file_creation_time": self.file_creation_time,
            "file_id": self.file_id,
        }

        # テキストブロックに保存
        text_block = blend_time_data()
        if text_block:
            text_block.clear()
            text_block.write(json.dumps(data, indent=2))
            print(
                f"Saved time data: {len(self.sessions)} sessions, "
                f"{format_time(self.total_time)} total time"
            )
        else:
            print("Failed to create or access text block for saving")

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
            print("Creating new TimeData instance")
            cls._instance = TimeData()
            cls._instance.ensure_loaded()
        return cls._instance
    
    @classmethod
    def clear_instance(cls):
        """TimeDataのインスタンスをクリアする"""
        if cls._instance:
            print("Clearing TimeData instance")
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

    print(f"File loaded: {bpy.data.filepath}")


@persistent
def save_handler(_dummy):
    """ファイル保存時のハンドラ"""
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()

    # ファイルIDを更新
    if bpy.data.filepath:
        old_id = time_data.file_id
        time_data.file_id = bpy.path.basename(bpy.data.filepath)
        print(f"File saved: Updated file_id from {old_id} to {time_data.file_id}")

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
        print(
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
    if time_data:
        time_data.save_data()


def get_file_modification_time():
    """現在のファイルの更新日時を取得する"""
    if bpy.data.filepath and os.path.exists(bpy.data.filepath):
        return os.path.getmtime(bpy.data.filepath)
    return time.time()


def register():
    """モジュールの登録"""
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
    
    print("Time data module unregistered")
