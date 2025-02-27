bl_info = {
    "name": "Work Time Tracker",
    "author": "Pluglug, Claude 3.5 Sonnet",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Time Tracker",
    "description": "Tracks working time in Blender sessions",
    "warning": "",
    "doc_url": "",
    "category": "Utility",
}

import bpy
import time
import datetime
import json
import os
import atexit
from bpy.app.handlers import persistent


# Constants
TEXT_NAME = ".work_time_tracker"
UNSAVED_WARNING_THRESHOLD = 10 * 60  # 10 minutes in seconds
DATA_VERSION = 1  # データ形式のバージョン管理用

# Global variables
time_data = None
timer = None


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
            'version': DATA_VERSION,
            'total_time': 0,
            'last_save_time': time.time(),
            'sessions': [],
            'file_creation_time': time.time(),
            'file_id': bpy.path.basename(bpy.data.filepath) if bpy.data.filepath else 'unsaved_file'
        }
        text_block.write(json.dumps(initial_data, indent=2))

    # fake_userフラグを確実に設定
    text_block.use_fake_user = True

    return text_block


class TimeData:
    def __init__(self):
        self.total_time = 0
        self.last_save_time = time.time()
        self.sessions = []
        self.file_creation_time = time.time()
        self.file_id = None
        self.current_session_start = None
        self.data_loaded = False  # このフラグは必要

    def reset(self):
        """Reset all data to defaults"""
        self.total_time = 0
        self.last_save_time = time.time()
        self.sessions = []
        self.file_creation_time = time.time()
        self.current_session_start = None

    def ensure_loaded(self):
        """Make sure data is loaded (safe to call after Blender is fully initialized)"""
        if not self.data_loaded:
            self.load_data()
            self.data_loaded = True

    def start_session(self):
        """セッションを開始 - ファイル読み込み時のみ呼び出す"""
        # アクティブなセッションがあるか確認
        active_sessions = [s for s in self.sessions if s.get('end') is None]

        if active_sessions:
            print(f"Warning: {len(active_sessions)} active sessions found, ending them first")
            self.end_active_sessions()

        # 新しいセッションを開始
        self.current_session_start = time.time()
        session_id = len(self.sessions) + 1

        self.sessions.append({
            'id': session_id,
            'start': self.current_session_start,
            'end': None,
            'duration': 0,
            'file_id': self.file_id,
            'date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'comment': '',
        })

        print(f"Started session #{session_id} at {datetime.datetime.fromtimestamp(self.current_session_start)}")
        return session_id

    def switch_session(self):
        """現在のセッションを終了し、新しいセッションを開始"""
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
        """現在のセッションをリセット"""
        if not self.sessions:
            return False
            
        # 最後のセッションを取得
        current_session = next((s for s in reversed(self.sessions) if s.get('end') is None), None)
        if not current_session:
            return False
            
        # 古いセッション時間を計算
        old_duration = time.time() - current_session['start']
        
        # 開始時間を現在時刻に更新
        current_session['start'] = time.time()
        current_session['duration'] = 0
        
        # トータル時間から古いセッション時間を引く
        self.total_time -= old_duration
        
        # 現在のセッション開始時間も更新
        self.current_session_start = current_session['start']
        
        # データを保存
        self.save_data()
        return True

    def end_active_sessions(self):
        """アクティブなセッションを終了"""
        end_time = time.time()
        ended_count = 0

        for session in self.sessions:
            if session.get('end') is None:
                session['end'] = end_time
                session['duration'] = session['end'] - session['start']
                print(f"Ended session #{session.get('id', '?')}: {datetime.datetime.fromtimestamp(session['start'])} to {datetime.datetime.fromtimestamp(session['end'])}")
                ended_count += 1

        if ended_count > 0:
            # トータル時間を更新
            self.total_time = sum(session.get('duration', 0) for session in self.sessions)
            print(f"Updated total time: {self.format_time(self.total_time)}")

        return ended_count

    def get_current_session(self):
        """現在のアクティブなセッションを取得"""
        if not self.sessions:
            return None
        return next((s for s in reversed(self.sessions) if s.get('end') is None), None)

    def set_session_comment(self, comment):
        """現在のセッションにコメントを設定"""
        current_session = self.get_current_session()
        if current_session:
            current_session['comment'] = comment
            self.save_data()
            return True
        return False

    def get_session_comment(self):
        """現在のセッションのコメントを取得"""
        current_session = self.get_current_session()
        return current_session.get('comment', '') if current_session else ''

    def load_data(self):
        """テキストブロックからデータを読み込む"""
        # 現在のファイルIDを保存（ファイルの識別用）
        old_file_id = self.file_id

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

        # 重要: データをリセットして、クリーンな状態から始める
        self.reset()

        # 設定したファイルIDを使用
        self.file_id = current_file_id

        # テキストブロックからデータ読み込み
        text_block = blend_time_data()

        if text_block and text_block.as_string().strip():
            try:
                data = json.loads(text_block.as_string())

                # データバージョンチェック (将来の互換性のため)
                version = data.get('version', 1)
                stored_file_id = data.get('file_id')

                # ファイルIDが一致する場合のみデータを読み込む
                if stored_file_id == self.file_id:
                    print(f"Found matching data for {self.file_id}")

                    # データの内容をすべて読み込む
                    self.total_time = data.get('total_time', 0)
                    self.last_save_time = data.get('last_save_time', time.time())
                    self.sessions = data.get('sessions', [])
                    self.file_creation_time = data.get('file_creation_time', time.time())
                    self.last_exit_clean = data.get('last_exit_clean', False)

                    # 未終了のセッションに対して、ファイルの最終更新時間を終了時間として設定
                    if file_exists and self.sessions:
                        for session in self.sessions:
                            if session.get('end') is None:
                                # 最終更新時間をセッション終了時間として使用
                                session['end'] = last_modified
                                session['duration'] = session['end'] - session['start']
                                print(f"Updated session #{session.get('id', '?')} end time using file's last modified time")

                        # トータル時間を更新
                        self.total_time = sum(session.get('duration', 0) for session in self.sessions)

                    print(f"Loaded time data: {len(self.sessions)} sessions, {self.format_time(self.total_time)} total time")
                else:
                    print(f"File ID mismatch: stored={stored_file_id}, current={self.file_id}")
                    # ファイルが違う場合は既に実行したresetの値を使用

                # 現在のセッション開始はリセット
                self.current_session_start = None

            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error parsing JSON: {e}")
                # JSONが無効な場合はデフォルト値を使用（resetで設定済み）
        else:
            # テキストブロックが存在しない場合
            print(f"No existing time data found for {self.file_id}, using new data")

    def update_session(self):
        """Update the current session duration"""
        if self.current_session_start is not None:
            current_time = time.time()
            # Find the active session
            for session in self.sessions:
                if session['end'] is None:
                    session['duration'] = current_time - session['start']
                    break

            # Update total_time in real-time based on all sessions
            self.total_time = sum(session.get('duration', 0) for session in self.sessions)

    def save_data(self):
        """Save time tracking data to text block"""
        current_time = time.time()

        # Update the active session's duration
        self.update_session()

        # Update last save time
        self.last_save_time = current_time

        # Update file_id if needed
        filepath = getattr(bpy.data, 'filepath', '')
        if filepath and not self.file_id:
            self.file_id = bpy.path.basename(filepath)

        data = {
            'total_time': self.total_time,
            'last_save_time': self.last_save_time,
            'sessions': self.sessions,
            'file_creation_time': self.file_creation_time,
            'file_id': self.file_id
        }

        # Use the safer text block getter
        text_block = blend_time_data()
        if text_block:
            text_block.clear()
            text_block.write(json.dumps(data, indent=2))
            print(f"Saved time data: {len(self.sessions)} sessions, {self.format_time(self.total_time)} total time")
        else:
            print("Failed to create or access text block for saving")

    def get_current_session_time(self):
        """Get time spent in current session"""
        if self.current_session_start:
            return time.time() - self.current_session_start
        return 0

    def get_time_since_last_save(self):
        """Get time since last save"""
        return time.time() - self.last_save_time

    def get_formatted_total_time(self):
        """Get formatted total working time"""
        return self.format_time(self.total_time)

    def get_formatted_session_time(self):
        """Get formatted current session time"""
        return self.format_time(self.get_current_session_time())

    def get_formatted_time_since_save(self):
        """Get formatted time since last save"""
        return self.format_time(self.get_time_since_last_save())
    
    def format_time(self, seconds):
        """Format seconds into readable time string"""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@persistent
