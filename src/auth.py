"""
src/auth.py — Cross-platform Anthropic API key resolver.

Resolution order:
  1. ANTHROPIC_API_KEY environment variable  (preferred for all users)
  2. Hermes auth.json at ~/.hermes/auth.json  (Hermes Agent users only)

Raises a clear RuntimeError with setup instructions if neither is found.
"""

import json
import os
from pathlib import Path


def get_api_key() -> str:
    """
    Resolve the Anthropic API key from the environment or Hermes auth file.

    Returns the key as a plain string. Raises RuntimeError if not found.
    """

    # 1. Environment variable — works everywhere, no Hermes required
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key

    # 2. Hermes auth.json — for users running Hermes Agent locally
    hermes_auth = Path.home() / ".hermes" / "auth.json"
    if hermes_auth.exists():
        try:
            with hermes_auth.open() as f:
                data = json.load(f)
            key = data["credential_pool"]["anthropic"][0]["access_token"]
            if key:
                return key
        except (KeyError, IndexError, json.JSONDecodeError, OSError):
            pass  # fall through to error

    raise RuntimeError(
        "\n"
        "══════════════════════════════════════════════════════\n"
        "  Anthropic API key not found.\n"
        "\n"
        "  Set it as an environment variable before running:\n"
        "\n"
        "    Linux / macOS:\n"
        "      export ANTHROPIC_API_KEY=sk-ant-...\n"
        "\n"
        "    Windows (PowerShell):\n"
        "      $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
        "\n"
        "    Windows (cmd):\n"
        "      set ANTHROPIC_API_KEY=sk-ant-...\n"
        "\n"
        "  Or add it to a .env file and load it with python-dotenv.\n"
        "\n"
        "  Get a key at: https://console.anthropic.com/\n"
        "══════════════════════════════════════════════════════\n"
    )


def get_anthropic_client():
    """Convenience wrapper: return an anthropic.Anthropic client."""
    import anthropic
    return anthropic.Anthropic(api_key=get_api_key())
