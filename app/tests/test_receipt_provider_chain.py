from __future__ import annotations

import asyncio
from unittest.mock import patch

import receipt_ai_provider as provider_module
from receipt_ai_provider import OpenAICompatibleVisionParser, ReceiptVisionProviderChain


class FakeProvider:
    def __init__(self, confidence, label):
        self.confidence = confidence
        self.label = label
        self.calls = 0

    async def analyze(self, **_kwargs):
        self.calls += 1
        return {'confidence': self.confidence, 'description': self.label}


def test_auto_chain_escalates_and_keeps_best_low_confidence_result():
    first = FakeProvider(0.5, 'first')
    second = FakeProvider(0.82, 'second')
    chain = ReceiptVisionProviderChain([('GEMINI:model', first), ('OPENROUTER:QWEN', second)])

    result = asyncio.run(chain.analyze(text='receipt'))

    assert [first.calls, second.calls] == [1, 1]
    assert result['description'] == 'second'
    assert result['_vision_provider'] == 'OPENROUTER:QWEN'
    assert chain.last_provider == 'OPENROUTER:QWEN'


def test_auto_chain_stops_when_confidence_reaches_configured_threshold():
    first = FakeProvider(0.9, 'enough')
    second = FakeProvider(0.99, 'unused')
    chain = ReceiptVisionProviderChain([('GEMINI:model', first), ('GROQ:LLAMA4', second)], confidence_threshold=0.85)

    result = asyncio.run(chain.analyze(text='receipt'))

    assert result['description'] == 'enough'
    assert [first.calls, second.calls] == [1, 0]


def test_all_engine_mode_reads_each_allowed_provider_and_keeps_best():
    first = FakeProvider(0.86, 'first')
    second = FakeProvider(0.94, 'second')
    third = FakeProvider(0.91, 'third')
    chain = ReceiptVisionProviderChain(
        [('GEMINI:model', first), ('OPENROUTER:QWEN', second), ('GROQ:LLAMA4', third)],
        confidence_threshold=0.85,
        stop_on_threshold=False,
    )

    result = asyncio.run(chain.analyze(text='receipt'))

    assert [first.calls, second.calls, third.calls] == [1, 1, 1]
    assert result['description'] == 'second'
    assert result['_vision_provider'] == 'OPENROUTER:QWEN'


def test_manual_engine_mode_builds_only_the_selected_provider(monkeypatch):
    created = []

    def fake_parser(_key, model, base_url):
        parser = FakeProvider(0.99, model)
        created.append((model, base_url, parser))
        return parser

    monkeypatch.setattr(provider_module, '_read_local_secrets', lambda _path: {'OPENROUTER_API_KEY': 'test-key'})
    monkeypatch.setattr(provider_module, 'OpenAICompatibleVisionParser', fake_parser)
    monkeypatch.setenv('STAGE4_DB_PATH', 'isolated-test.sqlite3')
    import v18_store
    with patch.object(v18_store, 'load_ui', return_value={'ai_engine_mode': 'OPENROUTER:QWEN', 'ai_confidence_threshold': 0.85}):
        chain = provider_module.build_receipt_vision_parser('.', gemini_api_key='', gemini_model='')

    assert [name for name, _parser in chain.providers] == ['OPENROUTER:QWEN']


def test_all_mode_builds_only_the_reported_ordered_provider_roster(monkeypatch):
    def fake_compatible(_key, model, base_url):
        return FakeProvider(0.9, f'{base_url}:{model}')

    def fake_gemini(_key, model):
        return FakeProvider(0.9, model)

    monkeypatch.setattr(provider_module, '_read_local_secrets', lambda _path: {
        'OPENROUTER_API_KEY': 'openrouter-test',
        'BASETEN_DEEPSEEK_V41_FLASH_API_KEY': 'baseten-deepseek-test',
        'BASETEN_GLM_FLASH_API_KEY': 'baseten-glm-test',
        'GROQ_API_KEY': 'groq-test',
    })
    monkeypatch.setattr(provider_module, 'OpenAICompatibleVisionParser', fake_compatible)
    monkeypatch.setattr(provider_module, 'GeminiFinancialParser', fake_gemini)
    monkeypatch.setenv('STAGE4_DB_PATH', 'isolated-test.sqlite3')
    import v18_store
    with patch.object(v18_store, 'load_ui', return_value={'ai_engine_mode': 'ALL', 'ai_confidence_threshold': 0.85}):
        chain = provider_module.build_receipt_vision_parser(
            '.', gemini_api_key='gemini-test', gemini_model='gemini-flash-latest')

    assert [name for name, _parser in chain.providers] == [
        'GEMINI:gemini-flash-latest', 'OPENROUTER:QWEN',
        'BASETEN:DEEPSEEK_V41_FLASH', 'BASETEN:GLM_FLASH', 'GROQ:LLAMA4',
    ]
    assert chain.stop_on_threshold is False


def test_openai_compatible_provider_accepts_text_only_reprocess(monkeypatch):
    captured = {}
    class Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            message = type('Message', (), {'content': '{"detected_type":"INFO","confidence":0.9,"description":"گزارش"}'})()
            return type('Response', (), {'choices': [type('Choice', (), {'message': message})()]})()
    class Client:
        def __init__(self, **_kwargs):
            self.chat = type('Chat', (), {'completions': Completions()})()
            self.closed = False
        async def close(self):
            self.closed = True
    parser = object.__new__(OpenAICompatibleVisionParser)
    parser._AsyncOpenAI = Client
    parser._api_key = 'test'
    parser._base_url = 'https://example.invalid/v1'
    parser.model = 'test-model'

    result = asyncio.run(parser.analyze(text='متن گزارش', image_bytes=None))

    assert result['detected_type'] == 'INFO'
    content = captured['messages'][0]['content']
    assert len(content) == 1 and content[0]['type'] == 'text'
