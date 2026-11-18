// Shared checks: the app runs locally with no external operation, under the
// strict CSP and the single read-only Tauri command. Run after `npm run build`.
import test from "node:test";
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve, join } from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const read = (p) => readFile(resolve(root, p), "utf8");
const CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src ipc: http://ipc.localhost";

async function distScripts() {
  const out = [];
  for (const dir of ["dist", "dist/domain"]) for (const name of await readdir(resolve(root, dir))) if (name.endsWith(".js")) out.push(join(dir, name));
  return out;
}

test("descriptor declares local state and no external operation", async () => {
  const d = JSON.parse(await read("dist/descriptor.json"));
  assert.equal(d.schema, "kotoba.app.client-runtime.v1");
  assert.deepEqual(d.operations, []);
  assert.deepEqual(d.workers, []);
  assert.equal(d["local-state"].adapter, "localstorage");
});

test("shipped scripts contain no network API", async () => {
  for (const file of await distScripts()) {
    const src = await read(file);
    for (const api of [/\bfetch\s*\(/, /XMLHttpRequest/, /\bWebSocket\b/, /\bEventSource\b/, /sendBeacon/, /import\s*\(\s*["'`]https?:/, /from\s+["']https?:/]) {
      assert.ok(!api.test(src), `${file} uses ${api}`);
    }
  }
});

test("CSP is strict in the page and in the Tauri config", async () => {
  assert.ok((await read("src/ui/index.html")).includes(CSP));
  const conf = JSON.parse(await read("src-tauri/tauri.conf.json"));
  assert.ok(conf.app.security.csp.startsWith(CSP));
  assert.equal(conf.$schema, "https://schema.tauri.app/config/3");
});

test("the Tauri host grants only the read-only host-info command", async () => {
  const caps = await readdir(resolve(root, "src-tauri/capabilities"));
  for (const name of caps) {
    const cap = JSON.parse(await read(join("src-tauri/capabilities", name)));
    assert.deepEqual(cap.permissions, ["allow-awai-host-info"]);
  }
  const cargo = await read("src-tauri/Cargo.toml");
  assert.match(cargo, /tauri = \{ version = "=3\.0\.0-alpha\.6"/);
  assert.doesNotMatch(cargo, /tauri-plugin-(http|fs|shell)/);
});

test("release manifest pins every shipped file", async () => {
  const release = JSON.parse(await read("dist/release.json"));
  for (const file of await distScripts()) assert.ok(release.files[file.replace(/^dist\//, "")], `${file} is not pinned`);
});

test("the Android project asks for no permission", async () => {
  const manifest = await read("src-tauri/gen/android/app/src/main/AndroidManifest.xml");
  assert.doesNotMatch(manifest, /<uses-permission/);
});
