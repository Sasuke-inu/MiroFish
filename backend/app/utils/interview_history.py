"""Order interview records without treating simulation ticks as Unix time."""

from datetime import datetime, timezone
import json
from pathlib import Path


def _reply_key(reply):
    return (reply.get('platform'), reply.get('agent_id'), str(reply.get('timestamp')),
            json.dumps(reply.get('response'), ensure_ascii=False, sort_keys=True))


def _time_key(record):
    value = record.get('timestamp')
    if isinstance(value, str):
        try:
            instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=timezone.utc)
            return (1, instant.timestamp())
        except (ValueError, OverflowError):
            pass
    # Legacy platform clocks are relative simulation ticks, not epoch dates.
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, float('-inf'))


def order_interview_history(records, simulation_dir):
    """Prefer saved command completion times, retaining original platform time."""
    command_times = {}
    for path in (Path(simulation_dir) / 'ipc_responses').glob('*.json'):
        try:
            event = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(event, dict):
                continue
            result = event.get('result')
            if event.get('status') != 'completed' or not isinstance(result, dict):
                continue
            timestamp = event.get('timestamp')
            if _time_key({'timestamp': timestamp})[0] != 1:
                continue
            replies = result.get('results')
            replies = replies.values() if isinstance(replies, dict) else [result]
            for reply in replies:
                if isinstance(reply, dict) and isinstance(reply.get('response'), str):
                    key = _reply_key(reply)
                    previous = command_times.get(key)
                    if previous is None or _time_key({'timestamp': timestamp}) > _time_key({'timestamp': previous}):
                        command_times[key] = timestamp
        except (OSError, ValueError, TypeError):
            # A response being written, or an old malformed receipt, must not
            # prevent reading the interview answers already stored in SQLite.
            continue

    for record in records:
        timestamp = command_times.get(_reply_key(record))
        if timestamp is not None:
            record['simulation_timestamp'] = record['timestamp']
            record['timestamp'] = timestamp
            record['timestamp_source'] = 'interview_command'
        else:
            record['timestamp_source'] = 'simulation'
    return sorted(records, key=_time_key, reverse=True)
