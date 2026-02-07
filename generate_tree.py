import os

# --- Configuration ---

# Directories to ignore to keep the tree clean
IGNORE_DIRS = {
    '.git',
    '__pycache__',
    'venv',
    '.venv',
    'env',
    '.idea',
    '.vscode',
    'node_modules',
    'instance',
    '.pytest_cache'
}


def generate_tree(dir_path, prefix, output_file):
    """
    Recursive function to traverse directories and write to file.
    """
    try:
        # Get list of all files and directories
        entries = os.listdir(dir_path)
    except PermissionError:
        output_file.write(f"{prefix}├── [ACCESS DENIED]\n")
        return

    # Filter ignored directories
    entries = [e for e in entries if e not in IGNORE_DIRS]

    # Sort: Directories first, then files (alphabetically)
    entries.sort(key=lambda s: (not os.path.isdir(os.path.join(dir_path, s)), s.lower()))

    entries_count = len(entries)

    for index, entry in enumerate(entries):
        path = os.path.join(dir_path, entry)
        is_last = (index == entries_count - 1)

        # Determine the branch connector
        connector = "└── " if is_last else "├── "

        # Add a slash if it is a directory for visual clarity
        display_name = entry + "/" if os.path.isdir(path) else entry

        # Write the line to the file
        output_file.write(f"{prefix}{connector}{display_name}\n")

        # If it is a directory, recurse into it
        if os.path.isdir(path):
            # Update the prefix for the next level
            extension = "    " if is_last else "│   "
            generate_tree(path, prefix + extension, output_file)


if __name__ == "__main__":
    # Get the current working directory
    root_dir = os.getcwd()
    root_name = os.path.basename(root_dir)
    output_filename = "project_structure.txt"

    print(f"Scanning directory: {root_dir}...")

    # Open the file with UTF-8 encoding to support tree characters
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(f"📂 Project Structure: {root_name}/\n")
        generate_tree(root_dir, "", f)

    print(f"✅ Done! Structure saved to '{output_filename}'")