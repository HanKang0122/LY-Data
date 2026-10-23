#!/usr/bin/env python3
"""Ensure commission plan v4 is integrated into index.html."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOADED = os.path.join(ROOT, '.github', 'assets', 'comm-plan-v4-source.html')
TARGET = os.path.join(ROOT, 'index.html')

NAMES = ['ink','ink2','muted','muted2','rule','rule2','bg','bg2','purple','purple-l','blue','blue-l','green','green-l','orange','orange-l','red','red-l','shadow','shadow-md','shadow-lg','radius','radius-sm']

def scope_css(css, scope):
    for name in NAMES:
        css = css.replace('--' + name + ':', '--v4-' + name + ':')
        css = css.replace('var(--' + name + ')', 'var(--v4-' + name + ')')
    result = []
    in_media = False
    in_keyframes = False
    for line in css.split('\n'):
        stripped = line.strip()
        if stripped.startswith('@media'):
            in_media = True
        elif stripped.startswith('@keyframes'):
            in_keyframes = True
        elif stripped == '}':
            if in_media:
                in_media = False
            elif in_keyframes:
                in_keyframes = False
        elif not in_keyframes and stripped and '{' in stripped and stripped[0] not in ['@', '{', '}']:
            line = scope_selector_line(line, scope)
        result.append(line)
    return '\n'.join(result)

def scope_selector_line(line, scope):
    if '{' not in line:
        return line
    sel_part, rest = line.split('{', 1)
    selectors = [s.strip() for s in sel_part.split(',') if s.strip()]
    new_selectors = []
    for sel in selectors:
        if sel in ('html', 'body', ':root'):
            new_selectors.append(scope)
        elif sel == '*':
            new_selectors.append(scope + ' *')
        else:
            new_selectors.append(scope + ' ' + sel)
    return ', '.join(new_selectors) + ' {' + rest

def main():
    if not os.path.exists(TARGET):
        print(f'[ERROR] Target not found: {TARGET}')
        return 1

    with open(TARGET, 'r', encoding='utf-8') as f:
        target = f.read()

    # Quick check: already integrated?
    if 'commPlanV4HTML' in target and '<option value="v4">' in target:
        print('[OK] v4 commission plan already integrated')
        return 0

    print('[INFO] v4 not found, integrating...')

    if not os.path.exists(UPLOADED):
        print(f'[ERROR] Source file not found: {UPLOADED}')
        return 1

    with open(UPLOADED, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # CSS lines 8-362 (1-based)
    css_content = ''.join(lines[7:362])
    css_content = re.sub(r'^\s*<style>\s*', '', css_content)
    css_content = re.sub(r'\s*</style>\s*$', '', css_content)
    scoped_css = scope_css(css_content, '.comm-plan-v4')

    # Body lines 421-691 (1-based)
    body_html = ''.join(lines[420:691])
    body_html = re.sub(r'\s*contenteditable="[^"]*"', '', body_html)
    body_html = re.sub(r'\s*contenteditable', '', body_html)
    body_html = '<div class="comm-plan-v4">\n' + body_html + '\n</div>'

    for name in sorted(NAMES, key=len, reverse=True):
        body_html = re.sub(r'var\(--' + re.escape(name) + r'\b', 'var(--v4-' + name, body_html)

    escaped = body_html.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r')
    v4_function = (
        "// 第四版商务提成方案 · 打品期 + 单品阶梯加成\n"
        "function commPlanV4HTML() {\n"
        "  return '" + escaped + "';\n"
        "}\n\n"
    )

    # Remove old v4 CSS markers
    v4_start_marker = '/* ===== V4 Commission Plan Styles ===== */'
    v4_end_marker = '/* ===== End V4 Commission Plan Styles ===== */'
    s = target.find(v4_start_marker)
    e = target.find(v4_end_marker)
    if s != -1 and e != -1:
        target = target[:s] + target[e + len(v4_end_marker):]

    # Insert CSS
    style_close = target.rfind('</style>')
    if style_close == -1:
        print('[ERROR] No </style> found')
        return 1
    v4_css_block = '\n' + v4_start_marker + '\n' + scoped_css + '\n' + v4_end_marker + '\n'
    target = target[:style_close] + v4_css_block + target[style_close:]

    # Remove old v4 functions
    v4_func_start = target.find('function commPlanV4HTML() {')
    while v4_func_start != -1:
        brace_count = 1
        i = v4_func_start + len('function commPlanV4HTML() {')
        while i < len(target) and brace_count > 0:
            if target[i] == '{':
                brace_count += 1
            elif target[i] == '}':
                brace_count -= 1
            i += 1
        target = target[:v4_func_start] + target[i:]
        v4_func_start = target.find('function commPlanV4HTML() {')

    # Insert v4 function before v3
    v3_pos = target.find('function commPlanV3HTML() {')
    if v3_pos == -1:
        print('[ERROR] commPlanV3HTML not found')
        return 1
    # Clean stray comments
    prefix = target[:v3_pos]
    prefix = re.sub(r'\n// 第三版商务提成方案[^\n]*\n*$', '\n', prefix)
    prefix = re.sub(r'\n// 第四版商务提成方案[^\n]*\n*$', '\n', prefix)
    target = prefix + target[v3_pos:]
    v3_pos = target.find('function commPlanV3HTML() {')
    target = target[:v3_pos] + v4_function + target[v3_pos:]

    # Update selector
    sel_start = target.find('<select id="biz-commission-version-filter" onchange="renderBizCommissionPlan()">')
    sel_end = target.find('</select>', sel_start)
    if sel_start == -1 or sel_end == -1:
        print('[ERROR] Version selector not found')
        return 1
    selector_block = target[sel_start:sel_end + 9]
    selector_block = re.sub(r'\s*<option value="v4">.*?</option>', '', selector_block)
    if '<option value="v4">' not in selector_block:
        selector_block = selector_block.replace(
            '<select id="biz-commission-version-filter" onchange="renderBizCommissionPlan()">',
            '<select id="biz-commission-version-filter" onchange="renderBizCommissionPlan()">\n                  <option value="v4">第四版 · 打品期+单品阶梯加成（2026年11月起）</option>'
        )
    target = target[:sel_start] + selector_block + target[sel_end + 9:]

    # Update render function
    target = re.sub(r"\s*if \(version === 'v4'\) html = commPlanV4HTML\(\);\s*", '\n  ', target)
    v3_pattern = r"if \(version === 'v3'\) html = commPlanV3HTML\(\);"
    if re.search(v3_pattern, target):
        target = re.sub(v3_pattern, "if (version === 'v4') html = commPlanV4HTML();\n  else if (version === 'v3') html = commPlanV3HTML();", target, count=1)

    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(target)

    print('[OK] v4 integrated into index.html')
    return 0

if __name__ == '__main__':
    sys.exit(main())
