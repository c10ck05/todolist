// Use the HTML's script order so regression tests exercise the actual entrypoint.
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
module.exports = [...html.matchAll(/<script\b[^>]*src="\.\/([^\"]+)"[^>]*><\/script>/g)]
    .map(match => fs.readFileSync(path.join(root, match[1]), 'utf8')).join('\n');
