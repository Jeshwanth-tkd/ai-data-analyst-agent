"""
Phase 6 helper: generates a large CSV to test the file-size cap in
app/ingestion/csv_profiler.py. This isn't part of the agent itself —
it's a one-off tool you run locally to create test data, since a
multi-megabyte file isn't something worth shipping through chat.

Run it directly:
    python data/samples/generate_huge_sample.py
"""

import csv
import os
import random

NUM_ROWS = 200_000
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "messy_huge.csv")

CATEGORIES = ["Electronics", "Fitness", "Home", "Office"]
PRODUCTS = ["Wireless Mouse", "Yoga Mat", "Bluetooth Speaker", "Desk Lamp", "Notebook"]

with open(OUTPUT_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["order_id", "product", "category", "price", "quantity", "order_date", "customer_email"])
    for i in range(1, NUM_ROWS + 1):
        writer.writerow([
            i,
            random.choice(PRODUCTS),
            random.choice(CATEGORIES),
            round(random.uniform(5, 100), 2),
            random.randint(1, 5),
            f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            f"user{i}@example.com",
        ])

size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
print(f"Generated {NUM_ROWS:,} rows at {OUTPUT_PATH} ({size_mb:.1f} MB)")
