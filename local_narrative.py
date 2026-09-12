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
