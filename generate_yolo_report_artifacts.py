from pathlib import Path
import json

from ultralytics import YOLO


WORKSPACE = Path(r"D:/Final year project/user interface")
REPORT_DIR = WORKSPACE / "report_images"

HELMET_MODEL = WORKSPACE / "models" / "helmet" / "best.pt"
LICENSE_MODEL = WORKSPACE / "models" / "license" / "best.pt"


def _read_model_metrics(model_path: Path) -> dict:
    if not model_path.exists():
        return {
            "model_path": str(model_path),
            "exists": False,
            "error": "Model file not found",
        }

    model = YOLO(str(model_path))
    ckpt = model.ckpt if isinstance(model.ckpt, dict) else {}
    train_metrics = ckpt.get("train_metrics", {}) or {}
    train_results = ckpt.get("train_results", {}) or {}

    def last_metric(metric_key: str):
        values = train_results.get(metric_key)
        if isinstance(values, list) and values:
            return values[-1]
        return None

    return {
        "model_path": str(model_path),
        "exists": True,
        "classes": model.names,
        "checkpoint_epoch_field": ckpt.get("epoch"),
        "checkpoint_best_fitness_field": ckpt.get("best_fitness"),
        "train_metrics": {
            "precision": train_metrics.get("metrics/precision(B)"),
            "recall": train_metrics.get("metrics/recall(B)"),
            "mAP50": train_metrics.get("metrics/mAP50(B)"),
            "mAP50_95": train_metrics.get("metrics/mAP50-95(B)"),
            "fitness": train_metrics.get("fitness"),
        },
        "last_epoch_metrics_from_train_results": {
            "precision": last_metric("metrics/precision(B)"),
            "recall": last_metric("metrics/recall(B)"),
            "mAP50": last_metric("metrics/mAP50(B)"),
            "mAP50_95": last_metric("metrics/mAP50-95(B)"),
        },
    }


def _save_human_readable(report: dict, out_file: Path) -> None:
    lines = []
    lines.append("YOLO Metrics From best.pt (No Retraining)")
    lines.append("=" * 44)

    for model_key in ("helmet", "license"):
        block = report[model_key]
        lines.append("")
        lines.append(f"[{model_key.upper()} MODEL]")
        lines.append(f"Path: {block.get('model_path')}")
        lines.append(f"Exists: {block.get('exists')}")

        if not block.get("exists"):
            lines.append(f"Error: {block.get('error')}")
            continue

        tm = block.get("train_metrics", {})
        lines.append("Train Metrics:")
        lines.append(f"  Precision : {tm.get('precision')}")
        lines.append(f"  Recall    : {tm.get('recall')}")
        lines.append(f"  mAP50     : {tm.get('mAP50')}")
        lines.append(f"  mAP50-95  : {tm.get('mAP50_95')}")
        lines.append(f"  Fitness   : {tm.get('fitness')}")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "source": "checkpoint train_metrics/train_results embedded in best.pt",
        "note": "No dataset validation or retraining executed.",
        "helmet": _read_model_metrics(HELMET_MODEL),
        "license": _read_model_metrics(LICENSE_MODEL),
    }

    json_file = REPORT_DIR / "yolo_metrics_from_bestpt.json"
    txt_file = REPORT_DIR / "yolo_metrics_from_bestpt.txt"

    json_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _save_human_readable(report, txt_file)

    print(f"Saved: {json_file}")
    print(f"Saved: {txt_file}")
    print("\nHelmet metrics:")
    print(report["helmet"].get("train_metrics"))
    print("\nLicense metrics:")
    print(report["license"].get("train_metrics"))


if __name__ == "__main__":
    main()
