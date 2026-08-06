const fs = require('fs').promises;
const path = require('path');

// ============ 新增日志缓存模块 ============
const LOG_CACHE = [];
const MAX_LOG_LEN = 200;

const oldLog = console.log;
const oldErr = console.error;

function pushLog(type, msg){
  const time = new Date().toLocaleString('zh-CN',{hour12:false});
  const line = `[${time}] [${type}] ${msg}`;
  LOG_CACHE.push(line);
  if(LOG_CACHE.length > MAX_LOG_LEN) LOG_CACHE.shift();
}

console.log = function(...args){
  const s = args.map(x=>typeof x==='object'?JSON.stringify(x,null,2):x).join(' ');
  pushLog("INFO", s);
  oldLog.apply(console, args);
};
console.error = function(...args){
  const s = args.map(x=>typeof x==='object'?JSON.stringify(x,null,2):x).join(' ');
  pushLog("ERROR", s);
  oldErr.apply(console, args);
};
// ========================================

const TEXTDB_CONFIG = {
  KEY: '8a7f3b9c2d4e',
  SIGNAL_NO_UPDATE: '0',
  SIGNAL_HAS_UPDATE: '1'
};

const SHARED_DIR = '/datasets/txc1/tdc-shared-data';
const SCRIPT_DIR = path.join(SHARED_DIR, 'scripts');
const TASK_LIST_FILE = path.join(SHARED_DIR, 'tasks.json');
const SIGNAL_FILE = path.join(SHARED_DIR, `textdb_${TEXTDB_CONFIG.KEY}.txt`);
const RESULT_DIR = path.join(SHARED_DIR, 'results');

const CAPTCHA_CONFIG = {
  PREHANDLE_URL: 'https://ca.turing.captcha.qcloud.com/cap_union_prehandle',
  AID: '189981187',
  IMAGE_BASE_URL: 'https://ca.turing.captcha.qcloud.com'
};

async function initDirsAndFiles() {
  await fs.mkdir(SCRIPT_DIR, { recursive: true });
  await fs.mkdir(RESULT_DIR, { recursive: true });

  try {
    await fs.access(TASK_LIST_FILE);
  } catch (err) {
    await fs.writeFile(TASK_LIST_FILE, JSON.stringify([]), 'utf8');
    console.log(`✅ 初始化任务列表文件: ${TASK_LIST_FILE}`);
  }

  try {
    await fs.access(SIGNAL_FILE);
  } catch (err) {
    await fs.writeFile(SIGNAL_FILE, TEXTDB_CONFIG.SIGNAL_NO_UPDATE, 'utf8');
    console.log(`✅ 初始化信号文件: ${SIGNAL_FILE}`);
  }

  console.log(`Worker 初始化完成，外部数据集目录: ${SHARED_DIR}`);
}

async function getTaskList() {
  try {
    const listStr = await fs.readFile(TASK_LIST_FILE, 'utf8');
    return JSON.parse(listStr);
  } catch (e) {
    console.error('解析任务列表失败，重置为空数组');
    return [];
  }
}

async function saveTaskList(list) {
  try {
    const listStr = JSON.stringify(list, null, 2);
    await fs.writeFile(TASK_LIST_FILE, listStr, 'utf8');

    const verifyStr = await fs.readFile(TASK_LIST_FILE, 'utf8');
    const verifyList = JSON.parse(verifyStr);
    if (verifyList.length !== list.length) {
      throw new Error(`验证失败:任务数量不一致`);
    }
    const writeMd5Set = new Set(list.map(item => item.md5));
    const verifyMd5Set = new Set(verifyList.map(item => item.md5));
    if (![...writeMd5Set].every(md5 => verifyMd5Set.has(md5))) {
      throw new Error('验证失败：任务MD5不完整');
    }

    console.log(`任务列表更新成功，共 ${list.length} 个任务`);
    return true;
  } catch (e) {
    console.error('保存任务列表失败!');
    return false;
  }
}

async function setTextDBSignal(signal) {
  try {
    await fs.writeFile(SIGNAL_FILE, signal, 'utf8');
    console.log(`✅ 本地信号已更新为：${signal}`);
    return true;
  } catch (e) {
    console.error('❌ 设置本地信号失败!');
    return false;
  }
}

async function saveScript(md5, jsContent) {
  const jsPath = path.join(SCRIPT_DIR, `${md5}.js`);
  await fs.writeFile(jsPath, jsContent, 'utf8');
}

async function getScript(md5) {
  const jsPath = path.join(SCRIPT_DIR, `${md5}.js`);
  try {
    await fs.access(jsPath);
    return await fs.readFile(jsPath, 'utf8');
  } catch (e) {
    return null;
  }
}

async function deleteScript(md5) {
  const jsPath = path.join(SCRIPT_DIR, `${md5}.js`);
  await fs.unlink(jsPath).catch(() => {});
}

