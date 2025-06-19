# Interactive Feedback MCP UI
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import os
import sys
import json
import psutil
import argparse
import subprocess
import threading
import hashlib

from typing import Optional, TypedDict, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox,
    QListWidget, QListWidgetItem, QSplitter, QScrollArea, QFrame,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QSettings
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtGui import QTextCursor, QIcon, QKeyEvent, QFont, QFontDatabase, QPalette, QColor

class FeedbackResult(TypedDict):
    command_logs: str
    interactive_feedback: str
    modified_files_content: Optional[str]
    selected_files: List[str]

class FeedbackConfig(TypedDict):
    run_command: str
    execute_automatically: bool

def set_dark_title_bar(widget: QWidget, dark_title_bar: bool) -> None:
    # Ensure we're on Windows
    if sys.platform != "win32":
        return

    from ctypes import windll, c_uint32, byref

    # Get Windows build number
    build_number = sys.getwindowsversion().build
    if build_number < 17763:  # Windows 10 1809 minimum
        return

    # Check if the widget's property already matches the setting
    dark_prop = widget.property("DarkTitleBar")
    if dark_prop is not None and dark_prop == dark_title_bar:
        return

    # Set the property (True if dark_title_bar != 0, False otherwise)
    widget.setProperty("DarkTitleBar", dark_title_bar)

    # Load dwmapi.dll and call DwmSetWindowAttribute
    dwmapi = windll.dwmapi
    hwnd = widget.winId()  # Get the window handle
    attribute = 20 if build_number >= 18985 else 19  # Use newer attribute for newer builds
    c_dark_title_bar = c_uint32(dark_title_bar)  # Convert to C-compatible uint32
    dwmapi.DwmSetWindowAttribute(hwnd, attribute, byref(c_dark_title_bar), 4)

    # HACK: Create a 1x1 pixel frameless window to force redraw
    temp_widget = QWidget(None, Qt.FramelessWindowHint)
    temp_widget.resize(1, 1)
    temp_widget.move(widget.pos())
    temp_widget.show()
    temp_widget.deleteLater()  # Safe deletion in Qt event loop

def get_dark_mode_palette(app: QApplication):
    darkPalette = app.palette()
    darkPalette.setColor(QPalette.Window, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.WindowText, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Base, QColor(42, 42, 42))
    darkPalette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    darkPalette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.ToolTipText, Qt.white)
    darkPalette.setColor(QPalette.Text, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Dark, QColor(35, 35, 35))
    darkPalette.setColor(QPalette.Shadow, QColor(20, 20, 20))
    darkPalette.setColor(QPalette.Button, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.ButtonText, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.BrightText, Qt.red)
    darkPalette.setColor(QPalette.Link, QColor(42, 130, 218))
    darkPalette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    darkPalette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    darkPalette.setColor(QPalette.HighlightedText, Qt.white)
    darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(127, 127, 127))
    darkPalette.setColor(QPalette.PlaceholderText, QColor(127, 127, 127))
    return darkPalette

def kill_tree(process: subprocess.Popen):
    killed: list[psutil.Process] = []
    parent = psutil.Process(process.pid)
    for proc in parent.children(recursive=True):
        try:
            proc.kill()
            killed.append(proc)
        except psutil.Error:
            pass
    try:
        parent.kill()
    except psutil.Error:
        pass
    killed.append(parent)

    # Terminate any remaining processes
    for proc in killed:
        try:
            if proc.is_running():
                proc.terminate()
        except psutil.Error:
            pass

def get_user_environment() -> dict[str, str]:
    if sys.platform != "win32":
        return os.environ.copy()

    import ctypes
    from ctypes import wintypes

    # Load required DLLs
    advapi32 = ctypes.WinDLL("advapi32")
    userenv = ctypes.WinDLL("userenv")
    kernel32 = ctypes.WinDLL("kernel32")

    # Constants
    TOKEN_QUERY = 0x0008

    # Function prototypes
    OpenProcessToken = advapi32.OpenProcessToken
    OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    OpenProcessToken.restype = wintypes.BOOL

    CreateEnvironmentBlock = userenv.CreateEnvironmentBlock
    CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.BOOL]
    CreateEnvironmentBlock.restype = wintypes.BOOL

    DestroyEnvironmentBlock = userenv.DestroyEnvironmentBlock
    DestroyEnvironmentBlock.argtypes = [wintypes.LPVOID]
    DestroyEnvironmentBlock.restype = wintypes.BOOL

    GetCurrentProcess = kernel32.GetCurrentProcess
    GetCurrentProcess.argtypes = []
    GetCurrentProcess.restype = wintypes.HANDLE

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    # Get process token
    token = wintypes.HANDLE()
    if not OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise RuntimeError("Failed to open process token")

    try:
        # Create environment block
        environment = ctypes.c_void_p()
        if not CreateEnvironmentBlock(ctypes.byref(environment), token, False):
            raise RuntimeError("Failed to create environment block")

        try:
            # Convert environment block to list of strings
            result = {}
            env_ptr = ctypes.cast(environment, ctypes.POINTER(ctypes.c_wchar))
            offset = 0

            while True:
                # Get string at current offset
                current_string = ""
                while env_ptr[offset] != "\0":
                    current_string += env_ptr[offset]
                    offset += 1

                # Skip null terminator
                offset += 1

                # Break if we hit double null terminator
                if not current_string:
                    break

                equal_index = current_string.index("=")
                if equal_index == -1:
                    continue

                key = current_string[:equal_index]
                value = current_string[equal_index + 1:]
                result[key] = value

            return result

        finally:
            DestroyEnvironmentBlock(environment)

    finally:
        CloseHandle(token)

class FeedbackTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            # Find the parent FeedbackUI instance and call submit
            parent = self.parent()
            while parent and not isinstance(parent, FeedbackUI):
                parent = parent.parent()
            if parent:
                parent._submit_feedback()
        else:
            super().keyPressEvent(event)

class LogSignals(QObject):
    append_log = Signal(str)

class ClickableFileItem(QWidget):
    """Custom widget for file items that can be clicked on text"""
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        # Default to checked only for .md files
        self.is_checked = file_path.lower().endswith('.md')
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)
        
        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.is_checked)
        self.checkbox.stateChanged.connect(self._on_checkbox_changed)
        
        # File label that's clickable
        self.file_label = QLabel(file_path)
        self.file_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                padding: 2px;
                border-radius: 2px;
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.1);
                cursor: pointer;
            }
        """)
        self.file_label.mousePressEvent = self._on_label_clicked
        
        # File size info
        self.size_label = QLabel()
        self.size_label.setStyleSheet("color: #888888; font-size: 9pt;")
        self._update_size_info()
        
        layout.addWidget(self.checkbox)
        layout.addWidget(self.file_label, 1)  # Take remaining space
        layout.addWidget(self.size_label)
        
    def _update_size_info(self):
        """Update file size information"""
        try:
            if hasattr(self.parent(), 'project_directory'):
                full_path = os.path.join(self.parent().project_directory, self.file_path)
            else:
                # Fallback: try to get from main window
                main_window = self
                while main_window.parent():
                    main_window = main_window.parent()
                if hasattr(main_window, 'project_directory'):
                    full_path = os.path.join(main_window.project_directory, self.file_path)
                else:
                    full_path = self.file_path
                    
            if os.path.exists(full_path):
                size = os.path.getsize(full_path)
                if size < 1024:
                    self.size_label.setText(f"{size}B")
                elif size < 1024 * 1024:
                    self.size_label.setText(f"{size/1024:.1f}KB")
                else:
                    self.size_label.setText(f"{size/(1024*1024):.1f}MB")
            else:
                self.size_label.setText("N/A")
        except:
            self.size_label.setText("")
    
    def _on_checkbox_changed(self, state):
        self.is_checked = state == Qt.Checked
        if hasattr(self.parent(), '_notify_selection_changed'):
            self.parent()._notify_selection_changed(self.file_path, self.is_checked)
    
    def _on_label_clicked(self, event):
        """Toggle checkbox when label is clicked"""
        self.checkbox.setChecked(not self.checkbox.isChecked())
        
    def setChecked(self, checked: bool):
        self.checkbox.setChecked(checked)
        
    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

class FileListWidget(QScrollArea):
    """Custom file list widget with clickable text"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None
        
        # Container widget
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(0)
        
        # Setup scroll area
        self.setWidget(self.container)
        self.setWidgetResizable(True)
        self.setMaximumHeight(120)  # Smaller height
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Style
        self.setStyleSheet("""
            QScrollArea {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #2b2b2b;
            }
        """)
        
        self.file_items = {}
        
    def set_main_window(self, main_window):
        """Set reference to main window for project directory access"""
        self.main_window = main_window
        
    def add_file(self, file_path: str):
        """Add a file to the list"""
        item = ClickableFileItem(file_path, self)
        # Set project directory for size calculation
        if self.main_window and hasattr(self.main_window, 'project_directory'):
            item.project_directory = self.main_window.project_directory
        self.file_items[file_path] = item
        self.layout.addWidget(item)
        
    def _notify_selection_changed(self, file_path: str, is_checked: bool):
        """Notify main window of selection changes"""
        if self.main_window and hasattr(self.main_window, '_on_file_selection_changed_new'):
            self.main_window._on_file_selection_changed_new(file_path, is_checked)
        # Reorder files after selection change
        self._reorder_files()
            
    def _reorder_files(self):
        """Reorder files to show checked files at the top"""
        # Get all file items and sort them: checked first, then unchecked
        sorted_items = sorted(
            self.file_items.items(),
            key=lambda x: (not x[1].isChecked(), x[0])  # False comes before True, so checked items first
        )
        
        # Remove all widgets from layout
        for file_path, item in self.file_items.items():
            self.layout.removeWidget(item)
        
        # Add widgets back in sorted order
        for file_path, item in sorted_items:
            self.layout.addWidget(item)
            
    def select_all(self):
        """Select all files"""
        for item in self.file_items.values():
            item.setChecked(True)
        self._reorder_files()
            
    def deselect_all(self):
        """Deselect all files"""
        for item in self.file_items.values():
            item.setChecked(False)
        self._reorder_files()
            
    def get_selected_files(self) -> List[str]:
        """Get list of selected files"""
        return [path for path, item in self.file_items.items() if item.isChecked()]

