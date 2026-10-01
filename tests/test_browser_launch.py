import tempfile
import unittest
from pathlib import Path

from src.automation.browser import (
    existing_chrome_args,
    external_chrome_args,
    find_chrome_executable,
)


class BrowserLaunchTests(unittest.TestCase):
    def test_external_chrome_is_local_and_does_not_enable_playwright_automation(self):
        args = external_chrome_args(
            Path("C:/Chrome/chrome.exe"),
            Path("C:/Profile"),
            43123,
        )

        self.assertIn("--remote-debugging-address=127.0.0.1", args)
        self.assertIn("--remote-debugging-port=43123", args)
        self.assertNotIn("--remote-debugging-port=0", args)
        self.assertNotIn("--enable-automation", args)
        self.assertEqual(args[-1], "about:blank")

    def test_explicit_chrome_executable_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "chrome.exe"
            executable.touch()
            self.assertEqual(find_chrome_executable(str(executable)), executable.resolve())

    def test_existing_chrome_reuses_normal_profile_without_debug_flags(self):
        args = existing_chrome_args(
            Path("C:/Chrome/chrome.exe"),
            "https://emissornfe.sebrae.com.br/",
        )

        self.assertEqual(
            args,
            ["C:\\Chrome\\chrome.exe", "https://emissornfe.sebrae.com.br/"],
        )
        self.assertFalse(any(argument.startswith("--user-data-dir") for argument in args))
        self.assertFalse(any(argument.startswith("--remote-debugging") for argument in args))


if __name__ == "__main__":
    unittest.main()
