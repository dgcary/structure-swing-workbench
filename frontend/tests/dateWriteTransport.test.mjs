import assert from "node:assert/strict";
import { test } from "node:test";
import { canSendDateWriteToken } from "../src/dateWriteTransport.ts";

test("privileged date token is allowed only over HTTPS or local loopback HTTP", () => {
  for (const host of ["workbench.example", "192.168.1.8", "localhost"]) {
    assert.equal(canSendDateWriteToken("https:", host), true);
  }
  for (const host of ["localhost", "127.0.0.1", "[::1]", "::1"]) {
    assert.equal(canSendDateWriteToken("http:", host), true);
  }
  for (const host of ["workbench.example", "192.168.1.8", "127.0.0.2", "localhost.evil.example"]) {
    assert.equal(canSendDateWriteToken("http:", host), false);
  }
  assert.equal(canSendDateWriteToken("file:", ""), false);
  assert.equal(canSendDateWriteToken("ws:", "localhost"), false);
});
