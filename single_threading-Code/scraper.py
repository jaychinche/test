# import json
# import time
# import pandas as pd
# import os
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
# from selenium.webdriver.chrome.service import Service as ChromeService
# from webdriver_manager.chrome import ChromeDriverManager
# import requests
# import signal
# import sys
# import threading
# import logging
# from datetime import datetime
# from pathlib import Path

# # ---------------------- CONFIGURATION ----------------------
# BASE_DIR = Path(__file__).parent
# DATA_DIR = BASE_DIR / "data"
# INPUT_DIR = DATA_DIR / "input"
# OUTPUT_DIR = DATA_DIR / "output"
# LOG_DIR = BASE_DIR / "logs"

# INPUT_FILE = INPUT_DIR / "VSKP1_data.xlsx"
# OUTPUT_FILE = OUTPUT_DIR / "VSKP2_data.xlsx"
# FAILED_FILE = OUTPUT_DIR / "VSKP1_failed.json"
# STATUS_FILE = DATA_DIR / "status.json"
# LOG_FILE = LOG_DIR / "scraper.log"

# URL = "https://www.apeasternpower.com/viewBillDetailsMain"
# CHECK_INTERNET_URL = "http://www.google.com"
# MAX_RETRIES = 3
# RETRY_DELAY = 10
# PAGE_LOAD_TIMEOUT = 30
# CAPTCHA_RETRY_DELAY = 5

# # ---------------------- GLOBAL STATE ----------------------
# should_pause = False
# should_stop = False
# scraper_thread = None

# # ---------------------- LOGGING SETUP ----------------------
# def setup_logging():
#     """Configure logging system"""
#     LOG_DIR.mkdir(exist_ok=True)
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(levelname)s - %(message)s',
#         handlers=[
#             logging.FileHandler(LOG_FILE),
#             logging.StreamHandler()
#         ]
#     )
#     return logging.getLogger(__name__)

# logger = setup_logging()

# # ---------------------- UTILITY FUNCTIONS ----------------------
# def create_directories():
#     """Create necessary directories if they don't exist"""
#     for directory in [INPUT_DIR, OUTPUT_DIR, LOG_DIR]:
#         directory.mkdir(parents=True, exist_ok=True)
#     logger.info("Directory structure verified")

# def signal_handler(sig, frame):
#     """Handle interrupt signals"""
#     global should_stop
#     logger.info("\n🛑 Received interrupt signal. Stopping gracefully...")
#     should_stop = True
#     sys.exit(0)

# signal.signal(signal.SIGINT, signal_handler)

# def check_internet_connection():
#     """Check if internet connection is available"""
#     try:
#         requests.get(CHECK_INTERNET_URL, timeout=5)
#         return True
#     except requests.ConnectionError:
#         return False

# def wait_for_internet():
#     """Wait until internet connection is restored"""
#     logger.info("🌐 Waiting for internet connection...")
#     while not check_internet_connection():
#         time.sleep(5)
#     logger.info("🌐 Internet connection restored")

# def load_status():
#     """Load scraping status from file"""
#     if STATUS_FILE.exists() and STATUS_FILE.stat().st_size > 0:
#         try:
#             with open(STATUS_FILE, "r") as f:
#                 return json.load(f)
#         except Exception as e:
#             logger.error(f"⚠ Couldn't read status file: {e}")
#     return {"last_processed": 0, "total_processed": 0, "start_time": None}

# def save_status(status_data):
#     """Save scraping status to file"""
#     try:
#         with open(STATUS_FILE, "w") as f:
#             json.dump(status_data, f)
#     except Exception as e:
#         logger.error(f"⚠ Couldn't save status file: {e}")

# def load_existing_data():
#     """Load existing data from output files"""
#     # Load successful data
#     if OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0:
#         try:
#             existing_df = pd.read_excel(OUTPUT_FILE, engine='openpyxl')
#             if "CID" not in existing_df.columns:
#                 existing_df["CID"] = None
#         except Exception as e:
#             logger.error(f"⚠ Couldn't read existing Excel file: {e}")
#             existing_df = pd.DataFrame(columns=["CID"])
#     else:
#         existing_df = pd.DataFrame(columns=["CID"])
    
