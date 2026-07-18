from bs4 import BeautifulSoup
from scraper.parser import _parse_price

text = open('amazon_dump.html', encoding='utf-8').read()
soup = BeautifulSoup(text, 'lxml')
item = soup.select_one('[data-asin="B0BRQ2QTL2"]')
orig_tag = item.select_one('span.a-price[data-a-strike="true"] .a-offscreen, span.a-text-price .a-offscreen')
val = orig_tag.get_text()
print('Length:', len(val))
print('Parsed:', _parse_price(val))
