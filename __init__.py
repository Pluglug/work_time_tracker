bl_info = {
    "name": "Work Time Tracker",
    "author": "Your Name",
    "version": (1, 1),
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
TEXT_NAME = ".hidden_work_time.json"
UNSAVED_WARNING_THRESHOLD = 10 * 60  # 10 minutes in seconds

# Global variables
time_data = None
timer = None

class TimeData:
    def __init__(self):
        # Default values
        self.total_time = 0  # Total tracked time in seconds
        self.last_save_time = time.time()
        self.sessions = []  # List of sessions with start/end times
        self.file_creation_time = time.time()  # Track when the file was first created
        self.file_id = None  # Store a unique ID for this blend file
        self.current_session_start = None
        self.data_loaded = False
    
    def ensure_loaded(self):
        """Make sure data is loaded (safe to call after Blender is fully initialized)"""
        if not self.data_loaded:
            self.load_data()
            self.data_loaded = True
            
    def start_session(self):
        """Start a new session - only call this during file load"""
        # End any existing active sessions first
        self.end_active_sessions()
        
        # Now start a new session
        self.current_session_start = time.time()
        self.sessions.append({
            'start': self.current_session_start,
            'end': None,
            'duration': 0
        })
        print(f"Started new session at {datetime.datetime.fromtimestamp(self.current_session_start)}")
        
    def end_active_sessions(self):
        """End any active sessions - useful when switching files or closing Blender"""
        end_time = time.time()
        session_ended = False
        
        for session in self.sessions:
            if session['end'] is None:
                session['end'] = end_time
                session['duration'] = session['end'] - session['start']
                print(f"Ended session: {datetime.datetime.fromtimestamp(session['start'])} to {datetime.datetime.fromtimestamp(session['end'])}")
                session_ended = True
                
        if session_ended:
            # Update total time
            self.total_time = sum(session.get('duration', 0) for session in self.sessions)
            return True
        return False

    def load_data(self):
        """Load time tracking data from text block"""
        # Set file_id based on current blend file
        if bpy.data.filepath:
            self.file_id = bpy.path.basename(bpy.data.filepath)
        else:
            self.file_id = "unsaved_file"
        
        print(f"Current file path: {bpy.data.filepath}")
        print(f"Setting file_id to: {self.file_id}")
        
        # Try to load existing data
        text_block = self._get_text_block()
        if text_block and text_block.as_string():
            try:
                data = json.loads(text_block.as_string())
                self.total_time = data.get('total_time', 0)
                self.last_save_time = data.get('last_save_time', time.time())
                self.sessions = data.get('sessions', [])
                self.file_creation_time = data.get('file_creation_time', time.time())
                self.file_id = data.get('file_id', self.file_id)
                self.current_session_start = None  # Always reset session start
                print(f"Loaded time data: {len(self.sessions)} sessions, {self.format_time(self.total_time)} total time")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error parsing JSON: {e}")
                # If JSON is invalid, use default values
                pass
        else:
            # If no text block exists, this is the first time opening this file
            # Create a new file_creation_time
            self.file_creation_time = time.time()
            print(f"No existing time data found, created new data")
            # Create an initial text block
            self.save_data()
    
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
        if bpy.data.filepath and not self.file_id:
            self.file_id = bpy.path.basename(bpy.data.filepath)
        
        data = {
            'total_time': self.total_time,
            'last_save_time': self.last_save_time,
            'sessions': self.sessions,
            'file_creation_time': self.file_creation_time,
            'file_id': self.file_id
        }
        
        # Save to text block
        text_block = self._get_text_block(create=True)
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
    
    def _get_text_block(self, create=False):
        """Get or create the text block for storing data"""
        # Safely check if texts collection is available
        if not hasattr(bpy.data, 'texts'):
            return None
            
        if TEXT_NAME in bpy.data.texts:
            return bpy.data.texts[TEXT_NAME]
        elif create:
            try:
                return bpy.data.texts.new(TEXT_NAME)
            except (AttributeError, RuntimeError) as e:
                print(f"Error creating text block: {e}")
                return None
        return None
    
    def format_time(self, seconds):
        """Format seconds into readable time string"""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

@persistent
def load_handler(dummy):
    """Handler called when a blend file is loaded"""
    global time_data
    
    filepath = getattr(bpy.data, 'filepath', '')
    print(f"load_handler called for file: {filepath}")
    
    # Initialize time_data if it doesn't exist
    if time_data is None:
        time_data = TimeData()
    
    # We must ensure data is loaded before creating a new session
    # so we preserve previous sessions
    time_data.ensure_loaded()
    
    # Detect if this is a NEW file (read_homefile or new Blender session)
    if not filepath:
        # This is likely a new unsaved file, so we should reset the file_id
        print("Detected new unsaved file - resetting file_id")
        time_data.file_id = "unsaved_file"
    elif filepath and time_data.file_id != bpy.path.basename(filepath):
        # This is a different file than what we had before
        print(f"Detected new file: {bpy.path.basename(filepath)}")
        time_data.file_id = bpy.path.basename(filepath)
    
    # Start a new session (this will automatically end any active session)
    time_data.start_session()
    
    # Save the updated data
    time_data.save_data()
    
    # Start the timer for UI updates
    start_timer()

@persistent
def save_handler(dummy):
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

def on_blender_exit():
    """Function called when Blender is closing"""
    global time_data
    if time_data:
        print("Blender is closing. Ending active sessions.")
        time_data.end_active_sessions()
        time_data.save_data()
        print("Final time data saved.")

def delayed_start():
    """Start the timer after Blender is fully initialized"""
    if time_data:
        time_data.ensure_loaded()
        # Debug - check if we have the correct file_id
        if bpy.data.filepath:
            current_file = bpy.path.basename(bpy.data.filepath)
            if time_data.file_id != current_file:
                print(f"Warning: file_id mismatch. Expected {current_file}, got {time_data.file_id}")
                time_data.file_id = current_file
                time_data.save_data()
                print(f"Corrected file_id to {time_data.file_id}")
    start_timer()
    return None  # Don't repeat

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
            if time_since_save > UNSAVED_WARNING_THRESHOLD:
                row_alert = layout.row()
                row_alert.alert = True
                row_alert.label(text=f"⚠️ {time_data.get_formatted_time_since_save()}")
                row_alert = layout.row()
                row_alert.alert = True
                row_alert.label(text="Consider saving your work!")
            else:
                row.label(text=time_data.get_formatted_time_since_save())
            
            # File info
            if time_data.file_id:
                layout.separator()
                row = layout.row()
                row.label(text=f"File ID: {time_data.file_id}")
                
                if time_data.file_creation_time:
                    creation_time = datetime.datetime.fromtimestamp(time_data.file_creation_time)
                    row = layout.row()
                    row.label(text=f"Created: {creation_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Reset button
            layout.separator()
            layout.operator("timetracker.reset_data", text="Reset Time Data")
            
            # Export button
            layout.operator("timetracker.export_data", text="Export Time Report")

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
                report.write(f"- Duration: {formatted_duration}\n\n")
            
            self.report({'INFO'}, f"Report created: {report_name}")
            return {'FINISHED'}
        return {'CANCELLED'}

# Visual Time Graph class (to be implemented in view_3d_draw_handler)
def draw_time_graph(self, context):
    # This will be implemented to draw a visual time graph
    pass

classes = (
    VIEW3D_PT_time_tracker,
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
    print("Time Tracker registered. Version 1.1")
    
    # Set a timer to start the actual timer after Blender is initialized
    bpy.app.timers.register(delayed_start, first_interval=1.0)
    
    # Register a handler for Blender exit
    atexit.register(on_blender_exit)

def unregister():
    # End any active sessions before unregistering
    if time_data:
        time_data.end_active_sessions()
        time_data.save_data()
    
    # Stop timer
    stop_timer()
    
    # Unregister handlers
    if load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler)
    if save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(save_handler)
    
    # Unregister atexit handler (if possible)
    try:
        atexit.unregister(on_blender_exit)
    except:
        pass
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()