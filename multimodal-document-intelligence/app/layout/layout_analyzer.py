
import json
import re
import argparse
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Unicode escapes avoid PowerShell / file-encoding corruption.
BULLET_PATTERN = re.compile(
    r"^\s*[\u2022\u25cf\u25aa\u25e6\u2043\u25b8\u25ba\u2013\u2014*]\s*"
)

NUMBERED_ITEM_PATTERN = re.compile(
    r"^\s*\d+[.)]\s+\S"
)

NUMBERED_HEADING_PATTERN = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?)\s+[A-Z][^\n]{1,100}$"
)

URL_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|"
    r"(?:github\.com|linkedin\.com)/\S+)",
    re.IGNORECASE,
)

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")

CONTACT_PATTERN = re.compile(
    r"linkedin\.com|github\.com|@|"
    r"\b(?:phone|email|contact|location)\b",
    re.IGNORECASE,
)

PUBLICATION_METADATA_PATTERN = re.compile(
    r"^(academic editor|received|revised|accepted|published|"
    r"copyright|licensee|this article is an open access article)",
    re.IGNORECASE,
)

AFFILIATION_PATTERN = re.compile(
    r"\b(department|school|faculty|university|institute|"
    r"college|research center|laboratory)\b",
    re.IGNORECASE,
)

ABSTRACT_PATTERN = re.compile(r"^abstract$", re.IGNORECASE)

KEYWORDS_PATTERN = re.compile(r"^keywords?\s*:", re.IGNORECASE)

SECTION_LABELS = {
    "introduction",
    "literature review",
    "related work",
    "methodology",
    "materials and methods",
    "methods",
    "results",
    "discussion",
    "conclusions",
    "conclusion",
    "future scope",
    "references",
    "acknowledgments",
    "acknowledgements",
    "abbreviations",
    "author contributions",
    "funding",
    "data availability",
    "conflicts of interest",
    "conflict of interest",
    "ethical approval",
    "institutional review board statement",
    "informed consent statement",
}


def union_bbox(boxes):
    """Calculate the bounding box enclosing multiple boxes."""
    boxes = [
        box for box in boxes
        if box and len(box) == 4
    ]

    if not boxes:
        return None

    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def bbox_center(box):
    return (
        (box[0] + box[2]) / 2,
        (box[1] + box[3]) / 2,
    )


def get_block_font_info(block):
    """Collect font information from all spans in a text block."""
    spans = [
        span
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ]

    sizes = [
        span["font_size"]
        for span in spans
        if span.get("font_size") is not None
    ]

    fonts = list({
        span.get("font", "Unknown")
        for span in spans
    })

    return {
        "font_sizes": sizes,
        "fonts": fonts,
        "max_font_size": max(sizes, default=0),
        "min_font_size": min(sizes, default=0),
    }


def get_block_text(block):
    return block.get("text", "").strip()


def get_spans(block):
    """Return all spans from a native text block."""
    return [
        span
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]


def is_bold_block(block):
    """Check font names for bold styling."""
    fonts = [
        span.get("font", "").lower()
        for span in get_spans(block)
    ]

    return bool(fonts) and any("bold" in font for font in fonts)


def split_bullet_items(block):
    """
    Split a text block into bullet items.

    Wrapped continuation lines remain attached to their
    preceding bullet. Original line coordinates are retained.
    """
    lines = block.get("lines", [])

    if not lines:
        return []

    groups = []
    current_group = []

    for line in lines:
        line_text = line.get("text", "").strip()

        if not line_text:
            continue

        if BULLET_PATTERN.match(line_text):
            if current_group:
                groups.append(current_group)

            current_group = [line]

        elif current_group:
            current_group.append(line)

        else:
            current_group = [line]

    if current_group:
        groups.append(current_group)

    items = []

    for index, group in enumerate(groups):
        text = "\n".join(
            line.get("text", "").strip()
            for line in group
        ).strip()

        boxes = [
            line.get("bbox")
            for line in group
        ]

        items.append({
            "text": BULLET_PATTERN.sub("", text, count=1),
            "bbox": union_bbox(boxes) or block.get("bbox"),
            "source_block_id": block["element_id"],
            "source_line_indices": [
                line.get("line_index")
                for line in group
            ],
            "bullet": bool(
                BULLET_PATTERN.match(
                    group[0].get("text", "").strip()
                )
            ),
            "item_index": index,
        })

    return items


