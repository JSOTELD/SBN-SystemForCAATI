"""Offline repository navigation. Python standard library; never imports application code."""
import argparse
import ast
from collections import defaultdict, deque
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
VERSION = 1
SKIP = {'.git', 'node_modules', 'vendor', 'dist', 'build', 'target', 'coverage',
        '.cache', '.next', '.nuxt', 'bin', 'obj', 'logs', '__pycache__', '.pytest_cache',
        '.venv', '.venv-local', 'outputs', '.codex-context', 'tooling', 'private_uploads'}
EXT = {'.py', '.js', '.cjs', '.html', '.css', '.sql', '.md', '.json', '.yaml', '.yml', '.sh', '.cmd', '.txt'}


def dump(path, value):
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True) + '\n'
    if not path.exists() or path.read_text(encoding='utf-8') != data:
        temp = path.with_suffix('.tmp')
        temp.write_text(data, encoding='utf-8')
        temp.replace(path)


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def inventory(root):
    """Prune excluded directories before reading source; honor nested ignore rules."""
    def walk(folder, inherited):
        rules = list(inherited)
        ignore = folder / '.gitignore'
        if ignore.exists():
            base = folder.relative_to(root).as_posix()
            for line in ignore.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    rules.append((base, line))
        for p in sorted(folder.iterdir()):
            if p.is_symlink() or p.name in SKIP or p.name.startswith('.env'):
                continue
            rel = p.relative_to(root).as_posix()
            ignored = False
            for base, pattern in rules:
                local = rel if base == '.' else rel.removeprefix(base + '/')
                if base != '.' and not rel.startswith(base + '/'):
                    continue
                negate = pattern.startswith('!')
                pattern = pattern.lstrip('!')
                directory = pattern.endswith('/')
                pattern = pattern.rstrip('/')
                anchored = pattern.startswith('/')
                pattern = pattern.lstrip('/')
                matched = fnmatch.fnmatchcase(local, pattern) if '/' in pattern or anchored else fnmatch.fnmatchcase(p.name, pattern)
                if pattern.startswith('**/'):
                    matched |= fnmatch.fnmatchcase(local, pattern[3:])
                if matched and (not directory or p.is_dir()):
                    ignored = not negate
            if ignored:
                continue
            if p.is_dir():
                yield from walk(p, rules)
            elif p.suffix in EXT and not p.name.endswith(('.min.js', '.min.css')) and 'lock' not in p.name and p.stat().st_size < 2_000_000:
                yield p
    yield from walk(root, [])


def module(path):
    if '/routes/' in path or '/services/' in path:
        return Path(path).stem
    return path.split('/')[0]


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted(node.value) + '.' + node.attr
    return ''


def literal(node, default=None):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return default


