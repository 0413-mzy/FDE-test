import test from 'node:test';
import assert from 'node:assert/strict';
import * as helpers from '../.test-output/helpers.js';

test('manual logistics offers only valid current-state and recovery actions', () => {
  assert.equal(typeof helpers.logisticsActions, 'function');
  const actions = state => helpers.logisticsActions(state).map(a => `${a.kind}:${a.reason ?? ''}`);
  assert.deepEqual(actions({status:'SHIPPED'}), ['COLLECTED:']);
  assert.deepEqual(actions({status:'COLLECTED'}), ['IN_TRANSIT:', 'EXCEPTION:TRANSPORT_DELAY']);
  assert.deepEqual(actions({status:'IN_TRANSIT'}), ['IN_TRANSIT:', 'OUT_FOR_DELIVERY:', 'EXCEPTION:TRANSPORT_DELAY']);
  assert.deepEqual(actions({status:'OUT_FOR_DELIVERY'}), ['DELIVERED:', 'EXCEPTION:DELIVERY_FAILED']);
  assert.deepEqual(actions({status:'EXCEPTION',exception_reason:'TRANSPORT_DELAY',exception_from_status:'COLLECTED'}), ['COLLECTED:']);
  assert.deepEqual(actions({status:'EXCEPTION',exception_reason:'DELIVERY_FAILED'}), ['OUT_FOR_DELIVERY:']);
  assert.deepEqual(actions({status:'EXCEPTION'}), ['IN_TRANSIT:']);
  assert.deepEqual(actions({status:'DELIVERED'}), []);
});

test('default occurrence uses submit time and stored event creates an exact safe replay', () => {
  assert.equal(typeof helpers.logisticsPayload, 'function');
  const at = new Date('2026-10-08T09:10:11.123Z');
  const payload = helpers.logisticsPayload(3, {kind:'IN_TRANSIT',reason:null}, 'Depot transfer', 'Depot A', '', at, 'fixed-event');
  assert.deepEqual(payload, {expected_version:3,event_id:'fixed-event',kind:'IN_TRANSIT',reason:null,description:'Depot transfer',location:'Depot A',occurred_at:at.toISOString()});
  assert.equal(typeof helpers.logisticsReplay, 'function');
  const stored = {...payload,request_version:3,created_at:'2026-10-08T09:10:12Z',status_applied:true};
  assert.deepEqual(helpers.logisticsReplay(stored), payload);
  assert.equal(helpers.logisticsReplay({...stored,request_version:null}), null);
  assert.equal(helpers.logisticsReplay({...stored,kind:'SHIPPED'}), null);
  assert.equal(helpers.logisticsPayload(3,{kind:'COLLECTED'},'collected','','2026-10-08T10:00:00',at,'late').occurred_at,new Date('2026-10-08T10:00:00').toISOString());
});

test('refresh keeps parcel state through success and read failure only for the same account and parcel', () => {
  assert.equal(typeof helpers.queryRefreshState, 'function');
  const client = {}, otherClient = {}, shipment = {id:'parcel-a',version:2};
  const snapshot = {data:shipment,loading:false,client,path:'/demo/shipments/parcel-a'};
  const refreshing = helpers.queryRefreshState(snapshot, client, snapshot.path, true);
  assert.equal(refreshing.data, shipment);
  assert.equal(refreshing.loading, true);
  const failure = new Error('read unavailable');
  const failed = helpers.queryRefreshState(refreshing, client, snapshot.path, true, failure);
  assert.equal(failed.data, shipment);
  assert.equal(failed.error, failure);
  assert.equal(failed.loading, false);
  assert.equal(helpers.queryRefreshState(snapshot, client, '/demo/shipments/parcel-b', true).data, undefined);
  assert.equal(helpers.queryRefreshState(snapshot, otherClient, snapshot.path, true).data, undefined);
  assert.equal(helpers.queryRefreshState(snapshot, client, snapshot.path, false).data, undefined);
});
