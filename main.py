"""
Google Form Auto-Fill and Submit Tool
Version 2.0 - Enhanced with better error handling, custom fill strategies, and submission tracking
Date: 2025-11-27
"""

import argparse
import datetime
import json
import logging
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Union

import requests

import form

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ========== Fill Strategies ========== #

class FillStrategy:
    """Base class for form filling strategies."""
    
    def __init__(self, email: str = "test@example.com", custom_values: Optional[Dict] = None, age_range: Optional[str] = None):
        """
        Initialize fill strategy.
        
        Args:
            email: Email address to use for email fields
            custom_values: Dictionary of entry_id -> value mappings for custom values
            age_range: Age range in format "min-max" (e.g., "18-25")
        """
        self.email = email
        self.custom_values = custom_values or {}
        self.age_min = None
        self.age_max = None
        
        # Parse age range if provided
        if age_range:
            self._parse_age_range(age_range)
    
    def _parse_age_range(self, age_range: str) -> None:
        """Parse age range string like '18-25' into min and max values."""
        try:
            parts = age_range.split('-')
            if len(parts) != 2:
                raise ValueError(f"Invalid age range format: {age_range}. Use format: 'min-max' (e.g., '18-25')")
            
            self.age_min = int(parts[0].strip())
            self.age_max = int(parts[1].strip())
            
            if self.age_min > self.age_max:
                raise ValueError(f"Minimum age ({self.age_min}) cannot be greater than maximum age ({self.age_max})")
            
            if self.age_min < 0 or self.age_max > 150:
                raise ValueError(f"Age values must be between 0 and 150")
            
            logger.info(f"Age range set to: {self.age_min}-{self.age_max} years")
        except ValueError as e:
            logger.error(f"Error parsing age range: {e}")
            raise
    
    def _is_age_field(self, entry_name: str) -> bool:
        """Check if the field name indicates an age field."""
        if not entry_name:
            return False
        
        entry_name_lower = entry_name.lower()
        age_keywords = ['age', 'umur', 'usia', 'tahun', 'edad', 'alter']
        
        return any(keyword in entry_name_lower for keyword in age_keywords)
    
    def _generate_age(self) -> str:
        """Generate a random age within the specified range."""
        if self.age_min is not None and self.age_max is not None:
            return str(random.randint(self.age_min, self.age_max))
        else:
            # Default age range if not specified
            return str(random.randint(18, 65))
    
    def fill(self, type_id: Union[int, str], entry_id: Union[str, int], 
             options: List[str], required: bool = False, entry_name: str = '') -> Union[str, List[str]]:
        """
        Fill a form entry with appropriate value.
        
        Args:
            type_id: Form field type ID
            entry_id: Entry ID
            options: Available options for the field
            required: Whether the field is required
            entry_name: Name/label of the entry
        
        Returns:
            Value to fill the field with
        """
        raise NotImplementedError("Subclasses must implement fill method")


class RandomFillStrategy(FillStrategy):
    """Fill form fields with random values."""
    
    def fill(self, type_id: Union[int, str], entry_id: Union[str, int], 
             options: List[str], required: bool = False, entry_name: str = '') -> Union[str, List[str]]:
        """Fill with random values."""
        # Check for custom values first
        if str(entry_id) in self.custom_values:
            return self.custom_values[str(entry_id)]
        
        # Handle email address
        if entry_id == 'emailAddress':
            return self.email
        
        # Handle different field types
        if type_id in [form.FIELD_TYPE_SHORT_ANSWER, form.FIELD_TYPE_PARAGRAPH]:
            if not required:
                return ''
            
            # Check if this is an age field
            if self._is_age_field(entry_name):
                return self._generate_age()
            
            responses = [
                'This is a test response',
                'Automated form submission',
                'Sample answer',
                'Test data entry',
                'Generated response'
            ]
            return random.choice(responses)
        
        if type_id == form.FIELD_TYPE_MULTIPLE_CHOICE:
            return random.choice(options) if options else ''
        
        if type_id == form.FIELD_TYPE_DROPDOWN:
            return random.choice(options) if options else ''
        
        if type_id == form.FIELD_TYPE_CHECKBOXES:
            if not options:
                return []
            num_selections = random.randint(1, min(len(options), 3))
            return random.sample(options, k=num_selections)
        
        if type_id == form.FIELD_TYPE_LINEAR_SCALE:
            return random.choice(options) if options else ''
        
        if type_id == form.FIELD_TYPE_GRID_CHOICE:
            return random.choice(options) if options else ''
        
        if type_id == form.FIELD_TYPE_DATE:
            return datetime.date.today().strftime('%Y-%m-%d')
        
        if type_id == form.FIELD_TYPE_TIME:
            return datetime.datetime.now().strftime('%H:%M')
        
        return ''


