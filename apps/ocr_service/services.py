import base64
import mimetypes
import os
import tempfile

import httpx
from django.db.models import Count
from django.utils import timezone

from apps.core.url_safety import validate_outbound_http_url

from .models import OcrBatch, OcrEngineConfig, OcrPage, OcrTask

IMAGE_EXTENSIONS = {'.bmp', '.gif', '.jpeg', '.jpg', '.png', '.tif', '.tiff', '.webp'}
PDF_EXTENSIONS = {'.pdf'}
SUPPORTED_UPLOAD_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS


def get_extension(filename):
    import os

    return os.path.splitext(filename or '')[1].lower()


def infer_source_type(filename, content_type=''):
    extension = get_extension(filename)
    if extension in PDF_EXTENSIONS or content_type == 'application/pdf':
        return OcrTask.SOURCE_PDF
    if extension in IMAGE_EXTENSIONS or str(content_type).startswith('image/'):
        return OcrTask.SOURCE_IMAGE
    return OcrTask.SOURCE_OTHER


def validate_upload_file(uploaded_file, max_size=20 * 1024 * 1024):
    extension = get_extension(uploaded_file.name)
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError('Unsupported OCR file type.')
    if uploaded_file.size > max_size:
        raise ValueError('OCR file is too large.')
    return extension


def resolve_credential(engine):
    credential_ref = (getattr(engine, 'credential_ref', '') or '').strip()
    if not credential_ref:
        return ''
    if credential_ref.lower().startswith('env:'):
        return os.environ.get(credential_ref.split(':', 1)[1], '')
    return os.environ.get(credential_ref, credential_ref)


def build_chat_completions_url(base_url):
    base_url = (base_url or '').strip()
    if not base_url:
        return ''
    base_url = validate_outbound_http_url(base_url, label='OCR engine base URL').rstrip('/')
    if base_url.endswith('/chat/completions'):
        return base_url
    if base_url.endswith('/v1') or base_url.endswith('/v4'):
        return f'{base_url}/chat/completions'
    return f'{base_url}/v1/chat/completions'


def _build_page_result(page_number, text, *, confidence=1.0, width=0, height=0, metadata=None):
    lines = [line.strip() for line in text.replace('\r\n', '\n').split('\n')]
    normalized_lines = [line for line in lines if line]
    blocks = [
        {
            'type': 'line',
            'text': line,
            'confidence': 1.0,
            'bbox': None,
        }
        for line in normalized_lines
    ]
    return {
        'page_number': page_number,
        'text': '\n'.join(normalized_lines),
        'line_count': len(normalized_lines),
        'char_count': len(text or ''),
        'confidence': confidence,
        'width': width or 0,
        'height': height or 0,
        'blocks': blocks,
        'tables': [],
        'metadata': metadata or {},
    }


def _build_text_result(text, pages=None):
    if pages is None:
        pages = [_build_page_result(1, text)]
    normalized_pages = [_normalize_page_result(page, index) for index, page in enumerate(pages, start=1)]
    normalized_text = '\n\n'.join(page.get('text', '') for page in normalized_pages if page.get('text', '')).strip()
    blocks = []
    for page in normalized_pages:
        blocks.extend(page.get('blocks') or [])
    return {
        'schema_version': '1.0',
        'text': normalized_text,
        'line_count': sum(int(page.get('line_count') or 0) for page in normalized_pages),
        'char_count': len(normalized_text),
        'blocks': blocks,
        'pages': normalized_pages,
        'tables': [],
    }


def _normalize_page_result(page, fallback_number):
    if not isinstance(page, dict):
        page = {'text': str(page or '')}
    page_number = int(page.get('page_number') or page.get('page') or fallback_number)
    text = str(page.get('text') or page.get('extracted_text') or page.get('content') or '').strip()
    blocks = page.get('blocks')
    if not isinstance(blocks, list):
        blocks = _build_page_result(page_number, text).get('blocks', [])
    return {
        'page_number': page_number,
        'text': text,
        'line_count': int(page.get('line_count') or len([line for line in text.splitlines() if line.strip()])),
        'char_count': int(page.get('char_count') or len(text)),
        'confidence': page.get('confidence'),
        'width': int(page.get('width') or 0),
        'height': int(page.get('height') or 0),
        'blocks': blocks,
        'tables': page.get('tables') if isinstance(page.get('tables'), list) else [],
        'metadata': page.get('metadata') if isinstance(page.get('metadata'), dict) else {},
    }


def _extract_text_from_pdf(file_path):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        from PyPDF2 import PdfFileReader as PdfReader

    page_results = []
    with open(file_path, 'rb') as handle:
        reader = PdfReader(handle)
        pages = getattr(reader, 'pages', [])
        for index, page in enumerate(pages, start=1):
            text = page.extract_text() or ''
            page_results.append(_build_page_result(index, text, metadata={'extractor': 'pypdf2'}))
    return _build_text_result('', pages=page_results)