def load_handler(_dummy):
    """Handler called when a blend file is loaded"""
    global time_data
    
    # Blenderが完全に初期化されるまで待機
    if not hasattr(bpy, 'data') or not hasattr(bpy.data, 'filepath'):
        print("load_handler called too early, bpy.data.filepath not available")
        return

    if time_data is None:
        time_data = TimeData()

    # データを読み込み（この中でresetも実行される）
    time_data.load_data()
    time_data.data_loaded = True

    # 新しいセッションを開始
    time_data.start_session()
    time_data.save_data()

    # タイマー開始
    start_timer()


@persistent
def save_handler(_dummy):
    """Handler called when a blend file is saved"""
    if time_data:
        print("save_handler called for file:", bpy.data.filepath)
        # Ensure data is loaded
        time_data.ensure_loaded()

        # Update file_id when file is saved
        if bpy.data.filepath:
            old_id = time_data.file_id
            time_data.file_id = bpy.path.basename(bpy.data.filepath)
            print(f"File saved: Updated file_id from {old_id} to {time_data.file_id}")

        # Just update the current session (don't end it) and save
        # No new session should be created on save
        time_data.update_session()
        time_data.save_data()


def update_time_callback():
    """Timer callback to update time tracking UI"""
    if time_data:
        # Ensure data is loaded after Blender is fully initialized
        time_data.ensure_loaded()

        # ONLY update the current session, NEVER create a new one here
        time_data.update_session()

        # Check if filepath has changed, which might indicate new file via "Save As"
        filepath = getattr(bpy.data, 'filepath', '')
        if filepath and time_data.file_id != bpy.path.basename(filepath):
            print(f"Detected file path change during timer: {time_data.file_id} -> {bpy.path.basename(filepath)}")
            # End current sessions (they belong to the old file)
            time_data.end_active_sessions()
            # Update file ID
            time_data.file_id = bpy.path.basename(filepath)
            # Start a new session for the new file
            time_data.start_session()
            time_data.save_data()

        # Force redraw of UI
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return 1.0  # Run again in 1 second