class FixedFillStrategy(FillStrategy):
    """Fill form fields with fixed values."""
    
    def __init__(self, email: str = "test@example.com", 
                 text_value: str = "Fixed response", 
                 custom_values: Optional[Dict] = None,
                 age_range: Optional[str] = None):
        """
        Initialize with fixed values.
        
        Args:
            email: Email address
            text_value: Fixed text to use for text fields
            custom_values: Custom value mappings
            age_range: Age range in format "min-max"
        """
        super().__init__(email, custom_values, age_range)
        self.text_value = text_value
    
    def fill(self, type_id: Union[int, str], entry_id: Union[str, int], 
             options: List[str], required: bool = False, entry_name: str = '') -> Union[str, List[str]]:
        """Fill with fixed values."""
        # Check for custom values first
        if str(entry_id) in self.custom_values:
            return self.custom_values[str(entry_id)]
        
        if entry_id == 'emailAddress':
            return self.email
        
        if type_id in [form.FIELD_TYPE_SHORT_ANSWER, form.FIELD_TYPE_PARAGRAPH]:
            if not required:
                return ''
            
            # Check if this is an age field
            if self._is_age_field(entry_name):
                return self._generate_age()
            
            return self.text_value
        
        if type_id in [form.FIELD_TYPE_MULTIPLE_CHOICE, form.FIELD_TYPE_DROPDOWN, 
                       form.FIELD_TYPE_LINEAR_SCALE, form.FIELD_TYPE_GRID_CHOICE]:
            return options[0] if options else ''
        
        if type_id == form.FIELD_TYPE_CHECKBOXES:
            return [options[0]] if options else []
        
        if type_id == form.FIELD_TYPE_DATE:
            return datetime.date.today().strftime('%Y-%m-%d')
        
        if type_id == form.FIELD_TYPE_TIME:
            return datetime.datetime.now().strftime('%H:%M')
        
        return ''


# Legacy function for backward compatibility
def fill_random_value(type_id, entry_id, options, required=False, entry_name=''):
    """
    Legacy fill function for backward compatibility.
    
    Note: Use RandomFillStrategy class instead for better control.
    """
    strategy = RandomFillStrategy()
    return strategy.fill(type_id, entry_id, options, required, entry_name)



# ========== Core Functions ========== #

