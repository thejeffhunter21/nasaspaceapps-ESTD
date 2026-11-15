"""Try real Gemini explanations on the committed results without changing them (A9).

  uv run python scripts/try_ai_explanations.py [--fresh] [--region ID]

Needs GEMINI_API_KEY and GEMINI_MODEL in .env. Sends each region's facts (numbers already
computed by code) to Gemini. See docs/ai.md, "Trying Gemini".
"""

import sys

from dotenv import load_dotenv

from earth_system_trend.ai.ai_trial import main

if __name__ == "__main__":
    load_dotenv()  # only this entry point reads .env; tests call main() directly
    sys.exit(main())