def _render_pdf_pages_to_images(file_path):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError('Scanned PDF vision OCR requires PyMuPDF.') from exc

    temp_dir = tempfile.TemporaryDirectory()
    image_paths = []
    document = fitz.open(file_path)
    zoom = 2
    matrix = fitz.Matrix(zoom, zoom)
    for index, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image_path = os.path.join(temp_dir.name, f'page-{index}.png')
        pixmap.save(image_path)
        image_paths.append((index, image_path, pixmap.width, pixmap.height))
    document.close()
    return temp_dir, image_paths


def _extract_pdf_with_vision(engine, file_path):
    temp_dir, image_paths = _render_pdf_pages_to_images(file_path)
    try:
        pages = []
        for page_number, image_path, width, height in image_paths:
            text = _extract_text_with_openai_vision(engine, image_path, 'image/png')
            pages.append(_build_page_result(
                page_number,
                text,
                confidence=None,
                width=width,
                height=height,
                metadata={'extractor': 'vision'},
            ))
        return _build_text_result('', pages=pages)
    finally:
        temp_dir.cleanup()


def _extract_text_with_tesseract(file_path):
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('Tesseract OCR requires pytesseract and Pillow.') from exc

    with Image.open(file_path) as image:
        return pytesseract.image_to_string(image).strip()


def _extract_text_with_easyocr(file_path):
    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError('EasyOCR is not installed.') from exc

    reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    results = reader.readtext(file_path, detail=0, paragraph=True)
    return '\n'.join(results).strip()


