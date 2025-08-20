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
    BoolProperty,
    CollectionProperty,
    PointerProperty,
)

from ..utils.formatting import format_time
from ..utils.logging import get_logger
from ..addon import get_prefs

log = get_logger(__name__)

DATA_VERSION = 1  # データ形式のバージョン管理用

timer = None


class WTT_TimeSession(PropertyGroup):
    """セッション情報 (PropertyGroup)"""

    id: IntProperty(name="ID", default=0)
    start: IntProperty(name="Start", default=0)
    end: IntProperty(name="End", default=0)  # 0 はアクティブ（未終了）
    comment: StringProperty(name="Comment", default="")
    
    def __repr__(self):
        return f"<Session #{self.id} start={self.start} end={self.end}>"


class WTT_BreakSession(PropertyGroup):
    """休憩セッション情報 (PropertyGroup)"""

    id: IntProperty(name="ID", default=0)
    session_id: IntProperty(name="Session ID", default=0)
    start: IntProperty(name="Start", default=0)
    end: IntProperty(name="End", default=0)  # 0 はアクティブ（未終了）
    reason: StringProperty(name="Reason", default="inactivity")
    comment: StringProperty(name="Comment", default="")


class WTT_TimeData(PropertyGroup):
    """時間データ (PropertyGroup)"""

    version: IntProperty(name="Version", default=DATA_VERSION)
    total_time: FloatProperty(name="Total Time", default=0.0)
    last_save_time: IntProperty(name="Last Save Time", default=0)
    file_creation_time: IntProperty(name="File Creation Time", default=0)
    file_id: StringProperty(name="File ID", default="")
    sessions: CollectionProperty(type=WTT_TimeSession)
    active_session_index: IntProperty(name="Active Session Index", default=-1)

    # Break tracking
    break_threshold_seconds: IntProperty(
        name="Break Threshold (sec)", default=300, min=30, max=3600
    )
    last_activity_time: IntProperty(name="Last Activity Time", default=0)
    is_on_break: BoolProperty(name="On Break", default=False)
    break_sessions: CollectionProperty(type=WTT_BreakSession)
    active_break_index: IntProperty(name="Active Break Index", default=-1)


