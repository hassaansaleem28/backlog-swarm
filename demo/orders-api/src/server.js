const { createApp } = require('./app');
const { loadKeys } = require('./keys');

const port = Number(process.env.PORT || 3000);
const ratesUrl = process.env.RATES_URL || 'https://rates.example.com';

createApp({ ...loadKeys(), ratesUrl }).listen(port, () => {
  console.log(`orders-api listening on ${port}`);
});
