frappe.ui.form.on('Revolut Source Transaction', {
  refresh(frm) {
    frm.add_custom_button(__('Source Legs'), () => frappe.set_route('List', 'Revolut Source Leg', {source_transaction: frm.doc.name}));
    frm.add_custom_button(__('Source History'), () => frappe.set_route('List', 'Revolut Source Revision', {source_transaction: frm.doc.name}));
    if (!frm.doc.needs_review || !frappe.user.has_role('System Manager')) return;
    frm.add_custom_button(__('Review and Apply'), () => {
      frappe.prompt([{fieldname: 'note', fieldtype: 'Small Text', label: __('Review Note'), reqd: 1,
        description: __('This fetches the current bank record. Changed or reverted imported rows are cancelled and replaced when appropriate. Remove reconciliation links first. No accounting vouchers are changed.')}],
      async values => {
        const result = await frappe.call({method: 'revolut_bank_feed.api.review_and_apply',
          args: {source_transaction: frm.doc.name, note: values.note}, freeze: true});
        await frm.reload_doc();
        frappe.msgprint(result.message.review ? __('Review remains unresolved. Check the reason and account mappings.') : __('Review applied.'));
      }, __('Review and Apply'));
    });
  },
});
