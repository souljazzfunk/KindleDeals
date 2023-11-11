from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import time
import tweepy
import sys
import os
sys.path.append(os.environ.get('API_KEYS'))
from api_keys import TwitterApiKeys, AmazonLogin

class AmazonScraper:
    def __init__(self):
        options = Options()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"')
        # chrome_service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install(), log_path="chromedriver.log"), options=options)

    def login(self, email, password):
        url = 'https://www.amazon.co.jp/b?ie=UTF8&node=3251934051'
        self.driver.get(url)
        self.driver.find_element(By.XPATH, '//div[@id="nav-signin-tooltip"]/a/span').click()
        self.driver.find_element(By.ID, "ap_email").send_keys(email)
        self.driver.find_element(By.ID, "continue").submit()
        self.driver.find_element(By.ID, "ap_password").send_keys(password)
        self.driver.find_element(By.ID, "signInSubmit").submit()

    def close(self):
        self.driver.quit()

    # refactor this!
    def get_book_info(self):
        # Constants for XPaths and retry settings
        XPATH_URL = '//textarea[@id="amzn-ss-text-shortlink-textarea"]'
        XPATH_TITLE = '//span[@id="productTitle"]'
        XPATH_DESC = """//div[@class="a-expander-content a-expander-partial-collapse-content"]/span[not(contains(text(),'※この商品はタブレット'))][1]"""
        XPATH_KU = '//span[@class="a-size-base a-color-secondary ku-promo-message"]'
        MAX_RETRIES = 10
        RETRY_WAIT_TIME = 5

        # 0:URL, 1:Title, 2:Description
        xpath0 = '//textarea[@id="amzn-ss-text-shortlink-textarea"]'
        xpath1 = '//span[@id="productTitle"]'
        xpath2 = """//div[@class="a-expander-content a-expander-partial-collapse-content"]/span[not(contains(text(),'※この商品はタブレット'))][1]"""
        xpath_ku = '//span[@class="a-size-base a-color-secondary ku-promo-message"]'
        info = [[''] * 3 for _ in range(3)]
        for i in range(3):
            book = self.driver.find_element(By.XPATH, '//div[@id="anonCarousel1"]/ol/li[' + str(i + 1) + ']/a/div/img')
            book.click()
            print(self.driver.title)
            retry = 0
            while True:
                bk_btn = self.driver.find_element(By.XPATH, '//li[@id="amzn-ss-text-link"]/span')
                bk_btn.click()
                time.sleep(1)
                info[i][0] = self.driver.find_element(By.XPATH, xpath0).text
                if info[i][0] != '':
                    break
                elif retry < 10:
                    close_btn = self.driver.find_element(By.XPATH, '//button[@data-action="a-popover-close"]')
                    close_btn.click()
                    retry += 1
                    print('retrying', retry)
                    time.sleep(5)
                else:
                    print('ERROR: link creation failed')
                    self.driver.quit()
                    exit(1)
            info[i][1] = self.driver.find_element(By.XPATH, xpath1).text
            try:
                ku = self.driver.find_element(By.XPATH, xpath_ku)
                if ku:
                    info[i][2] = '【Kindle Unlimited対象】'
            except NoSuchElementException:
                # print('Not included in Kindle Unlimited')
                pass
            info[i][2] += self.driver.find_element(By.XPATH, xpath2).get_attribute("innerText")
            for j in range(3):
                if info[i][j] == '':
                    print(f"ERROR: info[{i}][{j}] empty")
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
        twitter_client.post_tweet(body)
        if i > 0:
            time.sleep(1)

if __name__ == '__main__':
    main()