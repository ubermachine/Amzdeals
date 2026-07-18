import re
text = open('amazon_dump.html', encoding='utf-8').read()
comps = re.findall(r'data-component-type="([^"]+)"', text)
print("Data component types found:", set(comps))
