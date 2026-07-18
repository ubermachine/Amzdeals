from bs4 import BeautifulSoup
import sys

with open('amazon_dump.html', 'r', encoding='utf-8') as f:
    html = f.read()
soup = BeautifulSoup(html, 'lxml')
items = soup.select('[data-component-type="s-search-result"][data-asin]')
orig = items[0].select_one('span.a-price[data-a-strike="true"] .a-offscreen, span.a-text-price .a-offscreen')
if orig and orig.parent:
    print(orig.parent.prettify())
