import json
import time
import pandas as pd
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import requests
import signal
import sys
import threading
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request
from urllib.parse import quote

# Initialize Flask app
app = Flask(__name__)

# ---------------------- CONFIGURATION ----------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

INPUT_FILE = INPUT_DIR / "VSKP1_data.xlsx"
OUTPUT_FILE = OUTPUT_DIR / "VSKP2_data.xlsx"
FAILED_FILE = OUTPUT_DIR / "VSKP1_failed.json"
STATUS_FILE = DATA_DIR / "status.json"
LOG_FILE = LOG_DIR / "scraper.log"

# API Configuration
SCRAPER_API_KEY = "72efff2e41f7f4898cb0ba5cb1aa1ce7"  # Replace with your actual API key
SCRAPER_API_ENDPOINT = "https://api.scraperapi.com"
TARGET_BASE_URL = "https://httpbin.org/"  # Replace with your actual target URL

# User-Agent header
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'

# ---------------------- LOGGING SETUP ----------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------- GLOBAL STATE ----------------------
should_pause = False
should_stop = False
scraper_thread = None

# ---------------------- API SCRAPING FUNCTIONS ----------------------
def scrape_with_api(cid):
    """Scrape data using ScraperAPI"""
    try:
        # Encode the target URL with the CID
        target_url = f"{TARGET_BASE_URL}?cid={cid}"
        encoded_url = quote(target_url, safe='')
        
        # Construct the API URL with headers
        api_url = f"{SCRAPER_API_ENDPOINT}?api_key={SCRAPER_API_KEY}&url={encoded_url}"
        
        # Custom headers
        headers = {
            'User-Agent': USER_AGENT
        }
        
        logger.info(f"Scraping CID {cid} via API: {api_url}")
        
        # Make the request with timeout and headers
        response = requests.get(api_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            # Process the response data
            data = response.json()
            
            # Extract relevant information (modify according to your needs)
            sample_month = datetime.now().strftime("%Y-%m")
            amount = 100.0  # Replace with actual data extraction
            
            return {
                "sample_month": sample_month,
                "amount": amount,
                "raw_data": data  # Include raw data for debugging
            }
        else:
            logger.error(f"API request failed for CID {cid}: Status {response.status_code}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error for CID {cid}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error processing API response for CID {cid}: {str(e)}")
        return None

# ---------------------- BROWSER SETUP ----------------------
def initialize_browser():
    """Initialize Chrome with proper options for Render.com"""
    chrome_options = Options()
    
    # Essential options for running on Render
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--headless=new")  # New headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Set User-Agent for browser
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    
    # For Render.com specifically - use Chromium instead of Chrome
    chrome_options.binary_location = "/usr/bin/chromium-browser"
    
    # Set up ChromeDriver
    chrome_service = ChromeService(ChromeDriverManager().install())
    
    try:
        driver = webdriver.Chrome(
            service=chrome_service,
            options=chrome_options
        )
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize browser: {e}")
        raise

# ---------------------- SCRAPING FUNCTIONS ----------------------
def scraping_worker():
    global should_pause, should_stop
    
    # Initialize data structures
    output_data = {}
    not_scraped = set()
    
    try:
        # Load input data
        try:
            df = pd.read_excel(INPUT_FILE, header=None, engine='openpyxl')
            cid_list = df[0].astype(str).tolist()
            logger.info(f"Loaded {len(cid_list)} CIDs to process")
        except Exception as e:
            logger.error(f"Failed to read input file: {e}")
            return
        
        # Main scraping loop
        for cid in cid_list:
            if should_stop:
                logger.info("Scraping stopped by user request")
                break
                
            if should_pause:
                logger.info("Scraping paused by user request")
                while should_pause and not should_stop:
                    time.sleep(1)
                if should_stop:
                    break
                
            logger.info(f"Processing CID: {cid}")
            
            # Try API scraping first
            api_result = scrape_with_api(cid)
            
            if api_result:
                output_data[cid] = api_result
                continue
                
            # Fall back to browser scraping if API fails
            logger.info(f"API failed for CID {cid}, falling back to browser scraping")
            driver = None
            try:
                driver = initialize_browser()
                
                # Your actual browser scraping logic would go here
                # For demonstration, we'll just simulate scraping
                driver.get("https://www.google.com")  # Replace with your actual URL
                time.sleep(1)  # Simulate processing time
                
                # Simulate successful scrape with dummy data
                output_data[cid] = {
                    "sample_month": "2025-06",
                    "amount": 100.0
                }
                
            except Exception as e:
                logger.error(f"Browser scraping failed for CID {cid}: {e}")
                not_scraped.add(cid)
            finally:
                if driver is not None:
                    driver.quit()
        
        # Save results
        save_data(output_data, not_scraped)
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
    finally:
        logger.info("Scraping completed")

def save_data(output_data, not_scraped):
    """Save data ensuring directories exist"""
    try:
        # Ensure output directory exists (double-check)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Save successful data
        if output_data:
            df = pd.DataFrame.from_dict(output_data, orient='index')
            df.to_excel(OUTPUT_FILE, index_label="CID")
            logger.info(f"Saved {len(output_data)} records to {OUTPUT_FILE}")
        
        # Save failed CIDs
        if not_scraped:
            with open(FAILED_FILE, 'w') as f:
                json.dump(list(not_scraped), f)
            logger.info(f"Saved {len(not_scraped)} failed CIDs to {FAILED_FILE}")
            
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# ---------------------- FLASK ROUTES ----------------------
@app.route('/start-scraping', methods=['POST'])
def start_scraping():
    global scraper_thread, should_pause, should_stop
    
    if scraper_thread and scraper_thread.is_alive():
        return jsonify({"status": "error", "message": "Scraping already running"}), 400
    
    should_pause = False
    should_stop = False
    
    scraper_thread = threading.Thread(target=scraping_worker)
    scraper_thread.start()
    
    return jsonify({
        "status": "success", 
        "message": "Scraping started",
        "data_dirs": {
            "input": str(INPUT_DIR),
            "output": str(OUTPUT_DIR),
            "logs": str(LOG_DIR)
        },
        "scraping_method": "API with browser fallback"
    })

@app.route('/status', methods=['GET'])
def status():
    if not scraper_thread:
        return jsonify({"status": "inactive"})
    
    return jsonify({
        "status": "running" if scraper_thread.is_alive() else "inactive",
        "output_files": {
            "success": str(OUTPUT_FILE),
            "failed": str(FAILED_FILE)
        },
        "api_endpoint": SCRAPER_API_ENDPOINT
    })

@app.route('/test-api', methods=['GET'])
def test_api():
    """Endpoint to test the API connection"""
    test_url = "https://httpbin.org/get"
    encoded_url = quote(test_url, safe='')
    api_url = f"{SCRAPER_API_ENDPOINT}?api_key={SCRAPER_API_KEY}&url={encoded_url}"
    
    try:
        headers = {
            'User-Agent': USER_AGENT
        }
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return jsonify({
                "status": "success",
                "message": "API connection successful",
                "response_sample": response.json()
            })
        else:
            return jsonify({
                "status": "error",
                "message": f"API returned status {response.status_code}",
                "response": response.text
            }), 400
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    logger.info("Initializing application...")
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info(f"Input directory: {INPUT_DIR}")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info(f"Log directory: {LOG_DIR}")
    logger.info(f"Using ScraperAPI with key: {SCRAPER_API_KEY[:4]}...{SCRAPER_API_KEY[-4:]}")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
