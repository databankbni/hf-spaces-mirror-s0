// Pre-load require hook that neutralizes `server-only`.
// Used by `dump-adapter-outputs.mts` via `--require`.
const Module = require("node:module")
const origLoad = Module._load
Module._load = function (request, ...rest) {
  if (request === "server-only") {
    return {}
  }
  return origLoad.apply(this, [request, ...rest])
}
