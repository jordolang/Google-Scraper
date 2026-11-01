// Run with `node --test` from this folder (no install needed: the Blob
// upload is passed in as a fake). The expected values come from the Python
// side (opt_outs.fingerprint / opt_outs.sign), so the two can't drift apart.

import assert from "node:assert/strict";
import { test } from "node:test";

process.env.UNSUBSCRIBE_SECRET = "k1";
const { default: handler, sign, validLink } = await import("../api/unsubscribe.js");

// opt_outs.fingerprint("Owner@Shop.com ") and opt_outs.sign("k1", that)
const H = "231af1e209e7597ff54ab1b3fc35b00c961f870a0220dbe351166d2f6d3f3296";
const S = "68120365eee8e58a1ef4f290cf0d6c24";

function fakeRes() {
  return {
    statusCode: 200, headers: {}, body: "",
    setHeader(k, v) { this.headers[k.toLowerCase()] = v; },
    end(text = "") { this.body = text; },
  };
}

test("signatures match the desktop app", () => {
  assert.equal(sign("k1", H), S);
  assert.ok(validLink("k1", H, S));
  assert.ok(!validLink("k1", H, S.replace(/.$/, "0")));
  assert.ok(!validLink("other", H, S));
  assert.ok(!validLink("", H, S));
});

test("a footer click records the unsubscribe", async () => {
  const stored = [];
  const res = fakeRes();
  await handler({ method: "GET", url: `/api/unsubscribe?h=${H}&s=${S}` }, res,
    async (path, body, options) => stored.push({ path, body: JSON.parse(body), options }));
  assert.equal(res.statusCode, 200);
  assert.match(res.body, /unsubscribed/);
  assert.equal(stored[0].path, `optouts/${H}.json`);
  assert.equal(stored[0].body.method, "link");
  assert.equal(stored[0].options.addRandomSuffix, false);
});

test("one-click POST records and answers plainly", async () => {
  const stored = [];
  const res = fakeRes();
  await handler({ method: "POST", url: `/api/unsubscribe?h=${H}&s=${S}` }, res,
    async (path, body) => stored.push(JSON.parse(body)));
  assert.equal(res.body, "Unsubscribed.\n");
  assert.equal(stored[0].method, "one-click");
});

test("forged or broken links store nothing", async () => {
  const stored = [];
  for (const url of [`/api/unsubscribe?h=${H}&s=deadbeef`, "/api/unsubscribe", `/api/unsubscribe?h=x&s=${S}`]) {
    const res = fakeRes();
    await handler({ method: "GET", url }, res, async () => stored.push(url));
    assert.equal(res.statusCode, 400);
  }
  assert.equal(stored.length, 0);
});

test("a storage failure says so", async () => {
  const res = fakeRes();
  await handler({ method: "GET", url: `/api/unsubscribe?h=${H}&s=${S}` }, res,
    async () => { throw new Error("down"); });
  assert.equal(res.statusCode, 500);
});
