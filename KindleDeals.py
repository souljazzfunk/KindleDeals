from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse
import time
import tweepy
import sys
import os
import re

sys.path.append(os.environ.get('API_KEYS'))
from api_keys import TwitterApiKeys, AmazonLogin

XPATH_URL = '//textarea[@id="amzn-ss-text-shortlink-textarea"]'
XPATH_TITLE = '//span[@id="productTitle"]'
XPATH_DESC_DEFAULT = '//*[@id="bookDescription_feature_div"]/div/div[1]/span[not(contains(text(),"※"))]'
XPATH_DESC_SPAN = '//*[@id="bookDescription_feature_div"]/div/div[1]/span'
XPATH_KU = '//span[@class="a-size-base a-color-secondary ku-promo-message"]'
MAX_RETRIES = 5
RETRY_WAIT_TIME = 5

class AmazonScraper:
    def __init__(self):
        options = Options()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"')
        # chrome_service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install(), log_path="chromedriver.log"), options=options)

    def login(self, email, password):
        # url = "https://www.amazon.co.jp/hko/deals"
        url = "https://www.amazon.co.jp/kindle-dbs/browse?metadata=storeType=ebooks&widgetId=ebooks-deals-storefront_KindleDailyDealsStrategy&sourceType=recs"
        self.driver.get(url)
        
        # Wait for and click the account link
        account_link = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@id="nav-link-accountList"]/a'))
        )
        account_link.click()
        
        # Wait for and fill in email
        email_field = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'][name='email']"))
        )
        email_field.send_keys(email)
        
        # Wait for and click continue
        continue_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "continue"))
        )
        continue_button.click()
        
        # Wait for and fill in password
        password_field = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "ap_password"))
        )
        password_field.send_keys(password)
        
        # Wait for and click sign in
        sign_in_button = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "signInSubmit"))
        )
        sign_in_button.click()

        # def check_url(driver):
        #     current_url = urlparse(driver.current_url)
        #     base_current_url = f"{current_url.scheme}://{current_url.netloc}{current_url.path}"
        #     return base_current_url == url

        # try:
        #     WebDriverWait(self.driver, 60).until(check_url)
        #     print("Login successful: ", self.driver.title)
        # except TimeoutException:
        #     self.exit_with_error("Timed out waiting for URL redirection. Current URL:")

    def close(self):
        self.driver.quit()


    def exit_with_error(self, *args):
        msg = ' '.join(map(str, args))
        print(msg)
        current_url = self.driver.current_url.split('?', 1)[0]
        print(current_url)
        self.driver.quit()
        sys.exit(1)


    def get_book_element(self, index):
        try:
            # Find books in the grid view
            books = self.driver.find_elements(
                By.CSS_SELECTOR,
                'div.a-column.a-span4.a-spacing-extra-large'
            )
            if index < len(books):
                return books[index]
            else:
                self.exit_with_error(f"Book index {index} out of range. Found {len(books)} books.")
        except NoSuchElementException:
            self.exit_with_error("Failed to locate the book elements in grid view")


    def get_book_info(self):
        try:
            # Wait for the grid view to load
            time.sleep(5)
            
            # Find all book elements in the grid view
            books = self.driver.find_elements(
                By.CSS_SELECTOR,
                'div.a-column.a-span4.a-spacing-extra-large'
            )
            print(f"Found {len(books)} books in grid view")
            
            info = [[''] * 3 for _ in range(len(books))]
            for i in range(len(books)):
                self.process_book(i, info)
            return info
            
        except NoSuchElementException as e:
            print(f"Error finding book elements: {e}")
            return []


    def process_book(self, index, info):
        book = self.get_book_element(index)
        
        # Scroll element into view and wait a bit for the animation
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", book)
        time.sleep(1)
        
        book.click()
        print(self.driver.title)
        time.sleep(3)
        self.get_kindle_unlimited_status(index, info)
        self.get_book_description(index, info)
        self.get_book_url_and_title(index, info)
        self.verify_book_info(index, info)
        self.driver.back()


    def get_kindle_unlimited_status(self, index, info):
        try:
            ku = self.driver.find_element(By.XPATH, XPATH_KU)
            if ku:
                info[index][2] = '【Kindle Unlimited対象】'
        except NoSuchElementException:
            pass


    def get_book_description(self, index, info):
        XPATH_DESC_DIV = '//*[@id="bookDescription_feature_div"]/div/div[1]'
        retry_count = 0
        while True:
            # First try the original method - finding <span> elements without '※'
            span_elements = self.driver.find_elements(By.XPATH, XPATH_DESC_DEFAULT)
            if span_elements:
                description = "\n".join([span.text for span in span_elements])
                info[index][2] += description
                print("Description found successfully")
                break
            else:
                print("First method failed. Trying alternative method...")
                # Try the second method - all span elements
                span_elements = self.driver.find_elements(By.XPATH, XPATH_DESC_SPAN)
                if span_elements:
                    description = "\n".join([span.text for span in span_elements])
                    info[index][2] += description
                    break
                else:
                    # If both methods fail, try the fallback method
                    try:
                        fallback_span = self.driver.find_element(By.XPATH, '//*[@id="bookDescription_feature_div"]//span')
                        inner_html = fallback_span.get_attribute('innerHTML')
                        if '<br' in inner_html:  # Only use this method if we detect <br> tags
                            description = re.sub(r'<br\s*/?>', '\n', inner_html)
                            description = re.sub(r'<[^>]+>', '', description)
                            description = re.sub(r'\n\s*\n', '\n', description.strip())
                            info[index][2] += description
                            break
                    except NoSuchElementException:
                        pass

                    if retry_count == MAX_RETRIES:
                        print(f"WARNING: Could not obtain description after {MAX_RETRIES} attempts")
                        info[index][2] = ""
                        break
                    else:
                        retry_count += 1
                        print(f"Retrying ({retry_count})")
                        self.driver.refresh()
                        time.sleep(RETRY_WAIT_TIME)


    def get_book_url_and_title(self, index, info):
        self.get_book_url(index, info)
        info[index][1] = self.driver.find_element(By.XPATH, XPATH_TITLE).text


    def get_book_url(self, index, info):
        retry = 0
        while True:
            bk_btn = self.driver.find_element(By.XPATH, '//span[@id="amzn-ss-text-link"]')
            bk_btn.click()
            time.sleep(1)
            info[index][0] = self.driver.find_element(By.XPATH, XPATH_URL).text
            if info[index][0] != '':
                break
            elif retry < MAX_RETRIES:
                self.close_popover_modal()
                retry += 1
            else:
                self.exit_with_error('ERROR: link creation failed')


    def close_popover_modal(self):
        close_btn = self.driver.find_element(By.XPATH, '//button[@data-action="a-popover-close"]')
        close_btn.click()
        print('retrying to get the URL')
        time.sleep(RETRY_WAIT_TIME)
                

    def verify_book_info(self, index, info):
        # Skip verification if the book was marked as skipped
        if info[index][0] == 'Skipped due to page load error':
            return
            
        # Only verify URL and title (indices 0 and 1)
        for j in range(2):
            if not info[index][j]:
                self.exit_with_error(f"ERROR: info[{index}][{j}] empty")


