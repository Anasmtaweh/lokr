import yaml
import pathspec
from pathlib import Path
from typing import Generator

class CodeScanner:
    """
    A scanner for discovering valid source code files within a target directory.
    Uses pathspec to respect both .gitignore rules and custom config ignores.
    Filters to an explicit allowlist of supported source code extensions.
    """

    # Explicit allowlist of file extensions the parser can handle.
    # If a file extension is not in this set, it will be skipped.
    SUPPORTED_EXTENSIONS = {
        # Python
        ".py",
        # JavaScript & JSX
        ".js", ".jsx", ".mjs", ".cjs",
        # TypeScript & TSX
        ".ts", ".tsx",
        # Web
        ".html", ".htm", ".css",
        # PHP
        ".php", ".php5", ".phtml",
        # Config & Data
        ".json", ".yml", ".yaml", ".env", ".example", ""
    }

    def __init__(self, target_dir: str | Path, config_path: str | Path = "config.yaml") -> None:
        """
        Initializes the CodeScanner with the target directory and configuration structure.

        Args:
            target_dir (str | Path): The root directory to scan.
            config_path (str | Path): The path to the configuration file (default: config.yaml).
        """
        self.target_dir = Path(target_dir).resolve()
        self.config_path = Path(config_path).resolve()
        
        # Build the unified pathspec from config and optionally .gitignore
        self.ignore_spec = self._build_ignore_spec()

    def _load_config_rules(self) -> list[str]:
        """
        Loads ignore rules from the config.yaml file.
        
        Returns:
            list[str]: A list of pathspec patterns from the config.
        """
        rules: list[str] = []
        if self.config_path.is_file():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
                
            for d in config.get('ignore_dirs', []):
                rules.append(f"{d}/")
            for ext in config.get('ignore_extensions', []):
                rules.append(f"*{ext}")
        return rules

    def _load_gitignore_rules(self) -> list[str]:
        """
        Loads ignore rules from a local .gitignore file, if present.
        
        Returns:
            list[str]: A list of pathspec patterns from .gitignore.
        """
        rules: list[str] = []
        # Support looking for a .gitignore at the target root
        gitignore_path = self.target_dir / ".gitignore"
        if gitignore_path.is_file():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_stripped = line.strip()
                    # Skip empty lines and comments
                    if line_stripped and not line_stripped.startswith('#'):
                        rules.append(line_stripped)
        return rules

    def _build_ignore_spec(self) -> pathspec.PathSpec:
        """
        Compiles the pathspec rules from both config.yaml and .gitignore.
        
        Returns:
            pathspec.PathSpec: The compiled pathspec object.
        """
        rules = self._load_config_rules() + self._load_gitignore_rules()
        return pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, rules)

    def get_files(self) -> Generator[Path, None, None]:
        """
        Traverses the directory tree and yields absolute paths of valid source code files.
        Safely ignores directories/files matching the pathspec rules, binary formats,
        and skips symlinks to avoid recursive loops.

        Yields:
            Path: Absolute path to a valid source code file.
        """
        if not self.target_dir.is_dir():
            print(f"Target directory {self.target_dir} does not exist or is not a directory.")
            return

        for path in self.target_dir.rglob('*'):
            # Skip symlinks to avoid loops or circular references
            if path.is_symlink():
                continue
            
            # We only want to yield files
            if not path.is_file():
                continue

            # Calculate relative posix path string for pathspec matching
            # pathspec natively uses posix-style paths for git wildmatch patterns
            rel_path = path.relative_to(self.target_dir).as_posix()

            # Skip if matched by our pathspec
            if self.ignore_spec.match_file(rel_path):
                continue

            # Only include files with explicitly supported extensions
            # Note: Dockerfiles have no extension (path.suffix == "")
            if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            # Verify it's a decodable text file, thus avoiding hidden binary distributions
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    # Read a microscopic chunk simply to test ascii/utf-8 compatibility
                    f.read(1024)
            except UnicodeDecodeError:
                # File is binary
                continue
            except Exception:
                # Other transient system read errors, skip safely
                continue

            # Valid text file, emit absolute path
            yield path.resolve()
