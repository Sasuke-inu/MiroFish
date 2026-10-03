// Browser acceptance harness. This file is excluded from production images.
import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from '../src/App.vue'
import productionRouter from '../src/router'
import i18n from '../src/i18n'
import service from '../src/api'
import { providerClient } from '../src/api/providers'
import { createFixtureAdapter } from './fixtures/api'
import '../src/styles/studio.css'
import '../src/styles/theme.css'

const fixtureAdapter = createFixtureAdapter({ emptyHistory: new URLSearchParams(location.search).get('emptyHistory') === '1' })
service.defaults.adapter = fixtureAdapter
providerClient.defaults.adapter = fixtureAdapter
const router = createRouter({ history: createWebHashHistory(), routes: productionRouter.options.routes })
createApp(App).use(router).use(i18n).mount('#app')
document.body.classList.add('fixture-preview')
const style = document.createElement('style')
style.textContent = '#fixture-notice { background:#203449;color:#fff;padding:9px 14px;font:12px system-ui;min-height:36px; } #fixture-notice a {color:#ffe3ce;margin-left:12px} .fixture-preview #app:has(> .main-view):not(:has(> .settings-page)) {height:calc(100dvh - 36px)}'
document.head.append(style)
