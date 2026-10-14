"""Live web-research for macro parameters (دلار/مس/حداقل‌حقوق) via Gemini grounding.

Architecture agreed with the sibling session that owns the receipt-reading AI
chain (`receipt_ai_provider.py`) after they reviewed it -- **not** their
confidence-escalation pattern ("try engines until one looks good"). Only
Gemini has live web access in this app's engine roster (Google Search
grounding, via the ``google-genai`` SDK already used elsewhere); the other
four (Qwen/DeepSeek/GLM/Llama-4, all plain chat completions with no tool
access) would silently return a stale/guessed number from training data if
used as a fallback for a "live" figure -- a hidden quality regression, not a
real fallback.

So: Gemini-with-grounding is the *only* source of the live number here. The
other four are asked afterward only "does this number look plausible?" (a
sanity check, never a regeneration) -- disagreement gets flagged for manual
operator review via the module's existing ``needs_review`` mechanism, never
auto-resolved by swapping in a different engine's number.

Reuses the same config keys (``GEMINI_API_KEY``/``OPENROUTER_API_KEY``/
``GROQ_API_KEY``, from the environment or ``secrets.local.json``) the
receipt-reading feature already uses -- same shared key, confirmed with the
operator, read-only reuse. Does not import anything from
``receipt_ai_provider.py``: that module's ``OpenAICompatibleVisionParser``
is explicitly built for image input and raises without it; this module's
prompts are plain text, so it talks to the same base URLs directly instead.

**Wired into «شروع براورد» step ۵ (مدل هوش مصنوعی)** as an advisory
lookup: a researched value is only shown beside the entered one, and is
written only when the operator applies that row. Every network-touching class here is built
against a small ``Protocol`` so tests never make a real call, but nobody has
verified this against a *real* Gemini API key yet -- in particular the
sibling session's warning that some API versions restrict combining
``google_search`` grounding with a forced JSON ``response_schema`` in the
same call needs a real smoke test before this reaches the run wizard.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from runtime_base import load_local_secrets

_OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'
_GROQ_BASE_URL = 'https://api.groq.com/openai/v1'

# Same free-tier OpenRouter ids receipt_ai_provider.py uses for these three,
# kept as separate constants rather than imported so this module has no
# import-time dependency on that file's internals.
_SANITY_ENGINES = (
    ('OPENROUTER:QWEN', 'OPENROUTER_QWEN_MODEL', 'qwen/qwen3-235b-a22b:free', _OPENROUTER_BASE_URL, 'OPENROUTER_API_KEY'),
    ('OPENROUTER:DEEPSEEK', 'OPENROUTER_DEEPSEEK_MODEL', 'deepseek/deepseek-chat-v3.1:free', _OPENROUTER_BASE_URL, 'OPENROUTER_API_KEY'),
    ('OPENROUTER:GLM', 'OPENROUTER_GLM_MODEL', 'z-ai/glm-4.5-air:free', _OPENROUTER_BASE_URL, 'OPENROUTER_API_KEY'),
    ('GROQ:LLAMA4', 'GROQ_LLAMA_VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct', _GROQ_BASE_URL, 'GROQ_API_KEY'),
)


def _read_local_secrets(base_dir: str | Path) -> dict:
    return load_local_secrets(base_dir)


def cfg(name: str, base_dir: str | Path, default: str = '') -> str:
    """env var, then secrets.local.json -- same lookup order as receipt_ai_provider.cfg."""

    secrets = _read_local_secrets(base_dir)
    return str(os.getenv(name) or secrets.get(name) or default).strip()


@dataclass
class GroundedResult:
    value: float
    explanation: str
    source_urls: list[str] = field(default_factory=list)


class GroundedClient(Protocol):
    def fetch_grounded_value(self, prompt: str) -> GroundedResult: ...


class GeminiGroundedClient:
    """Real client. Import of ``google.genai`` is lazy so this module is
    importable (and its parsing/orchestration logic testable) even where the
    SDK or a key isn't configured."""

    def __init__(self, api_key: str, model: str = 'gemini-3.6-flash'):
        self._api_key = api_key
        self._model = model

    def fetch_grounded_value(self, prompt: str) -> GroundedResult:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        response = client.models.generate_content(model=self._model, contents=prompt, config=config)
        return parse_grounded_response(response)


