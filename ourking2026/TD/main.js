const express = require('express');
const cors = require('cors');
const app = express();

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

const worker = require('./worker');

// 原有业务接口全部保留
app.get('/do', (req, res) => worker.getCaptcha().then(d => res.json(d)));
app.get('/md5-list', (req, res) => worker.handleMd5List().then(d => res.json(d)));
app.get('/get', (req, res) => worker.handleGetAndTrigger(req.query).then(d => res.json(d)));
app.post('/save', (req, res) => worker.handleSave(req.body).then(d => res.json(d)));
app.get('/js', (req, res) => worker.handleGetCachedScript(req.query).then(d => {
  if (typeof d === 'string') {
    res.set('Content-Type', 'application/javascript').send(d);
  } else {
    res.json(d);
  }
}));
app.get('/cl5', (req, res) => worker.handleClear(req.query).then(d => res.json(d)));
app.get('/clear', (req, res) => worker.handleClearAll().then(d => res.json(d)));
app.get('/debug', (req, res) => worker.handleDebug().then(d => res.json(d)));
app.get('/log', (req, res) => worker.handleLog().then(d => res.json(d)));

// 首页路由：HTML完整放进反引号字符串
app.get('/76460805', (req, res) => {
  const html = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TDC 一体化服务 控制台</title>
<style>
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
        font-family: "Microsoft YaHei", system-ui, sans-serif;
    }
    body {
        background-color: #1a1d24;
        color: #eee;
        padding: 24px 16px;
        font-size: 18px;
        line-height: 1.6;
    }
    .container {
        max-width: 1000px;
        margin: 0 auto;
    }
    h1 {
        color: #4cd964;
        margin-bottom: 12px;
        font-size: 30px;
    }
    .desc {
        color: #aaa;
        margin-bottom: 36px;
        padding-bottom: 20px;
        border-bottom: 1px solid #333;
        font-size: 17px;
    }
    .api-card {
        background: #272c36;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .api-header {
        display: flex;
        align-items: center;
        gap:10px;
        margin-bottom:16px;
    }
    .api-path {
        font-size: 20px;
        font-weight: bold;
        color: #5ac8fa;
    }
    .method-tag {
        font-size: 15px;
        padding: 3px 8px;
        border-radius: 4px;
        background: #007aff;
    }
    .post-tag {
        background: #5856d6;
    }
    .api-desc {
        color: #ffcc00;
        font-size: 17px;
        margin-bottom:18px;
    }
    .form-row {
        margin-bottom:16px;
    }
    label {
        display:block;
        margin-bottom:8px;
        font-size:17px;
        color:#ddd;
    }
    input {
        width:100%;
        padding:12px 14px;
        background:#1f232b;
        border:1px solid #444;
        color:#fff;
        border-radius:8px;
        font-size:18px;
    }
    input::placeholder {
        color:#777;
    }
    .btn {
        padding:12px 22px;
        border:none;
        border-radius:8px;
        font-size:17px;
        cursor:pointer;
    }
    .btn-get {
        background:#007aff;
        color:#fff;
    }
    .btn-post {
        background:#5856d6;
        color:#fff;
    }
    .btn-danger {
        background:#ff3b30;
        color:#fff;
    }
    .btn-copy {
        background-color: #28a745;
        color: #fff;
        padding: 4px 10px;
        font-size:14px;
        border-radius:4px;
        border: none;
        cursor: pointer;
    }
    .btn-copy:active {
        opacity: 0.8;
    }
    .tip {
        margin-top:40px;
        font-size:15px;
        color:#999;
        line-height:1.8;
    }

    /* 弹窗样式 */
    .modal-mask {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.75);
        display: none;
        z-index: 9999;
        align-items: center;
        justify-content: center;
        padding:20px;
    }
    .modal-box {
        width: 100%;
        max-width: 800px;
        max-height: 80vh;
        background: #222730;
        border-radius: 12px;
        display: flex;
        flex-direction: column;
    }
    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding:16px 20px;
        border-bottom: 1px solid #333;
        gap:12px;
    }
    .modal-title {
        font-size: 20px;
        color:#5ac8fa;
        font-weight:bold;
        flex:1;
    }
    .modal-close {
        font-size:24px;
        color:#aaa;
        cursor:pointer;
        padding:4px 8px;
    }
    .modal-body {
        padding:20px;
        overflow-y: auto;
        flex: 1;
    }
    .modal-content {
        white-space: pre-wrap;
        word-break: break-all;
        color:#9feaff;
        font-family: Consolas, monospace;
        font-size:16px;
    }

    /* 复制成功轻提示 */
    .toast {
        position: fixed;
        bottom: 40px;
        left: 50%;
        transform: translateX(-50%);
        background: #28a745;
        color: #fff;
        padding: 10px 20px;
        border-radius: 6px;
        z-index: 10000;
        display: none;
    }
