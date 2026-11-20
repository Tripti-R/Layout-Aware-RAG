
import json
import sys
from pathlib import Path

file_path = Path(sys.argv[1])

with file_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

print("\nDOCUMENT LAYOUT SUMMARY")
print("=" * 65)
print("Pages:", len(data.get("pages", [])))

for page in data.get("pages", []):
    page_num = page.get("page_number", "?")
    elements = page.get("elements", [])

    left = []
    right = []
    full = []

    for el in elements:
        bbox = el.get("bbox", [0, 0, 0, 0])
        if len(bbox) < 4:
            continue

        x0, y0, x1, y1 = bbox
        width = x1 - x0
        center = (x0 + x1) / 2

        if width > 400:
            full.append(el)
        elif center < 300:
            left.append(el)
        else:
            right.append(el)

    print(
        f"Page {page_num:>2}: "
        f"Blocks={len(elements):>3} | "
        f"Left={len(left):>3} | "
        f"Right={len(right):>3} | "
        f"Wide={len(full):>3}"
    )

print("=" * 65)
print("Wide = blocks spanning much of the page; approximate only.")

print("\n\nDETAILED BLOCK POSITIONS")
print("=" * 75)

for page in data.get("pages", []):
    page_num = page.get("page_number", "?")

    if page_num not in [2, 8, 17, 19]:
        continue

    print(f"\nPAGE {page_num}")
    print("-" * 75)

    for el in page.get("elements", []):
        bbox = el.get("bbox", [0, 0, 0, 0])
        text = " ".join(el.get("text", "").split())

        print(
            f"X: {bbox[0]:6.1f}-{bbox[2]:6.1f} | "
            f"Y: {bbox[1]:6.1f}-{bbox[3]:6.1f} | "
            f"{text[:75]}"
        )
