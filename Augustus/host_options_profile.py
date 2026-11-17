"""Local host defaults, separate from personal settings and saved-room rules."""
import json
import os
import uuid
from pathlib import Path
import room_options


def load(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        if len(raw) > 32768:
            raise ValueError('oversized')
        data = json.loads(raw)
        keys = [row['key'] for row in room_options.SCHEMA]
        # Profiles saved before newer rules: fill the missing trailing rules with defaults.
        if isinstance(data,dict) and type(data.get('version')) is int and data['version']==1 and isinstance(data.get('options'),dict):
            for count in (41,42):
                if set(data['options'])==set(keys[:count]):
                    data=dict(data,options=dict(data['options'],**{row['key']:row['default'] for row in room_options.SCHEMA[count:]}))
                    break
        if (set(data) != {'version', 'options'} or type(data['version']) != int
                or data['version'] != 1 or not isinstance(data['options'], dict)
                or set(data['options']) != set(keys)):
            raise ValueError('schema')
        return room_options.values([data['options'][key] for key in keys])
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        raise ValueError('저장된 방장 설정 파일이 손상되었습니다: ' + str(path)) from error


def save(path, values):
    checked = room_options.values(values)
    data = dict(version=1, options={row['key']: v for row, v in zip(room_options.SCHEMA, checked)})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf8', newline='') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
