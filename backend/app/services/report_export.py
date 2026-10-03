"""Dependency-free, escaped, printable research reports. No network or scripts."""
import html
import json
import re


def escaped(value):
    return html.escape(str(value if value is not None else '未記錄'))


def markdown_text(value):
    """Small safe Markdown subset. Unsupported markup stays visible as text."""
    lines = str(value or '').splitlines()
    parts, index, in_code = [], 0, False
    while index < len(lines):
        line = lines[index]
        if line.startswith('```'):
            parts.append('</code></pre>' if in_code else '<pre><code>')
            in_code = not in_code
        elif in_code:
            parts.append(escaped(line) + '\n')
        elif (index + 1 < len(lines) and '|' in line and
              re.fullmatch(r'[\s|:\-]+', lines[index + 1]) and '-' in lines[index + 1]):
            cells = lambda text: text.strip().strip('|').split('|')
            parts.append('<table><thead><tr>' + ''.join('<th>' + escaped(cell.strip()) + '</th>' for cell in cells(line)) + '</tr></thead><tbody>')
            index += 2
            while index < len(lines) and '|' in lines[index] and lines[index].strip():
                parts.append('<tr>' + ''.join('<td>' + escaped(cell.strip()) + '</td>' for cell in cells(lines[index])) + '</tr>')
                index += 1
            parts.append('</tbody></table>')
            continue
        elif match := re.match(r'^(#{1,6})\s+(.*)', line):
            level = min(6, len(match[1]) + 1)
            parts.append(f'<h{level}>' + escaped(match[2]) + f'</h{level}>')
        elif line.strip():
            parts.append('<p>' + escaped(line) + '</p>')
        index += 1
    if in_code:
        parts.append('</code></pre>')
    return ''.join(parts)


def table(headers, rows):
    return '<table><thead><tr>' + ''.join('<th>'+escaped(value)+'</th>' for value in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+escaped(value)+'</td>' for value in row)+'</tr>' for row in rows) + '</tbody></table>'


def quality_chart(quality):
    """An accessible rendering of recorded counts, not an invented score."""
    rows = []
    for index, (key, label) in enumerate([('source_preservation', '來源保存'), ('citation_location', '引用定位')]):
        metric = quality[key]
        numerator, denominator = metric['numerator'], metric['denominator']
        y = index * 58 + 28
        description = f'{label}：{numerator}／{denominator}' if denominator else f'{label}：尚無可評估資料'
        width = 280 * max(0, min(1, numerator / denominator)) if denominator else 0
        rows.append(f'<text x="0" y="{y}" fill="#282b25">{escaped(description)}</text>'
                    f'<rect x="250" y="{y-17}" width="280" height="22" rx="3" fill="#d0c9ba"/>'
                    f'<rect x="250" y="{y-17}" width="{width:.2f}" height="22" rx="3" fill="#805014"/>')
    return ('<figure class="quality-chart"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 110" role="img" aria-label="來源保存與引用定位，計算定義見下表">'
            + ''.join(rows) + '</svg><figcaption>顯示保存與定位比例；不代表預測準確度或語意支持。</figcaption></figure>')


