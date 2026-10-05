import unittest
from metadata import build_metadata

class MetadataTests(unittest.TestCase):
    def test_multiple_classifications_and_unknown_cap(self):
        result=build_metadata(['US.A','US.ETF'],
            [{'code':'US.A','total_market_val':30000000000,'update_time':'2026-10-05'},
             {'code':'US.ETF','total_market_val':float('nan')}],
            [{'code':'US.A','plate_type':'INDUSTRY','plate_name':'半导体'},
             {'code':'US.A','plate_type':'CONCEPT','plate_name':'AI'},
             {'code':'US.A','plate_type':'OTHER','plate_name':'券商营销列表'}],
            {'标普500':['US.A'],'纳斯达克100':['US.A']})
        self.assertEqual(result['US.A']['market_cap'],30000000000)
        self.assertEqual(result['US.A']['sectors'],['半导体','AI'])
        self.assertEqual(result['US.A']['indices'],['标普500','纳斯达克100'])
        self.assertIsNone(result['US.ETF']['market_cap'])
        self.assertEqual(result['US.ETF']['indices'],[])
