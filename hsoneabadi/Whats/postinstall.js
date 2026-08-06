const fs = require('fs');
const path = require('path');

const utilsPath = path.join(__dirname, 'node_modules', 'whatsapp-web.js', 'src', 'util', 'Injected', 'Utils.js');

if (!fs.existsSync(utilsPath)) {
  console.warn('postinstall: Utils.js not found at', utilsPath);
  process.exit(0);
}

let content = fs.readFileSync(utilsPath, 'utf8');
let changed = false;

// Patch 1: canCheckStatusRankingPosterGating -> safe call
const oldCode1 = `                    cannotBeRanked: window
                        .require('WAWebStatusGatingUtils')
                        .canCheckStatusRankingPosterGating(),`;
const patchedCode1 = `                    cannotBeRanked: (() => {
                        try {
                            const gating = window.require('WAWebStatusGatingUtils');
                            return typeof gating.canCheckStatusRankingPosterGating === 'function'
                                ? gating.canCheckStatusRankingPosterGating()
                                : true;
                        } catch (e) {
                            return true;
                        }
                    })(),`;

if (content.includes(oldCode1)) {
  content = content.replace(oldCode1, patchedCode1);
  changed = true;
  console.log('postinstall: Patched canCheckStatusRankingPosterGating');
}

// Patch 2: isStatus detection broken in latest WA Web (returns true for all chats)
const oldCode2 = `        const isStatus = getIsBroadcast(chat);`;
const patchedCode2 = `        const isStatus = typeof getIsBroadcast === 'function' && getIsBroadcast(chat) && chat.id && (chat.id._serialized || '').endsWith('@broadcast');`;

if (content.includes(oldCode2)) {
  content = content.replace(oldCode2, patchedCode2);
  changed = true;
  console.log('postinstall: Patched isStatus detection');
}

if (changed) {
  fs.writeFileSync(utilsPath, content, 'utf8');
  console.log('postinstall: Utils.js updated');
}
