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
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"

        self.client = OpenAI(base_url=self.base_url, api_key="ollama")
        self.is_qwen3 = bool(
            self.model_name and self.model_name.lower().startswith("qwen3")
        )
        logger.bind(tag=TAG).info(
            f"KADENCE LOCAL LLM ready: model={self.model_name}, english_voice_guard=true"
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
        }
        if self.is_qwen3:
            # Ollama's OpenAI-compatible endpoint accepts provider-specific
            # request fields through extra_body.
            params["extra_body"] = {"think": False}
        if functions is not None:
            params["tools"] = functions
        return params

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
        responses = self.client.chat.completions.create(
            **self._request_params(dialogue)
        )
        is_active = True
        buffer = ""

        try:
            for chunk in responses:
                try:
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    content = getattr(delta, "content", "") if delta else ""
                    if not content:
                        continue
                    buffer += content
                    text, buffer, is_active = self._consume_text(buffer, is_active)
                    if text:
                        yield text
                except Exception as exc:
                    logger.bind(tag=TAG).error(f"Error processing LOCAL chunk: {exc}")
        finally:
            responses.close()

    def response_with_functions(self, session_id, dialogue, functions=None):
        stream = self.client.chat.completions.create(
            **self._request_params(dialogue, functions=functions)
        )
        is_active = True
        buffer = ""

        try:
            for chunk in stream:
                try:
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    if delta is None:
                        continue

                    tool_calls = getattr(delta, "tool_calls", None)
                    if tool_calls:
                        yield None, tool_calls
                        continue

                    content = getattr(delta, "content", None)
                    if not content:
                        continue
                    buffer += content
                    text, buffer, is_active = self._consume_text(buffer, is_active)
                    if text:
                        yield text, None
                except Exception as exc:
                    logger.bind(tag=TAG).error(
                        f"Error processing LOCAL function chunk: {exc}"
                    )
        finally:
            stream.close()
