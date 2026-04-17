with open('main.py', 'r') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    if 'final_result = f"## Fallback Model ({fallback_model})' in line and not '{result}"' in line:
        out.append(f'                    final_result = f"## Fallback Model ({{fallback_model}})\\n\\n{{result}}"\n')
        i += 3 # skip the next 2 lines which are blank and {result}
    elif 'final_result = f"## Main Model ({main_model})' in line and not '{result}"' in line:
        out.append(f'                    final_result = f"## Main Model ({{main_model}})\\n\\n{{result}}"\n')
        i += 3
    elif 'combined_text = "\\n\\n".join(multi_capture_texts)' in line:
         out.append(line.replace('combined_text = "\n\n".join(multi_capture_texts)', 'combined_text = "\\n\\n".join(multi_capture_texts)'))
         i += 1
    elif 'combined_text = "' in line and 'join' not in line: # Another possible break
        if lines[i+1] == '\n' and '".join(multi_capture_texts)' in lines[i+2]:
            out.append('            combined_text = "\\n\\n".join(multi_capture_texts)\n')
            i += 3
        else:
            out.append(line)
            i += 1
    else:
        out.append(line)
        i += 1

with open('main.py', 'w') as f:
    f.writelines(out)
