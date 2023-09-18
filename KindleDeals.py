from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import tweepy
import sys
import os
sys.path.append(os.environ.get('API_KEYS'))
from api_keys import TwitterApiKeys, AmazonLogin
# import argparse

def login(email, passwd):
    login_btn = driver.find_element(By.XPATH, '//div[@id="nav-signin-tooltip"]/a/span')
    login_btn.click()
    form_email = driver.find_element(By.ID, "ap_email")
    form_email.send_keys(email)
    btn_continue = driver.find_element(By.ID, "continue")
    btn_continue.submit()
    form_passwd = driver.find_element(By.ID, "ap_password")
    form_passwd.send_keys(passwd)
    btn_submit = driver.find_element(By.ID, "signInSubmit")
    btn_submit.submit()

def get_info():
    # 0:URL, 1:Title, 2:Description
    xpath0 = '//textarea[@id="amzn-ss-text-shortlink-textarea"]'
    xpath1 = '//span[@id="productTitle"]'
    xpath2 = """//div[@class="a-expander-content a-expander-partial-collapse-content"]/span[not(contains(text(),'※この商品はタブレット'))][1]"""
    xpath_ku = '//span[@class="a-size-base a-color-secondary ku-promo-message"]'
    info = [[''] * 3 for _ in range(3)]
    for i in range(3):
        book = driver.find_element(By.XPATH, '//div[@id="anonCarousel2"]/ol/li[' + str(i + 1) + ']/a/div/img')
        book.click()
        print(driver.title)
        retry = 0
        while True:
            bk_btn = driver.find_element(By.XPATH, '//li[@id="amzn-ss-text-link"]/span')
            bk_btn.click()
            time.sleep(1)
            info[i][0] = driver.find_element(By.XPATH, xpath0).text
            if info[i][0] != '':
                break
            elif retry < 10:
                close_btn = driver.find_element(By.XPATH, '//button[@data-action="a-popover-close"]')
                close_btn.click()
                retry += 1
                print('retrying', retry)
                time.sleep(5)
            else:
                print('ERROR: link creation failed')
                driver.quit()
                exit(1)
        info[i][1] = driver.find_element(By.XPATH, xpath1).text
        try:
            ku = driver.find_element(By.XPATH, xpath_ku)
            if ku:
                info[i][2] = '【Kindle Unlimited対象】'
        except:
            print('not included in KU')
        info[i][2] += driver.find_element(By.XPATH, xpath2).get_attribute("innerText")
        for j in range(3):
            if info[i][j] == '':
                print(f"ERROR: info[{i}][{j}] empty")
                driver.quit()
                exit(1)
        driver.back()
    return info

url = 'https://www.amazon.co.jp/b?ie=UTF8&node=3251934051'
my = AmazonLogin()
user_name = my.user_name
passwd = my.passwd

# parser = argparse.ArgumentParser(description='Toggle headless mode for Selenium')
# parser.add_argument('--headed', action='store_true', help='Run Selenium in headed mode')
# args = parser.parse_args()

chrome_service = Service(ChromeDriverManager().install())
options = Options()
options.add_argument('--window-size=1920,1080')
options.add_argument('--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"')

# if not args.headed:
    # options.add_argument("--headless")

driver = webdriver.Chrome(service=chrome_service, options=options)

driver.get(url)
login(user_name, passwd)
print(driver.title)
bk_info = get_info()
driver.quit()

my = TwitterApiKeys()
tw = tweepy.Client(
    consumer_key=my.consumer_key,
    consumer_secret=my.consumer_secret,
    access_token=my.access_token,
    access_token_secret=my.access_token_secret
)

for i in reversed(range(3)):
    header = f"【本日限定のKindleセール {i+1}/3】\n"
    desc = bk_info[i][2][:int((280 - 4 - len(bk_info[i][0]) - len((header + bk_info[i][1]).encode('utf-8'))/3*2)/2 - 8)] + "…"
    body = header + bk_info[i][1] + "\n" + bk_info[i][0] + "\n\n" + desc
    print(body)
    try:
        tw.create_tweet(text=body)
        # print(body)
    except Exception as err:
        print(err)
    if i < 2:
        time.sleep(1)
