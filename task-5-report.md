# Task 5 Report

## Issue Investigated
The HTML parser (`scraper/parser.py`) was misinterpreting the original prices of products, yielding erroneous values like 1.28 and enormous negative discounts (e.g., -14900%). This was primarily caused by two issues:
1. The selector for the original price tag (`span.a-text-price .a-offscreen`) loosely matched unit prices provided by Amazon (e.g., "₹1.28/millilitre").
2. The `_parse_price` function simply removed all commas and whitespace from duplicated price strings (e.g., "₹1,280 ₹1,280" from hidden accessibility spans) and tried to cast the entire string to a float, resulting in incorrect values.

## Changes Made
1. **Updated Selector**: Modified the `orig_tag` CSS selector in `scraper/parser.py` to ensure it only retrieves price tags with a strikethrough (`data-a-strike="true"`). The fallback selector is now strictly `'span.a-text-price[data-a-strike="true"] .a-offscreen'`.
2. **Robust Regex Parsing**: Updated `_parse_price()` to use regular expressions to extract the *first valid numeric price sequence* (matching numbers, commas, and optional 2-decimal places) rather than replacing non-numeric characters across the whole string.

## Testing and Verification
Created a local test script to run the updated `parse_search_results` against `amazon_dump.html`. Verified that prices like ₹1,280 and ₹350 are now correctly extracted, and discount percentages correctly fall into the expected ranges (e.g., 40% to 80%) without yielding distorted small values.
