const marked = require('marked');

// Notification bodies come from users, so raw HTML in them must never reach
// an inbox as HTML.
function renderEmail({ subject, markdown }) {
  return {
    subject: subject.trim(),
    html: marked(markdown, { sanitize: true }),
  };
}

module.exports = { renderEmail };
