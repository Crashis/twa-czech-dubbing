"""Offline invariants of the WEM production fallback; no encoder binaries are run."""
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
import wave

from tools import mod
from tools.wem.audio import pcm16
from tools.wem.encode import format_matches
from tools.wem.production import FALLBACK_PROFILES

NUMPY = importlib.util.find_spec('numpy') is not None


def tone_wav(path, parts, seconds=1.0, silence=None):
    import numpy as np
    t = np.arange(int(32000 * seconds)) / 32000
    values = sum(amplitude * np.sin(2 * math.pi * hz * t) for hz, amplitude in parts)
    if silence:
        start, end = silence
        values[int(start * 32000):int(end * 32000)] = 0
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(32000)
        audio.writeframes(np.rint(values).astype('<i2').tobytes())


def band_level(path, hz):
    import numpy as np
    _, pcm = pcm16(path)
    spectrum = np.abs(np.fft.rfft(np.asarray(pcm, dtype=np.float64)))
    return 20 * math.log10(spectrum[int(hz * len(pcm) / 32000)] + 1e-9)


class WemProductionTests(unittest.TestCase):
    def test_fallback_profiles_are_encoder_only_and_mildest_first(self):
        lowpass = []
        for name, options in FALLBACK_PROFILES:
            for option in options:
                key, _, value = option.partition('=')
                self.assertIn(key, {'lowpass_frequency', 'impulse_noisetune'}, name)
                if key == 'lowpass_frequency':
                    lowpass.append(float(value.replace(',', '.')))
        self.assertEqual(lowpass, sorted(lowpass, reverse=True))

    def test_non_arena_vorbis_blocks_are_rejected(self):
        expected = mod.load_manifest()['wem_format']
        arena = {'sample_rate': 32000, 'channels': 1, 'block_sizes': [256, 2048], 'subtype_channel_config': '0x4101'}
        self.assertTrue(format_matches(arena, expected))
        self.assertFalse(format_matches(arena | {'block_sizes': [512, 4096]}, expected))

    def test_recovery_ladder_is_mildest_first_and_evidence_bound(self):
        from tools.wem.recovery import ladder
        wide, narrow = ladder(7800), ladder(4800)
        plain = [c for c, shelf, tail in wide if not shelf and tail == 40]
        self.assertEqual(plain, sorted(plain, reverse=True))
        self.assertGreaterEqual(min(plain), 7000)  # below 7 kHz only where the line's own original is narrower
        self.assertIn((6500, 0, 40), narrow)
        self.assertTrue(all(c <= 8000 for c, shelf, _ in wide if shelf))
        first_shelf = next(i for i, (_, shelf, _) in enumerate(wide) if shelf)
        self.assertTrue(all(not shelf for _, shelf, _ in wide[:first_shelf]))
        # A new performance starts untouched; by default no cutoff is narrower than the original asset.
        self.assertEqual(ladder(7800, unfiltered=True)[0], (None, 0, 40))
        self.assertTrue(all(c is None or c >= 7500 for c, _, _ in ladder(7800, unfiltered=True)))
        self.assertIn((7000, 0, 40), ladder(7800, below_original=True))

    @unittest.skipUnless(NUMPY, 'NumPy is required for audio preparation')
    def test_band_limit_keeps_length_and_passband(self):
        from tools.wem.prepare import band_limit_wav
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder, 'in.wav'), Path(folder, 'out.wav')
            tone_wav(source, [(1000, 8000), (10000, 4000)])
            report = band_limit_wav(source, target, 8000)
            self.assertEqual(pcm16(target)[0]['frames'], pcm16(source)[0]['frames'])
            self.assertLess(abs(band_level(target, 1000) - band_level(source, 1000)), .1)
            self.assertLess(band_level(target, 10000) - band_level(source, 10000), -60)
            self.assertFalse(report['time_stretch'] or report['pitch_changed'])
            with self.assertRaises(ValueError):
                band_limit_wav(source, target, 8000)  # never overwrites
            with self.assertRaises(ValueError):
                band_limit_wav(source, Path(folder, 'strong.wav'), 8000, shelf_db=-6)

    @unittest.skipUnless(NUMPY, 'NumPy is required for audio preparation')
    def test_fidelity_guard_catches_dropouts_and_artifacts(self):
        from tools.wem.recovery import fidelity
        with tempfile.TemporaryDirectory() as folder:
            tts, same, dropout, noisy = (Path(folder, n + '.wav') for n in ('tts', 'same', 'dropout', 'noisy'))
            speech = [(300, 6000), (1200, 3000), (2500, 1500)]
            tone_wav(tts, speech)
            tone_wav(same, speech)
            tone_wav(dropout, speech, silence=(.40, .45))
            tone_wav(noisy, speech + [(5000, 9000)])
            self.assertEqual(fidelity(same, tts, 8000)['status'], 'PASS')
            missing = fidelity(dropout, tts, 8000)
            self.assertEqual(missing['status'], 'FAIL')
            self.assertGreater(missing['speech_dropout_frames'], 0)
            added = fidelity(noisy, tts, 8000)
            self.assertEqual(added['status'], 'FAIL')
            self.assertGreater(added['steady_added_energy_frames'], 0)


if __name__ == '__main__':
    unittest.main()
