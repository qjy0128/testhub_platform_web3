from urllib.parse import parse_qsl, urlparse

from .models import ApiCollection, ApiRequest


def _header_list_to_dict(headers):
    result = {}
    for header in headers or []:
        name = header.get('name') or header.get('key')
        if name:
            result[name] = header.get('value', '')
    return result


def _query_list_to_dict(query_items):
    result = {}
    for item in query_items or []:
        key = item.get('key') or item.get('name')
        if key:
            result[key] = item.get('value', '')
    return result


def _normalize_body(mode, body):
    if not body:
        return {}
    if mode == 'raw':
        raw = body.get('raw', '')
        return {'type': 'raw', 'data': raw}
    if mode in {'urlencoded', 'formdata'}:
        return {
            'type': 'x-www-form-urlencoded' if mode == 'urlencoded' else 'form-data',
            'data': [
                {'key': item.get('key'), 'value': item.get('value', ''), 'enabled': not item.get('disabled', False)}
                for item in body.get(mode, [])
                if item.get('key')
            ],
        }
    return {}


def import_postman_collection(project, payload, user):
    root = ApiCollection.objects.create(
        project=project,
        name=payload.get('info', {}).get('name') or 'Postman Import',
        description=payload.get('info', {}).get('description') or '',
    )
    created = {'collections': 1, 'requests': 0}

    def walk_items(items, parent, order_prefix=''):
        for index, item in enumerate(items or []):
            item_order = index + 1
            if 'item' in item:
                collection = ApiCollection.objects.create(
                    project=project,
                    parent=parent,
                    name=item.get('name') or 'Folder',
                    description=item.get('description') or '',
                    order=item_order,
                )
                created['collections'] += 1
                walk_items(item.get('item') or [], collection, f'{order_prefix}{item_order}.')
                continue

            request_data = item.get('request') or {}
            url_data = request_data.get('url') or {}
            if isinstance(url_data, str):
                raw_url = url_data
                parsed = urlparse(raw_url)
                params = dict(parse_qsl(parsed.query))
            else:
                raw_url = url_data.get('raw') or ''
                params = _query_list_to_dict(url_data.get('query'))

            body = request_data.get('body') or {}
            ApiRequest.objects.create(
                collection=parent,
                name=item.get('name') or request_data.get('name') or raw_url or 'Imported Request',
                description=item.get('description') or request_data.get('description') or '',
                method=str(request_data.get('method') or 'GET').upper(),
                url=raw_url,
                headers=_header_list_to_dict(request_data.get('header')),
                params=params,
                body=_normalize_body(body.get('mode'), body),
                created_by=user,
                order=item_order,
            )
            created['requests'] += 1

    walk_items(payload.get('item') or [], root)
    return created


def import_har(project, payload, user):
    collection = ApiCollection.objects.create(project=project, name='HAR Import')
    created = 0
    for index, entry in enumerate(payload.get('log', {}).get('entries') or [], start=1):
        request_data = entry.get('request') or {}
        url = request_data.get('url') or ''
        parsed = urlparse(url)
        params = _query_list_to_dict(request_data.get('queryString')) or dict(parse_qsl(parsed.query))
        post_data = request_data.get('postData') or {}
        body = {}
        if post_data.get('text'):
            body = {'type': 'raw', 'data': post_data.get('text')}
        elif post_data.get('params'):
            body = {
                'type': 'form-data',
                'data': [
                    {'key': item.get('name'), 'value': item.get('value', ''), 'enabled': True}
                    for item in post_data.get('params', [])
                    if item.get('name')
                ],
            }

        ApiRequest.objects.create(
            collection=collection,
            name=f"{request_data.get('method', 'GET')} {parsed.path or url}",
            method=str(request_data.get('method') or 'GET').upper(),
            url=url,
            headers=_header_list_to_dict(request_data.get('headers')),
            params=params,
            body=body,
            created_by=user,
            order=index,
        )
        created += 1
    return {'collections': 1, 'requests': created}


def export_openapi(project):
    paths = {}
    requests = ApiRequest.objects.filter(collection__project=project).select_related('collection').order_by('collection__order', 'order', 'id')
    for api_request in requests:
        parsed = urlparse(api_request.url)
        path = parsed.path or api_request.url or '/'
        method = str(api_request.method or 'GET').lower()
        paths.setdefault(path, {})[method] = {
            'summary': api_request.name,
            'description': api_request.description,
            'tags': [api_request.collection.name] if api_request.collection else [],
            'parameters': [
                {
                    'name': key,
                    'in': 'query',
                    'required': False,
                    'schema': {'type': 'string'},
                    'example': value,
                }
                for key, value in (api_request.params or {}).items()
            ],
            'responses': {
                '200': {'description': 'Successful response'}
            },
            'x-testhub-request-id': api_request.id,
            'x-testhub-extractors': api_request.extractors or [],
        }
        if method in {'post', 'put', 'patch'} and api_request.body:
            paths[path][method]['requestBody'] = {
                'content': {
                    'application/json': {
                        'schema': {'type': 'object'},
                        'example': api_request.body.get('data') if isinstance(api_request.body, dict) else api_request.body,
                    }
                }
            }

    return {
        'openapi': '3.0.3',
        'info': {
            'title': project.name,
            'description': project.description,
            'version': '1.0.0',
        },
        'paths': paths,
    }