#     # Load failed CIDs
#     if FAILED_FILE.exists() and FAILED_FILE.stat().st_size > 0:
#         try:
#             with open(FAILED_FILE, "r") as f:
#                 existing_failed = set(json.load(f))
#         except Exception as e:
#             logger.error(f"⚠ Couldn't read failed JSON file: {e}")
#             existing_failed = set()
#     else:
#         existing_failed = set()
    
#     return existing_df, existing_failed

# def save_data(output_data, not_scraped):
#     """Save data to files"""
#     try:
#         # Convert output_data to DataFrame
#         data_list = []
#         for cid, months in output_data.items():
#             for month, amount in months.items():
#                 data_list.append({
#                     "CID": cid,
#                     "Month": month,
#                     "Amount": amount
#                 })
        
#         # Create DataFrame and save to Excel
#         temp_df = pd.DataFrame(data_list)
#         temp_df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")
        
#         # Save failed CIDs
#         if not_scraped:
#             # Load existing failed CIDs to avoid duplicates
#             if FAILED_FILE.exists() and FAILED_FILE.stat().st_size > 0:
#                 try:
#                     with open(FAILED_FILE, "r") as f:
#                         existing_failed = set(json.load(f))
#                     not_scraped = list(set(not_scraped).union(existing_failed))
#                 except Exception as e:
#                     logger.error(f"⚠ Couldn't read failed JSON file: {e}")
            
#             with open(FAILED_FILE, "w") as f:
#                 json.dump(list(not_scraped), f, indent=4)
#             logger.info(f"⚠ Failed CIDs saved to {FAILED_FILE}")
            
#     except Exception as e:
#         logger.error(f"❌ Error saving data: {str(e)}")

# def check_pause():
#     """Check if pause was requested"""
#     global should_pause
#     if should_pause:
#         logger.info("⏸ Scraping paused. Press '3' to resume or '4' to stop")
#         while should_pause:
#             time.sleep(1)
#             if should_stop:
#                 logger.info("🛑 Stopping as requested during pause")
#                 return True
#         logger.info("▶ Resuming scraping...")
#     return False

# def initialize_browser():
#     """Initialize and configure the browser"""
#     options = webdriver.ChromeOptions()
#     options.add_argument("--disable-notifications")
#     options.add_argument("--disable-popup-blocking")
#     options.add_argument("--disable-infobars")
#     options.add_argument("--disable-extensions")
#     options.add_argument("--disable-gpu")
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")
#     options.add_argument("--window-size=1920,1080")
    
#     if os.name == 'posix':  # Running on Linux/Unix
#         options.add_argument('--headless')
    
#     try:
#         driver = webdriver.Chrome(
#             service=ChromeService(ChromeDriverManager().install()),
#             options=options
#         )
#         driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
#         return driver
#     except Exception as e:
#         logger.error(f"❌ Failed to initialize browser: {e}")
#         raise

# def process_cid(driver, cid):
#     """Process a single CID"""
#     retries = 0
#     while retries < MAX_RETRIES:
#         try:
#             if not check_internet_connection():
#                 wait_for_internet()
            
#             driver.get(URL)
#             time.sleep(2)

#             # Enter CID
#             WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'ltscno')))
#             cid_field = driver.find_element(By.ID, 'ltscno')
#             cid_field.clear()
#             cid_field.send_keys(cid)

#             # Solve CAPTCHA
#             WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'Billquestion')))
#             captcha_text = driver.execute_script("return document.getElementById('Billquestion').innerText;").strip()
#             driver.find_element(By.ID, 'Billans').send_keys(captcha_text)
#             driver.find_element(By.ID, 'Billsignin').click()
#             time.sleep(2)

#             # Check for CAPTCHA error alert
#             try:
#                 alert = driver.switch_to.alert
#                 alert_text = alert.text
#                 alert.accept()
#                 raise Exception(f"CAPTCHA validation failed: {alert_text}")
#             except:
#                 pass

