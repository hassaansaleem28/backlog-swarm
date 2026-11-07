const WebSocket = require('ws');

// Streams every sent notification to the dashboards that are watching.
function startLiveFeed(server) {
  const wss = new WebSocket.Server({ server });
  return {
    broadcast(message) {
      const data = JSON.stringify(message);
      for (const client of wss.clients) {
        if (client.readyState === WebSocket.OPEN) client.send(data);
      }
    },
    close: () => new Promise((resolve) => wss.close(resolve)),
  };
}

module.exports = { startLiveFeed };
