"""Shared runtime provider resolution for CLI, gateway, cron, and helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from hermes_cli import auth as auth_mod
from hermes_cli.auth import (
    AuthError,
    PROVIDER_REGISTRY,
    format_auth_error,
    resolve_provider,
    resolve_nous_runtime_credentials,
    resolve_codex_runtime_credentials,
    resolve_api_key_provider_credentials,
    resolve_external_process_provider_credentials,
)
from hermes_cli.config import load_config
from hermes_constants import OPENROUTER_BASE_URL


def _normalize_custom_provider_name(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _auto_detect_local_model(base_url: str) -> str:
    """Query a local server for its model name when only one model is loaded."""
    if not base_url:
        return ""
    try:
        import requests
        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url += "/v1"
        resp = requests.get(url + "/models", timeout=5)
        if resp.ok:
            models = resp.json().get("data", [])
            if len(models) == 1:
                model_id = models[0].get("id", "")
                if model_id:
                    return model_id
    except Exception:
        pass
    return ""


def _get_model_config() -> Dict[str, Any]:
    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        cfg = dict(model_cfg)
        default = cfg.get("default", "").strip()
        base_url = cfg.get("base_url", "").strip()
        is_local = "localhost" in base_url or "127.0.0.1" in base_url
        is_fallback = not default or default == "anthropic/claude-opus-4.6"
        if is_local and is_fallback and base_url:
            detected = _auto_detect_local_model(base_url)
            if detected:
                cfg["default"] = detected
        return cfg
    if isinstance(model_cfg, str) and model_cfg.strip():
        return {"default": model_cfg.strip()}
    return {}


def _copilot_runtime_api_mode(model_cfg: Dict[str, Any], api_key: str) -> str:
    configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
    if configured_mode:
        return configured_mode

    model_name = str(model_cfg.get("default") or "").strip()
    if not model_name:
        return "chat_completions"

    try:
        from hermes_cli.models import copilot_model_api_mode

        return copilot_model_api_mode(model_name, api_key=api_key)
    except Exception:
        return "chat_completions"


_VALID_API_MODES = {"chat_completions", "codex_responses", "anthropic_messages"}


def _parse_api_mode(raw: Any) -> Optional[str]:
    """Validate an api_mode value from config. Returns None if invalid."""
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in _VALID_API_MODES:
            return normalized
    return None


def resolve_requested_provider(requested: Optional[str] = None) -> str:
    """Resolve provider request from explicit arg, config, then env."""
    if requested and requested.strip():
        return requested.strip().lower()

    model_cfg = _get_model_config()
    cfg_provider = model_cfg.get("provider")
    if isinstance(cfg_provider, str) and cfg_provider.strip():
        return cfg_provider.strip().lower()

    env_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip().lower()
    if env_provider:
        return env_provider

    return "auto"


def _get_named_custom_provider(requested_provider: str) -> Optional[Dict[str, Any]]:
    requested_norm = _normalize_custom_provider_name(requested_provider or "")
    if not requested_norm or requested_norm == "custom":
        return None

    if requested_norm == "auto":
        return None
    if not requested_norm.startswith("custom:"):
        try:
            auth_mod.resolve_provider(requested_norm)
        except AuthError:
            pass
        else:
            return None

    config = load_config()
    custom_providers = config.get("custom_providers")
    if not isinstance(custom_providers, list):
        return None

    for entry in custom_providers:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        base_url = entry.get("base_url")
        if not isinstance(name, str) or not isinstance(base_url, str):
            continue
        name_norm = _normalize_custom_provider_name(name)
        menu_key = f"custom:{name_norm}"
        if requested_norm not in {name_norm, menu_key}:
            continue
        result = {
            "name": name.strip(),
            "base_url": base_url.strip(),
            "api_key": str(entry.get("api_key", "") or "").strip(),
        }
        api_mode = _parse_api_mode(entry.get("api_mode"))
        if api_mode:
            result["api_mode"] = api_mode
        return result

    return None


def _resolve_named_custom_runtime(
    *,
    requested_provider: str,
    explicit_api_key: Optional[str] = None,
    explicit_base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    custom_provider = _get_named_custom_provider(requested_provider)
    if not custom_provider:
        return None

    base_url = (
        (explicit_base_url or "").strip()
        or custom_provider.get("base_url", "")
    ).rstrip("/")
    if not base_url:
        return None

    api_key = (
        (explicit_api_key or "").strip()
        or custom_provider.get("api_key", "")
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )

    return {
        "provider": "openrouter",
        "api_mode": custom_provider.get("api_mode", "chat_completions"),
        "base_url": base_url,
        "api_key": api_key,
        "source": f"custom_provider:{custom_provider.get('name', requested_provider)}",
    }


def _resolve_openrouter_runtime(
    *,
    requested_provider: str,
    explicit_api_key: Optional[str] = None,
    explicit_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    model_cfg = _get_model_config()
    cfg_base_url = model_cfg.get("base_url") if isinstance(model_cfg.get("base_url"), str) else ""
    cfg_provider = model_cfg.get("provider") if isinstance(model_cfg.get("provider"), str) else ""
    cfg_api_key = ""
    for k in ("api_key", "api"):
        v = model_cfg.get(k)
        if isinstance(v, str) and v.strip():
            cfg_api_key = v.strip()
            break
    requested_norm = (requested_provider or "").strip().lower()
    cfg_provider = cfg_provider.strip().lower()

    env_openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    env_openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "").strip()

    use_config_base_url = False
    if cfg_base_url.strip() and not explicit_base_url:
        if requested_norm == "auto":
            if (not cfg_provider or cfg_provider == "auto") and not env_openai_base_url:
                use_config_base_url = True
        elif requested_norm == "custom" and cfg_provider == "custom":
            use_config_base_url = True

    skip_openai_base = requested_norm == "openrouter"

    base_url = (
        (explicit_base_url or "").strip()
        or (cfg_base_url.strip() if use_config_base_url else "")
        or ("" if skip_openai_base else env_openai_base_url)
        or env_openrouter_base_url
        or OPENROUTER_BASE_URL
    ).rstrip("/")

    _is_openrouter_url = "openrouter.ai" in base_url
    if _is_openrouter_url:
        api_key = (
            explicit_api_key
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
    else:
        api_key = (
            explicit_api_key
            or (cfg_api_key if use_config_base_url else "")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or ""
        )

    source = "explicit" if (explicit_api_key or explicit_base_url) else "env/config"

    return {
        "provider": "openrouter",
        "api_mode": _parse_api_mode(model_cfg.get("api_mode")) or "chat_completions",
        "base_url": base