_NUMBER_PATTERN = re.compile(r'([0-9][0-9,]*(?:\.[0-9]+)?)')


def parse_grounded_response(response) -> GroundedResult:
    """Pull a number and any grounding source URLs out of a genai response.

    Deliberately asks for a plain-sentence answer and regexes the number out,
    rather than a forced ``response_schema`` JSON shape: combining grounding
    with structured output is the exact interaction the sibling session
    flagged as unverified in some API versions.
    """

    text = getattr(response, 'text', '') or ''
    match = _NUMBER_PATTERN.search(text.replace('،', ','))
    if not match:
        raise ValueError(f'هیچ عدد قابل‌تشخیصی در پاسخ Gemini پیدا نشد: {text[:200]!r}')
    value = float(match.group(1).replace(',', ''))

    urls: list[str] = []
    candidates = getattr(response, 'candidates', None) or []
    for candidate in candidates:
        grounding = getattr(candidate, 'grounding_metadata', None)
        chunks = getattr(grounding, 'grounding_chunks', None) or [] if grounding else []
        for chunk in chunks:
            web = getattr(chunk, 'web', None)
            uri = getattr(web, 'uri', None) if web else None
            if uri:
                urls.append(uri)
    return GroundedResult(value=value, explanation=text.strip(), source_urls=urls)


@dataclass
class SanityCheckResult:
    engine: str
    plausible: bool | None  # None = engine unreachable/errored, not a disagreement
    note: str


class SanityCheckClient(Protocol):
    def check_plausible(self, value: float, context: str) -> SanityCheckResult: ...


class OpenAICompatibleSanityClient:
    """Asks one OpenAI-compatible engine whether a value looks plausible.

    Never asked to regenerate the number itself -- only to react to a number
    already fetched live by Gemini, per the agreed architecture.
    """

    def __init__(self, engine_name: str, api_key: str, base_url: str, model: str):
        self.engine_name = engine_name
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def check_plausible(self, value: float, context: str) -> SanityCheckResult:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        prompt = (
            f'{context}\nیک منبع مستقل مقدار {value:,.0f} را گزارش کرده است. '
            'آیا این عدد از نظر تو منطقی/محتمل به‌نظر می‌رسد؟ فقط با یکی از دو کلمه '
            '«بله» یا «خیر» و در صورت نیاز یک توضیح کوتاه پاسخ بده.'
        )
        try:
            response = client.chat.completions.create(
                model=self._model, messages=[{'role': 'user', 'content': prompt}], timeout=20,
            )
            text = (response.choices[0].message.content or '').strip()
        except Exception as exc:
            return SanityCheckResult(self.engine_name, None, f'خطا در تماس: {exc}')
        plausible = 'خیر' not in text[:10] and ('بله' in text or 'yes' in text.lower())
        return SanityCheckResult(self.engine_name, plausible, text)


def default_gemini_client(base_dir: str | Path) -> GeminiGroundedClient | None:
    key = cfg('GEMINI_API_KEY', base_dir)
    return GeminiGroundedClient(key) if key else None


def default_sanity_clients(base_dir: str | Path) -> list[OpenAICompatibleSanityClient]:
    clients = []
    for name, model_env, default_model, base_url, key_env in _SANITY_ENGINES:
        key = cfg(key_env, base_dir)
        if key:
            clients.append(OpenAICompatibleSanityClient(name, key, base_url, cfg(model_env, base_dir, default_model)))
    return clients


@dataclass
class ResearchResult:
    value: float
    explanation: str
    source_urls: list[str]
    sanity_checks: list[SanityCheckResult]
    needs_review: bool
    review_reason: str


