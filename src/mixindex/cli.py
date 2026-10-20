"""One CLI for preparation, probes, reproducible experiments and artifact sync."""

import argparse
import json
from pathlib import Path
import sys

from .config import load_config, project_root
from .io import read_json, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mixindex")
    parser.add_argument("--root", type=Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe", help="Record actual visible GPU, cgroup and storage limits")
    probe.add_argument("--config", default="configs/base.yaml")
    data = commands.add_parser("data", help="Download, ingest and fully validate source data")
    data.add_argument("action", choices=["prepare", "validate", "publish"])
    data.add_argument("--dataset", required=True)
    data.add_argument("--config", default="configs/base.yaml")
    models = commands.add_parser("models", help="Pin model revisions and smoke validated data")
    models.add_argument("action", choices=["prepare"])
    models.add_argument("--pair", required=True)
    models.add_argument("--dataset", default="fiqa")
    models.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    models.add_argument("--download-only", action="store_true")
    models.add_argument("--config", default="configs/base.yaml")
    sync = commands.add_parser("sync", help="Upload and checksum-verify closed artifacts")
    sync.add_argument("action", nargs="?", choices=["self-test"])
    sync.add_argument("--run-id")
    sync.add_argument("--pending", action="store_true")
    sync.add_argument("--config", default="configs/base.yaml")
    restore = commands.add_parser("restore", help="Restore an immutable receipt from pinned revisions")
    restore.add_argument("--receipt", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True)
    commands.add_parser("status", help="Show local environment, inputs and synchronization status")
    run = commands.add_parser("run", help="Run a stage with hardware and input gates")
    run.add_argument("--experiment", choices=["E0", "E1", "T0"], required=True)
    run.add_argument("--config", required=True)
    run.add_argument("--development-hardware", action="store_true",
                     help="E1 only: label this run diagnostic on other hardware; never certify target gates")
    args = parser.parse_args(argv)
    root = project_root(args.root)
    cfg = load_config(getattr(args, "config", None), root=root)
    try:
        if args.command == "run":
            if args.experiment == "E1":
                from .experiments import run_e1
                result = run_e1(cfg, root, args.development_hardware)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            from .runtime import probe_hardware, require_target_hardware
            require_target_hardware(cfg, probe_hardware())
            raise NotImplementedError("Stage wiring is not yet complete; no gate was certified")
        elif args.command == "probe":
            from .runtime import probe_hardware, probe_storage
            environment = probe_hardware()
            storage = probe_storage(Path(cfg["paths"]["runs"]))
            write_json(Path(cfg["paths"]["state"]) / "environment.json", environment)
            write_json(Path(cfg["paths"]["state"]) / "storage_manifest.json", storage)
            result = {"environment": environment, "storage": storage}
        elif args.command == "data":
            from .data.prepare import prepare_dataset, validate_prepared
            from .data.download import dataset_spec
            if args.action == "publish":
                from .data.publish import publish_dataset
                print(json.dumps(publish_dataset(args.dataset, cfg, root), indent=2))
                return 0
            if args.action == "prepare":
                manifest = prepare_dataset(args.dataset, cfg, root)
            else:
                manifest = validate_prepared(Path(cfg["paths"]["data"]) / "processed" / args.dataset,
                                             dataset_spec(args.dataset, root))
            result = {key: manifest[key] for key in ("dataset_id", "status", "counts", "release_hash")}
        elif args.command == "models":
            from .encoders import build_encoder, model_specs, resolve_model, smoke_encoder
            from .data.prepare import open_validated_data
            specs = {role: resolve_model(spec, cfg["paths"], root)
                     for role, spec in model_specs(args.pair, root).items()}
            result = {role: {"repo_id": spec["repo_id"], "revision": spec["resolved_revision"]}
                      for role, spec in specs.items()}
            if not args.download_only:
                data = open_validated_data(args.dataset, cfg)
                examples = [d.text for d in data.get_documents([0, len(data) // 2, len(data) - 1])]
                for role, spec in specs.items():
                    encoder = build_encoder(spec, args.device, cfg["models"]["batch_size"])
                    try:
                        result[role]["smoke"] = smoke_encoder(encoder, examples)
                    finally:
                        encoder.close()
                write_json(Path(cfg["paths"]["state"]) / f"model-smoke-{args.dataset}-{args.pair}.json", result)
        elif args.command == "sync":
            from .hf_sync import auto_sync_experiment, sync_self_test
            if args.action == "self-test":
                result = sync_self_test(root, cfg)
            elif args.run_id:
                if Path(args.run_id).name != args.run_id:
                    raise ValueError("run-id must be a single path component")
                result = auto_sync_experiment(Path(cfg["paths"]["runs"]) / args.run_id,
                                               cfg["sync"], root, cfg["paths"])
            elif args.pending:
                result = []
                for path in Path(cfg["paths"]["runs"]).glob("*/sync.json"):
                    if read_json(path).get("status") != "VERIFIED":
                        result.append(auto_sync_experiment(path.parent, cfg["sync"], root, cfg["paths"]))
            else:
                parser.error("sync requires self-test, --run-id or --pending")
            items = result if isinstance(result, list) else [result]
            if any(item.get("status") != "VERIFIED" for item in items):
                print(json.dumps(result, indent=2))
                return 2
        elif args.command == "restore":
            from .hf_sync import get_hf_client, restore_run
            api, _ = get_hf_client(root)
            output = restore_run(read_json(args.receipt), args.output, api)
            result = {"status": "RESTORED", "output": str(output)}
        else:
            state = Path(cfg["paths"]["state"])
            result = {"environment": read_json(state / "environment.json")
                      if (state / "environment.json").exists() else None,
                      "prepared": [p.parent.name for p in (Path(cfg["paths"]["data"]) / "processed").glob("*/manifest.json")],
                      "runs": [{"run_id": p.parent.name, **read_json(p)}
                               for p in Path(cfg["paths"]["runs"]).glob("*/summary.json")]}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        # Known local errors may be displayed; network exceptions are reduced to their type.
        message = str(exc) if isinstance(exc, (ValueError, PermissionError, NotImplementedError)) else type(exc).__name__
        print(json.dumps({"status": "FAILED", "error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
