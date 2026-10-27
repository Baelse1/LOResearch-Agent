"""Mock-only adapter checks. No real authorization or inference."""
import unittest
from test_chatgpt_flow import AuthTests,StreamTests

if __name__=='__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(AuthTests),
                             unittest.defaultTestLoader.loadTestsFromTestCase(StreamTests)])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
