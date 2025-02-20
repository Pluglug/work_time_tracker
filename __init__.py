bl_info = {
    "name": "Blender 作業時間トラッカー",
    "description": "Blender内での作業時間を追跡し、視覚化するアドオン",
    "author": "Your Name",
    "version": (0, 1),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > Time",
    "category": "System",
}

import bpy
import json
import time
import uuid

# 隠しテキストブロックの名前
HIDDEN_TEXT_NAME = ".hidden_work_time.json"

# 作業時間・セッション情報を管理するクラス
class TimeData:
    def __init__(self):
        self.total_time = 0.0         # 累積作業時間（秒）
        self.sessions = []            # セッション履歴（各辞書：開始、終了、期間）
        self.current_session_start = None
        self.last_save_time = None
        self.file_creation_time = None
        self.file_id = str(uuid.uuid4())
    
    def start_session(self):
        self.current_session_start = time.time()
        if self.file_creation_time is None:
            self.file_creation_time = self.current_session_start
    
    def end_session(self):
        if self.current_session_start is not None:
            end_time = time.time()
            duration = end_time - self.current_session_start
            self.sessions.append({
                "start": self.current_session_start,
                "end": end_time,
                "duration": duration
            })
            self.total_time += duration
            self.current_session_start = None
            
    def update_save_time(self):
        self.last_save_time = time.time()
    
    def get_current_session_time(self):
        if self.current_session_start is not None:
            return time.time() - self.current_session_start
        return 0.0
    
    def to_dict(self):
        return {
            "total_time": self.total_time,
            "sessions": self.sessions,
            "current_session_start": self.current_session_start,
            "last_save_time": self.last_save_time,
            "file_creation_time": self.file_creation_time,
            "file_id": self.file_id
        }
    
    def from_dict(self, data):
        self.total_time = data.get("total_time", 0.0)
        self.sessions = data.get("sessions", [])
        self.current_session_start = data.get("current_session_start")
        self.last_save_time = data.get("last_save_time")
        self.file_creation_time = data.get("file_creation_time")
        self.file_id = data.get("file_id", str(uuid.uuid4()))

# グローバル変数でTimeDataのインスタンスを保持
global_time_data = TimeData()

# 隠しテキストブロックからデータを読み込む／なければ新規作成
def load_hidden_text():
    text = bpy.data.texts.get(HIDDEN_TEXT_NAME)
    if text is None:
        text = bpy.data.texts.new(HIDDEN_TEXT_NAME)
        text.write(json.dumps(global_time_data.to_dict()))
    else:
        try:
            data = json.loads(text.as_string())
            global_time_data.from_dict(data)
        except Exception as e:
            print("Error loading time data:", e)
    return text

# 隠しテキストブロックにデータを書き込む
def save_hidden_text():
    text = bpy.data.texts.get(HIDDEN_TEXT_NAME)
    if text is None:
        text = bpy.data.texts.new(HIDDEN_TEXT_NAME)
    text.clear()
    text.write(json.dumps(global_time_data.to_dict(), indent=4))

# --- ハンドラー --- #

# ファイルロード時にセッションを開始
def on_load_post(dummy):
    print("ファイルロード完了: セッション開始")
    load_hidden_text()
    global_time_data.start_session()
    save_hidden_text()
    return None

# ファイル保存時に現在のセッションを終了し、保存時間を更新、その後新たなセッションを開始
def on_save_post(dummy):
    print("ファイル保存完了: 保存時刻更新とセッション更新")
    global_time_data.end_session()
    global_time_data.update_save_time()
    global_time_data.start_session()
    save_hidden_text()
    return None

# 1秒ごとにタイマーで更新（UI反映や定期保存）
def update_timer():
    save_hidden_text()
    return 1.0  # 次回呼び出しまでの秒数

# --- UIパネル --- #
class TIME_PT_Panel(bpy.types.Panel):
    bl_label = "作業時間トラッカー"
    bl_idname = "TIME_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Time"

    def draw(self, context):
        layout = self.layout

        # 合計作業時間（現在セッションも含む）
        total_time = global_time_data.total_time + global_time_data.get_current_session_time()
        minutes, seconds = divmod(int(total_time), 60)
        hours, minutes = divmod(minutes, 60)
        layout.label(text=f"合計作業時間: {hours}h {minutes}m {seconds}s")
        
        # 現在のセッション時間
        current = global_time_data.get_current_session_time()
        cmin, csec = divmod(int(current), 60)
        ch, cmin = divmod(cmin, 60)
        layout.label(text=f"現在セッション時間: {ch}h {cmin}m {csec}s")
        
        # 最後の保存からの経過時間
        if global_time_data.last_save_time:
            elapsed = time.time() - global_time_data.last_save_time
            emin, esec = divmod(int(elapsed), 60)
            eh, emin = divmod(emin, 60)
            layout.label(text=f"最後の保存から: {eh}h {emin}m {esec}s")
            if elapsed > 600:  # 10分以上未保存なら警告
                row = layout.row()
                row.alert = True
                row.label(text="警告: 10分以上未保存です!")
        else:
            layout.label(text="保存情報なし")
        
        # 時間データのリセット・レポート出力ボタン
        row = layout.row()
        row.operator("time.reset_data", text="時間データリセット")
        row = layout.row()
        row.operator("time.export_report", text="Markdownレポート出力")

# --- オペレーター --- #

# 時間データリセットオペレーター
class TIME_OT_ResetData(bpy.types.Operator):
    bl_idname = "time.reset_data"
    bl_label = "時間データリセット"

    def execute(self, context):
        global global_time_data
        global_time_data = TimeData()
        save_hidden_text()
        self.report({'INFO'}, "時間データをリセットしました。")
        return {'FINISHED'}

# Markdownレポート出力オペレーター
class TIME_OT_ExportReport(bpy.types.Operator):
    bl_idname = "time.export_report"
    bl_label = "Markdownレポート出力"

    def execute(self, context):
        report = generate_report()
        # レポートはコンソールに出力（必要に応じてファイル出力などに拡張可能）
        print(report)
        self.report({'INFO'}, "レポートをコンソールに出力しました。")
        return {'FINISHED'}

# レポート生成関数
def generate_report():
    report = []
    report.append("# 作業時間レポート")
    report.append(f"**ファイルID:** {global_time_data.file_id}")
    if global_time_data.file_creation_time:
        creation_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(global_time_data.file_creation_time))
        report.append(f"**ファイル作成日時:** {creation_time}")
    total = global_time_data.total_time + global_time_data.get_current_session_time()
    report.append(f"**合計作業時間:** {total:.2f}秒")
    current = global_time_data.get_current_session_time()
    report.append(f"**現在セッション時間:** {current:.2f}秒")
    if global_time_data.last_save_time:
        elapsed = time.time() - global_time_data.last_save_time
        report.append(f"**最後の保存からの経過時間:** {elapsed:.2f}秒")
    report.append("## セッション履歴")
    for session in global_time_data.sessions:
        s_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session['start']))
        e_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session['end']))
        duration = session['duration']
        report.append(f"- **開始:** {s_time}, **終了:** {e_time}, **期間:** {duration:.2f}秒")
    return "\n".join(report)

classes = (
    TIME_PT_Panel,
    TIME_OT_ResetData,
    TIME_OT_ExportReport,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(on_load_post)
    bpy.app.handlers.save_post.append(on_save_post)
    bpy.app.timers.register(update_timer)
    load_hidden_text()

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    if on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_post)
    if on_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_post)
    bpy.app.timers.unregister(update_timer)

if __name__ == "__main__":
    register()
