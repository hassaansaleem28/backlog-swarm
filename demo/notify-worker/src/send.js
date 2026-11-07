const fetch = require('node-fetch');

async function sendToWebhook(url, message) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(message),
  });
  if (!res.ok) throw new Error(`webhook answered ${res.status}`);
  return res.status;
}

module.exports = { sendToWebhook };
