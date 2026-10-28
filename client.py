"""Client minimale (solo stdlib) per endpoint OpenAI-compatibili: vLLM, SGLang, Ollama, llama.cpp, LM Studio...

Usa lo streaming per misurare TTFT (time to first token), il tempo al primo token di
risposta (dopo il "thinking") e la velocità di decodifica.
"""
import json
import time
import urllib.request
import urllib.error


class ChatClient:
    def __init__(self, base_url, model, api_key=None, timeout=1800):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, path, payload):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        return urllib.request.urlopen(req, timeout=self.timeout)

    def chat(self, messages, temperature=0.6, top_p=0.95, max_tokens=4096, extra_body=None):
        """Restituisce dict con content, reasoning, token e metriche di tempo."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if extra_body:
            payload.update(extra_body)

        content, reasoning = [], []
        usage, finish_reason = {}, None
        t0 = time.perf_counter()
        t_first = t_first_answer = None
        try:
            with self._request("/chat/completions", payload) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        # vLLM recenti usano "reasoning", versioni precedenti "reasoning_content"
                        r = delta.get("reasoning") or delta.get("reasoning_content")
                        c = delta.get("content")
                        if (r or c) and t_first is None:
                            t_first = time.perf_counter()
                        if r:
                            reasoning.append(r)
                        if c:
                            if t_first_answer is None:
                                t_first_answer = time.perf_counter()
                            content.append(c)
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:500]}"}
        except Exception as e:  # timeout, connessione chiusa, ...
            return {"error": f"{type(e).__name__}: {e}"}

        t_end = time.perf_counter()
        completion_tokens = usage.get("completion_tokens", 0)
        decode_time = t_end - (t_first or t_end)
        return {
            "content": "".join(content),
            "reasoning": "".join(reasoning),
            "finish_reason": finish_reason,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": completion_tokens,
            "latency_s": round(t_end - t0, 3),
            "ttft_s": round((t_first or t_end) - t0, 3),
            "time_to_answer_s": round((t_first_answer or t_end) - t0, 3),
            "decode_tok_s": round(completion_tokens / decode_time, 2) if decode_time > 0 else None,
        }
