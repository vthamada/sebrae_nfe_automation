from src.automation.browser import SebraeBrowser


class PortalMappingRequiredError(RuntimeError):
    """Raised before any portal mutation when the current UI has not been mapped."""


class SebraeAutomation:
    def __init__(self):
        self.browser = SebraeBrowser()
        self.page = None

    def start(self):
        self.page = self.browser.open_sebrae()
        return self.page

    def wait_for_manual_login(self):
        print("Faça o login manualmente no navegador.")
        input("Quando o painel estiver aberto, pressione ENTER... ")

    def prepare_product(self, product):
        raise PortalMappingRequiredError(
            "Cadastro no portal desativado: mapeie e homologue os seletores atuais primeiro."
        )

    def prepare_customer(self, customer):
        raise PortalMappingRequiredError(
            "Cadastro no portal desativado: mapeie e homologue os seletores atuais primeiro."
        )

    def prepare_invoice_draft(self, invoice):
        raise PortalMappingRequiredError(
            "Rascunho no portal desativado: mapeie e homologue os seletores atuais primeiro."
        )

    def close(self):
        self.browser.close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