</style>
</head>
<body>
<div class="container">
    <h1>✅ TDC 一体化服务运行正常</h1>
    <div class="desc">填写参数，点击执行按钮，弹窗展示接口返回结果，页面无冗余结果区域</div>

    <!-- 1. md5-list -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/md5-list</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">无参数，查询全部MD5列表</div>
        <button class="btn btn-get" onclick="fetchApi('GET','/md5-list',{},'/md5-list 接口返回')">执行请求</button>
    </div>

    <!-- 2. /do -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/do</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">无参数，执行核心业务任务</div>
        <button class="btn btn-get" onclick="fetchApi('GET','/do',{},'/do 接口返回')">执行请求</button>
    </div>

    <!-- 3. /get -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/get</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">必填参数：md5，根据MD5查询数据</div>
        <div class="form-row">
            <label>md5 参数</label>
            <input id="param-get-md5" placeholder="请输入32位MD5字符串，例如：868f3a65c6a237f5ed692cd91748cea5" value="">
        </div>
        <button class="btn btn-get" onclick="fetchApi('GET','/get',{md5:document.getElementById('param-get-md5').value},'/get 接口返回')">执行查询</button>
    </div>

    <!-- 4. /save POST -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/save</div>
            <span class="method-tag post-tag">POST</span>
        </div>
        <div class="api-desc">md5、collect、eks 三个参数，写入存储数据</div>
        <div class="form-row">
            <label>md5</label>
            <input id="param-save-md5" placeholder="填写MD5值" value="">
        </div>
        <div class="form-row">
            <label>collect</label>
            <input id="param-save-collect" placeholder="填写采集内容" value="">
        </div>
        <div class="form-row">
            <label>eks</label>
            <input id="param-save-eks" placeholder="填写eks参数值" value="">
        </div>
        <button class="btn btn-post" onclick="postSave()">提交POST写入</button>
    </div>

    <!-- 5. /js -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/js</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">必填参数：md5，读取缓存JS脚本</div>
        <div class="form-row">
            <label>md5 参数</label>
            <input id="param-js-md5" placeholder="输入MD5" value="">
        </div>
        <button class="btn btn-get" onclick="fetchApi('GET','/js',{md5:document.getElementById('param-js-md5').value},'/js 接口返回')">获取脚本</button>
    </div>

    <!-- 6. /cl5 -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/cl5</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">必填参数：md5，单条数据清理/校验</div>
        <div class="form-row">
            <label>md5 参数</label>
            <input id="param-cl5-md5" placeholder="输入需要清理的MD5" value="">
        </div>
        <button class="btn btn-get" onclick="fetchApi('GET','/cl5',{md5:document.getElementById('param-cl5-md5').value},'/cl5 接口返回')">执行处理</button>
    </div>

    <!-- 7. /clear 高危清空 -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/clear</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">高危操作：全局清空全部数据，操作不可逆！</div>
        <button class="btn btn-danger" onclick="clearAllData()">确认清空全部数据</button>
    </div>

    <!-- 8. /debug -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/debug</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">无参数，查看服务调试运行详情</div>
        <button class="btn btn-get" onclick="fetchApi('GET','/debug',{},'/debug 接口返回')">查看调试信息</button>
    </div>

    <!-- 9. /log -->
    <div class="api-card">
        <div class="api-header">
            <div class="api-path">/log</div>
            <span class="method-tag">GET</span>
        </div>
        <div class="api-desc">无参数，读取系统完整运行日志</div>
        <button class="btn btn-get" onclick="fetchApi('GET','/log',{},'/log 接口返回')">读取日志</button>
    </div>

    <div class="tip">
        执行请求后，结果弹窗弹出，可一键复制全部返回内容，查看完毕可点击右上角关闭按钮关闭弹窗。
    </div>
