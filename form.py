""" Get entries from form 
    Version 3: 
        - support submit almost all types of google form fields
        - support multi-page forms
        - not support upload file (because it's required to login)
        - improved type hints, error handling, and code organization
    Date: 2025-11-27
"""

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
from urllib.parse import urlparse, parse_qs

import requests

import generator

# Constants for form data extraction
ALL_DATA_FIELDS = "FB_PUBLIC_LOAD_DATA_"
FORM_SESSION_TYPE_ID = 8
ANY_TEXT_FIELD = "ANY TEXT!!"

# Form field type constants
FIELD_TYPE_SHORT_ANSWER = 0
FIELD_TYPE_PARAGRAPH = 1
FIELD_TYPE_MULTIPLE_CHOICE = 2
FIELD_TYPE_DROPDOWN = 3
FIELD_TYPE_CHECKBOXES = 4
FIELD_TYPE_LINEAR_SCALE = 5
FIELD_TYPE_GRID_CHOICE = 7
FIELD_TYPE_DATE = 9
FIELD_TYPE_TIME = 10

# Email collection modes
EMAIL_NOT_COLLECTED = 1
EMAIL_VERIFIED_REQUIRED = 2
EMAIL_RESPONDER_INPUT = 3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FormEntry:
    """Represents a single form entry/field."""
    id: Union[str, int]
    container_name: str
    type: Union[int, str]
    required: bool
    name: Optional[str] = None
    options: Optional[Union[List[str], str]] = None
    default_value: Optional[Union[str, List[str]]] = None

# --------- Helper Functions --------- #

def extract_form_id(url: str) -> Optional[str]:
    """
    Extract the form ID from a Google Form URL.
    
    Args:
        url: The Google Form URL
    
    Returns:
        The form ID string, or None if not found
    
    Example:
        >>> extract_form_id('https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform')
        '1FAIpQLSc...'
    """
    try:
        # Pattern for form ID in URL
        match = re.search(r'/forms/d/e/([^/]+)', url)
        if match:
            return match.group(1)
        
        # Alternative pattern
        match = re.search(r'/forms/d/([^/]+)', url)
        if match:
            return match.group(1)
        
        return None
    except Exception as e:
        logger.debug(f"Could not extract form ID: {e}")
        return None

def generate_output_filename(url: str, output_dir: str = "form_outputs", extension: str = "txt") -> str:
    """
    Generate a unique output filename based on form ID and timestamp.
    
    Args:
        url: The Google Form URL
        output_dir: Directory to save the file in
        extension: File extension (without dot)
    
    Returns:
        Full path to the output file
    """
    # Extract form ID
    form_id = extract_form_id(url)
    if form_id:
        # Truncate long IDs for readability
        if len(form_id) > 20:
            form_id = form_id[:20]
        filename = f"form_{form_id}"
    else:
        filename = "form_output"
    
    # Add timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}.{extension}"
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    return os.path.join(output_dir, filename)

def normalize_form_url(url: str) -> str:
    """
    Convert any Google Form URL (edit, viewform, etc.) to viewform URL.
    
    Args:
        url: The Google Form URL (edit, viewform, or form ID)
    
    Returns:
        The viewform URL
    
    Example:
        >>> normalize_form_url('https://docs.google.com/forms/d/ABC123/edit')
        'https://docs.google.com/forms/d/ABC123/viewform'
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    
    # Remove query parameters and fragments
    if '?' in url:
        url = url.split('?')[0]
    if '#' in url:
        url = url.split('#')[0]
    
    # Replace /edit with /viewform
    url = url.replace('/edit', '/viewform')
    
    # If it doesn't have viewform or formResponse, add viewform
    if '/viewform' not in url and '/formResponse' not in url:
        if not url.endswith('/'):
            url += '/'
        url += 'viewform'
    
    return url


def get_form_response_url(url: str) -> str:
    """
    Convert a Google Form view URL to its corresponding form response URL.
    
    Args:
        url: The Google Form URL (can be edit, viewform, or any valid form URL)
    
    Returns:
        The form response URL for submitting data
    
    Example:
        >>> get_form_response_url('https://docs.google.com/forms/d/e/ABC/viewform')
        'https://docs.google.com/forms/d/e/ABC/formResponse'
        >>> get_form_response_url('https://docs.google.com/forms/d/ABC/edit')
        'https://docs.google.com/forms/d/ABC/formResponse'
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    
    # First normalize to viewform
    url = normalize_form_url(url)
    
    # Then convert to formResponse
    url = url.replace('/viewform', '/formResponse')
    if not url.endswith('/formResponse'):
        if not url.endswith('/'):
            url += '/'
        url += 'formResponse'
    return url

