from flask import Flask, render_template_string, request
import re
from flask import Response
import csv
import io

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
    fields_part = re.search(r'\(([\s\S]*?)\)\s*(PARTITIONED|ROW|STORED|LOCATION|TBLPROPERTIES|;)', sql, re.IGNORECASE)
    if not fields_part:
        return []
    fields_str = fields_part.group(1)
    # 按行读取字段定义，跳过以 -- 注释的行（前面允许空白）
    field_lines = [line.strip() for line in fields_str.split('\n') if line.strip() and not re.match(r'^\s*--', line)]
    # 字段类型为字段名和 COMMENT 之间的所有内容
    field_pattern = re.compile(r'^`?(\w+)`?\s+(.+?)(?:\s+COMMENT\s+[\'\"]([^\'\"]*)[\'\"])?$', re.IGNORECASE)
    fields = []
    for line in field_lines:
        match = field_pattern.match(line.rstrip(','))
        if match:
            name, dtype, comment = match.groups()
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
    app.run(debug=True)