class TimeData:
    """時間データを管理するクラス（PGを唯一のソースとして扱う）"""

    def __init__(self):
        self.total_time = 0.0
        self.last_save_time = int(time.time())
        self.file_creation_time = int(time.time())
        self.file_id = None
        self.data_loaded = False
        log.debug("TimeData initialized")

    # PropertyGroup 同期ヘルパー -----------------------------
    def _pg(self):
        """Sceneに紐づくPropertyGroupを取得"""
        scene = getattr(bpy.context, "scene", None)
        if not scene:
            return None
        return getattr(scene, "wtt_time_data", None)

    def _sync_from_pg(self):
        """PGから最低限の情報のみ読み込む（互換用）"""
        pg = self._pg()
        if not pg:
            return
        self.total_time = float(pg.total_time)
        self.last_save_time = int(pg.last_save_time) if pg.last_save_time else int(time.time())
        self.file_creation_time = (
            int(pg.file_creation_time) if pg.file_creation_time else int(time.time())
        )
        if pg.file_id:
            self.file_id = pg.file_id

    def _sync_to_pg(self):
        """最小限のメタ情報のみPGへ反映"""
        pg = self._pg()
        if not pg:
            return
        pg.version = DATA_VERSION
        pg.total_time = float(self.total_time)
        pg.last_save_time = int(self.last_save_time)
        pg.file_creation_time = int(self.file_creation_time)
        pg.file_id = self.file_id or ""

    def reset(self):
        """すべてのデータをデフォルト値にリセットする（PGベース）"""
        pg = self._pg()
        if not pg:
            return
        self.total_time = 0.0
        self.last_save_time = int(time.time())
        self.file_creation_time = int(time.time())
        self._sync_to_pg()
        pg.sessions.clear()
        pg.break_sessions.clear()
        pg.active_session_index = -1
        pg.is_on_break = False
        pg.active_break_index = -1
        pg.last_activity_time = int(time.time())
        # 新規セッション開始
        self.start_session()

    def ensure_loaded(self):
        """PG初期化の保証"""
        if not self.data_loaded:
            self.load_data()
            self.data_loaded = True

    def start_session(self):
        """新しいセッションを開始（既存アクティブは終了してから）"""
        pg = self._pg()
        if not pg:
            return -1
        # 既存アクティブを終了
        self.end_active_sessions()
        # 新規セッション
        now = int(time.time())
        # CollectionPropertyのaddは既存の値を持っている可能性がある
        log.debug(f"[Session-Create] Before add: sessions count={len(pg.sessions)}")
        item = pg.sessions.add()
        log.debug(f"[Session-Create] After add: default values - id={item.id}, start={item.start}, end={item.end}")
        item.id = len(pg.sessions)
        item.start = now
        item.end = 0
        item.comment = ""
        pg.active_session_index = len(pg.sessions) - 1
        log.debug(f"[Session-Create] Initial values: id={item.id}, start={item.start}, end={item.end}")
        log.debug(f"[Session-Create] Setting start={now}")
        # 値を明示的に設定し直す
        item["start"] = now  # 辞書アクセスで強制設定
        log.debug(f"[Session-Create] After dict assignment: start={item.start}")
        log.debug(f"[Session-Create] Verification: item.start={item.start}, expected={now}, match={item.start == now}")
        # アクティビティ/休憩状態の初期化
        pg.last_activity_time = now
        pg.is_on_break = False
        pg.active_break_index = -1
        log.info(f"Started session #{item.id} at {datetime.datetime.fromtimestamp(now)} (start={item.start})")
        # 直後に確認
        if item.start != now:
            log.error(f"Session start time was changed! Expected {now}, got {item.start}")
        # メタ更新
        self.update_total_time()
        return item.id

    def switch_session(self):
        """現在のセッションを終了し、新しいセッションを開始する"""
        ended_count = self.end_active_sessions()
        if ended_count > 0:
            log.info(f"Ended {ended_count} active sessions")
        new_session_id = self.start_session()
        log.info(f"Started new session #{new_session_id}")
        self.save_data()
        return True

    def reset_current_session(self):
        """現在のセッションをリセット（開始を現在に、当該セッションの休憩をクリア）"""
        pg = self._pg()
        if not pg or pg.active_session_index < 0 or pg.active_session_index >= len(pg.sessions):
            return False
        now = int(time.time())
        s = pg.sessions[pg.active_session_index]
        s.start = now
        s.end = 0
        # 当該セッションの休憩を削除
        to_keep = [b for b in pg.break_sessions if b.session_id != s.id]
        pg.break_sessions.clear()
        for b in to_keep:
            bi = pg.break_sessions.add()
            bi.id = b.id
            bi.session_id = b.session_id
            bi.start = b.start
            bi.end = b.end
            bi.reason = b.reason
            bi.comment = b.comment
        # 状態クリア
        pg.is_on_break = False
        pg.active_break_index = -1
        self.update_total_time()
        self.save_data()
        return True

    def end_active_sessions(self):
        """アクティブなセッションを終了（休憩も締める）"""
        pg = self._pg()
        if not pg:
            return 0
        now = int(time.time())
        ended_count = 0
        for i, s in enumerate(pg.sessions):
            if s.end <= 0:
                # セッション終了
                s.end = now
                ended_count += 1
                # 開いている休憩を締める（当該セッションのみ）
                for b in pg.break_sessions:
                    if b.session_id == s.id and b.start > 0 and b.end <= 0:
                        b.end = now
                log.info(
                    f"Ended session #{s.id}: "
                    f"{datetime.datetime.fromtimestamp(s.start)} to "
                    f"{datetime.datetime.fromtimestamp(s.end)}"
                )
        if ended_count:
            pg.active_session_index = -1
            # 休憩状態クリア
            pg.is_on_break = False
            pg.active_break_index = -1
            # 合計更新
            self.update_total_time()
        return ended_count

    def get_current_session(self):
        """現在のアクティブなセッション（PGアイテム）を取得する"""
        pg = self._pg()
        if not pg:
            return None
        idx = getattr(pg, "active_session_index", -1)
        if 0 <= idx < len(pg.sessions):
            return pg.sessions[idx]
        # フォールバック: 未終了の最後
        for s in reversed(pg.sessions):
            if s.end <= 0:
                return s
        return None

    def set_session_comment(self, comment):
        """現在のセッションにコメントを設定する"""
        s = self.get_current_session()
        if s:
            s.comment = comment
            self.save_data()
            return True
        return False

    def get_session_comment(self):
        """現在のセッションのコメントを取得する"""
        s = self.get_current_session()
        return s.comment if s else ""

    def load_data(self):
        """PG初期化/最低限のロード"""
        if bpy.data.filepath:
            current_file_id = bpy.path.basename(bpy.data.filepath)
        else:
            current_file_id = "unsaved_file"
        log.info(f"Loading data for file: {current_file_id}")
        self.file_id = current_file_id
        pg = self._pg()
        if not pg:
            return
        # 既存PGの基本値補正
        if pg.last_activity_time <= 0:
            pg.last_activity_time = int(time.time())
        if not pg.file_id:
            pg.file_id = self.file_id
        # 合計更新
        self.update_total_time()

    def update_session(self):
        """現在のセッションの継続時間を再計算（導出）"""
        self.update_total_time()
        return self.get_current_session_time()

    def save_data(self):
        """メタ情報の保存（PGへ反映）"""
        self.update_total_time()
        self.last_save_time = int(time.time())
        self._sync_to_pg()
        pg = self._pg()
        num_sessions = len(pg.sessions) if pg else 0
        log.info(
            f"Saved time data: {num_sessions} sessions, {format_time(self.total_time)} total time"
        )

    def _sum_breaks_for_session(self, session_id: int, end_cap: int) -> float:
        pg = self._pg()
        if not pg:
            return 0.0
        # 対象セッションを取得
        session = None
        for s in pg.sessions:
            if s.id == session_id:
                session = s
                break
        if not session:
            return 0.0
        start_cap = session.start
        total = 0.0
        for b in pg.break_sessions:
            if b.session_id != session_id or b.start <= 0:
                continue
            # セッション境界にクランプ
            bstart = max(start_cap, b.start)
            bend = b.end if b.end > 0 else end_cap
            bend = min(bend, end_cap)
            total += max(0.0, bend - bstart)
        return max(0.0, total)

    def get_session_work_seconds_by_id(self, session_id: int) -> float:
        pg = self._pg()
        if not pg:
            return 0.0
        for s in pg.sessions:
            if s.id == session_id:
                end_cap = int(time.time()) if s.end <= 0 else s.end
                base = max(0.0, end_cap - s.start)
                return max(0.0, base - self._sum_breaks_for_session(session_id, end_cap))
        return 0.0

    def get_current_session_time(self):
        """現在のセッションで費やした時間（導出）"""
        s = self.get_current_session()
        if not s:
            return 0.0
        return self.get_session_work_seconds_by_id(s.id)

    def get_time_since_last_save(self):
        """最後に保存してからの経過時間を取得する"""
        return int(time.time()) - self.last_save_time

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

    def update_total_time(self):
        """全セッションの実作業合計を再計算しPGへ反映"""
        pg = self._pg()
        if not pg:
            self.total_time = 0.0
            return
        total = 0.0
        for s in pg.sessions:
            end_cap = int(time.time()) if s.end <= 0 else s.end
            # セッション開始時刻の妥当性チェック
            if s.start <= 0.0:
                log.warning(f"[Recalc] Invalid session start time: session_id={s.id} start={s.start}")
                continue
            base = max(0.0, end_cap - s.start)
            breaks = self._sum_breaks_for_session(s.id, end_cap)
            work = max(0.0, base - breaks)
            total += work
            log.debug(
                f"[Recalc] session_id={s.id} base={int(base)} breaks={int(breaks)} work={int(work)} start={datetime.datetime.fromtimestamp(s.start).strftime('%H:%M:%S')}"
            )
        self.total_time = float(total)
        pg.total_time = self.total_time