</div>

<!-- 全局弹窗DOM -->
<div class="modal-mask" id="resultModal">
    <div class="modal-box">
        <div class="modal-header">
            <div class="modal-title" id="modalTitle">接口返回结果</div>
            <button class="btn-copy" onclick="copyModalContent()">📋 复制结果</button>
            <div class="modal-close" onclick="closeModal()">×</div>
        </div>
        <div class="modal-body">
            <div class="modal-content" id="modalContent"></div>
        </div>
    </div>
</div>

<!-- 复制成功提示 -->
<div class="toast" id="copyToast">✅ 复制成功，已存入剪贴板</div>

<script>
// 全局缓存弹窗文本，用于复制
let currentModalText = '';

// 打开弹窗
function openModal(title, text) {
    currentModalText = text;
    document.getElementById('modalTitle').innerText = title;
    document.getElementById('modalContent').innerText = text;
    document.getElementById('resultModal').style.display = 'flex';
}
// 关闭弹窗
function closeModal() {
    document.getElementById('resultModal').style.display = 'none';
}
// 点击遮罩层关闭弹窗
document.getElementById('resultModal').addEventListener('click', function(e){
    if(e.target === this) closeModal();
})

// 复制弹窗全部内容（兼容现代浏览器+老旧浏览器降级）
async function copyModalContent() {
    if (!currentModalText) {
        alert('暂无可复制内容！');
        return;
    }
    try {
        // 现代浏览器标准API
        await navigator.clipboard.writeText(currentModalText);
        showToast();
    } catch (err) {
        // 降级兼容方案
        const textarea = document.createElement('textarea');
        textarea.value = currentModalText;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast();
    }
}

// 显示复制成功轻提示，2秒自动消失
function showToast() {
    const toast = document.getElementById('copyToast');
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 2000);
}

// 通用GET请求封装，结果弹窗展示
function fetchApi(method, url, params, title) {
    openModal(title, '请求加载中，请稍候...');
    const query = new URLSearchParams(params).toString();
    const reqUrl = query ? url + '?' + query : url;

    fetch(reqUrl, {method: method})
    .then(resp => {
        if(url === '/js') return resp.text();
        return resp.json();
    })
    .then(data => {
        let showText;
        if(typeof data === 'string'){
            showText = data;
        }else{
            showText = JSON.stringify(data, null, 2);
        }
        openModal(title, showText);
    })
    .catch(err => {
        openModal(title, '请求异常：' + err.message);
    })
}

// POST /save 专用函数
function postSave() {
    const md5 = document.getElementById('param-save-md5').value;
    const collect = document.getElementById('param-save-collect').value;
    const eks = document.getElementById('param-save-eks').value;
    openModal('/save POST 提交结果', 'POST请求提交中...');

    fetch('/save', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({md5, collect, eks})
    })
    .then(resp => resp.json())
    .then(data => {
        openModal('/save POST 提交结果', JSON.stringify(data, null, 2));
    })
    .catch(err => {
        openModal('/save POST 提交结果', '请求异常：' + err.message);
    })
}

// /clear 二次确认弹窗
function clearAllData() {
    if(!confirm('⚠️ 警告：清空所有数据不可恢复，确定执行吗？')) return;
    fetchApi('GET','/clear',{},'/clear 全局清空结果');
}
</script>
</body>
</html>
  `;
  res.send(html);
});

app.listen(7860, '0.0.0.0', () => {
  console.log('✅ 服务运行在 7860');
});

// 启动 bot
require('./tdc-bot.js');