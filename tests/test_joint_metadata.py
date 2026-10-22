"""Independent metadata composition preserves canonical bytes and exact payload boundaries."""
import hashlib
import unittest
from tools.installer.joint import composition_hashes


class JointMetadataTests(unittest.TestCase):
    def test_multiple_disjoint_payloads_and_canonical_immutability(self):
        original = b'HEADER:aaaa|bbbb|cccc:APPENDIX'
        expected = b'HEADER:AAAA|bbbb|CCCC:APPENDIX'
        self.assertEqual(composition_hashes(original, [(17,4,b'CCCC'), (7,4,b'AAAA')]),
                         hashlib.sha256(expected).hexdigest())
        self.assertEqual(original, b'HEADER:aaaa|bbbb|cccc:APPENDIX')
        self.assertEqual(composition_hashes(original, []), hashlib.sha256(original).hexdigest())

    def test_malformed_size_overlap_and_out_of_bounds_are_rejected(self):
        for spans in ([(2,4,b'X')], [(2,3,b'abc'),(4,2,b'xy')], [(-1,1,b'x')], [(7,2,b'xx')], [(2,0,b'')]):
            with self.subTest(spans=spans), self.assertRaises(ValueError):
                composition_hashes(b'12345678', spans)


if __name__ == '__main__':
    unittest.main()
