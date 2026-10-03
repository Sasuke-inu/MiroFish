"""Normalize a compatible provider's JSON values without repairing content."""


def unwrap_properties(value, expected_fields):
    """Accept values wrapped in JSON-schema's properties object.

    Some compatible models echo the requested schema envelope around its
    values. Preserve an already matching object, including legitimate fields
    named properties. Callers still validate the resulting values normally.
    """
    if not isinstance(value, dict) or set(expected_fields).intersection(value):
        return value
    candidate = value.get('properties')
    schema_keys = {'properties', 'type', 'required', 'title', 'description', 'additionalProperties', '$schema'}
    if (set(value).issubset(schema_keys) and isinstance(candidate, dict)
            and set(expected_fields).intersection(candidate)):
        return candidate
    return value
