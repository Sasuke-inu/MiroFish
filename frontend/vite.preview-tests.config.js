import { defineConfig, mergeConfig } from 'vite'
import applicationConfig from './vite.config.js'

export default mergeConfig(applicationConfig, defineConfig({
  server: { host: '127.0.0.1', port: 3131, strictPort: true, open: false }
}))