def generate_request_body(
    url: str, 
    only_required: bool = False,
    fill_strategy: Optional[FillStrategy] = None,
    custom_values: Optional[Dict] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate form request body data.
    
    Args:
        url: Google Form URL
        only_required: Only include required fields
        fill_strategy: Strategy to use for filling values
        custom_values: Custom values for specific fields
    
    Returns:
        Dictionary containing form data ready for submission
    """
    try:
        if fill_strategy is None:
            fill_strategy = RandomFillStrategy(custom_values=custom_values)
        
        data = form.get_form_submit_request(
            url,
            only_required=only_required,
            fill_algorithm=fill_strategy.fill,
            output="return",
            with_comment=False
        )
        
        if not data:
            logger.error("Failed to generate request body")
            return None
        
        parsed_data = json.loads(data)
        logger.info(f"Generated request body with {len(parsed_data)} fields")
        return parsed_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse generated data: {e}")
        return None
    except Exception as e:
        logger.error(f"Error generating request body: {e}")
        return None


def get_page_count(url: str) -> int:
    """
    Get the number of pages in a Google Form.
    
    Args:
        url: Google Form URL
    
    Returns:
        Number of pages in the form (0 if single page or error)
    """
    try:
        entries = form.parse_form_entries(url, only_required=False)
        if not entries:
            return 0
        
        # Check for pageHistory entry
        for entry in entries:
            if entry.get('id') == 'pageHistory':
                page_history = entry.get('default_value', '')
                if page_history:
                    # Count pages from pageHistory (e.g., "0,1,2" = 3 pages)
                    return len(page_history.split(','))
        
        return 0
    except Exception as e:
        logger.debug(f"Error getting page count: {e}")
        return 0


def submit_form(url: str, data: Dict[str, Any], timeout: int = 10, verify_ssl: bool = True) -> bool:
    """
    Submit form data to Google Forms.
    
    Args:
        url: Google Form URL
        data: Form data dictionary
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
    
    Returns:
        True if submission was successful, False otherwise
    """
    try:
        response_url = form.get_form_response_url(url)
        logger.info(f"Submitting to: {response_url}")
        logger.debug(f"Data: {json.dumps(data, indent=2)}")
        
        response = requests.post(
            response_url, 
            data=data, 
            timeout=timeout,
            verify=verify_ssl,
            allow_redirects=True
        )
        
        # Google Forms typically returns 200 for both success and some errors
        if response.status_code == 200:
            # Check multiple indicators of success
            response_text = response.text.lower()
            
            # Check for success indicators in the response
            success_indicators = [
                'your response has been recorded' in response_text,
                'thank you' in response_text,
                'formResponse' in response.url,
                'closedform' in response.url,
            ]
            
            # Check for error indicators
            error_indicators = [
                'error' in response_text and 'submit' in response_text,
                'invalid' in response_text,
                'formrestricted' in response.url,
            ]
            
            if any(success_indicators) and not any(error_indicators):
                logger.info("✓ Form submitted successfully!")
                return True
            elif any(error_indicators):
                logger.error("Form submission rejected (form may be restricted or have validation errors)")
                logger.debug(f"Response URL: {response.url}")
                logger.debug(f"Response snippet: {response.text[:500]}")
                return False
            else:
                # Ambiguous response - treat as success if status is 200
                logger.info("✓ Form submitted (status 200 received)")
                logger.debug(f"Response URL: {response.url}")
                return True
        else:
            logger.error(f"Submission failed with status code: {response.status_code}")
            logger.debug(f"Response: {response.text[:500]}")
            return False
            
    except requests.Timeout:
        logger.error(f"Request timed out after {timeout} seconds")
        return False
    except requests.RequestException as e:
        logger.error(f"Network error during submission: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during submission: {e}")
        return False


def submit_form_progressive(
    url: str,
    data: Dict[str, Any],
    page_delay: float = 0.5,
    timeout: int = 10,
    verify_ssl: bool = True
) -> bool:
    """
    Submit multi-page form progressively, simulating clicking "Next" button on each page.
    
    This function splits the submission into multiple requests, one for each page,
    which more closely mimics how a user would interact with the form.
    
    Args:
        url: Google Form URL
        data: Complete form data dictionary
        page_delay: Delay between page submissions in seconds
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
    
    Returns:
        True if all pages were submitted successfully, False otherwise
    """
    try:
        # Check if this is a multi-page form
        page_count = get_page_count(url)
        
        if page_count <= 1:
            # Single page form, use normal submission
            logger.debug("Single page form detected, using normal submission")
            return submit_form(url, data, timeout, verify_ssl)
        
        logger.info(f"Multi-page form detected with {page_count} pages")
        logger.info("Submitting progressively (simulating 'Next' button clicks)...")
        
        response_url = form.get_form_response_url(url)
        
        # Submit each page
        for page_num in range(page_count):
            logger.info(f"📄 Submitting page {page_num + 1}/{page_count}...")
            
            # Create page-specific data
            page_data = data.copy()
            
            # Update pageHistory to show progression
            current_history = ','.join(map(str, range(page_num + 1)))
            page_data['pageHistory'] = current_history
            
            # For pages before the last one, we're just navigating
            is_final_page = (page_num == page_count - 1)
            
            try:
                response = requests.post(
                    response_url,
                    data=page_data,
                    timeout=timeout,
                    verify=verify_ssl,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    # For final page, check success indicators
                    if is_final_page:
                        response_text = response.text.lower()
                        success_indicators = [
                            'your response has been recorded' in response_text,
                            'thank you' in response_text,
                            'formResponse' in response.url,
                        ]
                        
                        if any(success_indicators):
                            logger.info(f"✓ Page {page_num + 1}/{page_count} submitted (Final page - Success!)")
                        else:
                            logger.info(f"✓ Page {page_num + 1}/{page_count} submitted (Final page)")
                    else:
                        logger.info(f"✓ Page {page_num + 1}/{page_count} submitted (Next)")
                        # Delay before next page
                        if page_delay > 0:
                            time.sleep(page_delay)
                else:
                    logger.error(f"Failed to submit page {page_num + 1} (Status: {response.status_code})")
                    logger.debug(f"Response snippet: {response.text[:300]}")
                    return False
                    
            except requests.RequestException as e:
                logger.error(f"Error submitting page {page_num + 1}: {e}")
                return False
        
        logger.info("✓ All pages submitted successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error in progressive submission: {e}")
        return False


def submit_multiple(
    url: str, 
    count: int = 1, 
    delay: float = 1.0,
    only_required: bool = False,
    fill_strategy: Optional[FillStrategy] = None,
    save_responses: bool = False,
    progressive: bool = False
) -> Dict[str, int]:
    """
    Submit form multiple times.
    
    Args:
        url: Google Form URL
        count: Number of times to submit
        delay: Delay between submissions in seconds
        only_required: Only fill required fields
        fill_strategy: Strategy for filling values
        save_responses: Save generated responses to file
        progressive: Use progressive page-by-page submission for multi-page forms
    
    Returns:
        Dictionary with submission statistics
    """
    stats = {
        'total': count,
        'successful': 0,
        'failed': 0,
        'responses': []
    }
    
    logger.info(f"Starting batch submission: {count} submissions with {delay}s delay")
    if progressive:
        logger.info("Progressive mode enabled (page-by-page submission)")
    
    for i in range(count):
        logger.info(f"\n--- Submission {i + 1}/{count} ---")
        
        try:
            # Generate new data for each submission
            data = generate_request_body(url, only_required, fill_strategy)
            if not data:
                logger.error("Failed to generate request body")
                stats['failed'] += 1
                continue
            
            if save_responses:
                stats['responses'].append(data)
            
            # Submit (choose method based on progressive flag)
            if progressive:
                success = submit_form_progressive(url, data)
            else:
                success = submit_form(url, data)
            
            if success:
                stats['successful'] += 1
            else:
                stats['failed'] += 1
            
            # Delay before next submission (except for last one)
            if i < count - 1 and delay > 0:
                logger.debug(f"Waiting {delay}s before next submission...")
                time.sleep(delay)
                
        except KeyboardInterrupt:
            logger.warning("\nBatch submission interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error in submission {i + 1}: {e}")
            stats['failed'] += 1
    
    # Save responses if requested
    if save_responses and stats['responses']:
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"form_outputs/responses_{timestamp}.json"
            os.makedirs("form_outputs", exist_ok=True)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(stats['responses'], f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(stats['responses'])} responses to: {filename}")
        except Exception as e:
            logger.error(f"Failed to save responses: {e}")
    
    return stats


def main(
    url: str, 
    only_required: bool = False,
    email: str = "test@example.com",
    custom_values: Optional[Dict] = None,
    count: int = 1,
    delay: float = 1.0,
    strategy: str = "random",
    save_responses: bool = False,
    dry_run: bool = False,
    progressive: bool = False,
    age_range: Optional[str] = None
) -> bool:
    """
    Main function to fill and submit Google Form.
    
    Args:
        url: Google Form URL
        only_required: Only fill required fields
        email: Email address for email fields
        custom_values: Custom values for specific fields
        count: Number of submissions
        delay: Delay between submissions
        strategy: Fill strategy ('random' or 'fixed')
        save_responses: Save generated responses
        dry_run: Generate data but don't submit
        progressive: Use progressive page-by-page submission for multi-page forms
        age_range: Age range in format "min-max" (e.g., "18-25")
    
    Returns:
        True if all submissions were successful
    """
    try:
        # Create fill strategy
        if strategy == "fixed":
            fill_strat = FixedFillStrategy(email=email, custom_values=custom_values, age_range=age_range)
        else:
            fill_strat = RandomFillStrategy(email=email, custom_values=custom_values, age_range=age_range)
        
        # Check if this is a multi-page form
        page_count = get_page_count(url)
        if page_count > 1 and not dry_run:
            if progressive:
                logger.info(f"🔄 Multi-page form detected ({page_count} pages) - Progressive mode enabled")
            else:
                logger.info(f"📄 Multi-page form detected ({page_count} pages) - Using standard submission")
                logger.info(f"💡 Tip: Use --progressive flag for page-by-page submission simulation")
        
        # Dry run mode - just show what would be submitted
        if dry_run:
            logger.info("=== DRY RUN MODE - No actual submission ===")
            data = generate_request_body(url, only_required, fill_strat, custom_values)
            if data:
                print("\nGenerated form data:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                if page_count > 1:
                    print(f"\nℹ️  This is a multi-page form with {page_count} pages")
                    print(f"   pageHistory field: {data.get('pageHistory', 'N/A')}")
                return True
            return False
        
        # Single submission
        if count == 1:
            data = generate_request_body(url, only_required, fill_strat, custom_values)
            if not data:
                return False
            
            if save_responses:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"form_outputs/response_{timestamp}.json"
                os.makedirs("form_outputs", exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved response to: {filename}")
            
            # Choose submission method
            if progressive:
                success = submit_form_progressive(url, data)
            else:
                success = submit_form(url, data)
            
            if success:
                logger.info("\n✓ Done! Form submitted successfully.")
            else:
                logger.error("\n✗ Failed to submit form.")
            return success
        
        # Multiple submissions
        else:
            stats = submit_multiple(
                url, count, delay, only_required, 
                fill_strat, save_responses, progressive
            )
            
            logger.info(f"\n{'='*50}")
            logger.info("SUBMISSION SUMMARY")
            logger.info(f"{'='*50}")
            logger.info(f"Total attempts:  {stats['total']}")
            logger.info(f"Successful:      {stats['successful']} ✓")
            logger.info(f"Failed:          {stats['failed']} ✗")
            logger.info(f"Success rate:    {stats['successful']/stats['total']*100:.1f}%")
            logger.info(f"{'='*50}")
            
            return stats['failed'] == 0
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if logger.level == logging.DEBUG:
            import traceback
            traceback.print_exc()
        return False



# ========== Command Line Interface ========== #

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Google Form Auto-Fill and Submit Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Submit form once with random values
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform
  
  # Submit only required fields
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -r
  
  # Submit with custom email
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --email myemail@gmail.com
  
  # Submit with age range for age/umur fields
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --age-range "18-25"
  
  # Submit multiple times with delay
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --count 5 --delay 2
  
  # Use fixed values instead of random
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --strategy fixed
  
  # Dry run (generate data but don't submit)
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --dry-run
  
  # Save generated responses to file
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --save-responses
  
  # Load custom values from JSON file
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --custom-file values.json
  
  # Verbose mode for debugging
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform -v
  
  # Progressive mode for multi-page forms (simulates clicking "Next" button)
  %(prog)s https://docs.google.com/forms/d/e/ABC123/viewform --progressive

Custom values JSON format:
  {
    "entry.123456": "Custom value",
    "entry.789012": ["Option 1", "Option 2"]
  }
        """
    )
    
    # Required arguments
    parser.add_argument(
        'url', 
        help='Google Form URL (viewform or formResponse)'
    )
    
    # Fill options
    fill_group = parser.add_argument_group('Fill Options')
    fill_group.add_argument(
        '-r', '--required', 
        action='store_true', 
        help='Only fill required fields'
    )
    fill_group.add_argument(
        '--email', 
        default='test@example.com',
        help='Email address for email fields (default: test@example.com)'
    )
    fill_group.add_argument(
        '--strategy',
        choices=['random', 'fixed'],
        default='random',
        help='Fill strategy: random or fixed values (default: random)'
    )
    fill_group.add_argument(
        '--custom-file',
        metavar='FILE',
        help='JSON file with custom field values'
    )
    fill_group.add_argument(
        '--age-range',
        metavar='MIN-MAX',
        help='Age range for age/umur fields (e.g., "18-25", "20-30")'
    )
    
    # Submission options
    submit_group = parser.add_argument_group('Submission Options')
    submit_group.add_argument(
        '--count',
        type=int,
        default=1,
        metavar='N',
        help='Number of times to submit the form (default: 1)'
    )
    submit_group.add_argument(
        '--delay',
        type=float,
        default=1.0,
        metavar='SEC',
        help='Delay between submissions in seconds (default: 1.0)'
    )
    submit_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate form data but do not submit'
    )
    submit_group.add_argument(
        '--progressive',
        action='store_true',
        help='Use progressive page-by-page submission for multi-page forms (simulates "Next" button)'
    )
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--save-responses',
        action='store_true',
        help='Save generated responses to JSON file in form_outputs/'
    )
    output_group.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging output'
    )
    output_group.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Minimal output (errors only)'
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Load custom values from file if provided
    custom_values = None
    if args.custom_file:
        try:
            if not os.path.exists(args.custom_file):
                logger.error(f"Custom values file not found: {args.custom_file}")
                sys.exit(1)
            
            with open(args.custom_file, 'r', encoding='utf-8') as f:
                custom_values = json.load(f)
            logger.info(f"Loaded {len(custom_values)} custom values from {args.custom_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in custom values file: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error loading custom values file: {e}")
            sys.exit(1)
    
    # Validate arguments
    if args.count < 1:
        logger.error("Count must be at least 1")
        sys.exit(1)
    
    if args.delay < 0:
        logger.error("Delay cannot be negative")
        sys.exit(1)
    
    # Run main function
    try:
        success = main(
            url=args.url,
            only_required=args.required,
            email=args.email,
            custom_values=custom_values,
            count=args.count,
            delay=args.delay,
            strategy=args.strategy,
            save_responses=args.save_responses,
            dry_run=args.dry_run,
            progressive=args.progressive,
            age_range=args.age_range
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
