from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_parser import GeminiFinancialParser, SYSTEM_PROMPT
from runtime_base import load_local_secrets


class OpenAIFinancialVisionParser:
    """Optional second Vision provider for receipt extraction.

    It is only activated when OPENAI_API_KEY is configured. The image is sent
    as a base64 data URL through the Responses API. Output is requested as JSON
    and then normalized through the same financial normalization used by the
    Gemini parser so downstream accounting logic is provider-independent.
    """
    def __init__(self, api_key: str, model: str = "gpt-5.6"):
        from openai import AsyncOpenAI
        self._AsyncOpenAI = AsyncOpenAI
        self._api_key = api_key
        self.model=model

    async def analyze(self, *, text: str, image_bytes: bytes | None = None,
                      image_mime_type: str = "image/jpeg", ocr_text: str = "") -> dict[str, Any]:
        if not image_bytes and not (text or ocr_text):
            raise ValueError("Receipt provider needs text or image evidence")
        b64=base64.b64encode(image_bytes).decode("ascii") if image_bytes else ""
        instruction=(
            SYSTEM_PROMPT
            + "\nخروجی را فقط به صورت یک JSON object معتبر و بدون markdown برگردان. "
              "کلیدها همان کلیدهای موتور مالی Peymaan باشند.\n"
            + f"\nکپشن همراه سند:\n{text or '-'}\n"
            + (f"\nOCR محلی کمکی (ممکن است خطا داشته باشد):\n{ocr_text[:12000]}\n" if ocr_text else "")
        )
        # A fresh client per call - see the matching comment in
        # ai_parser.GeminiFinancialParser.analyze(): AsyncOpenAI's async
        # transport binds to whichever event loop is running when first used,
        # and this parser is a long-lived singleton reused across many
        # separate asyncio.run() calls (one per GUI reprocess click).
        client = self._AsyncOpenAI(api_key=self._api_key)
        try:
            content = [{"type": "input_text", "text": instruction}]
            if image_bytes:
                content.append({"type": "input_image", "image_url": f"data:{image_mime_type};base64,{b64}", "detail": "high"})
            response = await client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": content}],
            )
        finally:
            try:
                await client.close()
            except Exception:
                pass
        raw=(response.output_text or "").strip()
        if raw.startswith("```"):
            raw=raw.strip("`").strip()
            if raw.lower().startswith("json"):raw=raw[4:].strip()
        data=json.loads(raw)
        out=GeminiFinancialParser._normalize(data, text=text)
        out["_vision_provider"]="OPENAI"
        return out


