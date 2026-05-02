from pathlib import Path
import json
import shutil

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from ultralytics import YOLO


WORKSPACE = Path(r"D:/Final year project/user interface")
REPORT_DIR = WORKSPACE / "report_images"
RUNS_DIR = WORKSPACE / "runs" / "detect"
RUN_NAME = "coco_person_motorcycle_val"

COCO_CLASSES = [0, 3]  # 0=person, 3=motorcycle
COCO_CLASS_NAMES = ["person", "motorcycle"]


def resolve_coco_model_path() -> Path:
    candidates = [
        WORKSPACE / "integrate" / "yolov8n.pt",
        WORKSPACE / "backend" / "yolov8n.pt",
        WORKSPACE / "yolov8n.pt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find yolov8n.pt in integrate/, backend/, or workspace root.")


def copy_artifact(run_dir: Path, filename: str, output_name: str) -> str | None:
    source = run_dir / filename
    if not source.exists():
        return None

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    destination = REPORT_DIR / output_name
    shutil.copy2(source, destination)
    return str(destination)


def plot_metric_summary_curve(results_dict: dict, output_path: Path) -> None:
    labels = ["Precision", "Recall", "mAP50", "mAP50-95"]
    values = [
        results_dict.get("metrics/precision(B)"),
        results_dict.get("metrics/recall(B)"),
        results_dict.get("metrics/mAP50(B)"),
        results_dict.get("metrics/mAP50-95(B)"),
    ]

    fig, ax = plt.subplots(figsize=(9.5, 5.8), facecolor="white")
    ax.set_facecolor("white")
    ax.plot(labels, values, marker="o", linewidth=2.4, markersize=7, color="#1f77b4")

    for index, value in enumerate(values):
        if value is None:
            continue
        ax.text(index, value + 0.015, f"{value:.3f}", ha="center", va="bottom", fontsize=10, fontweight="semibold")

    ax.set_title("COCO (Person + Motorcycle) Metric Summary", fontsize=15, fontweight="bold", pad=12)
    ax.set_xlabel("Metric", fontsize=12)
    ax.set_ylabel("Value", fontsize=12)
    ax.set_ylim(0, 1.02)
    ax.grid(True, linestyle="--", alpha=0.45)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_two_class_confusion_matrices(val_results, output_raw: Path, output_norm: Path) -> tuple[bool, bool]:
    cm_obj = getattr(val_results, "confusion_matrix", None)
    matrix = getattr(cm_obj, "matrix", None)

    if matrix is None:
        return False, False

    matrix = np.array(matrix)
    if matrix.ndim != 2:
        return False, False

    # Use class-only block for the requested classes (exclude background row/col).
    sub = matrix[np.ix_(COCO_CLASSES, COCO_CLASSES)]

    fig1, ax1 = plt.subplots(figsize=(6.8, 5.8), facecolor="white")
    ax1.set_facecolor("white")
    sns.heatmap(
        sub,
        annot=True,
        fmt=".0f",
        cmap="Blues",
        cbar=True,
        linewidths=0.6,
        linecolor="white",
        square=True,
        xticklabels=COCO_CLASS_NAMES,
        yticklabels=COCO_CLASS_NAMES,
        ax=ax1,
    )
    ax1.set_title("COCO Confusion Matrix (Person vs Motorcycle)", fontsize=14, fontweight="bold", pad=10)
    ax1.set_xlabel("True Class", fontsize=11)
    ax1.set_ylabel("Predicted Class", fontsize=11)
    fig1.tight_layout()
    fig1.savefig(output_raw, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig1)

    row_sums = sub.sum(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        sub_norm = np.divide(sub, row_sums, where=row_sums > 0)
    sub_norm = np.nan_to_num(sub_norm)

    fig2, ax2 = plt.subplots(figsize=(6.8, 5.8), facecolor="white")
    ax2.set_facecolor("white")
    sns.heatmap(
        sub_norm,
        annot=True,
        fmt=".2f",
        cmap="Blues",
        vmin=0,
        vmax=1,
        cbar=True,
        linewidths=0.6,
        linecolor="white",
        square=True,
        xticklabels=COCO_CLASS_NAMES,
        yticklabels=COCO_CLASS_NAMES,
        ax=ax2,
    )
    ax2.set_title("COCO Confusion Matrix Normalized (Person vs Motorcycle)", fontsize=14, fontweight="bold", pad=10)
    ax2.set_xlabel("True Class", fontsize=11)
    ax2.set_ylabel("Predicted Class", fontsize=11)
    fig2.tight_layout()
    fig2.savefig(output_norm, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig2)

    return True, True


def main() -> None:
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font_scale=1.1,
        rc={
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "grid.color": "#d0d0d0",
            "grid.linestyle": "--",
            "grid.alpha": 0.5,
        },
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = resolve_coco_model_path()
    print(f"Using COCO model: {model_path}")
    print("Running validation only (no retraining) for classes: person, motorcycle")

    model = YOLO(str(model_path))
    try:
        val_results = model.val(
            data="coco128.yaml",
            classes=COCO_CLASSES,
            imgsz=640,
            batch=16,
            workers=0,
            device="cpu",
            project=str(RUNS_DIR),
            name=RUN_NAME,
            exist_ok=True,
            plots=True,
            verbose=True,
        )
    except Exception as exc:
        print("Validation failed before generating artifacts.")
        print(f"Reason: {exc}")
        print("Tip: Ensure internet access for coco128 download, or provide a local COCO-format data YAML.")
        raise

    save_dir = Path(val_results.save_dir)
    results_dict = val_results.results_dict if isinstance(val_results.results_dict, dict) else {}

    artifact_map = {
        "confusion_matrix.png": "coco_person_motorcycle_confusion_matrix.png",
        "confusion_matrix_normalized.png": "coco_person_motorcycle_confusion_matrix_normalized.png",
        "BoxP_curve.png": "coco_person_motorcycle_precision_curve.png",
        "BoxR_curve.png": "coco_person_motorcycle_recall_curve.png",
        "BoxPR_curve.png": "coco_person_motorcycle_pr_curve.png",
        "BoxF1_curve.png": "coco_person_motorcycle_f1_curve.png",
    }

    copied = {}
    for src_name, dst_name in artifact_map.items():
        copied_path = copy_artifact(save_dir, src_name, dst_name)
        copied[src_name] = copied_path
        if copied_path:
            print(f"Saved: {copied_path}")
        else:
            print(f"Missing from run dir: {src_name}")

    summary_curve = REPORT_DIR / "coco_person_motorcycle_metric_summary_curve.png"
    plot_metric_summary_curve(results_dict, summary_curve)
    print(f"Saved: {summary_curve}")

    two_class_raw = REPORT_DIR / "coco_person_motorcycle_confusion_matrix_2class.png"
    two_class_norm = REPORT_DIR / "coco_person_motorcycle_confusion_matrix_2class_normalized.png"
    raw_ok, norm_ok = plot_two_class_confusion_matrices(val_results, two_class_raw, two_class_norm)
    if raw_ok:
        print(f"Saved: {two_class_raw}")
    else:
        print("Could not generate 2-class raw confusion matrix from validation object.")
    if norm_ok:
        print(f"Saved: {two_class_norm}")
    else:
        print("Could not generate 2-class normalized confusion matrix from validation object.")

    manifest = {
        "model_path": str(model_path),
        "classes": COCO_CLASS_NAMES,
        "class_ids": COCO_CLASSES,
        "validation_data": "coco128.yaml",
        "run_dir": str(save_dir),
        "metrics": {
            "precision": results_dict.get("metrics/precision(B)"),
            "recall": results_dict.get("metrics/recall(B)"),
            "mAP50": results_dict.get("metrics/mAP50(B)"),
            "mAP50-95": results_dict.get("metrics/mAP50-95(B)"),
        },
        "artifacts": copied,
        "custom_artifacts": {
            "metric_summary_curve": str(summary_curve),
            "confusion_matrix_2class": str(two_class_raw) if raw_ok else None,
            "confusion_matrix_2class_normalized": str(two_class_norm) if norm_ok else None,
        },
        "note": "Generated from validation-only run (no retraining).",
    }

    manifest_path = REPORT_DIR / "coco_person_motorcycle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved: {manifest_path}")


if __name__ == "__main__":
    main()