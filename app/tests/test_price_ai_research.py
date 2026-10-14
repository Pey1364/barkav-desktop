from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import price_ai_research as research


class FakeGeminiClient:
    def __init__(self, result: research.GroundedResult):
        self.result = result
        self.prompts: list[str] = []

    def fetch_grounded_value(self, prompt: str) -> research.GroundedResult:
        self.prompts.append(prompt)
        return self.result


class FakeSanityClient:
    def __init__(self, engine: str, plausible: bool | None, note: str = ''):
        self.engine_name = engine
        self._plausible = plausible
        self._note = note
        self.calls: list[tuple[float, str]] = []

    def check_plausible(self, value: float, context: str) -> research.SanityCheckResult:
        self.calls.append((value, context))
        return research.SanityCheckResult(self.engine_name, self._plausible, self._note)


def test_cfg_prefers_env_var_over_secrets_file(tmp_path: Path, monkeypatch):
    (tmp_path / 'secrets.local.json').write_text(json.dumps({'GEMINI_API_KEY': 'from-file'}), encoding='utf-8')
    monkeypatch.setenv('GEMINI_API_KEY', 'from-env')
    assert research.cfg('GEMINI_API_KEY', tmp_path) == 'from-env'


def test_cfg_falls_back_to_secrets_file(tmp_path: Path, monkeypatch):
    (tmp_path / 'secrets.local.json').write_text(json.dumps({'GEMINI_API_KEY': 'from-file'}), encoding='utf-8')
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert research.cfg('GEMINI_API_KEY', tmp_path) == 'from-file'


def test_cfg_returns_default_when_nothing_configured(tmp_path: Path, monkeypatch):
    monkeypatch.delenv('SOME_MISSING_KEY', raising=False)
    assert research.cfg('SOME_MISSING_KEY', tmp_path, default='fallback') == 'fallback'


def test_parse_grounded_response_extracts_number_and_source_urls():
    chunk = SimpleNamespace(web=SimpleNamespace(uri='https://tgju.org/profile/price_dollar_rl'))
    grounding = SimpleNamespace(grounding_chunks=[chunk])
    candidate = SimpleNamespace(grounding_metadata=grounding)
    response = SimpleNamespace(text='نرخ دلار آزاد امروز 232,500 تومان است.', candidates=[candidate])

    result = research.parse_grounded_response(response)
    assert result.value == 232_500
    assert result.source_urls == ['https://tgju.org/profile/price_dollar_rl']


def test_parse_grounded_response_handles_persian_comma_and_no_sources():
    response = SimpleNamespace(text='قیمت مس کاتد 2،603،290 تومان بر کیلوگرم.', candidates=[])
    result = research.parse_grounded_response(response)
    assert result.value == 2_603_290
    assert result.source_urls == []


def test_parse_grounded_response_raises_when_no_number_found():
    response = SimpleNamespace(text='متاسفانه اطلاعاتی پیدا نشد.', candidates=[])
    with pytest.raises(ValueError):
        research.parse_grounded_response(response)


def test_fetch_and_verify_uses_gemini_as_sole_live_source():
    gemini = FakeGeminiClient(research.GroundedResult(232_500, 'نرخ فعلی 232,500', ['https://tgju.org']))
    sanity = [FakeSanityClient('OPENROUTER:QWEN', True), FakeSanityClient('GROQ:LLAMA4', True)]

    result = research.fetch_and_verify('نرخ دلار آزاد چند است؟', 'context', gemini_client=gemini,
                                        sanity_clients=sanity)

    assert result.value == 232_500
    assert result.needs_review is False
    assert gemini.prompts == ['نرخ دلار آزاد چند است؟']
    # Sanity engines are asked to react to Gemini's number, never to produce their own.
    assert all(call[0] == 232_500 for client in sanity for call in client.calls)


def test_fetch_and_verify_flags_review_on_any_disagreement_not_majority():
    gemini = FakeGeminiClient(research.GroundedResult(232_500, 'نرخ فعلی 232,500'))
    sanity = [
        FakeSanityClient('OPENROUTER:QWEN', True),
        FakeSanityClient('OPENROUTER:DEEPSEEK', True),
        FakeSanityClient('OPENROUTER:GLM', True),
        FakeSanityClient('GROQ:LLAMA4', False, note='این عدد خیلی بالا به‌نظر می‌رسد'),
    ]

    result = research.fetch_and_verify('q', 'context', gemini_client=gemini, sanity_clients=sanity)

    assert result.needs_review is True
    assert 'GROQ:LLAMA4' in result.review_reason


