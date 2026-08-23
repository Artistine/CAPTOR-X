with open('gui/style.css', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
for i, line in enumerate(lines):
    if 'form-group' in line:
        print(f"Line {i+1}: {line.strip()}")
        # Print surrounding lines
        start = max(0, i-5)
        end = min(len(lines), i+6)
        print("Context:")
        for idx in range(start, end):
            print(f"  {idx+1}: {lines[idx].strip()}")
        print("-" * 40)