def extract_script_variables(name: str, html: str) -> Optional[Any]:
    """
    Extract JavaScript variables from HTML content.
    
    Args:
        name: The variable name to extract
        html: The HTML content containing the JavaScript variable
    
    Returns:
        The parsed variable value, or None if extraction fails
    """
    if not name or not html:
        logger.warning("Variable name or HTML content is empty")
        return None
    
    pattern = re.compile(r'var\s' + re.escape(name) + r'\s*=\s*(\[[\s\S]*?\]);')
    match = pattern.search(html)
    if not match:
        logger.debug(f"Variable '{name}' not found in HTML")
        return None
    
    value_str = match.group(1)
    try:
        return json.loads(value_str)
    except json.JSONDecodeError as e:
        logger.debug(f"JSON parsing failed: {e}, trying ast.literal_eval")
        try:
            import ast
            return ast.literal_eval(value_str)
        except Exception as ast_error:
            logger.error(f"Failed to parse variable '{name}': {ast_error}")
            return None

def get_fb_public_load_data(url: str) -> Optional[Any]:
    """
    Fetch and extract form data from a Google Form URL.
    
    Args:
        url: The Google Form URL (will be normalized to viewform)
    
    Returns:
        The extracted form data, or None if the request fails
    
    Raises:
        ValueError: If the URL is invalid
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    
    if not url.startswith('http'):
        raise ValueError("URL must start with http:// or https://")
    
    # Normalize URL (handles /edit URLs and query parameters)
    url = normalize_form_url(url)
    logger.info(f"Fetching form from: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        logger.info(f"Successfully fetched URL - Status Code: {response.status_code}")
        
        data = extract_script_variables(ALL_DATA_FIELDS, response.text)
        if not data:
            logger.error(f"Failed to extract {ALL_DATA_FIELDS} from the response")
            logger.info("The form may require login or the URL format has changed")
        return data
    except requests.Timeout:
        logger.error(f"Request timed out after 15 seconds")
        return None
    except requests.HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching URL: {e}")
        return None

# ------ MAIN LOGIC ------ #

def parse_form_entries(url: str, only_required: bool = False) -> Optional[List[Dict[str, Any]]]:
    """
    Parse form entries from a Google Form URL.
    
    Extracts form field information from window.FB_PUBLIC_LOAD_DATA_:
    - v[1][1]: form entries array
    - For each entry x in v[1][1]:
        - x[0]: entry container ID
        - x[1]: entry name
        - x[3]: entry type (see FIELD_TYPE_* constants)
        - x[4]: array of sub-entries (multiple for Grid/Linear Scale)
            - x[4][0]: entry ID for request
            - x[4][1]: array of entry value options (null for text fields)
            - x[4][2]: required flag (1=required, 0=optional)
            - x[4][3]: names for Grid Choice/Linear Scale
    - v[1][10][6]: email collection mode (see EMAIL_* constants)
    
    Args:
        url: The Google Form URL
        only_required: If True, only parse required fields
    
    Returns:
        List of parsed form entries as dictionaries, or None if parsing fails
    """
    try:
        url = get_form_response_url(url)
    except ValueError as e:
        logger.error(f"Invalid URL: {e}")
        return None
    
    v = get_fb_public_load_data(url)
    if not v:
        logger.error("Failed to get form data")
        return None
    
    if not isinstance(v, list) or len(v) < 2 or not v[1]:
        logger.error("Unexpected form data structure")
        return None
    
    if not v[1][1]:
        logger.error("No form entries found. Login may be required.")
        return None
    
    def parse_entry(entry: List[Any]) -> List[Dict[str, Any]]:
        """Parse a single form entry into structured data."""
        if not entry or len(entry) < 5:
            logger.warning("Skipping malformed entry")
            return []
        
        entry_name = entry[1] or "Unnamed Field"
        entry_type_id = entry[3]
        result = []
        
        for sub_entry in entry[4]:
            if not sub_entry or len(sub_entry) < 3:
                logger.warning(f"Skipping malformed sub-entry in '{entry_name}'")
                continue
            
            info = {
                "id": sub_entry[0],
                "container_name": entry_name,
                "type": entry_type_id,
                "required": sub_entry[2] == 1,
                "name": ' - '.join(sub_entry[3]) if (len(sub_entry) > 3 and sub_entry[3]) else None,
                "options": [(x[0] or ANY_TEXT_FIELD) for x in sub_entry[1]] if sub_entry[1] else None,
            }
            
            if only_required and not info['required']:
                continue
            result.append(info)
        return result

    parsed_entries = []
    page_count = 0
    
    for entry in v[1][1]:
        if not entry or len(entry) < 4:
            logger.warning("Skipping invalid entry")
            continue
        
        if entry[3] == FORM_SESSION_TYPE_ID:
            page_count += 1
            continue
        
        parsed_entries.extend(parse_entry(entry))
    
    # Handle email collection
    try:
        email_mode = v[1][10][6] if (len(v[1]) > 10 and v[1][10] and len(v[1][10]) > 6) else EMAIL_NOT_COLLECTED
        if email_mode > EMAIL_NOT_COLLECTED:
            parsed_entries.append({
                "id": "emailAddress",
                "container_name": "Email Address",
                "type": "required",
                "required": True,
                "options": "email address",
            })
            logger.info("Email address collection is enabled for this form")
    except (IndexError, TypeError) as e:
        logger.debug(f"Could not determine email collection mode: {e}")
    
    # Handle multi-page forms
    if page_count > 0:
        page_history = ','.join(map(str, range(page_count + 1)))
        parsed_entries.append({
            "id": "pageHistory",
            "container_name": "Page History",
            "type": "required",
            "required": False,
            "options": f"from 0 to {page_count}",
            "default_value": page_history
        })
        logger.info(f"Multi-page form detected: {page_count + 1} pages")
    
    logger.info(f"Successfully parsed {len(parsed_entries)} form entries")
    return parsed_entries

def fill_form_entries(
    entries: List[Dict[str, Any]], 
    fill_algorithm: Callable[[Union[int, str], Union[str, int], List[str], bool, str], Union[str, List[str]]]
) -> List[Dict[str, Any]]:
    """
    Fill form entries using the provided algorithm.
    
    Args:
        entries: List of parsed form entries
        fill_algorithm: Function that takes (type_id, entry_id, options, required, entry_name)
                       and returns a value to fill the field with
    
    Returns:
        The same entries list with default_value fields populated
    
    Note:
        Entries that already have a default_value will not be modified.
        The ANY_TEXT_FIELD placeholder is filtered from options before calling fill_algorithm.
    """
    if not entries:
        logger.warning("No entries to fill")
        return entries
    
    if not callable(fill_algorithm):
        raise TypeError("fill_algorithm must be callable")
    
    for entry in entries:
        if entry.get('default_value'):
            continue
        
        # Remove ANY_TEXT_FIELD from options to prevent choosing it
        options = (entry.get('options') or [])[:]
        if isinstance(options, list) and ANY_TEXT_FIELD in options:
            options.remove(ANY_TEXT_FIELD)
        
        try:
            entry['default_value'] = fill_algorithm(
                entry['type'], 
                entry['id'], 
                options,
                required=entry['required'], 
                entry_name=entry['container_name']
            )
        except Exception as e:
            logger.error(f"Error filling entry '{entry['container_name']}': {e}")
            entry['default_value'] = ''
    
    return entries

# ------ OUTPUT ------ #

def get_form_submit_request(
    url: str,
    output: str = "console",
    only_required: bool = False,
    with_comment: bool = True,
    fill_algorithm: Optional[Callable] = None,
) -> Optional[str]:
    """
    Generate form submission request body data.
    
    Args:
        url: The Google Form URL
        output: Output mode - "console" (print), "return" (return string), or file path (save to file)
        only_required: If True, only include required fields
        with_comment: If True, include explanatory comments for each field
        fill_algorithm: Optional function to automatically fill form values
    
    Returns:
        The generated request body as a string (if output="return"), otherwise None
    
    Raises:
        ValueError: If the URL is invalid or output mode is invalid
        IOError: If file writing fails
    """
    logger.info(f"Processing form: {url}")
    
    entries = parse_form_entries(url, only_required=only_required)
    if not entries:
        logger.error("Failed to parse form entries")
        return None
    
    if fill_algorithm:
        logger.info("Filling form entries with provided algorithm")
        entries = fill_form_entries(entries, fill_algorithm)
    
    result = generator.generate_form_request_dict(entries, with_comment)
    
    if output == "console":
        print(result)
        return None
    elif output == "return":
        return result
    else:
        # Save to file
        try:
            # Handle different output modes
            if output == "auto":
                # Auto-generate filename in form_outputs folder
                output_path = generate_output_filename(url)
            elif os.path.isdir(output) or output.endswith(os.sep) or output.endswith('/'):
                # If output is a directory, generate filename in that directory
                output_path = generate_output_filename(url, output_dir=output.rstrip(os.sep + '/'))
            else:
                # Use the provided path directly
                output_path = output
                # Create parent directory if it doesn't exist
                parent_dir = os.path.dirname(output_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
            
            # Write the file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result)
            
            # Get absolute path for display
            abs_path = os.path.abspath(output_path)
            logger.info(f"Successfully saved to: {abs_path}")
            print(f"\n✓ File saved to: {abs_path}")
            
        except IOError as e:
            logger.error(f"Failed to write to file '{output}': {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while saving file: {e}")
            raise
    return None



if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Google Form Entry Parser and Request Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -o auto
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -o my_forms/
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -o output/form.txt
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -r -c --verbose

Output modes:
  console        : Print to console (default)
  auto           : Auto-generate filename in 'form_outputs' folder
  folder/        : Auto-generate filename in specified folder
  path/file.txt  : Save to specific file path
        """
    )
    parser.add_argument(
        "url", 
        help="Google Form URL (viewform or formResponse URL)"
    )
    parser.add_argument(
        "-o", "--output", 
        default="console", 
        metavar="PATH",
        help="Output: 'console' (default), 'auto', folder path, or file path"
    )
    parser.add_argument(
        "-r", "--required", 
        action="store_true", 
        help="Only include required fields"
    )
    parser.add_argument(
        "-c", "--no-comment", 
        action="store_true", 
        help="Don't include explanatory comments for each field"
    )
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true", 
        help="Enable verbose logging output"
    )
    
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    try:
        get_form_submit_request(
            args.url, 
            args.output, 
            args.required, 
            not args.no_comment
        )
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        exit(1)