def test_fetch_and_verify_treats_engine_errors_as_neutral_not_disagreement():
    gemini = FakeGeminiClient(research.GroundedResult(232_500, 'x'))
    sanity = [FakeSanityClient('OPENROUTER:QWEN', None, note='خطا در تماس: timeout')]

    result = research.fetch_and_verify('q', 'context', gemini_client=gemini, sanity_clients=sanity)

    assert result.needs_review is False
    assert result.sanity_checks[0].plausible is None


def test_default_gemini_client_returns_none_without_a_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert research.default_gemini_client(tmp_path) is None


def test_default_gemini_client_builds_with_configured_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key-123')
    client = research.default_gemini_client(tmp_path)
    assert isinstance(client, research.GeminiGroundedClient)


def test_default_sanity_clients_only_includes_engines_with_a_configured_key(tmp_path: Path, monkeypatch):
    for _name, _model_env, _default_model, _url, key_env in research._SANITY_ENGINES:
        monkeypatch.delenv(key_env, raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'or-key')

    clients = research.default_sanity_clients(tmp_path)
    names = {c.engine_name for c in clients}
    assert names == {'OPENROUTER:QWEN', 'OPENROUTER:DEEPSEEK', 'OPENROUTER:GLM'}
    assert 'GROQ:LLAMA4' not in names


def test_openai_compatible_sanity_client_never_hits_network_in_tests(monkeypatch):
    """Guard: this test documents that check_plausible must go through the
    injectable openai.OpenAI client, so a monkeypatch of openai.OpenAI fully
    intercepts it -- no real network call is reachable from a unit test."""

    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            message = SimpleNamespace(content='بله، منطقی به‌نظر می‌رسد.')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setattr('openai.OpenAI', FakeOpenAI)
    client = research.OpenAICompatibleSanityClient('OPENROUTER:QWEN', 'key', 'https://example.test', 'model-x')
    result = client.check_plausible(232_500, 'context')

    assert result.plausible is True
    assert calls and calls[0]['model'] == 'model-x'


def _roster():
    import price_ai_research as research

    info = research.ModelInfo
    return [
        info('GEMINI', 'Gemini', 'Google', research.ROLE_SEARCH, 'g', '', 'K', True, free=True),
        info('GEMINI:gemini-flash-latest', 'Flash', 'Google', research.ROLE_SEARCH, 'f', '', 'K', True, free=True),
        info('OPENROUTER:QWEN', 'Qwen', 'Openrouter', research.ROLE_CHECK, 'q', '', 'K2', True, free=True),
        info('BASETEN:KIMI', 'Kimi', 'Baseten', research.ROLE_CHECK, 'k', '', 'K3', True),
        info('OPENAI', 'OpenAI', 'OpenAI', research.ROLE_CHECK, 'o', '', 'K4', False),
    ]


def test_selection_modes_never_include_an_engine_without_a_key():
    import price_ai_research as research

    roster = _roster()
    assert research.resolve_selection('AUTO', roster, []) == ['GEMINI', 'GEMINI:gemini-flash-latest', 'OPENROUTER:QWEN']
    assert research.resolve_selection('ALL_ACTIVE', roster, []) == [m.engine_id for m in roster[:4]]
    assert research.resolve_selection('GEMINI_ONLY', roster, []) == ['GEMINI']
    assert research.resolve_selection('OFF', roster, ['GEMINI']) == []
    assert research.resolve_selection('SELECTED', roster, ['OPENAI', 'BASETEN:KIMI']) == ['BASETEN:KIMI']
    assert set(research.PRICE_AI_MODES) == {'AUTO', 'ALL_ACTIVE', 'SELECTED', 'GEMINI_ONLY', 'OFF'}


def test_the_next_selected_gemini_answers_when_the_first_fails():
    import price_ai_research as research

    class Down:
        def fetch_grounded_value(self, prompt):
            raise RuntimeError('429 quota')

    class Up:
        def fetch_grounded_value(self, prompt):
            return research.GroundedResult(7.0, 'ok')

    assert research._FirstWorkingGrounded([Down(), Up()]).fetch_grounded_value('x').value == 7.0
    try:
        research._FirstWorkingGrounded([Down()]).fetch_grounded_value('x')
    except RuntimeError as exc:
        assert '429' in str(exc)
    else:
        raise AssertionError('expected the failure to surface')


def test_months_between_shamsi_dates_counts_whole_months():
    from price_update_stage18_7 import _shamsi_months_between

    assert _shamsi_months_between('1405/01/10', '1405/04/10') == 3
    assert _shamsi_months_between('1404/11/20', '1405/02/05') == 2
    assert _shamsi_months_between('۱۴۰۵/۰۱/۰۱', '۱۴۰۶/۰۱/۰۱') == 12
    assert _shamsi_months_between('', '1405/01/01') is None
