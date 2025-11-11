import uuid

__all__ = ["gen_id"]

def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
