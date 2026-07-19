import sys
import os
import re

def extract_task(plan_path, task_num, out_path):
    if not os.path.exists(plan_path):
        print(f"Plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(2)
        
    with open(plan_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by headers that start with '### Task N:'
    # We want to parse and extract the content under task_num
    lines = content.split('\n')
    extracted = []
    intask = False
    infence = False
    
    # Matches '### Task N:' (any level heading, optionally space before/after 'Task N')
    task_header_re = re.compile(r'^#+[ \t]+Task[ \t]+([0-9]+)', re.IGNORECASE)
    
    for line in lines:
        if line.startswith('```'):
            infence = not infence
            
        if not infence:
            match = task_header_re.match(line)
            if match:
                current_task = int(match.group(1))
                intask = (current_task == task_num)
                
        if intask:
            extracted.append(line)
            
    if not extracted:
        print(f"Task {task_num} not found in {plan_path}", file=sys.stderr)
        sys.exit(3)
        
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(extracted) + '\n')
        
    print(f"Wrote {out_path}: {len(extracted)} lines")

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python task_brief.py PLAN_PATH TASK_NUMBER OUT_PATH")
        sys.exit(1)
    extract_task(sys.argv[1], int(sys.argv[2]), sys.argv[3])
