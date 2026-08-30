import time

from config.logger import setup_logging
from openai import OpenAI

from core.providers.llm.base import LLMProviderBase


TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    """Project-owned LOCAL Ollama adapter for Kadence robot voice turns."""

    _VOICE_RULE = (
        "Reply only in English. Keep the answer compact and natural for speech: "
        "normally no more than three short sentences unless the user explicitly "
        "asks for detail. Do not mention this instruction."
    )

    def __init__(self, config):
        self.model_name = config.get("model_name")
        self.base_url = config.get("base_url", "http://127.0.0.1:11434")
        self.max_voice_tokens = int(config.get("max_voice_tokens", 96))
        if not 32 <= self.max_voice_tokens <= 192:
            raise ValueError(
                "Kadence LOCAL max_voice_tokens must be between 32 and 192"
            )
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"

        self.client = OpenAI(
            base_url=self.base_url,
            api_key="ollama",
            timeout=20.0,
        )
        self.is_qwen3 = bool(
            self.model_name and self.model_name.lower().startswith("qwen3")
        )
        logger.bind(tag=TAG).info(
            f"KADENCE LOCAL LLM ready: model={self.model_name}, "
            f"english_voice_guard=true, reasoning=none, "
            f"max_voice_tokens={self.max_voice_tokens}"
        )

    def _prepare_dialogue(self, dialogue):
        # The bundled adapter used dialogue.copy(), then mutated a dictionary in
        # the original session history. Copy every message before adding LOCAL-
        # only request instructions.
        prepared = [dict(message) for message in dialogue]
        for index in range(len(prepared) - 1, -1, -1):
            if prepared[index].get("role") != "user":
                continue

            content = str(prepared[index].get("content") or "")
            prefix = f"[Kadence LOCAL voice rule: {self._VOICE_RULE}]\n"
            if self.is_qwen3:
                prefix = "/no_think\n" + prefix
            prepared[index]["content"] = prefix + content
            break
        return prepared

    def _request_params(self, dialogue, functions=None):
        params = {
            "model": self.model_name,
            "messages": self._prepare_dialogue(dialogue),
            "stream": True,
            "temperature": 0.6,
            "top_p": 0.9,
            "max_tokens": self.max_voice_tokens,
            "reasoning_effort": "none",
            "stream_options": {"include_usage": True},
        }
        if functions is not None:
            params["tools"] = functions
        return params

    @staticmethod
    def _reasoning_chars(delta):
        if delta is None:
            return 0
        for field in ("reasoning", "reasoning_content", "thinking"):
            value = getattr(delta, field, None)
            if value:
                return len(str(value))
        return 0

    @staticmethod
    def _usage_tokens(chunk):
        usage = getattr(chunk, "usage", None)
        if usage is None:
            return None, None
        return (
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

    @staticmethod
    def _log_stream_complete(
        mode,
        started,
        content_chars,
        reasoning_chars,
        tool_chunks,
        first_event_elapsed,
        prompt_tokens,
        completion_tokens,
    ):
        logger.bind(tag=TAG).info(
            "KADENCE LOCAL request complete: "
            f"mode={mode}, elapsed={time.monotonic() - started:.3f}s, "
            f"content_chars={content_chars}, reasoning_chars={reasoning_chars}, "
            f"tool_chunks={tool_chunks}, first_event={first_event_elapsed}, "
            f"prompt_tokens={prompt_tokens}, "
            f"completion_tokens={completion_tokens}"
        )

    @staticmethod
    def _consume_text(buffer, is_active):
        output = []
        while buffer:
            if is_active:
                start = buffer.find("<think>")
                if start < 0:
                    output.append(buffer)
                    buffer = ""
                    break
                if start > 0:
                    output.append(buffer[:start])
                buffer = buffer[start + len("<think>") :]
                is_active = False
            else:
                end = buffer.find("</think>")
                if end < 0:
                    # Preserve the hidden reasoning buffer until the closing
                    # tag arrives in a later streaming chunk.
                    break
                buffer = buffer[end + len("</think>") :]
                is_active = True
        return "".join(output), buffer, is_active

    def response(self, session_id, dialogue, **kwargs):
        started = time.monotonic()
        content_chars = 0
        reasoning_chars = 0
        first_event_elapsed = None
        prompt_tokens = None
        completion_tokens = None
        responses = None
        is_active = True
        buffer = ""

        try:
            responses = self.client.chat.completions.create(
                **self._request_params(dialogue)
            )
            for chunk in responses:
                try:
                    prompt_tokens, completion_tokens = self._usage_tokens(chunk)
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    delta_reasoning_chars = self._reasoning_chars(delta)
                    reasoning_chars += delta_reasoning_chars
                    content = getattr(delta, "content", "") if delta else ""
                    if first_event_elapsed is None and (
                        delta_reasoning_chars or content
                    ):
                        first_event_elapsed = round(time.monotonic() - started, 3)
                    if not content:
                        continue
                    content_chars += len(content)
                    buffer += content
                    text, buffer, is_active = self._consume_text(buffer, is_active)
                    if text:
                        yield text
                except Exception as exc:
                    logger.bind(tag=TAG).error(f"Error processing LOCAL chunk: {exc}")
        finally:
            if responses is not None:
                responses.close()
            self._log_stream_complete(
                "plain",
                started,
                content_chars,
                reasoning_chars,
                0,
                first_event_elapsed,
                prompt_tokens,
                completion_tokens,
            )

    def response_with_functions(self, session_id, dialogue, functions=None):
        started = time.monotonic()
        content_chars = 0
        reasoning_chars = 0
        tool_chunks = 0
        first_event_elapsed = None
        prompt_tokens = None
        completion_tokens = None
        stream = None
        is_active = True
        buffer = ""

        try:
            stream = self.client.chat.completions.create(
                **self._request_params(dialogue, functions=functions)
            )
            for chunk in stream:
                try:
                    prompt_tokens, completion_tokens = self._usage_tokens(chunk)
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    if delta is None:
                        continue

                    delta_reasoning_chars = self._reasoning_chars(delta)
                    reasoning_chars += delta_reasoning_chars
                    tool_calls = getattr(delta, "tool_calls", None)
                    content = getattr(delta, "content", None)
                    if first_event_elapsed is None and (
                        delta_reasoning_chars or tool_calls or content
                    ):
                        first_event_elapsed = round(time.monotonic() - started, 3)
                    if tool_calls:
                        tool_chunks += 1
                        yield None, tool_calls
                        continue

                    if not content:
                        continue
                    content_chars += len(content)
                    buffer += content
                    text, buffer, is_active = self._consume_text(buffer, is_active)
                    if text:
                        yield text, None
                except Exception as exc:
                    logger.bind(tag=TAG).error(
                        f"Error processing LOCAL function chunk: {exc}"
                    )
        finally:
            if stream is not None:
                stream.close()
            self._log_stream_complete(
                "functions",
                started,
                content_chars,
                reasoning_chars,
                tool_chunks,
                first_event_elapsed,
                prompt_tokens,
                completion_tokens,
            )