def parse(path, text):
    result = dict(module=module(path), type=Path(path).suffix.lstrip('.'), symbols=[], imports={}, routes=[], tables=[], references=[], prefixes={})
    if path.endswith('.py'):
        tree = ast.parse(text, filename=path)
        package = path[:-3].split('/')
        if package[-1] == '__init__':
            package.pop()
        else:
            package = package[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                source = '.'.join(prefix + ([node.module] if node.module else []))
                for name in node.names:
                    result['imports'][name.asname or name.name] = source + '.' + name.name
            elif isinstance(node, ast.Import):
                for name in node.names:
                    result['imports'][name.asname or name.name.split('.')[0]] = name.name
            if isinstance(node, ast.Call) and dotted(node.func).endswith('register_blueprint'):
                prefix = next((literal(k.value) for k in node.keywords if k.arg == 'url_prefix'), '')
                if node.args and isinstance(prefix, str):
                    # This project's registration loop enumerates the blueprint tuple.
                    for loop in ast.walk(tree):
                        if isinstance(loop, ast.For) and isinstance(loop.iter, (ast.Tuple, ast.List)) and dotted(loop.target) == dotted(node.args[0]):
                            for bp in loop.iter.elts:
                                result['prefixes'][dotted(bp)] = prefix
                    result['prefixes'][dotted(node.args[0])] = prefix

        def visit(node, parent=''):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = (parent + '.' if parent else '') + child.name
                    refs = sorted({dotted(n) for n in ast.walk(child) if isinstance(n, (ast.Name, ast.Attribute))} - {''})
                    kind = 'class' if isinstance(child, ast.ClassDef) else ('method' if parent else 'function')
                    result['symbols'].append(dict(name=name, type=kind, line=child.lineno, end=child.end_lineno, refs=refs))
                    if isinstance(child, ast.ClassDef):
                        table = dict(model=name, primary_keys=[], foreign_keys={}, relationships={}, columns=[], migrations=[])
                        for stmt in child.body:
                            if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__tablename__' for t in stmt.targets):
                                table['table'] = literal(stmt.value)
                            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                                target = stmt.target if isinstance(stmt, ast.AnnAssign) else stmt.targets[0]
                                value = stmt.value
                                if isinstance(value, ast.Call):
                                    field = dotted(target)
                                    if dotted(value.func).endswith('mapped_column'):
                                        table['columns'].append(field)
                                        if any(k.arg == 'primary_key' and literal(k.value) is True for k in value.keywords):
                                            table['primary_keys'].append(field)
                                        for call in ast.walk(value):
                                            if isinstance(call, ast.Call) and dotted(call.func).endswith('ForeignKey') and call.args:
                                                table['foreign_keys'][field] = literal(call.args[0])
                                    elif dotted(value.func).endswith('relationship') and value.args:
                                        table['relationships'][field] = literal(value.args[0])
                        if table.get('table'):
                            result['tables'].append(table)
                    for dec in child.decorator_list:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.args:
                            verb = dec.func.attr
                            route = literal(dec.args[0])
                            if verb in {'get', 'post', 'put', 'patch', 'delete', 'route'} and isinstance(route, str):
                                methods = next((literal(k.value) for k in dec.keywords if k.arg == 'methods'), ['GET'] if verb == 'route' else [verb.upper()])
                                result['routes'].append(dict(path=route, methods=methods, handler=name, blueprint=dotted(dec.func.value), line=dec.lineno))
                    visit(child, name)
                else:
                    visit(child, parent)
        visit(tree)
    elif path.endswith(('.js', '.cjs')):
        pattern = r'\b(?:async\s+)?function\s+(\w+)\s*\(|\bclass\s+(\w+)|\b(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^\n]*?\)|\w+)\s*=>'
        for match in re.finditer(pattern, text):
            result['symbols'].append(dict(name=next(x for x in match.groups() if x), type='class' if match.group(2) else 'function', line=text.count('\n', 0, match.start()) + 1, refs=[]))
        result['references'] = sorted(set(re.findall(r'\b([A-Za-z_$][\w$]*)\s*\(', text)))
        result['api_paths'] = sorted(set(re.findall(r'''(?:api|fetch)\s*\(\s*['"`]([^'"`]+)''', text)))
    elif path.endswith('.html'):
        result['scripts'] = re.findall(r'<script[^>]+src=["\']([^"\']+)', text)
    return result


def build(root=ROOT, rebuild=False):
    out = root / '.codex-context'
    out.mkdir(exist_ok=True)
    old = read(out / 'cache.json', {})
    fingerprint = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if old.get('parser') != fingerprint:
        rebuild = True
    previous = old.get('files', {})
    cache = {}
    parsed = []
    for p in inventory(root):
        key = p.relative_to(root).as_posix()
        stat = p.stat()
        stamp = [stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns]
        record = previous.get(key, {})
        if not rebuild and record.get('stamp') == stamp:
            cache[key] = record
            continue
        raw = p.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if not rebuild and record.get('hash') == digest:
            cache[key] = dict(record, stamp=stamp)
            continue
        metadata = parse(key, raw.decode('utf-8-sig'))
        cache[key] = dict(stamp=stamp, hash=digest, data=metadata)
        parsed.append(key)
    symbols, files, graph, modules, tables, routes = {}, {}, {}, defaultdict(list), {}, []
    names = defaultdict(list)
    qualified = {}
    for path, record in cache.items():
        data = record['data']
        for s in data['symbols']:
            sid = path + ':' + s['name']
            symbols[sid] = {k: v for k, v in s.items() if k != 'refs'} | dict(file=path, module=data['module'], uses=[])
            names[s['name']].append(sid)
            qualified[path.removesuffix('.py').replace('/', '.').removesuffix('.__init__') + '.' + s['name']] = sid

    def resolve(path, ref):
        local = path + ':' + ref
        if local in symbols:
            return local
        data = cache[path]['data']
        head, _, rest = ref.partition('.')
        imported = data['imports'].get(head)
        if imported:
            return qualified.get(imported + ('.' + rest if rest else '')) or qualified.get(imported)
        if path.endswith(('.js', '.cjs')):
            candidates = [sid for sid in names.get(ref, []) if symbols[sid]['file'].startswith('frontend/')]
            if len(candidates) == 1:
                return candidates[0]
        return None

    prefixes = {k: v for r in cache.values() for k, v in r['data']['prefixes'].items()}
    for path, record in cache.items():
        data = record['data']
        deps = set()
        for s in data['symbols']:
            sid = path + ':' + s['name']
            uses = sorted({target for ref in s['refs'] if (target := resolve(path, ref)) and target != sid})
            symbols[sid]['uses'] = uses
            graph[sid] = uses
            deps.update(symbols[t]['file'] for t in uses)
        for ref in data['imports'].values():
            parts = ref.split('.')
            while parts:
                candidate = '/'.join(parts)
                found = next((x for x in (candidate + '.py', candidate + '/__init__.py') if x in cache), None)
                if found:
                    deps.add(found)
                    break
                parts.pop()
        for ref in data.get('references', []):
            if target := resolve(path, ref):
                deps.add(symbols[target]['file'])
        for script in data.get('scripts', []):
            target = (Path(path).parent / script.split('?')[0]).as_posix()
            if target in cache:
                deps.add(target)
        deps.discard(path)
        graph[path] = sorted(deps)
        files[path] = dict(module=data['module'], type=data['type'], symbols=[s['name'] for s in data['symbols']], depends_on=sorted(deps))
        modules[data['module']].append(path)
        for table in data['tables']:
            tables[table['table']] = table | dict(file=path, symbol=path + ':' + table['model'])
        for route in data['routes']:
            sid = path + ':' + route['handler']
            routes.append(route | dict(path=prefixes.get(route['blueprint'], '') + route['path'], handler=sid, file=path, uses=graph[sid]))
    for path, record in cache.items():
        for api in record['data'].get('api_paths', []):
            api = '/api' + api if not api.startswith('/api') else api
            static = re.split(r'\$\{|\?', api)[0].rstrip('/')
            for route in routes:
                route_static = route['path'].split('<')[0].rstrip('/')
                if static and static == route_static:
                    graph[path] = sorted(set(graph[path] + [route['file']]))
                    files[path]['depends_on'] = graph[path]
    for table in tables.values():
        table['used_by'] = sorted(sid for sid, s in symbols.items() if table['symbol'] in s['uses'])
    outputs = {'files-index.json': files, 'symbols-index.json': symbols, 'dependency-graph.json': graph,
               'modules.json': dict(modules), 'routes.json': routes,
               'database-map.json': dict(engine='MySQL/MariaDB; SQLite en pruebas', tables=tables,
                   migrations={'files': [p for p in files if '/migrations/' in p], 'schema_helpers': [p for p in files if p.endswith('services/schema.py')], 'sql': [p for p in files if p.endswith('.sql')]})}
    for name, value in outputs.items():
        dump(out / name, value)
    removed = sorted(set(previous) - set(cache))
    dump(out / 'cache.json', dict(parser=fingerprint, files=cache))
    dump(out / 'context-version.json', dict(schema=VERSION, parser=fingerprint, files=len(files), symbols=len(symbols), routes=len(routes), parsed=parsed, removed=removed, mode='rebuild' if rebuild else 'incremental'))
    return dict(files=len(files), symbols=len(symbols), routes=len(routes), parsed=parsed, removed=removed)


def words(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return re.findall(r'[a-z0-9]+', unicodedata.normalize('NFKD', text.lower()).encode('ascii', 'ignore').decode())


ALIASES = {'activo': 'asset assets sbn', 'activos': 'asset assets', 'registrar': 'create register apply payload',
           'registro': 'create register', 'codigo': 'sbn barcode code', 'barras': 'barcode sbn',
           'inventario': 'inventory', 'jornada': 'session inventory', 'autenticacion': 'auth login security',
           'usuarios': 'user admin', 'censo': 'census sample', 'investigacion': 'research study',
           'simulacion': 'simulation', 'permisos': 'security roles', 'guia': 'observation simulation'}


def query(root, text, limit):
    out = root / '.codex-context'
    symbols = read(out / 'symbols-index.json', {})
    files = read(out / 'files-index.json', {})
    routes = read(out / 'routes.json', [])
    groups = [set(words(w + ' ' + ALIASES.get(w, ''))) for w in words(text)]
    ranked = []
    for sid, s in symbols.items():
        name = set(words(s['name']))
        context = set(words(s['file'] + ' ' + ' '.join(s['uses'])))
        score = sum(5 * bool(g & name) + bool(g & context) for g in groups)
        if s['file'].startswith('backend/app/'):
            score += 2 if score else 0
        if any(g & {'registro', 'registrar'} for g in groups) and name & {'create', 'apply'}:
            score += 8
        if score:
            ranked.append((score, sid, s))
    results = []
    for score, sid, s in sorted(ranked, key=lambda x: (-x[0], x[1]))[:limit]:
        results.append(dict(symbol=sid, line=s['line'], module=s['module'], uses=s['uses'][:6],
                            routes=[r['methods'][0] + ' ' + r['path'] for r in routes if r['handler'] == sid][:4]))
    matched = sorted({s['file'] for _, _, s in sorted(ranked, key=lambda x: (-x[0], x[1]))[:limit]})
    if not results:
        matched = [p for p in files if any(g & set(words(p)) for g in groups)][:limit]
    return dict(query=text, results=results, files=matched, total_matches=len(ranked), limit=limit)


def impact(root, target, depth, limit):
    out = root / '.codex-context'
    graph = read(out / 'dependency-graph.json', {})
    roots = [key for key in graph if key == target or key.split(':')[-1] == target]
    if not roots:
        return dict(error='Símbolo/archivo no encontrado; use query o el identificador file:symbol.')
    reverse = defaultdict(list)
    for source, deps in graph.items():
        for dep in deps:
            reverse[dep].append(source)
    found, edges = set(roots), []
    queue = deque((key, 0) for key in roots[:limit])
    while queue and len(edges) < limit:
        key, level = queue.popleft()
        if level >= depth:
            continue
        for relation, neighbors in [('uses', graph.get(key, [])), ('used_by', reverse[key])]:
            for neighbor in neighbors:
                if len(edges) >= limit:
                    break
                edges.append(dict(source=key, relation=relation, target=neighbor, depth=level + 1))
                if neighbor not in found:
                    found.add(neighbor)
                    queue.append((neighbor, level + 1))
    routes = read(out / 'routes.json', [])
    return dict(roots=roots[:limit], depth=depth, edges=edges, potentially_affected_routes=[dict(path=r['path'], methods=r['methods']) for r in routes if r['handler'] in found or r['file'] in found][:limit], truncated=bool(queue) or len(edges) >= limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['query', 'symbol', 'impact', 'update', 'rebuild', 'status'])
    parser.add_argument('text', nargs='?', default='')
    parser.add_argument('--limit', type=int, default=6)
    parser.add_argument('--depth', type=int, default=2)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 100 or args.depth < 0 or args.depth > 10:
        parser.error('limit: 1..100; depth: 0..10')
    try:
        if args.command in {'update', 'rebuild'}:
            result = build(rebuild=args.command == 'rebuild')
        else:
            # Stat-only for unchanged files; updates only changed source, never executes it.
            build()
            if args.command == 'impact':
                result = impact(ROOT, args.text, args.depth, args.limit * 4)
            elif args.command == 'status':
                result = read(ROOT / '.codex-context/context-version.json', {})
            else:
                result = query(ROOT, args.text, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, SyntaxError) as error:
        print(f'Índice no actualizado: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
