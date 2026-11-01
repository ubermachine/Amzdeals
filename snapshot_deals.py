"""CLI utility to manage, dump, export, and compare daily deal snapshots.

Usage:
  python snapshot_deals.py --dump                    # Dump all deals from cache into deal_history.db
  python snapshot_deals.py --dates                   # List available snapshot dates
  python snapshot_deals.py --compare 2026-11-01 2026-11-02  # Compare two dates
  python snapshot_deals.py --export-csv 2026-11-01   # Export snapshot to CSV
  python snapshot_deals.py --export-json 2026-11-01  # Export snapshot to JSON
"""

import argparse
import asyncio
import csv
from datetime import datetime
import json
import os
import sys

from cache.history import (
    dump_cache_to_snapshots,
    list_snapshot_dates,
    get_snapshots_by_date,
    compare_snapshots,
    record_deal_snapshot,
    DEFAULT_HISTORY_DB,
)


def format_inr(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"Rs {val:,.2f}"


def cmd_dump(args):
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    count = dump_cache_to_snapshots(cache_db_path="cache.db", snapshot_date=date)
    print(f"\n[+] Successfully dumped {count} deals into '{DEFAULT_HISTORY_DB}' for date '{date}'.")
    cmd_dates(args)


def cmd_dates(args):
    dates = list_snapshot_dates()
    if not dates:
        print("\n[!] No snapshot dates found in database. Run --dump first.")
        return

    print("\n" + "=" * 80)
    print(f"{'Snapshot Date':<15} {'Deals':<8} {'Categories':<12} {'Avg Score':<12} {'True Deals':<12} {'Avg Price':<15}")
    print("=" * 80)
    for d in dates:
        print(
            f"{d['snapshot_date']:<15} {d['unique_deals']:<8} {d['categories_count']:<12} "
            f"{d['avg_score']:<12} {d['true_deals_count']:<12} {format_inr(d['avg_price']):<15}"
        )
    print("=" * 80)


def cmd_compare(args):
    d1 = args.date1
    d2 = args.date2
    if not d1 or not d2:
        dates = list_snapshot_dates()
        if len(dates) < 2:
            print("\n[!] Need at least two snapshot dates to compare. Use --dates to see available dates.")
            return
        d1 = dates[1]["snapshot_date"]
        d2 = dates[0]["snapshot_date"]

    res = compare_snapshots(d1, d2)
    s = res["summary"]

    print("\n" + "=" * 80)
    print(f" DAY-OVER-DAY DEAL COMPARISON: {d1}  -->  {d2}")
    print("=" * 80)
    print(f" Earlier Snapshot ({d1}): {s['earlier_total_deals']} deals")
    print(f" Later Snapshot   ({d2}): {s['later_total_deals']} deals")
    print(f" Price Drops:      {s['price_drops_count']} items (cheaper today!)")
    print(f" Price Hikes:      {s['price_hikes_count']} items (more expensive)")
    print(f" Unchanged:        {s['unchanged_price_count']} items")
    print(f" New Deals Added:  {s['new_deals_count']} items")
    print(f" Expired Deals:    {s['expired_deals_count']} items")
    print("=" * 80)

    if res["price_drops"]:
        print("\n [TOP PRICE DROPS]")
        for item in res["price_drops"][:8]:
            print(f"  - [{item['category']}] {item['title'][:55]}...")
            print(f"    Was {format_inr(item['old_price'])} -> Now {format_inr(item['new_price'])} (Save {format_inr(item['savings_inr'])}, -{item['drop_pct']}%) | Score: {item['deal_score']}")

    if res["new_deals"]:
        print("\n [NEW DEALS INTRODUCED]")
        for item in res["new_deals"][:8]:
            badge = " [TRUE DEAL]" if item.get("is_true_deal") else ""
            print(f"  - [{item['category']}] {item['title'][:55]}...{badge}")
            print(f"    Price: {format_inr(item['price'])} (-{item['discount_pct']}%) | Score: {item['deal_score']}")

    if res["expired_deals"]:
        print(f"\n [EXPIRED DEALS: {len(res['expired_deals'])} items dropped from top ranking]")
        for item in res["expired_deals"][:5]:
            print(f"  - [{item['category']}] {item['title'][:60]}... (Last price: {format_inr(item['last_price'])})")


def cmd_export_json(args):
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    deals = get_snapshots_by_date(date)
    filename = f"deals_{date}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Exported {len(deals)} deals for '{date}' to '{filename}'.")


def cmd_export_csv(args):
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    deals = get_snapshots_by_date(date)
    filename = f"deals_{date}.csv"
    if not deals:
        print(f"\n[!] No deals found for date '{date}'.")
        return

    fields = [
        "asin", "category", "title", "current_price", "effective_price",
        "original_price", "discount_pct", "deal_score", "is_true_deal",
        "rating", "review_count", "flipkart_price", "flipkart_verdict", "product_url"
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(deals)
    print(f"\n[+] Exported {len(deals)} deals for '{date}' to '{filename}'.")


def main():
    parser = argparse.ArgumentParser(description="Deal Finder Daily Snapshot & Historical Comparison CLI")
    parser.add_argument("--dump", action="store_true", help="Dump all current cached deals to history database")
    parser.add_argument("--dates", action="store_true", help="List all recorded snapshot dates")
    parser.add_argument("--compare", nargs="*", help="Compare two snapshot dates: --compare [DATE1] [DATE2]")
    parser.add_argument("--export-json", nargs="?", const="today", help="Export snapshot to JSON file: --export-json [DATE]")
    parser.add_argument("--export-csv", nargs="?", const="today", help="Export snapshot to CSV file: --export-csv [DATE]")
    parser.add_argument("--date", help="Target snapshot date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.dump:
        cmd_dump(args)
    elif args.dates:
        cmd_dates(args)
    elif args.compare is not None:
        args.date1 = args.compare[0] if len(args.compare) > 0 else None
        args.date2 = args.compare[1] if len(args.compare) > 1 else None
        cmd_compare(args)
    elif args.export_json is not None:
        args.date = None if args.export_json == "today" else args.export_json
        cmd_export_json(args)
    elif args.export_csv is not None:
        args.date = None if args.export_csv == "today" else args.export_csv
        cmd_export_csv(args)
    else:
        # Default action: dump today's cache and show summary
        cmd_dump(args)


if __name__ == "__main__":
    main()
