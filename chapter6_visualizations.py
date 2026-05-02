from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns


def create_violation_distribution_chart(output_dir: Path) -> Path:
    violation_types = ["NO_HELMET", "TRIPLE_RIDING", "CO_RIDING_NO_HELMET"]
    counts = [68, 28, 17]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

    fig, ax = plt.subplots(figsize=(10, 6), facecolor="white")
    ax.set_facecolor("white")
    bars = ax.bar(violation_types, counts, color=colors, edgecolor="#2f2f2f", linewidth=0.6)

    ax.set_title("Violation Type Distribution", fontsize=16, fontweight="bold", pad=14)
    ax.set_xlabel("Violation Type", fontsize=12)
    ax.set_ylabel("Count of Violations", fontsize=12)
    ax.grid(axis="y", linestyle="--", alpha=0.45)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=10, rotation=0)
    ax.tick_params(axis="y", labelsize=10)

    for bar, value in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + 1,
            str(value),
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="semibold",
        )

    fig.tight_layout()
    output_path = output_dir / "violation_distribution.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def create_violations_over_time_chart(output_dir: Path) -> Path:
    hours = ["9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "6 PM"]

    no_helmet = [3, 5, 9, 11, 10, 6, 7, 10, 9, 5]
    triple_riding = [1, 2, 4, 5, 4, 2, 3, 5, 4, 2]
    co_riding_no_helmet = [1, 1, 3, 4, 3, 2, 2, 4, 3, 1]

    fig, ax = plt.subplots(figsize=(11, 6), facecolor="white")
    ax.set_facecolor("white")
    ax.plot(hours, no_helmet, marker="o", linewidth=2.4, markersize=6, label="NO_HELMET", color="#1f77b4")
    ax.plot(
        hours,
        triple_riding,
        marker="s",
        linewidth=2.2,
        markersize=5.5,
        label="TRIPLE_RIDING",
        color="#ff7f0e",
    )
    ax.plot(
        hours,
        co_riding_no_helmet,
        marker="^",
        linewidth=2.2,
        markersize=6,
        label="CO_RIDING_NO_HELMET",
        color="#2ca02c",
    )

    ax.set_title("Violations Detected Over Time", fontsize=16, fontweight="bold", pad=14)
    ax.set_xlabel("Time of Day", fontsize=12)
    ax.set_ylabel("Violations Detected per Hour", fontsize=12)
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.tick_params(axis="x", labelrotation=20, labelsize=10)
    ax.tick_params(axis="y", labelsize=10)
    ax.legend(title="Violation Type", fontsize=10, title_fontsize=10, frameon=True)

    fig.tight_layout()
    output_path = output_dir / "violations_over_time.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path


def main() -> None:
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font_scale=1.15,
        rc={
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "grid.color": "#d0d0d0",
            "grid.linestyle": "--",
            "grid.alpha": 0.5,
        },
    )

    output_dir = Path(__file__).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)

    chart1_path = create_violation_distribution_chart(output_dir)
    chart2_path = create_violations_over_time_chart(output_dir)

    print(f"Saved: {chart1_path}")
    print(f"Saved: {chart2_path}")


if __name__ == "__main__":
    main()