def fetch_and_verify(prompt: str, context: str, *, gemini_client: GroundedClient,
                      sanity_clients: list[SanityCheckClient]) -> ResearchResult:
    """The whole flow: Gemini fetches the live number, others only sanity-check it.

    ``needs_review`` is set on ANY disagreement (not majority vote) -- for a
    macro parameter every other price in the catalog multiplies against,
    understating risk here is worse than an occasional unnecessary manual
    check.
    """

    grounded = gemini_client.fetch_grounded_value(prompt)
    checks = [client.check_plausible(grounded.value, context) for client in sanity_clients]
    disagreements = [c for c in checks if c.plausible is False]
    needs_review = bool(disagreements)
    reason = ''
    if disagreements:
        names = '، '.join(c.engine for c in disagreements)
        reason = f'عدم توافق موتورهای صحت‌سنجی: {names}'
    return ResearchResult(
        value=grounded.value, explanation=grounded.explanation, source_urls=grounded.source_urls,
        sanity_checks=checks, needs_review=needs_review, review_reason=reason,
    )


# ---------------------------------------------------------------- model roster
#
# «شروع براورد» step ۵ lists every engine this app knows, whether its key is
# configured (فعال/غیرفعال), and lets the operator pick several. Only Gemini
# can search the live web; every other engine can only sanity-check a number
# Gemini found (see the module docstring), so each entry carries its role.

ROLE_SEARCH = 'search'
ROLE_CHECK = 'check'
ROLE_LABELS = {ROLE_SEARCH: 'جستجوی زنده وب', ROLE_CHECK: 'صحت‌سنجی'}

#: ui.json ``price_ai_mode`` -- how step ۵ picks its engines (also offered in تنظیمات).
PRICE_AI_MODES = {
    'AUTO': 'خودکار: جمینای برای جستجو، مدل‌های رایگان برای صحت‌سنجی',
    'ALL_ACTIVE': 'همه مدل‌های فعال (کندتر و پرهزینه‌تر)',
    'SELECTED': 'فقط مدل‌های انتخاب‌شده',
    'GEMINI_ONLY': 'فقط جمینای (بدون صحت‌سنجی)',
    'OFF': 'بدون هوش مصنوعی',
}
DEFAULT_PRICE_AI_MODE = 'AUTO'

_OPENAI_BASE_URL = 'https://api.openai.com/v1'
_BASETEN_BASE_URL = 'https://inference.baseten.co/v1'
_DEFAULT_GEMINI_MODEL = 'gemini-3.6-flash'


@dataclass
class ModelInfo:
    engine_id: str
    label: str
    provider: str
    role: str
    model: str
    base_url: str
    key_env: str
    active: bool
    #: Free-tier engine (OpenRouter/Groq); Baseten and OpenAI bill per token.
    free: bool = False


def _baseten_models() -> dict[str, tuple[str, str]]:
    # The receipt chain owns this roster (keys are per model there); read it
    # instead of keeping a second copy that would drift.
    try:
        from receipt_ai_provider import _BASETEN_MODELS
        return dict(_BASETEN_MODELS)
    except Exception:
        return {}


def model_catalog(base_dir: str | Path) -> list[ModelInfo]:
    """Every engine, in the order step ۵ lists them; ``active`` = its key is configured."""

    def has(key_env: str) -> bool:
        return bool(cfg(key_env, base_dir))

    out = []
    gemini_model = cfg('GEMINI_MODEL', base_dir, _DEFAULT_GEMINI_MODEL)
    out.append(ModelInfo('GEMINI', f'Gemini ({gemini_model})', 'Google', ROLE_SEARCH, gemini_model,
                         '', 'GEMINI_API_KEY', has('GEMINI_API_KEY'), free=True))
    if gemini_model != 'gemini-flash-latest':
        out.append(ModelInfo('GEMINI:gemini-flash-latest', 'Gemini Flash (آخرین نسخه)', 'Google',
                             ROLE_SEARCH, 'gemini-flash-latest', '', 'GEMINI_API_KEY',
                             has('GEMINI_API_KEY'), free=True))
    for name, model_env, default_model, base_url, key_env in _SANITY_ENGINES:
        provider, _sep, tag = name.partition(':')
        out.append(ModelInfo(name, f'{tag.title()} ({provider.title()})', provider.title(), ROLE_CHECK,
                             cfg(model_env, base_dir, default_model), base_url, key_env, has(key_env),
                             free=True))
    for tag, (key_env, default_model) in _baseten_models().items():
        out.append(ModelInfo(f'BASETEN:{tag}', f"{default_model.split('/')[-1]} (Baseten)", 'Baseten',
                             ROLE_CHECK, cfg(f'BASETEN_{tag}_MODEL', base_dir, default_model),
                             _BASETEN_BASE_URL, key_env, has(key_env)))
    out.append(ModelInfo('OPENAI', 'OpenAI', 'OpenAI', ROLE_CHECK,
                         cfg('OPENAI_PRICE_MODEL', base_dir, 'gpt-5.6'), _OPENAI_BASE_URL,
                         'OPENAI_API_KEY', has('OPENAI_API_KEY')))
    return out


