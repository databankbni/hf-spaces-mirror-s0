import codecs
with codecs.open('app.py', 'r', 'utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_line = line.replace('─', '-').replace('→', '->').replace('📊', '[Chart]')
    # strip any other non-ascii safely
    new_line = ''.join(c if ord(c) < 128 else '' for c in new_line)
    new_lines.append(new_line)

with codecs.open('app.py', 'w', 'utf-8') as f:
    f.writelines(new_lines)
