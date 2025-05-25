import os
import time
import json
import asyncio
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv
import discord
from discord.ext import tasks

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('icbc_checker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ICBC Credentials
LAST_NAME = os.getenv('ICBC_LAST_NAME')
LICENSE_NUMBER = os.getenv('ICBC_LEARNER_LICENSE')
KEYWORD = os.getenv('ICBC_KEYWORD')

# Discord Configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

if not DISCORD_CHANNEL_ID:
    logger.error("DISCORD_CHANNEL_ID is not set in .env file")
    logger.info("Please create a .env file with the following content:")
    logger.info("""
    # ICBC Credentials
    ICBC_LAST_NAME=your_last_name
    ICBC_LEARNER_LICENSE=your_license_number
    ICBC_KEYWORD=your_keyword

    # Discord Configuration
    DISCORD_BOT_TOKEN=your_discord_bot_token
    DISCORD_CHANNEL_ID=your_channel_id

    # Check interval (in minutes)
    CHECK_INTERVAL_MINUTES=5
    """)
    exit(1)

try:
    DISCORD_CHANNEL_ID = int(DISCORD_CHANNEL_ID)
except ValueError:
    logger.error(f"DISCORD_CHANNEL_ID must be a number, got: {DISCORD_CHANNEL_ID}")
    exit(1)

# Check interval in minutes
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL_MINUTES', '5'))
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds

# Initialize Discord client
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# Store previously found appointments to avoid duplicate notifications
previous_appointments = set()

class ICBCChecker:
    def __init__(self):
        self.driver = None
        self.setup_driver()

    def setup_driver(self):
        try:
            # Set up Chrome options
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-notifications')
            
            # Add experimental options
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            
            # Initialize ChromeDriver with simple setup
            logger.info("Initializing Chrome WebDriver...")
            driver_manager = ChromeDriverManager()
            driver_path = driver_manager.install()
            
            # Extract the actual chromedriver executable path
            if 'chromedriver-win32' in driver_path:
                driver_path = os.path.join(os.path.dirname(driver_path), 'chromedriver.exe')
            elif not driver_path.endswith('.exe'):
                driver_path = driver_path + '.exe'
                
            logger.info(f"Using ChromeDriver at: {driver_path}")
            
            if not os.path.exists(driver_path):
                raise FileNotFoundError(f"ChromeDriver not found at: {driver_path}")
            
            # Create service with explicit path
            service = Service(
                executable_path=driver_path,
                log_path='chromedriver.log'
            )
            
            # Initialize the driver with service and options
            logger.info("Creating Chrome WebDriver instance...")
            self.driver = webdriver.Chrome(
                service=service,
                options=chrome_options
            )
            
            # Set window size and wait timeout
            self.driver.set_window_size(1920, 1080)
            self.wait = WebDriverWait(self.driver, 20)
            logger.info("Chrome WebDriver initialized successfully in headless mode")
            
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {str(e)}")
            logger.error("Stack trace:", exc_info=True)
            # Log additional diagnostic information
            try:
                import platform
                logger.error(f"System information:")
                logger.error(f"OS: {platform.system()} {platform.version()}")
                logger.error(f"Python version: {platform.python_version()}")
                logger.error(f"Architecture: {platform.architecture()}")
                
                # Try to get Chrome version
                import subprocess
                try:
                    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                    if os.path.exists(chrome_path):
                        version = subprocess.check_output([chrome_path, "--version"]).decode().strip()
                        logger.error(f"Chrome version: {version}")
                except Exception as chrome_error:
                    logger.error(f"Could not determine Chrome version: {str(chrome_error)}")
            except Exception as info_error:
                logger.error(f"Error getting system information: {str(info_error)}")
            raise

    def login(self):
        try:
            # Navigate to login page
            self.driver.get('https://onlinebusiness.icbc.com/webdeas-ui/login;type=driver')
            logger.info("Navigated to login page")
            
            # Wait for and fill in login fields
            self.wait.until(EC.presence_of_element_located((By.ID, 'mat-input-0'))).send_keys(LAST_NAME)
            self.wait.until(EC.presence_of_element_located((By.ID, 'mat-input-1'))).send_keys(LICENSE_NUMBER)
            self.wait.until(EC.presence_of_element_located((By.ID, 'mat-input-2'))).send_keys(KEYWORD)
            logger.info("Filled in login credentials")
            
            # Accept terms
            terms_checkbox = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'mat-checkbox-inner-container')))
            terms_checkbox.click()
            
            # Click sign in
            sign_in_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Sign in')]")))
            sign_in_button.click()
            
            # Wait for navigation to complete
            self.wait.until(EC.url_contains('/booking'))
            logger.info("Successfully logged in")
            return True
        except TimeoutException as e:
            logger.error(f"Timeout during login: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False

    def check_availability(self):
        try:
            logger.info("Starting appointment availability check...")
            
            # Wait for and click the "By office" tab using exact XPath
            logger.info("Waiting for 'By office' tab to be present...")
            tab_xpath = "/html/body/div/div/div/mat-dialog-container/app-search-modal/div/div/form/div[1]/mat-tab-group/mat-tab-header/div[2]/div/div/div[2]"
            
            by_office_tab = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, tab_xpath))
            )
            logger.info("Found 'By office' tab, clicking...")
            by_office_tab.click()
            logger.info("Clicked 'By office' tab successfully")
            
            # Wait for and interact with the location input using exact XPath
            logger.info("Waiting for location input field...")
            input_xpath = "/html/body/div/div[1]/div/mat-dialog-container/app-search-modal/div/div/form/div[1]/mat-tab-group/div/mat-tab-body[2]/div/div/mat-form-field/div/div[1]/div[3]/input"
            
            location_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, input_xpath))
            )
            
            # Ensure input is clickable
            self.wait.until(
                EC.element_to_be_clickable((By.XPATH, input_xpath))
            )
            
            logger.info("Found location input, clicking and entering location...")
            location_input.click()
            location_name = "Richmond driver licensing (Lansdowne Centre mall)"
            location_input.send_keys(location_name)
            logger.info(f"Entered location: {location_name}")
            
            # Small wait for the dropdown to populate
            time.sleep(1)
            
            # Wait for and click the location option using exact XPath
            logger.info("Waiting for location option to appear...")
            option_xpath = "/html/body/div/div[2]/div/div/mat-option/span"
            
            richmond_option = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, option_xpath))
            )
            logger.info("Found location option, clicking...")
            richmond_option.click()
            logger.info("Selected Richmond location successfully")
            
            # Wait for the results popup using exact XPath
            logger.info("Waiting for results popup...")
            results_xpath = "/html/body/div/div[2]/div/mat-dialog-container/app-eligible-tests/div/div[2]"
            
            results_container = self.wait.until(
                EC.presence_of_element_located((By.XPATH, results_xpath))
            )
            logger.info("Results popup found, looking for appointments...")
            
            # Look for appointment slots within the results container
            try:
                # First check for the "no appointments" message
                no_appointments_elements = results_container.find_elements(By.XPATH, ".//p[contains(text(), 'no appointment') or contains(text(), 'No appointment')]")
                if no_appointments_elements:
                    logger.info("No appointments available message found")
                    return []
                
                # Look for appointment slots
                available_slots = results_container.find_elements(By.XPATH, ".//div[contains(@class, 'appointment-time')]")
                appointments = []
                
                for slot in available_slots:
                    try:
                        # Find the associated date (looking within the current context)
                        date_element = slot.find_element(By.XPATH, "./preceding::div[contains(@class, 'appointment-date')][1]")
                        date_text = date_element.text
                        time_text = slot.text
                        appointment = f"{date_text} at {time_text}"
                        appointments.append(appointment)
                        logger.info(f"Found appointment: {appointment}")
                    except Exception as e:
                        logger.warning(f"Failed to parse an appointment slot: {str(e)}")
                
                if not appointments:
                    logger.info("No available appointments found in the results")
                else:
                    logger.info("Successfully found appointments:")
                    for apt in appointments:
                        print(f"Available: {apt}")
                
                return appointments
                
            except Exception as e:
                logger.error(f"Error parsing results: {str(e)}")
                return []
            
        except Exception as e:
            logger.error(f"Error checking availability: {str(e)}")
            logger.error("Stack trace:", exc_info=True)
            return []

    def close(self):
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
                logger.info("WebDriver closed successfully")
        except Exception as e:
            logger.error(f"Error closing WebDriver: {str(e)}")

