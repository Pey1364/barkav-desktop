from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any

from ai_parser import GeminiFinancialParser, SYSTEM_PROMPT


class OpenAIFinancialVisionParser:
    """Optional second Vision provider for receipt extraction.

    It is only activated when OPENAI_API_KEY is configured. The image is sent
    as a base64 data URL through the Responses API. Output is requested as JSON
    and then normalized through the same financial normalization used by the
    Gemini parser so downstream accounting logic is provider-independent.
    """
    def __init__(self, api_key: str, model: str = "gpt-5.6"):
        from openai import AsyncOpenAI
        self.client=AsyncOpenAI(api_key=api_key)
        self.model=model

    async def analyze(self, *, text: str, image_bytes: bytes | None = None,
                      image_mime_type: str = "image/jpeg", ocr_text: str = "") -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("OpenAI receipt provider requires image bytes")
        b64=base64.b64encode(image_bytes).decode("ascii")
        instruction=(
            SYSTEM_PROMPT
            + "\nخروجی را فقط به صورت یک JSON object معتبر و بدون markdown برگردان. "
              "کلیدها همان کلیدهای موتور مالی Peymaan باشند.\n"
            + f"\nکپشن همراه سند:\n{text or '-'}\n"
            + (f"\nOCR محلی کمکی (ممکن است خطا داشته باشد):\n{ocr_text[:12000]}\n" if ocr_text else "")
        )
        response=await self.client.responses.create(
            model=self.model,
            input=[{
                "role":"user",
                "content":[
                    {"type":"input_text","text":instruction},
                    {"type":"input_image","image_url":f"data:{image_mime_type};base64,{b64}","detail":"high"},
                ],
            }],
        )
        raw=(response.output_text or "").strip()
        if raw.startswith("```"):
            raw=raw.strip("`").strip()
            if raw.lower().startswith("json"):raw=raw[4:].strip()
        data=json.loads(raw)
        out=GeminiFinancialParser._normalize(data)
        out["_vision_provider"]="OPENAI"
        return out


class ReceiptVisionProviderChain:
    def __init__(self, providers: list[tuple[str, Any]]):
        self.providers=providers
        self.last_provider=""
        self.last_errors: list[str]=[]

    async def analyze(self, **kwargs) -> dict[str, Any]:
        errors=[]
        for name,provider in self.providers:
            for attempt in range(2):
                try:
                    out=await provider.analyze(**kwargs)
                    self.last_provider=name
                    self.last_errors=errors
                    out=dict(out);out["_vision_provider"]=name
                    return out
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
        self.last_provider="";self.last_errors=errors
        raise RuntimeError(" | ".join(errors) if errors else "No receipt AI provider configured")


def _read_local_secrets(base_dir: str | Path) -> dict[str, Any]:
    p=Path(base_dir)/"secrets.local.json"
    if not p.exists():return {}
    try:
        d=json.loads(p.read_text(encoding="utf-8"));return d if isinstance(d,dict) else {}
    except Exception:return {}


def build_receipt_vision_parser(base_dir: str | Path, *, gemini_api_key: str, gemini_model: str):
    secrets=_read_local_secrets(base_dir)
    providers: list[tuple[str,Any]]=[]
    if gemini_api_key:
        # Try the model copied from V15 first. If that alias is unavailable or
        # temporarily incompatible, use Google's rolling Flash alias as a second
        # provider. Missing SDK does not crash the GUI; diagnostics will expose it.
        configured=(gemini_model or "gemini-flash-latest").strip()
        try:
            providers.append((f"GEMINI:{configured}",GeminiFinancialParser(gemini_api_key,configured)))
            if configured != "gemini-flash-latest":
                providers.append(("GEMINI:gemini-flash-latest",GeminiFinancialParser(gemini_api_key,"gemini-flash-latest")))
        except Exception:
            pass
    openai_key=str(os.getenv("OPENAI_API_KEY") or secrets.get("OPENAI_API_KEY") or "").strip()
    if openai_key:
        model=str(os.getenv("OPENAI_RECEIPT_MODEL") or secrets.get("OPENAI_RECEIPT_MODEL") or "gpt-5.6").strip()
        try:providers.append(("OPENAI",OpenAIFinancialVisionParser(openai_key,model)))
        except Exception:pass
    return ReceiptVisionProviderChain(providers)
