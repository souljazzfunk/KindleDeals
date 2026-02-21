from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse
import time
import tweepy
import sys
import os
import re
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.environ.get('API_KEYS'))
from api_keys import TwitterApiKeys, AmazonLogin

_gemini_model = None

def init_gemini(api_key):
    global _gemini_model
    genai.configure(api_key=api_key)
    # _gemini_model = genai.GenerativeModel("gemini-2.5-flash-lite")
    _gemini_model = genai.GenerativeModel("gemini-3-flash-preview")

XPATH_URL = '//textarea[@id="amzn-ss-text-shortlink-textarea"]'
XPATH_TITLE = '//span[@id="productTitle"]'
XPATH_DESC_DEFAULT = '//*[@id="bookDescription_feature_div"]/div/div[1]/span[not(contains(text(),"※"))]'
XPATH_DESC_SPAN = '//*[@id="bookDescription_feature_div"]/div/div[1]/span'
XPATH_KU = '//span[@class="a-size-base a-color-secondary ku-promo-message"]'
MAX_RETRIES = 5
RETRY_WAIT_TIME = 5
MAX_BOOKS_TO_PROCESS = 3

MANGA_KEYWORDS = ['マンガ', 'まんが', '漫画', 'コミック', 'comic']
GENRE_PRIORITIES = [
    ['AI', '人工知能', '機械学習', '深層学習', 'ChatGPT', 'LLM', '生成AI', 'プログラミング', 'Python', 'エンジニア', 'IT', 'データ', 'Web', 'クラウド', 'セキュリティ'],
    ['音楽', 'ミュージック', 'ジャズ', '楽器', 'ピアノ', 'ギター', 'ドラム'],
    ['アジア', '中国', '韓国', '台湾', 'インド', '東南アジア', '東アジア'],
    ['哲学', '思想', '倫理'],
    ['ノンフィクション', 'ルポ', 'ドキュメント'],
    ['エッセイ', '随筆', 'コラム'],
    ['料理', 'レシピ', 'グルメ'],
]

def classify_book_priority(title):
    title_lower = title.lower()
    for keyword in MANGA_KEYWORDS:
        if keyword.lower() in title_lower:
            return None
    for priority, keywords in enumerate(GENRE_PRIORITIES):
        for keyword in keywords:
            if keyword.lower() in title_lower:
                return priority
    return len(GENRE_PRIORITIES)

