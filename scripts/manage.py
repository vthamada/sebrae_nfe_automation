import argparse
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings
from src.database import init_db
from src.rpa_plan import build_plan, order_from_local_invoice, verify_result, write_plan
from src.repository import (
    add_customer,
    add_product,
    adjust_stock,
    cancel_invoice,
    create_invoice_draft,
    list_customers,
    list_invoices,
    list_invoices_to_issue,
    list_low_stock_products,
    list_price_history,
    list_products,
    list_stock_movements,
    mark_invoice_ready,
    record_invoice_emitted,
    update_customer,
    update_product,
)


def _print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _product_payload(args):
    return {
        "internal_code": args.codigo,
        "barcode": args.codigo_barras,
        "description": args.descricao,
        "unit": args.unidade,
        "category": args.categoria,
        "subcategory": args.subcategoria,
        "brand": args.marca,
        "model": args.modelo,
        "tags": args.tags,
        "cost_price": args.custo,
        "sale_price": args.preco,
        "stock_qty": args.estoque,
        "min_stock": args.estoque_minimo,
        "ncm": args.ncm,
        "cest": args.cest,
        "cfop": args.cfop,
        "origin": args.origem,
        "moves_stock": not args.sem_estoque,
    }


def _customer_payload(args):
    return {
        "document": args.documento,
        "legal_name": args.nome,
        "trade_name": args.fantasia,
        "state_registration": args.inscricao_estadual,
        "email": args.email,
        "phone": args.telefone,
        "zip_code": args.cep,
        "street": args.logradouro,
        "number": args.numero,
        "complement": args.complemento,
        "neighborhood": args.bairro,
        "city": args.cidade,
        "state": args.uf,
        "country": args.pais,
    }


def _parse_item(raw):
    parts = [part.strip() for part in raw.split(";")]
    if len(parts) < 2 or len(parts) > 4 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError(
            "Item deve usar CODIGO;QUANTIDADE[;PRECO[;DESCONTO]]."
        )
    item = {"product_code": parts[0], "quantity": parts[1]}
    if len(parts) >= 3 and parts[2]:
        item["unit_price"] = parts[2]
    if len(parts) == 4 and parts[3]:
        item["discount"] = parts[3]
    return item


