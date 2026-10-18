// Uses the settings API shipped with this installed Docker Desktop build.
import http from 'node:http';
const socketPath = '\\\\.\\pipe\\dockerBackendApiServer';
const delta = { settings: { 'desktop.analyticsEnabled': false } };
async function request(method, path, body) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? undefined : JSON.stringify(body);
    const req = http.request({
      socketPath, method, path, timeout: 5000,
      headers: payload === undefined ? {} : { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) },
    }, response => {
      let text = '';
      response.on('data', chunk => { text += chunk; });
      response.on('end', () => {
        if (response.statusCode !== 200) return reject(new Error(`Docker settings HTTP ${response.statusCode}`));
        try { resolve(JSON.parse(text)); } catch (error) { reject(error); }
      });
    });
    req.on('timeout', () => req.destroy(new Error('Docker settings timeout')));
    req.on('error', reject);
    req.end(payload);
  });
}
const current = await request('GET', '/app/settings');
console.log('Docker analytics enabled:', current.desktop.analyticsEnabled.value);
const restart = await request('GET', '/app/settings/gui/do_changes_need_restart', delta);
console.log('Restart requirement:', JSON.stringify(restart));
