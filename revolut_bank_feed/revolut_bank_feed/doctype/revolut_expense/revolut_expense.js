frappe.ui.form.on('Revolut Expense', {
  refresh(frm) {
    const call=(method,args={}) => frappe.call({method:`revolut_bank_feed.enrichment_api.${method}`,args:{name:frm.doc.name,...args},freeze:true});
    frm.add_custom_button(__('Refresh expense and receipts'),async()=>{await call('refresh_expense');await frm.reload_doc();});
    if(frm.doc.source_transaction) frm.add_custom_button(__('Bank source'),()=>frappe.set_route('Form','Revolut Source Transaction',frm.doc.source_transaction));
    frm.add_custom_button(__('Link accounting document'),()=>frappe.prompt([
      {fieldname:'target_doctype',fieldtype:'Select',label:__('Document type'),options:'Purchase Invoice\nExpense Claim',reqd:1},
      {fieldname:'target_name',fieldtype:'Dynamic Link',options:'target_doctype',label:__('Document'),reqd:1}
    ],async values=>{await call('link_expense',values);await frm.reload_doc();},__('Link existing record')));
    if(frm.doc.accounting_review_required) frappe.msgprint(__('Revolut expense evidence changed after linking. Review your accounting document, then link it again to acknowledge.'));
    const esc=value=>frappe.utils.escape_html(String(value ?? ''));
    const data=JSON.parse(frm.doc.data || '{}');
    const rows=(data.splits || []).map(s=>`<tr><td>${esc(s.category?.name)}</td><td>${esc(s.amount?.amount)} ${esc(s.amount?.currency)}</td><td>${esc(s.tax_rate?.name)} ${esc(s.tax_rate?.percentage)}%</td></tr>`).join('');
    const labels=Object.entries(data.labels || {}).map(([key,values])=>`${esc(key)}: ${esc(Array.isArray(values)?values.join(', '):values)}`).join('<br>');
    frm.set_intro(`${__('Imported evidence. Link your accounting document after review; this does not create a reimbursement or post to the ledger.')}<table class="table"><thead><tr><th>${__('Category')}</th><th>${__('Amount')}</th><th>${__('Tax')}</th></tr></thead><tbody>${rows}</tbody></table>${labels}`,'blue');
  }
});
