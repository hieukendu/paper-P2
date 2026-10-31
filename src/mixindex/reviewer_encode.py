"""Small direct-transformers encoder used by reviewer supplemental jobs.

The production environment has the CUDA/Transformers stack but not the optional
``sentence-transformers`` wrapper.  This keeps the pinned MiniLM/MPNet recipe
identical (mean pooling, attention-mask normalization, float32) while making
the batch size explicit for the visible H100 MIG slice.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer


MODELS = {
    "minilm": {
        "dim": 384,
        "max_tokens": 256,
    },
    "mpnet": {
        "dim": 768,
        "max_tokens": 384,
    },
}


def encode_jsonl(model_name: str, model_path: Path, input_path: Path, output_path: Path, batch_size: int):
    spec = MODELS[model_name]
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModel.from_pretrained(model_path, local_files_only=True).cuda().eval()
    texts = []
    ids = []
    with input_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            ids.append(str(row["id"]))
            texts.append(str(row["text"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    values = np.lib.format.open_memmap(output_path, mode="w+", dtype=np.float32,
                                       shape=(len(texts), spec["dim"]))
    started = time.monotonic()
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            batch_text = texts[start:start + batch_size]
            encoded = tokenizer(batch_text, padding=True, truncation=True,
                                max_length=spec["max_tokens"], return_tensors="pt")
            encoded = {key: value.cuda(non_blocking=True) for key, value in encoded.items()}
            hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp_min(1.0)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            values[start:start + len(batch_text)] = pooled.float().cpu().numpy()
            if start == 0 or (start + len(batch_text)) % max(batch_size * 100, 1024) == 0:
                print(f"{model_name}: {start + len(batch_text)}/{len(texts)}", flush=True)
    values.flush()
    del model
    torch.cuda.empty_cache()
    metadata = {
        "model": model_name,
        "model_path": str(model_path),
        "rows": len(texts),
        "dim": spec["dim"],
        "max_tokens": spec["max_tokens"],
        "batch_size": batch_size,
        "device": torch.cuda.get_device_name(0),
        "elapsed_seconds": time.monotonic() - started,
        "id_order_sha256": __import__("hashlib").sha256("\n".join(ids).encode()).hexdigest(),
    }
    output_path.with_suffix(output_path.suffix + ".json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()
    encode_jsonl(args.model, args.model_path, args.input, args.output, args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
