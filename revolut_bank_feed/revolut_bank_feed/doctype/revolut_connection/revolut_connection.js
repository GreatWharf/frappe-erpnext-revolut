frappe.ui.form.on('Revolut Connection', {
  refresh(frm) {
    frm.add_custom_button(__('Guided setup'), () => frappe.set_route('revolut-setup'));
    if (frm.is_new()) return;
    const call = (method, args = {}) => frappe.call({
      method: `revolut_bank_feed.api.${method}`,
      args: {connection: frm.doc.name, ...args}, freeze: true,
    });
    const saved = () => {
      if (frm.is_dirty()) { frappe.msgprint(__('Save your changes first.')); return false; }
      return true;
    };
    frm.add_custom_button(__('Load Private Key'), () => {
      if (!saved()) return;
      const input = document.createElement('input');
      input.type = 'file'; input.accept = '.pem';
      input.onchange = async () => {
        const file = input.files[0];
        if (!file || file.size > 16000) return frappe.msgprint(__('Choose a PEM file under 16 KB.'));
        const pem = await file.text();
        await call('set_private_key', {encoded_key: btoa(pem)});
        await frm.reload_doc();
        frappe.show_alert(__('Private key stored encrypted.'));
      };
      input.click();
    }, __('Authorization'));
    frm.add_custom_button(__('Authorize READ Access'), async () => {
      if (!saved()) return;
      const result = await call('get_authorization_url');
      const url = frappe.utils.escape_html(result.message);
      frappe.msgprint({title: __('Authorize in Revolut'),
        message: `<p>${__('Open Revolut, authorize READ access, then copy the code from the redirected URL. Codes expire after two minutes.')}</p><p><a href="${url}" target="_blank" rel="noopener noreferrer">${__('Open Revolut consent')}</a></p>`});
    }, __('Authorization'));
    frm.add_custom_button(__('Exchange Authorization Code'), () => {
      if (!saved()) return;
      frappe.prompt([{fieldname: 'code', fieldtype: 'Password', label: __('Authorization Code'), reqd: 1}],
        async values => { await call('exchange_code', values); await frm.reload_doc(); },
        __('Exchange Authorization Code'));
    }, __('Authorization'));
    frm.add_custom_button(__('Discover Accounts'), async () => {
      if (!saved()) return;
      const result = await call('discover_accounts');
      const esc = frappe.utils.escape_html;
      const rows = result.message.map(row => `<tr><td>${esc(row.name || '')}</td><td>${esc(row.id)}</td><td>${esc(row.currency)}</td><td>${esc(row.state || '')}</td></tr>`).join('');
      frappe.msgprint({title: __('Revolut Accounts'), wide: true,
        message: `<p>${__('Copy an account ID into a Revolut Account Map for this connection.')}</p><table class="table table-bordered"><thead><tr><th>${__('Name')}</th><th>${__('Account ID')}</th><th>${__('Currency')}</th><th>${__('State')}</th></tr></thead><tbody>${rows}</tbody></table>`});
    });
    frm.add_custom_button(__('Account Mappings'), () => frappe.set_route('List', 'Revolut Account Map', {connection: frm.doc.name}));
    frm.add_custom_button(__('Sync Now'), async () => {
      if (!saved()) return;
      await call('sync_now'); frappe.show_alert(__('Sync queued. Check Sync Logs for results.'));
    });
    frm.add_custom_button(__('Historical Backfill'), () => {
      if (!saved()) return;
      frappe.prompt([
        {fieldname: 'from_date', fieldtype: 'Date', label: __('From'), reqd: 1, default: frm.doc.historical_from},
        {fieldname: 'through_date', fieldtype: 'Date', label: __('Through (inclusive)'), reqd: 1, default: frappe.datetime.get_today()},
      ], async values => { await call('start_backfill', values); await frm.reload_doc(); }, __('Historical Backfill'));
    });
    frm.add_custom_button(__('Sync Logs'), () => frappe.set_route('List', 'Revolut Sync Log', {connection: frm.doc.name}));
    frm.add_custom_button(__('Source Reviews'), () => frappe.set_route('List', 'Revolut Source Transaction', {connection: frm.doc.name, needs_review: 1}));
  },
});
