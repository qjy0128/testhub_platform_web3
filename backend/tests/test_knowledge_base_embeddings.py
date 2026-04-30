import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.knowledge_base.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from apps.knowledge_base.services import index_document, search_knowledge_base
from apps.projects.models import Project


class _EmbeddingResponse:
    def __init__(self, vectors):
        self.vectors = vectors

    def raise_for_status(self):
        return None

    def json(self):
        return {
            'data': [
                {'index': index, 'embedding': vector}
                for index, vector in enumerate(self.vectors)
            ]
        }


class KnowledgeBaseEmbeddingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='owner', password='pass')
        self.project = Project.objects.create(name='KB Project', owner=self.owner)

    def test_local_hash_embedding_indexes_and_searches_without_external_service(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Local KB',
            created_by=self.owner,
        )
        document = KnowledgeDocument.objects.create(
            knowledge_base=knowledge_base,
            title='Login Requirement',
            source_type=KnowledgeDocument.SOURCE_TEXT,
            content_text='login failure should show an account or password error.',
            created_by=self.owner,
        )

        index_document(document)

        chunk = KnowledgeChunk.objects.get(document=document)
        self.assertEqual(chunk.embedding_provider, 'local-hash')
        self.assertEqual(chunk.embedding_model, 'hash-96')
        self.assertEqual(chunk.embedding_dimensions, 96)
        self.assertEqual(chunk.metadata['vector_store'], 'database')

        hits = search_knowledge_base(knowledge_base, 'login failure')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.document_id, document.id)

    def test_openai_compatible_embedding_provider_uses_configured_endpoint(self):
        knowledge_base = KnowledgeBase.objects.create(
            project=self.project,
            name='Remote KB',
            embedding_provider='openai-compatible',
            embedding_model='text-embedding-test',
            metadata={
                'embedding': {
                    'base_url': 'https://embedding.example/v1',
                    'api_key_env': 'KB_EMBEDDING_KEY',
                }
            },
            created_by=self.owner,
        )
        document = KnowledgeDocument.objects.create(
            knowledge_base=knowledge_base,
            title='Payment Requirement',
            source_type=KnowledgeDocument.SOURCE_TEXT,
            content_text='支付成功后订单状态应更新为已支付。',
            created_by=self.owner,
        )

        response = _EmbeddingResponse([[0.1, 0.2, 0.3]])
        with patch.dict(os.environ, {'KB_EMBEDDING_KEY': 'secret'}), patch('httpx.Client.post', return_value=response) as post:
            index_document(document)

        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://embedding.example/v1/embeddings')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret')
        self.assertEqual(kwargs['json']['model'], 'text-embedding-test')
        self.assertEqual(kwargs['json']['input'], ['支付成功后订单状态应更新为已支付。'])

        chunk = KnowledgeChunk.objects.get(document=document)
        self.assertEqual(chunk.embedding_provider, 'openai-compatible')
        self.assertEqual(chunk.embedding_model, 'text-embedding-test')
        self.assertEqual(chunk.embedding_dimensions, 3)
        self.assertEqual(chunk.embedding_vector, [0.1, 0.2, 0.3])