class TimeDataManager:
    """時間データマネージャー（シングルトン）"""

    _instance = None

    @classmethod
    def get_instance(cls):
        """TimeDataのシングルトンインスタンスを取得する"""
        if cls._instance is None:
            log.debug("Creating new TimeData instance")
            cls._instance = TimeData()
            # ensure_loaded()は呼び出し元で必要に応じて実行
        return cls._instance

    @classmethod
    def clear_instance(cls):
        """TimeDataのインスタンスをクリアする"""
        if cls._instance:
            log.debug("Clearing TimeData instance")
            try:
                cls._instance.end_active_sessions()
                cls._instance.save_data()
            except Exception:
                pass
        cls._instance = None


@persistent
def load_handler(_dummy):
    """ファイル読み込み時のハンドラ"""
    log.debug(f"[load_handler] Called with filepath: {bpy.data.filepath}")
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()

    # データを読み込む（既にロード済みの場合はスキップ）
    if not time_data.data_loaded:
        time_data.load_data()
        time_data.data_loaded = True
        # 新しいセッションを開始
        time_data.start_session()
    else:
        log.debug("[load_handler] Data already loaded, skipping")

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


def depsgraph_activity_handler(_scene):
    """依存グラフ更新時: 最終アクティビティ時刻のみを更新"""
    # 依存グラフから渡されるシーンを優先して使用
    pg = getattr(_scene, "wtt_time_data", None)
    if not pg:
        return
    now = int(time.time())
    prev = int(getattr(pg, "last_activity_time", 0))
    idle_before = max(0.0, now - prev) if prev > 0 else -1.0
    pg.last_activity_time = now
    log.debug(
        f"[Activity] now={datetime.datetime.fromtimestamp(now)} idle_before={int(idle_before)} on_break={pg.is_on_break}"
    )