async function saveResult(md5, data) {
  const resultPath = path.join(RESULT_DIR, `${md5}.json`);
  await fs.writeFile(resultPath, JSON.stringify(data, null, 2), 'utf8');
}

async function getResult(md5) {
  const resultPath = path.join(RESULT_DIR, `${md5}.json`);
  try {
    await fs.access(resultPath);
    const data = await fs.readFile(resultPath, 'utf8');
    return JSON.parse(data);
  } catch (e) {
    return null;
  }
}

async function deleteResult(md5) {
  const resultPath = path.join(RESULT_DIR, `${md5}.json`);
  await fs.unlink(resultPath).catch(() => {});
}

async function updateMd5List(md5, status) {
  const currentList = await getTaskList();
  const itemIndex = currentList.findIndex(item => item.md5 === md5);
  const now = Date.now();

  if (itemIndex > -1) {
    currentList[itemIndex].status = status;
    currentList[itemIndex].updateTime = now;
  } else {
    currentList.push({
      md5,
      status,
      createTime: now,
      updateTime: now
    });
  }

  const saveSuccess = await saveTaskList(currentList);
  if (!saveSuccess) {
    throw new Error(`任务列表更新失败:MD5-[${md5}]`);
  }

  const signalSuccess = await setTextDBSignal(TEXTDB_CONFIG.SIGNAL_HAS_UPDATE);
  if (!signalSuccess) {
    console.warn(`MD5-[${md5}]状态更新成功，但信号设置失败`);
  }
}

async function generateTask(md5 = Date.now().toString(16).slice(-8), jsCode) {
  try {
    if (!jsCode) {
      jsCode = `
        window.TDC = {
          getData: function() {
            return 'collect_${md5}_' + Math.random().toString(36).slice(2);
          },
          getInfo: function() {
            return { info: 'eks_${md5}_' + Math.random().toString(36).slice(2) };
          }
        };
      `;
    }

    await saveScript(md5, jsCode);
    console.log(`生成JS脚本: ${md5}.js`);

    const taskList = await getTaskList();
    taskList.push({ md5, status: 1, createTime: Date.now(), updateTime: Date.now() });
    await saveTaskList(taskList);
    console.log(`更新任务列表，当前任务数: ${taskList.length}`);

    await setTextDBSignal(TEXTDB_CONFIG.SIGNAL_HAS_UPDATE);
    console.log(`发送执行信号: ${TEXTDB_CONFIG.SIGNAL_HAS_UPDATE}`);

    return { success: true, md5 };
  } catch (err) {
    console.error(`❌ 生成任务失败: ${err.message}`);
    return { success: false, error: err.message };
  }
}

global.triggerTask = async (md5, jsCode) => {
  return await generateTask(md5, jsCode);
};

exports.getCaptcha = async function () {
  try {
    const prehandleUrl = `${CAPTCHA_CONFIG.PREHANDLE_URL}?aid=${CAPTCHA_CONFIG.AID}`;
    const res = await fetch(prehandleUrl, { timeout: 5000 });
    let txt = await res.text();

    if (txt.length >= 2) {
      if (txt.startsWith('(') && txt.endsWith(')')) {
        txt = txt.substring(1, txt.length - 1);
      } else if (!txt.startsWith('{')) {
        txt = txt.substring(1);
      }
    }

    const data = JSON.parse(txt);
    const commCfg = data.data.comm_captcha_cfg;
    const tdcPath = `${CAPTCHA_CONFIG.IMAGE_BASE_URL}${commCfg.tdc_path}`;
    const md5 = commCfg.pow_cfg?.md5 || null;

    if (md5) {
      const tdcRes = await fetch(tdcPath, { timeout: 5000 });
      if (tdcRes.ok) {
        const jsContent = await tdcRes.text();
        await saveScript(md5, jsContent);
        console.log(`JS缓存成功：${md5}`);
        await updateMd5List(md5, 1);
      } else {
        console.error(`JS下载失败：${tdcRes.status}`);
      }
    }

    let img_url = data.data.dyn_show_info?.bg_elem_cfg?.img_url || null;
    let sprite_url = data.data.dyn_show_info?.sprite_url || null;

    if (img_url && img_url.startsWith('/')) {
      img_url = CAPTCHA_CONFIG.IMAGE_BASE_URL + img_url;
    }
    if (sprite_url && sprite_url.startsWith('/')) {
      sprite_url = CAPTCHA_CONFIG.IMAGE_BASE_URL + sprite_url;
    }

    return {
      sess: data.sess,
      tdc_path: tdcPath,
      prefix: commCfg.pow_cfg?.prefix || null,
      md5: md5,
      img_url: img_url,
      sprite_url: sprite_url
    };
  } catch (e) {
    console.error('验证码接口 /do 失败!');
    return { error: e.message };
  }
};

