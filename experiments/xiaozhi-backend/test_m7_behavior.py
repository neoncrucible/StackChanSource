from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from kadence_behavior import (
    KADENCE_BEHAVIOR_MAX_CHARS,
    KADENCE_BEHAVIOR_PATH,
    KADENCE_BEHAVIOR_STATE,
    KadenceBehaviorError,
    KadenceBehaviorState,
    get_kadence_behavior_snapshot,
    render_kadence_behavior_prompt,
    start_kadence_behavior_server,
    stop_kadence_behavior_server,
)


def expect(condition, label):
    if not condition:
        raise AssertionError(label)
    print(f"PASS  {label}")


def post_json(url, payload):
    raw = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def get_json(url):
    with urlopen(url, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main():
    local = KadenceBehaviorState()
    expect(local.snapshot()["mode"] == "default", "fresh process state begins DEFAULT")
    expect(local.render("CANONICAL") == "CANONICAL", "DEFAULT leaves canonical prompt byte-for-byte unchanged")

    state = local.set_custom("Be extremely terse.\nUse dry humour.")
    expect(state["mode"] == "custom", "CUSTOM state activates explicitly")
    expect(state["chars"] == len("Be extremely terse.\nUse dry humour."), "CUSTOM character count is exact")

    rendered = local.render("CANONICAL")
    expect(rendered.startswith("CANONICAL\n\n## Temporary Session Behaviour Overlay"), "CUSTOM is appended after canonical prompt")
    expect("Canonical Kadence identity remains authoritative" in rendered, "overlay retains canonical-authority guard")
    expect("This overlay is ACTIVE" in rendered, "active CUSTOM is stated explicitly")
    expect("on every response" in rendered, "CUSTOM applies to every subsequent response")
    expect("more authoritative than earlier assistant wording" in rendered, "CUSTOM outranks prior assistant style")
    expect("prior conversational style" in rendered, "CUSTOM outranks dialogue-history style")
    expect("cannot change safety requirements" in rendered, "overlay explicitly cannot change safety requirements")
    expect("tool availability or schemas" in rendered, "overlay explicitly cannot change tool authority")
    expect("Be extremely terse." in rendered, "operator behaviour text is included")

    local.clear()
    expect(local.snapshot()["mode"] == "default", "DEFAULT action clears CUSTOM")
    expect(local.render("CANONICAL") == "CANONICAL", "DEFAULT restores canonical prompt exactly")

    for invalid, label in [
        ("", "empty CUSTOM fails closed"),
        ("   ", "whitespace CUSTOM fails closed"),
        ("x" * (KADENCE_BEHAVIOR_MAX_CHARS + 1), "overlong CUSTOM fails closed"),
        ("ok\x00bad", "hidden control character fails closed"),
    ]:
        try:
            local.set_custom(invalid)
        except KadenceBehaviorError:
            print(f"PASS  {label}")
        else:
            raise AssertionError(label)

    # Exercise the actual loopback control surface protocol on an ephemeral port.
    KADENCE_BEHAVIOR_STATE.set_custom("stale test state")
    server = start_kadence_behavior_server(host="127.0.0.1", port=0)
    try:
        host, port = server.server_address[:2]
        expect(host == "127.0.0.1", "control server binds loopback only")
        base = f"http://127.0.0.1:{port}{KADENCE_BEHAVIOR_PATH}"

        status, body = get_json(base)
        expect(status == 200, "control GET succeeds")
        expect(body["state"]["mode"] == "default", "server start hard-resets state to DEFAULT")

        status, body = post_json(base, {"mode": "custom", "prompt": "Answer in exactly one sentence."})
        expect(status == 200, "control CUSTOM POST succeeds")
        expect(body["state"]["mode"] == "custom", "control CUSTOM POST activates overlay")
        expect(KADENCE_BEHAVIOR_STATE.get_custom() == "Answer in exactly one sentence.", "HTTP control updates process-owned state")
        snapshot = get_kadence_behavior_snapshot()
        expect(snapshot["mode"] == "custom", "runtime snapshot reports CUSTOM")
        expect(snapshot["chars"] == len("Answer in exactly one sentence."), "runtime snapshot reports CUSTOM character count")

        global_rendered = render_kadence_behavior_prompt("BASE")
        expect(global_rendered.startswith("BASE\n\n## Temporary Session Behaviour Overlay"), "runtime renderer observes live control state")
        expect("more authoritative than earlier assistant wording" in global_rendered, "live runtime renderer carries history-precedence rule")

        status, body = post_json(base, {"mode": "default"})
        expect(status == 200, "control DEFAULT POST succeeds")
        expect(body["state"]["mode"] == "default", "control DEFAULT POST clears overlay")
        expect(get_kadence_behavior_snapshot()["mode"] == "default", "runtime snapshot returns DEFAULT after clear")
        expect(render_kadence_behavior_prompt("BASE") == "BASE", "runtime renderer returns canonical prompt after DEFAULT")

        try:
            post_json(base, {"mode": "custom", "prompt": "x" * (KADENCE_BEHAVIOR_MAX_CHARS + 1)})
        except HTTPError as exc:
            expect(exc.code == 400, "HTTP control rejects overlong CUSTOM")
        else:
            raise AssertionError("HTTP control rejects overlong CUSTOM")

        try:
            post_json(base, {"mode": "invented"})
        except HTTPError as exc:
            expect(exc.code == 400, "HTTP control rejects invented mode")
        else:
            raise AssertionError("HTTP control rejects invented mode")
    finally:
        stop_kadence_behavior_server(server)
        KADENCE_BEHAVIOR_STATE.clear()

    print("M7 deterministic behaviour tests: PASS")


if __name__ == "__main__":
    main()
