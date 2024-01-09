from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
import sys
import os
import re

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

# Open the local HTML file
current_directory = os.getcwd()
file_path = f"file:///Users/otchy/Documents/GitHub/Python/KindleDeals/dummy.html"
driver.get(file_path)

XPATH_DESC_DEFAULT = """//*[@id="bookDescription_feature_div"]/div/div[1]/span[not(contains(text(),'※'))]"""
XPATH_DESC_SPAN = '//*[@id="bookDescription_feature_div"]/div/div[1]/span'

info = ""

def get_book_description(info):
    # Find <span> elements that do NOT contain '※'
    span_elements = driver.find_elements(By.XPATH, XPATH_DESC_DEFAULT)
    if span_elements:
        description = "\n".join([span.text for span in span_elements])
        info += description
    else:
        info += retry_book_description()
    return info

def retry_book_description():
    print("Retrieving the description: second attempt")
    span_elements = driver.find_elements(By.XPATH, XPATH_DESC_SPAN)
    if span_elements:
        return filter_description_with_regex(span_elements)
    else:
        exit_with_error(f"ERROR: Obtaining description failed.\n{driver.current_url}")

# Retrieve all the <span> elements and filter lines starting with '※'
def filter_description_with_regex(span_elements):
    filtered_lines = []
    for span in span_elements:
        inner_html = span.get_attribute('innerHTML')
        lines = inner_html.split('<br>')
        for line in lines:
            if not re.match(r'^\s*※|^\s*$', line):
                filtered_line = re.sub('<[^<]+?>', '', line).strip()
                filtered_lines.append(filtered_line)
    return '\n'.join(filtered_lines)

def verify_book_info(info):
    if not info:
        exit_with_error(f"ERROR: info empty\n{driver.current_url}")

def exit_with_error(*args):
    msg = ' '.join(map(str, args))
    print(msg)
    driver.quit()
    sys.exit(1)

info = get_book_description(info)
verify_book_info(info)
print(info)
driver.quit()
