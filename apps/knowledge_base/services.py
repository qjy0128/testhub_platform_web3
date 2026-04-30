import hashlib
import math
import os
import re
from dataclasses import dataclass

from asgiref.sync import async_to_sync
from django.db import transaction

from apps.core.url_safety import validate_outbound_http_url

from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeQuery


MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 120
LOCAL_EMBEDDING_DIMENSIONS = 96
LOCAL_EMBEDDING_PROVIDER = 'local-hash'
OPENAI_COMPATIBLE_EMBEDDING_PROVIDER = 'openai-compatible'
DATABASE_VECTOR_STORE = 'database'
TOKEN_PATTERN = re.compile(r'[\w\u4e00-\u9fff]+', re.UNICODE)
TEXT_EXTENSIONS = {'.txt', '.md', '.markdown', '.csv', '.json', '.log', '.yaml', '.yml'}
PDF_EXTENSIONS = {'.pdf'}
DOCX_EXTENSIONS = {'.docx'}
SUPPORTED_UPLOAD_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS


@dataclass(frozen=True)
class SearchHit:
    chunk: KnowledgeChunk
    score: float
    excerpt: str


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list
    provider: str
    model: str

    @property
    def dimensions(self):
        return len(self.vector or [])


class BaseEmbeddingProvider:
    provider_key = LOCAL_EMBEDDING_PROVIDER

    def __init__(self, knowledge_base):
        self.knowledge_base = knowledge_base

    @property
    def model_name(self):
        return self.knowledge_base.embedding_model or f'hash-{LOCAL_EMBEDDING_DIMENSIONS}'

    def embed_texts(self, texts):
        raise NotImplementedError

    def embed_query(self, text):
        return self.embed_texts([text])[0]


class LocalHashEmbeddingProvider(BaseEmbeddingProvider):
    provider_key = LOCAL_EMBEDDING_PROVIDER

    def embed_texts(self, texts):
        return [
            EmbeddingResult(
                vector=vectorize_text(text),
                provider=self.provider_key,
                model=self.model_name,
            )
            for text in texts
        ]


