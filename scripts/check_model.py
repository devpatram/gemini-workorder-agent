"""Finds a Gemini model that answers in your project and writes it into workorder_agent/.env.

Gemini model versions are retired on a schedule, so check which one answers before you build.
Usage:  python3 scripts/check_model.py              tries the list below, newest first
        python3 scripts/check_model.py MODEL_ID     tries only that model
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from google import genai

CANDIDATES = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
LOCATIONS = ["global", "us-central1"]
ENV = Path(__file__).resolve().parents[1] / "workorder_agent" / ".env"


def project_id() -> str:
    pid = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    if not pid and ENV.exists():
        m = re.search(r"^GOOGLE_CLOUD_PROJECT=(.+)$", ENV.read_text(), re.M)
        pid = m.group(1).strip() if m else ""
    if not pid or pid == "your-project-id":
        pid = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True).stdout.strip()
    return pid


def client(project: str, location: str):
    try:
        return genai.Client(enterprise=True, project=project, location=location)
    except TypeError:  # older google-genai
        return genai.Client(vertexai=True, project=project, location=location)


def save(model: str, location: str) -> None:
    if not ENV.exists():
        print(f"Found {model} at {location}, but {ENV} does not exist yet. Copy .env.example to .env first.")
        return
    text = ENV.read_text()
    for key, value in (("MODEL", model), ("MODEL_LOCATION", location)):
        if re.search(rf"^{key}=.*$", text, re.M):
            text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
        else:
            text += f"\n{key}={value}\n"
    ENV.write_text(text)
    print(f"Saved to {ENV}: MODEL={model}, MODEL_LOCATION={location}")


def main() -> int:
    project = project_id()
    if not project:
        print("No project set. Run: gcloud config set project YOUR_PROJECT_ID")
        return 1
    models = sys.argv[1:] or CANDIDATES
    print(f"Project {project}. Trying {len(models)} model(s) in {', '.join(LOCATIONS)}.")
    first_error = None
    for location in LOCATIONS:
        c = client(project, location)
        for model in models:
            try:
                reply = c.models.generate_content(model=model, contents="Reply with the single word OK.")
                print(f"  yes  {model} at {location}: {(reply.text or '').strip()[:20]}")
                save(model, location)
                return 0
            except Exception as e:  # not found, not enabled, no permission, quota
                msg = " ".join(str(e).split())
                first_error = first_error or msg
                print(f"  no   {model} at {location}: {msg[:110]}")
    print("\nNo model answered. The first error in full:\n" + (first_error or "none"))
    print("If it says default credentials were not found, run: gcloud auth application-default login")
    print("If it says the API is not enabled or permission denied, enable the Agent Platform (Vertex AI) API and wait a minute.")
    print("If every model says not found, open the Agent Platform model versions page and run: python3 scripts/check_model.py <model-id>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