def is_section_heading(text, block, body_font_size):
    """Recognize common and numbered academic section headings."""
    normalized = re.sub(r"\s+", " ", text).strip()
    lower = normalized.lower().rstrip(" .:")

    if lower in SECTION_LABELS:
        return True

    if NUMBERED_HEADING_PATTERN.match(normalized):
        return True

    font_info = get_block_font_info(block)

    if (
        len(normalized) <= 85
        and font_info["max_font_size"] >= body_font_size + 1.0
        and not normalized.endswith((".", ",", ";"))
    ):
        return True

    return False


def classify_block(
    block,
    body_font_size,
    page_height,
    page_width,
    page_number=1,
    previous_blocks=None,
):
    """Apply deterministic document and layout classification rules."""
    text = get_block_text(block)

    if not text:
        return "empty"

    font_info = get_block_font_info(block)
    max_size = font_info["max_font_size"]

    bbox = block.get("bbox") or [0, 0, 0, 0]
    x0, y0, x1, y1 = bbox

    center_x = (x0 + x1) / 2
    page_center_x = page_width / 2

    is_centered = (
        abs(center_x - page_center_x) < page_width * 0.20
    )

    # Academic article title.
    if (
        page_number == 1
        and 0.07 * page_height < y0 < 0.27 * page_height
        and max_size >= 14
        and len(text) < 300
    ):
        return "document_title"

    # Publication metadata in the left-side front matter.
    if (
        page_number == 1
        and x0 < page_width * 0.30
        and y0 > page_height * 0.65
        and max_size <= 8.5
        and PUBLICATION_METADATA_PATTERN.search(text)
    ):
        return "publication_metadata"

    # Abstract heading.
    if page_number == 1 and ABSTRACT_PATTERN.match(text):
        return "section_heading"

    # Keywords.
    if page_number == 1 and KEYWORDS_PATTERN.match(text):
        return "keywords"

    # Author names: typically bold and immediately after the title.
    if (
        page_number == 1
        and previous_blocks
        and any(
            item.get("_classification") == "document_title"
            for item in previous_blocks[-3:]
        )
        and is_bold_block(block)
        and len(text) < 200
        and not AFFILIATION_PATTERN.search(text)
        and not EMAIL_PATTERN.search(text)
    ):
        return "authors"

    # Affiliation and correspondence details.
    if (
        page_number == 1
        and y0 < page_height * 0.35
        and (
            AFFILIATION_PATTERN.search(text)
            or EMAIL_PATTERN.search(text)
        )
    ):
        return "affiliation"

    # Résumé-style centered document header.
    if (
        y0 < page_height * 0.08
        and is_centered
        and len(text) < 100
        and max_size < 14
    ):
        return "document_header"

    # Contact information.
    if (
        y0 < page_height * 0.10
        and (
            EMAIL_PATTERN.search(text)
            or PHONE_PATTERN.search(text)
            or CONTACT_PATTERN.search(text)
        )
    ):
        return "contact_info"

    # Standalone URL.
    if URL_PATTERN.search(text):
        remaining_text = URL_PATTERN.sub("", text).strip(
            " \t|—–-,:;"
        )

        if len(remaining_text) <= 8:
            return "hyperlink"

    # Figure caption.
    if re.match(r"^\s*Figure\s+\d+", text, re.IGNORECASE):
        return "figure_caption"

    # Table caption.
    if re.match(r"^\s*Table\s+\d+", text, re.IGNORECASE):
        return "table_caption"

    # Numbered or bulleted list.
    if BULLET_PATTERN.match(text):
        return "list"

    if (
        NUMBERED_ITEM_PATTERN.match(text)
        and len(text) > 85
    ):
        return "list"

    # Academic section heading.
    if is_section_heading(text, block, body_font_size):
        return "section_heading"

    return "paragraph"


def extract_table_spans(block):
    """Extract spans with valid text and coordinates."""
    result = []

    for span in get_spans(block):
        bbox = span.get("bbox")

        if not bbox or len(bbox) != 4:
            continue

        text = span.get("text", "").strip()

        if not text:
            continue

        cx, cy = bbox_center(bbox)

        result.append({
            "text": text,
            "bbox": bbox,
            "center_x": cx,
            "center_y": cy,
        })

    return result


def looks_like_table_header(block):
    """
    Identify a likely table header using its span content.

    This is intentionally conservative. A block must contain
    several short, distinct labels.
    """
    spans = extract_table_spans(block)

    if len(spans) < 3:
        return False

    text = get_block_text(block).lower()

    known_headers = {
        "model", "accuracy", "precision", "recall",
        "f1", "f1-score", "roc-auc", "fpr",
        "name", "value", "category", "year",
        "method", "result", "parameter",
    }

    matches = sum(
        1 for span in spans
        if span["text"].strip().lower() in known_headers
    )

    return matches >= 3


