"""
Phase 18: Automatic EDA Engine (charts).

Every chart in this app so far has come from the LLM deciding, on its
own, what's worth plotting. That's flexible, but it means the user gets
ZERO charts if the LLM has a bad run, and it means basic "what does this
data even look like" charts (a histogram, a correlation heatmap, a
missingness overview) get reinvented by the LLM from scratch every time
instead of just... always being there.

This module generates a small, fixed set of standalone EDA charts
directly from the DataFrame -- no LLM involved, so they're always
available and always consistent, the same "deterministic, not LLM"
philosophy as app/quality/data_quality.py and app/eda/auto_eda.py.
Matplotlib is used (already a dependency) rather than adding Plotly, to
keep the same static-PNG delivery mechanism (st.image) already used
everywhere else in the app -- no new dependency, no new rendering path.
"""

import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

AUTO_EDA_OUTPUTS_DIR = "outputs/auto_eda"
# Cap the number of distribution histograms -- a 40-column dataset
# shouldn't produce 40 charts; the columns with the most spread (highest
# coefficient of variation) are the most likely to be visually interesting.
MAX_DISTRIBUTION_CHARTS = 4


def _clear_auto_eda_charts(outputs_dir: str = AUTO_EDA_OUTPUTS_DIR) -> None:
    os.makedirs(outputs_dir, exist_ok=True)
    for path in glob.glob(os.path.join(outputs_dir, "auto_*.png")):
        os.remove(path)


def _pick_columns_for_distribution_charts(df: pd.DataFrame) -> list:
    numeric_df = df.select_dtypes(include="number")
    variability = {}
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        if len(series) < 2 or series.mean() == 0:
            continue
        # Coefficient of variation (std / mean) -- a scale-independent way
        # to rank "how spread out is this column" so a column measured in
        # the thousands doesn't automatically win over one measured in
        # single digits just because its raw std is bigger.
        variability[col] = abs(series.std() / series.mean())

    ranked = sorted(variability, key=variability.get, reverse=True)
    return ranked[:MAX_DISTRIBUTION_CHARTS]


def _save_distribution_chart(df: pd.DataFrame, col: str, outputs_dir: str, index: int) -> str:
    fig, ax = plt.subplots()
    df[col].dropna().plot(kind="hist", bins=20, ax=ax, color="#4C72B0", edgecolor="white")
    ax.set_title(f"Distribution of {col}")
    ax.set_xlabel(col)
    ax.set_ylabel("count")
    plt.tight_layout()
    path = os.path.join(outputs_dir, f"auto_dist_{index}_{col}.png")
    plt.savefig(path)
    plt.close(fig)
    return path


def _save_correlation_heatmap(df: pd.DataFrame, outputs_dir: str) -> str:
    numeric_df = df.select_dtypes(include="number")
    corr = numeric_df.corr()

    fig, ax = plt.subplots(figsize=(max(5, len(corr.columns) * 0.9), max(5, len(corr.columns) * 0.9)))
    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.columns)
    for i in range(len(corr.columns)):
        for j in range(len(corr.columns)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="correlation")
    ax.set_title("Correlation heatmap")
    plt.tight_layout()
    path = os.path.join(outputs_dir, "auto_correlation_heatmap.png")
    plt.savefig(path)
    plt.close(fig)
    return path


def _save_missingness_chart(df: pd.DataFrame, outputs_dir: str) -> str:
    missing_pct = (df.isnull().mean() * 100).sort_values(ascending=True)
    missing_pct = missing_pct[missing_pct > 0]

    fig, ax = plt.subplots(figsize=(6, max(2, len(missing_pct) * 0.4)))
    missing_pct.plot(kind="barh", ax=ax, color="#C44E52")
    ax.set_xlabel("% missing")
    ax.set_title("Missing values by column")
    plt.tight_layout()
    path = os.path.join(outputs_dir, "auto_missingness.png")
    plt.savefig(path)
    plt.close(fig)
    return path


def generate_auto_eda_charts(df: pd.DataFrame, outputs_dir: str = AUTO_EDA_OUTPUTS_DIR) -> list:
    """
    Generate the fixed set of deterministic EDA charts for this
    DataFrame and return the list of saved file paths, in a stable
    order (distributions, then correlation heatmap, then missingness).
    A chart type is skipped entirely when it wouldn't be meaningful
    (e.g. no correlation heatmap for a dataset with only one numeric
    column, no missingness chart if nothing is actually missing).
    """
    _clear_auto_eda_charts(outputs_dir)
    saved_paths = []

    for index, col in enumerate(_pick_columns_for_distribution_charts(df), start=1):
        saved_paths.append(_save_distribution_chart(df, col, outputs_dir, index))

    if df.select_dtypes(include="number").shape[1] >= 2:
        saved_paths.append(_save_correlation_heatmap(df, outputs_dir))

    if df.isnull().values.any():
        saved_paths.append(_save_missingness_chart(df, outputs_dir))

    return saved_paths


# Demo block: python -m app.eda.auto_charts data/samples/sample_sales.csv
if __name__ == "__main__":
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    dataframe = load_csv(csv_path)
    paths = generate_auto_eda_charts(dataframe)
    print(f"Generated {len(paths)} automatic EDA charts:")
    for p in paths:
        print(f"  - {p}")
