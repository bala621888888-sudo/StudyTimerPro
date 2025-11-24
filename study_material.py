"""
Study Material Management
Handles storage and retrieval of AI-generated study materials
"""

import os
import json
from pathlib import Path

# Base directory for study materials
STUDY_MATERIALS_DIR = os.path.join(os.path.dirname(__file__), "study_materials")

def ensure_materials_dir():
    """Create study_materials directory if it doesn't exist."""
    os.makedirs(STUDY_MATERIALS_DIR, exist_ok=True)

def get_material_path(plan_name, session_name):
    """
    Get file path for study material.
    
    Args:
        plan_name: Name of the plan
        session_name: Name of the session
        
    Returns:
        Path to the material file
    """
    ensure_materials_dir()
    plan_dir = os.path.join(STUDY_MATERIALS_DIR, plan_name)
    os.makedirs(plan_dir, exist_ok=True)
    
    # Sanitize session name for filename
    safe_name = "".join(c for c in session_name if c.isalnum() or c in (' ', '-', '_')).strip()
    return os.path.join(plan_dir, f"{safe_name}.json")

def save_study_material(plan_name, session_name, content):
    """
    Save generated study material.
    
    Args:
        plan_name: Name of the plan
        session_name: Name of the session
        content: The study material content (string)
    """
    file_path = get_material_path(plan_name, session_name)
    
    data = {
        "plan_name": plan_name,
        "session_name": session_name,
        "content": content,
        "last_generated": None  # Will be set when AI generates
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"[MATERIAL] Saved study material for {plan_name} - {session_name}")

def load_study_material(plan_name, session_name):
    """
    Load existing study material.
    
    Args:
        plan_name: Name of the plan
        session_name: Name of the session
        
    Returns:
        Material content (string) or None if not found
    """
    file_path = get_material_path(plan_name, session_name)
    
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("content", None)
    except Exception as e:
        print(f"[MATERIAL] Error loading material: {e}")
        return None

def material_exists(plan_name, session_name):
    """
    Check if study material exists for a session.
    
    Args:
        plan_name: Name of the plan
        session_name: Name of the session
        
    Returns:
        True if material exists, False otherwise
    """
    file_path = get_material_path(plan_name, session_name)
    return os.path.exists(file_path)