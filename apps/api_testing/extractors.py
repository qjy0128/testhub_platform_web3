import json


def _response_json(response):
    try:
        return response.json()
    except Exception:
        try:
            return json.loads(getattr(response, 'text', '') or '{}')
        except Exception:
            return {}


def _extract_jsonpath(payload, expression):
    try:
        from jsonpath_ng import parse
    except Exception:
        return None
    try:
        matches = parse(expression).find(payload)
    except Exception:
        return None
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].value
    return [match.value for match in matches]


def extract_response_variables(response, extractors):
    values = {}
    details = []
    payload = None
    for extractor in extractors or []:
        if not isinstance(extractor, dict) or extractor.get('enabled') is False:
            continue
        name = extractor.get('name') or extractor.get('variable') or extractor.get('key')
        expression = extractor.get('expression') or extractor.get('jsonpath') or extractor.get('path')
        extractor_type = str(extractor.get('type') or 'jsonpath').lower()
        if not name or not expression:
            continue

        value = None
        if extractor_type == 'jsonpath':
            if payload is None:
                payload = _response_json(response)
            value = _extract_jsonpath(payload, expression)
        elif extractor_type == 'header':
            value = response.headers.get(expression)

        values[name] = value
        details.append({
            'name': name,
            'type': extractor_type,
            'expression': expression,
            'value': value,
            'matched': value is not None,
        })
    return values, details
