frappe.ui.form.on('Revolut FX Quote', {
  refresh(frm) {
    frm.set_intro(__('Indicative sell quote for one unit, with fee shown separately. This is not the historical rate applied to a transaction. Currency Exchange applies site-wide across Companies.'),'blue');
    frm.add_custom_button(__('Use in Currency Exchange'),()=>frappe.confirm(
      __('Create a site-wide Currency Exchange record from this quote? Existing rates will not be overwritten.'),async()=>{
        const result=await frappe.call({method:'revolut_bank_feed.enrichment_api.use_quote',args:{name:frm.doc.name},freeze:true});
        frappe.set_route('Form','Currency Exchange',result.message.name);
      }));
  }
});
