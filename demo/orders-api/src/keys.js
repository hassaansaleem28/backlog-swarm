const crypto = require('node:crypto');

// Signing keys for development and tests, generated in memory at startup.
// Production reads its keys from JWT_PRIVATE_KEY and JWT_PUBLIC_KEY instead.
const DEV_KEY_BITS = 1024;

function devKeys() {
  return crypto.generateKeyPairSync('rsa', {
    modulusLength: DEV_KEY_BITS,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
  });
}

function loadKeys(env = process.env) {
  if (env.NODE_ENV === 'production') {
    if (!env.JWT_PRIVATE_KEY || !env.JWT_PUBLIC_KEY) {
      throw new Error('JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required in production');
    }
    return { privateKey: env.JWT_PRIVATE_KEY, publicKey: env.JWT_PUBLIC_KEY };
  }
  return devKeys();
}

module.exports = { devKeys, loadKeys };
