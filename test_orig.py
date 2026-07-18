import json
from bs4 import BeautifulSoup

with open('amazon_dump.html', 'r', encoding='utf-8') as f:
    html = f.read()
soup = BeautifulSoup(html, "lxml")
result_items = soup.select('[data-component-type="s-search-result"][data-asin]')

for item in result_items[:2]:
    orig_tag = item.select_one('span.a-price[data-a-strike="true"] .a-offscreen, span.a-text-price .a-offscreen')
    if orig_tag:
        print("Raw text:", repr(orig_tag.get_text()))
        print("parent text:", repr(orig_tag.parent.get_text()))
