frappe.ui.form.on('Revolut Account Map', {
  setup(frm) {
    frm.set_query('bank_account', () => ({filters: {company: frm.doc.company, is_company_account: 1, disabled: 0}}));
  },
  async connection(frm) {
    if (frm.doc.connection) {
      const result = await frappe.db.get_value('Revolut Connection', frm.doc.connection, 'company');
      await frm.set_value('company', result.message.company);
    }
  },
});
