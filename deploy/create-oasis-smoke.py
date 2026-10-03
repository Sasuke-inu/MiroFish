"""Prepare two fictional agents for one real OASIS round on both platforms."""
import csv
import json
import re
import sys
from pathlib import Path

name = sys.argv[1] if len(sys.argv) > 1 else 'installation-check'
if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
    raise ValueError('Use a short test name containing only lowercase letters, numbers and hyphens.')
target = Path(__file__).resolve().parents[1] / 'backend/uploads' / name
target.mkdir(parents=True, exist_ok=True)
profiles = [
    {'name': 'Orange Test', 'username': 'orange_test', 'persona': 'You are a fictional cafe owner testing software. Write one short friendly invitation to a board game event. Use Traditional Chinese.', 'bio': 'Fictional cafe owner', 'mbti': 'ENFJ', 'age': 30, 'gender': 'other', 'country': 'Fictional'},
    {'name': 'Blue Test', 'username': 'blue_test', 'persona': 'You are a fictional neighbor testing software. Write one short response about keeping the board game event quiet. Use Traditional Chinese.', 'bio': 'Fictional neighbor', 'mbti': 'ISFJ', 'age': 30, 'gender': 'other', 'country': 'Fictional'},
]
with (target / 'twitter_profiles.csv').open('w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['user_id', 'name', 'username', 'user_char', 'description'])
    for index, profile in enumerate(profiles):
        writer.writerow([index, profile['name'], profile['username'], profile['persona'], profile['bio']])
(target / 'reddit_profiles.json').write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding='utf-8')
config = {
    'simulation_id': name,
    'time_config': {'total_simulation_hours': 1, 'minutes_per_round': 60, 'agents_per_hour_min': 2, 'agents_per_hour_max': 2, 'peak_hours': [], 'off_peak_hours': []},
    'agent_configs': [{'agent_id': i, 'entity_name': p['name'], 'active_hours': list(range(24)), 'activity_level': 1.0} for i, p in enumerate(profiles)],
    'event_config': {'initial_posts': [{'poster_agent_id': 0, 'content': '完全虛構的軟體測試：咖啡店週六舉辦免費桌遊活動，最多八人，晚上六點結束。'}]},
}
(target / 'simulation_config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Prepared {name} with 2 fictional agents and 1 round.')
