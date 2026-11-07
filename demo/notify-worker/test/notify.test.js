const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const WebSocket = require('ws');
const { renderEmail } = require('../src/render');
const { sendToWebhook } = require('../src/send');
const { startLiveFeed } = require('../src/live');
const { parseOptions } = require('../src/cli');

function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
}

test('renders Markdown to HTML', () => {
  const { subject, html } = renderEmail({ subject: ' Weekly report ', markdown: '**Done:** 3 [tasks](https://example.com)' });
  assert.equal(subject, 'Weekly report');
  assert.match(html, /<strong>Done:<\/strong>/);
  assert.match(html, /<a href="https:\/\/example.com">tasks<\/a>/);
});

test('never lets raw HTML through', () => {
  const { html } = renderEmail({
    subject: 'x',
    markdown: 'Hello <script>alert(1)</script> <img src=x onerror=alert(2)>',
  });
  assert.doesNotMatch(html, /<script/i);
  assert.doesNotMatch(html, /<img/i);
});

test('parses command-line options', () => {
  assert.deepEqual(parseOptions(['-s', 'Hi', '-f', 'msg.md', '--dry-run']), {
    subject: 'Hi',
    file: 'msg.md',
    webhook: undefined,
    dryRun: true,
  });
  assert.throws(() => parseOptions(['--subject', 'Hi']), /usage/);
});

test('posts the rendered email to the webhook', async (t) => {
  let received;
  const hook = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      received = JSON.parse(body);
      res.statusCode = 202;
      res.end();
    });
  });
  const port = await listen(hook);
  t.after(() => hook.close());
  const status = await sendToWebhook(`http://127.0.0.1:${port}/hook`, { subject: 'Hi', html: '<p>x</p>' });
  assert.equal(status, 202);
  assert.deepEqual(received, { subject: 'Hi', html: '<p>x</p>' });
});

test('streams sent emails to live dashboards', async (t) => {
  const server = http.createServer();
  const feed = startLiveFeed(server);
  const port = await listen(server);
  t.after(async () => {
    await feed.close();
    server.close();
  });
  const client = new WebSocket(`ws://127.0.0.1:${port}`);
  await new Promise((resolve) => client.on('open', resolve));
  const message = new Promise((resolve) => client.on('message', (data) => resolve(JSON.parse(data))));
  feed.broadcast({ subject: 'Hi' });
  assert.deepEqual(await message, { subject: 'Hi' });
  client.close();
});
