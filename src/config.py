from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _bool_setting(name, default="false"):
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "sim"}


def _path_setting(name, default):
    configured = os.getenv(name)
    raw_value = configured.strip() if configured and configured.strip() else str(default)
    raw = os.path.expandvars(os.path.expanduser(raw_value))
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


LOCAL_DATA_ROOT = Path(os.getenv("LOCALAPPDATA", ROOT / "data")) / "SebraeNFeAutomation"
PRODUCTION_HOST = "emissornfe.sebrae.com.br"


def validate_sebrae_url(url, *, allowed_hosts, allow_production):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise ValueError("A URL do Sebrae deve usar HTTPS e possuir um host válido.")
    if host not in allowed_hosts:
        raise ValueError(f"Host não autorizado para automação: {host}")
    if host == PRODUCTION_HOST and not allow_production:
        raise RuntimeError(
            "Abertura do emissor de produção bloqueada. Defina ALLOW_PRODUCTION=true "
            "somente para uma operação supervisionada."
        )
    return url

@dataclass(frozen=True)
class Settings:
    sebrae_url: str = os.getenv(
        "SEBRAE_URL",
        "https://emissornfe.sebrae.com.br/"
    ).strip()
    allowed_hosts: tuple = tuple(
        host.strip().lower()
        for host in os.getenv("SEBRAE_ALLOWED_HOSTS", PRODUCTION_HOST).split(",")
        if host.strip()
    )
    allow_production: bool = _bool_setting("ALLOW_PRODUCTION")
    headless: bool = _bool_setting("HEADLESS")
    browser_mode: str = os.getenv("BROWSER_MODE", "external_chrome").strip().lower()
    browser_channel: str = os.getenv("BROWSER_CHANNEL", "chrome").strip()
    browser_executable: str = os.getenv("BROWSER_EXECUTABLE", "").strip()
    capture_screenshot: bool = _bool_setting("CAPTURE_SCREENSHOT")
    db_path: Path = _path_setting("DB_PATH", LOCAL_DATA_ROOT / "sebrae.db")
    browser_profile: Path = _path_setting(
        "BROWSER_PROFILE", LOCAL_DATA_ROOT / "inspector-profile-v2"
    )
    screenshot_dir: Path = _path_setting(
        "SCREENSHOT_DIR", LOCAL_DATA_ROOT / "screenshots"
    )
    log_dir: Path = _path_setting("LOG_DIR", LOCAL_DATA_ROOT / "logs")

    def validated_sebrae_url(self):
        return validate_sebrae_url(
            self.sebrae_url,
            allowed_hosts=self.allowed_hosts,
            allow_production=self.allow_production,
        )

settings = Settings()
