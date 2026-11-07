const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { createApp } = require('../src/app');
const { devKeys } = require('../src/keys');

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

test('orders flow', async (t) => {
  const rates = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ base: 'USD', rates: { EUR: 0.5, USD: 1 } }));
  });
  const ratesUrl = await listen(rates);
  const api = http.createServer(createApp({ ...devKeys(), ratesUrl }));
  const base = await listen(api);
  t.after(() => {
    api.close();
    rates.close();
  });

  const call = async (path, { token, body, method } = {}) => {
    const res = await fetch(base + path, {
      method: method || (body ? 'POST' : 'GET'),
      headers: {
        'content-type': 'application/json',
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    return { status: res.status, body: await res.json() };
  };

  const { body: login } = await call('/login', { body: { user: 'ada' } });
  const token = login.token;

  await t.test('sign-in issues a token', () => {
    assert.ok(token);
  });

  await t.test('rejects requests without a valid token', async () => {
    assert.equal((await call('/orders')).status, 401);
    assert.equal((await call('/orders', { token: 'nope' })).status, 401);
  });

  await t.test('creates an order with defaults', async () => {
    const { status, body } = await call('/orders', {
      token,
      body: { currency: 'EUR', items: [{ sku: 'a', price: 10, qty: 3 }] },
    });
    assert.equal(status, 201);
    assert.equal(body.status, 'pending');
    assert.equal(body.owner, 'ada');
  });

  await t.test('lists only the caller’s orders', async () => {
    const other = (await call('/login', { body: { user: 'bob' } })).body.token;
    assert.equal((await call('/orders', { token })).body.length, 1);
    assert.equal((await call('/orders', { token: other })).body.length, 0);
  });

  await t.test('totals an order in its currency', async () => {
    const { body } = await call('/orders/1/total', { token });
    assert.deepEqual(body, { currency: 'EUR', total: 15 });
  });

  await t.test('an order body cannot pollute Object.prototype', async () => {
    await call('/orders', {
      token,
      body: JSON.parse('{"items":[],"__proto__":{"polluted":true}}'),
    });
    assert.equal({}.polluted, undefined);
  });
});