def delayed_start():
    """Start the timer after Blender is fully initialized"""
    if time_data:
        time_data.ensure_loaded()
    start_timer()
    return None


def start_timer():
    """Start the timer for updating the UI"""
    global timer
    if timer is None:
        timer = bpy.app.timers.register(update_time_callback, persistent=True)


def stop_timer():
    """Stop the timer and save data"""
    global timer
    if timer and timer in bpy.app.timers.registered:
        bpy.app.timers.unregister(timer)
    timer = None
    if time_data:
        time_data.save_data()


def get_file_modification_time():
    """ファイルの最終更新時間を取得"""
    if bpy.data.filepath and os.path.exists(bpy.data.filepath):
        return os.path.getmtime(bpy.data.filepath)
    return None


class VIEW3D_PT_time_tracker(bpy.types.Panel):
    """Time Tracker Panel"""
    bl_label = "Time Tracker"
    bl_idname = "VIEW3D_PT_time_tracker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Time'

    def draw(self, context):
        layout = self.layout

        if time_data:
            # Ensure data is loaded
            time_data.ensure_loaded()

            # Display total time
            row = layout.row()
            row.label(text="Total Work Time:")
            row.label(text=time_data.get_formatted_total_time())

            # Display current session time
            row = layout.row()
            row.label(text="Current Session:")
            row.label(text=time_data.get_formatted_session_time())

            # Display time since last save
            time_since_save = time_data.get_time_since_last_save()
            row = layout.row()
            row.label(text="Time Since Save:")

            # Show warning if unsaved for too long
            if context.blend_data.is_dirty and time_since_save > UNSAVED_WARNING_THRESHOLD:
                # row_alert = layout.row()
                row.alert = True
                row.label(text=f"{time_data.get_formatted_time_since_save()}")
                row_alert = layout.row()
                row_alert.alert = True
                row_alert.label(text="Consider saving your work!")
            else:
                row.label(text=time_data.get_formatted_time_since_save())

            box = layout.box()
            row = box.row()
            row.label(text="Session Info:", icon='TEXT')
            
            # コメント表示/編集
            current_comment = time_data.get_session_comment()
            if current_comment:
                row = box.row()
                row.label(text=current_comment, icon='SMALL_CAPS')
            row = box.row()
            row.operator("timetracker.edit_comment", text="Edit Comment", icon='GREASEPENCIL')

            # File info
            if time_data.file_id:
                layout.separator()
                row = layout.row()
                row.label(text=f"File ID: {time_data.file_id}")

                if time_data.file_creation_time:
                    creation_time = datetime.datetime.fromtimestamp(time_data.file_creation_time)
                    row = layout.row()
                    row.label(text=f"Created: {creation_time.strftime('%Y-%m-%d %H:%M')}")

            # layout.separator()
            layout.operator("timetracker.switch_session", text="New Session", icon='FILE_REFRESH')
            layout.operator("timetracker.export_data", text="Export Report", icon='TEXT')

            # layout.separator()
            header, sub_panel = layout.panel(idname="time_tracker_subpanel", default_closed=True)
            header.label(text="Reset Data", icon='ERROR')
            if sub_panel:
                sub_panel.operator("timetracker.reset_session", text="Reset Current Session", icon='CANCEL')
                sub_panel.alert = True
                sub_panel.operator("timetracker.reset_data", text="Reset All Session", icon='ERROR')


