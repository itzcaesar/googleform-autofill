# 🚀 Google Form AutoFill and Submit

<div align="center">

**Automate Google Forms submission with Python**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Requests](https://img.shields.io/badge/requests-2.31+-orange.svg)](https://requests.readthedocs.io/)

[Features](#-features) •
[Quick Start](#-quick-start) •
[Documentation](#-documentation) •
[Examples](#-complete-usage-examples) •
[Advanced](#-customize-the-script)

</div>

---

## 📖 Overview
This is a fork/improved version of the original google form autofill/submit created by [tienthanh214](https://github.com/tienthanh214), Original Version [here](https://github.com/tienthanh214/googleform-autofill-and-submit)

This is a **simple and lightweight** script to automatically fill and submit Google Forms with random or custom data. The script is highly customizable, allowing you to:
- 🎲 Fill forms with random values
- 📝 Use custom data from JSON files
- 🔄 Submit forms multiple times (batch mode)
- 💾 Save responses for audit trails
- 🧪 Test without submitting (dry-run mode)

It also includes a request body **generator** for those who prefer manual data input - simply paste a Google Form URL, eliminating the need for manual inspection.

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [📦 Prerequisites](#-prerequisites)
- [🚀 Quick Start](#-quick-start)
- [📚 Documentation](#-documentation)
  - [Access and Get the URL](#1-access-and-get-the-url)
  - [Extract Information](#2-extract-information)
  - [Write the Python Script](#3-write-the-python-script)
- [🎯 AutoFill and Submit](#-autofill-and-submit)
  - [Run the Script](#run-the-script)
  - [Quick Start Examples](#quick-start-examples)
  - [Enhanced Features](#-enhanced-features)
  - [Complete Usage Examples](#-complete-usage-examples)
  - [All Command Line Options](#-all-command-line-options)
  - [Customize the Script](#-customize-the-script)
  - [Tips and Best Practices](#-tips-and-best-practices)
  - [Error Handling](#-error-handling)
- [⚠️ Limitations](#️-limitations)

---

## ✨ Features

<table>
<tr>
<td width="50%">

### Core Features
- ✅ Multiple pages support
- ✅ **Progressive page-by-page submission**
- ✅ Email collection support
- ✅ Auto request body generation
- ✅ Random value auto-fill
- ✅ Multi-page form handling

</td>
<td width="50%">

### Enhanced Features
- ✨ Multiple fill strategies
- ✨ Batch submissions
- ✨ Custom values via JSON
- ✨ Dry-run testing mode
- ✨ Response saving
- ✨ Comprehensive logging
- ✨ Auto-generated filenames
- ✨ **"Next" button simulation**

</td>
</tr>
</table>

---

## 📦 Prerequisites

```bash
# Python 3.7 or higher
python --version

# Install dependencies
pip install -r requirements.txt

# Or install directly
pip install requests
```

**Requirements:**
- Python 3.7+
- `requests` library (≥2.31.0)

---

## 🚀 Quick Start

### 1️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 2️⃣ Generate Form Template
```bash
python form.py 'https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform' -o auto
```

### 3️⃣ Submit the Form
```bash
python main.py 'https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform'
```

**That's it!** 🎉 Your form has been submitted with random data.

---

## 📚 Documentation

### Getting Started

If you only want to fill and submit a Google Form with random data, skip to the [AutoFill and Submit](#-autofill-and-submit) section.

Below are the detailed steps to understand and customize the process.

---

### 1. Access and Get the URL

The URL of the Google Form will look like this:
```
https://docs.google.com/forms/d/e/form-index/viewform
```

Just copy it and replace **viewform** with **formResponse**:
```
https://docs.google.com/forms/d/e/form-index/formResponse
```

---

### 2. Extract Information

#### 🤖 Automatically (Recommended)

Just copy the Google Form URL and run the `form.py` script. It will return a dictionary containing the name attributes of each input element and the data you need to fill out.

```bash
python form.py <your-gg-form-url>
```

#### 📂 Output Options for form.py

| Mode | Command | Description |
|------|---------|-------------|
| **Console** | `python form.py <url>` | Print to console (default) |
| **Auto-generate** | `python form.py <url> -o auto` | Save to `form_outputs/` with auto-generated name |
| **Folder** | `python form.py <url> -o my_forms/` | Save to specified folder with auto-generated name |
| **File** | `python form.py <url> -o path/to/file.txt` | Save to specific file path |

#### 💡 Examples

```bash
# Save to auto-generated file
python form.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' -o auto

# Save to specific file
python form.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' -o results.txt

# Only required fields with verbose output
python form.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' -o auto -r --verbose
```

#### 🔧 Get More Help
```bash
python form.py -h
```

---

#### 🔍 Manually

<details>
<summary>Click to expand manual method</summary>

Open the Google Form, then open DevTools (inspect) to inspect the input elements.

Each input element you need to fill has a format: `name = "entry.id"`

Try filling each input box to discover its ID.

</details>

---

#### 📌 Note

> **Important:** 
> - If the form requires email, add the `emailAddress` field
> - For multiple-page forms, add the `pageHistory` field with comma-separated page numbers (starting from 0)
>   - Example: 4-page form → `"pageHistory": "0,1,2,3"`

---

### 3. Write the Python Script

#### 📝 Fill Form

Create a dictionary where keys are the name attributes of each input element, and values are the data you need to fill out:

```python
# Example
def fill_form():
    name = get_name_by_day()
    date, hour = str(get_gmt_time()).split(' ')
    date = date.split('-')
    hour = hour.split(':')
    if (int(hour[0]) < 10):
        hour[0] = hour[0][1:]

    value = {
        # Text
        "entry.2112281434": name,
        # Dropdown menu
        "entry.1600556346": "Sài Gòn",
        # Date
        "entry.77071893_year": date[0],
        "entry.77071893_month": date[1],
        "entry.77071893_day": date[2],
        # Hour
        "entry.855769839": hour[0] + 'h',
        # Checkbox 
        "entry.819260047": ["Cafe", "Fences"],
        # One choice
        "entry.1682233942": "Okay"
    }
    print(value, flush=True)
    return value
```

#### 📤 Submit Form

Use POST method with `requests`:

```python
def submit(url, data):
    try:
        requests.post(url, data=data)
        print("Submitted successfully!")
    except:
        print("Error!")

submit(url, fill_form())
```

**Done!** ✨

---

## 🎯 AutoFill and Submit

### Run the Script

Run the `main.py` script with the Google Form URL to automatically fill and submit with **random data**:

```bash
python main.py <your-gg-form-url>
```

---

### Quick Start Examples

```bash
# 🎲 Basic submission with random values
python main.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform'

# ⚡ Only fill required fields
python main.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' -r

# 📧 Custom email address
python main.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' --email myemail@gmail.com

# 🎂 Specify age range for age fields
python main.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' --age-range "18-25"

# 🧪 Dry run (preview without submitting)
python main.py 'https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform' --dry-run
```

---

## 🎨 Enhanced Features

### 1️⃣ Fill Strategies

Choose how to populate form fields:

| Strategy | Description | Usage |
|----------|-------------|-------|
| **Random** (default) | Fills fields with random realistic values | `python main.py <url>` |
| **Fixed** | Uses consistent values across submissions | `python main.py <url> --strategy fixed` |

**Examples:**
```bash
# Random values (default)
python main.py <form_url>

# Fixed values
python main.py <form_url> --strategy fixed
```

---

### 2️⃣ Batch Submissions

Submit the same form multiple times with automatic delays:

```bash
# Submit 10 times with 2-second delay
python main.py <form_url> --count 10 --delay 2

# Rapid submissions (be careful!)
python main.py <form_url> --count 5 --delay 0.5
```

**Batch submission includes:**
- ⏱️ Automatic delays between submissions
- 📊 Success/failure tracking
- 📈 Detailed statistics summary
- 🔄 Progress indicators

**Example output:**
```
==================================================
SUBMISSION SUMMARY
==================================================
Total attempts:  10
Successful:      10 ✓
Failed:          0 ✗
Success rate:    100.0%
==================================================
```

---

### 3️⃣ Progressive Multi-Page Submission

**NEW!** For multi-page forms, simulate clicking the "Next" button on each page:

```bash
# Automatically detect and submit multi-page forms progressively
python main.py <form_url> --progressive
```

**What is Progressive Mode?**
- 🔄 Submits each page separately (like clicking "Next")
- ⏱️ Adds realistic delays between pages
- ✅ Better mimics human behavior
- 🎯 Useful for forms with page-specific validation

**Examples:**
```bash
# Single progressive submission
python main.py <form_url> --progressive

# Batch progressive submissions
python main.py <form_url> --progressive --count 5 --delay 2

# Progressive with custom data
python main.py <form_url> --progressive --custom-file data.json -v
```

**How it works:**
1. Detects number of pages in the form
2. Submits data for page 1 → receives response
3. Updates pageHistory to "0,1"
4. Submits data for page 2 → receives response
5. Continues until final page
6. Shows progress for each page

**Output example:**
```
Multi-page form detected with 3 pages
Submitting progressively (simulating 'Next' button clicks)...
📄 Submitting page 1/3...
✓ Page 1/3 submitted (Next)
📄 Submitting page 2/3...
✓ Page 2/3 submitted (Next)
📄 Submitting page 3/3...
✓ Page 3/3 submitted (Final page)
✓ All pages submitted successfully!
```

> 💡 **Tip:** Use verbose mode (`-v`) to see detailed page-by-page progress

---

### 4️⃣ Age Range for Age Fields

Automatically fill age/umur fields with values from a specified range:

```bash
# Fill age fields with ages between 18-25
python main.py <form_url> --age-range "18-25"

# Different age ranges
python main.py <form_url> --age-range "20-30"
python main.py <form_url> --age-range "30-50"
```

**How it works:**
- 🔍 **Smart detection**: Automatically identifies age fields by keywords:
  - English: `age`
  - Indonesian: `umur`, `usia`, `tahun`
  - Spanish: `edad`
  - German: `alter`
- 🎲 **Random generation**: Generates random ages within your specified range
- ✅ **Works with both strategies**: Compatible with random and fixed fill strategies
- 🌍 **Multi-language support**: Detects age fields in multiple languages

**Examples:**
```bash
# Submit form with ages between 18-20
python main.py <form_url> --age-range "18-20"

# Batch submissions with age range
python main.py <form_url> --age-range "25-35" --count 10

# Combine with other options
python main.py <form_url> --age-range "20-30" --progressive --save-responses
```

**Validation:**
- ✅ Age range format: `"min-max"` (e.g., `"18-25"`)
- ✅ Valid range: 0-150 years
- ✅ Min must be less than max
- ❌ Invalid formats will show helpful error messages

---

### 5️⃣ Custom Values

Override specific fields with custom values using a JSON file:

**Step-by-step:**

```bash
# 1. Generate form template to get entry IDs
python form.py <form_url> -o auto

# 2. Create custom_values.json
```

```json
{
  "entry.123456": "My custom answer",
  "entry.789012": ["Option A", "Option B"],
  "emailAddress": "myemail@gmail.com"
}
```

```bash
# 3. Use it
python main.py <form_url> --custom-file custom_values.json
```

> 💡 **Tip:** See [custom_values_example.json](custom_values_example.json) for a complete example.

---

### 6️⃣ Dry Run Mode

Preview what will be submitted **without actually submitting**:

```bash
python main.py <form_url> --dry-run
```

**Perfect for:**
- ✅ Testing your fill strategy
- ✅ Validating custom values
- ✅ Debugging form data
- ✅ Previewing batch submissions
- ✅ Checking multi-page form structure

**Example output with multi-page form:**
```
=== DRY RUN MODE - No actual submission ===

Generated form data:
{
  "entry.123456": "Test value",
  "entry.789012": "Another value",
  "pageHistory": "0,1,2"
}

ℹ️  This is a multi-page form with 3 pages
   pageHistory field: 0,1,2
```

---

### 7️⃣ Save Responses

Save generated form data to JSON files for record-keeping:

```bash
# Save single submission
python main.py <form_url> --save-responses

# Save all batch submissions
python main.py <form_url> --count 10 --save-responses
```

> 📁 Files are saved to `form_outputs/` with timestamps for easy tracking.

---

### 8️⃣ Logging Levels

Control output verbosity:

```bash
# 📢 Verbose mode (shows all details including debug info)
python main.py <form_url> -v

# 🔇 Quiet mode (errors only)
python main.py <form_url> -q

# 📝 Normal mode (default - info and errors)
python main.py <form_url>
```

**Verbose mode shows:**
- Page-by-page submission progress
- Detailed form data
- Network requests
- All debug information

---

## 💡 Complete Usage Examples

### Example 1: Simple One-Time Submission
```bash
python main.py https://docs.google.com/forms/d/e/ABC123/viewform
```

---

### Example 2: Batch Testing
```bash
# Submit 20 times with random values, 1.5s delay, save all responses
python main.py https://docs.google.com/forms/d/e/ABC123/viewform \
  --count 20 \
  --delay 1.5 \
  --save-responses
```

---

### Example 3: Custom Data Submission
```bash
# 1. Generate form template
python form.py https://docs.google.com/forms/d/e/ABC123/viewform -o auto

# 2. Edit the generated file to create your custom_data.json
# 3. Submit with custom data
python main.py https://docs.google.com/forms/d/e/ABC123/viewform \
  --custom-file custom_data.json \
  --email realuser@example.com
```

---

### Example 4: Development Testing
```bash
# Dry run to check data generation with verbose output
python main.py https://docs.google.com/forms/d/e/ABC123/viewform \
  --dry-run \
  --verbose
```

---

### Example 5: Multi-Page Form Progressive Submission
```bash
# Submit multi-page form with progressive mode (simulates clicking "Next")
python main.py https://docs.google.com/forms/d/e/MULTIPAGE_FORM/viewform \
  --progressive \
  --verbose
```

**What happens:**
- Automatically detects 3-page form
- Submits page 1, waits, submits page 2, waits, submits page 3
- Shows progress for each page

---

### Example 6: Batch Multi-Page Testing
```bash
# Submit multi-page form 10 times progressively
python main.py https://docs.google.com/forms/d/e/MULTIPAGE_FORM/viewform \
  --progressive \
  --count 10 \
  --delay 2 \
  --save-responses \
  --verbose
```

---

### Example 7: Age-Specific Form Testing
```bash
# Submit form with specific age range
python main.py https://docs.google.com/forms/d/e/ABC123/viewform \
  --age-range "18-25" \
  --count 10 \
  --save-responses
```

---

### Example 8: Production-like Testing
```bash
# Fill and submit only required fields with fixed values
python main.py https://docs.google.com/forms/d/e/ABC123/viewform \
  --required \
  --strategy fixed \
  --count 5 \
  --delay 2 \
  --save-responses
```

---

## 🛠️ All Command Line Options

### `main.py` Options

<details open>
<summary><b>Click to expand/collapse</b></summary>

#### Positional Arguments
```
url                   Google Form URL
```

#### Fill Options
```
-r, --required        Only fill required fields
--email EMAIL         Email address for email fields (default: test@example.com)
--strategy {random,fixed}
                      Fill strategy: random or fixed values
--custom-file FILE    JSON file with custom field values
--age-range MIN-MAX   Age range for age/umur fields (e.g., "18-25", "20-30")
```

#### Submission Options
```
--count N             Number of times to submit (default: 1)
--delay SEC           Delay between submissions in seconds (default: 1.0)
--dry-run             Generate data but do not submit
```

#### Submission Options
```
--count N             Number of times to submit (default: 1)
--delay SEC           Delay between submissions in seconds (default: 1.0)
--dry-run             Generate data but do not submit
--progressive         Use progressive page-by-page submission for multi-page forms
```

#### Output Options
```
--save-responses      Save generated responses to JSON
-v, --verbose         Enable verbose logging
-q, --quiet           Minimal output (errors only)
```

</details>

---

### `form.py` Options

<details>
<summary><b>Click to expand/collapse</b></summary>

#### Positional Arguments
```
url                   Google Form URL
```

#### Optional Arguments
```
-o, --output PATH     Output: 'console', 'auto', folder path, or file path
-r, --required        Only include required fields
-c, --no-comment      Don't include explanatory comments
-v, --verbose         Enable verbose logging
```

</details>

---

## 🎓 Customize the Script

The `main.py` script is a powerful tool that can be customized in several ways:

### 🔧 Custom Fill Strategies (Advanced)

For advanced users, create custom fill strategies:

```python
from main import FillStrategy
import form

class CustomFillStrategy(FillStrategy):
    def fill(self, type_id, entry_id, options, required=False, entry_name=''):
        # Your custom logic here
        if "name" in entry_name.lower():
            return "John Doe"
        
        if type_id == form.FIELD_TYPE_DATE:
            return "2025-12-31"
        
        # Fall back to parent class for other fields
        return super().fill(type_id, entry_id, options, required, entry_name)

# Use in code:
from main import main
strategy = CustomFillStrategy(email="custom@example.com")
main(url, fill_strategy=strategy)
```

---

### 📦 Using as a Python Module

```python
from main import generate_request_body, submit_form, RandomFillStrategy

# Generate data
url = "https://docs.google.com/forms/d/e/ABC123/viewform"
strategy = RandomFillStrategy(email="test@example.com")
data = generate_request_body(url, fill_strategy=strategy)

# Customize specific fields
data["entry.123456"] = "My custom value"

# Submit
success = submit_form(url, data)
print("Success!" if success else "Failed!")
```

---

## 💎 Tips and Best Practices

| # | Tip | Description |
|---|-----|-------------|
| 1️⃣ | **Use dry-run first** | Always test with `--dry-run` before actual submissions |
| 2️⃣ | **Respect rate limits** | Use appropriate delays (1-2 seconds recommended) for batch submissions |
| 3️⃣ | **Save responses** | Use `--save-responses` for audit trails and debugging |
| 4️⃣ | **Custom values** | Great for production-like test data |
| 5️⃣ | **Verbose mode** | Use `-v` when debugging issues |
| 6️⃣ | **Start small** | Test with `--count 1` before large batch submissions |
| 7️⃣ | **Check saved files** | Files in `form_outputs/` include timestamps for easy tracking |
| 8️⃣ | **Progressive for multi-page** | Use `--progressive` for forms with multiple pages to simulate real user flow |
| 9️⃣ | **Auto-detection** | Multi-page forms are automatically detected - progressive mode is optional |
| 🔟 | **Age range for surveys** | Use `--age-range` for demographic surveys to ensure realistic age distributions |

### 📄 Multi-Page Form Specific Tips

- **Auto vs Progressive**: Tool automatically includes `pageHistory` field. Use `--progressive` for page-by-page submission
- **Testing multi-page**: Use `--dry-run` to see the `pageHistory` field value
- **Debugging**: Use `-v` with `--progressive` to see each page being submitted
- **Page delays**: Progressive mode adds 0.5s delay between pages by default
- **Batch testing**: Combine `--progressive --count N` for realistic batch testing of multi-page forms

---

## 🚨 Error Handling

The enhanced version includes comprehensive error handling for:

- 🌐 Network timeouts and connection errors
- 🔗 Invalid URLs or malformed responses
- 💾 File I/O errors
- 📄 JSON parsing errors
- ⚠️ Missing required fields
- 🔒 SSL certificate issues

> All errors are logged with clear messages and the program exits with appropriate status codes for scripting.

---

## 📖 Help Commands

Use `-h` or `--help` to get comprehensive help for each script:

```bash
python main.py -h
python form.py -h
```

---

## 📄 Multi-Page Forms - Detailed Guide

### 🎯 Overview

The tool fully supports **progressive page-by-page submission** for multi-page Google Forms, simulating the behavior of clicking the "Next" button on each page.

### 🔄 Two Submission Modes

#### 1. **Standard Mode (Default)**
- Submits all form data at once
- Includes `pageHistory` field automatically
- Single HTTP request
- ⚡ Fast and efficient

```bash
python main.py <form_url>
```

#### 2. **Progressive Mode**
- Submits data page-by-page
- Simulates clicking "Next" button
- Multiple HTTP requests (one per page)
- 🎭 More realistic user behavior

```bash
python main.py <form_url> --progressive
```

---

### 🔍 How Each Mode Works

**Standard Mode Flow:**
```
1. Generate all form data
2. Add pageHistory: "0,1,2,3"
3. Submit → Done ✓
```

**Progressive Mode Flow:**
```
1. Detect 4 pages in form
2. Submit page 1 data (pageHistory: "0")
3. Wait 0.5s ⏱️
4. Submit page 2 data (pageHistory: "0,1")
5. Wait 0.5s ⏱️
6. Submit page 3 data (pageHistory: "0,1,2")
7. Wait 0.5s ⏱️
8. Submit page 4 data (pageHistory: "0,1,2,3")
9. Done ✓
```

---

### 💡 When to Use Each Mode

**✅ Use Progressive Mode When:**
- Form has page-specific validation
- You want to mimic real user behavior
- Testing form's multi-page logic
- Debugging page navigation issues
- Form requires client-side page progression

**✅ Standard Mode is Fine When:**
- Simple batch testing
- Fast automated submissions
- Form accepts all data at once
- You don't need page-by-page simulation

---

### 📊 Mode Comparison

| Feature | Standard Mode | Progressive Mode |
|---------|--------------|------------------|
| **Speed** | ⚡ Fast | 🐢 Slower (0.5s per page) |
| **Requests** | 1 request | N requests (N = pages) |
| **Realism** | Medium | High |
| **Debugging** | Simple | Detailed per-page |
| **Use Case** | Bulk testing | Realistic simulation |
| **Auto-detection** | ✅ Yes | ✅ Yes |

---

### 🛠️ Technical Details

#### Auto-Detection
Both modes automatically detect multi-page forms by:
1. Parsing form structure from `FB_PUBLIC_LOAD_DATA_`
2. Counting page breaks (`FORM_SESSION_TYPE_ID`)
3. Automatically adding `pageHistory` field

#### Page History Format
- Single page: No `pageHistory` field
- 2 pages: `"0,1"`
- 3 pages: `"0,1,2"`
- 4 pages: `"0,1,2,3"`
- And so on...

---

### 📝 Progressive Mode Examples

#### Example 1: Simple Progressive Submission
```bash
python main.py https://docs.google.com/forms/d/e/FORM_ID/viewform --progressive
```

**Output:**
```
🔄 Multi-page form detected (3 pages) - Progressive mode enabled
Submitting progressively (simulating 'Next' button clicks)...
📄 Submitting page 1/3...
✓ Page 1/3 submitted (Next)
📄 Submitting page 2/3...
✓ Page 2/3 submitted (Next)
📄 Submitting page 3/3...
✓ Page 3/3 submitted (Final page)
✓ All pages submitted successfully!
```

---

#### Example 2: Batch Progressive Testing
```bash
python main.py https://docs.google.com/forms/d/e/FORM_ID/viewform \
  --progressive \
  --count 5 \
  --delay 3 \
  --save-responses \
  --verbose
```

**What this does:**
- Submits the multi-page form 5 times
- Uses progressive mode (page-by-page)
- 3 second delay between complete submissions
- Saves all responses to JSON files
- Shows detailed verbose output

---

#### Example 3: Compare Both Modes
```bash
# Test with standard mode
python main.py <url> --dry-run -v

# Test with progressive mode  
python main.py <url> --progressive --dry-run -v
```

This lets you see the difference in how data is prepared and submitted.

---

### ⚙️ Configuration & Customization

#### Default Settings
- **Page delay**: 0.5 seconds between pages
- **Request timeout**: 10 seconds per request
- **SSL verification**: Enabled

#### Code-Level Customization
```python
from main import submit_form_progressive

# Custom page delay
success = submit_form_progressive(
    url=form_url,
    data=form_data,
    page_delay=1.0,  # 1 second between pages
    timeout=15       # 15 second timeout
)
```

---

### 🐛 Troubleshooting Multi-Page Forms

| Issue | Solution |
|-------|----------|
| **"Single page form detected"** | Form is actually single page - progressive mode not needed |
| **Progressive mode too slow** | Expected (0.5s delay per page). Use standard mode for speed |
| **Page submission failed** | Check verbose output with `-v`, verify pageHistory, try standard mode |
| **Wrong page count** | Use `--dry-run -v` to see detected structure |
| **Form not submitting** | Try without `--progressive` first, check if form requires login |

---

### 💻 Using Progressive Mode in Code

```python
from main import (
    main, 
    submit_form_progressive, 
    generate_request_body,
    RandomFillStrategy,
    get_page_count
)

# Check if form is multi-page
url = "https://docs.google.com/forms/d/e/YOUR_FORM/viewform"
page_count = get_page_count(url)
print(f"Form has {page_count} pages")

# Generate data
strategy = RandomFillStrategy(email="test@example.com")
data = generate_request_body(url, fill_strategy=strategy)

# Submit progressively
if page_count > 1:
    success = submit_form_progressive(url, data, page_delay=1.0)
else:
    success = submit_form(url, data)
```

---

### 🎓 Best Practices for Multi-Page Forms

1. **Test with dry-run first**: `--dry-run -v` to see form structure and pageHistory
2. **Use verbose for debugging**: `-v` shows detailed page-by-page submission
3. **Standard mode for speed**: Unless you specifically need progressive behavior
4. **Save responses for analysis**: `--save-responses` helps track what was submitted
5. **Combine with custom data**: Progressive mode works seamlessly with `--custom-file`
6. **Start with small counts**: Test with `--count 1` before batch submissions
7. **Monitor rate limits**: Use appropriate delays to avoid overwhelming the form

---

### ✨ Progressive Mode Benefits

- ✅ **Page-by-page submission** - Each page submitted separately
- ✅ **Automatic detection** - No manual configuration needed
- ✅ **Realistic simulation** - Mimics actual user clicking "Next"
- ✅ **Detailed progress** - See each page being processed
- ✅ **Compatible** - Works with all existing features
- ✅ **Flexible** - Optional - standard mode still available

---

## ⚠️ Limitations
Please note that this script currently operates only with Google Forms that do not require user authentication.