#             # Click History
#             try:
#                 WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "historyDivbtn")))
#                 driver.execute_script("window.scrollBy(0, 280)")
#                 time.sleep(2)
#                 driver.find_element(By.ID, "historyDivbtn").click()
#             except TimeoutException:
#                 raise Exception("CAPTCHA failed or no history button")

#             # Scrape data
#             WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "consumptionData")))
#             rows = driver.find_element(By.ID, "consumptionData").find_elements(By.TAG_NAME, "tr")[1:]
            
#             if not rows:
#                 raise Exception("No data rows found")

#             # Store data
#             cid_data = {}
#             for row in rows:
#                 cells = row.find_elements(By.TAG_NAME, "td")
#                 if len(cells) < 4:
#                     continue
                
#                 bill_month = cells[1].text.strip()
#                 try:
#                     amount_text = cells[3].find_element(By.TAG_NAME, "input").get_attribute("value").strip()
#                 except NoSuchElementException:
#                     amount_text = cells[3].text.strip()
                
#                 try:
#                     amount = float(amount_text.replace(",", "")) if amount_text.replace(",", "").replace(".", "").isdigit() else 0
#                 except:
#                     amount = 0
                
#                 cid_data[bill_month] = amount

#             return cid_data

#         except Exception as e:
#             retries += 1
#             logger.warning(f"⚠ Attempt {retries}/{MAX_RETRIES} failed for CID {cid}: {str(e)[:100]}")
#             if retries < MAX_RETRIES:
#                 time.sleep(CAPTCHA_RETRY_DELAY)
#             else:
#                 raise e

# def scraping_worker():
#     """Worker function that runs the scraping process"""
#     global should_pause, should_stop
    
#     # Setup browser
#     driver = None
#     try:
#         driver = initialize_browser()
        
#         # Load data
#         df = pd.read_excel(INPUT_FILE, header=None, engine='openpyxl')
#         cid_list = df[0].astype(str).tolist()
#         existing_df, existing_failed = load_existing_data()
#         status = load_status()
        
#         # Initialize data structures
#         output_data = {}
#         if not existing_df.empty:
#             # Convert existing data to our output format
#             for _, row in existing_df.iterrows():
#                 cid = row['CID']
#                 if cid not in output_data:
#                     output_data[cid] = {}
#                 # Assuming the data is stored with months as columns
#                 for col in row.index:
#                     if col != 'CID' and pd.notna(row[col]):
#                         output_data[cid][col] = row[col]
        
#         not_scraped = set(existing_failed)
        
#         # Track counts
#         total = len(cid_list)
#         success_count = status.get("total_processed", 0)
#         failed_count = len(not_scraped)
#         start_index = status.get("last_processed", 0)
        
#         # Update start time if not set
#         if "start_time" not in status or not status["start_time"]:
#             status["start_time"] = datetime.now().isoformat()
#             save_status(status)
        
#         logger.info(f"Starting scraping from index {start_index} of {total} CIDs")
#         logger.info(f"Previously processed: {success_count} success, {failed_count} failed")

#         for index in range(start_index, total):
#             if should_stop:
#                 logger.info("🛑 Stopping as requested")
#                 break
                
#             if check_pause():  # Returns True if we should stop during pause
#                 should_stop = True
#                 break
            
#             cid = cid_list[index]
            
#             # Skip already processed CIDs
#             if cid in output_data or cid in not_scraped:
#                 continue
                
#             logger.info(f"🔍 Processing CID {cid} ({index + 1}/{total})")
            
#             try:
#                 cid_data = process_cid(driver, cid)
#                 output_data[cid] = cid_data
#                 success_count += 1
#                 logger.info(f"✅ Successfully scraped CID {cid}")
                
#             except Exception as e:
#                 logger.error(f"❌ Failed to scrape CID {cid}: {str(e)[:100]}...")
#                 not_scraped.add(cid)
#                 failed_count += 1

#             # Save progress
#             status.update({
#                 "last_processed": index + 1,
#                 "total_processed": success_count,
#                 "last_updated": datetime.now().isoformat()
#             })
#             save_status(status)
            
#             # Periodic save every 10 CIDs
#             if (index + 1) % 10 == 0:
#                 save_data(output_data, not_scraped)
#                 logger.info(f"↻ Saved progress: {success_count} success, {failed_count} failed")

