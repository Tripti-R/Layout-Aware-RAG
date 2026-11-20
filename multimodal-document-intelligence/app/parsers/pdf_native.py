
from pathlib import Path
import argparse
import hashlib
import json
import re

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def safe_name(filename: str) -> str:
    """Create a filesystem-safe document name."""
    name = Path(filename).stem
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name)
    return name.strip("_") or "document"


def extract_text_block(block: dict) -> dict:
    """Preserve text, lines, spans, fonts, and coordinates."""
    lines = []
    line_texts = []

    for line_index, line in enumerate(block.get("lines", [])):
        spans = []

        for span in line.get("spans", []):
            spans.append({
                "text": span.get("text", ""),
                "font": span.get("font"),
                "font_size": span.get("size"),
                "font_flags": span.get("flags"),
                "bbox": span.get("bbox"),
            })

        text = "".join(span["text"] for span in spans)
        line_texts.append(text)

        lines.append({
            "line_index": line_index,
            "bbox": line.get("bbox"),
            "text": text,
            "spans": spans,
        })

    return {
        "type": "text",
        "bbox": block.get("bbox"),
        "text": "\n".join(line_texts),
        "lines": lines,
    }


def process_pdf(
    pdf_path: str | Path,
    output_dir: Path | None = None,
    dpi: int = 200,
) -> Path:
    """Extract native PDF content, images, and page renderings."""

    pdf_path = Path(pdf_path).resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a PDF.")

    if dpi <= 0:
        raise ValueError("DPI must be greater than zero.")

    output_dir = output_dir or PROJECT_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    document_name = safe_name(pdf_path.name)
    file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:12]
    document_id = f"{document_name}_{file_hash}"

    image_dir = PROJECT_ROOT / "data" / "page_images" / document_id
    asset_dir = PROJECT_ROOT / "data" / "assets" / document_id

    image_dir.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)

    pages_data = []

    with pymupdf.open(pdf_path) as document:

        metadata = document.metadata or {}

        for page_index, page in enumerate(document):
            page_number = page_index + 1

            page_image_path = image_dir / f"page_{page_number:04d}.png"

            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            pixmap.save(str(page_image_path))

            page_dict = page.get_text("dict", sort=False)

            elements = []

            for block_index, block in enumerate(page_dict["blocks"]):

                if block.get("type") == 0:
                    element = extract_text_block(block)

                elif block.get("type") == 1:
                    extension = block.get("ext", "bin")
                    image_name = (
                        f"page_{page_number:04d}_"
                        f"image_{block_index:04d}.{extension}"
                    )
                    image_path = asset_dir / image_name

                    image_bytes = block.get("image")
                    if image_bytes:
                        image_path.write_bytes(image_bytes)

                    element = {
                        "type": "image",
                        "bbox": block.get("bbox"),
                        "width": block.get("width"),
                        "height": block.get("height"),
                        "image_path": str(image_path.relative_to(PROJECT_ROOT)),
                    }

                else:
                    continue

                element["element_id"] = (
                    f"p{page_number:04d}_e{block_index:04d}"
                )
                element["source_block_index"] = block_index

                elements.append(element)

            pages_data.append({
                "page_number": page_number,
                "width": page.rect.width,
                "height": page.rect.height,
                "rotation": page.rotation,
                "coordinate_system": (
                    "PyMuPDF page coordinates: points, "
                    "origin at top-left"
                ),
                "rendered_image": str(
                    page_image_path.relative_to(PROJECT_ROOT)
                ),
                "elements": elements,
            })

    result = {
        "document_id": document_id,
        "source": {
            "filename": pdf_path.name,
            "sha256": file_hash,
        },
        "metadata": metadata,
        "processing": {
            "parser": "PyMuPDF",
            "parser_version": pymupdf.__version__,
            "render_dpi": dpi,
            "extraction_type": "native_pdf_extraction",
        },
        "page_count": len(pages_data),
        "pages": pages_data,
    }

    output_path = output_dir / f"{document_id}_native.json"

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print(f"PDF processed successfully: {pdf_path.name}")
    print(f"Pages extracted: {len(pages_data)}")
    print(f"JSON output: {output_path}")
    print(f"Page images: {image_dir}")
    print(f"Extracted images: {asset_dir}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Extract native PDF content using PyMuPDF."
    )

    parser.add_argument("pdf", help="Path to the input PDF")
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Page rendering DPI (default: 200)",
    )

    args = parser.parse_args()
    process_pdf(args.pdf, dpi=args.dpi)


if __name__ == "__main__":
    main()
