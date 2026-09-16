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
const selections = [
  {account:{id:'known',currency:'GBP'}, control:{get_value:()=> 'Main GBP'}},
  {account:{id:'unidentified',currency:'GBP'}, control:{get_value:()=> ''}},
];
const chosen = setup.mappingSelections(selections);
assert.equal(chosen.length, 1);
assert.equal(chosen[0].account_id, 'known');
const skipped = setup.skippedSelections(selections);
assert.deepEqual(JSON.parse(JSON.stringify(skipped)), [{account_id:'unidentified',currency:'GBP'}]);
console.log('Account metadata, escaping, zero balance and explicit mapping checks passed');

// Minimal render boundary: exercise real dashboard grouping without needing Desk.
class Element {
  constructor(markup) { this.markup = markup; this.children = []; }
  appendTo(parent) { this.parent = parent; parent.children.push(this); return this; }
  text(value) { this.content = value; return this; }
  html(value) { this.content = value; return this; }
  css() { return this; }
  attr() { return this; }
}
function isDisclosure(element) {
  for (let node = element; node; node = node.parent) {
    if (node.markup.startsWith('<details')) return true;
  }
  return false;
}
function checkDashboardGroups() {
  testing.$ = markup => new Element(markup);
  const dashboard = Object.create(testing.Setup.prototype);
  dashboard.card = new Element('<section>');
  dashboard.data = {scheduler_enabled:true, reviews:0};
  dashboard.esc = setup.esc;
  const actions = [];
  dashboard.action = (parent, label, fn, primary = false) => { actions.push({parent,label,fn,primary}); };
  dashboard.dashboard({name:'connection', company:'Acme', enabled:1});
  const action = label => actions.find(row => row.label === label);
  const main = action('Sync now').parent;
  assert.equal(action('Sync now').primary, true);
  assert.deepEqual(actions.filter(row => row.parent === main).map(row => row.label),
    ['Sync now', 'Bank transactions', 'Review transactions', 'Sync logs']);
  assert.equal(actions.length, 14); // Preserve every existing capability.
  assert.ok(isDisclosure(action('Import older transactions').parent));
  assert.ok(isDisclosure(action('Choose extra data').parent));
  assert.notEqual(action('Choose extra data').parent, action('Import older transactions').parent);
  assert.equal(action('FX quotes').parent, action('Choose extra data').parent);
  assert.notEqual(action('Pause feed').parent, main);
  assert.equal(action('Manage accounts').parent, action('Pause feed').parent);
  console.log('Dashboard primary actions, disclosures and separated management checks passed');
}
function checkConnectionFormGroups() {
  const formFile = path.join(__dirname, '../revolut_bank_feed/revolut_bank_feed/doctype/revolut_connection/revolut_connection.js');
  let handlers;
  const formContext = {__: value => value, frappe:{ui:{form:{on:(name, value) => { handlers = value; }}}}};
  vm.runInNewContext(fs.readFileSync(formFile, 'utf8'), formContext);
  const actions = [], types = [];
  const frm = {doc:{name:'connection',enabled:1}, is_new:()=>false,
    add_custom_button:(label,fn,group) => actions.push({label,fn,group}),
    change_custom_button_type:(...args) => types.push(args)};
  handlers.refresh(frm);
  assert.deepEqual(actions.filter(row => !row.group).map(row => row.label), ['Guided setup', 'Sync Now']);
  assert.equal(actions.find(row => row.label === 'Discover Accounts').group, 'Accounts');
  assert.equal(actions.find(row => row.label === 'Account Mappings').group, 'Accounts');
  assert.equal(actions.find(row => row.label === 'Historical Backfill').group, 'Sync');
  assert.equal(actions.find(row => row.label === 'Sync Logs').group, 'View');
  assert.equal(actions.find(row => row.label === 'Source Reviews').group, 'View');
  assert.deepEqual(types, [['Sync Now', null, 'primary']]);
  actions.length = 0;
  frm.doc.enabled = 0;
  handlers.refresh(frm);
  assert.ok(!actions.some(row => ['Sync Now','Historical Backfill'].includes(row.label)));
  console.log('Native connection toolbar grouping and paused-state checks passed');
}

(async () => {
  const calls = [], confirmations = [];
  let decision = false;
  testing.frappe.confirm = (message, yes, no) => {
    confirmations.push(message);
    queueMicrotask(() => { if (decision !== 'dismiss') (decision ? yes : no)(); });
    return {$wrapper:{one:(event, hidden) => { if (decision === 'dismiss') queueMicrotask(hidden); }}};
  };
  setup.call = async (...args) => calls.push(args);
  setup.load = async () => calls.push(['load']);
  await setup.openAccountMappings({name:'connection', enabled:1});
  assert.equal(calls.length, 0); // Cancel does not pause or navigate.
  decision = 'dismiss';
  await setup.openAccountMappings({name:'connection', enabled:1});
  assert.equal(calls.length, 0); // Closing the native dialog also settles the action.
  decision = true;
  await setup.openAccountMappings({name:'connection', enabled:1});
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['pause', {connection:'connection'}], ['load']]);
  assert.ok(confirmations.every(message => /paus/i.test(message)));
  calls.length = 0;
  decision = false;
  await setup.pauseFeed({name:'connection'});
  assert.equal(calls.length, 0);
  decision = true;
  await setup.pauseFeed({name:'connection'});
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [['pause', {connection:'connection'}], ['load']]);
  calls.length = 0;
  await setup.saveMappingProgress({name:'connection'}, [], 'UTC', skipped);
  assert.equal(calls[0][0], 'save_mappings');
  assert.deepEqual(JSON.parse(calls[0][1].selections), []);
  assert.deepEqual(JSON.parse(calls[0][1].skipped_accounts), [{account_id:'unidentified',currency:'GBP'}]);
  await setup.saveMappingProgress({name:'connection'}, chosen, 'UTC', skipped);
  assert.equal(calls[1][0], 'save_mappings');
  assert.ok(!calls.some(call => call[0] === 'activate'));
  console.log('Pause confirmations, dismissal and persisted skip selections checks passed');
  checkDashboardGroups();
  checkConnectionFormGroups();
})().catch(error => { console.error(error); process.exitCode = 1; });
