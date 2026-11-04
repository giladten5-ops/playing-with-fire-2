import os
from pathlib import Path

# Directories to ignore
IGNORE_DIRS = {
    ".git",
    ".vscode",
    ".idea",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    "target",
    "bin",
    "obj",
}

# File extensions to ignore (binaries, media, compiled files, locks)
IGNORE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".mp4", ".mp3", ".wav",
    ".pyc", ".pyo", ".pyd",
    ".exe", ".dll", ".so", ".dylib",
    ".zip", ".tar", ".gz", ".7z",
    ".pdf", ".doc", ".docx",
    ".sqlite3", ".db",
    ".lock",
}

# Specific files to ignore
IGNORE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    ".DS_Store",
    "project_dump.txt",      # Avoid dumping the output file into itself
    "export_project.py",     # Optional: ignore this export script
}


def is_text_file(filepath: Path) -> bool:
    """Check if a file is plain text by reading a small chunk."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            f.read(1024)
        return True
    except (UnicodeDecodeError, PermissionError):
        return False


def build_tree(root_dir: Path, prefix: str = "") -> list[str]:
    """Generate an ASCII tree structure of the project."""
    tree_lines = []
    
    entries = sorted(
        [e for e in root_dir.iterdir() if e.name not in IGNORE_DIRS and e.name not in IGNORE_FILES],
        key=lambda s: (not s.is_dir(), s.name.lower())
    )
    
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        tree_lines.append(f"{prefix}{connector}{entry.name}")
        
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            tree_lines.extend(build_tree(entry, prefix + extension))
            
    return tree_lines


def export_project(output_file: str = "project_dump.txt"):
    root_path = Path(".").resolve()
    output_path = root_path / output_file

    with open(output_path, "w", encoding="utf-8") as out:
        # 1. Header & Project Structure Tree
        out.write(f"PROJECT EXPORT: {root_path.name}\n")
        out.write("=" * 80 + "\n\n")
        out.write("DIRECTORY STRUCTURE:\n")
        out.write(".\n")
        tree_lines = build_tree(root_path)
        out.write("\n".join(tree_lines))
        out.write("\n\n" + "=" * 80 + "\n\n")

        # 2. Iterate through files and append content
        file_count = 0
        for current_root, dirs, files in os.walk(root_path):
            # Mutate dirs in-place to avoid traversing ignored folders
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for file in sorted(files):
                if file in IGNORE_FILES or file == output_file:
                    continue

                file_path = Path(current_root) / file
                
                if file_path.suffix.lower() in IGNORE_EXTENSIONS:
                    continue

                if not is_text_file(file_path):
                    continue

                relative_path = file_path.relative_to(root_path)
                
                # Write file boundary marker
                out.write(f"\n{'=' * 80}\n")
                out.write(f"FILE: {relative_path}\n")
                out.write(f"{'=' * 80}\n\n")

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        out.write(f.read())
                    out.write("\n")
                    file_count += 1
                except Exception as e:
                    out.write(f"[ERROR: Could not read file: {e}]\n")

        print(f"Export completed successfully!")
        print(f"Total text files exported: {file_count}")
        print(f"Saved to: {output_path}")


if __name__ == "__main__":
    export_project()