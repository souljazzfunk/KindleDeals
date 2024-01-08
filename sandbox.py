from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import os
import re

options = Options()
options.add_argument('--headless')
driver = webdriver.Chrome(options=options)

# Open the local HTML file
current_directory = os.getcwd()
file_path = f"file:///Users/otchy/Documents/GitHub/Python/KindleDeals/dummy.html"
driver.get(file_path)

XPATH_SPAN = '//*[@id="bookDescription_feature_div"]/div/div[1]/span'
span_elements = driver.find_elements(By.XPATH, XPATH_SPAN)

filtered_lines = []
for span in span_elements:
    inner_html = span.get_attribute('innerHTML')
    lines = inner_html.split('<br>')
    for line in lines:
        if not re.match(r'^\s*※|^\s*$', line):
            filtered_line = re.sub('<[^<]+?>', '', line).strip()
            filtered_lines.append(filtered_line)

filtered_text = '\n'.join(filtered_lines)
print(filtered_text)

# Close the browser
driver.quit()