#         # Final save
#         save_data(output_data, not_scraped)
        
#         # Calculate elapsed time
#         if status.get("start_time"):
#             start_time = datetime.fromisoformat(status["start_time"])
#             elapsed = datetime.now() - start_time
#             elapsed_hours = elapsed.total_seconds() / 3600
#             cids_per_hour = success_count / elapsed_hours if elapsed_hours > 0 else success_count
            
#             logger.info(f"\n⏱ Scraping Statistics:")
#             logger.info(f"Total time: {str(elapsed)}")
#             logger.info(f"CIDs processed per hour: {cids_per_hour:.2f}")
        
#         logger.info(f"\n🎉 Scraping completed. Results:")
#         logger.info(f"Total CIDs: {total}")
#         logger.info(f"Successfully scraped: {success_count}")
#         logger.info(f"Failed to scrape: {failed_count}")
#         logger.info(f"Success rate: {success_count/total*100:.2f}%")
        
#     except Exception as e:
#         logger.error(f"❌ Scraping failed with error: {str(e)}")
#     finally:
#         if driver:
#             driver.quit()
#             logger.info("🚪 Browser closed")

# # ---------------------- CONTROL FUNCTIONS ----------------------
# def start_scraping():
#     """Start the scraping process"""
#     global should_pause, should_stop, scraper_thread
#     should_pause = False
#     should_stop = False
    
#     if scraper_thread and scraper_thread.is_alive():
#         logger.warning("⚠ Scraping is already running")
#         return
    
#     scraper_thread = threading.Thread(target=scraping_worker)
#     scraper_thread.start()
#     logger.info("🚀 Scraping started")

# def pause_scraping():
#     """Pause the scraping process"""
#     global should_pause
#     if not scraper_thread or not scraper_thread.is_alive():
#         logger.warning("⚠ No active scraping to pause")
#         return
    
#     should_pause = True
#     logger.info("⏸ Pause requested. Will pause after current CID completes.")

# def resume_scraping():
#     """Resume the scraping process"""
#     global should_pause
#     if not should_pause:
#         logger.warning("⚠ Scraping is not paused")
#         return
    
#     should_pause = False
#     logger.info("▶ Resuming scraping...")

# def stop_scraping():
#     """Stop the scraping process gracefully"""
#     global should_stop
#     if not scraper_thread or not scraper_thread.is_alive():
#         logger.warning("⚠ No active scraping to stop")
#         return
    
#     should_stop = True
#     logger.info("🛑 Stop requested. Will stop after current CID completes.")

# def show_status():
#     """Show current scraping status"""
#     if not scraper_thread:
#         logger.info("🛑 No scraping session exists")
#         return
    
#     if not scraper_thread.is_alive():
#         logger.info("🛑 No active scraping running")
#         return
    
#     status = load_status()
#     if should_pause:
#         logger.info("⏸ Scraping is currently paused")
#     elif should_stop:
#         logger.info("🛑 Scraping is stopping...")
#     else:
#         logger.info("▶ Scraping is running")
    
#     if status.get("start_time"):
#         start_time = datetime.fromisoformat(status["start_time"])
#         elapsed = datetime.now() - start_time
#         logger.info(f"⏱ Elapsed time: {str(elapsed)}")
    
#     logger.info(f"📊 Status: {status.get('last_processed', 0)} processed, {status.get('total_processed', 0)} successful")

# def print_menu():
#     """Print the control menu"""
#     print("\n" + "="*50)
#     print("AP Eastern Power Scraper Control Panel".center(50))
#     print("="*50)
#     print("1. Start scraping")
#     print("2. Pause scraping")
#     print("3. Resume scraping")
#     print("4. Stop scraping")
#     print("5. Check status")
#     print("6. Exit")
#     print("="*50)

# if __name__ == "__main__":
#     create_directories()
    
#     while True:
#         print_menu()
#         choice = input("\nEnter your choice (1-6): ")
        