class OpenAICompatibleEmbeddingProvider(BaseEmbeddingProvider):
    provider_key = OPENAI_COMPATIBLE_EMBEDDING_PROVIDER

    @property
    def model_name(self):
        return self.knowledge_base.embedding_model or self.embedding_settings.get('model') or 'text-embedding-3-small'

    @property
    def embedding_settings(self):
        metadata = self.knowledge_base.metadata or {}
        settings = metadata.get('embedding', {})
        return settings if isinstance(settings, dict) else {}

    def _resolve_api_key(self):
        settings = self.embedding_settings
        env_name = settings.get('api_key_env') or settings.get('credential_ref')
        if env_name:
            value = os.environ.get(env_name)
            if value:
                return value
            raise ValueError(f'Embedding API key environment variable is not set: {env_name}')
        api_key = settings.get('api_key')
        if api_key:
            return api_key
        raise ValueError('Embedding API key is not configured.')

    def _resolve_embeddings_url(self):
        settings = self.embedding_settings
        base_url = (settings.get('base_url') or '').strip()
        if not base_url:
            raise ValueError('Embedding base_url is not configured.')
        base_url = validate_outbound_http_url(base_url, label='Embedding base URL').rstrip('/')
        if base_url.endswith('/embeddings'):
            return base_url
        version_match = re.search(r'/v\d+$', base_url)
        if version_match:
            return f'{base_url}/embeddings'
        return f'{base_url}/v1/embeddings'

    def embed_texts(self, texts):
        if not texts:
            return []

        import httpx

        settings = self.embedding_settings
        payload = {
            'model': self.model_name,
            'input': list(texts),
        }
        dimensions = settings.get('dimensions')
        if dimensions:
            payload['dimensions'] = int(dimensions)

        headers = {
            'Authorization': f'Bearer {self._resolve_api_key()}',
            'Content-Type': 'application/json',
        }
        timeout = float(settings.get('timeout_seconds') or 60)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(self._resolve_embeddings_url(), headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        rows = data.get('data') if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError('Embedding response does not contain a data array.')
        rows = sorted(rows, key=lambda item: item.get('index', 0))
        vectors = []
        for item in rows:
            vector = item.get('embedding') if isinstance(item, dict) else None
            if not isinstance(vector, list):
                raise ValueError('Embedding response item is missing embedding vector.')
            vectors.append([
                float(value)
                for value in vector
            ])
        if len(vectors) != len(texts):
            raise ValueError('Embedding response size does not match input size.')
        return [
            EmbeddingResult(vector=vector, provider=self.provider_key, model=self.model_name)
            for vector in vectors
        ]


class DatabaseVectorStore:
    name = DATABASE_VECTOR_STORE

    def search(self, knowledge_base, question, query_embedding, limit=5):
        question_tokens = tokenize(question)
        hits = []
        chunks = KnowledgeChunk.objects.filter(
            document__knowledge_base=knowledge_base,
            document__status=KnowledgeDocument.STATUS_INDEXED,
            embedding_status=KnowledgeChunk.EMBEDDING_READY,
        ).select_related('document')

        for chunk in chunks:
            chunk_tokens = tokenize(chunk.content)
            keyword_score = len(question_tokens & chunk_tokens)
            vector_score = max(0.0, cosine_similarity(query_embedding.vector, chunk.embedding_vector or []))
            score = keyword_score + (vector_score * 4)
            if score <= 0:
                continue
            hits.append(SearchHit(
                chunk=chunk,
                score=round(score, 4),
                excerpt=_excerpt(chunk.content, question_tokens),
            ))

        hits.sort(key=lambda hit: (-hit.score, hit.chunk.document_id, hit.chunk.chunk_index))
        return hits[:limit]


def get_embedding_provider(knowledge_base):
    provider = (knowledge_base.embedding_provider or LOCAL_EMBEDDING_PROVIDER).strip().lower()
    if provider in {'', LOCAL_EMBEDDING_PROVIDER, 'hash', 'local'}:
        return LocalHashEmbeddingProvider(knowledge_base)
    if provider in {OPENAI_COMPATIBLE_EMBEDDING_PROVIDER, 'openai', 'custom'}:
        return OpenAICompatibleEmbeddingProvider(knowledge_base)
    raise ValueError(f'Unsupported embedding provider: {provider}')


def get_vector_store(knowledge_base):
    store = (getattr(knowledge_base, 'vector_store', '') or DATABASE_VECTOR_STORE).strip().lower()
    if store == DATABASE_VECTOR_STORE:
        return DatabaseVectorStore()
    raise ValueError(f'Unsupported vector store: {store}')


def normalize_text(value):
    lines = [line.strip() for line in (value or '').replace('\r\n', '\n').split('\n')]
    compact_lines = []
    blank_seen = False
    for line in lines:
        if not line:
            if not blank_seen:
                compact_lines.append('')
            blank_seen = True
            continue
        compact_lines.append(line)
        blank_seen = False
    return '\n'.join(compact_lines).strip()


def content_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def get_extension(filename):
    return os.path.splitext(filename or '')[1].lower()


def validate_upload_file(uploaded_file, max_size=10 * 1024 * 1024):
    extension = get_extension(uploaded_file.name)
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError('Unsupported knowledge document file type.')
    if uploaded_file.size > max_size:
        raise ValueError('Knowledge document file is too large.')
    return extension


def extract_text_from_text_file(file_path):
    for encoding in ('utf-8', 'utf-8-sig', 'gbk', 'latin-1'):
        try:
            with open(file_path, 'r', encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError:
            continue
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
        return handle.read()


def extract_text_from_pdf(file_path):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        from PyPDF2 import PdfFileReader as PdfReader

    text_parts = []
    with open(file_path, 'rb') as handle:
        reader = PdfReader(handle)
        pages = getattr(reader, 'pages', [])
        for page in pages:
            text_parts.append(page.extract_text() or '')
    return '\n'.join(text_parts)


def extract_text_from_docx(file_path):
    import docx

    document = docx.Document(file_path)
    return '\n'.join(paragraph.text for paragraph in document.paragraphs)


def extract_text_from_document_file(file_path, filename):
    extension = get_extension(filename)
    if extension in TEXT_EXTENSIONS:
        return extract_text_from_text_file(file_path)
    if extension in PDF_EXTENSIONS:
        return extract_text_from_pdf(file_path)
    if extension in DOCX_EXTENSIONS:
        return extract_text_from_docx(file_path)
    raise ValueError('Unsupported knowledge document file type.')


def tokenize(text):
    return {token.lower() for token in TOKEN_PATTERN.findall(text or '') if len(token.strip()) > 1}


def estimate_token_count(text):
    return max(1, len(TOKEN_PATTERN.findall(text or '')))


def vectorize_text(text, dimensions=LOCAL_EMBEDDING_DIMENSIONS):
    vector = [0.0] * dimensions
    tokens = TOKEN_PATTERN.findall(text or '')
    if not tokens:
        return vector

    for token in tokens:
        normalized = token.lower().strip()
        if not normalized:
            continue
        digest = hashlib.sha256(normalized.encode('utf-8')).digest()
        bucket = int.from_bytes(digest[:4], 'big') % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    magnitude = math.sqrt(sum(value * value for value in vector))
    if not magnitude:
        return vector
    return [round(value / magnitude, 6) for value in vector]


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    return sum(float(left[index]) * float(right[index]) for index in range(size))


def split_text(text, max_chars=MAX_CHUNK_CHARS, overlap_chars=CHUNK_OVERLAP_CHARS):
    text = normalize_text(text)
    if not text:
        return []

    paragraphs = [paragraph.strip() for paragraph in re.split(r'\n\s*\n', text) if paragraph.strip()]
    chunks = []
    current = ''

    for paragraph in paragraphs:
        separator = '\n\n' if current else ''
        candidate = f'{current}{separator}{paragraph}'
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = current[-overlap_chars:] if overlap_chars else ''

        if len(paragraph) <= max_chars:
            current = f'{current}\n\n{paragraph}'.strip() if current else paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = start + max_chars
            chunk = paragraph[start:end].strip()
            if chunk:
                chunks.append(chunk)
            next_start = end - overlap_chars if overlap_chars else end
            start = next_start if next_start > start else end
        current = ''

    if current:
        chunks.append(current)

    return chunks


def split_document_into_chunks(document):
    metadata = document.metadata or {}
    ocr_pages = metadata.get('ocr_pages')
    if isinstance(ocr_pages, list) and ocr_pages:
        rows = []
        for page in ocr_pages:
            if not isinstance(page, dict):
                continue
            page_number = page.get('page_number')
            page_text = normalize_text(page.get('text') or '')
            if not page_text:
                continue
            for chunk in split_text(page_text):
                rows.append({
                    'content': chunk,
                    'metadata': {
                        'source': 'ocr_service',
                        'page_number': page_number,
                        'ocr_task_id': metadata.get('ocr_task_id'),
                        'ocr_page_id': page.get('id'),
                    },
                })
        if rows:
            return rows

    return [
        {
            'content': chunk,
            'metadata': {},
        }
        for chunk in split_text(document.content_text)
    ]


def index_document(document):
    document.status = KnowledgeDocument.STATUS_INDEXING
    document.error_message = ''
    document.save(update_fields=['status', 'error_message', 'updated_at'])

    text = normalize_text(document.content_text)
    if not text:
        document.status = KnowledgeDocument.STATUS_FAILED
        document.chunk_count = 0
        document.error_message = 'No text content to index.'
        document.save(update_fields=['status', 'chunk_count', 'error_message', 'updated_at'])
        return document

    chunks = split_document_into_chunks(document)
    embedding_provider = get_embedding_provider(document.knowledge_base)
    vector_store = get_vector_store(document.knowledge_base)
    embeddings = embedding_provider.embed_texts([chunk['content'] for chunk in chunks])

    with transaction.atomic():
        document.chunks.all().delete()
        KnowledgeChunk.objects.bulk_create([
            KnowledgeChunk(
                document=document,
                chunk_index=index,
                content=chunk['content'],
                token_count=estimate_token_count(chunk['content']),
                embedding_status=KnowledgeChunk.EMBEDDING_READY,
                embedding_provider=embedding.provider,
                embedding_model=embedding.model,
                embedding_dimensions=embedding.dimensions,
                embedding_ref=f'{embedding.provider}:{embedding.model}:{vector_store.name}',
                embedding_vector=embedding.vector,
                metadata={
                    'vector_store': vector_store.name,
                    **chunk.get('metadata', {}),
                },
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ])

        document.content_text = text
        document.content_hash = content_hash(text)
        document.chunk_count = len(chunks)
        document.status = KnowledgeDocument.STATUS_INDEXED
        document.error_message = ''
        document.save(update_fields=[
            'content_text',
            'content_hash',
            'chunk_count',
            'status',
            'error_message',
            'updated_at',
        ])
    return document


def _excerpt(content, question_tokens):
    content = normalize_text(content)
    if not content:
        return ''

    lowered = content.lower()
    first_match = None
    for token in question_tokens:
        position = lowered.find(token)
        if position >= 0 and (first_match is None or position < first_match):
            first_match = position

    if first_match is None:
        return content[:360]

    start = max(0, first_match - 140)
    end = min(len(content), first_match + 260)
    prefix = '...' if start > 0 else ''
    suffix = '...' if end < len(content) else ''
    return f'{prefix}{content[start:end]}{suffix}'


def search_knowledge_base(knowledge_base, question, limit=5):
    question_tokens = tokenize(question)
    if not question_tokens:
        return []
    embedding_provider = get_embedding_provider(knowledge_base)
    vector_store = get_vector_store(knowledge_base)
    query_embedding = embedding_provider.embed_query(question)
    return vector_store.search(knowledge_base, question, query_embedding, limit=limit)


def get_answer_model_config(user=None):
    try:
        from apps.requirement_analysis.models import AIModelConfig
    except Exception:
        return None

    queryset = AIModelConfig.objects.filter(is_active=True)
    roles = ['knowledge_base', 'writer']
    if user is not None and getattr(user, 'is_authenticated', False):
        for role in roles:
            config = queryset.filter(created_by=user, role=role).order_by('-updated_at').first()
            if config:
                return config
    for role in roles:
        config = queryset.filter(role=role).order_by('-updated_at').first()
        if config:
            return config
    return None


def _extract_ai_content(response):
    choices = response.get('choices') if isinstance(response, dict) else None
    if not choices:
        return ''
    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                parts.append(item.get('text', ''))
        return '\n'.join(parts).strip()
    return ''


def _build_local_answer(hits):
    answer_lines = ['Based on the indexed content, the most relevant references are:']
    for index, hit in enumerate(hits, start=1):
        title = hit.chunk.document.title
        answer_lines.append(f'{index}. {title}: {hit.excerpt}')
    return '\n'.join(answer_lines)


def synthesize_answer_with_ai(query, hits):
    config = get_answer_model_config(query.created_by)
    if config is None:
        return ''

    references = []
    for index, hit in enumerate(hits, start=1):
        references.append(
            f'[{index}] {hit.chunk.document.title}\n'
            f'Document ID: {hit.chunk.document_id}, Chunk: {hit.chunk.chunk_index}\n'
            f'{hit.chunk.content[:1800]}'
        )

    messages = [
        {
            'role': 'system',
            'content': (
                'You answer questions strictly from the supplied knowledge base references. '
                'If the references are insufficient, say what is missing. '
                'Cite references with bracket numbers such as [1].'
            ),
        },
        {
            'role': 'user',
            'content': (
                f'Question:\n{query.question}\n\n'
                f'References:\n\n' + '\n\n'.join(references)
            ),
        },
    ]

    from apps.requirement_analysis.models import AIModelService

    response = async_to_sync(AIModelService.call_openai_compatible_api)(
        config,
        messages,
        max_tokens=min(getattr(config, 'max_tokens', 1600) or 1600, 2400),
    )
    return _extract_ai_content(response)


@transaction.atomic
def answer_query(query, use_ai=True):
    hits = search_knowledge_base(query.knowledge_base, query.question)
    if not hits:
        query.answer = 'No relevant indexed content was found in this knowledge base.'
        query.citations = []
        query.status = KnowledgeQuery.STATUS_ANSWERED
        query.error_message = ''
        query.save(update_fields=['answer', 'citations', 'status', 'error_message'])
        return query

    citations = []
    for hit in hits:
        title = hit.chunk.document.title
        citations.append({
            'document_id': hit.chunk.document_id,
            'document_title': title,
            'chunk_id': hit.chunk.id,
            'chunk_index': hit.chunk.chunk_index,
            'page_number': (hit.chunk.metadata or {}).get('page_number'),
            'score': hit.score,
            'excerpt': hit.excerpt,
        })

    fallback_answer = _build_local_answer(hits)
    ai_error = ''
    if use_ai:
        try:
            ai_answer = synthesize_answer_with_ai(query, hits)
            if ai_answer:
                fallback_answer = ai_answer
        except Exception as exc:
            ai_error = f'AI synthesis failed, local retrieval answer returned: {exc}'

    query.answer = fallback_answer
    query.citations = citations
    query.status = KnowledgeQuery.STATUS_ANSWERED
    query.error_message = ai_error
    query.save(update_fields=['answer', 'citations', 'status', 'error_message'])
    return query


def index_pending_documents(limit=None, queryset=None):
    queryset = queryset or KnowledgeDocument.objects.all()
    queryset = queryset.filter(
        status__in=[KnowledgeDocument.STATUS_PENDING, KnowledgeDocument.STATUS_FAILED],
    ).exclude(content_text='')
    if limit:
        queryset = queryset[:limit]

    indexed = 0
    failed = 0
    for document in queryset:
        try:
            index_document(document)
            indexed += 1
        except Exception as exc:
            document.status = KnowledgeDocument.STATUS_FAILED
            document.error_message = str(exc)
            document.save(update_fields=['status', 'error_message', 'updated_at'])
            failed += 1
    return {'indexed': indexed, 'failed': failed}
