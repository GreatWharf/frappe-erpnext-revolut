// v16 evaluates Page scripts within an IIFE. Exercise registration without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const file = path.join(__dirname, '../revolut_bank_feed/revolut_bank_feed/page/revolut_setup/revolut_setup.js');
const script = fs.readFileSync(file, 'utf8');
const context = {frappe: {pages: {'revolut-setup': {}}}};
vm.createContext(context);
for (let i = 0; i < 2; i++) {
  vm.runInContext(`(function () {\n${script}\n})();`, context);
  assert.equal(typeof context.frappe.pages['revolut-setup'].on_page_load, 'function');
  assert.equal(typeof context.frappe.pages['revolut-setup'].on_page_show, 'function');
}
assert.equal(context.RevolutSetup, undefined);
console.log('v16 Page IIFE registration smoke check passed');
