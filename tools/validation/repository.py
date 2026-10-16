"""Read-only Git candidate size, asset and secret audit; never prints secrets."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', 'build', 'dist', 'tmp', 'temp',
                 'cache', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.vscode', '.idea',
                 'work', 'release', 'vendor'}
SECRET_PATTERNS = [
    rb'\bBearer\s+[A-Za-z0-9_.~+/=-]{20,}',
    rb'\bsk[-_][A-Za-z0-9]{20,}',
    rb'\bgh[pousr]_[A-Za-z0-9]{20,}',
    rb'\bgithub_pat_[A-Za-z0-9_]{20,}',
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    rb'(?i)\b(?:ELEVENLABS_API_KEY|api_key|access_token|refresh_token|client_secret|password)\s*[=:]\s*[\x22\x27]?[A-Za-z0-9_+/.=-]{24,}',
    rb'(?i)https?://[^\s/:]+:[^\s/@]{8,}@',
]


def candidates(root=ROOT):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for name in names:
            if name == '.env' or name.startswith('.env.') and name != '.env.example':
                continue
            if name.endswith(('.pyc', '.pyo', '.log', '.partial')):
                continue
            yield Path(base) / name


def private_values(root):
    path = root / '.env'
    values = []
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            value = line.split('=', 1)[1].strip().strip('\"\'')
            if len(value) >= 8 and value != 'your_api_key_here':
                values.append(value.encode('utf-8'))
    return values


def audit(root=ROOT):
    root = Path(root)
    paths = set(candidates(root))
    # Also inspect tracked files even if a later ignore rule would hide them.
    if (root / '.git').exists():
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=True)
        paths.update(root / name.decode('utf-8') for name in tracked.stdout.split(b'\0') if name)
    files = sorted((p for p in paths if p.is_file()), key=lambda p: p.stat().st_size, reverse=True)
    values = private_values(root)
    findings = []
    assets = []
    personal_paths = []
    historical = []
    links = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        if re.search(rb'(?i)[a-z]:[\\/]+Users[\\/]+[^\\/\s]+', raw):
            personal_paths.append(rel)
        if path.name in {'cleanup-before.md', 'cleanup-after.md', 'repository-audit.json'} or re.fullmatch(r'batch[-_ ]?0[1-4].*\.(md|json)', path.name, re.I):
            historical.append(rel)
        if path.suffix.lower() == '.md':
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', raw.decode('utf-8')):
                target = target.split('#', 1)[0].strip('<>')
                if target and not re.match(r'[a-z]+:', target, re.I) and not (path.parent / target).exists():
                    links.append({'file': rel, 'target': target})
        if any(secret in raw for secret in values) or any(re.search(pattern, raw) for pattern in SECRET_PATTERNS):
            findings.append(rel)  # No matching bytes, values, lines or snippets are logged.
        if path.suffix.lower() in {'.pack', '.orig', '.bnk', '.wav', '.ogg', '.mp3', '.flac', '.exe', '.dll', '.zip', '.pyd'}:
            assets.append(rel)
        if path.suffix.lower() == '.wem' and not rel.startswith('replacements/'):
            assets.append(rel)
        if path.name == '.env' or path.name.startswith('.env.') and path.name != '.env.example':
            assets.append(rel)
    sizes = [(p.stat().st_size, p.relative_to(root).as_posix()) for p in files]
    return {'secret_scan': 'SECRET SCAN FAIL' if findings else 'SECRET SCAN PASS',
            'secret_finding_files': findings, 'prohibited_asset_files': assets,
            'personal_path_files': personal_paths, 'historical_report_files': historical, 'broken_markdown_links': links,
            'git_candidate_bytes': sum(size for size, _ in sizes), 'git_candidate_files': len(files),
            'largest_source_file': next(({'file': name, 'bytes': size} for size, name in sizes if name.endswith(('.py', '.ps1', '.spec'))), None),
            'largest_files': [{'file': name, 'bytes': size} for size, name in sizes[:20]],
            'files_over_50_mib': [name for size, name in sizes if size > 50 * 1024**2],
            'files_over_100_mib': [name for size, name in sizes if size > 100 * 1024**2]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = audit()
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(bool(report['secret_finding_files'] or report['prohibited_asset_files'] or report['files_over_100_mib']
                          or report['personal_path_files'] or report['historical_report_files'] or report['broken_markdown_links']))
