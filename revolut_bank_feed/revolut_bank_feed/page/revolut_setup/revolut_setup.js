/* Guided setup uses native Desk controls; secrets are never saved in browser storage. */
frappe.pages['revolut-setup'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: __('Connect Revolut'), single_column: true});
  wrapper.revolut_setup = new RevolutSetup(page);
};
frappe.pages['revolut-setup'].on_page_show = function (wrapper) {
  wrapper.revolut_setup?.load();
};

class RevolutSetup {
  constructor(page) {
    this.page = page;
    this.connection = null;
    this.initial = true;
    this.busy = false;
    page.main.addClass('revolut-setup');
    page.add_inner_button(__('Advanced settings'), () => {
      frappe.set_route('List', 'Revolut Connection');
    });
    if (!document.getElementById('revolut-setup-styles')) {
      $('<style id="revolut-setup-styles">').text(`
        .revolut-setup {max-width:1000px;margin:0 auto;padding:24px 16px 56px;}
        .revolut-setup .rb-top {display:flex;gap:16px;justify-content:space-between;align-items:center;margin-bottom:24px;flex-wrap:wrap;}
        .revolut-setup .rb-top h2 {font-size:22px;font-weight:650;letter-spacing:-.02em;margin:0 0 6px;}
        .revolut-setup .rb-muted {color:var(--text-muted);line-height:1.6;}
        .revolut-setup .rb-steps {display:flex;padding:0;list-style:none;border-bottom:1px solid var(--border-color);margin:0 0 24px;}
        .revolut-setup .rb-steps li {flex:1;padding:12px 4px;color:var(--text-muted);border-bottom:3px solid transparent;font-size:13px;}
        .revolut-setup .rb-steps li[aria-current=step] {color:var(--primary);border-color:var(--primary);font-weight:600;}
        .revolut-setup .rb-card {background:var(--card-bg);border:1px solid var(--border-color);border-radius:12px;padding:28px;}
        .revolut-setup .rb-card h3 {font-size:19px;margin:0 0 10px;}
        .revolut-setup .rb-fields {max-width:520px;margin-top:22px;}
        .revolut-setup .rb-actions {display:flex;gap:10px;flex-wrap:wrap;margin-top:24px;}
        .revolut-setup .rb-note {padding:14px 16px;background:var(--subtle-fg);border-radius:8px;margin-top:20px;line-height:1.6;}
        .revolut-setup .rb-error {padding:14px;border:1px solid var(--red-300);border-radius:8px;margin-bottom:16px;}
        .revolut-setup pre {white-space:pre-wrap;word-break:break-all;max-height:180px;overflow:auto;font-size:12px;}
        .revolut-setup .rb-table {width:100%;margin:16px 0;}
        .revolut-setup .rb-table th,.revolut-setup .rb-table td {padding:14px 10px;border-bottom:1px solid var(--border-color);text-align:left;vertical-align:middle;}
        .revolut-setup .rb-table td:first-child {padding-left:0;}
        .revolut-setup .rb-table .form-group {margin:0;}
        .revolut-setup .rb-status {display:flex;gap:32px;flex-wrap:wrap;padding:16px 0;}
        .revolut-setup .rb-status strong {display:block;font-size:16px;margin-top:4px;}
        .revolut-setup button:focus-visible,.revolut-setup a:focus-visible {outline:2px solid var(--primary);outline-offset:3px;}
        @media(max-width:640px) {.revolut-setup .rb-card{padding:18px}.revolut-setup .rb-steps li{font-size:11px}.revolut-setup .rb-table th,.revolut-setup .rb-table td{padding:10px 4px}.revolut-setup .rb-status{gap:16px}}
      `).appendTo(document.head);
    }
  }
  esc(value) { return frappe.utils.escape_html(String(value ?? '')); }
  async call(method, args = {}, api = 'setup') {
    const response = await frappe.call({method: `revolut_bank_feed.${api}.${method}`, args});
    return response.message;
  }
  control(parent, fieldname, fieldtype, label, options = {}) {
    return frappe.ui.form.make_control({parent, df: {fieldname, fieldtype, label: __(label), ...options}, render_input: true});
  }
  action(parent, label, fn, primary = false) {
    const button = $('<button type="button">').addClass(`btn ${primary ? 'btn-primary' : 'btn-default'}`).text(__(label)).appendTo(parent);
    button.on('click', async () => {
      if (this.busy) return;
      this.busy = true; button.prop('disabled', true); this.page.main.find('.rb-error').remove();
      try { await fn(); }
      catch (error) {
        // Frappe displays server validation messages. Keep this inline guidance free of tokens/payloads.
        $('<div class="rb-error" role="alert">').text(__('This step did not finish. Check the message above, correct the details and try again. Your saved progress is safe.')).prependTo(this.page.main.find('.rb-card'));
      } finally { this.busy = false; button.prop('disabled', false); }
    });
    return button;
  }
  async load() {
    const data = await this.call('overview', this.connection ? {connection: this.connection} : {});
    this.data = data;
    const initial = this.initial; this.initial = false;
    if (initial && !this.connection && data.connections.length === 1) {
      this.connection = data.connections[0].name;
      return this.load();
    }
    this.page.main.empty();
    const top = $('<div class="rb-top">').appendTo(this.page.main);
    $('<div>').html(`<h2>${__('Your Revolut bank feed')}</h2><div class="rb-muted">${__('Connect accounts once. Review transactions in ERPNext.')}</div>`).appendTo(top);
    const selector = $('<select class="form-control" aria-label="Revolut connection">').css('max-width','300px').appendTo(top);
    $('<option>').val('').text(__('New connection')).appendTo(selector);
    data.connections.forEach(c => $('<option>').val(c.name).text(`${c.connection_name} · ${c.company}`).appendTo(selector));
    selector.val(this.connection || '').on('change', () => { this.connection = selector.val() || null; this.load(); });
    const doc = data.connection;
    const step = !doc ? 0 : !doc.has_private_key && !doc.authorized ? 1 : !doc.authorized ? 2 : doc.enabled ? 4 : 3;
    if (step < 4) {
      const steps = $('<ol class="rb-steps" aria-label="Setup progress">').appendTo(this.page.main);
      ['Company', 'Certificate', 'Connect', 'Accounts'].forEach((title, i) => {
        const li = $('<li>').text(`${i + 1}. ${__(title)}`).appendTo(steps);
        if (i === step) li.attr('aria-current', 'step');
      });
    }
    this.card = $('<section class="rb-card">').appendTo(this.page.main);
    if (step === 0) this.company();
    else if (step === 1) this.certificate(doc);
    else if (step === 2) this.connect(doc);
    else if (step === 3) await this.accounts(doc);
    else this.dashboard(doc);
  }
  intro(title, text) {
    $('<h3>').text(__(title)).appendTo(this.card);
    $('<p class="rb-muted">').text(__(text)).appendTo(this.card);
  }
  company() {
    this.intro('Start with your company', 'Choose the company that owns this Revolut Business account. You can add another connection for another company later.');
    const fields = $('<div class="rb-fields">').appendTo(this.card);
    const company = this.control(fields, 'company', 'Select', 'Company', {options: [''].concat(this.data.companies), reqd: 1});
    const environment = this.control(fields, 'environment', 'Select', 'Revolut account', {options: ['Sandbox', 'Production']});
    environment.set_value('Sandbox');
    const date = this.control(fields, 'historical_from', 'Date', 'Import transactions from', {reqd: 1});
    date.set_value(frappe.datetime.add_days(frappe.datetime.get_today(), -30));
    $('<div class="rb-note">').text(__('Sandbox is for testing. Choose Production for your real Business account. Start with a short period so you can compare it with a statement.')).appendTo(this.card);
    this.action($('<div class="rb-actions">').appendTo(this.card), 'Continue', async () => {
      if (!company.get_value() || !date.get_value()) return frappe.msgprint(__('Choose a company and start date.'));
      const doc = await this.call('create_connection', {company: company.get_value(), environment: environment.get_value(), historical_from: date.get_value()});
      this.connection = doc.name; await this.load();
    }, true);
  }
  certificate(doc) {
    this.intro('Create your connection certificate', 'ERPNext will generate the certificate Revolut needs. Your private key stays encrypted on this server; you only copy the public certificate.');
    $('<div class="rb-note">').text(__('No terminal commands or key files to manage. Keep your normal ERPNext backups, including the site encryption key.')).appendTo(this.card);
    this.action($('<div class="rb-actions">').appendTo(this.card), 'Generate certificate', async () => {
      await this.call('generate_certificate', {connection: doc.name}); await this.load();
    }, true);
  }
  connect(doc) {
    this.intro('Allow Revolut to share transactions', 'Register the certificate in Revolut, then approve read-only access. You will return here to finish the connection.');
    const host = doc.environment === 'Production' ? 'business.revolut.com' : 'sandbox-business.revolut.com';
    $('<p>').html(`<strong>${__('1. Register the certificate')}</strong><br>${__('In Revolut, open Settings → APIs → Business API → Add API certificate.')}`).appendTo(this.card);
    const link = $('<a target="_blank" rel="noopener noreferrer">').attr('href', `https://${host}`).text(__('Open Revolut Business')).appendTo(this.card);
    link.addClass('btn btn-default');
    if (doc.public_certificate) {
      $('<pre>').text(doc.public_certificate).appendTo(this.card);
      this.action($('<div class="rb-actions">').appendTo(this.card), 'Copy public certificate', async () => {
        await navigator.clipboard.writeText(doc.public_certificate); frappe.show_alert(__('Public certificate copied.'));
      });
    }
    $('<p class="rb-muted">').css('margin-top','18px').text(__('Use this exact redirect address when Revolut asks for it:')).appendTo(this.card);
    const redirect = $('<input class="form-control" readonly aria-label="Redirect address">').val(doc.redirect_uri).appendTo(this.card);
    redirect.on('focus', () => redirect[0].select());
    this.action($('<div class="rb-actions">').appendTo(this.card), 'Copy redirect address', () => navigator.clipboard.writeText(doc.redirect_uri));
    const fields = $('<div class="rb-fields">').appendTo(this.card);
    const client = this.control(fields, 'client_id', 'Data', 'Client ID shown by Revolut', {reqd: 1});
    client.set_value(doc.client_id === 'pending-setup' ? '' : doc.client_id);
    this.action($('<div class="rb-actions">').appendTo(this.card), 'Save Client ID', async () => {
      await this.call('save_client_id', {connection: doc.name, client_id: client.get_value()}); await this.load();
    });
    if (doc.client_id === 'pending-setup') return;
    $('<hr>').appendTo(this.card);
    $('<p>').html(`<strong>${__('2. Approve read-only access')}</strong><br>${__('Open the consent page below and authorize access. No payment permission is requested.')}`).appendTo(this.card);
    this.action($('<div class="rb-actions">').appendTo(this.card), 'Open Revolut authorization', async () => {
      // Open synchronously to avoid popup blockers after the awaited server call.
      const popup = window.open('about:blank', '_blank');
      if (popup) popup.opener = null;
      try {
        const url = await this.call('get_authorization_url', {connection: doc.name}, 'api');
        if (popup) popup.location.href = url;
        else frappe.msgprint(`<a href="${this.esc(url)}" target="_blank" rel="noopener noreferrer">${__('Open authorization')}</a>`);
      } catch (error) { if (popup) popup.close(); throw error; }
    }, true);
    $('<p class="rb-muted">').css('margin-top','20px').text(__('After approval, copy the full address of the page Revolut opens and paste it below. The code lasts two minutes.')).appendTo(this.card);
    const pasted = this.control($('<div class="rb-fields">').appendTo(this.card), 'pasted', 'Password', 'Redirected address or authorization code', {reqd: 1});
    this.action($('<div class="rb-actions">').appendTo(this.card), 'Connect account', async () => {
      const value = pasted.get_value();
      try { await this.call('connect_from_paste', {connection: doc.name, pasted_value: value}); }
      finally { pasted.set_value(''); }
      await this.load();
    }, true);
  }
  async accounts(doc) {
    this.intro('Choose where transactions go', 'Your Revolut accounts are listed below. Match each one to an ERPNext Bank Account in the same currency.');
    const options = await this.call('account_options', {connection: doc.name});
    const fields = $('<div class="rb-fields">').appendTo(this.card);
    const timezone = this.control(fields, 'timezone', 'Data', 'Statement timezone', {reqd: 1});
    timezone.set_value(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
    const table = $('<table class="rb-table"><thead><tr><th></th><th></th><th></th></tr></thead><tbody></tbody></table>').appendTo(this.card);
    table.find('th').eq(0).text(__('Revolut account')); table.find('th').eq(1).text(__('Currency')); table.find('th').eq(2).text(__('ERPNext Bank Account'));
    const selections = [];
    options.accounts.forEach((account, index) => {
      const row = $('<tr>').appendTo(table.find('tbody'));
      $('<td>').text(account.name || account.id).appendTo(row);
      $('<td>').text(account.currency).appendTo(row);
      const cell = $('<td>').appendTo(row);
      const existing = this.data.maps.find(m => m.account_id === account.id && m.currency === account.currency);
      const choices = options.bank_accounts.filter(b => b.currency === account.currency).map(b => b.name);
      const control = this.control(cell, `bank_${index}`, 'Select', `Bank Account (${account.currency})`, {options: [''].concat(choices), reqd: 1});
      if (existing) { control.set_value(existing.bank_account); control.df.read_only = 1; control.refresh(); }
      selections.push({account, control});
    });
    if (!options.accounts.length) $('<p>').text(__('Revolut returned no accounts. Check the Business account and environment.')).appendTo(this.card);
    $('<div class="rb-note">').text(__('Choose all accounts for a complete feed. Fees initially go to review until you confirm their statement treatment. Existing mapping currencies and dates stay fixed. Use Advanced settings to exclude accounts or adjust fee rules.')).appendTo(this.card);
    const actions = $('<div class="rb-actions">').appendTo(this.card);
    this.action(actions, 'Create an ERPNext Bank Account', () => this.newBank(doc));
    this.action(actions, 'Save accounts and start sync', async () => {
      if (!selections.length || selections.some(s => !s.control.get_value())) return frappe.msgprint(__('Select an ERPNext Bank Account for every listed currency account.'));
      const rows = selections.map(s => ({account_id: s.account.id, currency: s.account.currency, bank_account: s.control.get_value()}));
      await this.call('save_mappings', {connection: doc.name, selections: JSON.stringify(rows), timezone: timezone.get_value()});
      await this.call('activate', {connection: doc.name}); await this.load();
    }, true);
    if (this.data.maps.length) this.action(actions, 'Resume existing feed', async () => {
      await this.call('activate', {connection: doc.name}); await this.load();
    });
  }
  newBank(doc) {
    const dialog = new frappe.ui.Dialog({title: __('Create Bank Account'), fields: [
      {fieldname: 'account_name', fieldtype: 'Data', label: __('Account name'), reqd: 1, default: 'Revolut'},
      {fieldname: 'ledger', fieldtype: 'Link', options: 'Account', label: __('Bank ledger'), reqd: 1,
        description: __('Select a bank ledger in the correct currency. You can create one from this field if your accounting permissions allow it.'),
        get_query: () => ({filters: {company: doc.company, account_type: 'Bank', is_group: 0, disabled: 0}})},
    ], primary_action_label: __('Create Bank Account'), primary_action: async values => {
      dialog.disable_primary_action();
      try { await this.call('create_bank_account', {connection: doc.name, ...values}); dialog.hide(); await this.load(); }
      finally { dialog.enable_primary_action(); }
    }});
    dialog.show();
  }
  dashboard(doc) {
    this.intro('Your bank feed is connected', 'New transactions are imported in the background. Reconcile them with your accounting records in ERPNext.');
    const status = $('<div class="rb-status">').appendTo(this.card);
    [[__('Connection'), doc.connection_name], [__('Last result'), doc.last_status || __('First sync queued')],
      [__('Needs review'), this.data.reviews || 0]].forEach(([label, value]) => {
      $('<div>').html(`<span class="rb-muted">${this.esc(label)}</span><strong>${this.esc(value)}</strong>`).appendTo(status);
    });
    if (!this.data.scheduler_enabled) $('<div class="rb-error" role="alert">').text(__('The scheduler is disabled. Ask your Docker administrator to enable the site scheduler. Manual Sync Now still needs a running worker.')).appendTo(this.card);
    if (doc.last_error_code) $('<div class="rb-note">').text(`${__('Sync needs attention:')} ${doc.last_error_code}. ${__('Open Sync Logs for details.')}`).appendTo(this.card);
    const actions = $('<div class="rb-actions">').appendTo(this.card);
    this.action(actions, 'Sync now', async () => { await this.call('sync_now', {connection: doc.name}, 'api'); frappe.show_alert(__('Sync queued.')); }, true);
    this.action(actions, 'Refresh status', () => this.load());
    this.action(actions, 'Bank transactions', () => frappe.set_route('List', 'Bank Transaction', {company: doc.company}));
    this.action(actions, 'Review transactions', () => frappe.set_route('List', 'Revolut Source Transaction', {connection: doc.name, needs_review: 1}));
    this.action(actions, 'Sync logs', () => frappe.set_route('List', 'Revolut Sync Log', {connection: doc.name}));
    this.action(actions, 'Import older transactions', () => {
      frappe.prompt([{fieldname: 'from_date', fieldtype: 'Date', label: __('From'), reqd: 1, default: doc.historical_from},
        {fieldname: 'through_date', fieldtype: 'Date', label: __('Through'), reqd: 1, default: frappe.datetime.get_today()}],
        async values => { await this.call('start_backfill', {connection: doc.name, ...values}, 'api'); await this.load(); }, __('Historical import'));
    });
    this.action(actions, 'Choose extra data', () => {
      const production = doc.environment === 'Production';
      frappe.prompt([
        {fieldname:'sync_fx', fieldtype:'Check', label:__('Daily FX quotes'), default:doc.sync_fx || 0},
        {fieldname:'sync_expenses', fieldtype:'Check', label:__('Expenses (Production only)'), default:doc.sync_expenses || 0, read_only:!production},
        {fieldname:'sync_receipts', fieldtype:'Check', label:__('Private receipts (enable expenses too)'), default:doc.sync_receipts || 0, read_only:!production},
        {fieldname:'sync_catalogs', fieldtype:'Check', label:__('Categories, tax rates and labels'), default:doc.sync_catalogs || 0}
      ], async values => { await this.call('configure', {connection:doc.name,...values}, 'enrichment_api'); await this.load(); }, __('Read-only imports'));
    });
    this.action(actions, 'Refresh extra data', async () => { await this.call('sync_now', {connection:doc.name}, 'enrichment_api'); frappe.show_alert(__('Extra data sync queued.')); });
    [['Accounts and balances','Revolut Account Snapshot'],['Expenses and receipts','Revolut Expense'],
      ['FX quotes','Revolut FX Quote'],['Categories and taxes','Revolut Reference']].forEach(([label,type]) =>
      this.action(actions,label,() => frappe.set_route('List',type,{connection:doc.name})));
    $('<p class="rb-muted">').text(`${__('Extra data:')} ${doc.extras_last_status || __('Hourly refresh pending')} ${doc.extras_error_code || ''}`).appendTo(this.card);
    this.action(actions, 'Pause feed', async () => { await this.call('pause', {connection: doc.name}); await this.load(); });
    $('<p class="rb-muted">').css('margin-top', '22px').text(`${__('Last successful run:')} ${doc.last_success_at || __('Waiting for the worker')}`).appendTo(this.card);
  }
}
