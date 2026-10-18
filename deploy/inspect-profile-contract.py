"""Inspect a fictional profile response shape without printing credentials."""
import json
import sys

sys.path.insert(0, '/app/backend')
from app.services import oasis_profile_generator as profiles
from app.services.zep_entity_reader import ZepEntityReader
from app.utils.locale import set_locale

set_locale('zh-TW')
graph_id = sys.argv[1]
entities = ZepEntityReader().filter_defined_entities(graph_id).entities
entity = next(item for item in entities if item.name == '小橙')
original = profiles.create_chat_completion


def inspect(*args, **kwargs):
    response = original(*args, **kwargs)
    content = profiles.extract_chat_completion_text(response)
    value = json.loads(content)
    print(json.dumps({'top_keys': list(value), 'nested_keys': {
        key: list(item) for key, item in value.items() if isinstance(item, dict)},
        'response_characters': len(content)}, ensure_ascii=True), flush=True)
    return response


profiles.create_chat_completion = inspect
generator = profiles.OasisProfileGenerator(graph_id=graph_id)
result = generator.generate_profile_from_entity(entity, 0, use_llm=True)
print(json.dumps({'persona_characters': len(result.persona), 'bio_characters': len(result.bio)}, ensure_ascii=True))