def looks_like_table_data(block):
    """Check whether a block contains repeated numeric data."""
    spans = extract_table_spans(block)

    numeric_spans = [
        span for span in spans
        if re.search(r"\d", span["text"])
    ]

    return len(numeric_spans) >= 5


def cluster_numeric_rows(spans, tolerance=3.0):
    """Cluster numeric spans by their vertical center."""
    numeric_spans = [
        span for span in spans
        if re.search(r"\d", span["text"])
    ]

    numeric_spans.sort(key=lambda span: span["center_y"])

    rows = []

    for span in numeric_spans:
        if (
            not rows
            or abs(
                span["center_y"] - rows[-1]["center_y"]
            ) > tolerance
        ):
            rows.append({
                "center_y": span["center_y"],
                "spans": [span],
            })
        else:
            row = rows[-1]
            row["spans"].append(span)
            row["center_y"] = median(
                item["center_y"] for item in row["spans"]
            )

    return rows


def reconstruct_table(header_block, data_block, caption_block=None):
    """
    Reconstruct a table using header and data span coordinates.

    Column centers come from the header spans. Numeric data
    spans establish row positions. Text in the first column
    is assigned to the nearest row, allowing wrapped labels.
    """
    header_spans = extract_table_spans(header_block)
    data_spans = extract_table_spans(data_block)

    if len(header_spans) < 3 or len(data_spans) < 5:
        return None

    header_spans.sort(key=lambda span: span["center_x"])

    columns = [
        {
            "column_index": index,
            "name": span["text"],
            "bbox": span["bbox"],
            "center_x": span["center_x"],
        }
        for index, span in enumerate(header_spans)
    ]

    row_clusters = cluster_numeric_rows(data_spans)

    if not row_clusters:
        return None

    # Assign each data span to its closest column.
    for span in data_spans:
        nearest_column = min(
            columns,
            key=lambda column: abs(
                span["center_x"] - column["center_x"]
            ),
        )
        span["column_index"] = nearest_column["column_index"]

    # Assign spans to rows using their vertical position.
    # A slightly larger tolerance supports wrapped first-column labels.
    for span in data_spans:
        nearest_row = min(
            row_clusters,
            key=lambda row: abs(
                span["center_y"] - row["center_y"]
            ),
        )
        span["row_index"] = row_clusters.index(nearest_row)

    rows = []

    for row_index, row_cluster in enumerate(row_clusters):
        cells = []

        for column in columns:
            cell_spans = [
                span for span in data_spans
                if (
                    span.get("row_index") == row_index
                    and span.get("column_index")
                    == column["column_index"]
                )
            ]

            cell_spans.sort(key=lambda span: span["center_y"])

            cell_text = " ".join(
                span["text"] for span in cell_spans
            ).strip()

            cells.append({
                "column_index": column["column_index"],
                "text": cell_text,
                "bbox": union_bbox([
                    span["bbox"] for span in cell_spans
                ]),
                "source_spans": [
                    {
                        "text": span["text"],
                        "bbox": span["bbox"],
                    }
                    for span in cell_spans
                ],
            })

        rows.append({
            "row_index": row_index,
            "cells": cells,
            "bbox": union_bbox([
                span["bbox"]
                for span in data_spans
                if span.get("row_index") == row_index
            ]),
        })

    caption = (
        get_block_text(caption_block)
        if caption_block else None
    )

    source_ids = [header_block["element_id"], data_block["element_id"]]

    if caption_block:
        source_ids.insert(0, caption_block["element_id"])

    return {
        "type": "table",
        "table_id": f"{data_block['element_id']}_table",
        "caption": caption,
        "columns": columns,
        "rows": rows,
        "bbox": union_bbox([
            header_block.get("bbox"),
            data_block.get("bbox"),
            caption_block.get("bbox") if caption_block else None,
        ]),
        "source_element_ids": source_ids,
        "confidence": 0.90,
        "classification_method": "span_coordinate_table_reconstruction",
    }


def detect_tables(text_blocks):
    """
    Find adjacent caption, header and data blocks.

    Original blocks are retained in the native extraction JSON.
    Their IDs are recorded in the reconstructed table.
    """
    tables = []
    consumed_ids = set()

    for index, block in enumerate(text_blocks):
        if not looks_like_table_header(block):
            continue

        if index + 1 >= len(text_blocks):
            continue

        data_block = text_blocks[index + 1]

        if not looks_like_table_data(data_block):
            continue

        caption_block = None

        if index > 0:
            previous = text_blocks[index - 1]

            if re.match(
                r"^\s*Table\s+\d+",
                get_block_text(previous),
                re.IGNORECASE,
            ):
                caption_block = previous

        table = reconstruct_table(
            block,
            data_block,
            caption_block,
        )

        if table:
            tables.append(table)
            consumed_ids.update(table["source_element_ids"])

    return tables, consumed_ids