def update_time_callback():
    """タイマーコールバック - 定期的に時間を更新する"""
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()

    # 重要ハンドラの自己修復（ファイルオープン後に消えるケース対策）
    try:
        def _is_registered(lst, func):
            for f in lst:
                if getattr(f, "__name__", None) == getattr(func, "__name__", None):
                    return True
            return False
        if not _is_registered(bpy.app.handlers.depsgraph_update_post, depsgraph_activity_handler):
            bpy.app.handlers.depsgraph_update_post.append(depsgraph_activity_handler)
        if not _is_registered(bpy.app.handlers.load_post, load_handler):
            bpy.app.handlers.load_post.append(load_handler)
        if not _is_registered(bpy.app.handlers.save_post, save_handler):
            bpy.app.handlers.save_post.append(save_handler)
    except Exception:
        pass

    # 軽量アイドル検出と休憩管理（閾値はアドオンプリファレンスから）
    pg = time_data._pg()
    now = int(time.time())
    if pg:
        # 初期化（Blender起動直後など）
        if pg.last_activity_time <= 0:
            pg.last_activity_time = now

        idle = now - pg.last_activity_time
        try:
            prefs = get_prefs(bpy.context)
            threshold = int(getattr(prefs, "break_threshold_seconds", 300))
        except Exception:
            threshold = 300
        threshold = max(30, threshold)
        if not pg.is_on_break and idle >= threshold:
            # 休憩開始
            bi = pg.break_sessions.add()
            bi.id = len(pg.break_sessions)
            current = time_data.get_current_session()
            bi.session_id = current.id if current else 0
            # last_activity_timeの遅延により過去に遡り過ぎないよう、セッション開始以降へクランプ
            start_candidate = pg.last_activity_time if pg.last_activity_time > 0 else (now - idle)
            if current:
                bi.start = max(current.start, start_candidate)
            else:
                bi.start = start_candidate
            bi.end = 0
            bi.reason = "inactivity"
            pg.active_break_index = len(pg.break_sessions) - 1
            pg.is_on_break = True
            log.debug(
                f"[Break-Start] break_id={bi.id} session_id={bi.session_id} idle={int(idle)} threshold={threshold} start={datetime.datetime.fromtimestamp(bi.start)}"
            )
        elif pg.is_on_break and idle < 1:
            # アクティビティ復帰直後: 休憩終了
            idx = getattr(pg, "active_break_index", -1)
            if 0 <= idx < len(pg.break_sessions):
                br = pg.break_sessions[idx]
                br.end = now
                log.debug(
                    f"[Break-End] break_id={br.id} session_id={br.session_id} end={datetime.datetime.fromtimestamp(now)}"
                )
            # 直後の再判定で即座に休憩再開しないよう、アクティビティ時刻を最新化
            pg.last_activity_time = now
            pg.is_on_break = False
            pg.active_break_index = -1

    # 作業時間更新（休憩処理の後で導出）
    time_data.update_total_time()

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
    log.debug("[delayed_start] Called")
    # 時間データのインスタンスを取得
    time_data = TimeDataManager.get_instance()
    # 既にload_handlerで初期化されている場合はスキップ
    if not time_data.data_loaded:
        time_data.ensure_loaded()
        # 新規ファイルの場合のみセッション開始
        pg = time_data._pg()
        if pg and len(pg.sessions) == 0:
            time_data.start_session()

    # 欠落したハンドラを再登録（再ロード対策）
    try:
        def _is_registered(lst, func):
            for f in lst:
                if getattr(f, "__name__", None) == getattr(func, "__name__", None):
                    return True
            return False
        if not _is_registered(bpy.app.handlers.depsgraph_update_post, depsgraph_activity_handler):
            bpy.app.handlers.depsgraph_update_post.append(depsgraph_activity_handler)
    except Exception:
        pass

    # タイマーを開始
    start_timer()
    return None  # 一度だけ実行


