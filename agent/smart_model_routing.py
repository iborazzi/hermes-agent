"""Helpers for smart model routing: Tiered IQ and Failover support."""

from __future__ import annotations
import os
import re
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Zorluk puanı hesaplamak için anahtar kelimeler ve ağırlıkları
_COMPLEXITY_SCORES = {
    "debug": 3, "refactor": 3, "architecture": 4, "optimize": 3,
    "error": 2, "traceback": 3, "exception": 3, "fix": 2,
    "implement": 3, "complex": 2, "benchmark": 3, "kubernetes": 4,
    "docker": 3, "db": 2, "sql": 2, "api": 2
}

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

def _get_complexity_score(text: str) -> int:
    """Mesajın zorluk puanını hesaplar."""
    score = 0
    words = {token.strip(".,:;!?()[]{}\"'`").lower() for token in text.split()}
    for word, weight in _COMPLEXITY_SCORES.items():
        if word in words:
            score += weight
    # Kod bloğu varsa puanı artır
    if "```" in text:
        score += 5
    return score

def choose_smart_route(user_message: str, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Mesajın IQ seviyesine göre rota belirler."""
    if not cfg.get("enabled"): return None

    text = (user_message or "").strip()
    score = _get_complexity_score(text)
    
    # Eşik değer (Threshold): Puan 4'ten büyükse 'High IQ' modele git
    threshold = int(cfg.get("complexity_threshold", 4))
    
    if score >= threshold:
        # High IQ (Pahalı/Akıllı) Rota
        route = dict(cfg.get("high_iq_model", {}))
        route["routing_reason"] = f"high_complexity (score:{score})"
    else:
        # Low IQ (Ucuz/Hızlı) Rota
        route = dict(cfg.get("cheap_model", {}))
        route["routing_reason"] = "simple_task"
    
    return route if route.get("model") else None

def resolve_turn_route(user_message: str, routing_config: Optional[Dict[str, Any]], primary: Dict[str, Any]) -> Dict[str, Any]:
    """Rotayı çözer ve hata durumunda failover yapar."""
    cfg = routing_config or {}
    route = choose_smart_route(user_message, cfg)
    
    # Eğer akıllı rota belirlenemediyse direkt primary (ana) modele git
    target = route if route else primary

    from hermes_cli.runtime_provider import resolve_runtime_provider

    try:
        runtime = resolve_runtime_provider(
            requested=target.get("provider"),
            explicit_base_url=target.get("base_url")
        )
        return {
            "model": target.get("model"),
            "runtime": runtime,
            "label": f"smart route [{target.get('routing_reason', 'manual')}]",
            "signature": (
                target.get("model"),
                target.get("provider"),
                target.get("base_url"),
                target.get("api_mode", "chat_completions"),
            ),
        }
    except Exception as e:
        logger.warning(f"Routing failed, falling back to primary: {e}")
        return {
            "model": primary.get("model"),
            "runtime": primary, 
            "label": "primary (failover mode)",
            "signature": (
                primary.get("model"),
                primary.get("provider"),
                primary.get("base_url"),
                primary.get("api_mode", "chat_completions"),
            ),
        }