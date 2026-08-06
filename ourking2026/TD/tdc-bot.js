const puppeteer = require('puppeteer');
const fs = require('fs').promises;
const path = require('path');

const SHARED_DIR = '/datasets/txc1/tdc-shared-data';

const SCRIPT_DIR = path.join(SHARED_DIR, 'scripts');
const TASK_LIST_FILE = path.join(SHARED_DIR, 'tasks.json');
const SIGNAL_FILE = path.join(SHARED_DIR, 'textdb_8a7f3b9c2d4e.txt');
const RESULT_DIR = path.join(SHARED_DIR, 'results');

const CHECK_INTERVAL = 2000;
const MAX_CONCURRENT_TASKS = 10;
const BROWSER_LAUNCH_TIMEOUT = 60000;
const WARMUP_URL = 'http://127.0.0.1:7860';
const PAGE_GOTO_TIMEOUT = 8000;

let taskStats = {
  total: 0,
  success: 0,
  failed: 0,
  concurrent: 0,
  totalDuration: 0
};

const processedTaskMD5s = new Map();
const browserPool = { available: [], busy: new Map(), isInitialized: false };
const runningTasks = new Set();
const taskQueue = new Set();

async function createBrowser() {
  try {
    const browser = await puppeteer.launch({
      headless: 'new',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--disable-gpu',
        '--single-process',
        '--no-zygote'
      ],
      timeout: BROWSER_LAUNCH_TIMEOUT,
      dumpio: false
    });

    const page = await browser.newPage();
    await page.evaluateOnNewDocument(() => {
      Object.defineProperty(navigator, 'webdriver', { get: () => false });
      Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
    });
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.1 Safari/537.36');
    
    await page.goto(WARMUP_URL, {
      waitUntil: 'domcontentloaded',
      timeout: PAGE_GOTO_TIMEOUT
    }).catch(()=>{});

    return { browser, page };
  } catch (err) {
    console.error(`❌ 浏览器实例启动失败: ${err.message}`);
    return null;
  }
}

async function initBrowserPool() {
  console.log(`初始化浏览器池（${MAX_CONCURRENT_TASKS}个实例）...`);
  const promises = Array.from({ length: MAX_CONCURRENT_TASKS }, () => createBrowser());
  const results = await Promise.all(promises);
  browserPool.available = results.filter(Boolean);
  browserPool.isInitialized = true;
  console.log(`浏览器池初始化完成，可用：${browserPool.available.length}/${MAX_CONCURRENT_TASKS}`);
}

async function acquireBrowser() {
  while (!browserPool.isInitialized) await new Promise(resolve => setTimeout(resolve, 100));
  return browserPool.available.length > 0 ? browserPool.available.shift() : null;
}

async function releaseBrowser(resource, md5) {
  if (browserPool.busy.has(md5)) {
    await resource.page.close().catch(()=>{});
    await resource.browser.close().catch(()=>{});
    browserPool.busy.delete(md5);
    taskStats.concurrent--;
  }
  const newResource = await createBrowser();
  if (newResource) browserPool.available.push(newResource);
  processNextTask();
}

async function readScriptFromVolume(md5) {
  const jsFilePath = path.join(SCRIPT_DIR, `${md5}.js`);
  return await fs.readFile(jsFilePath, 'utf8');
}

async function executeTask(md5) {
  if (processedTaskMD5s.has(md5) || runningTasks.has(md5)) return;

  runningTasks.add(md5);
  taskStats.total++;
  const startTime = Date.now();

  try {
    const [browserResource, jsCode] = await Promise.all([acquireBrowser(), readScriptFromVolume(md5)]);
    if (!browserResource) {
      taskQueue.add(md5);
      runningTasks.delete(md5);
      return;
    }

    const { browser, page } = browserResource;
    browserPool.busy.set(md5, browserResource);
    taskStats.concurrent++;

    const result = await page.evaluate(script => {
      window.eval(script);
      const collect = window.TDC?.getData?.() || null;
      const eks = window.TDC?.getInfo?.()?.info || null;
      return { collect, eks };
    }, jsCode);

    if (!result.collect || !result.eks) throw new Error('无有效返回');

    const resultPath = path.join(RESULT_DIR, `${md5}.json`);
    await fs.writeFile(resultPath, JSON.stringify({
      md5, collect: result.collect, eks: result.eks, success: true, timestamp: Date.now()
    }), 'utf8');

    await updateTaskStatus(md5, 2);
    processedTaskMD5s.set(md5, Date.now());

    const taskDuration = Date.now() - startTime;
    taskStats.success++;
    taskStats.totalDuration += taskDuration;
    console.log(`✅ 任务完成 ${md5} | ${taskDuration}ms`);
    await releaseBrowser(browserResource, md5);

  } catch (err) {
    const taskDuration = Date.now() - startTime;
    taskStats.failed++;
    console.error(`❌ 任务失败 ${md5}：${err.message}`);

    const resultPath = path.join(RESULT_DIR, `${md5}.json`);
    await fs.writeFile(resultPath, JSON.stringify({
      md5, success: false, error: err.message, timestamp: Date.now()
    }), 'utf8').catch(()=>{});

    const resource = browserPool.busy.get(md5);
    if (resource) releaseBrowser(resource, md5);
  } finally {
    runningTasks.delete(md5);
  }
}

async function updateTaskStatus(md5, status) {
  for (let i = 0; i < 3; i++) {
    try {
      const taskList = JSON.parse(await fs.readFile(TASK_LIST_FILE, 'utf8'));
      const updated = taskList.map(t => t.md5 === md5 ? {...t, status} : t);
      await fs.writeFile(TASK_LIST_FILE, JSON.stringify(updated,null,2), 'utf8');
      return;
    } catch {
      await new Promise(r=>setTimeout(r,100));
    }
  }
}

function processNextTask() {
  if (taskQueue.size === 0 || browserPool.available.length === 0) return;
  const md5 = [...taskQueue].shift();
  taskQueue.delete(md5);
  executeTask(md5);
}

async function pollSignal() {
  try {
    const signal = (await fs.readFile(SIGNAL_FILE, 'utf8')).trim();
    if (signal === '1') {
      await fetchTaskListFromVolume();
      await fs.writeFile(SIGNAL_FILE, '0', 'utf8');
    }
  } catch {}
}

async function fetchTaskListFromVolume() {
  try {
    const list = JSON.parse(await fs.readFile(TASK_LIST_FILE, 'utf8'));
    const pending = list.filter(t => t.status === 1 && !processedTaskMD5s.has(t.md5));
    pending.forEach(t => {
      taskQueue.add(t.md5);
      executeTask(t.md5);
    });
  } catch {}
}

async function startBot() {
  console.log('[TDC Bot 后台启动（无独立端口）]');
  await initBrowserPool();
  await fs.mkdir(RESULT_DIR, { recursive: true });
  setInterval(pollSignal, CHECK_INTERVAL);
  await fetchTaskListFromVolume();
}

process.on('SIGINT', async () => {
  console.log('\n退出清理浏览器...');
  const all = [...browserPool.available, ...browserPool.busy.values()];
  for (const r of all) {
    await r.page.close().catch(()=>{});
    await r.browser.close().catch(()=>{});
  }
  process.exit(0);
});

startBot().catch(err => {
  console.error('Bot启动失败：', err);
  process.exit(1);
});
