import "@testing-library/jest-dom";

// --- React Flow (@xyflow/react) jsdom shims -------------------------------
// React Flow measures nodes/viewport with browser APIs jsdom doesn't provide.
// These are the mocks recommended by the xyflow testing guide.

class ResizeObserverMock {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    this.callback(
      [{ target } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}
(globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverMock;

class DOMMatrixReadOnlyMock {
  m22: number;
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([\d.]+)\)/)?.[1];
    this.m22 = scale !== undefined ? +scale : 1;
  }
}
(globalThis as Record<string, unknown>).DOMMatrixReadOnly = DOMMatrixReadOnlyMock;

Object.defineProperties(globalThis.HTMLElement.prototype, {
  offsetHeight: {
    get(this: HTMLElement) {
      return parseFloat(this.style.height) || 1;
    },
  },
  offsetWidth: {
    get(this: HTMLElement) {
      return parseFloat(this.style.width) || 1;
    },
  },
});

(globalThis.SVGElement.prototype as unknown as { getBBox: () => object }).getBBox =
  () => ({ x: 0, y: 0, width: 0, height: 0 });
