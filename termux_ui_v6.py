from __future__ import annotations

import termux_ui_v5 as base

appmod = base.appmod
_original_parse_signal = appmod.parse_signal


def parse_signal_default_10x(text: str) -> dict:
    result = _original_parse_signal(text)
    if str(result.get("leverage_source", "")).lower() == "default":
        result["leverage"] = 10.0
    return result


appmod.parse_signal = parse_signal_default_10x


if __name__ == "__main__":
    appmod.app.run(host="127.0.0.1", port=8501, debug=False)