def _add_address_arguments(parser, *, required=False):
    parser.add_argument("--email")
    parser.add_argument("--telefone")
    parser.add_argument("--cep")
    parser.add_argument("--logradouro")
    parser.add_argument("--numero")
    parser.add_argument("--complemento")
    parser.add_argument("--bairro")
    parser.add_argument("--cidade")
    parser.add_argument("--uf", required=required)
    parser.add_argument("--pais", default="BRASIL" if required else None)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Gestão local de produtos, clientes, estoque e fila de NF-e."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Inicializa ou migra o banco local.")
    rpa = subparsers.add_parser("rpa-preparar", help="Valida pedido JSON e exporta plano de rascunho; não abre o portal.")
    rpa.add_argument("--pedido", required=True)
    rpa.add_argument("--saida", required=True)
    export = subparsers.add_parser("nota-exportar-rpa", help="Exporta nota local com mapeamento explícito dos produtos do portal.")
    export.add_argument("--id", type=int, required=True)
    export.add_argument("--config", required=True)
    export.add_argument("--saida", required=True)
    result = subparsers.add_parser("rpa-conferir-resultado", help="Confere recibo de rascunho; não registra emissão nem baixa estoque.")
    result.add_argument("--plano", required=True)
    result.add_argument("--resultado", required=True)

    product_add = subparsers.add_parser("produto-adicionar", help="Cadastra um produto.")
    product_add.add_argument("--codigo", help="Se omitido, gera PROD-001, PROD-002...")
    product_add.add_argument("--codigo-barras", help="Se omitido, gera código interno EAN-13.")
    product_add.add_argument("--descricao", required=True)
    product_add.add_argument("--unidade", required=True)
    product_add.add_argument("--categoria")
    product_add.add_argument("--subcategoria")
    product_add.add_argument("--marca")
    product_add.add_argument("--modelo")
    product_add.add_argument("--tags")
    product_add.add_argument("--custo", default="0")
    product_add.add_argument("--preco", required=True)
    product_add.add_argument("--estoque", default="0")
    product_add.add_argument("--estoque-minimo", default="0")
    product_add.add_argument("--ncm")
    product_add.add_argument("--cest")
    product_add.add_argument("--cfop")
    product_add.add_argument("--origem")
    product_add.add_argument("--sem-estoque", action="store_true")

    product_update = subparsers.add_parser("produto-atualizar", help="Atualiza dados ou preço.")
    product_update.add_argument("--codigo", required=True)
    product_update.add_argument("--motivo", required=True)
    product_update.add_argument("--descricao")
    product_update.add_argument("--unidade")
    product_update.add_argument("--codigo-barras")
    product_update.add_argument("--categoria")
    product_update.add_argument("--subcategoria")
    product_update.add_argument("--marca")
    product_update.add_argument("--modelo")
    product_update.add_argument("--tags")
    product_update.add_argument("--custo")
    product_update.add_argument("--preco")
    product_update.add_argument("--estoque-minimo")
    product_update.add_argument("--ncm")
    product_update.add_argument("--cest")
    product_update.add_argument("--cfop")
    product_update.add_argument("--origem")

    stock = subparsers.add_parser("estoque-ajustar", help="Registra entrada ou saída manual.")
    stock.add_argument("--codigo", required=True)
    stock.add_argument("--quantidade", required=True, help="Positiva para entrada; negativa para saída.")
    stock.add_argument("--motivo", required=True)

    customer_add = subparsers.add_parser("cliente-adicionar", help="Cadastra cliente por CPF/CNPJ.")
    customer_add.add_argument("--documento", required=True)
    customer_add.add_argument("--nome", required=True)
    customer_add.add_argument("--fantasia")
    customer_add.add_argument("--inscricao-estadual")
    _add_address_arguments(customer_add)

    customer_update = subparsers.add_parser("cliente-atualizar", help="Atualiza um cliente.")
    customer_update.add_argument("--documento", required=True)
    customer_update.add_argument("--nome")
    customer_update.add_argument("--fantasia")
    customer_update.add_argument("--inscricao-estadual")
    _add_address_arguments(customer_update)

    invoice_create = subparsers.add_parser("nota-criar", help="Cria rascunho e reserva estoque.")
    invoice_create.add_argument("--referencia", required=True)
    invoice_create.add_argument("--cliente", required=True, help="CPF ou CNPJ já cadastrado.")
    invoice_create.add_argument(
        "--item",
        action="append",
        type=_parse_item,
        required=True,
        help='Repita para cada item: "CODIGO;QUANTIDADE[;PRECO[;DESCONTO]]".',
    )
    invoice_create.add_argument("--observacoes")

    invoice_ready = subparsers.add_parser("nota-pronta", help="Libera um rascunho revisado para emissão.")
    invoice_ready.add_argument("--id", required=True, type=int)

    invoice_emitted = subparsers.add_parser(
        "nota-emitida", help="Registra emissão confirmada e baixa o estoque."
    )
    invoice_emitted.add_argument("--id", required=True, type=int)
    invoice_emitted.add_argument("--numero", required=True)
    invoice_emitted.add_argument("--chave", required=True)

    invoice_cancel = subparsers.add_parser(
        "nota-cancelar", help="Cancela antes da emissão e libera a reserva."
    )
    invoice_cancel.add_argument("--id", required=True, type=int)
    invoice_cancel.add_argument("--motivo", required=True)

    subparsers.add_parser("listar-produtos", help="Lista produtos e saldos.")
    product_history = subparsers.add_parser(
        "produto-historico", help="Lista preços e movimentos de estoque."
    )
    product_history.add_argument("--codigo", required=True)
    subparsers.add_parser("listar-clientes", help="Lista clientes ativos.")
    subparsers.add_parser("estoque-baixo", help="Lista produtos no estoque mínimo.")
    subparsers.add_parser("notas-a-emitir", help="Lista somente notas prontas para emissão.")
    invoice_list = subparsers.add_parser("listar-notas", help="Lista notas por status opcional.")
    invoice_list.add_argument(
        "--status", choices=["DRAFT", "READY_TO_ISSUE", "EMITTED", "CANCELLED"]
    )
    return parser


