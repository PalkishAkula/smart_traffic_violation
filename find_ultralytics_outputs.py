from pathlib import Path


MODEL_HELMET = Path(r"D:\Final year project\user interface\models\helmet\best.pt")
MODEL_LICENSE = Path(r"D:\Final year project\user interface\models\license\best.pt")


def candidate_run_dirs(workspace_root: Path) -> list[Path]:
    return [
        workspace_root / "runs" / "detect",
        MODEL_HELMET.parent / "runs" / "detect",
        MODEL_LICENSE.parent / "runs" / "detect",
        MODEL_HELMET.parent.parent / "runs" / "detect",
        MODEL_LICENSE.parent.parent / "runs" / "detect",
    ]


def is_excluded(path: Path) -> bool:
    excluded = {"venv", ".git", "__pycache__"}
    return any(part in excluded for part in path.parts)


def find_files(root: Path, names: set[str]) -> list[Path]:
    matches: list[Path] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if is_excluded(file_path):
            continue
        if file_path.name in names:
            matches.append(file_path.resolve())
    return sorted(matches)


def print_group(title: str, paths: list[Path]) -> None:
    print(f"\n{title}")
    if not paths:
        print("  None found")
        return
    for path in paths:
        print(f"  {path}")


def main() -> None:
    root = Path(__file__).resolve().parent

    print(f"Workspace root: {root}")
    print("\nModel paths:")
    print(f"  Helmet  : {MODEL_HELMET}  (exists={MODEL_HELMET.exists()})")
    print(f"  License : {MODEL_LICENSE}  (exists={MODEL_LICENSE.exists()})")

    likely_dirs = [d for d in candidate_run_dirs(root) if d.exists()]
    print_group("Detected run directories near model/workspace paths:", likely_dirs)

    targeted_results: list[Path] = []
    targeted_confusions: list[Path] = []
    for run_dir in likely_dirs:
        targeted_results.extend(find_files(run_dir, {"results.png", "results.jpg", "results.jpeg"}))
        targeted_confusions.extend(
            find_files(
                run_dir,
                {
                    "confusion_matrix.png",
                    "confusion_matrix.jpg",
                    "confusion_matrix.jpeg",
                    "confusion_matrix_normalized.png",
                    "confusion_matrix_normalized.jpg",
                    "confusion_matrix_normalized.jpeg",
                },
            )
        )

    targeted_results = sorted(set(targeted_results))
    targeted_confusions = sorted(set(targeted_confusions))

    print_group("Detected Ultralytics results files in likely run dirs:", targeted_results)
    print_group("Detected confusion matrix files in likely run dirs:", targeted_confusions)

    results_files = find_files(root, {"results.png", "results.jpg", "results.jpeg"})
    confusion_files = find_files(
        root,
        {
            "confusion_matrix.png",
            "confusion_matrix.jpg",
            "confusion_matrix.jpeg",
            "confusion_matrix_normalized.png",
            "confusion_matrix_normalized.jpg",
            "confusion_matrix_normalized.jpeg",
        },
    )

    print_group("Detected Ultralytics results files:", results_files)
    print_group("Detected Ultralytics confusion matrix files:", confusion_files)

    if not results_files and not confusion_files:
        print("\nExpected Ultralytics run folders from your training names:")
        print("  .\\runs\\detect\\traffic_violation_improved\\")
        print("  .\\runs\\detect\\traffic_violation_model\\")
        print("\nIf training was started from model folders, also check:")
        print("  .\\models\\helmet\\runs\\detect\\traffic_violation_improved\\")
        print("  .\\models\\license\\runs\\detect\\traffic_violation_model\\")
        print("\nIf training was done in Google Colab, check:")
        print("  /content/runs/detect/traffic_violation_improved/")


if __name__ == "__main__":
    main()