import sys, json
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\Users\sushi\.gemini\antigravity\brain\9d9ef939-d7e4-4351-afb7-77891dfb8cfd\.system_generated\logs\transcript_full.jsonl'
lines = open(path, 'r', encoding='utf-8').readlines()

# Find specific steps
for idx in [7872, 7876, 7908, 7914]:
    for l in lines:
        obj = json.loads(l)
        if obj.get('step_index') == idx:
            tc = obj.get('tool_calls', [])
            for t in tc:
                name = t.get('name', '')
                if name in ('replace_file_content', 'multi_replace_file_content'):
                    args = t.get('args', {})
                    print(f"\n===== Step {idx}: {name} =====")
                    print(f"File: {args.get('TargetFile', '')}")
                    print(f"Description: {args.get('Description', '')}")
                    print(f"--- TargetContent ---")
                    print(args.get('TargetContent', '')[:500])
                    print(f"--- ReplacementContent ---")
                    print(args.get('ReplacementContent', '')[:500])
            break