def _non_null_changes(args, mapping):
    return {
        target: getattr(args, source)
        for source, target in mapping.items()
        if getattr(args, source, None) is not None
    }


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "rpa-preparar":
        plan = build_plan(json.loads(Path(args.pedido).read_text(encoding="utf-8-sig")))
        destination = write_plan(plan, args.saida)
        _print_json({"status": "PREPARED", "file": str(destination.resolve()),
                     "total_cents": plan["total_cents"], "items": len(plan["items"]),
                     "issued": False, "stock_changed": False})
        return
    if args.command == "rpa-conferir-resultado":
        _print_json(verify_result(
            json.loads(Path(args.plano).read_text(encoding="utf-8-sig")),
            json.loads(Path(args.resultado).read_text(encoding="utf-8-sig")),
        ))
        return
    init_db()

    if args.command == "init":
        _print_json({"status": "ok", "database": str(settings.db_path)})
    elif args.command == "nota-exportar-rpa":
        from src.repository import get_invoice
        invoice = get_invoice(args.id)
        config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
        path = write_plan(build_plan(order_from_local_invoice(invoice, config)), args.saida)
        _print_json({"status": "PREPARED", "file": str(path.resolve()), "issued": False})
    elif args.command == "produto-adicionar":
        product_id = add_product(_product_payload(args))
        _print_json({"status": "created", "product_id": product_id})
    elif args.command == "produto-atualizar":
        mapping = {
            "descricao": "description",
            "unidade": "unit",
            "codigo_barras": "barcode",
            "categoria": "category",
            "subcategoria": "subcategory",
            "marca": "brand",
            "modelo": "model",
            "tags": "tags",
            "custo": "cost_price",
            "preco": "sale_price",
            "estoque_minimo": "min_stock",
            "ncm": "ncm",
            "cest": "cest",
            "cfop": "cfop",
            "origem": "origin",
        }
        _print_json(update_product(args.codigo, _non_null_changes(args, mapping), reason=args.motivo))
    elif args.command == "estoque-ajustar":
        _print_json(adjust_stock(args.codigo, args.quantidade, reason=args.motivo))
    elif args.command == "cliente-adicionar":
        customer_id = add_customer(_customer_payload(args))
        _print_json({"status": "created", "customer_id": customer_id})
    elif args.command == "cliente-atualizar":
        mapping = {
            "nome": "legal_name",
            "fantasia": "trade_name",
            "inscricao_estadual": "state_registration",
            "email": "email",
            "telefone": "phone",
            "cep": "zip_code",
            "logradouro": "street",
            "numero": "number",
            "complemento": "complement",
            "bairro": "neighborhood",
            "cidade": "city",
            "uf": "state",
            "pais": "country",
        }
        _print_json(update_customer(args.documento, _non_null_changes(args, mapping)))
    elif args.command == "nota-criar":
        _print_json(
            create_invoice_draft(
                reference=args.referencia,
                customer_document=args.cliente,
                items=args.item,
                notes=args.observacoes,
            )
        )
    elif args.command == "nota-pronta":
        _print_json(mark_invoice_ready(args.id))
    elif args.command == "nota-emitida":
        _print_json(
            record_invoice_emitted(args.id, invoice_number=args.numero, access_key=args.chave)
        )
    elif args.command == "nota-cancelar":
        _print_json(cancel_invoice(args.id, reason=args.motivo))
    elif args.command == "listar-produtos":
        _print_json(list_products())
    elif args.command == "produto-historico":
        _print_json(
            {
                "prices": list_price_history(args.codigo),
                "stock": list_stock_movements(args.codigo),
            }
        )
    elif args.command == "listar-clientes":
        _print_json(list_customers())
    elif args.command == "estoque-baixo":
        _print_json(list_low_stock_products())
    elif args.command == "notas-a-emitir":
        _print_json(list_invoices_to_issue())
    elif args.command == "listar-notas":
        _print_json(list_invoices(status=args.status))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