def _extract_text_with_openai_vision(engine, file_path, mime_type=''):
    if not engine.base_url or not engine.model_name:
        raise RuntimeError('Vision OCR requires base_url and model_name.')

    api_key = resolve_credential(engine)
    if not api_key:
        raise RuntimeError('Vision OCR requires credential_ref or matching environment variable.')

    mime_type = mime_type or mimetypes.guess_type(file_path)[0] or 'image/png'
    with open(file_path, 'rb') as handle:
        encoded = base64.b64encode(handle.read()).decode('ascii')

    prompt = (engine.options or {}).get(
        'prompt',
        'Extract all visible text from this image. Return plain text only.',
    )
    payload = {
        'model': engine.model_name,
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {
                        'type': 'image_url',
                        'image_url': {'url': f'data:{mime_type};base64,{encoded}'},
                    },
                ],
            },
        ],
        'temperature': float((engine.options or {}).get('temperature', 0)),
        'max_tokens': int((engine.options or {}).get('max_tokens', 2048)),
        'stream': False,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    timeout = float((engine.options or {}).get('timeout', 120))
    with httpx.Client(timeout=timeout) as client:
        response = client.post(build_chat_completions_url(engine.base_url), headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get('choices') or []
    if not choices:
        return ''
    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return '\n'.join(
            item.get('text', '')
            for item in content
            if isinstance(item, dict) and item.get('type') == 'text'
        ).strip()
    return ''


def _normalize_ocr_result(data):
    if isinstance(data, str):
        return _build_text_result(data)
    if not isinstance(data, dict):
        return _build_text_result('')

    result = data.get('result')
    if isinstance(result, dict):
        data = result

    pages = data.get('pages')
    if isinstance(pages, list):
        return _build_text_result(data.get('text') or data.get('extracted_text') or '', pages=pages)

    text = data.get('text') or data.get('extracted_text') or data.get('content') or ''
    return _build_text_result(str(text).strip())


def _extract_text_with_custom_http(engine, task):
    if not engine.base_url:
        raise RuntimeError('Custom OCR requires base_url.')

    endpoint = validate_outbound_http_url(engine.base_url, label='Custom OCR base URL')
    options = engine.options or {}
    headers = {}
    credential = resolve_credential(engine)
    if credential:
        header_name = options.get('auth_header', 'Authorization')
        header_value = options.get('auth_template', 'Bearer {token}').format(token=credential)
        headers[header_name] = header_value

    timeout = float(options.get('timeout', 120))
    field_name = options.get('file_field', 'file')
    with httpx.Client(timeout=timeout) as client:
        if task.input_file:
            with open(task.input_file.path, 'rb') as handle:
                files = {
                    field_name: (
                        task.original_filename or os.path.basename(task.input_file.name),
                        handle,
                        task.mime_type or 'application/octet-stream',
                    )
                }
                response = client.post(endpoint, headers=headers, data={'task_id': str(task.id)}, files=files)
        else:
            response = client.post(
                endpoint,
                headers=headers,
                json={
                    'task_id': task.id,
                    'input_url': task.input_url,
                    'input_text': task.input_text,
                    'source_type': task.source_type,
                },
            )
        response.raise_for_status()
        data = response.json()

    return _normalize_ocr_result(data)


def _extract_file_result(task):
    if not task.input_file:
        raise RuntimeError('No input file was uploaded.')

    file_path = task.input_file.path
    engine_type = getattr(task.engine, 'engine_type', '') if task.engine else OcrEngineConfig.ENGINE_EASYOCR
    if task.source_type == OcrTask.SOURCE_PDF:
        result = _extract_text_from_pdf(file_path)
        if result.get('text'):
            return result
        if engine_type == OcrEngineConfig.ENGINE_CUSTOM:
            if (task.engine.options or {}).get('mode') == 'openai_vision':
                return _extract_pdf_with_vision(task.engine, file_path)
            return _extract_text_with_custom_http(task.engine, task)
        if engine_type in {OcrEngineConfig.ENGINE_GPT4V, OcrEngineConfig.ENGINE_GLM4V}:
            return _extract_pdf_with_vision(task.engine, file_path)
        raise RuntimeError('No selectable text was found in this PDF. Use a custom OCR engine for scanned PDFs.')

    if engine_type == OcrEngineConfig.ENGINE_TESSERACT:
        return _build_text_result(_extract_text_with_tesseract(file_path))
    if engine_type == OcrEngineConfig.ENGINE_EASYOCR:
        return _build_text_result(_extract_text_with_easyocr(file_path))
    if engine_type in {OcrEngineConfig.ENGINE_GPT4V, OcrEngineConfig.ENGINE_GLM4V}:
        return _build_text_result(_extract_text_with_openai_vision(task.engine, file_path, task.mime_type))
    if engine_type == OcrEngineConfig.ENGINE_CUSTOM:
        mode = (task.engine.options or {}).get('mode', 'http')
        if mode == 'openai_vision':
            return _build_text_result(_extract_text_with_openai_vision(task.engine, file_path, task.mime_type))
        return _extract_text_with_custom_http(task.engine, task)

    return _build_text_result(_extract_text_with_easyocr(file_path))


def refresh_ocr_batch_status(batch):
    if batch is None:
        return None

    counts = {
        item['status']: item['count']
        for item in batch.tasks.values('status').annotate(count=Count('id'))
    }
    total = sum(counts.values())
    succeeded = counts.get(OcrTask.STATUS_SUCCEEDED, 0)
    failed = counts.get(OcrTask.STATUS_FAILED, 0)
    cancelled = counts.get(OcrTask.STATUS_CANCELLED, 0)
    running = counts.get(OcrTask.STATUS_RUNNING, 0)
    pending = counts.get(OcrTask.STATUS_PENDING, 0)

    if cancelled and cancelled == total:
        status_value = OcrBatch.STATUS_CANCELLED
    elif running or pending:
        status_value = OcrBatch.STATUS_RUNNING if running else OcrBatch.STATUS_PENDING
    elif failed and succeeded:
        status_value = OcrBatch.STATUS_PARTIAL
    elif failed:
        status_value = OcrBatch.STATUS_FAILED
    else:
        status_value = OcrBatch.STATUS_SUCCEEDED

    batch.total_tasks = total
    batch.succeeded_tasks = succeeded
    batch.failed_tasks = failed
    batch.cancelled_tasks = cancelled
    batch.status = status_value
    batch.save(update_fields=[
        'total_tasks',
        'succeeded_tasks',
        'failed_tasks',
        'cancelled_tasks',
        'status',
        'updated_at',
    ])
    return batch


def _mark_task_succeeded(task, result, confidence=None):
    task.extracted_text = result['text']
    task.result_json = result
    task.confidence = confidence
    task.status = OcrTask.STATUS_SUCCEEDED
    task.error_message = ''
    task.finished_at = timezone.now()
    task.save(update_fields=[
        'extracted_text',
        'result_json',
        'confidence',
        'status',
        'error_message',
        'finished_at',
        'updated_at',
    ])
    OcrPage.objects.filter(task=task).delete()
    OcrPage.objects.bulk_create([
        OcrPage(
            task=task,
            page_number=page.get('page_number') or index,
            text=page.get('text', ''),
            confidence=page.get('confidence'),
            width=page.get('width') or 0,
            height=page.get('height') or 0,
            result_json=page,
            metadata=page.get('metadata') if isinstance(page.get('metadata'), dict) else {},
        )
        for index, page in enumerate(result.get('pages') or [], start=1)
    ])
    refresh_ocr_batch_status(task.batch)
    return task


def _mark_task_failed(task, message):
    if task.attempt < max(1, task.max_attempts):
        task.status = OcrTask.STATUS_PENDING
        task.error_message = f'{message} Scheduled retry {task.attempt + 1}/{task.max_attempts}.'
        update_fields = ['status', 'error_message', 'updated_at']
    else:
        task.status = OcrTask.STATUS_FAILED
        task.error_message = message
        task.finished_at = timezone.now()
        update_fields = ['status', 'error_message', 'finished_at', 'updated_at']
    task.save(update_fields=update_fields)
    refresh_ocr_batch_status(task.batch)
    return task


def run_ocr_task(task):
    if task.status == OcrTask.STATUS_CANCELLED:
        return task

    task.status = OcrTask.STATUS_RUNNING
    task.error_message = ''
    task.started_at = timezone.now()
    task.finished_at = None
    task.attempt += 1
    task.save(update_fields=['status', 'error_message', 'started_at', 'finished_at', 'attempt', 'updated_at'])
    refresh_ocr_batch_status(task.batch)

    if task.source_type == OcrTask.SOURCE_TEXT:
        text = (task.input_text or '').strip()
        if not text:
            return _mark_task_failed(task, 'No input text was provided.')

        result = _build_text_result(text)
        return _mark_task_succeeded(task, result, confidence=1.0)

    if task.input_url and task.engine and task.engine.engine_type == OcrEngineConfig.ENGINE_CUSTOM:
        try:
            result = _extract_text_with_custom_http(task.engine, task)
        except Exception as exc:
            return _mark_task_failed(task, str(exc))

        if not result['text']:
            return _mark_task_failed(task, 'No text was extracted from the custom OCR response.')
        return _mark_task_succeeded(task, result, confidence=None)

    if task.input_file:
        try:
            result = _extract_file_result(task)
        except Exception as exc:
            return _mark_task_failed(task, str(exc))

        if not result.get('text'):
            return _mark_task_failed(task, 'No text was extracted from the uploaded file.')
        return _mark_task_succeeded(task, result, confidence=None if task.source_type == OcrTask.SOURCE_PDF else 0.9)

    return _mark_task_failed(task, 'OCR execution for image/PDF sources is not connected yet.')


def check_ocr_engine(engine):
    issues = []
    capabilities = []

    if engine.engine_type == OcrEngineConfig.ENGINE_TESSERACT:
        try:
            import pytesseract
            from PIL import Image  # noqa: F401

            capabilities.append('image')
            try:
                capabilities.append(f'tesseract:{pytesseract.get_tesseract_version()}')
            except Exception as exc:
                issues.append(f'Tesseract binary is not available: {exc}')
        except ImportError as exc:
            issues.append(f'Missing pytesseract or Pillow: {exc}')
    elif engine.engine_type == OcrEngineConfig.ENGINE_EASYOCR:
        try:
            import easyocr  # noqa: F401

            capabilities.extend(['image', 'ch_sim', 'en'])
        except ImportError as exc:
            issues.append(f'Missing EasyOCR: {exc}')
    elif engine.engine_type in {OcrEngineConfig.ENGINE_GPT4V, OcrEngineConfig.ENGINE_GLM4V}:
        capabilities.extend(['image', 'pdf_page_vision'])
        if not engine.base_url:
            issues.append('base_url is required.')
        else:
            try:
                build_chat_completions_url(engine.base_url)
            except ValueError as exc:
                issues.append(str(exc))
        if not engine.model_name:
            issues.append('model_name is required.')
        if not resolve_credential(engine):
            issues.append('credential_ref or matching environment variable is required.')
    elif engine.engine_type == OcrEngineConfig.ENGINE_CUSTOM:
        capabilities.extend(['image', 'pdf', 'url'])
        if not engine.base_url:
            issues.append('base_url is required.')
        else:
            try:
                validate_outbound_http_url(engine.base_url, label='Custom OCR base URL')
            except ValueError as exc:
                issues.append(str(exc))
    else:
        issues.append('Unsupported OCR engine type.')

    result = {
        'ready': not issues,
        'engine_type': engine.engine_type,
        'capabilities': capabilities,
        'issues': issues,
    }
    engine.last_checked_at = timezone.now()
    engine.last_check_result = result
    engine.save(update_fields=['last_checked_at', 'last_check_result', 'updated_at'])
    return result


def run_pending_ocr_tasks(limit=None, queryset=None):
    queryset = queryset or OcrTask.objects.all()
    queryset = queryset.filter(status=OcrTask.STATUS_PENDING).order_by('priority', 'created_at')
    if limit:
        queryset = queryset[:limit]

    succeeded = 0
    failed = 0
    pending_retry = 0
    for task in queryset:
        run_ocr_task(task)
        task.refresh_from_db()
        if task.status == OcrTask.STATUS_SUCCEEDED:
            succeeded += 1
        elif task.status == OcrTask.STATUS_FAILED:
            failed += 1
        elif task.status == OcrTask.STATUS_PENDING:
            pending_retry += 1
    return {'succeeded': succeeded, 'failed': failed, 'pending_retry': pending_retry}
