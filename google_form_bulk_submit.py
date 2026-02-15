#!/usr/bin/env python3
"""
One‑step Google Form bulk submitter.
Usage: python google_form_bulk_submit.py <FORM_URL> <M>
"""

import sys
import os
import json
import re
import random
import time
import hashlib
from urllib.parse import urlparse, parse_qs

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# ------------------------------------------------------------
# 1.  Form structure extractor (Selenium, used only once per form)
# ------------------------------------------------------------
def extract_form_structure(form_url):
    """Parse the Google Form and return a dict with action_url, fbzx, questions."""
    print("📡 Parsing form structure with Selenium (one‑time operation)...")

    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')          # run in background
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    try:
        driver.get(form_url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'form'))
        )

        # ---- Action URL ----
        form = driver.find_element(By.CSS_SELECTOR, 'form')
        action = form.get_attribute('action')
        if not action.startswith('http'):
            action = 'https://docs.google.com' + action

        # ---- fbzx (required anti‑spam token) ----
        fbzx_elem = driver.find_element(By.NAME, 'fbzx')
        fbzx = fbzx_elem.get_attribute('value')

        # ---- Page history (needed for multi‑page forms) ----
        page_history = None
        try:
            page_history_elem = driver.find_element(By.NAME, 'pageHistory')
            page_history = page_history_elem.get_attribute('value')
        except NoSuchElementException:
            pass

        # ---- All question containers ----
        questions = []
        containers = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')

        for idx, qc in enumerate(containers):
            entry_id = None
            q_type = None
            options_list = []

            # Find the entry ID from any named element inside this container
            named = (
                qc.find_elements(By.CSS_SELECTOR, '[name^="entry."]') +
                qc.find_elements(By.CSS_SELECTOR, 'select[name^="entry."]')
            )
            if named:
                full_name = named[0].get_attribute('name')
                entry_id = full_name.split('_')[0]   # strip suffixes like _sentinel

            # ----- Detect type and collect possible answers -----
            # 1. Radio buttons
            radios = qc.find_elements(By.CSS_SELECTOR, 'div[role="radio"]')
            if radios:
                q_type = 'radio'
                for r in radios:
                    val = r.get_attribute('data-value')
                    if val:
                        options_list.append(val)
                if not options_list:
                    # fallback: use aria-label
                    options_list = [r.get_attribute('aria-label') for r in radios if r.get_attribute('aria-label')]

            # 2. Checkboxes
            if not q_type:
                checkboxes = qc.find_elements(By.CSS_SELECTOR, 'div[role="checkbox"]')
                if checkboxes:
                    q_type = 'checkbox'
                    for cb in checkboxes:
                        val = cb.get_attribute('data-value')
                        if val:
                            options_list.append(val)
                    if not options_list:
                        options_list = [cb.get_attribute('aria-label') for cb in checkboxes if cb.get_attribute('aria-label')]

            # 3. Dropdown
            if not q_type:
                selects = qc.find_elements(By.TAG_NAME, 'select')
                if selects:
                    q_type = 'dropdown'
                    select = Select(selects[0])
                    for opt in select.options:
                        val = opt.get_attribute('value')
                        if val:
                            options_list.append(val)

            # 4. Text input (short answer)
            if not q_type:
                text_inputs = qc.find_elements(By.CSS_SELECTOR, 'input[type="text"]')
                if text_inputs:
                    q_type = 'text'

            # 5. Textarea (paragraph)
            if not q_type:
                textareas = qc.find_elements(By.TAG_NAME, 'textarea')
                if textareas:
                    q_type = 'paragraph'

            # 6. Linear scale (radiogroup)
            if not q_type:
                radiogroups = qc.find_elements(By.CSS_SELECTOR, 'div[role="radiogroup"]')
                if radiogroups:
                    q_type = 'scale'
                    for rg in radiogroups:
                        scale_radios = rg.find_elements(By.CSS_SELECTOR, 'div[role="radio"]')
                        for sr in scale_radios:
                            val = sr.get_attribute('data-value')
                            if val:
                                options_list.append(val)

            # 7. Date picker
            if not q_type:
                date_inputs = qc.find_elements(By.CSS_SELECTOR, 'input[type="date"]')
                if date_inputs:
                    q_type = 'date'

            # 8. Time picker
            if not q_type:
                time_inputs = qc.find_elements(By.CSS_SELECTOR, 'input[type="time"]')
                if time_inputs:
                    q_type = 'time'

            if entry_id and q_type:
                questions.append({
                    'entry_id': entry_id,
                    'type': q_type,
                    'options': options_list,
                })

        driver.quit()
        return {
            'action_url': action,
            'fbzx': fbzx,
            'page_history': page_history,
            'questions': questions
        }

    except Exception as e:
        driver.quit()
        raise RuntimeError(f"Failed to parse form: {e}")

