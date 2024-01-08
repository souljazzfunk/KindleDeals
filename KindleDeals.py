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
            self.exit_with_error("Timed out waiting for URL redirection. Current URL:", self.driver.current_url)

    def close(self):
        self.driver.quit()


    def exit_with_error(self, *args):
        msg = ' '.join(map(str, args))
        print(msg)
        self.driver.quit()
        sys.exit(1)


    def get_book_element(self, index):
        try:
            xpath = f"//h2[contains(text(), 'Kindle日替わりセール')]/following::ol[1]/li[{index + 1}]"
            book = self.driver.find_element(By.XPATH, xpath)
            return book
        except NoSuchElementException:
            self.exit_with_error("Failed to locate the Daily Sale element at:", self.driver.current_url)


    def get_book_info(self):
        info = [[''] * 3 for _ in range(3)]
        for i in range(3):
            self.process_book(i, info)
        return info


    def process_book(self, index, info):
        book = self.get_book_element(index)
        book.click()
        print(self.driver.title)
        time.sleep(5)
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
        try:
            # Find <span> elements that do NOT contain '※'
            span_elements = self.driver.find_elements(By.XPATH, XPATH_DESC_DEFAULT)
            description = "\n".join([span.text for span in span_elements])
            info[index][2] += description
        except NoSuchElementException:
            self.retry_book_description(index, info)


    def retry_book_description(self, index, info):
        try:
            print("Retrieving the description: second attempt")
            info[index][2] += self.get_filtered_description()
        except NoSuchElementException:
            self.exit_with_error(f"ERROR: Obtaining description failed.\n{self.driver.current_url}")


    # Retrieve all the <span> elements and filter lines starting with '※'
    def get_filtered_description(self):
        span_elements = self.driver.find_elements(By.XPATH, XPATH_DESC_SPAN)
        filtered_lines = []
        for span in span_elements:
            inner_html = span.text
            lines = inner_html.split('<br>')
            for line in lines:
                if not re.match(r'^\s*※|^\s*$', line):
                    filtered_line = re.sub('<[^<]+?>', '', line).strip()
                    filtered_lines.append(filtered_line)
        return '\n'.join(filtered_lines)


    def get_book_url_and_title(self, index, info):
        self.get_book_url(index, info)
        info[index][1] = self.driver.find_element(By.XPATH, XPATH_TITLE).text


    def get_book_url(self, index, info):
        retry = 0
        while True:
            bk_btn = self.driver.find_element(By.XPATH, '//li[@id="amzn-ss-text-link"]/span')
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
        print('retrying')
        time.sleep(RETRY_WAIT_TIME)
                

    def verify_book_info(self, index, info):
        for j in range(3):
            if info[index][j] == '':
                self.exit_with_error(f"ERROR: info[{index}][{j}] empty\n{self.driver.current_url}")


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
        twitter_client.post_tweet(body)
        if i > 0:
            time.sleep(1)

if __name__ == '__main__':
    main()