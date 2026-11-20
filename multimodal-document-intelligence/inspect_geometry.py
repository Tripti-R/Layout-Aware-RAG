
import json
import sys


def inspect_geometry(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for page in data["pages"]:
        print(f"\nPAGE {page['page_number']}")
        print("-" * 95)
        print(
            f"{'ID':<16} {'X0':>9} {'Y0':>9} "
            f"{'X1':>9} {'Y1':>9} {'TEXT'}"
        )

        for element in page["elements"]:
            if element["type"] != "text":
                continue

            x0, y0, x1, y1 = element["bbox"]

            text = element["text"].replace("\n", " ")
            text = text[:65]

            print(
                f"{element['element_id']:<16} "
                f"{x0:>9.1f} {y0:>9.1f} "
                f"{x1:>9.1f} {y1:>9.1f} {text}"
            )


if __name__ == "__main__":
    inspect_geometry(sys.argv[1])
