import test from 'node:test';
import assert from 'node:assert/strict';
import * as helpers from '../.test-output/helpers.js';
const line = {id:'a',quantity:5,shipped_qty:3,refunded_unshipped_qty:1,refunded_shipped_qty:1};
test('terminal cases do not block address, receipt or a new application',()=>{
 assert.equal(helpers.hasActiveCase?.({after_sale_cases:[{state:'COMPLETED'},{state:'REJECTED'},{state:'CANCELLED'}]}),false);
 assert.equal(helpers.hasActiveCase?.({after_sale_cases:[{state:'REFUND_PENDING'}]}),true);
});
test('partial refund quantity excludes already refunded or shipped goods',()=>{
 assert.equal(helpers.refundableQuantity?.({shipments:[]},line,'UNSHIPPED_REFUND'),1);
});
test('return requires every shipment covering the line delivered within inclusive 14 days',()=>{
 const now = Date.parse('2026-10-20T00:00:00Z');
 const shipment = {status:'DELIVERED',delivered_at:'2026-10-06T00:00:00Z',lines:[{order_line_id:'a',quantity:3}]};
 assert.equal(helpers.refundableQuantity?.({shipments:[shipment]},line,'RETURN_REFUND',now),2);
 assert.equal(helpers.refundableQuantity?.({shipments:[shipment]},line,'RETURN_REFUND',now+1),0);
 assert.equal(helpers.refundableQuantity?.({shipments:[shipment,{...shipment,status:'IN_TRANSIT'}]},line,'RETURN_REFUND',now),0);
});