_timer_running = False


def start_timer():
    """タイマーを開始する（多重登録防止）"""
    global _timer_running
    if not _timer_running:
        bpy.app.timers.register(update_time_callback, persistent=True)
        _timer_running = True


def stop_timer():
    """タイマーを停止し、データを保存する"""
    global _timer_running
    try:
        bpy.app.timers.unregister(update_time_callback)
    except Exception:
        pass
    _timer_running = False
    td = TimeDataManager.get_instance()
    if td:
        td.save_data()


def get_file_modification_time():
    """現在のファイルの更新日時を取得する"""
    if bpy.data.filepath and os.path.exists(bpy.data.filepath):
        return os.path.getmtime(bpy.data.filepath)
    return int(time.time())


def register():
    """モジュールの登録"""
    # SceneにPropertyGroupへのポインタを追加
    if not hasattr(bpy.types.Scene, "wtt_time_data"):
        bpy.types.Scene.wtt_time_data = PointerProperty(type=WTT_TimeData)

    # ハンドラーを登録（重複防止）
    def _is_registered(lst, func):
        for f in lst:
            if getattr(f, "__name__", None) == getattr(func, "__name__", None):
                return True
        return False

    if not _is_registered(bpy.app.handlers.load_post, load_handler):
        bpy.app.handlers.load_post.append(load_handler)
    if not _is_registered(bpy.app.handlers.save_post, save_handler):
        bpy.app.handlers.save_post.append(save_handler)
    # 依存グラフ更新でアクティビティを検知（軽量: タイムスタンプ更新のみ）
    if not _is_registered(bpy.app.handlers.depsgraph_update_post, depsgraph_activity_handler):
        bpy.app.handlers.depsgraph_update_post.append(depsgraph_activity_handler)

    bpy.app.timers.register(delayed_start, first_interval=1.0)


def unregister():
    """モジュールの登録解除"""
    # ハンドラーを解除
    if load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler)
    if save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(save_handler)
    if depsgraph_activity_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_activity_handler)

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
