with open('main.py', 'r') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'print(f"Combined Text:' in line and '{combined_text}"' not in line:
        out.append(f'            print(f"Combined Text:\\n{{combined_text}}")\n')
        i += 2
    else:
        out.append(line)
        i += 1

with open('main.py', 'w') as f:
    f.writelines(out)
