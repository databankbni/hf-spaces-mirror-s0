const express = require('express');
const cors = require('cors');
const worker = require('./worker');
const app = express();

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get('/do', async (req, res) => res.json(await worker.getCaptcha()));
app.get('/md5-list', async (req, res) => res.json(await worker.handleMd5List()));
app.get('/get', async (req, res) => res.json(await worker.handleGetAndTrigger(req.query)));
app.post('/save', async (req, res) => res.json(await worker.handleSave(req.query)));

app.get('/js', async (req, res) => {
  const result = await worker.handleGetCachedScript(req.query);
  if (typeof result === 'object' && result.error) {
    res.json(result);
  } else {
    res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
    res.send(result);
  }
});

app.get('/cl5', async (req, res) => res.json(await worker.handleClear(req.query)));
app.get('/clear', async (req, res) => res.json(await worker.handleClearAll()));
app.get('/reset-signal', async (req, res) => res.json(await worker.handleResetSignal()));
app.get('/debug', async (req, res) => res.json(await worker.handleDebug()));

// 新增日志接口
app.get('/log', async (req, res) => res.json(await worker.handleLog()));

app.listen(3000, '0.0.0.0', () => {
  console.log('项目已运行在本地端口3000');
});
