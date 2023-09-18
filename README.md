# Amazon Book Scraper and Twitter Poster

## Introduction

This project is designed to automate the scraping of book information from Amazon's daily deals page and subsequently post this information on Twitter. Utilizing Selenium for web scraping and Tweepy for Twitter API interaction, the project offers an effective way to share good deals on books with Twitter followers.

## Features

- Automated login into Amazon account
- Scrape book details including:
  - Title
  - URL
  - Description
- Post scraped information to Twitter

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/souljazzfunk/KindleDeals.git
   ```
   
2. Navigate to the project directory:
   ```bash
   cd KindleDeals
   ```
   
3. Install the required packages.

## Requirements

- Python 3.x
- Selenium
- Tweepy
- ChromeDriver

## Usage

1. Create `api_keys.py` and enter your Amazon login details and Twitter API keys.
   
2. Run the script:
   ```
   python KindleDeals.py
   ```

## License

This project is licensed under the MIT License.
