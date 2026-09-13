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

const testing = {frappe: {pages: {'revolut-setup': {}}}, __: value => value};
vm.createContext(testing);
vm.runInContext(`(function () {\n${script}\nglobalThis.Setup = RevolutSetup;})();`, testing);
const setup = Object.create(testing.Setup.prototype);
setup.esc = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const details = setup.accountDetails({id:'5c58d86e-5730-e2ad-0040-6d4b29390ffe', currency:'GBP', balance:0, state:'active', name:null});
assert.match(details, /Unnamed Revolut account/);
assert.match(details, /Balance: 0 GBP/);
assert.match(details, /Type: Not provided by Revolut/);
assert.match(details, /5c58d86e-5730-e2ad-0040-6d4b29390ffe/);
assert.ok(!setup.accountDetails({name:'<script>', currency:'GBP'}).includes('<script>'));
const chosen = setup.mappingSelections([
  {account:{id:'known',currency:'GBP'}, control:{get_value:()=> 'Main GBP'}},
  {account:{id:'unknown',currency:'GBP'}, control:{get_value:()=> ''}},
]);
assert.equal(chosen.length, 1);
assert.equal(chosen[0].account_id, 'known');
console.log('Account metadata, escaping, zero balance and optional mapping checks passed');

(async () => {
  const calls = [];
  setup.call = async (...args) => calls.push(args);
  setup.load = async () => calls.push(['load']);
  await setup.openAccountMappings({name:'connection', enabled:1});
  assert.deepEqual(JSON.parse(JSON.stringify(calls)),  [['pause', {connection:'connection'}], ['load']]);
  calls.length = 0;
  await setup.saveMappingProgress({name:'connection'}, [], 'UTC');
  assert.equal(calls.length, 0); // All accounts can remain skipped without activation.
  await setup.saveMappingProgress({name:'connection'}, [{account_id:'known',currency:'GBP',bank_account:'Main'}], 'UTC');
  assert.equal(calls[0][0], 'save_mappings');
  assert.ok(!calls.some(call => call[0] === 'activate'));
  console.log('Reopen basic mappings and save-for-later checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