class TwitterClient:
    def __init__(self, api_keys):
        self.client = tweepy.Client(
            consumer_key=api_keys.consumer_key,
            consumer_secret=api_keys.consumer_secret,
            access_token=api_keys.access_token,
            access_token_secret=api_keys.access_token_secret
        )

    def post_tweet(self, text):
        try:
            self.client.create_tweet(text=text)
        except Exception as e:
            print(e)

def generate_tweet_text(book_info, i, number_of_books):
    header = f"【本日限定のKindleセール {i+1}/{number_of_books}】\n"
    book_title = book_info[i][1]
    book_url = book_info[i][0]
    book_desc = book_info[i][2]
    tweet_text = trim_text_for_tweet(header + book_title + "\n" + book_url + "\n\n" + book_desc)
    print(tweet_text)
    return tweet_text

def calculate_weighted_length(text):
    total_length = 0
    
    for char in text:
        if char == '　':  # Full-width space
            total_length += 2
        elif char.isspace() or char.isascii():  # Whitespace or ASCII
            total_length += 1
        elif len(char.encode('utf-8')) > 1:  # Multi-byte characters (Assuming these are Japanese)
            total_length += 2
        else:
            print(f"Unhandled character: {char}")
            total_length += 2  # Default handling
    
    return total_length

def trim_text_for_tweet(text):
    MAX_TWEET_LENGTH = 280
    INITIAL_TRIM_LENGTH = 200 # Unweighted
    ELLIPSIS_LENGTH = 2  # The length of '…'

    # Initial trim
    trimmed_text = text[:INITIAL_TRIM_LENGTH]
    text_length = calculate_weighted_length(trimmed_text)
    
    # Trimming loop
    while text_length + ELLIPSIS_LENGTH > MAX_TWEET_LENGTH:
        trimmed_text = trimmed_text[:-1]
        text_length = calculate_weighted_length(trimmed_text)
    
    # Adding ellipsis
    trimmed_text += "…"
    
    return trimmed_text

def main():
    # Amazon Scraper
    amazon_credentials = AmazonLogin()
    scraper = AmazonScraper()
    scraper.login(amazon_credentials.user_name, amazon_credentials.passwd)

    book_info = scraper.get_book_info()
    scraper.close()

    # Twitter Client
    twitter_keys = TwitterApiKeys()
    twitter_client = TwitterClient(twitter_keys)

    for i in reversed(range(len(book_info))):
        body = generate_tweet_text(book_info, i, len(book_info))
        twitter_client.post_tweet(body)
        if i > 0:
            time.sleep(1)

if __name__ == '__main__':
    main()