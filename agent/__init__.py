from pathlib import Path

AGENT_DIR = Path(".agent")
CONFIG_PATH = AGENT_DIR / "config.toml"
SESSIONS_DIR = AGENT_DIR / "sessions"
INDEX_PATH = AGENT_DIR / "index.txt"
MODELS_CACHE_PATH = AGENT_DIR / "models.json"

DEFAULT_MODEL = "deepseek-ai/deepseek-v4-pro"
BASE_URL = "https://integrate.api.nvidia.com/v1"

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", "target",
}
TEXT_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".toml", ".md",
    ".txt", ".yaml", ".yml", ".html", ".css", ".sh", ".rs",
    ".go", ".java", ".c", ".cpp", ".h", ".sql", ".cfg", ".ini",
}

# Brand name
APP_NAME = "Revona CLI"
COMPANY = "LX Obsidian Labs"

# Brand colours (Rich markup)
C_PRIMARY = "black"
C_ACCENT = "bright_blue"
C_SUCCESS = "bright_green"
C_WARNING = "bright_yellow"
C_ERROR = "bright_red"
C_DIM = "bright_black"

REVONA_ASCII = """\
██████╗ ███████╗██╗   ██╗ ██████╗ ███╗   ██╗ █████╗
██╔══██╗██╔════╝██║   ██║██╔═══██╗████╗  ██║██╔══██╗
██████╔╝█████╗  ██║   ██║██║   ██║██╔██╗ ██║███████║
██╔══██╗██╔══╝  ╚██╗ ██╔╝██║   ██║██║╚██╗██║██╔══██║
██║  ██║███████╗ ╚████╔╝ ╚██████╔╝██║ ╚████║██║  ██║
╚═╝  ╚═╝╚══════╝  ╚═══╝   ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝"""


def ensure_dirs() -> None:
    AGENT_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
