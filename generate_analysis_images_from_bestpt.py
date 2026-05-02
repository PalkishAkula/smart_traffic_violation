from pathlib import Path
import json

import matplotlib.pyplot as plt
import seaborn as sns
from ultralytics import YOLO


WORKSPACE = Path(r"D:/Final year project/user interface")
REPORT_DIR = WORKSPACE / "report_images"

MODEL_PATHS = {
    "helmet": WORKSPACE / "models" / "helmet" / "best.pt",
    "license": WORKSPACE / "models" / "license" / "best.pt",
}

METRIC_KEYS = {
    "metrics/precision(B)": "Precision",
    "metrics/recall(B)": "Recall",
    "metrics/mAP50(B)": "mAP50",
    "metrics/mAP50-95(B)": "mAP50-95",
}

METRIC_COLORS = {
    "Precision": "#1f77b4",
    "Recall": "#ff7f0e",
    "mAP50": "#2ca02c",
    "mAP50-95": "#d62728",
}


def load_model_metrics(model_path: Path) -> dict:
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    model = YOLO(str(model_path))
    ckpt = model.ckpt if isinstance(model.ckpt, dict) else {}
    train_results = ckpt.get("train_results", {}) or {}
    train_metrics = ckpt.get("train_metrics", {}) or {}

    epochs = train_results.get("epoch", [])
    if not isinstance(epochs, list) or not epochs:
        epochs = list(range(1, 2))

    curves = {}
    for metric_key, metric_label in METRIC_KEYS.items():
        values = train_results.get(metric_key)
        if isinstance(values, list) and values:
            curves[metric_label] = values
        else:
            final_value = train_metrics.get(metric_key)
            if final_value is not None:
                curves[metric_label] = [final_value for _ in epochs]

    finals = {
        "Precision": train_metrics.get("metrics/precision(B)"),
        "Recall": train_metrics.get("metrics/recall(B)"),
        "mAP50": train_metrics.get("metrics/mAP50(B)"),
        "mAP50-95": train_metrics.get("metrics/mAP50-95(B)"),
    }

    return {
        "model_path": str(model_path),
        "class_names": model.names,
        "epochs": epochs,
        "curves": curves,
        "finals": finals,
    }


def plot_metric_curves(model_name: str, payload: dict) -> Path:
    epochs = payload["epochs"]
    curves = payload["curves"]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="white")
    ax.set_facecolor("white")

    for metric_label, values in curves.items():
        length = min(len(epochs), len(values))
        x = epochs[:length]
        y = values[:length]
        ax.plot(
            x,
            y,
            linewidth=2.2,
            marker="o",
            markersize=4,
            label=metric_label,
            color=METRIC_COLORS.get(metric_label),
        )

    ax.set_title(f"{model_name.capitalize()} Model Metrics Across Epochs", fontsize=16, fontweight="bold", pad=14)
    ax.set_xlabel("Epoch", fontsize=12)
    ax.set_ylabel("Metric Value", fontsize=12)
    ax.set_ylim(0, 1.02)
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.legend(title="Metric", fontsize=10, title_fontsize=10, frameon=True)

    fig.tight_layout()
    output_path = REPORT_DIR / f"{model_name}_precision_recall_map_curves.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def build_estimated_confusion_matrix(precision: float, recall: float, positives: int = 1000, negatives: int = 1000) -> list[list[int]]:
    if precision is None or recall is None:
        return [[0, 0], [0, 0]]

    tp = int(round(recall * positives))
    fn = positives - tp

    fp = int(round(tp * (1.0 / precision - 1.0))) if precision > 0 else 0
    fp = max(0, min(fp, negatives))

    tn = negatives - fp
    return [[tn, fp], [fn, tp]]


def plot_estimated_confusion_matrix(model_name: str, payload: dict) -> Path:
    precision = payload["finals"].get("Precision")
    recall = payload["finals"].get("Recall")
    matrix = build_estimated_confusion_matrix(precision, recall)

    fig, ax = plt.subplots(figsize=(7.4, 6.2), facecolor="white")
    ax.set_facecolor("white")

    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="Blues",
        cbar=False,
        linewidths=0.6,
        linecolor="white",
        square=True,
        ax=ax,
        annot_kws={"fontsize": 12, "fontweight": "bold"},
    )

    ax.set_title(f"{model_name.capitalize()} Estimated Confusion Matrix", fontsize=15, fontweight="bold", pad=12)
    ax.set_xlabel("Predicted Label", fontsize=11)
    ax.set_ylabel("Actual Label", fontsize=11)
    ax.set_xticklabels(["Negative", "Positive"], rotation=0)
    ax.set_yticklabels(["Negative", "Positive"], rotation=0)

    fig.text(
        0.5,
        0.02,
        "Estimated from final precision/recall in best.pt; not a dataset re-validation matrix.",
        ha="center",
        fontsize=9,
        color="#444444",
    )

    fig.tight_layout(rect=[0, 0.05, 1, 1])
    output_path = REPORT_DIR / f"{model_name}_confusion_matrix_estimated.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


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

    manifest = {
        "source": "best.pt checkpoint embedded metrics",
        "note": "No retraining and no dataset validation were run.",
        "images": {},
        "metrics": {},
    }

    for model_name, model_path in MODEL_PATHS.items():
        payload = load_model_metrics(model_path)

        curve_img = plot_metric_curves(model_name, payload)
        conf_img = plot_estimated_confusion_matrix(model_name, payload)

        manifest["images"][model_name] = {
            "curves": str(curve_img),
            "confusion_estimated": str(conf_img),
        }
        manifest["metrics"][model_name] = payload["finals"]

        print(f"Saved: {curve_img}")
        print(f"Saved: {conf_img}")

    manifest_path = REPORT_DIR / "analysis_images_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved: {manifest_path}")


if __name__ == "__main__":
    main()