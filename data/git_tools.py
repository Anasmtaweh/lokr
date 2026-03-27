import subprocess
from pathlib import Path
from typing import List, Tuple

class GitWatchman:
    """
    Monitors a Git repository for file changes using `git status`.
    Designed for fast, incremental syncing of the ChromaDB vector store.
    """

    def get_changed_files(self, repo_path: Path) -> Tuple[List[Path], List[Path]]:
        """
        Runs `git status --porcelain` on the target repository and parses the output
        to classify changed files into modified/added and deleted categories.

        Args:
            repo_path (Path): The root path of the Git repository to inspect.

        Returns:
            Tuple[List[Path], List[Path]]: A tuple of two lists:
                - modified_files: Absolute Paths for Added (A), Modified (M), and Untracked (??) files.
                - deleted_files: Absolute Paths for Deleted (D) files.
        """
        repo_path = Path(repo_path).resolve()
        modified_files: List[Path] = []
        deleted_files: List[Path] = []

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                print(f"[WATCHMAN] git status returned non-zero exit code: {result.stderr.strip()}")
                return modified_files, deleted_files

            for line in result.stdout.splitlines():
                # git status --porcelain format: "XY filename"
                # lines are at least 4 chars: 2-char status + space + at least one char filename
                if not line or len(line) < 4:
                    continue

                # Split into status code and path cleanly without slice indexing
                # Format is always: "XY path" — first token is status, rest is the path
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    continue

                status: str = parts[0]
                raw_path: str = parts[1].strip()

                # Handle renames: "R old/path -> new/path" — take only destination
                if " -> " in raw_path:
                    raw_path = raw_path.split(" -> ")[-1].strip()

                file_path = (repo_path / raw_path).resolve()

                # Classify: Deleted vs. Modified/Added/Renamed/Untracked
                if "D" in status:
                    deleted_files.append(file_path)
                elif any(c in status for c in ("A", "M", "?", "R", "C", "U")):
                    modified_files.append(file_path)

        except FileNotFoundError:
            print("[WATCHMAN] ERROR: `git` command not found. Is Git installed?")
        except subprocess.TimeoutExpired:
            print("[WATCHMAN] ERROR: `git status` timed out after 10 seconds.")
        except Exception as e:
            print(f"[WATCHMAN] ERROR: Unexpected failure running git status: {e}")

        return modified_files, deleted_files