class FeedbackUI(QMainWindow):
    def __init__(self, project_directory: str, prompt: str, modified_files: Optional[List[str]] = None):
        super().__init__()
        self.project_directory = project_directory
        self.prompt = prompt
        self.modified_files = modified_files or []
        self.selected_files = set()  # Track which files are selected

        self.process: Optional[subprocess.Popen] = None
        self.log_buffer = []
        self.feedback_result = None
        self.log_signals = LogSignals()
        self.log_signals.append_log.connect(self._append_log)

        self.setWindowTitle("Interactive Feedback MCP")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "images", "feedback.png")
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        self.settings = QSettings("InteractiveFeedbackMCP", "InteractiveFeedbackMCP")
        
        # Load general UI settings for the main window (geometry, state)
        self.settings.beginGroup("MainWindow_General")
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(650, 550)  # Smaller width: 650 instead of 800
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - 650) // 2
            y = (screen.height() - 550) // 2
            self.move(x, y)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
        self.settings.endGroup() # End "MainWindow_General" group
        
        # Load project-specific settings (command, auto-execute, command section visibility)
        self.project_group_name = get_project_settings_group(self.project_directory)
        self.settings.beginGroup(self.project_group_name)
        loaded_run_command = self.settings.value("run_command", "", type=str)
        loaded_execute_auto = self.settings.value("execute_automatically", False, type=bool)
        command_section_visible = self.settings.value("commandSectionVisible", False, type=bool)
        self.settings.endGroup() # End project-specific group
        
        self.config: FeedbackConfig = {
            "run_command": loaded_run_command,
            "execute_automatically": loaded_execute_auto
        }

        self._create_ui() # self.config is used here to set initial values

        # Set command section visibility AFTER _create_ui has created relevant widgets
        self.command_group.setVisible(command_section_visible)
        if command_section_visible:
            self.toggle_command_button.setText("Hide Command Section")
        else:
            self.toggle_command_button.setText("Show Command Section")

        set_dark_title_bar(self, True)
        
        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Setup auto-save timer
        self._setup_auto_save()

        if self.config.get("execute_automatically", False):
            self._run_command()

    def _format_windows_path(self, path: str) -> str:
        if sys.platform == "win32":
            # Convert forward slashes to backslashes
            path = path.replace("/", "\\")
            # Capitalize drive letter if path starts with x:\
            if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
                path = path[0].upper() + path[1:]
        return path

    def _create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Toggle Command Section Button
        self.toggle_command_button = QPushButton("Show Command Section")
        self.toggle_command_button.clicked.connect(self._toggle_command_section)
        layout.addWidget(self.toggle_command_button)

        # Command section
        self.command_group = QGroupBox("Command")
        command_layout = QVBoxLayout(self.command_group)

        # Working directory label
        formatted_path = self._format_windows_path(self.project_directory)
        working_dir_label = QLabel(f"Working directory: {formatted_path}")
        command_layout.addWidget(working_dir_label)

        # Command input row
        command_input_layout = QHBoxLayout()
        self.command_entry = QLineEdit()
        self.command_entry.setText(self.config["run_command"])
        self.command_entry.returnPressed.connect(self._run_command)
        self.command_entry.textChanged.connect(self._update_config)
        self.run_button = QPushButton("&Run")
        self.run_button.clicked.connect(self._run_command)

        command_input_layout.addWidget(self.command_entry)
        command_input_layout.addWidget(self.run_button)
        command_layout.addLayout(command_input_layout)

        # Auto-execute and save config row
        auto_layout = QHBoxLayout()
        self.auto_check = QCheckBox("Execute automatically on next run")
        self.auto_check.setChecked(self.config.get("execute_automatically", False))
        self.auto_check.stateChanged.connect(self._update_config)

        save_button = QPushButton("&Save Configuration")
        save_button.clicked.connect(self._save_config)

        auto_layout.addWidget(self.auto_check)
        auto_layout.addStretch()
        auto_layout.addWidget(save_button)
        command_layout.addLayout(auto_layout)

        # Console section (now part of command_group)
        console_group = QGroupBox("Console")
        console_layout_internal = QVBoxLayout(console_group)
        console_group.setMinimumHeight(200)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        font.setPointSize(9)
        self.log_text.setFont(font)
        console_layout_internal.addWidget(self.log_text)

        # Clear button
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("&Clear")
        self.clear_button.clicked.connect(self.clear_logs)
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)
        console_layout_internal.addLayout(button_layout)
        
        command_layout.addWidget(console_group)

        self.command_group.setVisible(False) 
        layout.addWidget(self.command_group)

        # File Changes section (only show if modified_files provided)
        if self.modified_files:
            self._create_file_changes_section(layout)

        # Rules section
        self._create_rules_section(layout)

        # Quick Actions section
        self._create_quick_actions_section(layout)

        # Feedback section with adjusted height
        self.feedback_group = QGroupBox("Feedback")
        feedback_layout = QVBoxLayout(self.feedback_group)

        # Short description label (from self.prompt)
        self.description_label = QLabel(self.prompt)
        self.description_label.setWordWrap(True)
        feedback_layout.addWidget(self.description_label)

        self.feedback_text = FeedbackTextEdit()
        font_metrics = self.feedback_text.fontMetrics()
        row_height = font_metrics.height()
        # Calculate height for 5 lines + some padding for margins
        padding = self.feedback_text.contentsMargins().top() + self.feedback_text.contentsMargins().bottom() + 5 # 5 is extra vertical padding
        self.feedback_text.setMinimumHeight(5 * row_height + padding)

        self.feedback_text.setPlaceholderText("Enter your feedback here (Ctrl+Enter to submit)")
        submit_button = QPushButton("&Send Feedback (Ctrl+Enter)")
        submit_button.clicked.connect(self._submit_feedback)

        feedback_layout.addWidget(self.feedback_text)
        feedback_layout.addWidget(submit_button)

        # Set minimum height for feedback_group to accommodate its contents
        # This will be based on the description label and the 5-line feedback_text
        self.feedback_group.setMinimumHeight(self.description_label.sizeHint().height() + self.feedback_text.minimumHeight() + submit_button.sizeHint().height() + feedback_layout.spacing() * 2 + feedback_layout.contentsMargins().top() + feedback_layout.contentsMargins().bottom() + 10) # 10 for extra padding

        # Add widgets in a specific order
        layout.addWidget(self.feedback_group)



        # Credits/Contact Label
        contact_label = QLabel('Enhanced by AI • Contact Fábio Ferreira on <a href="https://x.com/fabiomlferreira">X.com</a> or visit <a href="https://dotcursorrules.com/">dotcursorrules.com</a>')
        contact_label.setOpenExternalLinks(True)
        contact_label.setAlignment(Qt.AlignCenter)
        contact_label.setStyleSheet("font-size: 9pt; color: #cccccc;") # Light gray for dark theme
        layout.addWidget(contact_label)

    def _create_file_changes_section(self, layout):
        """Create the file changes section with clickable files"""
        self.file_changes_group = QGroupBox("Modified Files")
        file_changes_layout = QVBoxLayout(self.file_changes_group)

        # Info row with file count and controls
        info_controls_layout = QHBoxLayout()
        
        # File count info
        file_count_label = QLabel(f"{len(self.modified_files)} files")
        file_count_label.setStyleSheet("color: #cccccc; font-size: 10pt;")
        
        # Control buttons (smaller)
        select_all_btn = QPushButton("All")
        deselect_all_btn = QPushButton("None")
        
        # Make buttons smaller
        for btn in [select_all_btn, deselect_all_btn]:
            btn.setMaximumWidth(50)
            btn.setStyleSheet("font-size: 9pt; padding: 2px 6px;")
        
        select_all_btn.clicked.connect(self._select_all_files)
        deselect_all_btn.clicked.connect(self._deselect_all_files)
        
        info_controls_layout.addWidget(file_count_label)
        info_controls_layout.addStretch()
        info_controls_layout.addWidget(select_all_btn)
        info_controls_layout.addWidget(deselect_all_btn)
        file_changes_layout.addLayout(info_controls_layout)

        # Custom file list
        self.file_list = FileListWidget(self)
        self.file_list.set_main_window(self)
        
        for file_path in self.modified_files:
            self.file_list.add_file(file_path)
            # Only add .md files to selected_files by default
            if file_path.lower().endswith('.md'):
                self.selected_files.add(file_path)
        
        # Reorder files to show checked files at the top initially
        self.file_list._reorder_files()
        
        file_changes_layout.addWidget(self.file_list)
        layout.addWidget(self.file_changes_group)

    def _create_quick_actions_section(self, layout):
        """Create enhanced quick action buttons with more features"""
        self.quick_actions_group = QGroupBox("Quick Actions")
        quick_actions_layout = QVBoxLayout(self.quick_actions_group)

        # Row 1: Main actions
        main_actions_layout = QHBoxLayout()
        main_actions = [
            ("✅ Continue", "Continue with the implementation."),
            ("💬 Discuss", "I have some questions about this approach."),
            ("🔧 Fix Issues", "There are some issues that need to be addressed."),
        ]

        for text, feedback in main_actions:
            btn = QPushButton(text)
            btn.setStyleSheet("font-size: 10pt; padding: 4px 8px;")
            btn.clicked.connect(lambda checked, f=feedback: self._set_quick_feedback(f))
            main_actions_layout.addWidget(btn)

        # Row 2: Secondary actions  
        secondary_actions_layout = QHBoxLayout()
        secondary_actions = [
            ("🧪 Add Tests", "Please add tests for these changes."),
            ("🎯 Perfect", "Perfect! These changes look great."),
            ("⏸️ Stop", "Stop here, I want to review manually.")
        ]

        for text, feedback in secondary_actions:
            btn = QPushButton(text)
            btn.setStyleSheet("font-size: 10pt; padding: 4px 8px;")
            btn.clicked.connect(lambda checked, f=feedback: self._set_quick_feedback(f))
            secondary_actions_layout.addWidget(btn)

        # Row 3: Advanced features
        advanced_layout = QHBoxLayout()
        
        # Preview button
        self.preview_btn = QPushButton("👁️ Preview")
        self.preview_btn.setStyleSheet("font-size: 9pt; padding: 2px 6px;")
        self.preview_btn.clicked.connect(self._show_file_preview)
        
        # Smart suggestions button
        self.smart_btn = QPushButton("🤖 Smart")
        self.smart_btn.setStyleSheet("font-size: 9pt; padding: 2px 6px;")
        self.smart_btn.clicked.connect(self._show_smart_suggestions)
        
        # Clear button
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setStyleSheet("font-size: 9pt; padding: 2px 6px;")
        clear_btn.clicked.connect(lambda: self.feedback_text.clear())
        
        advanced_layout.addWidget(self.preview_btn)
        advanced_layout.addWidget(self.smart_btn)
        advanced_layout.addStretch()
        advanced_layout.addWidget(clear_btn)

        quick_actions_layout.addLayout(main_actions_layout)
        quick_actions_layout.addLayout(secondary_actions_layout)
        quick_actions_layout.addLayout(advanced_layout)
        
        layout.addWidget(self.quick_actions_group)

    def _create_rules_section(self, layout):
        """Create rules selection section with checkboxes"""
        self.rules_group = QGroupBox("Additional Rules")
        rules_layout = QVBoxLayout(self.rules_group)
        
        # Rules checkboxes
        rules_container = QWidget()
        rules_container_layout = QVBoxLayout(rules_container)
        rules_container_layout.setContentsMargins(5, 5, 5, 5)
        rules_container_layout.setSpacing(3)
        
        # Define the rules as specified in the task
        self.rules_checkboxes = {}
        rules_config = [
            ("single_operation", "ALWAYS BATCH EDIT: GROUP all EDITS on the SAME FILE into ONE OPERATION, do NOT use MULTIPLE CALLS, READ ENTIRE FILE in ONE CALL, do NOT CREATE or MODIFY other FILES unless REQUESTED, applies to ALL TOOL CALLS."),
            ("no_new_md", "AFTER EVERY ACTION OR RESPONSE, THE AGENT MUST CALL MCP interactive_feedback — WITHOUT EXCEPTION — AND MUST NOT COMPLETE OR END THE PROCESS UNTIL USER FEEDBACK IS EMPTY."),
        ]
        
        for rule_key, rule_text in rules_config:
            # Create a container widget for better width control
            checkbox_container = QWidget()
            checkbox_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            
            container_layout = QHBoxLayout(checkbox_container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(8)
            
            # Create checkbox without text
            checkbox = QCheckBox()
            checkbox.setFixedSize(16, 16)  # Fixed size for the checkbox indicator
            
            # Create label with word wrap for the text
            label = QLabel(rule_text)
            label.setStyleSheet("color: #ffffff; font-size: 9pt;")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            
            # Make label clickable to toggle checkbox
            def make_label_clickable(cb):
                def label_clicked(event):
                    cb.setChecked(not cb.isChecked())
                return label_clicked
            
            label.mousePressEvent = make_label_clickable(checkbox)
            label.setStyleSheet("color: #ffffff; font-size: 9pt; cursor: pointer;")
            
            container_layout.addWidget(checkbox)
            container_layout.addWidget(label)
            
            # Store rule_key as property of checkbox for easy access
            checkbox.rule_key = rule_key
            # Store reference to label for getting text later
            checkbox.rule_label = label
            
            # Load saved state for this rule (default to True)
            self.settings.beginGroup(self.project_group_name)
            saved_state = self.settings.value(f"rule_{rule_key}", True, type=bool)
            self.settings.endGroup()
            
            # Set initial state
            checkbox.setChecked(True)
            
            # Store initial state to prevent unnecessary saves
            checkbox._initial_state = saved_state
            
            # Connect to save function AFTER setting initial state
            checkbox.stateChanged.connect(self._on_rule_checkbox_changed)
            
            self.rules_checkboxes[rule_key] = checkbox
            rules_container_layout.addWidget(checkbox_container)
        
        rules_layout.addWidget(rules_container)
        layout.addWidget(self.rules_group)
    
    def _on_rule_checkbox_changed(self, state):
        """Handle rule checkbox state change"""
        sender = self.sender()
        if hasattr(sender, 'rule_key'):
            rule_key = sender.rule_key
            checked = state == Qt.Checked
            
            # Only save if this is different from initial state (user actually changed it)
            if hasattr(sender, '_initial_state') and checked == sender._initial_state:
                return
                
            self._save_rule_state(rule_key, checked)
            
            # Update initial state to prevent repeated saves
            sender._initial_state = checked
    
    def _save_rule_state(self, rule_key: str, checked: bool):
        """Save rule checkbox state"""
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue(f"rule_{rule_key}", checked)
        self.settings.endGroup()
        # Force sync to ensure settings are saved immediately
        self.settings.sync()


    
    def _get_selected_rules(self) -> List[str]:
        """Get list of selected rules for inclusion in feedback"""
        selected_rules = []
        for rule_key, checkbox in self.rules_checkboxes.items():
            if checkbox.isChecked():
                # Get text from the associated label instead of checkbox
                rule_text = checkbox.rule_label.text() if hasattr(checkbox, 'rule_label') else checkbox.text()
                selected_rules.append(f"- {rule_text}")
        return selected_rules

    def _select_all_files(self):
        """Select all files in the list"""
        if hasattr(self, 'file_list'):
            self.file_list.select_all()
            # Update selected_files set to include all files
            self.selected_files = set(self.modified_files)

    def _deselect_all_files(self):
        """Deselect all files in the list"""
        if hasattr(self, 'file_list'):
            self.file_list.deselect_all()
            # Clear selected_files set
            self.selected_files.clear()

    def _on_file_selection_changed_new(self, file_path: str, is_checked: bool):
        """Handle file selection changes from custom widget"""
        if is_checked:
            self.selected_files.add(file_path)
        else:
            self.selected_files.discard(file_path)

    def _on_file_selection_changed(self, item):
        """Legacy handler for QListWidget - kept for compatibility"""
        file_path = item.text()
        if item.checkState() == Qt.Checked:
            self.selected_files.add(file_path)
        else:
            self.selected_files.discard(file_path)

    def _set_quick_feedback(self, feedback_text):
        """Set quick feedback text and focus on feedback area"""
        self.feedback_text.setPlainText(feedback_text)
        self.feedback_text.setFocus()
        
    def _show_file_preview(self):
        """Show quick preview of selected files"""
        if not self.selected_files:
            self._set_quick_feedback("⚠️ No files selected for preview.")
            return
            
        if len(self.selected_files) > 3:
            self._set_quick_feedback(f"📄 Preview: {len(self.selected_files)} files selected (too many to preview, will include in context)")
            return
            
        preview_lines = []
        preview_lines.append("📄 File Preview:")
        preview_lines.append("")
        
        for file_path in sorted(list(self.selected_files)[:3]):  # Max 3 files
            full_path = os.path.join(self.project_directory, file_path)
            try:
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    lines = content.split('\n')
                    size_info = f"{len(lines)} lines, {len(content)} chars"
                    
                    preview_lines.append(f"• {file_path} ({size_info})")
                    
                    # Show first few lines
                    for i, line in enumerate(lines[:3]):
                        preview_lines.append(f"  {i+1}: {line}")
                    if len(lines) > 3:
                        preview_lines.append(f"  ... ({len(lines) - 3} more lines)")
                    preview_lines.append("")
                else:
                    preview_lines.append(f"• {file_path} (file not found)")
                    preview_lines.append("")
            except Exception as e:
                preview_lines.append(f"• {file_path} (error: {str(e)})")
                preview_lines.append("")
        
        preview_lines.append("👆 Ready to include full content in feedback.")
        self.feedback_text.setPlainText('\n'.join(preview_lines))
        
    def _show_smart_suggestions(self):
        """Show smart suggestions based on file types and patterns"""
        if not self.selected_files:
            suggestions = [
                "🤖 Smart Suggestions:",
                "",
                "• General feedback: Continue with the implementation",
                "• If you see issues: Please fix the errors I mentioned",
                "• If you need more: Let's discuss this approach further",
                "• If it's good: Perfect! These changes look great"
            ]
        else:
            suggestions = ["🤖 Smart Suggestions based on files:"]
            suggestions.append("")
            
            # Analyze file types
            python_files = [f for f in self.selected_files if f.endswith('.py')]
            js_files = [f for f in self.selected_files if f.endswith(('.js', '.ts', '.jsx', '.tsx'))]
            test_files = [f for f in self.selected_files if 'test' in f.lower() or f.endswith('_test.py')]
            config_files = [f for f in self.selected_files if f.endswith(('.json', '.yaml', '.yml', '.toml', '.ini'))]
            
            if test_files:
                suggestions.append("🧪 Test files detected:")
                suggestions.append("• 'Run the tests to make sure they pass'")
                suggestions.append("• 'Add more test cases for edge cases'")
                suggestions.append("")
                
            if python_files:
                suggestions.append("🐍 Python files detected:")
                suggestions.append("• 'Check for PEP 8 compliance'")
                suggestions.append("• 'Add type hints if missing'")
                suggestions.append("• 'Consider adding docstrings'")
                suggestions.append("")
                
            if js_files:
                suggestions.append("📜 JavaScript/TypeScript files detected:")
                suggestions.append("• 'Run linter and fix any issues'")
                suggestions.append("• 'Check for proper error handling'")
                suggestions.append("• 'Ensure proper TypeScript types'")
                suggestions.append("")
                
            if config_files:
                suggestions.append("⚙️ Config files detected:")
                suggestions.append("• 'Validate configuration syntax'")
                suggestions.append("• 'Check if all required fields are present'")
                suggestions.append("")
                
            # File count based suggestions
            if len(self.selected_files) > 5:
                suggestions.append("📊 Many files changed:")
                suggestions.append("• 'This is a large change, let's break it down'")
                suggestions.append("• 'Please test thoroughly before proceeding'")
                suggestions.append("")
            
            suggestions.append("💡 General suggestions:")
            suggestions.append("• 'Continue - everything looks good'")
            suggestions.append("• 'Let's discuss - I have questions'")
            suggestions.append("• 'Fix issues - there are problems to address'")
            
        self.feedback_text.setPlainText('\n'.join(suggestions))

    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for better productivity"""
        # Ctrl+Enter: Submit feedback (already handled in FeedbackTextEdit)
        
        # Ctrl+1-6: Quick actions
        shortcuts_actions = [
            ("Ctrl+1", lambda: self._set_quick_feedback("Looks good, continue with the implementation.")),
            ("Ctrl+2", lambda: self._set_quick_feedback("I have some questions about this approach.")),
            ("Ctrl+3", lambda: self._set_quick_feedback("There are some issues that need to be addressed.")),
            ("Ctrl+4", lambda: self._set_quick_feedback("Please add tests for these changes.")),
            ("Ctrl+5", lambda: self._set_quick_feedback("Perfect! These changes look great.")),
            ("Ctrl+6", lambda: self._set_quick_feedback("Stop here, I want to review manually."))
        ]
        
        for shortcut_key, action in shortcuts_actions:
            shortcut = QShortcut(QKeySequence(shortcut_key), self)
            shortcut.activated.connect(action)
        
        # Ctrl+P: Preview files
        preview_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        preview_shortcut.activated.connect(self._show_file_preview)
        
        # Ctrl+S: Smart suggestions
        smart_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        smart_shortcut.activated.connect(self._show_smart_suggestions)
        
        # Ctrl+A: Select all files (when file list is focused)
        select_all_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        select_all_shortcut.activated.connect(self._select_all_files)
        
        # Ctrl+D: Deselect all files
        deselect_all_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        deselect_all_shortcut.activated.connect(self._deselect_all_files)
        
        # Escape: Clear feedback text
        clear_shortcut = QShortcut(QKeySequence("Escape"), self)
        clear_shortcut.activated.connect(lambda: self.feedback_text.clear())

    def _setup_auto_save(self):
        """Setup auto-save for feedback drafts"""
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save_draft)
        self.auto_save_timer.start(5000)  # Auto-save every 5 seconds
        
        # Load existing draft
        # self._load_draft()

    def _auto_save_draft(self):
        """Auto-save current feedback as draft"""
        if hasattr(self, 'feedback_text'):
            draft_text = self.feedback_text.toPlainText().strip()
            if draft_text:  # Only save if there's content
                self.settings.beginGroup(self.project_group_name)
                self.settings.setValue("feedback_draft", draft_text)
                self.settings.endGroup()

    def _load_draft(self):
        """Load saved draft if exists"""
        self.settings.beginGroup(self.project_group_name)
        draft = self.settings.value("feedback_draft", "", type=str)
        self.settings.endGroup()
        
        if draft and hasattr(self, 'feedback_text'):
            # Only load if feedback text is empty
            if not self.feedback_text.toPlainText().strip():
                self.feedback_text.setPlainText(draft)
                # Add a subtle indicator that this is a draft
                self.feedback_text.setPlaceholderText("Draft loaded - Ctrl+Enter to submit")

    def _clear_draft(self):
        """Clear saved draft"""
        self.settings.beginGroup(self.project_group_name)
        self.settings.remove("feedback_draft")
        self.settings.endGroup()

    def _get_selected_files_content(self):
        """Read content of selected files"""
        if not self.selected_files:
            return None
            
        content_parts = []
        content_parts.append("## Files Modified by User:")
        content_parts.append("")
        
        for file_path in sorted(self.selected_files):
            full_path = os.path.join(self.project_directory, file_path)
            try:
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    content_parts.append(f"### {file_path}")
                    content_parts.append("```")
                    content_parts.append(content)
                    content_parts.append("```")
                    content_parts.append("")
                else:
                    content_parts.append(f"### {file_path} (file not found)")
                    content_parts.append("")
            except Exception as e:
                content_parts.append(f"### {file_path} (error reading: {str(e)})")
                content_parts.append("")
        
        return "\n".join(content_parts)

    def _toggle_command_section(self):
        is_visible = self.command_group.isVisible()
        self.command_group.setVisible(not is_visible)
        if not is_visible:
            self.toggle_command_button.setText("Hide Command Section")
        else:
            self.toggle_command_button.setText("Show Command Section")
        
        # Immediately save the visibility state for this project
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("commandSectionVisible", self.command_group.isVisible())
        self.settings.endGroup()

        # Adjust window height only
        new_height = self.centralWidget().sizeHint().height()
        if self.command_group.isVisible() and self.command_group.layout().sizeHint().height() > 0 :
             # if command group became visible and has content, ensure enough height
             min_content_height = self.command_group.layout().sizeHint().height() + self.feedback_group.minimumHeight() + self.toggle_command_button.height() + layout().spacing() * 2
             new_height = max(new_height, min_content_height)

        current_width = self.width()
        self.resize(current_width, new_height)

    def _update_config(self):
        self.config["run_command"] = self.command_entry.text()
        self.config["execute_automatically"] = self.auto_check.isChecked()

    def _append_log(self, text: str):
        self.log_buffer.append(text)
        self.log_text.append(text.rstrip())
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    def _check_process_status(self):
        if self.process and self.process.poll() is not None:
            # Process has terminated
            exit_code = self.process.poll()
            self._append_log(f"\nProcess exited with code {exit_code}\n")
            self.run_button.setText("&Run")
            self.process = None
            self.activateWindow()
            self.feedback_text.setFocus()

    def _run_command(self):
        if self.process:
            kill_tree(self.process)
            self.process = None
            self.run_button.setText("&Run")
            return

        # Clear the log buffer but keep UI logs visible
        self.log_buffer = []

        command = self.command_entry.text()
        if not command:
            self._append_log("Please enter a command to run\n")
            return

        self._append_log(f"$ {command}\n")
        self.run_button.setText("Sto&p")

        try:
            self.process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.project_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_user_environment(),
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="ignore",
                close_fds=True,
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ""):
                    self.log_signals.append_log.emit(line)

            threading.Thread(
                target=read_output,
                args=(self.process.stdout,),
                daemon=True
            ).start()

            threading.Thread(
                target=read_output,
                args=(self.process.stderr,),
                daemon=True
            ).start()

            # Start process status checking
            self.status_timer = QTimer()
            self.status_timer.timeout.connect(self._check_process_status)
            self.status_timer.start(100)  # Check every 100ms

        except Exception as e:
            self._append_log(f"Error running command: {str(e)}\n")
            self.run_button.setText("&Run")

    def _submit_feedback(self):
        # Get selected files content
        selected_files_content = self._get_selected_files_content()
        
        # Get selected rules
        selected_rules = self._get_selected_rules()
        
        # Combine user feedback with file context and rules
        user_feedback = self.feedback_text.toPlainText().strip()
        combined_feedback = user_feedback
        
        # Add rules section if any rules are selected
        if selected_rules:
            rules_section = f"## Additional Rules to Apply:\n" + "\n".join(selected_rules)
            if combined_feedback:
                combined_feedback = f"{rules_section}\n\n{combined_feedback}"
            else:
                combined_feedback = rules_section
        
        # Add files content if any
        if selected_files_content:
            if combined_feedback:
                combined_feedback = f"{selected_files_content}\n\n## User Feedback:\n{combined_feedback}"
            else:
                combined_feedback = selected_files_content
        
        # Clear draft after successful submission
        self._clear_draft()
        
        self.feedback_result = FeedbackResult(
            command_logs="".join(self.log_buffer),
            interactive_feedback=combined_feedback,
            modified_files_content=selected_files_content,
            selected_files=list(self.selected_files)
        )
        self.close()

    def clear_logs(self):
        self.log_buffer = []
        self.log_text.clear()

    def _save_config(self):
        # Save run_command and execute_automatically to QSettings under project group
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("run_command", self.config["run_command"])
        self.settings.setValue("execute_automatically", self.config["execute_automatically"])
        self.settings.endGroup()
        self._append_log("Configuration saved for this project.\n")

    def closeEvent(self, event):
        # Save general UI settings for the main window (geometry, state)
        self.settings.beginGroup("MainWindow_General")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.endGroup()

        # Save project-specific command section visibility (this is now slightly redundant due to immediate save in toggle, but harmless)
        self.settings.beginGroup(self.project_group_name)
        self.settings.setValue("commandSectionVisible", self.command_group.isVisible())
        self.settings.endGroup()

        if self.process:
            kill_tree(self.process)
        super().closeEvent(event)

    def run(self) -> FeedbackResult:
        self.show()
        QApplication.instance().exec()

        if self.process:
            kill_tree(self.process)

        if not self.feedback_result:
            return FeedbackResult(
                command_logs="".join(self.log_buffer), 
                interactive_feedback="",
                modified_files_content=None,
                selected_files=[]
            )

        return self.feedback_result

def get_project_settings_group(project_dir: str) -> str:
    # Create a safe, unique group name from the project directory path
    # Using only the last component + hash of full path to keep it somewhat readable but unique
    basename = os.path.basename(os.path.normpath(project_dir))
    full_hash = hashlib.md5(project_dir.encode('utf-8')).hexdigest()[:8]
    return f"{basename}_{full_hash}"

def feedback_ui(project_directory: str, prompt: str, output_file: Optional[str] = None, modified_files: Optional[List[str]] = None) -> Optional[FeedbackResult]:
    app = QApplication.instance() or QApplication()
    app.setPalette(get_dark_mode_palette(app))
    app.setStyle("Fusion")
    ui = FeedbackUI(project_directory, prompt, modified_files)
    result = ui.run()

    if output_file and result:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        # Save the result to the output file
        with open(output_file, "w") as f:
            json.dump(result, f)
        return None

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the feedback UI")
    parser.add_argument("--project-directory", default=os.getcwd(), help="The project directory to run the command in")
    parser.add_argument("--prompt", default="I implemented the changes you requested.", help="The prompt to show to the user")
    parser.add_argument("--output-file", help="Path to save the feedback result as JSON")
    parser.add_argument("--modified-files", help="JSON string of modified file paths", default=None)
    args = parser.parse_args()

    modified_files = json.loads(args.modified_files) if args.modified_files else None
    result = feedback_ui(args.project_directory, args.prompt, args.output_file, modified_files)
    if result:
        print(f"\nLogs collected: \n{result['command_logs']}")
        print(f"\nFeedback received:\n{result['interactive_feedback']}")
        if result['selected_files']:
            print(f"\nSelected files: {', '.join(result['selected_files'])}")
    sys.exit(0)
