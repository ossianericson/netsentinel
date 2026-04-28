with open('modules/metric_store.py', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(1139, len(lines)):
    if lines[i].count('"""') % 2 == 1:
        print(str(i+1) + ': ' + lines[i][:80])
