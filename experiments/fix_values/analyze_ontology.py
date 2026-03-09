# This deliverable is considered developed content as defined in contract between BDF parties.


"""Script to analyze JSON-LD ontology file."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def load_jsonld(file_path: Path) -> Dict[str, Any]:
    """Load JSON-LD file.

    Args:
        file_path: Path to JSON-LD file

    Returns:
        Dictionary containing the JSON-LD data
    """
    print(f"Reading JSON-LD file...")
    with open(file_path) as f:
        data = json.load(f)
    return data


def get_node_by_id(
    graph: List[Dict[str, Any]], node_id: str
) -> Optional[Dict[str, Any]]:
    """Get a node from the graph by its @id.

    Args:
        graph: List of nodes from the JSON-LD @graph
        node_id: ID of the node to find

    Returns:
        The node if found, None otherwise
    """
    for node in graph:
        if node.get("@id") == node_id:
            return node
    return None


def get_field_options(
    graph: List[Dict[str, Any]], field_name: str
) -> Optional[Set[str]]:
    """Get valid options for a field from the ontology.

    Args:
        graph: List of nodes from the JSON-LD @graph
        field_name: Name of field to get options for

    Returns:
        Set of valid values for the field, if found
    """
    # Look for class with matching name
    for node in graph:
        if node.get("@type") == "rdfs:Class" and str(
            node.get("@id", "")
        ).lower().endswith(field_name.lower()):
            print(f"\nFound class: {node['@id']}")

            # Get all instances of this class
            options = set()

            # Check for values in schema:rangeIncludes
            range_includes = node.get("schema:rangeIncludes", [])
            if not isinstance(range_includes, list):
                range_includes = [range_includes]

            for value in range_includes:
                if isinstance(value, dict) and "@id" in value:
                    # Get the referenced node
                    ref_node = get_node_by_id(graph, value["@id"])
                    if ref_node and "rdfs:label" in ref_node:
                        options.add(str(ref_node["rdfs:label"]))
                        print(f"Found value: {ref_node['rdfs:label']}")
                    else:
                        # Use the ID if no label is found
                        label = value["@id"].split(":")[-1]
                        options.add(label)
                        print(f"Found value (from ID): {label}")

            return options if options else None

    return None


def analyze_ontology(file_path: Path) -> Dict[str, Set[str]]:
    """Analyze ontology to extract field options.

    Args:
        file_path: Path to JSON-LD ontology file

    Returns:
        Dictionary mapping field names to sets of valid values
    """
    print(f"Loading ontology from {file_path}...")
    data = load_jsonld(file_path)

    # Get the @graph array
    graph = data.get("@graph", [])
    print(f"Found {len(graph)} nodes in graph")

    # Get all classes
    classes = [node for node in graph if node.get("@type") == "rdfs:Class"]
    print(f"Found {len(classes)} classes")

    # Extract field options
    field_options: Dict[str, Set[str]] = {}
    for node in classes:
        class_name = str(node.get("@id", "")).split(":")[-1].lower()
        if not class_name:
            continue

        print(f"\nAnalyzing class: {class_name}")
        options = get_field_options(graph, class_name)
        if options:
            field_options[class_name] = options
            print(f"Found {len(options)} options for field {class_name}")

    return field_options


def main() -> None:
    """Main entry point."""
    ontology_path = Path(
        "/home/ubuntu/projects/data/pz-nf-testing-data/schema/NF.jsonid"
    )

    try:
        field_options = analyze_ontology(ontology_path)

        # Print summary
        print("\nField options summary:")
        for field, options in field_options.items():
            print(f"\n{field}:")
            for option in sorted(options):
                print(f"  - {option}")

    except Exception as e:
        print(f"Error analyzing ontology: {e}")


if __name__ == "__main__":
    main()
