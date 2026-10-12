const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../scripts/runtime_acceptance.js"), "utf8");

function gate({ frontend = false, backend = true, busyPort = false, browserFails = false, platform = process.platform, npmPresent = true } = {}) {
  const calls = { spawned: [], sync: [], cleanup: [], browserClosed: false };
  const page = {
    on() {},
    goto: async () => ({ status: () => 200 }),
    evaluate: async (fn) => !String(fn).includes("return root ?"),
    locator: () => ({ innerText: async () => "Application prête" }),
    waitForTimeout: async () => {},
  };
  const chromium = { launch: async () => {
    if (browserFails) throw Error("chromium unavailable");
    return { newPage: async () => page, close: async () => { calls.browserClosed = true; } };
  } };
  const fakeHttp = { get(url, onResponse) {
    const request = new EventEmitter();
    request.setTimeout = () => request;
    request.destroy = () => {};
    setImmediate(() => {
      const response = new EventEmitter();
      response.statusCode = 200;
      response.headers = { "content-type": "application/json" };
      response.resume = () => {};
      onResponse(response);
      response.emit("data", Buffer.from("{}"));
      response.emit("end");
    });
    return request;
  } };
  class FakeSocket extends EventEmitter {
    setTimeout() {}
    destroy() {}
    connect() { setImmediate(() => this.emit(busyPort ? "connect" : "error")); }
  }
  const childProcess = {
    spawn(command, args, options) {
      calls.spawned.push({ command, args, options });
      const child = new EventEmitter();
      child.stdout = new EventEmitter();
      child.stderr = new EventEmitter();
      child.pid = 100;
      child.exitCode = null;
      child.killed = false;
      child.kill = () => { calls.cleanup.push("kill"); child.killed = true; };
      return child;
    },
    spawnSync(command, args, options) {
      calls.sync.push({ command, args, options });
      if (command === "taskkill") calls.cleanup.push("taskkill");
      return { status: 0, stdout: command === "ps" ? "100 1" : "", stderr: "" };
    },
  };
  const modules = { fs: { existsSync: (file) => !String(file).endsWith("npm-cli.js") || npmPresent }, http: fakeHttp, net: { Socket: FakeSocket }, path,
                    child_process: childProcess, playwright: { chromium } };
  const fakeRequire = (name) => modules[name];
  fakeRequire.main = {};
  const sandbox = {
    require: fakeRequire, module: { exports: {} },
    process: {
      argv: ["node", "runtime_acceptance.js", "/workspace", "2000", frontend ? "/workspace/frontend" : "", backend ? "1" : "0"],
      env: { RUNTIME_BACKEND_COMMAND: JSON.stringify(["fake-backend"]), RUNTIME_BACKEND_LANGUAGE: "node" },
      platform,
      execPath: "C:\\Program Files\\nodejs\\node.exe",
      kill: () => calls.cleanup.push("kill"),
      exit() { throw Error("process.exit must not bypass cleanup"); },
    },
    console: { log() {} }, setTimeout, clearTimeout, URL,
  };
  vm.runInNewContext(source, sandbox, { filename: "runtime_acceptance.js" });
  return { api: sandbox.module.exports, process: sandbox.process, calls };
}

test("successful gate closes browser and child before returning", async () => {
  const run = gate({ frontend: true });
  await run.api.main();
  assert.equal(run.process.exitCode, 0);
  assert.equal(run.calls.spawned.length, 1);
  assert.equal(run.calls.browserClosed, true);
  assert.ok(run.calls.cleanup.length > 0);
});

test("browser infra failure also cleans the backend", async () => {
  const run = gate({ frontend: true, browserFails: true });
  await run.api.main();
  assert.equal(run.process.exitCode, 2);
  assert.ok(run.calls.cleanup.length > 0);
});

test("a pure API has no Chromium dependency and still cleans its server", async () => {
  const run = gate({ browserFails: true });
  await run.api.main();
  assert.equal(run.process.exitCode, 0);
  assert.equal(run.calls.browserClosed, false);
  assert.ok(run.calls.cleanup.length > 0);
});

test("frontend-only rejects an occupied port without launching or killing anything", async () => {
  const run = gate({ frontend: true, backend: false, busyPort: true });
  await run.api.main();
  assert.equal(run.process.exitCode, 2);
  assert.equal(run.calls.spawned.length, 0);
  assert.equal(run.calls.cleanup.length, 0);
});

test("frontend preview pins its port and never starts a backend", async () => {
  const run = gate({ frontend: true, backend: false });
  await run.api.main();
  assert.equal(run.process.exitCode, 0);
  assert.equal(run.calls.spawned.length, 1);
  assert.equal(run.calls.spawned[0].command, process.platform === "win32" ? "C:\\Program Files\\nodejs\\node.exe" : "npm");
  assert.ok(run.calls.spawned[0].args.includes("--strictPort"));
  assert.ok(run.calls.cleanup.length > 0);
});

test("Windows executables preserve space and shell-metacharacter arguments literally", () => {
  const run = gate({ platform: "win32" });
  const args = ["C:\\Project & files\\main.py", "value&whoami", "$(literal)"];
  run.api.launch("backend", "C:\\Program Files\\uv\\uv.exe", args, "C:\\Project & files");
  const call = run.calls.spawned[0];
  assert.equal(call.command, "C:\\Program Files\\uv\\uv.exe");
  assert.equal(call.options.shell, false);
  assert.deepEqual(Array.from(call.args), args);
});

test("Windows npm.cmd uses node plus npm-cli.js without a command shell", () => {
  const run = gate({ platform: "win32" });
  const resolved = run.api.resolveCommand("C:\\Tools & packages\\npm.cmd", ["run", "build", "--", "a&b"]);
  assert.equal(resolved.cmd, "C:\\Program Files\\nodejs\\node.exe");
  assert.deepEqual(Array.from(resolved.args), ["C:\\Tools & packages\\node_modules\\npm\\bin\\npm-cli.js", "run", "build", "--", "a&b"]);
});

test("Windows frontend build uses shell false", () => {
  const run = gate({ platform: "win32", frontend: true });
  run.api.runFrontendBuild();
  const build = run.calls.sync[0];
  assert.equal(build.options.shell, false);
  assert.equal(build.command, "C:\\Program Files\\nodejs\\node.exe");
  assert.ok(build.args[0].endsWith("npm-cli.js"));
});

test("Windows npm missing or unsupported batch launchers fail closed", () => {
  const run = gate({ platform: "win32", npmPresent: false });
  assert.throws(() => run.api.resolveCommand("npm", ["run", "build"]), /npm-cli.js introuvable/);
  assert.throws(() => run.api.resolveCommand("custom.cmd", []), /Launcher shell non pris en charge/);
  assert.equal(run.calls.spawned.length, 0);
});
