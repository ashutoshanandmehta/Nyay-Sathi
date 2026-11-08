"""Abuse & security controls: rate limits, cost circuit breakers, upload isolation, and audit logs."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

DISGUISED_EXECUTABLE_PREFIXES = (
    b"MZ",
    b"\x7fELF",
    b"#!",
    b"\xca\xfe\xba\xbe",
    b"PK\x03\x04",
)

DANGEROUS_PDF_TOKENS = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA|RichMedia)\b"
)

SCRIPT_POLYGLOT_RE = re.compile(
    rb"(?:<script\b|javascript:|<\?php|powershell\s+-enc)",
    re.I,
)

POISONED_DOCUMENT_RE = re.compile(
    r"(?:ignore\s+(?:all|previous|prior)\s+instructions|system\s+prompt|developer\s+message|"
    r"act\s+as\s+(?:an?\s+)?(?:lawyer|advocate|system)|override\s+verification|"
    r"cite\s+fake\s+section|do\s+not\s+verify)",
    re.I,
)


def inspect_upload_bytes(data: bytes, filename: str | None = None) -> dict[str, Any]:
    """Isolate and inspect uploaded bytes before extraction; blocks malware/active-content polyglots."""
    name = (filename or "").lower()
    if any(name.endswith(ext) for ext in (".exe", ".bat", ".cmd", ".sh", ".ps1", ".js", ".php", ".dll")):
        raise ValueError("blocked_executable_filename")
    for prefix in DISGUISED_EXECUTABLE_PREFIXES:
        if data.startswith(prefix):
            raise ValueError("blocked_executable_or_archive_payload")
    if SCRIPT_POLYGLOT_RE.search(data[:65536]):
        raise ValueError("blocked_script_polyglot")
    if data.startswith(b"%PDF-") and DANGEROUS_PDF_TOKENS.search(data):
        raise ValueError("blocked_active_pdf_content")
    return {
        "scan_status": "clean_isolated",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def inspect_extracted_text(text: str) -> dict[str, Any]:
    """Detect prompt-injection and poisoned-document payloads without logging document text."""
    zero_width_count = sum(text.count(ch) for ch in ("\u200b", "\u200c", "\u200d", "\ufeff"))
    injection_match = bool(POISONED_DOCUMENT_RE.search(text))
    return {
        "prompt_injection_detected": injection_match or zero_width_count > 25,
        "zero_width_anomalies": zero_width_count > 25,
        "isolation_policy": "untrusted_data_only_never_instructions",
    }


class AbuseController:
    """Sliding-window IP/device/turn rate limiter and model-cost circuit breaker."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self.ip_buckets: dict[str, deque[float]] = defaultdict(deque)
        self.device_buckets: dict[str, deque[float]] = defaultdict(deque)
        self.turn_buckets: dict[str, deque[float]] = defaultdict(deque)
        self.device_calls: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
        self.system_calls: deque[tuple[float, float]] = deque()

    def clear(self) -> None:
        with self._lock:
            self.ip_buckets.clear()
            self.device_buckets.clear()
            self.turn_buckets.clear()
            self.device_calls.clear()
            self.system_calls.clear()

    def _prune(self, bucket: deque[float], cutoff: float) -> None:
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def check_http_rate(
        self,
        *,
        ip_key: str,
        device_key: str | None,
        is_turn_request: bool,
        settings,
    ) -> tuple[bool, str | None]:
        now = self.clock()
        minute_ago = now - 60.0
        with self._lock:
            ip_b = self.ip_buckets[ip_key]
            self._prune(ip_b, minute_ago)
            if len(ip_b) >= settings.requests_per_minute:
                return False, "ip_rate_limit_exceeded"

            if device_key:
                dev_b = self.device_buckets[device_key]
                self._prune(dev_b, minute_ago)
                if len(dev_b) >= settings.device_requests_per_minute:
                    return False, "device_rate_limit_exceeded"

            if is_turn_request:
                t_key = device_key or ip_key
                turn_b = self.turn_buckets[t_key]
                self._prune(turn_b, minute_ago)
                if len(turn_b) >= settings.turn_requests_per_minute:
                    return False, "turn_burst_limit_exceeded"
                turn_b.append(now)

            ip_b.append(now)
            if device_key:
                self.device_buckets[device_key].append(now)
            return True, None

    def check_circuit_breaker(self, owner_id: str, settings) -> tuple[bool, str | None]:
        now = self.clock()
        hour_ago = now - 3600.0
        with self._lock:
            while self.system_calls and self.system_calls[0][0] < hour_ago:
                self.system_calls.popleft()
            dev = self.device_calls[owner_id]
            while dev and dev[0][0] < hour_ago:
                dev.popleft()

            sys_count = len(self.system_calls)
            sys_cost = sum(c for _, c in self.system_calls)
            if sys_count >= settings.system_hourly_model_call_limit:
                return False, "system_model_call_circuit_open"
            if sys_cost >= settings.system_hourly_cost_limit_usd:
                return False, "system_model_cost_circuit_open"

            dev_count = len(dev)
            dev_cost = sum(c for _, c in dev)
            if dev_count >= settings.device_hourly_model_call_limit:
                return False, "device_model_call_circuit_open"
            if dev_cost >= settings.device_hourly_cost_limit_usd:
                return False, "device_model_cost_circuit_open"
            return True, None

    def record_turn_usage(self, owner_id: str, model_calls_count: int, cost_usd: float = 0.0) -> None:
        if model_calls_count <= 0 and cost_usd <= 0:
            return
        now = self.clock()
        per_call = (cost_usd / max(1, model_calls_count)) if cost_usd > 0 else 0.0
        with self._lock:
            for _ in range(max(1, model_calls_count)):
                self.device_calls[owner_id].append((now, per_call))
                self.system_calls.append((now, per_call))

    def snapshot(self) -> dict[str, Any]:
        now = self.clock()
        hour_ago = now - 3600.0
        with self._lock:
            active_sys = [x for x in self.system_calls if x[0] >= hour_ago]
            return {
                "system_hourly_model_calls": len(active_sys),
                "system_hourly_estimated_cost_usd": round(sum(c for _, c in active_sys), 6),
                "tracked_ip_windows": len(self.ip_buckets),
                "tracked_device_windows": len(self.device_buckets),
            }