# ------------------------------------------------------------
# 2.  Random answer generators
# ------------------------------------------------------------
def random_text():
    words = ['apple', 'banana', 'car', 'dog', 'energy', 'finance', 'goal', 'happy',
             'investment', 'job', 'knowledge', 'life', 'money', 'nature', 'option',
             'plan', 'quality', 'return', 'stock', 'time', 'value', 'work', 'xray',
             'young', 'zebra']
    return ' '.join(random.sample(words, random.randint(2, 5)))

def random_paragraph():
    return random_text() + '. ' + random_text() + '.'

def random_date():
    return f"{random.randint(2000,2030)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

def random_time():
    return f"{random.randint(0,23):02d}:{random.randint(0,59):02d}"

def random_choice(options):
    return random.choice(options) if options else ""

def random_multiple(options):
    """Select a random subset of options (1 up to half of total)."""
    if not options:
        return []
    k = random.randint(1, max(1, len(options)//2))
    return random.sample(options, k)

# ------------------------------------------------------------
# 3.  Build POST data for one submission
# ------------------------------------------------------------
def build_post_data(form_struct):
    """Return a list of (key, value) tuples suitable for requests.post(data=...)."""
    data = []
    # Required fields
    data.append(('fbzx', form_struct['fbzx']))
    if form_struct.get('page_history'):
        data.append(('pageHistory', form_struct['page_history']))

    # Answer each question
    for q in form_struct['questions']:
        entry = q['entry_id']
        qtype = q['type']
        opts = q['options']

        if qtype in ('radio', 'dropdown'):
            if opts:
                data.append((entry, random_choice(opts)))
            # else skip – no options available

        elif qtype == 'checkbox':
            selected = random_multiple(opts)
            for val in selected:
                data.append((entry, val))

        elif qtype == 'text':
            data.append((entry, random_text()))

        elif qtype == 'paragraph':
            data.append((entry, random_paragraph()))

        elif qtype == 'date':
            data.append((entry, random_date()))

        elif qtype == 'time':
            data.append((entry, random_time()))

        elif qtype == 'scale':
            if opts:
                data.append((entry, random_choice(opts)))

    return data

# ------------------------------------------------------------
# 4.  Main: cache management + bulk POST
# ------------------------------------------------------------
def get_cache_filename(form_url):
    """Create a unique, safe filename from the form URL."""
    # Extract form ID (long string after /d/e/)
    match = re.search(r'/d/e/([^/]+)', form_url)
    if match:
        form_id = match.group(1)
    else:
        # fallback: hash the whole URL
        form_id = hashlib.md5(form_url.encode()).hexdigest()[:10]
    return f"google_form_{form_id}.json"

def main():
    if len(sys.argv) != 3:
        print("Usage: python google_form_bulk_submit.py <FORM_URL> <M>")
        sys.exit(1)

    form_url = sys.argv[1]
    try:
        M = int(sys.argv[2])
    except ValueError:
        print("M must be an integer.")
        sys.exit(1)

    cache_file = get_cache_filename(form_url)

    # ---- Load or extract form structure ----
    if os.path.exists(cache_file):
        print(f"📁 Loading cached form structure from {cache_file}")
        with open(cache_file, 'r') as f:
            form_struct = json.load(f)
    else:
        form_struct = extract_form_structure(form_url)
        with open(cache_file, 'w') as f:
            json.dump(form_struct, f, indent=2)
        print(f"💾 Form structure cached to {cache_file}")

    # ---- Bulk submissions ----
    print(f"🚀 Submitting {M} responses...")
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://docs.google.com',
        'Referer': form_url,
    })

    success = 0
    for i in range(M):
        post_data = build_post_data(form_struct)
        try:
            resp = session.post(form_struct['action_url'], data=post_data)
            if resp.status_code == 200:
                success += 1
                print(f"✅ {i+1}/{M} submitted (HTTP 200)")
            else:
                print(f"⚠️ {i+1}/{M} returned {resp.status_code}")
        except Exception as e:
            print(f"❌ {i+1}/{M} error: {e}")

        # Be polite – random delay between 0.3 and 1.5 seconds
        time.sleep(random.uniform(0.3, 1.5))

    print(f"\n🎉 Done. {success}/{M} submissions successful.")

if __name__ == '__main__':
    main()