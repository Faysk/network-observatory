"""Validate alert rules offline without starting the Observatory or touching the router.

Example:
  python tools/check_alert_rules.py /mnt/sd/observatory-alerts.json
"""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.operations import validate_rules


def main():
    parser=argparse.ArgumentParser(description='Validate local passive Observatory alert rules')
    parser.add_argument('path',type=Path,help='Local rules JSON; never uploaded')
    args=parser.parse_args()
    try:
        path=args.path
        if not path.is_file() or path.stat().st_size>8192:
            raise ValueError('File must exist and contain at most 8192 bytes')
        rules=validate_rules(json.loads(path.read_text(encoding='utf-8')))
        print('Regras válidas. Ativo:',rules['enabled'])
        print('Fontes selecionadas:',', '.join(rules['change_sources']) or 'nenhuma')
        print('Sem alterações no router, base SQLite ou configurações em uso.')
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print('Configuração inválida:',exc,file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