@client.event
async def on_ready():
    logger.info(f'Discord bot logged in as {client.user}')
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Send startup notification
    try:
        channel = client.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            startup_message = f"🟢 **ICBC Appointment Checker Started** - {current_time}\n\n"
            startup_message += f"I'll check for appointments every {CHECK_INTERVAL} minutes.\n"
            startup_message += "I'll notify you about:\n"
            startup_message += "• New appointments when they become available\n"
            startup_message += "• Current appointment status on each check\n"
            startup_message += "• Any errors that occur during checking"
            await channel.send(startup_message)
    except Exception as e:
        logger.error(f"Failed to send startup notification: {str(e)}")
    
    check_appointments.start()

@tasks.loop(minutes=CHECK_INTERVAL)
async def check_appointments():
    global previous_appointments
    checker = None
    
    try:
        checker = ICBCChecker()
        if checker.login():
            appointments = checker.check_availability()
            
            # Convert appointments list to set for comparison
            current_appointments = set(appointments)
            
            # Get the Discord channel
            channel = client.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Find new appointments
                new_appointments = current_appointments - previous_appointments
                
                if new_appointments:
                    # New appointments found
                    message = "🚨 **New ICBC Road Test Appointments Available!**\n\n"
                    message += "\n".join([f"📅 {apt}" for apt in new_appointments])
                    message += "\n\nBook now at: https://onlinebusiness.icbc.com/webdeas-ui/booking"
                    await channel.send(message)
                    logger.info(f"Sent notification for {len(new_appointments)} new appointments")
                elif not current_appointments:
                    # No appointments available
                    message = f"⚠️ **ICBC Appointment Check Update** - {current_time}\n\n"
                    message += "No appointments currently available at Richmond (Lansdowne Centre mall).\n"
                    message += "I'll keep checking and notify you when appointments become available."
                    await channel.send(message)
                    logger.info("Sent notification for no available appointments")
                else:
                    # Appointments exist but no new ones
                    message = f"ℹ️ **ICBC Appointment Check Update** - {current_time}\n\n"
                    message += "Currently available appointments:\n"
                    message += "\n".join([f"📅 {apt}" for apt in current_appointments])
                    message += "\n\nNo new appointments since last check."
                    await channel.send(message)
                    logger.info("Sent notification for existing appointments")
            
            # Update previous appointments
            previous_appointments = current_appointments
    
    except Exception as e:
        logger.error(f"Error in check_appointments: {str(e)}")
        logger.error("Stack trace:", exc_info=True)
        
        try:
            channel = client.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                error_message = f"❌ **ICBC Checker Error** - {current_time}\n\n"
                error_message += "Failed to check appointments.\n"
                error_message += "I'll try again in the next scheduled check."
                await channel.send(error_message)
        except Exception as notify_error:
            logger.error(f"Failed to send error notification: {str(notify_error)}")
    
    finally:
        if checker:
            checker.close()

if __name__ == "__main__":
    # Verify required environment variables
    required_vars = ['ICBC_LAST_NAME', 'ICBC_LEARNER_LICENSE', 'ICBC_KEYWORD', 'DISCORD_BOT_TOKEN', 'DISCORD_CHANNEL_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)
        
    logger.info("Starting ICBC appointment checker")
    client.run(DISCORD_TOKEN) 