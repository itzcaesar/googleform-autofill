"""
Multi-page Google Form Progressive Submission Example

This example demonstrates how to submit a multi-page Google Form
using the progressive mode, which simulates clicking the "Next" button
on each page before final submission.

Progressive mode is useful when:
1. You want to mimic real user behavior more closely
2. The form has client-side validation on each page
3. You want to ensure each page is processed separately
"""

import sys
import os

# Add parent directory to path to import main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import main, RandomFillStrategy, logger
import logging

# Example URL (replace with your actual multi-page form URL)
FORM_URL = "https://docs.google.com/forms/d/e/YOUR_MULTIPAGE_FORM_ID/viewform"

def example_progressive_submission():
    """Submit a multi-page form using progressive mode."""
    
    print("=" * 60)
    print("Multi-Page Form Progressive Submission Example")
    print("=" * 60)
    print()
    
    # Configure logging to see detailed progress
    logger.setLevel(logging.INFO)
    
    print("📄 This example will submit a multi-page form progressively,")
    print("   simulating clicking 'Next' on each page.")
    print()
    
    # Option 1: Simple progressive submission with random data
    print("Method 1: Simple progressive submission")
    print("-" * 40)
    success = main(
        url=FORM_URL,
        progressive=True,  # Enable progressive mode
        email="test@example.com"
    )
    
    if success:
        print("\n✓ Progressive submission completed successfully!")
    else:
        print("\n✗ Progressive submission failed.")
    
    print("\n" + "=" * 60)


def example_progressive_with_custom_data():
    """Submit multi-page form progressively with custom data."""
    
    print("Method 2: Progressive submission with custom values")
    print("-" * 40)
    
    # Define custom values for specific fields
    custom_data = {
        "entry.123456": "Custom answer for page 1",
        "entry.789012": "Custom answer for page 2",
        "entry.345678": ["Option A", "Option B"],  # Checkbox
        "emailAddress": "custom@example.com"
    }
    
    success = main(
        url=FORM_URL,
        progressive=True,
        custom_values=custom_data,
        email="custom@example.com",
        only_required=False,  # Fill all fields
        save_responses=True   # Save the generated data
    )
    
    if success:
        print("\n✓ Progressive submission with custom data completed!")
    else:
        print("\n✗ Progressive submission with custom data failed.")


def example_batch_progressive():
    """Submit multi-page form multiple times using progressive mode."""
    
    print("\nMethod 3: Batch progressive submissions")
    print("-" * 40)
    
    success = main(
        url=FORM_URL,
        progressive=True,
        count=5,              # Submit 5 times
        delay=2.0,            # 2 second delay between submissions
        strategy="random",    # Use random values
        save_responses=True
    )
    
    if success:
        print("\n✓ All batch progressive submissions completed!")
    else:
        print("\n✗ Some batch progressive submissions failed.")


def example_comparison():
    """Compare standard vs progressive submission."""
    
    print("\nMethod 4: Comparison - Standard vs Progressive")
    print("-" * 40)
    
    print("\n1. Standard submission (all data at once):")
    success_standard = main(
        url=FORM_URL,
        progressive=False,    # Standard mode
        email="standard@example.com"
    )
    
    print("\n2. Progressive submission (page-by-page):")
    success_progressive = main(
        url=FORM_URL,
        progressive=True,     # Progressive mode
        email="progressive@example.com"
    )
    
    print("\n" + "=" * 60)
    print("Comparison Results:")
    print(f"  Standard mode:    {'✓ Success' if success_standard else '✗ Failed'}")
    print(f"  Progressive mode: {'✓ Success' if success_progressive else '✗ Failed'}")
    print("=" * 60)


if __name__ == "__main__":
    print("\n🚀 Multi-Page Form Progressive Submission Examples\n")
    
    # Uncomment the example you want to run:
    
    # Example 1: Simple progressive submission
    # example_progressive_submission()
    
    # Example 2: Progressive with custom data
    # example_progressive_with_custom_data()
    
    # Example 3: Batch progressive submissions
    # example_batch_progressive()
    
    # Example 4: Comparison between standard and progressive
    # example_comparison()
    
    print("\n💡 Tips:")
    print("   1. Replace FORM_URL with your actual multi-page form URL")
    print("   2. Uncomment one of the example functions above to run it")
    print("   3. Use --progressive flag in command line:")
    print("      python main.py <url> --progressive")
    print("   4. Progressive mode automatically detects multi-page forms")
    print("   5. For debugging, use --verbose flag to see page-by-page progress")
    print()