def analyze_page(page):
    """Analyze text blocks and construct interpreted elements."""
    text_blocks = [
        block
        for block in page.get("elements", [])
        if block.get("type") == "text"
    ]

    all_sizes = [
        size
        for block in text_blocks
        for size in get_block_font_info(block)["font_sizes"]
    ]

    body_font_size = median(all_sizes) if all_sizes else 10.0

    page_height = page.get("height", 792)
    page_width = page.get("width", 612)
    page_number = page.get("page_number", 1)

    # Detect tables before ordinary text classification.
    tables, consumed_table_ids = detect_tables(text_blocks)

    interpreted = []
    current_section = None
    previous_blocks = []

    for block in text_blocks:
        source_id = block["element_id"]
        text = get_block_text(block)

        if source_id in consumed_table_ids:
            previous_blocks.append({
                "_classification": "table_component",
            })
            continue

        classification = classify_block(
            block,
            body_font_size,
            page_height,
            page_width,
            page_number,
            previous_blocks,
        )

        if classification == "section_heading":
            current_section = text

        if classification == "list":
            items = split_bullet_items(block)

            for item in items:
                interpreted.append({
                    "element_id": (
                        f"{source_id}_item_{item['item_index']}"
                    ),
                    "type": "list_item",
                    "text": item["text"],
                    "bbox": item["bbox"],
                    "source_block_ids": [source_id],
                    "source_line_indices": item["source_line_indices"],
                    "section": current_section,
                    "confidence": 0.90,
                    "classification_method": "bullet_marker",
                })

        else:
            interpreted.append({
                "element_id": f"{source_id}_interpreted",
                "type": classification,
                "text": text,
                "bbox": block.get("bbox"),
                "source_block_ids": [source_id],
                "section": current_section,
                "confidence": (
                    0.95 if classification == "hyperlink"
                    else 0.85 if classification in {
                        "document_title",
                        "authors",
                        "affiliation",
                        "publication_metadata",
                        "section_heading",
                        "figure_caption",
                        "table_caption",
                        "keywords",
                    }
                    else 0.75
                ),
                "classification_method": (
                    "url_pattern" if classification == "hyperlink"
                    else "document_structure_and_layout_heuristics"
                ),
            })

        previous_blocks.append({
            "_classification": classification,
        })

    # Add reconstructed tables as first-class interpreted elements.
    for table in tables:
        table["section"] = current_section
        interpreted.append(table)

    # Restore approximate reading order by vertical position.
    interpreted.sort(
        key=lambda element: (
            element.get("bbox", [0, 0, 0, 0])[1]
            if element.get("bbox") else 0
        )
    )

    return {
        "page_number": page_number,
        "layout_type": "unclassified",
        "body_font_size_estimate": round(body_font_size, 2),
        "elements": interpreted,
    }


def analyze_document(input_path, output_path=None):
    input_path = Path(input_path)

    with input_path.open("r", encoding="utf-8") as file:
        document = json.load(file)

    analyzed_pages = [
        analyze_page(page)
        for page in document.get("pages", [])
    ]

    result = {
        "document_id": document.get("document_id"),
        "source": document.get("source"),
        "processing": {
            "analyzer": "rule_based_layout_analyzer",
            "version": "0.2.0",
            "source_parser": document.get(
                "processing", {}
            ).get("parser"),
        },
        "page_count": len(analyzed_pages),
        "pages": analyzed_pages,
    }

    if output_path is None:
        output_path = (
            PROJECT_ROOT
            / "data"
            / "processed"
            / f"{input_path.stem}_layout.json"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print("Layout analysis completed.")
    print("Output:", output_path)

    for page in analyzed_pages:
        print(f"\nPage {page['page_number']}")

        for element in page["elements"]:
            if element["type"] == "table":
                print(
                    f"{'table':<18} "
                    f"{element['table_id']:<30} "
                    f"{len(element['rows'])} rows, "
                    f"{len(element['columns'])} columns"
                )
            else:
                print(
                    f"{element['type']:<18} "
                    f"{element['element_id']:<30} "
                    f"{element.get('text', '')[:75]}"
                )

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Analyze native PDF extraction JSON."
    )

    parser.add_argument("input", help="Native extraction JSON")
    parser.add_argument(
        "--output",
        help="Optional output JSON path",
    )

    args = parser.parse_args()
    analyze_document(args.input, args.output)


if __name__ == "__main__":
    main()
