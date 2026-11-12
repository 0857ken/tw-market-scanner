"""Guard the exact approved source bytes, date coverage and price predicates."""
import json
import unittest

from scripts.build_rebound_snapshot import DATES, OUTPUT, build, public_signals


class PublicReboundTest(unittest.TestCase):
    def test_pinned_csvs_reproduce_asset_and_all_eight_checks(self):
        data = build()
        self.assertEqual(json.loads(OUTPUT.read_bytes()), data)
        self.assertEqual(tuple(row['date'] for row in data['rows']), DATES)
        self.assertEqual({source['id'] for source in data['sources']}, {'11755', '11672'})
        self.assertEqual(len(data['checks']), 8)
        for check in data['checks']:
            self.assertTrue(check['match'])
            self.assertEqual(check['ohlc_close'], check['turnover_close'])

    def test_missing_history_is_distinct_from_false(self):
        data = build()
        states = data['signals']
        self.assertTrue(all(value is None for value in states[0].values()))
        self.assertTrue(all(state['down4'] is None for state in states[:4]))
        self.assertIs(states[4]['down4'], True)
        self.assertIs(states[5]['down4'], False)
        self.assertEqual([row['date'] for row, state in zip(data['rows'], states)
                          if state['day_drop3'] is True], [DATES[i] for i in (1, 3, 4)])
        for state in states:
            self.assertEqual(len(state), 15)
            self.assertTrue(all(value is None for key, value in state.items()
                                if key not in ('day_drop3', 'lower_wick', 'down4')))

    def test_lower_wick_requires_both_conditions(self):
        prev = {'close': 100}
        qualified = {'open': 100, 'close': 97, 'low': 95.8}
        self.assertIs(public_signals([prev, qualified], 1)['lower_wick'], True)
        self.assertIs(public_signals([prev, {**qualified, 'low': 96}], 1)['lower_wick'], False)
        self.assertIs(public_signals([prev, {**qualified, 'close': 101}], 1)['lower_wick'], False)