#         if choice == "1":
#             start_scraping()
#         elif choice == "2":
#             pause_scraping()
#         elif choice == "3":
#             resume_scraping()
#         elif choice == "4":
#             stop_scraping()
#         elif choice == "5":
#             show_status()
#         elif choice == "6":
#             stop_scraping()  # Try to stop gracefully first
#             logger.info("👋 Exiting...")
#             break
#         else:
#             logger.warning("Invalid choice. Please try again.")

















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
import requests
import signal
import sys
import threading
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request

# ---------------------- FLASK APP SETUP ----------------------
app = Flask(__name__)

# ---------------------- CONFIGURATION ----------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

INPUT_FILE = INPUT_DIR / "VSKP1_data.xlsx"
OUTPUT_FILE = OUTPUT_DIR / "VSKP2_data.xlsx"
FAILED_FILE = OUTPUT_DIR / "VSKP1_failed.json"
STATUS_FILE = DATA_DIR / "status.json"
LOG_FILE = LOG_DIR / "scraper.log"

URL = "https://www.apeasternpower.com/viewBillDetailsMain"
CHECK_INTERNET_URL = "http://www.google.com"
MAX_RETRIES = 3
RETRY_DELAY = 10
PAGE_LOAD_TIMEOUT = 30
CAPTCHA_RETRY_DELAY = 5

# ---------------------- GLOBAL STATE ----------------------
should_pause = False
should_stop = False
scraper_thread = None

# ---------------------- LOGGING SETUP ----------------------
def setup_logging():
    """Configure logging system"""
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ---------------------- UTILITY FUNCTIONS ----------------------
def create_directories():
    """Create necessary directories if they don't exist"""
    for directory in [INPUT_DIR, OUTPUT_DIR, LOG_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    logger.info("Directory structure verified")

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global should_stop
    logger.info("\n🛑 Received interrupt signal. Stopping gracefully...")
    should_stop = True
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def check_internet_connection():
    """Check if internet connection is available"""
    try:
        requests.get(CHECK_INTERNET_URL, timeout=5)
        return True
    except requests.ConnectionError:
        return False

def wait_for_internet():
    """Wait until internet connection is restored"""
    logger.info("🌐 Waiting for internet connection...")
    while not check_internet_connection():
        time.sleep(5)
    logger.info("🌐 Internet connection restored")

def load_status():
    """Load scraping status from file"""
    if STATUS_FILE.exists() and STATUS_FILE.stat().st_size > 0:
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠ Couldn't read status file: {e}")
    return {"last_processed": 0, "total_processed": 0, "start_time": None}

def save_status(status_data):
    """Save scraping status to file"""
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status_data, f)
    except Exception as e:
        logger.error(f"⚠ Couldn't save status file: {e}")

def load_existing_data():
    """Load existing data from output files"""
    # Load successful data
    if OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0:
        try:
            existing_df = pd.read_excel(OUTPUT_FILE, engine='openpyxl')
            if "CID" not in existing_df.columns:
                existing_df["CID"] = None
        except Exception as e:
            logger.error(f"⚠ Couldn't read existing Excel file: {e}")
            existing_df = pd.DataFrame(columns=["CID"])
    else:
        existing_df = pd.DataFrame(columns=["CID"])
    
    # Load failed CIDs
    if FAILED_FILE.exists() and FAILED_FILE.stat().st_size > 0:
        try:
            with open(FAILED_FILE, "r") as f:
                existing_failed = set(json.load(f))
        except Exception as e:
            logger.error(f"⚠ Couldn't read failed JSON file: {e}")
            existing_failed = set()
    else:
        existing_failed = set()
    
    return existing_df, existing_failed

def save_data(output_data, not_scraped):
    """Save data to files"""
    try:
        # Convert output_data to DataFrame
        data_list = []
        for cid, months in output_data.items():
            for month, amount in months.items():
                data_list.append({
                    "CID": cid,
                    "Month": month,
                    "Amount": amount
                })
        
        # Create DataFrame and save to Excel
        temp_df = pd.DataFrame(data_list)
        temp_df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")
        
        # Save failed CIDs
        if not_scraped:
            # Load existing failed CIDs to avoid duplicates
            if FAILED_FILE.exists() and FAILED_FILE.stat().st_size > 0:
                try:
                    with open(FAILED_FILE, "r") as f:
                        existing_failed = set(json.load(f))
                    not_scraped = list(set(not_scraped).union(existing_failed))
                except Exception as e:
                    logger.error(f"⚠ Couldn't read failed JSON file: {e}")
            
            with open(FAILED_FILE, "w") as f:
                json.dump(list(not_scraped), f, indent=4)
            logger.info(f"⚠ Failed CIDs saved to {FAILED_FILE}")
            
    except Exception as e:
        logger.error(f"❌ Error saving data: {str(e)}")

