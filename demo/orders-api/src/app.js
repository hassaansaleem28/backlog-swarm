const express = require('express');
const jwt = require('jsonwebtoken');
const _ = require('lodash');
const axios = require('axios');

const ORDER_DEFAULTS = { currency: 'USD', items: [], status: 'pending' };

function createApp({ privateKey, publicKey, ratesUrl }) {
  const app = express();
  app.use(express.json());
  const orders = [];

  app.post('/login', (req, res) => {
    const { user } = req.body || {};
    if (!user) return res.status(400).json({ error: 'user is required' });
    const token = jwt.sign({ sub: user }, privateKey, { algorithm: 'RS256', expiresIn: '1h' });
    res.json({ token });
  });

  function requireUser(req, res, next) {
    const token = (req.get('authorization') || '').replace(/^Bearer /, '');
    try {
      req.user = jwt.verify(token, publicKey, { algorithms: ['RS256'] });
      next();
    } catch {
      res.status(401).json({ error: 'invalid token' });
    }
  }

  app.post('/orders', requireUser, (req, res) => {
    const order = _.merge({}, ORDER_DEFAULTS, _.pick(req.body, ['currency', 'items']), {
      id: orders.length + 1,
      owner: req.user.sub,
    });
    orders.push(order);
    res.status(201).json(order);
  });

  app.get('/orders', requireUser, (req, res) => {
    res.json(orders.filter((o) => o.owner === req.user.sub));
  });

  app.get('/orders/:id/total', requireUser, async (req, res, next) => {
    try {
      const order = orders.find((o) => o.id === Number(req.params.id) && o.owner === req.user.sub);
      if (!order) return res.status(404).json({ error: 'not found' });
      const subtotal = _.sumBy(order.items, (item) => item.price * item.qty);
      const { data } = await axios.get(`${ratesUrl}/rates`, { params: { base: 'USD' } });
      const rate = data.rates[order.currency] ?? 1;
      res.json({ currency: order.currency, total: Math.round(subtotal * rate * 100) / 100 });
    } catch (err) {
      next(err);
    }
  });

  return app;
}

module.exports = { createApp };
