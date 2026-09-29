from __future__ import annotations

import re

import termux_ui_v11 as base

appmod = base.appmod
_original_parse_signal = appmod.parse_signal


def _remove_timeframe_annotations(text: str) -> str:
    """Remove timeframe numbers such as 4h/1H/15m before signal parsing.

    Example: "Stop Loss: 1415 (4h close)" must parse SL as 1415, not 4.
    """
    return re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:M|MIN|MINS|MINUTE|MINUTES|H|HR|HRS|HOUR|HOURS|D|DAY|DAYS|W|WK|WEEK|WEEKS)\b",
        " ",
        str(text),
        flags=re.IGNORECASE,
    )


def parse_signal_without_timeframe_numbers(text: str) -> dict:
    return _original_parse_signal(_remove_timeframe_annotations(text))


appmod.parse_signal = parse_signal_without_timeframe_numbers

if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
