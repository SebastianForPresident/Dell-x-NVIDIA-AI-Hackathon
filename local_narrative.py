"""Optional report wording through OpenShell's locally routed inference endpoint."""

import json
import urllib.request


def _local_chat(system: str, user: str, max_tokens: int = 450) -> str:
    payload = {"messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "max_tokens": max_tokens, "temperature": 0}
    request = urllib.request.Request(
        "https://inference.local/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    return result["choices"][0]["message"]["content"].strip()


def extract_claim_fields(claim_text: str) -> str:
    """Return model suggestions as text; the adjuster verifies entries in the form."""
    return _local_chat(
        "Extract only explicit facts from the supplied claim text. Return concise JSON with keys claim_id, "
        "reported_cause, reported_loss_date, claimed_crop, and evidence_quotes. Use null for absent facts. "
        "Date must be YYYY-MM-DD only if unambiguous. Do not infer missing fields or decide the claim.",
        claim_text[:16000],
        max_tokens=350,
    )


def check_local_model() -> str:
    """Smoke test OpenShell's configured inference route."""
    return _local_chat(
        "Reply with exactly LOCAL_MODEL_READY.",
        "Check the local inference route.",
        max_tokens=80,
    )


def write_narrative(report: dict) -> str:
    return _local_chat(
        "You write concise crop insurance evidence summaries for a human adjuster. Use only the supplied "
        "structured findings. Distinguish supported, contradicted, inconclusive and unavailable. "
        "Never approve or deny a claim, infer causation, or invent data. Mention that the evidence is not a coverage determination.",
        json.dumps(report, separators=(",", ":")),
    )


def analyze_structured_case(case: dict) -> dict:
    """Ask local Qwen for a short review of measured, locally stored case data."""
    payload = {
        "claim": {key: case.get(key) for key in ("id", "crop", "cause", "loss_date", "location")},
        "weather_series": case.get("weather_series", []),
        "ndvi_series": case.get("ndvi_series", []),
        "measured_findings": case["report"]["findings"],
        "synthetic_demo": case.get("synthetic_demo", False),
    }
    answer = _local_chat(
        "You assist a crop insurance adjuster. Review only the supplied structured local data. "
        "Return one JSON object with exactly five short string fields: weather, vegetation, crop, "
        "neighbors, overall. Explain what each finding does and does not support. If evidence is "
        "missing or inconclusive, say so. Do not invent measurements, confidence scores, weather "
        "sources, causes, or claim decisions. Do not approve or deny the claim. Output JSON only.",
        json.dumps(payload, separators=(",", ":")),
        max_tokens=900,
    )
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json.loads(cleaned)
    keys = ("weather", "vegetation", "crop", "neighbors", "overall")
    if not isinstance(result, dict) or any(not isinstance(result.get(key), str) or not result[key].strip() for key in keys):
        raise ValueError("Qwen did not return all five evidence summaries")
    return {key: result[key].strip()[:1200] for key in keys}
