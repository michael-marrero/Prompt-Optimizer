"""
Coarse vendor buckets derived from checkpoint / API model strings.

Used for softer embedding-router targets and for aligning baseline evaluation metrics.
"""


def infer_model_vendor_family(model_name: str) -> str:
    name = str(model_name).lower()

    if "qwen" in name:
        return "qwen"
    if "deepseek" in name:
        return "deepseek"
    if "gpt" in name:
        return "gpt"
    if "gemini" in name:
        return "gemini"
    if "internlm" in name or "intern-s1" in name or "intern_s1" in name:
        return "internlm"
    if "granite" in name:
        return "granite"
    if "glm" in name:
        return "glm"
    if "kimi" in name:
        return "kimi"
    if "openrouter" in name:
        return "openrouter"
    if "llama" in name:
        return "llama"
    if "minicpm" in name:
        return "minicpm"
    if "openthinker" in name:
        return "openthinker"
    if "claude" in name:
        return "claude"
    if "mimo" in name:
        return "mimo"
    if "fin-r1" in name or "fin_r1" in name:
        return "fin-r1"
    if "gemma" in name:
        return "gemma"

    return "other"
