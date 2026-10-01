import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from src.config import settings


def find_chrome_executable(configured=""):
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())

    command = shutil.which("chrome.exe") or shutil.which("chrome")
    if command:
        candidates.append(Path(command))

    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.getenv(variable)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Google Chrome não encontrado. Defina BROWSER_EXECUTABLE no .env."
    )


def external_chrome_args(executable, profile, port, *, headless=False):
    args = [
        str(executable),
        f"--user-data-dir={profile}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    if headless:
        args.insert(-1, "--headless=new")
    return args


def existing_chrome_args(executable, url):
    return [str(executable), url]


def open_in_existing_chrome(url):
    executable = find_chrome_executable(settings.browser_executable)
    return subprocess.Popen(existing_chrome_args(executable, url))


def _available_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def _wait_for_cdp(process, port, timeout=20):
    endpoint = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "O Chrome encerrou antes de disponibilizar a inspeção. "
                "Verifique se o perfil já está aberto em outra janela."
            )
        try:
            with urlopen(f"{endpoint}/json/version", timeout=0.5) as response:
                if response.status == 200:
                    return endpoint
        except (OSError, URLError):
            time.sleep(0.1)
    raise TimeoutError("O Chrome não disponibilizou a inspeção local em 20 segundos.")

class SebraeBrowser:
    def __init__(self):
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.chrome_process = None

    def start(self):
        settings.browser_profile.mkdir(parents=True, exist_ok=True)
        self.pw = sync_playwright().start()
        try:
            if settings.browser_mode == "external_chrome":
                executable = find_chrome_executable(settings.browser_executable)
                port = _available_local_port()
                self.chrome_process = subprocess.Popen(
                    external_chrome_args(
                        executable,
                        settings.browser_profile,
                        port,
                        headless=settings.headless,
                    )
                )
                endpoint = _wait_for_cdp(self.chrome_process, port)
                self.browser = self.pw.chromium.connect_over_cdp(endpoint)
                self.context = self.browser.contexts[0]
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            elif settings.browser_mode == "playwright":
                self.context = self.pw.chromium.launch_persistent_context(
                    user_data_dir=str(settings.browser_profile),
                    channel=settings.browser_channel or None,
                    headless=settings.headless,
                    viewport={"width": 1440, "height": 900},
                )
                self.page = self.context.new_page()
            else:
                raise ValueError(
                    "BROWSER_MODE deve ser external_chrome ou playwright."
                )
            self.page.bring_to_front()
            return self.page
        except Exception:
            if self.chrome_process and self.chrome_process.poll() is None:
                self.chrome_process.terminate()
                self.chrome_process.wait(timeout=5)
            self.chrome_process = None
            self.pw.stop()
            self.pw = None
            raise

    def open_sebrae(self):
        url = settings.validated_sebrae_url()
        if not self.page:
            self.start()
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.bring_to_front()
        return self.page

    def close(self):
        try:
            if self.browser:
                try:
                    self.browser.close()
                except PlaywrightError:
                    pass
            elif self.context:
                try:
                    self.context.close()
                except PlaywrightError:
                    pass
        finally:
            self.browser = None
            self.context = None
            self.page = None
            if self.pw:
                try:
                    self.pw.stop()
                except PlaywrightError:
                    pass
                self.pw = None
            if self.chrome_process and self.chrome_process.poll() is None:
                self.chrome_process.terminate()
                try:
                    self.chrome_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.chrome_process.kill()
            self.chrome_process = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
