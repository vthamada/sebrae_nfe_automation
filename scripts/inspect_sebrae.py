from pathlib import Path
from datetime import datetime
import argparse
import json
import sys
from urllib.parse import urlsplit, urlunsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.automation.browser import SebraeBrowser, open_in_existing_chrome
from src.config import settings, validate_sebrae_url

JS = r'''
() => {
  const nodes = Array.from(document.querySelectorAll(
    'input, select, textarea, button, [role="button"], [role="combobox"], [role="textbox"]'
  ));
  function getLabel(el) {
    if (el.labels && el.labels.length) {
      return Array.from(el.labels).map(x => x.innerText.trim()).filter(Boolean).join(' | ');
    }
    const id = el.getAttribute('id');
    if (id) {
      const lb = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (lb) return lb.innerText.trim();
    }
    const parent = el.closest('label');
    return parent ? parent.innerText.trim() : '';
  }
  return nodes.map((el, i) => ({
    index: i,
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    role: el.getAttribute('role'),
    id: el.getAttribute('id'),
    name: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'),
    ariaLabel: el.getAttribute('aria-label'),
    label: getLabel(el),
    text: el.tagName.toLowerCase() === 'button'
      ? (el.innerText || '').trim().slice(0,120)
      : '',
    disabled: !!el.disabled
  }));
}
'''


def _safe_url(raw_url):
    try:
        parsed = urlsplit(raw_url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return "URL inválida"


def _attach_diagnostics(context):
    events = []
    attached = set()

    def record(kind, detail):
        if len(events) < 200:
            events.append({"kind": kind, **detail})

    def attach(page):
        page_id = id(page)
        if page_id in attached:
            return
        attached.add(page_id)
        page.on(
            "console",
            lambda message: record(
                "console",
                {"type": message.type, "text": message.text[:500]},
            )
            if message.type in {"error", "warning"}
            else None,
        )
        page.on(
            "pageerror",
            lambda error: record("pageerror", {"text": str(error)[:500]}),
        )
        page.on(
            "requestfailed",
            lambda request: record(
                "requestfailed",
                {
                    "resource_type": request.resource_type,
                    "url": _safe_url(request.url),
                    "failure": request.failure,
                },
            ),
        )
        page.on(
            "response",
            lambda response: record(
                "http_error",
                {"status": response.status, "url": _safe_url(response.url)},
            )
            if response.status >= 400
            else None,
        )

    context.on("page", attach)
    for current_page in context.pages:
        attach(current_page)
    return events


def _current_portal_page(context):
    pages = [page for page in context.pages if not page.is_closed()]
    portal_pages = [
        page
        for page in pages
        if page.url != "about:blank" and ".emissornfe.sebrae.com.br" in page.url
    ]
    if portal_pages:
        return portal_pages[-1]
    non_blank = [page for page in pages if page.url != "about:blank"]
    return non_blank[-1] if non_blank else pages[-1]

def main():
    parser = argparse.ArgumentParser(description="Mapeia campos visíveis do Emissor Sebrae.")
    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Captura a tela inteira; pode conter dados pessoais ou fiscais.",
    )
    parser.add_argument(
        "--diagnose-seconds",
        type=int,
        default=5,
        help="Tempo de observação de falhas após pressionar ENTER.",
    )
    parser.add_argument(
        "--isolated-diagnostic",
        action="store_true",
        help=(
            "Tenta capturar por um perfil isolado. Use somente para diagnóstico; "
            "o portal atual pode bloquear essa sessão na tela de carregamento."
        ),
    )
    args = parser.parse_args()

    if not args.isolated_diagnostic:
        # Este caminho apenas abre uma aba para inspeção humana. A proteção
        # ALLOW_PRODUCTION continua obrigatória no modo automatizado isolado.
        url = validate_sebrae_url(
            settings.sebrae_url,
            allowed_hosts=settings.allowed_hosts,
            allow_production=True,
        )
        open_in_existing_chrome(url)
        print("Portal aberto no Chrome normal, reutilizando a sessão já autenticada.")
        print("A captura deve ser solicitada no Codex, que usa a conexão autorizada do Chrome.")
        print("O terminal não acessa cookies nem o conteúdo dessa sessão e será encerrado.")
        return

    browser = SebraeBrowser()
    try:
        browser.start()
        diagnostics = _attach_diagnostics(browser.context)
        # Este caminho somente lê a interface e é sempre supervisionado. A
        # proteção de produção continua ativa nas classes que alterariam dados.
        url = validate_sebrae_url(
            settings.sebrae_url,
            allowed_hosts=settings.allowed_hosts,
            allow_production=True,
        )
        page = browser.page
        page.goto(url, wait_until="domcontentloaded")
        page.bring_to_front()
        print("URL aberta pelo inspector:", page.url)
        print("Faça login manualmente e navegue até a tela a mapear.")
        input("Quando estiver na tela correta, pressione ENTER... ")

        page = _current_portal_page(browser.context)
        page.bring_to_front()
        if args.diagnose_seconds > 0:
            page.wait_for_timeout(args.diagnose_seconds * 1000)
        print("Aba selecionada para inspeção:", page.url)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        out = settings.log_dir / f"sebrae_ui_{stamp}.json"
        screenshot_path = None
        if args.screenshot or settings.capture_screenshot:
            settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = settings.screenshot_dir / f"sebrae_ui_{stamp}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)

        payload = {
            "url": _safe_url(page.url),
            "title": page.title(),
            "note": "Valores digitados nos inputs não são coletados no JSON.",
            "ready_state": page.evaluate("document.readyState"),
            "pages": [
                {"url": _safe_url(current.url), "closed": current.is_closed()}
                for current in browser.context.pages
            ],
            "diagnostics": diagnostics,
            "elements": page.evaluate(JS),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if screenshot_path:
            print("Screenshot sensível:", screenshot_path)
        print("Mapa da interface:", out)
        print("Revise o JSON e qualquer screenshot antes de compartilhá-los.")
        input("Pressione ENTER para encerrar... ")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
