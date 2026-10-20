"""Unittest discovery plus machine-readable 4C-2B evidence; no network or deployment."""
import argparse
import json
from pathlib import Path
import unittest

EXPECTED = {prefix+str(n).zfill(2) for prefix, count in [('B',8),('A',5),('C',5),('P',10),('L',5),('R',5),('G',4),('W',3)] for n in range(1,count+1)}


class MatrixResult(unittest.TextTestResult):
    matrix = None

    def startTestRun(self):
        self.matrix = {}
        super().startTestRun()

    def record(self, test, status):
        ids = getattr(getattr(test, getattr(test, '_testMethodName', ''), None), 'matrix_ids', ())
        for i in ids:
            self.matrix.setdefault(i, []).append({'test': test.id(), 'status': status})

    def addSuccess(self, test):
        super().addSuccess(test); self.record(test, 'PASS')

    def addError(self, test, err):
        super().addError(test, err); self.record(test, 'FAIL')

    def addFailure(self, test, err):
        super().addFailure(test, err); self.record(test, 'FAIL')

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.record(test, 'BLOCKED')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None: self.record(test, 'FAIL')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true', help='Include all pre-existing Python regressions')
    parser.add_argument('--output', type=Path, default=Path('test-results/stage4c2b-matrix.json'))
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover('tests') if args.all else unittest.defaultTestLoader.loadTestsFromNames(['tests.test_publication','tests.test_publication_p1'])
    result = unittest.TextTestRunner(verbosity=2, resultclass=MatrixResult).run(suite)
    cases = {i: {'status': 'PASS' if result.matrix.get(i) and all(x['status']=='PASS' for x in result.matrix[i]) else 'BLOCKED' if not result.matrix.get(i) else 'FAIL',
                 'evidence': result.matrix.get(i, [])} for i in sorted(EXPECTED)}
    report = {'schemaVersion':1, 'scope':'offline fixtures; not official new-day/live/remote acceptance',
              'pythonTests':result.testsRun, 'failures':len(result.failures), 'errors':len(result.errors), 'skips':len(result.skipped),
              'cases':cases, 'remoteAcceptance':{
                  'genesis-and-immutable-release':'NOT_AUTHORIZED', 'real-pages':'NOT_AUTHORIZED', 'real-rollback':'NOT_AUTHORIZED',
                  'P10-all-real-writers-coordinated':'BLOCKED: legacy first-release entry must be retired/integrated in 4C-2D',
                  'iPhone-Safari':'BLOCKED: physical-device acceptance remains required'},
              'realMutations':0, 'networkPolicy':'new publication tests deny real socket connections'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return 0 if result.wasSuccessful() and all(x['status']=='PASS' for x in cases.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
