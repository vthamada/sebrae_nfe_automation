# Mapeado em 2026-08-25 na sessão autenticada do Chrome normal.
# Somente seletores confirmados são preenchidos; None continua significando que
# o campo não possui ainda um alvo estável e não deve ser automatizado.

ROUTES = {
    "products": "#/item",
    "services": "#/service",
    "brands": "#/brand",
    "categories": "#/category",
    "units": "#/item_unit",
    "customers": "#/client",
    "customer_new": "#/client/new",
    "invoice_nfe": "#/invoice/search/JTdCJTIySW52b2ljZU1vZGVsJTIyOjElN0Q=",
    "invoice_new": "#/invoice/new",
    "report_products": "#/report_products_price",
    "report_customers": "#/report_clients_birthday",
    "report_stock": "#/report_stock_kardex",
}

NEW_BUTTON = {"by": "css", "value": "#btAddNewActionBar"}

PRODUCT = {
    "menu_products": {"by": "route", "value": ROUTES["products"]},
    "new_button": NEW_BUTTON,
    "barcode": None,
    "description": None,
    "unit": None,
    "category": None,
    "subcategory": None,
    "brand": None,
    "model": None,
    "internal_code": None,
    "tags": {"by": "placeholder", "value": "Adicione uma tag"},
    "cost_price": None,
    "sale_price": None,
    "stock_qty": None,
    "min_stock": None,
    "ncm": {"by": "label", "value": "NCM"},
    "cest": {"by": "label", "value": "CEST"},
    "cfop": None,
    "origin": {"by": "label", "value": "Origem"},
    "characteristic": None,
    "classification": {"by": "label", "value": "Classificação"},
    "stock_tab": {"by": "role", "role": "button", "name": "Estoque"},
    "fiscal_tab": {"by": "role", "role": "button", "name": "Fiscal"},
    "save_button": None,
}

CUSTOMER = {
    "menu_customers": {"by": "route", "value": ROUTES["customers"]},
    "new_button": NEW_BUTTON,
    "document": None,
    "legal_name": None,
    "trade_name": None,
    "state_registration": None,
    "email": {"by": "label", "value": "Email"},
    "phone": {"by": "label", "value": "Telefone"},
    "zip_code": {"by": "label", "value": "CEP"},
    "street": None,
    "number": {"by": "label", "value": "Nº"},
    "complement": {"by": "label", "value": "Complemento"},
    "neighborhood": {"by": "label", "value": "Bairro"},
    "city": None,
    "state": None,
    "save_button": None,
}

INVOICE = {
    "menu_invoices": {"by": "route", "value": ROUTES["invoice_nfe"]},
    "new_button": NEW_BUTTON,
    "customer_search": {
        "by": "placeholder",
        "value": "Nome do cliente ou fornecedor",
    },
    "add_product": None,
    "product_search": None,
    "quantity": None,
    "unit_price": None,
    "discount": None,
    "total": None,
    "save_draft": None,
}
