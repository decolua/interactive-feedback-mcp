# Interactive Feedback MCP
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import os
import sys
import json
import tempfile
import subprocess
import glob
from pathlib import Path

from typing import Annotated, Dict, Optional, List

from fastmcp import FastMCP
from pydantic import Field

# The log_level is necessary for Cline to work: https://github.com/jlowin/fastmcp/issues/81
mcp = FastMCP("Interactive Feedback MCP", log_level="ERROR")

def find_latest_modified_md_file(project_directory: str) -> Optional[str]:
    """Find the latest modified .md file in the project directory"""
    try:
        # Find all .md files in project directory (including subdirectories)
        md_pattern = os.path.join(project_directory, "**", "*.md")
        md_files = glob.glob(md_pattern, recursive=True)
        
        if not md_files:
            return None
        
        # Sort by modification time, newest first
        md_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Return path relative to project directory
        latest_file = md_files[0]
        return os.path.relpath(latest_file, project_directory)
    except Exception:
        return None

def enhance_modified_files(project_directory: str, modified_files: Optional[List[str]] = None) -> List[str]:
    """Enhance modified_files by automatically adding the latest modified .md file"""
    enhanced_files = modified_files.copy() if modified_files else []
    
    latest_md = find_latest_modified_md_file(project_directory)
    
    if latest_md and latest_md not in enhanced_files:
        enhanced_files.append(latest_md)
        print(f"🔍 Auto-detected latest modified .md file: {latest_md}", file=sys.stderr)
    
    return enhanced_files

def launch_feedback_ui(project_directory: str, summary: str, modified_files: Optional[List[str]] = None) -> dict[str, str]:
    enhanced_modified_files = enhance_modified_files(project_directory, modified_files)
    
    # Create a temporary file for the feedback result
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_file = tmp.name

    try:
        # Get the path to feedback_ui.py relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        feedback_ui_path = os.path.join(script_dir, "feedback_ui.py")

        # Run feedback_ui.py as a separate process
        # NOTE: There appears to be a bug in uv, so we need
        # to pass a bunch of special flags to make this work
        args = [
            sys.executable,
            "-u",
            feedback_ui_path,
            "--project-directory", project_directory,
            "--prompt", summary,
            "--output-file", output_file
        ]
        
        # Add enhanced modified files
        if enhanced_modified_files:
            args.extend(["--modified-files", json.dumps(enhanced_modified_files)])
        result = subprocess.run(
            args,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True
        )
        if result.returncode != 0:
            raise Exception(f"Failed to launch feedback UI: {result.returncode}")

        # Read the result from the temporary file
        with open(output_file, 'r') as f:
            result = json.load(f)
        os.unlink(output_file)
        return result
    except Exception as e:
        if os.path.exists(output_file):
            os.unlink(output_file)
        raise e

def first_line(text: str) -> str:
    return text.split("\n")[0].strip()

@mcp.tool()
def interactive_feedback(
    project_directory: Annotated[str, Field(description="Full path to the project directory")],
    summary: Annotated[str, Field(description="Short, one-line summary of the changes")],
    modified_files: Annotated[Optional[List[str]], Field(description="List of file paths that were modified", default=None)] = None,
) -> Dict[str, str]:
    """Request interactive feedback for a given project directory and summary"""
    return launch_feedback_ui(first_line(project_directory), first_line(summary), modified_files)

if __name__ == "__main__":
    mcp.run(transport="stdio")
