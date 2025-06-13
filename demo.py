#!/usr/bin/env python3
"""
Demo script for Enhanced Interactive Feedback MCP
Showcases the new file tracking and quick actions features
"""

import subprocess
import sys
import os

def run_demo():
    """Run the demo to show new features"""
    print("🚀 Enhanced Interactive Feedback MCP Demo")
    print("=" * 50)
    
    # Demo 1: Basic usage (backward compatible)
    print("\n📌 Demo 1: Basic Usage (Backward Compatible)")
    print("Running without modified_files parameter...")
    
    result1 = subprocess.run([
        sys.executable, "feedback_ui.py",
        "--project-directory", os.getcwd(),
        "--prompt", "Demo 1: Basic feedback without file tracking"
    ], capture_output=True, text=True)
    
    if result1.returncode == 0:
        print("✅ Basic mode works correctly")
    else:
        print(f"❌ Error: {result1.stderr}")
        
    # Demo 2: Enhanced usage with file tracking
    print("\n📌 Demo 2: Enhanced Usage with File Tracking")
    print("Running with modified_files parameter...")
    
    modified_files = ["server.py", "feedback_ui.py", "README.md"]
    
    import json
    result2 = subprocess.run([
        sys.executable, "feedback_ui.py", 
        "--project-directory", os.getcwd(),
        "--prompt", "Demo 2: File tracking with quick actions",
        "--modified-files", json.dumps(modified_files)
    ], capture_output=True, text=True, timeout=5)
    
    if result2.returncode == 0:
        print("✅ Enhanced mode works correctly")
    else:
        print(f"❌ Error: {result2.stderr}")
    
    # Demo 3: Show key features
    print("\n🎯 Key Features Implemented:")
    print("✅ File Change Tracking")
    print("  - AI can pass modified_files parameter") 
    print("  - UI shows clickable file list with size info")
    print("  - File content included in context")
    print()
    print("✅ Enhanced Quick Actions Panel")
    print("  - Continue, Discuss, Fix issues, Add tests, Perfect, Stop")
    print("  - Auto-fills feedback text with emoji icons")
    print("  - 2-row layout with advanced features")
    print()
    print("✅ Advanced Features (NEW!)")
    print("  - 👁️ File Preview (Ctrl+P): Quick content preview")
    print("  - 🤖 Smart Suggestions (Ctrl+Shift+S): AI-powered context advice")
    print("  - ⌨️ Keyboard Shortcuts: Ctrl+1-6 for quick actions")
    print("  - 💾 Auto-save Draft: Never lose your feedback")
    print()
    print("✅ UI/UX Improvements")
    print("  - Smaller window (650x550) for better screen usage")
    print("  - Clickable file text (not just checkbox)")
    print("  - File size display next to each file")
    print("  - Compact padding for cleaner look")
    print("  - Smart default selection (only .md files checked)")
    print("  - Help tooltips with keyboard shortcuts")
    print()
    print("✅ Enhanced Context Integration")
    print("  - Reads selected file contents")
    print("  - Combines with user feedback")
    print("  - Structured prompt format")
    print()
    print("✅ Backward Compatibility")
    print("  - Existing workflows unaffected")
    print("  - Optional parameters")
    print("  - Graceful degradation")
    
    # Demo 4: API usage examples
    print("\n💻 API Usage Examples:")
    print()
    print("# Basic usage:")
    print("interactive_feedback(")
    print("    project_directory='/path/to/project',")
    print("    summary='Made some changes'")
    print(")")
    print()
    print("# Enhanced usage:")
    print("interactive_feedback(")
    print("    project_directory='/path/to/project',")
    print("    summary='Refactored main components',")
    print("    modified_files=['src/main.py', 'src/utils.py']")
    print(")")
    
    print("\n🎉 Enhancement Phase 1 & 2.5 Complete!")
    print("🚀 Ready for AI-assisted development with:")
    print("   • Advanced context awareness")
    print("   • Productivity-focused UI")
    print("   • Smart suggestions & previews")
    print("   • Full keyboard workflow support")
    print("   • Auto-save reliability")
    print("\n💡 Try these shortcuts in the UI:")
    print("   Ctrl+P → Preview files")
    print("   Ctrl+Shift+S → Smart suggestions")
    print("   Ctrl+1-6 → Quick actions")
    print("   Click on file names → Toggle selection")

if __name__ == "__main__":
    try:
        run_demo()
    except Exception as e:
        print(f"Demo error: {e}")
        sys.exit(1) 