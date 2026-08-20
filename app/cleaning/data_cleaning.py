"""
Phase 24: Data Cleaning Agent.

Turns Phase 12's deterministic data_quality report into concrete,
human-readable cleaning suggestions, and can optionally APPLY a
conservative subset of them to produce a cleaned DataFrame plus a
plain-language log of exactly what changed.

Design decisions:
- Deterministic only, no LLM call -- this is data-quality bookkeeping,
  not analysis, and doesn't need probabilistic judgment.
- suggest_cleaning_actions() and apply_cleaning_actions() are separate
  functions on purpose: computing suggestions never touches the data, so
  it's always safe to compute and show. Applying a fix is a distinct,
  explicit step -- the general project principle of never silently
  mutating a user's data, applied here too.
- Only a conservative, opinionated default set of actions are
  auto-applied: filling missing values, dropping exact-duplicate rows,
  and standardizing inconsistent category spellings. Dropping a whole
  COLUMN (constant or ID-like) is a much higher-risk, harder-to-undo
  decision, so those stay suggestions only (auto_applied=False) -- a
  user should decide that, not have it happen silently.
- apply_cleaning_actions() always works on a COPY of the input
  DataFrame, never the original -- the caller's df is left untouched.
"""

import pandas as pd

MISSING_CATEGORICAL_FILL_VALUE = "Unknown"


def suggest_cleaning_actions(df: pd.DataFrame, quality_report: dict) -> list:
    """
    Returns a list of suggested actions, each a plain dict:
    {"type": str, "column": str|None, "description": str, "auto_applied": bool}

    auto_applied marks which suggestions apply_cleaning_actions() will
    actually perform if handed this same list -- everything else is
    shown as a suggestion only.
    """
    suggestions = []

    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        if null_count == 0:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            suggestions.append({
                "type": "fill_missing_numeric",
                "column": col,
                "description": f"Fill {null_count} missing value(s) in '{col}' with the column median.",
                "auto_applied": True,
            })
        else:
            suggestions.append({
                "type": "fill_missing_categorical",
                "column": col,
                "description": f"Fill {null_count} missing value(s) in '{col}' with '{MISSING_CATEGORICAL_FILL_VALUE}'.",
                "auto_applied": True,
            })

    duplicate_count = int(df.duplicated().sum())
    if duplicate_count > 0:
        suggestions.append({
            "type": "drop_duplicates",
            "column": None,
            "description": f"Remove {duplicate_count} exact duplicate row(s).",
            "auto_applied": True,
        })

    inconsistent = quality_report.get("structural_flags", {}).get("inconsistent_categories", {})
    for col, groups in inconsistent.items():
        # groups looks like {"usa": ["USA", "usa", " Usa"]} -- show the
        # raw spellings found so the suggestion is concrete, not vague.
        examples = ", ".join(f"{{{'/'.join(map(str, v))}}}" for v in list(groups.values())[:3])
        suggestions.append({
            "type": "standardize_categories",
            "column": col,
            "description": f"Standardize inconsistent spellings in '{col}' (e.g. {examples}) to one canonical form.",
            "auto_applied": True,
        })

    for col in quality_report.get("structural_flags", {}).get("constant_columns", []):
        suggestions.append({
            "type": "drop_constant_column",
            "column": col,
            "description": f"Consider dropping '{col}' -- it has only one distinct value across every row.",
            "auto_applied": False,
        })

    for col in quality_report.get("structural_flags", {}).get("id_like_columns", []):
        suggestions.append({
            "type": "drop_id_column",
            "column": col,
            "description": f"Consider dropping '{col}' -- it looks like an identifier column (almost all values unique), unlikely to be useful for analysis.",
            "auto_applied": False,
        })

    return suggestions


def apply_cleaning_actions(df: pd.DataFrame, actions: list) -> dict:
    """
    Applies every action flagged auto_applied=True, in order, to a COPY
    of df. Returns {"cleaned_df": pd.DataFrame, "log": [str, ...]} --
    the log is a plain-language record of exactly what happened, in the
    order it happened, so nothing is a silent mutation.
    """
    cleaned = df.copy()
    log = []

    for action in actions:
        if not action.get("auto_applied"):
            continue

        action_type = action["type"]
        col = action.get("column")

        if action_type == "fill_missing_numeric":
            fill_value = cleaned[col].median()
            missing_before = int(cleaned[col].isnull().sum())
            cleaned[col] = cleaned[col].fillna(fill_value)
            log.append(f"Filled {missing_before} missing value(s) in '{col}' with the median ({fill_value}).")

        elif action_type == "fill_missing_categorical":
            missing_before = int(cleaned[col].isnull().sum())
            cleaned[col] = cleaned[col].fillna(MISSING_CATEGORICAL_FILL_VALUE)
            log.append(f"Filled {missing_before} missing value(s) in '{col}' with '{MISSING_CATEGORICAL_FILL_VALUE}'.")

        elif action_type == "drop_duplicates":
            before = len(cleaned)
            cleaned = cleaned.drop_duplicates().reset_index(drop=True)
            removed = before - len(cleaned)
            log.append(f"Removed {removed} exact duplicate row(s).")

        elif action_type == "standardize_categories":
            # Collapse every value to its normalized (stripped, lowercased)
            # form's most common ORIGINAL spelling -- e.g. "USA"/"usa"/" Usa "
            # all become whichever of those three appears most often.
            normalized = cleaned[col].astype(str).str.strip().str.lower()
            canonical_by_normalized = (
                cleaned[col]
                .astype(str)
                .groupby(normalized)
                .agg(lambda values: values.value_counts().idxmax())
            )
            changed_count = int((cleaned[col].astype(str) != normalized.map(canonical_by_normalized)).sum())
            cleaned[col] = normalized.map(canonical_by_normalized)
            log.append(f"Standardized {changed_count} inconsistent spelling(s) in '{col}' to one canonical form.")

    return {"cleaned_df": cleaned, "log": log}


# Demo block, same convention as every other module in this project:
#   python -m app.cleaning.data_cleaning data/samples/messy_mixed_types.csv
if __name__ == "__main__":
    import json
    import os
    import sys

    from app.ingestion.csv_profiler import load_csv
    from app.quality.data_quality import assess_data_quality

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    dataframe = load_csv(csv_path)
    report = assess_data_quality(dataframe)

    actions = suggest_cleaning_actions(dataframe, report)
    print(f"{len(actions)} suggested action(s):")
    for a in actions:
        marker = "AUTO" if a["auto_applied"] else "manual review"
        print(f"  [{marker}] {a['description']}")

    result = apply_cleaning_actions(dataframe, actions)
    print("\nApplied:")
    for line in result["log"]:
        print(f"  - {line}")
    print(f"\nShape before: {dataframe.shape}, after: {result['cleaned_df'].shape}")
