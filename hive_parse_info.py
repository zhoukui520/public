from flask import Flask, render_template_string, request
import re
from flask import Response
import csv
import io
import socket
import os

app = Flask(__name__)

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Hive建表SQL字段解析</title>
    <style>
        textarea { width: 100%; height: 200px; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px;}
        th, td { border: 1px solid #ccc; padding: 8px; text-align: left;}
        th { background: #f2f2f2;}
        .btn, .download-btn {
            padding: 8px 16px;
            margin-top: 10px;
            background: #4CAF50;
            color: #fff;
            border: none;
            cursor: pointer;
            border-radius: 4px;
            transition: all 0.2s;
        }
        .btn:active, .download-btn:active {
            transform: scale(1.15);
            background: #388e3c;
        }
        .download-btn {
            margin-left: 16px;
            background: #2196F3;
        }
        .download-btn:active {
            background: #1565c0;
        }
    </style>
</head>
<body>
    <h2>Hive建表SQL字段解析工具</h2>
    <form method="post" id="sql-form">
        <textarea name="sql" placeholder="请粘贴Hive建表SQL...">{{ sql or '' }}</textarea><br>
        <button class="btn" id="parse-btn" type="submit">解析</button>
    </form>
    <form method="post" action="/download" id="download-form" style="display:inline;">
        <input type="hidden" name="sql" id="download-sql" value="{{ sql|e }}">
        <button class="download-btn" id="download-btn" type="submit">下载CSV</button>
    </form>
    {% if fields %}
    <table id="result-table">
        <tr>
            <th>字段名</th>
            <th>字段类型</th>
            <th>字段注释</th>
        </tr>
        {% for f in fields %}
        <tr>
            <td>{{ f['字段名'] }}</td>
            <td>{{ f['字段类型'] }}</td>
            <td>{{ f['字段注释'] }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}
    <script>
    // 按钮动态变大
    function addDynamicButtonEffect(id) {
        var btn = document.getElementById(id);
        if (!btn) return;
        btn.addEventListener('mousedown', function() {
            btn.style.transform = 'scale(1.15)';
        });
        btn.addEventListener('mouseup', function() {
            btn.style.transform = '';
        });
        btn.addEventListener('mouseleave', function() {
            btn.style.transform = '';
        });
    }
    addDynamicButtonEffect('parse-btn');
    addDynamicButtonEffect('download-btn');

    function getTableText(tabSep) {
        var table = document.getElementById('result-table');
        if (!table) return '';
        var rows = table.rows;
        var text = '';
        for (var i = 0; i < rows.length; i++) {
            var cells = rows[i].cells;
            var rowText = [];
            for (var j = 0; j < cells.length; j++) {
                rowText.push((cells[j].innerText || cells[j].textContent || '').replace(/\n/g, ' '));
            }
            text += rowText.join(tabSep) + '\n';
        }
        return text;
    }

    function downloadTable() {
        var text = getTableText(','); // 逗号分隔，csv格式
        if (!text) {
            alert('没有可下载的表格内容！');
            return;
        }
        var blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        link.style.display = 'none';
        link.href = URL.createObjectURL(blob);
        link.download = 'table.csv';
        document.body.appendChild(link);
        link.click();
        setTimeout(function() {
            document.body.removeChild(link);
            window.URL.revokeObjectURL(link.href);
        }, 100);
    }

    // 在下载前把 textarea 的 SQL 同步到隐藏字段
    var downloadForm = document.getElementById('download-form');
    if (downloadForm) {
        downloadForm.addEventListener('submit', function(e){
            var ta = document.querySelector('textarea[name="sql"]');
            var hidden = document.getElementById('download-sql');
            if (ta && hidden) {
                hidden.value = ta.value;
            }
        });
    }
    </script>
</body>
</html>
'''

def parse_hive_create_table(sql):
    # 提取字段定义部分（不要把字段级 COMMENT 当作结束标志）
    # 这里不使用基于尾部关键字的正则，因为注释里可能包含分号或这些关键词。
    # 改为从第一个 '(' 开始做手动配对，忽略引号内的括号和分号，直到匹配到顶层的 ')'
    start = sql.find('(')
    if start == -1:
        return []
    i = start + 1
    in_single = False
    in_double = False
    depth = 1
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            # 处理单引号内的转义''
            if in_single:
                if i + 1 < len(sql) and sql[i+1] == "'":
                    i += 1
                else:
                    in_single = False
            else:
                in_single = True
        elif ch == '"' and not in_single:
            if in_double:
                if i + 1 < len(sql) and sql[i+1] == '"':
                    i += 1
                else:
                    in_double = False
            else:
                in_double = True
        elif not in_single and not in_double:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
        i += 1
    if depth != 0:
        return []
    fields_str = sql[start+1:i]
    # 将字段列表按顶层逗号拆分（忽略引号内的逗号与嵌套小括号），以支持 COMMENT 中包含逗号或换行的情况
    def split_top_level(s):
        parts = []
        cur = []
        in_single = False
        in_double = False
        paren = 0
        i = 0
        while i < len(s):
            ch = s[i]
            cur.append(ch)
            if ch == "'" and not in_double:
                if in_single:
                    # SQL 中单引号内用两个单引号表示一个单引号
                    if i + 1 < len(s) and s[i+1] == "'":
                        cur.append(s[i+1]); i += 1
                    else:
                        in_single = False
                else:
                    in_single = True
            elif ch == '"' and not in_single:
                if in_double:
                    if i + 1 < len(s) and s[i+1] == '"':
                        cur.append(s[i+1]); i += 1
                    else:
                        in_double = False
                else:
                    in_double = True
            elif ch == '(' and not in_single and not in_double:
                paren += 1
            elif ch == ')' and not in_single and not in_double:
                if paren > 0:
                    paren -= 1
            elif ch == ',' and not in_single and not in_double and paren == 0:
                part = ''.join(cur[:-1]).strip()
                if part:
                    parts.append(part)
                cur = []
            i += 1
        last = ''.join(cur).strip()
        if last:
            parts.append(last)
        return parts

    field_lines = [ln for ln in split_top_level(fields_str) if ln]

    # 提取字段名、字段类型以及 COMMENT 引号内的完整内容（支持用两个引号转义的场景）
    def extract_comment_and_dtype(part):
        in_single = False
        in_double = False
        i = 0
        while i < len(part):
            ch = part[i]
            if ch == "'" and not in_double:
                if in_single:
                    if i + 1 < len(part) and part[i+1] == "'":
                        i += 1
                    else:
                        in_single = False
                else:
                    in_single = True
            elif ch == '"' and not in_single:
                if in_double:
                    if i + 1 < len(part) and part[i+1] == '"':
                        i += 1
                    else:
                        in_double = False
                else:
                    in_double = True

            if not in_single and not in_double:
                # 找到 COMMENT 关键字（单词边界）
                if part[i:i+7].upper() == 'COMMENT' and (i == 0 or not part[i-1].isalpha()):
                    j = i + 7
                    while j < len(part) and part[j].isspace():
                        j += 1
                    if j < len(part) and part[j] in ("'", '"'):
                        q = part[j]
                        k = j + 1
                        val_chars = []
                        while k < len(part):
                            if part[k] == q:
                                # 双引号或单引号转义（'' 或 ""）
                                if k + 1 < len(part) and part[k+1] == q:
                                    val_chars.append(q)
                                    k += 2
                                    continue
                                else:
                                    break
                            else:
                                val_chars.append(part[k])
                                k += 1
                        comment = ''.join(val_chars)
                        dtype = part[:i].strip()
                        return comment, dtype
                    else:
                        # COMMENT 后没有引号，取到行尾作为注释
                        comment = part[j:].strip()
                        dtype = part[:i].strip()
                        return comment, dtype
            i += 1
        return '', part.strip()

    fields = []
    name_pattern = re.compile(r'^`?(\w+)`?\s*', re.IGNORECASE)
    for line in field_lines:
        text = line.rstrip(',').strip()
        if not text:
            continue
        # 提取字段名
        nm = name_pattern.match(text)
        if not nm:
            continue
        name = nm.group(1)
        rest = text[nm.end():].strip()
        comment, dtype = extract_comment_and_dtype(rest)
        fields.append({
            '字段名': name,
            '字段类型': dtype,
            '字段注释': comment if comment else ''
        })
    return fields

@app.route('/', methods=['GET', 'POST'])
def index():
    sql = ''
    fields = []
    if request.method == 'POST':
        sql = request.form.get('sql', '')
        fields = parse_hive_create_table(sql)
    return render_template_string(HTML, sql=sql, fields=fields)


@app.route('/download', methods=['POST'])
def download():
    sql = request.form.get('sql', '')
    fields = parse_hive_create_table(sql)
    if not fields:
        return '没有可导出的字段', 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['字段名', '字段类型', '字段注释'])
    for f in fields:
        writer.writerow([f['字段名'], f['字段类型'], f['字段注释']])
    csv_data = output.getvalue()
    output.close()

    resp = Response(csv_data, mimetype='text/csv')
    resp.headers.set('Content-Disposition', 'attachment', filename='fields.csv')
    return resp

if __name__ == '__main__':
    def find_free_port(range_start=5000, range_end=5100):
        # Try to use PORT env first
        env_port = os.environ.get('PORT')
        if env_port:
            try:
                p = int(env_port)
                return p
            except Exception:
                pass
        for p in range(range_start, range_end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('127.0.0.1', p))
                    return p
                except OSError:
                    continue
        raise RuntimeError('no free port in range')

    port = find_free_port()
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('DEBUG', 'True').lower() in ('1', 'true', 'yes')
    app.run(debug=debug, host=host, port=port)
