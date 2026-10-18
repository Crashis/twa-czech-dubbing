"""Established Hannibal 24 kHz mono PCM16 -> 32 kHz preparation (NumPy optional)."""
import argparse
import json
import math
from pathlib import Path
import wave
from tools.mod import sha256
from tools.pack.reader import require
from tools.wem.audio import pcm16

def prepare_game_wav(source, target, trailing_margin_ms=40):
    import numpy as np
    with wave.open(str(source),'rb') as audio:
        require(audio.getframerate()==24000 and audio.getnchannels()==1 and audio.getsampwidth()==2,'Unexpected source WAV')
        values = np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(np.float64)
    active = np.flatnonzero(np.abs(values) >= 32768*10**(-48/20))
    require(active.size>0,'Silent source')
    require(20 <= trailing_margin_ms <= 40, 'Unsupported trailing-silence margin')
    start=max(0,int(active[0])-480)
    end=min(len(values),int(active[-1])+1+round(24*trailing_margin_ms))
    trimmed=values[start:end]
    length=round(len(trimmed)*4/3)
    indexes=np.arange(length,dtype=np.int64)
    bases=indexes*3//4; phases=indexes*3%4
    result=np.zeros(length,dtype=np.float64)
    # Same 64-tap Lanczos sinc as the previously game-tested 24->32 kHz path.
    for phase in range(4):
        selected=np.flatnonzero(phases==phase)
        base=bases[selected]
        if phase==0:
            good=base<len(trimmed); result[selected[good]]=trimmed[base[good]]
            continue
        offsets=np.arange(-31,33)
        x=phase/4-offsets
        weights=np.sinc(x)*np.sinc(x/32)
        weights/=weights.sum()
        for offset,weight in zip(offsets,weights):
            src=base+offset; good=(src>=0)&(src<len(trimmed))
            result[selected[good]]+=trimmed[src[good]]*weight
    fade=.5-.5*np.cos(np.pi*np.arange(160)/159)
    result[:160]*=fade; result[-160:]*=fade[::-1]
    gain=min(1.,32768*10**(-4/20)/float(np.max(np.abs(result))))
    quantized=np.rint(result*gain).astype('<i2')
    target=Path(target)
    require(not target.exists(), 'Output already exists')
    with wave.open(str(target),'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(32000); audio.writeframes(quantized.tobytes())
    info,_=pcm16(target)
    report = {'source_sha256':sha256(source),'prepared':info,
         'trimmed_leading_seconds':start/24000,'trimmed_trailing_seconds':(len(values)-end)/24000,
         'silence_threshold_dbfs':-48,'margins_ms':[20,trailing_margin_ms],'resample':'64-tap Lanczos sinc 4/3',
         'gain_db':20*math.log10(gain),'peak_limit_dbfs':-4,'boundary_fades_ms':5,
         'time_stretch':False,'playback_speed_changed':False}
    return report


BAND_LIMIT_TAPS = 255
BAND_LIMIT_BETA = 6.76  # Kaiser window: about 70 dB stopband, about 0.55 kHz transition at 32 kHz


SHELF_TRANSITION_HZ = (4500, 6500)


def shelf_taps(shelf_db):
    """Zero-phase FIR: unity below 4.5 kHz, a smooth dB ramp, then a constant shelf_db above 6.5 kHz."""
    import numpy as np
    n = 8192
    freqs = np.fft.rfftfreq(n, 1 / 32000)
    low, high = SHELF_TRANSITION_HZ
    ramp = np.clip((freqs - low) / (high - low), 0, 1)
    gain = 10 ** (shelf_db * (.5 - .5 * np.cos(np.pi * ramp)) / 20)
    impulse = np.roll(np.fft.irfft(gain, n), BAND_LIMIT_TAPS // 2)[:BAND_LIMIT_TAPS]
    taps = impulse * np.kaiser(BAND_LIMIT_TAPS, BAND_LIMIT_BETA)
    return taps / taps.sum()


def band_limit_wav(source, target, cutoff_hz, shelf_db=0):
    """Linear-phase low-pass of a prepared 32 kHz PCM16 WAV; length, timing and level are kept.

    Matches band-limited original voice assets; it removes only content above the cutoff
    and never changes duration, pitch or the in-band waveform beyond FIR passband ripple.
    An optional mild static high shelf (at most -3 dB above 6.5 kHz) moves the TTS spectral tilt
    part of the way toward the measured, much darker original assets.
    """
    import numpy as np
    require(4000 <= cutoff_hz <= 15000, 'Unsupported band-limit cutoff')
    require(-3 <= shelf_db <= 0, 'Only a mild high shelf of at most -3 dB is allowed')
    info, pcm = pcm16(source)
    require(info['rate'] == 32000, 'Expected a prepared 32 kHz WAV')
    values = np.asarray(pcm, dtype=np.float64)
    offsets = np.arange(BAND_LIMIT_TAPS) - BAND_LIMIT_TAPS // 2
    taps = 2 * cutoff_hz / 32000 * np.sinc(2 * cutoff_hz / 32000 * offsets) * np.kaiser(BAND_LIMIT_TAPS, BAND_LIMIT_BETA)
    taps /= taps.sum()
    filtered = np.convolve(values, taps, mode='same')  # odd symmetric taps: zero phase, same length
    if shelf_db:
        filtered = np.convolve(filtered, shelf_taps(shelf_db), mode='same')
    require(np.max(np.abs(filtered)) < 32767, 'Band limit would clip')
    quantized = np.rint(filtered).astype('<i2')
    target = Path(target)
    require(not target.exists(), 'Output already exists')
    with wave.open(str(target), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(32000); audio.writeframes(quantized.tobytes())
    removed = values - filtered
    prepared, _ = pcm16(target)
    return {'source_sha256': sha256(source), 'source_pcm_sha256': info['pcm_sha256'], 'prepared': prepared,
            'band_limit': {'cutoff_hz': cutoff_hz, 'cutoff_definition': '-6 dB point', 'fir_taps': BAND_LIMIT_TAPS,
                           'window': f'Kaiser beta {BAND_LIMIT_BETA}', 'phase': 'linear (zero delay)',
                           'removed_energy_db': 10 * math.log10(max(float(removed @ removed) / float(values @ values), 1e-30)),
                           'high_shelf_db': shelf_db, 'high_shelf_transition_hz': list(SHELF_TRANSITION_HZ) if shelf_db else None},
            'time_stretch': False, 'playback_speed_changed': False, 'pitch_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(prepare_game_wav(args.source, args.output), indent=2))
