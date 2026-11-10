from copy import deepcopy
import json
from pathlib import Path
import unittest

from app.evaluation.scorecard import catalog, compare_baseline, fingerprint, row
from app.evaluation.scoring import score_knowledge

ROOT=Path(__file__).resolve().parents[1]


class ReviewedCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases={c['id']:c for c in catalog() if c['id'] in ('tc-054','tc-072')}
        cls.reviews={c['id']:c for c in json.loads((ROOT/'evals/expectation_reviews.json').read_text(encoding='utf-8'))['cases']}

    def state(self, answer):
        return {'status':'answered','answer':answer,'retrieved_chunks':[{'id':'vpn','document_id':'vpn_troubleshooting'}],
                'sources':[{'source_id':1,'chunk_id':'vpn'}]}

    def test_single_sufficient_policy_source_passes_without_forcing_a_second_document(self):
        answers={'tc-054':'No, free VPN workarounds are prohibited. [Source 1]',
                 'tc-072':'Only install the approved VPN client through Company Portal. [Source 1]'}
        for name,answer in answers.items():
            with self.subTest(case=name):
                checks,_=score_knowledge(self.cases[name],self.state(answer))
                self.assertTrue(all(checks.values()),checks)
                old=deepcopy(self.cases[name]);old['expected_document_ids']=self.reviews[name]['previous_expected_document_ids']
                old_checks,_=score_knowledge(old,self.state(answer))
                self.assertFalse(old_checks['expected_documents_actually_cited'])

    def test_incorrect_policy_and_unknown_citations_still_fail(self):
        for name,answer in [('tc-054','Yes, install a free VPN app. [Source 1]'),
                            ('tc-072','Only install it from an internet download site. [Source 1]'),
                            ('tc-072','Only use Company Portal. [Source 99]')]:
            with self.subTest(case=name,answer=answer):
                checks,_=score_knowledge(self.cases[name],self.state(answer))
                self.assertFalse(all(checks.values()))

    def test_reviewed_hashes_cannot_masquerade_as_unchanged_baselines(self):
        for name,case in self.cases.items():
            previous=self.reviews[name]['previous_expectation_hash']
            self.assertNotEqual(fingerprint(case),previous)
            new=row(case,{'status':'passed'})
            old={**new,'expectation_hash':previous,'status':'failed'}
            self.assertFalse(compare_baseline([new],{'results':[old]})['compatible'])
            self.assertEqual(case['expectation_revision'],2)
