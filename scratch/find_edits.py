import sys, json
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\Users\sushi\.gemini\antigravity\brain\9d9ef939-d7e4-4351-afb7-77891dfb8cfd\.system_generated\logs\transcript.jsonl'
lines = open(path, 'r', encoding='utf-8').readlines()
print(f'Total steps: {len(lines)}')
# Find edit/replace/write file calls in last 200 steps
for l in lines[-200:]:
    obj = json.loads(l)
    tc = obj.get('tool_calls', [])
    for t in tc:
        name = t.get('name', '')
        if name in ('replace_file_content', 'multi_replace_file_content', 'write_to_file'):
            args = t.get('args', {})
            target = args.get('TargetFile', '')
            desc = args.get('Description', '')[:100]
            print(f"Step {obj.get('step_index')}: {name} -> {target} | {desc}")
