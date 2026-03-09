# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Curator Workflows Metadata Clients

This package provides clients for interacting with the Curator workflow API endpoints.
"""

# Import all client classes and utility functions for easy access
from .base_client import BaseClient
from .extract_client import ExtractMetadataClient
from .fix_client import FixMetadataClient
from .transform_client import TransformMetadataClient
from .utils import (
    analyze_batch_results,
    batch_status_callback,
    combine_batch_results,
    default_status_callback,
    detailed_status_callback,
    display_extraction_results,
    download_results,
    extract_entity_filenames_from_csv,
    get_file_info,
    load_entity_filenames_from_directory,
    map_files_to_entities,
)
