import test from 'node:test';
import assert from 'node:assert/strict';
import { demoPolicy } from '../.test-output/helpers.js';

test('unknown public configuration cannot expose account mutation forms', () => {
    assert.deepEqual(demoPolicy(), { publicDemo: false, allowAccountWrites: false });
});
test('public demo keeps shared accounts immutable regardless of advertised credentials', () => {
    assert.deepEqual(demoPolicy({ enabled: true, accounts: ['customer.a'], password: 'public-fixture-only' }), { publicDemo: true, allowAccountWrites: false });
});
test('confirmed ordinary environment retains registration and account editing', () => {
    assert.deepEqual(demoPolicy({ enabled: false, accounts: [], password: null }), { publicDemo: false, allowAccountWrites: true });
});
