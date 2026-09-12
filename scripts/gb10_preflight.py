"""Run inside the OpenShell sandbox to verify the local Qwen inference route."""

from local_narrative import check_local_model


if __name__ == "__main__":
    reply = check_local_model()
    if not reply:
        raise SystemExit("Inference route returned an empty model response.")
    print(f"OpenShell inference.local route responded: {reply}")
