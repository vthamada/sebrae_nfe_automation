import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.automation.browser import SebraeBrowser
from src.config import settings


SEBRAE_COOKIE_DOMAIN = re.compile(r"(^|\.)sebrae\.com\.br$", re.IGNORECASE)


def _is_sebrae_origin(origin):
    try:
        host = (urlsplit(origin).hostname or "").lower()
    except ValueError:
        return False
    return host == "sebrae.com.br" or host.endswith(".sebrae.com.br")


def _origin(raw_url):
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _diagnostic_origins():
    origins = set()
    for path in settings.log_dir.glob("sebrae_ui_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        candidates = [payload.get("url", "")]
        candidates.extend(page.get("url", "") for page in payload.get("pages", []))
        for candidate in candidates:
            origin = _origin(candidate)
            if origin and _is_sebrae_origin(origin):
                origins.add(origin)
    return origins


def main():
    browser = SebraeBrowser()
    try:
        browser.start()
        context = browser.context
        state = context.storage_state(indexed_db=True)
        origins = {
            item["origin"]
            for item in state.get("origins", [])
            if _is_sebrae_origin(item.get("origin", ""))
        }
        origins.update(_diagnostic_origins())
        origins.add("https://emissornfe.sebrae.com.br")

        matching_cookies = [
            cookie
            for cookie in context.cookies()
            if SEBRAE_COOKIE_DOMAIN.search(cookie.get("domain", ""))
        ]
        context.clear_cookies(domain=SEBRAE_COOKIE_DOMAIN)
        context.clear_permissions()

        session = context.new_cdp_session(browser.page)
        for origin in sorted(origins):
            session.send(
                "Storage.clearDataForOrigin",
                {"origin": origin, "storageTypes": "all"},
            )
        print(f"Cookies Sebrae removidos: {len(matching_cookies)}")
        print(f"Origens Sebrae limpas: {len(origins)}")
        print("Sessão local redefinida. Faça login novamente no próximo acesso.")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