exports.handleMd5List = async function () {
  try {
    const taskList = await getTaskList();
    return taskList.map(item => ({ md5: item.md5, status: item.status }));
  } catch (e) {
    console.error('/md5-list 接口失败!');
    return [];
  }
};

exports.handleGetAndTrigger = function (query) {
  const md5 = query.md5;
  if (!md5) return { error: '缺少 md5 参数' };
  return getResult(md5).then(data=>{
    const res = { status: '读取成功', message: '结果如下↓' };
    if(data){
      res.collect = data.collect;
      res.eks = data.eks;
    }
    return res;
  }).catch(e=>{
    console.error('/get 接口失败!');
    return { error: e.message };
  });
};

exports.handleSave = async function (query) {
  const md5 = query.md5;
  const col = query.collect;
  const eks = query.eks;

  if (!md5) return { success: false, error: '缺少 md5 参数' };
  if (!col || !eks) return { success: false, error: '缺少 collect 或 eks 参数' };

  try {
    const data = { collect: col, eks: eks, updated: Date.now() };
    await saveResult(md5, data);
    await updateMd5List(md5, 0);
    return { success: true, message: '已保存，状态更新为0' };
  } catch (e) {
    console.error(`/save 接口处理MD5-[${md5}]失败!`);
    return { success: false, error: e.message };
  }
};

exports.handleGetCachedScript = async function (query) {
  const md5 = query.md5;
  if (!md5) return { error: '缺少 md5 参数' };
  try {
    const jsContent = await getScript(md5);
    return jsContent || '/* TDC Worker: Cache Miss- MD5不存在或未缓存*/';
  } catch (e) {
    console.error('/js 接口失败!');
    return { error: e.message };
  }
};

exports.handleClear = async function (query) {
  const md5 = query.md5;
  if (!md5) return { error: '缺少 md5 参数' };
  try {
    await deleteScript(md5);
    await deleteResult(md5);
    const currentList = await getTaskList();
    const newList = currentList.filter(item => item.md5 !== md5);
    const removeSuccess = await saveTaskList(newList);
    if (!removeSuccess) throw new Error('移除任务列表项失败!');
    await setTextDBSignal(TEXTDB_CONFIG.SIGNAL_HAS_UPDATE);
    return { status: 'success', message: `MD5 ${md5}已清除` };
  } catch (e) {
    console.error('/cl5 接口失败!');
    return { error: e.message };
  }
};

exports.handleClearAll = async function () {
  try {
    const scriptFiles = await fs.readdir(SCRIPT_DIR).catch(() => []);
    await Promise.all(scriptFiles.map(file => fs.unlink(path.join(SCRIPT_DIR, file))));
    const resultFiles = await fs.readdir(RESULT_DIR).catch(() => []);
    await Promise.all(resultFiles.map(file => fs.unlink(path.join(RESULT_DIR, file))));
    await fs.writeFile(TASK_LIST_FILE, JSON.stringify([]), 'utf8');
    await setTextDBSignal(TEXTDB_CONFIG.SIGNAL_NO_UPDATE);
    return {
      status: 'success',
      message: '所有数据已清除，本地信号已重置为 0',
      deletedCount: scriptFiles.length + resultFiles.length
    };
  } catch (e) {
    console.error('/clear 接口失败');
    return { error: e.message };
  }
};

exports.handleResetSignal = async function () {
  try {
    const success = await setTextDBSignal(TEXTDB_CONFIG.SIGNAL_NO_UPDATE);
    return {
      success: success,
      message: success ? '本地信号已重置为 0' : '重置本地信号失败'
    };
  } catch (e) {
    console.error('/reset-signal 接口失败!');
    return { success: false, error: e.message };
  }
};

exports.handleDebug = async function () {
  try {
    const taskList = await getTaskList();
    let currentSignal = 'unknown';
    try {
      currentSignal = await fs.readFile(SIGNAL_FILE, 'utf8');
    } catch (e) {
      console.warn('读取本地信号失败：', e);
    }
    return {
      r2_task_count: taskList.length,
      textdb_key: TEXTDB_CONFIG.KEY,
      textdb_current_signal: currentSignal.trim(),
      r2_task_list: taskList.map(item => ({ md5: item.md5, status: item.status }))
    };
  } catch (e) {
    console.error('/debug 接口失败!');
    return { error: e.message };
  }
};

// 新增：日志接口
exports.handleLog = async function () {
  return {
    serverTime: new Date().toLocaleString('zh-CN',{hour12:false}),
    logTotal: LOG_CACHE.length,
    logs: [...LOG_CACHE]
  };
};

initDirsAndFiles()
  .then(() => {
    console.log(`Worker启动成功 (使用外部 Hugging Face Dataset)`);
    setInterval(() => {}, 1000);
  })
  .catch((err) => {
    console.error(`❌ Worker启动失败: ${err.message}`);
    process.exit(1);
  });
