import sys
import subprocess
import os

def generate_review_package(base, head, out_path):
    # Run git commands to collect info
    try:
        # Check commits
        commits_output = subprocess.check_output(
            ["git", "log", "--oneline", f"{base}..{head}"],
            text=True, encoding="utf-8"
        )
        # Check diff stat
        stat_output = subprocess.check_output(
            ["git", "diff", "--stat", f"{base}..{head}"],
            text=True, encoding="utf-8"
        )
        # Check detailed diff with context -U10
        diff_output = subprocess.check_output(
            ["git", "diff", "-U10", f"{base}..{head}"],
            text=True, encoding="utf-8"
        )
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Review package: {base}..{head}\n\n")
        f.write("## Commits\n")
        f.write(commits_output)
        f.write("\n## Files changed\n")
        f.write(stat_output)
        f.write("\n## Diff\n")
        f.write(diff_output)

    print(f"Wrote review package to {out_path}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python review_package.py BASE HEAD OUT_PATH")
        sys.exit(1)
    generate_review_package(sys.argv[1], sys.argv[2], sys.argv[3])
