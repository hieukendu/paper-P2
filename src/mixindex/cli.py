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
    models.add_argument("action", choices=["prepare", "probe"])
    models.add_argument("--pair", required=True)
    models.add_argument("--dataset", default="fiqa")
    models.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    models.add_argument("--download-only", action="store_true")
    models.add_argument("--development-hardware", action="store_true")
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
    run.add_argument("--experiment", choices=["E0", "E1", "CORE_SMOKE", "T0", "E2_PREFLIGHT", "E2", "E4", "E5", "E6", "E7"], required=True)
    run.add_argument("--config", required=True)
    run.add_argument("--development-hardware", action="store_true",
                     help="Label development diagnostics on other hardware; never certify target gates")
    presetup = commands.add_parser("presetup", help="Enqueue the bounded core setup DAG and run ready tasks")
    presetup.add_argument("--scope", default="core",
                          help="core, scale, or case.<dataset>.<model_pair>")
    presetup.add_argument("--config", default="configs/base.yaml")
    presetup.add_argument("--enqueue-only", action="store_true")
    presetup.add_argument("--once", action="store_true")
    presetup.add_argument("--development-hardware", action="store_true")
    plan = commands.add_parser("plan", help="Write the declared exact FiQA experiment matrix without starting it")
    plan.add_argument("--experiment", choices=["E2", "E3", "E4", "E5", "E6", "E7"], required=True)
    plan.add_argument("--config", default="configs/experiments/e2.yaml")
    plan.add_argument("--output", type=Path, default=Path("configs/jobs.yaml"))
    enqueue = commands.add_parser("enqueue", help="Add explicit immutable jobs without executing dependencies")
    enqueue.add_argument("--jobs", type=Path, required=True)
    queue = commands.add_parser("queue", help="Run ready subprocess workers within measured resource limits")
    queue.add_argument("--jobs", type=Path)
    queue.add_argument("--max-compute-jobs", type=int, choices=[1, 2], default=1)
    queue.add_argument("--once", action="store_true")
    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--task-file", type=Path, required=True)
    args = parser.parse_args(argv)
    root = project_root(args.root)
    cfg = load_config(getattr(args, "config", None), root=root)
    try:
        if args.command == "_worker":
            from .queue import run_single
            task = read_json(args.task_file)
            try:
                result = run_single(task, root)
            except Exception as exc:
                result = {"compute_status": "FAILED", "error_type": type(exc).__name__}
            write_json(args.task_file.parent / "result.json", result)
            return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
        if args.command == "plan":
            from .experiments_static import build_static_tasks
            import yaml
            from .io import atomic_bytes
            if args.experiment == "E3":
                from .experiments_systems import build_systems_tasks
                tasks = build_systems_tasks(cfg, root)
            elif args.experiment == "E4":
                from .experiments_e4 import build_scale_tasks
                tasks = build_scale_tasks(cfg, root)
            elif args.experiment == "E5":
                from .experiments_e5 import build_e5_tasks
                tasks = build_e5_tasks(cfg, root)
            elif args.experiment == "E7":
                from .experiments_e7 import build_e7_tasks
                tasks = build_e7_tasks(cfg, root)
            elif args.experiment == "E6":
                from .experiments_e6 import build_e6_tasks
                tasks = build_e6_tasks(cfg, root)
            else:
                tasks = build_static_tasks(cfg, root)
            atomic_bytes(args.output, yaml.safe_dump({"jobs": tasks}, sort_keys=False).encode())
            result = {"output": str(args.output), "tasks": len(tasks), "status": "PLANNED"}
        elif args.command == "presetup":
            from .experiments import build_presetup_tasks
            from .queue import enqueue_tasks, prepare_task, run_queue
            cfg["execution"]["require_target"] = not args.development_hardware
            tasks = [prepare_task(task, root) for task in build_presetup_tasks(args.scope, cfg, root)]
            state = enqueue_tasks(tasks, Path(cfg["paths"]["state"]) / "tasks.json")
            if not args.enqueue_only:
                state = run_queue(cfg, root, once=args.once, only_task_ids={t["task_id"] for t in tasks})
            result = {task["task_id"]: {key: state["tasks"][task["task_id"]].get(key)
                                       for key in ("status", "sync_status", "reason")}
                      for task in tasks}
        elif args.command in {"enqueue", "queue"}:
            from .queue import enqueue_tasks, load_jobs, prepare_task, run_queue
            if args.jobs:
                specs = [prepare_task(task, root) for task in load_jobs(args.jobs)]
                state = enqueue_tasks(specs, Path(cfg["paths"]["state"]) / "tasks.json")
            if args.command == "queue":
                state = run_queue(cfg, root, args.max_compute_jobs, args.once)
            result = {key: {field: row.get(field) for field in
                             ("status", "sync_status", "reason", "pid", "run_dir")}
                       for key, row in state["tasks"].items()}
        elif args.command == "run":
            if args.experiment in {"E2_PREFLIGHT", "E2"}:
                from .experiments_static import run_static_cell, run_static_preflight
                runner = run_static_preflight if args.experiment == "E2_PREFLIGHT" else run_static_cell
                result = runner(cfg, root)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            if args.experiment in {"E0", "E1", "CORE_SMOKE"}:
                from .experiments import run_core_smoke, run_e0, run_e1
                runner = {"E0": run_e0, "E1": run_e1, "CORE_SMOKE": run_core_smoke}[args.experiment]
                result = runner(cfg, root, args.development_hardware)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            if args.experiment == "E4":
                from .experiments_e4 import run_scale_task
                cfg["execution"]["require_target"] = not args.development_hardware
                result = run_scale_task(cfg, root)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            if args.experiment == "E5":
                from .experiments_e5 import run_e5_cell
                cfg["execution"]["require_target"] = not args.development_hardware
                result = run_e5_cell(cfg, root)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            if args.experiment == "E7":
                from .experiments_e7 import run_e7_cell
                cfg["execution"]["require_target"] = not args.development_hardware
                result = run_e7_cell(cfg, root)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            if args.experiment == "E6":
                from .experiments_e6 import run_e6_cell
                cfg["execution"]["require_target"] = not args.development_hardware
                result = run_e6_cell(cfg, root)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
            from .experiments import run_presetup
            cfg["execution"]["require_target"] = not args.development_hardware
            result = run_presetup({"root": str(root)}, {}, cfg)
            print(json.dumps(result, indent=2))
            return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
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
                spec = dataset_spec(args.dataset, root)
                # AOL-IA is intentionally published as a capped temporal
                # release, so the registry's full upstream document count is
                # provenance rather than a local prepared-release expectation.
                expected = None if spec.get("parser") == "aol_recovery" else spec
                manifest = validate_prepared(
                    Path(cfg["paths"]["data"]) / "processed" / args.dataset, expected)
            result = {key: manifest[key] for key in ("dataset_id", "status", "counts", "release_hash")}
        elif args.command == "models":
            if args.action == "probe":
                from .experiments import run_encoder_probes
                result = run_encoder_probes(cfg, root, args.pair, args.dataset, args.device,
                                            args.development_hardware)
                print(json.dumps(result, indent=2))
                return 0 if result["compute_status"] == "COMPUTE_DONE" else 1
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
