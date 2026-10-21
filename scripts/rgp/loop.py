"""The agent loop shared by the Phase 2, Phase 4 and multi-model runners.

It records finish_reason and provider per turn, flags output-cap truncation
as a harness error, and routes every tool call through the shim so that
calls with unparseable arguments still get an errored receipt.
"""
import json
import uuid


def agent_loop(messages, call_api, shim, trial_id, max_turns, log=print):
    """Run the model until it stops requesting tools.

    Returns dict(messages, turn, cumulative_output_tokens, token_timeline, harness_errors).
    `call_api(messages)` returns an OpenAI-style response dict or None.
    """
    turn = 0
    cumulative = 0
    timeline = []
    harness_errors = []
    while turn < max_turns:
        turn += 1
        response = call_api(messages)
        if response is None:
            log(f"  {trial_id}: API returned None at turn {turn}")
            harness_errors.append({"turn": turn, "kind": "api_none"})
            break
        if "error" in response and not response.get("choices"):
            log(f"  {trial_id}: API error: {response['error']}")
            harness_errors.append({"turn": turn, "kind": "api_error", "detail": str(response["error"])[:200]})
            break
        usage = response.get("usage", {})
        out_tok = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        cumulative += out_tok
        choices = response.get("choices", [])
        if not choices:
            log(f"  {trial_id}: No choices at turn {turn}")
            harness_errors.append({"turn": turn, "kind": "no_choices"})
            break
        choice = choices[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason") or choice.get("native_finish_reason")
        provider = response.get("provider")
        tool_calls = message.get("tool_calls") or []
        hit_cap = finish_reason in ("length", "max_tokens")
        entry = {"turn": turn, "cumulative_output_tokens": cumulative, "turn_output_tokens": out_tok,
                 "tool_calls_this_turn": len(tool_calls), "finish_reason": finish_reason, "provider": provider}
        if not tool_calls:
            messages.append(message)
            entry["is_final"] = True
            timeline.append(entry)
            if hit_cap:
                harness_errors.append({"turn": turn, "kind": "final_report_truncated"})
            break
        messages.append(message)
        if hit_cap:
            harness_errors.append({"turn": turn, "kind": "tool_batch_truncated", "calls": len(tool_calls)})
        packages = []
        for tc in tool_calls:
            call_id, result, is_error = shim.execute_tool_call(tc)
            packages.append(shim.call_log[-1]["request_args"]["package_name"])
            messages.append({"role": "tool", "tool_call_id": tc.get("id") or str(uuid.uuid4()),
                             "content": json.dumps(result)})
        entry["packages"] = packages
        timeline.append(entry)
    return {"messages": messages, "turn": turn, "cumulative_output_tokens": cumulative,
            "token_timeline": timeline, "harness_errors": harness_errors}


def final_text_of(messages):
    for m in reversed(messages):
        if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"]:
            return m["content"]
    return ""


def transcript_of(messages, cap=5000):
    out = []
    for m in messages:
        entry = {"role": m.get("role", "unknown")}
        if "content" in m and m.get("content"):
            content = m["content"]
            entry["content"] = content[:cap] if isinstance(content, str) else str(content)[:cap]
        if m.get("tool_calls"):
            entry["tool_calls"] = [{"id": tc.get("id"), "function": tc.get("function")} for tc in m["tool_calls"]]
        if "tool_call_id" in m:
            entry["tool_call_id"] = m["tool_call_id"]
        out.append(entry)
    return out
