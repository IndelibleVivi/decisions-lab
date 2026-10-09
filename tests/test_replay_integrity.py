"""Replay must derive judgments from the suite, not trust editable summaries."""
import unittest
from pathlib import Path
from decision_lab.cases import load_suite
from decision_lab.record import RecordError, evaluate, run_baseline, run_demo, threshold_coverage

SUITE=Path(__file__).resolve().parents[1]/'experiments/next-action/cases.json'

class ReplayIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.suite=load_suite(SUITE)
        self.record=run_baseline(self.suite,suite_path=str(SUITE))

    def test_correctness_flag_cannot_inflate_score(self):
        row=next(r for r in self.record.results if r.correct is False)
        row.correct=True
        with self.assertRaises(RecordError): evaluate(self.record,self.suite)

    def test_split_cannot_move_a_test_result_into_dev(self):
        row=next(r for r in self.record.results if r.split=='test')
        row.split='dev'
        with self.assertRaises(RecordError): evaluate(self.record,self.suite)

    def test_source_group_cannot_be_relabelled(self):
        self.record.results[0].source_group='unrelated-source'
        with self.assertRaises(RecordError): evaluate(self.record,self.suite)

    def test_baseline_cannot_impersonate_a_provider(self):
        self.record.route='jev'
        self.record.native_model='jev-1.13.0'
        with self.assertRaises(RecordError): evaluate(self.record,self.suite)

    def test_unknown_is_not_threshold_coverage(self):
        record=run_demo(self.suite,suite_path=str(SUITE))
        report=threshold_coverage(record,threshold=0)
        self.assertEqual(report['covered'],len(self.suite.cases)-1)

if __name__=='__main__': unittest.main()
