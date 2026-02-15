# Google Forms Bulk Responder

> ⚠️ **Disclaimer**: This tool is for **educational purposes only**. Only use it on forms you own or have explicit permission to test. Unauthorised bulk submissions violate Google's Terms of Service and may lead to IP bans or legal action.

## Description

Automatically extract the structure of a Google Form and submit a large number of random responses. Useful for load testing your own forms or generating dummy data.

## Features

- Extracts all question types (radio, checkbox, dropdown, text, paragraph, date, time, linear scale).
- Caches the form structure to avoid repeated Selenium calls.
- Configurable delays and retry logic.
- Verifies successful submission by checking for "Your response has been recorded".
- Dry‑run mode to preview data without sending.

## Requirements

- Python 3.6 or higher
- Google Chrome browser
- Internet connection

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/google-forms-bulk-responder.git
   cd google-forms-bulk-responder
