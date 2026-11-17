"""Scenario workspace, recent projects and data-only sharing. No GUI or game launch."""
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from scenario_project import load

HERE = Path(__file__).resolve().parent
# Scenarios taken off the list (user 2026-11-15: what can be put in must come out again) are moved here, inside the
# workspace, never deleted: the author can bring one back by moving the file.
DELETED = 'deleted-scenarios'


class Workspace:
    def __init__(self, root=HERE):
        self.root = Path(root).resolve()
        self.settings = self.root / 'creator-workspace.json'

    def read(self):
        default = dict(directory=str(self.root / 'creator-projects'), recent=[])
        try:
            if self.settings.stat().st_size > 128 * 1024:
                return default
            data = json.loads(self.settings.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict):
                return default
            directory = data.get('directory')
            if isinstance(directory, str) and Path(directory).is_absolute():
                default['directory'] = directory
            recent = data.get('recent', [])
            if isinstance(recent, list):
                default['recent'] = list(dict.fromkeys(p for p in recent if isinstance(p, str) and Path(p).is_absolute()))[:100]
        except (OSError, ValueError):
            pass
        return default

    def write(self, data):
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.settings.with_name(self.settings.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, self.settings)
        finally:
            tmp.unlink(missing_ok=True)

    def directory(self):
        path = Path(self.read()['directory'])
        path.mkdir(parents=True, exist_ok=True)
        return path

    def set_directory(self, path):
        path = Path(path).resolve()
        # Installation metadata and temporary runtime files are not project folders.
        if path.parent == path or path == self.root or path.is_relative_to(self.root / 'creator-cache') or path.is_relative_to(self.root / 'rooms') or path.is_relative_to(self.root / 'scenarios'):
            raise ValueError('설치 폴더나 기본 예제 대신 시나리오 작업 전용 폴더를 선택하세요.')
        path.mkdir(parents=True, exist_ok=True)
        data = self.read()
        data['directory'] = str(path)
        self.write(data)
        return self.catalog()

    def remember(self, path):
        path = Path(path).resolve()
        load(path)
        data = self.read()
        data['recent'] = [str(path)] + [p for p in data['recent'] if os.path.normcase(p) != os.path.normcase(str(path))]
        data['recent'] = data['recent'][:100]
        self.write(data)

    def catalog(self):
        folder = self.directory()
        data = self.read()
        known = {os.path.normcase(p) for p in data['recent']}
        paths = [Path(p) for p in data['recent']]
        paths += [p for p in folder.rglob('*.json') if not re.fullmatch('[0-9a-f]{32}', p.stem) or os.path.normcase(str(p.resolve())) in known]
        rows, seen = [], set()
        for path in paths:
            if path.resolve().is_relative_to(self.root/'scenarios') or path.resolve().is_relative_to(folder.resolve()/DELETED):
                continue
            key = os.path.normcase(str(path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            try:
                scenario = load(path)
                stamp = path.stat().st_mtime
                rows.append(dict(path=str(path.resolve()), title=scenario['title'], players=len(scenario['slots']),
                                 modified=datetime.fromtimestamp(stamp).strftime('%Y-%m-%d %H:%M'), stamp=stamp,
                                 recent=key in known))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        rows.sort(key=lambda row: row['stamp'], reverse=True)
        examples=[]
        try:bundled=[self.root/'scenarios'/str(n)/'scenario.json' for n in json.loads((self.root/'default-scenarios.json').read_text(encoding='utf-8-sig'))['scenarios']]   # the same list the lobby shows
        except (OSError,ValueError,KeyError,TypeError):bundled=sorted((self.root/'scenarios').rglob('scenario.json'))+sorted((self.root/'scenarios').glob('*.json'))
        for path in bundled:
            try:
                scenario=load(path)
                examples.append(dict(path=str(path.resolve()),title=scenario['title'],players=len(scenario['slots']),modified='기본 제공',recent=False))
            except (OSError,ValueError,KeyError,TypeError):continue
        return dict(directory=str(folder), entries=rows, examples=examples)

    def forget(self, path):
        """The recent list without this file (the file itself is not touched)."""
        key = os.path.normcase(str(Path(path).resolve()))
        data = self.read()
        data['recent'] = [p for p in data['recent'] if os.path.normcase(str(Path(p).resolve())) != key]
        self.write(data)
        return dict(forgotten=True)

    def discard(self, path):
        """Off the list: a scenario in the workspace folder is moved to deleted-scenarios with its .bak copies; a file
        elsewhere (opened from another folder) only leaves the recent list. Bundled scenarios stay."""
        path = Path(path).resolve()
        if path.is_relative_to(self.root / 'scenarios'):
            raise ValueError('기본 제공 시나리오는 목록에서 지울 수 없습니다.')
        folder = self.directory().resolve()
        moved = None
        if path.is_file() and path.is_relative_to(folder) and not path.is_relative_to(folder / DELETED):
            target = folder / DELETED / time.strftime('%Y%m%d-%H%M%S')
            target.mkdir(parents=True, exist_ok=True)
            for item in [path] + sorted(path.parent.glob(glob_escape(path.name) + '.*.bak')):
                destination = target / item.name
                n = 1
                while destination.exists():
                    destination = target / (item.stem + '-' + str(n) + item.suffix)
                    n += 1
                shutil.move(str(item), str(destination))
            moved = str(target / path.name)
        self.forget(path)
        return dict(moved=moved)

    def tidy(self):
        """Old files the editor made for itself (previews, checks, editor copies nobody saved into). Never the author's
        projects, shelf, or an editor copy with a saved map in it."""
        cache = self.root / 'creator-cache'
        now = time.time()
        removed = 0

        def old(p, days):
            try:
                return now - p.stat().st_mtime > days * 86400
            except OSError:
                return False

        def drop(p):
            nonlocal removed
            try:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                removed += 1
            except OSError:
                pass

        if not cache.is_dir():
            return dict(removed=0)
        for p in cache.glob('validation-*'):
            if old(p, 2):
                drop(p)
        # The terrain/empire catalogue (export_preset_inventory.py) is made again whenever the game files or the engine
        # change; the folders it no longer points to (each a few hundred MB) go after a day (user 2026-11-16). One a
        # running editor has a file open in cannot be renamed and is left for next time.
        try:
            current = Path(json.loads((cache / 'presets-current.json').read_text(encoding='utf8'))['metadata']).resolve().parent
        except (OSError, ValueError, KeyError, TypeError):
            current = None
        if current is not None:
            for p in cache.glob('presets-*'):
                if p.is_dir() and p.resolve() != current and old(p, 1):
                    gone = cache / ('removing-' + uuid.uuid4().hex)
                    try:
                        os.rename(p, gone)
                    except OSError:
                        continue
                    drop(gone)
        for p in cache.glob('removing-*'):
            drop(p)
        for p in cache.glob('presets-current.*.tmp'):
            if old(p, 1):
                drop(p)
        for p in (cache / 'snapshots').glob('*.json') if (cache / 'snapshots').is_dir() else []:
            if old(p, 1):
                drop(p)
        for p in (cache / 'native-preview').iterdir() if (cache / 'native-preview').is_dir() else []:
            if old(p, 14):
                drop(p)
        for p in (cache / 'native-editor').iterdir() if (cache / 'native-editor').is_dir() else []:
            if not old(p, 30):
                continue
            try:
                state = json.loads((p / 'session.json').read_text(encoding='utf8'))
                maps = [m for m in (p / 'user' / 'scenarios').iterdir()]
                untouched = len(maps) == 1 and maps[0].name == 'edit.mapx' and hashlib.sha256(maps[0].read_bytes()).hexdigest() == state.get('original_sha256')
            except (OSError, ValueError, AttributeError):
                untouched = False
            if untouched:
                drop(p)
        return dict(removed=removed)

    def import_zip(self, source):
        with zipfile.ZipFile(source) as z:
            if len(z.namelist()) != len(set(z.namelist())):
                raise ValueError('중복 파일이 있는 공유 ZIP입니다.')
            names = set(z.namelist())
            if not {'scenario.json', 'checksums.json'} <= names or names - {'scenario.json', 'checksums.json', 'README.txt'}:
                raise ValueError('제작기에서 만든 공유 ZIP을 선택하세요.')
            if z.getinfo('scenario.json').file_size > 16777216 or z.getinfo('checksums.json').file_size > 4096:
                raise ValueError('공유 시나리오 파일이 너무 큽니다.')
            raw = z.read('scenario.json')
            checks = json.loads(z.read('checksums.json').decode('utf-8-sig'))
            if not isinstance(checks, dict) or checks.get('scenario.json') != hashlib.sha256(raw).hexdigest():
                raise ValueError('공유 ZIP의 내용이 손상되었거나 변경되었습니다.')
        cache = self.root / 'creator-cache'
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temp:
            checked = Path(temp) / 'scenario.json'
            checked.write_bytes(raw)
            scenario = load(checked)
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', scenario['title']).strip(' .')[:60] or '시나리오'
        target = self.directory() / (name + '-' + uuid.uuid4().hex[:8] + '.json')
        with target.open('xb') as stream:
            stream.write(raw)
        self.remember(target)
        return dict(path=str(target), title=scenario['title'])


def glob_escape(name):
    return re.sub(r'([\[\]*?])', r'[\1]', name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['list', 'folder', 'remember', 'import', 'forget', 'discard', 'tidy'])
    parser.add_argument('path', nargs='?')
    args = parser.parse_args()
    workspace = Workspace()
    if args.operation == 'list':
        result = workspace.catalog()
    elif args.operation == 'tidy':
        result = workspace.tidy()
    else:
        if not args.path:
            parser.error('path required')
        if args.operation == 'folder':
            result = workspace.set_directory(args.path)
        elif args.operation == 'remember':
            workspace.remember(args.path)
            result = dict(saved=True)
        elif args.operation == 'forget':
            result = workspace.forget(args.path)
        elif args.operation == 'discard':
            result = workspace.discard(args.path)
        else:
            result = workspace.import_zip(args.path)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