def resolve_selection(mode: str, catalog: list[ModelInfo], selected: list[str] | tuple[str, ...]) -> list[str]:
    """The engine ids a run uses under ``mode``; inactive engines never make it in."""

    active = [m for m in catalog if m.active]
    mode = (mode or DEFAULT_PRICE_AI_MODE).upper()
    if mode == 'OFF':
        return []
    if mode == 'GEMINI_ONLY':
        return [m.engine_id for m in active if m.role == ROLE_SEARCH][:1]
    if mode == 'SELECTED':
        chosen = set(selected or ())
        return [m.engine_id for m in active if m.engine_id in chosen]
    if mode == 'ALL_ACTIVE':
        return [m.engine_id for m in active]
    # AUTO: every search engine (the next answers when one fails) plus the
    # free checkers -- the paid ones only when the operator picks them.
    return [m.engine_id for m in active if m.role == ROLE_SEARCH or m.free]


class _FirstWorkingGrounded:
    """Several selected Gemini models: the next one answers when one fails (quota, outage)."""

    def __init__(self, clients: list[GroundedClient]):
        self._clients = clients

    def fetch_grounded_value(self, prompt: str) -> GroundedResult:
        errors = []
        for client in self._clients:
            try:
                return client.fetch_grounded_value(prompt)
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError(' | '.join(errors) or 'هیچ مدل جستجوی زنده‌ای انتخاب نشده است')


def build_clients(base_dir: str | Path, engine_ids: list[str]):
    """(grounded client or None, sanity clients) for the chosen engine ids."""

    by_id = {m.engine_id: m for m in model_catalog(base_dir)}
    grounded, checkers = [], []
    for engine_id in engine_ids:
        info = by_id.get(engine_id)
        if info is None or not info.active:
            continue
        key = cfg(info.key_env, base_dir)
        if info.role == ROLE_SEARCH:
            grounded.append(GeminiGroundedClient(key, info.model))
        else:
            checkers.append(OpenAICompatibleSanityClient(info.label, key, info.base_url, info.model))
    return (_FirstWorkingGrounded(grounded) if grounded else None), checkers


def check_status(base_dir: str | Path) -> dict[str, str]:
    """{engine id: 'ok'|'error'|'no_key'} -- the receipt chain's cheap auth check, reused.

    Blocking (runs its own event loop); call it from a worker thread.
    """

    import asyncio

    from receipt_ai_provider import check_engine_status

    raw = asyncio.run(check_engine_status(base_dir))
    out = {engine_id: entry.get('status', '') for engine_id, entry in raw.items()}
    if 'GEMINI' in out:
        out.setdefault('GEMINI:gemini-flash-latest', out['GEMINI'])
    return out


#: (parameter key, question, context for the checkers) -- the macro
#: parameters step ۵ can research. The copper answer is دلار/تن (London),
#: converted to the project's stored unit by the wizard, same as TGJU's.
RESEARCH_PROMPTS = {
    'usd': ('نرخ امروز دلار آمریکا در بازار آزاد تهران به تومان چقدر است؟ '
            'فقط یک عدد به تومان و منبع را بنویس.',
            'نرخ دلار آزاد تهران به تومان'),
    'copper': ('قیمت امروز مس کاتد در بورس فلزات لندن (LME) به دلار برای هر تن چقدر است؟ '
               'فقط یک عدد به دلار/تن و منبع را بنویس.',
               'قیمت مس LME به دلار بر تن'),
    'wage_annual_growth': ('درصد افزایش حداقل دستمزد مصوب شورای عالی کار ایران برای سال جاری '
                           'چند درصد است؟ فقط یک عدد درصد و منبع را بنویس.',
                           'درصد افزایش سالانه حداقل دستمزد ایران'),
}
