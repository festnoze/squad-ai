import { configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { FakeEventSource } from "./FakeEventSource";

// A cold first run on Windows can spend seconds setting up jsdom: the default 1 s of
// findBy / waitFor then fails tests that are not wrong.
configure({ asyncUtilTimeout: 5000 });

// jsdom has no EventSource: every test gets the fake unless it stubs its own.
beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  FakeEventSource.reset();
  window.location.hash = "";
});
