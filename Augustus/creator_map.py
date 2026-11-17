"""Use original local empire artwork; never include private preview caches in exports."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from creator_presets import local_inventory,empire_preset

def prepare(template=25):
    inventory=local_inventory()
    source=next((x for x in inventory['empires'] if x['id']==template),None)
    if source is None:
        failures=[t for t in inventory.get('terrains',[]) if t.get('error')]
        if failures:
            raise ValueError('제국지도 미리보기 생성에 실패했습니다: '+failures[0]['error']+' (creator-cache의 engine.log를 확인하세요.)')
        raise ValueError('이 제국지도의 원본 파일을 시저 3 폴더에서 찾지 못했습니다.')
    image=Path(source['image']);metadata=image.with_name('map.json');p=empire_preset(template)
    metadata.write_text(json.dumps(dict(width=p['width'],height=p['height'],cities=p['cities']),ensure_ascii=False),encoding='utf8')
    return dict(image=str(image),metadata=str(metadata),image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),metadata_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest())

if __name__=='__main__':
    try:print(json.dumps(prepare(int(sys.argv[1]) if len(sys.argv)>1 else 25)))
    except (ValueError,OSError,RuntimeError) as error:raise SystemExit(str(error))
