
import json
import re
import argparse
from pathlib import Path
from collections import Counter


PROJECT_ROOT = Path(__file__).resolve().parents[2]

URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?"
    r"(github\.com|gitlab\.com|bitbucket\.org)/.+$",
    re.IGNORECASE,
)


class DocumentValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checked_groups = 0
        self.checked_elements = 0

    def error(self, code, message, **details):
        self.errors.append({
            "severity": "error",
            "code": code,
            "message": message,
            **details,
        })

    def warning(self, code, message, **details):
        self.warnings.append({
            "severity": "warning",
            "code": code,
            "message": message,
            **details,
        })

    @staticmethod
    def valid_bbox(bbox):
        if not isinstance(bbox, list) or len(bbox) != 4:
            return False

        try:
            x0, y0, x1, y1 = map(float, bbox)
        except (TypeError, ValueError):
            return False

        return (
            x0 <= x1
            and y0 <= y1
        )

    def build_source_index(self, document):
        """
        Build a global index of interpreted elements.

        Each element is indexed by its ID and page number.
        """
        source_index = {}

        interpreted = document.get("interpreted_document", {})
        pages = interpreted.get("pages", [])

        for page in pages:
            page_number = page.get("page_number")

            for element in page.get("elements", []):
                element_id = element.get("element_id")

                if not element_id:
                    self.error(
                        "MISSING_ELEMENT_ID",
                        "An interpreted element has no element_id.",
                        page_number=page_number,
                    )
                    continue

                if element_id in source_index:
                    self.error(
                        "DUPLICATE_ELEMENT_ID",
                        f"Element ID '{element_id}' occurs more than once.",
                        page_number=page_number,
                    )
                    continue

                source_index[element_id] = {
                    "element": element,
                    "page_number": page_number,
                }

                self.checked_elements += 1

        return source_index

    def validate_source_reference(
        self,
        element_id,
        source_index,
        group_page,
        project_title,
    ):
        if element_id not in source_index:
            self.error(
                "UNKNOWN_SOURCE_ELEMENT",
                f"Source element '{element_id}' does not exist.",
                project_title=project_title,
                page_number=group_page,
            )
            return None

        source = source_index[element_id]

        if source["page_number"] != group_page:
            self.error(
                "PAGE_PROVENANCE_MISMATCH",
                f"Element '{element_id}' belongs to page "
                f"{source['page_number']}, not page {group_page}.",
                project_title=project_title,
            )

        return source["element"]

    def validate_project(
        self,
        project,
        page_number,
        source_index,
        assignments,
    ):
        self.checked_groups += 1

        title = project.get("title")

        if not isinstance(title, str) or not title.strip():
            self.error(
                "MISSING_PROJECT_TITLE",
                "A project group has no valid title.",
                page_number=page_number,
            )
            title = "<missing title>"

        repository = project.get("repository")

        if not repository:
            self.warning(
                "MISSING_REPOSITORY",
                "Project has no repository link.",
                project_title=title,
                page_number=page_number,
            )
        elif not URL_PATTERN.match(repository.strip()):
            self.warning(
                "INVALID_REPOSITORY_FORMAT",
                "Repository does not match a supported URL pattern.",
                project_title=title,
                repository=repository,
            )

        descriptions = project.get("description", [])

        if not isinstance(descriptions, list):
            self.error(
                "INVALID_DESCRIPTION_STRUCTURE",
                "Project description must be a list.",
                project_title=title,
            )
            descriptions = []

        if not descriptions:
            self.warning(
                "EMPTY_PROJECT_DESCRIPTION",
                "Project has no description items.",
                project_title=title,
            )

        source_ids = project.get("source_element_ids", [])

        if not isinstance(source_ids, list):
            self.error(
                "INVALID_SOURCE_ID_LIST",
                "source_element_ids must be a list.",
                project_title=title,
            )
            source_ids = []

        if not source_ids:
            self.error(
                "EMPTY_SOURCE_ID_LIST",
                "Project has no source element references.",
                project_title=title,
            )

        # Check duplicate IDs inside the same project.
        duplicate_ids = [
            element_id
            for element_id, count in Counter(source_ids).items()
            if count > 1
        ]

        for element_id in duplicate_ids:
            self.error(
                "DUPLICATE_PROJECT_SOURCE",
                f"Source element '{element_id}' appears more than once "
                "in the same project.",
                project_title=title,
            )

        # Check that a source element is not assigned
        # to multiple project groups.
        for element_id in source_ids:
            previous_assignment = assignments.get(element_id)

            if previous_assignment is not None:
                self.error(
                    "SOURCE_ASSIGNED_TO_MULTIPLE_PROJECTS",
                    f"Source element '{element_id}' is assigned to "
                    "more than one project.",
                    project_title=title,
                    previous_project=previous_assignment,
                )
            else:
                assignments[element_id] = title

            source_element = self.validate_source_reference(
                element_id,
                source_index,
                page_number,
                title,
            )

            if source_element is None:
                continue

            bbox = source_element.get("bbox")

            if bbox is not None and not self.valid_bbox(bbox):
                self.error(
                    "INVALID_SOURCE_BBOX",
                    f"Source element '{element_id}' has an invalid bbox.",
                    project_title=title,
                )

        # Check title provenance.
        title_source_ids = [
            element_id
            for element_id in source_ids
            if element_id.endswith("_interpreted")
        ]

        if not title_source_ids:
            self.warning(
                "TITLE_PROVENANCE_UNCLEAR",
                "Could not identify the interpreted title source "
                "using the current ID convention.",
                project_title=title,
            )

        # Check every description item.
        for index, item in enumerate(descriptions):
            if not isinstance(item, dict):
                self.error(
                    "INVALID_DESCRIPTION_ITEM",
                    "Description item must be an object.",
                    project_title=title,
                    item_index=index,
                )
                continue

            text = item.get("text", "")

            if not isinstance(text, str) or not text.strip():
                self.error(
                    "EMPTY_DESCRIPTION_ITEM",
                    "Description item has no text.",
                    project_title=title,
                    item_index=index,
                )

            description_source_id = item.get("source_element_id")

            if not description_source_id:
                self.error(
                    "MISSING_DESCRIPTION_SOURCE",
                    "Description item has no source element ID.",
                    project_title=title,
                    item_index=index,
                )
            elif description_source_id not in source_ids:
                self.error(
                    "DESCRIPTION_SOURCE_NOT_IN_GROUP",
                    "Description source ID is missing from "
                    "project.source_element_ids.",
                    project_title=title,
                    source_element_id=description_source_id,
                )

        # Preserve unexpected elements, but report them.
        unexpected = project.get("unclassified_children", [])

        if unexpected:
            self.warning(
                "UNCLASSIFIED_PROJECT_CHILDREN",
                "Project contains unexpected elements that need review.",
                project_title=title,
                count=len(unexpected),
            )

    def validate_document(self, document):
        source_index = self.build_source_index(document)

        assignments = {}

        for page in document.get("pages", []):
            page_number = page.get("page_number")

            for project in page.get("projects", []):
                self.validate_project(
                    project,
                    page_number,
                    source_index,
                    assignments,
                )

        return {
            "document_id": document.get("document_id"),
            "validation": {
                "validator": "structural_document_validator",
                "version": "0.1.0",
                "status": (
                    "failed" if self.errors else "passed"
                ),
                "checked_elements": self.checked_elements,
                "checked_groups": self.checked_groups,
                "error_count": len(self.errors),
                "warning_count": len(self.warnings),
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_file(input_path, output_path=None):
    input_path = Path(input_path)

    with input_path.open("r", encoding="utf-8") as file:
        document = json.load(file)

    validator = DocumentValidator()
    report = validator.validate_document(document)

    if output_path is None:
        output_path = (
            PROJECT_ROOT
            / "data"
            / "processed"
            / f"{input_path.stem}_validation.json"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    summary = report["validation"]

    print("\nStructural validation completed.")
    print("-" * 55)
    print("Status:", summary["status"].upper())
    print("Checked elements:", summary["checked_elements"])
    print("Checked project groups:", summary["checked_groups"])
    print("Errors:", summary["error_count"])
    print("Warnings:", summary["warning_count"])
    print("Report:", output_path)

    if report["errors"]:
        print("\nERRORS")

        for issue in report["errors"]:
            print(
                f"[{issue['code']}] {issue['message']}"
            )

    if report["warnings"]:
        print("\nWARNINGS")

        for issue in report["warnings"]:
            print(
                f"[{issue['code']}] {issue['message']}"
            )

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate semantic document structure."
    )

    parser.add_argument(
        "input",
        help="Input semantic JSON file",
    )

    parser.add_argument(
        "--output",
        help="Optional validation report path",
    )

    args = parser.parse_args()

    validate_file(args.input, args.output)


if __name__ == "__main__":
    main()
