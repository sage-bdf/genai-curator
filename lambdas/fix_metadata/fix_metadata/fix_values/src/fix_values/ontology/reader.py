# This deliverable is considered developed content as defined in contract between BDF parties.


from pathlib import Path
from typing import Dict, List, Optional, Set

import ijson
from loguru import logger


class OntologyReader:
    def __init__(self, file_path: str):
        """Initialize the OntologyReader with a file path."""
        self.file_path = Path(file_path)
        self.field_options: Dict[str, Set[str]] = {}

    def _clean_id(self, id_str: str) -> str:
        """Clean an @id string to get the base name."""
        if ":" in id_str:
            return id_str.split(":")[-1]
        return id_str.split("/")[-1]

    def process_chunk(self, item: dict) -> None:
        """Process a chunk of the JSON-LD data to extract field options."""
        if "@type" not in item:
            return

        # Get the field name from @id
        if "@id" not in item:
            return

        field_name = self._clean_id(item["@id"])

        # Look for valid options in schema:rangeIncludes
        if "schema:rangeIncludes" in item:
            range_includes = item["schema:rangeIncludes"]
            if not isinstance(range_includes, list):
                range_includes = [range_includes]

            # Initialize set for this field if not exists
            if field_name not in self.field_options:
                self.field_options[field_name] = set()

            # Add each option
            for option in range_includes:
                if isinstance(option, dict) and "@id" in option:
                    clean_option = self._clean_id(option["@id"])
                    self.field_options[field_name].add(clean_option)

    def read_ontology(self, max_chunks: Optional[int] = None) -> None:
        """Read the ontology file in chunks using ijson."""
        try:
            logger.debug(f"Attempting to read file: {self.file_path}")
            logger.debug(f"File exists: {self.file_path.exists()}")

            with open(self.file_path, "rb") as file:
                logger.debug("File opened successfully")
                # Parse the @graph array
                parser = ijson.items(file, "@graph.item")

                chunk_count = 0
                for item in parser:
                    self.process_chunk(item)
                    chunk_count += 1

                    if chunk_count % 100 == 0:
                        logger.debug(f"Processed {chunk_count} chunks")

                    if max_chunks is not None and chunk_count >= max_chunks:
                        break

                logger.info(f"Total chunks processed: {chunk_count}")

        except Exception as e:
            logger.exception("Error reading ontology file")

    def get_field_options(self, field_name: str) -> List[str]:
        """Get the list of valid options for a given field."""
        return sorted(list(self.field_options.get(field_name, set())))

    def get_all_fields(self) -> List[str]:
        """Get a list of all fields that have options."""
        return sorted(list(self.field_options.keys()))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Read and extract options from an RDF/OWL ontology in JSON-LD format"
    )
    parser.add_argument("--field", type=str, help="Field name to get options for")
    parser.add_argument(
        "--list-fields", action="store_true", help="List all available fields"
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=1000,
        help="Maximum number of chunks to process (default: 1000)",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="/home/ubuntu/projects/data/pz-nf-testing-data/schema/NF.jsonid",
        help="Path to the ontology file",
    )

    args = parser.parse_args()

    # Create reader and process chunks
    reader = OntologyReader(args.file)
    reader.read_ontology(max_chunks=args.max_chunks)

    if args.list_fields:
        logger.info("\nAvailable fields:")
        for field in reader.get_all_fields():
            logger.info(f"- {field}")

    if args.field:
        options = reader.get_field_options(args.field)
        if options:
            logger.info(f"\nOptions for {args.field}:")
            for option in options:
                logger.info(f"- {option}")
        else:
            logger.warning(f"\nNo options found for field: {args.field}")

    if not args.list_fields and not args.field:
        parser.print_help()