def render_html(data):
    project = data['project']
    label = '合成示範 · 非模型執行結果' if project.get('demo') else '探索性研究 · 非未來預測'
    body = ['<header><p class="eyebrow">MIROFISH · 研究紀錄</p><h1>'+escaped(project['name'])+'</h1><p class="status">'+label+'</p></header>',
            '<h2>研究問題</h2><p>'+escaped(project.get('simulation_requirement'))+'</p>',
            '<h2>保存的報告</h2>']
    for report in data['reports']:
        body += ['<article><h3>'+escaped((report.get('outline') or {}).get('title') or report['report_id'])+'</h3>',
                 '<p class="meta">版本 '+escaped(report.get('version', 1))+' · '+escaped(report['status'])+' · '+escaped(report.get('completed_at'))+'</p>',
                 markdown_text(report.get('markdown_content'))]
        if not report.get('markdown_content') or report['status'] != 'completed':
            for section in (report.get('outline') or {}).get('sections', []):
                body += ['<h4>'+escaped(section.get('title'))+'</h4>', markdown_text(section.get('content'))]
        body.append('</article>')
    body += ['<h2>來源版本與證據</h2><p>以下列出已保存版本與引句。版本定位相符，不代表語意支持或現實真確性已驗證。</p>']
    rows = []
    for entry in data['evidence_index']:
        for version in entry['versions']:
            rows.append((entry['source']['title'], version['version_id'], version.get('fetched_at') or version.get('created_at'), version['status'], version.get('sha256')))
    body.append(table(['來源', '版本', '保存／擷取時間', '狀態', '內容指紋'], rows))
    spans = {span['span_id']: span for entry in data['evidence_index'] for version in entry['versions'] for span in version.get('spans', [])}
    for ref in data['references']['items']:
        body += ['<section class="reference" id="'+escaped(ref['reference_id'])+'"><h3>'+escaped(ref['subject_type'])+' · '+escaped(ref['subject_id'])+'</h3>',
                 '<p>'+escaped(ref['category'])+' · '+escaped(ref['relation'])+' · 定位：'+escaped(ref.get('validation', {}).get('location_status'))+'</p>',
                 '<p>'+escaped(ref.get('note') or '')+'</p>']
        span = spans.get(ref.get('span_id'))
        if span:
            body += ['<blockquote>'+escaped(span['quote'])+'</blockquote>', '<p class="meta">'+escaped(ref.get('version_id'))+' · 字元 '+escaped(span['start'])+'–'+escaped(span['end'])+'</p>']
        else:
            body.append('<p class="meta">未保存原文定位；假設與模型推論不當作來源引句。</p>')
        body.append('</section>')
    body += ['<h2>執行配置</h2><p>每筆執行保存獨立配置。未知費用或實際路由結果不以零代替。</p>']
    for run in data['runs']:
        body += ['<section><h3>'+escaped(run['simulation_id'])+'</h3>',
                 table(['狀態', '執行身分', '圖譜收尾'], [(run['status'], run.get('run_id'), run.get('graph_ready'))]),
                 '<details open><summary>保存的完整配置</summary><pre>'+escaped(json.dumps(run.get('manifest', {}), ensure_ascii=False, indent=2))+'</pre></details></section>']
    quality = data['quality']
    body += ['<h2>品質檢查與限制</h2>', quality_chart(quality), table(['檢查', '分子', '分母', '定義'], [(name, quality[key]['numerator'], quality[key]['denominator'], quality[key]['definition']) for key, name in [('source_preservation', '來源保存'), ('citation_location', '引用定位')]])]
    body += ['<p>'+escaped(value)+'</p>' for value in data['limitations']]
    body.append('<footer>計算版本：'+escaped(quality['calculation_version'])+' · 匯出版本：'+escaped(data['export_version'])+' · 列印此頁可保存為 PDF。匯出不會重新生成內容。</footer>')
    css = '''body{font:16px/1.7 "Segoe UI","Microsoft JhengHei","PingFang TC",sans-serif;color:#282b25;background:#ded8cb;max-width:960px;margin:32px auto;padding:32px}
    h1{font-size:2rem;line-height:1.25}h1,h2,h3,h4{break-after:avoid}h2{border-bottom:2px solid #805014;margin-top:2em;padding-bottom:.3em}
    p,td,th,pre,blockquote{overflow-wrap:anywhere}p{white-space:pre-wrap}pre{white-space:pre-wrap;font:12px/1.55 Consolas,monospace;background:#e8e2d6;padding:16px}
    table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px;margin-block:16px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #898b7f;padding:8px}thead{display:table-header-group}tr{break-inside:avoid}
    .eyebrow,.meta,footer{color:#515548;font-size:13px}.status{border-left:4px solid #805014;padding-left:12px}blockquote{border-left:3px solid #805014;margin:1em 0;padding-left:16px}.reference{border-bottom:1px solid #b4b1a3;padding-block:8px}footer{margin-top:3em}
    .quality-chart{margin:20px 0;break-inside:avoid}.quality-chart svg{width:100%;max-width:640px;display:block}.quality-chart figcaption{font-size:13px;color:#515548}
    @media print{body{background:white;margin:0;padding:0;font-size:11pt;max-width:none}pre{font-size:9pt;background:none}table{font-size:9pt}p{orphans:3;widows:3}h2{margin-top:1.2em}@page{size:A4;margin:17mm}}'''
    return '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+escaped(project['name'])+'</title><style>'+css+'</style></head><body>'+''.join(body)+'</body></html>'
