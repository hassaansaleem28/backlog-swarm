#!/usr/bin/env node
const fs = require('node:fs');
const parseArgs = require('minimist');
const { renderEmail } = require('./render');
const { sendToWebhook } = require('./send');

function parseOptions(argv) {
  const args = parseArgs(argv, {
    string: ['subject', 'file', 'webhook'],
    boolean: ['dry-run'],
    alias: { s: 'subject', f: 'file', w: 'webhook' },
  });
  if (!args.subject || !args.file) {
    throw new Error('usage: notify --subject <text> --file <markdown> [--webhook <url>] [--dry-run]');
  }
  return { subject: args.subject, file: args.file, webhook: args.webhook, dryRun: args['dry-run'] };
}

async function main(argv) {
  const options = parseOptions(argv);
  const email = renderEmail({ subject: options.subject, markdown: fs.readFileSync(options.file, 'utf8') });
  if (options.dryRun || !options.webhook) {
    process.stdout.write(`${email.html}\n`);
    return;
  }
  await sendToWebhook(options.webhook, email);
}

if (require.main === module) {
  main(process.argv.slice(2)).catch((err) => {
    console.error(err.message);
    process.exit(1);
  });
}

module.exports = { parseOptions };
