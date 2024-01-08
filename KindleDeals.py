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
XPATH_DESC_DEFAULT = """//*[@id="bookDescription_feature_div"]/div/div[1]/span[not(contains(text(),'※'))]"""
XPATH_DESC_SPAN = '//*[@id="bookDescription_feature_div"]/div/div[1]/span'
XPATH_KU = '//span[@class="a-size-base a-color-secondary ku-promo-message"]'
MAX_RETRIES = 10
RETRY_WAIT_TIME = 5

class AmazonScraper:
    def __init__(self):
        options = Options()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"')
        # chrome_service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install(), log_path="chromedriver.log"), options=options)

    def login(self, email, password):
        url = 'https://www.amazon.co.jp/hko/deals'
        self.driver.get(url)
        self.driver.find_element(By.XPATH, '//div[@id="nav-signin-tooltip"]/a/span').click()
        self.driver.find_element(By.ID, "ap_email").send_keys(email)
        self.driver.find_element(By.ID, "continue").submit()
        self.driver.find_element(By.ID, "ap_password").send_keys(password)
        self.driver.find_element(By.ID, "signInSubmit").submit()

        def check_url(driver):
            current_url = urlparse(driver.current_url)
            base_current_url = f"{current_url.scheme}://{current_url.netloc}{current_url.path}"
            return base_current_url == url

        try:
            WebDriverWait(self.driver, 60).until(check_url)
            print("Login successful: ", self.driver.title)
        except TimeoutException:
            print("Timed out waiting for URL redirection. Current URL:", self.driver.current_url)
            self.driver.quit()
            sys.exit(1)

    def close(self):
        self.driver.quit()

    def get_book_element(self, index):
        try:
            xpath = f"//h2[contains(text(), 'Kindle日替わりセール')]/following::ol[1]/li[{index + 1}]"
            book = self.driver.find_element(By.XPATH, xpath)
            return book
        except NoSuchElementException:
            print("Failed to locate the Daily Sale element at:", self.driver.current_url)
            self.driver.quit()
            sys.exit(1)

    # refactor this!
    def get_book_info(self):
        info = [[''] * 3 for _ in range(3)]
        for i in range(3):
            book = self.get_book_element(i)
            book.click()
            print(self.driver.title)

            try:
                ku = self.driver.find_element(By.XPATH, XPATH_KU)
                if ku:
                    info[i][2] = '【Kindle Unlimited対象】'
            except NoSuchElementException:
                # print('Not included in Kindle Unlimited')
                pass

            try:
                # Find <span> elements that do NOT contain '※'
                print("Retrieving the description: first attempt")
                info[i][2] += self.driver.find_element(By.XPATH, XPATH_DESC_DEFAULT).text
            except:
                # Retrieve all the <span> elements and filter lines starting with '※'
                try:
                    print("Retrieving the description: second attempt")
                    span_elements = self.driver.find_elements(By.XPATH, XPATH_DESC_SPAN)
                    filtered_lines = []
                    for span in span_elements:
                        inner_html = span.text
                        lines = inner_html.split('<br>')
                        for line in lines:
                            if not re.match(r'^\s*※|^\s*$', line):
                                filtered_line = re.sub('<[^<]+?>', '', line).strip()
                                filtered_lines.append(filtered_line)

                    info[i][2] += '\n'.join(filtered_lines)
                except NoSuchElementException:
                    print(f"ERROR: Obtaining description failed.\n{self.driver.current_url}")
                    self.driver.quit()
                    exit(1)

            retry = 0
            while True:
                bk_btn = self.driver.find_element(By.XPATH, '//li[@id="amzn-ss-text-link"]/span')
                bk_btn.click()
                time.sleep(1)
                info[i][0] = self.driver.find_element(By.XPATH, XPATH_URL).text
                if info[i][0] != '':
                    break
                elif retry < MAX_RETRIES:
                    close_btn = self.driver.find_element(By.XPATH, '//button[@data-action="a-popover-close"]')
                    close_btn.click()
                    retry += 1
                    print('retrying', retry)
                    time.sleep(RETRY_WAIT_TIME)
                else:
                    print('ERROR: link creation failed')
                    self.driver.quit()
                    exit(1)
            info[i][1] = self.driver.find_element(By.XPATH, XPATH_TITLE).text

            for j in range(3):
                if info[i][j] == '':
                    print(f"ERROR: info[{i}][{j}] empty\n{self.driver.current_url}")
                    self.driver.quit()
                    exit(1)

            self.driver.back()

        return info

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

def generate_tweet_text(book_info, i):
    header = f"【本日限定のKindleセール {i+1}/3】\n"
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

    for i in reversed(range(3)):
        body = generate_tweet_text(book_info, i)
        # twitter_client.post_tweet(body)
        if i > 0:
            time.sleep(1)

if __name__ == '__main__':
    main()