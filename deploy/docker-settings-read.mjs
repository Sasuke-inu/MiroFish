import http from 'node:http';

const pipe = '\\\\.\\pipe\\dockerBackendApiServer';
await new Promise((resolve, reject) => {
  const request = http.get({ socketPath: pipe, path: '/app/settings', timeout: 5000 }, response => {
    let data = '';
    response.on('data', chunk => { data += chunk; });
    response.on('end', () => {
      console.log('Docker settings HTTP status:', response.statusCode);
      try {
        const value = JSON.parse(data);
        function printAnalytics(object, path = '') {
          if (!object || typeof object !== 'object') return;
          for (const [key, child] of Object.entries(object)) {
            const current = path + '.' + key;
            if (/analyticsEnabled/i.test(key)) console.log(current, JSON.stringify(child));
            else printAnalytics(child, current);
          }
        }
        printAnalytics(value);
        console.log('Top-level keys:', Object.keys(value).slice(0, 24).join(', '));
      } catch { console.log(data.slice(0, 300)); }
      resolve();
    });
  });
  request.on('timeout', () => request.destroy(new Error('Docker settings request timed out')));
  request.on('error', reject);
});
