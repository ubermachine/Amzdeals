from bs4 import BeautifulSoup
import sys

with open('amazon_dump.html', 'r', encoding='utf-8') as f:
    html = f.read()
soup = BeautifulSoup(html, 'lxml')
items = soup.select('[data-component-type="s-search-result"][data-asin]')
print(items[0].prettify())
