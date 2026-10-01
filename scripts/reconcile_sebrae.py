import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings
from src.reconciliation import build_reconciliation, compact_summary
from src.repository import list_customers, list_products


def _latest_snapshot():
    candidates = sorted(settings.log_dir.glob("sebrae_snapshot_*.json"))
    workspace_candidates = sorted((ROOT / "logs").glob("sebrae_snapshot_*.json"))
    candidates.extend(path for path in workspace_candidates if path not in candidates)
    if not candidates:
        raise FileNotFoundError("Nenhum snapshot Sebrae foi encontrado.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(
        description="Compara o banco local com um snapshot somente leitura do Sebrae."
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--details",
        action="store_true",
        help="Mostra também nomes e diferenças detalhadas no terminal.",
    )
    args = parser.parse_args()

    snapshot_path = args.snapshot or _latest_snapshot()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    report = build_reconciliation(list_products(active_only=False), list_customers(active_only=False), snapshot)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or settings.log_dir / f"sebrae_reconciliation_{stamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(report if args.details else compact_summary(report), ensure_ascii=False, indent=2))
    print("Relatório detalhado:", output_path)
    print("Nenhum dado foi alterado no banco local ou no portal.")


if __name__ == "__main__":
    main()