class OpenAICompatibleVisionParser:
    """Vision provider for any OpenAI-Chat-Completions-compatible endpoint
    (OpenRouter, Groq, ...). Kept separate from OpenAIFinancialVisionParser
    above because OpenRouter/Groq only support the older Chat Completions API
    (/chat/completions), not OpenAI's own newer Responses API that class uses.
    """
    def __init__(self, api_key: str, model: str, base_url: str):
        from openai import AsyncOpenAI
        self._AsyncOpenAI = AsyncOpenAI
        self._api_key = api_key
        self._base_url = base_url
        self.model = model

    async def analyze(self, *, text: str, image_bytes: bytes | None = None,
                      image_mime_type: str = "image/jpeg", ocr_text: str = "") -> dict[str, Any]:
        if not image_bytes and not (text or ocr_text):
            raise ValueError("Receipt provider needs text or image evidence")
        b64=base64.b64encode(image_bytes).decode("ascii") if image_bytes else ""
        instruction=(
            SYSTEM_PROMPT
            + "\nخروجی را فقط به صورت یک JSON object معتبر و بدون markdown برگردان. "
              "کلیدها همان کلیدهای موتور مالی Peymaan باشند.\n"
            + f"\nکپشن همراه سند:\n{text or '-'}\n"
            + (f"\nOCR محلی کمکی (ممکن است خطا داشته باشد):\n{ocr_text[:12000]}\n" if ocr_text else "")
        )
        # A fresh client per call - see the matching comment on
        # OpenAIFinancialVisionParser.analyze() above.
        client = self._AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        content = [{"type": "text", "text": instruction}]
        if image_bytes:
            content.append({"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{b64}"}})
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": content,
                }],
            )
        finally:
            try:
                await client.close()
            except Exception:
                pass
        raw=(response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw=raw.strip("`").strip()
            if raw.lower().startswith("json"):raw=raw[4:].strip()
        data=json.loads(raw)
        return GeminiFinancialParser._normalize(data, text=text)


# Below this confidence, a provider's own read is treated the same as a
# soft failure: worth trying the next engine, but not worth failing the
# whole item over if nothing does better. Overridable per project via
# ui.json's ai_confidence_threshold (SettingsTab187's AI box) - the operator
# explicitly wants to tune this by feel over time, so 0.85 here is only the
# starting point for a project that has never set it, not a tuned constant.
# (receipt_intelligence.py's own separate vision-retry trigger keeps its own
# unrelated 0.72 cutoff for a single provider's enhanced-image second pass;
# this threshold is specifically about escalating to a *different* engine.)
DEFAULT_CONFIDENCE_ESCALATION_THRESHOLD = 0.85


class ReceiptVisionProviderChain:
    def __init__(self, providers: list[tuple[str, Any]], *,
                 confidence_threshold: float = DEFAULT_CONFIDENCE_ESCALATION_THRESHOLD,
                 stop_on_threshold: bool = True):
        self.providers=providers
        self.confidence_threshold=confidence_threshold
        self.stop_on_threshold=stop_on_threshold
        self.last_provider=""
        self.last_errors: list[str]=[]

    async def analyze(self, **kwargs) -> dict[str, Any]:
        errors=[]
        best_name=""; best_out: dict[str, Any] | None=None; best_confidence=-1.0
        providers = self.providers
        stop_on_threshold = self.stop_on_threshold
        if getattr(self, '_section_settings187', False):
            from ai_section_models187 import section_choice, provider_order
            from v18_store import load_ui
            choice = section_choice('data_entry', load_ui())
            available = dict(self._all_providers187)
            providers = [(name, available[name]) for name in provider_order(choice, list(available), self._automatic_names187)]
            stop_on_threshold = choice['mode'] != 'ALL'
        for name,provider in providers:
            for attempt in range(2):
                try:
                    out=await provider.analyze(**kwargs)
                    out=dict(out);out["_vision_provider"]=name
                    try:
                        confidence=float(out.get("confidence") or 0)
                    except (TypeError, ValueError):
                        confidence=0.0
                    if confidence > best_confidence:
                        best_name, best_out, best_confidence = name, out, confidence
                    if confidence >= self.confidence_threshold and stop_on_threshold:
                        # Cost-conscious mode: stop once the ordered primary
                        # provider has produced a sufficiently confident read.
                        self.last_provider=name;self.last_errors=errors
                        return out
                    errors.append(f"{name}: low confidence {confidence:.2f}, trying next engine")
                    break
                except Exception as exc:
                    msg=f"{exc.__class__.__name__}: {exc}"
                    low=msg.lower()
                    transient=any(token in low for token in (
                        'timeout','timed out','429','rate limit','resource exhausted',
                        '503','502','500','temporarily unavailable','connection reset',
                        'network','service unavailable'
                    ))
                    errors.append(f"{name} attempt {attempt+1}: {msg}")
                    if attempt == 0 and transient:
                        await asyncio.sleep(1.2)
                        continue
                    break
        if best_out is not None:
            # Every engine that answered gave a low-confidence read - use the
            # best of what came back instead of failing the item outright; it
            # still routes to NEEDS_REVIEW downstream on low confidence.
            self.last_provider=best_name;self.last_errors=errors
            return best_out
        self.last_provider="";self.last_errors=errors
        raise RuntimeError(" | ".join(errors) if errors else "No receipt AI provider configured")


def _read_local_secrets(base_dir: str | Path) -> dict[str, Any]:
    return load_local_secrets(base_dir)


_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_BASETEN_BASE_URL = "https://inference.baseten.co/v1"

# Free-tier OpenRouter model ids. QWEN is confirmed live (openrouter.ai's own
# model page at the time this was written). DEEPSEEK/GLM here are the
# original best-guess ids from before Baseten keys existed - kept only as
# manual-picker options now (see _BASETEN_AUTO_CHAIN_TAGS below), no longer
# auto-chain-eligible, since their Baseten equivalents are better-confirmed.
_DEFAULT_OPENROUTER_MODELS = {
    "QWEN": "qwen/qwen2.5-vl-32b-instruct:free",
    "DEEPSEEK": "deepseek/deepseek-v4-flash:free",
    "GLM": "z-ai/glm-4.5v",
}
_DEFAULT_GROQ_LLAMA_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Baseten "Model APIs" catalog (docs.baseten.co/inference/model-apis) - each
# model has its own dedicated secrets.local.json key (unlike OpenRouter/Groq,
# where one key covers every model), confirmed by the operator's own key
# names. Model ids are the best-evidenced ones found (Baseten's own model
# library pages) at the time this was written. Every id below except
# DEEPSEEK (the operator's original, unqualified key - no specific model was
# ever pinned down for it) was subsequently ground-truthed directly from
# Baseten's own per-model code samples in the operator's dashboard
# (2026-09-23) and confirmed correct as written here - DEEPSEEK stays a
# best guess. Overridable per tag via BASETEN_<TAG>_MODEL in
# secrets.local.json regardless, same escape hatch as the OpenRouter ids
# above - a wrong id just makes that one engine fail cleanly; it never
# blocks Gemini or corrupts data.
_BASETEN_MODELS: dict[str, tuple[str, str]] = {
    "DEEPSEEK": ("BASETEN_DEEPSEEK_API_KEY", "deepseek-ai/DeepSeek-V4.1"),
    "DEEPSEEK_V4_PRO": ("BASETEN_DEEPSEEK_V4_PRO_API_KEY", "deepseek-ai/DeepSeek-V4-Pro"),
    "DEEPSEEK_V4_PRO_0813": ("BASETEN_DEEPSEEK_V4_PRO_0813_API_KEY", "deepseek-ai/DeepSeek-V4-Pro-0813"),
    "DEEPSEEK_V41_FLASH": ("BASETEN_DEEPSEEK_V41_FLASH_API_KEY", "deepseek-ai/DeepSeek-V4.1-Flash"),
    "GLM": ("BASETEN_GLM_API_KEY", "zai-org/GLM-5.3"),
    "GLM_FLASH": ("BASETEN_GLM_FLASH_API_KEY", "zai-org/GLM-5.3-Flash"),
    "GLM_FAST": ("BASETEN_GLM_FAST_API_KEY", "zai-org/GLM-5.3-Fast"),
    "KIMI": ("BASETEN_KIMI_API_KEY", "moonshotai/Kimi-K3"),
    "INKLING": ("BASETEN_INKLING_API_KEY", "thinkingmachines/inkling"),
    "INKLING_SMALL": ("BASETEN_INKLING_SMALL_API_KEY", "thinkingmachines/inkling-small"),
}
# Operator's priority call (relayed 2026-09-23): keep the confidence-based
# AUTO-escalation chain small - Baseten is pay-per-token, not free like
# OpenRouter/Groq, and every extra hop adds real cost + latency to a chain
# meant to stop early most of the time. Only these two Baseten models are
# confirmed vision-capable AND auto-chain-eligible; every other Baseten
# model above is still built (when its key exists) so the manual
# per-document engine picker can reach it, just never auto-escalated to.
_BASETEN_AUTO_CHAIN_TAGS = {"DEEPSEEK_V41_FLASH", "GLM_FLASH"}


def build_receipt_vision_parser(base_dir: str | Path, *, gemini_api_key: str, gemini_model: str):
    secrets=_read_local_secrets(base_dir)

    def cfg(name: str, default: str = "") -> str:
        return str(os.getenv(name) or secrets.get(name) or default).strip()

    all_providers: list[tuple[str,Any]]=[]
    auto_chain_names: list[str]=[]

    if gemini_api_key:
        configured=(gemini_model or "gemini-flash-latest").strip()
        try:
            name=f"GEMINI:{configured}"
            all_providers.append((name,GeminiFinancialParser(gemini_api_key,configured)))
            auto_chain_names.append(name)
        except Exception:
            pass

        # Extra Gemini keys (GEMINI_API_KEY_2, _3, ...) - the operator's own
        # free-tier RPM cap was getting maxed out under load on a single key,
        # so these exist for rotation headroom on the SAME model, not a
        # different model/quality tier. '429'/'rate limit' are already in the
        # chain's transient-retry token list, so a capped key naturally falls
        # through to the next Gemini key with no new retry logic needed - just
        # more chain entries. Tried before the same key's own model-alias
        # fallback below: a key that is rate-limited on its configured model
        # is likely rate-limited on any model, so a fresh key is worth trying
        # first. Stops at the first missing number, not a fixed count.
        extra_index = 2
        while True:
            extra_key = cfg(f"GEMINI_API_KEY_{extra_index}")
            if not extra_key:
                break
            try:
                name = f"GEMINI:{configured}#{extra_index}"
                all_providers.append((name, GeminiFinancialParser(extra_key, configured)))
                auto_chain_names.append(name)
            except Exception:
                pass
            extra_index += 1

        if configured != "gemini-flash-latest":
            # Google's rolling Flash alias as a same-key fallback, in case the
            # specifically configured model is unavailable/incompatible.
            try:
                name2="GEMINI:gemini-flash-latest"
                all_providers.append((name2,GeminiFinancialParser(gemini_api_key,"gemini-flash-latest")))
                auto_chain_names.append(name2)
            except Exception:
                pass

    openrouter_key=cfg("OPENROUTER_API_KEY")
    if openrouter_key:
        for tag, default_model in _DEFAULT_OPENROUTER_MODELS.items():
            model=cfg(f"OPENROUTER_{tag}_MODEL", default_model)
            name=f"OPENROUTER:{tag}"
            try:
                all_providers.append((name, OpenAICompatibleVisionParser(openrouter_key, model, _OPENROUTER_BASE_URL)))
                if tag == "QWEN":
                    auto_chain_names.append(name)
            except Exception:
                pass

    for tag, (secret_key, default_model) in _BASETEN_MODELS.items():
        baseten_key=cfg(secret_key)
        if not baseten_key:
            continue
        model=cfg(f"BASETEN_{tag}_MODEL", default_model)
        name=f"BASETEN:{tag}"
        try:
            all_providers.append((name, OpenAICompatibleVisionParser(baseten_key, model, _BASETEN_BASE_URL)))
            if tag in _BASETEN_AUTO_CHAIN_TAGS:
                auto_chain_names.append(name)
        except Exception:
            pass

    groq_key=cfg("GROQ_API_KEY")
    if groq_key:
        model=cfg("GROQ_LLAMA_VISION_MODEL", _DEFAULT_GROQ_LLAMA_VISION_MODEL)
        name="GROQ:LLAMA4"
        try:
            all_providers.append((name, OpenAICompatibleVisionParser(groq_key, model, _GROQ_BASE_URL)))
            auto_chain_names.append(name)
        except Exception:
            pass

    openai_key=cfg("OPENAI_API_KEY")
    if openai_key:
        # Operator's original idea, dropped in favor of the free/cheap roster
        # above - left wired (inactive with no key configured) in case that
        # changes; manual-picker option only, never auto-chain-eligible.
        model=cfg("OPENAI_RECEIPT_MODEL", "gpt-5.6")
        try:all_providers.append(("OPENAI",OpenAIFinancialVisionParser(openai_key,model)))
        except Exception:pass

    # The Settings "AI Machine" box (SettingsTab187 in dashboard_stage18_7.py)
    # writes ai_engine_mode (ALL, or one exact provider name above - a manual
    # override of which engine(s) this project uses) and
    # ai_confidence_threshold (0..1, how confident the primary engine must be
    # before the chain stops instead of escalating) into ui.json. Only
    # consulted when a project context is actually configured (STAGE4_DB_PATH
    # set), so a bare unit test constructing this function directly never
    # touches project storage. Matches this project's established pattern of
    # settings only taking effect on the next full app restart, not live.
    engine_mode = "AUTO"
    confidence_threshold = DEFAULT_CONFIDENCE_ESCALATION_THRESHOLD
    if os.getenv("STAGE4_DB_PATH"):
        try:
            from v18_store import load_ui
            ui = load_ui()
            engine_mode = str(ui.get("ai_engine_mode") or "AUTO").strip().upper()
            raw_threshold = ui.get("ai_confidence_threshold")
            if raw_threshold is not None:
                confidence_threshold = max(0.0, min(float(raw_threshold), 1.0))
        except Exception:
            engine_mode = ""
            confidence_threshold = DEFAULT_CONFIDENCE_ESCALATION_THRESHOLD

    if engine_mode and engine_mode not in {"ALL", "AUTO"}:
        # Manual override reaches any constructed provider, not just the
        # auto-chain subset - e.g. picking a Baseten model that exists only
        # for manual use.
        if engine_mode == "GEMINI":
            selected = [(n, p) for n, p in all_providers if n.startswith("GEMINI:")]
        else:
            selected = [(n, p) for n, p in all_providers if n == engine_mode]
    else:
        by_name = dict(all_providers)
        selected = [(n, by_name[n]) for n in auto_chain_names if n in by_name]

    chain = ReceiptVisionProviderChain(
        selected, confidence_threshold=confidence_threshold,
        stop_on_threshold=(engine_mode != "ALL"),
    )
    chain._all_providers187 = all_providers
    chain._automatic_names187 = auto_chain_names
    chain._section_settings187 = bool(os.getenv('STAGE4_DB_PATH'))
    return chain


async def _check_gemini_key(api_key: str) -> tuple[str, str | None]:
    from google import genai
    client = genai.Client(api_key=api_key)
    try:
        # A models-list call authenticates the key without spending any
        # generation quota - the cheapest real check available.
        await client.aio.models.list(config={"page_size": 1})
        return "ok", None
    except Exception as exc:
        return "error", f"{exc.__class__.__name__}: {exc}"
    finally:
        try:
            await client.aio.aclose()
        except Exception:
            pass


async def _check_openai_compatible_key(api_key: str, base_url: str) -> tuple[str, str | None]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        await client.models.list()
        return "ok", None
    except Exception as exc:
        return "error", f"{exc.__class__.__name__}: {exc}"
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def check_engine_status(base_dir: str | Path) -> dict[str, dict[str, Any]]:
    """On-demand health check, one entry per constructible engine id
    (GEMINI/OPENROUTER:.../BASETEN:.../GROQ:LLAMA4/OPENAI - the same ids
    build_receipt_vision_parser() would use). Each value is
    {"status": "ok"|"error"|"no_key", "detail": str|None, "checked_at": iso str|None}.

    Every check is a cheap models-list auth call, never a real generation/
    vision call, so it costs no meaningful quota - it proves the key
    authenticates, not that any specific model id is currently correct/live.
    An engine with no key configured gets "no_key" with no network call at
    all. This is async (matches every other provider call in this module,
    including tonight's fresh-client-per-call fix) - call it via
    asyncio.run(check_engine_status(base_dir)) from a background thread, the
    same pattern dashboard_stage18_2.reprocess_rows already uses, so it never
    blocks the UI thread.
    """
    secrets=_read_local_secrets(base_dir)

    def cfg(name: str, default: str = "") -> str:
        return str(os.getenv(name) or secrets.get(name) or default).strip()

    def now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    out: dict[str, dict[str, Any]] = {}

    gemini_key = cfg("GEMINI_API_KEY")
    if gemini_key:
        status, detail = await _check_gemini_key(gemini_key)
        out["GEMINI"] = {"status": status, "detail": detail, "checked_at": now()}
    else:
        out["GEMINI"] = {"status": "no_key", "detail": None, "checked_at": None}

    openrouter_key = cfg("OPENROUTER_API_KEY")
    if openrouter_key:
        status, detail = await _check_openai_compatible_key(openrouter_key, _OPENROUTER_BASE_URL)
        checked_at = now()
        for tag in _DEFAULT_OPENROUTER_MODELS:
            out[f"OPENROUTER:{tag}"] = {"status": status, "detail": detail, "checked_at": checked_at}
    else:
        for tag in _DEFAULT_OPENROUTER_MODELS:
            out[f"OPENROUTER:{tag}"] = {"status": "no_key", "detail": None, "checked_at": None}

    groq_key = cfg("GROQ_API_KEY")
    if groq_key:
        status, detail = await _check_openai_compatible_key(groq_key, _GROQ_BASE_URL)
        out["GROQ:LLAMA4"] = {"status": status, "detail": detail, "checked_at": now()}
    else:
        out["GROQ:LLAMA4"] = {"status": "no_key", "detail": None, "checked_at": None}

    # Unlike OpenRouter/Groq, each Baseten model has its own dedicated key,
    # so each gets its own independent check.
    for tag, (secret_key, _default_model) in _BASETEN_MODELS.items():
        baseten_key = cfg(secret_key)
        if baseten_key:
            status, detail = await _check_openai_compatible_key(baseten_key, _BASETEN_BASE_URL)
            out[f"BASETEN:{tag}"] = {"status": status, "detail": detail, "checked_at": now()}
        else:
            out[f"BASETEN:{tag}"] = {"status": "no_key", "detail": None, "checked_at": None}

    return out
