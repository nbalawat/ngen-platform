#!/usr/bin/env python3
"""End-to-end test for the model gateway with real providers.

Tests Anthropic (if ANTHROPIC_API_KEY set) and Ollama (if reachable).
Run directly: uv run python scripts/test_gateway_e2e.py
"""

from __future__ import annotations

import os
import sys

import httpx

GATEWAY_BASE = "http://localhost:8002"


def test_health():
    resp = httpx.get(f"{GATEWAY_BASE}/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    print("[PASS] Health check")


def test_list_models():
    resp = httpx.get(f"{GATEWAY_BASE}/v1/models")
    assert resp.status_code == 200
    models = resp.json()["data"]
    model_ids = [m["id"] for m in models]
    print(f"[INFO] Registered models: {model_ids}")
    assert len(models) > 0, "No models registered"
    print(f"[PASS] List models ({len(models)} registered)")
    return model_ids


def test_ollama_chat(model_id: str = "mistral"):
    """Test Ollama via OpenAI-compatible chat endpoint."""
    print(f"[INFO] Testing Ollama model '{model_id}' via /v1/chat/completions ...")
    resp = httpx.post(
        f"{GATEWAY_BASE}/v1/chat/completions",
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": "Say hello in exactly 3 words."}],
            "max_tokens": 50,
        },
        headers={"x-tenant-id": "e2e-test"},
        timeout=120.0,
    )
    assert resp.status_code == 200, f"Ollama chat failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print(f"[INFO] Ollama response: {content[:100]}")
    print(f"[PASS] Ollama chat completion with '{model_id}'")


def test_anthropic_chat():
    """Test Anthropic via OpenAI-compatible chat endpoint (translated)."""
    print("[INFO] Testing Anthropic via /v1/chat/completions ...")
    resp = httpx.post(
        f"{GATEWAY_BASE}/v1/chat/completions",
        json={
            "model": "claude-haiku-4-5",
            "messages": [
                {"role": "system", "content": "You are helpful. Be very brief."},
                {"role": "user", "content": "What is 2+2? Answer with just the number."},
            ],
            "max_tokens": 50,
        },
        headers={"x-tenant-id": "e2e-test"},
        timeout=30.0,
    )
    assert resp.status_code == 200, f"Anthropic chat failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print(f"[INFO] Anthropic response: {content[:100]}")
    assert "4" in content, f"Expected '4' in response, got: {content}"
    print("[PASS] Anthropic chat completion (OpenAI format)")


def test_anthropic_native():
    """Test Anthropic via native /v1/messages endpoint."""
    print("[INFO] Testing Anthropic via /v1/messages (native) ...")
    resp = httpx.post(
        f"{GATEWAY_BASE}/v1/messages",
        json={
            "model": "claude-haiku-4-5",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": "What is 3+3? Answer with just the number."}],
        },
        headers={"x-tenant-id": "e2e-test"},
        timeout=30.0,
    )
    assert resp.status_code == 200, f"Anthropic native failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    content = data["content"][0]["text"]
    print(f"[INFO] Anthropic native response: {content[:100]}")
    assert "6" in content, f"Expected '6' in response, got: {content}"
    print("[PASS] Anthropic native Messages API")


def test_usage():
    resp = httpx.get(f"{GATEWAY_BASE}/v1/usage/e2e-test")
    assert resp.status_code == 200
    data = resp.json()
    print(f"[INFO] Usage: {data}")
    print(f"[PASS] Usage tracking ({data['request_count']} requests, {data['total_tokens']} tokens, ${data['total_cost']:.6f})")


def main():
    print("=" * 60)
    print("NGEN Model Gateway — End-to-End Tests")
    print("=" * 60)

    test_health()
    model_ids = test_list_models()

    # Ollama tests
    ollama_models = [m for m in model_ids if m in ("mistral", "llama3.2", "phi3")]
    if ollama_models:
        # Use smallest model for speed
        test_model = "mistral" if "mistral" in ollama_models else ollama_models[0]
        test_ollama_chat(test_model)
    else:
        print("[SKIP] No Ollama models available")

    # Anthropic tests
    anthropic_models = [m for m in model_ids if m.startswith("claude-")]
    if anthropic_models:
        test_anthropic_chat()
        test_anthropic_native()
    else:
        print("[SKIP] No Anthropic models registered (set NGEN_GATEWAY_ANTHROPIC_API_KEY)")

    test_usage()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
