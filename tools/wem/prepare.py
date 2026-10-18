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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(prepare_game_wav(args.source, args.output), indent=2))