def classify_books_batch(titles):
    if not titles:
        return []
    if _gemini_model is not None:
        numbered = '\n'.join(f"{i+1}. {t}" for i, t in enumerate(titles))
        prompt = f"""以下の書籍タイトルのジャンルをそれぞれ分類し、ジャンル番号をカンマ区切りで返してください。

書籍タイトル一覧:
{numbered}

ジャンル:
0: AI・テクノロジー（AI・機械学習・プログラミング・IT・エンジニアリング・データサイエンス・コンピュータ）
1: 音楽（音楽理論・楽器・音楽史）
2: アジア（中国・韓国・台湾・東南アジア・インド・日本などのアジア諸国の文化・歴史・社会・旅行ガイド。欧米など非アジア地域は含まない）
3: 哲学・思想・倫理・宗教
4: ノンフィクション・ルポルタージュ・ドキュメンタリー・歴史・地政学・社会問題
5: エッセイ・随筆・コラム（著者の体験や意見を綴った文章。小説・フィクション・物語は含まない）
6: 料理・レシピ・グルメ・献立
7: その他（小説・フィクション・ミステリー・ビジネス書・自己啓発・旅行ガイド（アジア以外）・育児・趣味など）

分類の注意:
- 文庫・ミステリー・恋愛・SFなど小説・物語は必ず7
- 「地球の歩き方」はアジア・中東諸国（タイ・中国・韓国・台湾・インド・トルコなど）なら2、欧米（ローマ・フランス・ドイツなど）なら7
- ビジネス書・自己啓発・コミュニケーション本は7
- アジアの歴史・文化を扱う本は2（哲学・思想ではなくアジアを優先）

タイトルの順番に対応した数字のみをカンマ区切りで返してください（例: 5,3,7,0）"""
        try:
            response = _gemini_model.generate_content(prompt)
            parts = response.text.strip().split(',')
            results = [int(p.strip()) for p in parts]
            if len(results) == len(titles) and all(0 <= r <= 7 for r in results):
                return results
            print(f"WARNING: Gemini batch response malformed ({response.text.strip()!r}), falling back to keyword matching")
        except Exception as e:
            print(f"WARNING: Gemini batch classification failed, falling back to keyword matching: {e}")
    return [classify_book_priority(title) for title in titles]

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
        
        try:
            # Wait for and click the account link
            account_link = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="nav-link-accountList"]/a'))
            )
            account_link.click()
            print("account link clicked")

            # Wait for and fill in email
            email_field = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email'][name='email']"))
            )
            email_field.clear()
            email_field.send_keys(email)
            print("id typed")

            # Wait for and click continue
            continue_button = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((By.ID, "continue"))
            )
            continue_button.click()
            print("continue button clicked")

            # Wait for and fill in password - ensure it's clickable, not just present
            # Longer timeout to allow for OTP challenge
            password_field = WebDriverWait(self.driver, 120).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password'][name='password']"))
            )
            password_field.clear()
            password_field.send_keys(password)
            print("password typed")

            # Check if already logged in (e.g., after password change auto-login)
            # or wait for the sign-in button
            for _ in range(120):
                # Check for the sign-in button first
                sign_in_buttons = self.driver.find_elements(By.ID, "signInSubmit")
                if sign_in_buttons:
                    sign_in_buttons[0].click()
                    print("signin button clicked")
                    time.sleep(5)
                    break
                # If we're on the deals/browse page, login is already complete
                if 'kindle-dbs/browse' in self.driver.current_url:
                    print("Already logged in (redirected to deals page)")
                    break
                time.sleep(1)

            print("Login successful: ", self.driver.title)
            
        except TimeoutException as e:
            self.exit_with_error(f"Login timeout: {e}")
        except Exception as e:
            self.exit_with_error(f"Login error: {e}")

    def close(self):
        self.driver.quit()


    def exit_with_error(self, *args):
        msg = ' '.join(map(str, args))
        print(msg)
        current_url = self.driver.current_url.split('?', 1)[0]
        print(current_url)
        self.driver.quit()
        sys.exit(1)


    def get_book_element(self, index, max_retries=3):
        for attempt in range(max_retries):
            try:
                # Wait for books to be present in the grid view
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.a-column.a-span4.a-spacing-extra-large'))
                )
                
                # Find books in the grid view
                books = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    'div.a-column.a-span4.a-spacing-extra-large'
                )
                
                if index < len(books):
                    return books[index]
                else:
                    self.exit_with_error(f"Book index {index} out of range. Found {len(books)} books.")
                    
            except (NoSuchElementException, StaleElementReferenceException, TimeoutException) as e:
                if attempt < max_retries - 1:
                    print(f"Attempt {attempt + 1} failed: {e}. Retrying...")
                    time.sleep(2)
                else:
                    self.exit_with_error(f"Failed to locate the book elements after {max_retries} attempts: {e}")


    def get_book_info(self):
        try:
            time.sleep(5)
            books = self.driver.find_elements(
                By.CSS_SELECTOR,
                'div.a-column.a-span4.a-spacing-extra-large'
            )
            print(f"Found {len(books)} books in grid view")

            # Phase 1: collect all titles and detect manga
            entries = []
            for i, book in enumerate(books):
                try:
                    title_el = book.find_element(By.CSS_SELECTOR, 'span.browse-text-line')
                    title = title_el.text.strip()
                except NoSuchElementException:
                    title = ""
                title_lower = title.lower()
                is_manga = any(kw.lower() in title_lower for kw in MANGA_KEYWORDS)
                entries.append((i, title, is_manga))

            # Phase 2: batch classify non-manga titles with one Gemini call
            non_manga_titles = [title for _, title, is_manga in entries if not is_manga]
            priorities = classify_books_batch(non_manga_titles)

            # Phase 3: build candidates list
            priority_iter = iter(priorities)
            candidates = []
            for i, title, is_manga in entries:
                if is_manga:
                    print(f"  [{i}] SKIP (manga): {title}")
                else:
                    priority = next(priority_iter)
                    print(f"  [{i}] priority {priority}: {title}")
                    candidates.append((priority, i, title))

            # Sort by priority, then by original order
            candidates.sort(key=lambda x: (x[0], x[1]))
            selected = candidates[:MAX_BOOKS_TO_PROCESS]
            print(f"Selected {len(selected)} books to process")

            info = [[''] * 3 for _ in range(len(selected))]
            for info_idx, (priority, grid_idx, title) in enumerate(selected):
                print(f"Processing [{grid_idx}]: {title}")
                self.process_book(grid_idx, info, info_idx)
            return info

        except NoSuchElementException as e:
            print(f"Error finding book elements: {e}")
            return []


    def process_book(self, grid_idx, info, info_idx):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Re-find the book element each time to avoid stale reference
                book = self.get_book_element(grid_idx)

                # Scroll element into view and wait a bit for the animation
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", book)
                time.sleep(1)

                # Re-find the book element after scrolling to ensure it's still valid
                book = self.get_book_element(grid_idx)
                book.click()
                print(self.driver.title)
                time.sleep(3)
                self.get_kindle_unlimited_status(info_idx, info)
                self.get_book_description(info_idx, info)
                self.get_book_url_and_title(info_idx, info)
                self.verify_book_info(info_idx, info)
                self.driver.back()

                # Wait for the page to fully load after going back
                time.sleep(2)
                break  # Success, exit retry loop

            except StaleElementReferenceException as e:
                if attempt < max_retries - 1:
                    print(f"Stale element error on attempt {attempt + 1}: {e}. Retrying...")
                    time.sleep(2)
                else:
                    self.exit_with_error(f"Failed to process book {grid_idx} after {max_retries} attempts due to stale elements")
            except Exception as e:
                self.exit_with_error(f"Error processing book {grid_idx}: {e}")


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

                # Try the third method - p>span structure, filtering ※ disclaimers
                p_span_elements = self.driver.find_elements(
                    By.XPATH, '//*[@id="bookDescription_feature_div"]/div/div[1]/p/span[not(contains(text(),"※"))]'
                )
                if p_span_elements:
                    description = "\n".join([span.text for span in p_span_elements])
                    info[index][2] += description
                    print("Description found via p>span method")
                    break

                else:
                    # If all methods fail, try the innerHTML fallback
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
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", bk_btn)
            time.sleep(0.5)
            try:
                bk_btn.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", bk_btn)
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

    def post_tweet(self, text, max_attempts=3):
        base_wait_time = 60
        for attempt in range(max_attempts):
            try:
                self.client.create_tweet(text=text)
                print(f"Tweet posted successfully")
                return True
            except tweepy.errors.TooManyRequests as e:
                if attempt < max_attempts - 1:
                    wait_time = base_wait_time * (2 ** attempt)
                    print(f"Rate limit hit (429). Waiting {wait_time} seconds before retry {attempt + 1}/{max_attempts}...")
                    time.sleep(wait_time)
                else:
                    print(f"Failed to post tweet after {max_attempts} attempts due to rate limiting: {e}")
                    return False
            except Exception as e:
                print(f"Error posting tweet: {e}")
                return False

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
    # Gemini
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if gemini_api_key:
        init_gemini(gemini_api_key)
    else:
        print("WARNING: GEMINI_API_KEY not set, using keyword matching fallback")

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
        # twitter_client.post_tweet(body)
        if i > 0:
            time.sleep(1)

if __name__ == '__main__':
    main()