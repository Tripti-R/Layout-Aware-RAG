
import json
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def normalize_text(text):
    return " ".join(text.lower().split())


def is_project_title(element):
    """
    Identify a likely project title.

    Initial heuristic:
    - Must be a paragraph.
    - Must contain a reasonably short title.
    - Must be inside the Projects section.
    """
    if element.get("type") != "paragraph":
        return False

    text = element.get("text", "").strip()

    if not text or len(text) > 180:
        return False

    # Project titles in the current test contain a separate Domains field.
    return "domains:" in text.lower()


def extract_project_title(text):
    """
    Separate the project title from its Domains metadata.
    """
    parts = text.split("Domains:", maxsplit=1)

    title = parts[0].strip()
    domains = parts[1].strip() if len(parts) > 1 else None

    return title, domains


def is_repository_link(element):
    if element.get("type") != "hyperlink":
        return False

    text = element.get("text", "").lower()

    return (
        "github.com/" in text
        or "gitlab.com/" in text
        or "bitbucket.org/" in text
    )


def group_projects(elements):
    """
    Group project titles, repository links and description items.

    Expected order:
        project title
        repository URL
        description item(s)
        next project title
    """
    projects = []
    current_section = None
    current_project = None

    def finish_project():
        nonlocal current_project

        if current_project is not None:
            projects.append(current_project)
            current_project = None

    for element in elements:
        element_type = element.get("type")
        text = element.get("text", "").strip()
        section = element.get("section")

        # Track section transitions.
        if section != current_section:
            if current_section == "Projects":
                finish_project()

            current_section = section

        # Ignore content outside the Projects section.
        if current_section != "Projects":
            continue

        # Start a new project.
        if is_project_title(element):
            finish_project()

            title, domains = extract_project_title(text)

            current_project = {
                "type": "project",
                "title": title,
                "domains": domains,
                "repository": None,
                "description": [],
                "source_element_ids": [
                    element["element_id"]
                ],
                "bbox": element.get("bbox"),
                "confidence": 0.90,
                "grouping_method": "project_title_domains_pattern",
            }

        elif current_project is not None and is_repository_link(element):
            current_project["repository"] = text

            current_project["source_element_ids"].append(
                element["element_id"]
            )

        elif (
            current_project is not None
            and element_type == "list_item"
        ):
            current_project["description"].append({
                "text": text,
                "source_element_id": element["element_id"],
                "bbox": element.get("bbox"),
            })

            current_project["source_element_ids"].append(
                element["element_id"]
            )

        elif current_project is not None:
            # An unexpected element inside the project sequence.
            # Preserve it rather than silently discarding it.
            current_project.setdefault(
                "unclassified_children", []
            ).append({
                "type": element_type,
                "text": text,
                "source_element_id": element["element_id"],
            })

            current_project["source_element_ids"].append(
                element["element_id"]
            )

    finish_project()

    return projects


def group_page(page):
    elements = page.get("elements", [])

    projects = group_projects(elements)

    return {
        "page_number": page["page_number"],
        "projects": projects,
    }


def group_document(input_path, output_path=None):
    input_path = Path(input_path)

    with input_path.open("r", encoding="utf-8") as file:
        document = json.load(file)

    grouped_pages = [
        group_page(page)
        for page in document.get("pages", [])
    ]

    result = {
        "document_id": document.get("document_id"),
        "source": document.get("source"),
        "processing": {
            "grouper": "initial_rule_based_semantic_grouper",
            "version": "0.1.0",
            "input_analyzer": document.get(
                "processing", {}
            ).get("analyzer"),
        },
        "page_count": len(grouped_pages),
        "pages": grouped_pages,

        # Retain the complete interpreted representation.
        "interpreted_document": document,
    }

    if output_path is None:
        output_path = (
            PROJECT_ROOT
            / "data"
            / "processed"
            / f"{input_path.stem}_semantic.json"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    print("Semantic grouping completed.")
    print("Output:", output_path)

    for page in grouped_pages:
        print(f"\nPage {page['page_number']}")

        for index, project in enumerate(page["projects"], start=1):
            print(f"\nProject {index}: {project['title']}")
            print(f"Domains: {project['domains']}")
            print(f"Repository: {project['repository']}")
            print(
                f"Description items: "
                f"{len(project['description'])}"
            )

            for item in project["description"]:
                print("  -", item["text"][:100])

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Group interpreted PDF elements semantically."
    )

    parser.add_argument(
        "input",
        help="Input layout-analysis JSON",
    )

    parser.add_argument(
        "--output",
        help="Optional output JSON path",
    )

    args = parser.parse_args()

    group_document(args.input, args.output)


if __name__ == "__main__":
    main()
