
import json
import sys
from pathlib import Path
from collections import Counter


def inspect_layout(json_path, max_blocks=20, max_spans=5):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for page in data["pages"]:
        elements = [
            e for e in page["elements"]
            if e["type"] == "text"
        ]

        print(f"\n{'=' * 70}")
        print(f"PAGE {page['page_number']}")
        print(f"Total text blocks: {len(elements)}")
        print(f"{'=' * 70}")

        for element in elements[:max_blocks]:
            spans = [
                span
                for line in element.get("lines", [])
                for span in line.get("spans", [])
            ]

            fonts = Counter(
                span.get("font", "Unknown") for span in spans
            )

            sizes = sorted({
                round(span["font_size"], 2)
                for span in spans
                if span.get("font_size") is not None
            })

            text = element.get("text", "").replace("\n", " | ")

            print(f"\nID: {element['element_id']}")
            print(f"BBox: {element.get('bbox')}")
            print(f"Text: {text[:350]}")
            print(f"Span count: {len(spans)}")
            print(f"Fonts: {dict(fonts)}")
            print(f"Font sizes: {sizes}")

            print("Representative spans:")
            for span in spans[:max_spans]:
                print(
                    f"  {span.get('font')} "
                    f"({span.get('font_size')}) "
                    f"{span.get('text')!r}"
                )

            if len(spans) > max_spans:
                print(f"  ... {len(spans) - max_spans} more spans")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_layout.py path/to/file.json")
        sys.exit(1)

    inspect_layout(sys.argv[1])
