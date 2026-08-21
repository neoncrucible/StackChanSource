#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib
import json
import random
import re
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

TTS_BOUNDARY_RE = re.compile(r"[,.;:!?，。；：！？\n]")
PROVIDERS = ("gemini", "luna")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kadence Alpha 2 Milestone 3 controlled LLM benchmark"
    )
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--prompt-pack", required=True)
    parser.add_argument("--persona", required=True)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=1)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected mapping in YAML: {path}")
    return data


def auto_check_response(spec: Dict[str, Any] | None, response: str) -> bool | None:
    if not spec:
        return None
    kind = spec.get("type")
    expected = str(spec.get("value", ""))
    actual = response.strip()
    if kind == "exact":
        return actual == expected
    if kind == "exact_casefold":
        return actual.casefold() == expected.casefold()
    return None


def tts_ready(buffer: str) -> bool:
    return bool(TTS_BOUNDARY_RE.search(buffer))


def run_stream(provider: Any, prompt: str, persona: str) -> Dict[str, Any]:
    dialogue = [
        {"role": "system", "content": persona},
        {"role": "user", "content": prompt},
    ]
    session_id = f"m3-benchmark-{uuid.uuid4().hex}"
    started = time.perf_counter()
    first_text_at = None
    first_tts_at = None
    pieces: List[str] = []
    buffer = ""

    try:
        stream = provider.response(session_id, dialogue)
        for raw in stream:
            if raw is None:
                continue
            if isinstance(raw, tuple):
                raw = raw[0]
            text = str(raw or "")
            if not text:
                continue
            now = time.perf_counter()
            if first_text_at is None:
                first_text_at = now
            pieces.append(text)
            buffer += text
            if first_tts_at is None and tts_ready(buffer):
                first_tts_at = now
        ended = time.perf_counter()
        response = "".join(pieces).strip()
        if first_tts_at is None and response:
            first_tts_at = ended
        return {
            "ok": True,
            "response": response,
            "first_text_ms": (
                round((first_text_at - started) * 1000, 1)
                if first_text_at is not None
                else None
            ),
            "first_tts_ready_ms": (
                round((first_tts_at - started) * 1000, 1)
                if first_tts_at is not None
                else None
            ),
            "completion_ms": round((ended - started) * 1000, 1),
            "chars": len(response),
            "words": len(response.split()),
            "error": None,
        }
    except Exception as exc:
        ended = time.perf_counter()
        return {
            "ok": False,
            "response": "",
            "first_text_ms": None,
            "first_tts_ready_ms": None,
            "completion_ms": round((ended - started) * 1000, 1),
            "chars": 0,
            "words": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def median(values: Iterable[float | None]) -> float | None:
    usable = [float(v) for v in values if v is not None]
    if not usable:
        return None
    return round(statistics.median(usable), 1)


def mean(values: Iterable[float | None]) -> float | None:
    usable = [float(v) for v in values if v is not None]
    if not usable:
        return None
    return round(statistics.fmean(usable), 1)


def build_provider(server_dir: Path, name: str, cfg: Dict[str, Any]) -> Any:
    if str(server_dir) not in sys.path:
        sys.path.insert(0, str(server_dir))
    if name == "gemini":
        module_name = "core.providers.llm.gemini.gemini"
    elif name == "luna":
        module_name = "core.providers.llm.openai.openai"
    else:
        raise ValueError(name)
    module = importlib.import_module(module_name)
    return module.LLMProvider(cfg)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.repeats < 1 or args.repeats > 5:
        raise SystemExit("--repeats must be between 1 and 5")
    if args.warmup < 0 or args.warmup > 3:
        raise SystemExit("--warmup must be between 0 and 3")

    runtime_root = Path(args.runtime_root).resolve()
    output_root = Path(args.output_root).resolve()
    prompt_pack_path = Path(args.prompt_pack).resolve()
    persona_path = Path(args.persona).resolve()

    repo_dir = runtime_root / "xiaozhi-esp32-server"
    server_dir = repo_dir / "main" / "xiaozhi-server"
    config_path = server_dir / "data" / ".config.yaml"

    for required in (server_dir, config_path, prompt_pack_path, persona_path):
        if not required.exists():
            raise SystemExit(f"Required path not found: {required}")

    config = load_yaml(config_path)
    prompt_pack = load_json(prompt_pack_path)
    persona = persona_path.read_text(encoding="utf-8").strip()
    if not persona:
        raise SystemExit("Canonical persona is empty.")
    if not isinstance(prompt_pack, list) or not prompt_pack:
        raise SystemExit("Prompt pack is empty or invalid.")

    llm_cfg = config.get("LLM", {})
    gemini_cfg = llm_cfg.get("GeminiLLM")
    luna_cfg = llm_cfg.get("OpenAILLM")
    if not isinstance(gemini_cfg, dict):
        raise SystemExit("GeminiLLM config block missing.")
    if not isinstance(luna_cfg, dict):
        raise SystemExit("OpenAILLM config block missing.")

    # Never serialize provider configs: they contain local API keys.
    provider_meta = {
        "gemini": {
            "model": gemini_cfg.get("model_name"),
            "reasoning_effort": None,
        },
        "luna": {
            "model": luna_cfg.get("model_name"),
            "reasoning_effort": luna_cfg.get("reasoning_effort"),
        },
    }

    output_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    repo_root = Path(__file__).resolve().parents[3]
    metadata = {
        "run_id": run_id,
        "started_utc": utc_now(),
        "git_head": safe_git_head(repo_root),
        "repeats": args.repeats,
        "warmup_per_provider": args.warmup,
        "persona_file": str(persona_path),
        "prompt_pack_file": str(prompt_pack_path),
        "providers": provider_meta,
        "notes": [
            "Provider-level controlled benchmark; voice transport is not involved.",
            "Both providers receive the same canonical Kadence persona and user prompt.",
            "first_tts_ready_ms is the first streamed chunk completing a punctuation boundary used as a speech-readiness proxy.",
            "Full robot prompt/template and audible latency are validated separately in Stage C.",
            "No API keys are written to benchmark output.",
        ],
    }

    providers = {
        "gemini": build_provider(server_dir, "gemini", gemini_cfg),
        "luna": build_provider(server_dir, "luna", luna_cfg),
    }

    print("Kadence M3 Stage B controlled benchmark")
    print(f"Output: {run_dir}")
    print(
        f"Gemini: {provider_meta['gemini']['model']} | "
        f"Luna: {provider_meta['luna']['model']} reasoning={provider_meta['luna']['reasoning_effort']}"
    )

    if args.warmup:
        print("Warm-up (discarded)...")
        for provider_name in PROVIDERS:
            for _ in range(args.warmup):
                warm = run_stream(
                    providers[provider_name],
                    "Reply with only the word ready.",
                    persona,
                )
                if not warm["ok"]:
                    raise SystemExit(
                        f"{provider_name} warm-up failed: {warm['error']}"
                    )

    rng = random.Random(f"{run_id}:{uuid.uuid4().hex}")
    records: List[Dict[str, Any]] = []

    for prompt_index, item in enumerate(prompt_pack, start=1):
        prompt_id = str(item["id"])
        prompt = str(item["prompt"])
        print(f"[{prompt_index}/{len(prompt_pack)}] {prompt_id}")
        for repeat in range(1, args.repeats + 1):
            order = list(PROVIDERS)
            rng.shuffle(order)
            for provider_name in order:
                result = run_stream(providers[provider_name], prompt, persona)
                record = {
                    "prompt_id": prompt_id,
                    "category": item.get("category"),
                    "prompt": prompt,
                    "repeat": repeat,
                    "provider": provider_name,
                    "model": provider_meta[provider_name]["model"],
                    **result,
                }
                record["auto_check"] = (
                    auto_check_response(item.get("auto_check"), result["response"])
                    if result["ok"]
                    else False
                )
                records.append(record)
                state = "OK" if result["ok"] else "ERROR"
                print(
                    f"  r{repeat} {provider_name:<6} {state:<5} "
                    f"first={result['first_text_ms']}ms "
                    f"tts={result['first_tts_ready_ms']}ms "
                    f"done={result['completion_ms']}ms"
                )
                write_json(
                    run_dir / "results.partial.json",
                    {"metadata": metadata, "records": records},
                )

    metadata["completed_utc"] = utc_now()

    summaries: Dict[str, Dict[str, Any]] = {}
    for provider_name in PROVIDERS:
        rows = [r for r in records if r["provider"] == provider_name]
        successful = [r for r in rows if r["ok"]]
        checked = [r for r in rows if r["auto_check"] is not None]
        summaries[provider_name] = {
            "model": provider_meta[provider_name]["model"],
            "calls": len(rows),
            "successful_calls": len(successful),
            "errors": len(rows) - len(successful),
            "first_text_median_ms": median(r["first_text_ms"] for r in successful),
            "first_text_mean_ms": mean(r["first_text_ms"] for r in successful),
            "first_tts_ready_median_ms": median(
                r["first_tts_ready_ms"] for r in successful
            ),
            "first_tts_ready_mean_ms": mean(
                r["first_tts_ready_ms"] for r in successful
            ),
            "completion_median_ms": median(r["completion_ms"] for r in successful),
            "completion_mean_ms": mean(r["completion_ms"] for r in successful),
            "auto_checks_passed": sum(1 for r in checked if r["auto_check"] is True),
            "auto_checks_total": len(checked),
        }

    mapping = list(PROVIDERS)
    rng.shuffle(mapping)
    blind_map = {"A": mapping[0], "B": mapping[1]}

    first_outputs: Dict[str, Dict[str, str]] = {}
    for item in prompt_pack:
        pid = str(item["id"])
        first_outputs[pid] = {}
        for label, provider_name in blind_map.items():
            match = next(
                (
                    r
                    for r in records
                    if r["prompt_id"] == pid
                    and r["provider"] == provider_name
                    and r["repeat"] == 1
                ),
                None,
            )
            if match and match["ok"]:
                first_outputs[pid][label] = match["response"]
            elif match:
                first_outputs[pid][label] = f"[ERROR: {match['error']}]"
            else:
                first_outputs[pid][label] = "[ERROR: missing result]"

    review_lines = [
        "# Kadence M3 Stage B — Blind Quality Review",
        "",
        "Do not open `blind_mapping.json` until you have judged the answers.",
        "",
        "For each prompt, choose A, B, Tie, or Fail and optionally score:",
        "- answer quality / factual accuracy: 1–5",
        "- canonical Kadence personality: 1–5",
        "- spoken concision: 1–5",
        "- instruction following: 1–5",
        "",
        "Latency is intentionally hidden here so the quality review is not biased by speed.",
        "",
    ]
    for index, item in enumerate(prompt_pack, start=1):
        pid = str(item["id"])
        review_lines += [
            f"## {index}. {pid} — {item.get('category', '')}",
            "",
            f"**Prompt:** {item['prompt']}",
            "",
            f"**Review target:** {item.get('review', '')}",
            "",
            "**A**",
            "",
            first_outputs[pid]["A"] or "[empty response]",
            "",
            "**B**",
            "",
            first_outputs[pid]["B"] or "[empty response]",
            "",
            "**Preference:** ___",
            "",
            "**Notes:** ___",
            "",
        ]

    (run_dir / "blind_review.md").write_text(
        "\n".join(review_lines).rstrip() + "\n", encoding="utf-8"
    )
    write_json(run_dir / "blind_mapping.json", blind_map)
    write_json(
        run_dir / "results.json",
        {"metadata": metadata, "summary": summaries, "records": records},
    )

    with (run_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "provider",
                "model",
                "calls",
                "successful_calls",
                "errors",
                "first_text_median_ms",
                "first_tts_ready_median_ms",
                "completion_median_ms",
                "auto_checks_passed",
                "auto_checks_total",
            ]
        )
        for provider_name in PROVIDERS:
            s = summaries[provider_name]
            writer.writerow(
                [
                    provider_name,
                    s["model"],
                    s["calls"],
                    s["successful_calls"],
                    s["errors"],
                    s["first_text_median_ms"],
                    s["first_tts_ready_median_ms"],
                    s["completion_median_ms"],
                    s["auto_checks_passed"],
                    s["auto_checks_total"],
                ]
            )

    partial = run_dir / "results.partial.json"
    if partial.exists():
        partial.unlink()

    print("")
    print("Stage B run complete.")
    for provider_name in PROVIDERS:
        s = summaries[provider_name]
        print(
            f"{provider_name}: first text median={s['first_text_median_ms']}ms | "
            f"TTS-ready median={s['first_tts_ready_median_ms']}ms | "
            f"completion median={s['completion_median_ms']}ms | "
            f"errors={s['errors']}"
        )
    print(f"Blind review: {run_dir / 'blind_review.md'}")
    print(f"Machine results: {run_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
