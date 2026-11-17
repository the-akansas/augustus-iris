"""Local display-name and successful-address history, shared by both room roles.

No invitation, token, room ID or password is stored here. Bad entries are ignored
on read; each successful update replaces the JSON atomically.
"""
import json
import os
import unicodedata
import uuid
from pathlib import Path

from connection_config import address

MAX_IPS = 50
MAX_NAMES = 100
MAX_FILE_BYTES = 128 * 1024


def player_name(value):
    if not isinstance(value, str):
        raise ValueError('아이디는 공백이 아닌 24자 이내로 입력해 주세요.')
    value = value.strip()
    if not value or len(value) > 24 or any(unicodedata.category(ch) in ('Cc', 'Cf', 'Cs') for ch in value):
        raise ValueError('아이디는 공백이 아닌 24자 이내로 입력해 주세요.')
    return value


def display_line(value):
    """A mailbox choice always occupies exactly one UTF-8 line."""
    return ' '.join(''.join(' ' if unicodedata.category(ch).startswith('C') else ch
                           for ch in str(value)).split())[:400]


class Preferences:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        result = dict(version=1, recent_ips=[], player_names=[])
        try:
            with self.path.open('rb') as source:
                raw = source.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                return result
            data = json.loads(raw.decode('utf-8-sig'))
        except (OSError, UnicodeError, ValueError):
            return result
        if not isinstance(data, dict) or data.get('version') != 1:
            return result
        for key, validate, limit in [('recent_ips', address, MAX_IPS),
                                      ('player_names', player_name, MAX_NAMES)]:
            values = data.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                try:
                    value = validate(value)
                except ValueError:
                    continue
                if value not in result[key]:
                    result[key].append(value)
                if len(result[key]) == limit:
                    break
        return result

    def update(self, key, value, forget=False):
        validate, limit = {'recent_ips': (address, MAX_IPS),
                           'player_names': (player_name, MAX_NAMES)}[key]
        value = validate(value)
        data = self.read()
        data[key] = [item for item in data[key] if item != value]
        if not forget:
            data[key].insert(0, value)
        data[key] = data[key][:limit]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('w', encoding='utf-8', newline='\n') as target:
                json.dump(data, target, ensure_ascii=False, indent=2)
                target.write('\n')
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return value
