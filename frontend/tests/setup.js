import { vi } from 'vitest'

class Observer {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('IntersectionObserver', Observer)
vi.stubGlobal('ResizeObserver', Observer)
Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 800 })
Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 600 })
Element.prototype.scrollTo = vi.fn()
window.scrollTo = vi.fn()
SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 80, height: 20 })
Object.defineProperty(SVGElement.prototype, 'width', { configurable: true, get: () => ({ baseVal: { value: 800 } }) })
Object.defineProperty(SVGElement.prototype, 'height', { configurable: true, get: () => ({ baseVal: { value: 600 } }) })
Object.defineProperty(SVGElement.prototype, 'viewBox', { configurable: true, get: () => ({ baseVal: { x: 0, y: 0, width: 800, height: 600 } }) })
