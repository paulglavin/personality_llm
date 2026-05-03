"""Fire test commands against HA and collect benchmark data from state.

Workflow (run once per model):
  1. In HA, set the conversation model you want to test.
  2. python bench_ha.py --model GPTOSS --headers > results.csv
  3. Change model in HA.
  4. python bench_ha.py --model Gemma4 >> results.csv
  5. Repeat for remaining models.

Requires: pip install httpx
"""

import argparse
import csv
import datetime
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

try:
    from bench_secrets import HA_URL, HA_TOKEN
except ImportError:
    HA_URL   = "http://homeassistant.local:8123"
    HA_TOKEN = ""

AGENT_ID = "conversation.gptoss_2ob_ai_agent"

# Speaker webhook — fires before each command so the personality integration
# resolves the correct per-user config.
WEBHOOK_ID     = "personality_llm_input"
SPEAKER_ID     = "paul"
WEBHOOK_SECRET = ""                        # leave "" if no webhook secret configured

# HA state entity written by the integration after each rephrase.
BENCH_ENTITY = "personality_llm.bench"

# Seconds to wait between queries so HA state from the previous query
# doesn't bleed into the next one's poll window.
PAUSE_BETWEEN_QUERIES = 3.0

QUERIES = {
    "lights_on":  "Turn on the kitchen lights",
    "lights_off": "Turn off all the lights in the Dining Room and Kitchen",
    "weather":    "What's the weather like today?",
    "music":      "Play something by Radiohead in the kitchen",
    "general":    "Tell me something interesting",
}

# ---------------------------------------------------------------------------
# HA API calls
# ---------------------------------------------------------------------------

HEADERS = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}


def send_speaker_webhook(client: httpx.Client) -> None:
    """Fire the speaker identification webhook so HA resolves the right user config."""
    payload: dict = {
        "speaker_id": SPEAKER_ID,
        "confidence": 1.0,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if WEBHOOK_SECRET:
        payload["secret"] = WEBHOOK_SECRET
    try:
        r = client.post(f"{HA_URL}/api/webhook/{WEBHOOK_ID}", json=payload, timeout=5)
        if r.status_code not in (200, 201, 204):
            print(f"    WARNING: webhook returned {r.status_code}", file=sys.stderr)
    except Exception as exc:
        print(f"    WARNING: webhook error: {exc}", file=sys.stderr)


def get_bench_state(client: httpx.Client) -> dict | None:
    """Return the personality_llm.bench state attributes, or None if unavailable."""
    try:
        r = client.get(f"{HA_URL}/api/states/{BENCH_ENTITY}", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def send_command(client: httpx.Client, query: str) -> tuple[str, int]:
    """Returns (spoken response, total latency ms)."""
    t0 = time.monotonic()
    resp = client.post(
        f"{HA_URL}/api/conversation/process",
        json={"text": query, "language": "en", "agent_id": AGENT_ID},
        timeout=60,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    speech = (
        resp.json()
        .get("response", {})
        .get("speech", {})
        .get("plain", {})
        .get("speech", "")
    )
    return speech, latency_ms


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--model",   required=True, help="Model label for this run, e.g. GPTOSS")
    parser.add_argument("--headers", action="store_true", help="Emit CSV header row first")
    parser.add_argument("--debug",   action="store_true", help="Print bench state to stderr after each query")
    args = parser.parse_args()

    writer = csv.writer(sys.stdout)

    if args.headers:
        writer.writerow([
            "local_model",
            "query_label",
            "query_text",
            "original_response",
            "ha_response",
            "total_latency_ms",
            "p1_latency_ms",
            "rephrase_model",
            "personality_prompt_tok",
            "original_tok",
            "rephrase_input_tok",
            "rephrased_tok",
            "rephrase_latency_ms",
            "total_tokens",
        ])

    with httpx.Client(headers=HEADERS) as client:

        for label, query in QUERIES.items():
            print(f"  [{label}] webhook...", end="", flush=True, file=sys.stderr)
            send_speaker_webhook(client)

            # Snapshot ts before sending so we can detect the new state update.
            pre_state = get_bench_state(client)
            pre_ts = (pre_state or {}).get("attributes", {}).get("ts", 0.0)

            print(" sending...", end="", flush=True, file=sys.stderr)
            query_start = time.time()
            speech, total_lat = send_command(client, query)
            print(f" {total_lat}ms", file=sys.stderr)

            # Poll personality_llm.bench until ts is newer than query_start.
            attrs = None
            for attempt in range(10):
                time.sleep(1.0)
                state = get_bench_state(client)
                if state:
                    ts = state.get("attributes", {}).get("ts", 0.0)
                    if ts > pre_ts and ts >= query_start:
                        attrs = state["attributes"]
                        break
                print(f"    (poll {attempt + 1}/10)...", end="", flush=True, file=sys.stderr)

            if args.debug:
                print(f"\n--- DEBUG [{label}] pre_ts={pre_ts:.1f} query_start={query_start:.1f} ---", file=sys.stderr)
                if state:
                    print(f"  state ts={state.get('attributes', {}).get('ts', 'n/a')}  found={attrs is not None}", file=sys.stderr)
                else:
                    print("  state entity not found (404 or missing)", file=sys.stderr)
                print("---\n", file=sys.stderr)

            if attrs:
                p1_lat = max(0, total_lat - attrs["rephrase_latency_ms"])
                writer.writerow([
                    args.model,
                    label,
                    query,
                    attrs.get("original", ""),
                    speech,
                    total_lat,
                    p1_lat,
                    state["state"],          # rephrase_model stored as state value
                    attrs["personality_prompt_tok"],
                    attrs["original_tok"],
                    attrs["rephrase_input_tok"],
                    attrs["rephrased_tok"],
                    attrs["rephrase_latency_ms"],
                    attrs["original_tok"] + attrs["rephrase_input_tok"] + attrs["rephrased_tok"],
                ])
            else:
                print(f"    WARNING: no bench state update seen for [{label}]", file=sys.stderr)
                writer.writerow([args.model, label, query, "", speech, total_lat, "", "", "", "", "", "", "", ""])

            if PAUSE_BETWEEN_QUERIES > 0:
                time.sleep(PAUSE_BETWEEN_QUERIES)

    sys.stdout.flush()


if __name__ == "__main__":
    main()