def format_hours_minutes(seconds):
    """時間を HH:MM 形式でフォーマット"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours:02d}:{minutes:02d}"


def time_tracker_draw(self, context):
    """トップバーに表示するコンパクトなUI"""
    if not time_data:
        return

    layout = self.layout
    row = layout.row(align=True)

    total_time_str = format_hours_minutes(time_data.total_time)
    session_time_str = format_hours_minutes(time_data.get_current_session_time())

    compact_text = f"{total_time_str} | {session_time_str}"

    row.popover(
        panel="VIEW3D_PT_time_tracker",
        text=compact_text,
        icon='TIME'
    )

    row.separator()

    time_since_save = time_data.get_time_since_last_save()
    if not context.blend_data.is_saved:
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Unsaved File", icon='ERROR')
    elif context.blend_data.is_dirty and time_since_save > UNSAVED_WARNING_THRESHOLD:
        row_alert = row.row(align=True)
        row_alert.alert = True
        row_alert.label(text="Save Pending", icon='ERROR')


class TIMETRACKER_OT_edit_comment(bpy.types.Operator):
    """セッションコメントを編集"""
    bl_idname = "timetracker.edit_comment"
    bl_label = "Edit Session Comment"
    bl_description = "Edit comment for the current session"
    bl_options = {'REGISTER', 'UNDO'}

    comment: bpy.props.StringProperty(
        name="Comment",
        description="Comment for the current session",
        default=""
    )

    def invoke(self, context, event):
        if time_data:
            self.comment = time_data.get_session_comment()
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if time_data and time_data.set_session_comment(self.comment):
            self.report({'INFO'}, "Session comment updated")
            return {'FINISHED'}
        self.report({'WARNING'}, "No active session to comment on")
        return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "comment", text="")


class TIMETRACKER_OT_switch_session(bpy.types.Operator):
    """現在のセッションを終了し、新しいセッションを開始"""
    bl_idname = "timetracker.switch_session"
    bl_label = "Switch Session"
    bl_description = "End current session and start a new one"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if time_data and time_data.switch_session():
            self.report({'INFO'}, "Started new session")
            return {'FINISHED'}
        self.report({'WARNING'}, "Failed to switch session")
        return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class TIMETRACKER_OT_reset_session(bpy.types.Operator):
    """現在のセッションをリセット"""
    bl_idname = "timetracker.reset_session"
    bl_label = "Reset Current Session"
    bl_description = "Reset the current session time to zero"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if time_data and time_data.reset_current_session():
            self.report({'INFO'}, "Current session has been reset")
            return {'FINISHED'}
        self.report({'WARNING'}, "No active session to reset")
        return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class TIMETRACKER_OT_reset_data(bpy.types.Operator):
    """Reset time tracking data"""
    bl_idname = "timetracker.reset_data"
    bl_label = "Reset Time Data"
    bl_description = "Reset all time tracking data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global time_data
        if TEXT_NAME in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[TEXT_NAME])
        time_data = TimeData()
        time_data.start_session()
        time_data.save_data()
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class TIMETRACKER_OT_export_data(bpy.types.Operator):
    """Export time tracking data"""
    bl_idname = "timetracker.export_data"
    bl_label = "Export Time Report"
    bl_description = "Export time tracking data to a text file"

    def execute(self, context):
        if time_data:
            # Ensure data is loaded
            time_data.ensure_loaded()

            # Update current session before generating report
            time_data.update_session()

            # Create a report
            current_time = datetime.datetime.now()
            report_name = f"WorkTimeReport_{current_time.strftime('%Y%m%d_%H%M%S')}.md"
            report = bpy.data.texts.new(report_name)

            # Get file name
            filename = bpy.path.basename(bpy.data.filepath) or "Unsaved File"

            # Get file creation time
            creation_date = datetime.datetime.fromtimestamp(time_data.file_creation_time)

            # Write report header
            report.write(f"# Work Time Report for {filename}\n")
            report.write(f"Generated: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            report.write(f"File created: {creation_date.strftime('%Y-%m-%d %H:%M:%S')}\n")
            report.write(f"File ID: {time_data.file_id}\n\n")

            # Write summary
            report.write("## Summary\n")
            report.write(f"- Total work time: {time_data.get_formatted_total_time()}\n")
            report.write(f"- Current session: {time_data.get_formatted_session_time()}\n")
            report.write(f"- Time since last save: {time_data.get_formatted_time_since_save()}\n\n")

            # Write detailed session info
            report.write("## Session History\n")
            for i, session in enumerate(time_data.sessions):
                start_time = datetime.datetime.fromtimestamp(session['start']).strftime('%Y-%m-%d %H:%M:%S')

                if session['end'] is None:
                    end_time = "Current"
                    duration = time.time() - session['start']
                else:
                    end_time = datetime.datetime.fromtimestamp(session['end']).strftime('%Y-%m-%d %H:%M:%S')
                    duration = session['duration']

                formatted_duration = time_data.format_time(duration)
                report.write(f"### Session {i+1}\n")
                report.write(f"- Start: {start_time}\n")
                report.write(f"- End: {end_time}\n")
                report.write(f"- Duration: {formatted_duration}\n")
                if session.get('comment'):
                    report.write(f"- Comment: {session['comment']}\n")
                
                report.write("\n")
            self.report({'INFO'}, f"Report created: {report_name}")
            return {'FINISHED'}
        return {'CANCELLED'}


# Visual Time Graph class (to be implemented in view_3d_draw_handler)
def draw_time_graph(_self, _context):
    # This will be implemented to draw a visual time graph
    pass


classes = (
    VIEW3D_PT_time_tracker,
    TIMETRACKER_OT_edit_comment,
    TIMETRACKER_OT_switch_session,
    TIMETRACKER_OT_reset_session,
    TIMETRACKER_OT_reset_data,
    TIMETRACKER_OT_export_data,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register handlers
    bpy.app.handlers.load_post.append(load_handler)
    bpy.app.handlers.save_post.append(save_handler)

    # Initialize time data but don't load data yet
    global time_data
    time_data = TimeData()

    # Debug info
    print(f"Time Tracker registered. Version {bl_info['version']}")

    # Set a timer to start the actual timer after Blender is initialized
    bpy.app.timers.register(delayed_start, first_interval=1.0)

    bpy.types.STATUSBAR_HT_header.prepend(time_tracker_draw)


def unregister():
    bpy.types.STATUSBAR_HT_header.remove(time_tracker_draw)

    # End any active sessions before unregistering
    if time_data:
        time_data.end_active_sessions()
        time_data.save_data()

    # Stop timer
    stop_timer()

    # Unregister handlers - important to remove these first
    if load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler)
    if save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(save_handler)

    # Unregister classes last
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    print("Time Tracker unregistered.")


if __name__ == "__main__":
    register()