def check_pause():
    """Check if pause was requested"""
    global should_pause
    if should_pause:
        logger.info("⏸ Scraping paused. Press '3' to resume or '4' to stop")
        while should_pause:
            time.sleep(1)
            if should_stop:
                logger.info("🛑 Stopping as requested during pause")
                return True
        logger.info("▶ Resuming scraping...")
    return False

def initialize_browser():
    """Initialize and configure the browser"""
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    if os.name == 'posix':  # Running on Linux/Unix
        options.add_argument('--headless')
    
    try:
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        return driver
    except Exception as e:
        logger.error(f"❌ Failed to initialize browser: {e}")
        raise

def process_cid(driver, cid):
    """Process a single CID"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            if not check_internet_connection():
                wait_for_internet()
            
            driver.get(URL)
            time.sleep(2)

            # Enter CID
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'ltscno')))
            cid_field = driver.find_element(By.ID, 'ltscno')
            cid_field.clear()
            cid_field.send_keys(cid)

            # Solve CAPTCHA
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'Billquestion')))
            captcha_text = driver.execute_script("return document.getElementById('Billquestion').innerText;").strip()
            driver.find_element(By.ID, 'Billans').send_keys(captcha_text)
            driver.find_element(By.ID, 'Billsignin').click()
            time.sleep(2)

            # Check for CAPTCHA error alert
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
                raise Exception(f"CAPTCHA validation failed: {alert_text}")
            except:
                pass

            # Click History
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "historyDivbtn")))
                driver.execute_script("window.scrollBy(0, 280)")
                time.sleep(2)
                driver.find_element(By.ID, "historyDivbtn").click()
            except TimeoutException:
                raise Exception("CAPTCHA failed or no history button")

            # Scrape data
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "consumptionData")))
            rows = driver.find_element(By.ID, "consumptionData").find_elements(By.TAG_NAME, "tr")[1:]
            
            if not rows:
                raise Exception("No data rows found")

            # Store data
            cid_data = {}
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 4:
                    continue
                
                bill_month = cells[1].text.strip()
                try:
                    amount_text = cells[3].find_element(By.TAG_NAME, "input").get_attribute("value").strip()
                except NoSuchElementException:
                    amount_text = cells[3].text.strip()
                
                try:
                    amount = float(amount_text.replace(",", "")) if amount_text.replace(",", "").replace(".", "").isdigit() else 0
                except:
                    amount = 0
                
                cid_data[bill_month] = amount

            return cid_data

        except Exception as e:
            retries += 1
            logger.warning(f"⚠ Attempt {retries}/{MAX_RETRIES} failed for CID {cid}: {str(e)[:100]}")
            if retries < MAX_RETRIES:
                time.sleep(CAPTCHA_RETRY_DELAY)
            else:
                raise e

def scraping_worker():
    """Worker function that runs the scraping process"""
    global should_pause, should_stop
    
    # Setup browser
    driver = None
    try:
        driver = initialize_browser()
        
        # Load data
        df = pd.read_excel(INPUT_FILE, header=None, engine='openpyxl')
        cid_list = df[0].astype(str).tolist()
        existing_df, existing_failed = load_existing_data()
        status = load_status()
        
        # Initialize data structures
        output_data = {}
        if not existing_df.empty:
            # Convert existing data to our output format
            for _, row in existing_df.iterrows():
                cid = row['CID']
                if cid not in output_data:
                    output_data[cid] = {}
                # Assuming the data is stored with months as columns
                for col in row.index:
                    if col != 'CID' and pd.notna(row[col]):
                        output_data[cid][col] = row[col]
        
        not_scraped = set(existing_failed)
        
        # Track counts
        total = len(cid_list)
        success_count = status.get("total_processed", 0)
        failed_count = len(not_scraped)
        start_index = status.get("last_processed", 0)
        
        # Update start time if not set
        if "start_time" not in status or not status["start_time"]:
            status["start_time"] = datetime.now().isoformat()
            save_status(status)
        
        logger.info(f"Starting scraping from index {start_index} of {total} CIDs")
        logger.info(f"Previously processed: {success_count} success, {failed_count} failed")

        for index in range(start_index, total):
            if should_stop:
                logger.info("🛑 Stopping as requested")
                break
                
            if check_pause():  # Returns True if we should stop during pause
                should_stop = True
                break
            
            cid = cid_list[index]
            
            # Skip already processed CIDs
            if cid in output_data or cid in not_scraped:
                continue
                
            logger.info(f"🔍 Processing CID {cid} ({index + 1}/{total})")
            
            try:
                cid_data = process_cid(driver, cid)
                output_data[cid] = cid_data
                success_count += 1
                logger.info(f"✅ Successfully scraped CID {cid}")
                
            except Exception as e:
                logger.error(f"❌ Failed to scrape CID {cid}: {str(e)[:100]}...")
                not_scraped.add(cid)
                failed_count += 1

            # Save progress
            status.update({
                "last_processed": index + 1,
                "total_processed": success_count,
                "last_updated": datetime.now().isoformat()
            })
            save_status(status)
            
            # Periodic save every 10 CIDs
            if (index + 1) % 10 == 0:
                save_data(output_data, not_scraped)
                logger.info(f"↻ Saved progress: {success_count} success, {failed_count} failed")

        # Final save
        save_data(output_data, not_scraped)
        
        # Calculate elapsed time
        if status.get("start_time"):
            start_time = datetime.fromisoformat(status["start_time"])
            elapsed = datetime.now() - start_time
            elapsed_hours = elapsed.total_seconds() / 3600
            cids_per_hour = success_count / elapsed_hours if elapsed_hours > 0 else success_count
            
            logger.info(f"\n⏱ Scraping Statistics:")
            logger.info(f"Total time: {str(elapsed)}")
            logger.info(f"CIDs processed per hour: {cids_per_hour:.2f}")
        
        logger.info(f"\n🎉 Scraping completed. Results:")
        logger.info(f"Total CIDs: {total}")
        logger.info(f"Successfully scraped: {success_count}")
        logger.info(f"Failed to scrape: {failed_count}")
        logger.info(f"Success rate: {success_count/total*100:.2f}%")
        
    except Exception as e:
        logger.error(f"❌ Scraping failed with error: {str(e)}")
    finally:
        if driver:
            driver.quit()
            logger.info("🚪 Browser closed")

# ---------------------- FLASK ROUTES ----------------------
@app.route('/start-scraping', methods=['POST'])
def start_scraping_api():
    """API endpoint to start the scraping process"""
    global should_pause, should_stop, scraper_thread
    
    if scraper_thread and scraper_thread.is_alive():
        return jsonify({
            "status": "error",
            "message": "Scraping is already running"
        }), 400
    
    should_pause = False
    should_stop = False
    
    scraper_thread = threading.Thread(target=scraping_worker)
    scraper_thread.start()
    
    return jsonify({
        "status": "success",
        "message": "Scraping started successfully"
    })

@app.route('/scraping-status', methods=['GET'])
def scraping_status_api():
    """API endpoint to check scraping status"""
    status = load_status()
    
    if not scraper_thread:
        return jsonify({
            "status": "inactive",
            "message": "No scraping session exists"
        })
    
    if not scraper_thread.is_alive():
        return jsonify({
            "status": "inactive",
            "message": "No active scraping running"
        })
    
    response = {
        "status": "paused" if should_pause else "stopping" if should_stop else "running",
        "last_processed": status.get("last_processed", 0),
        "total_processed": status.get("total_processed", 0)
    }
    
    if status.get("start_time"):
        start_time = datetime.fromisoformat(status["start_time"])
        elapsed = datetime.now() - start_time
        response["elapsed_time"] = str(elapsed)
    
    return jsonify(response)

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    create_directories()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=9000)